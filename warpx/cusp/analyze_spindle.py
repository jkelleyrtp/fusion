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
from analyze_cage import C_LIGHT, M_E, MU0, Q_E

M_U = 1.66053906660e-27

from analyze_beta import bin_centres, field_and_charge, table

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


def pressure_per_particle(mean_energy: float, mass: float) -> float:
    """Pressure over number density (J) of particles of this mean kinetic energy (J): a third of momentum times speed.

    Two thirds of the energy for slow particles, falling towards one third for fast ones; taken at the mean
    energy, not averaged over the spread. For 100 keV electrons it is 8% below two thirds.
    """
    rest = mass * C_LIGHT**2
    return mean_energy * (mean_energy + 2 * rest) / (mean_energy + rest) / 3


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


def merge(position: np.ndarray, profile: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Average neighbouring bins in fours."""
    whole = slice(None, len(position) // 4 * 4)
    return position[whole].reshape(-1, 4).mean(axis=1), profile[whole].reshape(-1, 4).mean(axis=1)


def orbit_times_field(energy_eV: float) -> float:
    """Orbit radius times field (T m) of an electron of this kinetic energy: its momentum over its charge.

    The second term is the correction for speeds near that of light: 5% at 100 keV, under 1% at 10 keV.
    """
    energy = energy_eV * Q_E
    return float(np.sqrt(2 * energy * M_E + (energy / C_LIGHT) ** 2) / Q_E)


def stream_through_coil(radius: np.ndarray, count: np.ndarray, cell: float) -> dict:
    """Width of the stream through a coil, from the number of particles counted in each ring of radius.

    Within two cells of the axis the density is a spike (or, with the coils off, a dip) a cell wide sitting on a
    stream millimetres across. The half-width is taken from outside it, and its height is reported separately.
    """
    density = count / radius
    place, merged = merge(radius, density)
    nearby = (radius > 2 * cell) & (radius < 6 * cell)
    return {
        "stream_half_radius_in_coil_mm": round(half_width(place[place > 2 * cell], merged[place > 2 * cell]) * 1e3, 4),
        "stream_radius_holding_half_in_coil_mm": round(
            float(np.interp(0.5, np.cumsum(count) / max(count.sum(), 1e-300), radius)) * 1e3, 4),
        "density_on_axis_over_nearby_in_coil": round(
            float(density[radius < cell].mean() / max(density[nearby].mean(), 1e-300)), 2),
    }


def leaving(run: Path, name: str, shell: float) -> tuple[np.ndarray, np.ndarray]:
    """(time, particles leaving per second) through one of the two counting shells."""
    data = table(run, name)
    return data[:, 1], (data[:, 2:] * bin_centres(run, name)).sum(axis=1) * C / shell


def field_maps(run: Path) -> dict | None:
    """The fields in the last snapshot, as arrays over (z, r), or None if the run wrote no snapshot. A run on
    several GPUs writes its mesh in several boxes, each placed here by the corners it records."""
    files = sorted((p for p in (run / "diags").glob("diag1[0-9]*") if (p / "Level_0/Cell_H").exists()), key=lambda p: int(p.name[5:]))
    if not files:
        return None
    header = (files[-1] / "Header").read_text().split("\n")
    names = header[2 : 2 + int(header[1])]
    nr, nz = (int(value) + 1 for value in header[len(names) + 8].split(") (")[1].split(")")[0].split(","))
    cube = np.empty((len(names), nz, nr))
    for name, offset in re.findall(r"FabOnDisk: (\S+) (\d+)", (files[-1] / "Level_0/Cell_H").read_text()):
        with open(files[-1] / "Level_0" / name, "rb") as data:
            data.seek(int(offset))
            r0, z0, r1, z1 = (int(edge) for edge in re.search(r"\(\((\d+),(\d+)\) \((\d+),(\d+)\)", data.readline().decode()).groups())
            shape = (len(names), z1 - z0 + 1, r1 - r0 + 1)
            cube[:, z0 : z1 + 1, r0 : r1 + 1] = np.frombuffer(data.read(8 * int(np.prod(shape))), dtype="<f8").reshape(shape)
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
    # With the coil field held on the mesh, the snapshot's field is the coils' plus the plasma's; otherwise the plasma's alone.
    on_mesh = bool(re.search(r"^particles\.B_ext_particle_on_grid = 1", (run / "warpx_used_inputs").read_text(), re.MULTILINE))
    own_r = maps["Br"][::stride, ::stride] - (coil_r if on_mesh else 0)
    own_z = maps["Bz"][::stride, ::stride] - (coil_z if on_mesh else 0)
    total = np.sqrt((coil_r + own_r) ** 2 + (coil_z + own_z) ** 2 + maps["Bt"][::stride, ::stride] ** 2)
    reference = float(np.hypot(*coil_field(np.array([0.0]), np.array([c["dc"]]), c))[0])
    inside = (grid_r < c["rc"]) & (np.abs(grid_z) < c["dc"])
    volume = 2 * np.pi * grid_r * (r[1] - r[0]) * (z[1] - z[0])
    weak_alone = volume[inside & (alone < 0.1 * reference)].sum()
    weak_now = volume[inside & (total < 0.1 * reference)].sum()
    strong = inside & (alone > 0.2 * reference) & (np.hypot(grid_r - c["rc"], np.abs(grid_z) - c["dc"]) > 0.3 * c["a"])
    return {
        "weak_field_volume_over_coils_alone": round(float(weak_now / weak_alone), 3),
        "largest_cut_in_field": round(float((1 - total[strong] / alone[strong]).max()), 3),
        # Away from the coil conductors, where the mesh cannot follow the coil field and the difference is not the plasma's.
        "own_field_max_T": round(float(np.hypot(own_r, own_z)[np.hypot(grid_r - c["rc"], np.abs(grid_z) - c["dc"]) > 0.3 * c["a"]].max()), 4),
        "own_field_around_axis_max_T": round(float(np.abs(maps["Bt"]).max()), 4),
    }


def each_leak(run: Path, c: dict, fed_until: float, lost_per_s: dict[str, float]) -> dict:
    """For runs of inputs_rz_spindle_leak: which leaks are open, the plasma held inside the coils (a closed leak
    parks plasma between itself and its wall, which the vessel total counts), the holding time that gives, the
    net rate crossing each leak at the leak, and whether the run has settled."""
    text = (run / "warpx_used_inputs").read_text()
    low, high = (re.search(rf"^boundary\.particle_{side} = (\S+) (\S+)", text, re.MULTILINE).groups() for side in ("lo", "hi"))
    out = {"open_leaks": {("absorbing", "absorbing"): "both", ("reflecting", "absorbing"): "coils", ("absorbing", "reflecting"): "gap"}[(high[0], high[1])]}
    assert low[1] == high[1], "the two end walls differ"
    for species in ("electrons", "ions"):
        letter = species[0]
        data, energy = table(run, f"{letter}_core"), bin_centres(run, f"{letter}_core")
        late = (data[:, 1] >= 0.8 * fed_until) & (data[:, 1] <= fed_until)
        before = (data[:, 1] >= 0.6 * fed_until) & (data[:, 1] < 0.8 * fed_until)
        inside = data[:, 2:].sum(axis=1)
        out[f"{species}_held_inside_coils"] = float(f"{inside[late].mean():.4g}")
        out[f"{species}_inside_coils_over_fifth_before"] = round(float(inside[late].mean() / inside[before].mean()), 3)
        out[f"{species}_mean_energy_inside_coils_eV"] = round(float((data[late, 2:] * energy).sum() / inside[late].sum()), 1)
        lost = lost_per_s[species]
        out[f"{species}_leaving_over_feed"] = round(lost / c["feed"], 3)
        out[f"{species}_holding_time_inside_coils_ns"] = round(inside[late].mean() / lost * 1e9, 2) if lost > 0 else None
        for route in ("coils", "gap"):
            when, rate = leaving(run, f"{letter}_at_{route}", c["shell"])
            out[f"{species}_net_out_at_{route}_per_s"] = float(f"{rate[(when >= 0.8 * fed_until) & (when <= fed_until)].mean():.4g}")
    return out


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
    orbit = orbit_times_field(c["te"])
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
        out["core_pressure_Pa"] += core * pressure_per_particle(each, M_E if index == 0 else c["mass_amu"] * M_U)
        for where, value in (("coil", "radius"), ("gap", "height")):
            data, position = table(run, f"{letter}_in_{where}"), bin_centres(run, f"{letter}_in_{where}")
            profile = data[(data[:, 1] >= 0.8 * fed_until) & (data[:, 1] <= fed_until), 2:].mean(axis=0)
            if where == "coil":
                for key, number in stream_through_coil(position, profile, c["rw"] / c["nr"]).items():
                    out[f"{species[:-1]}_{key}"] = number
            else:
                out[f"{species[:-1]}_stream_half_height_in_gap_mm"] = round(half_width(*merge(position, profile)) * 1e3, 4)
    if c["coil_at"]:
        out["core_pressure_over_magnetic_in_coil"] = float(f"{out['core_pressure_Pa'] / (field_in_coil**2 / (2 * MU0)):.3g}")
        out["core_pressure_over_magnetic_in_gap"] = float(f"{out['core_pressure_Pa'] / (field_in_gap**2 / (2 * MU0)):.3g}")
        out.update(pushed_out(run, c))
    out["core_pressure_Pa"] = float(f"{out['core_pressure_Pa']:.4g}")
    if (run / "diags/reducedfiles/e_core.txt").exists():
        out.update(each_leak(run, c, fed_until, {species: out[f"{species}_leaving_per_s"] for species in held}))
    out.update(field_and_charge(run, 0.8 * fed_until, fed_until))
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps(reduce(Path(path))))
