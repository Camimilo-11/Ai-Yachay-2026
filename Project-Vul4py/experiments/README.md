# Experiments

One folder per version of the study, in the order they ran. Each folder's README says what ran, the main result and
which files hold the evidence; the decisions fixed before each run are in [`../prereg/`](../prereg/).

| Folder | Dates (2026) | What it holds |
|---|---|---|
| [`v0_mvp/`](v0_mvp/) | Oct 12-14 | Pilot of the proposal: one model through NVIDIA's API on 5 cases, its harness, answers and verdicts |
| [`v1_environment/`](v1_environment/) | to Nov 24 | Scan reports per build round and the oracle control of the 100 cases |
| [`v2_pilot_tournament/`](v2_pilot_tournament/) | Nov 25 | Repairer tournament, the two pipeline pilots and the two juror calibrations |
| [`v3_main/`](v3_main/) | Nov 25-26 | Main sample (C0, C0g, C1) with every claim rule, and the GPT benchmark |
| [`v4_evigate_confirmation/`](v4_evigate_confirmation/) | Nov 26 | evigate on the 29 C1 patches and the confirmatory run of the coverage rule (65 cases) |
| [`v5_rag/`](v5_rag/) | Nov 26-27 | Knowledge base of the retrieval step, development check, main run (H1 not confirmed) and its case records |
