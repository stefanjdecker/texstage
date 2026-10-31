# A picnic, planned together

A complete texstage feature tour built around a familiar task: planning a picnic.
The main file is [showcase.tex](showcase.tex). It contains runnable slides,
questions, activities and brief feature notes. Supporting files supply a
short silent clip for local video playback and tiny fictional datasets.

## What is included?

- All nine quiz types across 13 questions, including alternative phone inputs.
- Five activities: two- and three-field contributions, SQL, SPARQL and Turtle.
- An original silent video, with a real poster, packaged for offline local playback.
- Ordinary slides, overlays, math, links, notes, join, leaderboard and podium frames.
- A [feature checklist](COVERAGE.md) distinguishing executable source examples
  from browser controls and optional platform/deployment workflows.

Everything is synthetic. No DBIS course files, branding, accounts or data are
needed. The code activities use fixed examples; they do not consume the audience's
earlier live contributions. Preferences do not automatically change later slides.

## Install once

Follow the project's [installation guide](../../docs/installation.md) for Windows,
macOS or Linux. Use the matching candidate source checkout, Python 3.12-3.14, a
new virtual environment, and a TeX distribution with pdfLaTeX, Beamer, TikZ and
booktabs. This candidate is not assumed to be available on PyPI.

In the activated environment, at the repository root:

    python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt -r requirements/build.txt
    python -m pip install --no-deps --no-build-isolation .
    texstage --help
    pdflatex --version

The CLI supplies all four texstage style files to TeX. You do not need to install
lecture-tools or copy course-specific styles. The supplied MP4 is ready to use;
Pillow and ffmpeg are needed only to regenerate it with make_media.py.

## Start the demonstration

From the repository root, with a free port and a dedicated demo data folder:

    texstage present examples/showcase/showcase.tex --port 8766 --data .showcase-data --no-tunnel

Keep the terminal and presenter open. The first build takes longer than later
starts. Projector opens the audience window. Notes are private to the presenter.
The running server supplies the join address, QR code and PIN.

Do not use an already-running course server on this port: present can reuse an
existing server. Use another free port if needed. This command isolates demo
session storage from ordinary lectures.

On the same computer, participant browsers can use http://127.0.0.1:8766/play.
For actual phones, use the LAN address shown by texstage, on the same reachable
network. Do not type localhost on a phone. Allow the local server through the
firewall if prompted and permitted. An isolated guest Wi-Fi network may block
peer connections. The [manual](../../docs/manual.md) explains HTTPS hosting and
tunnels when participants are remote.

Use three real devices or independent browser profiles, named Alex, Sam and
Riley. Tabs in one profile can share an identity. One participant is sufficient
for basic operation; three give useful result distributions, upvotes, leaderboards
and the two-person agreement example.

For a downloaded portable source pack, enter its unpacked folder and replace
examples/showcase/showcase.tex in commands with showcase.tex. The pack includes
matching styles for plain TeX use, but a working texstage installation is still
required for live interaction. The included INSTALLATION.md is a copy of the
matching installation guide; acquire the candidate project source for its locks
and installer if you do not already have it.

## Build without starting a server

    texstage pdf --present examples/showcase/showcase.tex
    texstage pdf --solutions examples/showcase/showcase.tex
    texstage pdf --handout examples/showcase/showcase.tex
    texstage build examples/showcase/showcase.tex --server http://127.0.0.1:8766 --data .showcase-data

Default output is examples/showcase/texquiz-out/. Build creates the live and static
PowerPoint files, browser bundle, uploadable bundle ZIP, and stage PDF with notes.
A raw PDF cannot run phone interactions. Present-mode PDF builds also contain
build assets; use the slide-only preview produced by the verification script for
a clean review copy.

To compile plain LaTeX without the CLI, put the matching four generic style files
on TeX's search path. Select the mode before input:

    pdflatex "\def\texstagemode{solutions}\input{showcase.tex}"

Plain compilation defaults to handout behavior. The portable source pack includes
the styles beside the source for this purpose.


## Rebuild and verify this example

With the project's development/build dependencies and a recent Node.js installed:

    python maintenance/check_showcase_example.py

This builds and checks the deck, verifies all nine quiz types and five activities,
checks the media packaging and private references, runs the three code examples
against texstage's actual JavaScript/WASM engines, and writes slide-only preview,
solutions and handout PDFs under .showcase-build/output/. It does not start a
server or publish anything. Visual review and hardware rehearsal remain separate.

All original source, sample data, illustration/video and documentation in this
directory are provided under the project's Apache-2.0 license. There is no
third-party footage or music. See the repository LICENSE and NOTICE.
