#!/usr/bin/env python3
"""Prototipo sintético: RTI con calibración EM frente a K-NN.

Flujo del prototipo
-------------------
1. Crea una cuadrícula y nodos de radio en el perímetro.
2. Calcula la matriz elíptica W de RTI.
3. Genera una muestra de ruido sintético de dos gaussianas y estima sus
   parámetros con el EM C++17 de em.cpp mediante el adaptador em_cpp.py.
4. Genera huellas sintéticas, reconstruye imágenes con RTI y estima la
   posición con K-NN para comparar el error y el tiempo.

Este programa NO simula propagación electromagnética ni es una simulación
validada de Wi-Fi a través de escombros. Las mediciones son sintéticas y usan
el modelo lineal y el modelo de ruido descritos en las referencias.

Dependencias: numpy, matplotlib

Ejemplo:
    python simulacion_rti_em_knn.py
    python simulacion_rti_em_knn.py --grid-size 20 --nodes 16 --test-cases 500 --seed 8

Referencias de implementación:
- Wilson & Patwari, Radio Tomographic Imaging with Wireless Networks (2010):
  https://span.ece.utah.edu/uploads/RTI_version_3.pdf
- Wilson & Patwari, Through-Wall Motion Tracking Using Variance-Based RTI:
  https://arxiv.org/abs/0909.5417
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from em_cpp import backend_executable, backend_metadata, fit_zero_mean_gmm_em


def validate_args(args: argparse.Namespace) -> None:
    if args.grid_size < 4:
        raise ValueError("--grid-size debe ser al menos 4.")
    if args.nodes < 4:
        raise ValueError("--nodes debe ser al menos 4.")
    if args.room_m <= 0 or args.ellipse_width_m < 0 or args.alpha <= 0:
        raise ValueError("room-m y alpha deben ser positivos; ellipse-width-m no puede ser negativo.")
    if not 0.0 <= args.link_loss < 1.0:
        raise ValueError("--link-loss debe estar entre 0 y 1.")
    if not 0.0 < args.p_narrow < 1.0:
        raise ValueError("--p-narrow debe estar entre 0 y 1.")
    if args.sigma_narrow_db <= 0 or args.sigma_wide_db <= args.sigma_narrow_db:
        raise ValueError("Se requiere 0 < sigma-narrow-db < sigma-wide-db.")
    if args.sigma_floor <= 0 or args.em_tolerance <= 0:
        raise ValueError("--sigma-floor y --em-tolerance deben ser positivos.")
    if args.target_attenuation_db <= 0:
        raise ValueError("--target-attenuation-db debe ser positivo.")
    if args.train_per_cell < 1 or args.test_cases < 1 or args.calibration_samples < 100:
        raise ValueError("Aumenta train-per-cell, test-cases y calibration-samples.")
    if args.knn_k < 1 or args.em_iterations < 1 or args.em_replicates < 1:
        raise ValueError("knn-k, em-iterations y em-replicates deben ser positivos.")


def perimeter_nodes(count: int, side_m: float) -> np.ndarray:
    """Ubica nodos a intervalos regulares sobre el perímetro de un cuadrado."""
    perimeter = 4.0 * side_m
    distances = np.linspace(0.0, perimeter, count, endpoint=False)
    nodes = np.empty((count, 2), dtype=float)
    for i, distance in enumerate(distances):
        if distance < side_m:
            nodes[i] = (distance, 0.0)
        elif distance < 2.0 * side_m:
            nodes[i] = (side_m, distance - side_m)
        elif distance < 3.0 * side_m:
            nodes[i] = (3.0 * side_m - distance, side_m)
        else:
            nodes[i] = (0.0, 4.0 * side_m - distance)
    return nodes


def grid_centers(grid_size: int, side_m: float) -> np.ndarray:
    step = side_m / grid_size
    axis = (np.arange(grid_size, dtype=float) + 0.5) * step
    xx, yy = np.meshgrid(axis, axis)
    return np.column_stack((xx.ravel(), yy.ravel()))


def make_links(nodes: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devuelve pares de nodos y sus extremos, usando cada enlace una vez."""
    pairs = np.array([(a, b) for a in range(len(nodes)) for b in range(a + 1, len(nodes))])
    return pairs, nodes[pairs[:, 0]], nodes[pairs[:, 1]]


