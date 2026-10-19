# Electrons alone from the end walls, in the two-coil (r, z) runs with casings

Status: 2026-10-19. Method check on this machine's CPUs, then campaign `gun1` at size 15 (18 of 19 cases complete
when this was written). The gun does not help. Voltage on the casings helps a lot when the feed is small.

## Why

Every two-coil run so far is fed with equal numbers of electrons and ions born at the centre. The electrons
leave faster, so the plasma sits at +40 to +100 kV whatever the casings are at (`rz-casing-voltage.md`), and
metal at a negative voltage collects ions. Electrostatic plugging and the Polywell assume the opposite: more
electrons than ions, a plasma below the metal's potential, ions held by that. To get there the device needs a
source of electrons with no ions.

## What is added

Deck `inputs_rz_spindle_casing_gun`: the casing deck plus two electron sources, one on each end wall of the
can, on a disc of radius `rg` around the axis, sending `gun` electrons per second (the two together) toward the
centre at temperature `tg`. With the casings at a positive voltage and `tg` small this is the Polywell
arrangement: electrons start cold on the grounded wall and fall toward the metal. `gun = 0.` gives the
casing deck's run. The neutral feed at the centre stays, as the source of ions; `feed` sets it.

The reducer divides by `feed` for every holding time. With a gun the electrons' holding times are therefore not
per electron supplied; the ions' are.

## Why the end walls

The field solver never solves Gauss's law (`flux-injection-charge.md`): a particle made anywhere in the plasma
without a partner leaves its opposite charge fixed on the mesh at that place. So an unequal feed at the centre
would not make the plasma negative; it would put a fixed positive charge at the centre. A particle made on a
conducting wall leaves its opposite charge on the wall, which is right. WarpX makes nothing on the upper wall
itself, so both sources sit 1e-9 coil radii inside their wall.

## Check

Size 15, 128 cells across the radius, casings at +100 kV, no neutral feed, `gun = 1.8e21`, 1 keV, 1.6 ns
(5,117 steps), four snapshots. Mean of `eps0 div E - rho` over the cells in the disc's radius, by row of cells
counted from the wall (C/m3):

| Row from the wall | Charge density | Error, lower wall | Error, upper wall |
|---|---|---|---|
| second | -0.19 to -0.21 | 0.0083 to 0.0086 | 0.0081 to 0.0087 |
| third | -0.09 to -0.11 | 6e-11 to 7e-11 | 6e-11 to 7e-11 |
| at the centre | -0.04 to -0.06 | 3e-11 to 4e-11 | |

- From the third row in, Gauss's law holds to 7e-10 of the charge density.
- The second row is off by 4% of its charge density and does not grow: the same at 0.4 ns as at 1.6 ns, while the
  charge fired goes up fourfold. A charge left behind by each electron would grow with the number fired, and
  all of it left in that row would be about 50 C/m3 by 1.6 ns. Not known whether the 4% is in the fields or only in
  how the snapshot's charge density is cut off at the wall.
- The first row holds the wall's own surface charge in `div E`, with or without a gun, and is not a test.
- A source given a temperature of its own does use it: mean energy 1.7 keV a few steps after leaving at `tg` =
  1 keV with the casings at 0 V, where the species' 100 keV would give 200 keV.

Without ions the cloud is limited by its own charge: at 1.4 ns 3.6e11 electrons are in the can of 2.5e12 fired.

Not checked: the mesh.

## Runs (`gun1`, size 15, coils at 0.6 radii, both leaks open)

Pairs born at the centre with 10 keV electrons and 10 keV ions (earlier tables used 100 keV electrons, which
halves every holding time). `feed` is in units of 1.8e22 pairs per second, `gun` in units of 1.8e22 electrons per
second. All from `table.jsonl`; Gauss's law off the axis holds to 1.3e-10 in every case.

| Casings (kV) | Feed | Gun | Ion holding time inside the coils (ns) | Potential: centre / gap at coil radius (kV) | Share of ions leaving through the coils |
|---|---|---|---|---|---|
| 0 | 0.01 | 0 | 3.15 | 8.5 / 3.4 | 0.48 |
| 0 | 0.01 | 1 | 2.94 | 9.5 / 2.1 | 0.58 |
| 100 | 0.01 | 0 | 13.2 | 19.9 / 29.6 | 0.78 |
| 100 | 0.01 | 0.1 | 12.6 | 23.1 / 30.3 | 0.84 |
| 100 | 0.01 | 1 | 9.74 | 21.6 / 25.4 | 0.84 |
| 300 | 0.01 | 1 | 11.1 | 121 / 155 | 0.99 |
| 0 | 0.1 | 0 | 4.50 | 12.5 / 5.7 | 0.40 |
| 100 | 0.1 | 0 | 6.60 | 13.3 / 8.7 | 0.43 |
| 100 | 0.1 | 0.1 | 6.18 | 13.8 / 7.3 | 0.46 |
| 100 | 0.1 | 1 | 5.05 | 16.3 / 4.9 | 0.55 |
| 300 | 0.1 | 0 | 8.50 | 75.7 / 68.3 | 0.49 |
| 300 | 0.1 | 1 | 7.35 | 90.4 / 71.1 | 0.57 |
| 100 | 1 | 0 | 7.82 | 8.5 / 8.0 | 0.56 |
| 100 | 1 | 1 | 6.87 | 5.5 / 4.7 | 0.59 |

- The gun lowers the holding time in all six pairs, by 5 to 26%.
- Little of the gun gets in. Counted in the shell 1 to 2 mm inside each end wall, the electrons heading inward are
  2 to 6% of those fired with the casings at +100 kV (19% when the gun is a tenth as strong) and under 1% at 0 V.
  The rest turn back in the first millimetre, held by their own charge.
- The plasma is never below the wall's potential. What changes with the feed is the potential in the ring leak
  against the centre: 10 kV above it at 0.01 feed and +100 kV, below it in every case at 0.1 and 1. Where it is
  above, ions are turned back there (a third of those reaching the coil radius at 0.01 feed) and four fifths of
  the ions leave through the coils instead.
- Voltage on the casings: 4.2 times the holding time at 0.01 feed, 1.5 times at 0.1 feed. With 100 keV electrons
  at 1 feed it was 1.14 times (`rz-casing-voltage.md`).
- The 0.01-feed cases at +100 and +300 kV had not settled: ions inside the coils still rising 6 to 19% over the
  last fifth, loss 85 to 95% of feed.
- At +300 kV and 0.1 feed, electrons land on the casings at 0.96 of the feed rate.
- The potential on the axis in a coil is not usable: its spread between snapshots is up to 31 kV, from the axis
  cells that fail Gauss's law.

### Electrons going out and coming back

Electrons crossing the coil planes and the gap at the coil radius, outward and inward, last fifth of the run, in
units of the pair feed, no gun:

| Casings (kV) | Feed | Out through the leaks | Back in | Share that come back |
|---|---|---|---|---|
| 0 | 0.01 | 1.54 | 0.55 | 36% |
| 100 | 0.1 | 3.60 | 2.63 | 73% |
| 100 | 0.01 | 19.4 | 18.6 | 96% |

In the shell 1 to 2 mm inside the side wall at +100 kV and 0.01 feed, 8.5 go out and 8.1 come back: they turn
round in the last millimetre before the wall. Field lines that close round a coil inside the can without touching anything fill 41% of the can, but the plasma is
not on them: in the six cases whose snapshots were fetched, the share of electrons there is 0 with 10 keV electrons
and 1e-5 with 100 keV, and of ions 1e-4 to 2e-3 (`plugcheck/lines.py`). So all of this is turning back at the wall's
potential.
