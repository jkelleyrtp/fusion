"""Plot well profiles, ion radius and centre potential over time for POPS runs: plot_well_shape.py out.png label=run_dir ..."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_electron_well import potential

out, runs = sys.argv[1], [arg.split("=", 1) for arg in sys.argv[2:]]
figure, (profile, radius_axis, centre_axis) = plt.subplots(1, 3, figsize=(16, 4.6))
for label, name in runs:
    files = Path(name) / "diags/reducedfiles"
    ions = np.loadtxt(files / "ibeam.txt")
    probe = np.loadtxt(files / "probe.txt", skiprows=1)
    radius = np.sqrt((ions[:, 9:12] ** 2).sum(axis=1))
    steps = np.unique(probe[:, 0])[1:]
    wells = [potential(probe[probe[:, 0] == step]) for step in steps]
    ion_radius = np.interp(steps, ions[:, 0], radius)
    x, phi = wells[int(np.argmax(ion_radius))]  # the snapshot with the ions furthest out
    line, = profile.plot(x * 1e3, phi / phi[0], label=f"{label} ({phi[0] / 1e3:.1f} kV)")
    radius_axis.plot(ions[:, 1] * 1e9, radius * 1e3, color=line.get_color(), label=label)
    times = np.interp(steps, ions[:, 0], ions[:, 1])
    centre_axis.plot(times * 1e9, [well[1][0] / 1e3 for well in wells], color=line.get_color(), label=label)
r = np.linspace(0, 10, 50)
profile.plot(r, 1 - (r / 10) ** 2, "k--", label="harmonic")
profile.set(xlabel="radius (mm)", ylabel="potential / centre potential", title="Well shape with the ions out")
radius_axis.set(xlabel="time (ns)", ylabel="ion rms radius (mm)", yscale="log", title="Ion cloud radius")
centre_axis.set(xlabel="time (ns)", ylabel="centre potential (kV)", title="Centre potential (sampled each 1 ns)")
for axis in (profile, radius_axis, centre_axis):
    axis.grid(alpha=0.3)
    axis.legend(fontsize=8)
figure.tight_layout()
figure.savefig(out, dpi=130)
