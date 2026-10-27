# Figura del sistema: pendiente de diseño manual

La guía de la materia especifica que el diagrama debe diseñarlo el estudiante y no debe generarse con IA. Por esa razón, esta entrega no incluye una figura dibujada automáticamente. Para completar la propuesta, crear manualmente la Figura 1 con draw.io, PowerPoint, Canva o una herramienta equivalente y guardarla como `report/figures/system_diagram.png`.

El dibujo debe explicar con flechas esta cadena del código:

1. **Configuración y geometría:** posiciones sintéticas de nodos, cuadrícula de celdas y matriz elíptica `W`.
2. **Generación de datos:** referencia, atenuación sintética y ruido; guardar medidas RSS por enlace y verdad de posición en archivos separados.
3. **Calibración:** bloque de residuos independiente que entra al EM de dos gaussianas en C++17; salida `p`, `sigma1`, `sigma2`, convergencia y `gamma`.
4. **Validación de ruido:** datos reservados comparan log-densidad de la mezcla EM contra una gaussiana única.
5. **Localización:** consultas de prueba alimentan RTI Tikhonov, RTI con escala Fisher, K-NN ponderado y el control del centro; incluir el Tikhonov equivalente como control algebraico.
6. **Evaluación:** comparar predicciones con posiciones verdaderas reservadas; reportar error medio, RMSE, cobertura y convergencia.

Rotular todo el diagrama como **simulación sintética**. No dibujar cámara, captura Wi-Fi, CSI ni mediciones físicas como parte del flujo ejecutado. La verdad de posición no debe aparecer como entrada de EM o de los métodos de localización; solo se usa al final para calcular error.
