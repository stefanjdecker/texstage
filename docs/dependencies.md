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
| `docs.txt` | Legacy documentation extras retained for compatibility; the LaTeX PDF build does not need them |
| `*.in` | Generated direct inputs; edit pyproject.toml (texstage's, or a kind's in `kinds/`) rather than these files |
| `lock-manifest.json` | Hashes of dependency metadata (the kinds' too), generator, inputs and lock outputs |

`runtime.txt` is texstage's full runtime dependency set. Vendored JavaScript
and LaTeX are committed resources, not packages downloaded by these lockfiles.
It also holds what the kinds of live activities beside texstage need
(`kinds/*/pyproject.toml`, their dependencies but texstage and the kinds' own
packages, which are on no index): they are packages of their own, installed after
texstage with `--no-deps` as a local package has no hash to lock, so their
dependencies are locked with texstage's. The manifest has their metadata's
hashes: any edit of a kind's `pyproject.toml` - a new dependency, a new version -
fails `--check` until the locks are regenerated, which needs uv and the network.
Where lecture-tools pairs with texstage, the kinds come from the same texstage
source as its wheel, unpinned by hash: their dependencies must be among
texstage's own, which `pip check` holds in the course's environment.

## Install and verify

Create and activate a new Python environment, then run from the repository root:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/dev.txt
python maintenance/lock_dependencies.py --check
python -m pip install --no-deps --no-build-isolation -e .
python -m pip install --no-deps --no-build-isolation -e kinds/texstage-kinds-sql -e kinds/texstage-kinds-rdf
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

lecture-tools pins texstage by its wheel and vendors its LaTeX styles: pairing it
with another texstage build is lecture-tools-next's own work, described in that
repository's `docs/dependencies.md` ("Pair with another texstage"); the
repository is not public.

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
