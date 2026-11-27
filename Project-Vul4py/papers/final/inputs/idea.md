# Idea (input for the final paper: v1-v5)

## Working title
False Assurance in LLM-Based Vulnerability Repair: Validated Environments, Multi-Model Verification,
Executable Evidence and Retrieval on Vul4Py

## Author and course
Camilo Vasquez, Computer Science, School of Mathematical and Computational Sciences, Yachay Tech University
(camilo.vasquez@yachaytech.edu.ec). Final project of the Artificial Intelligence course (2026), combined with the
Networks course (Redes), where the Vul4Py lab was assigned. The v0 pilot is reported in the proposal paper
(papers/v0_proposal).

## Problem
An LLM that repairs a vulnerability states whether its patch works. When the statement is wrong, a developer who
trusts it ships vulnerable code (false assurance). The v0 pilot (5 cases, one model) showed confident false claims
(FAR 3/4 at 95% confidence), but also that the benchmark environments and the model's input decide what can be
measured.

## Research questions
- RQ1 (measurement): with environments where the oracle is valid, how often are a strong LLM's repair claims false
  (FAR), next to how often its repairs are verified (VRR)?
- RQ2 (verification steps): does a mechanical gate, or a unanimous jury of models from other families, lower FAR
  without lowering VRR?
- RQ3 (evidence and localization): does executable evidence written by models (evigate) or a rule that the patch must
  cover every hinted line range lower FAR, and does the rule hold on cases not used to find it?
- RQ4 (cost): does retrieval of other projects' fixes and CWE guidance (RAG) raise the VRR of a model about 20 times
  cheaper, and what does each verified repair cost?

## Method in one paragraph per version
- v1, environments: repair how each of the 100 Vul4Py cases is installed and which tests run (never a test or its
  expectations), until every case passes the scan and the oracle control.
- v2, pipeline: a multi-model pipeline (analyst, repairer, mechanical gate, jury of three reviewers from other model
  families with debate, revision and abstention), a repairer tournament on 5 pilot cases, a GPT benchmark, and the
  calibration of candidate jurors on 28 candidates with known truth.
- v3, main sample: 30 cases (29 complete), three conditions with GPT-6.2 Sol as the repairer: C0 (repairer alone, its
  own claim), C0g (+ mechanical gate with feedback), C1 (+ analyst and unanimous jury of Claude and DeepSeek models).
- v4, evidence and confirmation: evigate (models write exploit tests from the report; a model-free verifier runs them
  in Docker) on the 29 C1 patches; the hint-coverage rule found post hoc on the main sample and confirmed on 65 new
  cases (63 complete) with C0.
- v5, RAG: Claude Haiku 5.5 alone and with RAG-R (Qdrant, local embeddings, fixes from other repositories, CWE
  mitigations) on the 95 cases of the main sample and the confirmation; C0 re-evaluated with the v5 harness.
  [PENDIENTE: results when the run ends]

## Practices
Every run's decisions (models, cases, conditions, primary test, analysis) were written and committed before the run
(prereg/decisiones_v1-v5.txt). Answers are frozen (SHA-256, read-only) before the oracle runs; the tests, the fixed
version and the reference fix never reach a model. Every model call is recorded with tokens, time and list-price cost.

## Contributions
1. Environment repairs that take Vul4Py from 18 to 100 cases with a valid oracle on a 2-vCPU machine.
2. FAR next to VRR for a single strong model, a mechanical gate and a cross-family unanimous jury on the same cases.
3. A localization rule confirmed on new cases (one-sided Fisher p = 0.024) and a negative result for executable
   evidence written by models.
4. A cost accounting per call and per verified repair, and a test of retrieval for a cheaper model.

## System diagram
The v5 flow (whiteboard "Flujo RAG de la v5"), redrawn in English with ChatGPT (GPT-6.2 Sol) from a prompt that lists
every component (TikZ version kept as an editable alternative); the planned v6 workflow drawn the same way.
