# texstage - the activity framework: F0 and F1 (plan)

Status: 2026-11-10, the plan for the first two stages of
[activity-framework-design.md](activity-framework-design.md) (here **AF**, section 18). F0's spike
is built and measured on one machine, its runs on the presentation laptop are still to come; F1's
packages 1 to 5 are built on `f1-server-checks` (4.9 and 5 say where it stands). F2 to F5 are
planned once F0 has measured what they build on. File references are
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
- **For the lecturer:** nothing changes in LaTeX or on the slides. Where the server checks, the
  phones say "being checked" instead of "waiting for the lecturer's computer", and a text the
  server could not check says so.
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
- **Not run yet (2026-11-10):** F0's numbers are from one machine, the server and the phones on
  it (its report says so). F1's packages 1 to 5 were built on those; the runs on the laptop come
  with package 6, on F1's code, in one session (4.9) - what they find about the laptop, the Wi-Fi
  and the tunnel changes F1 then, not before it.

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
| between them | `server/checking.py` (new, package 4) | the pool's answers to the engine on the event loop, the modes, `both`'s differences (4.5, 4.6) |
| the server | `server/app.py`, `server/game.py` | the pool started and stopped with the server; results pushed (4.5); the modes (4.6) |
| options | `cli.py` | `--checks`, `--workers`, `--max-players`, on `serve` and on `present` (4.7) |
| windows and phones | `web/stage/presenter.js`, `web/play/activity.js`, `web/i18n/en.js`, `de.js` | no evaluator unless the server asks for one; the new texts (4.5) |
| the tools | `tools/simulate.py`, `tools/load/` (new, package 6) | the simulator as F0 left it; the runs' bundle and their runner (4.9) |

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
- **What package 2 found (2026-11-09):** every field compares equal - status, error, key,
  canonical form, rows, summary - in 294 cases of 300; the versions made no difference, nor did
  SQLite 3.45.3 (Python 3.13, near Ubuntu's 3.45.1). The six that differ are in
  `tests/test_checks.py` (`KNOWN`): `SERVICE SILENT` refused (4.4); `load_extension` an error in
  other words; a lone surrogate, which only a broken phone sends, U+FFFD on the server where
  sql.js gave SQLite its three bytes; and parameters with and without names in one statement, an
  error. The browser's SQL check changed with package 2 - a text with the keyword `PRAGMA` is
  refused before anything is compiled (4.4) -, and the fixtures were made again from it. To get
  there the port reads texts as
  sql.js did - up to a NUL, through `TextDecoder`, which writes ill-formed bytes as U+FFFD and
  drops a leading byte order mark -, gives SQLite the text up to a NUL, as sql.js's C string
  did, finds empty statements by SQLite's tokenizer - a run of spaces that starts with one of
  five and goes on with `\v`, a byte order mark a space, `/*` at the very end a slash -, and
  runs a statement with parameters, `?` or `:name`, as sql.js did, each NULL: Python's sqlite3
  wants values for them, a list for nameless ones, a mapping for named ones, and refuses both
  kinds at once.

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
  is the student's `error` - one that reaches SQLite's own cap at once (decided 2026-11-10, the
  second review below).
- **SQL** (`checks/sql.py`): the seed run into a database in memory, under
  `PRAGMA temp_store = MEMORY` - else a large sort spills to temporary files, past the cap (F0's
  review) -, set before the seed and once more after it; then `PRAGMA query_only = ON`,
  extensions off. In the pool one process runs the seed, the others load a copy of the database
  it left (2026-11-10, below). The statements found as sql.js's count
  found them - split where SQLite splits them, each compiled behind `EXPLAIN` and none run -,
  one only, starting with `select`, `values` or `with` after its comments; more than 100,000
  rows an `error`, as today (LA 8.8). **Pragmas** (found in package 2): SQLite carries out many
  of them as it compiles them - `query_only = OFF` among them, behind `EXPLAIN` too -, and
  sql.js, which compiled every statement to count them, let a text make the database writable,
  after which a `WITH ... DELETE` emptied it for every text after it, in the presenter window,
  until it was reloaded. So both checks - the browser's (`namesPragma`, fixed in package 2) and
  the server's (`names_pragma`) - refuse a text with the keyword `PRAGMA`, read as SQLite reads
  it - not in a string, a quoted name, a comment or a parameter -, before anything is compiled;
  and on the server an authorizer makes a `PRAGMA`, an `ATTACH` and a `DETACH` compile to nothing
  besides, the second guard. While the query runs, the authorizer refuses `ATTACH` and `DETACH`;
  a pragma's table-valued function - `pragma_table_info('t')` - reads as in sql.js, as SQLite
  has them only for pragmas without effects.
- **SPARQL** (`checks/sparql.py`): the seed's prologue completed as today (LA 8.6); `SERVICE`
  refused before the query runs - pyoxigraph 0.5.13 connects for it (Q1) -, by a small tokenizer
  that decodes the `\u` and `\U` escapes as SPARQL does, skips strings, IRIs and comments, and
  reads variables and prefixed names whole, so that `?service`, `:service`, `ex:Service` and a
  prefix `service:` stay names (the spike's first check refused them); nesting beyond the cap
  (Q3) a `syntax` error, as an engine's own limit would be. The seed's blank nodes numbered in
  the order they come (2026-11-10, below).
- **Turtle** (`checks/turtle.py`): the quotes and the prologue as today (LA 8.9); more than 10,000
  triples an `error`; the nesting cap.
- **What package 3 built (2026-11-09):** `server/pool.py` and `server/worker.py`, from F0's
  prototype, with what the design adds to it. A worker sends back what the presenter window's
  evaluator sent - status, error, key, summary -, and after the first reference that gave a
  result, each summary's `diff` against it, as `evaluator-worker.js` added it; the rows stay in
  the worker. A check stopped by the clock, or whose worker died, runs once more on a fresh
  process - the spare, or a worker that has checked nothing yet -, then is `internal` and set
  aside in the pool; a CPU overrun is the student's `timeout` at once; a memory overrun on two
  fresh processes the student's `error` ("needs more memory than a check may use", in both
  catalogs). (The review below changed the references, the prepares and much else.) The watchdog counts memory from what a worker held after its prepares, plus 1 GB;
  SQLite's cap is the seed, 32 MB and 256 MB, set by the first SQL seed a worker loads, since the
  cap only goes down; the hard stop is 2 GB of committed memory per worker in a job object on
  Windows - which also ends a crashed worker without a dialog, and every worker when the server's
  process is gone -, and 4 GB of address space on Linux. SPARQL and Turtle read their solutions
  under the budget, every 16; what streams none - a `COUNT`, an `ORDER BY` - the watchdog ends. The
  same text while it is checked is one job; a seed that does not load fails its activity, and so
  does one whose preparing ends two workers; three workers in a row that die before they are
  ready stop the pool from starting more. Processes start, and futures resolve, outside the lock.
  `tests/test_pool.py` passes on Windows and on Linux (WSL's Ubuntu 24.04, Python 3.12.3, SQLite
  3.45.1). That Linux run found three things in the checks: Python 3.12's `urljoin` drops the
  empty fragment of a namespace `ns#`, which JavaScript's `URL` keeps (fixed); Python 3.12.3 took
  `?2` for a named parameter (handled); and Debian's SQLite allows parameters up to `?250000`,
  where sql.js's and Python's own stop at `?32766`, so SQLite's message differs (the test accepts
  either). CI has neither psutil nor pyoxigraph until package 5: the pool's tests, and the SPARQL
  and Turtle checks', skip there until then.
