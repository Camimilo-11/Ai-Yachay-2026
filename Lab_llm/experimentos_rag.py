r"""
Pruebas del recuperador híbrido (recuperador.py) frente al Modelo A original.

Uso (Anaconda Prompt, en esta carpeta):
    conda activate apidb
    python experimentos_rag.py

No usa internet ni la API key. Tarda menos de un minuto en CPU.

Protocolo
- Preguntas: las mismas 204 del notebook (66 de desarrollo, 138 de prueba, 11 situaciones).
- Desarrollo ampliado, solo para elegir valores: las 66 de desarrollo, 5 variantes nuevas de ruido de esas mismas
  preguntas base, 5 variantes con errores de teclado (que la clave fonética no corrige) y 20 preguntas fuera de alcance
  escritas aparte (OOS_CALIB), cada una con ruido. Ninguna pregunta base de prueba entra en desarrollo.
- Estructura del recuperador (índice con frases + descripción, consulta original + corregida, 70 % letras y 30 %
  MiniLM, promedio de las dos mejores frases, regla de cobertura): elegida con barridos sobre desarrollo
  (480 combinaciones; la de más aciertos con error inseguro ≤ 10 %).
- Umbral, margen y cobertura mínima: se eligen aquí, en desarrollo, con error inseguro ≤ 5 %. Se usa 5 % y no 10 %
  porque el desarrollo es chico: el Modelo A original pasó de 9 % de error inseguro en desarrollo a 16 % en prueba.
- «¿Tu pregunta es sobre…?»: cuando A+ duda, ofrece sus 2 mejores situaciones y «Ninguna de estas». El puntaje
  mínimo y la cobertura mínima para preguntar se eligen en desarrollo, con opciones sin la correcta ≤ 5 %.
  «Resuelta» = respuesta directa correcta, la correcta entre las opciones, o «no sé» a una pregunta fuera de alcance.
- Frases extra (frases_extra.json): 20 preguntas por situación y 40 fuera de alcance generadas con GPT a partir de
  la descripción y la respuesta (generar_frases.py; GPT nunca vio las preguntas de prueba). Se revisaron las
  etiquetas a mano y se quitaron las que se parecían a cualquier pregunta de desarrollo o prueba (trigramas ≥ 0,45
  o MiniLM ≥ 0,85). Las de fuera de alcance son «anclas»: si la pregunta se parece más a ellas, dice «no sé».
- La prueba se usa solo para reportar. Nota honesta: la prueba se miró varias veces durante el desarrollo (una
  primera versión sin preguntas fuera de alcance de calibración se equivocaba demasiado); las cifras de prueba
  pueden ser algo optimistas. Para confirmarlas hacen falta frases reales de la comunidad.
"""
import csv
import math
import random
from pathlib import Path

import numpy as np

import evaluar_locales as ev
from recuperador import RecuperadorHibrido, cargar_extra, norm

HERE = Path(__file__).resolve().parent
NO = ev.NO_ANSWER
KB = ev.KB

OOS_CALIB = [
    "cuando dan los resultados de la eleccion", "hasta cuando dura la ley seca", "puedo trabajar el dia de las elecciones",
    "hay transporte gratis para ir a votar", "a que hora termina el conteo de votos", "cuantas juntas hay en mi parroquia",
    "como denuncio una compra de votos", "que necesito para sacar el pasaporte", "puedo llevar a mi perro al recinto",
    "donde compro comida cerca del recinto", "a que hora abren las tiendas el domingo", "que hago si tengo fiebre",
    "donde queda el centro de salud", "cuanto cuesta el pasaje a quito", "como pago la luz", "donde se cobra el bono",
    "que dia es la minga de la comuna", "donde me puedo vacunar", "va a llover el domingo", "quien gano el partido de futbol",
]
FACT_QUESTIONS = [  # sección 9 del notebook: la situación que debe estar en el contexto del RAG
    ("¿Qué día son las elecciones seccionales y del CPCCS en Ecuador?", "fecha"),
    ("¿En qué horario se puede votar en las elecciones seccionales de Ecuador?", "horario"),
    ("¿Hasta qué hora puedo votar el día de las elecciones seccionales en Ecuador?", "horario"),
    ("En las elecciones seccionales de Ecuador, ¿puedo usar el celular mientras voto?", "celular"),
    ("Si no sé escribir, ¿cómo firmo el padrón en las elecciones de Ecuador?", "firma"),
    ("¿Quiénes pueden votar sin hacer fila en las elecciones de Ecuador?", "preferencial"),
]

