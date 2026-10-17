# Cusp results so far

Status 2026-10-17. Tables here are read from the reduced tables in `warpx/results/`; the case names are the
`case` field there. Only finished cases appear. All runs: plasma born inside, fixed coil field, light ions, and
WarpX patches reviewed by no one but their author ([warpx-patches.md](warpx-patches.md)).

> **2026-10-17: read [wall-charge.md](wall-charge.md) first.** Every run in sections 1, 2 and 4 left charge at
> the conducting walls, a fault of the deposition settings we used. Repeats without it give holding times 14 to
> 43% lower in the smaller cases wherever the plasma pressure is near or above the magnetic pressure. Section 3
> is the size scan rerun without the fault; the exponents of the earlier scan (section 4) are withdrawn. The
> widths of the current layer and the widening of the leaks with pressure hold up in the cases repeated so far.

## 1. Raising the pressure widens the leaks (2D two-coil cusp)

Deck `inputs_rz_spindle_fed`, campaign `sp2`, 16 kA-turns, 1 cm coils, 10 keV electrons, ions of 57 electron
masses, cells of 0.04 mm.

| Case | Feed (per s) | Plasma pressure ÷ magnetic pressure in the gap | Holding time (ns) | Stream half-width, coil / gap (mm) |
|---|---|---|---|---|
| `s_16k_f1e21` | 1e21 | 0.12 | 8.5 | 1.0 / 0.6 |
| `s_16k_f1e22` | 1e22 | 1.8 | 16.0 | 1.2 / 1.0 |
| `s_16k_f3e22` | 3e22 | 3.7 | 17.9 | 1.8 / 1.8 |
| `s_16k_f1e23` | 1e23 | 8.0 | 23.7 | 2.3 / 3.7 |
| `s_16k_f1e24` | 1e24 | 37 | 19.5 | 5.4 / 7.7 |

- The leak streams widen as the pressure rises. Plugging would be the opposite.
- Holding time nearly triples up to a pressure ratio of about 8, then falls.
- Repeats of the 1e23 case: second seed 23.7 ns, half the mesh 24.8 ns.
- At the lowest pressure the gap stream's half-height is 0.60 mm, against an electron orbit there of 0.92 mm
  at the fed temperature.

## 2. At low pressure the six-coil cusp leaks at about the ion sound speed (3D)

Deck `inputs_3d_cusp_fed`, campaign `fed2`. Base case: 32 kA-turns, 1 cm coils, 10 keV electrons, ions of 57
electron masses, 1e22 per second fed at the centre, 128 cells across 5 cm; holding time 10.0 and 11.3 ns for two
sizes of the source (`g_rf0.15`, `g_rf0.6`). At 1e22 per second and 8 kA-turns or more, the measured pressure at the
coil openings is a few percent of the magnetic pressure or less.

| Change | Cases | Holding time (ns) | Goes as |
|---|---|---|---|
| Coil current 4 → 8 → 128 kA-turns | `g_f1e22_4k`, `_8k`, `_128k` | 6.0 → 7.3 → 19.4 | field^0.3 to 0.35 |
| Coils off | `g_f1e22_off` | 4.0 | |
| Electron temperature 2.5 → 40 keV | `g_te2500`, `g_te40k` | 22.2 → 5.3 | temperature^−0.5 |
| Ion mass 57 → 229 → 918 electron masses | base, `g_m229`, `g_m918` | 11 → 17.9 → 28.8 | mass^0.35 |
| Half the size at the same field | `g_half_16k` | 4.4 | size^1.3 |
| Four times the size at the same field | campaign `mg2` | 81.8 | size^1.45 |

- Holding time follows size ÷ ion sound speed; against coils off, the field slows the loss by 1.5 to 5× over a 32× range of current.
- The stream through a coil narrows from 8.4 to 1.4 mm over that range while the electron orbit there shrinks
  from 2.4 to 0.08 mm, and is 1.5 mm in the half-size device against 2.9 mm (1.6 mm at twice the mesh). The cells
  are 0.4 mm, so streams near that width are not resolved.
- Three cases reach a pressure ratio of 1 to 4 at the openings by feeding 30 to 100× faster at 8 and 16
  kA-turns; their holding times fall (7.3 → 5.8 → 2.8 ns at 8 kA-turns). A half-time-step repeat (32 kA-turns,
  3e23 per second) gives 11.1 against 10.4 ns.

## 3. Size scan with the wall correction (2D picket fence): three sizes so far

