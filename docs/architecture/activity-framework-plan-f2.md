# texstage - the activity framework: F2 (plan)

Status: 2026-11-09, the plan for F2 of [activity-framework-design.md](activity-framework-design.md)
(here **AF**, section 18) - the core and the contract -, reworked after a critical review the same
day. Written at the lecturer's request before F1 is built and before F0's runs on the presentation
laptop: it takes for granted what the plan of F0 and F1
([activity-framework-plan.md](activity-framework-plan.md), here **P1**) delivers, and changes where
F1 or F0's report ([activity-framework-f0.md](activity-framework-f0.md)) say otherwise. Package 1
is built (2026-11-10, on `f2-core`, ahead of F1's last packages - 4.12 says where it stands); nothing
of the server uses it yet. File references are to `src/texstage/` unless they name another folder.

## 1. In short

- **What F2 delivers:** today's four kinds as two packages in `kinds/` (`texstage-kinds-rdf`,
  `texstage-kinds-sql`), the contract (API 0) cut from them, and the activity type rebuilt as AF's
  core around it - phases with reopening and pausing, entries, checks, groups, pictures,
  moderation, one panel and one phone screen for every kind -; texstage's own `choice`, `number`
  and `text`; the kit; the pages' Content-Security-Policy. An activity has one step: steps and
  points are F3's.
- **Size:** about eight weeks of work, the largest stage (4.12).
- **Before it starts:** F1. The five decisions it needed were taken on 2026-11-09 (2.4).
- **For the lecturer:** the decks build unchanged, the old keys being aliases (AF 8.1). The panel
  and the phone's screen are new, and the same for every kind; the controls are open, close,
  reopen, pause, reveal, reset and the time. The kinds are installed where the decks are built and
  where they are served, and reach the lectures with lecture-tools (2.3).
- **Done when** (AF 18): the four kinds and texstage's own pass the kit, and the KG lecture's decks
  give the same groups as with F1.

## 2. What F2 builds on, and what it needs decided

### 2.1 From F1

The pool (`server/pool.py`) with its rules - workers and a spare, CPU budgets, the watchdogs, one
retry, the students in turns, nothing blocking under its lock; the three checks in Python
(`checks/`) with their golden fixtures (`tests/fixtures/checks/`); the activity type checking on
the server, with an index of entries by player and counts kept as they change; `--workers` and
`--max-players`; the browser's evaluator gone (P1, 4.2 to 4.10). If F1 ends otherwise, this plan
follows F1.

### 2.2 From F0

The numbers of its report, and one finding F1 may meet first: texts that run into their budget can
use up the pool (4.6).

### 2.3 Where the lectures run: lecture-tools

The lectures do not run texstage-public: each lecture's `tools/` submodule is lecture-tools, which
carries a copy of texstage of its own (its `pyproject.toml` names itself `texstage`) and installs
it with `pip install -e tools`. On 2026-11-09 the KG lecture's submodule stood at lecture-tools
6388b6b of 2026-10-21, and 47 files of `src/texstage` differed from texstage-public's. So a stage
reaches a lecture when lecture-tools takes it - for F1's lecture with `both` too (P1, 2) -, and F2
has to bring lecture-tools its build, `texactivity.sty`, the kinds and their installation, where
the decks are built as much as where they are served: the build checks the references with the
kinds' checkers, so the authoring machine needs them and pyoxigraph.

### 2.4 The decisions it builds on

Five rows of AF 2 were proposals until the lecturer decided them, as they stood, on 2026-11-09.
F2 builds on each:

| decision (AF 2) | what in F2 depends on it | if it changes |
|---|---|---|
| Python or Rust: Python first | everything | F0's runs on the laptop decide (AF 15.3); a slow piece in Rust changes one package, not the plan |
| the parts of an activity: *step* | the core's and the protocol's names (4.3), the tables (`steps`) | another word, the same structure |
| a step's defaults; the reveal's key `solution=` | the LaTeX keys (4.4), the reveal (4.3) | another key's name; F3's points are unaffected in F2 |
| the sizes on the phones: 200 KB, 1 MB | the kit's measure (4.9) | other numbers in one place |
| short checks first | the queue (4.6), package 4's test of done | the queue as F1 leaves it, and a budget that holds only below about 1 % of runaway texts (F0) |

