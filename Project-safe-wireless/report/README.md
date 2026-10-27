# Informe editable IEEEtran

`main.tex` es la fuente principal, en inglés, para la entrega de Camilo Vásquez. Usa la clase oficial IEEEtran en modo `conference`, con dos columnas y flujo continuo. El alcance es calibración EM de ruido sintético y una comparación limitada de RTI. El algoritmo EM asignado está implementado en **C++17**; Python se utiliza como apoyo para generación de datos, RTI, validación y gráficas.

## Compilar

Desde la raíz del proyecto:

```powershell
python .\report\compilar_informe.py
```

El compilador busca `tectonic` en PATH, en la variable de entorno `TECTONIC`, o en la ubicación portable de esta máquina:

`C:\Users\THINKPAD\Documents\Codex\Research\tmp\herramientas\tectonic\tectonic.exe`

El binario usado procede de [Tectonic 0.17.0 oficial](https://github.com/tectonic-typesetting/tectonic/releases/tag/tectonic%400.17.0). La primera compilación requiere red para descargar el bundle de paquetes TeX; las posteriores usan la caché de Tectonic. No se realiza una instalación global. Compilación directa equivalente, desde esta carpeta:

```powershell
tectonic --bundle https://data1.fullyjustified.net/tlextras-2022.0r0.tar --keep-logs --keep-intermediates --outdir _build main.tex
```

El helper usa el bundle oficial mediante su URL directa para evitar el relay que falló en esta máquina; puede sustituirse con `TECTONIC_BUNDLE`. Actualiza las copias de las figuras de sus archivos fuente locales, compila `Informe_IEEE_RTI_EM.pdf`, registra sus fuentes y huellas en `provenance.json`, y crea `Overleaf_RTI_EM.zip`. El manuscrito es texto editable; no usa imágenes de páginas como sustituto del contenido.

## Overleaf

Sube `Overleaf_RTI_EM.zip` como proyecto nuevo, selecciona `main.tex` como documento principal y compila con pdfLaTeX. Incluye `main.tex`, `refs.bib`, `enlaces.tex`, la clase y estilo de bibliografía IEEEtran oficiales, las figuras, la trazabilidad y `codigo/em.cpp` como fuente editable del algoritmo. El apéndice incorpora el núcleo desde esa copia del código. Los archivos `IEEEtran.cls` y `IEEEtran.bst` se distribuyen sin modificaciones desde CTAN; sus encabezados conservan sus licencias y datos de autoría.

Los tres campos de enlaces se mantienen en `enlaces.tex`, generado por el actualizador central del repositorio. No sustituyas un campo pendiente por una URL sin verificar. `hyperref` se carga antes de incorporar esas macros para admitir URLs reales y los marcadores actuales.

## Alcance corregido

- Las cifras provienen exclusivamente de `results/python_preliminary`; el control constante predice el centro (3.2, 3.2) m y supera a los métodos con señales en error medio.
- EM ajusta probabilidades y desviaciones de una mezcla de media cero; no localiza por sí solo ni imputa RSSI faltante.
- El escalar Fisher en el reconstruidor equivale a cambiar `alpha` por `alpha/gamma`, con el correspondiente escalado del estabilizador numérico; no pondera enlaces individualmente.
- El artículo fuente informa `gamma=.548`/`.5483`; la integral de sus parámetros redondeados da aproximadamente `.404414`. La discrepancia se documenta sin atribuir una causa inventada.
- No se afirma robustez NLoS, penetración de obstáculos ni una ventaja de velocidad.

La derivación, el ejemplo numérico y el listado del núcleo C++ son parte de la explicación del algoritmo. Los ajustes EM de calibración y sus diagnósticos utilizan el ejecutable compilado desde `em.cpp`, invocado mediante `em_cpp.py`. La versión Python `em_ruido.py` se conserva como referencia de validación. El resto del simulador RTI sigue siendo una herramienta auxiliar Python.

## Fuentes científicas

La bibliografía incluye Dempster, Laird y Rubin (1977), Wu (1983), Wilson y Patwari (2010), y Bahl y Padmanabhan (2000), con sus DOI en `refs.bib`. El PDF institucional del artículo base está identificado en `provenance.json`. Las ecuaciones fuente relevantes son la mezcla (10), información Fisher (15) y Tikhonov (29).
