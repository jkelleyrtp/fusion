"""Summarize the long-window transient PIC sensitivity campaign from scalar diagnostics."""

import argparse
import json
import math
from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
import numpy as np

from analyze_pic_startup import Record, field_summary, scalar
from cusp_sim import E_CHARGE

plt.switch_backend("Agg")

REFERENCE_CASE = "pic_1A_n129"
MESH_CASES = ("pic_1A_n33", "pic_1A_n49", "pic_1A_n65", "pic_1A_n97", "pic_1A_n129")
VARIANT_CASES = ("pic_1A_n65_particles", "pic_1A_n65_dt", "pic_1A_n65_s2345")
WINDOW_METRICS = (
    "minimum_potential_V", "field_energy_J", "alive_electrons", "core_electron_count",
    "residence_s", "core_residence_s",
)


def load(case: Path) -> list[Record]:
    configuration = json.loads((case / "configuration.json").read_text())
    records = [
        cast(Record, json.loads(line))
        for line in (case / "diagnostics.jsonl").read_text().splitlines()
    ]
    if (not (case / "DONE").is_file() or not records
            or not math.isclose(scalar(records[-1], "time_s"), configuration["duration"], rel_tol=1e-12)):
        raise ValueError(f"Incomplete case: {case.name}")
    for record in records:
        assert scalar(record, "alive_count") + scalar(record, "lost_count") == scalar(record, "injected_count")
        assert all(math.isfinite(value) for value in record.values() if isinstance(value, (int, float)))
    return records


def derived(record: Record) -> dict[str, float]:
    rate = abs(scalar(record, "injected_charge_C")) / E_CHARGE / scalar(record, "time_s")
    alive = abs(scalar(record, "alive_charge_C")) / E_CHARGE
    return {
        "minimum_potential_V": scalar(record, "minimum_potential_V"),
        "field_energy_J": scalar(record, "field_energy_J"),
        "alive_electrons": alive,
        "core_electron_count": scalar(record, "core_electron_count"),
        "residence_s": alive / rate,
        "core_residence_s": scalar(record, "core_electron_count") / rate,
    }


def summarize(name: str, records: list[Record], window_start_s: float) -> dict[str, object]:
    window = [record for record in records if scalar(record, "time_s") >= window_start_s]
    times = np.array([scalar(record, "time_s") for record in window])
    values = {key: np.array([derived(record)[key] for record in window]) for key in WINDOW_METRICS}
    final = records[-1]
    injected = scalar(final, "injected_count")
    exits = cast(list[int], final["exit_counts_xlo_xhi_ylo_yhi_zlo_zhi"])
    return {
        "case": name,
        "window_s": [float(times[0]), float(times[-1])],
        "window_samples": len(window),
        "mean": {key: float(value.mean()) for key, value in values.items()},
        "relative_std": {key: float(value.std() / abs(value.mean())) for key, value in values.items()},
        "relative_drift_per_100ns": {
            key: float(np.polyfit(times, value, 1)[0] * 1e-7 / abs(value.mean()))
            for key, value in values.items()
        },
        "final_loss_fraction": scalar(final, "lost_count") / injected,
        "final_core_entries_per_injected_particle": scalar(final, "core_entry_count") / injected,
        "final_repeated_entry_particle_fraction": scalar(final, "repeated_entry_count") / injected,
        "final_exit_fractions_xlo_xhi_ylo_yhi_zlo_zhi": [count / sum(exits) for count in exits],
        "max_abs_charge_balance_C": max(abs(scalar(record, "charge_balance_C")) for record in records),
        "max_abs_deposition_error_C": max(abs(scalar(record, "deposition_error_C")) for record in records),
        "wall_s_per_step": scalar(final, "wall_s") / scalar(final, "step"),
    }


