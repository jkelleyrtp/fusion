#!/usr/bin/env python3
"""Plot the output of cusp_sim.py: field + trajectories, survival curves, escape channels,
and time-integrated (r,z) density, one row per sweep member, into <out>/report.png plus
per-member trajectory figures."""

import argparse
import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402


def load_members(out):
    members = []
    for path in sorted(glob.glob(os.path.join(out, "*", "summary.json"))):
        with open(path) as f:
            summary = json.load(f)
        data = np.load(os.path.join(os.path.dirname(path), "results.npz"))
        members.append((summary, data))
    members.sort(key=lambda m: (m[0]["energy_eV"], m[0].get("inject_r_m", 0), m[0].get("pitch_deg", [0])[0]))
    return members


def draw_field(ax, data, mirror=True):
    r, z = data["field_r"], data["field_z"]
    Br, Bz = data["field_Br"].astype(float), data["field_Bz"].astype(float)
    B = np.hypot(Br, Bz)
    if mirror:
        k = 1 if r[0] == 0 else 0
        rr = np.concatenate([-r[::-1][:-k or None], r])
        Bp = np.concatenate([B[:, ::-1][:, :-k or None], B], axis=1)
        Brp = np.concatenate([-Br[:, ::-1][:, :-k or None], Br], axis=1)
        Bzp = np.concatenate([Bz[:, ::-1][:, :-k or None], Bz], axis=1)
    else:
        rr, Bp, Brp, Bzp = r, B, Br, Bz
    ax.pcolormesh(z * 100, rr * 100, Bp.T, norm=LogNorm(vmin=max(B[B > 0].min(), 1e-4), vmax=B.max()), cmap="magma", shading="auto", rasterized=True)
    ax.streamplot(z * 100, rr * 100, Bzp.T, Brp.T, color="w", linewidth=0.4, density=1.2, arrowsize=0.5)


def rings(ax, summary):
    a, d = summary["ring_radius_m"] * 100, summary["ring_half_sep_m"] * 100
    for zc, c in ((-d, "cyan"), (d, "orange")):
        ax.plot([zc, zc], [a, a], "o", color=c, ms=6, mec="k")
        ax.plot([zc, zc], [-a, -a], "o", color=c, ms=6, mec="k")


