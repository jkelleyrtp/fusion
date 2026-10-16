"""The spindle-cusp deck and its reducer: the two must agree on the coil field."""
import math
import sys
import typing
import unittest
from pathlib import Path

import numpy as np

CUSP = Path(__file__).resolve().parents[1] / "warpx/cusp"
sys.path.insert(0, str(CUSP))
import analyze_spindle
import make_deck


def elliptic(k: float) -> tuple[float, float]:
    """Complete elliptic integrals of the first and second kind at modulus k, by the arithmetic-geometric mean."""
    a, b, total, power = 1.0, math.sqrt(1 - k * k), k * k / 2, 0.5
    while abs(a - b) > 1e-15:
        a, b, gap = (a + b) / 2, math.sqrt(a * b), (a - b) / 2
        power *= 2
        total += power * gap * gap
    return math.pi / (2 * a), math.pi / (2 * a) * (1 - total)


class SpindleTest(unittest.TestCase):
    constants: typing.ClassVar = {"a": 0.01, "dc": 0.012, "rc": 0.009, "coil_at": 16000.0}

    def deck_field(self, r: float, z: float) -> tuple[float, float]:
        """The coil field the deck gives WarpX at (x, y, z) = (r, 0, z), evaluated from its own formula."""
        names = {**self.constants, "x": r, "y": 0.0, "z": z, "mu0": 4e-7 * math.pi, "pi": math.pi, "sqrt": math.sqrt,
                 "comp_ellint_1": lambda k: elliptic(k)[0], "comp_ellint_2": lambda k: elliptic(k)[1]}
        return tuple(sum(eval(make_deck.loop("z", sign)[component], names) for sign in (1, -1)) for component in "xz")

    def test_the_deck_on_disk_is_the_one_the_generator_writes(self) -> None:
        self.assertEqual((CUSP / "inputs_rz_spindle_fed").read_text(), make_deck.spindle_deck())

    def test_the_reducer_and_the_deck_agree_on_the_coil_field(self) -> None:
        for r, z in ((0.002, 0.001), (0.006, 0.004), (0.009, 0.0), (0.004, 0.012), (0.015, -0.007), (0.0005, 0.018)):
            radial, axial = analyze_spindle.coil_field(np.array([r]), np.array([z]), self.constants)
            deck_radial, deck_axial = self.deck_field(r, z)
            scale = math.hypot(deck_radial, deck_axial)
            self.assertAlmostEqual(radial[0] / scale, deck_radial / scale, places=5)
            self.assertAlmostEqual(axial[0] / scale, deck_axial / scale, places=5)

    def test_the_field_on_the_axis_is_the_textbook_one(self) -> None:
        c = self.constants
        z = np.linspace(-0.02, 0.02, 9)
        exact = sum(-sign * 4e-7 * np.pi * c["coil_at"] * c["rc"] ** 2 / (2 * (c["rc"] ** 2 + (z - sign * c["dc"]) ** 2) ** 1.5)
                    for sign in (1, -1))
        radial, axial = analyze_spindle.coil_field(np.zeros_like(z), z, c)
        np.testing.assert_allclose(axial, exact, rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(radial, 0, atol=1e-12)

    def test_half_width_is_where_the_density_halves(self) -> None:
        position = np.linspace(0.05, 9.95, 100)
        self.assertAlmostEqual(analyze_spindle.half_width(position, np.exp(-position / 2)), 0.05 + 2 * math.log(2), delta=0.01)


if __name__ == "__main__":
    unittest.main()
