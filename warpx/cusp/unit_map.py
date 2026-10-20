"""Vacuum field, in (r, z), of the metal of a deck held at 1 V with the can around it at 0 V, written as an
openPMD file that WarpX adds, times the voltage, to the field on the particles (docs/rz-casing-voltage.md).

    python3 unit_map.py <deck> [my_constants.name=value ...]     writes unit.h5 and unit_potential.json here

The metal is the deck's own warpx.eb_implicit_function, evaluated here with the deck's constants and the
settings given, so the map and the run cannot disagree about where it is. WarpX's field solver treats every
cell the metal's surface cuts as metal, so the metal here is grown to the mesh nodes of those cells.
The potential is solved on the mesh nodes; the field is its difference along each mesh edge, which is where
WarpX keeps Er and Ez. The file has twice the mesh's resolution so that every edge midpoint is a sample: WarpX
then reads back exactly those differences, with no smoothing across the metal."""
import json
import math
import os
import re
import sys

import h5py
import numpy as np
from scipy.ndimage import binary_dilation
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

KNOWN = {"clight": 299792458.0, "m_u": 1.66053906660e-27, "m_e": 9.1093837015e-31, "q_e": 1.602176634e-19, "pi": math.pi,
         "floor": np.floor, "sqrt": np.sqrt, "abs": np.abs, "min": np.minimum, "max": np.maximum}


class Constants(dict):
    """The deck's my_constants, each worked out from its expression the first time it is asked for."""

    def __init__(self, deck_text: str, settings: list[str]):
        super().__init__()
        self.expressions = dict(re.findall(r"^my_constants\.(\w+)\s*=\s*([^#\n]+)", deck_text, re.MULTILINE))
        self.expressions.update(setting[len("my_constants."):].split("=", 1) for setting in settings if setting.startswith("my_constants."))

    def __missing__(self, name: str):
        if name in KNOWN:
            return KNOWN[name]
        self[name] = self.evaluate(self.expressions[name])
        return self[name]

    def evaluate(self, expression: str, **more):
        return eval(expression.strip().strip('"').replace("^", "**"), {"__builtins__": {}}, _Scope(self, more))


class _Scope(dict):
    def __init__(self, constants: Constants, more: dict):
        super().__init__(more)
        self.constants = constants

    def __missing__(self, name: str):
        return self.constants[name]


def metal_nodes(deck_text: str, c: Constants) -> np.ndarray:
    """Which mesh nodes (i, j), at r = i cell and z = j cell - zw, the run's field solver holds as metal."""
    nr = int(c["nr"])
    cell = c["rw"] / nr
    R, Z = np.meshgrid(np.arange(nr + 1) * cell, np.arange(2 * nr + 1) * cell - c["zw"], indexing="ij")
    function = re.search(r"^warpx\.eb_implicit_function\s*=\s*(.+)$", deck_text, re.MULTILINE).group(1)
    inside = c.evaluate(function, x=R, y=0.0, z=Z) > 0
    return binary_dilation(inside, structure=np.ones((3, 3), bool))


def potential(held: np.ndarray, d: float) -> np.ndarray:
    """The potential on the mesh nodes with the nodes in `held` at 1 and the can's (the outer and end ones) at 0."""
    nr, nz = held.shape[0] - 1, held.shape[1] - 1
    wall = (np.arange(nr + 1)[:, None] == nr) | (np.arange(nz + 1)[None, :] == 0) | (np.arange(nz + 1)[None, :] == nz)
    fixed = held | wall
    value = np.where(held, 1.0, 0.0)
    index = np.arange((nr + 1) * (nz + 1)).reshape(nr + 1, nz + 1)
    rows, cols, vals, rhs = [], [], [], np.zeros(index.size)
    I, J = np.nonzero(~fixed)
    here = index[I, J]
    diagonal = np.zeros(len(I))
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        # Area of the face between the node and this neighbour, per radian, over d.
        if di:
            weight = (I + 0.5 * di) * d
        else:
            weight = np.where(I > 0, I * d, d / 8)
        ok = (I + di >= 0)
        weight = np.where(ok, weight, 0.0)
        ni, nj = np.clip(I + di, 0, nr), J + dj
        there = index[ni, nj]
        isfixed = fixed[ni, nj]
        diagonal += weight
        free = ok & ~isfixed
        rows.append(here[free]); cols.append(there[free]); vals.append(-weight[free])
        np.add.at(rhs, here[ok & isfixed], (weight * value[ni, nj])[ok & isfixed])
    rows.append(here); cols.append(here); vals.append(diagonal)
    keep = np.full(index.size, -1); keep[here] = np.arange(len(here))
    A = coo_matrix((np.concatenate(vals), (keep[np.concatenate(rows)], keep[np.concatenate(cols)])), shape=(len(here),) * 2).tocsr()
    phi = value.copy()
    phi[I, J] = spsolve(A, rhs[here])
    return phi


