# texstage - live activities (design)

Status: 2026-10-18 - built through L5, the dry run in the KG lecture, with a second engine (SQL)
since, and a third (Turtle, 2026-10-21, branch `texstage-turtle-engine`); what is done and what is
left: section 14. Branch `texstage-live-activities`.
Decided on 2026-10-17: student input is evaluated in the presenter's browser, and the first
milestone builds the shared framework together with two pilots - a crowd graph from triples, and
SPARQL queries clustered by their results. It builds on
[content-types-design.md](content-types-design.md) (the core and its content types, here **CT**)
and takes its input from a proposal of 2026-10-17: every live interaction as a pipeline *Input ->
Evaluate/Cluster -> Reduce -> Visualize*, with five kinds of phone input, three ways of reducing
what comes in, moderation in the presenter window, one LaTeX environment and a small engine per
course. This design says which of it texstage builds first, where each part lives, and what the
core needs for it. File references are to `src/texstage/` unless they name another folder.

## 1. Idea in one paragraph

Today the phones answer quizzes: one answer per student and question, judged against a key, shown
as a distribution. A **live activity** lets the class build something together while the slide
shows it grow: the students send many small contributions - triples, queries -, texstage reduces
them to one picture - a graph that grows and is merged, clusters of queries with the same result
-, and the lecturer moderates that picture and puts parts of it on the projector. It is a new
content type, `activity`, a vertical slice like the video (CT section 3): a LaTeX package, its
step in the build, its part of the server and of the windows - and, new for a type, a screen on
the phones. What is specific to a course - running a SPARQL query - is an **engine** that runs in
the presenter's browser; the server only collects, counts and groups, and runs nothing (CT
principle 1).

## 2. Decisions

| Topic | Decision | |
|---|---|---|
| Where student input is evaluated | in the presenter's browser: an engine compiled to WebAssembly, served by texstage itself, in a worker; the results go to the server as data | decided 2026-10-17 |
| First milestone | the framework and both pilots: the crowd graph from triples and SPARQL result clusters | decided 2026-10-17 |
| Phones | never run code (CT, decided 2026-10-10): they send text and get states | kept |
| Engines | modules of texstage, chosen by name in the deck - no code in decks or bundles, no plug-ins (CT principles 1 and 2) | follows |
| Scope of the framework | what the pilots need: two inputs (`tuple`, `code`), two reductions (crowd, clusters), two views (graph, clusters); the rest of the proposal is listed with what it needs (section 13) and built when a deck needs it (CT principle 5) | proposed |
| SPARQL engine | Oxigraph (Apache-2.0 or MIT), its WebAssembly build from npm, vendored - for the pilots; the trial (8.7) found it fast and small, and one difference of substance from rdflib | proposed, tried 2026-10-17 |
| SQL engine | sql.js 1.14.2 (MIT; SQLite, public domain), its browser build vendored - the second engine, which checked the interface (8.3, 8.8) | asked for 2026-10-18 |
| Turtle engine | the students write a graph in Turtle, clustered by the graph it denotes - for the KG lecture's chapter 3, "one graph, many spellings"; Oxigraph's Turtle parser, the SPARQL engine's library, and its canonical form for a CONSTRUCT's graph, so that one graph has one key in both (8.9) | asked for 2026-10-21 |
| PowerPoint | activities are texstage's; PowerPoint shows their static form (CT principle 3) | follows |
| Names | `texactivity.sty`, the environment `activity` and its keys (section 5) | decided 2026-10-17 |
| Phones before the reveal | a phone learns whether its query runs (a Turtle text: whether it is valid Turtle), and the engine's syntax error - never its result (section 10) | decided 2026-10-17 |
| Live notebook cells | none: texstage's live content is interactive content. CT's live cells (N5) and Python cells in the browser (N6) are dropped; prepared results (N4) are not affected | decided 2026-10-17 |
| Pilot frames | a new frame in the KG lecture's `02-RDF` (the crowd graph) and exercise 2 of `05-SPARQL/014.tex` (section 14, L5) | decided 2026-10-17 |

## 3. From the proposal to texstage

L: in this milestone (section 14); later: section 13.

| the proposal | in texstage | |
|---|---|---|
| Input -> Evaluate/Cluster -> Reduce -> Visualize | phone -> presenter's browser (the engine) -> server (the reduction, data only) -> presenter and projector windows (the box's renderer) | L |
| five phone inputs | `tuple` (N fields with suggestions) and `code` (text with a token bar); `visual-target`, `state-walker`, `parametric-point` later | L / later |
| `CrowdStateAccumulator`: union, frequency, merge | the reduction *crowd* on the server: terms normalised as the word cloud groups answers, counted by students, merged by the lecturer | L |
| `EvalClusterEngine`: evaluate, hash, group | the reduction *clusters*: the presenter's browser evaluates and sends a key per input, the server groups by key | L |
| `AdversarialScoreboard`: rules x submissions | clusters by the vector of the rules' outcomes - needs an engine that runs rules | later |
| cluster inspector, push to the projector | the activity's panel in the presenter window; *Show* puts a cluster's example query (anonymous) and its result on the projector | L |
| pen lasso and drag: merge | *Merge* in the panel; on the slide the pen writes ink, so merging there needs a mode of its own | L / later |
| quarantine, top-K | hide a term or a contribution, block a student (as Q&A blocks), a minimum count for the projector, optionally review before anything shows | L |
| freeze and snapshot | *Close* stops the input; the archive keeps the contributions and the final picture; the picture in the annotated PDF later | L / later |
| `liveactivity` with `seeddata`, `\phoneprompt`, `\quicktokens`, `\referencesolution` | `activity` with `seed=` or `\seed{...}`, `\prompt{...}`, `tokens=`, `\reference{...}` or `reference=` (section 5) | L |
| a `<div data-config>` in a web build, `\fallback` in the PDF | the present compile records the box, the build writes the item into `deck.json`; every PDF shows the static form | L |
| `CourseDomainPlugin`: `initSeed`, `evaluate` -> `{valid, syntaxError, output, canonicalHash, highlightTargets}`, `onLecturerMerge` | an engine module: `start(wasm)`, `load(lib, seed)`, `evaluate(state, text)` -> `{status, error, canonical, summary}`; the framework hashes `canonical`; merges are the server's, on data; highlights later | L |
| Oxigraph, EYE-JS, shacl-engine, DuckDB-WASM, sql.js, Graphology, MiniSat, Pyodide, ONNX | Oxigraph for SPARQL and for Turtle (8.9), sql.js for SQL (8.8); each other engine when a deck needs it, vendored with its licence checked | L / later |

Two points of the proposal change on the way:

