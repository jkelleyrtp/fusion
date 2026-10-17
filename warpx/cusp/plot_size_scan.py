"""Draw the picket-fence size scan: holding time and leak widths against device size in electron orbits.

Usage: plot_size_scan.py TABLE.jsonl OUT.png [PREFIX]

Reads the rows `campaign.py sync` writes, keeps the cases whose names start with PREFIX (default `pm_s`) and
end in the inventory level `_h<level>`, and prints the table and the power-law fits it draws. A fit is made
only across cases of one inventory level, and only when there are at least three sizes of it.
"""
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SIZE = "coil_radius_in_electron_orbits_at_edge"
PANELS = (("electrons_holding_time_in_electron_crossings", "holding time (electron crossings)"),
          ("gap_stream_in_electron_orbits", "gap stream half-height (electron orbits)"),
          ("current_layer_width_in_orbits_at_fed_temperature", "current layer width (electron orbits)"))


def load(table: Path, prefix: str) -> list[dict]:
    rows = []
    for line in table.read_text().splitlines():
        row = json.loads(line)
        name = re.fullmatch(re.escape(prefix) + r"([0-9.]+)_h([0-9.]+)", row["case"])
        if name and SIZE in row:
            row["scale"], row["level"] = float(name.group(1)), name.group(2)
            row["gap_stream_in_electron_orbits"] = row["electron_stream_half_height_in_gap_mm"] / row["electron_orbit_at_edge_mm"]
            rows.append(row)
    return sorted(rows, key=lambda row: (row["level"], row["scale"]))


def exponent(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """The slope of log y against log x, and its standard error from the scatter about the line."""
    slope, offset = np.polyfit(np.log(x), np.log(y), 1)
    left = np.log(y) - slope * np.log(x) - offset
    error = np.sqrt(left @ left / max(len(x) - 2, 1) / ((np.log(x) - np.log(x).mean()) ** 2).sum())
    return float(slope), float(error)


def main() -> None:
    table, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = load(table, sys.argv[3] if len(sys.argv) > 3 else "pm_s")
    print("case  radius/orbit  pressure ratio  drift over last fifth  holding  gap stream  current layer")
    for row in rows:
        print(f"{row['case']:16s} {row[SIZE]:6.0f} {row['pressure_inside_over_magnetic_outside_edge']:6.2f} "
              f"{row['electrons_held_change_over_last_fifth']:+7.3f} {row[PANELS[0][0]]:7.1f} "
              f"{row[PANELS[1][0]]:6.2f} {row[PANELS[2][0]]:6.2f}")
    levels = sorted({row["level"] for row in rows}, key=float)
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    for axis, (key, label) in zip(axes, PANELS):
        for level, colour in zip(levels, ("tab:blue", "tab:green", "tab:red", "tab:purple")):
            mine = [row for row in rows if row["level"] == level]
            x, y = np.array([row[SIZE] for row in mine]), np.array([row[key] for row in mine])
            text = f"{level}× inventory"
            if len({row["scale"] for row in mine}) >= 3:
                slope, error = exponent(x, y)
                text += f": size^{slope:.2f}±{error:.2f}"
                print(f"{key} at inventory {level}: exponent {slope:.3f} +- {error:.3f} over {len(mine)} sizes")
            axis.loglog(x, y, "o-", color=colour, label=text)
        axis.set_xlabel("coil radius (electron orbits at the plasma edge)")
        axis.set_ylabel(label)
        axis.grid(True, which="both", alpha=0.3)
        axis.legend(fontsize=8)
    reach = np.array(axes[0].get_xlim())
    axes[0].loglog(reach, reach * rows[0][PANELS[0][0]] / rows[0][SIZE], ":", color="grey", label="size^1")
    axes[0].legend(fontsize=8)
    figure.suptitle("Picket-fence cusp, 100 keV, ions 64 electron masses: size scan at three inventories")
    figure.tight_layout()
    figure.savefig(out, dpi=130)


if __name__ == "__main__":
    main()
