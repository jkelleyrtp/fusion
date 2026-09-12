"""One-node fixed-field scan; every case retains its exact launch command."""

import argparse
import concurrent.futures
import itertools
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ELECTRON_CHARGE = 1.602176634e-19
ELECTRON_MASS = 9.1093837015e-31


def cases() -> list[dict[str, float | str]]:
    result: list[dict[str, float | str]] = []
    for current, angle, energy, cone in itertools.product(
        (50000, 250000, 1000000, 2000000), (0, 15, 30, 60),
        (5, 50, 500, 5000), (1, 10),
    ):
        result.append({
            "id": f"I{current}_A{angle}_E{energy}_C{cone}",
            "current": current, "angle": angle, "energy": energy, "cone": cone,
            "grid_r": 512, "grid_z": 1024, "gyro_fraction": 0.0125,
        })
    # Paired initial samples: numerical controls for low-energy, high-field tails.
    for current, angle in itertools.product((50000, 2000000), (0, 30)):
        result.append({
            "id": f"I{current}_A{angle}_E5_C1_refined",
            "current": current, "angle": angle, "energy": 5, "cone": 1,
            "grid_r": 1024, "grid_z": 2048, "gyro_fraction": 0.00625,
        })
    return result


def command(case: dict[str, float | str], output: Path, gpu: int) -> list[str]:
    energy = float(case["energy"])
    angle = math.radians(float(case["angle"]))
    speed = math.sqrt(2 * ELECTRON_CHARGE * energy / ELECTRON_MASS)
    duration = 50 * 0.5 / speed
    return [
        sys.executable, str(Path(__file__).with_name("cusp_sim.py")),
        "--out", str(output), "--device", f"cuda:{gpu}",
        "--ring-radius", "0.5", "--ring-half-sep", "0.25",
        "--current", str(case["current"]),
        "--inject-mode", "gun", "--inject-offset", "0.3",
        "--axial-margin", "0.4", "--inject-sigma", "0.0005",
        "--gun-direction", "0", str(-math.sin(angle)), str(math.cos(angle)),
        "--members", f"{energy},0.004,0,{case['cone']},0",
        "--space-charge-radius", "0.15", "--particles", "32768",
        "--sim-time", str(duration), "--block-steps", "2000",
        "--grid-r", str(case["grid_r"]), "--grid-z", str(case["grid_z"]),
        "--steps-per-gyro-inv", str(case["gyro_fraction"]),
        "--tracked", "32", "--traj-samples", "4096",
        "--traj-dt", str(duration / 4096), "--seed", "1234",
    ]


def execute_lane(gpu: int, assigned: list[dict[str, float | str]], root: Path) -> list[str]:
    failures = []
    for case in assigned:
        directory = root / str(case["id"])
        directory.mkdir()
        args = command(case, directory, gpu)
        (directory / "command.json").write_text(json.dumps(args, indent=2) + "\n")
        print(f"START GPU {gpu}: {case['id']}", flush=True)
        with (directory / "stdout.log").open("w") as log:
            try:
                subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                failures.append(str(case["id"]))
                (directory / "FAILED").write_text(str(error) + "\n")
        print(f"END GPU {gpu}: {case['id']}", flush=True)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    specs = cases()
    if args.dry_run:
        print(json.dumps([command(case, args.out / str(case["id"]), i % 8)
                          for i, case in enumerate(specs)], indent=2))
        return
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "cases": specs, "particles_per_case": 32768, "radius_m": 0.5,
        "duration_transits_a_over_v": 50, "space_charge": "none",
        "source": "Gaussian position; uniform-solid-angle velocity cone, not a calibrated thermionic source",
        "source_sigma_m": 0.0005, "gpu_count": 8,
        "git_revision": os.environ["CUSP_SOURCE_REVISION"],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(execute_lane, gpu, specs[gpu::8], args.out) for gpu in range(8)]
        failures = list(itertools.chain.from_iterable(future.result() for future in futures))
    (args.out / "failures.json").write_text(json.dumps(failures) + "\n")
    if failures:
        raise SystemExit(f"{len(failures)} cases failed; see failures.json")
    (args.out / "DONE").write_text(datetime.now(timezone.utc).isoformat() + "\n")


if __name__ == "__main__":
    main()
