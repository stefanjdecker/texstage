# texquiz — design

Status: v1, 2026-10-01; M1a (LaTeX package), M1b (builder), M2 (server) and M3 (views) built, see §11. Supersedes the
browser-first prototype in `research/latexpresenter`, which stays untouched for reference.

**Since 2026-10-10 the whole system is called texstage, and texquiz is its quiz**
([content-types-design.md](content-types-design.md), sections 2 and 10, N1): the Python package
is `texstage`, the commands are `texstage ...` (`texquiz ...` still works), the data folder
`~/.texstage` (or `~/.texquiz`, where only that one exists). Where this document says texquiz
for the whole, read texstage; `texquiz.sty` and the quiz keep their names.

## 1. Goal

A Kahoot-style classroom game whose **content is authored in LaTeX/Beamer** next to the ordinary
slides and whose **presentation surface is PowerPoint**. One command turns a deck into

1. a PowerPoint file — slide images and speaker notes as today, plus pre-configured live add-in
   objects on every quiz slide (no manual insertion),
2. a quiz bundle for the server — questions, answer keys, slide images, phone images.

Students play on their phones (PIN/QR, nickname). The lecturer only uses the clicker: showing a
quiz slide starts the question, the next slide reveals the answer, the next one the leaderboard.

Decisions taken with the user (2026-10-01):

| Topic | Decision |
|---|---|
| Live content in PowerPoint | Office **web add-in** (content add-in), inserted by the generator |
| Server hosting | Both: lecturer laptop and hosted server with HTTPS |
| Game mechanics | Kahoot-like and configurable: nicknames, speed points, streaks, leaderboard, podium; per quiz switchable to correctness-only or unscored |
| Phone view | Kahoot shape buttons **plus LaTeX-rendered images** of prompt and answers |
| Server language | Python (Starlette/uvicorn, WebSockets, SQLite); browser parts plain JS modules, no bundler. Reconfirmed after weighing TypeScript: the build needs a PDF renderer (pypdfium2 since texstage M7; PyMuPDF before) and python-pptx anyway, so one runtime and one install command (`uv tool install` / `pip install`) is simpler than two; the hosted server ships as a Docker image |
| Question types | v1: single, multiple, true/false, poll. Then numeric/slider, short text, open text/word cloud, ordering; texstage M6: sketch (the phones draw) |
| Project location | New subfolder `texquiz/`; since 2026-10-02 part of the shared `lecture-tools` repository (git submodule `tools/` of every DBIS lecture) |

Non-goals for now: accounts/SSO, LMS integration, teams, multi-node deployment, copying Kahoot's
branding or assets.

## 2. Overview

```
 lecture.tex ──(pdflatex + texquiz.sty, present mode)──► lecture.pdf  + lecture.tqz (metadata)
                                                            │  slides | notes  (2nd screen)
                                                            │  + trailing phone-asset pages
                                       texstage build ◄──────┘
                                      ┌──────┴──────────────────────────┐
                                      ▼                                 ▼
                    lecture.pptx  (pictures, notes,          bundle/  (deck.json, keys,
                    web-add-in objects on live slides)         slide PNGs, phone PNGs)
                                      │                                 │ upload / local dir
                                      ▼                                 ▼
                  PowerPoint slideshow ── add-in views ──WS──►  texstage server  ◄──WS── phones
                  (lobby, question, reveal, leaderboard,       (sessions, players,
                   podium)                                      rounds, scoring, SQLite)
```

Three cleanly separated layers:

- **Authoring/build** (LaTeX package + Python builder): produces immutable, content-hashed bundles.
- **Game server**: owns all state; sessions are pinned to a bundle version.
- **Views** (HTML/JS served by the server): add-in views inside PowerPoint, phone app, host
  console. The add-in views are ordinary web pages, so a browser "slide host" can run the whole
  game without PowerPoint — useful for testing and as a fallback.

## 3. Authoring in LaTeX

`texquiz.sty` works in any Beamer deck, including the DBIS course (one frame per `NNN.tex`;
the package would be loaded from `dbis-style.sty` or the deck preamble). A normal compile
produces the **student handout** (no answers, see §3.2); only `texstage build` produces the live
presentation.

### 3.1 Syntax

```latex
\usepackage{texquiz}
\quizsetup{time=20, points=standard, leaderboard=true, join-badge=true}

\quizjoinframe[title={Join the quiz}, note={Phones out!}]   % lobby: QR, PIN, nicknames appear live;
                                                           % note = its speaker note (it has no body)

\begin{quiz}[id=rdf-triple, time=20]{Which components form an RDF triple?}
  \choice{Entity, attribute, table}
  \choice*{Subject, predicate, object}         % * marks a correct choice
  \choice{Class, method, argument}
  \choice{Document, link, keyword}
  \explain{A triple consists of a subject, a predicate, and an object.}
  \note{Ask for an example after the reveal.}
\end{quiz}

\quizpodiumframe                               % final standings
```

Question types (`type=` is inferred where unambiguous):

| Type | Authoring | Scoring |
|---|---|---|
| `single` | 2–4 `\choice`, exactly one `\choice*` | speed points if correct |
| `multiple` | ≥1 `\choice*` (or `type=multiple`) | exact set required (option `partial=true`) |
| `truefalse` | `type=truefalse, answer=true` | speed points if correct |
| `poll` | `type=poll`, `\choice` only, `select=multiple` optional | none |
| `numeric` | `type=numeric, answer=42, tolerance=2, min=0, max=100, step=1, unit={ms}` | within tolerance; slider if `min`/`max` given |
| `text` | `type=text`, `\accept{RDF}`, `\accept{Resource Description Framework}` | normalised match (case, whitespace, optional accents) |
| `open` | `type=open, display=wordcloud\|list, max-chars=80` | none |
| `order` | `type=order`, `\step{…}` in correct order | exact order (option `partial=true`) |

Common keys: `id` (required, unique per deck; `[a-z0-9-]`), `time` (5–240 s), `points=standard|double|none`,
`leaderboard=true|false` (overrides `\quizsetup`), `title` (frame title, default from setup).
Choices take optional `id=` (default: A, B, C, D by position).

Choice content is arbitrary LaTeX (math, `\texttt`, small graphics) — it is never converted to
HTML; projector and phones both show what TeX typeset. Verbatim (`lstlisting`) inside a quiz is
not supported in v1 (use `\texttt` or an image).

### 3.2 Output modes — what a `quiz` produces

Authoring details are in `docs/authoring.md`. Two forms (revised 2026-10-01 after surveying the
Knowledge Graphs lecture, whose 67 predict-then-see question frames all carry material —
tables, graphs, listings — and are answered on a following "Answer:" frame):

- `\begin{quiz}...\end{quiz}` between frames makes its own frame (built-in layout);
- inside a frame with the option `quiz` (`\begin{frame}[t,fragile,quiz]`) it typesets question
  and answers in place, below the author's material; fragile frames work. Its `\explain` goes
  below the answers on the reveal and solutions pages - unless `reveal=none`, where the
  course's answer frame explains. (Before 2026-10-03 a quiz inside a frame never showed its
  `\explain`.)

Frames that give an answer away get the option `answer` (`answer=<quiz id>` also links them to
the quiz for the live deck). The mode decides what is emitted:

| Mode | How selected | Quiz | Answer frame | Purpose |
|---|---|---|---|---|
| `handout` | **default** — any normal compile, incl. the course's `build-chapter.py` | **placeholder page**, neutral title (no prompt, no material, no choices) | placeholder page, neutral title | PDF handed out **before** the lecture |
| `solutions` | `texstage pdf --solutions`; also the default when Beamer shows notes (`build-chapter.py --notes`) | question, material, correct answers marked; numeric answer, accepted texts, correct order | as written | PDF **after** the lecture; the lecturer's notes PDF |
| `present` | `texstage build` | *reading* slide (the question, no answers), *question* slide, and with `reveal=slide` (default) a *reveal* slide | as written; with `=<id>` it is the quiz's reveal slide | PPTX + server bundle (instructor only) |

