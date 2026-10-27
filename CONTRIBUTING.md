# Contributing

Start with the [development guide](docs/development.md), which documents the
locked environment, tests and distribution checks. Use synthetic decks and
disposable course copies for reproduction. Do not include private course
material, student responses, presenter keys or local server data in a change.

Keep changes focused. Explain the concrete problem, the resulting behavior and
the validation you ran in the pull request. Include an example for a new user
feature. Add regression coverage for behavior changes; update the relevant
public documentation and [changelog](CHANGELOG.md).

Preserve supported command arguments, output paths and formats. Coordinate
changes to the texstage API, bundle format or generated styles with the companion
project. Follow [the dependency workflow](docs/dependencies.md) for dependency
changes; never hand-edit lock hashes or vendored libraries/styles.

For rendering changes, compare a small synthetic deck before and after and
explain intentional differences. CI does not replace browser, Office or
real-course rehearsal. Course migrations are separate changes with explicit
approval and a recorded rollback pin.

Read [NOTICE](NOTICE) before copying or contributing material. This candidate
still has unresolved publication rights listed in [the release guide](docs/releasing.md).
The maintainer must settle the contribution license and publish a reporting
contact before opening public contributions; this file does not grant rights to
material excluded by NOTICE.

Report reproducible non-sensitive defects through the repository's Issues page
once hosted. Include OS, Python/package version, TeX version, command, expected
result and a minimal input. For sensitive reports, follow [SECURITY.md](SECURITY.md).
