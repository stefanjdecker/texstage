# texstage - the activity framework (design)

Status: 2026-11-09, a design to refine; of its stages (section 18), F0's spike, F1's packages
1 to 5 (2026-11-10) and F2's packages 1 and 2 - the contract of 7.1, the registry, the kit's Python
half (2026-11-11) - are built on their branches, nothing of it is in `main` yet. It comes from the
brainstorm of 2026-11-09, whose last open questions were decided the same day (section 2), was
revised after a critical review the same day, and redesigns the live activities of October
([live-activities-design.md](live-activities-design.md), here **LA**): the server checks what
students send, the kinds of activity are packages of their own, and an activity can have several
steps, with points. It keeps the core of [content-types-design.md](content-types-design.md) (here
**CT**) - the build, the bundle, the server's registry of types, the windows. File references are
to `src/texstage/` unless they name another folder.

## 1. Idea in one paragraph

An **activity** is a live exercise on a slide: every student sends something - a query, triples,
a choice -, texstage checks it, gathers what the class sent into one picture on the projector,
and the lecturer steers it. Today `server/activity.py` and its windows know two such things by
name, and the presenter's browser runs the checks. The framework splits this into a **core** that
owns the classroom - steps and their phases, entries, limits, checking on the server, groups,
points, the views, the lecturer's controls - and **kinds** that own a subject: what an entry is,
how it is checked, what a group of equal entries shows. A kind is a package, installed per
subject (`texstage-kinds-sql`) and named by a deck (`kind=sql-query`); the kinds texstage brings
itself use the same contract. An activity can have several **steps** - write, vote, fix -, each
with its phases, its timer and its points, driven by the clicker as a quiz is. The quiz stays a
type of its own and shares the timer, the points and the leaderboard. All of it is designed for
1,000 students, with the server on the presentation laptop.

## 2. Decisions

