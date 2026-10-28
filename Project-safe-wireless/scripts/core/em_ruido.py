"""Referencia Python para verificar paridad del núcleo oficial C++17 (em.cpp).

No es el backend ejecutado por el simulador; em_cpp.py invoca em.cpp.
Esta referencia ajusta una mezcla de dos gaussianas con media cero.

Entradas: muestras de ruido (dB), máximo de iteraciones, tolerancia relativa,
peso inicial, desviaciones iniciales opcionales y piso de desviación.
Salida: (peso de componente estrecha, sigma estrecha, sigma amplia,
iteraciones utilizadas, convergió).

Paso E: calcula la probabilidad de que cada muestra pertenezca a cada
componente. Paso M: actualiza el peso y las varianzas con esas probabilidades.
Repite hasta estabilizar los parámetros o agotar las iteraciones. No estima
posiciones, no rellena RSSI faltante y no es el reconstruidor RTI.
"""
from __future__ import annotations

import math
import numpy as np


def fit_zero_mean_gmm_em(
    samples: np.ndarray,
    max_iterations: int,
    tolerance: float = 1e-7,
    p_initial: float = 0.7,
    sigma_narrow_initial: float | None = None,
    sigma_wide_initial: float | None = None,
    sigma_floor: float = 0.15,
) -> tuple[float, float, float, int, bool]:
    """Ajusta una mezcla de dos normales centradas en cero mediante EM."""
    values = np.asarray(samples, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 20:
        raise ValueError("Se requieren al menos 20 observaciones válidas para EM.")

    spread = max(float(np.std(values)), 1e-3)
    p_narrow = float(np.clip(p_initial, 1e-4, 1.0 - 1e-4))
    sigma_narrow = max(
        sigma_narrow_initial if sigma_narrow_initial is not None else spread * 0.55,
        sigma_floor,
    )
    sigma_wide = max(
        sigma_wide_initial if sigma_wide_initial is not None else spread * 1.8,
        sigma_narrow * 1.05,
    )

    for iteration in range(1, max_iterations + 1):
        old = np.array([p_narrow, sigma_narrow, sigma_wide])
        var_narrow = max(sigma_narrow**2, 1e-8)
        var_wide = max(sigma_wide**2, 1e-8)

        log_narrow = (
            math.log(max(p_narrow, 1e-12))
            - 0.5 * math.log(2.0 * math.pi * var_narrow)
            - values**2 / (2.0 * var_narrow)
        )
        log_wide = (
            math.log(max(1.0 - p_narrow, 1e-12))
            - 0.5 * math.log(2.0 * math.pi * var_wide)
            - values**2 / (2.0 * var_wide)
        )
        max_log = np.maximum(log_narrow, log_wide)
        exp_narrow = np.exp(log_narrow - max_log)
        exp_wide = np.exp(log_wide - max_log)
        responsibility_narrow = exp_narrow / np.maximum(exp_narrow + exp_wide, 1e-300)

        mass_narrow = max(float(np.sum(responsibility_narrow)), 1e-8)
        mass_wide = max(float(values.size - mass_narrow), 1e-8)
        p_narrow = float(np.clip(mass_narrow / values.size, 1e-4, 1.0 - 1e-4))
        new_var_narrow = float(np.sum(responsibility_narrow * values**2) / mass_narrow)
        new_var_wide = float(
            np.sum((1.0 - responsibility_narrow) * values**2) / mass_wide
        )
        sigma_narrow = max(math.sqrt(max(new_var_narrow, 0.0)), sigma_floor)
        sigma_wide = max(math.sqrt(max(new_var_wide, 0.0)), sigma_floor)

        if sigma_narrow > sigma_wide:
            sigma_narrow, sigma_wide = sigma_wide, sigma_narrow
            p_narrow = 1.0 - p_narrow

        new = np.array([p_narrow, sigma_narrow, sigma_wide])
        if np.max(np.abs(new - old) / np.maximum(np.abs(old), 1e-8)) < tolerance:
            return p_narrow, sigma_narrow, sigma_wide, iteration, True

    return p_narrow, sigma_narrow, sigma_wide, max_iterations, False

