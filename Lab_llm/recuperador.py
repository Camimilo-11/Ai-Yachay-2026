"""Recuperador híbrido de Voto Claro: MiniLM + coincidencia fonética de letras.

Lo usan app.py (Modelo A sin internet) y el notebook (Modelo A+ y contexto del RAG).
Solo necesita numpy y una función que convierta textos en embeddings normalizados (MiniLM).

Cómo decide, para cada pregunta:
1. Corrige la ortografía con una clave fonética pensada para hablantes de kichwa (e~i, o~u, b~v, c/s/z, k/qu,
   ll~y, h muda): "a qoe hura puedo ir a botar" -> "a que hora puedo ir a votar".
2. Compara la pregunta (original y corregida) con las frases de ejemplo y la descripción de cada situación por dos
   caminos: MiniLM (significado) y n-gramas de letras sobre la clave fonética (forma escrita).
3. Junta los dos puntajes (70 % letras, 30 % MiniLM) y promedia las dos mejores frases de cada situación.
4. Se abstiene ("no sé, pregunta en tu junta") si el puntaje es bajo, si las dos mejores situaciones están muy
   cerca, o si casi ninguna palabra de la pregunta aparece en el instructivo (señal de pregunta fuera de alcance).
5. Si duda pero la pregunta parece del tema, decidir() propone sus dos mejores situaciones para que la persona elija
   («¿Tu pregunta es sobre…?»). Así no afirma nada que la persona no haya confirmado.

Frases extra (opcional, frases_extra.json): más ejemplos por situación, generados con GPT a partir de la descripción y
la respuesta (sin ver las preguntas de prueba), revisados a mano y descontaminados; y preguntas fuera de alcance que
sirven de «anclas»: si la pregunta se parece más a una de ellas que a cualquier situación, el asistente dice «no sé».

Los valores (peso, umbral, margen, cobertura) se eligieron con las preguntas de desarrollo; ver experimentos_rag.py.
"""
import json
import math
import re
import unicodedata
from collections import Counter

import numpy as np

NO_ANSWER = "NO_ANSWER"
DEFAULTS = {"peso_lexico": 0.7, "tau": 0.27, "margen": 0.08, "cobertura_min": 0.5,
            "preguntar_tau": None, "preguntar_cobertura": 0.5}   # preguntar_tau None = no pregunta

STOP = set("""a al algo alguien algun alguna ante aqui asi como con contra cual cuales cuando de del desde donde
el ella ellos en entre era es esa ese eso esta estan este esto estoy fue ha hay la las le les lo los mas me mi mis
muy nada ni no nos o otra otro para pero poco por porque puede pueden puedo que quien se sea ser si sin sobre son
su sus tambien te tengo tiene tu un una uno unos y ya yo""".split())


def norm(s):
    """Minúsculas, sin tildes ni signos."""
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]", " ", s)).strip()


def clave(palabra):
    """Clave fonética: el kichwa tiene tres vocales (a, i, u) y varias letras del español suenan igual."""
    w = norm(palabra).replace("ch", "#")
    w = w.replace("e", "i").replace("o", "u")
    w = re.sub(r"qu(?=i)", "k", w)
    w = re.sub(r"gu(?=i)", "g", w)
    w = re.sub(r"c(?=i)", "s", w)
    w = w.replace("c", "k").replace("q", "k").replace("z", "s").replace("x", "ks")
    w = w.replace("v", "b").replace("ll", "y").replace("h", "").replace("w", "u")
    w = re.sub(r"(.)\1+", r"\1", w)
    return w.replace("#", "ch")


STOP_CLAVES = {clave(w) for w in STOP}


def distancia(a, b, tope):
    """Distancia de edición de Levenshtein; corta apenas supera el tope."""
    if abs(len(a) - len(b)) > tope:
        return tope + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > tope:
            return tope + 1
        prev = cur
    return prev[-1]


class Corrector:
    """Cambia cada palabra por la del instructivo que suena igual (o a una letra de distancia, sin empates)."""

    def __init__(self, textos):
        frec = Counter(w for t in textos for w in norm(t).split())
        self.vocab = set(frec)
        self.por_clave = {}
        for w, _ in frec.most_common():
            self.por_clave.setdefault(clave(w), w)
        self.claves = list(self.por_clave)

    def palabra(self, t):
        if t in self.vocab or len(t) <= 2:
            return t
        k = clave(t)
        if k in self.por_clave:
            return self.por_clave[k]
        if len(k) >= 5:
            cerca = [kk for kk in self.claves if abs(len(kk) - len(k)) <= 1 and distancia(k, kk, 1) <= 1]
            if len(cerca) == 1:
                return self.por_clave[cerca[0]]
        return t

    def __call__(self, texto):
        return " ".join(self.palabra(t) for t in norm(texto).split())


