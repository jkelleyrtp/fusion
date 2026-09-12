#!/usr/bin/env python3
"""Kinetic (non-self-consistent) simulation of electrons in a biconic cusp trap.

Two coaxial current rings of radius `a` at z = +-d carry opposite currents, giving a
spindle/biconic cusp: point cusps on the axis beyond each ring and a ring (line) cusp at
the midplane. Electrons are injected along the axis through one point cusp and pushed
with RK4 in the static field  m dv/dt = q v x B.

The field is axisymmetric, so B(r,z) is tabulated once on a (r,z) grid via Biot-Savart
over a polygonal approximation of each ring, and the pusher does bilinear lookups.

Each GPU runs one member of a parameter sweep (injection energy); a fused CUDA kernel
advances every electron for a block of steps in registers. A pure-torch pusher is used
when the kernel cannot be compiled (or on CPU for smoke tests).

Output per sweep member (`<out>/<tag>/results.npz`):
  esc_time[N]       time of escape (s), NaN if still confined at the end
  esc_where[N]      0 = confined, 1 = -z point cusp, 2 = +z point cusp, 3 = ring cusp / wall
  traj[T, S, 6]     subsampled (x,y,z,vx,vy,vz) of T tracked electrons
  density[nz, nr]   time-integrated (r,z) occupancy histogram
  field_Br/Bz       the tabulated field, plus grid axes r, z
"""

import argparse
import json
import math
import os
import time

import numpy as np
import torch

E_CHARGE = 1.602176634e-19
M_E = 9.1093837015e-31
MU0 = 4e-7 * math.pi
QM = -E_CHARGE / M_E  # electron charge-to-mass ratio, C/kg
K_COULOMB = 8.9875517923e9


# --------------------------------------------------------------------------- field


def ellipke(m):
    """Complete elliptic integrals K(m), E(m) (parameter m = k^2, 0 <= m < 1) by the AGM
    iteration, double precision, elementwise on a tensor."""
    a = torch.ones_like(m)
    b = torch.sqrt(1 - m)
    c_sum = 0.5 * m.clone()  # sum of 2^(n-1) c_n^2 with c_0^2 = m
    p = 0.5
    for _ in range(12):
        c = 0.5 * (a - b)
        a, b = 0.5 * (a + b), torch.sqrt(a * b)
        p *= 2
        c_sum += p * c * c
    K = math.pi / (2 * a)
    E = K * (1 - c_sum)
    return K, E


def ring_field_on_grid(r, z, a, ring_z, currents, segments, device):
    """Br, Bz on the (r, z) grid from ideal circular filament loops, closed form
    (Smythe, Static and Dynamic Electricity, sec. 7.10) in complete elliptic integrals.

    r: [nr], z: [nz] -> Br, Bz: [nz, nr]. `segments` is unused (kept for CLI compatibility)."""
    R, Z = torch.meshgrid(r, z, indexing="xy")  # [nz, nr]
    br = torch.zeros_like(R)
    bz = torch.zeros_like(R)
    for zc, cur in zip(ring_z, currents):
        zz = Z - zc
        plus = (a + R) ** 2 + zz**2
        minus = ((a - R) ** 2 + zz**2).clamp_min(1e-18)
        m = 4 * a * R / plus
        K, E = ellipke(m)
        pref = MU0 * cur / (2 * math.pi) / torch.sqrt(plus)
        bz += pref * (K + (a * a - R * R - zz**2) / minus * E)
        # Br has a removable r->0 singularity; the r=0 column is exactly 0 by symmetry.
        br_loop = pref * zz / R.clamp_min(1e-300) * (-K + (a * a + R * R + zz**2) / minus * E)
        br += torch.where(R > 0, br_loop, torch.zeros_like(br_loop))
    return br, bz


def ring_field_on_grid_biot_savart(r, z, a, ring_z, currents, segments, device):
    """Polygonal-ring Biot-Savart reference for cross-checking ring_field_on_grid.

    r: [nr], z: [nz] -> Br, Bz: [nz, nr]. Field points sit at (x=r, y=0, z)."""
    R, Z = torch.meshgrid(r, z, indexing="xy")  # [nz, nr]
    px = R.reshape(-1)
    py = torch.zeros_like(px)
    pz = Z.reshape(-1)
    bx = torch.zeros_like(px)
    bz = torch.zeros_like(px)

    phi = torch.linspace(0, 2 * math.pi, segments + 1, device=device, dtype=torch.float64)
    for zc, cur in zip(ring_z, currents):
        # segment endpoints and midpoints
        sx, sy = a * torch.cos(phi), a * torch.sin(phi)
        dlx, dly = sx[1:] - sx[:-1], sy[1:] - sy[:-1]
        mx, my = 0.5 * (sx[1:] + sx[:-1]), 0.5 * (sy[1:] + sy[:-1])
        chunk = 32
        for s in range(0, segments, chunk):
            rx = px[:, None] - mx[None, s : s + chunk]
            ry = py[:, None] - my[None, s : s + chunk]
            rz = pz[:, None] - zc
            inv_r3 = (rx * rx + ry * ry + rz * rz).clamp_min(1e-12).pow(-1.5)
            # dl x r  (dl has no z component)
            cx = dly[None, s : s + chunk] * rz
            cz = dlx[None, s : s + chunk] * ry - dly[None, s : s + chunk] * rx
            bx += (MU0 * cur / (4 * math.pi)) * (cx * inv_r3).sum(1)
            bz += (MU0 * cur / (4 * math.pi)) * (cz * inv_r3).sum(1)
    return bx.reshape(len(z), len(r)), bz.reshape(len(z), len(r))


