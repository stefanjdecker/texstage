# Refactoring history

Current release infrastructure is documented in [development.md](development.md),
[dependencies.md](dependencies.md) and [releasing.md](releasing.md). CI workflows,
hashed locks, synthetic examples and public guides are now present. Hosted CI
runs and publication decisions are still pending.

## First refactoring increment (historical record)

Implemented on 27 October 2026, from combined lecture-tools commit
`6388b6ba48d8c4f770c81cc66c992a3d5c9cde26`. The source snapshot and per-file
attribution are recorded in `provenance/`. Local history starts with an extraction
commit; the choice of history for publication is still open.

This file records the first increment. The subsequent lecture-tools 0.1.0.dev1
increment completes Python command relocation and extracts the reusable style
modules; see the companion repository's docs/package-and-style-modules.md and
docs/validation-phase2.json. The texstage runtime/API is unchanged.

The full release and real-course migration plan remains incomplete.

| Plan step | Result |
|---|---|
| M0: extraction and baselines | Separate local repositories and original file provenance; recorded source/course pins; synthetic compatibility tests. Full real-course before/after baselines remain pending. |
| M1: texstage boundary | Standalone runtime, server, web assets and four generic styles; supported lazy `texstage.api`; separate tests and distribution metadata. |
| M2: lecture-tools package | Installable package, deterministic course discovery, configuration, resource discovery and additive CLI. Legacy implementations remain under `scripts/`; relocation into build/check/edit modules remains pending. |
| M3: generic TeX assets | Four styles and notices synchronized from a hashed texstage wheel; committed lock and forwarding loaders; runtime mismatch checks before a live build. |
| M4: style decomposition | Pending. The existing DBIS style remains intact to preserve behavior while core/theme/subject boundaries are extracted next. |
| M5: release infrastructure | Local packaging checks and initial documentation. CI, full dependency locks, public examples and complete release documentation remain pending. |
| M6: course migration | No actual course has been migrated. Real-course rehearsal and explicit pin changes come later. |
| M7: publication | No GitHub remote, public repository or package-index release created. Licensing of material excluded by the original NOTICE remains unresolved. |

## Compatibility and boundaries

- Course wrappers use `texstage.api`, never a sibling runtime source path.
- The legacy `lecture.py` shim selects its owning course before CWD ancestors;
  explicit `LECTURE_ROOT` takes precedence. The CLI additionally accepts `--root`.
- Existing course IDs, file paths and `build/texquiz` output naming remain.
- DBIS settings and macros remain unchanged. English/tight and German/classic
  synthetic courses compile; no new Python or TEXINPUTS requirement for plain TeX.
- Shared skills remain usable without slide/server dependencies.
- Generic styles have one canonical owner in texstage. Their copies are generated,
  hash checked and accompanied by LICENSE/NOTICE.
- Developer/migration utilities are retained as source, not promoted to installed
  commands. Historical tools remain unsupported.
- Both packages use development versions and `Private :: Do Not Upload` while
  release decisions are pending. This classifier does not prevent GitHub publishing.

## Validation scope

The source suites exercise generic rendering, quiz bundles, server behavior,
JavaScript, PowerPoint exports, note extraction, course commands and skills.
Windows registry tests use a temporary test key. Synthetic course tests cover
legacy LaTeX loading, language/box settings, label resolution, configuration,
deck IDs, notes and rejection of a mismatched texstage pair.

Wheel/source-archive build and isolated installed-package checks are recorded in
`validation-results.json`. Testing here used Windows and Python 3.14 with local
TeX Live and Node.js. Linux/macOS, a Docker image build, interactive PowerPoint,
and real-course rendering comparisons are not yet validated.

## Next step recorded at the first increment

Move command implementations into the package while leaving tested thin wrappers,
then extract the DBIS style into core, theme and subject modules without changing
macro semantics. Add CI and a locked wheelhouse. Rehearse each course against its
own original tools pin in disposable copies before proposing any real-course change.
