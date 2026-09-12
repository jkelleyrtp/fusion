"""Stationary trajectory–Poisson iteration; not a transient PIC stability calculation."""

import argparse
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from cusp_sim import (
    E_CHARGE,
    M_E,
    QM,
    TorchPusher,
    gun_beam_basis,
    ring_field_on_grid,
    sample_gun_beam,
)
from electrostatic import (
    EPSILON_0,
    ElectrostaticMesh,
    clip_segment,
    sphere_segment_fraction,
)

MagneticField = Callable[[torch.Tensor], torch.Tensor]


@dataclass
class PacketResult:
    charge: torch.Tensor
    dwell: torch.Tensor
    core_dwell: torch.Tensor
    entries: torch.Tensor
    escaped: torch.Tensor
    relative_energy_error: torch.Tensor
    final_kinetic_energy: torch.Tensor


def thermal_source(origin: list[float], direction: list[float], energy_ev: float,
                   temperature_ev: float, sigma: float, count: int,
                   device: torch.device, seed: int) -> tuple[torch.Tensor, torch.Tensor]:
    if (not math.isfinite(energy_ev) or not math.isfinite(temperature_ev)
            or energy_ev <= 0 or temperature_ev < 0 or count < 1):
        raise ValueError("Positive acceleration energy/count and nonnegative temperature required")
    torch.manual_seed(seed)
    properties = {"device": device, "dtype": torch.float64}  # legacy untyped sampler dict
    speed = math.sqrt(2 * energy_ev * E_CHARGE / M_E)
    positions, velocity, unit = sample_gun_beam(origin, direction, speed, count, 0, 0, 0, properties)
    positions[:, :2] += sigma * torch.randn(count, 2, device=device, dtype=torch.float64)
    if temperature_ev == 0:
        return positions, velocity
    e1, e2 = gun_beam_basis(unit)
    thermal_speed = math.sqrt(temperature_ev * E_CHARGE / M_E)
    parallel = torch.sqrt(speed * speed - 2 * thermal_speed ** 2
                          * torch.log1p(-torch.rand(count, device=device, dtype=torch.float64)))
    velocity = parallel[:, None] * torch.as_tensor(unit, device=device, dtype=torch.float64)
    velocity += thermal_speed * (
        torch.randn(count, device=device, dtype=torch.float64)[:, None]
        * torch.as_tensor(e1, device=device, dtype=torch.float64)
        + torch.randn(count, device=device, dtype=torch.float64)[:, None]
        * torch.as_tensor(e2, device=device, dtype=torch.float64))
    return positions, velocity


def trace_packet(mesh: ElectrostaticMesh, initial_pos: torch.Tensor, initial_vel: torch.Tensor,
                 potential: torch.Tensor, magnetic_field: MagneticField, current_a: float,
                 dt: float, duration: float, core_radius: float,
                 max_steps: int = 20000) -> PacketResult:
    if current_a < 0 or dt <= 0 or duration <= 0 or core_radius <= 0:
        raise ValueError("Invalid current, time or core radius")
    steps = math.ceil(duration / dt)
    if steps > max_steps:
        raise ValueError(f"Orbit needs {steps} steps, above explicit limit {max_steps}")
    count = len(initial_pos)
    if count == 0:
        raise ValueError("Empty injection packet")
    mesh.stencil(initial_pos)
    pos, vel = initial_pos.clone(), initial_vel.clone()
    ids = torch.arange(count, device=pos.device)
    dwell = pos.new_zeros(count)
    core_dwell = pos.new_zeros(count)
    entries = torch.zeros(count, device=pos.device, dtype=torch.int64)
    escaped = torch.zeros(count, device=pos.device, dtype=torch.bool)
    error = pos.new_zeros(count)
    charge = pos.new_zeros(mesh.shape)
    initial_ke = 0.5 * M_E * initial_vel.square().sum(dim=1)
    final_ke = initial_ke.clone()
    initial_h = initial_ke - E_CHARGE * mesh.gather(potential, initial_pos)[0]
    for step in range(steps):
        h = min(dt, duration - step * dt)
        for half in range(2):
            end, fraction, hit = clip_segment(pos, pos + 0.5 * h * vel, mesh)
            elapsed = 0.5 * h * fraction
            charge += mesh.deposit(0.5 * (pos + end), -current_a / count * elapsed)
            dwell[ids] += elapsed
            inside, entered = sphere_segment_fraction(pos, end, core_radius)
            core_dwell[ids] += elapsed * inside
            entries[ids] += entered.long()
            if hit.any():
                escaped[ids[hit]] = True
                final_ke[ids[hit]] = 0.5 * M_E * vel[hit].square().sum(dim=1)
                energy = final_ke[ids[hit]] - E_CHARGE * mesh.gather(potential, end[hit])[0]
                error[ids[hit]] = (energy - initial_h[ids[hit]]).abs() / initial_ke[ids[hit]]
            keep = ~hit
            pos, vel, ids = end[keep], vel[keep], ids[keep]
            if len(ids) == 0:
                break
            if half == 0:
                electric = mesh.gather(potential, pos)[1]
                vminus = vel + 0.5 * h * QM * electric
                rotation = 0.5 * h * QM * magnetic_field(pos)
                s = 2 * rotation / (1 + rotation.square().sum(dim=1, keepdim=True))
                prime = vminus + torch.linalg.cross(vminus, rotation)
                vel = vminus + torch.linalg.cross(prime, s) + 0.5 * h * QM * electric
        if len(ids) == 0:
            break
    if len(ids):
        final_ke[ids] = 0.5 * M_E * vel.square().sum(dim=1)
        energy = final_ke[ids] - E_CHARGE * mesh.gather(potential, pos)[0]
        error[ids] = (energy - initial_h[ids]).abs() / initial_ke[ids]
    return PacketResult(charge, dwell, core_dwell, entries, escaped, error, final_ke)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--device", default="cpu")
    result.add_argument("--nodes", type=int, default=33)
    result.add_argument("--particles", type=int, default=1024)
    result.add_argument("--iterations", type=int, default=6)
    result.add_argument("--relaxation", type=float, default=0.25)
    result.add_argument("--current-a", type=float, default=1e-5)
    result.add_argument("--coil-current", type=float, default=1000)
    result.add_argument("--radius", type=float, default=0.05)
    result.add_argument("--energy-ev", type=float, default=5)
    result.add_argument("--temperature-ev", type=float, default=0.2)
    result.add_argument("--aim-deg", type=float, default=30)
    result.add_argument("--source-sigma", type=float, default=5e-5)
    result.add_argument("--duration", type=float, default=1e-7)
    result.add_argument("--dt", type=float, default=1e-10)
    result.add_argument("--time-refinement", type=float, default=1)
    result.add_argument("--max-steps", type=int, default=20000)
    result.add_argument("--seed", type=int, default=1234)
    result.add_argument("--source-revision", default="unversioned")
    return result


