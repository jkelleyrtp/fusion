# Development

## Layout

| Path | What |
|---|---|
| `warpx/campaign.py` | Campaign runner: `submit`, `add`, `status`, `sync`, `reduce`, `local` |
| `warpx/job-template.json` | The broker job every campaign node is submitted as |
| `warpx/cusp/inputs_*`, `warpx/cusp/make_deck.py` | Cusp decks and the script that writes them |
| `warpx/cusp/analyze_*.py` | Reducers: one finished case to one `measured.json`. `REDUCERS` in `campaign.py` maps decks to them |
| `warpx/cusp/check_*.py`, `vacuum_dwell.py` | Checks of the patches against independent calculations |
| `warpx/pops/` | Decks and reducers of the electron-well study |
| `warpx/campaigns/<study>/*.txt` | Case lists: one case per line, `name deck setting=value ...` |
| `warpx/campaigns/registry.json` | Each campaign's question, cases and jobs. Written by `campaign.py`; names are never reused |
| `warpx/results/<campaign>.jsonl` | Reduced table of each campaign as last fetched, one line per finished case |
| `warpx/patches/` | Patches applied to WarpX 26.10 |
| `tests/` | stdlib `unittest` suite for the above |
| `docs/` | Results, methods, prior work |
| `legacy/` | The in-house particle code and everything that belongs to it |

Paths outside the repository that `campaign.py` uses: the local WarpX checkout and CPU builds under
`/home/ubuntu/warpx/warpx`, fetched results under `/home/ubuntu/warpx/results`, and shared storage on the
cluster at `/public/jonathan/cusp`.

## Checks

```bash
OMP_NUM_THREADS=1 python3 -m unittest discover -s tests
ruff check tests warpx/campaign.py
```

The legacy code keeps its own suite and narrow lint policy, in [`legacy/README.md`](../legacy/README.md):

```bash
cd legacy && PYTHONPATH=src OMP_NUM_THREADS=1 python3 -m unittest discover -s tests
```

## Adding a result

1. Add the cases to a file under `warpx/campaigns/<study>/` and run them with `campaign.py`.
2. `campaign.py sync NAME`, then copy `table.jsonl` to `warpx/results/NAME.jsonl`.
3. Only cases whose `DONE` reads `complete` are in the table. Quote case names in the write-up so every number
   can be found there.
