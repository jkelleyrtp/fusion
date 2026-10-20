"""Electron pressure against imposed magnetic pressure in radial shells of a six-coil PIC snapshot.

beta(r) = p_e(r) / (<B^2>(r) / 2 mu0), with p_e the shell-averaged scalar pressure (1/3) n m <v^2>
including beam flow. It estimates how far a run is from plasma pushing the imposed field outward;
it is not a self-consistent magnetic feedback calculation. The shell Debye length uses p_e / n_e as
the temperature, so beam flow overstates it.
"""

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import cast

import numpy as np
import torch

from cusp_sim import E_CHARGE, M_E, MU0
from electrostatic import EPSILON_0
from run_transient_pic import parser as pic_parser
from run_transient_pic import six_coil_table


def shell_beta(snapshot: Path, configuration: dict[str, object], shells: int, samples: int) -> dict[str, object]:
    with np.load(snapshot, allow_pickle=False) as values:
        prefix = "electron_" if "electron_position_m" in values.files else ""
        position, velocity = values[f"{prefix}position_m"], values[f"{prefix}velocity_m_s"]
        weight, lower, upper = values["electron_count"], values["lower_m"], values["upper_m"]
    coils = configuration["coils"]
    if not isinstance(coils, list) or len(coils) != 6:
        raise ValueError("Only six-coil runs are supported")
    argv = [item for key, value in configuration.items() if key in ("coil_offset", "radius", "coil_current",
            "box_half_width", "box_bottom", "box_top", "nodes", "casing_radius", "casing_voltage")
            for item in (f"--{key.replace('_', '-')}", str(value))]
    args = pic_parser().parse_args(["--out", "unused", "--device", "cpu", "--coils", "6", *argv])
    _, field, _ = six_coil_table(args, torch.device("cpu"), torch.tensor(lower), torch.tensor(upper))
    outer = args.coil_offset * args.radius
    edges = np.linspace(0.0, outer, shells + 1)
    radius = np.linalg.norm(position, axis=1)
    energy = weight * M_E * np.square(velocity).sum(axis=1)
    generator = np.random.default_rng(0)
    directions = generator.normal(size=(samples, 3))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    rows = []
    for inner, outer_edge in itertools.pairwise(edges):
        volume = 4 / 3 * math.pi * (outer_edge**3 - inner**3)
        inside = (radius >= inner) & (radius < outer_edge)
        middle = 0.5 * (inner + outer_edge)
        b2 = float(field(torch.tensor(middle * directions)).square().sum(dim=1).mean())
        pressure = float(energy[inside].sum()) / (3 * volume)
        density = float(weight[inside].sum()) / volume
        magnetic = b2 / (2 * MU0)
        rows.append({
            "r_inner_m": float(inner), "r_outer_m": float(outer_edge), "electron_density_m3": density,
            "electron_pressure_Pa": pressure, "rms_B_T": math.sqrt(b2), "magnetic_pressure_Pa": magnetic,
            "beta": pressure / magnetic if magnetic else None,
            "mean_energy_eV": float(energy[inside].sum() / weight[inside].sum()) / 2 / E_CHARGE
            if inside.any() else None,
            "debye_length_m": math.sqrt(EPSILON_0 * pressure) / (density * E_CHARGE) if density else None,
        })
    boundary = rows[-2]
    debye = [row["debye_length_m"] for row in rows if row["debye_length_m"] is not None]
    return {
        "snapshot": str(snapshot), "current_a": configuration["current_a"],
        "mesh_spacing_m": float(np.max((upper - lower) / (np.array(configuration["mesh_shape"]) - 1))),
        "min_shell_debye_length_m": min(debye) if debye else None,
        "coil_current_A_turn": configuration["coil_current"], "casing_voltage_V": configuration["casing_voltage"],
        "energy_ev": configuration["energy_ev"], "electrons": float(weight.sum()), "shells": rows,
        "max_beta_outside_null": max(row["beta"] for row in rows[shells // 4:] if row["beta"] is not None),
        "density_for_beta1_at_boundary_m3": boundary["magnetic_pressure_Pa"] * 3
        / (2 * boundary["mean_energy_eV"] * E_CHARGE) if boundary["mean_energy_eV"] else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--shells", type=int, default=12)
    parser.add_argument("--samples", type=int, default=4096)
    args = parser.parse_args()
    results = {}
    for case in args.cases:
        configuration = json.loads((case / "configuration.json").read_text())
        snapshot = max((case / "snapshots").glob("*.npz"))
        results[case.name] = shell_beta(snapshot, configuration, args.shells, args.samples)
        result = results[case.name]
        boundary = cast(list[dict[str, float]], result["shells"])[-2]
        print(f"{case.name:22s} n_boundary={boundary['electron_density_m3']:.2e} Brms={boundary['rms_B_T']:.3f} T "
              f"beta_boundary={boundary['beta']:.2e} max_beta={result['max_beta_outside_null']:.2e} "
              f"n_for_beta1={result['density_for_beta1_at_boundary_m3']:.2e} "
              f"debye_min={result['min_shell_debye_length_m']:.2e} m h={result['mesh_spacing_m']:.2e} m")
    args.out.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
