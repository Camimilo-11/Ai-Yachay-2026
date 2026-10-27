"""Paridad del EM C++ oficial con la referencia Python y prueba del CLI."""
import subprocess
import unittest

import numpy as np

from em_cpp import backend_executable, backend_metadata, fit_zero_mean_gmm_em
from em_ruido import fit_zero_mean_gmm_em as python_reference


class CppParityChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.executable = backend_executable()

    def test_parameter_parity_on_three_sample_sizes(self):
        rng = np.random.default_rng(481)
        for n in (100, 1000, 5000):
            scales = np.where(rng.random(n) < 0.548, 0.971, 3.003)
            values = rng.normal(0, scales)
            for initial in ({}, {"p_initial": 0.35, "sigma_narrow_initial": 0.6,
                                  "sigma_wide_initial": 4.0}):
                with self.subTest(n=n, initial=initial):
                    expected = python_reference(values, 500, **initial)
                    actual = fit_zero_mean_gmm_em(values, 500, **initial)
                    np.testing.assert_allclose(actual[:3], expected[:3], rtol=0, atol=1e-9)
                    self.assertEqual(actual[3:], expected[3:])

    def test_nonfinite_values_are_filtered(self):
        values = np.tile([-0.5, 0.5, -1, 1, -4, 4], 10).astype(float)
        values = np.append(values, [np.nan, np.inf, -np.inf])
        np.testing.assert_allclose(
            fit_zero_mean_gmm_em(values, 500)[:3], python_reference(values, 500)[:3],
            rtol=0, atol=1e-9,
        )

    def test_demo_is_computed_by_cpp(self):
        result = subprocess.run([str(self.executable), "--demo"], text=True,
                                capture_output=True, check=True)
        self.assertIn("p=0.355017; sigma1=1.259700; sigma2=2.622727", result.stdout)
        self.assertIn("responsabilidad=0.052085", result.stdout)
        self.assertIn("responsabilidad=0.657949", result.stdout)

    def test_fit_cli_rejects_four_observations(self):
        result = subprocess.run([str(self.executable), "--fit"], text=True,
                                input="4 1 1e-7 .5 1 3 .15\n-3 -1 1 3\n",
                                capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("20 residuos", result.stderr)

    def test_backend_records_compiler(self):
        metadata = backend_metadata()
        self.assertEqual(metadata["backend"], "C++17")
        self.assertIn("-std=c++17", metadata["flags"])
        self.assertIn("g++", metadata["compiler_version"])


if __name__ == "__main__":
    unittest.main()
