#!/usr/bin/env python3
"""rag_repair.py -- RAG-R v1 (decisiones_v5): reference fixes from OTHER projects for the repairer.

The base holds the official Vul4Py fixes (code files only, never tests or docs), one chunk per hunk:
the vulnerable code around the hunk and the hunk itself, with the case, its repository and its CWE ids.
For a case, the query is the vulnerable code around the localization hint the model already sees (no
information about the case's own fix), the search drops every chunk from the case's repository
(leave-one-repository-out), keeps the best chunk per source case and renders the top 3 with the MITRE
CWE mitigations of their weaknesses as a section of at most about 3000 tokens.

Vector store: Qdrant in local mode (qdrant-client, files under <kb>/qdrant; nothing leaves the machine).
Embeddings: FastEmbed jinaai/jina-embeddings-v2-base-code on CPU (model files under <kb>/models).

  python scripts/rag_repair.py fetch-cwe   --ids-file dataset/ok.txt --kb runs/v5/kb_rag_r_v1      (network: OSV)
  python scripts/rag_repair.py fetch-guides --kb runs/v5/kb_rag_r_v1                               (network: MITRE)
  python scripts/rag_repair.py build       --ids-file dataset/ok.txt --workspaces workspaces --kb runs/v5/kb_rag_r_v1
  python scripts/rag_repair.py check       --kb runs/v5/kb_rag_r_v1
  python scripts/rag_repair.py query       --kb runs/v5/kb_rag_r_v1 --workspaces workspaces --vid CVE-2024-52804

multiagent.py --rag <kb> calls lookup() for every case and puts the section between the hint and the
source files of the repairer prompt; without --rag nothing changes.
"""
from __future__ import annotations

import argparse
import atexit
import difflib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

KB_VERSION = "rag_r_v1"
COLLECTION = "rag_r_v1"
EMBED_MODEL = "jinaai/jina-embeddings-v2-base-code"
TEST_EMBEDDER = "test:hash256"          # tests only: a bag-of-identifiers hash, never for a real run
PRE_CONTEXT = 10                         # lines of vulnerable code kept around each changed line of a fix
PRE_MAX_LINES = 80
QUERY_CONTEXT = 20                       # lines around each hinted range in the query
# What goes into the embedding model. Attention memory grows with the square of the text length, and a
# batch is padded to its longest text: one pathological chunk (very long lines) padded a batch of 8 to the
# model's 8192 tokens and asked for 24 GB on the instance. Lines are clipped, texts capped, batches small.
LINE_MAX_CHARS = 240
EMBED_MAX_CHARS = 2400                   # a chunk (about 800 tokens of code)
QUERY_MAX_CHARS = 4000                   # the query (about 1300 tokens of code)
EMBED_BATCH = 2
TOP_K = 3                                # source cases shown
CANDIDATES = 40                          # nearest chunks fetched before keeping the best one per source case
MAX_CWE = 2
BUDGET_TOKENS = 3000
CHARS_PER_TOKEN = 4                      # budget estimate (code and English average about 4 characters a token)
GUIDE_CHARS = 1600                       # about 400 tokens per CWE
DIFF_STORE_CHARS = 6000
LEAK_FLAG = 0.5
IGNORED_CWE = {"NVD-CWE-noinfo", "NVD-CWE-Other"}
OSV = "https://api.osv.dev/v1/vulns/"
GH_ADVISORIES = "https://api.github.com/advisories?cve_id="
CWE_XML_ZIP = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"

INTRO = ("Reference fixes from OTHER projects, retrieved automatically because their code resembles the "
         "hinted code. They may not apply to this project and they are not evidence about these files: take "
         "them only as ideas, and back every statement with the files below.\n\n")
GUIDE_HEAD = "Mitigations that MITRE's CWE list gives for these weaknesses:\n"
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HINT_RE = re.compile(r"^- (\S+): lines (.+)$", re.M)


# ----------------------------------------------------------------------------- helpers

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def norm_repo(url: str) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"/+$", "", u)
    return re.sub(r"\.git$", "", u)


