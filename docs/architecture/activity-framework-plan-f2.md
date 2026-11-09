# texstage - the activity framework: F2 (plan)

Status: 2026-11-09, the plan for F2 of [activity-framework-design.md](activity-framework-design.md)
(here **AF**, section 18) - the core and the contract. Written at the lecturer's request before F1
is built and before F0's runs on the presentation laptop: it takes for granted what the plan of F0
and F1 ([activity-framework-plan.md](activity-framework-plan.md), here **P1**) delivers, and changes
where F1 or F0's report ([activity-framework-f0.md](activity-framework-f0.md)) say otherwise.
Nothing of it is built. File references are to `src/texstage/` unless they name another folder.

## 1. In short

- **What F2 delivers:** the activity type rebuilt as AF's core - phases with reopening and pausing,
  entries, checks, groups, pictures, moderation, one panel and one phone screen for every kind -,
  the contract (API 0) and its kit; today's four kinds as two packages in `kinds/`
  (`texstage-kinds-rdf`, `texstage-kinds-sql`); texstage's own `choice`, `number` and `text`; the
  pages' Content-Security-Policy. An activity has one step: steps and points are F3's.
- **Size:** about seven weeks of work, the largest stage. The lectures stay on F1's `main`
  meanwhile.
- **For the lecturer:** the decks build unchanged, the old keys being aliases (AF 8.1). The panel
  and the phone's screen are new, and the same for every kind; the controls are open, close,
  reopen, pause, reveal, reset and the time. Kinds come from `kinds/`, installed as texstage is.
- **Done when** (AF 18): the four kinds and texstage's own pass the kit, and the KG lecture's decks
  give the same groups as with F1.

## 2. What F2 builds on

- **From F1** (P1, 4.2 to 4.10): the pool (`server/pool.py`) with its rules - workers and a spare,
  CPU budgets, the watchdogs, one retry, the students in turns, nothing blocking under its lock;
  the three checks in Python (`checks/`) with their golden fixtures (`tests/fixtures/checks/`); the
  activity type checking on the server, with an index of entries by player and counts kept as they
  change; `--workers` and `--max-players`; the browser's evaluator gone.
- **From F0:** the numbers of its report, and one finding F1 may meet first: texts that run into
  their budget can use up the pool (4.6).
- If F1 ends otherwise than P1 says, this plan follows F1.

## 3. Ground rules

As P1's (P1, 2), and:

- **The branch `f2-core`;** the lectures stay on `main` until F2's test of done holds with the
  lecture's decks and a dry run has passed.
- **One activity type at a time:** F2 replaces F1's on its branch; no server carries both - two
  implementations of one type would cost more than the fallback is worth, and `main` is the
  fallback until the dry run.
- **The contract is API 0:** any package may change it; F4 calls it API 1 (AF 2).
- **The server side first:** packages 1 to 6 are tested without a browser, so that the browser's
  packages build on a core that holds.

## 4. The pieces

### 4.1 Where the code goes

