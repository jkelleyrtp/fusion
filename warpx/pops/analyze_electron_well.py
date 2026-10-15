"""Ion compression and well shape for POPS runs with injected electrons (WarpX reduced diagnostics)."""
import json
import sys
from pathlib import Path

import numpy as np


def columns(path: Path) -> dict[str, int]:
    names = path.read_text().split("\n", 1)[0].lstrip("#").split()
    return {name.split("]")[1].split("(")[0]: index for index, name in enumerate(names)}


def potential(snapshot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(snapshot[:, 2])
    x, ex = snapshot[order, 2], snapshot[order, 5]
    return x, np.array([np.trapezoid(ex[i:], x[i:]) for i in range(len(x))])  # wall at 0 V


def reduce(run: Path) -> dict:
    files = run / "diags/reducedfiles"
    ions, number = (np.loadtxt(files / name) for name in ("ibeam.txt", "number.txt"))
    column = columns(files / "number.txt")
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
    # The ion charge reshapes the well during a collapse, so report it with the ions out and with them in.
    centre, shape, misfit, ion_radius = [], [], [], []
    for step in np.unique(probe[:, 0]):
        x, phi = potential(probe[probe[:, 0] == step])
        if step == 0 or phi[0] == 0:
            continue
        centre.append(phi[0])
        shape.append(np.interp(0.5 * x[-1], x, phi) / phi[0])
        misfit.append(np.sqrt(np.mean((phi / phi[0] - 1 + (x / x[-1]) ** 2) ** 2)))
        ion_radius.append(np.interp(step, ions[:, 0], radius))
    centre, shape, misfit, ion_radius = map(np.array, (centre, shape, misfit, ion_radius))
    out = ion_radius > 0.8 * radius[0]
    return {
        "run": run.name,
        "collapse_times_ns": [round(float(time[i]) * 1e9, 1) for i in collapses],
        "compression": [round(float(radius[0] / radius[i]), 2) for i in collapses],
        "ions_kept": round(float(number[-1, column["ions_weight"]] / number[0, column["ions_weight"]]), 3),
        "electrons": float(np.median(number[len(number) // 2:, column["electrons_weight"]])),
        "well_centre_V": round(float(np.median(centre[out]))),
        "well_half_radius_over_centre": round(float(np.median(shape[out])), 3),  # 0.75 for a harmonic well
        "well_misfit_to_parabola": round(float(np.median(misfit[out])), 3),  # rms over radius, in units of the depth
        "shallowest_centre_V": round(float(centre.max())),  # at the deepest sampled point of a collapse
    }


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(json.dumps(reduce(Path(name))))
