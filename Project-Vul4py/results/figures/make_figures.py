#!/usr/bin/env python3
"""make_figures.py -- the data figures of both papers, from the CSV/JSON files of this repository.

  python results/figures/make_figures.py        (from the repository root; needs matplotlib >= 3.8)
  python results/figures/make_figures.py fig_main fig_cost   (redraws only the figures named)

Writes results/figures/<name>.pdf and .png (300 dpi), results/figures/MANIFEST.json, which records for every
figure the input files with their sha256, the transformations and the uncertainty shown, and
results/figures/figure_values.csv, one row per plotted value (count, denominator, interval, source file).

Style (Nov 26, 2026): the redesign the author made for the final paper (left-aligned bold titles, colours
reinforced by marker shape, counts printed beside every interval, zero-based bars) with the author's palette
(índigo noche, lavanda eléctrico, verde voltio; the light colours outlined in indigo), drawn here from the
repository's data instead of from values copied from the manuscript. The v0 figure keeps its published style.
Rules followed:
- proportions are points with 95% Wilson intervals and their k/n; bars start at zero;
- colour is never the only cue, and one colour means one thing within a figure;
- nothing is typed by hand except one documented constant: the number of cases that passed the scan with the
  public Vul4Py release (18, code/docs/README_multiagent.md).
Rows whose data are not in the repository yet (the v5 arms) are left out, and the manifest says which.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401
from matplotlib.colors import to_rgba  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "figures"

# ------------------------------------------------------------------ style of the final paper (redesign)
# palette chosen by the author: índigo noche, lavanda eléctrico, verde voltio. Their lightness differs (L* 24, 63,
# 94), so they stay apart in grayscale; the two light ones are too pale for white paper on their own, so they are
# always drawn with an indigo outline (markers, bars) or an indigo casing (interval lines).
INDIGO, LAVENDER, VOLT = "#312E81", "#B57BFF", "#CEFF00"
GRAY, LIGHT, DARK = "#59636E", "#DCE3E8", "#17212B"
LIGHT_FILLS = {LAVENDER, VOLT}
STYLE = {
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"],
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INDIGO, "axes.labelsize": 9,
    "axes.labelcolor": DARK, "axes.edgecolor": DARK, "axes.linewidth": 0.7,
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "xtick.color": DARK, "ytick.color": DARK,
    "xtick.direction": "out", "ytick.direction": "out", "xtick.major.size": 3, "ytick.major.size": 0,
    "pdf.fonttype": 42, "ps.fonttype": 42, "figure.facecolor": "white", "savefig.facecolor": "white",
    "savefig.edgecolor": "white", "savefig.transparent": False, "savefig.dpi": 300,
}
# ------------------------------------------------------------------ style of the v0 paper (kept as published)
OKABE = {"black": "#000000", "orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442",
         "blue": "#0072B2", "vermillion": "#D55E00", "purple": "#CC79A7", "grey": "#7A7A7A"}
MM = 1 / 25.4
RC = {"font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
      "legend.fontsize": 7, "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
      "ps.fonttype": 42, "savefig.dpi": 300, "figure.dpi": 150}

PUBLIC_RELEASE_OK = {"value": 18, "source": "code/docs/README_multiagent.md: 18 cases passed the first scan with the public release"}
MANIFEST: dict = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "figures": {}}
VALUES: list = []
VALUE_FIELDS = ["figure", "item", "measure", "numerator", "denominator", "value", "ci95_low", "ci95_high", "unit", "source"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def rows(path: Path, delimiter=","):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def bit(v):
    v = (v or "").strip()
    if v in ("", "None", "nan"):
        return None
    if v in ("True", "False"):
        return int(v == "True")
    return int(float(v))


def wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def complete(r) -> bool:
    return r.get("status") == "complete" and bit(r.get("V")) in (0, 1)


def arm(rs, agent, claim_col):
    done = [r for r in rs if r["agent"] == agent and complete(r)]
    v = sum(bit(r["V"]) for r in done)
    cl = [r for r in done if bit(r.get(claim_col)) == 1]
    return {"n": len(done), "verified": v, "claims": len(cl), "false": sum(1 for r in cl if bit(r["V"]) == 0)}


def record(figure, item, measure, value, unit, source, k=None, n=None):
    lo, hi = wilson(k, n) if (k is not None and n) else (None, None)
    VALUES.append({"figure": figure, "item": item, "measure": measure,
                   "numerator": "" if k is None else k, "denominator": "" if n is None else n,
                   "value": f"{value:.6f}", "ci95_low": "" if lo is None else f"{lo:.6f}",
                   "ci95_high": "" if hi is None else f"{hi:.6f}", "unit": unit, "source": source})


def save(fig, name: str, inputs, notes: dict, rc: dict | None = None):
    """Fonts are resolved when the file is written, so the figure's style must be active then too."""
    OUT.mkdir(exist_ok=True)
    # no creation date in the PDF, so the same data and library versions give byte-identical files
    pdf_meta = {"Creator": "results/figures/make_figures.py", "CreationDate": None}
    with plt.rc_context(rc or {}):
        for ext in ("pdf", "png"):
            fig.savefig(OUT / f"{name}.{ext}", metadata=pdf_meta if ext == "pdf" else None)
    plt.close(fig)
    outs = [OUT / f"{name}.pdf", OUT / f"{name}.png"]
    MANIFEST["figures"][name] = {"files": [rel(p) for p in outs],
                                 "outputs": {rel(p): sha(p) for p in outs},
                                 "inputs": {rel(p): sha(p) for p in inputs if p.exists()},
                                 **notes}


