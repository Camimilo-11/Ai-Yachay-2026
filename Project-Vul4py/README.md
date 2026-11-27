# Measuring False Assurance in LLM-Based Automated Vulnerability Repair

Research project for the Artificial Intelligence course (Yachay Tech University, 2026), by Camilo Vasquez (Computer
Science, School of Mathematical and Computational Sciences). It is combined, with permission, with the Networks course
(Redes), where the Vul4Py lab was assigned.

When a large language model repairs a real Python vulnerability and claims that the repair works, how often is the
claim false when executable tests check the patch, and which verification steps lower that false assurance without
losing correct repairs?

## Start here

| To... | Open |
|---|---|
| read the final paper (v1-v5) | [`papers/final/paper/main.pdf`](papers/final/paper/main.pdf) |
| read the proposal and the five-case pilot (v0) | [`papers/v0_proposal/paper/main.pdf`](papers/v0_proposal/paper/main.pdf) |
| see what each version ran and found | [`experiments/`](experiments/), one folder and README per version |
| check what was fixed before each run | [`prereg/`](prereg/) |
| see the figures and every model call | [`results/`](results/) |
| run the code | [`code/`](code/) and its [pipeline README](code/docs/README_multiagent.md) |

## Main results so far

| Finding | Value |
|---|---|
| Cases with a valid oracle: public release vs. after the environment repairs | 18 vs. 100 of 100 |
| False assurance rate (FAR) of GPT-6.2 Sol alone, main sample (29 cases) | 42.9% (12 of 28 positive claims) |
| FAR with a mechanical gate / with a unanimous jury of Claude and DeepSeek models | 50.0% / 46.2% |
| FAR when the claim needs exploit tests written by a model (evigate) | 54.5% |
| Hint-coverage rule, confirmed on 63 unused cases | FAR 65.6% -> 47.8%, one-sided Fisher p = 0.024 |
| Cost per verified repair: repairer alone vs. full pipeline with jury | 0.21 vs. 1.96 USD (list price) |
| v5: retrieval (RAG) for Claude Haiku 5.5, a model 20 times cheaper | running |

**Metrics.** A repair is *verified* when the patch applies, the project's functional tests still pass and the exploit
tests of the vulnerability pass (the Vul4Py oracle). VRR = verified repairs / complete attempts. FAR = positive
claims that are not verified / positive claims. Every proportion is reported with a 95% Wilson interval.

