"""Run named campaigns of WarpX cases on GPU nodes, through the job broker at priority 1.

A campaign is a directory on shared storage holding one queue of cases. Each job is one node whose eight GPUs
take cases from that queue, so a campaign spreads over as many nodes as it is given and more can be added later.
A case that stops without finishing (its node was reclaimed) is picked up by another GPU from its last
checkpoint. Each finished case is reduced on the node to `measured.json`.

  campaign.py submit NAME --cases FILE --question "..." [--nodes N]   start a campaign, or add cases or nodes to one
  campaign.py status NAME                                             what each case is doing
  campaign.py sync NAME                                               fetch finished cases and write table.jsonl
"""
import argparse
import base64
import datetime
import hashlib
import io
import json
import shlex
import subprocess
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
MAX_NODES = 6  # most nodes this script will hold at once, across all campaigns
PATCHES = sorted((ROOT / "patches").glob("*.patch"))
# The build directory is named after the patches applied to WarpX 26.10, so a changed patch gets a fresh build.
BUILD = f"{SHARED}/warpx-26.10-cuda-" + hashlib.sha256(b"".join(patch.read_bytes() for patch in PATCHES)).hexdigest()[:8]
# Which script reduces a finished case, by the deck it ran.
REDUCERS = {"inputs_3d_cusp_beta": "analyze_beta.py", "inputs_3d_cusp_cage": "analyze_cage.py",
            "inputs_3d_cusp_cage_gas": "analyze_cage.py"}

BUILD_STEPS = r"""if [ ! -x "$warpx" ]; then
  mkdir -p __BUILD__ && cd __BUILD__ || exit 1
  python3 -m pip install -q --target __BUILD__/tools cmake ninja
  export PATH=__BUILD__/tools/bin:$PATH PYTHONPATH=__BUILD__/tools
  [ -d src ] || { git clone -q --depth 1 --branch 26.10 https://github.com/BLAST-WarpX/warpx.git src \
    && for patch in "$files"/*.patch; do git -C src apply "$patch" || { echo patch-failed; exit 0; }; done; }
  cmake -S src -B build -G Ninja -DWarpX_DIMS=3 -DWarpX_COMPUTE=CUDA -DWarpX_MPI=OFF -DWarpX_EB=ON \
    -DWarpX_OPENPMD=OFF -DWarpX_FFT=OFF -DWarpX_QED=OFF -DWarpX_PYTHON=OFF -DCMAKE_BUILD_TYPE=Release > configure.log 2>&1 \
    && cmake --build build -j 32 > build.log 2>&1 || { tail -30 configure.log build.log; echo build-failed; exit 0; }
  cd "$camp"
fi"""

