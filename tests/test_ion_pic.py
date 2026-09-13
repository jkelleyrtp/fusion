import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from ion_pic import ionization_cross_section, parser, run, validate_coupled


def arguments(path: Path, *extra: str):
    return parser().parse_args([
        "--out", str(path), "--current-a", "1e-3", "--dt", "1e-11", "--inject-per-step", "4",
        "--nodes", "9", "--coil-current", "3000", "--max-live-particles", "20000",
        "--electron-startup", "2e-10", "--electron-window", "2e-10", "--electron-samples", "4",
        "--gas-pa", "1", "--ion-dt", "1e-9", "--cycle-duration", "1e-7", "--cycles", "2",
        "--ions-per-cycle", "64", "--ion-batches", "8", "--save-every-cycles", "1", "--secondary-every", "4", *extra,
    ])


class IonPICTests(unittest.TestCase):
    def test_lotz_cross_section(self):
        sigma = ionization_cross_section(torch.tensor([10.0, 15.43, 100.0, 1000.0], dtype=torch.float64))
        self.assertEqual(sigma[:2].tolist(), [0.0, 0.0])
        self.assertAlmostEqual(float(sigma[2]), 1.09e-20, delta=0.01e-20)
        self.assertAlmostEqual(float(sigma[3]), 2.43e-21, delta=0.01e-21)

    def test_coupled_cycles_account_for_charge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root))
            self.assertEqual((root / "DONE").read_text(), "complete\n")
            self.assertEqual(len(history), 2)
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertEqual(configuration["model"], "coupled-electron-ion-pic-v1")
            final = history[-1]
            self.assertEqual(final["ion_created_count"], 128)
            self.assertAlmostEqual(final["time_s"], 2e-7, delta=1e-15)
            self.assertAlmostEqual(final["electron_time_s"], 6e-10, delta=1e-18)
            created = final["ion_created_charge_C"]
            self.assertGreater(created, 0)
            self.assertLess(abs(final["ion_charge_balance_C"]), 1e-9 * created)
            self.assertLess(abs(final["ion_deposition_error_C"]), 1e-9 * created)
            self.assertGreater(final["neutralization_fraction"], 0)
            self.assertLess(final["secondary_injected_charge_C"], 0)
            self.assertEqual(sum(final["ion_exit_counts"]), final["ion_created_count"] - final["ion_count"])
            with np.load(root / final["snapshot"]) as state:
                self.assertEqual(len(state["ion_count"]), final["ion_count"])
                np.testing.assert_allclose(state["ion_charge_C"].sum(), final["ion_alive_charge_C"], rtol=1e-9)
                self.assertEqual(state["electron_position_m"].shape, state["electron_velocity_m_s"].shape)
                self.assertEqual(len(state["electron_count"]), final["electrons"]["alive_count"])

    def test_charge_exchange_thermalizes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root, "--cx-cross-section", "1e-12", "--no-secondaries", "--cycles", "1"))
            final = history[-1]
            self.assertGreaterEqual(final["ion_exchange_events"], final["ion_count"])
            self.assertLess(final["ion_mean_kinetic_eV"], 1)
            self.assertEqual(final["secondary_injected_charge_C"], 0)

    def test_population_limit_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root, "--max-live-particles", "60"))
            self.assertEqual(history, [])
            self.assertIn("max-live-particles", (root / "DONE").read_text())

    def test_invalid_plans(self):
        root = Path("unused")
        with self.assertRaisesRegex(ValueError, "Invalid cycle"):
            validate_coupled(arguments(root, "--ion-batches", "7"))
        with self.assertRaisesRegex(ValueError, "integer multiple"):
            validate_coupled(arguments(root, "--cycle-duration", "1.5e-9"))
        with self.assertRaisesRegex(ValueError, "positive"):
            validate_coupled(arguments(root, "--gas-pa", "0"))


if __name__ == "__main__":
    unittest.main()
