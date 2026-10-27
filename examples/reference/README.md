# Complete authoring example

From the repository root, with the locked development dependencies installed:

```sh
python maintenance/check_reference_examples.py
```

This builds present/solutions/handout PDFs and a checked browser/PowerPoint bundle
under `.reference-build`, using only synthetic data and a disposable localhost key.
It neither starts a server nor publishes a bundle. It tests all nine quiz types,
an unscored numeric estimate, delayed answers, session frames, video poster/link
packaging, tuple collection and all three code engines.

The unsupported example.invalid video address deliberately requires no download.
It produces a documented unsupported-source warning; actual video playback is not
tested. The poster is an unchanged synthetic screenshot from the illustrated manual
(see docs/images/manual/captures.json), reused solely as a packaging fixture.

For a plain PDF, run from this directory:

```sh
pdflatex -interaction=nonstopmode -halt-on-error reference.tex
```

Plain compilation defaults to a handout. Use the texstage CLI modes described in the
[LaTeX reference](../../docs/latex-reference.md) for other exports. For isolated builds
prefer the verification script, which keeps generated files outside this directory.
