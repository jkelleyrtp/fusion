import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "run_space_charge_pilot", Path(__file__).resolve().parents[1] / "src" / "run_space_charge_pilot.py"
)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class FilamentRunnerTests(unittest.TestCase):
    def test_filament_profile_commands_and_manifest(self):
        revision = "a" * 40
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with patch.dict(os.environ, {"CUSP_SOURCE_REVISION": revision}), patch(
                "sys.argv",
                [
                    "run_space_charge_pilot.py",
                    "--out",
                    str(output),
                    "--profile",
                    "filament",
                    "--track",
                    "64",
                    "--trajectory-frames",
                    "1025",
                ],
            ), patch.object(runner.subprocess, "run", return_value=type("Result", (), {"returncode": 0})()) as run:
                runner.main()

            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["source_revision"], revision)
            self.assertIn("broad 3 cm / 0 degree", manifest["purpose"])
            expected = [
                ("broad_vacuum", "0.03", "0"),
                ("broad_1A", "0.03", "0"),
                ("compact_vacuum", "5e-05", "10"),
                ("compact_1A", "5e-05", "10"),
            ]
            self.assertEqual(run.call_count, 4)
            for command, (name, sigma, divergence), device in zip(
                manifest["commands"], expected, range(4), strict=True
            ):
                self.assertEqual(Path(command[command.index("--out") + 1]).name, name)
                self.assertEqual(command[command.index("--device") + 1], f"cuda:{device}")
                self.assertEqual(command[command.index("--energy-ev") + 1], "5000")
                self.assertEqual(command[command.index("--temperature-ev") + 1], "0.2")
                self.assertEqual(command[command.index("--source-sigma") + 1], sigma)
                self.assertEqual(command[command.index("--divergence-deg") + 1], divergence)
                self.assertEqual(command[command.index("--current-a") + 1], "0" if "vacuum" in name else "1")
                self.assertEqual(command[command.index("--coil-current") + 1], "30000")
                self.assertEqual(command[command.index("--nodes") + 1], "33")
                self.assertEqual(command[command.index("--particles") + 1], "1024")
                self.assertEqual(command[command.index("--iterations") + 1], "8")
                self.assertEqual(command[command.index("--relaxation") + 1], "0.5")
                self.assertEqual(command[command.index("--duration") + 1], "1e-07")
                self.assertEqual(command[command.index("--dt") + 1], "1e-10")
                self.assertEqual(command[command.index("--max-steps") + 1], "250000")
                self.assertEqual(command[command.index("--time-refinement") + 1], "1")
            self.assertTrue((output / "DONE").exists())

    def test_legacy_profile_commands_emit_zero_divergence(self):
        revision = "b" * 40
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with patch.dict(os.environ, {"CUSP_SOURCE_REVISION": revision}), patch(
                "sys.argv", ["run_space_charge_pilot.py", "--out", str(output)]
            ), patch.object(runner.subprocess, "run", return_value=type("Result", (), {"returncode": 0})()):
                runner.main()
            commands = json.loads((output / "manifest.json").read_text())["commands"]
            self.assertTrue(all(command[command.index("--divergence-deg") + 1] == "0" for command in commands))


if __name__ == "__main__":
    unittest.main()
