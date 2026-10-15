"""Breathing period and compression of a POPS ion cloud from WarpX BeamRelevant output."""
import argparse
import json
import math
from pathlib import Path

import numpy as np

E, EPS0, AMU = 1.602176634e-19, 8.8541878128e-12, 1.66053907e-27


def reduce(run: Path, a: float, phi0: float, mass_amu: float) -> dict:
    data = np.loadtxt(run / "diags/reducedfiles/beam.txt")
    time, radius = data[:, 1], np.sqrt((data[:, 9:12] ** 2).sum(axis=1))
    omega = math.sqrt(2 * E * phi0 / (mass_amu * AMU * a * a))
    inner = np.flatnonzero((radius[1:-1] < radius[:-2]) & (radius[1:-1] <= radius[2:])) + 1
    minima = [i for i in inner if radius[i] < 0.7 * radius[0]]
    periods = np.diff(time[minima])
    return {
        "run": run.name,
        "predicted_breathing_period_s": math.pi / omega,
        "measured_breathing_period_s": float(periods.mean()) if len(periods) else None,
        "collapses": len(minima),
        "compression_first": float(radius[0] / radius[minima[0]]) if minima else None,
        "compression_last": float(radius[0] / radius[minima[-1]]) if minima else None,
        "charge_kept": float(data[-1, 23] / data[0, 23]),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--a", type=float, default=0.01)
    parser.add_argument("--phi0", type=float, default=1e4)
    parser.add_argument("--mass-amu", type=float, default=2.014)
    args = parser.parse_args()
    for run in args.runs:
        print(json.dumps(reduce(run, args.a, args.phi0, args.mass_amu)))