def style_axis(ax, grid_axis="x"):
    ax.grid(axis=grid_axis, color=LIGHT, linewidth=0.7)
    ax.tick_params(axis="both", length=3, width=0.65)


def edge(color):
    """outline of a filled mark: indigo around the light colours, white around the dark ones"""
    return INDIGO if color in LIGHT_FILLS else "white"


def interval(ax, y, k, n, color, marker, size=5.6):
    p = k / n
    lo, hi = wilson(k, n)
    light = color in LIGHT_FILLS
    eb = ax.errorbar(p, y, xerr=[[p - lo], [hi - p]], fmt=marker, color=color, ecolor=color, markersize=size + 0.4 * light,
                     capsize=2.5, elinewidth=1.3, markeredgecolor=edge(color), markeredgewidth=0.8 if light else 0.65, zorder=3)
    for artist in eb.get_children():         # a 0/n estimate sits on the axis; draw its marker whole
        artist.set_clip_on(False)
    if color == VOLT:                        # a volt line alone is invisible on white: give it an indigo casing
        for artist in list(eb.lines[1]) + list(eb.lines[2]):
            artist.set_path_effects([pe.withStroke(linewidth=2.6, foreground=INDIGO)])
    return p


def dotrow(ax, y, k, n, color, marker, label=None):          # v0 paper style
    p = k / n if n else math.nan
    lo, hi = wilson(k, n)
    ax.errorbar(p, y, xerr=[[p - lo], [hi - p]], fmt=marker, color=color, ms=5, capsize=2.5, lw=1.1, label=label)
    ax.text(1.02, y, f"{k}/{n}", va="center", fontsize=7, transform=ax.get_yaxis_transform())


# ----------------------------------------------------------------------------- figure: environment
def fig_environment():
    rounds = sorted((ROOT / "experiments/v1_environment").glob("scan_report_round*.tsv"))
    vals = [(f"R{i}", sum(1 for r in rows(p, "\t") if r.get("status") == "OK"), p) for i, p in enumerate(rounds)]
    orp = ROOT / "experiments/v1_environment/oracle_report.tsv"
    healthy = {r["vuln_id"] for r in rows(orp, "\t") if r.get("healthy") == "True"}
    ov = ROOT / "prereg" / "oracle_valid.txt"            # the list fixed for the split; must be the same cases
    if healthy != {x for x in ov.read_text().split() if x}:
        raise SystemExit("oracle_report.tsv and prereg/oracle_valid.txt disagree")
    oracle = len(healthy)
    docs = ROOT / "code/docs/README_multiagent.md"      # source of the public-release count
    labels = ["Public\nrelease"] + [v[0] for v in vals] + ["Oracle\ncontrol"]
    counts = [PUBLIC_RELEASE_OK["value"]] + [v[1] for v in vals] + [oracle]
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8.0, 3.0), layout="constrained")
        x = list(range(len(labels)))
        last = len(vals)                     # index of the last build round
        # the build rounds are one series on the instance; the public release (sandbox) and the oracle control
        # (a separate check) are not part of it, so only R0-R5 are joined by a line
        ax.plot(x[1:last + 1], counts[1:last + 1], color=INDIGO, linewidth=1.4, zorder=1)
        colors = [GRAY] + [INDIGO] * len(vals) + [VOLT]
        ax.scatter(x, counts, c=colors, s=52, edgecolors=[edge(c) for c in colors], linewidths=0.9, zorder=2)
        for xi, yi in zip(x, counts):
            ax.text(xi, yi + 3.4, f"{yi}", ha="center", va="bottom", fontsize=8.5, fontweight="bold", color=DARK)
        for sep in (0.5, last + 0.5):
            ax.axvline(sep, color=GRAY, linewidth=0.9, linestyle=(0, (3, 3)))
        ax.set_xticks(x, labels)
        ax.set_xlim(-0.45, len(labels) - 0.55)
        ax.set_ylim(0, 112)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_ylabel("Valid cases (of 100)")
        ax.set_title("Cases passing environment validation", loc="left", pad=9)
        style_axis(ax, "y")
        ax.text((1 + last) / 2, -0.23, "Build rounds on the instance, with the environment repairs",
                transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=8, color=GRAY)
    record("fig_environment", "Public release (sandbox scan)", "valid_cases", counts[0], "cases", PUBLIC_RELEASE_OK["source"])
    for lab, c, p in vals:
        record("fig_environment", lab, "valid_cases", c, "cases", rel(p) + " (status OK)")
    record("fig_environment", "Oracle control", "valid_cases", oracle, "cases", rel(orp) + " (healthy == True)")
    save(fig, "fig_environment", rounds + [orp, ov, docs],
         {"what": "cases with status OK per scan round on the instance; oracle-control survivors; public release as a "
                  "separate point (sandbox scan), not joined to the rounds", "constants": [PUBLIC_RELEASE_OK]}, rc=STYLE)


