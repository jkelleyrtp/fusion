"""Read published Poisson or transient PIC progress without loading particle arrays."""

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import cast


def read_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError(f"Expected an object in {path.name}")
    return cast(dict[str, object], value)


def read_progress(root: Path) -> dict[str, object] | None:
    attempts = sorted(
        (path for path in root.glob("attempt-*") if path.is_dir()),
        key=lambda path: path.name,
    )
    run = attempts[-1] if attempts else root
    manifest_path = run / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = read_object(manifest_path)
    commands = manifest["commands"]
    if not isinstance(commands, list):
        raise TypeError("Manifest commands must be a list")
    progress_unit = manifest.get("progress_unit", "iterations")
    if progress_unit not in {"iterations", "steps", "cycles"}:
        raise ValueError("Unknown progress unit")
    step_targets: list[int] | None = None
    if progress_unit in {"steps", "cycles"}:
        targets = manifest.get("step_targets")
        if (
            not isinstance(targets, list) or len(targets) != len(commands)
            or not all(type(target) is int and target > 0 for target in targets)
        ):
            raise ValueError("Step targets do not match manifest")
        step_targets = cast(list[int], targets)
    codes: list[int] | None = None
    code_path = run / "exit_codes.json"
    if code_path.exists():
        exit_value: object = json.loads(code_path.read_text())
        if not isinstance(exit_value, list) or len(exit_value) != len(commands) or not all(
            type(code) is int for code in exit_value
        ):
            raise ValueError("Exit codes do not match manifest")
        codes = cast(list[int], exit_value)
    cases = []
    for index, command in enumerate(commands):
        if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
            raise ValueError("Manifest command must contain strings")
        argv = cast(list[str], command)
        settings = {}
        for offset, arg in enumerate(argv[:-1]):
            if arg.startswith("--"):
                settings[arg[2:]] = argv[offset + 1]
        name = Path(settings["out"]).name
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid case name")
        case_dir = run / name
        iteration = 0
        updated_at = None
        physical_time = 0.0
        history_exists = False
        if step_targets is None:
            target = int(settings["iterations"])
            if target < 1:
                raise ValueError("Invalid iteration target")
            snapshots = sorted(case_dir.glob("viewer/iteration-*/summary.json"))
            if snapshots:
                latest_snapshot = snapshots[-1]
                summary = read_object(latest_snapshot)
                diagnostics = summary["poisson"]
                if not isinstance(diagnostics, dict):
                    raise ValueError("Missing Poisson diagnostics")
                step = diagnostics["iteration"]
                if type(step) is not int or not 0 <= step <= target:
                    raise ValueError("Invalid published iteration")
                iteration = step
                updated_at = datetime.fromtimestamp(
                    latest_snapshot.stat().st_mtime, timezone.utc
                ).isoformat()
        else:
            target = step_targets[index]
            history_path = case_dir / "history.json"
            if history_path.exists():
                history_exists = True
                try:
                    history_value: object = json.loads(history_path.read_text())
                except json.JSONDecodeError as error:
                    raise ValueError("Malformed PIC history") from error
                if (
                    not isinstance(history_value, list) or not history_value
                    or not all(isinstance(record, dict) for record in history_value)
                ):
                    raise ValueError("Malformed PIC history")
                latest_history = cast(list[dict[str, object]], history_value)[-1]
                step = latest_history.get("cycle" if progress_unit == "cycles" else "step")
                time = latest_history.get("time_s")
                try:
                    if progress_unit == "cycles":
                        if "cycle-duration" in settings:
                            duration = int(settings["cycles"]) * float(settings["cycle-duration"])
                        else:
                            configuration = json.loads((case_dir / "configuration.json").read_text())
                            duration = int(configuration["cycles"]) * float(configuration["cycle_duration"])
                    else:
                        duration = float(settings["duration"])
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError("Invalid published PIC duration") from error
                if not math.isfinite(duration):
                    raise ValueError("Invalid published PIC duration")
                if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step <= target:
                    raise ValueError("Invalid published PIC step")
                if not isinstance(time, (int, float)) or isinstance(time, bool):
                    raise ValueError("Invalid published PIC time")
                published_time = float(time)
                if (
                    not math.isfinite(published_time) or published_time < 0
                    or published_time > duration * (1 + 1e-9) + 1e-18
                ):
                    raise ValueError("Invalid published PIC time")
                iteration = step
                physical_time = published_time
                updated_at = datetime.fromtimestamp(
                    history_path.stat().st_mtime, timezone.utc
                ).isoformat()
        code = codes[index] if codes is not None else None
        if step_targets is None:
            status = "running" if iteration else "pending"
            if code == 124:
                status = "timed_out"
            elif code is not None and code != 0:
                status = "failed"
            elif code == 0 or (case_dir / "STATUS").exists() and iteration == target:
                status = "completed"
        else:
            status = "running" if history_exists else "pending"
            if code == 124:
                status = "timed_out"
            elif code is not None and code != 0:
                status = "failed"
            elif (
                (case_dir / "DONE").exists() and iteration == target
                and (code is None or code == 0)
            ):
                status = "completed"
        case = {
            "name": name,
            "iteration": iteration,
            "target": target,
            "status": status,
            "exitCode": code,
            "updatedAt": updated_at,
            "settings": {key: value for key, value in settings.items()
                         if key not in {"out", "device", "source-revision"}},
        }
        if step_targets is not None:
            case["physicalTimeS"] = physical_time
        cases.append(case)
    status_path = run / "STATUS"
    return {
        "attempt": run.name,
        "sourceRevision": manifest["source_revision"],
        "purpose": manifest["purpose"],
        "progressUnit": progress_unit,
        "done": (run / "DONE").exists(),
        "statusText": status_path.read_text().strip() if status_path.exists() else None,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_directory):
        raise ValueError("Expected a run directory name")
    root = Path("/public/devcontainer-shared/jonathan/cusp/runs") / args.run_directory
    print(json.dumps(read_progress(root), allow_nan=False))


if __name__ == "__main__":
    main()
