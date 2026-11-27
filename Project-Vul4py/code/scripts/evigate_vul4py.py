#!/usr/bin/env python3
"""Vul4Py adapter for evigate (measurement only).

evigate is a general tool and knows nothing about Vul4Py. This adapter is the only piece that touches the
benchmark, and it hands evigate exactly what a user of any project would have:

  - the code at the vulnerable commit, exported with `git archive HEAD` (tracked files only: no .git history,
    no virtual environment, and none of the harness's backported_support/ or backported_tests/ folders,
    which hold files from the fix);
  - a report with the same information C0 and C1 received: "this project contains a security vulnerability"
    plus the localization hint (files and lines changed by the upstream fix, as in the Vul4Py paper), copied
    verbatim from the C1 record of the case;
  - the Python version and the case's build recipe: install_cmds, the commands the harness uses to build the
    VULNERABLE version, followed by one line that pins every dependency to the version found in the case's
    environment (`uv pip freeze`, with the project itself removed). The pins go after the recipe and not as
    constraints during it, because the recipe's --exclude-newer dates conflict with packages the harness
    upgraded later (e.g. pytest 8.4.2);
  - the command the harness uses to run the project's own tests, as a developer would take it from their CI;
  - the patch to verify (paso A: the final C1 patch).

The hidden oracle (fixed/, new_test_files, the fix diff) is never passed on. V comes from the existing
results.csv, so paso A needs no new oracle run.

  python scripts/evigate_vul4py.py run --evigate ~/evigate --ids-file runs/preflight/pilot_ids.txt \
      --patches runs/pilot/c1v2 --results runs/pilot/results.csv --condition c1v2 --out runs/evigate_dev
  python scripts/evigate_vul4py.py summarize --out runs/evigate_dev --results runs/pilot/results.csv --condition c1v2
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HINT_BLOCK = ("Localization hint (where the upstream maintainers changed the code; it says where to look, "
              "not how to fix):\n{hint}\n")
REPORT = "This Python project contains a security vulnerability.\n\n" + HINT_BLOCK


def load_results(path: Path, condition: str):
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # the agent column names the run (c1, c1v2, ...); fall back to the condition column
            if (r.get("agent") or r.get("condition")) == condition:
                rows[r["vuln_id"]] = r
    return rows


def export_tree(vuln_dir: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    arch = subprocess.run(["git", "-C", str(vuln_dir), "archive", "--format=tar", "HEAD"],
                          capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(dst)], input=arch.stdout, check=True)


def copy_plain(src: Path, dst: Path) -> None:
    """Copy contents only: frozen records are read-only, and shutil.copy would carry that mode over."""
    dst = Path(dst)
    if dst.exists() or dst.is_symlink():
        dst.chmod(0o644)
        dst.unlink()
    dst.write_bytes(Path(src).read_bytes())


def project_free_pins(freeze_text: str) -> list:
    """Dependency pins only: editable or local installs (the project itself) and direct URLs are dropped."""
    pins = []
    for line in freeze_text.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "-")) or " @ " in s or "://" in s:
            continue
        pins.append(s)
    return pins


def prepare(vid: str, a) -> dict:
    ws = Path(a.workspaces) / vid
    meta = json.loads((ws / "meta.json").read_text())
    rec_path = Path(a.patches) / vid / "llm_response.json"
    hint = json.loads(rec_path.read_text()).get("hint_text", "") if rec_path.exists() else ""
    inp = Path(a.out) / vid / "_input"
    inp.mkdir(parents=True, exist_ok=True)
    export_tree(ws / "vulnerable", inp / "repo")
    (inp / "report.md").write_text(REPORT.format(hint=hint.strip()), encoding="utf-8")
    py = ws / "vulnerable" / ".venv" / "bin" / "python"
    freeze = subprocess.run(["uv", "pip", "freeze", "--python", str(py)], capture_output=True, text=True)
    pins = project_free_pins(freeze.stdout if freeze.returncode == 0 else "")
    (inp / "pins.txt").write_text("\n".join(pins) + "\n", encoding="utf-8")
    copy_plain(Path(a.patches) / vid / "patch.diff", inp / "patch.diff")
    ic = meta.get("install_cmds") or []
    if isinstance(ic, str):
        try:
            ic = ast.literal_eval(ic)
        except (ValueError, SyntaxError):
            ic = [ic]
    recipe = [str(c) for c in ic]
    if pins:
        uv = 'uv pip install --no-config --python "$VIRTUAL_ENV/bin/python"'
        recipe.append(
            "printf '%s\\n' " + " ".join(shlex.quote(p) for p in pins) + " > /tmp/evigate_pins.txt && "
            f"({uv} -r /tmp/evigate_pins.txt || "
            f"while read -r p; do {uv} --no-deps \"$p\" || echo \"[pins] failed: $p\"; done < /tmp/evigate_pins.txt)")
    (inp / "setup.sh").write_text("\n".join(recipe) + "\n", encoding="utf-8")
    base = shlex.split(str(meta.get("functional_test_cmd_base", "pytest -q")))
    if base[:3] == ["python", "-m", "pytest"]:
        base = base[3:]
    elif base and base[0] in ("pytest", "py.test"):
        base = base[1:]
    files = [f for f in (ast.literal_eval(meta["baseline_test_files"]) if isinstance(meta.get("baseline_test_files"), str)
                         else meta.get("baseline_test_files") or []) if (inp / "repo" / f).exists()]
    (inp / "test_args.txt").write_text(shlex.join(base + files), encoding="utf-8")
    return {"python": str(meta.get("python_version", "")), "hint_found": bool(hint), "recipe_lines": len(ic),
            "test_files": len(files), "pins": len(pins)}


def run(a) -> int:
    ids = [l.strip() for l in Path(a.ids_file).read_text().splitlines() if l.strip() and not l.startswith("#")]
    if a.only:
        ids = [i for i in ids if i in set(a.only.split(","))]
    res = load_results(Path(a.results), a.condition)
    todo = []
    for vid in ids:
        r = res.get(vid)
        if r is None or r.get("V") in ("", None):
            print(f"[skip] {vid}: no oracle verdict (V) for {a.condition}")
            continue
        if not (Path(a.patches) / vid / "patch.diff").is_file():
            print(f"[skip] {vid}: no patch.diff")
            continue
        if (Path(a.out) / vid / "verdict.json").exists() and not a.redo:
            print(f"[done] {vid}")
            continue
        todo.append(vid)
    print(f"[+] {len(todo)} cases to verify with {a.attacker}")
    env = dict(os.environ, PYTHONPATH=str(Path(a.evigate).resolve()))
    for i, vid in enumerate(todo, 1):
        if a.redo:                       # start the case from scratch
            for d in ("case", "_input"):
                shutil.rmtree(Path(a.out) / vid / d, ignore_errors=True)
            for f in ("verdict.json", "evigate.log"):
                (Path(a.out) / vid / f).unlink(missing_ok=True)
        info = prepare(vid, a)
        inp = Path(a.out) / vid / "_input"
        case = Path(a.out) / vid / "case"
        argv = [sys.executable, "-m", "evigate", "verify", "--repo", str(inp / "repo"),
                "--report", str(inp / "report.md"), "--patch", str(inp / "patch.diff"), "--out", str(case),
                "--attacker", a.attacker, "--effort", a.effort,
                "--memory-mb", str(a.memory_mb), "--cpus", str(a.cpus),
                "--setup-script", str(inp / "setup.sh"),
                "--test-args", (inp / "test_args.txt").read_text(encoding="utf-8")]
        if info["python"]:
            argv += ["--python", info["python"]]
        t0 = time.time()
        print(f"[{i}/{len(todo)}] {vid} (python {info['python'] or 'auto'}, hint {'ok' if info['hint_found'] else 'MISSING'}, "
              f"recipe {info['recipe_lines']} lines + {info['pins']} pins, {info['test_files']} test files)", flush=True)
        with open(Path(a.out) / vid / "evigate.log", "a", encoding="utf-8") as log:
            cp = subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT)
        if cp.returncode == 3:
            print("[!] the attacker could not authenticate: stopping", flush=True)
            return 3
        v = json.loads((case / "verdict.json").read_text())["verdict"] if (case / "verdict.json").exists() else {}
        if (case / "verdict.json").exists():
            copy_plain(case / "verdict.json", Path(a.out) / vid / "verdict.json")
        print(f"      -> {v.get('status', 'ERROR')} claim={v.get('claim')} V={res[vid]['V']} "
              f"({time.time() - t0:.0f} s)", flush=True)
    return 0


def crosscheck(a) -> int:
    """Measurement only: run each case's attack tests against the OFFICIAL fix.

    An attack test that also succeeds against the official fix asks for more than the oracle does (a
    different weakness, or an out-of-scope configuration); one that the official fix stops but the model's
    patch does not is evidence of an incomplete patch. evigate never sees the official fix: this runs
    afterwards, from the adapter, on the case folders it left behind.
    """
    sys.path.insert(0, str(Path(a.evigate).resolve()))
    from evigate import runner  # noqa: E402
    from evigate.evidence import PACKAGE_ROOT  # noqa: E402
    from evigate.sandbox import Limits, Mount, Sandbox  # noqa: E402
    from evigate.workspace import Case  # noqa: E402
    sbx = Sandbox(a.backend, Limits(memory_mb=a.memory_mb, cpus=a.cpus))
    cache = Path(a.cache) if a.cache else Path.home() / ".cache" / "evigate"
    run_mounts = [Mount(PACKAGE_ROOT, "/opt/evigate", ro=True), Mount(cache / "uvpython", "/opt/uvpython", ro=True)]
    rows = []
    for case_dir in sorted(Path(a.out).glob("*/case")):
        vid = case_dir.parent.name
        if a.only and vid not in set(a.only.split(",")):
            continue
        vf = case_dir / "verdict.json"
        if not vf.exists():
            continue
        state = json.loads(vf.read_text())
        steps = state.get("steps", {})
        repro = (steps.get("poc_vulnerable") or {}).get("reproduced") or []
        has_bypass = any((case_dir / "poc_bypass").glob("test_*.py"))
        if not repro and not has_bypass:
            continue
        case = Case(case_dir)
        export_tree(Path(a.workspaces) / vid / "fixed", case.p("trees", "official"))
        for d in list(case.p("trees", "vulnerable").glob("*.egg-info")) + list(case.p("trees", "vulnerable").glob("src/*.egg-info")):
            shutil.copytree(d, case.p("trees", "official") / d.relative_to(case.p("trees", "vulnerable")), dirs_exist_ok=True)
        ptt = 120 if (steps.get("env") or {}).get("pytest_timeout") else None
        out = {"vuln_id": vid, "status": state["verdict"]["status"]}
        if repro:
            out["poc_on_official"] = runner.run_tests(
                sbx, case, run_mounts, "official", repro, "xcheck_poc_official", "/work/poc",
                extra_mounts=[Mount(case.p("poc"), "/work/poc", ro=True)], timeout_s=600, repeat=1,
                per_test_timeout=ptt)
        if has_bypass:
            out["bypass_on_official"] = runner.run_tests(
                sbx, case, run_mounts, "official", ["/work/poc_bypass"], "xcheck_bypass_official", "/work/poc_bypass",
                extra_mounts=[Mount(case.p("poc_bypass"), "/work/poc_bypass", ro=True)], timeout_s=600, repeat=1,
                per_test_timeout=ptt)
        (case_dir / "crosscheck_official.json").write_text(json.dumps(out, indent=2))
        def cnt(r):
            c = {}
            for v in (r or {}).values():
                c[v["outcome"]] = c.get(v["outcome"], 0) + 1
            return c
        rows.append(out)
        print(f"{vid:22} {out['status']:12} attacks on official: {cnt(out.get('poc_on_official'))}  "
              f"bypasses on official: {cnt(out.get('bypass_on_official'))}", flush=True)
    return 0


def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def summarize(a) -> int:
    res = load_results(Path(a.results), a.condition)
    rows = []
    for d in sorted(Path(a.out).iterdir()):
        vf = d / "verdict.json"
        if not vf.exists() or d.name not in res:
            continue
        st = json.loads(vf.read_text())
        r = res[d.name]
        rows.append({"vuln_id": d.name, "V": int(r["V"]), "claim_evidence": st["verdict"]["claim"],
                     "status": st["verdict"]["status"],
                     **{k: int(r[k]) if r.get(k) not in ("", None) else 0 for k in
                        ("D_repairer", "D_unanimous", "D_gate", "D_independent")},
                     "seconds": st.get("seconds")})
    n = len(rows)
    out = {"n": n, "rules": {}}
    for rule in ("D_repairer", "D_unanimous", "D_gate", "D_independent", "claim_evidence"):
        acc = [x for x in rows if x[rule] == 1]
        fa = sum(1 for x in acc if x["V"] == 0)
        lo, hi = wilson(fa, len(acc))
        out["rules"][rule] = {"accepted": len(acc), "false_assurance": fa,
                              "FAR": round(fa / len(acc), 3) if acc else None,
                              "FAR_ci95": [round(lo, 3), round(hi, 3)] if acc else None,
                              "safe_yield": round((len(acc) - fa) / n, 3) if n else None}
    for base in ("D_unanimous", "D_gate"):
        b = sum(1 for x in rows if x[base] == 1 and x["V"] == 0 and x["claim_evidence"] == 0)
        c = sum(1 for x in rows if x[base] == 0 and x["claim_evidence"] == 1 and x["V"] == 0)
        lost = sum(1 for x in rows if x[base] == 1 and x["V"] == 1 and x["claim_evidence"] == 0)
        gained = sum(1 for x in rows if x[base] == 0 and x["V"] == 1 and x["claim_evidence"] == 1)
        out[f"vs_{base}"] = {"false_assurances_removed": b, "false_assurances_added": c,
                             "mcnemar_p_false_assurance": round(mcnemar_exact(b, c), 4),
                             "correct_claims_lost": lost, "correct_claims_gained": gained}
    out["status_counts"] = {}
    for x in rows:
        out["status_counts"][x["status"]] = out["status_counts"].get(x["status"], 0) + 1
    Path(a.out, "summary_evigate.json").write_text(json.dumps({"summary": out, "cases": rows}, indent=2))
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--evigate", required=True, help="path to the evigate folder")
    r.add_argument("--ids-file", required=True)
    r.add_argument("--patches", required=True, help="runs/<session>/<agent> with <vid>/patch.diff")
    r.add_argument("--results", required=True, help="results.csv with V for those patches")
    r.add_argument("--condition", required=True, help="condition/agent name in results.csv (c1, c1v2, ...)")
    r.add_argument("--out", required=True)
    r.add_argument("--workspaces", default="workspaces")
    r.add_argument("--attacker", default="claude:claude-opus-5-5")
    r.add_argument("--effort", default="high")
    r.add_argument("--memory-mb", type=int, default=3072)
    r.add_argument("--cpus", type=float, default=1.5)
    r.add_argument("--only", help="comma-separated vuln ids")
    r.add_argument("--redo", action="store_true")
    r.set_defaults(func=run)
    x = sub.add_parser("crosscheck", help="measurement only: run the attack tests against the official fix")
    x.add_argument("--evigate", required=True)
    x.add_argument("--out", required=True)
    x.add_argument("--workspaces", default="workspaces")
    x.add_argument("--only")
    x.add_argument("--memory-mb", type=int, default=3072)
    x.add_argument("--cpus", type=float, default=1.5)
    x.add_argument("--backend", default="docker", choices=["docker", "local"])
    x.add_argument("--cache", help="evigate's cache folder (default ~/.cache/evigate)")
    x.set_defaults(func=crosscheck)
    s = sub.add_parser("summarize")
    s.add_argument("--out", required=True)
    s.add_argument("--results", required=True)
    s.add_argument("--condition", required=True)
    s.set_defaults(func=summarize)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