def elliptical_weights(
    links_a: np.ndarray,
    links_b: np.ndarray,
    pixels: np.ndarray,
    ellipse_width_m: float,
) -> np.ndarray:
    """Matriz W: 1/sqrt(longitud del enlace) dentro de su elipse."""
    link_lengths = np.linalg.norm(links_a - links_b, axis=1)
    dist_a = np.linalg.norm(links_a[:, None, :] - pixels[None, :, :], axis=2)
    dist_b = np.linalg.norm(links_b[:, None, :] - pixels[None, :, :], axis=2)
    inside = (dist_a + dist_b) < (link_lengths[:, None] + ellipse_width_m)
    return inside.astype(float) / np.sqrt(np.maximum(link_lengths[:, None], 1e-12))


def smoothness_laplacian(grid_size: int) -> np.ndarray:
    """Forma D_x.T D_x + D_y.T D_y para diferencias entre píxeles vecinos."""
    count = grid_size * grid_size
    laplacian = np.zeros((count, count), dtype=float)
    for row in range(grid_size):
        for col in range(grid_size):
            current = row * grid_size + col
            for nr, nc in ((row + 1, col), (row, col + 1)):
                if nr < grid_size and nc < grid_size:
                    neighbor = nr * grid_size + nc
                    laplacian[current, current] += 1.0
                    laplacian[neighbor, neighbor] += 1.0
                    laplacian[current, neighbor] -= 1.0
                    laplacian[neighbor, current] -= 1.0
    return laplacian


def draw_mixture_noise(
    rng: np.random.Generator,
    count: int,
    p_narrow: float,
    sigma_narrow: float,
    sigma_wide: float,
) -> np.ndarray:
    narrow = rng.random(count) < p_narrow
    scales = np.where(narrow, sigma_narrow, sigma_wide)
    return rng.normal(loc=0.0, scale=scales, size=count)


def gmm_log_likelihood(
    samples: np.ndarray, p_narrow: float, sigma_narrow: float, sigma_wide: float
) -> float:
    """Log-verosimilitud de una mezcla gaussiana centrada en cero."""
    values = np.asarray(samples, dtype=float)
    log_a = math.log(p_narrow) - math.log(sigma_narrow) - 0.5 * math.log(2.0 * math.pi) - values**2 / (2.0 * sigma_narrow**2)
    log_b = math.log(1.0 - p_narrow) - math.log(sigma_wide) - 0.5 * math.log(2.0 * math.pi) - values**2 / (2.0 * sigma_wide**2)
    max_log = np.maximum(log_a, log_b)
    return float(np.sum(max_log + np.log(np.exp(log_a - max_log) + np.exp(log_b - max_log))))


