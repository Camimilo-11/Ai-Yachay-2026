#!/usr/bin/env python3
"""eval_harness.py -- the Vul4Py verdict for one patch, on the exact post-install state.

Same verdict as Vul4Py's run_eval._evaluate_one (same apply strategies, same functional and
exploit commands, same junit-based pass rules, same fixture overlay), with two harness fixes:

1. Restore to the post-install state (postinstall.restore) instead of `git clean -fdx`, which
   deletes build products of `pip install -e .` (compiled modules, generated _version.py) and
   makes every test error on cases such as orjson, brotli or setuptools_scm projects.
2. Rebuild after applying a patch that touches compiled sources (.c/.h/.rs/.pyx...), so a C or
   Rust fix is actually exercised; restore() then brings back the vulnerable build.

env_check() is the oracle control (functional passes unpatched, exploit fails unpatched, the
upstream fix passes both), with the upstream fix taken over every non-test code file the fix
commit changed -- not only .py files -- so cases fixed in C, Rust or templates can be verified.

Two options for v5 (decisiones_v5), both OFF unless set, so earlier runs reproduce unchanged:

3. VUL4PY_CLEAN_ENV=1 -- the project's build and test commands run without the caller's secrets
   (every variable whose name has a KEY, APIKEY, TOKEN, SECRET, PASSWORD, PASSWD, CREDENTIAL(S) or
   AUTH part, or an LLM-provider prefix, is unset in the test shell; names only reach the log).
   Without it the tests inherit the harness environment: in the confirmation run (Nov 26, 2026)
   smolagents' test_call_different_providers_without_key (CVE-2025-5120) expects no key, found
   OPENAI_API_KEY and sent it to Cerebras and Mistral, and the case was lost to the oracle control.
4. VUL4PY_FLAKE_RERUN=N -- when a functional run fails 1..VUL4PY_FLAKE_MAX tests (default 3), the
   suite runs again up to N times, and a test counts as failed only if it fails in every run.
   tornado's SimpleHTTPClientTestCase::test_connection_refused (CVE-2024-52804) passed in 0.002 s
   on the vulnerable tree and timed out (5 s) with the upstream fix, which only changes
   tornado/httputil.py: one flaky test took the case out of the confirmation. Exploit runs are
   never rerun.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# Per pytest run cap: Vul4Py's 900 s default is too tight for the largest suites (sqlfluff runs 6,000+
# tests) on a 2-vCPU machine; set before vul4py is imported, which reads it once.
os.environ.setdefault("VUL4PY_TEST_TIMEOUT", "3600")

import postinstall  # noqa: E402
import run_eval  # noqa: E402  (benchmark: fixture overlay)
import vul4py  # noqa: E402    (benchmark: test runners, junit parsing)

COMPILED_EXT = (".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".rs", ".pyx", ".pxd", ".pxi")
DOC_RE = re.compile(r"(^|/)(docs?|changelog|changes|history|news)(/|\.|$)|\.(md|rst)$", re.I)
DEFAULT_REBUILD = "python -m pip install --no-deps -e ."

# --- v5 options (docstring items 3 and 4); read once per process, like VUL4PY_TEST_TIMEOUT -------
CLEAN_ENV = os.environ.get("VUL4PY_CLEAN_ENV", "0").strip() == "1"
FLAKE_RERUNS = max(0, int(os.environ.get("VUL4PY_FLAKE_RERUN", "0").strip() or 0))
FLAKE_MAX = max(1, int(os.environ.get("VUL4PY_FLAKE_MAX", "3").strip() or 3))
HARNESS_TAG = "eval_harness/2" + (
    "" if not (CLEAN_ENV or FLAKE_RERUNS) else
    " + v5(" + ", ".join(x for x in ("clean env" if CLEAN_ENV else "",
                                     f"flake rerun x{FLAKE_RERUNS} if <= {FLAKE_MAX} fail" if FLAKE_RERUNS else "") if x) + ")")

# Name parts (split on "_") that mark a secret. AUTH as a whole part: SSH_AUTH_SOCK goes, GIT_AUTHOR_NAME
# stays (projects whose tests commit to a temporary repository need it). PWD/OLDPWD are never matched.
SECRET_PARTS = {"KEY", "APIKEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "CREDENTIALS", "AUTH"}
# LLM-provider prefixes also catch base URLs (OPENAI_BASE_URL) that would point a test at our endpoint.
# No AWS_/HF_ prefix: their keys and tokens already match SECRET_PARTS, and paths such as HF_HOME stay.
PROVIDER_PREFIXES = ("OPENAI", "ANTHROPIC", "DEEPSEEK", "CLAUDE", "MISTRAL", "CEREBRAS", "GROQ",
                     "GEMINI", "COHERE", "TOGETHER", "LITELLM")
_SHELL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def secret_env_names(environ=None) -> List[str]:
    """Variables of `environ` (default: this process) that the tests must not see."""
    env = os.environ if environ is None else environ
    out = []
    for k in env:
        if not _SHELL_NAME.fullmatch(k) or k.startswith("VUL4PY_"):
            continue
        up = k.upper()
        if set(up.split("_")) & SECRET_PARTS or up.startswith(PROVIDER_PREFIXES):
            out.append(k)
    return sorted(out)


_ORIG_RUN_IN_VENV = vul4py.run_in_venv


def _run_in_venv_clean(tools_root, cmd, proj_dir, logfile, check, extra_pythonpath=None, timeout=None):
    """vul4py.run_in_venv with the secrets unset inside the test shell. Only the command string changes,
    so the harness process (and the model calls running beside it) keep their environment."""
    names = secret_env_names()
    if names:
        cmd = "unset " + " ".join(names) + "; " + cmd
    return _ORIG_RUN_IN_VENV(tools_root, cmd, proj_dir, logfile, check,
                             extra_pythonpath=extra_pythonpath, timeout=timeout)


if CLEAN_ENV:
    vul4py.run_in_venv = _run_in_venv_clean   # run_functional / run_exploit_for_target look it up here


def _pf(j) -> Any:
    return None if not j else f"{j['passed']}/{j['failed']}/{j['errored']}/{j['skipped']}"


def _failed_ids(j) -> List[str]:
    return sorted({f"{c.get('classname', '')}::{c.get('name', '')}" for c in (j or {}).get("failed_cases", [])})


def _move_logs(logs: Path, src_stem: str, dst_stem: str) -> None:
    for ext in ("log", "junit.xml"):
        src = logs / f"{src_stem}.{ext}"
        if src.exists():
            src.replace(logs / f"{dst_stem}.{ext}")


def _functional(tools_root: Path, proj: Path, meta: Dict[str, Any], logs: Path, name: str):
    """Functional suite on `proj` (the vulnerable checkout, patched or not); logs end up as
    logs/functional_<name>.{log,junit.xml}. Returns (rc, junit dict or None, ok, flake info or None).
    ok is Vul4Py's rule (no failed or errored test; rc == 0 when there is no junit). With
    VUL4PY_FLAKE_RERUN=N and 1..FLAKE_MAX failures, each identified by its junit test case, the suite
    reruns up to N times and ok means that no test failed in every run."""
    for p in logs.glob(f"functional_{name}_rerun*.*"):    # stale files from an earlier evaluation
        p.unlink()
    rc = vul4py.run_functional(tools_root, proj, meta, logs)
    _move_logs(logs, f"functional_{proj.name}", f"functional_{name}")
    j = vul4py._parse_junit(logs / f"functional_{name}.junit.xml")
    ok = (j["failed"] == 0 and j["errored"] == 0) if j is not None else rc == 0
    if ok or not FLAKE_RERUNS or j is None:
        return rc, j, ok, None
    n_bad, first = j["failed"] + j["errored"], _failed_ids(j)
    flake: Dict[str, Any] = {"first_failed": first, "reruns": [], "persistent": first}
    if n_bad > FLAKE_MAX or len(first) != n_bad:
        flake["skipped"] = (f"{n_bad} failures > {FLAKE_MAX}" if n_bad > FLAKE_MAX
                            else "failures not identified by test case in the junit")
        return rc, j, ok, flake
    persistent = set(first)
    for i in range(1, FLAKE_RERUNS + 1):
        rrc = vul4py.run_functional(tools_root, proj, meta, logs)
        _move_logs(logs, f"functional_{proj.name}", f"functional_{name}_rerun{i}")
        jr = vul4py._parse_junit(logs / f"functional_{name}_rerun{i}.junit.xml")
        ids = _failed_ids(jr)
        flake["reruns"].append({"rc": rrc, "pfes": _pf(jr), "failed": ids})
        if jr is None or len(ids) != jr["failed"] + jr["errored"]:
            break                                  # crashed or unidentified failures: keep the first verdict
        persistent &= set(ids)
        if not persistent:
            break
    flake["persistent"] = sorted(persistent)
    return rc, j, not persistent, flake


def _is_test(path: str) -> bool:
    return "test" in path.lower()   # Vul4Py's prepare.is_test_path


def checkout_refs(case: Path) -> tuple:
    """(vulnerable HEAD, fixed HEAD) as checked out on disk. meta.json's refs can be wrong: the
    benchmark's override for CVE-2024-53861 points vulnerable_ref to a commit that does not exist in
    the repository, while the checkout (and the scan) use the fix's real parent."""
    def head(d: Path) -> str:
        return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True,
                              text=True).stdout.strip()
    return head(case / "vulnerable"), head(case / "fixed")


