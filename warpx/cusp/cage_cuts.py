"""Cut planes, a column sum and a sky map out of the last plotfile of 3D cage runs, small enough to copy home.

    python3 cage_cuts.py OUT.npz RUN_DIR [RUN_DIR ...]

Needs only NumPy. Nothing is averaged over the device's symmetries, so what is lopsided in the run stays lopsided
here. For each run and each field in the plotfile it keeps:

- `mid`: the plane z = 0 (mean of the two cell layers either side), axes (x, y)
- `diag`: the plane x = y, axes (x = y, z); it holds a coil axis (z), an edge direction and two corner directions
- `coil`: the plane x = `dc`, which a coil lies in, axes (y, z)
- `column`: the sum along z times the cell size, axes (x, y)
- `sky`: the mean over radii `SKY_SHELL` (in units of `a`) against direction, axes (cos of polar angle, azimuth)
- `shell`: the mean over all directions against radius
"""
import re
import sys
from pathlib import Path

import numpy as np

SKY_SHELL = (1.9, 2.3)   # outside the coils (1.3 to 1.64), inside the wall (2.4)
SKY_BINS = (90, 180)


def read(plotfile: Path) -> tuple[list[str], np.ndarray, float, float]:
    """Field names, the fields as one array (field, x, y, z), the low corner (m) and the cell size (m)."""
    header = (plotfile / "Header").read_text().split("\n")
    count = int(header[1])
    names = header[2:2 + count]
    low = float(header[count + 5].split()[0])
    n = int(header[count + 8].split(") (")[1].split(",")[0]) + 1
    cell = float(header[count + 10].split()[0])
    fields = np.empty((count, n, n, n))
    for name, offset in re.findall(r"FabOnDisk: (\S+) (\d+)", (plotfile / "Level_0/Cell_H").read_text()):
        with open(plotfile / "Level_0" / name, "rb") as data:
            data.seek(int(offset))
            box = re.search(r"\(\((\d+),(\d+),(\d+)\) \((\d+),(\d+),(\d+)\)", data.readline().decode())
            x0, y0, z0, x1, y1, z1 = (int(edge) for edge in box.groups())
            shape = (count, z1 - z0 + 1, y1 - y0 + 1, x1 - x0 + 1)   # Fortran order on disk: x varies fastest
            block = np.frombuffer(data.read(8 * int(np.prod(shape))), dtype="<f8").reshape(shape)
            fields[:, x0:x1 + 1, y0:y1 + 1, z0:z1 + 1] = block.transpose(0, 3, 2, 1)
    return names, fields, low, cell


def cuts(field: np.ndarray, low: float, cell: float, a: float, dc: float) -> dict[str, np.ndarray]:
    n = field.shape[0]
    half = n // 2
    centre = low + cell * (np.arange(n) + 0.5)
    x, y, z = np.meshgrid(centre, centre, centre, indexing="ij", sparse=True)
    radius = np.sqrt(x * x + y * y + z * z)
    inside = (radius > SKY_SHELL[0] * a) & (radius < SKY_SHELL[1] * a)
    cosine = np.broadcast_to(z / radius, radius.shape)[inside]
    azimuth = np.broadcast_to(np.arctan2(y, x), radius.shape)[inside]
    edges = (np.linspace(-1, 1, SKY_BINS[0] + 1), np.linspace(-np.pi, np.pi, SKY_BINS[1] + 1))
    sky = np.histogram2d(cosine, azimuth, edges, weights=field[inside])[0] / np.histogram2d(cosine, azimuth, edges)[0]
    rings = np.arange(0, -low + cell, cell)
    shell = np.histogram(radius, rings, weights=field)[0] / np.histogram(radius, rings)[0]
    return {"mid": field[:, :, half - 1:half + 1].mean(axis=2), "diag": field[np.arange(n), np.arange(n), :],
            "coil": field[int((dc - low) / cell)], "column": field.sum(axis=2) * cell, "sky": sky, "shell": shell}


if __name__ == "__main__":
    out = {}
    for run in map(Path, sys.argv[2:]):
        used = (run / "warpx_used_inputs").read_text()   # WarpX echoes each constant's value after a #
        c = {name: float(re.search(rf"^my_constants\.{name} = .*# (\S+)", used, re.MULTILINE).group(1)) for name in ("a", "dc")}
        names, fields, low, cell = read(max((run / "diags").glob("diag1*")))
        out[f"{run.name}/low_cell_a_dc"] = np.array([low, cell, c["a"], c["dc"]])
        for name, field in zip(names, fields):
            for cut, values in cuts(field, low, cell, c["a"], c["dc"]).items():
                out[f"{run.name}/{name}/{cut}"] = values.astype(np.float32)
        print(run.name, names, fields.shape, flush=True)
    np.savez_compressed(sys.argv[1], **out)
