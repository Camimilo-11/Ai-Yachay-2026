"""
Aplica a index.html las correcciones en kichwa que hicieron los hablantes en revision_kichwa.csv.

Cómo usarlo (Windows, dentro de la carpeta Lab_llm):
    python kichwa\\aplicar_revision_kichwa.py --probar   # solo muestra qué cambiaría
    python kichwa\\aplicar_revision_kichwa.py            # escribe los cambios en index.html

Solo se aplican las filas con texto en la columna «kichwa_revisado».
Las marcas <b>, </b>, <i>, <small>... deben quedar igual que en el borrador; si no, la fila se salta.
Solo usa la biblioteca estándar de Python.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BLOQUES = {   # bloque del script -> (texto que lo abre, texto que lo cierra)
    "QU": ("const QU = {", "\n  };"),
    "QU_ATTR": ("const QU_ATTR = {", "\n  };"),
    "AQ": ("const AQ = {", "\n};"),
    "UI.qu": ("    qu: {", "}\n  };"),
}
LITERAL = r'(["\'])((?:\\.|(?!\1).)*)\1'


def marcas(t):
    return Counter(re.findall(r"</?[a-z]+", t))


def bloque(html, nombre):
    ini, fin = BLOQUES[nombre]
    a = html.index(ini)
    b = html.index(fin, a)
    return a, b


def reemplazar_clave(html, nombre, clave, nuevo):
    a, b = bloque(html, nombre)
    parte = html[a:b]
    m = re.search(r"(?<![\w$])" + re.escape(clave) + r":\s*" + LITERAL, parte)
    if not m:
        raise KeyError(f"no encontré la clave {nombre}.{clave}")
    lit_ini, lit_fin = m.start(1), m.end()
    parte = parte[:lit_ini] + json.dumps(nuevo, ensure_ascii=False) + parte[lit_fin:]
    return html[:a] + parte + html[b:]


def titular(texto):
    """El titular se escribe palabra por palabra (cada palabra entra con una animación)."""
    palabras = texto.split()
    return " ".join(f'<span class="w" style="--i:{i}">{p}</span>' for i, p in enumerate(palabras))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(AQUI / "revision_kichwa.csv"))
    ap.add_argument("--html", default=str(AQUI.parent / "index.html"))
    ap.add_argument("--probar", action="store_true", help="muestra los cambios sin escribir index.html")
    args = ap.parse_args()

    ruta = Path(args.html)
    with open(ruta, encoding="utf-8", newline="") as f:
        html = f.read()
    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        muestra = f.read(2048); f.seek(0)
        sep = ";" if muestra.count(";") >= muestra.count(",") else ","
        filas = list(csv.DictReader(f, delimiter=sep))

    hechos, saltados = 0, 0
    for fila in filas:
        clave, tipo = fila["clave"].strip(), fila["tipo"].strip()
        viejo_crudo = fila.get("kichwa_borrador") or ""
        nuevo = (fila.get("kichwa_revisado") or "").strip()
        viejo = viejo_crudo.strip()
        if tipo == "fragmento" and nuevo:   # conserva los espacios de los extremos del fragmento original
            ini = viejo_crudo[:len(viejo_crudo) - len(viejo_crudo.lstrip())]
            fin = viejo_crudo[len(viejo_crudo.rstrip()):]
            viejo, nuevo = viejo_crudo, ini + nuevo + fin
        if not nuevo or nuevo == viejo:
            continue
        if tipo != "titular" and marcas(nuevo) != marcas(viejo):
            print(f"  SALTADO {clave}: las marcas <...> no coinciden con el borrador")
            saltados += 1
            continue
        try:
            if tipo == "titular":
                html = reemplazar_clave(html, "QU", "h1", titular(nuevo))
            elif tipo == "texto":
                nombre, _, k = clave.rpartition(".")
                html = reemplazar_clave(html, nombre, k, nuevo)
            elif tipo == "constante":
                m = re.search(r"const " + re.escape(clave) + r" = " + LITERAL + ";", html)
                if not m:
                    raise KeyError(f"no encontré {clave}")
                html = html[:m.start(1)] + json.dumps(nuevo, ensure_ascii=False) + html[m.end() - 1:]
            elif tipo == "fragmento":
                v, n = json.dumps(viejo, ensure_ascii=False), json.dumps(nuevo, ensure_ascii=False)
                if v not in html:
                    raise KeyError(f"no encontré el fragmento {v}")
                html = html.replace(v, n)
            else:
                raise KeyError(f"tipo desconocido: {tipo}")
        except KeyError as e:
            print(f"  SALTADO {clave}: {e}")
            saltados += 1
            continue
        hechos += 1
        print(f"  {clave}: {viejo[:60]!r} -> {nuevo[:60]!r}")

    print(f"\n{hechos} cambios listos, {saltados} saltados.")
    if args.probar or not hechos:
        print("No se escribió nada." if args.probar else "")
        return 0
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        f.write(html)
    print(f"Guardado en {ruta}. Abre la página en kichwa y revisa antes de hacer el commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