def plot_trajectories(summary, data, path, n_show=40):
    traj = data["traj"]  # [T, S, 6]
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [1.6, 1]})
    ax = axes[0]
    draw_field(ax, data)
    rings(ax, summary)
    esc = data["esc_where"][: traj.shape[0]]
    colors = {0: "lime", 1: "deepskyblue", 2: "gold", 3: "red"}
    labels = {0: "confined", 1: "lost -z cusp", 2: "lost +z cusp", 3: "lost ring cusp"}
    shown = set()
    for i in range(min(n_show, traj.shape[0])):
        t = traj[i]
        ok = np.isfinite(t[:, 0])
        if ok.sum() < 2:
            continue
        rr = np.hypot(t[ok, 0], t[ok, 1]) * np.sign(t[ok, 0])
        ax.plot(t[ok, 2] * 100, rr * 100, color=colors[int(esc[i])], lw=0.5, alpha=0.7,
                label=labels[int(esc[i])] if esc[i] not in shown else None)
        shown.add(int(esc[i]))
    ax.set_xlabel("z [cm]")
    ax.set_ylabel("signed r [cm]  (x-projection)")
    ax.set_title(f"{summary['tag']}: |B| (log), field lines, {min(n_show, traj.shape[0])} tracked electrons")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_aspect("equal")

    ax = axes[1]
    for i in range(min(n_show, traj.shape[0])):
        t = traj[i]
        ok = np.isfinite(t[:, 0])
        ax.plot(t[ok, 0] * 100, t[ok, 1] * 100, color=colors[int(esc[i])], lw=0.4, alpha=0.6)
    a = summary["ring_radius_m"] * 100
    ax.add_patch(plt.Circle((0, 0), a, fill=False, color="w", ls="--"))
    ax.set_xlim(-a * 1.05, a * 1.05)
    ax.set_ylim(-a * 1.05, a * 1.05)
    ax.set_aspect("equal")
    ax.set_facecolor("k")
    ax.set_xlabel("x [cm]")
    ax.set_ylabel("y [cm]")
    ax.set_title("end-on view")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_trajectories_3d(summary, data, path, n_show=128):
    traj = data["traj"][:n_show]
    initial = traj[:, 0, :3]
    valid_initial = np.isfinite(initial).all(axis=1)
    a = summary["ring_radius_m"] * 100
    d = summary["ring_half_sep_m"] * 100
    source_z = initial[valid_initial, 2].mean() * 100 if valid_initial.any() else 0
    beam = summary.get("inject_mode") == "gun" or abs(source_z) > d
    flip = -1 if beam and source_z > 0 else 1
    rotation = np.array([1, flip, flip])
    positions = traj[:, :, :3] * rotation * 100
    colors = {0: "#79e8aa", 1: "#53c7ff", 2: "#ffd166", 3: "#f47783"}
    labels = {0: "surviving at end", 1: "lost −z", 2: "lost +z", 3: "lost radially"}
    background = "#101a2b"
    foreground = "#dce5f4"
    fig = plt.figure(figsize=(10, 10), facecolor=background)
    ax = fig.add_subplot(111, projection="3d", facecolor=background)
    ax.set_proj_type("ortho")
    ax.view_init(elev=np.degrees(np.arctan(1 / np.sqrt(2))), azim=-45)
    ax.set_box_aspect((1, 1, 1))
    theta = np.linspace(0, 2 * np.pi, 361)
    for zc, color, label in ((-d, "#53c7ff", "−z coil"), (d, "#ffd166", "+z coil")):
        ax.plot(a * np.cos(theta), flip * a * np.sin(theta),
                np.full(theta.shape, flip * zc), color=color, lw=2.4, label=label)
    shown = set()
    for points, code in zip(positions, data["esc_where"][:len(traj)]):
        code = int(code)
        ax.plot(points[:, 0], points[:, 1], points[:, 2], color=colors[code],
                lw=0.65, alpha=0.6, label=labels[code] if code not in shown else None)
        shown.add(code)
    if valid_initial.any():
        starts = positions[valid_initial, 0]
        ax.scatter(starts[:, 0], starts[:, 1], starts[:, 2], color="white",
                   s=8, alpha=0.8, label="launch positions", depthshade=False)
        source = starts.mean(axis=0)
        velocity = traj[valid_initial, 0, 3:].mean(axis=0) * rotation
        speed = np.linalg.norm(velocity)
        if beam and np.isfinite(speed) and speed > 0:
            arrow = velocity / speed * a * 0.4
            ax.quiver(*source, *arrow, color="white", linewidth=2, arrow_length_ratio=0.25)
            ax.text(*source, "  gun" if summary.get("inject_mode") == "gun" else "  source",
                    color="white", fontsize=10)
    finite = positions[np.isfinite(positions).all(axis=2)]
    extent = max(a, d, float(np.abs(finite).max()) if finite.size else 0) * 1.08
    ax.set(xlim=(-extent, extent), ylim=(-extent, extent), zlim=(-extent, extent),
           xlabel="x [cm]", ylabel=f"{'−' if flip < 0 else ''}y [cm]",
           zlabel=f"{'−' if flip < 0 else ''}z [cm]")
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_pane_color((0.08, 0.13, 0.21, 1))
        axis.label.set_color(foreground)
    ax.tick_params(colors=foreground, labelsize=8)
    ax.grid(False)
    ax.legend(loc="upper left", fontsize=8, facecolor=background, edgecolor="#35435a",
              labelcolor=foreground)
    fig.suptitle("Isometric trajectory overlay", color="white", fontsize=19, y=0.97)
    ax.set_title(f"{summary['tag']}\n{len(traj)} sampled electrons · colors show final exit status",
                 color=foreground, fontsize=10, pad=14)
    sample_dt = float(data["traj_dt"])
    fig.text(0.5, 0.035,
             f"Saved every {sample_dt * 1e9:g} ns · buffer spans {(traj.shape[1] - 1) * sample_dt * 1e6:g} µs"
             "\nOrthographic projection · equal spatial scales · sampled paths, not field lines"
             + ("\nView rotated 180° about x to put the gun below the coils" if flip < 0 else ""),
             ha="center", color=foreground, fontsize=9)
    fig.subplots_adjust(left=0.03, right=0.96, bottom=0.08, top=0.88)
    fig.savefig(path, dpi=150, facecolor=background)
    plt.close(fig)


