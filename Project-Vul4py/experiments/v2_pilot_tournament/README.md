# v2: pipeline on the instance, repairer tournament, juror calibration

November 25, 2026. The multi-model pipeline (`code/scripts/multiagent.py`) ran on the EC2 instance on the 5 pilot cases
(`prereg/pilot_ids.txt`): a tournament of two repairers, the full pipeline C1 with a jury of GPT models, and the
calibration of candidate jurors from other families on 28 candidates with known truth (13 correct, 15 wrong).
The first attempt at the main run stopped when the API key ran out of credit (Nov 25, 11:41 UTC); those
outputs were archived and excluded.

| Pilot condition (5 cases) | VRR | FAR (repairer's claim) |
|---|---|---|
| Repairer GPT-6.2 Sol | 3/5 | 2/5 |
| Repairer GPT-5.4 mini | 1/5 | 4/5 |
| C1, jury of GPT models | 3/5 | 2/5 (unanimous jury: 1/4) |
| C1 v2, jury of other families | 3/5 | 2/5 |

Juror calibration v2 (`judge_calibration_v2/`): AUROC of the stated confidence from 0.74 (DeepSeek flash) to
0.91 (Claude Opus 5.5); the jury of the main run was chosen from these numbers (`prereg/decisiones_v2.txt`).
See `results/figures/fig_pilot_benchmarks.pdf` and `results/figures/fig_jury_calibration.pdf`.

| File | Content |
|---|---|
| `results.csv`, `summary.md`, `summary.json` | per-attempt rows and metrics of the pilot (fa_metrics.py) |
| `experiment_*.json` | exact configuration of each pilot run |
| `pilot/<arm>/<case>/` | the frozen record of each case (`llm_response.json`: models, tokens, time, HTTP attempts, prompt sha256), every model answer (`*.md`: repairers, analyst, jurors, cross-examination, revisions), every patch (`*.diff`) and the oracle's evaluation (`eval.json`); `pilot/<arm>__initial/` and `__cand*/` evaluate the initial patches and the other candidates, and `pilot/_baseline/` holds the oracle control of each case |
| `judge_calibration_v1/`, `judge_calibration_v2/` | juror verdicts per candidate, summary, token use and cost |
| `../../results/logs/calls/calls_v2_pilot.csv` | every model call of the pilot with tokens, time and cost |
| `../../results/logs/console/v2_*.log` | consoles of the tournament, the pilots and the calibration |

Every answer and patch has the sha256 recorded in its `llm_response.json`, every `patch.diff` has the `patch_sha256`
of `results.csv`, and every `eval.json` gives the verdict in `results.csv` (checked by `results/audit/audit_paper.py`).
The prompts (`context.md`) are not included: they are rebuilt from the benchmark, and their sha256 is in each record.
