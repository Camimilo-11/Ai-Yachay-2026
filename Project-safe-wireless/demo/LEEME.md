# Demo para la exposición de la propuesta

Abre `index.html` con doble clic en Edge, Chrome o Firefox. También puedes usar `ABRIR_DEMO.cmd` desde la carpeta principal del proyecto. La demo funciona sin conexión: no requiere instalar paquetes, iniciar un servidor ni ejecutar de nuevo los experimentos. Conserva los archivos de la carpeta `demo/` juntos.

## Qué puedes mostrar

- Frecuencias de **2,4 y 5 GHz**, seleccionando los escenarios guardados correspondientes.
- Nueve escenarios y 30 consultas por escenario; la dependencia temporal del ruido cambia según el caso.
- Vista superior de los seis nodos, sus enlaces, el objetivo de atenuación y la posición estimada.
- RTI Tikhonov, RTI con calibración EM, Tikhonov equivalente, K-NN y el control del centro.
- Error de cada consulta y métricas agregadas iguales a las de los CSV.
- Histograma de residuos, parámetros ajustados por EM y comparación con una gaussiana única.
- Lecturas RSS y enlaces sin medición, incluidos los casos de calibración insuficiente.
- Una capa opcional de señal de espacio libre (FSPL) calculada desde un nodo, con los parámetros del escenario. Se muestra como ilustración y no modifica las predicciones guardadas.

El botón **Recorrer casos** avanza por consultas distintas del experimento; no muestra el movimiento de una persona. En el escenario correlacionado, el ruido entre consultas tiene dependencia temporal. El control de frecuencia filtra datos existentes. Esta versión no crea escenarios nuevos ni ejecuta otra estimación.

## Recorrido sugerido para explicar en clase

1. **Caso base, vista superior.** Explica que los nodos intercambian señales, el círculo verde representa la posición conocida del objetivo sintético y el rombo naranja la estimación. La línea discontinua ilustra el error.
2. **Cambia RTI + EM por K-NN.** Recorre varias consultas para mostrar que los métodos pueden acertar o fallar de forma distinta. La tabla inferior agrega las 30 consultas; un caso individual no resume el desempeño.
3. **Calibración con EM.** EM estima la distribución del ruido a partir de 900 residuos en el caso base. La comparación predictiva utiliza otros 450 residuos: densidad logarítmica media de -2.101 para la mezcla y -2.145 para la gaussiana única. El ajuste estadístico y el error de localización son resultados distintos.
4. **Comparación de métodos.** En el caso base, el centro constante obtiene el menor error medio. RTI + EM y su Tikhonov equivalente coinciden. El piloto demuestra que se puede ejecutar la metodología; queda evaluar sus límites y mejoras.
5. **Escenario con ruido correlacionado.** El aviso conserva la falta de convergencia de EM en 600 iteraciones. Se muestran las predicciones que efectivamente quedaron guardadas.
6. **5 GHz con margen bajo.** El programa conserva el fallo de calibración y deja las métricas sin valor. Es una comparación del presupuesto de recepción ilustrativo, no una demostración de propagación por paredes.

Pulsa **Pantalla completa** o F11 para proyectar. Usa **Volver al caso base** cuando quieras reiniciar la explicación.

## Alcance científico

Esta es una visualización de las ejecuciones incluidas en `results/integracion_verificada/`. Cada consulta contiene un objetivo de atenuación sintético en una cuadrícula. No hay casos vacíos, varias personas, paredes, obstáculos ni modelos de materiales. Las posiciones de prueba se usan para evaluar las predicciones ya guardadas. Los colores de enlaces indican lecturas RSS disponibles. La capa opcional FSPL representa una predicción de espacio libre, no cobertura ni penetración de radio medidas; se calcula con el modelo de `wifi_rti/radio.py`, a distancias mínimas de 0,1 m para su representación.

La demo acompaña al artículo y a sus resultados preliminares; el diagrama del sistema que pide la materia sigue siendo un entregable separado.

## Regenerar después de ejecutar otros resultados

Con las dependencias del proyecto instaladas, desde su carpeta principal:

```powershell
.\.venv\Scripts\python.exe tools/crear_demo.py
```

El exportador lee los nueve escenarios originales, comprueba sus predicciones y métricas, escribe `datos_preliminares.json` y genera `index.html` desde `plantilla.html`. Los archivos científicos de origen se conservan como entrada de lectura.
