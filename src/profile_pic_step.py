"""Stage-level wall-clock profile of one transient PIC step per backend."""

import argparse
import json
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import torch

from cusp_sim import E_CHARGE
from pic_kernels import ReferenceKernels
from run_transient_pic import (
    create_simulation,
    inject_packet,
    validate,
)
from run_transient_pic import (
    parser as pic_parser,
)
from transient_pic import MagneticField

STAGES = ("deposit", "poisson", "gather", "magnetic", "boris", "drift")


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


class TimedKernels(ReferenceKernels):
    def __init__(self, inner: ReferenceKernels, totals: dict[str, float],
                 device: torch.device) -> None:
        self.mesh = inner.mesh
        self._inner = inner
        self._totals = totals
        self._device = device

    def _time(self, name: str, call: Callable[..., object], *args: object) -> object:
        synchronize(self._device)
        start = time.perf_counter()
        result = call(*args)
        synchronize(self._device)
        self._totals[name] += time.perf_counter() - start
        return result

    def deposit(self, position: torch.Tensor, charge: torch.Tensor) -> torch.Tensor:
        return cast(torch.Tensor, self._time("deposit", self._inner.deposit, position, charge))

    def potential(self, charge: torch.Tensor) -> torch.Tensor:
        return cast(torch.Tensor, self._time("poisson", self._inner.potential, charge))

    def gather(self, potential: torch.Tensor, position: torch.Tensor) -> torch.Tensor:
        return cast(torch.Tensor, self._time("gather", self._inner.gather, potential, position))

    def drift(self, position: torch.Tensor, velocity: torch.Tensor, h: float,
              core_radius: float) -> tuple[
                  torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        return cast(
            tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor],
            self._time("drift", self._inner.drift, position, velocity, h, core_radius),
        )

    def boris(self, velocity: torch.Tensor, electric: torch.Tensor, magnetic: torch.Tensor,
              h: float) -> torch.Tensor:
        return cast(
            torch.Tensor,
            self._time("boris", self._inner.boris, velocity, electric, magnetic, h),
        )


def timed_callable(name: str, call: Callable[..., torch.Tensor], totals: dict[str, float],
                   device: torch.device) -> Callable[..., torch.Tensor]:
    def wrapped(*args: object) -> torch.Tensor:
        synchronize(device)
        start = time.perf_counter()
        result = call(*args)
        synchronize(device)
        totals[name] += time.perf_counter() - start
        return result
    return wrapped


def microbenchmark(call: Callable[[], object], device: torch.device,
                   repeats: int = 20) -> list[float]:
    values = []
    for _ in range(repeats):
        synchronize(device)
        start = time.perf_counter()
        call()
        synchronize(device)
        values.append(time.perf_counter() - start)
    return values


