# MDPI LaTeX source

This folder contains the LaTeX source package supplied with the current article PDF. Keep `main.tex`, `fig1.png`, and `Definitions/` together.

The workflow figure is the Figma export `fig1.png`; the Yachay Tech logo and MDPI class assets are under `Definitions/`. References are included inline in `main.tex`, so no separate `.bib` file is needed.

Compile from this folder with a LaTeX installation that provides the MDPI class dependencies; for example, run `latexmk -pdf main.tex`.
