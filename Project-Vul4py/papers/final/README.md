# Final research paper (v1-v5)

MDPI research-article format (LaTeX, for Overleaf), in English, written with the PaperOrchestra pipeline
(outline, verified literature, sections, review, format check). Every number comes from the version folders in
`experiments/`, `results/logs/` and `prereg/`; the v5 results are marked in red `[PENDIENTE: ...]` until the v5 run ends.

| File | Content | Status |
|---|---|---|
| `inputs/idea.md`, `inputs/experimental_log.md` | research questions, method per version, every number of v1-v4, v5 design | v5 results pending |
| `paper/main.tex` | the manuscript (MDPI class): 14 tables, 11 figures | v1-v4 complete; v5 results marked `[PENDIENTE]` |
| `paper/main.pdf` | the current draft compiled with the same class (24 pages) | draft |
| `paper/references.bib`, `paper/citation_map.json` | 46 references: the 27 of the v0 paper and 19 new ones, each checked on its source | done |
| `paper/outline.json`, `paper/worklog.json` | outline and record of the writing pipeline | done |
| `paper/figures/fig_study_flow.tex`, `fig_pipeline_c1.tex` | Figures 1-2, TikZ (compile with pdflatex after editing) | done |
| `paper/figures/fig_system_v5_chatgpt.pdf`, `fig_v6_workflow_chatgpt.png` | Figures 3 and 11, drawn with ChatGPT (GPT-6.2 Sol) from prompts listing every component; disclosed in the paper | done |
| `paper/figures/fig_system_v5.tex` | the same v5 diagram in TikZ, as an editable alternative | done |
| `paper/figures/fig_*.pdf` (data) | drawn by `results/figures/make_figures.py` from the repository's CSV/JSON files | done; a v5 figure is added when the run ends |
| `paper/Definitions/` | official MDPI class, styles and logos (MDPI Article Template) | as distributed by MDPI |

## Compiling in Overleaf

1. Compress the folder `paper/` into a .zip file.
2. Overleaf: New Project, Upload Project, choose the .zip; set `main.tex` as the main document if Overleaf asks.
3. Recompile and check that no red `[PENDIENTE: ...]` mark is left before submitting.

## When the v5 run ends

Fill Table 11, the v5 rows of Tables 12 and 14, the v5 paragraphs of Sections 4.8, 4.9, 5.1 and 6 and the last
sentence of the abstract from `runs/v5/results.csv`, `runs/v5/summary.*` and `runs/v5/confirm_v5.json`, and add the
v5 results figure.
