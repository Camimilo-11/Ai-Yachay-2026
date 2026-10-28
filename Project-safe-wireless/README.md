# Safe Wireless — propuesta de Inteligencia Artificial

**Estudiante:** Camilo Vásquez · **Yachay Tech**

La entrega analiza una simulación reproducible de localización RTI con RSS sintético, calibración de ruido con EM y comparación con K-NN. No requiere capturar datos de un router. La meta futura de búsqueda bajo escombros es motivación; esta etapa no simula escombros ni detecta personas.

## Empieza por aquí

- [Reporte de investigación en PDF](report/Propuesta_IA_RTI_EM.pdf)
- [Demo visual para la exposición](demo/index.html) · abre `index.html` en el navegador; funciona sin internet.
- [Resultados preliminares](resultados_preliminares/README.md) · gráficos, métricas y resúmenes.
- [Scripts principales](scripts/LEER_SCRIPTS.md)
- [Descarga el ZIP completo de reproducción](Project-safe-wireless-reproduccion.zip) y extrae la carpeta antes de ejecutar.

## Descargar y reproducir

Descarga el ZIP desde el enlace anterior, extrae la carpeta completa `Project-safe-wireless` y abre PowerShell en esa carpeta. Se requiere Python 3.10 o posterior y un compilador `g++` con C++17.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
python .\scripts\verificar_paquete.py
python .\scripts\ejecutar_integracion.py --quick --suite --output results\reproduccion_propuesta
```

El último comando ejecuta nueve escenarios cortos. Para la configuración completa (12 nodos y 100 celdas):

```powershell
python .\scripts\ejecutar_integracion.py --config config_integracion\base.json --output results\reproduccion_completa
```

Cada corrida requiere una carpeta de salida nueva. Si Windows no encuentra `g++`, instala MinGW-w64/MSYS2 o define `CXX` antes de ejecutar:

```powershell
$env:CXX = 'C:\msys64\mingw64\bin\g++.exe'
```

El ZIP incluye los scripts, datos crudos, configuración, requisitos, código fuente de la propuesta, licencia del código adaptado, demo y documentación necesaria para repetir la simulación. Los scripts de Python son el flujo de reproducción; no hace falta un Jupyter Notebook.

## Cómo responde a la rúbrica

El PDF presenta el problema, la pregunta de investigación, la literatura, la metodología, los resultados preliminares, los controles y el alcance. Incluye un cronograma de cuatro semanas con una quinta opcional. La carpeta de resultados conserva las tablas, figuras y resúmenes que respaldan los resultados reportados; el ZIP permite regenerarlos.

El PDF ya incluye el nombre del docente y la Figura 1: un diagrama del flujo que conecta la generación de datos sintéticos, la calibración EM y la evaluación de localización. La demo complementa esa explicación con una vista interactiva de la simulación.

## Enlaces

- [Repositorio del proyecto](https://github.com/Camimilo-11/Ai-Yachay-2026/tree/main/Project-safe-wireless)
- [Ver resultados y trazabilidad](resultados_preliminares/README.md)
