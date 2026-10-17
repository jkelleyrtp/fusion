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
from analyze_cage import C_LIGHT, EPS0, M_E, MU0, Q_E
from analyze_spindle import M_U, half_width, leaving, pressure_per_particle

from analyze_beta import bin_centres, field_and_charge, table

NAMES = ("a", "rc", "h", "rw", "zw", "coil_at", "te", "ti", "mass_amu", "feed", "tfill", "sustain", "nr", "shell")


def constants(run: Path) -> dict:
    text = (run / "warpx_used_inputs").read_text()
    # WarpX echoes each constant followed by a comment holding its evaluated value.
    return {name: float(re.search(rf"^my_constants\.{name} = .*# (\S+)$", text, re.MULTILINE).group(1)) for name in NAMES}


def thermal_speed(temperature_eV: float, mass: float) -> float:
    """Speed (m/s) of a particle whose momentum is the spread the deck gives each direction: sqrt(T m)."""
    u = np.sqrt(temperature_eV * Q_E / (mass * C_LIGHT**2))
    return float(C_LIGHT * u / np.sqrt(1 + u * u))


def on_coil_plane(run: Path, after: float) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """(radius over the wall's, field strength, current density around the axis) across the plane of the middle
    coil, averaged over the snapshots later than `after`.

    With the coil field on the mesh, the snapshots hold the coil field and the plasma's together. The profiles
    are kept beside the other reduced diagnostics, so a case can be reduced again where its snapshots are not.
    """
    kept = run / "diags/reducedfiles/on_coil_plane.txt"
    rows = []
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
        strength = np.sqrt(cube["Br"][middle] ** 2 + cube["Bz"][middle] ** 2 + cube["Bt"][middle] ** 2).mean(axis=0)
        rows.append((strength, cube["jt"][middle].mean(axis=0)))
    if rows:
        strength, current = np.mean(rows, axis=0)
        np.savetxt(kept, np.column_stack([(np.arange(nr) + 0.5) / nr, strength, current]),
                   header=f"radius over the wall's, field strength (T), current density around the axis (A/m2); {len(rows)} snapshots")
    if not kept.exists():
        return None
    profile = np.loadtxt(kept)
    return profile[:, 0], profile[:, 1], profile[:, 2]


def current_inside(radius: np.ndarray, field_around_axis: np.ndarray, wall: float) -> float:
    """Current (A) along the axis flowing inside 0.7 to 0.8 of the wall's radius, from the field around the axis
    there. That band lies between the plasma's edge and the wall."""
    band = (radius > 0.7 * wall) & (radius < 0.8 * wall)
    return float((2 * np.pi * radius[band] * field_around_axis[band] / MU0).mean())


def along_axis(run: Path, wall: float) -> np.ndarray | None:
    """Rows of (time, current along the axis) from every snapshot. The deck repeats along the axis, so a current
    can flow along the axis and close through the repeat. Kept beside the other reduced diagnostics."""
    kept = run / "diags/reducedfiles/current_along_axis.txt"
    rows = []
    for snapshot in (run / "diags").glob("diag1*"):
        if not snapshot.name[5:].isdigit() or not (snapshot / "Level_0/Cell_D_00000").exists():
            continue
        if (snapshot / "Level_0/Cell_D_00001").exists():
            continue
        header = (snapshot / "Header").read_text().split("\n")
        names = header[2 : 2 + int(header[1])]
        with open(snapshot / "Level_0/Cell_D_00000", "rb") as data:
            high = data.readline().decode().split(") (")[1].split(")")[0]
            nr, nz = (int(value) + 1 for value in high.split(","))
            data.seek(names.index("Bt") * nr * nz * 8, 1)
            around = np.frombuffer(data.read(nr * nz * 8), dtype="<f8").reshape(nz, nr).mean(axis=0)
        rows.append((float(header[3 + int(header[1])]), current_inside((np.arange(nr) + 0.5) / nr * wall, around, wall)))
    if rows:
        np.savetxt(kept, sorted(rows), header="time (s), current along the axis inside 0.7 to 0.8 of the wall's radius (A)")
    return np.atleast_2d(np.loadtxt(kept)) if kept.exists() else None


