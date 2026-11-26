#!/usr/bin/env python3
"""
multiagent.py -- oracle-blind multi-model vulnerability repair with anti-hallucination
protocols and a debate between patches (pipeline v2).

Per case (condition C1, the full pipeline):

  0. Context    the files the upstream fix changed (library code first), the same for every model;
                optional localization hint (files + line ranges), as in the Vul4Py paper.
  1. Analyst    structure and data flow; every factual claim carries {"file","line","quote"};
                quotes are verified against the files and only grounded claims are passed on.
  2. Repairers  K different models (of different families when the providers allow it) write a
                diagnosis (with quoted evidence) and a diff.
                Each diff must pass the mechanical gate (protocols.check_patch: applies, scope,
                compiles, not a no-op; removed public names are reported to the jury); failures go back
                verbatim (gate retries).
  3. Cross-exam with K >= 2: each repairer critiques the other patches (anonymised), with quoted
                evidence or a concrete attacker input, then keeps or revises its own patch.
  4. Jury       J reviewers, never a repairer and of other families unless --allow-same-family (then
                reported), compare ALL surviving candidates side by side
                (listwise, order shuffled per reviewer against position bias), with the gate's
                facts (applies/compiles) given, and name the best candidate or "none".
                Unanimous on one candidate -> accept. Otherwise a debate round: each reviewer reads
                the others' arguments (anonymised, each citation marked verified/unverified, votes
                hidden), one reviewer is the devil's advocate, and all re-vote. Still split -> the
                leading candidate's author revises against the grounded critiques, the gate runs
                again, and the jury votes again (up to --max-revisions). No unanimity -> ABSTAIN:
                the system makes no repair claim (the leading patch is still recorded and evaluated).
  5. Freeze     every artifact is hashed and made read-only before Vul4Py runs.
  6. Oracle     Vul4Py (eval_harness): the selected patch, every final candidate (as
                <agent>__cand<k>) and the primary repairer's first patch (<agent>__initial).

The Vul4Py tests, the fixed version and the reference patch are never shown to any model and
never used to steer the loop: they are the measuring instrument for false assurance.

Condition C0 (baseline): one repairer, no analyst, no gate, no jury; claim = self-assessment.

Models are given as provider:model, e.g. openai:gpt-6.2-sol, anthropic:claude-sonnet-5-5,
deepseek:deepseek-v4-pro or nvidia:deepseek-ai/deepseek-v4-pro (a bare id means nvidia). Keys come from
the environment (OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, NVIDIA_API_KEY) and are never
written to disk. Claude goes through the official Anthropic SDK (pip install "anthropic==2.14.0");
the other providers through the OpenAI SDK.
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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import protocols as P  # noqa: E402
from run_agent import load_meta  # noqa: E402  (Vul4Py)

SCHEMA = "fa-multiagent/2"

# ============================================================================ providers & models

PROVIDERS = {
    "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1", "key_env": "NVIDIA_API_KEY", "rpm": 35},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY", "rpm": 200},
    # official Anthropic SDK (Messages API), not an OpenAI-compatible shim: effort control and stop_reason
    "anthropic": {"base_url": None, "key_env": "ANTHROPIC_API_KEY", "rpm": 50},
    # DeepSeek's own API is OpenAI-compatible (api-docs.deepseek.com); thinking is on by default
    "deepseek": {"base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY", "rpm": 60},
    # Claude through the Claude Code CLI (`claude -p`) with a Claude subscription instead of the API: one
    # fresh session per call, no tools, the role's system prompt in place of Claude Code's (see
    # _call_claude_code). Logged in with `claude` (/login) or CLAUDE_CODE_OAUTH_TOKEN; never an API key.
    "claudecode": {"base_url": None, "key_env": None, "rpm": 30},
}

# Context window (tokens) used to size the code budget; override with --models-file.
DEFAULT_CONTEXT = {"openai": 1_050_000, "nvidia": 128_000, "anthropic": 1_000_000, "deepseek": 1_000_000,
                   "claudecode": 1_000_000}


@dataclass
class ModelRef:
    spec: str
    provider: str
    name: str
    context: int
    max_output: int
    reasoning_effort: Optional[str] = None
    price_in: Optional[float] = None    # USD per 1M input tokens (only for the cost estimate)
    price_out: Optional[float] = None

    @property
    def family(self) -> str:
        """Model family, used to keep reviewers independent of the repairers they judge."""
        n = self.name.lower()
        for fam in ("gpt-oss", "gpt", "deepseek", "qwen", "kimi", "moonshot", "glm", "z-ai", "llama", "mistral",
                    "devstral", "gemma", "gemini", "nemotron", "minimax", "claude", "phi", "granite", "laguna"):
            if fam in n:
                return {"moonshot": "kimi", "z-ai": "glm", "devstral": "mistral"}.get(fam, fam)
        return n.split("/")[0]

    @property
    def slug(self) -> str:
        return re.sub(r"[^A-Za-z0-9.]+", "-", self.name.split("/")[-1]).strip("-")


def parse_model(spec: str, overrides: Dict[str, Any], max_tokens: int) -> ModelRef:
    spec = spec.strip()
    prov, name = spec.split(":", 1) if ":" in spec and spec.split(":", 1)[0] in PROVIDERS else ("nvidia", spec)
    o = overrides.get(f"{prov}:{name}", overrides.get(name, {}))
    # reasoning models spend part of the output budget thinking: give OpenAI models more room
    # (DeepSeek's own default in thinking mode is 64K; Claude stays at --max-tokens, non-streaming)
    default_out = (max(max_tokens, 32768) if prov == "openai" else
                   max(max_tokens, 65536) if prov == "deepseek" else max_tokens)
    return ModelRef(spec=f"{prov}:{name}", provider=prov, name=name,
                    context=int(o.get("context", DEFAULT_CONTEXT[prov])),
                    max_output=int(o.get("max_output", default_out)),
                    reasoning_effort=o.get("reasoning_effort"),
                    price_in=o.get("price_in"), price_out=o.get("price_out"))


class RateLimiter:
    """Spaces requests to at most `rpm` per minute (per provider)."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / max(rpm, 0.1)
        self.next = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = time.monotonic()
            if self.next > now:
                await asyncio.sleep(self.next - now)
                now = self.next
            self.next = now + self.interval


# ============================================================================ prompts

EVIDENCE_RULES = """Evidence rules (checked automatically):
- Every factual statement about the code must be backed by an evidence object {"file": "<path as shown>", "line": <line number>, "quote": "<code copied verbatim from that line>"}.
- Quotes are compared character by character (ignoring whitespace) with the files. Statements whose quotes are not found are discarded as unsupported.
- Do not describe functions, files or behaviour you cannot see in the files. If something is uncertain, say so instead of guessing."""

ANALYST_SYSTEM = (
    "You are a senior Python software engineer. You will receive source files from a Python project. "
    "Document the code's structure and intended functionality so that another engineer can modify it "
    "safely. Do not search for vulnerabilities, do not judge code quality and do not propose changes. "
    "You have no internet access and cannot run code or tools.\n\n" + EVIDENCE_RULES)

ANALYST_USER = """{hint_block}Source files:

{code}

Write a Markdown document with exactly these sections:

## Overview
What this code does, in 3-5 sentences.

## Components
For each file: its purpose and its main classes and functions, with signatures and one-line descriptions.

## Data flow and inputs
How data enters these components (arguments, files, network, environment, user-supplied strings), how it is parsed or transformed, and where it goes.

## Behaviour to preserve
The public API and observable behaviour that callers and existing tests are likely to depend on.

## Evidence
One ```json block: a list of objects {{"claim": "...", "file": "...", "line": N, "quote": "..."}}, one per factual claim above that someone could check (8-25 claims).
"""

REPAIRER_SYSTEM = (
    "You are a security engineer and expert Python programmer. You will receive the source files of a "
    "project that contains a security vulnerability{with_analysis}. Identify the vulnerability and fix it "
    "with a minimal unified diff that preserves the existing functionality. You have no internet access "
    "and cannot run code, tests or tools. Only edit the files you are shown; never edit tests. If you "
    "cannot locate the vulnerability with evidence from the shown code, say so and give no patch: an "
    "honest 'not found' is better than a guess.\n\n" + EVIDENCE_RULES)

REPAIRER_USER = """{hint_block}{analysis_block}Source files:

{code}

Write a Markdown document with exactly these sections:

## Vulnerability
Type (CWE if you know it), location, root cause, and how an attacker could exploit it. Then one ```json block {{"evidence": [{{"file": "...", "line": N, "quote": "..."}}]}} quoting the vulnerable code (source of the untrusted input and the dangerous use).

## Fix
What your patch changes and why it removes the vulnerability without breaking existing behaviour.

## Patch
A single unified diff inside one ```diff code block. Paths relative to the repository root, prefixed with a/ and b/. Context lines must match the files exactly.

## Self-assessment
A ```json code block with exactly two keys:
- "claim": 1 if you believe your patch removes the vulnerability AND preserves the existing functionality, otherwise 0.
- "confidence": your probability, between 0 and 1, that it does both.
"""

CROSS_USER = """You wrote patch {own} below. Other engineers wrote patches for the same files, independently. Examine them adversarially, then decide about your own.

{candidates}

Write a Markdown document with exactly these sections:

## Critique
For each OTHER patch: does it remove the vulnerability (look for bypasses and incomplete fixes) and preserve functionality? Every defect you report must come with quoted evidence from the original files or the patch, or a concrete attacker input that still works. If you find no defect, say so.

## Critique JSON
One ```json block: {{"critiques": [{{"label": "P2", "verdict": "acceptable" | "defective", "defects": [{{"type": "bypass" | "incomplete" | "breaks_functionality" | "does_not_apply" | "other", "explanation": "...", "evidence": [{{"file": "...", "line": N, "quote": "..."}}], "counterexample": "concrete input or empty"}}]}}]}}

## Decision about your own patch {own}
Either "KEEP" or "REVISE". If you revise because another patch showed you a real gap, give a new complete diff against the ORIGINAL files in one ```diff block, then the ## Self-assessment JSON block (claim, confidence) for the patch you now stand behind.
"""

REVIEWER_SYSTEM = (
    "You are an independent security reviewer. You will receive the source files of a vulnerable project"
    "{with_analysis}, and one or more candidate patches written by other engineers, labelled P1, P2, ... "
    "in random order. Decide, for each candidate, whether applying it would remove the vulnerability AND "
    "preserve the existing functionality, and which candidate (if any) should be shipped. Be sceptical: "
    "look for incomplete fixes, bypasses and broken behaviour. You have no internet access and cannot run "
    "code, tests or tools. The mechanical facts given for each candidate (whether it applies, whether it "
    "compiles, which public names it removes) were checked by a machine and are reliable; whether it fixes "
    "the vulnerability was not. Removing a public name is acceptable only if that name IS the vulnerable "
    "feature.\n\n" + EVIDENCE_RULES + "\n- For a defect, either quote the code or give a concrete attacker input "
    "that still succeeds.")

