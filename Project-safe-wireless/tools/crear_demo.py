"""Exporta resultados guardados a una demo HTML autónoma; no ejecuta simulaciones."""
from pathlib import Path
import csv
import hashlib
import json
import math

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "integracion_verificada"
DEMO = ROOT / "demo"
SCENARIOS = [
    ("base", "Caso base", "Mezcla de ruido RSS con geometría y parámetros de referencia."),
    ("ruido_alto", "Ruido elevado", "Mayor dispersión del ruido en las mediciones sintéticas."),
    ("cuantizacion", "RSS cuantizado", "Las mediciones RSS se redondean a pasos discretos."),
    ("correlacion", "Ruido correlacionado", "Ruido con dependencia temporal. Se conserva el aviso de no convergencia de EM."),
    ("perdidas", "Pérdida de enlaces", "Parte de las mediciones no está disponible para la estimación."),
    ("deriva", "Deriva de referencia", "La referencia cambia a lo largo del experimento sintético."),
    ("frecuencia_5ghz", "5 GHz · margen amplio", "Presupuesto ilustrativo a 5 GHz; no representa propagación por materiales."),
    ("margen_24ghz", "2,4 GHz · margen bajo", "Menor margen de recepción; solo se usan las mediciones que superan el umbral."),
    ("margen_5ghz", "5 GHz · margen bajo", "La calibración guardada es insuficiente y no ofrece predicciones de localización."),
]
METHODS = [
    {"id": "RTI_Tikhonov", "label": "RTI Tikhonov", "description": "Reconstruye un mapa de atenuación con regularización."},
    {"id": "RTI_EM_Fisher", "label": "RTI + EM", "description": "EM calibra el ruido; su escalar Fisher ajusta la regularización RTI."},
    {"id": "Tikhonov_equivalente_Fisher", "label": "Fisher equivalente", "description": "Control Tikhonov con regularización equivalente al escalar Fisher."},
    {"id": "KNN", "label": "K-NN", "description": "Compara el patrón RSS con huellas sintéticas de posiciones conocidas."},
    {"id": "Centro_constante", "label": "Centro del área", "description": "Control que predice siempre el centro de la habitación."},
]


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def optional_number(value):
    if value in (None, ""):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def histogram(path):
    if not path.is_file():
        return None
    residuals = np.array([float(row["residual_db"]) for row in csv_rows(path)])
    if not len(residuals) or not np.isfinite(residuals).all():
        raise ValueError(f"Residuos de calibración inválidos: {path}")
    density, edges = np.histogram(residuals, bins=36, density=True)
    return {
        "edges": edges.tolist(),
        "density": density.tolist(),
        "gaussianSigma": float(np.sqrt(np.mean(residuals ** 2))),
        "count": len(residuals),
    }


def check_predictions(cases, metrics, scenario_id):
    """Comprueba las cifras exportadas contra las predicciones CSV y summary.json."""
    known_methods = {method["id"] for method in METHODS}
    if set(metrics) - known_methods:
        raise ValueError(f"Métodos desconocidos en {scenario_id}")
    for method, saved in metrics.items():
        errors = []
        for case in cases:
            prediction = case["predictions"].get(method)
            if prediction is None:
                raise ValueError(f"Falta una predicción de {method} en {scenario_id}")
            if prediction["availableLinks"] != sum(link["valid"] for link in case["links"]):
                raise ValueError(f"Recuento de enlaces inconsistente en {scenario_id}")
            if prediction["position"] is not None:
                measured = math.dist(case["truth"], prediction["position"])
                if prediction["error"] is None or not math.isclose(measured, prediction["error"], abs_tol=1e-9):
                    raise ValueError(f"Error por consulta inconsistente en {scenario_id}")
                errors.append(prediction["error"])
            elif prediction["error"] is not None:
                raise ValueError(f"Error sin posición estimada en {scenario_id}")
        values = {
            "valid_cases": len(errors),
            "total_cases": len(cases),
            "coverage": len(errors) / len(cases),
            "mean_error_m": float(np.mean(errors)) if errors else None,
            "rmse_m": float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
        }
        for key, value in values.items():
            expected = saved[key]
            if value is None:
                if expected is not None:
                    raise ValueError(f"Métrica {key} inconsistente en {scenario_id}")
            elif expected is None or not math.isclose(value, expected, abs_tol=1e-9):
                raise ValueError(f"Métrica {key} inconsistente en {scenario_id}")


