r"""
Voto Claro desde la consola: el mismo chatbot de la página, sin abrir el navegador.

Usa app.py tal cual (mismos modelos, mismo orden B -> C -> A+, mismas respuestas verificadas de kb.json),
así que lo que responde aquí es lo mismo que respondería la página con el servidor.

Uso (Anaconda Prompt, dentro de la carpeta Lab_llm):
    conda activate apidb
    python chat_consola.py                                   # conversación: escribe preguntas, Enter vacío para salir
    python chat_consola.py "a ke ora puedo ir a botar" "no tengu sedula"   # una o varias preguntas
    python chat_consola.py --archivo preguntas.txt           # una pregunta por línea

Qué modelo responde (igual que el servidor):
    set OPENAI_API_KEY=...        Modelo B (GPT) si hay internet; la key solo vive en esa ventana
    set OLLAMA_MODEL=qwen3.5:2b   Modelo C (qwen, con Ollama abierto) si no hay B
    sin nada de lo anterior       Modelo A+ (MiniLM + letras), en la laptop
    set VOTO_MODE=A               fuerza un modelo: A, B o C

Los saludos («hola», «gracias») los responde la página, no los modelos; aquí llegan directo al modelo.
"""
import argparse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")   # tildes, ¿ y « » también al guardar la salida en un archivo
except (AttributeError, ValueError):
    pass

print("Cargando los modelos (unos segundos)...", flush=True)
import app  # noqa: E402  (carga MiniLM, el recuperador híbrido y, si hay key u Ollama, los modelos B y C)


def mostrar(r, elegida=False):
    quien = "elegida por la persona" if elegida else f"{r.get('modelo') or '-'} · {r.get('ms', 0)} ms"
    print(f"   [{quien} · situación: {r['intent']}]")
    print(f"   {r['texto']}")
    f = r.get("fuente")
    if f:   # igual que la página: las páginas son del instructivo; lo demás, otra fuente del CNE
        print(f"   Fuente: {'instructivo CNE, ' + f if f.startswith('pág') else f}")


def preguntar(texto, elegir):
    if not elegir:
        print(f"\nTú: {texto}")
    r = app.chat(app.Pregunta(pregunta=texto))
    mostrar(r)
    if r["intent"] == "PREGUNTAR":
        opciones = r["opciones"]
        for n, o in enumerate(opciones, 1):
            print(f"      {n}. {o['titulo']}")
        print("      0. Ninguna de estas")
        if not elegir:
            return r
        while True:
            pick = input("   Elige un número: ").strip()
            if pick.isdigit() and 0 <= int(pick) <= len(opciones):
                break
        if int(pick) == 0:
            print(f"   {app.FALLBACK}")
        else:
            mostrar(app.respuesta(opciones[int(pick) - 1]["intent"]), elegida=True)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("preguntas", nargs="*", help="preguntas a responder (sin ellas, modo conversación)")
    ap.add_argument("--archivo", help="archivo de texto con una pregunta por línea")
    args = ap.parse_args()

    h = app.health()
    activos = [f"B ({h['modelo_b']})" if h["modelo_b"] else None, f"C ({h['modelo_c']})" if h["modelo_c"] else None,
               "A+ (MiniLM + letras)" if app.REC_A is not None else "A (MiniLM)"]
    print("Modelos activos, en orden:", " -> ".join(m for m in activos if m), f"· modo {h['modo']}")

    preguntas = list(args.preguntas)
    if args.archivo:
        with open(args.archivo, encoding="utf-8-sig") as f:
            preguntas += [l.strip() for l in f if l.strip()]
    if preguntas:
        for q in preguntas:
            preguntar(q, elegir=False)
        return
    print("Escribe tu pregunta (Enter vacío para salir).")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        preguntar(q, elegir=True)


if __name__ == "__main__":
    main()
