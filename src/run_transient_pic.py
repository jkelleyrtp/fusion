"""Run bounded FP64 external-gun electrostatic PIC."""

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch

from cusp_sim import E_CHARGE, QM, TorchPusher, ring_field_on_grid
from electrostatic import ElectrostaticMesh
from pic_cuda import CUDAKernels
from pic_kernels import ReferenceKernels
from steady_space_charge import thermal_source
from transient_pic import PIC, MagneticField


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--device", default="cpu")
    result.add_argument("--kernels", choices=("reference", "cuda"), default="reference")
    result.add_argument("--nodes", type=int, default=17)
    result.add_argument("--inject-per-step", type=int, default=8)
    result.add_argument("--inject-every", type=int, default=1)
    result.add_argument("--current-a", type=float, default=1e-8)
    result.add_argument("--coil-current", type=float, default=1000)
    result.add_argument("--radius", type=float, default=0.5)
    result.add_argument("--energy-ev", type=float, default=5000)
    result.add_argument("--temperature-ev", type=float, default=0.2)
    result.add_argument("--aim-deg", type=float, default=30)
    result.add_argument("--source-sigma", type=float, default=5e-5)
    result.add_argument("--divergence-deg", type=float, default=10)
    result.add_argument("--dt", type=float, default=1e-12)
    result.add_argument("--duration", type=float, default=1e-10)
    result.add_argument("--max-steps", type=int, default=10000)
    result.add_argument("--max-live-particles", type=int, default=100000)
    result.add_argument("--save-every", type=int, default=10)
    result.add_argument("--max-snapshots", type=int, default=128)
    result.add_argument("--track", type=int, default=64)
    result.add_argument("--seed", type=int, default=1234)
    result.add_argument("--source-revision", default="unversioned")
    return result


def validate(args: argparse.Namespace) -> int:
    for value in vars(args).values():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Configuration numbers must be finite")
    if args.dt <= 0 or args.duration <= 0 or args.radius <= 0:
        raise ValueError("Positive timestep, duration and radius required")
    if args.energy_ev <= 0 or args.temperature_ev < 0 or args.current_a < 0:
        raise ValueError("Invalid source energy, temperature or current")
    if args.source_sigma < 0 or not 0 <= args.divergence_deg < 90:
        raise ValueError("Invalid source sigma or divergence")
    if not 0 <= args.aim_deg < 90:
        raise ValueError("Aim must point into the box")
    if args.nodes < 3 or args.inject_per_step < 1 or args.inject_every < 1 or args.max_live_particles < 1:
        raise ValueError("Invalid mesh size or particle limits")
    if args.save_every < 1 or args.max_snapshots < 2 or args.max_steps < 1:
        raise ValueError("Invalid output or step limits")
    if not 0 <= args.track <= 256 or args.seed < 0:
        raise ValueError("Invalid tracking count or seed")
    ratio = args.duration / args.dt
    if not math.isfinite(ratio):
        raise ValueError("Duration exceeds max-steps")
    steps = max(1, math.ceil(math.nextafter(ratio, -math.inf)))
    if steps > args.max_steps:
        raise ValueError("Duration exceeds max-steps")
    snapshots = 1 + steps // args.save_every + int(steps % args.save_every != 0)
    if snapshots > args.max_snapshots:
        raise ValueError("Output exceeds max-snapshots; increase save-every")
    return steps


def save_snapshot(
    simulation: PIC, directory: Path, step: int, h: float,
) -> dict[str, float | int | list[int] | str]:
    charge, potential = simulation.fields()
    p = simulation.particles
    arrays = {
        "ids": p.ids, "birth_s": p.birth, "position_m": p.position,
        "velocity_m_s": p.velocity, "electron_count": p.weight,
        "dwell_s": p.dwell, "core_dwell_s": p.core_dwell,
        "core_entries": p.entries, "charge_C": charge, "potential_V": potential,
        "lower_m": simulation.mesh.lower, "upper_m": simulation.mesh.upper,
        "tracked_position_m": simulation.tracked_position,
        "tracked_birth_s": simulation.tracked_birth,
        "tracked_exit_time_s": simulation.tracked_exit_time,
        "tracked_exit_face": simulation.tracked_exit_face,
    }
    name = f"step-{step:08d}.npz"
    path = directory / name
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(
            stream, allow_pickle=False, time_s=simulation.time, step=step, dt_s=h,
            **{key: value.cpu().numpy() for key, value in arrays.items()},
        )
    temporary.replace(path)
    record: dict[str, float | int | list[int] | str] = {
        **simulation.diagnostics(charge, potential),
        "step": step, "dt_s": h, "snapshot": f"snapshots/{name}",
    }
    if not all(math.isfinite(value) for value in record.values()
               if isinstance(value, (int, float))):
        raise ValueError("Nonfinite PIC diagnostics")
    return record


def source_geometry(args: argparse.Namespace) -> tuple[list[float], list[float]]:
    angle = math.radians(args.aim_deg)
    return [0.0, 0.008 * args.radius, -1.3 * args.radius], [0.0, -math.sin(angle), math.cos(angle)]


