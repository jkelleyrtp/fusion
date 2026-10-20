"""Two-coil cusp at three sizes: electron density with field lines, the stream between the coils, and the size scaling."""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

QE = 1.602176634e-19
CASES = [("pw1/zw15_f1.8e22_long@1", "15 (coils 29 kA)", 1.668, "tab:blue"),
         ("pw1/zw30_f4.5e22_long@1", "30 (59 kA)", 0.834, "tab:green"),
         ("sp2/zw60_f1.1e23_long@1", "60 (117 kA)", 0.417, "tab:red")]
archive = np.load(sys.argv[1])
names = list(archive["names"])
figure, axes = plt.subplots(2, 3, figsize=(17, 9.5), constrained_layout=True, height_ratios=[1, 1.25])
cmap = plt.get_cmap("inferno").copy()
cmap.set_bad("black")
for axis, (key, label, orbit, colour) in zip(axes[0], CASES):
    fields = dict(zip(names, archive[key].astype(float)))
    nz, nr = fields["Bz"].shape
    r = (np.arange(nr) + 0.5) / nr * 20
    z = (np.arange(nz) + 0.5) / nz * 40 - 20
    density = np.maximum(-fields["rho_electrons"] / QE, 1e10)
    image = axis.imshow(density.T, origin="lower", extent=(-20, 20, 0, 20), norm=LogNorm(1e18, 2e21), cmap=cmap, aspect="equal")
    flux = np.cumsum(r * fields["Bz"], axis=1)
    levels = np.linspace(-1, 1, 30) * np.abs(flux).max() * 0.6
    axis.contour(z, r, flux.T, levels=levels[levels != 0], colors="w", linewidths=0.35, linestyles="solid")
    axis.plot([-10, 10], [10, 10], "o", color="cyan", ms=6)
    axis.set(title=f"Size {label}: electrons at {float(archive[key + '_t']) * 1e9:.0f} ns, field lines in white", xlabel="distance along the axis (mm)", ylabel="distance from the axis (mm)")
    middle = density[:, (r > 14.5) & (r < 15.5)].mean(axis=1)
    along = z
    axes[1, 0].plot(along, middle / middle.max(), color=colour, label=label)
    axes[1, 1].plot(along / orbit, middle / middle.max(), color=colour, label=label)
figure.colorbar(image, ax=axes[0], shrink=0.6, label="electrons per m$^3$")
axes[1, 0].set(xlim=(-4, 4), xlabel="distance from the mid-plane (mm), at 15 mm from the axis", ylabel="electron density / its peak",
               title="Stream leaving between the coils, in mm")
axes[1, 1].set(xlim=(-5, 5), xlabel="distance from the mid-plane (electron orbits there)", ylabel="electron density / its peak",
               title="The same stream in electron orbits")
for axis in axes[1, :2]:
    axis.legend(fontsize=8, loc="upper right", title="size (coil radius\nin electron orbits)", title_fontsize=8)
    axis.grid(alpha=0.3)
models = [("Row of coils, wrap-around ends", [0.25, 0.375, 0.5, 0.75, 1], [34.2, 45.2, 52.5, 73.0, 91.2], "o-", "tab:purple", 0.71),
          ("Row of coils, mirror ends", [0.25, 0.375, 0.5], [42.4, 50.2, 59.7], "s-", "tab:orange", 0.49),
          ("Two coils, real end walls", [0.25, 0.5, 1], [3.99, 5.95, 8.51], "^-", "tab:red", 0.55)]
axis = axes[1, 2]
for label, size, held, style, colour, power in models:
    axis.plot(np.array(size) / size[0], np.array(held) / held[0], style, color=colour, label=f"{label}: size$^{{{power}}}$")
span = np.array([1, 4])
axis.plot(span, span, "k--", lw=0.8, label="leak of fixed width in orbits: size$^1$")
axis.plot(span, span**0, "k:", lw=0.8, label="leak grows with the device: size$^0$")
axis.set(xscale="log", yscale="log", xlabel="size / smallest size run (coil radius in electron orbits)", ylabel="holding time / at the smallest size",
         title="Holding time against size, three models of the ends")
axis.set_xticks([1, 2, 4], ["1", "2", "4"])
axis.set_yticks([1, 2, 4], ["1", "2", "4"])
axis.legend(fontsize=8)
axis.grid(alpha=0.3, which="both")
figure.savefig(sys.argv[2], dpi=110)
