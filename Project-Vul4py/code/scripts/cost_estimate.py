#!/usr/bin/env python3
"""cost_estimate.py -- planning estimate of the API cost of the experiment, before the pilot.

Counts the calls multiagent.py makes per case with its defaults (2 gate retries, cross-examination,
1 debate round, 1 revision) under three scenarios, sizes every prompt with the case's own code as
multiagent.py builds it (from the workspaces when they exist, compiled sources and excerpts past the
budget included; otherwise the estimate in sandbox_validation/dissect.json) and prices the tokens with
models.json (OpenAI Standard list prices). Reasoning tokens are billed as output and are the main
unknown, so the scenarios bracket them. Prompt caching is ignored (it only lowers the cost); --flex
halves the price of the models marked "flex": true in models.json. The pilot replaces all of this
with the measured cost: multiagent.py prints tokens and cost after every run.

    python scripts/cost_estimate.py --models-file models.json --analyst openai:gpt-6-luna \\
        --repairers openai:gpt-6.2-sol,openai:gpt-5.4-mini \\
        --jurors openai:gpt-6.1-sol,openai:gpt-6.1-terra,openai:gpt-6-luna \\
        --calibration-extra openai:gpt-6.2-astra --main 30 --main all
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

# Tokens of each prompt part and visible answer: assumptions, above what the simulated runs' prompts
# measured (real answers are longer than the simulated ones)
SYS, HINT, ANALYSIS, CAND, FEEDBACK, SHARED_REVIEW, CRITIQUES = 1500, 300, 2500, 1500, 800, 2000, 3000
ANS = {"analyst": 3000, "repairer": 2500, "reviewer": 2000}

# Per scenario: expected calls beyond the minimum, and reasoning tokens per call by reasoning effort
SCENARIOS = {
    "low": {"retries": 0, "cross_revise": 0, "jury_rounds": 1, "revision": 0,
            "reasoning": {"max": 4000, "xhigh": 4000, "high": 3000, "medium": 1500, "low": 800}},
    "mid": {"retries": 1, "cross_revise": 0.5, "jury_rounds": 1.9, "revision": 0.4,
            "reasoning": {"max": 12000, "xhigh": 10000, "high": 8000, "medium": 4000, "low": 2000}},
    "high": {"retries": 2, "cross_revise": 3, "jury_rounds": 4, "revision": 3,
             "reasoning": {"max": 30000, "xhigh": 25000, "high": 20000, "medium": 10000, "low": 5000}},
}


class Model:
    def __init__(self, spec: str, cfg: dict, flex: bool):
        o = cfg.get(spec, {})
        self.spec, self.context = spec, int(o.get("context", 1_050_000))
        self.effort = o.get("reasoning_effort", "medium")
        half = 0.5 if flex and o.get("flex") else 1.0
        self.pin, self.pout = o["price_in"] * half / 1e6, o["price_out"] * half / 1e6


def call(m: Model, tokens_in: float, role: str, sc: dict) -> float:
    return tokens_in * m.pin + (ANS[role] + sc["reasoning"].get(m.effort, 0)) * m.pout


def c1_case(c: int, a: Model, reps, jurors, sc: dict) -> float:
    base = SYS + HINT + ANALYSIS + c
    cost = call(a, SYS + HINT + c, "analyst", sc)
    for r in reps:
        cost += call(r, base, "repairer", sc)
        for k in range(int(sc["retries"])):
            cost += call(r, base + (k + 1) * (ANS["repairer"] + FEEDBACK), "repairer", sc)
        if len(reps) >= 2:
            cost += call(r, base + ANS["repairer"] + CAND * len(reps), "repairer", sc)
            cost += sc["cross_revise"] * call(r, base + 2 * ANS["repairer"] + CAND * len(reps), "repairer", sc)
    jury_in = SYS + HINT + ANALYSIS + c + CAND * len(reps)
    rounds = sc["jury_rounds"]
    debate_share = max(0.0, rounds - 1) / rounds if rounds else 0.0   # rounds after the first carry the debate
    for j in jurors:
        cost += rounds * call(j, jury_in + debate_share * SHARED_REVIEW * (len(jurors) - 1), "reviewer", sc)
    cost += sc["revision"] * call(reps[0], base + ANS["repairer"] + CRITIQUES, "repairer", sc)
    return cost


def c0_case(c: int, r: Model, sc: dict) -> float:
    return call(r, SYS + HINT + c, "repairer", sc)


def code_tokens(a, budget: int, valid) -> tuple:
    """Tokens of code each valid case shows the models, as multiagent.py builds it."""
    est = {r["vuln_id"]: r["context_tokens_est"] for r in json.loads(Path(a.contexts).read_text())}
    try:
        import multiagent as M
        import protocols as P
        from run_agent import load_meta
    except Exception:  # noqa: BLE001  (outside the Vul4Py repository: estimates only)
        M = None
    out, src = [], Counter()
    for v in sorted(valid):
        d = Path(a.workspaces) / v
        if M is not None and (d / "meta.json").exists():
            meta = load_meta(d)
            rels = M.context_files(d, meta, True)
            files, excerpts, _ = M.fit_context(d, rels, budget, M.hint_ranges_of(P.localization_hint(d, meta, rels)))
            out.append(len(M.render(files, excerpts)) / 3.6)
            src["workspaces"] += 1
        else:
            out.append(min(est[v], budget))
            src["dissect.json"] += 1
    return out, src


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models-file", default=str(ROOT / "models.json"))
    ap.add_argument("--workspaces", default=str(ROOT / "workspaces"))
    ap.add_argument("--contexts", default=str(ROOT / "sandbox_validation" / "dissect.json"),
                    help="Fallback context sizes for cases without a workspace")
    ap.add_argument("--status", default=str(ROOT / "sandbox_validation" / "case_status.csv"),
                    help="Cases whose final status is 'valid' make up the population")
    ap.add_argument("--analyst", required=True)
    ap.add_argument("--repairers", required=True)
    ap.add_argument("--jurors", required=True)
    ap.add_argument("--calibration-extra", default="", help="Reviewer candidates calibrated besides the jurors")
    ap.add_argument("--pilot", type=int, default=5)
    ap.add_argument("--main", action="append", default=[], help="Main-sample size or 'all' (repeatable)")
    ap.add_argument("--code-share", type=float, default=0.40)
    ap.add_argument("--flex", action="store_true", help="Half price on the models marked flex in models.json")
    a = ap.parse_args()

    cfg = json.loads(Path(a.models_file).read_text())
    mk = lambda s: Model(s.strip(), cfg, a.flex)  # noqa: E731
    an = mk(a.analyst)
    reps = [mk(s) for s in a.repairers.split(",") if s.strip()]
    jur = [mk(s) for s in a.jurors.split(",") if s.strip()]
    calib = jur + [mk(s) for s in a.calibration_extra.split(",") if s.strip()]
    budget = int(min(m.context for m in [an] + reps + jur) * a.code_share) - 4000
    valid = {r["vuln_id"] for r in csv.DictReader(open(a.status)) if r["final"] == "valid"}
    ctx, src = code_tokens(a, budget, valid)
    print(f"{len(ctx)} valid cases (code sized from {dict(src)}); code budget {budget} tokens; median "
          f"{statistics.median(ctx):.0f}, mean {statistics.mean(ctx):.0f}, largest {max(ctx):.0f}; "
          f"prices {'Flex where offered' if a.flex else 'Standard'}")
    sizes = a.main or ["30", "all"]
    print(f"{'scenario':8} {'C1/case':>8} {'C0/case':>8} {'pilot':>7} " + " ".join(f"{'main ' + s:>10}" for s in sizes)
          + " " + " ".join(f"{'total ' + s:>10}" for s in sizes))
    for name, sc in SCENARIOS.items():
        c1 = statistics.mean(c1_case(c, an, reps, jur, sc) for c in ctx)
        c0 = statistics.mean(c0_case(c, reps[0], sc) for c in ctx)
        tour = statistics.mean(sum(call(r, SYS + HINT + c, "repairer", sc) * (1 + sc["retries"]) for r in reps)
                               for c in ctx)
        cal = statistics.mean(sum(call(j, SYS + HINT + c + 4 * CAND, "reviewer", sc) for j in calib) for c in ctx)
        pilot = a.pilot * (c1 + c0 + tour + cal)
        mains = [(len(ctx) - a.pilot if s == "all" else int(s)) * (c1 + c0) for s in sizes]
        print(f"{name:8} {c1:8.2f} {c0:8.2f} {pilot:7.2f} " + " ".join(f"{x:10.0f}" for x in mains)
              + " " + " ".join(f"{pilot + x:10.0f}" for x in mains))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
