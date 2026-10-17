#!/usr/bin/env python3
"""Holding time of picket-fence runs over chosen intervals, to compare at another paper's run length.

    python3 holding_by_interval.py 10-20,20-28 RUN_DIR [RUN_DIR ...]

Intervals are in electron crossings of the coil diameter at the fed temperature. For each run and interval it
prints the holding time in those crossings and the electrons' mean energy over 1.5 times the fed temperature.
The rate of leaving is the feed less the change in the number held, so no snapshots are needed.
"""

import sys
from pathlib import Path

import numpy as np
from analyze_picket import M_E, Q_E, constants, thermal_speed


def holding_time(time: np.ndarray, held: np.ndarray, feed: float, start: float, end: float) -> float:
    """Mean number held between `start` and `end` over the rate of leaving, which is `feed` (per unit of `time`)
    less the rate at which the number held changes."""
    inside = (time >= start) & (time <= end)
    time, held = time[inside], held[inside]
    return float(held.mean() / (feed - (held[-1] - held[0]) / (time[-1] - time[0])))


if __name__ == "__main__":
    intervals = [tuple(float(edge) for edge in interval.split("-")) for interval in sys.argv[1].split(",")]
    for run in map(Path, sys.argv[2:]):
        c = constants(run)
        crossing = 2 * c["rc"] / thermal_speed(c["te"], M_E)
        number = np.loadtxt(run / "diags/reducedfiles/number.txt")
        energy = np.loadtxt(run / "diags/reducedfiles/energy.txt")
        time, sustaining = number[:, 1] / crossing, c["feed"] * c["sustain"] * crossing
        cells = []
        for start, end in intervals:
            if start < c["tfill"] / crossing - 0.05 or end > time[-1] + 0.5:
                cells.append("       -")
                continue
            during = (energy[:, 1] / crossing >= start) & (energy[:, 1] / crossing <= end)
            mean_energy = energy[during, 6].mean() / (1.5 * c["te"] * Q_E)
            cells.append(f"{holding_time(time, number[:, 6], sustaining, start, end):5.1f} {mean_energy:.2f}")
        print(f"{run.name:24s} " + "  ".join(cells))
