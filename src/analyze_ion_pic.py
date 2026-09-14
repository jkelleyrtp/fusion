"""Summarize coupled electron and molecular-ion PIC campaigns: neutralization, well depth, ion occupancy and sources."""

import argparse
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
import numpy as np

from analyze_pic_startup import Record, scalar

plt.switch_backend("Agg")

STUDIES: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "two-coil": (
        ("ions_p1e-3", "ions_p1e-3_nocx", "ions_p1e-3_nosec", "ions_p1e-2"),
        ("ions_p1e-3_dt05", "ions_p1e-3_cycle5", "ions_p1e-3_window80", "ions_p1e-3_ions2x"),
        ("ions_p1e-3", "ions_p1e-3_nocx", "ions_p1e-2"),
    ),
    "six-coil": (
        ("ions6_p1e-3", "ions6_p1e-3_s2345", "ions6_p1e-3_300mA", "ions6_p1e-2"),
        ("ions6_p1e-3_dt05", "ions6_p1e-3_cycle5", "ions6_p1e-3_window80", "ions6_p1e-3_ions2x"),
        ("ions6_p1e-3", "ions6_p1e-3_300mA", "ions6_p1e-2"),
    ),
    "six-coil-feed": (
        ("feed_1A_5keV", "feed_10A_5keV", "feed_10A_10keV", "feed_30A_10keV", "feed_100A_10keV",
         "feed_30A_10keV_60kAt", "feed_30A_10keV_10kAt", "feed_100A_10keV_10kAt"),
        (),
        ("feed_1A_5keV", "feed_30A_10keV", "feed_100A_10keV"),
    ),
    "six-coil-feed-fine": (
        ("feed_10A_10keV_idt2", "feed_30A_10keV_idt2", "feed_100A_10keV_idt2", "feed_30A_10keV_60kAt_idt2",
         "feed_100A_10keV_10kAt_idt2"),
        ("feed_10A_10keV_p1e-3", "feed_30A_10keV_p1e-3", "feed_100A_10keV_p1e-3"),
        ("feed_10A_10keV_idt2", "feed_100A_10keV_idt2", "feed_100A_10keV_p1e-3"),
    ),
    "six-coil-sustain": (
        ("sustain_1A_10keV", "sustain_3A_10keV", "sustain_10A_10keV_long", "sustain_30A_10keV_long",
         "sustain_10A_10keV_D2", "sustain_10A_10keV_p1e-4"),
        ("sustain_10A_10keV_s2345", "sustain_10A_10keV_cycle5"),
        ("sustain_1A_10keV", "sustain_10A_10keV_long", "sustain_30A_10keV_long"),
    ),
    "six-coil-splitting": (
        ("split_c20_w40", "split_c10_w80", "split_c5_w20", "split_c2p5_w40"),
        ("split_c10_w40_ions2x", "split_c5_w40_ions05x", "split_c5_w40_s2345", "split_c10_w40_idt05"),
        ("split_c20_w40", "split_c10_w80", "split_c5_w20", "split_c2p5_w40"),
    ),
    "six-coil-gun-limit": (
        ("limit_30A_20keV", "limit_100A_20keV", "limit_300A_20keV", "limit_100A_10keV_div30",
         "limit_100A_20keV_div30", "limit_100A_10keV_bias5kV", "limit_100A_20keV_bias5kV"),
        ("limit_30A_20keV_s2345",),
        ("limit_30A_20keV", "limit_100A_20keV", "limit_100A_20keV_div30"),
    ),
    "six-coil-multi-gun": (
        ("guns6_30A_10keV", "guns6_100A_10keV", "guns3_100A_10keV", "guns2_100A_10keV", "guns6_300A_10keV",
         "guns6_300A_20keV", "guns6_1000A_20keV"),
        ("guns6_100A_10keV_s2345",),
        ("guns2_100A_10keV", "guns6_100A_10keV", "guns6_1000A_20keV"),
    ),
    "six-coil-multi-gun-check": (
        ("guns6_100A_10keV_ppc4", "guns6_1000A_20keV_ppc4", "guns6_100A_10keV_p1e-4", "guns6_1000A_20keV_p1e-4"),
        ("guns6_100A_10keV_cycle5",),
        ("guns6_100A_10keV_ppc4", "guns6_1000A_20keV_ppc4", "guns6_100A_10keV_p1e-4"),
    ),
    "six-coil-multi-gun-scale": (
        ("guns6_100A_10keV_n49", "guns6_1000A_20keV_n49", "guns6_3000A_20keV_n49", "guns6_100A_10keV_60kAt",
         "guns6_1000A_20keV_60kAt", "guns6_100A_20keV", "guns6_3000A_20keV"),
        ("guns6_1000A_20keV_s2345",),
        ("guns6_1000A_20keV_n49", "guns6_1000A_20keV_60kAt", "guns6_3000A_20keV"),
    ),
    "six-coil-mesh": (
        ("guns6_100A_10keV_n81", "guns6_1000A_20keV_n81", "guns6_100A_20keV_n81", "guns6_100A_20keV_n49"),
        ("guns3_100A_10keV_n81", "guns3_100A_10keV_n49", "sustain_10A_10keV_n81", "sustain_10A_10keV_n49"),
        ("guns6_100A_10keV_n81", "guns3_100A_10keV_n81", "sustain_10A_10keV_n81"),
    ),
    "six-coil-gas": (
        ("d2_uniform_p1e-3", "d2_uniform_p1e-4", "d2_inlet_face_Q1e-3_S1", "d2_inlet_face_Q1e-4_S1",
         "d2_puff_face_Q1e-2_S1e3", "d2_puff_face_Q1e-1_S1e3", "d2_puff_corner_Q1e-1_S1e3", "d2_puff_gun_Q1e-1_S1e3"),
        (),
        ("d2_uniform_p1e-3", "d2_puff_face_Q1e-1_S1e3", "d2_puff_gun_Q1e-1_S1e3"),
    ),
    "six-coil-ion-gun": (
        ("gun_none", "gun_1mA_100eV", "gun_10mA_100eV", "gun_100mA_100eV", "gun_10mA_10eV", "gun_10mA_1keV",
         "gun_corner_10mA_100eV", "gun_10mA_100eV_bias5kV"),
        (),
        ("gun_none", "gun_10mA_100eV", "gun_100mA_100eV"),
    ),
    "six-coil-deuteron": (
        ("diss5_gun_none", "d2plus_10mA_100eV", "dplus_10mA_100eV", "dplus_10mA_100eV_s2345", "dplus_10mA_1keV",
         "dplus_100mA_100eV", "dplus_10mA_100eV_bias5kV", "dplus_10mA_100eV_60kAt"),
        (),
        ("diss5_gun_none", "d2plus_10mA_100eV", "dplus_10mA_100eV"),
    ),
    "six-coil-deuteron-fine": (
        ("dplus_30mA_100eV_idt2", "dplus_100mA_100eV_idt2", "dplus_100mA_1keV_idt2", "dplus_300mA_1keV_idt2",
         "dplus_100mA_100eV_bias5kV_idt2", "dplus_100mA_100eV_60kAt_idt2"),
        ("dplus_100mA_100eV_idt2_s2345", "dplus_100mA_100eV_idt1_20cyc"),
        ("dplus_30mA_100eV_idt2", "dplus_100mA_100eV_idt2", "dplus_300mA_1keV_idt2"),
    ),
    "six-coil-pulse": (
        ("pulse_continuous", "pulse_on150_off50", "pulse_on150_off20", "pulse_on50_off50", "pulse_on300_off100",
         "pulse_on50_off50_p1e-3", "pulse_on150_off50_s2345"),
        ("pulse_on150_off50_settle400",),
        ("pulse_continuous", "pulse_on150_off50", "pulse_on50_off50_p1e-3"),
    ),
    "six-coil-capture": (
        ("capture_off_1keV", "capture_on_1keV", "capture_always_1keV", "capture_continuous_1keV",
         "capture_off_300eV", "capture_off_1keV_on4_off2"),
        ("capture_off_1keV_s2345", "capture_off_1keV_idt2"),
        ("capture_off_1keV", "capture_on_1keV", "capture_continuous_1keV"),
    ),
}
CAPTURE = ("ion_bound_charge_C", "atomic_ion_bound_charge_C", "atomic_ion_alive_charge_C", "ion_gun_injected_charge_C")
SOURCE_KEYS = (
    "ion_species", "current_a", "energy_ev", "coil_current", "casing_voltage", "gas_pa", "gas_density_m3",
    "gas_density_at_origin_m3", "gas_inlet", "ion_gun", "dissociative_ionization",
)
METRICS = (
    "neutralization_fraction", "core_neutralization_fraction", "potential_origin_V", "potential_min_V",
    "core_mean_potential_V", "window_mean_electron_charge_C", "window_mean_core_electron_charge_C",
    "ion_core_count", "ion_core_time_weighted_kinetic_eV", "ion_mean_kinetic_eV", "field_energy_J",
)
PLOTS = (
    ("neutralization_fraction", "neutralization fraction"),
    ("potential_origin_V", "origin potential (V)"),
    ("window_mean_electron_charge_C", "window-mean electron charge (C)"),
    ("ion_core_count", "ion macroparticles in core"),
    ("ion_core_time_weighted_kinetic_eV", "core ion kinetic energy (eV)"),
    ("ion_lost_fraction", "ion lost / created"),
)


