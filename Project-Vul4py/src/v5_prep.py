#!/usr/bin/env python3
"""v5_prep.py -- two small steps of decisiones_v5.

  copy-c0  Copy the frozen C0 records into the v5 runs directory without their verdicts, so that
           multiagent.py (same --runs and --session as the other arms) re-evaluates them with the v5
           harness and calls no model. Every frozen file is checked against the hashes in its record.
             python scripts/v5_prep.py copy-c0 --from runs/final/c0 runs/confirm/c0 --to runs/v5/c0 \
                 --ids-file runs/preflight/v5_ids.txt
  gate     The feasibility gate on the 5 development cases (the cheap model without RAG): it fails when
           in 3 or more cases the model refused or gave no patch that applies.
             python scripts/v5_prep.py gate --results runs/v5_dev/results.csv --agent c0m
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

SKIP = {"eval.json", "logs"}          # verdicts and oracle logs: produced again by the v5 harness


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def copy_c0(sources, dest: Path, ids) -> int:
    found = {}
    for src in sources:
        for d in sorted(Path(src).iterdir()):
            if d.is_dir() and (d / "llm_response.json").exists():
                if d.name in found:
                    sys.exit(f"{d.name} is in two sources: {found[d.name]} and {d}")
                found[d.name] = d
    missing = [v for v in ids if v not in found]
    if missing:
        sys.exit(f"no frozen C0 record for {missing}")
    dest.mkdir(parents=True, exist_ok=True)
    for vid in ids:
        src, out = found[vid], dest / vid
        rec = json.loads((src / "llm_response.json").read_text())
        bad = [n for n, h in (rec.get("sha256") or {}).items() if sha256_file(src / n) != h]
        if bad:
            sys.exit(f"{vid}: frozen files changed after the freeze: {bad}")
        if out.exists():
            sys.exit(f"{out} already exists: this copy runs once, before the v5 runs")
        shutil.copytree(src, out, ignore=lambda _d, names: [n for n in names if n in SKIP])
        print(f"[copy] {vid}: {src} -> {out} ({rec.get('generation_status')})")
    print(f"[+] {len(ids)} frozen C0 records ready in {dest}; none has an eval.json")
    return 0


def gate(results: Path, agent: str) -> int:
    rows = [r for r in csv.DictReader(open(results, newline="", encoding="utf-8")) if r.get("agent") == agent]
    fails = []
    for r in rows:
        refused = (r.get("refused") or "").strip() in ("1", "True", "true")
        applies = (r.get("A") or "").strip() in ("1", "1.0")
        if refused or not applies:
            fails.append((r["vuln_id"], "refused" if refused else "no patch that applies"))
    print(f"{agent}: {len(rows)} development cases; {len(fails)} without a usable patch: {fails}")
    ok = len(rows) == 5 and len(fails) < 3
    print("GATE: " + ("PASSED, keep the model" if ok else "FAILED, switch to deepseek:deepseek-flash")
          + ("" if len(rows) == 5 else f" (expected 5 cases, found {len(rows)})"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("copy-c0")
    s.add_argument("--from", dest="sources", type=Path, nargs="+", required=True)
    s.add_argument("--to", type=Path, required=True)
    s.add_argument("--ids-file", type=Path, required=True)
    s = sub.add_parser("gate")
    s.add_argument("--results", type=Path, required=True)
    s.add_argument("--agent", default="c0m")
    a = ap.parse_args(argv)
    if a.cmd == "copy-c0":
        return copy_c0(a.sources, a.to, [x for x in a.ids_file.read_text().split() if x])
    return gate(a.results, a.agent)


if __name__ == "__main__":
    sys.exit(main())