def plot_histories(histories: dict[str, list[Record]], output: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(12, 7.5), constrained_layout=True)
    panels = (
        ("minimum_potential_V", 1, "Grounded-box minimum potential", "V"),
        ("alive_electrons", 1, "Live electrons", "electrons"),
        ("core_residence_s", 1e9, "Core electrons / injection rate", "ns"),
        ("field_energy_J", 1e3, "Field energy", "mJ"),
    )
    for name, records in histories.items():
        time_ns = [scalar(record, "time_s") * 1e9 for record in records]
        style = "-" if name in MESH_CASES else "--"
        for axis, (key, scale, _, _) in zip(axes.flat, panels, strict=True):
            axis.plot(time_ns, [derived(record)[key] * scale for record in records], style, label=name, lw=1.2)
    for axis, (_, _, title, unit) in zip(axes.flat, panels, strict=True):
        axis.set(title=title, xlabel="Physical time (ns)", ylabel=unit)
        axis.grid(alpha=0.25)
    axes[0, 0].legend(fontsize=7)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def plot_fields(run: Path, output: Path, names: tuple[str, ...]) -> None:
    figure, axes = plt.subplots(2, len(names), figsize=(4.2 * len(names), 7), constrained_layout=True)
    for column, name in enumerate(names):
        snapshot = max((run / name / "snapshots").glob("*.npz"))
        with np.load(snapshot, allow_pickle=False) as values:
            potential, charge = values["potential_V"], values["charge_C"]
            lower, upper = values["lower_m"], values["upper_m"]
        coordinates = [np.linspace(lower[axis], upper[axis], potential.shape[axis]) for axis in range(3)]
        cell_volume = np.prod([(upper[axis] - lower[axis]) / (potential.shape[axis] - 1) for axis in range(3)])
        center_y = potential.shape[1] // 2
        images = (
            axes[0, column].pcolormesh(coordinates[2], coordinates[0], potential[:, center_y, :],
                                       cmap="viridis", shading="auto"),
            axes[1, column].pcolormesh(coordinates[2], coordinates[0], -charge[:, center_y, :] / cell_volume / E_CHARGE,
                                       cmap="magma", shading="auto"),
        )
        figure.colorbar(images[0], ax=axes[0, column], label="Potential (V)")
        figure.colorbar(images[1], ax=axes[1, column], label="Electron density (m⁻³)")
        axes[0, column].set_title(f"{name}: potential, y = 0")
        axes[1, column].set_title(f"{name}: deposited density, y = 0")
        for axis in axes[:, column]:
            axis.set(xlabel="z (m)", ylabel="x (m)", aspect="equal")
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--window-start", type=float, default=2e-7)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    histories = {name: load(args.run / name) for name in (*MESH_CASES, *VARIANT_CASES)}
    summaries = {name: summarize(name, records, args.window_start) for name, records in histories.items()}

    def relative(name: str, reference: str) -> dict[str, float]:
        current = cast(dict[str, float], summaries[name]["mean"])
        target = cast(dict[str, float], summaries[reference]["mean"])
        return {key: (current[key] - target[key]) / abs(target[key]) for key in WINDOW_METRICS}

    report = {
        "scope": "Long-window sensitivity of the 1 A external-gun CUDA PIC model; not a convergence certificate.",
        "cases": list(summaries.values()),
        "final_fields": {name: field_summary(args.run / name) for name in histories},
        "mesh_relative_to_129": {name: relative(name, REFERENCE_CASE) for name in MESH_CASES[:-1]},
        "variants_relative_to_n65": {name: relative(name, "pic_1A_n65") for name in VARIANT_CASES},
        "limitations": [
            "Residence is live charge divided by injection rate; it equals mean dwell only in a stationary state.",
            "The 50 micrometre source is unresolved on every mesh in this study.",
            "Grounded outer box, imposed two-coil magnetic field, electrons only.",
            "One seed per mesh; seed spread is from a single alternative seed at 65 cubed.",
        ],
    }
    (args.out / "analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    plot_histories(histories, args.out / "evolution.png")
    plot_fields(args.run, args.out / "fields.png", ("pic_1A_n33", "pic_1A_n65", "pic_1A_n129"))


if __name__ == "__main__":
    main()
