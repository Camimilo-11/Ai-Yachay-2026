# Resultados preliminares

Esta carpeta muestra los resultados calculados y guardados para la propuesta. Las ejecuciones usan datos simulados; no son capturas Wi-Fi ni pruebas físicas.

La comparación rápida tiene seis nodos, quince enlaces, 36 celdas y treinta consultas de prueba. Su error medio fue 3,653 m con RTI de Tikhonov, 3,530 m con el factor Fisher derivado de EM, 2,529 m con K-NN y 2,357 m para el control del centro. El control del centro queda mejor en ese piloto. La variante Fisher coincide con el control de Tikhonov de regularización equivalente.

La comparación completa usa doce nodos, 66 enlaces, cien celdas y 120 consultas. RTI obtuvo 2,333 m de error medio, RTI con Fisher 2,433 m, K-NN 2,408 m y el centro 2,483 m. El piloto rápido y la configuración completa tienen distinta geometría y número de casos; se informan por separado.

Los archivos `comparison.csv` contienen cobertura y métricas por método. Las figuras permiten una vista general de todos los escenarios. Los resúmenes JSON conservan configuración, parámetros estimados, convergencia y procedencia. Los CSV crudos completos están en `results/` dentro del ZIP reproducible.

| Archivo | Contenido |
|---|---|
| `integracion_verificada_comparison.png` y `.csv` | Nueve escenarios rápidos de estrés, con treinta consultas por caso. |
| `integracion_verificada_base_summary.json` | Configuración y cifras del piloto base usadas en la propuesta. |
| `integracion_completa_comparison.png` y `.csv` | Comparación con doce nodos y 120 consultas. |
| `integracion_completa_base_summary.json` | Configuración y resumen de la corrida base completa. |

Consulta la sección de resultados preliminares del PDF para su interpretación, métricas y limitaciones. La generación completa, incluidos los archivos CSV originales y las instrucciones, está dentro del ZIP.