- **What package 3's review found, and what changed (2026-11-09):** a critical review - an
  independent reviewer with experiments, and mine - found thirteen faults, all confirmed:
  - *Leading spaces:* the SQL check's patterns for SQLite's spaces backtracked exponentially - 26
    spaces or newlines in front of a query took 6.6 s, which the pool would have made a `timeout`;
    possessive now, 0.1 ms. Adversarial texts of 2,000 characters take under 30 ms in all three
    checks.
  - *References:* every process checked them at once, watched only by a 120 s backstop: one that
    ran away held up every check of every activity for two minutes, then failed its activity.
    Now one process - the spare, else one that waits - checks them first, each under 10 s of CPU
    time: a runaway one is a `timeout`, one that ends its process `internal`, the next process goes
    on with the ones after it, and the others load the seed only then. The seed's backstop counts
    from when its loading begins, not from when it was queued.
  - *Preparing again, dropping:* a prepare's answer did not say which prepare it answered - one
    prepared again got the earlier one's outcomes, or failed with its error; prepares have
    generations now. A check of a dropped activity whose worker died waited for ever, holding up
    its student's other texts: it is `internal` now, and a student's text that no process can take
    yet holds up none of theirs.
  - *Breaking down:* a pool whose processes died before they were ready went on starting about
    eight a second; a process that could not be started ended a thread and emptied the pool
    unnoticed; two replies resolving one future could end a reader thread and lose its worker;
    `budget_s=None` ended the watchdog. Now the broken pool starts none and fails what comes at
    once; a failed start counts as an early death; futures are claimed under the lock and the
    readers and the watchdog survive whatever one message or round raises; a budget is a number of
    seconds, more than 0, at most 10.
  - *Budgets and memory:* a budget bounded only the engine's part - the Python work after it, the
    key above all (FNV-1a in Python, 9 MB a second), went uncounted, and `SELECT zeroblob(40000000)`
    ended its worker. Now that work counts, and is quicker: JSON quoting, UTF-16 lengths and cuts
    by regular expressions, the sort without a key unless a character beyond U+FFFF is among the
    rows, a blob shown from its first 64 bytes; both texts stop themselves at 0.2 s. A worker that
    ran out of memory itself - a job object's limit - made it the student's `error` at once: now the
    worker ends and the text runs once more on a fresh process, as the design has it; pyoxigraph
    ending its process at the hard stop stays `internal`.
  - *Retries, closing, the rest:* without a spare a retry could wait for ever for a fresh process -
    it takes any free one when no fresh one is to come; `close()` ended busy workers one after
    another, 2 s each - now at once, waiting checks answered first; the CPU baseline was written
    outside the lock, a log line inside it; workers outlived a killed server on Linux - they end
    themselves now when their parent is gone.
  - *Tests:* the lock's test could not fail - a mutant sending prepares under the lock passed it;
    with a busy worker taking the 8 MB seed, the mutant fails now (1.26 s held). `tests/test_pool.py`
    has 33 tests, one for each fault, about 25 s; it and `tests/test_checks.py` pass on Windows (five
    runs in a row) and on Linux (three).
