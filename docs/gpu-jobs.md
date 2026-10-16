# GPU jobs

The simulations run on shared B200 capacity managed by the slime job broker. The rules in
`AGENTS.md` exist so other researchers can always reclaim that capacity. This page explains them.

## Submitting

```bash
cd /home/ubuntu/repos/research
uv run train gpus --cluster aws-usw2          # free capacity
uv run train job list --cluster aws-usw2      # what is running
uv run train job submit /home/ubuntu/repos/fusion/jobs/<name>.yaml --cluster aws-usw2 --priority 1
```

An equivalent authorized cluster is acceptable only after inspecting its availability the same way.
All broker interaction goes through `uv run train job ...` and `uv run train gpus`.

## Priority

Priority 1 is a user requirement. It is not the lowest: it can preempt priority-0 jobs and is
preemptible by priorities 2–5. The broker's `preempt_min_runtime` may delay when a job becomes
eligible for preemption or eviction, so do not promise instant capacity reclamation.

## One node

The entrypoint keeps `--actor-num-nodes 1`, `--actor-num-gpus-per-node 8` (or fewer) and
`--rollout-num-gpus 0`, and uses GPUs only within that node. The older jobs run independent cases, one per GPU.
`warpx/campaign.py` can also run one WarpX case across the node's GPUs; see `multi-gpu.md`.

## Releasing the node

`shutdownAfterJobFinishes: true` and `ttlSecondsAfterFinished` make the job release its node when
it ends.

## Preemption

A preempted simulation restarts the whole sweep from scratch; there is no checkpoint or resume.
Member results are written incrementally to `<out>/<tag>/` on FSx, so partial outputs survive, and
a rerun creates a new timestamped run directory. A case is complete only when its `DONE` file
reads `complete`.
