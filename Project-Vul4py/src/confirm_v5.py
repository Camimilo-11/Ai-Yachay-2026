#!/usr/bin/env python3
"""Pre-registered analysis of decisiones_v5: does RAG-R raise the verified-repair rate of a cheap model?

Arms (agents in one runs directory, same cases, same oracle session):
  c0    gpt-6.2-sol, the frozen C0 patches re-evaluated with the v5 harness (no model calls)
  c0m   the cheap model alone, with C0's prompt
  c0mr  the cheap model with the RAG-R section (multiagent.py --rag)

Primary (H1): VRR(c0mr) > VRR(c0m) on the cases complete in both; exact one-sided McNemar on the
discordant pairs, alpha 0.05; confirmed when p < alpha AND VRR(c0mr) > VRR(c0m).
Secondary, estimates only: cost per verified repair (CPV) of c0mr against c0 with a paired bootstrap
interval; the VRR difference c0mr - c0 (Newcombe's interval for paired data); FAR and safe yield of each
arm; the v4 coverage rule in c0m and c0mr; which C0 verdicts the v5 harness changed; the leakage audit.

Input: the results.csv of scripts/fa_metrics.py for the runs directory (columns agent, vuln_id, status, V,
D_repairer, hint_coverage, D_coverage, repairer_model, input_tokens, output_tokens), models.json for list
prices, and the frozen llm_response.json of c0mr for the RAG records.  Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from confirm_v4 import fisher_greater, mcnemar_exact, wilson  # noqa: E402  (same helpers as v4)

ALPHA = 0.05
ARMS = ("c0", "c0m", "c0mr")
BOOT = 10_000
SEED = 2026
LEAK_FLAG = 0.5
# Haiku 5.5 is billed per request by prompt size (models.json _note): up to 100k prompt tokens 0.10/0.50,
# above 0.50/2.50 USD per million. Every v5 attempt is one request (preset c0), so a row is a request.
TIERS = {"claude-haiku-5-5": (100_000, 0.50, 2.50)}


def _bit(v) -> Optional[int]:
    v = (v or "").strip()
    return int(float(v)) if v not in ("", "None", "nan") else None


def _int(v) -> int:
    v = (v or "").strip()
    return int(float(v)) if v not in ("", "None", "nan") else 0


def pct(x) -> str:
    return "–" if x is None else f"{100 * x:.1f}%"


def ci(lo_hi) -> str:
    lo, hi = lo_hi
    return "" if lo is None else f" ({100 * lo:.1f}–{100 * hi:.1f}%)"


def mcnemar_greater(b: int, c: int) -> Optional[float]:
    """One-sided exact McNemar: P(X >= c) for X ~ Bin(b + c, 1/2); c = pairs where only the second arm wins."""
    n = b + c
    if n == 0:
        return None
    return sum(math.comb(n, k) for k in range(c, n + 1)) / 2 ** n


def newcombe_paired(a: int, b: int, c: int, d: int, z: float = 1.959964):
    """p1 - p2 with p1 = (a+b)/n, p2 = (a+c)/n, and its 95% CI (Newcombe 1998, method 10, with the
    continuity-corrected phi). a: both 1; b: first 1 only; c: second 1 only; d: both 0."""
    n = a + b + c + d
    if n == 0:
        return (None, None, None)
    p1, p2 = (a + b) / n, (a + c) / n
    (l1, u1), (l2, u2) = wilson(a + b, n, z), wilson(a + c, n, z)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    if den == 0:
        phi = 0.0
    else:
        num = a * d - b * c
        if num > 0:
            num = max(num - n / 2, 0.0)
        phi = num / math.sqrt(den)
    th = p1 - p2
    dl = math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    du = math.sqrt(max(0.0, (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2))
    return (th, th - dl, th + du)


def cost_usd(row: Dict[str, str], prices: Dict[str, Any]) -> Optional[float]:
    spec = (row.get("repairer_model") or "").strip()
    m = prices.get(spec)
    if not m or m.get("price_in") is None:
        return None
    tin, tout = _int(row.get("input_tokens")), _int(row.get("output_tokens"))
    pin, pout = m["price_in"], m["price_out"]
    tier = TIERS.get(spec.split(":", 1)[-1])
    if tier and tin > tier[0]:
        pin, pout = tier[1], tier[2]
    return tin / 1e6 * pin + tout / 1e6 * pout


def load(results: Path, ids: List[str]) -> Dict[str, Dict[str, Dict[str, str]]]:
    by: Dict[str, Dict[str, Dict[str, str]]] = {a: {} for a in ARMS}
    with open(results, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ag, vid = r.get("agent"), r.get("vuln_id")
            if ag not in by:
                continue
            if vid not in ids:
                raise SystemExit(f"{ag}/{vid} is not in the v5 case list")
            if vid in by[ag]:
                raise SystemExit(f"duplicate row {ag}/{vid}")
            by[ag][vid] = r
    return by


def complete(r: Optional[Dict[str, str]]) -> bool:
    return bool(r) and r.get("status") == "complete" and _bit(r.get("V")) in (0, 1)


def arm_summary(rows: Dict[str, Dict[str, str]], prices) -> Dict[str, Any]:
    done = [r for r in rows.values() if complete(r)]
    n = len(done)
    v = sum(_bit(r["V"]) for r in done)
    claims = [r for r in done if _bit(r.get("D_repairer")) == 1]
    false = sum(1 for r in claims if _bit(r["V"]) == 0)
    safe = sum(1 for r in claims if _bit(r["V"]) == 1)
    costs = [cost_usd(r, prices) for r in done]
    total = sum(c for c in costs if c is not None) if any(c is not None for c in costs) else None
    cov = [r for r in claims if (r.get("hint_coverage") or "").strip() not in ("", "None")]
    a_ = sum(1 for r in cov if _bit(r["V"]) == 1 and _bit(r.get("D_coverage")) == 1)
    b_ = sum(1 for r in cov if _bit(r["V"]) == 1 and _bit(r.get("D_coverage")) != 1)
    c_ = sum(1 for r in cov if _bit(r["V"]) == 0 and _bit(r.get("D_coverage")) == 1)
    d_ = sum(1 for r in cov if _bit(r["V"]) == 0 and _bit(r.get("D_coverage")) != 1)
    return {"attempted": len(rows), "complete": n, "incomplete": sorted(k for k, r in rows.items() if not complete(r)),
            "V": v, "VRR": v / n if n else None, "VRR_ci": wilson(v, n),
            "claims": len(claims), "false_claims": false, "FAR": false / len(claims) if claims else None,
            "FAR_ci": wilson(false, len(claims)), "safe_yield": safe / n if n else None,
            "cost_usd": round(total, 4) if total is not None else None,
            "CPV_usd": round(total / v, 4) if total is not None and v else None,
            "input_tokens": sum(_int(r.get("input_tokens")) for r in done),
            "output_tokens": sum(_int(r.get("output_tokens")) for r in done),
            "coverage_rule": {"pass_correct": a_, "veto_correct": b_, "pass_wrong": c_, "veto_wrong": d_,
                              "FAR": c_ / (a_ + c_) if a_ + c_ else None, "FAR_ci": wilson(c_, a_ + c_),
                              "fisher_one_sided_p": fisher_greater(a_, b_, c_, d_) if cov else None}}


def paired(x: Dict[str, Dict[str, str]], y: Dict[str, Dict[str, str]]) -> List[Tuple[str, int, int]]:
    return [(k, _bit(x[k]["V"]), _bit(y[k]["V"])) for k in sorted(x) if k in y and complete(x[k]) and complete(y[k])]


def h1(m: Dict, mr: Dict, exclude=()) -> Dict[str, Any]:
    pr = [p for p in paired(m, mr) if p[0] not in exclude]
    a = sum(1 for _, i, j in pr if i == 1 and j == 1)
    b = sum(1 for _, i, j in pr if i == 1 and j == 0)      # only the cheap model alone repaired
    c = sum(1 for _, i, j in pr if i == 0 and j == 1)      # only the cheap model with RAG repaired
    d = len(pr) - a - b - c
    n = len(pr)
    p = mcnemar_greater(b, c)
    diff = newcombe_paired(a, c, b, d)                     # VRR(c0mr) - VRR(c0m)
    vm, vmr = (a + b) / n if n else None, (a + c) / n if n else None
    return {"n_paired": n, "both": a, "only_m": b, "only_mr": c, "neither": d, "VRR_m": vm, "VRR_mr": vmr,
            "diff": diff[0], "diff_ci": (diff[1], diff[2]), "p_one_sided": p, "p_two_sided": mcnemar_exact(b, c),
            "confirmed": bool(p is not None and p < ALPHA and vmr is not None and vmr > vm)}


def cpv_bootstrap(c0: Dict, mr: Dict, prices) -> Dict[str, Any]:
    pr = [k for k in sorted(c0) if k in mr and complete(c0[k]) and complete(mr[k])]
    rows = [(cost_usd(c0[k], prices), _bit(c0[k]["V"]), cost_usd(mr[k], prices), _bit(mr[k]["V"])) for k in pr]
    if not rows or any(r[0] is None or r[2] is None for r in rows):
        return {"n_paired": len(rows), "note": "missing prices or tokens"}

    def ratio(sample):
        c_a, v_a = sum(r[0] for r in sample), sum(r[1] for r in sample)
        c_b, v_b = sum(r[2] for r in sample), sum(r[3] for r in sample)
        if not v_a or not v_b or not c_b:
            return None
        return (c_a / v_a) / (c_b / v_b)          # > 1: each verified repair is cheaper with c0mr

    point = ratio(rows)
    rng = random.Random(SEED)
    vals, undefined = [], 0
    for _ in range(BOOT):
        r = ratio([rows[rng.randrange(len(rows))] for _ in rows])
        if r is None:
            undefined += 1
        else:
            vals.append(r)
    vals.sort()
    lo = vals[int(0.025 * len(vals))] if vals else None
    hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))] if vals else None
    return {"n_paired": len(rows), "CPV_c0": (sum(r[0] for r in rows) / max(1, sum(r[1] for r in rows))),
            "CPV_c0mr": (sum(r[2] for r in rows) / max(1, sum(r[3] for r in rows))),
            "ratio_c0_over_c0mr": point, "ratio_ci95": (lo, hi), "resamples": BOOT, "undefined_resamples": undefined}


def harness_audit(c0_now: Dict, before: List[Path]) -> Dict[str, Any]:
    old: Dict[str, Dict[str, str]] = {}
    for p in before:
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("agent") == "c0":
                    old[r["vuln_id"]] = r
    flips, newly, lost = [], [], []
    for k, r in sorted(c0_now.items()):
        o = old.get(k)
        if o is None:
            continue
        if complete(o) and complete(r) and _bit(o["V"]) != _bit(r["V"]):
            flips.append({"case": k, "V_before": _bit(o["V"]), "V_v5": _bit(r["V"]),
                          "func_before": o.get("func_pfes"), "func_v5": r.get("func_pfes")})
        elif not complete(o) and complete(r):
            newly.append(k)
        elif complete(o) and not complete(r):
            lost.append(k)
    return {"compared": sum(1 for k in c0_now if k in old), "V_changed": flips, "now_complete": newly,
            "no_longer_complete": lost}


def rag_audit(runs: Path, ids: List[str]) -> Dict[str, Any]:
    recs = {}
    for vid in ids:
        p = runs / "c0mr" / vid / "llm_response.json"
        if p.exists():
            recs[vid] = (json.loads(p.read_text()).get("rag") or {})
    flagged = sorted(k for k, r in recs.items() if r.get("leak_flag"))
    errors = sorted(k for k, r in recs.items() if r.get("error"))
    toks = [r.get("section_tokens_est") for r in recs.values() if r.get("section_tokens_est") is not None]
    return {"records": len(recs), "errors": errors, "leak_flagged": flagged,
            "max_leak_ratio": max((a.get("ratio", 0) for r in recs.values() for a in r.get("leak_audit") or []), default=None),
            "with_cwe_guides": sum(1 for r in recs.values() if r.get("cwe_guides")),
            "section_tokens_mean": round(sum(toks) / len(toks), 1) if toks else None,
            "manifests": sorted({r.get("manifest_sha256") for r in recs.values() if r.get("manifest_sha256")}),
            "embed_models": sorted({r.get("embed_model") for r in recs.values() if r.get("embed_model")})}


def analyse(by, prices, ids, runs: Optional[Path], before: List[Path]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"arms": {a: arm_summary(by[a], prices) for a in ARMS}, "H1": h1(by["c0m"], by["c0mr"])}
    out["CPV"] = cpv_bootstrap(by["c0"], by["c0mr"], prices)
    pr = paired(by["c0mr"], by["c0"])
    a = sum(1 for _, i, j in pr if i == 1 and j == 1)
    b = sum(1 for _, i, j in pr if i == 1 and j == 0)
    c = sum(1 for _, i, j in pr if i == 0 and j == 1)
    d = len(pr) - a - b - c
    th, lo, hi = newcombe_paired(a, b, c, d)
    out["VRR_c0mr_minus_c0"] = {"n_paired": len(pr), "diff": th, "ci95": (lo, hi), "only_c0mr": b, "only_c0": c}
    if before:
        out["harness_audit"] = harness_audit(by["c0"], before)
    if runs:
        out["rag_audit"] = ra = rag_audit(runs, ids)
        if ra["leak_flagged"]:
            out["H1_without_leak_flagged"] = h1(by["c0m"], by["c0mr"], exclude=set(ra["leak_flagged"]))
    return out


def report(o: Dict[str, Any]) -> None:
    print("== decisiones_v5: RAG-R with a cheap model ==")
    for a in ARMS:
        s = o["arms"][a]
        print(f"{a:5s} complete {s['complete']}/{s['attempted']}  VRR {pct(s['VRR'])}{ci(s['VRR_ci'])}  "
              f"FAR {pct(s['FAR'])}{ci(s['FAR_ci'])} ({s['false_claims']}/{s['claims']})  safe yield {pct(s['safe_yield'])}  "
              f"cost {s['cost_usd']} USD  CPV {s['CPV_usd']} USD")
        cr = s["coverage_rule"]
        if cr["fisher_one_sided_p"] is not None:
            print(f"      coverage rule: FAR {pct(cr['FAR'])}{ci(cr['FAR_ci'])}, passes {cr['pass_correct']}/"
                  f"{cr['pass_correct'] + cr['veto_correct']} correct and {cr['pass_wrong']}/{cr['pass_wrong'] + cr['veto_wrong']} "
                  f"wrong, Fisher one-sided p = {cr['fisher_one_sided_p']:.4f}")
        if s["incomplete"]:
            print(f"      incomplete: {', '.join(s['incomplete'])}")
    h = o["H1"]
    print(f"\nH1 (primary): {h['n_paired']} paired cases; only c0m {h['only_m']}, only c0mr {h['only_mr']}; "
          f"VRR {pct(h['VRR_m'])} -> {pct(h['VRR_mr'])}; difference {pct(h['diff'])}{ci(h['diff_ci'])}; "
          f"one-sided exact McNemar p = {h['p_one_sided'] if h['p_one_sided'] is None else round(h['p_one_sided'], 4)}")
    print("RESULT: H1 " + ("CONFIRMED" if h["confirmed"] else "NOT CONFIRMED")
          + f" (needs p < {ALPHA} and VRR(c0mr) > VRR(c0m))")
    c = o["CPV"]
    if "ratio_c0_over_c0mr" in c and c["ratio_c0_over_c0mr"] is not None:
        lo, hi = c["ratio_ci95"]
        print(f"\nCost per verified repair: c0 {c['CPV_c0']:.4f} USD, c0mr {c['CPV_c0mr']:.4f} USD; c0 / c0mr = "
              f"{c['ratio_c0_over_c0mr']:.2f} (bootstrap 95% {lo:.2f}–{hi:.2f}; {c['undefined_resamples']} resamples undefined)")
    d = o["VRR_c0mr_minus_c0"]
    if d["diff"] is not None:
        print(f"VRR c0mr - c0: {pct(d['diff'])}{ci(d['ci95'])} on {d['n_paired']} paired cases")
    if "harness_audit" in o:
        ha = o["harness_audit"]
        print(f"\nv5 harness vs earlier C0 verdicts ({ha['compared']} cases): {len(ha['V_changed'])} changed V, "
              f"{len(ha['now_complete'])} newly complete {ha['now_complete']}, {len(ha['no_longer_complete'])} no longer complete")
        for f in ha["V_changed"]:
            print(f"      {f['case']}: V {f['V_before']} -> {f['V_v5']} (functional {f['func_before']} -> {f['func_v5']})")
    if "rag_audit" in o:
        ra = o["rag_audit"]
        print(f"\nRAG records {ra['records']}, errors {ra['errors']}, leak-flagged (>= {LEAK_FLAG}) {ra['leak_flagged']}, "
              f"max ratio {ra['max_leak_ratio']}, with CWE guides {ra['with_cwe_guides']}, mean section ~{ra['section_tokens_mean']} tokens, "
              f"model {ra['embed_models']}, manifest {ra['manifests']}")
    if "H1_without_leak_flagged" in o:
        h2 = o["H1_without_leak_flagged"]
        print(f"H1 without leak-flagged cases: p = {h2['p_one_sided']}, VRR {pct(h2['VRR_m'])} -> {pct(h2['VRR_mr'])}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path, required=True, help="runs/v5/results.csv (fa_metrics.py)")
    ap.add_argument("--ids-file", type=Path, required=True, help="runs/preflight/v5_ids.txt")
    ap.add_argument("--models-file", type=Path, default=HERE.parent / "models.json")
    ap.add_argument("--runs", type=Path, help="runs/v5 (reads c0mr/*/llm_response.json for the RAG audit)")
    ap.add_argument("--c0-before", type=Path, nargs="*", default=[],
                    help="earlier results.csv files with C0 rows (runs/final, runs/confirm) for the harness audit")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    ids = [x for x in a.ids_file.read_text().split() if x]
    prices = {k: v for k, v in json.loads(a.models_file.read_text()).items() if isinstance(v, dict)}
    o = analyse(load(a.results, ids), prices, ids, a.runs, a.c0_before)
    report(o)
    if a.json:
        a.json.write_text(json.dumps(o, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
