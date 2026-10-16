#!/usr/bin/env python3
"""Reduce fed spindle-cusp runs of inputs_rz_spindle_fed to one JSON line each.

    python3 analyze_spindle.py RUN_DIR [RUN_DIR ...]

Each line says how much plasma is held, how fast it leaves through the two coils and through the gap between
them, how wide those two leaks are next to an electron orbit there, and how far the plasma has pushed the
magnetic field out of the middle.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
from analyze_cage import M_E, MU0, Q_E

from analyze_beta import bin_centres, table

C = 299792458.0


def constants(run: Path) -> dict:
    text = (run / "warpx_used_inputs").read_text()
    names = ("a", "dc", "rc", "rw", "zw", "coil_at", "te", "ti", "mass_amu", "feed", "toff", "nr", "shell", "n0")
    # WarpX echoes each constant followed by a comment holding its evaluated value.
    return {name: float(re.search(rf"^my_constants\.{name} = .*# (\S+)$", text, re.MULTILINE).group(1)) for name in names}


def coil_field(r: np.ndarray, z: np.ndarray, c: dict) -> tuple[np.ndarray, np.ndarray]:
    """Radial and axial field (T) of the two coils at points (r, z), summed by Biot-Savart."""
    angle = (np.arange(360) + 0.5) * np.pi / 180
    radial, axial = np.zeros_like(r, dtype=float), np.zeros_like(r, dtype=float)
    for sign in (1, -1):
        u = (z - sign * c["dc"])[..., None]
        gap = (r[..., None] ** 2 + c["rc"] ** 2 + u**2 - 2 * r[..., None] * c["rc"] * np.cos(angle)) ** 1.5
        # The coil at +dc carries current in the negative sense, so that both point their field at the centre.
        scale = -sign * MU0 * c["coil_at"] * c["rc"] / (4 * np.pi) * (np.pi / 180)
        radial += scale * (u * np.cos(angle) / gap).sum(axis=-1)
        axial += scale * ((c["rc"] - r[..., None] * np.cos(angle)) / gap).sum(axis=-1)
    return radial, axial


def half_width(position: np.ndarray, density: np.ndarray) -> float:
    """Position at which the density falls to half its peak, going outward from the peak."""
    if density.max() <= 0:
        return float("nan")
    top = int(np.argmax(density))
    below = np.nonzero(density[top:] < 0.5 * density[top])[0]
    if not len(below):
        return float("nan")
    k = top + below[0]
    return float(np.interp(0.5 * density[top], [density[k], density[k - 1]], [position[k], position[k - 1]]))


def leaving(run: Path, name: str, shell: float) -> tuple[np.ndarray, np.ndarray]:
    """(time, particles leaving per second) through one of the two counting shells."""
    data = table(run, name)
    return data[:, 1], (data[:, 2:] * bin_centres(run, name)).sum(axis=1) * C / shell


def field_maps(run: Path) -> dict | None:
    """The fields in the last snapshot, as arrays over (z, r), or None if the run wrote no snapshot in one box."""
    files = sorted(p for p in (run / "diags").glob("diag1[0-9]*") if (p / "Level_0/Cell_D_00000").exists())
    if not files or (run / "diags" / files[-1].name / "Level_0/Cell_D_00001").exists():
        return None
    header = (files[-1] / "Header").read_text().split("\n")
    names = header[2 : 2 + int(header[1])]
    with open(files[-1] / "Level_0/Cell_D_00000", "rb") as data:
        high = data.readline().decode().split(") (")[1].split(")")[0]
        nr, nz = (int(value) + 1 for value in high.split(","))
        cube = np.frombuffer(data.read(len(names) * nr * nz * 8), dtype="<f8").reshape(len(names), nz, nr)
    return dict(zip(names, cube))


def pushed_out(run: Path, c: dict) -> dict:
    """How the field in the last snapshot differs from the coil field alone. The weak-field volume is where the
    field is under a tenth of the coil field at the middle of a coil; a plasma that pushes the field out makes
    that volume larger than the coils alone do."""
    maps = field_maps(run)
    if maps is None:
        return {}
    nz, nr = maps["Br"].shape
    stride = max(1, nr // 128)
    r = ((np.arange(nr) + 0.5) * c["rw"] / nr)[::stride]
    z = ((np.arange(nz) + 0.5) * 2 * c["zw"] / nz - c["zw"])[::stride]
    grid_r, grid_z = np.meshgrid(r, z)
    coil_r, coil_z = coil_field(grid_r, grid_z, c)
    alone = np.hypot(coil_r, coil_z)
    total = np.sqrt((coil_r + maps["Br"][::stride, ::stride]) ** 2 + (coil_z + maps["Bz"][::stride, ::stride]) ** 2
                    + maps["Bt"][::stride, ::stride] ** 2)
    reference = float(np.hypot(*coil_field(np.array([0.0]), np.array([c["dc"]]), c))[0])
    inside = (grid_r < c["rc"]) & (np.abs(grid_z) < c["dc"])
    volume = 2 * np.pi * grid_r * (r[1] - r[0]) * (z[1] - z[0])
    weak_alone = volume[inside & (alone < 0.1 * reference)].sum()
    weak_now = volume[inside & (total < 0.1 * reference)].sum()
    strong = inside & (alone > 0.2 * reference) & (np.hypot(grid_r - c["rc"], np.abs(grid_z) - c["dc"]) > 0.3 * c["a"])
    return {
        "weak_field_volume_over_coils_alone": round(float(weak_now / weak_alone), 3),
        "largest_cut_in_field": round(float((1 - total[strong] / alone[strong]).max()), 3),
        "own_field_max_T": round(float(np.hypot(maps["Br"], maps["Bz"]).max()), 4),
        "own_field_around_axis_max_T": round(float(np.abs(maps["Bt"]).max()), 4),
    }


def reduce(run: Path) -> dict:
    c = constants(run)
    number, energy = table(run, "number"), table(run, "energy")
    time, held = number[:, 1], {"electrons": number[:, 6], "ions": number[:, 7]}
    fed_until = min(time[-1], c["toff"])
    late = (time >= 0.8 * fed_until) & (time <= fed_until)
    recorded = table(run, "e_rad")[:, 1]
    assert ((recorded >= 0.8 * fed_until) & (recorded <= fed_until)).sum() >= 4, "under four histograms in the last fifth of the feed"
    field_in_coil = float(np.hypot(*coil_field(np.array([0.0]), np.array([c["dc"]]), c))[0])
    field_in_gap = float(np.hypot(*coil_field(np.array([c["rc"]]), np.array([0.0]), c))[0])
    orbit = np.sqrt(2 * c["te"] * Q_E * M_E) / Q_E
    out = {
        "run": run.resolve().name,
        "complete": (run / "DONE").exists() and (run / "DONE").read_text().strip() == "complete",
        "coil_kAt": c["coil_at"] / 1e3,
        "feed_per_s": c["feed"],
        "ion_mass_amu": c["mass_amu"],
        "cells_across_radius": int(c["nr"]),
        "end_ns": round(float(time[-1] * 1e9), 2),
        "feed_stops_ns": round(c["toff"] * 1e9, 2) if c["toff"] < time[-1] else None,
        "field_in_coil_T": round(field_in_coil, 4),
        "field_in_gap_T": round(field_in_gap, 4),
        "electron_orbit_in_coil_mm": round(float(orbit / max(field_in_coil, 1e-30) * 1e3), 4) if c["coil_at"] else None,
        "electron_orbit_in_gap_mm": round(float(orbit / max(field_in_gap, 1e-30) * 1e3), 4) if c["coil_at"] else None,
        "cell_mm": round(c["rw"] / c["nr"] * 1e3, 4),
    }
    for index, (species, counts) in enumerate(held.items()):
        letter = species[0]
        out[f"{species}_held_late_in_feed"] = float(f"{counts[late].mean():.4g}")
        rates = {}
        for route in ("coils", "gap"):
            when, rate = leaving(run, f"{letter}_through_{route}", c["shell"])
            rates[route] = float(rate[(when >= 0.8 * fed_until) & (when <= fed_until)].mean())
        total = rates["coils"] + rates["gap"]
        out[f"{species}_leaving_per_s"] = float(f"{total:.4g}")
        out[f"{species}_share_leaving_through_coils"] = round(rates["coils"] / total, 3) if total > 0 else None
        out[f"{species}_holding_time_ns"] = round(float(counts[late].mean() / total * 1e9), 2) if total > 0 else None
        # Mean energy late in the feed, and the pressure that gives the plasma within half a coil radius of the centre.
        each = float((energy[late, 3 + index] / np.maximum(counts[late], 1e-300)).mean())
        out[f"{species}_mean_energy_eV"] = round(each / Q_E, 1)
        data, radius = table(run, f"{letter}_rad"), bin_centres(run, f"{letter}_rad")
        recent = (data[:, 1] >= 0.8 * fed_until) & (data[:, 1] <= fed_until)
        core = data[recent, 2:].mean(axis=0)[radius < 0.5 * c["rc"]].sum() / (4 / 3 * np.pi * (0.5 * c["rc"]) ** 3)
        out[f"{species}_core_density_per_m3"] = float(f"{core:.4g}")
        out.setdefault("core_pressure_Pa", 0.0)
        out["core_pressure_Pa"] += core * 2 / 3 * each
        for where, value in (("coil", "radius"), ("gap", "height")):
            data, position = table(run, f"{letter}_in_{where}"), bin_centres(run, f"{letter}_in_{where}")
            profile = data[(data[:, 1] >= 0.8 * fed_until) & (data[:, 1] <= fed_until), 2:].mean(axis=0)
            # Counts per ring of radius become a density on dividing by the radius; the gap's bins are equal in volume.
            profile = profile / position if where == "coil" else profile
            merged = slice(None, len(position) // 4 * 4)
            out[f"{species[:-1]}_stream_half_{value}_in_{where}_mm"] = round(half_width(
                position[merged].reshape(-1, 4).mean(axis=1), profile[merged].reshape(-1, 4).mean(axis=1)) * 1e3, 4)
    if c["coil_at"]:
        out["core_pressure_over_magnetic_in_coil"] = float(f"{out['core_pressure_Pa'] / (field_in_coil**2 / (2 * MU0)):.3g}")
        out["core_pressure_over_magnetic_in_gap"] = float(f"{out['core_pressure_Pa'] / (field_in_gap**2 / (2 * MU0)):.3g}")
        out.update(pushed_out(run, c))
    out["core_pressure_Pa"] = float(f"{out['core_pressure_Pa']:.4g}")
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps(reduce(Path(path))))