def _git(repo: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    return cp.stdout.decode("utf-8", "replace") if cp.returncode == 0 else ""


def file_at_head(checkout: Path, rel: str) -> Optional[List[str]]:
    """The committed file (git show HEAD:rel), so in-place patches or build products never leak in."""
    cp = subprocess.run(["git", "-C", str(checkout), "show", f"HEAD:{rel}"], capture_output=True)
    if cp.returncode != 0:
        return None
    return cp.stdout.decode("utf-8", "replace").splitlines()


def hint_ranges(hint: str) -> Dict[str, List[Tuple[int, int]]]:
    """Same parser as multiagent.hint_ranges_of: '- path: lines 3-7, 12' -> {path: [(3, 7), (12, 12)]}."""
    out: Dict[str, List[Tuple[int, int]]] = {}
    for m in HINT_RE.finditer(hint or ""):
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


def clip_lines(lines: Sequence[str]) -> List[str]:
    return [x if len(x) <= LINE_MAX_CHARS else x[:LINE_MAX_CHARS] + " ..." for x in lines]


def embed_text(rel: str, code: str) -> str:
    return (f"# {rel}\n" + "\n".join(clip_lines(code.splitlines())))[:EMBED_MAX_CHARS]


def changed_lines(diff: str) -> List[str]:
    return [ln[1:].strip() for ln in diff.splitlines()
            if ln[:1] in "+-" and not ln.startswith(("+++", "---")) and ln[1:].strip()]


def split_hunks(file_diff: str) -> List[Dict[str, Any]]:
    hunks, cur = [], None
    for ln in file_diff.splitlines():
        m = HUNK_RE.match(ln)
        if m:
            if cur:
                hunks.append(cur)
            cur = {"old_start": int(m.group(1)), "old_count": int(m.group(2) if m.group(2) is not None else 1),
                   "lines": [ln]}
        elif cur is not None:
            cur["lines"].append(ln)
    if cur:
        hunks.append(cur)
    for h in hunks:
        h["text"] = "\n".join(h.pop("lines"))
    return hunks


# ----------------------------------------------------------------------------- corpus

def case_hunks(case: Path) -> Tuple[List[Dict[str, Any]], str]:
    """Chunks of one case's official fix (non-test, non-doc code files the fix added, changed or deleted;
    the same files the oracle control uses), and the case's own changed lines for the leakage audit."""
    import eval_harness   # the oracle's definition of the fix's code files
    vref, fref = eval_harness.checkout_refs(case)
    rels = eval_harness.code_files_changed(case)
    chunks, own = [], []
    for rel in rels:
        d = _git(case / "fixed", "diff", "--no-renames", "--no-color", "-U3", vref, fref, "--", rel)
        if not d.strip():
            continue
        own.extend(changed_lines(d))
        pre_file = file_at_head(case / "vulnerable", rel)
        for i, h in enumerate(split_hunks(d)):
            if not pre_file or h["old_count"] == 0 and h["old_start"] == 0:
                continue        # a file the fix added: no vulnerable code to match
            ext = max(0, PRE_CONTEXT - 3)          # -U3 already holds 3 lines of context on each side
            lo = max(1, h["old_start"] - ext)
            hi = min(len(pre_file), h["old_start"] + max(h["old_count"], 1) - 1 + ext)
            pre = pre_file[lo - 1:hi][:PRE_MAX_LINES]
            if not any(x.strip() for x in pre):
                continue
            chunks.append({"file": rel, "hunk": i, "old_start": h["old_start"], "pre_start": lo,
                           "pre": "\n".join(pre), "diff": h["text"][:DIFF_STORE_CHARS],
                           "changed": changed_lines(h["text"])})
    return chunks, "\n".join(own)


def query_text(case: Path, hint: str) -> Tuple[str, Dict[str, List[Tuple[int, int]]]]:
    rngs = hint_ranges(hint)
    parts = []
    for rel, rr in rngs.items():
        lines = file_at_head(case / "vulnerable", rel)
        if not lines:
            continue
        wins = []
        for a, b in rr:
            lo, hi = max(1, a - QUERY_CONTEXT), min(len(lines), b + QUERY_CONTEXT)
            wins.append("\n".join(clip_lines(lines[lo - 1:hi])))
        parts.append(f"# {rel}\n" + "\n...\n".join(wins))
    return "\n\n".join(parts)[:QUERY_MAX_CHARS], rngs


# ----------------------------------------------------------------------------- embeddings and store

def _hash_vec(text: str, dim: int = 256) -> List[float]:
    v = [0.0] * dim
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower()):
        v[int(hashlib.sha1(tok.encode()).hexdigest()[:8], 16) % dim] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