# ----------------------------------------------------------------------------- figure: pilot-scale comparisons
def fig_pilot():
    gbp = ROOT / "experiments/v3_main/gpt_benchmark/gpt_benchmark_verdicts.csv"
    plp = ROOT / "experiments/v2_pilot_tournament/results.csv"
    v0p = ROOT / "experiments/v0_mvp/results.csv"
    gb, pilot, v0 = rows(gbp), rows(plp), rows(v0p)
    items = [("v0 MVP: laguna-xs-2.1 (own pilot)", "v0 pilot", sum(bit(r["verified_repair"]) for r in v0), len(v0), rel(v0p))]
    names = {"gpt-6-luna": "GPT-6 Luna", "gpt-6.1-terra": "GPT-6.1 Terra", "gpt-6.2-astra": "GPT-6.2 Astra",
             "gpt-6.2-sol": "GPT-6.2 Sol", "gpt-6.2-sol_recortado": "GPT-6.2 Sol (trimmed context)"}
    by = defaultdict(list)
    for r in gb:
        by[r["model"]].append(int(r["V"]))
    for m in names:
        if m in by:
            items.append((f"GPT benchmark: {names[m]}", "GPT benchmark", sum(by[m]), len(by[m]), rel(gbp)))
    for ag, lab, grp in (("rep_gpt-5.4-mini", "Tournament repairer: GPT-5.4 mini", "Tournament"),
                         ("rep_gpt-6.2-sol", "Tournament repairer: GPT-6.2 Sol", "Tournament"),
                         ("c1", "Pilot C1: GPT-model jury", "C1 pilots"),
                         ("c1v2", "Pilot C1 v2: cross-family jury", "C1 pilots")):
        a = arm(pilot, ag, "D_repairer")
        items.append((lab, grp, a["verified"], a["n"], rel(plp)))
    gcol = {"v0 pilot": GRAY, "GPT benchmark": INDIGO, "Tournament": LAVENDER, "C1 pilots": VOLT}
    gmk = {"v0 pilot": "D", "GPT benchmark": "o", "Tournament": "s", "C1 pilots": "^"}
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8.4, 4.8), layout="constrained")
        ax.set_ylim(len(items) - 0.45, -0.55)
        prev = None
        for i, (lab, grp, k, n, src) in enumerate(items):
            p = interval(ax, i, k, n, gcol[grp], gmk[grp])
            ax.text(1.025, i, f"{k}/{n}", ha="left", va="center", fontsize=8, color=DARK, transform=ax.get_yaxis_transform())
            if prev is not None and grp != prev:
                ax.axhline(i - 0.5, color=LIGHT, linewidth=0.8)
            prev = grp
            record("fig_pilot_benchmarks", lab, "VRR", p, "proportion", src, k, n)
        ax.set_yticks(range(len(items)), [it[0] for it in items])
        ax.set_xlim(0, 1.14)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xlabel("Verified repair rate (VRR), 95% Wilson interval")
        ax.set_title("Pilot-scale comparisons, five cases per row", loc="left", pad=9)
        ax.text(1.025, 1.02, "Verified", ha="left", va="bottom", fontsize=8, color=GRAY, transform=ax.transAxes)
        style_axis(ax, "x")
        handles = [Line2D([0], [0], marker=gmk[g], linestyle="none", markerfacecolor=gcol[g], markeredgecolor=edge(gcol[g]),
                          markeredgewidth=0.8, markersize=6.5, label=g) for g in gcol]
        fig.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False, fontsize=8)
    save(fig, "fig_pilot_benchmarks", [gbp, plp, v0p],
         {"what": "VRR per model or condition on 5 cases", "uncertainty": "95% Wilson score interval; n = 5 per row"}, rc=STYLE)


