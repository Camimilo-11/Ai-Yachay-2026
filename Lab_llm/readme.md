# Voto Claro

Asistente para resolver dudas de votación (Elecciones Seccionales y CPCCS, domingo 29 de noviembre de 2026) pensado para votantes de comunidades kichwa. Entiende preguntas escritas con errores y responde solo con información verificada del *Instructivo para Miembros de las Juntas Receptoras del Voto* del CNE (págs. 4–7). Para «¿dónde me toca votar?» remite a la consulta oficial del CNE (lugarvotacion.cne.gob.ec).

El instructivo lleva el nombre «Elecciones Seccionales y CPCCS 2027», pero el CNE adelantó estas elecciones al domingo 29 de noviembre de 2026; la página lo aclara.

Proyecto académico independiente; no es un sitio del CNE. Los modelos y su evaluación están en `voto_claro_modelos.ipynb`.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La página web. Funciona sola o conectada al servidor. Las letras (Andika y Lora) van dentro del archivo, así que se ve igual sin internet |
| `app.py` | Servidor local (FastAPI) que conecta la página con los modelos |
| `kb.json` | Base de conocimiento del instructivo, umbral τ = 0,60 del Modelo A simple y valores del recuperador híbrido (`"recuperador"`) |
| `recuperador.py` | Recuperador híbrido del Modelo A: MiniLM + comparación fonética de letras. Lo usan `app.py` y el notebook |
| `experimentos_rag.py` | Pruebas del recuperador híbrido frente al Modelo A original; guarda el resumen en `resultados_rag.csv` |
| `frases_extra.json` | Frases de ejemplo extra y preguntas fuera de alcance del recuperador (revisadas y descontaminadas) |
| `generar_frases.py` | Genera esas frases con GPT u Ollama; su salida cruda queda en `frases_generadas.json` |
| `requirements.txt` | Librerías necesarias |
| `iconos/` | Logo de Voto Claro en SVG, PNG (16 a 1024 px) e ICO; `app.py` los sirve y la página los usa como icono |
| `pasos/` | Ilustraciones de «Cómo votar, paso a paso» (WebP en dos tamaños). Si faltan, la página muestra un icono en su lugar |
| `evaluar_locales.py` | Compara modelos locales (Ollama y el Modelo A) con las preguntas del notebook |
| `kichwa/` | Tabla para que hablantes revisen los textos en kichwa y script que aplica sus correcciones |

## Ejecutar la página con los modelos

En PowerShell (usa directamente el Python del entorno `apidb`, sin `conda activate`):

```powershell
cd C:\Users\THINKPAD\Documents\GitHub\Ai-Yachay-2026\Lab_llm
$py = "C:\Users\THINKPAD\anaconda3\envs\apidb\python.exe"
& $py -m pip install fastapi uvicorn        # solo la primera vez
$env:OPENAI_API_KEY = "tu-key-real"          # opcional: sin key responde solo el Modelo A
& $py -m uvicorn app:app --port 8000
```

Para detener el servidor: Ctrl + C.

Abre **http://localhost:8000**. La primera vez tarda unos segundos en cargar el Modelo A.

## Qué modelo responde

- **Con API key:** responde el **Modelo B** (GPT, `gpt-6-luna`). Si falla, por ejemplo sin internet, responde el **Modelo C** (Ollama, si está activado) y, si tampoco está, el **Modelo A** local.
- **Sin API key:** responde el **Modelo C** si está activado; si no, el **Modelo A** (MiniLM con el recuperador híbrido).
- Cada respuesta muestra su fuente y qué modelo la dio.
- Para forzar uno: `set VOTO_MODE=A`, `B` o `C` antes de `uvicorn` (en PowerShell: `$env:VOTO_MODE = "A"`).

## Modelo A mejorado: recuperador híbrido

Sin internet y sin Ollama responde el Modelo A, que ahora usa `recuperador.py`:

