# Actor records: manifest revision 3

This opt-in extension supports activities whose answers cannot fit in one shared
state. Manifest revisions 1 and 2 retain their existing state/effect contracts.
Revision 3 adds an optional content-type `actor_records` declaration containing
`capacity` (1–1000), `page_size` (1–25), `page_field` (a shared-state field),
and portable `value_schema` and `summary_schema` resource paths.

For example, add this to a revision-3 content-type capability:

```json
{"actor_records": {
  "capacity": 1000,
  "page_size": 25,
  "page_field": "records_page",
  "value_schema": "example_plugin/schemas/answer.json",
  "summary_schema": "example_plugin/schemas/status.json"
}}
```

The shared state initializes `records_page` to zero. A presenter message can
change it with the provider's normal control-version guard. Initial and reset
hooks receive empty records in the new epoch.

The host stores records by session, content type, item, epoch and authenticated
actor. Each value is at most 4096 canonical JSON bytes; its summary is at most
512 bytes. Actor identifiers retain their existing bounded encoding. Capacity
limits stored records, not concurrent connections. Existing records can be
replaced at capacity. The original transition, view, worker, job and receipt
budgets are unchanged.

For enabled types, hook context gains `records` with `count`, `actor`,
`number` and `value`. Participant commands/views receive only their own record.
Evaluation delivery receives the actor attached to the durable job. Other
system hooks receive no actor value. A presenter-only message may declare
`record_actor_field`, naming one payload field whose record is read; participants
cannot declare this facility. Reads never cross the current item or epoch.

Presenter context additionally contains `record_page`: `page`, `pages`,
`total` and bounded `rows` of actor identity, stable host-assigned number and
summary. The page is selected by the declared shared-state field and clamped to
the existing pages. Values are never included in the roster. Participant and
projector contexts do not receive this page.

A transition may emit one SDK `SaveActor(value, summary)` effect. The effect
does not accept an actor identifier: the host selects the authenticated command
actor or durable evaluation actor. Presenter and navigation transitions cannot
write records. The host validates both schemas and byte limits on every save.
Providers remain responsible for domain rules, version guards and role-specific
output projections.

```python
from texstage.plugin_api.v1 import SaveActor, Transition

# Inside a validated participant transition; no actor ID is accepted here.
old_answer = ctx["records"]["value"]
return Transition(new_shared_state, [SaveActor(new_answer, {"status": "pending"})])
```

Record replacement, shared-state revision CAS, evaluation jobs, cancellations
and the durable receipt commit in one SQLite transaction. Capacity, queue,
storage or concurrency failures roll everything back. Reset atomically removes
the item's actor records and invalidates its old jobs. Presenter-authorized
archives include the records as private data.

This is not arbitrary provider database access. There are no SQL, arbitrary-key
write, delete, full-roster or cross-session read effects. The resource limits
remain explicit. A changed provider/environment requires a fresh session;
old sessions are not automatically migrated.

Full-class plugin broadcasts yield between batches of 16 connections. New
mutations retain a fresh dirty marker, and every batch checks current membership,
role and state. No private projection is reused across actors or retained across
an event-loop yield. This keeps socket replies and evaluator traffic moving while
larger classes receive updates; it does not change worker policy or deadlines.
