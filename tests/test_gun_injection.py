"""Tests for the external-gun injection mode in cusp_sim (CPU only, no GPU/kernel)."""

import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cusp_sim

F64 = {"device": torch.device("cpu"), "dtype": torch.float64}


def _args(**over):
    defaults = {
        "out": tempfile.mkdtemp(), "particles": 64, "steps": 10, "sim_time": 1e-8, "traj_dt": None,
        "traj_samples": 16, "tracked": 4, "integrator": "boris", "adaptive": 0, "block_steps": 10,
        "steps_per_gyro_inv": 0.025, "dt_ref_b": None, "ring_radius": 0.05, "ring_half_sep": 0.025,
        "current": 23000.0, "space_charge": [0.0], "space_charge_radius": 0.05, "wall_fraction": 0.98,
        "axial_margin": 0.06, "inject_offset": 0.03, "inject_sigma": 0.0, "inject_mode": "gun",
        "inject_r": [0.0], "pitch_lo_deg": [0.0], "pitch_hi_deg": [1.0], "members": None,
        "grid_r": 64, "grid_z": 128, "segments": 72, "hist_r": 16, "hist_z": 32, "hist_every": 2,
        "seed": 1234, "no_kernel": True, "device": "cpu", "gun_position": None,
        "gun_direction": [0.0, 0.0, 1.0], "energies": [100.0],
    }
    defaults.update(over)
    return argparse.Namespace(**defaults)


def _run(args, member):
    out = Path(args.out)
    import json

    def log(msg):
        pass

    cusp_sim.run_member(args, member, "guntest", "cpu", log)
    return json.loads((out / "guntest" / "summary.json").read_text())


class SamplerTests(unittest.TestCase):
    def test_pencil_beam_exact_aim(self):
        # sigma=0, theta band 0: every particle at origin moving exactly along aim
        pos, vel, d = cusp_sim.sample_gun_beam([1, 2, 3], [0.0, -0.007142857, 1.0], 5.0, 32, 0.0, 0.0, 0.0, F64)
        np.testing.assert_allclose(pos.numpy(), np.tile([1, 2, 3], (32, 1)), atol=1e-15)
        np.testing.assert_allclose(vel.numpy(), np.tile(5.0 * d, (32, 1)), atol=1e-14)
        np.testing.assert_allclose(d, [0.0, -0.007142857, 1.0] / np.linalg.norm([0.0, -0.007142857, 1.0]))

    def test_sigma_in_perpendicular_plane_only(self):
        torch.manual_seed(0)
        origin = np.array([0.0, 6e-4, -0.055])
        d = np.array([0.3, 0.4, 0.5])
        d /= np.linalg.norm(d)
        pos, vel, _ = cusp_sim.sample_gun_beam(origin, d, 7.0, 20000, 1e-3, 0.0, 10.0, F64)
        offset = (pos.numpy() - origin)
        np.testing.assert_allclose(offset @ d, 0.0, atol=1e-12)  # zero divergence along aim
        vdir = vel.numpy() / np.linalg.norm(vel.numpy(), axis=1, keepdims=True)
        ang = np.degrees(np.arccos(np.clip(vdir @ d, -1, 1)))
        self.assertTrue((ang >= 0).all() and (ang <= 10.0 + 1e-9).all())
        self.assertGreater(ang.max(), 5.0)  # band actually populated

    def test_speed_exact_float64(self):
        for speed in (1e5, 5.93e6):
            _, vel, _ = cusp_sim.sample_gun_beam([0, 0, 1], [0, 0, 1], speed, 100, 0.0, 0.0, 30.0, F64)
            np.testing.assert_allclose(vel.norm(dim=1).numpy(), speed, rtol=1e-14)
            self.assertEqual(vel.dtype, torch.float64)

    def test_axis_aligned_directions(self):
        for d in ([1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]):
            _, vel, dn = cusp_sim.sample_gun_beam([0, 0, -0.06], d, 1e6, 500, 0.0, 0.0, 0.0, F64)
            np.testing.assert_allclose(vel.numpy()[0], 1e6 * np.asarray(d) / np.linalg.norm(d), atol=1e-8)
            np.testing.assert_allclose(dn, np.asarray(d) / np.linalg.norm(d))

    def test_invalid_inputs_rejected(self):
        for bad_dir in ([0, 0, 0], [float("nan"), 0, 1], [float("inf"), 0, 0]):
            with self.assertRaises(ValueError):
                cusp_sim.sample_gun_beam([0, 0, -0.06], bad_dir, 1e6, 8, 0.0, 0.0, 0.0, F64)
        with self.assertRaises(ValueError):
            cusp_sim.sample_gun_beam([0, 0, -0.06], [0, 0, 1], 1e6, 8, -1e-3, 0.0, 0.0, F64)
        with self.assertRaises(ValueError):
            cusp_sim.sample_gun_beam([0, 0, -0.06], [0, 0, 1], 1e6, 8, 0.0, 10.0, 5.0, F64)
        with self.assertRaises(ValueError):
            cusp_sim.sample_gun_beam([0, 0, -0.06], [0, 0, 1], 1e6, 8, 0.0, 0.0, 181.0, F64)


