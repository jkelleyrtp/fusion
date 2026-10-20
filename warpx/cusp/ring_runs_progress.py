"""Where the ring-voltage runs stand: plasma held in the vessel and inside the cage at set times, and ring voltages."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(next(Path("/public/jonathan/cusp/campaigns/rv2").glob("files-*"))))
from analyze_beta import constants, inside_cage
from analyze_ringv import ring_voltages


def near(series: np.ndarray, clock: np.ndarray, t: float) -> float:
    """Mean of a history within half a nanosecond of `t` (ns)."""
    return float(series[np.abs(clock * 1e9 - t) < 0.5].mean())


ROOT = Path("/public/jonathan/cusp/campaigns")
RUNS = [("rv1", "rv_78k_norings"), ("rv1", "rv_78k_stub"), ("rv1", "rv_78k_0kV"), ("rv1", "rv_78k_float"), ("rv2", "rv_78k_50kV"),
        ("rv2", "rv_78k_100kV"), ("rv2", "rv_78k_200kV"), ("rv2", "rv_78k_400kV"), ("rv1", "rv_78k_norings_seed2"),
        ("rv1", "rv_78k_stub_seed2"), ("rv1", "rv_78k_0kV_seed2"), ("rv1", "rv_78k_float_seed2")]
times = [float(t) for t in sys.argv[1:]] or [3, 6, 9, 12, 15, 18]
print(f"{'run':22s} {'done':9s} {'at ns':>6s} | " + " | ".join(f"{t:g} ns: e held, e in cage, i in cage (1e14), ring kV" for t in times))
for camp, name in RUNS:
    run = ROOT / camp / name
    if not (run / "diags/reducedfiles/number.txt").exists():
        continue
    number = np.loadtxt(run / "diags/reducedfiles/number.txt", skiprows=1, ndmin=2)
    c = constants(run)
    when, e_in = inside_cage(run, c, "erad")
    _, i_in = inside_cage(run, c, "irad")
    t_v, volts = ring_voltages(run)
    done = (run / "DONE").read_text().strip() if (run / "DONE").exists() else "running"
    cells = []
    for t in times:
        if number[-1, 1] * 1e9 < t + 0.5:
            cells.append("-")
            continue
        ring = np.mean([near(v, t_v, t) for v in volts]) / 1e3 if len(t_v) else float("nan")
        cells.append(f"{near(number[:, 6], number[:, 1], t) / 1e14:5.3f} {near(e_in, when, t) / 1e14:5.3f} {near(i_in, when, t) / 1e14:5.3f} {ring:5.0f}")
    print(f"{name:22s} {done:9s} {number[-1, 1] * 1e9:6.2f} | " + " | ".join(cells))
