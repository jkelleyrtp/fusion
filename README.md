# Biconic cusp electron trap — GPU kinetic simulation

Full-orbit test-particle (non-PIC) tracking of electrons in the static field of two coaxial
current rings with opposite polarity (a spindle / biconic cusp). Runs one sweep member
per GPU on a single node, writes compact results (subsampled tracked trajectories, per-electron
escape time + channel, survival curve, (r,z) density) and renders a report.

## Layout

| path | what |
|---|---|
| `cusp_sim.py` | simulator: exact loop field (elliptic integrals), fused CUDA Boris/RK4 kernel (torch `load_inline`), torch fallback |
| `cuda_build_cache.py` | persistent fingerprint-keyed build cache for the fused kernel (see below) |
| `benchmark_build_cache.py` | measures extension startup in fresh worker processes on the GPUs |
| `cusp_viz.py` | `report.png` + `traj_<member>.png` + markdown summary table from a run directory |
| `jobs/*.yaml` | broker-submittable single-node RayJobs (`uv run train job submit /home/ubuntu/repos/fusion/jobs/<x>.yaml --cluster aws-usw2 --priority 1`) |
| `results/` | reports and summaries pulled back from the runs |
| `docs/` | [reassessment](docs/reassessment.md) and [precision notes](docs/precision-notes.md) |

## GPU dispatch (shared B200 cluster)

Submit GPU work only through the slime job broker, from the research checkout:

```bash
cd /home/ubuntu/repos/research
uv run train gpus --cluster aws-usw2                       # check free capacity first
uv run train job list --cluster aws-usw2
uv run train job submit /home/ubuntu/repos/fusion/jobs/<name>.yaml --cluster aws-usw2 --priority 1
```

- **Priority 1, exactly one node** (`--actor-num-nodes 1 --actor-num-gpus-per-node 8
  --rollout-num-gpus 0` in the entrypoint), broker-scheduled cliques only.
- Priority 1 is a user requirement: it is preemptible by priorities 2–5 and can
  preempt priority 0 — it is not the absolute lowest. The broker's
  `preempt_min_runtime` may delay reclamation; do not promise instant release.
- If no node is free, wait — never displace running work, pin cliques, bypass
  health checks, or `kubectl apply` GPU jobs directly.
- `shutdownAfterJobFinishes: true` is mandatory; never hold GPUs awaiting input.
- A preempted run restarts the sweep from scratch; per-member outputs already
  written under the run directory are preserved on FSx.

See `AGENTS.md` for the full binding policy.

## Build cache

The fused kernel compiles once per fingerprint instead of once per worker/job: `cuda_build_cache.load_cached_extension`
hashes sources, bindings, flags, toolchain (compiler `PATH`s + `--version` output), Python/Torch/CUDA identity,
the compile environment, and the architecture request into a 24-hex key shared by identical workers. Job YAMLs
set `CUSP_BUILD_DIR=/public/jonathan/cusp/build_cache` (FSx, persists across jobs; mounted with cluster-wide
`flock`); unset, it defaults to `~/.cache/cusp_build`. Locking is a POSIX `flock` on `<keydir>/build.flock`
around the whole `load_inline` call; a stale torch `FileBaton` `lock` left by a killed build is removed while
holding it. `CUSP_BUILD_VERBOSE=1` turns on verbose ninja output.

`cuda_build_cache.py` must be staged next to `cusp_sim.py` on `/public/jonathan/cusp/` before running — the job
pods import it via the script's directory. Benchmark on the GPUs (one node, priority 1, broker only):

```bash
uv run train job submit /home/ubuntu/repos/fusion/jobs/cusp-cache-benchmark-aws.yaml --cluster aws-usw2 --priority 1
```

Each member's `summary.json` records `kernel_setup_time_s`: wall time of the extension build/load attempt
(including failed attempts; `null` on CPU or with `--no-kernel`).

## Physics model

- Field: Smythe's closed form for a circular filament, `B_r, B_z` in `K(k), E(k)` (AGM), tabulated on an
  (r,z) grid once per member; the kernel does bilinear lookups. Validated against the on-axis formula (1e-15)
  and a 2880-segment Biot-Savart polygon (6e-6).
- Pusher: Boris (default, `--integrator boris`) or classic RK4 (`--integrator rk4`, reference). Boris energy drift
  is at machine precision (1e-14) with B only; RK4 drifts 1e-5..1e-2 depending on `dt`.
- Time step: adaptive per particle (`--adaptive 1`, default): `dt = steps-per-gyro-inv * 2π m/(e|B|)` at the
  particle's position, capped by grid spacing / v and by a tenth of the space-charge radius / v. Every particle is
  integrated to the same physical `--sim-time`; trajectory and density sampling are on physical-time intervals.
  `--adaptive 0` recovers a fixed `dt` from the reference field. Adaptive runs take ~8x fewer steps here (most of
  the volume is far weaker than the field at the coils).
- Electrostatics: `--space-charge Q [Q2 ...]` (C) puts a uniformly charged sphere of radius
  `--space-charge-radius` at the null (linear E inside, Coulomb outside) - a prescribed proxy
  field; the charge is not computed from these particles. Negative = trapped electron cloud /
  virtual cathode (decelerates and repels incoming electrons); positive = attractive well. It
  is a sweep axis like energy.
