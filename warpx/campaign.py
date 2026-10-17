"""Run named campaigns of WarpX cases on GPU nodes, through the job broker at priority 1.

A campaign is a directory on shared storage holding one queue of cases. Each job is one node whose eight GPUs
take cases from that queue, so a campaign spreads over as many nodes as it is given and more can be added later.
A case that stops without finishing (its node was reclaimed) is picked up by another GPU from its last
checkpoint. Each finished case is reduced on the node to `measured.json`.

  campaign.py submit NAME --cases FILE --question "..." [--nodes N]   start a campaign, or add cases or nodes to one
  campaign.py add NAME --cases FILE                                    give more cases to the nodes a campaign already has
  campaign.py status NAME                                             what each case is doing
  campaign.py sync NAME                                               fetch finished cases and write table.jsonl
  campaign.py reduce NAME [--only PREFIX]                             reduce finished cases again on the node, with the reducers here
  campaign.py local NAME --cases FILE [--only PREFIX]                 run cases on this machine's CPUs instead, when they are small enough
"""
import argparse
import base64
import datetime
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARED = "/public/jonathan/cusp"
RESEARCH = "/home/ubuntu/repos/research"
CONTEXT = "cog-usw2-b200-ml-dev-devin"
REGISTRY = ROOT / "campaigns/registry.json"
RESULTS = Path("/home/ubuntu/warpx/results")
JOBS = Path("/home/ubuntu/warpx/jobs")
# WarpX 26.10 built here for CPUs with the same patches, for `local`.
LOCAL = {"inputs_rz_": Path("/home/ubuntu/warpx/warpx/build-rz/bin/warpx.rz"), "inputs_3d_": Path("/home/ubuntu/warpx/warpx/build/bin/warpx.3d")}
MAX_NODES = 6  # most nodes this script will hold at once, across all campaigns
LAUNCHER_CPU = 0.5  # cores the broker's launcher pod for a job asks for
PATCHES = sorted((ROOT / "patches").glob("*.patch"))
# The build directory is named after the patches applied to WarpX 26.10, so a changed patch gets a fresh build.
BUILD = f"{SHARED}/warpx-26.10-cuda-" + hashlib.sha256(b"".join(patch.read_bytes() for patch in PATCHES)).hexdigest()[:8]
# Which script reduces a finished case, by the deck it ran.
REDUCERS = {"inputs_rz_spindle_fed": "analyze_spindle.py", "inputs_rz_picket_fed": "analyze_picket.py", "inputs_3d_cusp_beta": "analyze_beta.py", "inputs_3d_cusp_fed": "analyze_beta.py", "inputs_3d_cusp_jets": "analyze_beta.py", "inputs_3d_cusp_cage": "analyze_cage.py",
            "inputs_3d_cusp_cage_gas": "analyze_cage.py"}

# Two executables are built from one source tree: the 3D one with conducting boundaries inside the box, and the
# cylindrical (r, z) one, which WarpX's electromagnetic solver does not support them in.
BUILD_STEPS = r"""if [ ! -x "$warpx" ] || [ ! -x "$warpx_rz" ]; then
  # One build at a time: a job on another node may have found the same executables missing.
  mkdir -p __BUILD__
  ( flock 9; cd __BUILD__ || exit 1
    python3 -m pip install -q --target __BUILD__/tools cmake ninja
    export PATH=__BUILD__/tools/bin:$PATH PYTHONPATH=__BUILD__/tools
    [ -d src ] || { git clone -q --depth 1 --branch 26.10 https://github.com/BLAST-WarpX/warpx.git src \
      && for patch in "$files"/*.patch; do git -C src apply "$patch" || { echo patch-failed; exit 1; }; done; }
    for kind in "3 ON build $warpx" "RZ OFF build-rz $warpx_rz"; do
      read -r dims eb dir exe <<< "$kind"
      [ -x "$exe" ] && continue
      cmake -S src -B $dir -G Ninja -DWarpX_DIMS=$dims -DWarpX_COMPUTE=CUDA -DWarpX_MPI=__MPI__ -DWarpX_EB=$eb \
        -DWarpX_OPENPMD=OFF -DWarpX_FFT=OFF -DWarpX_QED=OFF -DWarpX_PYTHON=OFF -DCMAKE_BUILD_TYPE=Release > configure-$dir.log 2>&1 \
        && cmake --build $dir -j 32 > $dir.log 2>&1 || { tail -30 configure-$dir.log $dir.log; echo build-failed; exit 1; }
    done ) 9> __BUILD__/build.lock || exit 0
fi"""