# ----------------------------------------------------------------------------- figure: main VRR and FAR
def fig_main():
    mp = ROOT / "experiments/v3_main/results.csv"
    v0p = ROOT / "experiments/v0_mvp/results.csv"
    main, v0 = rows(mp), rows(v0p)
    v0c = [r for r in v0 if r["claim"] == "True"]
    series = [("v0 pilot, laguna-xs-2.1", sum(bit(r["verified_repair"]) for r in v0), len(v0),
               sum(1 for r in v0c if r["verified_repair"] == "False"), len(v0c), "v0", rel(v0p))]
    for ag, col, lab in (("c0", "D_repairer", "C0: repairer alone (main sample)"),
                         ("c0g", "D_repairer", "C0g: repairer + mechanical gate"),
                         ("c1", "D_unanimous", "C1: analyst + unanimous jury")):
        a = arm(main, ag, col)
        series.append((lab, a["verified"], a["n"], a["false"], a["claims"], "main", rel(mp)))
    inputs = [mp, v0p]
    missing = []
    conf = ROOT / "experiments/v4_evigate_confirmation/confirm/results.csv"
    if conf.exists():
        a = arm(rows(conf), "c0", "D_repairer")
        series.append((f"C0: {a['n']} confirmation cases", a["verified"], a["n"], a["false"], a["claims"], "confirmation", rel(conf)))
        inputs.append(conf)
    else:
        missing.append("v4 confirmation (experiments/v4_evigate_confirmation/confirm/results.csv)")
    v5 = ROOT / "experiments/v5_rag/results.csv"
    if v5.exists():
        r5 = rows(v5)
        for ag, lab in (("c0", "v5: C0 re-evaluated, v5 harness"), ("c0m", "v5: Haiku 5.5 alone"), ("c0mr", "v5: Haiku 5.5 + RAG")):
            a = arm(r5, ag, "D_repairer")
            if a["n"]:
                series.append((lab, a["verified"], a["n"], a["false"], a["claims"], "v5", rel(v5)))
        inputs.append(v5)
    else:
        missing.append("v5 arms (experiments/v5_rag/results.csv)")
    color = {"v0": GRAY, "main": INDIGO, "confirmation": LAVENDER, "v5": VOLT}
    marker = {"v0": "D", "main": "o", "confirmation": "s", "v5": "^"}
    with plt.rc_context(STYLE):
        fig, (axv, axf) = plt.subplots(1, 2, figsize=(8.65, 0.55 * len(series) + 1.15), layout="constrained")
        for i, (lab, vk, vn, fk, fn, grp, src) in enumerate(series):
            pv = interval(axv, i, vk, vn, color[grp], marker[grp])
            axv.text(1.035, i, f"{vk}/{vn}", ha="left", va="center", fontsize=7.8, color=DARK, transform=axv.get_yaxis_transform())
            record("fig_main_vrr_far", lab, "VRR", pv, "proportion", src, vk, vn)
            if fn:
                pf = interval(axf, i, fk, fn, color[grp], marker[grp])
                axf.text(1.035, i, f"{fk}/{fn}", ha="left", va="center", fontsize=7.8, color=DARK, transform=axf.get_yaxis_transform())
                record("fig_main_vrr_far", lab, "FAR", pf, "proportion", src, fk, fn)
        for ax in (axv, axf):
            ax.set_xlim(0, 1.19)
            ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
            ax.set_ylim(len(series) - 0.5, -0.5)
            style_axis(ax, "x")
            ax.text(1.04, 1.025, "Count", ha="left", va="bottom", fontsize=7.6, color=GRAY, transform=ax.transAxes)
        axv.set_yticks(range(len(series)), [s[0] for s in series])
        axf.set_yticks(range(len(series)), [""] * len(series))
        axv.set_xlabel("VRR, 95% Wilson interval")
        axf.set_xlabel("FAR, 95% Wilson interval")
        axv.set_title("Verified repair rate", loc="left", pad=9)
        axf.set_title("False assurance rate", loc="left", pad=9)
    save(fig, "fig_main_vrr_far", inputs,
         {"what": "VRR and FAR with 95% Wilson intervals; labels give k/n",
          "claim_rule": "repairer's own claim (C0, C0g, v5); unanimous jury (C1, primary rule)", "missing_rows": missing}, rc=STYLE)