# Errores de teclado del celular: tecla vecina, letra que falta, letras invertidas o repetidas
QWERTY = ["qwertyuiop", "asdfghjklñ", "zxcvbnm"]
VECINAS = {}
for f, fila in enumerate(QWERTY):
    for c, ch in enumerate(fila):
        v = [fila[c + d] for d in (-1, 1) if 0 <= c + d < len(fila)]
        for ff in (f - 1, f + 1):
            if 0 <= ff < len(QWERTY):
                v += [QWERTY[ff][cc] for cc in (c - 1, c, c + 1) if 0 <= cc < len(QWERTY[ff])]
        VECINAS[ch] = v


def errores_teclado(texto, n, rng):
    s = list(ev.simplify(texto))
    for _ in range(n):
        idx = [i for i, ch in enumerate(s) if ch.isalpha()]
        if not idx:
            break
        i = rng.choice(idx)
        op = rng.choice(["sub", "del", "swap", "dup"])
        if op == "sub" and s[i] in VECINAS:
            s[i] = rng.choice(VECINAS[s[i]])
        elif op == "del":
            del s[i]
        elif op == "swap" and i + 1 < len(s) and s[i + 1].isalpha():
            s[i], s[i + 1] = s[i + 1], s[i]
        else:
            s.insert(i, s[i])
    return "".join(s)


def preguntas():
    """Las 204 del notebook (mismo orden y semillas) + desarrollo ampliado + prueba con errores de teclado."""
    split_rng = random.Random(ev.SEED)
    filas = []
    for intent, qs in ev.BASE_QUERIES.items():
        orden = list(range(len(qs)))
        split_rng.shuffle(orden)
        dev_ids = set(orden[:{"politica": 1, NO: 3}.get(intent, 2)])
        for b, q in enumerate(qs):
            gold = "lugar" if (q in ev.NOW_LUGAR and "lugar" in ev.INTENTS) else intent
            parte = "dev" if b in dev_ids else "test"
            for level in ["clean", "light", "heavy"]:
                rng = random.Random(f"{ev.SEED}-{intent}-{b}-{level}")
                filas.append({"texto": ev.add_noise(q, level, rng), "gold": gold, "level": level, "split": parte})
            for j in range(1, 6):
                for n in (1, 2):
                    rng = random.Random(f"typo{j}-{intent}-{b}-{n}")
                    filas.append({"texto": errores_teclado(q, n, rng), "gold": gold, "level": f"teclado{n}",
                                  "split": "devtypo" if parte == "dev" else "testtypo"})
            if parte == "dev":
                for j in range(1, 6):
                    for level in ["light", "heavy"]:
                        rng = random.Random(f"aug{j}-{intent}-{b}-{level}")
                        filas.append({"texto": ev.add_noise(q, level, rng), "gold": gold, "level": level,
                                      "split": "devaug"})
    for q in OOS_CALIB:
        for level in ["clean", "light", "heavy"]:
            rng = random.Random(f"oos-{q}-{level}")
            filas.append({"texto": ev.add_noise(q, level, rng), "gold": NO, "level": level, "split": "devoos"})
        for n in (1, 2):
            rng = random.Random(f"oostypo-{q}-{n}")
            filas.append({"texto": errores_teclado(q, n, rng), "gold": NO, "level": f"teclado{n}", "split": "devoos"})
    return filas


def metricas(filas, preds):
    oc = [ev.outcome(r["gold"], p) for r, p in zip(filas, preds)]
    n, k = len(oc), oc.count("correct")
    lo, hi = ev.wilson(k, n)
    fuera = [o for r, o in zip(filas, oc) if r["gold"] == NO]
    return {"n": n, "acc": k / n, "lo": lo, "hi": hi, "unsafe": oc.count("unsafe") / n,
            "abst": oc.count("safe_fail") / n, "oos": fuera.count("unsafe") / len(fuera) if fuera else float("nan")}


def mcnemar(a_ok, b_ok):
    b = sum(x and not y for x, y in zip(a_ok, b_ok))
    c = sum(y and not x for x, y in zip(a_ok, b_ok))
    n = b + c
    return b, c, (min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.0)


