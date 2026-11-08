# Optional Typst backend: implementation plan

Status: planned, not implemented.
Date: 2026-11-08.
Contract: [backend design](typst-backend-design.md).

Implement this as small changes in the existing host and plugin collection.
Start from reviewed branches containing the pending database-example/language
work, or preserve that work in separate commits before branching. Suggested
implementation branches are `codex/typst-prototype` in both repositories.
Do not discard pending edits to obtain a clean tree.

The prototype is complete only at the end of P4. P1's compiler experiment and
P3's built-in activities are useful milestones, not the delivered prototype.

## Sequence and review boundaries

| Milestone | Depends on | Deliverable | Review boundary |
| --- | --- | --- | --- |
| P0 | None | Compatibility baseline, executable fixture specification and toolchain choice | Tests/fixtures and evidence only |
| P1 | P0 | Geometry, metadata, notes and reveal experiment | New experimental files; no replacement of the LaTeX build |
| P2 | P1 | Shared internal build/export seam with LaTeX compatibility | Host refactor, separately reviewable |
| P3 | P2 | Typst build with ordinary slides, quiz and SQL | Host backend and synthetic examples |
| P4 | P3 | Native B+ renderer and complete four-slide prototype | Generic host contract first, provider adaptation second |
| P5 | P4 | Stable installation, exports, diagnostics, cache and CI | Optional-backend release hardening |
| P6 | P5 | Remaining activity authoring and verified feature matrix | One provider/content family per change |
| P7 | Relevant gates | Experimental release, then any wider support claim | Immutable artifacts and documentation |

No stage modifies an original repository or existing course. Capacity expansion,
course migration and video production are separate tasks.

## P0 — Establish the baseline

1. Record host and collection commit IDs, pending prerequisite commits, Python
   environment, installed provider wheels/payload hashes and current locks.
   Keep this evidence separate from any eventual published compatibility pins.
2. Build the existing synthetic LaTeX demo and prepared B+ example in an owned
   output directory. Preserve a semantic baseline of deck/keys data, page and
   note maps, quiz mappings, generated leaderboard placement and PDF geometry.
3. Run the existing focused suites covering builds, LaTeX, stage notes, public
   APIs, plain Beamer conversion, prepared plugins and bundle privacy. Record
   real TeX availability: a skipped compile is not compatibility evidence.
4. Define the four-slide fixture, including the exact B+ insertion source,
   expected quiz answers, SQL references/alternatives, language variants and
   notes. Store expected semantics separately from generated metadata so the
   test does not merely repeat the implementation.
5. Select a pinned Typst binary and licensed fonts for the experiment. Record
   download origin, checksum, version and OS. Do not install it into an
   existing course environment.

Suggested files in the host:

- `tests/fixtures/typst/expected-prototype.json`
- `tests/fixtures/build-compatibility/`
- `maintenance/typst-toolchain.lock.json`
- `docs/architecture/typst-prototype-validation.md` (created with actual evidence,
  not prefilled as passing)

**Exit gate:** a reproducible LaTeX baseline and an explicit prototype
specification. Do not declare byte-identical PDFs mandatory when timestamps
differ; compare normalized semantics and rendered pages with a documented
tolerance. Existing public API behavior must remain exact.

## P1 — Prove the geometry and page mapping

Add an experimental `maintenance/typst_probe.py` and a small Typst fixture.
The probe compiles and queries; it does not export a classroom bundle yet.
Use inert placeholders for the later quiz/SQL/B+ interactions while testing
their intended seven-page sequence and region positions.

Proposed host paths:

| File | Work |
| --- | --- |
| `src/texstage/build/typst_backend/compiler.py` | Executable discovery, argument construction, bounded subprocess execution, version check and diagnostics |
| `src/texstage/build/typst_backend/metadata.py` | Strict versioned JSON validation and conversion of numeric page/region records |
| `src/texstage/typst/texstage.typ` | Deck/slide/region primitives and namespaced metadata |
| `src/texstage/typst/notes.typ` | Stage note pages with explicit slide associations |
| `tests/fixtures/typst/geometry.typ` | Known-corner rectangles, two columns, nested margins, reveal and notes |
| `tests/test_typst_metadata.py` | Invalid records, size limits, page mismatches and geometry invariants |
| `tests/test_typst_compiler.py` | Missing compiler, failed query, timeout, path handling and no partial output promotion |

