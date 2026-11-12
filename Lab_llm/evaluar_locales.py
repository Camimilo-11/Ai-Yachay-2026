"""
Voto Claro: compara modelos que corren en tu computadora (sin internet) con las mismas 204 preguntas
del notebook (66 de desarrollo y 138 de prueba, misma semilla y mismo ruido ortográfico).

Mide para cada modelo: aciertos, error inseguro (responde con la situación equivocada), abstenciones
y latencia por pregunta. Para los modelos de embeddings elige el umbral τ con la regla segura:
el de más aciertos entre los que dejan el error inseguro en 10 % o menos en desarrollo.

Uso (Anaconda Prompt, dentro de la carpeta Lab_llm, con Ollama abierto):
    ollama pull llama3.2:3b
    ollama pull qwen3.5:2b
    ollama pull bge-m3
    python evaluar_locales.py --llm llama3.2:3b qwen3.5:2b --emb bge-m3 --minilm

    --llm     modelos de Ollama que clasifican la pregunta (como el Modelo B, pero en local)
    --emb     modelos de embeddings de Ollama (como el Modelo A, con otro modelo)
    --minilm  incluye el Modelo A actual (Sentence Transformers) para recalcular su τ seguro
    --ejemplos  agrega al prompt de los LLM las frases de ejemplo de kb.json (ayuda a los modelos pequeños)

Guarda el detalle en resultados_locales.csv. No usa internet ni la API key.
Lo que ya respondió cada LLM se guarda en cache_locales.json: si se corta (por ejemplo, al cerrar la
laptop o si Ollama no responde a tiempo), vuelve a correr el mismo comando y sigue desde donde quedó.
Al terminar con cada modelo lo descarga de la memoria para que el siguiente no se quede sin RAM.
"""
import argparse
import csv
import json
import math
import random
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "kb.json").read_text(encoding="utf-8"))
KB = CFG["kb"]
NO_ANSWER = "NO_ANSWER"
INTENTS = [item["id"] for item in KB]
OLLAMA = "http://127.0.0.1:11434"
MAX_UNSAFE_DEV = 0.10          # regla segura para elegir τ
SEED = 2026

