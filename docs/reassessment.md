# GPU performance and a simulation path for a Polywell

## Recommendation

Keep the full-orbit particle code as an orbit benchmark. Add self-consistent electrostatics with physical injectors and boundaries before choosing a more elaborate representation of velocity space. For steady operation, a trajectory–Poisson iteration is a useful intermediate step. For loading, pulses, and instabilities, use time-dependent kinetic electrons and ions.

Hermite and low-rank methods deserve a separate comparison on small, relevant benchmarks. Combining them with an unvalidated dissipation closure at the outset would make it difficult to tell whether a favorable result came from the device or from the approximation.

The previous performance and physics advice contained several errors. This reassessment corrects them using the source, completed simulation outputs, and the references below. No new simulation method or kernel optimization was implemented for this reassessment.

## 1. What the performance numbers actually mean

### The original 50–100 billion particle-steps/s claim is invalid

The original simulator at commit `3d3fdb5` computed throughput as:

```text
initial particle count × elapsed nominal steps / simulation-loop wall time
```

Its CUDA kernel stopped advancing particles when they escaped. The numerator continued crediting those skipped steps. This overstates executed work in runs with losses; the old numbers cannot establish a fixed-step RK4 baseline or an RK4-to-Boris speedup.

Evidence: `original_cusp_sim.py`, kernel early return at line 170, escape handling within its step loop, and throughput calculation at line 474.

The current implementation sums each particle's actual step counter. Its timer includes the synchronized simulation loop, diagnostics, reductions, and host overhead. It is a useful application-throughput measure, but it is not an isolated CUDA-kernel time.

### The corrected well sweep is much more informative

All 16 member outputs from run `20260912-123558` were retrieved. Each member used one B200, 200,000 particles, adaptive Boris, and a 100 µs duration. Measured simulation-loop throughput ranges from **4.56 to 32.04 billion actual particle-steps/s per GPU**. These cases have different energies, residence times, and electrostatic forces, so their spread is not a controlled optimization comparison.

For example:

| Case | Actual particle steps | Simulation-loop time | Rate |
|---|---:|---:|---:|
| 100 eV, no charge | 8.156 × 10¹¹ | 97.83 s | 8.34 billion/s |
| 100 eV, +3 nC | 1.832 × 10¹² | 76.06 s | 24.09 billion/s |
| 1 keV, +10 nC | 3.686 × 10¹² | 115.07 s | 32.04 billion/s |

The first eight members spent approximately 80–84 additional seconds in setup before the timed loop. The second round spent approximately 5–6 additional seconds. CUDA extension construction is a major setup component, and the per-device build directories are reused within the job. The timers do not isolate compilation from the rest of setup. My earlier assertion that every member spends 80 seconds compiling, or that compilation always dominates, was wrong.

### FP64 and occupancy were also mischaracterized

The HGX B200 specification lists approximately **37 TFLOP/s FP64 and 75 TFLOP/s FP32** [1]. My claim that B200 FP64 runs at roughly 1/30 of FP32 was wrong for this hardware. Tensor-core throughput is a different comparison and does not apply directly to this scalar orbit kernel.

There is also no universal rule that a B200 needs 300,000 particles to become occupied. Occupancy depends on registers, threads per block, resource limits, and the instruction stream. A 100,000–200,000-particle launch can supply substantial parallelism. Increasing the population is a benchmark variable, not an established fix.

No Nsight profile has been collected. A 100× optimization claim or a “few hundred billion steps/s” ceiling is unsupported.

### What I would optimize, in order

1. **Establish comparable measurements.** Warm the extension, separately time kernels and diagnostics, and compare identical initial states and simulated durations at matched numerical error. Include a confined population and an escaping population.
2. **Inspect register pressure and divergence.** The fused kernel keeps particle state local across many steps, which is a sensible design. Adaptive steps and unequal lifetimes can leave divergent warps. Test live-particle compaction and timestep buckets only where their cost is repaid.
3. **Measure field lookup and diagnostic costs.** Adaptive Boris evaluates the magnetic field for step selection and at the drift midpoint. Interpolation, double-precision divisions and square roots, histogram atomics, and host synchronization are candidates for profiling.
4. **Tune launch and precision choices.** Compare block sizes and carefully chosen mixed precision. Retain an FP64 reference. Long residence times and loss boundaries can make small orbit errors important even when total energy looks good.
5. **Amortize setup.** Reuse compiled artifacts and long-lived per-GPU workers across sweep members.

The primary metric should be GPU-seconds needed to estimate a confinement or loss observable to a stated error, not raw particle-steps/s. Adding particles can improve statistics while doing nothing for systematic orbit error.

## 2. The current “best confinement” result needs a different interpretation

