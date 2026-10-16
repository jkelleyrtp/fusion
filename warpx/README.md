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

## cusp/

`make_deck.py` writes the decks. `inputs_3d_cusp_cage` is six coils inside metal rings at `vgrid`,
with electron emitters on a wall at `wall_v`. The coil field is a fixed formula applied to the
particles; the plasma cannot change it. `analyze_cage.py` reduces runs to one JSON line each.

`inputs_3d_cusp_cage_gas` adds uniform H2 gas at density `ngas`. Electrons ionise it at the rate in
`h2_ionization.dat` (binary-encounter-Bethe formula, within 3% of the NIST table). Each ionisation
adds an H2+ ion at gas temperature and an electron. Left out: elastic scattering, excitation,
dissociation, charge exchange, recombination, and depletion of the gas.

## patches/

`prepare_job.py` applies these to WarpX 26.10 before building. For the local build:
`git apply <this directory>/*.patch` in the WarpX checkout.

`ionization-secondary-energy.patch` adds `<collision>.ionization_secondary_energy_scale`. Stock
WarpX gives each of the two electrons leaving an ionisation half the energy in a random direction.
With the option set, the ejected electron's energy W follows 1/(W^2 + scale^2) and the incident
electron keeps its direction and the rest. The gas deck sets 8.3 eV, the measured value for H2.
Without the option WarpX behaves as before.

`python3 cusp/check_ionization.py <warpx.3d> <work dir>` runs electrons through uniform gas at
100 eV, 1 keV and 8 keV and checks the ion count against density x cross-section x speed, the
energy removed per ionisation, and the ejected-electron spectrum. WarpX uses gamma times the speed
in the rate, which makes it 1.6% high at 8 keV; the check expects that.
