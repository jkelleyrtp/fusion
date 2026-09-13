"""FP64 CUDA particle operators for the shared transient PIC integrator."""

import math
from typing import Protocol, cast

import torch

from cuda_build_cache import load_cached_extension
from cusp_sim import QM, TorchPusher
from electrostatic import EPSILON_0, ElectrostaticMesh
from pic_kernels import ReferenceKernels

CPP_SRC = r"""
#include <torch/extension.h>
torch::Tensor deposit(torch::Tensor x, torch::Tensor q, torch::Tensor lower,
                      torch::Tensor h, int64_t nx, int64_t ny, int64_t nz);
torch::Tensor gather(torch::Tensor phi, torch::Tensor x, torch::Tensor lower, torch::Tensor h);
std::vector<torch::Tensor> drift(torch::Tensor x, torch::Tensor v, torch::Tensor lower,
                               torch::Tensor upper, double dt, double radius);
torch::Tensor boris(torch::Tensor v, torch::Tensor e, torch::Tensor b, double factor);
torch::Tensor axisymmetric(torch::Tensor x, torch::Tensor br, torch::Tensor bz,
                           double r0, double dr, double z0, double dz);
"""

CUDA_SRC = r"""
#include <torch/extension.h>
#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <cuda_runtime.h>
#include <math_constants.h>

__device__ double clamp01(double x) { return fmin(fmax(x, 0.0), 1.0); }

__device__ void stencil(const double* x, const double* lower, const double* h,
                        int nx, int ny, int nz, int* base, double* w) {
    int shape[3] = {nx, ny, nz};
    for (int k = 0; k < 3; ++k) {
        double scaled = (x[k] - lower[k]) / h[k];
        base[k] = min((int)floor(scaled), shape[k] - 2);
        w[k] = scaled - base[k];
    }
}

__global__ void deposit_kernel(const double* x, const double* q, const double* lower,
                               const double* h, int nx, int ny, int nz, int64_t count,
                               double* out) {
    int64_t p = (int64_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (p >= count) return;
    int base[3]; double w[3];
    stencil(x + 3*p, lower, h, nx, ny, nz, base, w);
    for (int i = 0; i < 2; ++i) for (int j = 0; j < 2; ++j) for (int k = 0; k < 2; ++k) {
        int64_t index = ((int64_t)(base[0]+i)*ny + base[1]+j)*nz + base[2]+k;
        double weight = ((i ? w[0] : 1-w[0]) * (j ? w[1] : 1-w[1])) * (k ? w[2] : 1-w[2]);
        atomicAdd(out + index, weight * q[p]);
    }
}

__global__ void gather_kernel(const double* phi, const double* x, const double* lower,
                              const double* h, int nx, int ny, int nz, int64_t count,
                              double* out) {
    int64_t p = (int64_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (p >= count) return;
    int base[3]; double w[3];
    stencil(x + 3*p, lower, h, nx, ny, nz, base, w);
    double gradient[3] = {0, 0, 0};
    for (int i = 0; i < 2; ++i) for (int j = 0; j < 2; ++j) for (int k = 0; k < 2; ++k) {
        int64_t index = ((int64_t)(base[0]+i)*ny + base[1]+j)*nz + base[2]+k;
        double value = phi[index], wx = i ? w[0] : 1-w[0];
        double wy = j ? w[1] : 1-w[1], wz = k ? w[2] : 1-w[2];
        gradient[0] += (value * (wy*wz)) * ((i ? 1.0 : -1.0) / h[0]);
        gradient[1] += (value * (wx*wz)) * ((j ? 1.0 : -1.0) / h[1]);
        gradient[2] += (value * (wx*wy)) * ((k ? 1.0 : -1.0) / h[2]);
    }
    for (int k = 0; k < 3; ++k) out[3*p+k] = -gradient[k];
}

__global__ void drift_kernel(const double* x, const double* v, const double* lower,
                             const double* upper, int64_t count, double dt, double radius,
                             double* end, double* fraction, bool* hit,
                             double* inside, bool* entered) {
    int64_t p = (int64_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (p >= count) return;
    double delta[3], clipped[3], f = 1;
    bool lost = false;
    for (int k = 0; k < 3; ++k) {
        double start = x[3*p+k], finish = start + dt*v[3*p+k];
        delta[k] = finish - start;
        double limit = delta[k] > 0 ? (upper[k]-start)/delta[k] :
                       delta[k] < 0 ? (lower[k]-start)/delta[k] : CUDART_INF;
        f = fmin(f, limit);
        lost |= finish <= lower[k] || finish >= upper[k];
    }
    f = clamp01(f);
    double a = 0, b = 0, c = 0;
    for (int k = 0; k < 3; ++k) {
        double start = x[3*p+k];
        double finish = fmin(fmax(start + f*delta[k], lower[k]), upper[k]);
        end[3*p+k] = finish;
        clipped[k] = finish - start;
        a += clipped[k]*clipped[k];
        b += start*clipped[k];
        c += start*start;
    }
    b = 2*b;
    c = c - radius*radius;
    double discriminant = b*b - (4*a)*c;
    double root = sqrt(fmax(discriminant, 0.0)), denominator = fmax(2*a, 1e-300);
    double lo = (-b-root)/denominator, hi = (-b+root)/denominator;
    inside[p] = a == 0 ? (c < 0 ? 1.0 : 0.0) : fmax(clamp01(hi)-clamp01(lo), 0.0);
    entered[p] = a > 0 && discriminant > 0 && lo > 0 && lo <= 1;
    fraction[p] = f;
    hit[p] = lost;
}

__device__ void cross3(const double* a, const double* b, double* c) {
    c[0] = __fma_rn(a[1], b[2], -(a[2]*b[1]));
    c[1] = __fma_rn(a[2], b[0], -(a[0]*b[2]));
    c[2] = __fma_rn(a[0], b[1], -(a[1]*b[0]));
}

__global__ void boris_kernel(const double* v, const double* e, const double* b,
                             int64_t count, double factor, double* out) {
    int64_t p = (int64_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (p >= count) return;
    double minus[3], t[3], s[3], prime[3], cross[3];
    for (int k = 0; k < 3; ++k) {
        minus[k] = v[3*p+k] + factor*e[3*p+k];
        t[k] = factor*b[3*p+k];
    }
    double norm = (t[0]*t[0] + t[2]*t[2]) + t[1]*t[1];
    for (int k = 0; k < 3; ++k) s[k] = (2*t[k])/(1+norm);
    cross3(minus, t, cross);
    for (int k = 0; k < 3; ++k) prime[k] = minus[k]+cross[k];
    cross3(prime, s, cross);
    for (int k = 0; k < 3; ++k) out[3*p+k] = (minus[k]+cross[k])+factor*e[3*p+k];
}

__device__ int64_t cell(double scaled, int64_t count) {
    int64_t index = (int64_t)floor(scaled);
    return index < 0 ? 0 : (index > count - 2 ? count - 2 : index);
}

__global__ void axisymmetric_kernel(const double* x, const double* br, const double* bz,
                                    int64_t nr, int64_t nz, double r0, double dr,
                                    double z0, double dz, int64_t count, double* out) {
    int64_t p = (int64_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (p >= count) return;
    double px = x[3*p], py = x[3*p+1], pz = x[3*p+2];
    double r = sqrt(px*px + py*py);
    double fr = (r - r0)/dr, fz = (pz - z0)/dz;
    int64_t ir = cell(fr, nr), iz = cell(fz, nz);
    double tr = clamp01(fr - (double)ir), tz = clamp01(fz - (double)iz);
    int64_t i00 = iz*nr + ir;
    double w00 = (1-tr)*(1-tz), w01 = tr*(1-tz), w10 = (1-tr)*tz, w11 = tr*tz;
    double radial = ((w00*br[i00] + w01*br[i00+1]) + w10*br[i00+nr]) + w11*br[i00+nr+1];
    double axial = ((w00*bz[i00] + w01*bz[i00+1]) + w10*bz[i00+nr]) + w11*bz[i00+nr+1];
    double inverse = r > 1e-12 ? 1.0/r : 0.0;
    out[3*p] = (radial*px)*inverse;
    out[3*p+1] = (radial*py)*inverse;
    out[3*p+2] = axial;
}

void check(torch::Tensor value, torch::Tensor like) {
    TORCH_CHECK(value.is_cuda() && value.is_contiguous() &&
                value.scalar_type() == torch::kFloat64 && value.device() == like.device(),
                "Expected contiguous FP64 tensors on one CUDA device");
}

torch::Tensor deposit(torch::Tensor x, torch::Tensor q, torch::Tensor lower,
                      torch::Tensor h, int64_t nx, int64_t ny, int64_t nz) {
    check(x, x); check(q, x); check(lower, x); check(h, x);
    TORCH_CHECK(x.dim() == 2 && x.size(1) == 3 && q.dim() == 1 && q.size(0) == x.size(0));
    TORCH_CHECK(lower.numel() == 3 && h.numel() == 3 && nx >= 3 && ny >= 3 && nz >= 3);
    c10::cuda::CUDAGuard guard(x.device());
    auto out = torch::zeros({nx, ny, nz}, x.options());
    if (x.size(0)) deposit_kernel<<<(x.size(0)+255)/256, 256, 0, at::cuda::getCurrentCUDAStream()>>>(
        x.data_ptr<double>(), q.data_ptr<double>(), lower.data_ptr<double>(), h.data_ptr<double>(),
        nx, ny, nz, x.size(0), out.data_ptr<double>());
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return out;
}

torch::Tensor gather(torch::Tensor phi, torch::Tensor x, torch::Tensor lower, torch::Tensor h) {
    check(phi, x); check(x, x); check(lower, x); check(h, x);
    TORCH_CHECK(phi.dim() == 3 && phi.size(0) >= 3 && phi.size(1) >= 3 && phi.size(2) >= 3);
    TORCH_CHECK(x.dim() == 2 && x.size(1) == 3 && lower.numel() == 3 && h.numel() == 3);
    c10::cuda::CUDAGuard guard(x.device());
    auto out = torch::empty_like(x);
    if (x.size(0)) gather_kernel<<<(x.size(0)+255)/256, 256, 0, at::cuda::getCurrentCUDAStream()>>>(
        phi.data_ptr<double>(), x.data_ptr<double>(), lower.data_ptr<double>(), h.data_ptr<double>(),
        phi.size(0), phi.size(1), phi.size(2), x.size(0), out.data_ptr<double>());
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return out;
}

std::vector<torch::Tensor> drift(torch::Tensor x, torch::Tensor v, torch::Tensor lower,
                               torch::Tensor upper, double dt, double radius) {
    check(x, x); check(v, x); check(lower, x); check(upper, x);
    TORCH_CHECK(x.dim() == 2 && x.size(1) == 3 && v.sizes() == x.sizes());
    TORCH_CHECK(lower.numel() == 3 && upper.numel() == 3);
    c10::cuda::CUDAGuard guard(x.device());
    auto end = torch::empty_like(x);
    auto fraction = torch::empty({x.size(0)}, x.options());
    auto inside = torch::empty_like(fraction);
    auto hit = torch::empty({x.size(0)}, x.options().dtype(torch::kBool));
    auto entered = torch::empty_like(hit);
    if (x.size(0)) drift_kernel<<<(x.size(0)+255)/256, 256, 0, at::cuda::getCurrentCUDAStream()>>>(
        x.data_ptr<double>(), v.data_ptr<double>(), lower.data_ptr<double>(), upper.data_ptr<double>(),
        x.size(0), dt, radius, end.data_ptr<double>(), fraction.data_ptr<double>(),
        hit.data_ptr<bool>(), inside.data_ptr<double>(), entered.data_ptr<bool>());
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return {end, fraction, hit, inside, entered};
}

torch::Tensor boris(torch::Tensor v, torch::Tensor e, torch::Tensor b, double factor) {
    check(v, v); check(e, v); check(b, v);
    TORCH_CHECK(v.dim() == 2 && v.size(1) == 3 && e.sizes() == v.sizes() && b.sizes() == v.sizes());
    c10::cuda::CUDAGuard guard(v.device());
    auto out = torch::empty_like(v);
    if (v.size(0)) boris_kernel<<<(v.size(0)+255)/256, 256, 0, at::cuda::getCurrentCUDAStream()>>>(
        v.data_ptr<double>(), e.data_ptr<double>(), b.data_ptr<double>(),
        v.size(0), factor, out.data_ptr<double>());
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return out;
}

torch::Tensor axisymmetric(torch::Tensor x, torch::Tensor br, torch::Tensor bz,
                           double r0, double dr, double z0, double dz) {
    check(x, x); check(br, x); check(bz, x);
    TORCH_CHECK(x.dim() == 2 && x.size(1) == 3 && br.dim() == 2 && bz.sizes() == br.sizes());
    TORCH_CHECK(br.size(0) >= 2 && br.size(1) >= 2);
    c10::cuda::CUDAGuard guard(x.device());
    auto out = torch::empty_like(x);
    if (x.size(0)) axisymmetric_kernel<<<(x.size(0)+255)/256, 256, 0, at::cuda::getCurrentCUDAStream()>>>(
        x.data_ptr<double>(), br.data_ptr<double>(), bz.data_ptr<double>(), br.size(1), br.size(0),
        r0, dr, z0, dz, x.size(0), out.data_ptr<double>());
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return out;
}
"""


