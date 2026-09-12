# AGENTS.md — cusp electron-trap simulations

Binding rules for any agent working in this repository. The simulation runs on shared
B200 capacity managed by the slime job broker; these rules exist so other researchers
can always reclaim capacity.

## GPU dispatch policy (binding)

- Submit GPU work **only** through the job broker CLI, from the research checkout:

  ```bash
  cd /home/ubuntu/repos/research
  uv run train job submit jobs/<name>.yaml --cluster aws-usw2 --priority 1
  ```

  An equivalent authorized cluster is acceptable only after inspecting its
  availability the same way.

- **Priority is 1. This is a user requirement — do not change it to 0.**
  Priority 1 is *not* the lowest: it can preempt priority-0 jobs, and it is
  preemptible by priorities 2–5. The broker's configured `preempt_min_runtime`
  may delay when this job becomes eligible for preemption or eviction, so do
  not promise instantaneous capacity reclamation.

- **One node only.** The entrypoint must keep `--actor-num-nodes 1`,
  `--actor-num-gpus-per-node 8` (or fewer), `--rollout-num-gpus 0`, and use GPUs
  only within that one node.

- **Check capacity before launching.** Run `uv run train gpus --cluster aws-usw2`
  and `uv run train job list --cluster aws-usw2`. If no free node exists, wait;
  do not try to displace running work.

- **Never**: `kubectl apply`/direct GPU pods, raw broker HTTP, clique pinning or
  reservations (`--pinned-cliques`), `--ignore-health-checks`, priority above 1,
  or stopping/reprioritizing other researchers' jobs.

- Keep `shutdownAfterJobFinishes: true` and `ttlSecondsAfterFinished` set so the
  job releases its node. Never leave a job holding GPUs while awaiting input.

- **Preemption caveat**: a preempted simulation currently restarts the whole
  sweep from scratch — there is no checkpoint/resume guarantee. Member results
  are written incrementally to `<out>/<tag>/` on FSx, so partial outputs are
  preserved; a rerun creates a new timestamped run directory.

- **Never run `kubectl port-forward` or curl the broker directly.** All broker
  interaction goes through `uv run train job ...` / `uv run train gpus`. This
  research-repo broker CLI rule applies to all future agents.

## Scientific scope (binding)

- **Production confinement studies must inject electrons from an external gun**
  that crosses field lines into the trapping region, with the gun position and
  aim/local-B angle explicitly documented in the run record. Inside-born
  particles (`--inject-mode inside`) are numerical controls only — they are not
  evidence about beam capture.
- **Keep FP64 as the reference.** Nondimensionalization and mixed precision are
  analysis topics, not approved implementation changes; do not change
  `CUDA_SRC`/`CPP_SRC`, integrator arithmetic, or injection code without an
  explicit, reviewed design.
- A **prescribed charge sphere** (`--space-charge`) is a fixed proxy field; the
  charge is not computed from the tracked particles. Confinement by a
  prescribed positive charge is not evidence of a self-consistent negative-ion
  well — distinguish the two in all claims.

## Checks

There is no established repo-wide lint/type/test policy for the simulation
scripts (`cusp_sim.py`, `cusp_viz.py` are standalone; do not broaden linting or
refactor legacy code). The `cuda_build_cache` module does have a narrow policy —
run before committing changes to it:

```bash
python3 -m unittest discover -s tests -v
ruff check cuda_build_cache.py tests/test_cuda_build_cache.py
mypy --follow-imports=silent cuda_build_cache.py
```

## Layout

| path | what |
|---|---|
| `cusp_sim.py` | simulator: exact loop field (elliptic integrals), fused CUDA Boris/RK4 kernel (torch `load_inline`), torch fallback |
| `cuda_build_cache.py` | persistent, fingerprint-keyed build cache for the fused kernel |
| `cusp_viz.py` | `report.png` + `traj_<member>.png` + summary table from a run directory |
| `jobs/*.yaml` | broker-submittable single-node RayJobs |
| `results/` | reports and summaries pulled back from runs |
| `docs/reassessment.md` | corrected interpretation and staged simulation plan |
| `tests/` | stdlib unittest suite for `cuda_build_cache.py` |