def complete(case: Path, configuration: dict[str, object], history: list[Record]) -> bool:
    done = (case / "DONE").read_text().strip() if (case / "DONE").is_file() else None
    return done == "complete" and bool(history) and scalar(history[-1], "cycle") == configuration["cycles"]


def load(case: Path, partial: bool) -> tuple[dict[str, object], list[Record]]:
    configuration = json.loads((case / "configuration.json").read_text())
    history = cast(list[Record], json.loads((case / "history.json").read_text()))
    if not history or not (partial or complete(case, configuration, history)):
        raise ValueError(f"Incomplete case: {case.name}")
    for record in history:
        created = scalar(record, "ion_created_charge_C")
        assert abs(scalar(record, "ion_charge_balance_C")) <= 1e-9 * max(created, 1e-18)
        assert all(math.isfinite(value) for value in record.values() if isinstance(value, (int, float)))
    return configuration, history


def derived(record: Record) -> dict[str, float]:
    """Scalar metrics, NaN where a record has none (for example neutralization with the gun off and no electrons)."""
    created = scalar(record, "ion_created_charge_C")
    return {
        **{name: math.nan if record[name] is None else scalar(record, name) for name in METRICS},
        **{name: math.nan if record.get(name) is None else scalar(record, name) for name in CAPTURE},
        "ion_alive_charge_C": scalar(record, "ion_alive_charge_C"),
        "ion_lost_fraction": scalar(record, "ion_lost_charge_C") / created if created else 0.0,
    }


