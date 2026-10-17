# Cusp confinement in WarpX

Fully kinetic particle-in-cell simulations of plasma held in magnetic cusps (the six-coil Polywell cage and its
two-dimensional relatives), run with [WarpX](https://github.com/BLAST-WarpX/warpx) 26.10 on GPUs.

**The question.** When the plasma pressure is comparable to or above the magnetic pressure, does the width of a
cusp's leaks stay a fixed number of electron orbits as the device grows, or does it grow with the device? The
first makes holding time rise fast with size ("cusp plugging"); the second does not. No published simulation
measures leak width against device size at fixed pressure ratio with a sustained feed
([prior work](docs/prior-work.md)).

## Where it stands (2026-10-16)

**2026-10-17:** every run counted below left charge at the conducting walls, and repeats without that fault
give holding times 14 to 43% lower at high pressure. The size scan is being rerun and its earlier exponents are
withdrawn. See [docs/wall-charge.md](docs/wall-charge.md).

Only finished runs are counted. Every result below uses WarpX patches that no one but their author has reviewed
([warpx/patches](warpx/patches/README.md)).

| Study | Result | Write-up |
|---|---|---|
| Check against a published case (2D picket fence, Park et al. 2019) | Holding time 141 electron crossings against about 135 published; current layer 2.2 electron orbits wide against about 2.1. Nothing tuned. Baseline only; mesh, seed and time-step repeats are not all in | [picket-park.md](docs/picket-park.md) |
| Pressure scan, 2D two-coil cusp | Raising the pressure ratio from 0.1 to 37 widens the leak streams (0.6 to 7.7 mm in the gap) instead of narrowing them. Holding time rises until a ratio of about 8, then falls | not written up yet; data in `warpx/results/sp2.jsonl` |
| Scalings, 3D six-coil cusp at low pressure | Holding time goes as field^0.3, temperature^−0.5, ion mass^0.35, size^1.3 to 1.45: plasma leaves at about the ion sound speed, slowed 2 to 3× by the field | [cusp-blog.md](docs/cusp-blog.md), `warpx/results/fed2.jsonl` |
| Plasma fired in from outside, 3D six-coil | It gets in and is held about as well as plasma born at the centre if the guns sit close to the coils | [gun-fed-cusp.md](docs/gun-fed-cusp.md) |
| Size scan at fixed pressure ratio, 2D picket fence | **In progress.** 0.25× to 2× the published size done, 4× and the controls running. No conclusion yet | `warpx/campaigns/picket/` |
| Electron wells and ion focusing in a sphere (POPS), no magnetic field | Earlier study, finished | [pops-writeup.md](docs/pops-writeup.md), [pops-results.md](docs/pops-results.md) |

What these runs are not: the 3D runs have cells about as large as an electron orbit except at the weakest
fields, the 2D runs cannot show anything that varies around the axis, the coil field is a fixed formula, and
most runs use ions of 57 to 64 electron masses.

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
