"""Cut mid-plane maps of voltage and electron density out of the WarpX plotfiles of cusp-cage runs.

Usage: slices.py OUT.npz RUN_DIR [RUN_DIR ...]

Reads single-box plotfiles holding phi and rho directly, so it needs only NumPy. Each map is averaged
over the three coordinate planes through the centre and their eight in-plane symmetries, which the
device has by construction; the density is also averaged over a slab four cells thick. That averaging
hides any asymmetry in the run, so use the plotfiles themselves to look for one.
"""
import sys
from pathlib import Path

import numpy as np

Q_E = 1.602176634e-19


def read(plotfile: Path) -> tuple[np.ndarray, np.ndarray, float]:
    header = (plotfile / "Header").read_text().split("\n")
    assert header[2:4] == ["phi", "rho"], header[:5]
    time = float(header[5])
    with open(plotfile / "Level_0/Cell_D_00000", "rb") as data:
        shape = data.readline().decode().split("))((0,0,0) (")[1].split(")")[0]
        n = int(shape.split(",")[0]) + 1
        cube = np.frombuffer(data.read(2 * n**3 * 8), dtype="<f8").reshape(2, n, n, n)
    # Fortran order on disk: the last index varies slowest, so axes arrive as (z, y, x).
    return cube[0].transpose(2, 1, 0), cube[1].transpose(2, 1, 0), time


def symmetric_plane(field: np.ndarray, half_width: int) -> np.ndarray:
    n = field.shape[0]
    slab = slice(n // 2 - half_width, n // 2 + half_width)
    planes = [field[:, :, slab].mean(axis=2), field[:, slab, :].mean(axis=1), field[slab, :, :].mean(axis=0)]
    total = np.zeros((n, n))
    for plane in planes:
        for image in (plane, plane.T):
            total += image + image[::-1] + image[:, ::-1] + image[::-1, ::-1]
    return total / 24


if __name__ == "__main__":
    out = {}
    for path in sys.argv[2:]:
        run = Path(path)
        files = sorted(p for p in (run / "diags").glob("diag1*") if (p / "Level_0/Cell_D_00000").exists())
        maps = [read(p) for p in files if p.name != "diag1000000"]
        if maps:
            out[f"{run.name}/time_ns"] = np.array([1e9 * t for _, _, t in maps])
            out[f"{run.name}/phi_V"] = np.array([symmetric_plane(phi, 1) for phi, _, _ in maps], dtype=np.float32)
            out[f"{run.name}/n_e_m3"] = np.array([symmetric_plane(-rho / Q_E, 2) for _, rho, _ in maps], dtype=np.float32)
    np.savez_compressed(sys.argv[1], **out)
    print({k: v.shape for k, v in out.items()})