def write_em_diagnostics(args: argparse.Namespace, output_dir: Path) -> None:
    """Mide recuperación de parámetros, convergencia y sensibilidad a inicialización."""
    rng = np.random.default_rng(args.seed + 100_003)
    sample_path = output_dir / "em_sample_size.csv"
    sizes = (100, 500, 1000, 5000, 10000)
    with sample_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "n", "replicas", "convergence_rate", "mae_p1", "mae_sigma1_db",
            "mae_sigma2_db", "mean_iterations", "mean_loglik_per_sample",
            "mean_runtime_ms",
        ))
        writer.writeheader()
        for n in sizes:
            errors_p, errors_s1, errors_s2, iters, lls, times = [], [], [], [], [], []
            converged = 0
            for _ in range(args.em_replicates):
                samples = draw_mixture_noise(
                    rng, n, args.p_narrow, args.sigma_narrow_db, args.sigma_wide_db
                )
                spread = max(float(np.std(samples)), args.sigma_floor * 2.0)
                p0 = float(rng.uniform(0.15, 0.85))
                s10 = max(args.sigma_floor, spread * float(rng.uniform(0.20, 0.95)))
                s20 = max(s10 * 1.10, spread * float(rng.uniform(1.0, 2.8)))
                started = time.perf_counter()
                p, s1, s2, steps, did_converge = fit_zero_mean_gmm_em(
                    samples, args.em_iterations, tolerance=args.em_tolerance, p_initial=p0,
                    sigma_narrow_initial=s10, sigma_wide_initial=s20,
                    sigma_floor=args.sigma_floor,
                )
                times.append(1000.0 * (time.perf_counter() - started))
                errors_p.append(abs(p - args.p_narrow))
                errors_s1.append(abs(s1 - args.sigma_narrow_db))
                errors_s2.append(abs(s2 - args.sigma_wide_db))
                iters.append(steps)
                lls.append(gmm_log_likelihood(samples, p, s1, s2) / n)
                converged += int(did_converge)
            writer.writerow({
                "n": n,
                "replicas": args.em_replicates,
                "convergence_rate": converged / args.em_replicates,
                "mae_p1": float(np.mean(errors_p)),
                "mae_sigma1_db": float(np.mean(errors_s1)),
                "mae_sigma2_db": float(np.mean(errors_s2)),
                "mean_iterations": float(np.mean(iters)),
                "mean_loglik_per_sample": float(np.mean(lls)),
                "mean_runtime_ms": float(np.mean(times)),
            })

    init_samples = draw_mixture_noise(
        rng, 5000, args.p_narrow, args.sigma_narrow_db, args.sigma_wide_db
    )
    spread = max(float(np.std(init_samples)), args.sigma_floor * 2.0)
    init_path = output_dir / "em_initialization.csv"
    with init_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "start", "p0", "sigma1_0_db", "sigma2_0_db", "p1_hat",
            "sigma1_hat_db", "sigma2_hat_db", "iterations", "converged",
            "loglik_per_sample", "floor_hits", "runtime_ms",
        ))
        writer.writeheader()
        for start in range(1, 21):
            p0 = float(rng.uniform(0.10, 0.90))
            s10 = max(args.sigma_floor, spread * float(rng.uniform(0.15, 1.15)))
            s20 = max(s10 * 1.10, spread * float(rng.uniform(0.80, 3.0)))
            started = time.perf_counter()
            p, s1, s2, steps, did_converge = fit_zero_mean_gmm_em(
                init_samples, args.em_iterations, tolerance=args.em_tolerance, p_initial=p0,
                sigma_narrow_initial=s10, sigma_wide_initial=s20,
                sigma_floor=args.sigma_floor,
            )
            writer.writerow({
                "start": start, "p0": p0, "sigma1_0_db": s10,
                "sigma2_0_db": s20, "p1_hat": p, "sigma1_hat_db": s1,
                "sigma2_hat_db": s2, "iterations": steps,
                "converged": int(did_converge),
                "loglik_per_sample": gmm_log_likelihood(init_samples, p, s1, s2) / len(init_samples),
                "floor_hits": int(s1 <= args.sigma_floor * 1.000001 or s2 <= args.sigma_floor * 1.000001),
                "runtime_ms": 1000.0 * (time.perf_counter() - started),
            })