class Embedder:
    def __init__(self, name: str, cache_dir: Path):
        self.name = name
        if name == TEST_EMBEDDER:
            self._m, self.dim = None, 256
            return
        from fastembed import TextEmbedding
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._m = TextEmbedding(name, cache_dir=str(cache_dir))
        self.dim = len(next(iter(self._m.embed(["def f(): pass"]))))

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if self._m is None:
            return [_hash_vec(t) for t in texts]
        return [[float(x) for x in v] for v in self._m.embed(list(texts), batch_size=EMBED_BATCH)]


def _client(kb: Path):
    from qdrant_client import QdrantClient
    return QdrantClient(path=str(kb / "qdrant"))


def _versions() -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for mod in ("qdrant_client", "fastembed", "onnxruntime"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception:  # noqa: BLE001
            out[mod] = None
    return out


def _tree_sha(d: Path) -> Optional[str]:
    if not d.exists():
        return None
    h = hashlib.sha256()
    for p in sorted(x for x in d.rglob("*") if x.is_file() and not x.name.endswith(".lock")):
        h.update(str(p.relative_to(d)).encode() + b"\0" + sha256_file(p).encode() + b"\n")
    return h.hexdigest()


# ----------------------------------------------------------------------------- CWE data (network)

def _get_json(url: str, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "vul4py-rag-r/1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def cwes_for(vid: str, get=_get_json) -> Tuple[List[str], str]:
    """CWE ids of a Vul4Py case: OSV's record, then its GHSA aliases, then GitHub's advisory API for a CVE."""
    seen: List[str] = []

    def take(xs):
        for x in xs or []:
            if x and x not in seen and x not in IGNORED_CWE:
                seen.append(x)

    src = ""
    try:
        d = get(OSV + vid)
        take((d.get("database_specific") or {}).get("cwe_ids"))
        if seen:
            src = "osv"
        for al in [a for a in (d.get("aliases") or []) if a.startswith("GHSA-")]:
            if seen:
                break
            try:
                take((get(OSV + al).get("database_specific") or {}).get("cwe_ids"))
                src = "osv:" + al if seen else src
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    if not seen and vid.startswith("CVE-"):
        try:
            for adv in get(GH_ADVISORIES + vid) or []:
                take([c.get("cwe_id") for c in adv.get("cwes") or []])
            src = "github" if seen else src
        except Exception:  # noqa: BLE001
            pass
    return seen, src or "none"


def _txt(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def parse_cwe_xml(xml_bytes: bytes, wanted: Sequence[str]) -> Tuple[Dict[str, Dict[str, Any]], str]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_bytes)

    def local(t):
        return t.rsplit("}", 1)[-1]

    want = {w.replace("CWE-", "") for w in wanted}
    out: Dict[str, Dict[str, Any]] = {}
    for el in root.iter():
        kind = local(el.tag)
        if kind not in ("Weakness", "Category") or el.get("ID") not in want:
            continue
        mits = []
        for m in el.iter():
            if local(m.tag) != "Mitigation":
                continue
            phases = [_txt(p) for p in m if local(p.tag) == "Phase"]
            desc = next((_txt(p) for p in m if local(p.tag) == "Description"), "")
            if desc:
                mits.append({"phases": phases, "text": desc})
        mits.sort(key=lambda x: (0 if "Implementation" in x["phases"] else 1 if "Architecture and Design" in x["phases"] else 2))
        summary = next((_txt(c) for c in el if local(c.tag) in ("Description", "Summary")), "")
        out["CWE-" + el.get("ID")] = {"name": el.get("Name"), "kind": kind, "status": el.get("Status"),
                                     "summary": summary,
                                     "mitigations": [m["text"] for m in mits[:3]]}
    return out, root.get("Version") or ""


# ----------------------------------------------------------------------------- build

def build(workspaces: Path, ids: Sequence[str], kb: Path, model: str) -> Dict[str, Any]:
    from qdrant_client import models
    kb.mkdir(parents=True, exist_ok=True)
    cwe_map = json.loads((kb / "cwe_map.json").read_text()) if (kb / "cwe_map.json").exists() else {}
    chunks: List[Dict[str, Any]] = []
    skipped = {}
    for vid in ids:
        case = workspaces / vid
        if not (case / "fixed").is_dir() or not (case / "vulnerable").is_dir() or not (case / "meta.json").exists():
            skipped[vid] = "no workspace"
            continue
        meta = json.loads((case / "meta.json").read_text())
        hs, _ = case_hunks(case)
        if not hs:
            skipped[vid] = "no code hunk with vulnerable lines"
        for h in hs:
            chunks.append({"id": len(chunks), "case": vid, "repo": norm_repo(meta.get("repo_url", "")),
                           "cwe": (cwe_map.get(vid) or {}).get("cwe", []), **h})
    emb = Embedder(model, kb / "models")
    vecs = emb.embed([embed_text(c["file"], c["pre"]) for c in chunks])
    client = _client(kb)
    try:
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)
        client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=emb.dim,
                                                                                distance=models.Distance.COSINE))
        for i in range(0, len(chunks), 64):
            client.upsert(COLLECTION, points=[models.PointStruct(id=c["id"], vector=v, payload=c)
                                              for c, v in zip(chunks[i:i + 64], vecs[i:i + 64])])
        n_points = client.count(COLLECTION, exact=True).count
    finally:
        client.close()
    with open(kb / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n")
    vec_sha = sha256_bytes(json.dumps([[round(x, 5) for x in v] for v in vecs]).encode())
    guides = kb / "cwe_guides.json"
    man = {"kb": KB_VERSION, "collection": COLLECTION, "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "embed_model": model, "dim": emb.dim, "versions": _versions(), "n_chunks": len(chunks), "n_points": n_points,
           "n_cases": len({c["case"] for c in chunks}), "skipped": skipped,
           "chunks_sha256": sha256_file(kb / "chunks.jsonl"), "vectors_sha256": vec_sha,
           "model_files_sha256": _tree_sha(kb / "models") if model != TEST_EMBEDDER else None,
           "cwe_map_sha256": sha256_file(kb / "cwe_map.json") if (kb / "cwe_map.json").exists() else None,
           "cwe_guides_sha256": sha256_file(guides) if guides.exists() else None,
           "params": {"pre_context": PRE_CONTEXT, "query_context": QUERY_CONTEXT, "line_max_chars": LINE_MAX_CHARS,
                      "embed_max_chars": EMBED_MAX_CHARS, "query_max_chars": QUERY_MAX_CHARS,
                      "embed_batch": EMBED_BATCH, "top_k": TOP_K,
                      "candidates": CANDIDATES, "max_cwe": MAX_CWE, "budget_tokens": BUDGET_TOKENS,
                      "chars_per_token": CHARS_PER_TOKEN, "guide_chars": GUIDE_CHARS, "filter": "repo != case repo"}}
    (kb / "manifest.json").write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return man


# ----------------------------------------------------------------------------- lookup (used by multiagent)

_CACHE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _close_all() -> None:
    """Close the local Qdrant clients before the interpreter tears down (their own __del__ fails then)."""
    for st in list(_CACHE.values()):
        try:
            st["client"].close()
        except Exception:  # noqa: BLE001
            pass
    _CACHE.clear()


atexit.register(_close_all)


def _open(kb: Path) -> Dict[str, Any]:
    key = str(kb.resolve())
    with _LOCK:
        if key not in _CACHE:
            man = json.loads((kb / "manifest.json").read_text())
            if man.get("kb") != KB_VERSION:
                raise RuntimeError(f"{kb} is {man.get('kb')}, not {KB_VERSION}")
            guides = json.loads((kb / "cwe_guides.json").read_text()) if (kb / "cwe_guides.json").exists() else {}
            g = guides.get("cwe", guides)
            _CACHE[key] = {"manifest": man, "manifest_sha256": sha256_file(kb / "manifest.json"),
                           "guides": g, "embedder": Embedder(man["embed_model"], kb / "models"),
                           "client": _client(kb)}
        return _CACHE[key]


def describe(kb: Path) -> Dict[str, Any]:
    st = _open(Path(kb))
    m = st["manifest"]
    return {"kb": m["kb"], "dir": str(kb), "manifest_sha256": st["manifest_sha256"], "embed_model": m["embed_model"],
            "n_chunks": m["n_chunks"], "chunks_sha256": m["chunks_sha256"], "params": m["params"]}


def usable_guide(g: Optional[Dict[str, Any]]) -> bool:
    """A deprecated CWE entry (MITRE keeps its id, renames it 'DEPRECATED: ...' and gives no mitigations,
    e.g. CWE-613) says nothing useful, so it never fills one of the guide slots."""
    if not g:
        return False
    return not ((g.get("name") or "").strip().upper().startswith("DEPRECATED") or g.get("status") == "Deprecated")


def _guide_line(cid: str, g: Dict[str, Any]) -> str:
    body = "; ".join(g.get("mitigations") or []) or g.get("summary") or ""
    line = f"- {cid} {g.get('name') or ''}: {body}"
    return line if len(line) <= GUIDE_CHARS else line[:GUIDE_CHARS - 16].rsplit(" ", 1)[0] + " ... (truncated)"


def _cut(text: str, n: int) -> str:
    text = "\n".join(clip_lines(text.splitlines()))
    if len(text) <= n:
        return text
    keep = text[:max(0, n - 16)].rsplit("\n", 1)[0]
    return keep + "\n... (truncated)"


def render(hits: List[Dict[str, Any]], guides: Dict[str, Any]) -> Tuple[str, List[str]]:
    counts: Dict[str, Tuple[int, int]] = {}
    for rank, h in enumerate(hits):
        for c in h.get("cwe") or []:
            n, r = counts.get(c, (0, rank))
            counts[c] = (n + 1, min(r, rank))
    chosen = [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[0]))
              if usable_guide(guides.get(c))][:MAX_CWE]
    guide_txt = (GUIDE_HEAD + "\n".join(_guide_line(c, guides[c]) for c in chosen) + "\n\n") if chosen else ""
    heads = [f"[R{i + 1}] {h['file']}" + (f" (weakness: {', '.join(h['cwe'])})" if h.get("cwe") else "")
             for i, h in enumerate(hits)]
    fixed = len(INTRO) + len(guide_txt) + sum(len(x) + len("\n```diff\n\n```\n\n") for x in heads)
    room = BUDGET_TOKENS * CHARS_PER_TOKEN - fixed
    per = max(400, room // max(1, len(hits)))
    body = "".join(f"{hd}\n```diff\n{_cut(h['diff'], per)}\n```\n\n" for hd, h in zip(heads, hits))
    return INTRO + body + guide_txt, chosen


def lookup(kb, case_dir, meta: Dict[str, Any], hint: str) -> Tuple[str, Dict[str, Any]]:
    """Section for the repairer prompt (ends with a blank line) and the record frozen with the case."""
    from qdrant_client import models
    t0 = time.perf_counter()
    kb, case = Path(kb), Path(case_dir)
    st = _open(kb)
    vid, repo = case.name, norm_repo(meta.get("repo_url", ""))
    q, rngs = query_text(case, hint)
    if not q.strip():
        raise RuntimeError("no hinted code to search with (the RAG needs --hint lines)")
    flt = models.Filter(must_not=[models.FieldCondition(key="repo", match=models.MatchValue(value=repo)),
                                  models.FieldCondition(key="case", match=models.MatchValue(value=vid))])
    with _LOCK:
        qv = st["embedder"].embed([q])[0]
        pts = st["client"].query_points(COLLECTION, query=qv, limit=CANDIDATES, query_filter=flt,
                                        with_payload=True).points
    hits, cases = [], set()
    for p in pts:
        pl = dict(p.payload)
        if pl["repo"] == repo or pl["case"] == vid:           # defensive: the filter already drops them
            raise RuntimeError(f"leave-one-repository-out filter failed for {vid}")
        if pl["case"] in cases:
            continue
        cases.add(pl["case"])
        hits.append({**pl, "score": round(float(p.score), 4)})
        if len(hits) == TOP_K:
            break
    section, chosen = render(hits, st["guides"])
    try:
        _, own = case_hunks(case)
    except Exception:  # noqa: BLE001
        own = None
    own_lines = own.splitlines() if own else []
    audit = [{"case": h["case"], "ratio": round(difflib.SequenceMatcher(None, own_lines, h.get("changed") or []).ratio(), 3)}
             for h in hits] if own_lines else []
    rec = {"kb": KB_VERSION, "manifest_sha256": st["manifest_sha256"], "embed_model": st["manifest"]["embed_model"],
           "repo_filtered": repo, "query_ranges": {k: [list(r) for r in v] for k, v in rngs.items()},
           "query_chars": len(q),
           "hits": [{k: h.get(k) for k in ("case", "repo", "file", "hunk", "old_start", "cwe", "score")} for h in hits],
           "cwe_guides": chosen, "section_chars": len(section),
           "section_tokens_est": round(len(section) / CHARS_PER_TOKEN),
           "section_sha256": sha256_bytes(section.encode()), "leak_audit": audit,
           "leak_flag": any(a["ratio"] >= LEAK_FLAG for a in audit),
           "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)}
    return section, rec


# ----------------------------------------------------------------------------- CLI

def _ids(path: Path) -> List[str]:
    return [x for x in path.read_text().split() if x and not x.startswith("#")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("fetch-cwe", help="CWE ids per case from OSV (network)")
    s.add_argument("--ids-file", type=Path, required=True)
    s.add_argument("--kb", type=Path, required=True)
    s = sub.add_parser("fetch-guides", help="MITRE CWE names and mitigations for the CWEs in cwe_map.json (network)")
    s.add_argument("--kb", type=Path, required=True)
    s.add_argument("--xml-zip", type=Path, help="a local cwec_*.xml.zip instead of downloading it")
    s = sub.add_parser("build", help="chunks, embeddings and the Qdrant collection")
    s.add_argument("--ids-file", type=Path, required=True)
    s.add_argument("--workspaces", type=Path, default=Path("workspaces"))
    s.add_argument("--kb", type=Path, required=True)
    s.add_argument("--embed-model", default=EMBED_MODEL)
    s = sub.add_parser("check", help="load the model and the collection, embed one query")
    s.add_argument("--kb", type=Path, required=True)
    s = sub.add_parser("query", help="show the section one case would get (diagnostic)")
    s.add_argument("--kb", type=Path, required=True)
    s.add_argument("--workspaces", type=Path, default=Path("workspaces"))
    s.add_argument("--vid", required=True)
    s.add_argument("--hint", help="hint text as in llm_response.json (default: computed from the fix)")
    a = ap.parse_args(argv)

    if a.cmd == "fetch-cwe":
        a.kb.mkdir(parents=True, exist_ok=True)
        out = {}
        for i, vid in enumerate(_ids(a.ids_file)):
            cwe, src = cwes_for(vid)
            out[vid] = {"cwe": cwe, "source": src}
            print(f"[{i + 1}] {vid}: {', '.join(cwe) or '-'} ({src})", flush=True)
            time.sleep(0.2)
        (a.kb / "cwe_map.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        n = sum(1 for v in out.values() if v["cwe"])
        print(f"[+] {n}/{len(out)} cases with a CWE -> {a.kb / 'cwe_map.json'}")
        return 0
    if a.cmd == "fetch-guides":
        cm = json.loads((a.kb / "cwe_map.json").read_text())
        wanted = sorted({c for v in cm.values() for c in v["cwe"]})
        raw = a.xml_zip.read_bytes() if a.xml_zip else urllib.request.urlopen(
            urllib.request.Request(CWE_XML_ZIP, headers={"User-Agent": "vul4py-rag-r/1"}), timeout=120).read()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name = next(n for n in z.namelist() if n.endswith(".xml"))
            guides, ver = parse_cwe_xml(z.read(name), wanted)
        doc = {"cwe_list_version": ver, "source": name, "zip_sha256": sha256_bytes(raw), "cwe": guides,
               "missing": [w for w in wanted if w not in guides]}
        (a.kb / "cwe_guides.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        print(f"[+] CWE list {ver}: {len(guides)}/{len(wanted)} weaknesses -> {a.kb / 'cwe_guides.json'}"
              + (f"; missing {doc['missing']}" if doc["missing"] else ""))
        return 0
    if a.cmd == "build":
        man = build(a.workspaces, _ids(a.ids_file), a.kb, a.embed_model)
        print(json.dumps({k: man[k] for k in ("kb", "embed_model", "dim", "n_chunks", "n_points", "n_cases",
                                               "skipped", "chunks_sha256", "vectors_sha256")}, indent=1))
        print(f"[+] manifest sha256 {sha256_file(a.kb / 'manifest.json')}")
        return 0
    if a.cmd == "check":
        st = _open(a.kb)
        n = st["client"].count(COLLECTION, exact=True).count
        v = st["embedder"].embed(["def parse(q):\n    return yaml.load(q)"])[0]
        print(f"[+] {st['manifest']['kb']}: {n} points, model {st['manifest']['embed_model']} (dim {len(v)}), "
              f"manifest sha256 {st['manifest_sha256']}, CWE guides {len(st['guides'])}")
        return 0 if n == st["manifest"]["n_chunks"] else 1
    if a.cmd == "query":
        case = a.workspaces / a.vid
        meta = json.loads((case / "meta.json").read_text())
        hint = a.hint
        if hint is None:
            import eval_harness
            import protocols
            hint = protocols.localization_hint(case, meta, eval_harness.code_files_changed(case, include_deleted=False))
        section, rec = lookup(a.kb, case, meta, hint)
        print(section)
        print(json.dumps(rec, indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
