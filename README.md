# Cusp confinement in WarpX

Fully kinetic particle-in-cell simulations of plasma held in magnetic cusps (the six-coil Polywell cage and its
two-dimensional relatives), run with [WarpX](https://github.com/BLAST-WarpX/warpx) 26.10 on GPUs.

**The question.** When the plasma pressure is comparable to or above the magnetic pressure, does the width of a
cusp's leaks stay a fixed number of electron orbits as the device grows, or does it grow with the device? The
first makes holding time rise fast with size ("cusp plugging"); the second does not. No published simulation
measures leak width against device size at fixed pressure ratio with a sustained feed
([prior work](docs/prior-work.md)).

## Where it stands (2026-10-18)

The longer account, with figures of the runs, is [docs/cusp-paper.md](docs/cusp-paper.md). Only finished runs are
counted. Every result uses WarpX patches that no one but their author has reviewed
([warpx/patches](warpx/patches/README.md)).

| Study | Result | Write-up |
|---|---|---|
| Boundary between plasma and field, 2D | 1.8 to 3.5 electron orbits thick in 60 of 61 runs, at every size | [progress-2026-10-17.md](docs/progress-2026-10-17.md) |
| Size scan, 2D, three treatments of the ends | Holding time goes as size^0.71 (row of coils, wrap-around ends), size^0.49 (mirror ends) and size^0.55 (two coils, real end walls), over a factor of 4 in size. Not size^1 (leak of fixed width in orbits), not size^0. The largest sizes still depend on particle count and the two-coil runs had not settled | [progress-2026-10-18.md](docs/progress-2026-10-18.md), [cusp-results.md](docs/cusp-results.md) |
| Check against a published case (2D row of coils, Park et al. 2019) | Boundary thickness agrees (2.2 against 2.1 orbits). Holding time does not: 58 to 63 electron crossings over the paper's own part of the run against its 135 to 174. An earlier match (141) was made by charge left at the walls | [park-vs-warpx.md](docs/park-vs-warpx.md), [wall-charge.md](docs/wall-charge.md) |
| Pressure scan, 2D two-coil cusp, before the wall correction | Raising the pressure ratio from 0.1 to 37 widens the leak streams (0.6 to 7.7 mm in the gap). Holding time rises until a ratio of about 8, then falls | [cusp-results.md](docs/cusp-results.md) |
| 3D six-coil cusp at low pressure | Holding time goes as field^0.3, temperature^−0.5, ion mass^0.35, size^1.3 to 1.45: plasma leaves at about the ion sound speed, slowed 1.5 to 5× by the field | [cusp-blog.md](docs/cusp-blog.md) |
| 3D six-coil cusp at high pressure, with and without floating rings | Leaks mainly through the coils, in streams about 6 electron orbits in half-width; held for about 12 electron crossings. Floating rings add 3% inside the cage; a further cloud of electrons gathers at the charged rings and was still growing at 18 ns | [cusp-paper.md](docs/cusp-paper.md) |
| Rings held at set voltages, 3D | **Running** (campaigns `rv1`, `rv2`): floating, grounded, rod-only, no rings, +50 to +400 kV | [ring-voltage-design.md](docs/ring-voltage-design.md) |
| Plasma fired in from outside, 3D six-coil | Held 45 to 65% as long as plasma born at the centre | [gun-fed-cusp.md](docs/gun-fed-cusp.md) |
| Electron wells and ion focusing in a sphere (POPS), no magnetic field | Earlier study, finished | [pops-writeup.md](docs/pops-writeup.md) |

What these runs are not: most use ions of 57 to 64 electron masses and electrons at 100 keV, the sizes span 15 to
about 190 electron orbits, the 3D runs have cells a quarter of an electron orbit at the coils, the 2D runs cannot
show anything that varies around the axis, and the coil field is a fixed formula.

## Layout

| Path | What |
|---|---|
| `warpx/campaign.py` | Runs named sets of cases on GPU nodes through the job broker, restarts them from checkpoints, reduces each on the node and fetches the reduced tables. See [warpx/README.md](warpx/README.md) |
| `warpx/cusp/` | Decks (`inputs_*`), the deck writer and the reducers (`analyze_*.py`) for the cusp studies |
| `warpx/pops/` | Decks and reducers for the electron-well study |
| `warpx/campaigns/` | The case list of every campaign, by study, and `registry.json`: each campaign's question, cases and jobs |
| `warpx/results/` | One reduced table per campaign, one line per finished case, as last fetched |
| `warpx/patches/` | The three patches applied to WarpX 26.10, how to apply and build |
| `tests/` | Tests of the campaign runner, deck writer and reducers |
| `docs/` | Results, methods and prior work. Start at [docs/README.md](docs/README.md) |
| `legacy/` | The in-house particle code this project used before WarpX, with its tests, results, viewer and notes. Not used by anything above. See [legacy/README.md](legacy/README.md) |

## Running

```bash
cd warpx
python3 campaign.py submit NAME --cases campaigns/<study>/<file>.txt --nodes 1 --question "..."
python3 campaign.py status NAME
python3 campaign.py sync NAME        # fetch finished cases, write the table
python3 campaign.py local NAME --cases FILE   # small cases on this machine's CPUs
```

GPU work goes through the job broker only, at priority 1, one node per job. The binding rules are in
[AGENTS.md](AGENTS.md) and explained in [docs/gpu-jobs.md](docs/gpu-jobs.md).

## Checks

```bash
OMP_NUM_THREADS=1 python3 -m unittest discover -s tests
ruff check tests warpx/campaign.py
```
