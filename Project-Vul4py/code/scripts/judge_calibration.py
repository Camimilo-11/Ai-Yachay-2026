#!/usr/bin/env python3
"""
judge_calibration.py (v2) -- how well each candidate REVIEWER model separates good patches from bad
ones, in the same listwise format the jury uses, on pilot cases outside the main sample.

Per case, one list of candidates with known truth (no Vul4Py run at judging time):
    reference  (V = 1)  the upstream fix (eval_harness.reference_diff)
    wrong      (V = 0)  real model patches that Vul4Py did NOT verify (--negatives-from runs/<dir>/<agent>,
                        read from their eval.json): the realistic, plausible-looking negatives
    decoy      (V = 0)  a patch that compiles and changes nothing relevant (easy negative)
    right      (V = 1)  with --with-right: real model patches from the same dirs that Vul4Py DID verify,
                        the realistic positives (the jury in C1 judges model patches, not upstream fixes)
Patches that did not apply (eval.json apply_ok false) are left out: the prompt would tell the reviewer
"applies=yes" about them, and in the pipeline the mechanical gate rejects them before any reviewer.
The order is shuffled per model and case (position bias). Output per model: sensitivity (accepts
the reference), specificity (rejects wrong/decoy), specificity on real wrong patches only, AUROC of
its confidence, Brier score, and how often its "best" is the reference; with --with-right also the
sensitivity on real right patches and the AUROC on real patches only (right vs wrong).

Caveats: reference fixes may be memorised from public repositories, and decoys are easy, so these
numbers are an upper bound on real-world reviewing; always include --negatives-from.

--export-prompts DIR writes the exact system and user prompts each model would get (same shuffle) and
DIR/truth.csv, without calling any API: to run the same review in Claude Code or Codex with a
subscription and compare it with the API.

Usage:
    read -rs OPENAI_API_KEY && export OPENAI_API_KEY   (and/or ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, NVIDIA_API_KEY)
    python scripts/judge_calibration.py --ids-file runs/preflight/pilot_ids.txt --models-file models.json \\
        --models openai:gpt-6.1-sol,openai:gpt-6.1-terra,openai:gpt-6-luna,openai:gpt-6.2-astra \\
        --negatives-from runs/pilot/c1 --negatives-from runs/pilot/rep_x --out runs/judge_calibration
    # v2 (jury from other families than the GPT repairer; the same pilot patches as v1, plus the right ones):
    NEG=$(for d in runs/pilot/*/; do printf -- '--negatives-from %s ' "${d%/}"; done)
    python scripts/judge_calibration.py --ids-file runs/preflight/pilot_ids.txt --models-file models.json \\
        --models anthropic:claude-opus-5-5,anthropic:claude-sonnet-5-5,anthropic:claude-haiku-5-5,deepseek:deepseek-v4-pro,deepseek:deepseek-flash \\
        $NEG --with-right --out runs/judge_calibration_v2
A reviewer that refuses (Claude stop_reason "refusal", or a refusal in words without a verdict) counts as
claim 0, as in the pipeline; the "refus" column counts the cases where that happened. The usage block at
the end gives tokens and list-price cost per model, the input for the 30-case cost projection.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import difflib
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import eval_harness  # noqa: E402
import multiagent as M  # noqa: E402
import protocols as P  # noqa: E402
from run_agent import load_meta  # noqa: E402


def decoy_diff(case: Path, rel: str) -> str:
    a = (case / "vulnerable" / rel).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    # after the module docstring/imports would be nicer; the end of the file is always safe
    b = a + ([] if not a or a[-1].endswith("\n") else ["\n"]) + ["\n", "_reviewed_input_handling = True\n"]
    return "".join(difflib.unified_diff(a, b, f"a/{rel}", f"b/{rel}"))


def make_item(code: str, hint: str, files: Dict[str, str], reference: str, decoy: str, vid: str,
              patch_dirs: List[Path], with_right: bool) -> Dict[str, Any]:
    """One case's candidate list, in a fixed order (the shuffle is applied later, per model):
    reference, decoy, the wrong patches in --negatives-from order, then the right ones (--with-right)."""
    cands = [("reference", 1, reference, "reference"), ("decoy", 0, decoy, "decoy")]
    rights = []
    seen = {reference, decoy}
    for src in patch_dirs:
        ev = Path(src) / vid / "eval.json"
        pd = Path(src) / vid / "patch.diff"
        if not (ev.exists() and pd.exists()):
            continue
        e = json.loads(ev.read_text())
        d = pd.read_text(errors="replace")
        if not d.strip() or d in seen or "environment check failed" in (e.get("notes") or ""):
            continue
        if e.get("apply_ok") is False:
            continue    # the reviewer would be told "applies=yes"; the gate rejects these before any reviewer
        if e.get("plausible"):
            if with_right:
                seen.add(d)
                rights.append(("right", 1, d, Path(src).name))
        else:
            seen.add(d)
            cands.append(("wrong", 0, d, Path(src).name))
    cands += rights
    return {"code": code, "hint": hint, "files": files,
            "cands": [{"k": i, "kind": kind, "truth": t, "source": source,
                       "versions": [{"md": f"## Patch\n```diff\n{d}```\n", "diff": d,
                                     "gate": {"applies": True, "failures": [], "changed_lines": None}}]}
                      for i, (kind, t, d, source) in enumerate(cands)]}


def export_prompts(out: Path, models: List[Any], items: Dict[str, Dict[str, Any]], seed: int) -> None:
    """The exact prompts jury_round would send to each model (same shuffle, same template), with no API call."""
    rows = []
    for m in models:
        for vid, it in items.items():
            cands = it["cands"]
            order = list(range(len(cands)))
            # jury_round is called with vid "<vid>:<spec>", round 0, juror 0
            random.Random(f"{seed}:{vid}:{m.spec}:0:0").shuffle(order)
            labelled = [(f"P{i + 1}", cands[order[i]]) for i in range(len(order))]
            hb = M.HINT_BLOCK.format(hint=it["hint"]) if it["hint"] else ""
            d = out / m.slug / vid
            d.mkdir(parents=True, exist_ok=True)
            (d / "system.md").write_text(M.REVIEWER_SYSTEM.replace("{with_analysis}", ""), encoding="utf-8")
            (d / "user.md").write_text(M.REVIEWER_USER.format(hint_block=hb, code=it["code"], analysis_block="",
                                                              candidates=M._cand_block(labelled, True),
                                                              debate_block=""), encoding="utf-8")
            rows += [{"model": m.spec, "vuln_id": vid, "label": lab, "kind": c["kind"], "truth": c["truth"],
                      "source": c.get("source", "")} for lab, c in labelled]
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "truth.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"prompts for {len(models)} model(s) x {len(items)} case(s) in {out}; truth in {out / 'truth.csv'}")


def auroc(pos: List[float], neg: List[float]):
    if not pos or not neg:
        return None
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


async def amain(a) -> None:
    overrides = json.loads(Path(a.models_file).read_text()) if a.models_file else {}
    models = [M.parse_model(s, overrides, a.max_tokens) for s in a.models.split(",") if s.strip()]
    ids = [l.split("#")[0].strip() for l in Path(a.ids_file).read_text().splitlines() if l.split("#")[0].strip()] \
        if a.ids_file else [s.strip() for s in a.vuln_ids.split(",") if s.strip()]
    a.gate, a.compiled_context, a.hint = True, True, a.hint
    items: Dict[str, Dict[str, Any]] = {}
    for vid in ids:
        case = a.workspaces / vid
        meta = load_meta(case)
        rels = M.context_files(case, meta, True)
        hint = P.localization_hint(case, meta, rels) if a.hint == "lines" else ""
        budget = int(min(m.context for m in models) * 0.4) - 4000
        files, excerpts, _ = M.fit_context(case, rels, budget, M.hint_ranges_of(hint))
        items[vid] = make_item(M.render(files, excerpts), hint, files, eval_harness.reference_diff(case),
                               decoy_diff(case, rels[0]), vid, a.negatives_from, a.with_right)
    if a.export_prompts:
        export_prompts(a.export_prompts, models, items, a.seed)
        return
    ctx = M.Ctx(a, {"analyst": None, "repairers": [], "jurors": models})
    rows: List[Dict[str, Any]] = []

    async def one(m: M.ModelRef, vid: str):
        it = items[vid]
        rec = {"stages": {}}
        out_dir = a.out / "raw" / m.slug / vid
        hb = M.HINT_BLOCK.format(hint=it["hint"]) if it["hint"] else ""
        vs = await M.jury_round(ctx, rec, 0, [m], it["cands"], it["code"], hb, "", "", it["files"], None,
                                out_dir, f"{vid}:{m.spec}")
        v = vs[0]
        for c in it["cands"]:
            rows.append({"model": m.spec, "vuln_id": vid, "kind": c["kind"], "source": c.get("source", ""),
                         "truth": c["truth"],
                         "status": v.get("status"), "claim": (v.get("claims_k") or {}).get(c["k"]),
                         "confidence": (v.get("conf_k") or {}).get(c["k"]),
                         "picked_best": int(v.get("best_k") == c["k"]) if v.get("status") == "ok" else None,
                         "refused": int(bool(v.get("refused")))})

    await asyncio.gather(*[one(m, vid) for m in models for vid in ids])
    a.out.mkdir(parents=True, exist_ok=True)
    cols = ["model", "vuln_id", "kind", "source", "truth", "status", "claim", "confidence", "picked_best", "refused"]
    with open(a.out / "judge_calibration.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    summary = {}
    for m in models:
        ok = [r for r in rows if r["model"] == m.spec and r["status"] == "ok" and r["claim"] is not None]
        pos = [r for r in ok if r["truth"] == 1]
        neg = [r for r in ok if r["truth"] == 0]
        wrong = [r for r in neg if r["kind"] == "wrong"]
        right = [r for r in pos if r["kind"] == "right"]
        refs = [r for r in pos if r["kind"] == "reference"]
        cs = [r for r in ok if r["confidence"] is not None]
        summary[m.spec] = {
            "n": len(ok), "unparsed": sum(1 for r in rows if r["model"] == m.spec) - len(ok),
            "sensitivity": sum(r["claim"] for r in pos) / len(pos) if pos else None,
            "specificity": sum(1 - r["claim"] for r in neg) / len(neg) if neg else None,
            "specificity_real_wrong": sum(1 - r["claim"] for r in wrong) / len(wrong) if wrong else None,
            "n_real_wrong": len(wrong),
            "sensitivity_real_right": sum(r["claim"] for r in right) / len(right) if right else None,
            "n_real_right": len(right),
            "auroc_confidence": auroc([r["confidence"] for r in pos if r["confidence"] is not None],
                                      [r["confidence"] for r in neg if r["confidence"] is not None]),
            # real patches only (right vs wrong): what the jury faces in C1
            "auroc_real": auroc([r["confidence"] for r in right if r["confidence"] is not None],
                                [r["confidence"] for r in wrong if r["confidence"] is not None]),
            "brier": (sum((r["confidence"] - r["truth"]) ** 2 for r in cs) / len(cs)) if cs else None,
            "best_is_reference": (sum(r["picked_best"] for r in refs) / len(refs)) if refs else None,
            # a refusal counts as claim 0 (as in the pipeline: a reviewer that refuses does not vouch)
            "refused_cases": len({r["vuln_id"] for r in rows if r["model"] == m.spec and r.get("refused")}),
        }
    (a.out / "judge_calibration_summary.json").write_text(json.dumps(summary, indent=2))
    f2 = lambda x: "  –  " if x is None else f"{x:6.2f}"  # noqa: E731
    print(f"{'model':48s} {'n':>4s} {'sens':>6s} {'spec':>6s} {'specW':>6s} {'sensR':>6s} {'AUROC':>6s} {'AUC_re':>6s} "
          f"{'Brier':>6s} {'best':>6s} {'refus':>5s}")
    for spec, s in sorted(summary.items(), key=lambda kv: -(kv[1]["auroc_confidence"] or 0)):
        print(f"{spec:48s} {s['n']:4d} {f2(s['sensitivity'])} {f2(s['specificity'])} {f2(s['specificity_real_wrong'])} "
              f"{f2(s['sensitivity_real_right'])} {f2(s['auroc_confidence'])} {f2(s['auroc_real'])} {f2(s['brier'])} "
              f"{f2(s['best_is_reference'])} {s['refused_cases']:5d}")
    usage = {spec: dict(u) for spec, u in ctx.usage.items()}
    cost = 0.0
    for spec, u in usage.items():
        mm = ctx.model_by_spec.get(spec)
        if mm and mm.provider == "claudecode":
            continue      # Claude plan: not billed (api_equivalent_usd says what it would cost at API prices)
        if mm and mm.price_in is not None and mm.price_out is not None:
            u["usd"] = round(u["input_tokens"] / 1e6 * mm.price_in + u["output_tokens"] / 1e6 * mm.price_out, 4)
            cost += u["usd"]
    (a.out / "judge_calibration_usage.json").write_text(json.dumps(usage, indent=2))
    print("\nTokens and list-price cost per model (the 30-case projection uses these):")
    for spec, u in usage.items():
        print(f"  {spec:46s} calls {u['calls']:3.0f}  in {u['input_tokens']:9.0f}  out {u['output_tokens']:8.0f}"
              + (f"  ~USD {u['usd']:.3f}" if "usd" in u else "")
              + (f"  Claude plan, not billed (~USD {u['api_equivalent_usd']:.3f} at API prices)"
                 if "api_equivalent_usd" in u else ""))
    print(f"  total ~USD {cost:.2f}")
    print("\nPick the jury from DIFFERENT families than the repairers, best AUROC and specificity on real wrong "
          "patches first.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Calibrate candidate reviewer models on known-truth patches (listwise).")
    ap.add_argument("--models", required=True)
    ap.add_argument("--models-file")
    ap.add_argument("--vuln-ids")
    ap.add_argument("--ids-file")
    ap.add_argument("--negatives-from", type=Path, action="append", default=[],
                    help="pilot run dir (runs/pilot/<agent>): its unverified patches become 'wrong' candidates")
    ap.add_argument("--with-right", action="store_true",
                    help="also add the verified patches of those dirs as 'right' candidates (realistic positives)")
    ap.add_argument("--export-prompts", type=Path,
                    help="write the prompts and truth.csv to this dir and exit, without calling any API")
    ap.add_argument("--workspaces", type=Path, default=SCRIPTS.parent / "workspaces")
    ap.add_argument("--out", type=Path, default=SCRIPTS.parent / "runs" / "judge_calibration")
    ap.add_argument("--hint", choices=["lines", "none"], default="lines")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=16384)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--max-http-retries", type=int, default=6)
    ap.add_argument("--per-model-concurrency", type=int, default=2)
    ap.add_argument("--max-active-cases", type=int, default=3)
    ap.add_argument("--nvidia-rpm", type=float)
    ap.add_argument("--openai-rpm", type=float)
    ap.add_argument("--nvidia-base-url")
    ap.add_argument("--openai-base-url")
    ap.add_argument("--anthropic-rpm", type=float)
    ap.add_argument("--deepseek-rpm", type=float)
    ap.add_argument("--anthropic-base-url")
    ap.add_argument("--deepseek-base-url")
    M.add_claudecode_args(ap)
    a = ap.parse_args()
    a.workspaces = a.workspaces.resolve()
    random.seed(a.seed)
    asyncio.run(amain(a))


if __name__ == "__main__":
    main()
