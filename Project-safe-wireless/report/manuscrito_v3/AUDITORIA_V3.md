# Auditoría editorial de manuscrito V3

## Alcance de esta auditoría

Revisión editorial y de trazabilidad realizada con `nature-publication-workflow`. No equivale a revisión por pares ni valida experimentalmente los resultados.

## Base y preservación

- La V3 parte del `main.tex` que corresponde al PDF V2 compartido por el autor.
- Se guarda en `report/manuscrito_v3/`; el PDF V2 y el `latex_source` antiguo de `report` se dejan intactos.
- La V3 integra los antecedentes y resultados de las etapas 4 y 5, manteniendo separados RTI/RSS sintético, CSI de presencia y la captura RSS de un solo enlace.

## Comprobaciones del archivo

- Resumen: 200 palabras según conteo por espacios/términos del texto extraído.
- 20 entradas bibliográficas; todas las claves citadas tienen entrada y no hay entradas sin citar.
- Las dos figuras usadas por `main.tex` están incluidas junto con `Definitions/mdpi.cls` y los recursos MDPI.
- Se eliminó un encabezado duplicado de “Materials and Methods”.
- Las afirmaciones centrales distinguen resultados simulados, piloto CSI y adquisición RSS; no se declara una fusión ni superioridad validada.

## Límites y asuntos pendientes declarados

- La comparación RTI reporta dos configuraciones de semilla única. El factor Fisher de EM coincide algebraicamente con el control Tikhonov de regularización equivalente; no se afirma que mejore la localización.
- La clasificación CSI se limita a 165 ventanas de tres rondas en un entorno; las etiquetas fueron confirmadas por el estudiante, el rendimiento varía entre rondas y no constituye validación externa.
- La captura RSS de un enlace no se incorpora como resultado de rendimiento de RTI o CSI.
- La variable de respuesta corporal permanece indefinida y nula; no se presenta un umbral universal en dB.
- 1,134 registros de la evidencia bibliográfica siguen pendientes de revisión; no hay exportaciones autenticadas de Scopus/Web of Science. Por ello no se afirma exhaustividad ni prioridad de novedad.
- CSI-GaitCov se cita como recurso potencial, pero no se analizó y su tarea de identificación de marcha no valida detección de presencia.
- La fuente local no documenta decisión institucional de revisión ética ni estado de consentimiento para las grabaciones CSI/RSS. El autor debe confirmar los requisitos aplicables antes de divulgar públicamente.
- La formulación de ponderación EM por enlace y la comparación Monte Carlo son propuestas futuras, todavía no implementadas ni evaluadas.

## Compilación

El autor compartió el PDF compilado en Overleaf y se archivó como `Project_Safe_Wireless_V3.pdf` junto al fuente. Tiene 15 páginas A4; el título y el resumen de los metadatos coinciden con `main.tex`, y las 15 páginas contienen texto seleccionable. Se renderizaron e inspeccionaron las páginas; la página final solo contiene las dos últimas referencias, con espacio blanco amplio, pero no se aprecia texto cortado.

SHA-256 del PDF archivado: `F076600033487DE63BC28FAD79A6C33FBEF12DAF9C530B031329A7D06D952A8B`.

El PDF se conserva sin modificar. La compilación local con Tectonic no pudo completarse porque el servidor de paquetes TeX usado por Tectonic no respondió desde este entorno; por tanto, la revisión visual corresponde al PDF entregado por el autor y no a una recompilación local.
