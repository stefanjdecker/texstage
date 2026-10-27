# Preparing and releasing a candidate

The workflows build and test candidates; they do not publish to GitHub Releases,
PyPI or a container registry. The current development version and
`Private :: Do Not Upload` classifier remain deliberate. That classifier does
not prevent someone from publishing the Git repository.

## Publication decisions still required

1. Select the GitHub owner, repository names and maintainers. Set the project
   URLs and a monitored private reporting route in SECURITY.md.
2. Resolve the scope in NOTICE with the rights holders. Lecture-tools code,
   styles, skills and utilities excluded by the original notice need an explicit
   disposition. In texstage, `tools/simulate.py` and `tools/slideshow.ps1` remain
   outside that scope even though they are excluded from distributions. Do not
   infer a blanket license from LICENSE or LICENSE.texstage.
3. Decide whether to publish attributed snapshot history or filtered history.
   Review every ref intended for publication, including historical utilities,
   private paths, credentials, course content and redistribution rights. Existing
   provenance records are attribution evidence, not permission to publish.
4. Select release numbers, check repository/package-name availability, and decide
   whether the release is GitHub-only or also goes to PyPI. Update the package and
   runtime versions together, refresh locks and coordinate the companion pin.
5. Confirm the supported browser/Office/OS matrix with actual runs. Enable the
   paired integration job for lecture-tools and require its successful result.

## GitHub setup

CI uses `push`, `pull_request` and manual triggers, read-only contents permissions,
immutable action commit pins, and no deployment credentials. Dependabot proposes
action updates monthly. Dependency upgrades are explicit lock refreshes so the
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

After hosting, run the workflows and set appropriate required checks on the
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
The refactoring has not changed any existing course's pin or environment.
