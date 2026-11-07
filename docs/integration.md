# Integration API

The companion Python package is `lecture-tools`, maintained in the separate
`lecture-tools-next` repository. Existing courses select a tested pair with their
own setup instructions and commit pins; publishing a Texstage documentation
update does not upgrade those environments.

Course tooling imports from `texstage.api`. API_VERSION remains 1. Imports are
lazy, so loading the facade does not load the PDF renderer or server.

| Name | Contract |
|---|---|
| `run_cli(argv=None)` | Standalone command arguments and integer return code |
| `convert_beamer_to_pptx(tex, output=None, **options)` | Plain Beamer export returning an absolute PPTX Path; added in 0.2.1.dev1 |
| `compile_latex(tex, **options)` and `LatexResult` | Generic pdflatex/latexmk runner and diagnostics; added in 0.2.1.dev2 |
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

The tested candidate pair is Texstage 0.2.1.dev3 and lecture-tools 0.1.0.dev4.
The `beamer2pptx` course command forwards to `run_cli(["pptx", ...])`. Earlier API
version 1 callers remain compatible; new conversion or compilation callers need their introducing candidate
or a later compatible version. The exact companion pin, wheel metadata and
`check_pair.py` prevent silently using a candidate without the conversion API.

Course styles, database and graph notation, DBIS appearance and optional live
loading remain separate modules in lecture-tools. Lecture-tools keeps a
wheel-verified snapshot of the four generic styles for offline LaTeX; that
snapshot is not updated by the experimental plugin implementation.
Lecture-tools delegates frame/deck engine execution through `compile_latex`.
It retains source assembly, course settings, reference/layout checks and locked-PDF
recovery policy. See the [compilation contract](compilation.md).

## Experimental plugin API

The [experimental plugin host](plugins.md) now supports independently installed
activity engines and custom slide types, including presenter, projector and phone
views. Profiles and locks are explicit command inputs. Existing SQL, SPARQL,
Turtle, quiz and video registries remain compatible while the complete prototype
passes the [design's release gates](architecture/plugin-system-design.md).
The plugin API is separate from the supported `texstage.api` facade above;
importing that facade does not discover or execute external plugins. Course
wrappers and verified style snapshots remain unchanged.
