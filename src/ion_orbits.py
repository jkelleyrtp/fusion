"""Test hydrogen ions in the time-averaged potential and imposed field of a finished PIC run.

Ions carry no charge into the field: this measures the well an ion sees, not an ion-modified well.
"""

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from cusp_sim import E_CHARGE
from electrostatic import Cylinder, ElectrostaticMesh, Shape
from run_transient_pic import coil_casings, gun_barrel, magnetic_table, mesh_shape
from run_transient_pic import parser as pic_parser

M_P = 1.67262192369e-27
QM_ION = E_CHARGE / M_P
FACES = ("x_lower", "x_upper", "y_lower", "y_upper", "z_lower", "z_upper")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--run", type=Path, required=True, help="PIC case directory")
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--window-start", type=float, default=2e-7,
                        help="average snapshots at or after this time (s)")
    result.add_argument("--birth", choices=("density", "uniform"), default="density",
                        help="density: births weighted by time-averaged electron charge, a proxy for "
                             "electron-impact ionization of a uniform gas; uniform: births uniform in the box")
    result.add_argument("--ions", type=int, default=4096)
    result.add_argument("--temperature-ev", type=float, default=0.1)
    result.add_argument("--dt", type=float, default=1e-9)
    result.add_argument("--duration", type=float, default=2e-5)
    result.add_argument("--track", type=int, default=16)
    result.add_argument("--track-every", type=int, default=20)
    result.add_argument("--seed", type=int, default=1234)
    return result


def load_run(
    run: Path, window_start: float,
) -> tuple[argparse.Namespace, ElectrostaticMesh, torch.Tensor, torch.Tensor, list[float]]:
    """Case arguments, mesh, window-mean potential and |charge|, and snapshot times used."""
    configuration = json.loads((run / "configuration.json").read_text())
    args = pic_parser().parse_args(["--out", str(run)])
    for key in vars(args):
        if key in configuration and key != "out":
            setattr(args, key, configuration[key])
    potential, charge, times = None, None, []
    lower = upper = None
    for path in sorted((run / "snapshots").glob("step-*.npz")):
        with np.load(path, allow_pickle=False) as snapshot:
            if float(snapshot["time_s"]) < window_start:
                continue
            times.append(float(snapshot["time_s"]))
            potential = snapshot["potential_V"] if potential is None else potential + snapshot["potential_V"]
            charge = abs(snapshot["charge_C"]) if charge is None else charge + abs(snapshot["charge_C"])
            lower, upper = snapshot["lower_m"], snapshot["upper_m"]
    if len(times) < 2 or potential is None or charge is None or lower is None or upper is None:
        raise ValueError("Need at least two snapshots in the averaging window")
    mesh = ElectrostaticMesh(torch.from_numpy(lower), torch.from_numpy(upper), mesh_shape(args))
    if tuple(potential.shape) != mesh.shape:
        raise ValueError("Snapshot potential does not match the case mesh")
    return (args, mesh, torch.from_numpy(potential / len(times)),
            torch.from_numpy(charge / len(times)), times)


def absorbed(shapes: tuple[Shape, ...], points: torch.Tensor) -> torch.Tensor:
    result = torch.full((len(points),), -1, dtype=torch.long)
    for index in reversed(range(len(shapes))):
        result = torch.where(shapes[index].contains(points), index, result)
    return result


def births(
    options: argparse.Namespace, mesh: ElectrostaticMesh, charge: torch.Tensor,
    shapes: tuple[Shape, ...], generator: torch.Generator,
) -> tuple[torch.Tensor, torch.Tensor]:
    positions = mesh.lower.new_empty((0, 3))
    while len(positions) < options.ions:
        count = 2 * options.ions
        if options.birth == "density":
            nodes = torch.multinomial(charge.flatten(), count, replacement=True, generator=generator)
            index = torch.stack(torch.unravel_index(nodes, mesh.shape), dim=1).to(torch.float64)
            jitter = torch.rand((count, 3), generator=generator, dtype=torch.float64) - 0.5
            candidate = (mesh.lower + (index + jitter) * mesh.h).clamp(mesh.lower, mesh.upper)
        else:
            candidate = mesh.lower + torch.rand(
                (count, 3), generator=generator, dtype=torch.float64,
            ) * (mesh.upper - mesh.lower)
        inside = ((candidate > mesh.lower) & (candidate < mesh.upper)).all(dim=1)
        positions = torch.cat((positions, candidate[inside & (absorbed(shapes, candidate) < 0)]))
    thermal = math.sqrt(options.temperature_ev * E_CHARGE / M_P)
    velocity = thermal * torch.randn((options.ions, 3), generator=generator, dtype=torch.float64)
    return positions[:options.ions], velocity


