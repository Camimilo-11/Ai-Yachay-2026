"""Salidas derivadas de las ejecuciones sintéticas, sin cifras prefabricadas."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .radio import fspl_db, noise_floor_dbm, C_M_S

def create_reports(output, summaries):
    output=Path(output)
    rows=[]
    for scenario,replica,summary in summaries:
        for method,metric in summary.get('metrics',{}).items():
            rows.append({'scenario':scenario,'replica':replica,'method':method,
                'status':summary['status'],**metric})
    if rows:
        with (output/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        cases=list(dict.fromkeys(r['scenario'] for r in rows))
        methods=['Centro_constante','KNN','RTI_Tikhonov','RTI_EM_Fisher']
        fig,ax=plt.subplots(figsize=(11,5))
        for j,method in enumerate(methods):
            values=[np.mean([r['mean_error_with_center_fallback_m'] for r in rows if r['scenario']==name and r['method']==method]) for name in cases]
            ax.bar(np.arange(len(cases))+(j-1.5)*.19,values,width=.18,label=method)
        ax.set_xticks(np.arange(len(cases)),cases,rotation=25,ha='right',fontsize=8)
        ax.set_ylabel('Error medio (m); centro en casos sin salida')
        ax.set_title('Comparación exploratoria con datos sintéticos')
        ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2);fig.tight_layout()
        fig.savefig(output/'comparison.png',dpi=180);plt.close(fig)
    radio=[{'carrier_mhz':f,'wavelength_cm':100*C_M_S/(f*1e6),'fspl_10m_db':float(fspl_db(10,f)),
            'extra_vs_2400_db':float(fspl_db(10,f)-fspl_db(10,2400))} for f in [2400,5000,6000]]
    with (output/'frequency_reference.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(radio[0]));writer.writeheader();writer.writerows(radio)
    notes=['# Ejecución de integración sintética','',
           'No son mediciones WiFi ni resultados de materiales. Cada escenario se identifica con su configuración.',
           'El error con fallback incluye el centro si no hay suficientes enlaces; comparison.csv también informa cobertura.',
           'Huellas y prueba comparten cuadrícula; no es evaluación de posiciones nuevas.','']
    for name,replica,result in summaries:
        notes.append(f"- {name}, réplica {replica}: {result['status']}; enlaces {result['observed_links']}/{result['total_links']}.")
    notes+=['','La portadora afecta solo el presupuesto FSPL y el censurado. Si no hay censurado, restar la referencia cancela la pérdida estática.',
            'El ancho de banda solo cambia el piso térmico del modelo. No modifica por sí mismo la varianza RSS elegida.',
            'Con rho o deriva la mezcla marginal real puede dejar de ser la familia GMM de partida.',
            'Una sola réplica ilustra funcionamiento; no acredita superioridad estadística.']
    (output/'LEER_RESULTADOS.md').write_text('\n'.join(notes)+'\n',encoding='utf-8')

