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
- the potential at the centre, on the axis in a coil and in the gap at the coil radius, from the last snapshot,
  beside the same three with no plasma;
- holding times that count what lands on the metal as lost.
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
| Particles are removed at the metal: where the landed particles are | on the hole's face and the faces towards the mid-plane, in the 102 particles written (faces at 0.3 of a cell) |
| Particles are all counted: rate lost (two counting shells plus the metal) against feed less growth, in a 1.2 ns run | electrons 0.452 against 0.446 of the feed; ions 0.468 against 0.446 (faces at 0.3 of a cell) |
| Gauss's law off the axis, 100 kV, at 1.6 ns | error 1.3e-10 of the charge density, both away from the metal and within two cells of it. With the faces at 0.3 of a cell it was 0.024 within two cells of the metal at 0.8 ns, and growing |
| Gauss's law in the cells on the axis | error 3.0 times the rms charge density there at 1.6 ns (2.1 at 0.8 ns). The same deck with no metal gives 2.0 at 0.8 ns, so this is not from the metal. It is the noise on the axis described in [park-vs-warpx.md](park-vs-warpx.md), section 6 |

## Not checked yet

- Whether the plasma's results change with the mesh. Campaign `casing1` has three cases at 256 cells for this.
- Gauss's law late in a full run. Every run's `measured.json` now carries it.
- Whether the error on the axis matters to these runs. Without metal, runs with 4 times the particles gave the
  same widths and a holding time 6% longer.
- The particle count in a settled run. The row above is from a run still filling.
- Any size but 15.
- The executable built for GPUs. All the rows above are from the CPU one.

Until the first two pass, numbers from these runs are provisional.

The CPU checks above were made with scripts kept outside the repository (`/home/ubuntu/warpx/plugcheck`).
