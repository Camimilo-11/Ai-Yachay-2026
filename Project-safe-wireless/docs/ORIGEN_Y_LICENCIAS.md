# Origen y licencias

Esta entrega integra el estimador EM en C++17 y las funciones geométricas, RTI y K-NN de la base Wireless Save con un adaptador de datos sintéticos. Los archivos `em.cpp`, `em_cpp.py`, `compilar_cpp.py` y `simulacion_rti_em_knn.py` forman parte del código necesario para ejecutar y verificar el estudio.

El código de IsukaW procede de la revisión
91aee04ea938274d014a3981d409f83267ea15c0 de
https://github.com/IsukaW/wifi-sensing-human-presence.
La revisión original puede consultarse en GitHub. Esta entrega conserva los adaptadores que utiliza la simulación y el aviso de licencia correspondiente.

La licencia MIT y su aviso de autoría se conservan en
vendor/wifi_sensing_human_presence/LICENSE. WiFiMeasurement y WiFiFeatureExtractor
se reutilizan con su lógica original en wifi_rti/upstream_contract.py y
wifi_rti/upstream_features.py; se redujeron los imports para evitar acceder a hardware.
El extractor es opcional y no participa en el ajuste EM ni en la reconstrucción RTI.

La licencia del proveedor se aplica a su código; esta entrega no atribuye una licencia nueva a Wireless Save. Los resultados de la propuesta proceden de las simulaciones identificadas por sus configuraciones, semillas y hashes de fuente en `summary.json`. Los informes y resultados de protocolos anteriores se mantienen fuera de esta entrega.