# ----------------------------------------------------------------------------- figure: juror calibration
def fig_judges():
    sp = ROOT / "experiments/v2_pilot_tournament/judge_calibration_v2/judge_calibration_summary.json"
    up = ROOT / "experiments/v2_pilot_tournament/judge_calibration_v2/judge_calibration_usage.json"
    mfp = ROOT / "code/models.json"
    dp = ROOT / "prereg/decisiones_v2.txt"
    s, u, prices = json.loads(sp.read_text()), json.loads(up.read_text()), json.loads(mfp.read_text())
    jury = next(line.split("=", 1)[1].strip().split(",") for line in dp.read_text(encoding="utf-8").splitlines()
                if line.startswith("jurado="))
    models = list(s.keys())

    def short(m):
        return m.split(":", 1)[1].replace("claude-", "Claude ").replace("deepseek-", "DeepSeek ").replace("-5-5", " 5.5") \
                .replace("v4-pro", "V4 Pro").replace("flash", "Flash").replace("opus", "Opus").replace("sonnet", "Sonnet") \
                .replace("haiku", "Haiku")
    costs = [u[m]["input_tokens"] * prices[m]["price_in"] / 1e6 + u[m]["output_tokens"] * prices[m]["price_out"] / 1e6
             for m in models]
    metric = [("auroc_confidence", "AUROC", INDIGO, "o", -0.14), ("sensitivity", "Sensitivity", LAVENDER, "s", 0.0),
              ("specificity", "Specificity", VOLT, "^", 0.14)]
    with plt.rc_context(STYLE):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.5, 3.7), gridspec_kw={"width_ratios": [1.65, 0.9]}, layout="constrained")
        for ax in (a1, a2):
            ax.set_ylim(len(models) - 0.48, -0.52)
        for i, m in enumerate(models):
            for key, lab, col, mk, off in metric:
                a1.scatter(s[m][key], i + off, s=38, marker=mk, color=col, edgecolor=edge(col),
                           linewidth=0.8 if col in LIGHT_FILLS else 0.65, zorder=3)
                record("fig_jury_calibration", short(m), lab, s[m][key], "proportion", rel(sp))
            a2.barh(i, costs[i], height=0.52, color=GRAY, alpha=0.85)
            a2.text(costs[i] + 0.02, i, f"{costs[i]:.2f}", va="center", ha="left", fontsize=8, color=DARK)
            record("fig_jury_calibration", short(m), "list_price_cost_5_calls", costs[i], "USD", f"{rel(up)} tokens x {rel(mfp)} prices")
        a1.set_yticks(range(len(models)), [short(m) + (" *" if m in jury else "") for m in models])
        for tick, m in zip(a1.get_yticklabels(), models):
            tick.set_color(INDIGO if m in jury else GRAY)
            tick.set_fontweight("bold" if m in jury else "normal")
        a2.set_yticks(range(len(models)), [""] * len(models))
        a1.set_xlim(0, 1.02)
        a1.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
        a2.set_xlim(0, max(costs) * 1.3)
        a1.set_xlabel("Score on 28 known-truth candidates (13 correct, 15 wrong)")
        a2.set_xlabel("USD (list price)")
        a1.set_title("Calibration metrics", loc="left", pad=9)
        a2.set_title("Cost of the five calls", loc="left", pad=9)
        style_axis(a1, "x")
        style_axis(a2, "x")
        handles = [Line2D([0], [0], marker=mk, color=col, markeredgecolor=edge(col), markeredgewidth=0.8, linestyle="none",
                          markersize=6, label=lab) for _, lab, col, mk, _ in metric]
        handles.append(Line2D([0], [0], linestyle="none", marker="$*$", color=INDIGO, markersize=6, label="selected juror"))
        fig.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False, fontsize=8)
    save(fig, "fig_jury_calibration", [sp, up, mfp, dp],
         {"what": "per-juror AUROC, sensitivity, specificity on 28 candidates; list-price cost of 5 calls (tokens x models.json)",
          "selected": jury, "note": "point estimates; the 28 candidates come from 5 pilot cases, so the scores are not independent"}, rc=STYLE)


