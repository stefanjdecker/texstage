# Engine results and view schemas

Revision 4 adds optional [host-owned activity points](plugin-points.md).
Earlier manifest revisions remain supported.

Manifest revision 3 optionally adds [bounded actor records](plugin-actor-records.md)
for larger classes. Revisions 1 and 2 retain their existing contracts.

This branch implements the first transaction-plugin prerequisite: typed engine
facts, revision-2 manifests, validated view projections and epoch-guarded reset.
API 1 remains experimental. This is usable host code; the transaction activity and
classroom-capacity changes are separate milestones. The subsequent
[pre-TeX authoring milestone](plugin-authoring.md) is now implemented.

## Manifest compatibility

The host accepts manifest revisions 1, 2, 3 and 4. Revision 1 remains closed and cannot
declare the new fields. Revision 2 adds an optional engine `result_data_schema`
and requires each content type to declare `view_schemas` covering exactly the
surfaces in `views`. All schema paths refer to inventoried, hashed package JSON
resources. Discovery validates them without importing the factory.

Engine capability addition:

```json
{"result_data_schema": "example_plugin/schemas/analysis.json"}
```

Content capability addition (for a type with these three views):

```json
{
  "view_schemas": {
    "presenter-overlay": "example_plugin/schemas/presenter.json",
    "projector-overlay": "example_plugin/schemas/projector.json",
    "participant-input": "example_plugin/schemas/participant.json"
  }
}
```

These are additions to the complete capability objects, not standalone manifests.
Each content type declares exactly one of the post-compilation `build_hook`
and the pre-compilation `authoring_hook`. The latter uses an explicit
`--activities` sidecar; see [preparing activities](plugin-authoring.md).
Older hosts reject unsupported revisions; they must not discard fields to accept
them. Revision 3 retains these fields and adds the opt-in actor-record contract.

## Engine facts and grading

An engine can return:

```javascript
{
  status: "ok",
  canonical: "order:a1,a2,b1,b2,a3,b3",
  summary: {kind: "text", text: "The conflict graph is acyclic."},
  data: {valid: true, order: ["a1", "a2", "b1", "b2", "a3", "b3"]}
}
```

For that example, a result schema can be:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["valid", "order"],
  "properties": {
    "valid": {"type": "boolean"},
    "order": {
      "type": "array", "minItems": 1, "maxItems": 15, "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 12}
    }
  }
}
```

`data` is optional even when declared. If present, it must satisfy the exact
installed engine's schema. Without a declaration it is refused. Facts travel
unchanged in `evaluation.finished.outcome.data` to the owning type's reducer;
they are not automatically exposed to students or the projector. The type chooses
which facts each view may contain and verifies exercise/submission identity.

The canonical key groups equal engine results. `matches` exists only for bindings
with reference evaluations and means canonical equality with one of those
references. It is not a general correctness flag. A transaction activity can
accept several distinct acyclic repairs from their facts without supplying an
equality reference. The core adds no transaction-specific grading rule.

Validation runs inside the evaluation worker, again before browser transmission,
and on the server before committing the leased result. Invalid data cannot consume
the job's successful result slot. The result namespace includes provider payload,
engine, canonical format, binding, contract revision and data-schema digest.
An old, foreign, expired or reset lease cannot commit a new result.

## Supported portable schema profile

New result/view schemas use a bounded subset of JSON Schema 2020-12, interpreted
without generated JavaScript or network access. The server also validates with
its installed JSON Schema validator. The accepted assertion keywords are:

- `type`, `enum`, `const`.
- `properties`, `required`, `additionalProperties`, `minProperties`, `maxProperties`.
- `items`, `prefixItems`, `minItems`, `maxItems`, `uniqueItems`.
- `minLength`, `maxLength` (Unicode code points).
- `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`.
- `allOf`, `anyOf`, `oneOf`, `not`.
- `$defs` and acyclic local JSON-pointer `$ref` values such as `#/$defs/edge`
  (standard `~0`/`~1` escaping; no percent-encoded pointer segments).

Boolean schemas are supported. Allowed annotations are `$schema`, `title`,
`description`, `$comment`, `examples` and `default`; annotations do not modify
values. The only supported declared dialect is
`https://json-schema.org/draft/2020-12/schema`.