def main():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(ev.CFG["embedding_model"], device="cpu")
    memo = {}

    def embed(texts):
        nuevos = [t for t in dict.fromkeys(texts) if t not in memo]
        if nuevos:
            for t, e in zip(nuevos, model.encode(nuevos, normalize_embeddings=True, convert_to_numpy=True,
                                                  show_progress_bar=False).astype("float32")):
                memo[t] = e
        return np.stack([memo[t] for t in texts])

    filas = preguntas()
    dev = [r for r in filas if r["split"] in ("dev", "devaug", "devtypo", "devoos")]
    test = [r for r in filas if r["split"] == "test"]
    typo = [r for r in filas if r["split"] == "testtypo"]
    conj = {"dev": dev, "test": test, "typo": typo}
    print(f"Desarrollo ampliado: {len(dev)} preguntas · prueba: {len(test)} · prueba con errores de teclado: {len(typo)}")

    cfg_kb = ev.CFG.get("recuperador", {})
    extra, anclas = cargar_extra(HERE / cfg_kb.get("frases_extra", "frases_extra.json"))

    # ---- control de contaminación: ninguna frase extra debe parecerse a una pregunta de prueba ----
    def tri(t):
        t = " " + norm(t) + " "
        return {t[i:i + 3] for i in range(len(t) - 2)}
    bases_prueba = {ev.simplify(q) for intent, qs in ev.BASE_QUERIES.items() for q in qs}
    tp = [tri(b) for b in bases_prueba]
    todas = [f for v in extra.values() for f in v] + list(anclas)
    if todas:
        peor = max(max(len(tri(f) & g) / len(tri(f) | g) for g in tp) for f in todas)
        print(f"Frases extra: {len(todas) - len(anclas)} de situaciones + {len(anclas)} anclas · "
              f"máximo parecido con una pregunta del notebook (trigramas): {peor:.2f}")

    # ---- Modelo A original: la mejor frase por MiniLM, τ 0,60 ----
    F = embed([f for it in KB for f in it["frases"]])
    ids = np.array([it["id"] for it in KB for _ in it["frases"]])

    def pred_a(t):
        s = (embed([t]) @ F.T)[0]
        j = int(s.argmax())
        return ids[j] if s[j] >= 0.60 else NO

    # ---- A+: decisión con anclas, umbral, margen, cobertura y, si se pide, «¿Tu pregunta es sobre…?» ----
    def rasgos(rec, rs):
        out = []
        for r in rs:
            rk = rec.ranking(r["texto"])
            reales = [(i, s) for i, s in rk if i != NO]
            out.append((rk[0][0] == NO, reales, rec.cobertura(r["texto"])))
        return out

    def resolver(feats, rs, v):
        c = {"directo": 0, "toque": 0, "no_se_bien": 0, "afirma_mal": 0, "opciones_mal": 0}
        preds = []
        for r, (ancla, reales, cb) in zip(rs, feats):
            (i1, s1), (_, s2) = reales[0], reales[1]
            g = r["gold"]
            if not ancla and s1 >= v["tau"] and s1 - s2 >= v["margen"] and cb >= v["cobertura_min"]:
                c["directo" if i1 == g else "afirma_mal"] += 1
                preds.append(i1)
                continue
            preds.append(NO)
            if not ancla and v.get("preguntar_tau") is not None and s1 >= v["preguntar_tau"] and cb >= v["preguntar_cobertura"]:
                c["toque" if g in (reales[0][0], reales[1][0]) else "opciones_mal"] += 1
            elif g == NO:
                c["no_se_bien"] += 1
        n = len(rs)
        out = {k: x / n for k, x in c.items()}
        out["resuelta"] = out["directo"] + out["toque"] + out["no_se_bien"]
        return out, preds

    def calibrar(feats):
        mejor = None
        for cb in (0.0, 0.5, 0.6):
            for m in (0.0, 0.02, 0.04, 0.06, 0.08, 0.1):
                for t100 in range(15, 70):
                    v = {"tau": t100 / 100, "margen": m, "cobertura_min": cb}
                    o, p = resolver(feats, dev, v)
                    acc = metricas(dev, p)["acc"]
                    key = (o["afirma_mal"] <= 0.05, acc, -o["afirma_mal"], t100)
                    if mejor is None or key > mejor[0]:
                        mejor = (key, v)
        v = mejor[1]
        mejor = None
        for t100 in range(10, int(v["tau"] * 100) + 1):
            for pc in (0.0, 0.34, 0.5, 0.6):
                w = {**v, "preguntar_tau": t100 / 100, "preguntar_cobertura": pc}
                o, _ = resolver(feats, dev, w)
                key = (o["opciones_mal"] <= 0.05, o["resuelta"], -o["opciones_mal"], t100)
                if mejor is None or key > mejor[0]:
                    mejor = (key, w)
        return mejor[1]

    versiones = {
        "A+ v1 (frases del instructivo)": RecuperadorHibrido(KB, embed, {"peso_lexico": cfg_kb.get("peso_lexico", 0.7)}),
        "A+ v2 (+ frases extra y anclas)": RecuperadorHibrido(KB, embed, {"peso_lexico": cfg_kb.get("peso_lexico", 0.7)},
                                                              extra, anclas),
    }
    filas_csv, preds = [], {"A original (τ 0,60)": [pred_a(r["texto"]) for r in test]}
    print(f"\n{'sistema':32s} | {'sin preguntar: aciertos [IC 95 %]':>33s} {'afirma mal':>10s} {'fuera alc.':>10s} | "
          f"{'preguntando: resueltas':>22s} {'opc. sin la correcta':>20s} | teclado: resueltas / afirma mal | recall@3 | RAG 6")
    t = metricas(test, preds["A original (τ 0,60)"])
    ty = metricas(typo, [pred_a(r["texto"]) for r in typo])
    print(f"{'A original (τ 0,60)':32s} | {t['acc']:20.1%} [{t['lo']:.0%}–{t['hi']:.0%}] {t['unsafe']:10.1%} {t['oos']:10.1%} | "
          f"{'—':>22s} {'—':>20s} | {ty['acc']:8.1%} / {ty['unsafe']:4.1%}")
    for nombre, rec in versiones.items():
        feats = {k: rasgos(rec, rs) for k, rs in conj.items()}
        v = calibrar(feats["dev"])
        _, p_t = resolver(feats["test"], test, v)
        preds[nombre] = p_t
        o_t, _ = resolver(feats["test"], test, v)
        o_y, _ = resolver(feats["typo"], typo, v)
        t = metricas(test, p_t)
        rec3 = np.mean([r["gold"] in [i for i, _ in reales[:3]] for r, (_, reales, _) in zip(test, feats["test"]) if r["gold"] != NO])
        rag = sum(g in rec.contexto(q) for q, g in FACT_QUESTIONS)
        print(f"{nombre:32s} | {t['acc']:20.1%} [{t['lo']:.0%}–{t['hi']:.0%}] {t['unsafe']:10.1%} {t['oos']:10.1%} | "
              f"{o_t['resuelta']:22.1%} {o_t['opciones_mal']:20.1%} | {o_y['resuelta']:8.1%} / {o_y['afirma_mal']:4.1%} | "
              f"{rec3:8.1%} | {rag}/6")
        print(f"{'':32s}   valores elegidos en desarrollo: " + ", ".join(f"{k} {x}" for k, x in v.items()))
        filas_csv.append({"sistema": nombre, **v, **{f"prueba_{k}": round(x, 4) for k, x in t.items()},
                          **{f"preguntando_{k}": round(x, 4) for k, x in o_t.items()},
                          **{f"teclado_{k}": round(x, 4) for k, x in o_y.items()}, "recall3": round(float(rec3), 4), "rag_6": rag})
    print("En kb.json:", cfg_kb)
    ok = {n: [p == r["gold"] for p, r in zip(pp, test)] for n, pp in preds.items()}
    for a, b in (("A+ v2 (+ frases extra y anclas)", "A original (τ 0,60)"),
                 ("A+ v2 (+ frases extra y anclas)", "A+ v1 (frases del instructivo)")):
        x, y, p = mcnemar(ok[a], ok[b])
        print(f"McNemar sin preguntar, {a} vs {b}: {x} frente a {y}, p = {p:.2g}")
    campos = list(dict.fromkeys(k for f in filas_csv for k in f))
    with open(HERE / "resultados_rag.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas_csv)
    print("\nResumen guardado en resultados_rag.csv")


if __name__ == "__main__":
    main()