def export_scenario(name, label, description):
    directory = SOURCE / f"{name}_r00"
    summary_path = directory / "summary.json"
    summary_bytes = summary_path.read_bytes()
    summary = json.loads(summary_bytes)
    config = summary["config"]
    with np.load(directory / "geometry.npz", allow_pickle=False) as geometry:
        nodes = geometry["nodes"].tolist()
        pairs = geometry["pairs"].astype(int).tolist()
    truth_rows = [row for row in csv_rows(directory / "ground_truth.csv") if row["phase"] == "test"]
    cases = {
        int(row["sample_id"]): {
            "id": int(row["sample_id"]),
            "truth": [float(row["x_true_m"]), float(row["y_true_m"])],
            "links": [],
            "predictions": {},
        }
        for row in truth_rows
    }
    if len(cases) != config["test_frames"]:
        raise ValueError(f"Número de consultas inesperado en {directory}")
    for row in csv_rows(directory / "raw" / "test.csv"):
        case = cases[int(row["sample_id"])]
        link_id = int(row["link_id"])
        tx, rx = pairs[link_id]
        valid = row["valid"] == "1"
        rss = optional_number(row["signal_strength"]) if valid else None
        if valid and rss is None:
            raise ValueError(f"RSS válido sin valor finito en {directory}")
        case["links"].append({"id": link_id, "tx": tx, "rx": rx, "rss": rss, "valid": valid})
    prediction_path = directory / "predictions.csv"
    if prediction_path.is_file():
        for row in csv_rows(prediction_path):
            case = cases[int(row["case_id"])]
            position = [optional_number(row["x_pred_m"]), optional_number(row["y_pred_m"])]
            case["predictions"][row["method"]] = {
                "position": position if all(value is not None for value in position) else None,
                "error": optional_number(row["error_m"]),
                "status": row["status"],
                "availableLinks": int(row["available_links"]),
            }
    ordered_cases = sorted(cases.values(), key=lambda case: case["id"])
    for case in ordered_cases:
        case["links"].sort(key=lambda link: link["id"])
        if [link["id"] for link in case["links"]] != list(range(len(pairs))):
            raise ValueError(f"Enlaces faltantes o repetidos en {directory}")
    metrics = summary.get("metrics", {})
    check_predictions(ordered_cases, metrics, name)
    if not metrics and any(case["predictions"] for case in ordered_cases):
        raise ValueError(f"Hay predicciones sin métricas en {directory}")
    return {
        "id": name,
        "label": label,
        "description": description,
        "status": summary["status"],
        "reason": summary.get("reason", ""),
        "sourcePath": directory.relative_to(ROOT).as_posix(),
        "summaryHash": hashlib.sha256(summary_bytes).hexdigest(),
        "frequencyMHz": config["carrier_mhz"],
        "config": config,
        "nodes": nodes,
        "gridSize": config["grid_size"],
        "metrics": metrics,
        "em": summary.get("em"),
        "validation": summary.get("noise_validation", {}),
        "histogram": histogram(directory / "calibration_residuals.csv"),
        "cases": ordered_cases,
    }


def main():
    data = {
        "version": 1,
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "methods": METHODS,
        "scenarios": [export_scenario(*scenario) for scenario in SCENARIOS],
    }
    serialized = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    DEMO.mkdir(exist_ok=True)
    (DEMO / "datos_preliminares.json").write_text(serialized + "\n", encoding="utf-8")
    template = DEMO / "plantilla.html"
    if template.is_file():
        source = template.read_text(encoding="utf-8")
        if source.count("__DEMO_DATA__") != 1:
            raise ValueError("La plantilla debe contener exactamente un marcador __DEMO_DATA__.")
        safe_json = serialized.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (DEMO / "index.html").write_text(source.replace("__DEMO_DATA__", safe_json), encoding="utf-8")
    total_cases = sum(len(scenario["cases"]) for scenario in data["scenarios"])
    print(f"Exportados {len(data['scenarios'])} escenarios y {total_cases} consultas guardadas.")
    print("Predicciones CSV, medias, RMSE y cobertura coinciden con summary.json.")
    print("No se ejecutaron simulaciones ni se modificaron los resultados originales.")


if __name__ == "__main__":
    main()
