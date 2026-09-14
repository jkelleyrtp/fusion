"""Summarize and plot the settled-electron paths recorded by the six-coil-tracks study (tracks.npz)."""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

plt.switch_backend("Agg")

TRACK_CASES = (
    "track_0V", "track_0V_s2345", "track_m1kV", "track_p5kV", "track_p10kV", "track_3A",
    "track_p5kV_2keV", "track_60kAt",
)
WALL_FACES = ("wall_x-", "wall_x+", "wall_y-", "wall_y+", "wall_z-", "wall_z+")
CUSP_CLASSES = ("point cusp (face axis)", "line cusp (edge)", "corner cusp")
PATHS_PER_PANEL = 4


@dataclass
class CaseTracks:
    name: str
    configuration: dict[str, object]
    time: np.ndarray
    position: np.ndarray
    lifetime: np.ndarray
    exited: np.ndarray
    entries: np.ndarray
    exits: dict[str, int]
    cusps: dict[str, int]
    full: bool

    def number(self, key: str) -> float:
        value = self.configuration[key]
        if not isinstance(value, int | float):
            raise TypeError(f"{key} must be numeric")
        return float(value)

    def label(self) -> str:
        return (
            f"{self.name}: {self.number('casing_voltage') / 1e3:+g} kV, {self.number('current_a'):g} A, "
            f"{self.number('energy_ev') / 1e3:g} keV, {self.number('coil_current') / 1e3:g} kA-t"
        )

    def summary(self) -> dict[str, object]:
        exited = self.lifetime[self.exited]
        return {
            "case": self.name,
            "casing_voltage_V": self.number("casing_voltage"),
            "current_A": self.number("current_a"),
            "energy_eV": self.number("energy_ev"),
            "coil_ampere_turns": self.number("coil_current"),
            "seed": self.configuration["seed"],
            "tracked": len(self.lifetime),
            "samples": len(self.time),
            "sample_interval_s": float(np.median(np.diff(self.time))),
            "buffer_full": self.full,
            "exited": int(self.exited.sum()),
            "median_exit_lifetime_s": float(np.median(exited)) if len(exited) else None,
            "mean_lifetime_lower_bound_s": float(self.lifetime.mean()),
            "sampled_core_entries_mean": float(self.entries.mean()),
            "sampled_core_entries_max": int(self.entries.max()),
            "fraction_entering_core_twice": float((self.entries >= 2).mean()),
            "exit_channels": self.exits,
            "exit_cusps": self.cusps,
        }


