"""Keep one JSON file describing every run of every campaign, for the site's Runs page.

Usage: runs_feed.py [--every SECONDS] [--out FILE]

Each round reads the campaign registry here and, through any node a job of ours holds, the state files the workers
keep on shared storage. What a case measured is kept here once fetched, so finished results stay on the page after
the last node is released; `cluster.reachable` says whether the states shown are from this round.
"""
import argparse
import datetime
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path

import campaign

OUT = Path("/home/ubuntu/warpx/live/runs.json")

# Runs on a node, where shared storage is mounted. Prints one JSON object: for each campaign folder, its queue,
# the GPUs each job has busy, and the state files of each case. `since` limits which measured.json are sent.
ON_NODE = r'''
import glob, json, os, re, sys, time
since, now, out = float(sys.argv[1]), time.time(), {}
def text(path):
    try:
        with open(path) as file: return file.read().strip()
    except OSError: return None
def last_step(path):
    try:
        with open(path, "rb") as file:
            file.seek(max(0, os.path.getsize(path) - 6000)); tail = file.read().decode(errors="replace")
    except OSError: return None
    found = re.findall(r"STEP (\d+) ends\. TIME = (\S+) DT = (\S+)", tail)
    return [int(found[-1][0]), float(found[-1][1]), float(found[-1][2])] if found else None
def limit(path):
    found = {}
    for line in (text(path) or "").splitlines():
        match = re.match(r"(stop_time|max_step)\s*=\s*(.*?)\s*(?:#\s*(\S+))?$", line)
        if match:
            try: found[match.group(1)] = float(match.group(3) or match.group(2))
            except ValueError: pass
    return found
for folder in sorted(glob.glob("/public/jonathan/cusp/campaigns/*/")):
    cases = {}
    for line in (text(folder + "all_cases.txt") or "").splitlines():
        name = line.split()[0]; case = folder + name + "/"
        if not os.path.isdir(case): continue
        entry = {"done": text(case + "DONE"), "wall_s": text(case + "WALL_S"), "tries": text(case + "TRIES")}
        tries = [l for l in (text(case + "attempts.log") or "").splitlines() if not l.endswith("lost its claim")]
        if tries: entry["last_try"] = tries[-1]
        if entry["done"] is None:
            entry["claim"] = text(case + "CLAIM")
            try: entry["claim_age_s"] = now - os.path.getmtime(case + "CLAIM")
            except OSError: pass
            entry["step"] = last_step(case + "run.log"); entry.update(limit(case + "warpx_used_inputs"))
            try: entry["try_started"] = os.path.getmtime(case + "attempts.log")
            except OSError: pass
        else:
            try: entry["finished"] = os.path.getmtime(case + "DONE")
            except OSError: pass
            try:
                if os.path.getmtime(case + "measured.json") > since: entry["measured"] = json.loads(text(case + "measured.json") or "null")
            except (OSError, ValueError): pass
        cases[name] = entry
    busy = {}
    for mark in glob.glob(folder + "files-*/busy.*"):
        busy.setdefault(mark.split("files-")[1].split("/")[0], []).append(int(mark.rsplit(".", 1)[1]))
    out[os.path.basename(folder[:-1])] = {"queue": [l.split()[0] for l in (text(folder + "queue.txt") or "").splitlines()], "busy": busy, "cases": cases}
print(json.dumps(out))
'''

# The research thread a case belongs to, by the first pattern its name matches.
THREADS = [
    (r"rv_", "Charged rings at set voltages (3D)"),
    (r"im_", "Explicit against semi-implicit and implicit"),
    (r"(hw|hr|h|k)_", "Six-coil cage at high pressure (3D)"),
    (r"(pfw|pf|pk)_", "Comparison with Park 2019"),
    (r"pw_.*_mirror", "Size scan: mirror ends"),
    (r"pw_.*_(two|four|eight)", "Size scan: longer wrap-around boxes"),
    (r"(pw|ps|pm)_", "Size scan: one-period wrap-around box"),
    (r"(zw|z|s|pt)\d*_", "Two coils with real end walls"),
]


