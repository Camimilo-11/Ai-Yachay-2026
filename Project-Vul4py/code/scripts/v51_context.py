#!/usr/bin/env python3
"""v51_context.py -- two harness steps of v5.1 (prereg/decisiones_v5_1.txt) for the cheap repairer.

1. related_code(): code of the same project that the shown files do not contain. v5 showed only the files
   the upstream fix changed, and in about 30 of its 49 abstentions Claude Haiku 5.5 said that the code it
   needed (a caller, a helper, a constant defined elsewhere) was not shown. This step adds, by name, the
   definitions of the names the hinted lines use (functions, classes and module constants of other project
   files) and the functions that call the hinted functions. It reads only the vulnerable checkout, never the
   fixed version, tests, docs or examples, and renders excerpts within a token budget. It says nothing about
   the fix: the names come from the hinted lines the model already sees.
2. uncovered(): the hinted line ranges a patch does not touch, with the same definition and tolerance as
   fa_metrics.hint_coverage (the coverage rule of decisiones_v4). multiagent.py --coverage-check sends them
   back to the repairer once.

Standard library only. multiagent.py imports it only with --project-context or --coverage-check.
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fa_metrics  # noqa: E402  (the coverage definition of decisiones_v4)

VERSION = "v51_context/1"
CHARS_PER_TOKEN = 3.6            # the estimate fit_context() uses for the source files
SNIPPET_MAX_LINES = 60           # a longer definition or caller is cut after its first 60 lines
MODULE_CONTEXT = 8               # lines around a module-level call site
MAX_DEFS = 6                     # definitions of names the hinted lines (then their function) use
FUNCTION_SCAN_LINES = 150        # names used in the hinted function, after those on the hinted lines
MAX_CALLERS = 4                  # functions that call the hinted functions
CALLERS_PER_NAME = 2
MAX_CANDIDATE_DEFS = 2           # a name defined in more places than this is ambiguous and skipped (unless imported)
MAX_PROJECT_FILES = 4000
MAX_FILE_BYTES = 1_500_000
SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "env", ".env", "site-packages", "node_modules", "build",
             "dist", "__pycache__", ".tox", ".nox", ".eggs", ".mypy_cache", ".pytest_cache", ".ruff_cache",
             "tests", "test", "testing", "docs", "doc", "examples", "example", "samples", "sample",
             "benchmarks", "benchmark", "demo", "demos", "fixtures"}
GENERIC = {"get", "set", "run", "call", "init", "main", "open", "close", "read", "write", "load", "save",
           "update", "parse", "format", "render", "send", "apply", "build", "process", "handle", "validate",
           "join", "split", "copy", "append", "items", "keys", "values", "str", "repr", "len", "list", "dict",
           "type", "print", "self", "cls", "super", "isinstance", "getattr", "setattr", "hasattr", "range",
           "enumerate", "zip", "map", "filter", "sorted", "min", "max", "sum", "any", "all", "int", "float",
           "bool", "bytes", "tuple", "object", "Exception", "ValueError", "TypeError", "KeyError", "None",
           "True", "False", "encode", "decode", "lower", "upper", "strip", "replace", "startswith", "endswith",
           "Optional", "Sequence", "Any", "List", "Dict", "Tuple", "Union", "Callable", "Iterable", "Mapping",
           "Type", "logger", "log", "LOGGER", "_log", "_logger"}

RELATED_INTRO = ("Related code from this project, found automatically by name (it is not in the files above): "
                 "definitions of names that the hinted lines use, and functions that call the hinted "
                 "functions. Only excerpts are shown; the omitted-line markers give the line numbers. These "
                 "files belong to the project too: you may edit them if the fix belongs there.\n\n")

COVERAGE_PATCH = """Automatic check of your answer: your patch does not change these hinted line ranges (the localization hint marks where the upstream maintainers changed the code):
{ranges}

Look again at the code at these lines. If the vulnerability involves them, extend your patch so that it fixes it there as well; if you are sure they need no change, keep your patch and say why in ## Fix. Answer again with the same four sections (## Vulnerability, ## Fix, ## Patch, ## Self-assessment): the ## Patch must be one complete unified diff against the ORIGINAL files, and the self-assessment must be about the patch you give now.
"""

COVERAGE_NOPATCH = """Automatic check of your answer: it has no patch, and the localization hint marks these line ranges as the places where the upstream maintainers changed the code:
{ranges}