- Diagnostics per particle: escape time / channel, step count, minimum |B| seen (loss-cone proxy).
- Energy drift is reported per member.
- Loss channels: `-z` point cusp, `+z` point cusp, ring cusp / wall (`r > wall_fraction * a`).
- Injection modes: `cusp` (beam through the -z point cusp, ring of radius `inject_r`, pitch band),
  `inside` (born in a ball around the null, pitch uniform in cos over the band; `0..180` = isotropic),
  and `gun` (external point source; see below).

## External gun mode

`--inject-mode gun` launches all particles as a packet at t=0 from a finite source —
an off-axis point with a Gaussian transverse width and an angular cone, i.e. the
effective beam after gun optics (hardware optics like a wire + focus element are not
simulated). This mirrors the historical `electron-optimization` point gun:

- Default origin: `(0, member inject_r, -(d + inject_offset))` — i.e. off-axis, *below* the -z coil.
  `--gun-position X Y Z` overrides it (and then requires member `inject_r == 0` so sweep values
  are not silently ignored).
- `--gun-direction DX DY DZ` (default `0 0 1`) sets the aim; the member pitch band is uniform in
  cos around the *aim direction* in gun mode (around +z in other modes). `--inject-sigma` is the
  RMS Gaussian transverse beam-plane width (0 = pencil beam).
- The origin must be outside the between-coil region (`|z| > d`) and inside the loss boundaries;
  sampled beam positions outside the domain are a `ValueError` (increase `--axial-margin` or
  reduce `--inject-sigma`) — no clipping.
- Summaries record `gun_position_m`, `gun_direction_unit`, `gun_B_T`,
  `gun_axis_B_angle_deg` (local-B crossing angle; null where B=0), and p05/p50/p95 of the
  per-particle velocity–B angle. This is launch geometry, not capture proof.

Example matching the historical off-axis gun (origin below the first coil, aimed slightly
inward toward the axis). These are starting guesses, not an optimum:

```bash
python3 cusp_sim.py --inject-mode gun \
  --ring-radius 0.05 --ring-half-sep 0.025 --current 23000 \
  --inject-offset 0.03 --members 100,0.0006,0,1 \
  --gun-direction 0 -0.007142857 1 --inject-sigma 0.0001 \
  --particles 20000 --sim-time 100e-6 --out out/gun_test
```

## Runs so far (all 1 node x 8 B200, priority 1 on the broker)

| run | geometry | result |
|---|---|---|
| `run1_43mT` | a=5 cm, coils z=±4 cm, 4 kA-turn (43 mT), on-axis beam ±20° | 0% confined; losses split point/ring cusps, e-fold ~0.2 µs at 10-30 eV |
| `run2_1T_onaxis` | a=25 cm, coils z=±20 cm, 400 kA-turn (0.86 T at the point cusp), on-axis beam | 0% confined, 99% out the ring cusp in one transit |
| `run3_1T_sweep` | a=25 cm, coils z=±10 cm, 300 kA-turn (0.44 T point / 1.05 T ring cusp), beam, r_inj x pitch sweep | 0% confined; pitch 20-60° reflects at the ring cusp, then exits the point cusp it came in |
| `run4_1T_inside` | same field, isotropic electrons born in a 5 cm ball at the null, 10 eV - 30 keV | see `results/run4_1T_inside/report.png` |
| `run5_23kA_spacecharge` | 2015 geometry: a=10 cm, coils z=±5 cm, 23 kA-turn (99 mT axis), beam at r=14 mm, 100 eV-1 keV, central charge -1.4e-9..+1e-9 C (−940..+670 V); Boris + adaptive | 0% confined in every member: the beam rides its field line from the point cusp straight out the ring cusp in one transit (8 ns at 1 keV), regardless of the central charge - it never comes within a few cm of the sphere. See `traj_*.png`. |
| `run7_corrected_well` | inside-born controls, 16 members, 200k each, 100 µs; prescribed charge well -3e-9..+1e-8 C at 30-1000 eV | see corrected interpretation in `docs/reassessment.md`; summaries + report in `results/run7_corrected_well/` |

## What the runs say

The tested beam configurations lost their particles; this does not prove a general impossibility of capture
in static fields. The production target is an external electron gun crossing field lines, with its origin
and aim explicitly specified. Inside-born populations are numerical controls. Strong positive-charge cases
can be energetically bound even without B and are not evidence of a self-generated negative potential well for positive ions. See
[the reassessment](docs/reassessment.md) for the corrected interpretation, measured performance, and staged
simulation plan.

## Convergence (CPU, inside-born 100 eV, 400 electrons, seed 7, 0.5 µs)

| integrator | adaptive | dt / gyroperiod | confined | steps/particle |
|---|---|---|---|---|
| Boris | yes | 1/20 | 54.5% | 11k |
| Boris | yes | 1/40 | 56.3% | 22k |
| Boris | yes | 1/80 | 57.8% | 44k |
| RK4 | yes | 1/40 | 55.8% | 22k |
| Boris | fixed | 1/40 (of B_ref) | 55.3% | 174k |

This small ensemble is a preliminary comparison, not a completed convergence study. Separate timestep/grid
bias from sampling uncertainty. The original 50–100 Gparticle-steps/s values credited steps skipped after
escape and are invalid as executed-throughput measurements. Run 7 measures actual particle steps and reports
4.56–32.04 Gparticle-steps/s per B200 across different workloads; this is not a controlled kernel comparison.

## Still to do

- Loss-cone diagnostic: pitch angle at each null crossing (min |B| per particle is recorded now).
- A real φ(r,z) solve (biased grids at the cusps) and eventually self-consistent space charge (PIC).
