# texstage - one core, many kinds of live content (design)

Status: 2026-10-10, a design - nothing of it is built yet. Decided the same day: the name
texstage; cells come from the exercise notebooks, named by tag, SPARQL first; videos local and
online (not from Opencast); phones never run code; laptop and central server alike, and a lecture
hall's PC as an option, signed in with the phone or a password, the university's single sign-on
later (section 9). It extends [design.md](design.md) (the build, the server, PowerPoint) and
[texstage-design.md](texstage-design.md) (the browser presenter), and refers to the current code
by file and line where it builds on it.

## 1. Idea in one paragraph

Today the whole chain - the LaTeX package, the build, the bundle, the server, PowerPoint's add-in,
the browser presenter - carries one kind of live content: the quiz. Most of the chain does not
depend on it: the present compile records boxes on pages, the build turns pages into pictures and
puts one add-in object over each live slide, the bundle is content-addressed files plus
`deck.json`, the server keeps a session per game and relays state to every window, texstage draws
a live layer over the PDF. This design splits that **core** from the quiz and makes the quiz the
first of several **content types** - a video, a notebook cell, later others - each a vertical
slice through every layer: a LaTeX package, its step in the build, what PowerPoint gets, what the
server does, and how each window shows it. The whole system is called **texstage**; texquiz stays
the name of the quiz.

## 2. The name

**texstage** for the whole system (decided 2026-10-10): TeX presentations, given live, with
content that happens on the stage. The reasons:

- *tex* + *stage*: a stage is where a talk is given, and where things happen live - the quiz, a
  video, code run in front of the room.
- It already names what the lecturer works with, the presenter and projector windows; the name
  moves from that part to the whole, and those windows become texstage's *stage*.
- It gives a family: texstage is the stage, and the content types are what plays on it -
  **texquiz** (the quiz, as today), **texvideo**, **texcell** (provisional names). Two names
  stay; none is added.
- Free on PyPI and on CTAN (checked 2026-10-10), and no other project of that name turned up.

Considered and dropped: *beamerlive* (says "live" outright, and Beamer is TeX's presentation
class - but it would be a third name next to texstage and texquiz); *livetex* (too close to TeX
Live); *texshow* (too close to TeXShop).

| | today | after the rename |
|---|---|---|
| the system, its Python package, the PyPI name | texquiz | **texstage** |
| the command | `texquiz` (`texstage` = `texquiz present`) | `texstage` (`texstage deck.tex` still presents); `texquiz` stays as a second name |
| the LaTeX core | inside `texquiz.sty` | `texstage.sty` |
| the quiz | `texquiz.sty`, the `quiz` environment | unchanged - it loads the core |
| further types | - | `texvideo.sty`, `texcell.sty`, ... |
| the browser presenter | texstage | texstage's presenter and projector windows; `/stage` unchanged |
| PowerPoint's add-in | "texquiz live (localhost:8470)" | "texstage (localhost:8470)" - **the same add-in ID** |
| the data folder | `~/.texquiz` | `~/.texstage`; `~/.texquiz` used while it exists and `~/.texstage` does not |
| the server's `/api/status` | `"server": "texquiz"` | `"texstage"`; the clients accept both |
| the lecture scripts | `texquiz-build.py`, `-serve`, `-present`, `-publish`, `-check` | `texstage-*.py`; the old names stay as one-line wrappers |

What must not change, so that everything built so far keeps working:

- **The add-in ID.** A live PPTX names its add-in by ID, `uuid5(ADDIN_NAMESPACE, origin)`
  (`build/powerpoint.py:38, 57-59`); the namespace constant stays, only the manifest's display
  and provider names change (`addin.py:44-47`; `texstage addin install` once per PC updates
  them). `addin.py:31` finds the manifests it wrote by name: it keeps finding the old ones.
- **`texquiz.sty` and everything a deck writes:** the `quiz` environment, its keys, the frame
  options, the theme hooks. The DBIS style loads it as before.
- **Bundles of format 1** stay readable (section 5.3).
- **Port 8470** and the presenter keys in the data folder.

1,178 places in 90 files name texquiz today (outside the vendored libraries), most of them in
`src/texquiz` (297), `latex/texquiz.sty` (188 - most of them stay: it remains the quiz's
package) and the documentation. The rename is mechanical; it is its own step (section 10, N1),
before anything is restructured.

## 3. What a content type is

A content type is everything one kind of live content needs, in every layer:

| layer | quiz (today) | video | notebook cell (SPARQL first) |
|---|---|---|---|
| LaTeX: handout PDF | a placeholder page | the poster frame, a play mark, the link | the query and its prepared result |
| LaTeX: present compile | reading, question, reveal and leaderboard pages; boxes; phone pictures | the poster in its box | the query; query box and result box |
| build | quizzes, answer keys (kept apart), phone pictures, layout check | a local file into the bundle | takes the cell from its notebook, runs it (rdflib), the result and the graphs into the bundle |
| PowerPoint | the add-in, live | a native video (python-pptx `add_movie`), live and static deck; an online one as a link | the prepared result, in the slide picture |
| server | the game: PIN, players, scores, keys | serves a local file (with byte ranges), relays play/pause/seek | keeps and relays results - **runs nothing** |
| texstage | the live overlays (`live.js`) | a `<video>` or the online player in the box; the projector follows | an editor; Run in the presenter's browser; the result in both windows |
| phones | answer | - | - (never) |

The types differ in kind, not only in content: the quiz is the only one with an audience,
secrets and scores; the video needs no server logic at all; the cell needs something that runs
queries - the build, and live the presenter's browser, never the server. So the core stays small,
and the quiz game is a module on top of it, not the model everything goes through.

Principles:

1. **Bundles are data, never code, and the server runs nothing.** A type's code lives in
   texstage itself; a deck only says which types it uses. A cell runs on the lecturer's machine
   when it is built and in the presenter's browser when it is run live (section 8) - so the same
   server works on the laptop and centrally (section 9).
2. **All types live in this package.** A registry of the types, no third-party plugins.
3. **PowerPoint gets each type's native or static form.** The add-in stays the quiz's: it
   flickers on every live slide (hence the first slide), needs Office.js from the internet, and an
   add-in that takes the keyboard focus takes the clicker's keys with it. New types are designed
   for texstage first.
4. **Every mode stays meaningful.** The handout and the static deck show each type's static form
   (a poster, a prepared output), as the quiz's handout shows its placeholder.
5. **The second type finds the seams, the third checks them.** No plugin interface designed in
   advance for "maybe others": the core is cut out of the working quiz where the video (section 7)
   needs it, and the cell (section 8) checks the cut.

