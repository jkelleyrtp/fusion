# WarpX runs

Simulations here use WarpX (https://github.com/BLAST-WarpX/warpx, tag 26.10) with the patches in `patches/`.

| | |
|---|---|
| `campaign.py`, `job-template.json` | runs campaigns on the cluster or locally |
| `cusp/` | cusp decks, deck writer, reducers, patch checks |
| `pops/` | electron-well decks and reducers |
| `campaigns/<study>/` | case lists; `campaigns/registry.json` records every campaign |
| `results/` | reduced table of each campaign as last fetched |
| `patches/` | the WarpX patches, how to apply and build ([README](patches/README.md)) |

Local CPU build used for development (apply the patches first):

```bash
git clone --depth 1 --branch 26.10 https://github.com/BLAST-WarpX/warpx.git && cd warpx
cmake -S . -B build -G Ninja -DWarpX_DIMS="3;RSPHERE" -DWarpX_COMPUTE=OMP -DWarpX_MPI=OFF \
  -DWarpX_EB=ON -DWarpX_OPENPMD=OFF -DWarpX_FFT=OFF -DWarpX_QED=OFF -DWarpX_PYTHON=OFF
cmake --build build -j 8
```

## campaign.py

Runs named sets of cases on GPU nodes through the job broker at priority 1.

```bash
python3 campaign.py submit em4 --cases campaigns/cusp/em4_pressure.txt --nodes 2 --question "..."
python3 campaign.py status em4
python3 campaign.py sync em4      # fetches finished cases into results/em4 and writes table.jsonl
```

- A campaign is one directory on shared storage with one queue. Every node given to it takes cases
  from that queue, one per GPU. `submit` on an existing name adds cases, nodes, or both.
- Names cannot be reused: `campaigns/registry.json` records each campaign's question, cases and jobs.
- `submit` refuses if it would hold more than `MAX_NODES` nodes or if too few nodes are free.
- A case whose node is taken away is restarted from its last checkpoint by another GPU, once its
  `CLAIM` file has gone five minutes without being touched. A case is failed when WarpX itself ends badly
  three times from the same point; losing its node does not count.
  The decks checkpoint every `chk_every` steps.
- Each finished case is reduced on the node to `measured.json` by the script `REDUCERS` names for
  its deck.

- `--gpus-per-case 2|4|8` makes the nodes added by that `submit` run each case on several GPUs, one
  WarpX process per GPU, using a second build with MPI. The case line must split the box into at
  least that many pieces, e.g. `amr.max_grid_size=128` for a 256³ mesh on 8 GPUs.

Checked: a run killed at step 150 and restarted from its step-100 checkpoint, with the later
diagnostic rows trimmed as the worker does, gives diagnostics identical in every digit to an
uninterrupted one (electromagnetic deck, CPU build, one thread; `/home/ubuntu/warpx/restart_check`).
Not yet checked: the same on the GPU build, restart of the electrostatic decks with electrodes, and
any run on more than one GPU.

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

`inputs_rz_spindle_fed` is two coils on one axis with opposing currents (a spindle cusp) in
cylindrical (r, z) geometry, with neutral plasma born on a disc at the centre at `feed` per second
and the plasma's own fields solved by Maxwell's equations. It has no electrodes, emitters or coil
casings. Being two-dimensional it affords cells of 0.04 mm in a 1 cm device, against 0.4 mm in the
six-coil runs, which is what it takes to resolve an electron orbit at the leaks. `analyze_spindle.py`
reduces it: what is held, the rate of leaving through the coils and through the gap between them,
the width of each leak next to an electron orbit there, and how far the field has been pushed out.
`campaign.py` runs any deck named `inputs_rz_*` with a second, cylindrical WarpX build.

Limits of that deck: the plasma is born inside. Nothing can vary around the axis, which rules out any
instability that needs to. The coil field is still a fixed formula. The reducer's coil field is checked
against the deck's formula in `tests/test_spindle.py`. Mesh, seed and time-step repeats on the GPU build are
in `results/sp2.jsonl`.

`inputs_rz_picket_fed` is the same in a periodic row of alternating coils (a picket fence), the geometry of
Park et al. 2019, reduced by `analyze_picket.py`. See `docs/picket-park.md` and `docs/cusp-results.md`.

## patches/

`campaign.py` applies these to WarpX 26.10 before building. How to apply and build by hand is in
[`patches/README.md`](patches/README.md); the checks behind each are in `docs/warpx-patches.md`.

`ionization-secondary-energy.patch` adds `<collision>.ionization_secondary_energy_scale`. Stock
WarpX gives each of the two electrons leaving an ionisation half the energy in a random direction.
With the option set, the ejected electron's energy W follows 1/(W^2 + scale^2) and the incident
electron keeps its direction and the rest. The gas deck sets 8.3 eV, the measured value for H2.
Without the option WarpX behaves as before.

`python3 cusp/check_ionization.py <warpx.3d> <work dir>` runs electrons through uniform gas at
100 eV, 1 keV and 8 keV and checks the ion count against density x cross-section x speed, the
energy removed per ionisation, and the ejected-electron spectrum. WarpX uses gamma times the speed
in the rate, which makes it 1.6% high at 8 keV; the check expects that.

`coil-field-on-grid.patch` adds `particles.B_ext_particle_on_grid`, for use with
`particles.B_ext_particle_init_style = parse_B_ext_particle_function`. Stock WarpX evaluates the
coil-field formula for every particle on every step, which is most of the run time. With the option
set, the formula is evaluated once on the mesh and particles interpolate it along with the plasma's
own field. The formula must not depend on time. The field-energy and field-probe diagnostics still
report the plasma's field alone. Without the option WarpX behaves as before.

Checked on the CPU build only:
- One electron followed for 150 ps ends 87 nm from an independent calculation at 128 cells across,
  against 85 nm with the formula evaluated per particle. At 64 cells it is 1.7 µm.
- A 600-step plasma-ball run at 64 cells differs from the per-particle run by less than a second
  random seed does, in every diagnostic, and takes 173 s against 784 s (8 threads each).

Not yet checked: the GPU build, its speed there, and decks with electrodes.

`inputs_3d_cusp_beta` is the electromagnetic deck: a neutral ball of electrons and ions released at
the centre of the coils, with the fields of the plasma's own charges and currents solved on the mesh
by Maxwell's equations. The coil field is still a fixed formula added at the particles, so the total
field a particle feels is the coil field plus whatever the plasma makes. No electrodes, no emitters.
The time step must stay below 0.577 x cell size / speed of light.
