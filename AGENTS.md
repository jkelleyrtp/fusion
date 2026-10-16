# AGENTS.md

Binding rules for agents working in this repository. Explanations and how-tos live in `docs/`:

- `README.md`: the question, where the results stand and the layout. Read this first.
- `docs/cusp-results.md`: the current tables. `docs/README.md` indexes the rest.
- `docs/gpu-jobs.md`: how GPU jobs are submitted and why the rules below exist.
- `docs/development.md`: repository layout, tests and lint commands.

## GPU jobs

- Submit GPU work only through the job broker CLI, from `/home/ubuntu/repos/research`:
  `uv run train job submit <job>.yaml --cluster aws-usw2 --priority 1`.
- Priority is exactly 1. Do not use 0 or anything above 1.
- One node, at most 8 GPUs: `--actor-num-nodes 1 --actor-num-gpus-per-node 8 --rollout-num-gpus 0`.
- Check capacity first with `uv run train gpus --cluster aws-usw2` and
  `uv run train job list --cluster aws-usw2`. If no node is free, wait.
- Keep `shutdownAfterJobFinishes: true` and a finite `ttlSecondsAfterFinished`. Never hold GPUs
  while waiting for input.
- Never use `kubectl apply`, `kubectl port-forward`, direct GPU pods, raw broker HTTP, clique
  pinning or reservations, `--ignore-health-checks`, or stop or reprioritize another researcher's job.

## Science

- A prescribed charge sphere (`--space-charge`) is a fixed proxy field, not a self-consistent well.
  Say which one a claim rests on.
- FP64 is the reference. Do not change `CUDA_SRC`/`CPP_SRC`, integrator arithmetic or injection
  code without an explicit, reviewed design in `docs/`.
- Only cases whose `DONE` file reads `complete` count as results.

## Checks

Run the tests before committing code: `OMP_NUM_THREADS=1 python3 -m unittest discover -s tests`, and
`ruff check tests warpx/campaign.py`. If you touch `legacy/`, run its suite too:
`cd legacy && PYTHONPATH=src OMP_NUM_THREADS=1 python3 -m unittest discover -s tests`. Do not broaden
linting to the legacy scripts.
