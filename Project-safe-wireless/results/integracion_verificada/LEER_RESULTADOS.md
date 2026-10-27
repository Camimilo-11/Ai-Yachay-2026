# Ejecución de integración sintética

No son mediciones WiFi ni resultados de materiales. Cada escenario se identifica con su configuración.
El error con fallback incluye el centro si no hay suficientes enlaces; comparison.csv también informa cobertura.
Huellas y prueba comparten cuadrícula; no es evaluación de posiciones nuevas.

- base, réplica 0: ok; enlaces 15/15.
- ruido_alto, réplica 0: ok; enlaces 15/15.
- cuantizacion, réplica 0: ok; enlaces 15/15.
- correlacion, réplica 0: em_not_converged; enlaces 15/15.
- perdidas, réplica 0: ok; enlaces 15/15.
- deriva, réplica 0: ok; enlaces 15/15.
- frecuencia_5ghz, réplica 0: ok; enlaces 15/15.
- margen_24ghz, réplica 0: ok; enlaces 14/15.
- margen_5ghz, réplica 0: insufficient_calibration; enlaces 4/15.

La portadora afecta solo el presupuesto FSPL y el censurado. Si no hay censurado, restar la referencia cancela la pérdida estática.
El ancho de banda solo cambia el piso térmico del modelo. No modifica por sí mismo la varianza RSS elegida.
Con rho o deriva la mezcla marginal real puede dejar de ser la familia GMM de partida.
Una sola réplica ilustra funcionamiento; no acredita superioridad estadística.
