# Development

## Layout

| path | what |
|---|---|
| `src/transient_pic.py`, `src/pic_kernels.py`, `src/pic_cuda.py` | FP64 electron PIC, its reference particle operators and the CUDA operators |
| `src/run_transient_pic.py` | external-gun electrostatic PIC driver: geometry, guns, casings, output |
| `src/ion_pic.py` | coupled electron and ion PIC with gas ionization and charge exchange |
| `src/electrostatic.py`, `src/steady_space_charge.py` | grounded-box Poisson solver and the stationary trajectory–Poisson iteration |
| `src/run_pic_campaign.py`, `src/run_parameter_sweep.py`, `src/run_space_charge_pilot.py` | one-node campaign runners |
| `src/analyze_*.py` | reductions of fetched campaigns |
| `src/accept_pic_cuda.py`, `src/validate_pic_*.py`, `src/diagnose_pic_*.py`, `src/profile_pic_step.py`, `src/benchmark_*.py` | CUDA acceptance, validation, diagnosis and timing |
| `src/job_progress.py`, `src/export_viewer.py`, `src/serve_viewer.py`, `web/` | dashboard data and the browser control room |
| `src/cusp_sim.py`, `src/cusp_viz.py`, `src/cuda_build_cache.py` | legacy fixed-field orbit simulator, its plots and its CUDA build cache |
| `analysis/fresh/` | scripts behind `docs/fresh-analysis.md` |
| `jobs/*.yaml` | broker-submittable single-node RayJobs |
| `results/` | reports and summaries pulled back from runs |
| `docs/` | designs, evidence and analyses |
| `tests/` | stdlib unittest suite |

## Checks

```bash
PYTHONPATH=src OMP_NUM_THREADS=1 python3 -m unittest discover -s tests
```

There is no repo-wide lint or type policy. `src/cusp_sim.py` and `src/cusp_viz.py` are standalone
legacy scripts; do not broaden linting to them or refactor them. These modules have a narrow policy:

```bash
ruff check src/cuda_build_cache.py tests/test_cuda_build_cache.py
mypy --follow-imports=silent src/cuda_build_cache.py

ruff check src/transient_pic.py src/run_transient_pic.py tests/test_transient_pic.py tests/test_transient_cli.py
mypy --follow-imports=silent src/transient_pic.py src/run_transient_pic.py

ruff check src/electrostatic.py src/steady_space_charge.py
mypy --follow-imports=silent src/electrostatic.py src/steady_space_charge.py
```