def finite_stats(records: list[Record], reduce: Callable[[list[float]], np.floating] = np.mean) -> dict[str, float | None]:
    """Per-metric `reduce` over the records where the metric exists."""
    values = [derived(record) for record in records]
    result: dict[str, float | None] = {}
    for key in values[0]:
        finite = [value[key] for value in values if math.isfinite(value[key])]
        result[key] = float(reduce(finite)) if finite else None
    return result


def pulse_summary(configuration: dict[str, object], history: list[Record]) -> dict[str, object] | None:
    """Duty-averaged and gun-on means over the last complete gun period."""
    pulse = cast(dict[str, float] | None, configuration.get("electron_gun_pulse"))
    if pulse is None:
        return None
    period = round(pulse["period_s"] / cast(float, configuration["cycle_duration"]))
    periods = len(history) // period
    if not periods:
        return None
    last = history[(periods - 1) * period:periods * period]
    on = [record for record in last if record["electron_gun_on"]]
    return {
        "period_cycles": period, "last_period_cycles": [scalar(record, "cycle") for record in (last[0], last[-1])],
        "duty_mean": finite_stats(last), "gun_on_mean": finite_stats(on),
        "peak_neutralization_fraction": finite_stats(on, np.max)["neutralization_fraction"],
        "alive_ion_charge_at_period_end_C": scalar(last[-1], "ion_alive_charge_C"),
        "period_ends": [
            {"cycle": scalar(record, "cycle"),
             **{key: value if math.isfinite(value := derived(record)[key]) else None for key in CAPTURE}}
            for record in history[period - 1:periods * period:period]
        ],
    }