WORKER = r"""
set -uo pipefail
export camp=__CAMP__ job=__JOB__; files=$camp/files-$job; warpx=${WARPX:-__BUILD__/build/bin/warpx.3d}
warpx_rz=${WARPX:-__BUILD__/build-rz/bin/warpx.rz}
# The broker starts a job again after taking its node away. Each start is a new run of this script, told apart
# by `me`, which every claim it makes carries.
export me="$job $(hostname) $$ $(date +%s)"
mkdir -p "$files" "$camp/logs"; cd "$camp"; rm -f "$files"/busy.*
exec >> "$camp/logs/$job.log" 2>&1
echo "__PAYLOAD__" | base64 -d | tar -xzf - -C "$files"
nvidia-smi -L
__BUILD_STEPS__
# Add this job's cases to the campaign's queue, skipping names the campaign already has.
flock "$camp/lock" bash -c 'touch all_cases.txt queue.txt
  grep -v "^[[:space:]]*$" "$0/cases.txt" | while read -r name rest; do
    grep -q "^$name " all_cases.txt || { echo "$name $rest" >> all_cases.txt; echo "$name $rest" >> queue.txt; }
  done' "$files"

# Print the next case and claim it: the head of the queue, or failing that a case that has no result and whose
# worker is gone. A worker is gone if it has not touched its CLAIM file for five minutes (its node was
# reclaimed), or at once if the claim was made by an earlier start of this same job.
next_case() {
  flock "$camp/lock" bash -c 'cd "$camp"; line=$(head -n 1 queue.txt); sed -i 1d queue.txt
    if [ -z "$line" ]; then
      while read -r name rest; do
        [ -f "$name/DONE" ] && continue
        claim=$(cat "$name/CLAIM" 2>/dev/null)
        [ -n "$(find "$name/CLAIM" -mmin -5 2>/dev/null)" ] && { [ "${claim%% *}" != "$job" ] || [ "$claim" = "$me" ]; } && continue
        line="$name $rest"; break
      done < all_cases.txt
    fi
    [ -z "$line" ] && exit 0
    read -r name rest <<< "$line"; mkdir -p "$name"; echo "$me" > "$name/CLAIM"
    echo $(( $(cat "$name/TRIES" 2>/dev/null || echo 0) + 1 )) > "$name/TRIES"; echo "$line"'
}

run_case() {
  local gpu=$1 name=$2 deck=$3; shift 3
  # A case whose first setting is np=K runs as K processes rather than one per GPU it was given, to compare speeds.
  local np=__GPUS__; [[ ${1:-} == np=* ]] && { np=${1#np=}; shift; }
  cd "$camp/$name"; local start=$(date +%s)
  local restart=""
  # Restart from the newest checkpoint that was written to the end, which the log shows by the next step finishing.
  for chk in $(ls -d diags/chk[0-9]* 2>/dev/null | sort -r); do
    grep -q "^STEP $(( 10#${chk##*chk} + 1 )) ends" run.log && { restart="amr.restart=$chk"; break; }
  done
  # The stopped try wrote diagnostics past its last checkpoint; drop those rows so the restart does not repeat them.
  local step=0
  if [ -n "$restart" ]; then
    step=$((10#${restart##*chk}))
    for file in diags/reducedfiles/*.txt; do awk -v last=$step 'NR == 1 || $1 <= last' "$file" > trim.tmp && mv trim.tmp "$file"; done
  fi
  # CRASHES counts the tries from this same point that WarpX itself ended badly; three and the case is failed. A try
  # that ended because its node was taken away is not counted, however many there are, nor is one that got
  # as far as a later checkpoint. TRIES counts every try, for `status`.
  [ "$(grep -v 'lost its claim$' attempts.log 2>/dev/null | tail -n 1 | awk '{print $NF}')" = "${restart:-fresh}" ] || echo 0 > CRASHES
  if [ "$(cat CRASHES 2>/dev/null || echo 0)" -ge 3 ]; then echo "failed after 3 tries" > DONE; return; fi
  echo "$job gpu $gpu ${restart:-fresh}" >> attempts.log
  local exe=$warpx; [[ $deck == inputs_rz_* ]] && exe=$warpx_rz
  CUDA_VISIBLE_DEVICES=$gpu timeout __TIMEOUT__ __LAUNCH__ "$exe" "$files/$deck" "$@" $restart >> run.log 2>&1 &
  local run=$!
  # While the case runs, keep its claim fresh, keep only the two newest checkpoints, and stop it if its log has
  # not grown for __STALL__ seconds: a hung case would otherwise hold its GPU until the time limit.
  # If the claim is no longer this worker's, another worker has taken the case and is writing to this directory:
  # stop at once and leave everything to it.
  ( while sleep $(( __STALL__ < 60 ? __STALL__ : 60 )); do
      [ "$(cat CLAIM 2>/dev/null)" = "$me" ] || { touch "$files/lost.$gpu"; kill $run; break; }
      touch CLAIM; ls -d diags/chk[0-9]* 2>/dev/null | sort | head -n -2 | xargs -r rm -rf
      [ $(( $(date +%s) - $(stat -c %Y run.log) )) -gt __STALL__ ] && { touch STALLED; kill $run; }; done ) &
  local beat=$!
  wait $run; local code=$?
  kill $beat 2>/dev/null
  if [ -f "$files/lost.$gpu" ] || [ "$(cat CLAIM 2>/dev/null)" != "$me" ]; then rm -f "$files/lost.$gpu"; echo "$job gpu $gpu lost its claim" >> attempts.log; return; fi
  echo $(( $(cat WALL_S 2>/dev/null || echo 0) + $(date +%s) - start )) > WALL_S
  if [ $code -eq 0 ]; then
    local reducer; reducer=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "$files/reducers.json" "$deck")
    echo complete > DONE
    [ -n "$reducer" ] && { python3 "$files/$reducer" . > measured.tmp 2> reduce.log && mv measured.tmp measured.json; }
    rm -rf diags/chk[0-9]*
  elif [ -f STALLED ]; then echo "failed: no output for __STALL__ seconds" > DONE
  elif [ $code -eq 124 ]; then
    # Out of time. If it left a later checkpoint than the one it started from, another try carries on from there.
    local reached=0
    for chk in $(ls -d diags/chk[0-9]* 2>/dev/null | sort -r); do
      grep -q "^STEP $(( 10#${chk##*chk} + 1 )) ends" run.log && { reached=$((10#${chk##*chk})); break; }
    done
    if [ $reached -gt $step ]; then rm -f CLAIM; else echo "failed: time limit" > DONE; fi
  else
    # Stopped or crashed: leave it for another GPU. If the node is being taken away this shell is about to be
    # stopped too, so wait: only a shell that outlives the wait saw WarpX itself fail, and counts a crash.
    sleep __PAUSE__; echo $(( $(cat CRASHES 2>/dev/null || echo 0) + 1 )) > CRASHES; rm -f CLAIM
  fi
}

# Each case gets __GPUS__ of the node's eight GPUs. Given more than one, WarpX splits its box between them, one
# process per GPU.
# With nothing to take, a GPU keeps looking once a minute for as long as another GPU of this node is working (the
# node is held anyway), since a case whose node was reclaimed can be taken five minutes after its last heartbeat.
for first in $(seq 0 __GPUS__ 7); do
  ( while true; do
      line=$(next_case)
      if [ -z "$line" ]; then ls "$files"/busy.* > /dev/null 2>&1 || break; sleep __LOOK__; continue; fi
      touch "$files/busy.$first"; run_case $(seq -s, $first $((first + __GPUS__ - 1))) $line; rm -f "$files/busy.$first"
    done ) &
done
wait
echo "$job finished $(date -u +%FT%TZ)"
"""


