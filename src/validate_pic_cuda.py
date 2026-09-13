"""Check CUDA particle operators against the shared FP64 PIC reference."""

import argparse
import json
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

import numpy as np
import torch

from cusp_sim import E_CHARGE, QM, TorchPusher
from electrostatic import ElectrostaticMesh
from pic_cuda import CUDAKernels
from pic_kernels import ReferenceKernels
from run_transient_pic import (
    GunSource,
    create_simulation,
    parser,
    save_snapshot,
    validate,
)
from transient_pic import PIC
from validate_pic_gpu import LIMITS, compare_states, control


def operator_controls(out: Path, device: torch.device) -> None:
    lower = torch.tensor([-1, -1.5, -2], dtype=torch.float64, device=device)
    mesh = ElectrostaticMesh(lower, -lower, (17, 19, 21))
    reference, actual = ReferenceKernels(mesh), CUDAKernels(mesh)
    generator = torch.Generator().manual_seed(314159)
    position = torch.rand((4096, 3), generator=generator, dtype=torch.float64).to(device)
    position = mesh.lower + position * (mesh.upper - mesh.lower)
    position[:2] = torch.stack((mesh.lower, mesh.upper))
    velocity = torch.randn((4096, 3), generator=generator, dtype=torch.float64).to(device) * 1e5
    charge = torch.rand(4096, generator=generator, dtype=torch.float64).to(device) * -1e-14
    potential = torch.randn(mesh.shape, generator=generator, dtype=torch.float64).to(device)
    magnetic = torch.randn((4096, 3), generator=generator, dtype=torch.float64).to(device) * 1e-3
    expected_charge = reference.deposit(position, charge)
    observed_charge = actual.deposit(position, charge)
    expected_electric = reference.gather(potential, position)
    observed_electric = actual.gather(potential, position)
    np.savez_compressed(
        out / "operators.npz", allow_pickle=False, position_m=position.cpu().numpy(),
        expected_charge_C=expected_charge.cpu().numpy(), observed_charge_C=observed_charge.cpu().numpy(),
        expected_electric_V_m=expected_electric.cpu().numpy(),
        observed_electric_V_m=observed_electric.cpu().numpy(),
    )
    torch.testing.assert_close(observed_charge, expected_charge, rtol=1e-12, atol=1e-26)
    torch.testing.assert_close(observed_charge.sum(), charge.sum(), rtol=1e-12, atol=1e-26)
    torch.testing.assert_close(observed_electric, expected_electric, rtol=1e-12, atol=1e-11)
    torch.testing.assert_close(
        actual.boris(velocity, expected_electric, magnetic, 1e-11),
        reference.boris(velocity, expected_electric, magnetic, 1e-11),
        rtol=1e-12, atol=1e-8,
    )
    rotated = actual.boris(velocity, torch.zeros_like(velocity), magnetic, 1e-11)
    torch.testing.assert_close(
        rotated.square().sum(dim=1), velocity.square().sum(dim=1), rtol=1e-12, atol=0,
    )
    for h in (1e-11, 1e-4):
        expected = reference.drift(position, velocity, h, 0.5)
        observed = actual.drift(position, velocity, h, 0.5)
        for result, target in zip(observed, expected, strict=True):
            floating = result.is_floating_point()
            torch.testing.assert_close(
                result, target, rtol=1e-12 if floating else 0, atol=1e-12 if floating else 0,
            )
    directions = position.new_tensor([
        [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0],
        [0, 0, -1], [0, 0, 1], [-1, -1, -1], [1, 1, 1],
    ])
    endpoints = directions * mesh.upper
    starts = torch.cat((torch.zeros_like(endpoints), mesh.lower[None], mesh.upper[None]))
    finishes = torch.cat((endpoints, torch.zeros_like(starts[:2])))
    expected = reference.drift(starts, finishes - starts, 1.0, 0.5)
    observed = actual.drift(starts, finishes - starts, 1.0, 0.5)
    for result, target in zip(observed, expected, strict=True):
        floating = result.is_floating_point()
        torch.testing.assert_close(
            result, target, rtol=1e-12 if floating else 0, atol=1e-12 if floating else 0,
        )
    assert observed[2].tolist() == [True] * 8 + [False] * 2
    assert observed[4].tolist() == [False] * 8 + [True] * 2
    torch.testing.assert_close(
        observed[3], 0.5 / (finishes - starts).norm(dim=1), rtol=1e-12, atol=1e-12,
    )
    torch.testing.assert_close(
        actual.potential(expected_charge), reference.potential(expected_charge),
        rtol=1e-10, atol=1e-13,
    )
    r = torch.linspace(0, 2.2, 256, dtype=torch.float64, device=device)
    z = torch.linspace(-2.1, 2.1, 512, dtype=torch.float64, device=device)
    samples = torch.cat((position, position.new_tensor([[0, 0, 0], [0, 0, -2.5], [2, 2, 2.5]])))
    tables = {
        "random": (
            torch.randn((512, 256), generator=generator, dtype=torch.float64).to(device),
            torch.randn((512, 256), generator=generator, dtype=torch.float64).to(device),
            1e-12,
        ),
        "smooth": (r[None] * torch.sin(z)[:, None], torch.cos(z)[:, None] * torch.exp(-r)[None], 1e-14),
    }
    differences = {}
    for name, (br, bz, atol) in tables.items():
        pusher = TorchPusher(br, bz, 0, float(r[1]), float(z[0]), float(z[1] - z[0]), QM)
        observed_field, expected_field = actual.magnetic_field(pusher)(samples), pusher.field(samples)
        differences[name] = {
            "max_abs": float((observed_field - expected_field).abs().max()),
            "unequal_fraction": float((observed_field != expected_field).double().mean()),
        }
        (out / "magnetic.json").write_text(json.dumps(differences, indent=2) + "\n")
        torch.testing.assert_close(observed_field, expected_field, rtol=1e-12, atol=atol)
        assert actual.magnetic_field(pusher)(position[:0]).shape == (0, 3)
    empty = position[:0]
    torch.testing.assert_close(actual.deposit(empty, charge[:0]), torch.zeros_like(expected_charge))
    assert actual.gather(potential, empty).shape == (0, 3)
    assert actual.boris(empty, empty, empty, 1e-11).shape == (0, 3)
    assert [tuple(item.shape) for item in actual.drift(empty, empty, 1e-11, 0.5)] == [
        (0, 3), (0,), (0,), (0,), (0,),
    ]


