# Cusp results so far

Status 2026-10-16. Tables here are read from the reduced tables in `warpx/results/`; the case names are the
`case` field there. Only finished cases appear. All runs: plasma born inside, fixed coil field, light ions, and
WarpX patches reviewed by no one but their author ([warpx-patches.md](warpx-patches.md)).

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

## 3. Size scan (2D picket fence): 51 to 761 electron orbits, pressure ratio not yet matched

Deck `inputs_rz_picket_fed`, the geometry checked against Park et al. 2019 in [picket-park.md](picket-park.md),
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
