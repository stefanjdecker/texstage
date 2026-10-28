# Article-format verification

Converted on 28 October 2026 in an isolated checkout using Python 3.14,
TeX Live 2026 / pdfLaTeX and latexmk 4.88.

The [manual](manual.pdf), including its LaTeX reference, is a 29-page portrait
A4 article. Its [native source](manual-latex/main.tex) uses the standard article
class, 11-point serif text, a conventional title and contents, continuous numbered
sections, numbered figures, multipage tables with repeated headers, and wrapped
code. Short code examples stay together. Both the published PDF and independent
LaTeX builds use this source and [documentation style](manual-latex/manual.sty).

The content audit compared the shared JSON with the preceding revision:
section order, all examples and table entries are unchanged. Only the
documentation-style description/package list and one page-dependent locator were
updated. All 19 original synthetic screenshots retain their file hashes and are
included in the generated LaTeX. Runtime sources, lecture styles, examples,
tests and dependency locks are unchanged.

Validation covered terminal compilation, the desktop editor compiler, portrait
A4 page dimensions, selectable text, PDF page rendering and visual inspection,
the style inventory, generated-document manifests and local documentation links.
The final terminal build has no overfull boxes. Underfull table warnings can
remain because columns use fixed proportional widths and ragged text.

The preview build uses --output-dir and compiles the same article in its copied
project. The source archive contains the PDF, TeX source, style, screenshot assets
and generators; its wheel rebuild matches the direct wheel's members. The
compatibility docs extra remains in the lock, but the PDF builder no longer uses
ReportLab or other third-party Python packages. CI now calls the unified builder
once; hosted GitHub Actions was not run for this layout change.

The previous [functional verification](latex-reference-verification.md) remains
applicable to the unchanged authoring examples. No runtime, presenter, phone or
course behavior was re-tested for this formatting change. The separate
preservation audit confirmed 249 original repository file hashes, its Git state,
and four course heads, tools pins and tracked working-tree states. Ignored course
outputs were not exhaustively inventoried.