def registry() -> dict:
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}


def shell(command: str, cwd: str | None = None) -> str:
    return subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, check=True).stdout


def my_pods() -> list[str]:
    """Head pods of this script's jobs that are running or waiting, which is one per node held."""
    lines = shell(f"kubectl --context {CONTEXT} get pods --no-headers").splitlines()
    return [line.split()[0] for line in lines
            if line.startswith("jonathan-warpx-") and "-head-" in line and line.split()[2] in ("Running", "Pending", "ContainerCreating")]


def free_nodes() -> int:
    """Nodes free for a new job: those the cluster shows free, less one for each of our jobs already waiting
    for one (the broker gives a freed node to those first)."""
    table = shell("COLUMNS=250 uv run train gpus --cluster aws-usw2", cwd=RESEARCH)
    jobs = shell("COLUMNS=250 uv run train job list --cluster aws-usw2", cwd=RESEARCH)
    waiting = sum("jonathan-warpx-" in line and "QUEUED" in line.split("│")[3] for line in jobs.splitlines() if line.count("│") > 3)
    return sum(int(line.split("│")[4]) for line in table.splitlines() if "compute.internal" in line) - waiting


def cpu(amount: str) -> float:
    """Kubernetes writes CPU as cores ("2") or thousandths of one ("500m")."""
    return float(amount[:-1]) / 1000 if amount.endswith("m") else float(amount)


