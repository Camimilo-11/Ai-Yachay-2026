#!/usr/bin/env python3
"""Analysis of decisiones_v5_1 (EXPLORATORY; run once, when both v5.1 arms have ended).

Arms of v5.1 (runs/v51, the 95 cases of v5, oracle session v5):
  c0mr51  M'+RAG': Claude Haiku 5.5 + related project code + coverage check + retrieval keyed by the case's CWE
  c0m51   M':      the same without the retrieval
Arms of v5 (runs/v5/results.csv): c0 (GPT-6.2 Sol, frozen patches), c0m (Haiku alone), c0mr (Haiku + RAG v1).

Main, as an estimate (no alpha, nothing is confirmed): VRR(c0mr51) - VRR(c0m51) on the cases complete in
both, Newcombe's interval for paired data (method 10) and the two-sided exact McNemar test.
Secondary: (1) c0m51 vs c0m and c0mr51 vs c0mr of v5, paired the same way; (2) the coverage check inside
each arm: verdict of the patch before the check (V_initial) against the final one, and FAR before and after;
(3) c0mr51 vs C0: VRR difference (Newcombe paired) and cost per verified repair as a ratio with a paired
bootstrap (10,000 resamples of cases, seed 2026, list prices, every call counted); (4) the v4 coverage rule on
the final patches of each arm (one-sided Fisher, descriptive); (5) audits: leakage flags, how many cases got
examples of their CWE, the guide only or no section, and the size of the related project code.

Inputs: results.csv of scripts/fa_metrics.py for runs/v51 and for runs/v5, the frozen llm_response.json
records of runs/v51 (calls, retrieval, project context, coverage check) and models.json for list prices.
Standard library only; the statistics are the functions of confirm_v4.py and confirm_v5.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from confirm_v4 import fisher_greater, mcnemar_exact, wilson  # noqa: E402
from confirm_v5 import TIERS, _bit, _int, ci, complete, cost_usd, newcombe_paired, pct  # noqa: E402

ARMS51 = ("c0mr51", "c0m51")
ARMS5 = ("c0", "c0m", "c0mr")
BOOT = 10_000
SEED = 2026
LEAK_FLAG = 0.5


# ----------------------------------------------------------------------------- loading

def load(results: Path, agents: Tuple[str, ...], ids: List[str]) -> Dict[str, Dict[str, Dict[str, str]]]:
    by: Dict[str, Dict[str, Dict[str, str]]] = {a: {} for a in agents}
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


def record(runs: Path, agent: str, vid: str) -> Dict[str, Any]:
    p = runs / agent / vid / "llm_response.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def call_cost(stage: Dict[str, Any], prices: Dict[str, Any]) -> Optional[float]:
    """List price of one call; Haiku's price tier depends on that call's prompt size (models.json)."""
    spec = stage.get("model") or ""
    m = prices.get(spec)
    if not m or m.get("price_in") is None:
        return None
    tin, tout = stage.get("input_tokens") or 0, stage.get("output_tokens") or 0
    pin, pout = m["price_in"], m["price_out"]
    tier = TIERS.get(spec.split(":", 1)[-1])
    if tier and tin > tier[0]:
        pin, pout = tier[1], tier[2]
    return tin / 1e6 * pin + tout / 1e6 * pout


def case_cost(rec: Dict[str, Any], prices) -> Tuple[Optional[float], int]:
    st = [s for s in (rec.get("stages") or {}).values() if s.get("status") == "ok"]
    costs = [call_cost(s, prices) for s in st]
    if any(c is None for c in costs):
        return None, len(st)
    return sum(costs), len(st)


def initial_verdict(row: Dict[str, str], runs: Path, agent: str) -> Optional[int]:
    """Verdict of the patch before the coverage check; an empty first patch (an abstention) cannot verify."""
    vi = _bit(row.get("V_initial"))
    if vi is not None:
        return vi
    p = runs / agent / row["vuln_id"] / "patch_initial.diff"
    if p.exists() and not p.read_text(encoding="utf-8", errors="replace").strip():
        return 0
    return None


# ----------------------------------------------------------------------------- summaries

def coverage_rule(done: List[Dict[str, str]]) -> Dict[str, Any]:
    claims = [r for r in done if _bit(r.get("D_repairer")) == 1]
    cov = [r for r in claims if (r.get("hint_coverage") or "").strip() not in ("", "None")]
    a_ = sum(1 for r in cov if _bit(r["V"]) == 1 and _bit(r.get("D_coverage")) == 1)
    b_ = sum(1 for r in cov if _bit(r["V"]) == 1 and _bit(r.get("D_coverage")) != 1)
    c_ = sum(1 for r in cov if _bit(r["V"]) == 0 and _bit(r.get("D_coverage")) == 1)
    d_ = sum(1 for r in cov if _bit(r["V"]) == 0 and _bit(r.get("D_coverage")) != 1)
    return {"pass_correct": a_, "veto_correct": b_, "pass_wrong": c_, "veto_wrong": d_,
            "FAR": c_ / (a_ + c_) if a_ + c_ else None, "FAR_ci": wilson(c_, a_ + c_),
            "fisher_one_sided_p": fisher_greater(a_, b_, c_, d_) if cov else None}


def arm51(rows: Dict[str, Dict[str, str]], runs: Path, agent: str, prices) -> Dict[str, Any]:
    done = [r for r in rows.values() if complete(r)]
    n = len(done)
    v = sum(_bit(r["V"]) for r in done)
    claims = [r for r in done if _bit(r.get("D_repairer")) == 1]
    false = sum(1 for r in claims if _bit(r["V"]) == 0)
    recs = {r["vuln_id"]: record(runs, agent, r["vuln_id"]) for r in done}
    costs, calls = [], 0
    for r in done:
        c, k = case_cost(recs[r["vuln_id"]], prices)
        costs.append(c)
        calls += k
    total = sum(c for c in costs if c is not None) if all(c is not None for c in costs) else None
    trail = [((rec.get("candidates") or [{}])[0].get("coverage_check") or [{}])[0] for rec in recs.values()]
    no_patch_final = sum(1 for r in done if _int(r.get("patch_bytes")) == 0)
    no_patch_initial = sum(1 for r in done
                           if not (runs / agent / r["vuln_id"] / "patch_initial.diff").exists()
                           or not (runs / agent / r["vuln_id"] / "patch_initial.diff").read_text().strip())
    # FAR before the check: the first answer's claim and the verdict of the first patch
    first = [(_bit(r.get("C_gen_initial")), initial_verdict(r, runs, agent)) for r in done]
    first = [(cl, vi) for cl, vi in first if cl is not None and vi is not None]
    claims0 = [x for x in first if x[0] == 1]
    false0 = sum(1 for _, vi in claims0 if vi == 0)
    v0 = sum(vi for _, vi in first)
    return {"attempted": len(rows), "complete": n, "incomplete": sorted(k for k, r in rows.items() if not complete(r)),
            "V": v, "VRR": v / n if n else None, "VRR_ci": wilson(v, n),
            "claims": len(claims), "false_claims": false, "FAR": false / len(claims) if claims else None,
            "FAR_ci": wilson(false, len(claims)),
            "no_patch_initial": no_patch_initial, "no_patch_final": no_patch_final,
            "coverage_check": {"fired": sum(1 for t in trail if t.get("action") not in (None, "none")),
                               "revised": sum(1 for t in trail if t.get("action") == "revised"),
                               "kept_previous": sum(1 for t in trail if (t.get("action") or "").endswith("kept_previous")),
                               "not_needed": sum(1 for t in trail if t.get("action") == "none")},
            "before_check": {"n": len(first), "V": v0, "VRR": v0 / len(first) if first else None,
                             "claims": len(claims0), "false_claims": false0,
                             "FAR": false0 / len(claims0) if claims0 else None, "FAR_ci": wilson(false0, len(claims0))},
            "calls": calls, "cost_usd": round(total, 4) if total is not None else None,
            "CPV_usd": round(total / v, 4) if total is not None and v else None,
            "coverage_rule": coverage_rule(done)}


def arm5(rows: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    done = [r for r in rows.values() if complete(r)]
    n, v = len(done), sum(_bit(r["V"]) for r in done)
    claims = [r for r in done if _bit(r.get("D_repairer")) == 1]
    false = sum(1 for r in claims if _bit(r["V"]) == 0)
    return {"complete": n, "V": v, "VRR": v / n if n else None, "VRR_ci": wilson(v, n), "claims": len(claims),
            "false_claims": false, "FAR": false / len(claims) if claims else None, "FAR_ci": wilson(false, len(claims))}


def paired(x: Dict[str, Dict[str, str]], y: Dict[str, Dict[str, str]], exclude=()) -> Dict[str, Any]:
    """VRR(x) - VRR(y) on the cases complete in both (Newcombe paired, two-sided exact McNemar)."""
    pr = [(k, _bit(x[k]["V"]), _bit(y[k]["V"])) for k in sorted(x)
          if k in y and k not in exclude and complete(x[k]) and complete(y[k])]
    a = sum(1 for _, i, j in pr if i == 1 and j == 1)
    b = sum(1 for _, i, j in pr if i == 1 and j == 0)
    c = sum(1 for _, i, j in pr if i == 0 and j == 1)
    d = len(pr) - a - b - c
    n = len(pr)
    th, lo, hi = newcombe_paired(a, b, c, d)
    return {"n_paired": n, "both": a, "only_first": b, "only_second": c, "neither": d,
            "VRR_first": (a + b) / n if n else None, "VRR_second": (a + c) / n if n else None,
            "diff": th, "diff_ci": (lo, hi), "p_two_sided": mcnemar_exact(b, c),
            "only_first_cases": [k for k, i, j in pr if i == 1 and j == 0],
            "only_second_cases": [k for k, i, j in pr if i == 0 and j == 1]}


def check_effect(rows: Dict[str, Dict[str, str]], runs: Path, agent: str) -> Dict[str, Any]:
    pr = []
    for r in rows.values():
        if complete(r):
            vi = initial_verdict(r, runs, agent)
            if vi is not None:
                pr.append((r["vuln_id"], vi, _bit(r["V"])))
    fixed = [k for k, i, j in pr if i == 0 and j == 1]
    broke = [k for k, i, j in pr if i == 1 and j == 0]
    return {"n": len(pr), "V_initial": sum(i for _, i, _ in pr), "V_final": sum(j for _, _, j in pr),
            "fixed_by_check": fixed, "broken_by_check": broke, "p_two_sided": mcnemar_exact(len(broke), len(fixed))}


def cpv_bootstrap(c0: Dict, mr: Dict, runs: Path, agent: str, prices) -> Dict[str, Any]:
    keys = [k for k in sorted(c0) if k in mr and complete(c0[k]) and complete(mr[k])]
    rows = [(cost_usd(c0[k], prices), _bit(c0[k]["V"]), case_cost(record(runs, agent, k), prices)[0], _bit(mr[k]["V"]))
            for k in keys]
    if not rows or any(r[0] is None or r[2] is None for r in rows):
        return {"n_paired": len(rows), "note": "missing prices or tokens"}

    def ratio(sample):
        c_a, v_a = sum(r[0] for r in sample), sum(r[1] for r in sample)
        c_b, v_b = sum(r[2] for r in sample), sum(r[3] for r in sample)
        if not v_a or not v_b or not c_b:
            return None
        return (c_a / v_a) / (c_b / v_b)          # > 1: each verified repair is cheaper with the v5.1 arm

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
    return {"n_paired": len(rows), "CPV_c0": sum(r[0] for r in rows) / max(1, sum(r[1] for r in rows)),
            "CPV_arm": sum(r[2] for r in rows) / max(1, sum(r[3] for r in rows)),
            "ratio_c0_over_arm": point, "ratio_ci95": (lo, hi), "resamples": BOOT, "undefined_resamples": undefined}


def audits(runs: Path, ids: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for agent in ARMS51:
        recs = {vid: record(runs, agent, vid) for vid in ids}
        recs = {k: r for k, r in recs.items() if r}
        pcs = [r.get("project_context") or {} for r in recs.values()]
        sn = [len(p.get("snippets", [])) for p in pcs]
        tk = [p.get("tokens_est", 0) for p in pcs]
        a: Dict[str, Any] = {"records": len(recs),
                             "project_context": {"cases_with_code": sum(1 for x in sn if x), "errors": sum(1 for p in pcs if "error" in p),
                                                 "excerpts_median": statistics.median(sn) if sn else None,
                                                 "tokens_median": statistics.median(tk) if tk else None,
                                                 "tokens_max": max(tk) if tk else None}}
        if agent == "c0mr51":
            rag = {k: r.get("rag") or {} for k, r in recs.items()}
            a["rag"] = {"with_examples": sum(1 for x in rag.values() if x.get("hits")),
                        "guide_only": sum(1 for x in rag.values() if not x.get("hits") and (x.get("section_chars") or 0) > 0),
                        "no_section": sum(1 for x in rag.values() if not (x.get("section_chars") or 0) and not x.get("error")),
                        "errors": sorted(k for k, x in rag.items() if x.get("error")),
                        "leak_flagged": sorted(k for k, x in rag.items() if x.get("leak_flag")),
                        "max_leak_ratio": max((y.get("ratio", 0) for x in rag.values() for y in x.get("leak_audit") or []),
                                              default=None),
                        "modes": sorted({x.get("mode") for x in rag.values() if x.get("mode")})}
        out[agent] = a
    return out


def analyse(by51, by5, prices, ids, runs: Path) -> Dict[str, Any]:
    o: Dict[str, Any] = {"arms_v51": {a: arm51(by51[a], runs, a, prices) for a in ARMS51},
                         "arms_v5": {a: arm5(by5[a]) for a in ARMS5}}
    o["main_c0mr51_minus_c0m51"] = paired(by51["c0mr51"], by51["c0m51"])
    o["c0m51_minus_c0m_v5"] = paired(by51["c0m51"], by5["c0m"])
    o["c0mr51_minus_c0mr_v5"] = paired(by51["c0mr51"], by5["c0mr"])
    o["c0mr51_minus_c0"] = paired(by51["c0mr51"], by5["c0"])
    o["check_effect"] = {a: check_effect(by51[a], runs, a) for a in ARMS51}
    o["CPV_c0_vs_c0mr51"] = cpv_bootstrap(by5["c0"], by51["c0mr51"], runs, "c0mr51", prices)
    o["audits"] = au = audits(runs, ids)
    flagged = set(au["c0mr51"].get("rag", {}).get("leak_flagged", []))
    if flagged:
        o["main_without_leak_flagged"] = paired(by51["c0mr51"], by51["c0m51"], exclude=flagged)
    return o


def report(o: Dict[str, Any]) -> None:
    print("== decisiones_v5_1 (EXPLORATORY): Claude Haiku 5.5 with project context, coverage check and CWE retrieval ==")
    for a in ARMS51:
        s = o["arms_v51"][a]
        print(f"{a:7s} complete {s['complete']}/{s['attempted']}  VRR {pct(s['VRR'])}{ci(s['VRR_ci'])}  "
              f"FAR {pct(s['FAR'])}{ci(s['FAR_ci'])} ({s['false_claims']}/{s['claims']})  calls {s['calls']}  "
              f"cost {s['cost_usd']} USD  CPV {s['CPV_usd']} USD")
        b, cc = s["before_check"], s["coverage_check"]
        print(f"        before the check: VRR {pct(b['VRR'])} ({b['V']}/{b['n']}), FAR {pct(b['FAR'])} ({b['false_claims']}/{b['claims']}); "
              f"no patch {s['no_patch_initial']} -> {s['no_patch_final']}; check fired {cc['fired']} (revised {cc['revised']}, "
              f"kept previous {cc['kept_previous']})")
        cr = s["coverage_rule"]
        if cr["fisher_one_sided_p"] is not None:
            print(f"        coverage rule on final patches: FAR {pct(cr['FAR'])}{ci(cr['FAR_ci'])}, passes {cr['pass_correct']}/"
                  f"{cr['pass_correct'] + cr['veto_correct']} correct and {cr['pass_wrong']}/{cr['pass_wrong'] + cr['veto_wrong']} wrong, "
                  f"Fisher one-sided p = {cr['fisher_one_sided_p']:.4f}")
        if s["incomplete"]:
            print(f"        incomplete: {', '.join(s['incomplete'])}")
    for a in ARMS5:
        s = o["arms_v5"][a]
        print(f"v5 {a:4s} complete {s['complete']}  VRR {pct(s['VRR'])}{ci(s['VRR_ci'])}  FAR {pct(s['FAR'])} ({s['false_claims']}/{s['claims']})")

    def line(name, d):
        p = d["p_two_sided"]
        print(f"{name}: {d['n_paired']} paired; only first {d['only_first']}, only second {d['only_second']}; "
              f"VRR {pct(d['VRR_first'])} vs {pct(d['VRR_second'])}; difference {pct(d['diff'])}{ci(d['diff_ci'])}; "
              f"two-sided exact McNemar p = {'–' if p is None else round(p, 4)}")
    print()
    line("MAIN (estimate) c0mr51 - c0m51", o["main_c0mr51_minus_c0m51"])
    line("c0m51 - c0m (v5)", o["c0m51_minus_c0m_v5"])
    line("c0mr51 - c0mr (v5)", o["c0mr51_minus_c0mr_v5"])
    line("c0mr51 - c0 (v5)", o["c0mr51_minus_c0"])
    if "main_without_leak_flagged" in o:
        line("MAIN without leak-flagged cases", o["main_without_leak_flagged"])
    for a in ARMS51:
        e = o["check_effect"][a]
        print(f"coverage check in {a}: {e['n']} cases, V {e['V_initial']} -> {e['V_final']}; fixed {len(e['fixed_by_check'])}, "
              f"broken {len(e['broken_by_check'])} (two-sided McNemar p = {e['p_two_sided']})")
    c = o["CPV_c0_vs_c0mr51"]
    if c.get("ratio_c0_over_arm") is not None:
        lo, hi = c["ratio_ci95"]
        print(f"cost per verified repair: c0 {c['CPV_c0']:.4f} USD, c0mr51 {c['CPV_arm']:.4f} USD; c0 / c0mr51 = "
              f"{c['ratio_c0_over_arm']:.2f} (bootstrap 95% {lo:.2f}–{hi:.2f}; {c['undefined_resamples']} undefined)")
    au = o["audits"]
    for a in ARMS51:
        pc = au[a]["project_context"]
        print(f"audit {a}: related code in {pc['cases_with_code']}/{au[a]['records']} cases (median {pc['excerpts_median']} excerpts, "
              f"~{pc['tokens_median']} tokens, max {pc['tokens_max']}), errors {pc['errors']}")
    ra = au["c0mr51"].get("rag", {})
    print(f"audit RAG: examples {ra.get('with_examples')}, guide only {ra.get('guide_only')}, no section {ra.get('no_section')}, "
          f"errors {ra.get('errors')}, leak-flagged {ra.get('leak_flagged')}, max ratio {ra.get('max_leak_ratio')}, modes {ra.get('modes')}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path, required=True, help="runs/v51/results.csv (fa_metrics.py)")
    ap.add_argument("--v5-results", type=Path, required=True, help="runs/v5/results.csv (c0, c0m, c0mr)")
    ap.add_argument("--runs", type=Path, required=True, help="runs/v51 (frozen records of the v5.1 arms)")
    ap.add_argument("--ids-file", type=Path, required=True, help="runs/preflight/v5_ids.txt")
    ap.add_argument("--models-file", type=Path, default=HERE.parent / "models.json")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    ids = [x for x in a.ids_file.read_text().split() if x]
    prices = {k: v for k, v in json.loads(a.models_file.read_text()).items() if isinstance(v, dict)}
    o = analyse(load(a.results, ARMS51, ids), load(a.v5_results, ARMS5, ids), prices, ids, a.runs)
    report(o)
    if a.json:
        a.json.write_text(json.dumps(o, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
