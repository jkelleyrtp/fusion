import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from cusp_sim import E_CHARGE, ring_field_on_grid
from electrostatic import ElectrostaticMesh
from run_transient_pic import COIL_FRAMES, coils, parser, run, six_coil_field, validate


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

    def test_delayed_track_paths_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tracks"
            with contextlib.redirect_stdout(io.StringIO()):
                run(arguments(
                    root, "--track", "3", "--track-after", "1e-11", "--track-every", "1",
                    "--track-samples", "2",
                ))
            with np.load(root / "tracks.npz") as tracks, np.load(root / "snapshots/step-00000003.npz") as state:
                self.assertEqual(int(tracks["first_id"]), 2)
                self.assertEqual(int(state["tracked_first_id"]), 2)
                self.assertTrue(bool(tracks["full"]))
                self.assertEqual(tracks["position_m"].shape, (2, 3, 3))
                self.assertEqual(tracks["position_m"].dtype, np.float32)
                np.testing.assert_allclose(tracks["time_s"], [2e-11, 2.5e-11], rtol=0, atol=1e-26)
                np.testing.assert_array_equal(tracks["birth_s"], state["tracked_birth_s"])
                np.testing.assert_allclose(tracks["birth_s"], [1e-11, 1e-11, 2e-11], rtol=0, atol=0)
                self.assertTrue(np.isnan(tracks["position_m"][0, 2]).all())
                np.testing.assert_allclose(
                    tracks["position_m"][1], state["tracked_position_m"], rtol=1e-7, atol=0,
                )
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertIn("tracks.npz samples every 1 steps", configuration["tracking"])

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
            ("--diagnostic-every", "-1"), ("--box-half-width", "0.25"),
            ("--box-bottom", "1.2"), ("--box-top", "0.2"), ("--box-half-width", "0.5"),
            ("--gun-radius", "0.1"), ("--gun-radius", "-1"),
            ("--casing-radius", "-0.1"), ("--casing-radius", "0.5"), ("--casing-radius", "0.2"),
            ("--casing-voltage", "nan"),
        ]:
            with self.subTest(option=option, value=value), self.assertRaises(ValueError):
                validate(arguments(Path("unused"), option, value))
        six = ("--coils", "6", "--coil-offset", "1", "--box-half-width", "1.2", "--box-bottom", "1.95")
        for extra in (
            ("--box-half-width", "0.75"), ("--box-half-width", "1.2", "--casing-radius", "0.2"),
            ("--coil-offset", "1"), six, (*six, "--casing-radius", "0.15", "--box-top", "1.1"),
            (*six, "--casing-radius", "0.15", "--box-top", "1.3", "--coil-offset", "0.8"),
            (*six, "--casing-radius", "0.1", "--box-top", "1.3", "--coil-offset", "1.0"),
            (*six, "--casing-radius", "0.15", "--box-half-width", "1.425", "--box-top", "1.4625",
             "--coil-offset", "1.2"),
        ):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate(arguments(Path("unused"), *extra))

    def test_box_extensions_keep_reference_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "box"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(
                    root, "--box-half-width", "0.45", "--box-bottom", "1.625", "--box-top", "1.95",
                ))
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertEqual(configuration["mesh_shape"], [7, 7, 12])
            np.testing.assert_allclose(configuration["box_lower_m"], [-0.225, -0.225, -0.8125])
            np.testing.assert_allclose(configuration["box_upper_m"], [0.225, 0.225, 0.975])
            z_rows, r_columns = configuration["magnetic_table_shape_z_r"]
            self.assertEqual((z_rows, r_columns), (512 + 64 + 128, 193))
            with np.load(root / history[-1]["snapshot"]) as state:
                self.assertEqual(state["potential_V"].shape, (7, 7, 12))
                np.testing.assert_allclose(
                    (state["upper_m"] - state["lower_m"]) / (np.array([7, 7, 12]) - 1),
                    [0.075, 0.075, 1.3 / 8],
                )

    def test_gun_barrel_is_grounded_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gun"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(
                    root, "--nodes", "17", "--box-bottom", "1.625", "--gun-radius", "0.3",
                    "--current-a", "1e-3",
                ))
            configuration = json.loads((root / "configuration.json").read_text())
            barrel = configuration["gun_barrel"]
            self.assertGreater(barrel["nodes"], 0)
            np.testing.assert_allclose(barrel["front_m"], [0, 0.004, -0.65])
            self.assertIn("grounded absorbing gun barrel", configuration["boundary"])
            final = history[-1]
            self.assertEqual(final["conductor_exit_counts"], [0])
            self.assertGreater(final["conductor_charge_C"][0], 0)
            self.assertAlmostEqual(final["source_potential_V"], 0, delta=1e-9)
            with np.load(root / final["snapshot"]) as state:
                lower, upper, potential = state["lower_m"], state["upper_m"], state["potential_V"]
            axes = [np.linspace(lower[i], upper[i], potential.shape[i]) for i in range(3)]
            x, y, z = np.meshgrid(*axes, indexing="ij")
            relative = np.stack((x, y - 0.004, z + 0.65), axis=-1)
            inside = (-relative[..., 2] >= 0) & (np.hypot(relative[..., 0], relative[..., 1]) <= 0.15)
            self.assertLess(np.abs(potential[inside]).max(), 1e-9)
            self.assertLess(potential.min(), -1e-9)

    def test_coil_casings_hold_voltage_and_absorb(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "casings"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(
                    root, "--nodes", "17", "--box-half-width", "1.35", "--casing-radius", "0.3",
                    "--casing-voltage", "-500", "--coil-current", "30000", "--dt", "4e-12",
                    "--duration", "2e-11", "--save-every", "5", "--current-a", "1e-3",
                ))
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertEqual(configuration["conductor_names"], ["casing_lower", "casing_upper"])
            self.assertEqual(configuration["mesh_shape"], [37, 37, 17])
            casings = configuration["coil_casings"]
            self.assertEqual([casing["center_z_m"] for casing in casings], [-0.25, 0.25])
            self.assertTrue(all(casing["nodes"] > 0 and casing["voltage_V"] == -500 for casing in casings))
            self.assertIn("toroidal coil casings", configuration["boundary"])
            self.assertLess(configuration["magnetic_table_max_T"], 1)
            final = history[-1]
            self.assertEqual(final["conductor_exit_counts"], [0, 0])
            self.assertTrue(all(charge < 0 for charge in final["conductor_charge_C"]))
            with np.load(root / final["snapshot"]) as state:
                lower, upper, potential = state["lower_m"], state["upper_m"], state["potential_V"]
            axes = [np.linspace(lower[i], upper[i], potential.shape[i]) for i in range(3)]
            x, y, z = np.meshgrid(*axes, indexing="ij")
            tube = (np.hypot(x, y) - 0.5) ** 2 + np.minimum((z + 0.25) ** 2, (z - 0.25) ** 2) <= 0.15 ** 2
            np.testing.assert_allclose(potential[tube], -500, atol=1e-8)

    def test_six_coil_field_matches_closed_form_loops(self):
        args = parser().parse_args([
            "--out", "unused", "--coils", "6", "--coil-offset", "1.2", "--casing-radius", "0.1",
            "--box-half-width", "1.425", "--box-bottom", "1.95", "--box-top", "1.4625",
            "--coil-current", "30000", "--nodes", "17",
        ])
        validate(args)
        lower = torch.tensor([-0.7125, -0.7125, -0.975], dtype=torch.float64)
        upper = torch.tensor([0.7125, 0.7125, 0.73125], dtype=torch.float64)
        _, field, bmax, _ = six_coil_field(args, torch.device("cpu"), lower, upper)
        self.assertGreater(bmax, 0)
        generator = torch.Generator().manual_seed(3)
        points = (2 * torch.rand(24, 3, generator=generator, dtype=torch.float64) - 1) * 0.4
        points[0] = 0
        magnetic = field(points)
        self.assertLess(magnetic[0].abs().max(), 1e-15)
        exact = torch.zeros_like(points)
        for axis, center, turns in coils(args):
            frame = list(COIL_FRAMES[axis])
            local = points[:, frame] - points.new_tensor([0, 0, center])
            for row in range(1, len(points)):
                radius = torch.hypot(local[row, 0], local[row, 1])
                br, bz = ring_field_on_grid(radius[None], local[row, 2][None], 0.5, [0.0], [turns], 0, "cpu")
                exact[row, frame] += torch.stack((br[0, 0] * local[row, 0] / radius,
                                                  br[0, 0] * local[row, 1] / radius, bz[0, 0]))
        error = (magnetic - exact)[1:].norm(dim=1)
        self.assertLess(float(error.max()), 2e-3 * float(exact[1:].norm(dim=1).max()))
        quarter = points.new_tensor([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        np.testing.assert_allclose(field(points @ quarter.T), magnetic @ quarter.T, atol=1e-14)
        np.testing.assert_allclose(field(-points), -magnetic, atol=1e-14)

    def test_six_coil_casings_are_held_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "six"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(
                    root, "--nodes", "17", "--coils", "6", "--coil-offset", "1.2", "--casing-radius", "0.1",
                    "--box-half-width", "1.425", "--box-bottom", "1.95", "--box-top", "1.4625",
                    "--gun-radius", "0.06",
                    "--casing-voltage", "-500", "--coil-current", "30000", "--dt", "2e-12",
                    "--duration", "4e-12", "--current-a", "1e-3",
                ))
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertEqual(configuration["conductor_names"], [
                "gun_barrel", "casing_x-", "casing_x+", "casing_y-", "casing_y+", "casing_z-", "casing_z+",
            ])
            self.assertEqual([coil["ampere_turns"] for coil in configuration["coils"]], [30000, -30000] * 3)
            casings = configuration["coil_casings"]
            self.assertEqual([casing["axis"] for casing in casings], list("xxyyzz"))
            self.assertTrue(all(casing["nodes"] > 0 for casing in casings))
            self.assertIn("six-coil", configuration["magnetic_geometry"])
            final = history[-1]
            self.assertEqual(len(final["conductor_exit_counts"]), 7)
            with np.load(root / final["snapshot"]) as state:
                lower, upper, potential = state["lower_m"], state["upper_m"], state["potential_V"]
            axes = [np.linspace(lower[i], upper[i], potential.shape[i]) for i in range(3)]
            grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1)
            tube = np.zeros(potential.shape, dtype=bool)
            for axis in range(3):
                first, second = (other for other in range(3) if other != axis)
                radial = np.hypot(grid[..., first], grid[..., second]) - 0.5
                tube |= radial ** 2 + np.minimum((grid[..., axis] + 0.6) ** 2, (grid[..., axis] - 0.6) ** 2) <= 0.05 ** 2
            self.assertTrue(tube.any())
            np.testing.assert_allclose(potential[tube], -500, atol=1e-8)

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
