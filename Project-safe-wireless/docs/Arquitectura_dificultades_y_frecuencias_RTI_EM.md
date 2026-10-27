INFORME DE INTEGRACIÓN | 27 OCTUBRE 2026

Arquitectura, dificultadesy frecuencias de radio

Wireless Save + wifi-sensing-human-presence. Paquete ejecutable basado exclusivamente en datos sintéticos.

> Decisión: la integración es factible con una estructura reducida. Se conserva EM en C++17 y RTI/K-NN de Wireless Save. IsukaW aporta formato y estadísticas opcionales. No se usa cámara, escaneo ni extracción física.

1. Qué arquitectura ejecuta realmente GitHub

| Entrada original | Qué conecta y qué hace |
| --- | --- |
| main.py | OpenCV + src.wifi + src.utils. Cámara y cambios RSSI con reglas propias. |
| wifi_radar.py | WiFi + Matplotlib. Umbrales y posiciones construidas con fórmulas gráficas. |
| wifi_monitor.py | netsh de Windows. Monitor de señal de redes cercanas. |
| scripts/collect_data.py | Cámara + WiFi + etiqueta manual; guarda sesiones. |
| scripts/train_model.py | Carga sesiones y entrena Random Forest, SVM o MLP. |

El árbol del README no es un único flujo. main.py no utiliza DataFusionModule ni MLPipeline. fusion/ y ml/ son módulos separados. Clasificar estados de presencia no equivale a reconstruir un campo de atenuación con RTI. [1]

2. Qué impide asumir que todo está listo

El original declara CSI sin implementar su captura en la ruta revisada. main.py busca un archivo de configuración ausente y recurre a valores predeterminados. El recolector conserva un frame NumPy que su escritura JSON no convierte; la ruta de inferencia ML tampoco reutiliza correctamente todo el preprocesamiento guardado. [1]

run.bat no garantiza instalar dependencias. Su comprobación de pyvenv.cfg ocurre después de crear el entorno, cuando el archivo ya existe. La guía detallada y los puntos de lectura se incluyen en docs/ARQUITECTURA_Y_EJECUCION.md.

> No se comprobaron físicamente las cifras de exactitud, 20 Hz ni conteo de personas anunciadas. El radar de IsukaW no es una medición de posición RTI.

02 | WIRELESS SAVE + ISUKAW

La integración reducida

> Ruta: generar datos sintéticos → ajustar EM en C++ → ejecutar RTI y K-NN → comparar con controles.

```
ejecutar_integracion.py
  -> synthetic.py: datos y escenarios
  -> experiment.py: EM C++ y coordinacion
  -> evaluation.py: RTI/KNN y controles
  -> reporting.py: tablas y figura
```

No hay una etapa de extracción externa. Los CSV son registros de la propia simulación; se vuelven a leer para comprobar valores, pérdidas e identidad de enlaces. WiFiMeasurement se reutiliza como formato. El extractor de estadísticas de IsukaW es opcional y no alimenta EM/RTI.

3. Modelo y unidades

```
y(t) = W x(t) + n(t)
RSS_l(t) = b_l - y_l(t)
```

W tiene una fila por enlace y una columna por celda. y y n se expresan en dB; la referencia b y RSS se expresan en dBm. Una lectura ausente queda vacía y valid=0. La pérdida extra del modelo no se asigna a una pared o material.

| Bloque | Uso y separación |
| --- | --- |
| Referencia / calibración | La referencia se estima con su bloque; EM recibe solo residuos de calibración. |
| Validación de ruido | Bloque independiente para comparar densidades predictivas. |
| Huellas / desarrollo | Huellas con posición conocida. Alpha y k se eligen con desarrollo. |
| Prueba | La verdad solo puntúa. Las huellas cubren la misma cuadrícula, con ruido separado. |

Principal: 12 nodos, 66 enlaces y 100 celdas. Rápido: 6 nodos, 15 enlaces y 36 celdas. No se evalúan posiciones inéditas, varios objetivos o movimiento continuo. El modelo es estadístico y geométrico, no electromagnético.

4. Qué se mantiene de Wireless Save

em.cpp, em_cpp.py y las funciones existentes de geometría, reconstrucción y K-NN. La variante Fisher sigue siendo Tikhonov con alpha/gamma y estabilizador escalado. Se incluye el control algebraicamente equivalente.

Los máximos numéricamente empatados se resuelven con una tolerancia fija para que operadores equivalentes no cambien de celda por redondeo de máquina. No cambia el algoritmo EM.

03 | WIRELESS SAVE + ISUKAW

