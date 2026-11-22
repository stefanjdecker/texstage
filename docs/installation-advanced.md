# Additional installation recipes

For a first source installation, use [installation.md](installation.md). These recipes cover alternative delivery and hosting.

## From a candidate wheel

No release publishes wheels yet ([releasing.md](releasing.md)). A candidate's
wheels - texstage's and the kinds' - and their SHA256SUMS come from
`python maintenance/check_distributions.py --out dist/candidate` in a checkout
([development guide](development.md#build-and-test-the-installed-distribution)),
or from a CI run on GitHub, which keeps them for 14 days in its
`checks-ubuntu-24.04-py3.14` artifact (downloading it needs a GitHub account).
Verify each wheel's SHA-256 against that SHA256SUMS, use the
requirements/runtime.txt of the same revision, and install in a new environment:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt
python -m pip install --no-deps path/to/texstage-0.2.1.dev9-py3-none-any.whl
python -m pip install --no-deps path/to/texstage_kinds_rdf-0.1.0-py3-none-any.whl path/to/texstage_kinds_sql-0.1.0-py3-none-any.whl
python -m pip check
```

Replace the example paths with the actual artifacts. The candidate's SHA256SUMS
lists the kinds' wheels too: decks with crowd graphs, SQL, SPARQL or Turtle
activities need them where they are built and where they are served; quizzes
and texstage's own kinds (choice, number, text) need none. For development use the
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
Caddy, which gets a Let's Encrypt certificate for the domain by itself and passes
WebSockets through. The machine needs Docker with Compose, a DNS name pointing at
it and ports 80 and 443 open. In a checkout of this repository:

```sh
cd deploy
echo TEXSTAGE_DOMAIN=quiz.example.org > .env
echo TEXSTAGE_WORKERS=2 >> .env          # optional: the worker processes (below), default 2
docker compose up -d --build
docker compose exec texstage texstage lecturer add NAME --data /data
```

`.env` holds the domain and, optionally, the number of workers; git ignores it.
The last line makes a presenter key for one lecturer and shows it only then: give
it to that lecturer, and run it again with another name for the next one. A
running server takes a new key at once. The lecturers build their decks for the
server and upload them - and for PowerPoint register its add-in once per PC - as
"On a hosted server" in the [authoring guide](authoring.md#laptop-or-hosted-server)
describes. After a `git pull`, `docker compose up -d --build` builds and starts
the new version; the volumes keep bundles, games and keys.

The Docker build uses the committed Python runtime/build locks and installs the kinds of
live activities after texstage. The image's command - and the `command` of
docker-compose.yml - serves with the default activity type, the activity
framework's core, which uses them; with `--activities f1` added it serves with
F1's type, kept until a class has used the core. The core's type starts its
worker processes with the server - by default the physical cores less two, at
least one - and besides them two spares and one that normalizes. In a container
the default counts the host's cores, not the container's, so both commands give
`--workers 2` (docker-compose.yml: `TEXSTAGE_WORKERS` in deploy/.env): give as
many as the container's CPUs and memory hold. Each process takes some 25 MB at
rest, and a worker's checks took at most 67 MB in the load runs - but that is a
peak of ordinary checks, not a limit: one check may take up to 1 GB more than its
worker holds before the pool ends that worker, so leave room for that above the
processes' sum. Container base tags and operating-system packages are not digest
locked in this candidate; pin and test deployment images as part of the final
hosting decision.

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
