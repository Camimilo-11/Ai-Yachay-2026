# v5: RAG so a cheaper model repairs

November 26, 2026 onwards; fixed in `prereg/decisiones_v5.txt` before any of the 95 cases ran.

- **Model:** Claude Haiku 5.5 (effort high) through the Claude plan; list price 0.10/0.50 USD per million
  input/output tokens, 20 times cheaper than GPT-6.2 Sol (2/10).
- **RAG-R** (`src/rag_repair.py`): Qdrant in local mode on the instance; FastEmbed
  `jinaai/jina-embeddings-v2-base-code`; 913 chunks from the upstream fixes of the 100 cases (code files only)
  with the MITRE CWE mitigations (CWE list 5.0). The query is the hinted code the model already sees; the
  search drops every chunk from the case's own repository; the top 3 cases go into a section of at most
  3000 tokens before the source files.
- **Harness:** tests run without secrets in their environment (`VUL4PY_CLEAN_ENV=1`) and flaky functional
  tests are rerun (`VUL4PY_FLAKE_RERUN=2`).
- **Arms (95 cases):** C0 re-evaluated with the new harness (no model calls), Haiku alone, Haiku + RAG.
- **Primary test:** VRR(Haiku + RAG) > VRR(Haiku), exact one-sided McNemar, alpha 0.05 (`src/confirm_v5.py`).

Development check on the 5 pilot cases (not evidence; `dev_gate/`): Haiku 2/5 verified with and without RAG,
4 positive claims in each arm, no refusals, RAG sections of 585-1269 tokens, no leakage flags; 0.059 USD (Haiku
alone) and 0.065 USD (Haiku + RAG) for the 5 cases at list price (`logs/calls/calls_v5_dev.csv`).

## Files

| File | Content |
|---|---|
| `kb_rag_r_v1/manifest.json` | the knowledge base as frozen in `decisiones_v5.txt` (sha256 `ff641878...`): parameters, versions and the sha256 of every part |
| `kb_rag_r_v1/chunks.jsonl` | the 913 chunks (hunks of the upstream fixes with 10 lines of context) |
| `kb_rag_r_v1/cwe_map.json`, `cwe_guides.json` | CWE ids of each case (OSV, GitHub advisories) and the MITRE mitigations used (CWE list 5.0) |
| `dev_gate/results.csv`, `summary.*`, `experiment_*.json` | the development check: both arms on the 5 pilot cases |
| `dev_gate/<arm>/<case>/llm_response.json`, `rag_section.md` | frozen record of each answer and the section the RAG inserted |

The embedding model files (`kb_rag_r_v1/models/`) and the Qdrant store are rebuilt by `src/rag_repair.py build`
and are not in the repository.

[PENDIENTE: results when the run ends: results.csv, confirm_v5.json, per-call table, console.]
