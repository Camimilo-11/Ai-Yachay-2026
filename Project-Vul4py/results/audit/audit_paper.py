#!/usr/bin/env python3
"""audit_paper.py -- independent audit of the numbers of the final paper and of its data figures.

  python audit_paper.py <repo_root> <out_dir>

Recomputes every checked number from the raw files of the repository (CSV/TSV/JSON written by the runs), with
code written for the audit only: it does not import make_figures.py, fa_metrics.py or confirm_v4.py, and it
computes intervals and tests with other methods (Wilson bounds by root finding, scipy's exact tests).
The reported values are transcribed from papers/final/paper/main.tex (table or text, with the line) and from
results/figures/figure_values.csv (read from the file). Output: <out_dir>/audit_checks.csv (one row per check)
and <out_dir>/audit_summary.json.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from scipy.optimize import brentq
from scipy.stats import binomtest, fisher_exact, norm

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
Z = norm.ppf(0.975)
CHECKS: list[dict] = []


# ----------------------------------------------------------------------------------------------- helpers
def rows(rel, delim=","):
    with open(ROOT / rel, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delim))


def b(v):
    v = (v or "").strip()
    if v in ("", "None", "nan"):
        return None
    if v in ("True", "False"):
        return int(v == "True")
    return int(float(v))


def wilson_root(k, n):
    """Wilson score bounds as the roots of (phat - p)^2 = z^2 p (1 - p) / n (independent of the closed form)."""
    ph = k / n
    f = lambda p: (ph - p) ** 2 - Z * Z * p * (1 - p) / n  # noqa: E731
    # p = 0 (k = 0) and p = 1 (k = n) are trivial roots; search the other root away from them
    lo = 0.0 if k == 0 else brentq(f, 1e-12, ph if k < n else 1 - 1e-9)
    hi = 1.0 if k == n else brentq(f, ph if k > 0 else 1e-9, 1 - 1e-12)
    return lo, hi


def mcnemar_exact(x_ref, x_new):
    """two-sided exact McNemar on paired 0/1 indicators."""
    bb = sum(1 for a, c in zip(x_ref, x_new) if a == 1 and c == 0)
    cc = sum(1 for a, c in zip(x_ref, x_new) if a == 0 and c == 1)
    return (1.0 if bb + cc == 0 else binomtest(min(bb, cc), bb + cc, 0.5).pvalue), bb, cc


def fisher_greater(kc, nc, kw, nw):
    """one-sided Fisher: the rule keeps correct claims (kc of nc) more often than wrong ones (kw of nw)."""
    return fisher_exact([[kc, nc - kc], [kw, nw - kw]], alternative="greater").pvalue


def newcombe_hybrid(k1, n1, k2, n2):
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson_root(k1, n1)
    l2, u2 = wilson_root(k2, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def check(cid, area, where, item, reported, recomputed, tol=None, note="", kind="value"):
    """kind=value: numeric with tolerance (half a unit of the last printed digit unless given);
    kind=exact: string/integer identity; kind=info: recorded, not judged."""
    if kind == "info":
        status = "INFO"
    elif kind == "open":
        status = "OPEN"
    elif kind == "exact":
        status = "PASS" if str(reported) == str(recomputed) else "FAIL"
    else:
        if tol is None:
            s = str(reported)
            dec = len(s.split(".")[1]) if "." in s else 0
            tol = 0.5 * 10 ** (-dec) + 1e-9
        status = "PASS" if abs(float(reported) - float(recomputed)) <= tol else "FAIL"
    CHECKS.append({"id": cid, "area": area, "where": where, "item": item, "reported": reported,
                   "recomputed": recomputed if not isinstance(recomputed, float) else round(recomputed, 6),
                   "tolerance": "" if tol is None else tol, "status": status, "note": note})


def pct(k, n):
    return 100.0 * k / n


def kn_ci(cid, area, where, item, k_rep, n_rep, pct_rep, lo_rep, hi_rep, k, n):
    """a 'k/n = x% (lo-hi)' cell: counts exact, percent and bounds to one decimal."""
    check(cid + ".k", area, where, item + " numerator", k_rep, k, kind="exact")
    check(cid + ".n", area, where, item + " denominator", n_rep, n, kind="exact")
    check(cid + ".pct", area, where, item + " percent", pct_rep, pct(k, n))
    if lo_rep is not None:
        lo, hi = wilson_root(k, n)
        check(cid + ".lo", area, where, item + " Wilson low (%)", lo_rep, 100 * lo)
        check(cid + ".hi", area, where, item + " Wilson high (%)", hi_rep, 100 * hi)


# ----------------------------------------------------------------------------------------------- prices
MODELS = json.loads((ROOT / "code/models.json").read_text())


def list_cost(model, tin, tout):
    m = MODELS[model]
    pin, pout = m["price_in"], m["price_out"]
    if model.endswith("claude-haiku-5-5") and tin > 100_000:          # Haiku 5.5: 0.50/2.50 above 100k prompt tokens
        pin, pout = 0.50, 2.50
    return tin * pin / 1e6 + tout * pout / 1e6


# =============================================================================================== 1. environment
A = "Environment (Fig. 4, Sec. 4.1, Table 2)"
rounds = sorted(glob.glob(str(ROOT / "experiments/v1_environment/scan_report_round*.tsv")))
ok = [sum(1 for r in rows(Path(p).relative_to(ROOT), "\t") if r["status"] == "OK") for p in rounds]
for i, rep in enumerate([86, 98, 99, 99, 99, 100]):
    check(f"E1.R{i}", A, "main.tex l.253 (text); figure_values.csv", f"cases OK in build round R{i}", rep, ok[i], kind="exact")
orc = rows("experiments/v1_environment/oracle_report.tsv", "\t")
healthy = {r["vuln_id"] for r in orc if r["healthy"] == "True"}
valid = {x for x in (ROOT / "prereg/oracle_valid.txt").read_text().split() if x}
check("E2.healthy", A, "main.tex l.253", "oracle control healthy (oracle_report.tsv)", 100, len(healthy), kind="exact")
check("E2.same_set", A, "Fig. 4 reads oracle_report.tsv and checks prereg/oracle_valid.txt", "oracle_valid.txt == healthy set of oracle_report.tsv",
      "True", str(healthy == valid), kind="exact")
doc = (ROOT / "code/docs/README_multiagent.md").read_text(encoding="utf-8")
check("E3.public18", A, "main.tex l.135, l.253; abstract", "public release passes the first scan: 18 documented in code/docs",
      "True", str(bool(re.search(r"\b18\b", doc))), kind="exact", note="constant typed in make_figures.py; no raw scan file of the public release in the repo")
tags = Counter()
pyset = 0
pat = "doctor:deps|doctor:era|timeouts|auto_skip|oracle_repair|vuln_only|manual|torch_cpu"
mo = sorted(glob.glob(str(ROOT / "code/dataset/meta_overrides/*.json")))
for f in mo:
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    for t in set(re.findall(r"\[(%s)[\]:\s]" % pat, d.get("_note", ""))):
        tags[t] += 1
    pyset += "python_version" in d.get("set", {})
check("E4.files", A, "Table 2 caption; l.135", "meta_override files", 91, len(mo), kind="exact")
check("E4.test_overrides", A, "l.135", "test_overrides cases", 14, len(list((ROOT / "code/dataset/test_overrides").iterdir())), kind="exact")
for t, rep in (("doctor:deps", 14), ("doctor:era", 63), ("timeouts", 8), ("auto_skip", 65), ("oracle_repair", 26),
               ("vuln_only", 3), ("torch_cpu", 6), ("manual", 32)):
    check(f"E4.{t}", A, "Table 2", f"override notes tagged [{t}]", rep, tags[t], kind="exact",
          note="manual: 32 tagged + 3 described in prose (prose not machine-checkable)" if t == "manual" else "")
check("E4.python", A, "l.253", "override files that set the Python version", 54, pyset, kind="exact")

# =============================================================================================== 2. pilot
A = "Pilot comparisons (Table 4, Fig. 5, Sec. 4.2)"
v0 = rows("experiments/v0_mvp/results.csv")
v0_claims = [r for r in v0 if r["claim"] == "True"]
check("P0.vrr", A, "Table 4 / Fig. 5 / Fig. 7", "v0 verified", "1/5", f"{sum(r['verified_repair'] == 'True' for r in v0)}/{len(v0)}", kind="exact")
check("P0.far", A, "Intro l.57; Fig. 7", "v0 false claims / claims", "3/4",
      f"{sum(r['verified_repair'] == 'False' for r in v0_claims)}/{len(v0_claims)}", kind="exact")
check("P0.conf", A, "Intro l.57", "v0 claims made with 95% confidence", "95", ",".join(sorted({r["confidence_percent"] for r in v0_claims})), kind="exact")
pil = rows("experiments/v2_pilot_tournament/results.csv")


def arm(rs, agent, claim):
    done = [r for r in rs if r["agent"] == agent and r["status"] == "complete" and b(r["V"]) in (0, 1)]
    cl = [r for r in done if b(r[claim]) == 1]
    return {"n": len(done), "v": sum(b(r["V"]) for r in done), "claims": len(cl),
            "fa": sum(1 for r in cl if b(r["V"]) == 0), "rows": done}


for ag, claim, lab, rv, rc, rf in (("rep_gpt-6.2-sol", "D_repairer", "Tournament GPT-6.2 Sol", "3/5", 5, 2),
                                   ("rep_gpt-5.4-mini", "D_repairer", "Tournament GPT-5.4 mini", "1/5", 5, 4),
                                   ("c1", "D_unanimous", "C1 pilot 1 (GPT jury)", "3/5", 4, 1),
                                   ("c1v2", "D_unanimous", "C1 pilot 2 (cross-family jury)", "3/5", 5, 2)):
    a = arm(pil, ag, claim)
    check(f"P1.{ag}.vrr", A, "Table 4; Fig. 5", f"{lab} VRR", rv, f"{a['v']}/{a['n']}", kind="exact")
    check(f"P1.{ag}.claims", A, "Table 4", f"{lab} claims", rc, a["claims"], kind="exact")
    check(f"P1.{ag}.fa", A, "Table 4", f"{lab} false assurances", rf, a["fa"], kind="exact")
a = arm(pil, "c1", "D_repairer")
check("P1.c1.repairer_fa", A, "l.265 text", "C1 pilot 1: false claims of the repairer before the jury", 2, a["fa"], kind="exact")
gb = rows("experiments/v3_main/gpt_benchmark/gpt_benchmark_verdicts.csv")
for m, rep in (("gpt-6-luna", "0/5"), ("gpt-6.1-terra", "1/5"), ("gpt-6.2-astra", "3/5"), ("gpt-6.2-sol", "3/5"),
               ("gpt-6.2-sol_recortado", "3/5")):
    rr = [r for r in gb if r["model"] == m]
    check(f"P2.{m}", A, "Table 4; Fig. 5; l.265", f"GPT benchmark {m}", rep, f"{sum(int(r['V']) for r in rr)}/{len(rr)}", kind="exact")
check("P2.luna_empty", A, "l.265", "GPT-6 Luna answers with an empty patch", 4,
      sum(1 for r in gb if r["model"] == "gpt-6-luna" and "empty patch" in r["notes"]), kind="exact")

# =============================================================================================== 3. calibration
A = "Juror calibration (Table 5, Fig. 6, Sec. 4.3)"


def calib(rel):
    out = {}
    for r in rows(rel):
        out.setdefault(r["model"], []).append(r)
    res = {}
    for m, rs in out.items():
        pos = [r for r in rs if r["truth"] == "1"]
        neg = [r for r in rs if r["truth"] == "0"]
        sens = sum(r["claim"] == "1" for r in pos) / len(pos)
        spec = sum(r["claim"] == "0" for r in neg) / len(neg)
        # AUROC as the Mann-Whitney probability, ties counted one half
        wins = sum((float(p["confidence"]) > float(q["confidence"])) + 0.5 * (float(p["confidence"]) == float(q["confidence"]))
                   for p in pos for q in neg)
        auroc = wins / (len(pos) * len(neg))
        brier = statistics.fmean((float(r["confidence"]) - int(r["truth"])) ** 2 for r in rs)
        real_neg = [r for r in neg if r.get("kind") not in ("reference", "decoy")]
        spec_real = (sum(r["claim"] == "0" for r in real_neg) / len(real_neg)) if real_neg else None
        res[m] = {"n": len(rs), "pos": len(pos), "neg": len(neg), "sens": sens, "spec": spec, "auroc": auroc,
                  "brier": brier, "spec_real": spec_real, "status": Counter(r["status"] for r in rs)}
    return res


c2 = calib("experiments/v2_pilot_tournament/judge_calibration_v2/judge_calibration.csv")
c1 = calib("experiments/v2_pilot_tournament/judge_calibration_v1/judge_calibration.csv")
T5 = {"claudecode:claude-opus-5-5": (0.913, 0.846, 0.667, 0.126), "claudecode:claude-sonnet-5-5": (0.905, 0.846, 0.733, 0.145),
      "claudecode:claude-haiku-5-5": (0.900, 0.769, 0.733, 0.155), "deepseek:deepseek-v4-pro": (0.838, 0.846, 0.933, 0.150),
      "deepseek:deepseek-flash": (0.744, 0.846, 0.867, 0.214), "openai:gpt-6.1-sol": (0.800, 0.600, 0.778, 0.245),
      "openai:gpt-6.1-terra": (0.711, 0.600, 0.833, 0.201), "openai:gpt-6.2-astra": (0.700, 0.600, 0.833, 0.215),
      "openai:gpt-6-luna": (0.672, 0.800, 0.778, 0.421)}
for m, (au, se, sp, br) in T5.items():
    r = c2.get(m) or c1.get(m)
    tag = m.split(":")[1]
    check(f"K1.{tag}.auroc", A, "Table 5", f"{tag} AUROC", f"{au:.3f}", r["auroc"])
    check(f"K1.{tag}.sens", A, "Table 5", f"{tag} sensitivity", f"{se:.3f}", r["sens"])
    check(f"K1.{tag}.spec", A, "Table 5", f"{tag} specificity", f"{sp:.3f}", r["spec"])
    check(f"K1.{tag}.brier", A, "Table 5", f"{tag} Brier", f"{br:.3f}", r["brier"])
    check(f"K1.{tag}.n", A, "Table 5", f"{tag} candidates", 28 if m in c2 else 23, r["n"], kind="exact")
    check(f"K1.{tag}.ok", A, "l.295 'No candidate refused'", f"{tag} rows not ok", 0, r["n"] - r["status"].get("ok", 0), kind="exact")
check("K1.v2_truth", A, "Fig. 6 x-label; l.202", "v2 candidates correct/wrong", "13/15",
      ",".join(sorted({f"{r['pos']}/{r['neg']}" for r in c2.values()})), kind="exact")
spec_real = [c2[m]["spec_real"] for m in c2 if "claude" in m]
check("K2.spec_real_min", A, "Discussion l.574", "Claude specificity on real wrong patches, min", "0.50", min(spec_real))
check("K2.spec_real_max", A, "Discussion l.574", "Claude specificity on real wrong patches, max", "0.60", max(spec_real))
jury = next(l.split("=", 1)[1].strip() for l in (ROOT / "prereg/decisiones_v2.txt").read_text(encoding="utf-8").splitlines()
            if l.startswith("jurado="))
check("K3.jury", A, "l.295; Fig. 6 asterisks", "jury fixed in decisiones_v2",
      "claudecode:claude-opus-5-5,claudecode:claude-sonnet-5-5,deepseek:deepseek-v4-pro", ",".join(sorted(jury.split(","))), kind="exact")
top3 = sorted(c2, key=lambda m: -c2[m]["auroc"])
check("K3.rule", A, "l.202 rule", "highest AUROC with one per provider -> same three", "True",
      str(set(jury.split(",")) == {top3[0], top3[1], next(m for m in top3 if m.startswith("deepseek"))}), kind="exact")
usage = json.loads((ROOT / "experiments/v2_pilot_tournament/judge_calibration_v2/judge_calibration_usage.json").read_text())
tot = list(csv.DictReader(open(ROOT / "results/logs/calls/calls_v2_judge_calibration_totals.csv")))
costs = {}
for m, rep in (("claudecode:claude-opus-5-5", "0.68"), ("claudecode:claude-sonnet-5-5", "0.30"), ("claudecode:claude-haiku-5-5", "0.08"),
               ("deepseek:deepseek-v4-pro", "0.81"), ("deepseek:deepseek-flash", "0.28")):
    # per-call Haiku prompts: total/5 < 100k, so the base price applies
    costs[m] = list_cost(m, usage[m]["input_tokens"] / 5, usage[m]["output_tokens"] / 5) * 5
    check(f"K4.{m.split(':')[1]}", A, "Table 5; Fig. 6 right", f"{m} list-price cost of 5 calls", rep, costs[m])
    t = next(r for r in tot if r["model"] == m)
    check(f"K4.{m.split(':')[1]}.tokens", A, "calls_v2_judge_calibration_totals.csv", f"{m} tokens usage.json == totals csv",
          f"{t['input_tokens']}/{t['output_tokens']}", f"{usage[m]['input_tokens']}/{usage[m]['output_tokens']}", kind="exact")
check("K4.total_list", A, "l.295; Table 12", "calibration total at list price", "2.14", sum(costs.values()))
client = sum(float(r["cost_usd"]) for r in tot)
check("K4.total_client", A, "l.295", "calibration total with the client's report for Claude", "2.64", client)
check("K4.claude_client", A, "Table 12", "calibration, Claude calls, client report", "1.55",
      sum(float(r["cost_usd"]) for r in tot if r["model"].startswith("claudecode")))
check("K4.claude_list", A, "Table 12", "calibration, Claude calls, list price", "1.05", sum(v for m, v in costs.items() if "claude" in m))
check("K4.tokens", A, "Table 12", "calibration tokens in/out", "349,054/572,872",
      f"{sum(int(r['input_tokens']) for r in tot):,}/{sum(int(r['output_tokens']) for r in tot):,}", kind="exact")

# =============================================================================================== 4. main sample
A = "Main sample and confirmation (Table 6, Fig. 7, Sec. 4.4, abstract)"
v3 = rows("experiments/v3_main/results.csv")
v4 = rows("experiments/v4_evigate_confirmation/confirm/results.csv")
T6 = {"c0": (v3, "D_repairer", 16, 29, 55.2, 37.5, 71.6, 28, 12, 42.9, 26.5, 60.9, 55.2, 1, 12),
      "c0g": (v3, "D_repairer", 14, 29, 48.3, 31.4, 65.6, 28, 14, 50.0, 32.6, 67.4, 48.3, 1, 14),
      "c1": (v3, "D_unanimous", 14, 29, 48.3, 31.4, 65.6, 26, 12, 46.2, 28.8, 64.5, 48.3, 2, 13),
      "conf": (v4, "D_repairer", 22, 63, 34.9, 24.3, 47.2, 61, 40, 65.6, 53.0, 76.3, 33.3, 7, 34)}
for key, (rs, claim, vk, vn, vp, vl, vh, cl, fk, fp, fl, fh, sy, broke, expl) in T6.items():
    a = arm(rs, "c0" if key == "conf" else key, claim)
    kn_ci(f"M1.{key}.vrr", A, "Table 6; Fig. 7", f"{key} VRR", vk, vn, f"{vp:.1f}", f"{vl:.1f}", f"{vh:.1f}", a["v"], a["n"])
    check(f"M1.{key}.claims", A, "Table 6", f"{key} claims", cl, a["claims"], kind="exact")
    kn_ci(f"M1.{key}.far", A, "Table 6; Fig. 7", f"{key} FAR", fk, cl, f"{fp:.1f}", f"{fl:.1f}", f"{fh:.1f}", a["fa"], a["claims"])
    sy_k = sum(1 for r in a["rows"] if b(r[claim]) == 1 and b(r["V"]) == 1)
    check(f"M1.{key}.safe", A, "Table 6", f"{key} safe yield (%)", f"{sy:.1f}", pct(sy_k, a["n"]))
    unv = [r for r in a["rows"] if b(r["V"]) == 0]
    br_ = sum(1 for r in unv if b(r["A"]) == 0 or b(r["F"]) == 0)
    ex_ = sum(1 for r in unv if b(r["A"]) == 1 and b(r["F"]) == 1 and b(r["S"]) == 0)
    check(f"M1.{key}.broke", A, "Table 6", f"{key} unverified: did not apply or broke functionality", broke, br_, kind="exact")
    check(f"M1.{key}.expl", A, "Table 6; l.329", f"{key} unverified: functional OK, exploit failed", expl, ex_, kind="exact")
    check(f"M1.{key}.unv", A, "l.329", f"{key} unverified total = broke + exploit fails", len(unv), br_ + ex_, kind="exact")
inc3 = sorted({r["vuln_id"] for r in v3 if r["status"] != "complete"})
check("M2.excluded", A, "l.329", "main sample: excluded case (all conditions)", "CVE-2024-27454", ",".join(inc3), kind="exact")
check("M2.attempted", A, "Table 14", "main sample attempts per condition", "30/30/30",
      "/".join(str(sum(r["agent"] == g for r in v3)) for g in ("c0", "c0g", "c1")), kind="exact")
inc4 = sorted(r["vuln_id"] for r in v4 if r["status"] != "complete")
check("M2.v4_incomplete", A, "l.431; Table 1", "confirmation: attempted / incomplete", "65: CVE-2024-52804,CVE-2025-5120",
      f"{len(v4)}: {','.join(inc4)}", kind="exact")
pooled_v = arm(v3, "c0", "D_repairer")["v"] + arm(v4, "c0", "D_repairer")["v"]
pooled_n = arm(v3, "c0", "D_repairer")["n"] + arm(v4, "c0", "D_repairer")["n"]
check("M3.pooled", A, "Discussion l.572", "repairer alone, v3+v4 verified", "38/92", f"{pooled_v}/{pooled_n}", kind="exact")
check("M3.pooled_pct", A, "Discussion l.572", "repairer alone, v3+v4 percent", "41.3", pct(pooled_v, pooled_n))
ids = {n: set((ROOT / f"prereg/{n}").read_text().split()) for n in ("main_ids.txt", "pilot_ids.txt", "confirm65_ids.txt")}
check("M4.disjoint", A, "Table 1 caption", "main, pilot and confirmation ids disjoint; sizes 30/5/65", "True 30/5/65",
      f"{not (ids['main_ids.txt'] & ids['pilot_ids.txt'] or ids['main_ids.txt'] & ids['confirm65_ids.txt'] or ids['pilot_ids.txt'] & ids['confirm65_ids.txt'])} "
      f"{len(ids['main_ids.txt'])}/{len(ids['pilot_ids.txt'])}/{len(ids['confirm65_ids.txt'])}", kind="exact")
check("M4.v3_ids", A, "Table 1", "v3 cases == main_ids", "True", str({r["vuln_id"] for r in v3} == ids["main_ids.txt"]), kind="exact")
check("M4.v4_ids", A, "Table 1", "v4 cases == confirm65_ids", "True", str({r["vuln_id"] for r in v4} == ids["confirm65_ids.txt"]), kind="exact")

# =============================================================================================== 5. claim rules
A = "Claim rules and protocol (Tables 7-8, Sec. 4.5)"
c1r = [r for r in v3 if r["agent"] == "c1" and r["status"] == "complete" and b(r["V"]) in (0, 1)]
V = [b(r["V"]) for r in c1r]
fa = lambda col: [1 if (b(r[col]) == 1 and b(r["V"]) == 0) else 0 for r in c1r]  # noqa: E731
ref = fa("D_repairer")
T7 = [("D_repairer", "Repairer's own claim", 27, 13, 48.1, 30.7, 66.0, 48.3, None),
      ("D_judge1", "First juror", 27, 13, 48.1, 30.7, 66.0, 48.3, "1.000"),
      ("D_consensus", "Consensus", 26, 12, 46.2, 28.8, 64.5, 48.3, "1.000"),
      ("D_majority", "Majority", 27, 13, 48.1, 30.7, 66.0, 48.3, "1.000"),
      ("D_unanimous", "Unanimous jury", 26, 12, 46.2, 28.8, 64.5, 48.3, "1.000"),
      ("D_gate", "Confident majority", 19, 7, 36.8, 19.1, 59.0, 41.4, "0.031"),
      ("D_pre_revision", "Pre-revision", 25, 11, 44.0, 26.7, 62.9, 48.3, "0.500"),
      ("D_independent", "Independent vote round 0", 21, 9, 42.9, 24.5, 63.5, 41.4, "0.125")]
for col, lab, cl, fk, fp, fl, fh, sy, p in T7:
    # pre_revision and independent judge the initial patch (V_initial), as fa_metrics.py documents
    vcol = "V_initial" if col in ("D_pre_revision", "D_independent") else "V"
    claims = [r for r in c1r if b(r[col]) == 1]
    fks = sum(1 for r in claims if b(r[vcol]) == 0)
    check(f"R1.{col}.claims", A, "Table 7", f"{lab} claims", cl, len(claims), kind="exact")
    kn_ci(f"R1.{col}.far", A, "Table 7", f"{lab} FAR", fk, cl, f"{fp:.1f}", f"{fl:.1f}", f"{fh:.1f}", fks, len(claims))
    check(f"R1.{col}.safe", A, "Table 7", f"{lab} safe yield (%)", f"{sy:.1f}",
          pct(sum(1 for r in claims if b(r[vcol]) == 1), len(c1r)))
    if p:
        x = [1 if (b(r[col]) == 1 and b(r[vcol]) == 0) else 0 for r in c1r]
        pv, bb, cc = mcnemar_exact(ref, x)
        check(f"R1.{col}.p", A, "Table 7", f"{lab} McNemar p vs repairer (b={bb}, c={cc})", p, pv)
ev = rows("experiments/v4_evigate_confirmation/evigate_stepA/evigate_stepA_cases.csv")
evm = {r["vuln_id"]: r for r in ev}
check("R2.cases", A, "Table 9", "evigate cases == the 29 complete C1 cases", "True", str(set(evm) == {r["vuln_id"] for r in c1r}), kind="exact")
same = all(b(evm[r["vuln_id"]]["V"]) == b(r["V"]) and b(evm[r["vuln_id"]]["D_unanimous"]) == b(r["D_unanimous"])
           and b(evm[r["vuln_id"]]["D_gate"]) == b(r["D_gate"]) for r in c1r)
check("R2.consistent", A, "Table 9", "evigate file V / D_unanimous / D_gate agree with v3 results.csv", "True", str(same), kind="exact")
evc = [r for r in ev if b(r["claim_evidence"]) == 1]
kn_ci("R2.far", A, "Table 7; l.405; abstract", "evigate FAR", 6, 11, "54.5", "28.0", "78.7",
      sum(1 for r in evc if b(r["V"]) == 0), len(evc))
check("R2.safe", A, "Table 7; l.405", "evigate safe yield (%)", "17.2", pct(sum(1 for r in evc if b(r["V"]) == 1), len(ev)))
order = [r["vuln_id"] for r in c1r]
ev_fa = [1 if (b(evm[c]["claim_evidence"]) == 1 and b(evm[c]["V"]) == 0) else 0 for c in order]
un_fa = fa("D_unanimous")
pv, bb, cc = mcnemar_exact(un_fa, ev_fa)
check("R2.p_vs_unanimous", A, "Table 7; l.405", f"evigate McNemar p vs unanimous (b={bb}, c={cc})", "0.031", pv)
check("R2.removed_added", A, "l.405", "vs unanimous: false claims removed / added", "6/0", f"{bb}/{cc}", kind="exact")
un_ok = [1 if (b(r["D_unanimous"]) == 1 and b(r["V"]) == 1) else 0 for r in c1r]
ev_ok = [1 if (b(evm[c]["claim_evidence"]) == 1 and b(evm[c]["V"]) == 1) else 0 for c in order]
check("R2.lost_gained", A, "l.405", "vs unanimous: correct claims lost / gained", "9/0",
      f"{sum(1 for a_, e in zip(un_ok, ev_ok) if a_ and not e)}/{sum(1 for a_, e in zip(un_ok, ev_ok) if e and not a_)}", kind="exact")
cm_fa = fa("D_gate")
cm_ok = [1 if (b(r["D_gate"]) == 1 and b(r["V"]) == 1) else 0 for r in c1r]
check("R2.vs_confident", A, "l.405", "vs confident majority: FA removed / added / correct lost / gained", "4/3/8/1",
      f"{sum(1 for a_, e in zip(cm_fa, ev_fa) if a_ and not e)}/{sum(1 for a_, e in zip(cm_fa, ev_fa) if e and not a_)}/"
      f"{sum(1 for a_, e in zip(cm_ok, ev_ok) if a_ and not e)}/{sum(1 for a_, e in zip(cm_ok, ev_ok) if e and not a_)}", kind="exact")
T9 = {"verified": (5, 6), "bypass": (3, 1), "not_blocked": (2, 2), "no_functional_evidence": (2, 2), "not_reproduced": (1, 2),
      "env_failed": (1, 1), "regression": (0, 1)}
for st, (kc, kw) in T9.items():
    got = (sum(1 for r in ev if r["status"] == st and b(r["V"]) == 1), sum(1 for r in ev if r["status"] == st and b(r["V"]) == 0))
    check(f"R3.{st}", A, "Table 9", f"evigate status {st}: correct/wrong", f"{kc}/{kw}", f"{got[0]}/{got[1]}", kind="exact")
secs = [float(r["seconds"]) for r in ev]
check("R3.hours", A, "l.405", "evigate tool time (h)", "5.75", sum(secs) / 3600)
check("R3.median", A, "l.405", "evigate median seconds per patch", "656", statistics.median(secs))
# Table 8 (protocol behaviour): the caption says 29 complete attempts each; check both scopes
allc = {g: [r for r in v3 if r["agent"] == g] for g in ("c0", "c0g", "c1")}
comp = {g: [r for r in allc[g] if r["status"] == "complete"] for g in allc}
check("R4.abstain", A, "Table 8; l.358", "C1 abstentions (complete)", 3, sum(b(r["abstained"]) == 1 for r in comp["c1"]), kind="exact")
res = Counter(r["resolved_in"] for r in comp["c1"])
check("R4.resolved", A, "Table 8; l.358", "C1 resolved independent/debate/after revision (complete)", "21/5/0",
      f"{res['independent']}/{res['debate']}/{res['after_revision']}", kind="exact")
res_all = Counter(r["resolved_in"] for r in allc["c1"])
check("R4.resolved_all", A, "l.358 'a revision reached unanimity only in the excluded orjson case'",
      "C1 attempts resolved after a revision, all 30 attempts", "1 CVE-2024-27454",
      f"{res_all['after_revision']} {','.join(r['vuln_id'] for r in allc['c1'] if r['resolved_in'] == 'after_revision')}", kind="exact")
for g, rep in (("c0g", "3 (2)"), ("c1", "2 (2)")):
    s_comp = f"{sum(b(r['gate_failed_versions']) or 0 for r in comp[g])} ({sum(b(r['gate_rescued']) or 0 for r in comp[g])})"
    s_all = f"{sum(b(r['gate_failed_versions']) or 0 for r in allc[g])} ({sum(b(r['gate_rescued']) or 0 for r in allc[g])})"
    check(f"R4.gate.{g}", A, "Table 8", f"{g} gate rejections (rescued), 29 complete attempts", rep, s_comp, kind="exact",
          note=f"over all 30 attempts: {s_all}")
for g, rep in (("c0", "0 of 300"), ("c0g", "2 of 322"), ("c1", "1 of 1535")):
    s_comp = f"{sum(b(r['cites_rejected']) or 0 for r in comp[g])} of {sum(b(r['cites_total']) or 0 for r in comp[g])}"
    s_all = f"{sum(b(r['cites_rejected']) or 0 for r in allc[g])} of {sum(b(r['cites_total']) or 0 for r in allc[g])}"
    check(f"R4.cites.{g}", A, "Table 8; l.358", f"{g} quotes of code that does not exist, 29 complete attempts", rep, s_comp,
          kind="exact", note=f"over all 30 attempts: {s_all}")
for g, rep in (("c0", "16 / 16"), ("c0g", "14 / 14"), ("c1", "14 / 14")):
    check(f"R4.cand.{g}", A, "Table 8; l.358", f"{g} cases with a correct candidate / selected", rep,
          f"{sum(b(r['V_any_candidate']) or 0 for r in comp[g])} / {sum(b(r['jury_picked_correct']) or 0 for r in comp[g])}", kind="exact")
    check(f"R4.refused.{g}", A, "Table 8", f"{g} refusals", 0, sum(b(r["refused"]) or 0 for r in allc[g]), kind="exact")
calls3 = rows("results/logs/calls/calls_v3_main.csv")
for g, rep in (("c0", 30), ("c0g", 35), ("c1", 215)):
    check(f"R4.calls.{g}", A, "Table 8", f"{g} model calls", rep, sum(r["agent"] == g for r in calls3), kind="exact",
          note="counts the calls of all 30 attempted cases")
for g, rep in (("c0", 114), ("c0g", 98), ("c1", 453)):
    med_c = statistics.median(float(r["L_api_total_ms"]) / 1000 for r in comp[g])
    med_a = statistics.median(float(r["L_api_total_ms"]) / 1000 for r in allc[g])
    check(f"R4.api.{g}", A, "Table 8 (caption: API time counts all 30 attempted cases)", f"{g} median API time per case (s), 30 attempted",
          rep, med_a, tol=0.5 + 1e-9, note=f"over the 29 complete attempts: {med_c:.1f}")

# =============================================================================================== 6. coverage rule
A = "Hint-coverage rule (Table 10, Fig. 8, Sec. 4.7, abstract)"
cr = [r for r in v4 if r["agent"] == "c0" and r["status"] == "complete" and b(r["V"]) in (0, 1) and b(r["D_repairer"]) == 1]
undefined = [r["vuln_id"] for r in cr if (r["hint_coverage"] or "").strip() in ("", "None")]
check("C1.undefined", A, "confirm_v4.json", "claims with undefined hint coverage", 0, len(undefined), kind="exact")
corr = [r for r in cr if b(r["V"]) == 1]
wrong = [r for r in cr if b(r["V"]) == 0]
for col, lab, kc_rep, kw_rep, far_rep, flo, fhi, p_rep in (("D_coverage", "coverage (primary)", 12, 11, "47.8", "29.2", "67.0", "0.024"),
                                                          ("D_coverage75", "coverage75", 14, 13, "48.1", "30.7", "66.0", "0.011")):
    kc = sum(b(r[col]) == 1 for r in corr)
    kw = sum(b(r[col]) == 1 for r in wrong)
    check(f"C1.{col}.pass_correct", A, "Table 10; l.431", f"{lab}: correct claims kept", f"{kc_rep}/21", f"{kc}/{len(corr)}", kind="exact")
    check(f"C1.{col}.pass_wrong", A, "Table 10; l.431", f"{lab}: wrong claims kept", f"{kw_rep}/40", f"{kw}/{len(wrong)}", kind="exact")
    kn_ci(f"C1.{col}.far", A, "Table 10; Fig. 8", f"{lab}: FAR with the rule", kw_rep, kc_rep + kw_rep, far_rep, flo, fhi, kw, kc + kw)
    check(f"C1.{col}.p", A, "Table 10; abstract", f"{lab}: one-sided Fisher p", p_rep, fisher_greater(kc, len(corr), kw, len(wrong)))
kc = sum(b(r["D_coverage"]) == 1 for r in corr)
kw = sum(b(r["D_coverage"]) == 1 for r in wrong)
check("C2.p4", A, "l.431", "primary one-sided Fisher p (4 decimals)", "0.0237", fisher_greater(kc, len(corr), kw, len(wrong)))
d, lo, hi = newcombe_hybrid(kc, len(corr), kw, len(wrong))
check("C2.diff", A, "l.431", "pass-rate difference", "0.30", d)
check("C2.lo", A, "l.431", "Newcombe hybrid low", "0.04", lo)
check("C2.hi", A, "l.431", "Newcombe hybrid high", "0.51", hi)
check("C2.rates", A, "l.431", "pass rates (%) correct / wrong", "57.1/27.5", f"{pct(kc, len(corr)):.1f}/{pct(kw, len(wrong)):.1f}", kind="exact")
check("C2.removed", A, "l.431; Discussion", "false assurances removed / correct claims lost", "29/9", f"{len(wrong) - kw}/{len(corr) - kc}", kind="exact")
n63 = len([r for r in v4 if r["status"] == "complete" and b(r["V"]) in (0, 1)])
check("C2.safe", A, "l.431", "safe yield (%) repairer -> rule", "33.3 -> 19.0", f"{pct(len(corr), n63):.1f} -> {pct(kc, n63):.1f}", kind="exact")
kc75 = sum(b(r["D_coverage75"]) == 1 for r in corr)
check("C2.lost75", A, "l.431", "coverage75: correct claims lost", 7, len(corr) - kc75, kind="exact")
# discovery rows: recorded in prereg/decisiones_v4.txt (hallazgo); per-case hint coverage of v3 is not in the repository
dv4 = (ROOT / "prereg/decisiones_v4.txt").read_text(encoding="utf-8")
hall = next(l for l in dv4.splitlines() if l.startswith("hallazgo="))
for g, claim_rep, fa_rep, kept_rep, kept_fa_rep, p_rep in (("C0", 28, 12, 12, 3, "0.102"), ("C0g", 28, 14, 13, 5, "0.225"),
                                                           ("C1", 27, 13, 11, 2, "0.013")):
    m = re.search(rf"\b{g} (?:FAR )?(\d+)/(\d+) = [\d,]+ % -> (\d+)/(\d+)", hall)
    agent = {"C0": "c0", "C0g": "c0g", "C1": "c1"}[g]
    a = arm(v3, agent, "D_repairer")
    check(f"C3.{g}.claims", A, "Table 10 discovery", f"{g}: repairer claims / false (results.csv)", f"{claim_rep}/{fa_rep}",
          f"{a['claims']}/{a['fa']}", kind="exact")
    check(f"C3.{g}.prereg", A, "Table 10 discovery", f"{g}: FAR before -> with rule, as recorded in decisiones_v4",
          f"{fa_rep}/{claim_rep} -> {kept_fa_rep}/{kept_rep}", f"{m.group(1)}/{m.group(2)} -> {m.group(3)}/{m.group(4)}", kind="exact")
    kc_d, kw_d = kept_rep - kept_fa_rep, kept_fa_rep
    check(f"C3.{g}.p", A, "Table 10 discovery", f"{g}: one-sided Fisher p (from the recorded counts)", p_rep,
          fisher_greater(kc_d, claim_rep - fa_rep, kw_d, fa_rep))
check("C3.v3_hint_coverage", A, "Table 10 discovery", "per-case hint coverage of the v3 patches in the repository", "present",
      "absent" if "hint_coverage" not in v3[0] else "present", kind="open",
      note="discovery rows come from the summary recorded in decisiones_v4.txt; they cannot be recomputed per case")
pw = re.search(r"post hoc del C0, ([\d,]+) con 65 casos.*?mitad de esa diferencia, ([\d,]+)", dv4)
check("C4.power", A, "Sec. 3.7; Limitations", "power 0.73 / 0.26 (decisiones_v4)", "0.73/0.26",
      f"{pw.group(1).replace(',', '.')}/{pw.group(2).replace(',', '.')}", kind="exact")
# interim analysis (deviation): the 3 cases evaluated last, from the console order
log = (ROOT / "results/logs/console/v4_confirm_c0.log").read_text(encoding="utf-8", errors="replace")
evals = re.findall(r"\[eval\] c0/([\w-]+):", log)
last = []
done_ids = {r["vuln_id"] for r in cr} | {r["vuln_id"] for r in v4 if r["status"] == "complete"}
for cid in reversed(evals):
    if cid in done_ids and cid not in last:
        last.append(cid)
    if len(last) == 3:
        break
cr60 = [r for r in cr if r["vuln_id"] not in last]
n60 = len([r for r in v4 if r["status"] == "complete" and r["vuln_id"] not in last])
c60 = [r for r in cr60 if b(r["V"]) == 1]
w60 = [r for r in cr60 if b(r["V"]) == 0]
p60 = fisher_greater(sum(b(r["D_coverage"]) == 1 for r in c60), len(c60), sum(b(r["D_coverage"]) == 1 for r in w60), len(w60))
check("C5.interim", A, "l.431 deviation", f"interim analysis without the 3 cases evaluated last ({', '.join(last)}): N / p",
      "60 / 0.022", f"{n60} / {p60:.3f}", kind="exact", note="reconstructed from the evaluation order in the console log")

# =============================================================================================== 7. calls and cost
A = "Calls, tokens and cost (Tables 12-14, Figs. 9-10, Sec. 4.9)"
files = {"v0": "calls_v0_mvp.csv", "v2": "calls_v2_pilot.csv", "v3": "calls_v3_main.csv", "v4": "calls_v4_confirm.csv", "v5dev": "calls_v5_dev.csv",
         "v5": "calls_v5.csv"}
C = {k: rows(f"results/logs/calls/{f}") for k, f in files.items()}
maxdiff = 0.0
for k, rs in C.items():
    for r in rs:
        if r["model"].startswith("nvidia") or r["model"].startswith("poolside") or k == "v0":
            continue
        maxdiff = max(maxdiff, abs(list_cost(r["model"], int(r["input_tokens"]), int(r["output_tokens"])) - float(r["list_cost_usd"] or 0)))
check("$0.rowcost", A, "results/logs/calls/*.csv", "max |list_cost_usd - tokens x models.json prices| over all calls (USD)", 0, maxdiff, tol=1e-5)
check("$0.status", A, "Fig. 9 uses status ok", "calls with status other than ok", 0, sum(r["status"] != "ok" for rs in C.values() for r in rs), kind="exact")
T12 = {"v0": (5, 18989, 845, "0.23", 0.0, None, None), "v2": (117, 1283730, 986284, "2.35", "7.22", "2.48", "1.57"),
       "v3": (280, 8105924, 2356785, "6.87", "34.40", "27.60", "15.70"), "v4": (65, 848338, 442252, "1.70", "6.12", None, None),
       "v5dev": (10, 138975, 220165, "0.24", "0.12", "0.14", "0.12"), "v5": (190, 4604832, 4385390, "4.68", "4.15", "5.33", "4.15")}
for k, (n, tin, tout, h, cost, cl_rep, cl_list) in T12.items():
    rs = C[k]
    check(f"$1.{k}.calls", A, "Table 12", f"{k} calls", n, len(rs), kind="exact")
    check(f"$1.{k}.tokens", A, "Table 12", f"{k} tokens in/out", f"{tin}/{tout}",
          f"{sum(int(r['input_tokens']) for r in rs)}/{sum(int(r['output_tokens']) for r in rs)}", kind="exact")
    check(f"$1.{k}.hours", A, "Table 12", f"{k} summed call time (h)", h, sum(float(r["latency_s"]) for r in rs) / 3600)
    if k != "v0":
        check(f"$1.{k}.list", A, "Table 12", f"{k} list price (USD)", cost, sum(float(r["list_cost_usd"] or 0) for r in rs))
    if cl_rep:
        cla = [r for r in rs if r["model"].startswith("claudecode")]
        check(f"$1.{k}.client", A, "Table 12", f"{k} client report for Claude calls", cl_rep, sum(float(r["api_equivalent_usd"] or 0) for r in cla))
        check(f"$1.{k}.client_list", A, "Table 12", f"{k} list price of the same Claude calls", cl_list, sum(float(r["list_cost_usd"] or 0) for r in cla))
total_list = sum(float(r["list_cost_usd"] or 0) for k in ("v2", "v3", "v4", "v5dev") for r in C[k]) + sum(costs.values())
check("$1.total497", A, "l.482", "calls of v2-v4 + v5 dev incl. calibration", 497, sum(len(C[k]) for k in ("v2", "v3", "v4", "v5dev")) + 25, kind="exact")
check("$1.total_cost", A, "l.482", "their cost at list price (USD)", "50.0", total_list)
names = {"gpt-6.2-sol": "GPT-6.2 Sol", "claude-opus-5-5": "Claude Opus 5.5", "deepseek-v4-pro": "DeepSeek V4 Pro",
         "claude-sonnet-5-5": "Claude Sonnet 5.5", "gpt-5.4-mini": "GPT-5.4 mini", "gpt-6.1-sol": "GPT-6.1 Sol",
         "gpt-6.1-terra": "GPT-6.1 Terra", "gpt-6-luna": "GPT-6 Luna", "claude-haiku-5-5": "Claude Haiku 5.5",
         "poolside/laguna-xs-2.1": "laguna-xs-2.1"}
role = {"reviewer": "juror", "repairer": "repairer", "analyst": "analyst"}
G = defaultdict(list)
for rs in C.values():
    for r in rs:
        G[(names[r["model"].split(":", 1)[-1]], role[r["role"]])].append(r)
T13 = [("GPT-6.2 Sol", "repairer", 193, 3361372, 1336030, "91.7", "20.08", None), ("Claude Opus 5.5", "juror", 57, 2134275, 169842, "26.4", "11.93", "20.47"),
       ("DeepSeek V4 Pro", "juror", 57, 1406726, 1284226, "193.6", "6.94", None), ("Claude Sonnet 5.5", "juror", 57, 2139020, 105212, "13.4", "5.33", "9.61"),
       ("GPT-5.4 mini", "repairer", 22, 210005, 365519, "72.8", "1.80", None), ("GPT-6.1 Sol", "juror", 12, 132328, 81999, "111.0", "1.08", None),
       ("GPT-6.1 Terra", "juror", 12, 135380, 29568, "39.9", "0.28", None), ("GPT-6 Luna", "analyst", 40, 584093, 353525, "57.3", "0.24", None),
       ("GPT-6 Luna", "juror", 12, 134793, 59400, "36.3", "0.04", None), ("Claude Haiku 5.5", "repairer", 200, 4743807, 4605555, "74.9", "4.28", "5.47"),
       ("laguna-xs-2.1", "repairer", 5, 18989, 845, "49.7", "0", None)]
check("$2.groups", A, "Table 13; Fig. 9", "model-role groups in the call logs", len(T13), len(G), kind="exact")
for m, ro, n, tin, tout, lat, cost, client_ in T13:
    rs = G[(m, ro)]
    tag = f"{m} ({ro})"
    check(f"$2.{tag}.calls", A, "Table 13; Fig. 9 n", f"{tag} calls", n, len(rs), kind="exact")
    check(f"$2.{tag}.tokens", A, "Table 13", f"{tag} tokens in/out", f"{tin}/{tout}",
          f"{sum(int(r['input_tokens']) for r in rs)}/{sum(int(r['output_tokens']) for r in rs)}", kind="exact")
    check(f"$2.{tag}.lat", A, "Table 13; Fig. 9 median", f"{tag} median latency (s)", lat, statistics.median(float(r["latency_s"]) for r in rs))
    check(f"$2.{tag}.cost", A, "Table 13", f"{tag} list price (USD)", cost, sum(float(r["list_cost_usd"] or 0) for r in rs))
    if client_:
        check(f"$2.{tag}.client", A, "Table 13; l.238", f"{tag} client report (USD)", client_, sum(float(r["api_equivalent_usd"] or 0) for r in rs))
allrows = [r for rs in C.values() for r in rs]
check("$2.total", A, "Table 13 total", "calls / tokens in / tokens out", "667/15000788/8391721",
      f"{len(allrows)}/{sum(int(r['input_tokens']) for r in allrows)}/{sum(int(r['output_tokens']) for r in allrows)}", kind="exact")
check("$2.total_cost", A, "Table 13 total", "list price total (USD)", "52.02", sum(float(r["list_cost_usd"] or 0) for r in allrows))
rsum = sum(float(x[6]) for x in T13)
check("$2.rounding", A, "Table 13 total and caption", "printed total vs sum of the rounded rows (within 0.005 per row; caption notes rounding)",
      "52.02", rsum, tol=0.005 * len(T13) + 1e-9, note=f"rows sum to {rsum:.2f}; caption note present: "
      f"{'do not add up exactly to the total because of rounding' in (ROOT / 'papers/final/paper/main.tex').read_text(encoding='utf-8')}")
dsk = G[("DeepSeek V4 Pro", "juror")]
check("$3.ds_out", A, "l.482", "DeepSeek V4 Pro mean output tokens per call (about 22,500)", 22500,
      statistics.fmean(int(r["output_tokens"]) for r in dsk), tol=100)
for m in ("claude-opus-5-5", "claude-sonnet-5-5"):
    rs = [r for r in C["v3"] if r["model"].endswith(m) and r["agent"] == "c1"]
    check(f"$3.{m}.v3mean_in", A, "l.482 'more than 41,000 input tokens per call'", f"{m}: mean input tokens per call in C1 of v3 (> 41000)",
          "True", str(statistics.fmean(int(r["input_tokens"]) for r in rs) > 41000), kind="exact",
          note=f"mean {statistics.fmean(int(r['input_tokens']) for r in rs):,.0f} over {len(rs)} calls; over all 57 calls "
               f"{statistics.fmean(int(r['input_tokens']) for r in G[(names[m], 'juror')]):,.0f}")
mr3 = {g: arm(v3, g, "D_repairer") for g in ("c0", "c0g", "c1")}
T14 = {"c0": ("3.32", "0.111", "0.208"), "c0g": ("3.68", "0.123", "0.263"), "c1": ("27.40", "0.913", "1.957")}
for g, (cost, per_case, per_rep) in T14.items():
    cg = sum(float(r["list_cost_usd"] or 0) for r in C["v3"] if r["agent"] == g)
    att = sum(r["agent"] == g for r in v3)
    check(f"$4.{g}.cost", A, "Table 14; l.482", f"{g} cost (USD)", cost, cg)
    check(f"$4.{g}.case", A, "Table 14; Fig. 10", f"{g} per attempted case (/{att})", per_case, cg / att)
    check(f"$4.{g}.rep", A, "Table 14; Fig. 10; abstract", f"{g} per verified repair (/{mr3[g]['v']})", per_rep, cg / mr3[g]["v"])
c4 = sum(float(r["list_cost_usd"] or 0) for r in C["v4"])
check("$4.conf.case", A, "Table 14", "confirmation per attempted case (/65)", "0.094", c4 / 65)
check("$4.conf.rep", A, "Table 14; l.482", "confirmation per verified repair (/22)", "0.278", c4 / 22)
check("$4.ratio", A, "l.482; Discussion; Conclusions", "C1 / C0 per verified repair (9.4x)", "9.4",
      (T14_c1 := sum(float(r["list_cost_usd"] or 0) for r in C["v3"] if r["agent"] == "c1") / 14) /
      (sum(float(r["list_cost_usd"] or 0) for r in C["v3"] if r["agent"] == "c0") / 16))
check("$4.c0_v3v4", A, "Sec. 3.8", "C0 per verified repair over v3+v4 (about 0.25)", "0.25",
      (sum(float(r["list_cost_usd"] or 0) for r in C["v3"] if r["agent"] == "c0") + c4) / 38)
for mm, rep in (("claude-opus-5-5", "10.83"), ("deepseek-v4-pro", "5.96"), ("gpt-6.2-sol", "5.56"), ("claude-sonnet-5-5", "4.87"), ("gpt-6-luna", "0.18")):
    check(f"$5.{mm}", A, "Table 14 caption", f"C1 cost of {mm}", rep,
          sum(float(r["list_cost_usd"] or 0) for r in C["v3"] if r["agent"] == "c1" and r["model"].endswith(mm)))
check("$6.price_ratio", A, "RQ4; Sec. 3.8", "GPT-6.2 Sol / Claude Haiku 5.5 price per token (20x)", "20",
      MODELS["openai:gpt-6.2-sol"]["price_in"] / MODELS["claudecode:claude-haiku-5-5"]["price_in"], tol=1e-9)
T3 = {"openai:gpt-6.2-sol": "2.00/10.00", "openai:gpt-5.4-mini": "0.75/4.50", "openai:gpt-6-luna": "0.10/0.50", "openai:gpt-6.1-sol": "2.00/10.00",
      "openai:gpt-6.1-terra": "1.00/5.00", "openai:gpt-6.2-astra": "8.00/40.00", "claudecode:claude-opus-5-5": "4.00/20.00",
      "claudecode:claude-sonnet-5-5": "2.00/10.00", "claudecode:claude-haiku-5-5": "0.10/0.50", "deepseek:deepseek-v4-pro": "1.32/3.96",
      "deepseek:deepseek-flash": "0.30/1.20"}
for m, rep in T3.items():
    check(f"$7.{m}", A, "Table 3", f"{m} price in/out", rep, f"{MODELS[m]['price_in']:.2f}/{MODELS[m]['price_out']:.2f}", kind="exact")

# =============================================================================================== 8. v5 development check and knowledge base
A = "v5 development check and knowledge base (Table 11, Sec. 3.8, 4.8)"
dv = rows("experiments/v5_rag/dev_gate/results.csv")
c5 = rows("results/logs/calls/calls_v5_dev.csv")
for g, cost, per in (("c0m", "0.059", "0.029"), ("c0mr", "0.065", "0.033")):
    a = arm(dv, g, "D_repairer")
    check(f"V1.{g}.vrr", A, "Table 11; l.459", f"{g} VRR", "2/5", f"{a['v']}/{a['n']}", kind="exact")
    check(f"V1.{g}.far", A, "Table 11; l.459", f"{g} FAR", "2/4", f"{a['fa']}/{a['claims']}", kind="exact")
    cg = sum(float(r["list_cost_usd"] or 0) for r in c5 if r["agent"] == g)
    check(f"V1.{g}.cost", A, "Table 11", f"{g} cost (USD)", cost, cg)
    check(f"V1.{g}.per", A, "Table 11", f"{g} per verified repair", per, cg / a["v"])
check("V1.total", A, "l.459", "ten calls at list price (USD)", "0.124", sum(float(r["list_cost_usd"] or 0) for r in c5))
a = arm(dv, "c0m", "D_repairer")
check("V1.c0m_broke", A, "l.459", "M without retrieval: patches that did not apply or broke functionality", 1,
      sum(1 for r in a["rows"] if b(r["A"]) == 0 or b(r["F"]) == 0), kind="exact")
toks = []
leak = []
for f in sorted(glob.glob(str(ROOT / "experiments/v5_rag/dev_gate/c0mr/*/llm_response.json"))):
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    s = json.dumps(d)
    toks += [int(x) for x in re.findall(r'"section_tokens_est": (\d+)', s)]
    leak += re.findall(r'"leak(?:age)?_flag(?:ged)?": (true|false)', s)
check("V2.tokens", A, "l.459", "retrieval section tokens, min-max", "585-1269", f"{min(toks)}-{max(toks)}" if toks else "n/a", kind="exact")
check("V2.leak", A, "l.459", "cases flagged by the leakage audit", 0, sum(x == "true" for x in leak), kind="exact",
      note=f"{len(leak)} leakage flags found in the records")
nchunks = sum(1 for _ in open(ROOT / "experiments/v5_rag/kb_rag_r_v1/chunks.jsonl", encoding="utf-8"))
check("V3.chunks", A, "Sec. 3.8", "knowledge-base chunks", 913, nchunks, kind="exact")
cm = json.loads((ROOT / "experiments/v5_rag/kb_rag_r_v1/cwe_map.json").read_text())
check("V3.cwe", A, "Sec. 3.8", "cases with at least one CWE", 98, sum(1 for v in cm.values() if v.get("cwe")), kind="exact")
dv5 = (ROOT / "prereg/decisiones_v5.txt").read_text(encoding="utf-8")
check("V4.power", A, "Sec. 3.8", "H1 exact power with 94 cases: 0.65 (+10) and 0.20 (+4)", "True",
      str(bool(re.search(r"exacta con 94 casos: 0,65.*0,20 con \+4", dv5))), kind="exact")

# =============================================================================================== 9. methods facts
A = "Methods facts (Tables 1 and 3, Secs. 3.2-3.5)"
for m in T3:
    rep = {"openai:gpt-6.2-sol": "high", "openai:gpt-5.4-mini": "high", "openai:gpt-6-luna": "medium", "openai:gpt-6.1-sol": "high",
           "openai:gpt-6.1-terra": "medium", "openai:gpt-6.2-astra": "high", "claudecode:claude-opus-5-5": "medium",
           "claudecode:claude-sonnet-5-5": "medium", "claudecode:claude-haiku-5-5": "high", "deepseek:deepseek-v4-pro": "high",
           "deepseek:deepseek-flash": "high"}[m]
    check(f"X1.{m}", A, "Table 3", f"{m} effort", rep, MODELS[m].get("reasoning_effort"), kind="exact")
check("X1.haiku_note", A, "Table 3 caption", "Haiku 5.5 0.50/2.50 above 100k prompt tokens (models.json note)", "True",
      str("0.50/2.50 above" in MODELS["_note"]), kind="exact")
check("X2.v3_models", A, "Sec. 3.5", "v3 repairer / C1 analyst", "openai:gpt-6.2-sol / openai:gpt-6-luna",
      f"{','.join(sorted({r['repairer_model'] for r in v3}))} / {','.join(sorted({r['analyst_model'] for r in v3 if r['agent'] == 'c1'}))}", kind="exact")
wrong_v2 = [r for r in pil if r["agent"] == "c1v2" and b(r["V"]) == 0]
check("X2.c1v2_wrong", A, "l.265", "C1 pilot 2: how the two wrong patches were accepted", "after_revision,debate",
      ",".join(sorted(r["resolved_in"] for r in wrong_v2)), kind="exact")
envtxt = (ROOT / "experiments/v1_environment/environment.txt").read_text(encoding="utf-8")
check("X3.cpus", A, "Introduction (two-vCPU machine)", "cpus of the instance", "2", re.search(r"cpus: (\d+)", envtxt).group(1), kind="exact")
check("X3.credit", A, "Sec. 3.4", "credit ran out 25 Nov 11:41 UTC (decisiones_v2)", "True",
      str("25 nov, 11:41 UTC" in (ROOT / "prereg/decisiones_v2.txt").read_text(encoding="utf-8")), kind="exact")
for k, rs, rep in (("v2", pil, "2026-11-25"), ("v3", v3, "2026-11-25"), ("v4", v4, "2026-11-26"), ("v5dev", dv, "2026-11-26")):
    days = sorted({r["generated_at_utc"][:10] for r in rs if r.get("generated_at_utc")})
    check(f"X4.{k}", A, "Tables 1 and 3 (dates)", f"{k} generation dates (UTC)", rep, ",".join(days), kind="exact")
check("X4.v0", A, "Table 1", "v0 dates in the v0 report", "True",
      str("October 12" in (ROOT / "experiments/v0_mvp/REPORT_v0.md").read_text(encoding="utf-8") and
          "October 14" in (ROOT / "experiments/v0_mvp/REPORT_v0.md").read_text(encoding="utf-8")), kind="exact")
v5ids = set((ROOT / "prereg/v5_ids.txt").read_text().split())
check("X6.v5_ids", A, "Table 1; Sec. 3.8", "v5 cases = main sample + confirmation (95)", "True 95",
      f"{v5ids == ids['main_ids.txt'] | ids['confirm65_ids.txt']} {len(v5ids)}", kind="exact")
check("X6.context", A, "Sec. 3.3 'every case fitted whole'", "rows with context_mode other than full (v3, v4, v5 dev)", 0,
      sum(r["context_mode"] != "full" for r in v3 + v4 + dv), kind="exact")
check("X6.refused", A, "Sec. 4.5; 4.8; 3.4", "refusals in v3, v4, v5 dev and calibration v2", 0,
      sum(int(r["refused"] or 0) for r in v3 + v4 + dv) + sum(int(r["refused"] or 0) for r in rows("experiments/v2_pilot_tournament/judge_calibration_v2/judge_calibration.csv")), kind="exact")
med = {k: statistics.median(float(r["latency_s"]) for r in rs) for k, rs in G.items()}
mout = {k: statistics.fmean(int(r["output_tokens"]) for r in rs) for k, rs in G.items()}
check("X6.slowest", A, "l.482", "model with the highest median latency", "DeepSeek V4 Pro", max(med, key=med.get)[0], kind="exact")
top2 = sorted(mout, key=mout.get, reverse=True)[:2]
check("X6.most_out", A, "Sec. 4.9", "the two models with the most output tokens per call (about 23,000 and 22,500)",
      "Claude Haiku 5.5 23000, DeepSeek V4 Pro 22500", ", ".join(f"{k[0]} {round(mout[k], -2):.0f}" for k in top2), kind="exact",
      note="rounded to hundreds; the text says about 22,500 and 23,000")
check("X6.gate3", A, "l.459", "feasibility-gate threshold (decisiones_v5)", "True", str("en 3 o más" in dv5), kind="exact")
check("X5.v4_lost", A, "l.431; Limitations", "v4 lost cases documented (tornado timeout; API key)", "True",
      str("tornado" in (ROOT / "experiments/v4_evigate_confirmation/README.md").read_text(encoding="utf-8") and
          "API key" in (ROOT / "experiments/v4_evigate_confirmation/README.md").read_text(encoding="utf-8")), kind="exact",
      note="results.csv only says 'oracle invalid here'; the causes are documented in the README and the console log")

# =============================================================================================== 9b. released records
A = "Released case records (v0, v2-v5)"
v0runs = [d for d in (ROOT / "experiments/v0_mvp/runs/official/gpt").iterdir() if d.is_dir()]
REC = {"v2": ("experiments/v2_pilot_tournament/pilot", "experiments/v2_pilot_tournament/results.csv",
              ["rep_gpt-5.4-mini", "rep_gpt-6.2-sol", "c1", "c1v2"], ids["pilot_ids.txt"]),
       "v3": ("experiments/v3_main/final", "experiments/v3_main/results.csv", ["c0", "c0g", "c1"], ids["main_ids.txt"]),
       "v4": ("experiments/v4_evigate_confirmation/confirm", "experiments/v4_evigate_confirmation/confirm/results.csv", ["c0"],
              ids["confirm65_ids.txt"]),
       "v5dev": ("experiments/v5_rag/dev_gate", "experiments/v5_rag/dev_gate/results.csv", ["c0m", "c0mr"], ids["pilot_ids.txt"]),
       "v5": ("experiments/v5_rag/main", "experiments/v5_rag/results.csv", ["c0", "c0m", "c0mr"], v5ids)}
nrec, nfiles, badfile, npatch, badpatch, nv, badv, ncase_bad, nanswers = Counter(), 0, [], 0, [], 0, [], [], Counter()
for ver, (base, res, arms, expected) in REC.items():
    rrows = {(r["agent"], r["vuln_id"]): r for r in rows(res)}
    for arm_ in arms:
        cases = {d.name for d in (ROOT / base / arm_).iterdir() if d.is_dir()}
        if cases != expected:
            ncase_bad.append(f"{ver}/{arm_}")
        for c in sorted(cases):
            d = ROOT / base / arm_ / c
            rec = json.loads((d / "llm_response.json").read_text(encoding="utf-8"))
            nrec[ver] += 1
            nanswers[ver] += any(f.suffix == ".md" and f.name != "rag_section.md" for f in d.iterdir())
            for fn, h in rec.get("sha256", {}).items():
                if fn == "context.md":
                    continue                                   # prompts are not released; their hash is
                f = d / fn
                nfiles += 1
                if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != h:
                    badfile.append(f"{ver}/{arm_}/{c}/{fn}")
            r = rrows.get((arm_, c))
            if r and r["patch_sha256"] and (d / "patch.diff").exists():
                npatch += 1
                if hashlib.sha256((d / "patch.diff").read_bytes()).hexdigest() != r["patch_sha256"]:
                    badpatch.append(f"{ver}/{arm_}/{c}")
            ev = json.loads((d / "eval.json").read_text(encoding="utf-8")) if (d / "eval.json").exists() else {}
            if r and r["V"] not in ("", None) and ev.get("apply_ok") is not None:
                nv += 1
                if int(float(r["V"])) != int(bool(ev["apply_ok"]) and bool(ev["func_ok"]) and bool(ev["exploit_ok"])):
                    badv.append(f"{ver}/{arm_}/{c}")
check("X7.released", A, "Sec. 3.10; Data availability", "case records in the repo: v0 / v2 / v3 / v4 / v5 dev / v5", "5/20/90/65/10/285",
      f"{len(v0runs)}/{nrec['v2']}/{nrec['v3']}/{nrec['v4']}/{nrec['v5dev']}/{nrec['v5']}", kind="exact")
check("X7.answers", A, "Sec. 3.10", "case records that include the model answers (v2 / v3 / v4 / v5 dev / v5)", "20/90/65/10/285",
      f"{nanswers['v2']}/{nanswers['v3']}/{nanswers['v4']}/{nanswers['v5dev']}/{nanswers['v5']}", kind="exact")
check("X7.cases", A, "Table 1", "arms whose released cases differ from the prereg lists", 0, len(ncase_bad), kind="exact", note="; ".join(ncase_bad))
check("X7.filehash", A, "llm_response.json sha256 maps", f"released files whose sha256 differs from their record (of {nfiles})", 0,
      len(badfile), kind="exact", note="; ".join(badfile[:20]))
check("X7.patch", A, "results.csv patch_sha256", f"patch.diff files whose sha256 differs from results.csv (of {npatch})", 0, len(badpatch),
      kind="exact", note="; ".join(badpatch))
check("X7.verdict", A, "results.csv V", f"eval.json verdicts that differ from results.csv (of {nv})", 0, len(badv), kind="exact",
      note="; ".join(badv))
# a PEM header counts only with key material after it: the jurors of PyJWT CVE-2022-29217 discuss the bare headers
keypat = re.compile(r"sk-ant-|sk-proj-|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|xox[abp]-|"
                    r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:\\n|\s)+[A-Za-z0-9+/=]{40,}")
leaks = [str(f.relative_to(ROOT)) for base in [v[0] for v in REC.values()] for f in (ROOT / base).rglob("*")
         if f.is_file() and f.suffix in (".md", ".diff", ".json") and keypat.search(f.read_text(encoding="utf-8", errors="replace"))]
check("X7.keys", A, "Data availability 'No API keys are included'", "released files with an API-key pattern", 0, len(leaks), kind="exact",
      note="; ".join(leaks[:10]))
tx = (ROOT / "papers/final/paper/main.tex").read_text(encoding="utf-8")
check("X7.statement", A, "Sec. 3.10; Data availability", "the paper states what is released (answers, patches, evaluation, call records)", "True",
      str("the answers of every model, the patches, their evaluation and the record of every call" in tx and
          "evidence packages" not in tx), kind="exact")

# =============================================================================================== 9c. v5 main run
A = "v5 main run (Tables 10-14, Fig. 7, Sec. 4.8-4.9, abstract, discussion)"
import numpy as np  # noqa: E402


def newcombe_paired(a, b_, c, d):
    """p1 - p2 for paired 0/1 data with a = both, b_ = only the first, c = only the second, d = neither
    (Newcombe 1998, method 10, Wilson bounds from root finding)."""
    n = a + b_ + c + d
    p1, p2 = (a + b_) / n, (a + c) / n
    l1, u1 = wilson_root(a + b_, n)
    l2, u2 = wilson_root(a + c, n)
    den = (a + b_) * (c + d) * (a + c) * (b_ + d)
    num = a * d - b_ * c
    if num > 0:
        num = max(num - n / 2, 0)
    phi = num / math.sqrt(den) if den else 0.0
    dl = p1 - p2
    lo = dl - math.sqrt(max((p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2, 0))
    hi = dl + math.sqrt(max((u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2, 0))
    return dl, lo, hi


r5 = rows("experiments/v5_rag/results.csv")
done5 = {g: {r["vuln_id"]: r for r in r5 if r["agent"] == g and r["status"] == "complete" and b(r["V"]) in (0, 1)} for g in ("c0", "c0m", "c0mr")}
check("V5.complete", A, "Table 1; Sec. 4.8", "complete cases C0 / M / M+RAG", "94/95/94", "/".join(str(len(done5[g])) for g in ("c0", "c0m", "c0mr")), kind="exact")
inc5 = {g: sorted(r["vuln_id"] for r in r5 if r["agent"] == g and r["status"] != "complete") for g in ("c0", "c0m", "c0mr")}
check("V5.orjson", A, "Sec. 4.8", "incomplete cases (C0, M+RAG): the orjson crash", "CVE-2024-27454|CVE-2024-27454|",
      f"{','.join(inc5['c0'])}|{','.join(inc5['c0mr'])}|{','.join(inc5['c0m'])}", kind="exact")
check("V5.orjson_m", A, "Sec. 4.8", "orjson in M: the patch did not apply", "patch did not apply",
      next(r["eval_notes"] for r in r5 if r["agent"] == "c0m" and r["vuln_id"] == "CVE-2024-27454"), kind="exact")
c5 = C["v5"]
case_cost5 = defaultdict(float)
for r in c5:
    case_cost5[(r["agent"], r["case"])] += float(r["list_cost_usd"] or 0)
case_cost0 = defaultdict(float)
for r in [r for r in C["v3"] if r["agent"] == "c0"] + C["v4"]:
    case_cost0[r["case"]] += float(r["list_cost_usd"] or 0)
T11 = {"c0": (94, 38, "40.4", "31.1", "50.5", 91, 54, "59.3", "49.1", "68.9", "8.88", "0.234"),
       "c0m": (95, 14, "14.7", "9.0", "23.2", 62, 48, "77.4", "65.6", "86.0", "2.24", "0.160"),
       "c0mr": (94, 13, "13.8", "8.3", "22.2", 58, 45, "77.6", "65.3", "86.4", "1.68", "0.129")}
for g, (n, vk, vp, vl, vh, cl, fk, fp, fl, fh, cost, cpv) in T11.items():
    d5 = list(done5[g].values())
    vv = sum(b(r["V"]) for r in d5)
    cls = [r for r in d5 if b(r["D_repairer"]) == 1]
    kn_ci(f"V5.{g}.vrr", A, "Table 11; Fig. 7", f"{g} VRR", vk, n, vp, vl, vh, vv, len(d5))
    check(f"V5.{g}.claims", A, "Table 11", f"{g} claims", cl, len(cls), kind="exact")
    kn_ci(f"V5.{g}.far", A, "Table 11; Table 10; Fig. 7", f"{g} FAR", fk, cl, fp, fl, fh, sum(1 for r in cls if b(r["V"]) == 0), len(cls))
    cc = sum(case_cost0[c] for c in done5[g]) if g == "c0" else sum(case_cost5[(g, c)] for c in done5[g])
    check(f"V5.{g}.cost", A, "Table 11", f"{g} cost of the complete cases (USD)", cost, cc)
    check(f"V5.{g}.cpv", A, "Table 11", f"{g} cost per verified repair, complete cases", cpv, cc / vv)
# H1: M+RAG against M on the cases complete in both
pair = sorted(set(done5["c0m"]) & set(done5["c0mr"]))
vm = [b(done5["c0m"][c]["V"]) for c in pair]
vr = [b(done5["c0mr"][c]["V"]) for c in pair]
a_ = sum(1 for x, y in zip(vr, vm) if x and y); only_r = sum(1 for x, y in zip(vr, vm) if x and not y)
only_m = sum(1 for x, y in zip(vr, vm) if y and not x); none_ = len(pair) - a_ - only_r - only_m
check("V5.H1.n", A, "Sec. 4.8", "cases complete in both M and M+RAG", 94, len(pair), kind="exact")
check("V5.H1.discordant", A, "Sec. 4.8", "retrieval turned unverified into verified / verified into unverified", "5/6", f"{only_r}/{only_m}", kind="exact")
p1s = binomtest(only_r, only_r + only_m, 0.5, alternative="greater").pvalue
check("V5.H1.p", A, "Sec. 4.8; abstract; discussion", "H1 one-sided exact McNemar p", "0.73", p1s)
check("V5.H1.vrr", A, "Sec. 4.8; abstract", "paired VRR with / without retrieval (%)", "13.8/14.9",
      f"{pct(sum(vr), len(pair)):.1f}/{pct(sum(vm), len(pair)):.1f}", kind="exact")
dl, lo, hi = newcombe_paired(a_, only_r, only_m, none_)
check("V5.H1.diff", A, "Sec. 4.8", "VRR(M+RAG) - VRR(M), points", "-1.1", 100 * dl)
check("V5.H1.lo", A, "Sec. 4.8; discussion", "Newcombe paired 95% CI low, points", "-8.7", 100 * lo)
check("V5.H1.hi", A, "Sec. 4.8; discussion", "Newcombe paired 95% CI high, points", "6.5", 100 * hi)
check("V5.H1.confirmed", A, "Sec. 4.8", "H1 confirmed (p < 0.05 and VRR(M+RAG) > VRR(M))", "False", str(p1s < 0.05 and sum(vr) > sum(vm)), kind="exact")
# M+RAG against C0
pair0 = sorted(set(done5["c0"]) & set(done5["c0mr"]))
v0_ = [b(done5["c0"][c]["V"]) for c in pair0]
vr0 = [b(done5["c0mr"][c]["V"]) for c in pair0]
aa = sum(1 for x, y in zip(vr0, v0_) if x and y); onr = sum(1 for x, y in zip(vr0, v0_) if x and not y)
on0 = sum(1 for x, y in zip(vr0, v0_) if y and not x); nn = len(pair0) - aa - onr - on0
check("V5.c0.discordant", A, "Sec. 4.8", "cases verified only by C0 / only by M+RAG", "26/1", f"{on0}/{onr}", kind="exact")
dl, lo, hi = newcombe_paired(aa, onr, on0, nn)
check("V5.c0.diff", A, "Sec. 4.8; discussion", "VRR(M+RAG) - VRR(C0), points", "-26.6", 100 * dl)
check("V5.c0.lo", A, "Sec. 4.8", "Newcombe paired 95% CI, low (points)", "-36.0", 100 * lo)
check("V5.c0.hi", A, "Sec. 4.8", "Newcombe paired 95% CI, high (points)", "-16.8", 100 * hi)
# cost per verified repair: ratio C0 / M+RAG with a paired bootstrap (own resampling; the interval is Monte Carlo)
k0 = np.array([case_cost0[c] for c in pair0]); kr = np.array([case_cost5[("c0mr", c)] for c in pair0])
w0 = np.array(v0_, dtype=float); wr = np.array(vr0, dtype=float)
ratio = (k0.sum() / w0.sum()) / (kr.sum() / wr.sum())
check("V5.cpv.ratio", A, "Sec. 4.8", "cost per verified repair, C0 / M+RAG", "1.81", ratio)
rng = np.random.default_rng(20261127)
rs_ = []
for _ in range(10000):
    ix = rng.integers(0, len(pair0), len(pair0))
    if w0[ix].sum() and wr[ix].sum():
        rs_.append((k0[ix].sum() / w0[ix].sum()) / (kr[ix].sum() / wr[ix].sum()))
blo, bhi = np.percentile(rs_, [2.5, 97.5])
check("V5.cpv.lo", A, "Sec. 4.8", "bootstrap 95% CI low (own resamples, Monte Carlo)", "0.99", blo, tol=0.10,
      note="confirm_v5.py uses seed 2026; this audit draws its own resamples, so only agreement within 0.10 is required")
check("V5.cpv.hi", A, "Sec. 4.8", "bootstrap 95% CI high (own resamples, Monte Carlo)", "2.85", bhi, tol=0.10)
# the coverage rule in the three arms (Table 10, replication rows)
for g, (kc_, nc_, kw_, nw_, fr, flo, fhi, pr) in {"c0": (22, 37, 14, 54, "38.9", "24.8", "55.1", "0.001"),
                                                   "c0m": (9, 14, 10, 48, "52.6", "31.7", "72.7", "0.003"),
                                                   "c0mr": (7, 13, 8, 45, "53.3", "30.1", "75.2", "0.015")}.items():
    cls = [r for r in done5[g].values() if b(r["D_repairer"]) == 1]
    cor = [r for r in cls if b(r["V"]) == 1]; wro = [r for r in cls if b(r["V"]) == 0]
    kc5 = sum(b(r["D_coverage"]) == 1 for r in cor); kw5 = sum(b(r["D_coverage"]) == 1 for r in wro)
    check(f"V5.cov.{g}.pass", A, "Table 10; Sec. 4.8", f"{g}: correct / wrong claims kept by the rule", f"{kc_}/{nc_} {kw_}/{nw_}",
          f"{kc5}/{len(cor)} {kw5}/{len(wro)}", kind="exact")
    kn_ci(f"V5.cov.{g}.far", A, "Table 10; Sec. 4.8", f"{g}: FAR with the rule", kw_, kc_ + kw_, fr, flo, fhi, kw5, kc5 + kw5)
    check(f"V5.cov.{g}.p", A, "Table 10; Sec. 4.8", f"{g}: one-sided Fisher p", pr, fisher_greater(kc5, len(cor), kw5, len(wro)))
# the corrected harness: C0 verdicts that changed, cases recovered
before = {r["vuln_id"]: r for r in v3 if r["agent"] == "c0"}
before.update({r["vuln_id"]: r for r in v4 if r["agent"] == "c0"})
changed = sorted(c for c, r in done5["c0"].items() if before[c]["status"] == "complete" and b(before[c]["V"]) != b(r["V"]))
check("V5.harness.changed", A, "Sec. 4.8", "C0 verdicts changed by the v5 harness", "CVE-2024-35195 1->0",
      " ".join(f"{c} {b(before[c]['V'])}->{b(done5['c0'][c]['V'])}" for c in changed), kind="exact")
check("V5.harness.exploit", A, "Sec. 4.8", "CVE-2024-35195 exploit tests before / v5", "318/0/0/2 -> 317/1/0/2",
      f"{before['CVE-2024-35195']['exploit_pfes']} -> {done5['c0']['CVE-2024-35195']['exploit_pfes']}", kind="exact")
recov = sorted(c for c in done5["c0"] if before[c]["status"] != "complete")
check("V5.harness.recovered", A, "Sec. 4.8; Limitations", "cases lost in v4 now complete, and their C0 verdicts",
      "CVE-2024-52804:1 CVE-2025-5120:0", " ".join(f"{c}:{b(done5['c0'][c]['V'])}" for c in recov), kind="exact")
for g, (emp, fx, fn) in {"c0m": (23, 34, 48), "c0mr": (26, 33, 45)}.items():
    d5 = list(done5[g].values())
    cls_f = [r for r in d5 if b(r["D_repairer"]) == 1 and b(r["V"]) == 0]
    check(f"V5.{g}.empty", A, "Sec. 4.8", f"{g}: empty patches", emp, sum(1 for r in d5 if (r["eval_notes"] or "").startswith("empty patch")), kind="exact")
    check(f"V5.{g}.exploitonly", A, "Sec. 4.8", f"{g}: false claims whose patch failed only the exploit tests", f"{fx}/{fn}",
          f"{sum(1 for r in cls_f if b(r['A']) == 1 and b(r['F']) == 1 and b(r['S']) == 0)}/{len(cls_f)}", kind="exact")
# retrieval records: leakage audit and the repository filter
lk, same_repo, recs = [], 0, 0
for f in glob.glob(str(ROOT / "experiments/v5_rag/main/c0mr/*/llm_response.json")):
    rg = json.loads(Path(f).read_text(encoding="utf-8")).get("rag") or {}
    recs += 1
    lk += [x["ratio"] for x in rg.get("leak_audit", [])] + ([9.9] if rg.get("leak_flag") else [])
    same_repo += sum(1 for h in rg.get("hits", []) if h["repo"] == rg.get("repo_filtered") or h["case"] == Path(f).parent.name)
check("V5.rag.records", A, "Sec. 4.8", "M+RAG case records with a retrieval record", 95, recs, kind="exact")
check("V5.rag.leak", A, "Sec. 4.8", "largest leakage similarity (flagged at 0.5)", "0.095", max(lk))
check("V5.rag.filter", A, "Sec. 3.8", "retrieved examples from the case's own repository or case", 0, same_repo, kind="exact")
# costs counting every call (Table 14 and Sec. 4.9)
cm_all = sum(float(r["list_cost_usd"]) for r in c5 if r["agent"] == "c0m")
cr_all = sum(float(r["list_cost_usd"]) for r in c5 if r["agent"] == "c0mr")
c0_all = sum(case_cost0.values())
for g, cost, att, comp, ver, per_case, per_rep, val in (("c0m", "2.24", 95, 95, 14, "0.024", "0.160", cm_all),
                                                       ("c0mr", "1.91", 95, 94, 13, "0.020", "0.147", cr_all)):
    check(f"V5.t14.{g}.att", A, "Table 14", f"{g} attempted (complete), verified", f"{att} ({comp}) {ver}",
          f"{sum(1 for r in r5 if r['agent'] == g)} ({len(done5[g])}) {sum(b(r['V']) for r in done5[g].values())}", kind="exact")
    check(f"V5.t14.{g}.cost", A, "Table 14", f"{g} cost, every call (USD)", cost, val)
    check(f"V5.t14.{g}.case", A, "Table 14", f"{g} per attempted case", per_case, val / att)
    check(f"V5.t14.{g}.rep", A, "Table 14; Sec. 4.9", f"{g} per verified repair", per_rep, val / ver)
check("V5.txt.c0", A, "Sec. 4.9; discussion", "GPT-6.2 Sol per verified repair on the same 95 cases, every call", "0.25", c0_all / 38)
check("V5.txt.ratio", A, "Sec. 4.9", "verified repairs 1.6 to 1.7 times cheaper", "1.6-1.7",
      f"{(c0_all / 38) / (cm_all / 14):.1f}-{(c0_all / 38) / (cr_all / 13):.1f}", kind="exact")
out_m = statistics.fmean(int(r["output_tokens"]) for r in c5 if r["agent"] == "c0m")
out_r = statistics.fmean(int(r["output_tokens"]) for r in c5 if r["agent"] == "c0mr")
out_g = statistics.fmean(int(r["output_tokens"]) for r in [r for r in C["v3"] if r["agent"] == "c0"] + C["v4"])
check("V5.txt.tokens", A, "Sec. 4.9", "output tokens per call: M+RAG - M against GPT-6.2 Sol (thousands)", "21-25 / 7.1",
      f"{out_r / 1000:.0f}-{out_m / 1000:.0f} / {out_g / 1000:.1f}", kind="exact")

# =============================================================================================== 10. figures
A = "Data figures (values, provenance, integrity)"
FV = rows("results/figures/figure_values.csv")
check("F0.count", A, "figure_values.csv", "plotted values recorded (100 before v5, 6 more for its arms in Fig. 7)", 106, len(FV), kind="exact")
# every proportion with k/n: value and Wilson bounds by root finding
props = [r for r in FV if r["numerator"] != "" and r["denominator"] != ""]
bad = []
for r in props:
    k, n = int(r["numerator"]), int(r["denominator"])
    lo, hi = wilson_root(k, n)
    if abs(float(r["value"]) - k / n) > 1e-6 or abs(float(r["ci95_low"]) - lo) > 1e-6 or abs(float(r["ci95_high"]) - hi) > 1e-6:
        bad.append(f"{r['figure']}:{r['item']}:{r['measure']}")
check("F1.wilson", A, "figure_values.csv", f"proportions whose value or Wilson bounds differ from the root-finding bounds (of {len(props)})",
      0, len(bad), kind="exact", note="; ".join(bad))
# each plotted proportion against the audit's own counts
expect = {}
for i, c in enumerate(ok):
    expect[("fig_environment", f"R{i}", "valid_cases")] = c
expect[("fig_environment", "Oracle control", "valid_cases")] = len(healthy)
expect[("fig_environment", "Public release (sandbox scan)", "valid_cases")] = 18
for key, (rs, claim, *_r) in T6.items():
    a = arm(rs, "c0" if key == "conf" else key, claim)
    lab = {"c0": "C0: repairer alone (main sample)", "c0g": "C0g: repairer + mechanical gate", "c1": "C1: analyst + unanimous jury",
           "conf": f"C0: {a['n']} confirmation cases"}[key]
    expect[("fig_main_vrr_far", lab, "VRR")] = (a["v"], a["n"])
    expect[("fig_main_vrr_far", lab, "FAR")] = (a["fa"], a["claims"])
expect[("fig_main_vrr_far", "v0 pilot, laguna-xs-2.1", "VRR")] = (1, 5)
expect[("fig_main_vrr_far", "v0 pilot, laguna-xs-2.1", "FAR")] = (3, 4)
for g, lab in (("c0", "v5: C0 re-evaluated, v5 harness"), ("c0m", "v5: Haiku 5.5 alone"), ("c0mr", "v5: Haiku 5.5 + RAG")):
    d5 = list(done5[g].values())
    cls = [r for r in d5 if b(r["D_repairer"]) == 1]
    expect[("fig_main_vrr_far", lab, "VRR")] = (sum(b(r["V"]) for r in d5), len(d5))
    expect[("fig_main_vrr_far", lab, "FAR")] = (sum(1 for r in cls if b(r["V"]) == 0), len(cls))
expect[("fig_v0_pilot", "v0 pilot", "VRR")] = (sum(r["verified_repair"] == "True" for r in v0), len(v0))
expect[("fig_v0_pilot", "v0 pilot", "FAR")] = (sum(r["verified_repair"] == "False" for r in v0_claims), len(v0_claims))
expect[("fig_coverage_rule", "All positive claims", "FAR")] = (len(wrong), len(cr))
expect[("fig_coverage_rule", "Claims kept by the rule", "FAR")] = (kw, kc + kw)
for m, rep in (("gpt-6-luna", "GPT benchmark: GPT-6 Luna"), ("gpt-6.1-terra", "GPT benchmark: GPT-6.1 Terra"),
               ("gpt-6.2-astra", "GPT benchmark: GPT-6.2 Astra"), ("gpt-6.2-sol", "GPT benchmark: GPT-6.2 Sol"),
               ("gpt-6.2-sol_recortado", "GPT benchmark: GPT-6.2 Sol (trimmed context)")):
    rr = [r for r in gb if r["model"] == m]
    expect[("fig_pilot_benchmarks", rep, "VRR")] = (sum(int(r["V"]) for r in rr), len(rr))
expect[("fig_pilot_benchmarks", "v0 MVP: laguna-xs-2.1 (own pilot)", "VRR")] = (1, 5)
for ag, lab in (("rep_gpt-5.4-mini", "Tournament repairer: GPT-5.4 mini"), ("rep_gpt-6.2-sol", "Tournament repairer: GPT-6.2 Sol"),
                ("c1", "Pilot C1: GPT-model jury"), ("c1v2", "Pilot C1 v2: cross-family jury")):
    a = arm(pil, ag, "D_repairer")
    expect[("fig_pilot_benchmarks", lab, "VRR")] = (a["v"], a["n"])
short = {"claudecode:claude-opus-5-5": "Claude Opus 5.5", "claudecode:claude-sonnet-5-5": "Claude Sonnet 5.5",
         "claudecode:claude-haiku-5-5": "Claude Haiku 5.5", "deepseek:deepseek-v4-pro": "DeepSeek V4 Pro", "deepseek:deepseek-flash": "DeepSeek Flash"}
for m, s in short.items():
    expect[("fig_jury_calibration", s, "AUROC")] = c2[m]["auroc"]
    expect[("fig_jury_calibration", s, "Sensitivity")] = c2[m]["sens"]
    expect[("fig_jury_calibration", s, "Specificity")] = c2[m]["spec"]
    expect[("fig_jury_calibration", s, "list_price_cost_5_calls")] = costs[m]
for g, lab in (("c0", "C0"), ("c0g", "C0g"), ("c1", "C1")):
    cg = sum(float(r["list_cost_usd"] or 0) for r in C["v3"] if r["agent"] == g)
    att = sum(r["agent"] == g for r in v3)
    expect[("fig_cost_per_repair", lab, "cost_per_attempted_case")] = cg / att
    expect[("fig_cost_per_repair", lab, "cost_per_verified_repair")] = cg / mr3[g]["v"]
    expect[("fig_cost_per_repair", lab, "total_list_cost")] = cg
    expect[("fig_cost_per_repair", lab, "denominator_cost_per_attempted_case")] = att
    expect[("fig_cost_per_repair", lab, "denominator_cost_per_verified_repair")] = mr3[g]["v"]
for (m, ro), rs in G.items():
    for fld in ("input_tokens", "output_tokens", "latency_s"):
        expect[("fig_calls_tokens_time", f"{m} ({ro})", f"median_{fld}")] = statistics.median(max(float(r[fld] or 0), 1.0) for r in rs)
unmatched, mismatched = [], []
for r in FV:
    key = (r["figure"], r["item"], r["measure"])
    if key not in expect:
        unmatched.append(key)
        continue
    e = expect[key]
    if isinstance(e, tuple):
        okk = int(r["numerator"]) == e[0] and int(r["denominator"]) == e[1]
    else:
        okk = abs(float(r["value"]) - float(e)) <= 1e-6 * max(1.0, abs(float(e)))
    if not okk:
        mismatched.append(f"{key}: plotted {r['value']} ({r['numerator']}/{r['denominator']}) vs audit {e}")
check("F2.recomputed", A, "figure_values.csv", "plotted values that differ from the audit's own computation", 0, len(mismatched),
      kind="exact", note="; ".join(mismatched))
check("F2.unmatched", A, "figure_values.csv", "plotted values the audit could not match to a computation", 0, len(unmatched),
      kind="exact", note="; ".join(map(str, unmatched)))
# provenance: manifest hashes, copies in the paper folder
man = json.loads((ROOT / "results/figures/MANIFEST.json").read_text())
stale = [f"{fig}:{p}" for fig, m in man["figures"].items() if isinstance(m, dict) for p, h in m.get("inputs", {}).items()
         if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
check("F3.inputs", A, "MANIFEST.json", "input files whose sha256 differs from the manifest", 0, len(stale), kind="exact", note="; ".join(stale))
outs = [f"{fig}:{p}" for fig, m in man["figures"].items() if isinstance(m, dict) for p, h in m.get("outputs", {}).items()
        if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
check("F3.outputs", A, "MANIFEST.json", "figure files whose sha256 differs from the manifest", 0, len(outs), kind="exact", note="; ".join(outs))
diffcopy = []
for f in sorted(glob.glob(str(ROOT / "papers/final/paper/figures/fig_*.pdf"))):
    src = ROOT / "results/figures" / Path(f).name
    if src.exists() and hashlib.sha256(src.read_bytes()).hexdigest() != hashlib.sha256(Path(f).read_bytes()).hexdigest():
        diffcopy.append(Path(f).name)
check("F3.copies", A, "papers/final/paper/figures", "data-figure PDFs in the paper that differ from results/figures", 0, len(diffcopy),
      kind="exact", note="; ".join(diffcopy))
# captions: the files each caption names must be the files the figure is drawn from
tex = (ROOT / "papers/final/paper/main.tex").read_text(encoding="utf-8")
# the caption that ends with each figure label (no other \caption{ in between)
cap = {m.group(2): m.group(1) for m in re.finditer(r"\\caption\{((?:(?!\\caption\{).)*?)\\label\{(fig:[a-z]+)\}", tex, re.S)}
fig_of = {"fig:env": "fig_environment", "fig:pilotfig": "fig_pilot_benchmarks", "fig:calib": "fig_jury_calibration",
          "fig:main": "fig_main_vrr_far", "fig:coverage": "fig_coverage_rule", "fig:calls": "fig_calls_tokens_time", "fig:cost": "fig_cost_per_repair"}


def names_file(n, p):
    """a caption name covers an input path: same path, a wildcard over it, or a bare file name in the folder named before"""
    import fnmatch
    return (n == p or ("*" in n and fnmatch.fnmatch(p, n)) or (n.endswith("/") and p.startswith(n))
            or ("/" not in n and (p.endswith("/" + n) or fnmatch.fnmatch(Path(p).name, n))))


for lab, fig in fig_of.items():
    c = cap[lab].replace("\\_", "_")
    named = set(re.findall(r"\\texttt\{([^}]+)\}", c)) - {"results/figures/make_figures.py"}
    used = set(man["figures"][fig]["inputs"])
    missing = sorted(p for p in used if not any(names_file(n, p) for n in named))
    wrongs = sorted(n for n in named if not any(names_file(n, p) for p in used))
    check(f"F4.{fig}", A, f"caption of {lab}", f"{fig}: inputs not named in the caption / named files not used",
          "none / none", f"{', '.join(missing) or 'none'} / {', '.join(wrongs) or 'none'}", kind="exact")
# fonts: every font of the data figures embedded and not Type 3
import subprocess  # noqa: E402
t3, notemb = [], []
for fig in fig_of.values():
    out = subprocess.run(["pdffonts", str(ROOT / f"results/figures/{fig}.pdf")], capture_output=True, text=True).stdout.splitlines()[2:]
    for line in out:
        if "Type 3" in line:
            t3.append(fig)
        if " no " in f" {line.split()[-5]} ":
            notemb.append(fig)
check("F5.fonts", A, "results/figures/*.pdf", "data figures with Type 3 or non-embedded fonts", 0, len(set(t3 + notemb)), kind="exact",
      note="; ".join(sorted(set(t3 + notemb))))
# zero-based bars (Fig. 6 right, Fig. 10): the bar axes start at 0 in the code that draws them
src = (ROOT / "results/figures/make_figures.py").read_text(encoding="utf-8")
check("F6.bars", A, "make_figures.py", "bar axes set to start at zero (fig_cost: set_ylim(0, top); fig_judges: a2.set_xlim(0, ...))", "True",
      str("ax.set_ylim(0, top)" in src and "a2.set_xlim(0," in src), kind="exact")

# ----------------------------------------------------------------------------------------------- write
with open(OUT / "audit_checks.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(CHECKS[0]))
    w.writeheader()
    w.writerows(CHECKS)
summ = Counter(c["status"] for c in CHECKS)
by_area = defaultdict(Counter)
for c in CHECKS:
    by_area[c["area"]][c["status"]] += 1
(OUT / "audit_summary.json").write_text(json.dumps({"checks": len(CHECKS), "status": summ, "by_area": by_area,
                                                     "fails": [c for c in CHECKS if c["status"] == "FAIL"]}, indent=1, default=dict))
print(f"{len(CHECKS)} checks: {dict(summ)}")
for c in CHECKS:
    if c["status"] == "FAIL":
        print("FAIL", c["id"], "|", c["item"], "| reported", c["reported"], "| recomputed", c["recomputed"], "|", c["note"][:200])
