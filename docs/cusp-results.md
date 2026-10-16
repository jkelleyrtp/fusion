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

## 3. Size scan at fixed pressure ratio (2D picket fence): in progress, no conclusion

Deck `inputs_rz_picket_fed`, the geometry checked against Park et al. 2019 in [picket-park.md](picket-park.md),
at 0.25 to 4 times that paper's size measured in electron orbits. 100 keV electrons, ions of 64 electron masses
unless the name says otherwise, 50 electron crossings. In the names, `s…` is the size against the paper's,
`x…` the fill against that size's nominal fill, `k18` a sustaining feed of 1/18 of the filling feed (as in the
paper), `nr…` a finer mesh and `m…` the ion mass.

| Case | Coil radius in electron orbits at the edge | Pressure inside ÷ magnetic pressure outside | Holding time (electron crossings) | Change in number held over the last fifth | Current layer width (orbits at the fed temperature) | Gap stream half-height (mm) | Same, in electron orbits at the edge | Cells across the current layer |
|---|---|---|---|---|---|---|---|---|
| `ps_s0.25_k18` | 51 | 0.68 | 42 | −0.084 | 1.78 | 0.122 | 0.62 | 5.6 |
| `ps_s0.25_k18_nr384` | 51 | 0.66 | 39 | −0.104 | 1.86 | 0.130 | 0.67 | 22.5 |
| `ps_s0.25_x1.4_k18` | 58 | 0.71 | 44 | −0.080 | 1.91 | 0.137 | 0.79 | 5.3 |
| `ps_s0.25_x2.0_k18` | 70 | 0.64 | 45 | −0.074 | 1.81 | 0.151 | 1.06 | 4.5 |
| `ps_s0.5_k18` | 117 | 0.67 | 75 | −0.032 | 2.09 | 0.100 | 1.17 | 5.6 |
| `ps_s0.5_k18_nr384` | 116 | 0.61 | 64 | −0.050 | 1.98 | 0.106 | 1.23 | 11.4 |
| `ps_s0.5_x1.4_k18` | 133 | 0.66 | 79 | −0.026 | 1.99 | 0.124 | 1.65 | 5.3 |
| `ps_s0.5_x2.0_k18` | 153 | 0.67 | 82 | −0.016 | 2.27 | 0.154 | 2.36 | 5.0 |
| `ps_s0.5_k18_m16` | 79 | 0.68 | 54 | −0.052 | 1.92 | 0.070 | 0.55 | 6.6 |
| `ps_s0.5_k18_m256` (100 crossings) | 148 | 0.66 | 135 | +0.015 | 2.24 | 0.137 | 2.03 | 4.9 |
| `pf_x0.7` | 206 | 0.78 | 130 | −0.003 | 2.28 | 0.075 | 1.54 | 6.2 |
| `pf_x1.0` | 226 | 0.83 | 141 | +0.003 | 2.21 | 0.093 | 2.11 | 5.1 |
| `ps_s2_x0.5_k18` | 308 | 0.95 | 181 | +0.006 | 2.51 | 0.044 | 1.36 | 7.6 |
| `ps_s2_x0.7_k18` | 340 | 1.08 | 178 | +0.005 | 2.50 | 0.055 | 1.88 | 7.1 |
| `ps_s2_k18` | 364 | 1.07 | 183 | +0.007 | 2.82 | 0.060 | 2.19 | 6.9 |

What can be said now:
- The current layer stays 1.8 to 2.8 fed-temperature electron orbits wide over a factor of 7 in size.
- The gap stream gets narrower in millimetres as the device grows and wider in electron orbits, and at each
  size it widens with the fill. Because the pressure ratio is not the same across sizes (0.6 to 1.1), size and
  pressure are not yet separated.

What cannot:
- The 0.25× and 0.5× cases are still losing plasma at the end (the number held falls 3 to 10% over the last
  fifth), so their holding times are not steady values.
- The 4× cases, the longer runs, the seed repeat and most of the ion-mass and particle-count controls have not
  finished.
- "Gap stream half-height" is the half width at half maximum of the density profile across the gap, not a
  measure of the area the plasma leaves through.

## Not written up here

- Gun-fed runs: [gun-fed-cusp.md](gun-fed-cusp.md).
- The two-coil size scan in physical units (`z15` to `z60` in `sp2`): several of those runs were still filling
  when they ended, which inflates their holding times; they need longer runs before a table.
