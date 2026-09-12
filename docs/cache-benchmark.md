# CUDA cache measurement

Measured on 2026-09-12 with simulator/cache revision `9599c7f`. Two broker
jobs each used one eight-B200 node at priority 1 and shut down after completion:
`jonathan-cusp-cache-65f536` and `jonathan-cusp-cache-a34d77`.

| Batch | Eight-process wall time | Per-worker extension setup, min–max |
|---|---:|---:|
| First job, cold cache | 83.73 s | 75.60–76.06 s |
| First job, fresh processes | 8.06 s | 0.034–0.094 s |
| Second job, fresh node/processes | 8.19 s | 0.037–0.097 s |
| Second job, second fresh batch | 8.21 s | 0.035–0.063 s |

The cold batch compiled once; its other seven workers waited for that build.
The other 24 workers loaded the same persistent library without rebuilding.
All 32 workers passed the CUDA push smoke check, with identical library hash
and modification time. These checks exercise compilation/loading and a simple
particle push, not the scientific accuracy of an entire confinement run.

The practical saving is about 76 seconds per fresh eight-worker batch with this
unchanged toolchain and source. Python/Torch startup still takes about eight
seconds for the batch; extension loading alone is below 0.1 seconds. These times
exclude broker queueing, pod startup, and image pulls. Cache reuse does not change
the simulation-loop throughput.

Environment: Python 3.12.3, Torch 2.11.0+cu129, CUDA 12.9, SM 10.0.
Persistent root: `/public/jonathan/cusp/build_cache`.
Library key: `50e06a3a2b025b94124be649`.
SHA256: `b2cd338f81d2a553bb4703c078345fbad5b60c05d3a81a56138286433117ec6c`.

Raw per-worker measurements: [results/cache-benchmark](../results/cache-benchmark/).
