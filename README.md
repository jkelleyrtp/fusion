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

## Physics model

- Field: Smythe's closed form for a circular filament, `B_r, B_z` in `K(k), E(k)` (AGM), tabulated on an
  (r,z) grid once per member; the kernel does bilinear lookups. Validated against the on-axis formula (1e-15)
  and a 2880-segment Biot-Savart polygon (6e-6).
- Pusher: classic RK4 on `dv/dt = (q/m) v x B`, fixed `dt = gyroperiod(B_ref)/40`. Energy drift is reported
  per member (typ. 1e-5 over 1e7-1e8 steps).
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

## Easy improvements (not done yet)

- Boris pusher as the production integrator (exactly energy-conserving, 4x cheaper per step than RK4);
  keep RK4 as the reference.
- Adaptive `dt` from the local `|B|` (electrons near the coils are stepping 10x finer than needed elsewhere).
- Electrostatic potential: add a fixed φ(r,z) (e.g. a biased grid at the point cusps) - that is the actual
  "potential well" experiment and needs only an E lookup in the kernel.
- Loss-cone diagnostic: record pitch angle at the null crossings so the trapped/passing boundary can be plotted
  directly versus energy.
- Convergence checks in the harness: `dt`, grid resolution, particle count.
