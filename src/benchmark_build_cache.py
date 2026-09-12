#!/usr/bin/env python3
"""Measure extension startup in fresh worker processes and execute the CUDA pusher."""

import argparse
import hashlib
import json
import os
import platform
import time
from pathlib import Path

import torch
from torch.multiprocessing import spawn

import cusp_sim


def worker(rank: int, output: str) -> None:
    torch.cuda.set_device(rank)
    started = time.perf_counter()
    extension = cusp_sim.try_build_kernel(rank)
    setup_seconds = time.perf_counter() - started

    device = torch.device(f"cuda:{rank}")
    pos = torch.zeros((1, 3), dtype=torch.float64, device=device)
    vel = torch.tensor([[1.0, 0.0, 0.0]], dtype=torch.float64, device=device)
    physical_time = torch.zeros(1, dtype=torch.float64, device=device)
    steps = torch.zeros(1, dtype=torch.int64, device=device)
    alive = torch.ones(1, dtype=torch.int32, device=device)
    escape_time = torch.full((1,), float("nan"), dtype=torch.float64, device=device)
    escape_channel = torch.zeros(1, dtype=torch.int32, device=device)
    min_b = torch.full((1,), float("inf"), dtype=torch.float64, device=device)
    field = torch.zeros((2, 2), dtype=torch.float64, device=device)
    trajectory = torch.zeros((1, 2, 6), dtype=torch.float32, device=device)
    histogram = torch.zeros((2, 2), dtype=torch.int32, device=device)
    extension.push(
        pos, vel, physical_time, steps, alive, escape_time, escape_channel, min_b,
        field, field,
        0.0, 1.0, -1.0, 2.0, -1.0, 1,
        0.1, 0.0, 0.1, -1.0, 1.0, 1.0,
        trajectory, 0.1, histogram, 0.1, -1.0, 1.0, 1.0, 0.0, 1.0,
    )
    torch.cuda.synchronize(device)
    torch.testing.assert_close(
        pos, torch.tensor([[0.1, 0.0, 0.0]], dtype=torch.float64, device=device),
        rtol=0.0, atol=1e-14,
    )
    torch.testing.assert_close(
        physical_time, torch.tensor([0.1], dtype=torch.float64, device=device),
        rtol=0.0, atol=1e-14,
    )
    assert steps.item() == 1
    assert alive.item() == 1
    assert escape_channel.item() == 0
    assert torch.isnan(escape_time).all().item()
    assert extension.__file__ is not None
    library = Path(extension.__file__)
    result = {
        "rank": rank,
        "extension_setup_seconds": setup_seconds,
        "cuda_smoke_passed": True,
        "extension_name": extension.__name__,
        "library": str(library),
        "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "library_mtime_ns": library.stat().st_mtime_ns,
        "device": torch.cuda.get_device_name(rank),
        "capability": list(torch.cuda.get_device_capability(rank)),
        "python": platform.python_version(),
        "torch": str(torch.__version__),
        "cuda": torch.version.cuda,
        "cache_root": os.environ.get("CUSP_BUILD_DIR"),
        "architecture_request": os.environ.get("TORCH_CUDA_ARCH_LIST"),
    }
    Path(output, f"worker-{rank}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > torch.cuda.device_count():
        raise ValueError("workers must be between one and the visible CUDA device count")
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    spawn(worker, args=(str(output),), nprocs=args.workers, join=True)
    process_wall_seconds = time.perf_counter() - started
    results = [
        json.loads((output / f"worker-{rank}.json").read_text())
        for rank in range(args.workers)
    ]
    assert all(result["cuda_smoke_passed"] for result in results)
    summary = {
        "fresh_process_batch_wall_seconds": process_wall_seconds,
        "workers": results,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