All other keywords fail discovery, including `pattern`, `format`, `multipleOf`,
`unevaluatedProperties`, remote references, `$id` and dynamic references.
This explicit restriction prevents Python/JavaScript validation disagreements.
Existing command-message schemas retain their existing server-only support.

Each new schema is limited to 32 KiB of canonical JSON, depth 32 and 2,048 expanded
schema visits. Facts and revision-2 views must be plain JSON, nested at most
64 levels, with finite numbers of magnitude at most 9,007,199,254,740,991.
No getters, custom objects, sparse arrays or non-finite numbers cross the browser
contract. Use strings for larger exact values.

Typed facts have an 8-KiB budget inside the existing 12-KiB complete outcome budget;
the two budgets do not add together. These use ASCII-escaped JSON bytes on the
server. Values are refused rather than truncated. Canonical strings and optional
canonical row arrays each have a 1-MiB worker budget.

Standard summaries are closed objects: `text` has `text`; `ask` has `boolean`;
`select` has `columns`, `rows`, `count`; `graph` has `rows`, `count`.
Optional `diff` has nonnegative `common`, `missing` and `extra` counts.
Tables/graphs allow at most 20 displayed rows, 128 columns and 120-character cells;
graph rows have exactly three cells and table rows match their columns. Text
allows 10,000 characters, still subject to the combined byte budget. Failure
outcomes contain only `status`: `syntax`, `error`, `refused` or host `timeout`.

## Views, concurrency and reset

Revision-2 surface projections are checked against their declared schema before
transport. Use distinct closed schemas for presenter, projector and participant
fields. This catches unintended extra fields; trusted plugin code remains
responsible for the meaning and privacy of fields it declares. Revision-1
providers keep their existing view contract.

The existing `latest` revision policy runs a command against current committed
state. A reducer can check its own phase token, control version and per-actor
answer version atomically. This permits unrelated students to submit without
invalidating a presenter's control. A closed answer phase can still receive a
result for a previously accepted answer; superseded answer slots must ignore it.

Use the SDK helper for evaluation effects:

```python
from texstage.plugin_api.v1 import Evaluate, evaluation_correlation

correlation = evaluation_correlation(event["actor"], event["request_id"], "repair")
effect = Evaluate("schedule", correlation, normalized_answer)
```

The named slot distinguishes several effects in one command; actor identity
distinguishes different participants who happen to use the same request ID.
The collection's revision-1 coordinate example also uses this helper.

Presenter reset now checks the current epoch instead of the whole-item revision.
`expected_revision` remains a required nonnegative integer in the envelope.
Reset atomically advances the epoch, replaces state, invalidates old jobs and
saves its receipt. A lost-ACK retry returns that receipt; another presenter
still targeting the old epoch receives `stale-epoch`. Exact-policy operations
other than reset keep their revision check.

The runtime fingerprint includes this contract revision. Existing plugin sessions
must remain in their original environment; use a fresh session with this host.
No existing course environment is upgraded by building these changes.

## Verification and next milestone

`tests/test_plugin_contracts.py` checks schema discovery, malformed results,
restart delivery, namespace identity, view-field leakage, reset races, actor
correlations and phase/control/answer guards. Its shared schema cases run in
Python and JavaScript. The collection's browser conformance runner exercises
typed results in a real worker as well as the installed revision-1 example.

Preparation before TeX now lets one exercise source generate live data, handout
and worked solution; see [the authoring contract](plugin-authoring.md).
Structured command errors and mount reconciliation are implemented, along with
atomic cancellation/replacement at queue capacity; see the
[renderer contract](plugins.md). Fair scheduling and measured classroom load
remain later prerequisites for the transaction activity. A published compatible host
commit must be pinned in collection CI before claiming hosted conformance.

## Repeated schema validation

The host caches successful JSON-schema safety and meta-schema checks by canonical
schema content. It still validates every command, result and role-specific view.
The cache holds at most 128 immutable keys of at most 64 KiB each; larger schemas
are checked without caching. This does not change message, view or worker limits.