def code_files_changed(case: Path, include_deleted: bool = True) -> List[str]:
    """Non-test, non-doc files the fix commit added, modified or deleted (renames count as a
    deletion plus an addition). Deleted files matter: some fixes remove the vulnerable module
    (kedro's ShelveStore, CVE-2024-9701), and Vul4Py's prepare.py, which keeps only A/M .py files,
    leaves such a case with no code at all."""
    vref, fref = checkout_refs(case)
    cp = subprocess.run(["git", "-C", str(case / "fixed"), "diff", "--no-renames", "--name-status",
                         vref, fref], capture_output=True, text=True)
    out = []
    for ln in cp.stdout.splitlines():
        parts = ln.split("\t")
        if not parts or parts[0][:1] not in (("A", "M", "D") if include_deleted else ("A", "M")):
            continue
        path = parts[-1]
        if _is_test(path) or DOC_RE.search(path):
            continue
        out.append(path)
    return out


def reference_diff(case: Path, full: bool = True) -> str:
    """The benchmark's own fix as a patch on the vulnerable checkout, produced by git itself
    (deletions and renames included, so `git apply` reproduces the fixed tree for these files).
    full=True: every non-test, non-doc file the fix changed (C/Rust/templates too);
    full=False: only the .py files in meta new_code_files (the previous behaviour)."""
    meta = vul4py.load_meta(case)
    rels = code_files_changed(case) if full else meta.get("new_code_files", [])
    if not rels:
        return ""
    vref, fref = checkout_refs(case)
    cp = subprocess.run(["git", "-C", str(case / "fixed"), "diff", "--no-renames", "--no-color",
                         vref, fref, "--", *rels], capture_output=True)
    # bytes, not text=True: universal newlines would turn CRLF lines (pymdown's snippets.py) into LF
    # and the patch would no longer apply to the file it came from
    return cp.stdout.decode("utf-8", "surrogateescape")


