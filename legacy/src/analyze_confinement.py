"""Plasma-regime diagnostics for completed six-coil coupled PIC cases.

For each case's final snapshot: electron residence in beam transits, loss channels,
node-resolved densities, Debye length against the mesh spacing, plasma beta against
the vacuum coil field, and the Brillouin and beta = 1 density limits.
"""

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch

from cusp_sim import E_CHARGE, M_E
from run_transient_pic import coil_casings, six_coil_table

EPS0 = 8.8541878128e-12
MU0 = 4e-7 * math.pi
AMU = 1.66053906660e-27
C_LIGHT = 2.99792458e8


def load_case(case: Path) -> tuple[dict, dict, dict[str, np.ndarray]] | None:
    done = case / "DONE"
    snapshots = sorted((case / "snapshots").glob("cycle-*.npz"))
    if not done.is_file() or done.read_text().strip() != "complete" or not snapshots:
        return None
    configuration = json.loads((case / "configuration.json").read_text())
    if configuration.get("mesh_shape") is None or len(configuration.get("coils", [])) != 6:
        return None
    history = json.loads((case / "history.json").read_text())
    snapshot = np.load(snapshots[-1])
    return configuration, history[-1], {key: snapshot[key] for key in snapshot.files}


def node_sum(position: np.ndarray, value: np.ndarray, lower: np.ndarray, spacing: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    index = np.rint((position - lower) / spacing).astype(np.int64)
    index = np.clip(index, 0, np.array(shape) - 1)
    flat = np.ravel_multi_index(index.T, shape)
    return np.bincount(flat, weights=value, minlength=math.prod(shape)).reshape(shape)


def vacuum_field(configuration: dict, lower: np.ndarray, upper: np.ndarray, shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray, float]:
    args = argparse.Namespace(**{**configuration, "coils": 6})
    low, up = torch.tensor(lower), torch.tensor(upper)
    _, field, _ = six_coil_table(args, torch.device("cpu"), low, up)
    axes = [torch.linspace(float(lower[axis]), float(upper[axis]), shape[axis], dtype=torch.float64) for axis in range(3)]
    points = torch.stack(torch.meshgrid(*axes, indexing="ij"), dim=-1).reshape(-1, 3)
    windings = torch.zeros(len(points), dtype=torch.bool)
    for casing in coil_casings(args):
        windings |= casing.contains(points)
    magnitude = field(points.clone()).norm(dim=1)
    along = torch.linspace(0, configuration["coil_offset"] * configuration["radius"], 256, dtype=torch.float64)
    axis_points = torch.stack((torch.zeros_like(along), torch.zeros_like(along), along), dim=1)
    throat = float(field(axis_points).norm(dim=1).max())
    return magnitude.reshape(shape).numpy(), windings.reshape(shape).numpy(), throat


def analyze(case: Path) -> dict[str, object] | None:
    loaded = load_case(case)
    if loaded is None:
        return None
    configuration, last, snapshot = loaded
    lower, upper = snapshot["lower_m"], snapshot["upper_m"]
    shape = snapshot["potential_V"].shape
    spacing = (upper - lower) / (np.array(shape) - 1)
    volume = float(np.prod(spacing))

    electrons = last["electrons"]
    current = float(configuration["current_a"])
    energy = float(configuration["energy_ev"])
    speed = math.sqrt(2 * energy * E_CHARGE / M_E)
    transit = 2 * float(np.linalg.norm(configuration.get("source_origins_m", [configuration["source_origin_m"]])[0])) / speed
    residence = abs(float(last["window_mean_electron_charge_C"])) / current
    exits = electrons["conductor_exit_counts"]
    names = configuration["conductor_names"]
    lost = float(electrons["lost_count"])
    casing_loss = sum(count for name, count in zip(names, exits, strict=True) if name.startswith("casing"))
    barrel_loss = sum(count for name, count in zip(names, exits, strict=True) if name.startswith("gun_barrel"))

    electron_weight = snapshot["electron_count"]
    electron_energy = 0.5 * M_E * electron_weight * np.square(snapshot["electron_velocity_m_s"]).sum(axis=1)
    density_e = node_sum(snapshot["electron_position_m"], electron_weight, lower, spacing, shape) / volume
    energy_e = node_sum(snapshot["electron_position_m"], electron_energy, lower, spacing, shape) / volume
    ion_mass = np.where(snapshot["ion_species"] == 0, configuration["ion_mass_amu"], configuration.get("atomic_ion_mass_amu", configuration["ion_mass_amu"] / 2)) * AMU
    ion_energy = 0.5 * ion_mass * snapshot["ion_count"] * np.square(snapshot["ion_velocity_m_s"]).sum(axis=1)
    energy_i = node_sum(snapshot["ion_position_m"], ion_energy, lower, spacing, shape) / volume
    density_i = node_sum(snapshot["ion_position_m"], snapshot["ion_count"], lower, spacing, shape) / volume

    magnitude, windings, throat_B = vacuum_field(configuration, lower, upper, shape)
    outside = ~windings
    pressure = (2 / 3) * (energy_e + energy_i)
    beta = np.where(outside, pressure / np.maximum(np.square(magnitude) / (2 * MU0), 1e-30), 0.0)
    grid = np.meshgrid(*[np.linspace(lower[axis], upper[axis], shape[axis]) for axis in range(3)], indexing="ij")
    radius = np.sqrt(sum(np.square(axis) for axis in grid))
    interior = outside & (radius < 0.9 * configuration["radius"])
    core = radius < configuration["core_radius_m"]

    dense = density_e >= np.percentile(density_e[interior], 99.9)
    mean_energy = np.divide(energy_e, density_e, out=np.zeros_like(energy_e), where=density_e > 0)
    debye = np.sqrt(EPS0 * (2 / 3) * mean_energy[dense] / (density_e[dense] * E_CHARGE ** 2))
    beta_one = interior & (beta >= 1)
    core_pressure = float(pressure[core].mean())
    throat_pressure = throat_B ** 2 / (2 * MU0)
    beta_density = throat_pressure / ((2 / 3) * energy * E_CHARGE)
    brillouin = EPS0 * throat_B ** 2 / (2 * M_E)
    return {
        "case": case.name,
        "guns": configuration.get("guns", 1),
        "current_A": current,
        "energy_eV": energy,
        "coil_current_At": configuration["coil_current"],
        "gas_Pa": configuration["gas_pa"],
        "nodes": configuration["nodes"],
        "cycles": configuration["cycles"],
        "spacing_m": spacing.tolist(),
        "origin_potential_V": last["potential_origin_V"],
        "minimum_potential_V": last["potential_min_V"],
        "neutralization": last["neutralization_fraction"],
        "core_neutralization": last["core_neutralization_fraction"],
        "electron_residence_s": residence,
        "transit_s": transit,
        "transits": residence / transit,
        "repeat_core_entries_per_injected": electrons["repeated_entry_count"] / electrons["injected_count"],
        "loss_fraction_casings": casing_loss / lost,
        "loss_fraction_gun_barrels": barrel_loss / lost,
        "loss_fraction_box": 1 - (casing_loss + barrel_loss) / lost,
        "core_electron_density_m3": float(density_e[core].mean()),
        "core_ion_density_m3": float(density_i[core].mean()),
        "peak_electron_density_m3": float(density_e[dense].mean()),
        "dense_debye_m": float(np.median(debye)),
        "dense_spacing_over_debye": float(spacing.max() / np.median(debye)),
        "core_pressure_Pa": core_pressure,
        "throat_B_T": throat_B,
        "throat_magnetic_pressure_Pa": throat_pressure,
        "throat_beta": core_pressure / throat_pressure,
        "max_interior_beta_outside_core": float(beta[interior & ~core].max()),
        "beta_one_equivalent_radius_m": float((3 * beta_one.sum() * volume / (4 * math.pi)) ** (1 / 3)),
        "density_for_throat_beta_one_m3": beta_density,
        "brillouin_density_m3": brillouin,
        "brillouin_beta_limit": (2 / 3) * energy * E_CHARGE / (M_E * C_LIGHT ** 2),
    }


def plot(rows: list[dict[str, object]], output: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(12, 9))
    colors = {1: "tab:gray", 2: "tab:olive", 3: "tab:green", 6: "tab:blue"}

    def column(key: str) -> np.ndarray:
        return np.array([row[key] for row in rows], dtype=float)

    guns, energy, nodes, current = column("guns"), column("energy_eV"), column("nodes"), column("current_A")
    reference = rows[0]
    for count, color in colors.items():
        for high, marker in ((False, "o"), (True, "^")):
            for mesh, size in ((49, 15), (65, 30), (81, 50)):
                chosen = (guns == count) & ((energy > 10000) == high) & (nodes == mesh)
                for axis, key in ((axes[0, 0], "transits"), (axes[0, 1], "core_electron_density_m3"),
                                  (axes[1, 0], "dense_spacing_over_debye"), (axes[1, 1], "throat_beta")):
                    axis.scatter(current[chosen], column(key)[chosen], c=color, marker=marker, s=size)
    axes[0, 1].axhline(column("brillouin_density_m3")[0], color="tab:red", ls="--", label=f"Brillouin limit at throat B ({reference['throat_B_T']:.3f} T)")
    axes[0, 1].axhline(column("density_for_throat_beta_one_m3")[0], color="black", ls=":", label="beta = 1 at throat, 10 keV")
    axes[1, 0].axhline(1, color="tab:red", ls="--", label="h = Debye length")
    axes[1, 1].axhline(1, color="black", ls=":", label="beta = 1")
    labels = [
        ("Electron residence / beam transit", axes[0, 0]),
        ("Core electron density (m$^{-3}$)", axes[0, 1]),
        ("Largest cell / Debye length in densest 0.1% of nodes", axes[1, 0]),
        ("Core plasma pressure / throat magnetic pressure", axes[1, 1]),
    ]
    for label, axis in labels:
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlabel("Total gun current (A)")
        axis.set_ylabel(label)
        axis.grid(alpha=0.3, which="both")
    for axis in (axes[0, 1], axes[1, 0], axes[1, 1]):
        axis.legend(loc="best", fontsize=8)
    for count, color in colors.items():
        axes[0, 0].scatter([], [], c=color, label=f"{count} gun{'s' if count > 1 else ''}")
    axes[0, 0].scatter([], [], c="white", edgecolors="black", marker="o", label="≤10 keV")
    axes[0, 0].scatter([], [], c="white", edgecolors="black", marker="^", label="20 keV")
    axes[0, 0].legend(loc="best", fontsize=8)
    figure.suptitle("Six-coil PIC regime: confinement, density, resolution and beta (final snapshots)")
    figure.tight_layout()
    figure.savefig(output, dpi=130)
    plt.close(figure)


def plot_repeats(cases: list[Path], current: float, output: Path) -> None:
    """Centre potential histories of single-gun cases at one current and 1e-3 Pa, labeled by numerical settings."""
    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for case in cases:
        configuration = json.loads((case / "configuration.json").read_text())
        if configuration.get("guns", 1) != 1 or configuration["current_a"] != current or configuration["gas_pa"] != 1e-3:
            continue
        history = json.loads((case / "history.json").read_text())
        time = np.array([record["time_s"] for record in history]) * 1e6
        label = (f"{case.name}: {configuration['cycle_duration'] * 1e6:g} µs cycles, {configuration['electron_window'] * 1e9:g} ns window, "
                 f"ion dt {configuration['ion_dt']:g}, {configuration['ions_per_cycle']} ions, seed {configuration['seed']}, n{configuration['nodes']}"
                 + ("" if (case / "DONE").is_file() else " (running)"))
        axes[0].plot(time, [record["potential_origin_V"] / 1e3 for record in history], label=label)
        axes[1].plot(time, [record["neutralization_fraction"] for record in history])
    axes[0].set_ylabel("Centre potential (kV)")
    axes[1].set_ylabel("Neutralization fraction")
    for axis in axes:
        axis.set_xlabel("Time (µs)")
        axis.grid(alpha=0.3)
    figure.legend(loc="lower center", fontsize=7, ncol=2)
    figure.suptitle(f"One gun, {current:g} A, 10 keV, H2 at 1e-3 Pa: same physics, different numerical settings")
    figure.tight_layout(rect=(0, 0.22, 1, 1))
    figure.savefig(output, dpi=130)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("runs", type=Path, nargs="+", help="Result directories containing case subdirectories")
    parser.add_argument("--repeat-current", type=float, default=10.0, help="Single-gun current whose repeated cases are overlaid")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    cases = [case for run in args.runs for case in sorted(path for path in run.iterdir() if (path / "history.json").is_file())]
    plot_repeats(cases, args.repeat_current, args.out / "repeats.png")
    for run in args.runs:
        for case in sorted(path for path in run.iterdir() if path.is_dir()):
            row = analyze(case)
            if row is not None:
                row["run"] = run.parent.name
                rows.append(row)
                print(json.dumps({key: row[key] for key in ("run", "case", "transits", "loss_fraction_casings", "core_electron_density_m3", "dense_spacing_over_debye", "throat_beta")}))
    (args.out / "confinement.json").write_text(json.dumps(rows, indent=1))
    plot(rows, args.out / "confinement.png")


if __name__ == "__main__":
    main()
