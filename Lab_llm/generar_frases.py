r"""
Genera más frases de ejemplo para cada situación de kb.json (y preguntas fuera de alcance para calibrar),
para ampliar el índice del recuperador híbrido. El modelo solo ve la descripción, la respuesta y los ejemplos
del instructivo; nunca ve las preguntas de prueba del notebook.

Uso (Anaconda Prompt, en esta carpeta, con la key en la variable de entorno; nunca en el código):
    conda activate apidb
    set OPENAI_API_KEY=...
    python generar_frases.py

Sin key, con Ollama abierto:
    python generar_frases.py --ollama qwen3.5:2b

Guarda frases_generadas.json. Revísalo antes de usarlo: cada frase debe pedir lo que dice su situación.
Costo con GPT: unos centavos (12 llamadas).
"""
import argparse
import json
import os
import re
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "kb.json").read_text(encoding="utf-8"))
KB = CFG["kb"]
N_FRASES = 20
N_FUERA = 40

ESTILO = ("Escribe como preguntaría una persona votante de una comunidad kichwa de la sierra del Ecuador, en español "
          "sencillo y conversado, a veces muy corto, a veces con palabras del kichwa que se usan en el español de "
          "Ecuador. Varía las palabras y la forma de preguntar; no copies los ejemplos. Sin faltas de ortografía "
          "a propósito (los errores se prueban aparte).")


def prompt_situacion(item):
    return (f"{ESTILO}\n\nSituación: {item['descripcion']}\n"
            f"Respuesta oficial que recibirá la persona: {item['respuesta']}\n"
            f"Ejemplos que ya tenemos: {' | '.join(item['frases'])}\n\n"
            f"Escribe {N_FRASES} preguntas nuevas y distintas que esa persona haría y que esta respuesta contesta. "
            'Responde solo con JSON: {"frases": ["...", "..."]}')


def prompt_fuera():
    temas = "; ".join(f"{i['id']}: {i['descripcion']}" for i in KB)
    return (f"{ESTILO}\n\nUn asistente de votación solo sabe responder estas situaciones: {temas}.\n"
            f"Escribe {N_FUERA} preguntas que una persona podría hacer el día de las elecciones o en su comunidad y que "
            "ninguna de esas situaciones responde: la mitad sobre temas cercanos a la elección y la otra mitad sobre "
            'otros temas de la vida diaria. Responde solo con JSON: {"frases": ["...", "..."]}')


def con_gpt(model):
    from openai import OpenAI
    client = OpenAI()

    def ask(prompt):
        r = client.chat.completions.create(model=model, response_format={"type": "json_object"},
                                           messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content
    return ask


def con_ollama(model):
    def ask(prompt):
        body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": 0.7},
                "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))["message"]["content"]
    return ask


def lista(texto):
    try:
        frases = json.loads(texto).get("frases", [])
    except (json.JSONDecodeError, AttributeError):
        frases = re.findall(r'"([^"]{6,200})"', texto)
    limpias = []
    for f in frases:
        f = re.sub(r"\s+", " ", str(f)).strip()
        if 2 <= len(f.split()) <= 25 and f not in limpias:
            limpias.append(f)
    return limpias


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ollama", help="modelo de Ollama (si no hay API key de OpenAI)")
    args = ap.parse_args()
    if args.ollama:
        ask, origen = con_ollama(args.ollama), f"ollama:{args.ollama}"
    elif os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("OPENAI_MODEL", CFG.get("openai_model", "gpt-6-luna"))
        ask, origen = con_gpt(model), f"openai:{model}"
    else:
        raise SystemExit("Falta la API key (set OPENAI_API_KEY=...) o usa --ollama qwen3.5:2b")

    salida = {"origen": origen, "fecha": date.today().isoformat(), "frases": {}, "fuera_de_alcance": []}
    for item in KB:
        salida["frases"][item["id"]] = lista(ask(prompt_situacion(item)))
        print(f"{item['id']:13s} {len(salida['frases'][item['id']])} frases", flush=True)
    salida["fuera_de_alcance"] = lista(ask(prompt_fuera()))
    print(f"fuera de alcance: {len(salida['fuera_de_alcance'])} preguntas")
    (HERE / "frases_generadas.json").write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Guardado en frases_generadas.json. Revísalo antes de usarlo.")


if __name__ == "__main__":
    main()
