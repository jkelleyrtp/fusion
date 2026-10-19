# Electrons alone from the end walls, in the two-coil (r, z) runs with casings

Status: 2026-10-19. Method check on this machine's CPUs, then campaign `gun1` at size 15 (18 of 19 cases complete
when this was written). The gun does not help. Voltage on the casings helps a lot when the feed is small.

"Casing" here means the metal of `rz-casing-voltage.md`: for each coil a plate 2.9 mm thick with a hole of radius
8.55 mm round the axis, running out to the can. The ring leak is the slot between the two plates.

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

| Casings (kV) | Feed | Gun | Ion holding time inside the coils (ns) | Potential at the centre (kV) | Highest on the mid-plane (kV), at radius (mm) | 0.55 mm off the axis in a coil (kV) | Share of ions leaving through the coils |
|---|---|---|---|---|---|---|---|
| 0 | 0.01 | 0 | 3.15 | 2.6 | 4.7, 6.4 | 3.5 | 0.48 |
| 0 | 0.01 | 1 | 2.94 | 2.4 | 2.6, 6.2 | -0.1 | 0.57 |
| 100 | 0.01 | 0 | 13.2 | 10.3 | 31.1, 13.0 | 7.8 | 0.78 |
| 100 | 0.01 | 0.1 | 12.6 | 9.7 | 32.2, 12.8 | 6.1 | 0.84 |
| 100 | 0.01 | 1 | 9.74 | 10.4 | 28.6, 12.8 | 7.1 | 0.84 |
| 300 | 0.01 | 1 | 11.1 | 102 | 157, 11.7 | 88.7 | 0.99 |
| 0 | 0.1 | 0 | 4.50 | 2.9 | 6.0, 8.4 | 3.9 | 0.40 |
| 100 | 0.1 | 0 | 6.60 | 3.8 | 8.8, 8.9 | 4.0 | 0.43 |
| 100 | 0.1 | 0.1 | 6.18 | 2.5 | 7.2, 9.4 | 3.6 | 0.46 |
| 100 | 0.1 | 1 | 5.05 | 1.2 | 4.6, 9.2 | 2.4 | 0.55 |
| 300 | 0.1 | 0 | 8.50 | 60.3 | 68.1, 9.4 | 60.3 | 0.49 |
| 300 | 0.1 | 1 | 7.35 | 60.9 | 71.2, 9.1 | 57.8 | 0.57 |
| 100 | 1 | 0 | 7.82 | 8.0 ± 5.7 | 9.1, 9.1 | 5.6 | 0.56 |
| 100 | 1 | 1 | 6.87 | 2.4 ± 3.5 | 6.0, 2.0 | 3.6 | 0.59 |

The potentials are the mean of the last six snapshots (5 ns), with the field summed inward from the side wall and
stopped one cell short of the axis (`plugcheck/barrier.py`). Their spread between snapshots is 0.3 to 1.1 kV at 0.01
and 0.1 feed with no gun, and 2 to 6 kV at 1 feed. Summed to the same point from the end wall instead, they agree to
1 to 3 kV.

**The cell on the axis is left out, and `table.jsonl` for these runs has it in.** The reducer on the nodes summed the
mid-plane field right to the axis. The one cell on the axis adds 6 to 16 kV to the centre in the 10 keV runs (10.3 kV
becomes 19.4 at +100 kV and 0.01 feed), always upward. That cell is one of those that fail Gauss's law, and a
potential 10 kV higher across 0.16 mm would need 30 times the plasma's density in net charge there. The reducer now
stops one cell short (`on_metal` in `analyze_spindle.py`). The centre potentials in `rz-casing-voltage.md` are from
single snapshots with the axis cell in; there it moves the centre by -31 to +10 kV and one snapshot's waves are as
large, so read those as within about 20 kV.

- The gun lowers the holding time in all six pairs, by 5 to 26%.
- Little of the gun gets in. Counted in the shell 1 to 2 mm inside each end wall, the electrons heading inward are
  2 to 6% of those fired with the casings at +100 kV (19% when the gun is a tenth as strong) and under 1% at 0 V.
  The rest turn back in the first millimetre, held by their own charge.
- The plasma is never below the wall's potential.
- The potential rises from the centre outward along the mid-plane in every case with no gun, casings charged or
  not: a hill in the ring leak that ions have to climb. Its height above the centre, against the ions' 10 keV:
  2 kV (0 V, 0.01 feed), 3 kV (0 V, 0.1), 5 kV (+100 kV, 0.1), 8 kV (+300 kV, 0.1), 21 kV (+100 kV, 0.01), 55 kV
  (+300 kV, 0.01 with the gun). The share of ions leaving through the coils instead follows it: 0.48, 0.40, 0.43,
  0.49, 0.78, 0.99.
- Along the coils' axis there is no hill: 0.55 mm off the axis the potential falls from the centre to the end wall
  without rising, in every case. So the casings plug the ring leak for ions and leave the coils open.
- Voltage on the casings: 4.2 times the holding time at 0.01 feed, 1.5 times at 0.1 feed. With 100 keV electrons
  at 1 feed it was 1.14 times (`rz-casing-voltage.md`).
- The 0.01-feed cases at +100 and +300 kV had not settled: ions inside the coils still rising 6 to 19% over the
  last fifth, loss 85 to 95% of feed.
- At +300 kV and 0.1 feed, electrons land on the casings at 0.96 of the feed rate.

### Electrons going out and coming back

Electrons crossing the coil planes and the gap at the coil radius, outward and inward, last fifth of the run, in
units of the pair feed, no gun:

| Casings (kV) | Feed | Out through the leaks | Back in | Share that come back |
|---|---|---|---|---|
| 0 | 0.01 | 1.54 | 0.55 | 36% |
| 100 | 0.1 | 3.60 | 2.63 | 73% |
| 100 | 0.01 | 19.4 | 18.6 | 96% |

In the shell 1 to 2 mm inside the side wall at +100 kV and 0.01 feed, 8.5 go out and 8.1 come back: they turn
round in the last millimetre before the wall. Each coil's metal is a plate that runs from the hole round the axis out to the can (`rz-casing-voltage.md`), so
no field line closes round a coil clear of metal: 60% of the can's volume outside the metal is on lines that run
into a plate, and the rest is on lines that run from wall to wall through the centre. The plasma is on the
second kind. The share on lines that meet a plate (`plugcheck/lines.py shares`, last six snapshots of each of the
18 cases): electrons 0 with 10 keV electrons and plates at 0 or +100 kV, 1e-4 to 2e-3 with 100 keV electrons, 2e-3
to 3e-3 with plates at +300 kV; ions 5e-4 to 1e-3 at +100 kV and 2 to 4% at 0 V. So what comes back has turned
round at the wall's potential, at the end of the slot between the two plates or in front of an end wall.
