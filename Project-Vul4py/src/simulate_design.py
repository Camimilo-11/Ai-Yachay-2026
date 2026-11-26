#!/usr/bin/env python3
"""
simulate_design.py

Monte Carlo comparison of pipeline designs for the false-assurance experiment.
This is a PLANNING simulation: no model is called. Every number it produces
follows from the assumptions below, which are stated so they can be replaced
by pilot estimates.

Generative model for one case i
-------------------------------
u_i ~ N(0,1)        how convincing a wrong patch looks (shared by every LLM judge)
V_i ~ Bern(p_rep)   the repairer's patch is verified by Vul4Py
Repairer claim:     V=1 -> claims success w.p. 0.95
                    V=0 -> claims success w.p. c0 (MVP: 3 of 4 wrong patches claimed),
                           correlated with u_i through rho
Repairer confidence: constant (MVP: 0.95 on every claim) -> carries no information
Judge j score:      s_ij = d * V_i + sqrt(rho) * u_i + sqrt(1 - rho) * e_ij,  e ~ N(0,1)
                    d   = discrimination (AUROC = Phi(d / sqrt 2))
                    rho = error correlation between LLMs (shared blind spots)
Judge claim:        s > d/2 - lenience          Judge confidence: Phi(s - d/2)
Revision round:     if the judge rejects, the repairer revises once with the critique:
                    wrong -> verified w.p. r_fix; verified -> broken w.p. r_break;
                    the judge re-reviews (deceptiveness partly persists, kappa) and may
                    be swayed toward accepting a patch that "addressed its comments" (sway)

Designs: single (B), judge (A+B+C), consensus (B and C), gate tau (C and conf >= tau),
revise (B<->C one round, C decides), jury3 majority / unanimous, and the role swap
(strong model as judge instead of repairer).

Outputs (JSON + CSV in --out): expected VRR, FAR, coverage, safe yield = P(accepted and
verified), cost in calls per case, sensitivity grid, power of the paired comparison, and
the optimism of choosing tau on the evaluation cases.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import binom, norm

RNG = np.random.default_rng(20261108)


# ---------------------------------------------------------------- generative model

def simulate(n, p_rep, d_judge, rho, c0=0.75, lenience=0.0, n_judges=3,
             r_fix=0.25, r_break=0.10, kappa=0.5, sway=0.3, rng=RNG):
    """Draw n cases; return a dict of arrays used by every design."""
    u = rng.standard_normal(n)
    V = rng.random(n) < p_rep
    # repairer claim, correlated with u for wrong patches
    zb = math.sqrt(rho) * u + math.sqrt(1 - rho) * rng.standard_normal(n)
    CB = np.where(V, rng.random(n) < 0.95, zb > norm.ppf(1 - c0))
    # judges (first one is "the" reviewer C)
    e = rng.standard_normal((n_judges, n))
    S = d_judge * V + math.sqrt(rho) * u + math.sqrt(1 - rho) * e
    thr = d_judge / 2 - lenience
    CJ = S > thr
    PJ = norm.cdf(S - d_judge / 2)
    # one revision round; the patch after revision is drawn for every case and used only
    # where a design's trigger fires (judge 0 rejects, or the jury is not unanimous)
    rej = ~CJ[0]
    up = rng.random(n) < r_fix
    dn = rng.random(n) < r_break
    V2 = np.where(V, ~dn, up)
    u2 = kappa * u + math.sqrt(1 - kappa ** 2) * rng.standard_normal(n)
    S2 = (d_judge * V2 + math.sqrt(rho) * u2
          + math.sqrt(1 - rho) * rng.standard_normal((n_judges, n)) + sway)
    CJ2 = S2 > thr
    PJ2 = norm.cdf(S2 - d_judge / 2)
    return dict(V=V, CB=CB, S=S, CJ=CJ, PJ=PJ, rej=rej, V2=V2, CJ2=CJ2, PJ2=PJ2)


def designs(sim, taus=(0.7, 0.8, 0.9)):
    """Acceptance decision D and the verified indicator each design is judged on."""
    V, CB, CJ, PJ = sim["V"], sim["CB"], sim["CJ"], sim["PJ"]
    rej, V2, CJ2 = sim["rej"], sim["V2"], sim["CJ2"]
    out = {
        "single (B)": (CB, V, 1.0),
        "judge (A+B+C)": (CJ[0], V, 3.0),
        "consensus (B and C)": (CB & CJ[0], V, 3.0),
    }
    for t in taus:
        out[f"gate tau={t}"] = (CJ[0] & (PJ[0] >= t), V, 3.0)
    # revision: accepted at first review, or revised and accepted at second review
    D_rev = np.where(rej, CJ2[0], CJ[0])
    V_rev = np.where(rej, V2, V)
    cost_rev = 3.0 + 2.0 * rej.mean()
    out["revise (1 round)"] = (D_rev, V_rev, cost_rev)
    out["revise + consensus"] = (D_rev & np.where(rej, True, CB), V_rev, cost_rev)
    votes = CJ.sum(axis=0)
    out["jury3 majority"] = (votes >= 2, V, 5.0)
    out["jury3 unanimous"] = (votes == 3, V, 5.0)
    # composites: revise first, then a stricter final acceptance on the final patch
    PJf = np.where(rej, sim["PJ2"][0], PJ[0])
    out["revise + gate tau=0.8"] = (D_rev & (PJf >= 0.8), V_rev, cost_rev)
    votes_f = np.where(rej, sim["CJ2"].sum(axis=0), votes)
    out["revise + jury3 majority"] = (votes_f >= 2, V_rev, cost_rev + 2.0 + 2.0 * rej.mean())
    # jury-driven revision: revise unless all three judges accept; final rule on the new votes
    trig = votes < 3
    V_j = np.where(trig, V2, V)
    votes_j = np.where(trig, sim["CJ2"].sum(axis=0), votes)
    cost_j = 5.0 + 4.0 * trig.mean()
    out["jury-revise, majority"] = (votes_j >= 2, V_j, cost_j)
    out["jury-revise, unanimous"] = (votes_j == 3, V_j, cost_j)
    return out


def metrics(D, V, cost):
    D = D.astype(bool)
    V = V.astype(bool)
    n = len(D)
    acc = D.sum()
    fa = (D & ~V).sum()
    return {
        "VRR": V.mean(),
        "coverage": acc / n,
        "FAR": fa / acc if acc else float("nan"),
        "safe_yield": (D & V).sum() / n,
        "missed_repairs": (V & ~D).sum() / max(V.sum(), 1),
        "calls_per_case": cost,
    }


# ---------------------------------------------------------------- experiments

BASE = dict(p_rep=0.35, d_judge=1.0, rho=0.3)   # strong repairer, average judge
STRONG_D, WEAK_D = 1.5, 0.75                      # judge discrimination (AUROC ~0.86 / ~0.70)
STRONG_P, WEAK_P = 0.35, 0.20                     # repairer verified rate (MVP: 1/5)


def expected(n=400_000, **kw):
    sim = simulate(n, **kw)
    return {k: metrics(*v) for k, v in designs(sim).items()}


def sensitivity(n=200_000):
    rows = []
    for d in (0.5, 1.0, 1.5, 2.0):
        for rho in (0.0, 0.3, 0.6):
            for p in (WEAK_P, STRONG_P):
                res = expected(n, p_rep=p, d_judge=d, rho=rho)
                for name, m in res.items():
                    rows.append({"d_judge": d, "AUROC": round(norm.cdf(d / math.sqrt(2)), 3),
                                 "rho": rho, "p_rep": p, "design": name, **m})
    return rows


def role_swap(n=400_000):
    """Strong model as repairer + weak judge vs weak repairer + strong judge."""
    out = {}
    for label, p, d in (("strong repairer, weak judge", STRONG_P, WEAK_D),
                        ("weak repairer, strong judge", WEAK_P, STRONG_D)):
        res = expected(n, p_rep=p, d_judge=d, rho=0.3)
        out[label] = {k: res[k] for k in ("single (B)", "judge (A+B+C)", "gate tau=0.8",
                                          "revise (1 round)", "jury3 majority",
                                          "jury-revise, majority", "jury-revise, unanimous")}
    return out


def mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * binom.cdf(min(b, c), n, 0.5))


def power(design="revise (1 round)", ns=(10, 20, 30, 50, 100), reps=4000, alpha=0.05, **kw):
    """Power of an exact McNemar test on per-case false assurance, baseline vs design,
    both applied to the same cases (paired)."""
    kw = {**BASE, **kw}
    res = {}
    for n in ns:
        hits = 0
        for _ in range(reps):
            sim = simulate(n, **kw)
            ds = designs(sim)
            D0, V0, _ = ds["single (B)"]
            D1, V1, _ = ds[design]
            fa0 = D0 & ~V0
            fa1 = D1 & ~V1
            b = int((fa0 & ~fa1).sum())
            c = int((~fa0 & fa1).sum())
            hits += mcnemar_p(b, c) < alpha
        res[n] = hits / reps
    return res


def far_ci_halfwidth(far=0.4, coverage=0.5, ns=(10, 20, 30, 50, 100)):
    """Expected Wilson 95% half-width of FAR when N cases give N*coverage accepted claims."""
    out = {}
    z = 1.959964
    for n in ns:
        k = max(1, round(n * coverage))
        p = far
        d = 1 + z * z / k
        h = z * math.sqrt(p * (1 - p) / k + z * z / (4 * k * k)) / d
        out[n] = h
    return out


def tau_optimism(n_eval=30, reps=3000, grid=np.round(np.arange(0.5, 0.96, 0.05), 2), **kw):
    """Choose tau on the SAME cases (minimise FA count, keep >= 1 acceptance) vs
    fix it on a separate pilot of 10 cases; report FAR on fresh test cases."""
    kw = {**BASE, **kw}
    in_sample, pilot_chosen, test_far_in, test_far_pilot = [], [], [], []
    for _ in range(reps):
        ev = simulate(n_eval, **kw)
        pil = simulate(10, **kw)
        test = simulate(2000, **kw)

        def pick(sim):
            best, best_score = grid[0], -1e9
            for t in grid:
                D = sim["CJ"][0] & (sim["PJ"][0] >= t)
                if D.sum() == 0:
                    continue
                score = (D & sim["V"]).sum() - 2 * (D & ~sim["V"]).sum()
                if score > best_score:
                    best, best_score = t, score
            return best

        def far(sim, t):
            D = sim["CJ"][0] & (sim["PJ"][0] >= t)
            return (D & ~sim["V"]).sum() / D.sum() if D.sum() else np.nan

        t_in, t_pil = pick(ev), pick(pil)
        in_sample.append(far(ev, t_in))
        test_far_in.append(far(test, t_in))
        test_far_pilot.append(far(test, t_pil))
        pilot_chosen.append(t_pil)
    return {"reported_FAR_when_tau_tuned_on_eval": float(np.nanmean(in_sample)),
            "true_FAR_of_that_tau": float(np.nanmean(test_far_in)),
            "true_FAR_tau_from_pilot": float(np.nanmean(test_far_pilot))}


def auroc_curve(n=200_000, ds=np.round(np.arange(0.25, 2.51, 0.25), 2),
                keep=("single (B)", "judge (A+B+C)", "gate tau=0.8", "jury3 majority",
                      "revise (1 round)", "revise + gate tau=0.8", "jury-revise, majority",
                      "jury-revise, unanimous")):
    rows = []
    for d in ds:
        res = expected(n, p_rep=BASE["p_rep"], d_judge=float(d), rho=BASE["rho"])
        for k in keep:
            rows.append({"AUROC": round(float(norm.cdf(d / math.sqrt(2))), 3), "design": k,
                         "FAR": res[k]["FAR"], "safe_yield": res[k]["safe_yield"]})
    return rows


def sway_sensitivity(n=200_000):
    out = {}
    for sw in (0.0, 0.3, 0.6):
        res = expected(n, **BASE, sway=sw)
        out[sw] = {k: res[k] for k in ("revise (1 round)", "revise + gate tau=0.8",
                                       "jury-revise, majority", "jury-revise, unanimous")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("sim_out"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    base = expected(**BASE)
    sens = sensitivity()
    swap = role_swap()
    pw = {d: power(design=d) for d in ("judge (A+B+C)", "gate tau=0.8", "jury3 majority",
                                       "revise (1 round)", "revise + gate tau=0.8",
                                       "jury-revise, majority", "jury-revise, unanimous")}
    curve = auroc_curve()
    sway = sway_sensitivity()
    ci = far_ci_halfwidth()
    opt = tau_optimism()

    with open(a.out / "sensitivity.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sens[0]))
        w.writeheader()
        w.writerows(sens)
    summary = {"assumptions": {**BASE, "c0": 0.75, "r_fix": 0.25, "r_break": 0.10, "kappa": 0.5,
                               "sway": 0.3, "lenience": 0.0, "strong_d": STRONG_D, "weak_d": WEAK_D,
                               "strong_p": STRONG_P, "weak_p": WEAK_P},
               "base": base, "role_swap": swap, "power_vs_single": pw,
               "far_ci_halfwidth": ci, "tau_optimism": opt, "auroc_curve": curve,
               "sway_sensitivity": sway}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    print("BASE (p_rep=0.35, AUROC judge=%.2f, rho=0.3)" % norm.cdf(1 / math.sqrt(2)))
    print(f"{'design':24s} {'VRR':>6s} {'cover':>6s} {'FAR':>6s} {'safe':>6s} {'missed':>7s} {'calls':>6s}")
    for k, m in base.items():
        print(f"{k:24s} {m['VRR']:6.3f} {m['coverage']:6.3f} {m['FAR']:6.3f} {m['safe_yield']:6.3f} "
              f"{m['missed_repairs']:7.3f} {m['calls_per_case']:6.2f}")
    print("\nROLE SWAP")
    for lab, res in swap.items():
        for k, m in res.items():
            print(f"{lab:28s} {k:20s} VRR={m['VRR']:.3f} FAR={m['FAR']:.3f} safe={m['safe_yield']:.3f}")
    print("\nPOWER (exact McNemar, alpha .05) vs single:", json.dumps(pw, indent=1))
    print("FAR CI half-width:", {k: round(v, 3) for k, v in ci.items()})
    print("tau optimism:", opt)


if __name__ == "__main__":
    main()
