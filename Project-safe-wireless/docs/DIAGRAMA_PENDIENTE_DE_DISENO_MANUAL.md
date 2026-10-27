# Figura 1: flujo de la simulación

## Qué representa

La Figura 1 debe explicar el recorrido de los datos por el programa: cómo se generan mediciones RSS sintéticas, cómo EM calibra el modelo de ruido, cómo se estiman posiciones y cómo se calculan las métricas. Es un diagrama de flujo del experimento. No es un plano de una habitación real, una gráfica de resultados ni una arquitectura de cámara y sensores físicos.

La guía de la materia pide que el estudiante diseñe esta figura manualmente. Por eso el paquete incluye las instrucciones, pero no una ilustración generada. Dibuja la figura en draw.io, PowerPoint, Canva o una herramienta similar e insértala en la propuesta como Figura 1. Guarda una copia en `report/figures/system_diagram.png`.

## Cómo organizar el dibujo

Puedes distribuir las cajas de izquierda a derecha en tres franjas: **generación y partición de datos**, **calibración/validación**, y **estimación/evaluación**. Usa flechas para indicar qué datos pasan a cada etapa. La siguiente lista describe el contenido y la conexión que debe quedar visible; no es una figura para copiar automáticamente.

1. **Geometría y parámetros:** muestra el área simulada, la cuadrícula, las posiciones de los nodos y la matriz de pesos elípticos `W`. Rotula el bloque como sintético.
2. **Generador:** indica el modelo `y = W x + n`, donde `x` es la atenuación sintética y `n` el ruido. Desde aquí salen archivos RSS por enlace y las particiones independientes: referencia, calibración, validación de ruido, huellas, desarrollo y prueba. Guarda la posición real del objetivo en un archivo separado.
3. **Calibración EM:** conecta solo los residuos del bloque de calibración con el estimador EM de dos gaussianas en C++17. Anota como salidas `p`, `sigma1`, `sigma2`, el estado de convergencia y `gamma` (factor Fisher usado por la variante RTI).
4. **Validación del ruido:** conecta los residuos reservados de validación a una comparación entre la mezcla ajustada por EM y una gaussiana única. La salida es la densidad logarítmica media de cada modelo; esta rama evalúa ajuste del ruido, no precisión de posición.
5. **Ajuste y localización:** muestra que los datos de desarrollo fijan `alpha` para RTI y `K` para K-NN. Las mediciones de prueba alimentan RTI Tikhonov, RTI con escala Fisher, su control Tikhonov con regularización equivalente, K-NN ponderado (junto con las huellas sintéticas) y la predicción constante del centro. Cada método produce una posición estimada.
6. **Evaluación final:** une las posiciones estimadas con las posiciones verdaderas reservadas y calcula error medio, RMSE y cobertura. La verdad de posición se usa aquí para puntuar las predicciones; no debe entrar a EM ni a los métodos de localización. También puedes mostrar aquí los registros de convergencia de EM y los resultados de la validación del ruido.

## Rotulación y límites

Incluye una etiqueta visible **Simulación sintética**. No dibujes cámara, captura real de Wi-Fi, CSI ni propagación física como parte del flujo ejecutado. El diagrama debe representar lo que corre en este repositorio: generador sintético → calibración/validación → localización → evaluación.
