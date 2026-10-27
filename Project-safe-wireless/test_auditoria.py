"""Comprobaciones focalizadas de la extracción EM y del emparejamiento por ID.

Ejecutar: python -B -m unittest test_auditoria -v
No ejecuta la simulación ni modifica resultados guardados.
"""
from __future__ import annotations

import copy
import unittest

import numpy as np

from analizar_resultados import align_predictions
from em_cpp import fit_zero_mean_gmm_em
from simulacion_rti_em_knn import nearest_neighbor_prediction


class AuditChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"caso": str(case), "metodo": method, "x_real_m": str(case),
             "y_real_m": "2.0", "error_m": str(case + offset)}
            for case in (1, 2, 3)
            for method, offset in (("A", 0), ("B", 0.5))
        ]

    def test_reordering_preserves_pairing(self) -> None:
        original = align_predictions(self.rows, ["A", "B"], 3)
        shuffled = align_predictions(list(reversed(self.rows)), ["A", "B"], 3)
        for method in original:
            np.testing.assert_array_equal(original[method], shuffled[method])

    def test_incomplete_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "incompletos"):
            align_predictions(self.rows[:-1], ["A", "B"], 3)

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicado"):
            align_predictions(self.rows + [self.rows[0]], ["A", "B"], 3)

    def test_incompatible_truth_is_rejected(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[1]["x_real_m"] = "99"
        with self.assertRaisesRegex(ValueError, "incompatibles"):
            align_predictions(rows, ["A", "B"], 3)

    def test_em_known_zero_mean_mixture(self) -> None:
        # Salida calculada con el código original respaldado antes de extraerlo.
        values = np.tile(np.array([-0.5, 0.5, -1.0, 1.0, -4.0, 4.0]), 100)
        p, s1, s2, _, converged = fit_zero_mean_gmm_em(values, 500)
        self.assertTrue(converged)
        np.testing.assert_allclose(
            [p, s1, s2],
            [0.4340024410960611, 0.7655946006331233, 3.1160248191196542],
            rtol=1e-12,
        )

    def test_knn_common_scale_cancels_away_from_floor(self) -> None:
        rng = np.random.default_rng(71)
        features = rng.normal(size=(30, 6))
        positions = rng.uniform(0, 6.4, size=(30, 2))
        query = rng.normal(size=6)
        valid = np.array([True, False, True, True, True, False])
        distances = np.linalg.norm((features[:, valid] - query[valid]) / 2.3, axis=1)
        nearest = np.argpartition(distances, 3)[:3]
        before = np.average(
            positions[nearest], axis=0, weights=1 / np.maximum(distances[nearest], 1e-6)
        )
        after = nearest_neighbor_prediction(features, positions, query, valid, 3)
        np.testing.assert_allclose(before, after, rtol=1e-14, atol=1e-14)


if __name__ == "__main__":
    unittest.main()
