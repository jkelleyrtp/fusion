"""Four bounded transient PIC controls on one broker-allocated GPU node."""

import argparse
import concurrent.futures
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from run_transient_pic import parser as pic_parser
from run_transient_pic import validate as validate_config


def commands(out: Path, revision: str) -> list[list[str]]:
    cases = (
        ("pic_vacuum", 0, 4e-12, 8, 1, 625),
        ("pic_1mA", 1e-3, 4e-12, 8, 1, 625),
        ("pic_1A", 1, 4e-12, 8, 1, 625),
        ("pic_1A_dt", 1, 2e-12, 8, 2, 1250),
    )
    result = []
    for device, (name, current, dt, packet, interval, stride) in enumerate(cases):
        result.append([
            sys.executable, str(Path(__file__).with_name("run_transient_pic.py")),
            "--out", str(out / name), "--device", f"cuda:{device}",
            "--source-revision", revision, "--nodes", "33", "--current-a", str(current),
            "--dt", str(dt), "--duration", "3e-8", "--inject-per-step", str(packet),
            "--inject-every", str(interval),
            "--coil-current", "30000", "--radius", "0.5", "--energy-ev", "5000",
            "--temperature-ev", "0.2", "--source-sigma", "5e-5",
            "--divergence-deg", "10", "--aim-deg", "30", "--seed", "1234",
            "--save-every", str(stride), "--track", "64",
            "--max-steps", "20000", "--max-live-particles", "150000", "--max-snapshots", "16",
        ])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-timeout", type=float, default=900)
    args = parser.parse_args()
    if not math.isfinite(args.case_timeout) or args.case_timeout <= 0:
        parser.error("case-timeout must be finite and positive")
    revision = os.environ["CUSP_SOURCE_REVISION"]
    argv = commands(args.out, revision)
    targets = [validate_config(pic_parser().parse_args(command[2:])) for command in argv]
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "source_revision": revision, "commands": argv, "progress_unit": "steps",
        "step_targets": targets,
        "purpose": (
            "FP64 transient electron startup, 5 keV compact external gun, 30 kA-turn, "
            "30 ns: vacuum, 1 mA, 1 A and half-step 1 A. Half-step retains the same "
            "packet charge, particles and physical pulse times. Numerical exploration, "
            "not physical convergence."
        ),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (args.out / "preflight.log").open("w") as log:
        preflight = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("validate_pic_gpu.py")),
             "--out", str(args.out / "preflight"), "--device", "cuda:0"],
            stdout=log, stderr=subprocess.STDOUT, timeout=args.case_timeout, check=False,
        )
    if preflight.returncode:
        (args.out / "STATUS").write_text("CPU/GPU preflight failed; no physical cases launched.\n")
        raise SystemExit(preflight.returncode)

    def run(index: int) -> int:
        name = Path(argv[index][3]).name
        with (args.out / f"{name}.log").open("w") as log:
            try:
                return subprocess.run(
                    argv[index], stdout=log, stderr=subprocess.STDOUT,
                    timeout=args.case_timeout, check=False,
                ).returncode
            except subprocess.TimeoutExpired:
                log.write("\nTIMEOUT: partial history preserved\n")
                return 124

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        codes = list(executor.map(run, range(4)))
    (args.out / "exit_codes.json").write_text(json.dumps(codes) + "\n")
    message = (
        "All transient cases completed; inspect accounting and convergence before interpretation.\n"
        if not any(codes) else "Incomplete transient campaign; inspect exit_codes.json and partial histories.\n"
    )
    (args.out / "STATUS").write_text(message)
    if any(codes):
        raise SystemExit(1)
    (args.out / "DONE").write_text("complete\n")


if __name__ == "__main__":
    main()