A quiz is **one frame in every mode**: in `present` mode its slides are reading, question and
reveal, so frame numbers on the projector match the handout. The **reading slide** (since
2026-10-04) is the question page with the answers' room left empty - the grid is set in a box
that is never shipped and an empty box of its size takes its place, so the prompt, and a shrunk
frame's factor, stay as on the question page. The class reads the question for as long as the
lecturer likes; the click to the question slide makes the answers appear and starts the round
(3 s get-ready, then the countdown). Before, the question slide started the round at once, and
3 s were all the reading time there was. **Leaderboards are not frames**:
the builder adds a leaderboard slide (the reveal image under a live overlay) after a scored
quiz's reveal. Overlays are safe here because the reveal slide exists only in `present` mode:
a test (2026-10-01) showed that `\only<2>` content lands on page 2 of a normal compile and on the
single page of Beamer's `handout` mode, i.e. an overlay-based reveal in the handout would leak.

Handout placeholders are produced inside Beamer: every frame body (fragile ones after their
round trip through the `.vrb` file) is typeset by `\beamer@doseveralframes{<body>}`; for a
`quiz`/`answer` frame in the handout the body is run in a discarded box — `\label`s recorded and
set again, quizzes still validated — and the placeholder is typeset instead.

The look is a theme: macros `\texquizprompt`, `\texquizchoice`, ... (default: Kahoot colours and
shapes); `texquiz-theme-dbis.sty` gives the course look (`\dbisquestion`, `dbox-compact` answer
boxes A, B, C with a shape badge).

Authors preview a quiz with `texstage pdf --present 045.tex`; a plain standalone compile shows
the placeholder, by design.

### 3.2.1 Answer leak prevention (checked by tests)

- `handout` PDF: no prompt, material or choice text and no answer-frame content in the text
  layer; neutral titles; placeholder pages identical whatever the question.
- `present` question page: correct and wrong choices typeset by the same code path — no hidden
  text, no `\uncover`/transparency, no annotations, identical box geometry. A test compiles two
  decks that differ only in the correct answer and requires pixel-identical reading and question
  pages. The reading page carries no answer text at all (its grid is never shipped; tested).
