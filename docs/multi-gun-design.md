# Multi-gun electron injection (six-coil)

## Motivation

Every high-feed campaign so far uses one electron gun on the −z face axis. At 10 keV, 100 A
builds a −15 to −23 kV virtual cathode at the gun mouth and the beam barely reaches the centre
(`six-coil-feed-fine`). The gun-limit campaign tests energy, divergence and casing bias on that
single gun. The other lever is to split the same total current over several guns so each gun
carries a lower perveance, as practical Polywell designs do with several emitters.

## Geometry

`--guns N` with N in {1, 2, 3, 6} places copies of the existing gun on the six face-axis point
cusps of the six-coil cube, in this order: z−, z+, x−, x+, y−, y+ for N = 2 and 6, and z−, x−, y−
for N = 3. Each copy is the reference gun (emitter at (0, 0.008a, −1.3a), aimed
(0, −sin θ, cos θ)) transformed by a proper rotation of the cube:

| face | map (x, y, z) → |
|---|---|
| z− | (x, y, z) |
| z+ | (x, −y, −z) |
| x− | (z, x, y) |
| x+ | (−z, x, −y) |
| y− | (y, z, x) |
| y+ | (−y, −z, x) |

The six-coil field has this symmetry, so each gun sees the same local field and pitch as the
reference gun. The box is not symmetric (deeper bottom), which is a real difference between faces
and is recorded. With `--gun-radius`, each gun gets its own grounded absorbing barrel, the same
rotated cylinder as the reference barrel. `N > 1` requires `--coils 6`.

## Sampling and accounting

- Particle packets keep `--inject-per-step` macroparticles, which must be divisible by N; each
  packet holds `inject_per_step / N` from every gun, so the total current and the macroparticle
  weight are unchanged and each gun carries `current / N`.
- Gun 0 uses the existing seed stream (`SeedSequence([seed, block])`), so `--guns 1` reproduces
  the current sampler exactly. Gun k > 0 uses `SeedSequence([seed, block, k])`.
- Samples are drawn in the reference frame (including the backwards-velocity check) and then
  rotated, so the emitter spot, thermal spread and divergence are identical for every gun.
- Conductor names become `gun_barrel_<face>` for N > 1 (`gun_barrel` for N = 1); ion and electron
  exit counts therefore separate each barrel. `source_potential_V` stays the z− gun; the
  configuration records every origin, direction and barrel.

## Limits

- Guns are identical and share one current waveform and pulse schedule.
- No new physics: this changes source placement only; the pusher, deposition and field solves are
  untouched.
- Six guns on face cusps is one design choice; corner-cusp or off-axis emitters are not covered.
- The mesh spacing is coarser along z than across it, so the x and y barrels resolve onto fewer
  conductor nodes than the z barrels; `gun_barrels[].nodes` records the counts.

## Campaign `six-coil-multi-gun`

Coupled electron and H2+ PIC, 30 kA-turn, H2 at 1e-3 Pa, 32 × 10 µs cycles, 12 macroparticles per
packet, 0.5 ns ion steps unless noted. Compared against the one-gun `feed_*_p1e-3` and
`limit_*` cases.

| case | guns | total current | energy | notes |
|---|---|---|---|---|
| guns6_30A_10keV | 6 | 30 A | 10 keV | vs one-gun 30 A |
| guns6_100A_10keV | 6 | 100 A | 10 keV | vs one-gun 100 A choke |
| guns6_100A_10keV_s2345 | 6 | 100 A | 10 keV | second seed |
| guns3_100A_10keV | 3 | 100 A | 10 keV | |
| guns2_100A_10keV | 2 | 100 A | 10 keV | |
| guns6_300A_10keV | 6 | 300 A | 10 keV | 0.2 ns ion steps |
| guns6_300A_20keV | 6 | 300 A | 20 keV | 0.2 ns ion steps |
| guns6_1000A_20keV | 6 | 1000 A | 20 keV | 0.2 ns ion steps |

At the highest feeds the electron Debye length can fall below the mesh spacing; those cases need a
refinement check before their well depth is trusted.

## Campaign `six-coil-multi-gun-check`

