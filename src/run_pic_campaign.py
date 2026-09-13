"""Four bounded transient PIC controls on one broker-allocated GPU node."""

import argparse
import concurrent.futures
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from ion_pic import parser as ion_parser
from ion_pic import validate_coupled
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

GUN_BARRELS = {
    "pic_1A_gun_wall": ((0.6, 1.3, 1.3), 0.0, 65, 1234),
    "pic_1A_gun_b1625": ((0.6, 1.625, 1.3), 0.06, 65, 1234),
    "pic_1A_gun_b195": ((0.6, 1.95, 1.3), 0.06, 65, 1234),
    "pic_1A_gun_b26": ((0.6, 2.6, 1.3), 0.06, 65, 1234),
    "pic_1A_gun_b195_r004": ((0.6, 1.95, 1.3), 0.04, 65, 1234),
    "pic_1A_gun_b195_r010": ((0.6, 1.95, 1.3), 0.10, 65, 1234),
    "pic_1A_gun_b195_s2345": ((0.6, 1.95, 1.3), 0.06, 65, 2345),
    "pic_1A_gun_b195_n97": ((0.6, 1.95, 1.3), 0.06, 97, 1234),
}

SIX_COILS = {
    "pic_1A_two_coil_dt2": (2, 0.5, (1.2, 1.95, 1.3), 0.0, 1, 1234),
    "pic_1A_six_d100": (6, 1.0, (1.2, 1.95, 1.3), 0.0, 1, 1234),
    "pic_1A_six_d100_1mA": (6, 1.0, (1.2, 1.95, 1.3), 0.0, 1e-3, 1234),
    "pic_1A_six_d110": (6, 1.1, (1.275, 1.95, 1.3), 0.0, 1, 1234),
    "pic_1A_six_d100_w1275": (6, 1.0, (1.275, 1.95, 1.3), 0.0, 1, 1234),
    "pic_1A_six_d100_t195": (6, 1.0, (1.2, 1.95, 1.95), 0.0, 1, 1234),
    "pic_1A_six_d100_p1kV": (6, 1.0, (1.2, 1.95, 1.3), 1000.0, 1, 1234),
    "pic_1A_six_d100_s2345": (6, 1.0, (1.2, 1.95, 1.3), 0.0, 1, 2345),
}

COIL_CASINGS = {
    "pic_1A_casing_none": ((0.6, 1.95, 1.3), 0.0, 0.0, 1234),
    "pic_1A_casing_r015": ((1.2, 1.95, 1.3), 0.15, 0.0, 1234),
    "pic_1A_casing_r015_w1275": ((1.275, 1.95, 1.3), 0.15, 0.0, 1234),
    "pic_1A_casing_r020": ((1.275, 1.95, 1.3), 0.20, 0.0, 1234),
    "pic_1A_casing_r015_p1kV": ((1.2, 1.95, 1.3), 0.15, 1000.0, 1234),
    "pic_1A_casing_r015_m1kV": ((1.2, 1.95, 1.3), 0.15, -1000.0, 1234),
    "pic_1A_casing_r015_s2345": ((1.2, 1.95, 1.3), 0.15, 0.0, 2345),
    "pic_1A_casing_r015_t195": ((1.2, 1.95, 1.95), 0.15, 0.0, 1234),
}
CASING_GUN_RADIUS = 0.06

ION_CASES = {
    "ions_p1e-3": (),
    "ions_p1e-3_nocx": ("--cx-cross-section", "0"),
    "ions_p1e-3_nosec": ("--no-secondaries",),
    "ions_p1e-2": ("--gas-pa", "1e-2", "--cycle-duration", "1e-6"),
    "ions_p1e-3_dt05": ("--ion-dt", "5e-10"),
    "ions_p1e-3_cycle5": ("--cycle-duration", "5e-6", "--cycles", "80", "--save-every-cycles", "8"),
    "ions_p1e-3_window80": ("--electron-window", "8e-8"),
    "ions_p1e-3_ions2x": ("--ions-per-cycle", "16384"),
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
        "gun": tuple(
            (name, 1, 4e-12, 8, 1, 7500, nodes, seed, "cuda")
            for name, (_, _, nodes, seed) in GUN_BARRELS.items()
        ),
        "casing": tuple(
            (name, 1, 4e-12, 8, 1, 7500, 65, seed, "cuda")
            for name, (_, _, _, seed) in COIL_CASINGS.items()
        ),
        "ions": tuple((name, 1, 4e-12, 8, 1, 7500, 65, 1234, "cuda") for name in ION_CASES),
        "six-coil": tuple(
            (name, current, 2e-12, 8, 2, 15000, 65, seed, "cuda")
            for name, (_, _, _, _, current, seed) in SIX_COILS.items()
        ),
    }[study]
    return list(cases)


