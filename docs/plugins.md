# Experimental plugins

Optional [activity points](plugin-points.md) connect manifest-4 providers to
the normal game total, leaderboard and CSV export.

Manifest revision 3 optionally adds [bounded actor records](plugin-actor-records.md)
for larger classes. Revisions 1 and 2 retain their existing contracts.

This branch implements an experimental plugin host and two independently packaged
examples in the separate `texstage-plugins` repository. It is a prototype of the
[API 1 design](architecture/plugin-system-design.md), not a stable API 1 release.
Existing decks, SQL, SPARQL, Turtle, quizzes and videos need no plugin setup.

The first transaction-plugin host milestone is implemented: revision-2 manifests,
typed engine facts, surface schemas and epoch-guarded reset. See
[engine results and view schemas](plugin-contracts.md) for the supported contract,
limits and examples. [Preparation before LaTeX](plugin-authoring.md) now supplies
one exercise source for live data and static editions.

A plugin is an installed Python distribution with a declarative manifest. It may
provide a browser activity engine, a complete interactive slide type, or both.
It may include zero or more LaTeX packages. An ordinary `.sty` theme is not itself
a plugin. Decks contain data and exact provider requirements, never plugin code.

## Try the example

Use a fresh virtual environment and a disposable data directory. Install this
branch's Texstage wheel and its locked development dependencies first; an older
package with the same development version does not contain this experimental API.
The commands below use the virtual environment's `python` and `texstage` commands.

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/dev.txt
python -m build --no-isolation
python -m pip install --no-deps dist/texstage-0.2.1.dev5-py3-none-any.whl
```

In the separate collection checkout, build its two packages with
`python maintenance/build_wheels.py`. Install the two wheels printed by that
command with `python -m pip install --no-deps <distance-wheel> <coordinates-wheel>`.
These are ordinary, independently versioned packages. Neither is enabled by installation.

```sh
texstage plugins --data ./plugin-profile list
texstage plugins --data ./plugin-profile inspect org.example.distance
texstage plugins --data ./plugin-profile inspect org.example.coordinates
```

Review the package code, license, manifest and resources. For each package, copy
the exact `version` and `payload` printed by `inspect` into an explicit enable command:

```sh
texstage plugins --data ./plugin-profile enable org.example.distance --version 0.1.0 --payload <distance-payload>
texstage plugins --data ./plugin-profile enable org.example.coordinates --version 0.1.0 --payload <coordinates-payload>
texstage plugins --data ./plugin-profile lock --output ./plugins.lock.json
texstage build examples/plane.tex --data ./plugin-profile --plugins-lock ./plugins.lock.json
texstage plugins --data ./plugin-profile check examples/texquiz-out/plane.bundle
texstage serve examples/texquiz-out --data ./plugin-profile --present
```

The `--data` argument to `plugins` precedes its subcommand. Relative paths resolve
from the current directory. `build`, `pdf` and `present` use a plugin profile only
when `--data` is explicit. `serve` reads its selected data directory. Restart a
server after changing enablement; the running catalog and asset bytes are immutable.

Open the coordinate slide, join from a phone, choose a point and press **Send
point**. The browser presenter leases the evaluation job and runs the separately
installed distance engine in a worker. Reveal and reset controls appear in the
presenter toolbar. The projector receives its own filtered view. A point at
`(0,5)` has the same distance as `(3,4)`, but is correctly treated as a different point.

The LaTeX package draws a static diagram for PDF and PowerPoint. External live
views currently run in the browser presenter; native PowerPoint uses the fallback.

## Author a slide

The collection's `examples/plane.tex` uses `texstage-coordinates-plane.sty`. A
plugin may instead use the generic core environment:

```tex
\usepackage{texstage}
\begin{texstagepluginbox}[
  type=org.example.coordinates.plane,id=walk,
  public=plane-public.json,private=plane-private.json
]{0.9\linewidth}{4cm}
  A static diagram or explanation.