class GunMemberTests(unittest.TestCase):
    def test_smoke_and_summary_fields(self):
        a = _args()
        s = _run(a, (100.0, 6e-4, 0.0, 1.0, 0.0))
        self.assertEqual(s["inject_mode"], "gun")
        self.assertEqual(s["pitch_reference"], "gun_direction")
        np.testing.assert_allclose(s["gun_position_m"], [0.0, 6e-4, -0.055])
        np.testing.assert_allclose(s["gun_direction_unit"], [0.0, 0.0, 1.0])
        self.assertIsInstance(s["gun_B_T"], float)
        self.assertIsNotNone(s["gun_axis_B_angle_deg"])
        self.assertEqual(s["launch_angle_undefined_count"], 0)
        for k in ("p05", "p50", "p95"):
            self.assertIsNotNone(s[f"launch_angle_to_local_B_deg_{k}"])
        self.assertIn("kernel_setup_time_s", s)

    def test_origin_inside_trap_rejected(self):
        a = _args(gun_position=[0.0, 0.0, 0.01])  # |z| <= d=0.025
        with self.assertRaises(ValueError):
            _run(a, (100.0, 0.0, 0.0, 1.0, 0.0))

    def test_origin_outside_domain_rejected(self):
        a = _args(gun_position=[0.0, 0.0, -0.5])  # beyond axial margin
        with self.assertRaises(ValueError):
            _run(a, (100.0, 0.0, 0.0, 1.0, 0.0))
        a2 = _args(gun_position=[0.049, 0.0, -0.05])  # r >= r_max = 0.049
        with self.assertRaises(ValueError):
            _run(a2, (100.0, 0.0, 0.0, 1.0, 0.0))

    def test_explicit_position_requires_zero_inject_r(self):
        a = _args(gun_position=[0.0, 1e-3, -0.05])
        with self.assertRaises(ValueError):
            _run(a, (100.0, 1e-3, 0.0, 1.0, 0.0))  # inject_r nonzero -> silent-ignore guard
        s = _run(a, (100.0, 0.0, 0.0, 1.0, 0.0))
        np.testing.assert_allclose(s["gun_position_m"], [0.0, 1e-3, -0.05])

    def test_bad_energy_rejected(self):
        for e in (0.0, -5.0, float("nan")):
            with self.assertRaises(ValueError):
                _run(_args(), (e, 6e-4, 0.0, 1.0, 0.0))

    def test_beam_width_overflow_rejected(self):
        a = _args(inject_sigma=0.5)  # sigma huge -> sampled positions escape domain
        with self.assertRaises(ValueError) as ctx:
            _run(a, (100.0, 6e-4, 0.0, 1.0, 0.0))
        self.assertIn("axial-margin", str(ctx.exception))

    def test_worker_tag_distinct_for_gun(self):
        # _worker appends a deterministic geometry hash for gun mode only
        seen = []
        with tempfile.TemporaryDirectory() as td:
            for args in (_args(), _args(gun_direction=[0.0, -0.007142857, 1.0]),
                         _args(inject_mode="cusp")):
                with mock.patch.object(cusp_sim, "run_member",
                                       side_effect=lambda a, m, tag, dev, log: seen.append(tag)):
                    cusp_sim._worker(0, args, [(100.0, 6e-4, 0.0, 1.0, 0.0)], ["cpu"],
                                     os.path.join(td, "sim.log"))
        self.assertNotEqual(seen[0], seen[1])
        self.assertTrue(seen[0].startswith("E100eV") and "_gun" in seen[0])
        self.assertNotIn("_gun", seen[2])  # legacy modes keep their tags


if __name__ == "__main__":
    unittest.main()
