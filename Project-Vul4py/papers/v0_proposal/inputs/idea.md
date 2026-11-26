# Idea (input for the v0 paper: milestone 1, research proposal)

## Working title
Measuring False Assurance in LLM-Based Automated Vulnerability Repair: Research Proposal and a Five-Case
Pilot on Vul4Py [PENDIENTE: final title]

## Authors and course
Camilo Vasquez, Yachay Tech [PENDIENTE: school, email]. Artificial Intelligence course, 2026
[PENDIENTE: instructor]. The project is combined, with permission, with [PENDIENTE: other course and its
instructor], where the Vul4Py lab was assigned; the AI research question is the one below.

## Problem and relevance
LLM-based repair tools return a patch together with an explicit or implicit claim that it fixes the
vulnerability. When the claim is wrong, a developer who trusts it ships vulnerable code believing it is
fixed: this is false assurance. Patch correctness can be checked by executing tests (an oracle), but most
users only see the claim. The gap matters because security patches are often accepted without a
reproducible exploit test.

## Research question
RQ: When an LLM repairs a real Python vulnerability and claims the repair works, how often is the claim
false under an executable oracle (FAR), and how does it relate to how often the repair is actually verified
(VRR)? Planned follow-up: does splitting the task among three models lower FAR without lowering VRR?

## Objective
Build a reproducible measurement of VRR and FAR on Vul4Py with an executable oracle (patch applies,
functional tests pass, exploit tests pass), run a first model on a small subset, and plan the full study.

## Type of research
Applied research [PENDIENTE: confirm]: LLM repair evaluated on a public benchmark against baselines.

## Method (v0)
Input: the vulnerable versions of the files that the reference fix changes (Vul4Py's `new_code_files`;
file-level localization, at most 4 files and 60 kB), with one fixed system prompt (runner default
temperature 0 [PENDIENTE: confirm it was not overridden]). Output: a unified diff, a binary claim
("the patch removes the vulnerability and preserves functionality") and a confidence. The answer is saved
before any test runs. Evaluation: Vul4Py's oracle. Metrics: VRR = verified repairs / complete attempts;
FAR = unverified positive claims / positive claims; 95% Wilson intervals.

## Baselines
- The lab's reference run: 23 attempts, 1 verified (VRR 4.3%), 22 of 23 positive claims unverified
  (FAR 95.7%). [PENDIENTE: how to cite it: course material of the other course]
- The v0 run itself, as the baseline of the planned pipeline.

## Expected contribution
1. A measurement protocol for false assurance in LLM vulnerability repair with an executable oracle.
2. A working environment for the benchmark (planned: repair the installation of the 100 cases).
3. Evidence on whether a pipeline of three models with separate roles lowers FAR without lowering VRR.

## Planned methodology (after v0)
Build and check the environments of the 100 cases so the oracle is valid on each; replace the single model with
a pipeline of three models from NVIDIA's API catalog (code-structure analysis -> vulnerability and fix -> evaluator,
with the least reliable model on the lightest task), compared with the single model on the same cases and judged
by the same oracle; freeze every claim before the oracle runs and record every call with tokens, time and cost.

## Schedule and resources
Pilot (v0): Oct 12-14 (done). Then environment validation and the three-model pipeline, before the final report
on Dec 3. Resources: the NVIDIA API catalog (free); environments built on the author's computer [PENDIENTE: confirm].

## System diagram (drawn by the author; the rubric forbids AI-generated diagrams)
See `system_diagram_spec.md`.