def bootstrap_mean_ci(
    values: np.ndarray, rng: np.random.Generator, repetitions: int = 2000
) -> tuple[float, float]:
    """IC percentil 95% bootstrap para la media de errores por caso."""
    values = np.asarray(values, dtype=float)
    draws = rng.integers(0, values.size, size=(repetitions, values.size))
    means = np.mean(values[draws], axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def fisher_information_gamma(
    p_narrow: float,
    sigma_narrow: float,
    sigma_wide: float,
) -> float:
    """Calcula gamma = integral (f'(u)^2 / f(u)) du para la mezcla GMM."""
    limit = 10.0 * sigma_wide
    samples = np.linspace(-limit, limit, 40_001)
    narrow_pdf = np.exp(-0.5 * (samples / sigma_narrow) ** 2) / (
        math.sqrt(2.0 * math.pi) * sigma_narrow
    )
    wide_pdf = np.exp(-0.5 * (samples / sigma_wide) ** 2) / (
        math.sqrt(2.0 * math.pi) * sigma_wide
    )
    density = p_narrow * narrow_pdf + (1.0 - p_narrow) * wide_pdf
    derivative = (
        p_narrow * (-samples / sigma_narrow**2) * narrow_pdf
        + (1.0 - p_narrow) * (-samples / sigma_wide**2) * wide_pdf
    )
    integrand = derivative**2 / np.maximum(density, 1e-300)
    return float(np.sum(integrand) * (samples[1] - samples[0]))


def build_reconstruction_operator(
    weights: np.ndarray,
    laplacian: np.ndarray,
    alpha: float,
    gamma: float,
) -> np.ndarray:
    """Precalcula Pi para que cada consulta requiera solo una multiplicación."""
    matrix = gamma * (weights.T @ weights) + alpha * laplacian
    matrix.flat[:: matrix.shape[0] + 1] += 1e-8
    rhs = gamma * weights.T
    return np.linalg.solve(matrix, rhs)


def apply_smoothness(image: np.ndarray, grid_size: int) -> np.ndarray:
    """Aplica D_x.T D_x + D_y.T D_y sin construir una matriz densa."""
    field = image.reshape(grid_size, grid_size)
    result = np.zeros_like(field)
    horizontal = field[:, :-1] - field[:, 1:]
    result[:, :-1] += horizontal
    result[:, 1:] -= horizontal
    vertical = field[:-1, :] - field[1:, :]
    result[:-1, :] += vertical
    result[1:, :] -= vertical
    return result.ravel()


def solve_conjugate_gradient(
    weights: np.ndarray,
    observations: np.ndarray,
    grid_size: int,
    alpha: float,
    gamma: float,
    max_iterations: int = 400,
    tolerance: float = 1e-6,
) -> np.ndarray:
    """Resuelve el sistema RTI con productos matriciales, útil para grillas grandes."""
    pixel_count = grid_size * grid_size
    rhs = gamma * (weights.T @ observations)
    degree = np.zeros((grid_size, grid_size), dtype=float)
    degree[:, :-1] += 1.0
    degree[:, 1:] += 1.0
    degree[:-1, :] += 1.0
    degree[1:, :] += 1.0
    diagonal = gamma * np.sum(weights**2, axis=0) + alpha * degree.ravel() + 1e-8

    def matvec(vector: np.ndarray) -> np.ndarray:
        return (
            gamma * (weights.T @ (weights @ vector))
            + alpha * apply_smoothness(vector, grid_size)
            + 1e-8 * vector
        )

    estimate = np.zeros(pixel_count, dtype=float)
    residual = rhs.copy()
    preconditioned = residual / diagonal
    direction = preconditioned.copy()
    residual_product = float(residual @ preconditioned)
    rhs_norm = max(float(np.linalg.norm(rhs)), 1e-12)

    for _ in range(max_iterations):
        product = matvec(direction)
        denominator = float(direction @ product)
        if denominator <= 1e-20:
            break
        step = residual_product / denominator
        estimate += step * direction
        residual -= step * product
        if np.linalg.norm(residual) / rhs_norm <= tolerance:
            break
        preconditioned = residual / diagonal
        next_product = float(residual @ preconditioned)
        direction = preconditioned + (next_product / max(residual_product, 1e-20)) * direction
        residual_product = next_product

    return np.maximum(estimate, 0.0)


def reconstruct_image(
    operator: np.ndarray | None,
    weights: np.ndarray,
    observations: np.ndarray,
    grid_size: int,
    alpha: float,
    gamma: float,
) -> np.ndarray:
    """Aplica Pi precalculada o CG si la grilla es demasiado grande para una inversa densa."""
    if operator is not None:
        return np.maximum(operator @ observations, 0.0)
    return solve_conjugate_gradient(weights, observations, grid_size, alpha, gamma)


def nearest_neighbor_prediction(
    train_features: np.ndarray,
    train_positions: np.ndarray,
    query: np.ndarray,
    valid_links: np.ndarray,
    k: int,
) -> np.ndarray:
    features = train_features[:, valid_links]
    observed = query[valid_links]
    # Una escala común a todos los enlaces se cancela al normalizar los pesos.
    distances = np.linalg.norm(features - observed, axis=1)
    nearest = np.argpartition(distances, min(k, len(distances) - 1))[:k]
    local_distances = distances[nearest]
    weights = 1.0 / np.maximum(local_distances, 1e-6)
    return np.average(train_positions[nearest], axis=0, weights=weights)


def nearest_grid_index(position: np.ndarray, pixels: np.ndarray) -> int:
    return int(np.argmin(np.sum((pixels - position[None, :]) ** 2, axis=1)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estudia EM para ruido RSSI y compara RTI Tikhonov, una extensión con gamma de Fisher y K-NN."
    )
    parser.add_argument("--grid-size", type=int, default=10, help="Píxeles por lado; la imagen tiene N×N píxeles (por defecto: 10).")
    parser.add_argument("--nodes", type=int, default=12, help="Nodos de radio en el perímetro (por defecto: 12).")
    parser.add_argument("--room-m", type=float, default=6.4, help="Lado del área cuadrada en metros (por defecto: 6.4).")
    parser.add_argument("--ellipse-width-m", type=float, default=0.10, help="Exceso de trayecto de la elipse RTI en metros (por defecto: 0.10).")
    parser.add_argument("--alpha", type=float, default=0.10, help="Regularización espacial de Tikhonov (por defecto: 0.10).")
    parser.add_argument("--target-attenuation-db", type=float, default=4.0, help="Atenuación sintética del objetivo en dB (por defecto: 4).")
    parser.add_argument("--link-loss", type=float, default=0.0, help="Fracción de enlaces perdidos durante la consulta (por defecto: 0).")
    parser.add_argument("--p-narrow", type=float, default=0.548, help="Probabilidad de la componente de ruido estrecha (valor sintético inicial del paper: 0.548).")
    parser.add_argument("--sigma-narrow-db", type=float, default=0.971, help="Desviación de la componente estrecha en dB (valor de referencia: 0.971).")
    parser.add_argument("--sigma-wide-db", type=float, default=3.003, help="Desviación de la componente amplia en dB (valor de referencia: 3.003).")
    parser.add_argument("--calibration-samples", type=int, default=5000, help="Muestras sintéticas para ajustar el GMM con EM (por defecto: 5000).")
    parser.add_argument("--train-per-cell", type=int, default=3, help="Huellas K-NN por píxel de referencia (por defecto: 3).")
    parser.add_argument("--knn-k", type=int, default=3, help="Número de vecinos K-NN (por defecto: 3).")
    parser.add_argument("--test-cases", type=int, default=500, help="Consultas sintéticas de evaluación (por defecto: 500).")
    parser.add_argument("--em-iterations", type=int, default=500, help="Máximo de iteraciones de EM (por defecto: 500).")
    parser.add_argument("--em-replicates", type=int, default=20, help="Réplicas por tamaño muestral en el estudio de EM (por defecto: 20).")
    parser.add_argument("--em-tolerance", type=float, default=1e-7, help="Tolerancia relativa para detener EM.")
    parser.add_argument("--sigma-floor", type=float, default=0.15, help="Piso de desviación estándar para evitar colapso numérico (dB).")
    parser.add_argument("--seed", type=int, default=7, help="Semilla aleatoria reproducible (por defecto: 7).")
    parser.add_argument("--output-dir", type=Path, default=Path("results/python_preliminary"), help="Carpeta de salida (por defecto: results/python_preliminary).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_args(args)
    backend_executable()  # Compila una sola vez antes de los bucles de calibración.
    rng = np.random.default_rng(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_em_diagnostics(args, args.output_dir)

    nodes = perimeter_nodes(args.nodes, args.room_m)
    pixels = grid_centers(args.grid_size, args.room_m)
    pairs, links_a, links_b = make_links(nodes)
    all_weights = elliptical_weights(links_a, links_b, pixels, args.ellipse_width_m)
    total_links, n_pixels = all_weights.shape

    # En esta prueba todas las consultas usan el mismo conjunto de enlaces
    # disponibles para que RTI y K-NN comparen las mismas observaciones.
    valid_links = rng.random(total_links) >= args.link_loss
    if np.count_nonzero(valid_links) < max(6, min(args.nodes, total_links)):
        raise ValueError("Quedaron muy pocos enlaces; reduce --link-loss o aumenta --nodes.")
    weights = all_weights[valid_links]

    # El paper original estima el GMM con EM; sus parámetros publicados se
    # usan aquí únicamente para generar ruido sintético reproducible.
    calibration_started = time.perf_counter()
    calibration_noise = draw_mixture_noise(
        rng,
        args.calibration_samples,
        args.p_narrow,
        args.sigma_narrow_db,
        args.sigma_wide_db,
    )
    p_hat, sigma_narrow_hat, sigma_wide_hat, em_steps, em_converged = fit_zero_mean_gmm_em(
        calibration_noise, args.em_iterations, tolerance=args.em_tolerance, sigma_floor=args.sigma_floor
    )
    gamma_em = fisher_information_gamma(p_hat, sigma_narrow_hat, sigma_wide_hat)
    variance_gaussian = p_hat * sigma_narrow_hat**2 + (1.0 - p_hat) * sigma_wide_hat**2
    gamma_gaussian_reference = 1.0 / max(variance_gaussian, 1e-8)
    # El baseline implementa la forma clásica de Tikhonov: W'W + alpha*L.
    # Gamma_Fisher se reserva como variante experimental y no se presenta
    # como parte del estimador RTI canónico.
    gamma_tikhonov = 1.0
    calibration_seconds = time.perf_counter() - calibration_started

    # Cada huella K-NN representa el cambio de RSS esperado para un objetivo
    # situado en un píxel conocido, más ruido del mismo modelo GMM.
    train_started = time.perf_counter()
    train_features: list[np.ndarray] = []
    train_positions: list[np.ndarray] = []
    for pixel_index, pixel in enumerate(pixels):
        clean = all_weights[:, pixel_index] * args.target_attenuation_db
        for _ in range(args.train_per_cell):
            noise = draw_mixture_noise(
                rng, total_links, args.p_narrow, args.sigma_narrow_db, args.sigma_wide_db
            )
            train_features.append(clean + noise)
            train_positions.append(pixel)
    train_features_array = np.asarray(train_features)
    train_positions_array = np.asarray(train_positions)
    training_seconds = time.perf_counter() - train_started

    operators = {}
    operator_setup = {}
    if n_pixels <= 900:
        laplacian = smoothness_laplacian(args.grid_size)
        for method, gamma in (("RTI_Tikhonov", gamma_tikhonov), ("RTI_EM_Fisher_extension", gamma_em)):
            setup_started = time.perf_counter()
            operators[method] = build_reconstruction_operator(weights, laplacian, args.alpha, gamma)
            operator_setup[method] = time.perf_counter() - setup_started
        solver_name = "inversa densa precalculada"
    else:
        operators = {"RTI_Tikhonov": None, "RTI_EM_Fisher_extension": None}
        operator_setup = {"RTI_Tikhonov": 0.0, "RTI_EM_Fisher_extension": 0.0}
        solver_name = "gradiente conjugado"

    n_queries = args.test_cases
    true_indices = rng.integers(0, n_pixels, size=n_queries)
    true_positions = pixels[true_indices]
    predicted = {
        "RTI_Tikhonov": np.zeros((n_queries, 2)),
        "RTI_EM_Fisher_extension": np.zeros((n_queries, 2)),
        "KNN": np.zeros((n_queries, 2)),
        "Centro_constante": np.full((n_queries, 2), args.room_m / 2.0),
    }
    image_mse = {"RTI_Tikhonov": [], "RTI_EM_Fisher_extension": []}
    inference_seconds = {method: [] for method in predicted}
    sample_query: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None

    for q, true_index in enumerate(true_indices):
        clean = all_weights[:, true_index] * args.target_attenuation_db
        noise = draw_mixture_noise(
            rng, total_links, args.p_narrow, args.sigma_narrow_db, args.sigma_wide_db
        )
        observation = clean + noise
        observation_valid = observation[valid_links]
        truth_image = np.zeros(n_pixels, dtype=float)
        truth_image[true_index] = args.target_attenuation_db

        started = time.perf_counter()
        image_tikhonov = reconstruct_image(
            operators["RTI_Tikhonov"], weights, observation_valid,
            args.grid_size, args.alpha, gamma_tikhonov,
        )
        predicted["RTI_Tikhonov"][q] = pixels[int(np.argmax(image_tikhonov))]
        inference_seconds["RTI_Tikhonov"].append(time.perf_counter() - started)
        started = time.perf_counter()
        image_em_fisher = reconstruct_image(
            operators["RTI_EM_Fisher_extension"], weights, observation_valid,
            args.grid_size, args.alpha, gamma_em,
        )
        predicted["RTI_EM_Fisher_extension"][q] = pixels[int(np.argmax(image_em_fisher))]
        inference_seconds["RTI_EM_Fisher_extension"].append(time.perf_counter() - started)
        image_mse["RTI_Tikhonov"].append(float(np.mean((image_tikhonov - truth_image) ** 2)))
        image_mse["RTI_EM_Fisher_extension"].append(float(np.mean((image_em_fisher - truth_image) ** 2)))

        started = time.perf_counter()
        predicted["KNN"][q] = nearest_neighbor_prediction(
            train_features_array,
            train_positions_array,
            observation,
            valid_links,
            min(args.knn_k, len(train_features_array)),
        )
        inference_seconds["KNN"].append(time.perf_counter() - started)
        started = time.perf_counter()
        predicted["Centro_constante"][q] = args.room_m / 2.0
        inference_seconds["Centro_constante"].append(time.perf_counter() - started)
        if q == 0:
            sample_query = (truth_image, image_tikhonov, image_em_fisher)

    errors = {
        method: np.linalg.norm(predicted[method] - true_positions, axis=1)
        for method in predicted
    }
    bootstrap_rng = np.random.default_rng(args.seed + 900_001)
    preparation_seconds = {
        "RTI_Tikhonov": operator_setup["RTI_Tikhonov"],
        "RTI_EM_Fisher_extension": calibration_seconds + operator_setup["RTI_EM_Fisher_extension"],
        "KNN": training_seconds,
        "Centro_constante": 0.0,
    }
    metrics_path = args.output_dir / "metricas.csv"
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "metodo", "error_medio_m", "ic95_media_inf_m", "ic95_media_sup_m",
                "error_rmse_m", "mse_mapa_db2",
                "tiempo_preparacion_ms", "tiempo_inferencia_medio_ms",
            ),
        )
        writer.writeheader()
        for method in predicted:
            ci_low, ci_high = bootstrap_mean_ci(errors[method], bootstrap_rng)
            writer.writerow(
                {
                    "metodo": method,
                    "error_medio_m": float(np.mean(errors[method])),
                    "ic95_media_inf_m": ci_low,
                    "ic95_media_sup_m": ci_high,
                    "error_rmse_m": float(np.sqrt(np.mean(errors[method] ** 2))),
                    "mse_mapa_db2": float(np.mean(image_mse[method])) if method in image_mse else "",
                    "tiempo_preparacion_ms": 1000.0 * preparation_seconds[method],
                    "tiempo_inferencia_medio_ms": 1000.0 * float(np.mean(inference_seconds[method])),
                }
            )

    detail_path = args.output_dir / "predicciones.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("caso", "metodo", "x_real_m", "y_real_m", "x_estimado_m", "y_estimado_m", "error_m"),
        )
        writer.writeheader()
        for q in range(n_queries):
            for method in predicted:
                writer.writerow(
                    {
                        "caso": q + 1,
                        "metodo": method,
                        "x_real_m": true_positions[q, 0],
                        "y_real_m": true_positions[q, 1],
                        "x_estimado_m": predicted[method][q, 0],
                        "y_estimado_m": predicted[method][q, 1],
                        "error_m": errors[method][q],
                    }
                )

    params = {
        "effective_args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "em_tolerance": args.em_tolerance,
        "sigma_floor_db": args.sigma_floor,
        "train_per_cell": args.train_per_cell,
        "knn_k": args.knn_k,
        "em_max_iterations": args.em_iterations,
        "grid_size": args.grid_size,
        "voxels": n_pixels,
        "radio_nodes": args.nodes,
        "total_links": total_links,
        "available_links": int(np.count_nonzero(valid_links)),
        "room_side_m": args.room_m,
        "ellipse_width_m": args.ellipse_width_m,
        "alpha": args.alpha,
        "target_attenuation_db": args.target_attenuation_db,
        "link_loss_fraction": args.link_loss,
        "calibration_samples": args.calibration_samples,
        "noise_generation_parameters": {
            "p_narrow": args.p_narrow,
            "sigma_narrow_db": args.sigma_narrow_db,
            "sigma_wide_db": args.sigma_wide_db,
        },
        "em_noise_estimate": {
            "p_narrow": p_hat,
            "sigma_narrow_db": sigma_narrow_hat,
            "sigma_wide_db": sigma_wide_hat,
            "gamma_fisher": gamma_em,
            "gamma_gaussian_reference": gamma_gaussian_reference,
            "iterations": em_steps,
            "converged": em_converged,
        },
        "em_diagnostic_replicates": args.em_replicates,
        "test_cases": n_queries,
        "seed": args.seed,
        "em_backend": backend_metadata(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "rti_solver": solver_name,
        "method_note": "RTI_Tikhonov es el baseline clásico; RTI_EM_Fisher_extension aplica gamma como extensión exploratoria, no como reproducción directa del estimador del artículo.",
        "data_note": "Todas las mediciones son sintéticas; no representan una medición Wi-Fi real ni una validación con escombros.",
        "timing_note": "Preparación propia de cada método; EM incluye serialización e inicio del proceso C++. Compilación previa fuera de los cronómetros. Inferencia termina en coordenadas. Medición exploratoria sin calentamiento ni control del orden; no sustenta superioridad de velocidad.",
        "knn_scale_note": "Distancias sin escala común estimada por EM; el factor común se cancela en pesos normalizados salvo cuando actúa el piso numérico de 1e-6.",
    }
    params_path = args.output_dir / "parametros.json"
    params_path.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")

    if sample_query is not None:
        true_image, image_tikhonov, image_em_fisher = sample_query
        image_knn = np.zeros(n_pixels)
        image_knn[nearest_grid_index(predicted["KNN"][0], pixels)] = args.target_attenuation_db
        fig, axes = plt.subplots(2, 2, figsize=(11, 9), constrained_layout=True)
        panels = (
            (true_image.reshape(args.grid_size, args.grid_size), "Campo verdadero sintético"),
            (image_tikhonov.reshape(args.grid_size, args.grid_size), "RTI: Tikhonov clásico"),
            (image_em_fisher.reshape(args.grid_size, args.grid_size), "RTI: extensión Fisher-EM"),
            (image_knn.reshape(args.grid_size, args.grid_size), "K-NN: ubicación estimada"),
        )
        for axis, (image, title) in zip(axes.ravel(), panels):
            artist = axis.imshow(
                image,
                origin="lower",
                extent=(0, args.room_m, 0, args.room_m),
                cmap="inferno",
                aspect="equal",
            )
            axis.scatter(nodes[:, 0], nodes[:, 1], marker="^", c="cyan", s=22, label="Nodos")
            axis.scatter(
                true_positions[0, 0], true_positions[0, 1],
                marker="x", c="lime", s=70, linewidths=2, label="Real",
            )
            axis.set_title(title)
            axis.set_xlabel("x (m)")
            axis.set_ylabel("y (m)")
            fig.colorbar(artist, ax=axis, fraction=0.046, pad=0.04)
        axes[0, 0].legend(loc="upper right", fontsize=8)
        axes[1, 1].scatter(predicted["KNN"][0, 0], predicted["KNN"][0, 1], marker="+", c="cyan", s=70, label="K-NN")
        axes[1, 1].legend(loc="upper right", fontsize=8)
        figure_path = args.output_dir / "comparacion_rti_em_knn.png"
        fig.savefig(figure_path, dpi=180)
        plt.close(fig)

    print("Simulación terminada.")
    print(f"Nodos: {args.nodes} | enlaces: {total_links} ({np.count_nonzero(valid_links)} disponibles) | píxeles: {args.grid_size}×{args.grid_size} | casos: {n_queries}")
    print(f"Resolución RTI: {solver_name}")
    print(
        "EM-GMM: "
        f"p1={p_hat:.3f}, sigma1={sigma_narrow_hat:.3f} dB, "
        f"sigma2={sigma_wide_hat:.3f} dB, gamma={gamma_em:.4f} "
        f"({em_steps} iteraciones)"
    )
    for method in predicted:
        print(
            f"{method}: error medio={np.mean(errors[method]):.3f} m, "
            f"RMSE={np.sqrt(np.mean(errors[method] ** 2)):.3f} m, "
            f"inferencia media={1000*np.mean(inference_seconds[method]):.3f} ms"
        )
    print(f"Archivos guardados en: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
