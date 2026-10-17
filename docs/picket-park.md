# Reproducing the picket-fence cusp of Park et al. 2019

Status 2026-10-17: **the agreement reported here on 2026-10-16 does not survive the wall correction.** With
the charge left at the wall removed ([wall-charge.md](wall-charge.md)), the baseline holds for 85 electron
crossings, not 141, against the paper's 135. The current layer still agrees (2.5 orbits against 2.1). Three
corrected cases at 100 keV are complete; the corrected 25 keV and 2.76 keV cases are running. Everything below
the next section is the uncorrected record.

## Corrected repeat

Same inputs as `pf_x0.7`, `pf_x1.0`, `pf_x1.4` plus the two wall settings; campaign `pw1`, cases `pfw_…`.

| | Park et al. 2019, Run 1 | `pfw_x0.7` | `pfw_x1.0` | `pfw_x1.4` | `pf_x1.0` (uncorrected) |
|---|---|---|---|---|---|
| Holding time, electron crossings of the coil diameter | about 135 | 86.6 | 84.6 | 85.6 | 141 |
| Holding time, ion crossings | about 17 | 11.8 | 11.5 | 11.7 | 19.3 |
| Current layer, in electron orbits (their convention) | about 2.1 | 2.35 | 2.46 | 2.60 | 2.2 |
| Pressure inside ÷ magnetic pressure just outside the edge | not given in this form | 0.75 | 0.81 | 0.81 | 0.83 |
| Gap stream half-height, in electron orbits at the edge | not given | 1.0 | 1.7 | 2.2 | 2.1 |
| Electric field energy ÷ plasma energy | not given | 0.021 | 0.021 | 0.023 | not reduced |
| Change in electrons held over the last fifth | | −4.0% | −3.9% | −3.1% | +0.3% |

- The holding time is 37% below the paper's and does not depend on the fill between 0.7 and 1.4 times the
  baseline. The uncorrected 141 matched the paper by an error of ours, not by getting the physics right.
- These cases are not steady at 50 crossings: the sustaining feed is the paper's (1/18 of the filling rate,
  which balances a holding time of about 135 crossings), so with a shorter holding time the inventory is still
  falling. The holding time is the number held over the loss rate during that fall.
- We do not know why the paper's number is higher. Candidates we have not tested: its wall treatment, which
  the paper does not describe in enough detail for us to copy; its electron temperature (2.8 keV against our
  100 keV); its implicit time stepping. The corrected 2.76 keV case addresses the second.
- At 1.4× the fill the layer is still intact here (pressure ratio 0.81, the same as at 1.0×, with a wider gap
  stream), so we do not see the paper's sudden failure of the wall in the gap; the plasma instead leaks until
  the pressure ratio is back near 0.8.

Uses two unreviewed WarpX patches: paired injection and the coil field on the mesh
([warpx-patches.md](warpx-patches.md), [flux-injection-charge.md](flux-injection-charge.md)).

## Result before the wall correction (superseded)

| | Park et al. 2019, Run 1 | `pf_x1.0` | `pf_x0.7` (0.7× the fill) |
|---|---|---|---|
| Holding time, electron crossings of the coil diameter | about 135 | 141 | 130 |
| Holding time, ion crossings | about 17 | 19.3 | 17.8 |
| Current layer, full width at half maximum, in electron orbits (their convention) | about 2.1 (0.6 / 0.28) | 2.2 | 2.3 |
| Same width with the orbit taken from the measured electron pressure | not given | 3.2 | 3.3 |
| Density edge, 90% to 10%, in electron orbits at the edge field | not given | 3.5 | 3.8 |
| Pressure inside ÷ magnetic pressure just outside the edge | not given in this form | 0.83 | 0.78 |
| Cells across the current layer | about 5 and 7 at their two converged meshes | 5.1 | 6.2 |

- Electrons and ions leave at the same rate, and the number held changes by 0.3% over the last fifth of
  the run, so both cases are steady.
- The coil field is pushed out of the plasma: about 1 T inside against 12 to 14 T just outside the layer.
- Park's convention takes the orbit from the temperature the plasma is fed at and the mean field inside
  the current layer. Our electrons cool from 100 keV fed to a mean energy of 75 keV, so the orbit from
  the measured pressure is smaller and the same layer is 3.2 of those.

## What was run

`warpx/cusp/inputs_rz_picket_fed`, cases in `warpx/campaigns/picket/pf1.txt`, reduced by
`warpx/cusp/analyze_picket.py`.

- 2D axisymmetric, periodic along the axis, a row of 25 alternating ring coils of which the mesh holds one period, absorbing
  wall at 1.5 coil radii.
- Plasma fed in pairs near the axis: a filling phase of 10 electron crossings, then 1/18 of that rate, as in
  the paper. Ions are 64 electron masses.
- 50 electron crossings in all; measurements are means over the last fifth.

## Temperature repeats

Same case, same mesh, colder electrons with the field lowered to keep the orbit.

| Fed electron temperature | Holding time (electron crossings) | Current layer (orbits, their convention) | Mean electron energy ÷ (1.5 × fed temperature) |
|---|---|---|---|
| 100 keV (`pf_x1.0`) | 141 | 2.21 | 0.50 |
| 25 keV (`pf_25keV_x1.0`) | 188 | 2.43 | 0.48 |
| 6.25 keV (`pf_6keV_x1.0`) | 158 | 2.55 | 0.44 |
| 2.76 keV (`pf_2.76keV_x1.0`) | 174 | 2.58 | 0.39 |

- At the paper's own temperature the holding time is 172 crossings against its 135, and the layer 2.6 orbits
  against 2.1. The 100 keV case is the closer one.
- The mesh does not resolve the screening length below 100 keV, and an explicit code heats or cools plasma on
  such a mesh, so the colder rows are not a cleaner comparison than the 100 keV one.

## Differences from the paper

- **Electron temperature.** 100 keV here against about 2.8 keV (thermal speed 0.0735 of light) in the paper,
  so that one mesh resolves the screening length. See the temperature repeats below.
- **Code.** WarpX is explicit; the paper's code is implicit and conserves energy exactly.
- **Layer average.** The current profile here is a mean over 3 snapshots and 4 rows of cells; the paper uses 20.
- **Fill.** The coil current and the fill of `pf_x1.0` are the paper's, converted to our units. Neither was
  tuned to match its holding time.

## Not yet known

- Whether 141 crossings holds with another seed, a finer mesh and half the time step.
- Whether the wall fails in the gap at 1.4× the baseline pressure, as the paper reports.
- How the result changes with ion mass (16, 256).