The completed sweep is numerically much healthier than the earlier charged runs. Its charged cases have reported endpoint energy errors between approximately 9.3 × 10⁻⁷ and 3.2 × 10⁻⁵. These diagnostics cover **60 tracked particles**, not all 200,000, and compare initial and final energy. They are not maxima over every particle and every time.

Selected survival fractions at 100 µs:

| Initial energy | Central charge | Survival |
|---|---:|---:|
| 30 eV | 0 | 65.83% |
| 100 eV | 0 | 55.56% |
| 300 eV | 0 | 40.75% |
| 1 keV | 0 | 22.03% |
| 100 eV | −1 nC | 39.74% |
| 100 eV | +0.3 nC | 62.24% |
| 100 eV | +1 nC | 100% |
| 100 eV | +3 nC | 100% |
| 1 keV | +10 nC | 100% |

These particles start inside a 3 cm ball. The rings have 10 cm radius and 23 kA-turn current. This is not a 1 T beam-loading demonstration.

**The strongly positive charge cases are electrostatically bound by construction.** For +3 nC in a 5 cm sphere, the potential is approximately +712 to +809 V throughout the initial ball. A 100 eV electron therefore starts with total energy between approximately −709 and −612 eV, referenced to infinity. The potential energy at the nearest absorbing boundary is no lower than approximately −275 eV. Energy conservation forbids reaching that boundary, even without a magnetic field.

The observed 100% survival is a useful bounded-orbit test. It cannot demonstrate formation of the negative potential that confines positive ions in a Polywell.

For this +3 nC case, the reported endpoint relative energy error is 5.55 × 10⁻⁷. An independent calculation from its saved trajectories gives a maximum sampled energy change of about 0.00030 eV. Those trajectories cover only 0–59.99 µs: the job requested 6,000 samples at 10 ns spacing despite running for 100 µs. Survival and final-energy summaries cover the full duration.

The source currently describes Boris and adaptive stepping too strongly in places. Boris preserves speed in a magnetic-only step to floating-point accuracy. It does not exactly preserve magnetic moment or general electrostatic total energy. A symmetric fixed-step update also does not make a state-dependent adaptive timestep schedule time-reversible.

Other validation priorities are timestep and field-grid refinement, energy errors over time, and canonical angular momentum in the axisymmetric static problem. Exact elliptic-integral values at grid nodes do not make the interpolated field exact between nodes. A flux-function representation is worth considering to control magnetic-field consistency.

The earlier 400-particle convergence comparison is insufficient to dismiss all differences as counting noise. Step-size errors and ensemble sampling error should be assessed separately, including paired trajectories when the initial sample is identical.

## 3. What the Polywell model must add

### A well must form and survive ion loading

The desired ion well has negative electrostatic potential relative to the relevant boundary. Excess electrons produce it; their own potential energy rises in it. Maintaining that electron population requires injection, confinement or recirculation, and replacement of losses.

A prescribed charge sphere has no relationship between simulated particle count and physical electron density. It cannot determine injection current, screening by ions, or replenishment power.

At minimum, the next model needs:

- electron macroparticle weights tied to a physical injection current;
- a Poisson solve with chamber and electrode potentials;
- continuous injection, extraction, and actual material boundaries;
- kinetic ions for the ion-loading experiment;
- a defined fuel and ionization model if the injected hydrogen is neutral.

Fixed ions are useful as a controlled test. They cannot answer whether a well persists while an evolving ion population enters it.

### The geometry and boundaries may matter more than the pusher

The current cylinder absorbs particles once they cross a chosen radial or axial surface. It does not represent biased coil casings or an external recirculation region. In a real device, crossing the nominal cusp surface need not equal irreversible wall loss.

For the present two-ring geometry, an axisymmetric, two-position/three-velocity-component model is a good controlled next step. A polyhedral, multi-coil Polywell is genuinely three-dimensional. Axisymmetry introduces a conserved canonical angular momentum and excludes azimuthal instabilities. Strong confinement in that symmetry must eventually be challenged with three-dimensional fields and perturbations.

I also retract the assertion that time reversibility proves every injected electron must retrace and escape. Static fields conserve particle energy and can produce bound orbits or long chaotic residence. They provide no dissipative attractor, but the general capture question is more subtle. Simply reversing velocity while keeping the same magnetic field does not reverse a Lorentz-force trajectory. Our failed beam sweeps establish outcomes for the tested configurations and boundaries.

### A fixed vacuum magnetic field omits a central high-beta hypothesis

High-beta cusp confinement relies on plasma currents substantially modifying the magnetic field. The 2015 experiment reported enhanced high-energy electron confinement in that regime [2]. It did not establish net fusion power.

