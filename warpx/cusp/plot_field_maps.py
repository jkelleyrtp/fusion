"""Colour maps of two things in the picket-fence runs: the current along the axis in runs that repeat along the
axis, and the charge that piles up on the axis in runs between mirror planes.

Usage, in two steps because the snapshots live on the shared disk:
    plot_field_maps.py pack CASE[:FRACTION...] ... > maps.b64    (run in the campaign folder, on a worker)
    plot_field_maps.py draw maps.npz OUT_DIR                     (after base64 -d maps.b64 > maps.npz)

`pack` reads each case's field snapshot nearest each FRACTION of its run (default 1, the last) and writes them
as one compressed archive, base64 on standard output. `draw` expects the cases named in RUNS, COLUMNS and
TOTALS below, all at 15 mm wall radius, 10 mm coil radius and 5 mm coil spacing.

The mesh fields Br and Bz include the coil field, so the field lines drawn are those of the whole field. The
current along the axis is the curl of the field around the axis, which leaves out the displacement current.
"""
import base64
import io
import sys
from pathlib import Path

import numpy as np

MU0 = 4e-7 * np.pi
QE = 1.602176634e-19
WALL, COIL, HALF_PERIOD = 15.0, 10.0, 5.0  # mm

# Current figure: the two cases mapped, then the three whose running totals are plotted.
RUNS = [
    ("pw_s0.5_h1.0@1", "Standard particle count: 55 kA along the axis, holding time 71 crossings"),
    ("pw_s0.5_h1.0_ppc4_seed4@1", "4x the particles, seed 4: no net current, holding time 52 crossings"),
]
TOTALS = [
    ("pw_s0.5_h1.0_seed2@1", "Standard particles, seed 2 (73 crossings)", "#b2182b"),
    ("pw_s0.5_h1.0_ppc4_seed4@1", "4x particles, seed 4 (52 crossings)", "#444444"),
    ("pw_s0.5_h1.0@1", "Standard particles, seed 1 (71 crossings)", "#2166ac"),
]
# Mirror figure: one column each. No title means "Mirror ends" and the snapshot's time.
COLUMNS = [("pw_s0.25_h1.0_long_ppc8@1", "Wrap-around ends, 66 ns")] + [
    (f"pw_s0.25_h1.0_long2_ppc8_mirror@{fraction}", None) for fraction in ("0.25", "0.5", "0.75", "1")
]
READING = """The axis of the device is the bottom edge of each map;
the metal wall is the thick line at the top.
Dots: coil windings, seen end on. Black and white
carry opposite currents (78 kA each).
Between the dashed line and either side is one copy of
the simulated slice; what leaves one side re-enters
the other, so the picture repeats for ever.
Plasma leaks out between neighbouring coils.
Red/blue and orange/purple: the two directions.
The current maps are smoothed over 1.5 mesh cells.
In the bottom plot, a flat stretch means no current
flows there; a slope means current does."""
MIRROR_NOTE = """Smallest well-behaved size (0.25x), 4x the standard particles, one simulated slice. Left column: the same \
device with wrap-around ends, for comparison.
Colours are on a logarithmic scale. The plasma itself holds about 4 x 10$^{20}$ electrons per m$^3$; the surplus \
on the axis reaches 120 to 190 x 10$^{20}$ by the end.
In the mirror columns, the left and right edges of each map are the mirror planes."""


def pack(specs: list[str]) -> None:
    out = {}
    for spec in specs:
        case, *wanted = spec.split(":")
        snapshots = sorted(
            (d for d in Path(case, "diags").glob("diag1*")
             if d.name[5:].isdigit() and (d / "Level_0/Cell_D_00000").exists()
             and not (d / "Level_0/Cell_D_00001").exists()),
            key=lambda d: int(d.name[5:]),
        )
        headers = [(d / "Header").read_text().split("\n") for d in snapshots]
        times = np.array([float(h[3 + int(h[1])]) for h in headers])
        for fraction in wanted or ["1"]:
            i = int(np.argmin(abs(times - float(fraction) * times[-1])))
            count = int(headers[i][1])
            with open(snapshots[i] / "Level_0/Cell_D_00000", "rb") as data:
                nr, nz = (int(v) + 1 for v in data.readline().decode().split(") (")[1].split(")")[0].split(","))
                fields = np.frombuffer(data.read(count * nr * nz * 8), dtype="<f8").reshape(count, nz, nr)
            out[f"{case}@{fraction}"] = fields.astype("f4")
            out[f"{case}@{fraction}_t"] = times[i]
            out["names"] = np.array(headers[i][2:2 + count])
    packed = io.BytesIO()
    np.savez_compressed(packed, **out)
    sys.stdout.write(base64.b64encode(packed.getvalue()).decode())


