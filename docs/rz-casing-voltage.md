# Metal at a set voltage in the two-coil (r, z) runs

`warpx/cusp/inputs_rz_spindle_casing` is the two-coil leak deck with metal around each coil winding, held at a
voltage chosen per case. This page says how the voltage is put in, what has been checked, and what has not.
The 3D version of the same method is in `ring-voltage-design.md`.

## The metal

Each coil winding sits in a ring of square section, 2.9 mm across, which carries on outward to the can as a
flange. In (r, z) that is one block per coil. Plasma leaves between the two blocks (the ring leak) and through
the hole in each (the stream through a coil). Three constants move the metal towards the plasma: `rb`, the
radius of the hole; and `hs` with `rs`, the half-height of the gap between the blocks beyond radius `rs`.

The can stays at 0 V. The metal's voltage is against the can.

## How the voltage is put in

WarpX's electromagnetic solver cannot hold a conductor at a voltage: metal inside the box is at the can's
voltage. So the field is split in two, as in 3D:

1. The solver runs with the metal at 0 V. Its field is the plasma's, with the charge the plasma draws onto
   the metal and the can.
2. `warpx/cusp/unit_map.py` solves Laplace's equation for the metal at 1 V and the can at 0 V, with no plasma.
   WarpX reads that field from `unit.h5` and adds it, times `volts`, to the field on the particles.

The sum is the field with the metal at `volts`, exactly, provided both parts mean the same thing by "metal".
`campaign.py` makes `unit.h5` in the case's directory before WarpX starts, from the deck and the case's settings.

Three choices make the two parts agree:

- **Which cells are metal.** The solver leaves alone every cell the metal's surface cuts. `unit_map.py` reads
  the deck's own `warpx.eb_implicit_function` and grows the metal to the corners of those cells.
- **Where the faces are.** Each face is put in the middle of a cell. Which cells it cuts then does not hang on
  rounding. It also keeps Gauss's law at the metal: a particle's charge is spread over 1.5 cells either side
  of it, and WarpX takes a particle out when it passes the face, so at that moment none of its charge is on a
  node outside the metal. With the faces 0.3 of a cell past a mesh line, as first tried, each particle left
  up to 2% of its charge behind on the nearest node for the rest of the run (see the table).
- **Where the field is sampled.** The potential is on mesh nodes and the field is its difference along each
  mesh edge, which is where WarpX keeps Er and Ez. The file has twice the mesh's resolution, so each edge
  midpoint is a sample and WarpX reads the differences back with no interpolation across the metal.

One place they differ on purpose: in the map the metal stops 1 mm (`gap`) short of the can, so that the two
can be at different voltages; in the run it reaches the can. Particles in that last millimetre are about to
be absorbed.

## What is measured

`analyze_spindle.py` adds, for these runs:

- electrons and ions landing on the metal per second and the power they carry, from the particles WarpX
  writes as they land (one in ten is written, `scr_keep`);
- the potential at the centre, on the axis in a coil and in the gap at the coil radius, as the mean over the
  snapshots in the last fifth of the feed with its spread over them, beside the same three with no plasma. One
  snapshot is not enough: the field holds waves as large as the potential;
- holding times that count what lands on the metal as lost. The metal reaches out past the shell that counts
  what leaves by the gap, so a particle landing beyond that shell is already counted there; only the landings
  the shell has not seen are added (`..._landing_on_metal_not_counted_at_gap_per_s`).
- how far the last snapshot is from Gauss's law (rms of eps0 div E - rho over rms of rho), away from the metal,
  within two cells of it, and in the cells on the axis. The solver never solves that law, so this is the check
  that no charge is made or lost wrongly.

Power the supply must give is the electron current to the metal times the voltage (positive metal), which is
not in the table; the landing rates are.

## Checked

On this machine's CPUs, size 15 (29.3 kA-turns), coils at 0.6 radii, 128 cells across the radius unless said.

