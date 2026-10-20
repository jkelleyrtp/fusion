# Space charge rev0

The new reference solver is `src/steady_space_charge.py`. It performs a
**stationary trajectory–Poisson iteration** with continuous injection represented
by a distribution of particle ages. Its iterations are not elapsed reactor time.
It can find stationary candidates; it cannot establish their transient stability.

## Why this model

A negative electron cloud makes a potential depression for positive ions, but
repels additional electrons. Inventory cannot grow as `I × vacuum dwell` without
changing the trajectories. Injection may be reflected before reaching the core;
the deepest potential may be in the beam near the source. Both central potential
and global minimum are therefore recorded, along with core residence.

The box is three-dimensional so an off-axis localized gun is not silently replaced
by an azimuthally smeared source. The magnetic field remains the analytical
opposed-loop vacuum field. This is electrostatics, without magnetic plasma
response, collisions, ions, emission optics, or transient instabilities.

## Charge and field coupling

For `N` sampled launch conditions, each trajectory represents a number flux
`I / (e N)` in particles/s, not a fixed instantaneous macroparticle charge.
A residence interval `δt` contributes `−I δt / N` coulombs to the mesh.
Consequently the deposited inventory satisfies

```
sum(Q_nodes) = −I × mean(min(residence, observation_window)).
```

The same relation holds for geometric core inventory using time inside the core.
Non-escaped trajectories are censored. A converged iteration with substantial
censoring can still be a cutoff artifact: lengthen the window separately.

All six box faces are grounded absorbing conductors. Cloud-in-cell weights
deposit onto eight nodes. The seven-point finite-difference Poisson operator is
inverted using separable DST-I transforms implemented through GPU-compatible
FFTs. The rectangular grid can have different spacings on each axis.

The electric force is the **negative derivative of the same interpolated
potential** used by deposition. Its particle force agrees with the derivative of
discrete electrostatic energy. This spatial identity does not make the time
integrator exactly energy conserving, eliminate particle noise, or establish
physical thermalization.

Shape weight assigned to boundary nodes is reported separately. It is not a
particle loss: those nodes are fixed at zero potential and do not enter the
interior Poisson RHS. A large fraction indicates inadequate source/wall
resolution. Absorption occurs when an orbit segment reaches a physical face.
Segment clipping accounts for its fractional residence time before absorption.

Trajectories use FP64 drift–Boris–drift steps in a held potential. Charge is
deposited at drift-segment midpoints, weighted by actual segment duration.
This quadrature and wall-crossing treatment require timestep refinement.
The source is held identical between iterations to reduce Monte Carlo differences.

The update relaxes nodal charge:

```
Q_relaxed ← (1 − α) Q_relaxed + α Q_orbits
φ_next ← Poisson(Q_relaxed)
```

Output distinguishes the potential used for the orbits, the potential generated
by their deposition, and the relaxed next potential. Their disagreement is the
fixed-point residual; a small Poisson residual alone says nothing about that
nonlinear convergence.

## Source approximation

A Gaussian finite spot on the bottom entrance plane emits along a selected aim. Transverse thermal velocities
are Gaussian; the outgoing normal velocity has the flux-weighted half-Maxwellian
distribution. A specified acceleration energy is added to normal kinetic energy.
The expected total energy is `E_acceleration + 2 T_source` when both are in eV.
This captures a thermal floor in divergence and energy spread; it does not model
filament geometry, work function, emission-current limits, or focusing electrodes.

The optional `--divergence-deg` parameter describes a post-extraction inlet cone,
not the thermal source temperature. It rotates each sampled thermal velocity by a
uniform solid-angle offset up to the requested half-angle; it does not replace the
thermal draws. The default is zero and preserves the legacy source and random
stream exactly. The `filament` pilot profile compares four complete cases at 5 keV,
0.2 eV source temperature, 30 kA-turn, 33³ nodes, 1024 particles, eight iterations,
100 ns duration, and relaxation 0.5: broad 3 cm / 0° vacuum and 1 A cases versus
assumed 50 µm / 10° compact-source vacuum and 1 A cases. The source size and cone
are modeling assumptions; this coarse mesh does not resolve the emitter or
extraction field, and the comparison makes no convergence claim.

The source lies on the grounded bottom boundary, outside the central trapping
region. Its injection energy is therefore referenced to that specified boundary
potential. The boundary supplies a post-optics beam flux; its current is not
derived from a cathode/Child–Langmuir model. Beam particles returning to it are
absorbed. Emitting apertures, focusing optics and electrode biases need a more
detailed boundary model.

## Diagnostics and validation

`config.json`, `history.json`, and compressed `state.npz` record source parameters,
physical flux weight, current, timestep, seed, potential, deposited charge, field
energy, Poisson residual, fixed-point change, residence/core residence, repeated
core entries, escape/censor fractions, and endpoint Hamiltonian error.

Injected, escaped, and censored fluxes are currents, not charges integrated over
a transient run. Injected/escaped kinetic powers are partial flux diagnostics;
they are not a complete recoverable-energy or fusion power balance.

The reference tests check:

- charge conservation, including shapes touching boundaries;
- exact inversion of a discrete manufactured Poisson solution;
- second-order convergence against a continuum Poisson solution;
- the discrete field-energy identity and particle force/energy derivative;
- ballistic absorption, core residence, and censored inventory;
- motion in a uniform electric field;
- thermal-source energy moments and deterministic seeds.

Before interpreting a well: refine timestep, mesh, particle count, orbit duration,
source/wall separation, and relaxation. Check that central potential and core
inventory stabilize, not just the global potential minimum. Compare independent
seeds after common-seed iteration converges. Narrow beams on coarse meshes are
especially susceptible to artificial self-force and smoothing.
Source width in cells and a density/source-temperature Debye-length proxy are
reported. That proxy is not a measured temperature or a validity guarantee for a
non-Maxwellian cloud. A grid larger than the relevant shielding/sheath scale
cannot resolve it, even if the algebraic Poisson residual is tiny.

## Run

```bash
OMP_NUM_THREADS=1 python3 src/steady_space_charge.py \
  --out results/space-charge-reference --device cpu \
  --particles 256 --nodes 17 --iterations 3
python3 -m unittest discover -s tests -p test_electrostatic.py -v
```

`--device cuda:0` runs the same FP64 code on a GPU. GPU allocations still require
the repository's priority-1, one-node broker procedure. This implementation
prioritizes a checkable particle/field interface; it uses many Torch operations
per orbit step and is not a replacement for the fused production CUDA pusher.

## Next numerical stages

1. Fused GPU deposition/gather and particle advance, validated against this
   reference; spatial and temporal refinement of the stationary candidates.
2. Synchronized transient injection/absorption with physical macroparticle
   charges `−I Δt / N_injected`, solving fields at consistent global times.
   Include injected/lost/boundary/remaining charge and full energy accounting.
3. Physical ion loading, emission/electrode boundary conditions, pulses,
   collisions, and eventually electromagnetic plasma response.

Steady orbit steps cannot simply become independently timed self-consistent
particle steps: the charge and field must describe a common physical time in
transient PIC. A future implicit/geometric method should be compared against
resolved explicit reference cases and numerical-heating baselines.
