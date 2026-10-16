# GPU jobs

The simulations run on shared B200 capacity managed by the slime job broker. The rules in
`AGENTS.md` exist so other researchers can always reclaim that capacity. This page explains them.

## Submitting

```bash
cd /home/ubuntu/repos/research
uv run train gpus --cluster aws-usw2          # free capacity
uv run train job list --cluster aws-usw2      # what is running
uv run train job submit <job>.yaml --cluster aws-usw2 --priority 1
```

`warpx/campaign.py submit` writes the job file from `warpx/job-template.json` and runs these commands itself.

An equivalent authorized cluster is acceptable only after inspecting its availability the same way.
All broker interaction goes through `uv run train job ...` and `uv run train gpus`.

## Priority

Priority 1 is a user requirement. It is not the lowest: it can preempt priority-0 jobs and is
preemptible by priorities 2–5. The broker's `preempt_min_runtime` may delay when a job becomes
eligible for preemption or eviction, so do not promise instant capacity reclamation.

## One node

The entrypoint keeps `--actor-num-nodes 1`, `--actor-num-gpus-per-node 8` (or fewer) and
`--rollout-num-gpus 0`, and uses GPUs only within that node. `warpx/campaign.py` runs independent cases, one per GPU, and can also run one WarpX case across the node's GPUs; see `multi-gpu.md`.

## Releasing the node

`shutdownAfterJobFinishes: true` and `ttlSecondsAfterFinished` make the job release its node when
it ends.

## Preemption

The broker takes a priority-1 node back whenever higher-priority work needs it, and starts the job again when
a node is free. Do not resubmit around it. Each case checkpoints every `chk_every` steps; when the job comes
back, or another node of the same campaign has a free GPU, the case carries on from its last checkpoint. A
case is failed only if WarpX itself ends badly three times from the same point; losing its node does not
count. A case is complete only when its `DONE` file reads `complete`.
