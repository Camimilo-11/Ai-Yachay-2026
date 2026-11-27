#!/usr/bin/env python3
"""rag_cwe.py -- RAG-R keyed by the case's own weakness (v5.1, prereg/decisiones_v5_1.txt).

v5 (rag_repair.lookup) retrieved the 3 fixes of other repositories whose code most resembled the hinted
code, whatever their weakness: only 28 of the 285 examples shared a CWE with their case, 76 of the 95
cases got no example of their own weakness, and the MITRE mitigations shown were those of the examples.
Here the case's CWE ids (from its advisory: cwe_map.json of the same base, built before v5) decide what is
retrieved:

- examples: fixes of OTHER repositories with at least one of the case's CWE ids, ranked by the same code
  similarity (same base, embedder, query and leave-one-repository-out filter as v5), the best chunk per
  source case, at most 2 cases;
- guide: MITRE's name and mitigations of the case's own CWE ids (at most 2), placed first;
- a case with a CWE but no such example gets the guide only; a case without a CWE gets no section.

The section tells the model the weakness class of the case (from its advisory), which v5 did not. It says
nothing about the case's own fix: same leakage audit as v5 (difflib ratio between each example and the
case's official fix; 0.5 or more flags the case).
"""
from __future__ import annotations

import difflib
import hashlib
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag_repair as R  # noqa: E402

MODE = "cwe"
VERSION = "rag_cwe/1"
TOP_K = 2
MAX_CWE = 2
CANDIDATES = 40
BUDGET_TOKENS = R.BUDGET_TOKENS

INTRO = ("Weakness type of this case, from its public advisory: {cwes}. Below are MITRE's mitigations for it "
         "and, when the base has them, fixes of the SAME weakness type in OTHER projects, retrieved "
         "automatically because their code resembles the hinted code. They show how this kind of flaw is "
         "usually fixed; the localization hint shows where the flaw is in these files. They are not evidence "
         "about these files: back every statement with the files below.\n\n")
GUIDE_HEAD = "Mitigations that MITRE's CWE list gives for this weakness:\n"
NO_EXAMPLES = "(The base has no fix of this weakness type from another project.)\n\n"


def texts_sha256() -> str:
    return hashlib.sha256("\n\x00\n".join([INTRO, GUIDE_HEAD, NO_EXAMPLES]).encode()).hexdigest()


def params() -> Dict[str, Any]:
    return {"mode": MODE, "version": VERSION, "top_k": TOP_K, "max_cwe": MAX_CWE, "candidates": CANDIDATES,
            "budget_tokens": BUDGET_TOKENS, "chars_per_token": R.CHARS_PER_TOKEN, "guide_chars": R.GUIDE_CHARS,
            "filter": "repo != case repo AND chunk cwe shares a CWE with the case", "texts_sha256": texts_sha256()}


def describe(kb: Path) -> Dict[str, Any]:
    d = R.describe(kb)
    d["lookup"] = params()
    return d


def case_cwes(kb: Path, vid: str) -> List[str]:
    import json
    cm = json.loads((Path(kb) / "cwe_map.json").read_text())
    return [c for c in (cm.get(vid) or {}).get("cwe", []) if c not in R.IGNORED_CWE]


