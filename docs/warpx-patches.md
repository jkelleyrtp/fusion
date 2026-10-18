# Patches to WarpX 26.10

The cluster build applies every file in `warpx/patches/` to the WarpX 26.10 tag. Each changes what the particles
feel, so each has its check recorded here. All are off unless a deck asks for them, except
`crop-absorbing-walls-only.patch`, which changes what an existing setting does at walls that send particles back.

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

## `crop-absorbing-walls-only.patch`

**What it changes.** `particles.crop_on_PEC_boundary = 1` cuts each particle's step off at a conducting wall
before its current is laid down ([wall-charge.md](wall-charge.md)). That is right at a wall that absorbs: the
particle is gone. At a wall that sends particles back (`reflecting` or `thermal`) it is wrong: the particle
reappears inside, the part of its step beyond the wall is never laid down, and the fields keep a charge at the
wall that no particle carries. WarpX already folds that part of the step back into the mesh for such walls
(`ApplyReflectiveBoundarytoJfield`), so the patch only stops the cropping there. Walls that absorb are untouched.

**How the fault was found.** The closed-leak cases of `iso2` (two-coil device, one wall reflecting). In
`coils_z15_x27` at 48 ns the electric field holds +6.0e14 e in the last six cells at the reflecting side wall
and the particles there carry −2.5e14 e; at the absorbing end walls of the same run the two agree to 5%. The
false charge is positive (electrons reach the wall more often than ions), draws electrons onto the wall and
pushes ions off it.

**Check.** The same case run three ways on this machine's CPUs to 2 ns (128 radial cells). Charge in the last
six cells at each wall, in electron charges: what the particles carry / what the divergence of the electric
field gives. The divergence is taken by centred differences of the cell-centred snapshot and is good to 5 to 8%
where the books balance (the "elsewhere" row is the reference).

| | Cropping on, unpatched | Cropping off | Cropping on, patched |
|---|---|---|---|
| Reflecting side wall | +3.7e12 / +1.50e13 | +5.1e12 / +5.4e12 | +3.6e12 / +3.8e12 |
| Absorbing end walls | +1.6e12 / +1.7e12 | −2.9e12 / +1.31e13 | +1.5e12 / +1.6e12 |
| Elsewhere | +5.11e12 / +5.11e12 | +6.76e12 / +6.75e12 | +5.36e12 / +5.36e12 |

Only the patched run balances at both kinds of wall.

**Check on GPUs.** The size-15 closed-leak cases of `iso2` run again as `iso3` on the patched build (128 radial
cells, same measure as the table above; the last snapshot is at 47 ns).
At size 60 (512 radial cells, 27× feed, at 77 ns) the two agree more closely still: at the reflecting wall
`coils_z60_x27` has +6.71e13 against +6.88e13 and `gap_z60_x27` +6.96e13 against +7.13e13.

| Case | Reflecting wall | Absorbing wall | Elsewhere | Electric field energy over plasma energy |
|---|---|---|---|---|
| `coils_z15_x27`, unpatched, 10 ns | −2.6e13 / +1.24e14 | +1.00e13 / +1.05e13 | −1.15e13 / −1.15e13 | 0.35 at the end |
| `coils_z15_x27`, patched, 10 ns | +2.1e13 / +2.2e13 | +1.07e13 / +1.12e13 | −9.1e12 / −9.1e12 | |
| `coils_z15_x27`, patched, 47 ns | +2.1e13 / +2.3e13 | +1.18e13 / +1.27e13 | −9.5e12 / −9.5e12 | 0.028 |
| `gap_z15_x27`, unpatched, 10 ns | −8.2e12 / +2.9e13 | +8.2e12 / +8.6e12 | +1.79e12 / +1.80e12 | 0.10 at the end |
| `gap_z15_x27`, patched, 47 ns | +1.43e13 / +1.53e13 | +9.9e12 / +1.04e13 | +1.17e12 / +1.16e12 | 0.050 |
| `coils_z15_x3`, patched, 47 ns | +6.4e12 / +6.7e12 | +6.6e11 / +6.8e11 | +7.18e12 / +7.19e12 | 0.028 |

Patched, the two columns agree at every wall to the 5 to 8% the differencing allows, the electric field energy
is 3 to 5% of the plasma's at all four feeds (4 to 7% with both leaks open), and ions outnumber electrons by 1 to
5%, the same sign as with both leaks open. Turning cropping off everywhere is not a substitute: the four
`nocrop_*` cases of `iso2` end with electric field energy 0.24 to 3.0 times the plasma's.

**Status.** Not reviewed. Checked in 2D cylindrical geometry only, with the explicit pusher; the implicit
pusher's copy of the same test is changed the same way and not run. Every run with a reflecting wall and
cropping on that finished before the patch is affected and does not count: the closed-leak cases of `iso1` and
`iso2`. The mirror-end picket cases turned out not to be: three of `pw21` run again in `iso3` on the patched
build (`pw_s0.125_h1.0_ppc16_mirror`, `pw_s0.25_h1.0_long_ppc8_mirror`, `pw_s0.5_h1.0_mirror`) give holding
times of 6.43, 6.99 and 10.58 ns against 6.40, 6.99 and 10.50 ns before, as they should: their
reflecting ends are magnetic mirrors (`pmc`), not conductors, so cropping never applied there. A both-open case run again (`both_z15_x3_patched`) agrees with `both_z15_x3` to 2% in everything but the
on-axis density ratios, which are noisy.
