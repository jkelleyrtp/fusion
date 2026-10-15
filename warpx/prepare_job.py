"""Prepare (not submit) a one-node WarpX job: build WarpX for CUDA once on shared storage, run one case per GPU."""
import argparse
import base64
import io
import json
import shlex
import tarfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARED = "/public/jonathan/cusp"
BUILD = f"{SHARED}/warpx-26.10-cuda"

RUNNER = r"""
set -uo pipefail
out=__OUT__/attempt-$(date +%Y%m%d-%H%M%S); mkdir -p "$out"; cd "$out"
echo "__PAYLOAD__" | base64 -d | tar -xzf -
exec > >(tee -a "$out/job.log") 2>&1
nvidia-smi -L
if [ ! -x __BUILD__/build/bin/warpx.3d ]; then
  mkdir -p __BUILD__ && cd __BUILD__
  python3 -m pip install -q --target __BUILD__/tools cmake ninja
  export PATH=__BUILD__/tools/bin:$PATH PYTHONPATH=__BUILD__/tools
  [ -d src ] || git clone -q --depth 1 --branch 26.10 https://github.com/BLAST-WarpX/warpx.git src
  cmake -S src -B build -G Ninja -DWarpX_DIMS=3 -DWarpX_COMPUTE=CUDA -DWarpX_MPI=OFF -DWarpX_EB=ON \
    -DWarpX_OPENPMD=OFF -DWarpX_FFT=OFF -DWarpX_QED=OFF -DWarpX_PYTHON=OFF -DCMAKE_BUILD_TYPE=Release > configure.log 2>&1 \
    && cmake --build build -j 32 > build.log 2>&1 || { tail -30 configure.log build.log; echo build > "$out/JOB_FAILED"; exit 0; }
  cd "$out"
fi
gpu=0
while read -r name deck rest; do
  [ -z "$name" ] && continue
  mkdir -p "$name"
  ( cd "$name" && start=$(date +%s) \
    && CUDA_VISIBLE_DEVICES=$gpu timeout __TIMEOUT__ __BUILD__/build/bin/warpx.3d "$out/$deck" $rest > run.log 2>&1 \
    && echo complete > DONE || echo "failed $?" > DONE; echo $(( $(date +%s) - start )) > WALL_S ) &
  gpu=$(( (gpu + 1) % 8 ))
  [ "$gpu" = 0 ] && wait
done < cases.txt
wait
echo finished > "$out/JOB_DONE"
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="lines of: name deck [key=value ...]")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=21600)
    args = parser.parse_args()
    token = uuid.uuid4().hex[:12]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        archive.add(args.cases, "cases.txt")
        for deck in sorted((ROOT / "pops").glob("inputs_*")):
            archive.add(deck, deck.name)
    runner = (RUNNER.replace("__OUT__", f"{SHARED}/runs/warpx-{token}").replace("__BUILD__", BUILD)
              .replace("__TIMEOUT__", str(args.timeout))
              .replace("__PAYLOAD__", base64.b64encode(buffer.getvalue()).decode()))
    template = json.loads((ROOT.parent / "jobs/poisson-server-template.json").read_text())
    template["metadata"]["name"] = f"jonathan-warpx-{token}"
    spec = template["spec"]
    spec["entrypoint"] = (f"bash -c {shlex.quote(runner)} -- --actor-num-nodes 1 "
                          "--actor-num-gpus-per-node 8 --rollout-num-gpus 0")
    spec["submitterConfig"]["backoffLimit"] = 0
    assert spec["shutdownAfterJobFinishes"] is True and spec["ttlSecondsAfterFinished"] == 600
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "job.yaml").write_text(json.dumps(template, indent=2) + "\n")
    record = {"job_id": template["metadata"]["name"], "run_directory": f"warpx-{token}", "cases": args.cases.read_text()}
    (args.output / "request.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
