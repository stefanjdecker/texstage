# texstage

Present LaTeX Beamer decks in a browser or PowerPoint, with live quizzes written
in the same source. Students answer on their phones; the presenter controls the
session and shows the results on the slide.

This checkout is the **unpublished 0.2.1.dev0 development candidate**. Installation
instructions use this source or its verified wheel, not an assumed PyPI release.
See [release preparation](docs/releasing.md) for the remaining publication decisions.

## New to texstage?

texstage connects a Beamer source file, a private presenter browser, an audience display and participant phones. Start with the [illustrated user manual](docs/manual.md): it explains each part, installation on Windows/macOS/Linux, a complete first session, and how to edit your own quiz. Participants can skip installation and use the join address and PIN supplied by their presenter.

The [installation guide](docs/installation.md) begins with obtaining the candidate source and checking Python and TeX. PowerPoint, hosted servers and lecture-tools are optional paths.

## Features

- Quiz types include choice, polls, numeric and text answers, ordering and sketches.
- One source produces a handout, solutions and a live deck.
- The browser presenter provides notes, a projector view, ink, a timer and paired devices.
- PowerPoint exports carry live add-in slides and a server bundle.
- The server can run locally or behind an HTTPS proxy using the deployment example.

```latex
\documentclass{beamer}
\usepackage{texquiz}
\begin{document}
\quizjoinframe
\begin{quiz}[id=arithmetic]{What is two plus two?}
  \choice*{Four}
  \choice{Five}
\end{quiz}
\end{document}
```

## Start here

Python 3.12+ and a TeX distribution with Beamer are required for deck builds.
Create and activate a fresh virtual environment as described in
[installation](docs/installation.md), then from this repository:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt -r requirements/build.txt
python -m pip install --no-deps --no-build-isolation .
texstage pdf --present examples/demo/demo.tex
texstage present examples/demo/demo.tex
```

The `present` command opens the presenter; **Projector** opens the audience window.
Use a source copy for experimentation. Student-facing exports should be the
handout or solutions, not a live PowerPoint deck carrying presenter credentials.

## Documentation

| Guide | Use it for |
|---|---|
| [Illustrated user manual](docs/manual.md) ([PDF](docs/manual.pdf), [LaTeX](docs/manual-latex/README.md)) | Presenter walkthrough, phone screenshots, Q&A, exports and quick references |
| [Installation and quick start](docs/installation.md) | Requirements, first deck, troubleshooting and deployment |
| [Authoring](docs/authoring.md) | Quiz syntax, build modes and presenting |
| [Demo](examples/demo/README.md) | A runnable synthetic deck |
| [Integration API](docs/integration.md) | Supported API for companion course tooling |
| [Development](docs/development.md) | Tests, CI and installed-wheel checks |
| [Dependency locks](docs/dependencies.md) | Reproducible Python environments and updates |
| [Releasing](docs/releasing.md) | Candidate verification and publication prerequisites |
| [Architecture](docs/architecture/texstage-design.md) | Design context; some planned features may be unimplemented |

DBIS course commands, themes and subject notation belong to the separate
lecture-tools project. texstage has no dependency on that project.

## License and contributions

The runtime, generic styles and other paths identified in [NOTICE](NOTICE) are
covered by [Apache-2.0](LICENSE). Bundled third-party assets retain their own
licenses. Some retained developer utilities remain outside that scope and must
be resolved before repository publication. See [CONTRIBUTING.md](CONTRIBUTING.md),
[SECURITY.md](SECURITY.md) and [CHANGELOG.md](CHANGELOG.md).

The [LaTeX reference](docs/latex-reference.md) covers all four packages, author commands, options, modes and developer hooks. It is also included in the illustrated manual and its LaTeX edition. See the [runnable authoring examples](examples/reference/README.md).