Electrostatic PIC with fixed vacuum B can examine space-charge loading and electrostatic dynamics. It cannot test diamagnetic field exclusion or the proposed high-beta cusp boundary. That requires magnetic response through an appropriate electromagnetic or justified low-frequency model. Simply increasing the coil field does not substitute for it.

## 4. Which kinetic methods fit?

| Approach | Useful role | Main limitation for this problem |
|---|---|---|
| Full-orbit test particles | Geometry, orbit invariants, injection optics, loss channels | No self-consistent plasma |
| Steady trajectory–Poisson iteration | Fast searches for stationary injection and space-charge solutions | No transient stability or pulse history |
| Full-orbit electrostatic PIC | Well formation, ion loading, electrostatic instabilities | Fixed B omits diamagnetism; numerical relaxation requires measurement |
| Electromagnetic or validated low-frequency kinetic model | High-beta response and magnetic pulses | More expensive; scale ordering and circuit coupling matter |
| Hermite continuum kinetics | Low-noise distribution benchmarks and adaptive moment resolution | Beams, loss cones, positivity, boundaries, and mode growth |
| Dynamical low rank | Compressible phase-space solutions | Rank is problem-dependent; small global error can miss a critical loss tail |
| Gyrokinetic/guiding-center model | Magnetized regions with justified scale separation | Breaks down near the magnetic null and demagnetized cusp layer |
| Kinetic ions with fluid electrons | Problems where an electron closure is sufficient | Electron trapping and non-Maxwellian electron kinetics are central here |

**There is a particularly relevant intermediate method missing from the prior answer:** launch particles through an assumed electrostatic field, deposit their residence-time-weighted charge, solve Poisson, and iterate toward a stationary solution. This keeps much of the present independent-orbit GPU structure. It has already been applied to Polywell injection by Kollasch, Sovinec, and Santarius [3]. It can supply stationary candidates for subsequent time-dependent tests; convergence of the iteration does not establish physical stability.

The quoted survey is too sweeping about both novelty and hardware. SPS-DG and adaptive Hermite methods are real [4,5]. Adaptive velocity scaling directly addresses changing temperature; a 100-fold temperature increase is not automatically fatal. Sharp beams, loss cones, and phase mixing are the harder question.

Low rank does not require a near-Maxwellian distribution. It requires a sufficiently separable representation. Ensign demonstrates useful six-dimensional Vlasov–Poisson calculations [6], but that does not bound the rank needed for a cusp device.

Likewise, Hermite dynamics are not automatically dense matrix multiplication. Couplings, spatial transport, reductions, and field solves can dominate. Tensor cores help suitable kernels, not every operation written in a basis. PIC can exploit particle sorting and local deposition effectively on GPUs.

Fusion-oriented continuum kinetics already exists, including Gkeyll work on laboratory devices and tokamak edge turbulence [7]. Vlasiator's kinetic-ion/fluid-electron choice is not a direct fit for electron-well formation. Claims that nobody has applied advanced kinetics to fusion, or that all the hard mathematics is finished, are unsupported.

### PIC will not be “a microsecond Poisson solve”

A grid size and timestep cannot be chosen before density, temperature, geometry, and the retained physical modes are specified. As an illustration, at 10 keV the Debye length ranges from about 0.74 mm at 10¹⁸ m⁻³ to 0.074 mm at 10²⁰ m⁻³.

At 1 T, the electron gyroperiod is approximately 35.7 ps. A full-orbit run that uses 40 steps per local gyroperiod needs approximately 1.12 × 10⁸ steps for a particle that spends 100 µs in that field. The null permits larger steps, but this illustrates the scale problem.

Implicit methods can remove stability restrictions without preserving all unresolved physics. WarpX's effective-potential documentation explicitly discusses the altered numerical plasma frequency [8]. Independent per-particle stepping through a static field also does not transfer unchanged to PIC: charge deposition and field evolution must remain consistent in time.

Energy-conserving PIC is valuable, but conserving total energy does not prevent spurious redistribution of that energy among particles. Numerical thermalization is a separate, documented issue [9]. A Rider-related calculation needs a physical Coulomb collision model and a numerical-relaxation rate shown to be smaller than the effect being measured.

## 5. Pulses, non-Maxwellians, and energy recovery

Pulsed operation changes the question to the energy balance of a complete cycle. It does not, by itself, evade collisional relaxation.

A short pulse may end before substantial relaxation. It must still produce enough fusion yield to repay loading, acceleration, compression, extraction, and resetting the device. At fixed distribution shape and characteristic energy, both collisional rates and fusion reaction rates grow roughly with density, apart from factors such as the Coulomb logarithm. Increasing density alone does not generally improve their competition.

Use distribution-dependent reactivity,

\[
\mathcal R = \int f_1(\mathbf v_1) f_2(\mathbf v_2)
\sigma(v_{\rm rel})v_{\rm rel}\,d^3v_1\,d^3v_2,
\]

