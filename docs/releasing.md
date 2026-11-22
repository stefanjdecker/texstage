# Preparing and releasing a candidate

## Public source and package status

The source is public at [stefanjdecker/texstage](https://github.com/stefanjdecker/texstage),
with project information at [www.texstage.org](https://www.texstage.org).
The `main` branch includes the PowerPoint conversion, shared compilation and
German-language compatibility changes. The current version is
1.0.0, the current stable release, tagged v1.0 and published as source; a
packaged release - wheels on PyPI, a container image - is still to come
(below). Follow [installation.md](installation.md) to install the checkout
with its matching dependency locks.

The package CI workflows build and test candidates. They do not upload releases
to GitHub Releases, PyPI or a container registry. The `Private :: Do Not Upload`
classifier remains set: this release is published as source only. Separately,
the public repository's Pages workflow publishes the homepage and manual PDF on
relevant pushes to `main`.

The public and private repositories have separate histories. Keep private
demonstration recordings, scripts, transcripts and captions in the private
repository. Apply shared changes to each checkout separately; never merge the
private history into the public repository. In the public checkout, before a
public push, run:

```sh
python maintenance/check_public_content.py --rev HEAD
```

The public pre-push hook also checks each proposed tip and its ancestry. This
check covers the known private recording paths and narration; it is not a
general audit of all sensitive content.

## Remaining packaged-release work

1. Confirm maintainers, project metadata and a monitored private reporting route
   in SECURITY.md. Identify which versions will receive support.
2. Resolve the scope in NOTICE with the rights holders. In Texstage,
   `tools/simulate.py` and `tools/slideshow.ps1` remain outside that scope even
   though they are excluded from distributions. Public availability is not a
   blanket license for excluded utilities or companion course material.
3. Review every proposed release ref and artifact for attribution, redistribution
   rights, private data and credentials. Preserve the filtered public history.
4. Choose release numbers and whether packages will be distributed through
   GitHub Releases, PyPI or both. Check package-name availability before using a
   package index. Update package and runtime versions together, refresh locks
   and coordinate the companion pin.
5. Confirm the browser/Office/OS matrix with actual runs and record the release
   commit's successful CI runs.

## GitHub setup

Package CI uses `push`, `pull_request` and manual triggers, read-only contents
permissions, immutable action commit pins, and no package-publishing credentials.
The separate Pages deployment job requests Pages and OIDC permissions.
Dependabot proposes action updates monthly. Dependency upgrades are explicit lock refreshes so the
four lock profiles (runtime, build, dev and docs) stay consistent.

Set required checks on the default branch: the CI workflow's four test jobs and
its container job. Do not treat a local Windows run as proof of a successful
Linux or hosted Actions run. lecture-tools tests its pairing with texstage in
workflows of its own, described in lecture-tools-next's `docs/releasing.md`
(that repository is not public).

## Candidate validation

In a clean checkout, follow [development.md](development.md). Verify the locked
environment, complete the applicable suites, and run:

```sh
python maintenance/check_docs.py
python maintenance/lock_dependencies.py --check
python maintenance/check_distributions.py --out dist/candidate
```

Use a new empty output directory. This produces a wheel and a source archive of
texstage and of each kind of live activities in `kinds/`, SHA256SUMS and
validation.json. It also builds each wheel again from its source archive and
compares every uncompressed wheel member with the direct build. ZIP/tar
timestamps may differ; artifact SHA-256 hashes identify the actual archives.
Run the installed-wheel smoke check from the development guide and keep the
test reports with the candidate. Review the archive contents, including notices,
web assets, styles and documentation as applicable.

A new version changes `pyproject.toml` and `src/texstage/__init__.py` (a test
compares both with the installed metadata) and the files that name the current
version: README.md, the newest heading of CHANGELOG.md, site/index.html,
docs/manual-content.json (then regenerate the manual), this file,
compilation.md, powerpoint.md, installation-advanced.md, development.md and
examples/showcase/COVERAGE.md. `maintenance/check_docs.py` fails while one of
them names another version.

A candidate reaches courses only through lecture-tools, which pairs with its
verified wheel and runs its own checks (lecture-tools-next's
`docs/dependencies.md`, "Pair with another texstage"); a texstage release
changes no course's pin by itself.

## Release and rollback

After publication rights, destinations, versions and platform checks are settled,
remove the private classifier as a reviewed release change. Tag the tested
commits, attach the verified artifacts, checksums and release notes to the chosen
release destination, and retain the tested pair together. Publication itself is
a separate authorized action; no release upload workflow is installed here.

Keep previous wheels and locks available. Roll back a deployment by restoring
the prior environment and backed-up data, not by changing the meaning of an
existing tag. Rehearse course adoption separately in disposable copies and
record each course's original tools commit, environment and output baseline.
Course adoption is a separate, validated migration. Documentation updates do not
require changing any existing course's pin, installed tools or generated files.