def overlay_test_data(case: Path, target: Path) -> List[str]:
    """For the exploit run: test DATA files (non-.py, in a tests/ or test/ folder) the fix added or modified.
    Vul4Py overlays the new test files and the fixtures the fix added, but not fixtures it changed
    (eduMFA's RADIUS dictionary gains the attribute its new test sends), so the upstream fix itself
    failed its own exploit test. Test data only: code under test is never copied."""
    vref, fref = checkout_refs(case)
    cp = subprocess.run(["git", "-C", str(case / "fixed"), "diff", "--no-renames", "--name-status", vref, fref],
                        capture_output=True, text=True)
    done = []
    for line in cp.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or parts[0] not in ("M", "A"):
            continue
        rel = parts[1]
        # any test folder, also nested ones such as libnmap/test/files/ (Vul4Py's own overlay of added
        # fixtures only looks at a top-level tests/ or test/)
        if set(rel.split("/")[:-1]) & {"tests", "test"} and not rel.endswith(".py"):
            src, dst = case / "fixed" / rel, target / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
                done.append(rel)
    return done


def touches_compiled(diff: str) -> bool:
    return any(p.endswith(COMPILED_EXT) for p in re.findall(r"^\+\+\+ b/(\S+)", diff, re.MULTILINE))


def _apply(vuln_dir: Path, patch_path: Path) -> bool:
    # git and patch run with cwd=vuln_dir: the patch path must not be relative to the caller's cwd
    vuln_dir, patch_path = Path(vuln_dir).resolve(), Path(patch_path).resolve()
    for strip in (1, 0, 2, 3):
        cp = subprocess.run(["git", "apply", f"-p{strip}", str(patch_path)], cwd=str(vuln_dir),
                            capture_output=True, text=True)
        if cp.returncode == 0:
            return True
    for strip in (1, 0, 2, 3):
        cp = subprocess.run(["patch", f"-p{strip}", "-i", str(patch_path), "--no-backup-if-mismatch", "-f"],
                            cwd=str(vuln_dir), capture_output=True, text=True)
        if cp.returncode == 0:
            return True
    # Last resort, for files with CRLF line endings: a model sees (and patches) them with LF, which the
    # mechanical gate accepts; whitespace-insensitive context matching applies the same change here.
    for strip in (1, 0, 2, 3):
        cp = subprocess.run(["git", "apply", f"-p{strip}", "--ignore-whitespace", str(patch_path)],
                            cwd=str(vuln_dir), capture_output=True, text=True)
        if cp.returncode == 0:
            return True
    return False


