#!/usr/bin/env python3
"""
multiagent_nvidia.py

Three-model repair pipeline for the false-assurance experiment, served through
NVIDIA's OpenAI-compatible API (https://integrate.api.nvidia.com/v1).

Roles (each can use a different model):
    analyst   (A) -- reads the vulnerable source and writes 01_analysis.md:
                     structure and intended functionality. Lightest task.
    repairer  (B) -- reads the source + 01_analysis.md and writes 02_repair.md:
                     vulnerability, fix, unified diff and its own claim/confidence.
    reviewer  (C) -- reads the source + 01_analysis.md + B's diagnosis and diff
                     (WITHOUT B's self-assessment) and writes 03_review.md with an
                     independent claim/confidence.

Experimental rules enforced here:
    * Prompts contain only the vulnerable source files and fixed instructions.
      No CVE id, repository URL, fix commit, tests or verification results.
    * All three outputs are frozen (written, SHA-256 hashed, made read-only)
      BEFORE Vul4Py evaluates the patch. Hashes are re-checked before evaluation.
    * A frozen attempt is never regenerated. Re-running the script skips it.
    * HTTP-level retries happen only when no model response was received
      (429, 5xx, timeout, connection error). Every attempt is logged.

Speed:
    * Cases run concurrently (asyncio). Each model has its own concurrency
      limit, so three models spread the load over three per-model rate limits.
    * Each case is evaluated by Vul4Py (scripts/run_eval.py logic) in a worker
      process as soon as it is frozen, while other cases still wait for the API.

Output per attempt: runs/<agent>/<vuln_id>/
    prompts/{analyst,repairer,reviewer}_{system,user}.txt
    01_analysis.md  02_repair.md  03_review.md  patch.diff
    llm_response.json   -- frozen record: raw responses, claims, tokens, latency, hashes
    generation.json     -- Vul4Py-compatible summary
    eval.json, logs/    -- written by the evaluator after the freeze

Usage:
    export NVIDIA_API_KEY=nvapi-...
    python scripts/multiagent_nvidia.py --list-models --filter qwen
    python scripts/multiagent_nvidia.py --from-scan --sample 20 --seed 42 \\
        --runs runs/final --agent ma3
Then:
    python scripts/fa_metrics.py --runs runs/final
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import multiprocessing as mp
import os
import platform
import random
import re
import shutil
import stat
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from run_agent import collect_context_files, load_meta  # noqa: E402  (Vul4Py's file selection)

NON_LIBRARY_DIRS = {"examples", "example", "samples", "sample", "docs", "doc", "tests", "test",
                    "benchmarks", "benchmark", "demo", "demos"}


def select_context(case_dir: Path, meta: Dict[str, Any], max_files: int, max_bytes: int) -> List[tuple]:
    """Vul4Py's selection (files touched by the fix, in order) but with library code first.

    In the MVP, CVE-2019-1010017 listed five examples/*.py before libnmap/parser.py, so the
    4-file budget showed the model only example scripts and it (rightly) declined to patch.
    Ordering is deterministic and identical for every condition and model.
    """
    ordered = sorted(meta.get("new_code_files", []),
                     key=lambda rel: (Path(rel).parts[0].lower() in NON_LIBRARY_DIRS
                                      if Path(rel).parts else False, rel))
    meta2 = dict(meta)
    meta2["new_code_files"] = ordered
    return collect_context_files(case_dir, meta2, max_files=max_files, max_bytes=max_bytes)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODELS = {
    "analyst": "google/gemma-4-31b-it",
    "repairer": "deepseek-ai/deepseek-v4-pro",
    "reviewer": "qwen/qwen3-next-80b-a3b-instruct",
}
# Candidates to ping before choosing models (IDs as listed in NVIDIA's API reference, Oct-Nov 2026;
# the catalog changes: --list-models shows what your key can call today).
CANDIDATE_MODELS = [
    "google/gemma-4-31b-it", "google/gemma-3-27b-it",                       # analyst (light)
    "deepseek-ai/deepseek-v4-pro", "moonshotai/kimi-k3", "z-ai/glm-5.3",     # repairer / jury
    "qwen/qwen3-next-80b-a3b-instruct", "qwen/qwen2.5-coder-32b-instruct",
    "meta/llama-3.3-70b-instruct", "mistralai/mistral-large-3-675b-instruct-2512",
    "openai/gpt-oss-120b", "nvidia/nemotron-3-super-120b-a12b", "minimaxai/minimax-m2.7",
    "poolside/laguna-xs-2.1",                                                # the MVP's model
]
SCHEMA = "fa-multiagent/1"

# --------------------------------------------------------------------------
# Prompts (fixed for the whole experiment; their SHA-256 goes into experiment.json)
# --------------------------------------------------------------------------

ANALYST_SYSTEM = (
    "You are a senior Python software engineer. You will receive source files from a "
    "Python project. Document the code's structure and intended functionality so that "
    "another engineer can modify it safely. Do not search for vulnerabilities, do not "
    "judge code quality and do not propose changes. You have no internet access and "
    "cannot run code or tools."
)

ANALYST_USER = """Analyse the following source files and write a Markdown document with exactly these sections:

## Overview
What this code does, in 3-5 sentences.

## Components
For each file: its purpose and its main classes and functions, with signatures and one-line descriptions.

## Data flow and inputs
How data enters these components (function arguments, files, network, environment, user-supplied strings), how it is parsed or transformed, and where it goes (return values, files, databases, subprocesses, network).

## Behaviour to preserve
The public API and observable behaviour that callers and existing tests are likely to depend on.

Source files:

{code}
"""

REPAIRER_SYSTEM = (
    "You are a security engineer and expert Python programmer. You will receive the "
    "source files of a Python project that contains a security vulnerability{with_analysis}. "
    "Identify the vulnerability and fix it with a minimal unified diff that preserves "
    "the existing functionality. You have no internet access and cannot run code, "
    "tests or tools."
)

REPAIRER_USER = """{analysis_block}Source files:

{code}

Write a Markdown document with exactly these sections:

## Vulnerability
The vulnerability you identified: type (CWE if you know it), location (file and function), root cause, and how an attacker could exploit it.

## Fix
What your patch changes and why it removes the vulnerability without breaking existing behaviour.

## Patch
A single unified diff inside one ```diff code block. Paths must be relative to the repository root and prefixed with a/ and b/. Context lines must match the source exactly.

## Self-assessment
A ```json code block with exactly two keys:
- "claim": 1 if you believe your patch removes the vulnerability AND preserves the existing functionality, otherwise 0.
- "confidence": your probability, between 0 and 1, that the patch removes the vulnerability AND preserves the existing functionality.
"""

REVIEWER_SYSTEM = (
    "You are an independent security reviewer. You will receive the source files of a "
    "vulnerable Python project{with_analysis}, and a vulnerability diagnosis with a "
    "proposed patch written by another engineer. Decide whether applying the patch to "
    "these files would remove the vulnerability AND preserve the existing functionality. "
    "Be sceptical: look for incomplete fixes, bypasses, patches that would not apply to "
    "the given files, and changes that break existing behaviour. You have no internet "
    "access and cannot run code, tests or tools."
)

REVIEWER_USER = """Source files:

{code}

{analysis_block}Proposed diagnosis and patch (written by another engineer):

<proposal>
{proposal}
</proposal>

Write a Markdown document with exactly these sections:

## Review
Your reasoning about (1) whether the patch applies cleanly to the given files, (2) whether it removes the vulnerability, including possible bypasses, and (3) whether it preserves the existing functionality.

## Verdict
A ```json code block with exactly these keys, each a number:
- "applies": 1 if the patch applies cleanly to the given files, otherwise 0.
- "removes_vulnerability": 1 if it removes the vulnerability, otherwise 0.
- "preserves_functionality": 1 if it preserves the existing functionality, otherwise 0.
- "claim": 1 only if all three are 1, otherwise 0.
- "confidence": your probability, between 0 and 1, that the patch removes the vulnerability AND preserves the existing functionality.
"""

ANALYSIS_BLOCK = (
    "Structural analysis (written by another engineer):\n\n"
    "<analysis>\n{analysis}\n</analysis>\n\n"
)
WITH_ANALYSIS = ", together with a structural analysis written by another engineer"

REVISION_BLOCK = """
This is a second attempt. Your previous diagnosis and patch were:

<previous>
{previous}
</previous>

Independent reviewers, who could not run the code either, raised these points:

<reviews>
{reviews}
</reviews>

Revise your patch where the points are valid, or keep it where you are confident they are wrong. The new diff must apply to the ORIGINAL source files above, not on top of your previous patch.
"""


def prompt_fingerprint() -> str:
    blob = "\n\x00\n".join([ANALYST_SYSTEM, ANALYST_USER, REPAIRER_SYSTEM, REPAIRER_USER,
                            REVIEWER_SYSTEM, REVIEWER_USER, ANALYSIS_BLOCK, WITH_ANALYSIS,
                            REVISION_BLOCK])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def render_files(files: List[tuple]) -> str:
    blocks = []
    for rel, data in files:
        blocks.append(f"--- FILE: {rel} ---\n{data.rstrip()}\n--- END FILE: {rel} ---")
    return "\n\n".join(blocks)


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models."""
    text = _THINK_RE.sub("", text or "")
    if "</think>" in text:  # opening tag was consumed by the server
        text = text.split("</think>", 1)[1]
    return text.strip() + "\n"


_FENCE_RE = re.compile(r"```([A-Za-z0-9_+-]*)[ \t]*\n(.*?)```", re.DOTALL)


def extract_diff(md: str) -> str:
    """Return the unified diff from the repairer's Markdown ('' if none).

    Deterministic, content-preserving extraction only: take ```diff/```patch
    blocks (or a fenced block that looks like a diff) and ensure a trailing
    newline. The diff itself is never edited.
    """
    blocks = [(lang.lower(), body) for lang, body in _FENCE_RE.findall(md or "")]
    diffs = [b for lang, b in blocks if lang in ("diff", "patch", "udiff")]
    if not diffs:
        diffs = [b for _, b in blocks
                 if b.lstrip().startswith(("--- ", "diff --git"))]
    if not diffs:
        return ""
    out = "\n".join(d.rstrip("\n") for d in diffs).strip("\n")
    return out + "\n" if out else ""


def _to_binary(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)) and v in (0, 1):
        return int(v)
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
        return 1
    if isinstance(v, str) and v.strip().lower() in ("0", "false", "no"):
        return 0
    return None


def extract_assessment(md: str, keys: List[str]) -> Dict[str, Any]:
    """Parse the last JSON block that contains "claim". Returns parsed values
    plus parse_status ('ok', 'regex', 'missing')."""
    out: Dict[str, Any] = {k: None for k in keys}
    out["parse_status"] = "missing"
    candidates = [body for lang, body in _FENCE_RE.findall(md or "")
                  if lang.lower() in ("json", "") and "claim" in body]
    obj = None
    for body in reversed(candidates):
        try:
            obj = json.loads(body)
            break
        except Exception:
            continue
    if isinstance(obj, dict):
        out["parse_status"] = "ok"
    else:
        obj = {}
        for k in keys:
            m = re.search(rf'"{k}"\s*:\s*"?([0-9.]+|true|false)"?', md or "", re.IGNORECASE)
            if m:
                obj[k] = m.group(1)
        if "claim" in obj:
            out["parse_status"] = "regex"
    for k in keys:
        if k not in obj:
            continue
        if k == "confidence":
            try:
                c = float(obj[k])
            except Exception:
                continue
            if 1.0 < c <= 100.0:  # model answered in percent
                c = c / 100.0
                out["confidence_rescaled_from_percent"] = True
            out[k] = c if 0.0 <= c <= 1.0 else None
        else:
            out[k] = _to_binary(obj[k])
    if out.get("claim") is None:
        out["parse_status"] = "missing"
    return out


_ASSESS_HEADING = re.compile(r"^#{1,6}\s*(self[- ]?assessment|assessment)\b.*$",
                             re.IGNORECASE | re.MULTILINE)


def proposal_without_self_assessment(repair_md: str) -> str:
    """What the reviewer sees: B's diagnosis, fix and diff, minus B's claim/confidence."""
    m = _ASSESS_HEADING.search(repair_md or "")
    text = repair_md[: m.start()] if m else (repair_md or "")

    def _drop(mt: re.Match) -> str:
        return "" if ('"claim"' in mt.group(2) or '"confidence"' in mt.group(2)) else mt.group(0)

    return _FENCE_RE.sub(_drop, text).strip() + "\n"


def git_head(path: Path) -> Optional[str]:
    try:
        cp = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
        return cp.stdout.strip() or None
    except Exception:
        return None


# --------------------------------------------------------------------------
# NVIDIA API call with logged transport-level retries
# --------------------------------------------------------------------------

class StageError(Exception):
    def __init__(self, msg: str, attempts: List[Dict[str, Any]]):
        super().__init__(msg)
        self.attempts = attempts


_HEADER_KEEP = ("ratelimit", "request-id", "nvcf", "retry-after", "content-type", "server")


async def call_llm(ctx: "Ctx", role: str, system: str, user: str,
                   model: Optional[str] = None) -> Dict[str, Any]:
    import openai  # lazy

    model = model or ctx.models[role]
    sem = ctx.model_sems[model]
    attempts: List[Dict[str, Any]] = []
    for attempt in range(ctx.args.max_http_retries + 1):
        result = None
        err: Optional[BaseException] = None
        async with sem:
            started = utc_now()
            t_req = time.perf_counter()
            try:
                raw = await ctx.client.chat.completions.with_raw_response.create(
                    model=model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    temperature=ctx.args.temperature,
                    max_tokens=ctx.args.max_tokens,
                    timeout=ctx.args.timeout,
                )
                t_resp = time.perf_counter()
                resp = raw.parse()
                result = (raw, resp, t_req, t_resp, started)
            except Exception as e:  # noqa: BLE001
                err = e
                t_resp = time.perf_counter()
        if result is not None:
            raw, resp, t_req, t_resp, started = result
            choice = resp.choices[0]
            msg = choice.message
            usage = getattr(resp, "usage", None)
            attempts.append({"attempt": attempt + 1, "started_at_utc": started,
                             "http_status": raw.status_code,
                             "latency_ms": round(1000 * (t_resp - t_req), 1)})
            headers = {k: v for k, v in raw.headers.items()
                       if any(h in k.lower() for h in _HEADER_KEEP)}
            return {
                "role": role,
                "model_requested": model,
                "model_reported": getattr(resp, "model", None),
                "response_id": getattr(resp, "id", None),
                "http_status": raw.status_code,
                "http_headers": headers,
                "finish_reason": choice.finish_reason,
                "raw_text": msg.content or "",
                "reasoning_content": getattr(msg, "reasoning_content", None),
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
                "request_sent_at_utc": started,
                "response_received_at_utc": utc_now(),
                "latency_ms": round(1000 * (t_resp - t_req), 1),
                "http_attempts": attempts,
                "status": "ok",
            }

        status = getattr(err, "status_code", None)
        retryable = (
            isinstance(err, (openai.APITimeoutError, openai.APIConnectionError))
            or status in (408, 409, 429)
            or (isinstance(status, int) and status >= 500)
        )
        retry_after = None
        resp_obj = getattr(err, "response", None)
        if resp_obj is not None:
            try:
                retry_after = float(resp_obj.headers.get("retry-after"))
            except Exception:
                retry_after = None
        attempts.append({"attempt": attempt + 1, "started_at_utc": started,
                         "http_status": status, "error_type": type(err).__name__,
                         "error": str(err)[:500],
                         "latency_ms": round(1000 * (t_resp - t_req), 1)})
        if not retryable or attempt == ctx.args.max_http_retries:
            raise StageError(f"{role} ({model}): {type(err).__name__}: {str(err)[:200]}", attempts)
        delay = retry_after if retry_after else min(60.0, 2.0 * (2 ** attempt)) + random.uniform(0, 1)
        log(f"    {role} {model}: HTTP {status or type(err).__name__}, retry in {delay:.0f}s")
        await asyncio.sleep(delay)
    raise StageError(f"{role}: retries exhausted", attempts)  # pragma: no cover


# --------------------------------------------------------------------------
# One attempt: A -> B -> C -> freeze
# --------------------------------------------------------------------------

class Ctx:
    def __init__(self, args, client, models, reviewers=None):
        self.args = args
        self.client = client
        self.models = models
        self.reviewers = reviewers or [models["reviewer"]]
        self.model_sems = {m: asyncio.Semaphore(args.per_model_concurrency)
                           for m in set(models.values()) | set(self.reviewers)}
        self.case_sem = asyncio.Semaphore(args.max_active_cases)
        self.eval_locks: Dict[str, asyncio.Lock] = {}
        self.baseline_done: set = set()
        self.pool: Optional[ProcessPoolExecutor] = None
        self.eval_fn = eval_worker
        self.session = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{os.getpid()}"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _freeze(out_dir: Path, names: List[str]) -> Dict[str, str]:
    hashes = {}
    for n in names:
        p = out_dir / n
        if p.exists():
            hashes[n] = sha256_file(p)
    return hashes


def _make_read_only(out_dir: Path, names: List[str]) -> None:
    for n in names:
        p = out_dir / n
        if p.exists():
            p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def frozen_files(out_dir: Path) -> List[str]:
    """Every model artifact of the attempt (all rounds), plus generation.json."""
    names = sorted(p.name for p in out_dir.iterdir()
                   if p.is_file() and (p.suffix in (".md", ".diff") or p.name == "generation.json"))
    return names


REVIEW_KEYS = ["claim", "confidence", "applies", "removes_vulnerability", "preserves_functionality"]


def _strip_verdict(review_md: str) -> str:
    """Reviewer reasoning without its verdict JSON (what the repairer sees in a revision)."""
    m = re.search(r"^#{1,6}\s*verdict\b", review_md or "", re.IGNORECASE | re.MULTILINE)
    text = review_md[: m.start()] if m else (review_md or "")
    return _FENCE_RE.sub(lambda mt: "" if '"claim"' in mt.group(2) else mt.group(0), text).strip()


def _sfx(rnd: int) -> str:
    return "" if rnd == 0 else f"_r{rnd}"


async def _review_one(ctx: Ctx, j: int, model: str, sys_c: str, usr_c: str, out_dir: Path,
                      rnd: int, rec: Dict[str, Any]) -> Dict[str, Any]:
    name = f"03_review{_sfx(rnd)}_j{j}.md"
    key = f"reviewer{_sfx(rnd) or '_r0'}_j{j}"
    try:
        r = await call_llm(ctx, "reviewer", sys_c, usr_c, model=model)
        review_md = strip_reasoning(r["raw_text"])
        _write(out_dir / name, review_md)
        rec["stages"][key] = r
        v = extract_assessment(review_md, REVIEW_KEYS)
        subs = [v.get(k) for k in REVIEW_KEYS[2:]]
        v["consistent"] = (None if None in subs or v["claim"] is None
                           else int(all(subs)) == v["claim"])
        v["status"] = "complete" if v["parse_status"] != "missing" else "incomplete"
        v.update({"model": model, "file": name, "critique": _strip_verdict(review_md)})
        return v
    except StageError as e:
        rec["stages"][key] = {"status": "error", "error": str(e), "http_attempts": e.attempts}
        return {"status": "incomplete", "model": model, "error": str(e), "claim": None}


def _jury_summary(judges: List[Dict[str, Any]]) -> Dict[str, Any]:
    done = [j for j in judges if j.get("status") == "complete" and j.get("claim") is not None]
    n = len(judges)
    if len(done) < n:   # a missing vote makes every jury rule undefined for this attempt
        return {"status": "incomplete", "n_judges": n, "votes": None, "claim": None,
                "error": f"{n - len(done)} of {n} reviewers gave no parseable verdict"}
    votes = sum(j["claim"] for j in done)
    confs = [j["confidence"] for j in done if j.get("confidence") is not None]
    return {"status": "complete", "n_judges": n, "votes": votes,
            "majority": int(votes * 2 > n), "unanimous": int(votes == n),
            "claim": int(votes * 2 > n),                 # default jury decision = majority
            "judge1_claim": done[0]["claim"],
            "confidence": (sum(confs) / len(confs)) if confs else None,
            "confidence_min": min(confs) if confs else None,
            "parse_status": "ok"}


async def run_attempt(ctx: Ctx, vuln_id: str, agent: str, run_index: int) -> Optional[Dict[str, Any]]:
    a = ctx.args
    case_dir = a.workspaces / vuln_id
    out_dir = a.runs / agent / vuln_id
    rec_path = out_dir / "llm_response.json"
    if rec_path.exists():
        log(f"[skip] {agent}/{vuln_id}: already frozen")
        return json.loads(rec_path.read_text(encoding="utf-8"))
    if not (case_dir / "meta.json").exists():
        log(f"[!] {vuln_id}: no workspace at {case_dir}")
        return None

    meta = load_meta(case_dir)
    files = select_context(case_dir, meta, a.max_files, a.max_bytes)
    code = render_files(files)
    use_analyst = not a.skip_analyst
    use_reviewer = not a.skip_reviewer
    reviewers = ctx.reviewers if use_reviewer else []
    rec: Dict[str, Any] = {
        "schema": SCHEMA,
        "vuln_id": vuln_id,
        "agent": agent,
        "run_index": run_index,
        "pipeline": "+".join(r for r, on in (("analyst", use_analyst), ("repairer", True),
                                             (f"jury{len(reviewers)}" if len(reviewers) > 1 else "reviewer",
                                              use_reviewer)) if on)
                    + (f"+revise{a.max_revisions}" if use_reviewer and a.max_revisions else ""),
        "models": {"repairer": ctx.models["repairer"],
                   **({"analyst": ctx.models["analyst"]} if use_analyst else {}),
                   **({"reviewer": reviewers[0], "reviewers": reviewers} if use_reviewer else {})},
        "max_revisions": a.max_revisions if use_reviewer else 0,
        "revise_when": a.revise_when,
        "base_url": a.base_url,
        "temperature": a.temperature,
        "max_tokens": a.max_tokens,
        "context_files": [r for r, _ in files],
        "stages": {},
        "rounds": [],
        "generator": {},
        "reviewer": {},
        "generation_status": "complete",
        "incomplete_reason": "",
        "started_at_utc": utc_now(),
    }
    t0 = time.perf_counter()
    if out_dir.exists() and any(out_dir.iterdir()):
        # An earlier run was interrupted before the freeze (never evaluated).
        keep = a.runs / "_interrupted" / f"{agent}__{vuln_id}__{int(time.time())}"
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out_dir), str(keep))
        log(f"[note] {agent}/{vuln_id}: interrupted partial attempt moved to {keep}")
    out_dir.mkdir(parents=True, exist_ok=True)
    pdir = out_dir / "prompts"

    async with ctx.case_sem:
        if not files:
            rec["generation_status"] = "incomplete"
            rec["incomplete_reason"] = "no context files selected"
        analysis = ""
        # ---- A: analyst
        if use_analyst and rec["generation_status"] == "complete":
            sys_a, usr_a = ANALYST_SYSTEM, ANALYST_USER.format(code=code)
            _write(pdir / "analyst_system.txt", sys_a)
            _write(pdir / "analyst_user.txt", usr_a)
            log(f"  A  {agent}/{vuln_id} -> {ctx.models['analyst']}")
            try:
                r = await call_llm(ctx, "analyst", sys_a, usr_a)
                analysis = strip_reasoning(r["raw_text"])
                _write(out_dir / "01_analysis.md", analysis)
                rec["stages"]["analyst"] = r
            except StageError as e:
                rec["stages"]["analyst"] = {"status": "error", "error": str(e), "http_attempts": e.attempts}
                rec["generation_status"] = "incomplete"
                rec["incomplete_reason"] = f"analyst API error: {e}"

        ab = ANALYSIS_BLOCK.format(analysis=analysis.strip()) if use_analyst else ""
        wa = WITH_ANALYSIS if use_analyst else ""
        revision = ""
        for rnd in range(0, (a.max_revisions if use_reviewer else 0) + 1):
            if rec["generation_status"] != "complete":
                break
            sfx = _sfx(rnd)
            # ---- B: repairer (round rnd)
            sys_b = REPAIRER_SYSTEM.format(with_analysis=wa)
            usr_b = REPAIRER_USER.format(analysis_block=ab, code=code) + revision
            _write(pdir / f"repairer{sfx}_system.txt", sys_b)
            _write(pdir / f"repairer{sfx}_user.txt", usr_b)
            log(f"  B{rnd} {agent}/{vuln_id} -> {ctx.models['repairer']}")
            try:
                r = await call_llm(ctx, "repairer", sys_b, usr_b)
            except StageError as e:
                rec["stages"][f"repairer{sfx or '_r0'}"] = {"status": "error", "error": str(e),
                                                            "http_attempts": e.attempts}
                rec["generation_status"] = "incomplete"
                rec["incomplete_reason"] = f"repairer API error (round {rnd}): {e}"
                break
            repair_md = strip_reasoning(r["raw_text"])
            _write(out_dir / f"02_repair{sfx}.md", repair_md)
            rec["stages"][f"repairer{sfx or '_r0'}"] = r
            diff = extract_diff(repair_md)
            _write(out_dir / f"patch{sfx or '_r0'}.diff", diff)
            g = extract_assessment(repair_md, ["claim", "confidence"])
            g.update({"diff_extracted": bool(diff), "patch_bytes": len(diff.encode("utf-8")),
                      "patch_file": f"patch{sfx or '_r0'}.diff"})
            rnd_rec: Dict[str, Any] = {"round": rnd, "generator": g, "jury": {}, "judges": []}
            rec["rounds"].append(rnd_rec)
            if g["parse_status"] == "missing":
                rec["generation_status"] = "incomplete"
                rec["incomplete_reason"] = f"repairer gave no parseable claim (round {rnd})"
                break
            if not use_reviewer:
                break
            if not g["diff_extracted"]:
                # Nothing to review: the pipeline cannot accept a non-existent patch.
                rnd_rec["jury"] = {"status": "complete", "n_judges": len(reviewers), "votes": 0,
                                   "majority": 0, "unanimous": 0, "claim": 0, "judge1_claim": 0,
                                   "confidence": None, "parse_status": "imputed",
                                   "imputed": "no patch to review"}
                break
            # ---- C: jury (round rnd), in parallel; never sees B's self-assessment
            sys_c = REVIEWER_SYSTEM.format(with_analysis=wa)
            usr_c = REVIEWER_USER.format(code=code, analysis_block=ab,
                                         proposal=proposal_without_self_assessment(repair_md).strip())
            _write(pdir / f"reviewer{sfx}_system.txt", sys_c)
            _write(pdir / f"reviewer{sfx}_user.txt", usr_c)
            log(f"  C{rnd} {agent}/{vuln_id} -> {', '.join(reviewers)}")
            judges = await asyncio.gather(*[_review_one(ctx, j, m, sys_c, usr_c, out_dir, rnd, rec)
                                            for j, m in enumerate(reviewers)])
            rnd_rec["judges"] = [{k: v for k, v in jd.items() if k != "critique"} for jd in judges]
            rnd_rec["jury"] = jury = _jury_summary(judges)
            if jury["status"] != "complete":
                break
            fire = (jury["unanimous"] == 0) if a.revise_when == "any-reject" else (jury["majority"] == 0)
            if rnd < a.max_revisions and fire:
                reviews = "\n\n".join(f"Reviewer {i + 1}:\n{jd['critique']}" for i, jd in enumerate(judges))
                revision = REVISION_BLOCK.format(
                    previous=proposal_without_self_assessment(repair_md).strip(), reviews=reviews)
                continue
            break

        # final round = what is evaluated
        if rec["rounds"]:
            last = rec["rounds"][-1]
            rec["generator"] = dict(last["generator"])
            rec["generator_initial"] = dict(rec["rounds"][0]["generator"])
            rec["n_rounds"] = len(rec["rounds"])
            if use_reviewer:
                rec["reviewer"] = dict(last["jury"]) if last["jury"] else {
                    "status": "incomplete", "error": "generation incomplete; not reviewed"}
            pf = out_dir / last["generator"]["patch_file"]
            if pf.exists():
                shutil.copy(pf, out_dir / "patch.diff")
        if use_reviewer and not rec["reviewer"]:
            rec["reviewer"] = {"status": "incomplete", "error": "generation incomplete; not reviewed"}

    # ---- totals + freeze (before any verification)
    st = [s for s in rec["stages"].values() if s.get("status") == "ok"]
    rec["latency_ms_api_total"] = round(sum(s["latency_ms"] for s in st), 1)
    rec["api_calls"] = len(st)
    rec["http_retries"] = sum(max(0, len(s.get("http_attempts", [])) - 1) for s in rec["stages"].values())
    rec["input_tokens_total"] = sum(s.get("input_tokens") or 0 for s in st)
    rec["output_tokens_total"] = sum(s.get("output_tokens") or 0 for s in st)
    rec["wall_time_s"] = round(time.perf_counter() - t0, 2)
    rec["finished_at_utc"] = utc_now()

    rep = [s for k, s in rec["stages"].items() if k.startswith("repairer") and s.get("status") == "ok"]
    _write(out_dir / "generation.json", json.dumps({
        "agent": agent, "vuln_id": vuln_id, "model": ctx.models["repairer"],
        "pipeline": rec["pipeline"],
        "input_tokens": sum(s.get("input_tokens") or 0 for s in rep) or None,
        "output_tokens": sum(s.get("output_tokens") or 0 for s in rep) or None,
        "elapsed_s": (sum(s["latency_ms"] for s in rep) / 1000) if rep else None,
        "error": rec["incomplete_reason"] or None,
        "context_files": rec["context_files"],
    }, indent=2))

    rec["frozen_at_utc"] = utc_now()
    names = frozen_files(out_dir)
    rec["sha256"] = _freeze(out_dir, names)
    _write(rec_path, json.dumps(rec, indent=2, ensure_ascii=False))
    _make_read_only(out_dir, names + ["llm_response.json"])
    g, rv = rec["generator"], rec["reviewer"]
    log(f"[frozen] {agent}/{vuln_id}: status={rec['generation_status']} rounds={rec.get('n_rounds', 0)} "
        f"claim_B={g.get('claim')} votes={rv.get('votes')}/{rv.get('n_judges')} "
        f"api={rec['latency_ms_api_total']:.0f}ms")
    return rec


# --------------------------------------------------------------------------
# Evaluation (Vul4Py, after the freeze)
# --------------------------------------------------------------------------

def reference_diff(case: Path) -> str:
    """Unified diff vulnerable -> fixed over the files the fix changed (the benchmark's own fix)."""
    import difflib
    meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
    out = ""
    for rel in meta.get("new_code_files", []):
        va, fb = case / "vulnerable" / rel, case / "fixed" / rel
        a = va.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if va.exists() else []
        b = fb.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if fb.exists() else []
        out += "".join(difflib.unified_diff(a, b, f"a/{rel}", f"b/{rel}"))
    return out


def _pfes_of(j: Optional[Dict[str, Any]]) -> Optional[str]:
    return None if not j else f"{j['passed']}/{j['failed']}/{j['errored']}/{j['skipped']}"


def env_check(case: Path, runs_root: Path, tools_root: Path, session: str) -> Dict[str, Any]:
    """Oracle control, once per case per session, in the SAME environment the candidates use.

    The verdicts A/F/S only mean something if, right now and on this machine:
      1. functional tests pass on the unpatched code      (else: broken venv / missing deps)
      2. exploit tests FAIL on the unpatched code          (else: S cannot tell fixed from not)
      3. the benchmark's reference fix passes functional + exploit tests (else: S rejects even
         the true fix, e.g. a dependency changed behaviour since the benchmark was built)
    If any check fails the oracle is invalid here and every attempt on the case is incomplete."""
    import vul4py  # noqa: WPS433
    import run_eval  # noqa: WPS433

    out = runs_root / "_baseline" / case.name / "env_check.json"
    if out.exists():
        prev = json.loads(out.read_text(encoding="utf-8"))
        if prev.get("session") == session:
            return prev
    vuln, fixed, logs = case / "vulnerable", case / "fixed", case / "logs"
    meta = vul4py.load_meta(case)
    res: Dict[str, Any] = {"session": session, "checked_at_utc": utc_now()}
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        # 1. functional on unpatched
        vul4py._restore_target(vuln)
        vul4py.run_functional(tools_root, vuln, meta, logs)
        for ext in ("log", "junit.xml"):
            src = logs / f"functional_vulnerable.{ext}"
            if src.exists():
                src.replace(logs / f"functional_envcheck.{ext}")
        jf = vul4py._parse_junit(logs / "functional_envcheck.junit.xml")
        # 2. exploit on unpatched (fixture files the fix added are overlaid, as for candidates)
        run_eval._overlay_fixture_additions(fixed, vuln)
        vul4py.run_exploit_for_target(tools_root, fixed, vuln, "vulnerable", meta, logs)
        for ext in ("log", "junit.xml"):
            src = logs / f"exploit_vulnerable.{ext}"
            if src.exists():
                src.replace(logs / f"exploit_envcheck_unpatched.{ext}")
        je = vul4py._parse_junit(logs / "exploit_envcheck_unpatched.junit.xml")
        vul4py._restore_target(vuln)
        # 3. reference fix through the same evaluator as the candidates
        ref_root = runs_root / "_baseline" / "_reference"
        (ref_root / "reference" / case.name).mkdir(parents=True, exist_ok=True)
        (ref_root / "reference" / case.name / "patch.diff").write_text(reference_diff(case), encoding="utf-8")
        vr = run_eval._evaluate_one(case, ref_root, ["reference"], tools_root)[0]
        res.update({
            "functional_unpatched": _pfes_of(jf), "exploit_unpatched": _pfes_of(je),
            "functional_reference": vr.get("func_pfes"), "exploit_reference": vr.get("exploit_pfes"),
            "reference_apply_ok": vr.get("apply_ok"),
        })
        res["functional_ok"] = bool(jf and jf["passed"] > 0 and jf["failed"] == 0 and jf["errored"] == 0)
        res["exploit_discriminates"] = bool(je and (je["failed"] + je["errored"]) > 0)
        res["reference_verified"] = bool(vr.get("apply_ok") and vr.get("func_ok") and vr.get("exploit_ok"))
        if jf:
            res.update({k: jf[k] for k in ("passed", "failed", "errored", "skipped")})
    except Exception as e:  # noqa: BLE001
        res["error"] = repr(e)
        vul4py._restore_target(vuln)
    # Reproducibility record: exact packages and test commands this verdict was obtained with.
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
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    for name in ("functional_envcheck", "exploit_envcheck_unpatched"):
        for ext in ("log", "junit.xml"):
            p = logs / f"{name}.{ext}"
            if p.exists():
                shutil.copy(p, out.parent / p.name)
    return res


def eval_worker(case_dir: str, runs_root: str, agent: str, tools_root: str,
                session: str = "") -> Dict[str, Any]:
    """Runs in a separate process. Reuses scripts/run_eval.py unchanged."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run_eval  # noqa: WPS433

    case = Path(case_dir)
    run_dir = Path(runs_root) / agent / case.name
    env = env_check(case, Path(runs_root), Path(tools_root), session)
    if not env["healthy"]:
        verdict = {"agent": agent, "vuln_id": case.name, "apply_ok": False, "func_ok": False,
                   "exploit_ok": False, "plausible": False, "func_pfes": None,
                   "exploit_pfes": None, "elapsed_s": None, "env_check": env,
                   "notes": (f"environment check failed: {env.get('reason')} "
                             f"(functional unpatched {env.get('functional_unpatched')}, "
                             f"exploit unpatched {env.get('exploit_unpatched')}, "
                             f"reference {env.get('functional_reference')} / {env.get('exploit_reference')}) "
                             f"{env.get('error', '')}").strip()}
        (run_dir / "eval.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        return verdict
    patch_file = run_dir / "patch.diff"
    if not patch_file.exists() or not patch_file.read_text(encoding="utf-8", errors="replace").strip():
        # No patch to apply: A = 0 and, as the guide requires, neither test suite is run.
        verdict = {"agent": agent, "vuln_id": case.name, "apply_ok": False, "func_ok": False,
                   "exploit_ok": False, "plausible": False, "func_pfes": None,
                   "exploit_pfes": None, "elapsed_s": 0.0, "env_check": env, "notes": "empty patch"}
        (run_dir / "eval.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        return verdict
    try:
        verdict = run_eval._evaluate_one(case, Path(runs_root), [agent], Path(tools_root))[0]
        verdict["env_check"] = env
        (run_dir / "eval.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        verdict = {"agent": agent, "vuln_id": case.name, "apply_ok": False, "func_ok": False,
                   "exploit_ok": False, "plausible": False, "func_pfes": None,
                   "exploit_pfes": None, "notes": f"worker crash: {e!r}", "elapsed_s": None}
        (run_dir / "eval.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    logs = case / "logs"
    dst = run_dir / "logs"
    dst.mkdir(exist_ok=True)
    for kind in ("functional", "exploit"):
        for ext in ("log", "junit.xml"):
            src = logs / f"{kind}_{agent}_candidate.{ext}"
            if src.exists():
                shutil.copy(src, dst / src.name)
    return verdict


def snapshot_baseline(ctx: Ctx, vuln_id: str) -> None:
    """Copy the scan's vulnerable/fixed test logs once, before any evaluation
    (run_eval renames exploit_vulnerable.* to the agent name)."""
    if vuln_id in ctx.baseline_done:
        return
    ctx.baseline_done.add(vuln_id)
    src = ctx.args.workspaces / vuln_id / "logs"
    dst = ctx.args.runs / "_baseline" / vuln_id
    if dst.exists() or not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for kind in ("functional", "exploit"):
        for ver in ("vulnerable", "fixed"):
            for ext in ("log", "junit.xml"):
                p = src / f"{kind}_{ver}.{ext}"
                if p.exists():
                    shutil.copy(p, dst / p.name)


async def evaluate_attempt(ctx: Ctx, vuln_id: str, agent: str, rec: Dict[str, Any]) -> None:
    out_dir = ctx.args.runs / agent / vuln_id
    if (out_dir / "eval.json").exists():
        return
    if rec.get("generation_status") != "complete" or not (out_dir / "patch.diff").exists():
        return
    # Freeze check: artifacts must be byte-identical to what was hashed.
    for name, h in rec.get("sha256", {}).items():  # every frozen artifact, all rounds
        if sha256_file(out_dir / name) != h:
            log(f"[!] {agent}/{vuln_id}: {name} changed after freeze; not evaluating")
            _write(out_dir / "eval.json", json.dumps({
                "agent": agent, "vuln_id": vuln_id, "notes": f"frozen artifact modified: {name}"}))
            return
    lock = ctx.eval_locks.setdefault(vuln_id, asyncio.Lock())
    async with lock:  # run_eval patches vulnerable/ in place: one evaluation per case at a time
        snapshot_baseline(ctx, vuln_id)
        log(f"  EV {agent}/{vuln_id}")
        loop = asyncio.get_running_loop()
        v = await loop.run_in_executor(
            ctx.pool, ctx.eval_fn, str(ctx.args.workspaces / vuln_id), str(ctx.args.runs),
            agent, str(ctx.args.tools_root), ctx.session)
        log(f"[eval] {agent}/{vuln_id}: apply={v.get('apply_ok')} func={v.get('func_pfes')} "
            f"expl={v.get('exploit_pfes')} {v.get('notes') or ''}")


async def evaluate_initial(ctx: Ctx, vuln_id: str, agent: str, rec: Dict[str, Any]) -> None:
    """Evaluate the round-0 patch of a revised attempt, as pseudo-agent <agent>__initial.
    Only for measuring the effect of the revision (RQ2); never shown to any model."""
    src = ctx.args.runs / agent / vuln_id / "patch_r0.diff"
    if not src.exists() or src.read_bytes() and sha256_file(src) != rec.get("sha256", {}).get("patch_r0.diff"):
        return
    ini = f"{agent}__initial"
    dst = ctx.args.runs / ini / vuln_id
    if (dst / "eval.json").exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst / "patch.diff")
    lock = ctx.eval_locks.setdefault(vuln_id, asyncio.Lock())
    async with lock:
        loop = asyncio.get_running_loop()
        v = await loop.run_in_executor(
            ctx.pool, ctx.eval_fn, str(ctx.args.workspaces / vuln_id), str(ctx.args.runs),
            ini, str(ctx.args.tools_root), ctx.session)
        log(f"[eval] {ini}/{vuln_id}: apply={v.get('apply_ok')} func={v.get('func_pfes')} "
            f"expl={v.get('exploit_pfes')} {v.get('notes') or ''}")


# --------------------------------------------------------------------------
# Case selection, model listing, main
# --------------------------------------------------------------------------

def _pfes_passed(s: str) -> int:
    try:
        return int(str(s).split("/")[0])
    except Exception:
        return 0


def resolve_ids(a) -> List[str]:
    ids: List[str] = []
    if a.vuln_ids:
        ids += [s.strip() for s in a.vuln_ids.split(",") if s.strip()]
    if a.ids_file:
        for ln in Path(a.ids_file).read_text(encoding="utf-8").splitlines():
            ln = ln.split("#", 1)[0].strip()
            if ln:
                ids.append(ln)
    if a.from_scan:
        rep = a.workspaces / "scan_report.tsv"
        if not rep.exists():
            sys.exit(f"--from-scan: {rep} not found (run vul4py.py scan first)")
        lines = rep.read_text(encoding="utf-8").splitlines()
        hdr = lines[0].split("\t")
        for ln in lines[1:]:
            row = dict(zip(hdr, ln.split("\t")))
            # Guide 4.2: status OK and functional tests that actually pass
            if row.get("status") == "OK" and _pfes_passed(row.get("fv_pfes", "")) > 0:
                ids.append(row["cve_id"])
    ids = list(dict.fromkeys(ids))
    if a.sample and a.sample < len(ids):
        ids = sorted(random.Random(a.seed).sample(sorted(ids), a.sample))
    return ids


def make_client(a):
    from openai import AsyncOpenAI
    key = os.environ.get(a.api_key_env)
    if not key:
        sys.exit(f"Set {a.api_key_env} in your terminal (never commit it).")
    return AsyncOpenAI(base_url=a.base_url, api_key=key, max_retries=0, timeout=a.timeout)


async def list_models(a) -> None:
    client = make_client(a)
    page = await client.models.list()
    ids = sorted(m.id for m in page.data)
    for i in ids:
        if not a.filter or a.filter.lower() in i.lower():
            print(i)


async def amain(a, eval_fn=None) -> int:
    models = {"analyst": a.analyst_model, "repairer": a.repairer_model,
              "reviewer": a.reviewer_model}
    ids = resolve_ids(a)
    if not ids:
        sys.exit("No cases selected: use --vuln-ids, --ids-file or --from-scan.")
    if a.runs_per_case > 1 and a.temperature == 0:
        log("[warn] runs_per_case > 1 with temperature 0: repetitions may be near-identical")
    agents = ([f"{a.agent}_r{k}" for k in range(1, a.runs_per_case + 1)]
              if a.runs_per_case > 1 else [a.agent])

    client = make_client(a)  # fail fast if the key is missing
    a.runs.mkdir(parents=True, exist_ok=True)
    exp = {
        "schema": SCHEMA, "started_at_utc": utc_now(), "models": models,
        "pipeline": {"analyst": not a.skip_analyst, "reviewer": not a.skip_reviewer,
                     "reviewers": [m.strip() for m in a.reviewer_models.split(",") if m.strip()]
                     or [a.reviewer_model],
                     "max_revisions": a.max_revisions, "revise_when": a.revise_when},
        "base_url": a.base_url, "temperature": a.temperature, "max_tokens": a.max_tokens,
        "timeout_s": a.timeout, "max_http_retries": a.max_http_retries,
        "per_model_concurrency": a.per_model_concurrency, "max_active_cases": a.max_active_cases,
        "context": {"max_files": a.max_files, "max_bytes": a.max_bytes,
                    "selection": "meta.json new_code_files, library code before examples/docs/tests "
                                 "(select_context), then run_agent.collect_context_files budgets"},
        "prompt_sha256": prompt_fingerprint(), "vul4py_commit": git_head(ROOT),
        "vuln_ids": ids, "agents": agents, "sample": a.sample, "seed": a.seed,
        "python": platform.python_version(),
    }
    try:
        import openai
        exp["openai_client"] = openai.__version__
    except Exception:
        pass
    exp_path = a.runs / f"experiment_{a.agent}.json"
    _write(exp_path, json.dumps(exp, indent=2))
    log(f"[+] {len(ids)} cases x {len(agents)} run(s); models={models}")

    reviewers = ([m.strip() for m in a.reviewer_models.split(",") if m.strip()]
                 or [a.reviewer_model])
    ctx = Ctx(a, client, models, reviewers)
    if eval_fn is not None:
        ctx.eval_fn = eval_fn
    if not a.no_eval:
        ctx.pool = ProcessPoolExecutor(max_workers=a.eval_jobs,
                                       mp_context=mp.get_context("spawn"))

    async def one(vid: str, agent: str, k: int):
        try:
            rec = await run_attempt(ctx, vid, agent, k)
            if rec and not a.no_eval:
                await evaluate_attempt(ctx, vid, agent, rec)
                if a.eval_initial and (rec.get("n_rounds") or 1) > 1:
                    await evaluate_initial(ctx, vid, agent, rec)
        except Exception as e:  # noqa: BLE001  keep the batch alive
            log(f"[!] {agent}/{vid}: unexpected error {e!r}")

    t0 = time.perf_counter()
    # Interleave runs so repetition r2 of a case does not wait behind every r1.
    await asyncio.gather(*[one(v, ag, k + 1) for k, ag in enumerate(agents) for v in ids])
    if ctx.pool:
        ctx.pool.shutdown(wait=True)
    exp["finished_at_utc"] = utc_now()
    exp["wall_time_s"] = round(time.perf_counter() - t0, 1)
    _write(exp_path, json.dumps(exp, indent=2))
    log(f"[done] wall time {exp['wall_time_s']}s")

    if not a.no_eval:
        import fa_metrics
        fa_metrics.run(a.runs, None, a.workspaces)  # every condition under --runs, side by side
    return 0


def preflight_worker(case_dir: str, runs_root: str, tools_root: str, session: str) -> Dict[str, Any]:
    """Oracle control for one case, in a separate process. No API calls."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    t0 = time.time()
    case = Path(case_dir)
    try:
        res = dict(env_check(case, Path(runs_root), Path(tools_root), session))
    except Exception as e:  # noqa: BLE001
        res = {"healthy": False, "reason": f"preflight crash: {e!r}"}
    res["vuln_id"] = case.name
    res["seconds"] = round(time.time() - t0, 1)
    return res


PREFLIGHT_COLS = ["vuln_id", "healthy", "functional_unpatched", "exploit_unpatched",
                  "functional_reference", "exploit_reference", "reason", "seconds"]


def preflight(a) -> int:
    """Run the oracle control on every candidate case and fix the samples BEFORE any API call.

    Writes into --runs:
        oracle_report.tsv   one row per candidate (why each one is valid or not)
        oracle_valid.txt    cases whose oracle is valid on this machine
        main_ids.txt        main sample  = random sample of the valid cases (--seed, --main-size)
        pilot_ids.txt       pilot sample = random sample of the REMAINING valid cases
                            (--pilot-seed, --pilot-size); disjoint from the main sample
        split.json          seeds, sizes, counts, commit, timestamp
    """
    from concurrent.futures import as_completed

    a.sample = None                      # the control runs on every candidate
    ids = resolve_ids(a)
    if not ids:
        sys.exit("No candidate cases: use --from-scan (after vul4py.py scan), --ids-file or --vuln-ids.")
    missing = [v for v in ids if not (a.workspaces / v / "vulnerable" / ".venv").exists()]
    if missing:
        sys.exit(f"{len(missing)} case(s) have no test environment yet (run vul4py.py scan first): "
                 + ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else ""))
    a.runs.mkdir(parents=True, exist_ok=True)
    session = f"preflight-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    log(f"[+] Oracle control on {len(ids)} cases with {a.eval_jobs} worker(s); no API calls")
    rows: List[Dict[str, Any]] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=a.eval_jobs, mp_context=mp.get_context("spawn")) as pool:
        futs = [pool.submit(preflight_worker, str(a.workspaces / v), str(a.runs), str(a.tools_root), session)
                for v in ids]
        for k, f in enumerate(as_completed(futs), 1):
            r = f.result()
            rows.append(r)
            log(f"  [{k}/{len(ids)}] {r['vuln_id']}: {'VALID' if r.get('healthy') else 'invalid'} "
                f"func={r.get('functional_unpatched')} expl={r.get('exploit_unpatched')} "
                f"ref_func={r.get('functional_reference')} ref_expl={r.get('exploit_reference')} "
                f"({r['seconds']}s) {r.get('reason') or ''} {r.get('error') or ''}".rstrip())
    rows.sort(key=lambda r: r["vuln_id"])
    with open(a.runs / "oracle_report.tsv", "w", encoding="utf-8") as f:
        f.write("\t".join(PREFLIGHT_COLS) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in PREFLIGHT_COLS) + "\n")

    valid = sorted(r["vuln_id"] for r in rows if r.get("healthy"))
    _write(a.runs / "oracle_valid.txt", "".join(v + "\n" for v in valid))
    if (a.runs / "main_ids.txt").exists() and not a.resplit:
        # The samples are pre-registered: never redraw them silently. Re-running the control
        # only reports whether the cases already chosen are still valid on this machine.
        kept = {n: [l.strip() for l in (a.runs / f"{n}_ids.txt").read_text().splitlines() if l.strip()]
                for n in ("main", "pilot") if (a.runs / f"{n}_ids.txt").exists()}
        for n, ids_n in kept.items():
            bad = [v for v in ids_n if v not in set(valid)]
            log(f"[keep] {n} sample unchanged ({len(ids_n)} cases); "
                + (f"NO LONGER VALID here: {', '.join(bad)}" if bad else "all still valid"))
        log("[+] samples kept; use --resplit only before the main run has started")
        return 0
    n_main = min(a.main_size, max(0, len(valid) - a.pilot_size))
    main_ids = sorted(random.Random(a.seed).sample(valid, n_main))
    rest = [v for v in valid if v not in set(main_ids)]
    pilot_ids = sorted(random.Random(a.pilot_seed).sample(rest, min(a.pilot_size, len(rest))))
    _write(a.runs / "main_ids.txt", "".join(v + "\n" for v in main_ids))
    _write(a.runs / "pilot_ids.txt", "".join(v + "\n" for v in pilot_ids))
    _write(a.runs / "split.json", json.dumps({
        "created_at_utc": utc_now(), "vul4py_commit": git_head(ROOT), "session": session,
        "candidates": len(ids), "oracle_valid": len(valid),
        "main": {"size": len(main_ids), "requested": a.main_size, "seed": a.seed, "ids": main_ids},
        "pilot": {"size": len(pilot_ids), "requested": a.pilot_size, "seed": a.pilot_seed, "ids": pilot_ids},
        "wall_time_s": round(time.perf_counter() - t0, 1),
    }, indent=2))
    log(f"[done] candidates={len(ids)}  oracle-valid={len(valid)}  main={len(main_ids)}  "
        f"pilot={len(pilot_ids)}  ({time.perf_counter() - t0:.0f}s)")
    if len(main_ids) < a.main_size:
        log(f"[warn] only {len(valid)} valid cases: the main sample has {len(main_ids)} instead of "
            f"{a.main_size}. Report this N; do not add cases by hand.")
    log(f"[+] wrote {a.runs}/oracle_report.tsv, oracle_valid.txt, main_ids.txt, pilot_ids.txt, split.json")
    return 0


async def ping_models(a) -> int:
    """One tiny request per model: which IDs answer for this key, and how fast."""
    client = make_client(a)
    models = (CANDIDATE_MODELS if a.ping_models.strip().lower() == "default"
              else [m.strip() for m in a.ping_models.split(",") if m.strip()])

    async def one(m: str) -> Dict[str, Any]:
        t0 = time.perf_counter()
        try:
            raw = await client.chat.completions.with_raw_response.create(
                model=m, messages=[{"role": "user", "content": "Reply with the single word: OK"}],
                temperature=0, max_tokens=512, timeout=min(a.timeout, 180.0))
            resp = raw.parse()
            ch = resp.choices[0]
            text = (ch.message.content or "").strip()
            return {"model": m, "status": raw.status_code, "s": time.perf_counter() - t0,
                    "finish": ch.finish_reason,
                    "note": ("answer: " + text[:30].replace("\n", " ")) if text
                    else "EMPTY content (reasoning model? needs more max_tokens)"}
        except Exception as e:  # noqa: BLE001
            return {"model": m, "status": getattr(e, "status_code", None) or type(e).__name__,
                    "s": time.perf_counter() - t0, "finish": "-",
                    "note": "ERROR " + str(e)[:110].replace("\n", " ")}

    rows = await asyncio.gather(*[one(m) for m in models])
    print(f"{'model':46s} {'status':>8s} {'seconds':>8s}  {'finish':8s} note")
    for r in rows:
        print(f"{r['model']:46s} {str(r['status']):>8s} {r['s']:8.1f}  {str(r['finish']):8s} {r['note']}")
    ok = sum(1 for r in rows if r["status"] == 200 and not r["note"].startswith("EMPTY"))
    print(f"\n{ok}/{len(rows)} models answered. Use only models with status 200 and a non-empty answer.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Three-model (analyst/repairer/reviewer) repair pipeline via NVIDIA API.")
    sel = ap.add_argument_group("case selection")
    sel.add_argument("--vuln-ids", help="Comma-separated vuln IDs")
    sel.add_argument("--ids-file", help="File with one vuln ID per line")
    sel.add_argument("--from-scan", action="store_true",
                     help="Use every case with status OK and passing functional tests in scan_report.tsv")
    sel.add_argument("--sample", type=int, default=None, help="Random sample of N cases (reproducible with --seed)")
    sel.add_argument("--seed", type=int, default=42)

    mdl = ap.add_argument_group("models")
    mdl.add_argument("--analyst-model", default=DEFAULT_MODELS["analyst"])
    mdl.add_argument("--repairer-model", default=DEFAULT_MODELS["repairer"])
    mdl.add_argument("--reviewer-model", default=DEFAULT_MODELS["reviewer"])
    mdl.add_argument("--reviewer-models", default="",
                     help="Comma-separated jury (overrides --reviewer-model), e.g. 3 different families")
    mdl.add_argument("--max-revisions", type=int, default=0,
                     help="Revision rounds driven by the reviewers' critiques (0 = none)")
    mdl.add_argument("--revise-when", choices=["any-reject", "majority-reject"], default="any-reject",
                     help="Trigger a revision when any reviewer rejects, or only a majority")
    mdl.add_argument("--skip-analyst", action="store_true", help="Ablation: repairer gets source only")
    mdl.add_argument("--skip-reviewer", action="store_true", help="Ablation: no independent review")
    mdl.add_argument("--temperature", type=float, default=0.0)
    mdl.add_argument("--max-tokens", type=int, default=8192)
    mdl.add_argument("--max-files", type=int, default=4)
    mdl.add_argument("--max-bytes", type=int, default=60_000)

    api = ap.add_argument_group("API / speed")
    api.add_argument("--base-url", default=NVIDIA_BASE_URL)
    api.add_argument("--api-key-env", default="NVIDIA_API_KEY")
    api.add_argument("--timeout", type=float, default=600.0, help="Per-request timeout (s)")
    api.add_argument("--max-http-retries", type=int, default=3,
                     help="Retries only for 429/5xx/timeout/connection errors (no response received)")
    api.add_argument("--per-model-concurrency", type=int, default=4)
    api.add_argument("--max-active-cases", type=int, default=8)
    api.add_argument("--eval-jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    api.add_argument("--no-eval", action="store_true", help="Only generate + freeze; evaluate later")
    api.add_argument("--eval-initial", action="store_true",
                     help="Also evaluate the pre-revision patch (patch_r0.diff) to measure the revision effect")

    io = ap.add_argument_group("paths")
    io.add_argument("--runs", type=Path, default=ROOT / "runs" / "final")
    io.add_argument("--agent", default="ma3", help="Run name; repetitions become <agent>_r1, _r2, ...")
    io.add_argument("--runs-per-case", type=int, default=1)
    io.add_argument("--workspaces", type=Path, default=ROOT / "workspaces")
    io.add_argument("--tools-root", type=Path, default=None)

    pre = ap.add_argument_group("preflight (no API calls)")
    pre.add_argument("--preflight", action="store_true",
                     help="Run the oracle control on every candidate case and write the main/pilot samples")
    pre.add_argument("--main-size", type=int, default=30, help="Main sample size (drawn with --seed)")
    pre.add_argument("--pilot-size", type=int, default=5, help="Pilot sample size, disjoint from the main sample")
    pre.add_argument("--pilot-seed", type=int, default=7)
    pre.add_argument("--resplit", action="store_true",
                     help="Redraw main/pilot samples even if they already exist (only before the main run)")

    ap.add_argument("--list-models", action="store_true", help="List model IDs available to your key and exit")
    ap.add_argument("--filter", default="", help="Substring filter for --list-models")
    ap.add_argument("--ping-models", default="",
                    help="Comma-separated model IDs, or 'default' for the built-in candidate list: "
                         "send one tiny request to each and report status and latency")
    return ap


def main() -> int:
    a = build_parser().parse_args()
    a.runs = a.runs.resolve()
    a.workspaces = a.workspaces.resolve()
    a.tools_root = (a.tools_root or (a.workspaces / ".vul4py_tools")).resolve()
    if a.list_models:
        asyncio.run(list_models(a))
        return 0
    if a.ping_models:
        return asyncio.run(ping_models(a))
    if a.preflight:
        return preflight(a)
    return asyncio.run(amain(a))


if __name__ == "__main__":
    sys.exit(main())
