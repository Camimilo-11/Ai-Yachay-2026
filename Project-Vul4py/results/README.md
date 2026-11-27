# Results: figures and logs

## `figures/`

`make_figures.py` draws every data figure of both papers from the CSV and JSON files of this repository; run it from
the repository root with `python results/figures/make_figures.py` (or name the figures to redraw). `MANIFEST.json`
records, for each figure, its input files with their sha256.

| Figure | Shows |
|---|---|
| `fig_v0_pilot` | The five-case pilot of v0 (proposal paper) |
| `fig_environment` | Cases that pass the scan with the public release and after each build round, and the oracle control |
| `fig_pilot_benchmarks` | VRR of every comparison run on five cases |
| `fig_jury_calibration` | Calibration of the candidate jurors and its cost |
| `fig_main_vrr_far` | VRR and FAR of the main sample and the confirmation run |
| `fig_coverage_rule` | Confirmatory test of the hint-coverage rule |
| `fig_calls_tokens_time` | Tokens and time of every recorded model call |
| `fig_cost_per_repair` | Cost per attempted case and per verified repair in the main sample |

## `logs/`

- `calls/`: one row per model call (model, role, tokens, seconds, status and list-price cost), one file per run; the
  juror calibration has totals per model. Built by `code/tools/calls_table.py` from the frozen run records.
- `console/`: the console output of every run, as printed on the instance.
