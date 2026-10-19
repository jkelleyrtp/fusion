# Electrons alone from the end walls, in the two-coil (r, z) runs with casings

Status: 2026-10-19. The method check below is done on this machine's CPUs. No physics result yet.

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

Not checked: a settled run, the GPU build, and the mesh.
