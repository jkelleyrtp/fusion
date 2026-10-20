"""The run feed behind the site's Runs page: how a case's files on shared storage become a state."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "warpx"))
import runs_feed


class RunsFeed(unittest.TestCase):
    def test_state_follows_the_done_file_then_the_claim(self):
        self.assertEqual(runs_feed.state({"done": "complete"}, False), "complete")
        self.assertEqual(runs_feed.state({"done": "failed after 3 tries"}, False), "failed")
        self.assertEqual(runs_feed.state({"done": None, "claim": "job gpu", "claim_age_s": 20}, False), "running")
        # A claim nobody has touched for ten minutes is a worker that is gone.
        self.assertEqual(runs_feed.state({"done": None, "claim": "job gpu", "claim_age_s": 4000}, False), "unfinished")
        self.assertEqual(runs_feed.state({"done": None, "claim": None}, True), "queued")
        self.assertEqual(runs_feed.state(None, True), "queued")
        self.assertEqual(runs_feed.state(None, False), "not started")

    def test_cases_are_grouped_by_what_they_test(self):
        self.assertEqual(runs_feed.thread("pw_s0.5_h1.0_ppc4_two_mirror", "pw1"), "Size scan: mirror ends")
        self.assertEqual(runs_feed.thread("pw_s0.25_h1.0_long_ppc8_four", "pw1"), "Size scan: longer wrap-around boxes")
        self.assertEqual(runs_feed.thread("pw_s1_h1.0", "pw1"), "Size scan: one-period wrap-around box")
        self.assertEqual(runs_feed.thread("im_theta_x1.0", "pw1"), "Explicit against semi-implicit and implicit")
        self.assertEqual(runs_feed.thread("rv_78k_100kV", "rv1"), "Charged rings at set voltages (3D)")
        self.assertEqual(runs_feed.thread("zw60_f3.7e22", "sp2"), "Two coils with real end walls")
        self.assertEqual(runs_feed.thread("n3e20_64k", "em4"), "Earlier campaign em4")

    def test_what_is_written_is_json_a_browser_reads(self):
        cleaned = runs_feed.finite({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2}})
        self.assertEqual(cleaned, {"a": None, "b": [1.0, None], "c": {"d": 2}})
        json.dumps(cleaned, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