def launcher_room(nodes: dict, described: dict[str, str]) -> int:
    """How many more launcher pods fit. A launcher asks for half a CPU on one of the few nodes without taints.
    `nodes` is `kubectl get nodes -o json`; `described` is `kubectl describe node` by node name."""
    room = 0
    for node in nodes["items"]:
        if node["spec"].get("taints") or node["spec"].get("unschedulable"):
            continue
        asked = re.search(r"Allocated resources:.*?\n\s+cpu\s+(\S+)", described[node["metadata"]["name"]], re.DOTALL).group(1)
        room += int((cpu(node["status"]["allocatable"]["cpu"]) - cpu(asked)) / LAUNCHER_CPU)
    return room


def payload(texts: dict[str, str]) -> str:
    """What a worker needs beside WarpX, packed for a shell to unpack: the decks, the reducers and which deck
    each reducer serves, the WarpX patches, and the files given here by name."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for filename, content in {**texts, "reducers.json": json.dumps(REDUCERS)}.items():
            info = tarfile.TarInfo(filename)
            info.size = len(content.encode())
            archive.addfile(info, io.BytesIO(content.encode()))
        for file in sorted([*(ROOT / "pops").glob("inputs_*"), *(ROOT / "cusp").glob("inputs_*"),
                            *(ROOT / "cusp").glob("*.dat"), *(ROOT / "cusp").glob("analyze_*.py"), *PATCHES]):
            archive.add(file, file.name)
    return base64.b64encode(buffer.getvalue()).decode()


def job_spec(name: str, cases: str, timeout: int, gpus: int = 1, stall: int = 1800, pause: int = 120, look: int = 60) -> tuple[str, dict]:
    """The broker job for one node working on campaign `name`, carrying `cases` to add to its queue. Each case
    runs on `gpus` GPUs; more than one needs the WarpX build with MPI, which is kept beside the one without."""
    assert gpus in (1, 2, 4, 8), "a node's 8 GPUs must divide evenly between cases"
    build, launch = (BUILD, "") if gpus == 1 else (BUILD + "-mpi", "mpirun --allow-run-as-root --bind-to none -np $np")
    token = uuid.uuid4().hex[:12]
    worker = (WORKER.replace("__BUILD_STEPS__", BUILD_STEPS).replace("__CAMP__", f"{SHARED}/campaigns/{name}")
              .replace("__JOB__", token).replace("__BUILD__", build).replace("__TIMEOUT__", str(timeout)).replace("__STALL__", str(stall))
              .replace("__PAUSE__", str(pause)).replace("__LOOK__", str(look))
              .replace("__MPI__", "OFF" if gpus == 1 else "ON").replace("__LAUNCH__", launch).replace("__GPUS__", str(gpus))
              .replace("__PAYLOAD__", payload({"cases.txt": cases})))
    template = json.loads((ROOT / "job-template.json").read_text())
    template["metadata"]["name"] = f"jonathan-warpx-{token}"
    spec = template["spec"]
    spec["entrypoint"] = (f"bash -c {shlex.quote(worker)} -- --actor-num-nodes 1 "
                          "--actor-num-gpus-per-node 8 --rollout-num-gpus 0")
    spec["submitterConfig"]["backoffLimit"] = 0
    assert spec["shutdownAfterJobFinishes"] is True and spec["ttlSecondsAfterFinished"] == 600
    return token, template


def submit(args: argparse.Namespace) -> None:
    known = registry()
    entry = known.get(args.name)
    if entry is None:
        assert args.question, "a new campaign needs --question"
        assert not (RESULTS / args.name).exists(), f"results/{args.name} already exists; pick another name"
        entry = known[args.name] = {"question": args.question, "cases": [], "jobs": []}
    names = {line.split()[0] for line in entry["cases"]}
    new = [line for line in (args.cases.read_text().splitlines() if args.cases else []) if line.strip()]
    clash = sorted(names & {line.split()[0] for line in new})
    assert not clash, f"campaign {args.name} already has cases {clash}"
    assert len({line.split()[0] for line in new}) == len(new), "case names repeat within the file"
    assert new or entry["cases"], "no cases to run: give --cases"
    # A job's entrypoint is started by a small launcher pod on one of a few CPU nodes. While one of ours waits for
    # a place there, its GPU node is held idle, and another job would only join the wait.
    waiting = [line.split()[0] for line in shell(f"kubectl --context {CONTEXT} get pods --no-headers").splitlines()
               if line.startswith("jonathan-warpx-") and "-head-" not in line and line.split()[2] == "Pending"]
    assert not waiting, f"{waiting} is still waiting for a launcher slot; submit after it starts"
    nodes = json.loads(shell(f"kubectl --context {CONTEXT} get nodes -o json"))
    described = {node["metadata"]["name"]: shell(f"kubectl --context {CONTEXT} describe node {node['metadata']['name']}")
                 for node in nodes["items"] if not node["spec"].get("taints")}
    room = launcher_room(nodes, described)
    assert room >= args.nodes, f"the launcher nodes have room for {room} more jobs; {args.nodes} would hold GPU nodes idle"
    held, free = len(my_pods()), free_nodes()
    assert held + args.nodes <= MAX_NODES, f"holding {held} nodes; {args.nodes} more would pass the cap of {MAX_NODES}"
    assert free >= args.nodes, f"only {free} nodes are free"
    # Every job carries all of the campaign's cases, old and new. Its worker queues the ones the campaign's folder
    # has not seen, so a job added later still has work if an earlier one was stopped before its worker started.
    carried = "\n".join(entry["cases"] + new) + "\n"
    for index in range(args.nodes):
        token, template = job_spec(args.name, carried, args.timeout, args.gpus_per_case)
        folder = JOBS / f"{args.name}-{token}"
        folder.mkdir(parents=True)
        (folder / "job.yaml").write_text(json.dumps(template, indent=2) + "\n")
        print(shell(f"uv run train job submit {folder}/job.yaml --cluster aws-usw2 --priority 1", cwd=RESEARCH).strip()[-300:])
        entry["jobs"].append({"job": f"jonathan-warpx-{token}", "gpus_per_case": args.gpus_per_case, "submitted": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")})
        if index == 0:
            entry["cases"] += new
        REGISTRY.write_text(json.dumps(known, indent=1) + "\n")
    print(f"{args.name}: {len(new)} new cases, {args.nodes} nodes; holding {held + args.nodes} of {MAX_NODES}, {free - args.nodes} free")


def on_cluster(command: str, given: str | None = None) -> str:
    """Run a command where shared storage is mounted, which is inside any of this script's running jobs.
    `given` is what the command reads as its input."""
    pods = [pod for pod in my_pods() if "Running" in shell(f"kubectl --context {CONTEXT} get pod {pod} --no-headers")]
    assert pods, "no job of ours is running, so shared storage cannot be read right now"
    flag = "" if given is None else "-i "
    return subprocess.run(f"kubectl --context {CONTEXT} exec {flag}{pods[0]} -- bash -c {shlex.quote(command)}", shell=True,
                          input=given, capture_output=True, text=True, check=True).stdout


def queue_command(name: str, cases: list[str]) -> str:
    """The shell command that puts these cases on a campaign's queue, as a worker does with its own at its start."""
    lines = "\n".join(cases)
    return (f"cd {SHARED}/campaigns/{name} && flock lock bash -c 'while read -r name rest; do grep -q \"^$name \" all_cases.txt || "
            f"{{ echo \"$name $rest\" >> all_cases.txt; echo \"$name $rest\" >> queue.txt; }}; done' <<< {shlex.quote(lines)}")


