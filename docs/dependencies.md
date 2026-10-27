# Dependency locks

The package metadata declares compatible dependency ranges. The files in
`requirements/` fix the exact third-party versions used for candidate builds and
tests, including transitive dependencies, platform markers and SHA-256 hashes.
No local paths, private indexes or credentials are embedded in the locks.

| File | Purpose |
|---|---|
| `runtime.txt` | Runtime dependency set |
| `build.txt` | Build frontend, setuptools backend and the lock generator |
| `dev.txt` | Runtime, build and test dependencies; constrained by both other locks |
| `docs.txt` | texstage's PDF manual renderer and its dependencies; constrained by runtime pins |
| `*.in` | Generated direct inputs; edit pyproject.toml rather than these files |
| `lock-manifest.json` | Hashes of dependency metadata, generator, inputs and lock outputs |

For lecture-tools, `runtime.txt` includes **all optional authoring dependencies**
(slides, live and notebooks); its base wheel still has no third-party dependencies.
The unpublished texstage package itself is deliberately absent from these locks.
`requirements/texstage.json` records the runtime requirements extracted from the
exact wheel named in `texstage-assets.lock.json`. Install the tested companion
wheel separately with `--no-deps`; do not resolve the development version on PyPI.

For texstage, `runtime.txt` is its full runtime dependency set. Vendored JavaScript
and LaTeX are committed resources, not packages downloaded by these lockfiles.

## Install and verify

Create and activate a new Python environment, then run from the repository root:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/dev.txt
python maintenance/lock_dependencies.py --check
python -m pip install --no-deps --no-build-isolation -e .
```

`--only-binary` fails on a platform without a compatible wheel instead of compiling
an unpinned source build. `--check` is offline: it detects changed metadata,
generator, inputs or output hashes. It is not a fresh resolution or vulnerability
scan. Installing with pip's `--require-hashes` verifies the downloaded artifacts.

The locks use uv's universal resolution for Python 3.12 and newer. The CI target
matrix is CPython 3.12–3.14 on Linux and 3.14 on Windows; a marker in a lock does
not establish support for every platform, architecture or future Python version.
TeX distributions, OS packages, Node, browsers and Office remain external tools.
Hosted runner images and apt packages can change, so this is not a claim of
bit-for-bit reproducible operating-system images or PDFs across TeX versions.

## Refresh deliberately

The resolver version, uv 0.9.12, is pinned in the build lock. With the development
environment active:

```sh
python maintenance/lock_dependencies.py
python maintenance/lock_dependencies.py --check
```

The first command keeps current pins where compatible. To select new versions:

```sh
python maintenance/lock_dependencies.py --upgrade
```

Review all profiles and the manifest together; then run the tests and
installed-wheel checks described in [development.md](development.md). Changing
the resolver version also requires updating `UV_VERSION` in the generator and
regenerating with that version. The script resolves all profiles before replacing
the committed outputs.

When lecture-tools adopts another texstage artifact, synchronize the assets with
`maintenance/sync_texstage_latex.py`, update the exact extras in pyproject.toml,
and update `requirements/texstage.json` from that verified wheel's METADATA
(base Requires-Dist entries, Requires-Python, version and artifact SHA-256).
Regenerate locks, then run `maintenance/check_pair.py` against the installed
companion. A same-version wheel rebuilt for CI may have different archive bytes;
the pair check compares version, API, dependency metadata and actual style bytes.
The asset lock continues to identify the original artifact that supplied the
vendored snapshot. Change that provenance only through explicit synchronization.

## Save a wheelhouse for offline work

On the target OS/Python version, before disconnecting:

```sh
python -m pip download --require-hashes --only-binary=:all: -r requirements/dev.txt -d wheelhouse
```

In a fresh environment on the same platform:

```sh
python -m pip install --no-index --find-links wheelhouse --require-hashes --only-binary=:all: -r requirements/dev.txt
```

Copy the verified project wheels alongside the wheelhouse and install them with
`--no-deps`. Download separate wheelhouses for other platforms. A Windows
wheelhouse does not contain Linux binary wheels.

Reference: [uv locking environments](https://docs.astral.sh/uv/pip/compile/)
and [universal resolution](https://docs.astral.sh/uv/concepts/resolution/).
