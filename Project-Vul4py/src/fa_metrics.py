#!/usr/bin/env python3
"""
fa_metrics.py

Aggregate frozen generations (llm_response.json) and Vul4Py verdicts (eval.json)
into the per-attempt table and the aggregate metrics of Section 3 of the guide.

Per attempt i:
    A_i  patch applied            F_i  functional tests pass      S_i  exploit tests pass
    V_i = A_i * F_i * S_i
    FA_i(gen) = C_i(repairer) * (1 - V_i)      FA_i(rev) = C_i(reviewer) * (1 - V_i)

Aggregates over COMPLETED attempts only (incomplete ones are listed separately):
    VRR      = sum V / N
    FAR_gen  = sum FA_gen / sum C_gen     (undefined if sum C_gen = 0)
    FAR_rev  = sum FA_rev / sum C_rev     (undefined if sum C_rev = 0)

An attempt is INCOMPLETE (never counted as pass or fail) when generation failed
(API error, no parseable claim) or verification did not finish (no eval.json,
evaluator crash, no junit report, zero tests executed).

Usage:
    python scripts/fa_metrics.py --runs runs/final            # every agent under runs/final
    python scripts/fa_metrics.py --runs runs/final --agents ma3_r1,ma3_r2
Writes <runs>/results.csv, <runs>/summary.json and <runs>/summary.md
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics as st
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

COLS = [
    "group", "agent", "run_index", "vuln_id", "pipeline",
    "analyst_model", "repairer_model", "reviewer_model",
    "status", "incomplete_reason",
    "C_gen", "P_gen", "C_gen_initial", "n_rounds", "n_judges", "votes",
    "C_rev", "P_rev", "rev_applies", "rev_removes_vuln", "rev_preserves_func", "rev_consistent",
    "D_repairer", "D_judge1", "D_consensus", "D_majority", "D_unanimous", "D_gate", "D_pre_revision", "D_independent",
    "hint_coverage", "D_coverage", "D_coverage75", "D_gate_coverage",
    "diff_extracted", "patch_bytes", "patch_sha256",
    "A", "F", "S", "V", "V_initial", "FA_gen", "FA_rev",
    "func_pfes", "exploit_pfes", "baseline_exploit_pfes",
    "exploit_tests_fixed", "exploit_tests_still_failing", "exploit_new_failures",
    "L_analyst_ms", "L_repairer_ms", "L_reviewer_ms", "L_api_total_ms", "http_retries",
    "input_tokens", "output_tokens", "generated_at_utc", "frozen_at_utc",
    "eval_elapsed_s", "eval_notes",
    # pipeline v2 (protocols and debate)
    "condition", "n_candidates", "n_distinct", "selected_k", "abstained", "jury_rounds", "resolved_in",
    "gate_failed_versions", "gate_rescued", "refused", "context_mode",
    "cites_total", "cites_rejected", "V_any_candidate", "jury_picked_correct",
    "wall_time_s",
]


# ---------------- statistics ----------------

def wilson(k: int, n: int, z: float = 1.959964) -> Tuple[Optional[float], Optional[float]]:
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def mcnemar_exact(b: int, c: int) -> Optional[float]:
    """Two-sided exact McNemar p-value for discordant counts b, c."""
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def brier(pairs: List[Tuple[float, int]]) -> Optional[float]:
    return st.mean((p - v) ** 2 for p, v in pairs) if pairs else None


def pct(x: Optional[float]) -> str:
    return "undefined" if x is None else f"{100 * x:.1f}%"


# ---------------- junit / evidence ----------------

def junit_failed(path: Path) -> Optional[set]:
    if not path.exists():
        return None
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    out = set()
    for s in suites:
        for c in s.findall("testcase"):
            if c.find("failure") is not None or c.find("error") is not None:
                out.add(f"{c.get('classname', '')}::{c.get('name', '')}")
    return out


def pfes(s: Any) -> Optional[Tuple[int, int, int, int]]:
    try:
        p, f, e, k = (int(x) for x in str(s).split("/"))
        return p, f, e, k
    except Exception:
        return None


def load_scan(workspaces: Optional[Path]) -> Dict[str, Dict[str, str]]:
    if not workspaces:
        return {}
    rep = workspaces / "scan_report.tsv"
    if not rep.exists():
        return {}
    lines = rep.read_text(encoding="utf-8").splitlines()
    hdr = lines[0].split("\t")
    return {r["cve_id"]: r for r in (dict(zip(hdr, ln.split("\t"))) for ln in lines[1:]) if r.get("cve_id")}


def classify_eval(ev: Optional[Dict[str, Any]]) -> Tuple[str, str, Optional[int], Optional[int], Optional[int]]:
    """-> (status, reason, A, F, S)"""
    if ev is None:
        return "incomplete", "not evaluated (no eval.json)", None, None, None
    notes = ev.get("notes") or ""
    if "frozen artifact modified" in notes:
        return "incomplete", notes, None, None, None
    if not ev.get("apply_ok"):
        if notes in ("patch did not apply", "empty patch", "no patch", "") or notes.startswith("patch did not apply"):
            return "complete", "", 0, 0, 0          # guide: F = S = 0 when the patch does not apply
        return "incomplete", f"verification error: {notes}", None, None, None
    if "crash" in notes:
        return "incomplete", f"verification error: {notes}", 1, None, None
    fp, xp = pfes(ev.get("func_pfes")), pfes(ev.get("exploit_pfes"))
    if fp is None:
        return "incomplete", "functional junit report missing", 1, None, None
    if fp[0] + fp[1] + fp[2] == 0:
        return "incomplete", "no functional tests executed", 1, None, None
    if xp is None:
        if isinstance(ev.get("exploit_rc"), int) and ev["exploit_rc"] >= 128:
            return "complete", "", 1, int(bool(ev.get("func_ok"))), 0   # the exploit crashed the process
        return "incomplete", "exploit junit report missing", 1, None, None
    if xp[0] + xp[1] + xp[2] == 0:
        return "incomplete", "no exploit tests executed", 1, None, None
    return "complete", "", 1, int(bool(ev.get("func_ok"))), int(bool(ev.get("exploit_ok")))


# ---------------- collection ----------------

TAU = 0.8          # pre-registered confidence threshold for the "gate" rule (override: --tau)
PRIMARY = "unanimous"
RULES = ["repairer", "judge1", "consensus", "majority", "unanimous", "gate", "pre_revision", "independent",
         "coverage", "coverage75", "gate_coverage"]
# Location coverage (decisiones v4; found post hoc on the main sample, confirmed on a fresh one):
#   coverage       the repairer claims AND its final patch touches every line range of the localization hint
#   coverage75     the same with at least 75 % of the hinted ranges touched (secondary)
#   gate_coverage  the gate rule AND every hinted range touched (exploratory, needs a jury)
# A hinted range [a, b] counts as touched when a hunk of the patch, in the same file, overlaps [a-3, b+3]
# in the ORIGINAL file's line numbers. In Vul4Py the hint is the footprint of the upstream fix.
HINT_TOLERANCE = 3
# judged on the INITIAL patch (V_initial), from the stored jury rounds:
#   pre_revision  unanimous in a round before the first revision (decisiones v1, secondary analysis)
#   independent   unanimous in round 0, before any debate or revision (added after the pilot C1 v2,
#                 before the main C1; exploratory: the jury without debate)
INITIAL_PATCH_RULES = ("pre_revision", "independent")


def _hint_ranges(hint: str) -> Dict[str, List[Tuple[int, int]]]:
    out: Dict[str, List[Tuple[int, int]]] = {}
    for m in re.finditer(r"^- (\S+): lines (.+)$", hint or "", re.M):
        rs = []
        for part in m.group(2).split(","):
            a, _, b = part.strip().partition("-")
            if a.isdigit():
                rs.append((int(a), int(b) if b.isdigit() else int(a)))
        out[m.group(1)] = rs
    return out


def _patch_ranges(patch: str) -> Dict[str, List[Tuple[int, int]]]:
    out: Dict[str, List[Tuple[int, int]]] = {}
    cur = None
    for line in (patch or "").splitlines():
        if line.startswith("--- "):
            f = line[4:].split("\t")[0].strip()
            cur = f[2:] if f.startswith(("a/", "b/")) else f
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+", line)
        if m and cur:
            start, n = int(m.group(1)), int(m.group(2) or 1)
            out.setdefault(cur, []).append((start, start + max(n, 1) - 1))
    return out


def hint_coverage(hint: str, patch: str, tol: int = HINT_TOLERANCE) -> Optional[float]:
    """Share of the hinted line ranges that the patch touches (None when there is no line hint)."""
    hinted = _hint_ranges(hint)
    total = sum(len(v) for v in hinted.values())
    if not total:
        return None
    hunks = _patch_ranges(patch)
    hit = sum(1 for f, rs in hinted.items() for a, b in rs
              if any(not (hb + tol < a or ha - tol > b) for ha, hb in hunks.get(f, [])))
    return hit / total


def _sum_lat(stages: Dict[str, Any], prefix: str) -> Optional[float]:
    vals = [v.get("latency_ms") for k, v in stages.items()
            if k.startswith(prefix) and v.get("status") == "ok"]
    return round(sum(vals), 1) if vals else None


def discover_agents(runs: Path) -> List[str]:
    return sorted(d.name for d in runs.iterdir()
                  if d.is_dir() and not d.name.startswith("_")
                  and any(d.glob("*/llm_response.json")))


def collect(runs: Path, agents: List[str], workspaces: Optional[Path]) -> List[Dict[str, Any]]:
    scan = load_scan(workspaces)
    rows = []
    for agent in agents:
        for rec_path in sorted((runs / agent).glob("*/llm_response.json")):
            run_dir = rec_path.parent
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
            vid = rec["vuln_id"]
            ev_path = run_dir / "eval.json"
            ev = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else None
            g, r = rec.get("generator", {}), rec.get("reviewer", {})
            stg = rec.get("stages", {})

            if rec.get("generation_status") != "complete":
                status, reason, A, F, S = "incomplete", rec.get("incomplete_reason", "generation"), None, None, None
            else:
                status, reason, A, F, S = classify_eval(ev)

            V = A * F * S if status == "complete" else None
            V_initial = None
            if V is not None:
                if (rec.get("n_rounds") or 1) == 1:
                    V_initial = V                      # no revision: the initial patch is the final one
                else:
                    ip = runs / f"{agent}__initial" / vid / "eval.json"
                    if ip.exists():
                        st_i, _, Ai, Fi, Si = classify_eval(json.loads(ip.read_text(encoding="utf-8")))
                        V_initial = Ai * Fi * Si if st_i == "complete" else None
            Cg = g.get("claim")
            Cr = r.get("claim") if r.get("status") == "complete" else None
            j1 = None
            if rec.get("rounds") and rec["rounds"][-1].get("judges"):
                j1 = rec["rounds"][-1]["judges"][0]
            # acceptance rules on the FINAL patch (all from frozen data; computed after the fact)
            jury_ok = Cr is not None
            maj = r.get("majority", Cr) if jury_ok else None
            una = r.get("unanimous", Cr) if jury_ok else None
            conf = r.get("confidence")
            rules = {
                "repairer": Cg,
                "judge1": r.get("judge1_claim", Cr) if jury_ok else None,
                "consensus": (int(bool(Cg) and bool(maj)) if (jury_ok and Cg is not None) else None),
                "majority": maj,
                "unanimous": una,
                "gate": (int(bool(maj) and conf is not None and conf >= TAU) if jury_ok else None),
            }
            jrs = rec.get("jury_rounds") or []

            def _accepts(rr: Dict[str, Any]) -> int:
                d = rr.get("decision") or {}
                return int(bool(d.get("unanimous")) and d.get("accept_k") is not None)
            if jrs and jury_ok:
                pre = []
                for i, rr in enumerate(jrs):
                    if i > 0 and rr.get("kind") == "independent":
                        break           # a fresh vote on a revised patch: the revision happened before it
                    pre.append(rr)
                rules["pre_revision"] = int(any(_accepts(rr) for rr in pre))
                rules["independent"] = _accepts(jrs[0])
            else:
                rules["pre_revision"] = rules["independent"] = None
            pf = run_dir / "patch.diff"
            cov = hint_coverage(rec.get("hint_text", ""), pf.read_text(encoding="utf-8", errors="replace")
                                if pf.exists() else "")
            rules["coverage"] = (int(bool(Cg) and cov is not None and cov >= 1.0)
                                 if (Cg is not None and cov is not None) else None)
            rules["coverage75"] = (int(bool(Cg) and cov >= 0.75)
                                   if (Cg is not None and cov is not None) else None)
            rules["gate_coverage"] = (int(bool(rules["gate"]) and cov >= 1.0)
                                      if (rules["gate"] is not None and cov is not None) else None)
            row = {
                "group": re.sub(r"_r\d+$", "", agent), "agent": agent,
                "run_index": rec.get("run_index"), "vuln_id": vid,
                "pipeline": rec.get("pipeline"),
                "analyst_model": rec.get("models", {}).get("analyst", ""),
                "repairer_model": rec.get("models", {}).get("repairer", ""),
                "reviewer_model": rec.get("models", {}).get("reviewer", ""),
                "status": status, "incomplete_reason": reason,
                "C_gen": Cg, "P_gen": g.get("confidence"),
                "C_gen_initial": rec.get("generator_initial", {}).get("claim"),
                "n_rounds": rec.get("n_rounds"), "n_judges": r.get("n_judges"), "votes": r.get("votes"),
                "C_rev": Cr, "P_rev": conf if Cr is not None else None,
                "rev_applies": (j1 or r).get("applies"),
                "rev_removes_vuln": (j1 or r).get("removes_vulnerability"),
                "rev_preserves_func": (j1 or r).get("preserves_functionality"),
                "rev_consistent": (j1 or r).get("consistent"),
                **{f"D_{k}": v for k, v in rules.items()},
                "hint_coverage": round(cov, 3) if cov is not None else None,
                "diff_extracted": g.get("diff_extracted"), "patch_bytes": g.get("patch_bytes"),
                "patch_sha256": rec.get("sha256", {}).get("patch.diff", ""),
                "A": A, "F": F, "S": S, "V": V, "V_initial": V_initial,
                "FA_gen": (Cg * (1 - V)) if (V is not None and Cg is not None) else None,
                "FA_rev": (Cr * (1 - V)) if (V is not None and Cr is not None) else None,
                "func_pfes": (ev or {}).get("func_pfes"), "exploit_pfes": (ev or {}).get("exploit_pfes"),
                "baseline_exploit_pfes": scan.get(vid, {}).get("ev_pfes", ""),
                "L_analyst_ms": stg.get("analyst", {}).get("latency_ms"),
                "L_repairer_ms": _sum_lat(stg, "repairer"),
                "L_reviewer_ms": _sum_lat(stg, "reviewer"),
                "L_api_total_ms": rec.get("latency_ms_api_total"),
                "http_retries": rec.get("http_retries"),
                "input_tokens": rec.get("input_tokens_total"), "output_tokens": rec.get("output_tokens_total"),
                "generated_at_utc": rec.get("started_at_utc"), "frozen_at_utc": rec.get("frozen_at_utc"),
                "eval_elapsed_s": (ev or {}).get("elapsed_s"), "eval_notes": (ev or {}).get("notes", ""),
                "wall_time_s": rec.get("wall_time_s"),     # generation of the case, end to end (no evaluation)
            }
            # Partial-fix evidence: which exploit tests failed before (vulnerable) vs after (patched).
            base = junit_failed(runs / "_baseline" / vid / "exploit_vulnerable.junit.xml")
            cand = junit_failed(run_dir / "logs" / f"exploit_{agent}_candidate.junit.xml")
            if base is not None and cand is not None:
                row["exploit_tests_fixed"] = len(base - cand)
                row["exploit_tests_still_failing"] = len(base & cand)
                row["exploit_new_failures"] = len(cand - base)
            if rec.get("schema") == "fa-multiagent/2":
                row.update(v2_fields(runs, agent, vid, rec, row))
            rows.append(row)
    return rows


def v2_fields(runs: Path, agent: str, vid: str, rec: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """Protocol and debate statistics of one v2 attempt, plus the candidates' own verdicts."""
    cands = rec.get("candidates", [])
    vers = [v for c in cands for v in c.get("versions", [])]
    gate_failed = sum(1 for v in vers if v.get("gate") and not v["gate"].get("ok"))
    rescued = sum(1 for c in cands if c.get("status") == "ok"
                  and any(v.get("gate") and not v["gate"].get("ok") for v in c.get("versions", [])))
    cites = rej = 0
    for g in [rec.get("analyst_grounding") or {}] + [v.get("grounding") or {} for v in vers]:
        cites += g.get("n", 0) or 0
        rej += g.get("rejected", 0) or 0
    for jr in rec.get("jury_rounds", []):
        for vt in jr.get("votes", []):
            g = vt.get("grounding") or {}
            cites += (g.get("grounded", 0) or 0) + (g.get("rejected", 0) or 0)
            rej += g.get("rejected", 0) or 0
    rounds = rec.get("jury_rounds", [])
    resolved = None
    if rounds and rounds[-1].get("decision", {}).get("unanimous"):
        resolved = "independent" if len(rounds) == 1 else ("debate" if rounds[-1].get("kind") == "debate"
                                                           else "after_revision")
    vs = {}
    sel_patch = runs / agent / vid / "patch.diff"
    sel_text = sel_patch.read_text(encoding="utf-8", errors="replace") if sel_patch.exists() else None
    for c in cands:
        ep = runs / f"{agent}__cand{c['k']}" / vid / "eval.json"
        cp = runs / agent / vid / f"cand{c['k']}_final.diff"
        if ep.exists():
            st_c, _, A, F, S = classify_eval(json.loads(ep.read_text(encoding="utf-8")))
            if st_c == "complete":
                vs[c["k"]] = A * F * S
        elif cp.exists() and sel_text is not None and cp.read_text(encoding="utf-8", errors="replace") == sel_text \
                and row.get("V") is not None:
            vs[c["k"]] = row["V"]      # identical to the selected patch, evaluated as the agent itself
    distinct = {c["k"] for c in cands if c.get("status") == "ok" and c.get("duplicate_of") is None}
    sel = rec.get("selected_k")
    v_any = max(vs.values()) if vs else None
    return {
        "condition": rec.get("condition"), "n_candidates": len(cands), "n_distinct": len(distinct) or None,
        "selected_k": sel, "abstained": (rec.get("reviewer") or {}).get("abstained"),
        "jury_rounds": len(rounds), "resolved_in": resolved,
        "gate_failed_versions": gate_failed, "gate_rescued": rescued,
        "refused": sum(1 for c in cands if c.get("status") == "refused"),
        "context_mode": rec.get("context_mode"), "cites_total": cites, "cites_rejected": rej,
        "V_any_candidate": v_any,
        "jury_picked_correct": (int(vs.get(sel, row.get("V") or 0) == 1) if v_any == 1 and sel is not None else None),
    }


