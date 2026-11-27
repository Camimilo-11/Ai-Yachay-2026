# Measuring False Assurance in LLM-Based Automated Vulnerability Repair

Research project for the Artificial Intelligence course (Yachay Tech University, 2026), by Camilo Vasquez (Computer
Science, School of Mathematical and Computational Sciences). It is combined, with permission, with the Networks course
(Redes), where the Vul4Py lab was assigned.

**Research question.** When a large language model repairs a real Python vulnerability and claims the
repair works, how often is the claim false when the patch is checked by executable tests, and which
verification steps (a mechanical gate, a jury of models from other families, executable evidence, a
retrieval step) lower that false assurance without losing correct repairs?

**Metrics.** A repair is *verified* when the patch applies, the project's functional tests still pass and
the exploit tests of the CVE pass (the Vul4Py oracle). VRR = verified repairs / complete attempts.
FAR (false assurance rate) = positive claims that are not verified / positive claims. Every proportion is
reported with a 95% Wilson interval.

**Benchmark.** Vul4Py (Bui et al., 2026, arXiv:2608.00692; [PENDIENTE: link to its repository]), commit
`f80f861012cb7b7cfeca7323be51d33e72eaf8f3`: 100 real vulnerabilities (92 CVEs and 8 GitHub advisories) in
60 open-source Python projects, each with the vulnerable and
fixed commits, functional tests and exploit tests. Baseline: our own v0 MVP.

## Versions

Each version was fixed in a decisions file (`prereg/`) before the run it evaluates; later changes only
enter as dated addenda.

| Version | Dates (2026) | What changed | Main result | Folder |
|---|---|---|---|---|
| **v0** (milestone 1: proposal) | Oct 12-14 | One model (poolside/laguna-xs-2.1 through NVIDIA's API) repairs 5 cases; one saved answer per case | VRR 1/5 (20%), FAR 3/4 (75%) | [`v0_mvp/`](v0_mvp/) |
| **v1** | to Nov 24 | Environment repairs: with the public release only 18 of 100 cases pass the scan; with the repairs, 100 of 100 pass the scan and the oracle control | 100 valid cases | [`v1_environment/`](v1_environment/) |
| **v2** | Nov 25 | Pipeline on the EC2 instance: repairer tournament, pilot of the full pipeline, calibration of jurors from other families | Pilot: GPT-6.2 Sol 3/5 vs. GPT-5.4 mini 1/5; jurors chosen by AUROC | [`v2_pilot_tournament/`](v2_pilot_tournament/) |
| **v3** | Nov 25-26 | GPT benchmark on the pilot cases; main sample of 29 cases: C0 (repairer alone), C0g (+ mechanical gate), C1 (+ unanimous jury) | C0: VRR 55.2%, FAR 42.9%; C1: VRR 48.3%, FAR 46.2% | [`v3_main/`](v3_main/) |
| **v4** | Nov 26 | evigate (executable evidence); hint-coverage rule found post hoc and confirmed on 63 new cases | Coverage rule: FAR 65.6% -> 47.8%, one-sided Fisher p = 0.024 | [`v4_evigate_confirmation/`](v4_evigate_confirmation/) |
| **v5** | Nov 26- | RAG with Qdrant so a 20x cheaper model (Claude Haiku 5.5) repairs; harness without secrets and with reruns of flaky tests | running | [`v5_rag/`](v5_rag/) |

## Papers

| Paper | Covers | Format | Folder |
|---|---|---|---|
| Milestone 1, research proposal | v0 | MDPI research article (LaTeX) | [`papers/v0_proposal/`](papers/v0_proposal/) |
| Final research paper | v1-v5 | MDPI research article (LaTeX) | [`papers/final/`](papers/final/) |

## Repository layout

```
README.md, requirements.txt, models.json   models, list prices (USD per million tokens) and settings
src/                 code as of v5 (our scripts and the Vul4Py scripts we changed; MIT license of Vul4Py in src/LICENSE-Vul4Py)
dataset/             environment repairs: 91 meta_overrides and 14 test_overrides, each with its reason (_note)
prereg/              decisions files v1-v5 and the case lists (main, pilot, confirmation, v5)
v0_mvp/ ... v5_rag/  inputs, results and notes of each version
logs/console/        console output of every run
logs/calls/          one row per model call: model, role, tokens, seconds, list-price cost
figures/             make_figures.py and the figures it draws (PDF and PNG) with MANIFEST.json (inputs and their sha256)
tools/calls_table.py builds logs/calls/*.csv from the frozen run records
papers/              the two papers
docs/                README of the multi-model pipeline (environment levels, pipeline, configuration)
```

## Reproducing

1. Clone Vul4Py at commit `f80f861012cb7b7cfeca7323be51d33e72eaf8f3` and copy `src/*` into its `scripts/`
   folder, `dataset/*` into its `dataset/` folder and `models.json` into its root.
2. Build the environments (no API calls): `bash scripts/build_environment.sh` (see `docs/README_multiagent.md`;
   plan for 100 GB of disk and several hours; the instance had 2 vCPU and 7 GiB).
3. Install `requirements.txt` in the project's virtual environment. API keys are read from the environment
   (`read -rs OPENAI_API_KEY && export OPENAI_API_KEY`, the same for the other providers) and never written to
   disk; Claude through the Claude plan needs `CLAUDE_CODE_OAUTH_TOKEN`.
4. Run each version with the commands in its decisions file (`prereg/decisiones_v*.txt`) and its folder README.
5. Tables and figures: `python tools/calls_table.py --runs runs/final --version v3 --out logs/calls/calls_v3_main.csv`
   and `python figures/make_figures.py`.

The prepared workspaces (about 100 GB) and the full run directories are not in this repository; every
result here comes with the command that produced it, and the frozen records of each case are in the
evidence packages listed in each version folder (with their sha256).

## Cost of the experiments (list prices)

| Run | Calls | Input / output tokens | Cost at list price |
|---|---|---|---|
| v0 MVP (NVIDIA API catalog, free) | 5 saved answers | 18,989 / 845 | 0 USD |
| v2 pilot (tournament and pilots) | 117 | 1,283,730 / 986,284 | 7.22 USD |
| v2 juror calibration | 25 | see `logs/calls/calls_v2_judge_calibration_totals.csv` | 2.64 USD (1.55 API-equivalent on the Claude plan) |
| v3 main sample (C0, C0g, C1) | 280 | 8,105,924 / 2,356,785 | 34.40 USD (Claude jurors at API-equivalent price) |
| v4 confirmation (C0, 65 cases) | 65 | 848,338 / 442,252 | 6.12 USD |
| v5 development check (5 pilot cases, both arms) | 10 | 138,975 / 220,165 | 0.12 USD (Claude plan, API-equivalent) |
| v5 (Haiku 5.5, with and without RAG, 95 cases) | running | | |

## Use of AI tools

Large language models are the object of study: their calls, prompts, answers and costs are recorded in
`logs/`. The code, analyses and documents of this project were developed with the help of an AI assistant
(Claude, Anthropic); every result in the papers comes from the runs and files in this repository.
[PENDIENTE: confirm this statement and the course's policy on AI-assisted writing.]