def evaluate_patch(case: Path, run_dir: Path, label: str, tools_root: Path) -> Dict[str, Any]:
    """Vul4Py verdict for run_dir/patch.diff on case's vulnerable checkout; writes run_dir/eval.json."""
    case, run_dir = Path(case).resolve(), Path(run_dir).resolve()
    vul4py._restore_target = postinstall.restore   # used inside vul4py/run_eval helpers too
    meta = vul4py.load_meta(case)
    vuln_dir, fixed_dir, logs = case / "vulnerable", case / "fixed", case / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    patch_path = run_dir / "patch.diff"
    v: Dict[str, Any] = {"agent": label, "vuln_id": case.name, "apply_ok": False, "func_ok": False,
                         "exploit_ok": False, "plausible": False, "func_pfes": None, "exploit_pfes": None,
                         "notes": "", "elapsed_s": None,
                         "harness": HARNESS_TAG.replace("eval_harness/2", "eval_harness/2 (post-install restore)", 1)}
    t0 = time.time()
    run_dir.mkdir(parents=True, exist_ok=True)
    if not patch_path.exists() or not patch_path.read_text(errors="replace").strip():
        v["notes"] = "empty patch"
        (run_dir / "eval.json").write_text(json.dumps(v, indent=2))
        return v
    postinstall.restore(vuln_dir)
    try:
        if not _apply(vuln_dir, patch_path):
            v["notes"] = "patch did not apply"
            return v
        v["apply_ok"] = True
        diff = patch_path.read_text(errors="replace")
        if touches_compiled(diff):
            cmd = meta.get("rebuild_cmd") or DEFAULT_REBUILD
            cp = vul4py.run_in_venv(tools_root, cmd, vuln_dir, logs / f"rebuild_{label}.log", check=False)
            v["rebuild"] = {"cmd": cmd, "rc": cp.returncode}
            if cp.returncode != 0:
                v["notes"] = "rebuild after patch failed (patch breaks the build)"
                return v
        func_rc, j, func_ok, flake = _functional(tools_root, vuln_dir, meta, logs, f"{label}_candidate")
        if j is not None:
            v["func_pfes"] = _pf(j)
        v["func_ok"] = func_ok
        if flake:
            v["flake_rerun"] = flake
        run_eval._overlay_fixture_additions(fixed_dir, vuln_dir)
        overlay_test_data(case, vuln_dir)
        exp_rc = vul4py.run_exploit_for_target(tools_root, fixed_dir, vuln_dir, "vulnerable", meta, logs)
        v["exploit_rc"] = exp_rc
        for ext in ("log", "junit.xml"):
            src = logs / f"exploit_vulnerable.{ext}"
            if src.exists():
                src.replace(logs / f"exploit_{label}_candidate.{ext}")
        j = vul4py._parse_junit(logs / f"exploit_{label}_candidate.junit.xml")
        if j is not None:
            v["exploit_pfes"] = f"{j['passed']}/{j['failed']}/{j['errored']}/{j['skipped']}"
            v["exploit_ok"] = j["passed"] > 0 and j["failed"] == 0 and j["errored"] == 0
        else:
            # no junit: the exploit killed pytest (e.g. a segfault in a C extension, rc >= 128),
            # which Vul4Py's scan counts as "vulnerability triggered"
            v["exploit_ok"] = exp_rc == 0
            if exp_rc >= 128:
                v["notes"] = (v["notes"] + "; " if v["notes"] else "") + f"exploit crashed the test process (rc={exp_rc})"
        v["plausible"] = bool(v["apply_ok"] and v["func_ok"] and v["exploit_ok"])
        return v
    except Exception as e:  # noqa: BLE001
        v["notes"] = (v["notes"] + "; " if v["notes"] else "") + f"harness crash: {e!r}"
        return v
    finally:
        postinstall.restore(vuln_dir)
        v["elapsed_s"] = round(time.time() - t0, 1)
        (run_dir / "eval.json").write_text(json.dumps(v, indent=2))
        dst = run_dir / "logs"
        dst.mkdir(exist_ok=True)
        for kind in ("functional", "exploit"):
            for ext in ("log", "junit.xml"):
                p = logs / f"{kind}_{label}_candidate.{ext}"
                if p.exists():
                    shutil.copy(p, dst / p.name)
        for p in logs.glob(f"functional_{label}_candidate_rerun*.*"):
            shutil.copy(p, dst / p.name)