# ---------------- aggregation ----------------

def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    done = [r for r in rows if r["status"] == "complete"]
    inc = [r for r in rows if r["status"] != "complete"]
    N = len(done)
    sV = sum(r["V"] for r in done)
    # a complete attempt can carry no repairer claim (C1 with no candidate past the gate, or no parseable
    # self-assessment): it counts as no claim, so it adds nothing to C_gen or FA_gen
    sCg = sum((r["C_gen"] or 0) for r in done)
    sFAg = sum((r["FA_gen"] or 0) for r in done)
    rev = [r for r in done if r["C_rev"] is not None]
    sCr = sum(r["C_rev"] for r in rev)
    sFAr = sum(r["FA_rev"] for r in rev)
    out: Dict[str, Any] = {
        "attempts": len(rows), "N_complete": N, "N_incomplete": len(inc),
        "incomplete": [{"agent": r["agent"], "vuln_id": r["vuln_id"], "reason": r["incomplete_reason"]} for r in inc],
        "sum_V": sV, "VRR": sV / N if N else None, "VRR_CI95": wilson(sV, N),
        "sum_C_gen": sCg, "sum_FA_gen": sFAg,
        "FAR_gen": sFAg / sCg if sCg else None, "FAR_gen_CI95": wilson(sFAg, sCg),
        "N_reviewed": len(rev), "sum_C_rev": sCr, "sum_FA_rev": sFAr,
        "FAR_rev": sFAr / sCr if sCr else None, "FAR_rev_CI95": wilson(sFAr, sCr),
    }
    if rev:
        b = sum(1 for r in rev if r["FA_gen"] == 1 and r["FA_rev"] == 0)
        c = sum(1 for r in rev if r["FA_gen"] == 0 and r["FA_rev"] == 1)
        out.update({
            "reviewer_caught_false_assurance": b,
            "reviewer_added_false_assurance": c,
            "reviewer_rejected_verified_repair": sum(1 for r in rev if r["V"] == 1 and r["C_rev"] == 0),
            "mcnemar_p_FA_gen_vs_rev": mcnemar_exact(b, c),
            "brier_rev": brier([(r["P_rev"], r["V"]) for r in rev if r["P_rev"] is not None]),
            "rev_predicted_apply_accuracy": (st.mean(int(r["rev_applies"] == r["A"]) for r in rev
                                                     if r["rev_applies"] is not None)
                                             if any(r["rev_applies"] is not None for r in rev) else None),
        })
    paired = [r for r in done if r.get("V_initial") is not None]
    if paired and any((r.get("n_rounds") or 1) > 1 for r in done):
        b = sum(1 for r in paired if r["V_initial"] == 0 and r["V"] == 1)   # revision fixed it
        c = sum(1 for r in paired if r["V_initial"] == 1 and r["V"] == 0)   # revision broke it
        out["revision"] = {"N_paired": len(paired),
                           "VRR_initial": sum(r["V_initial"] for r in paired) / len(paired),
                           "VRR_final": sum(r["V"] for r in paired) / len(paired),
                           "fixed_by_revision": b, "broken_by_revision": c,
                           "mcnemar_p": mcnemar_exact(b, c)}
    out["rules"] = {}
    for rule in RULES:
        vk = "V_initial" if rule in INITIAL_PATCH_RULES else "V"    # the patch that rule's verdict was about
        sub = [r for r in done if r.get(f"D_{rule}") is not None and r.get(vk) is not None]
        D = [r[f"D_{rule}"] for r in sub]
        fa = [d * (1 - r[vk]) for d, r in zip(D, sub)]
        acc, sfa = sum(D), sum(fa)
        b = sum(1 for r, f in zip(sub, fa) if r["FA_gen"] == 1 and f == 0)
        c = sum(1 for r, f in zip(sub, fa) if r["FA_gen"] == 0 and f == 1)
        out["rules"][rule] = {
            "N": len(sub), "accepted": acc, "false_assurance": sfa,
            "FAR": sfa / acc if acc else None, "FAR_CI95": wilson(sfa, acc),
            "coverage": acc / len(sub) if sub else None,
            "safe_yield": (sum(d * r[vk] for d, r in zip(D, sub)) / len(sub)) if sub else None,
            "mcnemar_p_vs_repairer": mcnemar_exact(b, c) if rule != "repairer" else None,
            "primary": rule == PRIMARY,
        }
    v2 = [r for r in done if r.get("n_candidates") is not None]
    if v2:
        cit = sum(r["cites_total"] or 0 for r in v2)
        out["protocols"] = {
            "N": len(v2),
            "abstention_rate": (sum(1 for r in v2 if r.get("abstained") == 1) / len(v2)),
            "resolved_independent": sum(1 for r in v2 if r.get("resolved_in") == "independent"),
            "resolved_by_debate": sum(1 for r in v2 if r.get("resolved_in") == "debate"),
            "resolved_after_revision": sum(1 for r in v2 if r.get("resolved_in") == "after_revision"),
            "gate_failed_versions": sum(r["gate_failed_versions"] or 0 for r in v2),
            "candidates_rescued_by_gate_feedback": sum(r["gate_rescued"] or 0 for r in v2),
            "refusals": sum(r["refused"] or 0 for r in v2),
            "citations": cit, "citations_rejected": sum(r["cites_rejected"] or 0 for r in v2),
            "citation_rejection_rate": (sum(r["cites_rejected"] or 0 for r in v2) / cit) if cit else None,
            "cases_with_a_correct_candidate": sum(1 for r in v2 if r.get("V_any_candidate") == 1),
            "jury_picked_correct": sum(1 for r in v2 if r.get("jury_picked_correct") == 1),
            "VRR_oracle_best_candidate": (sum(1 for r in v2 if r.get("V_any_candidate") == 1) / len(v2)),
        }
    out["brier_gen"] = brier([(r["P_gen"], r["V"]) for r in done if r["P_gen"] is not None])
    claimed = [r["P_gen"] for r in done if r["C_gen"] == 1 and r["P_gen"] is not None]
    out["mean_conf_gen_when_claim"] = st.mean(claimed) if claimed else None
    out["precision_gen"] = (1 - out["FAR_gen"]) if out["FAR_gen"] is not None else None
    for k in ("L_analyst_ms", "L_repairer_ms", "L_reviewer_ms", "L_api_total_ms", "wall_time_s"):
        vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        out[f"median_{k}"] = st.median(vals) if vals else None
    # the breakdown of the professor's slides (same definitions): A*F failures, then S among A*F, then FAR
    af = [r for r in done if r["A"] == 1 and r["F"] == 1]
    out["professor_format"] = {
        "not_applied_or_broke_functionality": len(done) - len(af), "N": len(done),
        "applied_failed_security": sum(1 for r in af if r["S"] == 0), "applied_and_functional": len(af),
    }
    out["http_retries_total"] = sum(r["http_retries"] or 0 for r in rows)
    out["tokens_in_total"] = sum(r["input_tokens"] or 0 for r in rows)
    out["tokens_out_total"] = sum(r["output_tokens"] or 0 for r in rows)
    return out