def closed_controls(out: Path, device: torch.device) -> None:
    for name in ("walls", "magnetic", "charged"):
        reference, h = control(name, device)
        actual, _ = control(name, device)
        actual.kernels = CUDAKernels(actual.mesh)
        for step in range(512):
            reference.advance(h)
            actual.advance(h)
            if step + 1 in (1, 32, 128, 512):
                compare_states(out, f"{name}-{step + 1}", reference, actual)


def external_controls(out: Path, device: torch.device) -> None:
    for current in (0.0, 1.0):
        name = f"external-{current:g}A"
        args = parser().parse_args([
            "--out", str(out / name), "--device", str(device),
            "--nodes", "33", "--coil-current", "30000", "--current-a", str(current),
            "--dt", "4e-12", "--duration", str(8192 * 4e-12),
            "--save-every", "2048", "--max-snapshots", "16",
        ])
        steps = validate(args)
        reference, configuration = create_simulation(args)
        actual = PIC(
            reference.mesh, reference.magnetic_field, reference.core_radius,
            args.max_live_particles, args.track, kernels=CUDAKernels(reference.mesh),
        )
        (out / f"{name}-configuration.json").write_text(
            json.dumps(configuration, indent=2, allow_nan=False) + "\n",
        )
        source = GunSource(args)
        for step in range(steps):
            for simulation in (reference, actual):
                source.inject(simulation, step)
                simulation.advance(args.dt)
                simulation.time = (step + 1) * args.dt
            if step + 1 in (1, 64, 512, 2048, 8192):
                compare_states(out, f"{name}-{step + 1}", reference, actual)
                print(f"{name}: {step + 1}/{steps} states agree", flush=True)
        for label, simulation in (("reference", reference), ("cuda", actual)):
            directory = out / f"{name}-{label}"
            directory.mkdir()
            record = save_snapshot(simulation, directory, steps, args.dt)
            assert record["time_s"] == simulation.time
            with np.load(directory / f"step-{steps:08d}.npz", allow_pickle=False) as snapshot:
                assert float(snapshot["time_s"]) == simulation.time
                np.testing.assert_array_equal(snapshot["ids"], simulation.particles.ids.cpu().numpy())
                np.testing.assert_array_equal(
                    snapshot["position_m"], simulation.particles.position.cpu().numpy(),
                )
                np.testing.assert_array_equal(
                    snapshot["tracked_exit_face"], simulation.tracked_exit_face.cpu().numpy(),
                )


