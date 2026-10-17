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

**Where the scan stands (17 October, 14:30 UTC).** The table above is at the baseline particle count, which
is too low at 0.5× and 1× (below). Best finished case at each size, middle fill:

| Size | Case | Particles against the table above | Coil radius (electron orbits) | Holding time (electron crossings) | Change over the last fifth | Current layer (orbits) | Electron gap stream (orbits) | Standing |
|---|---|---|---|---|---|---|---|---|
| 0.25× | `pw_s0.25_h1.0_long_ppc8` | 4× | 56 | 34.2 | +0.8% | 2.06 | 1.07 | same at 1×, 4× and 16× the particles, and on a mesh twice as fine (`pw_s0.25_h1.0_long_nr192`: 34.0 crossings, layer 1.88, gap stream 1.11) |
| 0.5× | `pw_s0.5_h1.0_ppc4`, `_ppc4_seed2`, `_nr384_ppc2`, `_ppc16`, `_ppc4_long` | 4× to 16× | 96 to 103 | 52.5 to 58.2 | +0.2 to +4.9% | 1.83 to 2.10 | 0.78 to 0.87 | same on two meshes; 11% spread; at twice the length 54.3 and flat (+0.2%) |
| 1× | `pw_s1_h1.0_ppc2` | 4× | 216 | 113.9 | +5.6% | 2.76 | 1.19 | not settled; 16× running |
| 2× | `pw_s2_h1.0` | 1× | 396 | 179.3 | +0.2% | 3.08 | 1.64 | baseline particles only: an upper limit |

- Between 0.25× and 0.5× the holding time goes as radius^0.7 to 0.9, and between 0.5× and 1× as radius^0.9 to
  1.0 if the 1× number stands. With four smoothing passes at all three sizes (32.8, 50.7, 100.2 crossings at
  54, 95 and 210 orbits) the same two steps give 0.77 and 0.86. Neither is a result yet: the 1× case is still
  gaining plasma and is not shown to have enough particles.
- The current layer is 2.0 orbits at 0.25× and 0.5×, 2.8 at 1× and 3.1 at 2×. The electron gap stream is 1.1,
  0.8, 1.2 and 1.6 orbits. Both are wider at the two larger sizes; over a factor of 7 in size that is about
  size^0.2, far slower than the device.
- The pressure ratio is 0.63, 0.69 to 0.75, 0.76 and 1.05 from the smallest size up, so the sizes are still not
  in the same state.
- The electron gap stream is about one cell thick on the standard meshes (0.8 to 1.4 cells), which made it the
  least trusted width here. Halving the cell leaves it where it was in millimetres: 0.192 → 0.195 mm at 0.25×
  (`_ppc8` against `_nr192`) and 0.082 → 0.084 mm at 0.5× (`_ppc4` against `_nr384_ppc2`). So at the two
  smaller sizes the width is not set by the mesh. No finer-mesh case exists at 1× or 2×.
- **Fill at 0.5× with four times the particles (17 October, 16:50 UTC).** `pw_s0.5_h0.7_ppc4`,
  `pw_s0.5_h1.0_ppc4` and `pw_s0.5_h1.4_ppc4` give 52.0, 52.5 and 79.0 crossings, holding 0.87, 1.27 and
  2.42 ×10^15 electrons. The two lower fills are settled (+1.8% and +1.0% over the last fifth) and agree, so
  between them the holding time does not depend on how full the device is. The highest fill is not settled: it
  gains 11% over the last fifth, its magnetic field energy rises from about 4.5 to 11 J through the run, and
  its electrons heat to 85 keV against 66 to 70 keV in the other two. Its 79 is not a result. The same case
  for twice the length is queued (`pw16_fill_at_converged_particles.txt`), with the two outer fills at 0.25× at
  four times the particles.
- **Twice the length at 0.5× (17:50 UTC).** `pw_s0.5_h1.0_ppc4_long` runs to 800 crossings and gives 54.3,
  with +0.2% over its last fifth. It holds 1.24, 1.28, 1.30 and 1.32 ×10^15 electrons at 20, 66, 100 and
  131 ns: a gain of 6% over 110 ns that has stopped by the end. So the middle size is settled near 54.
