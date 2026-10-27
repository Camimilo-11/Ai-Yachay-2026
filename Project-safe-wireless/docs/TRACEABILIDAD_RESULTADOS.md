# Trazabilidad de resultados preliminares

| Resultado reportado | Archivo del artículo reproducible | Origen guardado |
|---|---|---|
| Parámetros de ruido estimados, iteraciones, convergencia y número de residuos de calibración | `results/integracion_verificada/base_r00/summary.json`, campo `em` | `calibration_residuals.csv`, configuración y hash del programa en `summary.json` |
| Densidad logarítmica de mezcla vs. gaussiana única | `summary.json`, campo `noise_validation` | Residuales de calibración y `raw/noise_validation.csv` |
| Error medio, RMSE y cobertura por método | `summary.json`, campo `metrics` | `predictions.csv`, `ground_truth.csv` y `comparison.csv` |
| Resultados del estrés de correlación y márgenes de recepción | `results/integracion_verificada/correlacion_r00/summary.json` y `margen_5ghz_r00/summary.json` | Configuración de cada escenario y CSV crudos por fase |

Para volver a generar la suite preliminar, usa una ruta de salida nueva:

```powershell
.\.venv\Scripts\python.exe ejecutar_integracion.py --quick --suite --output results/reproduccion_propuesta
```

La semilla base predeterminada es 7. Estas cifras proceden de ejecuciones del simulador versionado y deben presentarse como resultados preliminares sintéticos. No son mediciones físicas ni estimaciones de un intervalo de confianza poblacional. La suite rápida actual tiene una ejecución por escenario; la propuesta plantea repetirla con varias semillas.