def ship(name: str) -> None:
    """Give every node of a campaign this checkout's decks and reducers in place of the ones its job brought."""
    on_cluster(f"cd {SHARED}/campaigns/{name} && base64 -d > added.tgz && for files in files-*/; do tar -xzf added.tgz -C $files; done",
               given=payload({}))


def reduce(args: argparse.Namespace) -> None:
    """Reduce a campaign's complete cases again on its node, where their field snapshots are, with this
    checkout's reducers. `sync --reduce` does the same here, from the reduced diagnostics alone."""
    ship(args.name)
    decks = {line.split()[0]: line.split()[1] for line in registry()[args.name]["cases"]}
    wanted = " ".join(f"{case}:{REDUCERS[deck]}" for case, deck in decks.items() if case.startswith(args.only) and deck in REDUCERS)
    print(on_cluster(f"cd {SHARED}/campaigns/{args.name} && files=$(ls -d files-*/ | head -n 1) && for pair in {wanted}; do "
                     "case=${pair%%:*}; [ \"$(cat $case/DONE 2>/dev/null)\" = complete ] || continue; "
                     "( cd $case && python3 ../$files/${pair##*:} . > measured.tmp 2> reduce.log && mv measured.tmp measured.json "
                     "&& echo \"$case reduced\" || echo \"$case: $(tail -n 1 reduce.log)\" ); done"), end="")


