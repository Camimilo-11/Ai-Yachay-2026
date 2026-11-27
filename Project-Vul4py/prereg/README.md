# Preregistration: decisions fixed before each run

Each decisions file (in Spanish) was written and committed before the run it governs: models, cases, conditions,
primary test and analysis. Later changes enter only as dated addenda inside the same file. The files are kept exactly
as committed, so the hashes they quote still match.

| File | Governs | Version |
|---|---|---|
| `decisiones_v1.txt` | First main run with a jury of GPT models (stopped when the API credit ran out) and the C0 and C0g conditions | v3 |
| `decisiones_v2.txt` | Juror calibration v2, the cross-family jury and the main C1 run | v2-v3 |
| `decisiones_v3.txt` | evigate (executable evidence) on the 29 C1 patches | v4 |
| `decisiones_v4.txt` | Confirmatory test of the hint-coverage rule on the 65 unused cases | v4 |
| `decisiones_v5.txt` | Retrieval for a cheaper model and the rule for v6 | v5 |
| `decisiones_v5_1.txt` | Exploratory v5.1: related project code, coverage check and retrieval keyed by the case's CWE | v5.1 |

| Case list | Cases | Use |
|---|---|---|
| `split.json` | 100 | The single split of the valid cases, made before any run of v2-v5 (seeds 7 and 42) |
| `oracle_valid.txt` | 100 | Cases that passed the oracle control |
| `pilot_ids.txt` | 5 | Pilot cases (seed 7): tournament, pilots, calibration, v5 development check |
| `main_ids.txt` | 30 | Main sample (seed 42): v3, v4 evigate, v5 |
| `confirm65_ids.txt` | 65 | The cases never used before v4: confirmatory test, v5 |
| `confirm30_ids.txt` | 30 | Alternative confirmation sample, fixed in case of low API credit; not used |
| `v5_ids.txt` | 95 | Main sample plus confirmation cases, for v5 |
