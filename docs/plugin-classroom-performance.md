# Plugin classroom projections

Large classes can spend more server time projecting private phone views than
evaluating the activity itself. The host batches audience projections from one
committed item snapshot, while retaining the existing API-1 `view` hook.

The authenticated bridge determines each connection's role and actor. The
runtime checks its requested surface, fetches the state/spec once and sends
groups of at most 32 audiences to the isolated provider process. The worker
calls the ordinary view hook with a fresh deep copy of state, audience and
context for each projection. A provider that mutates an input cannot contaminate
the next student's input. No private projection is cached or reused for another
actor, session or surface.

Results are streamed separately, each with the existing 250 ms response timeout.
The batch does not grant a longer deadline to one hook. A timeout still kills
the worker; repeated failures still quarantine the provider. Every result is
checked against its own surface schema and the existing 128 KiB output limit.
Each synchronous batch owns a fresh schema-validator snapshot, discarded on
completion or the first error. This avoids repeated schema parsing without
sharing a mutable validator or an exception-owned schema across requests.
The 8 MiB IPC frame, 256 KiB transition, queue, receipt and evaluation limits are
unchanged, as are browser CSP and fresh-per-submission engine workers.

The authenticated presenter normally leases two jobs at a time. With at least
32 eligible queued/expired jobs, it leases up to four. The four-worker ceiling
reduces competition between fresh module startup, the presenter and incoming
submissions. Each job still
gets a separate worker, the same evaluation timeout and validated result/lease
identity. No engine state is pooled; a presenter disconnect requeues the owned
leases without resetting their retry generations.

Participant bursts coalesce projections; opt-in actor-record providers can
target the affected student's connections while retaining shared-field
invalidation. See [actor notifications](plugin-actor-records.md).
Presenter controls and core
navigation still push immediately. Full-class background broadcasts yield after
16 connections, refresh membership/state before each batch, and retain dirty
markers raised while yielding. Private projections never survive across a yield.
This is a transport optimization and needs
no plugin manifest or SDK hook change. Existing providers continue to implement
`view(state, audience, ctx)`.

An evaluation completion whose validated transition has no effects and leaves
the state byte-for-byte unchanged only marks that job delivered. It keeps the
same transaction and epoch/revision compare-and-swap protection, without
rewriting the class state or generating a visible revision for a superseded
answer. Actual state changes and user command receipts retain their usual
commit behavior.

Regression coverage lives in `tests/test_plugin_view_batch.py` and
`tests/test_plugin_broadcast.py`: authenticated audiences, session/role isolation,
input mutation, per-result schema/byte limits, stream alignment after a failure,
ordinary kill deadlines, partial broadcasts and session teardown. The separate
texstage-plugins repository supplies the installed-wheel 600–1,000-student B+ load
probe, including replacements and evaluator recovery. Synthetic loopback load
does not measure a lecture hall's Wi-Fi or physical phones.

Earlier scored B+ 0.7.0 checks with the 2/4/8 policy completed at 600/1,000 with Chrome and Firefox
presenters, and at 600 with Windows WebKit. WebKit intermittently crashed at
1,000; use Chrome or Firefox for that ceiling. Those historical measurements
do not establish capacity for the current four-worker policy. The collection's
classroom release validation records current transaction results separately
from B+ checks. Physical-classroom testing remains open.

For large-class B+ activities, manifest-3 actor records keep each answer outside
shared state and page private presenter summaries in groups of 25. See
[actor records](plugin-actor-records.md). The host keeps its 1,000-pending-job
ceiling; atomic cancellation permits replacement at a full queue. Queue
admission queries count only relevant rows and run only when adding jobs.
No change to SQLite FULL durability, per-worker isolation or security policy is
part of the throughput adaptation. Four-job batches apply at 32 eligible jobs;
smaller queues use two. Each bounded lease batch
commits once before any jobs are returned and rolls back entirely on failure.
