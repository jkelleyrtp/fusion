"""Compare the transient PIC device implementation against fixed CPU controls."""

import argparse
import json
import math
import time
from pathlib import Path
from typing import cast

import numpy as np
import torch

from electrostatic import ElectrostaticMesh
from pic_cuda import CUDAKernels
from run_transient_pic import (
    CoilSuperposition,
    coil_casings,
    coils,
    mesh_shape,
    parser,
    six_coil_field,
)
from transient_pic import PIC

LIMITS = {
    "position_m": 1e-13, "velocity_m_s": 1e-5, "weight": 0,
    "dwell_s": 1e-22, "core_dwell_s": 1e-22, "charge_C": 1e-25,
    "potential_V": 1e-10, "tracked_position_m": 1e-13,
    "tracked_exit_time_s": 1e-22, "birth_s": 1e-22, "tracked_birth_s": 1e-22,
}


def control(name: str, device: torch.device) -> tuple[PIC, float]:
    lower = torch.full((3,), -1.0, dtype=torch.float64, device=device)
    mesh = ElectrostaticMesh(lower, -lower, (17, 17, 17))

    def field(position: torch.Tensor) -> torch.Tensor:
        result = torch.zeros_like(position)
        if name == "magnetic":
            result[:, 2] = 0.001
        return result

    simulation = PIC(mesh, field, 0.2, 4096, track=6)
    if name == "walls":
        direction = torch.tensor(
            [[-1, 0, 0], [1, 0, 0], [0, -1, 0],
             [0, 1, 0], [0, 0, -1], [0, 0, 1]], dtype=torch.float64,
        )
        position, velocity = 0.999 * direction, 1e6 * direction
        weight = direction.new_zeros(6)
        h = 1e-8
    else:
        generator = torch.Generator().manual_seed(24680)
        position = torch.rand((256, 3), generator=generator, dtype=torch.float64) * 0.4 - 0.2
        velocity = torch.randn((256, 3), generator=generator, dtype=torch.float64) * 1e5
        weight = position.new_full((256,), 1e5 if name == "charged" else 0)
        h = 1e-10
    simulation.inject(position.to(device), velocity.to(device), weight.to(device))
    return simulation, h


def state(simulation: PIC) -> dict[str, torch.Tensor]:
    p = simulation.particles
    charge, potential = simulation.fields()
    return {
        "ids": p.ids, "birth_s": p.birth, "position_m": p.position, "velocity_m_s": p.velocity,
        "weight": p.weight, "dwell_s": p.dwell, "core_dwell_s": p.core_dwell,
        "entries": p.entries, "charge_C": charge, "potential_V": potential,
        "exit_counts": simulation.exit_counts,
        "tracked_position_m": simulation.tracked_position,
        "tracked_birth_s": simulation.tracked_birth,
        "tracked_exit_time_s": simulation.tracked_exit_time,
        "tracked_exit_face": simulation.tracked_exit_face,
    }


def compare_states(out: Path, name: str, reference: PIC, actual: PIC) -> None:
    expected_state, actual_state = state(reference), state(actual)
    np.savez_compressed(
        out / f"{name}.npz", allow_pickle=False,
        **{f"reference_{key}": value.cpu().numpy() for key, value in expected_state.items()},
        **{f"actual_{key}": value.cpu().numpy() for key, value in actual_state.items()},
    )
    for key in expected_state:
        expected, observed = expected_state[key].cpu(), actual_state[key].cpu()
        def message(text: str, label: str = f"{name}/{key}") -> str:
            return f"{label}: {text}"
        torch.testing.assert_close(
            observed, expected, rtol=1e-10 if expected.is_floating_point() else 0,
            atol=LIMITS.get(key, 0), equal_nan=True, msg=message,
        )
    diagnostics = []
    for simulation in (reference, actual):
        charge, potential = simulation.fields()
        record = simulation.diagnostics(charge, potential)
        diagnostics.append(record)
        scale = max(abs(cast(float, record["injected_charge_C"])), 1e-30)
        if abs(cast(float, record["charge_balance_C"])) > 1e-12 * scale:
            raise AssertionError(f"{name}: charge balance failed")
        if abs(cast(float, record["deposition_error_C"])) > 1e-12 * scale:
            raise AssertionError(f"{name}: deposition accounting failed")
    (out / f"{name}.json").write_text(json.dumps(diagnostics, indent=2, allow_nan=False) + "\n")
    for key, expected_value in diagnostics[0].items():
        actual_value = diagnostics[1][key]
        if key in ("charge_balance_C", "deposition_error_C"):
            continue
        if isinstance(expected_value, (int, list)):
            assert actual_value == expected_value, (name, key, actual_value, expected_value)
        else:
            assert isinstance(actual_value, float)
            absolute = 1e-10 if key == "minimum_potential_V" else 1e-25 if key.endswith("_C") else 1e-24
            if key.endswith("_J"):
                absolute = 1e-10 * max(abs(cast(float, diagnostics[0]["injected_kinetic_J"])), 1e-30)
            assert math.isclose(actual_value, expected_value, rel_tol=1e-10, abs_tol=absolute), (
                name, key, actual_value, expected_value,
            )