Look again at the code at these lines, together with the rest of the code shown. If you can now identify the flaw, give a minimal patch for it; if you still cannot locate it with evidence, you may answer "not found" again. Answer with the same four sections (## Vulnerability, ## Fix, ## Patch, ## Self-assessment); a ## Patch must be one complete unified diff against the ORIGINAL files.
"""


def texts_sha256() -> str:
    """Fingerprint of the v5.1 prompt texts (recorded in experiment_<agent>.json)."""
    blob = "\n\x00\n".join([RELATED_INTRO, COVERAGE_PATCH, COVERAGE_NOPATCH])
    return hashlib.sha256(blob.encode()).hexdigest()


# ----------------------------------------------------------------------------- coverage check

def coverage(hint: str, diff: str) -> Optional[float]:
    return fa_metrics.hint_coverage(hint, diff)


def uncovered(hint: str, diff: str) -> List[Tuple[str, int, int]]:
    """Hinted ranges the patch does not touch (fa_metrics.hint_coverage: same parsing, tolerance 3 lines)."""
    hinted = fa_metrics._hint_ranges(hint)
    hunks = fa_metrics._patch_ranges(diff or "")
    tol = fa_metrics.HINT_TOLERANCE
    out = []
    for f, rs in hinted.items():
        for a, b in rs:
            if not any(not (hb + tol < a or ha - tol > b) for ha, hb in hunks.get(f, [])):
                out.append((f, a, b))
    return out


def ranges_text(rs: Sequence[Tuple[str, int, int]]) -> str:
    by: Dict[str, List[str]] = {}
    for f, a, b in rs:
        by.setdefault(f, []).append(f"{a}-{b}" if a != b else f"{a}")
    return "\n".join(f"- {f}: lines {', '.join(v)}" for f, v in by.items())


def coverage_message(rs: Sequence[Tuple[str, int, int]], has_patch: bool) -> str:
    return (COVERAGE_PATCH if has_patch else COVERAGE_NOPATCH).format(ranges=ranges_text(rs))


# ----------------------------------------------------------------------------- project index

def _skip_rel(rel: str) -> bool:
    parts = Path(rel).parts
    if any(p.lower() in SKIP_DIRS or p.startswith(".") for p in parts[:-1]):
        return True
    name = parts[-1]
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py" or name == "setup.py"


def project_files(root: Path) -> List[str]:
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            rel = fn if rel_dir == "." else f"{rel_dir}/{fn}"
            rel = rel.replace(os.sep, "/")
            if _skip_rel(rel):
                continue
            p = root / rel
            try:
                if p.is_symlink() or p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            out.append(rel)
            if len(out) >= MAX_PROJECT_FILES:
                return out
    return out


class Module:
    def __init__(self, rel: str, text: str, keep_tree: bool = True):
        self.rel, self.text = rel, text
        self.lines = text.splitlines()
        try:
            self.tree: Optional[ast.AST] = ast.parse(text)
        except (SyntaxError, ValueError):
            self.tree = None
        self.defs: List[Tuple[str, int, int, str]] = []      # name, start, end, kind
        self.assigns: List[Tuple[str, int, int]] = []
        if self.tree is None:
            return
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                kind = "class" if isinstance(node, ast.ClassDef) else "def"
                self.defs.append((node.name, start, node.end_lineno or node.lineno, kind))
        for node in getattr(self.tree, "body", []):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        self.assigns.append((t.id, node.lineno, node.end_lineno or node.lineno))
        if not keep_tree:          # index-only files: keep the definitions, free the syntax tree
            self.tree = None

    def enclosing(self, lo: int, hi: int) -> Optional[Tuple[str, int, int, str]]:
        """Innermost function (or class) that contains the lines lo..hi."""
        best = None
        for d in self.defs:
            if d[1] <= lo and d[2] >= hi and (best is None or d[2] - d[1] < best[2] - best[1]):
                best = d
        return best

    def enclosing_function(self, line: int) -> Optional[Tuple[str, int, int, str]]:
        best = None
        for d in self.defs:
            if d[3] == "def" and d[1] <= line <= d[2] and (best is None or d[2] - d[1] < best[2] - best[1]):
                best = d
        return best


def _load(root: Path, rel: str, cache: Dict[str, Module], shown: Dict[str, str],
          keep_tree: bool = False) -> Optional[Module]:
    if rel not in cache:
        text = shown.get(rel)
        if text is None:
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
        cache[rel] = Module(rel, text, keep_tree)
    return cache[rel]


def _used_names(mod: Module, lo: int, hi: int) -> List[str]:
    """Names and attribute names used on the lines lo..hi (in order of first use)."""
    seen: List[str] = []
    if mod.tree is None:
        return seen
    nodes = [n for n in ast.walk(mod.tree) if hasattr(n, "lineno") and lo <= n.lineno <= hi]
    nodes.sort(key=lambda n: (n.lineno, getattr(n, "col_offset", 0)))
    for n in nodes:
        name = None
        if isinstance(n, ast.Name):
            name = n.id
        elif isinstance(n, ast.Attribute):
            name = n.attr
        if name and name not in seen:
            seen.append(name)
    return seen


def _imports(mod: Module) -> Dict[str, Tuple[str, int]]:
    """name -> (dotted module, relative level) for the 'from X import name' lines of a module."""
    out: Dict[str, Tuple[str, int]] = {}
    if mod.tree is None:
        return out
    for node in ast.walk(mod.tree):
        if isinstance(node, ast.ImportFrom):
            for al in node.names:
                out[al.asname or al.name] = (node.module or "", node.level or 0)
    return out


def _resolve(mod_rel: str, dotted: str, level: int, files: Set[str]) -> List[str]:
    """Project files that a 'from <dotted> import' in mod_rel can mean."""
    cands = []
    if level:
        base = Path(mod_rel).parent
        for _ in range(level - 1):
            base = base.parent
        stem = base / Path(*dotted.split(".")) if dotted else base
        cands += [f"{stem.as_posix()}.py", f"{stem.as_posix()}/__init__.py"]
    elif dotted:
        tail = "/".join(dotted.split("."))
        cands += [f for f in sorted(files) if f.endswith(f"{tail}.py") or f.endswith(f"{tail}/__init__.py")]
    return [c.lstrip("./") for c in cands if c.lstrip("./") in files]


# ----------------------------------------------------------------------------- related code

def related_code(case_dir: Path, shown: Dict[str, str], hint: str, budget_tokens: int
                 ) -> Tuple[Dict[str, str], Dict[str, List[Tuple[int, int]]], Dict[str, Any]]:
    """(files, excerpts, record): excerpts of other project files, for multiagent.render()."""
    root = Path(case_dir) / "vulnerable"
    rec: Dict[str, Any] = {"version": VERSION, "budget_tokens": budget_tokens, "snippets": [], "skipped": []}
    hinted = fa_metrics._hint_ranges(hint)
    if not hinted or not root.is_dir():
        rec["note"] = "no line hint" if not hinted else "no vulnerable checkout"
        return {}, {}, rec
    all_files = project_files(root)
    fileset = set(all_files)
    cache: Dict[str, Module] = {}
    wanted: List[Tuple[str, str, str, int, int]] = []      # kind, name, rel, start, end
    targets: List[Tuple[str, bool]] = []                    # hinted function names (is_method) for callers
    used: List[Tuple[str, str]] = []                        # (name, hinted file): hinted lines first
    used_fn: List[Tuple[str, str]] = []                     # then the rest of the hinted function
    for rel, rngs in hinted.items():
        if not rel.endswith(".py"):
            continue
        mod = _load(root, rel, cache, shown, keep_tree=True)
        if mod is None:
            continue
        for lo, hi in rngs:
            enc = mod.enclosing(lo, hi)
            if enc and enc[3] == "def":
                name = enc[0]
                cls = next((d for d in mod.defs if d[3] == "class" and d[1] < enc[1] and d[2] >= enc[2]), None)
                if name == "__init__" and cls:
                    targets.append((cls[0], False))
                elif not (name.startswith("__") and name.endswith("__")):
                    targets.append((name, cls is not None))
            for n in _used_names(mod, max(1, lo - 2), hi + 2):
                if (n, rel) not in used:
                    used.append((n, rel))
            if enc and enc[3] == "def":
                for n in _used_names(mod, enc[1], min(enc[2], enc[1] + FUNCTION_SCAN_LINES)):
                    if (n, rel) not in used_fn:
                        used_fn.append((n, rel))
    used += [u for u in used_fn if u not in used]
    # names the shown files define are already visible
    shown_names: Set[str] = set()
    for rel in shown:
        if rel.endswith(".py"):
            m = _load(root, rel, cache, shown, keep_tree=True)
            if m is not None:
                shown_names |= {d[0] for d in m.defs} | {x[0] for x in m.assigns}
    # --- definitions of names the hinted lines use, in other project files
    index: Dict[str, List[Tuple[str, int, int, str]]] = {}
    for f in all_files:
        if f in shown:
            continue
        m = _load(root, f, cache, shown)
        if m is None:
            continue
        for name, s, e, kind in m.defs:
            index.setdefault(name, []).append((f, s, e, kind))
        for name, s, e in m.assigns:
            index.setdefault(name, []).append((f, s, e, "constant"))
    n_defs = 0
    for name, src in used:
        if n_defs >= MAX_DEFS:
            break
        if name in GENERIC or name in shown_names or len(name) < 3 or name.startswith("__"):
            continue
        src_mod = cache.get(src)
        imported = _imports(src_mod).get(name) if src_mod else None
        hits = index.get(name, [])
        if imported:
            allowed = set(_resolve(src, imported[0], imported[1], fileset))
            pref = [h for h in hits if h[0] in allowed]
            hits = pref or (hits if len(hits) <= MAX_CANDIDATE_DEFS else [])
        elif len(hits) > MAX_CANDIDATE_DEFS:
            rec["skipped"].append({"name": name, "reason": f"defined in {len(hits)} places"})
            continue
        # top-level and class-level definitions only (a nested helper of an unrelated function is noise)
        hits = sorted(hits, key=lambda h: (h[0], h[1]))[:MAX_CANDIDATE_DEFS]
        for f, s, e, kind in hits:
            wanted.append((kind if kind != "def" else "definition", name, f, s, e))
        if hits:
            n_defs += 1
    # --- functions that call the hinted functions, in other project files
    n_callers = 0
    for name, is_method in targets:
        if n_callers >= MAX_CALLERS or name in GENERIC or len(name) < 4:
            continue
        pat = re.compile((r"\." if is_method else r"(?<![\w.])") + re.escape(name) + r"\s*\(")
        found = 0
        for f in all_files:
            if f in shown or found >= CALLERS_PER_NAME:
                continue
            m = _load(root, f, cache, shown)
            if m is None:
                continue
            for i, line in enumerate(m.lines, 1):
                if not pat.search(line) or re.match(r"\s*(async\s+)?def\s", line):
                    continue
                enc = m.enclosing_function(i)
                if enc:
                    wanted.append(("caller", name, f, enc[1], enc[2]))
                else:
                    wanted.append(("caller", name, f, max(1, i - MODULE_CONTEXT), min(len(m.lines), i + MODULE_CONTEXT)))
                found += 1
                break
        n_callers += found
    # --- excerpts within the budget (first come, first kept; same file merged)
    budget_chars = int(budget_tokens * CHARS_PER_TOKEN)
    used_chars = 0
    excerpts: Dict[str, List[List[int]]] = {}
    for kind, name, f, s, e in wanted:
        m = cache[f]
        e2 = min(e, s + SNIPPET_MAX_LINES - 1)
        if any(s >= a and e2 <= b for a, b in excerpts.get(f, [])):
            continue
        size = sum(len(x) + 1 for x in m.lines[s - 1:e2])
        if used_chars + size > budget_chars:
            rec["skipped"].append({"name": name, "file": f, "reason": "budget"})
            continue
        used_chars += size
        excerpts.setdefault(f, []).append([s, e2])
        rec["snippets"].append({"kind": kind, "name": name, "file": f, "lines": [s, e2], "truncated": e2 < e})
    out_ex: Dict[str, List[Tuple[int, int]]] = {}
    for f, rs in excerpts.items():
        merged: List[List[int]] = []
        for a, b in sorted(rs):
            if merged and a <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        out_ex[f] = [(a, b) for a, b in merged]
    files = {f: cache[f].text for f in sorted(out_ex)}
    rec.update({"n_project_files": len(all_files), "targets": [t[0] for t in targets],
                "used_names": [u[0] for u in used][:60], "chars": used_chars,
                "tokens_est": round(used_chars / CHARS_PER_TOKEN)})
    return files, {f: out_ex[f] for f in files}, rec
