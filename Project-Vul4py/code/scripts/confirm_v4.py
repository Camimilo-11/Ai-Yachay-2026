#!/usr/bin/env python3
"""Pre-registered confirmatory analysis (decisiones v4).

Question: on cases never used before, does claiming a fix only when the patch touches every hinted
line range (rule "coverage") lower the false assurance rate (FAR) of the repairer's claims?

Input: the results.csv that scripts/fa_metrics.py writes for a runs directory (columns agent, vuln_id,
status, V, D_repairer, hint_coverage, D_coverage, D_coverage75).

Primary test: among complete attempts where the repairer claims a fix (D_repairer = 1) and the coverage
rule is defined, one-sided Fisher exact test that the rule lets correct patches (V = 1) through more
often than wrong ones (V = 0); alpha = 0.05.  The hypothesis is confirmed when p < alpha AND
FAR(coverage) < FAR(repairer) on the same attempts.  Everything else is reported, not tested.

Standard library only, so it runs in any Python 3.8+.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ALPHA = 0.05
RULES = ("coverage", "coverage75")
PRIMARY = "coverage"


def wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fisher_greater(a: int, b: int, c: int, d: int) -> float:
    """One-sided Fisher exact p for [[a, b], [c, d]]; rows V=1 / V=0, columns rule passes / rule vetoes.
    Alternative: the pass rate is higher in the first row."""
    r1, r2, c1 = a + b, c + d, a + c
    den = math.comb(r1 + r2, c1)
    return sum(math.comb(r1, x) * math.comb(r2, c1 - x) for x in range(a, min(r1, c1) + 1)) / den


def newcombe(k1: int, n1: int, k2: int, n2: int):
    """95% CI for p1 - p2 (Newcombe's hybrid score method, from two Wilson intervals)."""
    if not n1 or not n2:
        return (None, None)
    p1, p2 = k1 / n1, k2 / n2
    (l1, u1), (l2, u2) = wilson(k1, n1), wilson(k2, n2)
    d = p1 - p2
    return (d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2))


def mcnemar_exact(b: int, c: int):
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def _bit(v):
    v = (v or "").strip()
    return int(float(v)) if v not in ("", "None", "nan") else None


def _pct(x):
    return "–" if x is None else f"{100 * x:.1f}%"


def _ci(lo_hi):
    lo, hi = lo_hi
    return "" if lo is None else f" ({100 * lo:.1f}–{100 * hi:.1f}%)"


def analyse(rows, ids=None):
    out = {"alpha": ALPHA, "primary_rule": PRIMARY}
    seen = {}
    for r in rows:
        seen.setdefault(r["vuln_id"], []).append(r)
    dup = sorted(k for k, v in seen.items() if len(v) > 1)
    if dup:
        raise SystemExit(f"more than one attempt per case: {dup}")
    if ids is not None:
        out["ids_expected"] = len(ids)
        out["not_in_list"] = sorted(set(seen) - set(ids))
        out["not_attempted"] = sorted(set(ids) - set(seen))
        if out["not_in_list"]:
            raise SystemExit(f"attempts outside the confirmation list: {out['not_in_list']}")
    comp = [r for r in rows if r.get("status") == "complete" and _bit(r.get("V")) in (0, 1)]
    out["attempts"] = len(rows)
    out["incomplete"] = sorted(r["vuln_id"] for r in rows if r not in comp)
    N = len(comp)
    sV = sum(_bit(r["V"]) for r in comp)
    out["N"] = N
    out["VRR"] = sV / N if N else None
    out["VRR_CI95"] = wilson(sV, N)

    def claims(rule, subset):
        acc = [r for r in subset if _bit(r[f"D_{rule}"]) == 1]
        fa = sum(1 for r in acc if _bit(r["V"]) == 0)
        ok = len(acc) - fa
        return {"N": len(subset), "accepted": len(acc), "false_assurance": fa,
                "FAR": fa / len(acc) if acc else None, "FAR_CI95": wilson(fa, len(acc)),
                "safe_yield": ok / len(subset) if subset else None}

    out["repairer_all"] = claims("repairer", comp)
    for rule in RULES:
        dfn = [r for r in comp if _bit(r[f"D_{rule}"]) is not None]
        bad = [r["vuln_id"] for r in dfn if _bit(r[f"D_{rule}"]) == 1 and _bit(r["D_repairer"]) != 1]
        if bad:
            raise SystemExit(f"{rule} accepts without a repairer claim: {bad}")
        rep = [r for r in dfn if _bit(r["D_repairer"]) == 1]
        a = sum(1 for r in rep if _bit(r["V"]) == 1 and _bit(r[f"D_{rule}"]) == 1)
        b = sum(1 for r in rep if _bit(r["V"]) == 1 and _bit(r[f"D_{rule}"]) == 0)
        c = sum(1 for r in rep if _bit(r["V"]) == 0 and _bit(r[f"D_{rule}"]) == 1)
        d = sum(1 for r in rep if _bit(r["V"]) == 0 and _bit(r[f"D_{rule}"]) == 0)
        res = {"undefined": sorted(r["vuln_id"] for r in comp if r not in dfn),
               "repairer_same_cases": claims("repairer", dfn), "rule": claims(rule, dfn),
               "table_V1_pass_veto_V0_pass_veto": [a, b, c, d],
               "fisher_one_sided_p": fisher_greater(a, b, c, d) if rep else None,
               "pass_rate_correct": a / (a + b) if a + b else None,
               "pass_rate_wrong": c / (c + d) if c + d else None,
               "pass_rate_difference_CI95": newcombe(a, a + b, c, c + d),
               "false_assurances_removed": d, "correct_claims_lost": b,
               "mcnemar_p_descriptive": mcnemar_exact(d, 0)}
        if rule == PRIMARY:
            far_r, far_c = res["repairer_same_cases"]["FAR"], res["rule"]["FAR"]
            p = res["fisher_one_sided_p"]
            res["confirmed"] = bool(p is not None and p < ALPHA and far_r is not None and far_c is not None
                                    and far_c < far_r)
        out[rule] = res
    out["confirmed"] = out[PRIMARY]["confirmed"]
    return out


