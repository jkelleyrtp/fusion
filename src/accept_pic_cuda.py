"""Physics-level CUDA acceptance: paired seeds against reference seed spread."""

import argparse
import json
import math
import statistics
from itertools import pairwise
from pathlib import Path
from typing import cast

from analyze_pic_startup import Record, check_completed, scalar, summarize

SPREAD_FRACTION = 0.1
METRICS = {
    "minimum_potential_V": ("absolute", 1e-3),
    "field_energy_J": ("relative", 1e-6),
    "observed_dwell_s": ("relative", 1e-6),
    "observed_core_dwell_s": ("relative", 1e-6),
    "core_electron_count": ("relative", 1e-6),
    "loss_fraction": ("particles", 2),
    "core_entry_events_per_injected_particle": ("particles", 2),
    "repeated_entry_particle_fraction": ("particles", 2),
}
FACES = ("xlo", "xhi", "ylo", "yhi", "zlo", "zhi")


def load(case: Path) -> list[Record]:
    history = cast(list[Record], json.loads((case / "history.json").read_text()))
    check_completed(case, history)
    return history


def seconds_per_step(history: list[Record]) -> float:
    intervals = [
        (scalar(after, "wall_s") - scalar(before, "wall_s"))
        / (scalar(after, "step") - scalar(before, "step"))
        for before, after in pairwise(history[1:])
    ]
    return statistics.median(intervals)


def value(summary: dict[str, object], key: str) -> float:
    return float(cast(float | int, summary[key]))


def faces(summary: dict[str, object]) -> list[int]:
    return cast(list[int], summary["exit_counts_xlo_xhi_ylo_yhi_zlo_zhi"])


def evaluate(
    reference: dict[int, dict[str, object]], cuda: dict[int, dict[str, object]],
) -> list[dict[str, object]]:
    if set(reference) != set(cuda) or len(reference) < 3:
        raise ValueError("Acceptance needs at least three seeds with both backends")
    rows = []
    for key, (kind, floor) in METRICS.items():
        values = [value(item, key) for item in reference.values()]
        spread = max(values) - min(values)
        for seed in sorted(reference):
            expected, observed = value(reference[seed], key), value(cuda[seed], key)
            if kind == "relative":
                bound = max(SPREAD_FRACTION * spread, floor * abs(expected))
            elif kind == "particles":
                bound = max(SPREAD_FRACTION * spread, floor / value(reference[seed], "injected_particles"))
            else:
                bound = max(SPREAD_FRACTION * spread, floor)
            rows.append({
                "metric": key, "seed": seed, "reference": expected, "cuda": observed,
                "difference": abs(observed - expected), "reference_seed_spread": spread,
                "bound": bound, "passed": abs(observed - expected) <= bound,
            })
    for index, face in enumerate(FACES):
        counts = [faces(item)[index] for item in reference.values()]
        spread = max(counts) - min(counts)
        for seed in sorted(reference):
            expected, observed = faces(reference[seed])[index], faces(cuda[seed])[index]
            bound = max(SPREAD_FRACTION * spread, 2)
            rows.append({
                "metric": f"exit_{face}", "seed": seed, "reference": expected, "cuda": observed,
                "difference": abs(observed - expected), "reference_seed_spread": spread,
                "bound": bound, "passed": abs(observed - expected) <= bound,
            })
    accounting_floor = max(
        1e-24, 10 * max(abs(value(item, "deposition_error_C")) for item in reference.values()),
    )
    for seed in sorted(cuda):
        for key in ("deposition_error_C", "charge_balance_C"):
            observed = abs(value(cuda[seed], key))
            rows.append({
                "metric": key, "seed": seed, "reference": None, "cuda": observed,
                "difference": observed, "reference_seed_spread": None,
                "bound": accounting_floor, "passed": observed <= accounting_floor,
            })
    return rows


def main() -> None:
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--campaign", type=Path, required=True)
    arguments.add_argument("--out", type=Path, required=True)
    args = arguments.parse_args()
    manifest = json.loads((args.campaign / "manifest.json").read_text())
    if manifest["study"] != "acceptance":
        raise ValueError("Acceptance analysis requires an acceptance-study campaign")
    summaries: dict[str, dict[int, dict[str, object]]] = {"reference": {}, "cuda": {}}
    timings: dict[str, dict[int, float]] = {"reference": {}, "cuda": {}}
    for case in manifest["cases"]:
        history = load(args.campaign / case["name"])
        summaries[case["kernels"]][case["seed"]] = summarize(case["name"], history)
        timings[case["kernels"]][case["seed"]] = seconds_per_step(history)
    rows = evaluate(summaries["reference"], summaries["cuda"])
    failures = [row for row in rows if not row["passed"]]
    speedups = [
        timings["reference"][seed] / timings["cuda"][seed] for seed in sorted(timings["cuda"])
    ]
    report = {
        "scope": (
            "Physics-level acceptance of CUDA operators: paired-seed differences against "
            f"{SPREAD_FRACTION:g} of the reference seed-to-seed spread with numerical floors. "
            "Not bitwise parity and not physical convergence."
        ),
        "source_revision": manifest["source_revision"],
        "seeds": sorted(summaries["reference"]),
        "passed": not failures,
        "failures": failures,
        "comparisons": rows,
        "summaries": {
            backend: {str(seed): summary for seed, summary in items.items()}
            for backend, items in summaries.items()
        },
        "seconds_per_step": {
            backend: {str(seed): seconds for seed, seconds in items.items()}
            for backend, items in timings.items()
        },
        "median_step_speedup": statistics.median(speedups),
    }
    if not all(math.isfinite(item) for item in speedups):
        raise ValueError("Nonfinite timing")
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "acceptance.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": report["passed"], "failures": len(failures),
                      "median_step_speedup": report["median_step_speedup"]}), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
