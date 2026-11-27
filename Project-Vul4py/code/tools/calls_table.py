#!/usr/bin/env python3
"""calls_table.py -- one row per model call, with tokens, time and list-price cost.

Reads the frozen records that scripts/multiagent.py writes (runs/<dir>/<agent>/<case>/llm_response.json,
one entry per call under "stages") and prices every call with the list prices in models.json:

  python code/tools/calls_table.py --runs runs/final --version v3 --models-file code/models.json --out results/logs/calls/calls_v3_main.csv

Cost rules (the same ones the papers use):
- OpenAI, Anthropic and DeepSeek models: input and output tokens at the models.json list price (USD per
  million). DeepSeek prices are its weekday peak prices; off-peak calls cost half, so these are upper bounds.
- Claude Haiku 5.5 is priced per request by prompt size: up to 100k prompt tokens 0.10/0.50, above 0.50/2.50.
- claudecode:* (Claude through the Claude Code CLI on the Claude plan) is not billed per call; the row keeps
  the list-price cost and the API-equivalent cost Claude Code reports.
- NVIDIA API catalog models (v0) were free; their cost is 0 and marked as such.
Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

TIERS = {"claude-haiku-5-5": (100_000, 0.50, 2.50)}
COLS = ["version", "run", "agent", "case", "stage", "role", "model", "status", "input_tokens", "output_tokens",
        "thinking_tokens", "latency_s", "http_attempts", "finish_reason", "list_cost_usd",
        "api_equivalent_usd", "price_note"]


def price(model: str, tin: int, tout: int, prices: dict):
    if model.startswith("nvidia:"):
        return 0.0, "NVIDIA API catalog (free)"
    m = prices.get(model)
    if not m or m.get("price_in") is None:
        return None, "no list price"
    pin, pout = m["price_in"], m["price_out"]
    note = "list price"
    tier = TIERS.get(model.split(":", 1)[-1])
    if tier and tin > tier[0]:
        pin, pout, note = tier[1], tier[2], "list price, Haiku tier above 100k prompt tokens"
    if model.startswith("deepseek:"):
        note = "list price at DeepSeek peak hours (off-peak is half)"
    if model.startswith("claudecode:"):
        note = "Claude plan, not billed per call; list-price equivalent"
    return tin / 1e6 * pin + tout / 1e6 * pout, note


def rows_for(runs: Path, version: str, prices: dict):
    for rec_path in sorted(runs.glob("*/*/llm_response.json")):
        agent, case = rec_path.parent.parent.name, rec_path.parent.name
        try:
            rec = json.loads(rec_path.read_text())
        except Exception:  # noqa: BLE001
            continue
        for key, st in (rec.get("stages") or {}).items():
            model = st.get("model") or ""
            tin, tout = int(st.get("input_tokens") or 0), int(st.get("output_tokens") or 0)
            cost, note = price(model, tin, tout, prices)
            yield {"version": version, "run": runs.name, "agent": agent, "case": case, "stage": key,
                   "role": st.get("role"), "model": model, "status": st.get("status", "ok"),
                   "input_tokens": tin, "output_tokens": tout, "thinking_tokens": st.get("thinking_tokens"),
                   "latency_s": round((st.get("latency_ms") or 0) / 1000, 1),
                   "http_attempts": len(st.get("http_attempts") or []), "finish_reason": st.get("finish_reason"),
                   "list_cost_usd": None if cost is None else round(cost, 6),
                   "api_equivalent_usd": st.get("api_equivalent_usd"), "price_note": note}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, required=True, help="a runs directory (runs/final, runs/pilot, ...)")
    ap.add_argument("--version", required=True, help="label for the version column (v2, v3, ...)")
    ap.add_argument("--models-file", type=Path, default=Path("models.json"))
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    prices = {k: v for k, v in json.loads(a.models_file.read_text()).items() if isinstance(v, dict)}
    rows = list(rows_for(a.runs, a.version, prices))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    total = sum(r["list_cost_usd"] or 0 for r in rows)
    print(f"[+] {len(rows)} calls, {sum(r['input_tokens'] for r in rows):,} input and "
          f"{sum(r['output_tokens'] for r in rows):,} output tokens, {total:.2f} USD at list price -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