Frecuencia, alcance y capa de enlace

| Magnitud | Ejemplo | Papel en el problema |
| --- | --- | --- |
| Portadora | 2,4 / 5 / 6 GHz | Frecuencia de la onda; afecta el presupuesto de enlace. |
| Ancho de canal | 20 / 40 MHz | Banda ocupada; no es la cadencia de lecturas RSS. |
| Muestreo RSS | 2 lecturas/s | Cadencia temporal; afecta dependencia y representación de cambios. |

Con potencia y ganancias de antena comparables, frecuencias menores suelen facilitar cobertura. La onda no viaja más rápido por tener menor frecuencia: cambia su longitud de onda y el presupuesto de recepción. Antenas, interferencia, sensibilidad y obstáculos también influyen. [3, 4]

5. Cálculo de espacio libre

```
lambda = c / f
FSPL(dB) = 20 log10(4 pi d f / c)
```

Se aplica UIT-R P.525-5 con antenas isotrópicas. Tabla calculada a 10 m, sin paredes ni pérdidas adicionales. [3]

| Portadora | Longitud de onda | FSPL a 10 m | Extra vs. 2,4 |
| --- | --- | --- | --- |
| 2.4 GHz | 12.49 cm | 60.05 dB | 0.00 dB |
| 5 GHz | 6.00 cm | 66.43 dB | 6.38 dB |
| 6 GHz | 5.00 cm | 68.01 dB | 7.96 dB |

> 5 GHz añade 6,38 dB de pérdida en este cálculo. No representa la pérdida de una pared ni una distancia de alcance interior.

En la integración, si el nivel de fondo es constante y no hay censurado, restar la referencia cancela esa pérdida estática. Por eso 2,4 y 5 GHz pueden dar el mismo resultado RTI. Cerca del umbral de recepción, sí se pierden observaciones. Es una consecuencia del modelo implementado.

6. Lo que aporta el material de clase

El PDF de clase explica FDMA (página 12 del archivo) y CSMA/CA para IEEE 802.11 (página 22). Trata cómo se comparte el canal; no aporta una ley de penetración en paredes. No se implementa un simulador MAC en esta entrega. [2]

NIST muestra que la atenuación medida depende de material, espesor y refuerzo. No existe una conversión universal de densidad a varianza RSS. extra_loss_db es un parámetro arbitrario de estrés, no una propiedad medida de un material. [5]

04 | WIRELESS SAVE + ISUKAW

Bajo qué parámetros tiene dificultad

| Condición | Dificultad | Cómo se explora |
| --- | --- | --- |
| Ruido frente a señal | Cambios de ruido comparables a W x reducen la información de posición. | sigma1, sigma2 y atenuación del objetivo. |
| Mezcla poco distinguible | Sigmas similares o peso extremo dificultan separar componentes. | Parámetros expuestos y estado de convergencia. |
| Pocas muestras | Las filas correlacionadas no equivalen a evidencia independiente. | Mínimos de datos, conteos y bloques separados. |
| Correlación temporal | Viola independencia y puede cambiar la familia marginal. | rho; se conserva la no convergencia observada. |
| Cuantización | Redondeo y ceros afectan el ajuste de densidad continua. | Error separado de integridad CSV. |
| Deriva de fondo | Referencia inestable y residuos de media no nula. | drift_db_per_s y media residual. |
| Pérdidas de enlaces | Menos cobertura espacial y huellas incompletas. | Máscaras, datos vacíos y cobertura por método. |
| Geometría / resolución | Pocos enlaces o celdas sin cobertura vuelven ambiguo el inverso. | Nodos, grilla, ancho elíptico, rango de W. |
| Regularización / K-NN | Suavizado o huellas inadecuadas sesgan la posición. | Alpha y k seleccionados con desarrollo. |
| Margen de recepción | Portadora y pérdidas pueden censurar datos débiles. | FSPL, potencia y umbral ilustrativos. |
| Ancho de banda | Más banda aumenta el ruido térmico integrado a potencia fija. | Solo modifica el umbral; no la varianza RSS elegida. |

> Un gamma global no identifica enlaces contaminados. La equivalencia con Tikhonov impide atribuir una mejora al carácter robusto de EM sin un control adecuado.

Cuando desarrollo no permite seleccionar parámetros, se detiene la evaluación de prueba. Cuando EM no converge, se informa explícitamente; no se cambia de algoritmo ni se oculta el fallo. Si un método no puede predecir una consulta, se informa su cobertura y el centro como fallback explícito.

La simulación no modela reflexión, difracción o absorción por materiales. Aumentar sigma2 no representa una pared más densa. Las condiciones de estrés no demuestran robustez a NLoS o escombros.

