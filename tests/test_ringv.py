"""The decks with the six rings held at a set voltage, and the reducer that reads the voltage they reach."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy import ndimage

CUSP = Path(__file__).resolve().parents[1] / "warpx/cusp"
sys.path.insert(0, str(CUSP))
import analyze_ringv
import make_deck

A = 0.01
SIZES = {"rw": 2.4 * A, "rc": A, "dc": 1.3 * A, "rm": 0.12 * A, "rs": 0.06 * A}


def pieces(metal: str, cells: int = 128) -> int:
    """How many separate pieces of metal the expression describes, on a mesh of the box."""
    centres = (np.arange(cells) + 0.5) / cells * 5 * A - 2.5 * A
    x, y, z = np.meshgrid(centres, centres, centres, indexing="ij")
    inside = eval(metal, {"max": np.maximum, "min": np.minimum, "sqrt": np.sqrt, "x": x, "y": y, "z": z, **SIZES}) > 0
    return ndimage.label(inside)[1]


class RingVoltageTest(unittest.TestCase):
    def test_the_decks_on_disk_are_the_ones_the_generator_writes(self) -> None:
        self.assertEqual((CUSP / "inputs_3d_cusp_ringv").read_text(), make_deck.ringv_deck())
        self.assertEqual((CUSP / "inputs_3d_cusp_ringv_stalks").read_text(), make_deck.ringv_deck(make_deck.stalks()))
        self.assertEqual((CUSP / "inputs_3d_cusp_ringv_stubs").read_text(), make_deck.ringv_deck(make_deck.stalks("2*rs")))
        self.assertEqual((CUSP / "inputs_3d_cusp_ringv_unit").read_text(), make_deck.ringv_deck() + make_deck.UNIT)

    def test_rods_join_every_ring_to_the_wall_and_stubs_leave_them_apart(self) -> None:
        self.assertEqual(pieces(make_deck.CONDUCTOR), 7)
        self.assertEqual(pieces(make_deck.stalks()), 1)
        self.assertEqual(pieces(make_deck.stalks("2*rs")), 7)

    def test_only_the_metal_differs_between_the_decks_and_all_measure_the_ring_voltage(self) -> None:
        plain, rods = make_deck.ringv_deck(), make_deck.ringv_deck(make_deck.stalks())
        self.assertEqual(rods.replace(make_deck.stalks(), make_deck.CONDUCTOR), plain + "eb2.cover_multiple_cuts = 1\n")
        self.assertTrue(plain.startswith(make_deck.beta_deck(fed=True)))
        for line in analyze_ringv.LINES:
            self.assertIn(f"{line}.resolution = {analyze_ringv.PROBE_POINTS}", plain)

    def test_the_voltage_is_the_field_summed_from_ring_to_wall(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            (run / "diags/reducedfiles").mkdir(parents=True)
            along = np.linspace(0, 1, analyze_ringv.PROBE_POINTS)
            for index, name in enumerate(analyze_ringv.LINES):
                rows = []
                for step, volts in ((0, 1e5), (10, 2e5)):
                    place = np.zeros((len(along), 3))
                    place[:, index] = 0.013 + 0.01 * along
                    field = np.zeros((len(along), 3))
                    field[:, index] = volts / 0.01 * 2 * along  # the voltage falls by `volts` along the line
                    rows += [[step, step * 1e-12, *p, *e, 0, 0, 0, 0] for p, e in zip(place, field)]
                np.savetxt(run / f"diags/reducedfiles/{name}.txt", rows, header="h")
            time, volts = analyze_ringv.ring_voltages(run)
        np.testing.assert_allclose(time, [0, 1e-11])
        np.testing.assert_allclose(volts, [[1e5, 2e5]] * 3, rtol=1e-4)

    def test_landing_points_are_sorted_into_rings_wall_and_rods(self) -> None:
        c = {"a": A, **SIZES}
        points = np.array([[1.3 * A, A + 0.12 * A, 0.0], [0.0, 0.0, 2.4 * A], [1.8 * A, 0.924 * A + 0.06 * A, 0.383 * A]])
        self.assertEqual(analyze_ringv.surface(points, c, 5 * A / 512).tolist(), [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