class Extension(Protocol):
    def deposit(self, x: torch.Tensor, q: torch.Tensor, lower: torch.Tensor, h: torch.Tensor,
                nx: int, ny: int, nz: int) -> torch.Tensor: ...
    def gather(self, phi: torch.Tensor, x: torch.Tensor, lower: torch.Tensor,
               h: torch.Tensor) -> torch.Tensor: ...
    def drift(self, x: torch.Tensor, v: torch.Tensor, lower: torch.Tensor, upper: torch.Tensor,
              dt: float, radius: float) -> list[torch.Tensor]: ...
    def boris(self, v: torch.Tensor, e: torch.Tensor, b: torch.Tensor, factor: float) -> torch.Tensor: ...
    def axisymmetric(self, x: torch.Tensor, br: torch.Tensor, bz: torch.Tensor,
                     r0: float, dr: float, z0: float, dz: float) -> torch.Tensor: ...


_MODULE: Extension | None = None


def _sine_transform(count: int, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    k = torch.arange(1, count - 1, device=device, dtype=torch.float64)
    basis = torch.sin(math.pi * torch.outer(k, k) / (count - 1))
    return 2 * basis, basis / (count - 1)


def _apply_along_axes(values: torch.Tensor, matrices: list[torch.Tensor]) -> torch.Tensor:
    values = torch.einsum("ia,abc->ibc", matrices[0], values)
    values = torch.einsum("jb,ibc->ijc", matrices[1], values)
    return torch.einsum("kc,ijc->ijk", matrices[2], values)


class CUDAKernels(ReferenceKernels):
    def __init__(self, mesh: ElectrostaticMesh) -> None:
        super().__init__(mesh)
        if mesh.lower.device.type != "cuda":
            raise ValueError("CUDA particle operators require a CUDA mesh")
        global _MODULE
        if _MODULE is None:
            _MODULE = cast(Extension, load_cached_extension(
                CPP_SRC, CUDA_SRC, mesh.lower.device.index or 0, ["-O3", "--fmad=false"],
                functions=("deposit", "gather", "drift", "boris", "axisymmetric"),
            ))
        self.extension = _MODULE
        transforms = [_sine_transform(count, mesh.lower.device) for count in mesh.shape]
        self.forward_transforms = [forward for forward, _ in transforms]
        self.inverse_transforms = [inverse for _, inverse in transforms]

    def _tensor(self, value: torch.Tensor, shape: tuple[int, ...]) -> torch.Tensor:
        if (value.shape != shape or value.dtype != torch.float64
                or value.device != self.mesh.lower.device):
            raise ValueError("Particle operators require FP64 tensors on the mesh device")
        return value.contiguous()

    def _positions(self, position: torch.Tensor) -> torch.Tensor:
        position = self._tensor(position, (len(position), 3))
        self.mesh.check_positions(position)
        return position

    def deposit(self, position: torch.Tensor, charge: torch.Tensor) -> torch.Tensor:
        position = self._positions(position)
        charge = self._tensor(charge, (len(position),))
        return self.extension.deposit(
            position, charge, self.mesh.lower.contiguous(), self.mesh.h.contiguous(), *self.mesh.shape,
        )

    def potential(self, charge: torch.Tensor) -> torch.Tensor:
        charge = self._tensor(charge, self.mesh.shape)
        rhs = charge[1:-1, 1:-1, 1:-1] / (EPSILON_0 * self.mesh.volume)
        rhs = _apply_along_axes(rhs, self.forward_transforms) / self.mesh.eigenvalues
        potential = torch.zeros_like(charge)
        potential[1:-1, 1:-1, 1:-1] = _apply_along_axes(rhs, self.inverse_transforms)
        return potential

    def magnetic_field(self, pusher: TorchPusher) -> "CUDAAxisymmetricField":
        return CUDAAxisymmetricField(self, pusher)

    def gather(self, potential: torch.Tensor, position: torch.Tensor) -> torch.Tensor:
        position = self._positions(position)
        potential = self._tensor(potential, self.mesh.shape)
        return self.extension.gather(
            potential, position, self.mesh.lower.contiguous(), self.mesh.h.contiguous(),
        )

    def drift(
        self, position: torch.Tensor, velocity: torch.Tensor, h: float, core_radius: float,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        position = self._tensor(position, (len(position), 3))
        velocity = self._tensor(velocity, tuple(position.shape))
        end, fraction, hit, inside, entered = self.extension.drift(
            position, velocity, self.mesh.lower.contiguous(), self.mesh.upper.contiguous(), h, core_radius,
        )
        return end, fraction, hit, inside, entered

    def boris(
        self, velocity: torch.Tensor, electric: torch.Tensor, magnetic: torch.Tensor, h: float,
        qm: float = QM,
    ) -> torch.Tensor:
        shape = (len(velocity), 3)
        return self.extension.boris(
            self._tensor(velocity, shape), self._tensor(electric, shape),
            self._tensor(magnetic, shape), 0.5 * h * qm,
        )


class CUDAAxisymmetricField:
    def __init__(self, kernels: CUDAKernels, pusher: TorchPusher) -> None:
        self.kernels = kernels
        self.br = kernels._tensor(pusher.br, tuple(pusher.br.shape))
        self.bz = kernels._tensor(pusher.bz, tuple(pusher.br.shape))
        self.grid = (float(pusher.r0), float(pusher.dr), float(pusher.z0), float(pusher.dz))

    def __call__(self, position: torch.Tensor) -> torch.Tensor:
        position = self.kernels._tensor(position, (len(position), 3))
        return self.kernels.extension.axisymmetric(position, self.br, self.bz, *self.grid)