def on_axis_analytic(z, a, ring_z, currents):
    """Bz on the axis for exact circular loops, for validating the Biot-Savart table."""
    bz = torch.zeros_like(z)
    for zc, cur in zip(ring_z, currents):
        bz += MU0 * cur * a * a / (2 * (a * a + (z - zc) ** 2) ** 1.5)
    return bz


# --------------------------------------------------------------------------- CUDA kernel

CUDA_SRC = r"""
#include <torch/extension.h>
#include <cuda.h>
#include <cuda_runtime.h>

struct Grid {
    const double* br; const double* bz;
    int nr, nz; double r0, dr, z0, dz;
    double sc_kq, sc_r;  // space-charge sphere at the origin: k*Q [V m] and radius [m]
};

__device__ __forceinline__ void field_at(const Grid& g, double x, double y, double z,
                                         double& Bx, double& By, double& Bz) {
    double r = sqrt(x * x + y * y);
    double fr = (r - g.r0) / g.dr, fz = (z - g.z0) / g.dz;
    int ir = (int)floor(fr), iz = (int)floor(fz);
    ir = max(0, min(g.nr - 2, ir));
    iz = max(0, min(g.nz - 2, iz));
    double tr = fr - ir, tz = fz - iz;
    tr = fmin(fmax(tr, 0.0), 1.0); tz = fmin(fmax(tz, 0.0), 1.0);
    int i00 = iz * g.nr + ir, i01 = i00 + 1, i10 = i00 + g.nr, i11 = i10 + 1;
    double w00 = (1 - tr) * (1 - tz), w01 = tr * (1 - tz), w10 = (1 - tr) * tz, w11 = tr * tz;
    double Br = w00 * g.br[i00] + w01 * g.br[i01] + w10 * g.br[i10] + w11 * g.br[i11];
    Bz = w00 * g.bz[i00] + w01 * g.bz[i01] + w10 * g.bz[i10] + w11 * g.bz[i11];
    double inv_r = r > 1e-12 ? 1.0 / r : 0.0;
    Bx = Br * x * inv_r; By = Br * y * inv_r;
}

// uniformly charged sphere at the origin: E = kQ r / R^3 inside, kQ r^ / r^2 outside
__device__ __forceinline__ void efield_at(const Grid& g, double x, double y, double z,
                                          double& ex, double& ey, double& ez) {
    double rr2 = x * x + y * y + z * z, rr = sqrt(rr2);
    double e_over_r = rr < g.sc_r ? g.sc_kq / (g.sc_r * g.sc_r * g.sc_r) : g.sc_kq / (rr2 * rr);
    ex = e_over_r * x; ey = e_over_r * y; ez = e_over_r * z;
}

__device__ __forceinline__ void accel(const Grid& g, double qm, double x, double y, double z,
                                      double vx, double vy, double vz,
                                      double& ax, double& ay, double& az) {
    double Bx, By, Bz;
    field_at(g, x, y, z, Bx, By, Bz);
    double ex, ey, ez;
    efield_at(g, x, y, z, ex, ey, ez);
    ax = qm * (vy * Bz - vz * By + ex);
    ay = qm * (vz * Bx - vx * Bz + ey);
    az = qm * (vx * By - vy * Bx + ez);
}

__device__ __forceinline__ double local_dt(const Grid& g, double qm, double x, double y, double z,
                                           double dt_max, double dt_frac) {
    // adaptive: a fixed fraction of the local gyroperiod, capped at dt_max (dt_frac <= 0 -> fixed dt_max)
    if (dt_frac <= 0) return dt_max;
    double Bx, By, Bz;
    field_at(g, x, y, z, Bx, By, Bz);
    double B = sqrt(Bx * Bx + By * By + Bz * Bz);
    double dt = dt_frac * 6.283185307179586 / (fabs(qm) * fmax(B, 1e-30));
    return fmin(dt, dt_max);
}

// One step of either integrator. Boris: leapfrog with E half-kicks and exact rotation about B
// (energy- and mu-conserving; v is stored at the same time as x, i.e. v is synchronised each step).
__device__ __forceinline__ void step_particle(const Grid& g, double qm, int boris, double h,
                                              double& x, double& y, double& z,
                                              double& vx, double& vy, double& vz) {
    if (boris) {
        double Bx, By, Bz, ex, ey, ez;
        field_at(g, x, y, z, Bx, By, Bz);
        efield_at(g, x, y, z, ex, ey, ez);
        double hq = 0.5 * h * qm;
        // half electric kick
        vx += hq * ex; vy += hq * ey; vz += hq * ez;
        // rotation
        double tx = hq * Bx, ty = hq * By, tz = hq * Bz;
        double t2 = tx * tx + ty * ty + tz * tz;
        double sx = 2 * tx / (1 + t2), sy = 2 * ty / (1 + t2), sz = 2 * tz / (1 + t2);
        double ux = vx + (vy * tz - vz * ty), uy = vy + (vz * tx - vx * tz), uz = vz + (vx * ty - vy * tx);
        vx += uy * sz - uz * sy; vy += uz * sx - ux * sz; vz += ux * sy - uy * sx;
        vx += hq * ex; vy += hq * ey; vz += hq * ez;
        // drift with the full-step velocity (synchronised leapfrog: x_{n+1} = x_n + h v_{n+1/2}
        // approximated by the rotated velocity; second order for uniform B).
        x += h * vx; y += h * vy; z += h * vz;
    } else {
        double h2 = 0.5 * h, h6 = h / 6.0;
        double a1x, a1y, a1z, a2x, a2y, a2z, a3x, a3y, a3z, a4x, a4y, a4z;
        accel(g, qm, x, y, z, vx, vy, vz, a1x, a1y, a1z);
        double v2x = vx + h2 * a1x, v2y = vy + h2 * a1y, v2z = vz + h2 * a1z;
        accel(g, qm, x + h2 * vx, y + h2 * vy, z + h2 * vz, v2x, v2y, v2z, a2x, a2y, a2z);
        double v3x = vx + h2 * a2x, v3y = vy + h2 * a2y, v3z = vz + h2 * a2z;
        accel(g, qm, x + h2 * v2x, y + h2 * v2y, z + h2 * v2z, v3x, v3y, v3z, a3x, a3y, a3z);
        double v4x = vx + h * a3x, v4y = vy + h * a3y, v4z = vz + h * a3z;
        accel(g, qm, x + h * v3x, y + h * v3y, z + h * v3z, v4x, v4y, v4z, a4x, a4y, a4z);
        x += h6 * (vx + 2 * v2x + 2 * v3x + v4x);
        y += h6 * (vy + 2 * v2y + 2 * v3y + v4y);
        z += h6 * (vz + 2 * v2z + 2 * v3z + v4z);
        vx += h6 * (a1x + 2 * a2x + 2 * a3x + a4x);
        vy += h6 * (a1y + 2 * a2y + 2 * a3y + a4y);
        vz += h6 * (a1z + 2 * a2z + 2 * a3z + a4z);
    }
}

// Advance every live particle from its own time t[i] to t_end. Trajectory samples are taken
// whenever a particle crosses a multiple of traj_dt; the histogram whenever it crosses hist_dt.
__global__ void push_kernel(double* __restrict__ pos, double* __restrict__ vel,
                            double* __restrict__ t, int64_t* __restrict__ nstep,
                            int* __restrict__ alive, double* __restrict__ esc_time,
                            int* __restrict__ esc_where, double* __restrict__ min_b,
                            const double* __restrict__ br, const double* __restrict__ bz,
                            int nr, int nz, double r0, double dr, double z0, double dz,
                            double qm, int boris, double dt_max, double dt_frac, double t_end,
                            double z_min, double z_max, double r_max,
                            float* __restrict__ traj, int ntrack, double traj_dt, int nsub,
                            int* __restrict__ hist, double hist_dt, int hnr, int hnz,
                            double hz0, double hdz, double hr_max, double sc_kq, double sc_r, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n || !alive[i]) return;
    Grid g{br, bz, nr, nz, r0, dr, z0, dz, sc_kq, sc_r};
    double x = pos[3 * i], y = pos[3 * i + 1], z = pos[3 * i + 2];
    double vx = vel[3 * i], vy = vel[3 * i + 1], vz = vel[3 * i + 2];
    double ti = t[i], bmin = min_b[i];
    int64_t ns = nstep[i];
    int where = 0;
    int64_t next_traj = (int64_t)floor(ti / traj_dt) + 1, next_hist = (int64_t)floor(ti / hist_dt) + 1;
    while (ti < t_end) {
        double h = local_dt(g, qm, x, y, z, dt_max, dt_frac);
        if (ti + h > t_end) h = t_end - ti;
        step_particle(g, qm, boris, h, x, y, z, vx, vy, vz);
        ti += h; ++ns;
        if (i < ntrack && ti >= next_traj * traj_dt) {
            if (next_traj < nsub) {
                float* tp = traj + ((size_t)i * nsub + next_traj) * 6;
                tp[0] = x; tp[1] = y; tp[2] = z; tp[3] = vx; tp[4] = vy; tp[5] = vz;
            }
            ++next_traj;
        }
        if (ti >= next_hist * hist_dt) {
            double r = sqrt(x * x + y * y);
            int ir = (int)(r / hr_max * hnr), iz = (int)((z - hz0) / hdz);
            if (ir >= 0 && ir < hnr && iz >= 0 && iz < hnz) atomicAdd(hist + iz * hnr + ir, 1);
            double Bx, By, Bz;
            field_at(g, x, y, z, Bx, By, Bz);
            bmin = fmin(bmin, sqrt(Bx * Bx + By * By + Bz * Bz));
            ++next_hist;
        }
        if (z < z_min) { where = 1; }
        else if (z > z_max) { where = 2; }
        else if (x * x + y * y > r_max * r_max) { where = 3; }
        if (where) { alive[i] = 0; esc_time[i] = ti; esc_where[i] = where; break; }
    }
    pos[3 * i] = x; pos[3 * i + 1] = y; pos[3 * i + 2] = z;
    vel[3 * i] = vx; vel[3 * i + 1] = vy; vel[3 * i + 2] = vz;
    t[i] = ti; nstep[i] = ns; min_b[i] = bmin;
}

void push(torch::Tensor pos, torch::Tensor vel, torch::Tensor t, torch::Tensor nstep,
          torch::Tensor alive, torch::Tensor esc_time, torch::Tensor esc_where, torch::Tensor min_b,
          torch::Tensor br, torch::Tensor bz,
          double r0, double dr, double z0, double dz, double qm, int64_t boris,
          double dt_max, double dt_frac, double t_end, double z_min, double z_max, double r_max,
          torch::Tensor traj, double traj_dt, torch::Tensor hist, double hist_dt,
          double hz0, double hdz, double hr_max, double sc_kq, double sc_r) {
    int n = pos.size(0);
    int threads = 128, blocks = (n + threads - 1) / threads;
    push_kernel<<<blocks, threads>>>(
        pos.data_ptr<double>(), vel.data_ptr<double>(), t.data_ptr<double>(), nstep.data_ptr<int64_t>(),
        alive.data_ptr<int>(), esc_time.data_ptr<double>(), esc_where.data_ptr<int>(), min_b.data_ptr<double>(),
        br.data_ptr<double>(), bz.data_ptr<double>(), br.size(1), br.size(0), r0, dr, z0, dz,
        qm, (int)boris, dt_max, dt_frac, t_end, z_min, z_max, r_max,
        traj.data_ptr<float>(), traj.size(0), traj_dt, traj.size(1),
        hist.data_ptr<int>(), hist_dt, hist.size(1), hist.size(0), hz0, hdz, hr_max, sc_kq, sc_r, n);
}
"""

