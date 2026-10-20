"""Plot ion-cloud compression at each collapse: full electron-plus-ion runs against the test-ion prediction from the electron-only well."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(path: Path, key: str) -> dict[str, list[float]]:
    rows = map(json.loads, path.read_text().splitlines())
    return {row["run"]: row[key] for row in rows if key in row}  # non-monotonic wells have no prediction


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--predicted", type=Path, nargs="+", required=True, help="analyze_well_scan.py output (JSON lines)")
    parser.add_argument("--measured", type=Path, nargs="+", required=True, help="analyze_electron_well.py output (JSON lines)")
    parser.add_argument("--pair", action="append", required=True, help="label=measured_run=predicted_run")
    args = parser.parse_args()
    predicted = {run: values for path in args.predicted for run, values in load(path, "predicted_compression").items()}
    measured = {run: values for path in args.measured for run, values in load(path, "compression").items()}
    figure, axis = plt.subplots(figsize=(7.5, 4.8))
    for index, pair in enumerate(args.pair):
        label, measured_run, predicted_run = pair.split("=")
        colour = f"C{index}"
        full = measured[measured_run]
        axis.plot(range(1, len(full) + 1), full, "o-", color=colour, label=label)
        test = predicted[predicted_run][: len(full) + 2]
        axis.plot(range(1, len(test) + 1), test, "--", color=colour, alpha=0.6)
    axis.plot([], [], "o-", color="k", label="electrons and ions")
    axis.plot([], [], "--", color="k", alpha=0.6, label="test ions in the electron-only well")
    axis.set_xlabel("collapse number")
    axis.set_ylabel("compression (initial rms radius / minimum)")
    axis.set_ylim(0)
    axis.grid(alpha=0.3)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(args.output, dpi=150)
