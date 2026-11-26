# Paper 1: research proposal (milestone 1, covers v0)

MDPI research-article format (LaTeX, for Overleaf), in English.

| File | Content | Status |
|---|---|---|
| `inputs/idea.md` | problem, research question, objective, method, baselines, planned work, schedule | draft, to be confirmed by the author |
| `inputs/experimental_log.md` | the v0 run: setup, per-case results, aggregate metrics, observations, limits (every number from `v0_mvp/`) | draft, to be confirmed by the author |
| `inputs/system_diagram_spec.md` | components and arrows of the system diagram | the diagram itself is drawn by the author (not AI-generated, as the rubric requires) |
| `paper/main.tex` | the manuscript (MDPI class) | first full draft; red `[PENDIENTE: ...]` marks are details the author must fill in |
| `paper/references.bib`, `paper/citation_map.json` | 27 references, each checked on its source page | done |
| `paper/figures/fig_v0_pilot.pdf` | Figure 2, drawn by `figures/make_figures.py fig_v0` from `v0_mvp/results.csv` | done |
| `paper/outline.json`, `paper/worklog.json` | outline and record of the writing pipeline | done |
| `paper/Definitions/` | official MDPI class, styles and logos (MDPI Article Template) | as distributed by MDPI |

## Compiling in Overleaf

`paper/` is a complete MDPI project: `main.tex`, `references.bib`, `figures/` and the official `Definitions/`
folder of the MDPI Article Template (class `mdpi.cls`, style `mdpi.bst`, logos).

1. Compress the folder `paper/` into a .zip file.
2. Overleaf: New Project, Upload Project, choose the .zip; set `main.tex` as the main document if Overleaf asks.
3. When the system diagram is ready, export it as `figures/fig_system_overview.pdf` and replace the red box of
   Figure 1 with `\includegraphics[width=\linewidth]{figures/fig_system_overview.pdf}`.
4. Recompile and look for every red `[PENDIENTE: ...]` before submitting.

`paper/main.pdf` is the current draft compiled with the same class.

Every number in the paper comes from `v0_mvp/` (results, oracle verdicts and saved model answers); every
reference was checked on its source page before it was cited.
