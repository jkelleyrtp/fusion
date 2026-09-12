import gzip
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

SPEC = importlib.util.spec_from_file_location(
    "export_viewer", Path(__file__).resolve().parents[1] / "src" / "export_viewer.py"
)
assert SPEC and SPEC.loader
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ViewerExportTests(unittest.TestCase):
    def test_completion_uses_marker_contents_not_file_time(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.assertIsNone(exporter.completed_at(directory))
            marker = directory / "DONE"
            marker.write_text("")
            self.assertIsNone(exporter.completed_at(directory))
            marker.write_text("2026-09-12T09:53:57-04:00")
            self.assertEqual(exporter.completed_at(directory), "2026-09-12T13:53:57+00:00")
            marker.write_text("2026-09-12T13:52:56")
            self.assertEqual(exporter.completed_at(directory), "2026-09-12T13:52:56+00:00")
            marker.write_text("not a timestamp")
            with self.assertRaises(ValueError):
                exporter.completed_at(directory)

    def test_restricted_mean_includes_survivors(self):
        result = exporter.residence_statistics(
            np.array([1.0, 3.0, np.nan]), np.array([1, 3, 0]), 5.0
        )
        self.assertEqual(result["meanDwellUs"], 3e6)
        self.assertTrue(result["dwellLowerBound"])
        self.assertEqual(result["lossCounts"], [1, 1, 0, 1])
        self.assertEqual(result["survival"]["counts"][0], 3)
        self.assertEqual(result["survival"]["counts"][-1], 1)
        self.assertTrue(np.all(np.diff(result["survival"]["counts"]) <= 0))

    def test_complete_escape_mean_and_invalid_records(self):
        result = exporter.residence_statistics(
            np.array([1.0, 2.0, 3.0]), np.array([1, 2, 3]), 5.0
        )
        self.assertEqual(result["meanDwellUs"], 2e6)
        self.assertFalse(result["dwellLowerBound"])
        with self.assertRaises(ValueError):
            exporter.residence_statistics(np.array([np.nan]), np.array([3]), 5.0)
        with self.assertRaises(ValueError):
            exporter.residence_statistics(np.array([1]), np.array([4]), 5.0)

    def test_all_survivors(self):
        result = exporter.residence_statistics(np.full(4, np.nan), np.zeros(4, dtype=int), 5.0)
        self.assertEqual(result["meanDwellUs"], 5e6)
        self.assertEqual(set(result["survival"]["counts"]), {4})

    def test_occupancy_counts_and_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "density.npz"
            np.savez(archive, density=np.array([[1, 2], [3, 4]]),
                     density_r=np.array([0.0, 1.0, 2.0]), density_z=np.array([-1.0, 0.0, 1.0]))
            with np.load(archive) as data:
                result = exporter.occupancy_map(data, 1.0)
            self.assertEqual((result["width"], result["height"]), (2, 2))
            self.assertEqual(result["counts"], [1, 2, 3, 4])
            self.assertAlmostEqual(result["coreSampleFraction"], 0.4)

    def test_binary_roundtrip_preserves_ids_last_frame_and_nan_gaps(self):
        trajectory = np.arange(2 * 8 * 6, dtype=np.float32).reshape(2, 8, 6)
        trajectory[1, 3, :3] = np.nan
        payload = exporter.encode_trajectories(trajectory, 16, 3)
        self.assertEqual(struct.unpack("<4sIIIII", payload[:24]), (b"CSP1", 2, 4, 3, 16, 1))
        np.testing.assert_array_equal(np.frombuffer(payload, "<u4", count=4, offset=24), [0, 3, 6, 7])
        np.testing.assert_array_equal(
            np.frombuffer(payload, "<f4", offset=40).reshape(2, 4, 3), trajectory[:, [0, 3, 6, 7], :3]
        )

    def test_content_addressed_chunks_and_member_consistency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member = root / "member"
            member.mkdir()
            summary = {
                "tag": "test", "energy_eV": 5, "ring_radius_m": 0.5, "particles": 2,
                "sim_duration_s": 5.0, "confined_at_end": 1,
            }
            (member / "summary.json").write_text(json.dumps(summary))
            trajectory = np.zeros((2, 8, 6), np.float32)
            trajectory[0, 3:] = np.nan
            np.savez(member / "results.npz", traj=trajectory, traj_dt=0.5,
                     esc_time=np.array([1.0, np.nan]), esc_where=np.array([1, 0]))
            card = exporter.export_member(root, "study", "external", member / "summary.json")
            self.assertEqual(card["meanDwellUs"], 3e6)
            meta = json.loads(gzip.decompress((root / card["meta"]["path"]).read_bytes()))
            self.assertEqual(meta["trajectory"]["escapeUs"], [1e6, None])
            for level in meta["trajectory"]["levels"]:
                for chunk in level["chunks"]:
                    compressed = (root / chunk["path"]).read_bytes()
                    self.assertEqual(len(compressed), chunk["bytes"])
            self.assertEqual(exporter.export_member(root, "study", "external", member / "summary.json"), card)


if __name__ == "__main__":
    unittest.main()
