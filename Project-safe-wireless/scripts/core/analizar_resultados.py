#!/usr/bin/env python3
"""Resume resultados y crea figuras reproducibles para el informe."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results" / "python_preliminary"
FIGURES = ROOT / "figures"
LABELS = {
    "RTI_Tikhonov": "Tikhonov RTI",
    "RTI_EM_Fisher_extension": "EM-Fisher extension",
    "KNN": "K-NN fingerprint baseline",
    "Centro_constante": "Constant center control",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def paired_bootstrap_difference(
    left: np.ndarray, right: np.ndarray, rng: np.random.Generator,
    repetitions: int = 20_000,
) -> tuple[float, float, float]:
    """Mean(left-right), percentile CI; same case IDs are paired."""
    difference = left - right
    indices = rng.integers(0, len(difference), size=(repetitions, len(difference)))
    means = difference[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(difference.mean()), float(low), float(high)


def align_predictions(
    predictions: list[dict[str, str]], methods: list[str], expected_cases: int,
) -> dict[str, np.ndarray]:
    """Une por ID y rechaza casos incompletos, duplicados o reales incompatibles."""
    indexed: dict[str, dict[int, float]] = {method: {} for method in methods}
    truth_by_case: dict[int, np.ndarray] = {}
    for row in predictions:
        method = row["metodo"]
        if method not in indexed:
            raise ValueError(f"Método inesperado: {method}")
        case = int(row["caso"])
        if case in indexed[method]:
            raise ValueError(f"Caso duplicado: {case}, método {method}")
        truth = np.asarray([float(row["x_real_m"]), float(row["y_real_m"])])
        error = float(row["error_m"])
        if not np.all(np.isfinite(truth)) or not np.isfinite(error) or error < 0:
            raise ValueError(f"Datos no válidos en caso {case}, método {method}")
        if case in truth_by_case and not np.allclose(truth_by_case[case], truth, rtol=0, atol=1e-9):
            raise ValueError(f"Coordenadas reales incompatibles para caso {case}")
        truth_by_case[case] = truth
        indexed[method][case] = error
    case_ids = list(range(1, expected_cases + 1))
    for method in methods:
        if set(indexed[method]) != set(case_ids):
            raise ValueError(f"IDs incompletos o inesperados en {method}; se esperan {expected_cases} casos")
    return {method: np.asarray([indexed[method][case] for case in case_ids]) for method in methods}


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    metrics = read_csv(RESULTS / "metricas.csv")
    sample = read_csv(RESULTS / "em_sample_size.csv")
    init = read_csv(RESULTS / "em_initialization.csv")
    predictions = read_csv(RESULTS / "predicciones.csv")
    parameters = json.loads((RESULTS / "parametros.json").read_text(encoding="utf-8"))

    labels = LABELS
    methods = list(labels)
    n_cases = int(parameters["test_cases"])
    by_method = align_predictions(predictions, methods, n_cases)

    # Paired bootstrap: positive difference means the right-hand method has lower error.
    rng = np.random.default_rng(parameters["seed"] + 44021)
    comparisons = [
        ("RTI_Tikhonov", "RTI_EM_Fisher_extension"),
        ("RTI_Tikhonov", "KNN"),
        ("RTI_EM_Fisher_extension", "KNN"),
        ("Centro_constante", "RTI_Tikhonov"),
        ("Centro_constante", "RTI_EM_Fisher_extension"),
        ("Centro_constante", "KNN"),
    ]
    pair_rows = []
    for baseline, candidate in comparisons:
        mean, low, high = paired_bootstrap_difference(
            by_method[baseline], by_method[candidate], rng
        )
        pair_rows.append({
            "baseline": baseline,
            "candidate": candidate,
            "mean_error_reduction_m": mean,
            "paired_bootstrap_ci95_low_m": low,
            "paired_bootstrap_ci95_high_m": high,
        })
    with (RESULTS / "comparaciones_pareadas.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_rows[0].keys())
        writer.writeheader()
        writer.writerows(pair_rows)

    # EM parameter recovery as sample size grows.
    sizes = np.asarray([int(r["n"]) for r in sample])
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.7), constrained_layout=True)
    panels = [
        ("mae_p1", "Mean absolute error: $p_1$", "Probability"),
        ("mae_sigma1_db", "Mean absolute error: $\\sigma_1$", "dB"),
        ("mae_sigma2_db", "Mean absolute error: $\\sigma_2$", "dB"),
    ]
    for ax, (column, title, ylabel) in zip(axes, panels):
        vals = np.asarray([float(r[column]) for r in sample])
        ax.plot(sizes, vals, marker="o", linewidth=2.2, color="#176B87")
        ax.set_xscale("log")
        ax.set_xlabel("Synthetic calibration sample size (log scale)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(alpha=0.25)
    fig.savefig(FIGURES / "em_parameter_recovery.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    # Point localization error and bootstrap CI from the same paired cases.
    rows = {r["metodo"]: r for r in metrics}
    methods = list(labels)
    means = np.asarray([float(rows[m]["error_medio_m"]) for m in methods])
    low = np.asarray([float(rows[m]["ic95_media_inf_m"]) for m in methods])
    high = np.asarray([float(rows[m]["ic95_media_sup_m"]) for m in methods])
    fig, ax = plt.subplots(figsize=(9.5, 4.8), constrained_layout=True)
    x = np.arange(len(methods))
    ax.bar(x, means, color=["#6C8EBF", "#3E8E7E", "#F0A35E", "#A5A5A5"], width=0.62)
    ax.errorbar(x, means, yerr=[means - low, high - means], fmt="none", ecolor="#243447", capsize=5, linewidth=1.4)
    ax.set_xticks(x, [labels[m] for m in methods], rotation=10, ha="right")
    ax.set_ylabel("Mean localization error (m)")
    ax.set_title(f"Synthetic localization: {n_cases} paired test cases (95% bootstrap CI)")
    ax.grid(axis="y", alpha=0.25)
    fig.savefig(FIGURES / "localization_mean_error.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    # Initial values and final solutions: show whether starts reach one solution.
    p_hat = np.asarray([float(r["p1_hat"]) for r in init])
    s1_hat = np.asarray([float(r["sigma1_hat_db"]) for r in init])
    s2_hat = np.asarray([float(r["sigma2_hat_db"]) for r in init])
    truth = parameters["noise_generation_parameters"]
    fig, axes = plt.subplots(1, 3, figsize=(11.6, 3.8), constrained_layout=True)
    panels = [
        (p_hat, truth["p_narrow"], "$p_1$ estimate", "Probability"),
        (s1_hat, truth["sigma_narrow_db"], "$\\sigma_1$ estimate", "dB"),
        (s2_hat, truth["sigma_wide_db"], "$\\sigma_2$ estimate", "dB"),
    ]
    start_ids = np.arange(1, len(init) + 1)
    for ax, (values, target, title, ylabel) in zip(axes, panels):
        ax.scatter(start_ids, values, color="#176B87", s=32, zorder=3)
        ax.axhline(target, color="#C75B39", linestyle="--", linewidth=1.5, label="Generating value")
        ax.set_title(title)
        ax.set_xlabel("Random start")
        ax.set_ylabel(ylabel)
        ax.set_xticks([1, 5, 10, 15, 20])
        ax.grid(alpha=0.22)
    axes[0].legend(fontsize=8)
    fig.suptitle(f"{len(init)} random EM initializations on the same n=5,000 sample", fontsize=12)
    fig.savefig(FIGURES / "em_initialization_sensitivity.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    # Compact Markdown results summary, generated directly from CSVs.
    lines = [
        "# Results summary (generated from CSVs)",
        "",
        f"All observations are synthetic. The localization comparison uses the same {n_cases} query cases for each method.",
        "Positive paired error reduction means the candidate had lower error than its baseline.",
        "",
        "## EM parameter recovery",
        "",
        "| n | Convergence rate | MAE p1 | MAE sigma1 (dB) | MAE sigma2 (dB) | Mean iterations |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sample:
        lines.append(
            f"| {row['n']} | {float(row['convergence_rate']):.0%} | {float(row['mae_p1']):.4f} | "
            f"{float(row['mae_sigma1_db']):.4f} | {float(row['mae_sigma2_db']):.4f} | {float(row['mean_iterations']):.1f} |"
        )
    converged_starts = sum(int(row["converged"]) for row in init)
    iterations = [int(row["iterations"]) for row in init]
    lines += [
        "", "## Initialization sensitivity", "",
        f"{converged_starts}/{len(init)} starting values met the stopping criterion on the same sample. Iterations ranged from {min(iterations)} to {max(iterations)}.",
        f"Final p1 estimates ranged from {p_hat.min():.6f} to {p_hat.max():.6f}. This is a repeatability check on one sample, not a guarantee of global convergence.",
    ]
    lines += ["", "## Localization", "", "| Method | Mean error (m) | 95% bootstrap CI (m) | RMSE (m) |", "|---|---:|---:|---:|"]
    for method in methods:
        r = rows[method]
        lines.append(
            f"| {labels[method]} | {float(r['error_medio_m']):.3f} | "
            f"[{float(r['ic95_media_inf_m']):.3f}, {float(r['ic95_media_sup_m']):.3f}] | {float(r['error_rmse_m']):.3f} |"
        )
    lines += ["", "## Paired differences", "", "| Baseline | Candidate | Mean error reduction (m) | Paired 95% CI (m) |", "|---|---|---:|---:|"]
    for r in pair_rows:
        lines.append(
            f"| {labels[r['baseline']]} | {labels[r['candidate']]} | {r['mean_error_reduction_m']:.3f} | "
            f"[{r['paired_bootstrap_ci95_low_m']:.3f}, {r['paired_bootstrap_ci95_high_m']:.3f}] |"
        )
    best_method = methods[int(np.argmin(means))]
    lines += [
        "",
        "## Localization utility against a control",
        "",
        f"The lowest mean error in these {n_cases} cases is obtained by {labels[best_method]} ({float(rows[best_method]['error_medio_m']):.3f} m).",
        "The constant-center control uses no RSSI observations. Pairwise differences above show whether an observation-based method improves on that control; negative reductions mean it performs worse.",
        "The Fisher extension changes the effective regularization from alpha to alpha/gamma. Its difference from fixed-alpha Tikhonov does not isolate a gain attributable to EM; alpha requires independent tuning before such a claim.",
        "",
        "## Scope note",
        "",
        "The experiment generates RSSI-like observations from an ellipsoidal linear RTI model and a two-component zero-mean Gaussian noise mixture. It does not simulate electromagnetic propagation, walls, rubble, or real Wi-Fi hardware.",
        "",
    ]
    (RESULTS / "resumen_resultados.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Figuras y resumen listos en {FIGURES} y {RESULTS}.")


if __name__ == "__main__":
    main()
