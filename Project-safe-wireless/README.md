# Project Safe Wireless: propuesta de IA y simulación reproducible

**Curso:** Artificial Intelligence  
**Estudiante:** Camilo Vásquez  
**Institución:** Yachay Tech University  
**Estado:** propuesta y resultados preliminares computacionales  
**Repositorio local:** `Ai-Yachay-2026/Project-safe-wireless`

Esta carpeta contiene la entrega reproducible de la propuesta. `SHA256SUMS.json` permite verificar la integridad de sus archivos; los paquetes ZIP para distribución se mantienen aparte del código del repositorio.

## Demo visual para la exposición

Abre [demo/index.html](demo/index.html) con doble clic, o ejecuta `ABRIR_DEMO.cmd`. Funciona sin internet, sin servidor y sin instalar dependencias. Mantén los archivos de `demo/` juntos. El recorrido para explicar los resultados en clase está en [demo/LEEME.md](demo/LEEME.md).

Para llevar la demo a otro equipo, copia la carpeta `demo/` completa y abre allí `index.html`.

La demo permite seleccionar frecuencia y escenario guardado, comparar RTI/K-NN, recorrer las consultas y ver la calibración EM y las lecturas RSS. Una capa opcional ilustra la señal del modelo de espacio libre (FSPL) desde el nodo seleccionado. Utiliza las nueve ejecuciones preliminares incluidas; cada consulta contiene un objetivo sintético. Los avisos de no convergencia y calibración insuficiente se conservan. El selector cambia entre datos existentes, no modifica un router ni genera mediciones nuevas.

Para regenerarla después de revisar sus archivos de origen:

```powershell
.\.venv\Scripts\python.exe tools/crear_demo.py
```

## ¿Qué investiga el proyecto?

Evalúa si el algoritmo de Expectation-Maximization (EM) puede ajustar un modelo de ruido de mezcla gaussiana a datos sintéticos de intensidad recibida y si ese ajuste ayuda después a estimar la ubicación de un objeto mediante Radio Tomographic Imaging (RTI). Es un estudio de Inteligencia Artificial aplicado a localización por radio. Toda medición se genera en el simulador: el proyecto no necesita cámara, router en modo de captura, CSI ni datos recogidos en una habitación.

A largo plazo, la motivación es investigar si un sistema de radio puede apoyar la búsqueda de personas bajo escombros. Esta primera etapa localiza un objetivo de atenuación sintético y no incorpora escombros ni propiedades de materiales. Cada consulta de prueba contiene un objetivo, así que los resultados actuales miden localización, no detección de presencia o capacidad de rescate.

La pregunta de investigación, los artículos relacionados, la metodología y los resultados preliminares están en [la propuesta de investigación](docs/Propuesta_IA_RTI_EM.md) y en su versión PDF [Propuesta_IA_RTI_EM.pdf](report/Propuesta_IA_RTI_EM.pdf).

Para regenerar el PDF desde el Markdown, instala la dependencia documental opcional en el entorno virtual y ejecuta el generador:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements_docs.txt
.\.venv\Scripts\python.exe tools/render_proposal_pdf.py
```

El repositorio de IsukaW sirve como referencia para el formato de medición y la arquitectura de detección de presencia. Su programa principal combina cámara y cambios de RSSI mediante reglas; los módulos de fusión y aprendizaje automático funcionan por separado. En esta entrega reutilizamos el contrato `WiFiMeasurement` para registrar los datos por enlace. La simulación genera esos datos y ejecuta la cadena RTI-EM sin captura física. La revisión del código y la procedencia están documentadas en `docs/ARQUITECTURA_Y_EJECUCION.md` y `docs/ORIGEN_Y_LICENCIAS.md`.

## Reproducir el experimento preliminar

Se requiere Python 3.10 o posterior y un compilador `g++` compatible con C++17. En Windows, abre PowerShell en esta carpeta y ejecuta:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
g++ --version
.\.venv\Scripts\python.exe ejecutar_integracion.py --quick --suite --output results/reproduccion_propuesta
```

La salida debe ser una carpeta nueva. El comando ejecuta nueve escenarios con semilla inicial 7: caso base, ruido elevado, cuantización, ruido correlacionado, pérdida de enlaces, deriva, 5 GHz con margen amplio y márgenes bajos a 2,4 y 5 GHz. La compilación de EM en C++ se realiza desde la integración. Si PowerShell no encuentra `g++`, instala MinGW-w64/MSYS2 y vuelve a abrir la terminal; también puedes fijar la ruta del compilador antes de ejecutar:

```powershell
$env:CXX = 'C:\msys64\mingw64\bin\g++.exe'
```

Para la configuración de estudio con 12 nodos, 66 enlaces y 100 celdas:

```powershell
.\.venv\Scripts\python.exe ejecutar_integracion.py --config config_integracion/base.json --output results/reproduccion_completa
```

Para repetir los nueve escenarios rápidos diez veces con semillas independientes:

```powershell
.\.venv\Scripts\python.exe ejecutar_integracion.py --quick --suite --replicas 10 --output results/repeticiones_10
```