- **No plug-ins from decks.** The proposal loads a course's plug-in "dynamically by slide
  metadata". In texstage a bundle is data, never code, and all types live in the package (CT
  principles 1 and 2): an engine is a module of texstage (`web/engines/sparql.js`), a deck only
  names it. A course that needs a new engine gets it in texstage - a few dozen lines around a
  vendored library, as the proposal estimates (the SQL engine: 139 lines, 8.8; the Turtle engine:
  129 lines around the SPARQL engine's Oxigraph, 8.9).
- **The interfaces are cut from the pilots.** The proposal designs five inputs, three reductions
  and a plug-in interface in advance. CT principle 5 builds what the first users need and lets
  the next one check the cut: the pilots need two inputs, two reductions and one engine; the
  engine interface (section 8.3) is cut from the SPARQL engine and was checked by the second, SQL
  (2026-10-18), and by a third, Turtle (2026-10-21), which needed no change of it. Inputs,
  reductions and views are still one choice (`input=`); the next input that is neither `tuple`
  nor `code` splits them.

## 4. An activity in every layer

| layer | crowd graph (triples) | SPARQL clusters |
|---|---|---|
| LaTeX: handout | the box with the prompt and "live activity" | the same; the solutions add the reference query |
| LaTeX: present | the box recorded; the prompt as a phone picture | the same |
| build | the item in `deck.json`: fields, suggestions, limits | the item: engine, tokens, the seed (a file in the bundle); the reference in `keys.json` |
| PowerPoint | the slide picture with the static form | the same |
| server | contributions, terms, counts, merges, moderation | contributions, keys from the presenter's browser, clusters; the reference's marked after the reveal |
| presenter window | the graph in the box; the panel: terms, merge, hide, minimum; the layout for every window | the clusters in the box; the panel; **the evaluator**: Oxigraph in a worker |
| projector | the graph, at the positions the presenter window sends | the clusters; a shown cluster's query and result |
| phones | three fields with suggestions; my triples, to withdraw | the query with a token bar; its state: waiting, runs (Turtle: valid), syntax error |

## 5. In LaTeX: texactivity.sty

```latex
\usepackage{texactivity}
...
\begin{frame}[t]{Our Lecture as a Graph}
  \begin{activity}[id=lecture-graph, input=tuple, fields={Subject, Predicate, Object},
                   suggest={:KG, :teaches, :attends, :isAbout}, limit=10]
    \prompt{Add triples about this lecture: who teaches it, who attends, what it is about.}
  \end{activity}
\end{frame}

\begin{frame}[t,fragile]{Exercise 2, Live}
  \begin{activity}[id=prof-lectures, input=code, engine=sparql, seed=data.ttl,
                   tokens={SELECT, WHERE, a, :Professor, :name, :taughtBy, :title, ?name, ?title}]
    \prompt{For every professor, the titles of the lectures they teach.}
    \reference{SELECT ?name ?title WHERE {
  ?professor a :Professor ; :name ?name .
  ?lecture :taughtBy ?professor ; :title ?title .
}}
  \end{activity}
\end{frame}

\begin{frame}[t,fragile]{Your Turn: Berlin in Turtle}
  \begin{activity}[id=berlin-turtle, input=code, engine=turtle, seed=turtle-prefixes.ttl,
                   tokens={dbr:Berlin, rdfs:label, dbo:populationTotal, "Berlin"@de, "Berlino"@it}]
    \prompt{Berlin in Turtle, as compactly as you can: its two labels and its population.}
    \reference{dbr:Berlin rdfs:label "Berlin"@de , "Berlino"@it ;
           dbo:populationTotal 3596999 .}
  \end{activity}
\end{frame}
```

The environment stands where its box goes on the slide. Keys:

- `id=` (required; lowercase letters, digits and dashes, as a quiz's; it also names the
  archive's files); `input=tuple|code`; `width=`, `height=` for the box (default: the line's
  width, 0.6 of the text height); `limit=` contributions per student (default 10 triples, 5
  queries); `open=auto|manual` (default `auto`: it opens when its frame comes).
- `tuple`: `fields=` the labels, two or three - the first and the last a node, a middle one the
  edge's label (more would not show in the graph: the build refuses them); `suggest=` terms the
  fields offer; `min=` the students a triple needs for the projector (default 1); `review`
  (nothing shows on the projector before the lecturer lets it); `terms=exact|loose` (default
  exact: a term as written, as RDF compares IRIs; loose: case, accents and spacing do not count,
  for plain words - section 7.3).
- `code`: `engine=sparql`, `engine=sql` or `engine=turtle` (`texstage/engines.py`); `tokens=`
  the buttons above the phone's keyboard - the engine adds its punctuation (in the key,
  `\{ \} \# \%` stand for those characters and `\^` for `^`: TeX reads `^^x` as a character
  code); `seed=` a file beside the deck (Turtle for `sparql` and `turtle` - of a `turtle` seed
  only its `@base` and `@prefix` lines count, 8.9 -, SQL statements for `sql`: `.ttl`, `.sql`)
  or `\seed{...}`.
- `\prompt{...}` is typeset for the phones as a picture, as a quiz's question is (the core's
  `\texstage_asset`, CT section 4.3), so formulas and code look as on the slides; the handout shows
  it in the box.
