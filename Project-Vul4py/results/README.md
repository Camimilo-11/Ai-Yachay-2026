# Results: figures and logs

## `figures/`

`make_figures.py` draws every data figure of both papers from the CSV and JSON files of this repository; run it from
the repository root with `python results/figures/make_figures.py` (or name the figures to redraw). `MANIFEST.json`
records, for each figure, its input and output files with their sha256, and `figure_values.csv` gives every plotted
value with its count, denominator, 95% Wilson interval and source file. The same data and library versions give
byte-identical files. The figures of the final paper use the author's palette (índigo noche, lavanda eléctrico,
verde voltio; the light colours are outlined in indigo so that they read on white paper).

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

## `audit/`

An independent audit of the final paper (Nov 26, 2026): `audit_paper.py` recomputes, from the raw files and without
the project's own code, every checked number of the paper's text and tables and every plotted value.
`audit_checks_before_fixes.csv` is the first run (497 checks, 12 discrepancies, none of which changed a result), and
`audit_checks.csv` the run after the corrections (505 checks: 504 pass and one open item, the per-case hint coverage
of the v3 patches, which is not in the repository). The final run also checks the case records released for v2-v4
and the v5 development check: every file against the sha256 in its record, every patch against `results.csv`, every
verdict against the oracle's `eval.json`, and that no file holds an API key. Rerun with `python results/audit/audit_paper.py . results/audit`.

## `logs/`

- `calls/`: one row per model call (model, role, tokens, seconds, status and list-price cost), one file per run; the
  juror calibration has totals per model. Built by `code/tools/calls_table.py` from the frozen run records.
- `console/`: the console output of every run, as printed on the instance.
