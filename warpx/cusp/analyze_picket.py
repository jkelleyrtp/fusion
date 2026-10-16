#!/usr/bin/env python3
"""Reduce picket-fence runs of inputs_rz_picket_fed to one JSON line each.

    python3 analyze_picket.py RUN_DIR [RUN_DIR ...]

Each line gives what Park et al. 2019 (arXiv:1901.08041) report for the same arrangement: how long the plasma is
held, counted in crossings of the coil diameter at the thermal speed, and how thick the edge of the plasma is in
the plane of a coil, counted in electron orbits in the field there. It adds the width of the stream through a gap.
All are averages over the last fifth of the run.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
from analyze_cage import C_LIGHT, M_E, MU0, Q_E
from analyze_spindle import M_U, half_width, leaving, pressure_per_particle

from analyze_beta import bin_centres, table

NAMES = ("a", "rc", "h", "rw", "zw", "coil_at", "te", "ti", "mass_amu", "feed", "tfill", "sustain", "nr", "shell")


def constants(run: Path) -> dict:
    text = (run / "warpx_used_inputs").read_text()
    # WarpX echoes each constant followed by a comment holding its evaluated value.
    return {name: float(re.search(rf"^my_constants\.{name} = .*# (\S+)$", text, re.MULTILINE).group(1)) for name in NAMES}


def thermal_speed(temperature_eV: float, mass: float) -> float:
    """Speed (m/s) of a particle whose momentum is the spread the deck gives each direction: sqrt(T m)."""
    u = np.sqrt(temperature_eV * Q_E / (mass * C_LIGHT**2))
    return float(C_LIGHT * u / np.sqrt(1 + u * u))


def field_on_coil_plane(run: Path, after: float) -> tuple[np.ndarray, np.ndarray] | None:
    """(radius, field strength) across the plane of the middle coil, averaged over the snapshots later than `after`.

    With the coil field on the mesh, the snapshots hold the coil field and the plasma's together.
    """
    strengths = []
    for snapshot in sorted(p for p in (run / "diags").glob("diag1[0-9]*") if (p / "Level_0/Cell_D_00000").exists()):
        header = (snapshot / "Header").read_text().split("\n")
        names = header[2 : 2 + int(header[1])]
        if float(header[3 + int(header[1])]) < after or (snapshot / "Level_0/Cell_D_00001").exists():
            continue
        with open(snapshot / "Level_0/Cell_D_00000", "rb") as data:
            high = data.readline().decode().split(") (")[1].split(")")[0]
            nr, nz = (int(value) + 1 for value in high.split(","))
            cube = dict(zip(names, np.frombuffer(data.read(len(names) * nr * nz * 8), dtype="<f8").reshape(len(names), nz, nr)))
        middle = slice(nz // 2 - 2, nz // 2 + 2)
        strengths.append(np.sqrt(cube["Br"][middle] ** 2 + cube["Bz"][middle] ** 2 + cube["Bt"][middle] ** 2).mean(axis=0))
    if not strengths:
        return None
    return (np.arange(nr) + 0.5) / nr, np.mean(strengths, axis=0)


def edge(radius: np.ndarray, count: np.ndarray, c: dict) -> dict:
    """Where the plasma ends in the plane of a coil, and over what distance its density falls from 90% to 10% of
    the density inside. Inside is between 0.4 and 0.6 coil radii, beyond the feed and before the edge. Each
    level is taken at the outermost place the density still reaches it, so ripples further in do not count."""
    density = count / radius
    level = density[(radius > 0.4 * c["rc"]) & (radius < 0.6 * c["rc"])].mean()
    place = {}
    for share in (0.9, 0.5, 0.1):
        reached = np.nonzero(density >= share * level)[0]
        if not len(reached) or reached[-1] == len(radius) - 1:
            return {}
        k = reached[-1]
        place[share] = float(np.interp(share * level, [density[k + 1], density[k]], [radius[k + 1], radius[k]]))
    return {"level": float(level), "middle": place[0.5], "thickness": place[0.1] - place[0.9]}


def reduce(run: Path) -> dict:
    c = constants(run)
    number, energy = table(run, "number"), table(run, "energy")
    time = number[:, 1]
    late = time >= 0.8 * time[-1]
    masses = {"electrons": M_E, "ions": c["mass_amu"] * M_U}
    crossing = {species: 2 * c["rc"] / thermal_speed(c["te"] if species == "electrons" else c["ti"], mass)
                for species, mass in masses.items()}
    out = {
        "run": run.resolve().name,
        "complete": (run / "DONE").exists() and (run / "DONE").read_text().strip() == "complete",
        "coil_kAt": c["coil_at"] / 1e3,
        "electron_temperature_eV": c["te"],
        "ion_mass_over_electron": round(masses["ions"] / M_E, 1),
        "cells_across_coil_radius": round(c["nr"] * c["rc"] / c["rw"]),
        "filled_with": float(f"{c['feed'] * c['tfill']:.4g}"),
        "feed_after_filling_per_s": float(f"{c['feed'] * c['sustain']:.4g}"),
        "end_in_electron_crossings": round(float(time[-1] / crossing["electrons"]), 1),
        "filling_in_electron_crossings": round(c["tfill"] / crossing["electrons"], 1),
    }
    pressure = 0.0
    slab = 2 * 0.02 * c["a"]
    for index, (species, mass) in enumerate(masses.items()):
        letter, held = species[0], number[:, 6 + index]
        when, rate = leaving(run, f"{letter}_through_side", c["shell"])
        assert (when >= 0.8 * time[-1]).sum() >= 4, "under four histograms in the last fifth of the run"
        lost = float(rate[when >= 0.8 * time[-1]].mean())
        out[f"{species}_held"] = float(f"{held[late].mean():.4g}")
        out[f"{species}_held_change_over_last_fifth"] = round(float(held[late][-1] / held[late][0] - 1), 3)
        out[f"{species}_leaving_per_s"] = float(f"{lost:.4g}")
        out[f"{species}_holding_time_ns"] = round(float(held[late].mean() / lost * 1e9), 3) if lost > 0 else None
        for name, each in crossing.items():
            out[f"{species}_holding_time_in_{name[:-1]}_crossings"] = round(float(held[late].mean() / lost / each), 1) if lost > 0 else None
        mean_energy = float((energy[late, 3 + index] / np.maximum(held[late], 1e-300)).mean())
        out[f"{species}_mean_energy_eV"] = round(mean_energy / Q_E, 1)
        data, radius = table(run, f"{letter}_line1"), bin_centres(run, f"{letter}_line1")
        found = edge(radius, data[data[:, 1] >= 0.8 * time[-1], 2:].mean(axis=0), c)
        if found:
            width = radius[1] - radius[0]
            density = found["level"] / (2 * np.pi * width * slab)
            out[f"{species}_density_inside_per_m3"] = float(f"{density:.4g}")
            out[f"{species[:-1]}_edge_at_over_coil_radius"] = round(found["middle"] / c["rc"], 4)
            out[f"{species[:-1]}_edge_thickness_mm"] = round(found["thickness"] * 1e3, 4)
            pressure += density * pressure_per_particle(mean_energy, mass)
        if index == 0:
            electron_edge, electron_pressure_each = found, pressure_per_particle(mean_energy, M_E)
        data, height = table(run, f"{letter}_line3"), bin_centres(run, f"{letter}_line3")
        profile = data[data[:, 1] >= 0.8 * time[-1], 2:].mean(axis=0)
        # The gap is centred half-way between the coils; fold the profile about that plane.
        folded = 0.5 * (profile + profile[::-1])[len(profile) // 2 :]
        out[f"{species[:-1]}_stream_half_height_in_gap_mm"] = round(half_width(height[: len(folded)], folded) * 1e3, 4)
    out["pressure_inside_Pa"] = float(f"{pressure:.4g}")
    field = field_on_coil_plane(run, 0.8 * time[-1])
    if field is not None and electron_edge:
        radius, strength = field[0] * c["rw"], field[1]
        middle, thickness = electron_edge["middle"], electron_edge["thickness"]
        at_edge = float(np.interp(middle, radius, strength))
        outside = float(np.interp(middle + thickness, radius, strength))
        # Orbit of an electron with the measured pressure per particle as its temperature: sqrt(T m) / (e B).
        momentum = np.sqrt(electron_pressure_each * M_E)
        out["field_at_edge_T"] = round(at_edge, 4)
        out["field_outside_edge_T"] = round(outside, 4)
        out["electron_orbit_at_edge_mm"] = round(float(momentum / (Q_E * at_edge) * 1e3), 4)
        out["edge_thickness_in_electron_orbits"] = round(float(thickness * Q_E * at_edge / momentum), 2)
        out["coil_radius_in_electron_orbits_at_edge"] = round(float(c["rc"] * Q_E * at_edge / momentum), 1)
        out["pressure_inside_over_magnetic_outside_edge"] = float(f"{pressure / (outside**2 / (2 * MU0)):.3g}")
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps(reduce(Path(path))))