def current_layer(radius: np.ndarray, current: np.ndarray, near: float, within: float) -> dict:
    """The layer of current at the plasma's edge: where it peaks within `within` of `near`, and its full width
    at half that peak. This is the thickness Park et al. 2019 quote."""
    size = np.abs(current)
    window = np.nonzero(np.abs(radius - near) < within)[0]
    peak = window[np.argmax(size[window])]
    half = 0.5 * size[peak]
    inner = outer = peak
    while inner > 0 and size[inner] >= half:
        inner -= 1
    while outer < len(radius) - 1 and size[outer] >= half:
        outer += 1
    if size[inner] >= half or size[outer] >= half:
        return {}
    low = float(np.interp(half, [size[inner], size[inner + 1]], [radius[inner], radius[inner + 1]]))
    high = float(np.interp(half, [size[outer], size[outer - 1]], [radius[outer], radius[outer - 1]]))
    return {"peak_at": float(radius[peak]), "from": low, "to": high, "width": high - low}


def edge(radius: np.ndarray, count: np.ndarray, c: dict) -> dict:
    """Where the plasma ends in the plane of a coil, and over what distance its density falls from 90% to 10% of
    the density just inside the edge.

    The density also falls slowly from the centre outward, so "inside" is a band 0.03 coil radii wide that
    ends one edge thickness short of the place the density halves; the band is moved until the thickness it
    gives stops changing. Each level is taken at the outermost place inside the coil that the density still
    reaches it, so ripples further in do not count, and neither does plasma that has already left through a gap
    and is passing the coil on the outside.
    """
    inside = radius < c["rc"]
    radius, density = radius[inside], (count / radius)[inside]
    step = radius[1] - radius[0]

    def places(level: float) -> dict[float, float]:
        found = {}
        for share in (0.9, 0.5, 0.1):
            reached = np.nonzero(density >= share * level)[0]
            if not len(reached) or reached[-1] == len(radius) - 1:
                return {}
            k = reached[-1]
            found[share] = float(np.interp(share * level, [density[k + 1], density[k]], [radius[k + 1], radius[k]]))
        return found

    level = density[(radius > 0.4 * c["rc"]) & (radius < 0.6 * c["rc"])].mean()
    place = places(level)
    short = 0.04 * c["rc"]
    for _ in range(8):
        if not place:
            return {}
        band = (radius > place[0.5] - short - 0.03 * c["rc"]) & (radius < place[0.5] - short)
        level = density[band].mean()
        place = places(level)
        if not place:
            return {}
        thickness = max(place[0.1] - place[0.9], 2 * step)
        if abs(thickness - short) < step:
            break
        short = thickness
    return {"level": float(level), "middle": place[0.5], "thickness": place[0.1] - place[0.9]}


def crowding(density: float, temperature_J: float, weight: float, radius: float, cell: float) -> tuple[float, float]:
    """(simulation particles within a screening length or a cell of each other, screening length in cells).

    A simulation particle in this geometry is a ring about the axis, so the count is of rings crossing an area
    of the r-z plane at `radius`: the screening length squared plus the cell squared, since a particle cannot
    be told from another closer than a cell. Runs with fewer than about 2000 hold more plasma than runs with
    more (docs/cusp-results.md).
    """
    screening = EPS0 * temperature_J / (density * Q_E**2)
    return float(density * 2 * np.pi * radius / weight * (screening + cell**2)), float(np.sqrt(screening) / cell)


