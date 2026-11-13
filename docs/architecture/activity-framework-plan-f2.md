# texstage - the activity framework: F2 (plan)

Status: 2026-11-09, the plan for F2 of [activity-framework-design.md](activity-framework-design.md)
(here **AF**, section 18) - the core and the contract -, reworked after a critical review the same
day. Written at the lecturer's request before F1 is built and before F0's runs on the presentation
laptop: it takes for granted what the plan of F0 and F1
([activity-framework-plan.md](activity-framework-plan.md), here **P1**) delivers, and changes where
F1 or F0's report ([activity-framework-f0.md](activity-framework-f0.md)) say otherwise. Packages 1
to 4 are built (2026-11-10 and 2026-11-11, on `f2-core`, ahead of F1's last packages - 4.12 says
where it stands); of the server, only the pool has changed with them (4.6). File references are to `src/texstage/` unless they name another folder.

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
| the core | `activities/` (new): `phases.py`, `entries.py`, `checks.py`, `reduce.py`, `views.py`, `moderation.py`, `store.py` | phases and the step, entries, the checks' way through the pool, groups, crowd and tally, pictures and phone states, the lecturer's acts, storage (4.3) |
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
  `tally`), `OPTIONS` (one schema for the activity and, from F3, its steps), `BUDGET_S`. Where the
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
- **What package 2 built (2026-11-11):** the contract, API 0 - `activities/kind.py`, no longer
  provisional, and AF 7.1 has it as it is now; `activities/options.py`, the options' types; the
  rules a check must keep (`fault`) and what the core makes of one that breaks them (`validated`:
  `internal`); `Check.sent()`, what leaves the worker. `activities/registry.py` finds the kinds by
  their entry points and says why one cannot be used - its module does not import, its class is no
  kind, its name is not its entry point's, another API, two packages with one name. `activities/kit.py`
  is the kit's Python half, and `texstage kinds` and `texstage kinds check [name ...]` the commands
  (4.9). Each kind's fixtures are beside its module (`tests/*.json`), made of F1's golden fixtures
  by `tests/fixtures/checks/to_kinds.py`, with the safety cases, a setting with references over
  rows that are not ASCII, the kinds' builds and the cases of `triples` - 364 cases and 27 builds
  after the review. `tests/test_contract.py`, `tests/test_kit.py`.
