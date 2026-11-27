# Experimental log (input for the final paper: v1-v5). Every number comes from the version folders in experiments/, results/logs/ and prereg/.

## Shared setup
- Benchmark: Vul4Py (Bui et al., 2026, arXiv:2608.00692), commit f80f861; 100 vulnerabilities (92 CVE, 8 GHSA) in 60 projects.
- Oracle: verified repair V = A·F·S (patch applies, functional tests pass, exploit tests pass); skipped tests never count;
  a segfaulting exploit (rc >= 128, no junit) counts as S = 0. FA = D·(1−V) for a claim D.
- Metrics: VRR = verified / complete attempts; FAR = unverified positive claims / positive claims; 95% Wilson intervals;
  exact McNemar for paired claims; one-sided Fisher for the v4 rule; Newcombe paired CI and bootstrap ratios in v5.
- Instance: AWS EC2, 2 vCPU, 7 GiB, 100 GB disk, Ubuntu 24.04. Answers frozen (SHA-256, read-only) before evaluation; tests,
  fixed version and reference fix never shown to a model. Each run's decisions committed before it ran (prereg/decisiones_v1-v5).
- Context given to the models: the files the upstream fix changed (library first) plus the line-range hint, as in the
  Vul4Py paper's direct-LLM protocol.

## v1: environments (to Nov 24)
- Public release: 18/100 cases pass the first scan in a sandbox the size of the instance.
- Repairs (never a test or its expectations; each with its reason in code/dataset/meta_overrides/<case>.json `_note`):
  test dependencies [doctor:deps]; era-matched Python and dependencies (fix date + 30 days) [doctor:era]; per-test timeouts
  [timeouts]; Vul4Py's auto_skip with two fixes [auto_skip]; baseline tests asserting the vulnerable behaviour deselected
  [oracle_repair]; functional tests failing only on the vulnerable version deselected (<= 10 per case) [vuln_only];
  case-by-case fixes [manual]; restore of install products, rebuild after C/Rust patches, fetch by SHA, open-files limit,
  torch CPU wheels (harness).
- 91 meta_overrides and 14 test_overrides.
- Scan on the instance per build round: R0 86, R1 98, R2-R4 99, R5 100 cases OK. Oracle control: 100/100 (functional tests
  pass unpatched, exploit tests fail unpatched, upstream fix passes both). results/figures/fig_environment.

## v2: pipeline, tournament, juror calibration (Nov 25)
- Pipeline (C1): analyst (structure and data flow, quotes verified) -> repairer(s) -> mechanical gate (applies like Vul4Py,
  only shown files, no tests, compiles, not a no-op, not oversized; failures returned verbatim, 2 retries) -> cross-examination
  (with 2+ repairers) -> merge of equivalent patches -> jury of 3 reviewers (never a repairer; listwise, order shuffled per juror)
  -> unanimous: claim; split: debate round, re-vote; still split: revision by the leader's author -> gate -> jury; no unanimity:
  ABSTAIN -> freeze -> oracle. C0 = repairer alone (its own claim); C0g = C0 + gate.
- Pilot on 5 cases (pilot_ids): repairer GPT-6.2 Sol VRR 3/5, FAR 2/5; GPT-5.4 mini VRR 1/5, FAR 4/5; C1 with a GPT jury VRR 3/5,
  FAR 2/5 (unanimous jury 1/4); C1 v2 with a jury of other families VRR 3/5, FAR 2/5.
