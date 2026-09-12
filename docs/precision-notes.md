# Precision recommendation

Keep FP64 as the reference implementation. Nondimensionalization is useful engineering, but small SI values are not themselves evidence of floating-point trouble. Normal numbers have relative precision; rescaling usually preserves the ratio between a state value and its increment.

## What the current run requires

For the neutral 100 eV member of `20260912-123558`:

| Quantity | Value |
|---|---:|
| End time | 100 µs |
| Reference timestep | 0.3966 ps |
| Maximum adaptive timestep | 32.995 ps |
| FP32 spacing at the end time | 7.276 ps |
| FP64 spacing at the end time | 1.355 × 10⁻⁸ ps |

The reference timestep is a field-based limit, not a claim that every particle takes that step throughout the run. Actual adaptive steps vary with position and are clipped at output boundaries.

Direct NumPy checks confirm that adding this reference increment to an FP32 clock at 100 µs leaves the clock unchanged. The same failure occurs for a 1 T gyroperiod divided into 40 steps (0.8931 ps). FP64 spacing is approximately 3.42 × 10⁻⁸ of the reference increment. This is not a reason to replace the existing FP64 clock.

Using the proposed scales, L₀ = 0.1 m and V₀ = 5.931 × 10⁶ m/s gives T₀ = 16.861 ns. The normalized final time is about 5,931 and the normalized reference step is 2.352 × 10⁻⁵. An FP32 clock still fails to advance under that addition. Changing units does not remove the large elapsed-time-to-step ratio.

These are representational checks, not measurements of total accumulated integration error.

## Normalized equations

Choose a positive reference electron energy, L₀ and V₀, with T₀ = L₀/V₀. Define

\[
x'=x/L_0,\quad v'=v/V_0,\quad t'=t/T_0,\quad
B'=B/B_0,\quad E'=E/E_0,\quad
E_0=\frac{m_e V_0^2}{eL_0}.
\]

For electrons,

\[
\frac{dx'}{dt'}=v',\qquad
\frac{dv'}{dt'}=-E'-\Omega_0\,v'\times B',
\qquad \Omega_0=\frac{eB_0T_0}{m_e}.
\]

The dimensionless parameter Ω₀ retains the separation between the transit and gyro times. Nondimensionalization does not remove physical stiffness.

## Which changes are worth testing?

- **FP64 time and accumulated diagnostics:** retain these in the first mixed-precision experiment.
- **FP32 particle and field arithmetic:** benchmark only as a separate, explicit mode against the FP64 reference. Long orbit histories, magnetic nulls, and loss boundaries can amplify small errors.
- **Integer time:** useful for exact synchronization if adaptive steps and output times share a defined tick lattice. The current power-of-two step quantization is helpful, but final shortened steps and sampling boundaries still need a consistent representation.
- **Automatic precision switching per particle:** defer it. It introduces conversion decisions, warp divergence, and another numerical policy to validate.

B200's published scalar FP32 peak is roughly twice FP64. Ordinary normalized magnitudes do not execute faster just because they are close to one; tensor-core performance is not directly applicable to this scalar orbit kernel.

An FP32 state followed by an FP64 diagnostic calculation does not restore precision already lost in the trajectory. Energy conservation alone is insufficient: compare timestep and grid convergence, survival curves, loss channels, and canonical angular momentum in the axisymmetric static problem. Use absolute energy errors as well as relative errors, since total energy can be close to zero. Well-depth and loss-current checks become relevant once electrostatics is self-consistent.

The current stored trajectory samples are already FP32; the active particle state and clock are FP64. Reducing output precision and reducing integrator precision are different changes.

No arithmetic or time representation was changed as part of this recommendation.
