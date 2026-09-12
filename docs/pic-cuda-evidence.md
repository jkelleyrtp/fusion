# Charged PIC comparisons encounter reference variability

CUDA remains unvalidated under the existing long-run acceptance checks.
The FP64 reference also fails those checks against an identical repeat.
This establishes a limitation of the current comparison; it does not prove
that every CUDA operator is correct.

## Experiments and provenance

All jobs used one B200 on one broker-managed AWS node at priority 1, with
automatic shutdown and a 600-second cleanup TTL.

| Experiment | Broker job | Immutable source | Result |
|---|---|---|---|
| Boris arithmetic preflight and strict CUDA validation | `jonathan-pic-cuda-3c4a2c3b893f-9f9afe` | `5639b4522465b95e2d931ac38aeed90b41afc5ac` | Preflight, controls and vacuum pass; charged final state fails |
| Identical reference repeat and fixed-input operators | `jonathan-pic-cuda-f1a8b7bea7fa-7e155f` | `1b9945a51b301efce3ef120af4010b07f65fff79` | Diagnostic completes; repeated charged reference fails |

The first job's automatic retry was stopped. Its comparisons passed local
operators, closed controls, and the vacuum external-gun checkpoints at steps
1, 64, 512, 2,048 and 8,192. The charged case passed through 2,048, then failed
at 8,192. The Boris preflight matched native Torch bitwise.

The repeat diagnostic used Torch `2.11.0+cu129`, CUDA `12.9` and FP64. Both
reference instances received identical 1 A external-gun packets for 8,192
steps of 4 ps: **32.768 ns**, distinct from the 30 ns refinement campaign.
It passed the original comparisons through 2,048 steps and failed at 8,192.

Saved paired states:

```text
/public/devcontainer-shared/jonathan/cusp/runs/pic-cuda-3c4a2c3b893f/
  attempt-20260912-193828-953231718/validation/external-1A-8192.npz
/public/devcontainer-shared/jonathan/cusp/runs/pic-cuda-f1a8b7bea7fa/
  attempt-20260912-194828-832002789/validation/reference-repeat-8192.npz
```

## Final-state comparison

The original relative tolerance is `1e-10`. Absolute tolerances remain
`1e-13 m` for position, `1e-5 m/s` for velocity, `1e-25 C` for nodal charge
and `1e-10 V` for potential. A component passes when its error is within
absolute tolerance plus relative tolerance times the reference magnitude.
Maximum absolute errors alone therefore do not determine pass/fail.

| Quantity | Reference vs CUDA: failing components | Reference vs repeat: failing components | Maximum absolute reference-repeat error |
|---|---:|---:|---:|
| Position, 193,413 components | 0 | 1 | 6.6473e−13 m |
| Velocity, 193,413 components | 20 | 17 | 5.9099e−4 m/s |
| Nodal charge, 35,937 components | 3 | 3 | 1.4217e−23 C |
| Potential, 35,937 components | 0 | 0 | 1.1369e−11 V |

All compared runs have the same 64,471 live IDs, weights, entry counts and
loss faces: 81 inlet losses, 984 opposite-end losses and no transverse-wall
losses. Reference-repeat birth times and total dwell are equal; core dwell
and tracked wall times meet the original tolerances.

These are two individual pairs, not a distribution of numerical error.
Neither their similarity nor the small absolute differences clears the
failed CUDA acceptance gate.

## Fixed-input operators

The diagnostic holds the final reference particle population fixed. It
repeats each deposit eight times against a first deposit, then compares
shared-input operators.

| Measurement | Unequal components | Maximum absolute difference |
|---|---:|---:|
| Torch deposit, identical-input repeats | 562–643 / 35,937 | 3.9291e−24 to 7.6514e−24 C |
| CUDA deposit, identical-input repeats | 579–607 / 35,937 | 1.4476e−24 to 4.3427e−24 C |
| Torch vs CUDA deposit | 836 / 35,937 | 3.9291e−24 C |
| Poisson, identical deposited input | 0 / 35,937 | 0 V |
| Gather, shared potential and positions | 159,414 / 193,413 | 5.8208e−11 V/m |
| Boris, shared velocities and E/B fields | 0 / 193,413 | 0 m/s |

The production reference accumulates charge with `index_add_`; the CUDA
deposit uses `atomicAdd`. The measurements establish nonrepeatable accumulation
on fixed inputs for both. Floating-point accumulation order is the leading
mechanism, consistent with those implementations. Gather also has a distinct
small arithmetic difference. These observations do not isolate how much each
contributes to the coupled long-run discrepancy.

## Next diagnostic design

Add an explicit `--deterministic-reference` mode only to
`diagnose_pic_reproducibility.py`. It calls
`torch.use_deterministic_algorithms(True, warn_only=False)` before creating
the reference. Unsupported operations must raise; there is no silent fallback.
This selects Torch's deterministic accumulation implementation without editing
the FP64 operators, injection, integrator, production defaults or tolerances.
The custom CUDA atomic kernel is unaffected by Torch's selection.

Repeat the same charged configuration and checkpoints. Preserve the original
strict comparison and additionally compare every saved state quantity at
`rtol=0, atol=0`, with corresponding uninitialized tracking NaNs equal.
Repeat fixed-input operators as before. Record the mode and toolchain in the
configuration and diagnostic report.

Acceptance for this diagnostic is repeatable reference states and fixed-input
reference deposition on this toolchain. It is not CUDA validation or physical
convergence. If repeatability is established, use that control to investigate
deposit/gather arithmetic and design an explicit CUDA acceptance protocol.
The existing failed gate remains visible until a reviewed protocol passes.

Performance timings were not reached in the strict CUDA validation.
No production speedup is established. The
[next simulation milestones](transient-pic.md#research-gates-after-startup-and-refinement)
separate this numerical work from physical inlet, mesh, species and scaling
studies.