- The first main run stopped when the OpenAI key ran out of credit (Nov 25, 11:41 UTC); archived and excluded.
- Juror calibration v2 (28 candidates with known truth per model: 13 correct, 15 wrong): AUROC of stated confidence
  Claude Opus 5.5 0.913, Sonnet 5.5 0.905, Haiku 5.5 0.900, DeepSeek V4 Pro 0.838, DeepSeek Flash 0.744; specificity 0.67,
  0.73, 0.73, 0.93, 0.87; Brier 0.126, 0.145, 0.155, 0.150, 0.214. Chosen jury: Opus 5.5, Sonnet 5.5 (Claude plan) and
  DeepSeek V4 Pro (three best by AUROC with one per provider at least). Calibration cost: 25 calls, 2.14 USD at list price
  (2.64 USD with the Claude client's own report, which counts input tokens at twice the input price).
- Pilot calls: 117, 1,283,730 input / 986,284 output tokens, 7.22 USD at list price.

## v3: GPT benchmark and main sample (Nov 25-26)
- GPT benchmark (5 pilot cases, through Codex): GPT-6 Luna 0/5, GPT-6.1 Terra 1/5, GPT-6.2 Astra 3/5, GPT-6.2 Sol 3/5.
- Main sample: 30 cases (main_ids), 29 complete (CVE-2024-27454 excluded: its exploit kills the test process with a segfault).
- Repairer GPT-6.2 Sol (reasoning effort high); analyst GPT-6 Luna; jury Opus 5.5 + Sonnet 5.5 (Claude Code, plan) + DeepSeek V4 Pro.

| Condition | VRR (95% CI) | FAR (95% CI) |
|---|---|---|
| C0 repairer alone | 16/29 = 55.2% (37.5-71.6) | 12/28 = 42.9% (26.5-60.9) |
| C0g + gate | 14/29 = 48.3% (31.4-65.6) | 14/28 = 50.0% (32.6-67.4) |
| C1 + unanimous jury (primary) | 14/29 = 48.3% (31.4-65.6) | 12/26 = 46.2% (28.8-64.5) |

- C1 other rules (descriptive): repairer's claim 13/27 = 48.1%; consensus 12/26; majority 13/27; gate (majority and mean
  confidence >= 0.8) 7/19 = 36.8% (19.1-59.0), McNemar vs repairer p = 0.031, safe yield 41.4% vs 48.3%; independent vote
  (round 0) 9/21 = 42.9%. Jury caught 1 false claim; McNemar unanimous vs repairer p = 1.000.
- Protocols: C1 abstained in 10.3% of 29; resolved by independent vote / debate / revision 21 / 5 / 0; gate rejected 2 patch
  versions in C1 (2 rescued) and 3 in C0g (2 rescued); quoted code that does not exist: 1 of 1535 citations in C1 (0.1%),
  2 of 322 in C0g, 0 of 300 in C0; refusals 0. Oracle-best VRR equal to the selected one in every condition.
- Main-sample calls: 280, 8,105,924 input / 2,356,785 output tokens, 34.40 USD (C0 3.33, C0g 3.68; C1: Opus 10.83,
  DeepSeek 5.96, GPT-6.2 Sol 5.56, Sonnet 4.87, GPT-6 Luna 0.18; Claude at API-equivalent price).
- Median latency per call: Sonnet 12.9 s, Opus 25.4 s, GPT-6 Luna 56.2 s, GPT-6.2 Sol 90.9-113.6 s, DeepSeek V4 Pro 187.7 s.

## v4: executable evidence and the coverage rule (Nov 26)
- evigate step A on the 29 C1 patches (blind attacker writes exploit tests from the report; a model-free verifier runs them in
  Docker; they must fail on the original and pass with the patch, 2 of 2; no functional regression; white-box attacker looks
  for a bypass): statuses verified 11, bypass 4, not blocked 4, no functional evidence 4, not reproduced 3, environment failed 2,
  regression 1. Claiming only with that evidence: 11 claims, 6 false, FAR 54.5% (28.0-78.7); versus the unanimous jury it removed
  6 false claims and lost 9 correct ones (McNemar on false assurances p = 0.031). It did not lower FAR.
- Post hoc finding on the main sample: claim only if the patch touches 100% of the hinted line ranges (+-3 lines):
  C0 12/28 -> 3/12; C0g 14/28 -> 5/13; C1 13/27 -> 2/11. Pass rate correct vs wrong patches: C0 9/16 vs 3/12 (one-sided Fisher
  p = 0.102), C0g 8/14 vs 5/14 (p = 0.225), C1 9/14 vs 2/13 (p = 0.013).
- Confirmation (decisiones_v4, fixed before the run): C0 on the 65 valid cases never used (confirm65_ids), 63 complete
  (tornado CVE-2024-52804: flaky functional test; smolagents CVE-2025-5120: tests found an API key in the environment).
  VRR 22/63 = 34.9% (24.3-47.2); FAR repairer 40/61 = 65.6% (53.0-76.3); FAR with the rule 11/23 = 47.8% (29.2-67.0);
  passes 12/21 correct vs 11/40 wrong, one-sided Fisher p = 0.0237 -> confirmed; pass-rate difference 0.30 (95% CI 0.04-0.51);
  29 false assurances removed, 9 correct claims lost; safe yield 33.3% -> 19.0%. coverage75: 13/27 = 48.1%.
- Confirmation calls: 65, 848,338 input / 442,252 output tokens, 6.12 USD.
- Caveat: in Vul4Py the hint is the footprint of the official fix; outside the dataset the rule needs a report with locations.

## v5: RAG for a cheaper model (Nov 26-27)
- Harness options (off by default, so v1-v4 reproduce): VUL4PY_CLEAN_ENV=1 (no secret-named variables in the test shell),
  VUL4PY_FLAKE_RERUN=2 (rerun when 1-3 functional tests fail; failed only if failed every time; exploit tests never rerun).
