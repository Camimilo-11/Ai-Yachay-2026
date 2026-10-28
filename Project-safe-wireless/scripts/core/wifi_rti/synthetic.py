"""Generación de tablas RSS sintéticas. No consulta adaptadores ni cámaras."""
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import json
import numpy as np
from simulacion_rti_em_knn import perimeter_nodes, grid_centers, make_links, elliptical_weights, draw_mixture_noise
from .acquisition import observation_records, write_records, read_records, reconstruct_scan
from .radio import budget_dbm, reception_threshold_dbm

@dataclass
class Config:
    seed: int = 7
    nodes: int = 12
    grid_size: int = 10
    room_m: float = 6.4
    ellipse_width_m: float = .15
    target_attenuation_db: float = 4.
    reference_frames: int = 80
    calibration_frames: int = 100
    noise_validation_frames: int = 60
    fingerprints_per_position: int = 5
    development_frames: int = 60
    test_frames: int = 120
    sample_interval_s: float = .5
    p_narrow: float = .548
    sigma_narrow_db: float = .971
    sigma_wide_db: float = 3.003
    quantization_db: float = 0.
    rho: float = 0.
    loss_rate: float = 0.
    drift_db_per_s: float = 0.
    link_noise_spread: float = 0.
    carrier_mhz: float = 2400.
    tx_power_dbm: float = 0.
    tx_gain_dbi: float = 0.
    rx_gain_dbi: float = 0.
    extra_loss_db: float = 0.
    receiver_sensitivity_dbm: float = -95.
    bandwidth_mhz: float = 20.
    noise_figure_db: float = 7.
    required_snr_db: float = 0.
    alpha_values: tuple = (.03,.1,.3,1.)
    knn_values: tuple = (1,3,5)
    min_links: int = 3
    export_upstream_features: bool = False

    def validate(self):
        counts=['nodes','grid_size','reference_frames','calibration_frames','noise_validation_frames',
                'fingerprints_per_position','development_frames','test_frames','min_links','seed']
        for name in counts:
            value=getattr(self,name)
            if not isinstance(value,int) or isinstance(value,bool) or value < (0 if name=='seed' else 1):
                raise ValueError(f"{name}: entero positivo requerido.")
        if not 4<=self.nodes<=32 or not 4<=self.grid_size<=20:
            raise ValueError("nodes en [4,32]; grid_size en [4,20].")
        for key,value in asdict(self).items():
            if isinstance(value,(float,int)) and not np.isfinite(value): raise ValueError(f"{key} no finito.")
        if min(self.room_m,self.sample_interval_s,self.carrier_mhz,self.bandwidth_mhz,self.target_attenuation_db)<=0:
            raise ValueError("Distancia, tiempo, frecuencia, banda y atenuación deben ser positivos.")
        if self.ellipse_width_m<0 or self.quantization_db<0 or self.extra_loss_db<0:
            raise ValueError("Ancho de elipse, cuantización y pérdida extra no negativos.")
        if not 0<=self.loss_rate<1 or not abs(self.rho)<1 or not 0<=self.link_noise_spread<1:
            raise ValueError("Pérdida, correlación o heterogeneidad fuera de rango.")
        if not 0<self.p_narrow<1 or not 0<self.sigma_narrow_db<self.sigma_wide_db:
            raise ValueError("Mezcla requiere 0<p<1 y 0<sigma1<sigma2.")
        if min(self.reference_frames,self.calibration_frames)<20:
            raise ValueError("Referencia y calibración requieren al menos 20 barridos.")
        if self.min_links>self.nodes*(self.nodes-1)//2: raise ValueError("min_links excede la geometría.")
        if not self.alpha_values or not all(np.isfinite(x) and x>0 for x in self.alpha_values):
            raise ValueError("alpha_values positivos y finitos requeridos.")
        if not self.knn_values or not all(isinstance(x,int) and x>0 for x in self.knn_values):
            raise ValueError("knn_values enteros positivos requeridos.")


