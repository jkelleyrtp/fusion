"""The spindle-cusp deck and its reducer: the two must agree on the coil field."""
import math
import re
import sys
import tempfile
import typing
import unittest
from pathlib import Path

import h5py
import numpy as np

CUSP = Path(__file__).resolve().parents[1] / "warpx/cusp"
sys.path.insert(0, str(CUSP))
import analyze_spindle
import make_deck
import unit_map


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
        self.assertEqual((CUSP / "inputs_rz_spindle_leak").read_text(), make_deck.leak_deck())
        self.assertEqual((CUSP / "inputs_rz_spindle_casing").read_text(), make_deck.casing_deck())

    def test_the_leak_deck_is_the_two_coil_deck_with_lines_added(self) -> None:
        plain, leak = make_deck.spindle_deck().splitlines(), make_deck.leak_deck().splitlines()
        changed = [line for line in plain if line not in leak]
        self.assertEqual([line.split(" = ")[0] for line in changed], ["warpx.reduced_diags_names"])

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

    def test_the_electron_orbit_allows_for_speeds_near_that_of_light(self) -> None:
        # Momentum from energy: pc = sqrt(T^2 + 2 T m c^2), with m c^2 = 510998.95 eV.
        for energy in (1.0e4, 1.0e5):
            expected = math.sqrt(energy**2 + 2 * energy * 510998.95) / 299792458.0
            self.assertAlmostEqual(analyze_spindle.orbit_times_field(energy) / expected, 1.0, places=5)
        slow = math.sqrt(2 * 1.0e5 * 510998.95) / 299792458.0
        self.assertGreater(analyze_spindle.orbit_times_field(1.0e5) / slow, 1.04)

    def test_pressure_is_two_thirds_of_the_energy_for_slow_particles_and_less_for_fast_ones(self) -> None:
        rest = 510998.95 * 1.602176634e-19
        self.assertAlmostEqual(analyze_spindle.pressure_per_particle(1e-6 * rest, analyze_spindle.M_E) / (1e-6 * rest), 2 / 3, places=5)
        # One particle of 100 keV: momentum times speed is T (T + 2 m c^2) / (T + m c^2).
        energy = 1.0e5 * 1.602176634e-19
        self.assertAlmostEqual(analyze_spindle.pressure_per_particle(energy, analyze_spindle.M_E) / energy, 0.6121, places=3)
        self.assertAlmostEqual(analyze_spindle.pressure_per_particle(1e3 * rest, analyze_spindle.M_E) / (1e3 * rest), 1 / 3, places=3)

    def test_half_width_is_where_the_density_halves(self) -> None:
        position = np.linspace(0.05, 9.95, 100)
        self.assertAlmostEqual(analyze_spindle.half_width(position, np.exp(-position / 2)), 0.05 + 2 * math.log(2), delta=0.01)

    def test_a_spike_a_cell_wide_on_the_axis_does_not_set_the_width_of_the_stream_through_a_coil(self) -> None:
        radius = np.linspace(0.0125e-3, 9.9875e-3, 400)
        density = np.where(radius < 4e-3, 1 - radius / 8e-3, 0.0)  # falls to half its peak at 4 mm, then stops
        density[radius < 0.08e-3] *= 4
        stream = analyze_spindle.stream_through_coil(radius, density * radius, 0.08e-3)
        self.assertAlmostEqual(stream["stream_half_radius_in_coil_mm"], 3.9, delta=0.2)
        self.assertAlmostEqual(stream["density_on_axis_over_nearby_in_coil"], 4.0, delta=0.2)
        self.assertGreater(stream["stream_radius_holding_half_in_coil_mm"], 2.0)
        self.assertLess(stream["stream_radius_holding_half_in_coil_mm"], 3.0)


class CasingVoltageTest(unittest.TestCase):
    """The field of the metal at 1 V that unit_map.py gives runs of inputs_rz_spindle_casing."""

    def at(self, cells: int) -> tuple[unit_map.Constants, np.ndarray, np.ndarray]:
        text = (CUSP / "inputs_rz_spindle_casing").read_text()
        c = unit_map.Constants(text, [f"my_constants.nr={cells}", "my_constants.dc=0.006"])
        held = unit_map.metal_nodes(text, c)
        held[np.arange(cells + 1) * c["rw"] / cells > c["rw"] - c["gap"]] = False
        return c, held, unit_map.potential(held, c["rw"] / cells)

    def test_the_metal_is_every_corner_of_every_cell_its_surface_cuts(self) -> None:
        c, held, _ = self.at(64)
        cell = c["rw"] / 64
        # In cells, a block's faces are at r = 27.5 and at z = 14.5 and 23.5 from the middle: they cut the cells
        # from 27 to 28 in r and from 14 to 15 and 23 to 24 in z, and the corners of those are the outermost metal.
        self.assertAlmostEqual(c["rb_face"], 27.5 * cell)
        self.assertAlmostEqual(c["lo_face"], 14.5 * cell)
        self.assertAlmostEqual(c["hi_face"], 23.5 * cell)
        middle = 64
        self.assertTrue(held[27:30, middle + 14 : middle + 25].all())
        self.assertFalse(held[26, :].any())
        self.assertFalse(held[:, middle + 13].any() or held[:, middle + 25].any())
        np.testing.assert_array_equal(held, held[:, ::-1])

    def test_snapshots_hold_what_the_check_of_gauss_law_reads(self) -> None:
        text = (CUSP / "inputs_rz_spindle_casing").read_text()
        plotted = re.findall(r"^diag1\.fields_to_plot = (.+)$", text, re.MULTILINE)[-1].split()
        self.assertIn("rho", plotted)
        self.assertIn("divE", plotted)

    def test_the_potential_is_one_on_the_metal_zero_on_the_can_and_settles_as_the_mesh_is_refined(self) -> None:
        (_, held, coarse), (_, _, fine) = self.at(64), self.at(128)
        self.assertTrue((coarse[held] == 1).all())
        self.assertTrue((coarse[-1] == 0).all() and (coarse[:, 0] == 0).all() and (coarse[:, -1] == 0).all())
        self.assertTrue((coarse >= 0).all() and (coarse <= 1).all())
        self.assertAlmostEqual(coarse[0, 64], fine[0, 128], delta=0.01)
        self.assertAlmostEqual(fine[0, 128], 0.9085, delta=0.001)

    def test_the_file_holds_the_potential_differences_at_the_middle_of_each_mesh_edge(self) -> None:
        c, _, phi = self.at(32)
        cell = c["rw"] / 32
        with tempfile.TemporaryDirectory() as folder:
            unit_map.write(f"{folder}/unit.h5", phi, cell, c["zw"])
            with h5py.File(f"{folder}/unit.h5", "r") as file:
                field = file["data/0/fields/E"]
                radial, axial = field["r"][0], field["z"][0]
                self.assertEqual(field.attrs["gridSpacing"].tolist(), [cell / 2, cell / 2])
        np.testing.assert_allclose(radial[1::2, ::2], -(phi[1:] - phi[:-1]) / cell)
        np.testing.assert_allclose(axial[::2, 1::2], -(phi[:, 1:] - phi[:, :-1]) / cell)


if __name__ == "__main__":
    unittest.main()