def md_summary(groups: Dict[str, Dict[str, Any]]) -> str:
    def ci(t):
        return "–" if t[0] is None else f"{100 * t[0]:.1f}–{100 * t[1]:.1f}%"

    lines = ["# False-assurance results", "",
             "| Group | Attempts | N complete | VRR (95% CI) | FAR repairer (95% CI) | FAR reviewer (95% CI) | Caught by reviewer | McNemar p |",
             "|---|---|---|---|---|---|---|---|"]
    for g, s in groups.items():
        p = s.get("mcnemar_p_FA_gen_vs_rev")
        lines.append(
            f"| {g} | {s['attempts']} | {s['N_complete']} | "
            f"{s['sum_V']}/{s['N_complete']} = {pct(s['VRR'])} ({ci(s['VRR_CI95'])}) | "
            f"{s['sum_FA_gen']}/{s['sum_C_gen']} = {pct(s['FAR_gen'])} ({ci(s['FAR_gen_CI95'])}) | "
            f"{s['sum_FA_rev']}/{s['sum_C_rev']} = {pct(s['FAR_rev'])} ({ci(s['FAR_rev_CI95'])}) | "
            f"{s.get('reviewer_caught_false_assurance', '–')} | {'–' if p is None else f'{p:.3f}'} |")
    for g, s in groups.items():
        if not s.get("rules"):
            continue
        lines += ["", f"## Acceptance rules — {g} (tau = {TAU}, primary = {PRIMARY})", "",
                  "| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |",
                  "|---|---|---|---|---|---|---|"]
        for rule, m in s["rules"].items():
            if m["N"] == 0:
                continue
            p = m["mcnemar_p_vs_repairer"]
            lines.append(f"| {rule}{' (primary)' if m['primary'] else ''} | {m['N']} | {m['accepted']} | "
                         f"{m['false_assurance']} | {pct(m['FAR'])} ({ci(m['FAR_CI95'])}) | "
                         f"{pct(m['safe_yield'])} | {'–' if p is None else f'{p:.3f}'} |")
    for g, s in groups.items():
        pr = s.get("protocols")
        if not pr:
            continue
        lines += ["", f"## Protocols and debate — {g}", "",
                  "| Measure | Value |", "|---|---|",
                  f"| Abstained (no unanimous verdict) | {pct(pr['abstention_rate'])} of {pr['N']} |",
                  f"| Resolved: independent vote / after debate / after revision | {pr['resolved_independent']} / "
                  f"{pr['resolved_by_debate']} / {pr['resolved_after_revision']} |",
                  f"| Patch versions rejected by the mechanical gate | {pr['gate_failed_versions']} "
                  f"(candidates rescued by the feedback: {pr['candidates_rescued_by_gate_feedback']}) |",
                  f"| Citations whose quoted code does not exist | {pr['citations_rejected']} of {pr['citations']} "
                  f"({pct(pr['citation_rejection_rate'])}) |",
                  f"| Refusals | {pr['refusals']} |",
                  f"| Cases where some candidate was correct (oracle-best VRR) | {pr['cases_with_a_correct_candidate']} "
                  f"({pct(pr['VRR_oracle_best_candidate'])}) |",
                  f"| ... and the jury selected a correct one | {pr['jury_picked_correct']} |"]
    lines += ["", "## In the format of the professor's slides (same definitions)", "",
              "System claim = the repairer's claim in C0/C0g, the primary acceptance rule where there is a jury.", "",
              "| Group | Did not apply or broke functionality | Applied, functional, failed security | "
              "Positive claims not verified (FAR) | Median generation time per case | Median API time per case | "
              "Tokens in / out |",
              "|---|---|---|---|---|---|---|"]
    for g, s in groups.items():
        pf = s.get("professor_format") or {}
        rules = s.get("rules") or {}
        sysr = rules.get(PRIMARY) if (rules.get(PRIMARY) or {}).get("N") else rules.get("repairer")
        far = (f"{sysr['false_assurance']}/{sysr['accepted']} = {pct(sysr['FAR'])}" if sysr
               else f"{s['sum_FA_gen']}/{s['sum_C_gen']} = {pct(s['FAR_gen'])}")
        wt, api = s.get("median_wall_time_s"), s.get("median_L_api_total_ms")
        lines.append(f"| {g} | {pf.get('not_applied_or_broke_functionality', '–')}/{pf.get('N', '–')} | "
                     f"{pf.get('applied_failed_security', '–')}/{pf.get('applied_and_functional', '–')} | {far} | "
                     f"{'–' if wt is None else f'{wt:.0f} s'} | {'–' if api is None else f'{api / 1000:.0f} s'} | "
                     f"{s.get('tokens_in_total', 0):,} / {s.get('tokens_out_total', 0):,} |")
    lines += ["", "FAR is 'undefined' when the model made no positive repair claim.",
              "Incomplete attempts are excluded from N and listed in summary.json.",
              "Safe yield = share of attempts that were accepted AND verified.",
              "pre_revision and independent judge the INITIAL patch (V_initial): unanimity before the first revision "
              "(secondary, decisiones v1) and unanimity in round 0, before any debate (exploratory, added after the "
              "pilot C1 v2 and before the main C1)."]
    return "\n".join(lines) + "\n"