def write(path, phi, d, zw):
    nr, nz = phi.shape[0] - 1, phi.shape[1] - 1
    fine = np.zeros((2, 2 * nr + 1, 2 * nz + 1))                        # Er, Ez on a mesh of spacing d/2
    edge_r = -(phi[1:] - phi[:-1]) / d                                  # at (i + 1/2, j)
    edge_z = -(phi[:, 1:] - phi[:, :-1]) / d                            # at (i, j + 1/2)
    fine[0, 1::2, ::2] = edge_r
    fine[1, ::2, 1::2] = edge_z
    # The other samples are never the nearest to an edge midpoint; fill them by averaging so the map is smooth to plot.
    fine[0, 2:-1:2, ::2] = 0.5 * (edge_r[1:] + edge_r[:-1]); fine[0, 0, ::2] = 0; fine[0, -1, ::2] = edge_r[-1]
    fine[0, :, 1::2] = 0.5 * (fine[0, :, :-1:2] + fine[0, :, 2::2])
    fine[1, ::2, 2:-1:2] = 0.5 * (edge_z[:, 1:] + edge_z[:, :-1]); fine[1, ::2, 0] = edge_z[:, 0]; fine[1, ::2, -1] = edge_z[:, -1]
    fine[1, 1::2, :] = 0.5 * (fine[1, :-1:2, :] + fine[1, 2::2, :])
    with h5py.File(path, "w") as f:
        f.attrs["openPMD"] = np.bytes_("1.1.0"); f.attrs["openPMDextension"] = np.uint32(0)
        f.attrs["basePath"] = np.bytes_("/data/%T/"); f.attrs["meshesPath"] = np.bytes_("fields/")
        f.attrs["iterationEncoding"] = np.bytes_("fileBased"); f.attrs["iterationFormat"] = np.bytes_("unit_%T.h5")
        f.attrs["software"] = np.bytes_("unit_map.py")
        it = f.create_group("data/0")
        it.attrs["time"] = 0.0; it.attrs["dt"] = 1.0; it.attrs["timeUnitSI"] = 1.0
        E = it.create_group("fields/E")
        E.attrs["geometry"] = np.bytes_("thetaMode"); E.attrs["geometryParameters"] = np.bytes_("m=0;imag=+")
        E.attrs["axisLabels"] = np.array([b"r", b"z"]); E.attrs["dataOrder"] = np.bytes_("C")
        E.attrs["gridSpacing"] = np.array([d / 2, d / 2]); E.attrs["gridGlobalOffset"] = np.array([0.0, -zw])
        E.attrs["gridUnitSI"] = 1.0; E.attrs["timeOffset"] = np.float32(0)
        E.attrs["unitDimension"] = np.array([1.0, 1.0, -3.0, -1.0, 0.0, 0.0, 0.0])
        E.attrs["fieldSmoothing"] = np.bytes_("none")
        for name, data in (("r", fine[0]), ("t", np.zeros_like(fine[0])), ("z", fine[1])):
            ds = E.create_dataset(name, data=data[None])
            ds.attrs["unitSI"] = 1.0; ds.attrs["position"] = np.array([0.0, 0.0])


def main(deck: str, settings: list[str]) -> None:
    text = open(deck).read()
    c = Constants(text, settings)
    nr = int(c["nr"])
    cell = c["rw"] / nr
    assert abs(c["zw"] / cell - 2 * nr * c["zw"] / c["rw"] / 2) < 1e-9 and c["zw"] == c["rw"], "the map is written for a can as long as it is wide"
    held = metal_nodes(text, c)
    # The metal reaches the can in the run. Here it stops short of it, so that the two can be at different voltages.
    held[np.arange(nr + 1) * cell > c["rw"] - c["gap"]] = False
    phi = potential(held, cell)
    write("unit.part.h5", phi, cell, c["zw"])
    os.replace("unit.part.h5", "unit.h5")                # a run stopped while this was being written starts it again
    at = lambda r, z: round(float(phi[int(round(r / cell)), int(round((z + c["zw"]) / cell))]), 4)
    with open("unit_potential.json", "w") as out:
        json.dump({"centre": at(0, 0), "on_axis_in_coil": at(0, c["dc"]), "in_gap_at_coil_radius": at(c["rc"], 0)}, out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
