# Biconic cusp electron trap — GPU kinetic simulation

Single-particle (non-PIC) RK4 tracking of electrons in the static field of two coaxial
current rings with opposite polarity (a spindle / biconic cusp). Runs one sweep member
per GPU on a single node, writes compact results (subsampled tracked trajectories, per-electron
escape time + channel, survival curve, (r,z) density) and renders a report.

## Layout

| path | what |
|---|---|
| `cusp_sim.py` | simulator: exact loop field (elliptic integrals), fused CUDA RK4 kernel (torch `load_inline`), torch fallback |
| `cusp_viz.py` | `report.png` + `traj_<member>.png` + markdown summary table from a run directory |
| `jobs/*.yaml` | broker-submittable single-node RayJobs (`uv run train job submit jobs/<x>.yaml --cluster aws-usw2 --priority 1`) |
| `results/` | reports and summaries pulled back from the runs |

## GPU dispatch (shared B200 cluster)

Submit GPU work only through the slime job broker, from the research checkout:

```bash
cd /home/ubuntu/repos/research
uv run train gpus --cluster aws-usw2                       # check free capacity first
uv run train job list --cluster aws-usw2
uv run train job submit jobs/<name>.yaml --cluster aws-usw2 --priority 1
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
  `--space-charge-radius` at the null (linear E inside, Coulomb outside) - the fixed `c_sphere` from the 2015
  OpenCL code. Negative = trapped electron cloud / virtual cathode (decelerates and repels incoming electrons);
  positive = attractive well. It is a sweep axis like energy.
- Diagnostics per particle: escape time / channel, step count, minimum |B| seen (loss-cone proxy).
- Energy drift is reported per member.
- Loss channels: `-z` point cusp, `+z` point cusp, ring cusp / wall (`r > wall_fraction * a`).
- Injection modes: `cusp` (beam through the -z point cusp, ring of radius `inject_r`, pitch band) and
  `inside` (born in a ball around the null, pitch uniform in cos over the band; `0..180` = isotropic).

## Runs so far (all 1 node x 8 B200, priority 1 on the broker)

| run | geometry | result |
|---|---|---|
| `run1_43mT` | a=5 cm, coils z=±4 cm, 4 kA-turn (43 mT), on-axis beam ±20° | 0% confined; losses split point/ring cusps, e-fold ~0.2 µs at 10-30 eV |
| `run2_1T_onaxis` | a=25 cm, coils z=±20 cm, 400 kA-turn (0.86 T at the point cusp), on-axis beam | 0% confined, 99% out the ring cusp in one transit |
| `run3_1T_sweep` | a=25 cm, coils z=±10 cm, 300 kA-turn (0.44 T point / 1.05 T ring cusp), beam, r_inj x pitch sweep | 0% confined; pitch 20-60° reflects at the ring cusp, then exits the point cusp it came in |
| `run4_1T_inside` | same field, isotropic electrons born in a 5 cm ball at the null, 10 eV - 30 keV | see `results/run4_1T_inside/report.png` |
| `run5_23kA_spacecharge` | 2015 geometry: a=10 cm, coils z=±5 cm, 23 kA-turn (99 mT axis), beam at r=14 mm, 100 eV-1 keV, central charge -1.4e-9..+1e-9 C (−940..+670 V); Boris + adaptive | 0% confined in every member: the beam rides its field line from the point cusp straight out the ring cusp in one transit (8 ns at 1 keV), regardless of the central charge - it never comes within a few cm of the sphere. See `traj_*.png`. |

## What the runs say

1. **An injected beam cannot be trapped by a static B field alone.** Motion is time-reversible and μ is
   (nearly) conserved: whatever mirror ratio a particle sees on the way in, it sees on the way out, so a beam
   that enters through the point cusp leaves through either the ring cusp (if its pitch is inside the ring-cusp
   loss cone) or back through the point cusp. Run 2 also had the wrong aspect ratio (coils too far apart:
   ring-cusp B < point-cusp B, so the ring cusp is the *weaker* mirror). Trapping a beam needs
   non-adiabatic scattering at the null (large r_L / L_B, i.e. weak field or high energy - opposite of what
   helps confinement), collisions, or a time-dependent / electrostatic field.
2. **Electrons that start inside** are confined until they diffuse into a loss cone. With B ~ 1 T the loss
   cones are geometric (fraction ~ 1/mirror ratio) and the remaining population is held for the whole run at
   low energy; at high energy the null region scatters pitch angle each pass and the trap leaks.
3. Field strength and size help through `r_L / L_B` (adiabaticity), not by themselves: what matters is
   `d/a` (ring-cusp vs point-cusp mirror ratio), the ring-cusp aperture in gyroradii, and the energy.
4. **Run 5, the 2015 configuration with the space-charge sphere, does not trap a 14 mm beam either.** At
   sep = a the ring-cusp field at the wall is only ~2x the axis field, so a 0-10° beam is deep inside the loss
   cone and exits at z=0 on its first pass; the central sphere is irrelevant because the field line from
   r=14 mm never approaches the centre. The old code's "long confinement" almost certainly came from members
   with much smaller `inject_r` (0.5-1 mm, lines that pass close to the null and see the sphere) and/or the
   different E-field formula in `trajectory_conf.cl`. Next sweep: `inject_r` 0.5-5 mm x charge, and
   `--inject-mode inside` with a positive well.

## Convergence (CPU, inside-born 100 eV, 400 electrons, seed 7, 0.5 µs)

| integrator | adaptive | dt / gyroperiod | confined | steps/particle |
|---|---|---|---|---|
| Boris | yes | 1/20 | 54.5% | 11k |
| Boris | yes | 1/40 | 56.3% | 22k |
| Boris | yes | 1/80 | 57.8% | 44k |
| RK4 | yes | 1/40 | 55.8% | 22k |
| Boris | fixed | 1/40 (of B_ref) | 55.3% | 174k |

The ~1-2% spread is at the level of counting noise for 400 particles (±2.5%); adaptive Boris at 1/40 is the
default. On a B200 the adaptive kernel does ~20 Gparticle-steps/s (per-particle step counts diverge, so
warps are less uniform than fixed-step RK4's 50-100 G/s, but 8x fewer steps).

## Still to do

- Loss-cone diagnostic: pitch angle at each null crossing (min |B| per particle is recorded now).
- A real φ(r,z) solve (biased grids at the cusps) and eventually self-consistent space charge (PIC).
