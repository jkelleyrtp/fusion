"""Core of the collapsed ion cloud from the radial histograms: size, density, charge cancelled, potential."""
import json
import sys
from pathlib import Path

import numpy as np

E_CHARGE, COULOMB, A = 1.602176634e-19, 8.9875517923e9, 0.01


def shell_potential(charge: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Potential at the bin edges of spherical shells of charge, with the wall at 0 V."""
    mid = 0.5 * (edges[1:] + edges[:-1])
    inside = np.concatenate([[0.0], np.cumsum(charge)])
    outer = np.concatenate([np.cumsum((charge / mid)[::-1])[::-1], [0.0]])
    phi = COULOMB * (np.divide(inside, edges, out=np.zeros_like(edges), where=edges > 0) + outer)
    return phi - phi[-1]


def mesh_potential(snapshot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(snapshot[:, 2])
    x, ex = snapshot[order, 2], snapshot[order, 5]
    return x, np.array([np.trapezoid(ex[i:], x[i:]) for i in range(len(x))])


def reduce(run: Path) -> dict:
    files = run / "diags/reducedfiles"
    hist = {name: np.loadtxt(files / f"{name}.txt") for name in ("irad", "erad", "krad", "crad")}
    ions = np.loadtxt(files / "ibeam.txt")
    probe = np.loadtxt(files / "probe.txt", skiprows=1)
    radius = np.sqrt((ions[:, 9:12] ** 2).sum(axis=1))
    first = ions[:, 1] < 3.0e-8
    collapse = np.argmin(np.where(first, radius, np.inf))
    row = np.argmin(np.abs(hist["irad"][:, 1] - ions[collapse, 1]))
    bins = hist["irad"].shape[1] - 2
    edges = np.linspace(0.0, A, bins + 1)
    volume = 4.0 / 3.0 * np.pi * np.diff(edges**3)
    count = {name: table[row, 2:] for name, table in hist.items()}
    cumulative = {name: np.cumsum(c) for name, c in count.items()}
    total = cumulative["irad"][-1]
    at = lambda name, r: float(np.interp(r, edges[1:], cumulative[name]))
    half, tenth = (float(np.interp(share * total, cumulative["irad"], edges[1:])) for share in (0.5, 0.1))
    density, start = count["irad"] / volume, hist["irad"][0, 2:] / volume
    charge = E_CHARGE * (count["irad"] - count["erad"] - count["krad"] - count["crad"])
    step = probe[np.argmin(np.abs(probe[:, 1] - hist["irad"][row, 1])), 0]
    _, mesh = mesh_potential(probe[probe[:, 0] == step])
    return {
        "run": run.name,
        "collapse_ns": round(float(ions[collapse, 1]) * 1e9, 2),
        "compression": round(float(radius[0] / radius[collapse]), 2),
        "rms_radius_mm": round(float(radius[collapse]) * 1e3, 3),
        "half_ion_radius_mm": round(half * 1e3, 3),
        "tenth_ion_radius_mm": round(tenth * 1e3, 3),
        "slow_over_ions_in_half_radius": round(at("crad", half) / at("irad", half), 3),
        "slow_over_ions_in_1mm": round(at("crad", 1e-3) / at("irad", 1e-3), 3),
        "ion_density_in_half_radius_m3": float(0.5 * total / (4.0 / 3.0 * np.pi * half**3)),
        "density_squared_gain": round(float((density**2 * volume).sum() / (start**2 * volume).sum()), 1),
        "centre_from_particles_kV": round(float(shell_potential(charge, edges)[0]) / 1e3, 2),
        "centre_on_mesh_kV": round(float(mesh[0]) / 1e3, 2),
    }


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(json.dumps(reduce(Path(name))))