- Answer position: optional `shuffle=true` removes the author's ordering habit as a hint.
- The PPTX and presentation PDF contain answers and notes → instructor-only (as today's PPTX).
- Server: reveal-slide images and keys are served to the host role only; phones receive
  correctness only after the reveal.

### 3.3 Metadata export (`present` mode only)

`texstage build` compiles with `\def\texquizmode{present}` on the command line. In that mode the package:

- writes `\jobname.tqz` (UTF-8 JSON lines): deck setup, every question with type, options,
  correctness, accepted answers, numeric parameters, explanation text (for the CSV and host
  console), and a **page record** per shipped page: `{page, quiz, phase}` (phase ∈ read,
  question, reveal, leaderboard, join, podium);
- records **rectangles** with `\pdfsavepos` at shipout: prompt box, each answer box, timer area,
  live area. The add-in uses them to place counts, bars and checkmarks exactly over the
  LaTeX-rendered boxes;
- typesets the **phone assets** (prompt and every choice) into boxes of phone width
  (≈ 7 cm, black text, no background) while the quiz frame is processed, and ships them as extra
  pages after the last slide. The builder crops them using the recorded sizes and drops those
  pages from the slide sequence. One compile run produces slides, notes, metadata and phone
  assets — macros, fonts and colours are guaranteed identical to the slides.

String values are serialised in hex inside TeX (as in the prototype) and decoded by Python, so
braces, `%`, `#`, backslashes and Unicode never break the JSON.

**Shrunk frames.** Beamer's `shrink` typesets the frame body and then scales the finished box
(`\beamer@shrinkframebox`: `\pgftext[left,top]` under `\pgftransformscale`), a PDF
transformation that `\pdfsavepos` does not see: every position recorded in a shrunk frame is
unscaled. texquiz wraps `\beamer@shrinkframebox`; in present mode it records the factor and
the body's height (`K`) and a mark at the body's top left corner (`Z`). The point the scaling
keeps in place is the body box's reference point, its bottom left corner as recorded
(`Z.y − height`) - measured on 2026-10-02 with marks in frames shrunk as requested, shrunk more
than requested and with `\vfill`, and on the KG pilot's shrunk question frames. The reader
maps the page's rectangles about that point.

**Layout-check marks.** In the solutions and present modes the log gets
`texquiz-check: quiz <id>` / `texquiz-check: answer <id>` while a quiz or answer frame is
typeset and `texquiz-check: page <n>` after every shipped page (a second-screen note page is
shipped after its slide with the same number; with stage notes, §4, it is numbered on, and
`texquiz-check: note` before its page mark says that it is a note page) - see §4.1.

Validation happens in TeX where the information is local (unknown keys, missing `\choice*`,
duplicate IDs → `\PackageError` with source line) and in Python for deck-level checks (duplicate
IDs across files, missing join frame → warning, page/record consistency).

## 4. Build pipeline (`texstage build`)

As built in M1b (2026-10-02). Input: a deck `.tex` - a course chapter's generated
`slides.tex`, or a standalone deck. In a lecture:

```
python tools/scripts/texstage-build.py 06-SPARQL-Semantics [--server https://...]
```

runs `combine-slides.py` in the chapter and `texstage build slides.tex` with the texquiz of
the lecture's own `tools/` checkout (`tools/src`, nothing to install), so style and builder
are always the same version. Output in `<chapter>/build/texquiz/`, which the lectures'
`.gitignore` covers: `<chapter>.pptx`, `<chapter>.bundle/` and `<chapter>.bundle.zip`. Elsewhere:
`texstage build deck.tex [-o dir]` (default `texquiz-out/` next to the deck; a deck called
`slides.tex` is named after its folder).

1. Compile next to the source (relative paths keep working) in present mode with
   second-screen notes (`\def\texquizmode{present}\def\texquiznotes{}`; the note template is
   the one of `beamer2pptx.py`), two passes, output in `<out>/build/`.
2. Read the `.tqz` (rectangles of shrunk frames mapped, §3.3). The PDF must consist of the
   slide pages and the phone-image pages, and the log must mark every slide page - otherwise
   the deck's `texquiz.sty` and the builder are out of step.
3. Render the slide half of every slide page to PNG, 1080 px high by default (`--height`): the
   size of today's course PPTX, and on a 1080p projector the add-in redraws it pixel-exactly
   (§9.1). Notes from the right half (`note_paragraphs`, shared with `beamer2pptx.py` through
   `texstage/build/notes.py`). Phone images: the trailing pages at 3 device pixels per CSS
   pixel, transparent.
4. Plan the PowerPoint slides: one per slide page, plus a **leaderboard slide** (the reveal
   picture again, under a live overlay) after every scored quiz (`points` not `none`, not a
   poll or open question, a numeric question only with an `answer`) that has
   `leaderboard=true`: after its reveal slide, or with `reveal=none` after the last page of its
   answer frame (`answer=<id>`; without one: a warning, and the leaderboard follows the
   question). None is added where the next page is a `\quizleaderboardframe`. An answer frame
   naming an unknown quiz is an error; a deck with quizzes but no `\quizjoinframe` a warning.
5. Write the **bundle** `<name>.bundle/` afresh:
   - `deck.json` - `quizzes`: what the phones get: type, time, points, scored, reveal, poll
     selection, numeric range and unit, open-text settings, the prompt and answer images with
     their CSS size. Answers are named A, B, C, ... by their position on the question slide -
     the labels the slide shows; the authored ids, and the step numbers of an ordering
     question (which are its solution), stay in `keys.json`. `slides`: for every PowerPoint
     slide its slide ID, picture, live phase and quiz, and rectangles as fractions of the
     slide from the top left (answer boxes under `cells` by public id) - for the host views
     only: reveal slides show the answers by nature.
   - `keys.json` - correct answers, `partial`, numeric answer and tolerance, accepted texts,
     the solved order, explanations, and the LaTeX sources of prompts and answers.
   - `slides/`, `phone/` - PNG files named by content hash. `bundle` = hash of both JSON files:
     the same source gives the same bundle ID.
6. Write the **PPTX** (python-pptx + raw OOXML for the web-extension parts, as in the spike):
   every slide gets its picture full-bleed and its notes; live slides (join, question, reveal,
   answer, leaderboard, podium) additionally one **content add-in object over the whole
   slide**, configured through web-extension properties `{server, deck, bundle, quiz, phase,
   slideId}`, with the slide picture as snapshot (what PowerPoint shows while the add-in
   loads). Slides that give an answer away - reveal, leaderboard, answer frame - store their
   quiz's *question* picture instead, as picture and snapshot (since 2026-10-04): PowerPoint
   shows a live slide's stored picture for a moment before its add-in has started, also
   while the add-in prepares the slides (below), and the add-in draws the real slide from the
   bundle anyway. Without a quiz server those slides show the question - present the static
   deck. **Every quiz server has its own add-in**, with an ID derived from the server's
   address (UUID 5 of its origin, `powerpoint.addin_id`): PowerPoint loads an add-in's page
   from the address in its registration, so the add-in the live slides reference decides the
   server of a PPTX - `--server` (default `http://localhost:8470`), or afterwards
   `texstage retarget deck.pptx --server …`, which rewrites the references in a second. The
   add-ins are referenced as sideloaded developer add-ins (`Registry`/`developer`); catalog
   and central deployment (`FileSystem`, `EXCatalog`) are untested (§8).
   **`<name>-static.pptx`**: the same slides and notes without add-in objects, for
   presenting without the quiz. A live slide cannot fall back by itself (tested 2026-10-03):
   if its server is not running, PowerPoint shows the picture with a yellow "ADD-IN ERROR …
   can't load the add-in [Retry] [Close]" bar; on a PC where its add-in is not registered,
   a blank white slide with "ADD-IN ERROR: This add-in is no longer available".
   A deck with live slides gets a **first slide** before its own (since 2026-10-10; not in
   the static deck, not in deck.json - PowerPoint's alone): its picture says what it is for
   (`builder.first_slide`, drawn with Pillow's own font), its add-in object (phase `prepare`,
   the same properties) prepares the live slides when the slideshow starts there (§5.2).
   The **join slide's** add-in object also carries the bundle (property `texquizBundle`:
   base64 of a zip with both JSON files, the phone pictures and the live slides' pictures -
   what presenting from PowerPoint needs), until 2026-10-09: a server that did not know the
   deck got it from there (§5.2). But PowerPoint keeps at most 2 MB for an add-in (the 5.3 MB
   of KG chapter 6, 33 live slides, did not arrive; the keynote's 1.3 MB did, the quiz-heavy
   demo's 1.92 MB is just over). Since then the PowerPoint file carries no bundle, and every
   deck reaches its server through its build, the same way for all: `texstage build` records
   the build folder in the data folder of the machine's quiz server (`builds.json`,
   `texstage/builds.py`; `--data` names another one), which serves those decks too, and uploads
   the bundle to a server elsewhere (`--server`; `cli.deliver`, as `texstage publish` does).
   The bundle also goes into one file next to the PowerPoint file, **`<name>.bundle.zip`**
   (`bundle.write_zip`; pictures stored, not compressed again), to upload by hand in a
   server's deck list (§8): for a server the build could not reach, from any browser.
7. **Check** the quiz and answer frames (§4.1; `--no-check` skips it and the solutions
   build). Exit status 1 if it fails - the files are written all the same.

**The stage PDF** (2026-10-06 with `--stage`; in every build since 2026-10-10, `--no-stage`
leaves it out; texstage, the browser presenter: `texstage-design.md`, §3): alongside step 1,
a second present-mode compile (`<stem>-stage.pdf`,
`\def\texquiznotes{stage}`) with the deck's own note template (DBIS: `dbisscript`), each
note page a page of its own after its slide (`show notes`, not a second screen - the slide
pages carry no note text, so they can go into the students' annotated PDF as they are), no
phone pages, no dates and no trailer ID (the same file when nothing changed). texquiz.sty
marks every note page in the log (`texquiz-check: note`, set through Beamer's
`\AtBeginNote`); `build/stage.py` pairs the slides with their note pages and checks them
against the present compile (as many slide pages, the live pages on the same slides). The
PDF goes into the bundle as `stage/<hash>.pdf` - not into the bundle the PPTX carries - and
`deck.json` gets `pdf` (`file`, `width`, `height` in PDF points) and per slide `frame` and
`step` (from the present compile's `.nav`; a frame broken by `allowframebreaks` is a frame
per page, as Beamer numbers them), `page` and `note` (its pages in the stage PDF; a
leaderboard slide has its anchor's) and `notes` (the extracted text, for texstage's
reflowing view). A note that runs to the bottom of its stage note page fails the check.
A build with `--no-stage` has none of it: no second compile, no `stage/`, nothing of it in
`deck.json` (`--stage` is still taken, and changes nothing).

`texstage pdf --handout|--solutions|--present` compiles the same source in one mode (the
handout is identical to a normal compile; the solutions PDF is the one for after the
lecture). The existing course scripts stay unchanged; `texstage build` is a superset of
`beamer2pptx.py` for decks that contain quizzes.

### 4.1 Layout check of quiz and answer frames

The course's own checks (`build-chapter.py`: pages = frames, overfull boxes, shrink;
`check-labels.py`) only ever see the handout, where quiz and answer frames are placeholder
pages. The pilot showed a converted question whose answer row pushed the author's material
into the footline (06/032 without its `shrink=8`) - invisible to those checks. So the builder
reads the logs of the present build and of a solutions build: the layout-check marks (§3.3)
attribute every `Overfull` box and every "Frame text is shrunk" warning to its page (note
pages are skipped), pages map to frames through the `.nav`, and frames to `NNN.tex` through
the `%%% --- Start of NNN.tex` markers of `combine-slides.py` (else "frame F (page P)").

It **fails** on an overfull `\vbox` of 1 pt or more (content runs into the footline), an
overfull `\hbox` of 5 pt or more, a frame shrunk by `--max-shrink` (15 %) or more, and a note
that fills its page (it would be cut off in the PowerPoint notes). Smaller overfull boxes are
listed as notes.

## 5. PowerPoint integration

### 5.1 The add-in

A content add-in ("texstage", XML add-in-only manifest, permission `ReadDocument`) per
quiz server, served by that server at `/addin/` (§4, §5.4). Each instance reads its
properties via `Office.context.document.settings` and mounts the matching view.

Live slides are **full-slide overlays**: the view draws the slide PNG as its background and
adds the live parts on top (timer, counters, bars inside the answer boxes, leaderboard). So the
look is identical to the static slide and the overlays can sit anywhere on it.

The page (`web/addin/`) is the browser slide host's stage (`web/shared/live.js`, §7) filling
the webview, plus the lecturer's mouse buttons. In PowerPoint's editing view it shows a small
status bar instead (which slide, server reachable, paired) with the pairing form (§5.3).
Nobody sees the console of an add-in, so its errors go to the server's log
(`POST /api/client-log`, hosts only). Office.js comes from Microsoft's CDN: the presenting PC
needs the internet (offline: the browser slide host, §8).

### 5.2 Clicker-driven game flow

| PowerPoint slide shown | Effect on the server (idempotent) | View shows |
|---|---|---|
| join (lobby) | (the session is opened by the add-in's hello: §6.2); after the podium a **new game** with a new PIN - the deck presented to the next group | QR, PIN, nicknames popping in, player count |
| quiz · reading | nothing starts (the class reads the question); a round already there - the lecturer stepped back - stays the phones' round | the question alone, nothing live (a running round is shown on its question slide); phones: the question and "the answers come next" |
| quiz · question (the lecturer's click) | if the round has not started: 3 s get-ready, then open voting | countdown, answers received; "Time's up!" (or "All answers are in!") + distribution when done (correct answer **not** marked) |
| quiz · reveal (`reveal=slide`) | close the round if still open (= skip), score, reveal | answer distribution inside each answer box, ✓ on correct |
| answer frame (`answer=<id>`, for `reveal=none`) | close, score, reveal | the author's answer slide; small results panel (distribution, share correct) |
| leaderboard (added by the builder) | ensure closed and revealed | top 5 with animated rank changes over the dimmed reveal/answer slide |
| podium | finish game | top 3 podium, then full ranking |

Going back never restarts a round; a small on-slide button (mouse) offers "ask again" as a
practice round, which also rewinds the game there: the later quizzes' rounds are withdrawn,
points and all, and those questions are asked anew (2026-10-05 - after a test run, or a
lecture restarted after an interruption, the game otherwise showed only old results from
there on). Mouse buttons on the overlay (also visible to the room, as in Kahoot): skip,
+10 s, pause.

**Which instance is the visible slide?** PowerPoint preloads the next slide's add-in and keeps
all instances alive (§9.1), so creation means nothing. Every instance polls
`getSelectedDataAsync(SlideRange)` (~250 ms) and acts only when the current slide ID equals its
embedded `slideId`: it connects as a host and reports the slide, and stays connected 15 s
after its slide is left. The instance that was activated last also reports the ordinary slides
in between, so the server always knows the slide. Presenter View renders the current slide
twice (the room's screen and the lecturer's); both instances activate, and the server treats
every activation as idempotent (verified in M4).

**The deck comes with its build** (since 2026-10-09, §4). The server on the machine that built
it scans the build folders recorded in its data folder's `builds.json` besides the folders it
serves and the uploads (`BundleStore(more=...)`, asked at every scan: also a deck built while it
runs, complete, with its stage PDF for texstage; folders that are gone drop out); a server
elsewhere got it uploaded by the build - or by hand, its `.bundle.zip` in the server's deck
list (§8). An instance whose server answers "unknown bundle"
retries every 3 s and says where the deck comes from: the laptop that built it, or a build for
this server (or `texstage publish`); `texstage check` says the same before the lecture.

Files built before carry the bundle on their join slide: an instance that carries it uploads
it once (`PUT /api/bundles/<id>`, presenter key) and goes on - the join slide comes before the
questions and PowerPoint loads it a slide ahead, so the upload was done before anyone saw it
(verified with an empty server, 2026-10-03) - as far as PowerPoint lets the add-in read it (2 MB;
`texstage check` names a file that carries more). The server keeps such an upload
(`<data>/bundles/`), marked incomplete (no ordinary slides' pictures); the full build replaces it.

**Why the bundle sits in one add-in object** (spike, 2026-10-03): stored there or as a custom
XML part, it survives editing and saving in PowerPoint (also 4 MB; the slide pictures stay
byte-identical). But an add-in object reads only its own properties; the custom XML parts are
invisible to the PowerPoint API (1.9) at the `ReadDocument` permission, and reading the whole
file (`getFileAsync`) needs `ReadAllDocument`. A 1.2-5 MB property costs nothing measurable
(read 0 ms, decode 3 ms). So: one copy, on the slide that is shown first anyway, and the
add-in keeps its small permission. (2026-10-09, in a real chapter: more than 2 MB does not
arrive - since then the PPTX carries no bundle, §4.)

**The white flash when a live slide's object starts** comes from PowerPoint: for the first
add-in of a freshly opened file about 950 ms pass inside PowerPoint before the page is even
requested (the request itself takes 3 ms); in a running slideshow 60-100 ms. (On the way, the
server now listens on IPv6 too: Windows tries `localhost` as `::1` first, and each new
connection to an IPv4-only server waited up to a second.) Recorded again on 2026-10-04 with a
rebuilt chapter (frames of the slideshow window, three per second): the **first** display of
every live slide after opening the file shows the stored picture, then white, black, black with
the add-in still at its small preload size in the top left corner, and only then the slide -
1.5 to 4 s, **also when presenting forward** (loading the next slide ahead does not prevent
it). Changes to an ordinary slide, and every later display of a live slide, are clean; the
started add-ins stay until the file is closed, also when the slideshow ends and starts again.

**Preparing the live slides** (since 2026-10-04) therefore moves all those first displays
before the lecture. The first time a join slide is shown in a slideshow, its add-in asks the
deck's other instances (BroadcastChannel per bundle) which slides have already been shown
since the file was opened, then shows every later live slide that has not - Office.js
`goToByIdAsync` moves a running slideshow (tested) -, each until its instance reports that it
is on the screen and drawn (at most 10 s), and returns to the join slide. Meanwhile it sends
`prepare` (the server starts, reveals and finishes nothing, and the phones stay where they
are; off by itself after 10 minutes), and a localStorage flag makes every live slide of the
deck show "Preparing the quiz slides n / N" instead of its content. A key the lecturer presses
meanwhile (the slideshow is not on the slide the preparation went to) ends it. Measured: 82-89
s for the 17 later live slides of a one-session chapter (PowerPoint takes 2-6 s to start each
add-in); afterwards a whole forward pass through the chapter, including leaderboard and
podium, showed no white or black frame. A slide reached by a jump may still show one white
frame (about 0.3 s).

**The first slide prepares** (since 2026-10-10, the lecturer's wish: the join slide comes in
the lecture, and its preparing put a minute and a half of "Preparing the quiz slides" before
the class). The live PPTX starts with a slide of its own whose add-in (phase `prepare`) does
the same for every live slide of the deck when the slideshow starts there, comes back, and
says **Ready** - the number prepared, the game's PIN, the players, the join address; in the
editing view what the slide is for. It stays there: the lecturer goes on with the clicker. Its
slide ID is not the deck's, so its add-in reports only the deck's slides to the server (the
server would take an unknown ID as an ordinary slide's anyway). The join slide still prepares,
but finds nothing left - unless the slideshow started further on, or the file was built
before. Checked in a browser with Office.js stood in for (a slideshow that starts on the first
slide; the 16 live slides of the keynote); not yet in PowerPoint.

### 5.3 Presenter credential

**Every lecturer has a presenter key of their own** (since 2026-10-03). A host connection or
request is the lecturer whose key it brings and sees only that lecturer's things: their
uploaded decks (`<data>/bundles/<lecturer>/<deck>/<bundle id>/`), their games (one running game per
lecturer and deck - two lecturers may both have a deck "01-intro"), their results, their
uploads. Decks in folders given to `texstage serve` (the laptop's chapters) are open to all its
lecturers, each with their own game. The server keeps the keys' SHA-256 hashes in
`<data>/lecturers.json`, managed on the server's machine with `texstage lecturer add NAME`
(shows the new key once), `renew NAME`, `remove NAME`, `list` (in Docker: `docker compose exec
texquiz texstage lecturer add NAME --data /data`); a running server rereads the file when it
changes. The server's own key (`<data>/presenter-key`, made at its first start) is one more
lecturer, named after the user running it (`texstage serve --owner`) - on a laptop the only one,
so a single lecturer notices nothing of all this.

The add-in needs host rights. **The live deck carries its server's presenter key** (property
`key` of every live slide, next to `server`; since 2026-10-03, the lecturer's decision: a
live deck must work plug and play, nothing to type in front of the class). `texstage build`
takes it from `--key`, `TEXSTAGE_KEY`, the key remembered for the server
(`~/.texstage/servers.json`), or - for a server on this machine - the data folder's
`presenter-key` (`texstage/keys.py`); `texstage retarget` swaps it with the server. Without a
known key the build warns and the slides fall back to pairing.

Fallbacks, if the server rejects the deck's key (it got a new one): the key stored in
`localStorage` of the add-in origin (shared by all instances, kept across restarts, §9.1),
then the server's own when it runs on the same machine (`GET /api/presenter-key`, answered
only to loopback addresses), then the status bar in the editing view asks for it. A rejected
key is forgotten and never tried twice.

The PPTX is the lecturer's file: its reveal slides and the bundle it carries hold the answers
anyway, and now the key - whoever has it can run that lecturer's games, see their results and
upload decks as them. If a PPTX gets out, that lecturer gets a new key (`texstage lecturer renew
NAME`; the server's own: delete `presenter-key`, restart) and the decks are built or
retargeted again. Students get the handout PDF, never the PPTX.

### 5.4 Registration (one-time per presenting PC)

- `texstage addin install [--url http://localhost:8470]` writes that server's manifest to
  `~/.texstage/texstage-addin-<host>[-<port>].xml` ("texstage (<host>)") and sideloads it via
  `HKCU\Software\Microsoft\Office\16.0\WEF\Developer` (value: add-in ID → manifest path); once
  per PC and server, per user, no admin rights; PowerPoint reads it at start.
  `texstage addin list` shows the registered texstage add-ins, `texstage addin uninstall
  [--url … | --all]` removes them. The server also serves the manifest for its own address at
  `/addin/manifest.xml` (and `texstage addin manifest` prints it).
- Which server a deck uses is part of the PPTX (§4: `--server`, `texstage retarget`). Why not
  a custom document property, editable in PowerPoint (2026-10-03): the add-in can read one,
  but PowerPoint loads the add-in's page before - from the address of the referenced add-in's
  registration - so a property could only make the page move on from there (works, tested),
  and that first address would have to be reachable too. Macros cannot help: a .pptx holds
  none, PowerPoint runs nothing when a file opens, and macros are often blocked.
- A shared-folder catalog (`TrustedCatalogs`) or central deployment by the university's
  Microsoft 365 admins would spare the per-PC registration but is untested (§8).
- **`texstage check deck.pptx`** (`scripts/texstage-check.py <chapter>`, `preflight.py`) before
  the lecture: reads what the live slides carry and checks, in the order things fail in front
  of the class, the add-in registration of the deck's server on this PC, the server
  (`/api/status`, which also names the join address), the deck's key (`/api/decks`), the
  deck on the server or a carried bundle, and Office.js (internet). `ready`, or `PROBLEM`
  lines with what to do and the static deck; exit status 1.
- HTTPS: hosted server via Let's Encrypt (Caddy). Laptop: plain `http://localhost` works for
  PowerPoint on the same machine (§9.1); phones use the laptop's LAN address.

### 5.5 Testing in PowerPoint

`tools/slideshow.ps1 run deck.pptx "goto 2" "sim 20" "next" "wait 25" "shot q1" … [-PresenterView]`
drives a real slideshow over COM in one call (PowerPoint started by a script quits when the
script ends): clicker steps, simulated phones (`tools/simulate.py --pin`), screenshots of the
show and the presenter view, the game's CSV. Screenshots must be taken DPI aware: PowerShell is
not, and on a monitor scaled to 150 % it sees and captures only the top-left 2560×1440 of a
3840×2160 screen - which looks exactly like an add-in that paints only part of its slide.

**M4 test run** (2026-10-02, PowerPoint 16.0.20326, three 4K monitors at 150 %/200 %): the demo
deck played with the clicker only, 20 simulated phones: lobby with QR code and players, every
question type with timer, distribution and reveal, leaderboards, podium, CSV; then with
Presenter View (§9.1, 3c). Still to do: real phones on a real network, and the lecture PC.

## 6. Game server

As built in M2 (2026-10-02). Python 3.14, Starlette + uvicorn (WebSockets), stdlib `sqlite3`.
One process, asyncio. `src/texstage/server/`:

| Module | |
|---|---|
| `game.py` | the game as a synchronous state machine: never reads a clock (every call gets `now`), never waits; unit-tested with a fake clock |
| `scoring.py` | answer validation, judging, points (pure functions) |
| `bundles.py` | loading and checking bundles (format, the bundle ID against both JSON files), finding them by ID |
| `store.py` | SQLite, written through by the engine |
| `app.py` | HTTP + WebSocket, pushing state, the timer |

```
texstage serve [bundle folders] [--port 8470] [--host 0.0.0.0] [--public-url URL] [--tunnel NAME | --no-tunnel]
              [--data ~/.texstage] [--key K] [--forwarded-allow-ips IPS]
```

serves the bundles in the given folders (a bundle folder, or folders holding bundles, three
levels deep - e.g. a chapter's `build/texquiz/`) and the published ones (`<data>/bundles/`,
§8); a bundle built while the server runs is found when a host asks for it. The presenter key is made on the first start and kept in the data
folder (`presenter-key`, next to `texquiz.sqlite3`); the start message shows only its first
characters (a terminal is often on a shared screen or in a recording), `--show-key` all of it. Phones join at `--public-url` (default:
`http://<LAN address>:<port>`; with `--tunnel`, the tunnel's hostname, §8). Two addresses, kept
apart: the live slides talk to the server their deck names (`--server` at build time, on a
laptop `http://localhost:8470`), the phones to `--public-url` (a server setting, shown on the
join slide - changing it needs no rebuild).

### 6.1 Model

| Entity | Fields |
|---|---|
| Bundle | id, deck, name, slides (PowerPoint slide ID → phase, quiz), quizzes (public part, keys) |
| Session | id, pin (6 digits, unique among running games), deck, bundle, created, last_active, ended, finished (podium shown), slide (what the lecturer shows), current (the round the phones show) |
| Player | id, session, nickname, token_hash, joined, kicked, score, streak, total answer time, rank, previous rank |
| Round | id, session, quiz, attempt, practice, phase (get-ready/open/closed/revealed), started, opens, deadline, limit, pause, closed (by time/skip/all), revealed |
| Answer | round, player, payload (canonical JSON), received, answer time, correct, credit, points, streak bonus |

**One running game per lecturer and deck.** The add-in's hello opens it: the lecturer's
running game of the deck if it plays the same bundle and has been active in the last 6 hours,
else a new one (the old one ends): the next lecture, or a rebuilt deck. After the podium, the
join slide starts a new game for the next group; the host can also start one explicitly
(`restart`).

**Lectures and versions.** A deck's ID names the lecture: `texstage-build.py` makes it
`<course>-<chapter>` (`kg-06-sparql-semantics`; the course is `"course"` in `lecture.json`,
else the lecture folder's name), so the chapters of different courses never share a name. The
bundle ID names the version: a fingerprint of `deck.json` and `keys.json` - questions, answers,
slide pictures (by their content hashes) - and each PPTX names exactly its own. The server
keeps every version apart: uploads as `bundles/<lecturer>/<deck>/<bundle id>/` (deck.json
dated to the build), and a deck from a served build folder is copied to
`served/<deck>/<bundle id>/` when a game starts with it - a rebuild replaces the build folder,
and the game, or an older PPTX shown elsewhere, goes on with its own pictures. The newest 10
builds per deck stay (`KEEP_BUILDS`, never one a game plays); a cleaned-up version comes back
when its PPTX is shown (the join slide). The host page lists the newest build of each deck,
plus the one a running game plays.

**Rounds** (`show_slide`, every step idempotent): a quiz's reading slide starts nothing - the
phones show its question (`reading` in their view) unless the quiz already has a round, which
then stays the current one; the question slide starts a round for its quiz
unless the quiz has one - get-ready 3 s, open for the quiz's time, closed when the time is up,
when every connected player has answered or when the lecturer skips; reveal, answer and
leaderboard slides close it if still open, judge, score and reveal. Going back never restarts a
round; `again` asks a revealed question once more as a practice round and rewinds the game
there: every round of the quizzes after it in the deck is deleted with its answers, and the
scores, streak bonuses and ranks are counted again from the rounds left. `pause` freezes the
countdown (answers are refused meanwhile; answer times leave the pause out), `extend` adds
time. An answer that arrives up to 0.5 s after the time ran out still counts (network, clocks),
not after a skip.

Everything lives in memory and is written through to SQLite, one transaction per engine
call; answers are inserted, unique per round and player. A restarted server continues: running
games, players (their tokens' hashes - phones reconnect with `resume`), rounds with their
deadlines (overdue ones close at their deadline), answers. Ended games are dropped from memory.

### 6.2 Roles and protocol

- **host** (add-in instances, host console): `hello` with the presenter key, deck and bundle;
  the key names the lecturer (§5.3), who gets only their own decks and games.
  `GET /api/presenter-key` gives the key only to the machine itself (not through a proxy,
  §8), so PowerPoint on the laptop pairs without typing it.
- **player** (phone): `join` with PIN and nickname (1-20 characters, unique in the game
  regardless of case) → a token (kept in the phone's localStorage), `resume` with it after a
  reconnect.
- **stage** and **display** (2026-10-07; texstage's presenter and projector windows,
  `texstage-design.md`): `hello` with the presenter key, like a host, and the host view, which
  also carries `stage` (what the projector shows - live, black, white or a frozen slide - and the
  presenter's timer; stored with the game). stage can do what a host can, plus
  `screen {screen}` and `timer {action, seconds?}`, and (M2) ink, the laser pointer, the zoom and
  whiteboard pages (`ink.*`, `pointer`, `zoom`, `board`, `go`; `texstage-design.md`, section 17);
  display only loads ink. A paired presenter device (an iPad, M3: `texstage-design.md`, section
  18) brings its own token instead of the key (`hello {device}`, header `X-Texquiz-Device`) and
  presents as its lecturer, but does not publish or pair. After the lecture (M4, section 19) the
  presenter window puts the annotated PDF into the lecture archive
  (`PUT /api/archive/<game>/annotated.pdf`, `GET /api/archive/<game>.zip` with the results). A
  recording (M5, section 20) reaches the archive in parts while it is made (`POST
  /api/archive/<game>/recording`, `PUT /api/recording/<take>/<n>`, `POST .../done`; downloaded
  through `/download/<ticket>/<name>`). M6 (section 21): stage asks ad-hoc polls (`poll.create`,
  `poll.show` - quizzes of the game, stored with the session, revealed as soon as they close),
  shows picked drawings of a sketch question (`sketch.list`, `sketch.show`; display may
  `sketch.get`) and moderates the audience's questions (`qa.open`, `qa.show`, `qa.mark`,
  `qa.block`); players ask and upvote them (`qa.ask`, `qa.vote`) and get the list only while they
  show it (`qa.watch`).
- One WebSocket per client; JSON messages `{"t": ...}`. A command may carry an `id`; the reply
  (`ok`, `welcome`, `error` with a code) carries it back as `re`, and a command resent with the
  same id is answered from a cache, not run twice. Host commands: `slide`, `skip`, `pause`,
  `continue`, `extend`, `reveal`, `again`, `kick`, `rename`, `finish`, `restart`, `prepare`
  (§5.2, preparing the live slides); player:
  `answer`. HTTP for hosts (header `X-Texquiz-Key`): `/api/decks`, `/api/deck/<bundle>`
  (deck.json), `/api/deck/<bundle>/pdf` (the stage PDF of a `--stage` build, §4; it holds
  every reveal page, so it is not a picture), `/api/results/<game>.csv`,
  `PUT /api/bundles/<id>` (`texstage publish`, §8), `POST /api/bundles` (a `.bundle.zip`
  uploaded by hand, §8).
- The server pushes `{"t": "state", "now": <server ms>, "role": ...}` with the role's view after
  every change - to players at once, to hosts at most every 200 ms while answers come in - and
  `bye` when a player is removed or the game is over. Pushes replace each other per
  connection, so a slow phone only gets the newest state. Clients count down from `deadline`
  and `now` (clock offset).
- **Views.** Players: their game (PIN, name), themselves (score, rank, streak) and the current
  round - timing, the quiz's public part (`deck.json`), their answer; after the reveal their
  result and the keys (`correct`, `order`, `answer`, `tolerance`, `accept`); after the podium the
  top 3. Hosts: the game (PIN, join URL, QR code URL, slide), all players with score, rank,
  previous rank and connection, and the latest round of every quiz - timing, answer count, the
  distribution once closed (`counts` per answer, `values`, `groups` of normalised texts,
  `positions` per item), the keys after the reveal. Nothing about correctness leaves the server
  before the reveal, not even to hosts: their views are on the projector.
- **Pictures**: `GET /bundle/<id>/<slides|phone>/<hash>.png`. Their names are content hashes
  listed only in `deck.json`, which only hosts get, so a reveal slide's picture cannot be
  guessed by a phone; `deck.json` and `keys.json` themselves are not served.
- `GET /join/<pin>.svg`: the QR code of the join URL.

### 6.3 Scoring

Kahoot-like, per quiz `points=standard|double|none`: a correct answer earns
`round(base × (1 − ½ · t_answer / t_limit))`, `base` = 1000 or 2000 - from the full base for an
instant answer down to half at the end. Streak bonus: +100 for the second correct answer in a
row, +200 for the third, ... at most +500 (a setting). `multiple`/`order`: exact answer required
unless `partial=true`; then the points times the share right - for `multiple` (right chosen −
wrong chosen) / right, for `order` the items in their place - and only an exact answer counts
as correct for the streak. `numeric`: correct within `tolerance` (without `answer`: an estimate,
unscored). `text`: compared after normalising case, accents and spacing. Polls, open questions,
`points=none` and practice rounds: no points, streaks untouched. Ranks: score, then total
answer time, then who joined first.

## 7. Views

As built in M3 (2026-10-02): plain JavaScript modules and CSS in `src/texstage/web/`, served by
the server (`/play`, `/host`, `/static/...`), no frameworks, no build step and nothing from the
internet (a lecture hall may have none). `shared/client.js` is the WebSocket client of all
pages: reconnects by itself, resends a pending command with its id, keeps the server's clock.

- **Live views** (`shared/live.js`, `live.css`): a *stage* shows one slide - its picture and,
  positioned by the slide's rectangles (`deck.json`), the live parts from the host view. The
  stage is a CSS size container, so everything scales with the slide (the same in a browser
  window and in the add-in's 1280×720 webview). Per phase:
  - join: PIN, join address, QR code, the players popping in;
  - question: get-ready countdown and timer ring with the answer count - in the timer square of
    a quiz frame of its own; for a quiz inside the author's frame (no free corner) a pill on the
    footline, bottom right; after the close "Time's up" and the distribution: count, share and
    bar inside each answer box (correct ones **not** marked), a histogram (numeric) or a word
    cloud / list (text, open) in the live area or, for inline quizzes, a panel;
  - reveal: the same with the keys: correct boxes outlined, the right number's bar green,
    accepted texts green, for an ordering the share of players who put each item in place;
    "n / m correct";
  - answer frame (`reveal=none`): a small results panel in the corner of the author's slide,
    fading after 10 s (the mouse brings it back);
  - leaderboard: the slide dimmed, the top 5 moving from their previous ranks to the new ones;
  - podium: the top 3 rising, 2-1-3.

  A round that is not revealed is always shown on its question slide - e.g. "ask again" pressed
  on the reveal slide: the reveal picture would give the answer away; or the lecturer stepped
  back to the reading slide: the answers and the timer would vanish. A reading slide without a
  round shows nothing live. Mouse buttons on the
  stage (shown while the mouse moves over it, as in Kahoot visible to the room): pause/continue,
  +10 s and skip while a question runs, ✓ reveal once it is closed, ↻ ask again (practice, and
  the questions after it start anew) once revealed. Texts in English or German, the buttons' too:
  the deck's language (deck.json's `language`, babel's main language; since 2026-10-24 - English
  before).
- **Phone** (`/play`): PIN (from the QR code's link) and nickname → "You're in" → while the
  reading slide is up the question picture and "Read the question – the answers come next" → get-ready →
  the answer screen per type: shape buttons with the LaTeX pictures (two columns only if every
  picture fits at full size; all answers of a question at one scale, so their text has one
  size), toggles + submit for multiple choice, a slider (or a number field without a range),
  a text field with a counter, ▲/▼ to order → "answer sent" with the pictures of the chosen
  answers → the result (correct / partly / wrong / no answer, points, streak bonus, rank, the
  right answer as pictures) → the final rank and the top 3. The pictures are cropped to what is
  drawn (by the builder) and shown 1.4× their LaTeX size (about 18 px text). The token is kept
  in localStorage: a reload or a lost connection resumes the player. Texts in English or German
  (the phone's language).
- **Host console** (`/host`): pairs by itself on the server's machine (`/api/presenter-key`),
  else asks for the key once; lists the decks on the server (the build on disk; running games
  with PIN and players) → the game: PIN and join address, a **browser slide host** (the deck's
  pictures with the live views; ←/→, PageUp/PageDown - what clickers send -, Space, Home/End,
  F for full screen), the players (rank, score, online; rename, remove), the quizzes (phase,
  answers; a click jumps to the quiz's reading slide), results as CSV, a new game. The stage follows the
  slide the server reports, so with PowerPoint as slide host the console is a remote and a
  second screen. A reload returns to the running game.

**M3 test run** (2026-10-02, in the app's browser): the demo deck and the KG pilot chapter
06 (inline quizzes in shrunk frames, predict-then-see with answer frames) played from the host
console with one browser phone and 24-30 simulated phones (`tools/simulate.py --pin`): every
question type, reveal, answer frames, leaderboards, a practice round, the podium, the CSV, a
server restart in the middle (the browser phone and the console reconnected by themselves).
Real phones on a network: still to do (§8).

## 8. Deployment

As built in M6 (2026-10-02). The same server runs in two places; the PPTX does not care which
(the add-in talks to the server its manifest names, §5.4).

**Laptop.** `texstage serve` (in a lecture: `tools/scripts/texstage-serve.py`) listens on all
interfaces, IPv4 and IPv6, so phones in the room reach it. The QR code and the join URL use `--public-url`,
by default the address of the default route; `texstage serve` lists the machine's other
addresses (a hotspot, a VPN, virtual adapters) and how to choose one, and says to open
`<public-url>/api/status` on a phone as a test. Windows asks once whether Python may accept
connections: allow it for the network type in use (eduroam is often "public"). Some networks
(eduroam among them) do not let phones reach a laptop at all - then a phone hotspot or the
laptop's hotspot, a tunnel, or the hosted server. PowerPoint and the host page use `http://localhost`
and pair by themselves (§5.3).

**Starting a lecture** (2026-10-10). `texstage present <deck.tex | build folder>` (in a lecture
`tools/scripts/texstage-present.py <chapter>`; `texstage` is the same command) is the one
command: it builds the deck if its newest build is missing, has no stage PDF or is older than
a source in the deck's folder (`.tex`, `.sty`, `.cls`, `.bib`, pictures; not the build folders,
not a PDF beside the deck - the compiled deck - and not a chapter's `slides.tex`, which
combine-slides.py writes; `cli.needs_build`), then asks `http://localhost:<port>/api/status`
whether this machine's server runs. If it does, the server finds the build by itself
(`builds.json`, §4) and only the deck is opened; if not, `texstage serve` runs in this process
over the build folder and the others named (a chapter: every chapter's `build/texquiz`), with
the remembered tunnel, and opens the deck once the server answers. Opened is texstage's presenter
window on the deck (`/stage?bundle=<id>`), or with `--powerpoint` the live PPTX in the program
the system opens it with. `texstage serve` stays for the server alone (`--present` opens the
presenter's deck list).

**Laptop with a tunnel** (2026-10-04). The phones come through Cloudflare, the laptop only
connects out: `texstage serve --tunnel NAME` runs `cloudflared tunnel run NAME` with the server
(`server/tunnel.py`; on Windows in a job object, so cloudflared ends with the server however
the server ends) and listens on the loopback only - no firewall prompt, nothing reachable in
the room's network. The phones' address is the hostname cloudflared's config sends to the
server's port (`config.yml` where cloudflared finds it, `ingress: - hostname: quiz.example.org,
service: http://localhost:8470`), or `--public-url`. The data folder remembers the tunnel
(`tunnel.json`; `--no-tunnel` forgets it), so `tools/scripts/texstage-serve.py` needs no option
after the first start. The decks do not change: their slides still talk to
`http://localhost:8470`; only the join slide's address and QR code name the tunnel. Once
cloudflared runs, the server fetches `<public-url>/api/status` over the internet until the
`instance` there (random per server process) is its own and says "the tunnel works" - or why
not (Cloudflare's 530: the tunnel is not running, 502: cloudflared cannot reach the server;
cloudflared's log is `<data>/cloudflared.log`); `texstage check` tries the address the same way
before the lecture. The lecture hall's network must let cloudflared out (port 7844). cloudflared
runs with `--protocol http2` (TCP): its default QUIC needs UDP to port 7844, which university
networks often block, and there cloudflared 2026.9 took 2.5 minutes to fall back to HTTP/2 - the
server's check had given up after 90 s (`protocol:` in cloudflared's config or
`TUNNEL_TRANSPORT_PROTOCOL` choose another). A named
tunnel with the lecturer's own domain is the one for lectures; quick tunnels (a random
`trycloudflare.com` address) are meant for tests and cap concurrent requests.

**Hosted.** `deploy/`: a Docker image of the server (`python:3.14-slim`, the volume `/data`
holds bundles, games and the presenter key) behind Caddy, which gets a Let's Encrypt
certificate for the domain and passes WebSockets through:

```
cd deploy && echo TEXQUIZ_DOMAIN=quiz.example.org > .env && docker compose up -d --build
docker compose exec texquiz texstage lecturer add decker --data /data     # a key per lecturer
```

A deck built for the hosted server (`--server https://quiz…`) is uploaded at the end of its
build (§4), complete - for PowerPoint, the host page (the ordinary slides' pictures) and
texstage (the stage PDF). `texstage publish <build folders> --url https://quiz… --key K
--remember` (in a lecture: `tools/scripts/texstage-publish.py`) uploads builds made for another
server, or made while this one could not be reached: every bundle the server does not have
complete goes as a zip to `PUT /api/bundles/<id>` (hosts
only); the server accepts only the bundle's own file names, checks the bundle ID against the
JSON files and the size (200 MB), and keeps it as `/data/bundles/<lecturer>/<deck>/<bundle
id>/` next to the deck's other builds (§6.1).

**By hand** (2026-10-09), nothing to install: the deck lists of the host page and of
texstage's presenter take a deck's `<name>.bundle.zip` (§4) - **Upload a deck**, or the file
dropped onto the list (`web/shared/upload.js`) - and send it to `POST /api/bundles` with the
presenter key (a paired device's token is not enough). The ID is the one its deck.json names,
then the same checks and the same place as above; a deck the server has complete already is
left as it is ("the server has it already"). A `.bundle` folder zipped by hand is read the
same way (`bundle_files`): the files inside one folder (also nested), backslashes
(PowerShell 5's `Compress-Archive`), Finder's `__MACOSX/` and `.DS_Store`, Explorer's
`Thumbs.db` - for builds from before the `.bundle.zip`. Error messages name the problem, not
the server's folders.

The hosted server's add-in is registered once per PC
(`texstage addin install --url https://quiz…`), and the decks are built for it with
`--server https://quiz… --key K` (or `texstage retarget`): they carry its address and key and
pair by themselves (§5.3).

On the internet: the presenter key is never handed out through a proxy (`/api/presenter-key`
answers only requests from the machine itself, addressed as localhost, without
`X-Forwarded-*` or `CF-Connecting-IP` headers - this also stops DNS rebinding; through a tunnel
a request also carries the tunnel's hostname); uvicorn takes the client address and `https`
from the proxy's headers (`--forwarded-allow-ips`: by default from 127.0.0.1 and ::1, i.e. Caddy
or cloudflared on the same machine; `*` in Docker, where only Caddy reaches the server); wrong
PINs are counted per client address (300 in 10 minutes - a lecture hall behind one NAT address
stays far below, a PIN guesser is slowed to a crawl). Behind a tunnel, too, every phone counts
with its own address, not cloudflared's: otherwise anyone could lock the class out by
mistyping PINs.

**Load** (M6 test, one Windows laptop running the server and all simulated phones,
`tools/simulate.py`): the demo deck with 300 phones - joined in 0.6 s, every slide reached
the last phone within 75 ms, answers accepted within 9 ms, the server used 5 s CPU in a 66 s
game and 160 MB. With 1000 phones answering within 1.5 s: slides within 0.27 s, answers within
19 ms (95 %), 18 s CPU in 103 s, 430 MB. One process is plenty for a lecture hall.

**Not done.** The Docker image was not built here (this machine's Docker runs Windows
containers only); real phones on a real network, the lecture hall's network and PC.
Office.js comes from Microsoft's CDN, so PowerPoint needs the internet; without it, the browser
slide host (`/host`, F for full screen) plays the deck instead - it needs no internet. A shared
add-in catalog or central deployment by the university's admins would need the PPTX's add-in
reference to match that store; untested, and per-user sideloading needs no admin rights.

## 9. Risks and the first spike

The PowerPoint side is the riskiest part and has never been verified (the prototype stopped
before Office execution). Spike S1 answers, in the installed PowerPoint (16.0.20326, x64):

1. Does PowerPoint load a content add-in object that a **script** wrote into the PPTX
   (`webextension` part + `graphicFrame`), with `storeType=Registry/developer`?
2. Are the embedded `we:property` values readable through `Office.context.document.settings`?
3. In slideshow: when are add-in instances created/destroyed, which events fire on slide change,
   does `getSelectedDataAsync(SlideRange)` report the current slide, do neighbouring slides'
   add-ins preload? Same questions for Presenter View.
4. Is `localStorage` shared between instances (and across PowerPoint restarts)?
5. Is HTTPS mandatory for a sideloaded add-in on `localhost`? Is the webview background
   transparent?

Method: a throw-away probe add-in (`spike/`) reports every lifecycle event to a logging server;
PowerPoint is driven over COM (open deck, run slideshow, go to slides) so the test is repeatable.

### 9.1 Spike S1 results (2026-10-01, PowerPoint 16.0.20326 x64, Windows 10, one 1920×1080 screen)

| # | Question | Result |
|---|---|---|
| 1 | Script-written add-in objects load? | **Yes.** PowerPoint reports them as `msoContentApp` (shape type 27) and runs them in the slideshow. Reference `storeType="Registry" store="developer"` + `HKCU\…\WEF\Developer` sideloading works; no trust prompt appeared. |
| 2 | Embedded properties readable? | **Yes.** `settings.get(k)` returns the JSON-decoded `we:property` values (numbers, strings, nested objects, Unicode, `"<&>`). |
| 3a | Instance lifecycle | Instances are created on demand and **stay alive** for the rest of the slideshow (and after it, until the file closes). The add-in on the **next** slide is preloaded when the current slide is shown; a jump loads the target on demand (~0.1–0.2 s). |
| 3b | Which slide is showing? | `getSelectedDataAsync(SlideRange)` returns the **current slideshow slide** (`{id, index}`, `id` = `p:sldId/@id`, known at build time) to every instance. `DocumentSelectionChanged` does **not** fire on slideshow navigation, `visibilityState` stays `visible`, and `resize` fires only sometimes. → Poll every ~250 ms and compare with the instance's embedded slide ID. |
| 3c | Presenter View | Not tested in S1 (one monitor). **M4** (three 4K monitors): the show is a `screenClass` window, the presenter view a `PodiumParent` window on another monitor; the presenter view's current slide runs a second live instance of the add-in, the game is unaffected. Its *next slide* preview stays white (cosmetic; the preloaded instance has a fixed small size). |
| 4 | `localStorage` shared? | **Yes**, shared by all instances of the add-in origin and **persistent across PowerPoint restarts**. |
| 5a | HTTPS required? | **No** for a sideloaded add-in served from `http://localhost` (desktop PowerPoint). A remote server needs HTTPS anyway. |
| 5b | Transparent background? | **No**, the webview is opaque white. |
| 5c | Rendering quality | Webview layout is 1280×720 CSS px at `devicePixelRatio` 1.5 on a 1920×1080 slideshow; a 1920×1080 slide PNG drawn by the add-in matches the original almost pixel-exactly (mean abs. difference 0.2/255). On a 3840×2160 screen at 150 % (M4): 1281×721 CSS px at `devicePixelRatio` 3. |

Consequences for the design:

- Full-slide overlays (§5.1) are confirmed: the view draws the slide PNG itself.
- Current-slide detection (§5.2) = polling `SlideRange` and comparing with the embedded slide ID.
  Since every live instance sees the current slide, the add-in also reports **every** slide
  change to the server (the bundle maps slide IDs to phases), so phones can follow the lecture.
- Because instances persist after the slideshow ends, every view watches `ActiveViewChanged`
  and switches to a passive setup view in editing mode.
- Laptop mode needs no certificate for PowerPoint on the same machine (§5.4 simplified).

## 10. Project layout

In the `lecture-tools` repository (since 2026-10-02):

```
lecture-tools/
  pyproject.toml           # package + CLI entry point "texstage"
  latex/                   # texquiz.sty, texquiz-theme-dbis.sty (and the lectures' dbis-slides.sty)
  scripts/texstage-build.py # a lecture chapter -> live deck (besides the other lecture scripts);
                           # texstage-present.py, texstage-serve.py, texstage-publish.py, texstage-check.py;
                           # install-skills.py (the shared skills into a lecture)
  skills/plan-quizzes/     # Claude Code skill: a chapter's quizzes planned (QUIZ-PLAN.md,
                           # approved by the lecturer), written, verified, revised from results
  deploy/                  # Dockerfile, docker-compose.yml, Caddyfile: the hosted server (§8)
  src/texstage/
    cli.py                 # present | pdf | build | check | retarget | serve | lecturer | publish | addin
    keys.py, preflight.py  # presenter keys (§5.3); texstage check (§5.4)
                           # (server/lecturers.py: the lecturers and their keys' hashes)
    addin.py               # the add-ins' manifests and their registration (§5.4)
    publish.py             # bundles onto a hosted server (§8)
    build/                 # latex.py (compile), tqz.py (metadata), raster.py, notes.py,
                           # bundle.py, powerpoint.py (PPTX + add-in objects), check.py, builder.py
    server/                # game.py, scoring.py, bundles.py, store.py, app.py (§6)
    web/                   # M3: shared/, addin/, play/, host/   (static, served by the server)
  examples/demo/           # self-contained demo deck covering all question types
  tests/                   # test_latex, test_build, test_scripts, test_scoring, test_game, test_server,
                           # test_addin, test_publish, test_lecturers, test_preflight
  docs/                    # design.md, authoring.md, spike/ (S1 probe), pilot/
  tools/make_kg_pilot.py   # the KG pilot copy (five questions converted)
  tools/simulate.py        # a host and N simulated phones play a deck against a running server
  tools/slideshow.ps1      # drives a PowerPoint slideshow over COM (§5.5)
```

## 11. Milestones

| # | Result | Acceptance |
|---|---|---|
| S1 | PowerPoint spike | **done 2026-10-01**, see §9.1 (Presenter View: with M4) |
| M1a | `texquiz.sty` | **done 2026-10-01**: all eight question types, three modes, metadata/rectangles/phone images, `texstage pdf`; 27 tests incl. pixel-level leak checks; DBIS style fixture (copy) compiles in all modes, standalone frames too. See `docs/authoring.md` |
| M1b | builder | **done 2026-10-02**: `texstage build` and `scripts/texstage-build.py` (§4). Demo deck → 26 slides (24 live, 6 leaderboards) and bundle; PowerPoint 16 opens the file and reports the add-in objects as content apps. KG pilot chapters 01, 06, 16, 17 build from the lecture's `tools/`; the check catches the pilot's 06/032 overflow; rectangles of shrunk frames mapped (§3.3); all 728 KG handout pages pixel-identical before and after. 53 tests |
| M2 | Game server | **done 2026-10-02**: `texstage serve` (§6): state machine and scoring with unit tests (fake clock), WebSocket protocol, SQLite write-through and restart recovery (tests restart the engine and the server mid-round). `tools/simulate.py` plays a deck with simulated phones against a running server: 300 phones in one game on one machine - joined in 0.4 s, a reveal reaches all of them within 50 ms |
| M3 | Views in the browser slide host | **done 2026-10-02** (§7): phone page, host console with browser slide host, live views shared with the add-in; full games of the demo deck and a KG pilot chapter with a browser phone and simulated phones; real phones on a real network still to do (with M4) |
| M4 | PowerPoint end-to-end | **done 2026-10-02** (§5): the add-in page, `texstage addin install`, pairing, clicker-only games of the demo deck in real slideshows with simulated phones, incl. Presenter View (§5.5). Open: real phones on a network and the lecture PC (with M6); the presenter view's next-slide preview stays white |
| M5 | More question types | numeric/slider, text, open/word cloud, ordering - **done with M2 and M3**: the server judges and scores all eight types, the phone has an answer screen for each, the live views show their results (histogram, word cloud, places in an ordering) |
| M6 | Deployment | **done 2026-10-02** (§8): `texstage publish` and the server's upload, Docker image + Caddy (HTTPS) in `deploy/`, the server ready for a proxy and the internet (presenter key, client addresses, wrong PINs), laptop banner with the machine's addresses; load test 300 phones (slides within 75 ms) and 1000 phones (within 0.27 s). Open: building the image on a Linux Docker host, a real domain, real phones in a real lecture hall |

## 12. Reused from the prototype

Ideas, not code: hex-encoded export from expl3, separation of public deck data and private keys,
idempotent commands, the second-screen notes trick from the course's `beamer2pptx.py`. New:
WebSockets instead of polling, the full-slide add-in overlays, phone images instead of KaTeX,
clicker-driven phases, Kahoot scoring.
