# Arquitectura y viabilidad 

Fuente: IsukaW/wifi-sensing-human-presence, revisión 91aee04ea938274d014a3981d409f83267ea15c0.
La revisión se hizo sobre el código, no solo sobre el árbol de carpetas del README.
No se ejecutó captura física ni se verificó una exactitud anunciada por el autor.

## Lo que realmente se conecta
| Entrada | Dependencias principales | Comportamiento |
|---|---|---|
| main.py | src.wifi, src.utils y OpenCV | SimplePresenceSystem; cámara + cambios RSSI + reglas propias. |
| wifi_radar.py | src.wifi, src.utils y Matplotlib | Compara una referencia RSSI; crea detecciones y coordenadas heurísticas. |
| wifi_monitor.py | biblioteca estándar y netsh | Muestra redes y variaciones en Windows. |
| scripts/collect_data.py | camera, wifi y utilidades | Recoge ambos sensores y una etiqueta manual; guarda sesiones JSON/CSV. |
| scripts/train_model.py | src.ml y utilidades | Carga sesiones, limpia características y entrena un clasificador. |

main.py no importa DataFusionModule ni MLPipeline. Por tanto, camera -> wifi -> fusion -> ml
no es una cadena real del programa principal. fusion/ es un módulo aparte y contiene una demo simulada.
ml/ admite Random Forest, SVM y MLP; eso es clasificación de estados, no el problema inverso RTI.

## Flujo radio real del repositorio
WiFiScanner consulta herramientas del SO -> WiFiMeasurement -> ventanas y estadísticas.
En Windows lee porcentajes con netsh y usa una conversión aproximada -100+0.7*porcentaje.
WiFiFeatureExtractor agrupa por SSID/BSSID; no genera una geometría Tx-Rx con coordenadas conocidas.
La clase CSI y las opciones del YAML no constituyen una captura CSI implementada.

## Cómo se ejecuta el ORIGINAL (referencia, no requerido por nuestra simulación)
Desde vendor/wifi_sensing_human_presence, usando un entorno con las dependencias originales instaladas:
- python wifi_monitor.py
- python wifi_radar.py
- python main.py
- python -m scripts.collect_data --help
- python -m scripts.train_model --help

Las tres primeras rutas necesitan hardware; no se ejecutaron en esta entrega.
main.py no implementa argparse: --config o --mode no configuran esa aplicación.
Busca config/my_config.yaml, ausente en esa revisión; ConfigLoader usa valores predeterminados.
run.bat crea el entorno y después consulta pyvenv.cfg: ese archivo ya existe y la instalación puede omitirse.
Conviene instalar explícitamente las dependencias si se estudia el original, en otro entorno.
Sus requirements incluyen Torch/Jupyter y herramientas que no son necesarias para nuestro método.

## Problemas que impiden asumir una integración lista
1. El recolector conserva un frame NumPy y luego intenta serializar el registro con JSON sin convertir ese frame.
2. El entrenamiento ajusta el escalador antes de dividir entrenamiento/prueba y usa una separación aleatoria de filas.
3. El cargador de fusión ML no reutiliza el preprocesador guardado y mapea clases de forma fija.
4. El script de entrenamiento pasa config['ml'] mientras el entrenador busca type y opciones en ese nivel;
   el tipo está anidado en model. Elegir --model-type no garantiza el efecto descrito.
5. La frecuencia RSSI configurada es un intervalo de 0.5 s más el coste del escaneo, no una garantía de 20 Hz.
6. Las coordenadas del radar se construyen con fórmulas gráficas; no son triangulación o tomografía.

## Veredicto y recorte para RTI-EM
Es factible reutilizar formato, ideas de organización y estadísticas, pero no replicar directamente
la localización RTI mediante el radar o el clasificador del proyecto.
Para esta entrega, toda entrada es sintética:
generador -> EM en C++ -> RTI/KNN -> métricas.
Las mediciones se registran por enlace para verificar el recorrido; no existe fase de extracción externa.
WiFiMeasurement y, opcionalmente, WiFiFeatureExtractor se extraen de IsukaW con licencia y atribución.
El núcleo EM y las funciones geométricas/reconstructivas se conservan de Wireless Save.
La arquitectura principal no depende de camera/, fusion/, ml/, modelos preentrenados ni Torch.

## Puntos de lectura verificables en la revisión
- main.py: importaciones 18-19; configuración 180; _simple_fusion 396.
- wifi_radar.py: _analyze_signals 205; posición heurística 434.
- src/wifi/__init__.py: escáner 49; parser Windows 511; extractor 595; WiFiModule 775.
- scripts/collect_data.py: bucle 192; guardado JSON 273.
- src/ml/__init__.py: ajuste y split 187-198; demo sintética 569.
- src/fusion/__init__.py: carga de modelo 257; predicción y clases 320-399.