05 | WIRELESS SAVE + ISUKAW

Resultados del ejemplo ejecutado

Suite rápida: semilla 7, una réplica, 6 nodos, 15 enlaces, 36 celdas y 30 consultas. Los valores se leen de results/integracion_verificada. No son las cifras históricas del manuscrito.

| Escenario | RSS válidos | EM conv. | KNN (m) | RTI (m) | Fisher (m) |
| --- | --- | --- | --- | --- | --- |
| Base | 100.0% | Sí | 2.529 | 3.653 | 3.530 |
| Ruido alto | 100.0% | Sí | 2.643 | 3.638 | 3.684 |
| Cuantización | 100.0% | Sí | 2.459 | 3.540 | 3.534 |
| Correlación | 100.0% | No | 2.652 | 3.279 | 3.028 |
| Pérdidas | 61.3% | Sí | 2.363 | 2.898 | 3.005 |
| Deriva | 100.0% | Sí | 2.511 | 3.594 | 3.497 |
| 5 GHz, margen amplio | 100.0% | Sí | 2.529 | 3.653 | 3.530 |
| 2,4 GHz, margen bajo | 38.2% | Sí | 2.939 | 4.131 | 4.131 |
| 5 GHz, margen bajo | 1.3% | Sin ajuste | - | - | - |

Error medio con fallback explícito al centro cuando falta predicción. El centro constante obtiene 2,357 m en estos objetivos. comparison.csv también contiene errores condicionados a casos válidos y cobertura. El porcentaje de RSS disponibles no es esa cobertura.

7. Interpretación

La base y 5 GHz con margen amplio coinciden porque se cancela la pérdida estática. Con pérdida extra de 28 dB y sensibilidad de -82 dBm, 5 GHz no reúne calibración suficiente. No se inventa una métrica de localización para ese caso.

Con rho=0,8 EM no cumple la tolerancia en 600 iteraciones. Se marca em_not_converged y sus resultados son exploratorios. Que alguna pérdida aleatoria reduzca el error en una réplica no demuestra que perder datos sea beneficioso.

> En esta suite ningún método dependiente de señal supera al centro en error medio. La integración funciona, pero mejorar la utilidad de localización continúa abierto.

Falta repetir toda la cadena con varias semillas y evaluar posiciones fuera de las huellas. Las conclusiones se limitan a los supuestos y configuraciones guardados.

06 | WIRELESS SAVE + ISUKAW

Ejecución, fuentes y comprobaciones

8. Ejecutar la simulación

```
python -m pip install -r requirements.txt
python ejecutar_integracion.py --quick --suite --output results/mi_prueba

python ejecutar_integracion.py --config config_integracion/base.json --output results/completa
python ejecutar_integracion.py --quick --suite --replicas 5 --output results/replicas

```

Escribe cada comando en una línea. Usa una salida nueva mediante --output para no sobrescribir resultados. Requiere Python >=3.10 y g++ C++17. INICIAR_SIMULACION.bat ofrece la ruta rápida. La principal de 12 nodos también se ejecutó y se incluye en results/integracion_completa.

9. Verificación

```
python -m pip install -r requirements_opcionales.txt
python -B -m unittest test_integracion test_auditoria test_em_cpp -v
python verificar_paquete.py
```

29 pruebas pasan y una revisión independiente verificó los casos corregidos: CSV alterado, desarrollo sin selección válida, procedencia desde otra carpeta y convergencia explícita. Los paquetes opcionales se necesitan para la prueba del extractor IsukaW; no para el flujo sintético principal.

10. Fuentes

[1] IsukaW, wifi-sensing-human-presence. Código y MIT, revisión 91aee04. Fuente.

[2] UC.6_The_Link_Layer_and_LANs.pdf, material docente aportado, 33 páginas. Páginas 7, 10, 12 y 22 del archivo; autor y fecha no identificados en ellas.

[3] UIT-R P.525-5 (11/2024), Calculation of free-space attenuation. Fuente.

[4] Cisco, Site Preparation and Planning, apartados de propagación y presupuesto de enlace. Fuente.

[5] William C. Stone. Electromagnetic Signal Attenuation in Construction Materials. NISTIR 6055, octubre de 1997. Fuente.

[6] Wireless Save: copia de la ruta indicada. Código EM/RTI y resultados; hashes de origen en docs/base_snapshot.json.

> Entrega exclusivamente sintética. No valida captura WiFi real, CSI, conteo de personas ni operación entre escombros. La carpeta original del usuario permanece intacta.
