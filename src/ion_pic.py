"""Coupled electron and ion (H2+/H+ or D2+/D+) PIC with electron-impact ionization of neutral gas.

Cycles alternate a short external-gun electron window, run against the frozen ion charge, with a
long ion push in the window-mean electron charge plus the live ion charge. See docs/ion-pic-design.md.

The neutral density is a static background, pumped residual plus inlet throughput over pump speed,
plus an optional free-molecular effusive plume from a gas inlet: n(x) = Q cos(theta) / (pi vbar r^2)
with Q the molecular throughput, theta the angle from the inlet axis and r clamped to the inlet radius.

Ions are molecular (species 0) or atomic (species 1). A fraction `--dissociative-fraction` of
ionizations produce the atomic ion with `--dissociation-energy-ev` of isotropic kinetic energy. Charge
exchange on the fuel molecule leaves a thermal molecular ion for either species. An optional ion gun
injects either species as a monoenergetic beam with Gaussian spot radius and angular divergence.
"""

import argparse
import copy
import dataclasses
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
import torch

from cusp_sim import E_CHARGE, M_E
from electrostatic import EPSILON_0
from run_transient_pic import (
    GunSource,
    create_simulation,
    source_geometry,
    source_potential,
    validate,
)
from run_transient_pic import parser as pic_parser

AMU = 1.66053906660e-27
K_B = 1.380649e-23
LOTZ_A_M2_EV2 = 4.5e-18
H2_IONIZATION_EV = 15.43
H2_SHELL_ELECTRONS = 2
SECONDARY_BATCH = 16
FUELS = {"H2": (2.016, 1.008, 15.43), "D2": (4.028, 2.014, 15.47)}  # molecule and atom in amu, ionization eV
SPECIES = ("molecular", "atomic")
ION_GUN_PHASES = ("always", "electron-on", "electron-off")