## 4. The core in LaTeX

Line numbers without a file name refer to `latex/texquiz.sty` (1,745 lines).

### 4.1 texquiz.sty today

| section | lines | core or quiz |
|---|---|---|
| messages | 25-43 | mixed: the mode's and the general messages go to the core |
| mode | 45-69 | core |
| state, quiz keys | 71-115, 241-314 | quiz |
| setup | 117-239 | mixed: the LaTeX2e bridge (`\texquiz@ifhandout`, `\texquiz@pagerecord`, 180-183) goes to the core |
| body commands, validation | 316-390, 392-640 | quiz (the dry pass over `\choice`, `\explain`; types, checks, the shuffle) |
| export (present) | 642-839 | core: 643-785 - the output stream, hex encoding, `\pdfsavepos`, the writers of G, R, V, K, Z and D, the log marks, the stage notes; quiz: `\__tq_export:` (787-839) |
| phone assets | 841-934 | mixed: storing and shipping extra pages (848-865, 884-934) go to the core |
| layout | 936-1341 | quiz, but for helpers (939, 944-951, 1184-1211) |
| frames | 1343-1534 | mixed: the check outside frames (1344-1348), the live frame and its `note=` keys (1465-1488), the choice of the slide in present mode (1437-1458) go to the core |
| drawing | 1536-1583 | mixed: `\texquiz@vfill` and the `\texquiznotes` switch (1537-1555) go to the core |
| theme hooks | 1585-1675 | quiz |
| quiz and answer frames | 1677-1745 | mixed: the swap of `\beamer@doseveralframes` (1719-1743) becomes the core's frame options |

About a fifth of it, some 380 lines, is the core. The modes, as a second package has to know
them:

- **The mode** is set before `\documentclass` (`\def\texquizmode{present}`, the build does it,
  `build/latex.py:57-60`); without it, solutions if Beamer shows notes, else handout (55-63);
  present is always explicit; XeTeX is refused in it (66-69). Today the mode is private
  (`\g__tq_mode_str`); only "is it the handout?" is exposed (180), and it is final only at
  `\begin{document}`.
- **`\texquiznotes`**: empty, the present compile's notes on a second screen, for extracting
  their text; `stage`, the stage compile's own note pages (742-746, 754-766), which ships no extra
  pages (782).
- **No package ships pages of its own:** the build requires the PDF's pages, minus the extra
  pages its records announce, to equal the pages marked in the log (`build/builder.py:195-203`).

### 4.2 What blocks a second type

- **The `.tqz` reader** takes one page record (G) per page - a second overwrites it
  (`build/tqz.py:157`); rectangles (R, V) on a page without one fail (160, 175), and their id is
  ignored, so two boxes on a page collide (160).
- **The build** makes every page with a G record a live slide (`build/builder.py:130-137, 228`)
  and gives the kinds quiz, answer, join, leaderboard their meaning (110-127, 141, 213, 224-226);
  `build/stage.py:96-99` compares them between the two compiles.
- **Extra pages** (X) name a quiz and are grouped by quizzes (930; `build/bundle.py:190`).
- **Frame options don't compose:** `[quiz]` and `[answer]` swap `\beamer@doseveralframes` by
  `\let` against one original saved at load (1699, 1710-1716, 1727).
- **The quiz owns its frame's slides:** it sets their number (1437-1439) and tests for the first
  slide itself (1373, 1440); a box in an author's overlay frame needs a first-slide test of its
  own. Frame numbers must agree between the modes (1349-1350).
- **Ids and messages are a quiz's:** the registry and the id pattern (101, 1370-1378), "Quiz
  '<id>'" in every error (28).
- **Nothing flows back from the build into LaTeX** - texquiz only writes. A cell needs its
  outputs in every mode, also in a plain compile of the handout, so they are kept beside the deck
  (section 8).

### 4.3 texstage.sty

The core, in expl3 with LaTeX2e names `\texstage@...` beside it; the quiz and every other type
build on these:

```latex
\texstage_if_mode:nTF {handout|solutions|present}   \texstage_if_stage:TF
\texstage_record:n {fields}                    % a record line, at once
\texstage_page_record:n {fields}               % ... with |page, at shipout
\texstage_object:nnn {type}{id}{phase}         % item <id> of <type> is on this page; several per page
\texstage_rect:nnnnn {id}{phase}{key}{wd}{ht}  \texstage_area:nnn {id}{phase}{key}
\texstage_box:nnnnn {type}{id}{key}{wd}{content}  % a box with its object and its rectangle
\texstage_once:n {code}                        % on the frame's first slide only
\texstage_asset:nnnn {id}{key}{wd}{content}    % an extra page (X), never in the stage compile
\texstage_frame_option:nn {key}{wrapper}       % frame options that compose
\texstage_placeholder:nnn {title}{heading}{text}
\texstage_result:nnTF {id}{key}                % a prepared output (texcell), if there is one
```

- **Records:** the page record's kind names the type (the quiz's kinds - quiz, answer, join,
  leaderboard, podium - stay and mean type quiz); a type's own records start with its name
  (section 5.2). The reader keys rectangles by page, id and key, and a page without an object
  carries none.
- **Loading:** the DBIS decks load the lecture's `dbis-style`, which loads
  `lecture-tools/latex/dbis-slides` by path (e.g. `keynote/dbis-style.sty:15`); its last step loads
  `texquiz-theme-dbis` (`dbis-slides.sty:851-858`), which loads texquiz from its own folder by
  path (`texquiz-theme-dbis.sty:14-20`). Other decks say `\usepackage{texquiz}` after Beamer and
  find it through the build's TEXINPUTS (`build/latex.py:62`). No deck passes options;
  configuration is `\texquizmode`, `\texquiznotes`, `\quizsetup`. texquiz hooks into Beamer as it
  loads (702, 1692, 1727), so the core too loads after the document class.
