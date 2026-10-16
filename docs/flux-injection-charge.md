# Charge left behind by WarpX flux injection in electromagnetic runs

Status: found 2026-10-16. Fix proposed below, not yet reviewed. Affects every deck that feeds plasma with
`NFluxPerCell` while Maxwell's equations are solved: `inputs_3d_cusp_jets`, `inputs_3d_cusp_fed`,
`inputs_rz_spindle_fed`.

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
- Centre-fed runs have the same layer on the feed disc, but there it is a small share of what is held with the
  coils on: 0.5% of the ions in `fed2/g_f1e22_128k`, 2.8% in `fed1/f3e23_32k`, both at 40 ns. With the coils off
  (`fed2/g_f1e22_off`) 44% of the ions still in the box at 40 ns are in it.

## What it means for results so far

- `jet1`, `jet2`: the capture and holding numbers are not usable. The layer sits in the path of the jet and
  grows through the run.
- `fed1`, `fed2`, `sp1` with coils on: holding times stand to a few percent. Counts after the feed stops with
  the coils off do not.

## Proposed fix (needs review before results that use it are reported)

Patch `AddPlasmaFlux` with an option, per injection source, `flux_paired = 1`:

1. The place of each new particle on the source plane, and the rounding of the number made in a cell, come from a
   hash of the cell, the particle's index in the cell and the step number, not from the shared random stream. Two
   species with the same flux function and `num_particles_per_cell` then make their particles at the same places.
2. The random move along the velocity is skipped, so both start on the plane itself.

Every electron then starts on top of an ion, the two stand-ins cancel exactly, and all later motion deposits
current as usual. The cost is that particles enter in sheets one step apart, `v*dt` thick, far below a cell.
Momenta still come from the shared random stream.

Checks to make: (a) coils off, fire for 1 ns, stop, wait 2 ns: nothing left at the mouths, against about 3% of
what was fired without the option; (b) the number fired per second is unchanged; (c) `div E - rho/eps0` summed
over the source region stays at round-off; (d) a centre-fed case repeated with the option gives the same
holding time within the few percent above.
