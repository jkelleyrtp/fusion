"""Figures comparing 3D six-coil cage runs with and without the metal rings around the coils.

    python3 plot_ring_pair.py CUTS.npz OUT_DIR WITH_RINGS_RUN NO_RINGS_RUN

CUTS.npz comes from cage_cuts.py. The run folders need only diags/reducedfiles and warpx_used_inputs.
The mesh field in these runs already holds the coils' field (checked against Biot-Savart near the wall, where
they agree to 1%), so the field maps are the whole field.
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from analyze_cage import coil_field, histogram, line_potential
from matplotlib.colors import LogNorm, SymLogNorm
from matplotlib.patches import Circle

Q_E = 1.602176634e-19
A, DC, RM, RW = 10.0, 13.0, 1.2, 24.0   # mm: coil radius, coil distance from the centre, ring thickness, wall


def constant(run: Path, name: str) -> float:
    for line in (run / "warpx_used_inputs").read_text().split("\n"):
        if line.startswith(f"my_constants.{name} ="):
            return float(line.split("#")[-1])
    raise KeyError(name)


def outline(axis, cut: str, rings: bool) -> None:
    """Draw the wall and, where the cut crosses them, the rings."""
    stretch = np.sqrt(2) if cut == "diag" else 1.0
    if cut == "coil":
        axis.add_patch(Circle((0, 0), np.sqrt(RW**2 - DC**2), fill=False, color="w", lw=0.8))
        marks = [Circle((0, 0), A + RM, fill=False, color="w", lw=0.6), Circle((0, 0), A - RM, fill=False, color="w", lw=0.6)]
    else:
        axis.add_patch(Circle((0, 0), RW, fill=False, color="w", lw=0.8))
        spots = [(A, DC), (A, -DC), (-A, DC), (-A, -DC)]
        spots += [(y, x) for x, y in spots] if cut == "mid" else []
        marks = [Circle(spot, RM, fill=False, color="w", lw=0.6) for spot in spots]
    for mark in marks:
        mark.set_linestyle("-" if rings else ":")
        axis.add_patch(mark)
    axis.set_xlim(-25 * min(stretch, 1.0), 25 * min(stretch, 1.0))
    axis.set_ylim(-25, 25)
    axis.set_aspect("equal")


CUTS = {"mid": ("plane through the centre, across four coils", "x (mm)", "y (mm)"),
        "diag": ("diagonal plane: coil axis up, corners at 55 degrees", "distance along x = y (mm)", "z (mm)"),
        "coil": ("plane of one coil", "y (mm)", "z (mm)")}


def maps(cuts, runs: dict[str, str], value, label: str, norm, cmap: str, path: Path, title: str) -> None:
    figure, axes = plt.subplots(len(runs), 3, figsize=(15, 5 * len(runs)), constrained_layout=True)
    for row, (run, name) in zip(axes, runs.items()):
        for axis, (cut, (what, across, up)) in zip(row, CUTS.items()):
            wide = 25 * (np.sqrt(2) if cut == "diag" else 1.0)
            image = axis.imshow(value(cuts, run, cut).T, origin="lower", extent=(-wide, wide, -25, 25), norm=norm, cmap=cmap)
            outline(axis, cut, "no rings" not in name)
            axis.set(title=f"{name}: {what}", xlabel=across, ylabel=up)
            axis.title.set_fontsize(10)
    figure.colorbar(image, ax=axes, shrink=0.7, label=label)
    figure.suptitle(title)
    figure.savefig(path, dpi=110)
    plt.close(figure)


def strength(cuts, run: str, cut: str) -> np.ndarray:
    """Strength (T) of the field on the mesh, which is the coils' field plus the plasma's."""
    return np.sqrt(sum(cuts[f"{run}/B{part}/{cut}"].astype(float) ** 2 for part in "xyz"))


def late(run: Path, name: str, last: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """Bin centres and the mean of a histogram over the last `last` of the run."""
    header = (run / f"diags/reducedfiles/{name}.txt").read_text().split("\n")[0].split()
    centres = np.array([float(word.split("=")[1].rstrip("()")) for word in header if "=" in word])
    counts = histogram(run, name)[1]
    return centres, counts[int(len(counts) * (1 - last)):].mean(axis=0)


if __name__ == "__main__":
    cuts, out = np.load(sys.argv[1]), Path(sys.argv[2])
    folders = {"rings": Path(sys.argv[3]), "no rings": Path(sys.argv[4])}
    runs = {folder.name: f"{label}" for label, folder in folders.items()}
    colour = {"rings": "tab:red", "no rings": "tab:blue"}
    coil_at = constant(folders["rings"], "coil_at")
    out.mkdir(parents=True, exist_ok=True)

    density = lambda species: lambda c, run, cut: np.abs(c[f"{run}/rho_{species}/{cut}"]) / Q_E + 1e10
    maps(cuts, runs, density("electrons"), "electrons per m$^3$", LogNorm(1e17, 3e20), "inferno", out / "cage-electron-density.png",
         "Electron density at 18 ns. White: wall and rings (dotted where the rings were removed)")
    maps(cuts, runs, density("ions"), "ions per m$^3$", LogNorm(1e17, 3e20), "inferno", out / "cage-ion-density.png", "Ion density at 18 ns")
    net = lambda c, run, cut: (c[f"{run}/rho_electrons/{cut}"] + c[f"{run}/rho_ions/{cut}"]) / Q_E
    maps(cuts, runs, net, "ions less electrons per m$^3$ (red: positive)", SymLogNorm(3e17, vmin=-3e19, vmax=3e19), "RdBu_r",
         out / "cage-net-charge.png", "Net charge at 18 ns")

    figure, axes = plt.subplots(2, 3, figsize=(15, 9.5), constrained_layout=True)
    for column, cut in enumerate(("mid", "diag")):
        for row, (run, name) in enumerate(runs.items()):
            wide = 25 * (np.sqrt(2) if cut == "diag" else 1.0)
            image = axes[row, column].imshow(strength(cuts, run, cut).T, origin="lower", extent=(-wide, wide, -25, 25), norm=LogNorm(0.03, 6), cmap="viridis")
            outline(axes[row, column], cut, name == "rings")
            axes[row, column].set(title=f"{name}: {CUTS[cut][0]}", xlabel=CUTS[cut][1], ylabel=CUTS[cut][2])
            axes[row, column].title.set_fontsize(9)
    figure.colorbar(image, ax=axes[:, :2], shrink=0.7, label="field strength, coils and plasma together (T)")
    low, cell = cuts[f"{next(iter(runs))}/low_cell_a_dc"][:2]
    x = 1e3 * (low + cell * (np.arange(512) + 0.5))
    line = np.stack([x * 1e-3, np.zeros(512), np.zeros(512)], axis=1)
    vacuum = np.linalg.norm(coil_field(line, coil_at, A * 1e-3), axis=1)
    axes[0, 2].plot(x, vacuum, "k--", label="coils alone")
    for run, name in runs.items():
        axes[0, 2].plot(x, strength(cuts, run, "mid")[:, 255:257].mean(axis=1), color=colour[name], label=name)
        shell = cuts[f"{run}/rho_electrons/shell"]
        axes[1, 2].plot(1e3 * cell * (np.arange(len(shell)) + 0.5), np.abs(shell) / Q_E, color=colour[name], label=f"electrons, {name}")
        shell = cuts[f"{run}/rho_ions/shell"]
        axes[1, 2].plot(1e3 * cell * (np.arange(len(shell)) + 0.5), shell / Q_E, color=colour[name], ls=":", label=f"ions, {name}")
    axes[0, 2].set(yscale="log", ylim=(0.01, 5), xlim=(0, 24), xlabel="distance from the centre along a coil axis (mm)",
                   ylabel="field strength (T)", title="Field along a coil axis")
    axes[0, 2].axvline(DC, color="grey", lw=0.6)
    axes[0, 2].legend()
    axes[1, 2].set(yscale="log", ylim=(1e17, 3e20), xlim=(0, 24), xlabel="distance from the centre (mm)", ylabel="per m$^3$",
                   title="Density averaged over all directions")
    for radius, what in ((DC, "coil planes"), (RW, "wall")):
        axes[1, 2].axvline(radius, color="grey", lw=0.6)
        axes[1, 2].text(radius, 2e17, what, rotation=90, ha="right", fontsize=8)
    axes[1, 2].legend(fontsize=8)
    figure.suptitle("Magnetic field at 18 ns")
    figure.savefig(out / "cage-field.png", dpi=110)
    plt.close(figure)

    figure, axes = plt.subplots(2, 2, figsize=(14, 8), constrained_layout=True)
    for column, species in enumerate(("electrons", "ions")):
        for row, (run, name) in enumerate(runs.items()):
            sky = np.abs(cuts[f"{run}/rho_{species}/sky"]) / Q_E
            image = axes[row, column].imshow(sky, origin="lower", extent=(-180, 180, -1, 1), aspect="auto", norm=LogNorm(1e17, 1e20), cmap="magma")
            axes[row, column].set(title=f"{species}, {name}", xlabel="angle around the z axis (degrees)", ylabel="cosine of angle from the z axis")
    figure.colorbar(image, ax=axes, shrink=0.8, label="per m$^3$, mean over 19 to 23 mm from the centre")
    figure.suptitle("Where the plasma is on its way out: density between the coils and the wall against direction.\n"
                    "Coil axes are at 0, 90, 180, 270 degrees on the middle line and at the top and bottom edges; corners are at 45 degrees and cosine 0.58")
    figure.savefig(out / "cage-sky.png", dpi=110)
    plt.close(figure)

    figure, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    for name, run in folders.items():
        number = np.loadtxt(run / "diags/reducedfiles/number.txt", skiprows=1)
        energy = np.loadtxt(run / "diags/reducedfiles/energy.txt", skiprows=1)
        fields = np.loadtxt(run / "diags/reducedfiles/fields.txt", skiprows=1)
        axes[0, 0].plot(1e9 * number[:, 1], number[:, 6], color=colour[name], label=f"electrons, {name}")
        axes[0, 0].plot(1e9 * number[:, 1], number[:, 7], color=colour[name], ls=":", label=f"ions, {name}")
        axes[0, 1].plot(1e9 * number[:, 1], (number[:, 7] - number[:, 6]) / number[:, 6], color=colour[name], label=name)
        axes[0, 2].plot(1e9 * energy[:, 1], energy[:, 6] / Q_E / 1e3, color=colour[name], label=f"electrons, {name}")
        axes[0, 2].plot(1e9 * energy[:, 1], energy[:, 7] / Q_E / 1e3, color=colour[name], ls=":", label=f"ions, {name}")
        axes[1, 0].plot(1e9 * fields[:, 1], fields[:, 3], color=colour[name], label=f"electric, {name}")
        axes[1, 0].plot(1e9 * fields[:, 1], fields[:, 4], color=colour[name], ls=":", label=f"plasma's magnetic, {name}")
        for axis, probe, where in ((axes[1, 1], "axis", "a coil axis"), (axes[1, 2], "edge", "the line between two coils")):
            profiles = line_potential(run, probe, 0.0)
            steps = sorted(profiles)[-4:]
            radius = profiles[steps[-1]][0]
            volts = np.mean([profiles[step][1] for step in steps], axis=0)
            axis.plot(1e3 * radius, volts / 1e3, color=colour[name], label=name)
            axis.set(xlabel=f"distance from the centre along {where} (mm)", ylabel="voltage against the wall (kV)",
                     title=f"Voltage along {where} (last four readings)")
    axes[1, 2].axvline(np.hypot(DC, A), color="grey", lw=0.6)
    axes[1, 2].text(np.hypot(DC, A), 0, " 0.9 mm from two rings", fontsize=8)
    axes[0, 0].set(xlabel="time (ns)", ylabel="number in the vessel", title="Plasma held (fed at 2.4e23 per second throughout)")
    axes[0, 1].set(xlabel="time (ns)", ylabel="(ions less electrons) / electrons", title="Charge imbalance of the plasma in the vessel")
    axes[0, 2].set(xlabel="time (ns)", ylabel="mean energy (keV)", title="Mean energy per particle (fed at 100 keV temperature)")
    axes[1, 0].set(xlabel="time (ns)", ylabel="energy (J)", yscale="log", title="Energy in the fields")
    for axis in axes.ravel():
        axis.legend(fontsize=8)
        axis.grid(alpha=0.3)
    figure.savefig(out / "cage-histories.png", dpi=110)
    plt.close(figure)

    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8), constrained_layout=True)
    for name, run in folders.items():
        for species, style in (("e", "-"), ("i", ":")):
            kind = "electrons" if species == "e" else "ions"
            centres, counts = late(run, f"{species}throat")
            width = centres[1] - centres[0]
            axes[0].plot(1e3 * centres, counts / (2 * np.pi * centres * width * 2 * 0.05 * A * 1e-3) / 6, color=colour[name], ls=style, label=f"{kind}, {name}")
            centres, counts = late(run, f"{species}out")
            axes[1].plot(np.degrees(np.arccos(centres)), counts, color=colour[name], ls=style, label=f"{kind}, {name}")
            centres, counts = late(run, f"{species}rad")
            axes[2].plot(1e3 * centres, counts / (4 * np.pi * centres**2 * (centres[1] - centres[0])), color=colour[name], ls=style, label=f"{kind}, {name}")
    axes[0].set(xlabel="distance from the coil axis, in the plane of a coil (mm)", ylabel="per m$^3$", yscale="log",
                title="The stream through the middle of a coil (last fifth of the run)")
    axes[0].axvspan(A - RM, A, color="grey", alpha=0.3)
    axes[1].set(xlabel="angle from the nearest coil axis (degrees)", ylabel="number beyond 19 mm, per bin",
                title="Plasma outside the coils, by direction (corners are at 55 degrees)")
    axes[2].set(xlabel="distance from the centre (mm)", ylabel="per m$^3$", yscale="log", title="Density against radius, from the particle counts")
    for axis in axes:
        axis.legend(fontsize=8)
        axis.grid(alpha=0.3)
    figure.savefig(out / "cage-streams.png", dpi=110)
    plt.close(figure)
