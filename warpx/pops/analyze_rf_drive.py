"""Reduce radio-frequency-driven POPS runs: the swing of the ion cloud's rms radius in each drive period, as JSON lines."""

import argparse
import json
from pathlib import Path

import numpy as np

from analyze_electron_well import columns


def reduce(run: Path, period: float) -> dict:
    files = run / "diags/reducedfiles"
    ions, number = (np.loadtxt(files / name) for name in ("ibeam.txt", "number.txt"))
    time, radius = ions[:, 1], np.sqrt((ions[:, 9:12] ** 2).sum(axis=1))
    weight = number[:, columns(files / "number.txt")["ions_weight"]]
    smallest, swing, kept = [], [], []
    for index in range(int(time[-1] / period)):
        window = (time >= index * period) & (time < (index + 1) * period)
        smallest.append(round(float(radius[window].min() / radius[0]), 3))
        swing.append(round(float(radius[window].max() / radius[window].min()), 2))
        kept.append(round(float(np.interp((index + 1) * period, number[:, 1], weight) / weight[0]), 3))
    return {"run": run.name, "largest_over_smallest_radius": swing, "smallest_over_initial_radius": smallest, "ions_kept": kept}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--period", type=float, required=True, help="drive period (s)")
    args = parser.parse_args()
    for run in args.runs:
        print(json.dumps(reduce(run, args.period)))
