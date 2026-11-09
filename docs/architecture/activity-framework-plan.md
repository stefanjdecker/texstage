# texstage - the activity framework: F0 and F1 (plan)

Status: 2026-11-09, the plan for the first two stages of
[activity-framework-design.md](activity-framework-design.md) (here **AF**, section 18); nothing of
it is built yet. F2 to F5 are planned once F0 has measured what they build on. File references are
to `src/texstage/` unless they name another folder; **LA** is
[live-activities-design.md](live-activities-design.md).

## 1. In short

- **F0, the spike** (about five working days): what F1 takes for granted, tried and measured on
  the presentation laptop - pyoxigraph 0.5 and `SERVICE`, runaway queries and deep nesting, what a
  pool of worker processes costs, and AF's budgets (AF 15.1) with 1,100 simulated phones. Its code
  stays on its branch; its report settles F1's open details.
- **F1, checking on the server** (about three weeks of work, and one lecture): today's
  activities - the KG lecture's four, the showcase's SQL - checked by a pool of Python workers
  instead of the presenter's browser, with today's decks, today's messages and today's phones, and
  the same groups. Checking needs no presenter window any more: with PowerPoint presenting, the
  entries are checked too.
- **For the lecturer:** nothing changes in LaTeX or on the slides. The phones say "being checked"
  instead of "waiting for the lecturer's computer", and a text the server could not check says so.
  Until a lecture has run with it, the browser can still check (4.6).

## 2. Ground rules

- **Branches:** F0 on `f0-spike`, from `main`: a prototype that stays on its branch - what F1
  takes from it is written again, with tests. F1 on `f1-server-checks`.
- **F1 comes to `main`** when its packages 1 to 6 have passed (4.9) and the KG lecture's decks run
  on the branch's server, with the browser's checks still there; they go once a lecture has run
  with both (packages 7 and 8).
- **The lectures run lecture-tools' copy of texstage,** not texstage-public: each lecture's
  `tools/` submodule is lecture-tools, installed with `pip install -e tools`. On 2026-11-09 the KG
  lecture's stood at lecture-tools 6388b6b of 2026-10-21, 47 files of `src/texstage` apart from
  texstage-public's. So F1 reaches a lecture when lecture-tools takes it - package 7's lecture
  needs that first.
- **Every package lands with its tests;** the whole suite passes on Windows and Linux, as CI runs
  it (`pytest`, the Node tests included, takes about six minutes on this PC).
- **Measured on the presentation laptop,** with the presenter window and PowerPoint or the
  projector window running (AF 15.1); the simulated phones come from a second machine.
- **The docs follow the code:** each package names the sections of LA and AF it changes; AF
  section 18 records each stage's result.

## 3. F0 - the spike

### 3.1 What is known already (2026-11-09)

- **Packages:** pyoxigraph 0.5.13 (released 2026-10-22) and psutil 7.2.2 ship wheels for every
  Python from 3.9 on (`abi3`), for Windows, macOS and Linux, x86-64 and ARM, so the locks
  (`requirements/`, `--only-binary`) can take them. Neither is a dependency of texstage yet.
- **pyoxigraph's `Store.query`** has no option to switch `SERVICE` off and none for a timeout
  (its documentation, 0.5.13). The 0.3.22 on this PC tried to connect for `SERVICE`, and 800
  nested braces - 1,615 characters - ended its process (AF 11).
- **Python's sqlite3** gives no position with an error (`incomplete input`); the venv's SQLite is
  3.50.4, sql.js's 3.49.1.
- **The KG lecture** has four activities: two crowd graphs (`02-RDF/029.tex`,
  `03-Serialization/026.tex`), a Turtle text (`03-Serialization/015.tex`, seed
  `turtle-prefixes.ttl`) and a SPARQL query (`05-SPARQL/014.tex`, seed `data.ttl` with a blank
  node, its reference with `ORDER BY`). It has no SQL: SQL is in the showcase, the reference
  examples and the manual. The crowd graphs are keyed on the server already
  (`server/activity.py:537`), so F1 moves three engines, not four.
- **`tools/simulate.py`** plays an activity only beside a presenter window that opens it
  (`--pin`), times no entry and watches no verdict, and draws its texts from small fixed pools -
  with each distinct text checked once, that leaves almost nothing to check.

### 3.2 The questions