def main() -> None:
    args = parser().parse_args()
    for value in vars(args).values():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Configuration numbers must be finite")
    if not 0 < args.relaxation <= 1 or args.iterations < 1 or args.radius <= 0:
        raise ValueError("Invalid relaxation, iterations or radius")
    if not 0 <= args.aim_deg < 90:
        raise ValueError("Aim must point into the box from below")
    if args.time_refinement < 1:
        raise ValueError("Time refinement must be at least one")
    device = torch.device(args.device)
    a = args.radius
    lower = torch.tensor([-0.6 * a, -0.6 * a, -1.3 * a], device=device, dtype=torch.float64)
    mesh = ElectrostaticMesh(lower, -lower, (args.nodes,) * 3)
    r = torch.linspace(0, math.sqrt(2) * 0.6 * a, 256, device=device, dtype=torch.float64)
    z = torch.linspace(-1.3 * a, 1.3 * a, 512, device=device, dtype=torch.float64)
    br, bz = ring_field_on_grid(r, z, a, [-0.5 * a, 0.5 * a],
                                [args.coil_current, -args.coil_current], 720, device)
    pusher = TorchPusher(br, bz, 0, float(r[1]), float(z[0]), float(z[1] - z[0]), QM)
    angle = math.radians(args.aim_deg)
    pos, vel = thermal_source([0, 0.008 * a, -1.3 * a], [0, -math.sin(angle), math.cos(angle)],
                              args.energy_ev, args.temperature_ev, args.source_sigma,
                              args.particles, device, args.seed)
    bmax = float(torch.sqrt(br * br + bz * bz).max())
    source_b = pusher.field(pos)
    source_b_norm = source_b.norm(dim=1)
    pitch = torch.rad2deg(torch.acos(
        ((source_b * vel).sum(dim=1) / (source_b_norm * vel.norm(dim=1)).clamp_min(1e-300)).clamp(-1, 1)))
    gyro_dt = 2 * math.pi / (80 * abs(QM) * bmax) if bmax else math.inf
    potential = pos.new_zeros(mesh.shape)
    relaxed_charge = torch.zeros_like(potential)
    args.out.mkdir(parents=True, exist_ok=False)
    configuration = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    configuration.update({
        "model": "stationary trajectory-Poisson, grounded 3D box, fixed vacuum B",
        "box_lower_m": lower.tolist(), "box_upper_m": (-lower).tolist(),
        "macroparticle_rate_per_s": args.current_a / (E_CHARGE * args.particles),
        "source": "flux-weighted half-Maxwellian accelerated along aim; finite Gaussian source",
        "source_mean_energy_ev": args.energy_ev + 2 * args.temperature_ev,
        "source_position_m": [0, 0.008 * a, -1.3 * a],
        "source_aim": [0, -math.sin(angle), math.cos(angle)],
        "source_sigma_in_cells": [args.source_sigma / float(mesh.h[0]),
                                  args.source_sigma / float(mesh.h[1]), 0],
        "source_mean_local_B_angle_deg": float(pitch.mean()) if bmax else None,
        "field_grid_rz": [256, 512], "table_max_B_T": bmax,
        "injected_kinetic_power_W": args.current_a * float(
            (0.5 * M_E / E_CHARGE * vel.square().sum(dim=1)).mean()),
    })
    (args.out / "config.json").write_text(json.dumps(configuration, indent=2) + "\n")
    history = []
    for iteration in range(args.iterations):
        vmax = math.sqrt(float(vel.square().sum(dim=1).max())
                         + 2 * abs(QM) * float(potential.max() - potential.min()))
        omega = math.sqrt(abs(QM) * float(relaxed_charge.abs().max()) / (float(mesh.volume) * EPSILON_0))
        dt = min(args.dt, gyro_dt, 0.2 * float(mesh.h.min()) / vmax,
                 0.1 / omega if omega else math.inf) / args.time_refinement
        orbit_potential = potential.clone()
        packet = trace_packet(mesh, pos, vel, orbit_potential, pusher.field, args.current_a,
                              dt, args.duration, 0.3 * a, args.max_steps)
        candidate = mesh.potential(packet.charge)
        mismatch = float((candidate - orbit_potential).abs().max() / candidate.abs().max().clamp_min(1e-30))
        relaxed_charge = (1 - args.relaxation) * relaxed_charge + args.relaxation * packet.charge
        potential = mesh.potential(relaxed_charge)
        deposited = float(packet.charge.sum())
        expected = -args.current_a * float(packet.dwell.mean())
        boundary_charge = deposited - float(packet.charge[1:-1, 1:-1, 1:-1].sum())
        peak_density = float(packet.charge.abs().max() / mesh.volume)
        debye_proxy = (math.sqrt(EPSILON_0 * args.temperature_ev / peak_density)
                       if peak_density and args.temperature_ev > 0 else None)
        record = {
            "iteration": iteration, "dt_s": dt, "fixed_point_relative_change": mismatch,
            "orbit_potential_min_V": float(orbit_potential.min()),
            "deposited_potential_min_V": float(candidate.min()),
            "relaxed_potential_min_V": float(potential.min()),
            "core_centre_potential_V": float(mesh.gather(candidate, pos.new_zeros((1, 3)))[0][0]),
            "mean_dwell_s": float(packet.dwell.mean()),
            "mean_core_dwell_s": float(packet.core_dwell.mean()),
            "core_inventory_charge_C": -args.current_a * float(packet.core_dwell.mean()),
            "mean_core_entries": float(packet.entries.double().mean()),
            "fraction_with_repeated_core_entries": float((packet.entries >= 2).double().mean()),
            "censored_fraction": float((~packet.escaped).double().mean()),
            "deposited_charge_C": deposited, "expected_charge_C": expected,
            "charge_conservation_error_C": deposited - expected,
            "shape_charge_on_boundary_nodes_C": boundary_charge,
            "poisson_relative_residual": float(mesh.residual(candidate, packet.charge)),
            "peak_electron_density_m3": peak_density / E_CHARGE,
            "source_temperature_debye_proxy_m": debye_proxy,
            "max_cell_over_debye_proxy": float(mesh.h.max()) / debye_proxy if debye_proxy else None,
            "gyro_angle_bound_rad": abs(QM) * bmax * dt,
            "field_energy_J": float(mesh.field_energy(candidate)),
            "orbit_energy_error_max_rel_initial_ke": float(packet.relative_energy_error.max()),
            "injected_current_A": args.current_a,
            "escaped_current_estimate_A": args.current_a * float(packet.escaped.double().mean()),
            "censored_current_A": args.current_a * float((~packet.escaped).double().mean()),
            "escaped_kinetic_power_W": args.current_a / (E_CHARGE * args.particles)
            * float(packet.final_kinetic_energy[packet.escaped].sum()),
        }
        history.append(record)
        (args.out / "history.json").write_text(json.dumps(history, indent=2) + "\n")
        np.savez_compressed(
            args.out / "state.npz", orbit_potential_V=orbit_potential.cpu().numpy(),
            deposited_potential_V=candidate.cpu().numpy(), relaxed_potential_V=potential.cpu().numpy(),
            deposited_charge_C=packet.charge.cpu().numpy(), relaxed_charge_C=relaxed_charge.cpu().numpy(),
            dwell_s=packet.dwell.cpu().numpy(), core_dwell_s=packet.core_dwell.cpu().numpy(),
            core_entries=packet.entries.cpu().numpy(), escaped=packet.escaped.cpu().numpy(),
            lower_m=mesh.lower.cpu().numpy(), upper_m=mesh.upper.cpu().numpy(),
        )
        print(json.dumps(record), flush=True)
    (args.out / "STATUS").write_text(
        "Iterations completed. Stationary candidate only; requires cutoff/grid/timestep/particle convergence.\n")


if __name__ == "__main__":
    main()