def plot_capture(histories: dict[str, list[Record]], output: Path) -> None:
    """Alive and energetically bound atomic ions per unit injected gun charge."""
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    for name, history in histories.items():
        time = [1e3 * scalar(record, "time_s") for record in history]
        values = [derived(record) for record in history]
        injected = [value["ion_gun_injected_charge_C"] or math.nan for value in values]
        off = [index for index, record in enumerate(history) if not record.get("electron_gun_on", True)]
        for axis, key in zip(axes, ("atomic_ion_alive_charge_C", "atomic_ion_bound_charge_C")):
            axis.plot(time, [value[key] / total for value, total in zip(values, injected)], label=name,
                      marker=".", markersize=4, markevery=off)
        axes[2].plot(time, [value["potential_origin_V"] for value in values], label=name, marker=".",
                     markersize=4, markevery=off)
    for axis, label in zip(axes, ("alive D+ / injected gun charge", "bound D+ / injected gun charge",
                                  "origin potential (V)")):
        axis.set_xlabel("time (ms, dots: electron gun off)")
        axis.set_ylabel(label)
        axis.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    figure.savefig(output, dpi=140)
    plt.close(figure)


def last_snapshot(case: Path) -> Path:
    return max((case / "snapshots").glob("cycle-*.npz"))


def birth_potential(case: Path) -> float | None:
    """Charge-weighted mean potential at the birth point of the ions alive in the last snapshot."""
    with np.load(last_snapshot(case), allow_pickle=False) as values:
        weight, potential = values["ion_count"], values["ion_birth_potential_V"]
    return float((weight * potential).sum() / weight.sum()) if weight.sum() else None