| Check | Result |
|---|---|
| WarpX reads the map as written: snapshot of a run with no plasma at 100 kV against the map, every cell | rms difference 2e-8 V/m in a field of 1.3e7 V/m |
| Particles feel the map: 400 heavy particles at rest in a run with no plasma at 1 kV, the push each gets over 10 steps against the map's field gathered at where it sits, down to 0.2 of a cell from the metal | rms difference 7.5e-14 of the rms field, largest 7.8e-13 |
| The solver's metal is the map's metal: cells where the solver's own field is exactly zero in a plasma run against cells whose four corners are metal in the map | the same 2,812 cells, none more and none fewer |
| The map settles with the mesh: potential at the centre for 1 V | 0.9085, 0.9062, 0.9048 at 128, 256, 1,024 cells |
| Gauss's law off the axis, 100 kV, at 1.6 ns | error 1.3e-10 of the charge density, both away from the metal and within two cells of it. With the faces at 0.3 of a cell it was 0.024 within two cells of the metal at 0.8 ns, and growing |
| Gauss's law in the cells on the axis | error 3.0 times the rms charge density there at 1.6 ns (2.1 at 0.8 ns). The same deck with no metal gives 2.0 at 0.8 ns, so this is not from the metal. It is the noise on the axis described in [park-vs-warpx.md](park-vs-warpx.md), section 6 |

## Checked on the GPU executable, in full runs

Campaign `casing1`: 48 ns, size 15, coils at 0.6 radii, 1× feed, faces at mid-cell. Thirteen cases: seven
voltages, three at 256 cells, three with metal reaching to 1 mm from the mid-plane outside 12 mm radius (`near`).

| Check | Result |
|---|---|
| Gauss's law off the axis at 48 ns, all seven voltages | error 1.3e-10 of the charge density, away from the metal and within two cells of it |
| The same with the `near` metal, which has an inside corner | 1.3e-10 away from the metal; 2e-5 to 1e-4 within two cells of it, all of it in the two cells diagonal to each inside corner |
| Particles are all counted: rate lost (two shells plus the metal landings the shells have not seen) against feed less growth, last fifth | agree to 0.6% or better for electrons in all thirteen cases, and to 2% for ions |
| Where particles land | 0 V: ions on the faces towards the mid-plane (4% of the feed). Negative metal: ions on those faces and the hole's face, and at -300 kV the faces towards the ends as well (86% of the feed). +300 kV: electrons on the faces towards the mid-plane beyond 16 mm radius (35% of the feed). No electron lands on negative metal and no ion on metal at +300 kV |
| Mesh: 256 cells against 128, at -100, 0 and +100 kV | holding time 2.40, 3.50, 4.13 against 2.48, 3.57, 4.15 ns; ring leak half-height 0.264, 0.284, 0.312 against 0.250, 0.281, 0.308 mm; stream through a coil 1.68, 1.82, 1.90 against 1.66, 1.80, 1.88 mm |
| Gauss's law in the cells on the axis | 1.6 to 2.3 times the rms charge density there, at every voltage including 0, as on the CPUs |

## Not checked

- Whether the error on the axis matters to these runs. Without metal, runs with 4 times the particles gave the
  same widths and a holding time 6% longer.
- Any size but 15.
- Why grounded casings alone hold longer than no metal (3.57 against 2.84 ns in `iso3`). The metal also shuts
  the plasma's own magnetic field out of the casings; the two decks have not been compared line by line.
- The potential on the axis in a coil: its spread over ten snapshots is 50 to 110 kV, so it is not usable.

## What the runs say (provisional)

| Metal (kV) | Electron holding time (ns) | Electrons landing on metal (share of feed) | Ions landing on metal | Potential at centre (kV) | Same with no plasma |
|---|---|---|---|---|---|
| -300 | 0.66 | 0 | 0.86 | 33 ± 14 | -272 |
| -100 | 2.48 | 0 | 0.36 | 36 ± 16 | -91 |
| -30 | 3.28 | 0 | 0.14 | 45 ± 11 | -27 |
| 0 | 3.57 | 0.0001 | 0.04 | 43 ± 8 | 0 |
| +30 | 3.80 | 0.0002 | 0.005 | 42 ± 11 | 27 |
| +100 | 4.15 | 0.001 | 0 | 50 ± 9 | 91 |
| +300 | 4.45 | 0.35 | 0 | 98 ± 14 | 272 |

- The plasma sits near +40 kV whatever the metal is at between -300 and +100 kV: it screens the voltage.
- Positive metal lengthens the holding time by 16% at 100 kV for almost no landing. At 300 kV it gains 25% and
  a third of the electrons land on the metal, each having gained up to 300 keV from the supply.
- Negative metal pulls the ions on to itself.
- Metal 1 mm from the ring leak is worse at every voltage (2.31 ns at 0 V): the plasma lands on it.

The CPU checks above were made with scripts kept outside the repository (`/home/ubuntu/warpx/plugcheck`).