Job `jonathan-pic-3228957e6203`, source `b6ba5d6`, submitted while `six-coil-multi-gun` was at
cycles 8–17. Mid-run histories showed the multi-gun wells reaching −7 to −28 kV at the origin, but
with only 18k–240k live electron macroparticles (378 in the core at 1000 A), so particle noise and
mesh resolution both need checking before the depths are used. Each case reuses its base case's
guns, current, energy, seed and ion step.

| case | base | change |
|---|---|---|
| guns6_100A_10keV_n97 | guns6_100A_10keV | 97-node mesh, 16 cycles |
| guns6_1000A_20keV_n97 | guns6_1000A_20keV | 97-node mesh, 16 cycles |
| guns6_100A_10keV_ppc4 | guns6_100A_10keV | 48 macroparticles per packet, 16 cycles |
| guns6_1000A_20keV_ppc4 | guns6_1000A_20keV | 48 macroparticles per packet, 16 cycles |
| guns6_100A_10keV_cycle5 | guns6_100A_10keV | 5 µs cycles, 64 cycles |
| guns6_100A_10keV_p1e-4 | guns6_100A_10keV | 1e-4 Pa, 16 × 100 µs cycles |
| guns6_1000A_20keV_p1e-4 | guns6_1000A_20keV | 1e-4 Pa, 8 × 100 µs cycles |
| guns6_100A_10keV_60kAt | guns6_100A_10keV | 60 kA-turn coils |

Comparisons use the base case's history at the same simulated time, since the 16-cycle checks stop
halfway through the base run.

Three cases failed at startup and produced no data:

- **n97 (both):** CUDA out of memory building the conductor capacitance matrix. The 97-node mesh has
  139k held conductor surface nodes, so one dense FP64 copy is 117 GiB and the Cholesky inverse needs
  three. Probing the next valid finer mesh (81 nodes, 87k surface nodes, 56 GiB per copy) also rules it
  out: cuSOLVER `potrf` fails with `CUSOLVER_STATUS_INTERNAL_ERROR` above ~65.5k rows (65,000 passes,
  66,000 fails), which reads as a 2^32-element internal limit. Mesh sizes must keep whole reference cells
  (nodes − 1 a multiple of 16: 49, 65, 81, 97), so 65 nodes is the finest mesh the dense conductor
  path supports. Refining further needs a factorization that is blocked or matrix-free.
- **60kAt:** `Timestep requires at least 80 steps per gyration`. The 2 ps electron step gives
  \|q/m\| B_max dt = 0.114 at 60 kA-turn against a limit of 2π/80 = 0.0785.

## Campaign `six-coil-multi-gun-scale`

Replaces the failed check cases and extends the feed. Six guns, H2 at 1e-3 Pa, 10 µs cycles, 12
macroparticles per packet.

| case | current | energy | change |
|---|---|---|---|
| guns6_100A_10keV_n49 | 100 A | 10 keV | 49-node mesh (coarser), 16 cycles |
| guns6_1000A_20keV_n49 | 1000 A | 20 keV | 49-node mesh, 16 cycles |
| guns6_3000A_20keV_n49 | 3000 A | 20 keV | 49-node mesh, 0.1 ns ion step, 16 cycles |
| guns6_100A_10keV_60kAt | 100 A | 10 keV | 60 kA-turn, 1 ps electron step, 16 cycles |
| guns6_1000A_20keV_60kAt | 1000 A | 20 keV | 60 kA-turn, 1 ps electron step, 16 cycles |
| guns6_1000A_20keV_s2345 | 1000 A | 20 keV | second seed, 32 cycles |
| guns6_100A_20keV | 100 A | 20 keV | energy at matched current, 32 cycles |
| guns6_3000A_20keV | 3000 A | 20 keV | 0.1 ns ion step, 16 cycles |

The mesh check coarsens rather than refines: the 49 → 65 change bounds the 65-node discretization error
only if the trend is monotone, and it is weaker evidence than a finer mesh. The 1 ps runs keep 4 ps
packets, so injected current is unchanged. At 3000 A each gun carries 500 A at 20 keV, 1.8e-4 A/V^1.5,
above the single-gun choke estimate of ~1e-4; that tests whether six guns hold off the choke at the
same per-gun perveance.