with the appropriate identical-species factor. A nominal “temperature” does not determine the reactivity of counterstreaming or anisotropic populations.

Rider's calculation concerns the power needed to sustain nonequilibrium distributions against collisions [10]. Evaluating a pulse requires testing its assumptions against the actual cycle, not treating either “pulsed” or “non-Maxwellian” as a conclusion.

For an operating cycle, record externally supplied work, recoverable output through a specified circuit or collector, particle loss energy, radiation, fusion yield, and changes in stored particle and field energy. Recoverability requires a physical extraction protocol and its efficiency.

Collisionless Vlasov evolution conserves fine-grained entropy in a closed system. That does not mean all phase-mixed energy can be recovered by reversing a coil-current waveform. Real devices have finite controls, escaping particles, collisions, and radiation. Measure recoverable work through a proposed device operation.

The entropy-cascade theory is relevant, but the cited solvable stochastic-heating study uses a 1D–1V model with a prescribed random electric field [11]. It does not supply a calibrated closure for a pulsed cusp device. A velocity-space closure should preserve the appropriate conserved quantities and model physical entropy production; it should not simply delete kinetic energy above a cutoff.

If the pulse changes the magnetic field, Faraday induction must be included. Updating the static B table while omitting the induced electric field would give the wrong particle work and compression budget. Injector-current pulses with a fixed external B are a simpler first experiment.

## 6. Practical sequence

1. Correct benchmark interpretation and validate the existing orbit model against timestep, grid, invariant, and boundary checks.
2. Introduce physical injectors, biased surfaces, macroparticle weights, and a steady trajectory–Poisson calculation. Ask whether a useful negative well can be sustained at an acceptable electron-loss power.
3. Test promising states with time-dependent full-orbit electrons and ions. Include physical collisions for distribution-relaxation questions. Begin with the two-ring axisymmetric benchmark, then test the intended three-dimensional topology.
4. Add magnetic response when investigating high-beta confinement, and circuit/inductive physics when investigating magnetic pulses.
5. Compare a small Hermite or low-rank benchmark against converged particle and continuum references. Judge well depth, loss current, distribution tails, and recovered work. Add a closure only when its error can be separated from the physics being tested.

The most useful next research result is a relationship between **well depth, electron replenishment power, ion loading, and confinement duration**. That would tell us which numerical improvements and reduced models are worth building.

## Evidence and references

Local source inspected: `fusion/cusp_sim.py` at commit `1099181`; source SHA-256 `b6f90c6dcdd0c8c817b3bb904e354c04ef112051d80c8d8bad340de2fb9645b1`. The staged source had the same hash when collected. Historical source was exported from `3d3fdb5`. Run evidence is preserved in `reassessment-evidence/run-20260912-123558-snapshot2/20260912-123558/`. All 16 summary step totals and final survival counts were checked against their NPZ arrays.

1. [HGX B200 specifications, Lenovo product guide](https://lenovopress.lenovo.com/lp2226-thinksystem-nvidia-hgx-b200-180gb-1000w-gpu).
2. [Park et al., High-Energy Electron Confinement in a Magnetic Cusp Configuration, PRX (2015)](https://doi.org/10.1103/PhysRevX.5.021024).
3. [Kollasch, Sovinec, Santarius, steady-state Vlasov–Poisson/PIC for Polywell (2014 workshop)](https://iec.neep.wisc.edu/usjapan/16th_US-Japan/Posters/ICC_2014_Kollasch.pdf). See also [measured well dependence on injection current, field, and bias](https://doi.org/10.1063/1.4894475).
4. [SPS-DG: multidimensional Hermite–DG Vlasov–Maxwell](https://doi.org/10.1016/j.cpc.2021.107866).
5. [Physics-based Hermite adaptivity](https://arxiv.org/abs/2208.14373).
6. [Ensign: efficient six-dimensional Vlasov simulations](https://arxiv.org/abs/2110.13481).
7. [Gkeyll continuum electromagnetic gyrokinetics in laboratory and fusion devices](https://doi.org/10.1063/1.5141157).
8. [WarpX electrostatic PIC and effective-potential method](https://warpx.readthedocs.io/en/latest/theory/models_algorithms/electrostatic_pic.html).
9. [Numerical thermalization in 2D PIC](https://arxiv.org/abs/2401.06057); [energy/charge-conserving implicit collisional PIC](https://doi.org/10.1016/j.jcp.2023.112383).
10. [Rider, Fundamental limitations on plasma fusion systems not in thermodynamic equilibrium (1997)](https://www.osti.gov/biblio/527873).
11. [Nastac et al., phase-space entropy cascade in a stochastic-heating model](https://doi.org/10.1103/PhysRevE.109.065210).