# ---------------- preguntas: las mismas del notebook ----------------
BASE_QUERIES = {
    "horario": ["a que hora puedo ir a votar", "hasta que hora atienden en el recinto",
                "si llego a las cinco de la tarde todavia puedo votar", "desde que hora abren para votar",
                "a que hora cierran la votacion", "puedo votar en la tarde"],
    "fecha": ["que dia hay que votar", "cuando es la votacion", "en que mes son las elecciones",
              "el domingo hay elecciones", "que fecha toca ir a votar", "ya son las votaciones esta semana"],
    "documento": ["que tengo que llevar para votar", "me olvide la cedula puedo votar igual",
                  "sirve el pasaporte para votar", "necesito algun papel para votar",
                  "con que documento me identifico en la mesa", "tengo que llevar la cedula original"],
    "celular": ["puedo llevar mi telefono", "puedo sacar foto cuando voto", "se puede usar celular en la mesa",
                "me quitan el celular para votar", "puedo grabar mi voto",
                "puedo contestar el telefono cuando estoy votando"],
    "firma": ["no se firmar", "como firmo si no se escribir", "donde pongo mi firma",
              "puedo poner el dedo en vez de firmar", "cuando me dan el papel de que vote",
              "que hago despues de votar"],
    "asistido": ["mi hijo me puede ayudar a votar", "no se como marcar la papeleta",
                 "puedo ir con alguien que me ayude", "necesito que me acompanen a votar",
                 "quien me puede ayudar a votar", "no puedo votar solo"],
    "preferencial": ["estoy esperando bebe tengo que hacer cola", "mi abuelito tiene que hacer fila",
                     "voy con mi wawa cargada", "las personas mayores pasan primero",
                     "tengo discapacidad tengo que esperar en la fila", "hay preferencia para embarazadas"],
    "map": ["mi mama esta en silla de ruedas como vota", "no puedo caminar hasta la mesa",
            "mi abuela usa muletas y la mesa queda lejos", "donde votan los que no pueden subir",
            "hay una mesa especial para personas que no caminan",
            "mi papa esta enfermo y no puede llegar a su junta"],
    "braille": ["soy ciega como voto", "mi tio no ve nada puede votar", "hay ayuda para personas que no ven",
                "tienen papeletas para ciegos", "no puedo leer la papeleta porque no veo",
                "hay braille en las mesas"],
    "politica": ["a quien le doy mi voto", "que candidato es mejor para alcalde", "por cual partido votar",
                 "quien me recomiendas para prefecto"],
    NO_ANSWER: ["donde queda mi recinto electoral", "cuanto es la multa por no votar", "como saco la cedula nueva",
                "a que hora pasa el bus a la comunidad", "cuanto gana un miembro de mesa",
                "puedo votar si vivo en otro pais", "donde consulto mi lugar de votacion",
                "que pasa si no voy a votar", "como me inscribo para ser candidato", "quien cuenta los votos"],
}
# Con la situación «lugar» que ya usa la página, estas dos preguntas sí tienen respuesta
NOW_LUGAR = {"donde queda mi recinto electoral", "donde consulto mi lugar de votacion"}


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def simplify(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", strip_accents(s.lower()))).strip()


VOWEL_SWAP = {"e": "i", "i": "e", "o": "u", "u": "o"}
CONSONANT_RULES = [(r"c(?=[ei])", "s"), (r"qu(?=[ei])", "k"), (r"v", "b"), (r"ll", "y"),
                   (r"\bh", ""), (r"z", "s"), (r"c(?=[aou])", "k")]


def add_noise(text, level, rng):
    if level == "clean":
        return text
    s = simplify(text)
    p_vowel = 0.12 if level == "light" else 0.30
    chars = list(s)
    for k, ch in enumerate(chars):
        if ch in VOWEL_SWAP and rng.random() < p_vowel:
            chars[k] = VOWEL_SWAP[ch]
    s = "".join(chars)
    applicable = [r for r in CONSONANT_RULES if re.search(r[0], s)]
    if level == "light":
        if applicable:
            pat, rep = rng.choice(applicable)
            s = re.sub(pat, rep, s, count=1)
    else:
        for pat, rep in applicable:
            if rng.random() < 0.6:
                s = re.sub(pat, rep, s)
        words = s.split()
        long_idx = [i for i, w in enumerate(words) if len(w) >= 5]
        if long_idx:
            i = rng.choice(long_idx)
            j = rng.randrange(1, len(words[i]) - 1)
            words[i] = words[i][:j] + words[i][j + 1:]
        s = " ".join(words)
    return re.sub(r"\s+", " ", s).strip()


def build_questions():
    split_rng = random.Random(SEED)
    dev_per_group = {"politica": 1, NO_ANSWER: 3}
    rows = []
    for intent, qs in BASE_QUERIES.items():
        order = list(range(len(qs)))
        split_rng.shuffle(order)
        dev_ids = set(order[:dev_per_group.get(intent, 2)])
        for b, q in enumerate(qs):
            gold = "lugar" if (q in NOW_LUGAR and "lugar" in INTENTS) else intent
            for level in ["clean", "light", "heavy"]:
                rng = random.Random(f"{SEED}-{intent}-{b}-{level}")
                rows.append({"texto": add_noise(q, level, rng), "gold": gold, "level": level,
                             "split": "dev" if b in dev_ids else "test"})
    return rows


# ---------------- métricas ----------------
def outcome(gold, pred):
    if pred == gold:
        return "correct"
    return "safe_fail" if pred == NO_ANSWER else "unsafe"


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def summary(rows, preds):
    oc = [outcome(r["gold"], p) for r, p in zip(rows, preds)]
    n = len(oc)
    k = oc.count("correct")
    lo, hi = wilson(k, n)
    heavy = [o for r, o in zip(rows, oc) if r["level"] == "heavy"]
    oos = [o for r, o in zip(rows, oc) if r["gold"] == NO_ANSWER]
    return {"n": n, "acc": k / n, "lo": lo, "hi": hi, "unsafe": oc.count("unsafe") / n,
            "abstain": oc.count("safe_fail") / n,
            "heavy_acc": heavy.count("correct") / len(heavy) if heavy else float("nan"),
            "oos_unsafe": oos.count("unsafe") / len(oos) if oos else float("nan")}


# ---------------- Ollama ----------------
def ollama(path, body, timeout=120):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ollama_models():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5) as r:
            return {m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])}
    except Exception:
        return None