def render(cwes: List[str], hits: List[Dict[str, Any]], guides: Dict[str, Any]) -> Tuple[str, List[str]]:
    chosen = [c for c in cwes if R.usable_guide(guides.get(c))][:MAX_CWE]
    names = ", ".join(f"{c} ({guides[c].get('name')})" if R.usable_guide(guides.get(c)) and guides[c].get("name")
                      else c for c in cwes[:MAX_CWE])
    intro = INTRO.format(cwes=names)
    guide_txt = (GUIDE_HEAD + "\n".join(R._guide_line(c, guides[c]) for c in chosen) + "\n\n") if chosen else ""
    if not hits:
        return intro + guide_txt + NO_EXAMPLES, chosen
    heads = [f"[R{i + 1}] {h['file']}" + (f" (weakness: {', '.join(h['cwe'])})" if h.get("cwe") else "")
             for i, h in enumerate(hits)]
    fixed = len(intro) + len(guide_txt) + sum(len(x) + len("\n```diff\n\n```\n\n") for x in heads)
    room = BUDGET_TOKENS * R.CHARS_PER_TOKEN - fixed
    per = max(400, room // max(1, len(hits)))
    body = "".join(f"{hd}\n```diff\n{R._cut(h['diff'], per)}\n```\n\n" for hd, h in zip(heads, hits))
    return intro + guide_txt + body, chosen


def lookup(kb, case_dir, meta: Dict[str, Any], hint: str) -> Tuple[str, Dict[str, Any]]:
    """Section for the repairer prompt (empty for a case without CWE) and the record frozen with the case."""
    from qdrant_client import models
    t0 = time.perf_counter()
    kb, case = Path(kb), Path(case_dir)
    st = R._open(kb)
    vid, repo = case.name, R.norm_repo(meta.get("repo_url", ""))
    cwes = case_cwes(kb, vid)
    rec: Dict[str, Any] = {"kb": R.KB_VERSION, "lookup": VERSION, "mode": MODE,
                           "manifest_sha256": st["manifest_sha256"], "embed_model": st["manifest"]["embed_model"],
                           "repo_filtered": repo, "case_cwe": cwes}
    if not cwes:
        rec.update({"hits": [], "cwe_guides": [], "section_chars": 0, "section_tokens_est": 0,
                    "section_sha256": R.sha256_bytes(b""), "leak_audit": [], "leak_flag": False,
                    "note": "the case has no CWE: no section", "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)})
        return "", rec
    q, rngs = R.query_text(case, hint)
    if not q.strip():
        raise RuntimeError("no hinted code to search with (the RAG needs --hint lines)")
    flt = models.Filter(
        must=[models.FieldCondition(key="cwe", match=models.MatchAny(any=cwes))],
        must_not=[models.FieldCondition(key="repo", match=models.MatchValue(value=repo)),
                  models.FieldCondition(key="case", match=models.MatchValue(value=vid))])
    with R._LOCK:
        qv = st["embedder"].embed([q])[0]
        pts = st["client"].query_points(R.COLLECTION, query=qv, limit=CANDIDATES, query_filter=flt,
                                        with_payload=True).points
    hits, seen = [], set()
    for p in pts:
        pl = dict(p.payload)
        if pl["repo"] == repo or pl["case"] == vid:                # defensive: the filter already drops them
            raise RuntimeError(f"leave-one-repository-out filter failed for {vid}")
        if not set(pl.get("cwe") or []) & set(cwes):
            raise RuntimeError(f"CWE filter failed for {vid}")
        if pl["case"] in seen:
            continue
        seen.add(pl["case"])
        hits.append({**pl, "score": round(float(p.score), 4)})
        if len(hits) == TOP_K:
            break
    section, chosen = render(cwes, hits, st["guides"])
    try:
        _, own = R.case_hunks(case)
    except Exception:  # noqa: BLE001
        own = None
    own_lines = own.splitlines() if own else []
    audit = [{"case": h["case"], "ratio": round(difflib.SequenceMatcher(None, own_lines, h.get("changed") or []).ratio(), 3)}
             for h in hits] if own_lines else []
    rec.update({"query_ranges": {k: [list(r) for r in v] for k, v in rngs.items()}, "query_chars": len(q),
                "hits": [{k: h.get(k) for k in ("case", "repo", "file", "hunk", "old_start", "cwe", "score")} for h in hits],
                "cwe_guides": chosen, "section_chars": len(section),
                "section_tokens_est": round(len(section) / R.CHARS_PER_TOKEN),
                "section_sha256": R.sha256_bytes(section.encode()), "leak_audit": audit,
                "leak_flag": any(a["ratio"] >= R.LEAK_FLAG for a in audit),
                "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)})
    return section, rec
