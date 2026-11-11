# Development


## Environment

Use CPython 3.12, 3.13 or 3.14 and a fresh virtual environment at the repository
root. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Linux/macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
```

If PowerShell activation is restricted, call `.venv\Scripts\python.exe` and the
other executables there directly. Do not change system policy just to activate.

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/dev.txt
python maintenance/lock_dependencies.py --check
python maintenance/check_docs.py
```

For the full suites install `pdflatex`, Beamer, latexmk, German language support,
recommended fonts and extra LaTeX packages. CI uses these Ubuntu packages:
`texlive-latex-extra texlive-fonts-recommended texlive-lang-german latexmk`.
TeX Live/MiKTeX can supply the Windows equivalents. Node 24 runs the JavaScript
tests without npm installation; JavaScript libraries are committed with notices.

## CI scope

The configured matrix targets Ubuntu 24.04 with Python 3.12, 3.13 and 3.14, and
Windows 2025 with Python 3.14. Linux installs TeX. Windows runs Python/JavaScript
checks and the isolated test registry checks where applicable; TeX-dependent
tests skip there unless TeX is installed. Linux skips Windows-only registry and
event-loop tests. Reports show skips explicitly.

This is the intended CI matrix, not a claim that hosted runs have already passed.
macOS, interactive browser/Office behavior and real-course renderings require
separate validation. No CI job opens a real course or uses a production server.

A separate Linux job builds the Docker image with locked Python dependencies and
checks its health endpoint. It uses a disposable container/volume and publishes
no image or network port. The local Windows validation did not run this job
because no Docker daemon was available.

## Run the source suite

```sh
python -m pip install --no-deps --no-build-isolation -e .
python -m pip install --no-deps --no-build-isolation -e kinds/texstage-kinds-sql -e kinds/texstage-kinds-rdf
python -m pip check
texstage kinds check
python -m pytest tests -ra
```

The second line installs the kinds of live activities: packages of their own in
`kinds/`, found by their entry points. `texstage kinds` lists what is installed,
and `texstage kinds check` runs the kit - the test every kind passes - on each.
Without them the tests of the registry and of the kit fail and say what to install;
the kinds' own tests find their sources in `kinds/`.

The tests exercise Python, server/WebSocket behavior, Node-based browser logic,
LaTeX and PowerPoint file generation. Windows registration tests use the
temporary `Software\texquiz-tests` registry tree and clean it up. They do not
configure Office. TeX/Node tests can skip when their tools are missing; install
both before calling a local result a full suite.

## Build and test the installed distribution

```sh
python maintenance/check_distributions.py --out dist/candidate
python -m venv .wheel-venv
.wheel-venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt
.wheel-venv/bin/python -m pip install --no-deps dist/candidate/texstage-0.2.1.dev3-py3-none-any.whl
.wheel-venv/bin/python maintenance/check_installed.py
```

On Windows replace `.wheel-venv/bin/python` with
`.wheel-venv\Scripts\python.exe`. Use a new output/environment folder for later
candidates. The smoke check runs from a temporary directory, asserts resources
come from site-packages, and builds a synthetic live deck without touching the
presenter's home data directory.

The distribution check compares direct and sdist-rebuilt wheel contents and
writes checksums. A successful source test alone does not prove wheel resources
are complete. See [releasing.md](releasing.md) for the remaining gates.

## Local candidate evidence

See [validation-phase3.json](validation-phase3.json) for the completed local checks
and the explicit limits of those results.