| | question | how F0 answers it | the answer decides |
|---|---|---|---|
| Q1 | does pyoxigraph 0.5.13 run `SERVICE` over HTTP? | a local listener that records connections; `SERVICE` as written, in lower case and as `SERVICE` | how much F1's refusal (4.4) has to stop; its tests |
| Q2 | can a running SPARQL query be stopped? | results come as an iterator: a CPU check between solutions, for streaming queries; for blocking ones (`ORDER BY`, `GROUP BY`, a cross product) on the KG seeds, how long they run | whether F1 stops SPARQL from inside or by ending the worker |
| Q3 | how deep can a text nest before a parser fails? | pyoxigraph's SPARQL and Turtle parsers and SQLite, nesting 50 to 1,000 deep | a cap per engine, with a margin |
| Q4 | what does a pool cost on the laptop? | a worker started (`spawn`, pyoxigraph imported); the KG seeds prepared; a job's round trip, idle and under load; a worker ended and replaced | the pool's sizes (AF 10.3); whether ending workers holds up a burst |
| Q5 | how exact is a CPU budget? | SQLite's progress handler; psutil read every 50 ms; on the laptop's fast and its efficient cores, if it has both | the budget's margin (AF 11) |
| Q6 | do the memory limits hold? | `hard_heap_limit` with the seeds prepared; the watchdog ending a worker; a Windows job object through ctypes | each limit seen working |
| Q7 | do AF's budgets hold? | the runs of 3.4 | AF 15.1's table, filled in |

### 3.3 What F0 builds, on its branch

- **`tools/spike/pool.py`:** a pool as AF 10.3 has it - workers started with `spawn` at a low
  priority, a spare, a queue, the CPU and memory watchdogs, a job object on Windows. Run by
  itself, it answers Q4 to Q6 and prints a table.
- **`tools/spike/checks.py`:** the SQL check (sqlite3 in memory: the seed, `PRAGMA query_only`,
  an authorizer, the progress handler, `hard_heap_limit`) and the SPARQL and Turtle checks
  (pyoxigraph: the seed, `SERVICE` refused after decoding, a nesting cap), each giving today's
  status, key and summary for a text (LA 8.3) - not yet byte for byte, which is F1's work (4.3).
  Q1 to Q3 run against them.
- **On the branch only,** `server/activity.py` sends a waiting text to the spike's pool instead of
  handing it to the presenter's evaluator, and applies the result as `_result` does - enough to
  measure the whole way, no more.
- **`tools/simulate.py`** gets what the runs need, and keeps it, for F1:
  - `--activity ID`: it opens and closes the activity itself, as a presenter connection with the
    key (`--key`), so that runs repeat without a hand on the presenter window;
  - `--burst N --within S` and `--deadline`: N entries within S seconds, evenly or most of them
    in the last seconds;
  - `--distinct F` and `--runaway F`: texts made from the bundle's references - a column dropped,
    a join left out, a typo, a cross product -, a share F of them distinct, and a share F running
    into its budget;
  - `--fetch BYTES`: every phone loads a file of that size when it joins, as phones will load the
    kinds' files (AF 7.3);
  - its timings: per entry sent, acknowledged and checked, per phase change on the last phone -
    as p50, p95 and the maximum.
- **`texstage serve --max-players N`:** `max_players` is fixed at 1,000 today
  (`server/game.py:82`), and no option reaches it; F0 adds one, so that 1,100 phones can join.
- **The presenter window's slide changes timed:** `web/stage/presenter.js` logs them to the
  console behind `?timing`.

### 3.4 The runs

- **Set-up:** the presentation laptop runs `texstage serve`, with the presenter window and
  PowerPoint or the projector window; a second machine runs simulate.py - once over a room's
  Wi-Fi or a hotspot, once through the tunnel. This needs the lecturer: the laptop, the second
  machine, the tunnel's name.
- **Runs**, each three times:
  1. 1,100 phones join within two minutes, each loading 200 KB;
  2. the showcase's SQL activity: 1,000 entries within 10 s, 300 of them distinct, 1 % running
     into their budget, most of them in the last seconds;
  3. the same with the KG lecture's SPARQL activity, on its seed;
  4. a quiz round right after, and slide changes in the presenter window throughout.
- **Recorded:** AF 15.1's budgets; the server's and the workers' CPU and memory; the workers
  ended and replaced; the connections the tunnel dropped.

### 3.5 What F0 decides

