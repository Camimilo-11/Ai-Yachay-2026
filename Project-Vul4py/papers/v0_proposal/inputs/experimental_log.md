# Experimental log (input for the v0 paper). Every number comes from v0_mvp/.

## Setup
- Benchmark: Vul4Py, commit f80f861012cb7b7cfeca7323be51d33e72eaf8f3 [PENDIENTE: confirm the v0 runs used this
  commit]; 5 cases: CVE-2017-16615, CVE-2017-16618, CVE-2018-7753, CVE-2019-1010017, CVE-2019-10800.
- Model: poolside/laguna-xs-2.1 through NVIDIA's OpenAI-compatible endpoint (NVIDIA API catalog, free),
  approved by the instructor.
- Prompt: one fixed system prompt ("security engineer"; answer CLAIM: YES/NO, CONFIDENCE: 0-100, PATCH: unified
  diff) and one user template per case with the vulnerable versions of the files the reference fix changes
  (at most 4 files, 60 kB) (v0_mvp/code/scripts/run_agent.py). The runner sends temperature 0
  unless another value is given on its command line.
- Benchmark size: 100 vulnerabilities (92 CVEs, 8 GitHub advisories) in 60 open-source Python projects (dataset/vul4py.csv lists
  61 repository URLs because starlette appears under encode/ and kludex/);
  paper: Bui et al. (2026), arXiv:2608.00692.
- Oracle: Vul4Py run_eval.py; a repair is verified when the patch applies, the functional tests pass and the
  exploit (security) tests pass. Skipped tests are reported separately and never count as passes.

## Timeline (from the archive)
- Oct 12: setup checks on an isolated CVE-2017-16615 checkout (a YAML test failed until future 1.0.0 was
  installed; a 16-test run then passed with one SQLAlchemy deprecation warning). Not part of the results.
- Oct 13-14: NVIDIA API configuration and troubleshooting.
- Oct 14: the five generation files were saved between 1:44 p.m. and 3:28 p.m.; evaluation files at about
  4:40 p.m. (archive file times).

## API problems
Some requests returned HTTP 503 (busy / resource limit); earlier setup attempts returned HTTP 410 and 403.
Requests were resubmitted after some failures, so there were more than five requests; only the final saved
answer per case is recorded, and not every failed request was preserved.

## Results per case
| Case | Claim (confidence) | Patch | Functional tests (p/f/e/s) | Exploit tests (p/f/e/s) | Verified | Input tokens | Output tokens | Generation s |
|---|---|---|---|---|---|---|---|---|
| CVE-2017-16615 | yes (95%) | applied, 419 bytes | 15/0/0/0 | 1/0/0/0 | yes | 1083 | 139 | 15.5 |
| CVE-2017-16618 | yes (95%) | did not apply, 547 bytes | not run | not run | no | 1697 | 203 | 49.7 |
| CVE-2018-7753 | yes (95%) | applied, 745 bytes | 234/0/0/2 | 114/8/0/1 | no | 5240 | 214 | 307.98 |
| CVE-2019-1010017 | no (30%) | empty | not run | not run | no | 2394 | 106 | 40 |
| CVE-2019-10800 | yes (95%) | applied, 425 bytes | 50/0/0/18 | 50/1/0/18 | no | 8575 | 183 | 409.3 |

## Aggregate
- VRR = 1/5 = 20% (95% Wilson 3.6-62.4%).
- Positive claims: 4; unverified: 3. FAR = 3/4 = 75% (95% Wilson 30.1-95.4%).
- Tokens: 18,989 input and 845 output in the five saved calls; cost 0 USD (free API catalog).

## Observations
- The model claimed success with 95% confidence on four of five cases; only one was verified.
- One claimed patch did not apply at all; two applied and kept the functional tests passing but left exploit
  tests failing (the vulnerability was not removed).
- The single "no" (30%) came with an empty patch: the model's low confidence matched a non-repair. Its four
  context files were example scripts (examples/*.py), and the model wrote that the vulnerable library code was not
  among them (runs/official/gpt/CVE-2019-1010017/raw_response.txt, generation.json).
- CVE-2019-10800: the patch removes one line and adds it back unchanged, so it changes nothing; it was claimed
  "yes" at 95%, applied, kept the functional tests passing and left 1 exploit test failing (patch.diff).
- The five pilot cases are the first five rows of the benchmark list (dataset/vul4py.csv): MLAlchemy, owlmixin,
  bleach, python-libnmap and codecov-python.

## Limits
Five cases and one model; one saved answer per case after resubmissions; no generation timestamps; failed
requests incomplete. The numbers describe this run only.