def summarize(case: Path, configuration: dict[str, object], history: list[Record], done: bool) -> dict[str, object]:
    name = case.name
    tail = history[len(history) * 3 // 4:]
    final = history[-1]
    return {
        "name": name, "complete": done, "cycles": len(history), "requested_cycles": configuration["cycles"],
        "time_s": scalar(final, "time_s"),
        "sources": {key: configuration[key] for key in SOURCE_KEYS if key in configuration},
        "ion_gun_injected_charge_C": final.get("ion_gun_injected_charge_C"),
        "atomic_ion_alive_charge_C": final.get("atomic_ion_alive_charge_C"),
        "alive_ion_mean_birth_potential_V": birth_potential(case),
        "cycle_duration_s": configuration["cycle_duration"],
        "electron_window_s": configuration["electron_window"], "ion_dt_s": configuration["ion_dt"],
        "ions_per_cycle": configuration["ions_per_cycle"],
        "final": {key: value if math.isfinite(value) else None for key, value in derived(final).items()},
        "last_quarter_mean": finite_stats(tail), "last_quarter_spread": finite_stats(tail, np.std),
        "electron_gun_pulse": pulse_summary(configuration, history),
        "neutralization_time_s": final["neutralization_time_s"],
        "ion_exit_counts": final["ion_exit_counts"], "ion_exchange_events": final["ion_exchange_events"],
        "max_ion_charge_balance_C": max(abs(scalar(record, "ion_charge_balance_C")) for record in history),
        "wall_s": scalar(final, "wall_s"),
    }


def plot_histories(histories: dict[str, list[Record]], physics: tuple[str, ...], output: Path) -> None:
    figure, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    for axis, (key, label) in zip(axes.flat, PLOTS):
        for name, history in histories.items():
            time = [1e3 * scalar(record, "time_s") for record in history]
            off = [index for index, record in enumerate(history) if not record.get("electron_gun_on", True)]
            axis.plot(time, [derived(record)[key] for record in history], label=name,
                      linestyle="-" if name in physics else "--", marker=".", markersize=4, markevery=off)
        axis.set_xlabel("time (ms, dots: electron gun off)")
        axis.set_ylabel(label)
        axis.grid(alpha=0.3)
    axes.flat[0].legend(fontsize=7)
    figure.savefig(output, dpi=140)
    plt.close(figure)


def plot_scan(summaries: dict[str, dict[str, object]], output: Path) -> None:
    names = list(summaries)
    figure, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    for axis, (key, label) in zip(axes.flat, PLOTS):
        values, spread = ([math.nan if (value := cast(dict[str, float | None], summaries[name][field])[key]) is None
                           else value for name in names] for field in ("last_quarter_mean", "last_quarter_spread"))
        axis.bar(range(len(names)), values, yerr=spread, color=["C0" if summaries[name]["complete"] else "C7"
                                                                for name in names])
        axis.set_xticks(range(len(names)), names, rotation=60, ha="right", fontsize=7)
        axis.set_ylabel(f"{label}, last-quarter mean")
        axis.grid(alpha=0.3, axis="y")
    figure.suptitle("grey bars: incomplete (partial) cases", fontsize=9)
    figure.savefig(output, dpi=140)
    plt.close(figure)


def plot_fields(run: Path, output: Path, names: tuple[str, ...]) -> None:
    figure, axes = plt.subplots(len(names), 3, figsize=(15, 3.6 * len(names)), constrained_layout=True,
                               squeeze=False)
    for row, name in zip(axes, names):
        snapshot = last_snapshot(run / name)
        with np.load(snapshot, allow_pickle=False) as values:
            potential, lower, upper = values["potential_V"], values["lower_m"], values["upper_m"]
            weight, born = values["ion_count"], values["ion_birth_potential_V"]
        if weight.sum():
            row[2].hist(born, bins=60, weights=weight / weight.sum())
        row[2].set_xlabel("potential at ion birth (V)")
        row[2].set_ylabel("alive ion charge fraction")
        row[2].set_title(f"{name}: alive-ion birth potential", fontsize=9)
        center = [size // 2 for size in potential.shape]
        for axis, (plane, extent, labels) in zip(row, (
            (potential[center[0], :, :].T, (lower[1], upper[1], lower[2], upper[2]), ("y (m)", "z (m)")),
            (potential[:, :, center[2]].T, (lower[0], upper[0], lower[1], upper[1]), ("x (m)", "y (m)")),
        )):
            image = axis.imshow(plane, origin="lower", extent=extent, cmap="viridis")
            axis.set_title(f"{name}: {snapshot.stem}", fontsize=9)
            axis.set_xlabel(labels[0])
            axis.set_ylabel(labels[1])
            figure.colorbar(image, ax=axis, label="potential (V)")
    figure.savefig(output, dpi=140)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--study", choices=tuple(STUDIES), default="two-coil")
    parser.add_argument("--partial", action="store_true",
                        help="summarize cases that are still running and skip cases without a history or snapshot")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    physics, splitting, fields = STUDIES[args.study]
    if args.partial:
        missing = [name for name in physics + splitting
                   if not (args.run / name / "history.json").is_file()
                   or not any((args.run / name / "snapshots").glob("cycle-*.npz"))]
        physics, splitting = (tuple(name for name in names if name not in missing) for names in (physics, splitting))
        fields = tuple(name for name in fields if name not in missing)
    else:
        missing = []
    reference_case = physics[0]
    loaded = {name: load(args.run / name, args.partial) for name in physics + splitting}
    summaries = {
        name: summarize(args.run / name, configuration, history, complete(args.run / name, configuration, history))
        for name, (configuration, history) in loaded.items()
    }
    reference = cast(dict[str, float | None], summaries[reference_case]["last_quarter_mean"])

    def relative(name: str) -> dict[str, float | None]:
        means = cast(dict[str, float | None], summaries[name]["last_quarter_mean"])
        return {key: (mean - value) / abs(value) if value and (mean := means[key]) is not None else None
                for key, value in reference.items()}

    result = {
        "run": str(args.run), "partial": bool(missing) or not all(summary["complete"] for summary in summaries.values()),
        "reference": reference_case, "cases": summaries, "without_history": missing,
        "relative_to_reference": {name: relative(name) for name in summaries if name != reference_case},
    }
    (args.out / "ion-pic-summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    histories = {name: history for name, (_, history) in loaded.items()}
    plot_histories(histories, physics, args.out / "ion-pic-histories.png")
    plot_fields(args.run, args.out / "ion-pic-fields.png", fields)
    plot_scan(summaries, args.out / "ion-pic-scan.png")
    if args.study == "six-coil-capture":
        plot_capture(histories, args.out / "ion-pic-capture.png")
    for name, summary in summaries.items():
        means = {key: math.nan if value is None else value
                 for key, value in cast(dict[str, float | None], summary["last_quarter_mean"]).items()}
        print(f"{name:22s} {summary['cycles']}/{summary['requested_cycles']} neut={means['neutralization_fraction']:.3f} "
              f"origin={means['potential_origin_V']:8.1f} V core_ions={means['ion_core_count']:8.0f} "
              f"core_KE={means['ion_core_time_weighted_kinetic_eV']:7.1f} eV lost={means['ion_lost_fraction']:.3f}")


if __name__ == "__main__":
    main()
