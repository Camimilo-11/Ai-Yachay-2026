# EM para calibración de ruido RSS: estudio sintético con RTI

Proyecto de Análisis de Algoritmos de Camilo Vásquez. La entrega del algoritmo asignado debe ser en **C++17**. El objetivo principal es explicar y evaluar EM para estimar una mezcla de dos gaussianas con medias fijadas en cero.

## Archivos para grabar y entregar

- `slides/Presentacion_RTI_EM.pdf`: diapositivas para la grabación.
- `slides/Presentacion_RTI_EM.pptx`: presentación editable.
- `notes/guion_presentacion_10_min.md`: guion en español con tiempos de referencia.
- `notes/guia_defensa_em.md`: preguntas para preparar la defensa.
- `report/Informe_IEEE_RTI_EM.pdf`: informe en plantilla IEEE Conference.
- `report/main.tex` y `report/Overleaf_RTI_EM.zip`: manuscrito editable y paquete para Overleaf.
- `em.cpp`: implementación C++17 de EM y demostración que se muestra al explicar el algoritmo.
- `compilar_cpp.py`: ayuda para compilar el ejecutable con g++ sin dependencias externas de C++.
- `em_cpp.py`: adaptador para usar el ejecutable C++ desde los experimentos auxiliares en Python.

## Compilar y mostrar el algoritmo C++

Requiere g++ con soporte C++17. El núcleo utiliza únicamente la biblioteca estándar. Desde esta carpeta:

```powershell
python .\compilar_cpp.py
.\build\em.exe --demo
```

El helper ejecuta g++ y crea el programa nativo. El ejemplo muestra una iteración E/M sobre cuatro residuos, sin necesitar datos Wi-Fi ni NumPy.

## Ejecutar los experimentos auxiliares

Python 3.10 o posterior, NumPy y Matplotlib generan datos y gráficas. **Todos los ajustes EM los ejecuta el programa C++** mediante el adaptador. Desde esta carpeta:

```powershell
python -m pip install -r requirements.txt
python .\simulacion_rti_em_knn.py --output-dir .\results\python_preliminary
python .\analizar_resultados.py
```

El escenario principal usa semilla 7, 12 nodos, 66 enlaces, 100 píxeles, 500 consultas, 5.000 residuos de calibración, 20 réplicas por tamaño muestral y 20 inicializaciones. Los argumentos efectivos se guardan en `results/python_preliminary/parametros.json`.

`em.cpp` contiene las actualizaciones E/M. `em_ruido.py` se conserva solo como referencia Python para comprobar la paridad del port, no como implementación de entrega. El simulador organiza geometría, generación y reconstrucción RTI/KNN. El analizador valida IDs de caso, calcula comparaciones pareadas y crea las figuras. La generación de documentos es independiente del algoritmo que se explica.

## Resultados e interpretación

Los errores de recuperación de parámetros tienden a disminuir al aumentar las muestras. Veinte inicios sobre una muestra llegan a estimaciones muy similares. Ese resultado no garantiza un máximo global en cualquier conjunto.

En localización, el centro constante obtiene **2.407 m** de error medio, frente a **2.618 m** de KNN, **3.062 m** de la extensión Fisher y **3.244 m** de Tikhonov. La comparación no demuestra utilidad media de esos localizadores frente al control. El factor Fisher modifica la regularización efectiva a alpha/gamma, por lo que la mejora frente a alpha fijo no aísla una ventaja de EM.

Todas las observaciones son sintéticas. El código no simula ondas, CSI ni penetración en paredes o escombros. EM estima parámetros globales de ruido y no imputa enlaces perdidos. El artículo de Wilson y Patwari aporta valores de referencia para el generador y utiliza radios IEEE 802.15.4.

`resultados_rti/` conserva una corrida antigua. Informe y slides usan exclusivamente `results/python_preliminary/`. Los mini tests externos de penalización y EM robusto no se mezclan con esta entrega.

## Añadir los enlaces

Los enlaces reales se guardan en `docs/enlaces_entrega.json`. Cuando estén disponibles:

```powershell
python .\actualizar_enlaces.py --overleaf URL_REAL --github URL_REAL --video URL_REAL
python .\generar_entregables.py --solo-informe
```

El script actualiza el anexo y su archivo LaTeX. Después hay que recompilar y volver a cargar el informe actualizado en Moodle. Los campos sin enlace permanecen identificados como pendientes.

## Regenerar documentos

`python .\generar_entregables.py` coordina análisis, compilación del informe y presentación. El compilador local incluido requiere Tectonic. También se puede compilar el manuscrito con LaTeX/IEEEtran o en Overleaf. En este entorno las slides se construyen con Node.js y `@oai/artifact-tool`, y se convierten a PDF con LibreOffice. Fuera de Codex puedes editar directamente el PPTX en PowerPoint o LibreOffice. Estos requisitos de edición son independientes de las bibliotecas del experimento.

Antes de entregar, comprueba los enlaces del anexo, ambos PDF, la duración real de la grabación y las instrucciones de Moodle. Consulta `docs/alcance_y_limitaciones.md` para los límites científicos.
