import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "job_progress", Path(__file__).resolve().parents[1] / "src" / "job_progress.py"
)
assert SPEC and SPEC.loader
progress = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progress)


class ProgressTests(unittest.TestCase):
    def fixture(self, root: Path, iteration: int = 4) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(json.dumps({
            "source_revision": "abc",
            "purpose": "reference",
            "commands": [["python3", "steady_space_charge.py", "--out", "/remote/10uA",
                          "--iterations", "12", "--energy-ev", "5"]],
        }))
        snapshot = root / "10uA" / "viewer" / f"iteration-{iteration:04d}"
        snapshot.mkdir(parents=True)
        (snapshot / "summary.json").write_text(json.dumps({
            "poisson": {"iteration": iteration},
        }))

    def test_published_snapshot_and_manifest_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            result = progress.read_progress(root)
            self.assertFalse(result["done"])
            self.assertEqual(result["cases"][0]["iteration"], 4)
            self.assertEqual(result["cases"][0]["target"], 12)
            self.assertEqual(result["cases"][0]["status"], "running")
            self.assertEqual(result["cases"][0]["settings"]["energy-ev"], "5")
            self.assertNotIn("out", result["cases"][0]["settings"])

    def test_done_marker_does_not_hide_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            (root / "DONE").write_text("finished")
            (root / "exit_codes.json").write_text("[124]")
            result = progress.read_progress(root)
            self.assertTrue(result["done"])
            self.assertEqual(result["cases"][0]["status"], "timed_out")
            self.assertEqual(result["cases"][0]["iteration"], 4)

    def test_case_completion_before_whole_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, 12)
            (root / "10uA" / "STATUS").write_text("Iterations completed.")
            result = progress.read_progress(root)
            self.assertFalse(result["done"])
            self.assertEqual(result["cases"][0]["status"], "completed")

    def test_new_attempt_never_inherits_previous_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "attempt-20260912-100000"
            self.fixture(first, 12)
            (first / "DONE").write_text("finished")
            (first / "exit_codes.json").write_text("[0]")
            second = root / "attempt-20260912-110000"
            second.mkdir()
            self.assertIsNone(progress.read_progress(root))
            self.fixture(second, 1)
            result = progress.read_progress(root)
            self.assertEqual(result["attempt"], second.name)
            self.assertEqual(result["cases"][0]["iteration"], 1)
            self.assertFalse(result["done"])

    def test_incomplete_summary_publication_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            next_snapshot = root / "10uA" / "viewer" / "iteration-0005"
            next_snapshot.mkdir()
            (next_snapshot / "summary.tmp").write_text("{")
            self.assertEqual(progress.read_progress(root)["cases"][0]["iteration"], 4)

    def test_malformed_exit_codes_are_not_reported_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            (root / "exit_codes.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "Exit codes"):
                progress.read_progress(root)


if __name__ == "__main__":
    unittest.main()
