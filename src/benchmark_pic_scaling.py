"""Whole-step throughput versus live-particle count for both PIC backends.

Particles are born inside the box as a numerical load, not as confinement evidence.
"""

import argparse
import json
import math
import time

import torch

from cusp_sim import M_E
from run_transient_pic import create_simulation, validate
from run_transient_pic import parser as pic_parser


def load(simulation_args: argparse.Namespace, count: int) -> float:
    simulation, _ = create_simulation(simulation_args)
    device = simulation.mesh.lower.device
    generator = torch.Generator().manual_seed(simulation_args.seed + count)
    position = (torch.rand((count, 3), generator=generator, dtype=torch.float64) - 0.5) * 0.2
    speed = math.sqrt(2 * simulation_args.energy_ev * 1.602176634e-19 / M_E)
    direction = torch.randn((count, 3), generator=generator, dtype=torch.float64)
    velocity = direction / direction.norm(dim=1, keepdim=True) * speed
    weight = torch.full((count,), simulation_args.total_electrons / count, dtype=torch.float64)
    simulation.inject(position.to(device), velocity.to(device), weight.to(device))
    h = simulation_args.dt
    for _ in range(simulation_args.warm_steps):
        simulation.advance(h)
    torch.cuda.synchronize(device)
    start = time.perf_counter()
    for _ in range(simulation_args.timed_steps):
        simulation.advance(h)
    torch.cuda.synchronize(device)
    return (time.perf_counter() - start) / simulation_args.timed_steps


def main() -> None:
    arguments = pic_parser()
    arguments.add_argument("--counts", type=int, nargs="+", default=[65536, 1048576, 4194304, 16777216])
    arguments.add_argument("--warm-steps", type=int, default=20)
    arguments.add_argument("--timed-steps", type=int, default=100)
    arguments.add_argument("--total-electrons", type=float, default=1e9)
    arguments.set_defaults(
        nodes=33, dt=4e-12, duration=4e-12, coil_current=30000, radius=0.5,
        energy_ev=100, max_live_particles=16777216, device="cuda:0",
    )
    args = arguments.parse_args()
    validate(args)
    if torch.device(args.device).type != "cuda":
        raise ValueError("Scaling benchmark requires a CUDA device")
    rows = []
    for count in args.counts:
        if count > args.max_live_particles:
            raise ValueError("Particle count exceeds max-live-particles")
        seconds = {}
        for backend in ("reference", "cuda"):
            args.kernels = backend
            seconds[backend] = load(args, count)
        row = {
            "particles": count, "reference_seconds_per_step": seconds["reference"],
            "cuda_seconds_per_step": seconds["cuda"], "speedup": seconds["reference"] / seconds["cuda"],
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "gpu": torch.cuda.get_device_name(torch.device(args.device)), "torch": torch.__version__,
        "mesh": [args.nodes] * 3, "dt_s": args.dt, "energy_ev": args.energy_ev,
        "scope": "inside-born numerical load; throughput only, not physics", "rows": rows,
    }
    (args.out / "scaling.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
