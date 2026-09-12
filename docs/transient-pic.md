# Electron-only transient PIC reference

`src/run_transient_pic.py` advances an evolving electron population on the FP64
Torch backend. Every step injects a new packet at the grounded lower-z boundary.
Particles remain in the population until they hit an absorbing wall.

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

GPU execution uses `--device cuda:0` **only inside a broker-managed job**, following
`AGENTS.md`; this CLI does not submit or allocate GPU resources.

## Charge and time semantics

For step length `h`, positive input current `I` and `N` injected macroparticles,
each represents `I*h/(e*N)` electrons and has charge `-I*h/N`. Current zero keeps
zero-weight test particles. Injection is a pulse at the start of each step, so
the pulse approximation must be refined with the timestep.

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
