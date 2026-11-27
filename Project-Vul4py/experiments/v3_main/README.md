# v3: GPT benchmark and the main sample (C0, C0g, C1)

November 25-26, 2026. First, five GPT models repaired the 5 pilot cases through Codex
(`gpt_benchmark/`): GPT-6 Luna 0/5, GPT-6.1 Terra 1/5, GPT-6.2 Astra 3/5, GPT-6.2 Sol 3/5 (also with trimmed
context). Then three conditions ran on the main sample (30 cases, 29 complete; `prereg/main_ids.txt`),
with GPT-6.2 Sol as the repairer and the rules fixed in `prereg/decisiones_v3.txt`:

| Condition | VRR (95% CI) | FAR (95% CI) |
|---|---|---|
| C0: repairer alone | 16/29 = 55.2% (37.5-71.6%) | 12/28 = 42.9% (26.5-60.9%) |
| C0g: repairer + mechanical gate with feedback | 14/29 = 48.3% (31.4-65.6%) | 14/28 = 50.0% (32.6-67.4%) |
| C1: + unanimous jury of other families (primary rule) | 14/29 = 48.3% (31.4-65.6%) | 12/26 = 46.2% (28.8-64.5%) |

CVE-2024-27454 is excluded in the three conditions: its exploit kills the test process with a segfault.
See `results/figures/fig_main_vrr_far.pdf` and `results/figures/fig_cost_per_repair.pdf`.

| File | Content |
|---|---|
| `results.csv`, `summary.md`, `summary.json` | per-attempt rows and every acceptance rule (fa_metrics.py) |
| `experiment_c0.json`, `experiment_c0g.json`, `experiment_c1.json` | exact configuration, token use and cost of each condition |
| `gpt_benchmark/` | verdict per model and case of the GPT benchmark |
| `../../results/logs/calls/calls_v3_main.csv` | every model call (280) with tokens, time and list-price cost |
| `../../results/logs/console/v3_final_*.log` | consoles of the three conditions |
