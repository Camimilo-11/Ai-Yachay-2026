"""Comparación RTI/K-NN reutilizando las funciones de Wireless Save."""
from functools import lru_cache
import numpy as np
from simulacion_rti_em_knn import build_reconstruction_operator, nearest_neighbor_prediction, smoothness_laplacian


class Evaluator:
    def __init__(self, config, weights, pixels, train, train_positions, gamma):
        self.config,self.weights,self.pixels=config,weights,pixels
        self.train,self.train_positions,self.gamma=train,train_positions,gamma
        self.laplacian=smoothness_laplacian(config.grid_size)
        self.operator=lru_cache(maxsize=128)(self._operator)

    def _operator(self, mask_key, alpha, gamma, matched):
        mask=np.frombuffer(mask_key,dtype=np.bool_)
        w=self.weights[mask]
        if not matched:return build_reconstruction_operator(w,self.laplacian,alpha,gamma)
        matrix=w.T@w+(alpha/gamma)*self.laplacian
        matrix.flat[::len(matrix)+1]+=1e-8/gamma
        return np.linalg.solve(matrix,w.T)

    def predict(self, query, method, parameter):
        mask=np.isfinite(query)
        if method=='Centro_constante':return np.full(2,self.config.room_m/2),'ok'
        if mask.sum()<self.config.min_links:return None,'insufficient_links'
        if method=='KNN':
            candidates=np.isfinite(self.train[:,mask]).all(axis=1)
            if not candidates.any():return None,'no_fingerprints'
            return nearest_neighbor_prediction(self.train[candidates],self.train_positions[candidates],
                        query,mask,min(int(parameter),int(candidates.sum()))),'ok'
        gamma=1. if method=='RTI_Tikhonov' else self.gamma
        operator=self.operator(mask.tobytes(),float(parameter),float(gamma),
                               method=='Tikhonov_equivalente_Fisher')
        image=np.maximum(operator@query[mask],0.)
        if not np.isfinite(image).all():return None,'nonfinite_estimate'
        # Un mapa simétrico puede tener máximos iguales: redondeo de 1e-16
        # no debe cambiar la celda seleccionada entre operadores equivalentes.
        maxima=np.flatnonzero(np.isclose(image,image.max(),rtol=1e-10,atol=1e-12))
        return self.pixels[int(maxima[0])],'ok'

    def tune(self, queries, positions, method, candidates):
        scores=[]
        for parameter in candidates:
            errors=[]
            for query,position in zip(queries,positions):
                prediction,_=self.predict(query,method,parameter)
                if prediction is not None:errors.append(float(np.linalg.norm(prediction-position)))
            scores.append(float(np.mean(errors)) if errors else float('inf'))
        best=int(np.argmin(scores))
        return candidates[best],{'candidates':list(candidates),
            'mean_error_m':[x if np.isfinite(x) else None for x in scores],
            'selected':candidates[best],'valid_selection':bool(np.isfinite(scores[best]))}

    def evaluate(self, queries, positions, alpha_t, alpha_f, k):
        methods={'RTI_Tikhonov':alpha_t,'RTI_EM_Fisher':alpha_f,
                 'Tikhonov_equivalente_Fisher':alpha_f,'KNN':k,'Centro_constante':0}
        rows=[];fisher=[];matched=[];metrics={}
        for method,parameter in methods.items():
            errors=[];policy=[];coordinates=[]
            for case,(query,truth) in enumerate(zip(queries,positions)):
                predicted,status=self.predict(query,method,parameter)
                error=float(np.linalg.norm(predicted-truth)) if predicted is not None else None
                fallback=float(np.linalg.norm(np.full(2,self.config.room_m/2)-truth))
                if error is not None:errors.append(error)
                policy.append(error if error is not None else fallback);coordinates.append(predicted)
                rows.append({'case_id':case,'method':method,'status':status,'available_links':int(np.isfinite(query).sum()),
                    'x_true_m':float(truth[0]),'y_true_m':float(truth[1]),
                    'x_pred_m':float(predicted[0]) if predicted is not None else None,
                    'y_pred_m':float(predicted[1]) if predicted is not None else None,'error_m':error})
            metrics[method]={'valid_cases':len(errors),'total_cases':len(queries),
                'coverage':len(errors)/len(queries),'mean_error_m':float(np.mean(errors)) if errors else None,
                'rmse_m':float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
                'mean_error_with_center_fallback_m':float(np.mean(policy))}
            if method=='RTI_EM_Fisher':fisher=coordinates
            if method=='Tikhonov_equivalente_Fisher':matched=coordinates
        differences=[float(np.max(np.abs(a-b))) for a,b in zip(fisher,matched) if a is not None and b is not None]
        return rows,metrics,max(differences,default=0.)

