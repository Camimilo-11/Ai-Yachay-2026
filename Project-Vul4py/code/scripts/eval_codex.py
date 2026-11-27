#!/usr/bin/env python3
"""eval_codex.py -- Vul4Py verdict for the patches written in the Codex pilot (no API calls).

Reads piloto_codex/resultados/<run>/<caso>/{patch.diff,autoevaluacion.json}, maps caso_N to its CVE with
piloto_codex_mapa.csv, evaluates every patch with the same harness as multiagent.py (eval_harness), and
prints per run: A, F, S, V, the repairer's claim and false assurance, then VRR and FAR, next to the API
result of the pilot v1 (runs/pilot/results.csv) for the same cases.

Patches are applied in place in the case checkouts, so it refuses to run while multiagent.py runs.

    python scripts/eval_codex.py --results ~/piloto_codex/resultados --map ~/piloto_codex_mapa.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import eval_harness  # noqa: E402
from fa_metrics import classify_eval  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, required=True, help="piloto_codex/resultados")
    ap.add_argument("--map", type=Path, required=True, help="piloto_codex_mapa.csv (caso,cve,repo)")
    ap.add_argument("--workspaces", type=Path, default=SCRIPTS.parent / "workspaces")
    ap.add_argument("--tools-root", type=Path)
    ap.add_argument("--out", type=Path, default=SCRIPTS.parent / "runs" / "codex_eval")
    ap.add_argument("--api-results", type=Path, default=SCRIPTS.parent / "runs" / "pilot" / "results.csv")
    ap.add_argument("--runs", default="", help="comma-separated run folders to evaluate (default: all)")
    a = ap.parse_args()
    busy = subprocess.run(["pgrep", "-f", "scripts/multiagent.py"], capture_output=True, text=True).stdout.strip()
    if busy:
        sys.exit("multiagent.py is running (pid " + busy.replace("\n", ", ") + "): patches are applied in place in the "
                 "checkouts, so wait until it finishes.")
    tools = (a.tools_root or a.workspaces / ".vul4py_tools").resolve()
    cve = {r["caso"]: r["cve"] for r in csv.DictReader(open(a.map))}
    api = {}
    if a.api_results.exists():
        for r in csv.DictReader(open(a.api_results)):
            if r["agent"] == "rep_gpt-6.2-sol" and r["status"] == "complete":
                api[r["vuln_id"]] = (r["V"], r["C_gen"])
    wanted = {s.strip() for s in a.runs.split(",") if s.strip()}
    rows = []
    for run_dir in sorted(p for p in a.results.iterdir() if p.is_dir()):
        if wanted and run_dir.name not in wanted:
            continue
        for case_dir in sorted(p for p in run_dir.iterdir() if p.is_dir() and p.name in cve):
            vid = cve[case_dir.name]
            out = a.out / run_dir.name / vid
            out.mkdir(parents=True, exist_ok=True)
            src = case_dir / "patch.diff"
            shutil.copy(src, out / "patch.diff") if src.exists() else (out / "patch.diff").write_text("")
            label = "codex_" + run_dir.name.replace(".", "_")
            ev = eval_harness.evaluate_patch(a.workspaces / vid, out, label, tools)
            status, reason, A, F, S = classify_eval(ev)
            V = A * F * S if status == "complete" else None
            sa = json.loads((case_dir / "autoevaluacion.json").read_text()) if (case_dir / "autoevaluacion.json").exists() else {}
            claim = sa.get("claim")
            fa = claim * (1 - V) if (V is not None and claim is not None) else None
            row = {"run": run_dir.name, "caso": case_dir.name, "cve": vid, "status": status, "A": A, "F": F, "S": S,
                   "V": V, "claim": claim, "confidence": sa.get("confidence"), "FA": fa,
                   "func": ev.get("func_pfes"), "exploit": ev.get("exploit_pfes"), "notes": ev.get("notes", ""),
                   "api_v1_V": api.get(vid, ("", ""))[0], "api_v1_claim": api.get(vid, ("", ""))[1]}
            rows.append(row)
            print(f"{run_dir.name:28s} {case_dir.name} {vid:16s} A={A} F={F} S={S} V={V} claim={claim} FA={fa} "
                  f"| API v1 V={row['api_v1_V']}  {row['notes'][:60]}", flush=True)
    if not rows:
        sys.exit("no patches found under " + str(a.results))
    a.out.mkdir(parents=True, exist_ok=True)
    with open(a.out / "codex_eval.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\nrun                          N  VRR   claims  FA  FAR")
    for run in sorted({r["run"] for r in rows}):
        sub = [r for r in rows if r["run"] == run and r["V"] is not None]
        c = sum(r["claim"] or 0 for r in sub)
        fa = sum(r["FA"] or 0 for r in sub)
        print(f"{run:28s} {len(sub):2d}  {sum(r['V'] for r in sub)}/{len(sub)}  {c:6d}  {fa:2d}  "
              + (f"{fa / c:.0%}" if c else "–"))
    if api:
        v = [int(api[k][0]) for k in api]
        print(f"{'API v1 gpt-6.2-sol (C0)':28s} {len(v):2d}  {sum(v)}/{len(v)}")
    print(f"\nTable: {a.out / 'codex_eval.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