def report(o, agent):
    lines = [f"Confirmatory analysis (decisiones v4), agent {agent}",
             f"attempts {o['attempts']}, complete N = {o['N']}, incomplete {o['incomplete'] or 'none'}"]
    if "ids_expected" in o:
        lines.append(f"cases in the list {o['ids_expected']}, not attempted {o['not_attempted'] or 'none'}")
    lines.append(f"VRR {_pct(o['VRR'])}{_ci(o['VRR_CI95'])}")
    r = o["repairer_all"]
    lines.append(f"repairer: accepted {r['accepted']}, false assurance {r['false_assurance']}, "
                 f"FAR {_pct(r['FAR'])}{_ci(r['FAR_CI95'])}, safe yield {_pct(r['safe_yield'])}")
    for rule in RULES:
        x = o[rule]
        rr, ru = x["repairer_same_cases"], x["rule"]
        a, b, c, d = x["table_V1_pass_veto_V0_pass_veto"]
        lines += [f"{rule}{'  [PRIMARY]' if rule == PRIMARY else '  [secondary]'}: undefined {x['undefined'] or 'none'}",
                  f"  repairer on the same cases: FAR {_pct(rr['FAR'])} ({rr['false_assurance']}/{rr['accepted']})",
                  f"  {rule}: accepted {ru['accepted']}, false assurance {ru['false_assurance']}, "
                  f"FAR {_pct(ru['FAR'])}{_ci(ru['FAR_CI95'])}, safe yield {_pct(ru['safe_yield'])}",
                  f"  among repairer claims: correct pass {a}/{a + b}, wrong pass {c}/{c + d}; "
                  f"one-sided Fisher p = {x['fisher_one_sided_p']:.4f}" if x["fisher_one_sided_p"] is not None
                  else "  no repairer claims",
                  "  difference in pass rate (correct - wrong): "
                  + ("–" if x["pass_rate_correct"] is None or x["pass_rate_wrong"] is None else
                     f"{100 * (x['pass_rate_correct'] - x['pass_rate_wrong']):.1f} points"
                     f" (95% CI {100 * x['pass_rate_difference_CI95'][0]:.1f} to {100 * x['pass_rate_difference_CI95'][1]:.1f})"),
                  f"  false assurances removed {d}, correct claims lost {b}, McNemar (descriptive) p = "
                  + ("–" if x["mcnemar_p_descriptive"] is None else f"{x['mcnemar_p_descriptive']:.4f}")]
    lines.append(f"RESULT: hypothesis {'CONFIRMED' if o['confirmed'] else 'NOT confirmed'} "
                 f"(needs one-sided Fisher p < {ALPHA} and FAR(coverage) < FAR(repairer))")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results", type=Path, required=True, help="results.csv written by fa_metrics.py")
    ap.add_argument("--agent", default="c0")
    ap.add_argument("--ids-file", type=Path, help="the confirmation list (checks that no other case is included)")
    ap.add_argument("--json", type=Path, help="also write the full result as JSON here")
    a = ap.parse_args(argv)
    with open(a.results, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("agent") == a.agent]
    if not rows:
        raise SystemExit(f"no rows for agent {a.agent} in {a.results}")
    ids = None
    if a.ids_file:
        ids = [l.strip() for l in a.ids_file.read_text(encoding="utf-8").splitlines()
               if l.strip() and not l.startswith("#")]
    o = analyse(rows, ids)
    o["agent"] = a.agent
    print(report(o, a.agent))
    if a.json:
        a.json.write_text(json.dumps(o, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