def profile_backend(args: argparse.Namespace) -> dict[str, object]:
    simulation, _ = create_simulation(args)
    device = simulation.mesh.lower.device
    h = args.dt
    for step in range(args.warm_steps):
        inject_packet(simulation, args, step)
        simulation.advance(h)
        simulation.time = (step + 1) * args.dt

    totals = {stage: 0.0 for stage in (*STAGES, "step_total")}
    inner_kernels = simulation.kernels
    inner_magnetic = simulation.magnetic_field
    simulation.kernels = TimedKernels(inner_kernels, totals, device)
    simulation.magnetic_field = cast(
        MagneticField,
        timed_callable("magnetic", inner_magnetic, totals, device),
    )

    live_start = len(simulation.particles.ids)
    for step in range(args.warm_steps, args.warm_steps + args.timed_steps):
        start = time.perf_counter()
        inject_packet(simulation, args, step)
        simulation.advance(h)
        synchronize(device)
        totals["step_total"] += time.perf_counter() - start
        simulation.time = (step + 1) * args.dt
    live_end = len(simulation.particles.ids)

    simulation.kernels = inner_kernels
    simulation.magnetic_field = inner_magnetic

    first = args.warm_steps + args.timed_steps
    synchronize(device)
    start = time.perf_counter()
    for step in range(first, first + args.timed_steps):
        inject_packet(simulation, args, step)
        simulation.advance(h)
        simulation.time = (step + 1) * args.dt
    synchronize(device)
    plain_seconds_per_step = (time.perf_counter() - start) / args.timed_steps

    split = {"inject": 0.0, "advance": 0.0}
    first += args.timed_steps
    for step in range(first, first + args.timed_steps):
        start = time.perf_counter()
        inject_packet(simulation, args, step)
        synchronize(device)
        middle = time.perf_counter()
        simulation.advance(h)
        synchronize(device)
        split["inject"] += middle - start
        split["advance"] += time.perf_counter() - middle
        simulation.time = (step + 1) * args.dt

    p = simulation.particles
    charge = inner_kernels.deposit(p.position, -E_CHARGE * p.weight)
    potential = inner_kernels.potential(charge)
    electric = inner_kernels.gather(potential, p.position)
    magnetic = inner_magnetic(p.position)
    benchmarks = {
        "deposit": microbenchmark(
            lambda: inner_kernels.deposit(p.position, -E_CHARGE * p.weight), device),
        "poisson": microbenchmark(lambda: inner_kernels.potential(charge), device),
        "magnetic": microbenchmark(lambda: inner_magnetic(p.position), device),
        "gather": microbenchmark(
            lambda: inner_kernels.gather(potential, p.position), device),
        "boris": microbenchmark(
            lambda: inner_kernels.boris(p.velocity, electric, magnetic, h), device),
        "drift": microbenchmark(
            lambda: inner_kernels.drift(p.position, p.velocity, h, simulation.core_radius),
            device),
    }

    profile_dir = args.out
    activities = [torch.profiler.ProfilerActivity.CPU]
    if device.type == "cuda":
        activities.append(torch.profiler.ProfilerActivity.CUDA)
    with torch.profiler.profile(activities=activities) as profiler:
        for _ in range(20):
            simulation.advance(h)
            synchronize(device)
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / f"profile-{args.kernels}.txt").write_text(
        profiler.key_averages().table(sort_by="cuda_time_total", row_limit=40) + "\n",
    )
    profiler.export_chrome_trace(str(profile_dir / f"profile-{args.kernels}-trace.json"))

    stage_total = sum(totals[stage] for stage in STAGES)
    totals["host_other"] = totals["step_total"] - stage_total
    return {
        "gpu": (
            torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu"
        ),
        "torch": torch.__version__,
        "live_particles_start": live_start,
        "live_particles_end": live_end,
        "seconds_per_step": totals["step_total"] / args.timed_steps,
        "plain_seconds_per_step": plain_seconds_per_step,
        "split_seconds_per_step": {name: value / args.timed_steps for name, value in split.items()},
        "stage_totals_s": {stage: totals[stage] for stage in STAGES},
        "stage_fraction_of_step": {
            stage: totals[stage] / totals["step_total"] for stage in STAGES
        },
        "host_other_fraction_of_step": totals["host_other"] / totals["step_total"],
        "microbenchmarks_s": {
            name: {"median": statistics.median(values), "repeats": values}
            for name, values in benchmarks.items()
        },
    }


def main() -> None:
    arguments = pic_parser()
    arguments.add_argument("--warm-steps", type=int, default=7000)
    arguments.add_argument("--timed-steps", type=int, default=500)
    arguments.set_defaults(
        kernels="both", nodes=33, current_a=1, dt=4e-12, duration=4e-8,
        inject_per_step=8, inject_every=1, coil_current=30000, radius=0.5,
        energy_ev=5000, temperature_ev=0.2, source_sigma=5e-5,
        divergence_deg=10, aim_deg=30, seed=1234, max_live_particles=150000,
        track=64, max_steps=20000, device="cuda:0", save_every=625,
    )
    # The kernels choice widens to include "both"; per-run parsing maps it back.
    for action in arguments._actions:
        if action.dest == "kernels":
            action.choices = ("reference", "cuda", "both")
    args = arguments.parse_args()
    validate(args)
    out_root = Path(args.out)
    backends = ("reference", "cuda") if args.kernels == "both" else (args.kernels,)
    results: dict[str, dict[str, object]] = {}
    for backend in backends:
        args.kernels = backend
        args.out = out_root / backend
        results[backend] = profile_backend(args)
        (args.out / "timings.json").write_text(
            json.dumps(results[backend], indent=2, allow_nan=False) + "\n",
        )
    if len(backends) == 2:
        reference, cuda = results["reference"], results["cuda"]
        summary = {
            "reference_seconds_per_step": reference["seconds_per_step"],
            "cuda_seconds_per_step": cuda["seconds_per_step"],
            "reference_plain_seconds_per_step": reference["plain_seconds_per_step"],
            "cuda_plain_seconds_per_step": cuda["plain_seconds_per_step"],
            "cuda_reference_step_ratio": (
                cast(float, cuda["seconds_per_step"])
                / cast(float, reference["seconds_per_step"])
            ),
            "stage_cuda_reference_ratio": {
                stage: (
                    cast(dict[str, float], cuda["stage_totals_s"])[stage]
                    / cast(dict[str, float], reference["stage_totals_s"])[stage]
                )
                for stage in STAGES
            },
        }
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / "summary.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n",
        )
    print(json.dumps({
        backend: result["seconds_per_step"]
        for backend, result in results.items()
    }), flush=True)


if __name__ == "__main__":
    main()
