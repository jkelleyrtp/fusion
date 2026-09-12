"""Measure Boris operation-order differences without changing production operators."""

import argparse
import ctypes
import ctypes.util
import json
from pathlib import Path

import torch

from cusp_sim import QM
from electrostatic import ElectrostaticMesh
from pic_cuda import CUDAKernels
from pic_kernels import ReferenceKernels


def difference(expected: torch.Tensor, actual: torch.Tensor) -> dict[str, int | float]:
    assert expected.shape == actual.shape
    assert torch.isfinite(expected).all() and torch.isfinite(actual).all()
    return {
        "components": expected.numel(),
        "unequal": int((expected != actual).sum()),
        "max_abs": float((expected - actual).abs().max()),
    }


def expanded_cross(left: torch.Tensor, right: torch.Tensor) -> torch.Tensor:
    return torch.stack([
        left[:, 1] * right[:, 2] - left[:, 2] * right[:, 1],
        left[:, 2] * right[:, 0] - left[:, 0] * right[:, 2],
        left[:, 0] * right[:, 1] - left[:, 1] * right[:, 0],
    ], dim=1)


def fused_cross(left: torch.Tensor, right: torch.Tensor, second: bool) -> torch.Tensor:
    library = ctypes.util.find_library("m")
    if library is None:
        raise RuntimeError("The diagnostic needs libm's correctly rounded FP64 fma")
    fma = ctypes.CDLL(library).fma
    fma.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
    fma.restype = ctypes.c_double
    rows = []
    for a, b in zip(left.cpu().tolist(), right.cpu().tolist(), strict=True):
        row = []
        for j, k in ((1, 2), (2, 0), (0, 1)):
            value = -fma(a[k], b[j], -a[j] * b[k]) if second else fma(a[j], b[k], -a[k] * b[j])
            row.append(value)
        rows.append(row)
    return left.new_tensor(rows)


def grouped_boris(
    velocity: torch.Tensor, electric: torch.Tensor, magnetic: torch.Tensor,
    h: float, expand_cross: bool, expand_sum: bool,
) -> torch.Tensor:
    minus = velocity + 0.5 * h * QM * electric
    t = 0.5 * h * QM * magnetic
    square = t.square()
    norm = (
        ((square[:, 0] + square[:, 1]) + square[:, 2])[:, None]
        if expand_sum else square.sum(dim=1, keepdim=True)
    )
    s = 2 * t / (1 + norm)
    cross = expanded_cross if expand_cross else torch.linalg.cross
    prime = minus + cross(minus, t)
    return minus + cross(prime, s) + 0.5 * h * QM * electric


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-boris-bitwise", action="store_true")
    args = parser.parse_args()
    device = torch.device(args.device)
    lower = torch.full((3,), -1.0, dtype=torch.float64, device=device)
    mesh = ElectrostaticMesh(lower, -lower, (17, 17, 17))
    reference, actual = ReferenceKernels(mesh), CUDAKernels(mesh)
    generator = torch.Generator().manual_seed(271828)
    velocity = torch.randn((32768, 3), generator=generator, dtype=torch.float64).to(device) * 4e7
    electric = torch.randn((32768, 3), generator=generator, dtype=torch.float64).to(device) * 1e4
    magnetic = torch.randn((32768, 3), generator=generator, dtype=torch.float64).to(device) * 0.1
    h = 4e-12
    factor = 0.5 * h * QM
    minus, t = velocity + factor * electric, factor * magnetic
    native_cross = torch.linalg.cross(minus, t)
    square = t.square()
    result: dict[str, object] = {
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "device": torch.cuda.get_device_name(device),
        "scope": "Boris arithmetic diagnostic only; not a validation pass or physical study",
        "cross_expanded_vs_native": difference(native_cross, expanded_cross(minus, t)),
        "cross_fma_first_vs_native": difference(native_cross, fused_cross(minus, t, False)),
        "cross_fma_second_vs_native": difference(native_cross, fused_cross(minus, t, True)),
        "sum_left_associated_vs_native": difference(
            square.sum(dim=1), (square[:, 0] + square[:, 1]) + square[:, 2],
        ),
        "sum_021_vs_native": difference(
            square.sum(dim=1), (square[:, 0] + square[:, 2]) + square[:, 1],
        ),
        "sum_120_vs_native": difference(
            square.sum(dim=1), (square[:, 1] + square[:, 2]) + square[:, 0],
        ),
    }
    expected = reference.boris(velocity, electric, magnetic, h)
    observed = actual.boris(velocity, electric, magnetic, h)
    result["boris_native_vs_cuda"] = difference(expected, observed)
    for expand_cross in (False, True):
        for expand_sum in (False, True):
            grouped = grouped_boris(velocity, electric, magnetic, h, expand_cross, expand_sum)
            result[f"boris_cross_{expand_cross}_sum_{expand_sum}_vs_cuda"] = difference(
                grouped, observed,
            )
    args.out.mkdir(parents=True, exist_ok=False)
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    (args.out / "arithmetic.json").write_text(text)
    print(text, flush=True)
    if args.require_boris_bitwise:
        torch.testing.assert_close(observed, expected, rtol=0, atol=0)


if __name__ == "__main__":
    main()
