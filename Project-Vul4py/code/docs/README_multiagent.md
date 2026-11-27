# False assurance in LLM vulnerability repair: multi-model pipeline v2

This package extends Vul4Py (commit `f80f861`) for the course lab "Measuring False Assurance in
LLM-Based Automated Vulnerability Repair". It contains (1) environment repairs that make far more of
the 100 cases usable, and (2) an oracle-blind multi-model repair pipeline with anti-hallucination
protocols and a debate between patches. The v1 configuration below uses only OpenAI models, with one
key; models from NVIDIA's free API catalog can be mixed in, but its limit of about 40 requests per
minute per account (reported by its users) makes a run of this size much slower. Configuration v2
(Nov 25, 2026; see "v2: jury from other families") keeps the GPT analyst and repairer and takes the
jury from Claude (official Anthropic SDK) and DeepSeek (its OpenAI-compatible API), so no reviewer
shares a family with the patches it judges.

## Files (copy into the Vul4Py repository root; the zip already has this layout)

Paths in this document are inside the Vul4Py checkout. In this repository, `scripts/` is `code/scripts/`,
`dataset/` is `code/dataset/` and `models.json` is `code/models.json`.

| File | Purpose |
|---|---|
| `scripts/build_environment.sh` | Builds and validates the benchmark environment, no API calls (see below) |
| `scripts/prepare_robust.py` | `prepare.py` + fetch-by-SHA when a fix commit lives only on a pull-request ref |
| `scripts/scan_wrapper.py` | `vul4py.py` unchanged + a snapshot of the files each install builds in the checkout |
| `scripts/postinstall.py` | Snapshot/restore of the post-install state (used by the scan wrapper and the evaluator) |
| `scripts/eval_harness.py` | Vul4Py verdict for one patch on the post-install state; rebuilds after C/Rust patches; oracle control |
| `scripts/preflight.py` | Oracle control on every OK case and the pre-registered samples |
| `scripts/auto_skip.py` | Vul4Py's own script with two fixes: correct node ids for `_Private` and nested test classes, and exploit tests failing on network errors are never deselected |
| `scripts/oracle_repair.py` | Deselects baseline tests that assert the vulnerable behaviour (they fail with the upstream fix itself) |
| `scripts/vuln_only.py` | Deselects functional tests that fail only on the vulnerable version (used for three cases, `[vuln_only]`) |
| `scripts/protocols.py` | Oracle-blind checks: quoted-evidence verification, mechanical patch gate, refusal detection, localization hint |
| `scripts/multiagent.py` | The pipeline (analyst, repairers, cross-examination, jury, debate, revision, abstention, freeze, evaluation) |
| `scripts/judge_calibration.py` | Listwise reviewer calibration on known-truth patches (pilot only) |
| `scripts/fa_metrics.py` | Per-attempt table and VRR/FAR per acceptance rule, plus protocol and debate statistics |
| `scripts/simulate_design.py` | The Monte Carlo planning simulation behind the proposal |
| `scripts/cost_estimate.py` | Planning estimate of the API cost: calls per stage x each case's context x list prices, in three scenarios |
| `dataset/meta_overrides/*.json` | The benchmark's own per-case fixes plus the environment repairs; every entry has a `_note` |
| `models.json` | Per-model context window, output budget, reasoning effort and list prices (cost estimate only) |
| `sandbox_validation/` | How the overrides were derived (driver, environment levels, order) and `case_status.csv`, the outcome per case; on EC2 only `cost_estimate.py` reads it (case list, fallback context sizes) |

## Environment repairs (why the public benchmark loses most cases)

Every repair changes how a case is installed or which tests run, never a test or its expectations, and
is recorded with its reason in `dataset/meta_overrides/<id>.json` (`_note`). Per case they were applied
in this order, each level only where the previous ones were not enough (`sandbox_validation/` has the
code and `case_status.csv` the outcome per case):

