# Relativistic electron pusher: design

Status: proposed. AGENTS.md requires a reviewed design before integrator arithmetic changes.

## Why

The electron pusher advances Newtonian velocity. The error in electron speed for a given kinetic
energy is 3% at 20 keV, 7% at 50 keV and 14% at 100 keV, and the gyroradius and gyration period
are wrong by the same order. The six-coil regime analysis shows the well is capped near the gun
energy, so the next sweep raises gun energy to 50–100 keV. Those runs need a relativistic push.

## Scope

- A `--relativistic` option on the electron PIC (`run_transient_pic.py`, `run_ion_pic.py`).
  With it off, every operation and every existing kernel call is unchanged, so existing FP64 and
  CUDA results reproduce exactly.
- Ions stay Newtonian (100 keV D+ has v/c ≈ 0.01).
- The field model stays electrostatic with a prescribed vacuum B.

## State

With `--relativistic`, the electron `velocity` array holds proper velocity u = γv in m/s, with
γ = sqrt(1 + |u|²/c²). Run configuration records `"relativistic": true`, and snapshots store the
same array under `electron_proper_velocity_m_s` instead of `electron_velocity_m_s`, so analysis
code cannot silently read u as v.

## Arithmetic

Relativistic Boris (Birdsall and Langdon §15-4), with a = qE/m and b = qB/m:

```
u⁻ = u + a h/2
γ⁻ = sqrt(1 + |u⁻|²/c²)
t  = b h / (2 γ⁻)
s  = 2t / (1 + |t|²)
u' = u⁻ + u⁻ × t
u⁺ = u⁻ + u' × s
u  ← u⁺ + a h/2
```

At γ⁻ = 1 this is the existing Boris step term by term. In the CUDA extension it is a new
`boris_relativistic` kernel; `boris_kernel` is not edited. The reference implementation is a new
`ReferenceKernels.boris_relativistic` beside the existing method.

Drift uses v = u/γ computed in PyTorch before the existing drift kernel, so the clip, core-entry
and dwell accounting are unchanged.

Kinetic energy uses T = m|u|²/(γ + 1), which equals (γ − 1)mc² without cancellation at low
energy. It replaces ½m|v|² in `PIC.kinetic_energy`, lost-particle totals, injected packet energy,
and the electron-impact energy for ionization and charge exchange in `ion_pic.py`.

## Injection

The gun sampler draws velocities exactly as today, giving a kinetic energy
T = ½m|v|² and direction for each electron. With `--relativistic` each sample is mapped to
|u| = c sqrt((1 + T/mc²)² − 1) along the same direction. This preserves the energy, thermal
spread and divergence distributions and leaves the random stream untouched.

## Guards

- 80 steps per gyration keeps the Newtonian test q|B|h/m; the relativistic gyrofrequency is
  lower by γ, so the guard is conservative.
- The 0.2-cell drift bound uses |v| = |u|/γ.
- ω_p h ≤ 0.1 keeps the Newtonian plasma frequency, also conservative.

## Validation

1. Uniform B, 100 keV and 1 MeV: gyroradius p/(eB) and period 2πγm/(eB) within 1e-4 over
   100 gyrations; energy conserved to roundoff.
2. Crossed E and B: drift velocity E/B for E/B ≪ c.
3. Electron accelerated through a 100 kV drop: final T within 1e-6 of 100 keV plus initial T.
4. `--relativistic` off: bitwise identical history on the existing reference test cases.
5. CUDA against reference: short-run roundoff gate, then the four-seed physics acceptance.
6. Six-gun 100 A, 20 keV case with and without the option: expect differences of a few percent.

## First sweep after validation

Six external guns, 1e-3 Pa H2, 65 nodes, 320 µs:

| Gun energy | Coil current (B ∝ electron momentum from 10 keV at 30 kA-turn) | Total current |
|---|---|---|
| 20 keV | 42.6 kA-turn, and 30 kA-turn control | 1000 A |
| 50 keV | 68.4 kA-turn, and 30 kA-turn control | 1000 A and 3950 A (perveance-scaled) |
| 100 keV | 99 kA-turn, and 30 kA-turn control | 1000 A and 11200 A (perveance-scaled) |
