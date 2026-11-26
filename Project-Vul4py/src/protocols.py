#!/usr/bin/env python3
"""protocols.py -- oracle-blind checks the pipeline runs between model calls.

Nothing here runs a Vul4Py test or reads the fixed version: every check uses only what a
developer would have before knowing whether the patch is right (the vulnerable source files,
the candidate diff, a Python interpreter). The Vul4Py oracle stays hidden until the freeze.

Three protocols against hallucination:

1. Evidence must be quoted.  Models cite code as JSON objects {"file", "line", "quote"}.
   verify_evidence() checks each quote verbatim (whitespace-normalised) against the file, within
   a few lines of the cited line. Unverified citations are removed before anything is passed on,
   and the share that failed is recorded per model and per stage.

2. A patch must survive mechanical checks before any reviewer reads it (check_patch):
   it parses as a unified diff; touches only the files the model was shown and no test file;
   applies to the vulnerable files the way Vul4Py's evaluator would apply it; every touched
   Python file still compiles; the change is not a no-op (identical AST) and not oversized.
   Failures go back to the same model, verbatim. Removed public names are reported to the
   reviewers as a fact (some fixes delete a dangerous API on purpose), not rejected.

3. Refusals and empty answers are classified, not mistaken for "no vulnerability":
   is_refusal() separates "I can't help with that" from a deliberate "no patch".
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# The checks parse the project's own code, which may contain old-style escape sequences.
warnings.filterwarnings("ignore", category=SyntaxWarning)

# ----------------------------------------------------------------------------- evidence

_FENCE_RE = re.compile(r"```([A-Za-z0-9_+-]*)[ \t]*\n(.*?)```", re.DOTALL)
_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").strip())


def json_blocks(md: str) -> List[object]:
    out = []
    for lang, body in _FENCE_RE.findall(md or ""):
        if lang.lower() not in ("json", ""):
            continue
        try:
            out.append(json.loads(body))
        except Exception:  # noqa: BLE001
            continue
    return out


def extract_evidence(md: str, key: str = "evidence") -> List[Dict[str, object]]:
    """Every {"file","line","quote"} object found in JSON blocks, at any depth under `key`."""
    found: List[Dict[str, object]] = []

    def walk(o):
        if isinstance(o, dict):
            if {"file", "quote"} <= set(o.keys()):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for b in json_blocks(md):
        walk(b)
    return found


def verify_quote(text: str, line: Optional[int], quote: str, window: int = 4) -> str:
    """'exact' if `quote` appears verbatim (whitespace-normalised) in `text` within `window`
    lines of `line`; 'relocated' if it appears elsewhere in the file (real code, wrong line
    number); 'not_found' otherwise. Multi-line quotes are matched against joined lines."""
    q = _norm(quote)
    if len(q) < 3:
        return "not_found"
    lines = text.splitlines()
    if isinstance(line, int) and 1 <= line <= len(lines) + window:
        lo = max(0, line - 1 - window)
        hi = min(len(lines), line + window + q.count(" ") // 6 + 2)
        if q in _norm(" ".join(lines[lo:hi])):
            return "exact"
    if q in _norm(" ".join(lines)):
        return "relocated"
    return "not_found"


def verify_evidence(items: Iterable[Dict[str, object]], files: Dict[str, str],
                    window: int = 4) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    """Split citations into (grounded, rejected). `files` maps repo-relative path -> text;
    a citation may name any of them (original files, or a candidate's patched view).
    Grounded = the quoted code exists in the named file ('exact' or 'relocated')."""
    ok, bad = [], []
    for it in items:
        f = str(it.get("file", "")).strip()
        if f.startswith(("a/", "b/")) and f[2:] in files:
            f = f[2:]
        f = f[2:] if f.startswith("./") else f
        try:
            line = int(it.get("line")) if it.get("line") is not None else None
        except (TypeError, ValueError):
            line = None
        text = files.get(f)
        status = verify_quote(text, line, str(it.get("quote", "")), window) if text is not None else "unknown_file"
        rec = {**it, "file": f, "check": status}
        (ok if status in ("exact", "relocated") else bad).append(rec)
    return ok, bad


# ----------------------------------------------------------------------------- diffs

@dataclass
class FilePatch:
    old: str
    new: str
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    hunks: int = 0


def parse_diff(diff: str) -> List[FilePatch]:
    files: List[FilePatch] = []
    cur: Optional[FilePatch] = None
    old = None
    for ln in (diff or "").splitlines():
        if ln.startswith("--- "):
            old = ln[4:].split("\t")[0].strip()
            continue
        if ln.startswith("+++ ") and old is not None:
            new = ln[4:].split("\t")[0].strip()
            cur = FilePatch(old=_strip_prefix(old), new=_strip_prefix(new))
            files.append(cur)
            old = None
            continue
        if cur is None:
            continue
        if ln.startswith("@@"):
            cur.hunks += 1
        elif ln.startswith("+") and not ln.startswith("+++"):
            cur.added.append(ln[1:])
        elif ln.startswith("-") and not ln.startswith("---"):
            cur.removed.append(ln[1:])
    return files


def _strip_prefix(p: str) -> str:
    if p in ("/dev/null", "dev/null"):
        return "/dev/null"
    return p[2:] if p.startswith(("a/", "b/")) else p


def _looks_test(path: str) -> bool:
    lo = path.lower()
    return "test" in lo  # same heuristic as Vul4Py's prepare.is_test_path


def apply_in_scratch(diff: str, files: Dict[str, str], extra_root: Optional[Path] = None
                     ) -> Tuple[bool, str, Dict[str, str], str]:
    """Apply `diff` to copies of `files` (rel -> text) in a scratch directory, trying the same
    strategies as Vul4Py's run_eval (git apply -p1/-p0/-p2/-p3, then patch -pN with fuzz).
    Returns (applied, method, patched_files, error)."""
    tmp = Path(tempfile.mkdtemp(prefix="gate_"))
    try:
        for rel, text in files.items():
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")
        pf = tmp / ".candidate.diff"
        pf.write_text(diff if diff.endswith("\n") else diff + "\n", encoding="utf-8")
        err = ""
        for strip in (1, 0, 2, 3):
            cp = subprocess.run(["git", "apply", f"-p{strip}", "--whitespace=nowarn", str(pf)],
                                cwd=tmp, capture_output=True, text=True)
            if cp.returncode == 0:
                return True, f"git apply -p{strip}", _read_back(tmp, files), ""
            err = err or cp.stderr.strip()
        if shutil.which("patch"):
            for strip in (1, 0, 2, 3):
                cp = subprocess.run(["patch", f"-p{strip}", "-i", str(pf), "--no-backup-if-mismatch", "-f",
                                     "--silent"], cwd=tmp, capture_output=True, text=True)
                if cp.returncode == 0:
                    return True, f"patch -p{strip} (fuzzy)", _read_back(tmp, files), ""
                for rel, text in files.items():  # patch may have half-applied: reset
                    (tmp / rel).write_text(text, encoding="utf-8")
        return False, "", {}, err[:2000]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _read_back(tmp: Path, files: Dict[str, str]) -> Dict[str, str]:
    out = {}
    for rel in files:
        p = tmp / rel
        out[rel] = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    for p in tmp.rglob("*"):  # new files created by the patch
        rel = str(p.relative_to(tmp))
        if p.is_file() and rel not in out and not rel.startswith(".candidate"):
            out[rel] = p.read_text(encoding="utf-8", errors="replace")
    return out


def public_api(src: str) -> Optional[set]:
    """Top-level public functions/classes/assignments and public methods of public classes."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            names.add(node.name)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        not sub.name.startswith("_") or sub.name in ("__init__", "__call__")):
                    names.add(f"{node.name}.{sub.name}")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_"):
                    names.add(t.id)
    return names


def compile_check(rel: str, text: str, python: Optional[str]) -> Optional[str]:
    """None if the file byte-compiles with the case's interpreter (or this one), else the error.
    compile() also catches what ast.parse lets through (misplaced __future__ imports,
    'return' outside a function, invalid nonlocal, ...)."""
    if not rel.endswith(".py"):
        return None
    if python and Path(python).exists():
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(text)
            name = f.name
        try:
            cp = subprocess.run([python, "-W", "ignore", "-c",
                                 "import sys; compile(open(sys.argv[1],encoding='utf-8').read(), sys.argv[2], 'exec')",
                                 name, rel], capture_output=True, text=True, timeout=60)
            return None if cp.returncode == 0 else (cp.stderr.strip().splitlines() or ["syntax error"])[-1][:300]
        finally:
            Path(name).unlink(missing_ok=True)
    try:
        compile(text, rel, "exec")
        return None
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"


@dataclass
class GateResult:
    ok: bool
    failures: List[str]
    details: Dict[str, object]
    patched: Dict[str, str]

    def feedback(self) -> str:
        lines = ["Your patch was checked automatically before review and was rejected:"]
        for f in self.failures:
            lines.append(f"- {f}")
        if self.details.get("apply_error"):
            lines.append("\n`git apply` said:\n```\n" + str(self.details["apply_error"])[:1500] + "\n```")
        lines.append("\nWrite a corrected diff against the ORIGINAL files shown above (not on top of your "
                     "previous diff). Keep context lines exactly as in the files.")
        return "\n".join(lines)


def check_patch(diff: str, files: Dict[str, str], python: Optional[str] = None,
                max_changed_lines: int = 600) -> GateResult:
    """Mechanical gate. `files` = the source files the model was shown (rel -> text)."""
    fails: List[str] = []
    det: Dict[str, object] = {}
    fps = parse_diff(diff)
    det["files_touched"] = sorted({fp.new if fp.new != "/dev/null" else fp.old for fp in fps})
    det["changed_lines"] = sum(len(fp.added) + len(fp.removed) for fp in fps)
    if not diff.strip() or not fps:
        return GateResult(False, ["empty: no unified diff found"], det, {})
    for fp in fps:
        target = fp.new if fp.new != "/dev/null" else fp.old
        if _looks_test(target):
            fails.append(f"scope: the patch edits a test file ({target}); tests may not be changed")
        elif target not in files:
            fails.append(f"scope: the patch edits {target}, which is not one of the files you were shown")
    if det["changed_lines"] > max_changed_lines:
        fails.append(f"size: {det['changed_lines']} changed lines; keep the fix minimal")
    applied, method, patched, err = apply_in_scratch(diff, files)
    det["applies"], det["apply_method"] = applied, method
    if not applied:
        fails.append("apply: the diff does not apply to the original files")
        det["apply_error"] = err
        return GateResult(False, fails, det, {})
    changed = [r for r in patched if patched.get(r) != files.get(r)]
    deleted = [r for r in files if r in patched and patched[r] == "" and files[r] != ""]
    det["files_deleted"] = deleted
    det["files_changed"] = changed
    if not changed:
        fails.append("no-op: applying the diff leaves every file unchanged")
    for rel in changed:
        err_c = compile_check(rel, patched[rel], python)
        if err_c:
            fails.append(f"syntax: {rel} no longer compiles: {err_c}")
            continue
        if rel.endswith(".py") and rel in files:
            before, after = public_api(files[rel]), public_api(patched[rel])
            if before is not None and after is not None:
                gone = sorted(before - after)
                if gone:   # a warning, not a failure: some fixes remove a dangerous API on purpose
                    det.setdefault("api_removed", {})[rel] = gone[:20]
            try:
                if ast.dump(ast.parse(files[rel])) == ast.dump(ast.parse(patched[rel])):
                    fails.append(f"no-op: {rel} changes only comments or formatting")
            except SyntaxError:
                pass
    return GateResult(not fails, fails, det, patched if applied else {})


# ----------------------------------------------------------------------------- refusals

_REFUSAL = re.compile(
    r"(I\s*(?:can(?:no|')t|cannot|won't|will not|am (?:not able|unable)) (?:help|assist|provide|comply|"
    r"do that|create|write)|I'm sorry,? but|I must decline|against (?:my|our) (?:policy|guidelines)|"
    r"not able to help with)", re.IGNORECASE)


def is_refusal(text: str, has_diff: bool) -> bool:
    if has_diff:
        return False
    head = (text or "")[:1200]
    return bool(_REFUSAL.search(head))


# ----------------------------------------------------------------------------- hints

def localization_hint(case_dir: Path, meta: dict, files: Sequence[str]) -> str:
    """The Vul4Py paper's direct-prompt hint: files and line ranges (in the vulnerable version)
    changed by the upstream fix. Says WHERE to look, never HOW to fix."""
    fixed = case_dir / "fixed"
    vref = subprocess.run(["git", "-C", str(case_dir / "vulnerable"), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip() or meta["vulnerable_ref"]
    fref = subprocess.run(["git", "-C", str(fixed), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip() or meta["fixed_ref"]
    out = []
    for rel in files:
        cp = subprocess.run(["git", "-C", str(fixed), "diff", "-U0", vref, fref,
                             "--", rel], capture_output=True, text=True)
        ranges = []
        for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", cp.stdout, re.MULTILINE):
            start, n = int(m.group(1)), int(m.group(2) or 1)
            lo, hi = (start, start + n - 1) if n > 0 else (start, start)
            ranges.append((lo, hi))
        if ranges:
            merged: List[List[int]] = []
            for lo, hi in sorted(ranges):
                if merged and lo <= merged[-1][1] + 3:
                    merged[-1][1] = max(merged[-1][1], hi)
                else:
                    merged.append([lo, hi])
            out.append(f"- {rel}: lines " + ", ".join(f"{a}-{b}" if a != b else f"{a}" for a, b in merged))
    return "\n".join(out)
