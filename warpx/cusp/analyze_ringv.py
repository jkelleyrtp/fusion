"""Reduce runs of the inputs_3d_cusp_ringv decks to one JSON line each.

    python3 analyze_ringv.py RUN_DIR [RUN_DIR ...]

To what analyze_beta.py measures, this adds the voltage of the rings above the wall, the charge the plasma has
put on the rings, and where the plasma lands: how many electrons and ions per second reach the rings, the rods
and the wall, and the power they carry there.

The unit deck (rings at 1 V in vacuum, one step) is not a plasma run. For it this moves the field's sample
points to where WarpX's reader expects them and reports the voltage the probes read, which should be 1 V.
"""

import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from analyze_beta import constants, table
from analyze_cage import M_E

C = 299792458.0
PROBE_POINTS = 401  # points along each voltage line (`resolution` in make_deck.RINGV)
LINES = ("vxp", "vyp", "vzp")


def ring_voltages(run: Path) -> tuple[np.ndarray, np.ndarray]:
    """Time (s) and the voltage (V) of three rings above the wall: the electric field summed along a line from
    inside each ring's metal to inside the wall's."""
    volts = []
    for name in LINES:
        rows = table(run, name, PROBE_POINTS)
        rows = rows[: len(rows) // PROBE_POINTS * PROBE_POINTS].reshape(-1, PROBE_POINTS, rows.shape[1])
        place, field = rows[:, :, 2:5], rows[:, :, 5:8]
        volts.append(np.sum(0.5 * (field[:, 1:] + field[:, :-1]) * np.diff(place, axis=1), axis=(1, 2)))
        time = rows[:, 0, 1]
    count = min(map(len, volts))
    return time[:count], np.array([v[:count] for v in volts])


def surface(place: np.ndarray, c: dict, cell: float) -> np.ndarray:
    """Which metal each landing point is on: 0 a ring, 1 the wall, 2 anything else (the rods)."""
    a = c["a"]
    nearest = np.full(len(place), np.inf)
    for axis in range(3):
        u, v = place[:, (axis + 1) % 3], place[:, (axis + 2) % 3]
        for sign in (1, -1):
            nearest = np.minimum(nearest, np.hypot(np.hypot(u, v) - a, place[:, axis] - sign * 1.3 * a) - c["rm"])
    out = np.full(len(place), 2)
    out[np.linalg.norm(place, axis=1) > c["rw"] - 1.5 * cell] = 1
    out[nearest < 1.5 * cell] = 0
    return out


def column(node) -> np.ndarray:
    """One stored quantity of every particle. openPMD stores a quantity that is the same for all of them, or a
    species with no particles, as a single value and a count."""
    return node[:] if hasattr(node, "shape") else np.full(node.attrs["shape"], node.attrs["value"])


def landed(run: Path, c: dict, since_step: float, seconds: float) -> dict:
    """Particles per second and watts reaching each metal surface after `since_step`, from the particles WarpX
    wrote as they landed. Kept in landed.json, because the files it is made from are large and are removed."""
    kept = run / "landed.json"
    files = sorted((run / "diags/scr/particles_at_eb").glob("*.h5")) if (run / "diags/scr").exists() else []
    if not files:
        return json.loads(kept.read_text()) if kept.exists() else {}
    import h5py

    cell = 5 * c["a"] / c["ncell"]
    masses = {"electrons": M_E, "ions": c["mass_amu"] * 1.66053906660e-27}
    names = ("rings", "wall", "rods")
    rate = {f"{species}_per_s_on_{name}": 0.0 for species in masses for name in names}
    power = {f"{species}_W_on_{name}": 0.0 for species in masses for name in names}
    for path in files:
        with h5py.File(path, "r") as file:
            for step, iteration in file["data"].items():
                # Each file holds what landed in the scr_every steps up to its own.
                if int(step) <= since_step:
                    continue
                for species, mass in masses.items():
                    group = iteration["particles"].get(species)
                    if group is None or "position" not in group:
                        continue
                    place = np.stack([column(group["position"][k]) + column(group["positionOffset"][k]) for k in "xyz"], axis=1)
                    momentum = np.stack([column(group["momentum"][k]) for k in "xyz"], axis=1)
                    # Only a random share of them was written, so each stands for 1/share.
                    weight = column(group["weighting"]) / c["scr_keep"]
                    energy = (np.sqrt(1 + np.sum(momentum**2, axis=1) / (mass * C) ** 2) - 1) * mass * C * C
                    where = surface(place, c, cell)
                    for index, name in enumerate(names):
                        rate[f"{species}_per_s_on_{name}"] += float(weight[where == index].sum()) / seconds
                        power[f"{species}_W_on_{name}"] += float((weight * energy)[where == index].sum()) / seconds
    out = {key: float(f"{value:.4g}") for key, value in {**rate, **power}.items()}
    kept.write_text(json.dumps(out) + "\n")
    shutil.rmtree(run / "diags/scr")
    return out


def fix_unit_map(run: Path) -> dict:
    """WarpX writes a field at cell centres but, reading one, places the samples from the box's corner. Move the
    stated corner half a cell, once, so the field is read back where it was written."""
    import h5py

    path = max((run / "diags/unit").glob("*.h5"))
    with h5py.File(path, "r+") as file:
        field = next(iter(file["data"].values()))["fields/E"]
        # Each component says where in its cell it sits: half a cell in as written, zero once moved.
        if np.any(field["x"].attrs["position"]):
            field.attrs["gridGlobalOffset"] = field.attrs["gridGlobalOffset"] + 0.5 * field.attrs["gridSpacing"]
            for k in "xyz":
                field[k].attrs["position"] = np.zeros(3)
        shape = list(field["x"].shape)
    _, volts = ring_voltages(run)
    return {"map": str(path.resolve()), "cells": shape, "ring_V_read_by_probes": [round(float(v[-1]), 4) for v in volts]}


def echoed(text: str) -> dict[str, float]:
    """The sizes the landing counts need, from the inputs WarpX echoes with each constant's value after a #.
    WarpX echoes only the constants a deck uses, so the rod radius, which nothing here needs, is not asked for:
    decks without rods do not have it."""
    return {name: float(re.search(rf"^my_constants\.{name} = .*# (\S+)$", text, re.MULTILINE).group(1)) for name in ("rm", "rw", "scr_keep")}


def reduce(run: Path) -> dict:
    text = (run / "warpx_used_inputs").read_text()
    complete = (run / "DONE").exists() and (run / "DONE").read_text().strip() == "complete"
    if re.search(r"^unit\.diag_type", text, re.MULTILINE):
        return {"run": run.resolve().name, "complete": complete, **fix_unit_map(run)}
    import analyze_beta

    out = analyze_beta.reduce(run)
    c = constants(run)
    c.update(echoed(text))
    applied = re.search(r"^particles\.read_fields_E_dependency\(t\) = (\S+)", text, re.MULTILINE)
    out["rings_set_to_kV"] = float(applied.group(1)) / 1e3 if applied else None
    out["rods"] = "none" if "min(rs*rs" not in text else ("stop short of the rings" if "(dc+rm+" in text else "join rings to wall")
    time, volts = ring_voltages(run)
    if len(time) > 1:
        late = time >= 0.8 * time[-1]
        out["ring_kV_late"] = [round(float(v[late].mean()) / 1e3, 1) for v in volts]
        out["ring_kV_late_spread"] = [round(float(v[late].std()) / 1e3, 1) for v in volts]
        charge = table(run, "qring")
        out["ring_charge_from_plasma_late_nC"] = round(float(charge[charge[:, 1] >= 0.8 * time[-1], 2].mean()) * 1e9, 2)
        out.update(landed(run, c, 0.8 * time[-1] / c["dt"], 0.2 * time[-1]))
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps(reduce(Path(path))))
