#!/usr/bin/env python3
"""oracle_repair.py -- remove baseline tests that assert the vulnerable behaviour.

Vul4Py's functional oracle runs the VULNERABLE checkout's own tests on the patched code. When the
upstream fix intentionally changes behaviour (e.g. a default becomes stricter), some of those old
tests encode the vulnerable behaviour: they pass on the vulnerable code and FAIL with the upstream
fix itself. With them in, even the reference fix "breaks functionality" and the case looks invalid.

For every case whose oracle control (eval_harness.env_check) shows
    functional_ok (unpatched passes)  AND  exploit_discriminates  AND  reference exploit passes
    BUT the reference fix fails some functional tests,
this script deselects exactly those functional tests (the benchmark's own auto_skip does the same
for tests that fail on the fixed version) and records why in dataset/meta_overrides/<id>.json.
It refuses when more than --max-share of the functional tests would go (a bigger problem).

Usage:  python scripts/oracle_repair.py --runs runs/preflight [--workspaces workspaces] [--dry-run]
Then re-run the oracle control (multiagent.py preflight) for the repaired cases.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from auto_skip import append_deselects, collect_failing  # noqa: E402  (benchmark)

OVR = HERE.parent / "dataset" / "meta_overrides"


def _pfes(s):
    try:
        return [int(x) for x in str(s).split("/")]
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--workspaces", type=Path, default=HERE.parent / "workspaces")
    ap.add_argument("--max-share", type=float, default=0.2)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    repaired, refused = [], []
    for envp in sorted((a.runs / "_baseline").glob("*/env_check.json")):
        vid = envp.parent.name
        e = json.loads(envp.read_text())
        if e.get("healthy") or not (e.get("functional_ok") and e.get("exploit_discriminates")):
            continue
        fr, xr = _pfes(e.get("functional_reference")), _pfes(e.get("exploit_reference"))
        if not fr or not xr or xr[1] + xr[2] > 0 or xr[0] == 0 or fr[1] + fr[2] == 0:
            continue   # only: reference passes the exploit tests but fails some functional ones
        junit = a.runs / "_baseline" / "_reference" / "reference" / vid / "logs" / "functional_reference_candidate.junit.xml"
        failing = collect_failing(junit)
        total = sum(fr)
        if not failing or len(failing) > a.max_share * max(total, 1):
            refused.append((vid, len(failing), total))
            continue
        meta_p = a.workspaces / vid / "meta.json"
        meta = json.loads(meta_p.read_text())
        cmd = append_deselects(meta.get("functional_test_cmd_base", "pytest -q"), failing)
        if a.dry_run:
            print(f"[dry] {vid}: would deselect {len(failing)} of {total}: {failing[:3]}")
            continue
        op = OVR / f"{vid}.json"
        ov = json.loads(op.read_text()) if op.exists() else {}
        ov.setdefault("set", {})["functional_test_cmd_base"] = cmd
        done = sorted(set(ov.get("_oracle_repair_deselected", []) + failing))
        note = re.sub(r"\s*\[oracle_repair:[^\]]*\]", "", ov.get("_note", ""))
        tag = (f"[oracle_repair: {len(done)} baseline tests assert the vulnerable behaviour "
               f"(pass unpatched, fail with the upstream fix); deselected]")
        ov["_note"] = (note + " " if note else "") + tag
        ov["_oracle_repair_deselected"] = done
        op.write_text(json.dumps(ov, indent=2) + "\n")
        meta["functional_test_cmd_base"] = cmd
        meta_p.write_text(json.dumps(meta, indent=2))
        repaired.append(vid)
        print(f"[ok ] {vid}: deselected {len(failing)} of {total} functional tests: {failing[:3]}")
    for vid, n, total in refused:
        print(f"[refused] {vid}: {n} of {total} functional tests fail with the reference fix (> {a.max_share:.0%})")
    (a.runs / "oracle_repaired.txt").write_text("".join(v + "\n" for v in repaired))
    print(f"[done] repaired={len(repaired)} refused={len(refused)} -> {a.runs / 'oracle_repaired.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