- **Old decks compile unchanged:** `texquiz.sty` keeps its name, its commands, `\texquiz@shape`
  and its colours (which the theme uses, `texquiz-theme-dbis.sty:25-60`), `\texquizmode` and
  `\texquiznotes` (as names of the core's), the `texquiz-check:` log marks (`build/check.py:26`)
  and `\jobname.tqz`. It loads the core from its own folder (`\CurrentFilePath`, as the theme
  does), else by name - a plain lecture compile has no TEXINPUTS (`dbis-slides.sty:852-853`). A
  package loaded once by path and once by name is read once (tried 2026-10-10), so `texvideo` and
  `texcell` can simply `\RequirePackage{texstage}`.

## 5. The core in the build

References in this section: B = `build/builder.py`, BU = `build/bundle.py`, PP =
`build/powerpoint.py`, SB = `server/bundles.py`, APP = `server/app.py` (all under `src/texstage/`,
`src/texquiz/` until the rename).

### 5.1 The pipeline today

| step | where | core or quiz |
|---|---|---|
| server origin, deck name and ID | B:183-189 | core |
| the present compile, and beside it the stage compile | B:191, 307-316 | core |
| the solutions compile, inside the check | B:327-330 | quiz |
| reading the `.tqz`: records D G R V K Z X / Q P C S L A E N O | `tqz.py`; an unknown letter fails, tqz.py:171-172 | core / quiz |
| pages: the PDF's pages minus the phone pages must match the log | B:193-203 | mixed: every page after the slides is taken for a phone picture (B:195) |
| the stage plan: slides paired with note pages | B:204-209, `stage.py:88-109` | core |
| slide pictures and note text | B:210, `raster.py:30-47`, `notes.py` | core |
| phone pictures | B:211, `raster.py:50-67`, BU:182-191 | mixed: rendering is core, the entries are a quiz's |
| slides from the page records; leaderboard slides after a scored quiz | B:108-142 | mixed: a slide knows only `phase`, `quiz`, `rects` (B:59-66) |
| the live PPTX: pictures swapped on reveal and leaderboard slides | B:224-226 | quiz |
| the first slide that prepares the live slides | B:228 | mixed: any phase makes one |
| `deck.json`, `keys.json` | B:230-248 | mixed: only `quizzes` |
| bundle ID, folder, zip | B:249-256, BU:127-160 | core |
| the add-in objects | B:262-286, PP:101-150 | mixed: the object is core, its properties name a quiz |
| the static PPTX, saving both | B:290-298 | core |
| the checks: the notes' cut-off / the quiz and answer frames | B:331-337 / `check.py:113-116` | core / quiz |
| delivery: `builds.json`, the upload | `cli.py:92-116` | core |

Hard-wired besides: `bundle.py` imports the quiz's `Question` (BU:31); the server accepts only the
bundle's known file names and serves only PNG (SB:23-24, 97-100; APP:129-130, 989;
`publish.py:51-56`); nothing runs before the compiles (B:191).

### 5.2 What a type gives the build

The core keeps a registry of the types and calls each one at these points:

1. **Records.** The core reads its own records (D G R V K Z X); every other line starts with a
   type's name (`video|...`) and goes to that type, which returns its *items* - a quiz, a video,
   a cell. The quiz keeps its single letters.
2. **Before the compiles** (`prepare`): a type may run something whose results the compiles
   need - the cell: a quick compile that writes which notebook cells the deck shows, then their
   runs, the results written beside the deck (section 8).
3. **The slides** (`plan`): a type may add or mark slides - the quiz's leaderboard slides, its
   swapped pictures.
4. **The slide entry:** the core writes each slide's `id`, `image` and stage fields, and a list
   `live` of the slide's boxes, each `{type, item, phase?, rects?}` from the type.
5. **Public and private parts** of each item: `deck.json` gets `items[type][id]`, `keys.json`
   the private part, as the quiz's answer keys are kept apart today (BU:88-123).
6. **Files**, content-addressed (`<folder>/<sha256[:16]>.<ext>`, BU:37-38): the quiz's phone
   pictures, the video's file and poster, a cell's output pictures. The server's list of folders,
   suffixes and media types comes from the registry instead of SB:23-24 and APP:129-130.
7. **PowerPoint:** per live box an add-in object (the quiz), a native object (the video,
   `add_movie`) or nothing (the cell: its output is in the picture). Only types that use the
   add-in make the first slide (B:228): a deck with videos and no quiz needs no add-in at all, and
   its live and static PPTX are the same.
8. **Compiles and checks:** a type may ask for a compile of its own (the quiz: the solutions
   compile) and adds findings to the check (the quiz: its frames, `check.py`).

### 5.3 The bundle, format 2

```json
{"format": 2, "deck": "kg-06-sparql", "name": "06-SPARQL", "language": "en", "types": ["quiz", "video"],
 "image": {"width": 1920, "height": 1080},
 "slides": [{"id": 263, "image": "slides/3f0c....png", "frame": 7, "step": 1, "page": 9,
             "live": [{"type": "quiz", "item": "welche", "phase": "question", "rects": {}}]},
            {"id": 264, "image": "slides/a91e....png", "frame": 8, "step": 1, "page": 11,
             "live": [{"type": "video", "item": "plan", "rects": {"box": {}}}]}],
 "items": {"quiz": {"welche": {}}, "video": {"plan": {"media": "media/77d2....mp4",
                                                    "poster": "media/0b6c....jpg"}}},
 "pdf": {"file": "stage/feb9....pdf", "width": 453.5, "height": 255.1}}
```

- `types` names every type the deck uses. A server that lacks one refuses the deck when it finds
  it or when it is uploaded ("this deck needs video - update texstage"), instead of failing at the
  slide in the lecture.
