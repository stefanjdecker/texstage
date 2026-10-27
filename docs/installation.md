# Install and present a first deck

This candidate is installed from a local checkout or a verified candidate wheel.
Python 3.12+ is required. Deck builds use `pdflatex` and Beamer from TeX Live or
MiKTeX. The server can serve already-built bundles without a TeX installation.
Recording remux uses ffmpeg when installed. PowerPoint presentation needs Office
and add-in setup; the browser presenter does not need Office.

## From source

In the checkout, create an environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS activation is `. .venv/bin/activate`. With it active:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt -r requirements/build.txt
python -m pip install --no-deps --no-build-isolation .
texstage --help
pdflatex --version
texstage pdf --present examples/demo/demo.tex
texstage present examples/demo/demo.tex
```

Commands find the installed generic `.sty` files themselves. A plain external
`pdflatex` call needs those files on its TeX search path. The [demo guide](../examples/demo/README.md)
uses texstage so no global TeX configuration changes are needed.

## From a candidate wheel

Verify its SHA-256 against the candidate's SHA256SUMS, use the matching
requirements/runtime.txt, and install in a new environment:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt
python -m pip install --no-deps path/to/texstage-0.2.1.dev0-py3-none-any.whl
```

Replace the example path with the actual artifact. For development use the
[development guide](development.md) instead of mixing installations into an
existing course environment.

## Build and serve separately

```sh
texstage build examples/demo/demo.tex
texstage serve
```

By default the server uses port 8470 and a local data directory chosen by
texstage (`~/.texstage`, or the existing legacy `~/.texquiz` when appropriate).
Use `--data PATH` to isolate a rehearsal. No existing data is migrated by install.
For students' phones, the advertised URL must be reachable from their network;
`localhost` on a phone is the phone itself. See the networking and hosting
instructions in [authoring.md](authoring.md).

For PowerPoint, run `texstage addin install` on the presenting Windows PC, then
`texstage present examples/demo/demo.tex --powerpoint`. This is an intentional
user setup action; package installation and CI do not configure Office itself.

## Hosting

[deploy/docker-compose.yml](../deploy/docker-compose.yml) runs texstage behind
Caddy. Configure a domain, DNS and deployment secrets as described in the
[authoring guide](authoring.md), then build from the repository root. The Docker
build uses the committed Python runtime/build locks. Container base tags and
operating-system packages are not digest locked in this candidate; pin and test
deployment images as part of the final hosting decision.

The deployment example preserves data in named volumes. Keep presenter keys
private, use HTTPS, restrict trusted forwarded headers to your proxy, and back
up the data volume before upgrading. See [SECURITY.md](../SECURITY.md).

## Common problems

| Symptom | Check |
|---|---|
| `texstage` not found | Activate the environment or call its Scripts/bin executable |
| `pdflatex` not found | Install TeX and add its executable directory to PATH |
| A LaTeX package is missing | Install the extra Beamer/TeX packages; inspect the first TeX error |
| Phones cannot join | Check the advertised URL, firewall and shared network |
| Dependency hash fails | Stop and check the lock/artifact origin; do not disable hash checking |
| A platform has no wheel | Use a tested OS/Python combination or validate an explicit dependency update |

Include a minimal synthetic deck and version details in a bug report. Remove
keys and student data first.