WORKER = r"""
set -uo pipefail
export camp=__CAMP__; job=__JOB__; files=$camp/files-$job; warpx=${WARPX:-__BUILD__/build/bin/warpx.3d}
mkdir -p "$files" "$camp/logs"; cd "$camp"
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
# worker has not touched its CLAIM file for five minutes (its node was reclaimed). Three tries, then it is failed.
next_case() {
  flock "$camp/lock" bash -c 'cd "$camp"; line=$(head -n 1 queue.txt); sed -i 1d queue.txt
    if [ -z "$line" ]; then
      while read -r name rest; do
        [ -f "$name/DONE" ] || [ -n "$(find "$name/CLAIM" -mmin -5 2>/dev/null)" ] && continue
        if [ "$(cat "$name/TRIES" 2>/dev/null || echo 0)" -ge 3 ]; then echo "failed after 3 tries" > "$name/DONE"; continue; fi
        line="$name $rest"; break
      done < all_cases.txt
    fi
    [ -z "$line" ] && exit 0
    read -r name rest <<< "$line"; mkdir -p "$name"; touch "$name/CLAIM"
    echo $(( $(cat "$name/TRIES" 2>/dev/null || echo 0) + 1 )) > "$name/TRIES"; echo "$line"'
}

run_case() {
  local gpu=$1 name=$2 deck=$3; shift 3
  cd "$camp/$name"; local start=$(date +%s)
  # While the case runs, keep its claim fresh and keep only the two newest checkpoints.
  ( while sleep 60; do touch CLAIM; ls -d diags/chk[0-9]* 2>/dev/null | sort | head -n -2 | xargs -r rm -rf; done ) &
  local beat=$! restart=""
  # Restart from the newest checkpoint that was written to the end, which the log shows by the next step finishing.
  for chk in $(ls -d diags/chk[0-9]* 2>/dev/null | sort -r); do
    grep -q "^STEP $(( 10#${chk##*chk} + 1 )) ends" run.log && { restart="amr.restart=$chk"; break; }
  done
  # The stopped try wrote diagnostics past its last checkpoint; drop those rows so the restart does not repeat them.
  if [ -n "$restart" ]; then
    local step=$((10#${restart##*chk}))
    for file in diags/reducedfiles/*.txt; do awk -v last=$step 'NR == 1 || $1 <= last' "$file" > trim.tmp && mv trim.tmp "$file"; done
  fi
  echo "$job gpu $gpu ${restart:-fresh}" >> attempts.log
  CUDA_VISIBLE_DEVICES=$gpu timeout __TIMEOUT__ "$warpx" "$files/$deck" "$@" $restart >> run.log 2>&1; local code=$?
  kill $beat 2>/dev/null
  echo $(( $(cat WALL_S 2>/dev/null || echo 0) + $(date +%s) - start )) > WALL_S
  if [ $code -eq 0 ]; then
    local reducer; reducer=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "$files/reducers.json" "$deck")
    echo complete > DONE
    [ -n "$reducer" ] && { python3 "$files/$reducer" . > measured.tmp 2> reduce.log && mv measured.tmp measured.json; }
    rm -rf diags/chk[0-9]*
  elif [ $code -eq 124 ]; then echo "failed: time limit" > DONE
  else rm -f CLAIM  # stopped or crashed: leave it for another GPU, up to three tries
  fi
}

for gpu in 0 1 2 3 4 5 6 7; do
  ( while line=$(next_case) && [ -n "$line" ]; do run_case $gpu $line; done ) &
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
    table = shell("COLUMNS=250 uv run train gpus --cluster aws-usw2", cwd=RESEARCH)
    return sum(int(line.split("│")[4]) for line in table.splitlines() if "compute.internal" in line)


def job_spec(name: str, cases: str, timeout: int) -> tuple[str, dict]:
    """The broker job for one node working on campaign `name`, carrying `cases` to add to its queue."""
    token = uuid.uuid4().hex[:12]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for content, filename in ((cases, "cases.txt"), (json.dumps(REDUCERS), "reducers.json")):
            info = tarfile.TarInfo(filename)
            info.size = len(content.encode())
            archive.addfile(info, io.BytesIO(content.encode()))
        for file in sorted([*(ROOT / "pops").glob("inputs_*"), *(ROOT / "cusp").glob("inputs_*"),
                            *(ROOT / "cusp").glob("*.dat"), *(ROOT / "cusp").glob("analyze_*.py"), *PATCHES]):
            archive.add(file, file.name)
    worker = (WORKER.replace("__BUILD_STEPS__", BUILD_STEPS).replace("__CAMP__", f"{SHARED}/campaigns/{name}")
              .replace("__JOB__", token).replace("__BUILD__", BUILD).replace("__TIMEOUT__", str(timeout))
              .replace("__PAYLOAD__", base64.b64encode(buffer.getvalue()).decode()))
    template = json.loads((ROOT.parent / "jobs/poisson-server-template.json").read_text())
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
    held, free = len(my_pods()), free_nodes()
    assert held + args.nodes <= MAX_NODES, f"holding {held} nodes; {args.nodes} more would pass the cap of {MAX_NODES}"
    assert free >= args.nodes, f"only {free} nodes are free"
    for index in range(args.nodes):
        # Every job carries all the new cases; the first to start queues them and the rest find them queued.
        token, template = job_spec(args.name, "\n".join(new) + "\n", args.timeout)
        folder = JOBS / f"{args.name}-{token}"
        folder.mkdir(parents=True)
        (folder / "job.yaml").write_text(json.dumps(template, indent=2) + "\n")
        print(shell(f"uv run train job submit {folder}/job.yaml --cluster aws-usw2 --priority 1", cwd=RESEARCH).strip()[-300:])
        entry["jobs"].append({"job": f"jonathan-warpx-{token}", "submitted": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")})
        if index == 0:
            entry["cases"] += new
        REGISTRY.write_text(json.dumps(known, indent=1) + "\n")
    print(f"{args.name}: {len(new)} new cases, {args.nodes} nodes; holding {held + args.nodes} of {MAX_NODES}, {free - args.nodes} free")


def on_cluster(command: str) -> str:
    """Run a command where shared storage is mounted, which is inside any of this script's running jobs."""
    pods = [pod for pod in my_pods() if "Running" in shell(f"kubectl --context {CONTEXT} get pod {pod} --no-headers")]
    assert pods, "no job of ours is running, so shared storage cannot be read right now"
    return shell(f"kubectl --context {CONTEXT} exec {pods[0]} -- bash -c {shlex.quote(command)}")