# ----------------------------------------------------------------------------- figure: tokens and time per call
def fig_calls():
    files = [f for f in sorted((ROOT / "results/logs/calls").glob("calls_v*.csv")) if "totals" not in f.name]
    calls = []
    for f in files:
        calls += rows(f)
    names = {"gpt-6.2-sol": "GPT-6.2 Sol", "gpt-5.4-mini": "GPT-5.4 mini", "gpt-6-luna": "GPT-6 Luna",
             "gpt-6.1-sol": "GPT-6.1 Sol", "gpt-6.1-terra": "GPT-6.1 Terra", "claude-opus-5-5": "Claude Opus 5.5",
             "claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-haiku-5-5": "Claude Haiku 5.5",
             "deepseek-v4-pro": "DeepSeek V4 Pro", "poolside/laguna-xs-2.1": "laguna-xs-2.1"}
    role_name = {"reviewer": "juror", "repairer": "repairer", "analyst": "analyst"}
    role_col = {"juror": INDIGO, "repairer": LAVENDER, "analyst": VOLT}
    groups = defaultdict(list)
    for r in calls:
        if r["status"] != "ok":
            continue
        m = r["model"].split(":", 1)[-1]
        groups[(names.get(m, m), role_name.get(r["role"], r["role"]))].append(r)
    order = {"juror": 0, "repairer": 1, "analyst": 2}
    keys = sorted(groups, key=lambda k: (order.get(k[1], 3), -len(groups[k]), k[0]))
    fields = (("input_tokens", "Input tokens per call"), ("output_tokens", "Output tokens per call"), ("latency_s", "Seconds per call"))
    rng = random.Random(20261127)                   # fixed jitter, so the figure redraws identically
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 3, figsize=(10.2, 0.42 * len(keys) + 1.4), sharey=True,
                                 gridspec_kw={"width_ratios": [1.12, 1.12, 0.95]}, layout="constrained")
        for ax, (field, lab) in zip(axes, fields):
            data = [[max(float(r[field] or 0), 1.0) for r in groups[k]] for k in keys]
            bp = ax.boxplot(data, positions=range(len(keys)), orientation="horizontal", widths=0.46, patch_artist=True,
                            showfliers=False, manage_ticks=False, medianprops={"color": DARK, "linewidth": 1.2},
                            whiskerprops={"color": GRAY, "linewidth": 0.8}, capprops={"color": GRAY, "linewidth": 0.8},
                            boxprops={"color": GRAY, "linewidth": 0.75})
            for box, k in zip(bp["boxes"], keys):
                col = role_col[k[1]]
                box.set_facecolor(to_rgba(col, 0.17 if col == INDIGO else 0.38))
                box.set_edgecolor(INDIGO if col in LIGHT_FILLS else col)
            for i, (k, d) in enumerate(zip(keys, data)):
                col = role_col[k[1]]
                light = col in LIGHT_FILLS
                ax.scatter(d, [i + rng.uniform(-0.16, 0.16) for _ in d], s=9 if light else 8,
                           color=to_rgba(col, 0.85 if light else 0.55),
                           edgecolors=to_rgba(INDIGO, 0.75) if light else "none", linewidths=0.35 if light else 0, zorder=3)
                med = sorted(d)[len(d) // 2] if len(d) % 2 else sum(sorted(d)[len(d) // 2 - 1:len(d) // 2 + 1]) / 2
                record("fig_calls_tokens_time", f"{k[0]} ({k[1]})", f"median_{field}", med,
                       "seconds" if field == "latency_s" else "tokens", "results/logs/calls/calls_v*.csv", None, None)
            ax.set_xscale("log")
            ax.set_ylim(len(keys) - 0.45, -0.55)
            ax.set_xlabel(lab)
            ax.grid(axis="x", color=LIGHT, linewidth=0.7)
            ax.tick_params(axis="both", length=3, width=0.65, colors=DARK)
        axes[0].set_yticks(range(len(keys)), [f"{m} ({role}, n={len(groups[(m, role)])})" for m, role in keys])
        for ax in axes[1:]:
            ax.tick_params(axis="y", labelleft=False)
        versions = sorted({r["version"] for r in calls})
        fig.suptitle(f"Every recorded model call ({', '.join(versions)}), one point per call, log scale",
                     x=0.02, ha="left", fontsize=10, fontweight="bold", color=INDIGO)
        handles = [Line2D([0], [0], marker="s", linestyle="none", markersize=7, markerfacecolor=to_rgba(c, 0.85 if c in LIGHT_FILLS else 0.6),
                          markeredgecolor=INDIGO if c in LIGHT_FILLS else c, markeredgewidth=0.8, label=r) for r, c in role_col.items()]
        fig.legend(handles=handles, loc="outside lower center", ncol=3, frameon=False, fontsize=8)
    save(fig, "fig_calls_tokens_time", files,
         {"what": "distribution per model and role of input/output tokens and latency per call",
          "transform": "log10 x-axis; zero values drawn at 1; boxes = quartiles, whiskers = 1.5 IQR, points = calls with fixed jitter"}, rc=STYLE)


# ----------------------------------------------------------------------------- figure: cost per verified repair
def fig_cost():
    cp = ROOT / "results/logs/calls/calls_v3_main.csv"
    mp = ROOT / "experiments/v3_main/results.csv"
    calls, main = rows(cp), rows(mp)
    cost_by_agent = defaultdict(float)
    for r in calls:
        cost_by_agent[r["agent"]] += float(r["list_cost_usd"] or 0)
    bars = []
    for ag, lab in (("c0", "C0\nRepairer alone"), ("c0g", "C0g\nMechanical gate"), ("c1", "C1\nAnalyst + jury")):
        a = arm(main, ag, "D_repairer")
        attempts = sum(1 for r in main if r["agent"] == ag)
        c = cost_by_agent[ag]
        bars.append((lab, c / max(attempts, 1), c / a["verified"] if a["verified"] else math.nan, attempts, a["verified"], c))
    v5c = ROOT / "results/logs/calls/calls_v5.csv"
    missing = [] if v5c.exists() else ["v5 arms (results/logs/calls/calls_v5.csv)"]
    colors = [INDIGO, LAVENDER, VOLT]
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.3), layout="constrained")
        for ax, idx, title, measure in ((axes[0], 1, "Per attempted case", "cost_per_attempted_case"),
                                        (axes[1], 2, "Per verified repair", "cost_per_verified_repair")):
            vals = [b[idx] for b in bars]
            top = max(vals) * 1.12
            ax.bar(range(len(bars)), vals, width=0.58, color=colors, edgecolor=INDIGO, linewidth=0.9, zorder=2)
            for xi, (b, v) in enumerate(zip(bars, vals)):
                ax.text(xi, v + top * 0.025, f"{v:.3f}", ha="center", va="bottom", fontsize=8.5, fontweight="bold", color=DARK)
                den = b[3] if idx == 1 else b[4]
                record("fig_cost_per_repair", b[0].split("\n")[0], measure, v, "USD", f"{rel(cp)} / {rel(mp)}", None, None)
                if idx == 1:
                    record("fig_cost_per_repair", b[0].split("\n")[0], "total_list_cost", b[5], "USD", rel(cp))
                record("fig_cost_per_repair", b[0].split("\n")[0], "denominator_" + measure, den, "count", rel(mp))
            ax.set_xticks(range(len(bars)), [b[0] for b in bars])
            ax.set_ylim(0, top)
            ax.set_ylabel("USD (list price)")
            ax.set_title(title, loc="left", pad=9)
            style_axis(ax, "y")
        fig.suptitle("Main sample (v3): list-price cost of all model calls of each condition", x=0.02, ha="left",
                     fontsize=10, fontweight="bold", color=INDIGO)
    save(fig, "fig_cost_per_repair", [cp, mp],
         {"what": "sum of list-price cost of all calls per condition / attempts and / verified repairs",
          "note": "C1 includes Claude jurors on the Claude plan priced at list price and DeepSeek at peak prices",
          "missing_rows": missing}, rc=STYLE)


