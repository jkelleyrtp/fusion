# Patches to WarpX 26.10

The cluster build applies every file in `warpx/patches/` to the WarpX 26.10 tag. Each changes what the particles
feel, so each has its check recorded here. All are off unless a deck asks for them.

## `ionization-secondary-energy.patch`

**What it changes.** Stock `background_mcc` ionisation gives the two outgoing electrons half the remaining energy
each and scatters both isotropically. At keV energies most ejected electrons are slow and the incident electron
is barely deflected. With `<collision_name>.ionization_secondary_energy_scale = w` (eV) the ejected energy `W`
is drawn from `1/(W² + w²)` on `[0, (E − E_ion)/2]` (Opal et al., J. Chem. Phys. 55, 4100, 1971), the ejected
electron is isotropic, and the incident electron keeps its direction and the rest of the energy.

**Check.** `warpx/cusp/inputs_3d_ionization_check` with `check_ionization.py`: a monoenergetic electron beam in
a uniform hydrogen box, CPU build.

| Beam energy | Ion count against density × cross-section × speed | Energy removed per ionisation | Ejected spectrum |
|---|---|---|---|
| 100 eV, 1 keV, 8 keV | within 0.5–1.5% | the ionisation energy, as set | matches the sampled law |

The cross-section table `h2_ionization.dat` is within 3% of the NIST values. Not checked: the angular
distribution of the ejected electron against measurement (it is taken as isotropic), and the GPU build beyond
the campaign `s6` runs finishing without error.

## `coil-field-on-grid.patch`

**What it changes.** `particles.B_ext_particle_init_style = parse_B_ext_particle_function` evaluates the coil
field expression for every particle on every step. With `particles.B_ext_particle_on_grid = 1` the same
expression is evaluated once on the mesh and added to the field the particles gather, so the particles see the
coil field interpolated from the mesh. The expression must not depend on time. Field-energy and field-probe
diagnostics keep reporting the plasma's field alone.

**What it costs.** The coil field is now only as accurate as the mesh interpolation, which matters near the
coil conductors where it varies fastest.

**Check 1: one electron against an independent integration** (`inputs_3d_orbit_check`, `check_orbit.py`, CPU
build, 16 kA-turns, position error after 150 ps):

| Coil field | Error |
|---|---|
| per particle | 85 nm |
| on a 128-cell mesh | 87 nm |
| on a 64-cell mesh | 1660 nm |

**Check 2: matched production runs on B200 GPUs** (campaign `og1` against the per-particle originals):

| Deck | Pairs | Largest change in held particles, loss times, pressures, well depth | Speed |
|---|---|---|---|
| `inputs_3d_cusp_beta` (128³, 192³, 256³) | 5 | 0.5%, the spread between seeds | 5–12× |
| `inputs_3d_cusp_fed` | 1 | 0.1% | 10× |
| `inputs_3d_cusp_cage` (electrodes) | 2 | 0.5%; centre voltage moves 7 V in an 8.6 kV well | 3× |

The leak-stream half-width changes by up to 3%, against 2% between seeds. The largest dent in the field along a
single probe line is dominated by noise in both modes (it varies several-fold between seeds) and is not a
usable comparison.

**Check 3: the cylindrical build, with periodic ends and a restart** (`inputs_rz_picket_fed`, 96 radial cells,
1280 steps on a CPU; a short filling run, not a result):

| Run | Electrons lost | Ions lost | Electron energy (J) | Ion energy (J) |
|---|---|---|---|---|
| field per particle | 4.33e12 | 2.43e12 | 4.129 | 8.201 |
| field on the mesh | 4.28e12 | 2.40e12 | 4.078 | 8.254 |
| field on the mesh, second seed | 4.37e12 | 2.51e12 | 4.049 | 8.241 |

The two modes differ by 1% in particles lost and in energy, which is the spread between seeds. A run stopped at
step 400 and started again from its checkpoint holds the same number of electrons at step 800 as an
uninterrupted one to 0.1%, and beyond the coils its field differs from the coil field by 1.2% (uninterrupted:
1.1%), so the coil field is neither lost nor added twice on restart. At step 0 the field on the mesh is within
0.05% of an endless row of coils on the coil plane.

With the option on, the field written to plot files includes the coil field; with it off it does not.
`analyze_picket.py` relies on the former.

**Not checked.** Agreement between the two modes on more than one GPU (with or without a restart), and meshes
coarser than 128 cells across the device in 3D.

## `flux-paired.patch`

**What it changes.** With `<species>.<source>.flux_paired = 1`, particles made by `NFluxPerCell` start on the
source plane at places fixed by the cell and the step, so that electrons and ions fed through the same plane
start on top of each other. Without it, electromagnetic runs leave a growing layer of charge on the plane that
the fields can never remove. The fault, the evidence and the checks are in `flux-injection-charge.md`.

**Status.** Not reviewed. Gauss's law at the source goes from an error of a quarter of the charge density to
round-off in 3D and in 2D. On full GPU runs the plasma stuck at the gun mouths goes from 3.4% of what was fired
to 0.1%, and centre-fed holding times are unchanged within 1%.
