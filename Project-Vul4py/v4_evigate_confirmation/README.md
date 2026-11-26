# v4: executable evidence (evigate) and a confirmatory test

November 26, 2026.

**evigate, step A** (`evigate_stepA/`, `src/evigate_0.1.3.tgz`): on the 29 patches of C1, a blind attacker
writes exploit tests from the report, a verifier with no model runs them in Docker (they must fail on the
original and pass with the patch, 2 of 2), the project's tests must not regress, and a white-box attacker
looks for a bypass. Claiming only with that evidence: 11 claims, 6 false (FAR 54.5%, 95% CI 28.0-78.7%),
so it did not lower the FAR; comparing against the upstream fix explained why.

**Hint-coverage rule** (post hoc, on the main sample): claim only when the patch touches every hinted line
range (+-3 lines). It was confirmed on the 65 valid cases never used before (`prereg/confirm65_ids.txt`),
with C0 and the analysis fixed in `prereg/decisiones_v4.txt` (`src/confirm_v4.py`):

| C0 on 63 complete new cases | Value |
|---|---|
| VRR | 22/63 = 34.9% (24.3-47.2%) |
| FAR of the repairer's claims | 40/61 = 65.6% (53.0-76.3%) |
| FAR with the coverage rule | 11/23 = 47.8% (29.2-67.0%) |
| Rule passes correct vs. wrong patches | 12/21 vs. 11/40; one-sided Fisher p = 0.0237 (confirmed) |
| Correct claims lost | 9 of 21 (safe yield 33.3% -> 19.0%) |

The first analysis was run with 3 cases still without a verdict (N = 60, p = 0.022); it was repeated when the
run ended, as the decisions file requires, and the conclusion did not change. Two cases were lost to the
environment: a flaky tornado test (`test_connection_refused` timed out at 5 s with the upstream fix, which
does not touch that code) and smolagents tests that found an API key in the environment. v5 fixes both.

## Files of the confirmation run

| File | Content |
|---|---|
| `confirm/results.csv` | one row per case (65): verdicts, claims, `hint_coverage` and the decisions of every rule |
| `confirm/summary.md`, `confirm/summary.json` | VRR, FAR and the acceptance rules with 95% Wilson intervals (`src/fa_metrics.py`) |
| `confirm/confirm_v4.json` | the confirmatory analysis of `prereg/decisiones_v4.txt` (`src/confirm_v4.py`): Fisher test, rates, cases lost |
| `confirm/experiment_c0.json` | models, settings and harness of the run |
| `confirm/c0/<case>/llm_response.json` | the frozen record of each case: prompt hashes, answer, tokens, time, HTTP attempts |
| `../logs/calls/calls_v4_confirm.csv` | one row per model call: 65 calls of GPT-6.2 Sol, 848,338 input and 442,252 output tokens, 6.12 USD at list price |
| `../logs/console/v4_confirm_c0.log` | console output of the run |