# ----------------------------------------------------------------------------- figure: coverage rule
def fig_coverage():
    mp = ROOT / "experiments/v3_main/results.csv"
    conf = ROOT / "experiments/v4_evigate_confirmation/confirm/results.csv"
    sets = [("C0, main sample", mp, "c0"), ("C0g, main sample", mp, "c0g"), ("C1, main sample", mp, "c1")]
    if conf.exists():
        sets.append(("C0, confirmation", conf, "c0"))
    loaded = [(lab, p, ag, rows(p)) for lab, p, ag in sets]
    # hint_coverage and D_coverage exist only in results written by fa_metrics.py of v4 or later
    dropped = [s[0] for s in loaded if not any((r.get("hint_coverage") or "").strip() not in ("", "None") for r in s[3])]
    loaded = [s for s in loaded if s[0] not in dropped]
    if not loaded:
        MANIFEST["figures"]["fig_coverage_rule"] = {"skipped": "no results.csv with hint_coverage yet"}
        return
    lines = []
    for lab, p, ag, rs in loaded:
        done = [r for r in rs if r["agent"] == ag and complete(r) and bit(r.get("D_repairer")) == 1
                and (r.get("hint_coverage") or "").strip() not in ("", "None")]
        cov = [r for r in done if bit(r.get("D_coverage")) == 1]
        n_cases = len({r["vuln_id"] for r in rs if r["agent"] == ag and complete(r)})
        prefix = "" if len(loaded) == 1 else f"{lab}: "          # one set: its name goes in the title
        lines.append((f"{prefix}All positive claims", sum(1 for r in done if bit(r["V"]) == 0), len(done), INDIGO, "o", p, n_cases))
        lines.append((f"{prefix}Claims kept by the rule", sum(1 for r in cov if bit(r["V"]) == 0), len(cov), LAVENDER, "s", p, n_cases))
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.8, 0.6 * len(lines) + 1.3), layout="constrained")
        ax.set_ylim(len(lines) - 0.5, -0.5)
        for i, (lab, k, n, col, mk, p, _) in enumerate(lines):
            pv = interval(ax, i, k, n, col, mk, size=7)
            ax.text(1.035, i, f"{pv:.1%}  ({k}/{n})", ha="left", va="center", fontsize=8.5, color=DARK, transform=ax.get_yaxis_transform())
            record("fig_coverage_rule", lab, "FAR", pv, "proportion", rel(p), k, n)
        ax.set_yticks(range(len(lines)), [ln[0] for ln in lines])
        ax.set_xlim(0, 1.34)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xlabel("False assurance rate, 95% Wilson interval")
        only = loaded[0] if len(loaded) == 1 else None
        title = (f"Confirmatory hint-coverage test ({only[2].upper()}, {lines[0][6]} complete cases)" if only and only[1] == conf
                 else "Hint-coverage rule")
        ax.set_title(title, loc="left", pad=9)
        ax.text(1.035, 1.04, "Estimate (count)", ha="left", va="bottom", fontsize=8, color=GRAY, transform=ax.transAxes)
        style_axis(ax, "x")
    save(fig, "fig_coverage_rule", [s[1] for s in loaded],
         {"what": "FAR of claims and of claims that touch every hinted range (+-3 lines)",
          "missing_rows": [f"{d}: results.csv without hint_coverage (re-run fa_metrics.py of v4 on runs/final)" for d in dropped]}, rc=STYLE)


