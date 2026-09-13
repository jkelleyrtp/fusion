"""FP64 electron PIC with instantaneous charge and synchronized particle states."""

import math
from collections.abc import Callable
from dataclasses import dataclass

import torch

from cusp_sim import E_CHARGE, M_E, QM
from electrostatic import (
    EPSILON_0,
    Conductors,
    ElectrostaticMesh,
)
from pic_kernels import ReferenceKernels

MagneticField = Callable[[torch.Tensor], torch.Tensor]


@dataclass
class Particles:
    ids: torch.Tensor
    birth: torch.Tensor
    position: torch.Tensor
    velocity: torch.Tensor
    weight: torch.Tensor
    dwell: torch.Tensor
    core_dwell: torch.Tensor
    entries: torch.Tensor

    def select(self, keep: torch.Tensor) -> "Particles":
        if keep.dtype == torch.bool:
            keep = keep.nonzero().squeeze(1)
        return Particles(
            self.ids[keep], self.birth[keep], self.position[keep],
            self.velocity[keep], self.weight[keep], self.dwell[keep],
            self.core_dwell[keep], self.entries[keep],
        )

    def split(self, count: int) -> tuple["Particles", "Particles"]:
        fields = (
            self.ids, self.birth, self.position, self.velocity, self.weight,
            self.dwell, self.core_dwell, self.entries,
        )
        return (
            Particles(*(field[:count] for field in fields)),
            Particles(*(field[count:] for field in fields)),
        )


LOST_TOTALS = (
    "charge", "kinetic", "dwell", "core_dwell", "electron_dwell",
    "electron_core_dwell", "entries", "repeated_entries",
)