- **What it decided of what the four taught:**
  - *`normalize`* gives an entry and may refuse (`Unfit`, with the phone's code); whether the core
    keeps the bounds that need no kind is package 3's, with the entries.
  - *What stays in the worker* - `canonical`, `rows`, `memory` - are fields of the check that
    `sent()` leaves out; the comparison with the reference stays the core's order (`referenced`).
  - *`copy`* and the first worker: `first()`, as F1's worker does it.
  - *Messages are codes* (AF 6.3, 7.4): a check says `Message(code, args)`, a kind lists its codes
    and their arguments (`MESSAGES`), and `engine` is the code for an engine's own words, cut to
    300 characters. Until the phones say them (package 8), `activities/code.py` words a message as
    F1's catalog does - which is how the golden fixtures still hold. F1's checks carry the codes
    only when a kind asks (`checks/texts.py`: `coded()`); F1's worker gets plain text as before.
  - *The base of three kinds* (`code.py`) is a helper beside the contract, not a part of it.
  - *By input, not by kind:* the pause between entries and whether a new entry stands beside the
    old ones or in the old one's place are the input's rules, the core's (package 3); how many
    entries a student has is the kind's (`LIMIT`).
  - *Options:* typed, and read as the kind asks for them, so that today's order of refusals stays;
    the keys a kind does not take are `Options.unused()`'s. A seed's two megabytes stay until the
    build is rewired (package 7), where the number is decided anew.
  - *Budgets* in seconds; the references' own is `referenced`'s argument, the pool's to give.
  - *`triples` through a worker:* package 4 measures it, with the queue.
- **What package 2 pulled forward:** the registry finds a kind by its entry point, which only an
  installed package has - so the kinds are installed from here on: `docs/development.md`, CI (which
  runs `texstage kinds check` too) and the image (`deploy/Dockerfile`) install both packages after
  texstage, without dependencies of their own to lock - pyoxigraph is texstage's since F1. The rest
  of installing - `docs/installation.md`, lecture-tools - stays package 11's.
- **What package 2's review found (2026-11-11, fixed the same day):** an independent reviewer with
  experiments, and the author's. F1 is untouched in effect - the kinds give what F1's worker gives
  for 4,500 garbled texts, the options what today's build makes of 6,000 random records.
  Thirteen faults:
  1. *A result over text that is not ASCII became `internal`:* the rule measured a detail's JSON
     with every such letter escaped, six times its length - twenty rows of Cyrillic, umlauts or
     emoji were over 12 KiB, and a right answer would never have been graded. It is measured as it
     is sent now; a fixture of each code kind has such rows, with references.
  2. *The kit ignored a check that failed the second time:* a check that raised or broke a rule on
     its second run, in the other order, was not compared. It is.
  3. *`texstage kinds check` passed when nothing was checked* - no kind installed -, so that the
     image's job in CI could be green without the kinds; and a package whose import leaves the
     process took the command with it. Nothing to check fails now; what a package does when it is
     imported is its kind's reason.
  4. *`fault` raised* where it promises a reason - a message's code that is no text, a detail
     nested without end, a kind whose tables are none. It never raises now, and neither does
     `validated`.
  5. *It passed what a phone cannot read:* `NaN` and infinity, whole numbers beyond 2^53, half of a
     surrogate pair in a key or a message.
  6. *A syntax error's column was a text, its line a number* - both are numbers now, in F1's two
     checks too, whose words are the same.
  7. *The kit, smaller:* a `normalize` that raised anything but `Unfit` ended the kit - it fails its
     case now; malformed fixture files ended it or were passed over - each is said, a key twice in
     a table and a file for a kind that is not installed among them; a tuple in a detail was held
     against the list a case pins; a check that never came back was waited for - it is given up
     after 30 s; no fixture had a reference; the kit never called `build` - fixtures have builds
     now, what a kind makes of a deck's keys or the words it refuses them with.
  8. *The registry, smaller:* a kind whose engine's library is not installed was listed as usable -
     a kind of an engine imports it when it is made, and cannot be made without; `API = False`
     passed as 0; a name twice in one package gave two kinds; what was found could be changed.
  9. *The texts that carry their codes could not be pickled or copied* - they can; and nothing
     held that the codes end with the check that asked for them.
  10. *texstage's source archive* had the image's file, which copies `kinds/`, and no `kinds/` -
      it has them now (`MANIFEST.in`).
  11. *43 of the reviewer's 76 small faults passed the tests:* a credit below 0, a place of three
      numbers, the kit's own failure lost, and others - each has its test now.
  12. *Seven sentences* of docstrings, the development guide, the design's 7.1 and this plan said
      what the code does not.
  13. *The keys a kind does not take* missed a seed given in the body when the record had no such
      key at all.

  One fault of F1's own came with the first: its server measures a result's summary the same
  way, and drops the table of a group whose rows are mostly not ASCII (`server/activity.py`); it
  is F1's to fix, on its branch.
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

The first part, as built (package 3: `activities/phases.py`, `entries.py`, `store.py`) and as it is
after its review - fourteen findings, fixed -, and what it settled:

- **The step** of an activity that writes none out is named `main`.
- **A step's time** is counted by the moves and by a tick the server gives a few times a second,
  each taking off what passed since the last. More than 5 s between two of them means the server
  did not run - a sleep, or an event loop that stood still: the step is paused (by `sleep`), nothing
  is taken off, and the lecturer resumes it; a round that opens or ends after such a gap leaves it
  so. A restart is such a time as well: a step that was open with a time is paused when the server
  starts again. A step without a time stays open through both. A running time is saved every 5 s.
  A clock that is set back takes nothing off - the server's time is the wall clock's -, and one set
  forward by more than 5 s is a sleep.
- **Who paused** a step is kept (`lecturer`, `quiz`, `sleep`): a round's end resumes only what a
  round paused; the lecturer's *Resume* - and *Open*, on a paused step, with a time if one is given
  - resumes any.
- **No step runs beside a quiz round** (the review): the core remembers that a round runs - the
  engine says so, when the server starts again too -, and a step that is opened, resumed or paged
  to meanwhile is paused by the round and starts at its end.
- **The moves** give the rows they changed, and none when repeated - but *more time*, which adds
  each time it is asked for (the reply cache keeps a message sent twice from adding twice).
  Refused, with a code: opening a revealed step (`revealed`), pausing, resuming or timing one that
  does not run (`closed`), a time that is none (`time`), a name that is no step's (`invalid`). A
  refused move may have changed rows all the same - the time ran out as the lecturer pressed
  *Pause* -: the refusal has them, and package 6 pushes them as after any move (the review: they
  were lost, and no later tick said them). *Reveal* takes a step in any phase, a ready one too.
- **The current step** - the one the phones show - is the one that runs, else the one that was
  opened or revealed last: each such move gives the step the game's next turn (`seq`). A reset
  leaves it the current one (the review: by the time it last moved, a reset gave the phones an older
  activity's reveal, and two steps that moved in one millisecond changed places at a restart).
- **The slides** give the core, for the old and the new page, the steps each shows and what the page
  is of its step - `open` or `revealed` (package 7 records it): a step whose pages go closes; a ready
  one opens when a page of its comes that is marked open; a page marked revealed reveals its step
  if it was opened - paging back onto the reveal of a step nobody answered reveals nothing, and
  after a reset the question's page opens it again. What a page asks is looked at before anything
  changes.
- **Entries:** an id is 8 to 40 letters, digits, `-` and `_`; one the step has - in any epoch - is
  the entry sent again, and gets the entry that is there, whatever the phase is now. Then, in this
  order: `closed` or `paused`, `blocked`, `too-fast`, `too-many`, `full` (10,000 in an epoch), and
  the input's shape - `text`, `field`, `too-long`; a text with half a surrogate pair, which no
  store takes, is refused. The step is asked as it is after a tick: who takes an entry ticks first.
  A clock set back asks no gap. Entering gives the entry and the earlier ones it replaced, for the
  checks' queue and the groups.
- **The limit:** with `counts=latest` every entry a student sent counts. With `counts=all` those
  count that are in or hidden - what the lecturer hid gives no place back, and is not taken a
  second time -, one taken back gives its place back, and a student sends at most three times the
  limit in all, so that nobody fills a step's 10,000 by sending and taking back (F1 had both holes).
  `counts=all` refuses a student's same input twice (`duplicate`) as it was typed; inputs that only
  normalize alike are package 4's.
- **Hide and show** are the entries' own moves (moderation, package 5, calls them): only what is in
  is hidden, only what is hidden is shown - and where the latest counts and the student has sent
  another since, the one shown again is replaced by it, so that no student counts twice (package 5's
  review: nor when both were hidden and the earlier one was shown first - the later one, shown,
  replaces it; `show` gives the entries that changed).
- **Storage:** `steps`, `entries`, `checks`, `details`; `moderation` comes with package 5. Beyond
  AF 10.2's columns: a step's `paused_by` and `seq`, a check's `parts` (the crowd graph's, which a
  restart needs) and `aside` (a text set aside). Until the type is the core's (package 6),
  `store.create` makes the tables as the server's store would; the type then hands `ROWS` over for
  the tables alone - the core's rows are written by its writer and read by `store.load`, never by
  the server's store, which replaces a row it saves again (it moves to the table's end) and reads a
  flag as a number. A column that a file of an earlier version lacks is read as the row's default.
- **The writer** writes a row as it is at the commit and updates it in place, so that the entries
  are read back in the order they came. It uses the store's connection, in a savepoint of its own:
  a commit of its that fails takes back what it wrote, not what the engine left uncommitted there (a
  hook that saves and then refuses does). A commit the database refuses writes nothing,
  acknowledges nothing and is tried again, each time after twice as long, up to 2 s. A row that no
  commit can take - a fault of the core's, since the contract keeps such values out of a check - is
  set aside and told (`lost`), and what waited for it is not acknowledged; the rows after it are
  written. Cancelled, the writer writes what is left.