Required experiments:

- Compare queried anchors/dimensions with independent rendered fiducials.
  Check the 1-point/2-pixel tolerances from the design.
- Prove seven present pages can be mapped from four logical slides, and that
  notes and phone pages are never counted as slides.
- Demonstrate the same metadata under repeated compile/query operations over
  the frozen snapshot; deliberately change an input and reject stale results.
- Reject a split, rotated, out-of-page or duplicate interactive region.
- Build in paths containing spaces and non-ASCII characters.
- Run without LaTeX and without network access once dependencies are staged.

**Exit gate:** measured geometry and deterministic page/note identity on the
chosen toolchain. If this fails, revise the module/metadata design before
touching the classroom pipeline. Do not compensate in the browser with
per-slide coordinate offsets.

## P2 — Extract the shared build seam

Create `src/texstage/build/document.py` for the internal compiled-deck types
and `src/texstage/build/assemble.py` for common bundle/PPTX assembly.

| Existing host files | Change |
| --- | --- |
| `build/builder.py` | Retain `build`, `BuildOptions` and `BuildResult`; delegate compilation and common assembly |
| `build/tqz.py`, new `build/latex_backend.py` | Keep TeX parsing intact; convert its result into the internal model |
| `build/quiz.py`, `activity.py`, `plugins.py`, `video.py` | Separate record decoding from semantic preparation/export; keep compatibility wrappers |
| `build/raster.py` | Add explicit single-page/region rendering for other backends; preserve double-width LaTeX validation |
| `build/stage.py` | Accept explicit validated page mappings while retaining the log/.nav adapter |
| `build/bundle.py`, `powerpoint.py` | Reuse format/security/export behavior; change only interfaces needed by the shared model |

Keep source compilation, log checking and `.nav` interpretation in the LaTeX
adapter. Do not move `beamer.py` or change `compile_latex` to support Typst;
those are specific compatibility APIs.

**Exit gate:** the P0 LaTeX baseline and existing relevant tests pass before
any Typst activity is connected. Compare phone assets, rectangle rounding,
notes, quiz phase/choice mappings, private data and provider pins. Review the
refactor separately from feature additions so regressions are attributable.

## P3 — Build the three host-owned prototype slides

Add the Typst adapter and authoring primitives for ordinary slides, single-choice
quizzes and the existing SQL activity. Keep SQL validation and execution in the
existing engine; this milestone only supplies equivalent source metadata.

Proposed paths and responsibilities:

| Host file | Work |
| --- | --- |
| `build/typst_backend/backend.py` | Snapshot, compile modes, metadata/PDF reconciliation and `CompiledDeck` production |
| `src/texstage/typst/quiz.typ` | Read/question/reveal pages, choice-region marks and phone image mode |
| `src/texstage/typst/activity.typ` | SQL prompt, editor region, confined seed and reference declarations |
| `src/texstage/typst/prepared.typ` | Prepared-use placement/digest contract; renderer integration lands in P4 |
| `src/texstage/cli.py` | Explicit `.typ` dispatch, proposed backend selector and Typst failure handling |
| `src/texstage/api.py` | Preserve existing APIs; add only additive resource access if needed |
| `pyproject.toml`, `MANIFEST.in` | Include all new modules/schemas in installed wheel and sdist |
| `examples/typst-demo/` | Three-slide host example using built-ins only |
| `tests/test_typst_build.py`, `test_typst_present.py` | Real output, dispatch, freshness and stale-build refusal |

P3 implements build, PDF handout/solutions and presentation sufficiently for the
prototype. `present lesson.typ` always rebuilds initially. Do not claim support
for direct-compiler preparation export or other quiz types yet; unsupported
features produce actionable errors.

Verify:

- Current bundle validators load the output with no server changes.
- Phone prompt/choice pictures and public IDs agree with the projected quiz.
- Correct and wrong quiz answers produce existing grades.
- SQL seed/reference handling matches LaTeX; equivalent correct queries work,
  invalid queries report errors, and DROP/other writes stay rejected.
- Notes appear only in the presenter; projector/phone resize and step
  navigation work; handout and solution modes select the intended content.
