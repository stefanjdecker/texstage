# Convert Beamer to PowerPoint

`texstage pptx` converts a Beamer `.tex` document into a static `.pptx`: each
rendered PDF page becomes an image slide, and its Beamer notes become PowerPoint
speaker notes. Overlays become separate slides. Text and diagrams remain images,
not editable PowerPoint objects. PowerPoint itself is not needed to convert.

This command is available in the 0.2.1.dev1 candidate. Install this checkout in a
fresh environment using the [installation guide](installation.md). Python 3.12+
and `pdflatex` with Beamer and pgfpages must be available on PATH. Conversion does
not start a server or require a course root or DBIS styles.

```sh
texstage pptx talk.tex
texstage pptx talk.tex -o exports/talk.pptx --target-height 720
texstage pptx talk.tex --standard --note-side left --dpi 144
```

The default output is `talk.pptx` beside the input, even when invoked elsewhere.
An explicit relative output path is relative to your current working directory;
create its parent directory first. Existing output files can be replaced.
Relative `\input`, style and image paths resolve from the source directory.
The source document must contain its own `\begin{document}`; assemble individual
course frames with lecture-tools before converting the combined document.

## Options and notes

| Option | Behavior |
|---|---|
| `-o`, `--output` | Output file; defaults to the source path with `.pptx` extension |
| `--target-height N` | Approximate image height in pixels, default 1080; DPI is rounded |
| `--dpi N` | Fixed positive DPI; takes precedence over target height |
| `--standard` | 10 × 7.5 inch (4:3) canvas; default is 13.333 × 7.5 inches |
| `--note-side left/right` | Which half of the second-screen PDF carries notes; default right |
| `--legacy-two-pass-notes` | Compile separate slide and note PDFs and match pages by index |
| `--allow-note-mismatch` | In legacy mode only, pad missing notes or truncate extra ones |
| `--keep-artifacts` | Keep generated `.tex`, `.pdf` and auxiliary files for diagnosis |

Images are centered on the canvas and retain their aspect ratio. The default
second-screen method puts each slide and its note on the same PDF page before
splitting them, preserving alignment through overlays. Legacy mode is retained
for compatibility; its page counts must match unless explicitly allowed, and
padding cannot infer which slide originally owned a missing note.

The converter runs pdflatex twice per generated variant. Generated files have
the `_b2p_` prefix beside the source and are removed after success or failure,
unless `--keep-artifacts` is set. Existing files with those job names cause a
clear error instead of being overwritten or deleted. Move retained artifacts
before reusing that job name. The source directory must be writable.

For interactive quizzes, audience participation, native embedded video and a
server bundle, use the existing `texstage build` workflow. The plain converter
does not add those live behaviors to its image slides.

## Python integration

```python
from texstage.api import convert_beamer_to_pptx

output = convert_beamer_to_pptx("talk.tex", target_height=720, note_side="right")
print(output)  # absolute pathlib.Path
```

The function accepts `tex`, optional `output`, and keyword arguments
`target_height=1080`, `dpi=None`, `standard=False`, `note_side="right"`,
`legacy_two_pass_notes=False`, `allow_note_mismatch=False`, and
`keep_artifacts=False`. It emits progress to stdout. It raises `OSError` for file
or missing-tool errors, `ValueError` for invalid input and `RuntimeError` for
failed compilation or a legacy note-count mismatch. The CLI returns 0 for success,
2 for file/argument errors and 1 for compilation/conversion failures.

This is an additive API version 1 extension. Integrations should use
`texstage.api`, not import build internals. The existing lecture-tools
`beamer2pptx` command and script forward here with all options preserved.
The illustrated manual's screenshots describe the earlier 0.2.1.dev0 edition;
this page documents the new conversion command.
