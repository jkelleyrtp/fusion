"""Summarize the long-window, grounded-box, gun-barrel, coil-casing and six-coil transient PIC campaigns."""

import argparse
import json
import math
from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

from analyze_pic_startup import Record, field_summary, scalar
from cusp_sim import E_CHARGE

plt.switch_backend("Agg")

REFERENCE_CASE = "pic_1A_n129"
MESH_CASES = ("pic_1A_n33", "pic_1A_n49", "pic_1A_n65", "pic_1A_n97", "pic_1A_n129")
VARIANT_CASES = ("pic_1A_n65_particles", "pic_1A_n65_dt", "pic_1A_n65_s2345")
DOMAIN_CASES = (
    "pic_1A_box", "pic_1A_box_w0525", "pic_1A_box_w045", "pic_1A_box_t195", "pic_1A_box_t26",
    "pic_1A_box_b1625", "pic_1A_box_b195", "pic_1A_box_b195_t26",
)
GUN_CASES = (
    "pic_1A_gun_wall", "pic_1A_gun_b1625", "pic_1A_gun_b195", "pic_1A_gun_b26",
    "pic_1A_gun_b195_r004", "pic_1A_gun_b195_r010", "pic_1A_gun_b195_s2345", "pic_1A_gun_b195_n97",
)
CASING_CASES = (
    "pic_1A_casing_r015", "pic_1A_casing_none", "pic_1A_casing_r015_w1275", "pic_1A_casing_r020",
    "pic_1A_casing_r015_p1kV", "pic_1A_casing_r015_m1kV", "pic_1A_casing_r015_s2345", "pic_1A_casing_r015_t195",
)
SIX_COIL_CASES = (
    "pic_1A_six_d120", "pic_1A_two_coil_c010", "pic_1A_six_d120_1mA", "pic_1A_six_d130",
    "pic_1A_six_d120_w1575", "pic_1A_six_d120_t195", "pic_1A_six_d120_p1kV", "pic_1A_six_d120_s2345",
)
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
        "relative_std": {
            key: float(value.std() / abs(value.mean())) if value.mean() else None
            for key, value in values.items()
        },
        "relative_drift_per_100ns": {
            key: float(np.polyfit(times, value, 1)[0] * 1e-7 / abs(value.mean())) if value.mean() else None
            for key, value in values.items()
        },
        "final_loss_fraction": scalar(final, "lost_count") / injected,
        "final_core_entries_per_injected_particle": scalar(final, "core_entry_count") / injected,
        "final_repeated_entry_particle_fraction": scalar(final, "repeated_entry_count") / injected,
        "final_exit_fractions_xlo_xhi_ylo_yhi_zlo_zhi": (
            [count / sum(exits) for count in exits] if sum(exits) else None
        ),
        "max_abs_charge_balance_C": max(abs(scalar(record, "charge_balance_C")) for record in records),
        "max_abs_deposition_error_C": max(abs(scalar(record, "deposition_error_C")) for record in records),
        "wall_s_per_step": scalar(final, "wall_s") / scalar(final, "step"),
    }


def core_field(case: Path, core_radius_m: float) -> dict[str, object]:
    """Final-snapshot potential at the origin node and its minimum inside the core sphere."""
    snapshot = max((case / "snapshots").glob("*.npz"))
    with np.load(snapshot, allow_pickle=False) as values:
        potential, lower, upper = values["potential_V"], values["lower_m"], values["upper_m"]
    axes = [np.linspace(lower[axis], upper[axis], potential.shape[axis]) for axis in range(3)]
    origin = tuple(int(np.abs(axis).argmin()) for axis in axes)
    x, y, z = np.meshgrid(*axes, indexing="ij")
    inside = x**2 + y**2 + z**2 <= core_radius_m**2
    minimum = np.unravel_index(np.where(inside, potential, np.inf).argmin(), potential.shape)
    minimum_all = np.unravel_index(potential.argmin(), potential.shape)
    return {
        "origin_node_m": [float(axes[axis][origin[axis]]) for axis in range(3)],
        "origin_potential_V": float(potential[origin]),
        "core_minimum_potential_V": float(potential[minimum]),
        "core_minimum_position_m": [float(axes[axis][minimum[axis]]) for axis in range(3)],
        "minimum_potential_V": float(potential[minimum_all]),
        "minimum_potential_position_m": [float(axes[axis][minimum_all[axis]]) for axis in range(3)],
        "box_lower_m": lower.tolist(), "box_upper_m": upper.tolist(),
        "mesh_shape": list(potential.shape),
    }