def gap_stream(count: np.ndarray, lost: float, band: float, ring: float, inside: float) -> tuple[float, float]:
    """(height of a slab at the inside density that carries one gap's stream, mean outward speed in the stream).
    `count` is the particles in a band `band` thick around the coil radius, binned along the axis with both gaps
    folded together; `ring` is the band's area seen along the axis; `lost` is particles leaving per second."""
    return float(count.sum() / (2 * ring * inside)), float(lost * band / count.sum())


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
    pressures = []
    # A mesh of several periods folds them onto one in lines 1 and 3 (make_deck.two_periods).
    periods = round(c["zw"] / c["h"])
    slab = 2 * 0.02 * c["a"] * periods
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
            pressures.append(density * pressure_per_particle(mean_energy, mass))
        if index == 0:
            electron_edge, electron_pressure_each = found, pressure_per_particle(mean_energy, M_E)
            if found:
                weight = float((held[late] / number[late, 3]).mean())
                count, cells = crowding(density, electron_pressure_each, weight, 0.5 * c["rc"], c["rw"] / c["nr"])
                out["simulation_electrons_within_a_screening_length_or_cell"] = round(count)
                out["screening_length_in_cells"] = round(cells, 2)
        data, height = table(run, f"{letter}_line3"), bin_centres(run, f"{letter}_line3")
        profile = data[data[:, 1] >= 0.8 * time[-1], 2:].mean(axis=0)
        # The gap is centred half-way between the coils; fold the profile about that plane.
        folded = 0.5 * (profile + profile[::-1])[len(profile) // 2 :]
        out[f"{species[:-1]}_stream_half_height_in_gap_mm"] = round(half_width(height[: len(folded)], folded) * 1e3, 4)
        if found and lost > 0:
            band = 2 * 0.02 * c["a"]
            slab_height, speed = gap_stream(profile / periods, lost / periods, band, 2 * np.pi * c["rc"] * band, density)
            out[f"{species[:-1]}_stream_height_at_inside_density_mm"] = round(slab_height * 1e3, 4)
            out[f"{species}_mean_speed_through_gap_over_light"] = round(speed / C_LIGHT, 4)
    # Both species or nothing: one species' edge not being found must not pass for a low pressure.
    pressure = sum(pressures) if len(pressures) == len(masses) else None
    out["pressure_inside_Pa"] = float(f"{pressure:.4g}") if pressure is not None else None
    out.update(field_and_charge(run, 0.8 * time[-1], time[-1]))
    axial = along_axis(run, c["rw"])
    if axial is not None:
        out["current_along_axis_at_end_over_coil_current"] = round(float(abs(axial[-1, 1]) / c["coil_at"]), 3)
        out["current_along_axis_largest_over_coil_current"] = round(float(np.abs(axial[:, 1]).max() / c["coil_at"]), 3)
    profiles = on_coil_plane(run, 0.8 * time[-1])
    if profiles is not None and electron_edge:
        radius, strength, current = profiles[0] * c["rw"], profiles[1], profiles[2]
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
        if pressure is not None:
            out["pressure_inside_over_magnetic_outside_edge"] = float(f"{pressure / (outside**2 / (2 * MU0)):.3g}")
        layer = current_layer(radius, current, middle, 0.1 * c["rc"])
        if layer:
            inside = (radius >= layer["from"]) & (radius <= layer["to"])
            mean = float(strength[inside].mean())
            # Park et al. take the orbit from the temperature the plasma is fed at and the mean field in the layer.
            fed = np.sqrt(c["te"] * Q_E * M_E) / (Q_E * mean)
            out["current_layer_at_over_coil_radius"] = round(layer["peak_at"] / c["rc"], 4)
            out["current_layer_width_mm"] = round(layer["width"] * 1e3, 4)
            out["current_layer_width_in_cells"] = round(layer["width"] / (radius[1] - radius[0]), 1)
            out["field_in_current_layer_T"] = round(mean, 4)
            out["current_layer_width_in_orbits_at_fed_temperature"] = round(float(layer["width"] / fed), 2)
            out["current_layer_width_in_orbits_at_measured_pressure"] = round(float(layer["width"] * Q_E * mean / momentum), 2)
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps(reduce(Path(path))))