def six_coil_control(device: torch.device) -> dict[str, object]:
    """CUDA table lookup of the rotated six-coil superposition against the CPU reference field."""
    args = parser().parse_args([
        "--out", "unused", "--nodes", "17", "--radius", "0.5", "--coils", "6", "--coil-offset", "1.0",
        "--casing-radius", "0.15", "--box-half-width", "1.2", "--box-bottom", "1.95", "--box-top", "1.3",
        "--coil-current", "30000",
    ])
    fields = []
    generator = torch.Generator().manual_seed(13579)
    unit = torch.rand((65536, 3), generator=generator, dtype=torch.float64)
    for where in (torch.device("cpu"), device):
        lower = torch.tensor([-0.6, -0.6, -0.975], dtype=torch.float64, device=where)
        upper = torch.tensor([0.6, 0.6, 0.65], dtype=torch.float64, device=where)
        pusher, reference, _, _ = six_coil_field(args, where, lower, upper)
        points = lower + (upper - lower) * unit.to(where)
        windings = torch.zeros(len(points), dtype=torch.bool, device=where)
        for casing in coil_casings(args):
            windings |= casing.contains(points)
        points = points[~windings]
        fields.append(reference(points))
        if where.type == "cuda":
            cuda = CUDAKernels(ElectrostaticMesh(lower, upper, mesh_shape(args)))
            fields.append(CoilSuperposition(cuda.magnetic_field(pusher), coils(args), args.coil_current)(points))
    expected = fields[0]
    for observed in fields[1:]:
        torch.testing.assert_close(observed.cpu(), expected, rtol=1e-10, atol=1e-15)
    return {"control": "six_coil_field", "points": len(expected), "passed": True,
            "max_T": float(expected.norm(dim=1).max())}


def validate(out: Path, device: torch.device) -> dict[str, object]:
    if device.type != "cuda" or not torch.cuda.is_available():
        raise ValueError("GPU validation requires a broker-allocated CUDA device")
    out.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, object]] = []
    for name in ("walls", "magnetic", "charged"):
        cpu, h = control(name, torch.device("cpu"))
        gpu, _ = control(name, device)
        cpu_start = time.perf_counter()
        for _ in range(128):
            cpu.advance(h)
        cpu_s = time.perf_counter() - cpu_start
        torch.cuda.synchronize(device)
        gpu_start = time.perf_counter()
        for _ in range(128):
            gpu.advance(h)
        torch.cuda.synchronize(device)
        gpu_s = time.perf_counter() - gpu_start
        compare_states(out, name, cpu, gpu)
        rows.append({"control": name, "steps": 128, "dt_s": h,
                     "cpu_s": cpu_s, "gpu_s": gpu_s, "passed": True})
    rows.append(six_coil_control(device))
    report = {
        "gpu": torch.cuda.get_device_name(device), "torch": torch.__version__,
        "precision": "float64", "relative_tolerance": 1e-10,
        "absolute_tolerances": LIMITS, "controls": rows,
        "scope": "fixed CPU/GPU numerical controls; no physical convergence claim",
    }
    (out / "validation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (out / "PASSED").write_text("CPU/GPU controls passed\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    print(json.dumps(validate(args.out, torch.device(args.device)), allow_nan=False))


if __name__ == "__main__":
    main()
