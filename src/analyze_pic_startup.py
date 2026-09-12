"""Summarize one transient PIC campaign and plot its physical-time histories."""

import argparse
import json
from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
import numpy as np

from cusp_sim import E_CHARGE

plt.switch_backend("Agg")

Record = dict[str, float | int | list[int] | str]


def scalar(record: Record, name: str) -> float:
    return float(cast(float | int, record[name]))


def observed_dwell(record: Record, core: bool = False) -> float:
    injected_electrons = abs(scalar(record, "injected_charge_C")) / E_CHARGE
    if injected_electrons:
        key = "total_core_dwell_electron_s" if core else "total_dwell_electron_s"
        return scalar(record, key) / injected_electrons
    if not scalar(record, "injected_count"):
        return 0
    key = "total_core_dwell_particle_s" if core else "total_dwell_particle_s"
    return scalar(record, key) / scalar(record, "injected_count")


def summarize(name: str, history: list[Record]) -> dict[str, object]:
    final = history[-1]
    injected = scalar(final, "injected_count")
    injected_energy = scalar(final, "injected_kinetic_J")
    return {
        "case": name,
        "time_s": scalar(final, "time_s"),
        "step": int(scalar(final, "step")),
        "injected_particles": int(injected),
        "lost_particles": int(scalar(final, "lost_count")),
        "loss_fraction": scalar(final, "lost_count") / injected,
        "observed_dwell_s": observed_dwell(final),
        "observed_core_dwell_s": observed_dwell(final, core=True),
        "core_entry_events_per_injected_particle": scalar(final, "core_entry_count") / injected,
        "repeated_entry_particle_fraction": scalar(final, "repeated_entry_count") / injected,
        "core_electron_count": scalar(final, "core_electron_count"),
        "minimum_potential_V": scalar(final, "minimum_potential_V"),
        "field_energy_J": scalar(final, "field_energy_J"),
        "open_energy_balance_fraction": (
            scalar(final, "open_energy_balance_J") / injected_energy if injected_energy else 0
        ),
        "charge_balance_C": scalar(final, "charge_balance_C"),
        "deposition_error_C": scalar(final, "deposition_error_C"),
        "exit_counts_xlo_xhi_ylo_yhi_zlo_zhi": final[
            "exit_counts_xlo_xhi_ylo_yhi_zlo_zhi"
        ],
    }


def relative_change(coarse: dict[str, object], fine: dict[str, object], key: str) -> float:
    target = abs(float(cast(float | int, fine[key])))
    return abs(float(cast(float | int, coarse[key])) - float(cast(float | int, fine[key]))) / target


def plot_histories(histories: dict[str, list[Record]], output: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for name, history in histories.items():
        time_ns = [scalar(record, "time_s") * 1e9 for record in history]
        axes[0, 0].plot(time_ns, [scalar(record, "minimum_potential_V") for record in history], label=name)
        axes[0, 1].plot(time_ns, [observed_dwell(record) * 1e9 for record in history], label=name)
        axes[1, 0].plot(time_ns, [observed_dwell(record, core=True) * 1e9 for record in history], label=name)
        axes[1, 1].plot(
            time_ns,
            [scalar(record, "repeated_entry_count") / scalar(record, "injected_count")
             if scalar(record, "injected_count") else 0 for record in history],
            label=name,
        )
    for axis, title, ylabel in (
        (axes[0, 0], "Grounded-box potential", "Minimum potential (V)"),
        (axes[0, 1], "Charge-weighted observed residence", "Mean observed dwell (ns)"),
        (axes[1, 0], "Charge-weighted observed core residence", "Mean observed core dwell (ns)"),
        (axes[1, 1], "Repeated core entries", "Repeated-particle fraction"),
    ):
        axis.set(title=title, xlabel="Physical time (ns)", ylabel=ylabel)
        axis.grid(alpha=0.25)
    axes[0, 0].legend(fontsize=8)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def field_summary(case: Path) -> dict[str, object]:
    snapshot = max((case / "snapshots").glob("*.npz"))
    with np.load(snapshot, allow_pickle=False) as values:
        potential = values["potential_V"]
        lower, upper = values["lower_m"], values["upper_m"]
        center = tuple(size // 2 for size in potential.shape)
        minimum = np.unravel_index(potential.argmin(), potential.shape)
        axes = [
            np.linspace(lower[axis], upper[axis], potential.shape[axis])
            for axis in range(3)
        ]
        return {
            "center_potential_V": float(potential[center]),
            "minimum_potential_position_m": [
                float(axes[axis][minimum[axis]]) for axis in range(3)
            ],
        }


def plot_fields(run: Path, output: Path) -> None:
    names = ("pic_1A", "pic_1A_dt")
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for row, name in enumerate(names):
        snapshot = max((run / name / "snapshots").glob("*.npz"))
        with np.load(snapshot, allow_pickle=False) as values:
            potential, charge = values["potential_V"], values["charge_C"]
            lower, upper = values["lower_m"], values["upper_m"]
        coordinates = [
            np.linspace(lower[axis], upper[axis], potential.shape[axis])
            for axis in range(3)
        ]
        cell_volume = np.prod(
            [(upper[axis] - lower[axis]) / (potential.shape[axis] - 1) for axis in range(3)],
        )
        center_y = potential.shape[1] // 2
        potential_image = axes[row, 0].pcolormesh(
            coordinates[2], coordinates[0], potential[:, center_y, :],
            cmap="viridis", shading="auto",
        )
        charge_image = axes[row, 1].pcolormesh(
            coordinates[2], coordinates[0], charge[:, center_y, :] / cell_volume,
            cmap="magma_r", shading="auto",
        )
        figure.colorbar(potential_image, ax=axes[row, 0], label="Potential (V)")
        figure.colorbar(charge_image, ax=axes[row, 1], label="Nodal charge / cell volume (C/m³)")
        axes[row, 0].set_title(f"{name}: central potential")
        axes[row, 1].set_title(f"{name}: central deposited charge")
        for axis in axes[row]:
            axis.set(xlabel="z (m)", ylabel="x (m)", aspect="equal")
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    histories = {
        path.name: cast(list[Record], json.loads((path / "history.json").read_text()))
        for path in sorted(args.run.glob("pic_*"))
        if (path / "history.json").exists()
    }
    if not histories:
        raise ValueError("No transient PIC histories found")
    summaries = {name: summarize(name, history) for name, history in histories.items()}
    report = {
        "cases": list(summaries.values()),
        "final_fields": {
            name: field_summary(args.run / name) for name in ("pic_1A", "pic_1A_dt")
        },
        "preliminary_1A_timestep_relative_changes": {
            key: relative_change(summaries["pic_1A"], summaries["pic_1A_dt"], key)
            for key in (
                "minimum_potential_V", "field_energy_J", "observed_dwell_s",
                "observed_core_dwell_s", "core_entry_events_per_injected_particle",
                "repeated_entry_particle_fraction", "core_electron_count",
            )
        },
        "limitations": [
            "Observed dwell is right-censored by the 30 ns startup window.",
            "The half-step case changes packet cadence and source sampling.",
            "The 50 micrometre source is unresolved on the 33-cubed mesh.",
            "A grounded-box startup is not a converged virtual-cathode or device prediction.",
        ],
    }
    (args.out / "analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    plot_histories(histories, args.out / "evolution.png")
    plot_fields(args.run, args.out / "fields.png")


if __name__ == "__main__":
    main()
