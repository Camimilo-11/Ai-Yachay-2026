# Voto Claro

Asistente para resolver dudas de votación (Elecciones Seccionales y CPCCS, domingo 29 de noviembre de 2026) pensado para votantes de comunidades kichwa. Entiende preguntas escritas con errores y responde solo con información verificada del *Instructivo para Miembros de las Juntas Receptoras del Voto* del CNE (págs. 4–7).

Proyecto académico independiente; no es un sitio del CNE. Los modelos y su evaluación están en `voto_claro_modelos.ipynb`.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La página web. Funciona sola o conectada al servidor |
| `app.py` | Servidor local (FastAPI) que conecta la página con los modelos |
| `kb.json` | Base de conocimiento del instructivo y umbral τ = 0.40 elegido en el notebook |
| `requirements.txt` | Librerías necesarias |

## Ejecutar la página con los modelos

En PowerShell, dentro de esta carpeta:

```powershell
conda activate apidb
pip install -r requirements.txt
$env:OPENAI_API_KEY = "sk-..."     # opcional: sin key responde solo el Modelo A
uvicorn app:app --port 8000
```

Abre **http://localhost:8000**. La primera vez tarda unos segundos en cargar el Modelo A.

## Qué modelo responde

- **Con API key:** responde el **Modelo B** (GPT, `gpt-6-luna`). Si falla, por ejemplo sin internet, responde el **Modelo A** local.
- **Sin API key:** responde el **Modelo A** (Sentence Transformers + FAISS).
- Cada respuesta muestra su fuente y qué modelo la dio.
- Para forzar uno: `$env:VOTO_MODE = "A"` o `"B"` antes de `uvicorn`.

## GitHub Pages

GitHub Pages solo publica archivos estáticos: no puede ejecutar Python ni los modelos. Si se publica `index.html` ahí, la página usa un buscador simple incluido en el propio HTML. Para la versión con los modelos, ejecuta `app.py` como se indica arriba.

## Privacidad y seguridad

- La API key se lee de una variable de entorno; nunca la escribas en un archivo del repositorio.
- El servidor no guarda las preguntas.
- Los textos en kichwa son un borrador sin validar; deben revisarlos hablantes antes de usarse con votantes.
