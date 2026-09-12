"""Eight reference and refinement cases on the broker's single allocated node."""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--track", type=int, default=64)
    parser.add_argument("--trajectory-frames", type=int, default=1025)
    parser.add_argument("--case-timeout", type=float, default=1800)
    args = parser.parse_args()
    revision = os.environ["CUSP_SOURCE_REVISION"]
    cases = [
        ("vacuum", 0, 33, 1024, 1e-10, 2e-7),
        ("1uA", 1e-6, 33, 1024, 1e-10, 2e-7),
        ("10uA", 1e-5, 33, 1024, 1e-10, 2e-7),
        ("100uA", 1e-4, 33, 1024, 1e-10, 2e-7),
        ("10uA_grid", 1e-5, 65, 1024, 1e-10, 2e-7),
        ("10uA_dt", 1e-5, 33, 1024, 1e-10, 2e-7),
        ("10uA_particles", 1e-5, 33, 4096, 1e-10, 2e-7),
        ("10uA_duration", 1e-5, 33, 1024, 1e-10, 4e-7),
    ]
    args.out.mkdir(parents=True, exist_ok=False)
    commands = []
    for device, (name, current, nodes, particles, dt, duration) in enumerate(cases):
        command = [
            sys.executable, str(Path(__file__).with_name("steady_space_charge.py")),
            "--out", str(args.out / name), "--device", f"cuda:{device}",
            "--source-revision", revision, "--current-a", str(current),
            "--nodes", str(nodes), "--particles", str(particles), "--dt", str(dt),
            "--duration", str(duration), "--radius", "0.05", "--coil-current", "1000",
            "--energy-ev", "5", "--temperature-ev", "0.2", "--source-sigma", "0.003",
            "--aim-deg", "30", "--relaxation", "0.5", "--iterations", "12",
            "--time-refinement", "2" if name == "10uA_dt" else "1", "--max-steps", "50000",
            "--track", str(args.track), "--trajectory-frames", str(args.trajectory_frames),
        ]
        commands.append(command)
    (args.out / "manifest.json").write_text(json.dumps(
        {"source_revision": revision, "commands": commands,
         "purpose": "small-geometry numerical reference; not a reactor well prediction"}, indent=2) + "\n")

    def run(index: int) -> int:
        with (args.out / f"{cases[index][0]}.log").open("w") as log:
            try:
                result = subprocess.run(commands[index], stdout=log, stderr=subprocess.STDOUT,
                                        timeout=args.case_timeout, check=False)
                return result.returncode
            except subprocess.TimeoutExpired:
                log.write("\nTIMEOUT: incomplete reference case\n")
                return 124

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        codes = list(executor.map(run, range(8)))
    (args.out / "exit_codes.json").write_text(json.dumps(codes) + "\n")
    if any(code not in (0, 124) for code in codes):
        raise SystemExit("Incomplete pilot: see exit_codes.json and case logs")
    (args.out / "DONE").write_text(datetime.now(timezone.utc).isoformat() + "\n")
    (args.out / "STATUS").write_text(
        "Partial results: cases timed out; inspect exit_codes.json.\n" if any(codes) else
        "All reference cases completed; inspect numerical convergence before interpretation.\n")


if __name__ == "__main__":
    main()
