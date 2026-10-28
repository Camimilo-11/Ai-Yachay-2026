# Scripts principales

El código fuente completo y los archivos necesarios para ejecutar estos scripts están en el ZIP de reproducción, en la raíz del proyecto extraído. Abre PowerShell en esa carpeta antes de ejecutar los comandos.

| Script | Para qué sirve |
|---|---|
| `ejecutar_integracion.py` | Punto de entrada. Genera datos sintéticos, ajusta EM y compara RTI y K-NN. |
| `verificar_paquete.py` | Comprueba los SHA-256 del contenido distribuido. |
| `crear_paquete_reproduccion.py` | Vuelve a construir el ZIP completo desde el proyecto extraído. |
| `core/em.cpp` | Implementa la estimación EM de la mezcla gaussiana. |
| `core/wifi_rti/synthetic.py` | Genera las mediciones RSS sintéticas por etapa. |
| `core/wifi_rti/experiment.py` | Coordina EM, validación de ruido, comparación y resultados. |
| `core/wifi_rti/evaluation.py` | Ajusta los controles en desarrollo y mide la localización en prueba. |

`core/` contiene los módulos auxiliares y las pruebas. Los comandos de instalación y ejecución están en el README principal. El ejecutable compilado se genera localmente al correr la integración.
