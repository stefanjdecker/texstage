# Integration API

Course tooling imports from `texstage.api`. API_VERSION remains 1. Imports are
lazy, so loading the facade does not load the PDF renderer or server.

| Name | Contract |
|---|---|
| `run_cli(argv=None)` | Standalone command arguments and integer return code |
| `convert_beamer_to_pptx(tex, output=None, **options)` | Plain Beamer export returning an absolute PPTX Path; added in 0.2.1.dev1 |
| `needs_build(folder, out, ignore=())` | Existing reason string or None |
| `slug(text)` | Existing deck identifier normalization |
| `Pdf` | Context manager with indexing/iteration; close it after use |
| `note_paragraphs(page, clip=None)` and `NOTE_TEMPLATE` | Existing note extraction and template |
| `latex_resources()` | Context manager yielding the directory of four generic styles |

Use the resource directory only inside its context. It can be temporary for a
zipped installation. LATEX_FILES identifies the four generic style files.
See [PowerPoint conversion](powerpoint.md) for the converter's parameters,
defaults, output paths, artifact behavior and errors.

Texstage owns generic conversion, slide rendering, PowerPoint writing and live
presentation. Lecture-tools owns course assembly, notebooks, checks, themes and
subject notation. Integrations must not import implementation modules or insert
another checkout's source path.

The tested candidate pair is Texstage 0.2.1.dev1 and lecture-tools 0.1.0.dev2.
The `beamer2pptx` course command forwards to `run_cli(["pptx", ...])`. Earlier API
version 1 callers remain compatible; new conversion callers need this candidate
or a later compatible version. The exact companion pin, wheel metadata and
`check_pair.py` prevent silently using a candidate without the conversion API.

Course styles, database and graph notation, DBIS appearance and optional live
loading remain separate modules in lecture-tools. The four generic style files
are unchanged; lecture-tools keeps a wheel-verified snapshot for offline LaTeX.
Chapter-specific compilation remains in lecture-tools for a subsequent step.
