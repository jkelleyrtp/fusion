"""The jet deck (plasma fired in from guns outside the cage) and the part of the reducer that measures it."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

CUSP = Path(__file__).resolve().parents[1] / "warpx/cusp"
sys.path.insert(0, str(CUSP))
import analyze_beta
import make_deck

CONSTANTS = {"a": 0.01, "coil_at": 32000.0, "zg": 0.019, "vj": 0.0, "rf": 0.003, "feed": 1e22, "toff": 6e-9}


class JetsTest(unittest.TestCase):
    def test_the_decks_on_disk_are_the_ones_the_generator_writes(self) -> None:
        self.assertEqual((CUSP / "inputs_3d_cusp_jets").read_text(), make_deck.beta_deck(jets=True))
        self.assertEqual((CUSP / "inputs_3d_cusp_fed").read_text(), make_deck.beta_deck(fed=True))

    def test_the_jet_deck_starts_empty_with_both_guns_outside_the_coils_firing_inward(self) -> None:
        deck = make_deck.beta_deck(jets=True)
        self.assertNotIn("NUniformPerCell", deck)
        for species in ("electrons", "ions"):
            self.assertIn(f"{species}.injection_sources = up down", deck)
            # The gun below the cage fires up and the one above fires down, each with its drift toward the centre.
            self.assertIn(f"{species}.up.surface_flux_pos = (+1)*(-zg)\n{species}.up.flux_normal_axis = z\n"
                          f"{species}.up.flux_direction = +1", deck)
            self.assertIn(f"{species}.down.surface_flux_pos = (-1)*(-zg)\n{species}.down.flux_normal_axis = z\n"
                          f"{species}.down.flux_direction = -1", deck)
            # WarpX draws the speed along the flux direction and then applies the direction's sign, so a drift
            # toward the centre is positive for both guns. A negative one is away from the centre and, once it
            # passes the thermal speed, WarpX's sampler never returns.
            self.assertIn(f"{species}.up.uz_m = vj/clight", deck)
            self.assertIn(f"{species}.down.uz_m = vj/clight", deck)
        self.assertIn("my_constants.zg = 1.9*a", deck)
        self.assertIn("my_constants.dc = 1.3*a", deck)

    def test_every_fed_electron_starts_on_top_of_an_ion(self) -> None:
        """Each source is paired, and the two species give WarpX the same plane, flux and particles per cell."""
        for name in ("inputs_3d_cusp_jets", "inputs_3d_cusp_fed", "inputs_rz_spindle_fed"):
            lines = (CUSP / name).read_text().splitlines()
            for source in ("up", "down"):
                electrons = [line for line in lines if line.startswith(f"electrons.{source}.")]
                ions = [line.replace("ions.", "electrons.", 1) for line in lines if line.startswith(f"ions.{source}.")]
                self.assertIn(f"electrons.{source}.flux_paired = 1", electrons, name)
                self.assertEqual(electrons, ions, name)

    def test_the_reducer_counts_only_what_is_inside_the_coil_planes(self) -> None:
        """Half of what is in the box sits inside, level while the guns fire, then drains to a quarter."""
        radius = (np.arange(96) + 0.5) * 0.024 / 96
        time = np.linspace(0, 1e-8, 101)
        inside = np.where(time <= 6e-9, 4e13, 4e13 * (1 - 0.75 * (time - 6e-9) / 4e-9))
        rows = np.zeros((101, 98))
        rows[:, 0], rows[:, 1] = np.arange(101), time
        rows[:, 2 + 10] = inside
        rows[:, 2 + 80] = 4e13
        header = "#[0]step() [1]time(s) " + " ".join(f"[{k + 2}]bin{k + 1}={r:.6e}()" for k, r in enumerate(radius))
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            (run / "diags/reducedfiles").mkdir(parents=True)
            for name in ("erad", "irad"):
                np.savetxt(run / f"diags/reducedfiles/{name}.txt", rows, header=header[1:], comments="#")
            out = analyze_beta.jets(run, CONSTANTS)
        self.assertEqual(out["gun_mouths_over_a"], [[0.0, 0.0, 1.9], [0.0, 0.0, -1.9]])
        self.assertEqual(out["angle_of_aim_to_coil_field_deg"], 0.0)
        self.assertGreater(out["coil_field_at_opening_over_at_mouth"], 1.0)
        self.assertEqual(out["guns_stop_ns"], 6.0)
        for species in ("electrons", "ions"):
            self.assertAlmostEqual(out[f"{species}_fired_held_ns"], 4.0, places=3)
            self.assertAlmostEqual(out[f"{species}_inside_growth_over_fired"], 0.0, places=3)
            self.assertAlmostEqual(out[f"{species}_inside_at_end_over_at_stop"], 0.25, places=3)
            self.assertAlmostEqual(out[f"{species}_inside_loss_time_just_after_stop_ns"], 4.85, delta=0.06)
            self.assertEqual(out[f"{species}_inside_early_over_late_in_firing"], 1.0)
            # The 4e13 placed at 2.01 a is within 0.15 a of the mouths, out of 6e13 fired.
            self.assertAlmostEqual(out[f"{species}_at_gun_mouths_at_end_over_fired"], 0.6667, places=4)

    def test_a_table_is_refused_unless_each_step_is_there_once_and_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            (run / "diags/reducedfiles").mkdir(parents=True)

            def write(name: str, steps: list[int]) -> None:
                np.savetxt(run / f"diags/reducedfiles/{name}.txt", np.column_stack([steps, steps]), header="step time")

            write("number", [0, 250, 500])
            self.assertEqual(len(analyze_beta.table(run, "number")), 3)
            # A second worker writing to the same directory repeats steps the first has written.
            write("number", [0, 250, 500, 250, 500])
            with self.assertRaises(AssertionError):
                analyze_beta.table(run, "number")
            # A field probe along a line writes a row per point at each step.
            write("axis", [0, 0, 0, 500, 500, 500])
            self.assertEqual(len(analyze_beta.table(run, "axis", rows_per_step=3)), 6)
            write("axis", [0, 0, 0, 500, 500, 500, 500, 500, 500])
            with self.assertRaises(AssertionError):
                analyze_beta.table(run, "axis", rows_per_step=3)


if __name__ == "__main__":
    unittest.main()
