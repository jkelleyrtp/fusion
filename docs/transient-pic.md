# Electron-only transient PIC reference

`src/run_transient_pic.py` advances an evolving electron population with either
the FP64 Torch reference operators or explicitly selected FP64 CUDA operators.
Packets enter at the grounded lower-z boundary and particles remain in the
population until they hit an absorbing wall.

This is a nonrelativistic electrostatic numerical reference with an imposed
magnetic field. It does not yet establish a converged reactor well, model the gun
electrodes or filament sheath, or include ions, collisions or magnetic feedback.
The compact inlet footprint and divergence are post-extraction assumptions.

## Bounded CPU example

```bash
OMP_NUM_THREADS=1 python3 src/run_transient_pic.py \
  --out results/pic-smoke \
  --current-a 1e-10 --coil-current 0 --radius .5 \
  --energy-ev 5000 --temperature-ev 0 \
  --source-sigma 0 --divergence-deg 0 --aim-deg 0 \
  --nodes 9 --inject-per-step 2 --dt 1e-11 --duration 2.5e-11 \
  --save-every 1
```

This accounting control injects six macroparticles across three steps, including
a fractional final step. Their total represented charge is −2.5e−21 C. It is too
short and too weak to study confinement. Omitting these overrides runs a separate
100-step startup smoke configuration with 1,000 A-turn imposed coils.

GPU execution uses `--device cuda:0 --kernels cuda` **only inside a
broker-managed job**, following `AGENTS.md`; this CLI does not submit or allocate
GPU resources. Selecting CUDA fails if its extension cannot compile or run.

## Charge and time semantics

For packet interval `p`, step length `h`, positive input current `I` and `N`
injected macroparticles, each packet normally represents `I*p*h/e` electrons.
The final packet is truncated to the remaining simulated duration. Current zero
keeps zero-weight test particles. `--inject-every` lets a timestep comparison
retain identical packet times, samples, represented charge and particle count.

Each step:

1. Inject at physical time `t`.
2. Half-drift and absorb wall intersections at their clipped crossing times.
3. Deposit instantaneous CIC charge at the surviving midpoint positions.
4. Solve grounded-box Poisson and apply a full Boris velocity kick.
5. Half-drift and absorb again.
6. Save synchronized positions and velocities at `t+h` when requested.

Saved charge and potential are recomputed at the saved end positions. Changing
the output stride does not alter the integration. There is no stationary
under-relaxation or residence weighting in PIC deposition.

Stable IDs, birth times, represented electron counts, residence, core residence
and core entries accompany live particles. Lost particles contribute to
cumulative charge, kinetic energy, residence and exit-face totals. The first
`--track` IDs retain bounded position and wall-event records; these represent the
earliest injections, not a uniform sample over injection time.

## Files

- `configuration.json`: model identifier, source assumptions, source origin and
  aim, nominal aim/local-B angle, magnetic table, boundary and precision.
- `history.json`: atomically published scalar diagnostics and snapshot paths.
- `snapshots/step-*.npz`: compressed FP64 particle and field arrays, physical
  timestamp, step length, stable IDs, weights and tracked wall events.
- `DONE`: written only on successful completion.

The NPZ archives contain numeric arrays and can be loaded with
`numpy.load(path, allow_pickle=False)`. Partial history remains available when a
run fails. `--max-steps`, `--max-live-particles` and `--max-snapshots` reject
overflow explicitly. Output is a reference archive; a browser adapter and lazy
trajectory packaging remain to be implemented. Do not import this data as
stationary Poisson iterations.

## Accounting and numerical checks

With both injected and lost charge negative:

```text
charge_balance_C = injected_charge_C - lost_charge_C - alive_charge_C
deposition_error_C = sum(charge_grid_C) - alive_charge_C
```

Boundary CIC shape charge is included in deposition accounting and reported
separately. It is not equivalent to absorbed particle charge.

Kinetic energy uses represented electron counts. Field energy uses the mesh's
discrete grounded-box energy. The open-system diagnostic is:

```text
K + U + cumulative_lost_kinetic - cumulative_injected_kinetic
```

The CLI starts empty, so its initial energy is zero. Injected particles start
on a zero-potential wall. This diagnostic is not an experimental power budget
or an exact discrete invariant. `PIC.inject` also permits interior particles
for closed numerical controls; the open-system diagnostic does not account for
the interaction energy of arbitrary interior injection.

The driver checks the tabulated maximum magnetic field for 80 steps per
gyration. Each advance also checks the local magnetic field, a 0.2-cell drift
bound and `omega_p*h <= 0.1` using peak deposited nodal density. Violations
stop the run; there is no silent timestep adaptation.

```bash
PYTHONPATH=src OMP_NUM_THREADS=1 python3 -m unittest discover \
  -s tests -p 'test_transient_*.py' -v
PYTHONPATH=src OMP_NUM_THREADS=1 python3 -m unittest discover \
  -s tests -p test_electrostatic.py -v
ruff check src/transient_pic.py src/run_transient_pic.py \
  tests/test_transient_pic.py tests/test_transient_cli.py
mypy --follow-imports=silent src/transient_pic.py src/run_transient_pic.py
```