CPP_SRC = """
void push(torch::Tensor pos, torch::Tensor vel, torch::Tensor t, torch::Tensor nstep,
          torch::Tensor alive, torch::Tensor esc_time, torch::Tensor esc_where, torch::Tensor min_b,
          torch::Tensor br, torch::Tensor bz,
          double r0, double dr, double z0, double dz, double qm, int64_t boris,
          double dt_max, double dt_frac, double t_end, double z_min, double z_max, double r_max,
          torch::Tensor traj, double traj_dt, torch::Tensor hist, double hist_dt,
          double hz0, double hdz, double hr_max, double sc_kq, double sc_r);
"""


def try_build_kernel(device_index):
    from torch.utils.cpp_extension import load_inline

    build_dir = os.path.join(os.environ.get("CUSP_BUILD_DIR", "/tmp/cusp_build"), f"gpu{device_index}")
    os.makedirs(build_dir, exist_ok=True)
    return load_inline(
        name=f"cusp_push_{device_index}",
        cpp_sources=CPP_SRC,
        cuda_sources=CUDA_SRC,
        functions=["push"],
        build_directory=build_dir,
        extra_cuda_cflags=["-O3", "--use_fast_math"],
        verbose=False,
    )


# --------------------------------------------------------------------------- torch pusher (fallback)