def commands(
    out: Path, revision: str, study: str = "startup", kernels: str = "reference",
) -> list[list[str]]:
    result = []
    window = study in ("window", "domain", "gun", "casing", "ions", "six-coil")
    for device, (name, current, dt, packet, interval, stride, nodes, seed, backend) in enumerate(
        case_specs(study, kernels),
    ):
        limits = [
            "--duration", "3e-7", "--diagnostic-every", str(stride // 30),
            "--max-steps", "160000", "--max-live-particles", "3000000",
        ] if window else [
            "--duration", "3e-8", "--max-steps", "20000", "--max-live-particles", "150000",
        ]
        if study == "ions":
            limits = ["--max-live-particles", "3000000"]
        result.append([
            sys.executable, str(Path(__file__).with_name("ion_pic.py" if study == "ions" else "run_transient_pic.py")),
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
        if study == "gun":
            (width, bottom, top), radius, _, _ = GUN_BARRELS[name]
            result[-1] += [
                "--box-half-width", str(width), "--box-bottom", str(bottom), "--box-top", str(top),
                "--gun-radius", str(radius),
            ]
        if study in ("casing", "ions"):
            (width, bottom, top), casing, voltage, _ = COIL_CASINGS[
                "pic_1A_casing_r015" if study == "ions" else name
            ]
            result[-1] += [
                "--box-half-width", str(width), "--box-bottom", str(bottom), "--box-top", str(top),
                "--gun-radius", str(CASING_GUN_RADIUS), "--casing-radius", str(casing),
                "--casing-voltage", str(voltage),
            ]
        if study == "six-coil":
            count, offset, (width, bottom, top), voltage, _, _ = SIX_COILS[name]
            result[-1] += [
                "--box-half-width", str(width), "--box-bottom", str(bottom), "--box-top", str(top),
                "--gun-radius", str(CASING_GUN_RADIUS), "--casing-radius", "0.15",
                "--casing-voltage", str(voltage), "--coils", str(count), "--coil-offset", str(offset),
            ]
        if study == "ions":
            result[-1] += ["--gas-pa", "1e-3", "--cycles", "40", "--save-every-cycles", "4", *ION_CASES[name]]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-timeout", type=float, default=900)
    parser.add_argument(
        "--study",
        choices=("startup", "refinement", "acceptance", "window", "domain", "gun", "casing", "ions", "six-coil"),
        default="startup",
    )
    parser.add_argument("--kernels", choices=("reference", "cuda"), default="reference")
    args = parser.parse_args()
    if not math.isfinite(args.case_timeout) or args.case_timeout <= 0:
        parser.error("case-timeout must be finite and positive")
    revision = os.environ["CUSP_SOURCE_REVISION"]
    argv = commands(args.out, revision, args.study, args.kernels)
    targets = []
    for command in argv:
        if args.study == "ions":
            configuration = ion_parser().parse_args(command[2:])
            validate_coupled(configuration)
            targets.append(configuration.cycles)
        else:
            targets.append(validate_config(pic_parser().parse_args(command[2:])))
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "source_revision": revision, "commands": argv,
        "progress_unit": "cycles" if args.study == "ions" else "steps",
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
        ) if args.study == "domain" else (
            "CUDA 1 A grounded gun barrel, 300 ns: gun on the lower wall versus a grounded, "
            "absorbing barrel behind the emitter with the lower wall at 1.625a, 1.95a and 2.6a; "
            "barrel radius 0.04a/0.06a/0.10a, a second seed and a 97-node mesh at 1.95a. "
            "Tests whether a fixed emitter reference removes the bottom-wall sensitivity. "
            "Grounded outer box, imposed two-coil field, electron-only."
        ) if args.study == "gun" else (
            "CUDA 1 A absorbing toroidal coil casings, 300 ns, grounded 0.06a gun barrel with the "
            "lower wall at 1.95a: no casings in the coil-bounded 0.6a box versus 0.15a casings in "
            "1.2a and 1.275a boxes, 0.20a casings, casings at +1 kV and -1 kV, a second seed and "
            "a farther top wall. Tests whether the side-wall sensitivity survives once the box "
            "encloses the coils. Imposed two-coil field, electron-only."
        ) if args.study == "casing" else (
            "Coupled electron and H2+ PIC with electron-impact ionization in the 0.15a casing geometry "
            "(1 A, 5 keV): 1e-3 Pa over 40 x 10 us cycles, with charge exchange off, secondaries off, "
            "1e-2 Pa over 1 us cycles, half ion timestep, 5 us cycles, 80 ns electron windows and twice "
            "the ion macroparticles. Tests how fast ions neutralize the electron well and whether the "
            "operator-split cycle is converged. Imposed two-coil field, no Coulomb collisions."
        ) if args.study == "ions" else (
            "CUDA electron-only PIC, 300 ns at 2 ps with matched packets, 0.15a casings and the grounded "
            "0.06a gun barrel: two-coil cusp versus a six-coil cube (one coil per face, imposed vacuum "
            "field, coil planes 1.0a or 1.1a from the centre), a 1 mA six-coil control, a wider box, a "
            "farther top wall, casings at +1 kV and a second seed. Tests whether the six-coil geometry "
            "changes the potential structure and core dwell. No plasma magnetic feedback, no ions."
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