- **Fill at 0.25× with four times the particles.** `pw_s0.25_h0.7_long_ppc8` gives 34.2 crossings, the same as
  fill 1.0 (34.2); fill 1.4 gives 33.6 (`pw_s0.25_h1.4_long_ppc8`; 34.2 at the baseline count). The radius in electron
  orbits at the plasma edge is 49, 56 and 64 in those three, because a fuller plasma sits against a stronger
  field. So at one physical size the holding time does not follow that number; it is a poor size axis, and the
  scan should be read against the physical size.
- **2× at the highest fill, baseline particles:** `pw_s2_h1.4` gives 179.3 crossings, the same as fill 1.0,
  and both are flat over the last fifth. Still an upper limit until `pw_s2_h1.0_ppc1` finishes.
- **Sizes in between (queued 18:24 UTC, `pw17_sizes_between.txt`):** 0.125×, 0.375× and 0.75× at the particles
  per cell of the four-times cases, with the sustaining feed interpolated between the neighbouring sizes.
  They test whether the step from 0.25× to 0.5× (1.6 times the holding time) carries on above and below.

What the three sizes show at the baseline particle count:
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
  flat (1.24 → 1.27 × 10^15). The slow rise in the number held, here and at 1×, therefore depends on a
  numerical setting; the table below shows it is not simply fewer particles. The standard runs have about 320, 270 and 210 electrons per cell at 0.25×, 0.5× and 1×, so
  the error need not be the same at each size. `pw3_particles.txt` repeats all three sizes with more particles.
- Another seed changes little: `pw_s0.5_h1.0_seed2` gives 73.3 crossings and a 0.67-orbit gap stream against
  71.3 and 0.66.
- Ion mass, at 0.5×, at the baseline particle count: 49.3, 71.3 and 110.2 crossings and a gap stream of 0.040,
  0.066 and 0.146 mm at 16, 64 and 256 electron masses, about mass^0.46. **That exponent does not survive more
  particles.** With four times the particles (`pw_s0.5_h1.0_m16_ppc4`, `_ppc4`, `_m256_ppc4`; 17 October):

  | Ion mass (electron masses) | Holding time (electron crossings) | Change over the last fifth | Electron gap stream (mm) | Ion gap stream (mm) | Current layer (mm) | Electron orbit at the edge (mm) | Electron gap stream (orbits at the edge) | Electron / ion energy (keV) |
  |---|---|---|---|---|---|---|---|---|
  | 16 | 33.2 | +0.9% | 0.075 | 0.228 | 0.59 | 0.149 | 0.50 | 84 / 108 |
  | 64 | 52.5 | +1.0% | 0.082 | 0.232 | 0.48 | 0.104 | 0.79 | 66 / 120 |
  | 256 | 95.5 | +3.5% | 0.121 | 0.248 | 0.34 | 0.068 | 1.79 | 51 / 136 |

  - In millimetres the electron stream goes as mass^0.17 (0.06 from 16 to 64, 0.28 from 64 to 256) and the ion
    stream as mass^0.03. The ion orbit at the edge grows 2.6 times over this range (0.68, 1.12, 1.76 mm from
    the columns above), so neither stream follows it.
  - In electron orbits at the edge the electron stream still goes as mass^0.46, but that is the orbit
    shrinking, not the stream widening: the heavier-ion plasma holds 2.8 times as much, sits against a stronger
    field and has colder electrons.
  - The holding time goes as mass^0.38 (0.33, then 0.43). A stream of fixed width emptied at the ion speed
    would give mass^0.5; with the measured widths, mass^0.33 to 0.47. So the reading that fits is a hole of
    nearly fixed size that plasma leaves through at the speed of its ions, not a hole an ion orbit wide.
  - The baseline count overstated the holding time by 49%, 36% and 15% at 16, 64 and 256 electron masses.
    Only the middle mass has a 16× repeat; `pw_s0.5_h1.0_m16_ppc16` is running.