- Bundle ZIP and PPTX open structurally; presenter keys are handled exactly as
  in existing lecturer exports and never included in public test artifacts.

**Exit gate:** a complete three-slide built-in example without TeX. This is
still missing the B+ part of the promised prototype.

## P4 — Complete the prototype with B+ trees

Land the generic host extension before the provider change.

### Host contract work

| File area | Work |
| --- | --- |
| `plugin_api/v1/__init__.py` | Add preparation/render registrations and typed render result; preserve legacy constructors |
| `plugins/schemas/manifest-v6.json` | New mutually exclusive preparation/rendering declaration and pinned Typst resources; recheck revision allocation first |
| `plugins/manifest.py`, `catalog.py`, `worker.py` | Validate target support, resource ownership and method dispatch/budgets |
| `build/authoring.py` | Shared preparation plus target/edition rendering; keep old format-1 path and identities |
| New `build/authoring_typst.py` | Owned materialization of Typst registry, public/solution projections and freshness metadata |
| `plugins/sdk.py` and packaging/checking code | Inventory Typst resources, validate new manifest and build portable artifacts |
| `tests/test_plugin_authoring.py`, new `tests/test_plugin_rendering.py` | Legacy/new compatibility, identity changes, private/public separation and missing-target errors |

Use a synthetic provider fixture for host tests. The core must not import B+
rules to make the test pass. Test that exercise rendering cannot receive
private answers and that a renderer failure prevents publication.

### Collection work

| B+ provider file | Work |
| --- | --- |
| `texstage_bplus_lab/authoring.py` | Extract shared validation/preparation; render from the already checked answer |
| New `texstage_bplus_lab/render_latex.py` | Preserve current LaTeX fragment semantics and styles |
| New `texstage_bplus_lab/render_typst.py` | Native exercise and worked-solution fragments using safe data encoding |
| `texstage_bplus_lab/layout.py` | Reuse `geometry`; preserve the existing TikZ output contract |
| Optional `texstage_bplus_lab/typst/bplus.typ` | Packaged drawing helpers if the renderer needs them |
| `texstage-plugin.json`, `pyproject.toml`, `MANIFEST.in` | Opt into the new contract, bump the provider version and declare resource inventory |
| `plugins/bplus-lab/tests/` | Same prepared data/grades across targets, all operation layouts, locale and privacy cases |

Keep model, reducer, evaluator, submissions and scoring behavior unchanged.
Verify unchanged behavior rather than treating untouched filenames as proof.

Create `examples/typst-database/` in the collection for the full four-slide
lesson, its English/German masters, activity sidecar, checked B+ source and
reproduction instructions. The host's three-slide example must remain usable
without any optional provider.

Build host/provider wheel and sdist, install them into a fresh matching
environment, explicitly enable the new provider pin and generate a new test
lock. Old course profiles continue to use their current wheels.

**Prototype acceptance:**

- Four logical slides, seven present pages, correctly associated notes and
  separate phone assets; all promised exports generated and inspected.
- Real B+ submission, full/partial/zero credit, feedback, score publication and
  reset; score follows the existing rubric in both authoring targets.
- Late evaluator results do not repopulate a reset activity.
- B+ private reference/solution sentinels are absent from prereveal phone and
  projector payloads, public assets and caches.
- English and German in Chromium, Firefox and WebKit, including browser locale
  opposite to deck language; keyboard and touch-style input at 390 px width.
- Existing production CSP and worker restrictions; no compatibility-only
  relaxed security policy.
- Native Typst build succeeds with TeX executables unavailable.
- P0 LaTeX compatibility remains passing.

Record measured versions, wheel/payload hashes, outputs, failures and screenshots
in a dated validation report. A real phone and classroom network check remains
a separately identified manual gate until it is performed.

## P5 — Make the optional backend maintainable

Finish the features required for an experimental release:

- Complete Typst input/dependency fingerprints and cache invalidation. Change
  imported slides, SQL, JSON, fonts, compiler/options and provider pins in tests.
  Keep existing LaTeX freshness behavior and `needs_build` API intact.
- Add direct Typst preparation exports only with stale-input detection
  equivalent in purpose to the direct-pdfLaTeX bridge; until then reject that
  mode explicitly.
