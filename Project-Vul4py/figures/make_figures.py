#!/usr/bin/env python3
"""make_figures.py -- the data figures of both papers, from the CSV/JSON files of this repository.

  python figures/make_figures.py        (from the repository root; needs matplotlib >= 3.8)

Writes figures/<name>.pdf and .png (300 dpi) and figures/MANIFEST.json, which records for every figure the
input files with their sha256, the transformations and the uncertainty shown. Rules followed:
- proportions are shown as points with 95% Wilson intervals, with n in the label; bars start at zero;
- color is never the only cue (markers and labels carry the same information; Okabe-Ito palette);
- nothing is typed by hand except two documented constants: the lab's reference run (23 attempts) and the
  number of cases that passed the scan with the public Vul4Py release (18, docs/README_multiagent.md).
Figures whose data are not in the repository yet (the confirmation run of v4, the v5 arms) are drawn
without those rows, and the manifest says which rows are missing.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "figures"
OKABE = {"black": "#000000", "orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442",
         "blue": "#0072B2", "vermillion": "#D55E00", "purple": "#CC79A7", "grey": "#7A7A7A"}
MM = 1 / 25.4
RC = {"font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
      "legend.fontsize": 7, "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
      "ps.fonttype": 42, "savefig.dpi": 300, "figure.dpi": 150}
LAB_REFERENCE = {"label": "Lab reference run (23 attempts)", "n": 23, "verified": 1, "claims": 23, "false": 22,
                 "source": "reference results distributed with the course lab (23 attempts)"}
PUBLIC_RELEASE_OK = {"value": 18, "source": "docs/README_multiagent.md: 18 cases passed the first scan with the public release"}
MANIFEST: dict = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "figures": {}}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


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


def save(fig, name: str, inputs, notes: dict):
    OUT.mkdir(exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{name}.{ext}", facecolor="white")
    plt.close(fig)
    MANIFEST["figures"][name] = {"files": [f"figures/{name}.pdf", f"figures/{name}.png"],
                                 "inputs": {str(p.relative_to(ROOT)): sha(p) for p in inputs if p.exists()},
                                 **notes}


def dotrow(ax, y, k, n, color, marker, label=None):
    p = k / n if n else math.nan
    lo, hi = wilson(k, n)
    ax.errorbar(p, y, xerr=[[p - lo], [hi - p]], fmt=marker, color=color, ms=5, capsize=2.5, lw=1.1, label=label)
    ax.text(1.02, y, f"{k}/{n}", va="center", fontsize=7, transform=ax.get_yaxis_transform())


# ----------------------------------------------------------------------------- figure 1: environment
def fig_environment():
    rounds = sorted((ROOT / "v1_environment").glob("scan_report_round*.tsv"))
    vals = [(f"R{i}", sum(1 for r in rows(p, "\t") if r.get("status") == "OK")) for i, p in enumerate(rounds)]
    oracle = len([x for x in (ROOT / "prereg" / "oracle_valid.txt").read_text().split() if x])
    data = [("Public\nrelease", PUBLIC_RELEASE_OK["value"])] + vals + [("Oracle\ncontrol", oracle)]
    with plt.rc_context(RC):
        fig, ax = plt.subplots(figsize=(160 * MM, 55 * MM), layout="constrained")
        xs = range(len(data))
        colors = [OKABE["grey"]] + [OKABE["sky"]] * len(vals) + [OKABE["green"]]
        bars = ax.bar(xs, [d[1] for d in data], color=colors, edgecolor="black", linewidth=0.5)
        for b, (_, v) in zip(bars, data):
            ax.text(b.get_x() + b.get_width() / 2, v + 1.5, str(v), ha="center", fontsize=7)
        ax.set_xticks(list(xs), [d[0] for d in data])
        ax.set_ylim(0, 110)
        ax.set_ylabel("Valid cases (of 100)")
        ax.set_xlabel("R0-R5: build rounds on the instance with the environment repairs")
        ax.set_title("Vul4Py cases that pass the scan: public release vs. environment repairs (v1)")
    save(fig, "fig_environment", rounds + [ROOT / "prereg" / "oracle_valid.txt"],
         {"what": "cases with status OK per scan round on the instance; oracle-control survivors",
          "constants": [PUBLIC_RELEASE_OK]})


# ----------------------------------------------------------------------------- figure 2: pilot-scale benchmarks
def fig_pilot():
    gb = rows(ROOT / "v3_main/gpt_benchmark/gpt_benchmark_verdicts.csv")
    pilot = rows(ROOT / "v2_pilot_tournament/results.csv")
    v0 = rows(ROOT / "v0_mvp/results.csv")
    items = []
    items.append(("v0 MVP: laguna-xs-2.1 (its own 5 cases)", sum(bit(r["verified_repair"]) for r in v0), len(v0), OKABE["grey"], "s"))
    names = {"gpt-6-luna": "GPT-6 Luna", "gpt-6.1-terra": "GPT-6.1 Terra", "gpt-6.2-astra": "GPT-6.2 Astra",
             "gpt-6.2-sol": "GPT-6.2 Sol", "gpt-6.2-sol_recortado": "GPT-6.2 Sol, trimmed context"}
    by = defaultdict(list)
    for r in gb:
        by[r["model"]].append(int(r["V"]))
    for m in ["gpt-6-luna", "gpt-6.1-terra", "gpt-6.2-astra", "gpt-6.2-sol", "gpt-6.2-sol_recortado"]:
        if m in by:
            items.append((f"GPT benchmark (Codex): {names[m]}", sum(by[m]), len(by[m]), OKABE["blue"], "o"))
    for ag, lab in (("rep_gpt-5.4-mini", "Tournament repairer: GPT-5.4 mini"), ("rep_gpt-6.2-sol", "Tournament repairer: GPT-6.2 Sol"),
                    ("c1", "Pilot C1 (jury of GPT models)"), ("c1v2", "Pilot C1 v2 (jury of other families)")):
        a = arm(pilot, ag, "D_repairer")
        items.append((lab, a["verified"], a["n"], OKABE["orange"], "D"))
    with plt.rc_context(RC):
        fig, ax = plt.subplots(figsize=(160 * MM, 78 * MM), layout="constrained")
        for i, (lab, k, n, c, mk) in enumerate(items):
            dotrow(ax, len(items) - 1 - i, k, n, c, mk)
        ax.set_yticks(range(len(items)), [it[0] for it in reversed(items)])
        ax.set_xlim(0, 1)
        ax.set_xlabel("Verified repair rate (VRR), 95% Wilson interval")
        ax.set_title("Pilot-scale comparisons, 5 cases per row")
        ax.grid(axis="x", lw=0.3, alpha=0.5)
    save(fig, "fig_pilot_benchmarks", [ROOT / "v3_main/gpt_benchmark/gpt_benchmark_verdicts.csv",
                                       ROOT / "v2_pilot_tournament/results.csv", ROOT / "v0_mvp/results.csv"],
         {"what": "VRR per model or condition on 5 cases", "uncertainty": "95% Wilson score interval; n = 5 per row"})


# ----------------------------------------------------------------------------- figure 3: main VRR and FAR
def fig_main():
    main = rows(ROOT / "v3_main/results.csv")
    v0 = rows(ROOT / "v0_mvp/results.csv")
    series = [(LAB_REFERENCE["label"], LAB_REFERENCE["verified"], LAB_REFERENCE["n"], LAB_REFERENCE["false"], LAB_REFERENCE["claims"], OKABE["grey"], "s")]
    v0c = [r for r in v0 if r["claim"] == "True"]
    series.append(("v0 MVP, laguna-xs-2.1 (5 cases)", sum(bit(r["verified_repair"]) for r in v0), len(v0),
                   sum(1 for r in v0c if r["verified_repair"] == "False"), len(v0c), OKABE["grey"], "D"))
    for ag, col, lab in (("c0", "D_repairer", "C0: repairer alone (main sample)"),
                         ("c0g", "D_repairer", "C0g: repairer + mechanical gate"),
                         ("c1", "D_unanimous", "C1: unanimous jury of other families")):
        a = arm(main, ag, col)
        series.append((lab, a["verified"], a["n"], a["false"], a["claims"], OKABE["blue"], "o"))
    missing = []
    conf = ROOT / "v4_evigate_confirmation/confirm/results.csv"
    if conf.exists():
        a = arm(rows(conf), "c0", "D_repairer")
        series.append(("C0 on 63 new cases (v4 confirmation)", a["verified"], a["n"], a["false"], a["claims"], OKABE["vermillion"], "^"))
    else:
        missing.append("v4 confirmation (v4_evigate_confirmation/confirm/results.csv)")
    v5 = ROOT / "v5_rag/results.csv"
    if v5.exists():
        r5 = rows(v5)
        for ag, lab in (("c0m", "v5: Haiku 5.5 alone"), ("c0mr", "v5: Haiku 5.5 + RAG")):
            a = arm(r5, ag, "D_repairer")
            if a["n"]:
                series.append((lab, a["verified"], a["n"], a["false"], a["claims"], OKABE["green"], "P"))
    else:
        missing.append("v5 arms (v5_rag/results.csv)")
    with plt.rc_context(RC):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(160 * MM, 70 * MM), layout="constrained", sharey=True)
        ys = list(range(len(series) - 1, -1, -1))
        for y, (lab, v, n, f, c, col, mk) in zip(ys, series):
            dotrow(a1, y, v, n, col, mk)
            if c:
                dotrow(a2, y, f, c, col, mk)
        a1.set_yticks(ys, [s[0] for s in series])
        a1.set_xlim(0, 1)
        a2.set_xlim(0, 1)
        a1.set_xlabel("VRR: verified repairs / complete attempts")
        a2.set_xlabel("FAR: unverified claims / positive claims")
        a1.set_title("Verified repair rate")
        a2.set_title("False assurance rate")
        for ax in (a1, a2):
            ax.grid(axis="x", lw=0.3, alpha=0.5)
    save(fig, "fig_main_vrr_far", [ROOT / "v3_main/results.csv", ROOT / "v0_mvp/results.csv"] + ([conf] if conf.exists() else []) + ([v5] if v5.exists() else []),
         {"what": "VRR and FAR with 95% Wilson intervals; labels give k/n", "claim_rule": "repairer's own claim (C0, C0g, v5); unanimous jury (C1, primary rule of decisiones_v3)",
          "constants": [LAB_REFERENCE], "missing_rows": missing})


# ----------------------------------------------------------------------------- figure 4: jury calibration
def fig_judges():
    s = json.loads((ROOT / "v2_pilot_tournament/judge_calibration_v2/judge_calibration_summary.json").read_text())
    u = json.loads((ROOT / "v2_pilot_tournament/judge_calibration_v2/judge_calibration_usage.json").read_text())
    models = list(s.keys())
    short = {m: m.split(":", 1)[1].replace("claude-", "Claude ").replace("deepseek-", "DeepSeek ").replace("-5-5", " 5.5") for m in models}
    with plt.rc_context(RC):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(160 * MM, 62 * MM), layout="constrained", gridspec_kw={"width_ratios": [1.5, 1]})
        metrics = [("auroc_confidence", "AUROC (confidence)", OKABE["blue"], "o"), ("sensitivity", "Sensitivity", OKABE["green"], "^"),
                   ("specificity", "Specificity", OKABE["vermillion"], "s")]
        for j, (key, lab, col, mk) in enumerate(metrics):
            a1.scatter([s[m][key] for m in models], [i + (j - 1) * 0.18 for i in range(len(models))], color=col, marker=mk, s=22, label=lab, zorder=3)
        a1.set_yticks(range(len(models)), [short[m] for m in models])
        a1.set_xlim(0.5, 1.0)
        a1.set_xlabel("Score on 28 known-truth candidates (13 correct, 15 wrong)")
        a1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False)
        a1.grid(axis="x", lw=0.3, alpha=0.5)
        a1.set_title("Juror calibration (v2)")
        costs = [u[m].get("api_equivalent_usd", u[m].get("usd")) for m in models]
        kinds = ["//" if "api_equivalent_usd" in u[m] else "" for m in models]
        bars = a2.barh(range(len(models)), costs, color=OKABE["sky"], edgecolor="black", linewidth=0.5)
        for b, h, c in zip(bars, kinds, costs):
            b.set_hatch(h)
            a2.text(c + 0.02, b.get_y() + b.get_height() / 2, f"{c:.2f}", va="center", fontsize=7)
        a2.set_yticks(range(len(models)), [""] * len(models))
        a2.set_xlim(0, max(costs) * 1.3)
        a2.set_xlabel("USD (hatched: Claude plan,\nAPI-equivalent; plain: billed)")
        a2.set_title("Cost of the 5 calls")
    save(fig, "fig_jury_calibration", [ROOT / "v2_pilot_tournament/judge_calibration_v2/judge_calibration_summary.json",
                                        ROOT / "v2_pilot_tournament/judge_calibration_v2/judge_calibration_usage.json"],
         {"what": "per-juror AUROC, sensitivity, specificity on 28 candidates; cost of 5 calls",
          "note": "point estimates; the 28 candidates come from 5 pilot cases, so the scores are not independent"})


# ----------------------------------------------------------------------------- figure 5: tokens and time per call
def fig_calls():
    calls = []
    files = sorted((ROOT / "logs/calls").glob("calls_v*.csv"))
    files = [f for f in files if "totals" not in f.name]
    for f in files:
        calls += rows(f)
    groups = defaultdict(list)
    for r in calls:
        if r["status"] != "ok":
            continue
        model = r["model"].split(":", 1)[-1]
        groups[(model, r["role"])].append(r)
    keys = sorted(groups, key=lambda k: (k[1], k[0]))
    with plt.rc_context(RC):
        fig, axes = plt.subplots(1, 3, figsize=(160 * MM, 80 * MM), layout="constrained", sharey=True)
        for ax, field, lab in zip(axes, ("input_tokens", "output_tokens", "latency_s"), ("Input tokens", "Output tokens", "Seconds")):
            data = [[max(float(r[field] or 0), 1) for r in groups[k]] for k in keys]
            ax.boxplot(data, orientation="horizontal", widths=0.6, showfliers=False, medianprops={"color": OKABE["vermillion"]})
            for i, d in enumerate(data):
                ax.scatter(d, [i + 1] * len(d), s=4, color=OKABE["blue"], alpha=0.35, zorder=3)
            ax.set_xscale("log")
            ax.set_xlabel(lab)
            ax.grid(axis="x", lw=0.3, alpha=0.5)
        axes[0].set_yticks(range(1, len(keys) + 1), [f"{m} ({role}, n={len(groups[(m, role)])})" for m, role in keys])
        versions = sorted({r["version"] for r in calls})
        fig.suptitle(f"Every recorded model call ({', '.join(versions)}), one point per call, log scale", fontsize=8.5)
    save(fig, "fig_calls_tokens_time", files, {"what": "distribution per model and role of input/output tokens and latency per call",
                                                "transform": "log10 x-axis; zero values drawn at 1; boxes without outliers, points are calls"})


# ----------------------------------------------------------------------------- figure 6: cost per verified repair
def fig_cost():
    calls = rows(ROOT / "logs/calls/calls_v3_main.csv")
    main = rows(ROOT / "v3_main/results.csv")
    cost_by_agent = defaultdict(float)
    for r in calls:
        cost_by_agent[r["agent"]] += float(r["list_cost_usd"] or 0)
    bars = []
    for ag, lab in (("c0", "C0"), ("c0g", "C0g"), ("c1", "C1")):
        a = arm(main, ag, "D_repairer")
        attempts = sum(1 for r in main if r["agent"] == ag)
        c = cost_by_agent[ag]
        bars.append((lab, c / max(attempts, 1), c / a["verified"] if a["verified"] else math.nan, a))
    v5c = ROOT / "logs/calls/calls_v5.csv"
    missing = [] if v5c.exists() else ["v5 arms (logs/calls/calls_v5.csv)"]
    with plt.rc_context(RC):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(160 * MM, 55 * MM), layout="constrained")
        xs = range(len(bars))
        for ax, idx, lab in ((a1, 1, "USD per attempted case"), (a2, 2, "USD per verified repair")):
            vals = [b[idx] for b in bars]
            bb = ax.bar(xs, vals, color=[OKABE["blue"], OKABE["sky"], OKABE["orange"]], edgecolor="black", linewidth=0.5)
            for b, v in zip(bb, vals):
                ax.text(b.get_x() + b.get_width() / 2, v * 1.02, f"{v:.3f}", ha="center", fontsize=7)
            ax.set_xticks(list(xs), [b[0] for b in bars])
            ax.set_ylabel(lab + " (list price)")
            ax.set_ylim(0, max(vals) * 1.2)
        fig.suptitle("Main sample (v3): cost at list price, all model calls of each condition", fontsize=8.5)
    save(fig, "fig_cost_per_repair", [ROOT / "logs/calls/calls_v3_main.csv", ROOT / "v3_main/results.csv"],
         {"what": "sum of list-price cost of all calls per condition / attempts and / verified repairs",
          "note": "C1 includes Claude jurors on the Claude plan priced at list-price equivalent and DeepSeek at peak prices",
          "missing_rows": missing})


# ----------------------------------------------------------------------------- figure 7: coverage rule
def fig_coverage():
    sets = [("C0 (main)", rows(ROOT / "v3_main/results.csv"), "c0"), ("C0g (main)", rows(ROOT / "v3_main/results.csv"), "c0g"),
            ("C1 (main)", rows(ROOT / "v3_main/results.csv"), "c1")]
    conf = ROOT / "v4_evigate_confirmation/confirm/results.csv"
    if conf.exists():
        sets.append(("C0, 63 new cases (confirmatory)", rows(conf), "c0"))
    # hint_coverage and D_coverage exist only in results written by fa_metrics.py of v4 or later
    dropped = [s[0] for s in sets if not any((r.get("hint_coverage") or "").strip() not in ("", "None") for r in s[1])]
    sets = [s for s in sets if s[0] not in dropped]
    if not sets:
        MANIFEST["figures"]["fig_coverage_rule"] = {"skipped": "no results.csv with hint_coverage yet (re-run fa_metrics.py "
                                                               "of v4 on runs/final and add the confirmation run)"}
        return
    with plt.rc_context(RC):
        fig, ax = plt.subplots(figsize=(160 * MM, 50 * MM), layout="constrained")
        for i, (lab, rs, ag) in enumerate(sets):
            y = len(sets) - 1 - i
            done = [r for r in rs if r["agent"] == ag and complete(r) and bit(r.get("D_repairer")) == 1
                    and (r.get("hint_coverage") or "").strip() not in ("", "None")]
            f0 = sum(1 for r in done if bit(r["V"]) == 0)
            cov = [r for r in done if bit(r.get("D_coverage")) == 1]
            f1 = sum(1 for r in cov if bit(r["V"]) == 0)
            for k, n, col, mk, dy in ((f0, len(done), OKABE["blue"], "o", 0.12), (f1, len(cov), OKABE["vermillion"], "s", -0.12)):
                p = k / n
                lo, hi = wilson(k, n)
                ax.errorbar(p, y + dy, xerr=[[p - lo], [hi - p]], fmt=mk, color=col, ms=5, capsize=2.5, lw=1.1)
            ax.text(1.02, y, f"{f0}/{len(done)} -> {f1}/{len(cov)}", va="center", fontsize=7, transform=ax.get_yaxis_transform())
        ax.set_yticks(range(len(sets)), [s[0] for s in reversed(sets)])
        ax.set_ylim(-0.6, len(sets) - 0.4)
        ax.set_xlim(0, 1)
        ax.set_xlabel("False assurance rate with 95% Wilson interval")
        ax.legend(handles=[plt.Line2D([], [], ls="", marker="o", color=OKABE["blue"], label="all positive claims of the repairer"),
                           plt.Line2D([], [], ls="", marker="s", color=OKABE["vermillion"], label="claims kept by the hint-coverage rule")],
                  loc="upper left", frameon=False)
        ax.grid(axis="x", lw=0.3, alpha=0.5)
    save(fig, "fig_coverage_rule", [ROOT / "v3_main/results.csv"] + ([conf] if conf.exists() else []),
         {"what": "FAR of claims and of claims that touch every hinted range (+-3 lines)",
          "missing_rows": ([] if conf.exists() else ["v4 confirmation"]) + [f"{d}: results.csv without hint_coverage "
                                                                            "(re-run fa_metrics.py of v4 on runs/final)" for d in dropped]})


# ----------------------------------------------------------------------------- v0 paper: the five-case pilot
def fig_v0():
    """Pilot of milestone 1: oracle stage of each case (a) and VRR/FAR with Wilson intervals (b)."""
    src = ROOT / "v0_mvp" / "results.csv"
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
        L = LAB_REFERENCE
        series = [("VRR, pilot", v, n, OKABE["blue"], "o"), ("VRR, lab reference", L["verified"], L["n"], OKABE["grey"], "s"),
                  ("FAR, pilot", fa, len(claims), OKABE["blue"], "o"), ("FAR, lab reference", L["false"], L["claims"], OKABE["grey"], "s")]
        for i, (lab, k, m, col, mk) in enumerate(series):
            dotrow(a2, len(series) - 1 - i - (0.4 if i >= 2 else 0), k, m, col, mk)
        a2.set_yticks([len(series) - 1 - i - (0.4 if i >= 2 else 0) for i in range(len(series))], [s[0] for s in series])
        a2.set_xlim(0, 1)
        a2.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        a2.set_xlabel("Proportion with 95% Wilson interval")
        a2.set_title("(b) VRR and FAR", loc="left")
        a2.grid(axis="x", lw=0.4, color="#dddddd")
        save(fig, "fig_v0_pilot", [src],
             {"transformations": ["VRR = verified/attempts; FAR = unverified positive claims/positive claims",
                                  "functional and exploit cells are 'not run' when the patch did not apply or was empty"],
              "uncertainty": "95% Wilson score intervals (z = 1.959964)",
              "constants": {"lab_reference": LAB_REFERENCE},
              "values": {"pilot": {"n": n, "verified": v, "claims": len(claims), "false": fa}}})


if __name__ == "__main__":
    import sys
    ALL = {f.__name__: f for f in (fig_environment, fig_pilot, fig_main, fig_judges, fig_calls, fig_cost, fig_coverage, fig_v0)}
    chosen = sys.argv[1:] or list(ALL)          # e.g. `python figures/make_figures.py fig_v0` redraws one figure
    if sys.argv[1:] and (OUT / "MANIFEST.json").exists():
        old = json.loads((OUT / "MANIFEST.json").read_text())
        MANIFEST["figures"] = old.get("figures", {})
    for name in chosen:
        ALL[name]()
    (OUT / "MANIFEST.json").write_text(json.dumps(MANIFEST, indent=1) + "\n")
    print(f"[+] {len(MANIFEST['figures'])} figures in the manifest -> {OUT}")