- `language` (since 2026-10-24) is the deck's, a BCP 47 tag: babel's main language as the present
  compile records it (`\languagename` in the `D` record - `ngerman` gives `de`; build/bundle.py,
  `language_tag`). Everything the deck's audience and lecturer read speaks it, from the catalogs
  in `web/i18n/` (`i18n.js`: `texts`, `errorText`): the live views on the slides - the quiz's
  (`web/shared/live.js`) and the types' boxes, which `Stage` gives it (`web/stage/activity.js`) -,
  the phones (the server's views name it: `session.language`; the join slide's address and QR
  code too, `?lang=de`, so that the join form speaks it before the phone has joined), the
  presenter, projector and host windows and the add-in, the polls typed in the lecture
  (`server/polls.py`) and the slides' own texts (`latex/texstage.sty`, section "language"):
  German for a German deck, else English, also without the key (a deck built before). A page
  without a deck - the decks list, pairing a device, a phone's join form without `?lang=` -
  speaks the browser's language. The server's refusals carry a code (the WebSocket's `error`,
  the HTTP API's `code`), which the windows and phones say in their language.
- `keys.json` becomes `{"format": 2, "deck": ..., "items": {"quiz": {...}}}`.
- Format 1 stays readable: the server reads a format-1 slide's `phase`, `quiz`, `rects` as one
  `live` box of type quiz, and `quizzes` as `items.quiz` - every PPTX and bundle built so far
  keeps working.
- The bundle ID stays what it is, the hash of both files without `bundle` (BU:127-130), so
  format 2 changes every deck's ID once.
- The upload takes at most 200 MB (APP:126) - a limit videos will reach; section 7.

## 6. The core in the server and in the windows

References: APP = `server/app.py`, G = `server/game.py`, ST = `server/store.py`; the windows'
files are under `web/`.

### 6.1 Today

- **Roles:** `host` (the add-in, the host page), `stage` (the presenter window) and `display`
  (the projector window) share one `hello` (APP:629-656); `player` is a phone. A paired device is
  one of these roles with a device token instead of the key (APP:633-637).
- **Messages** (APP:571-627): the quiz's - `slide`, `prepare`, `skip`, `extend`, `pause`,
  `continue`, `reveal`, `again`, `finish`, a phone's `answer`; the audience's - `join`, `resume`,
  `kick`, `rename`, `restart`, `qa.*`; the stage's - `pointer`, `ink.*`, `screen`, `timer`,
  `zoom`, `board`, `go`, `lecture.new`, `lecture.continue`, `poll.*`, `sketch.*`.
- **State:** the `Engine` (G:179) keeps a `Session` per game (G:135-162: PIN, slide, the current
  round, polls, players, rounds, questions, and `stage`, free-form keys for the stage's state).
  `stage` is stored as JSON with the session (ST:24-39) and goes to every window with each push
  and on `hello` (APP:404-429, 656), through the whitelist `_stage_view` (G:818-826).
- **The quiz drives the game** from the slide's phase (`show_slide`, G:357-402): reading,
  question, reveal, leaderboard, podium, join.
- **The audience** - PIN, join and resume, players - is shared by the quiz, the ad-hoc polls
  (game-level quiz definitions, `polls.py:93-99`), the sketches (answers of type sketch) and Q&A.
  It belongs to the core, as do the presenter's own tools: ink, pointer, zoom, screen, timer,
  whiteboard pages, polls, Q&A, sketches, recording.
- **Hard-wired:** the dispatch is a chain per role, with prefix routing only for `ink.`
  (APP:720); the stage's keys are named in `_stage_view`, in `show_slide`'s clearing, `go_board`
  and `_create` (G:818-826, 363-366, 812-813, 734, 273-280); a slide knows `phase` and `quiz`
  (`bundles.py:52-57`); the bundle's file names are a fixed pattern (APP:129-130,
  `bundles.py:23-24, 97-100`); the archive writer names results, polls, questions and sketches
  (APP:853-869).
- **The windows:** `live.js` renders by a switch on the slide's overlay, then its phase
  (`live.js:112-126`), and replaces the whole layer whenever its HTML changes (86-91). texstage's
  layers (`stage/stage.css:93-107`), from the bottom: the PDF canvas, the live layer, ink,
  pointer, the quiz's controls, the pen input, the zoom box - all in slide fractions; the zoom
  transforms the live layer with the page (`stage/pdfview.js:264-267`).

### 6.2 What a type gives the server

1. **Messages in its own namespace** (`video.play`, `cell.run`) and the roles that may send each
   - as `PEN` does for the projector's pen (APP:135); the core routes by prefix, as it does for
   `ink.` today.
2. **State in the session**, under its name (`stage["video"]`), and its part of the window
   view, instead of the whitelist. Only small state: every push sends the whole view to every
   window (APP:415-420). Larger data - a cell's outputs - is fetched when needed, as `ink.load`
   and `sketch.get` are.
3. **Tables of its own** for what must survive a restart (the `TABLES` pattern, ST:24-59).
4. **What a slide change does** to its state: the quiz's rounds as in `show_slide`; a video
   stops; a cell keeps its output.
5. **Files it serves** from the bundle: folders and media types (section 5.2).
6. **Its part of the archive:** the quiz's results, the cell's queries as run with their results.

### 6.3 What a type gives the windows

- **A renderer per type** for the live layer, which owns its elements - mounted when its slide
  comes, updated with the state, removed when it goes. A `<video>` or an editor must not be
  rebuilt with every change of the state, as the layer's HTML swap would do. Built with the
  video (N3): a window gives its Stage `types` (`{video: VideoBox}`) and `host` (its role, how to
  send, the media files' addresses); a renderer is made per item on the slide shown and kept
  while the next slides show the same item (a frame's steps), with `place(rects)`,
  `update(state)`, `tick()`, `key(key)` and `destroy()` (`web/shared/live.js`, `showTypes`).
- **Interactive boxes** (a video's bar, an editor) lie above the pen input in the presenter
  window; elsewhere on the slide the pen writes as before. The stage's layers, bottom to top:
  the page, the live views and the types' boxes (`.tq-types`), the ink, the laser, the quiz's
  buttons, the pen's input, the types' buttons (`.tq-typectl`, which the pen leaves alone); the
  zoom moves all of them with the page. An editor (N5) will have to opt out of the stage's
  `user-select: none` and `touch-action: none` (`live.css:15`, `stage.css:95`); a video's bar
  does not need to.
- **A frozen projector** holds its picture with everything on it (`projector.js:116`): a video
  freezes with it.
- **The add-in stays the quiz's**; the other types give PowerPoint native objects or pictures
  (section 5.2).
- **State goes through the server:** the windows' BroadcastChannel carries only keys and "deck
  changed" (`presenter.js:79`, `projector.js:48-50`) and reaches no paired device.

Patterns to reuse: the timer's `{since, elapsed}` on the server's clock (G:746-769) for the
video's playhead; message ids and resending (`client.js:40-45, 76-94`; APP:592-619). The reply
cache, though, keeps 64 replies per role and session and caches every `ink.points` (APP:121,
594, 616): it cannot keep a cell's result from being stored twice after a resend - the result
carries a run ID of its own, which the server remembers. A message may have 16 KiB (APP:120,
1006): a larger result goes by HTTP, as the recording's parts do.

### 6.4 Security, as the code is today

Why the server must not run a deck's code - and so, in this design, runs none (section 8):

- **Roles are no security boundary.** A device token may say hello as any of the three host
  roles (APP:630-637), so a paired device has the presenter's whole power, and the projector
  window holds the full presenter key (`projector.js:41-46`).
- **Every live slide of a built PPTX carries the presenter key** (`build/builder.py:263-285`):
  whoever has the file has the key.
- The server listens on all interfaces, or on the loopback behind a tunnel (`cli.py:141`);
  `/api/presenter-key` answers only loopback requests without proxy headers (APP:915-925).
- **Uploads** must hash to their bundle ID and match the file-name pattern, at most 200 MiB
  (APP:336-351, 504-508, 962-968; `bundles.py:117-122`); the files' contents are not compared
  with their hash names. An upload belongs to the lecturer who sent it, a bundle from a folder on
  this machine to everyone (`bundles.py:159-180`) - and an upload with the same ID can take over
  a local bundle's path when its folder was rebuilt or is incomplete (`bundles.py:174-179`).

A server that ran cells would have to guard against all of this, and centrally also against the
other lecturers' decks. Results that come back from a presenter window are data: they are kept
and passed on as columns, rows and text, and shown as text - never as HTML.

## 7. The video (texvideo)

The smallest type with something to show: no runtime on the server, no audience. It decides
where the core is cut out of the quiz (N2) and is then built on it (N3, section 10).

```latex
\usepackage{texvideo}
...
\begin{frame}[t]{The query plan, animated}
  \video[poster=media/plan.jpg, width=0.8\textwidth, start=12, end=48]{media/plan.mp4}
\end{frame}
```

Keys: `poster=` (required at first: a picture of the video's size - the build extracts no
frames), `width=` / `height=` (as for `\includegraphics`), `start=` / `end=` (seconds), `loop`,
`muted`, `autoplay` (starts when its slide comes up; by default the presenter starts it), `url=`
(an online copy, for the handout), `id=` (default: from the file name). One id names one video:
it may be on some of a frame's slides only (`\only<2>`, `\pause`) and come again (`\againframe`,
or in another frame) - the same video, which goes on where it was; the id for another file,
poster or keys is an error, as the same video twice on one slide.

- **Every PDF** shows the poster in the box. The handout and the solutions add a play mark and
  the file name, or with `url=` a link and a QR code. The present compile records the box.
- **The build** puts the file into the bundle as `media/<sha256[:16]>.<ext>`, content-addressed
  like the pictures, and the box into `deck.json` (`type: "video"`, the box, the media file, the
  poster, the keys). PowerPoint gets a **native video** at the box, the poster as its poster frame,
  in the live and in the static deck (python-pptx 1.0.2 `SlideShapes.add_movie`); the slide
  picture keeps the poster. PowerPoint plays the whole file, started by a click: `start=`,
  `end=`, `loop` and `autoplay` are texstage's for now (python-pptx writes no trim and no
  timing; PowerPoint's own XML for them is a later step). A video never needs the add-in. A slide with a video and a quiz is
  refused: the quiz's add-in covers the whole slide (`build/powerpoint.py:4`).
  MP4 (H.264, AAC) plays in PowerPoint and in every browser; the build warns about other formats,
  and about large files - the bundle, its zip and both PPTX files grow by the video, and an
  upload to a hosted server takes 200 MB at most (section 5.3); on the laptop the server reads
  the build where it is.
- **The server** serves the file only to the lecturer's windows, not by its name alone as it
  serves slide pictures (`/bundle/...`, `server/app.py:984-989`): a `<video>` cannot send the key,
  so a window asks for a ticket - a random address, as the recording's download address is made
  (`server/app.py:880-884`, there valid for 10 minutes), here valid while the session lasts. A
  video may be material that is not for everyone. Starlette 1.7's `FileResponse` answers byte
  ranges, so seeking works. The session keeps one state per video, `{playing, time, at}`
  (media time `time` at server time `at`, as the timer keeps its time,
  `server/game.py:746-769`), set by a presenter window (`video.play`, `video.pause`,
  `video.seek`) and sent to the others with the stage's state - and to a window that connects,
  so a reloaded projector goes on at the right second. When the projector shows something else
  (`server/video.py`, `slide`): a playing video that the new slide does not show stops where it
  is - the next step of its frame shows it too and lets it play on -, and one that plays by
  itself (`autoplay`) starts from its start when a slide brings it; a whiteboard page, a poll or
  sketches stop them all.
- **texstage** (`web/stage/video.js`): the presenter window shows a `<video>` in the box, muted
  (the sound is the projector's), with a small bar: play/pause, position (drag it), time. Until
  it was played the box shows the slide's poster. A click in the box plays or pauses - the
  mouse's or a finger's; a pen writes there -, K too, J goes back 10 s (Keynote's and YouTube's
  keys; their L, forward, is texstage's laser: the bar goes there); Space and the arrows stay the
  slides'. Every window plays from `time + (now - at)` and corrects a drift of more than 0.3 s -
  the presenter's copies as well, so a laptop and a paired iPad stay in step; a hidden window
  follows by the video's own events. The projector window plays the sound: browsers allow sound
  after a click in the window, which the click that makes it full screen gives; if a browser
  refuses all the same, the video plays without sound with a note on it ("Click for sound")
  until a click or a key in that window, and the presenter window says so ("click into the
  projector window once"). A frozen projector holds the video's picture. Ink stays above the
  video; the zoom zooms it with the slide.
- **The recording** has the video's picture (it records the projector's screen), but not its
  sound: it takes the microphone alone (`stage/record.js:29-35`). Adding the screen's sound
  (`getDisplayMedia` with audio - Chrome offers it for a tab, on Windows for the whole screen) is
  a later step.
- **Online videos** (decided: local and online): the argument is a URL instead of a file -
  YouTube or Vimeo, or a direct link to an MP4, which plays in a `<video>` as a local file does.
  The handout shows the poster with a link and a QR code. PowerPoint gets the poster with a click
  that opens the video in the browser (python-pptx sets a picture's hyperlink; it cannot embed
  PowerPoint's own online video - inserted by hand, if wanted). Only the URL and the poster go
  into the bundle; the server takes no part in playing it. texstage puts the platform's player into
  the box; YouTube's IFrame Player API (in its privacy-enhanced mode, `youtube-nocookie.com`) and
  Vimeo's Player API play, pause and seek, so the projector follows the presenter as for a file,
  the presenter's copy muted. Ads and the player's own buttons are the platform's; the hall needs
  internet, and where the player cannot load, the poster stays.
  **The trial** (2026-10-10, a scratch page with two players of Blender's *Big Buck Bunny*
  following one state as `video.js` does; YouTube `aqz-KE-bpKQ`, Vimeo `1084537`): after a click
  in the page, both platforms keep two players in step. YouTube: playing within 0.13-0.22 s,
  then 0.10 and 0.18 s behind the state and 0.08 s apart, with no further jumps; a seek costs one
  jump per player; a pause lands within 0.035 s. Vimeo (chromeless with `controls: false`): from
  cold 0.6 s, then within 0.25 s of the state and 0.04 s of each other; a seek settles in 0.16 s;
  a pause within 0.03 s; its time comes by events, four a second, and is extrapolated between them.
  The projector's copy played with sound. **Without a click or a key in the window**, though,
  script-started playback is unreliable on both, muted too: YouTube reports "autoplay blocked"
  and each seek then takes about 0.7 s, so a follower that jumps every second never catches up;
  Vimeo pauses itself again and again. Hence: an online player is started only in a window that
  has had a click - otherwise its box says "Click for the video", and the presenter window is
  told, as for the sound -; it jumps at most every 2 s, aiming ahead by the delay its last jump
  took. YouTube's `seekTo` on a video not yet started starts it; its title, logo and "Watch on
  YouTube" stay over the picture until it plays - the box keeps the slide's poster until then.
  **As built** (`web/stage/video.js`): the build gives each online video its `player` in
  `deck.json` - `{youtube: id}`, `{vimeo: id, hash}` or `{file: address}` - from its address as
  it is shared (`watch?v=`, `youtu.be/`, `embed/`, `shorts/`; `vimeo.com/<id>[/<hash>]`,
  `player.vimeo.com/video/<id>?h=`; an address ending in `.mp4`, `.m4v`, `.webm` or `.mov`); any
  other address keeps its poster, with a warning. The windows have one interface over the three
  players. An online player starts only after a *click* in its window - in the end-to-end check a
  key press was not enough for YouTube -, is placed only once it has played (YouTube's seek would
  try to play it), and needs no click where the browser lets it play all the same. YouTube decides
  for itself whether a click in the page lets it play, and not the same way every time: while it
  waits, the click goes into its own frame, which starts it. The platform's
  script loads when a slide first brings one of its videos; leaving the slide removes the player.
  Checked with a scratch server: YouTube - presenter 0.07 s ahead of the state, projector 0.17 s
  behind, a pause and J landing on the same frame in both; Vimeo - after the click into the
  projector both within 0.09 s of the state and 0.02 s of each other.
- **Opencast is not a source** (decided 2026-10-10). The university's Opencast is reachable only
  through Moodle, so neither texstage nor the projector window can fetch its episodes; and its
  player, Paella 7, has no documented interface for another page to play, pause and seek it. The
  lecture recordings belong there anyway. A video that lives in Opencast goes on a slide as a
  local file, downloaded once - where its rights allow.

What it proves: boxes of a type that is not the quiz, through the records, `deck.json` and
PowerPoint (a native object instead of the add-in); files of a type in the bundle; a type's state
in the session, sent as the stage's own state is; a renderer per type in both windows. Not at
first: sound alone, poster frames extracted by the build.

## 8. The notebook cell (texcell)

Of the three things "notebook cells" can mean - results prepared by the build, cells run live in
texstage, students running code on their phones - the first two are planned (N4, N5); students
never run code (decided 2026-10-10). The first cells are SPARQL queries, taken from the exercise
notebooks (decided). Since 2026-10-17 only the first is planned: no live notebook cells -
texstage's live content is interactive content
([live-activities-design.md](live-activities-design.md)); N5 and the Python cells of N6 are
dropped.

### 8.1 The notebooks

The Knowledge Graphs lecture's SPARQL notebooks (`lecture-notebooks/english/05-RDF-SPARQL_translated.ipynb`,
in German `lecture-notebooks/german/05-RDF-SPARQL.ipynb`) run their queries with
*rwth-jupyter-rdfify* - MIT, the DBIS group's own, on PyPI (1.7 of 2026-09-20), built on rdflib,
SPARQLWrapper, owlrl and pySHACL. Its cells are declarative:

```text
%%rdf turtle -l uni --display none                    data: Turtle into the graph "uni"
%%rdf sparql -l uni                                   a query over that graph
%%rdf sparql -e https://query.wikidata.org/sparql     a query to an endpoint
```

`05-RDF-SPARQL` has 34 code cells; 32 are `%%rdf` cells - Turtle data and SPARQL queries,
three of them to Wikidata - and the first installs the packages and loads the extension. Every
cell has an id (nbformat 4.5), and the German and the English notebook share them. The cells
have no tags yet.

**Naming a cell: by tag** (proposed 2026-10-10). Adding, moving or deleting other cells is
harmless either way - an id belongs to its cell, not to a position. But an id is lost when the
cell itself is replaced: retyped, pasted (Jupyter gives a pasted cell a new id), or rewritten by a
tool that does not keep ids; and `2b164e11` says nothing on the slide. A tag is a name the
lecturer gives, in the cell's metadata (JupyterLab: *Cell Tags* in the property inspector); it
moves with the cell, survives copying, and reads well in the `.tex`. It is added once per cell a
slide shows - in both languages' notebooks, where both are used. An id still works for a first
try (`id:2b164e11`). A cell added before a query and loading into its graph changes the query's
result: the next build runs it again, as the notebook would.

### 8.2 On the slide

```latex
\usepackage{texcell}
\cellnotebook{../lecture-notebooks/english/05-RDF-SPARQL_translated.ipynb}
\begin{frame}[t]{Students and their names}
  \cell[output=below]{students-names}   % the cell's tag (or id:2b164e11)
\end{frame}
```

The build stops with a clear message when the tag is not in the notebook, or is there more than
once (a copied cell keeps its tag).

The slide shows the query - without its `%%rdf` line, typeset as SPARQL in the lecture's
listings style - and its result. Keys: `output=below|right|none`, or a box of its own placed with
`\celloutput{<id>}`; `rows=` (the rows shown, the rest counted: "and 12 more"); `comments=false`
(without the query's `#` comments, which the notebook writes for the students);
`error=expected`; and overlay specifications as for `\pause` (the result on the next click).

### 8.3 What runs, and where

- **Which cells:** texstage reads the `%%rdf` cells as rdfify does, first the kinds the slides
  need: `turtle -l <graph>` (data), `sparql -l <graph>` (SELECT, CONSTRUCT, ASK over a graph)
  and `sparql -e <endpoint>`. A query's graph is what the notebook's cells before it loaded into
  it, in the notebook's order - so a query needs no setup on the slide, and nothing else of the
  notebook runs (not its `pip install`). Other kinds - SHACL, OWL, graph pictures - as slides
  need them.
- **At build time (N4)**, on the lecturer's machine: a quick compile (`pdflatex -draftmode`, no
  PDF) writes which cells the deck shows; the build reads their notebooks (nbformat), takes each
  cell and runs it with rdflib, the engine rdfify runs on, over its graph - or sends it to its
  endpoint. The result - a table of bindings, a graph's triples, yes or no - is written to
  `build/cells/` in the deck's folder as LaTeX, which every compile includes: the build's own and
  a plain one such as `build-chapter.py`'s handout. That is PythonTeX's shape - LaTeX names the
  cell, a runner runs it, the next compile includes the result; where none is prepared yet, the
  PDF says so. The result goes into the bundle too, as data, with the graphs (Turtle,
  content-addressed). It is cached by the hash of the query, the graph's data and rdflib's
  version, so a rebuild without changes runs nothing and keeps its bundle ID. An endpoint's
  result carries its date and is fetched again only on request - Wikidata changes. An error
  fails the check unless the cell expects it. `texstage present` counts the notebook among the
  deck's sources (`cli.needs_build`).
- **PowerPoint** gets the prepared result in the slide picture.
- **Live (N5), in the presenter's browser** (dropped 2026-10-17 - no live notebook cells; the
  plan as it was): the query box becomes an editor in the presenter
  window, at its place and in the slide's look (CodeMirror 6, MIT, with SPARQL highlighting,
  vendored as PDF.js is), with Run (Shift+Enter). The query runs in that window: rdflib in
  Pyodide - CPython compiled to WebAssembly; rdflib is pure Python - over the bundle's graphs,
  with the same rdflib version as the build, so live and prepared results agree. An endpoint the
  browser asks itself: Wikidata's, the only one the KG notebooks ask, answers the pages of any
  site (`Access-Control-Allow-Origin: *`, checked 2026-10-10). Only an endpoint that does not
  would need the server to pass the query on - not built until a deck needs one (section 9.2).
  The presenter window sends the result to the server as data; the server keeps it
  with the session, sends it to the projector and a paired iPad, and puts the queries as run, with
  their results, into the archive. Pyodide loads in the background when the deck opens, from the
  texstage server itself - on the laptop also without internet.
- **Why the browser, not a kernel:** nothing runs on the server, so the same server works on the
  laptop and centrally (section 9); nothing has to be installed where the lecture is given, so a
  lecture hall's PC with a browser will do; and the browser's sandbox is the boundary - not the
  presenter key, which every live PPTX carries (section 6.4). The cost: Pyodide's first load, and
  only what Pyodide can run runs live - rdflib and pandas can; native packages such as pyoxigraph
  or morph-kgc, and Java (HermiT), cannot: such cells show their prepared results.
- **Python cells, later** (dropped with N5, 2026-10-17): ordinary Python cells (pandas,
  matplotlib) can follow the same way, in Pyodide. Should a cell that Pyodide cannot run ever be
  wanted live, it would run in a helper on the presenting machine that only the presenter window
  talks to - never in the server.
- **Licences:** rdflib and nbformat BSD-3-Clause, rdfify and CodeMirror MIT, Pyodide MPL-2.0 (a
  file-level licence: its files keep it, texstage stays Apache-2.0); an optional extra,
  `pip install texstage[cells]`.

## 9. On the laptop or on a central server

The same server software runs in both places today ([design.md](design.md), section 8:
`deploy/` with Docker and Caddy, lecturers with keys of their own, a deck built with
`--server https://...` uploaded at the end of its build). The central lecture server will be run
by the group's technician, from `deploy/`; its upload and storage limits stay as they are for now
(decided 2026-10-10). With the cells of section 8, nothing in this design needs the laptop:

| | laptop server | central server |
|---|---|---|
| building | on the laptop | on the laptop; the bundle is uploaded (`cli.deliver`), as today |
| PowerPoint's add-in | that of `localhost:8470` | the central server's, once per PC (`texstage addin install --url ...`) |
| quiz, phones | as today | as today; a deck belongs to the lecturer who uploaded it |
| texstage | `http://localhost:8470/stage` | `https://<server>/stage`; recordings and archives on the server |
| video, local file | read where it was built | uploaded with the bundle - at most 200 MB today (APP:126), and the proxy in front of the server must take it too; both windows stream it over the hall's network |
| video, online | the platform's player | the same; the server is not involved |
| cell, prepared | built on the laptop | the same, uploaded with the bundle |
| cell, live | in the presenter's browser | the same; only an endpoint that does not answer browsers needs the server to reach it |
| presenting from a lecture hall's PC | - | sign in there and present, nothing installed (section 9.1) |

What a central server needs beyond today's: room for videos - a larger upload limit, or the
videos online - and outgoing HTTPS only if decks ask endpoints through it. What it does not
need: a kernel, a sandbox, anything that runs a lecturer's code.

### 9.1 Presenting from a lecture hall's PC

Wanted as an option (2026-10-10): at the hall's PC, sign in to the central server and present -
no laptop, nothing installed. texstage needs only a browser there: the decks are on the server,
the presenter window and the projector window open on the PC's two screens, a pen display at the
lectern writes as the projector window's pen, the phones join the server, live cells run in the
browser (section 8), videos stream from the server or the platform. What is missing is a way to
**sign in on a shared PC**:

- **Today** the presenter window on a server other than the laptop's own asks for the presenter
  key and keeps it in `localStorage` (`stage/presenter.js:105, 142-145`): on a hall PC, the key
  would stay behind for whoever comes next - and a long random key is no fun to type.
- **Signing in with the phone** (the main way, decided 2026-10-10): the hall PC's presenter
  window shows a QR code and a short code; the lecturer scans it with the phone, which already
  holds a presenter sign-in (paired once from the laptop, as an iPad is today,
  `docs/texstage-design.md` section 5), compares the code and allows it. The PC gets a
  **session**, not the key: a token of the lecturer's that ends with the day, with *Sign out* in
  the presenter window, or when the phone ends it under *Devices* - nothing typed on the PC. It
  is today's pairing the other way round: there the signed-in window shows the code and the new
  device scans it.
- **With a password** (decided 2026-10-10), for days without the phone: the lecturer's name and
  a password (set by the technician, `texstage lecturer password NAME`, or by the lecturer in the
  presenter window; stored as a hash, attempts limited per address as the PIN's are,
  `server/app.py:138`) - the same kind of session. A password typed on a shared PC is open to
  whatever runs on it; the phone avoids that.
- **The university's sign-in** (single sign-on in front of the server) comes later (decided
  2026-10-10), set up by the technician - texstage maps the signed-in person to a lecturer, and
  it may make the password unnecessary.
- **The session** is kept in `sessionStorage`, so closing the browser ends it too; the projector
  window, opened by the presenter window, gets a copy of it. It may do what the presenter key may
  do in a lecture - present, record, upload a deck - but not manage lecturers or devices; today
  recording and uploading need the key (`stage/presenter.js:1412`; `server/app.py:933, 946`).
  *After the lecture* reminds that its downloads would stay on the PC: the archive is on the
  server, to be fetched later from one's own machine.
- **PowerPoint on a hall PC** stays possible - its add-in registered there for the central server
  - but every live PPTX carries the presenter key: a copy left on the PC leaves the key with it.
  texstage with a session leaves nothing behind.
- **The browser:** Edge or Chrome, for placing the projector window on the second screen
  (Window Management) and for recording.

### 9.2 Requests from the server to the outside

A live query to an endpoint goes from the presenter's browser straight to the endpoint. A
browser lets a page read the answer of another site only if that site allows it, with a header
(CORS). Wikidata does, so for the KG notebooks the server makes no outgoing request at all. An
endpoint that does not would leave one way: the texstage server fetches the answer for the
browser. On the laptop that is harmless. On a central server it is the technician's decision,
for three reasons:

- **The network:** servers in a data centre are often allowed to receive connections only;
  outgoing ones may be blocked, or have to go through a proxy.
- **Misuse:** a server that fetches addresses on request can be made to reach what only it can
  reach - internal systems of the university (server-side request forgery). texstage would pass
  on queries only to the endpoints a deck names, only for signed-in lecturers, with time and size
  limits - still a door the technician should know of.
- **Limits:** all queries would come from the server's address, and public endpoints limit the
  requests per address (Wikidata does).

So it is not built until a deck needs such an endpoint, and then with the technician.

## 10. Plan

Each step has its own test of done. The semester is running, so N1 and N2 are done on a branch;
the lectures stay on `main` until N2 has passed a dry run.

**N1 is done** (2026-10-10, branch `texstage-rename`): all 192 tests pass, none reaching a home
data folder; the demo deck and copies of the keynote and KG chapter 6 built before and after the
rename give the same bundle IDs (`42aa43d06e307d19`, `03ae0fa65100eef5`, `8b0603b6b83d1aa5` - the
ID covers every picture, the stage PDF and both JSON files); the add-in's ID is unchanged
(`dcbdd854-...` for `localhost:8470`), and so is the server's database, `texquiz.sqlite3`.
Kept as they were, besides the quiz's own names: the build folders (`build/texquiz/`,
`texquiz-out/`), the HTTP headers and the browsers' storage keys. The old command name
`texquiz` and the scripts `texquiz-*.py` went on 2026-10-11, after the merge into `main`: the
lectures' notes and READMEs and the keynote call texstage's.

**N2, so far** (2026-10-10): the LaTeX core, `texstage.sty` (section 4.3; texquiz.sty 1,745 ->
1,504 lines, the three decks' bundle IDs unchanged), and the build's content types with format 2
(section 5: `build/types.py`, `build/quiz.py`; the reader keeps several items per page; the three
decks: the same files, and deck.json and keys.json as before but for the format). The server
reads formats 1 and 2 and gives the windows the names of format 1 as well (`client_view`): the
presenter plays a format-2 deck's quiz as before. 195 tests pass. **The server's and the windows'
hooks** (sections 6.2 and 6.3: a type's messages and state, its files, a renderer per type) **are
built with the video (N3)**: no type but the video uses them yet, and a hook built without its
user is a guess (principle 5). Mind the order: a server must be updated before decks of format 2
reach it - one of before reads format 1 only.

**N3, so far** (2026-10-10): the local video - `texvideo.sty`, the build (`build/video.py`:
the files in `media/`, a native video in both PPTX files), the server (`server/video.py`,
`server/types.py`: the state, the messages, the files by ticket) and both windows
(`web/stage/video.js` on the renderers of `live.js`). Checked in the browser with a scratch
server: play, pause, K and J, the bar, a click into the video, the frame's steps, a slide
without it, autoplay with loop, freeze, zoom, the projector refusing the sound, a reload in the
middle, hidden windows; the projector within 0.05 s of the presenter. The online videos -
YouTube, Vimeo, an address of a file - after the trial (section 7), checked the same way. To do:
the dry run, with the user.

| step | what | done when |
|---|---|---|
| **N1** | the rename (section 2); no change in behaviour | all tests pass; the demo deck, KG ch. 6 and the keynote give the same PDFs, slide pictures and bundle IDs; a PPTX built before N1 plays with the server after it; the old script names and the `texquiz` command still work |
| **N2** | the core cut out of the quiz (sections 4 to 6), where the video needs it; no change in behaviour | all tests pass; the same PDFs and slide pictures; `deck.json` format 2 with `types` (the bundle IDs change once, by that alone); format 1 still read; a dry run in PowerPoint and in texstage as on 2026-10-09 |
| **N3** | texvideo: local files, YouTube and Vimeo (section 7) | a deck with a local and an online video: handout, both PPTX files, texstage with the projector in step, a reload in the middle; the local file only with a ticket |
| **N4** | texcell: SPARQL results prepared from the notebooks (section 8) | queries from `05-RDF-SPARQL` on slides: their results in the handout, both PPTX files and texstage; a rebuild without changes runs nothing |
| **N5** | texcell live: SPARQL in the presenter's browser - **dropped 2026-10-17** (no live notebook cells) | edit and Run in a dry run, on the laptop and on a central server (the `deploy/` image); live results equal the prepared ones; a reload keeps them |
| **N6** | Python cells in the browser (**dropped 2026-10-17**); further types, each checked against the table in section 3 - the next: live activities ([live-activities-design.md](live-activities-design.md)) | e.g. a web page in a box, an interactive chart, a timer |
| **H** | presenting from a hall PC: sign-in with the phone or a password, sessions (section 9.1) - independent of the types, any time after N1; the university's single sign-on later, with the technician | at a PC that never had texstage: sign in with the phone, and once with the password, present with the projector window on the second screen, record; after *Sign out* no key and no session are left on the PC |

Two trials come first, each a day's work at most: before N3's online part, YouTube's and Vimeo's
player APIs keeping two windows in step (done 2026-10-10: they do, after a click in the window -
section 7); before N5, Pyodide with rdflib in the presenter window - its load time over a lecture
hall's network, and `05-RDF-SPARQL`'s queries giving the same results as CPython's rdflib (not
needed since N5 was dropped, 2026-10-17).

The PyPI release, under the new name, after N2.

## 11. Open questions

- Only if a deck ever needs an endpoint that does not answer browsers: whether the central
  server may pass queries on to it - the technician's decision (section 9.2).
- The type names and their commands (`texvideo` with `\video`, `texcell` with `\cell`) are
  provisional.
- The documentation after N2: `design.md` describes the core, the quiz's parts move to
  `quiz-design.md`, `texstage-design.md` becomes the presenter's (`presenter-design.md`).
