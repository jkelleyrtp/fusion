# Charge left at absorbing conducting walls

Status 2026-10-17. Every run before this date used WarpX's default current deposition at walls that are
conducting for the fields and absorbing for particles. That combination leaves charge in the last cell at the
wall, and the electric field of that charge changed the holding times we reported. Two input settings remove it;
no WarpX source was changed. Corrected repeats are running; this file says what is established and which
earlier numbers are withdrawn.

## What goes wrong

A particle that crosses the wall during a step is deleted, but the default (Esirkepov) deposition has already
laid down current for the whole of its last step, including the part beyond the wall. The field solver then
sees charge in the last cell that no particle carries. Electrons overshoot further per step than ions, so the
leftovers add up to a positive layer that keeps growing for as long as plasma reaches the wall.

Measured in the smallest picket-fence case (`w_near` in `warpx/campaigns/picket/wall1.txt`, 96 radial cells)
and its twin with the fix (`w_vill`), at 3.1 ns. "Field implies" is the charge inside the outermost cell from
the flux of the radial electric field through its inner face; "particles carry" is the deposited charge density
summed over the same cell.

| | Default | With the fix |
|---|---|---|
| Charge the field implies in the last cell | +2.0e13 e | +1.6e12 e |
| Charge the particles carry there | −6.1e12 e | +1.6e12 e |
| Voltage across the last cell | 60 kV | 5 kV |
| Field energy in the last two radial cells | 0.152 J | 0.002 J |
| Field energy inside 1 cm (the plasma) | 0.192 J | 0.191 J |

In the default run the voltage across the last cell reaches 119 kV by 9.4 ns, against electrons fed at 100 keV.
Moving the wall twice as far out (`w_far`) lowers the share of field energy in the last two cells from 53% to
18% at 4.7 ns but does not remove it. `w_near`, `w_far` and `w_vill` were diagnostic runs read part-way
through; none is a result.

## The fix

```
particles.crop_on_PEC_boundary = 1
algo.current_deposition = villasenor
```

The first cuts each trajectory at the wall before depositing; the second is a charge-conserving deposition that
honours the cut. Cropping with the default deposition did not remove the layer in our test (`w_crop`, stopped
early). Villasenor without cropping has not been run to a readable time, so we do not know whether the
deposition alone would do.

## How it shows in a table row

The reducers now report two numbers per case, averaged over the last fifth of the run:

- `electric_field_energy_over_plasma_energy`: about 0.01 in the corrected picket cases, and steady. With
  the fault it grows without limit: 0.14 after 200 electron crossings at the smallest size, 2.9 in `pm_s1_h1.4`.
- `ions_minus_electrons_over_electrons`: +0.003 corrected (a slightly positive plasma, as expected when
  electrons leave faster). With the fault it drifts negative, to −0.10 in `pm_s0.25_h1.0_long`, because the
  positive wall layer pushes electrons back and pulls ions out.

## Effect on results

Paired cases, the same input except for the two settings. Old rows are campaign `pm1` and `sp2`, corrected
rows campaign `pw1`. Only complete cases.

**Picket fence, 100 keV, holding time in electron crossings and gap stream half-height in electron orbits at
the edge:**

| Size | Fill | Length (crossings) | Holding time, old → corrected | Gap stream, old → corrected | Current layer (orbits), old → corrected |
|---|---|---|---|---|---|
| 0.25× | 0.7 | 200 | 52.6 → 37.1 | 1.07 → 0.77 | 2.24 → 2.11 |
| 0.25× | 1.0 | 200 | 55.4 → 36.4 | 1.38 → 0.88 | 1.89 → 2.13 |
| 0.25× | 1.4 | 200 | 54.7 → 35.8 | 1.82 → 1.24 | 1.93 → 2.03 |
| 0.25× | 1.0 | 400 | 59.4 → 33.9 | 1.50 → 1.01 | 2.19 → 2.10 |
| 0.25× | 1.4 | 400 | 56.7 → 34.2 | 2.06 → 1.29 | 2.29 → 2.03 |
| 0.5× | 0.7 | 400 | 102.8 → 69.0 | 0.75 → 0.46 | 2.19 → 2.41 |
| 0.5× | 1.0 | 400 | 100.6 → 71.3 | 1.20 → 0.66 | 2.18 → 2.42 |
| 0.5× | 1.4 | 400 | 97.8 → 74.8 | 1.42 → 0.96 | 2.64 → 2.31 |

Holding times fall by 24 to 43%, gap streams narrow by 28 to 45%, and the current layer stays at 2.0 to 2.4
orbits. The
corrected runs settle: the 400-crossing case holds within 7% of the 200-crossing one, where the old pair kept
growing.

**Two-coil cusp, the hot-electron cases `z…` of `sp2`, holding time in ns and pressure ratio in the gap:**

| Case | Pressure ratio | Holding time, old → corrected | Gap stream half-height (mm), old → corrected |
|---|---|---|---|
| `z15_f2e21` | 0.12 | 1.71 → 1.69 | 0.77 → 0.76 |
| `z15_f6e21` | 0.42 | 2.15 → 2.10 | 0.89 → 0.89 |
| `z15_f1.8e22` | 1.5 | 3.20 → 2.74 | 1.21 → 1.19 |
| `z15_f5.4e22` | 3.6 | 4.00 → 3.01 | 2.08 → 1.95 |
| `z30_f5e21` | 0.14 | 2.85 → 2.63 | 0.42 → 0.42 |
| `z30_f1.5e22` | 0.54 | 3.95 → 3.32 | 0.51 → 0.49 |
| `z30_f4.5e22` | 1.8 | 5.39 → 4.28 | 0.80 → 0.75 |
| `z30_f1.3e23` | 3.6 | 6.75 → 4.41 | 1.83 → 1.63 |

The fault grows with the amount of plasma reaching the wall: holding times fall 1 to 16% at pressure ratios
under 0.6 and 14 to 35% above 1. The widths move by 11% at most. So "the leak streams widen as the pressure
rises" stands, and the rise of holding time with pressure was partly the fault: from the lowest to the highest
pressure here it was 2.3 to 2.4 times, and corrected it is 1.7 to 1.8 times. The 10 keV pressure scan in
section 1 of [cusp-results.md](cusp-results.md) has not been repeated.

## What is withdrawn, what stands, what is not yet known

- **Withdrawn:** the picket-fence size-scan exponents (holding time as size^0.7, gap stream as size^0.56) and
  every `pm1` holding time. Section 3 of [cusp-results.md](cusp-results.md) is kept for the record only.
- **Overstated:** two-coil holding times at pressure ratios above 1, by 14 to 35% in the cases repeated, and
  with them the size of the rise of holding time with pressure.
- **Stands:** the current-layer width of 2 to 2.5 electron orbits; the widening of the leak streams with
  pressure; two-coil numbers at the lowest pressure ratios, within a few percent.
- **Not yet known:** the corrected size scan beyond 0.5× (1×, 2×, 4× running in `pw1`); the effect in the 3D
  six-coil runs (two twins of `hot1` cases running as `hw1`); whether the published-case check in
  [picket-park.md](picket-park.md) still agrees.

Runs from now on use the two settings. Campaigns finished before this date have not been rerun except where
listed above.