# ----------------------------------------------------------------------------- v0 paper: the five-case pilot
def fig_v0():
    """Pilot of milestone 1: oracle stage of each case (a) and VRR/FAR with Wilson intervals (b)."""
    src = ROOT / "experiments" / "v0_mvp" / "results.csv"
    rs = rows(src)
    with plt.rc_context(RC):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(170 * MM, 64 * MM), width_ratios=[1.45, 1], layout="constrained")
        cols = ["Claim\n(conf.)", "Patch\napplies", "Functional\ntests", "Exploit\ntests", "Verified\nrepair"]
        keys = [None, "apply_ok", "functional_ok", "exploit_ok", "verified_repair"]
        for i, r in enumerate(rs):
            y = len(rs) - 1 - i
            claim = bit(r["claim"]) == 1
            a1.text(0, y, f"{'YES' if claim else 'NO'} ({r['confidence_percent']}%)", ha="center", va="center", fontsize=7,
                    fontweight="bold" if claim else "normal")
            for j, k in enumerate(keys[1:], start=1):
                ran = True
                if k in ("functional_ok", "exploit_ok"):
                    ran = (r["func_pfes"] if k == "functional_ok" else r["exploit_pfes"]).strip() != ""
                if not ran:
                    a1.plot(j, y, marker="_", ms=9, mew=1.5, color=OKABE["grey"])
                    a1.text(j, y - 0.32, "not run", ha="center", va="center", fontsize=5.5, color=OKABE["grey"])
                elif bit(r[k]) == 1:
                    a1.plot(j, y, marker="o", ms=7, color=OKABE["green"], mec="black", mew=0.5)
                else:
                    a1.plot(j, y, marker="X", ms=7, color=OKABE["vermillion"], mec="black", mew=0.5)
                    if k == "exploit_ok":
                        failed = r["exploit_pfes"].split("/")[1]
                        a1.text(j, y - 0.32, f"{failed} failed", ha="center", va="center", fontsize=5.5)
        a1.set_xticks(range(len(cols)), cols)
        a1.set_yticks(range(len(rs)), [r["vuln_id"] for r in reversed(rs)])
        a1.set_xlim(-0.6, len(cols) - 0.4)
        a1.set_ylim(-0.7, len(rs) - 0.4)
        a1.tick_params(axis="x", length=0)
        a1.tick_params(axis="y", length=0)
        for side in ("left", "bottom"):
            a1.spines[side].set_visible(False)
        a1.xaxis.tick_top()
        a1.set_title("(a) Oracle stage reached by each answer", loc="left", pad=6)
        leg = [plt.Line2D([], [], ls="", marker="o", ms=6, color=OKABE["green"], mec="black", mew=0.5, label="yes"),
               plt.Line2D([], [], ls="", marker="X", ms=6, color=OKABE["vermillion"], mec="black", mew=0.5, label="no"),
               plt.Line2D([], [], ls="", marker="_", ms=8, mew=1.5, color=OKABE["grey"], label="not run")]
        a1.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3, frameon=False)
        n = len(rs)
        v = sum(bit(r["verified_repair"]) for r in rs)
        claims = [r for r in rs if bit(r["claim"]) == 1]
        fa = sum(1 for r in claims if bit(r["verified_repair"]) == 0)
        series = [("VRR", v, n, OKABE["blue"], "o"), ("FAR", fa, len(claims), OKABE["vermillion"], "s")]
        for i, (lab, k, m, col, mk) in enumerate(series):
            dotrow(a2, len(series) - 1 - i, k, m, col, mk)
        a2.set_yticks([len(series) - 1 - i for i in range(len(series))], [s[0] for s in series])
        a2.set_ylim(-0.6, len(series) - 0.4)
        a2.set_xlim(0, 1)
        a2.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        a2.set_xlabel("Proportion with 95% Wilson interval")
        a2.set_title("(b) VRR and FAR", loc="left")
        a2.grid(axis="x", lw=0.4, color="#dddddd")
        record("fig_v0_pilot", "v0 pilot", "VRR", v / n, "proportion", rel(src), v, n)
        record("fig_v0_pilot", "v0 pilot", "FAR", fa / len(claims), "proportion", rel(src), fa, len(claims))
        save(fig, "fig_v0_pilot", [src],
             {"transformations": ["VRR = verified/attempts; FAR = unverified positive claims/positive claims",
                                  "functional and exploit cells are 'not run' when the patch did not apply or was empty"],
              "uncertainty": "95% Wilson score intervals (z = 1.959964)",
              "values": {"pilot": {"n": n, "verified": v, "claims": len(claims), "false": fa}}})


if __name__ == "__main__":
    import sys
    ALL = {f.__name__: f for f in (fig_environment, fig_pilot, fig_main, fig_judges, fig_calls, fig_cost, fig_coverage, fig_v0)}
    chosen = sys.argv[1:] or list(ALL)          # e.g. `python results/figures/make_figures.py fig_v0` redraws one figure
    old_values = []
    if sys.argv[1:] and (OUT / "MANIFEST.json").exists():
        old = json.loads((OUT / "MANIFEST.json").read_text())
        MANIFEST["figures"] = old.get("figures", {})
        if (OUT / "figure_values.csv").exists():
            old_values = rows(OUT / "figure_values.csv")
    for name in chosen:
        ALL[name]()
    (OUT / "MANIFEST.json").write_text(json.dumps(MANIFEST, indent=1) + "\n")
    produced = {v["figure"] for v in VALUES}
    keep = [r for r in old_values if r["figure"] not in produced]
    with open(OUT / "figure_values.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=VALUE_FIELDS)
        w.writeheader()
        w.writerows(keep + VALUES)
    print(f"[+] {len(MANIFEST['figures'])} figures in the manifest, {len(keep) + len(VALUES)} plotted values -> {OUT}")