- Arms on 95 cases (main + confirmation): C0 frozen patches re-evaluated with the v5 harness (no model calls); M = Claude Haiku 5.5
  (effort high, Claude plan) with the C0 prompt; M+RAG = the same plus a references section.
- RAG-R v1: Qdrant local (cosine), FastEmbed jina-embeddings-v2-base-code (768-d) on CPU; corpus = one chunk per hunk of the 100
  upstream fixes (code files only, 10 lines of context): 913 chunks; CWE ids from OSV / GitHub advisories (98/100 with CWE) and
  MITRE CWE list 5.0 mitigations; query = the hinted ranges +-20 lines; filter repo != case repo; top 40 -> best chunk per source
  case -> top 3; at most 3000 tokens; leakage audit (difflib >= 0.5 flags the case). KB manifest sha256 ff641878...
- Primary: H1 VRR(M+RAG) > VRR(M), exact one-sided McNemar, alpha 0.05. Secondary: cost per verified repair vs C0 (paired
  bootstrap, 10,000 resamples, seed 2026), FAR with Wilson, coverage rule, harness and RAG audits. Rule v6: n8n only if H1 holds.
- Development gate (5 pilot cases, not analysed): M 2/5 verified, FAR 2/4; M+RAG 2/5, FAR 2/4; no refusals; RAG sections
  585-1269 tokens; no leakage flags; 10 calls, 138,975 / 220,165 tokens, 0.12 USD (M 0.059, M+RAG 0.065).
- Prices (code/models.json, USD per million input/output tokens): Haiku 5.5 0.10/0.50; GPT-6.2 Sol 2/10.
- Main run (experiments/v5_rag/results.csv, confirm_v5.json; no interruptions; C0 22:23-03:44 UTC, M -05:58, M+RAG -07:24):
  C0 94/95 complete, VRR 38/94 = 40.4% (31.1-50.5), FAR 54/91 = 59.3% (49.1-68.9), cost of the complete cases 8.88 USD,
  0.234 USD per verified repair; M 95/95, VRR 14/95 = 14.7% (9.0-23.2), FAR 48/62 = 77.4% (65.6-86.0), 2.24 USD, 0.160;
  M+RAG 94/95, VRR 13/94 = 13.8% (8.3-22.2), FAR 45/58 = 77.6% (65.3-86.4), 1.68 USD, 0.129. orjson crashed again (C0, M+RAG).
- H1 not confirmed: 94 paired cases, both 8, only M+RAG 5, only M 6, neither 75; one-sided exact McNemar p = 0.726;
  VRR 13.8% vs 14.9%, difference -1.1 points (Newcombe paired 95% CI -8.7 to 6.5). Leakage audit: no case flagged (max 0.095).
- M+RAG vs C0: -26.6 points (95% CI -36.0 to -16.8; only C0 26, only M+RAG 1); CPV ratio C0/M+RAG 1.81 (bootstrap 0.99-2.85).
- Coverage rule: C0 22/37 correct and 14/54 wrong kept, FAR 38.9% (24.8-55.1), p = 0.0013; M 9/14 and 10/48, FAR 52.6%
  (31.7-72.7), p = 0.0035; M+RAG 7/13 and 8/45, FAR 53.3% (30.1-75.2), p = 0.015 (one-sided Fisher).
- Harness: tornado CVE-2024-52804 and smolagents CVE-2025-5120 complete (C0 verified the first); one C0 verdict changed,
  CVE-2024-35195 (exploit 318/0/0/2 -> 317/1/0/2). Haiku: 23 and 26 empty patches; false claims failing only the exploit
  tests 34/48 and 33/45. Calls: 190, 4,604,832 / 4,385,390 tokens, 4.68 h, 4.15 USD (client report 5.33); every call
  counted, 0.160 (M) and 0.147 (M+RAG) USD per verified repair against 0.249 for GPT-6.2 Sol on the same 95 cases.

## Cost summary (list prices)
| Run | Calls | Input / output tokens | Cost |
|---|---|---|---|
| v0 pilot (NVIDIA, free) | 5 | 18,989 / 845 | 0 |
| v2 pilot and tournament | 117 | 1,283,730 / 986,284 | 7.22 |
| v2 juror calibration | 25 | 349,054 / 572,872 | 2.14 (2.64 with the client's report) |
| v3 main sample | 280 | 8,105,924 / 2,356,785 | 34.40 |
| v4 confirmation | 65 | 848,338 / 442,252 | 6.12 |
| v5 development | 10 | 138,975 / 220,165 | 0.12 |
| v5 main run | 190 | 4,604,832 / 4,385,390 | 4.15 (5.33 with the client's report) |
