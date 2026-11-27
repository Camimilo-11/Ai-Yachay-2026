# v5.1: exploratory follow-up of v5 (Claude Haiku 5.5)

November 27, 2026; fixed in `prereg/decisiones_v5_1.txt` before any v5.1 case ran. It is exploratory: the
changes were chosen after seeing v5 on these same 95 cases, and Vul4Py has no unused cases left, so a positive
result would be a lead to test on new cases, not a confirmation.

Where the changes come from (v5 records in `../v5_rag/`): 49 of Haiku's 190 answers had no patch, all calls ended
normally, and in about 30 of them the model said that code it needed was not shown; only 28 of the 285 retrieved
examples shared a CWE with their case; and 38 of the 48 false claims of M did not touch every hinted line range.

| Arm | Agent | What it adds to v5's M (preset c0, `claudecode:claude-haiku-5-5`, hint lines) |
|---|---|---|
| M'+RAG' | `c0mr51` (runs first) | (1) related project code, (2) coverage check, (3) retrieval keyed by the case's CWE |
| M' | `c0m51` | (1) and (2) |

1. **Related project code** (`code/scripts/v51_context.py`, `--project-context 4000`): after the source files,
   excerpts of other files of the same project found by name: definitions of the names the hinted lines use and
   the functions that call the hinted functions; never tests, docs, examples or the fixed version.
2. **Coverage check** (`--coverage-check 1`): when the first patch does not touch every hinted range (the v4
   coverage definition), the untouched ranges go back to the same model once; an unparseable revision keeps the
   previous answer. `patch_initial.diff` keeps the patch from before the check.
3. **Retrieval keyed by the case's CWE** (`code/scripts/rag_cwe.py`, `--rag-mode cwe`): fixes of other
   repositories that share the case's CWE (at most 2, same base, embedder and query as v5) and MITRE's
   mitigations for the case's own CWE; 61 of the 95 cases have such examples, 32 get the guide only, 2 no section.

Without the new options, `code/scripts/multiagent.py` gives byte for byte the same prompts and records as in v5
(checked locally with 3 real cases and a simulated model).

Analysis (`code/scripts/confirm_v51.py`, run once when both arms end): VRR and FAR of each arm with Wilson
intervals; VRR(M'+RAG') - VRR(M') with Newcombe's paired interval and the two-sided exact McNemar test, as an
estimate; each arm against its v5 counterpart and against C0; the effect of the coverage check inside each arm;
the v4 coverage rule on the final patches; cost per verified repair counting every call; leakage and retrieval
audits. The development check on the 5 pilot cases (`code/scripts/v51_devcheck.py`) only checks that the arms
run as designed.

Status: running on the instance; the results and the case records are added here when the run ends.