- **What the second review found, and what changed (2026-11-10):** before package 4 builds on the
  reworked pool, the user asked for a second critical review of it - an independent reviewer with
  experiments, and mine. Eleven faults, each reproduced against the real pool, all fixed ("Fix all
  eleven"), one by changing a decided rule:
  - *A drop, then a prepare under the same name* began again at generation 1, so what the dropped
    prepare answered counted for the new one: the old references' outcomes came back for the new
    references, and a worker counted as prepared that held nothing - every check of the activity
    `internal: not prepared` (20 of 20), while `wait_ready()` said all was ready. Generations are
    the pool's now, never given twice.
  - *Checks made against an earlier prepare:* a text checked while its activity was prepared again
    came back with the old seed's outcome, and the same text submitted after joined that check. A
    job carries its prepare's generation now; one that ran against an earlier one runs again, not
    counted as a try, and one of an activity dropped meanwhile is `internal`.
  - *The waiting spare slowed every burst:* with the workers busy the spare was free, and every
    submit and every message walked the whole queue for a job it could take - none, as it takes
    retries only. 1,000 SQL texts on 4 workers: 0.41 s inside `submit()` and 1.0 s to the last
    verdict, against 0.006 s and 0.12 s without a spare, quadratic in the queue. The queued
    retries are counted now, and with no worker free only they are looked at: 0.007 s and 0.15 s.
  - *SQLite's own cap ended two workers per text:* a forgotten join condition with `ORDER BY`
    reached it; the pool ended the worker, ran the text on a fresh one, ended that too and
    answered after 3.25 s - though SQLite stops such a query from inside and counts alike in every
    process. Now the text is the student's `error` at once and its worker goes on (the design's
    section 11, decided 2026-11-10); Python's own `MemoryError` still runs once more, fresh.
  - *Retries on fresh processes:* without a spare the retry went to a worker that had made three
    checks while the fresh replacement still loaded its seed, and two deaths at once put the second
    retry on the spare after its first. A retry now waits for a process being started, replaced or
    still preparing its activity, and is placed before the students' turns, so that no first try
    takes the fresh process; a process not ready within a minute is ended.
  - *A process that could not prepare what another did* - its seed not loading there, or the
    reference with the rows giving none there - failed the activity for every process after its
    prepare had succeeded, unannounced; for the rows, it prepared anyway, and its checks carried no
    diff. Now that process is ended and a fresh one prepares the activity; when three could not,
    the activity fails, and the log and `stats()["failed"]` say so.
  - *SQLite's cap was set from one seed but holds for the whole process:* each SQL seed set it to
    its own pages and 288 MB, and a smaller seed after a larger one lowered it below what the
    larger one held: a 300 MB seed worked alone, and with a small SQL activity after it no text of
    either ran. The cap is set through `sqlite3_hard_heap_limit64` now (ctypes, in Python's own
    SQLite - checked on Windows and on Ubuntu) from all that SQLite holds, and lifted while a seed
    loads; where ctypes cannot reach it, the pragma, set once by the first seed.
  - *Closing while a replacement started* left that process running, outside the job object (5 of
    5 when caught in the window): `close()` waits for it now, and `_spawn` ends it.
  - *Linux:* under `ulimit -v` below twice the hard stop every worker failed at its `setrlimit` -
    a process may not raise its hard limit - and the pool broke; only the soft limit is set now,
    never above what it was.
  - *Tests that passed with the behaviour broken:* the pool's tests passed against a pool that
    retried on any process, and against one that looked at each student's first text only; none
    held a prepare after a drop or closing while a process starts. `tests/test_pool.py` has 48
    tests now, about 37 s. Of the 15 new ones, 13 fail against the code before the review, one holds
    behaviour that was right but untested, and the Linux one stands for an experiment that failed
    there before. They and `tests/test_checks.py` pass on Windows (five runs in a row) and on Linux
    (three).
  - *Found on the way:* a seed with `random()`, `randomblob()` or the time (`datetime('now')`)
    gives each worker data of its own - the browser ran a seed once -, so one text can get
    different keys on different workers (put to the user, 2026-11-10; fixed before the commit:
    the next point).