- `\reference{...}` and `\seed{...}` are commands whose argument is read verbatim (xparse's `+v`,
  between braces that pair up, as a query's do): line breaks, `#`, `%` and `^^` stay as written,
  so the frame is `fragile`; `reference=FILE` and `seed=FILE` name files beside the deck instead.
  Several `\reference{...}` are allowed: equivalent queries - for `turtle`, spellings of one
  graph -, each of whose results counts as the reference's.

Modes, as the core gives them (CT section 4.3): the handout shows the box with the prompt and the
theme's placeholder ("live activity - join with the PIN"), the solutions add the reference,
the present compile records the box (`\texstage_box`) and writes a record line
`activity|id|input|engine|...|tex file|line` (hex-encoded where the quiz's are), the stage compile
the same without phone pages. One activity per frame, and none on a quiz's frame: the phones show
one thing at a time (section 10).

## 6. In the build: build/activity.py

A type module as `build/video.py`, in the registry `build/types.py:25`: `NAME = "activity"`,
`KINDS = {"activity"}`, `USES_ADDIN = False` (no add-in, no first slide; the live and the static
PPTX are the same for it); `box()` gives a slide's live box `{type: "activity", item, rects:
{box}}`; `entries()` gives

```json
"items": {"activity": {
  "lecture-graph": {"input": "tuple", "fields": ["Subject", "Predicate", "Object"],
                    "suggest": [":KG", ":teaches", ":attends", ":isAbout"], "limit": 10, "min": 1, "terms": "exact",
                    "prompt": "phone/2f1c09a4d5e6b7c8.png"},
  "prof-lectures": {"input": "code", "engine": "sparql", "seed": "data/9a3e5b7c1d2f4a6b.ttl",
                    "tokens": ["SELECT", "WHERE", "a", ":Professor"], "limit": 5,
                    "prompt": "phone/7b0d3c2e1f4a5b6c.png"}}}
```

and `keys.json` the private part, `{"activity": {"prof-lectures": {"reference": ["SELECT ?name
..."]}}}`, which the server keeps as it keeps a quiz's keys (`build/bundle.py:3-12`). The seed
goes into the bundle content-addressed, `data/<sha256[:16]>.ttl` - `.sql` for the SQL engine:
the file types of each engine, and the media types the server gives them, are in
`texstage/engines.py`, which the build and the server share (`build/bundle.py:37-38`); the
server's list of bundle files learns `data/` from the registry (CT section 5.2, item 6; today
`BUNDLE_ENTRY`, `server/app.py:139-140`). The build stops when a seed file is missing or not
the engine's, an engine is unknown or an id is taken. It runs no query in this milestone: a reference that does not parse
shows in the presenter window when the activity opens (section 8.5) - and in the dry run. Later
the build can run it with pyoxigraph, the same engine built for Python and released with it, and
the solutions PDF can show its result.

## 7. On the server: server/activity.py

### 7.1 State and tables

Small state in the session, under the type's name (CT section 6.2, item 2) - `stage["activity"]`:

```json
{"prof-lectures": {"phase": "open", "version": 41, "revealed": false, "shown": null},
 "lecture-graph": {"phase": "closed", "version": 230, "min": 2, "revealed": false,
                   "merges": [["node", "alice", "dr alice"]], "hidden": ["lol"], "approved": []}}
```

`phase` is `ready` (not opened yet), `open` or `closed`; `version` counts the changes of the
activity's **picture** - the graph or the clusters, as the windows draw them -, which the windows
fetch anew when it changes (7.4). Everything else is in tables of the type (CT section 6.2, item
3; the `TABLES` pattern, `server/store.py:24-40`):

- `contributions`: id, session, activity, player, created, input (JSON: the fields, or the
  text), state (`in`, `replaced`, `withdrawn`, `hidden`), key (crowd: the triple's normalised
  terms; clusters: the result's key, empty while it waits), status (`waiting`, `ok`, `syntax`,
  `error`, `timeout`, `refused`), error (the engine's message, at most 300 characters).
- `results`: session, activity, key, summary (JSON, at most 12 KiB: the columns, the first rows,
  the number of rows, the comparison with the reference), created - one row per distinct result,
  however many students got it.

### 7.2 Lifecycle

- An activity **opens** when its frame comes to the projector (`open=auto`) or when the lecturer
  opens it; the phones show it. At most one is open: opening one closes another.
- It **closes** when the projector leaves its frame - another frame, a whiteboard page, a poll -
  or when the lecturer closes it (*Close*): leaving a slide stops a video in the same way (the
  types' `slide` hook, `server/video.py:42-51`). The picture stays, and what waits for the
  evaluator is still evaluated. Back at the frame the picture is there again; it does not open by
  itself a second time - *Open* goes on with what is there.
- **Reveal** (clusters): the reference's clusters are marked in every window, and each phone
  learns whether its latest query gave the reference's result. The crowd graph has no key and no
  reveal.
- Everything is stored, so a restarted server goes on; a new game - the next lecture,
  `lecture.new`, a restart - starts every activity afresh (`game.py:272-288` carries the timer,
  Q&A and the whiteboard pages over, nothing else).

### 7.3 The reductions

**Crowd** (`tuple`). A term counts as written (`terms=exact`, the default since 2026-10-18): RDF
compares IRIs character by character, so `:kg` and `:KG` are two nodes, as they are two
resources - the device test showed the word cloud's grouping merging them silently, while the
frame says the graph cannot know two names are one. For plain words (`terms=loose`) a term is
normalised as the word cloud groups its answers - case, accents and spaces do not count
(`scoring.normalize_text`, `server/scoring.py:37-41`) - and shown in the spelling most students
used (`game.py:1180-1185`). The lecturer merges a term into another
(*Merge*: a union-find per role - nodes, the first and the last field; labels, the middle one): it
shows under the kept term's spelling, its edges move with it, *Unmerge* undoes it. A triple counts
the students who sent it (twice by one student: once), a node the students who used it. The
projector's picture: the triples with at least `min` students, without hidden terms (and with
`review` only approved ones), the 40 nodes with the most students, "and 23 more" for the rest
(more labels do not fit apart in a slide's box, L5).

**Clusters** (`code`). A contribution waits until the evaluator sends its key (section 8);
inputs with the same text (but for spaces at the ends of lines) are evaluated once, and a text
whose key is known gets it at once. A student's latest query counts - an earlier one is
`replaced` -, so the bars show where the class is now. A cluster is the students whose latest
query gave one key, with the summary of the result (stored once) and an example query - the text
most of them sent, else the first one. What is not a result is a cluster of its own: *syntax
error*, *error*, *timeout*, *refused*.

### 7.4 Views and messages

No view names anybody: the server keeps a contribution's player for the student's own list and
for blocking, as it does for the audience's questions (`server/qa.py:1-9`).

- **The host view** (pushed, `game.py:1229-1250`) carries per activity its state and counts -
  students, contributions, waiting -, never the reference before the reveal.
- **The picture** is fetched, not pushed - it is too large for every push to every window (CT
  section 6.2): `activity.view {activity}` when `version` changes, a read like `sketch.list`
  (`READS`, `server/app.py:125`). The projector gets the moderated picture; the presenter window
  also what is hidden, merged or waiting for review, and the reference's clusters before the
  reveal.
- **The player view** (pushed to the phone at once) carries the open activity - input, fields,
  suggestions, tokens, the prompt's picture - and the student's own contributions with their
  states.

The messages, in the type's namespace (CT section 6.2, item 1):

| from | message |
|---|---|
| phone | `activity.send {activity, fields \| text}` -> `{contribution}`; `activity.withdraw {activity, contribution}` |
| presenter window | `activity.open`, `activity.close`, `activity.reveal` `{activity}` |
| presenter window | crowd: `activity.merge {activity, role, term, into}`, `activity.unmerge {activity, role, term}`, `activity.approve {activity, term}`, `activity.min {activity, min}` |
| presenter window | `activity.hide {activity, term \| contribution, on}`, `activity.block {activity, contribution}` |
| presenter window | clusters: `activity.show {activity, cluster \| null}` - the projector shows it |
| presenter and projector windows | `activity.view {activity}` -> the picture |
| the presenter window with the lease (8.1) | `activity.work` -> `{lease, jobs: [{activity, input, text}], references: {activity: [texts]}, known: {activity: [keys]}, engines: {activity: {engine, seed}}}`; `activity.result {activity, input \| reference, status, key?, error?, summary?}`; crowd: `activity.layout {activity, at: {term: [x, y]}}` |

### 7.5 What the core gains

The video needed messages from the presenter window, state, slide changes and files
(`server/types.py:5-15`). An activity needs more; each becomes a hook of the registry, not a
special case in `app.py` and `game.py`:

1. **Messages from phones.** `_player` takes `answer` and `qa.*` only (`server/app.py:849-874`);
   a type names its phone messages, routed by prefix as the presenter's are (`app.py:808-809`).
2. **Its part of the player view** (`game.py:1314-1356`), as it has its part of the stage's
   (`game.py:860-869`).
3. **Reads**, answered anew rather than from the reply cache, and open to the projector window,
   which may send a fixed list today (`app.py:618-625`).
4. **Tables of its own**: the store takes a type's dataclasses and tables beside its own
   (`store.py:24-40`), and the engine loads them at start as it loads the questions
   (`game.py:190-196`).
5. **Its part of the archive** (`app.py:893-909`; the file names, `server/archive.py:36`).
6. **Bundle files** in folders of its own (`data/`), from the registry.
7. **A lease** for one presenter window (section 8.1).
8. **Blocking** becomes general: `players.muted` stops a player asking questions today
   (`game.py:1064-1079`); it stops their contributions too.
9. **Quiet messages** (L5): a type names those of its messages that come in bulk - the
   evaluator's results, one per query, and the layout, twice a second -; the hosts get the state
   they change with the next of the five pushes a second (`HOST_PUSH_S`, `app.py:123`), as with
   the phones' answers, not at once. Without it, 300 queries evaluated in a burst made 39 pushes a
   second to every host window. A phone a result concerns still gets its state at once.

The phone page gains a registry of renderers per type, as the stage has one (`showTypes`,
`web/shared/live.js:413-438`): a type's screen, mounted while its activity is open.

## 8. Evaluation in the presenter's browser

### 8.1 Which window

One presenter window evaluates at a time: the first that asks for work gets a lease from the
server, renewed with each request and passed on when that window goes (closed, or 15 s without a
request). The same window lays out the crowd graph (section 9). The projector window never
evaluates, the phones never do. Without a presenter window nothing is evaluated: contributions
wait, the phones say so, and the next presenter window takes them up. A paired iPad that is the
only presenter window evaluates - Oxigraph runs in Safari too.

### 8.2 The worker

The engine runs in a module worker (`web/stage/evaluator.js` and its worker), never on the
window's own thread: a slide change must take under 100 ms (texstage-requirements.md, section 4),
and a student's query may run long. Each query has a budget of 2 s - the trial's queries took
under 1 ms each (8.7): over it, the worker is terminated - status `timeout` - and a new one
starts from the compiled module, in 16 ms. The window fetches the
engine's WebAssembly file and the seed from the texstage server - offline as well - and hands them
to the worker, which is served with `Content-Security-Policy: connect-src 'none'`: a student's
query reaches no network, also not with `SERVICE`, which the engine refuses anyway. The server
serves `.wasm` as `application/wasm`, which Windows' registry may lack, as it lacked `.mjs`
(`app.py:152`).

### 8.3 The engine interface

Cut from the SPARQL engine and checked by the second, SQL (2026-10-18, CT principle 5), and by
the third, Turtle (2026-10-21, 8.9):

```js
// web/engines/sparql.js, sql.js, turtle.js - run in the worker (stage/evaluator-worker.js)
export const NAME = "sparql";
export async function start(wasm) { }          // the library, from the compiled WebAssembly module
export function load(lib, seed) { }            // the seed's text -> state
export function evaluate(state, text) { }      // -> {status, error?, canonical?, rows?, summary?}
```

The second engine moved what both need into the framework: `web/engines/common.js` hashes
`canonical` to the key, compares `rows` with the reference's and cuts a summary to the message's
size; `start` loads the engine's library itself, so the worker imports an engine by its name. An
engine has two entries in tables of its own, one per side: `web/engines/index.js` (the module
and its WebAssembly, for the windows) and `texstage/engines.py` (the seed's file types with their
media types, the tokens every bar offers, what a student's text is called in the server's
messages - for the build and the server); a test checks that they name the same engines. A third
engine is a module, a vendored library and these two lines - the Turtle engine (8.9) did without
the library: it parses with the SPARQL engine's Oxigraph, and a window compiles that WebAssembly
once for both (`stage/evaluator.js`).

- `status`: `ok`; `syntax`, with `error` - the message, its line and column in the student's text
  where the engine gives them (Oxigraph does, SQLite does not); `error` (it parses, but fails);
  `refused` (what the engine does not run: for SPARQL, `SERVICE` - an update is not a query and
  fails to parse as one -; for SQL, anything but one query, 8.8; Turtle refuses nothing).
- `canonical`: a text that is the same for the same result (8.4). The framework hashes it to the
  key: 64-bit FNV-1a, 16 hex digits - for a few hundred results a collision is out of reach, and it
  needs no secure context (Web Crypto's digest does, and a paired iPad may load texstage by
  `http://` over the room network).
- `summary`: what the windows show - the columns, the first 20 rows (values cut at 120
  characters) and the number of rows; for SPARQL also yes or no, or the triples. At most 12 KiB,
  so that `activity.result` fits into a message (16 KiB, `app.py:126`).
- `compare`: the worker compares each result's full rows (`rows`) with each reference's: "11
  rows - 7 of the reference's, 4 more" goes into the summary; the rows stay in the worker.

### 8.4 SPARQL: the same result, the same cluster

- A query gets the seed's `@base` and `@prefix` lines in front, as `BASE` and `PREFIX`, unless it
  declares them itself: nobody types prefixes on a phone, and the KG lecture's checker completes
  its listings the same way. Line numbers in errors are counted back to the student's text.
- SELECT: the rows are a bag - their order does not count, repeated rows do (a query without
  `DISTINCT` that repeats rows gives another answer; bag semantics is part of the KG lecture). The
  columns count in the order the query projects them, their names do not: `?n` and `?name` give
  the same table. A value is its term in N-Triples form - an IRI, a literal with its datatype or
  language -, an unbound one `-`; blank nodes are all alike (`_:`) in this milestone.
- ASK: yes or no. CONSTRUCT and DESCRIBE: the triples, sorted, blank nodes alike - the canonical
  form the Turtle engine gives a graph too, so that one graph has one key in both (8.9).
- Every key of an activity comes from one engine in one window, so the keys agree with each
  other. Whether Oxigraph's results agree with rdflib's - the engine of the notebooks and of the
  lecture's checks - the trial finds out (L0).

### 8.5 The reference

`keys.json` holds the reference queries; the server gives them only to the evaluating presenter
window, with its first work for the activity - the projector shows the class everything it gets,
so it gets no key before the reveal (the host view carries a quiz's keys only after its reveal
too, `game.py:24-26`). The window
evaluates them first; their keys mark the reference's clusters - in the presenter window at once,
everywhere after the reveal. A reference that does not parse or run says so in the panel ("the
reference does not parse: line 2, ...").

### 8.6 The SPARQL engine: Oxigraph

Oxigraph (Thomas Pellissier Tanon and contributors; Apache-2.0 or MIT) is a graph database in
Rust with SPARQL 1.1 and the RDF syntaxes; its npm package `oxigraph` is the WebAssembly build,
with an in-memory store. Proposed rather than rdflib in Pyodide, which CT section 8.3 had planned
for live cells (dropped, section 2):

- **Fast:** a class's hundreds of queries in seconds, so that the clusters grow while students
  type; rdflib's SPARQL is pure Python, and slower again in Pyodide. (The trial: 300 queries in
  0.08 s.)
- **Small:** one WebAssembly file of 4.0 MB against Pyodide's tens of megabytes and its memory -
  an iPad presents too.
- **Standard:** it implements SPARQL 1.1 as the W3C's test suites check it.
- CT's reason for rdflib - live results equal to the results the build prepared - does not apply:
  an activity has no prepared results.

Its cost: it is not the notebooks' engine; where the two differ on a student's query, the class
sees Oxigraph's answer - and they differ in one point of substance (8.7): Oxigraph stores a typed
literal of the XSD datatypes by its value, not as written. It is vendored as the other libraries
are (`web/vendor/README.md`: the files as published, from `npm pack` with the tarball's
integrity, with its licence files), and `NOTICE` lists it; the wheel grows by its WebAssembly
file.

### 8.7 The trial (L0, 2026-10-17)

Oxigraph 0.5.11 (npm, 2026-09-02; `MIT OR Apache-2.0`; tarball 2.9 MB, integrity
`sha512-zKdgmp1t...pLng==` as the registry lists it). The package holds a Node build and a browser
build (`web.js` 50 KB, `web_bg.wasm` 4.0 MB) and no licence files - those come from the
repository when it is vendored. Run in the app's Chromium and in Node 24:

- **In the browser:** the window compiles the WebAssembly once (28 ms from a local server) and
  sends the compiled module to a module worker; the worker starts from it in 1 ms, loads the KG
  lecture's chapter 5 graph (267 triples) in 15 ms - 47 ms from `new Worker` to ready - and uses
  1.7 MB of memory. Exercise 2 gives its 11 rows (the cross product without the join 84, the
  professors alone 7); 300 queries took 81 ms, 0.2 ms each (median; at most 0.8 ms). A runaway
  query (four patterns, all triples crossed) was stopped at its 2 s budget, and a new worker from
  the same module was ready 16 ms later. `SERVICE` is refused by the engine ("The service ... is
  not supported"). With `Content-Security-Policy: connect-src 'none'` on the worker's script, its
  `fetch`, `XMLHttpRequest` and `WebSocket` were all blocked - nothing reached the server.
- **Syntax errors** carry line and column ("error at 5:19: expected WHERE") - counted with the
  prologue, so the evaluator subtracts its lines (8.4).
- **Against rdflib 7.2.1:** the 76 SPARQL listings of the KG chapters 5 and 6 and of the
  exercises whose `% check:` runs them over a `data.ttl` (13 more need a closure, an update or
  an endpoint), completed as `check-listings.py` completes them: 71 give the same bag of rows,
  term by term. The five others: `AVG` with 18 decimal digits against Python's 28 (two
  listings); `SUM` over integers an `xsd:integer` - as SPARQL's numeric functions require - where
  rdflib gives an `xsd:decimal`; a query that uses `rdfs:` without declaring it - rdflib knows
  that prefix by itself, Oxigraph does not (and the KG checker's completion misses it after a
  `/`: `a/rdfs:subClassOf*`); and **06-SPARQL-Semantics/032**, the slide on term and value
  equality: `ASK { :Berlin :population "03500000"^^xs:integer }` is false by RDF's term
  equality - the data says `"3500000"` -, but true in Oxigraph. Oxigraph keeps typed literals of
  the XSD datatypes as values: `"03500000"^^xsd:integer` comes back as `"3500000"`, `"1.50"` as
  `"1.5"`, `"1"^^xsd:boolean` as `"true"`, and a pattern with one matches the other. Chapter 6's
  queries name their graph (`FROM :`), which Oxigraph - as the standard says - looks up in the
  store, while rdflib's graph ignores it: there the data was loaded under that name too.
- **What follows:** Oxigraph for the pilots - exercise 2 is a join, where both engines agree.
  Not with Oxigraph: an activity on lexical forms and term equality (chapter 6, frame 032); it
  would need an engine that keeps literals as written. The seed's prefixes go in front of every
  query (8.4), so an undeclared `rdfs:` works whenever the seed declares it. Not tried yet:
  Safari on the iPad (L4's test), Firefox.

### 8.8 The SQL engine: sql.js (2026-10-18)

sql.js (the sql.js authors; MIT) is SQLite compiled to WebAssembly; texstage vendors its browser
build, 1.14.2 - 45 KB of JavaScript and a 0.7 MB module (`web/vendor/README.md`; 1.15.0, four
days old, was passed over). The engine (`web/engines/sql.js`, 139 lines) runs the seed - a script
of `CREATE TABLE` and `INSERT` statements - into a database of its own and then sets it
read-only (`PRAGMA query_only`).

- **One query.** A student's text is one statement, `SELECT`, `VALUES` or `WITH ... SELECT`;
  more than one, or any other statement - `DELETE`, `DROP`, `PRAGMA`, `ATTACH`, `EXPLAIN` - is
  `refused`, and the read-only database refuses what slips through (`WITH ... DELETE`): no query
  changes what the next one sees.
- **The same result, the same cluster:** the rows as a bag, the columns in the order the query
  gives them, their names not - as for SPARQL (8.4). A number counts by its value: `7` and `7.0`
  alike, a fraction to 15 significant digits, so that `AVG(x)` and `SUM(x) / COUNT(*)` agree; a
  text as written, `NULL`, a blob by its bytes; `7` and `'7'` differ, as they do in SQL - and so
  do `1 / 2` (SQLite's integer division gives 0) and `1 / 2.0`.
- **What went wrong:** SQLite's message - `near "SELEC": syntax error` (`syntax`), `no such
  column: nme` (`error`) -, without a line and column, which sql.js does not give. A result of
  more than 100,000 rows is an `error`, not a result: a join condition forgotten on large tables
  - in the classroom's tables a cross product is a few hundred rows and a cluster of its own.
- **Loading it:** the browser build is a UMD script, not an ES module; the engine loads the file
  as published, with CommonJS's `module` in place while it starts (a browser imports the file as a
  module that exports nothing). The Node test loads it the same way, through a loader hook.
- **Checked** (2026-10-18): Node tests (keys, values, refusals, errors, summaries, the
  comparison); in the app's Chromium a scratch deck - the reference evaluated in the presenter's
  worker under its CSP, a query built on the phone with the token bar, 60 scripted phones in nine
  clusters (the reference's 11 rows in three spellings, a cross product, a LEFT JOIN, a count, a
  syntax error, an unknown column, a `DELETE`, two runaway queries stopped at 2 s), the reveal
  with the phone's verdict; the same key in Node and in Chromium. The 60 queries were all
  evaluated 0.57 s after the last was sent; of bursts within half a second, 200 queries were
  evaluated 0.57 s after the last, 300 queries 2.7 s after - and once 11.9 s, which was not
  repeated and is not explained (no timeouts, nothing in the server's log; section 15).

### 8.9 The Turtle engine (2026-10-21)

The user's request for the KG lecture's chapter 3, Serialization, whose thesis is *one graph,
many spellings*: the class writes one small graph in Turtle on the phones, and the box groups the
answers by the graph they denote, not by their text. Full triples, `;` and `,`, `3596999` or
`"3596999"^^xsd:integer`, prefixed names or the IRIs they stand for: one bar. The population in
quotes - a string, another literal - or a label without its language tag: another graph, another
bar. A comma where the semicolon belongs: a syntax error. The frame is
`03-Serialization/015.tex`, "Your Turn: Berlin in Turtle". The engine (`web/engines/turtle.js`,
129 lines) has no library of its own: it reads with Oxigraph's Turtle parser - the SPARQL
engine's library (8.6) - and takes the seed's prologue and a graph's terms from `sparql.js`.

- **What it parses.** Turtle only: Oxigraph 0.5.11's parser for `text/turtle`, which reads RDF
  1.2's Turtle (`PREFIX` and `BASE` besides `@prefix` and `@base`, `VERSION`, triple terms, a
  text's direction); TriG's graph blocks and JSON-LD are syntax errors. The seed is a Turtle file
  beside the deck (`seed=`, `.ttl`) or `\seed{...}`, parsed when the activity opens - a seed that
  does not parse says so in the panel. Its `@base` and `@prefix` lines go in front of every text
  that does not declare them itself, in Turtle's form, as the SPARQL engine completes a query
  (8.4); its triples are no part of anybody's graph. A phone keyboard's typographic quotes (iOS:
  `“Berlin”`, German `„Berlin“`) count as Turtle's, as the crowd graph takes them (section 9) -
  else every iPhone's string would be a syntax error.
- **The canonical form** is the SPARQL engine's for a CONSTRUCT's graph (8.4), the same function
  (`rdfjsTerm`): `graph` and the triples, sorted, each term as N-Triples writes it - an IRI, a
  literal with its datatype or its language in lower case -, blank nodes all alike (`_:`). A
  graph is a set: a triple written twice is one (the triples are told apart by their terms, blank
  nodes by their own labels, before the labels go), and Oxigraph's CONSTRUCT gives a set too, so a
  Turtle text and a CONSTRUCT that give one graph have one key - a test checks three graphs, one
  with a collection. A literal counts as written, as RDF compares terms: `"3596999"` (a string) is
  not `3596999` (an `xsd:integer`), nor are `"3596999"^^xsd:int` and `03596999`; `"Berlin"@DE` is
  `"Berlin"@de`. A CONSTRUCT's literals that come from Oxigraph's store are values (8.7:
  `"03"^^xsd:integer` comes back as `"3"`), so the two keys agree for literals in their canonical
  lexical form, as the slides write them.
- **A limit shared with the SPARQL engine: blank nodes all alike**, as in its SELECT rows and its
  CONSTRUCT and DESCRIBE graphs (8.4). Two graphs that differ only in which blank node is which
  get one key: the order of a collection's members does not count -
  `( dbr:Potsdam dbr:Teltow dbr:Falkensee )` and `( dbr:Teltow dbr:Potsdam dbr:Falkensee )` are
  one cluster, the same seven triples once their blank nodes are `_:` -, nor which of two nested
  blank nodes carries which triples. A collection with another member or of another length, and
  every triple without a blank node, still count. A stronger canonical form gives each blank node
  a canonical label instead of one for all: RDF Dataset Canonicalization (RDFC-1.0, a W3C
  Recommendation since 2024), or a colour refinement as graph-isomorphism tests use - a blank
  node's label the hash of its triples and its neighbours' labels, refined until nothing changes;
  enough for collections and nested blank nodes, only highly symmetric blank-node structures need
  RDFC-1.0's exhaustive branching. It would have to go into both engines at once - `rdfjsTerm`
  and the SELECT rows -, or a Turtle text's key and a CONSTRUCT's would part; it changes the
  SPARQL engine's keys and costs a pass per result. It waits for an activity that needs it: a
  collection whose order is the point.
- **What went wrong:** `syntax`, with Oxigraph's message at the student's line and column (the
  lines in front subtracted; columns as Oxigraph counts them, from 1):
  `line 2, column 1: A dot is expected at the end of statements` (a period missing - found where
  the next statement begins), `line 1, column 6: Berlin is not a valid predicate`
  (`dbr: Berlin`, a space after the colon),
  `line 1, column 1: The prefix dbp: has not been declared`,
  `line 1, column 32: , is not a valid RDF object`. A text without a triple - comments or
  prefixes only - is `syntax`, "no triples", as SQL's "no statement" (8.8). Nothing is
  `refused`.
- **Limits:** a graph of more than 10,000 triples is an `error`, not a result - a phone's 2,000
  characters make about 2,000 at most (a collection of digits); the worker's budget of 2 s (8.2)
  as for a query. In Node a text took at most 0.3 ms.
- **The summary** is a graph's, as a CONSTRUCT's: the number of triples and the first 20 - here
  in the order written and in Turtle's form, so that the windows show what differs: IRIs short
  with the seed's prefixes (`rdf:type` as `a`), `3596999` bare and `"3596999"` in quotes,
  `"1237-10-28"^^xsd:date`, blank nodes numbered as they come (`_:b1`); values cut at 120
  characters, at most 12 KiB.
- **The windows:** the bars say "3 triples"; the box waits "for the first graphs", a shown
  cluster is "the reference's graph", the panel speaks of texts, not queries (`codeWords`). The
  phone learns the engine from its view and says "Valid Turtle ✓", "Syntax error: line 2, column
  1: …" and, after the reveal, "The same graph as the reference ✓" or "A different graph than the
  reference" (in German too); a query's words are as they were. The server refuses an empty text
  as "a Turtle text" (`engines.py`, `text`). The token bar adds `: . ; , " @ ^^ < > _: [ ] ( )` to
  the deck's tokens; a sign goes in as it is - since this step no space after `:`, `?` and `_:`,
  which had made the SPARQL engine's `?` and `:` buttons write `? name` and `: Professor`.
- **The reference** is Turtle in `\reference{...}`, read verbatim with its `#`, `%` and `^^`
  (section 5); several are allowed - spellings of one graph share a key -, and the build, the
  presenter window and the reveal treat them as a query's (8.5).
- **Simulated phones** (`tools/simulate.py`) send Turtle to a turtle activity: a built-in pool -
  the three triples of `015.tex`'s reference (Berlin's two labels and its population) in eight
  spellings, each of which hits the reference's key over the frame's seed, four wrong graphs and
  four syntax errors - and, given the bundle folder (also with `--pin`), the deck's reference
  with variants of it: as written and with its first number's datatype written out (the
  reference's graph), that number in quotes or a language tag left out (wrong graphs), a space
  after a colon or the last period left out (syntax errors).
- **Checked** (2026-10-21): Node tests - `tests/web-activity-turtle.test.mjs` (four spellings,
  the number as a string, a missing tag, duplicates, blank nodes and a collection, the key against
  a CONSTRUCT's, the errors at the student's lines, the limits, the seed, the summary, the
  comparison) and `tests/web-activity-phone.test.mjs` (the phone's words, its screen on a DOM
  double, the token bar) -, a build test (a turtle activity: the seed, the tokens, two references
  verbatim) and a server test (the engine in the phone's view, the refusal's words, the work, the
  reveal). The browser and real phones: the live test with chapter 3's deck.

## 9. The windows

- **The box** (`web/stage/activity.js`, `ActivityBox`, a renderer as `VideoBox` is - registered
  in `web/stage/presenter.js:640` and `web/stage/projector.js:82`) draws the picture in the
  activity's box, in both windows the same: what the class sees. It lies under the ink
  (`.tq-types`), so the lecturer writes on it; it has no buttons on the slide. It fetches the
  picture when `version` changes, at most twice a second.
- **The graph:** nodes as labels, edges as arrows with theirs, thicker with more students; new
  ones fade in. **A literal is a box** as the slides draw one (`rdf-literal`: light yellow, a
  dark rim; since 2026-10-19, the user's wish), a resource stays rounded: the server marks a
  node whose term is written as Turtle writes a literal - a quoted string with its language or
  datatype, a number, `true`, `false` (`is_literal`) -, and the archive's SVG draws it as a
  square. A phone's typographic quotes (iOS: `“Kant”`, German `„Kant“`) become Turtle's when
  the term comes in (`clean_term`), so the literal is one node whichever keyboard typed it.
  Edges between the same two nodes, either way round, curve apart, their labels
  apart; a triple whose subject is its object is a loop above its node, and the layout keeps
  room for it (`edgeShapes`, `edgePath`; until the device test of 2026-10-18 such an edge was a
  line of no length, and `:test :test :test` showed as a node alone). A label that many edges
  at one node carry - thirty students who `:attends :KG` - shows on the three edges most
  students named (`repeatedLabels`). **The layout runs** (`ForceLayout`, since 2026-10-18; the
  user's wish: a display that lives): a force simulation as d3-force's - labels repel each
  other, edges pull like springs, a pull towards the middle keeps parts off the rim, labels that
  overlap are pushed apart -, whose heat cools until the graph rests, from cold in five seconds.
  A new label heats it, a new edge less; a count alone does not (grown labels are only pushed
  apart). So the graph moves while triples come and settles after the last. **The positions
  are shared:** the presenter window with the lease (8.1) steps the simulation once a frame,
  draws it, and sends the positions as fractions of the slide (`activity.layout`, at most twice
  a second); the projector and the iPad glide their labels there, slowly enough to fill the half
  second until the next ones come. A presenter window that gets no frames - minimised, or a tab
  in the background - runs the simulation to rest at once with every change, or new labels
  would stay on their neighbours, and any window without frames draws the nodes and their
  labels at their places at once (until 2026-10-19 the nodes that were there waited for a
  frame to glide, and lay on one another meanwhile); one that gets the lease starts from the
  places sent, and heats only if labels lie on one another. Ink and the pointer are fractions of
  the slide too (texstage-design.md, sections 6.2 and 17): once the graph rests - seconds after
  the last triple - a circle drawn around a node on the iPad lies around it on the projector;
  while it moves, the projector is half a second behind. Without a presenter window the
  projector lays out by itself, at rest at once. Positions are not stored: after a restart they
  are laid out anew. (Before: the presenter window laid the graph out at once at every change,
  and the windows glided to the result.)
- **The edges' labels apart** (`placeLabels`, since 2026-10-19; the user's wish after the device
  test, where labels lay on one another in the dense core): a label tries twelve spots along
  its edge - the middle above the line and below it, then a little to either side, beside it,
  further along - and takes the first inside the box, on no node and on no label placed
  before; the labels of the edges most students sent are placed first. A label with no free
  spot fades out rather than lie on another (`.tq-off`), and comes back when there is room; one
  whose spot changes glides there along its edge. The spots follow from the positions alone,
  not from where the labels were, so every window puts a label where the others do - ink on
  one lies on it on the projector. The labels lie over every edge (`.tq-elabels`, between the
  edges and the nodes; before, a later edge's line crossed an earlier edge's label). **The
  layout makes room for them:** for the labels shown, `ForceLayout` keeps the other nodes off
  the edge's way (15 % to 85 % of it, a label's height on either side) and the edge long
  enough to hold its label between its ends; labels apart come first - the last pass at rest
  is without the room. Measured on twelve class-like graphs (40 nodes, a hub of students who
  `:attends :KG` and a core the many sent; 225 labels): left out 119 without the room, 34 with
  it - of the labels more than three students sent, 52 and 11 (none to three per graph); no
  label on another, no node on another; one more node against the rim per graph; moving while
  the graph grows hardly more (median 0.016 -> 0.018 of the box per triple). In a crowded hub
  not every label fits: the minimum (from 2 students) thins it. The archive's SVG places its
  labels the same way (`place_labels`, server/activity.py).
- **The clusters:** a bar per cluster, the largest first - "11 rows · 14 students", "77 rows ·
  9", "syntax error · 5" -, at most eight and "others"; after the reveal the reference's carry a
  tick. A shown cluster (`activity.show`) puts its example query and its result as a card over
  the box.
- **The box's words** follow the deck's language (deck.json's `language`, since 2026-10-24;
  `WORDS` in activity.js, which `Stage` passes it): a German deck's box says "11 Zeilen",
  "5 Personen · 2 warten", "Warten auf die ersten Anfragen …", "Keine Tripel."; an English
  deck's, and one built before, as above. The phones keep their own language, the panel its
  English.
- **The panel** in the presenter window, a drawer as the Q&A panel: *Open*, *Close*, *Reveal*;
  the counts; the evaluator ("Oxigraph ready - 3 waiting"). Crowd: the terms by students - pick
  two and *Merge*, *Unmerge*, *Hide*, *Approve* (with `review`), the minimum. Clusters: the
  clusters with their example queries (anonymous), *Show on the projector*, *Hide*, *Block*.
- Freeze, zoom, the black screen, whiteboard pages and the recording work as on every slide. The
  host console and PowerPoint's add-in show nothing of activities.

## 10. The phones

- **One thing at a time:** a phone shows the quiz's round while one is open, else the open
  activity. (An activity closes when its frame goes, and a quiz's question has a frame of its own,
  so the two meet only when the lecturer opens an activity by hand.)
- **`tuple`:** the prompt (its picture), the fields with their labels - each offers the deck's
  suggestions and the terms the projector shows, so that the class converges on one name for one
  thing -, *Add*; below, my triples, each with × to withdraw it. At most `limit`, one every 2 s, a
  term at most 60 characters.
- **`code`:** the prompt, a text field in a monospaced font without autocorrection, capitals and
  spell checking (`autocapitalize="off"`, `autocorrect="off"`, `spellcheck="false"` - a phone's
  keyboard otherwise "corrects" `SELECT` and `?name`), the token bar above the keyboard (a tap
  inserts at the cursor), *Send*. Below, the state of my latest query: waiting, runs, syntax error
  with the engine's message - so that a typo can be fixed -, timeout. At most `limit`, one every
  5 s, at most 2,000 characters. The words follow the engine (the view's `engine`): a Turtle text
  is "Valid Turtle ✓" or a syntax error, its graph the reference's or not (8.9).
- **Before the reveal** a phone learns whether its query runs - never its result, nor whether it
  is right (as with quizzes, `game.py:24-26`); after it, whether its result is the reference's.
- Of the others' contributions a phone sees only the suggested terms. Everything a student typed
  is shown as text, never as HTML, in every window: a "term" can be `<img onerror=...>` (CT
  section 6.4).

## 11. The archive

Per activity, in the game's folder of the lecture archive: `activity-<id>.csv`, a row per
contribution - time, input, state, terms or key, status -, without names, as `questions.csv`;
`activity-<id>.json`, the final picture - the graph with its counts, merges and positions, or the
clusters with their summaries and the reference's keys; and for a graph `activity-<id>.svg`,
written by the server from that picture as the sketches are (`server/archive.py:62`). Not in this
milestone: the picture in the annotated PDF - the frame's page shows the static form there;
later drawn into it as vector paths, as the ink is (`web/stage/export.js`).

## 12. Limits and load

| | limit |
|---|---|
| students | 1,000 per game (`game.py:82`) |
| triples | `limit=` per student and activity (default 10), one every 2 s, a term at most 60 characters |
| queries | `limit=` per student and activity (default 5), one every 5 s, at most 2,000 characters |
| contributions | 5,000 per activity |
| distinct results | 500 per activity; beyond, the panel says so and the rest wait |
| a query's result | SQL: at most 100,000 rows - more is an error (8.8); Turtle: at most 10,000 triples (8.9); each query at most 2 s in the worker (8.2) |
| the picture | 40 nodes; eight clusters and "others"; a result's summary at most 12 KiB |
| pushes | the hosts as today (at most five a second), the picture fetched at most twice a second per window, a phone at once with its own changes |

300 phones sending a triple each within a minute make five contributions a second: an insert, a
push to that phone, the hosts within 200 ms (`app.py:123`) - well within what quizzes do. The
evaluator's load is hundreds of distinct queries; Oxigraph's time per query on the KG lecture's
university graph (chapter 5, `data.ttl`) is the trial's measurement.

L5 measured it (2026-10-18; server, presenter and projector window on the laptop, 300 simulated
phones over WebSockets on the same machine, the KG lecture's two activities): 300 triples within
10 s, each acknowledged in 5 ms (median; 13 ms for the 95th percentile); 300 different queries
within 10 s, 2 ms (7 ms), the last evaluated 0.57 s after it was sent; all 300 within half a
second, 6 ms (20 ms) and 1.09 s. The host windows got at most five pushes a second throughout -
39 before the evaluator's results became quiet messages (7.5, item 9).

## 13. Later

| | what it is | what it needs |
|---|---|---|
| `visual-target` | tap nodes, edges or regions of a picture | the phone shows the box as a phone picture; taps as fractions; counts or a heat map per target |
| `state-walker` | every phone walks a graph: PageRank by hand | the graph as data in the deck; the server moves each phone along its choices (data, no code); visits per state |
| `parametric-point` | sliders or a 2D pad | points; a scatter view |
| rule matrix | each contribution against named rules | an engine that runs rules; the key: the vector of outcomes |
| further engines | entailment (EYE-JS), SHACL (shacl-engine), larger SQL (DuckDB-WASM), graphs (Graphology), SAT (MiniSat), Python (Pyodide), models (ONNX Runtime Web) | each vendored with its licence checked, as KaTeX was, and named in the two tables (8.3); a large one (Pyodide, DuckDB) also a longer budget and the iPad's memory checked - the worker's restart after a timeout is quick only for small engines |
| inputs, reductions, views apart | a tuple judged by an engine (k-anonymity, functional dependencies), taps counted by target | `input=` split into input, reduction and view - each a table of its own, today's two pairs the defaults |
| merging by pen | drag a node onto another, a lasso | a mode of the box in which the pen does not write |
| highlights | the seed's triples behind a cluster's rows | the engine's highlights; a view of the seed graph |
| the annotated PDF | the final picture on the frame's page | `export.js` draws it |
| a time limit | `time=` closes the activity by itself | the engine's deadlines (`game.py`, `next_deadline`) |
| the reference at build time | the solutions PDF shows its result | pyoxigraph in the build |
| canonical blank nodes | a graph's key that counts which blank node is which - a collection's order (8.9) | canonical labels (RDFC-1.0, or a colour refinement) in both RDF engines' canonical forms at once; the SPARQL engine's keys change |

## 14. Plan

The semester runs: the work stays on the branch, and the lectures on `main` until a dry run has
passed. Each step has its test of done.

**L0 is done** (2026-10-17, section 8.7) but for Safari on the iPad, which L4 tests: Oxigraph
0.5.11 in a module worker of Chromium and in Node; 71 of 76 KG listings as rdflib gives them, the
five differences explained; 300 queries in 0.08 s; the budget stops a runaway query, a new worker
takes 16 ms; the worker's CSP blocks every request.

**L1 to L4, so far** (2026-10-17, on the branch, committed 2026-10-18): the core's hooks
(`server/types.py`: `Call`, `Refused`, phone messages, reads, a type's Book and tables, its
archive and bundle files; `game.py`: the types' calls and the phones they concern, `take_due`;
`play.js`: a screen per type) - all tests passing unchanged but for the stage view's new key;
`texactivity.sty` (and the core's `\texstage_asset:nnnn`), `build/activity.py`;
`server/activity.py` (both reductions, moderation, the lease, the archive); the windows'
`stage/activity.js` (the box, the agent, the layout), the panel in `presenter.js`, the phone's
`play/activity.js`; the evaluator (`stage/evaluator.js`, its worker, `engines/sparql.js`) with
Oxigraph vendored (`web/vendor/oxigraph`, with its licence files from the repository). Tests: LaTeX (the
package's modes and refusals), build (items, keys, seed; refusals), server
(`tests/test_activity.py`: both pilots through the engine, a restart, the archive, the whole over
WebSockets), Node (the
engine on the vendored Oxigraph: keys, prefixes, errors, summaries, comparisons). Checked in the
app's Chromium with a scratch deck: presenter, projector and phones (one in a mobile context,
scripted ones): the crowd graph - triples, minimum, review, the same positions in both windows
(the presenter lays out, once per change of the graph) -; the queries - the references run in the
presenter's worker, a query built on the phone with the token bar, a syntax error, a cross product,
clusters on the projector, a cluster shown, the reveal with the phone's verdict, a runaway query
stopped at 2 s and the next one evaluated in the new worker. Not yet: Safari on the iPad, the
merge by hand in the browser (the server's tests cover it), ink over the graph.

**L5, so far** (2026-10-18, the KG lecture's worktree; committed there and here the same day):
`dbis-slides.sty` loads
`texactivity` beside the quiz theme; `02-RDF/029.tex` "Your Turn: Our Lecture as a Graph" is new
(frames 029-040 became 030-041), and `05-SPARQL/014.tex` has exercise 2 as an activity, with
frame 015's query as the reference (11 rows); both decks and their texstage builds pass. The load
of section 12 passed after two fixes: the evaluator's results and the layout became quiet
messages (7.5, item 9), and the layout was made for a crowded graph - with 60 nodes, 54 labels
had ended on the box's rim; now 40 are shown, smaller, pushed apart where they overlap, and a
node keeps its place (section 9; `tests/web-activity-layout.test.mjs`). In the app's Chromium the
projector drew the load's 40 nodes inside the box without an overlap; 60 more phones then moved
a label by 10 px (the median; the box 481 px high) while three nodes came and went. Left for the
lecturer: real phones on the lecture hall's network, and the iPad (Safari) as the presenter
window that evaluates.

**After L5** (2026-10-18): a review of the design for the range of activities it covers found
the activity type to be the two pilots wired through every layer (`input=` chooses the phone's
screen, the reduction, the view and the panel together) and one defect: the build took tuples of
up to six fields, but the box drew only the first and the last - two or three now (section 5).
The engine interface got its second engine, SQL (8.3, 8.8), on the user's request: the
interface held, the parts both engines need moved into `web/engines/common.js`, and an engine is
now named in two tables instead of five places.

**With the lecturer's devices** (2026-10-18): the KG worktree's server through the lecture's
Cloudflare tunnel, the iPad paired as the presenter window, a phone, and 30 simulated phones per
deck (`tools/simulate.py`, which now takes part in activities too). The phone's triples arrived;
a triple whose subject is its object did not show - fixed (section 9), together with edges
between the same nodes, which lay on one another, and arrowheads that grew with the line. The
simulated phones lost their connections through the tunnel within minutes - 29 answered the
first quiz, 3 sent triples ten minutes later - and, unlike a phone's browser, did not take them
up again; now they do, with their tokens, and say so (section 15).

**The edges' labels apart** (2026-10-19, the user's wish after the device test; section 9): in
Edge on that test's game (91 phones, 40 nodes shown), after six more phones had sent triples,
the graph at rest showed 19 of its 22 labels, none on another or on a node; the presenter
window and the projector placed the same 19 at the same spots (within 0.3 of 1000 - the
projector's glide stops that close to the places sent) and left out the same three.

**The Turtle engine** (2026-10-21, the user's request for the KG lecture's chapter 3; branch
`texstage-turtle-engine`, not committed yet; section 8.9): a third engine, `engine=turtle` -
`web/engines/turtle.js` around the SPARQL engine's Oxigraph, which shares its prologue and its
terms (`sparql.js` exports them; its behaviour is unchanged but for RDF 1.2's triple terms and
text direction, which its canonical form now writes out - before, a triple term was `?Quad` and
a direction was dropped); a row in each engine table (`engines.py` gained a `text` column: what
the server's messages call a student's text); the phone's words engine by engine, and the token
bar's signs without a space after them; the box's and the panel's words (`codeWords`); the
evaluator compiles a WebAssembly module once for the engines that share it; `tools/simulate.py`
sends Turtle. The engine interface held unchanged. Tests: 307 passed before, 312 after (pytest,
which runs the Node files too) - the Turtle engine's Node tests, the phone's, a build test, a
server test, a build refusal -, and the 65 Node tests of the ten files all pass. Left: the live
test with chapter 3's deck (`03-Serialization/015.tex`), simulated phones and a real one.

| step | what | done when |
|---|---|---|
| **L0** | the trial, a day at most: Oxigraph in a worker of the presenter window | its size; load time and memory in Edge on the laptop and in Safari on the iPad, from the texstage server; the KG lecture's `05-SPARQL` listings over its `data.ttl` give the rows `check-listings.py` (rdflib) gets, the differences listed; time per query; a runaway query stopped within its budget, and what a new worker costs; the worker's CSP blocks requests in both browsers |
| **L1** | the core's hooks (section 7.5) and the phones' registry; no change in behaviour | all tests pass; a deck without activities builds to the same bundle ID and plays as before |
| **L2** | `texactivity.sty`, `build/activity.py` | a deck with both activities: handout, solutions, the present and stage compiles, `deck.json` and `keys.json`, the seed in the bundle; a LaTeX test and a build test |
| **L3** | the crowd graph: server, phones, box, panel, layout, archive | engine and server tests; in Edge with presenter, projector and three phones (mobile contexts): triples, merge and unmerge, hide, minimum, review, block, a reload of every window, a server restart; ink on the graph where it was drawn, in both windows; the archive's three files |
| **L4** | SPARQL clusters: the evaluator, the clusters, the reference, the reveal | Node tests of the canonical form and the key; engine and server tests with a scripted evaluator; in Edge as in L3, with queries: a syntax error fixed on the phone, a timeout, the reveal; the iPad as the only presenter window, evaluating |
| **L5** | dry run in the KG lecture | in its worktree (branch `kg-worktree`): a new frame in `02-RDF` (the crowd graph) and exercise 2 of `05-SPARQL/014.tex` (professors and their lectures, 11 rows) as an activity; real phones; 300 simulated phones (a script over WebSockets): pushes as in section 12, and the evaluator through 300 different queries within 10 s (the engine alone: 0.08 s, 8.7) |
| **T** | the Turtle engine (8.9) | Node tests: one key for the spellings of a graph and the key of a CONSTRUCT that gives it, another for a string in place of a number and for a missing tag, a set's duplicates, blank nodes and a collection, the errors at the student's lines, the limits, the summary; the phone's words; build and server tests; then chapter 3's frame live, with simulated phones: the reference's bar holding several spellings, the wrong graphs and the syntax errors apart, the reveal on the phones |

The tests follow texstage-design.md, section 13: pytest for the engine and the server
(`tests/fake_bundle.py`), Node for the windows' code, LaTeX tests for the package, the browser
with two windows and mobile contexts; SPDX headers on every new file.

## 15. Open questions

The review's four (2026-10-17) are answered in section 2: the names, the phones' feedback before
the reveal, no live notebook cells, the pilot frames. The trial (8.7) leaves one: Oxigraph keeps
typed literals as values, not as written - fine for the pilots, wrong for an activity on term
equality (chapter 6, frame 032). Such an activity would need a second SPARQL engine; none is
planned until a deck wants one.

The SQL engine's check (8.8) leaves one: a burst of 300 queries within half a second was once
evaluated 11.9 s after the last was sent - over L5's 10 s -, against 2.7 s and 0.57 s in the
other runs; there were no timeouts and nothing in the server's log. The presenter window sends
its results one at a time, each waiting for the server's answer, and asks for the next twenty
only then; a log of those messages, kept until the slow case comes again, would show where the
time goes.

The device test leaves another: why did the simulated phones' connections through the tunnel
break - within three minutes, without a close frame, as when the server stops, though it did
not and cloudflared's log shows its connections to Cloudflare unbroken? Phones take a lost connection up
again by themselves, but a class whose connections break every few minutes would see it. The
next test through the tunnel, with the simulator saying when it loses a connection, tells how
often it happens.