def plot_report(members, path):
    n = len(members)
    fig, axes = plt.subplots(n, 3, figsize=(18, 4.2 * n), squeeze=False)
    for row, (s, d) in enumerate(members):
        # survival
        ax = axes[row, 0]
        t_us = d["survival_t"] * 1e6 if "survival_t" in d else d["survival_steps"] * s["dt_s"] * 1e6
        ax.plot(t_us, d["survival"] / s["particles"], lw=2)
        ax.set_yscale("log")
        ax.set_ylim(max(1e-4, 0.5 / s["particles"]), 1.1)
        ax.set_xlabel("t [us]")
        ax.set_ylabel("fraction still confined")
        ax.set_title(f"{s['tag']}: survival  ({100 * s['confined_fraction']:.1f}% at {s['sim_duration_s'] * 1e6:.1f} us)")
        ax.grid(alpha=0.3)
        # escape time histogram by channel
        ax = axes[row, 1]
        et, ew = d["esc_time"], d["esc_where"]
        bins = np.linspace(0, s["sim_duration_s"] * 1e6, 80)
        for code, c, lab in ((1, "deepskyblue", "-z point cusp"), (2, "gold", "+z point cusp"), (3, "red", "ring cusp / wall")):
            m = ew == code
            if m.any():
                ax.hist(et[m] * 1e6, bins=bins, color=c, alpha=0.7, label=f"{lab} ({m.sum()})")
        ax.set_xlabel("escape time [us]")
        ax.set_ylabel("electrons")
        ax.set_yscale("log")
        ax.set_title("loss channels")
        ax.legend(fontsize=8)
        # density
        ax = axes[row, 2]
        dens = d["density"].astype(float)
        rz, zz = d["density_r"], d["density_z"]
        # normalise by annulus volume so it's a density, not a count
        area = np.pi * (rz[1:] ** 2 - rz[:-1] ** 2)
        dens = dens / area[None, :]
        dens_m = np.concatenate([dens[:, ::-1], dens], axis=1)
        rr = np.concatenate([-rz[::-1][:-1], rz]) * 100
        ax.pcolormesh(zz * 100, rr, dens_m.T, norm=LogNorm(vmin=max(dens[dens > 0].min(), 1e-12), vmax=dens.max()), cmap="inferno", shading="auto", rasterized=True)
        rings(ax, s)
        ax.set_aspect("equal")
        ax.set_xlabel("z [cm]")
        ax.set_ylabel("r [cm]")
        ax.set_title("time-integrated electron density (log)")
    fig.suptitle(
        f"Biconic cusp electron trap - {members[0][0]['particles']:,} electrons per energy, "
        f"rings R={members[0][0]['ring_radius_m'] * 100:.0f} cm at z=+-{members[0][0]['ring_half_sep_m'] * 100:.0f} cm, "
        f"{members[0][0]['current_A']:.0f} A-turns, B_axis_max={members[0][0]['B_axis_max_T']:.3f} T, "
        + (f"space charge {members[0][0]['space_charge_C']:.1e} C ({members[0][0]['centre_potential_V']:.0f} V), " if members[0][0].get('space_charge_C') else "")
        + f"{members[0][0].get('integrator', 'rk4')}, "
        f"{members[0][0]['device_name']} x{n}",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    args, _ = p.parse_known_args()
    members = load_members(args.out)
    assert members, f"no summary.json under {args.out}"
    for s, d in members:
        plot_trajectories(s, d, os.path.join(args.out, f"traj_{s['tag']}.png"))
        plot_trajectories_3d(s, d, os.path.join(args.out, f"traj3d_{s['tag']}.png"))
    plot_report(members, os.path.join(args.out, "report.png"))
    print("| member | confined | lost -z | lost +z | lost ring | median t_esc | E drift | Gpart-steps/s | kernel |")
    print("|---|---|---|---|---|---|---|---|---|")
    for s, _ in members:
        med = s["median_escape_time_s"]
        print(f"| {s['tag']} | {100 * s['confined_fraction']:.2f}% | {s['escaped_minus_z_cusp']} | "
              f"{s['escaped_plus_z_cusp']} | {s['escaped_ring_cusp']} | {med * 1e6 if med else float('nan'):.3f} us | "
              f"{s['energy_drift_rel_max']:.1e} | {s['particle_steps_per_s'] / 1e9:.2f} | {s['kernel']} |")


if __name__ == "__main__":
    main()
