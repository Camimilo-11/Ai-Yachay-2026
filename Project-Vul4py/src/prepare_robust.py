#!/usr/bin/env python3
"""prepare_robust.py -- Vul4Py's prepare.py, unchanged, except for one failure mode:

a plain `git clone` only fetches branches and tags. When an upstream fix commit is reachable only
from a pull-request ref (CVE-2024-47164 in gradio, for example), `git checkout <sha>` fails and the
case is lost. Here, if the checkout fails, the commit is fetched by its SHA (GitHub serves any
reachable commit) and the checkout is retried. Same arguments as prepare.py.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import prepare  # noqa: E402


def clone_and_checkout(target: Path, repo_url: str, ref: str):
    if target.exists():
        raise RuntimeError(f"{target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    prepare.run(["git", "clone", repo_url, str(target)], check=True)
    cp = subprocess.run(["git", "-C", str(target), "checkout", ref], capture_output=True, text=True)
    if cp.returncode != 0:
        print(f"[prepare_robust] {ref[:12]} not on any branch or tag of {repo_url}; fetching it by SHA", flush=True)
        prepare.run(["git", "-C", str(target), "fetch", "origin", ref], check=True)
        prepare.run(["git", "-C", str(target), "checkout", ref], check=True)


prepare.clone_and_checkout = clone_and_checkout

if __name__ == "__main__":
    prepare.main()