def plot_histories(histories: dict[str, list[Record]], output: Path, solid: tuple[str, ...]) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(12, 7.5), constrained_layout=True)
    panels = (
        ("minimum_potential_V", 1, "Grounded-box minimum potential", "V"),
        ("alive_electrons", 1, "Live electrons", "electrons"),
        ("core_residence_s", 1e9, "Core electrons / injection rate", "ns"),
        ("field_energy_J", 1e3, "Field energy", "mJ"),
    )
    for name, records in histories.items():
        time_ns = [scalar(record, "time_s") * 1e9 for record in records]
        style = "-" if name in solid else "--"
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
        density = np.maximum(-charge[:, center_y, :] / cell_volume / E_CHARGE, 0)
        images = (
            axes[0, column].pcolormesh(coordinates[2], coordinates[0], potential[:, center_y, :],
                                       cmap="viridis", shading="auto"),
            axes[1, column].pcolormesh(coordinates[2], coordinates[0], density, cmap="magma", shading="auto",
                                       norm=LogNorm(vmin=1e-4 * density.max(), vmax=density.max())),
        )
        figure.colorbar(images[0], ax=axes[0, column], label="Potential (V)")
        figure.colorbar(images[1], ax=axes[1, column], label="Electron density (m⁻³), log scale")
        axes[0, column].set_title(f"{name}\npotential, y = 0", fontsize=10)
        axes[1, column].set_title(f"{name}\ndeposited density, y = 0", fontsize=10)
        for axis in axes[:, column]:
            axis.set(xlabel="z (m)", ylabel="x (m)", aspect="equal")
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--window-start", type=float, default=2e-7)
    parser.add_argument("--study", choices=("window", "domain", "gun", "casing", "six-coil"), default="window")
    parser.add_argument("--domain-run", type=Path, help="grounded-box campaign to compare the gun study against")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    names = {"domain": DOMAIN_CASES, "gun": GUN_CASES, "casing": CASING_CASES, "six-coil": SIX_COIL_CASES}.get(
        args.study, (*MESH_CASES, *VARIANT_CASES),
    )
    histories = {name: load(args.run / name) for name in names}
    summaries = {name: summarize(name, records, args.window_start) for name, records in histories.items()}

    def relative(name: str, reference: str) -> dict[str, float | None]:
        current = cast(dict[str, float], summaries[name]["mean"])
        target = cast(dict[str, float], summaries[reference]["mean"])
        return {
            key: (current[key] - target[key]) / abs(target[key]) if target[key] else None
            for key in WINDOW_METRICS
        }

    if args.study in ("casing", "six-coil"):
        six = args.study == "six-coil"
        core_radius = 0.25 * json.loads((args.run / names[0] / "configuration.json").read_text())["radius"]
        conductors = {}
        for name, records in histories.items():
            configuration = json.loads((args.run / name / "configuration.json").read_text())
            final = records[-1]
            box_exits = sum(cast(list[int], final["exit_counts_xlo_xhi_ylo_yhi_zlo_zhi"]))
            shape_exits = cast(list[int], final["conductor_exit_counts"])
            total_exits = box_exits + sum(shape_exits)
            window = [record for record in records if scalar(record, "time_s") >= args.window_start]
            conductors[name] = {
                "box_lower_m": configuration["box_lower_m"], "box_upper_m": configuration["box_upper_m"],
                "mesh_shape": configuration["mesh_shape"], "seed": configuration["seed"],
                "coil_casings": configuration["coil_casings"], "conductor_setup_s": configuration["conductor_setup_s"],
                **({"coils": configuration["coils"], "coil_offset": configuration["coil_offset"],
                    "source_B_T": configuration["source_B_T"],
                    "source_nominal_pitch_deg": configuration["source_nominal_pitch_deg"]} if six else {}),
                "source_potential_V_window_mean": float(np.mean([scalar(r, "source_potential_V") for r in window])),
                "final_conductor_charge_C": dict(zip(
                    configuration["conductor_names"], cast(list[float], final["conductor_charge_C"]), strict=True,
                )),
                "final_exit_fractions": {
                    "outer_box": box_exits / total_exits,
                    **{
                        conductor: count / total_exits
                        for conductor, count in zip(configuration["conductor_names"], shape_exits, strict=True)
                    },
                },
            }
        casing_report: dict[str, object] = {
            "scope": (
                "Six-coil imposed cube field versus the two-coil cusp, grounded barrel and casings, 1 A external-gun CUDA PIC."
                if six else
                "Absorbing coil casings inside a wider grounded box, with the gun barrel, 1 A external-gun CUDA PIC."
            ),
            "cases": list(summaries.values()),
            "conductors": conductors,
            "final_fields": {name: core_field(args.run / name, core_radius) for name in names},
            "relative_to_six_d120" if six else "relative_to_r015": {name: relative(name, names[0]) for name in names[1:]},
            "limitations": [
                "Conductor absorption tests step endpoints only." if six else
                "Conductor absorption tests step endpoints only; no casing received an electron in any case.",
                "Casings are tori at the coil radius; the windings, supports and feedthroughs are not modelled.",
                "Imposed vacuum magnetic field without plasma currents; electrons only; one seed except the reference."
                if six else
                "Grounded outer box, imposed two-coil magnetic field, electrons only, one seed except r015.",
            ],
        }
        (args.out / "analysis.json").write_text(json.dumps(casing_report, indent=2, allow_nan=False) + "\n")
        plot_histories(histories, args.out / "evolution.png", names[:2])
        plot_fields(args.run, args.out / "fields.png", (
            ("pic_1A_two_coil_c010", "pic_1A_six_d120", "pic_1A_six_d130") if six else
            ("pic_1A_casing_none", "pic_1A_casing_r015", "pic_1A_casing_r015_m1kV")
        ))
        return
    if args.study == "gun":
        core_radius = 0.25 * json.loads((args.run / GUN_CASES[0] / "configuration.json").read_text())["radius"]
        barrels = {}
        for name, records in histories.items():
            configuration = json.loads((args.run / name / "configuration.json").read_text())
            window = [record for record in records if scalar(record, "time_s") >= args.window_start]
            source = np.array([scalar(record, "source_potential_V") for record in window])
            final = records[-1]
            exits = cast(list[int], final["exit_counts_xlo_xhi_ylo_yhi_zlo_zhi"])
            conductor_exits = cast(list[int], final.get("conductor_exit_counts", []))
            barrels[name] = {
                "box_lower_m": configuration["box_lower_m"], "box_upper_m": configuration["box_upper_m"],
                "mesh_shape": configuration["mesh_shape"], "gun_barrel": configuration["gun_barrel"],
                "seed": configuration["seed"],
                "source_potential_V": {"window_mean": float(source.mean()), "final": float(source[-1])},
                "final_conductor_charge_C": final.get("conductor_charge_C"),
                "final_barrel_exit_fraction": (
                    sum(conductor_exits) / (sum(exits) + sum(conductor_exits))
                    if sum(exits) + sum(conductor_exits) else None
                ),
            }
        report: dict[str, object] = {
            "scope": "Grounded, absorbing gun barrel around the emitter of the 1 A external-gun CUDA PIC model.",
            "cases": list(summaries.values()),
            "barrels": barrels,
            "final_fields": {name: core_field(args.run / name, core_radius) for name in names},
            "relative_to_wall_gun": {name: relative(name, GUN_CASES[0]) for name in GUN_CASES[1:]},
            "limitations": [
                "The barrel is a staircase of mesh nodes; the emitter potential is interpolated, not exactly 0 V.",
                "The 50 micrometre source and a few-cm barrel are both unresolved at the few-cell level.",
                "Grounded outer box, no coil casings, imposed two-coil magnetic field, electrons only.",
            ],
        }
        if args.domain_run is not None:
            for name in ("pic_1A_box_b1625", "pic_1A_box_b195"):
                summaries[name] = summarize(name, load(args.domain_run / name), args.window_start)
            report["barrel_relative_to_open_bottom_wall"] = {
                "pic_1A_gun_b1625": relative("pic_1A_gun_b1625", "pic_1A_box_b1625"),
                "pic_1A_gun_b195": relative("pic_1A_gun_b195", "pic_1A_box_b195"),
            }
        (args.out / "analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        plot_histories(histories, args.out / "evolution.png", GUN_CASES[:1])
        plot_fields(args.run, args.out / "fields.png", ("pic_1A_gun_wall", "pic_1A_gun_b195", "pic_1A_gun_b26"))
        return
    if args.study == "domain":
        core_radius = 0.25 * json.loads((args.run / DOMAIN_CASES[0] / "configuration.json").read_text())["radius"]
        domain_report = {
            "scope": "Grounded-box sensitivity of the 1 A external-gun CUDA PIC model at 65-cubed reference cells.",
            "cases": list(summaries.values()),
            "final_fields": {name: core_field(args.run / name, core_radius) for name in names},
            "relative_to_reference_box": {name: relative(name, DOMAIN_CASES[0]) for name in DOMAIN_CASES[1:]},
            "limitations": [
                "Transverse walls can only move inward: the coil windings lie just outside the reference box.",
                "A farther bottom wall leaves the gun inside the grounded volume rather than on a wall aperture.",
                "One seed per box; 65-cubed cells are mesh-sensitive at the ~10% level for the minimum potential.",
                "Grounded outer box, imposed two-coil magnetic field, electrons only.",
            ],
        }
        (args.out / "analysis.json").write_text(json.dumps(domain_report, indent=2, allow_nan=False) + "\n")
        plot_histories(histories, args.out / "evolution.png", DOMAIN_CASES[:1])
        plot_fields(args.run, args.out / "fields.png", ("pic_1A_box", "pic_1A_box_w045", "pic_1A_box_b195_t26"))
        return
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
    plot_histories(histories, args.out / "evolution.png", MESH_CASES)
    plot_fields(args.run, args.out / "fields.png", ("pic_1A_n33", "pic_1A_n65", "pic_1A_n129"))


if __name__ == "__main__":
    main()
