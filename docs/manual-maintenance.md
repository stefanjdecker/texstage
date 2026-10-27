# Maintaining the illustrated manual

The [manual](manual.md) and [PDF](manual.pdf) share
[manual-content.json](manual-content.json) as their text source.
[build_manual.py](../maintenance/build_manual.py) handles the page layouts,
Markdown generation, capture integrity checks and build manifest. Edit the JSON
and renderer, then regenerate both reading formats. Do not edit the generated
Markdown independently.

## Build and check

Use a fresh Python 3.12+ environment in the new texstage checkout. The renderer
does not need a running texstage server or a TeX installation.

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/docs.txt
python maintenance/build_manual.py
python maintenance/build_manual.py --check
python maintenance/check_docs.py
```

The documentation lock pins ReportLab and its transitive dependencies. It is
separate from runtime dependencies; see [dependencies.md](dependencies.md).
To preview without replacing the committed outputs:

```sh
python maintenance/build_manual.py --output-dir .manual-build
```

The normal build writes manual.md, manual.pdf and manual-build.json in docs.
The manifest records hashes of the text, renderer, capture inventory and outputs.
The offline --check path uses only the Python standard library. It checks the
generated Markdown, manifest and screenshot hashes; it does not replace visual
review. CI also renders a fresh copy on Linux and retains it as a build artifact.

Render every PDF page with Poppler and inspect text, screenshots, captions,
tables and page boundaries before committing a refresh:

```sh
pdftoppm -r 120 -png docs/manual.pdf .manual-build/manual
```

Create .manual-build first if it does not exist. The PDF contains bookmarks for
each section. Screenshots retain their original resolution inside the PDF.

## Refresh the screenshots

The checked-in images are raw JPEG screenshots of the real application.
Desktop captures use 1280 x 720; phone captures use a 390 x 844 browser viewport.
The phone viewport emulates the available screen space. It is not a physical
phone test, and microphone recording and external-display placement were not
tested in the capture session.

Use [examples/manual/demo.tex](../examples/manual/demo.tex), an installed copy of
the matching texstage revision, and disposable output/data directories. From the
repository root, the isolated capture setup is:

```sh
texstage build examples/manual/demo.tex --output-dir .manual-build/deck --data .manual-data --server http://127.0.0.1:8765 --key manual-demo-only
texstage serve .manual-build/deck --data .manual-data --host 127.0.0.1 --port 8765 --public-url http://127.0.0.1:8765 --key manual-demo-only --owner manual-demo
```

The example key is intentionally synthetic and is only for this loopback demo.
Open /stage and /play on that local server. Present the deck, join as Alex, and
capture the library, workspace, join flow, question reading/answering/reveal,
overview, answer formats, Q&A, podium and export panel. The filenames and captions
in [captures.json](images/manual/captures.json) are the shot list.
Capture the export panel before generating the annotated PDF. Restore the browser
viewport and stop the demo server after the session.

Keep course sources, existing server data and original repository checkouts out
of this workflow. Do not commit the data directory, built live deck, recording
or exported participant results. Review each capture for private content.

Update captures.json with the source revision, capture date, viewport dimensions,
descriptions and SHA-256 of each new image. The image paths are relative to docs.
For an individual image, calculate its digest with:

```sh
python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('docs/images/manual/02-presenter-workspace.jpg').read_bytes()).hexdigest())"
```

Update the manual's version/date and provenance text as appropriate, regenerate,
run the checks and review the rendered PDF. Changes to the PDF renderer itself
also require regeneration because the build manifest includes its source hash.