Campaign `pw1`, deck `inputs_rz_picket_fed` with `particles.crop_on_PEC_boundary=1` and
`algo.current_deposition=villasenor`. 100 keV electrons fed, ions of 64 electron masses, 0.25, 0.5 and 1 times
the size of Park et al. 2019, each at three fills (`h0.7`, `h1.0`, `h1.4`) and with a sustaining feed chosen per
size. Runs last 400 electron crossings except `pw_s0.25_h0.7` (200). The 2× and 4× sizes are running and are
not in the table.

| Case | Coil radius in electron orbits at the edge | Pressure inside ÷ magnetic pressure outside | Holding time (electron crossings) | Change in number held over the last fifth | Current layer width (orbits at the fed temperature) | Electron gap stream half-height (electron orbits at the edge) | Ion gap stream half-height (same unit) | Mean electron energy (keV) | Cells across the current layer |
|---|---|---|---|---|---|---|---|---|---|
| `pw_s0.25_h0.7` | 50 | 0.65 | 37 | −0.011 | 2.11 | 0.77 | 2.33 | 74 | 5.8 |
| `pw_s0.5_h0.7` | 85 | 0.63 | 69 | +0.014 | 2.41 | 0.46 | 1.53 | 77 | 7.3 |
| `pw_s1_h0.7` | 158 | 0.90 | 120 | +0.024 | 2.66 | 0.61 | 0.64 | 59 | 8.8 |
| `pw_s0.25_h1.0_long` | 56 | 0.63 | 34 | −0.007 | 2.10 | 1.01 | 2.75 | 71 | 5.2 |
| `pw_s0.5_h1.0` | 100 | 0.65 | 71 | +0.017 | 2.42 | 0.66 | 1.53 | 73 | 6.3 |
| `pw_s1_h1.0` | 191 | 0.87 | 142 | +0.063 | 2.84 | 0.79 | 0.90 | 73 | 7.5 |
| `pw_s0.25_h1.4_long` | 64 | 0.64 | 34 | −0.014 | 2.03 | 1.29 | 2.86 | 70 | 4.5 |
| `pw_s0.5_h1.4` | 118 | 0.67 | 75 | +0.021 | 2.31 | 0.96 | 1.63 | 69 | 5.7 |
| `pw_s1_h1.4` | 227 | 0.89 | 130 | +0.046 | 2.88 | 1.55 | 1.17 | 64 | 6.6 |

What the three sizes show:
- **Holding time in electron crossings rises about in proportion to the radius in electron orbits.** A fit of
  holding time against radius in orbits gives exponents of 1.01, 1.16 and 1.05 at the three fills (0.93, 1.17
  and 1.02 if the crossing time is taken at the measured electron energy instead of the fed temperature).
  Proportional to size is what a leak of fixed width in orbits would give. The uncorrected scan gave about 0.7.
- **The electron gap stream does not grow in electron orbits:** 1.0, 0.7, 0.8 orbits at fill 1.0, and no trend
  at the other fills. The ion stream, in the same unit, narrows from 2.3–2.9 to 0.6–1.2.
- **The current layer thickens slowly,** 2.1, 2.4, 2.8 fed-temperature orbits, about radius^0.2 to 0.3.
- Electric field energy is under 1% of the plasma energy and the charge imbalance under 0.1% in the 1× rows.

**Is this high pressure?** Yes, by the usual meanings, though the table's ratio stays below 1. On the plane of
the middle coil, at fill 1.0 (field of the coils alone computed from the coil formula; 17 October):

