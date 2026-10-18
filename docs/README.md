# Documents

Read in this order.

## Results

| | |
|---|---|
| [cusp-paper.md](cusp-paper.md) | Informal paper of 18 October: the question, what the runs show about the leak, size scaling and the 3D cage with and without rings, what failed, and ways to do better. With figures |
| [cusp-results.md](cusp-results.md) | The current tables: pressure scan, six-coil scalings, and the size scan in progress |
| [progress-2026-10-18.md](progress-2026-10-18.md) | Overnight results of 18 October: end treatments, size exponents by model, faults |
| [wall-charge.md](wall-charge.md) | Charge left at the conducting walls in every run before 2026-10-17: the evidence, the fix, and which results are withdrawn |
| [picket-park.md](picket-park.md) | Check of our setup against the published picket-fence cusp of Park et al. 2019 |
| [gun-fed-cusp.md](gun-fed-cusp.md) | Plasma fired into the six-coil cusp from outside |
| [prior-work.md](prior-work.md) | What the literature says about cusp leaks at high pressure, and what is missing from it |
| [park-vs-warpx.md](park-vs-warpx.md) | How Park et al. 2019's code and setup differ from ours, what each difference has been shown to do, and our holding time over Park's own part of the run |
| [park-comparison-audit.md](park-comparison-audit.md) | Item-by-item audit of our picket-fence deck against Park et al. 2019, and the runs that would explain the holding-time gap |
| [ring-voltage-design.md](ring-voltage-design.md) | Design, with CPU tests, for holding the 3D six-coil rings at chosen voltages without changing WarpX (not yet run on GPU) |
| [electrostatic-plugging-prior-work.md](electrostatic-plugging-prior-work.md) | What is published on charged cages and plugging cusp leaks with electrodes, with what was read in full and what was not |

## Methods

| | |
|---|---|
| [../warpx/README.md](../warpx/README.md) | The campaign runner, the decks and the reducers |
| [warpx-patches.md](warpx-patches.md) | What each WarpX patch changes and how it was checked |
| [flux-injection-charge.md](flux-injection-charge.md) | The charge fault in WarpX's flux injection and the design of the fix |
| [multi-gpu.md](multi-gpu.md) | One run on several GPUs: speed and checks |
| [gpu-jobs.md](gpu-jobs.md) | How GPU jobs are submitted and why the rules in `AGENTS.md` exist |
| [development.md](development.md) | Layout, tests and lint |

## Earlier studies in WarpX

| | |
|---|---|
| [size-scan-blog.md](size-scan-blog.md), [with charts](artifacts/size-scan-blog.html) | Plain-language account of the size scan: the question, how the runs work, the current along the axis, the mirror fault, and where the answer stands |
| [cusp-blog.md](cusp-blog.md) | Six-coil cage with electrodes and electron emitters: wells, losses, and why electrons alone were not enough |
| [pops-writeup.md](pops-writeup.md), [pops-results.md](pops-results.md), [pops-blog.md](pops-blog.md) | Electron wells and ion focusing in a sphere with no magnetic field |
| `artifacts/` | The HTML pages built for those two studies |

Notes on the in-house particle code used before WarpX are in [../legacy/docs](../legacy/docs).
