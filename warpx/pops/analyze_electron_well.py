"""Ion compression and well shape for POPS runs with injected electrons (WarpX reduced diagnostics)."""
import json
import sys
from pathlib import Path

import numpy as np


def reduce(run: Path) -> dict:
    files = run / "diags/reducedfiles"
    ions, number = (np.loadtxt(files / name) for name in ("ibeam.txt", "number.txt"))
    probe = np.loadtxt(files / "probe.txt", skiprows=1)  # its header line has no comment marker
    time, radius = ions[:, 1], np.sqrt((ions[:, 9:12] ** 2).sum(axis=1))
    inner = np.flatnonzero((radius[1:-1] < radius[:-2]) & (radius[1:-1] <= radius[2:])) + 1
    minima = [i for i in inner if radius[i] < 0.8 * radius[0]]
    collapses = [minima[0]] if minima else []
    for i in minima[1:]:  # keep one minimum per collapse
        if time[i] - time[collapses[-1]] > 1e-8:
            collapses.append(i)
        elif radius[i] < radius[collapses[-1]]:
            collapses[-1] = i
    last = probe[probe[:, 0] == probe[-1, 0]]
    x, ex = last[:, 2], last[:, 5]
    order = np.argsort(x)
    x, ex = x[order], ex[order]
    phi = np.array([np.trapezoid(ex[i:], x[i:]) for i in range(len(x))])  # wall at 0 V
    half = np.interp(0.5 * x[-1], x, phi)
    return {
        "run": run.name,
        "collapse_times_ns": [round(float(time[i]) * 1e9, 1) for i in collapses],
        "compression": [round(float(radius[0] / radius[i]), 2) for i in collapses],
        "ions_kept": round(float(number[-1, 7] / number[0, 7]), 3),
        "electrons": float(number[-1, 6]),
        "well_centre_V": round(float(phi[0])),
        "well_half_radius_over_centre": round(float(half / phi[0]), 3),  # 0.75 for a harmonic well
    }


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(json.dumps(reduce(Path(name))))
