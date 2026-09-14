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


class PicProgressTests(unittest.TestCase):
    def fixture(
        self,
        root: Path,
        targets: list[int] | str = "[4, 8]",
        codes: list[int] | None = None,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        commands = [
            ["python3", "run_transient_pic.py", "--out", "/remote/pic_vacuum",
             "--duration", "4e-12", "--dt", "1e-12", "--current-a", "0"],
            ["python3", "run_transient_pic.py", "--out", "/remote/pic_1A",
             "--duration", "4e-12", "--dt", "5e-13", "--current-a", "1"],
        ]
        step_targets = targets if isinstance(targets, str) else json.dumps(targets)
        (root / "manifest.json").write_text(
            '{"source_revision":"abc","purpose":"pic","progress_unit":"steps",'
            f'"step_targets":{step_targets},"commands":{json.dumps(commands)}}}'
        )
        if codes is not None:
            (root / "exit_codes.json").write_text(json.dumps(codes))

    def history(self, root: Path, case: str, records: object) -> Path:
        case_dir = root / case
        case_dir.mkdir(parents=True, exist_ok=True)
        path = case_dir / "history.json"
        if isinstance(records, str):
            path.write_text(records)
        else:
            path.write_text(json.dumps(records))
        return path

    def test_step_histories_report_physical_time_and_case_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            self.history(root, "pic_vacuum", [{"step": 2, "time_s": 2e-12}])
            self.history(root, "pic_1A", [{"step": 8, "time_s": 4e-12}])
            (root / "pic_1A" / "DONE").write_text("complete")

            result = progress.read_progress(root)

            self.assertEqual(result["progressUnit"], "steps")
            self.assertEqual(
                [(item["name"], item["iteration"], item["target"], item["status"],
                  item["physicalTimeS"]) for item in result["cases"]],
                [("pic_vacuum", 2, 4, "running", 2e-12),
                 ("pic_1A", 8, 8, "completed", 4e-12)],
            )
            self.assertNotIn("snapshots", result["cases"][0]["settings"])

    def test_step_zero_history_is_running_but_done_requires_full_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            self.history(root, "pic_vacuum", [{"step": 0, "time_s": 0}])
            (root / "pic_vacuum" / "DONE").write_text("complete")

            result = progress.read_progress(root)

            self.assertEqual(result["cases"][0]["status"], "running")
            self.assertEqual(result["cases"][0]["iteration"], 0)
            self.assertEqual(result["cases"][0]["physicalTimeS"], 0)
            self.assertEqual(result["cases"][1]["status"], "pending")

    def test_legacy_manifest_still_reports_iterations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = root / "10uA" / "viewer" / "iteration-0004"
            case.mkdir(parents=True)
            (root / "manifest.json").write_text(json.dumps({
                "source_revision": "abc", "purpose": "legacy",
                "commands": [["python3", "steady_space_charge.py", "--out",
                              "/remote/10uA", "--iterations", "12"]],
            }))
            (case / "summary.json").write_text('{"poisson":{"iteration":4}}')

            result = progress.read_progress(root)

            self.assertEqual(result["progressUnit"], "iterations")
            self.assertNotIn("physicalTimeS", result["cases"][0])

    def test_malformed_step_manifest_and_histories_are_rejected(self) -> None:
        bad_histories = (
            [{"step": -1, "time_s": 0}],
            [{"step": 5, "time_s": 0}],
            [{"step": 1, "time_s": float("nan")}],
            [{"step": 1, "time_s": 5e-12}],
            [],
            [[]],
            "{}",
        )
        for records in bad_histories:
            with self.subTest(records=records), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.fixture(root)
                self.history(root, "pic_vacuum", records)
                with self.assertRaises(ValueError):
                    progress.read_progress(root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, targets="[4]")
            with self.assertRaisesRegex(ValueError, "Step targets"):
                progress.read_progress(root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            (root / "manifest.json").write_text(
                (root / "manifest.json").read_text().replace('"steps"', '"particles"')
            )
            with self.assertRaisesRegex(ValueError, "progress unit"):
                progress.read_progress(root)

    def test_timeout_exit_preserves_partial_step_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, codes=[124, 0])
            self.history(root, "pic_vacuum", [{"step": 2, "time_s": 2e-12}])
            self.history(root, "pic_1A", [{"step": 8, "time_s": 4e-12}])
            (root / "pic_1A" / "DONE").write_text("complete")
            (root / "DONE").write_text("campaign finished")

            result = progress.read_progress(root)

            self.assertEqual(result["cases"][0]["status"], "timed_out")
            self.assertEqual(result["cases"][0]["iteration"], 2)
            self.assertEqual(result["cases"][1]["status"], "completed")

    def test_cycle_histories_report_coupled_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            command = ["python3", "run_ion_pic.py", "--out", "/remote/guns6", "--cycle-duration",
                       "1e-05", "--cycles", "8", "--guns", "6", "--cycles", "16"]
            (root / "manifest.json").write_text(json.dumps({
                "source_revision": "abc", "purpose": "ions", "progress_unit": "cycles",
                "step_targets": [16], "commands": [command],
            }))
            self.history(root, "guns6", [{"cycle": 16, "time_s": 0.00016000000000125254}])
            (root / "guns6" / "DONE").write_text("complete")

            result = progress.read_progress(root)

            self.assertEqual(result["progressUnit"], "cycles")
            case = result["cases"][0]
            self.assertEqual(
                (case["iteration"], case["target"], case["status"], case["physicalTimeS"]),
                (16, 16, "completed", 0.00016000000000125254),
            )
            self.history(root, "guns6", [{"cycle": 17, "time_s": 1.6e-4}])
            with self.assertRaisesRegex(ValueError, "PIC step"):
                progress.read_progress(root)


if __name__ == "__main__":
    unittest.main()
