#!/usr/bin/env python3
"""v51_devcheck.py -- feasibility check of v5.1 on the 5 development cases (prereg/decisiones_v5_1.txt).

Looks only at whether the two arms ran as designed: every record complete, the sections within their budgets,
the coverage check fired when the patch missed a hinted range, no leakage flag. How many cases were repaired
is printed for the record but is not a criterion (nothing is tuned on it).

  python scripts/v51_devcheck.py --runs runs/v51_dev [--agents c0mr51,c0m51]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--agents", default="c0mr51,c0m51")
    ap.add_argument("--context-budget", type=int, default=4000)
    ap.add_argument("--rag-budget", type=int, default=3000)
    a = ap.parse_args()
    problems = []
    for agent in [x.strip() for x in a.agents.split(",") if x.strip()]:
        recs = sorted((a.runs / agent).glob("*/llm_response.json"))
        print(f"\n== {agent}: {len(recs)} cases")
        if not recs:
            problems.append(f"{agent}: no records")
        for rp in recs:
            r = json.loads(rp.read_text())
            vid = r["vuln_id"]
            ev = rp.parent / "eval.json"
            v = json.loads(ev.read_text()) if ev.exists() else {}
            pc = r.get("project_context") or {}
            rag = r.get("rag") or {}
            cov = ((r.get("candidates") or [{}])[0].get("coverage_check") or [{}])[0]
            g = r.get("generator") or {}
            print(f"{vid:22s} {r['generation_status']:10s} ctx={len(pc.get('snippets', []))}/{pc.get('tokens_est', 0)}t "
                  f"rag={'-' if not rag else (str(len(rag.get('hits', []))) + 'ej/' + str(rag.get('section_tokens_est')) + 't')} "
                  f"cwe={','.join(rag.get('case_cwe', []) or []) or '-'} cov={cov.get('coverage_before')}->{cov.get('action')} "
                  f"claim={g.get('claim')} parche={g.get('patch_bytes')}B V={int(bool(v.get('plausible'))) if v else '?'}")
            if r["generation_status"] != "complete":
                problems.append(f"{agent}/{vid}: {r.get('incomplete_reason')}")
            if "error" in pc:
                problems.append(f"{agent}/{vid}: project context failed {pc['error']}")
            if pc.get("tokens_est", 0) > a.context_budget:
                problems.append(f"{agent}/{vid}: project context over budget")
            if rag.get("leak_flag"):
                problems.append(f"{agent}/{vid}: leakage flag")
            if rag and (rag.get("section_tokens_est") or 0) > a.rag_budget * 1.05:
                problems.append(f"{agent}/{vid}: RAG section over budget")
            if cov.get("uncovered") and cov.get("action") in (None, "none"):
                problems.append(f"{agent}/{vid}: coverage check did not fire")
        # the new steps must be active somewhere (an empty section everywhere would mean a path problem)
        if recs and not any((json.loads(rp.read_text()).get("project_context") or {}).get("snippets") for rp in recs):
            problems.append(f"{agent}: no case got related project code")
        if recs and agent.startswith("c0mr") and not any(
                ((json.loads(rp.read_text()).get("rag") or {}).get("section_tokens_est") or 0) > 0 for rp in recs):
            problems.append(f"{agent}: no case got a RAG section")
    print("\n" + ("OK: v5.1 runs as designed; go on with the 95 cases" if not problems else
                  "CHECK BEFORE THE 95 CASES:\n- " + "\n- ".join(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