1. Corrige la pregunta con una clave fonética pensada para cómo escriben el español los hablantes de kichwa (e/i, o/u, b/v, c/s/z, k/qu, ll/y, h muda): `a qoe hura puedo ir a botar` → `a que hora puedo ir a votar`.
2. Compara el significado (MiniLM) y la forma escrita (n-gramas de letras) con las frases de ejemplo, la descripción de cada situación y 183 frases más de `frases_extra.json`.
3. Dice «no sé» si la pregunta se parece más a una de las 36 preguntas fuera de alcance de `frases_extra.json` o si usa palabras que el instructivo no tiene.
4. Si duda entre dos situaciones, pregunta «¿Tu pregunta es sobre…?» con dos botones y «Ninguna de estas». No afirma nada que la persona no haya elegido.

Resultados en las 138 preguntas de prueba:

| Modelo A | Aciertos sin preguntar [IC 95 %] | Error inseguro | Fuera de alcance respondidas | Resueltas preguntando | Situación correcta entre las 3 primeras |
|---|---|---|---|---|---|
| Original (τ 0,60) | 42 % [34–50] | 16 % | 17 % | — | 77 % |
| A+ v1 (frases del instructivo) | 59 % [50–67] | 9 % | 11 % | 70 % | 94 % |
| **A+ v2 (+ frases extra y anclas)** | **73 % [65–80]** | **8 %** | 17 % | **81 %** | 98 % |

- «Resueltas preguntando» = respuesta directa correcta, la correcta entre las dos opciones, o «no sé» a una pregunta fuera de alcance. En 8 % de las preguntas las opciones no traían la correcta (incluye preguntas fuera de alcance, donde la persona puede tocar «Ninguna de estas»).
- A+ v2 acierta más que el original (McNemar: 51 frente a 8 preguntas, p < 0,001) y que A+ v1 (24 frente a 4, p < 0,001), con menos error inseguro. Sin preguntar ya iguala a qwen3.5:2b (75 %; diferencia no significativa, p = 0,87) y responde en milisegundos.
- Con errores de teclado, que la clave fonética no corrige, A+ v2 resuelve 73 % preguntando, con 9 % de error inseguro (el original: 47 % de aciertos y 23 % de error).
- `frases_extra.json` sale de `generar_frases.py`: GPT escribió 20 preguntas por situación y 40 fuera de alcance a partir de la descripción y la respuesta, sin ver nunca las preguntas de prueba (el resultado crudo está en `frases_generadas.json`). Revisé las etiquetas a mano y quité las que se parecían a cualquier pregunta de desarrollo o prueba.
- Los valores de `"recuperador"` en `kb.json` se eligieron solo con preguntas de desarrollo (error inseguro ≤ 5 % y opciones sin la correcta ≤ 5 %). Para repetir la comparación (menos de un minuto, sin internet): `python experimentos_rag.py`.
- Para volver al Modelo A original: `set VOTO_A=simple` antes de `uvicorn`.
- Cuidado: la clave fonética se parece al ruido sintético de las preguntas de prueba, y la prueba se miró varias veces mientras se desarrollaba A+; con frases reales la mejora puede ser menor.

## Modelo local con Ollama (opcional)

