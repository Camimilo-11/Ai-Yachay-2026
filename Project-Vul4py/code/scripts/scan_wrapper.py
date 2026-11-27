#!/usr/bin/env python3
"""scan_wrapper.py -- run Vul4Py's own CLI (vul4py.py) unchanged, plus two hooks:

1. after every install (create_and_install), record the files the install created inside the
   checkout (postinstall.snapshot), so evaluations can restore the exact post-install state instead
   of deleting compiled modules and generated files with `git clean -fdx`;
2. after each case's scan, free the venvs nothing will use again (disk): fixed/.venv always
   (evaluations run every test in vulnerable/.venv) and both venvs when the case is not OK
   (every scan starts from fresh venvs anyway: _scan_one_cve calls wipe_all_venvs first).

Usage: identical to vul4py.py, e.g.
    python scripts/scan_wrapper.py --workspace-root workspaces scan --jobs 2
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import postinstall  # noqa: E402
import vul4py  # noqa: E402

_orig = vul4py.create_and_install


def create_and_install(tools_root, proj_dir, meta, logs_dir):
    _orig(tools_root, proj_dir, meta, logs_dir)
    postinstall.snapshot(Path(proj_dir), Path(logs_dir))


vul4py.create_and_install = create_and_install

_orig_scan = vul4py._scan_one_cve


def _scan_one_cve(args_for_worker):
    r = _orig_scan(args_for_worker)
    case = Path(args_for_worker[0]).resolve()
    for v in (("fixed",) if r.get("status") == "OK" else ("vulnerable", "fixed")):
        shutil.rmtree(case / v / ".venv", ignore_errors=True)
    return r


# picklable by reference from the pool workers (looked up as vul4py._scan_one_cve)
_scan_one_cve.__module__, _scan_one_cve.__qualname__ = "vul4py", "_scan_one_cve"
vul4py._scan_one_cve = _scan_one_cve

if __name__ == "__main__":
    vul4py.main()
