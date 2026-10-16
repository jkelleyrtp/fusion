#!/usr/bin/env python3
"""Reduce runs of inputs_3d_cusp_beta, inputs_3d_cusp_fed and inputs_3d_cusp_jets to one JSON line each.

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
    names = ("a", "coil_at", "te", "ti", "mass_amu", "dt", "ncell")
    # WarpX echoes each constant followed by a comment holding its evaluated value.
    out = {name: float(re.search(rf"^my_constants\.{name} = .*# (\S+)$", text, re.MULTILINE).group(1)) for name in names}
    # WarpX echoes only the constants a deck uses. Only the fed and jet decks have a feed, only the jet deck has
    # guns and only it has no starting ball; a constant that is absent reads as zero.
    for name in ("feed", "toff", "zg", "vj", "rf", "n0", "r0", "ppd"):
        found = re.search(rf"^my_constants\.{name} = .*# (\S+)$", text, re.MULTILINE)
        out[name] = float(found.group(1)) if found else 0.0
    out["charge_only"] = bool(re.search(r"^warpx\.do_electrostatic = labframe", text, re.MULTILINE))
    return out


def table(run: Path, name: str) -> np.ndarray:
    rows = np.loadtxt(run / f"diags/reducedfiles/{name}.txt", skiprows=1, ndmin=2)
    # Two runs writing to one directory, or a restart that repeated steps, leave rows out of order.
    assert (np.diff(rows[:, 0]) > 0).all(), f"{name}.txt: steps repeat or go backwards, so this is not one run's output"
    return rows


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


def inside_cage(run: Path, c: dict, name: str) -> tuple[np.ndarray, np.ndarray]:
    """Times, and the number of particles within the distance of the coil planes from the centre at each."""
    data, radius = table(run, name), bin_centres(run, name)
    return data[:, 1], data[:, 2:][:, radius < 1.3 * c["a"]].sum(axis=1)


def jets(run: Path, c: dict) -> dict:
    """Where the guns are and how they are aimed, and how much of what they fire is inside the cage, counted
    within the distance of the coil planes from the centre. `fired_held_ns` is the amount inside over the firing
    rate: the time an average fired particle spends inside, zero if nothing gets in."""
    mouth = np.array([[0.0, 0.0, c["zg"]]])
    aim = np.array([0.0, 0.0, -1.0])
    out = {
        "gun_mouths_over_a": [[0.0, 0.0, round(c["zg"] / c["a"], 3)], [0.0, 0.0, -round(c["zg"] / c["a"], 3)]],
        "gun_mouth_radius_over_a": round(c["rf"] / c["a"], 3),
        "gun_aim": "toward the centre along the z axis",
        "jet_speed_m_per_s": c["vj"],
        "fired_per_s": c["feed"],
        "guns_stop_ns": None,
    }
    if c["coil_at"]:
        at_mouth = coil_field(mouth, c["coil_at"], c["a"])[0]
        at_opening = coil_field(np.array([[0.0, 0.0, 1.3 * c["a"]]]), c["coil_at"], c["a"])[0]
        cosine = abs(at_mouth @ aim) / np.linalg.norm(at_mouth)
        out["angle_of_aim_to_coil_field_deg"] = round(float(np.degrees(np.arccos(min(cosine, 1.0)))), 2)
        out["coil_field_at_opening_over_at_mouth"] = round(float(np.linalg.norm(at_opening) / np.linalg.norm(at_mouth)), 3)
    for name, species in (("erad", "electrons"), ("irad", "ions")):
        time, inside = inside_cage(run, c, name)
        stop = min(time[-1], c["toff"])
        late = (time >= 0.8 * stop) & (time <= stop)
        assert late.sum() >= 4, "under four histograms in the last fifth of the firing"
        growth = np.polyfit((time[late] - time[late].mean()) * 1e9, inside[late], 1)[0] * 1e9
        out[f"{species}_inside_late_in_firing"] = float(f"{inside[late].mean():.4g}")
        # Near 0 the amount inside has settled; near 1 everything fired is still accumulating.
        out[f"{species}_inside_growth_over_fired"] = round(float(growth / c["feed"]), 3)
        out[f"{species}_fired_held_ns"] = round(float(inside[late].mean() / c["feed"] * 1e9), 3)
        # Well above 1 means less gets in as the firing goes on, which no steady gun should show.
        early = (time >= 0.2 * stop) & (time <= 0.4 * stop)
        out[f"{species}_inside_early_over_late_in_firing"] = round(float(inside[early].mean() / max(inside[late].mean(), 1e-300)), 2)
        if c["toff"] < time[-1]:
            out["guns_stop_ns"] = round(c["toff"] * 1e9, 2)
            after = time >= c["toff"] + 0.5 * (time[-1] - c["toff"])
            out[f"{species}_inside_at_end_over_at_stop"] = round(float(inside[-1] / max(np.interp(c["toff"], time, inside), 1e-300)), 4)
            out[f"{species}_inside_loss_time_after_stop_ns"] = loss_time_ns(time[after], inside[after]) if after.sum() >= 4 else None
            # The first quarter of the time after the guns stop, when the plasma is closest to its firing state.
            # What was still in flight arrives during it, so this reads long.
            first = (time >= c["toff"]) & (time <= c["toff"] + 0.25 * (time[-1] - c["toff"]))
            rate = -np.polyfit(time[first], inside[first], 1)[0] if first.sum() >= 4 else 0.0
            out[f"{species}_inside_loss_time_just_after_stop_ns"] = round(float(inside[first].mean() / rate * 1e9), 1) if rate > 0 else None
            # Plasma still sitting at the gun mouths long after they stop is held there by charge the injection
            # left behind (docs/flux-injection-charge.md), not by anything physical.
            data, radius = table(run, name), bin_centres(run, name)
            at_mouths = data[-1, 2:][np.abs(radius - c["zg"]) < 0.15 * c["a"]].sum()
            out[f"{species}_at_gun_mouths_at_end_over_fired"] = round(float(at_mouths / (c["feed"] * c["toff"])), 4)
    return out


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
        "run": run.resolve().name,
        "complete": (run / "DONE").exists() and (run / "DONE").read_text().strip() == "complete",
        "n0_per_m3": c["n0"],
        "ion_mass_amu": c["mass_amu"],
        "ion_temperature_eV": c["ti"],
        "coil_kAt": c["coil_at"] / 1e3,
        "ncell": int(c["ncell"]),
        "charge_only": c["charge_only"],
        "end_ns": round(float(time[-1] * 1e9), 2),
        # pressure of the starting ball over the magnetic pressure of the coil field, at two places
        "pressure_ratio_at_coil_opening": round(pressure / (throat_field**2 / (2 * MU0)), 4) if c["coil_at"] and c["n0"] else None,
        "pressure_ratio_at_ball_edge": round(pressure / (edge_field**2 / (2 * MU0)), 3) if c["coil_at"] and c["n0"] else None,
        "electrons_left": round(float(electrons[-1] / electrons[0]), 4) if electrons[0] else None,
        "ions_left": round(float(ions[-1] / ions[0]), 4) if ions[0] else None,
        "electron_loss_time_ns": loss_time_ns(time, electrons),
        "ion_loss_time_ns": loss_time_ns(time, ions),
        "electron_energy_left": round(float(energy[-1, 3] / energy[0, 3]), 3) if electrons[0] else None,
        "ion_energy_over_start": round(float(energy[-1, 4] / energy[0, 4]), 3) if ions[0] else None,
        # against the plasma energy at the start, or now if the run started empty
        "own_magnetic_energy_over_plasma": float(f"{fields[-1, 4] / (energy[0, 2] if electrons[0] else energy[-1, 2]):.3e}"),
        "electron_stream_half_width_mm": round(stream_half_width(run, "ethroat", 0.7 * time[-1]) * 1e3, 3),
        "ion_stream_half_width_mm": round(stream_half_width(run, "ithroat", 0.7 * time[-1]) * 1e3, 3),
        "electron_orbit_at_coil_opening_mm": round(float(gyroradius * 1e3), 3) if c["coil_at"] else None,
    }
    if c["zg"]:
        out.update(jets(run, c))
    elif c["feed"]:
        # While the feed is on, what leaves per second is the feed minus the growth of what is held.
        late = (time >= 0.8 * min(time[-1], c["toff"])) & (time <= c["toff"])
        assert late.sum() >= 4, "under four counts in the last fifth of the feed"
        out["feed_per_s"] = c["feed"]
        out["feed_stops_ns"] = round(c["toff"] * 1e9, 2) if c["toff"] < time[-1] else None
        # The holding times below are measured over this window, the last fifth of the feed.
        out["feed_window_ns"] = [round(float(time[late][0] * 1e9), 2), round(float(time[late][-1] * 1e9), 2)]
        for name, count in (("electrons", electrons), ("ions", ions)):
            out[f"{name}_held_late_in_feed"] = float(f"{count[late].mean():.4g}")
            # Fitted in nanoseconds from the window centre, which keeps the fit well conditioned.
            growth = np.polyfit((time[late] - time[late].mean()) * 1e9, count[late], 1)[0] * 1e9
            leaving = c["feed"] - growth
            # Near 1 the amount held has settled. Near 0 it is still filling and the holding time is a small
            # difference of two large numbers.
            out[f"{name}_leaving_over_feed"] = round(float(leaving / c["feed"]), 3)
            out[f"{name}_holding_time_in_feed_ns"] = round(float(count[late].mean() / leaving * 1e9), 2) if leaving > 0 else None
        # The same measure the jet runs report as `fired_held_ns`, so the two ways of feeding can be compared.
        for name, species in (("erad", "electrons"), ("irad", "ions")):
            when, inside = inside_cage(run, c, name)
            window = (when >= 0.8 * min(when[-1], c["toff"])) & (when <= c["toff"])
            assert window.sum() >= 4, "under four histograms in the last fifth of the feed"
            out[f"{species}_inside_cage_over_feed_ns"] = round(float(inside[window].mean() / c["feed"] * 1e9), 3)
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
