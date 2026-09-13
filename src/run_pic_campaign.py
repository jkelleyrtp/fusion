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

DOMAIN_BOXES = {
    "pic_1A_box": (0.6, 1.3, 1.3),
    "pic_1A_box_w0525": (0.525, 1.3, 1.3),
    "pic_1A_box_w045": (0.45, 1.3, 1.3),
    "pic_1A_box_t195": (0.6, 1.3, 1.95),
    "pic_1A_box_t26": (0.6, 1.3, 2.6),
    "pic_1A_box_b1625": (0.6, 1.625, 1.3),
    "pic_1A_box_b195": (0.6, 1.95, 1.3),
    "pic_1A_box_b195_t26": (0.6, 1.95, 2.6),
}


def case_specs(
    study: str, kernels: str,
) -> list[tuple[str, float, float, int, int, int, int, int, str]]:
    cases = {
        "startup": (
            ("pic_vacuum", 0, 4e-12, 8, 1, 625, 33, 1234, kernels),
            ("pic_1mA", 1e-3, 4e-12, 8, 1, 625, 33, 1234, kernels),
            ("pic_1A", 1, 4e-12, 8, 1, 625, 33, 1234, kernels),
            ("pic_1A_dt", 1, 2e-12, 8, 2, 1250, 33, 1234, kernels),
        ),
        "refinement": (
            ("pic_1A", 1, 4e-12, 8, 1, 625, 33, 1234, kernels),
            ("pic_1A_dt", 1, 2e-12, 8, 2, 1250, 33, 1234, kernels),
            ("pic_1A_mesh", 1, 4e-12, 8, 1, 625, 65, 1234, kernels),
            ("pic_1A_particles", 1, 4e-12, 16, 1, 625, 33, 1234, kernels),
        ),
        "acceptance": tuple(
            (f"pic_1A_s{seed}_{backend}", 1, 4e-12, 8, 1, 625, 33, seed, backend)
            for seed in (1234, 2345, 3456, 4567)
            for backend in ("reference", "cuda")
        ),
        "window": (
            *((f"pic_1A_n{nodes}", 1, 4e-12, 8, 1, 7500, nodes, 1234, "cuda")
              for nodes in (33, 49, 65, 97, 129)),
            ("pic_1A_n65_particles", 1, 4e-12, 16, 1, 7500, 65, 1234, "cuda"),
            ("pic_1A_n65_dt", 1, 2e-12, 8, 2, 15000, 65, 1234, "cuda"),
            ("pic_1A_n65_s2345", 1, 4e-12, 8, 1, 7500, 65, 2345, "cuda"),
        ),
        "domain": tuple(
            (name, 1, 4e-12, 8, 1, 7500, 65, 1234, "cuda") for name in DOMAIN_BOXES
        ),
    }[study]
    return list(cases)


def commands(
    out: Path, revision: str, study: str = "startup", kernels: str = "reference",
) -> list[list[str]]:
    result = []
    window = study in ("window", "domain")
    for device, (name, current, dt, packet, interval, stride, nodes, seed, backend) in enumerate(
        case_specs(study, kernels),
    ):
        limits = [
            "--duration", "3e-7", "--diagnostic-every", str(stride // 30),
            "--max-steps", "160000", "--max-live-particles", "3000000",
        ] if window else [
            "--duration", "3e-8", "--max-steps", "20000", "--max-live-particles", "150000",
        ]
        result.append([
            sys.executable, str(Path(__file__).with_name("run_transient_pic.py")),
            "--out", str(out / name), "--device", f"cuda:{device}",
            "--kernels", backend, "--source-revision", revision,
            "--nodes", str(nodes), "--current-a", str(current),
            "--dt", str(dt), *limits, "--inject-per-step", str(packet),
            "--inject-every", str(interval),
            "--coil-current", "30000", "--radius", "0.5", "--energy-ev", "5000",
            "--temperature-ev", "0.2", "--source-sigma", "5e-5",
            "--divergence-deg", "10", "--aim-deg", "30", "--seed", str(seed),
            "--save-every", str(stride), "--track", "64", "--max-snapshots", "16",
        ])
        if study == "domain":
            width, bottom, top = DOMAIN_BOXES[name]
            result[-1] += [
                "--box-half-width", str(width), "--box-bottom", str(bottom), "--box-top", str(top),
            ]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-timeout", type=float, default=900)
    parser.add_argument(
        "--study", choices=("startup", "refinement", "acceptance", "window", "domain"),
        default="startup",
    )
    parser.add_argument("--kernels", choices=("reference", "cuda"), default="reference")
    args = parser.parse_args()
    if not math.isfinite(args.case_timeout) or args.case_timeout <= 0:
        parser.error("case-timeout must be finite and positive")
    revision = os.environ["CUSP_SOURCE_REVISION"]
    argv = commands(args.out, revision, args.study, args.kernels)
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
        ) if args.study == "startup" else (
            "FP64 1 A transient sensitivity: baseline, matched-packet half timestep, "
            "65-cubed mesh and twice the particles per packet. All use 30 ns and "
            "identical physical source geometry/current/cadence. Particle refinement "
            "changes Monte Carlo samples; one realization does not establish convergence."
        ) if args.study == "refinement" else (
            "Physics-level CUDA acceptance: four independent seeds, each run with "
            "FP64 reference and CUDA operators (1 A, 5 keV, 30 kA-turn, 33-cubed, "
            "30 ns). Paired differences are judged against reference seed-to-seed "
            "spread; not bitwise parity, not physical convergence."
        ) if args.study == "acceptance" else (
            "CUDA 1 A long-window sensitivity: 300 ns (10x startup) to test whether the "
            "electron population, potential and losses saturate. Meshes 33/49/65/97/129, "
            "plus at 65-cubed: twice the particles per packet, matched-packet half "
            "timestep and a second seed. Scalar diagnostics every 1 ns. One realization "
            "per setting; grounded box, imposed two-coil field, electron-only."
        ) if args.study == "window" else (
            "CUDA 1 A grounded-box sensitivity, 300 ns, cells of the 65-cubed reference box: "
            "narrower transverse walls (the coils bound widening), a farther top wall, "
            "and a farther bottom wall that leaves the gun inside the box. Same gun, "
            "field, seed and packets. One realization per box; electron-only."
        ),
        "study": args.study, "kernels": args.kernels,
        "cases": [
            {"name": name, "kernels": backend, "seed": seed, "device": f"cuda:{device}"}
            for device, (name, _, _, _, _, _, _, seed, backend) in enumerate(
                case_specs(args.study, args.kernels),
            )
        ],
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(argv)) as executor:
        codes = list(executor.map(run, range(len(argv))))
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
