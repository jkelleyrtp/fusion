"""Measure repeated FP64 reference runs without changing validation tolerances."""

import argparse
import json
from pathlib import Path

import torch

from cusp_sim import E_CHARGE
from diagnose_pic_cuda import difference
from pic_cuda import CUDAKernels
from run_transient_pic import create_simulation, inject_packet, parser, validate
from transient_pic import PIC
from validate_pic_gpu import LIMITS, compare_states, state


def repeated_operators(simulation: PIC, h: float) -> dict[str, object]:
    p = simulation.particles
    charge = -E_CHARGE * p.weight
    reference, actual = simulation.kernels, CUDAKernels(simulation.mesh)
    deposited = reference.deposit(p.position, charge)
    potential = simulation.mesh.potential(deposited)
    electric = reference.gather(potential, p.position)
    magnetic = simulation.magnetic_field(p.position)
    repeats: dict[str, object] = {}
    for name, kernels in (("reference", reference), ("cuda", actual)):
        first = kernels.deposit(p.position, charge)
        repeats[f"{name}_deposit_repeats"] = [
            difference(first, kernels.deposit(p.position, charge)) for _ in range(8)
        ]
        repeats[f"{name}_deposited_sum_C"] = float(first.sum())
    repeats["particle_charge_C"] = float(charge.sum())
    repeats["reference_vs_cuda_deposit"] = difference(
        deposited, actual.deposit(p.position, charge),
    )
    repeats["poisson_identical_input"] = difference(
        potential, simulation.mesh.potential(deposited),
    )
    repeats["gather_shared_potential"] = difference(
        electric, actual.gather(potential, p.position),
    )
    repeats["boris_shared_fields"] = difference(
        reference.boris(p.velocity, electric, magnetic, h),
        actual.boris(p.velocity, electric, magnetic, h),
    )
    return repeats


def main() -> None:
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--out", type=Path, required=True)
    arguments.add_argument("--device", default="cuda:0")
    arguments.add_argument("--deterministic-reference", action="store_true")
    options = arguments.parse_args()
    device = torch.device(options.device)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise ValueError("Reproducibility diagnosis requires a broker-allocated CUDA GPU")
    if options.deterministic_reference:
        torch.use_deterministic_algorithms(True, warn_only=False)
    options.out.mkdir(parents=True, exist_ok=False)
    args = parser().parse_args([
        "--out", str(options.out), "--device", str(device),
        "--nodes", "33", "--coil-current", "30000", "--current-a", "1",
        "--dt", "4e-12", "--duration", str(8192 * 4e-12),
        "--save-every", "2048", "--max-snapshots", "16",
    ])
    steps = validate(args)
    reference, configuration = create_simulation(args)
    configuration["diagnostic_deterministic_reference"] = options.deterministic_reference
    repeated = PIC(
        reference.mesh, reference.magnetic_field, reference.core_radius,
        args.max_live_particles, args.track,
    )
    (options.out / "configuration.json").write_text(
        json.dumps(configuration, indent=2, allow_nan=False) + "\n",
    )
    report: dict[str, object] = {
        "scope": "Reference repeatability and fixed-input operators; not CUDA validation",
        "gpu": torch.cuda.get_device_name(device),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "relative_tolerance": 1e-10,
        "absolute_tolerances": LIMITS,
        "steps": steps,
        "dt_s": args.dt,
        "deterministic_reference": options.deterministic_reference,
        "torch_deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "cuda_deposit": "custom atomic kernel; unaffected by Torch deterministic selection",
    }
    comparisons: list[dict[str, object]] = []
    report["comparisons"] = comparisons
    for step in range(steps):
        for simulation in (reference, repeated):
            inject_packet(simulation, args, step)
            simulation.advance(args.dt)
            simulation.time = (step + 1) * args.dt
        if step + 1 in (1, 64, 512, 2048, 8192):
            name = f"reference-repeat-{step + 1}"
            comparison: dict[str, object] = {"step": step + 1}
            try:
                compare_states(options.out, name, reference, repeated)
            except AssertionError as error:
                comparison["strict_comparison_passed"] = False
                comparison["error"] = str(error)
            else:
                comparison["strict_comparison_passed"] = True
            if options.deterministic_reference:
                expected, observed = state(reference), state(repeated)
                try:
                    for key in expected:
                        torch.testing.assert_close(
                            observed[key], expected[key], rtol=0, atol=0, equal_nan=True,
                            msg=f"{name}/{key}: deterministic reference state",
                        )
                except AssertionError as error:
                    comparison["exact_state_passed"] = False
                    comparison["exact_error"] = str(error)
                else:
                    comparison["exact_state_passed"] = True
            comparisons.append(comparison)
            (options.out / "reproducibility.json").write_text(
                json.dumps(report, indent=2, allow_nan=False) + "\n",
            )
            print(json.dumps(comparison), flush=True)
    report["fixed_input_operators"] = repeated_operators(reference, args.dt)
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    (options.out / "reproducibility.json").write_text(text)
    (options.out / "DIAGNOSTIC_COMPLETE").write_text(
        "Diagnostic completed; inspect comparisons. This is not a CUDA validation pass.\n",
    )
    print(text, flush=True)


if __name__ == "__main__":
    main()
