#!/usr/bin/env python3
"""vuln_only.py -- deselect functional tests that fail on the VULNERABLE version and pass on the fixed one.

Vul4Py's functional oracle reruns the vulnerable checkout's own tests on a candidate patch: a test that
already fails on the unpatched code cannot tell a patch that breaks functionality from one that does
not, and with it in the suite the case is not usable (scan status NON_ORACLE or UNEXPECTED). These
tests either check the fixed behaviour (extra exploit tests) or are timing-dependent. auto_skip.py
removes tests that fail on the fixed version; this removes the mirror set, for the cases named, and
records why in dataset/meta_overrides/<id>.json.

Usage:  python scripts/vuln_only.py --workspaces workspaces --ids CVE-...,CVE-... [--max 10]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from auto_skip import append_deselects, collect_failing, strip_sandbox  # noqa: E402

OVR = HERE.parent / "dataset" / "meta_overrides"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspaces", type=Path, required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--max", type=int, default=10, help="refuse when more tests than this would go")
    a = ap.parse_args()
    for vid in [i for i in a.ids.split(",") if i]:
        case = a.workspaces / vid
        logs = case / "logs"
        vuln = set(collect_failing(logs / "functional_vulnerable.junit.xml", case / "vulnerable"))
        fixed = set(collect_failing(logs / "functional_fixed.junit.xml", case / "fixed"))
        only = sorted(t for t in vuln - fixed if "::" in t)     # single tests, never whole files
        if not only:
            print(f"[noop] {vid}")
            continue
        if len(only) > a.max:
            print(f"[refused] {vid}: {len(only)} tests fail only on the vulnerable version (> {a.max})")
            continue
        meta_p = case / "meta.json"
        meta = json.loads(meta_p.read_text())
        cmd = append_deselects(strip_sandbox(vid, "functional_test_cmd_base",
                                             meta.get("functional_test_cmd_base", "pytest -q")), only)
        op = OVR / f"{vid}.json"
        ov = json.loads(op.read_text()) if op.exists() else {}
        ov.setdefault("set", {})["functional_test_cmd_base"] = cmd
        done = sorted(set(ov.get("_vuln_only_deselected", [])) | set(only))
        note = re.sub(r"\s*\[vuln_only:[^\]]*\]", "", ov.get("_note", ""))
        ov["_note"] = (note + f" [vuln_only: {len(done)} functional tests fail on the vulnerable version "
                       "and pass with the fix; they cannot detect a broken patch; deselected]").strip()
        ov["_vuln_only_deselected"] = done
        op.write_text(json.dumps(ov, indent=2) + "\n")
        meta["functional_test_cmd_base"] = cmd
        meta_p.write_text(json.dumps(meta, indent=2))
        print(f"[ok ] {vid}: {only}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