def vector(configuration: dict[str, object], key: str) -> list[float]:
    value = configuration[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    return [float(item) for item in value]


def core_entries(radius: np.ndarray, core: float) -> np.ndarray:
    """Sampled outside-to-inside core crossings per electron; a lower bound between samples."""
    inside = radius < core
    return (inside[1:] & ~inside[:-1]).sum(axis=0)


def cusp_class(position: np.ndarray) -> str:
    """Nearest cube-symmetry direction of a wall exit: face axis, edge or corner (22.5° boundaries)."""
    magnitude = np.abs(position)
    return CUSP_CLASSES[int((magnitude > math.tan(math.pi / 8) * magnitude.max()).sum()) - 1]


def load(case: Path) -> CaseTracks:
    configuration = json.loads((case / "configuration.json").read_text())
    with np.load(case / "tracks.npz") as data:
        time = data["time_s"]
        position = data["position_m"].astype(np.float64)
        birth = data["birth_s"]
        exit_time = data["exit_time_s"]
        exit_face = data["exit_face"]
        full = bool(data["full"])
    if len(time) < 2 or np.isnan(birth).any():
        raise ValueError(f"{case.name}: tracked electrons were not all injected and sampled")
    with np.load(max((case / "snapshots").glob("step-*.npz"))) as data:
        if not np.array_equal(data["tracked_exit_time_s"], exit_time, equal_nan=True):
            raise ValueError(f"{case.name}: the last snapshot and tracks.npz disagree on exits")
        terminal = data["tracked_position_m"]
    exited = ~np.isnan(exit_time)
    position[time[:, None] > np.where(exited, exit_time, math.inf)[None, :]] = math.nan
    names = [*WALL_FACES, *(str(name) for name in configuration.get("conductor_names", []))]
    exits: dict[str, int] = {}
    cusps: dict[str, int] = {}
    for index in np.flatnonzero(exited):
        name = names[int(exit_face[index])]
        exits[name] = exits.get(name, 0) + 1
        if int(exit_face[index]) >= len(WALL_FACES):
            cusps[name] = cusps.get(name, 0) + 1
            continue
        kind = cusp_class(terminal[index])
        cusps[kind] = cusps.get(kind, 0) + 1
    return CaseTracks(
        name=case.name, configuration=configuration, time=time, position=position,
        lifetime=np.where(exited, exit_time, float(configuration["duration"])) - birth, exited=exited,
        entries=core_entries(np.linalg.norm(position, axis=2), float(configuration["core_radius_m"])),
        exits=exits, cusps=cusps, full=full,
    )


def draw_geometry(axis: plt.Axes, case: CaseTracks) -> None:
    lower, upper = vector(case.configuration, "box_lower_m"), vector(case.configuration, "box_upper_m")
    axis.add_patch(plt.Rectangle(
        (lower[1], lower[2]), upper[1] - lower[1], upper[2] - lower[2], fill=False, color="0.3", lw=0.8,
    ))
    axis.add_patch(plt.Circle((0, 0), case.number("core_radius_m"), fill=False, ls="--", color="0.4"))
    radius = case.number("radius")
    casing = case.number("casing_radius") * radius
    offset = case.number("coil_offset") * radius
    for sign_a in (1, -1):
        for sign_b in (1, -1):
            axis.add_patch(plt.Circle((sign_a * offset, sign_b * radius), casing, color="0.75"))
            axis.add_patch(plt.Circle((sign_a * radius, sign_b * offset), casing, color="0.75"))
    origin = vector(case.configuration, "source_origin_m")
    axis.plot(origin[1], origin[2], "k^", ms=5)
    axis.set_xlim(lower[1], upper[1])
    axis.set_ylim(lower[2], upper[2])
    axis.set_aspect("equal")


def plot_paths(cases: list[CaseTracks], out: Path) -> None:
    figure, axes = plt.subplots(2, 4, figsize=(20, 10.5), constrained_layout=True)
    for axis, case in zip(axes.flat, cases, strict=True):
        draw_geometry(axis, case)
        order = np.lexsort((-case.lifetime, -case.entries))
        for rank, index in enumerate(order[:PATHS_PER_PANEL]):
            axis.plot(case.position[:, index, 1], case.position[:, index, 2], lw=0.5, color=f"C{rank}", alpha=0.85)
        axis.set_title(
            f"{case.label()}\n{PATHS_PER_PANEL} most-entering of {len(case.lifetime)}; "
            f"mean sampled core entries {case.entries.mean():.2f}", fontsize=8,
        )
        axis.set_xlabel("y (m)")
        axis.set_ylabel("z (m)")
    figure.suptitle(
        "Settled-electron paths, y–z projection (grey: y and z coil casings in this plane; dashed: core; ▲: gun). "
        "Imposed vacuum field, electrons only.", fontsize=11,
    )
    figure.savefig(out, dpi=130)
    plt.close(figure)


def plot_statistics(cases: list[CaseTracks], out: Path) -> None:
    figure, (survival, entries_axis, channels) = plt.subplots(1, 3, figsize=(20, 6), constrained_layout=True)
    for index, case in enumerate(cases):
        grid = np.linspace(0, float(case.lifetime.max()), 200)
        lost_at = np.where(case.exited, case.lifetime, math.inf)
        survival.plot(grid * 1e9, (lost_at[None, :] > grid[:, None]).mean(axis=1), color=f"C{index}", label=case.name)
        counts = np.bincount(case.entries, minlength=11)[:11]
        entries_axis.plot(range(len(counts)), counts / len(case.entries), "o-", color=f"C{index}", ms=3)
    survival.set_xlabel("time since injection (ns)")
    survival.set_ylabel("fraction of tracked electrons not yet lost")
    survival.set_title("Survival (censored at the end of the run)")
    survival.legend(fontsize=8)
    entries_axis.set_xlabel("sampled core entries per electron")
    entries_axis.set_ylabel("fraction of tracked electrons")
    entries_axis.set_title("Core entries within the path window (lower bound on lifetime entries)")
    names = [*CUSP_CLASSES, *sorted({name for case in cases for name in case.cusps} - set(CUSP_CLASSES))]
    bottom = np.zeros(len(cases))
    for index, name in enumerate(names):
        values = np.array([case.cusps.get(name, 0) / len(case.lifetime) for case in cases])
        channels.bar(range(len(cases)), values, bottom=bottom, label=name, color=plt.get_cmap("tab20")(index % 20))
        bottom += values
    channels.set_xticks(range(len(cases)), [case.name for case in cases], rotation=40, ha="right", fontsize=8)
    channels.set_ylabel("fraction of tracked electrons")
    channels.set_title("Exit channel by the end of the run (wall exits by nearest cusp direction)")
    channels.legend(fontsize=7, ncol=2)
    figure.savefig(out, dpi=130)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="campaign attempt directory")
    parser.add_argument("--out", type=Path, required=True, help="output directory for images")
    parser.add_argument("--summary", type=Path, required=True, help="summary JSON path")
    parser.add_argument("--prefix", default="pic-six-coil-tracks")
    args = parser.parse_args()
    cases = []
    for name in TRACK_CASES:
        if (args.run / name / "DONE").read_text().strip() != "complete":
            raise ValueError(f"{name} is not complete")
        cases.append(load(args.run / name))
    args.out.mkdir(parents=True, exist_ok=True)
    plot_paths(cases, args.out / f"{args.prefix}-paths.png")
    plot_statistics(cases, args.out / f"{args.prefix}-statistics.png")
    summary = [case.summary() for case in cases]
    args.summary.write_text(json.dumps(summary, indent=2) + "\n")
    for item in summary:
        print(json.dumps(item))


if __name__ == "__main__":
    main()