Cada escenario guarda los datos sintéticos por etapa en `raw/`, la verdad de posición separada, las predicciones y `summary.json`. El resumen registra los parámetros, convergencia de EM, densidad predictiva, cobertura, errores y hashes del código utilizado. `comparison.csv` reúne las métricas; `comparison.png` presenta el resumen. `frequency_reference.csv` contiene únicamente el cálculo ilustrativo de espacio libre.

El paquete incluye el resultado rápido usado en la propuesta (`results/integracion_verificada/`) y una ejecución base más grande (`results/integracion_completa/`). Puedes comprobar la integridad de los archivos incluidos con:

```powershell
.\.venv\Scripts\python.exe verificar_paquete.py
```

El experimento usa particiones independientes para referencia, calibración, validación del ruido, huellas, desarrollo y prueba. Los parámetros de RTI y K-NN se seleccionan con desarrollo. La prueba usa posiciones de una cuadrícula que también está representada en las huellas, aunque con realizaciones de ruido independientes; por ello, se interpreta como evaluación *matched-grid*, no como generalización a un lugar o una cuadrícula nuevos.

## Resultado preliminar que debe poder reproducirse

El caso base rápido usa seis nodos, 15 enlaces, 36 celdas y 30 consultas de prueba. El error es distancia euclidiana media en metros; RMSE es la raíz del error cuadrático medio. Los valores salen de `results/integracion_verificada/base_r00/summary.json`.

| Método | Error medio (m) | RMSE (m) |
|---|---:|---:|
| RTI con Tikhonov | 3.653 | 4.113 |
| RTI con escala Fisher estimada por EM | 3.530 | 4.015 |
| Tikhonov equivalente con igual regularización | 3.530 | 4.015 |
| K-NN ponderado | 2.529 | 2.836 |
| Centro constante del área | 2.357 | 2.517 |

En este piloto el control del centro obtiene el menor error. K-NN queda por debajo de ambas variantes RTI, y la variante Fisher coincide con el Tikhonov de regularización equivalente. El resultado confirma que el flujo puede ejecutarse, pero no demuestra una mejora de localización atribuible a EM. En la validación base, la mezcla obtiene una densidad logarítmica algo mayor que la gaussiana única (`-2.101` frente a `-2.145` por observación; n=450). Esta métrica evalúa el ajuste del ruido; por sí sola no indica la precisión espacial.

## Qué se propone completar para el proyecto

La evaluación final repetirá los escenarios con varias semillas y comparará la densidad predictiva del ruido con el error de localización, además de informar cobertura y convergencia. El control Tikhonov equivalente permite determinar si la escala Fisher cambia algo más que la intensidad de regularización. Los resultados actuales corresponden a una ejecución preliminar por escenario y aún no permiten estimar la variabilidad entre ejecuciones.

Antes de enviar la propuesta, el autor debe insertar la Figura 1 del sistema y completar el nombre del docente. El diagrama debe cumplir la instrucción de diseño personal establecida por la materia.

## Archivos principales

- `ejecutar_integracion.py`: punto de entrada del simulador.
- `wifi_rti/`: generador sintético, contrato de mediciones, EM, RTI/K-NN y evaluación.
- `em.cpp`, `em_cpp.py`, `compilar_cpp.py`: estimador EM original de Wireless Save y su adaptador.
- `config_integracion/base.json`: configuración del experimento de mayor tamaño.
- `vendor/wifi_sensing_human_presence/LICENSE`: licencia MIT del código reutilizado; su origen y revisión se documentan en `docs/ORIGEN_Y_LICENCIAS.md`.
- `results/integracion_verificada/`: nueve escenarios preliminares de ejecución corta.
- `results/integracion_completa/`: escenario base con más enlaces, celdas y consultas.
- `report/Propuesta_IA_RTI_EM.pdf`: propuesta de investigación de esta entrega.
- `docs/`: fuente editable de la propuesta, arquitectura, evidencia, procedencia y trazabilidad de resultados.
- `tools/`: generación reproducible del PDF y del visor de resultados.
- `test_*.py`: comprobaciones de serialización, evaluación y paridad del algoritmo EM.

El flujo principal necesita solo `requirements.txt` y C++17. Los paquetes de `requirements_opcionales.txt` habilitan estadísticas de diagnóstico reutilizadas del repositorio de IsukaW; no intervienen en EM ni en RTI.

Para ejecutar todas las comprobaciones automatizadas, instala también las dependencias de esos diagnósticos:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements_opcionales.txt
.\.venv\Scripts\python.exe -B -m unittest discover -p 'test_*.py' -v
```

Las cachés, el entorno virtual, `build/`, `tmp/`, las figuras generadas en la raíz y la salida de trabajo predeterminada `results/integracion_nueva/` se crean localmente y están excluidos de Git. La entrega conserva las ejecuciones verificadas y el escenario completo que se describen en este README.

## Fuente y estado de publicación

El repositorio de la entrega es [Project-safe-wireless en GitHub](https://github.com/Camimilo-11/Ai-Yachay-2026/tree/main/Project-safe-wireless). Cada ejecución registra configuración, semilla y hashes del código en su resumen para identificar la versión que produjo los resultados.

El alcance se limita a datos sintéticos y a la evaluación de RTI y K-NN en el modelo implementado. El simulador no mide canales Wi-Fi, CSI, propagación a través de paredes ni detección de personas.