def env_check(case: Path, runs_root: Path, tools_root: Path, session: str) -> Dict[str, Any]:
    """Oracle control on this machine, through the same harness the candidates use."""
    case, runs_root = Path(case).resolve(), Path(runs_root).resolve()
    out = runs_root / "_baseline" / case.name / "env_check.json"
    if out.exists():
        prev = json.loads(out.read_text())
        if prev.get("session") == session:
            return prev
    vul4py._restore_target = postinstall.restore
    meta = vul4py.load_meta(case)
    vuln, fixed, logs = case / "vulnerable", case / "fixed", case / "logs"
    res: Dict[str, Any] = {"session": session, "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "harness": HARNESS_TAG}
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        postinstall.restore(vuln)
        _, jf, jf_ok, jf_flake = _functional(tools_root, vuln, meta, logs, "envcheck")
        if jf_flake:
            res["functional_unpatched_flake"] = jf_flake
        run_eval._overlay_fixture_additions(fixed, vuln)
        overlay_test_data(case, vuln)
        xrc = vul4py.run_exploit_for_target(tools_root, fixed, vuln, "vulnerable", meta, logs)
        res["exploit_unpatched_rc"] = xrc
        for ext in ("log", "junit.xml"):
            src = logs / f"exploit_vulnerable.{ext}"
            if src.exists():
                src.replace(logs / f"exploit_envcheck_unpatched.{ext}")
        je = vul4py._parse_junit(logs / "exploit_envcheck_unpatched.junit.xml")
        postinstall.restore(vuln)
        ref_dir = runs_root / "_baseline" / "_reference" / "reference" / case.name
        ref_dir.mkdir(parents=True, exist_ok=True)
        with open(ref_dir / "patch.diff", "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
            fh.write(reference_diff(case))
        vr = evaluate_patch(case, ref_dir, "reference", tools_root)

        res.update({"functional_unpatched": _pf(jf), "exploit_unpatched": _pf(je),
                    "functional_reference": vr.get("func_pfes"), "exploit_reference": vr.get("exploit_pfes"),
                    "reference_apply_ok": vr.get("apply_ok"), "reference_notes": vr.get("notes"),
                    "reference_files": code_files_changed(case)})
        if vr.get("flake_rerun"):
            res["functional_reference_flake"] = vr["flake_rerun"]
        res["functional_ok"] = bool(jf and jf["passed"] > 0 and jf_ok)
        res["exploit_discriminates"] = bool((je and (je["failed"] + je["errored"]) > 0)
                                            or (je is None and isinstance(xrc, int) and xrc >= 128))
        res["reference_verified"] = bool(vr.get("plausible"))
    except Exception as e:  # noqa: BLE001
        res["error"] = repr(e)
        postinstall.restore(vuln)
    try:
        fr = subprocess.run([str(vuln / ".venv" / "bin" / "python"), "-m", "pip", "freeze"],
                            capture_output=True, text=True, timeout=120)
        (out.parent / "pip_freeze.txt").write_text(fr.stdout, encoding="utf-8")
        shutil.copy(case / "meta.json", out.parent / "meta.json")
    except Exception as e:  # noqa: BLE001
        res["freeze_error"] = repr(e)
    res["healthy"] = bool(res.get("functional_ok") and res.get("exploit_discriminates")
                          and res.get("reference_verified"))
    failed = [k for k in ("functional_ok", "exploit_discriminates", "reference_verified") if not res.get(k)]
    res["reason"] = "" if res["healthy"] else ("oracle invalid here: " + ", ".join(f"not {k}" for k in failed))
    out.write_text(json.dumps(res, indent=2))
    for name in ("functional_envcheck", "exploit_envcheck_unpatched"):
        for ext in ("log", "junit.xml"):
            p = logs / f"{name}.{ext}"
            if p.exists():
                shutil.copy(p, out.parent / p.name)
    for p in logs.glob("functional_envcheck_rerun*.*"):
        shutil.copy(p, out.parent / p.name)
    return res