**Benchmark.** Vul4Py (Bui et al., 2026, arXiv:2608.00692), from the repository used in the lab
([github.com/tabudz/vul4py](https://github.com/tabudz/vul4py)) at commit `f80f861012cb7b7cfeca7323be51d33e72eaf8f3`:
100 real vulnerabilities (92 CVEs and 8 GitHub advisories) in 60 open-source Python projects, each with the vulnerable
and fixed commits, functional tests and exploit tests.

## Repository layout

```
Project-Vul4py/
├── README.md                this guide
├── papers/
│   ├── v0_proposal/         milestone 1: proposal and five-case pilot (MDPI LaTeX + PDF)
│   └── final/               final paper, v1-v5 (MDPI LaTeX + PDF)
├── experiments/             one folder per version, each with a README (what ran, results, files)
│   ├── v0_mvp/              pilot: one model through NVIDIA's API on 5 cases
│   ├── v1_environment/      environment repairs, scan and oracle control of the 100 cases
│   ├── v2_pilot_tournament/ repairer tournament, pipeline pilots, juror calibration
│   ├── v3_main/             main sample: C0, C0g, C1; GPT benchmark
│   ├── v4_evigate_confirmation/  executable evidence and the confirmatory test of the coverage rule
│   └── v5_rag/              retrieval for a cheaper model (knowledge base, development check, results)
├── prereg/                  decisions files v1-v5 and case lists, each fixed before its run
├── results/
│   ├── figures/             make_figures.py, the data figures (PDF and PNG) and MANIFEST.json
│   └── logs/
│       ├── calls/           one row per model call: model, role, tokens, seconds, list-price cost
│       └── console/         console output of every run
└── code/
    ├── scripts/             our scripts and the Vul4Py scripts we changed (Vul4Py's MIT license inside)
    ├── dataset/             environment repairs: 91 meta_overrides and 14 test_overrides, each with its reason
    ├── tools/               calls_table.py, which builds results/logs/calls from the frozen run records
    ├── docs/                README of the multi-model pipeline (environment levels, pipeline, configuration)
    ├── models.json          models, list prices (USD per million tokens) and settings
    └── requirements.txt
```

## Versions

Each version was fixed in a decisions file (`prereg/`) before the run it evaluates; later changes only enter as dated
addenda.

| Version | Dates (2026) | What changed | Main result | Folder |
|---|---|---|---|---|
| **v0** (milestone 1: proposal) | Oct 12-14 | One model (poolside/laguna-xs-2.1 through NVIDIA's API) repairs 5 cases; one saved answer per case | VRR 1/5 (20%), FAR 3/4 (75%) | [`experiments/v0_mvp/`](experiments/v0_mvp/) |
| **v1** | to Nov 24 | Environment repairs: with the public release only 18 of 100 cases pass the scan; with the repairs, 100 of 100 pass the scan and the oracle control | 100 valid cases | [`experiments/v1_environment/`](experiments/v1_environment/) |
| **v2** | Nov 25 | Pipeline on the EC2 instance: repairer tournament, pilot of the full pipeline, calibration of jurors from other families | Pilot: GPT-6.2 Sol 3/5 vs. GPT-5.4 mini 1/5; jurors chosen by AUROC | [`experiments/v2_pilot_tournament/`](experiments/v2_pilot_tournament/) |
| **v3** | Nov 25-26 | GPT benchmark on the pilot cases; main sample of 29 cases: C0 (repairer alone), C0g (+ mechanical gate), C1 (+ unanimous jury) | C0: VRR 55.2%, FAR 42.9%; C1: VRR 48.3%, FAR 46.2% | [`experiments/v3_main/`](experiments/v3_main/) |
| **v4** | Nov 26 | evigate (executable evidence); hint-coverage rule found post hoc and confirmed on 63 new cases | Coverage rule: FAR 65.6% -> 47.8%, one-sided Fisher p = 0.024 | [`experiments/v4_evigate_confirmation/`](experiments/v4_evigate_confirmation/) |
| **v5** | Nov 26- | RAG with Qdrant so a 20x cheaper model (Claude Haiku 5.5) repairs; harness without secrets and with reruns of flaky tests | running | [`experiments/v5_rag/`](experiments/v5_rag/) |

## Reproducing

1. Clone Vul4Py at commit `f80f861012cb7b7cfeca7323be51d33e72eaf8f3` and copy `code/scripts/*` into its `scripts/`
   folder, `code/dataset/*` into its `dataset/` folder and `code/models.json` into its root.
2. Build the environments (no API calls): `bash scripts/build_environment.sh` inside the Vul4Py checkout (see
   [`code/docs/README_multiagent.md`](code/docs/README_multiagent.md); plan for 100 GB of disk and several hours; the
   instance had 2 vCPU and 7 GiB).
3. Install `code/requirements.txt` in the project's virtual environment. API keys are read from the environment
   (`read -rs OPENAI_API_KEY && export OPENAI_API_KEY`, the same for the other providers) and never written to disk;
   Claude through the Claude plan needs `CLAUDE_CODE_OAUTH_TOKEN`.
4. Run each version with the commands in its decisions file (`prereg/decisiones_v*.txt`) and its folder README.
5. Tables and figures, from this repository's root:
   `python code/tools/calls_table.py --runs runs/final --version v3 --models-file code/models.json --out results/logs/calls/calls_v3_main.csv`
   and `python results/figures/make_figures.py`.

The prepared workspaces (about 100 GB) and the full run directories are not in this repository; every result here
comes with the command that produced it. The frozen record of each case is in the version folders for v0, v2-v4
and the v5 development check: the answers of every model, the patches, the oracle's evaluation, and the tokens, time
and prompt sha256 of every call. The prompts themselves (`context.md`) are not included: they are rebuilt from the
benchmark, and their sha256 is in each record.

## Cost of the experiments (list prices)

| Run | Calls | Input / output tokens | Cost at list price |
|---|---|---|---|
| v0 MVP (NVIDIA API catalog, free) | 5 saved answers | 18,989 / 845 | 0 USD |
| v2 pilot (tournament and pilots) | 117 | 1,283,730 / 986,284 | 7.22 USD |
| v2 juror calibration | 25 | 349,054 / 572,872 (totals in `results/logs/calls/calls_v2_judge_calibration_totals.csv`) | 2.14 USD (2.64 with the Claude client's own report for the Claude calls) |
| v3 main sample (C0, C0g, C1) | 280 | 8,105,924 / 2,356,785 | 34.40 USD (Claude jurors at list price) |
| v4 confirmation (C0, 65 cases) | 65 | 848,338 / 442,252 | 6.12 USD |
| v5 development check (5 pilot cases, both arms) | 10 | 138,975 / 220,165 | 0.12 USD (Claude plan, list-price equivalent) |
| v5 (Haiku 5.5, with and without RAG, 95 cases) | running | | |

## Use of AI tools

Large language models are the object of study: the tokens, time and cost of every call are recorded in
`results/logs/calls/` and the consoles in `results/logs/console/`; the frozen answers are in the version folders
named above. The code, analyses and documents of this project were developed with the help of an AI assistant
(Claude Opus 5.5, Anthropic), and two diagrams of the final paper were drawn with ChatGPT (OpenAI); both uses are
declared in the papers. Every result comes from the runs and files in this repository.
