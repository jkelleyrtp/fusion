# Reproducing the picket-fence cusp of Park et al. 2019

Status 2026-10-17: **the agreement reported here on 2026-10-16 was produced by the wall fault.** With the
charge left at the wall removed ([wall-charge.md](wall-charge.md)), the baseline holds for 85 electron crossings
when measured at 40 to 50 crossings, not 141, against the paper's 135, and is still rising then. The same size
run for 400 crossings reaches 120 to 140. The paper's Run 1 covers about 28 electron crossings, so at its run
length we are well below it, and the difference is unexplained. The current layer agrees throughout (2.4 to 2.9
orbits against 2.1). The corrected 2.76 keV case is running. Everything below the next two sections is the
uncorrected record.

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

- At 50 crossings the holding time is 37% below the paper's and does not depend on the fill between 0.7 and
  1.4 times the baseline. The uncorrected 141 matched the paper by an error of ours, not by getting the physics
  right.
- These cases are not steady at 50 crossings: the sustaining feed is the paper's (1/18 of the filling rate,
  which balances a holding time of about 135 crossings), so with a shorter holding time the inventory is still
  falling. The holding time is the number held over the loss rate during that fall.
- We do not know why the paper's number is higher. Candidates we have not tested: its wall treatment, which
  the paper does not describe in enough detail for us to copy; its electron temperature (2.8 keV against our
  100 keV); its implicit time stepping. The corrected 2.76 keV case addresses the second.
- Four runs proposed by an audit of this comparison ([park-comparison-audit.md](park-comparison-audit.md));
  three are complete (17 October, `campaigns/picket/pk1_park_audit.txt`), all at 100 keV with the baseline
  particle count:

  | Case | Change from `pfw_x1.0` | Holding time (electron crossings) | Measured over crossings | Change in electrons held over the last fifth | Electric field energy ÷ plasma energy |
  |---|---|---|---|---|---|
  | `pfw_x1.0` | none | 84.6 | 40–50 | −3.9% | 0.021 |
  | `pk_open_wall` | outer boundary absorbs waves (Silver-Mueller) instead of reflecting them | 91.7 | 40–50 | −2.6% | 0.014 |
  | `pk_open_wall_esirkepov` | the same, with the default deposition and no cropping | 94.0 | 40–50 | −2.5% | 0.014 |
  | `pk_const_charge` | sustaining feed raised to 0.154 of the filling rate, run for 28 crossings as the paper's Run 1 | 61.2 | 22–28 | +0.2% | 0.017 |

  - With the paper's protocol (number held kept constant, 28 crossings) the holding time is 61, against the
    paper's 135 (or 174 from its own charge and injection figures). The number held is steady to 0.2%, so this
    is held ÷ feed as well as held ÷ loss. The gap is not the protocol.
  - An open outer boundary raises the holding time by 8%, and with it the deposition method changes the result
    by 2.5%, with no wall layer in either (field energy 1.4% of plasma energy in both). The false wall charge
    is specific to a conducting mesh edge. An open boundary in WarpX does not produce the paper's number. This
    says nothing about what the paper's code does at its boundary.
  - The wall was left at 1.5 coil radii in these runs. The audit asked for 1.4 (the paper's 42 against our 45
    code units), which is not yet run.
  - `pk_ppc_paper` (8 times the particles) is running.
- At 1.4× the fill the layer is still intact here (pressure ratio 0.81, the same as at 1.0×, with a wider gap
  stream), so we do not see the paper's sudden failure of the wall in the gap; the plasma instead leaks until
  the pressure ratio is back near 0.8.
- At 25 keV fed (`pfw_25keV_x1.0`, complete) the corrected holding time at 50 crossings is 116 crossings
  against 85 at 100 keV, with a 2.6-orbit layer; uncorrected it was 188. Colder electrons hold longer in these
  units, which moves toward the paper's number.

## The same size run eight times longer

The size scan's 1× cases (`pw_s1_h…` in `pw1`) are this geometry and coil current with the correction, at 0.56,
0.8 and 1.12 times the paper's fill, a sustaining feed of 0.0721 of the filling feed instead of 1/18, and 400
crossings instead of 50. Holding time in electron crossings, number held over the rate of leaving, by interval:

| Interval (crossings) | 10–20 | 20–30 | 30–40 | 40–50 | 50–75 | 75–100 | 100–150 | 150–200 | 200–300 | 300–400 |
|---|---|---|---|---|---|---|---|---|---|---|
| `pfw_x1.0` (paper's feed, ends at 50) | 54 | 64 | 75 | 84 | | | | | | |
| `pw_s1_h0.7` | 57 | 63 | 69 | 76 | 86 | 96 | 103 | 113 | 120 | 119 |
| `pw_s1_h1.0` | 60 | 70 | 79 | 88 | 101 | 111 | 117 | 119 | 129 | 141 |
| `pw_s1_h1.4` | 53 | 65 | 77 | 87 | 99 | 109 | 115 | 115 | 121 | 129 |
| `pf_x1.0` (uncorrected, ends at 50) | 65 | 93 | 126 | 154 | | | | | | |

These intervals use the feed minus the change in number held as the rate of leaving; the table rows elsewhere
use the counted flux through the side, which is why 84 here is 84.6 there.

- **The holding time is not settled at 50 crossings.** Every corrected case passes 84 to 88 at 40–50 crossings
  and keeps rising for hundreds of crossings, to 119–141. The paper's 135 lies inside that range.
- **That does not restore the agreement.** The paper's 135 is the holding time its sustaining feed balances
  while the charge held stays constant, in a Run 1 that covers 3.5 ion crossings (28 electron crossings) from
  start to end, and it states a minimum of 2.2 ion crossings after filling. At 20 to 30 crossings our corrected
  runs hold for 63 to 70 and are losing plasma on the paper's feed. We reach its number only an order of
  magnitude later in time.
- The electrons cool as this happens (mean energy 59 to 73 keV at the end against 150 keV fed), and holding
  time counted in crossings at the fed temperature rises as they do.


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