class TorchPusher:
    """Same algorithm as the CUDA kernel, vectorised with torch ops. Slower but portable.
    All live particles take one (individually sized) step per iteration until every one has
    reached t_end."""

    def __init__(self, br, bz, r0, dr, z0, dz, qm, sc_kq=0.0, sc_r=1.0, boris=True):
        self.br, self.bz = br, bz
        self.nz, self.nr = br.shape
        self.r0, self.dr, self.z0, self.dz, self.qm = r0, dr, z0, dz, qm
        self.sc_kq, self.sc_r, self.boris = sc_kq, sc_r, boris

    def field(self, p):
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        r = torch.sqrt(x * x + y * y)
        fr = (r - self.r0) / self.dr
        fz = (z - self.z0) / self.dz
        ir = fr.floor().long().clamp(0, self.nr - 2)
        iz = fz.floor().long().clamp(0, self.nz - 2)
        tr = (fr - ir).clamp(0, 1)
        tz = (fz - iz).clamp(0, 1)
        i00 = iz * self.nr + ir
        brf, bzf = self.br.reshape(-1), self.bz.reshape(-1)
        w00, w01, w10, w11 = (1 - tr) * (1 - tz), tr * (1 - tz), (1 - tr) * tz, tr * tz
        Br = w00 * brf[i00] + w01 * brf[i00 + 1] + w10 * brf[i00 + self.nr] + w11 * brf[i00 + self.nr + 1]
        Bz = w00 * bzf[i00] + w01 * bzf[i00 + 1] + w10 * bzf[i00 + self.nr] + w11 * bzf[i00 + self.nr + 1]
        inv_r = torch.where(r > 1e-12, 1.0 / r, torch.zeros_like(r))
        return torch.stack([Br * x * inv_r, Br * y * inv_r, Bz], 1)

    def efield(self, p):
        rr2 = (p * p).sum(1)
        rr = rr2.sqrt()
        e_over_r = torch.where(rr < self.sc_r, torch.full_like(rr, self.sc_kq / self.sc_r**3), self.sc_kq / (rr2 * rr))
        return e_over_r[:, None] * p

    def accel(self, p, v):
        return self.qm * (torch.cross(v, self.field(p), dim=1) + self.efield(p))

    def step(self, p, v, h):
        h = h[:, None]
        if self.boris:
            hq = 0.5 * h * self.qm
            e = self.efield(p)
            v = v + hq * e
            t = hq * self.field(p)
            s = 2 * t / (1 + (t * t).sum(1, keepdim=True))
            u = v + torch.cross(v, t, dim=1)
            v = v + torch.cross(u, s, dim=1) + hq * e
            return p + h * v, v
        h2 = 0.5 * h
        a1 = self.accel(p, v)
        v2 = v + h2 * a1
        a2 = self.accel(p + h2 * v, v2)
        v3 = v + h2 * a2
        a3 = self.accel(p + h2 * v2, v3)
        v4 = v + h * a3
        a4 = self.accel(p + h * v3, v4)
        return p + (h / 6) * (v + 2 * v2 + 2 * v3 + v4), v + (h / 6) * (a1 + 2 * a2 + 2 * a3 + a4)

    def push(self, pos, vel, t, nstep, alive, esc_time, esc_where, min_b, dt_max, dt_frac, t_end,
             z_min, z_max, r_max, traj, traj_dt, hist, hist_dt, hz0, hdz, hr_max):
        ntrack, nsub = traj.shape[0], traj.shape[1]
        hnz, hnr = hist.shape
        while True:
            idx = ((alive > 0) & (t < t_end)).nonzero().squeeze(1)
            if idx.numel() == 0:
                return
            p, v, ti = pos[idx], vel[idx], t[idx]
            if dt_frac > 0:
                B = self.field(p).norm(dim=1)
                h = (dt_frac * 2 * math.pi / (abs(self.qm) * B.clamp_min(1e-30))).clamp_max(dt_max)
            else:
                h = torch.full_like(ti, dt_max)
            h = torch.minimum(h, t_end - ti)
            k_traj0, k_hist0 = (ti / traj_dt).floor(), (ti / hist_dt).floor()
            p, v = self.step(p, v, h)
            ti = ti + h
            pos[idx], vel[idx], t[idx] = p, v, ti
            nstep[idx] += 1
            crossed = ((ti / traj_dt).floor() > k_traj0) & (idx < ntrack) & (k_traj0 + 1 < nsub)
            if crossed.any():
                k = (k_traj0[crossed] + 1).long()
                traj[idx[crossed], k, :3] = p[crossed].float()
                traj[idx[crossed], k, 3:] = v[crossed].float()
            hc = (ti / hist_dt).floor() > k_hist0
            if hc.any():
                ph = p[hc]
                r = torch.sqrt(ph[:, 0] ** 2 + ph[:, 1] ** 2)
                ir = (r / hr_max * hnr).long()
                iz = ((ph[:, 2] - hz0) / hdz).long()
                ok = (ir >= 0) & (ir < hnr) & (iz >= 0) & (iz < hnz)
                hist.view(-1).index_add_(0, (iz[ok] * hnr + ir[ok]), torch.ones(int(ok.sum()), dtype=hist.dtype, device=hist.device))
                min_b[idx[hc]] = torch.minimum(min_b[idx[hc]], self.field(ph).norm(dim=1))
            where = torch.zeros(idx.numel(), dtype=torch.int32, device=pos.device)
            where = torch.where(p[:, 2] < z_min, torch.ones_like(where), where)
            where = torch.where((where == 0) & (p[:, 2] > z_max), torch.full_like(where, 2), where)
            where = torch.where((where == 0) & (p[:, 0] ** 2 + p[:, 1] ** 2 > r_max**2), torch.full_like(where, 3), where)
            dead = where > 0
            if dead.any():
                d = idx[dead]
                alive[d] = 0
                esc_time[d] = ti[dead]
                esc_where[d] = where[dead]