Each call uses a fresh snapshot for instance validation. Mutating an input schema
causes another safety check, and a schema exposed by a validation error cannot
alter a later call. External references, external scopes and dynamic references
remain forbidden. No validator, mutable schema or validated instance is shared
through this cache. See `tests/test_plugin_schema_cache.py` and
`tests/test_plugin_schema_cache_isolation.py` for security and mutation regressions.

This generic optimization was prompted by Query-plan's 64-participant load
probe. It does not establish a host-wide capacity guarantee or change evaluator
leases, queue policy, worker CSP or provider authorization.

## Bounded item records (host 0.2.1.dev4)

A manifest-revision-2 content type can declare `state_records: true`. Its state
hook then implements `record_keys(state, event, ctx)` before transition and view
calls. Return a list of keys, or `{"keys": [...], "page": {"offset": 0, "limit": 16}}`.
The host supplies the requested existing values in `ctx["records"]` and the
ordered page keys in `ctx["record_page"]`. Page order is the database's key order.
The scope is always the current session, content type, item and epoch.

Use `PutRecord(key, value)` from `texstage.plugin_api.v1`, or its JSON effect
`{"kind": "put-record", "key": key, "value": value}`, to upsert a record. State,
record writes, jobs and the receipt commit in one revision-checked transaction.
Reset removes the item's records and advances its epoch; private session archives
include records. Replaying an accepted receipt does not execute the writes again.

The limits are 1,024 records per item/epoch, 4,096 canonical JSON bytes per value,
and 32 distinct reads per hook call including any page and explicit selection.
A key has 1–256 characters and at most 512 canonical JSON bytes. Page offset is
0–1,024 and limit is 1–32. Duplicate write keys, malformed requests and excess
capacity are rejected. Existing effect, transition, command and view budgets
remain unchanged; this API avoids sending an entire classroom's answers through
every hook. It does not grant the provider direct database access.

Enabled provider hooks are trusted code. They must request and project only the
records appropriate to the authenticated audience; the host enforces item/epoch
scope and output schemas, not the meaning of an arbitrary record key. Record
contents are never automatically included in public views.

## Actor-scoped participant updates

A content type may opt into `participant_updates: "actor"` only when a
participant command and its completion cannot change another participant's
projection. The host then coalesces updates for affected authenticated actors;
presenters/projectors still refresh. Presenter commands, reset and navigation
remain full broadcasts. Multiple pending actor sets are unioned, and a full
broadcast dominates them. Providers without this declaration retain the original
broadcast behavior. Global participant counts therefore belong in presenter
views for an opted-in activity, not in each phone's live projection.

## Deterministic successful-result reuse

A revision-2 engine may declare `result_cache: "by-input"` when its outcome is a
deterministic function of its prepared binding and exact input. The host can
reuse a previously accepted, validated successful outcome within the same
session, content type, item and epoch. The cache identity includes the provider
payload, engine/result schema, binding seed/options/references and exact input.
No cached outcome crosses a reset, exercise or session boundary. Non-success,
invalid, expired, cancelled, superseded-owner or stale-generation results do not
prime the cache. The in-memory LRU retains at most 128 immutable JSON outcomes;
each retains the existing 12 KiB result limit. A restart safely discards it.

Each submission still has its own durable job, authenticated actor, correlation,
answer version and guarded delivery transition. A known cache hit can be stored
atomically with the new job and delivered before broadcasting its saved state,
without an unnecessary intermediate pending projection. A cache hit is never a shortcut
around provider semantic verification or audience privacy. At most 32 cached
jobs are completed per work poll; the presenter polls promptly while queued work
remains. Fresh executions still use fresh restricted workers, at most two per
poll, with unchanged CSP, network restrictions, deadlines and retry limits.
Engines with stateful, random, time-dependent or actor-dependent outcomes must
not opt in. Existing engines remain uncached by default.

The separate revision-3 [actor-record API](plugin-actor-records.md) remains
available with its host-controlled authenticated-actor projection. The revision-2
item-record opt-in described here uses provider-selected keys and a different
context shape; a content type uses the contract declared by its manifest.

See `test_plugin_records.py`, `test_plugin_result_cache.py`, the broadcast tests
and the evaluator-poll tests for transaction, isolation and bounded-work checks.
Use fresh sessions and an exactly pinned compatible host/provider environment;
the development version alone is not a reproducible artifact identity.
