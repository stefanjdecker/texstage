# Plugin-system review using transaction schedules

Reviewed 2026-11-05 against public host commit `d8ac4f4`, the matching private
host commit `4fbc1da`, and collection commit `bb9934f`. This is a design revision
and implementation backlog. Runtime code, manifests and existing course pins
have not been changed by this review itself.

Implementation follow-up: the H1 host work now supplies typed result transport,
revision-2 result/view schemas, a portable schema profile, epoch-guarded reset and
actor-scoped correlation helpers. Tests cover semantic phase/control/answer guards
using synthetic reducers. See [implemented contracts](../plugin-contracts.md).
The H2 follow-up implements [pre-TeX authoring and static exports](../plugin-authoring.md).
The findings below preserve the original review evidence; the transaction packages,
renderer/capacity work and published CI pins remain open.

The proposed activity and its implementation plan live in the separate
[plugin collection](https://github.com/stefanjdecker/texstage-plugins):
`docs/design/transaction-schedules.md` and
`docs/design/transaction-schedules-plan.md`. Those documents are local additions
until committed and pushed. The [main architecture](plugin-system-design.md)
incorporates the decisions below.

## 1. What this activity tests

The coordinate example proves that one submitted point can reach an independent
engine and return supplementary feedback. A transaction activity adds a phased
lesson, editable per-participant answers, several valid repairs, a shared trace,
structured graph evidence, multilingual explanations and a burst of submissions.
It also needs the same exercise to generate the live activity and a worked PDF.

The existing choices remain useful: independently installed providers, explicit
profiles, immutable resource hashes, code-free bundles, four renderer surfaces,
pure hooks, durable receipts/jobs, actor authentication and reset epochs.

At review time, typed result data and preparation before compilation were
missing. The H1 and H2 follow-ups now supply these contracts. The remaining
renderer, scheduling and capacity findings still gate the complete classroom
workflow; the historical evidence below records why each change was needed.

## 2. Findings and decisions

P0 means a prerequisite to implementing the promised transaction workflow.
P1 means required before a classroom pilot or stable API 1. These are design
priorities, not claims that all are exploitable security vulnerabilities.

| ID | Priority | Evidence in the current prototype | Revised decision |
| --- | --- | --- | --- |
| TS-01 | P0 | [builder](../../src/texstage/build/builder.py) compiles LaTeX before `plugin_build.prepare`; [PreparedItem](../../src/texstage/plugin_api/v1/__init__.py) has no static-artifact contract | Add an explicit generic authoring sidecar and optional pre-compilation hook; generate the worksheet, solution and prepared live data from one input |
| TS-02 | P0 | [evaluator](../../src/texstage/web/stage/plugin-evaluator.js) forwards only summary/key/matches; [Runtime.finish](../../src/texstage/plugins/runtime.py) rejects other successful fields | Add optional schema-validated engine `data`, carried unchanged to the owning type's completion event |
| TS-03 | P0 | The current result model centers on canonical equality and reference matches | Specify that equivalence/grouping is distinct from pedagogical validity; a type may accept many different analyzed repairs |
| TS-04 | P0 | [Runtime.command](../../src/texstage/plugins/runtime.py) checks a global item revision for exact operations, including reset | Keep transport ordering separate from semantic guards; clarify latest-state reducers, actor-local answer versions, control versions and epoch-guarded reset |
| TS-05 | P0 | [Surface.dispatch](../../src/texstage/web/shared/plugins.js) collapses refusals to a plain Error; `PluginBox.update` retains mounts when the descriptor disappears | Preserve structured receipts/errors, tear down revoked/missing descriptors, and define edit/focus preservation across updates |
| TS-06 | P1 | [Server.push](../../src/texstage/server/app.py) computes plugin views per connection; each [Runtime.view](../../src/texstage/plugins/runtime.py) sends the whole item state to a worker | Batch pure audience projections, coalesce publications and bound compact state; benchmark the actual classroom-sized case |
| TS-07 | P0/P1 | [PluginEvaluator.poll](../../src/texstage/web/stage/plugin-evaluator.js) requests at most two jobs and sleeps 750 ms after each batch; no per-actor fairness/rate admission is implemented | Drain ready work without that fixed inter-batch pause; provide bounded fair admission and honest pending/evaluator status |
| TS-08 | P1 | [Runtime.archive](../../src/texstage/plugins/runtime.py) exports private rows, not a portable lesson explanation; [record.js](../../src/texstage/web/stage/record.js) already captures the selected screen/window | Integrate private/static archive data and optional sanitized summaries; verify existing recording captures the overlay; defer a separate event-replay system |
| TS-09 | P0/P1 | [manifest schema](../../src/texstage/plugins/schemas/manifest-v1.json) is closed; worker summaries are only partially validated; the collection workflow defaults to host main | Version the extended manifest, validate complete schemas at every boundary, and pin a published compatible host for conformance |

## 3. TS-01: one authoring source, before TeX

Add a proposed `--activities lesson.activities.json` input to the build/PDF
pipeline. It explicitly lists type, item ID and a source JSON path under the
authoring root. Do not discover Python work by parsing arbitrary LaTeX or by
treating `\usepackage` as enablement.

An optional provider-owned authoring hook runs in the approved build worker
before any TeX compilation. It receives decoded data and bounded context and
returns:

- The normal prepared public/private item data and evaluation bindings.
- Static exercise and solution TeX fragments plus declared ordinary data/images.
- Bounded diagnostics, source digest and a preparation-format identity.

SDK shape implemented by the H2 follow-up:

```python
def prepare_source(source_data: dict, context: dict) -> PreparedAuthoring: ...

# New optional registry on PluginV1:
# authoring_hooks = {"schedule": prepare_source}
#
# PreparedAuthoring:
#   prepared: PreparedItem
#   fragments: {"exercise": str, "solutions": str}
#   format: 1
```

Context supplies item ID, qualified type, language, source identity and host
limits. A revision-2 content capability declares exactly one of `authoring_hook`
and the existing post-TeX `build_hook`; a prepared item is not processed twice.
Each TeX fragment is limited to 128 KiB and the complete JSON worker response
to the existing 8-MiB frame budget. Existing seed/data limits still apply.
The host computes the final preparation digest from provider identity, source
and declared resource bytes, prepared data and fragment hashes; it does not
trust an arbitrary digest supplied by the hook.

Core writes artifacts into a fresh owned build directory with collision-free
names; plugins cannot choose arbitrary output paths. TeX fragments are build
inputs from trusted enabled code, not new executable bundle asset types.
Plain text from exercise data must be TeX-escaped. Core confines dependencies,
rejects traversal/symlinks, enforces budgets, and verifies style provenance.

The generic record bridge binds an emitted live box to a prepared item and its
source digest. Missing, extra, conflicting or mismatched records fail the build.
All modes use that prepared record: present, stage, handout, solutions and static
PowerPoint. A materialized preparation export allows direct pdfLaTeX with the
approved styles; it is explicitly regenerated after source changes.

Keep the current post-compilation hook for simple plugins that already emit
their static fallback directly from LaTeX options. This avoids breaking the
coordinate fixture or making every plugin supply a new authoring hook.

Acceptance: changing one increment in the source JSON changes the live trace,
handout labels and worked solution consistently. A changed source with stale
prepared artifacts fails. No private solution appears in an ordinary handout,
public bundle asset route or static presenter-slide image.

## 4. TS-02 and TS-03: structured facts and multiple valid answers

An engine may declare `result_data_schema`, a package-local JSON Schema resource.
An `ok` result can then carry `data` satisfying that schema in addition to the
standard canonical string and summary. Without the declaration, `data` is
rejected. No arbitrary new summary kind or plugin-supplied HTML is necessary.

Validate the full result at the worker boundary, again before transmission, and
at the server against the job's installed engine/schema identity. The accepted
completion carries the typed data to its owning content-type reducer. Provider
payload, canonical format and the schema digest contribute to comparison/cache
identity. Remote schema references and executable values remain prohibited.
The complete delivered outcome keeps the 12-KiB limit; typed data gets an 8-KiB
sub-budget. Oversized data fails explicitly and is never silently truncated.

The transaction engine returns facts: normalized schedule, program validity,
final values, direct edges, witnesses and an acyclic certificate or cycle.
The activity's reducer evaluates its declared learning objective from these
facts. It must also verify that the result names the expected exercise and the
exact accepted answer, even though the presenter evaluator is trusted.

`matches` retains one meaning: canonical equality with an approved reference
evaluation. It is optional for custom-type bindings and is not a general
`correct` flag. The transaction binding uses no equality reference; all valid,
program-order-preserving acyclic repairs may succeed. Canonical keys may group
equivalent outputs, but must not collapse merely equal final database states
into a claim of schedule correctness.

Malformed execution, invalid domain answers and infrastructure failure remain
different outcomes. A parseable but invalid permutation can return an `ok`
analysis with `valid=false` and bounded reason codes. It is not a worker crash.
Failure diagnostics must remain bounded and cannot expose private seeds.

Acceptance: two different valid repairs both succeed; a cyclic schedule with
the same final values as a serial one does not pass the CSR objective. Unknown
data fields, mismatched schemas, stale exercise identity and oversized traces
are refused. SQL/SPARQL/Turtle and old summary-only plugins retain their behavior.

## 5. TS-04: revisions describe different things

Keep the existing host envelope and durable receipt ordering. Its revision
orders whole-item snapshots; its epoch identifies the reset generation.

Clarify `revision_policy=latest`: it runs a validated command against current
committed state and permits bounded replacements as well as additive changes.
It does not bypass authorization or domain preconditions. The plugin must check
any semantic compare-and-swap guard inside the same pure transition.

| Guard | Owner | Transaction activity use |
| --- | --- | --- |
| Epoch | core | Reject requests/results from an earlier reset |
| Whole-item revision | core | Order snapshots; exact-state operations where appropriate |
| Control version | plugin | Two presenters cannot unknowingly overwrite each other's phase/cursor intent |
| Phase token | plugin | A submission belongs to the open answer phase the student saw |
| Answer version per actor and phase | plugin | Reject conflicting replacements from two devices sharing one identity |
| Correlation and answer version | plugin plus core job identity | Old asynchronous feedback cannot replace the current answer |

Do not add transaction-specific phase fields to the core protocol. Stable refusal
codes include stale-phase, stale-answer and stale-control; presentation strings
are localized by the activity. A lost ACK repeats the unchanged request. A
terminal refusal is displayed; the renderer does not invent a new intent silently.

Revise reset semantics for the next experimental host revision: a reset is an
explicit presenter intent to replace the whole current epoch. Its guard is the
current epoch, not the rapidly changing item revision. Its accepted receipt,
epoch increment, state replacement and job invalidation are atomic. The existing
envelope's expected_revision remains syntactically valid but is not a reset
precondition. A different reset request from another presenter still targeting
the old epoch is refused; replay of an already accepted reset returns its receipt.
This change is implemented in the H1 follow-up, with lost-ACK and racing-reset tests.

A phase closure accepts or refuses a racing answer by server commit order.
Closure freezes accepted slots but does not discard their valid pending results.
Starting the next phase does not make those old-phase slots obsolete. Only an
explicit replacement, superseding phase instance, cancelled attempt or epoch
change makes a result obsolete. Keep this distinction in SDK examples.

Acceptance: hundreds of unrelated answers do not make phase/cursor operations
stale; same-actor replacement races do. Exercise close-vs-submit, reset-vs-result,
two-presenter resets, lost reset ACKs and late completion of an accepted closed
phase. Derive effect correlations from actor/request identity and an effect slot;
test two actors using the same request string.

## 6. TS-05: editable views and meaningful command outcomes

Continue using four independent surfaces and host-owned transport. Extend the
SDK's dispatch contract with a documented command outcome/error shape containing
the durable receipt, refusal code, accepted flag and known epoch/revision.
Distinguish terminal domain refusal from a transient transport/worker problem.
Do not reduce all failures to an unstructured string.

Revision-2 content capabilities also declare `view_schemas`, a mapping from
every declared surface to a package-local JSON Schema resource. Validate each
returned projection, including each batched projection, against its exact
surface schema before caching or transport. The transaction schemas use closed
objects and distinct presenter/projector/participant fields. This helps catch
accidental field sharing; it does not make malicious trusted renderers safe.
Revision-1 providers keep their existing behavior during migration.

The renderer owns its unsubmitted local edit. Ordinary `update` calls update
status and shared facts without replacing that edit or its focused control.
Only a matching acknowledged submission replaces saved-answer state. A newer
authoritative answer version from another device is a conflict to show, not a
reason to silently erase the local draft.

Define mount identity as session, bundle, provider payload, type, item, surface
and role. A missing/revoked descriptor or changed identity destroys old mounts,
listeners and controls. An epoch change clears obsolete drafts and feedback.
Repeated placement or an equal-revision redraw is harmless. A failed renderer
removes stale dynamic content and exposes a useful fallback, including on phones.
Controls must not remain live after deactivation.

Transient network reconnect preserves in-memory edits and retransmits pending
commands with their original IDs. Full-page-reload draft persistence is not a
mandatory first-release service; if implemented later it must be scoped to
identity/epoch with explicit saved versus unsaved status. Never auto-submit a
restored draft. This keeps a browser-storage subsystem out of the immediate API.

Acceptance: focus remains on a phone's operation selector during other students'
updates; returning after navigation restores the acknowledged answer; failures,
descriptor removal and resets cannot leave an old revealed graph visible.
Test the same renderer module mounted on two surfaces independently, keyboard
reordering, touch, zoom, reduced motion and de/en fallback.

## 7. TS-06 and TS-07: classroom-sized operation

The current whole-state worker call per recipient multiplies state serialization
by class size. A 200-student burst also competes with synchronous view work and
the fixed two-jobs-per-750-ms polling loop. Passing one-phone tests does not
establish acceptable classroom behavior.

Keep deterministic reducers and host persistence. Add these generic measures:

- Bounded queued worker calls outside the ASGI event loop; a slow view cannot
  block connections, core navigation or unrelated plugins.
- Coalesced publication and an optional `view_many(state, audiences, context)`
  hook, with a fallback that invokes `view` inside one worker call. The host
  chooses audiences and maps returned projections back to their recipients.
  Batch sizes and total bytes stay below IPC limits.
- Projection caching keyed by runtime/provider identity, item, epoch, revision
  and exact audience. Personal views are never shared across actors. Views are
  pure projections of supplied state/configuration/audience; changing wall-clock
  time is not an implicit input. Persist deadlines and animate with host time.
- Fair job admission and scheduling by session/item/actor, bounded per-actor
  submissions and outstanding work, and explicit overload receipts. Preserve
  valid lost-ACK replay even at the admission limit.
- Two bounded evaluator workers may continue draining available work immediately;
  only an empty queue or a transport failure triggers polling backoff.
  Cancellation/supersession releases logical queue capacity atomically.
- Role-filtered host status for pending work and evaluator availability. It is
  descriptive operational data, not a content-type verdict or a grading flag.

The transaction activity stays below existing byte limits by retaining compact
current answer slots and small certificates rather than every edit and trace.
The host does not acquire plugin-defined database tables or an arbitrary mutable
KV API. Partitioned participant storage can be reconsidered only if measured
budgets show that bounded state cannot support the intended class.

Proposed acceptance workload: 200 participants, a 200-submission burst over five
seconds, two presenter windows, a projector and a phone reconnect. On a documented
reference machine, target p95 acceptance under 750 ms, phase/navigation response
under 500 ms, and all bounded repair analyses completing within 15 seconds after
the burst with a healthy evaluator. These are targets, not measured results.
Record reducer/projection timings, IPC bytes, queue age, memory and worst cases;
revise targets or implementation based on evidence before a classroom pilot.

## 8. TS-08: export and recording boundaries

The current raw private JSON export is useful for diagnostics, but does not
complete the promised archive/replay contract. Define a versioned private archive
manifest with provider/format pins, exercise, final accepted answer versions,
outcome status and static exercise/solution representations. Refuse unnoticed
schema conversion when opening an archive with different providers.

Any public summary is a separate projection, stripped of identities, private
seeds, raw requests and unrevealed feedback. With no plugin installed, a reader
can still inspect the static material and documented JSON facts.

The current recorder already captures a selected screen/window plus microphone.
Rehearse capture of the projector with the plugin overlay and phase/cursor
changes visible. It needs no transaction-specific video API. A separate
event-replay system is not a prerequisite for this first activity. If introduced
later, it should replay authorized snapshots rather than re-submit commands or
re-evaluate student work. Do not record an unbounded stream of local draft edits.
Confirm video and archive behavior separately; a passing export test is not
proof that the chosen recording source includes the projector overlay.

## 9. TS-09: versioning and an executable compatibility gate

Use a proposed manifest revision 2 for the new optional authoring-hook,
result-data-schema and explicit per-surface view-schema declarations. Continue reading revision 1 for existing
plugins. Plugin API 1 remains experimental; this does not announce stable API 1
or create a new major merely to rename the proposal. Old hosts must reject
revision-2 providers before imports or build work, with a clear compatibility
diagnostic. Never quietly drop new fields to make a package appear compatible.

The extended schema resources are included in provider inventories and portable
digests. Validate the standard summary schemas too; the current kind/size check
alone is not the full result contract. Preserve legacy bundle formats and
summary-only providers. A changed host/runtime fingerprint continues to require
a fresh session or the old environment for rollback.

The collection's conformance workflow must select a published, exact compatible
host commit for push/PR runs. Manual overrides may select an experimental ref,
but reports record its resolved commit and built wheel digest. The current
default of main is not a compatibility pin and can select a host without the SDK.
Publish feature branches and test their pair before counting a successful CI
run as evidence. No release or catalog entry is created by this design revision.

## 10. Revised sequence and completion evidence

| Work package | Scope | Completion evidence |
| --- | --- | --- |
| H0 | Preserve current wheel fixtures and legacy regression baseline; fix CI host selection | Published compatible host/collection pair, explicit artifact identities |
| H1 | TS-02/03/04 contracts, manifest revision and typed result schemas | Contract tests including distinct valid answers, scoped races, forged/malformed results and old plugins |
| H2 (implemented locally) | TS-01 authoring prepass and static export | One source change updates live data, exercise and worked solution; real builds and installed-worker checks pass; stale source/artifact and privacy checks covered |
| H3 | TS-05/06/07 renderer, dispatch and capacity work | Real-browser edit/reconnect tests and measured 200-participant run |
| P1 | Transaction engine and authoring analyzer | Independent expected fixtures, all small interleavings, Python/JS parity, installed wheel |
| P2 | Transaction content type and four views | Full predict/inspect/diagnose/repair/reveal lesson through the public interfaces |
| H4/P3 | TS-08 archives/recording and final conformance | Private/public projections, static fallback, actual projector capture and two-way platform matrix |
| Later | Built-in registry consolidation and supported release | Existing SQL restrictions/aliases, quiz/video and course facade checks still pass |

Do the schema and authoring work before coding the final lesson interface.
Keep stage 3's broad built-in migration behind this extended prototype gate.
Lecture-tools gets optional argument forwarding only after the host input/API
exists. Course adoption uses disposable copies and is a separate change; all
current courses and their pinned toolchains stay unchanged.
