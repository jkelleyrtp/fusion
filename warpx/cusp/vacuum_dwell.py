"""Dwell time of single electrons in the six-coil field with no space charge.

Electrons start on the sphere wall around the +x coil axis and are followed until they return to
the wall. This is a design aid for choosing gun positions; it has no self-fields, so it says nothing
about the well. One transit is the time to cross the sphere diameter at the launch speed.
"""
import argparse
import json

import numpy as np
from scipy.special import ellipe, ellipk

MU0, A, C = 4e-7 * np.pi, 0.01, 299792458.0
Q_OVER_M = -1.75882001076e11
REST_EV = 510998.95


def loop(u, rho, at, rc):
    rho = np.maximum(rho, 1e-9)
    alpha2 = rc**2 + rho**2 + u**2 - 2 * rc * rho
    beta = np.sqrt(rc**2 + rho**2 + u**2 + 2 * rc * rho)
    m = 1 - alpha2 / beta**2
    c = MU0 * at / (2 * np.pi)
    axial = c / (alpha2 * beta) * ((rc**2 - rho**2 - u**2) * ellipe(m) + alpha2 * ellipk(m))
    radial = c * u / (alpha2 * beta * rho) * ((rc**2 + rho**2 + u**2) * ellipe(m) - alpha2 * ellipk(m))
    return axial, radial


def field(p, at, dc=1.3 * A, rc=A):
    total = np.zeros_like(p)
    for axis in range(3):
        o = [i for i in range(3) if i != axis]
        for sign in (1, -1):
            rho = np.hypot(p[:, o[0]], p[:, o[1]])
            axial, radial = loop(p[:, axis] - sign * dc, rho, at, rc)
            total[:, axis] += -sign * axial
            for i in o:
                total[:, i] += -sign * radial * p[:, i] / np.maximum(rho, 1e-9)
    return total


def launch(n, r0, r1, rng):
    rho = np.sqrt(rng.uniform(r0**2, r1**2, n))
    phi = rng.uniform(0, 2 * np.pi, n)
    start = np.stack([np.sqrt(A**2 - rho**2), rho * np.cos(phi), rho * np.sin(phi)], axis=1)
    return start * (1 - 1e-4)


def run(at, r0, r1, energy, aim, spread, n, tmax, dt, seed, dc, rc):
    rng = np.random.default_rng(seed)
    pos = launch(n, r0, r1, rng)
    gamma = 1 + energy / REST_EV
    speed = C * np.sqrt(1 - 1 / gamma**2)
    inward = -pos / np.linalg.norm(pos, axis=1, keepdims=True)
    direction = inward.copy()
    b0 = field(pos, at, dc, rc)
    bnorm = np.linalg.norm(b0, axis=1, keepdims=True)
    if aim == "field" and at:
        direction = b0 / bnorm * np.sign((b0 * inward).sum(axis=1, keepdims=True))
    direction = direction + spread * rng.normal(size=pos.shape)
    direction /= np.linalg.norm(direction, axis=1, keepdims=True)
    angle = np.degrees(np.arccos(np.clip(np.abs((b0 * inward).sum(axis=1)) / np.maximum(bnorm[:, 0], 1e-30), 0, 1)))
    vel = direction * speed
    alive = np.arange(n)
    dwell = np.full(n, tmax)
    exit_cos = np.full(n, np.nan)
    k = Q_OVER_M / gamma * dt / 2
    for step in range(int(tmax / dt)):
        if not alive.size:
            break
        t = k * field(pos, at, dc, rc)
        s = 2 * t / (1 + (t * t).sum(axis=1, keepdims=True))
        vel = vel + np.cross(vel + np.cross(vel, t), s)
        pos = pos + vel * dt
        radius = np.linalg.norm(pos, axis=1)
        out = radius >= A
        if out.any():
            dwell[alive[out]] = (step + 1) * dt
            exit_cos[alive[out]] = np.abs(pos[out]).max(axis=1) / radius[out]
            pos, vel, alive = pos[~out], vel[~out], alive[~out]
    transit = 2 * A / speed
    left = ~np.isnan(exit_cos)
    return {
        "coil_at": at, "gun_r0_mm": r0 * 1e3, "gun_r1_mm": r1 * 1e3, "aim": aim, "spread": spread,
        "wall_B_T": round(float(bnorm.mean()), 4),
        "B_to_wall_normal_deg": round(float(angle.mean()), 1),
        "mean_dwell_transits": round(float(dwell.mean() / transit), 2),
        "median_dwell_transits": round(float(np.median(dwell) / transit), 2),
        "returned_within_0.2_transit": round(float((dwell < 0.2 * transit).mean()), 3),
        "over_10_transits": round(float((dwell > 10 * transit).mean()), 3),
        "still_inside_at_end": round(float(1 - left.mean()), 3),
        "exit_face": round(float((exit_cos[left] > 0.93).mean()), 3),
        "exit_corner": round(float((exit_cos[left] < 0.66).mean()), 3),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coil-at", type=float, nargs="+", default=[16000.0])
    parser.add_argument("--r0", type=float, nargs="+", default=[0.0], help="inner gun radius (mm), measured from the coil axis")
    parser.add_argument("--width", type=float, default=0.5, help="radial width of the gun annulus (mm)")
    parser.add_argument("--energy", type=float, default=1.0e4)
    parser.add_argument("--aim", choices=("normal", "field"), default="normal")
    parser.add_argument("--spread", type=float, default=0.0)
    parser.add_argument("--n", type=int, default=400)
    parser.add_argument("--tmax", type=float, default=2.0e-8)
    parser.add_argument("--dt", type=float, default=1.0e-12)
    parser.add_argument("--dc", type=float, default=1.3)
    parser.add_argument("--rc", type=float, default=1.0)
    args = parser.parse_args()
    for at in args.coil_at:
        for r0 in args.r0:
            print(json.dumps(run(at, r0 * 1e-3, (r0 + args.width) * 1e-3, args.energy, args.aim, args.spread,
                                 args.n, args.tmax, args.dt, 0, args.dc * A, args.rc * A)), flush=True)
