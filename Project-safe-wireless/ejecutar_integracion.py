#!/usr/bin/env python3
"""Ejecuta solo simulación; no accede a cámara ni interfaces WiFi."""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
from wifi_rti.experiment import Config, run_experiment
from wifi_rti.reporting import create_reports

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,help='JSON de parámetros; ver config_integracion/base.json.')
    parser.add_argument('--output',type=Path,default=Path('results/integracion_nueva'))
    parser.add_argument('--quick',action='store_true',help='6 nodos, grilla 6x6 y menos casos.')
    parser.add_argument('--suite',action='store_true',help='Comparar ruido, pérdidas, cuantización, deriva y frecuencia.')
    parser.add_argument('--replicas',type=int,default=1)
    parser.add_argument('--features-upstream',action='store_true',help='Diagnóstico opcional; requiere requirements_opcionales.txt.')
    args=parser.parse_args()
    if not 1<=args.replicas<=50:parser.error('--replicas debe estar entre 1 y 50.')
    config=Config(**json.loads(args.config.read_text(encoding='utf-8'))) if args.config else Config()
    if args.quick:config=replace(config,nodes=6,grid_size=6,reference_frames=40,calibration_frames=60,
        noise_validation_frames=30,fingerprints_per_position=3,development_frames=20,test_frames=30)
    config=replace(config,export_upstream_features=args.features_upstream)
    config.validate()
    if args.output.exists() and any(args.output.iterdir()):parser.error('La salida debe ser una carpeta nueva.')
    args.output.mkdir(parents=True,exist_ok=True)
    scenarios={'base':{}}
    if args.suite:scenarios.update(ruido_alto={'sigma_wide_db':7.},cuantizacion={'quantization_db':2.},
        correlacion={'rho':.8},perdidas={'loss_rate':.35},deriva={'drift_db_per_s':.02},
        frecuencia_5ghz={'carrier_mhz':5000.},
        margen_24ghz={'extra_loss_db':28.,'receiver_sensitivity_dbm':-82.},
        margen_5ghz={'extra_loss_db':28.,'receiver_sensitivity_dbm':-82.,'carrier_mhz':5000.})
    results=[]
    for replica in range(args.replicas):
        for name,changes in scenarios.items():
            specific=replace(config,seed=config.seed+replica*100003,**changes)
            result=run_experiment(specific,args.output/f'{name}_r{replica:02d}')
            results.append((name,replica,result))
            print(f"{name} r{replica}: {result['status']}; {result['observed_links']}/{result['total_links']} enlaces",flush=True)
    create_reports(args.output,results)
    manifest={'mode':'simulation','replicas':args.replicas,'scenarios':list(scenarios),
              'steps':'generar -> EM C++ -> RTI/KNN -> comparar','base_config':asdict(config)}
    (args.output/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f"Resultados: {args.output.resolve()}")

if __name__=='__main__':main()

