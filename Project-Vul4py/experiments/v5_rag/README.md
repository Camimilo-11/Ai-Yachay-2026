# v5: RAG so a cheaper model repairs

November 26-27, 2026; fixed in `prereg/decisiones_v5.txt` before any of the 95 cases ran. The run had no interruptions:
C0 was re-evaluated from 22:23 to 03:44 UTC, Haiku alone ran until 05:58 and Haiku + RAG until 07:24.

- **Model:** Claude Haiku 5.5 (effort high) through the Claude plan; list price 0.10/0.50 USD per million
  input/output tokens, 20 times cheaper than GPT-6.2 Sol (2/10).
- **RAG-R** (`code/scripts/rag_repair.py`): Qdrant in local mode on the instance; FastEmbed
  `jinaai/jina-embeddings-v2-base-code`; 913 chunks from the upstream fixes of the 100 cases (code files only)
  with the MITRE CWE mitigations (CWE list 5.0). The query is the hinted code the model already sees; the
  search drops every chunk from the case's own repository; the top 3 cases go into a section of at most
  3000 tokens before the source files.
- **Harness:** tests run without secrets in their environment (`VUL4PY_CLEAN_ENV=1`) and flaky functional
  tests are rerun (`VUL4PY_FLAKE_RERUN=2`).
- **Arms (95 cases):** C0 re-evaluated with the new harness (no model calls), Haiku alone, Haiku + RAG.
- **Primary test:** VRR(Haiku + RAG) > VRR(Haiku), exact one-sided McNemar, alpha 0.05 (`code/scripts/confirm_v5.py`).

Development check on the 5 pilot cases (not evidence; `dev_gate/`): Haiku 2/5 verified with and without RAG,
4 positive claims in each arm, no refusals, RAG sections of 585-1269 tokens, no leakage flags; 0.059 USD (Haiku
alone) and 0.065 USD (Haiku + RAG) for the 5 cases at list price (`results/logs/calls/calls_v5_dev.csv`).

## Files

| File | Content |
|---|---|
| `kb_rag_r_v1/manifest.json` | the knowledge base as frozen in `decisiones_v5.txt` (sha256 `ff641878...`): parameters, versions and the sha256 of every part |
| `kb_rag_r_v1/chunks.jsonl` | the 913 chunks (hunks of the upstream fixes with 10 lines of context) |
| `kb_rag_r_v1/cwe_map.json`, `cwe_guides.json` | CWE ids of each case (OSV, GitHub advisories) and the MITRE mitigations used (CWE list 5.0) |
| `dev_gate/results.csv`, `summary.*`, `experiment_*.json` | the development check: both arms on the 5 pilot cases |
| `dev_gate/<arm>/<case>/` | the frozen record (`llm_response.json`), the answer (`*.md`), the patches (`*.diff`), the oracle's evaluation (`eval.json`) and, in M+RAG, the section the RAG inserted (`rag_section.md`); `dev_gate/_baseline/` holds the oracle control |

The embedding model files (`kb_rag_r_v1/models/`) and the Qdrant store are rebuilt by `code/scripts/rag_repair.py build`
and are not in the repository.

## Results of the main run (`confirm_v5.json`, run once when the three arms ended)

| Arm (95 cases) | Complete | VRR (95% CI) | FAR (95% CI) | Cost of the complete cases | Per verified repair |
|---|---|---|---|---|---|
| C0, GPT-6.2 Sol, frozen patches re-evaluated with the v5 harness | 94 | 38/94 = 40.4% (31.1-50.5%) | 54/91 = 59.3% (49.1-68.9%) | 8.88 USD (generation in v3/v4) | 0.234 USD |
| M, Claude Haiku 5.5 alone | 95 | 14/95 = 14.7% (9.0-23.2%) | 48/62 = 77.4% (65.6-86.0%) | 2.24 USD | 0.160 USD |
| M+RAG, Claude Haiku 5.5 with retrieval | 94 | 13/94 = 13.8% (8.3-22.2%) | 45/58 = 77.6% (65.3-86.4%) | 1.68 USD | 0.129 USD |

- **H1 not confirmed:** on the 94 cases complete in both Haiku arms, retrieval turned 5 unverified repairs into
  verified ones and 6 verified ones into unverified ones (one-sided exact McNemar p = 0.73; VRR 13.8% vs. 14.9%,
  difference -1.1 points, Newcombe 95% CI -8.7 to 6.5). The leakage audit flagged no case (largest similarity 0.095).
- **Against C0:** M+RAG verified 26.6 points fewer repairs (95% CI 16.8-36.0); C0 cost 1.81 times as much per
  verified repair (paired bootstrap 95% CI 0.99-2.85).
- **Coverage rule (v4) with another model family:** FAR 77.4% -> 52.6% in M and 77.6% -> 53.3% in M+RAG
  (one-sided Fisher p = 0.003 and 0.015); in C0 with the v5 harness, 59.3% -> 38.9% (p = 0.001).
- **Harness:** both cases lost in v4 (tornado, smolagents) are complete now, and C0 verified one of them; one C0
  verdict changed (CVE-2024-35195: one of the 318 exploit tests that had passed in v4 failed).
- **Rule fixed before v5:** H1 was not confirmed, so the n8n workflow (v6) waits; the retrieval step is tuned on
  the 5 development cases first, and any new measurement on the 95 cases is exploratory.

| File | Content |
|---|---|
| `results.csv`, `summary.md`, `summary.json` | one row per arm and case (285) and every acceptance rule (`code/scripts/fa_metrics.py`) |
| `confirm_v5.json` | the analysis fixed in `decisiones_v5.txt` (`code/scripts/confirm_v5.py`): H1, cost ratio, Newcombe interval, coverage rule, harness and retrieval audits |
| `experiment_c0.json`, `experiment_c0m.json`, `experiment_c0mr.json` | configuration, start and end times and token use of each arm |
| `main/<arm>/<case>/` | the frozen record (`llm_response.json`, with the retrieval record in M+RAG), the answer (`*.md`), the patches (`*.diff`), the oracle's evaluation (`eval.json`) and the RAG section (`rag_section.md`); `main/_baseline/` holds the oracle control; the C0 records are the frozen ones of v3 and v4 |
| `kb_rag_r_v1/build.log` | the build of the vector store (913 chunks, vectors sha256) |
| `../../results/logs/calls/calls_v5.csv` | the 190 Haiku calls: 4,604,832 input and 4,385,390 output tokens, 4.15 USD at list price (5.33 USD in the client's report) |
| `../../results/logs/console/v5_main.log` | console output of the run |