## 3. Ground rules

As P1's (P1, 2), and:

- **The branch `f2-core`;** F2 comes to `main` when its test of done holds, and to the lectures
  when lecture-tools takes it, after a dry run.
- **The four kinds first:** the contract is cut from today's four kinds (AF 2, "Order of the
  work"), so they are moved behind a provisional contract before the contract is written down -
  not fitted into one afterwards, as the plugin system's kinds were (AF 3.2).
- **One activity type at a time:** F2 replaces F1's on its branch; no server carries both, and
  F1's release stays the fallback until the dry run. Going back after a lecture on F2 loses that
  lecture's entries for F1 - F2 moves today's data forward only (4.10); its archive stays.
- **The contract is API 0:** any package may change it; F4 calls it API 1 (AF 2).
- **The days** are working days of one developer with an assistant, as F0's were; the lectures,
  F0's runs on the laptop and the dry runs set the pace more than the days do.

## 4. The pieces

### 4.1 Where the code goes

| piece | where | what |
|---|---|---|
| the four kinds | `kinds/texstage-kinds-rdf/`, `kinds/texstage-kinds-sql/` (new packages) | F1's checks moved into kind classes, with texts, browser modules and fixtures (4.7) |
| the contract | `activities/kind.py` (new) | `Kind` (API 0); the option types; `Built`, `Prepared`, `Check` (AF 6.3) and an entry; the registry from the entry points `texstage.kinds` (4.2) |
| the core | `activities/` (new): `phases.py`, `entries.py`, `checks.py`, `reduce.py`, `views.py`, `store.py` | phases and the step, entries, the checks' way through the pool, groups, crowd and tally, pictures and phone states, storage (4.3) |
| the type | `server/activity.py`, rewritten and thin | the content type's hooks (`server/types.py`) handing over to the core; AF 10.4's messages |
| the pool | `server/pool.py` (F1's) | a worker for normalizing; short checks first (4.6) |
| the build | `build/activity.py`, `latex/texactivity.sty` | the core's keys, a kind's recorded for its `build`; named record fields; `deck.json`'s kinds; the aliases (4.4) |
| the browser | `web/play/activity.js`, `web/stage/activity.js`, the panel in `web/stage/presenter.js`, `web/host/host.js`, `web/kinds.js` (new) | one phone screen, one box, one panel, the host console's line; a kind's `hint.js` in a Web Worker, `input.js`, `box.js` (4.5) |
| the server's pages | `server/app.py` | a kind's files under `/kinds/<name>/<hash>/`; a policy per page (4.5) |
| texstage's own kinds | `activities/kinds/`: `choice`, `number`, `text` | through the same entry points (4.8) |
| the kit | `activities/kit.py`; `cli.py`: `texstage kinds`, `texstage kinds check` | AF 7.5 (4.9) |
| texts | `web/i18n/en.js`, `de.js`; each kind's `texts/` | the core's new words; a kind's under `kinds.<name>` (AF 7.4) |
| installing | `requirements/`, `maintenance/lock_dependencies.py`, `deploy/Dockerfile`, `.github/workflows/ci.yml`, `docs/installation.md` | the kinds' dependencies locked, the kinds installed, tested and in the image (4.7) |
| the lectures | lecture-tools (its own repository) | its copy of texstage taking F2, its environment installing the kinds (2.3) |

Today's type is about 900 lines (`server/activity.py`), its box and agent about 800
(`web/stage/activity.js`), its phone screen 165 (`web/play/activity.js`), its build 195 and its
package 283 (`build/activity.py`, `latex/texactivity.sty`); F2 rewrites all of them, keeping what
works - the crowd graph's layout (`tests/web-activity-layout.test.mjs`), the term cleaning, the
archive's files.

### 4.2 The contract, cut from the four kinds

- **First the four as classes:** F1's checks become `SqlQuery`, `SparqlQuery`, `TurtleGraph` and
  `Triples`, each with what AF 7.1 sketches - `build`, `prepare`, `normalize`, `check` - behind a
  provisional base class, and F1's golden fixtures pass through them unchanged.
- **Then what they share is the contract** (`activities/kind.py`, API 0): `NAME`, `API = 0`,
  `INPUT` (one of the core's inputs, or the kind's own), `REDUCTION` (`groups`, `crowd` or
  `tally`), `OPTIONS` (one schema for the activity and, from F3, its steps), `BUDGET_MS`. Where the
  four differ, the contract learns: `triples` has fields and `crowd`'s parts, `turtle-graph` a seed
  that is only a prologue, `sparql-query` and `turtle-graph` share a seed's prefixes, `sql-query`
  hints from the seed's schema. And `sql-query`'s `prepare` is not alike on every worker - a seed
  with `random()` or the time -, so F1 runs it on the first worker only, and every worker - the
  first too, which lets go of its run - loads a copy of the database it left (`checks/sql.py`:
  `image()`, `load(image=)`; 2026-11-10): the contract gets an optional copy of what a `prepare`
  made.
- **An entry** is what the input sends: a text, the fields or a choice - one small typed object,
  not a dictionary that kinds read differently.
- **What package 1 built (2026-11-10):** the provisional contract, `activities/kind.py` - `Kind`
  with `build`, `prepare`, `copy`, `normalize` and `check`; `Entry`, `Built`, `Step`, `Prepared`,
  `Check` with AF 6.3's fields and statuses -; `activities/code.py`, what the three kinds of a text
  checked against a seed share; and the four as classes in their packages -
  `kinds/texstage-kinds-sql` (`SqlQuery`) and `kinds/texstage-kinds-rdf` (`SparqlQuery`,
  `TurtleGraph`, `Triples`), each with its `pyproject.toml` and entry points. `tests/test_kinds.py`
  holds them against today: F1's 300 golden fixtures through their checks, byte for byte, and again
  in the other order on the same prepared seeds; a check against the outcome a worker of F1's pool
  sends, the diff with the first reference's rows included; a kind's `build` against the build's
  activity module for 43 records, the refusals' words among them, the bounds themselves and
  which of two faults is said; a tuple's key and literals against the activity type's; the first
  worker's preparing against F1's. What the cleaning does is `tests/test_cleaning.py`'s, each
  case with its result written out. 528 cases after the review.
- **What it left where it is,** because F1 is not in `main` yet and may still change: the three
  checks stay in `checks/` - the classes call them - and move into the packages when F1 has landed;
  the fixtures stay in `tests/fixtures/checks/`; the packages are not installed - the test puts
  their sources on the path -, which package 2's registry needs first. Two small changes to F1's
  code, both without a change in what it does: a tuple's and a text's cleaning moved from
  `server/activity.py` to `checks/cleaning.py`, so that a kind needs nothing of the server; and the
  SPARQL and the Turtle check say where a syntax error is (`at`), beside the words that had it.
  The languages' test, which looks through the server's code for every refusal a phone can get,
  reads `checks/cleaning.py` too (`tests/web-i18n.test.mjs`).
- **What package 1's review found (2026-11-10, fixed on 2026-11-11):** an independent reviewer
  with experiments, and the author's. Nothing differs from F1's server, pool, worker or build -
  the cleaning held against the committed code in 537,712 comparisons, the build for 3,000 random
  records, the checks for every fixture through F1's own worker loop. Ten faults, in the tests,
  the contract's shape and the packaging:
  1. *The cleaning's tests held the code against itself:* since the move, the type's cleaning and
     the kinds' are one function, and seventeen faults put into it passed, twelve of them the
     whole suite. `tests/test_cleaning.py` writes every result out.
  2. *The contract's `copy` left the first worker unlike the others:* it checked on the seed's own
     run, they on the copy, and `SELECT total_changes()` had two keys. F1's first worker loads the
     copy too; the contract says so now, and `first()` does it.
  3. *A test set SQLite's memory cap for the whole test process* - 96 MB for every test after it.
     Loads with an allowance belong in a process of their own; the file checks the cap as it ends.
  4. *A test failed when run alone:* it looked a module up that an earlier test had imported.
  5. *Fourteen more faults passed:* the bounds themselves, an empty word, a seed's file before its
     body, a reference file after the body's, which of two faults is said, a seed's byte order
     mark, `timeout` among the statuses - and one that made a test never end, where it now fails.
  6. *An entry of the wrong type:* a tuple's check raised on a text, a text's check called fields
     the student's error in Python's words, and three characters of one string were three fields.
     A check of an entry that is not of its kind's input raises `TypeError` - the core's fault,
     `internal` -, and fields are a list.
  7. *The shape:* a check's CPU time in milliseconds on the class and in seconds on the step - in
     seconds now, as F1's pool counts, and the references' own ten seconds are `referenced`'s to
     take; `unused` could not give today's warning without its caller - it sees the bodies and the
     default of `fields` now; a kind's options were one dictionary shared by three kinds - fixed
     ones now; `Kind` was not importable from `texstage.activities`; and what was left unsaid: a
     part's `literal` is its text's, not its key's, and `at` counts from 1, the column in
     characters.
  8. *Inherited from F1,* and changed in F1's code here: cleaning a clean text could change it - a
     letter and its accent with a soft hyphen between them were composed only the second time;
     the control characters go first now. `min=` with a superscript two ended the build with
     Python's error, and an Arabic three was taken as 3: ASCII's digits only, in the build's
     module too. A seed that is not UTF-8 says so.
  9. *The packages' wheels had no licence text* - each has `LICENSE` and `NOTICE` now. Their
     dependency on texstage has no lower bound still: texstage has had no version since the
     contract came, so none would tell; a kind's package says what is missing when it is imported,
     and the bound comes with F2's version (package 11).
  10. *Two comments* in `web/engines/turtle.js` pointed at the cleaning's old place.

  The author's and the reviewer's small faults, and those for what the fixes added - 109 in all,
  one at a time: 107 fail the tests now, and two are no faults (a bound written another way; a
  failed reference has no rows to keep).
- **What the four taught, for package 2:**
  - *`normalize` gives an entry, not a string* - a tuple's fields stay fields - *and may refuse*
    (`Unfit`, with the phone's code): a field of 61 characters, a text of none. Today the phone
    hears that at once, in the server's loop; with `normalize` in a worker it waits for one, unless
    the core keeps the bounds that need no kind (a text's length, a field's).
  - *A check carries what stays in its worker:* the canonical form its key is made of - hashing it
    counts against the budget -, the rows the next checks are compared with, and that it ran out of
    memory, which the pool tries once more on a fresh process. The contract needs a place for them
    that is not the check the core stores.
  - *The comparison with the reference is the core's order, not the kind's:* the references are
    checked first and compared with none; the first that gives a result leaves its rows with what
    was prepared (`referenced`).
  - *`prepare` is not alike on every worker* (`copy`, as 4.2 had it already), *and takes what the
    pool allows the worker* - SQLite's own memory. Where there is a copy, the first worker checks
    on it too: what ran the seed counts the seed's changes, what was loaded from a copy does not
    (the review). A seed is read as F1's server reads it: UTF-8, its line ends `\n`, a byte order
    mark kept.
  - *An entry of another input than the kind's is the core's fault,* and so is whatever else a
    kind is handed wrongly: the contract needs to say what a kind may assume, and the core has to
    make `internal` of what it raises.
  - *Budgets are in seconds, and the references have their own* - ten where a student's text has
    two: the sketch's `BUDGET_MS` and one budget for both do not fit F1's pool.
  - *A part's `literal` is its text's:* with loose terms, `true` and `TRUE` are one node, written
    as a literal once. A node is a literal when its label is, and the label is the core's choice.
  - *`at` needs its unit in the contract:* from 1, the column in characters - a phone's strings
    count UTF-16 units, two for an emoji.
  - *Messages are worded on the server,* in the deck's language, and the engines' own - SQLite's,
    Oxigraph's - pass through in English. Codes with arguments (AF 6.3) need a code for "the
    engine says", and `at` apart from it; SQLite gives no place.
  - *Three of the four are one shape* (`code.py`): whether that base is the contract's, a helper
    beside it, or each package's own. With it the engines' table (`engines.py`) is the kinds' -
    a seed's file types, the tokens, what a student's text is called.
  - *What the type does by input is a kind's fact or the core's rule:* ten entries from each
    student or five (`LIMIT`, in the class); a pause of two seconds between entries or five; a new
    entry beside the old ones, the same one refused - which needs its key at once -, or in the old
    one's place.
  - *The keys a kind does not take* are a warning of the build's, so the core knows every key of a
    record (`unused`); `fields` has a default the deck did not write. And a seed's two megabytes
    were the presenter's browser's limit - the reason is gone with F1, the number has to be decided
    anew.
  - *`triples` prepares nothing and runs nothing:* its check is a few string operations. No kind
    code in the server's loop (AF 7.1) sends it through a worker all the same; F0's question of
    what the round trip costs is its question most of all.
- **A check is validated by the core** before it is stored: its status one of AF 6.3's, a key where
  the status is `ok`, a verdict and a credit between 0 and 1 where the kind judges, a message code
  its texts have, a detail of at most 12 KiB, the parts for `crowd`. A kind that returns something
  else gets `internal` for that entry, and the kit finds it first.
- **The registry:** `[project.entry-points."texstage.kinds"]`; texstage's own kinds through its own
  `pyproject.toml`, which has no entry points yet (only `[project.scripts]`).
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
- **Checks:** one per step and distinct normalized entry. The event loop merges identical texts; a
  new text goes to the pool's worker for normalizing, a new form to the queue (4.6). Results in
  `checks`, details in `details`; a dead worker's check once more, then `internal` (AF 11); after a
  restart, what was unchecked goes to the pool again.
- **Reductions:** `groups` - by key, counted by students, the largest first, each shown by its most
  frequent text in normalized form (AF 5.1); `crowd` - today's graph, from the fields' parts and
  the lecturer's merges; `tally` - choices counted. At most 10,000 entries and 2,000 distinct forms
  per step; beyond, the panel says so and new texts wait.
- **Pictures:** versioned; the windows fetch them, at most four times a second (`activity.view`).
- **Moderation:** show, hide, merge, unmerge, block - a row each in `moderation`, so that every act
  can be undone and survives a restart. *Approve* and *pick* come with F3 and peer review.
- **What a phone gets, in two messages:** today every phone's `state` push carries its whole view,
  the activity's part built for each phone. F2 sends the step's own part - its phase, prompt,
  input, time, what `feedback=` shows - as a message of its own, `activity.step`, serialized once
  per version and sent to every phone of the game as the same text (a `Conn` method that pushes
  text already serialized); the phone's own entries and verdicts, small, stay in its `state`, from
  the index by player. The quiz's part of `state` does not change (AF 10.4).
- **The lead window** that lays out the crowd graph (AF 13): today it holds the lease that
  `activity.work` hands out. In F2 the first presenter window that sends `activity.layout` holds
  it, for 15 s and again with each layout it sends; when it goes, the next presenter window that
  sends one takes over; the picture says which window leads.
- **Storage:** the tables `entries`, `checks`, `details`, `steps`, `moderation` (AF 10.2), new
  tables through the type's `ROWS`, so that the store creates them (`server/store.py`); `ledger`
  is F3's.
- **Messages:** AF 10.4's, but for `activity.next` and the acts `pick` and `approve` (F3);
  `activity.work` goes.
- **The archive:** `activity-<id>.csv` with the step and the epoch, `activity-<id>.json` with the
  final picture, the crowd graph's SVG (AF 10.5).

### 4.4 The build and LaTeX

- **`texactivity.sty`** knows the core's keys that F2 uses - `id`, `kind`, `limit`, `counts`,
  `gap`, `time`, `budget`, `feedback`, `projector`, `solution` (the reveal's), `open`, `width`,
  `height` - and records every other key for the kind, which checks them at build
  (AF 8.1). `\step`, `from=`, `points=` and `speed` come with F3.
- **Record lines name their fields** (`activity|id=...|kind=...`), and one module reads them (AF 9).
- **`build/activity.py`** asks the kind: its `build` checks the keys and gives the item, the keys
  and the files; the references are checked by the checker the server uses; `deck.json` gets the
  kinds; the build says how much a phone loads for the deck's kinds.
- **The aliases:** `input=tuple` is `kind=triples`, `input=code, engine=sparql` is
  `kind=sparql-query`, `engine=sql` is `kind=sql-query`, `engine=turtle` is `kind=turtle-graph`
  (AF 17).
- **Where the decks are built:** with lecture-tools' copy (2.3) - so the KG lecture's decks build
  unchanged when lecture-tools has taken F2 and its environment has the kinds (package 11).

### 4.5 The browser

- **The phone's one screen** (AF 12): the prompt, the core's input - `code`, `fields`, `choice`,
  `number`, `text` - or the kind's `input.js`, *Send*, the entries and their states; the step's
  part from `activity.step`, its own from `state` (4.3). A kind's `hint.js` runs in a Web Worker
  and gets the text 300 ms after the last key, so that a slow hint never holds up typing.
- **The box:** the core's views - bars for `groups` and `tally`, the graph for `crowd` with today's
  layout from the lead window (4.3), a histogram for numbers -, a group's detail drawn by the
  kind's `box.js`.
- **The panel**, the same for every kind (AF 13): the phase and the timer, the counts - students,
  entries, checked, waiting, unchecked -, the groups with their details and buttons, and a small
  copy of what the projector shows; the controls as buttons and as keys of the presenter window.
- **The host console** shows the open activity, its phase and its counts (AF 13); today it shows
  nothing of activities.
- **A kind's files** come from `/kinds/<name>/<hash>/...` - the hash of their contents, cached long,
  compressed once when the server starts - and a phone loads them in the background when it joins
  (AF 7.3); `web/kinds.js` loads them and hands the core a kind's modules.
- **The pages' Content-Security-Policy** (AF 7.3; P1 4.12): one per page, the phone's the
  strictest, allowing workers from the server for the hints; the add-in's allows Office.js from
  Microsoft's CDN, and the pages whose KaTeX and `web/shared/live.js` write inline styles allow
  those; tried in the app's Chromium and in PowerPoint before it lands.

### 4.6 Short checks first (decided, from F0)

F0's runs on one machine (its report, section 2): with 1 % of the texts running into their budget,
95 % of the verdicts came within 0.9 s; with 3 % within 8.0 s, with 5 % within 15.8 s - the budget
is 3 s. Each runaway text holds a worker for its whole budget, and 30 of them hold six workers for
about 13 s; taking the students in turns does not help when every runaway text is another
student's. Decided on 2026-11-09 (AF 2):

- **A first slice:** every check gets 0.25 s of CPU time first. One that needs more while other
  texts wait is stopped and goes to a second queue, which runs only while the first is empty, with
  the whole budget.
- **What stopping costs:** SQLite stops a check from inside, for nothing; a SPARQL check that
  pyoxigraph cannot stop costs its worker, and a new one is ready about 0.3 s later (F0, Q4). With
  30 to 50 runaway texts in a burst, ending a worker each time may cost more than it saves, while
  one spare covers one ending at a time. So package 4 measures two ways with F0's runs at 3 and
  5 %: ending workers at the first slice, with two spares; and a lane of its own for long checks -
  at most two workers, which every check that outlasts its first slice moves to on its next turn.
  The one that keeps 95 % of the other texts' verdicts within 3 s stays.
- **A budget of 1 s,** not 2: right queries on a lecture's seed take milliseconds (F0, Q4).

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
- **Installed as texstage is** (AF 7.2): the kinds' dependencies join texstage's locks
  (`requirements/*.in`, made by `maintenance/lock_dependencies.py`); the kinds themselves are
  installed after them with `pip install --no-deps -e kinds/...`, as texstage is with `-e .`,
  since a local package has no hash to lock.
- **Where it must reach:** the image (`deploy/Dockerfile` installs only texstage today: it copies
  `kinds/` and installs both packages), CI (`.github/workflows/ci.yml`: both packages installed,
  their tests and their kits run - the suite's `tests/` alone does not reach them), the installation
  guide (`docs/installation.md`), and lecture-tools (2.3).
- The server refuses a bundle whose kinds are missing (AF 7.2).

### 4.8 texstage's own kinds

- **`choice`** - one or several of the options a deck gives (from F3 also an earlier step's
  groups); reduction `tally`; right when the choice is the reference's.
- **`number`** - a number, with a tolerance as its option; a histogram; right within the
  tolerance.
- **`text`** - a short answer, normalized as the quiz's text answers are
  (`scoring.normalize_text`); reduction `groups`.

They come after the four, as the contract's second test: no seed, other reductions, other views.
Their checks run in the pool too: no kind code runs in the server's event loop (AF 2).

### 4.9 The kit

`texstage kinds` lists what is installed - name, package, version, API. `texstage kinds check
<name>` loads the kind and checks its options; runs its fixtures, twice and in both orders, and the
safety fixtures - for SPARQL `SERVICE` in every spelling and the names that are not it
(`?service`, `:service`), for every kind nesting beyond its parser's cap; compares its texts in
English and German; loads its browser modules in Node, with a network that refuses; measures what a
phone loads - against the sizes of AF 2 -; and reports each fixture's time against the
budget (AF 7.5). Its Python half comes with the contract (package 2), its browser half with the
browser (package 8).

### 4.10 Moving the data

When the server loads a game that has today's tables - `contributions`, `results` - their rows
become entries (one step, epoch 0, the ids kept), checks (a status and a key per distinct text) and
details (the summaries). The old tables stay: the store drops nothing (`server/store.py`). Archives
already written stay as they are. The move goes one way: F1's release, run again on that store,
does not see what F2 stored (3).

### 4.11 Tests

- **The four kinds and the contract:** F1's golden fixtures through the kind classes; a kind that
  breaks each rule fails the kit with words that say which.
- **The core:** the phases - reopening, pausing for a quiz round, a sleep, a reset, the moves
  idempotent; entries - the limits, a resend, a restart; checks - merging, normalizing, the queue's
  turns and short checks first, the retry; the reductions; the pictures; moderation
  and its undo; the lead window's lease; the store's new tables and the move of today's data.
- **Over WebSockets:** AF 10.4's messages, `activity.step` sent once as the same text to every
  phone, a phone's verdict without a presenter window, a phase change on every phone.
- **The build and LaTeX:** the core's keys, a kind's keys, the aliases, the record lines,
  `deck.json`'s kinds, a server refusing a bundle whose kind it lacks; frames of the four kinds'
  shapes, written for the tests as the showcase's are - the KG lecture's own frames stay in its
  repository, which is not public, unless the lecturer wants them in texstage-public's tests.
- **The browser** (Node): the phone screen with each core input and `activity.step`, a hint in its
  worker, the box's views, the panel's counts, the host console's line; every page sending its
  policy.
- **The kinds:** both packages' tests and kits in CI.
- **The lectures:** the KG lecture's decks built with lecture-tools after it has taken F2, their
  groups compared with F1's (package 13).
- **The load:** F0's runs on F2, on the presentation laptop with the phones from a second machine
  (package 13).

### 4.12 The work, in order

| | package | done when | days |
|---|---|---|---|
| 1 | the four kinds as classes, behind a provisional contract (4.2, 4.7) | F1's golden fixtures pass through them | 3 |
| 2 | the contract cut from them (API 0), the registry, the kit's Python half (4.2, 4.9) | `texstage kinds` lists the four; a kind that breaks a rule fails the kit with its reason | 3 |
| 3 | the core, 1: phases, the step, entries, storage, commits every 50 ms, a restart, the move of today's data (4.3, 4.10) | their tests pass; a store of today's games loads | 3-4 |
| 4 | the core, 2: checks and the queue - normalizing, turns, short checks first (4.3, 4.6) | F0's runs at 1, 3 and 5 % against the budget | 2-3 |
| 5 | the core, 3: reductions, pictures, moderation (4.3) | their tests pass, today's crowd graph among them | 2-3 |
| 6 | the core, 4: AF 10.4's messages, `activity.step`, the lead window (4.3) | over WebSockets, without a browser | 2 |
| 7 | the build and LaTeX (4.4) | the test frames and the showcase build unchanged | 3-4 |
| 8 | the browser and the kit's browser half (4.5, 4.9) | the phone, the box, the panel and the host console for the four kinds, in the app's Chromium | 6-8 |
| 9 | texstage's own kinds (4.8) | their kits pass, their views drawn | 2 |
| 10 | the pages' policy (4.5) | every page has one; the phone, the windows, the add-in in PowerPoint work | 1-2 |
| 11 | installing: the locks, the image, CI; lecture-tools taking F2 (4.7, 2.3) | CI green with both packages; the image serves a KG bundle; lecture-tools builds the KG decks | 2-3 |
| 12 | texts, docs and the manual | the i18n test passes; LA, AF and the manual say what F2 does | 2 |
| 13 | the load and the groups (4.11) | AF 15.1's budgets with 1,000 phones on the laptop; the KG decks' groups as with F1 | 2 |
| 14 | into `main` and lecture-tools, after a dry run | the class used it; the archive has it | - |

About eight weeks of work - 33 to 42 days -, and the dry run.

**Where it stands (2026-11-10):** package 1 is built on `f2-core`, which starts from
`f1-server-checks` - F1's packages 6 to 8 were waiting for a second machine and a lecture, not for
code. It rewires nothing: the server, the pool and the build are F1's, and the suite passes as
before. Its review is done - ten faults, fixed (4.2). Three of the fixes change F1's code, for
texts and decks no lecture has met: what a text with a soft hyphen before an accent is cleaned to,
and a number written with other digits than ASCII's, in the build. What F1 still changes reaches
`f2-core` by a merge; the checks' move into the packages waits for that (4.2).

### 4.13 Risks

| risk | what then |
|---|---|
| the size: the type, its windows and its build rewritten at once | F1's release stays the fallback; the four kinds and the server side (packages 1 to 6) are tested before the browser's |
| the contract changes as it is cut | it is API 0 (AF 2); the four kinds come first, and their fixtures show what each change breaks |
| a decision of 2.4 changes later | 2.4's table says what follows; short checks first is measured before it stays (4.6) |
| lecture-tools has drifted from texstage-public (47 files on 2026-11-09) | taking F2 is a package of its own (11), and F1's lecture brings it nearer first |
| the groups differ from F1's | normalizing merges only checks, not groups; package 13 compares them in the lecture's environment |
| the pages' policy breaks the add-in or KaTeX | a policy per page, tried in PowerPoint and Chromium (package 10) |
| separate packages make installing harder (decided, AF 2) | locks for their dependencies, one command for development, the image and CI install both |
| a fallback after a lecture on F2 | F1's release, without that lecture's entries; its archive stays (3, 4.10) |
| the semester ends first | F2's dry run in the summer semester's first lectures |

### 4.14 Not in F2

Steps beyond the one, `from=`, the vote, points and the ledger are F3's; peer review comes later; a
kind of another subject is F4's, and the move of the shared kinds to texstage-plugins comes after
it.

## 5. Calendar

- **First:** F1 (P1, 5) - its work to the middle of December, then a lecture with `both`, which
  needs lecture-tools to take F1.
- **F2:** from January 2027, about eight weeks, into March.
- **F2's dry run:** the summer semester's first lectures with an activity, from April 2027.
