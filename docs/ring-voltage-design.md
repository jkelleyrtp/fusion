# Holding the six-coil rings at chosen voltages in WarpX 26.10, without changing WarpX's code

Helper report for the coordinating session (branch `devin/1789237491-pic-research`, PR #5). Nothing was pushed, no GPU or broker jobs were used, and the WarpX source was not modified. All tests below ran on this machine's CPU at 64³ cells. They show that the methods *work mechanically*. They are not physics results.

## 1. Results first

| # | Finding | Basis |
|---|---|---|
| 1 | **The electromagnetic (Yee) solver has no setting that holds a conductor at a voltage or charge.** `warpx.eb_potential(x,y,z,t)` only sets the starting field at t = 0. After that the rings float. | Docs and source read; ran it (§4.1, test T2) |
| 2 | **A ring's voltage can come from position alone.** `eb_potential` is a function of x, y, z, so one expression can put the rings at V and the wall at 0, or give each ring its own value. | Ran it: probe line integral gave 100.01 kV for a 100 kV setting (T2) |
| 3 | **Joining each ring to the wall with a thin conducting stalk grounds it (0 V). This works.** Ring voltage stayed at 0 ± 20 kV, against +140 to +170 kV for floating rings in the same run. | Ran it (T5, T4) |
| 4 | **Recommended for chosen voltages: stalks plus an added static field ("superposition").** Run the normal electromagnetic deck with the rings grounded by stalks. Add, as a fixed external field on the particles, the vacuum field of "rings at 1 V, wall at 0 V", multiplied by the target voltage. Because the field equations are linear, the sum equals rings held at V. No source change is needed, but WarpX must be built with openPMD. Held 100 kV → 104 ± 13 kV and 200 kV → 197 ± 12 kV (time-averaged over 0.4–1.0 ns). | Ran it (T6, T7); the exactness argument is in §4.4 |
| 5 | **Pre-charging a floating ring does not last.** A ring started at +100 kV reached about +200 kV within about 0.4 ns, which is where an uncharged floating ring settles too (+140 to +170 kV). Production runs last 12–30 ns. | Ran it (T3, T4) |
| 6 | **The electrostatic-plus-magnetostatic solver (`warpx.do_electrostatic = labframe-electromagnetostatic`) keeps the plasma's own magnetic field and holds `eb_potential` exactly at every step.** It runs on this six-coil deck with its embedded boundaries. It drops inductive electric fields and fine-mesh refinement, and was about 10–20× slower per step on CPU. Use it only as a cross-check. | Docs and source read; ran it (T8) |
| 7 | **Measuring ring voltage:** integrate E along `FieldProbe` lines that run from inside a ring to inside the wall. **Measuring absorbed power:** use the scraped-particle buffer for embedded boundaries plus a geometric ring/wall classifier. Both need nothing beyond diagnostics, but scraping also needs openPMD. Production builds currently use `-DWarpX_OPENPMD=OFF` (`warpx/campaign.py`, line 63). | Ran both (§5) |
| 8 | **In every test, electrons never reached the rings. Only ions did.** The ion power on the rings was 230 MW at 0 V, 130 MW at 100 kV and 95 MW at 200 kV. These are coarse, 1 ns, unconverged numbers that only show the diagnostic works. | Ran it (T5–T7, T4b) |

**Bottom line:** chosen ring voltages are possible without WarpX source changes. Use stalks for 0 V, and stalks plus a voltage-scaled external field map for +50/+100/+200 kV. The one requirement outside the input file is turning on openPMD in the build. That flag is in this repository's `warpx/campaign.py`, not in WarpX itself.

## 2. Terms (each defined once)

| Term | Meaning here |
|---|---|
| Embedded boundary (EB) | A solid surface cut into the simulation grid by `warpx.eb_implicit_function`. Points where the function is > 0 are inside metal. In this deck the metal is the spherical wall and the six rings. |
| Floating conductor | A piece of metal joined to nothing. Its voltage is set by whatever charge lands on it. |
| Grounded | Joined to the wall, so it has the same voltage as the wall (0 V). |
| Electromagnetic (EM) / Yee solver | Advances the full Maxwell equations in time. It includes magnetic fields made by plasma currents and electric fields induced by changing magnetic fields. This is the current deck (`algo.maxwell_solver = yee`). |
| Electrostatic (ES) solver | Recomputes only the electric field from the charges at every step, using Poisson's equation. Conductors can be held at fixed voltages, but there is no plasma magnetic field. |
| Magnetostatic | Recomputes the magnetic field of the plasma currents at every step as if the currents were steady. It omits the electric field induced by changing currents. |
| Superposition | Linear equations let solutions be added. (Field of plasma with grounded rings) + (field of rings at V with no plasma) = field of plasma with rings at V. |
| Unit field map | The vacuum electric field with the rings at 1 V and the wall at 0 V, saved to a file. |
| openPMD | The file format WarpX uses to read field maps and to write scraped particles. It is a build option. |
| Scraped-particle buffer | WarpX's record of each particle absorbed by an embedded boundary: position, momentum, weight and time. |
| FieldProbe | A WarpX diagnostic that samples E and B at points along a line. |
| `ChargeOnEB` | A WarpX diagnostic that adds up the charge on an embedded-boundary surface, ε₀∮E·dS, over a chosen region. |
| Capacitance C | Charge per volt of a conductor, Q = C·V. A floating ring's voltage changes at dV/dt = I/C, where I is the net current landing on it. |
| Pressure ratio | Plasma pressure divided by magnetic pressure (`docs/progress-2026-10-17.md`). |

## 3. Options table

Status key: **works** = run here and behaved as intended. **Does not work** = run or source shows it cannot do the job. **Untested** = not run.

| Option | Status | What it gives | Evidence | GPU / EB compatibility |
|---|---|---|---|---|
| A. EM Yee, as now (floating rings) | Works as a reference. **Does not work** for a chosen voltage | No input sets a conductor's voltage or charge during the run | Docs `parameters.rst` §`warpx.eb_potential`: "When using other solvers (e.g. Maxwell solver), setting this variable will trigger an electrostatic solve at t=0". Source `WarpXInitData.cpp`: this solve is the only use outside ES modes. T1: floating rings reach +140 to +170 kV | Production path today |
| B. EM + stalks joining the rings to the wall | **Works** for 0 V | Rings at the wall's voltage, with full EM physics | T5: 0 ± 20 kV over 1 ns. A connectivity check (§7.2) shows one connected conductor at 64, 96 and 128 cells. Needs `eb2.cover_multiple_cuts = 1`, or WarpX aborts with "more than 2 cuts not supported" | EB geometry only, so GPU-neutral |
| C. ES `labframe` + `eb_potential` | Works, but loses the plasma's magnetic field | Voltage held exactly at every step | T2b vacuum check. Docs: "used in order to compute the potential … at each timestep" | Needs MLMG settings: the default precision 1e-11 failed to converge (`MLMG failed`). `warpx.self_fields_required_precision = 1e-7` and `warpx.self_fields_max_iters = 1000` worked |
| D. ES-plus-magnetostatic `labframe-electromagnetostatic` + `eb_potential` | **Works** (T8, 300 steps) | Exact voltage plus the plasma's steady magnetic field (plasma self-B energy 0.032 J against 0.054 J in the EM floating run at step 300; `FieldEnergy` B column, coil field excluded) | Docs (`electrostatic_pic.rst`, read in full). Source `WarpXEvolve.cpp`: "Time varying A contribution to E field is neglected". `MagnetostaticSolver.cpp` asserts `max_level == 0`. WarpX CI test `Examples/Tests/magnetostatic_eb/inputs_test_3d_magnetostatic_eb` uses 3D EB with `eb_potential` | One mesh level only. FFT solver rejected. About 1.3 s/step against about 0.1 s/step for EM on CPU at 64³ |
| E. External particle E field, analytic (`particles.E_ext_particle_init_style = parse_E_ext_particle_function`) | Not useful | There is no closed form for the vacuum field of six tori inside a sphere | Docs list the parameter. It cannot be written down accurately | — |
| F. External particle E field from file (`particles.E_ext_particle_init_style = read_from_file`) + stalks = **superposition** | **Works** (T6, T7) | Rings effectively at V with full EM physics. Per-ring and time-varying voltages are possible through the multi-field mode `particles.E_ext_particle_fields = …` and `particles.<name>.read_fields_E_dependency(t)` | Source `WarpXComm.cpp`/`GetExternalFields.cpp`: the file field is added to `Efield_aux`, which particles gather, at every step. `ExternalField.cpp` loads it with `amrex::ParallelFor` (GPU-capable). Needs `-DWarpX_OPENPMD=ON` | Data loaded on device. Memory cost: one extra 3-component field |
| G. External **grid** E field (`warpx.E_ext_grid_init_style = read_from_file` or `parse_E_ext_grid_function`) | Does not work in EM | In EM it is only an initial value, the same as option A | Docs and source (`WarpXInitData.cpp`): in ES/magnetostatic modes it is added after each solve, which option D does better with `eb_potential` | — |
| H. Pre-charge floating rings (`eb_potential` in EM) | Works mechanically. **Does not work** as a voltage control | Starts at V, then drifts to the floating value in about 0.4 ns | T3: 100 kV → about 200 kV by 0.4–0.6 ns. There is no input to place a chosen *charge* directly. `eb_potential` sets the starting *voltage* | — |
| I. Separate isolated "reservoir" capacitor (a large thin-gap shell joined to the rings) | Untested, idea only | Would slow the drift by raising C | Estimate: about 130 pF for a 0.5 mm gap over the wall area, giving about 2 kV/ns at 300 A. Needs domain changes | — |

## 4. Details per option

### 4.1 EM solver: no voltage or charge control (verified)
- `warpx.eb_potential(x,y,z,t)` (read in `PoissonBoundaryHandler.cpp`) sets `m_boundary_potential_specified`. In `WarpXInitData.cpp` this triggers one `ComputeSpaceChargeField` at t = 0, also when no electrostatic solver is chosen. It is not used again in EM runs.
- After that, the Yee solver advances E only through ∇×B and the deposited current J. A ring keeps its starting charge and gains or loses charge as particles land on it, so it floats.
- T2 (vacuum, no plasma, 200 steps): ring-to-wall voltage was 100.01 kV at step 0 and still 100.01 kV at step 200. The starting field persists exactly when no particles are present.

### 4.2 Stalks (verified at 64³; production resolution untested)
- Stalks are rods of radius `rs`, parallel to each coil axis and passing through the ring's tube centre at 22.5° around the ring. Each runs from the ring's mid-plane out through the wall. The wall is at |r| = 2.4a and the ring at 1.3a, so a rod is about 1.1a long. They sit on the far side of the ring from the plasma centre.
- Exact geometry, generated by `mkgeom.py` (§7.3) and used in T5–T7:
```
warpx.eb_implicit_function = "max(max(max(max(max(max(max(max(max(max(max(max(x*x+y*y+z*z-rw*rw,(rm*rm-(sqrt(y*y+z*z)-rc)**2-(x-(1)*dc)**2)),min(rs*rs-(y-0.9238795325*rc)**2-(z-0.3826834324*rc)**2,(1)*x-dc)),(rm*rm-(sqrt(y*y+z*z)-rc)**2-(x-(-1)*dc)**2)),min(rs*rs-(y-0.9238795325*rc)**2-(z-0.3826834324*rc)**2,(-1)*x-dc)),(rm*rm-(sqrt(x*x+z*z)-rc)**2-(y-(1)*dc)**2)),min(rs*rs-(z-0.9238795325*rc)**2-(x-0.3826834324*rc)**2,(1)*y-dc)),(rm*rm-(sqrt(x*x+z*z)-rc)**2-(y-(-1)*dc)**2)),min(rs*rs-(z-0.9238795325*rc)**2-(x-0.3826834324*rc)**2,(-1)*y-dc)),(rm*rm-(sqrt(x*x+y*y)-rc)**2-(z-(1)*dc)**2)),min(rs*rs-(x-0.9238795325*rc)**2-(y-0.3826834324*rc)**2,(1)*z-dc)),(rm*rm-(sqrt(x*x+y*y)-rc)**2-(z-(-1)*dc)**2)),min(rs*rs-(x-0.9238795325*rc)**2-(y-0.3826834324*rc)**2,(-1)*z-dc))"
my_constants.rs = 0.06*a
eb2.cover_multiple_cuts = 1
```
- The "stub" control is the same rods with a gap of 2·`rs` to the ring. It keeps the same obstacle in the leak paths but leaves the rings floating. It is generated by replacing each `(±1)*x-dc` with `(±1)*x-(dc+rm+2*rs)`, and likewise for y and z.
- Resolution: production uses 512 cells (cell = 0.0098a), so `rs = 0.06a` is about 6 cells in radius. T5 used `rs = 0.12a` at 64 cells (about 1.5 cells).

### 4.3 Electrostatic and ES-plus-magnetostatic (verified to run; physics loss is from the source)
- The modes are listed in docs: `warpx.do_electrostatic = labframe | labframe-electromagnetostatic | labframe-effective-potential | relativistic`.
- **What `labframe` loses:** the plasma's magnetic field, B is not computed from the plasma current. At a pressure ratio near 1, that field is what pushes the coil field out, so plain ES cannot answer the question.
- **What `labframe-electromagnetostatic` keeps and loses:** it keeps B = ∇×A, with ∇²A = −μ₀J solved at every step (docs `electrostatic_pic.rst`, read in full). It loses the induced electric field −∂A/∂t (source comment above), electromagnetic waves, and fine-mesh refinement (`max_level == 0`). It works with the coil-field-on-grid patch, because `UpdateAuxiliaryData()` runs in this mode too. Use `algo.current_deposition = direct`, as the WarpX EB magnetostatic test does.
- **Semi-implicit Darwin is out:** its preconditioner requires periodic field boundaries (`DarwinMLMGPC.H`, `SemiImplicitDarwin.cpp`), and this deck has metal walls.
- Different voltages per ring are possible. The masks are constant on whole rings, because each ring lies entirely in its own wedge (for the +x ring, |y|, |z| ≤ 1.12a < x ≥ 1.18a):
```
warpx.eb_potential(x,y,z,t) = "Vr*(x*x+y*y+z*z<(0.9*rw)**2)"                       # all six rings at Vr, wall 0
warpx.eb_potential(x,y,z,t) = "Vx*(x>abs(y))*(x>abs(z))*(x*x+y*y+z*z<(0.9*rw)**2)"  # +x ring only
```
- The docs warn that the function "is also evaluated inside the embedded boundary … it is important to define this function in such a way that it is constant inside the embedded boundary". The masks above satisfy this.

### 4.4 External field from file, plus stalks: why it is self-consistent (argument from linearity; checked in tests)
- Maxwell's equations are linear in the charges, currents and boundary values. Split the field into two parts:
  1. The plasma's field computed with all metal at 0 V. The EM solver does this when stalks join the rings to the wall.
  2. The static vacuum field with the rings at V and the wall at 0, called V·E_unit. In vacuum it has zero curl and zero divergence, so it is a valid time-independent Maxwell solution with no sources.
- Their sum satisfies Maxwell with the rings at V. The particles feel the sum, so their motion and the charge and current they deposit are self-consistent. The EM solver never needs to see part 2.
- Reasons it is not exact:
  - Part 2 is computed without stalks. Near a stalk the total field does not satisfy the metal boundary condition. The stalk effectively has a voltage that falls from V to 0 along its length, like a resistive high-voltage support.
  - The map is interpolated from file.
  - It does not hold the voltage of anything except the shapes in the map.
- Diagnostics: `FieldProbe` reads `Efield_aux` (`FieldProbe.cpp`), which includes the file field, so the probe sees the full voltage (T6 confirmed this). `ChargeOnEB` reads `Efield_fp`, so it reports only the plasma-induced ring charge. The total ring charge is that value plus C·V. `FieldEnergy` excludes part 2.
- The reader ignores the openPMD `position` attribute and places samples at `gridGlobalOffset + i·dx` (`ExternalField.cpp`). WarpX's own Full-diagnostic openPMD output is cell-centred (`position = 0.5`), with `gridGlobalOffset = prob_lo`. Unfixed, the map is shifted by half a cell. The fix (§7.4) adds 0.5·dx to the offset.

### 4.5 Pre-charging and drift (measured at 64³)
- WarpX has no "initial charge on conductor" input. The way to start a ring at a chosen voltage is `eb_potential` in EM (option H), which gives the matching charge automatically.
- Measured, as the average of the three probe lines with spread over time:

| Run | 0–0.2 ns | 0.2–0.4 ns | 0.4–0.6 ns | 0.6–0.8 ns | 0.8–1.0 ns |
|---|---|---|---|---|---|
| Floating, start 0 V (T1) | 0.3 kV | 44 ± 33 | 143 ± 25 | 172 ± 46 | 155 ± 56 |
| Floating, start +100 kV (T3) | 100 | 138 ± 28 | 209 ± 33 | 199 ± 52 | 194 ± 53 |

- The drift is about +300 kV/ns while the rings charge. The precharge is forgotten in about 0.4 ns. A rough cross-check: the measured ion current onto the rings is 250–530 A, and C for six rings is about 3.4 pF from `ChargeOnEB` in vacuum (0.56 pF per ring), giving I/C ≈ 75–160 kV/ns. That is the same order.
- **Open question:** in the floating runs, ions kept arriving at about 250 A after 0.5 ns with no electrons, yet the voltage stopped rising. A constant net current should keep charging the ring. I did not resolve whether nearby plasma charge offsets it or whether absorbed charge is partly not retained near the metal.

## 5. Diagnostics

### 5.1 Ring voltage
Integrate E along a straight line from inside a ring's metal (its tube centre) to inside the wall. V_ring − V_wall = ∫E·dl. Add one line per ring direction to the deck:
```
vxp.type = FieldProbe
vxp.probe_geometry = Line
vxp.x_probe = dc
vxp.y_probe = 0.
vxp.z_probe = rc
vxp.x1_probe = 2.3*a
vxp.y1_probe = 0.
vxp.z1_probe = rc
vxp.resolution = 401
vxp.intervals = 200
```
`vyp` and `vzp` are the same with the axes rotated: for `vyp`, start (rc, dc, 0) and end (rc, 2.3a, 0); for `vzp`, start (0, rc, dc) and end (0, rc, 2.3a). The output has one row per point, with columns step, time, x, y, z, Ex, Ey, Ez, …; the integration script is in §7.1.

Accuracy checked here:

| Method | 100 kV setting read back |
|---|---|
| EM with t = 0 solve (T2), 64³ | 100.01 kV |
| ES `labframe` (T2b), 64³ | 107.65 kV |
| ES `labframe` (T2b), 96³ | 103.92 kV |
| ES-plus-magnetostatic (T8), 64³ | 107.5 kV |

The ES error shrinks with cell size. It looks like the gradient near cut cells. I infer it will be about 1% or less at 512³; this was not run.

Probe noise in EM runs with plasma: the time spread was 10–50 kV at 64³. Average over time and over the three rings. The two-standard-error resolution over 0.6 ns was about ±25 kV per ring at 64³.

`ChargeOnEB` is a cross-check for ring charge:
```
qring.type = ChargeOnEB
qring.intervals = 200
qring.weighting_function(x,y,z) = "(x*x+y*y+z*z<(0.9*rw)**2)"
```
Vacuum check: Q = 3.36e-7 C at 100 kV for six rings. The +x ring alone gave exactly 1/6. **Do not use** the equivalent wall mask: it gave −5.6e-7 C instead of −3.4e-7 C, which is not understood.

### 5.2 Power absorbed on rings (electrons and ions separately)
```
electrons.save_particles_at_eb = 1
ions.save_particles_at_eb = 1
diagnostics.diags_names = diag1 chk scr
scr.diag_type = BoundaryScraping
scr.format = openpmd
scr.openpmd_backend = h5
scr.intervals = 2000
```
- Each file holds only the particles scraped since the previous write, so read all of them. Each particle has `position`, `momentum` (SI), `weighting`, `timeScraped`, `stepScraped` and the surface normal `nx, ny, nz`.
- Classify a particle as a ring hit if its distance to the nearest ring surface is under 1.5 cells. This was clean in tests: ion ring hits lay between 0.16 cells inside and 1.0 cell outside the analytic ring surface, and no electron came closer than 4.0 cells. Particles away from both rings and wall are stalk hits.
- Power = Σ weight × kinetic energy over a time window, divided by its length. Current = Σ weight × charge, divided by the same length. The script is in §7.1.
- The build needs openPMD: `BoundaryScrapingDiagnostics.cpp` aborts with "You need to compile WarpX with openPMD support" otherwise.

T4b–T7, window 0.5–1.0 ns (coarse: only 106–218 ion macroparticles hit the rings in each run):

| Rings | Ring voltage measured | Electron power to rings | Ion power to rings | Ion current to rings | Ion mean energy on rings |
|---|---|---|---|---|---|
| Grounded by stalks (0 V) | 6 ± 13 kV | 0 | 231 MW | 531 A | 434 keV |
| Floating | 141 kV | 0 | 100 MW | 253 A | 395 keV |
| Superposition 100 kV | 104 ± 13 kV | 0 | 133 MW | 299 A | 444 keV |
| Superposition 200 kV | 197 ± 12 kV | 0 | 95 MW | 210 A | 455 keV |

### 5.3 Holding time and leak width
Keep the deck's existing diagnostics and reducers: `number`, `ethroat`/`ithroat` (throat histograms), `eout`/`iout`, and `erad`/`irad`. Use them unchanged, the same way as for the `hw1_wall_fix` cases, so results compare directly. One caution for the superposition cases: `FieldEnergy` excludes the applied ring field, so any energy budget must add the work done by the ring field on the particles.

## 6. Recommendation, cases and risks

### 6.1 Recommended method
1. **0 V:** use stalks (option B).
2. **+50/+100/+200 kV:** use stalks plus a voltage-scaled unit map (option F).
3. **Floating:** keep the existing deck as the reference.
4. **Cross-check:** run one `labframe-electromagnetostatic` case (option D) at 100 kV. If holding time and leak width agree with option F, the missing induced field is unimportant at this pressure. If they disagree, trust F, which is full EM.
5. **One prerequisite:** set `-DWarpX_OPENPMD=ON` in `warpx/campaign.py` line 63 (a Fusion change, not a WarpX source change), and make sure HDF5 is present in the build image. On this machine that required `libhdf5-dev`. openPMD-api was fetched by CMake.

**Proposed new deck** `warpx/cusp/inputs_3d_cusp_ringv`, not created. It is `inputs_3d_cusp_fed` plus the block below. List-valued settings cannot be passed through the one-line case format, which splits on spaces.
```
warpx.reduced_diags_names = number energy fields axis edge corner erad irad eout iout ethroat ithroat eke qring vxp vyp vzp
# + qring / vxp / vyp / vzp definitions from §5.1
# + the scraping block from §5.2
my_constants.rs = 0.06*a
my_constants.Vr = 0.
```

**Unit map (one-off; a single-step run, but its cost at 512³ was not measured).** Run once at the production grid, `ncell=512`, rings without stalks, EM mode, 1 step. Then apply the offset fix in §7.4:
```
my_constants.ncell = 512
my_constants.r0 = 0.
my_constants.feed = 0.
warpx.eb_potential(x,y,z,t) = "1.0*(x*x+y*y+z*z<(0.9*rw)**2)"
diagnostics.diags_names = unit
unit.diag_type = Full
unit.format = openpmd
unit.openpmd_backend = h5
unit.intervals = 1
unit.fields_to_plot = Ex Ey Ez
max_step = 1
```
At 512³ the file is about 3.2 GB. A 256³ map is about 0.4 GB, and WarpX interpolates it, but accuracy within one coarse cell of the rings is then reduced (untested). The geometry is the same at every device size here, because size is set by `coil_at`. One map therefore serves every case.

### 6.2 Cases
- Base = the `hw_78k_f2.4e23` line in `hw1_wall_fix.txt`, with pressure ratio about 0.9 at 1× per `docs/cusp-results.md`.
- `STALKS` = the full `warpx.eb_implicit_function=…` string from §4.2. `STUBS` = the gap version.
- `MAP` = path of the offset-fixed unit map.

| # | Name | Purpose | Changes against base (exact tokens) |
|---|---|---|---|
| 0 | `rv_check` | Cheap check: vacuum superposition and stalks at full grid. Expect V_ring = Vr within about 1% | `my_constants.r0=0. my_constants.feed=0. my_constants.tmax=1.5e-11 warpx.eb_implicit_function=STALKS eb2.cover_multiple_cuts=1 particles.E_ext_particle_init_style=read_from_file particles.read_fields_from_path=MAP particles.read_fields_E_dependency(t)=1e5` |
| 1 | `rv_78k_float` | Floating reference with the new diagnostics | (none) |
| 2 | `rv_78k_0kV` | Grounded rings | `warpx.eb_implicit_function=STALKS eb2.cover_multiple_cuts=1` |
| 3 | `rv_78k_stub` | Stalk-obstacle control with floating rings | `warpx.eb_implicit_function=STUBS eb2.cover_multiple_cuts=1` |
| 4 | `rv_78k_50kV` | Voltage scan | case 2 + `particles.E_ext_particle_init_style=read_from_file particles.read_fields_from_path=MAP particles.read_fields_E_dependency(t)=5e4` |
| 5 | `rv_78k_100kV` | Voltage scan | same, with `…E_dependency(t)=1e5` |
| 6 | `rv_78k_200kV` | Voltage scan | same, with `…E_dependency(t)=2e5` |
| 7 | `rv_78k_100kV_ems` | Physics cross-check (no induced E). Uses no stalks and no map | `warpx.do_electrostatic=labframe-electromagnetostatic algo.current_deposition=direct warpx.eb_potential(x,y,z,t)=1e5*(x*x+y*y+z*z<(0.9*rw)**2) warpx.self_fields_required_precision=1e-7 warpx.self_fields_max_iters=1000` (whether `particles.crop_on_PEC_boundary=1` matters in ES was not tested) |
| 8 | `rv_39k_100kV` | Size scan at fixed voltage | case 5 with `my_constants.coil_at=39210 my_constants.feed=1e+23 my_constants.tmax=1.2e-08` |
| 9 | `rv_157k_100kV` | Size scan at fixed voltage | case 5 with `my_constants.coil_at=156840 my_constants.feed=6e+23 my_constants.ppc_feed=0.125 my_constants.tmax=3e-08` |

- The existing no-ring control is `hr_78k_f2.4e23` in `hr1_no_rings.txt` (`my_constants.rm=0.`). It is not repeated here.
- The pressure ratio for cases 8 and 9 uses the existing size-scan feeds, which were not matched (`docs/cusp-results.md`: 0.63–0.67 at the smaller sizes). Matching it is the coordinator's call.
- For case 7, set its time step from the 3D ES limits. The base `dt` of 1.5e-13 s is well below them. I did not test `villasenor` deposition with ES, so it is switched to `direct`.

### 6.3 Open risks and limits
1. **openPMD in the GPU build** is untested here; only the CPU build with openPMD was tested. It needs HDF5 or ADIOS2 in the image and network access for CMake's fetch.
2. **Stalks are extra metal in the leak region.** Case 3 measures their effect. At 64³ the 0 V rings took 2× the ion current of floating rings. That comes mostly from the voltage difference, not necessarily from the stalks.
3. **The superposition is exact only if the stalks are ignored.** Each stalk carries a gradient of V/1.1a in the applied field, which is not a metal-boundary condition. The effect should be confined to near the stalks; that is inferred, not measured.
4. **Applied-field energy is not counted** in `FieldEnergy`, which matters for energy-balance checks.
5. **The ES-plus-magnetostatic cross-check** drops the induced electric field, is about 10–20× slower per step on CPU, and allows no refinement.
6. **Probe-line voltage is noisy in EM:** ±10–50 kV at 64³. Production resolution and particle counts should be better, but that is unmeasured.
7. **The `ChargeOnEB` wall-mask disagreement** and the floating-voltage plateau (§4.5) are not understood.
8. **All tests were 64³, 1 ns and coarse.** The production geometry has not been run at 512³. The numbers in §4.5 and §5.2 show that the diagnostics work. They are not physics results.
9. **Scientific scope:** this deck feeds particles from inside. `AGENTS.md` makes inside-born particles numerical controls only, not evidence about beam capture.

### 6.4 If a source change were wanted (proposal only; not needed for fixed voltages)
- The superposition already holds fixed voltages. The smallest WarpX change that would remove the openPMD dependency and the stalk inconsistency: at initialization, compute the Laplace field for `eb_potential` once, using the existing `AddBoundaryField` path. Then add it to `Efield_aux` at every step in `UpdateAuxiliaryData()`. This would be a new boolean such as `warpx.eb_potential_persistent = 1`.
- A truly *floating-with-set-charge* or *battery-with-internal-resistance* ring needs per-component ring charges. WarpX has no concept of embedded-boundary components, so that would be a larger change.

## 7. Tests run and scripts

Builds: WarpX 26.10 at `ec1660d961696c865c87c26728b7e248b5454082` with the three Fusion patches. Two 3D CPU builds: OMP, EB, no MPI, one with `-DWarpX_OPENPMD=OFF` and one with `=ON`. The small-test overlay changed the deck to `ncell=64`, `dt=1e-12`, the hot-case plasma (`n0=1e18`, `te=ti=1e5`, `mass_amu=0.035109`, `coil_at=78420`, `feed=2.4e23`, `ppc_feed=0.25`, `ppd=2`) and `particles.B_ext_particle_on_grid=1`. Runs were 1000 steps (1 ns) unless noted.

| ID | Run | Result |
|---|---|---|
| T1 | EM, floating rings | 0 → about 150 kV by 0.5 ns |
| T2 | EM vacuum, `eb_potential` = 100 kV mask, 200 steps | 100.01 kV, constant |
| T2b | ES `labframe` vacuum, 1 step, 64³ and 96³ | 107.65 / 103.92 kV. Default MLMG precision fails |
| T3 | EM, pre-charged to 100 kV | Drifts to about 200 kV by 0.5 ns |
| T4/T4b | EM floating, with scraping | §5.2 table |
| T5 | EM, stalks (`rs=0.12a`) | 0 ± 20 kV. Needs `eb2.cover_multiple_cuts=1` |
| T6/T7 | EM, stalks + unit map × 1e5 / × 2e5 | 104 ± 13 / 197 ± 12 kV (steps 400–1000) |
| T8 | ES-plus-magnetostatic + `eb_potential` 100 kV, 300 steps | Runs. 107 kV (probe bias) |

### 7.1 Voltage and power scripts
```python
# vstat: ring-to-wall voltage from FieldProbe line files
import numpy as np
def V(f):
    d = np.loadtxt(f, skiprows=1, ndmin=2); out = []
    for s in np.unique(d[:,0]):
        r = d[d[:,0]==s]
        out.append((s, np.sum(0.5*(r[1:,5:8]+r[:-1,5:8])*np.diff(r[:,2:5],axis=0))))
    return np.array(out)
```
```python
# scraped power: concatenate all diags/scr/particles_at_eb/*.h5; per species
ke = (np.sqrt(1+(px**2+py**2+pz**2)/(m*c)**2)-1)*m*c*c
def ring_dist(x,y,z):       # distance to the nearest ring surface
    d = np.full(x.shape, np.inf)
    for ax,(u,v) in ((x,(y,z)),(y,(x,z)),(z,(x,y))):
        for s in (1,-1):
            d = np.minimum(d, np.sqrt((np.sqrt(u*u+v*v)-rc)**2+(ax-s*dc)**2)-rm)
    return d
onring = ring_dist(x,y,z) < 1.5*dx
P_ring = np.sum(w[onring]*ke[onring]) / T;   I_ring = q*np.sum(w[onring]) / T
```

### 7.2 Stalk connectivity check
Evaluate the implicit function at cell centres, then label the connected regions where it is > 0 (`scipy.ndimage.label`).

| Geometry | Separate metal pieces |
|---|---|
| Stalks, 64³ (`rs` = 0.12a or 0.06a) | 1 |
| Stalks, 96³ (`rs` = 0.06a) | 1 |
| Stalks, 128³ (`rs` = 0.06a) | 1 |
| Rings only | 7 (wall + 6 rings) |

### 7.3 Geometry generator
```python
c, s = 0.9238795325, 0.3826834324
def ring(ax, sign):
    o = {'x': ('y','z'), 'y': ('x','z'), 'z': ('x','y')}[ax]
    return f"(rm*rm-(sqrt({o[0]}*{o[0]}+{o[1]}*{o[1]})-rc)**2-({ax}-({sign})*dc)**2)"
def stalk(ax, sign, gap="0"):
    u, v = {'x': ('y','z'), 'y': ('z','x'), 'z': ('x','y')}[ax]
    start = "dc" if gap == "0" else f"(dc+rm+{gap})"
    return f"min(rs*rs-({u}-{c}*rc)**2-({v}-{s}*rc)**2,({sign})*{ax}-{start})"
expr = "x*x+y*y+z*z-rw*rw"
for ax in "xyz":
    for sign in (1, -1):
        expr = f"max(max({expr},{ring(ax,sign)}),{stalk(ax,sign)})"   # use stalk(ax,sign,"2*rs") for stubs
```

### 7.4 Unit-map offset fix
```python
import h5py, numpy as np
f = h5py.File("unit_E_1V.h5", "r+"); E = f["data/0/fields/E"]          # iteration key may differ
E.attrs["gridGlobalOffset"] = E.attrs["gridGlobalOffset"] + 0.5*E.attrs["gridSpacing"]
for k in "xyz": E[k].attrs["position"] = np.zeros(3)
```
Note: the file's `axisLabels` are `z, y, x` with C data order. The reader accepts this (`ExternalField.cpp`).

## 8. Sources and how much of each was read

| Source | Read | Used for |
|---|---|---|
| `docs/progress-2026-10-17.md` | Full | Context, pressure-ratio definition |
| `docs/cusp-results.md` | Full | Base cases, pressure ratios |
| `docs/wall-charge.md` | Full | Floating-ring evidence, 0.8 pF estimate |
| `docs/picket-park.md` | Full | Context only |
| `docs/prior-work.md` | Full | Context only. No paper claims are used here |
| `AGENTS.md` | Full | Rules, scope (§6.3 item 9) |
| `warpx/cusp/inputs_3d_cusp_fed` | Full | Base deck |
| `warpx/campaigns/cusp/{hw1_wall_fix,hot1_six_coil_sizes,hr1_no_rings,plug1_fine_six_coil}.txt` | Relevant lines | Case lines |
| `warpx/campaign.py` | Build section and line handling only | openPMD flag, case format |
| `warpx/patches/coil-field-on-grid.patch` | Full (added lines) | Coil field in ES modes, probe/energy behaviour |
| WarpX `Docs/source/usage/parameters.rst` | Relevant sections only: `eb_potential`, `do_electrostatic`, self-field precision, external particle/grid fields incl. `read_from_file` multi-field, EB scraping, `ChargeOnEB`, `FieldProbe`, diagnostics types | Parameter names and quoted behaviour |
| WarpX `Docs/source/theory/models_algorithms/electrostatic_pic.rst` | Full | ES and magnetostatic equations |
| WarpX source: `PoissonBoundaryHandler.{H,cpp}`, `WarpXInitData.cpp` (init solve, external fields), `WarpXEvolve.cpp` (ES step), `WarpX.cpp` (solver selection), `MagnetostaticSolver.cpp`, `SemiImplicitDarwin.cpp`, `DarwinMLMGPC.H`, `ExternalParticleFields.cpp`, `ExternalField.cpp` (reader), `WarpXComm.cpp` (`UpdateAuxiliaryData`), `GetExternalFields.cpp`, `FieldProbe.cpp`, `ChargeOnEB.cpp`, `ParticleBoundaryBuffer.cpp`, `BoundaryScrapingDiagnostics.cpp`, `WarpXOpenPMD.cpp`, `ablastr/fields/PoissonSolver.H` | Relevant functions only, not whole files | Each claim above |
| WarpX `Examples/Tests/magnetostatic_eb/inputs_test_3d_magnetostatic_eb` | Full | Evidence that 3D EB + magnetostatic is tested upstream |
| Papers | None read for this report | — |

Everything in §1, §3 and §5 marked "ran" comes from the CPU tests in §7. Statements marked "inferred", plus risks 3 and 6 and the 512³ accuracy expectations, are reasoning, not measurement.