def simulate(options: argparse.Namespace) -> dict[str, object]:
    args, mesh, potential, charge, times = load_run(options.run, options.window_start)
    pusher, bmax, _ = magnetic_table(args, torch.device("cpu"))
    shapes: tuple[Shape, ...] = ((gun_barrel(args),) if args.gun_radius else ()) + coil_casings(args)
    boundary_v = min([0.0] + [shape.voltage for shape in shapes])
    steps = round(options.duration / options.dt)
    if (options.ions < 1 or options.dt <= 0 or steps < 1 or options.track < 0
            or options.track > options.ions or options.track_every < 1):
        raise ValueError("Invalid ion run configuration")
    depth = float(potential.max() - potential.min())
    speed = math.sqrt(2 * E_CHARGE * depth / M_P) + 5 * math.sqrt(options.temperature_ev * E_CHARGE / M_P)
    if QM_ION * bmax * options.dt > 2 * math.pi / 80:
        raise ValueError("Timestep requires at least 80 steps per ion gyration")
    if speed * options.dt > 0.2 * float(mesh.h.min()):
        raise ValueError("Timestep exceeds the 0.2-cell ion drift bound")
    core_radius = 0.25 * args.radius
    generator = torch.Generator().manual_seed(options.seed)
    position, velocity = births(options, mesh, charge, shapes, generator)
    birth_position = position.clone()
    birth_phi, electric = mesh.gather(potential, position)
    birth_kinetic_ev = 0.5 * M_P * velocity.square().sum(dim=1) / E_CHARGE
    total_ev = birth_kinetic_ev + birth_phi
    count = options.ions
    exit_time = torch.full((count,), math.nan, dtype=torch.float64)
    exit_index = torch.full((count,), -1, dtype=torch.long)
    exit_kinetic = torch.full((count,), math.nan, dtype=torch.float64)
    core_entries = torch.zeros(count, dtype=torch.long)
    core_time = torch.zeros(count, dtype=torch.float64)
    core_kinetic = torch.zeros(count, dtype=torch.float64)
    max_kinetic = birth_kinetic_ev.clone()
    in_core = position.norm(dim=1) < core_radius
    alive = torch.arange(count)
    tracks = np.full((options.track, steps // options.track_every + 1, 3), np.nan)
    tracks[:, 0] = position[:options.track].numpy()
    survivors = [count]
    h = options.dt
    velocity = velocity + 0.5 * h * QM_ION * electric
    for step in range(1, steps + 1):
        if len(alive):
            _, electric = mesh.gather(potential, position)
            magnetic = pusher.field(position)
            half_electric = 0.5 * h * QM_ION * electric
            minus = velocity + half_electric
            t = 0.5 * h * QM_ION * magnetic
            s = 2 * t / (1 + t.square().sum(dim=1, keepdim=True))
            prime = minus + torch.cross(minus, t, dim=1)
            velocity = minus + torch.cross(prime, s, dim=1) + half_electric
            position = position + h * velocity
            kinetic_ev = 0.5 * M_P * velocity.square().sum(dim=1) / E_CHARGE
            ids = alive
            max_kinetic[ids] = torch.maximum(max_kinetic[ids], kinetic_ev)
            core = position.norm(dim=1) < core_radius
            core_entries[ids] += (core & ~in_core).long()
            core_time[ids] += h * core
            core_kinetic[ids] += h * core * kinetic_ev
            outside = ((position <= mesh.lower) | (position >= mesh.upper)).any(dim=1)
            conductor = absorbed(shapes, position)
            lost = outside | (conductor >= 0)
            if lost.any():
                distances = torch.stack((
                    (position - mesh.lower).abs() / mesh.h, (position - mesh.upper).abs() / mesh.h,
                ), dim=2).flatten(start_dim=1)
                index = torch.where(outside, distances.argmin(dim=1), 6 + conductor)
                exit_time[ids[lost]] = step * h
                exit_index[ids[lost]] = index[lost]
                exit_kinetic[ids[lost]] = kinetic_ev[lost]
                keep = ~lost
                alive, position, velocity, in_core = ids[keep], position[keep], velocity[keep], core[keep]
            else:
                in_core = core
            if step % options.track_every == 0:
                tracked = alive < options.track
                tracks[alive[tracked].numpy(), step // options.track_every] = position[tracked].numpy()
        survivors.append(len(alive))
    drift = position.new_empty(0)
    if len(alive):
        phi, _ = mesh.gather(potential, position)
        drift = 0.5 * M_P * velocity.square().sum(dim=1) / E_CHARGE + phi - total_ev[alive]
    options.out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(
        options.out / "ions.npz", allow_pickle=False,
        birth_position_m=birth_position.numpy(), exit_kinetic_eV=exit_kinetic.numpy(),
        birth_potential_V=birth_phi.numpy(), birth_kinetic_eV=birth_kinetic_ev.numpy(),
        total_energy_eV=total_ev.numpy(), exit_time_s=exit_time.numpy(), exit_index=exit_index.numpy(),
        core_entries=core_entries.numpy(), core_time_s=core_time.numpy(),
        max_kinetic_eV=max_kinetic.numpy(), tracks_m=tracks, survivors=np.array(survivors),
        potential_V=potential.numpy(), lower_m=mesh.lower.numpy(), upper_m=mesh.upper.numpy(),
    )
    names = list(FACES) + [
        "gun_barrel" if isinstance(shape, Cylinder) else f"casing_{'lower' if shape.center_z < 0 else 'upper'}"
        for shape in shapes
    ]
    lost_mask = exit_index >= 0
    entered = core_entries > 0
    origin_phi = float(mesh.gather(potential, mesh.lower.new_zeros((1, 3)))[0][0])
    summary: dict[str, object] = {
        "run": str(options.run), "birth": options.birth, "ions": count,
        "temperature_ev": options.temperature_ev, "dt_s": h, "duration_s": steps * h, "seed": options.seed,
        "window_snapshot_times_s": times, "core_radius_m": core_radius,
        "potential_min_V": float(potential.min()), "potential_origin_V": origin_phi,
        "boundary_min_V": boundary_v, "magnetic_table_max_T": bmax,
        "energetically_confined_fraction": float((total_ev < boundary_v).double().mean()),
        "lost_fraction": float(lost_mask.double().mean()),
        "exit_fractions": {
            name: float((exit_index == index).double().mean()) for index, name in enumerate(names)
        },
        "median_exit_time_s": float(exit_time[lost_mask].median()) if lost_mask.any() else None,
        "entered_core_fraction": float(entered.double().mean()),
        "mean_core_entries": float(core_entries.double().mean()),
        "mean_core_entries_entering": float(core_entries[entered].double().mean()) if entered.any() else None,
        "core_time_weighted_kinetic_eV": float(core_kinetic.sum() / core_time.sum()) if core_time.sum() else None,
        "max_kinetic_eV_percentiles": dict(zip(
            ("p10", "p50", "p90"), torch.quantile(max_kinetic, max_kinetic.new_tensor([0.1, 0.5, 0.9])).tolist(),
            strict=True,
        )),
        "birth_potential_V_percentiles": dict(zip(
            ("p10", "p50", "p90"), torch.quantile(birth_phi, birth_phi.new_tensor([0.1, 0.5, 0.9])).tolist(),
            strict=True,
        )),
        "surviving_max_energy_drift_eV": float(drift.abs().max()) if len(drift) else None,
        "validation_scope": (
            "test ions in a frozen, window-averaged electron potential; no ion space charge, "
            "collisions, charge exchange or field fluctuations"
        ),
    }
    (options.out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    plot(options, mesh, potential, tracks, survivors, max_kinetic, core_entries)
    return summary


def plot(
    options: argparse.Namespace, mesh: ElectrostaticMesh, potential: torch.Tensor, tracks: np.ndarray,
    survivors: list[int], max_kinetic: torch.Tensor, core_entries: torch.Tensor,
) -> None:
    lower, upper = mesh.lower.numpy(), mesh.upper.numpy()
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    image = axes[0].imshow(
        potential[:, mesh.shape[1] // 2, :].numpy(), origin="lower", aspect="equal",
        extent=(lower[2], upper[2], lower[0], upper[0]), cmap="viridis",
    )
    for track in tracks:
        axes[0].plot(track[:, 2], track[:, 0], lw=0.6, color="white", alpha=0.8)
    axes[0].set(xlabel="z (m)", ylabel="x (m)", title="Mean potential, y = 0, tracked ions (x-z)")
    figure.colorbar(image, ax=axes[0], label="Potential (V)")
    time_us = np.arange(len(survivors)) * options.dt * 1e6
    axes[1].plot(time_us, np.array(survivors) / survivors[0])
    axes[1].set(xlabel="Time (µs)", ylabel="Surviving fraction", ylim=(0, 1.02), title="Ion survival")
    axes[2].hist(max_kinetic.numpy() / 1e3, bins=60, weights=np.full(len(max_kinetic), 1 / len(max_kinetic)))
    axes[2].set(xlabel="Peak ion kinetic energy (keV)", ylabel="Fraction of ions",
                title=f"{options.birth} births; mean core entries {core_entries.double().mean():.1f}")
    figure.savefig(options.out / "ions.png", dpi=130)
    plt.close(figure)


def main() -> None:
    print(json.dumps(simulate(parser().parse_args()), indent=2))


if __name__ == "__main__":
    main()
