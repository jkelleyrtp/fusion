import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from analyze_tracks import cusp_class, load


class AnalyzeTracksTests(unittest.TestCase):
    def test_exited_paths_are_masked_and_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "track_0V"
            case.mkdir()
            (case / "configuration.json").write_text(json.dumps({
                "core_radius_m": 0.1, "conductor_names": ["gun_barrel", "casing_x-"],
                "casing_voltage": 5000.0, "current_a": 1.0, "energy_ev": 5000.0,
                "coil_current": 30000.0, "seed": 1234, "duration": 4e-12,
            }))
            position = np.full((5, 2, 3), math.nan, dtype=np.float32)
            position[:, 0, 0] = [0.5, 0.05, 0.5, 0.05, 0.9]
            position[1:, 1, 0] = [0.5, 0.05, 0.5, 0.5]
            position[:, :, 1:] = np.where(np.isnan(position[:, :, :1]), math.nan, 0.0)
            np.savez_compressed(
                case / "tracks.npz", time_s=np.arange(5) * 1e-12, position_m=position,
                birth_s=np.array([0.0, 1e-12]), exit_time_s=np.array([3.5e-12, math.nan]),
                exit_face=np.array([7, -1]), first_id=10, full=True,
            )
            tracks = load(case)
        self.assertTrue(np.isnan(tracks.position[4, 0]).all())
        np.testing.assert_array_equal(tracks.entries, [2, 1])
        np.testing.assert_allclose(tracks.lifetime, [3.5e-12, 3e-12], rtol=0, atol=1e-27)
        self.assertEqual(tracks.exits, {"casing_x-": 1})
        self.assertEqual(tracks.cusps, {"casing_x-": 1})
        self.assertEqual(tracks.summary()["exited"], 1)

    def test_wall_exits_are_classified_by_cusp_direction(self):
        self.assertEqual(cusp_class(np.array([0.1, -0.7, 0.05])), "point cusp (face axis)")
        self.assertEqual(cusp_class(np.array([0.6, 0.6, 0.1])), "line cusp (edge)")
        self.assertEqual(cusp_class(np.array([-0.5, 0.6, 0.55])), "corner cusp")


if __name__ == "__main__":
    unittest.main()
