"""The picket-fence deck (a row of opposed coils that repeats along the axis) and its reducer."""
import math
import re
import sys
import unittest
from pathlib import Path

import numpy as np

CUSP = Path(__file__).resolve().parents[1] / "warpx" / "cusp"
sys.path.insert(0, str(CUSP))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_picket
import make_deck
from test_spindle import elliptic


class PicketTest(unittest.TestCase):
    def deck_field(self, r: float, z: float) -> tuple[float, float]:
        """The coil field (in units of mu0 * current / coil radius) the deck on disk gives WarpX at (r, 0, z)."""
        text = (CUSP / "inputs_rz_picket_fed").read_text()
        names = {"a": 1.0, "rc": 1.0, "h": 0.5, "coil_at": 1.0, "mu0": 1.0, "x": r, "y": 0.0, "z": z, "pi": math.pi,
                 "sqrt": math.sqrt, "comp_ellint_1": lambda k: elliptic(k)[0], "comp_ellint_2": lambda k: elliptic(k)[1]}
        # The last assignment of each component is the one WarpX uses.
        return tuple(eval(re.findall(rf'^particles\.B{component}_external_particle_function\(x,y,z,t\) = "(.*)"$', text,
                                     re.MULTILINE)[-1], names) for component in "xz")

    def test_the_deck_on_disk_is_the_one_the_generator_writes(self) -> None:
        self.assertEqual((CUSP / "inputs_rz_picket_fed").read_text(), make_deck.picket_deck())

    def test_the_field_repeats_from_one_end_of_the_mesh_to_the_other(self) -> None:
        # The mesh runs from -h to h. An endless row has no radial field in the plane of a coil, and the same
        # axial field at both ends.
        scale = math.hypot(*self.deck_field(0.77, 0.0))
        for r in (0.2, 0.77, 1.3):
            low, high = self.deck_field(r, -0.5), self.deck_field(r, 0.5)
            self.assertLess(abs(low[0]) / scale, 3e-4)
            self.assertLess(abs(high[0]) / scale, 3e-4)
            self.assertAlmostEqual(low[1] / scale, high[1] / scale, places=9)
            # One coil along, an endless row has the same field with its sign turned. The deck's row is cut
            # off, which leaves each of the two off by up to 0.05% of the field at the plasma's edge.
            self.assertAlmostEqual(self.deck_field(r, 0.1)[1] / scale, -self.deck_field(r, -0.4)[1] / scale, delta=1e-3)

    def test_the_field_in_the_plane_of_a_coil_is_that_of_many_opposed_loops(self) -> None:
        angle = (np.arange(2000) + 0.5) * math.pi / 1000
        axial = 0.0
        for k in range(-60, 61):
            gap = (0.77**2 + 1 + (0.5 * k) ** 2 - 2 * 0.77 * np.cos(angle)) ** 1.5
            axial += (-1) ** k / (4 * math.pi) * (math.pi / 1000) * ((1 - 0.77 * np.cos(angle)) / gap).sum()
        self.assertAlmostEqual(self.deck_field(0.77, 0.0)[1] / axial, 1.0, places=3)

    def test_the_thermal_speed_stays_below_that_of_light(self) -> None:
        self.assertAlmostEqual(analyze_picket.thermal_speed(2760.0, analyze_picket.M_E) / analyze_picket.C_LIGHT, 0.0733, places=4)
        self.assertAlmostEqual(analyze_picket.thermal_speed(1e5, analyze_picket.M_E) / analyze_picket.C_LIGHT, 0.4046, places=4)

    def test_the_edge_is_where_the_density_halves_and_its_thickness_is_the_fall_from_nine_tenths_to_one_tenth(self) -> None:
        radius = (np.arange(600) + 0.5) * 0.015 / 600
        # Density flat to 7.5 mm, then falling in a straight line to nothing at 8.5 mm; counts go as radius * density.
        density = np.clip((0.0085 - radius) / 0.001, 0.0, 1.0)
        found = analyze_picket.edge(radius, 3e9 * radius * density, {"rc": 0.01})
        self.assertAlmostEqual(found["middle"], 0.008, places=5)
        self.assertAlmostEqual(found["thickness"], 0.0008, places=5)
        self.assertAlmostEqual(found["level"], 3e9, delta=3e3)

    def test_the_current_layer_is_measured_at_half_its_peak_and_a_larger_current_elsewhere_is_ignored(self) -> None:
        radius = (np.arange(384) + 0.5) * 0.015 / 384
        # A layer 0.2 mm wide at half its height, at 7.3 mm, under the far larger current of a coil at 10 mm.
        current = -4e9 * np.exp(-4 * np.log(2) * ((radius - 0.0073) / 0.0002) ** 2) + 5e10 * np.exp(-(((radius - 0.01) / 0.0002) ** 2))
        found = analyze_picket.current_layer(radius, current, 0.00735, 0.001)
        self.assertAlmostEqual(found["peak_at"], 0.0073, delta=2e-5)
        self.assertAlmostEqual(found["width"], 0.0002, delta=1e-5)

    def test_a_density_that_falls_slowly_from_the_centre_does_not_thicken_the_edge(self) -> None:
        radius = (np.arange(600) + 0.5) * 0.015 / 600
        # Density falling from 2.5 at the centre to 1 at 7.9 mm, then in a straight line to nothing at 8.1 mm.
        density = np.where(radius < 0.0079, 1 + 1.5 * (0.0079 - radius) / 0.0079, np.clip((0.0081 - radius) / 0.0002, 0.0, 1.0))
        found = analyze_picket.edge(radius, radius * density, {"rc": 0.01})
        self.assertAlmostEqual(found["middle"], 0.008, delta=2e-5)
        self.assertAlmostEqual(found["thickness"], 0.00016, delta=5e-5)


if __name__ == "__main__":
    unittest.main()
