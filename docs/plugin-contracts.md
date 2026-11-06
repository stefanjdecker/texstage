# Engine results and view schemas

This branch implements the first transaction-plugin prerequisite: typed engine
facts, revision-2 manifests, validated view projections and epoch-guarded reset.
API 1 remains experimental. This is usable host code; the transaction activity and
classroom-capacity changes are separate milestones. The subsequent
[pre-TeX authoring milestone](plugin-authoring.md) is now implemented.

## Manifest compatibility

The host accepts manifest revisions 1 and 2. Revision 1 remains closed and cannot
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
Old hosts reject revision 2; they must not discard fields to accept it.

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
Structured command errors,
editable-view lifecycle, fair scheduling and measured classroom load remain
later prerequisites for the transaction activity. A published compatible host
commit must be pinned in collection CI before claiming hosted conformance.
