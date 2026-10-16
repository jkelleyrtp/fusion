# WarpX patches

Every run in this repository uses WarpX 26.10 (`ec1660d`, https://github.com/BLAST-WarpX/warpx) with the three
patches in this directory applied. Each is off unless a deck asks for it. What each changes and how it was
checked is in [`docs/warpx-patches.md`](../../docs/warpx-patches.md); the design of the injection patch is in
[`docs/flux-injection-charge.md`](../../docs/flux-injection-charge.md).

| Patch | Adds | Set by |
|---|---|---|
| `coil-field-on-grid.patch` | `particles.B_ext_particle_on_grid`: the coil field is put on the mesh once instead of being evaluated per particle per step | the picket deck, and the 3D case lists from `og1` and `fed2` on. The 2D spindle deck does not use it |
| `flux-paired.patch` | `<species>.<source>.flux_paired`: fed electrons and ions start on top of each other, so the feed leaves no charge behind | the fed, gun, spindle and picket decks; campaigns `fed3`, `jet3`, `sp2` and later |
| `ionization-secondary-energy.patch` | `<collision>.ionization_secondary_energy_scale`: measured energy split between the two electrons leaving an ionisation | the gas deck `inputs_3d_cusp_cage_gas` |

None of the three has been reviewed by anyone but their author.

## Applying

```bash
git clone --depth 1 --branch 26.10 https://github.com/BLAST-WarpX/warpx.git && cd warpx
for patch in <this directory>/*.patch; do git apply "$patch"; done
```

They touch different lines, so the order does not matter. `campaign.py` does the same on the cluster and names
its build directory after a hash of the patch files (`warpx-26.10-cuda-9e4eb929` for the three as they stand),
so changing a patch gets a fresh build rather than reusing an old executable.

Checked 2026-10-16: applied to a clean checkout of the 26.10 tag, in both orders tried, the patches reproduce
byte for byte the 15 changed files of the source tree the local executables were built from.

## Building

Local CPU executables, used by `campaign.py local` and the checks:

```bash
cmake -S . -B build    -G Ninja -DWarpX_DIMS=3  -DWarpX_COMPUTE=OMP -DWarpX_MPI=OFF -DWarpX_EB=ON \
  -DWarpX_OPENPMD=OFF -DWarpX_FFT=OFF -DWarpX_QED=OFF -DWarpX_PYTHON=OFF && cmake --build build -j 8
cmake -S . -B build-rz -G Ninja -DWarpX_DIMS=RZ -DWarpX_COMPUTE=OMP -DWarpX_MPI=OFF -DWarpX_EB=OFF \
  -DWarpX_OPENPMD=OFF -DWarpX_FFT=OFF -DWarpX_QED=OFF -DWarpX_PYTHON=OFF && cmake --build build-rz -j 8
```

The cluster build is the same with `-DWarpX_COMPUTE=CUDA -DCMAKE_BUILD_TYPE=Release`, and `-DWarpX_MPI=ON` for
cases that run on several GPUs (`BUILD_STEPS` in `campaign.py`).
