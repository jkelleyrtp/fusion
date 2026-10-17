# One WarpX run on several GPUs

`warpx/campaign.py submit ... --gpus-per-case 8` runs each case as one MPI process per GPU on a single node,
using a second WarpX build (`-DWarpX_MPI=ON`). A case whose first setting is `np=K` uses K processes instead.
Measured on one node of 8 B200s, campaign `mg1`, deck `inputs_3d_cusp_beta`, 2000 steps, 64 kA-turns.

## Speed

| Mesh | GPUs | Run time | Against 1 GPU |
|---|---|---|---|
| 256³ | 1 | 553 s | 1 |
| 256³ | 2 | 297 s | 1.9× |
| 256³ | 4 | 169 s | 3.3× |
| 256³ | 8 | 97 s | 5.7× |
| 256³, mesh split into 64-cell boxes | 8 | 113 s | 4.9× |
| 384³ | 8 | 266 s | |
| 512³ | 8 | 584 s | |
| 256³, coil field on the mesh (`mg2`) | 8 | 36 s | 15× |

Times include start-up and writing output. With the coil field evaluated per particle, that evaluation is most
of the cost; holding it on the mesh (see `warpx-patches.md`) is the larger gain.

## Same answer

Across 1, 2, 4 and 8 GPUs at 256³: electrons and ions held, energy left and the plasma's magnetic energy agree
to 4 significant figures (magnetic energy to 0.2%). The leak-stream half-width varies between 2.81 and 2.86 mm,
the same 2% spread seen between seeds. With the coil field on the mesh the 8-GPU run gives the same held
fractions and a 2.87 mm stream.

## Which GPU each process uses

WarpX warns that every process can see every GPU. `nvidia-smi` on the node during a 512³ run shows one
process on each of the 8 GPUs, each at about 60% utilisation, so the processes are spread as intended.

## Not checked

- Restart from a checkpoint on several GPUs.
- The cylindrical build on several GPUs.
- More than one node. The job rules allow one node per job, so 8 GPUs is the ceiling.