def load(archive, key: str) -> dict:
    """One snapshot's mesh fields by name, indexed [along the axis, from the axis], with the derived ones."""
    stack = archive[key].astype("f8")
    f = dict(zip(archive["names"], stack, strict=True))
    cells = stack.shape[2]
    r = (np.arange(cells) + 0.5) / cells * WALL * 1e-3
    f["r_mm"] = r * 1e3
    f["ns"] = float(archive[key + "_t"]) * 1e9
    f["electrons"] = -f["rho_electrons"] / QE
    f["ions_minus_electrons"] = (f["rho_electrons"] + f["rho_ions"]) / QE
    f["flux"] = np.cumsum(r * f["Bz"], axis=1) * (r[1] - r[0])
    f["current_density"] = np.gradient(r * f["Bt"], r, axis=1) / (MU0 * r)
    f["current_inside"] = 2 * np.pi * r * f["Bt"].mean(0) / MU0
    f["field_strength"] = np.hypot(f["Er"], f["Ez"])
    return f


def frame(ax, periods: int) -> None:
    """Wall, coil windings (black and white carry opposite currents) and, for two periods, where they join."""
    ax.set_xlim(-HALF_PERIOD, HALF_PERIOD * (2 * periods - 1))
    ax.set_ylim(0, WALL)
    ax.set_aspect("equal")
    for k in range(2 * periods + 1):
        ax.plot(
            [(k - 1) * HALF_PERIOD], [COIL], "o", ms=5, mfc="white" if k % 2 else "black", mec="black", mew=0.8,
            zorder=5, clip_on=k in (0, 2 * periods),
        )
    ax.axhline(WALL, color="k", lw=2)
    if periods == 2:
        ax.axvline(HALF_PERIOD, color="k", lw=0.8, ls=(0, (4, 3)))


def show(ax, field, extent, **how):
    return ax.imshow(field.T, origin="lower", extent=extent, aspect="equal", interpolation="nearest", **how)


def field_lines(ax, flux, extent, count: int = 14) -> None:
    z = np.linspace(extent[0], extent[1], flux.shape[0] * 2 + 1)[1::2]
    r = np.linspace(0, WALL, flux.shape[1] * 2 + 1)[1::2]
    # Levels are set by the flux inside 0.62 of the wall radius, so the lines are dense in the plasma and not
    # crowded round the windings. The zero level is left out: it is the axis.
    top = 0.98 * np.abs(flux[:, : int(0.62 * flux.shape[1])]).max()
    levels = np.delete(np.linspace(-top, top, 2 * count + 1), count)
    ax.contour(z, r, flux.T, levels=levels, colors="white", linewidths=0.45, alpha=0.75, linestyles="solid")


def draw_current(archive, out: Path) -> None:
    import matplotlib.pyplot as plt
    from scipy.ndimage import gaussian_filter

    fig = plt.figure(figsize=(13.6, 10.6))
    grid = fig.add_gridspec(
        3, 3, height_ratios=[1, 1, 0.8], hspace=0.5, wspace=0.2, left=0.06, right=0.965, top=0.875, bottom=0.055
    )
    extent = (-HALF_PERIOD, 3 * HALF_PERIOD, 0, WALL)
    for row, (key, label) in enumerate(RUNS):
        f = load(archive, key)
        smooth = gaussian_filter(f["current_density"], 1.5, mode=("wrap", "nearest"))
        maps = [
            ("Electron density (10$^{21}$ per m$^3$), magnetic field lines in white", f["electrons"] / 1e21,
             {"cmap": "magma", "vmin": 0, "vmax": 3.0}),
            ("Magnetic field circling the axis (T)", f["Bt"], {"cmap": "RdBu_r", "vmin": -1.5, "vmax": 1.5}),
            ("Current along the axis (billion A per m$^2$)", smooth / 1e9,
             {"cmap": "PuOr_r", "vmin": -1.2, "vmax": 1.2}),
        ]
        for col, (title, field, how) in enumerate(maps):
            ax = fig.add_subplot(grid[row, col])
            image = show(ax, np.concatenate([field, field]), extent, **how)
            frame(ax, 2)
            ax.set_title(title)
            plt.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
            if row == len(RUNS) - 1:
                ax.set_xlabel("Distance along the axis (mm)")
            if col == 0:
                field_lines(ax, np.concatenate([f["flux"], f["flux"]]), extent)
                ax.set_ylabel("Distance from the axis (mm)")
                ax.text(-HALF_PERIOD, WALL * 1.2, label, fontsize=11.5, fontweight="bold", va="bottom", color="#333333")

    ax = fig.add_subplot(grid[2, :2])
    ax.axvspan(0, 4.5, color="#f3d9a4", alpha=0.55, lw=0)
    ax.axvspan(6, 9, color="#c9b6e4", alpha=0.6, lw=0)
    ax.axvline(COIL, color="k", lw=1, ls=":")
    ax.axvline(WALL, color="k", lw=2)
    ax.axhline(0, color="k", lw=0.6)
    for key, label, colour in TOTALS:
        kiloamps = load(archive, key)["current_inside"] / 1e3
        ax.plot(load(archive, key)["r_mm"], kiloamps, color=colour, lw=2)
        above = kiloamps[-1] >= -1
        ax.text(
            14.8, kiloamps[-40:].mean() + (5 if above else -5), label, color=colour, ha="right",
            va="bottom" if above else "top", fontsize=9,
        )
    ax.set_xlim(0, WALL)
    ax.set_ylim(-95, 95)
    ax.set_xlabel("Distance from the axis (mm)")
    ax.set_ylabel("Current along the axis\ninside this radius (kA)")
    ax.set_title("Adding it up from the axis outward (averaged along the axis)", loc="left")
    for x, name, align in [
        (2.25, "plasma core", "center"), (7.5, "plasma edge", "center"), (COIL + 0.15, "coil radius", "left"),
        (WALL - 0.15, "wall", "right"),
    ]:
        ax.text(x, -88, name, ha=align, va="bottom", fontsize=9)

    ax = fig.add_subplot(grid[2, 2])
    ax.axis("off")
    ax.text(0, 1.12, "How to read the maps", fontweight="bold", va="top", fontsize=10.5)
    ax.text(0, 0.99, READING, va="top", fontsize=9.3, linespacing=1.45)
    fig.suptitle(
        "Two runs of the same device: one ends with a net current along the axis, the other with currents that cancel",
        x=0.06, ha="left", fontsize=13.5, fontweight="bold", y=0.985,
    )
    fig.text(
        0.06, 0.955,
        "Middle size (0.5x), wrap-around ends, both finished, 66 ns in. Same device and feed; they differ in "
        "particle count and random numbers.",
        fontsize=10, va="top",
    )
    fig.savefig(out / "picket-axial-current-map.png")
    plt.close(fig)


