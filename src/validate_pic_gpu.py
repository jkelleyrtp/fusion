"""Compare the transient PIC device implementation against fixed CPU controls."""

import argparse
import json
import time
from pathlib import Path
from typing import cast

import numpy as np
import torch

from electrostatic import ElectrostaticMesh
from transient_pic import PIC


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
        "ids": p.ids, "position_m": p.position, "velocity_m_s": p.velocity,
        "weight": p.weight, "dwell_s": p.dwell, "core_dwell_s": p.core_dwell,
        "entries": p.entries, "charge_C": charge, "potential_V": potential,
        "exit_counts": simulation.exit_counts,
        "tracked_position_m": simulation.tracked_position,
        "tracked_exit_time_s": simulation.tracked_exit_time,
        "tracked_exit_face": simulation.tracked_exit_face,
    }


def validate(out: Path, device: torch.device) -> dict[str, object]:
    if device.type != "cuda" or not torch.cuda.is_available():
        raise ValueError("GPU validation requires a broker-allocated CUDA device")
    out.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, object]] = []
    limits = {
        "position_m": 1e-13, "velocity_m_s": 1e-5, "weight": 0,
        "dwell_s": 1e-22, "core_dwell_s": 1e-22, "charge_C": 1e-25,
        "potential_V": 1e-10, "tracked_position_m": 1e-13,
        "tracked_exit_time_s": 1e-22,
    }
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
        reference, actual = state(cpu), state(gpu)
        for key in reference:
            expected = reference[key].cpu()
            observed = actual[key].cpu()
            def message(text: str, label: str = f"{name}/{key}") -> str:
                return f"{label}: {text}"
            torch.testing.assert_close(
                observed, expected, rtol=1e-10 if expected.is_floating_point() else 0,
                atol=limits.get(key, 0), equal_nan=True, msg=message,
            )
        for simulation in (cpu, gpu):
            charge, potential = simulation.fields()
            diagnostics = simulation.diagnostics(charge, potential)
            scale = max(abs(cast(float, diagnostics["injected_charge_C"])), 1e-30)
            if abs(cast(float, diagnostics["charge_balance_C"])) > 1e-12 * scale:
                raise AssertionError(f"{name}: charge balance failed")
            if abs(cast(float, diagnostics["deposition_error_C"])) > 1e-12 * scale:
                raise AssertionError(f"{name}: deposition accounting failed")
        np.savez_compressed(
            out / f"{name}.npz", allow_pickle=False,
            **{f"cpu_{key}": value.cpu().numpy() for key, value in reference.items()},
            **{f"gpu_{key}": value.cpu().numpy() for key, value in actual.items()},
        )
        rows.append({"control": name, "steps": 128, "dt_s": h,
                     "cpu_s": cpu_s, "gpu_s": gpu_s, "passed": True})
    report = {
        "gpu": torch.cuda.get_device_name(device), "torch": torch.__version__,
        "precision": "float64", "relative_tolerance": 1e-10,
        "absolute_tolerances": limits, "controls": rows,
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
