"""Build the body of the cusp-cage page from reduced results.

Usage: build_cage_page.py FIG_DIR RESULTS_DIR
FIG_DIR holds series.json and the map PNGs written by plot_cage.py; RESULTS_DIR holds <batch>/measured.jsonl.
Only runs whose DONE file reads "complete" are used.
"""
import base64, datetime, json, sys
from pathlib import Path
import numpy as np

fig, results = Path(sys.argv[1]), Path(sys.argv[2])
series = json.loads((fig / "series.json").read_text())
measured = {}
for batch in ("c1", "s1", "s2", "s3", "s4"):
    for line in open(results / batch / "measured.jsonl"):
        m = json.loads(line)
        if m["status"] == "complete":
            measured[m["run"]] = m
Q_E = 1.602176634e-19
grid = np.arange(0, 30.01, 0.25)


def on_grid(t, v, axis=grid):
    out = np.interp(axis, t, v)
    return [round(float(x), 3) if t[0] <= g <= t[-1] else None for g, x in zip(axis, out)]


def dip(run):
    """(time ns, centre voltage dip V) of one run, starting from the empty device."""
    s = series[run]
    return [0.0] + s["probe_time_ns"][1:], [0.0] + [s["centre_V"][0] - x for x in s["centre_V"][1:]]


def at(run, t_ns):
    """(electrons, centre dip) of one run at one time."""
    s = series[run]
    return float(np.interp(t_ns, s["time_ns"], s["electrons"])), float(np.interp(t_ns, *dip(run)))


count_runs = {"c_b0_0.1A": "b0", "c_b4k_0.1A": "b4", "c_b16k_0.1A": "b16"}
rate = measured["c_b16k_0.1A"]["emitted_A"] / Q_E
count_rows = [{"t": float(g), "emitted": round(rate * g * 1e-9 / 1e9, 3)} for g in grid]
for run, key in count_runs.items():
    for row, v in zip(count_rows, on_grid(series[run]["time_ns"], np.array(series[run]["electrons"]) / 1e9)):
        row[key] = v

scan = {"h_b0_w1500_3A": "k0", "h_8k_w1500_3A": "k8", "h_16k_w1500_3A": "k16", "h_32k_w1500_3A": "k32"}
scan_rows = [{"t": float(g)} for g in grid]
for run, key in scan.items():
    for row, x in zip(scan_rows, on_grid(*dip(run))):
        row[key] = x

loss_runs = ["g_b0_1A", "b_8k_1A", "g_b16k_1A", "b_32k_1A", "f_b16k_1A_60ns",
             "h_b0_w1500_3A", "h_8k_w1500_3A", "h_16k_w1500_3A", "h_32k_w1500_3A",
             "h_16k_w1500_1A", "h_16k_w1500_10A", "h_16k_w800_3A"]
loss = [measured[r] for r in loss_runs]
for m in loss:
    m["available_V"] = m["centre_V_empty"] + m["emitter_eV"]

off_grid = np.arange(-5, 25.01, 0.25)
off_rows = [{"t": float(g)} for g in off_grid]
off = {}
for run, key in (("d_b0_1A_off", "off0"), ("d_b16k_1A_off", "off16"), ("d_b64k_1A_off", "off64")):
    s = series[run]
    t = np.array(s["time_ns"]) - s["toff_ns"]
    n = np.array(s["electrons"])
    start = float(np.interp(0.0, t, n))
    for row, v in zip(off_rows, on_grid(t, 100 * n / start, off_grid)):
        row[key] = v
    last = t >= t[-1] - 5
    off[key] = {"after_ns": float(t[-1]), "left": float(n[-1] / start), "left_10": float(np.interp(10.0, t, n) / start),
                "left_2": float(np.interp(2.0, t, n) / start),
                "late_tau_ns": float(-n[last].mean() / np.polyfit(t[last], n[last], 1)[0])}

pair = lambda a, b, t: {"t": t, "n": at(b, t)[0] / at(a, t)[0] - 1, "dip": at(b, t)[1] / at(a, t)[1] - 1}
checks = {
    "mesh500": pair("h_16k_w1500_3A", "h_16k_w1500_3A_n192", 20.0),
    "mesh50": pair("g_b16k_1A", "f_b16k_1A_n192", 20.0),
    "seed500": pair("h_16k_w1500_3A", "h_16k_w1500_3A_seed2", 30.0),
    "seed50": pair("w_1k_r3_1A", "w_1k_r3_1A_seed2", 30.0),
    "step": pair("g_b16k_1A", "f_b16k_1A_dt", 20.0),
}
best = max((measured[r] for r in scan), key=lambda m: m["well_V"])
facts = {"off": off, "checks": checks,
         "best": {"well": best["well_V"], "available": best["centre_V_empty"] + best["emitter_eV"], "coil": best["coil_at"],
                  "centre": best["centre_V"]},
         "ring_off": measured["h_b0_w1500_3A"]["ring_direct_A"], "ring_on": measured["h_16k_w1500_3A"]["ring_direct_A"],
         "well_off": measured["h_b0_w1500_3A"]["well_V"]}

labels = {"h_b0_w1500_3A": "Coils off", "h_8k_w1500_3A": "8 kA-turns", "h_16k_w1500_3A": "16 kA-turns",
          "h_32k_w1500_3A": "32 kA-turns", "g_b16k_1A": "16 kA-turns, weak emitters"}
images = {r: "data:image/png;base64," + base64.b64encode((fig / f"{r}.png").read_bytes()).decode() for r in labels}
maps = [{"run": r, "label": l} for r, l in labels.items()]
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M UTC on %-d %B %Y")
body = Path(__file__).with_name("cusp-cage-template.html").read_text()
for key, value in (("COUNT", count_rows), ("SCAN", scan_rows), ("LOSS", loss), ("OFF", off_rows), ("FACTS", facts),
                   ("IMAGES", images), ("MAPS", maps)):
    body = body.replace(f"__{key}__", json.dumps(value))
body = body.replace("__STAMP__", stamp)
assert "__" not in body.replace("__proto__", ""), "unfilled placeholder"
Path(__file__).with_name("cusp-cage-body.html").write_text(body)
print(json.dumps(facts, indent=1))