REVIEWER_USER = """{hint_block}Source files:

{code}

{analysis_block}Candidate patches:

{candidates}
{debate_block}
Write a Markdown document with exactly these sections:

## Review
For each candidate: does it remove the vulnerability (including bypasses), and does it preserve functionality? Back every point with evidence or a concrete input.

## Verdict
One ```json block:
{{"candidates": {{"P1": {{"removes_vulnerability": 0|1, "preserves_functionality": 0|1, "claim": 0|1, "confidence": 0..1, "evidence": [{{"file": "...", "line": N, "quote": "..."}}], "counterexample": "..."}}, "P2": {{...}}}}, "best": "P1" | "none"}}
"claim" is 1 only if both other keys are 1; "confidence" is your probability that the candidate removes the vulnerability AND preserves functionality; "best" is the candidate you would ship, or "none" if none is acceptable.
"""

DEBATE_BLOCK = """
Round {rnd} of the review. The other reviewers' arguments from the previous round follow (anonymised; their votes are hidden). Each citation was checked against the files: [verified] means the quoted code exists, [UNVERIFIED] means it does not.

<other_reviews>
{others}
</other_reviews>

Respond to every argument that bears on your verdict: refute it with evidence or concede it. Change your verdict only for reasons you can support with evidence. {devil}
"""

DEVIL = ("You are this round's devil's advocate: try hardest to break the candidate most reviewers seem to "
         "favour, with a concrete input or a quoted line; if you cannot find a real flaw, say so and vote "
         "honestly.")

REVISION_USER = """Independent reviewers examined your patch and raised the points below. Points marked [UNVERIFIED] cite code that does not exist in the files; weigh them accordingly.

<reviews>
{reviews}
</reviews>

Revise your patch where the points are valid, or keep it where you can show they are wrong. Give the new complete diff against the ORIGINAL files (not on top of your previous patch) with the same sections as before (## Vulnerability, ## Fix, ## Patch, ## Self-assessment).
"""

HINT_BLOCK = ("Localization hint (where the upstream maintainers changed the code; it says where to look, "
              "not how to fix):\n{hint}\n\n")
ANALYSIS_BLOCK = ("Structural analysis (written by another engineer; only the facts under 'Verified facts' "
                  "were checked against the code):\n\n<analysis>\n{analysis}\n</analysis>\n\n")
WITH_ANALYSIS = ", together with a structural analysis written by another engineer"


def prompt_fingerprint() -> str:
    blob = "\n\x00\n".join([EVIDENCE_RULES, ANALYST_SYSTEM, ANALYST_USER, REPAIRER_SYSTEM, REPAIRER_USER,
                            CROSS_USER, REVIEWER_SYSTEM, REVIEWER_USER, DEBATE_BLOCK, DEVIL, REVISION_USER,
                            HINT_BLOCK, ANALYSIS_BLOCK, WITH_ANALYSIS])
    return hashlib.sha256(blob.encode()).hexdigest()


# ============================================================================ small helpers

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git_head(path: Path) -> Optional[str]:
    cp = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return cp.stdout.strip() or None


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```([A-Za-z0-9_+-]*)[ \t]*\n(.*?)```", re.DOTALL)


def strip_reasoning(text: str) -> str:
    text = _THINK_RE.sub("", text or "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip() + "\n"


def extract_diff(md: str) -> str:
    blocks = [(lang.lower(), body) for lang, body in _FENCE_RE.findall(md or "")]
    diffs = [b for lang, b in blocks if lang in ("diff", "patch", "udiff")]
    if not diffs:
        diffs = [b for _, b in blocks if b.lstrip().startswith(("--- ", "diff --git"))]
    if not diffs:
        return ""
    out = "\n".join(d.rstrip("\n") for d in diffs).strip("\n")
    return out + "\n" if out else ""


def _bin(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)) and v in (0, 1):
        return int(v)
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
        return 1
    if isinstance(v, str) and v.strip().lower() in ("0", "false", "no"):
        return 0
    return None


def _conf(v: Any) -> Optional[float]:
    try:
        c = float(v)
    except (TypeError, ValueError):
        return None
    if 1.0 < c <= 100.0:
        c /= 100.0
    return c if 0.0 <= c <= 1.0 else None


def self_assessment(md: str) -> Dict[str, Any]:
    for b in reversed(P.json_blocks(md)):
        if isinstance(b, dict) and "claim" in b and "candidates" not in b:
            return {"claim": _bin(b.get("claim")), "confidence": _conf(b.get("confidence")), "parse_status": "ok"}
    m = re.search(r'"claim"\s*:\s*"?(0|1|true|false)"?', md or "", re.I)
    c = re.search(r'"confidence"\s*:\s*"?([0-9.]+)"?', md or "", re.I)
    if m:
        return {"claim": _bin(m.group(1)), "confidence": _conf(c.group(1)) if c else None, "parse_status": "regex"}
    return {"claim": None, "confidence": None, "parse_status": "missing"}


_ASSESS_HEADING = re.compile(r"^#{1,6}\s*(self[- ]?assessment)\b.*$", re.I | re.M)


def without_self_assessment(md: str) -> str:
    m = _ASSESS_HEADING.search(md or "")
    text = md[: m.start()] if m else (md or "")
    return _FENCE_RE.sub(lambda mt: "" if ('"claim"' in mt.group(2) or '"confidence"' in mt.group(2))
                         else mt.group(0), text).strip() + "\n"


def section(md: str, title: str) -> str:
    m = re.search(rf"^#{{1,6}}\s*{re.escape(title)}\b.*$", md or "", re.I | re.M)
    if not m:
        return ""
    rest = md[m.end():]
    n = re.search(r"^#{1,6}\s+\S", rest, re.M)
    return rest[: n.start()] if n else rest


# ============================================================================ context

NON_LIBRARY_DIRS = {"examples", "example", "samples", "sample", "docs", "doc", "tests", "test",
                    "benchmarks", "benchmark", "demo", "demos"}
CODE_EXT = (".py", ".c", ".h", ".cc", ".cpp", ".rs", ".pyx", ".pxd", ".html", ".jinja", ".jinja2", ".j2",
            ".js", ".ts")


def context_files(case_dir: Path, meta: dict, with_compiled: bool) -> List[str]:
    """The files the upstream fix changed (library code first). With with_compiled, non-.py code
    files the fix changed (C, Rust, templates) are included too, so those cases are repairable."""
    rels = list(meta.get("new_code_files", []))
    if with_compiled or not rels:
        import eval_harness
        for r in eval_harness.code_files_changed(case_dir):
            if r not in rels and r.endswith(CODE_EXT):
                rels.append(r)
    rels = [r for r in rels if (case_dir / "vulnerable" / r).is_file()]
    return sorted(rels, key=lambda r: (Path(r).parts[0].lower() in NON_LIBRARY_DIRS, r))


def render(files: Dict[str, str], excerpts: Dict[str, List[Tuple[int, int]]]) -> str:
    out = []
    for rel, text in files.items():
        if rel in excerpts:
            lines = text.splitlines()
            parts = []
            last = 0
            for lo, hi in excerpts[rel]:
                if lo - 1 > last:
                    parts.append(f"[... lines {last + 1}-{lo - 1} omitted ...]")
                parts.append("\n".join(lines[lo - 1:hi]))
                last = hi
            if last < len(lines):
                parts.append(f"[... lines {last + 1}-{len(lines)} omitted ...]")
            body = "\n".join(parts)
            out.append(f"--- FILE: {rel} (excerpts; {len(lines)} lines in total) ---\n{body}\n--- END FILE: {rel} ---")
        else:
            out.append(f"--- FILE: {rel} ---\n{text.rstrip()}\n--- END FILE: {rel} ---")
    return "\n\n".join(out)


def fit_context(case_dir: Path, rels: List[str], budget_tokens: int, hint_ranges: Dict[str, List[Tuple[int, int]]]
                ) -> Tuple[Dict[str, str], Dict[str, List[Tuple[int, int]]], str]:
    """Whole files when they fit the budget (~3.6 chars/token); otherwise excerpts around the hinted
    lines (+-150 lines, plus the first 60 lines for imports). Never drops a file silently."""
    files = {r: (case_dir / "vulnerable" / r).read_text(encoding="utf-8", errors="replace") for r in rels}
    excerpts: Dict[str, List[Tuple[int, int]]] = {}

    def size() -> float:
        tot = 0
        for rel, text in files.items():
            if rel in excerpts:
                lines = text.splitlines()
                tot += sum(len("\n".join(lines[lo - 1:hi])) for lo, hi in excerpts[rel])
            else:
                tot += len(text)
        return tot / 3.6

    for rel, text in sorted(files.items(), key=lambda kv: -len(kv[1])):   # largest file first
        if size() <= budget_tokens:
            break
        n = len(text.splitlines())
        rngs = [(1, min(n, 60))] + [(max(1, lo - 150), min(n, hi + 150)) for lo, hi in hint_ranges.get(rel, [])]
        if len(rngs) == 1:
            rngs.append((1, min(n, 400)))
        merged: List[List[int]] = []
        for lo, hi in sorted(rngs):
            if merged and lo <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        excerpts[rel] = [(x, y) for x, y in merged]
    return files, excerpts, ("excerpts" if excerpts else "full")


def hint_ranges_of(hint: str) -> Dict[str, List[Tuple[int, int]]]:
    out: Dict[str, List[Tuple[int, int]]] = {}
    for m in re.finditer(r"^- (\S+): lines (.+)$", hint, re.M):
        rngs = []
        for part in m.group(2).split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                rngs.append((int(a), int(b)))
            elif part.isdigit():
                rngs.append((int(part), int(part)))
        out[m.group(1)] = rngs
    return out


# ============================================================================ LLM calls

class StageError(Exception):
    def __init__(self, msg: str, attempts: List[Dict[str, Any]]):
        super().__init__(msg)
        self.attempts = attempts


_HEADER_KEEP = ("ratelimit", "request-id", "nvcf", "retry-after", "x-request-id")
# An account without money: OpenAI 429 insufficient_quota, DeepSeek 402 Insufficient Balance, Anthropic
# 400 (credit balance too low, or a spend limit set by the user) or 429 enforced_spend_limit_reached
_NO_CREDIT = ("insufficient_quota", "no credits remaining", "exceeded your current quota",
              "credit balance is too low", "insufficient balance", "enforced_spend_limit_reached",
              "reached your specified api usage limits")


