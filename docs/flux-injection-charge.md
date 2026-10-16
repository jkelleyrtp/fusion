# Charge left behind by WarpX flux injection in electromagnetic runs

Status: found 2026-10-16. The fix below is written (`warpx/patches/flux-paired.patch`) and on in the three fed
decks. It has passed the Gauss's-law check; the checks on full runs are on the cluster. It has not been reviewed,
so results that use it must say so. Affects every deck that feeds plasma with `NFluxPerCell` while Maxwell's
equations are solved: `inputs_3d_cusp_jets`, `inputs_3d_cusp_fed`, `inputs_rz_spindle_fed`.

## What goes wrong

The electromagnetic solver never solves Gauss's law. It advances E from the current the particles deposit, and
that keeps `div E = rho / eps0` true only if every charge arrives where it is by moving there. A particle made
by flux injection appears at its first position without any current. From then on the fields behave as if a
fixed charge of the opposite sign sat at the place the particle was born.

Electrons and ions are injected as separate species, at independent random places on the source plane, and
WarpX then moves each a random fraction of a step along its own velocity before the first push
(`AddPlasmaFlux`, "Update particle position by a random `t_fract`"). Electrons are faster, so they are born
deeper. Their fixed positive stand-ins therefore sit, on average, `0.5 * mean(vz) * dt` further in than the
ions' negative ones. The source plane becomes a fixed double layer whose strength grows with everything ever
fired. Real plasma is then trapped on it until it cancels it: electrons on the inner side, ions on the plane.

## Evidence

- `jet1/j_off` (coils off, guns stop at 60 ns), particles in the plotfile at 80 ns: 85% of the electrons and
  97% of the ions left in the box sit in a slab at the gun mouths, electrons at 1.85-1.90 a and ions at
  1.90-1.95 a from the centre, with keV energies and no net motion. Nothing physical holds plasma there.
- The amount matches the mechanism: fired charge per mouth area 1.7 C/m2, times depth difference 13 um over cell
  390 um, gives 0.057 C/m2 held; the slab holds 1e13 particles per mouth, 0.057 C/m2.
- The radial histograms show the slab growing in proportion to time while the guns fire, in every jet run, and
  the number inside the cage falling as it grows (`j_32k`: 1.3 ns of feed at 13 ns, 0.36 ns at 60 ns).
- Centre-fed runs have the same layer on the feed disc. Counted in the last plotfile of each run, as a share of
  the ions in the box:

  | Run | When | Share in the layer |
  |---|---|---|
  | `fed2/g_f1e22_128k` (3D, 128 kA-turns) | 15 ns after the feed stops | 0.5% |
  | `fed1/f3e23_32k` (3D, 32 kA-turns) | 15 ns after the feed stops | 2.8% |
  | `fed2/g_f1e22_off` (3D, coils off) | 15 ns after the feed stops | 44% |
  | `sp1/sp_16k_f1e23_nr256` (2D, 16 kA-turns) | feed still on | 3.3% |
  | `sp1/sp_off_f1e23` (2D, coils off) | feed still on | 11% |

  The 3D holding times are measured while the feed is on. The layer then is under 1% of what is held with the
  coils on and about 2% with them off (`g_f1e22_off`: 4.9e11 ions in the layer against 2.6e13 held).

## What it means for results so far

- `jet1`, `jet2`: the capture and holding numbers are not usable. The layer sits in the path of the jet and
  grows through the run.
- `fed1`, `fed2` (3D): holding times while the feed is on stand to a few percent by count. What is left after the
  feed stops with the coils off is mostly the layer.
- `sp1` (2D): 3% of what is held with the coils on and 11% with them off is the layer.
- The count is not the whole effect: the layer also sits in the middle of the plasma. Repeats with the fix
  (`fed3`, `sp2`) are the test of that.

## The fix (not yet reviewed)

`warpx/patches/flux-paired.patch` adds an option to `AddPlasmaFlux`, per injection source, `flux_paired = 1`:

1. The place of each new particle on the source plane, and the rounding of the number made in a cell, come from a
   hash of the cell's index in the whole domain, the step number, the flux direction and the particle's index in
   the cell, not from the shared random stream. Two species with the same plane, flux function and
   `num_particles_per_cell` then make their particles at the same places.
2. The random move along the velocity is skipped, so both start on the plane itself.

Every electron then starts on top of an ion, the two stand-ins cancel exactly, and all later motion deposits
current as usual. The cost is that particles enter in sheets one step apart, `v*dt` thick, far below a cell.
Momenta still come from the shared random stream. `tests/test_jets.py` checks that every source in the three
decks is paired and that the two species give WarpX identical source lines.

## Checks

Done, CPU build, 50 to 100 steps, same deck with the option on and off:

| Case | `eps0*div E - rho` at the source, rms (C/m3) | `rho` there, rms (C/m3) |
|---|---|---|
| 3D guns, 64 cells, option off | 2.5e-2 | 0.1 |
| 3D guns, 64 cells, option on | 1e-10 | 0.1 |
| 2D spindle feed, 128 cells, option off | 0.65 | 6 |
| 2D spindle feed, 128 cells, option on | 4e-9 | 6 |

With the option on, what error remains in the 3D box is next to the walls and coil rings, where absorbed
particles leave their charge on the conductor, and is the same with the option off.

Still to come, from the cluster:

- `jet3/p_off` against `jet3/p_off_stock`: coils off, guns stop at 60 ns; nothing should be left at the mouths
  at 80 ns with the option on.
- `jet3/p_32k` against `jet3/p_32k_stock`: the number inside the cage should stop falling while the guns fire.
- `fed3`: six centre-fed cases repeated with the option on, two with it off on the same build.

## A separate fault on the axis of the 2D runs

In the cylindrical runs `eps0*div E - rho` is at round-off everywhere except the ring of cells on the axis, where
it is as large as `rho` itself, with the option on or off. It tracks the charge on the axis rather than piling up
(1600-step test). The 2D runs also show a density spike one cell wide on the axis through the coils (2.4 times
the density next to it for electrons in `sp_16k_f1e23_nr256`; a dip with the coils off). The stream widths are
now measured from outside that cell (`stream_through_coil`). One cell is 0.04% of the stream's area, so the
holding times are not affected, but nothing within two cells of the axis in a 2D run should be read as physics.