def draw_mirror(archive, out: Path) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm, SymLogNorm

    fig, axes = plt.subplots(
        3, len(COLUMNS), figsize=(13.6, 11.2),
        gridspec_kw={
            "left": 0.095, "right": 0.9, "top": 0.855, "bottom": 0.05, "wspace": 0.12, "hspace": 0.28,
            "height_ratios": [1.5, 0.75, 1.5],
        },
    )
    extent = (-HALF_PERIOD, HALF_PERIOD, 0, WALL)
    charge_scale = {"cmap": "RdBu_r", "norm": SymLogNorm(1, vmin=-200, vmax=200)}
    inner = 8
    for col, (key, title) in enumerate(COLUMNS):
        f = load(archive, key)
        charge = f["ions_minus_electrons"] / 1e20
        charge_image = show(axes[0, col], charge, extent, **charge_scale)
        frame(axes[0, col], 1)
        axes[0, col].set_title(title or f"Mirror ends, {f['ns']:.0f} ns", fontweight="bold")
        axes[1, col].imshow(
            charge[:, :inner].T, origin="lower", extent=(*extent[:2], 0, WALL * inner / charge.shape[1]),
            aspect="auto", interpolation="nearest", **charge_scale,
        )
        field_image = show(axes[2, col], f["field_strength"], extent, cmap="inferno", norm=LogNorm(1e7, 1e11))
        frame(axes[2, col], 1)
        axes[2, col].set_xlabel("Distance along the axis (mm)")
    for ax in axes[:, 1:].ravel():
        ax.set_yticklabels([])
    for ax in axes.ravel():
        ax.set_xticks([-4, -2, 0, 2, 4])
    axes[0, 0].set_ylabel("NET CHARGE\n\nDistance from the axis (mm)")
    axes[1, 0].set_ylabel(f"NET CHARGE\ninnermost {inner} cells\n\n(mm)")
    axes[2, 0].set_ylabel("ELECTRIC FIELD STRENGTH\n\nDistance from the axis (mm)")
    fig.colorbar(charge_image, cax=fig.add_axes([0.912, 0.42, 0.012, 0.42])).set_label(
        "ions minus electrons (10$^{20}$ per m$^3$)\nred: too many ions, blue: too many electrons", fontsize=9
    )
    fig.colorbar(field_image, cax=fig.add_axes([0.912, 0.06, 0.012, 0.27])).set_label("V per m", fontsize=9)
    fig.suptitle(
        "Between mirror planes, charge piles up along the axis (the bottom edge) and keeps growing",
        x=0.075, ha="left", fontsize=13.5, fontweight="bold", y=0.985,
    )
    fig.text(0.075, 0.953, MIRROR_NOTE, fontsize=9.5, va="top")
    fig.savefig(out / "picket-mirror-axis-charge-map.png")
    plt.close(fig)


def draw(archive_path: str, out_dir: str) -> None:
    # Imported here because `pack` runs on workers, which have numpy only.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.titlesize": 10.5, "figure.dpi": 150, "font.family": "DejaVu Sans"})
    archive = np.load(archive_path)
    draw_current(archive, Path(out_dir))
    draw_mirror(archive, Path(out_dir))


if __name__ == "__main__":
    if sys.argv[1] == "pack":
        pack(sys.argv[2:])
    elif sys.argv[1] == "draw":
        draw(*sys.argv[2:4])
    else:
        sys.exit(__doc__)