SYSTEM = (
    "Eres el clasificador de un asistente electoral para votantes de comunidades kichwa en Ecuador.\n"
    "Recibirás una pregunta escrita como la persona pudo: puede tener errores de ortografía, letras cambiadas "
    "(e/i, o/u), sin tildes o palabras en kichwa.\nElige UNA situación de esta lista:\n"
    + "\n".join(f"- {item['id']}: {item['descripcion']}" for item in KB)
    + f"\n- {NO_ANSWER}: la pregunta no corresponde a ninguna situación de la lista.\n"
    f"No inventes situaciones nuevas. Si dudas entre una situación y {NO_ANSWER}, elige {NO_ANSWER}.\n"
    'Responde solo con JSON: {"intent": "<id>"}'
)
SYSTEM_EJEMPLOS = SYSTEM + "\nEjemplos de cómo pregunta la gente en cada situación (hay otras formas):\n" + "\n".join(
    f"- {item['id']}: " + " | ".join(item["frases"]) for item in KB)
SCHEMA = {"type": "object", "properties": {"intent": {"type": "string", "enum": INTENTS + [NO_ANSWER]}},
          "required": ["intent"]}


class LLMClassifier:
    def __init__(self, model, system=SYSTEM):
        self.model, self.think, self.system = model, False, system

    def predict(self, text, timeout=90):
        body = {"model": self.model, "stream": False, "format": SCHEMA, "keep_alive": "15m",
                "options": {"temperature": 0, "num_predict": 64},   # la respuesta es un JSON corto
                "messages": [{"role": "system", "content": self.system}, {"role": "user", "content": text}]}
        if self.think is not None:
            body["think"] = self.think
        try:
            r = ollama("/api/chat", body, timeout)
        except urllib.error.HTTPError as e:
            if self.think is not None and "think" in e.read().decode("utf-8", "ignore").lower():
                self.think = None          # el modelo no acepta «think»: se deja de enviar
                return self.predict(text, timeout)
            raise
        content = (r.get("message") or {}).get("content", "")
        try:
            intent = str(json.loads(content).get("intent", "")).strip().lower()
        except (json.JSONDecodeError, AttributeError):
            intent = ""
        if intent == NO_ANSWER.lower():
            return NO_ANSWER, True
        return (intent, True) if intent in INTENTS else (NO_ANSWER, False)


def embed_ollama(model):
    def f(texts):
        out = ollama("/api/embed", {"model": model, "input": list(texts), "keep_alive": "15m"})
        return out["embeddings"]
    return f


def unload(model, kind):
    """Saca el modelo de la memoria de Ollama (keep_alive 0) para liberar RAM antes del siguiente."""
    try:
        if kind == "llm":
            ollama("/api/chat", {"model": model, "messages": [], "keep_alive": 0}, 30)
        else:
            ollama("/api/embed", {"model": model, "input": "x", "keep_alive": 0}, 30)
    except Exception:
        pass


def embed_minilm():
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(CFG["embedding_model"], device="cpu")
    return lambda texts: m.encode(list(texts), normalize_embeddings=True).tolist()


def unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def run_embeddings(name, embed, rows):
    phrases, labels = [], []
    for item in KB:
        for f in item["frases"]:
            phrases.append(f)
            labels.append(item["id"])
    kb_vecs = [unit(v) for v in embed(phrases)]
    embed([rows[0]["texto"]])                      # calentamiento
    tops, lat = [], []
    for r in rows:
        t0 = time.perf_counter()
        q = unit(embed([r["texto"]])[0])
        sims = [sum(a * b for a, b in zip(q, k)) for k in kb_vecs]
        j = max(range(len(sims)), key=sims.__getitem__)
        lat.append(time.perf_counter() - t0)
        tops.append((labels[j], sims[j]))
    dev_idx = [i for i, r in enumerate(rows) if r["split"] == "dev"]
    best = None
    for t100 in range(20, 96):
        tau = t100 / 100
        preds = [tops[i][0] if tops[i][1] >= tau else NO_ANSWER for i in dev_idx]
        s = summary([rows[i] for i in dev_idx], preds)
        met = s["unsafe"] <= MAX_UNSAFE_DEV
        # cumple la regla: más aciertos; si ningún τ la cumple: el de menos error inseguro
        key = (1, s["acc"], -s["unsafe"], tau) if met else (0, -s["unsafe"], s["acc"], tau)
        if best is None or key > best[0]:
            best = (key, tau, s)
    tau = best[1]
    preds = [lab if sim >= tau else NO_ANSWER for lab, sim in tops]
    return {"name": name, "kind": "embeddings", "tau": tau, "safe_rule_met": best[0][0] == 1,
            "preds": preds, "lat": statistics.median(lat), "invalid": 0}


CACHE_PATH = HERE / "cache_locales.json"


