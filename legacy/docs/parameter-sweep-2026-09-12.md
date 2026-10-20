# External-gun current/energy/angle sweep

Broker job `jonathan-cusp-parameter-sweep-d67ba6` succeeded: 132/132 cases,
32,768 electrons per case. Raw outputs are on FSx under
`/public/jonathan/cusp/runs/parameter-sweep-20260912-143728`.
`src/analyze_parameter_sweep.py` reproduces the ensemble table and paired checks
from a downloaded run directory, writing `analysis.csv` and `analysis.json`.

## What changed the result

The largest finite-window mean residence in this sweep was at **50 kA,
5 eV, 30° aim**, in the 50 cm radius geometry. Increasing field strength
at that launch condition shortened residence:

| Coil current | Maximum on-axis B | Mean residence | Surviving at 18.85 µs | Radial losses |
|---:|---:|---:|---:|---:|
| 50 kA | 0.043 T | 3.089 µs | 4.01% | 61.11% |
| 250 kA | 0.215 T | 0.867 µs | 0 | 100% |
| 1 MA | 0.860 T | 0.867 µs | 0 | 100% |
| 2 MA | 1.721 T | 0.867 µs | 0 | 100% |

These use a 1° cone half-angle. Widening the 50 kA cone to 10° gave
3.064 µs and 3.93% surviving. The Monte Carlo source spot has 0.5 mm Gaussian
width; the velocity cone is not calibrated to a real filament.

Doubling both magnetic-grid dimensions and halving the gyro-step fraction,
with paired launch samples, changed the leading case from **3.089 to
3.033 µs** (−1.82%). Survival changed from 4.01% to 3.84%.
The paired residence-change standard error was 0.030 µs. This is encouraging
agreement at one joint refinement, not full grid/timestep/tail convergence.

The 32 stored example trajectories offer a useful qualitative distinction:
all 32 enter the 15 cm core in both the 50 kA and 2 MA cases. Fourteen of the
50 kA sample re-enter the core, versus none at 2 MA; the refined 50 kA sample
has thirteen. Some sampled paths make ten entries. These small trajectory
samples are not ensemble bounce-rate estimates.

## Interpretation and useful next levers

Increasing current scales B without changing the vacuum field-line topology
or mirror ratios. Better magnetization alone does not close a loss channel.
The stronger-field trajectories here enter the core but leave radially after
one pass. Following open field lines more adiabatically is a plausible
explanation; confirming it requires field-line and magnetic-moment diagnostics.
Near the null, the usual magnetic-moment/loss-cone approximation can fail.

The next geometry study should vary gun placement and local-B pitch together
with coil separation and the physical collecting surfaces. A multi-coil cusp
layout is also worth comparing: this opposed-loop configuration has a radial
ring loss channel. Rank settings by **core residence and repeated access**,
not just time somewhere inside the bounding volume.

Electron space charge must then be solved from those residence distributions.
A negative cloud attracts hydrogen ions but repels incoming electrons; it may
produce a near-gun virtual cathode that blocks injection instead of a useful
central well. Measure central potential and core inventory separately from the
global potential minimum. Neutral hydrogen first needs ionization.

Five-eV beams are numerical/low-energy confinement studies. A grounded-source
electron with only 5 eV cannot penetrate a static potential depression more than
about 5 V below its source potential without additional energy. Reactor-scale
ion acceleration needs correspondingly energetic injection and a full power
balance.

## Measurement limits

- Residence includes censored survivors through the observation cutoff. It is
  a lower bound on unlimited-time mean residence, not permanent confinement.
- Each energy uses a window of `50 a/v`; windows therefore differ in seconds.
  The CSV includes residence normalized by `a/v` to expose trivial speed scaling.
- Ensemble escape records determine residence. The legacy occupancy image
  counts samples; adaptive steps can skip histogram times near weak fields, so
  its intensity must not be interpreted as quantitative charge density.
- Green trajectories survive the window; cyan exit −z; purple exit +z; orange
  hit the radial boundary. Colors encode final outcomes, not lost data.
- Lines connect stored positions. “Full” removes browser decimation, not the
  integration-to-storage sampling. Each member stores 32 example trajectories.
- No self-consistent electric field, ions, collisions, or plasma modification
  of B is included in this sweep. Energy preservation in a magnetic pusher alone
  does not validate loss probabilities.

The [space-charge reference](space-charge-rev0.md) replaces occupancy counts
with current × segment-residence deposition and a grounded 3D Poisson solve.
Its separate small-geometry pilot is numerical scaffolding, not a prediction
of this 50 cm device.