def add(args: argparse.Namespace) -> None:
    """Give more cases to the nodes a campaign already holds: a GPU there takes one when it finishes its own."""
    known = registry()
    entry = known[args.name]
    new = [line for line in args.cases.read_text().splitlines() if line.strip()]
    clash = sorted({line.split()[0] for line in entry["cases"]} & {line.split()[0] for line in new})
    assert not clash, f"campaign {args.name} already has cases {clash}"
    assert len({line.split()[0] for line in new}) == len(new), "case names repeat within the file"
    # The new cases may use decks and reducers written since those nodes' jobs were submitted.
    ship(args.name)
    on_cluster(queue_command(args.name, new))
    entry["cases"] += new
    REGISTRY.write_text(json.dumps(known, indent=1) + "\n")
    print(f"{args.name}: {len(new)} cases added to the queue")


def status(args: argparse.Namespace) -> None:
    pods = shell(f"kubectl --context {CONTEXT} get pods --no-headers").splitlines()
    for job in registry()[args.name]["jobs"]:
        # A job's entrypoint is started by a small submitter pod on a CPU node; until that pod is placed the
        # job holds its GPU node without working.
        states = {("node" if "-head-" in line else "worker"): line.split()[2] for line in pods if line.startswith(job["job"])}
        print(f"{job['job']}: " + (", ".join(f"{role} {state}" for role, state in sorted(states.items())) or "gone"))
    print(on_cluster(f"""cd {SHARED}/campaigns/{args.name} 2>/dev/null && [ -f queue.txt ] || {{ echo "no worker has started its cases yet (WarpX may be building)"; exit 0; }}
      echo "queued: $(wc -l < queue.txt)"; while read -r name rest; do
      if [ -f $name/DONE ]; then echo "$name: $(cat $name/DONE) ($(cat $name/WALL_S) s)"
      elif [ -d $name ]; then echo "$name: running, try $(cat $name/TRIES), $(grep 'ends. TIME' $name/run.log | tail -n 1 | cut -c1-40)"
      fi; done < all_cases.txt"""))


