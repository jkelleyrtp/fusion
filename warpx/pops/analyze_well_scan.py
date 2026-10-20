"""Rank electron-only wells by how well ions of different amplitude would stay in step (WarpX FieldProbe output).

For each run, average the radial field over the samples after `--after` seconds, fit the potential with an even
polynomial, and compute the bounce period of a radial ion orbit against its turning radius. A harmonic well has one
period for all radii; the spread of periods over a Gaussian ion cloud is what dephases successive collapses.
"""
import argparse
import json
from pathlib import Path

import numpy as np

E, AMU = 1.602176634e-19, 1.66053907e-27


def reduce(run: Path, after: float, s0_over_a: float, mass_amu: float) -> dict:
    probe = np.loadtxt(run / "diags/reducedfiles/probe.txt", skiprows=1)  # its header line has no comment marker
    probe = probe[probe[:, 1] >= after]
    steps = np.unique(probe[:, 0])
    x = np.sort(probe[probe[:, 0] == steps[0], 2])
    field = np.mean([probe[probe[:, 0] == step][np.argsort(probe[probe[:, 0] == step, 2]), 5] for step in steps], axis=0)
    a = x[-1]
    phi = np.array([np.trapezoid(field[i:], x[i:]) for i in range(len(x))])  # wall at 0 V
    fit = np.polynomial.Polynomial.fit((x / a) ** 2, phi / phi[0], 5)  # even powers of r up to r^10

    theta = (np.arange(400) + 0.5) * (np.pi / 2) / 400
    turning = np.linspace(0.05, 0.9, 35)
    period = []
    for r0 in turning:  # quarter period = integral of dr / v with r = r0 sin(theta)
        drop = (fit(r0**2) - fit((r0 * np.sin(theta)) ** 2)) * phi[0]  # volts climbed from r to the turning point
        if drop.min() <= 0:  # not a monotonic well (e.g. ion charge at the centre): no bounce period to report
            return {"run": run.name, "well_centre_V": round(float(phi[0])), "period_spread": None}
        speed = np.sqrt(2 * E * drop / (mass_amu * AMU))
        period.append(4 * np.sum(r0 * a * np.cos(theta) / speed) * (theta[1] - theta[0]))
    period = np.array(period)
    weight = turning**2 * np.exp(-(turning**2) / (2 * s0_over_a**2))  # ions starting at rest in a Gaussian cloud
    mean = np.sum(weight * period) / np.sum(weight)
    spread = np.sqrt(np.sum(weight * (period - mean) ** 2) / np.sum(weight)) / mean
    predicted = test_ion_compression(fit.deriv(), phi[0], a, s0_over_a, mass_amu, 3.6 * mean)
    return {
        "run": run.name,
        "predicted_compression": predicted,
        "well_centre_V": round(float(phi[0])),
        "well_half_radius_over_centre": round(float(np.interp(0.5 * a, x, phi) / phi[0]), 3),
        "bounce_period_ns": round(float(mean) * 1e9, 2),
        "period_spread": round(float(spread), 4),
        "collapses_in_step": round(float(0.25 / spread), 1),  # bounces until the cloud is a quarter period out of step
        "period_inner_over_outer": round(float(np.interp(0.15, turning, period) / np.interp(0.6, turning, period)), 3),
    }


def test_ion_compression(slope, centre: float, a: float, s0_over_a: float, mass_amu: float, duration: float) -> list[float]:
    """Compression at each collapse of chargeless test ions released at 1 eV from a Gaussian cloud in the fitted well."""
    rng = np.random.default_rng(0)
    position = rng.normal(0, s0_over_a * a, (6000, 3))
    position = position[np.linalg.norm(position, axis=1) < 0.95 * a]
    velocity = rng.normal(0, np.sqrt(E / (mass_amu * AMU)), position.shape)
    dt = duration / 12000

    def acceleration(at: np.ndarray) -> np.ndarray:
        u = np.minimum(np.sum(at**2, axis=1) / a**2, 1.0)
        return (-E * centre * slope(u) * 2 / a**2 / (mass_amu * AMU))[:, None] * at

    radius = []
    velocity += 0.5 * dt * acceleration(position)
    for _ in range(12000):
        position += dt * velocity
        velocity += dt * acceleration(position)
        radius.append(np.sqrt(np.mean(np.sum(position**2, axis=1))))
    radius = np.array(radius)
    minima = [i for i in range(1, len(radius) - 1) if radius[i] < radius[i - 1] and radius[i] <= radius[i + 1]
              and radius[i] < 0.7 * radius[0]]
    return [round(float(s0_over_a * a * np.sqrt(3) / radius[i]), 1) for i in minima]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--after", type=float, default=2e-9)
    parser.add_argument("--s0-over-a", type=float, default=0.3)
    parser.add_argument("--mass-amu", type=float, default=2.014)
    args = parser.parse_args()
    for run in args.runs:
        print(json.dumps(reduce(run, args.after, args.s0_over_a, args.mass_amu)))
