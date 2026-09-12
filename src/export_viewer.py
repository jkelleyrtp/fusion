"""Export saved particle outputs into independently fetchable browser chunks."""

import argparse
import gzip
import hashlib
import json
import shutil
import struct
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


def write_blob(root: Path, payload: bytes, suffix: str) -> dict[str, str | int]:
    compressed = gzip.compress(payload, compresslevel=6, mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    filename = f"{digest}.{suffix}.cspz"
    (root / filename).write_bytes(compressed)
    return {"path": filename, "bytes": len(compressed), "sha256": digest}


def residence_statistics(
    escape_s: NDArray[np.floating], exits: NDArray[np.integer], window_s: float
) -> dict:
    if (not np.isfinite(window_s) or window_s <= 0 or exits.ndim != 1 or
            escape_s.ndim != 1 or len(exits) == 0 or len(escape_s) != len(exits)):
        raise ValueError("Invalid observation window or particle arrays")
    if not np.isin(exits, [0, 1, 2, 3]).all():
        raise ValueError("Unknown loss channel")
    escaped = escape_s[exits != 0].astype(np.float64)
    if not np.isfinite(escaped).all() or np.any(escaped < 0):
        raise ValueError("Escaped particles need finite nonnegative escape times")
    clipped = np.minimum(escaped, window_s)
    censored = int(np.count_nonzero(exits == 0))
    mean_s = (clipped.sum(dtype=np.float64) + censored * window_s) / len(exits)
    grid = np.unique(np.r_[0, np.geomspace(window_s / 10000, window_s, 100),
                           np.quantile(clipped, np.linspace(0, 1, 51)) if len(clipped) else []])
    counts = len(exits) - np.searchsorted(np.sort(clipped), grid, side="right")
    return {
        "meanDwellUs": float(mean_s * 1e6),
        "dwellLowerBound": censored > 0,
        "survival": {"tUs": (grid * 1e6).tolist(), "counts": counts.tolist()},
        "lossCounts": [int(np.count_nonzero(exits == code)) for code in range(4)],
    }


def encode_trajectories(
    trajectory: NDArray[np.floating], first: int, stride: int
) -> bytes:
    if trajectory.ndim != 3 or trajectory.shape[1] == 0 or trajectory.shape[2] < 3 or stride < 1:
        raise ValueError("Expected particle × sample × state trajectory array")
    indices = np.unique(np.r_[np.arange(0, trajectory.shape[1], stride), trajectory.shape[1] - 1])
    xyz = np.asarray(trajectory[:, indices, :3], dtype="<f4", order="C")
    header = struct.pack("<4sIIIII", b"CSP1", len(xyz), len(indices), stride, first, 1)
    return header + indices.astype("<u4").tobytes() + xyz.tobytes()


def occupancy_map(data: np.lib.npyio.NpzFile, core_radius: float) -> dict | None:
    if "density" not in data:
        return None
    density = data["density"].astype(np.int64)
    z_edges, r_edges = data["density_z"], data["density_r"]
    if density.shape != (len(z_edges) - 1, len(r_edges) - 1) or np.any(density < 0):
        raise ValueError("Invalid occupancy histogram")
    z_mid, r_mid = (z_edges[1:] + z_edges[:-1]) / 2, (r_edges[1:] + r_edges[:-1]) / 2
    core = z_mid[:, None] ** 2 + r_mid[None, :] ** 2 <= core_radius ** 2
    total = int(density.sum())
    z_step = max(1, len(z_mid) // 100)
    r_step = max(1, len(r_mid) // 50)
    coarse = np.add.reduceat(np.add.reduceat(density, np.arange(0, len(z_mid), z_step), axis=0),
                            np.arange(0, len(r_mid), r_step), axis=1)
    return {
        "width": coarse.shape[1], "height": coarse.shape[0],
        "counts": coarse.ravel().tolist(), "rMaxM": float(r_edges[-1]),
        "zMinM": float(z_edges[0]), "zMaxM": float(z_edges[-1]),
        "coreSampleFraction": float(density[core].sum() / total) if total else None,
        "coreRadiusM": core_radius,
    }


def export_member(root: Path, study: str, kind: str, path: Path) -> dict:
    summary = json.loads(path.read_text())
    tag = str(summary["tag"])
    run_id = f"{study}-{hashlib.sha256(tag.encode()).hexdigest()[:12]}"
    card = {
        "id": run_id, "study": study, "kind": kind, "tag": tag,
        "energyEV": summary["energy_eV"], "radiusM": summary["ring_radius_m"],
        "chargeC": summary.get("space_charge_C", 0),
        "particles": summary["particles"], "windowUs": summary["sim_duration_s"] * 1e6,
        "survivors": summary["confined_at_end"], "meanDwellUs": None, "dwellLowerBound": None,
        "medianEscapeUs": None if summary.get("median_escape_time_s") is None else summary["median_escape_time_s"] * 1e6,
        "axisAngleDeg": summary.get("gun_axis_B_angle_deg"), "meta": None,
        "tracked": 0, "trajectoryWindowUs": 0,
    }
    archive = path.with_name("results.npz")
    if not archive.exists():
        return card
    with np.load(archive, allow_pickle=False) as data:
        exits, escape = data["esc_where"], data["esc_time"]
        if len(exits) != card["particles"]:
            raise ValueError(f"Particle count mismatch in {path}")
        stats = residence_statistics(escape, exits, summary["sim_duration_s"])
        if stats["lossCounts"][0] != card["survivors"]:
            raise ValueError(f"Survivor count mismatch in {path}")
        trajectory = data["traj"]
        count = min(len(trajectory), len(exits))
        trajectory = trajectory[:count]
        if not np.isfinite(trajectory[:, 0, :3]).all():
            raise ValueError(f"Invalid initial tracked positions in {path}")
        sample_s = float(data["traj_dt"])
        if not np.isfinite(sample_s) or sample_s <= 0:
            raise ValueError("Trajectory sample interval must be positive")
        card.update({
            "meanDwellUs": stats["meanDwellUs"], "dwellLowerBound": stats["dwellLowerBound"],
            "tracked": count, "trajectoryWindowUs": (trajectory.shape[1] - 1) * sample_s * 1e6,
        })
        levels = []
        for name, stride in [("Preview", 24), ("Standard", 6), ("Full", 1)]:
            chunks = []
            for first in range(0, count, 16):
                part = trajectory[first:first + 16]
                payload = encode_trajectories(part, first, stride)
                chunks.append({**write_blob(root, payload, "bin"), "first": first, "count": len(part)})
            levels.append({"name": name, "stride": stride, "chunks": chunks})
        meta = {
            "version": 1, "summary": summary, **stats,
            "occupancy": occupancy_map(data, summary.get("space_charge_radius_m", summary["ring_radius_m"] * 0.3)),
            "trajectory": {
                "count": count, "samples": trajectory.shape[1], "sampleNs": sample_s * 1e9,
                "windowUs": card["trajectoryWindowUs"], "levels": levels,
                "exits": exits[:count].tolist(),
                "escapeUs": [None if code == 0 else float(t) * 1e6
                             for t, code in zip(escape[:count], exits[:count], strict=True)],
            },
        }
        card["meta"] = write_blob(root, json.dumps(meta, separators=(",", ":"), allow_nan=False).encode(), "json")
    return card


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--study", nargs=4, action="append", required=True,
                        metavar=("ID", "LABEL", "KIND", "DIRECTORY"))
    parser.add_argument("--bundle-out", type=Path)
    parser.add_argument("--bundle-study", action="append", default=[])
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    studies: list[dict[str, str]] = []
    runs: list[dict] = []
    for study, label, kind, directory in args.study:
        if kind not in ("external", "control", "historical") or any(s["id"] == study for s in studies):
            raise ValueError("Study IDs must be unique; kind is external, control, or historical")
        paths = sorted(Path(directory).glob("*/summary.json"))
        if not paths:
            raise ValueError(f"No member summaries in {directory}")
        studies.append({"id": study, "label": label, "kind": kind})
        for path in paths:
            runs.append(export_member(args.out, study, kind, path))
    catalog = {"version": 1, "studies": studies, "runs": runs}
    (args.out / "catalog.json").write_text(json.dumps(catalog, separators=(",", ":"), allow_nan=False) + "\n")
    if args.bundle_out:
        bundle_runs = [run for run in runs if run["study"] in args.bundle_study]
        if not bundle_runs:
            raise ValueError("No studies selected for bundled sample data")
        args.bundle_out.mkdir(parents=True, exist_ok=True)
        for run in bundle_runs:
            if run["meta"] is None:
                continue
            meta_path = args.out / run["meta"]["path"]
            shutil.copyfile(meta_path, args.bundle_out / meta_path.name)
            metadata = json.loads(gzip.decompress(meta_path.read_bytes()))
            for level in metadata["trajectory"]["levels"]:
                for chunk in level["chunks"]:
                    shutil.copyfile(args.out / chunk["path"], args.bundle_out / chunk["path"])
        bundle = {"version": 1, "studies": [s for s in studies if s["id"] in args.bundle_study], "runs": bundle_runs}
        (args.bundle_out / "catalog.json").write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False) + "\n")
    print(f"Exported {len(runs)} members; {sum(r['tracked'] > 0 for r in runs)} have paged trajectories.")


if __name__ == "__main__":
    main()