def sync(args: argparse.Namespace) -> None:
    """Fetch the reduced diagnostics of finished cases and write one line per complete case to table.jsonl."""
    target = RESULTS / args.name
    target.mkdir(parents=True, exist_ok=True)
    # Cases fetched before are not fetched again, apart from what `reduce` may have written since.
    have = " ".join(path.parent.name for path in target.glob("*/DONE"))
    packed = on_cluster(f"cd {SHARED}/campaigns/{args.name} && tar -czf - all_cases.txt $(for done in */DONE; do case=${{done%/DONE}}; "
                        f"case ' {have} ' in *\" $case \"*) ;; *) echo $case/DONE $case/WALL_S $case/attempts.log $case/warpx_used_inputs "
                        "$case/diags/reducedfiles ;; esac; done) "
                        "$(ls */measured.json */diags/reducedfiles/on_coil_plane.txt 2>/dev/null) 2>/dev/null | base64 -w0")
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(packed)), mode="r:gz") as archive:
        archive.extractall(target, filter="data")
    table(args.name, args.reduce)


def table(name: str, again: bool = False) -> None:
    """Write one line per complete case of a campaign to its table.jsonl, reducing each again here if asked."""
    target = RESULTS / name
    decks = {line.split()[0]: line.split()[1] for line in registry()[name]["cases"]}
    rows, unreduced = [], []
    for done in sorted(target.glob("*/DONE")):
        measured = done.parent / "measured.json"
        if again and done.read_text().strip() == "complete" and decks[done.parent.name] in REDUCERS:
            # The reducer in this checkout may be newer than the one the node ran.
            measured.write_text(shell(f"{sys.executable} {ROOT / 'cusp' / REDUCERS[decks[done.parent.name]]} {done.parent}"))
        if done.read_text().strip() == "complete" and measured.exists() and measured.read_text().strip():
            rows.append(json.dumps({"case": done.parent.name, **json.loads(measured.read_text())}))
        elif done.read_text().strip() == "complete" and decks[done.parent.name] in REDUCERS:
            unreduced.append(done.parent.name)
    (target / "table.jsonl").write_text("\n".join(rows) + "\n")
    states = [done.read_text().strip() for done in target.glob("*/DONE")]
    print(f"{name}: {states.count('complete')} complete, {len(states) - states.count('complete')} failed, "
          f"{len(registry()[name]['cases']) - len(states)} to go; {len(rows)} rows in {target}/table.jsonl")
    if unreduced:
        # A node taken away between a case finishing and its reduction leaves the case complete with no row.
        print(f"complete but not reduced, so not in the table (run `campaign.py reduce {name}`): {' '.join(unreduced)}")