- **The move** (4.10): the entries, a check per distinct input with a verdict, the details, each
  activity's phase, the activity the phones showed as the current step. Left behind: F1's words for
  an error (a check has a status and a key), and the crowd graph's merges, hidden and approved terms
  and minimum - they are moderation's, and move with package 5.

Left for the packages that follow, from the review:

- **Package 4:** an entry is unchecked while its step has no check for its norm - moved entries
  have a norm and may have no check, so an empty norm is not the test. An entry that the kind's
  `normalize` refuses has been taken by then, and with `counts=latest` has replaced the student's
  earlier one: it needs a verdict of its own - proposed: a check that is `invalid` with the
  refusal's code, under the norm of the input as it was sent. The 2,000 characters are measured as
  sent, before any cleaning.
- **Package 6:** the server ticks every game's steps a few times a second and before it takes an
  entry; it checks that an activity, a step and a player are the deck's and the game's before it
  asks the core; it pushes what a refusal changed; and while the writer's commits fail, it says so
  in the panel - the entries wait unacknowledged, and the phones send them again.

The second part, as built (package 4: `activities/checks.py`, `server/normalizer.py`, `server/pool.py`)
and as it is after its review - twelve findings, fixed:

- **The core's checks** (`activities/checks.py`) say what is to be done and take what the workers
  answer; they run nothing, and call no pool: package 6 hands their jobs to it. A text the step has
  not seen is a job for the normalizing process, entries with the same text waiting for that one; a
  normalized form the step has not seen is a job for the pool, once, entries of the same form waiting
  for that one check; a check that no entry waits for any more - replaced, taken back - is a job to
  take it out of the queue. An entry that is hidden still waits: it may be shown again.
- **What normalize refuses** is a check of its own, as proposed above: `invalid`, the refusal's code
  as its message, under the hash of the input as it was sent. It is kept in memory and not stored -
  asking the kind again costs nothing - and is no form of the step's.
- **What could not be normalized at all** - the kind is not installed, its normalize raised or took
  too long, the process ended - is not the student's (the review: it was stored as their `invalid`
  text for good): the entries count as unchecked, and the same text sent again, or a restart, asks
  again.
- **An `internal` check** that is not set aside is not stored: its entries count as unchecked, the
  same text sent again is checked again, and a restart asks for it again. Set aside, it is stored
  and final.
- **A step takes 2,000 distinct forms** - those that have a check, are being checked, or failed and
  are still waited for; beyond, a new form waits unchecked, the counts say the step is full, and the
  form is asked for as soon as there is room (the review: it never was, and refused texts and forms
  nobody waited for used the room up). The cap is the step's, not an epoch's: a reset keeps the
  checks, and so the forms. The counts for the panel - waiting, unchecked, forms, full - are of the
  step's epoch and of the entries that are in.
- **A check asked for twice** - its only entry left, the pool had begun it, the text came again - is
  one check: the second answer changes nothing.
- **After a restart** the checks and details are the tables'; a text whose entry has a check is
  known at once; an entry without one goes to normalize again - a form is not stored, only its hash -
  and is checked as a new one is.
- **The pool normalizes** (`pool.normalize`) on a process of its own (`server/normalizer.py`): the
  kind's `normalize`, found by the kind's name in the registry, one input at a time. A process that
  ends is replaced and its input tried again, three times in all; an input that takes more than 5 s
  ends its process and is an error, never the student's; a process that ends before it is ready is
  seen on Windows too, where its pipe does not tell (the review: every text after it waited for
  ever). `pool.withdraw` says that one who asked for a check waits no more: once nobody does - the
  pool counts who asked, two games of a deck share a check - and the check is not being made, it
  leaves the queue.
- **In the pool,** after the review: the long checks leave one process to what comes meanwhile; a
  long check's retry waits its turn among the long ones; a slice that ends when its activity cannot
  be checked any more - the pool broke, its seed failed - is `internal`, not the text's timeout.
- **Short checks first** is in the pool as 4.6 decided it; the budget is 1 s, the kinds' default with
  it.
- **Not yet:** the pool's workers still check with F1's engines (`texstage.checks`), as F1's type asks
  them to; that they prepare and check through the kinds - `prepare`, `copy`, `check`, each check held
  against the contract's rules - comes with the type's rewiring (package 6), which is where the core's
  jobs meet the pool.

The third part, as built (package 5: `activities/reduce.py`, `views.py`, `moderation.py`, and the table
`moderation` in `store.py`) and as it is after its review - twenty findings, fixed:

- **What counts** in a reduction is an entry that is in, of the step's epoch, with a check. The
  reductions are kept as the entries and their checks change: whoever changes an entry says which
  (`touch`), and the reduction looks for itself at what the entry is now - told twice, nothing counts
  twice. A picture goes through a step's groups and their distinct texts, not through its entries
  (AF 10.2): with 10,000 entries in a step it is made in 0.4 to 7 ms on the development machine -
  2,000 results; one group of 2,000 texts that do not parse, each with its own message; 10,000 texts
  that normalize refused; a crowd graph of 10,000 triples.
- **Groups:** by the check's key, and by its status where the check is no result. A group's id, as
  the pictures and the acts name it, is 16 hexadecimal digits of a hash of both (`store.gid`): a key
  may be any text of up to 4,096 characters - a short answer's among them, which may read `invalid`.
  Counted by students; the largest first, among as many a result before what is none, then by key.
  The projector gets 8 groups and the panel 50, as F1's; the others are counted.
- **What a group is shown by** is the text that most of its entries have, in the form the kind's
  normalize gave it; among as many, the one whose first entry came first. For that a check keeps its
  normalized input (`form`, a new column of `checks`; package 4 dropped it once the check was made).
  What normalize refused has none: such a group shows its status alone. A moved check has the text
  as F1 cleaned it, which is what F1 showed - its comments with it. As package 5 was built, the
  kinds' normalize took off the spaces at the ends of the lines and no more, as F1's cleaning did,
  and a group showed a text's comments (the review: this plan and the code's own words said
  otherwise, and the tests showed it with a normalize of their own). **Since 2026-11-12 the three
  kinds of a text take its comments out** (4.7), as AF 5.1 wants: no name in a comment reaches the
  class. It changes which texts are checked as one, not their groups.