\end{texstagepluginbox}
```

The JSON files are relative to the deck, bounded to 2 MiB and confined to its
directory. A convenience style may supply `public-json` and `private-json`
instead. Use either a file or inline JSON for each field. The final two arguments
reserve the overlay rectangle. The body is the static fallback. Full details are
also in the [LaTeX reference](latex-reference.md#experimental-plugin-authoring).

External bundles use format 3. Requirements identify the package ID, version,
portable payload digest and selected capabilities, including engines used by a
different plugin's type. Missing, disabled or changed providers fail preflight.
Built-in-only builds continue writing format 2, and formats 1 and 2 remain readable.

## Develop a package

Use `texstage.plugins.sdk` as the PEP 517 backend, delegate package selection to
setuptools, and include `texstage-plugin.json` in `MANIFEST.in`. The backend adds
the manifest, complete resource hashes and sizes to the wheel's `.dist-info`, then
updates `RECORD`. The source manifest omits `resources`; the installed manifest
must satisfy its declared manifest revision: [v1](../src/texstage/plugins/schemas/manifest-v1.json),
[v2](../src/texstage/plugins/schemas/manifest-v2.json) or
[v3](../src/texstage/plugins/schemas/manifest-v3.json).

API 1 requires a portable `py3-none-any` wheel. Own one independent Python package;
do not overwrite Texstage or share files with another distribution. Native plugin
binaries, symlinks, undeclared resources, path traversal, duplicate IDs, reserved
names and conflicting styles are rejected. Native dependencies belong in the
environment's separate platform dependency lock. Installed payload identity is
portable; the runtime fingerprint also includes Python, platform and distribution
RECORDs, and is intentionally stricter for session resumption.

Declare exactly one `texstage.plugins.v1` entry point named after the plugin ID.
Listing, inspection, catalog refresh, locking and bundle preflight only read
metadata. The factory runs only inside an enabled provider's dedicated process.
Engine-only providers do not need their factory for browser evaluation.

The factory returns `PluginV1(build_hooks=..., state_hooks=...)` from
`texstage.plugin_api.v1`. A build hook receives public/private JSON and returns
`PreparedItem`. An asset maps a logical name to `{source, visibility}`; the host
copies approved data/image files under content hashes. Evaluation bindings map
manifest names to `seed`, `options` and optional private `references`; the manifest
fixes the engine identity. Reference arrays are limited to 32 inputs of 2,000
characters each.

State hooks implement `initial_state(item, ctx)`, `transition(state, event, ctx)`
and `view(state, audience, ctx)`. Context contains JSON item data, authenticated
actor/role, epoch, revision and a host timestamp. Never retain state in module
globals or perform I/O in a reducer. Return `Transition(state, effects)` or
`{"refusal": "bounded-error-code"}` for a terminal domain refusal. Effects are
only `Evaluate(binding, correlation_id, text)` and
`CancelEvaluation(correlation_id)`. The coordinate example demonstrates the full
contract, including ignoring completion of an older submission.

Each renderer exports synchronous `mount(ctx)` returning `update`, `destroy` and,
for overlays, `place`. Presenter overlay, presenter controls, projector overlay
and participant input each get an independent mount. `ctx.container` belongs to
that instance; `ctx.signal` aborts listeners on teardown. Overlay rectangles use
CSS pixels relative to the host container. `update` receives a complete filtered
`{epoch, revision, data}` view. `ctx.dispatch(operation, payload)` owns retry IDs;
the projector cannot dispatch. Use text nodes for untrusted text. Renderer
exceptions leave the static slide usable. `resolveAsset(name)` only returns URLs
for verified browser resources or explicitly public bundle data; undeclared names
are rejected.

The host preserves mounts during ordinary view updates and disposes them when
an item/surface disappears or its module, public data, assets, role or language
changes. Late module imports cannot resurrect a disposed surface. Keep unsaved
drafts inside a mount and handle epoch/version conflicts explicitly.

Command rejection exposes `error.code`; a domain refusal also includes
`error.receipt` with the authoritative epoch/revision. Operational codes include
`queue-full`, `session-capacity`, `worker-timeout`, `worker-unavailable`,
`concurrent-update` and `environment-changed`. Generic contract failures retain
`plugin`. Never translate an operational failure into an incorrect answer.
Cancellation and replacement reserve queue space atomically without raising
the session's pending-job ceiling.

An engine exports `start(context)`, `load(library, seed, options)`,
`evaluate(state, text, context)` and `dispose(state)`. The host supplies declared
asset bytes, creates fresh state for every reference and submission, and terminates
workers after a 30-second startup or 2-second individual evaluation budget.
Output is bounded, validated and namespaced by provider, engine, canonical format,
binding, contract revision and result-schema digest. Revision-2 engines can declare
typed JSON facts; revision-1 engines retain summary-only results.
For Firefox and WebKit compatibility, an engine's manifest `module` must point
to a self-contained ES module with no static dependency imports. Keep modular
development sources and bundle the engine entry at maintenance time; the
collection's `npm run build:workers` demonstrates this. A one-file engine needs
no bundler. Ship the generated module inside the wheel and keep its content
covered by the normal provider resource hashes. Runtime asset bytes still come
from the host's declared-asset loader.

The worker imports the bundled contract and engine after initialization. Its
HTTP policy remains
`default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'none'; worker-src 'none'`.
Do not add `unsafe-eval`, `blob:`, network origins or child-worker permission to
make imports work. Changes to engine bytes produce new provider payloads; rebuild
and explicitly approve the new pins in disposable profiles before migration.
Existing enabled pins are never silently updated.

Evaluation workers cannot fetch the network or spawn workers. This is
not a sandbox for hostile plugin code: Python hooks and browser renderers remain
operator-trusted code.

## Recovery and operation

State, request receipts and logical jobs commit together in `plugins.sqlite3`.
Authentication and schema checks apply on every request. An identical retry
returns its stored receipt, including after a server restart; changing an envelope
while reusing its request ID fails. Exact-revision presenter operations and
latest-revision participant submissions are separate policies. Both check epochs.

Reset increments the epoch once, preserves whether the item is active, and
invalidates old jobs. It is guarded by epoch, so unrelated submissions do not
invalidate the presenter's reset. Other exact-policy operations retain their
revision check. Evaluation results must match their job, lease generation,
owner and epoch. Terminal results are delivered durably to the reducer, once per
logical completion. No presenter evaluator means queued work, not successful
feedback. Leases allow bounded retries, with up to two jobs per poll and a
120-second lease covering startup plus reference replay. Python hooks have a
10-second startup and 250-ms operation budget (2 seconds for build preparation);
three failures quarantine a provider until restart.

The presenter-authorized `GET /api/archive/<session>/plugins.json` exports plugin
state and jobs. It includes private data and is separate from the student PDF.
Full integration with the existing archive ZIP and recording timelines remains
part of the release gate. Keep the original environment for rollback: resuming
plugin sessions with a different runtime fingerprint is refused.

## Collection and installation

The separate [texstage-plugins collection](https://github.com/stefanjdecker/texstage-plugins)
contains sources, tests, an initially empty catalog and release preparation
workflows. Its experimental source branch is published; plugin wheel releases
are not yet published. After a reviewed release is published,
an operator can cache its index from an immutable GitHub commit:

```sh
texstage plugins --data ./plugin-profile catalog update --url https://raw.githubusercontent.com/stefanjdecker/texstage-plugins/FULL_COMMIT_SHA/catalog/index.json
texstage plugins --data ./plugin-profile search coordinate
texstage plugins --data ./plugin-profile info org.example.coordinates
texstage plugins --data ./plugin-profile install org.example.coordinates==0.1.0 --write-requirements ./plugin-wheel.txt
```

`--file` accepts a local index instead of `--url`. Installation verifies the
catalog pin, whole wheel, manifest inventory and existing dependency versions,
then invokes pip with hashes, wheels only and no dependency changes. It refuses
in-place package upgrades and overwrites; prepare another environment first.
The requirements output points to the verified cached wheel. `--offline` requires
that cache. Installation never enables a provider. Withdrawn releases cannot be
installed, and catalog refresh cannot rewrite or remove old releases. Neither a
running lecture nor an existing lock needs GitHub access.

## Classroom evaluation and reconnects

Plugin commands keep their durable receipts. Participant submissions and
evaluation results coalesce role-filtered views. Cheap broadcasts retain the
ordinary 200 ms update interval; expensive broadcasts wait up to one second
before the next full projection, based on the preceding broadcast's cost. This
leaves time for socket replies, asset requests and evaluation jobs during a
classroom burst. Presenter phase, selection and sharing controls still push
their new state immediately. An acknowledgement can
arrive before its updated view. Clients must keep using the supplied epoch,
revision and plugin-specific edit guards; an acknowledgement is not a new view.
Coalescing avoids rendering the whole class again for each answer in a burst.

A presenter leases at most two jobs per poll. It immediately requests another
batch after completing work; an empty queue or transport error retains the
750 ms backoff. Every evaluation still uses a fresh restricted worker and the
same two-second per-evaluation deadline. These bounds are unchanged.

The presenter caches immutable provider asset bytes by the complete pinned URL
(at most 64 entries and 16 MiB retained). Concurrent jobs share downloads, then
each fresh worker receives its own cloned buffers. No worker, engine state,
answer, result or reference is shared between jobs. Failed downloads are evicted;
oversized assets are usable without retention. Destroying the evaluator clears
the cache, and a late download cannot repopulate it. URL approval, CSP and all
result checks remain enforced on every job.

When the server observes a presenter socket disconnect, it requeues that
connection's unfinished jobs. Reassignment increments the lease generation;
results from an old owner or generation cannot update an answer. Disconnects do
not reset the three-attempt retry budget. The 120-second lease expiry remains
the fallback when a lost connection has not yet been detected. Without a
presenter evaluator, submitted answers remain pending.

Successful schema safety checks are cached by complete canonical schema content.
The cache holds at most 128 schemas of at most 64 KiB each; larger schemas are
checked without retention. Each value is validated with a fresh schema snapshot,
so mutating an error's exposed schema cannot change later validation. External
references/scopes and dynamic references remain refused.

The FD Lab classroom-load record in the separate plugin collection documents
the measured Windows/browser limits. A provider's storage ceiling does not
guarantee response latency for that many participants. Physical phones, LAN
conditions and deployments need their own checks.

## Implementation status and release gate

Implemented: manifest/SDK contracts, metadata discovery, explicit profiles and
locks, format-3 builds and preflight, killable Python hooks, durable receipts and
jobs, four browser surfaces, isolated browser evaluation, the independent example
packages, and catalog commands. Automated checks cover legacy behavior, hashing,
authorization, privacy, duplicate requests, crash recovery, reset and lease races.

Still required before a stable API 1 release:

- Implement the [transaction-schedule review's contract revisions](architecture/transaction-plugin-review.md):
  the transaction-specific semantic edit guards,
  editable views, fair evaluation and measured class-size operation.
  Typed engine `data`, revision-2 result/view schemas, scoped-reducer contract
  tests, revised reset behavior and preparation before TeX are implemented.
  `authoring_hook`, `--activities` and direct-pdfLaTeX exports are available;
  see [the authoring contract](plugin-authoring.md). The transaction activity is still planned.

- Complete the two-way Windows/Linux build-and-serve matrix. Local evidence covers
  Windows authoring and browser interaction, plus Linux serving of that same bundle
  using identical provider wheels; local Ubuntu has no TeX installation.
- Complete Safari/Firefox, ordinary LAN HTTP, renderer failure/cleanup,
  accessibility and concurrent-load conformance cases.
- Consolidate the legacy built-in registries behind catalog adapters after that
  prototype gate, preserving SQL read-only behavior and course facade imports.
  External engines currently bind through custom slide types; selecting them
  directly in the built-in `texcodeactivity` environment is part of that stage.
- Add the public conformance command, archive ZIP integration and remaining SDK
  packaging/rollback stress cases, then publish reviewed collection releases.

Existing courses and lecture-tools remain on their current packages and style
snapshots. Adopting plugins into a course is a separate change.

## Language in participant plugin views

Plugin projections carry the deck's language to participant, presenter and
projector renderers; decks without a language default to English. The phone's
browser-selected language supplies a fallback until that projection arrives.
The built-in phone controls retain their own browser-language selection.
Unchanged language updates do not remount a plugin or discard its draft; a
language change remounts the surface through the existing lifecycle contract.

Provider authoring language is separate: it selects generated static text and
provider-owned prepared explanations. Authors should align the activity sidecar
language with the deck's Babel/Polyglossia language where appropriate.

Presenter/projector navigation shortcuts leave key events to native interactive
controls and plugin surfaces. Enter/Space can activate a plugin button without
advancing the slide, arrows can operate a selector or scroll proof tables, and
an event already handled by a renderer is not handled again. Slide-navigation
shortcuts remain available when focus returns to the slide background.

In a narrow, short presenter window (including browser zoom), the workspace
scrolls vertically so notes and plugin controls retain usable height.

## Classroom scheduling and schema validation

Student plugin commands and evaluator results use coalesced, role-filtered
projections at a cost-aware rate: ordinarily every 200 ms, with at most one
second deliberate delay after expensive broadcasts. Durable command receipts
are still immediate. Presenter controls push their updated guarded
view immediately so selecting and then sharing an answer uses current state.
Membership, actor identity and projection rules are checked when sending.

The evaluator keeps draining nonempty batches without a fixed pause between
them; empty or failed polls retain the 750 ms backoff. The two-job lease limit,
worker confinement, result validation and evaluation deadlines are unchanged.
An observed presenter disconnect requeues only that connection's leased jobs,
retaining retry counts and rejecting its old results. The 120-second lease
expiry remains a fallback for an unobserved disconnect.

Successful schema safety checks are cached by exact canonical schema content
(128 entries, each at most 64 KiB of serialized schema). Every value is still
validated with a fresh schema snapshot. Neither caller mutation nor an exposed
validation error can corrupt later checks: validator objects are never retained.
Oversized schemas are checked without retention. External/dynamic references remain
forbidden. The serialized cache bound is not a total process-memory bound.

Class size remains provider- and deployment-specific. ER registration 0.5.0
supports 600 answering actors using bounded item records, actor-scoped updates
and opt-in deterministic result reuse. See the [host contract](plugin-contracts.md)
and the collection's `docs/design/er-600-validation.md` for exact artifacts and
measurements. Test the intended teaching host and network before deployment;
a synthetic loopback run does not measure classroom Wi-Fi or 600 rendered phones.
