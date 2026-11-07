# Activity points for plugins

TeXStage 0.2.1.dev6 supports quiz speed/streak scoring in manifest revision 5,
alongside the fixed activity points introduced in revision 4.
The plugin decides whether an answer meets its target. TeXStage owns the award,
publication boundary, durable ledger, total, rank and CSV export. Revisions 1–3
keep their existing behavior; declaring a `correct` field alone awards nothing.

A content type opts in with:

```json
{"scoring": {"policy": "fixed-v1", "points_field": "points"}}
```

The named field in each prepared public item must be an integer from 0 to 10,000.
Build, uploaded-bundle preflight and runtime creation validate it. Zero means
practice: the activity does not create point contributions or affect ranks.
An uploaded deck can configure an installed capability, never install code.

The SDK provides `SetCredit(credit)` and `PublishPoints()` effects. Credit is an
integer from 0 to 1,000, or `None` for pending/unavailable feedback. A participant
command or durable evaluation delivery can replace only its authenticated actor's
credit; the effect accepts no actor ID or raw point amount. The host calculates
`(maximum * credit + 500) // 1000`. The trusted reducer validates domain facts;
schema-valid browser output alone is not sufficient evidence of correctness.

Only a presenter command can publish points. Credits before publication cannot
change public totals/ranks or expose correctness. Publishing also admits later
results from already accepted submissions. Every actor has one current credit
per item/epoch; replacement changes that contribution rather than adding another.
No response-time multiplier or quiz streak bonus applies to fixed-v1 activities.
Existing quizzes retain their scoring rules and add to the same game total.

Credits/publication and reset commit in the same SQLite transaction as activity
state, actor records, jobs and receipts. Reset deletes credits and withdraws the
activity's previous contribution. A new epoch can earn a replacement award, not
an accumulated second award. Ordinary navigation preserves points. Quiz practice
rewinds preserve contributions of plugin activities whose state was not reset.
A new game/session starts with zero contributions.

The game store receives an absolute, versioned projection keyed by session,
content type and item. Updating that projection, totals and ranks is one game
transaction. The plugin ledger and game store use separate transactions: if the
process stops between them, the next synchronization replays the durable ledger.
Replaying an already applied epoch/revision cannot add points twice. Failed game
writes roll back the projection and in-memory totals and remain retryable. Reads
and exports synchronize before exposing totals. Changed runtime environments
cannot replay an old session's ledger; resume in the original environment.

Hook context gains `scoring` with `maximum`, `released` and `awarded` (integer or
null). Only a participant receives its own released award; no other actor's
credit is exposed. The plugin can display this host-calculated award. Released
scored activities add credit/point columns to the normal CSV export and contribute
to its answered/correct totals. Pending or unavailable credit exports as blank,
while a verified unsuccessful answer exports zero. Private plugin archives also
retain the ledger. Each activity supports at most 1,000 actor credits; all existing
message, worker, queue and result-security restrictions remain in force.

## Quiz speed and shared streaks (revision 5)

Use `{"scoring":{"policy":"quiz-v1","points_field":"points","time_field":"time"}}`.
The public base is 0–10,000 and the public speed window is an integer 1–3,600
seconds. Zero base means practice and has no effect on streaks or tie-break time.
Revision 4 remains closed to this policy; existing fixed-v1 behavior is preserved.

`SetPointsOpen(True)` starts/resumes the clock and `SetPointsOpen(False)` pauses
it. Only presenter commands can open it; system deactivation may pause it.
`SetCredit` from a participant command records the host's receipt time. System
evaluation delivery only updates the credit of an already timed submission.
The clock and credit share the state/receipt transaction. Replayed receipts do
not retime an answer; accepted replacements do. Publishing requires a closed
clock and records the original publication time once. Reset clears the clock.

The core uses `server.scoring.speed_points`, then applies credit, with the same
rounding as quizzes. Elapsed time excludes closed periods and is capped at the
window. The window does not itself close the provider's submission phase.
No client or evaluator can choose timestamps, points, bonuses or another actor.

The game engine replays scored quizzes and quiz-v1 activities in reveal order
using `server.scoring.streak_bonus` and the common host setting. Ties in reveal
milliseconds put quizzes before plugin activities, with stable IDs resolving
activity ties. A missing or non-perfect answer breaks the streak; an explicitly
pending/unavailable submission is neutral until a verified result arrives.
Late results or resets recompute subsequent bonuses and tie-break times. Fixed
activities remain streak-neutral. The projection stores source credits/times
separately from derived totals, so recomputation and replay remain idempotent.
Failed game writes restore scores, streaks, times, ranks and derived bonuses.

The authenticated bridge supplies the participant's complete scoring context:
`awarded`, `base_points`, `bonus`, `answer_ms`, `streak`, `maximum`, `released`.
Derived fields are absent for pending/unavailable feedback. No other actor's
values are exposed. Released quiz-v1 CSV rows add speed, bonus and time columns.
Score changes refresh all rankings even for actor-scoped provider updates.
