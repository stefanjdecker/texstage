# Integration API

Course tooling imports from `texstage.api`. API_VERSION is 1. Imports are lazy so
loading the facade does not load the PDF renderer or server.

| Name | Contract |
|---|---|
| `run_cli(argv=None)` | Standalone command arguments and integer return code |
| `needs_build(folder, out, ignore=())` | Existing reason string or None |
| `slug(text)` | Existing deck identifier normalization |
| `Pdf` | Existing context manager with indexing/iteration; close it after use |
| `note_paragraphs(page, clip=None)` and `NOTE_TEMPLATE` | Existing note extraction and template |
| `latex_resources()` | Context manager yielding the directory of four generic styles |

Use the resource directory only inside its context. It can be temporary for a
zipped installation. LATEX_FILES identifies the four generic style files.

DBIS themes and course-specific command wrappers belong to lecture-tools. Keep
their generated styles pinned to the tested texstage release; do not import
implementation modules or insert another checkout's source path.

This local development snapshot is 0.2.1.dev0. It is not a published release.
