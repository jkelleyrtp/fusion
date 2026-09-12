"""Read published Poisson progress without loading particle or field arrays."""

import argparse
import json
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
    codes: list[int] | None = None
    code_path = run / "exit_codes.json"
    if code_path.exists():
        value: object = json.loads(code_path.read_text())
        if not isinstance(value, list) or len(value) != len(commands) or not all(
            type(code) is int for code in value
        ):
            raise ValueError("Exit codes do not match manifest")
        codes = cast(list[int], value)
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
        target = int(settings["iterations"])
        if target < 1:
            raise ValueError("Invalid iteration target")
        snapshots = sorted((run / name / "viewer").glob("iteration-*/summary.json"))
        iteration = 0
        updated_at = None
        if snapshots:
            latest = snapshots[-1]
            summary = read_object(latest)
            diagnostics = summary["poisson"]
            if not isinstance(diagnostics, dict):
                raise ValueError("Missing Poisson diagnostics")
            step = diagnostics["iteration"]
            if type(step) is not int or not 0 <= step <= target:
                raise ValueError("Invalid published iteration")
            iteration = step
            updated_at = datetime.fromtimestamp(
                latest.stat().st_mtime, timezone.utc
            ).isoformat()
        code = codes[index] if codes is not None else None
        status = "running" if iteration else "pending"
        if code == 124:
            status = "timed_out"
        elif code is not None and code != 0:
            status = "failed"
        elif code == 0 or ((run / name / "STATUS").exists() and iteration == target):
            status = "completed"
        cases.append({
            "name": name,
            "iteration": iteration,
            "target": target,
            "status": status,
            "exitCode": code,
            "updatedAt": updated_at,
            "settings": {key: value for key, value in settings.items()
                         if key not in {"out", "device", "source-revision"}},
        })
    status_path = run / "STATUS"
    return {
        "attempt": run.name,
        "sourceRevision": manifest["source_revision"],
        "purpose": manifest["purpose"],
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