The checks cover wall timing, charge balance, zero-population behavior, magnetic
speed preservation, time reversal, second-order closed-system energy error
under timestep refinement, fractional injection and saved-state consistency.
The existing manufactured Poisson test checks second-order mesh refinement.
That test does **not** establish physical source/grid convergence: particle
count, mesh spacing, pulse duration, box extent and observation window need
separate studies before interpreting startup, dwell or well stability.

## Research gates after startup and refinement

The [startup](pic-startup-evidence.md) and [refinement](pic-refinement-evidence.md)
studies support continuing with transient PIC. They do not establish an ion
well: the deepest electron potential is near the inlet, and mesh refinement
changes the dominant loss channel. The next work should follow these gates.

### 1. Establish charged-run repeatability and CUDA agreement

Keep the existing comparison tolerances and the FP64 reference unchanged.
Run the charged reference twice with identical physical packets, then compare
fixed-input deposition, Poisson, gather and Boris operations. This determines
whether a long-run discrepancy also occurs without changing the backend.
Record failed comparisons and toolchain versions.

If the reference cannot repeat within the existing limits, first establish a
reproducible diagnostic reduction path and a written validation protocol.
Changing the protocol requires a separate review; it cannot turn an earlier
failed run into a pass. CUDA stays excluded from physical comparisons until
its declared acceptance checks pass.

After correctness, measure deposit, gather, drift, Boris, Poisson and complete
steps at increasing live populations. Include allocation, launch and host
synchronization costs. Optimize the measured bottleneck; a fast Boris kernel
alone does not establish a faster PIC step. Keep Rust deferred.

### 2. Separate the physical gun from numerical boundaries

The current source position and box size both scale with coil radius. Decouple
explicit gun origin/aim, coil geometry, box bounds and per-axis mesh counts
before a boundary study. Merely changing radius moves the apparatus and is not
an outer-boundary convergence test.

First compare 33³, 65³ and 129³ at fixed physical geometry and packet cadence,
subject to the existing stability and runtime limits. Then vary box extent
while preserving cell widths and the physical gun/coil locations. Resolve the
inlet model before moving the grounded wall away from the source: injecting
inside a nonzero potential changes the energy supplied by the source, so the
current open energy diagnostic would need a reviewed extension.

Use an electrode/aperture boundary model with prescribed voltages to represent
extraction. Validate its vacuum solution before adding beam space charge.
Monitor charge assigned to boundary nodes separately from particle absorption.
Mesh-alignment checks must identify any accompanying change to physical
boundaries rather than attributing every difference to grid alignment.

Acceptance requires trends across successive refinements for central potential,
the spatial potential minimum, core-entry probability, inlet losses and
represented core charge. Resolve the 33³/65³ loss discrepancy before calling
the electron result spatially converged. Uniform millimetre-scale cells cannot
resolve a 50 µm filament; model the post-extraction distribution explicitly
until a locally resolved injector is available.

### 3. Measure useful dwell and replenishment

After the inlet study, repeat independent source seeds and double particle
sampling at fixed current. Extend the physical window in bounded stages while
holding injection cadence fixed. Save injection cohorts, terminal events,
survival fractions, time-integrated core charge and repeated-entry counts.
An electron still alive at the end contributes censored residence, not a
measured full lifetime; the mean age of a growing population is not evidence
of a stationary dwell distribution.

The target is a sustained central negative potential accessible to incoming
positive ions, with a measured replenishment cost. Permanent electron
confinement is not required. Report central depth, inlet barrier, spatial
extent, temporal fluctuations and electron replacement power together.
The present `K + U` residual is insufficient for an electrode power budget.

### 4. Add geometry and species in validated increments

Implement a three-dimensional six-coil field with explicit coil poses and
current directions for Polywell studies. Check single-coil limits, symmetries,
field nulls and interpolation convergence before injecting an external beam.
The present axisymmetric field table cannot represent that geometry.

Start hydrogen with non-depositing test ions in the evolving electron field.
Check acceleration and energy in prescribed potentials, then measure whether
ions reach the core or encounter an inlet barrier. Only then add self-consistent
ion charge, per-species accounting and appropriate timestep/subcycling checks.
Introduce collisions, ionization and neutral depletion when estimated rates
and densities require them, using verified cross sections.

Helion-like field-reversed-configuration formation and compression require
electromagnetic induction and magnetic-field evolution. Adding ions to this
fixed-B electrostatic model does not provide that capability. Define that
separate physical specification and electromagnetic validation problem before
choosing its field solver and particle/fluid closure.

### 5. Scale the same PIC model and finish the control-room path

After single-GPU correctness and profiling, partition globally identified
particles across 2, then up to 8 B200 GPUs on one broker-managed node. Each
partition deposits its own charge grid; reduce those grids, solve Poisson once,
and distribute the field. Normalize weights by the global source packet count,
preserve global injection IDs/seeds, and compare charge, losses and fields
against the one-GPU case before reporting scaling. Keep replicated meshes
until memory or measured communication costs justify a distributed solver.
GB200 portability remains a goal; no GB300 capacity is needed.

Keep one transient production launcher and retain stationary reports only as
historical data. The app currently tracks transient jobs, but its generic
launch command still targets the older stationary profile. Switching that
launch surface and packaging transient snapshots for lazy physical-time replay
are explicit remaining deliverables. Preserve immutable source/configuration
records, bounded compressed output and terminal failure reasons throughout.
