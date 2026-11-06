# Changelog

## Unreleased — 0.2.1.dev3 candidate

- Prepare explicitly declared plugin activities before LaTeX, sharing one source
  between live data, handouts, solutions and static PowerPoint. Add bounded
  authoring hooks, source/asset identity checks and direct-pdfLaTeX exports.

- Add revision-2 plugin manifests with bounded typed engine results and explicit
  surface-view schemas, retaining revision-1 providers. Validate complete results
  in the worker, browser transport and server; pin schema identity in result keys.
- Guard presenter reset by epoch while preserving durable retry receipts, and
  add an SDK helper for actor-scoped evaluation correlations.
- Add cross-language schema, result, concurrency and browser conformance checks.

- Add an experimental plugin host: metadata discovery, explicit enablement and
  locks, portable wheels, generic LaTeX boxes and format-3 bundle preflight.
- Connect external slide types to isolated hooks, durable command receipts and
  evaluation jobs, presenter/projector/phone views and browser engine workers.
- Add catalog refresh/search/inspection and verified wheel installation, with
  independent examples in the separate texstage-plugins collection.
- Document the prototype and remaining API 1 release gates; retain legacy
  formats and built-in activity behavior. Extend the authoring reference.
- Fix presenter startup with an already saved key by initializing module helpers
  before opening the remembered deck.

- Update public-source installation, SQL activity restrictions, PowerPoint
  command guidance and release status; correct screenshot provenance.
- Regenerate the Markdown, LaTeX and PDF manuals from their shared source.

- Preserve the deck language from Babel/Polyglossia in the bundle. German
  decks use German live labels in the presenter and projector views.
- Retain compatibility with older language-free TQZ records and English
  fallback for unsupported languages. Ported from lecture-tools 97a3317.

## Earlier 0.2.1.dev2 candidate

- Added the lazy `compile_latex` API and `LatexResult`, supporting pdflatex
  and latexmk, source-relative includes, output/job names, bounded reruns
  and captured diagnostics without selecting a theme or content mode.
- Routed live-deck and plain PowerPoint compilation through the same runner.
- Added compiler, chapter compatibility and installed-package checks.

## Earlier 0.2.1.dev1 candidate

- Moved plain Beamer-to-PowerPoint conversion from lecture-tools into
  Texstage, with `texstage pptx` and the lazy `convert_beamer_to_pptx` API.
- Reused the live deck's slide writer while preserving fitted images, notes,
  overlay order, output paths, resolution options and legacy two-pass mode.
- Refuse to overwrite retained conversion artifacts; clean generated
  artifacts on failure unless explicitly kept.

## Earlier 0.2.1.dev0 candidate

- Normalize inline activity references and seeds to LF line endings across
  LaTeX versions, preserving indentation, comments and literal escape sequences.
- Reload lecturer keys after an atomic file replacement even when its timestamp
  matches the cached file, including same-size key renewals.

- Converted the manuals and references to portrait LaTeX articles with serif
  text, continuous sections, multipage tables and wrapped code.
- Unified the downloadable manual PDF and native LaTeX build, preserving all
  presenter and phone screenshots.

- Added a source-reviewed LaTeX package/command reference to the shared manual,
  a standalone reference page, compiled authoring examples and CI coverage checks.

- Extracted the standalone runtime, server, browser assets and four generic styles.
- Added the supported lazy `texstage.api` facade for companion integrations.
- Added hashed runtime/build/development locks, CI, source-archive rebuild checks
  and an installed-wheel smoke check.
- Added installation, development, contribution and release documentation.
- Added an illustrated user manual in Markdown and PDF, 19 screenshots of a
  synthetic session, a runnable manual demo, and locked PDF build dependencies.
- Added an editable LaTeX edition of the same manual, with shared screenshots,
  standalone latexmk build instructions and a CI compilation check.

This candidate has not been published. DBIS styles and course commands are owned
by the companion lecture-tools project. Publication rights for retained developer
utilities and hosted/platform validation remain release prerequisites.