def elapsed(operation: Callable[[], object], device: torch.device) -> float:
    for _ in range(2):
        operation()
    torch.cuda.synchronize(device)
    start = time.perf_counter()
    for _ in range(10):
        operation()
    torch.cuda.synchronize(device)
    return (time.perf_counter() - start) / 10


def benchmark(out: Path, device: torch.device) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for count in (1024, 32768, 131072):
        lower = torch.full((3,), -1.0, dtype=torch.float64, device=device)
        mesh = ElectrostaticMesh(lower, -lower, (33, 33, 33))
        generator = torch.Generator().manual_seed(100 + count)
        position = torch.rand((count, 3), generator=generator, dtype=torch.float64).to(device) - 0.5
        velocity = torch.randn((count, 3), generator=generator, dtype=torch.float64).to(device) * 1e5
        weight = position.new_full((count,), 1000)
        field = torch.zeros_like(position)
        charge = -E_CHARGE * weight
        nodal_charge = mesh.deposit(position, charge)
        potential = mesh.potential(nodal_charge)
        simulations = []
        for label, kernels in (("reference", ReferenceKernels(mesh)), ("cuda", CUDAKernels(mesh))):
            simulation = PIC(mesh, torch.zeros_like, 0.2, count, kernels=kernels)
            simulation.inject(position.clone(), velocity.clone(), weight.clone())
            simulations.append(simulation)
            operations: dict[str, Callable[[], object]] = {
                "deposit": partial(kernels.deposit, position, charge),
                "gather": partial(kernels.gather, potential, position),
                "drift": partial(kernels.drift, position, velocity, 5e-12, 0.2),
                "boris": partial(kernels.boris, velocity, field, field, 1e-11),
                "poisson": partial(mesh.potential, nodal_charge),
                "whole_step": partial(simulation.advance, 1e-11),
            }
            times = {name: elapsed(operation, device) for name, operation in operations.items()}
            rows.append({"particles": count, "backend": label, "seconds_per_call": times})
        compare_states(out, f"benchmark-{count}", simulations[0], simulations[1])
    return rows


def main() -> None:
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--out", type=Path, required=True)
    arguments.add_argument("--device", default="cuda:0")
    arguments.add_argument(
        "--controls-only", action="store_true",
        help="Stop after operator and closed controls; long runs use accept_pic_cuda.py",
    )
    args = arguments.parse_args()
    device = torch.device(args.device)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise ValueError("Validation requires a broker-allocated CUDA GPU")
    args.out.mkdir(parents=True, exist_ok=False)
    operator_controls(args.out, device)
    print("Local operators passed", flush=True)
    closed_controls(args.out, device)
    print("Closed controls passed", flush=True)
    if args.controls_only:
        (args.out / "PASSED").write_text("CUDA operator and closed controls passed\n")
        return
    external_controls(args.out, device)
    timings = benchmark(args.out, device)
    report = {
        "gpu": torch.cuda.get_device_name(device), "torch": torch.__version__,
        "precision": "float64", "mesh": [33, 33, 33], "timings": timings,
        "state_relative_tolerance": 1e-10, "state_absolute_tolerances": LIMITS,
        "scope": "local operators, closed controls, and matched 32.768 ns external-gun states; not physical convergence",
    }
    (args.out / "validation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (args.out / "PASSED").write_text("CUDA controls and external-gun comparisons passed\n")
    print(json.dumps(report, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