| Problem in the public release | Repair | Tag in `_note` |
|---|---|---|
| `pip install -e .` misses the test dependencies | Extras, requirements files, pytest plugins from `addopts`, packages imported by tests and by the fixed code | `[doctor:deps]` |
| Every case runs on Python 3.11 with 2026 libraries (PyYAML 6, click 8.2, pydantic, numpy 2, python-multipart...); the paper used 3.6-3.11 | The newest CPython the project supported at the fix date and every dependency resolved as of the fix date + 30 days (`uv --exclude-newer`; the fix date itself where that window already broke the suite); kept only where it did not make the case worse | `[doctor:era]` |
| Suites that hang until Vul4Py's 900 s cap | `pytest-timeout` per test (20 s for asyncssh's exploit tests) | `[timeouts]` |
| Tests that fail even with the upstream fix (environment noise) | Vul4Py's own `auto_skip.py`, fixed: node ids of classes such as `_TestFoo` and nested classes were wrong, and exploit tests that fail only for lack of network are never deselected | `[auto_skip:...]` |
| Old baseline tests that assert the vulnerable behaviour make even the upstream fix "break functionality" | `oracle_repair.py` deselects exactly those tests | `[oracle_repair]` |
| Functional tests that already fail on the vulnerable version and pass with the fix: they cannot tell a broken patch from a good one | `vuln_only.py` deselects them (single tests only, at most 10 per case) | `[vuln_only]` |
| Files listed as tests that abort or block the whole pytest session (templates with spaces in the path, a `setup.py`, a pip probe script, benchmark hooks, App Engine-only tests, an SMTP server script and Gradio demo apps that start servers when imported, a `tests/__init__.py` that makes pytest 6 collect a module twice, old tests importing the module the fix deletes), and per-project fixes (a same-named PyPI package installed by mistake, test-extra pins the era level ignored such as pytest-asyncio<0.23 or anyio 4.10, GitPython's `--maxfail=10` and post-clone git setup, the fix-date pytest for pydash, kedro's starters version, Gradio's compiled frontend taken from its release wheel) | Fixed case by case | `[manual]` |
| `_restore_target` runs `git clean -fdx`, deleting compiled extensions and generated files built by the install | `postinstall.py` snapshots the install's products and restores them exactly | harness |
| Fixes outside `.py` files (C in orjson and brotli, Jinja templates in changedetection.io, a deleted module in kedro) | Context and reference fix include every non-test code file the fix changed; patches touching C/Rust trigger a rebuild | harness |
| A fix commit reachable only from a pull-request ref; a `vulnerable_ref` that does not exist | `prepare_robust.py` fetches by SHA; the harness reads the checkouts' HEADs | harness |
| Gradio's functional suite keeps more than 1024 files open, and with Ubuntu's default limit pytest dies before writing its junit, so the case looks broken | `postinstall.py` raises the open-files limit to the system maximum for every test run (the validation sandbox allowed 20000) | harness |
| torch's PyPI wheels are 6+ GB CUDA builds | torch from PyTorch's CPU index at the validated version, as the benchmark already does for two picklescan cases | `[torch_cpu]` |

Validation outcome, in a sandbox the size of the instance (2 vCPU, 7 GiB, Ubuntu 24.04): 99 of the 100
cases end valid (scan OK and oracle control passed); 18 passed the first scan with the public release.
None is corrupt. The one left, pypdf CVE-2025-62708, downloads its exploit PDF from a GitHub attachment
that the sandbox cannot reach; the build script retries it on the instance. The exploit test of requests
CVE-2024-35195 ran there against a local stand-in for https://invalid.badssl.com.
`sandbox_validation/case_status.csv` has the outcome and the repair levels of every case, and a fresh
prepare plus these overrides reproduces the validated metadata of all 100 cases.

Disk: plan for 100 GB. The 200 clones take about 11 GB, the venvs kept for evaluation about 35 GB
(gradio's test requirements and smolagents install the full torch, ~5 GB each), and the build peaks
near 65 GB. Time: each pytest run may take up to 3600 s (gradio's suite takes ~30 min on 2 vCPU) and
each case scan up to 3 h.

## Pipeline v2 (condition C1)

```
context (files the fix changed, library first; line-range hint as in the Vul4Py paper)
  -> analyst: structure + data flow; every claim quotes code; unverifiable quotes are dropped
  -> K repairers (different models): diagnosis with quoted evidence + diff
       -> mechanical gate: applies like Vul4Py would, only shown files, no tests, compiles,
          not a no-op, not oversized; failures go back verbatim (2 retries)
  -> cross-examination: each repairer attacks the others' (anonymous) patches, keeps or revises
  -> equivalent patches merged (same AST effect)
  -> jury (3 reviewers, never a repairer; listwise, order shuffled per juror, gate facts given)
       unanimous on one candidate -> claim
       split -> debate round (others' arguments, citations marked verified/UNVERIFIED, votes hidden,
                a devil's advocate) -> re-vote
       still split -> the leader's author revises against grounded critiques -> gate -> jury
       no unanimity left -> ABSTAIN (no claim; the leading patch is still evaluated)
  -> freeze (SHA-256, read-only) -> Vul4Py: selected patch, every candidate, the first patch
```

The Vul4Py tests, the fixed version and the reference fix are never shown to a model and never
steer the loop. If they did, the system would only claim what the oracle already confirmed and the
false-assurance rate would be zero by construction.

Condition C0 (`--preset c0`): the primary repairer alone, no analyst, gate or jury; claim = its
self-assessment. `--preset c0g` adds only the gate.

## How to run (EC2, Ubuntu 24.04; the Spanish runbook has every step)

```bash
python3.12 -m venv .venv && source .venv/bin/activate && python -m pip install -U pip openai "uv==0.11.32"
mkdir -p runs && bash scripts/build_environment.sh "$(nproc)" 3 2>&1 | tee runs/build.log   # 10-14 h on 2 vCPU

read -rs OPENAI_API_KEY && export OPENAI_API_KEY
python scripts/multiagent.py --models-file models.json \
    --ping openai:gpt-6.2-sol,openai:gpt-5.4-mini,openai:gpt-6.1-sol,openai:gpt-6.1-terra,openai:gpt-6-luna

A=openai:gpt-6-luna
R=openai:gpt-6.2-sol,openai:gpt-5.4-mini
J=openai:gpt-6.1-sol,openai:gpt-6.1-terra,openai:gpt-6-luna
python scripts/cost_estimate.py --analyst "$A" --repairers "$R" --jurors "$J" --main 30 --main all
python scripts/multiagent.py --preset c1 --ids-file runs/preflight/main_ids.txt --runs runs/final --agent c1 \
    --analyst "$A" --repairers "$R" --jurors "$J" --allow-same-family --session final --models-file models.json
python scripts/multiagent.py --preset c0 --ids-file runs/preflight/main_ids.txt --runs runs/final --agent c0 \
    --repairers "${R%%,*}" --session final --models-file models.json
python scripts/multiagent.py --preset c0g --ids-file runs/preflight/main_ids.txt --runs runs/final --agent c0g \
    --repairers "${R%%,*}" --session final --models-file models.json
python scripts/fa_metrics.py --runs runs/final --workspaces workspaces
```

Everything is resumable: frozen attempts are never regenerated, missing evaluations are completed.
Before the first evaluation of a case, the harness repeats its oracle control (vulnerable and reference
versions) once per session. `--session final` makes C1, C0 and C0g share that control: every condition
is judged against the same one, and each case is checked once instead of once per condition (a pass
takes about as long as the build's oracle control, some 6 h for 100 cases on 2 vCPU). Without the flag,
every invocation runs its own control. Never run two multiagent.py processes on the same workspaces at
once: patches are applied in place, and the per-case lock only works inside one process.
Keys come only from the environment. Every model here is a GPT, so the family rule cannot hold:
`--allow-same-family` lets the run start and `experiment_<agent>.json` records the families; a
model is never allowed to review its own patches. Flex (`--openai-extra '{"service_tier": "flex"}'`)
halves the price of gpt-6.1-sol, gpt-6.1-terra and gpt-6-luna (OpenAI does not offer it on the GPT-6.2
models), about 14% off this configuration; a model that rejects it, or a Flex request that keeps
getting 429, goes on at the Standard tier and the drop is recorded.

Cost (`cost_estimate.py`, Standard list prices, Nov 2026): the pilot plus 30 cases about 55 USD (20 to
200 depending on how much the models reason and how many rounds the jury needs), all 99 valid cases
about 140 (55 to 540). With gpt-6.2-astra as a juror the main run costs 1.6 to 1.8 times as much. The
pilot measures the real cost; multiagent.py prints tokens and cost after every run.

Code budget: 40% of the smallest context window in the run, 156k tokens with gpt-5.4-mini. Every case
goes whole except orjson CVE-2024-27454 (about 181k tokens with its C library), which gets excerpts
around the fix; every request stays under the 272K input tokens above which OpenAI doubles the price.
Without gpt-5.4-mini (v2) the budget is about 396k tokens and orjson goes whole too, as in C0 and C0g,
whose only model is gpt-6.2-sol.

## v2: jury from other families (budget of 20 USD per provider)

The OpenAI key provided for the course ran out during the first main run (Nov 25, 11:41 UTC; those outputs are archived
in `runs/final_v0` and excluded). The rest runs on three budgets of 20 USD (OpenAI, Anthropic,
DeepSeek). The repairer stays gpt-6.2-sol (the only one measured in the pilot, so C0, C0g and C1 share
it), gpt-5.4-mini leaves C1 (1 of 5 repaired, the most output tokens, and the only false assurance of
the pilot C1), and the jury comes from Claude and DeepSeek, chosen by `judge_calibration.py`: the three
best by AUROC with at least one per provider, Opus only if its measured cost fits. With one repairer
there is no cross-examination. A reviewer that refuses to judge (Claude `stop_reason: "refusal"`, or a
refusal in words without a verdict) counts as a vote that vouches for nothing: no unanimity, the system
abstains, no further rounds; the vote is stored with `"refused": true`.

Calibration v2 (decided Nov 25, before running it): per pilot case the reviewer judges the upstream fix,
a decoy, the pilot model patches that Vul4Py did not verify, and with `--with-right` also those it did
verify (13 right and 15 wrong candidates per model). In C1 the jury judges model patches, not upstream
fixes, which it may also have memorised. Patches that did not apply are left out (the prompt would say
"applies=yes"). The ranking uses the AUROC over all candidates; the AUROC on real patches only (right
vs wrong) is reported as secondary. `--export-prompts DIR` writes the same prompts without calling any
API, which is how the Claude Code pilot (`piloto_claude`, subscription, no API key) got identical inputs.

```bash
python -m pip install "anthropic==2.14.0"
read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY
read -rs DEEPSEEK_API_KEY && export DEEPSEEK_API_KEY
CAND=anthropic:claude-opus-5-5,anthropic:claude-sonnet-5-5,anthropic:claude-haiku-5-5,deepseek:deepseek-v4-pro,deepseek:deepseek-flash
python scripts/multiagent.py --models-file models.json --ping "$CAND"
NEG=$(for d in runs/pilot/*/; do printf -- '--negatives-from %s ' "${d%/}"; done)   # every pilot run dir
python scripts/judge_calibration.py --ids-file runs/preflight/pilot_ids.txt --models-file models.json --models "$CAND" \
    $NEG --with-right --out runs/judge_calibration_v2
A=openai:gpt-6-luna; R=openai:gpt-6.2-sol; J=<the three chosen>
python scripts/multiagent.py --preset c1 --ids-file runs/preflight/pilot_ids.txt --runs runs/pilot --agent c1v2 \
    --analyst "$A" --repairers "$R" --jurors "$J" --session piloto --models-file models.json
python scripts/multiagent.py --preset c1 --ids-file runs/preflight/main_ids.txt --runs runs/final --agent c1 \
    --analyst "$A" --repairers "$R" --jurors "$J" --session final --models-file models.json
```

### Option B (chosen Nov 25): Claude through Claude Code with the Claude plan

The Claude reviewers run through the Claude Code CLI with a Claude subscription instead of the API
(provider `claudecode:` in models.json; nothing is billed, Claude Code reports the API-equivalent cost).
Each call is `claude -p` in a fresh session, with no tools and no MCP, the role's system prompt
replacing Claude Code's, `--effort` from models.json, the prompt on stdin, from an empty working
directory (no CLAUDE.md of this repository reaches the model) and without `ANTHROPIC_API_KEY` in its
environment (with a key present `claude -p` would bill it). The stage record keeps the model that
actually answered (`model_reported`), the thinking tokens and the API-equivalent cost. A refusal counts
as above. At the plan's usage limit the call waits (10-minute checks, `--claudecode-limit-wait`, 330 min
by default) and then stops the run without freezing cases in flight; a rejected login stops the run
at once; both resume with the same command. `--claudecode-concurrency` (3) caps the `claude`
processes at once.

```bash
curl -fsSL https://claude.ai/install.sh | bash          # Claude Code, native installer (~/.local/bin/claude)
export PATH="$HOME/.local/bin:$PATH" && claude --version
# login, either: a one-year token made on a PC with a browser (`claude setup-token`; model requests only)
read -rs CLAUDE_CODE_OAUTH_TOKEN && export CLAUDE_CODE_OAUTH_TOKEN
# ... or `claude`, choose the subscription, press c to copy the URL, open it elsewhere, paste the code back
# (stored in ~/.claude/.credentials.json; remove it at the end with `claude` then /logout)
read -rs DEEPSEEK_API_KEY && export DEEPSEEK_API_KEY
CAND=claudecode:claude-opus-5-5,claudecode:claude-sonnet-5-5,claudecode:claude-haiku-5-5,deepseek:deepseek-v4-pro,deepseek:deepseek-flash
python scripts/multiagent.py --models-file models.json --ping "$CAND"
NEG=$(for d in runs/pilot/*/; do printf -- '--negatives-from %s ' "${d%/}"; done)
python scripts/judge_calibration.py --ids-file runs/preflight/pilot_ids.txt --models-file models.json --models "$CAND" \
    $NEG --with-right --out runs/judge_calibration_v2
```

The pilot C1 v2 and the main C1 are the commands above with the chosen `claudecode:`/`deepseek:` jurors.

Claude: `reasoning_effort` in models.json becomes `output_config.effort` (Opus 5.5 medium, its
default; Sonnet 5.5 and Haiku 5.5 high), thinking stays adaptive, no temperature, 16,384 output tokens
per call (non-streaming). DeepSeek: `reasoning_effort` high (its default), 65,536 output tokens, no
temperature (it has no effect in thinking mode). An account without money stops the run at once (exit
code 3, nothing in flight frozen): OpenAI 429 insufficient_quota, DeepSeek 402, Anthropic 400 "credit
balance is too low" or a spend limit. DeepSeek costs half outside 01:00-04:00 and 06:00-10:00 UTC on
weekdays; models.json carries the peak prices.

## Outputs per attempt (`runs/<agent>/<vuln_id>/`)

`context.md` (exactly what the models saw), `prompts/*.json` (every message list), `analyst.md` and
`01_analysis_verified.md`, `cand<k>_<stage>_t<n>.md/.diff` (every repairer answer and retry),
`cand<k>_cross.md`, `jury_r<round>_j<j>.md`, `patch_initial.diff`, `cand<k>_final.diff`,
`patch.diff` (selected), `llm_response.json` (frozen record: stages, HTTP attempts, tokens, gate
results, grounding counts, jury rounds and votes, decision, SHA-256 of every artifact), `eval.json`.
Candidates and the first patch are evaluated as `<agent>__cand<k>` and `<agent>__initial`.

## Metrics

`fa_metrics.py` keeps the definitions of the guide (A, F, S, V = A·F·S, FA = D·(1−V), VRR, FAR
with Wilson intervals, exact McNemar against the repairer's claim) for the rules repairer, judge 1,
consensus, majority, unanimous (primary) and gate (τ = 0.8), and adds for v2: abstention rate,
cases resolved by the independent vote / the debate / the revision, patch versions rejected by the
gate and candidates rescued by its feedback, share of citations whose quoted code does not exist,
refusals, and the oracle-best VRR (some candidate was correct) against what the jury selected.
A segfaulting exploit (rc ≥ 128, no junit) counts as S = 0, as in Vul4Py's scan.

## Known limitations

- The context is the set of files the upstream fix changed, plus the line-range hint, as in the
  Vul4Py paper's direct-LLM protocol: it tells the models where to look.
- Public CVEs: models may remember the upstream fix.
- Environment repairs change dependency versions, never tests or expectations; they are listed per case.
- OpenAI classifies GPT-6.2 as "Critical" for cybersecurity with tighter safeguards; refusals are
  recorded as such (`refused`), never as "no vulnerability".
- All models are GPTs: the reviewers share the repairers' family. Model errors are strongly
  correlated, shared providers among the causes (Kim et al., ICML 2025), and an LLM evaluator tends to
  favour its own generations (Panickssery et al., NeurIPS 2024). No reviewer judges its own patch,
  candidates are anonymous and shuffled, and the pilot calibrates every reviewer on known-truth
  patches; still, the measured FAR is that of a GPT-only jury. gpt-6-luna is both analyst and juror
  (every juror gets the same verified analysis).
