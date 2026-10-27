# Contrato de la integración (2026-10-27)

Se ejecuta en una copia de la ruta solicitada. La base científica y em.cpp se conservan.
La instrucción del usuario de generar el ZIP autoriza implementar el flujo de simulación ya discutido.

## Módulos y orden
1. wifi_rti/acquisition.py: formato por enlace, CSV y emulador; reutiliza WiFiMeasurement de IsukaW.
2. wifi_rti/experiment.py: geometría y reconstrucción existentes, EM C++ y separación de fases.
3. wifi_rti/reporting.py: métricas, sensibilidad, figuras y trazabilidad.
4. docs/: dificultad, frecuencias y vínculo con las diapositivas de redes.

## Condiciones verificables
- RSSI simulado en dBm; diferencias en dB; frecuencia portadora en MHz y tiempo en s.
- RSS = referencia - (W x + ruido); ida y vuelta sin efectos nuevos tolera 1e-10 dB.
- Cada observación conserva fase, sample_id y link_id. Coordenadas verdaderas van en otro archivo.
- Las pérdidas son campos vacíos y valid=False; nunca se convierten en cero.
- Referencia, calibración, huellas, desarrollo y prueba usan corrientes aleatorias separadas.
- Alpha se selecciona con desarrollo, nunca con prueba.
- Se informa cobertura y fallos además del error condicionado a casos válidos.
- Se reutilizan EM en C++ y las funciones RTI/KNN existentes. No se sustituye el algoritmo por Python.
- Se incluyen código MIT y licencia de IsukaW, con revisión y derivaciones identificadas.
- No hay captura física, CSI, difusión electromagnética ni simulación de materiales.
- La frecuencia solo afecta un presupuesto de enlace ilustrativo de espacio libre, con potencias y ganancias explícitas.
- Se entregan pruebas, ejemplo ejecutado, configuración, resultados por caso y hashes.

## Alcance estadístico
Localización en cuadrícula emparejada: las huellas cubren los centros de celda, con ruido independiente.
Las pruebas con correlación/deriva no conservan necesariamente la familia marginal de dos gaussianas.
No se interpretan como robustez a NLoS ni como efecto de una pared. El control Fisher solo cambia alpha/gamma.