- Make diagnostics identify backend, source/item, failed mode and compiler
  error. Test missing compiler/resources, malformed metadata, invalid providers,
  timeout, overflow and locked output files.
- Finish handout/solutions policies, Unicode, text/math/code, long notes and
  page-map validation. Reject unsupported overflowing interactive content
  instead of quietly clipping it.
- Check all B+ operation families in both languages and modes.
- Decide whether to add a pinned Touying adapter. Keep the neutral model and
  region contract fixed; adopting Touying must not become a browser dependency.
- Document the source module, install requirements, editor materialization,
  offline builds, feature gaps and artifact privacy. Update the Markdown/LaTeX/
  PDF manuals together when the feature is actually available.
- Run a shared-runtime smoke test for recording and device coupling with the
  Typst bundle; no new recording or coupling implementation is planned.

Add a dedicated host CI job, for example
`.github/workflows/typst.yml`, and corresponding GitLab coverage when that
mirror's pipeline runs tests. Keep LaTeX CI mandatory. Exercise Windows and
Linux builds with installed artifacts; explicitly report other platforms as
untested until covered. A normal installation/test path must pass without
Typst present.

The collection CI consumes the matching host artifact and exact provider
wheel, not an editable source import. Include missing-target/older-host
rejection tests. Reproducible jobs stage dependencies then block network access.

Benchmark small (prototype), medium (50 slides) and larger (200 slides)
synthetic decks against semantically equivalent LaTeX decks. Report median
cold and repeated build times and peak memory, separating preparation,
compilation, metadata query, rasterization and PPTX assembly. At least five
runs per scenario; do not change course files to obtain measurements.

**Exit gate:** repeatable installed-package CI, documented limitations and
measured performance. Faster full builds are a possible benefit, not a release
criterion or a promised result.

## P6 — Extend coverage deliberately

Maintain a support matrix with columns for live source authoring, handout,
solutions, notes/reveals, English/German and browser verification.

| Family | Next work |
| --- | --- |
| Remaining built-in quizzes | Implement the other types until all nine pass; cover shuffle, partial credit, ordering, text/numeric rules, free-form answers, sketch and leaderboard/podium behavior |
| SPARQL, Turtle and shared graphs | Equivalent typed declarations and static rendering using existing engines and restrictions |
| Transactions | Render schedules, prediction tasks, checked traces and worked explanations from existing lesson data |
| Relational algebra | Render relations/query trees and intermediate results without duplicating evaluator rules |
| Functional dependencies and normalization | Render relation schemas, closures, decompositions and proof/counterexample material |
| ER decisions and query plans | Render the existing modelling/cost exercises and worked feedback |
| Coordinates | Provide a target-aware path for this legacy post-TeX content provider; preserve its separate distance engine |
| Video and other special slides | Validate authoring, poster/media paths and existing export behavior |

Engine-only distributions do not need a static renderer. Each content provider
opts in independently, with its own version, resource hashes and installed-wheel
evidence. Unsupported content must fail clearly in Typst while continuing to
work in LaTeX.

Do not use the successful four-slide prototype to mark this matrix complete.
A later all-activities Typst deck can mirror the synthetic database example
after the corresponding providers pass.

## P7 — Release and rollback

1. Rebase and validate the reviewed host change; release a compatible host
   artifact before providers that require its new manifest contract.
2. Publish only immutable, reviewed provider artifacts with the matching host
   requirement, wheel/payload hashes and updated catalog entries.
3. Mark the backend experimental with an explicit support matrix. Publish
   documentation that distinguishes available commands from future work.
4. Test installing the old provider with the new host and refusing the new
   provider with an old host. Keep old artifacts/locks valid.
5. Verify the GitHub/GitLab host mirrors contain the same code. Keep all private
   video/narration material in the separate private media repository.

Rollback consists of disabling Typst dispatch for new source builds and keeping
the existing LaTeX/runtime paths available. Previously generated valid bundles
remain usable with their required provider pins. No rollback step rewrites
course sources or automatically downgrades installed profiles.

## What to do first

Implement P0 and P1: pin a disposable toolchain, record the LaTeX baseline, and
produce the geometry/metadata/notes probe. Its report should answer whether the
same physical boxes and slide identities can reliably reach the existing
runtime. That evidence authorizes the technical choice of adapter, not a
course migration or publication.