El **Modelo C** clasifica la pregunta igual que el Modelo B, pero en tu computadora y sin internet. Usa un modelo pequeño de [Ollama](https://ollama.com) con la salida limitada a la lista de situaciones y, en el prompt, las frases de ejemplo de `kb.json`.

1. Instala Ollama para Windows ([ollama.com/download/windows](https://ollama.com/download/windows)) y ábrelo.
2. En Anaconda Prompt, descarga el modelo recomendado: `ollama pull qwen3.5:2b` (unos 3 GB).
3. Enciende el servidor con ese modelo:

```bat
set OLLAMA_MODEL=qwen3.5:2b
uvicorn app:app --port 8000
```

   En PowerShell: `$env:OLLAMA_MODEL = "qwen3.5:2b"`. La consola dirá «Modelo C listo» cuando el modelo esté cargado.

### Por qué qwen3.5:2b

Resultados en las 138 preguntas de prueba del notebook (11 situaciones, con errores de ortografía), medidos en la CPU de la laptop (32 GB de RAM) en noviembre de 2026:

| Modelo | Aciertos [IC 95 %] | Ruido fuerte | Error inseguro | Latencia (mediana) |
|---|---|---|---|---|
| C · qwen3.5:2b + ejemplos | 75 % [67–81] | 61 % | 10 % | 8,3 s |
| llama3.2:3b + ejemplos | 52 % [44–60] | 43 % | 1 % | 0,9 s |
| bge-m3 (embeddings, τ 0,70) | 54 % [45–62] | 26 % | 4 % | 45 ms |
| A · MiniLM (τ 0,60) | 42 % [34–50] | 28 % | 16 % | 15 ms |
| Motor local de la página (sin servidor) | 69 % [61–76] | 67 % | 12 % | — |

- qwen3.5:2b acierta más que MiniLM, bge-m3 y llama3.2 (McNemar exacto, p < 0,001). Frente al motor local de la página la diferencia no es significativa (p = 0,23).
- La fila del motor local de la página se midió aparte, ejecutando su JavaScript con las mismas 138 preguntas; ese script no está en el repositorio.
- Su latencia fue estable (máximo 9,8 s), por debajo del límite de 20 s de `OLLAMA_TIMEOUT`.
- La mayoría de sus errores inseguros confunden situaciones vecinas: movilidad reducida con atención preferente y persona ciega con voto asistido.
- El umbral del Modelo A en `kb.json` pasó de 0,40 a 0,60: es el τ con más aciertos y error inseguro ≤ 10 % en las preguntas de desarrollo (en las de prueba, el error inseguro fue 16 %).

### Repetir la comparación

```bat
ollama pull llama3.2:3b
ollama pull bge-m3
python evaluar_locales.py --llm llama3.2:3b qwen3.5:2b --emb bge-m3 --minilm --ejemplos
```

Tarda unos 35 minutos en CPU. Cada respuesta se guarda en `cache_locales.json`: si se corta, el mismo comando sigue desde donde quedó (borra ese archivo para medir desde cero). El detalle por pregunta queda en `resultados_locales.csv`.

## Revisión del kichwa

Los textos en kichwa son un borrador. Para corregirlos:

1. Abre `kichwa/revision_kichwa.csv` en Excel o Google Sheets. Cada fila tiene el texto en español, el borrador en kichwa y una columna vacía `kichwa_revisado`.
2. La persona que revisa escribe su versión en `kichwa_revisado` (y su nombre en `revisado_por`). Las filas que estén bien se dejan vacías. Hay que mantener las marcas como `<b>` y `</b>` donde estén.
3. Guarda el archivo como CSV (UTF-8) con el mismo nombre.
4. En PowerShell, dentro de esta carpeta:

```powershell
python kichwa\aplicar_revision_kichwa.py --probar   # muestra qué cambiaría
python kichwa\aplicar_revision_kichwa.py            # aplica los cambios a index.html
```

Abre la página en kichwa para revisar el resultado antes de hacer el commit.

## GitHub Pages

GitHub Pages solo publica archivos estáticos: no puede ejecutar Python ni los modelos. Si se publica `index.html` ahí, la página usa un buscador simple incluido en el propio HTML. Para la versión con los modelos, ejecuta `app.py` como se indica arriba.

## Privacidad y seguridad

- La API key se lee de una variable de entorno; nunca la escribas en un archivo del repositorio.
- El servidor no guarda las preguntas.
- Los textos en kichwa son un borrador sin validar; deben revisarlos hablantes antes de usarse con votantes (ver «Revisión del kichwa»).