- **Nothing of the reference before the reveal:** the projector's picture marks no group and has no
  verdict and no solution until then - and of a group's detail not what the kind says there of the
  reference, its comparison (`diff`: none missing, none more, marks the right group). The contract
  names that part (`kind.COMPARED`), and the core takes it out for the projector until the reveal
  (the review: it went out whole, as F1's does - no window draws it today).
- **The panel's picture has more:** the counts - entries, students, checked, waiting, unchecked, the
  step's forms and whether it is full -; an entry of each group, for its buttons; what is hidden,
  marked; what the checks of a group that is no result said, each message once, the first five in
  the order their entries came; and the entries whose text was set aside, as a group of their own -
  never graded, never on the projector. A group that is no result is not judged by a verdict that
  one of its checks has: only a result's group takes the kind's own.
- **The crowd graph** is F1's: the same nodes, edges and order, `more`, the positions, the panel's
  terms. The tests hold it against F1's own function (`server/activity.py`: `_crowd`) with the same
  entries and the same acts - twelve random games, two and three fields, both windows - and against
  a game moved from one of F1's stores. One difference, on purpose: a term is written as most of the
  entries that count write it - F1 counted the ones taken back and hidden too -, among as many as
  the entry that came first wrote it, whichever was checked first; a node that nobody writes any
  more keeps its first writing. An entry that is no triple - a field longer than a term may be,
  which F1 refused when it came - counts as an entry, is in no graph, and the panel says how many
  there are.
- **The tally** is the deck's choices in its order, one nobody made among them - which can be
  hidden like any other -, then the largest of the other groups, as many as a window lists. What an
  item calls its choices, and an entry of several, come with the kind (package 9).
- **A step's setup** (`Setup.of`) reads the item's `min` and `review` for a crowd graph and its
  `options` for a tally only: with another reduction these names are the kind's own.
- **The references:** the pool's results of them are handed to the core (`refer`; package 6) and kept
  in memory - a restarted server checks its references again. A check's verdict is the kind's own;
  else the core's, by the references' keys; none while no reference has a result, and never for an
  `internal` check. The panel has the references' groups at once, the projector at the reveal; with
  `solution=show` both pictures then have the references' texts and details, with `mark` neither.
- **Pictures:** one per window - `display` (the projector and the box), `stage` (the panel) -, made
  once per version. `projector=count` gives the projector the counts alone until the step is closed,
  `hidden` nothing until the reveal. A step's version goes up with everything a picture shows - an
  entry, a check, the phase, an act, a reference, and the checks' counts, which a check that comes
  back for a text nobody waits for changes without changing an entry -, the positions of a crowd
  graph have a counter of their own, and the windows are told at most every 250 ms (`told`, which
  the server asks with its tick). Positions are taken for a crowd graph only, of the terms its
  entries have as a node, and are not stored.
- **Moderation:** the acts `hide` (a group, a crowd graph's term, an entry), `approve`, `merge`,
  `unmerge`, `show`, `min` and `block`; `off` takes a `hide`, an `approve` or a `block` back. Beyond
  this section's list: `approve` and `min`, which today's crowd graph has (F3's *Approve* is of
  entries, for peer review). An act that changes nothing makes no row. A row has the act's number
  in its game, the step's epoch, the act, `target` (a group's id, a term's key), `role`, `entry`,
  `onto`, `off`, `value` (the minimum; of a block the entries it hid and those it found hidden),
  when, and `undone` - AF 10.2's `group`, `into` and `on` are SQL's own words; the message
  (package 6) can keep them. A game takes 5,000 acts that hold, and 20,000 rows.
- **Undo** marks an act, and what holds is read again from the acts that are left, in their order.
  By the act's number, or the last one; the panel's picture has the last ten. The entries are then
  as the acts that hold say, each from what the first act about it found: one that an act showed
  again was hidden before, with or without an act - a moved game's hidden entries have none. An
  undo that would leave two terms merged into each other is refused; merges that a stored game has
  going round already are skipped, and keep no other act from being undone.
- **Where the latest counts, a student has one entry in:** shown again, an entry is replaced by a
  later one of the student's that is in - and replaces an earlier one (the review: two hidden
  entries of a student, both shown again, were both in).
- **Through a reset** the acts on groups and terms stay, as the checks do - that two terms are one,
  or that a word is not to be shown, is as true of the next epoch. The acts on entries are those
  entries': after a reset the panel does not list them, no undo takes them, and no undo changes an
  entry of the earlier epoch. The group whose detail is on the projector is its epoch's - after a
  reset none is, though the same result comes again.
- **A block** hides what its student has in the step. While the student is blocked, their entries
  stay hidden: no undo brings one back, and showing one is refused until the student is unblocked.
  Taken back with `off`, the entries stay hidden; the block undone, they are as before it. An
  unblock is undone by blocking again - an act of its own, which hides what the student sent
  meanwhile. Who is blocked is read from the acts (`blocked`) - no row and no picture names a
  student, a block names an entry; so the acts are loaded after the entries, and loading them
  before is an error, not a game in which nobody is blocked.
- **The move** (4.10) makes acts of what F1 kept in an activity's state: the crowd graph's minimum
  - unless it is the deck's own, which F1 wrote into every graph's state; the caller hands the
  deck's items over -, merges, hidden and approved terms, and the result that was shown. What F1
  never wrote makes no act and ends no move: a minimum beyond 1,000, a term twice, a merge that
  leads back to its own term, a state that is no table. Who was blocked in F1 is the server's (a
  player's `muted`), and stays there.

Left for the packages that follow:

- **Package 6:**
  - It loads a game in this order: the move, if the game is F1's - before any act is in memory, since
    the moved acts are numbered after the table's -, the steps, the entries, the checks, the acts,
    then the reductions (`Reduced.load`) and the references (`refer`), without which no check has a
    verdict.
  - It tells the reductions every entry that changed (`touch`): what `enter` gives with what it
    replaced, `withdraw`, what `normalized`, `unnormalized` and `checked` give, and an act's or an
    undo's entries; it hands the acts' jobs to the pool; it tells the pictures every move (`moved`).
    Forgotten, nothing fails - the counts are stale.
  - It asks both who is blocked: `moderation.blocked` and the player's `muted`, when it takes an
    entry (`enter(blocked=...)`).
  - It gives an undo the step of the act; it checks who may send positions (the lead window's
    lease); it asks `told` with its tick.
  - The archive's files - F1's `graph_svg` draws the core's crowd picture as it is -; the phones'
    states.
  - A picture's version starts anew with the server: a window fetches when it is another, not a
    higher one.
- **Package 8:** the panel's 50 groups come with their details, up to 12 KiB each, as F1's - about
  0.6 MB when all are full.
- **The kinds' normalize takes comments out** - done on 2026-11-12, before package 6 (4.7).

The fourth part, as built (package 6: `activities/play.py`, `server/activities.py`, and what
`server/worker.py`, `pool.py`, `types.py`, `game.py` and `app.py` have of it) and as it is after
its review - five faults and five doubts, fixed:

- **Beside F1's type, not in its place.** 3 says that no server carries both, and none does: a
  server runs one of the two (`types.py`: `use`; `ServerConfig.activities`, `f1` or `core`), and
  F1's is the one it runs unless it is told otherwise. The core's type is `server/activities.py` -
  `server/activity.py` is F1's still, untouched -, so that `main` keeps its lectures' type while
  the windows and the build learn the core's (packages 7 and 8); F1's tests pass as before. Taking
  F1's type out, and the switch with it, is a step of its own, for when the browser speaks AF
  10.4. No command line option chooses the core yet: without its windows nobody could use it.
- **The pool's processes prepare and check through the kinds** (`worker.py`: `_OfKind`): an
  activity whose module is named `kind:<name>` has the kind's `prepare`, its `copy` for every
  process, the first too, its references, each compared with none, and its checks - a check's
  outcome is `Check.sent()`, held against the contract's rules first (`validated`): one that
  breaks them, and whatever a kind's check raises, is `internal`. The pool's own queue did not
  change: a job's text is the normalized input as JSON, its seed `{item, keys, files}`. F1's
  engines run beside, for F1's type.
- **One game's core as one** (`activities/play.py`: `Play`): whoever changes an entry tells the
  reductions, whoever moves a step the pictures, and every job a part asks for goes out at once.
  An entry is taken in its step as it is after a tick. `Part` is what a game reads of an activity
  of its deck: the item, the keys, the kind - for a deck built before kinds are named (package 7),
  the one of its `input` and `engine` -, the step's setup, and `feedback=`.
- **`feedback=`** (AF 5.3) is read here: `none` - received, no more -, `status` - the default: it
  runs, or the error with its line -, `verdict`, `full` - with what the kind's detail says of the
  reference. At the reveal every phone has its verdict. An `internal` check tells a phone nothing
  but that the entry is unchecked; an entry the lecturer hid is the student's as before.
- **The messages** are AF 10.4's, and `activity.undo {activity, act?}` for 13's "every moderation
  can be undone". `activity.moderate` keeps the design's names - `group`, `into`, `on` -, the
  rows' are `target`, `onto`, `off`. `activity.open` and `activity.time` take seconds. A step
  other than `main` is refused: steps are F3's.
- **An entry is acknowledged once it is written** (AF 10.1): the hook's reply carries what is to
  be called then (`types.WRITTEN`), the app answers - and remembers the answer for a message sent
  again - only when the writer has committed the row. Until then the same message is asked
  again, and gets the entry that is there. No session is stored for an entry: the engine saved
  the game and committed for every phone's message.
- **What the windows are told** is the type's part of the game's stage - under a name of its own,
  `activities`, so that F1's `activity` stays as F1 left it, for the move and for going back -:
  the current activity, and of each step the game's core knows - one that moved, or was looked
  at - its phase, epoch, time, and the version
  the windows are told, at most four times a second. A time that runs is told once, with when it
  was read; told with every tick, every window and phone would get its state ten times a second.
- **`activity.step`:** the step's own part of a phone's state - phase, kind, input, limit,
  `feedback`, time, the prompt, the fields and what they offer, the tokens - is one text per
  game, serialized once and sent to every phone as it is (`Conn.text`), at once when a step
  moves, else at most once a second: what a field offers grows with the graph. A phone that
  comes gets what the others have. A phone's own entries stay in its `state`.
- **The tick** (`Engine.pulse`, every 100 ms): every game's steps - a time that ran out closes
  its step, a sleep pauses it -, a quiz round that began or ended, what the windows and the
  phones are to be told, and the pool's answers that nobody woke the engine for. It stores no
  session; a step's row goes to the writer as its time runs out, and every 5 s while it runs.
  One game's fault in it is that game's: the others' time goes on, and the log says it once.
- **The lead window:** the first presenter window that sends `activity.layout` leads for 15 s
  and again with each layout; another window's layout is not taken, and it is told so (`lead`);
  `activity.view` says whether the asking window leads. A window that goes leads no more, and
  a layout that is none takes no lease.
- **The references are a game's whenever they come** (the review: the pool prepares a deck as
  its game comes, long before anybody shows an activity - and a game got them only if it had
  its core by then, so a deck's first game had no verdicts): a game's core takes what is known
  of its deck as it is made, and what comes later as it comes - and then every phone gets its
  state again, since a verdict may be new.
- **A refused message that found a step changed** - its time ran out as a phone sent, or as the
  lecturer pressed *Pause* - tells the phones at once and the windows with the next tick: the
  engine and the app tell nobody after a refusal (the review: the panel showed an open step at
  0:00 until something else happened).
- **What is not prepared says so:** a seed that does not load, a kind that is not installed, a
  pool that is broken - in the game's host view, as F1's, and in the panel's picture
  (`failed`). A job the pool does not take - it is closed, there is none - is answered as one
  it could not do: its entries are unchecked, never waiting for ever, and the same text sent
  again is asked for again. A game that ends takes what it still waited for out of the queue.
- **F1's games move one at a time** when the core's type first starts on their store: one that
  does not move takes none of the others' rows back with it.
- **A restart:** the type's book begins once the engine has its games - the core's tables, the
  writer, then per game the move if it is F1's, the steps, entries, checks and acts
  (`Play.load`); the references are checked again as the deck is prepared, and what was unchecked
  is asked for once the pool runs.
- **The panel says when nothing is written:** `activity.view` in the presenter window has the
  writer's failures and its last error while there is one.
- **The archive:** `activity-<id>.csv` with step and epoch, without names; the final picture as
  JSON; a crowd graph as SVG, drawn by F1's `graph_svg` from the core's picture.
- **What the engine asks a type besides** (`types.py`): `begin`, `deck`, `resume`, `shown` - a
  slide change with the game -, `pulse`, a book's `apply` - the pool's answers - and `release`,
  each only where a type has it.

Left after package 6:

- **The slides reveal nothing yet:** until the build records what a page is of its step
  (package 7), every page of an activity is its question's - it opens and closes.
- **The deck list's failed references** are F1's still (`app.py`); the panel's picture has the
  core's.
- **Not there, and not F2's:** `activity.next`, the acts `pick` and `approve` (F3).
- **No load run yet** with the core's type: package 13's.

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

**Measured and decided** (package 4, 2026-11-11), with the load runs (`tools/load/run.py local`: 1,100
phones, a burst of 1,000 SPARQL texts in 10 s, 30 % of them distinct) on one machine of 8 cores - 6
workers, and the spares -, the budget at 1 s. The runaway text of the runs is one that nothing but the watchdog stops,
so each ends a worker at its slice and another at its budget. The verdicts of the texts that do not
run away - the runs now say them apart -, 95 % and the slowest, in ms:

| the way | 3 % runaway | 5 % runaway | a runaway text's own verdict, at most |
|---|---|---|---|
| no slice (F1's queue) | 2,337 / 2,986 | 4,953 / 7,589 | 4.1 s / 8.8 s |
| a slice; the long checks only while no other text waits; one spare | 604 / 694 | 1,761 / 2,549 | 8.0 s / 14.4 s |
| ... two spares | 367 / 531 and 397 / 552 | 1,192 / 1,962 and 1,145 / 2,016 | 6.9 s / 13.4 s |
| a slice; a lane of two for the long checks; one spare | 1,037 / 1,247 | 2,847 / 4,502 | 17.5 s / 29.9 s |
| ... two spares | 529 / 706 | 2,170 / 3,490 | 17.6 s / 30.2 s |

- **It stays:** a first slice of 0.25 s, the long checks only while no other text waits for a process,
  two spares (`server/pool.py`: `SLICE_S`, `LANE`, `SPARES`). At 5 % the others have 95 % of their
  verdicts within 1.2 s, where F1's queue took 5 s; at 1 % within 11 ms (three runs, the slowest 281 ms;
  SQL, whose runaway text SQLite stops itself: 9 to 11 ms, no worker ended).
- **As it stands after the review** - the long checks leave one process to what comes meanwhile
  (`KEPT`), the process that normalizes runs beside the workers, idle in these runs -, the same runs
  again, twice at 3 and 5 %: 386 / 611 and 356 / 556 at 3 %, 1,224 / 2,271 and 1,270 / 2,076 at 5 %;
  at 1 % 10 to 13 ms (the slowest 256 ms), SQL 9 to 12 ms. A runaway text's own verdict: at most 8.0 s
  at 3 %, 15.4 s at 5 %.
- **What the slice does not do:** once no other text waits, the long checks take the processes but
  one, each for its whole budget; texts that come then share the one, or wait for a long check to
  end - the slowest of the others at 5 %, about 2 s, is such a one. A runaway text holds up those
  that wait with it for its slice; it can still hold up one that comes later for a budget.
- **The lane loses** on both counts: the other texts wait for the processes it keeps busy, and the
  runaway texts for the two it has - one of 50 had no verdict after 30 s.
- **A second spare** is worth about a third of the others' time at 5 %.
- **What it costs:** a text that needs more than its slice is checked twice, and one that only the
  watchdog stops ends two workers, not one - 100 in the run at 5 %. The runaway texts' own verdicts
  come later than without the slice (15 s for 9 s): they wait until the others are through.
- On one machine, with its phones on the same cores: the laptop's run with the phones from a second
  machine is package 13's.

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

**A text without its comments (2026-11-12, after package 5's review; AF 5.1).** `sql-query`,
`sparql-query` and `turtle-graph` normalize a text to what it is without its comments
(`activities/code.py`: `CodeKind.normalize`; `checks/cleaning.py`: `uncommented`), since a group is
shown by that text and F3's vote puts it on every phone. F1's type is as it was: it shows a text
with its comments until the core replaces it.

- **Where the comments are, the engine says** (`comments(text)` in `checks/sql.py`, `sparql.py`,
  `turtle.py`), each as its parser reads the text: SQLite's `--` to the line's end and `/* */` to
  the first `*/` or the text's end - none in a string, a quoted name or a parameter, and `/*` as
  the text's last two characters is a slash and a star -; SPARQL's and Turtle's `#` to the line's
  end - none in a string, in an IRI (`<http://x#y>`) or behind a backslash (`ex:a\#b`); in Turtle
  a phone's typographic quotes make a string, as in the check.
- **Only what is surely a comment goes.** Oxigraph reads a `<` in SPARQL as an IRI's start or as
  the comparison, as the grammar around it wants: `FILTER(?a<?b#c>` is a comparison and a comment.
  The text is read both ways at once (`common.hash_comments`), and a `#` is a comment where every
  reading says so - in `?s <http://x#y> ?o # c` the last one. What may be one stays: such a text
  keeps a comment, and is checked as before.
- **SQL:** a comment between two words leaves a space (`SELECT/**/1`), a line of nothing but
  comments goes. SQLite names a column by its expression's text: the detail's `1 /* Max */ + 2` is
  `1 + 2` now. The spaces at a line's end go as ever, those in front of a comment that was the
  line's last too - also a no-break space, which SQLite reads as a letter.
- **SPARQL and Turtle keep their lines** - a comment's line stays as an empty one, and the blank
  lines in front stay too, which F1's cleaning took off; only what is behind the last line that
  has something goes -, so that the place an error names is a place of the student's text: the
  engines' errors name a line and a column, SQLite's do not. (A kind keeps its lines if its
  messages have `at`.) For Turtle it is also the place Oxigraph names for the text with its
  comments. For SPARQL not always: its parser names how far it read, and of ordinary broken
  queries with comments at their lines' ends about one in six is named a line further down once
  the comments are out - where the same query typed without comments always was (the review).
  A text that began with a comment begins with an empty line: it is another form than the text
  without that line, checked for itself and counted for itself where a group's most frequent text
  is asked for, and a window that draws a group's text may leave such lines out (package 8). The
  blank lines in front count to a text's 2,000 characters now.
- **A text of nothing but comments is refused** (`Unfit`, the phone's code `text`: "a query is more
  than its comments") - it was a syntax error before; either way it is in the group of what is
  invalid, now without a text to show.
- **Checked as the text with its comments:** 240,000 random texts, each checked as F1 cleaned it
  and as normalize leaves it - words, quotes, IRIs and comments thrown together, and texts that
  check with comments between their words; and 240,000 of the reviewer's own. Nothing that is no
  comment was taken or changed in any of them, a normal form was its own and had no comment left,
  and for SQL whatever gave a result gave the same one and whatever gave none gave none. For
  Turtle that holds since its check reads a text's end as it reads the rest, for SPARQL but for
  the one thing below; 3,000 texts per kind are in the suite (`tests/test_kinds.py`), which names
  it. What may differ besides is an
  error's words: Oxigraph's "expected ..." depends on how far it read, a comment included. The
  golden texts with comments go to the checks as they are (`direct`), as references do - a
  reference is not normalized -, so what the engines make of a comment stays pinned; the kinds'
  fixtures have texts with comments through normalize beside them (`*-comments.json`: what the
  code gives, so they show a change, not that it is right - the random texts show that).
- **Where the check is another without the comments** - one thing is left, the grammar's: *SPARQL
  takes no comment in brackets that are empty* - `[ # any node`, then `]` on the next line, and
  `( )`, `RAND( )` alike: with the comment a syntax error, without it the node the student meant.
  (As a reference, which is not normalized, the text stays an error.) Keeping the comment there
  would show it to the class, and tell a student that a comment is a mistake.
- **Two more the review found were faults of F1's checks, older than the comments, and are mended
  there** (2026-11-12, on the user's word) - where the server checks; in the lectures the phones
  check until lecture-tools takes F1 (2.3), with the browser's engines, which have both still:
  - *A text's own base* (`checks/sparql.py`, `turtle.py`: `_completed`). The checks put the
    seed's declarations in front of a text that does not make them itself. For a seed with `@base`
    and a prefix relative to it - `@prefix : <> .`, as the lectures' seeds have - and a text with
    a `BASE` of its own, the seed's base was left out and its relative prefix stood in front of
    the text's `BASE`, where it has no base: a syntax error, placed in a line the student never
    wrote. The seed's base stands in front of every text now, the seed's prefixes behind it as the
    seed has them, and the text's own `BASE` behind those: what the text writes is its own
    base's. Nothing else changes for a text without a base of its own, nor for one whose seed's
    prefixes are not relative. (With comments out, `BASE# c` and its IRI on the next line had
    become such a text.)
  - *A Turtle text's end* (`checks/turtle.py`: `_parsed`). Oxigraph reads a name with an escape
    in it, and the dot behind it, other at a text's end than in front of a space, a line end or a
    comment: `ex:a ex:p ex:b\#c.` was "Unexpected end" and is a graph once anything follows;
    `ex:b\..` named `b`, and `b.` once anything follows; `ex:a ex:p ex:\.`, a triple without its
    dot, was a graph. A text of that shape - a backslash in its last word, a dot its end - is read
    with a space behind it; of 40,000 random texts 2,777 were read otherwise at their end, all of
    that shape, and none is now (120,000 texts). Every other text is read as before, so no error
    of theirs has another place or other words - a space behind every text would move "Unexpected
    end", the commonest error, a column on. Where a text of the shape is no graph, its error is
    its own, where it was; where it was one only at its end, the error is the one with the space,
    its place no further than behind the text's last character.
  - *The browser's engines have both faults still* (`web/engines`), and the golden fixtures made
    from them had the first as two syntax errors: these are in `KNOWN` now
    (`tests/test_checks.py`), with the reason. Where a server compares the phones' checks with its
    own (`--checks both`), such texts show as differences.
- **Quick:** 1 to 2 ms for 2,000 characters full of comments, 4 ms for the slowest of 9,000 random
  texts, on the process that normalizes; the time grows with the text's length and no faster.
- **An engine must say where comments are:** a kind of this shape whose engine has no
  `comments(text)` cannot be made, and the registry says why - not every entry of a lecture.
- **Its review (2026-11-12):** an independent reviewer, 240,000 random texts of its own, mutants
  - the brackets and the two faults above, the SPARQL lines, a speed that was said too low, two tests that were
  missing, and what follows.
- **Found by it in F1's check, and mended: SERVICE got past its refusal** (`checks/sparql.py`:
  `names_service`), so that a student's query could have the server ask an address of the
  student's choosing - wherever the server checks, which so far is the load runs and the laptop's
  runs, and no lecture: the lectures' copy of texstage (2.3) has no server's checks yet (looked at
  on 2026-11-13: lecture-tools has no `src/texstage/checks`), there the phones check, and a
  browser's Oxigraph has no network and refuses the word. The mending reaches a lecture with F1,
  when lecture-tools takes it from a `main` that has it - the branch `f1-server-checks` has not.
  (This paragraph said "in the lectures too" until 2026-11-13, and the commit's message says so
  still: it was not looked up.) A pattern read the text one way; four texts were read
  otherwise by Oxigraph, which then ran the word: a name's escape (`ex:a\#b` - the `#` began a
  comment for the pattern, and `ex:a\'b` a string), an IRI with a no-break space or a `\u`
  escape in front of its `#`, a long string with an escaped quote at its end (`'''a\''''`), and
  a comparison that looks like an IRI's start (`FILTER(?o<'>')`). The refusal reads a text now as
  its comments are read - both ways at once, and the cautious way round: SERVICE counts if one
  reading has it as a word. Held against Oxigraph itself: of 300,000 random queries with what may
  break a reading in front of SERVICE, 70,000 had the keyword - they parse, and do not once the
  word reads `@@@` -, and none got past, where one in ten had before (1,351 of the first 14,172);
  6,000 are in the suite
  (`tests/test_checks.py`). The price: `<http://e.org/it's>` and, behind it, a string that says
  SERVICE is refused, since the IRI may be a comparison and a string's start.
- **Not done:** the spacing within a line, which AF 5.1 named with the comments, stays as typed -
  a column is the student's own only so. And a name in a string, or a text that is a name, is
  shown: comments are what is written for no one to run.

### 4.8 texstage's own kinds

- **`choice`** - one or several of the options a deck gives (from F3 also an earlier step's
  groups); reduction `tally`; right when the choice is the reference's.
- **`number`** - a number, with a tolerance as its option; a histogram; right within the
  tolerance.
- **`text`** - a short answer, normalized as the quiz's text answers are
  (`scoring.normalize_text`); reduction `groups`.

They come after the four, as the contract's second test: no seed, other reductions, other views.
Their checks run in the pool too: no kind code runs in the server's event loop (AF 2).

Asked alone, each is what a quiz's question or a poll asks already - a choice, a number, a short
text. The duplication is accepted (decided 2026-11-11): the quiz stays as simple to use as it is,
with its own flow (AF 2, "Quizzes"), and is not bent to serve as a step of an activity; the three
kinds are the activities' own, for the steps that need them - a vote on an earlier step's groups,
a number before a query (AF 5.1) - and they stay in F2.

### 4.9 The kit

`texstage kinds` lists what is installed - name, package, version, API. `texstage kinds check
<name>` loads the kind and checks its options; runs its fixtures, twice and in both orders, and the
safety fixtures - for SPARQL `SERVICE` in every spelling and the names that are not it
(`?service`, `:service`), for every kind nesting beyond its parser's cap; compares its texts in
English and German; loads its browser modules in Node, with a network that refuses; measures what a
phone loads - against the sizes of AF 2 -; and reports each fixture's time against the
budget (AF 7.5). Its Python half comes with the contract (package 2), its browser half with the
browser (package 8).

The Python half, as built (`activities/kit.py`): the class against the contract's rules; the
fixtures, each entry through `normalize` and `check` on a thread with a worker's stack, twice and
the second time in the other order; every check against the rules a check must keep; for a kind
of code, three texts nested as deep as a text is long, which must come back as a check; each
fixture's time against the kind's budget - over it, a warning -, and a check that is not back
after 30 s given up. A fixture names a setting - the item, keys and files the kind is prepared
with, its references among them -, an entry, and what it pins: the check's status, or the
statuses it may be, and of its other fields those it lists, or the code `normalize` refuses the
entry with. A build gives a deck's keys, bodies and files, and what the kind makes of them or the
words it refuses them with. The command fails when a kind fails, cannot be used, or none is there
to check.
Left for the browser half: the texts in English and German - the codes are listed in Python
(`MESSAGES`), their words are not there yet -, the modules in Node, what a phone loads.

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
before. Its review is done - ten faults, fixed (4.2). Three of those fixes change F1's code, for
texts and decks no lecture has met: what a text with a soft hyphen before an accent is cleaned to,
and a number written with other digits than ASCII's, in the build. Package 2 is built on it
(2026-11-11): the contract as API 0, the registry, the kit's Python half; `texstage kinds` lists
the four, and a kind that breaks a rule fails the kit with the rule. Its review is done too -
thirteen faults, fixed (4.2). What F1 still changes reaches
`f2-core` by a merge; the checks' move into the packages waits for that (4.2). Both are on `main`
since 2026-11-11, with F1 and the presenter view's improvements; `f2-core` goes on from there.
Package 3 is built on it (2026-11-11): the steps and their phases, the entries, the storage with its
writer, a restart, and the move of F1's rows (4.3 says what it settled). It rewires nothing either:
F1's type runs the server, and the core's tables are made only where its own code is asked to. Its
review is done - fourteen findings, fixed (4.3). Package 4 is built on it (2026-11-11): the core's checks, the
process that normalizes, and short checks first in the pool - measured with the load runs at 1, 3
and 5 %, which decided its way (4.6). It changes F1's pool, which the server runs: the budget of a
check is 1 s, a check gets a slice first, the pool has two spares. Its review is done - twelve
findings, fixed (4.3, 4.6). Package 5 is built on it (2026-11-11): the reductions - groups, today's
crowd graph, the tally -, the pictures and their versions, and the lecturer's acts with their undo
(4.3). It rewires nothing. Its review is done (2026-11-12) - twenty findings, fixed (4.3). What
the review left to the kinds is done too (2026-11-12): their normalize takes a text's comments out
(4.7) - F1's type shows them as before. Its own review found a fault of F1's check, and it is
mended in F1's code: SERVICE got past its refusal - where the server checks, which is no lecture
yet (2.3; 4.7). Two more faults of F1's checks, which the review met, are mended with it: a text with a
base of its own for a seed with relative prefixes, and how Oxigraph reads a Turtle text's end
(4.7). Package 6 is built on it (2026-11-13), not reviewed yet: the core's type with AF 10.4's
messages, `activity.step` and the lead window, the pool's processes checking through the kinds -
beside F1's type, which a server runs unless it is told otherwise (4.3): it rewires nothing for
the lectures.

### 4.13 Risks

| risk | what then |
|---|---|
| the size: the type, its windows and its build rewritten at once | F1's release stays the fallback; the four kinds and the server side (packages 1 to 6) are tested before the browser's |
| the contract changes as it is cut | it is API 0 (AF 2); the four kinds come first, and their fixtures show what each change breaks |
| a decision of 2.4 changes later | 2.4's table says what follows; short checks first is measured before it stays (4.6) |
| lecture-tools has drifted from texstage-public (47 files on 2026-11-09) | taking F2 is a package of its own (11), and F1's lecture brings it nearer first |
| the groups differ from F1's | normalizing merges only checks, not groups; package 13 compares them in the lecture's environment |
| a name in a comment reaches the class | the kinds' normalize takes comments out since 2026-11-12 (4.7); a comment that only may be one stays - SPARQL's `<`, an IRI's start or the comparison -, and so does a name in a string |
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
