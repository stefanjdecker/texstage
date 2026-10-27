# texstage

Development extraction, version 0.2.1.dev0. This local snapshot is not a published release.

Beamer decks presented live. **texstage** presents a LaTeX Beamer deck in the browser - a
presenter window and a projector window - or in PowerPoint, and brings live content onto its
slides. The first kind is **texquiz**, live quizzes written in the deck: a quiz is a `quiz`
environment; the students answer on their phones, and the slide shows the results as they
come in. (Until 2026-10-10 the whole package was called texquiz.)

```latex
\documentclass{beamer}
\usepackage{texquiz}
\begin{document}
\quizjoinframe
\begin{quiz}[id=rdf-triple]{Which components form an RDF triple?}
  \choice{Entity, attribute, table}
  \choice*{Subject, predicate, object}
  \choice{Class, method, argument}
\end{quiz}
\end{document}
```

## What it does

- **Quizzes in LaTeX:** single and multiple choice, true/false, polls, numbers, short text, word
  clouds, ordering and sketches. Questions and answers are typeset by LaTeX, so formulas and
  code look as they do on your slides, also on the phones. Speed points, streaks, a
  leaderboard and a podium are optional per quiz.
- **One source, three PDFs:** a handout with placeholders (before the lecture), a solutions PDF
  (after it), and the live deck.
- **`texstage build`:** the live deck as a PowerPoint file with the quiz add-in, and the quiz
  bundle for the server; a layout check of the quiz frames.
- **`texstage serve`:** the quiz server, on the presenting laptop or hosted (a Docker image is in
  `deploy/`); phones join with a PIN or the QR code.
- **The browser presenter:** a presenter window with notes, next slide, timer and
  overview, and a projector window that shows the slides as PDF.js renders them. Ink with a
  pen or a stylus, a laser pointer, zoom and whiteboard pages; an iPad as presenter, paired by QR
  code; the annotated PDF for the students; a recording of the lecture; polls typed during the
  lecture, questions from the audience with upvotes, and drawings from the phones - with
  formulas (KaTeX).

## Install

```bash
python -m pip install -e .
```

Python 3.12 or newer. Building decks needs a TeX distribution with `pdflatex` and Beamer
(TeX Live, MiKTeX); the LaTeX package (`texquiz.sty`) comes with texstage and is found by its
commands. Recording
remuxes with `ffmpeg` if it is installed.

## Quick start

```bash
texstage pdf --present deck.tex          # a preview of the live deck
texstage present deck.tex               # present it in the browser (texstage)
texstage present deck.tex --powerpoint  # or in PowerPoint
texstage build deck.tex                 # the build alone: PowerPoint file and quiz bundle
texstage serve                          # the quiz server alone
```

`texstage present deck.tex` builds the deck if its build is missing or older than its sources,
starts the quiz server if none runs on this machine, and opens texstage's presenter window
on the deck; *Projector* opens the window for the projector. With `--powerpoint` it opens the
live PowerPoint file instead (its add-in once per PC: `texstage addin install`). `texstage
deck.tex` without a command presents as well.
The phones join at the address the join slide shows.

The source distribution holds the documentation: `docs/authoring.md` (writing quizzes, the
builds, presenting), `docs/architecture/design.md` and `docs/architecture/texstage-design.md` (how it works), and
`docs/architecture/content-types-design.md` (what comes next: videos, notebook cells).

## Licence

Apache License 2.0 - see `LICENSE` and `NOTICE`, which also lists the bundled third-party code
(PDF.js, perfect-freehand, pdf-lib, KaTeX) and its licences.
