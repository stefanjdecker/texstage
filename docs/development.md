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
`texlive-latex-extra texlive-fonts-recommended texlive-lang-german lmodern latexmk`.
TeX Live/MiKTeX can supply the Windows equivalents. Node 24 runs the JavaScript
tests without npm installation; JavaScript libraries are committed with notices.
The browser smoke tests need Chrome (or Edge) installed - Playwright, in
`requirements/dev.txt`, drives the installed browser and downloads none.

## CI scope

The CI workflow, `.github/workflows/ci.yml`, runs on every push and pull request
on GitHub and passes on `main`; a failed run shows on the repository's Actions
page. Its test job runs on Ubuntu 24.04 with Python 3.12, 3.13 and 3.14, and on
Windows 2025 with Python 3.14. Its steps, the scripts in `maintenance/`:

1. Linux: install TeX, the Ubuntu packages above.
2. Install the locked `requirements/dev.txt`, hashes checked.
3. Check the locks and the documentation: `lock_dependencies.py --check`,
   `check_public_content.py`, `check_docs.py`, `check_latex_reference.py` and
   `build_manual.py --check`.
4. Linux with Python 3.14: rebuild the illustrated manual into `.manual-build`.
5. Install texstage and the kinds of live activities, then `texstage kinds check`.
6. Linux with Python 3.14: compile the authoring examples
   (`check_reference_examples.py`) and rehearse the feature showcase
   (`check_showcase_example.py`).
7. Run the test suite, `python -m pytest tests -ra`.
8. Linux with Python 3.14: build and verify the distributions
   (`check_distributions.py`), install the wheels in a new environment and check
   them there (`pip check`, `check_installed.py`, `check_kinds_served.py`).
9. Keep the test report, `dist/`, the manual and the showcase's output for 14
   days, as the artifact `checks-<os>-py<python>`.

Windows has no TeX: its TeX-dependent tests skip, and it runs the Python and
JavaScript tests and the isolated test registry checks. Linux skips the
Windows-only registry and event-loop tests. Reports show skips explicitly. The
browser smoke tests run on every job, in the runner's Chrome, and fail there
instead of skipping (`TEXSTAGE_BROWSER_TESTS=required`). CI does not cover macOS,
browsers other than Chrome (Safari on iPhones), interactive Office behavior, real
phones on a real network or real-course renderings: they need separate
validation. No CI job opens a real course or uses a production server.

The workflow's second job, `container`, builds the Docker image on Linux with
locked Python dependencies and checks its health endpoint. It runs the kinds'
kit in the container and `maintenance/check_kinds_served.py`: a server of the
core's activity type there takes a deck with an activity of each of texstage's
kinds and checks a phone's entry of each in its pool. It uses a disposable
container/volume and publishes no image or network port. The phase-3 validation
on Windows had no Docker daemon for it; the job's steps were run locally with
Docker Desktop for F2's package 11 (2026-11-16). Another workflow, `pages.yml`,
publishes the homepage and the manual PDF when a push to `main` changes them.

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

An editable install keeps the version it was installed with. After a pull that
changes texstage's version, run the first two lines again: until then
`texstage kinds` and a build's deck.json name the old version. `pip check` does
not notice - the kinds need texstage 0.2.1.dev4 or later, which an older
candidate's install still is -, but the test
`tests/test_packaging.py::test_the_installed_metadata_is_this_texstages` fails
and says what to run.

The tests exercise Python, server/WebSocket behavior, Node-based browser logic,
LaTeX and PowerPoint file generation. Windows registration tests use the
temporary `Software\texquiz-tests` registry tree and clean it up. They do not
configure Office. TeX, Node and browser tests can skip when their tools are
missing; install all three before calling a local result a full suite.

The browser smoke tests (`tests/test_browser_smoke.py`) drive a real browser
through Playwright: a phone that joins, types a number and rejoins after *New
game*, the presenter window pausing a question while answers stream in, the
projector window's keys behind a dialog, and *Decks* while the server is away -
each against a real server on a free port. They take the installed Chrome;
`TEXSTAGE_BROWSER=msedge` takes Edge, and `TEXSTAGE_BROWSER=chromium` Playwright's
own Chromium after `python -m playwright install chromium`. Without Playwright or
the browser they are skipped, unless `TEXSTAGE_BROWSER_TESTS=required` (CI).

## Build and test the installed distribution

```sh
python maintenance/check_distributions.py --out dist/candidate
python -m venv .wheel-venv
.wheel-venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt
.wheel-venv/bin/python -m pip install --no-deps dist/candidate/texstage-0.2.1.dev8-py3-none-any.whl dist/candidate/texstage_kinds_rdf-0.1.0-py3-none-any.whl dist/candidate/texstage_kinds_sql-0.1.0-py3-none-any.whl
.wheel-venv/bin/python -m pip check
.wheel-venv/bin/python maintenance/check_installed.py
.wheel-venv/bin/python maintenance/check_kinds_served.py
```

On Windows replace `.wheel-venv/bin/python` with
`.wheel-venv\Scripts\python.exe`. Use a new output/environment folder for later
candidates. The smoke check runs from a temporary directory, asserts resources
come from site-packages, and builds a synthetic live deck without touching the
presenter's home data directory. With the kinds' wheels it runs their kit, builds
a deck with an activity of each of texstage's kinds - the build runs their
references with the kinds - and serves it: `check_kinds_served.py` starts a
server of the core's activity type on a free local port, with a key and a data
folder of its own, has a phone send each activity's first reference as its kind
takes one (a crowd graph a term per field), reveals the step and wants the
phone's own entry checked with status ok and judged correct - and a crowd
graph's terms in the step's picture. Without arguments it serves a deck of its
own, an activity of each kind made by texstage's build without LaTeX; given
`--bundles <folder>` the built decks there, passing over a deck without
activities unless `--every`.

The distribution check builds texstage's wheel and source archive and each
kind's, compares direct and sdist-rebuilt wheel contents and writes checksums.
`pip check` holds the kinds' bound on texstage - 0.2.1.dev4 or later - against the
wheel. A successful source test alone does not prove wheel resources are
complete. See [releasing.md](releasing.md) for the remaining gates.

## Local candidate evidence

See [validation-phase3.json](validation-phase3.json) for the completed local checks
and the explicit limits of those results.
