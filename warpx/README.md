# WarpX runs

Simulations here use WarpX (https://github.com/BLAST-WarpX/warpx, tag 26.10), not the PIC code in `src/`.

Local CPU build used for development:

```bash
git clone --depth 1 --branch 26.10 https://github.com/BLAST-WarpX/warpx.git && cd warpx
cmake -S . -B build -G Ninja -DWarpX_DIMS="3;RSPHERE" -DWarpX_COMPUTE=OMP -DWarpX_MPI=OFF \
  -DWarpX_EB=ON -DWarpX_OPENPMD=OFF -DWarpX_FFT=OFF -DWarpX_QED=OFF -DWarpX_PYTHON=OFF
cmake --build build -j 8
```

## pops/

`inputs_3d_ideal_well` puts deuterons in a prescribed harmonic well inside a grounded sphere and
solves their own space charge. The well stands in for a uniform electron cloud, so this stage has no
electrons and nothing cancels the ion charge at the focus. Every `my_constants` value can be
overridden on the command line:

```bash
warpx.3d inputs_3d_ideal_well my_constants.fill=1e-2 my_constants.comp=10
python3 analyze_ideal_well.py <run directory>...
```

`fill` is the number of ions divided by the number of electrons in the cloud that would make the
well. `comp` is the radius compression the cloud's temperature allows when space charge is absent.