def parser() -> argparse.ArgumentParser:
    result = pic_parser()
    result.description = __doc__
    result.add_argument("--fuel", choices=tuple(FUELS), default="H2")
    result.add_argument("--gas-pa", type=float, default=1e-3, help="residual background pressure")
    result.add_argument("--gas-temperature-k", type=float, default=300)
    result.add_argument("--gas-inlet", type=float, nargs=3, default=None, help="inlet position (m)")
    result.add_argument("--gas-inlet-direction", type=float, nargs=3, default=None,
                        help="plume axis; defaults to pointing at the origin")
    result.add_argument("--gas-inlet-throughput", type=float, default=0.0, help="Pa m^3/s")
    result.add_argument("--gas-inlet-radius", type=float, default=5e-3, help="m")
    result.add_argument("--pump-speed", type=float, default=1.0, help="m^3/s")
    result.add_argument("--ionization-scale", type=float, default=1.0)
    result.add_argument("--cx-cross-section", type=float, default=5e-20, help="m^2")
    result.add_argument("--ion-mass-amu", type=float, default=None, help="molecular ion mass; defaults to the fuel molecule")
    result.add_argument("--dissociative-fraction", type=float, default=0.0,
                        help="fraction of ionizations producing the atomic ion")
    result.add_argument("--dissociation-energy-ev", type=float, default=5.0,
                        help="isotropic kinetic energy of dissociatively born atomic ions")
    result.add_argument("--ion-temperature-ev", type=float, default=0.05)
    result.add_argument("--ion-gun-current", type=float, default=0.0, help="A")
    result.add_argument("--ion-gun-species", choices=SPECIES, default="molecular")
    result.add_argument("--ion-gun-position", type=float, nargs=3, default=None, help="m")
    result.add_argument("--ion-gun-direction", type=float, nargs=3, default=None,
                        help="beam axis; defaults to pointing at the origin")
    result.add_argument("--ion-gun-energy-ev", type=float, default=100.0)
    result.add_argument("--ion-gun-divergence-deg", type=float, default=5.0, help="RMS angle per transverse axis")
    result.add_argument("--ion-gun-radius", type=float, default=5e-3, help="RMS spot size per transverse axis (m)")
    result.add_argument("--ion-gun-phase", choices=ION_GUN_PHASES, default="always",
                        help="cycles in which the ion gun injects, relative to the electron gun state")
    result.add_argument("--secondaries", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--secondary-temperature-ev", type=float, default=3.0)
    result.add_argument("--secondary-every", type=int, default=64, help="electron steps per secondary batch")
    result.add_argument("--gun-period-cycles", type=int, default=0,
                        help="electron-gun on/off period in cycles; 0 injects every cycle")
    result.add_argument("--gun-on-cycles", type=int, default=0, help="leading cycles of each period with the gun on")
    result.add_argument("--gun-settle", type=float, default=2e-7,
                        help="electron time advanced when the gun switches, before the cycle's window (s)")
    result.add_argument("--electron-startup", type=float, default=2e-7)
    result.add_argument("--electron-window", type=float, default=4e-8)
    result.add_argument("--electron-samples", type=int, default=16)
    result.add_argument("--ion-dt", type=float, default=1e-9)
    result.add_argument("--cycle-duration", type=float, default=1e-5)
    result.add_argument("--cycles", type=int, default=40)
    result.add_argument("--ions-per-cycle", type=int, default=8192)
    result.add_argument("--ion-batches", type=int, default=64)
    result.add_argument("--ion-field-every", type=int, default=10)
    result.add_argument("--max-live-ions", type=int, default=2_000_000)
    result.add_argument("--save-every-cycles", type=int, default=4)
    return result


def steps_for(duration: float, dt: float, name: str) -> int:
    steps = round(duration / dt)
    if steps < 1 or abs(steps * dt - duration) > 1e-9 * duration:
        raise ValueError(f"{name} must be a positive integer multiple of its timestep")
    return steps


@dataclass(frozen=True)
class Plan:
    startup_steps: int
    window_steps: int
    ion_steps: int
    batch_every: int
    per_batch: int
    settle_steps: int


def validate_coupled(args: argparse.Namespace) -> Plan:
    positive = (args.gas_temperature_k, ion_mass_amu(args), args.ion_dt, args.cycle_duration,
                args.gas_inlet_radius, args.pump_speed, args.gas_pa + args.gas_inlet_throughput)
    if not all(math.isfinite(value) and value > 0 for value in positive):
        raise ValueError("Gas temperature and pressure, ion mass, ion timestep, cycle, inlet radius and pump "
                         "speed must be positive")
    if args.gas_inlet_throughput and args.gas_inlet is None:
        raise ValueError("Gas inlet throughput requires --gas-inlet")
    if args.gas_inlet is not None and math.dist(aim(args.gas_inlet, args.gas_inlet_direction), (0, 0, 0)) == 0:
        raise ValueError("Gas inlet direction must be nonzero")
    if args.ion_gun_current and args.ion_gun_position is None:
        raise ValueError("Ion gun current requires --ion-gun-position")
    if args.ion_gun_position is not None and math.dist(aim(args.ion_gun_position, args.ion_gun_direction),
                                                       (0, 0, 0)) == 0:
        raise ValueError("Ion gun direction must be nonzero")
    if not (math.isfinite(args.ion_gun_energy_ev) and args.ion_gun_energy_ev > 0
            and 0 <= args.ion_gun_divergence_deg < 90):
        raise ValueError("Ion gun energy must be positive and divergence in [0, 90) degrees")
    if not (0 <= args.dissociative_fraction <= 1 and math.isfinite(args.dissociation_energy_ev)
            and args.dissociation_energy_ev >= 0):
        raise ValueError("Dissociative fraction must be in [0, 1] and dissociation energy nonnegative")
    nonnegative = (args.gas_pa, args.gas_inlet_throughput, args.ionization_scale, args.cx_cross_section,
                   args.ion_temperature_ev, args.secondary_temperature_ev, args.ion_gun_current, args.ion_gun_radius)
    if not all(math.isfinite(value) and value >= 0 for value in nonnegative):
        raise ValueError("Ionization scale, cross section, temperatures and ion gun current and radius must be "
                         "nonnegative")
    if (args.cycles < 1 or args.electron_samples < 1 or args.ion_field_every < 1 or args.secondary_every < 1
            or args.save_every_cycles < 1 or args.ions_per_cycle < 1 or args.ion_batches < 1
            or args.ions_per_cycle % args.ion_batches or args.max_live_ions < 1):
        raise ValueError("Invalid cycle, sampling or ion particle settings")
    if not (0 < args.gun_on_cycles < args.gun_period_cycles or args.gun_on_cycles == args.gun_period_cycles == 0):
        raise ValueError("A pulsed gun needs 0 < gun-on-cycles < gun-period-cycles; continuous needs both 0")
    if args.ion_gun_phase != "always" and not args.gun_period_cycles:
        raise ValueError("A gated ion gun requires a pulsed electron gun")
    startup = steps_for(args.electron_startup, args.dt, "electron-startup")
    window = steps_for(args.electron_window, args.dt, "electron-window")
    ion_steps = steps_for(args.cycle_duration, args.ion_dt, "cycle-duration")
    if window < 2 * args.electron_samples or ion_steps < args.ion_batches:
        raise ValueError("Windows need two steps per electron sample and cycles one step per ion batch")
    settle = steps_for(args.gun_settle, args.dt, "gun-settle") if args.gun_period_cycles else 0
    validate(electron_arguments(args, startup + args.cycles * window + gun_transitions(args) * settle))
    return Plan(startup, window, ion_steps, ion_steps // args.ion_batches, args.ions_per_cycle // args.ion_batches,
                settle)


def gun_schedule(args: argparse.Namespace) -> list[bool]:
    """Electron-gun state per cycle; index 0 is the startup window, which always injects."""
    period, on = args.gun_period_cycles, args.gun_on_cycles
    return [True] + [not period or (cycle - 1) % period < on for cycle in range(1, args.cycles + 1)]


def gun_transitions(args: argparse.Namespace) -> int:
    schedule = gun_schedule(args)
    return sum(before != after for before, after in itertools.pairwise(schedule))


def ion_mass_amu(args: argparse.Namespace) -> float:
    return FUELS[args.fuel][0] if args.ion_mass_amu is None else args.ion_mass_amu


def species_label(args: argparse.Namespace, species: str) -> str:
    return f"{args.fuel}+" if species == "molecular" else f"{args.fuel[0]}+"


def atomic_enabled(args: argparse.Namespace) -> bool:
    return args.dissociative_fraction > 0 or (args.ion_gun_current > 0 and args.ion_gun_species == "atomic")


def aim(position: list[float], direction: list[float] | None) -> tuple[float, ...]:
    """Source axis: `direction`, or from `position` toward the origin."""
    return tuple(-item for item in position) if direction is None else tuple(direction)


def transverse_basis(axis: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Two unit vectors perpendicular to the unit vector `axis` and to each other."""
    helper = torch.zeros_like(axis)
    helper[int(axis.abs().argmin())] = 1
    first = torch.linalg.cross(axis, helper)
    first = first / first.norm()
    return first, torch.linalg.cross(axis, first)


def electron_arguments(args: argparse.Namespace, steps: int) -> argparse.Namespace:
    """Gun and electron PIC settings spanning every electron window, as one continuous electron run."""
    electron = copy.copy(args)
    electron.duration = args.electron_startup + args.cycles * args.electron_window
    if args.gun_period_cycles:
        electron.duration += gun_transitions(args) * args.gun_settle
    electron.max_steps = steps
    electron.save_every = steps
    return electron


def ionization_cross_section(energy_ev: torch.Tensor, threshold_ev: float = H2_IONIZATION_EV) -> torch.Tensor:
    """Lotz electron-impact ionization cross section of a two-electron molecule in m^2; zero below threshold."""
    energy = energy_ev.clamp(min=threshold_ev)
    sigma = LOTZ_A_M2_EV2 * H2_SHELL_ELECTRONS * torch.log(energy / threshold_ev) / (energy * threshold_ev)
    return torch.where(energy_ev > threshold_ev, sigma, 0.0)


@dataclass
class Ions:
    position: torch.Tensor
    velocity: torch.Tensor
    weight: torch.Tensor
    birth: torch.Tensor
    birth_potential: torch.Tensor
    core_time: torch.Tensor
    entries: torch.Tensor
    exchanges: torch.Tensor
    species: torch.Tensor

    def tensors(self) -> tuple[torch.Tensor, ...]:
        return (self.position, self.velocity, self.weight, self.birth, self.birth_potential,
                self.core_time, self.entries, self.exchanges, self.species)

    def select(self, keep: torch.Tensor) -> "Ions":
        return Ions(*(tensor[keep] for tensor in self.tensors()))

    def cat(self, other: "Ions") -> "Ions":
        return Ions(*(torch.cat(pair) for pair in zip(self.tensors(), other.tensors(), strict=True)))


class PopulationLimit(Exception):
    pass


class CoupledPIC:
    def __init__(self, args: argparse.Namespace, plan: Plan) -> None:
        self.args = args
        self.plan = plan
        electron_args = electron_arguments(args, plan.startup_steps + args.cycles * plan.window_steps)
        self.electrons, self.configuration = create_simulation(electron_args)
        self.gun_on = True
        self.mesh = self.electrons.mesh
        self.kernels = self.electrons.kernels
        self.conductors = self.electrons.conductors
        device = self.mesh.lower.device
        self.ion_mass = ion_mass_amu(args) * AMU
        self.qm = E_CHARGE / self.ion_mass
        self.species_mass = torch.tensor((self.ion_mass, FUELS[args.fuel][1] * AMU), dtype=torch.float64, device=device)
        self.qm_ratio = self.ion_mass / self.species_mass
        self.max_qm = E_CHARGE / float(self.species_mass[1]) if atomic_enabled(args) else self.qm
        bmax = cast(float, self.configuration["magnetic_table_max_T"])
        if self.max_qm * bmax * args.ion_dt > 2 * math.pi / 80:
            raise ValueError("Ion timestep requires at least 80 steps per gyration")
        kt = K_B * args.gas_temperature_k
        self.gas_density = (args.gas_pa + args.gas_inlet_throughput / args.pump_speed) / kt
        self.inlet: tuple[torch.Tensor, torch.Tensor, float] | None = None
        if args.gas_inlet is not None:
            axis = torch.tensor(aim(args.gas_inlet, args.gas_inlet_direction), dtype=torch.float64, device=device)
            molecule = FUELS[args.fuel][0] * AMU
            speed = math.sqrt(8 * kt / (math.pi * molecule))
            strength = args.gas_inlet_throughput / kt / (math.pi * speed)
            self.inlet = (torch.tensor(args.gas_inlet, dtype=torch.float64, device=device), axis / axis.norm(), strength)
        self.ion_gun: tuple[torch.Tensor, ...] | None = None
        if args.ion_gun_position is not None:
            axis = torch.tensor(aim(args.ion_gun_position, args.ion_gun_direction), dtype=torch.float64, device=device)
            axis = axis / axis.norm()
            self.ion_gun = (torch.tensor(args.ion_gun_position, dtype=torch.float64, device=device), axis,
                            *transverse_basis(axis))
        self.ion_gun_species = SPECIES.index(args.ion_gun_species)
        self.ion_gun_charge = 0.0
        self.generator = torch.Generator(device=device).manual_seed(args.seed + 7919)
        self.source = GunSource(electron_args)
        self.origin, _ = source_geometry(args)
        self.electron_step = 0
        self.time = 0.0
        empty = self.mesh.lower.new_empty(0)
        self.ions = Ions(
            empty.reshape(0, 3), empty.reshape(0, 3), empty.clone(), empty.clone(), empty.clone(),
            empty.clone(), empty.long(), empty.long(), empty.long(),
        )
        shapes = 0 if self.conductors is None else len(self.conductors.shapes)
        self.ion_exit_counts = torch.zeros(6 + shapes, device=device, dtype=torch.int64)
        self.ion_totals = empty.new_zeros(4)  # created charge, lost charge, lost kinetic, exchanged kinetic
        self.ion_created = 0
        self.ion_exchanges = torch.zeros((), device=device, dtype=torch.int64)
        self.secondary_charge = 0.0
        self.rate = 0.0
        self.pool = empty.reshape(0, 3)
        self.ion_conductor_charge = empty.new_zeros(shapes)

    def neutral_density(self, position: torch.Tensor) -> torch.Tensor:
        """Background plus effusive inlet-plume neutral molecule density at `position` in m^-3."""
        density = position.new_full((len(position),), self.gas_density)
        if self.inlet is None:
            return density
        origin, axis, strength = self.inlet
        offset = position - origin
        distance = offset.norm(dim=1).clamp(min=self.args.gas_inlet_radius)
        cosine = (offset @ axis / distance).clamp(min=0, max=1)
        return density + strength * cosine / distance.square()

    def ion_charge(self) -> torch.Tensor:
        return self.kernels.deposit(self.ions.position, E_CHARGE * self.ions.weight)

    def potential(self, charge: torch.Tensor) -> torch.Tensor:
        if self.conductors is None:
            return self.kernels.potential(charge)
        potential, self.ion_conductor_charge = self.conductors.potential(charge)
        return potential

    def sample_electrons(self, count: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Deposited electron charge, ionizations per second, and `count` rate-weighted birth positions."""
        p = self.electrons.particles
        charge = self.kernels.deposit(p.position, -E_CHARGE * p.weight)
        speed = p.velocity.norm(dim=1)
        energy_ev = 0.5 * M_E * speed.square() / E_CHARGE
        sigma = ionization_cross_section(energy_ev, FUELS[self.args.fuel][2])
        rates = self.neutral_density(p.position) * self.args.ionization_scale * p.weight * sigma * speed
        total = rates.sum()
        if bool((rates < 0).any()):
            raise ValueError("Ionization rates must be nonnegative")
        if not len(p.ids) or float(total) <= 0:
            return charge, total, p.position.new_empty((0, 3))
        index = torch.multinomial(rates, count, replacement=True, generator=self.generator)
        return charge, total, p.position[index]

    def inject_secondaries(self) -> None:
        args = self.args
        if not args.secondaries or not len(self.pool) or self.rate <= 0:
            return
        index = torch.randint(len(self.pool), (SECONDARY_BATCH,), generator=self.generator, device=self.pool.device)
        thermal = math.sqrt(args.secondary_temperature_ev * E_CHARGE / M_E)
        velocity = thermal * torch.randn(
            (SECONDARY_BATCH, 3), generator=self.generator, dtype=torch.float64, device=self.pool.device,
        )
        weight = self.rate * args.secondary_every * args.dt / SECONDARY_BATCH
        before = self.electrons.injected_charge
        self.electrons.inject(self.pool[index], velocity, torch.full_like(velocity[:, 0], weight))
        self.secondary_charge += self.electrons.injected_charge - before

    def electron_window(self, steps: int) -> torch.Tensor:
        """Advance electrons against the frozen ion charge; return the second-half mean electron charge."""
        args = self.args
        electrons = self.electrons
        electrons.background_charge = self.ion_charge()
        every = max(1, (steps // 2) // args.electron_samples)
        sample_steps = {steps - 1 - k * every for k in range(args.electron_samples)}
        per_sample = math.ceil(4 * args.ions_per_cycle / args.electron_samples)
        charges, rates, pools = [], [], []
        for index in range(steps):
            if len(electrons.particles.ids) + args.inject_per_step + SECONDARY_BATCH > args.max_live_particles:
                raise PopulationLimit("electron population reached max-live-particles")
            if self.gun_on:
                self.source.inject(electrons, self.electron_step)
            if self.electron_step % args.secondary_every == 0:
                self.inject_secondaries()
            electrons.advance(args.dt)
            self.electron_step += 1
            electrons.time = self.electron_step * args.dt
            if index in sample_steps:
                charge, rate, births = self.sample_electrons(per_sample)
                charges.append(charge)
                rates.append(rate)
                pools.append(births)
        self.rate = float(torch.stack(rates).mean())
        self.pool = torch.cat(pools)
        self.pool = self.pool[torch.randperm(len(self.pool), generator=self.generator, device=self.pool.device)]
        return torch.stack(charges).mean(dim=0)

    def create_ions(self, count: int, weight: float, potential: torch.Tensor, start: int) -> None:
        args = self.args
        if count == 0 or not len(self.pool) or weight <= 0:
            return
        if len(self.ions.weight) + count > args.max_live_ions:
            raise PopulationLimit("ion population reached max-live-ions")
        position = self.pool[(start + torch.arange(count, device=self.pool.device)) % len(self.pool)]
        thermal = math.sqrt(args.ion_temperature_ev * E_CHARGE / self.ion_mass)
        velocity = thermal * torch.randn((count, 3), generator=self.generator, dtype=torch.float64, device=position.device)
        species = torch.zeros(count, dtype=torch.long, device=position.device)
        if args.dissociative_fraction > 0:
            atomic = torch.rand(count, generator=self.generator, dtype=torch.float64,
                                device=position.device) < args.dissociative_fraction
            direction = torch.randn((count, 3), generator=self.generator, dtype=torch.float64, device=position.device)
            speed = math.sqrt(2 * args.dissociation_energy_ev * E_CHARGE / float(self.species_mass[1]))
            velocity = torch.where(atomic[:, None], speed * direction / direction.norm(dim=1, keepdim=True), velocity)
            species = atomic.long()
        self.append_ions(position, velocity, weight, potential, species)

    @property
    def ion_gun_on(self) -> bool:
        phase = self.args.ion_gun_phase
        return phase == "always" or (phase == "electron-on") == self.gun_on

    def inject_gun_ions(self, count: int, potential: torch.Tensor) -> None:
        """Append `count` ion-gun macroparticles carrying one batch of the gun current."""
        args = self.args
        if self.ion_gun is None or not args.ion_gun_current or not self.ion_gun_on:
            return
        if len(self.ions.weight) + count > args.max_live_ions:
            raise PopulationLimit("ion population reached max-live-ions")
        origin, axis, first, second = self.ion_gun
        spot, angle = torch.randn((2, count, 2), generator=self.generator, dtype=torch.float64, device=origin.device)
        position = origin + args.ion_gun_radius * (spot[:, :1] * first + spot[:, 1:] * second)
        spread = math.tan(math.radians(args.ion_gun_divergence_deg))
        direction = axis + spread * (angle[:, :1] * first + angle[:, 1:] * second)
        speed = math.sqrt(2 * args.ion_gun_energy_ev * E_CHARGE / float(self.species_mass[self.ion_gun_species]))
        weight = args.ion_gun_current * args.cycle_duration / (E_CHARGE * args.ions_per_cycle)
        species = torch.full((count,), self.ion_gun_species, dtype=torch.long, device=origin.device)
        self.append_ions(position, speed * direction / direction.norm(dim=1, keepdim=True), weight, potential, species)
        self.ion_gun_charge += E_CHARGE * weight * count

    def append_ions(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: float, potential: torch.Tensor,
        species: torch.Tensor,
    ) -> None:
        count = len(position)
        weights = position.new_full((count,), weight)
        phi = self.mesh.gather(potential, position)[0]
        zeros = torch.zeros_like(weights)
        self.ions = self.ions.cat(Ions(
            position, velocity, weights, position.new_full((count,), self.time), phi, zeros.clone(),
            zeros.long(), zeros.long(), species,
        ))
        self.ion_totals[0] += E_CHARGE * weight * count
        self.ion_created += count

    def ion_kinetic_ev(self) -> torch.Tensor:
        return self.kinetic_j(self.ions) / E_CHARGE

    def kinetic_j(self, ions: Ions) -> torch.Tensor:
        return 0.5 * self.species_mass[ions.species] * ions.velocity.square().sum(dim=1)

    def drift_ions(self, h: float) -> None:
        ions = self.ions
        if not len(ions.weight):
            return
        end, fraction, wall, inside, entered = self.kernels.drift(
            ions.position, ions.velocity, h, self.electrons.core_radius,
        )
        hit = wall
        absorbed = None
        if self.conductors is not None:
            absorbed = self.conductors.absorbing(end)
            hit = wall | (absorbed >= 0)
        ions.core_time += h * fraction * inside
        ions.entries += entered.long()
        ions.position = end
        if not bool(hit.any()):
            return
        lost = ions.select(hit)
        self.ion_totals[1] += E_CHARGE * lost.weight.sum()
        self.ion_totals[2] += (lost.weight * self.kinetic_j(lost)).sum()
        distances = torch.stack((
            (lost.position - self.mesh.lower).abs() / self.mesh.h,
            (lost.position - self.mesh.upper).abs() / self.mesh.h,
        ), dim=2).flatten(start_dim=1)
        faces = distances.argmin(dim=1)
        if absorbed is not None:
            faces = torch.where(wall[hit], faces, 6 + absorbed[hit])
        self.ion_exit_counts.index_add_(0, faces, torch.ones_like(faces))
        self.ions = ions.select(~hit)

    def exchange(self, h: float) -> None:
        args = self.args
        ions = self.ions
        if not args.cx_cross_section or not len(ions.weight):
            return
        speed = ions.velocity.norm(dim=1)
        probability = -torch.expm1(-self.neutral_density(ions.position) * args.cx_cross_section * speed * h)
        exchanged = torch.rand(speed.shape, generator=self.generator, dtype=torch.float64, device=speed.device) < probability
        thermal = math.sqrt(args.gas_temperature_k * K_B / self.ion_mass)
        replacement = thermal * torch.randn(ions.velocity.shape, generator=self.generator, dtype=torch.float64,
                                            device=speed.device)
        mask = exchanged[:, None]
        self.ion_totals[3] += (ions.weight * exchanged * (
            self.kinetic_j(ions) - 0.5 * self.ion_mass * replacement.square().sum(dim=1))).sum()
        ions.velocity = torch.where(mask, replacement, ions.velocity)
        ions.species = torch.where(exchanged, 0, ions.species)
        ions.exchanges += exchanged.long()
        self.ion_exchanges += exchanged.sum()

    def accelerate(self, potential: torch.Tensor, h: float) -> None:
        """Boris velocity update; per-species charge-to-mass enters as a scale on E and B at the molecular q/m."""
        ions = self.ions
        ratio = self.qm_ratio[ions.species][:, None]
        electric = ratio * self.kernels.gather(potential, ions.position)
        magnetic = ratio * self.electrons.magnetic_field(ions.position)
        ions.velocity = self.kernels.boris(ions.velocity, electric, magnetic, h, self.qm)

    def check_ions(self, h: float, charge: torch.Tensor) -> None:
        if not len(self.ions.weight):
            return
        speed = self.ions.velocity.norm(dim=1).max()
        omega = torch.sqrt(charge.clamp(min=0).max() / (self.mesh.volume * EPSILON_0) * self.max_qm)
        speeding, oscillating, finite = torch.stack((
            speed * h > 0.2 * self.mesh.h.min(), omega * h > 0.1, torch.isfinite(speed),
        )).tolist()
        if not finite:
            raise ValueError("Nonfinite ion velocity")
        if speeding:
            raise ValueError("Ion timestep exceeds the 0.2-cell drift bound")
        if oscillating:
            raise ValueError("Ion timestep exceeds omega_pi * dt <= 0.1")

    def ion_cycle(self, electron_charge: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Push ions over one cycle; returns final total potential and time-weighted core kinetic sums."""
        args, plan = self.args, self.plan
        h = args.ion_dt
        weight = self.rate * args.cycle_duration / args.ions_per_cycle
        core_kinetic = electron_charge.new_zeros(())
        core_weight = electron_charge.new_zeros(())
        potential = self.potential(electron_charge + self.ion_charge())
        for step in range(plan.ion_steps):
            if step % plan.batch_every == 0 and step // plan.batch_every < args.ion_batches:
                self.create_ions(plan.per_batch, weight, potential, step // plan.batch_every * plan.per_batch)
                self.inject_gun_ions(plan.per_batch, potential)
            self.drift_ions(h / 2)
            if step % args.ion_field_every == 0:
                ion_charge = self.ion_charge()
                self.check_ions(h, ion_charge)
                potential = self.potential(electron_charge + ion_charge)
            if len(self.ions.weight):
                self.accelerate(potential, h)
                self.exchange(h)
            self.drift_ions(h / 2)
            ions = self.ions
            if len(ions.weight):
                core = ions.position.square().sum(dim=1) < self.electrons.core_radius ** 2
                core_weight += h * (ions.weight * core).sum()
                core_kinetic += h * (ions.weight * core * self.ion_kinetic_ev()).sum()
            self.time += h
        return self.potential(electron_charge + self.ion_charge()), core_kinetic, core_weight

    def record(
        self, cycle: int, electron_charge: torch.Tensor, potential: torch.Tensor,
        core_kinetic: torch.Tensor, core_weight: torch.Tensor, start: float,
    ) -> dict[str, object]:
        args = self.args
        mesh = self.mesh
        charge, electron_potential = self.electrons.fields()
        electrons = self.electrons.diagnostics(charge, electron_potential)
        ions = self.ions
        ion_charge = self.ion_charge()
        alive_ion_charge = float(E_CHARGE * ions.weight.sum())
        created, lost, lost_kinetic, exchanged_kinetic = self.ion_totals.tolist()
        axes = [torch.linspace(float(mesh.lower[i]), float(mesh.upper[i]), n, dtype=torch.float64,
                               device=mesh.lower.device) for i, n in enumerate(mesh.shape)]
        grid = torch.meshgrid(*axes, indexing="ij")
        core_nodes = sum(axis.square() for axis in grid) < self.electrons.core_radius ** 2
        mean_electron = float(electron_charge.sum())
        core_electron = float(electron_charge[core_nodes].sum())
        core_ion = float(ion_charge[core_nodes].sum())
        in_core = ions.position.square().sum(dim=1) < self.electrons.core_radius ** 2
        kinetic = self.ion_kinetic_ev()
        bound = ions.weight * (kinetic + mesh.gather(potential, ions.position)[0] < 0)
        record: dict[str, object] = {
            "cycle": cycle, "time_s": self.time, "electron_time_s": self.electrons.time,
            "electron_steps": self.electron_step, "electron_gun_on": self.gun_on, "ion_gun_on": self.ion_gun_on,
            "window_mean_electron_charge_C": mean_electron,
            "window_mean_core_electron_charge_C": core_electron,
            "electron_residence_s": abs(mean_electron) / args.current_a if args.current_a else None,
            "secondary_injected_charge_C": self.secondary_charge,
            "ion_gun_injected_charge_C": self.ion_gun_charge,
            "ionization_rate_s": self.rate,
            "neutralization_time_s": abs(mean_electron) / (E_CHARGE * self.rate) if self.rate else None,
            "ion_count": len(ions.weight), "ion_created_count": self.ion_created,
            "atomic_ion_count": int(ions.species.sum()),
            "atomic_ion_alive_charge_C": float(E_CHARGE * (ions.weight * ions.species).sum()),
            "ion_created_charge_C": created, "ion_lost_charge_C": lost, "ion_alive_charge_C": alive_ion_charge,
            "ion_charge_balance_C": created - lost - alive_ion_charge,
            "ion_bound_charge_C": float(E_CHARGE * bound.sum()),
            "atomic_ion_bound_charge_C": float(E_CHARGE * (bound * ions.species).sum()),
            "ion_deposition_error_C": float(ion_charge.sum()) - alive_ion_charge,
            "ion_lost_kinetic_J": lost_kinetic, "ion_exchanged_kinetic_J": exchanged_kinetic,
            "ion_exchange_events": int(self.ion_exchanges),
            "ion_exit_counts": self.ion_exit_counts.tolist(),
            "core_ion_charge_C": core_ion,
            "neutralization_fraction": alive_ion_charge / abs(mean_electron) if mean_electron else None,
            "core_neutralization_fraction": core_ion / abs(core_electron) if core_electron else None,
            "ion_mean_kinetic_eV": float((ions.weight * kinetic).sum() / ions.weight.sum()) if len(ions.weight) else None,
            "ion_core_count": int(in_core.sum()),
            "ion_core_time_weighted_kinetic_eV": float(core_kinetic / core_weight) if float(core_weight) else None,
            "potential_min_V": float(potential.min()),
            "potential_max_V": float(potential.max()),
            "potential_origin_V": float(mesh.gather(potential, mesh.lower.new_zeros((1, 3)))[0][0]),
            "core_mean_potential_V": float(potential[core_nodes].mean()),
            "source_potential_V": source_potential(self.electrons, potential, self.origin),
            "field_energy_J": float(mesh.field_energy(potential)),
            "ion_conductor_charge_C": self.ion_conductor_charge.tolist(),
            "electrons": electrons,
            "wall_s": time.perf_counter() - start,
        }
        return record

    def save(self, directory: Path, cycle: int, electron_charge: torch.Tensor, potential: torch.Tensor) -> str:
        ions = self.ions
        electrons = self.electrons.particles
        arrays = {
            "potential_V": potential, "electron_charge_C": electron_charge, "ion_charge_C": self.ion_charge(),
            "electron_position_m": electrons.position, "electron_velocity_m_s": electrons.velocity,
            "electron_count": electrons.weight,
            "ion_position_m": ions.position, "ion_velocity_m_s": ions.velocity, "ion_count": ions.weight,
            "ion_birth_s": ions.birth, "ion_birth_potential_V": ions.birth_potential,
            "ion_core_time_s": ions.core_time, "ion_core_entries": ions.entries, "ion_exchanges": ions.exchanges,
            "ion_species": ions.species,
            "lower_m": self.mesh.lower, "upper_m": self.mesh.upper,
        }
        name = f"cycle-{cycle:05d}.npz"
        temporary = (directory / name).with_suffix(".tmp")
        with temporary.open("wb") as stream:
            np.savez_compressed(
                stream, allow_pickle=False, time_s=self.time, cycle=cycle,
                **{key: value.cpu().numpy() for key, value in arrays.items()},
            )
        temporary.replace(directory / name)
        return f"snapshots/{name}"


def run(args: argparse.Namespace) -> list[dict[str, object]]:
    plan = validate_coupled(args)
    simulation = CoupledPIC(args, plan)
    args.out.mkdir(parents=True, exist_ok=False)
    snapshots = args.out / "snapshots"
    snapshots.mkdir()
    configuration = {
        **simulation.configuration,
        "model": "coupled-electron-ion-pic-v1",
        "coupling": "operator-split cycles: electron window on frozen ions, ion push on window-mean electrons",
        "ionization": f"electron impact on {args.fuel}: static background plus effusive inlet plume, Lotz cross section",
        "ion_species": f"{args.fuel}+",
        "atomic_ion_species": species_label(args, "atomic"),
        "atomic_ion_mass_amu": FUELS[args.fuel][1],
        "dissociative_ionization": {
            "fraction": args.dissociative_fraction, "atomic_energy_eV": args.dissociation_energy_ev,
            "model": "fixed branching ratio, isotropic monoenergetic atomic ion, neutral atom not tracked",
        },
        "ion_gun": None if simulation.ion_gun is None else {
            "species": species_label(args, args.ion_gun_species), "current_A": args.ion_gun_current, "position_m": args.ion_gun_position,
            "direction": simulation.ion_gun[1].tolist(), "energy_eV": args.ion_gun_energy_ev,
            "divergence_deg": args.ion_gun_divergence_deg, "radius_m": args.ion_gun_radius,
            "phase": args.ion_gun_phase,
        },
        "gas_inlet": None if args.gas_inlet is None else {
            "position_m": args.gas_inlet, "direction": aim(args.gas_inlet, args.gas_inlet_direction),
            "throughput_Pa_m3_s": args.gas_inlet_throughput, "radius_m": args.gas_inlet_radius,
            "pump_speed_m3_s": args.pump_speed, "temperature_K": args.gas_temperature_k,
            "model": "free-molecular cosine-law plume, no shadowing or wall reflection",
        },
        "electron_gun_pulse": None if not args.gun_period_cycles else {
            "period_s": args.gun_period_cycles * args.cycle_duration, "on_s": args.gun_on_cycles * args.cycle_duration,
            "settle_s": args.gun_settle, "transitions": gun_transitions(args),
            "model": "gun switched at cycle boundaries; electrons advance gun-settle on frozen ions at each switch",
        },
        "ion_mass_amu": ion_mass_amu(args),
        "gas_density_m3": simulation.gas_density,
        "gas_density_at_origin_m3": float(simulation.neutral_density(simulation.mesh.lower.new_zeros((1, 3)))[0]),
        "ion_charge_to_mass_C_kg": simulation.qm,
        "plan": dataclasses.asdict(plan),
        "validation_scope": (
            "numerical model; sub-sampled electron time, no Coulomb collisions, gas depletion, "
            "recombination or plasma magnetic field"
        ),
    }
    (args.out / "configuration.json").write_text(json.dumps(configuration, indent=2, allow_nan=False) + "\n")
    history: list[dict[str, object]] = []
    start = time.perf_counter()
    stop_reason = "complete"
    try:
        simulation.electron_window(plan.startup_steps)
        schedule = gun_schedule(args)
        for cycle in range(1, args.cycles + 1):
            if schedule[cycle] != simulation.gun_on:
                simulation.gun_on = schedule[cycle]
                simulation.electron_window(plan.settle_steps)
            electron_charge = simulation.electron_window(plan.window_steps)
            potential, core_kinetic, core_weight = simulation.ion_cycle(electron_charge)
            record = simulation.record(cycle, electron_charge, potential, core_kinetic, core_weight, start)
            if cycle % args.save_every_cycles == 0 or cycle == args.cycles:
                record["snapshot"] = simulation.save(snapshots, cycle, electron_charge, potential)
            history.append(record)
            temporary = args.out / "history.tmp"
            temporary.write_text(json.dumps(history, indent=2, allow_nan=False) + "\n")
            temporary.replace(args.out / "history.json")
            print(json.dumps({key: value for key, value in record.items() if key != "electrons"},
                             allow_nan=False), flush=True)
    except PopulationLimit as error:
        stop_reason = str(error)
    (args.out / "DONE").write_text(stop_reason + "\n")
    return history


def main() -> None:
    run(parser().parse_args())


if __name__ == "__main__":
    main()
