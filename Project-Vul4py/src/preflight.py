#!/usr/bin/env python3
"""preflight.py -- oracle control on every candidate case and the pre-registered samples. No API calls.

For each candidate (status OK in the scan, or --ids-file), eval_harness.env_check verifies on THIS
machine that functional tests pass unpatched, exploit tests fail unpatched, and the upstream fix
passes both. Writes into --runs:
    oracle_report.tsv   one row per candidate and why it is (in)valid
    oracle_valid.txt    valid cases
    main_ids.txt        main sample: every valid case not in the pilot (--main-size all, default)
                        or a random sample of N (--main-size N, --seed)
    pilot_ids.txt       pilot sample, disjoint from the main one (--pilot-size, --pilot-seed)
    split.json          sizes, seeds, commit, timestamp
Existing samples are never redrawn (only --resplit, before the main run starts).
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import random
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COLS = ["vuln_id", "healthy", "functional_unpatched", "exploit_unpatched", "functional_reference",
        "exploit_reference", "reason", "reference_notes", "seconds"]


def worker(case_dir: str, runs: str, tools_root: str, session: str) -> dict:
    sys.path.insert(0, str(HERE))
    import eval_harness
    t0 = time.time()
    try:
        r = dict(eval_harness.env_check(Path(case_dir), Path(runs), Path(tools_root), session))
    except Exception as e:  # noqa: BLE001
        r = {"healthy": False, "reason": f"preflight crash: {e!r}"}
    r["vuln_id"] = Path(case_dir).name
    r["seconds"] = round(time.time() - t0, 1)
    return r


def candidates(a) -> list:
    if a.ids_file:
        return [ln.split("#")[0].strip() for ln in Path(a.ids_file).read_text().splitlines() if ln.split("#")[0].strip()]
    rep = a.workspaces / "scan_report.tsv"
    lines = rep.read_text().splitlines()
    hdr = lines[0].split("\t")
    out = []
    for ln in lines[1:]:
        r = dict(zip(hdr, ln.split("\t")))
        try:
            passed = int(str(r.get("fv_pfes", "0")).split("/")[0])
        except ValueError:
            passed = 0
        if r.get("status") == "OK" and passed > 0:
            out.append(r["cve_id"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workspaces", type=Path, default=ROOT / "workspaces")
    ap.add_argument("--tools-root", type=Path)
    ap.add_argument("--runs", type=Path, default=ROOT / "runs" / "preflight")
    ap.add_argument("--ids-file")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--main-size", default="all", help="'all' (every valid case not in the pilot) or N")
    ap.add_argument("--pilot-size", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--pilot-seed", type=int, default=7)
    ap.add_argument("--resplit", action="store_true")
    ap.add_argument("--report-only", action="store_true", help="Only the oracle report; never write samples")
    ap.add_argument("--session", help="Reuse oracle controls already run in this session (same --runs)")
    a = ap.parse_args()
    # absolute paths: the harness runs git and patch inside each checkout, so a relative --runs
    # (as build_environment.sh passes) would make the reference patch path unreachable there
    a.workspaces, a.runs = a.workspaces.resolve(), a.runs.resolve()
    tools = (a.tools_root or a.workspaces / ".vul4py_tools").resolve()
    ids = candidates(a)
    a.runs.mkdir(parents=True, exist_ok=True)
    session = a.session or f"preflight-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    print(f"[+] oracle control on {len(ids)} cases ({a.jobs} worker(s)); no API calls", flush=True)
    rows = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.jobs, mp_context=mp.get_context("spawn")) as pool:
        futs = [pool.submit(worker, str(a.workspaces / v), str(a.runs), str(tools), session) for v in ids]
        for k, f in enumerate(as_completed(futs), 1):
            r = f.result()
            rows.append(r)
            print(f"  [{k}/{len(ids)}] {r['vuln_id']}: {'VALID' if r.get('healthy') else 'invalid'} "
                  f"func={r.get('functional_unpatched')} expl={r.get('exploit_unpatched')} "
                  f"ref={r.get('functional_reference')}/{r.get('exploit_reference')} ({r['seconds']}s) "
                  f"{r.get('reason') or ''} {r.get('reference_notes') or ''}".rstrip(), flush=True)
    rows.sort(key=lambda r: r["vuln_id"])
    with open(a.runs / "oracle_report.tsv", "w") as f:
        f.write("\t".join(COLS) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in COLS) + "\n")
    valid = sorted(r["vuln_id"] for r in rows if r.get("healthy"))
    (a.runs / "oracle_valid.txt").write_text("".join(v + "\n" for v in valid))
    print(f"[+] valid {len(valid)} of {len(ids)} -> {a.runs / 'oracle_valid.txt'}")
    if a.report_only:
        return 0
    if (a.runs / "main_ids.txt").exists() and not a.resplit:
        for n in ("main", "pilot"):
            p = a.runs / f"{n}_ids.txt"
            if p.exists():
                kept = [l.strip() for l in p.read_text().splitlines() if l.strip()]
                bad = [v for v in kept if v not in set(valid)]
                print(f"[keep] {n} sample unchanged ({len(kept)}); "
                      + (f"NO LONGER VALID here: {', '.join(bad)}" if bad else "all still valid"))
        return 0
    pilot = sorted(random.Random(a.pilot_seed).sample(valid, min(a.pilot_size, len(valid))))
    rest = [v for v in valid if v not in set(pilot)]
    if str(a.main_size).lower() == "all":
        main_ids = rest
    else:
        main_ids = sorted(random.Random(a.seed).sample(rest, min(int(a.main_size), len(rest))))
    (a.runs / "main_ids.txt").write_text("".join(v + "\n" for v in main_ids))
    (a.runs / "pilot_ids.txt").write_text("".join(v + "\n" for v in pilot))
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (a.runs / "split.json").write_text(json.dumps({
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "vul4py_commit": head,
        "session": session, "candidates": len(ids), "oracle_valid": len(valid),
        "main": {"size": len(main_ids), "requested": a.main_size, "seed": a.seed, "ids": main_ids},
        "pilot": {"size": len(pilot), "requested": a.pilot_size, "seed": a.pilot_seed, "ids": pilot},
        "wall_time_s": round(time.time() - t0, 1)}, indent=2))
    print(f"[done] valid={len(valid)} main={len(main_ids)} pilot={len(pilot)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