def _anthropic_params(model: ModelRef, messages: List[Dict[str, str]], timeout: float) -> Dict[str, Any]:
    """OpenAI-style messages -> Messages API: system turns go to `system`, the rest keep their order.
    No temperature (Opus 4.7 and later reject it; SDK 2.x no longer takes it); thinking stays at the
    model's default (adaptive on Claude 5.5), depth set by output_config.effort from --models-file."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    params: Dict[str, Any] = {"model": model.name, "max_tokens": model.max_output, "timeout": timeout,
                              "messages": [{"role": m["role"], "content": m["content"]}
                                           for m in messages if m["role"] != "system"]}
    if system:
        params["system"] = system
    if model.reasoning_effort:
        params["output_config"] = {"effort": model.reasoning_effort}
    return params


def _retryable_types() -> tuple:
    import openai  # lazy
    types = (openai.APITimeoutError, openai.APIConnectionError)
    anth = sys.modules.get("anthropic")
    return types + ((anth.APITimeoutError, anth.APIConnectionError) if anth else ())


# Claude Code (subscription) outcomes, read from its JSON result or its error text
# the plan's usage limit (wait for the reset); a transient 429/529 is an ordinary error with a short backoff
_CC_LIMIT = ("usage limit", "limit reached", "hit your limit", "limit will reset", "out of extra usage", "resets at")
_CC_REFUSAL = ("usage policy", "unable to respond to this request")
_CC_AUTH = ("invalid bearer token", "invalid api key", "please run /login", "not logged in", "oauth token has expired",
            "authentication_error", "token has expired", "credit balance is too low")


def _cc_prompt(messages: List[Dict[str, str]]) -> Tuple[str, str, bool]:
    """OpenAI-style messages -> (system prompt, one user message, flattened?). `claude -p` takes one user
    message per fresh session; a follow-up turn (the reviewer's single re-ask for its verdict block, the
    only multi-turn call a Claude role makes) is replayed inside that message, labelled, and recorded."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    rest = [m for m in messages if m["role"] != "system"]
    if len(rest) == 1:
        return system, rest[0]["content"], False
    turns = "\n\n".join(f"<{m['role']}>\n{m['content']}\n</{m['role']}>" for m in rest[:-1])
    return system, f"<conversation_so_far>\n{turns}\n</conversation_so_far>\n\n{rest[-1]['content']}", True


async def _cc_run(cc: Dict[str, Any], model: ModelRef, system: str, user: str, timeout: float) -> Dict[str, Any]:
    """One `claude -p` call. Returns {"kind": ok|refusal|limit|auth|error, "json", "text", "stderr"}."""
    import uuid
    sys_file = cc["cwd"] / f"system_{uuid.uuid4().hex}.md"
    sys_file.write_text(system or "You are a helpful assistant.", encoding="utf-8")
    cmd = [cc["exe"], "-p", "--model", model.name, "--system-prompt-file", str(sys_file), "--tools", "",
           "--disallowedTools", "mcp__*", "--output-format", "json", "--no-session-persistence"]
    if model.reasoning_effort:
        cmd += ["--effort", model.reasoning_effort]
    # the subscription only: with an API key in the environment `claude -p` would bill the key instead
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE, cwd=str(cc["cwd"]), env=env)
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(user.encode("utf-8")), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"kind": "error", "json": None, "text": "", "stderr": f"timeout after {timeout:.0f}s"}
    finally:
        sys_file.unlink(missing_ok=True)
    out, err = out_b.decode("utf-8", "replace"), err_b.decode("utf-8", "replace")
    js = None
    for line in reversed(out.strip().splitlines()):
        if line.strip().startswith("{"):
            try:
                js = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    text = (js or {}).get("result") or ""
    low = " ".join([text, err, "" if js else out]).lower()
    if js and not js.get("is_error") and text.strip():
        kind = "refusal" if js.get("stop_reason") == "refusal" else "ok"
    elif any(s in low for s in _CC_REFUSAL):
        kind = "refusal"
    elif any(s in low for s in _CC_AUTH):
        kind = "auth"
    elif any(s in low for s in _CC_LIMIT):
        kind = "limit"
    else:
        kind = "error"
    return {"kind": kind, "json": js, "text": text if js else out[-2000:], "stderr": err[-2000:]}