| Topic | Decision | |
|---|---|---|
| Quizzes | stay a type of their own with their own flow - well known and easy to set up; they share the timer, the points ledger and the leaderboard with activities (section 14) | decided 2026-11-09 |
| Where entries are checked | on the server, in worker processes; the phones give hints while a student types, never a verdict (sections 6.3, 7.3, 12) | decided 2026-11-09 |
| Where the server runs | on the presentation laptop or hosted - the same program (section 16) | decided 2026-11-09 |
| Kinds | packages, installable separately, per subject; a deck names the kinds it uses; the kinds texstage brings use the same contract (section 7) | decided 2026-11-09 |
| Steps and points | in the core from the start (sections 5, 14) | decided 2026-11-09 |
| Scale | 1,000 students in one session, the server on the presentation laptop (section 15) | decided 2026-11-09 |
| The kind contract | a kind sets its options - one schema, on the activity or per step -, its checks' verdict and credit, its input and its views in the browser; it uses the core's reductions, none of its own; no kind code runs in the server's event loop: `normalize` runs in a worker, as `check` does (sections 6.2, 7.1, 10.1) | decided 2026-11-09 |
| Where kinds live | the first ones in texstage-public, in `kinds/`, each a package of its own; after F4 the shared ones move to texstage-plugins and a subject's own to its repository; installed as texstage is, from source with locked requirements - on PyPI later, with texstage (section 7.2) | decided 2026-11-09 |
| Steps first | write-then-vote and write-see-fix (F3); the clicker can run a whole activity, a vote's choices made without the lecturer (sections 5.1, 8.2) | decided 2026-11-09 |
| Time and memory of a check | CPU time, not the clock's: a text over its budget is the student's `timeout`, a check the clock's backstop stops is `internal`; SQLite's own memory cap, a watchdog on every worker's memory, and the systems' hard limits where they have them (section 11) | decided 2026-11-09 |
| Hints | JavaScript, no WebAssembly on the phones; their size limited leniently, by the sizes below (section 7.3) | decided 2026-11-09 |
| Polls | stay as they are: quiz rounds the lecturer asks on the spot (`server/polls.py`); back to them only if the vote step and polls come to duplicate code | decided 2026-11-09 |
| Order of the work | first today's four kinds checked on the server, behind today's messages and LaTeX; then the core and the contract, cut from them; then steps - each stage on a branch until its test passes, the lectures on `main` meanwhile (section 18) | decided 2026-11-09 |
| The contract's number | API 0 while it may still change; API 1 once a kind of another subject has checked it (F4) (sections 7.1, 7.2) | decided 2026-11-09 |
| Failed checks | a check whose worker died, or that the clock stopped, runs once more on a fresh worker; failing again, it stays `internal` and its text is set aside for the step; memory is a text's fault only if it runs over on a fresh worker too (sections 6.3, 11) - except SQLite's own cap, which counts alike in every worker: a text that reaches it is the student's `error` at once (decided 2026-11-10). A text set aside stays so when the server starts again - no third worker dies for it then either -, while every other `internal` entry is checked again; and a worker stopped from outside - Ctrl+Break, a stop of the whole process group - is not its text's doing: that sets no text aside (both decided 2026-11-10, after the review of F1's package 4) | decided 2026-11-09 |
| Reopening | the lecturer can open a closed step again; going back on the slides does not, as today (section 5.2) | decided 2026-11-09 |
| The automatic vote | its choices are made once the earlier step's checks are in, at most 3 s after it closes; a choice shows its group's most frequent text in the kind's normalized form - comments gone -, never a text as one student typed it (section 5.1) | decided 2026-11-09 |
| The word *kind* | kept: it clashes only inside the code - the page records' `G\|kind\|...`, the polls' kinds (`server/polls.py:28`, `choice` and `text` among them) -, where *stage* clashes in the windows and the protocol; the framework's code says *activity kind* (section 4) | decided 2026-11-09 |
| Python or Rust | Python, designed for 1,000 and measured early on the real laptop; what the measurement shows to be slow moves to Rust, piece by piece (section 15.3) | decided 2026-11-09 |
| The parts of an activity | called **steps**: the brainstorm said *stages*, but texstage already uses that word - the presenter window's role `stage`, the session's stage state, `web/stage/`, the stage PDF | decided 2026-11-09 |
| Defaults of a step | no points unless the deck gives them (`points=none`), no speed points (`speed` off); the reveal's setting is called `solution=`, since `reference=` names a file (sections 5.3, 14) | decided 2026-11-09 |
| Sizes on the phones | what a phone loads for a kind: up to 200 KB compressed without a word, a warning of the kit above that, a refusal above 1 MB; sent compressed; no limit in the windows (sections 7.3, 7.5, 15.1) | decided 2026-11-09 |
| Short checks first | every check gets 0.25 s of CPU time first; one that needs more while others wait goes to a second queue, which runs with the whole budget when the first is empty; the budget 1 s, not 2 - in F0, 3 % of texts running into their budget pushed 95 % of the verdicts to 8 s ([activity-framework-plan-f2.md](activity-framework-plan-f2.md), 4.6; section 11) | decided 2026-11-09 |

This changes two of CT's principles (CT section 3) and keeps the others:

- **"The server runs nothing"** (principle 1) goes: the server checks entries. Bundles stay data,
  never code: a deck names kinds, it brings none.
- **"All types live in this package"** (principle 2) goes for kinds: the activity type is
  texstage's, its kinds come from packages. Whoever runs a server decides which kinds it has, as
  they decide which Python packages it has.
- **"The second type finds the seams, the third checks them"** (principle 5) stays: the kind
  contract is cut from today's four kinds (section 17) and checked by a kind from another subject
  before it is called stable (section 18, F4).

Of LA's decisions, evaluation in the presenter's browser (LA section 8) goes, and with it the
lease for evaluating; "phones never run code" becomes "phones check nothing": a phone may run a
kind's hint module, which sees public data only (section 7.3). With the evaluator goes the
barrier that kept students' queries off the network - the worker's Content-Security-Policy
(`server/app.py:167`) and a WebAssembly build without HTTP: on the server, each kind has to keep
its engine from the outside itself (section 11).

## 3. Why a redesign

### 3.1 What today's activities taught

Main's activity type (LA; `server/activity.py`, 895 lines) works in the lecture, and shows where
it does not grow - with new kinds, and with more phones:

- **One module for two things.** `input=tuple` and `input=code` each fix an input, a reduction
  and a view at once (LA section 3); the crowd graph and the clusters share one file and one
  state.
- **A new kind touches about eight files:** the LaTeX package, the build, the server, the
  engines' two tables (`texstage/engines.py`, `web/engines/index.js`), the windows, the phone -
  and record lines by position (`activity|id|input|engine|...`).
- **The panel knows the two by name;** the host console shows nothing of activities.
- **No timer, no points:** they belong to the quiz's rounds (`server/game.py`), not to the
  registry of types (`server/types.py`).
- **Checking hangs on one window.** Without a presenter window nothing is checked (LA section
  8.1); an iPad that presents checks in Safari.
- **Work grows with the class.** Every entry recounts all of the activity's contributions
  (`_recount`, `server/activity.py:249-253`), every phone's view goes through all of them for its
  own (`server/activity.py:569`, `:580`), and every message is saved in a transaction of its own
  (`server/store.py:5-6`); only the picture is computed once per version
  (`server/activity.py:602-612`). Fine for 300 phones (LA section 12), not the way to 1,000.

### 3.2 What the plugin system taught

The plugin system (tag `version1`, 5ed43a6; main went back to the state before it with 9a30f17)
added about 16,000 lines in three and a half days - 6,600 of them code in `src/texstage`, the
rest documents, tests and locks. Worth keeping:

- decks without code; kinds as pure reductions over storage the host owns;
- idempotent requests, and a reset as a new epoch rather than a deletion;
- typed check results, in which a technical failure is never a wrong answer;
- points owned by the host, not by the plugin;
- checkers locked away from the network;
- one source for the live item, the handout and the solutions.

Worth avoiding:

- every plugin re-implementing the lifecycle, with names that drifted apart;
- a `plugin.*` protocol beside `activity.*`, into which the built-in activities never moved;
- packaging machinery and five revisions of a manifest before the model had settled;
- a fresh worker and a re-run of the reference for every submission, in the presenter's
  browser: it limited the throughput (24 to 48 s for 1,000 submissions), was a single point of
  failure, and was what crashed WebKit. The functional-dependency lab met its burst target only
  by checking on the server.

### 3.3 What the redesign must do better

The four aims the redesign was asked for, and this design's answers:

| aim | answer |
|---|---|
| better integrated | one lifecycle, one protocol (`activity.*`), one panel and one phone screen for every kind; the clicker drives steps as it drives a quiz; timer, points, leaderboard, archive and languages are the core's, for quizzes and activities alike (sections 5, 8.2, 13, 14) |
| better controls | the same controls for every activity - open, close, reopen, pause, next step, reveal, time, show, hide, merge, block, reset - as buttons, as keys and from the slides; the panel shows what the projector shows (section 13) |
| more flexibility | kinds per subject, as packages; steps composed in LaTeX; per step the kind, the feedback before the reveal, what the projector shows, the timer and the points; a step can build on an earlier one - vote on its groups, fix after seeing them (sections 5, 8) |
| more logical handling | one state machine with named phases; a small vocabulary, the same in LaTeX, the protocol, the panel and the code (section 4); the core owns the state, a kind owns the subject, and nothing lies in between (section 6) |

## 4. Words

| word | meaning |
|---|---|
| **activity** | one live exercise of a deck, `\begin{activity}[id=..., kind=...]`; it has one step or more |
| **kind** | what a step is about - `sql-query`, `sparql-query`, `triples`, `choice` -: a package with its checker, its texts and its parts for the browser (section 7); in the code *activity kind*, since page records and polls have kinds too |
| **step** | one part of an activity - write, vote, fix -, with its own prompt, rules, timer and points |
| **phase** | where a step stands: `ready`, `open`, `paused`, `closed`, `revealed` (section 5.2) |
| **entry** | what a student sends in a step - a text, fields or a choice (LA's *contribution*) |
| **hint** | what a phone says while a student types: a kind's quick look at the text, never a verdict |
| **check** | the server's verdict on an entry: its status, its group, right or not, its credit (section 6.3) |
| **group** | the entries the check found equal - one result of a query (LA's *cluster*), one triple, one choice |
| **picture** | what the projector and the panel draw of a step: its groups, counted, moderated (as in LA) |
| **detail** | what one group shows: a result's columns and first rows, a graph (LA's result *summary*) |
| **credit** | a check's share of a step's points, 0 to 1 |
| **ledger** | the points every student got, from quizzes and activities alike (section 14) |

## 5. The model

### 5.1 An activity in steps

An activity has one step or more; one of them is its **current** step. A one-step activity needs
no step written out (section 8.1). Each step has a kind, by default the activity's. Shapes the
model has to carry:

- **write** - the class writes queries; the projector shows the groups growing; the reveal marks
  the reference's.
- **write, then vote** - step 2 offers groups of step 1 as choices: "which of these is right?";
  then the reveal. Without the lecturer the choices are the largest groups - always with the
  largest right one among them, if anybody was right -, shuffled, and "none of these is right",
  so that the options never give the answer away; the lecturer can pick them instead. They are
  made once step 1's last checks are in - its last seconds bring the most entries -, at most 3 s
  after it closes, while the phones say "counting". A choice shows its group's most frequent text
  in the kind's normalized form - its comments gone, and the spaces at its lines' ends -, never a
  text as one student typed it: no name or joke in a comment reaches 1,000 phones (but one in
  what only may be a comment - the plan of F2, 4.7).
- **write, see, fix** - after step 1 closes, the projector shows its groups; step 2 asks again,
  and the points go to whoever is right at the end: a student's entry of step 1 stands in step 2
  until they send another.
- **predict, then do** - step 1 asks for a number ("how many rows?"), step 2 for the query; the
  reveal shows both.
- later: **peer review** - each phone gets another student's entry of an earlier step,
  anonymous, to judge.

A step that builds on an earlier one says so (`from=write`); the core hands it the earlier step's
groups, never who sent them. `choice` is one of texstage's own kinds (7.2); on an earlier step's
groups it needs no checker: the core counts the choices, and a choice is right when its group is
the reference's.

F3 builds write-then-vote and write-see-fix first (decided 2026-11-09): between them they need
both mechanisms - a step built on another step's groups, and one kind twice with the points at
the end. Predict-then-do follows with little more; peer review later.

### 5.2 Phases

```
                  ┌──────open───────┐
                  ▼                 │
ready ──open──► open ──close──► closed ──reveal──► revealed
                │  ▲
           pause│  │resume
                ▼  │
              paused
```

- `ready`: not opened yet. `open`: the phones can send. `paused`: the timer stops, and the phones
  cannot send until it resumes (as a paused quiz round). `closed`: nothing new comes in; what
  waits is still checked. `revealed`: the phones learn their verdicts, the reference shows, the
  points are given.
- A step opens when its page comes to the projector (section 8.2) or when the lecturer opens it;
  it closes when its time is up, when its page goes, or when the lecturer closes it. *Next* closes
  the current step and opens the next.
- One activity is open at a time, as today: the phones show one thing (section 12). Opening a
  step of another activity closes the open one; a quiz round that opens pauses the open step, and
  the round's end resumes it.
- Every move is idempotent and can come from the panel, the keys or the slides. Going back on the
  slides never reopens a closed step, but the lecturer's *Open* does: it goes on with what is
  there, with the time the lecturer gives it (as LA section 7.2). A revealed step stays revealed.
- **After a sleep** of the laptop an open step is paused, not closed: a step's time counts while
  the server runs (today's deadlines are the wall clock's, `server/app.py:171-172`).
- **Reset** gives a step a new epoch: its entries stay stored and in the archive, but no longer
  count; after the reveal it takes the step's points back too (section 14). The panel asks first.
- A step without a reference has nothing to reveal: its reveal only ends it.

### 5.3 What each audience learns, and when

Per step, set in LaTeX (section 8.1):

| key | values | default |
|---|---|---|
| `feedback=` - what a phone learns before the reveal | `none` (received); `status` (it runs - or the syntax error, with its line where the engine gives one: SQLite does not); `verdict` (right or not, at once: a practice step); `full` (the verdict and the kind's message: "3 rows missing") | the kind's; `status` for queries |
| `projector=` - what the class sees while the step is open | `live` (the picture grows); `count` (how many sent; the picture once the step closes - nobody copies the largest group); `hidden` (nothing until the reveal) | `live` |
| `solution=` - what the reveal shows the class | `show` (the reference and its result on the projector); `mark` (only the groups that match it) | `show` |

The reference reaches no phone and not the projector before the reveal (LA section 8.5), and no
view names a student (LA section 7.4).

## 6. The core and the kinds

### 6.1 Who does what

| | the core | the kind |
|---|---|---|
| LaTeX | the environment, steps, overlays, the box, handout and solutions | its keys, checked at build; optionally a package for a handout form of its own |
| build | the records, prompt pictures, `deck.json` and `keys.json`, files into the bundle | checks its keys, prepares its data, checks the references (section 9) |
| server | phases, timers, entries, limits, rates, blocking, equal inputs checked once, the pool of workers, groups, pictures, moderation, points, views, pushes, storage, archive | `normalize` and `check`, both in a worker: no kind code runs in the server's event loop |
| windows | the panel and its controls, the box and its frame, the choice of what the projector shows | how a group's detail draws - a table of rows, a graph -; optionally a whole view |
| phones | the screen, the step's state, sending and sending again, the verdict | a hint while the student types; optionally an input of its own |
| texts | the controls, states and refusals, in English and German | its own words, in English and German |

A kind has no state, no messages and no lifecycle of its own: everything it does is a function
the core calls with data. The reason the plugins' names drifted apart is gone with it.

### 6.2 What the core brings

So that most kinds are a checker and little else, the core brings the common parts; a kind
names the ones it uses:

- **inputs** (the phone's form): `code` - monospaced text with a token bar, no autocorrection
  (LA section 10); `fields` - two or three fields with suggestions (LA's `tuple`); `choice` - one
  or several of given options, or of an earlier step's groups; `number`; `text` - a short answer.
- **reductions:** `groups` - entries grouped by their check's key, counted by students, the
  largest first, each with an example (LA's clusters); `crowd` - fields as nodes and edges,
  merged by the lecturer (LA's crowd graph); `tally` - choices counted.
- **views:** bars for `groups` and `tally`, the graph for `crowd`, a histogram for numbers.

A kind that needs more brings an input or a view of its own as a browser module (section 7.3).
A reduction of its own is not in the contract (decided 2026-11-09): the kinds F4 has in mind -
functional dependencies, relational algebra, normal forms - all fit `groups`, and the first kind
that does not is where the contract grows next.

### 6.3 A check

What a kind's `check` returns - typed facts, not a free dictionary:

| field | meaning |
|---|---|
| `status` | `ok` (it ran); `invalid` (it does not parse - the student's, with the message and where); `error` (it parses and fails - the student's: a table that does not exist, too much memory); `refused` (what the kind does not run: `SERVICE`, an update); `timeout` (the student's text used up its CPU time); `internal` (the checker failed, or its worker died - never the student's) |
| `key` | the group: entries with equal keys form one group - the hash of the result's canonical form (LA section 8.4); without a key, entries group by their status |
| `parts` | for `crowd`: per field its key (by `terms=`), its cleaned text and whether it is a literal - what today's tuples carry (`server/activity.py:172-207`, `:537`) |
| `verdict` | `correct`, `partial`, `incorrect` - or none: the step has no reference, or the kind does not judge |
| `credit` | 0 to 1, the share of the step's points |
| `message` | for the student: a code and its arguments, which the phone says in its language from the kind's texts |
| `at` | line and column in the student's text, both from 1, the column in characters, where the engine gives them - Oxigraph does, SQLite does not (LA section 8.8) |
| `detail` | for the windows: the columns and the first rows, and under `diff` the comparison with the reference, which the core keeps from the projector until the reveal - at most 12 KiB |

Unless the kind judges for itself, the core does: `correct` when the key is one of the
references' keys, else `incorrect`. An `internal` check is never graded: the entry counts as
unchecked, the panel says how many are, and the core checks it once more, on a fresh worker;
failing again, it stays `internal`, its text is set aside for the step - no third worker dies
for it, after a restart of the server neither -, and its entries earn nothing (sections 11, 14).
An `internal` check that is the server's doing - its pool broke, the step's preparing failed, a
worker was stopped from outside - sets no text aside: the same text sent again is checked again,
and so are such entries when the server starts again (10.2).

## 7. Kinds

### 7.1 The contract

Cut from today's four kinds (section 17), as `activities/kind.py` has it (API 0, 2026-11-11):

```python
# a kind: a class the core makes once (texstage.activities.Kind, API 0 until F4, then 1)
class SqlQuery(Kind):
    NAME = "sql-query"                           # as a deck names it, and its entry point (7.2)
    API = 0                                      # the contract it implements
    INPUT = "code"                               # the core's input its steps show (6.2), or its own (7.3)
    REDUCTION = "groups"                         # groups | crowd | tally: the core's (6.2)
    OPTIONS = fixed(tokens=Words(), seed=File(".sql"), reference=File())    # the deck's keys it takes, typed
    MESSAGES = fixed(queriesOnly=(), engine=("text",))                     # what its checks may say, by code
    BUDGET_S = 2.0                               # a check's CPU time in seconds; a step may set less (budget=)
    LIMIT = 5                                    # a student's entries, unless the deck says

    # the build, on the author's machine
    def build(self, options, bodies) -> Built: ...           # checks its keys; the item (public), keys (private), files

    # the server, in a worker process - no kind code runs in the server's event loop
    def prepare(self, item, keys, files, limits=None, copy=None) -> Prepared: ...   # per worker and seed
    def copy(self, prepared, most) -> bytes | None: ...      # optional: what prepare made, for every worker
    def normalize(self, step, entry) -> Entry: ...           # quick: entries that normalize alike are checked once
    def check(self, prepared, step, entry) -> Check: ...     # one distinct entry, within the budget
```

`OPTIONS` is one schema for an activity and its steps: a key given on a step overrides the
activity's. Its types - `Words`, `Int`, `Flag`, `Choice`, `File` (`activities/options.py`) - read
what the deck gave and say what is wrong with it; a kind's `build` asks for each key, and so says
in which order a deck's faults are told. An entry is what a step's input sends: a text, the fields
or a choice. `normalize` gives an entry, not a string - fields stay fields -, and may refuse one
that is not checked at all, too long or empty, with the code the phone has words for. `MESSAGES`
lists what a check may say, each code with its arguments (6.3, 7.4). A check's time is counted in
seconds, as the pool counts it; the references, which are the lecturer's, have a longer budget of
their own. An input of a kind's own (7.3) and the entries of `choice` and `number` come with the
browser and with texstage's own kinds; until then the kit takes the core's inputs, and an entry is
a text or the fields. No kind code
runs in the server's event loop (decided 2026-11-09): the loop merges entries whose texts are
identical, and a worker normalizes a new text - the pool's worker for normalizing, which never
waits behind a check (10.3), so that a slow or faulty kind can never hold up 1,000 phones; F0
measures what the round trip costs (10.1).

Beside the module, a kind has its files: `texts/en.js` and `texts/de.js` (its words, for the
phones and the windows; the rules of `web/i18n`'s catalogs apply), `web/hint.js`, `web/input.js`
and `web/box.js` (section 7.3), and `tests/`, fixtures the kit runs (section 7.5).

What the core guarantees a kind: `prepare` runs once per worker for every seed and options its
steps use - a step that sets its own `seed=` gets its own -, before any of their checks; `check`
runs once per step and distinct normalized entry; the references are checked first. A check gets
the public item, the keys and the student's entry - never who sent it - and must leave
`prepared` as it found it (the kit runs every fixture twice, in both orders). Where a kind has a copy of what the first
worker's `prepare` made (`copy`), every worker, the first too, prepares from it: a seed with
`random()` gives every worker the same data, and a database that ran its seed is not one that was
loaded from a copy. An entry that is not of the kind's input is the core's fault, not the
student's: `check` raises, and the core makes the check `internal` - as it does with a check that
breaks a rule of the contract (`validated`: a status there is none of, an `ok` without a key, a
message the kind does not list), which the kit finds first. What a kind
promises the core: `normalize` gives a form people can read - its comments gone, the student's
names kept, and its lines where the kind's errors name one, so that the line is the student's own
-, since a vote shows it (5.1); and its parsers refuse what they choke on before they parse it
(section 11).

### 7.2 Packages

- A kind is found by its package's entry point:
  `[project.entry-points."texstage.kinds"] sql-query = "texstage_kinds_sql:SqlQuery"`. One
  package can hold a subject's kinds: `texstage-kinds-rdf` with `triples`, `sparql-query` and
  `turtle-graph`.
- texstage brings the kinds every subject needs - `choice`, `number`, `text` - through the same
  entry points, so that the contract is used by its own author every day.
- `texstage kinds` lists what is installed: name, package, version, API.
- **Where they live** (decided 2026-11-09): the first kinds in texstage-public, in `kinds/`, each
  a package of its own with its own `pyproject.toml`, installed separately. While the contract
  still changes (F2 to F4), a change then lands in one commit and one test run, not in several
  repositories (3.2). After F4 the kinds several subjects share move to texstage-plugins (its
  main is empty; perhaps renamed texstage-kinds), and a subject's repository keeps the kinds only
  it uses.
- **How they are installed:** as texstage is - from source, with locked requirements
  ([installation.md](../installation.md)); on PyPI later, together with texstage.
- The build writes into `deck.json` which kinds the deck uses, with package, version and API:
  `"kinds": {"sql-query": {"package": "texstage-kinds-sql", "version": "1.2.0", "api": 0}}`. A
  server that lacks a kind, has it with another API or another major version, or with an older
  version than the build's - whose options it may not know -, refuses the bundle and says which
  package to install - as it refuses a deck that names a type it lacks (`server/bundles.py`).
- Nothing more at first: no catalog, no signatures, no pinned hashes of a kind's files (3.2).
  They come when kinds travel beyond the people who install them.

Kinds are trusted code, as every Python package of the server is: whoever runs a server installs
them. The students' texts are not trusted (section 11).

### 7.3 The kind in the browser

```js
// on the phones: JavaScript, public data only, no network (the pages' CSP); their size: below
// web/hint.js - in a Web Worker, so that a slow hint never holds up typing
export function hint(step, text, words) {}     // -> null | {code, args, at}: while the student types;
                                               //    words: {language} - data, as a worker gets it
// web/input.js - (optional) in the page: an input of its own instead of the core's
export function input(element, step, words, send) {}   // draws the input into element; send(entry)
                                               //    sends what it holds - a promise: taken or not

// web/box.js - in the presenter and projector windows
export function group(detail, words) {}        // a group's detail as HTML: rows as a table, a graph
export function view(picture, words) {}        // (optional) the whole box instead of the core's view
```

A group's detail carries what students' queries gave: `group` escapes what it puts in. The windows
put its HTML in as it comes - they trust a kind's code as the server trusts its Python. (`view`
is not built in F2: the four kinds and texstage's own need none.)

The server serves a kind's files from its package under the hash of their contents
(`/kinds/<hash>/...`): cached long and immutable, as a bundle's pictures are, gzip-compressed once
when it starts, and never stale - a kind installed from source changes without a new version, and
its hash changes with it. The kinds of one package share their folder, so their hash: a file they
share comes once. A phone loads all of the deck's kinds' files in the background when it joins -
its hints too, which their worker takes from the browser's cache - not in the second a step opens
on 1,000 phones (section 15.2).

Every page gets a Content-Security-Policy - scripts and connections from the server only -, so
that a kind's modules reach no network in fact, not by convention. Today the evaluator's worker
has one, and the hints' worker since F2's package 8 (`default-src 'none'; script-src 'self'`: a
worker's `import()` is a script's, so blocking `fetch` alone is not enough); F2 fits the pages'
own to today's pages - KaTeX's inline styles, the add-in's Office.js
([activity-framework-plan.md](activity-framework-plan.md), 4.12).

A hint knows what the phone knows: the step's public item - its tokens, the seed's table and
column names, its prefixes - and the student's text. "A parenthesis is not closed in line 2" and
"`Studnet` is not a table - `Student`?" are hints; whether a query is right is not one. A hint
never stops a student from sending.

The sizes are lenient (section 2). What a phone loads for a kind - its modules, what they
import, its texts and styles - may take up to 200 KB compressed without a word; above that the
kit warns, and above 1 MB it refuses the kind (7.5). For scale: texstage's own phone page is about
45 KB compressed, and KaTeX, which a phone loads for a formula, about 80 KB; 200 KB leave room for
an editor with highlighting or a parser library. 1,000 phones at 200 KB are 200 MB while they
join, at 1 MB a gigabyte - minutes of a hall's network; F0 measures the join (15.1). The windows'
modules have no limit: a few windows load them, not 1,000 phones.

No WebAssembly on the phones (decided 2026-11-09). A parser there buys little: the server's
syntax error is back within a second of *Send*, with its line and column where the engine gives
them - SQLite names the token, not the place, so an SQL kind may bring a JavaScript tokenizer for
its hints -; and Oxigraph's engine alone is 1.4 MB compressed - above the limit, and 1.4 GB for
1,000 phones. Back to it when a subject needs more.

### 7.4 Texts

A kind's texts join the core's catalogs under `kinds.<name>` (`web/i18n`); the phones and the
windows speak the deck's language, in English where a kind lacks a text. A check's `message` is a
code into those texts, so the server sends no words. As built (F2, package 8): a kind's package has
`texts/en.js` and `texts/de.js` - a function of the message's arguments for each code -, and a key
`<kind>:<status>` there is the kind's own word for a check's status in place of the core's: a
Turtle text is valid, it does not run (`"turtle-graph:ok": "Valid Turtle ✓"`).

### 7.5 The kit

`texstage kinds check <name>` is the test every kind passes, texstage's own ones too: it loads the
kind, checks its options, runs its fixtures (an entry and the check it must give, against a seed
and references) - among them the entries that must neither reach out nor bring a worker down:
for SPARQL `SERVICE` in every spelling, `\u` escapes too, and for every kind nesting beyond its
parser's cap (11) -, compares its texts in English and German, loads its browser modules in Node
as a phone has them - no network, imports from its folder alone, none of Node's own globals, under
Node's permission model -, measures what a phone loads for the kind - a warning above 200 KB
compressed, a refusal above 1 MB (7.3) -, and reports each fixture's time against the budget. A
kind's own tests come on top. The kit finds a kind's mistakes; it is no sandbox for a kind that
means harm, whose Python runs on the server anyway.

## 8. In LaTeX

### 8.1 The environment

`texactivity.sty` keeps its environment and becomes general: it knows the core's keys and records
the others for the kind, which checks them at build - so a new kind needs no change of LaTeX. One
step, as short as today:

```latex
\begin{frame}[t,fragile]{Exercise 2, Live}
  \begin{activity}[id=prof-lectures, kind=sparql-query, seed=data.ttl, points=standard,
                   tokens={SELECT, WHERE, a, :Professor, :name, :taughtBy, :title}]
    \prompt{For every professor, the titles of the lectures they teach.}
    \reference{SELECT ?name ?title WHERE {
  ?professor a :Professor ; :name ?name .
  ?lecture :taughtBy ?professor ; :title ?title .
}}
  \end{activity}
\end{frame}
```

Several steps, each an overlay of the frame, so that the clicker goes through them:

```latex
\begin{frame}[t,fragile]{Exercise 3, Live}
  \begin{activity}[id=lecture-titles, kind=sql-query, seed=uni.sql]
    \reference{SELECT p.name, l.title FROM professor p JOIN lecture l ON l.taught_by = p.id}
    \step<1>[id=write, time=180, projector=count]
      \prompt{The titles of the lectures each professor teaches.}
    \step<2>[id=vote, kind=choice, from=write, choices=4, points=standard]
      \prompt{Which of these is right?}
    \reveal<3>
  \end{activity}
\end{frame}
```

A `\step` runs to the next `\step` or `\reveal`, as an `\item` does, so that what belongs to it -
its `\prompt`, its own `\reference` - is never inside another command's argument: `\reference`
is read verbatim and could not be. A `\reference` before the first `\step` is the activity's,
for every step without one of its own; predict-then-do gives each step its own - `\reference{42}`
after "How many rows?", the query after "Now the query." `\step` and `\reveal` exist inside the
environment only, as `\prompt` does.

- The core's keys: `id=`, `kind=`, `limit=` (entries per student and step: 5 for queries, 10 for
  fields, as today), `counts=latest|all` (a student's latest entry replaces the earlier ones -
  queries -, or all count - triples), `credit=latest|best` (which entry earns the points), `gap=`
  (seconds between two entries: 5 for queries, 2 for fields, as today), `time=` (seconds, as a
  quiz's), `budget=` (a check's CPU time in ms, at most the kind's), `feedback=`, `projector=`,
  `solution=` (5.3), `points=standard|double|none` and `speed` (section 14), `open=auto|manual`,
  `from=`, `width=`, `height=`. Given on the activity, they are the defaults of its steps. A text
  has at most 2,000 characters, as today.
- `\prompt`, `\reference` and `\seed` as today (LA section 5): `\prompt` is typeset, `\reference`
  and `\seed` are read verbatim, several references allowed; a step's `\prompt` becomes its phone
  picture.
- A step can also be a later frame: `\activitystep{lecture-titles}{vote}` there shows that step -
  for a vote that needs a slide of its own.
- `\activityview[step=write]{lecture-titles}` puts a step's picture on any later frame, to read
  only: the groups again when the lecture discusses them.
- `\activitysetup{...}` sets the defaults of a deck, as `\quizsetup` does.
- The old keys stay as aliases until the decks have moved: `input=tuple` is `kind=triples`,
  `input=code, engine=sparql` is `kind=sparql-query`, and so on (section 17).
- PowerPoint shows an activity's static form, as today (CT principle 3).

### 8.2 The slides drive the steps

The present compile records which page is which step and phase, as it records a quiz's pages
(`G|kind|id|phase|page`, `build/types.py`). The type's `slide` hook (`server/types.py`) moves the
activity when the projector shows a page: to step 2 on the second overlay, to the reveal on the
third. Today the hook learns only which items a page shows (`server/bundles.py:55-60`); it learns
their step and phase from these records too. Without overlays, the frame opens the activity and
leaving it closes it, as today.

The clicker alone can run a whole activity (decided 2026-11-09): the first page opens *write*
and its timer closes it, the second opens the vote with its choices made without the lecturer
once *write*'s last checks are in (5.1), the third reveals. Only the panel and the keys pause,
add time, reopen, moderate, and pick a vote's choices by hand (section 13).

## 9. In the build

`build/activity.py` stays the type's build step and asks the kind: `build(options, bodies, files)`
checks the kind's keys and gives the public item, the private keys and the files for the bundle
(the seed, content-addressed as today). The references are checked at build time by the checker
the server uses: one that does not run stops the build, rather than showing in the panel during
the lecture (LA section 8.5), and the solutions can show its result. The build records the
references' keys; the server checks them again when a bundle comes - uploaded, or found when it
starts - and says in the deck list, not during the lecture, when its engine gives other keys
(another SQLite, say). The record lines name their fields (`activity|id=...|kind=...`) instead
of counting on their positions, and one module reads them. The build also says how much a phone
loads for the deck's kinds together, since the limits of 7.3 are a kind's alone.

## 10. On the server

### 10.1 An entry's way

1. A phone sends `activity.enter {activity, step, entry, text | fields | choice}`: the phone
   makes the entry's id (today the server does, `server/activity.py:531`). A repeated id gets the
   reply it got before - from the reply cache while the server runs (`server/app.py:630-634`: per
   player, in memory), from the stored entry after a restart, since an entry's id is unique.
2. The event loop checks what the core knows - the step is open, the student is not blocked, not
   too fast (`gap=`), not over the limit, the text not too long - and looks the text up among the
   step's known texts. No kind code runs here.
3. The entry is stored with the next group of writes (10.2) and acknowledged: `{entry, state}` -
   `checked` with what `feedback=` allows of the verdict, if the text was known; else `waiting`.
4. A new text goes to the pool's worker for normalizing (the kind's `normalize`, quick, 10.3);
   only a normalized form the step has not seen is queued for a check, once. Entries with the
   same text or the same form wait for that one check; a queued check that no entry waits for
   any more - its entry replaced (`counts=latest`) or withdrawn - leaves the queue.
5. The check comes back: it is stored; the entries that waited for it get it, their groups count
   them, their phones get their state; the picture's version goes up, and the windows fetch it at
   most four times a second.
6. At the reveal, each student's entry that earns the points gives its credit, the ledger its
   rows (section 14), and every phone its verdict and points.

### 10.2 Storage

Tables of the type (the `ROWS` of `server/types.py`, every one with its `session`):

- `entries`: id, activity, step, epoch, player, created, input (JSON), norm (the hash of the
  normalized input), state (`in`, `replaced`, `withdrawn`, `hidden`).
- `checks`: activity, step, norm, status, key, parts, verdict, credit, message, at, aside (a text
  set aside, 6.3), form (the normalized input itself: what its group is shown by, 5.1) - one per
  distinct input. A reset keeps them: the same text has the same result.
- `details`: activity, step, key, detail - one per group (LA's `results`).
- `ledger` (the core's, for quizzes too): player, source (`quiz` or `activity`), item, part (a
  round or a step), epoch, points, bonus, created - one row per player, part and epoch, so that a
  reveal repeated after a restart gives nothing twice.
- `steps`: activity, step, epoch, phase, the time left, who paused it, its turn (the step whose
  turn is the highest is the current one), the vote's choices (F3).
- `moderation`: the act's number in its game, activity, step, epoch, act, the group or term or
  entry it is on, a term's role, what a term is merged into, whether it takes an earlier act back, a value
  (the crowd graph's minimum; the entries a block hid and those it found hidden), created, undone - every act a row, so that
  it can be undone: what holds is what the acts that are not undone say, in their order (F2's
  plan, 4.3). No row names a student.

In memory, per step: the entries by student, the groups by key with their students, the counts -
what the views read, so that no view goes through the entries. Writes are gathered and committed
every 50 ms in one transaction (SQLite in WAL mode, as the store is, `server/store.py:50-51`),
not one transaction per call as the game's engine does today (`server/game.py`). A restarted
server goes on where it stopped, as today (`server/store.py:5-6`): it rebuilds what is in memory
from the tables, queues the entries still unchecked again - those that wait and those that are
`internal`, but for the texts set aside (6.3), which the tables keep as such -, and the workers
prepare again (10.3).

Entries keep what students typed, the ledger how each did; both stay as long as their game, as
the quiz's answers do. How long a server keeps games is not settled yet - for quizzes neither
(section 19).

### 10.3 The pool of workers

- The workers start with the server and wait: starting a Python process takes a noticeable part
  of a second on Windows, too long to start one for a burst. As many as the cores less two, at
  least one; at a low priority (`BELOW_NORMAL_PRIORITY_CLASS` on Windows, `nice` elsewhere), so
  that the presenter window, PowerPoint and the projector stay smooth. Two more wait as
  spares (F2's plan, 4.6: one covers one ending at a time): when the pool ends a worker
  (section 11), a spare takes its place at once, and a new spare starts. And one more normalizes
  and does nothing else: quick jobs, which never wait behind a check (10.1).
- Workers prepare a deck's activities (`prepare`) when the deck is loaded - for a large seed, one
  slide before its activity -, the spare too, so that a slide change never waits for a seed; the
  references are checked first. They drop what they prepared when the deck goes. On a hosted
  server each running deck gets some of the workers, which prepare that deck only.
- A job is one distinct entry. The queue takes the open step's first - the students in turns, so
  that one student's many texts do not hold up the others -, then what closed steps still wait
  for; on a hosted server it takes the sessions in turns, so that one class's burst does not
  hold up another's.
- Budgets and limits: section 11.

### 10.4 Messages

One namespace for every kind; a kind has no messages of its own:

| from | message |
|---|---|
| phone | `activity.enter {activity, step, entry, text \| fields \| choice}` -> `{entry, state}`; `activity.withdraw {activity, step, entry}` |
| presenter window | `activity.open` (a ready step, or a closed one again), `activity.close`, `activity.pause`, `activity.resume`, `activity.next`, `activity.reveal`, `activity.reset` `{activity, step?}`; `activity.time {activity, step, add \| stop}` |
| presenter window | `activity.moderate {activity, step, act, group?, into?, entry?, on?}` - `act`: `show`, `hide`, `merge`, `unmerge`, `approve`, `pick` (a group as a choice of a later step), `block` (the entry's student) |
| presenter and projector windows | `activity.view {activity, step}` -> the picture (a read, as LA's) |
| the lead window (13) | `activity.layout {activity, step, at}` - in bulk, so the hosts get it with their next push (LA section 7.5, item 9) |

A phone gets the step's state in two parts: the step's own - the same for every phone, so it is
serialized once and sent 1,000 times - and its own entries and verdicts, small, as they change.

### 10.5 The archive

Per activity, in the game's folder of the lecture archive (LA section 11): `activity-<id>.csv`, a
row per entry with its step and epoch, without names; `activity-<id>.json`, each step's final
picture; and the files of its reduction - the crowd graph's SVG.

## 11. Checking on the server, safely

Students' texts now run on the server - on the lecturer's laptop, too. The kinds are trusted;
the texts are not.

- **In worker processes, never in the server's:** a crash or a runaway query takes down a worker,
  not the class. The pool starts a new one.
- **A budget of CPU time per check** - the kind's, at most 10 s; a step may set less with
  `budget=` -, not of the clock's, so that a laptop kept busy by PowerPoint does not turn a quick
  query into a timeout (decided 2026-11-09). CPU time still varies with the clock speed and the
  kind of core, so a budget lies far above what a right query needs: milliseconds against
  seconds. The pool reads every busy worker's CPU time with psutil (BSD-3-Clause, packages for
  Windows, macOS and Linux; a new dependency of the core). SQLite stops a query from inside (its
  progress handler), and its worker goes on; pyoxigraph is stopped between solutions where its
  results stream, and where they do not - its `Store.query` has no timeout (F0, Q2) -, the pool
  ends the worker, and the spare takes its place (10.3). A check over its budget is a `timeout`,
  the student's. The clock stays as a backstop at five times the budget: a check
  it stops is `internal`, as is one whose worker died for another reason.
- **Once more, then never again:** an `internal` check runs once more, on a fresh worker; failing
  again, it stays `internal`, and its text is set aside for the step, so that no third worker
  dies for it (6.3) - unless the worker was stopped from outside, as Ctrl+Break on Windows or a
  stop of the whole process group stops it: its exit code says so, and that is not the text's
  doing (F1's package 4: a server stopped that way had set the texts being checked aside). Texts
  that end a worker exist: in pyoxigraph 0.5.13, 800 nested groups overflow its
  parser's stack and end the process - 512 parse, and today's limit of 2,000 characters allows
  about 660 -, and `ORDER BY` with two keys over mixed literals ends it too (F0, Q2 and Q3). So
  the checks run on a thread with a 64 MB stack, a kind refuses what its parser chokes on before
  it parses - nesting beyond a cap -, and the kit tests it (7.5).
- **Memory** (decided 2026-11-09): SQLite caps its own memory on every system with
  `PRAGMA hard_heap_limit`, which the kind sets in `prepare`, before its authorizer refuses
  `PRAGMA` (the SQLite 3.50.4 of the Python 3.14 that texstage is developed with has it). The cap
  holds for the whole process, so the kind sets it to what the prepared seeds take plus what a
  text may use. For the rest - Oxigraph above all - a watchdog in the pool reads every worker's
  memory (psutil, as above) every 50 ms and ends a worker over its limit, which likewise counts
  from what the worker holds prepared, on all three systems; a job object on Windows (through
  ctypes: psutil makes none) and `RLIMIT_AS` on Linux stay as the systems' hard stop. What
  remains on a Mac is a short overshoot of a few hundred megabytes, not a frozen laptop - not
  measured yet: CI runs Linux and Windows only. A text over its memory is the student's `error`
  only if it runs over on a fresh worker too, since memory built up before it is never its fault;
  its message says so. SQLite's own cap is the exception (decided 2026-11-10): SQLite stops the
  query from inside and counts only what its seeds and the query hold, alike in every worker, so a
  fresh one comes to the same - the text is the student's `error` at once, and no worker ends for
  it (the second review of F1's pool: a forgotten join condition with `ORDER BY` ended two). And
  since `PRAGMA hard_heap_limit` can only lower the cap, which a smaller seed after a larger one
  then set below what the larger one held, the cap is set through SQLite's own
  `sqlite3_hard_heap_limit64` (ctypes), from everything the worker's SQLite holds; the pragma
  stays for a Python whose SQLite ctypes cannot reach. The limits on a result's size stay as
  today (rows, triples: LA section 12).
- **No network, no files:** the seed is in memory before any student's text runs; SQLite runs in
  memory, with an authorizer that allows reading and refuses `ATTACH`, `PRAGMA` and the like, and
  without extensions, its temporary storage in memory (else a large sort spills to files: F0, Q6).
  SPARQL needs more than today: pyoxigraph runs `SERVICE` over HTTP - 0.5.13 connects, `SILENT`
  hiding the failure, and its `Store.query` has no option to switch it off (F0, Q1) -, while
  today's refusal is the WebAssembly build's own (`web/engines/sparql.js:134`), behind the
  worker's CSP - and both go. So the kind refuses `SERVICE` before the query runs, by tokens
  that read variables and prefixed names whole, after decoding the `\u` escapes, which SPARQL
  decodes before it parses: looking for the word in the raw text is not enough, and finds
  `?service` too. Each kind says how its engine is kept from the outside, and its
  fixtures show it to the kit (7.5). A hosted server can add a barrier of the system's, a
  firewall rule for its workers; a lecturer's laptop cannot be asked for one.
- **Not in this design:** kinds that run students' programs - Python, JavaScript. They need a
  real sandbox (a container, or a WebAssembly runtime such as wasmtime) and come when a subject
  needs them.

## 12. On the phones

- **One thing at a time,** as today: the quiz's round while one is open - it pauses the open
  step (5.2) -, else the current step of the open activity, else the waiting screen.
- **One screen for every kind:** the prompt, the input (the core's or the kind's), *Send*, the
  student's entries and their states, in the deck's language.
- **An entry's states:** sent; received (the server has stored it); being checked; then what
  `feedback=` allows - it runs, a syntax error (in line 2, where the engine says), right, wrong,
  the kind's message -; and after the reveal the verdict and the points.
- **Hints** while the student types (7.3); verdicts come from the server only.
- **Sending survives the network:** a phone that loses its connection sends its entry again with
  the same id, and gets the same reply (10.1).
- **What a student typed shows as text,** never as HTML, in every window (LA section 10).
- An iPad that presents checks nothing any more (3.1).

## 13. In the windows

- **The panel** in the presenter window is the same for every kind: the activity and its steps,
  the phase, the timer (+30 s, stop), the counts - students, entries, checked, waiting, unchecked
  -, the groups with their details (the kind's `group`) and their buttons, and a small copy of
  what the projector shows.
- **The controls** are the same for every activity, in the panel and as keys of the presenter
  window: *Open* (a closed step too), *Close*, *Pause*, *Next step*, *Reveal*, *Reset step*, the
  time; on a group *Show* (on the projector), *Hide*, *Merge* (where its reduction allows it),
  *Approve* (when the step reviews), *Pick* (as a choice of a later step); on an entry *Block*
  its student. Every moderation can be undone; a reset asks first. The slides open, close, go to
  the next step and reveal (8.2); the rest needs the panel or the keys.
- **The box** on the slide draws the picture with the core's view or the kind's, under the ink,
  the same in the presenter and the projector window (LA section 9).
- **The lead window:** what every window must draw alike and one must compute - the crowd graph's
  layout - is computed in one presenter window and sent to the others (LA's lease, kept for this
  alone, LA section 9). No window is needed for checking.
- **The host console** shows the open activity, its step and phase - today it shows nothing of
  activities.

## 14. Points

- **One ledger for everything:** a row per student and source - a quiz's round or an activity's
  step - with points and bonus. A student's score is the sum of their rows; the leaderboard and
  the podium read it. The quiz goes on computing its points as today - speed, streaks, the rewind
  (`again`) - and writes them to the ledger. Its `_rescore` rebuilds every score from the quiz's
  rounds alone (`server/game.py:587-592`); with the ledger it rebuilds the quiz's rows and leaves
  the activities' alone.
- **A step's points** are its points - `standard` (1,000) or `double` (2,000), as a quiz's - times
  the credit of the student's entry that earns them (`credit=latest|best`); with `speed`, on a
  step with `time=`, less with time, as the quiz's (`scoring.speed_points`). Writing a query is
  no race: `speed` is off unless a step asks for it.
- **Given at the reveal,** not with each check: the leaderboard moves when the lecturer chooses,
  and a later entry cannot take points back. An entry still unchecked at the reveal gives its
  points when its check comes - with `credit=latest` it is the one that counts, not an earlier
  checked one -, and the leaderboard moves once more then. A reset after the reveal takes the
  step's points back.
- **A technical failure is never a wrong answer:** an unchecked entry gets its points when its
  check comes; one whose check failed twice (11) earns nothing - with `credit=best` the
  student's best checked entry counts instead -, and the panel says how many there are.
- Whether activities count towards the quiz's leaderboard is the deck's choice
  (`\activitysetup{leaderboard=...}`); a step with `points=none` (the default) is practice.

## 15. 1,000 students

### 15.1 The budgets

Measured with 1,000 simulated phones on a second machine, over Wi-Fi, against the server on the
presentation laptop, with the presenter window, and PowerPoint or the projector window, running:

| | budget |
|---|---|
| an entry acknowledged | under 0.5 s for 95 % of the entries, in a burst of 1,000 within 10 s |
| its verdict | under 3 s for 95 %, in the same burst, for checks of a few milliseconds each |
| a phase change on every phone | within 0.5 s |
| the projector's picture | at most four updates a second |
| a slide change in the presenter window | under 100 ms throughout (texstage-requirements.md, section 4) |
| the kinds' files on a phone | within 30 s of its join for 95 % of the phones, 1,000 joining within two minutes and loading 200 KB each, while the budgets above hold |

What there is to start from: the quiz's load test (design.md, section 8, M6) - 1,000 simulated
phones on the same laptop as the server, a slide on the last phone within 0.27 s, answers
accepted within 19 ms (95 %); and LA's 300 phones (LA section 12).

Three things the measurement adds. The burst runs also with 1 % of the texts running into their
CPU budget, and F0 reports what that does to the others' verdicts. The server takes at most
1,000 players today (`max_players`, `server/game.py:82`); the setting rises, so that 1,000
students have room, and F0 simulates 1,100. And one machine that plays 1,000 phones over Wi-Fi
measures the server and one link, not a hall's Wi-Fi with 1,000 radios: that, only a lecture
shows (F5).

### 15.2 How the design keeps them

- **The same work for every entry,** however large the class: an entry is checked for limits,
  normalized, looked up, stored, acknowledged; a new input queues one check, whose result changes
  its group's count - no pass over all entries, no picture per phone (3.1).
- **Equal inputs are checked once:** the server keeps the check of every distinct normalized
  input per step, so the hundredth student with the same query gets the verdict at once - for
  the same text from the event loop alone, for another spelling after one quick round trip to the
  normalizing worker (10.1).
- **Writes in groups:** stored every 50 ms, acknowledged once stored (10.2).
- **A pool of workers, ready** with the deck prepared (10.3).
- **Pushes:** a phone gets its own changes at once, and only those; a phase change is one
  message, serialized once (10.4); the projector and the panel get the picture at most four times
  a second.
- **Bytes before the moment:** a phone loads the kinds' files when it joins and a step's prompt
  picture while the slide before is shown, so that 1,000 phones do not fetch them in the second
  the step opens.
- **Limits that fit 1,000:** 10,000 entries and 2,000 distinct inputs per step (LA: 5,000 and 500
  per activity); beyond 2,000 the panel says so and new texts wait, as in LA.

### 15.3 Python or Rust

Python first, decided by measurement:

- The plugin system was slow by its architecture, not by its language: a fresh worker for every
  submission, a transaction for every request, every connection's view built from all the state
  (3.2). Rust would have fixed none of them; this design removes them.
- The heavy work is native already: SQLite is C, Oxigraph is Rust (pyoxigraph); Python hands
  them the text.
- Python already serves 1,000 phones in the quiz (15.1), with one process.
- Rust's costs: a kind's author would need Rust; compiled packages for Windows, macOS and Linux;
  a Rust toolchain in CI; and a rewrite of about 6,000 lines of the live server before anybody
  knows that it is needed.

So the core is written in Python as above, and measured first (section 18, F0). What the
measurement shows to be slow moves to Rust piece by piece, through PyO3; a kind whose checker is
slow ships it compiled. The first such piece may come ready-made: orjson (Rust; Apache-2.0 or
MIT) for the JSON of every message. The contract does not change: a check is data in, data out,
in a worker.

## 16. On the laptop or hosted

The same program, as today (CT section 9):

- **On the laptop:** the phones reach it on the room's network or a hotspot, or through the
  tunnel where the network keeps devices apart (eduroam does). 1,000 phones through the tunnel
  have not been measured, and the device test saw the tunnel's connections break (LA section
  15); the measurement (F0) includes the tunnel.
- **Hosted:** the operator installs the kinds; the classes on the server share its pool of
  workers - each running deck some of them, which take its checks in turns (10.3) -, and the
  operator can keep the workers off the network with a firewall rule (11).

## 17. From today's activities to kinds

| today | kind | package, in `kinds/` (7.2) |
|---|---|---|
| `input=tuple` - the crowd graph | `triples`: input `fields`, reduction `crowd`, the core's graph (6.2) | texstage-kinds-rdf |
| `input=code, engine=sparql` | `sparql-query`: pyoxigraph on the server | texstage-kinds-rdf |
| `input=code, engine=turtle` | `turtle-graph`: pyoxigraph's Turtle parser | texstage-kinds-rdf |
| `input=code, engine=sql` | `sql-query`: Python's sqlite3 on the server | texstage-kinds-sql |

- The checks move from JavaScript in the presenter's browser (`web/engines/`,
  `web/stage/evaluator.js`) to Python on the server. The canonical forms and summaries (LA
  sections 8.3, 8.4, 8.9) are written anew in Python; today's engine tests
  (`tests/web-activity-engine.test.mjs`, `tests/web-activity-sql.test.mjs`,
  `tests/web-activity-turtle.test.mjs`) become the kinds' fixtures, so that both give the same
  groups.
- pyoxigraph is the Oxigraph of today's WebAssembly build, so the results of SPARQL and Turtle
  stay as the class saw them. SQL changes from sql.js's SQLite to the one of the server's Python;
  the old engine tests, as the kinds' fixtures, show where the two differ - the build cannot,
  since it runs Python's SQLite too.
- `triples` needs more than a text and one key: today's tuples clean every field - control
  characters out, a phone's typographic quotes made Turtle's -, key it by `terms=` and mark
  literals (`server/activity.py:172-207`, `:537`). In the kind, `normalize` cleans, the check's
  `parts` carry each field's key and whether it is a literal (6.3), and the lecturer's merges
  stay the core's (13).
- The KG lecture's decks build unchanged, through the aliases (8.1), and give the same groups -
  the migration's test. The archive changes a little: its CSV gains the step and the epoch
  (10.5), and the status `syntax` becomes `invalid` (6.3).
- What goes: the evaluator in the presenter's browser, its lease and its messages
  (`activity.work`, `activity.result`), its worker's CSP - the pages' replaces it (7.3) -, the
  engines' two tables. What stays: the boxes, the graph's layout and its labels (LA section 9),
  the archive's files (LA section 11), the phones' inputs (LA section 10).

## 18. Plan

The semester runs: the lectures stay on `main`, and each stage is built on a branch and comes to
`main` once its test of done has passed with the lecture's decks - as LA did (LA section 14). The
lectures themselves run lecture-tools' copy of texstage, so a stage reaches them when
lecture-tools takes it (the plans' sections 2).
The riskiest part comes first: checking on the server, with today's kinds behind today's
messages, before the core and the steps are built on it. Each stage has its test of done. F0
and F1 are planned in detail in [activity-framework-plan.md](activity-framework-plan.md), F2 in
[activity-framework-plan-f2.md](activity-framework-plan-f2.md); F0's report is
[activity-framework-f0.md](activity-framework-f0.md).

| | what | done when |
|---|---|---|
| F0 | a spike: an entry's way through a pool - stored, normalized and checked under its CPU-time budget and memory watchdog, its verdict, the pushes - with the `sql-query` and the `sparql-query` checkers, among them a runaway SPARQL query and a worker ended and replaced; pyoxigraph 0.5's `SERVICE` and whether it can stop a query from inside; `tools/simulate.py` with a burst, mostly distinct texts, the kinds' files over HTTP and 1,100 phones, run from a second machine; the presenter window timed | the budgets of 15.1 measured on the presentation laptop over Wi-Fi and through the tunnel; `SERVICE` off, or refused after decoding; Python kept, or the slow piece named |
| F1 | today's four kinds checked on the server, behind today's `activity.*` messages and LaTeX: the pool, the safety of section 11, a restart that goes on | the KG lecture's decks run unchanged and give the same groups; the evaluator in the browser is gone; 1,000 phones within the budgets |
| F2 | the core and the contract (API 0), cut from those four kinds: phases with reopening, entries, checks, groups, pictures, moderation, the panel, the phone's screen; the kit; the four as packages in `kinds/` (7.2, 17); `choice`, `number`, `text`; the pages' Content-Security-Policy (7.3) | the four kinds and texstage's own pass the kit; the KG lecture's decks give the same groups as with F1 |
| F3 | several steps and points - write-then-vote and write-see-fix first (5.1) -: `from=`, overlays, the vote's choices, the ledger shared with the quiz | write-then-vote and write-see-fix run by the clicker; the quiz's scores the same as before the ledger |
| F4 | a kind of another subject, installed separately - functional dependencies, relational algebra or normal forms from the DBIS lectures; then the shared kinds move to texstage-plugins (7.2) | it needs no change of the core - or the contract changes; then the contract is called API 1 |
| F5 | a dry run in a lecture, steps and all | the class used it; the archive has it |

## 19. Open questions

The first draft's seven - what a kind may do, where kinds live, which steps first, memory on
macOS, timeout or internal, hints, polls - were decided on 2026-11-09 (section 2), and so were
the six that close the gaps a critical review found the same day - the order of the work, API 0
until F4, failed checks, reopening, the automatic vote, the word *kind* - and, the same day, the
last proposals: Python first, the name *step*, a step's defaults with `solution=`, the sizes on
the phones, and short checks first. Every row of section 2 is decided. Whether pyoxigraph 0.5 can
switch `SERVICE` off or stop a query from inside, F0 found out: it cannot (section 11). Still
open:

- **To find out on the way:** how far a Mac's memory overshoots, and whether a budget holds on
  efficient cores (section 11; F0, Q5); whether texstage-plugins is renamed when the kinds move
  there (after F4).
- **Not settled:** how long a server keeps games - their answers, entries and ledger (10.2).
