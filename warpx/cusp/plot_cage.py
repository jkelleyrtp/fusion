"""Draw mid-plane maps (electron density, voltage) and time histories for cusp-cage runs.

Usage: plot_cage.py SLICES.npz OUT_DIR RUN_DIR [RUN_DIR ...]

Writes one PNG per run with a map in SLICES.npz, plus series.json holding the electron count and the
centre voltage against time for every run given. Coil field lines are the vacuum field of vacuum_dwell.py.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

from analyze_cage import Q_E, constants, line_potential
from vacuum_dwell import field

A, DC, RC, RM, RW, HALF = 0.01, 0.013, 0.01, 0.0012, 0.024, 0.025


def hardware(ax, colour, scale):
    """Rings, wall and emitters of a device `scale` times the 1 cm one, in cm."""
    k = 100 * scale
    for sx in (1, -1):
        for sy in (1, -1):
            ax.add_patch(plt.Circle((sx * DC * k, sy * RC * k), RM * k, color=colour, zorder=5))
            ax.add_patch(plt.Circle((sy * RC * k, sx * DC * k), RM * k, color=colour, zorder=5))
    ax.add_patch(plt.Circle((0, 0), RW * k, fill=False, color=colour, lw=1.5, zorder=5))
    for x, y in ((RW, 0), (-RW, 0), (0, RW), (0, -RW)):
        ax.plot([k * x], [k * y], marker="s", color="#d62728", ms=6, zorder=6)
    ax.set_xlim(-HALF * k, HALF * k), ax.set_ylim(-HALF * k, HALF * k), ax.set_aspect("equal")
    ax.set_xlabel("x (cm)"), ax.set_ylabel("y (cm)")


def field_lines(ax, coil_at, colour, scale):
    if coil_at == 0:
        return
    # The scaled device has the 1 cm device's field-line pattern, stretched.
    grid = np.linspace(-HALF, HALF, 161)
    x, y = np.meshgrid(grid, grid)
    points = np.stack([x.ravel(), y.ravel(), np.zeros(x.size)], axis=1)
    b = field(points, coil_at).reshape(161, 161, 3)
    ax.streamplot(100 * scale * x, 100 * scale * y, b[..., 0], b[..., 1], density=1.3, color=colour, linewidth=0.5, arrowsize=0.5)


def draw(name, constants_, time_ns, phi, density, out: Path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.9), dpi=110)
    scale = constants_["a"] / A
    half = 100 * HALF * scale
    extent = [-half, half, -half, half]
    cells = np.linspace(-half, half, phi.shape[0])
    outside = np.hypot(*np.meshgrid(cells, cells)) > 100 * RW * scale
    density = np.ma.masked_where(outside | (density <= 0), density)
    image = axes[0].imshow(density.T, origin="lower", extent=extent, cmap="magma",
                           norm=LogNorm(vmin=1e13, vmax=1e17))
    fig.colorbar(image, ax=axes[0], label="electron density (per m³)", shrink=0.85)
    field_lines(axes[0], constants_["coil_at"], "#9ecae1", scale)
    hardware(axes[0], "#bbbbbb", scale)
    axes[0].set_title(f"Electrons at {time_ns:.0f} ns, with coil field lines", fontsize=10)
    image = axes[1].imshow(np.ma.masked_where(outside, phi).T / 1e3, origin="lower", extent=extent, cmap="viridis",
                           vmin=constants_["wall_v"] / 1e3, vmax=10)
    fig.colorbar(image, ax=axes[1], label="voltage (kV)", shrink=0.85)
    levels = np.arange(0, 10, 1)
    axes[1].contour(cells, cells, phi.T / 1e3, levels=levels, colors="white", linewidths=0.4)
    hardware(axes[1], "#222222", scale)
    axes[1].set_title(f"Voltage (rings at +10 kV, emitters at 0, wall at {constants_['wall_v'] / 1e3:.1f} kV)".replace("-", "−"),
                      fontsize=10)
    fig.tight_layout()
    fig.savefig(out / f"{name}.png")
    plt.close(fig)


if __name__ == "__main__":
    slices, out = np.load(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    series = {}
    for path in sys.argv[3:]:
        run = Path(path)
        c = constants(run)
        number = np.loadtxt(run / "diags/reducedfiles/number.txt", skiprows=1)
        axis = line_potential(run, "axis", 0.0 if c["gun_off"] == 0 else c["wall_v"])
        steps = sorted(s for s in axis if s > 0)
        keep = slice(0, None, max(1, len(number) // 300))
        series[run.name] = {
            "coil_at": c["coil_at"], "current_A": c["current"], "ncell": c["ncell"], "toff_ns": 1e9 * c["toff"],
            "time_ns": (1e9 * number[keep, 1]).round(3).tolist(),
            "electrons": number[keep, 6].tolist(),
            "probe_time_ns": [round(1e9 * s * c["dt"], 3) for s in steps],
            "centre_V": [round(float(axis[s][1][0]), 1) for s in steps],
        }
        if f"{run.name}/phi_V" in slices:
            draw(run.name, c, slices[f"{run.name}/time_ns"][-1], slices[f"{run.name}/phi_V"][-1],
                 slices[f"{run.name}/n_e_m3"][-1], out)
    (out / "series.json").write_text(json.dumps(series))