def status(args: argparse.Namespace) -> None:
    pods = shell(f"kubectl --context {CONTEXT} get pods --no-headers").splitlines()
    for job in registry()[args.name]["jobs"]:
        # A job's entrypoint is started by a small submitter pod on a CPU node; until that pod is placed the
        # job holds its GPU node without working.
        states = {("node" if "-head-" in line else "worker"): line.split()[2] for line in pods if line.startswith(job["job"])}
        print(f"{job['job']}: " + (", ".join(f"{role} {state}" for role, state in sorted(states.items())) or "gone"))
    print(on_cluster(f"""cd {SHARED}/campaigns/{args.name} 2>/dev/null || {{ echo "no worker has started yet"; exit 0; }}
      echo "queued: $(wc -l < queue.txt)"; while read -r name rest; do
      if [ -f $name/DONE ]; then echo "$name: $(cat $name/DONE) ($(cat $name/WALL_S) s)"
      elif [ -d $name ]; then echo "$name: running, try $(cat $name/TRIES), $(grep 'ends. TIME' $name/run.log | tail -n 1 | cut -c1-40)"
      fi; done < all_cases.txt"""))


def sync(args: argparse.Namespace) -> None:
    """Fetch the reduced diagnostics of finished cases and write one line per complete case to table.jsonl."""
    target = RESULTS / args.name
    target.mkdir(parents=True, exist_ok=True)
    have = " ".join(f"--exclude={path.parent.name}" for path in target.glob("*/DONE"))
    packed = on_cluster(f"cd {SHARED}/campaigns/{args.name} && tar -czf - {have} all_cases.txt $(ls -d */DONE | sed 's|/DONE||' | "
                        "sed 's|.*|& |' | awk '{print $1\"/DONE \"$1\"/WALL_S \"$1\"/attempts.log \"$1\"/warpx_used_inputs \"$1\"/diags/reducedfiles\"}') "
                        "$(ls */measured.json 2>/dev/null) 2>/dev/null | base64 -w0")
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(packed)), mode="r:gz") as archive:
        archive.extractall(target, filter="data")
    rows = []
    for done in sorted(target.glob("*/DONE")):
        measured = done.parent / "measured.json"
        if done.read_text().strip() == "complete" and measured.exists() and measured.read_text().strip():
            rows.append(json.dumps({"case": done.parent.name, **json.loads(measured.read_text())}))
    (target / "table.jsonl").write_text("\n".join(rows) + "\n")
    states = [done.read_text().strip() for done in target.glob("*/DONE")]
    print(f"{args.name}: {states.count('complete')} complete, {len(states) - states.count('complete')} failed, "
          f"{len(registry()[args.name]['cases']) - len(states)} to go; {len(rows)} rows in {target}/table.jsonl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in (("submit", submit), ("status", status), ("sync", sync)):
        command = commands.add_parser(name)
        command.add_argument("name")
        command.set_defaults(function=function)
        if name == "submit":
            command.add_argument("--cases", type=Path, help="lines of: name deck [key=value ...]")
            command.add_argument("--question", help="what the campaign is meant to answer")
            command.add_argument("--nodes", type=int, default=1)
            command.add_argument("--timeout", type=int, default=21600, help="seconds allowed per try of a case")
    arguments = parser.parse_args()
    arguments.function(arguments)