class NgramasFoneticos:
    """TF-IDF de n-gramas de 3 y 4 letras sobre la clave fonética: tolera letras cambiadas."""

    def __init__(self, docs):
        gramas = [self._gramas(d) for d in docs]
        df = Counter(g for gs in gramas for g in set(gs))
        n = len(docs)
        self.idf = {g: math.log((1 + n) / (1 + c)) + 1 for g, c in df.items()}
        self.M = [self._vector(gs) for gs in gramas]

    @staticmethod
    def _gramas(texto):
        s = " " + " ".join(clave(w) for w in norm(texto).split()) + " "
        return [s[i:i + k] for k in (3, 4) for i in range(len(s) - k + 1)]

    def _vector(self, gramas):
        tf = Counter(gramas)
        v = {g: (1 + math.log(c)) * self.idf[g] for g, c in tf.items() if g in self.idf}
        nrm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / nrm for g, x in v.items()}

    def similitudes(self, texto):
        q = self._vector(self._gramas(texto))
        return np.array([sum(x * d.get(g, 0.0) for g, x in q.items()) for d in self.M], dtype="float32")


class Cobertura:
    """Qué parte de las palabras de contenido de la pregunta aparece (o casi) en el instructivo."""

    def __init__(self, textos):
        self.claves = {clave(w) for t in textos for w in norm(t).split()}
        self._memo = {}

    def _conocida(self, k):
        if k not in self._memo:
            self._memo[k] = k in self.claves or (len(k) >= 5 and any(
                distancia(k, kk, 1) <= 1 for kk in self.claves if abs(len(kk) - len(k)) <= 1))
        return self._memo[k]

    def __call__(self, texto):
        ks = [clave(w) for w in norm(texto).split()]
        contenido = [k for k in ks if k not in STOP_CLAVES and len(k) >= 3]
        if not contenido:
            return 1.0
        return sum(self._conocida(k) for k in contenido) / len(contenido)


def cargar_extra(ruta):
    """Lee frases_extra.json: ({situación: [frases]}, [preguntas fuera de alcance]). Sin archivo: ({}, [])."""
    try:
        d = json.loads(open(ruta, encoding="utf-8").read())
    except FileNotFoundError:
        return {}, []
    return d.get("frases", {}), d.get("fuera_de_alcance", [])


class RecuperadorHibrido:
    def __init__(self, kb, embed, cfg=None, extra=None, anclas=None):
        """kb: lista de situaciones (id, frases, descripcion, respuesta); embed: textos -> vectores normalizados.
        extra: {situación: [frases]} adicionales; anclas: preguntas fuera de alcance (clase NO_ANSWER)."""
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self.embed = embed
        docs, etiquetas = [], []
        for item in kb:
            for f in dict.fromkeys(list(item["frases"]) + [item["descripcion"]] + list((extra or {}).get(item["id"], []))):
                docs.append(f)
                etiquetas.append(item["id"])
        vocab = list(docs)                     # las anclas no cuentan como vocabulario del instructivo
        for f in anclas or []:
            docs.append(f)
            etiquetas.append(NO_ANSWER)
        self.ids = list(dict.fromkeys(etiquetas))
        self.etiquetas = np.array(etiquetas)
        self.D = embed(docs)
        self.letras = NgramasFoneticos(docs)
        self.corregir = Corrector(vocab)
        self.cobertura = Cobertura(vocab + [item["respuesta"] for item in kb])

    def ranking(self, texto):
        """Clases ordenadas de mayor a menor puntaje (incluye NO_ANSWER si hay anclas)."""
        variantes = list(dict.fromkeys([texto, self.corregir(texto)]))
        denso = (self.embed(variantes) @ self.D.T).max(axis=0)
        w = self.cfg["peso_lexico"]
        s = (1 - w) * denso + w * self.letras.similitudes(texto)
        puntajes = {i: float(np.sort(s[self.etiquetas == i])[::-1][:2].mean()) for i in self.ids}
        return sorted(puntajes.items(), key=lambda x: -x[1])

    def decidir(self, texto, opciones=2):
        """("responder", [situación]) | ("preguntar", [las 2 mejores]) | ("no_se", []), con el puntaje más alto."""
        r = self.ranking(texto)
        reales = [(i, s) for i, s in r if i != NO_ANSWER]
        (i1, s1), (_, s2) = reales[0], reales[1]
        if r[0][0] == NO_ANSWER:               # se parece más a una pregunta fuera de alcance
            return "no_se", [], s1
        cob = self.cobertura(texto)
        c = self.cfg
        if s1 >= c["tau"] and s1 - s2 >= c["margen"] and cob >= c["cobertura_min"]:
            return "responder", [i1], s1
        if c.get("preguntar_tau") is not None and s1 >= c["preguntar_tau"] and cob >= c["preguntar_cobertura"]:
            return "preguntar", [i for i, _ in reales[:opciones]], s1
        return "no_se", [], s1

    def predecir(self, texto):
        """Devuelve (situación o NO_ANSWER, puntaje), sin preguntar."""
        tipo, ids, s1 = self.decidir(texto)
        return (ids[0] if tipo == "responder" else NO_ANSWER), s1

    def contexto(self, texto, k=3):
        """Las k situaciones más parecidas, para darle contexto a GPT (RAG)."""
        return [i for i, _ in self.ranking(texto) if i != NO_ANSWER][:k]