class PIC:
    def __init__(
        self, mesh: ElectrostaticMesh, magnetic_field: MagneticField,
        core_radius: float, max_live: int, track: int = 0,
        *, kernels: ReferenceKernels | None = None, conductors: Conductors | None = None,
        track_after: float = 0.0,
    ) -> None:
        if not math.isfinite(core_radius) or core_radius <= 0 or max_live < 1:
            raise ValueError("Positive core radius and live-particle limit required")
        if not 0 <= track <= 256:
            raise ValueError("Track count must be between 0 and 256")
        if not math.isfinite(track_after) or track_after < 0:
            raise ValueError("Tracking start time must be finite and nonnegative")
        self.mesh = mesh
        self.kernels = ReferenceKernels(mesh) if kernels is None else kernels
        if self.kernels.mesh is not mesh:
            raise ValueError("Particle operators must use the PIC mesh")
        if conductors is not None and conductors.mesh is not mesh:
            raise ValueError("Conductors must use the PIC mesh")
        self.conductors = conductors
        self.magnetic_field = magnetic_field
        self.core_radius = core_radius
        self.max_live = max_live
        empty = mesh.lower.new_empty(0)
        self.particles = Particles(
            empty.long(), empty.clone(), empty.reshape(0, 3),
            empty.reshape(0, 3), empty.clone(), empty.clone(),
            empty.clone(), empty.long(),
        )
        self.time = 0.0
        self.injected_count = 0
        self.lost_count = 0
        self.injected_charge = 0.0
        self.injected_kinetic = 0.0
        self._lost_totals = empty.new_zeros(len(LOST_TOTALS))
        shapes = 0 if conductors is None else len(conductors.shapes)
        self.exit_counts = torch.zeros(6 + shapes, device=empty.device, dtype=torch.int64)
        self.conductor_charge = empty.new_zeros(shapes)
        self.background_charge: torch.Tensor | None = None
        self.tracked_position = empty.new_full((track, 3), math.nan)
        self.tracked_birth = empty.new_full((track,), math.nan)
        self.tracked_exit_time = empty.new_full((track,), math.nan)
        self.tracked_exit_face = torch.full(
            (track,), -1, device=empty.device, dtype=torch.int64,
        )
        self._tracked_live = 0
        self.track_after = track_after
        self.tracked_first_id: int | None = None

    def lost_totals(self) -> dict[str, float]:
        """Charge, kinetic energy, dwell and entry sums over lost particles."""
        return dict(zip(LOST_TOTALS, self._lost_totals.tolist(), strict=True))

    @property
    def lost_charge(self) -> float:
        return self.lost_totals()["charge"]

    @property
    def lost_kinetic(self) -> float:
        return self.lost_totals()["kinetic"]

    @property
    def lost_dwell(self) -> float:
        return self.lost_totals()["dwell"]

    @property
    def lost_core_dwell(self) -> float:
        return self.lost_totals()["core_dwell"]

    def _raise_first(
        self, checks: list[tuple[torch.Tensor, str]], *extra: torch.Tensor,
    ) -> list[float]:
        tensors = [flag for flag, _ in checks] + list(extra)
        if not tensors:
            return []
        flags = torch.stack(tensors).tolist()
        for flag, (_, message) in zip(flags, checks, strict=False):
            if flag:
                raise ValueError(message)
        return flags[len(checks):]

    def inject(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: torch.Tensor,
    ) -> None:
        self._check_append(position, velocity, weight)
        charge, kinetic = self._raise_first([
            (~torch.isfinite(tensor).all(), "Particle arrays must be finite")
            for tensor in (position, velocity, weight)
        ] + [
            ((weight < 0).any(), "Represented electron counts must be nonnegative"),
            (((position < self.mesh.lower) | (position > self.mesh.upper)).any(),
             "Deposit/gather requires positions inside the box"),
        ], -E_CHARGE * weight.sum(), (0.5 * M_E * weight * velocity.square().sum(dim=1)).sum())
        self._append(position, velocity, weight, charge, kinetic)

    def append_validated_packet(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: float,
        kinetic_J: float,
    ) -> None:
        """Append equal-weight particles already checked finite and inside the box."""
        if not math.isfinite(weight) or weight < 0 or not math.isfinite(kinetic_J):
            raise ValueError("Represented electron counts must be finite and nonnegative")
        count = len(position)
        weights = torch.full((count,), weight, dtype=torch.float64, device=position.device)
        self._check_append(position, velocity, weights)
        self._append(position, velocity, weights, -E_CHARGE * weight * count, kinetic_J)

    def _check_append(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: torch.Tensor,
    ) -> None:
        count = len(position)
        if len(self.particles.ids) + count > self.max_live:
            raise ValueError("Injection exceeds max-live-particles")
        if position.shape != (count, 3) or velocity.shape != (count, 3):
            raise ValueError("Particle positions and velocities must be N by 3")
        if weight.shape != (count,):
            raise ValueError("Particle weights must have length N")
        for tensor in (position, velocity, weight):
            if tensor.dtype != torch.float64 or tensor.device != self.mesh.lower.device:
                raise ValueError("Particle arrays must be FP64 on the mesh device")

    def _append(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: torch.Tensor,
        charge: float, kinetic: float,
    ) -> None:
        count = len(position)
        ids = torch.arange(
            self.injected_count, self.injected_count + count, device=position.device,
        )
        birth = weight.new_full((count,), self.time)
        zeros = torch.zeros_like(weight)
        p = self.particles
        self.particles = Particles(
            torch.cat((p.ids, ids)), torch.cat((p.birth, birth)),
            torch.cat((p.position, position)), torch.cat((p.velocity, velocity)),
            torch.cat((p.weight, weight)), torch.cat((p.dwell, zeros)),
            torch.cat((p.core_dwell, zeros)), torch.cat((p.entries, zeros.long())),
        )
        start = self.injected_count
        if self.tracked_first_id is None and self.time >= self.track_after:
            self.tracked_first_id = start
        local = 0 if self.tracked_first_id is None else start - self.tracked_first_id
        tracked = 0 if self.tracked_first_id is None else max(
            0, min(count, len(self.tracked_birth) - local),
        )
        self.injected_count += count
        self.injected_charge += charge
        self.injected_kinetic += kinetic
        self.tracked_birth[local:local + tracked] = self.time
        self.tracked_position[local:local + tracked] = position[:tracked]
        self._tracked_live += tracked

    def fields(self) -> tuple[torch.Tensor, torch.Tensor]:
        """Deposited electron charge, and the potential of that charge plus any background charge."""
        p = self.particles
        charge = self.kernels.deposit(p.position, -E_CHARGE * p.weight)
        total = charge if self.background_charge is None else charge + self.background_charge
        if self.conductors is None:
            return charge, self.kernels.potential(total)
        potential, self.conductor_charge = self.conductors.potential(total)
        return charge, potential

    def kinetic_energy(self) -> torch.Tensor:
        p = self.particles
        return (0.5 * M_E * p.weight * p.velocity.square().sum(dim=1)).sum()

    def _drift(
        self, h: float, start_time: float, checks: list[tuple[torch.Tensor, str]],
    ) -> None:
        p = self.particles
        if len(p.ids) == 0:
            self._raise_first(checks)
            return
        end, fraction, hit, inside, entered = self.kernels.drift(
            p.position, p.velocity, h, self.core_radius,
        )
        wall = hit
        if self.conductors is not None:
            absorbed = self.conductors.absorbing(end)
            hit = wall | (absorbed >= 0)
        live = self._tracked_live
        first = self.tracked_first_id or 0
        older = ((p.ids < first).sum(),) if live and first else ()
        lost_count, *offset = self._raise_first(checks, hit.sum(), *older)
        elapsed = h * fraction
        p.dwell += elapsed
        p.core_dwell += elapsed * inside
        p.entries += entered.long()
        lower = int(offset[0]) if offset else 0
        self.tracked_position[p.ids[lower:lower + live] - first] = end[lower:lower + live]
        p.position = end
        if not lost_count:
            return
        survivors = len(p.ids) - int(lost_count)
        order = torch.argsort(hit.to(torch.int8), stable=True)
        kept, lost = p.select(order).split(survivors)
        self._lost_totals += torch.stack((
            -E_CHARGE * lost.weight.sum(),
            (0.5 * M_E * lost.weight * lost.velocity.square().sum(dim=1)).sum(),
            lost.dwell.sum(),
            lost.core_dwell.sum(),
            (lost.weight * lost.dwell).sum(),
            (lost.weight * lost.core_dwell).sum(),
            lost.entries.sum().to(torch.float64),
            (lost.entries >= 2).sum().to(torch.float64),
        ))
        self.lost_count += len(lost.ids)
        distances = torch.stack((
            (lost.position - self.mesh.lower).abs() / self.mesh.h,
            (lost.position - self.mesh.upper).abs() / self.mesh.h,
        ), dim=2).flatten(start_dim=1)
        faces = distances.argmin(dim=1)
        if self.conductors is not None:
            removed = order[survivors:]
            faces = torch.where(wall[removed], faces, 6 + absorbed[removed])
        self.exit_counts.index_add_(0, faces, torch.ones_like(faces))
        if live:
            before = int((lost.ids < first).sum()) if first else 0
            tracked = int((lost.ids < first + len(self.tracked_birth)).sum()) - before
            self._tracked_live = live - tracked
            tracked_ids = lost.ids[before:before + tracked] - first
            self.tracked_exit_time[tracked_ids] = (
                start_time + elapsed[order[survivors + before:survivors + before + tracked]]
            )
            self.tracked_exit_face[tracked_ids] = faces[before:before + tracked]
        self.particles = kept

    def _speed_checks(self, h: float) -> list[tuple[torch.Tensor, str]]:
        if len(self.particles.ids) == 0:
            return []
        speed = self.particles.velocity.norm(dim=1).max()
        return [
            (~torch.isfinite(speed), "Nonfinite particle velocity"),
            (speed * h > 0.2 * self.mesh.h.min(), "Timestep exceeds the 0.2-cell drift bound"),
        ]

    def advance(self, h: float) -> None:
        if not math.isfinite(h) or h <= 0:
            raise ValueError("Timestep must be finite and positive")
        self._drift(h / 2, self.time, self._speed_checks(h))
        charge, potential = self.fields()
        omega_p = torch.sqrt(
            charge.abs().max() * E_CHARGE / (self.mesh.volume * EPSILON_0 * M_E),
        )
        checks = [(omega_p * h > 0.1, "Timestep exceeds omega_p * dt <= 0.1")]
        p = self.particles
        if len(p.ids):
            electric = self.kernels.gather(potential, p.position)
            magnetic = self.magnetic_field(p.position)
            if (magnetic.shape != p.position.shape or magnetic.dtype != torch.float64
                    or magnetic.device != p.position.device):
                raise ValueError("Magnetic field must be finite FP64, N by 3 on the mesh device")
            checks += [
                (~torch.isfinite(magnetic).all(),
                 "Magnetic field must be finite FP64, N by 3 on the mesh device"),
                (abs(QM) * magnetic.norm(dim=1).max() * h > 2 * math.pi / 80,
                 "Timestep requires at least 80 steps per gyration"),
            ]
            p.velocity = self.kernels.boris(p.velocity, electric, magnetic, h)
        self._drift(h / 2, self.time + h / 2, checks + self._speed_checks(h))
        self.time += h

    def diagnostics(
        self, charge: torch.Tensor, potential: torch.Tensor,
    ) -> dict[str, float | int | list[int] | list[float]]:
        p = self.particles
        alive_charge = float(-E_CHARGE * p.weight.sum())
        kinetic = float(self.kinetic_energy())
        field = float(self.mesh.field_energy(potential))
        in_core = p.position.square().sum(dim=1) < self.core_radius ** 2
        lost = self.lost_totals()
        exits = self.exit_counts.tolist()
        conductors: dict[str, list[int] | list[float]] = {} if self.conductors is None else {
            "conductor_exit_counts": exits[6:],
            "conductor_charge_C": self.conductor_charge.tolist(),
        }
        return {
            "time_s": self.time,
            "injected_count": self.injected_count,
            "lost_count": self.lost_count,
            "alive_count": len(p.ids),
            "injected_charge_C": self.injected_charge,
            "lost_charge_C": lost["charge"],
            "alive_charge_C": alive_charge,
            "charge_balance_C": self.injected_charge - lost["charge"] - alive_charge,
            "deposition_error_C": float(charge.sum()) - alive_charge,
            "boundary_shape_charge_C": float(
                charge.sum() - charge[1:-1, 1:-1, 1:-1].sum(),
            ),
            "kinetic_J": kinetic,
            "field_energy_J": field,
            "injected_kinetic_J": self.injected_kinetic,
            "lost_kinetic_J": lost["kinetic"],
            "open_energy_balance_J": (
                kinetic + field + lost["kinetic"] - self.injected_kinetic
            ),
            "total_dwell_particle_s": lost["dwell"] + float(p.dwell.sum()),
            "total_core_dwell_particle_s": (
                lost["core_dwell"] + float(p.core_dwell.sum())
            ),
            "total_dwell_electron_s": (
                lost["electron_dwell"] + float((p.weight * p.dwell).sum())
            ),
            "total_core_dwell_electron_s": (
                lost["electron_core_dwell"] + float((p.weight * p.core_dwell).sum())
            ),
            "core_entry_count": int(lost["entries"]) + int(p.entries.sum()),
            "repeated_entry_count": (
                int(lost["repeated_entries"]) + int((p.entries >= 2).sum())
            ),
            "core_particle_count": int(in_core.sum()),
            "core_electron_count": float(p.weight[in_core].sum()),
            "minimum_potential_V": float(potential.min()),
            "exit_counts_xlo_xhi_ylo_yhi_zlo_zhi": exits[:6],
            **conductors,
        }
