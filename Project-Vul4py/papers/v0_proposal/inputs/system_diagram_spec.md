# System diagram of the proposal: components and arrows (Figure 1)

Components and arrows of Figure 1 of the v0 paper, drawn as TikZ code in `paper/figures/fig_system_overview.tex`
(written with the AI assistant at the author's request; the rubric's rule on author-designed diagrams applies to
the final paper). Left to right, four zones as the rubric asks:
Input -> Processing / AI method -> Evaluation -> Output.

## 1. Input
- Box "Vul4Py case": the vulnerable versions of the files that the reference fix changes (file-level
  localization; at most 4 files and 60 kB).
- Small note under it: "100 real Python vulnerabilities; v0 uses 5".

## 2. Processing / AI method
- Box "Prompt builder": one template; asks for diagnosis, unified diff, claim (yes/no) and confidence.
- Box "LLM repairer": v0 = poolside/laguna-xs-2.1 via NVIDIA API (planned: a pipeline of three models).
- Box "Frozen answer": claim + confidence + patch, saved before any test runs (draw a lock or a dashed border).

## 3. Evaluation (Vul4Py oracle)
- Three boxes in a row, each with a "no" exit: "Patch applies?" -> "Functional tests pass?" -> "Exploit tests pass?".
- The "yes" exit of the last one goes to "Verified repair (V = 1)"; every "no" goes to "Not verified (V = 0)".

## 4. Output
- Box "Metrics": VRR = verified / attempts; FAR = unverified positive claims / positive claims; 95% Wilson intervals.
- Box "Results table + logs": per case verdicts, tokens, time, cost.

## Arrows
Vul4Py case -> Prompt builder -> LLM repairer -> Frozen answer -> Patch applies? -> ... -> Metrics -> Results.
Also a thin arrow from "Frozen answer" (the claim) straight to "Metrics" (the claim is compared with V).

## Optional dashed box (planned work)
Around the AI method: "Planned: environment validation (100 cases) and three models: analysis -> repair -> evaluator".
