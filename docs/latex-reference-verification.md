# LaTeX reference verification

Validated locally with TeX Live 2026 / pdfLaTeX and Python 3.14.
The native reference compiles to 41 pages. The desktop LaTeX compiler was
also checked. Generated content is maintained from the shared JSON source.

- All shipped .sty files inventoried with reviewed source hashes; runtime public
  declaration names checked against reference text.
- Markdown file links and generated Markdown/LaTeX/PDF manifests checked.
- PDF pages rendered and reviewed for clipping and layout; no overfull boxes
  in the final native documentation build.
- Source archives and wheels built; a wheel rebuilt from the source archive
  matched the direct wheel. Reference sources, PDFs and examples are included.

The texstage authoring example passes the normal checked build in present and
solutions modes, plus a separate handout build. It covers nine quiz types, an
unscored numeric estimate, delayed answer frames, session frames, video poster/link
packaging and four activities (tuple, SQL, SPARQL, Turtle). Bundle checks verify
activity references stay in private answer data.

The illustrated PDF has 39 pages and retains the 19 original synthetic screenshots.
The example.invalid video intentionally emits an unsupported-source warning;
actual movie playback, phone interaction and Office playback were not re-tested.

The new CI steps have been checked locally; hosted GitHub Actions has not been run
for this change. Original repositories and courses are not build inputs. The
separate preservation audit checks original file hashes, Git state and course pins.
