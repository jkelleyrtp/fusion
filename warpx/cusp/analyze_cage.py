"""Reduce cusp-cage runs to one JSON line each: electron inventory, dwell time and centre voltage.

Usage: analyze_cage.py RUN_DIR [RUN_DIR ...]   (each holds diags/reducedfiles and warpx_used_inputs)

The dwell time is the electron inventory divided by the emission rate. It equals the mean time an
electron spends in the device only once the inventory has stopped changing, so `filling` reports the
net growth of the inventory over the last fifth of the run as a fraction of the emission rate.
The empty-device centre voltage is read at step 1, before any emitted charge matters.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

Q_E = 1.602176634e-19


def constants(run: Path) -> dict[str, float]:
    """The my_constants values this run used, from the inputs WarpX echoes into the run directory."""
    text = (run / "warpx_used_inputs").read_text()
    names = ("a", "coil_at", "vgrid", "wall_v", "current", "eb0", "dt", "ncell", "gun_off", "nions")
    return {name: float(re.search(rf"^my_constants\.{name} = (\S+)", text, re.M).group(1)) for name in names}


def line_potential(run: Path, name: str, end_voltage: float):
    """Voltage along a probe line, integrated inward from the known wall voltage, per output step."""
    data = np.loadtxt(run / f"diags/reducedfiles/{name}.txt", skiprows=1)
    out = {}
    for step in np.unique(data[:, 0]):
        rows = data[data[:, 0] == step]
        pos, efield = rows[:, 2:5], rows[:, 5:8]
        r = np.linalg.norm(pos, axis=1)
        order = np.argsort(r)
        r, pos, efield = r[order], pos[order], efield[order]
        e_r = (efield * pos).sum(axis=1) / np.maximum(r, 1e-12)
        rise = np.concatenate([[0.0], np.cumsum(0.5 * (e_r[1:] + e_r[:-1]) * np.diff(r))])
        out[int(step)] = (r, end_voltage + rise[-1] - rise)
    return out


def histogram(run: Path, name: str):
    data = np.loadtxt(run / f"diags/reducedfiles/{name}.txt", skiprows=1, ndmin=2)
    return data[:, 0].astype(int), data[:, 2:]


def reduce(run: Path) -> dict:
    c = constants(run)
    number = np.loadtxt(run / "diags/reducedfiles/number.txt", skiprows=1, ndmin=2)
    time, electrons = number[:, 1], number[:, 6]
    if time[-1] < 5.0e-10:
        raise ValueError(f"{run.name} has only run {time[-1]:.2e} s; the emission rate needs 0.3 ns")
    # The wall source delivers a few percent less than the nominal current because the emitter patches
    # are cut cells. Nothing can be lost in the first 0.3 ns, so the early inventory gives the true rate.
    early = np.searchsorted(time, 3.0e-10)
    rate = electrons[early] / time[early]
    last = time >= 0.8 * time[-1]
    growth = np.polyfit(time[last], electrons[last], 1)[0] / rate
    axis = line_potential(run, "axis", 0.0 if c["gun_off"] == 0 else c["wall_v"])
    # Step 0 is written before the first field solve and holds no field, so the first solved step
    # (a few electrons, so effectively the empty device) is the reference.
    steps = sorted(step for step in axis if step > 0)
    centre = {step: float(axis[step][1][0]) for step in steps}
    r, final = axis[steps[-1]]
    edge = line_potential(run, "edge", c["wall_v"])[steps[-1]]
    corner = line_potential(run, "corner", c["wall_v"])[steps[-1]]
    hist_steps, radial = histogram(run, "erad")
    bins = (np.arange(radial.shape[1]) + 0.5) * 2.4 * c["a"] / radial.shape[1]
    tail = radial[hist_steps >= 0.8 * hist_steps[-1]].mean(axis=0)
    _, core_energy = histogram(run, "eke")
    energy_bins = (np.arange(core_energy.shape[1]) + 0.5) * 1.2 * c["vgrid"] / core_energy.shape[1]
    core = core_energy[-1]
    out_steps, outside = histogram(run, "eout")
    cosine = 0.55 + (np.arange(outside.shape[1]) + 0.5) * 0.45 / outside.shape[1]
    # Runs are read while still writing, so each histogram is indexed by its own steps.
    out = outside[out_steps >= 0.8 * out_steps[-1]].mean(axis=0)
    at = lambda line, radius: float(np.interp(radius, line[0], line[1]))
    return {
        "run": run.name,
        "coil_at": c["coil_at"], "current_A": c["current"], "vgrid_V": c["vgrid"], "ncell": c["ncell"],
        "end_ns": round(time[-1] * 1e9, 2),
        "emitted_A": round(rate * Q_E, 4),
        "electrons": float(electrons[-1]),
        "dwell_ns": round(electrons[-1] / rate * 1e9, 3),
        "filling": round(float(growth), 3),
        "centre_V_empty": round(centre[steps[0]], 1),
        "centre_V": round(centre[steps[-1]], 1),
        "centre_V_min": round(min(centre.values()), 1),
        "well_V": round(centre[steps[0]] - centre[steps[-1]], 1),
        "axis_V_at_5mm_10mm": [round(at((r, final), x), 1) for x in (0.005, 0.01)],
        "edge_V_at_5mm_10mm": [round(at(edge, x), 1) for x in (0.005, 0.01)],
        "corner_V_at_5mm_10mm": [round(at(corner, x), 1) for x in (0.005, 0.01)],
        "inside_5mm": round(float(tail[bins < 0.005].sum() / max(tail.sum(), 1e-300)), 4),
        "inside_cage": round(float(tail[bins < 0.013].sum() / max(tail.sum(), 1e-300)), 4),
        "core_mean_eV": round(float((core * energy_bins).sum() / max(core.sum(), 1e-300)), 1),
        "outside_on_axis": round(float(out[cosine > 0.95].sum() / max(out.sum(), 1e-300)), 3),
        "outside_share": round(float(out.sum() / max(tail.sum(), 1e-300)), 4),
    }


if __name__ == "__main__":
    for path in sys.argv[1:]:
        run = Path(path)
        if (run / "diags/reducedfiles/number.txt").exists():
            print(json.dumps(reduce(run)))
