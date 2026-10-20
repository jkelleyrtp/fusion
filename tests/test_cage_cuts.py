"""The plotfile reader puts each box where its header says, and the cuts come out on the axes the docstring names."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "warpx/cusp"))
import cage_cuts


def write_plotfile(folder: Path, fields: np.ndarray, low: float, cell: float) -> None:
    count, n = fields.shape[:2]
    half = n // 2
    (folder / "Level_0").mkdir(parents=True)
    header = ["HyperCLaw-V1.1", str(count), *[f"f{i}" for i in range(count)], "3", "0.5", "0",
              f"{low} {low} {low}", f"{-low} {-low} {-low}", "", f"((0,0,0) ({n - 1},{n - 1},{n - 1}) (0,0,0))", "1",
              f"{cell} {cell} {cell}"]
    (folder / "Header").write_text("\n".join(header) + "\n")
    index = []
    with open(folder / "Level_0/Cell_D_00000", "wb") as data:
        for x0 in (0, half):
            index.append(f"FabOnDisk: Cell_D_00000 {data.tell()}")
            data.write(f"FAB ((8, (64 11 52 0 1 12 0 1023)),(8, (8 7 6 5 4 3 2 1)))(({x0},0,0) ({x0 + half - 1},{n - 1},{n - 1}) (0,0,0)) {count}\n".encode())
            data.write(np.ascontiguousarray(fields[:, x0:x0 + half].transpose(0, 3, 2, 1)).tobytes())
    (folder / "Level_0/Cell_H").write_text("1\n1\n" + "\n".join(index) + "\n")


class CageCuts(unittest.TestCase):
    def test_boxes_land_where_their_headers_say_and_cuts_follow_the_named_axes(self):
        n, cell = 16, 0.25
        low = -n * cell / 2
        centre = low + cell * (np.arange(n) + 0.5)
        x, y, z = np.meshgrid(centre, centre, centre, indexing="ij")
        fields = np.array([x + 10 * y + 100 * z, np.ones_like(x)])
        with tempfile.TemporaryDirectory() as folder:
            write_plotfile(Path(folder) / "p", fields, low, cell)
            names, read, read_low, read_cell = cage_cuts.read(Path(folder) / "p")
        self.assertEqual(names, ["f0", "f1"])
        self.assertEqual((read_low, read_cell), (low, cell))
        np.testing.assert_array_equal(read, fields)
        cut = cage_cuts.cuts(read[0], low, cell, a=0.5, dc=1.1)
        np.testing.assert_allclose(cut["mid"], (x + 10 * y)[:, :, 0], atol=1e-12)
        np.testing.assert_allclose(cut["diag"], 11 * centre[:, None] + 100 * centre[None, :])
        np.testing.assert_allclose(cut["coil"], centre[12] + 10 * centre[:, None] + 100 * centre[None, :])
        np.testing.assert_allclose(cut["column"], (x + 10 * y)[:, :, 0] * n * cell, atol=1e-9)
        ones = cage_cuts.cuts(read[1], low, cell, a=0.5, dc=1.1)
        np.testing.assert_allclose(ones["shell"], 1)
        self.assertEqual(ones["sky"].shape, cage_cuts.SKY_BINS)


if __name__ == "__main__":
    unittest.main()