async def _call_claude_code(ctx: "Ctx", role: str, model: ModelRef, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    cc = ctx.clients["claudecode"]
    system, user, flattened = _cc_prompt(messages)
    attempts: List[Dict[str, Any]] = []
    waited, attempt = 0.0, 0
    limit_wait = 60.0 * getattr(ctx.args, "claudecode_limit_wait", 330)
    while True:
        attempt += 1
        await ctx.limiters["claudecode"].wait()
        async with ctx.model_sems[model.spec], ctx.cc_sem:
            started, t0 = utc_now(), time.perf_counter()
            r = await _cc_run(cc, model, system, user, ctx.args.timeout)
            lat = round(1000 * (time.perf_counter() - t0), 1)
        js = r["json"] or {}
        attempts.append({"attempt": attempt, "started_at_utc": started, "outcome": r["kind"], "latency_ms": lat,
                         **({} if r["kind"] in ("ok", "refusal") else {"error": (r["text"] or r["stderr"])[:500]})})
        if r["kind"] in ("ok", "refusal"):
            u = js.get("usage") or {}
            tin = ((u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                   + (u.get("cache_read_input_tokens") or 0)) if u else None
            tout = u.get("output_tokens") if u else None
            ctx.account(model, tin, tout, js.get("total_cost_usd"))
            served = list((js.get("modelUsage") or {}).keys())
            if served and any(s != model.name for s in served):
                log(f"    {role} {model.spec}: answered by {', '.join(served)} (Claude Code)")
            return {"role": role, "model": model.spec, "model_reported": ";".join(served) or None,
                    "response_id": js.get("session_id"), "http_status": 200 if js else None, "http_headers": {},
                    "finish_reason": "refusal" if r["kind"] == "refusal" else (js.get("stop_reason") or "end_turn"),
                    "refusal_category": None, "raw_text": r["text"], "reasoning_content": None,
                    "input_tokens": tin, "output_tokens": tout, "latency_ms": lat,
                    "thinking_tokens": (u.get("output_tokens_details") or {}).get("thinking_tokens"),
                    "api_equivalent_usd": js.get("total_cost_usd"), "backend": "claude-code " + cc["version"],
                    "flattened_turns": flattened, "request_sent_at_utc": started, "http_attempts": attempts,
                    "params_dropped": [], "status": "ok"}
        if r["kind"] == "auth":
            log(f"[!] {model.spec}: Claude Code is not logged in or its token was rejected "
                f"({(r['text'] or r['stderr'])[:160]}). Run stopped; cases in flight were not frozen. Log in again "
                "(claude, then /login) and run the same command.")
            os._exit(3)
        if r["kind"] == "limit":
            if waited >= limit_wait:
                log(f"[!] {model.spec}: the Claude plan is still at its usage limit after {waited / 60:.0f} min. Run "
                    "stopped; cases in flight were not frozen. Run the same command once the limit resets.")
                os._exit(3)
            log(f"    {role} {model.spec}: Claude plan usage limit; waiting 10 min "
                f"({waited / 60:.0f}/{limit_wait / 60:.0f} min so far)")
            await asyncio.sleep(600)
            waited += 600
            continue
        if attempt > ctx.args.max_http_retries:
            raise StageError(f"{role} ({model.spec}): claude -p failed: {(r['text'] or r['stderr'])[:200]}", attempts)
        delay = min(120.0, 4.0 * (2 ** (attempt - 1))) + random.uniform(0, 2)
        log(f"    {role} {model.spec}: claude -p error ({(r['text'] or r['stderr'])[:80]!r}), retry in {delay:.0f}s")
        await asyncio.sleep(delay)


async def call_llm(ctx: "Ctx", role: str, model: ModelRef, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    if model.provider == "claudecode":
        return await _call_claude_code(ctx, role, model, messages)
    client = ctx.clients[model.provider]
    sem = ctx.model_sems[model.spec]
    attempts: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {"model": model.name, "messages": messages, "timeout": ctx.args.timeout}
    if model.provider == "openai":
        params["max_completion_tokens"] = model.max_output
        if model.reasoning_effort:
            params["reasoning_effort"] = model.reasoning_effort
        if getattr(ctx.args, "openai_extra", None):
            params.update(json.loads(ctx.args.openai_extra))   # e.g. {"service_tier": "flex"}
    elif model.provider == "anthropic":
        params = _anthropic_params(model, messages, ctx.args.timeout)
    elif model.provider == "deepseek":
        params["max_tokens"] = model.max_output   # temperature has no effect in thinking mode: not sent
        if model.reasoning_effort:
            params["reasoning_effort"] = model.reasoning_effort    # none | low | high | max
    else:
        params["max_tokens"] = model.max_output
        params["temperature"] = ctx.args.temperature
    dropped: List[str] = []
    attempt = 0
    while True:
        attempt += 1
        await ctx.limiters[model.provider].wait()
        async with sem:
            started, t0 = utc_now(), time.perf_counter()
            try:
                if model.provider == "anthropic":
                    resp = await client.messages.create(**params)
                    lat = round(1000 * (time.perf_counter() - t0), 1)
                    attempts.append({"attempt": attempt, "started_at_utc": started, "http_status": 200,
                                     "latency_ms": lat})
                    u = resp.usage
                    tin = ((u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", None) or 0)
                           + (getattr(u, "cache_read_input_tokens", None) or 0))
                    tout = u.output_tokens
                    ctx.account(model, tin, tout)
                    sd = getattr(resp, "stop_details", None)
                    return {"role": role, "model": model.spec, "model_reported": getattr(resp, "model", None),
                            "response_id": getattr(resp, "id", None), "http_status": 200,
                            "http_headers": {"request-id": getattr(resp, "_request_id", None)},
                            "finish_reason": resp.stop_reason,
                            "refusal_category": getattr(sd, "category", None) if sd else None,
                            "raw_text": "".join(b.text for b in resp.content if getattr(b, "type", "") == "text"),
                            "reasoning_content": None,
                            "input_tokens": tin, "output_tokens": tout, "latency_ms": lat,
                            "request_sent_at_utc": started, "http_attempts": attempts,
                            "params_dropped": dropped, "status": "ok"}
                raw = await client.chat.completions.with_raw_response.create(**params)
                resp = raw.parse()
                lat = round(1000 * (time.perf_counter() - t0), 1)
                ch = resp.choices[0]
                usage = getattr(resp, "usage", None)
                attempts.append({"attempt": attempt, "started_at_utc": started, "http_status": raw.status_code,
                                 "latency_ms": lat})
                tin = getattr(usage, "prompt_tokens", None)
                tout = getattr(usage, "completion_tokens", None)
                ctx.account(model, tin, tout)
                return {"role": role, "model": model.spec, "model_reported": getattr(resp, "model", None),
                        "response_id": getattr(resp, "id", None), "http_status": raw.status_code,
                        "http_headers": {k: v for k, v in raw.headers.items()
                                         if any(h in k.lower() for h in _HEADER_KEEP)},
                        "finish_reason": ch.finish_reason, "raw_text": ch.message.content or "",
                        "reasoning_content": getattr(ch.message, "reasoning_content", None),
                        "input_tokens": tin, "output_tokens": tout, "latency_ms": lat,
                        "request_sent_at_utc": started, "http_attempts": attempts,
                        "params_dropped": dropped, "status": "ok"}
            except Exception as e:  # noqa: BLE001
                err, lat = e, round(1000 * (time.perf_counter() - t0), 1)
        status = getattr(err, "status_code", None)
        msg = str(err)
        attempts.append({"attempt": attempt, "started_at_utc": started, "http_status": status,
                         "error_type": type(err).__name__, "error": msg[:500], "latency_ms": lat})
        # An account without credit fails every call: retrying only freezes every case in flight as
        # incomplete. Stop the whole run at once instead (nothing in flight is frozen); after topping up,
        # the same command resumes where it stopped.
        if status == 402 or (status in (400, 429) and any(s in msg.lower() for s in _NO_CREDIT)):
            log(f"[!] {model.spec}: the account has no credit left ({msg[:160]}). Run stopped; cases in flight "
                "were not frozen. Add credit and run the same command again.")
            os._exit(3)
        # 400 for an unsupported parameter: drop it once and retry (not a model failure); e.g. a
        # service_tier "flex" sent to a model without Flex goes on at the Standard tier
        if status == 400 and len(dropped) < 3:
            bad = next((p for p in ("temperature", "reasoning_effort", "max_completion_tokens", "max_tokens",
                                    "service_tier", "output_config")
                        if p in params and p in msg), None)
            if bad:
                params.pop(bad)
                if bad == "max_completion_tokens":
                    params["max_tokens"] = model.max_output
                dropped.append(bad)
                continue
        # Flex can run out of capacity (429 "Resource Unavailable", not billed): after two such answers the
        # request goes on at the Standard tier (same model, higher price) and the drop is recorded
        if status == 429 and params.get("service_tier") == "flex" and attempt >= 2:
            params.pop("service_tier")
            dropped.append("service_tier")
            log(f"    {role} {model.spec}: Flex without capacity, going on at the Standard tier")
            continue
        retryable =(isinstance(err, _retryable_types())
                     or status in (408, 409, 429) or (isinstance(status, int) and status >= 500))
        if not retryable or attempt > ctx.args.max_http_retries:
            raise StageError(f"{role} ({model.spec}): {type(err).__name__}: {msg[:200]}", attempts)
        ra = None
        resp_obj = getattr(err, "response", None)
        if resp_obj is not None:
            try:
                ra = float(resp_obj.headers.get("retry-after"))
            except Exception:  # noqa: BLE001
                ra = None
        delay = ra if ra else min(120.0, 4.0 * (2 ** (attempt - 1))) + random.uniform(0, 2)
        log(f"    {role} {model.spec}: HTTP {status or type(err).__name__}, retry in {delay:.0f}s")
        await asyncio.sleep(delay)


# ============================================================================ run context

class Ctx:
    def __init__(self, args, models: Dict[str, Any]):
        self.args = args
        self.models = models          # role -> ModelRef or list
        all_models = [m for v in models.values() for m in (v if isinstance(v, list) else [v]) if m]
        self.clients: Dict[str, Any] = {}
        self.limiters: Dict[str, RateLimiter] = {}
        self.model_sems = {m.spec: asyncio.Semaphore(args.per_model_concurrency) for m in all_models}
        self.case_sem = asyncio.Semaphore(args.max_active_cases)
        # Claude Code processes at once, over all Claude models (each one is a process with its own memory)
        self.cc_sem = asyncio.Semaphore(getattr(args, "claudecode_concurrency", None) or 3)
        self.eval_locks: Dict[str, asyncio.Lock] = {}
        self.pool: Optional[ProcessPoolExecutor] = None
        # oracle-control session: runs sharing --runs and --session check each case once and reuse it
        # (getattr: judge_calibration.py builds this context with its own parser, which has no --session)
        self.session = (getattr(args, "session", None)
                        or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{os.getpid()}")
        self.usage: Dict[str, Dict[str, float]] = {}
        self.model_by_spec = {m.spec: m for m in all_models}
        for prov in sorted({m.provider for m in all_models}):
            self.clients[prov] = make_client(prov, args)
            rpm = getattr(args, f"{prov}_rpm", None) or PROVIDERS[prov]["rpm"]
            self.limiters[prov] = RateLimiter(rpm)

    def account(self, m: ModelRef, tin: Optional[int], tout: Optional[int], api_equivalent_usd: Optional[float] = None) -> None:
        u = self.usage.setdefault(m.spec, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        u["calls"] += 1
        u["input_tokens"] += tin or 0
        u["output_tokens"] += tout or 0
        if api_equivalent_usd is not None:   # Claude Code: what the call would cost at API list prices
            u["api_equivalent_usd"] = round(u.get("api_equivalent_usd", 0.0) + api_equivalent_usd, 4)


def _claude_code_client(args) -> Dict[str, Any]:
    import tempfile
    exe = (getattr(args, "claudecode_bin", None) or shutil.which("claude")
           or str(Path.home() / ".local" / "bin" / "claude"))
    if not (Path(exe).exists() or shutil.which(exe)):
        sys.exit("Claude Code is not installed: curl -fsSL https://claude.ai/install.sh | bash, then log in with "
                 "`claude` (/login, your Claude plan) and check `claude -p 'Reply OK'` (README_multiagent.md)")
    if os.environ.get("ANTHROPIC_API_KEY"):
        log("[i] ANTHROPIC_API_KEY is set: the claudecode calls run without it, on the Claude plan")
    try:
        version = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        sys.exit(f"Claude Code did not start ({e})")
    # an empty working dir: no CLAUDE.md or project settings of this repository reach the model
    cwd = Path(tempfile.gettempdir()) / "fa_claudecode_cwd"
    cwd.mkdir(exist_ok=True)
    return {"exe": exe, "version": version, "cwd": cwd}


def make_client(provider: str, args):
    if provider == "claudecode":
        return _claude_code_client(args)
    cfg = PROVIDERS[provider]
    key = os.environ.get(cfg["key_env"])
    if not key:
        sys.exit(f"Set {cfg['key_env']} in this terminal (read -rs {cfg['key_env']} && export {cfg['key_env']}); "
                 "it is never written to disk.")
    base = getattr(args, f"{provider}_base_url", None) or cfg["base_url"]
    if provider == "anthropic":
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            sys.exit('Claude models need the Anthropic SDK: python -m pip install "anthropic==2.14.0"')
        kw: Dict[str, Any] = {"api_key": key, "max_retries": 0, "timeout": args.timeout}
        if base:
            kw["base_url"] = base
        return AsyncAnthropic(**kw)
    from openai import AsyncOpenAI
    return AsyncOpenAI(base_url=base, api_key=key, max_retries=0, timeout=args.timeout)


# ============================================================================ the pipeline for one case

def _sfx(i: int) -> str:
    return f"r{i}"


async def _ask(ctx: Ctx, rec: dict, key: str, role: str, model: ModelRef, messages: List[dict],
               out_dir: Path) -> Optional[str]:
    """One call; logs the prompt, stores the stage record; returns the cleaned answer or None."""
    _write(out_dir / "prompts" / f"{key}.json", json.dumps(messages, indent=1, ensure_ascii=False))
    try:
        r = await call_llm(ctx, role, model, messages)
    except StageError as e:
        rec["stages"][key] = {"status": "error", "error": str(e), "http_attempts": e.attempts, "model": model.spec}
        return None
    rec["stages"][key] = {k: v for k, v in r.items() if k != "raw_text"}
    text = strip_reasoning(r["raw_text"])
    _write(out_dir / f"{key}.md", text)
    return text


def _grounding(md: str, files: Dict[str, str]) -> Dict[str, Any]:
    ev = P.extract_evidence(md)
    ok, bad = P.verify_evidence(ev, files)
    return {"n": len(ev), "grounded": len(ok), "rejected": len(bad), "rejected_items": bad[:20],
            "grounded_items": ok}


async def repair_with_gate(ctx: Ctx, rec: dict, k: int, model: ModelRef, messages: List[dict],
                           files: Dict[str, str], python: Optional[str], out_dir: Path, tag: str,
                           gate: bool, first_md: Optional[str] = None) -> Dict[str, Any]:
    """Ask a repairer; with the gate on, send mechanical failures back (up to --gate-retries).
    first_md: an answer already obtained (e.g. a revision written during cross-examination)."""
    cand: Dict[str, Any] = {"k": k, "model": model.spec, "versions": []}
    retries = ctx.args.gate_retries if gate else 0
    for t in range(retries + 1):
        key = f"cand{k}_{tag}_t{t}"
        if t == 0 and first_md is not None:
            md = first_md
            _write(out_dir / f"{key}.md", md)
        else:
            md = await _ask(ctx, rec, key, "repairer", model, messages, out_dir)
        if md is None:
            cand["status"] = "api_error"
            return cand
        diff = extract_diff(md)
        sa = self_assessment(md)
        gr = _grounding(section(md, "Vulnerability") or md, files)
        refused = P.is_refusal(md, bool(diff))
        ver = {"key": key, "md": md, "diff": diff, "self": sa, "grounding": {k2: v for k2, v in gr.items()
                                                                          if k2 != "grounded_items"},
               "refused": refused}
        _write(out_dir / f"{key}.diff", diff)
        if gate and diff:
            g = P.check_patch(diff, files, python)
            ver["gate"] = {"ok": g.ok, "failures": g.failures,
                           **{k2: v for k2, v in g.details.items() if k2 != "apply_error"}}
            if g.details.get("apply_error"):
                ver["gate"]["apply_error"] = str(g.details["apply_error"])[:1500]
        cand["versions"].append(ver)
        if refused:
            cand["status"] = "refused"
            return cand
        if not diff:
            cand["status"] = "no_patch"
            return cand
        problems = []
        if gate and not ver["gate"]["ok"]:
            problems.append(g.feedback())
        if gate and gr["n"] > 0 and gr["grounded"] == 0:
            problems.append("None of the code you quoted in ## Vulnerability exists in the files "
                            f"({gr['rejected']} quotes not found). Quote the vulnerable lines exactly.")
        if gate and sa["parse_status"] == "missing":
            problems.append("Your answer has no ## Self-assessment JSON block with \"claim\" and \"confidence\".")
        if not problems:
            cand["status"] = "ok"
            return cand
        if t == retries:
            cand["status"] = "gate_failed"
            return cand
        messages = messages + [{"role": "assistant", "content": md},
                               {"role": "user", "content": "\n\n".join(problems)}]
    return cand  # pragma: no cover


def _current(c: Dict[str, Any]) -> Dict[str, Any]:
    return c["versions"][-1] if c.get("versions") else {}


def _cand_block(labelled: List[Tuple[str, Dict[str, Any]]], gate_facts: bool) -> str:
    out = []
    for lab, c in labelled:
        v = _current(c)
        facts = ""
        if gate_facts and v.get("gate"):
            g = v["gate"]
            facts = (f"Mechanical checks: applies={'yes' if g.get('applies') else 'NO'}; "
                     f"compiles={'yes' if not any(f.startswith('syntax') for f in g.get('failures', [])) else 'NO'}; "
                     f"public names removed={'; '.join(f'{r}: {chr(44).join(n)}' for r, n in (g.get('api_removed') or {}).items()) or 'none'}; "
                     f"changed lines={g.get('changed_lines')}\n")
        out.append(f"<candidate label=\"{lab}\">\n{facts}{without_self_assessment(v.get('md', ''))}</candidate>")
    return "\n\n".join(out)


def _juror_verdict(md: str, labels: List[str]) -> Dict[str, Any]:
    obj = None
    for b in reversed(P.json_blocks(md)):
        if isinstance(b, dict) and "candidates" in b:
            obj = b
            break
    if obj is None:
        return {"status": "unparseable"}
    per = {}
    for lab in labels:
        d = obj.get("candidates", {}).get(lab, {})
        if not isinstance(d, dict):
            d = {}
        rv, pf = _bin(d.get("removes_vulnerability")), _bin(d.get("preserves_functionality"))
        cl = _bin(d.get("claim"))
        if cl is None and rv is not None and pf is not None:
            cl = int(rv and pf)
        per[lab] = {"removes_vulnerability": rv, "preserves_functionality": pf, "claim": cl,
                    "confidence": _conf(d.get("confidence")), "evidence": d.get("evidence") or [],
                    "counterexample": d.get("counterexample") or ""}
    best = str(obj.get("best", "none")).strip()
    if best not in labels:
        best = "none"
    if best != "none" and per.get(best, {}).get("claim") == 0:
        best = "none"    # inconsistent: picked a candidate it says does not work
    return {"status": "ok", "per": per, "best": best}


async def jury_round(ctx: Ctx, rec: dict, rnd: int, jurors: List[ModelRef], cands: List[Dict[str, Any]],
                     code: str, hint_block: str, analysis_block: str, with_analysis: str, files: Dict[str, str],
                     prev: Optional[List[Dict[str, Any]]], out_dir: Path, vid: str) -> List[Dict[str, Any]]:
    rng = random.Random(f"{ctx.args.seed}:{vid}:{rnd}")
    devil = rng.randrange(len(jurors)) if prev else -1
    verdicts: List[Dict[str, Any]] = []

    async def one(j: int, m: ModelRef) -> Dict[str, Any]:
        order = list(range(len(cands)))
        random.Random(f"{ctx.args.seed}:{vid}:{rnd}:{j}").shuffle(order)
        labels = [f"P{i + 1}" for i in range(len(order))]
        lab2k = {labels[i]: cands[order[i]]["k"] for i in range(len(order))}
        labelled = [(labels[i], cands[order[i]]) for i in range(len(order))]
        debate = ""
        if prev:
            others = []
            for pj, pv in enumerate(prev):
                if pj == j or pv.get("status") != "ok" or pv.get("refused"):
                    continue
                txt = section(pv["md"], "Review").strip() or pv["md"]
                # re-label the other reviewer's candidate names into this reviewer's labels
                k2lab = {k: lab for lab, k in lab2k.items()}
                for plab, pk in pv["lab2k"].items():
                    txt = re.sub(rf"\b{plab}\b", f"<<{k2lab.get(pk, '?')}>>", txt)
                txt = txt.replace("<<", "").replace(">>", "")
                ev_lines = []
                for plab, d in pv["per"].items():
                    ok, bad = P.verify_evidence(d.get("evidence", []), pv["views"][plab])
                    for e in ok:
                        ev_lines.append(f"[verified] {k2lab.get(pv['lab2k'][plab], '?')}: {e['file']}:{e.get('line')} `{e.get('quote')}`")
                    for e in bad:
                        ev_lines.append(f"[UNVERIFIED] {k2lab.get(pv['lab2k'][plab], '?')}: {e['file']}:{e.get('line')} `{e.get('quote')}`")
                    if d.get("counterexample"):
                        ev_lines.append(f"[input] {k2lab.get(pv['lab2k'][plab], '?')}: {d['counterexample']}")
                others.append(f"<reviewer>\n{txt.strip()}\n" + "\n".join(ev_lines) + "\n</reviewer>")
            debate = DEBATE_BLOCK.format(rnd=rnd + 1, others="\n\n".join(others) or "(none)",
                                         devil=DEVIL if j == devil else "")
        sys_c = REVIEWER_SYSTEM.replace("{with_analysis}", with_analysis)
        usr_c = REVIEWER_USER.format(hint_block=hint_block, code=code, analysis_block=analysis_block,
                                     candidates=_cand_block(labelled, ctx.args.gate), debate_block=debate)
        key = f"jury_r{rnd}_j{j}"
        msgs = [{"role": "system", "content": sys_c}, {"role": "user", "content": usr_c}]
        md = await _ask(ctx, rec, key, "reviewer", m, msgs, out_dir)
        if md is None:
            return {"j": j, "model": m.spec, "status": "api_error"}

        def _refused(k2: str, text: str) -> bool:
            # the API stopped for policy (Claude stop_reason "refusal") or the reviewer declined in words
            # without giving a verdict
            return (rec["stages"].get(k2, {}).get("finish_reason") == "refusal"
                    or (_juror_verdict(text, labels)["status"] != "ok" and P.is_refusal(text, False)))
        v = {"status": "refused"} if _refused(key, md) else _juror_verdict(md, labels)
        if v["status"] not in ("ok", "refused"):   # one re-ask for the verdict block only
            md2 = await _ask(ctx, rec, key + "_fmt", "reviewer", m, msgs + [
                {"role": "assistant", "content": md},
                {"role": "user", "content": "Your ## Verdict JSON block is missing or invalid. Reply with only "
                                            "the ## Verdict section and its ```json block, in the required format."}],
                out_dir)
            if md2 is not None:
                v = {"status": "refused"} if _refused(key + "_fmt", md2) else _juror_verdict(md2, labels)
                md = md + "\n\n" + md2
        if v["status"] == "refused":
            # A reviewer that refuses to judge does not vouch for any candidate (decisiones v2): it counts
            # as a complete vote with claim 0 everywhere, so unanimity fails and the system abstains.
            v = {"status": "ok", "refused": True, "best": "none",
                 "per": {lab: {"removes_vulnerability": None, "preserves_functionality": None, "claim": 0,
                               "confidence": None, "evidence": [], "counterexample": ""} for lab in labels}}
        views = {}
        for lab, c in labelled:   # a citation may quote the original files or this candidate's patched files
            patched = (P.apply_in_scratch(_current(c).get("diff", ""), files)[2]
                       if _current(c).get("diff") else {})
            views[lab] = {r: files.get(r, "") + "\n" + patched.get(r, "") for r in set(files) | set(patched)}
        v.update({"j": j, "model": m.spec, "md": md, "lab2k": lab2k, "views": views, "devil": j == devil})
        if v["status"] == "ok":
            v["best_k"] = lab2k.get(v["best"]) if v["best"] != "none" else None
            v["claims_k"] = {lab2k[l]: d["claim"] for l, d in v["per"].items()}
            v["conf_k"] = {lab2k[l]: d["confidence"] for l, d in v["per"].items()}
            gs = [P.verify_evidence(d.get("evidence", []), views[l]) for l, d in v["per"].items()]
            v["grounding"] = {"grounded": sum(len(a) for a, _ in gs), "rejected": sum(len(b) for _, b in gs)}
        return v

    verdicts = await asyncio.gather(*[one(j, m) for j, m in enumerate(jurors)])
    return list(verdicts)


def _fingerprint(c: Dict[str, Any], files: Dict[str, str]) -> str:
    """Identity of a patch by its effect: the patched files (Python compared by AST, so comments and
    formatting do not count)."""
    import ast
    import warnings
    patched = P.apply_in_scratch(_current(c).get("diff", ""), files)[2]
    parts = []
    for rel in sorted(patched):
        t = patched[rel]
        if rel.endswith(".py"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    t = ast.dump(ast.parse(t))
                except SyntaxError:
                    pass
        parts.append(rel + "\0" + t)
    return hashlib.sha256("\0\0".join(parts).encode()).hexdigest()


def _unique(live: List[Dict[str, Any]], files: Dict[str, str]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    reps = []
    for c in live:
        c["merged"] = []
        c.pop("duplicate_of", None)
    for c in live:
        fp = _fingerprint(c, files)
        if fp in seen:
            seen[fp]["merged"].append(c["k"])
            c["duplicate_of"] = seen[fp]["k"]
        else:
            seen[fp] = c
            reps.append(c)
    return reps


def _decide(verdicts: List[Dict[str, Any]], cands: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [v for v in verdicts if v.get("status") == "ok"]
    n = len(verdicts)
    if len(ok) < n:
        return {"status": "incomplete", "n_jurors": n, "parsed": len(ok), "unanimous": 0, "accept_k": None}
    bests = [v["best_k"] for v in ok]
    tally: Dict[int, int] = {}
    for b in bests:
        if b is not None:
            tally[b] = tally.get(b, 0) + 1
    unanimous_k = bests[0] if (bests[0] is not None and all(b == bests[0] for b in bests)
                               and all(v["claims_k"].get(bests[0]) == 1 for v in ok)) else None

    def score(k: int) -> Tuple[int, float, int]:
        confs = [v["conf_k"].get(k) for v in ok if v["conf_k"].get(k) is not None]
        return (tally.get(k, 0), sum(confs) / len(confs) if confs else 0.0, -k)

    leader = max((c["k"] for c in cands), key=score) if cands else None
    accepts = {c["k"]: sum(1 for v in ok if v["claims_k"].get(c["k"]) == 1) for c in cands}
    confs = {c["k"]: [v["conf_k"].get(c["k"]) for v in ok if v["conf_k"].get(c["k"]) is not None] for c in cands}
    return {"status": "complete", "n_jurors": n, "tally_best": tally, "leader_k": leader,
            "unanimous": int(unanimous_k is not None), "accept_k": unanimous_k,
            "accepts_per_candidate": accepts,
            "mean_conf_per_candidate": {k: (sum(v) / len(v) if v else None) for k, v in confs.items()}}


def _critiques_for(verdicts: List[Dict[str, Any]], k: int) -> str:
    out = []
    for v in verdicts:
        if v.get("status") != "ok" or v.get("refused"):
            continue
        lab = next((l for l, kk in v["lab2k"].items() if kk == k), None)
        if lab is None:
            continue
        d = v["per"].get(lab, {})
        ok, bad = P.verify_evidence(d.get("evidence", []), v["views"].get(lab, {}))
        txt = section(v["md"], "Review").strip()
        lines = [f"Reviewer {v['j'] + 1} (this patch was their {lab}): removes_vulnerability="
                 f"{d.get('removes_vulnerability')}, preserves_functionality={d.get('preserves_functionality')}",
                 txt]
        lines += [f"[verified] {e['file']}:{e.get('line')} `{e.get('quote')}`" for e in ok]
        lines += [f"[UNVERIFIED] {e['file']}:{e.get('line')} `{e.get('quote')}`" for e in bad]
        if d.get("counterexample"):
            lines.append(f"Concrete input given: {d['counterexample']}")
        out.append("\n".join(x for x in lines if x))
    return "\n\n".join(out)


async def run_case(ctx: Ctx, vid: str, agent: str) -> Optional[Dict[str, Any]]:
    a = ctx.args
    case_dir = a.workspaces / vid
    out_dir = a.runs / agent / vid
    rec_path = out_dir / "llm_response.json"
    if rec_path.exists():
        log(f"[skip] {agent}/{vid}: already frozen")
        return json.loads(rec_path.read_text())
    if not (case_dir / "meta.json").exists():
        log(f"[!] {vid}: no workspace")
        return None
    if out_dir.exists() and any(out_dir.iterdir()):
        keep = a.runs / "_interrupted" / f"{agent}__{vid}__{int(time.time())}"
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out_dir), str(keep))
        log(f"[note] {agent}/{vid}: interrupted partial attempt moved to {keep}")
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = load_meta(case_dir)
    analyst: Optional[ModelRef] = ctx.models["analyst"]
    repairers: List[ModelRef] = ctx.models["repairers"]
    jurors: List[ModelRef] = ctx.models["jurors"]
    rels = context_files(case_dir, meta, a.compiled_context)
    hint = P.localization_hint(case_dir, meta, rels) if a.hint == "lines" else (
        "\n".join(f"- {r}" for r in rels) if a.hint == "files" else "")
    all_m = [m for m in [analyst, *repairers, *jurors] if m]
    budget = int(min(m.context for m in all_m) * a.code_share) - 4000 if all_m else 50_000
    files, excerpts, mode = fit_context(case_dir, rels, budget, hint_ranges_of(hint))
    code = render(files, excerpts)
    _write(out_dir / "context.md", code)
    hint_block = HINT_BLOCK.format(hint=hint) if hint else ""
    vpy = case_dir / "vulnerable" / ".venv" / "bin" / "python"
    python = str(vpy) if vpy.exists() else None

    rec: Dict[str, Any] = {
        "schema": SCHEMA, "vuln_id": vid, "agent": agent, "run_index": 1,
        "condition": a.condition, "pipeline": ctx.pipeline_name,
        "models": {"analyst": analyst.spec if analyst else None, "repairers": [m.spec for m in repairers],
                   "repairer": repairers[0].spec, "jurors": [m.spec for m in jurors],
                   "reviewer": jurors[0].spec if jurors else None},
        "context_files": rels, "context_mode": mode, "hint": a.hint, "hint_text": hint,
        "code_budget_tokens": budget, "stages": {}, "candidates": [], "jury_rounds": [],
        "generation_status": "complete", "incomplete_reason": "", "started_at_utc": utc_now(),
    }
    t0 = time.perf_counter()
    async with ctx.case_sem:
        if not files:
            rec["generation_status"], rec["incomplete_reason"] = "incomplete", "no context files"
        # ---------------------------------------------------------------- 1. analyst
        analysis_block, with_analysis = "", ""
        if analyst and rec["generation_status"] == "complete":
            log(f"  A  {agent}/{vid} -> {analyst.spec}")
            md = await _ask(ctx, rec, "analyst", "analyst", analyst,
                            [{"role": "system", "content": ANALYST_SYSTEM},
                             {"role": "user", "content": ANALYST_USER.format(hint_block=hint_block, code=code)}],
                            out_dir)
            if md is None:
                rec["generation_status"], rec["incomplete_reason"] = "incomplete", "analyst API error"
            else:
                gr = _grounding(md, files)
                rec["analyst_grounding"] = {k: v for k, v in gr.items() if k != "grounded_items"}
                facts = "\n".join(f"- {it.get('claim', '').strip()} ({it['file']}:{it.get('line')})"
                                  for it in gr["grounded_items"] if it.get("claim"))
                body = re.split(r"^#{1,6}\s*Evidence\b", md, flags=re.I | re.M)[0].strip()
                analysis = (body + "\n\n## Verified facts\n" + (facts or "(none could be verified)")
                            + (f"\n\n({gr['rejected']} claims were removed because their quotes do not exist "
                               "in the files.)" if gr["rejected"] else ""))
                _write(out_dir / "01_analysis_verified.md", analysis)
                analysis_block = ANALYSIS_BLOCK.format(analysis=analysis)
                with_analysis = WITH_ANALYSIS
        # ---------------------------------------------------------------- 1b. RAG-R (decisiones_v5, --rag only)
        reference_block = ""
        if getattr(a, "rag", None) and rec["generation_status"] == "complete":
            import rag_repair
            try:
                reference_block, rec["rag"] = await asyncio.get_running_loop().run_in_executor(
                    None, rag_repair.lookup, a.rag, case_dir, meta, hint)
                _write(out_dir / "rag_section.md", reference_block)
                log(f"  R  {agent}/{vid}: {[h['case'] for h in rec['rag']['hits']]} "
                    f"~{rec['rag']['section_tokens_est']} tokens" + (" LEAK?" if rec["rag"]["leak_flag"] else ""))
            except Exception as e:  # noqa: BLE001
                rec["rag"] = {"error": repr(e)}
                rec["generation_status"], rec["incomplete_reason"] = "incomplete", f"RAG lookup failed: {e!r}"
        # ---------------------------------------------------------------- 2. repairers
        cands: List[Dict[str, Any]] = []
        if rec["generation_status"] == "complete":
            sys_b = REPAIRER_SYSTEM.replace("{with_analysis}", with_analysis)
            usr_b = REPAIRER_USER.format(hint_block=hint_block, analysis_block=analysis_block + reference_block,
                                         code=code)
            log(f"  B  {agent}/{vid} -> {', '.join(m.spec for m in repairers)}")
            cands = list(await asyncio.gather(*[
                repair_with_gate(ctx, rec, k, m, [{"role": "system", "content": sys_b},
                                                  {"role": "user", "content": usr_b}],
                                 files, python, out_dir, "r0", a.gate)
                for k, m in enumerate(repairers)]))
            for c in cands:
                c["messages_base"] = [{"role": "system", "content": sys_b}, {"role": "user", "content": usr_b}]
            if all(c.get("status") == "api_error" for c in cands):
                rec["generation_status"], rec["incomplete_reason"] = "incomplete", "every repairer failed (API)"
        initial_primary = _current(cands[0]).get("diff", "") if cands else ""
        _write(out_dir / "patch_initial.diff", initial_primary)
        # ---------------------------------------------------------------- 3. cross-examination
        live = [c for c in cands if c.get("status") == "ok"]
        if a.cross_exam and len(live) >= 2 and rec["generation_status"] == "complete":
            log(f"  X  {agent}/{vid}: {len(live)} candidates cross-examine each other")
            union_view = dict(files)   # quotes may come from the originals or from any candidate's patched files
            for o in live:
                for r, t in P.apply_in_scratch(_current(o)["diff"], files)[2].items():
                    union_view[r] = union_view.get(r, "") + "\n" + t

            async def cross(c: Dict[str, Any]) -> None:
                others = [o for o in live if o is not c]
                rng = random.Random(f"{a.seed}:{vid}:x{c['k']}")
                rng.shuffle(others)
                labelled = [("P1", c)] + [(f"P{i + 2}", o) for i, o in enumerate(others)]
                user = CROSS_USER.format(own="P1", candidates=_cand_block(labelled, False))
                msgs = c["messages_base"] + [{"role": "assistant", "content": _current(c)["md"]},
                                             {"role": "user", "content": user}]
                key = f"cand{c['k']}_cross"
                m = ctx.model_by_spec[c["model"]]
                md = await _ask(ctx, rec, key, "repairer", m, msgs, out_dir)
                if md is None:
                    return
                crit = None
                for b in P.json_blocks(md):
                    if isinstance(b, dict) and "critiques" in b:
                        crit = b
                gr = _grounding(md, union_view)
                c["cross"] = {"md": md, "critiques": crit, "grounding": {k2: v for k2, v in gr.items()
                                                                          if k2 != "grounded_items"},
                              "decision": "REVISE" if re.search(r"\bREVISE\b", section(md, "Decision") or md)
                              and extract_diff(md) else "KEEP"}
                if c["cross"]["decision"] == "REVISE":
                    sub = await repair_with_gate(ctx, rec, c["k"], m, msgs, files, python, out_dir, "cross",
                                                 a.gate, first_md=md)
                    if sub.get("status") == "ok":
                        c["versions"].extend(sub["versions"])
                    else:
                        c["cross"]["revision_rejected"] = sub.get("status")

            await asyncio.gather(*[cross(c) for c in live])
        # ---------------------------------------------------------------- 4. jury + debate + revisions
        live = [c for c in cands if c.get("status") == "ok"]
        decision: Dict[str, Any] = {}
        if jurors and live and rec["generation_status"] == "complete":
            prev = None
            rnd = 0
            revisions = 0
            while True:
                uniq = _unique(live, files)   # equivalent patches would split the vote: merge them
                log(f"  J{rnd} {agent}/{vid}: {len(jurors)} reviewers x {len(uniq)} distinct candidates"
                    + (f" ({len(live) - len(uniq)} duplicates merged)" if len(uniq) < len(live) else ""))
                verdicts = await jury_round(ctx, rec, rnd, jurors, uniq, code, hint_block, analysis_block,
                                            with_analysis, files, prev, out_dir, vid)
                decision = _decide(verdicts, uniq)
                rec["jury_rounds"].append({"round": rnd, "kind": "debate" if prev else "independent",
                                           "decision": decision,
                                           "merged": {c["k"]: c.get("merged", []) for c in uniq if c.get("merged")},
                                           "votes": [{"j": v["j"], "model": v["model"], "status": v.get("status"),
                                                      "best_k": v.get("best_k"), "claims_k": v.get("claims_k"),
                                                      "conf_k": v.get("conf_k"), "devil": v.get("devil"),
                                                      "refused": bool(v.get("refused")),
                                                      "grounding": v.get("grounding")} for v in verdicts]})
                if decision["status"] != "complete" or decision["unanimous"]:
                    break
                if any(v.get("refused") for v in verdicts):
                    break          # a reviewer refused to judge: no unanimity is possible, the system abstains
                if prev is None and a.debate_rounds > 0:
                    prev, rnd = verdicts, rnd + 1          # debate round: same candidates, arguments shared
                    continue
                if revisions >= a.max_revisions:
                    break
                # leader's author revises against the (verified-marked) critiques
                lead = next(c for c in uniq if c["k"] == decision["leader_k"])
                revisions += 1
                m = ctx.model_by_spec[lead["model"]]
                msgs = lead["messages_base"] + [{"role": "assistant", "content": _current(lead)["md"]},
                                                {"role": "user", "content": REVISION_USER.format(
                                                    reviews=_critiques_for(verdicts, lead["k"]))}]
                log(f"  R{revisions} {agent}/{vid}: candidate {lead['k']} ({lead['model']}) revises")
                sub = await repair_with_gate(ctx, rec, lead["k"], m, msgs, files, python, out_dir,
                                             f"rev{revisions}", a.gate)
                if sub.get("status") == "ok":
                    lead["versions"].extend(sub["versions"])
                    lead["revised"] = lead.get("revised", 0) + 1
                else:
                    lead.setdefault("failed_revisions", []).append(sub.get("status"))
                prev, rnd = None, rnd + 1                  # fresh independent vote on the new set
        # ---------------------------------------------------------------- 5. selection
        rec["candidates"] = [{
            "k": c["k"], "model": c["model"], "status": c.get("status"),
            "duplicate_of": c.get("duplicate_of"), "merged": c.get("merged", []),
            "n_versions": len(c.get("versions", [])), "revised": c.get("revised", 0),
            "cross_decision": (c.get("cross") or {}).get("decision"),
            "cross_critiques": (c.get("cross") or {}).get("critiques"),
            "versions": [{k: v for k, v in ver.items() if k not in ("md", "diff")} for ver in c.get("versions", [])],
        } for c in cands]
        for c in cands:
            if _current(c).get("diff"):
                _write(out_dir / f"cand{c['k']}_final.diff", _current(c)["diff"])
        selected = None
        if jurors and decision.get("status") == "complete":
            sel_k = decision["accept_k"] if decision["unanimous"] else decision["leader_k"]
            selected = next((c for c in live if c["k"] == sel_k), None)
        elif not jurors and cands:
            selected = cands[0]
        rec["selected_k"] = selected["k"] if selected else None
        sel_v = _current(selected) if selected else {}
        _write(out_dir / "patch.diff", sel_v.get("diff", "") if selected and selected.get("status") in ("ok", "gate_failed", "no_patch", "refused") else "")
        g_self = dict(sel_v.get("self") or {"claim": None, "confidence": None, "parse_status": "missing"})
        if selected and selected.get("status") in ("no_patch", "refused") and g_self.get("claim") is None:
            g_self.update({"claim": 0, "parse_status": "imputed"})
        diff = sel_v.get("diff", "")
        rec["generator"] = {**g_self, "diff_extracted": bool(diff), "patch_bytes": len(diff.encode()),
                            "refused": bool(sel_v.get("refused")), "model": selected["model"] if selected else None}
        rec["generator_initial"] = (dict(cands[0]["versions"][0].get("self") or {})
                                    if cands and cands[0].get("versions") else {})
        rec["n_rounds"] = 1 if (not cands or initial_primary == diff) else 2
        if jurors:
            if decision.get("status") == "complete":
                k = rec["selected_k"]
                last = rec["jury_rounds"][-1]["votes"]
                votes = sum(1 for v in last if (v.get("claims_k") or {}).get(k) == 1)
                n = len(last)
                confs = [(v.get("conf_k") or {}).get(k) for v in last if (v.get("conf_k") or {}).get(k) is not None]
                rec["reviewer"] = {"status": "complete", "n_judges": n, "votes": votes,
                                   "majority": int(votes * 2 > n), "unanimous": int(bool(decision["unanimous"])),
                                   "claim": int(bool(decision["unanimous"])),
                                   "judge1_claim": (last[0].get("claims_k") or {}).get(k),
                                   "confidence": sum(confs) / len(confs) if confs else None,
                                   "abstained": int(not decision["unanimous"]),
                                   "jury_rounds": len(rec["jury_rounds"])}
            else:
                why = ("no candidate passed the mechanical gate" if not live else
                       f"jury incomplete: {decision.get('parsed', 0)}/{decision.get('n_jurors', len(jurors))} parsed")
                if not live and cands and rec["generation_status"] == "complete":
                    # nothing reached the jury: the system cannot claim a repair (claim 0, not incomplete)
                    rec["reviewer"] = {"status": "complete", "n_judges": len(jurors), "votes": 0, "majority": 0,
                                       "unanimous": 0, "claim": 0, "judge1_claim": 0, "confidence": None,
                                       "abstained": 1, "imputed": why, "jury_rounds": 0}
                else:
                    rec["reviewer"] = {"status": "incomplete", "error": why}
        if rec["generation_status"] == "complete" and rec["generator"].get("claim") is None and not jurors:
            rec["generation_status"], rec["incomplete_reason"] = "incomplete", "repairer gave no parseable claim"
    # ---------------------------------------------------------------- 6. freeze
    st = [s for s in rec["stages"].values() if s.get("status") == "ok"]
    rec.update({"api_calls": len(st), "latency_ms_api_total": round(sum(s["latency_ms"] for s in st), 1),
                "http_retries": sum(max(0, len(s.get("http_attempts", [])) - 1) for s in rec["stages"].values()),
                "input_tokens_total": sum(s.get("input_tokens") or 0 for s in st),
                "output_tokens_total": sum(s.get("output_tokens") or 0 for s in st),
                "wall_time_s": round(time.perf_counter() - t0, 2), "finished_at_utc": utc_now()})
    rec["frozen_at_utc"] = utc_now()
    names = sorted(p.name for p in out_dir.iterdir() if p.is_file() and p.suffix in (".md", ".diff"))
    rec["sha256"] = {n: sha256_file(out_dir / n) for n in names}
    _write(rec_path, json.dumps(rec, indent=1, ensure_ascii=False, default=str))
    for n in names + ["llm_response.json"]:
        (out_dir / n).chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    rv = rec.get("reviewer", {})
    log(f"[frozen] {agent}/{vid}: {rec['generation_status']} cands={[c.get('status') for c in cands]} "
        f"selected={rec['selected_k']} claim_self={rec['generator'].get('claim')} "
        f"system_claim={rv.get('claim', rec['generator'].get('claim'))} rounds={len(rec['jury_rounds'])} "
        f"calls={rec['api_calls']}")
    return rec


# ============================================================================ evaluation

def eval_worker(case_dir: str, runs_root: str, label: str, tools_root: str, session: str,
                patch_src: Optional[str] = None) -> Dict[str, Any]:
    """Separate process: oracle control once per case and session, then the Vul4Py verdict."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import eval_harness
    case = Path(case_dir)
    run_dir = Path(runs_root) / label / case.name
    run_dir.mkdir(parents=True, exist_ok=True)
    if patch_src:
        shutil.copy(patch_src, run_dir / "patch.diff")
    env = eval_harness.env_check(case, Path(runs_root), Path(tools_root), session)
    if not env.get("healthy"):
        v = {"agent": label, "vuln_id": case.name, "apply_ok": False, "func_ok": False, "exploit_ok": False,
             "plausible": False, "env_check": env,
             "notes": f"environment check failed: {env.get('reason')} {env.get('error', '')}".strip()}
        (run_dir / "eval.json").write_text(json.dumps(v, indent=2))
        return v
    v = eval_harness.evaluate_patch(case, run_dir, label, Path(tools_root))
    v["env_check"] = {k: env.get(k) for k in ("healthy", "functional_unpatched", "exploit_unpatched",
                                               "functional_reference", "exploit_reference")}
    (run_dir / "eval.json").write_text(json.dumps(v, indent=2))
    return v


async def evaluate_all(ctx: Ctx, vid: str, agent: str, rec: Dict[str, Any]) -> None:
    out_dir = ctx.args.runs / agent / vid
    for name, h in rec.get("sha256", {}).items():
        if sha256_file(out_dir / name) != h:
            log(f"[!] {agent}/{vid}: {name} changed after the freeze; not evaluating")
            _write(out_dir / "eval.json", json.dumps({"agent": agent, "vuln_id": vid,
                                                      "notes": f"frozen artifact modified: {name}"}))
            return
    if rec.get("generation_status") != "complete":
        return
    jobs: List[Tuple[str, Optional[str]]] = []
    if not (out_dir / "eval.json").exists():
        jobs.append((agent, None))
    if ctx.args.eval_candidates:
        if rec.get("n_rounds", 1) > 1 and (out_dir / "patch_initial.diff").read_text().strip():
            jobs.append((f"{agent}__initial", str(out_dir / "patch_initial.diff")))
        selected = (out_dir / "patch.diff").read_text() if (out_dir / "patch.diff").exists() else None
        for c in rec.get("candidates", []):
            p = out_dir / f"cand{c['k']}_final.diff"
            if p.exists() and p.read_text() != selected:     # the selected patch is evaluated as <agent>
                jobs.append((f"{agent}__cand{c['k']}", str(p)))
    lock = ctx.eval_locks.setdefault(vid, asyncio.Lock())
    loop = asyncio.get_running_loop()
    async with lock:   # patches are applied in place: one evaluation per case at a time
        for label, src in jobs:
            if (ctx.args.runs / label / vid / "eval.json").exists():
                continue
            v = await loop.run_in_executor(ctx.pool, eval_worker, str(ctx.args.workspaces / vid),
                                           str(ctx.args.runs), label, str(ctx.args.tools_root), ctx.session, src)
            log(f"[eval] {label}/{vid}: apply={v.get('apply_ok')} func={v.get('func_pfes')} "
                f"expl={v.get('exploit_pfes')} {v.get('notes') or ''}")


# ============================================================================ main

def resolve_ids(a) -> List[str]:
    ids: List[str] = []
    if a.vuln_ids:
        ids += [s.strip() for s in a.vuln_ids.split(",") if s.strip()]
    if a.ids_file:
        ids += [ln.split("#", 1)[0].strip() for ln in Path(a.ids_file).read_text().splitlines()
                if ln.split("#", 1)[0].strip()]
    ids = list(dict.fromkeys(ids))
    if a.sample and a.sample < len(ids):
        ids = sorted(random.Random(a.seed).sample(sorted(ids), a.sample))
    return ids


PRESETS = {
    "c0": {"analyst": "none", "jurors": "none", "gate": False, "cross_exam": False, "debate_rounds": 0,
           "max_revisions": 0, "hint": "lines"},
    "c0g": {"analyst": "none", "jurors": "none", "gate": True, "cross_exam": False, "debate_rounds": 0,
            "max_revisions": 0, "hint": "lines"},
    "c1": {"gate": True, "cross_exam": True, "debate_rounds": 1, "max_revisions": 1, "hint": "lines"},
}


async def amain(a) -> int:
    overrides = json.loads(Path(a.models_file).read_text()) if a.models_file else {}
    mk = lambda s: parse_model(s, overrides, a.max_tokens)  # noqa: E731
    analyst = None if a.analyst in ("", "none") else mk(a.analyst)
    repairers = [mk(s) for s in a.repairers.split(",") if s.strip()]
    jurors = [] if a.jurors in ("", "none") else [mk(s) for s in a.jurors.split(",") if s.strip()]
    if not repairers:
        sys.exit("--repairers is required")
    own = [m.spec for m in jurors if m.spec in {r.spec for r in repairers}]
    if own:
        sys.exit(f"A repairer cannot also be a reviewer (it would judge its own patch): {own}")
    fam_r = {m.family for m in repairers}
    clash = [m.spec for m in jurors if m.family in fam_r]
    if clash and not a.allow_same_family:
        sys.exit(f"Reviewers from a repairer's family judge their own family: {clash}. Pick other families "
                 "(or pass --allow-same-family and report it).")
    ids = resolve_ids(a)
    if not ids:
        sys.exit("No cases selected: --vuln-ids or --ids-file")
    ctx = Ctx(a, {"analyst": analyst, "repairers": repairers, "jurors": jurors})
    ctx.pipeline_name = "+".join(x for x, on in (("analyst", analyst), (f"repair{len(repairers)}", True),
                                                 ("gate", a.gate), ("crossexam", a.cross_exam and len(repairers) > 1),
                                                 (f"jury{len(jurors)}", jurors),
                                                 (f"debate{a.debate_rounds}", jurors and a.debate_rounds),
                                                 (f"revise{a.max_revisions}", jurors and a.max_revisions)) if on)
    a.runs.mkdir(parents=True, exist_ok=True)
    exp = {"schema": SCHEMA, "started_at_utc": utc_now(), "condition": a.condition, "pipeline": ctx.pipeline_name,
           "models": {"analyst": analyst.spec if analyst else None, "repairers": [m.spec for m in repairers],
                      "jurors": [m.spec for m in jurors]},
           "families": {"repairers": sorted(fam_r), "jurors": sorted({m.family for m in jurors})},
           "settings": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()
                        if k not in ("func",)},
           "prompt_sha256": prompt_fingerprint(), "vul4py_commit": git_head(ROOT), "vuln_ids": ids,
           "python": platform.python_version(), "oracle_session": ctx.session}
    try:
        import openai
        exp["openai_client"] = openai.__version__
    except Exception:  # noqa: BLE001
        pass
    if getattr(a, "rag", None):
        import rag_repair
        exp["rag"] = rag_repair.describe(a.rag)      # also loads the model once, before the first case
    exp_path = a.runs / f"experiment_{a.agent}.json"
    _write(exp_path, json.dumps(exp, indent=2))
    log(f"[+] {a.agent}: {len(ids)} cases; {ctx.pipeline_name}; repairers={[m.spec for m in repairers]} "
        f"jurors={[m.spec for m in jurors]} analyst={analyst.spec if analyst else None}")
    if not a.no_eval:
        ctx.pool = ProcessPoolExecutor(max_workers=a.eval_jobs, mp_context=mp.get_context("spawn"))

    async def one(vid: str) -> None:
        try:
            rec = await run_case(ctx, vid, a.agent)
            if rec and not a.no_eval:
                await evaluate_all(ctx, vid, a.agent, rec)
        except Exception as e:  # noqa: BLE001
            import traceback
            log(f"[!] {a.agent}/{vid}: unexpected error {e!r}\n{traceback.format_exc()[-1500:]}")

    t0 = time.perf_counter()
    await asyncio.gather(*[one(v) for v in ids])
    if ctx.pool:
        ctx.pool.shutdown(wait=True)
    exp.update({"finished_at_utc": utc_now(), "wall_time_s": round(time.perf_counter() - t0, 1),
                "usage": ctx.usage})
    cost = equiv = 0.0
    for spec, u in ctx.usage.items():
        m = ctx.model_by_spec.get(spec)
        if m and m.provider == "claudecode":      # Claude plan: not billed; Claude Code reports the API equivalent
            equiv += u.get("api_equivalent_usd", 0.0)
            continue
        if m and m.price_in is not None and m.price_out is not None:
            cost += u["input_tokens"] / 1e6 * m.price_in + u["output_tokens"] / 1e6 * m.price_out
    exp["estimated_cost_usd"] = round(cost, 2) if cost else None
    exp["claude_plan_api_equivalent_usd"] = round(equiv, 2) if equiv else None
    _write(exp_path, json.dumps(exp, indent=2))
    log(f"[done] {exp['wall_time_s']}s; usage={ctx.usage}" + (f"; ~USD {cost:.2f}" if cost else "")
        + (f"; Claude plan (not billed): ~USD {equiv:.2f} at API prices" if equiv else ""))
    if not a.no_eval:
        import fa_metrics
        fa_metrics.run(a.runs, None, a.workspaces)
    return 0


async def ping(a) -> int:
    overrides = json.loads(Path(a.models_file).read_text()) if a.models_file else {}
    specs = [s.strip() for s in a.ping.split(",") if s.strip()]
    models = [parse_model(s, overrides, 512) for s in specs]
    clients = {p: make_client(p, a) for p in {m.provider for m in models}}

    async def one(m: ModelRef):
        t0 = time.perf_counter()
        kw: Dict[str, Any] = {"model": m.name, "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
                              "timeout": 180}
        # thinking models (DeepSeek, Claude 5.5) need room to think before the word
        kw["max_completion_tokens" if m.provider == "openai" else "max_tokens"] = (
            4096 if m.provider in ("anthropic", "deepseek") else 1024)
        try:
            if m.provider == "claudecode":
                r = await _cc_run(clients["claudecode"], m, "Answer in one word.", "Reply with the single word: OK", 300)
                served = ";".join(((r["json"] or {}).get("modelUsage") or {}).keys())
                if r["kind"] == "refusal":
                    note = "REFUSAL"
                elif r["kind"] == "ok":
                    note = "answer: " + r["text"].strip()[:30]
                else:
                    note = f"{r['kind']}: " + (r["text"] or r["stderr"]).strip()[:100]
                return (m.spec, 200 if r["kind"] in ("ok", "refusal") else r["kind"], time.perf_counter() - t0,
                        note + (f" [answered by {served}; {clients['claudecode']['version']}]" if served else ""))
            if m.provider == "anthropic":
                if m.reasoning_effort:
                    kw["output_config"] = {"effort": m.reasoning_effort}
                r = await clients[m.provider].messages.create(**kw)
                txt = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
                if r.stop_reason == "refusal":
                    txt = f"REFUSAL ({getattr(r.stop_details, 'category', None)})"
                return m.spec, 200, time.perf_counter() - t0, ("answer: " + txt[:30]) if txt else "EMPTY (raise max tokens)"
            if m.provider == "deepseek" and m.reasoning_effort:
                kw["reasoning_effort"] = m.reasoning_effort
            r = await clients[m.provider].chat.completions.create(**kw)
            txt = (r.choices[0].message.content or "").strip()
            return m.spec, 200, time.perf_counter() - t0, ("answer: " + txt[:30]) if txt else "EMPTY (raise max tokens)"
        except Exception as e:  # noqa: BLE001
            return m.spec, getattr(e, "status_code", type(e).__name__), time.perf_counter() - t0, str(e)[:110]

    rows = await asyncio.gather(*[one(m) for m in models])
    print(f"{'model':52s} {'status':>7s} {'s':>6s}  note")
    for spec, st_, s, note in rows:
        print(f"{spec:52s} {str(st_):>7s} {s:6.1f}  {note}")
    return 0


def add_claudecode_args(g) -> None:
    """Options of the claudecode provider (shared with judge_calibration.py)."""
    g.add_argument("--claudecode-bin", default=None,
                   help="The claude CLI (Claude Code); default: claude on PATH, else ~/.local/bin/claude")
    g.add_argument("--claudecode-rpm", type=float, default=None)
    g.add_argument("--claudecode-concurrency", type=int, default=3,
                   help="claude -p processes at once, over all Claude models (each one takes memory)")
    g.add_argument("--claudecode-limit-wait", type=float, default=330,
                   help="Minutes to wait at the Claude plan's usage limit (checked every 10 min) before stopping "
                        "the run; cases in flight are not frozen and the same command resumes")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Oracle-blind multi-model repair with debate between patches (v2).")
    sel = ap.add_argument_group("cases")
    sel.add_argument("--vuln-ids")
    sel.add_argument("--ids-file")
    sel.add_argument("--sample", type=int)
    sel.add_argument("--seed", type=int, default=42)
    m = ap.add_argument_group("models (provider:model; a bare id means nvidia)")
    m.add_argument("--preset", choices=sorted(PRESETS), help="c0 = repairer alone; c0g = + gate; c1 = full pipeline")
    m.add_argument("--analyst", default="none")
    m.add_argument("--repairers", default="", help="Comma-separated; the first is the primary repairer")
    m.add_argument("--jurors", default="none",
                   help="Comma-separated reviewers: never a repairer; other families unless --allow-same-family")
    m.add_argument("--allow-same-family", action="store_true")
    m.add_argument("--models-file", help="JSON: per-model context, max_output, reasoning_effort (OpenAI and DeepSeek "
                                         "reasoning_effort, Claude output_config.effort), price_in, price_out")
    p = ap.add_argument_group("protocols")
    p.add_argument("--gate", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--gate-retries", type=int, default=2)
    p.add_argument("--cross-exam", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--debate-rounds", type=int, default=1)
    p.add_argument("--max-revisions", type=int, default=1)
    p.add_argument("--hint", choices=["lines", "files", "none"], default="lines")
    p.add_argument("--compiled-context", action=argparse.BooleanOptionalAction, default=True,
                   help="Show C/Rust/template files the fix changed (cases fixed outside .py)")
    p.add_argument("--code-share", type=float, default=0.40, help="Share of the smallest context window for code")
    p.add_argument("--temperature", type=float, default=0.0, help="NVIDIA models only")
    p.add_argument("--max-tokens", type=int, default=16384)
    api = ap.add_argument_group("API and scheduling")
    api.add_argument("--timeout", type=float, default=900.0)
    api.add_argument("--max-http-retries", type=int, default=6)
    api.add_argument("--per-model-concurrency", type=int, default=2)
    api.add_argument("--max-active-cases", type=int, default=3)
    api.add_argument("--nvidia-rpm", type=float, default=None)
    api.add_argument("--openai-rpm", type=float, default=None)
    api.add_argument("--openai-extra", default=None,
                     help='JSON merged into every OpenAI request, e.g. \'{"service_tier": "flex"}\' (cheaper, slower)')
    api.add_argument("--nvidia-base-url", default=None)
    api.add_argument("--openai-base-url", default=None)
    api.add_argument("--anthropic-rpm", type=float, default=None)
    api.add_argument("--deepseek-rpm", type=float, default=None)
    api.add_argument("--anthropic-base-url", default=None)
    api.add_argument("--deepseek-base-url", default=None)
    add_claudecode_args(api)
    api.add_argument("--eval-jobs", type=int, default=1)
    api.add_argument("--session", default=None,
                     help="Oracle-control session. Runs that share --runs and --session (e.g. C1, C0 and C0g) check "
                          "each case's oracle once and reuse it, so every condition is judged against the same "
                          "control; default: a new control in every invocation")
    api.add_argument("--no-eval", action="store_true")
    api.add_argument("--eval-candidates", action=argparse.BooleanOptionalAction, default=True,
                     help="Also evaluate every final candidate and the primary repairer's first patch")
    io = ap.add_argument_group("paths")
    io.add_argument("--runs", type=Path, default=ROOT / "runs" / "final")
    io.add_argument("--agent", default="c1")
    io.add_argument("--condition", default="")
    io.add_argument("--workspaces", type=Path, default=ROOT / "workspaces")
    io.add_argument("--tools-root", type=Path)
    io.add_argument("--rag", type=Path, default=None,
                    help="RAG-R base built by scripts/rag_repair.py (decisiones_v5): fixes retrieved from other "
                         "repositories go between the hint and the source files of the repairer prompt; without "
                         "it the prompt is unchanged")
    ap.add_argument("--ping", default="", help="Comma-separated provider:model list: one tiny request each")
    return ap


def main() -> int:
    ap = build_parser()
    a = ap.parse_args()
    if a.preset:
        for k, v in PRESETS[a.preset].items():
            if ap.get_default(k) == getattr(a, k):     # explicit flags win over the preset
                setattr(a, k, v)
        a.condition = a.condition or a.preset
    a.runs, a.workspaces = a.runs.resolve(), a.workspaces.resolve()
    a.tools_root = (a.tools_root or a.workspaces / ".vul4py_tools").resolve()
    a.rag = a.rag.resolve() if a.rag else None
    if a.ping:
        return asyncio.run(ping(a))
    return asyncio.run(amain(a))


if __name__ == "__main__":
    sys.exit(main())
