"""Bounded Poisson studies on the broker's single allocated node."""

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
    parser.add_argument("--profile", choices=["reference", "high-voltage", "filament"], default="reference")
    args = parser.parse_args()
    revision = os.environ["CUSP_SOURCE_REVISION"]
    cases = [
        ("vacuum", 0, 33, 1024, 1e-10, 2e-7, 0.003, 0),
        ("1uA", 1e-6, 33, 1024, 1e-10, 2e-7, 0.003, 0),
        ("10uA", 1e-5, 33, 1024, 1e-10, 2e-7, 0.003, 0),
        ("100uA", 1e-4, 33, 1024, 1e-10, 2e-7, 0.003, 0),
        ("10uA_grid", 1e-5, 65, 1024, 1e-10, 2e-7, 0.003, 0),
        ("10uA_dt", 1e-5, 33, 1024, 1e-10, 2e-7, 0.003, 0),
        ("10uA_particles", 1e-5, 33, 4096, 1e-10, 2e-7, 0.003, 0),
        ("10uA_duration", 1e-5, 33, 1024, 1e-10, 4e-7, 0.003, 0),
    ]
    coil_currents = {name: 1000 for name, *_ in cases}
    radius, energy = 0.05, 5
    iterations = 12
    max_steps = 50000
    purpose = "small-geometry numerical reference; not a reactor well prediction"
    case_timeout = args.case_timeout if args.case_timeout is not None else 1800
    if args.profile == "high-voltage":
        cases = [
            ("30kAt_vacuum", 0, 33, 1024, 1e-10, 1e-7, 0.03, 0),
            ("30kAt_1A", 1, 33, 1024, 1e-10, 1e-7, 0.03, 0),
            ("100kAt_vacuum", 0, 33, 1024, 1e-10, 1e-7, 0.03, 0),
            ("100kAt_1A", 1, 33, 1024, 1e-10, 1e-7, 0.03, 0),
        ]
        coil_currents = dict(zip((case[0] for case in cases), [30000, 30000, 100000, 100000], strict=True))
        radius, energy = 0.5, 5000
        iterations = 8
        max_steps = 100000
        purpose = (
            "5 keV exploration: 50 cm coils, 30/100 kA-turn, vacuum versus 1 A beam; "
            "scaled 3 cm RMS source, 30 degree aim, 100 ns orbit window. "
            "Nonrelativistic FP64 stationary Poisson pilot; no convergence or well-depth claim."
        )
    elif args.profile == "filament":
        cases = [
            ("broad_vacuum", 0, 33, 1024, 1e-10, 1e-7, 0.03, 0),
            ("broad_1A", 1, 33, 1024, 1e-10, 1e-7, 0.03, 0),
            ("compact_vacuum", 0, 33, 1024, 1e-10, 1e-7, 5e-5, 10),
            ("compact_1A", 1, 33, 1024, 1e-10, 1e-7, 5e-5, 10),
        ]
        coil_currents = {name: 30000 for name, *_ in cases}
        radius, energy = 0.5, 5000
        iterations = 8
        max_steps = 250000
        case_timeout = 1200
        purpose = (
            "5 keV compact-source comparison: broad 3 cm / 0 degree versus assumed "
            "50 um / 10 degree post-extraction source, each vacuum and 1 A; "
            "30 kA-turn, FP64 stationary Poisson; no convergence claim."
        )
    args.out.mkdir(parents=True, exist_ok=False)
    commands = []
    for device, (name, current, nodes, particles, dt, duration, sigma, divergence) in enumerate(cases):
        command = [
            sys.executable, str(Path(__file__).with_name("steady_space_charge.py")),
            "--out", str(args.out / name), "--device", f"cuda:{device}",
            "--source-revision", revision, "--current-a", str(current),
            "--nodes", str(nodes), "--particles", str(particles), "--dt", str(dt),
            "--duration", str(duration), "--radius", str(radius), "--coil-current", str(coil_currents[name]),
            "--energy-ev", str(energy), "--temperature-ev", "0.2", "--source-sigma", str(sigma),
            "--divergence-deg", str(divergence), "--aim-deg", "30", "--relaxation", "0.5",
            "--iterations", str(iterations),
            "--time-refinement", "2" if name == "10uA_dt" else "1", "--max-steps", str(max_steps),
            "--track", str(args.track), "--trajectory-frames", str(args.trajectory_frames),
        ]
        commands.append(command)
    (args.out / "manifest.json").write_text(json.dumps(
        {"source_revision": revision, "commands": commands,
         "purpose": purpose}, indent=2) + "\n")

    def run(index: int) -> int:
        with (args.out / f"{cases[index][0]}.log").open("w") as log:
            try:
                result = subprocess.run(commands[index], stdout=log, stderr=subprocess.STDOUT,
                                        timeout=case_timeout, check=False)
                return result.returncode
            except subprocess.TimeoutExpired:
                log.write("\nTIMEOUT: incomplete reference case\n")
                return 124

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(cases)) as executor:
        codes = list(executor.map(run, range(len(cases))))
    (args.out / "exit_codes.json").write_text(json.dumps(codes) + "\n")
    if any(code not in (0, 124) for code in codes):
        raise SystemExit("Incomplete pilot: see exit_codes.json and case logs")
    (args.out / "DONE").write_text(datetime.now(timezone.utc).isoformat() + "\n")
    (args.out / "STATUS").write_text(
        "Partial results: cases timed out; inspect exit_codes.json.\n" if any(codes) else
        "All reference cases completed; inspect numerical convergence before interpretation.\n")


if __name__ == "__main__":
    main()
