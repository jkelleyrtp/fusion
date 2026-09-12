"""Export central field slices and diagnostics from stationary Poisson archives."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from numpy.typing import NDArray

from cusp_sim import E_CHARGE, QM, TorchPusher, ring_field_on_grid
from electrostatic import ElectrostaticMesh

plt.switch_backend("Agg")


def planes(values: NDArray, axes: list[NDArray]) -> dict:
    ix, iy, iz = [len(axis) // 2 for axis in axes]
    return {
        "xz": {
            "u": axes[2].tolist(),
            "v": axes[0].tolist(),
            "uAxis": "z",
            "vAxis": "x",
            "fixedAxis": "y",
            "fixedM": float(axes[1][iy]),
            "values": values[:, iy, :].ravel().tolist(),
        },
        "yz": {
            "u": axes[2].tolist(),
            "v": axes[1].tolist(),
            "uAxis": "z",
            "vAxis": "y",
            "fixedAxis": "x",
            "fixedM": float(axes[0][ix]),
            "values": values[ix, :, :].ravel().tolist(),
        },
        "xy": {
            "u": axes[0].tolist(),
            "v": axes[1].tolist(),
            "uAxis": "x",
            "vAxis": "y",
            "fixedAxis": "z",
            "fixedM": float(axes[2][iz]),
            "values": values[:, :, iz].T.ravel().tolist(),
        },
    }


def build_field_data(case: Path, max_iteration: int | None = None) -> dict:
    config = json.loads((case / "config.json").read_text())
    history = json.loads((case / "history.json").read_text())
    saved = sorted(case.glob("viewer/iteration-*/state.npz"))
    if not saved:
        saved = [case / "state.npz"]
    snapshots = []
    magnetic = None
    shape = None
    axes = []
    for path in saved:
        iteration = (
            int(path.parent.name.split("-")[-1])
            if path.parent != case
            else len(history)
        )
        if max_iteration is not None and iteration > max_iteration:
            continue
        with np.load(path, allow_pickle=False) as state:
            potential = state["orbit_potential_V"]
            if shape is None:
                shape = potential.shape
                axes = [
                    np.linspace(lo, hi, n)
                    for lo, hi, n in zip(
                        state["lower_m"], state["upper_m"], shape, strict=True
                    )
                ]
                radius = config["radius"]
                r = torch.linspace(
                    0,
                    np.sqrt(2) * 0.6 * radius,
                    config["field_grid_rz"][0],
                    dtype=torch.float64,
                )
                z = torch.linspace(
                    -1.3 * radius,
                    1.3 * radius,
                    config["field_grid_rz"][1],
                    dtype=torch.float64,
                )
                br, bz = ring_field_on_grid(
                    r,
                    z,
                    radius,
                    [-0.5 * radius, 0.5 * radius],
                    [config["coil_current"], -config["coil_current"]],
                    720,
                    "cpu",
                )
                pusher = TorchPusher(
                    br, bz, 0, float(r[1]), float(z[0]), float(z[1] - z[0]), QM
                )
                points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(
                    -1, 3
                )
                magnetic = (
                    pusher.field(torch.from_numpy(points))
                    .norm(dim=1)
                    .numpy()
                    .reshape(shape)
                )
            if potential.shape != shape:
                raise ValueError("Field mesh changed between snapshots")
            if any(
                not np.allclose(np.linspace(lo, hi, n), axis, rtol=0, atol=1e-15)
                for lo, hi, n, axis in zip(
                    state["lower_m"], state["upper_m"], shape, axes, strict=True
                )
            ):
                raise ValueError("Field bounds changed between snapshots")
            spacing = np.array([axis[1] - axis[0] for axis in axes])
            volume = float(np.prod(spacing))
            fields = {
                "orbit": potential,
                "deposited": state["deposited_potential_V"],
                "relaxed": state["relaxed_potential_V"],
                "density": -state["deposited_charge_C"] / (E_CHARGE * volume),
                "relaxedDensity": -state["relaxed_charge_C"] / (E_CHARGE * volume),
                "electric": np.linalg.norm(
                    np.stack(np.gradient(potential, *spacing, edge_order=2)), axis=0
                ),
                "magnetic": magnetic,
            }
            slices = {}
            for name, values in fields.items():
                if not np.isfinite(values).all():
                    raise ValueError(f"Nonfinite {name} field in {path}")
                slices[name] = planes(values, axes)
            minimum = np.unravel_index(np.argmin(fields["deposited"]), shape)
            mesh = ElectrostaticMesh(
                torch.from_numpy(state["lower_m"]),
                torch.from_numpy(state["upper_m"]),
                shape,
            )
            centre = mesh.gather(
                torch.from_numpy(fields["deposited"]),
                torch.zeros((1, 3), dtype=torch.float64),
            )[0]
            snapshots.append(
                {
                    "iteration": iteration,
                    "fields": slices,
                    "minimumPositionM": [
                        float(axis[i]) for axis, i in zip(axes, minimum, strict=True)
                    ]
                    if np.ptp(fields["deposited"])
                    else None,
                    "depositedMinimumV": float(fields["deposited"].min()),
                    "depositedCentreV": float(centre[0]),
                    "chargeC": float(state["deposited_charge_C"].sum()),
                }
            )
    return {
        "version": 1,
        "case": case.name,
        "sourceRevision": config["source_revision"],
        "coreRadiusM": 0.3 * config["radius"],
        "sourcePositionM": config["source_position_m"],
        "requestedIterations": config["iterations"],
        "history": history[:max_iteration],
        "snapshots": snapshots,
        "notes": [
            "Stationary solver iterations, not physical time.",
            "Density uses every particle: nodal charge / (−e × cell volume).",
            "Orbit potential drives paths; deposited potential comes from charge.",
            "|E| is a nodal finite difference, not the particle gather.",
            "|B| reconstructs the imposed field table without plasma feedback.",
            "Central slices, not projections. Dashed circle: diagnostic core.",
        ],
    }


def plot_case(case: Path, output: Path) -> dict:
    data = build_field_data(case)
    output.mkdir(parents=True, exist_ok=True)
    (output / "fields.json").write_text(json.dumps(data, allow_nan=False))
    snapshot = data["snapshots"][-1]
    fig, axs = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    for ax, key, title, unit in zip(
        axs.flat,
        ["deposited", "density", "magnetic", "electric"],
        [
            "Deposited potential",
            "Deposited electron density",
            "Imposed magnetic magnitude",
            "Orbit electric magnitude",
        ],
        ["V", "m⁻³", "T", "V/m"],
        strict=True,
    ):
        plane = snapshot["fields"][key]["yz"]
        values = np.array(plane["values"]).reshape(len(plane["v"]), len(plane["u"]))
        image = ax.pcolormesh(
            plane["u"], plane["v"], values, shading="nearest", cmap="viridis"
        )
        ax.add_patch(
            plt.Circle(
                (0, 0), data["coreRadiusM"], fill=False, ls="--", color="white", lw=0.8
            )
        )
        ax.set(title=title, xlabel="z (m)", ylabel="y (m)", aspect="equal")
        fig.colorbar(image, ax=ax, label=unit, shrink=0.7)
    fig.suptitle(
        f"{case.name} · iteration {snapshot['iteration']} · x = 0 slice\n"
        "B null and negative potential well are different diagnostics"
    )
    fig.savefig(output / "fields.png", dpi=170)
    plt.close(fig)
    history = data["history"]
    iteration = [row["iteration"] + 1 for row in history]
    fig, axs = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True, sharex=True)
    for key, label in [
        ("core_centre_potential_V", "Deposited centre"),
        ("deposited_potential_min_V", "Deposited minimum"),
        ("relaxed_potential_min_V", "Relaxed minimum"),
        ("orbit_potential_min_V", "Orbit minimum"),
    ]:
        axs[0].plot(iteration, [row[key] for row in history], "o-", label=label)
    axs[0].set_ylabel("Potential (V)")
    for key, label in [
        ("mean_dwell_s", "Box dwell"),
        ("mean_core_dwell_s", "Core dwell"),
    ]:
        axs[1].plot(iteration, [row[key] * 1e9 for row in history], "o-", label=label)
    axs[1].set_ylabel("Mean residence (ns)")
    axs[2].plot(
        iteration,
        [row["fixed_point_relative_change"] for row in history],
        "o-",
        label="Fixed-point mismatch",
    )
    axs[2].set(xlabel="Solver iteration (not physical time)", ylabel="Relative change")
    for ax in axs:
        ax.legend()
        ax.grid(alpha=0.2)
    fig.suptitle(case.name)
    fig.savefig(output / "evolution.png", dpi=170)
    plt.close(fig)
    saved = sorted(case.glob("viewer/iteration-*/results.npz"))
    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    for index, color in zip(
        sorted({0, len(saved) // 2, len(saved) - 1}) if saved else [],
        ["#2879b9", "#dc872b", "#36a16c"],
    ):
        with np.load(saved[index], allow_pickle=False) as archive:
            trajectories = archive["traj"]
        iteration_id = int(saved[index].parent.name.split("-")[-1])
        label = f"Iteration {iteration_id} · {len(trajectories)} paths"
        for i, track in enumerate(trajectories):
            ax.plot(
                track[:, 2],
                track[:, 1],
                color=color,
                alpha=0.22,
                lw=0.6,
                label=label if i == 0 else None,
            )
    plane = snapshot["fields"]["orbit"]["yz"]
    ax.set(
        xlim=(plane["u"][0], plane["u"][-1]),
        ylim=(plane["v"][0], plane["v"][-1]),
        xlabel="z (m)",
        ylabel="y (m)",
        aspect="equal",
        title=f"{case.name} · projected trajectories across frozen-field iterations",
    )
    ax.add_patch(
        plt.Circle(
            (0, 0), data["coreRadiusM"], fill=False, ls="--", color="black", lw=0.8
        )
    )
    ax.legend()
    fig.savefig(output / "trajectories.png", dpi=170)
    plt.close(fig)
    if saved:
        with np.load(saved[-1], allow_pickle=False) as archive:
            positions = archive["traj"][:, 0]
            codes = archive["esc_where"][: len(positions)]
        fig, ax = plt.subplots(figsize=(8, 7), constrained_layout=True)
        for code, label, color in zip(
            range(4),
            ["At window end", "−z entrance", "+z exit", "Transverse wall"],
            ["#9165b3", "#2589b0", "#28a87b", "#d57e35"],
            strict=True,
        ):
            mask = codes == code
            ax.scatter(
                positions[mask, 0] * 1000,
                positions[mask, 1] * 1000,
                c=color,
                s=35,
                label=f"{label} ({mask.sum()})",
            )
        source = data["sourcePositionM"]
        ax.axhline(source[1] * 1000, color="grey", ls="--", lw=0.8)
        ax.scatter(source[0] * 1000, source[1] * 1000, marker="+", c="black")
        ax.set(
            xlabel="Initial x (mm)",
            ylabel="Initial y (mm)",
            aspect="equal",
            title=f"{case.name} · {len(positions)} recorded launch positions\n"
            "Coloured by final loss; dashed line through nominal source y",
        )
        ax.legend()
        fig.savefig(output / "source-loss.png", dpi=170)
        plt.close(fig)
    fig, axs = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True, sharex=True)
    for step in data["snapshots"]:
        for ax, key in zip(axs, ["deposited", "density"], strict=True):
            plane = step["fields"][key]["yz"]
            values = np.array(plane["values"]).reshape(len(plane["v"]), len(plane["u"]))
            row = len(plane["v"]) // 2
            ax.plot(plane["u"], values[row], label=f"Iteration {step['iteration']}")
            ax.set_title(f"x = {plane['fixedM']:.3g}, y = {plane['v'][row]:.3g} m")
    axs[0].set_ylabel("Deposited potential (V)")
    axs[1].set(xlabel="z (m)", ylabel="Deposited density (m⁻³)")
    for ax in axs:
        ax.legend()
        ax.grid(alpha=0.2)
    fig.suptitle(f"{case.name} · {len(data['snapshots'])} retained field snapshot(s)")
    fig.savefig(output / "profiles.png", dpi=170)
    plt.close(fig)
    return {key: value for key, value in snapshot.items() if key != "fields"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases = (
        [args.directory]
        if (args.directory / "config.json").exists()
        else sorted(path.parent for path in args.directory.glob("*/config.json"))
    )
    if not cases:
        raise ValueError("No Poisson case archives found")
    summaries = {case.name: plot_case(case, args.out / case.name) for case in cases}
    (args.out / "summary.json").write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