- **The same data on every process (2026-11-10):** the user chose to fix that before committing.
  Every process ran an SQL seed, the browser one: with `random()` two workers gave one query two
  keys (the review's E8), and a right answer could count as wrong on one process and right on
  another. Now the first process alone runs it, and the database it leaves
  (`Connection.serialize`) goes to the pool, which every other process loads in the seed's place
  (`deserialize`) - the next to go on with the references, the spare, and every process started
  later -; the first checks on such a copy too. A copy is the database alone, so the seed's
  `PRAGMA` statements, which hold for their connection (`case_sensitive_like`), run again over it -
  found by SQLite's tokens, read in Python, where the word is in the seed at all: a 4 MB seed of
  `INSERT`s runs in 0.10 s, its copy loads in 0.04 s, and in 0.66 s with a `PRAGMA` in it.
  A seed that leaves TEMP objects or an attached database has no copy, nor has a database beyond
  128 MB or a quarter of the memory allowance - making a copy takes three times its size for a
  moment -: every process runs such a seed, as before. The copy goes through the pipe as bytes of
  its own, not pickled; while it is made the authorizer steps aside - SQLite reads
  `PRAGMA page_count` as it copies, which the authorizer made nothing, so the first copy failed
  unseen - and SQLite's cap is lifted. 36 MB took 21 ms to copy and 7 ms to load, and queries ran
  on the copy as fast as on the run.
  - *SPARQL too, which I had called unaffected:* pyoxigraph gives each blank node a random id as
    it reads the seed, and their order decides `ORDER BY` and what a `LIMIT` takes after it -
    `SELECT ?n WHERE { ?p :name ?n } ORDER BY ?p LIMIT 2` over blank nodes gave four keys in five
    processes. The seed's blank nodes are numbered in the order they come now; the other queries
    tried gave one key already, blank nodes being alike in the canonical form. Turtle compares
    unordered graphs: unaffected.
  - *Found on the way, and fixed:* the server's SQL check lost a seed's TEMP tables and views -
    `temp_store = MEMORY` was set after the seed, and SQLite drops every TEMP object as the setting
    changes; the browser kept them. It is set before the seed now, and once more after it.
  - *Tests:* 13 new, 8 in `tests/test_checks.py` and 5 in `tests/test_pool.py` (53 now). All 13
    fail against the code before: six by what they test - other keys or tokens on other processes,
    the TEMP table gone -, seven for want of the new functions. Both files pass on Windows (three
    runs in a row) and on Linux (three).

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
- **Statuses:** today's five (`server/activity.py:75`) and `internal`. The phone's texts change in
  English and German: where the server checks, `waiting` says "Sent - being checked …"
  (`web/i18n/en.js:63`) - in the browser's mode and in `both`, as before, "Sent - waiting for the
  lecturer's computer …"; the phone's view says which (`checks: "server"`) -, and `internal` gets
  words: "This could not be checked - not your fault." The panel counts `internal` apart from the
  waiting ones, as the design's panel does (AF 13), and in the server's mode its note says that the
  server checks, or why it cannot. (Package 4's review changed this rule, which had the box and the
  panel count `internal` with the waiting ones and dropped the note: a pool that broke looked like a
  slow one.)
- **Each phone's view finds its own entries in an index by player,** instead of going through
  all of the activity's (`server/activity.py:569`, `:580`): in F0, closing an activity with 1,000
  entries reached the last of 1,100 phones after 597 ms, over the budget of 0.5 s (Q7).
- **The counts are kept as entries come and go,** instead of counting all of the activity's
  contributions on every send (`_recount`, `server/activity.py:249-253`).
- **Commits gathered, if package 6 asks for them:** one transaction per call stays, as today,
  unless the load on the laptop brings acknowledgements near their budget - in F0, 95 % within
  348 ms of 500 -; then F1 takes AF's commits every 50 ms (AF 10.2) ahead of F2.
- **No table changes:** `contributions.status` takes one value more; results and references keep
  their keys (4.3). An older texstage on the same data folder - lecture-tools' until package 7 -
  takes `internal` for a result, though: its windows show such entries as a group "internal". A
  game with them is best not played on with it.
- **What package 4 built (2026-11-10):** `server/checking.py` between the pool and the engine: the
  pool answers on its own threads, and its answers wait in an inbox until the event loop applies
  them, all that came at once, with one commit (`Engine.apply_checks`). In the pool an activity is
  its build and its id, prepared once for every game of that build when a game starts and after a
  restart, and dropped when the build's last game ends; a text goes to the pool as it comes, one
  job per distinct text, whichever games wait for it. Its outcome is applied as the window's result
  was (`_apply`, shared) - a summary over the limits is left out, not the check -; `internal` counts
  with the waiting ones and forms no cluster, and the phone says "This could not be checked - not
  your fault." without the server's reasons. In the server's mode `activity.work` gives the lease
  and no jobs and says `checks: "server"`, also without the lease, the presenter window makes no
  evaluator - elsewhere it makes one on the first reply that gives it the lease -, and
  `activity.result` is refused; in `both` the window's
  results count and every difference of status or key - for texts and for references - is a row of
  `checks-compare.csv`: the time, the activity, what (a text, reference 1 ...), the text, and each
  side's status, key and error. Each phone's entries are found by player, and the counts and the
  waiting texts are kept as entries change (`Shelf.change`), not counted again. The deck list says
  which references of a running game fail; `/api/status` names the mode. `--checks`, `--workers` and
  `--max-players` are on `serve` and `present`; `browser` stays the default until package 7.
  `tests/test_activity.py` has 7 new tests, with a pool of one worker - the references as the game
  starts, the texts as they come, `internal`, a failing reference in the deck list, a restart with
  texts waiting, `both`'s differences, and over WebSockets a phone's verdict with no window
  evaluating -; its 9 earlier ones pass unchanged in the browser's mode; a Node test has the phone's
  new words. The showcase's three code activities and the KG lecture's three, in its decks built on
  this machine, ran on the branch's server with no presenter window: after the reveal the reference
  matches, another query is `ok` and not the reference's, a syntax error is `syntax`. And
  `texstage serve --checks server` started its workers through `spawn`, and a phone's verdict came
  2 ms after its query. Not done: commits gathered (package 6 decides), the manual (package 8).
- **What package 4's review found, and what changed (2026-11-10):** before package 4 was committed,
  the user asked for a critical review of it - an independent reviewer with experiments, and mine.
  Nine faults, each reproduced but for three points read from the code, all fixed ("Fix all
  nine"), one by changing the rule on `internal` above:
  - *A failure to check stuck to the text:* the known result of a text took `internal` too, so the
    same text from anyone else got it at once and never reached the pool, and a restart sent only
    the waiting texts again - also where the failure was the server's: a pool that broke, a seed
    the pool could not load. After a fallback to `--checks browser` the window did not run the
    references the pool had failed either, so the activity could not be revealed. Now `internal` is
    final only where the pool set the text aside, for ending two of its processes (its outcome says
    `set_aside`; the error kept begins "set aside: "), so a later identical text goes to the pool
    again; a restart makes every other `internal` entry wait again, for the pool or the window (AF
    10.2: a restarted server queues the entries still unchecked again); a build whose preparing
    fails gives its references `internal`, not `error`; and the window runs a reference that is not
    run yet or `internal`.
  - *Ctrl+Break on Windows* reached every process of the console: the workers, which left only
    Ctrl+C to the server, died at once, the check's retry died too, and the text was committed
    `internal`, set aside, while the server shut down. The workers ignore Ctrl+Break now (not
    SIGTERM: multiprocessing ends its daemons with it as the server's process exits), and a death
    whose exit code says it was stopped from outside - Ctrl+Break or a closed console on Windows,
    SIGTERM, SIGHUP or SIGINT elsewhere, as systemd stops the whole group - sets no text aside.
  - *The panel said nothing true in the server's mode:* a pool that broke showed as texts waiting
    (6 of 6), the note was hidden, and before the window's first `activity.work` it said that
    another window evaluates; while the server prepared, it said that the deck gives no reference.
    The host view now says who checks and why the server cannot for an activity (`checks: {mode,
    failing}`); the panel says "The server checks the queries." or why it cannot, counts what could
    not be checked apart from what waits, and has each reference not run yet as such.
  - *Every restart prepared the decks of all games never ended* - a game ends when its deck is
    opened again -, on every process, held until the server stopped: 8 decks of a semester's weeks,
    with seeds of 1.5 MB, took 7.8 s after a restart, ahead of this lecture's, and each worker held
    238 MB instead of 125. A restart skips games idle for longer than 6 hours now - a text sent to
    one prepares its deck -, and opening a stale game's deck lets go of the old build only once the
    new game is there (it had dropped the build and prepared it again).
  - *The tests missed real faults:* five mutants passed them all - no one job for the same text in
    two games, the build let go of while another game ran, a summary over the limits, no commit,
    no drop -, and a push that never came hung the WebSocket tests (starlette's receive waits for
    ever). They fail now, as does each fix undone; the WebSocket tests wait 30 s at most.
  - *A restart with `--checks server` overwrote a game's reference keys* - against 4.11, a game the
    browser's checks began keeps its keys -: where the engines' keys differ, a revealed match turned
    into none. The pool's outcomes fill only references not run yet or failed.
  - *One answer that failed to apply stranded its round:* the inbox was emptied first, and an error
    of the store's or the engine's lost the round's other answers, whose texts waited until a
    restart. Each answer is applied on its own; one that fails comes again with the next round, a
    second later, three times at most.
  - *The browser's mode looked different:* the phone said "being checked" where only the presenter
    window checks; now only where the server does. (The deck list's failing references show in
    every mode, as meant.)
  - *Claims:* the bullet above said that the window makes its evaluator only once it is given jobs;
    `texstage present --checks` went unsaid while a server ran - it says now which mode that server
    has, and that the options are for a server it starts; 4.8 wanted the scripted tests run with the
    pool (4.8 now says what is).

  New tests: 9 in `tests/test_activity.py` (what the server could not check, after a restart and
  after a fallback to the browser's checks; references not run yet; two games of one build; a
  summary over the limits; a text being checked as the server stops; stale games; a game's keys
  kept; an answer applied again), 2 and an assertion in `tests/test_pool.py` (a text set aside says
  so; processes stopped from outside; the signals the workers leave to the server), 1 in
  `tests/test_present.py`, the words of both modes in `web-activity-phone.test.mjs`. 25 mutants -
  the fixes undone one at a time, and the eight of the review - fail them. The review's own
  experiments, run again on the fixed code, show none of the faults: no text stays `internal` after
  a restart or a fallback, a Ctrl+Break leaves the text being checked waiting and the restart pushes
  its verdict, a restart after 8 stale decks prepares none. And a presenter window on the showcase,
  its server in the server's mode, says "The server checks the queries." (for Turtle: "the texts")
  with reference 1's key, as soon as the panel opens on the deck's first slide.
- **What the review of those fixes found, and what changed (package 5a, 2026-11-10):** the same
  two reviewers again, on the fixes alone. Nothing that breaks a lecture whose pool works; six
  faults where something else has failed already, each reproduced, all fixed ("Fix all six"):
  - *A worker that ended before it took its pipe was never seen to die,* on Windows: its end of
    the pipe waits in the server's process to be taken, so the pipe never ends. Where no worker
    can start at all - a broken environment, a virus scanner -, the pool was never broken, the
    panel went on saying that the server checks, and every text waited. This is the pool's
    (package 3), and it undid the panel's note. The watchdog asks a process that is not ready
    whether it has ended: the pool breaks within half a second.
  - *An answer applied again repaired nothing* when the store had failed after the entry changed
    in memory: nothing waited any more, so the retry did nothing - no push to the phone, "1
    waiting" in the panel, the row waiting in the store. An answer that comes again saves, counts
    and pushes the entries that have its outcome already; a result is saved before the shelf
    takes it.
  - *The three tries were gone within milliseconds* while the pool answered: every answer made a
    round, and each round tried again. Each answer to apply again has its time now, a second
    after its last try, and the server sets one wake-up for it.
  - *A stale game's entries waited again at a restart, with nobody to check them:* the restart
    turned them to waiting in every game, while only games not stale are prepared. Both are one
    step now (`Engine.resume_checks`, in every mode): a stale game is left as it is.
  - *An entry that could not be checked stayed so beside the same text's verdict:* a later final
    outcome reaches the text's earlier entries that are not final too (`Shelf.unsure`).
  - *On Linux a stop of the whole process group* still stores the text being checked as
    `internal` - in two runs of three -, not set aside, and the next start checks it; "stays
    waiting" above holds for Windows.

  For these, and for the review's 14 mutants that passed the fixes' tests: 13 more tests, 12 in
  `tests/test_activity.py` and one in `tests/test_pool.py` - the six faults above; a pool that
  breaks during the lecture, said to the windows; a text set aside
  that stays so after a restart; the counts after a restart; a deck built again; a failed
  preparing pushed to a game that keeps its keys; a failed reference that is not the window's
  again; `both`'s phone words; the limit of tries; the server's wake-up; a commit and a push that
  fail. 39 mutants fail the tests now, and the review's own, where their code still exists.

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
- **Package 5, done (2026-11-09), before package 4:** `psutil>=7.2` and `pyoxigraph>=0.5.13,<0.6`
  in `pyproject.toml` - below 0.6, since a new minor version of pyoxigraph may change what the
  keys are made of -; the locks made again (psutil 7.2.2 and pyoxigraph 0.5.13, every other pin
  as it was), `lock_dependencies.py --check` passes, the wheel carries `texstage.checks` and the
  pool and requires both. Done first so that CI runs the pool's tests and the SPARQL and Turtle
  checks' - and since packages 1 to 3, pushed without fresh locks, had failed CI's lock check.
  lecture-tools' lock pairs with a texstage artifact (`requirements/texstage.json`), whose
  requirements it takes: it changes when lecture-tools takes F1 (package 7).

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
  `test_a_turtle_activity`) unchanged with `--checks browser`, and the same checked by the pool in
  tests of their own - with the real engines, and a test engine where a text must crash or sleep
  (as built: the scripted ones script the presenter window's results, which the pool replaces); a
  restart with entries waiting; references prepared at the game's start; `both` writing a
  difference; over WebSockets, `activity.work` giving the lease and no jobs, and the phones getting
  their verdicts without a presenter window. And what package 4's review found (4.5).
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
| 5a | a critical review of what package 4's review changed - it changed the pool again (added 2026-11-10) | its faults reproduced and fixed | 0.5-1 |
| 6 | the load on the laptop, with the phones from a second machine, over Wi-Fi and through the tunnel - F0's runs 1 to 4 (3.4), which were never run there, on F1's code - and what it finds | AF 15.1's budgets with 1,000 phones; F0's final report; whether commits are gathered (4.5) | 2 |
| 7 | into `main`, with `--checks both` as the default; lecture-tools taking it; one lecture with an activity | the lecture's `checks-compare.csv` holds no difference left unexplained; then `server` becomes the default | - |
| 8 | the browser's checks removed (4.10) | the suite passes; the docs and the manual say that the server checks | 1-2 |

About eleven to sixteen working days, and the lecture of package 7 between them.

**Where it stands (2026-11-10):** packages 1 to 5 are built and pushed (`f1-server-checks`,
e5bc4bb), on 2026-11-09 and 2026-11-10. Three critical reviews - an independent reviewer with
experiments, and the author's - found 13 and 11 faults in the pool and 9 in package 4, all fixed
(4.4, 4.5). The table had no reviews: **each package from now on gets one before it is
committed,** about a day with its fixes, and 5a is the one of package 4's fixes - done the same
day: six faults in failure paths, fixed (4.5). What is left waits for hardware and a lecture, not
for code: package 6 needs the laptop, a second machine and
the tunnel on one day, package 7 a lecture with an activity (5).

**Package 6, prepared (2026-11-10):** the branch has what the session needs. `tools/simulate.py`
is F0's, with its burst (`--activity`, `--burst`, `--deadline`, `--runaway`, `--fetch`,
`--join-within`); `tools/load/bundle.py` writes the runs' bundle - a SQL, a SPARQL, a heavier
SPARQL and a Turtle activity, the lecture's own where its folder lies beside the repository, else
stand-ins -; `tools/load/run.py` makes the runs - a fresh server with `--checks server` and a fresh
data folder each, 1,100 phones, a burst of 1,000 entries within 10 s, 30 % distinct - and holds
what the phones measured against AF 15.1's budgets. The session:

1. Both machines: this branch and its environment (`docs/development.md`). The laptop lets the
   port in (8471; Windows asks at the first start).
2. The laptop: `python tools/load/run.py server <scratch>`; then the presenter window on
   `http://localhost:8471/stage` with the deck "Load runs", and PowerPoint or the projector window,
   as in a lecture - through all the runs, each of which has a server of its own (a window that
   does not find the next server by itself is loaded again; not tried yet).
3. The second machine, in the room's Wi-Fi: `python tools/load/run.py phones <scratch> --url
   ws://<the laptop's address>:8471/ws`. It waits for each run's server by itself and says when a
   run is done; then Enter on the laptop starts the next. Ten runs, about a quarter of an hour.
4. The same through the tunnel: the laptop's side with `--tunnel <name> --port <the tunnel's>
   --key <a key of its own>`, the phones' with `--url wss://<the tunnel's host>/ws --key <that
   key>` (with a tunnel the server listens on the laptop only).
5. By hand, as F0's report has it: the presenter window's slide changes (`?timing`) and the
   projector's updates during a run; and a quiz round right after one (run 4 of 3.4), with the
   showcase's deck and `tools/simulate.py` as for the quiz's load test.
6. Both sides write `results-<side>.json` to their scratch folders; the phones' side prints the
   table. Those numbers make F0's report final and decide what 4.5 left open: whether commits
   are gathered.

The dry run on one machine - server, workers and all 1,100 phones on it, 8 cores - says what the
session has to look at, not what it will find: at 1 % of the texts running into their budget,
verdicts came within 0.2 to 1.7 s for 95 % in the first runs (SQL, SPARQL, the heavier seed) and
within 4.9 s in the worst of the repeats, Turtle's within 16 ms; at 3 and 5 % within 12 and 18 s,
as on F0's spike (short checks first is F2's, 4.6 of its plan). Acknowledgements for 95 % ranged from 13 ms to 3.2 s between runs of the same kind, and an
activity's opening and closing reached the last phone after 0.3 to 0.8 s - over their budgets in
some runs. That is this machine, not F1: the spike's server, run in turns with F1's on the same
day and bundle, acknowledged within 175 to 664 ms, F1's within 52 to 239 ms - on the day of F0's
report the spike had 13 to 32 ms. The server's event loop was late by up to 0.7 s at the burst's
peak with no single slow call - the store's saves and commits took 9 ms at most, a round of
verdicts 10 ms -, while the simulator, one process playing every phone, competed for the same
cores. Only phones on a second machine can tell the server's share.

**The laptop alone, and through its tunnel (2026-11-10, evening):** the machine these runs were on
is a laptop itself, and with less else running on it the same ten runs held every budget at 1 %:
acknowledgements for 95 % within 4 to 241 ms, verdicts within 6 ms to 1.8 s, an activity open and
closed on the last phone after 0.2 to 0.3 s; at 3 and 5 % verdicts took 7 and 14 s.

Then the phones went out through the laptop's Cloudflare tunnel and came back (`run.py local
--tunnel`; the servers had a key of their own while they were on the internet): all 1,100 joined
within their 30 s in each of the ten runs, none was refused, no connection was lost, and Cloudflare
gave the 273 KB file from its cache - on 95 % of the phones within 0.6 to 3.5 s of 30.
Acknowledgements for 95 % came within 34 to 316 ms, 660 ms in the run on the heavier seed;
verdicts at 1 % within 35 ms to 2.3 s, at 3 and 5 % within 8 and 16 s; opening and closing
reached the last phone after 0.2 to 0.6 s, three times of twenty just over the half second. So the
tunnel's way holds 1,100 phones; what its numbers still carry is the simulator on the same cores.

Two things the first tries through the tunnel taught, both the simulator's, not the tunnel's.
Every simulated phone made a TLS context of its own, and its file's fetch another: 92 ms each on
Windows, in one process - five joins a second, and with more the openings timed out (of 300
phones joining within 30 s, 208 tries; with 1,100, the join stood still at 70). The phones share
one context now. And a phone whose join the network refuses tries again, as a browser does - up
to five times, counted in the report - where one refusal had ended the run.

Still open for the session: the phones from a second machine over the room's Wi-Fi, which alone
separates the server's share from the simulator's; the presenter window's slide changes and the
projector's updates during a run; a quiz round right after one.

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

As it went, and what is left (2026-11-10; the first proposal had F0 until 2026-11-20 and F1's
packages 1 to 6 from 2026-11-23 to the middle of December):

- **F0's spike:** done on 2026-11-09, measured on one machine; its report is the interim one.
- **F1, packages 1 to 5:** done on 2026-11-09 and 2026-11-10, with their reviews.
- **Package 5a,** the review of package 4's fixes: done on 2026-11-10.
- **Package 6 with F0's runs:** one session on a day the presentation laptop, a second machine
  and the tunnel are free - the lecturer's to name. Everything after waits for it: F1 comes to
  `main` only with its numbers (section 2).
- **Package 7:** lecture-tools takes F1, then the next lecture with an activity after package 6,
  before or after the Christmas break - the lecturer's to name too.
- **Package 8:** right after it.
- **F2's plan:** [activity-framework-plan-f2.md](activity-framework-plan-f2.md), written on
  2026-11-09 ahead of F0's final report, at the lecturer's request; it changes with that report and
  with F1.
