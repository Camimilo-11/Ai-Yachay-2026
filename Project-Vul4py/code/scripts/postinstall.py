#!/usr/bin/env python3
"""postinstall.py -- keep evaluations on the exact post-install state of a checkout.

Why: Vul4Py's `_restore_target` runs `git clean -fdx`, which also deletes what `pip install -e .`
built inside the source tree (compiled extensions such as orjson's Rust module or brotli's C
module, setuptools_scm's generated _version.py, egg-info). After that, the unpatched code no
longer imports and every test errors -- the oracle looks broken although the scan said OK.

snapshot(proj_dir, logs_dir)  right after the install: tar every untracked or ignored file of the
                              checkout (except the venv, caches and the harness' own folders).
restore(proj_dir)             what evaluations call instead of `_restore_target`: tracked files back
                              to HEAD, everything else removed, then the snapshot extracted again.
                              Falls back to the benchmark's behaviour when no snapshot exists.
"""
from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import List

def raise_open_files_limit() -> None:
    """Large suites leak file descriptors (gradio's runs past 1024): with Ubuntu's default soft limit
    pytest dies with "Too many open files" before writing its junit and the case looks broken.
    Test runs are child processes and inherit the limit, so raising it on import covers the scan,
    the oracle control and every evaluation."""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        want = 1048576 if hard == resource.RLIM_INFINITY else min(hard, 1048576)
        if soft != resource.RLIM_INFINITY and soft < want:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    except (ImportError, ValueError, OSError):
        pass


raise_open_files_limit()

EXCLUDE_TOP = {".venv", "backported_support", "backported_tests", ".pytest_cache", ".git"}
EXCLUDE_ANY = {"__pycache__", ".pytest_cache", ".mypy_cache", ".tox", ".nox"}


def _snapshot_path(proj_dir: Path) -> Path:
    # <case>/logs/postinstall_<version>.tar, outside the checkout so git clean never touches it
    return proj_dir.parent / "logs" / f"postinstall_{proj_dir.name}.tar"


def _untracked(proj_dir: Path) -> List[str]:
    out: List[str] = []
    for extra in ([], ["--ignored"]):
        cp = subprocess.run(["git", "-C", str(proj_dir), "ls-files", "--others", "--exclude-standard",
                             *extra, "-z"], capture_output=True, text=True)
        out += [p for p in cp.stdout.split("\0") if p]
    keep = []
    for p in sorted(set(out)):
        parts = p.split("/")
        if parts[0] in EXCLUDE_TOP or any(x in EXCLUDE_ANY for x in parts) or p.endswith(".pyc"):
            continue
        keep.append(p)
    return keep


def snapshot(proj_dir: Path, logs_dir: Path | None = None) -> Path:
    proj_dir = Path(proj_dir)
    dst = _snapshot_path(proj_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    files = _untracked(proj_dir)
    with tarfile.open(dst, "w") as tf:
        for rel in files:
            full = proj_dir / rel
            if full.is_file() or full.is_symlink():
                tf.add(str(full), arcname=rel, recursive=False)
    (dst.with_suffix(".txt")).write_text("\n".join(files) + "\n", encoding="utf-8")
    return dst


def restore(target_dir: Path) -> None:
    target_dir = Path(target_dir)
    if not target_dir.exists() or not (target_dir / ".git").exists():
        return
    subprocess.run(["git", "-C", str(target_dir), "checkout", "HEAD", "--", "."],
                   capture_output=True, text=True, check=False)
    subprocess.run(["git", "-C", str(target_dir), "clean", "-fdx",
                    "-e", ".venv", "-e", "backported_support", "-e", "backported_tests"],
                   capture_output=True, text=True, check=False)
    shutil.rmtree(target_dir / "backported_support", ignore_errors=True)
    snap = _snapshot_path(target_dir)
    if snap.exists():
        with tarfile.open(snap) as tf:
            try:
                tf.extractall(target_dir, filter="tar")
            except TypeError:  # Python < 3.12
                tf.extractall(target_dir)


def install_restore_hook() -> None:
    """Make the benchmark's evaluator (run_eval / vul4py) restore to the post-install state."""
    import vul4py  # noqa: WPS433
    vul4py._restore_target = restore