`docs/architecture/activity-framework-f0.md` reports the numbers and settles: Python kept, or the
slow piece named and measured again after its fix (AF 15.3); how `SERVICE` is refused (Q1); how
SPARQL is stopped (Q2); the nesting caps (Q3); the pool's sizes on the laptop (Q4, Q5). AF section
18 notes the result, and this plan's F1 changes where F0 says so.

**Size:** about five working days - the pool and the checks two, simulate.py one, the runs and
the report two.

## 4. F1 - checking on the server

### 4.1 The way of an entry, before and after

Today a phone sends `activity.send`, and the server stores the contribution as `waiting`. A
presenter window that holds the lease asks for jobs (`activity.work`, every 5 s while entries
wait), checks them in its worker (`web/stage/evaluator.js`, 2 s of the clock per text) and sends
each result back (`activity.result`); the server applies it to every contribution waiting with the
same text (`_result`, `server/activity.py:454`). Without a presenter window - PowerPoint alone,
the host console - nothing is checked.

With F1 the server sends each new text to a pool of worker processes at once, and applies the
result when it comes: the same `_result` logic, the same pushes. `activity.work` stays only for the
lease the crowd graph's layout needs (AF 13), and hands out no jobs.

### 4.2 The pieces

| piece | where | what |
|---|---|---|
| the checks | `checks/` (new): `common.py`, `sql.py`, `sparql.py`, `turtle.py` | the three engines of `web/engines/` in Python, with the same status, canonical form, key and summary (4.3), and their safety (4.4) |
| the pool | `server/pool.py`, `server/worker.py` (new) | the worker processes, the queue, the budgets, the watchdogs, the retries (4.4) |
| the activity type | `server/activity.py` | texts sent to the pool, results applied, references prepared, restarts (4.5) |
| the server | `server/app.py`, `server/game.py` | the pool started and stopped with the server; results pushed (4.5); the modes (4.6) |
| options | `cli.py` | `--checks`, `--workers`, `--max-players`, on `serve` and on `present` (4.7) |
| windows and phones | `web/stage/presenter.js`, `web/play/activity.js`, `web/i18n/en.js`, `de.js` | no evaluator unless the server asks for one; the new texts (4.5) |
| the tools | `tools/simulate.py` | as F0 left it |

### 4.3 The same keys as today

Stored contributions, results and references hold the keys the browser made. A game that goes on
across the update, and the groups the class has seen, need the server to make the same keys: the
same canonical text, byte for byte, under the same hash. So:

- **Golden fixtures first.** A Node script, `tests/fixtures/checks/make.mjs`, runs today's engines
  over a corpus and writes each text's status, canonical form, key, summary and error
  (`tests/fixtures/checks/*.json`). The corpus: the seeds and texts of today's engine tests
  (`tests/web-activity-engine.test.mjs`, `-sql`, `-turtle`), the KG lecture's three code
  activities with their references, simulate.py's right and wrong answers, the showcase's, and
  texts that probe the rules below. The fixtures are committed and outlive the JavaScript engines.
- **What the Python checks do as JavaScript does:** sort rows by UTF-16 code units, not by code
  points; write numbers as JavaScript's `String` does - `1e-7`, not `1e-07`; `3`, not `3.0` - and
  round them to 15 significant digits as `toPrecision` does; write strings as `JSON.stringify`
  does; hash with the same 64-bit FNV-1a over UTF-8 (`web/engines/common.js:39-46`); and cut
  summaries as `cut` and `bounded` do - 20 rows, 120 characters a value, 11,000 in all, counted in
  UTF-16 code units as JavaScript counts them. sql.js reads integers above 2^53 as doubles; the
  port rounds them alike.
- **What may differ, and is said where it does:** an error's words - SQLite 3.50.4 against
  3.49.1, pyoxigraph 0.5.13 against the WebAssembly build's 0.5.11. The fixtures compare status
  and position exactly and the words where both engines agree; a case that cannot be made equal
  stays in the fixtures with its reason, as LA's L0 listed its five (LA section 14).

### 4.4 The pool, and the checks' safety