def local(args: argparse.Namespace) -> None:
    """Run cases on this machine's CPUs, one after another, with WarpX built here from the same patches. The
    rule is the nodes': a case is complete when WarpX ran to its end and exited cleanly, and is then reduced.
    A case another call has started is left alone, so calls with different --only run side by side."""
    for patch in PATCHES:
        shell(f"git apply --reverse --check {patch}", cwd="/home/ubuntu/warpx/warpx")
    known = registry()
    entry = known.get(args.name)
    if entry is None:
        assert args.question, "a new campaign needs --question"
        entry = known[args.name] = {"question": args.question, "cases": [], "jobs": []}
    lines = [line for line in args.cases.read_text().splitlines() if line.strip()]
    held = {line.split()[0]: line for line in entry["cases"]}
    changed = sorted(line.split()[0] for line in lines if held.get(line.split()[0], line) != line)
    assert not changed, f"campaign {args.name} already has cases {changed} with other settings"
    entry["cases"] += [line for line in lines if line.split()[0] not in held]
    REGISTRY.write_text(json.dumps(known, indent=1) + "\n")
    for line in lines:
        case, deck, *settings = line.split()
        folder = RESULTS / args.name / case
        if not case.startswith(args.only) or folder.exists():
            continue
        folder.mkdir(parents=True)
        (folder / "attempts.log").write_text(f"local cpu {args.threads} threads fresh\n")
        exe = next(path for prefix, path in LOCAL.items() if deck.startswith(prefix))
        start = datetime.datetime.now(datetime.UTC)
        with (folder / "run.log").open("w") as log:
            code = subprocess.run([exe, ROOT / "cusp" / deck, *settings], cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                                  env={**os.environ, "OMP_NUM_THREADS": str(args.threads)}, check=False).returncode
        (folder / "WALL_S").write_text(f"{(datetime.datetime.now(datetime.UTC) - start).seconds}\n")
        (folder / "DONE").write_text("complete\n" if code == 0 else f"failed: exit code {code}\n")
        if code == 0 and deck in REDUCERS:
            (folder / "measured.json").write_text(shell(f"{sys.executable} {ROOT / 'cusp' / REDUCERS[deck]} {folder}"))
        for checkpoint in (folder / "diags").glob("chk[0-9]*"):
            shutil.rmtree(checkpoint)
        print(f"{case}: {(folder / 'DONE').read_text().strip()}", flush=True)
    table(args.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in (("submit", submit), ("add", add), ("status", status), ("sync", sync), ("reduce", reduce), ("local", local)):
        command = commands.add_parser(name)
        command.add_argument("name")
        command.set_defaults(function=function)
        if name == "sync":
            command.add_argument("--reduce", action="store_true", help="reduce every complete case again here, with this checkout's reducers")
        if name == "reduce":
            command.add_argument("--only", default="", help="reduce only the cases whose names start with this")
        if name == "local":
            command.add_argument("--cases", type=Path, required=True, help="lines of: name deck [key=value ...]")
            command.add_argument("--question", help="what the campaign is meant to answer, if it is new")
            command.add_argument("--only", default="", help="run only the cases whose names start with this")
            command.add_argument("--threads", type=int, default=4)
        if name == "add":
            command.add_argument("--cases", type=Path, required=True, help="lines of: name deck [key=value ...]")
        if name == "submit":
            command.add_argument("--cases", type=Path, help="lines of: name deck [key=value ...]")
            command.add_argument("--question", help="what the campaign is meant to answer")
            command.add_argument("--nodes", type=int, default=1)
            command.add_argument("--timeout", type=int, default=21600, help="seconds allowed per try of a case")
            command.add_argument("--gpus-per-case", type=int, default=1, help="1, 2, 4 or 8; the nodes added now run every case they take on this many GPUs")
    arguments = parser.parse_args()
    arguments.function(arguments)