def create_simulation(args: argparse.Namespace) -> tuple[PIC, dict[str, object]]:
    device = torch.device(args.device)
    a = args.radius
    lower = torch.tensor(
        [-0.6 * a, -0.6 * a, -1.3 * a], device=device, dtype=torch.float64,
    )
    mesh = ElectrostaticMesh(lower, -lower, (args.nodes,) * 3)
    r = torch.linspace(
        0, math.sqrt(2) * 0.6 * a, 256, device=device, dtype=torch.float64,
    )
    z = torch.linspace(
        -1.3 * a, 1.3 * a, 512, device=device, dtype=torch.float64,
    )
    br, bz = ring_field_on_grid(
        r, z, a, [-0.5 * a, 0.5 * a],
        [args.coil_current, -args.coil_current], 720, device,
    )
    bmax = float(torch.sqrt(br.square() + bz.square()).max())
    if not math.isfinite(bmax):
        raise ValueError("Nonfinite magnetic field table")
    if abs(QM) * bmax * min(args.dt, args.duration) > 2 * math.pi / 80:
        raise ValueError("Timestep requires at least 80 steps per gyration")
    pusher = TorchPusher(
        br, bz, 0, float(r[1]), float(z[0]), float(z[1] - z[0]), QM,
    )
    kernels: ReferenceKernels
    magnetic_field: MagneticField
    if args.kernels == "cuda":
        cuda = CUDAKernels(mesh)
        kernels, magnetic_field = cuda, cuda.magnetic_field(pusher)
    else:
        kernels = ReferenceKernels(mesh)
        magnetic_field = pusher.field
    simulation = PIC(
        mesh, magnetic_field, 0.25 * a, args.max_live_particles, args.track, kernels=kernels,
    )
    origin, direction = source_geometry(args)
    source_field = pusher.field(lower.new_tensor([origin]))[0]
    source_norm = float(source_field.norm())
    pitch = math.degrees(math.acos(max(-1, min(1, float(
        source_field.dot(lower.new_tensor(direction)),
    ) / source_norm)))) if source_norm else None
    configuration: dict[str, object] = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in vars(args).items()
    }
    configuration.update({
        "model": "transient-electrostatic-pic-v1",
        "precision": "float64",
        "time_semantics": "physical seconds; synchronized end-of-step states",
        "source_interpretation": "post-extraction grounded-wall inlet, discrete charge packets",
        "source_pulse_interval_s": args.dt * args.inject_every,
        "source_origin_m": origin, "source_direction": direction,
        "source_nominal_pitch_deg": pitch,
        "source_B_T": source_field.cpu().tolist(),
        "magnetic_table_max_T": bmax,
        "magnetic_table_shape_z_r": [512, 256],
        "core_radius_m": simulation.core_radius,
        "boundary": "grounded rectangular box; absorbing particle walls",
        "charge_deposition": "instantaneous CIC; no residence weighting",
        "energy_balance": "K + U + lost kinetic - injected kinetic; not a power budget",
        "tracking": "first stable particle IDs; includes terminal wall positions",
        "validation_scope": "numerical model; physical source/mesh convergence pending",
    })
    return simulation, configuration


def inject_packet(simulation: PIC, args: argparse.Namespace, step: int) -> None:
    if step % args.inject_every:
        return
    if len(simulation.particles.ids) + args.inject_per_step > args.max_live_particles:
        raise ValueError("Injection exceeds max-live-particles")
    origin, direction = source_geometry(args)
    position, velocity = thermal_source(
        origin, direction, args.energy_ev, args.temperature_ev,
        args.source_sigma, args.inject_per_step, torch.device("cpu"),
        args.seed + step // args.inject_every, args.divergence_deg,
    )
    if (velocity[:, 2] <= 0).any():
        raise ValueError("Sampled inlet velocity points backwards")
    pulse_duration = min(args.dt * args.inject_every, args.duration - step * args.dt)
    weight = position.new_full(
        (args.inject_per_step,), args.current_a * pulse_duration / (E_CHARGE * args.inject_per_step),
    )
    packet = torch.cat((position, velocity, weight[:, None]), dim=1).to(simulation.mesh.lower.device)
    simulation.inject(packet[:, :3], packet[:, 3:6], packet[:, 6])


def run(args: argparse.Namespace) -> list[dict[str, float | int | list[int] | str]]:
    steps = validate(args)
    simulation, configuration = create_simulation(args)
    args.out.mkdir(parents=True, exist_ok=False)
    snapshots = args.out / "snapshots"
    snapshots.mkdir()
    (args.out / "configuration.json").write_text(
        json.dumps(configuration, indent=2, allow_nan=False) + "\n",
    )
    history: list[dict[str, float | int | list[int] | str]] = []

    def publish(step: int, h: float) -> None:
        record = save_snapshot(simulation, snapshots, step, h)
        record["wall_s"] = time.perf_counter() - start
        history.append(record)
        temporary = args.out / "history.tmp"
        temporary.write_text(json.dumps(history, indent=2, allow_nan=False) + "\n")
        temporary.replace(args.out / "history.json")
        print(json.dumps(record, allow_nan=False), flush=True)

    start = time.perf_counter()
    publish(0, 0)
    for step in range(steps):
        h = args.duration - step * args.dt if step + 1 == steps else args.dt
        inject_packet(simulation, args, step)
        simulation.advance(h)
        simulation.time = args.duration if step + 1 == steps else (step + 1) * args.dt
        if (step + 1) % args.save_every == 0 or step + 1 == steps:
            publish(step + 1, h)
    (args.out / "DONE").write_text("complete\n")
    return history


def main() -> None:
    run(parser().parse_args())


if __name__ == "__main__":
    main()
