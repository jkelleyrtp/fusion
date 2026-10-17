"""Net current along the axis in every snapshot of finished picket cases, from the field around the axis."""
import sys
from pathlib import Path

import numpy as np

MU0 = 4e-7 * np.pi
root = Path("/public/jonathan/cusp/campaigns/pw1")
profile_for = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else set()
for run in sorted(root.glob(sys.argv[2] if len(sys.argv) > 2 else "pw_s*")):
    if not (run / "DONE").exists() or (run / "DONE").read_text().strip() != "complete":
        continue
    rw = 0.015  # the picket deck puts the wall at 1.5 a, with a = 1 cm
    out, last = [], None
    for snapshot in sorted((p for p in (run / "diags").glob("diag1[0-9]*") if (p / "Level_0/Cell_D_00000").exists()), key=lambda p: int(p.name[5:]) if p.name[5:].isdigit() else -1):
        if (snapshot / "Level_0/Cell_D_00001").exists() or not snapshot.name[5:].isdigit():
            continue
        header = (snapshot / "Header").read_text().split("\n")
        n = int(header[1]); names = header[2:2 + n]; time = float(header[3 + n])
        k = names.index("Bt")
        with open(snapshot / "Level_0/Cell_D_00000", "rb") as data:
            high = data.readline().decode().split(") (")[1].split(")")[0]
            nr, nz = (int(v) + 1 for v in high.split(","))
            data.seek(k * nr * nz * 8, 1)
            bt = np.frombuffer(data.read(nr * nz * 8), dtype="<f8").reshape(nz, nr)
        r = (np.arange(nr) + 0.5) / nr * rw
        current = 2 * np.pi * r * bt.mean(axis=0) / MU0 / 1e3
        band = (r > 0.7 * rw) & (r < 0.8 * rw)
        out.append((time * 1e9, float(current[band].mean())))
        last = (r, current, bt)
    if not out:
        print(run.name, "no single-box snapshots"); continue
    t = np.array(out)
    pick = [t[np.argmin(np.abs(t[:, 0] - f * t[-1, 0]))] for f in (0.2, 0.4, 0.6, 0.8, 1.0)]
    print(f"{run.name:32s} end {t[-1,0]:6.1f} ns | kA at fifths: " + " ".join(f"{p[1]:7.1f}" for p in pick) + f" | largest {np.abs(t[:,1]).max():6.1f} | {len(t)} snapshots")
    if run.name in profile_for:
        r, current, bt = last
        print("   r/rw:    " + " ".join(f"{x:6.2f}" for x in np.arange(0.05, 1.0, 0.1)))
        print("   I(<r) kA " + " ".join(f"{np.interp(x*rw, r, current):6.1f}" for x in np.arange(0.05, 1.0, 0.1)))
        nz = bt.shape[0]
        print("   along z at 0.75 rw, kA: " + " ".join(f"{2*np.pi*0.75*rw*bt[j, int(0.75*bt.shape[1])]/MU0/1e3:6.1f}" for j in range(0, nz, max(1, nz // 8))))