| Case | Field at 0.6 coil radii, coils alone → with plasma (T) | Field at 0.75 coil radii, coils alone → with plasma (T) | Pressure ÷ magnetic pressure of the field inside the plasma | Pressure ÷ magnetic pressure of the coils alone at the plasma edge | Pressure ÷ magnetic pressure just outside the edge (the table's ratio) |
|---|---|---|---|---|---|
| `pw_s0.25_h1.0_long` | 1.15 → 0.40 | 2.56 → 3.05 | 43 | 1.66 | 0.63 |
| `pw_s0.5_h1.0` | 2.25 → 0.46 | 5.25 → 6.75 | 117 | 1.77 | 0.65 |
| `pw_s0.5_h1.0_ppc4` | 2.25 → 0.29 | 5.25 → 6.49 | 68 | 1.56 | 0.69 |
| `pw_s1_h1.0` | 4.55 → 0.50 | 10.62 → 14.31 | 341 | 2.17 | 0.87 |

The plasma pushes the field out of its interior and piles it up outside its edge. The table's ratio compares
the pressure with that piled-up field, which is why it tops out near 1. The field is pushed out by a factor of
3 at the smallest size and 9 at the largest, so the three sizes are not in the same state.

What limits this:
- **Three sizes, a factor of 3.5 in radius.** The two larger sizes decide whether the exponent holds.
- **The pressure ratio is not matched:** 0.63–0.67 at the two smaller sizes, 0.87–0.90 at 1×.
- **The 1× cases are not steady at 400 crossings.** The number held is still rising 2 to 6% over the last fifth
  and the holding time with it: at fill 1.0 it is 117, 119, 129 and 141 crossings over 100–150, 150–200, 200–300
  and 300–400 crossings.
- **The result is not converged in particle number, so the exponent is not established.** `pw_s0.5_h1.0_ppc4`
  (four times the particles, about 880 per cell against 270) holds for 52.5 crossings against 71.3, with a
  1.83-orbit current layer against 2.42 and 66 keV electrons against 73. The two runs agree to 10 ns; after
  that the standard run gains plasma (1.36 → 1.71 × 10^15 electrons from 20 to 65 ns) and the finer one stays
  flat (1.24 → 1.27 × 10^15). The slow rise in the number held, here and at 1×, is therefore at least partly
  particle noise. The standard runs have about 320, 270 and 210 electrons per cell at 0.25×, 0.5× and 1×, so
  the error need not be the same at each size. `pw3_particles.txt` repeats all three sizes with more particles.
- Another seed changes little: `pw_s0.5_h1.0_seed2` gives 73.3 crossings and a 0.67-orbit gap stream against
  71.3 and 0.66.
- Ion mass, at 0.5×: 49.3, 71.3 and 110.2 crossings and a gap stream of 0.040, 0.066 and 0.146 mm at 16, 64
  and 256 electron masses. The gap stream goes as about mass^0.46.
- Half the time step (`pw_s0.5_h1.0_half_dt`) gives 55.9 crossings, a 2.17-orbit layer and a 0.74-orbit gap
  stream, and holds a flat 1.30 to 1.35 × 10^15 electrons. This is not a clean time-step test: the feed adds a
  fixed number of particles per cell per step, so the run ends with 1.65 times the baseline's particles (16.0
  against 9.7 million; `ppc4` ends with 31.3 million). Holding time against particles is 71.3, 55.9, 52.5 for
  9.7, 16.0, 31.3 million, which particle count alone could explain. `pw_s0.5_h1.0_half_dt_ppc0.5` (half the
  step with the baseline's particle count) separates the two and is running.
- The finer-mesh repeat is running.
- Against the uncorrected twins (`pm1`), holding time at 1× is higher, not lower: 123 → 142 at fill 1.0 and
  101 → 130 at fill 1.4. The uncorrected runs peak near 140 at 50 to 100 crossings and then fall as the wall
  layer grows.

## 4. Size scan before the wall correction (withdrawn)

Kept for the record. Deck `inputs_rz_picket_fed`, the geometry checked against Park et al. 2019 in [picket-park.md](picket-park.md),
at 0.25 to 4 times that paper's size measured in electron orbits. 100 keV electrons, ions of 64 electron masses
unless the name says otherwise, 50 electron crossings. In the names, `s…` is the size against the paper's,
`x…` the fill against that size's nominal fill, `k18` a sustaining feed of 1/18 of the filling feed (as in the
paper), `nr…` the mesh, `m…` the ion mass, `ppc4` four times the particles and `seed2` another seed.