def make_dataset(config, output):
    config.validate();output=Path(output);(output/'raw').mkdir(parents=True)
    nodes=perimeter_nodes(config.nodes,config.room_m);pixels=grid_centers(config.grid_size,config.room_m)
    pairs,a,b=make_links(nodes);weights=elliptical_weights(a,b,pixels,config.ellipse_width_m)
    baseline=budget_dbm(np.linalg.norm(a-b,axis=1),config);m=len(pairs)
    np.savez_compressed(output/'geometry.npz',nodes=nodes,pixels=pixels,pairs=pairs,weights=weights)
    counts=dict(reference=config.reference_frames,calibration=config.calibration_frames,
                noise_validation=config.noise_validation_frames,fingerprint=len(pixels)*config.fingerprints_per_position,
                development=config.development_frames,test=config.test_frames)
    streams=np.random.SeedSequence(config.seed).spawn(len(counts));data={};truth=[];clock=0.;quant_error=0.;csv_error=0.
    for (phase,frames),stream in zip(counts.items(),streams):
        r_noise,r_positions,r_drop=[np.random.default_rng(s) for s in stream.spawn(3)]
        if phase=='fingerprint':indices=np.repeat(np.arange(len(pixels)),config.fingerprints_per_position)
        elif phase in {'development','test'}:indices=r_positions.integers(0,len(pixels),frames)
        else:indices=np.full(frames,-1,dtype=int)
        previous=draw_mixture_noise(r_noise,m,config.p_narrow,config.sigma_narrow_db,config.sigma_wide_db)
        scales=np.linspace(1-config.link_noise_spread,1+config.link_noise_spread,m)
        rows=[]
        for sample_id,index in enumerate(indices):
            innovation=draw_mixture_noise(r_noise,m,config.p_narrow,config.sigma_narrow_db,config.sigma_wide_db)
            previous=config.rho*previous+np.sqrt(1-config.rho**2)*innovation
            clean=np.zeros(m) if index<0 else weights[:,index]*config.target_attenuation_db
            # Deriva global entre fases; no se cancela reiniciándola por consulta.
            elapsed=clock+sample_id*config.sample_interval_s
            changes=clean+previous*scales+config.drift_db_per_s*elapsed
            rss=baseline-changes
            valid=(r_drop.random(m)>=config.loss_rate)&(rss>=reception_threshold_dbm(config))
            block=observation_records(baseline,changes,pairs,phase,sample_id,elapsed,config.carrier_mhz,valid)
            if config.quantization_db:
                for row in block:
                    if row['valid']:row['signal_strength']=float(np.rint(row['signal_strength']/config.quantization_db)*config.quantization_db)
            recovered,mask=reconstruct_scan(block,baseline,pairs)
            if mask.any():quant_error=max(quant_error,float(np.max(np.abs(recovered[mask]-changes[mask]))))
            rows.extend(block)
            if index>=0:truth.append(dict(phase=phase,sample_id=sample_id,pixel_index=int(index),x_true_m=float(pixels[index,0]),y_true_m=float(pixels[index,1])))
        expected=np.array([r['signal_strength'] if r['valid'] else np.nan for r in rows]).reshape(frames,m)
        path=output/'raw'/f'{phase}.csv';write_records(path,rows)
        restored=read_records(path)
        # Se reconstruye desde el CSV guardado, no desde la matriz original.
        signals=np.full((frames,m),np.nan)
        if len(restored)!=frames*m:raise ValueError('CSV perdió observaciones.')
        for sample_id in range(frames):
            block=restored[sample_id*m:(sample_id+1)*m]
            if any(r['sample_id']!=sample_id or r['phase']!=phase for r in block):
                raise ValueError('CSV contiene barridos incompatibles.')
            reconstruct_scan(block,baseline,pairs)
        for row in restored:
            if row['valid']:signals[row['sample_id'],row['link_id']]=row['signal_strength']
        if not np.array_equal(np.isfinite(expected),np.isfinite(signals)):
            raise ValueError('CSV alteró la máscara de validez.')
        finite=np.isfinite(expected)
        if finite.any():csv_error=max(csv_error,float(np.max(np.abs(expected[finite]-signals[finite]))))
        if csv_error>1e-10:raise ValueError('CSV alteró las lecturas guardadas.')
        data[phase]={'signals':signals,'rows':restored,'indices':indices}
        clock+=frames*config.sample_interval_s+10.
    with (output/'ground_truth.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['phase','sample_id','pixel_index','x_true_m','y_true_m'])
        writer.writeheader();writer.writerows(truth)
    # Verdad separada, usada por el generador/evaluador; no se envía a EM.
    (output/'config.json').write_text(json.dumps(asdict(config),indent=2),encoding='utf-8')
    return data,baseline,nodes,pixels,pairs,weights,csv_error,quant_error

