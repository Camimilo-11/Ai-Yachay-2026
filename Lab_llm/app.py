"""
Voto Claro: servidor local que conecta la página web con los modelos del notebook.

Uso (Windows PowerShell, dentro de esta carpeta):
    conda activate apidb
    pip install -r requirements.txt
    $env:OPENAI_API_KEY = "sk-..."      # opcional: sin key responde solo el Modelo A
    uvicorn app:app --port 8000
Luego abre http://localhost:8000

Variables opcionales:
    VOTO_MODE     auto (por defecto) | A | B
    OPENAI_MODEL  modelo de OpenAI para el Modelo B (por defecto, el de kb.json)
    VOTO_TAU      umbral de similitud del Modelo A (por defecto, el elegido en el notebook)
"""
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "kb.json").read_text(encoding="utf-8"))
KB = CFG["kb"]
KB_BY_ID = {item["id"]: item for item in KB}
INTENTS = [item["id"] for item in KB]
NO_ANSWER = "NO_ANSWER"
FALLBACK = CFG["fallback"]
TAU = float(os.environ.get("VOTO_TAU", CFG["tau"]))
MODE = os.environ.get("VOTO_MODE", "auto").upper()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", CFG.get("openai_model", "gpt-6-luna"))

# ---------- Modelo A: Sentence Transformers + FAISS (local) ----------
from sentence_transformers import SentenceTransformer

model_a = SentenceTransformer(CFG["embedding_model"], device="cpu")
kb_texts, kb_ids = [], []
for item in KB:
    for frase in item["frases"]:
        kb_texts.append(frase)
        kb_ids.append(item["id"])


def embed(texts):
    return model_a.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True,
                          show_progress_bar=False).astype("float32")


kb_emb = embed(kb_texts)
try:
    import faiss

    faiss_index = faiss.IndexFlatIP(kb_emb.shape[1])
    faiss_index.add(kb_emb)

    def search(q_emb, k):
        return faiss_index.search(q_emb, k)
except ImportError:
    def search(q_emb, k):
        sims = q_emb @ kb_emb.T
        idx = np.argsort(-sims, axis=1)[:, :k]
        return np.take_along_axis(sims, idx, axis=1), idx


def predict_a(text):
    D, I = search(embed([text]), 1)
    score = float(D[0, 0])
    return (kb_ids[I[0, 0]] if score >= TAU else NO_ANSWER), score


# ---------- Modelo B: GPT (OpenAI), solo si hay API key ----------
client = None
if MODE in ("AUTO", "B") and os.environ.get("OPENAI_API_KEY"):
    from openai import OpenAI

    client = OpenAI()   # lee la key de la variable de entorno; nunca se guarda en archivos

INTENT_LIST = "\n".join(f"- {item['id']}: {item['descripcion']}" for item in KB)
SYSTEM_B = f"""Eres el clasificador de un asistente electoral para votantes de comunidades kichwa en Ecuador.
Recibirás una pregunta escrita como la persona pudo: puede tener errores de ortografía, letras cambiadas (e/i, o/u), sin tildes o palabras en kichwa.
Elige UNA situación de esta lista:
{INTENT_LIST}
- {NO_ANSWER}: la pregunta no corresponde a ninguna situación de la lista.
No inventes situaciones nuevas. Si dudas entre una situación y {NO_ANSWER}, elige {NO_ANSWER}.
Responde solo con JSON: {{"intent": "<id>"}}"""


def parse_intent(content):
    content = content or ""
    match = re.search(r"\{.*\}", content, re.S)
    try:
        intent = json.loads(match.group(0)).get("intent") if match else content.strip()
    except (json.JSONDecodeError, AttributeError):
        intent = None
    return intent if (intent in INTENTS or intent == NO_ANSWER) else NO_ANSWER


def predict_b(text):
    kwargs = {"model": OPENAI_MODEL, "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": SYSTEM_B}, {"role": "user", "content": text}]}
    try:
        r = client.chat.completions.create(temperature=0, **kwargs)
    except Exception as e:
        msg = str(e).lower()
        if "temperature" not in msg and "response_format" not in msg:
            raise
        if "response_format" in msg:
            kwargs.pop("response_format")
        r = client.chat.completions.create(**kwargs)
    return parse_intent(r.choices[0].message.content)


# ---------- API ----------
app = FastAPI(title="Voto Claro")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


class Pregunta(BaseModel):
    pregunta: str
    idioma: Optional[str] = "es"


@app.get("/")
def home():
    return FileResponse(HERE / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "modelo_a": CFG["embedding_model"], "tau": TAU,
            "modelo_b": OPENAI_MODEL if client else None, "modo": MODE}


@app.post("/api/chat")
def chat(p: Pregunta):
    question = p.pregunta.strip()[:500]
    t0 = time.perf_counter()
    intent, modelo = None, None
    if client is not None and MODE != "A":
        try:
            intent, modelo = predict_b(question), f"Modelo B ({OPENAI_MODEL})"
        except Exception as e:   # sin internet o error de la API: responde el Modelo A
            print(f"Modelo B no disponible ({type(e).__name__}); respondo con el Modelo A")
    if intent is None:
        intent, _ = predict_a(question)
        modelo = "Modelo A (local)"
    item = KB_BY_ID.get(intent)
    return {"texto": item["respuesta"] if item else FALLBACK,
            "fuente": item["fuente"] if item else None,
            "intent": intent, "modelo": modelo,
            "ms": round((time.perf_counter() - t0) * 1000)}