| Case | Coil radius in electron orbits at the edge | Pressure inside ÷ magnetic pressure outside | Holding time (electron crossings) | Change in number held over the last fifth | Current layer width (orbits at the fed temperature) | Gap stream half-height (mm) | Same, in electron orbits at the edge | Cells across the current layer |
|---|---|---|---|---|---|---|---|---|
| `ps_s0.25_k18` | 51 | 0.68 | 42 | −0.084 | 1.78 | 0.122 | 0.62 | 5.6 |
| `ps_s0.25_k18_nr192` | 52 | 0.64 | 38 | −0.104 | 1.76 | 0.126 | 0.65 | 10.9 |
| `ps_s0.25_k18_nr384` | 51 | 0.66 | 39 | −0.104 | 1.86 | 0.130 | 0.67 | 22.5 |
| `ps_s0.25_x1.4_k18` | 58 | 0.71 | 44 | −0.080 | 1.91 | 0.137 | 0.79 | 5.3 |
| `ps_s0.25_x2.0_k18` | 70 | 0.64 | 45 | −0.074 | 1.81 | 0.151 | 1.06 | 4.5 |
| `ps_s0.5_k18` | 117 | 0.67 | 75 | −0.032 | 2.09 | 0.100 | 1.17 | 5.6 |
| `ps_s0.5_k18_seed2` | 117 | 0.68 | 78 | −0.031 | 1.92 | 0.097 | 1.13 | 5.2 |
| `ps_s0.5_k18_ppc4` | 121 | 0.64 | 64 | −0.051 | 2.21 | 0.106 | 1.29 | 5.5 |
| `ps_s0.5_k18_nr384` | 116 | 0.61 | 64 | −0.050 | 1.98 | 0.106 | 1.23 | 11.4 |
| `ps_s0.5_k9` | 125 | 0.68 | 72 | +0.016 | 1.99 | 0.115 | 1.43 | 5.1 |
| `ps_s0.5_k18_long` (100 crossings) | 107 | 0.70 | 110 | +0.023 | 2.08 | 0.091 | 0.97 | 5.9 |
| `ps_s0.5_x1.4_k18` | 133 | 0.66 | 79 | −0.026 | 1.99 | 0.124 | 1.65 | 5.3 |
| `ps_s0.5_x2.0_k18` | 153 | 0.67 | 82 | −0.016 | 2.27 | 0.154 | 2.36 | 5.0 |
| `ps_s0.5_k18_m16` | 79 | 0.68 | 54 | −0.052 | 1.92 | 0.070 | 0.55 | 6.6 |
| `ps_s0.5_k18_m256` (100 crossings) | 148 | 0.66 | 135 | +0.015 | 2.24 | 0.137 | 2.03 | 4.9 |
| `pf_x0.7` | 206 | 0.78 | 130 | −0.003 | 2.28 | 0.075 | 1.54 | 6.2 |
| `pf_x1.0` | 226 | 0.83 | 141 | +0.003 | 2.21 | 0.093 | 2.11 | 5.1 |
| `ps_s2_x0.5_k18` | 308 | 0.95 | 181 | +0.006 | 2.51 | 0.044 | 1.36 | 7.6 |
| `ps_s2_x0.7_k18` | 340 | 1.08 | 178 | +0.005 | 2.50 | 0.055 | 1.88 | 7.1 |
| `ps_s2_k18` | 364 | 1.07 | 183 | +0.007 | 2.82 | 0.060 | 2.19 | 6.9 |
| `ps_s2_k36` | 379 | 1.03 | 195 | −0.016 | 3.48 | 0.058 | 2.20 | 8.8 |
| `ps_s2_x0.7_k18_m16` | 257 | 1.20 | 125 | −0.013 | 2.14 | 0.025 | 0.65 | 7.1 |
| `ps_s4_k18` | 761 | 1.21 | 266 | +0.019 | 2.47 | 0.040 | 3.02 | 5.2 |
| `ps_s4_k72` | 717 | 1.15 | 267 | −0.020 | 5.45 | 0.039 | 2.83 | 13.1 |

What can be said now:
- **The current layer does not grow with the device.** With the paper's sustaining feed (`k18`) it is 1.8, 2.1,
  2.2, 2.8 and 2.5 fed-temperature electron orbits wide at 51, 117, 226, 364 and 761 orbits of radius.
- **The gap stream does grow in electron orbits, but slower than the device:** 0.6, 1.2, 2.1, 2.2 and 3.0 orbits
  at those sizes, about size^0.56, so as a fraction of the device it shrinks. It also widens with ion mass
  (0.55, 1.17, 2.03 orbits at 16, 64, 256 electron masses at 0.5×), about mass^0.47, which is how an ion orbit
  scales and not how an electron orbit does.
- **Holding time in electron crossings rises with size, about size^0.7** (39, 75, 141, 183, 266). A fixed leak
  width in orbits would give size^1.
- Repeats at 0.5×: another seed gives 78 crossings against 75; four times the particles and twice the mesh both
  give 64.

What cannot:
- **The exponents are not at fixed pressure ratio.** It rises from 0.66 at 0.25× to 1.2 at 4×, and at each size
  the gap stream widens with the fill.
- **The layer width at the large sizes depends on the sustaining feed.** A quarter of the feed at 4× (`k72`)
  gives 5.5 orbits against 2.5, and half the feed at 2× (`k36`) 3.5 against 2.8, with the holding time unchanged.
- **Fifty crossings is short of a holding time at every size above 0.25×.** The 0.25× and 0.5× cases lose 3 to
  10% of their plasma over the last fifth, and running 0.5× for 100 crossings gives 110 crossings against 75.
- "Gap stream half-height" is the half width at half maximum of the density profile across the gap, not a
  measure of the area the plasma leaves through.
- Cases still to finish: `ps_s2_x0.7_k18` at 16 and 256 electron masses is done only for 16; its long,
  four-times-particles and 256-mass repeats are running.

## Not written up here

- Gun-fed runs: [gun-fed-cusp.md](gun-fed-cusp.md).
- The two-coil size scan in physical units (`z15` to `z60` in `sp2`): several of those runs were still filling
  when they ended, which inflates their holding times; they need longer runs before a table.
