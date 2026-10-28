"""Formato compatible con WiFiMeasurement de IsukaW, más identidad de enlace."""
import csv
from pathlib import Path
import numpy as np
from .upstream_contract import WiFiMeasurement

FIELDS = ["session_id","phase","sample_id","timestamp","link_id","tx_id","rx_id",
          "ssid","bssid","signal_strength","frequency","channel","interface","valid","source"]


def observation_records(baseline, changes, pairs, phase, sample_id, timestamp, frequency_mhz, valid):
    baseline, changes = np.asarray(baseline), np.asarray(changes)
    if baseline.shape != changes.shape or baseline.shape != (len(pairs),) or len(valid)!=len(pairs):
        raise ValueError("Dimensiones incompatibles entre enlaces y observaciones.")
    if not np.isfinite(baseline).all() or not np.isfinite(changes).all():
        raise ValueError("El generador requiere valores finitos antes de aplicar pérdidas.")
    rows=[]
    for link_id, ((a,b),b0,y,ok) in enumerate(zip(pairs,baseline,changes,valid)):
        rows.append(dict(session_id=phase,phase=phase,sample_id=int(sample_id),timestamp=float(timestamp),
            link_id=link_id,tx_id=f"node_{a}",rx_id=f"node_{b}",ssid=f"RTI_TX_{a:02d}",
            bssid=f"02:00:00:{a:02x}:{b:02x}:01",signal_strength=float(b0-y) if ok else None,
            frequency=float(frequency_mhz),channel=0,interface=f"sim_rx_{b}",valid=bool(ok),source="simulation"))
    return rows


def write_records(path, rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for row in rows:
            out=dict(row);out["valid"]=int(out["valid"]);writer.writerow(out)


def read_records(path):
    with Path(path).open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames != FIELDS: raise ValueError("Esquema de mediciones incompatible.")
        rows=[]
        for row in reader:
            if row["valid"] not in {"0","1"}: raise ValueError("Validez debe ser 0 o 1.")
            row["valid"]=row["valid"]=="1"
            for name in ["sample_id","link_id","channel"]: row[name]=int(row[name])
            for name in ["timestamp","frequency"]: row[name]=float(row[name])
            row["signal_strength"]=float(row["signal_strength"]) if row["signal_strength"] else None
            numeric=[row["timestamp"],row["frequency"]]
            if row["valid"]:
                if row["signal_strength"] is None: raise ValueError("Lectura válida sin RSS.")
                numeric.append(row["signal_strength"])
            elif row["signal_strength"] is not None:
                raise ValueError("Lectura perdida debe tener RSS vacío.")
            if not np.isfinite(numeric).all() or row["frequency"]<=0:
                raise ValueError("Tiempo, frecuencia y RSS deben ser finitos.")
            if row["source"]!="simulation": raise ValueError("Esta entrega solo admite origen simulation.")
            rows.append(row)
    return rows


def reconstruct_scan(rows, baseline, pairs):
    values=np.full(len(pairs),np.nan);mask=np.zeros(len(pairs),dtype=bool);seen=set()
    scan_ids={(r["phase"],r["sample_id"]) for r in rows}
    if len(scan_ids)>1: raise ValueError("Se esperaba un solo barrido.")
    for r in rows:
        k=r["link_id"]
        if k in seen or not 0<=k<len(pairs): raise ValueError("Enlace duplicado o desconocido.")
        seen.add(k);a,b=pairs[k]
        if r["tx_id"]!=f"node_{a}" or r["rx_id"]!=f"node_{b}":
            raise ValueError("Identidad del enlace incompatible con la geometría.")
        if r["valid"] and np.isfinite(baseline[k]):
            signal=r["signal_strength"]
            if signal is None or not np.isfinite(signal): raise ValueError("RSS inválido.")
            values[k]=baseline[k]-signal;mask[k]=True
    return values,mask


def upstream_measurements(rows):
    return [WiFiMeasurement(timestamp=r["timestamp"],ssid=r["ssid"],bssid=r["bssid"],
        signal_strength=r["signal_strength"],frequency=r["frequency"],channel=r["channel"],
        interface=r["interface"]) for r in rows if r["valid"]]

