"""Reduce cusp-cage runs to one JSON line each: electron inventory, dwell time and centre voltage.

Usage: analyze_cage.py RUN_DIR [RUN_DIR ...]   (each holds diags/reducedfiles and warpx_used_inputs)

The dwell time is the electron inventory divided by the emission rate. It equals the mean time an
electron spends in the device only once the inventory has stopped changing, so `filling` reports the
net growth of the inventory over the last fifth of the run as a fraction of the emission rate.
`kept_early` is the same fraction between 0.3 and 1 ns, before any electron has crossed the device:
below 1 the emitters are choked by their own charge and both of the above overstate the current.
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
    out = {name: float(re.search(rf"^my_constants\.{name} = (\S+)", text, re.M).group(1)) for name in names}
    # Decks older than the emitter switch have no toff; their emitters never switch off.
    found = re.search(r"^my_constants\.toff = (\S+)", text, re.M)
    out["toff"] = float(found.group(1)) if found else 1.0
    # Only the gas deck has a gas density.
    found = re.search(r"^my_constants\.ngas = (\S+)", text, re.M)
    out["ngas"] = float(found.group(1)) if found else 0.0
    gun_r = re.search(r"^my_constants\.gun_r = (\S+)", text, re.M).group(1)
    out["gun_r"] = out["a"] * 0.15 if "a" in gun_r else float(gun_r)
    return out


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


C_LIGHT = 299792458.0
SHELL = 0.8e-3  # thickness of the flux-measuring shell just inside the wall, as set in the deck
RING_SHELL = 0.6e-3  # thickness of the shell around the rings


def shell_currents(run: Path, time: np.ndarray, electrons: np.ndarray) -> dict:
    """Late-time currents (A) through the shell inside the wall, and what the count balance leaves for the rings.

    Runs made before the deck had the shell histograms return nothing.
    """
    if not (run / "diags/reducedfiles/fcol.txt").exists():
        return {}
    out = {}
    for name, label, thickness in (("fcol", "emitter", SHELL), ("fwall", "wall", SHELL), ("fring", "ring", RING_SHELL)):
        if not (run / f"diags/reducedfiles/{name}.txt").exists():
            continue
        data = np.loadtxt(run / f"diags/reducedfiles/{name}.txt", skiprows=1, ndmin=2)
        when, weight = data[:, 1], data[:, 2:]
        velocity = (-0.25 + 0.5 * (np.arange(weight.shape[1]) + 0.5) / weight.shape[1]) * C_LIGHT
        late = when >= 0.8 * when[-1]
        current = weight[late].mean(axis=0) * velocity / thickness * Q_E
        out[f"{label}_in_A"] = round(float(-current[velocity < 0].sum()), 4)
        out[f"{label}_out_A"] = round(float(current[velocity > 0].sum()), 4)
    if "ring_in_A" in out:
        # Around the rings negative velocity is toward the ring surface, so "in" minus "out" is what they collect.
        out["ring_direct_A"] = round(out.pop("ring_in_A") - out.pop("ring_out_A"), 4)
    last = time >= 0.8 * time[-1]
    filling = np.polyfit(time[last], electrons[last], 1)[0] * Q_E
    net_in = out["emitter_in_A"] - out["emitter_out_A"] + out["wall_in_A"] - out["wall_out_A"]
    out["net_in_A"] = round(net_in, 4)
    out["filling_A"] = round(float(filling), 4)
    # Electrons that crossed the shell inward and are neither still in the device nor back out through
    # the shell can only have landed on the rings.
    out["ring_A"] = round(net_in - float(filling), 4)
    return out


def reduce(run: Path) -> dict:
    c = constants(run)
    number = np.loadtxt(run / "diags/reducedfiles/number.txt", skiprows=1, ndmin=2)
    time, electrons, ions = number[:, 1], number[:, 6], number[:, 7]
    if time[-1] < 1.0e-9:
        raise ValueError(f"{run.name} has only run {time[-1]:.2e} s; the early rates need 1 ns")
    # The wall source delivers a few percent less than the nominal current because the emitter patches
    # are cut cells. Nothing is lost in the first 0.1 ns even at 10 A, so that inventory gives the true rate.
    early = np.searchsorted(time, 1.0e-10)
    rate = electrons[early] / time[early]
    # Low-current runs lose nothing before 1 ns, the time to cross the device. A net fill rate below the
    # emission rate before then means electrons are going straight back into the wall at the emitters.
    start, cross = np.interp([3.0e-10, 1.0e-9], time, electrons)
    kept_early = (cross - start) / 7.0e-10 / rate
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
    _, ion_radial = histogram(run, "irad")
    ion_tail = ion_radial[-1]
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
        # Only a run whose DONE file reads "complete" counts as a result.
        "status": (run / "DONE").read_text().strip() if (run / "DONE").exists() else "running",
        "coil_at": c["coil_at"], "current_A": c["current"], "vgrid_V": c["vgrid"], "ncell": c["ncell"],
        "a_m": c["a"], "wall_V": c["wall_v"], "emitter_eV": c["eb0"], "emitter_radius_m": c["gun_r"], "toff_ns": 1e9 * c["toff"],
        "end_ns": round(time[-1] * 1e9, 2),
        "emitted_A": round(rate * Q_E, 4),
        "kept_early": round(float(kept_early), 3),
        "electrons": float(electrons[-1]),
        "gas_per_m3": c["ngas"],
        "ions": float(ions[-1]),
        "ions_inside_half_a": round(float(ion_tail[bins < 0.5 * c["a"]].sum() / max(ion_tail.sum(), 1e-300)), 4),
        "ions_inside_cage": round(float(ion_tail[bins < 1.3 * c["a"]].sum() / max(ion_tail.sum(), 1e-300)), 4),
        "dwell_ns": round(electrons[-1] / rate * 1e9, 3),
        "filling": round(float(growth), 3),
        "centre_V_empty": round(centre[steps[0]], 1),
        "centre_V": round(centre[steps[-1]], 1),
        "centre_V_min": round(min(centre.values()), 1),
        "well_V": round(centre[steps[0]] - centre[steps[-1]], 1),
        "axis_V_at_half_a_and_a": [round(at((r, final), x), 1) for x in (0.5 * c["a"], c["a"])],
        "edge_V_at_half_a_and_a": [round(at(edge, x), 1) for x in (0.5 * c["a"], c["a"])],
        "corner_V_at_half_a_and_a": [round(at(corner, x), 1) for x in (0.5 * c["a"], c["a"])],
        "inside_half_a": round(float(tail[bins < 0.5 * c["a"]].sum() / max(tail.sum(), 1e-300)), 4),
        "inside_cage": round(float(tail[bins < 1.3 * c["a"]].sum() / max(tail.sum(), 1e-300)), 4),
        "core_mean_eV": round(float((core * energy_bins).sum() / max(core.sum(), 1e-300)), 1),
        "outside_on_axis": round(float(out[cosine > 0.95].sum() / max(out.sum(), 1e-300)), 3),
        "outside_share": round(float(out.sum() / max(tail.sum(), 1e-300)), 4),
        **shell_currents(run, time, electrons),
    }


if __name__ == "__main__":
    for path in sys.argv[1:]:
        run = Path(path)
        if (run / "diags/reducedfiles/number.txt").exists():
            print(json.dumps(reduce(run)))