| piece | where | what |
|---|---|---|
| the contract | `activities/kind.py` (new) | `Kind` (API 0); the option types - `File`, `Words`, `Int`, `Number`, `Choice`, `Text`; `Built`, `Prepared`, `Check` (AF 6.3) and an entry; the registry from the entry points `texstage.kinds` |
| the core | `activities/` (new): `phases.py`, `entries.py`, `checks.py`, `reduce.py`, `views.py`, `store.py` | phases and the step, entries, the checks' way through the pool, groups, crowd and tally, pictures and phone states, storage (4.3) |
| the type | `server/activity.py`, rewritten and thin | the content type's hooks (`server/types.py`) handing over to the core; AF 10.4's messages |
| the pool | `server/pool.py` (F1's) | a worker for normalizing; short checks first (4.6) |
| the build | `build/activity.py`, `latex/texactivity.sty` | the core's keys, a kind's recorded for its `build`; named record fields; `deck.json`'s kinds; the aliases (4.4) |
| the browser | `web/play/activity.js`, `web/stage/activity.js`, the panel in `web/stage/presenter.js`, `web/kinds.js` (new) | one phone screen, one box, one panel; a kind's `hint.js` in a Web Worker, `input.js`, `box.js` (4.5) |
| the server's pages | `server/app.py` | a kind's files under `/kinds/<name>/<hash>/`; a policy per page (4.5) |
| texstage's own kinds | `activities/kinds/`: `choice`, `number`, `text` | through the same entry points (4.8) |
| the four kinds | `kinds/texstage-kinds-rdf/`, `kinds/texstage-kinds-sql/` (new packages) | F1's checks moved in, with texts, browser modules and fixtures (4.7) |
| the kit | `activities/kit.py`; `cli.py`: `texstage kinds`, `texstage kinds check` | AF 7.5 (4.9) |
| texts | `web/i18n/en.js`, `de.js`; each kind's `texts/` | the core's new words; a kind's under `kinds.<name>` (AF 7.4) |

Today's type is about 900 lines (`server/activity.py`), its box and agent about 800
(`web/stage/activity.js`), its phone screen 165 (`web/play/activity.js`), its build 195 and its
package 283 (`build/activity.py`, `latex/texactivity.sty`); F2 rewrites all of them, keeping what
works - the crowd graph's layout (`tests/web-activity-layout.test.mjs`), the term cleaning, the
archive's files.

### 4.2 The contract, API 0

- **`Kind`** as AF 7.1 sketches it: `NAME`, `API = 0`, `INPUT` (one of the core's inputs, or the
  kind's own), `REDUCTION` (`groups`, `crowd` or `tally`), `OPTIONS` (one schema for the activity
  and, from F3, its steps), `BUDGET_MS`; `build(options, bodies, files)`,
  `prepare(item, keys, files)`, `normalize(step, entry)`, `check(prepared, step, entry)`.
- **An entry** is what the input sends: a text, the fields or a choice - one small typed object,
  not a dictionary that kinds read differently.
- **A check is validated by the core** before it is stored: its status one of AF 6.3's, a key
  where the status is `ok`, a verdict and a credit between 0 and 1 where the kind judges, a message
  code its texts have, a detail of at most 12 KiB, the parts for `crowd`. A kind that returns
  something else gets `internal` for that entry, and the kit finds it first.
- **The registry:** `[project.entry-points."texstage.kinds"]`; texstage's own kinds through its
  own `pyproject.toml`, which has no entry points yet (only `[project.scripts]`).
- **`deck.json` names the kinds** with package, version and API; a server that lacks one, has
  another API or major version, or an older version than the build's refuses the bundle and says
  which package to install (AF 7.2, `server/bundles.py`).

### 4.3 The core on the server

- **Phases** as AF 5.2 has them: `ready`, `open`, `paused`, `closed`, `revealed`; *Open* on a
  closed step goes on with what is there; a quiz round pauses the open step, and its end resumes
  it; a step's time counts while the server runs, so that a laptop's sleep pauses it; *Reset* gives
  a new epoch. The slides open, close and reveal (AF 8.2), the `slide` hook learning a page's step
  and phase from the records.
- **Entries:** their ids made by the phones and unique per step, so that a resend after a restart
  is recognized; `limit=`, `gap=`, 2,000 characters; `counts=latest|all`; withdrawn by the
  student. Written every 50 ms in one transaction and acknowledged once written (AF 10.2).
- **Checks:** one per step and distinct normalized entry. The event loop merges identical texts;
  a new text goes to the pool's worker for normalizing, a new form to the queue (4.6). Results in
  `checks`, details in `details`; a dead worker's check once more, then `internal` (AF 11); after a
  restart, what was unchecked goes to the pool again.
- **Reductions:** `groups` - by key, counted by students, the largest first, each shown by its most
  frequent text in normalized form (AF 5.1); `crowd` - today's graph, from the fields' parts and
  the lecturer's merges; `tally` - choices counted. At most 10,000 entries and 2,000 distinct forms
  per step; beyond, the panel says so and new texts wait.
- **Pictures:** versioned; the windows fetch them, at most four times a second (`activity.view`).
- **Moderation:** show, hide, merge, unmerge, block - a row each in `moderation`, so that every act
  can be undone and survives a restart. *Approve* and *pick* come with F3 and peer review.
- **Phone states:** the step's own part serialized once per version and sent to every phone; each
  phone's entries and verdicts, small, from the index by player (AF 10.4).
- **Storage:** the tables `entries`, `checks`, `details`, `steps`, `moderation` (AF 10.2), new
  tables through the type's `ROWS`, so that the store creates them (`server/store.py`); `ledger`
  is F3's.
- **Messages:** AF 10.4's, but for `activity.next` and the acts `pick` and `approve` (F3).
- **The archive:** `activity-<id>.csv` with the step and the epoch, `activity-<id>.json` with the
  final picture, the crowd graph's SVG (AF 10.5).

### 4.4 The build and LaTeX

- **`texactivity.sty`** knows the core's keys that F2 uses - `id`, `kind`, `limit`, `counts`,
  `gap`, `time`, `budget`, `feedback`, `projector`, `solution`, `open`, `width`, `height` - and
  records every other key for the kind, which checks them at build (AF 8.1). `\step`, `from=`,
  `points=` and `speed` come with F3.
- **Record lines name their fields** (`activity|id=...|kind=...`), and one module reads them (AF 9).
- **`build/activity.py`** asks the kind: its `build` checks the keys and gives the item, the keys
  and the files; the references are checked by the checker the server uses; `deck.json` gets the
  kinds; the build says how much a phone loads for the deck's kinds.
- **The aliases:** `input=tuple` is `kind=triples`, `input=code, engine=sparql` is
  `kind=sparql-query`, `engine=sql` is `kind=sql-query`, `engine=turtle` is `kind=turtle-graph`
  (AF 17).
- **The KG lecture's frames** - the four activities of 02-RDF, 03-Serialization and 05-SPARQL -
  are copied into the tests as fixtures, since the lecture lives in another repository: they build
  unchanged and give F1's groups.

### 4.5 The browser

- **The phone's one screen** (AF 12): the prompt, the core's input - `code`, `fields`, `choice`,
  `number`, `text` - or the kind's `input.js`, *Send*, the entries and their states. A kind's
  `hint.js` runs in a Web Worker and gets the text 300 ms after the last key, so that a slow hint
  never holds up typing.
- **The box:** the core's views - bars for `groups` and `tally`, the graph for `crowd` with today's
  layout and the lead window that computes it (AF 13), a histogram for numbers -, a group's detail
  drawn by the kind's `box.js`.
- **The panel**, the same for every kind (AF 13): the phase and the timer, the counts - students,
  entries, checked, waiting, unchecked -, the groups with their details and buttons, and a small
  copy of what the projector shows; the controls as buttons and as keys of the presenter window.
- **A kind's files** come from `/kinds/<name>/<hash>/...` - the hash of their contents, cached long,
  compressed once when the server starts - and a phone loads them in the background when it joins
  (AF 7.3); `web/kinds.js` loads them and hands the core a kind's modules.
- **The pages' Content-Security-Policy** (AF 7.3; P1 4.12): one per page, the phone's the
  strictest; the add-in's allows Office.js from Microsoft's CDN, and the pages whose KaTeX and
  `web/shared/live.js` write inline styles allow those; tried in the app's Chromium and in
  PowerPoint before it lands.

### 4.6 Short checks first (new, from F0)

F0's runs on one machine (its report, section 2): with 1 % of the texts running into their budget,
95 % of the verdicts came within 0.9 s; with 3 % within 8.0 s, with 5 % within 15.8 s - the budget
is 3 s. Each runaway text holds a worker for its whole budget, and 30 of them hold six workers
for about 13 s; taking the students in turns does not help when every runaway text is another
student's. Proposed (AF 2):

- **A first slice:** every check gets 0.25 s of CPU time first. One that needs more while other
  texts wait is stopped - SQLite from inside, pyoxigraph by ending its worker - and goes to a second
  queue, which runs only while the first is empty, with the whole budget.
- **A budget of 1 s,** not 2: right queries on a lecture's seed take milliseconds (F0, Q4).
- **The test:** F0's runs with 3 % and 5 % again - 95 % of the other texts' verdicts within 3 s;
  the runaway ones as `timeout` after the burst.

If F1's package 6 meets the problem on the laptop, F1 takes this first (P1 4.4).

### 4.7 The four kinds as packages

- **`kinds/texstage-kinds-rdf/`:** `triples` - input `fields`, reduction `crowd`, `normalize`
  cleaning the terms (control characters, a phone's typographic quotes), the check's parts with
  each field's key and whether it is a literal (AF 6.3, 17); `sparql-query` and `turtle-graph` -
  F1's checks, the hints an undeclared prefix and an unclosed brace or quote. Its dependency:
  pyoxigraph.
- **`kinds/texstage-kinds-sql/`:** `sql-query` - F1's check; the hint a table or a column the seed
  does not have, from the seed's schema in the public item.
- **Each package:** its `pyproject.toml` (version 0.1.0, the entry points, its dependencies), its
  texts (`texts/en.js`, `de.js`), its browser modules (`web/hint.js`, and `box.js` where a detail
  needs more than a table), its fixtures (`tests/`, F1's golden fixtures moved in) and a README.
- **Installed as texstage is:** from source, editable in development (`pip install -e kinds/...`),
  with locked requirements; `requirements/` and `maintenance/lock_dependencies.py` take the kinds'
  dependencies; CI installs both packages and runs their kits; `docs/installation.md` says how.

### 4.8 texstage's own kinds

- **`choice`** - one or several of the options a deck gives (from F3 also an earlier step's
  groups); reduction `tally`; right when the choice is the reference's.
- **`number`** - a number, with a tolerance as its option; a histogram; right within the
  tolerance.
- **`text`** - a short answer, normalized as the quiz's text answers are
  (`scoring.normalize_text`); reduction `groups`.

Their checks run in the pool too: no kind code runs in the server's event loop (AF 2).

### 4.9 The kit

`texstage kinds` lists what is installed - name, package, version, API. `texstage kinds check
<name>` loads the kind and checks its options; runs its fixtures, twice and in both orders, and
the safety fixtures - for SPARQL `SERVICE` in every spelling and the names that are not it
(`?service`, `:service`), for every kind nesting beyond its parser's cap; compares its texts in
English and German; loads its browser modules in Node, with a network that refuses; measures what
a phone loads - a warning above 200 KB compressed, a refusal above 1 MB -; and reports each
fixture's time against the budget (AF 7.5).

### 4.10 Moving the data

When the server loads a game that has today's tables - `contributions`, `results` - their rows
become entries (one step, epoch 0, the ids kept), checks (a status and a key per distinct text)
and details (the summaries). The old tables stay: the store drops nothing (`server/store.py`).
Archives already written stay as they are.

### 4.11 Tests

- **The contract and the kit:** a kind that breaks each rule fails the kit with words that say
  which.
- **The core:** the phases - reopening, pausing for a quiz round, a sleep, a reset, the moves
  idempotent; entries - the limits, a resend, a restart; checks - merging, normalizing, the
  queue's turns and short checks first, the retry; the reductions; the pictures; moderation and
  its undo; the store's new tables and the move of today's data.
- **Over WebSockets:** AF 10.4's messages, a phone's verdict without a presenter window, a phase
  change on every phone.
- **The build and LaTeX:** the core's keys, a kind's keys, the aliases, the record lines,
  `deck.json`'s kinds, a server refusing a bundle whose kind it lacks; the KG lecture's frames.
- **The browser** (Node): the phone screen with each core input, a hint in its worker, the box's
  views, the panel's counts; every page sending its policy.
- **The kinds:** both packages' kits in CI.
- **The load:** F0's runs on F2 (package 11).

### 4.12 The work, in order

| | package | done when | days |
|---|---|---|---|
| 1 | the contract and the registry (4.2) | `texstage kinds` lists texstage's own kinds; a kind that breaks a rule is refused | 2 |
| 2 | the kit (4.9) | a broken kind fails it, each way, with its reason | 2-3 |
| 3 | texstage's own kinds (4.8) | their kits pass | 2 |
| 4 | the core on the server (4.3) and the move of the data (4.10) | the core's tests pass; a store of today's games loads | 6-8 |
| 5 | the pool's additions: normalizing, short checks first (4.6) | F0's 3 % and 5 % runs within the budget for the other texts | 2 |
| 6 | the build and LaTeX (4.4) | the KG frames and the showcase build unchanged | 3-4 |
| 7 | the browser (4.5) | the phone, the box and the panel for every kind, in the app's Chromium | 6-8 |
| 8 | the four kinds as packages (4.7) | their kits pass, F1's golden fixtures among them | 3-4 |
| 9 | the pages' policy (4.5) | every page has one; the phone, the windows, the add-in in PowerPoint work | 1-2 |
| 10 | texts, docs and the manual | the i18n test passes; LA, AF and the manual say what F2 does | 2 |
| 11 | the load and the groups (4.11) | AF 15.1's budgets with 1,000 phones; the KG decks' groups as with F1 | 2 |
| 12 | into `main` after a dry run | the class used it; the archive has it | - |

About seven weeks of work - 31 to 39 days -, and the dry run.

### 4.13 Risks

| risk | what then |
|---|---|
| the size: the type, its windows and its build rewritten at once | F1 stays on `main`; the server side (packages 1 to 6) is tested before the browser's |
| the contract changes as it is cut | it is API 0 (AF 2); the kit and the four kinds' fixtures show what each change breaks |
| the groups differ from F1's | normalizing merges only checks, not groups; the KG frames' test compares with F1's groups |
| the pages' policy breaks the add-in or KaTeX | a policy per page, tried in PowerPoint and Chromium (package 9) |
| separate packages make installing harder (decided, AF 2) | one command for development, CI installing both, `docs/installation.md` |
| moving the data of running games | only between lectures; tested with a copy of a real store |
| the semester ends first | F2's dry run in the summer semester's first lectures |

### 4.14 Not in F2

Steps beyond the one, `from=`, the vote, points and the ledger are F3's; peer review comes later;
a kind of another subject is F4's, and the move of the shared kinds to texstage-plugins comes
after it.

## 5. Calendar

- **F1 first** (P1, 5): its work to the middle of December, then a lecture with `both`.
- **F2:** from January 2027, about seven weeks, to the end of February.
- **F2's dry run:** the summer semester's first lectures with an activity, from April 2027.
