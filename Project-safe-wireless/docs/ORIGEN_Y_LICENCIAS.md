# Origen y licencias

Esta entrega integra una copia de Wireless Save con un adaptador exclusivamente sintético.
El inventario original y sus hashes están en base_snapshot.json; el README original está
en README_BASE_ORIGINAL.md. La carpeta de origen no se modifica.

El código de IsukaW procede de la revisión
91aee04ea938274d014a3981d409f83267ea15c0 de
https://github.com/IsukaW/wifi-sensing-human-presence.
Los 28 archivos conservados se verificaron contra sus identificadores de objeto Git;
el inventario está en upstream_blob_hashes.json. Se omiten el entorno virtual y las
instrucciones de herramientas de .github, ajenos a la ejecución científica.

La licencia MIT y su aviso de autoría se conservan en
vendor/wifi_sensing_human_presence/LICENSE. WiFiMeasurement y WiFiFeatureExtractor
se reutilizan con su lógica original en wifi_rti/upstream_contract.py y
wifi_rti/upstream_features.py; se redujeron los imports para evitar acceder a hardware.
El extractor es opcional y no participa en el ajuste EM ni en la reconstrucción RTI.

La licencia del proveedor se aplica a su código; esta entrega no atribuye una licencia
nueva a Wireless Save. El material docente se cita en el informe y no se redistribuye.
Los resultados y figuras nuevos proceden de las simulaciones identificadas por sus
configuraciones y semillas. Los resultados históricos de la base se identifican aparte.