- **Workers,** as AF 10.3 and AF 11 have them: started with the server (`spawn`), as many as the
  cores less two (at least one) unless `--workers` says otherwise, at a low priority, one spare. A
  job is one distinct text of an activity; each student's jobs wait in a queue of their own, and
  the students take turns (in F0 another student's text waited one round, not three, behind one
  student's 18 slow ones). F1 needs no worker for normalizing: it merges identical texts as today,
  and the kinds' `normalize` comes with F2.
- **The event loop never waits for a worker:** a thread per worker reads its pipe and hands each
  result to the loop (`call_soon_threadsafe`). And the pool never blocks while it holds its lock:
  each worker's messages - a prepare carries a whole seed - go out through an outbox with a
  thread of its own, and a dead worker is joined, and psutil read, outside the lock; F0's first
  pool did both under it (F0's review).
- **A worker checks on a thread with a 64 MB stack:** on the default stack, pyoxigraph's SPARQL
  parser overflows at 800 nested groups and ends the process (F0, Q3 -
  [activity-framework-f0.md](activity-framework-f0.md)).
- **Budgets:** 2 s of CPU time per text, where today's are 2 s of the clock (LA 12). SQLite's
  progress handler stops a query from inside; pyoxigraph is stopped between solutions or, where
  none comes, by ending its worker (Q2). The clock stays as a backstop at five times the budget. A
  text over its budget is a `timeout`, the student's.
- **Texts that run into their budget can use up the pool:** in F0's runs with 3 % of them, 95 %
  of the verdicts came within 8.0 s, with 5 % within 15.8 s - the budget is 3 s. Package 6
  measures it on the laptop; if it holds there, F1 takes F2's short checks first
  ([activity-framework-plan-f2.md](activity-framework-plan-f2.md), 4.6).
- **Retries:** a check whose worker died, or that the backstop stopped, runs once more on a fresh
  worker; failing again, it gets the status `internal`, and its text is not checked again in that
  activity (AF 11). F0 found a text that needs it: `ORDER BY` with two keys over mixed literals
  ends pyoxigraph 0.5.13's process (Q2).
- **Memory:** SQLite's `hard_heap_limit`, set in the worker once its seeds are loaded, at what
  they take plus an allowance F0 sets; for pyoxigraph the watchdog, every 50 ms, on committed
  memory - private bytes on Windows, as the job object counts it; a job object on Windows (through
  ctypes) and `RLIMIT_AS` on Linux as the hard stop. A text that runs over on a fresh worker too
  is the student's `error`.
- **SQL** (`checks/sql.py`): the seed run into a database in memory, then
  `PRAGMA temp_store = MEMORY` - else a large sort spills to temporary files, past the cap (F0's
  review) -, `PRAGMA query_only = ON`, an authorizer that refuses `ATTACH`, `DETACH` and
  `PRAGMA`, extensions off; one statement only -
  Python's sqlite3 refuses two with an error of its own, which the check reads as `refused`, as
  sql.js's count does -, starting with `select`, `values` or `with` after its comments; more than
  100,000 rows an `error`, as today (LA 8.8).
- **SPARQL** (`checks/sparql.py`): the seed's prologue completed as today (LA 8.6); `SERVICE`
  refused before the query runs - pyoxigraph 0.5.13 connects for it (Q1) -, by a small tokenizer
  that decodes the `\u` and `\U` escapes as SPARQL does, skips strings, IRIs and comments, and
  reads variables and prefixed names whole, so that `?service`, `:service`, `ex:Service` and a
  prefix `service:` stay names (the spike's first check refused them); nesting beyond the cap
  (Q3) a `syntax` error, as an engine's own limit would be.
- **Turtle** (`checks/turtle.py`): the quotes and the prologue as today (LA 8.9); more than 10,000
  triples an `error`; the nesting cap.

### 4.5 The activity type

- **A new text goes to the pool at once** (`player`, `server/activity.py:503`), unless its result
  is known or it is queued already for that activity; the contribution is stored `waiting`, as
  today.
- **A result is applied as `_result` applies the evaluator's:** `_result`'s body becomes one
  function for both ways - the browser's results while they exist (4.6), the pool's after. It runs
  as an engine call of its own, as the ticker's `tick` does (`server/game.py:1225`), so that the
  store commits, the windows are marked for their next push and the phones it concerns get their
  state (`push_due`, `server/app.py:516`).
- **References are prepared when a game starts with the deck,** and again after a restart: every
  worker prepares each code activity - its seed, its references -, and the references' keys go
  into the activity's state as today (`st["refs"]`). A reference that fails shows in the panel as
  today, but before the lecture too: the deck list says so.
- **After a restart** the contributions still `waiting` go to the pool again; today the next
  `activity.work` handed them out again.
- **`activity.work` stays** for the layout's lease: in the server's mode its reply hands out no
  jobs and says `checks: "server"`, and `presenter.js` makes no `Evaluator`
  (`web/stage/presenter.js:705`); `activity.result` is refused in that mode.
- **Statuses:** today's five (`server/activity.py:75`) and `internal`; `waiting` now means "being
  checked". The phone's texts change in English and German - `waiting` becomes "Sent - being
  checked …" (`web/i18n/en.js:63`), and `internal` gets words: "This could not be checked - not
  your fault." The box and the panel count `internal` with the waiting ones, as unchecked; the
  panel's note on which window evaluates goes.
- **Each phone's view finds its own entries in an index by player,** instead of going through
  all of the activity's (`server/activity.py:569`, `:580`): in F0, closing an activity with 1,000
  entries reached the last of 1,100 phones after 597 ms, over the budget of 0.5 s (Q7).
- **The counts are kept as entries come and go,** instead of counting all of the activity's
  contributions on every send (`_recount`, `server/activity.py:249-253`).
- **Commits gathered, if package 6 asks for them:** one transaction per call stays, as today,
  unless the load on the laptop brings acknowledgements near their budget - in F0, 95 % within
  348 ms of 500 -; then F1 takes AF's commits every 50 ms (AF 10.2) ahead of F2.
- **No table changes:** `contributions.status` takes one value more; results and references keep
  their keys (4.3).

### 4.6 Three modes, for the first lectures

`texstage serve --checks server|browser|both`, and `texstage present` likewise:

- `server`: the pool checks - the only mode once package 8 is done.
- `browser`: as today; no pool, the presenter window checks.
- `both`: the presenter window checks, and its results count, as today; the pool checks the same
  texts, and the server writes every difference of status or key to `checks-compare.csv` in the
  game's archive folder (LA section 11). A lecture in `both` shows, with real students' texts,
  whether 4.3 holds - before the browser's checks go.

### 4.7 Options, dependencies, CI

- **`cli.py`:** `--checks`, `--workers` and `--max-players` on `serve`; `cmd_present` builds
  `serve`'s options by hand (`cli.py:348`), so it gets them too.
- **`pyproject.toml`:** pyoxigraph and psutil as dependencies; the locks made again with
  `maintenance/lock_dependencies.py` (which needs the network), and lecture-tools' lock, which
  pairs with texstage's.
- **CI** as today - Ubuntu with Python 3.12 to 3.14, Windows with 3.14 -, the pool's tests on
  both; the container job installs from the lock, unchanged.

### 4.8 Tests

- **`tests/test_checks.py`:** the golden fixtures (4.3); the refusals - `SERVICE` in every
  spelling, `ATTACH`, two statements, an update; what must not be refused - `?service`,
  `:service`, `ex:Service`, a prefix `service:`, `SERVICE` in a string or a comment; the limits -
  rows, triples, nesting, on Linux too (the 64 MB stack); a sort beyond SQLite's cap that fails
  without a temporary file.
- **`tests/test_pool.py`:** a check; a CPU timeout from inside (SQL) and by ending the worker (a
  test engine that loops); a worker that dies, its one retry, then `internal`; memory over the
  limit; the spare taking over; the priority; the job object on Windows (skipped elsewhere); the
  students' turns; a seed of several MB prepared while workers die, without the pool's lock held
  up. Budgets of 200 ms, so that the suite stays quick.
- **`tests/test_activity.py`:** its scripted checks (`test_the_clusters`,
  `test_a_turtle_activity`) run with the pool and a test engine, and, unchanged, with
  `--checks browser`; a restart with entries waiting; references prepared at the game's start;
  `both` writing a difference; over WebSockets, `activity.work` giving the lease and no jobs, and
  the phones getting their verdicts without a presenter window.
- **Node:** `web-activity-phone.test.mjs` with the new texts and `internal`; `web-i18n.test.mjs`
  finds words for every new code. The engines' tests stay until package 8.
- **The load:** F0's runs 2 and 3 on F1's code (package 6).

### 4.9 The work, in order

| | package | done when | days |
|---|---|---|---|
| 1 | the golden fixtures, from today's engines (4.3) | `make.mjs` writes them, and they are committed | 1 |
| 2 | the three checks in Python (4.3, 4.4) | `tests/test_checks.py` passes on every fixture, or the fixture says why not | 3-4 |
| 3 | the pool (4.4), from F0's prototype, with its tests | `tests/test_pool.py` passes on Windows and Linux | 2-3 |
| 4 | the activity type and the server (4.5), the modes (4.6), the options (4.7) | the activity tests pass in all three modes; the KG lecture's decks and the showcase run on the branch's server without a presenter window | 2-3 |
| 5 | the dependencies and the locks (4.7) | `lock_dependencies.py --check` and CI pass | 0.5 |
| 6 | the load on the laptop - F0's runs 2 and 3 - and what it finds | AF 15.1's budgets with 1,000 phones | 1-2 |
| 7 | into `main`, with `--checks both` as the default; lecture-tools taking it; one lecture with an activity | the lecture's `checks-compare.csv` holds no difference left unexplained; then `server` becomes the default | - |
| 8 | the browser's checks removed (4.10) | the suite passes; the docs and the manual say that the server checks | 1-2 |

About eleven to sixteen working days, and the lecture of package 7 between them.

### 4.10 What package 8 removes, and the docs

- **Code:** `web/stage/evaluator.js` and `evaluator-worker.js`; `web/engines/*.js` with the
  JavaScript half of the engines' table test; the vendored WebAssembly (`web/vendor/oxigraph`,
  `web/vendor/sqljs`) with its entries in `pyproject.toml`, the NOTICE (`tests/test_packaging.py`),
  `web/vendor/README.md` and the provenance; the `.wasm` type and the worker's CSP in
  `server/app.py`; `activity.result`, the jobs of `activity.work`, the `browser` and `both` modes;
  the evaluator's texts (`engines`, the panel's notes); `maintenance/check_showcase_engines.mjs`,
  which the showcase check calls, becomes a check in Python.
- **Docs:** LA's sections that describe the browser's checking - 4, 7, 8, 9, 10, 12, 14 and 15 -
  get a note; the manual (`docs/manual-content.json`, rebuilt with `maintenance/build_manual.py`)
  and the homepage (`site/index.html`) say that the server checks; AF section 18 records F1.

### 4.11 Risks

| risk | what then |
|---|---|
| not every key can be made the same (4.3) | the fixtures list the cases; a game started before the update keeps its stored keys, and a case that differs forms a group of its own until that game ends |
| pyoxigraph cannot be stopped from inside, and ending workers holds up a burst (Q2, Q4) | a lower budget for SPARQL, the spare prepared; the lectures' seeds are small, and a cross product on them is a few hundred rows (LA 8.8) |
| the laptop is too weak for 1,000 phones and a pool | F0 shows it before F1 begins: fewer workers, or the hosted server for the largest lectures |
| the tunnel drops phones under load (LA section 15) | F0 measures it; the phones reconnect with their tokens |
| `both` checks everything twice during its lecture | the pool's low priority; F0's runs show what the laptop takes |
| no lecture with an activity comes before the semester ends | a session with real phones - the tutors', a lab group - in package 7's place |
| many phones connect at once - after the Wi-Fi drops, say - and Windows refuses what its short queue of waiting connections cannot hold (F0: 235 of 1,000 downloads at once) | the phones try again, as they do today; the hosted server (Linux) queues more; F0's run in a hall shows how phones reconnect |

### 4.12 Not in F1

- **The pages' Content-Security-Policy moves to F2.** It guards the kinds' modules on the phones
  (AF 7.3), which come with F2, while the one module that had a policy - the evaluator's worker -
  goes in F1. And it needs care that is better spent with the modules it is for: the add-in loads
  Office.js from Microsoft's CDN (`web/addin/index.html`), and KaTeX and `web/shared/live.js`
  write inline styles. AF section 18 says so.
- **No normalizing worker, no kinds as packages, no new messages, no steps:** F2 and F3.

## 5. Calendar

A proposal, to fit the semester:

- **F0:** 2026-11-10 to 2026-11-20, its runs on a day the laptop and a second machine are free.
- **F1, packages 1 to 6:** from 2026-11-23, about three weeks, to the middle of December.
- **Package 7:** the next lecture with an activity, before or after the Christmas break.
- **Package 8:** right after it.
- **F2's plan:** [activity-framework-plan-f2.md](activity-framework-plan-f2.md), written on
  2026-11-09 ahead of F0's final report, at the lecturer's request; it changes with that report and
  with F1.