- Numerical repeats at 0.5× split into two groups, and we do not know why (17 October):

  | Case | Cells across the radius | Time step | Electrons per cell ÷ baseline's | Holding time (electron crossings) | Electrons held at 20 → 65.9 ns (10^15) | Current layer (orbits) | Gap stream (orbits) |
  |---|---|---|---|---|---|---|---|
  | `pw_s0.5_h1.0` | 192 | 0.156 ps | 1 | 71.3 | 1.36 → 1.71 | 2.42 | 0.66 |
  | `pw_s0.5_h1.0_seed2` | 192 | 0.156 ps | 1 | 73.3 | 1.36 → 1.75 | 2.43 | 0.67 |
  | `pw_s0.5_h1.0_nr384` | 384 | 0.078 ps | 0.5 | 72.2 | 1.34 → 1.72 | 2.12 | 0.75 |
  | `pw_s0.5_h1.0_half_dt` | 192 | 0.078 ps | 1.6 to 1.9 | 55.9 | 1.27 → 1.35 | 2.17 | 0.74 |
  | `pw_s0.5_h1.0_ppc4` | 192 | 0.156 ps | 3.2 to 4.8 | 52.5 | 1.24 → 1.27 | 1.83 | 0.79 |

  - All five agree to 10 ns. The first three then gain plasma; the last two stay flat.
  - Neither the time step nor the mesh separates the groups: `nr384` has half the step and twice the mesh and
    reproduces the baseline.
  - One number does order all of them (found 17 October, 10:10 UTC, after `pw_s0.5_h1.0_ppc2` finished): the
    count of simulation electrons within one screening length or one cell of each other, whichever is larger,
    `N_c = (electrons per unit area of the r-z plane at half the coil radius) × (screening length² + cell²)`.
    It sets how often simulation particles scatter off each other, which real particles at this density and
    temperature do about a hundred thousand times less often (textbook estimates of both rates, not measured). The finer mesh has smaller cells and fewer particles per cell,
    and the two cancel.

    | Case | `N_c` | Holding time (electron crossings) | Electrons held at the end ÷ most held |
    |---|---|---|---|
    | `pw_s0.5_h1.0` | 564 | 71.3 | 0.85 |
    | `pw_s0.5_h1.0_seed2` | 583 | 73.3 | 0.87 |
    | `pw_s0.5_h1.0_nr384` | 616 | 72.2 | 0.86 |
    | `pw_s0.5_h1.0_half_dt` | 942 | 55.9 | 0.67 |
    | `pw_s0.5_h1.0_ppc2` | 1002 | 60.2 | 0.72 |
    | `pw_s0.5_h1.0_ppc4` | 1942 | 52.5 | 0.63 |

  - A straight line in `1/N_c` through the first and last rows gives 45 crossings with no scattering between
    simulation particles. This is an inference from six runs, not a result.
  - Predictions written before the runs finish: `pw_s0.5_h1.0_ppc16` (`N_c` about 7500) 46 to 48;
    `pw_s0.5_h1.0_nr384_ppc2` (about 2100) 50 to 54; `pw_s0.5_h1.0_half_dt_ppc0.5` (about 500) 70 to 75.
    If these fail, the explanation is wrong.
  - Outcome so far (17 October, 10:40 UTC). One of the three is complete and holds:
    `pw_s0.5_h1.0_half_dt_ppc0.5` gives 71.2 crossings (`N_c` about 500). Halving the time step at a fixed
    particle count changes nothing, so the 55.9 of `pw_s0.5_h1.0_half_dt` came from its extra particles.
  - The 16-times-particle prediction failed (complete 17 October, 13:20 UTC): `pw_s0.5_h1.0_ppc16` gives 58.2
    crossings, not 46 to 48, so the straight line in `1/N_c` and its 45 crossings are wrong. The runs with four
    or more times the baseline's particles, all complete:

    | Case | `N_c` | Holding time (electron crossings) | Electrons held at 30 → 65 ns (10^15) | Change over the last fifth | Current layer (orbits) | Gap stream, electrons / ions (orbits) |
    |---|---|---|---|---|---|---|
    | `pw_s0.5_h1.0_ppc4` | 1871 | 52.5 | 1.232 → 1.270 | +1.0% | 1.83 | 0.79 / 2.23 |
    | `pw_s0.5_h1.0_ppc4_seed2` | 1888 | 54.7 | 1.248 → 1.325 | +2.4% | 1.93 | 0.78 / 2.21 |
    | `pw_s0.5_h1.0_ppc4_smooth4` (four smoothing passes) | 1956 | 52.8 | 1.168 → 1.274 | +3.5% | 1.96 | 0.63 / 2.55 |
    | `pw_s0.5_h1.0_ppc16` | 8446 | 58.2 | 1.270 → 1.390 | +4.9% | 2.02 | 0.87 / 2.28 |

    - The holding time at 0.5× with enough particles is 52 to 58 crossings, against 71 to 73 at the baseline
      count. Two seeds at four times the particles differ by 4%.
    - None of these is flat. They gain 1 to 5% over the last fifth, the most in the run with the most
      particles. So part of the slow gain is not noise, and "more particles stop it" (said of `ppc4` alone) was
      wrong: more particles cut it from 26% between 20 and 65 ns to 2 to 9%.
    - Four smoothing passes on top of four times the particles leaves the holding time where it was (52.8
      against 52.5 and 54.7) and thins the electron gap stream (0.63 against 0.78 to 0.79 orbits).
    - `pw_s0.5_h1.0_nr384_ppc2` is still running.
    - The finer mesh with four times its particles, `pw_s0.5_h1.0_nr384_ppc2` (`N_c` 2210), gives 56.2
      crossings, a 1.93-orbit layer and an electron gap stream of 0.86 orbits, inside the range of the runs
      above. So at 0.5× the many-particle answer does not depend on the mesh.
  - At 1× (complete 17 October, 14:25 UTC), four times the particles and four smoothing passes both lower the
    holding time, by different amounts, and the first has not settled:

    | Case | `N_c` | Holding time (electron crossings) | Electrons held at 30 → 65 ns (10^15) | Change over the last fifth | Pressure inside ÷ magnetic pressure outside | Current layer (orbits) | Gap stream, electrons / ions (orbits) |
    |---|---|---|---|---|---|---|---|
    | `pw_s1_h1.0` | about 340 | 141.8 | 7.37 → 8.63 | +6.3% | 0.87 | 2.84 | 0.79 / 0.90 |
    | `pw_s1_h1.0_ppc2` (four times the particles) | 1372 | 113.9 | 6.10 → 7.10 | +5.6% | 0.76 | 2.76 | 1.19 / 1.50 |
    | `pw_s1_h1.0_smooth4` | 298 | 100.2 | 6.17 → 6.49 | +1.5% | 0.82 | 2.75 | 0.86 / 1.27 |

    `pw_s1_h1.0_ppc2` gains plasma as fast as the baseline (14% between 30 and 60 ns in both), from a level 17%
    lower. `pw_s1_h1.0_ppc8_half` (16 times the particles, 200 crossings) is running to say whether four
    times is enough here.
  - It does not explain 0.25×, where `N_c` of 610, 2591 and 10561 gives 33.9, 34.2 and 35.4 crossings. The 0.25×
    runs last half as many plasma oscillations as 0.5× and a quarter as many per holding time; whether that is
    enough to remove the effect is not shown.
  - By the same count, the 1× cases (`N_c` 330 to 450, 2.4 times the plasma oscillations of 0.5×) should be
    affected more than 0.5×, which would make the measured growth of holding time with size too steep.
  - Adding real collisions does not reproduce the baseline (complete 17 October). `pw_s0.5_h1.0_ppc4_clog1e6`,
    `_clog4e6` and `_clog1.6e7` add WarpX's Coulomb collisions with a chosen logarithm (deck
    `inputs_rz_picket_fed_collisions`) to the four-times-particle case:

    | Coulomb logarithm | Holding time (electron crossings) | Pressure inside ÷ magnetic pressure outside | Current layer (orbits) | Mean energy, electrons / ions (keV) | Change over the last fifth |
    |---|---|---|---|---|---|
    | none (`pw_s0.5_h1.0_ppc4`) | 52.5 | 0.69 | 1.83 | 66 / 120 | +1.0% |
    | 1e6 | 45.3 | 0.32 | 2.72 | 77 / 139 | 0.0% |
    | 4e6 | 76.1 | 0.26 | 5.65 | 172 / 110 | +15.5% |
    | 1.6e7 | 54.1 | 0.03 | 8.32 | 153 / 143 | +13.3% |

    The weakest setting lowers the holding time and spreads the boundary. The two stronger ones dissolve the
    boundary (pressure ratio 0.26 and 0.03, a layer of 6 to 8 orbits), heat the electrons to 150 to 170 keV
    from a 100 keV feed and have not settled, so they are a different plasma and their holding times do not
    compare. None of them looks like the baseline, which keeps a 2.4-orbit layer and 73 keV electrons. So
    whatever too few particles does, it is not what pair collisions do, even though `N_c` orders the runs.
  - No run before 17 October 10:40 UTC smoothed its currents. WarpX turns smoothing off in this geometry unless
    `warpx.use_filter=1` is given, and the deck's `warpx.filter_npass_each_dir = 0 1` did nothing without it
    (checked locally: 1, 4 and 16 passes give identical output without the switch, different output with it).
    Smoothing along the radius is refused outright, so these runs smooth along z only.
  - Smoothing the currents lowers the holding time, and keeps lowering it with more passes, so it is not a
    substitute for particles (17 October, 12:25 UTC; every row complete). `smooth1`, `smooth4` and `smooth16`
    are one, four and sixteen passes along z; `shape3` is wider particles with no smoothing.

    | Case | Holding time (electron crossings) | Electrons held, late mean (10^15) | Change over the last fifth | Mean energy, electrons / ions (keV) | Current layer (orbits) | Gap stream, electrons / ions (electron orbits) | Field energy ÷ plasma energy | Ions minus electrons ÷ electrons |
    |---|---|---|---|---|---|---|---|---|
    | `pw_s0.5_h1.0` | 71.3 | 1.705 | +1.7% | 73 / 97 | 2.42 | 0.66 / 1.53 | | |
    | `pw_s0.5_h1.0_shape3` | 66.1 | 1.559 | +3.0% | 71 / 103 | 2.34 | 0.61 / 1.70 | 0.95% | +0.16% |
    | `pw_s0.5_h1.0_smooth1` | 62.8 | 1.471 | +4.3% | 70 / 106 | 2.33 | 0.52 / 1.85 | 0.88% | +0.17% |
    | `pw_s0.5_h1.0_smooth4` | 50.7 | 1.218 | +1.1% | 69 / 117 | 2.18 | 0.46 / 2.37 | 0.94% | +0.23% |
    | `pw_s0.5_h1.0_smooth16` | 43.1 | 1.040 | +0.9% | 72 / 124 | 1.97 | 0.43 / 3.02 | 0.91% | +0.28% |
    | `pw_s0.5_h1.0_ppc4` (no smoothing) | 52.5 | 1.265 | +1.0% | 66 / 120 | 1.83 | 0.79 / 2.23 | 0.98% | +0.21% |
    | `pw_s0.25_h1.0_long` (0.25×, no smoothing) | 33.9 | 0.465 | −0.7% | 71 / 142 | 2.10 | 1.01 / 2.75 | | |
    | `pw_s0.25_h1.0_long_ppc8` (0.25×, four times the particles) | 34.2 | 0.467 | +0.8% | 71 / 144 | 2.06 | 1.07 / 2.79 | 1.09% | +0.33% |
    | `pw_s0.25_h1.0_long_smooth4` (0.25×) | 32.8 | 0.450 | +0.1% | 72 / 145 | 2.13 | 0.90 / 2.98 | 1.03% | +0.35% |

    - Four passes at one times the particles and no passes at four times the particles agree in holding time
      (3%), number held (4%), ion energy, ion gap stream, field energy and charge balance. That agreement is
      partly a coincidence of the pass count: sixteen passes gives 43.1, 18% below the four-times-particle run,
      with no sign of levelling off (71.3, 62.8, 50.7, 43.1 at 0, 1, 4, 16 passes).
    - At 0.25×, where the answer does not depend on the particle count, four passes lowers it from 33.9 to 34.2
      down to 32.8 (3 to 4%), narrows the electron gap stream (0.90 against 1.01 to 1.07 orbits) and widens the
      ion one. So smoothing changes the answer by itself, by a few percent at four passes.
    - What survives: lowering the field noise by either route cuts the slow gain of plasma several times over
      (2 to 9% between 20 and 65 ns in the many-particle runs above against 26% in the baseline). It does not
      remove it. Why noisy fields make the run hold more is not known.
    - The electron gap stream is 0.6 to 1.2 cells in every run on this mesh (1.95 cells and 0.75 orbits on the
      mesh twice as fine), so it is the least resolved number in the table, and smoothing along z thins it.
    - At 2× the smoothed run is numerically unstable. In `pw_s2_h1.0_smooth4` the electric field energy grows
      from 17 J at 5 ns to 1,455 J at 20 ns (it falls from 50 J to 11 J in the unsmoothed `pw_s2_h1.0`), the
      mean electron energy reaches 3 MeV and nine tenths of the plasma is lost. Stopped by hand at 32 ns and
      recorded as failed; it is not a result. The smoothed runs at 0.25×, 0.5× and 1× show no such growth
      (their electric field energy falls and levels off). The cause is not known, so smoothing is not usable
      at 2× and its results at the smaller sizes are estimates only.
    - Cost at 0.5×: 2,763 s for `smooth4` against 5,588 s for `ppc4`.
  - The 1× case run twice as long does not settle (complete 17 October): `pw_s1_h1.0_long` holds for 153.9
    crossings measured at 800, against 141.8 at 400 in `pw_s1_h1.0`, and its number held is still rising 6.1%
    over the last fifth (6.65, 8.12, 9.13 and 9.79×10^15 electrons at 20, 65, 100 and 130 ns). Its pressure
    ratio is 0.70, its current layer 3.24 orbits and its electron gap stream 1.31 orbits, against 0.87, 2.84
    and 0.79 at 400 crossings. `pw_s1_h1.0_ppc2` (table above) holds 17% less and
    rises as fast.
  - In every finished case the particle count closes: feed = loss + change in the number held, to 1%, for both
    species in every time window. Over the last fifth the loss is 0.96 to 1.00 of the feed in the 0.25× and 0.5×
    cases and 0.90 in `pw_s1_h1.0`. So the holding time is the number held divided by a feed we chose, and the
    differences between repeats are differences in how much plasma each one ends up holding.
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
- The same scan with the wall correction (`zw15`, `zw30`, `zw60`: one device, field raised so that the coil
  radius is 15, 30 and 60 electron orbits). Finished so far, at 40 ns: `zw15_f1.8e22_long` 3.98 ns and
  `zw30_f4.5e22_long` 5.87 ns, with gap streams of 0.62 and 0.89 orbits and coil streams of 2.2 and 3.6
  orbits, at a pressure of 1.7 and 2.0 times the magnetic pressure of the coils alone in the gap. Both still
  gain 6 to 7% of their electrons over the last fifth, so neither is settled. Four times the particles leaves
  the smallest unchanged (`zw15_f1.8e22_long_ppc4`: 3.99 ns, gap stream 0.62 orbits, +6.6%), so here the slow
  gain is not a particle-count effect. The 60-orbit case at 40 ns and the 30-orbit case with more particles are
  running; a table waits for them.
