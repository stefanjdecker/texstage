# Preparing and releasing a candidate

## Public source and package status

The source is public at [stefanjdecker/texstage](https://github.com/stefanjdecker/texstage),
with project information at [www.texstage.org](https://www.texstage.org).
The `main` branch includes the PowerPoint conversion, shared compilation and
German-language compatibility changes. The current version remains the
0.2.1.dev3 development candidate; source publication is distinct from declaring
a supported package release. Follow [installation.md](installation.md) to install
the checkout with its matching dependency locks.

The package CI workflows build and test candidates. They do not upload releases
to GitHub Releases, PyPI or a container registry. The `Private :: Do Not Upload`
classifier remains set for this development candidate. Separately, the public
repository's Pages workflow publishes the homepage and manual PDF on relevant
pushes to `main`.

Maintain one code checkout and publish the same reviewed commits to GitHub and
the GitLab code mirror. Keep private demonstration recordings, scripts,
transcripts, captions and the narrated production showcase in the separate
`texstage-media` repository. Follow [repository-layout.md](repository-layout.md)
for remotes, synchronization and the transition from the old private history.
Do not merge or fetch private media history into the code repository.

Before publishing code to either host, run:

```sh
python maintenance/check_public_content.py --rev HEAD
```

The pre-push hook also checks each proposed tip and its ancestry. This check
covers the known private recording paths and narration; it is not a general
audit of all sensitive content.

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
5. Confirm the browser/Office/OS matrix with actual runs and record successful
   package and paired-integration CI results. A skipped integration job is not
   release evidence.

## GitHub setup

Package CI uses `push`, `pull_request` and manual triggers, read-only contents
permissions, immutable action commit pins, and no package-publishing credentials.
The separate Pages deployment job requests Pages and OIDC permissions.
Dependabot proposes action updates monthly. Dependency upgrades are explicit lock refreshes so the
three lock profiles stay consistent.

Lecture-tools has an independent base workflow and a separate paired workflow.
Set repository variables `TEXSTAGE_REPOSITORY` (`owner/name`) and `TEXSTAGE_REF`
(full 40-character commit SHA) to the public companion revision being tested.
The paired workflow then runs on pushes and pull requests. Manual runs can supply
both values instead. Both repositories must be accessible to checkout using the
standard read-only token; private cross-repository credentials are not configured.
If both variables are absent, the summary explicitly reports that integration
has **not run**. One missing or malformed value fails configuration. An unconfigured
or skipped integration check is not release evidence.

Run the workflows on the hosting service and set appropriate required checks on the
default branch, including the paired `integration` job. Do not treat a local
Windows run as proof of a successful Linux or hosted Actions run.

## Candidate validation

In a clean checkout, follow [development.md](development.md). Verify the locked
environment, complete the applicable suites, and run:

```sh
python maintenance/check_docs.py
python maintenance/lock_dependencies.py --check
python maintenance/check_distributions.py --out dist/candidate
```

Use a new empty output directory. This produces a wheel, source archive,
SHA256SUMS and validation.json. It also builds a wheel from the source archive
and compares every uncompressed wheel member with the direct build. ZIP/tar
timestamps may differ; artifact SHA-256 hashes identify the actual archives.
Run the installed-wheel smoke check from the development guide and keep the
test reports with the candidate. Review the archive contents, including notices,
web assets, styles, skills and documentation as applicable.

For a release changing the texstage pair, install the candidate texstage wheel,
run lecture-tools' metadata/API/style check and full synthetic regression suite,
and record the exact Git revisions and wheel hashes. Refresh the generated
LaTeX snapshot only from a verified wheel. Do not silently retarget old courses.

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
