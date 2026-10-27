"""Datos sintéticos -> EM C++ -> RTI/K-NN. Sin captura física."""
from dataclasses import asdict
from pathlib import Path
import csv
import hashlib
import json
import platform
import numpy as np
from em_cpp import fit_zero_mean_gmm_em, backend_metadata
from simulacion_rti_em_knn import fisher_information_gamma, gmm_log_likelihood
from .synthetic import Config, make_dataset
from .evaluation import Evaluator


def finite_mean(matrix, axis=0):
    counts=np.isfinite(matrix).sum(axis=axis)
    return np.divide(np.nansum(matrix,axis=axis),counts,
                     out=np.full(np.shape(counts),np.nan,dtype=float),where=counts>0)


def save_json(path, data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def source_provenance():
    root=Path(__file__).resolve().parents[1]
    paths=[root/name for name in ['em.cpp','em_cpp.py','compilar_cpp.py','simulacion_rti_em_knn.py',
                                  'ejecutar_integracion.py','requirements.txt','requirements_opcionales.txt']]
    paths+=list((root/'wifi_rti').glob('*.py'))
    hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return {'python':platform.python_version(),'numpy':np.__version__,'source_sha256':hashes,
            'upstream_revision':'91aee04ea938274d014a3981d409f83267ea15c0'}


def run_experiment(config, output):
    config.validate();output=Path(output)
    if output.exists() and any(output.iterdir()):raise FileExistsError("Utiliza una carpeta de salida nueva.")
    data,b_true,nodes,pixels,pairs,weights,roundtrip,quant_error=make_dataset(config,output)
    reference=finite_mean(data['reference']['signals'])
    residual_matrix=reference-data['calibration']['signals']
    residuals=residual_matrix[np.isfinite(residual_matrix)]
    summary={'status':'ok','source':'simulation','evaluation_protocol':'matched_grid',
        'config':asdict(config),'test_frames':config.test_frames,'roundtrip_max_error_db':roundtrip,
        'quantization_max_error_db':quant_error,'provenance':source_provenance(),
        'observed_links':int(np.isfinite(reference).sum()),'total_links':len(pairs),
        'valid_measurement_fraction':{k:float(np.isfinite(v['signals']).mean()) for k,v in data.items()},
        'note':'Presupuesto FSPL ilustrativo. Sin materiales, CSI ni propagación electromagnética.'}
    np.savetxt(output/'calibration_residuals.csv',residuals,delimiter=',',header='residual_db',comments='')
    if len(residuals)<20 or np.isfinite(reference).sum()<config.min_links:
        summary.update(status='insufficient_calibration',reason='Insuficientes residuos o enlaces válidos.')
        save_json(output/'summary.json',summary);return summary
    p,s1,s2,iterations,converged=fit_zero_mean_gmm_em(residuals,600)
    gamma=fisher_information_gamma(p,s1,s2)
    summary['em']={'backend':'C++17','p':p,'sigma1_db':s1,'sigma2_db':s2,
                   'iterations':iterations,'converged':converged,'fisher_gamma':gamma,
                   'residual_mean_db':float(residuals.mean()),'n_residuals':len(residuals)}
    summary['provenance']['cpp']=backend_metadata()
    if not converged:summary['status']='em_not_converged'
    validation=reference-data['noise_validation']['signals']
    heldout=validation[np.isfinite(validation)]
    gaussian_sigma=max(float(np.sqrt(np.mean(residuals**2))),1e-8)
    summary['noise_validation']={'n':len(heldout),'mean_db':float(heldout.mean()) if len(heldout) else None,
        'gmm_mean_log_density':gmm_log_likelihood(heldout,p,s1,s2)/len(heldout) if len(heldout) else None,
        'gaussian_mean_log_density':float(np.mean(-np.log(gaussian_sigma*np.sqrt(2*np.pi))-heldout**2/(2*gaussian_sigma**2))) if len(heldout) else None,
        'note':'Densidad continua exploratoria; con cuantización no es probabilidad discreta.'}
    train_rss=data['fingerprint']['signals'].reshape(len(pixels),config.fingerprints_per_position,len(pairs))
    train=reference-finite_mean(train_rss,axis=1)
    development=reference-data['development']['signals']
    dev_positions=pixels[data['development']['indices']]
    evaluator=Evaluator(config,weights,pixels,train,pixels,gamma)
    alpha_t,tune_t=evaluator.tune(development,dev_positions,'RTI_Tikhonov',config.alpha_values)
    alpha_f,tune_f=evaluator.tune(development,dev_positions,'RTI_EM_Fisher',config.alpha_values)
    k,tune_k=evaluator.tune(development,dev_positions,'KNN',config.knn_values)
    summary['development_selection']={'Tikhonov':tune_t,'Fisher':tune_f,'KNN':tune_k}
    if not all(t['valid_selection'] for t in [tune_t,tune_f,tune_k]):
        summary.update(status='insufficient_development',reason='No hubo selección válida en desarrollo; no se evalúa prueba.')
        save_json(output/'summary.json',summary);return summary
    queries=reference-data['test']['signals'];positions=pixels[data['test']['indices']]
    rows,metrics,match_error=evaluator.evaluate(queries,positions,alpha_t,alpha_f,k)
    with (output/'predictions.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary.update(metrics=metrics,fisher_matched_max_abs_error=match_error,upstream_feature_rows=0,
                   geometry_rank=int(np.linalg.matrix_rank(weights)),uncovered_cells=int((weights.sum(axis=0)==0).sum()))
    if config.export_upstream_features:
        from .acquisition import upstream_measurements
        from .upstream_features import WiFiFeatureExtractor
        features=WiFiFeatureExtractor(window_size=5.,overlap=.5).extract_features(
            upstream_measurements(data['calibration']['rows']))
        features.to_csv(output/'upstream_features.csv',index=False)
        summary['upstream_feature_rows']=len(features)
        summary['upstream_features_note']='Diagnóstico opcional; no entra en EM/RTI. FFT normalizada por muestra; no equivale a CSI.'
    save_json(output/'summary.json',summary)
    return summary