def run(runs: Path, agents: Optional[List[str]] = None, workspaces: Optional[Path] = None) -> Dict[str, Any]:
    runs = Path(runs)
    agents = agents or discover_agents(runs)
    rows = collect(runs, agents, workspaces)
    with open(runs / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLS})
    groups: Dict[str, Dict[str, Any]] = {}
    for key in sorted({r["agent"] for r in rows} | {r["group"] for r in rows}):
        sub = [r for r in rows if r["agent"] == key or r["group"] == key]
        groups[key] = summarize(sub)
    (runs / "summary.json").write_text(json.dumps(groups, indent=2), encoding="utf-8")
    (runs / "summary.md").write_text(md_summary(groups), encoding="utf-8")
    print(md_summary(groups))
    print(f"[+] wrote {runs / 'results.csv'}, summary.json, summary.md")
    return groups


def main() -> None:
    ap = argparse.ArgumentParser(description="Compute VRR / FAR from frozen generations and Vul4Py verdicts.")
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--agents", default="", help="Comma-separated; default: every agent under --runs")
    ap.add_argument("--workspaces", type=Path, default=Path(__file__).resolve().parent.parent / "workspaces")
    ap.add_argument("--tau", type=float, default=TAU, help="Pre-registered threshold for the gate rule")
    ap.add_argument("--primary", choices=RULES, default=PRIMARY, help="Pre-registered primary rule")
    a = ap.parse_args()
    globals()["TAU"], globals()["PRIMARY"] = a.tau, a.primary
    agents = [s.strip() for s in a.agents.split(",") if s.strip()] or None
    run(a.runs, agents, a.workspaces)


if __name__ == "__main__":
    main()
