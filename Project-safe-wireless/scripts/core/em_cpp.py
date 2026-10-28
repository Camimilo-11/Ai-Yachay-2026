"""Adaptador de E/S: todas las estimaciones EM se ejecutan en em.cpp."""
from __future__ import annotations

from functools import lru_cache
import json
import subprocess

import numpy as np

from compilar_cpp import MANIFEST, build_em


@lru_cache(maxsize=1)
def backend_executable():
    return build_em()


def backend_metadata() -> dict:
    backend_executable()
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def fit_zero_mean_gmm_em(
    samples: np.ndarray,
    max_iterations: int,
    tolerance: float = 1e-7,
    p_initial: float = 0.7,
    sigma_narrow_initial: float | None = None,
    sigma_wide_initial: float | None = None,
    sigma_floor: float = 0.15,
) -> tuple[float, float, float, int, bool]:
    """Misma firma de la referencia; serializa residuos y lee la salida C++."""
    values = np.asarray(samples, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 20:
        raise ValueError("Se requieren al menos 20 observaciones válidas para EM.")
    s1 = float("nan") if sigma_narrow_initial is None else sigma_narrow_initial
    s2 = float("nan") if sigma_wide_initial is None else sigma_wide_initial
    header = f"{values.size} {max_iterations} {tolerance:.17g} {p_initial:.17g} {s1:.17g} {s2:.17g} {sigma_floor:.17g}\n"
    payload = header + " ".join(format(value, ".17g") for value in values) + "\n"
    result = subprocess.run(
        [str(backend_executable()), "--fit"], input=payload,
        text=True, capture_output=True, check=True, timeout=120,
    )
    p, s1, s2, iterations, converged = result.stdout.split()
    return float(p), float(s1), float(s2), int(iterations), bool(int(converged))
