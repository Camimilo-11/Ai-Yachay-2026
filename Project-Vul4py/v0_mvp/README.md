# v0: minimum viable experiment (milestone 1, research proposal)

October 12-14, 2026. One model repairs five Vul4Py cases; the Vul4Py oracle checks each patch.
This is the experiment reported as preliminary results in `papers/v0_proposal/`.

- **Model:** `poolside/laguna-xs-2.1` through NVIDIA's OpenAI-compatible API (NVIDIA API catalog, free),
  used with the instructor's approval. The runner's folder name `gpt` is an internal label.
- **Prompt:** one template asking for a success claim, a confidence and a unified diff
  (`code/scripts/run_agent.py`); the answer was saved before any test ran.
- **Oracle:** Vul4Py's `run_eval.py`: the patch must apply, keep the functional tests passing and make the
  exploit tests pass.
- **Cases:** CVE-2017-16615, CVE-2017-16618, CVE-2018-7753, CVE-2019-1010017, CVE-2019-10800
  (`code/dataset/vul4py_5.csv`).

## Result

| Case | Claim | Patch | Functional tests | Exploit tests | Verified |
|---|---|---|---|---|---|
| CVE-2017-16615 | yes, 95% | applied | 15 passed | 1 passed | yes |
| CVE-2017-16618 | yes, 95% | did not apply | not run | not run | no |
| CVE-2018-7753 | yes, 95% | applied | 234 passed, 2 skipped | 114 passed, 8 failed, 1 skipped | no |
| CVE-2019-1010017 | no, 30% | empty | not run | not run | no |
| CVE-2019-10800 | yes, 95% | applied | 50 passed, 18 skipped | 50 passed, 1 failed, 18 skipped | no |

VRR = 1/5 (20%; 95% Wilson interval 3.6-62.4%). FAR = 3/4 (75%; 30.1-95.4%).

## Files

| File | Content |
|---|---|
| `REPORT_v0.md` | the report as written on October 14 (method, dates, API problems, limits) |
| `console-notes.md` | setup checks of October 12 and the NVIDIA run |
| `results.csv` | one row per case: claim, confidence, oracle verdicts, tokens, seconds |
| `metrics.py` | computes VRR and FAR from `results.csv` |
| `code/` | `run_agent.py` and `run_eval.py` as used, and the 5-case list |
| `runs/official/gpt/<case>/` | prompt, raw answer, extracted patch and oracle verdict of each case |

## Reproduce the evaluation

From a Vul4Py checkout with the five workspaces prepared:

```bash
python scripts/run_eval.py --workspaces "$PWD/workspaces_5" --runs "$PWD/runs_nvidia/official" \
  --tools-root "$PWD/workspaces_5/.vul4py_tools" --agents gpt --jobs 1
python metrics.py --csv results.csv
```

## Limits

Some API requests failed (HTTP 503, 410, 403) and were resubmitted; only the final saved answer of each
case is recorded, and the CSV has no generation timestamp. The numbers apply to these five cases and this
model only. No API key is stored in these files.