def thread(case: str, name: str) -> str:
    return next((label for pattern, label in THREADS if re.match(pattern, case)), f"Earlier campaign {name}")


def finite(value):
    """The same value with NaN and infinity as None, which is all a browser's JSON reader accepts."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite(item) for key, item in value.items()}
    return [finite(item) for item in value] if isinstance(value, list) else value


def pods() -> list[dict]:
    """Our jobs' pods, as the cluster lists them."""
    lines = campaign.shell(f"kubectl --context {campaign.CONTEXT} get pods --no-headers").splitlines()
    return [{"pod": line.split()[0], "state": line.split()[2], "age": line.split()[-1], "role": "node" if "-head-" in line else "launcher"}
            for line in lines if line.startswith("jonathan-warpx-")]


def state(entry: dict | None, queued: bool) -> str:
    if entry is None:
        return "queued" if queued else "not started"
    if entry["done"] is not None:
        return "complete" if entry["done"] == "complete" else "failed"
    if entry.get("claim") and entry.get("claim_age_s", 1e9) < 600:
        return "running"
    # Started, then left: its job ended or lost the node before the case finished.
    return "queued" if queued else "unfinished"


def collect(previous: dict) -> dict:
    """One round. `previous` is the last file written, whose measurements and states are kept where the cluster
    gives nothing new."""
    known = {(run["campaign"], run["case"]): run for run in previous.get("runs", [])}
    cluster = {"reachable": False, "pods": [], "note": ""}
    seen: dict = {}
    try:
        cluster["pods"] = pods()
        running = [pod["pod"] for pod in cluster["pods"] if pod["role"] == "node" and pod["state"] == "Running"]
        if running:
            since = previous.get("cluster", {}).get("read_at", 0) - 300
            got = subprocess.run(["kubectl", "--context", campaign.CONTEXT, "exec", "-i", running[0], "--", "python3", "-", str(since)],
                                 input=ON_NODE, capture_output=True, text=True, check=True, timeout=240)
            seen, cluster["reachable"], cluster["read_at"] = json.loads(got.stdout), True, time.time()
        else:
            cluster["note"] = "No node is held, so shared storage cannot be read. States are from the last round that could."
    except (subprocess.SubprocessError, ValueError) as error:
        cluster["note"] = f"Reading the cluster failed: {str(error)[:300]}"
    if not cluster["reachable"]:
        cluster["read_at"] = previous.get("cluster", {}).get("read_at", 0)
    runs, campaigns = [], []
    for name, entry in campaign.registry().items():
        there = seen.get(name, {})
        campaigns.append({"name": name, "question": entry["question"], "jobs": entry["jobs"], "busy": there.get("busy", {})})
        for line in entry["cases"]:
            case, deck, *changes = line.split()
            old = known.get((name, case), {})
            run = {"campaign": name, "case": case, "deck": deck, "changes": changes, "thread": thread(case, name)}
            if cluster["reachable"] and name in seen:
                files = there["cases"].get(case)
                run["state"] = state(files, case in there["queue"])
                files = files or {}
                run["measured"] = files.get("measured", old.get("measured"))
                for key in ("done", "wall_s", "tries", "last_try", "finished", "step", "stop_time", "max_step", "try_started"):
                    if files.get(key) is not None:
                        run[key] = files[key]
            else:
                # Without a reading, a run that was under way is of unknown state now.
                run.update({key: value for key, value in old.items() if key not in run})
                if run.get("state") in ("running", "queued"):
                    run["state"] = "unknown"
                run.setdefault("state", "unknown")
            runs.append(run)
    return {"written_at": time.time(), "written": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "cluster": cluster, "campaigns": campaigns, "runs": runs}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--every", type=int, default=0, help="seconds between rounds; 0 for one round")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    while True:
        previous = json.loads(args.out.read_text()) if args.out.exists() else {}
        partial = args.out.with_suffix(".tmp")
        partial.write_text(json.dumps(finite(collect(previous)), allow_nan=False))
        os.replace(partial, args.out)
        if not args.every:
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
