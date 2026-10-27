# LaTeX edition of the texstage manual

[main.tex](main.tex) is ordinary, editable LaTeX source. It uses
[manual.sty](manual.sty) for layout and the original JPEG screenshots in
[../images/manual](../images/manual/). It contains the same text as the
[Markdown manual](../manual.md), with a LaTeX-generated contents page.

## Compile without Python

Install TeX Live or MiKTeX with pdfLaTeX, latexmk, Latin Modern fonts and the
standard LaTeX extra packages. From the repository root:

```sh
cd docs/manual-latex
latexmk -pdf -interaction=nonstopmode -halt-on-error -no-shell-escape main.tex
```

This produces main.pdf beside the source. No texstage server, Python package,
course repository or network service is needed. Open the project folder in a
LaTeX editor and select main.tex as the main document, or use the command above.
The output contains selectable text, bookmarks and the original screenshots.

To build a copy elsewhere, copy this folder and ../images/manual while preserving
their relative positions. References to companion documentation link to files
beside this project in the repository. For a portable complete copy, use the
project's source archive.

The original [illustrated PDF](../manual.pdf) remains available. Its layout is
produced by the Python renderer; a PDF compiled from main.tex uses LaTeX typography
and may have different pagination.

## Edit and regenerate

You can edit and compile main.tex directly for your own version. In this repository,
[manual-content.json](../manual-content.json) is the shared text source for the
LaTeX, Markdown and original PDF editions. Repository edits to text belong there;
otherwise regenerating the manual will overwrite local changes to main.tex.

Edit manual.sty to change the LaTeX layout. The exporter lives in
[manual_latex.py](../../maintenance/manual_latex.py). From the repository root,
regenerate with:

```sh
python maintenance/build_manual.py
python maintenance/build_manual.py --check
```

Regeneration needs the locked documentation dependencies described in
[manual-maintenance.md](../manual-maintenance.md); compiling existing TeX does not.
CI checks the generated source and compiles it with pdfLaTeX. Review the compiled
pages visually after changing content, layout or screenshots.