# --------------------------------------------------------------------------- simulation


def run_member(args, member, tag, device, log):
    energy_ev, inject_r, pitch_lo_deg, pitch_hi_deg, space_charge = member
    torch.manual_seed(args.seed + int.from_bytes(tag.encode(), "little") % 100_000)
    dev = torch.device(device)
    f64 = dict(device=dev, dtype=torch.float64)
    t_start = time.time()

    a, d, current = args.ring_radius, args.ring_half_sep, args.current
    ring_z, currents = [-d, d], [current, -current]  # opposite polarity -> cusp

    # ---- field table
    z_lo, z_hi = -(d + args.axial_margin), d + args.axial_margin
    r = torch.linspace(0, a, args.grid_r, **f64)
    z = torch.linspace(z_lo, z_hi, args.grid_z, **f64)
    Br, Bz = ring_field_on_grid(r, z, a, ring_z, currents, args.segments, dev)
    axis_err = ((Bz[:, 0] - on_axis_analytic(z, a, ring_z, currents)).abs() / on_axis_analytic(z, a, ring_z, currents).abs().max()).max().item()
    Bmag = torch.sqrt(Br**2 + Bz**2)
    # Exclude a small annulus around the wire from the "max B" used to pick dt: electrons
    # reaching it are counted as lost at r_max anyway.
    r_max = args.wall_fraction * a
    b_for_dt = args.dt_ref_b if args.dt_ref_b else Bmag[:, r <= r_max].max().item()
    dt = args.steps_per_gyro_inv * (2 * math.pi / (abs(QM) * b_for_dt))  # fraction of the shortest gyroperiod
    # adaptive: dt_i = dt_frac * local gyroperiod, capped so a step never exceeds the grid cell /
    # a fraction of the transit time across the space-charge sphere
    v0 = math.sqrt(2 * energy_ev * E_CHARGE / M_E)
    v_cap = math.sqrt(v0 * v0 + 2 * abs(K_COULOMB * space_charge) / args.space_charge_radius * 1.5 * abs(QM))
    dt_max = min(a / (args.grid_r - 1), args.space_charge_radius / 10) / v_cap if args.adaptive else dt
    dt_max = max(dt_max, dt) if args.adaptive else dt
    dt_frac = args.steps_per_gyro_inv if args.adaptive else 0.0
    boris = args.integrator == "boris"
    log(f"[{tag}] field table {args.grid_z}x{args.grid_r}, on-axis rel err {axis_err:.2e}, "
        f"B_axis_max={Bmag[:, 0].max().item():.4f} T, B_max(r<r_max)={b_for_dt:.4f} T, "
        f"integrator={args.integrator} dt_ref={dt:.3e} s" + (f" adaptive dt<= {dt_max:.3e} s" if args.adaptive else ""))

    # ---- particles: injected through the -z point cusp on a ring of radius inject_r
    # (gaussian-blurred by inject_sigma), pitch uniform in [pitch_lo, pitch_hi]
    n = args.particles
    pos = torch.zeros(n, 3, **f64)
    ang = torch.rand(n, **f64) * 2 * math.pi
    if args.inject_mode == "cusp":
        pos[:, 0] = inject_r * torch.cos(ang) + torch.randn(n, **f64) * args.inject_sigma
        pos[:, 1] = inject_r * torch.sin(ang) + torch.randn(n, **f64) * args.inject_sigma
        pos[:, 2] = -(d + args.inject_offset)
    else:  # "inside": born uniformly in a ball of radius inject_r about the field null; pitch relative to +z
        u = torch.rand(n, **f64) ** (1 / 3) * inject_r
        cth = 2 * torch.rand(n, **f64) - 1
        sth = torch.sqrt(1 - cth**2)
        pos[:, 0], pos[:, 1], pos[:, 2] = u * sth * torch.cos(ang), u * sth * torch.sin(ang), u * cth
    # pitch uniform in cos(pitch) over the band (isotropic if the band is 0..180)
    c_lo, c_hi = math.cos(math.radians(pitch_hi_deg)), math.cos(math.radians(pitch_lo_deg))
    pitch = torch.acos(c_lo + torch.rand(n, **f64) * (c_hi - c_lo))
    az = torch.rand(n, **f64) * 2 * math.pi
    vel = torch.stack([v0 * torch.sin(pitch) * torch.cos(az), v0 * torch.sin(pitch) * torch.sin(az), v0 * torch.cos(pitch)], 1)

    alive = torch.ones(n, dtype=torch.int32, device=dev)
    esc_time = torch.full((n,), float("nan"), **f64)
    esc_where = torch.zeros(n, dtype=torch.int32, device=dev)
    t_part = torch.zeros(n, **f64)
    nstep = torch.zeros(n, dtype=torch.int64, device=dev)
    min_b = torch.full((n,), float("inf"), **f64)

    # --steps counts reference (fixed-dt) steps: total simulated time = steps * dt_ref
    total_steps = args.steps
    t_total = args.sim_time if args.sim_time else total_steps * dt
    nsub = args.traj_samples
    traj_dt = args.traj_dt if args.traj_dt else t_total / nsub
    hist_dt = args.hist_every * dt
    traj = torch.full((args.tracked, nsub, 6), float("nan"), dtype=torch.float32, device=dev)
    traj[:, 0, :3] = pos[: args.tracked].float()
    traj[:, 0, 3:] = vel[: args.tracked].float()
    hist = torch.zeros(args.hist_z, args.hist_r, dtype=torch.int32, device=dev)
    hz0, hdz = z_lo, (z_hi - z_lo) / args.hist_z

    z_min, z_max = z_lo, z_hi
    r0, dr, z0, dz = 0.0, (a / (args.grid_r - 1)), z_lo, (z_hi - z_lo) / (args.grid_z - 1)
    Brc, Bzc = Br.contiguous(), Bz.contiguous()

    kernel = None
    if dev.type == "cuda" and not args.no_kernel:
        try:
            kernel = try_build_kernel(dev.index or 0)
            log(f"[{tag}] fused CUDA kernel compiled")
        except Exception as e:  # noqa: BLE001 - fall back to torch ops on any build failure
            log(f"[{tag}] CUDA kernel build failed ({type(e).__name__}: {str(e)[:300]}); using torch pusher")
    sc_kq = K_COULOMB * space_charge
    pusher = TorchPusher(Brc, Bzc, r0, dr, z0, dz, QM, sc_kq, args.space_charge_radius, boris)

    def potential_ev(p):  # electron potential energy in the sphere's field, eV
        rr = p.norm(dim=1)
        R = args.space_charge_radius
        phi = torch.where(rr < R, sc_kq * (3 * R * R - rr * rr) / (2 * R**3), sc_kq / rr)
        return -phi

    def push(t_end):
        if kernel is not None:
            kernel.push(pos, vel, t_part, nstep, alive, esc_time, esc_where, min_b, Brc, Bzc, r0, dr, z0, dz,
                        QM, int(boris), dt_max, dt_frac, t_end, z_min, z_max, r_max, traj, traj_dt,
                        hist, hist_dt, hz0, hdz, a, sc_kq, args.space_charge_radius)
        else:
            pusher.push(pos, vel, t_part, nstep, alive, esc_time, esc_where, min_b, dt_max, dt_frac, t_end,
                        z_min, z_max, r_max, traj, traj_dt, hist, hist_dt, hz0, hdz, a)

    # initial kinetic energy of tracked particles, for the drift diagnostic
    ke0 = 0.5 * M_E * (vel[: args.tracked] ** 2).sum(1) / E_CHARGE + potential_ev(pos[: args.tracked])

    survival_t, survival = [], []
    block_t = args.block_steps * dt
    nblocks = math.ceil(t_total / block_t)
    t0 = time.time()
    for b in range(nblocks):
        t_end = min((b + 1) * block_t, t_total)
        push(t_end)
        n_alive = int(alive.sum().item())
        survival_t.append(t_end)
        survival.append(n_alive)
        if b % max(1, nblocks // 20) == 0 or n_alive == 0 or b == nblocks - 1:
            el = time.time() - t0
            ps = nstep.sum().item()
            log(f"[{tag}] t={t_end * 1e6:.3f}/{t_total * 1e6:.3f} us "
                f"alive {n_alive}/{n} ({100 * n_alive / n:.1f}%) {el:.1f}s "
                f"{ps / max(el, 1e-9) / 1e9:.2f} Gpart-steps/s")
        if n_alive == 0:
            break
    if dev.type == "cuda":
        torch.cuda.synchronize(dev)
    sim_time = time.time() - t0
    total_particle_steps = int(nstep.sum().item())

    ke_end = 0.5 * M_E * (vel[: args.tracked] ** 2).sum(1) / E_CHARGE + potential_ev(pos[: args.tracked])
    esc = esc_where.cpu().numpy()
    et = esc_time.cpu().numpy()
    confined = int((esc == 0).sum())
    summary = {
        "tag": tag,
        "energy_eV": energy_ev,
        "inject_r_m": inject_r,
        "pitch_deg": [pitch_lo_deg, pitch_hi_deg],
        "particles": n,
        "integrator": args.integrator,
        "adaptive": bool(args.adaptive),
        "space_charge_C": space_charge,
        "space_charge_radius_m": args.space_charge_radius,
        "centre_potential_V": 1.5 * sc_kq / args.space_charge_radius,
        "steps": total_steps,
        "dt_s": dt,
        "dt_max_s": dt_max,
        "sim_duration_s": t_total,
        "sim_duration_run_s": survival_t[-1],
        "particle_steps_total": total_particle_steps,
        "mean_steps_per_particle": total_particle_steps / n,
        "min_B_seen_T_median": float(min_b[torch.isfinite(min_b)].median().item()) if torch.isfinite(min_b).any() else None,
        "confined_at_end": confined,
        "confined_fraction": confined / n,
        "escaped_minus_z_cusp": int((esc == 1).sum()),
        "escaped_plus_z_cusp": int((esc == 2).sum()),
        "escaped_ring_cusp": int((esc == 3).sum()),
        "mean_escape_time_s": float(np.nanmean(et)) if np.isfinite(et).any() else None,
        "median_escape_time_s": float(np.nanmedian(et)) if np.isfinite(et).any() else None,
        "energy_drift_rel_max": float(((ke_end - ke0).abs() / ke0.abs()).max().item()),
        "energy_drift_rel_mean": float(((ke_end - ke0).abs() / ke0.abs()).mean().item()),
        "field_on_axis_rel_err": axis_err,
        "B_axis_max_T": Bmag[:, 0].max().item(),
        "ring_radius_m": a,
        "ring_half_sep_m": d,
        "current_A": current,
        "kernel": "cuda" if kernel is not None else "torch",
        "device": str(dev),
        "device_name": torch.cuda.get_device_name(dev) if dev.type == "cuda" else "cpu",
        "wall_time_s": time.time() - t_start,
        "sim_wall_time_s": sim_time,
        "particle_steps_per_s": total_particle_steps / max(sim_time, 1e-9),
    }
    out_dir = os.path.join(args.out, tag)
    os.makedirs(out_dir, exist_ok=True)
    np.savez_compressed(
        os.path.join(out_dir, "results.npz"),
        esc_time=et.astype(np.float32),
        esc_where=esc.astype(np.int8),
        traj=traj.cpu().numpy(),
        traj_dt=np.float64(traj_dt),
        min_b=min_b.cpu().numpy().astype(np.float32),
        nstep=nstep.cpu().numpy(),
        density=hist.cpu().numpy(),
        density_r=np.linspace(0, a, args.hist_r + 1),
        density_z=np.linspace(z_lo, z_hi, args.hist_z + 1),
        field_Br=Br.cpu().numpy().astype(np.float32),
        field_Bz=Bz.cpu().numpy().astype(np.float32),
        field_r=r.cpu().numpy(),
        field_z=z.cpu().numpy(),
        survival_t=np.array(survival_t),
        survival=np.array(survival),
        final_pos=pos[: args.tracked].cpu().numpy().astype(np.float32),
    )
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    log(f"[{tag}] done: confined {confined}/{n} ({100 * confined / n:.2f}%), "
        f"ring-cusp {summary['escaped_ring_cusp']}, +z {summary['escaped_plus_z_cusp']}, -z {summary['escaped_minus_z_cusp']}, "
        f"energy drift max {summary['energy_drift_rel_max']:.2e}, {summary['particle_steps_per_s'] / 1e9:.2f} Gpart-steps/s, "
        f"{summary['wall_time_s']:.1f}s wall")
    return summary


def member_tag(m):
    e, ri, plo, phi, q = m
    return f"E{e:g}eV_r{ri * 1e3:g}mm_p{plo:g}-{phi:g}" + (f"_Q{q:g}C" if q else "")


def sweep_members(args):
    """Cartesian product of energies x inject radii x pitch bands, unless --members is given."""
    if args.members:
        return [tuple((list(map(float, m.split(","))) + [0.0])[:5]) for m in args.members]
    return [(e, ri, plo, phi, q) for e in args.energies for ri in args.inject_r for plo, phi in zip(args.pitch_lo_deg, args.pitch_hi_deg) for q in args.space_charge]


def _worker(rank, args, members, devices, log_path):
    member = members[rank]
    device = devices[rank]
    tag = member_tag(member)

    def log(msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(log_path, "a") as f:
            f.write(line + "\n")

    run_member(args, member, tag, device, log)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, help="output directory (one subdir per sweep member)")
    p.add_argument("--energies", type=float, nargs="+", default=[20, 100, 500, 2500], help="injection energies, eV (one per GPU)")
    p.add_argument("--particles", type=int, default=250_000)
    p.add_argument("--steps", type=int, default=400_000, help="reference steps; simulated time = steps * dt_ref (see --sim-time)")
    p.add_argument("--traj-dt", type=float, default=None, help="trajectory sample spacing (s); default sim_time/traj_samples. Set small for beam runs so short-lived electrons are drawn (buffer fills after traj_samples samples)")
    p.add_argument("--sim-time", type=float, default=None, help="simulated time (s); overrides --steps")
    p.add_argument("--integrator", choices=["boris", "rk4"], default="boris", help="boris: symplectic leapfrog (energy/mu conserving); rk4: classic 4th order")
    p.add_argument("--adaptive", type=int, default=1, help="1: per-particle dt = steps-per-gyro-inv * local gyroperiod (capped); 0: fixed dt from the max field")
    p.add_argument("--block-steps", type=int, default=2000, help="steps per kernel launch")
    p.add_argument("--steps-per-gyro-inv", type=float, default=1 / 40, help="dt as a fraction of the shortest gyroperiod")
    p.add_argument("--dt-ref-b", type=float, default=None, help="field (T) defining the gyroperiod used for dt; default is max |B| inside the wall (dominated by the near-wire region)")
    p.add_argument("--ring-radius", type=float, default=0.05, help="m")
    p.add_argument("--ring-half-sep", type=float, default=0.04, help="rings at z = +-this, m")
    p.add_argument("--current", type=float, default=4000.0, help="ring current (ampere-turns)")
    p.add_argument("--space-charge", type=float, nargs="+", default=[0.0], help="fixed charge (C) of a uniform sphere at the trap centre; negative = trapped electron cloud / virtual cathode (decelerates and repels incoming electrons); positive = attractive well for electrons. Sweepable.")
    p.add_argument("--space-charge-radius", type=float, default=0.02, help="m")
    p.add_argument("--wall-fraction", type=float, default=0.9, help="electrons beyond this fraction of the ring radius are lost")
    p.add_argument("--axial-margin", type=float, default=0.03, help="domain extends this far beyond the rings, m")
    p.add_argument("--inject-offset", type=float, default=0.02, help="injection plane this far outside the -z ring, m")
    p.add_argument("--inject-sigma", type=float, default=1e-3, help="transverse gaussian blur of injection, m")
    p.add_argument("--inject-mode", choices=["cusp", "inside"], default="cusp", help="cusp: beam through the -z point cusp; inside: born in a ball of radius inject_r at the center")
    p.add_argument("--inject-r", type=float, nargs="+", default=[0.0], help="injection ring radii (cusp) / birth ball radii (inside) to sweep, m")
    p.add_argument("--pitch-lo-deg", type=float, nargs="+", default=[0.0], help="pitch band lower edges to sweep (paired with --pitch-hi-deg)")
    p.add_argument("--pitch-hi-deg", type=float, nargs="+", default=[20.0])
    p.add_argument("--members", nargs="+", default=None, help="explicit sweep members 'E_eV,inject_r_m,pitch_lo,pitch_hi[,space_charge_C]' (overrides the product)")
    p.add_argument("--grid-r", type=int, default=512)
    p.add_argument("--grid-z", type=int, default=1024)
    p.add_argument("--segments", type=int, default=720, help="Biot-Savart segments per ring")
    p.add_argument("--tracked", type=int, default=256, help="electrons whose trajectories are stored")
    p.add_argument("--traj-samples", type=int, default=4000, help="stored samples per tracked trajectory")
    p.add_argument("--hist-r", type=int, default=200)
    p.add_argument("--hist-z", type=int, default=400)
    p.add_argument("--hist-every", type=int, default=50)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--no-kernel", action="store_true", help="force the torch pusher")
    p.add_argument("--device", default=None, help="run every sweep member on this device sequentially (e.g. cpu)")
    # The job broker parses these from the entrypoint and may append --training-clique-ids;
    # they are irrelevant to the simulation.
    args, unknown = p.parse_known_args(argv)
    if unknown:
        print(f"ignoring broker/orchestration flags: {unknown}", flush=True)
    return args


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    log_path = os.path.join(args.out, "sim.log")
    members = sweep_members(args)
    if args.device is not None or not torch.cuda.is_available():
        device = args.device or "cpu"
        for rank in range(len(members)):
            _worker(rank, args, members, [device] * len(members), log_path)
        return
    ngpu = torch.cuda.device_count()
    assert len(members) <= ngpu, f"{len(members)} sweep members but only {ngpu} GPUs"
    devices = [f"cuda:{i}" for i in range(len(members))]
    print(f"running {len(members)} sweep members on {devices}: {[member_tag(m) for m in members]}", flush=True)
    torch.multiprocessing.spawn(_worker, args=(args, members, devices, log_path), nprocs=len(members), join=True)
    with open(os.path.join(args.out, "DONE"), "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S"))


if __name__ == "__main__":
    main()
