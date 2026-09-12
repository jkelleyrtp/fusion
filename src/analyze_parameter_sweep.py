"""Summarize finite-window residence from archived ensemble escape records."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory
    manifest = json.loads((root / "manifest.json").read_text())
    if not (root / "DONE").exists() or json.loads((root / "failures.json").read_text()):
        raise ValueError("Sweep is incomplete")
    rows = []
    dwell_by_case = {}
    initial_by_case = {}
    for case in manifest["cases"]:
        paths = list((root / case["id"]).glob("*/summary.json"))
        if len(paths) != 1:
            raise ValueError(f"Expected exactly one member for {case['id']}")
        summary = json.loads(paths[0].read_text())
        n = summary["particles"]
        window = summary["sim_duration_s"]
        with np.load(paths[0].with_name("results.npz"), allow_pickle=False) as data:
            exits = data["esc_where"]
            times = data["esc_time"].astype(np.float64)
            if len(exits) != n or not np.isin(exits, [0, 1, 2, 3]).all():
                raise ValueError("Invalid ensemble escape records")
            counts = np.bincount(exits, minlength=4)
            expected = [summary[key] for key in (
                "confined_at_end", "escaped_minus_z_cusp",
                "escaped_plus_z_cusp", "escaped_ring_cusp")]
            if counts.tolist() != expected:
                raise ValueError("Summary disagrees with ensemble counts")
            if not np.isfinite(times[exits != 0]).all() or (times[exits != 0] < 0).any():
                raise ValueError("Invalid escape time")
            dwell = np.where(exits == 0, window, np.minimum(times, window))
            summary_mean = ((summary["mean_escape_time_s"] or 0) * (n - counts[0])
                            + window * counts[0]) / n
            if not np.isclose(dwell.mean(), summary_mean, rtol=1e-6, atol=1e-15):
                raise ValueError("Summary disagrees with finite-window mean residence")
            dwell_by_case[case["id"]] = dwell
            initial_by_case[case["id"]] = data["traj"][:, 0, :].copy()
        rows.append({
            "case": case["id"], "coil_current_A": case["current"],
            "energy_eV": case["energy"], "aim_deg": case["angle"],
            "cone_half_angle_deg": case["cone"], "particles": n,
            "window_us": window * 1e6, "mean_dwell_us": float(dwell.mean() * 1e6),
            "mean_dwell_standard_error_us": float(dwell.std(ddof=1) / np.sqrt(n) * 1e6),
            "mean_dwell_in_a_over_v": float(dwell.mean() / window * 50),
            "surviving_fraction": float(counts[0] / n),
            "minus_z_fraction": float(counts[1] / n),
            "plus_z_fraction": float(counts[2] / n),
            "radial_fraction": float(counts[3] / n),
            "source_B_T": summary["gun_B_T"], "axis_max_B_T": summary["B_axis_max_T"],
            "seed": summary["rng_seed"],
        })
    if len({row["case"] for row in rows}) != len(rows):
        raise ValueError("Duplicate case identifiers")
    paired = []
    for row in rows:
        key = str(row["case"])
        if not key.endswith("_refined"):
            continue
        base = key.removesuffix("_refined")
        if not np.array_equal(initial_by_case[key], initial_by_case[base]):
            raise ValueError("Refinement does not preserve recorded initial samples")
        delta = dwell_by_case[key] - dwell_by_case[base]
        paired.append({
            "base": base, "refined": key,
            "mean_change_us": float(delta.mean() * 1e6),
            "paired_standard_error_us": float(delta.std(ddof=1) / np.sqrt(len(delta)) * 1e6),
            "relative_change": float(delta.mean() / dwell_by_case[base].mean()),
        })
    result = {
        "source_revision": manifest["git_revision"],
        "finished_at": (root / "DONE").read_text().strip(),
        "interpretation": "Finite-window means; survivors are censored. Standard errors describe launch sampling only.",
        "rows": rows, "paired_refinement": paired,
    }
    (root / "analysis.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    with (root / "analysis.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"cases": len(rows), "paired_refinement": paired}, indent=2))


if __name__ == "__main__":
    main()
