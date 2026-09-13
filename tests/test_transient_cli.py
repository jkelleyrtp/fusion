import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from cusp_sim import E_CHARGE
from electrostatic import ElectrostaticMesh
from run_transient_pic import parser, run, validate


def arguments(path: Path, *extra: str):
    return parser().parse_args([
        "--out", str(path), "--current-a", "1e-10", "--dt", "1e-11",
        "--duration", "2.5e-11", "--inject-per-step", "2", "--nodes", "9",
        "--radius", ".5", "--coil-current", "0", "--energy-ev", "5000",
        "--temperature-ev", "0", "--source-sigma", "0", "--divergence-deg", "0",
        "--aim-deg", "0", "--save-every", "1", *extra,
    ])


class TransientCLITests(unittest.TestCase):
    def test_fractional_injection_and_output_consistency(self):
        with tempfile.TemporaryDirectory() as directory:
            roots = [Path(directory) / "one", Path(directory) / "two"]
            for stride, root in enumerate(roots, start=1):
                with contextlib.redirect_stdout(io.StringIO()):
                    history = run(arguments(root, "--save-every", str(stride)))
                self.assertEqual(history[-1]["injected_count"], 6)
                self.assertEqual(history[-1]["alive_count"], 6)
                self.assertAlmostEqual(
                    history[-1]["injected_charge_C"], -2.5e-21, delta=1e-35,
                )
                self.assertAlmostEqual(history[-1]["charge_balance_C"], 0, delta=1e-35)
                self.assertEqual(history[-1]["time_s"], 2.5e-11)
                self.assertAlmostEqual(history[-1]["dt_s"], 0.5e-11, delta=1e-26)
                for record in history:
                    with np.load(root / record["snapshot"]) as state:
                        mesh = ElectrostaticMesh(
                            torch.from_numpy(state["lower_m"]),
                            torch.from_numpy(state["upper_m"]), (9,) * 3,
                        )
                        charge = mesh.deposit(
                            torch.from_numpy(state["position_m"]),
                            -E_CHARGE * torch.from_numpy(state["electron_count"]),
                        )
                        np.testing.assert_array_equal(charge.numpy(), state["charge_C"])
                        np.testing.assert_array_equal(
                            mesh.potential(charge).numpy(), state["potential_V"],
                        )
                        self.assertEqual(float(state["time_s"]), record["time_s"])
                self.assertTrue((root / "DONE").exists())
                configuration = json.loads((root / "configuration.json").read_text())
                self.assertEqual(configuration["model"], "transient-electrostatic-pic-v1")
            with (
                np.load(roots[0] / history[-1]["snapshot"]) as one,
                np.load(roots[1] / history[-1]["snapshot"]) as two,
            ):
                for name in one.files:
                    np.testing.assert_array_equal(one[name], two[name])
                np.testing.assert_array_equal(one["ids"], np.arange(6))
                np.testing.assert_allclose(
                    one["birth_s"], [0, 0, 1e-11, 1e-11, 2e-11, 2e-11],
                    rtol=0, atol=0,
                )

    def test_scalar_diagnostics_match_snapshot_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "diagnostics"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root, "--diagnostic-every", "2"))
            lines = (root / "diagnostics.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            expected = history[2]
            self.assertEqual(record["step"], 2)
            for key, value in expected.items():
                if key not in ("snapshot", "wall_s"):
                    self.assertEqual(record[key], value, key)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "no-diagnostics"
            with contextlib.redirect_stdout(io.StringIO()):
                run(arguments(root))
            self.assertFalse((root / "diagnostics.jsonl").exists())

    def test_nominal_duration_ulp_does_not_add_pulse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ten-steps"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(
                    root, "--duration", "1e-10", "--max-steps", "10",
                    "--save-every", "10",
                ))
            self.assertEqual(history[-1]["injected_count"], 20)
            self.assertEqual(history[-1]["time_s"], 1e-10)
            self.assertAlmostEqual(
                history[-1]["injected_charge_C"], -1e-20, delta=1e-34,
            )
        self.assertEqual(
            validate(arguments(Path("unused"), "--duration", "1.001e-10")), 11,
        )

    def test_capacity_and_step_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "capacity"
            with (
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(ValueError, "max-live-particles"),
            ):
                run(arguments(root, "--max-live-particles", "3"))
            history = json.loads((root / "history.json").read_text())
            self.assertEqual(history[-1]["injected_count"], 2)
            self.assertFalse((root / "DONE").exists())
            step_root = Path(directory) / "steps"
            with self.assertRaisesRegex(ValueError, "max-steps"):
                run(arguments(step_root, "--max-steps", "2"))
            self.assertFalse(step_root.exists())

    def test_invalid_configuration(self):
        for option, value in [
            ("--dt", "0"), ("--dt", "nan"), ("--duration", "inf"),
            ("--current-a", "-1"), ("--source-sigma", "-1"),
            ("--aim-deg", "100"), ("--divergence-deg", "90"),
            ("--save-every", "0"), ("--max-snapshots", "2"),
            ("--diagnostic-every", "-1"),
        ]:
            with self.subTest(option=option, value=value), self.assertRaises(ValueError):
                validate(arguments(Path("unused"), option, value))

    def test_backwards_sample_rejected(self):
        position = torch.tensor([[0, 0.004, -0.65]] * 2, dtype=torch.float64)
        velocity = position.new_tensor([[0, 0, -1]] * 2)
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("run_transient_pic.thermal_source", return_value=(position, velocity)),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(ValueError, "backwards"),
        ):
            run(arguments(Path(directory) / "backwards"))


if __name__ == "__main__":
    unittest.main()