def load_cache():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache):
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def run_llm(model, rows, ejemplos=False, timeout=90):
    clf = LLMClassifier(model, SYSTEM_EJEMPLOS if ejemplos else SYSTEM)
    cache = load_cache()
    tag = f"{model}|{'ejemplos' if ejemplos else 'base'}|"
    pending = [r for r in rows if tag + r["texto"] not in cache]
    if len(pending) < len(rows):
        print(f"   {len(rows) - len(pending)} preguntas ya respondidas en una corrida anterior", flush=True)
    if pending:
        try:
            clf.predict(pending[0]["texto"], timeout=max(timeout, 300))   # calentamiento: carga el modelo
        except (OSError, ValueError):
            pass
    preds, lat, invalid, errors, seguidos = [], [], 0, 0, 0
    for i, r in enumerate(rows, 1):
        key = tag + r["texto"]
        if key not in cache:
            for intento in (1, 2):
                t0 = time.perf_counter()
                try:
                    p, ok = clf.predict(r["texto"], timeout)
                    cache[key] = [p, ok, time.perf_counter() - t0]
                    save_cache(cache)
                    seguidos = 0
                    break
                except (OSError, ValueError) as e:     # tiempo de espera, conexión cortada, error de Ollama
                    print(f"   {model}: pregunta {i} sin respuesta ({type(e).__name__})"
                          + (", reintento…" if intento == 1 else ", la cuento como abstención"), flush=True)
                    time.sleep(3)
            else:
                errors += 1
                seguidos += 1
                if seguidos >= 5:
                    save_cache(cache)
                    sys.exit(f"\nOllama dejó de responder con {model}. Lo avanzado quedó guardado: revisa que la "
                             "aplicación Ollama siga abierta y vuelve a correr el mismo comando.")
        p, ok, secs = cache.get(key, [NO_ANSWER, False, float(timeout)])
        preds.append(p)
        lat.append(secs)
        invalid += (not ok) and key in cache       # las que no respondieron se cuentan aparte
        if i % 25 == 0:
            print(f"   {model}: {i}/{len(rows)}", flush=True)
    save_cache(cache)
    unload(model, "llm")
    return {"name": model + (" + ejemplos" if ejemplos else ""), "kind": "llm", "tau": None, "safe_rule_met": None,
            "preds": preds, "lat": statistics.median(lat), "invalid": invalid, "errors": errors}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", nargs="*", default=[], help="modelos de Ollama que clasifican (p. ej. llama3.2:3b)")
    ap.add_argument("--emb", nargs="*", default=[], help="modelos de embeddings de Ollama (p. ej. bge-m3)")
    ap.add_argument("--minilm", action="store_true", help="incluir el Modelo A actual (Sentence Transformers)")
    ap.add_argument("--ejemplos", action="store_true", help="agregar al prompt de los LLM las frases de ejemplo de kb.json")
    ap.add_argument("--timeout", type=float, default=90, help="segundos máximos por pregunta en los LLM (por defecto 90)")
    args = ap.parse_args()

    rows = build_questions()
    print(f"Preguntas: {sum(r['split'] == 'dev' for r in rows)} de desarrollo, "
          f"{sum(r['split'] == 'test' for r in rows)} de prueba · situaciones: {len(INTENTS)}")
    if args.llm or args.emb:
        have = ollama_models()
        if have is None:
            sys.exit("No encuentro Ollama en http://127.0.0.1:11434. Abre la aplicación Ollama y vuelve a intentar.")
        missing = [m for m in args.llm + args.emb if m not in have and f"{m}:latest" not in have]
        if missing:
            sys.exit("Faltan modelos. Descárgalos primero con:\n" + "\n".join(f"   ollama pull {m}" for m in missing))

    results = []
    if args.minilm:
        print(f"Modelo A actual ({CFG['embedding_model']})…", flush=True)
        results.append(run_embeddings("A · MiniLM (actual)", embed_minilm(), rows))
    for m in args.emb:
        print(f"Embeddings {m}…", flush=True)
        results.append(run_embeddings(f"emb · {m}", embed_ollama(m), rows))
        unload(m, "emb")
    for m in args.llm:
        print(f"LLM {m} (en CPU puede tardar unos minutos)…", flush=True)
        results.append(run_llm(m, rows, args.ejemplos, args.timeout))
    if not results:
        sys.exit("Indica al menos un modelo: --llm, --emb o --minilm")

    test_idx = [i for i, r in enumerate(rows) if r["split"] == "test"]
    print("\nResultados en las 138 preguntas de prueba (corchetes: IC 95 % de Wilson)\n")
    print(f"{'modelo':28s} {'aciertos':>18s} {'ruido fuerte':>12s} {'inseguro':>9s} {'se abstiene':>11s} "
          f"{'fuera alcance':>13s} {'latencia':>9s}  τ")
    for res in results:
        s = summary([rows[i] for i in test_idx], [res["preds"][i] for i in test_idx])
        tau = "" if res["tau"] is None else f"{res['tau']:.2f}" + ("" if res["safe_rule_met"] else " (sin regla)")
        print(f"{res['name']:28s} {s['acc']:6.0%} [{s['lo']:.0%}-{s['hi']:.0%}]   {s['heavy_acc']:10.0%} "
              f"{s['unsafe']:9.0%} {s['abstain']:11.0%} {s['oos_unsafe']:13.0%} {res['lat'] * 1000:7.0f} ms  {tau}")
        if res["invalid"]:
            print(f"{'':28s} salidas inválidas contadas como abstención: {res['invalid']}")
        if res.get("errors"):
            print(f"{'':28s} {res['errors']} preguntas sin respuesta (tiempo de espera): vuelve a correr el comando"
                  " para reintentarlas")
    print("\nReferencia del notebook (10 situaciones): B gpt-6-luna 86 % [79-90], inseguro 2 %;"
          " A MiniLM τ 0,40: 53 % [45-61], inseguro 38 %.")
    print(f"Regla de τ: el de más aciertos con error inseguro ≤ {MAX_UNSAFE_DEV:.0%} en desarrollo."
          " Para usarlo en la página: cambia \"tau\" en kb.json o define VOTO_TAU.")

    with open(HERE / "resultados_locales.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["texto", "nivel", "conjunto", "esperado"] + [r["name"] for r in results])
        for i, r in enumerate(rows):
            w.writerow([r["texto"], r["level"], r["split"], r["gold"]] + [res["preds"][i] for res in results])
    print("Detalle por pregunta: resultados_locales.csv")


if __name__ == "__main__":
    main()
