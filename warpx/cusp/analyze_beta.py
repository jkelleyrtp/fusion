#!/usr/bin/env python3
"""Reduce plasma-ball runs of inputs_3d_cusp_beta to one JSON line each.

    python3 analyze_beta.py RUN_DIR [RUN_DIR ...]

Each line says how much of the plasma is left, how fast it is leaving, how wide the stream through a coil
opening is, and how far the plasma has changed the magnetic field from the coil field.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
from analyze_cage import M_E, MU0, Q_E, coil_field


def constants(run: Path) -> dict:
    """The my_constants values this run used, and whether it solved the full fields or only the charge."""
    text = (run / "warpx_used_inputs").read_text()
    names = ("a", "coil_at", "n0", "r0", "te", "ti", "mass_amu", "dt", "ncell", "ppd")
    # WarpX echoes each constant followed by a comment holding its evaluated value.
    out = {name: float(re.search(rf"^my_constants\.{name} = .*# (\S+)$", text, re.MULTILINE).group(1)) for name in names}
    out["charge_only"] = bool(re.search(r"^warpx\.do_electrostatic = labframe", text, re.MULTILINE))
    return out


def table(run: Path, name: str) -> np.ndarray:
    return np.loadtxt(run / f"diags/reducedfiles/{name}.txt", skiprows=1, ndmin=2)


def bin_centres(run: Path, name: str) -> np.ndarray:
    header = (run / f"diags/reducedfiles/{name}.txt").read_text().split("\n", 1)[0]
    return np.array([float(value) for value in re.findall(r"bin\d+=([-\d.e+]+)\(\)", header)])


def stream_half_width(run: Path, name: str, since: float) -> float:
    """Distance from the coil axis (m) at which the density in the coil plane falls to half its peak, going
    outward from the peak, averaged from time `since` on. The histogram counts particles per ring of radius;
    dividing by the radius turns that into a density. Bins are merged in fives (0.5 mm) to steady the count
    near the axis, where the rings are small."""
    data = table(run, name)
    radius = bin_centres(run, name).reshape(-1, 5).mean(axis=1)
    density = (data[data[:, 1] >= since, 2:].mean(axis=0) / bin_centres(run, name)).reshape(-1, 5).mean(axis=1)
    if density.max() <= 0:
        return float("nan")
    top = int(np.argmax(density))
    below = np.nonzero(density[top:] < 0.5 * density[top])[0]
    if not len(below):
        return float("nan")
    # Interpolate between the last bin above half and the first below it.
    k = top + below[0]
    return float(np.interp(0.5 * density[top], [density[k], density[k - 1]], [radius[k], radius[k - 1]]))


def outside_shares(run: Path, name: str, since: float) -> dict:
    """Of the particles beyond 1.9 a, the share heading out along a coil axis and toward a cube corner. A cloud
    leaving evenly in all directions would give 0.15 and 0.03."""
    data, direction = table(run, name), bin_centres(run, name)
    weight = data[data[:, 1] >= since, 2:].mean(axis=0)
    total = max(weight.sum(), 1e-300)
    return {"on_axis": round(float(weight[direction >= 0.95].sum() / total), 3),
            "at_corner": round(float(weight[direction < 0.65].sum() / total), 3)}


def loss_time_ns(time: np.ndarray, count: np.ndarray) -> float | None:
    """Count over loss rate across the last fifth of the run, or None if nothing is being lost."""
    late = time >= 0.8 * time[-1]
    rate = -np.polyfit(time[late], count[late], 1)[0]
    return round(float(count[late].mean() / rate * 1e9), 1) if rate > 0 else None


def field_change(run: Path, c: dict, line: str) -> dict:
    """How the field along a probe line at the last snapshot differs from the coil field alone."""
    data = table(run, line)
    last = data[data[:, 0] == data[:, 0].max()]
    points = last[:, 2:5]
    radius = np.linalg.norm(points, axis=1)
    order = np.argsort(radius)
    points, radius, own = points[order], radius[order], last[order, 8:11]
    coils = coil_field(points, c["coil_at"], c["a"])
    total = np.linalg.norm(coils + own, axis=1)
    alone = np.linalg.norm(coils, axis=1)
    inside = radius < 1.2 * c["a"]
    weakest = np.argmin(np.where(inside & (alone > 0.02 * alone[inside].max()), total / np.maximum(alone, 1e-30), np.inf))
    return {
        "own_field_max_T": round(float(np.linalg.norm(own[inside], axis=1).max()), 4),
        "largest_cut": round(float(1 - total[weakest] / alone[weakest]), 3),
        "largest_cut_at_r_over_a": round(float(radius[weakest] / c["a"]), 2),
    }


def pressure_history(run: Path, c: dict) -> dict:
    """Plasma pressure over the coil field's magnetic pressure, through the run, at the start and at a quarter,
    half and the end of it. The density is the average over a shell of radius r, from the radial histograms.
    The temperature is two thirds of the mean kinetic energy of all particles of that species still in the box,
    so it counts the outward flow as heat and reads high once the ball is expanding. The magnetic pressure uses
    the coil field's root-mean-square over the same shell. `balance_radius` is the largest radius at which the
    ratio is still above 1: inside it the plasma out-pushes the coil field."""
    number, energy = table(run, "number"), table(run, "energy")
    radius = bin_centres(run, "erad")
    volume = 4 * np.pi * radius**2 * (radius[1] - radius[0])
    # 200 directions spread evenly over the sphere
    k = np.arange(200) + 0.5
    polar, turn = np.arccos(1 - 2 * k / 200), np.pi * (1 + 5**0.5) * k
    directions = np.stack([np.sin(polar) * np.cos(turn), np.sin(polar) * np.sin(turn), np.cos(polar)], axis=1)
    magnetic = np.array([(coil_field(r * directions, c["coil_at"], c["a"]) ** 2).sum(axis=1).mean() for r in radius]) / (2 * MU0)
    pressure = 0
    for name, count, joules in (("erad", number[:, 6], energy[:, 3]), ("irad", number[:, 7], energy[:, 4])):
        data = table(run, name)
        each = np.interp(data[:, 1], energy[:, 1], joules) / np.maximum(np.interp(data[:, 1], number[:, 1], count), 1e-300)
        pressure = pressure + data[:, 2:] / volume * (2 / 3 * each)[:, None]
    times = table(run, "erad")[:, 1]
    out = {"balance_radius_over_a": [], "pressure_ratio_at_a": [], "pressure_ratio_at_coil_opening_now": []}
    for fraction in (0, 0.25, 0.5, 1):
        ratio = pressure[np.argmin(np.abs(times - fraction * times[-1]))] / magnetic
        above = np.nonzero(ratio > 1)[0]
        out["balance_radius_over_a"].append(round(float(radius[above[-1]] / c["a"]), 2) if len(above) else 0.0)
        out["pressure_ratio_at_a"].append(float(f"{np.interp(c['a'], radius, ratio):.3g}"))
        out["pressure_ratio_at_coil_opening_now"].append(float(f"{np.interp(1.3 * c['a'], radius, ratio):.3g}"))
    return out


def reduce(run: Path) -> dict:
    c = constants(run)
    number, energy, fields = table(run, "number"), table(run, "energy"), table(run, "fields")
    time, electrons, ions = number[:, 1], number[:, 6], number[:, 7]
    throat_field = float(np.linalg.norm(coil_field(np.array([[1.3 * c["a"], 0, 0]]), c["coil_at"], c["a"])))
    edge_field = float(np.linalg.norm(coil_field(np.array([[c["r0"], 0, 0]]), c["coil_at"], c["a"])))
    pressure = c["n0"] * (c["te"] + c["ti"]) * Q_E
    gyroradius = np.sqrt(2 * c["te"] * Q_E * M_E) / (Q_E * max(throat_field, 1e-30))
    out = {
        "run": run.name,
        "complete": (run / "DONE").exists() and (run / "DONE").read_text().strip() == "complete",
        "n0_per_m3": c["n0"],
        "ion_mass_amu": c["mass_amu"],
        "ion_temperature_eV": c["ti"],
        "coil_kAt": c["coil_at"] / 1e3,
        "ncell": int(c["ncell"]),
        "charge_only": c["charge_only"],
        "end_ns": round(float(time[-1] * 1e9), 2),
        # pressure of the starting ball over the magnetic pressure of the coil field, at two places
        "pressure_ratio_at_coil_opening": round(pressure / (throat_field**2 / (2 * MU0)), 4) if c["coil_at"] else None,
        "pressure_ratio_at_ball_edge": round(pressure / (edge_field**2 / (2 * MU0)), 3) if c["coil_at"] else None,
        "electrons_left": round(float(electrons[-1] / electrons[0]), 4),
        "ions_left": round(float(ions[-1] / ions[0]), 4),
        "electron_loss_time_ns": loss_time_ns(time, electrons),
        "ion_loss_time_ns": loss_time_ns(time, ions),
        "electron_energy_left": round(float(energy[-1, 3] / energy[0, 3]), 3),
        "ion_energy_over_start": round(float(energy[-1, 4] / energy[0, 4]), 3),
        "own_magnetic_energy_over_plasma": float(f"{fields[-1, 4] / energy[0, 2]:.3e}"),
        "electron_stream_half_width_mm": round(stream_half_width(run, "ethroat", 0.7 * time[-1]) * 1e3, 3),
        "ion_stream_half_width_mm": round(stream_half_width(run, "ithroat", 0.7 * time[-1]) * 1e3, 3),
        "electron_orbit_at_coil_opening_mm": round(float(gyroradius * 1e3), 3) if c["coil_at"] else None,
    }
    for line in ("axis", "edge", "corner") if c["coil_at"] else ():
        out.update({f"{line}_{key}": value for key, value in field_change(run, c, line).items()})
    if c["coil_at"]:
        out.update(pressure_history(run, c))
    for name, species in (("eout", "electrons"), ("iout", "ions")):
        out.update({f"{species}_outside_{key}": value for key, value in outside_shares(run, name, 0.6 * time[-1]).items()})
    for name, species in (("erad", "electron"), ("irad", "ion")):
        data, radius = table(run, name), bin_centres(run, name)
        share = data[-1, 2:] / max(data[-1, 2:].sum(), 1e-300)
        out[f"{species}_mean_radius_over_a"] = round(float((share * radius).sum() / c["a"]), 3)
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps(reduce(Path(path))))
