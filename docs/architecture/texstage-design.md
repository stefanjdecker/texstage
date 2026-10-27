# texstage - design

Status: 2026-10-07, M1 to M7 implemented - where they differ from this design or leave something
for later, sections 16 to 22 say so; merged into `main` on 2026-10-08, after a day beside
texquiz 0.1 (section 23). Requirements: [texstage-requirements.md](texstage-requirements.md)
(the identifiers P1-P9, I1-I6, T1-T3, A1-A2, R1-R2, Q1-Q3 refer to it). The existing system is
described in [design.md](design.md); this document only states what texstage adds or changes, and
refers to the current code by file and line where it builds on it.

**Since 2026-10-10 texstage is the name of the whole system** - this presenter, the build, the
server - and texquiz the name of its quiz ([content-types-design.md](content-types-design.md),
section 2): the commands are `texstage ...`, the Python package `texstage`. This document keeps
its history as written.

## 1. Idea in one paragraph

texstage presents a texquiz deck in the browser with PDF.js, in two windows: a clean **projector
window** and a **presenter window**. The PDF is the present-mode deck compiled once more with the
deck's own note pages (`<stem>-stage.pdf`, section 3). texstage drives the existing texquiz game
exactly as the PowerPoint add-in does: `hello`, then `slide` with the deck's slide IDs. Ink, pointer, zoom, whiteboard pages, black/freeze, Q&A and sketches are
new *stage state* kept by the same server and pushed to every window and device. The quiz overlays
are the existing `live.js` views, drawn over the PDF instead of over a PNG. PowerPoint remains an
export of the same build.

## 2. Architecture

```
 deck.tex ─texstage build─────────┬─► present compile: PNGs, note text, .tqz, .nav ─┬─► PPTX (export)
                                 └─► stage compile: stage PDF with readable notes ─┴─► bundle
                                                                                         │
                                       texquiz/texstage server (one process) ◄───────────┘
                    ┌───────────────────────────┬──────────────┬───────────────────┐
              presenter window (laptop)   projector window   iPad (paired       phones (players)
              /stage/presenter            /stage/projector   presenter device)   /play  (+ Q&A, sketch)
              role "stage"                role "display"     role "stage"        role "player"
```

- **One server** (`texstage serve`, also on a hosted server): the game as today, plus a *stage
  session* per game: position, ink, pointer, zoom, black/freeze, timer, whiteboard pages, Q&A,
  sketches, ad-hoc polls. Everything persists in the existing SQLite store, so a reload or a
  restart loses nothing (as games do today).
- **Windows are thin:** they render state; the server is the single source of truth. Two windows
  on the same laptop additionally talk over a `BroadcastChannel` for the latency-critical ink and
  pointer (section 6.4).
- **No framework, no bundler** (as `src/texstage/web/`): plain ES modules; third-party code vendored
  under `web/vendor/` - PDF.js, perfect-freehand, KaTeX, pdf-lib - so presenting works offline.

## 3. The build: what texstage needs from a deck

Facts (survey of 2026-10-06, checked against the code): `deck.json` has slide IDs, images,
phases and live rects, but no PDF page, frame or overlay step (`build/builder.py:186-200`); the
builder knows each slide's page (`Slide.page`, `build/builder.py:58-59`); `.tqz` has page records
only for live pages (`G` records, `build/tqz.py:13`); the frame-to-page map exists only in
Beamer's `.nav` (`\beamer@framepages{first}{last}`), which texquiz reads only for the layout check
(`build/check.py:80-102`); the present PDF's pages are slide | notes, 2 × `\paperwidth` wide,
followed by the phone-asset pages (`build/raster.py:3-5, 38`).

**Decisions:**

1. **Frame map from `.nav`** (requirements §6.1). The builder already reads the present compile's
   `.nav` (`build/builder.py:275`); it writes the map into `deck.json`:
   - per slide: `page` and `note` (its page and its note page in the stage PDF, decision 2),
     `frame` (the frame's number, as on the footline) and `step` (1-based overlay step within the
     frame);
   - top level: `pdf: {file, width, height}` (the page size in PDF points); the frames follow
     from the slides' `frame` numbers;
   - all of it only in a build with the stage PDF (`--stage` until 2026-10-10, since then every
     build but one with `--no-stage`): builds without it keep their deck.json and bundle ID;
   - the synthetic leaderboard slides use their anchor's pages, as they already use its picture
     (`build/builder.py:131-134`), and get the anchor's `frame`/`step`;
   - `allowframebreaks` frames appear as overlapping entries, `{6}{6}` then `{6}{7}`
     (`scripts/framepages.py:11-13`): the builder makes every break page a frame of its own (an
     entry that overlaps the previous one starts after it).
2. **Readable notes need a second compile** (P4, "both"). The present compile's note page is
   typeset for text extraction only - `\tiny`, ragged right, no hyphenation, a wide `\parskip`
   (`latex/texquiz.sty:1521-1537`) - because the PPTX notes are read from it: a line end must be a
   space, and paragraphs are found by the gap (`build/notes.py:7-42`). The deck's own note page
   cannot take its place: DBIS's `dbisscript` is justified and hyphenated, with a 0.3em paragraph
   gap and the frame title on top (`latex/dbis-slides.sty:148-158`). So `texstage build`
   compiles the present deck a second time, in parallel (own job name), with a new value of the
   existing flag (`\def\texquiznotes{stage}`, `build/latex.py:46-47`): the deck's own note
   template (Beamer's default if it sets none), and the note pages *interleaved* (`show notes`)
   instead of on a second screen. The result is the **stage PDF**: every slide a page of the
   deck's size, followed by its note page if its frame has a note.
   - **Why separate note pages:** the annotated PDF for the students (section 11) copies slide
     pages. A second-screen page cropped to its slide half would still carry the note's text,
     hidden but found by search and copy-paste.
   - **Pairing:** an interleaved note page is numbered on like any page - Beamer steps the page
     counter back only for second-screen notes (`beamerbasenotes.sty`) - so texquiz.sty marks
     note pages itself: Beamer's `\AtBeginNote` code flags the page while it is typeset, and the
     log gets `texquiz-check: note` before its page mark. `build/stage.py` pairs the pages and
     checks them against the present compile (as many slide pages, the live pages on the same
     slides); a note template that does not show `\insertnote` is refused, not paired wrongly.
   - **Reproducible:** the stage PDF has no dates and no trailer ID, so a rebuild without
     changes gives the same file and bundle ID; it has no phone pages.
   - **Checks:** the slide pages must match the present compile's; the cut-off check
     (`note_reaches_bottom`) runs on the note pages - for DBIS decks the same check as
     `build-chapter.py --notes`.
   - **Text:** the extracted note text (present compile, as today) also goes into `deck.json` as
     `notes` per slide, for the reflowing view.
3. **The stage PDF goes into the bundle** as `stage/<sha256[:16]>.pdf`, content-addressed like the
   PNGs, but not into the bundle the PowerPoint file carries (`build/bundle.py` `carried`,
   146-151): PowerPoint never needs it, and it would make the PPTX much heavier. The new fields
   change the bundle ID - intended: a texstage deck is a new build.
4. **The stage PDF is served only to stage devices** (`GET /api/deck/{bundle}/pdf`, with the
   presenter key or a device token, like `/api/deck/{bundle}`). Today the reveal pictures are
   protected by their names: content hashes that only `deck.json` lists, and only hosts get it
   (`server/app.py:13-15`). The PDF holds every reveal page in one file, and PDF.js can send a
   header with its request, so its route checks the key instead of relying on a name.

## 4. Rendering with PDF.js

- **What is drawn:** the projector draws slide pages of the stage PDF; the presenter view draws the
  current and the next step and the current slide's note page. Every page has the deck's size, so
  the overlay rects (fractions of the slide) apply to it directly.
- **Resolution:** device pixels (`devicePixelRatio` × CSS size), re-rendered on resize; 4K
  projectors work.
- **Speed:** a page cache keyed by (page, size): the current page, the next two steps and the
  previous one are rendered ahead in the PDF.js worker; a frame change shows the cached bitmap at
  once. Heavy TikZ pages on the iPad: previews at reduced resolution, the current page at full.
- **The overlay sits on the slide box.** `live.js`'s `Stage` today creates its own `<img>`
  (`web/shared/live.js:29`), and its CSS has the 16:9 ratio hard-coded (`web/shared/live.css:8`).
  Two seams:
  - `Stage` takes a *slide surface* (an `<img>` as today, or the texstage canvas stack) instead of
    creating the image;
  - the ratio comes from `deck.pdf` (paper width / height) instead of `16/9`.
  The swap rule - an unrevealed quiz shows its `question` slide in place of a read/reveal/answer/
  leaderboard slide (`web/shared/live.js:51-54`) - becomes a function both use, so the projector
  draws the same PDF page the add-in would show.
- **Layers of the projector**, bottom to top: PDF canvas → ink canvas → quiz overlay (DOM, the
  existing views) → pointer canvas → black/freeze cover. Zoom is one CSS transform on the stack
  below the pointer, so ink, overlay and slide magnify together.

## 5. Windows, devices and roles

| Window / device | Route | Role | Can |
|---|---|---|---|
| Presenter window (laptop) | `/stage` | `stage` | navigate, ink, pointer, zoom, black/freeze, timer, Q&A, polls, export, record |
| Projector window (laptop) | `/stage/projector?bundle=…` | `display` | show - it is what a recording captures (section 9) |
| iPad / tablet | `/stage` after pairing | `stage` | the same as the presenter window |
| Host console, PowerPoint add-in | as today | `host` | unchanged |
| Phones | `/play` | `player` | answer, ask (Q&A), vote, sketch |

- **Authentication:** the laptop's windows use the presenter key as the host page does today
  (`/api/presenter-key`, loopback only; on a hosted server the key is typed once and kept in
  local storage, `web/host/host.js:27-52`). Other devices pair (T2): the presenter window shows a QR
  code with a one-time token (valid 2 minutes, one use); the device exchanges it for a *device
  token* (stored in its local storage, scoped to the lecturer, listed and revocable in the
  presenter view). Phones never receive stage roles.
- **WebSocket roles:** today `hello` is for hosts only, and every other connection is a player
  (`server/app.py:470, 486-487`). texstage adds `stage` and `display`; both join the lecturer's
  game for the deck with `hello{role, key|device, deck, bundle}`. All windows must use the **same bundle**: a `hello` with another build of the
  deck ends the running game (`server/game.py:203-220`) - the presenter window warns before it
  loads a different build.
- **Placing the projector window:** `texstage present` (or `texstage serve --present`) opens the
  presenter window once the server runs; its Projector button opens the projector window. On Chromium the Window
  Management API (`getScreenDetails`) moves it onto the second display (the browser asks once);
  elsewhere the lecturer drags it there. A click in it makes it full screen.

## 6. Stage state and messages

### 6.1 Position and navigation (P2, P6, P8)

- The **position** is `{kind: "slide", id}` (a deck slide), `{kind: "board", id}` (a whiteboard
  page) or `{kind: "poll", id}` (an ad-hoc poll's slide). Navigation goes step by step through the
  deck's slides in `deck.json` order; a frame's steps share one slide number.
- For deck slides the server forwards the ID to the game exactly as the add-in's `slide` message
  does (`server/game.py` `show_slide` 245-286), so read, question, reveal, leaderboard and podium
  behave as with PowerPoint. Boards and polls do not touch the game's slide.
- **Overview:** one tile per frame (its last step), whiteboard pages in place; click or type a
  number to jump to the frame's first step.
- **Keys** (PowerPoint's where they exist): → ↓ PageDown Space Enter next; ← ↑ PageUp Backspace
  previous; Home/End; number + Enter jump; B black; W white; F freeze; G overview; P pen; H
  highlighter; E eraser; L laser pointer; Z zoom; Ctrl+Z / Ctrl+Y undo/redo; N new whiteboard page.

### 6.2 Messages

New client → server messages (same envelope as today: `{t, id?}`, replies `ok`/`error`):

| Message | Fields | Effect |
|---|---|---|
| `go` | `to` (position), `step?` | set the position; deck slides also drive the game (M2, with whiteboard pages; M1 uses the host's `slide`) |
| `ink.begin` / `ink.points` / `ink.end` | `stroke, frame, tool, color, width`, `points: [[x,y,p,t]…]` | a stroke, streamed while it is drawn |
| `ink.erase` | `strokes: [id…]` | remove strokes (stroke eraser) |
| `ink.undo` / `ink.redo` / `ink.clear` | `frame` | per frame, per device |
| `pointer` | `x, y` or `off` | laser pointer; not stored |
| `zoom` | `rect` or `off` | region of the slide shown magnified |
| `screen` | `black` / `white` / `freeze` / `live` | projector cover |
| `board.add` | `after, kind: blank/grid` | insert a whiteboard page |
| `timer` | `start/pause/reset, target?` | presenter timer, stored so a reload keeps it |
| `poll.create` | text, type, answers | ad-hoc poll (section 10) |
| `qa.ask` / `qa.vote` (player) / `qa.show`, `qa.hide`, `qa.done` (stage) | | Q&A (section 10) |
| `sketch.show` | `round, player` | put a sketch answer on the projector |
| `pair.offer` / `pair.accept` | token | device pairing |

Server → client: one more part in the host view's state snapshot, `stage{position, screen, zoom,
pointer, timer, boards, devices, qa…}`; **ink is not part of the snapshot** - strokes go out as
events (`ink.*` relayed to the other stage and display connections) and are fetched per frame on
demand (`ink.load{frame}` → all strokes), because snapshots are sent whole and ink grows large.

- **Coordinates** are fractions of the slide box from the top-left, as the live rects already are
  (`build/bundle.py` `public_rects` 66-79): independent of window size and zoom.
- **Limits:** today a message may have 16 KiB (`MESSAGE_MAX`, `server/app.py:71`) and a WebSocket
  frame 64 KiB (`cli.py:120`). Ink points go in batches of at most one animation frame (quantised
  to 1/10,000 of the slide, pressure to 1/256), far below the limit.

### 6.3 Persistence

New tables in `texquiz.sqlite3` (`server/store.py`), all keyed by the game session (so ink
"starts fresh" with a new build or a new game - requirements §2):

- `stage(session, position, screen, timer, zoom, updated)`
- `boards(session, id, after_slide, kind, created)`
- `strokes(session, id, frame, device, tool, color, width, points, created, erased)` - `frame` is
  the frame number or `board:<id>`
- `devices(id, owner, name, token_hash, paired, revoked)`
- `questions(session, id, player, text, votes, state, created)` and `votes(question, player)`
- sketch answers use the existing `answers.payload` (section 10)

### 6.4 Ink transport (requirements §6.3)

- **Decision: through the server, plus a local fast path.** A stroke is drawn locally at once,
  sent to the server in per-frame batches, and the server relays it to every other `stage` and
  `display` connection of the game and stores it. Two windows in one browser (presenter and
  projector on the laptop) also exchange the batches over `BroadcastChannel("texstage:<session>")`,
  so the projector shows ink within one frame, independent of the network.
- From the **iPad**, the path is iPad → laptop server → projector window, all in the room network:
  one hop each way, well under the 50 ms target. Through the Cloudflare tunnel (when the iPad is not
  in the room network) it works with tunnel latency (typically 50-150 ms) - documented as best
  effort; a direct WebRTC data channel is not worth its complexity for this case.

## 7. Ink and pointer (I1-I6)

- **Input:** Pointer Events on the slide box (`touch-action: none`): `pointerType` pen/mouse/touch,
  `pressure`, `tiltX/tiltY`, the eraser end (`buttons & 32`); all samples via
  `getCoalescedEvents()` and `pointerrawupdate` where the browser has them. Palm rejection: while
  a pen is down or hovering, touch is ignored; on the iPad, fingers scroll and pinch, the Pencil
  draws.
  Wacom on Windows needs *Use Windows Ink* (setup notes).
- **Strokes:** perfect-freehand turns the points into a pressure-sensitive outline, filled as a
  `Path2D`; highlighter: constant width, 35 % opacity, below the pen strokes; colours and widths
  from a small palette in the presenter view.
- **Latency:** local drawing on the ink canvas in the same frame; on Chromium additionally a
  low-latency canvas context (`desynchronized: true`) and the delegated ink trail
  (`navigator.ink`) - enhancements, not requirements (Safari has neither).
- **Frames and steps (I2):** strokes belong to the frame, so they stay when the next overlay step
  appears; the projector draws the frame's strokes over whichever step is shown.
- **Eraser:** stroke eraser (a stroke touched by the eraser disappears); undo/redo per device.
- **Laser pointer (I4):** `pointer` messages at most every animation frame; the projector draws a
  red dot (until 2026-10-10 with a 300 ms fading trail, section 24); not stored.
- **Zoom (I5):** the presenter drags a rectangle (or zooms with the wheel/pinch); the projector
  animates its stack to that rectangle; ink drawn while zoomed is stored in slide coordinates.
- **Whiteboard pages (I6):** blank or grid pages of the deck's size, inserted after the current
  frame; they take part in navigation, overview and export.

## 8. Presenter window (P3-P7)

Layout (laptop, landscape): current step (large, with the ink tools), next step (smaller), notes
(the slide's note page, or the reflowing text view), timer and clock, a strip of
controls (screen, pointer, zoom, board, overview), and panels that appear when there is something
to show: the quiz state (players, answers, results - the host console's panel), Q&A, sketch
gallery. On the iPad the same page in a touch layout: current step full width, notes and next
step in a drawer. **Black/freeze** (P7): `screen` messages; *freeze* keeps the projector's last
picture while the presenter keeps navigating; *live* jumps the projector to the current position.

## 9. Recording and hybrid lectures (R1-R2; requirements §6.2)

- **R1** needs no code: the projector window has no UI, so the hall's capture system records the
  projector signal and Zoom/Teams can share that one window.
- **R2 - decision: capture the projector output, not a composed canvas.** The presenter window
  starts the recording: `getDisplayMedia` opens the browser's picker on the laptop screen (started
  in the projector window, its prompt would appear in front of the audience), and the lecturer
  picks the projector's screen or the projector window - one confirmation per recording, in every
  browser of the platform list (macOS asks once to allow screen recording for the browser). The
  microphone comes from `getUserMedia`; `MediaRecorder` records both (WebM with VP9/Opus; MP4
  where the browser records it, e.g. Safari). Recording what the hall sees puts the quiz
  overlays, ink and pointer into the video without drawing them twice; composing everything in
  one canvas would duplicate the overlay views (`live.js`, some 300 lines, and its CSS) for no
  gain.
- **Robustness:** the recorder uploads a chunk every 10 s (`MediaRecorder.start(10000)`,
  `POST /api/stage/{session}/recording`); after a crash the file holds everything up to the last
  chunk. Start, pause and stop from the presenter view; a red dot in the presenter view (never on
  the projector) while it runs. MediaRecorder's WebM files have no duration and no seek index: the
  archive step remuxes them (`ffmpeg -c copy`) when ffmpeg is installed; without it they play,
  but seek poorly.

## 10. New interaction (Q1-Q3)

- **Content without LaTeX** is text with inline math (`$...$`), rendered with KaTeX (vendored) on
  phones, projector and presenter view. `play.js` today shows prompts and answers as images from
  the build; it gets a text path next to the image path.
- **Ad-hoc polls (Q1):** `poll.create` adds a quiz definition to the *session* (not to the bundle):
  yes/no, A-D, a 1-5 scale, a word cloud or free text. The game treats it like a bundle quiz - the
  same round life cycle, the same result views - and the results table (`server/game.py`
  `results_table`) includes it. The projector shows it on a generated poll slide.
- **Q&A (Q2):** a second tab on the phone: ask (max. 280 characters, rate-limited), upvote.
  Questions appear only in the presenter view, sorted by votes; `qa.show` puts one on the projector
  (a card over the slide), `qa.done` archives it. On the projector questions are anonymous; the
  server keeps the player ID only for moderation (delete, block).
- **Sketch answers (Q3):** a quiz type `sketch` - prepared in LaTeX (`\begin{quiz}[type=sketch]`)
  or ad hoc. Phones draw with the same stroke code (finger or stylus, no pressure needed); the
  answer is a stroke list, simplified (Ramer-Douglas-Peucker) and quantised to stay under the
  message limit. The presenter view shows a gallery; `sketch.show` puts selected sketches on the
  projector; sketches go into the lecture archive as SVG.

## 11. After the lecture (A1-A2; requirements §6.3)

- **Decision: the annotated PDF is assembled in the presenter window with pdf-lib** (MIT), so it
  works the same on the laptop and on a hosted server and needs no PDF library on the server:
  for every frame the slide page of its last step, copied from the stage PDF (the note pages are
  separate pages and stay behind, section 3), with the frame's strokes as filled vector paths
  (perfect-freehand outlines; the highlighter with opacity), and the whiteboard pages at their
  places; virtual leaderboard slides are left out.
- **Lecture archive (A2):** the presenter window uploads the PDF to the server, which keeps per game
  `<data>/archive/<deck>/<date>-<pin>/` with the annotated PDF, the results CSV (today's export),
  the Q&A list, the sketches as SVG and the recording; the presenter view offers it as one ZIP.

## 12. Dependencies and the Apache-2.0 release

| Component | Licence | Use |
|---|---|---|
| PDF.js (`pdfjs-dist`, prebuilt ES modules) | Apache-2.0 | rendering |
| perfect-freehand | MIT | ink strokes |
| pdf-lib | MIT | annotated PDF |
| KaTeX | MIT | math in non-LaTeX content |
| Starlette, uvicorn, segno, lxml; Pillow; python-pptx | BSD; HPND; MIT | server, PPTX export (as today) |
| **PyMuPDF** | **AGPL-3.0 or commercial** | build: `builder.py`, `raster.py`, `notes.py`; scripts `beamer2pptx.py`, `build-chapter.py`, `render-pages.py`; `tools/deck_baseline.py`; two test modules |

PyMuPDF is the only conflict (replaced in M7: section 22). Replacement with **pypdfium2** (Apache-2.0/BSD): rendering maps to
its `render(scale, crop, fill_color)`; `notes.py` needs its word grouping rebuilt from pdfium's
character boxes (pdfium has no "words" call). A quick first step independent of the release:
PyMuPDF is a required dependency (`pyproject.toml:11`) and `cli.py:8` imports the builder at
module level, so `texstage serve` and the server's Docker image (`deploy/Dockerfile`) install and
load PyMuPDF although the server never uses it - make that import lazy and move PyMuPDF to a
`build` extra.

## 13. Testing

- **Server:** pytest with Starlette's `TestClient` on synthetic bundles (`tests/fake_bundle.py`),
  as `tests/test_server.py`: roles and pairing, navigation driving the game, ink persistence and
  relay, Q&A, ad-hoc polls, sketch answers, restart recovery.
- **Build:** `deck.json`'s `page`/`note`/`frame`/`step`/`frames`/`pdf`/`notes`, and the stage
  compile (slide and note pages paired, the same slides as the present compile, the deck's note
  template kept, not in the carried bundle), on the demo deck (`tests/conftest.py` `demo_build`).
- **Browser:** Playwright with the installed Edge, two windows: navigation in sync; the overlay
  rects line up with the PDF.js rendering (pixel checks against the build's PNGs); pen input
  simulated through the DevTools protocol (`Input.dispatchMouseEvent` with `pointerType: "pen"`,
  `force` for the pressure, `tiltX`/`tiltY`); ink appears in the projector window; the annotated
  PDF contains the strokes and no note text.
- **Latency harness:** presenter input to projector paint, measured with the server clock
  (`client.now()` exists in `web/shared/client.js`).
- **Devices, by hand per milestone:** Windows + Wacom (Edge, Chrome, Firefox), iPad + Pencil
  (Safari), macOS (Safari, Chrome), Linux (Chrome, Firefox); 1080p and 4K projectors.

## 14. Milestones and work items

| | Work items | Done when |
|---|---|---|
| **M1** Replace PowerPoint | build: `page/note/frame/step/frames/pdf/notes`, the stage compile (`--stage`, note pages interleaved), the stage PDF in the bundle, the authenticated PDF route; server: `stage`/`display` roles, `go`, `screen`, `timer`, the stage snapshot, persistence; web: PDF.js rendering and cache, projector window (layers, overlay seam), presenter window (current, next, notes in both views, timer, overview, keys), `texstage present`; tests | one chapter presented without PowerPoint, quizzes included |
| **M2** Ink and pointer | ink engine (input, perfect-freehand, layers), relay and storage, eraser and undo, pointer, zoom, whiteboard pages; browser tests with simulated pen | a lecture with Wacom ink, pointer, zoom and a whiteboard page |
| **M3** iPad | pairing and device tokens, touch layout, palm rejection, latency measurements in the room network and through the tunnel | the same lecture driven and inked from the iPad |
| **M4** After the lecture | pdf-lib export, lecture archive and ZIP | annotated PDF and results of a real lecture uploaded |
| **M5** Recording | capture of the projector output from the presenter window, microphone, chunked upload, controls, remux | a recorded lecture as a video file; a screen-shared session |
| **M6** New interaction | text/KaTeX path in the views, ad-hoc polls, Q&A, sketch quiz type (LaTeX and ad hoc) | one lecture with an ad-hoc poll, Q&A and a sketch question |
| **M7** Release | pypdfium2 instead of PyMuPDF, lazy import, packaging (`texstage` entry point), documentation, licence headers | Apache-2.0 release |

## 15. Risks

- **PDF.js on the iPad** with heavy TikZ pages: rendering time and memory. Mitigation: render ahead,
  reduced-resolution previews, a cache limit; measure in M1 on real decks.
- **The stage compile costs build time:** a `--stage` build runs pdflatex twice as often (in
  parallel, so the wall time grows less). Notes written for the tiny extraction template can run
  off the deck's own note page; the cut-off check reports them (DBIS notes are already sized for
  `dbisscript`).
- **Browser differences** in pen input (Safari, Firefox) and screen capture (permission prompts,
  formats): each feature has a baseline that works everywhere and Chromium-only enhancements.
- **One build per game:** loading another build ends the game; the presenter window guards it.
- **Scope:** M1 alone replaces PowerPoint; each later milestone is useful on its own, so the
  project can stop after any of them.

## 16. M1 as built (2026-10-07)

- **Build** (section 3): `texstage build --stage`; note pages marked through `\AtBeginNote`; the
  frames and steps per slide in `deck.json`; builds without `--stage` unchanged.
- **Server:** roles `stage` (everything a host can, plus `screen {screen}` and
  `timer {action: start|pause|reset|target, seconds?}`) and `display` (sends nothing). Deck slides
  are driven with the host's `slide` command; `go` comes with whiteboard pages (M2). The host view
  has `stage {screen, frozen, timer}`, stored with the session (`sessions.stage`); the timer goes on
  in the deck's next game (after the podium, a restart, a rebuild), not in the next lecture.
  `GET /api/deck/<bundle>/pdf` for hosts only; `/api/decks` says which builds have a stage PDF.
- **Windows:** `/stage` (presenter: picks the deck as the host console does) and
  `/stage/projector?bundle=…`; `texstage serve --present` opens the presenter. PDF.js 6.4.299 is
  vendored (`web/vendor/`; the server serves `.mjs` as JavaScript, which a Windows registry may
  not). Pages are rendered at their size in device pixels into a cache of 48 megapixels and the
  next two steps ahead. The projector window's keys go to the presenter window over a
  `BroadcastChannel` (`texstage:<bundle>`), so a clicker works whichever window has the focus;
  frozen, it keeps the state of the moment it froze, live views included. The timer starts with
  the first step (as PowerPoint's with the show); keys B or `.` black, W or `,` white, F freeze,
  G overview, T timer, a number and Enter. Notes: the note page by default, the text (A−/A+, kept
  per browser) as the option.
- **Not yet:** a players panel in the presenter window (kick and rename stay in the host
  console); a warning before another build of a running deck is loaded (the deck list shows the
  game); the iPad layout beyond the narrow one-column view (M3).
- **Tested:** engine and server tests for the roles, the screen, the timer and its persistence;
  in Edge, a DBIS deck (33 frames, 5 quizzes) through join, reading, question and reveal, black,
  freeze, overview, number jumps, text notes, and a key in the projector window moving the
  presenter.

## 17. M2 as built (2026-10-07)

- **Ink** (`server/ink.py`, `web/stage/ink.js`): strokes per game and frame - `"12"` for a deck
  frame, `"board:<id>"` for a whiteboard page -, points as `[x, y, pressure]` (fractions of the
  slide, rounded to 1/10,000; pressure to 1/1,000), the width in fractions of the slide's height.
  `ink.begin` / `ink.points` (batches of at most 400 points, one per animation frame) / `ink.end`;
  only an ended stroke is stored (table `strokes`, kept when erased). `ink.erase` (the stroke
  eraser: one message per gesture), `ink.clear`, `ink.undo` and `ink.redo` per device (a name the
  window keeps over reloads) and frame - the history lives in memory, so a restarted server keeps
  the strokes, not the undo. `ink.load` gives a frame's strokes and those being drawn; the
  projector window may ask for it, nothing else. Events go to the game's other texstage windows
  as they happen; a window that lost its connection loads the ink anew.
- **Transport - the local fast path dropped:** through the server, on the laptop, a batch of
  points reaches the projector window in 1.0 ms (median; 95 %: 1.6 ms, at most 2.2 ms, measured
  over 300 batches at drawing speed), so the `BroadcastChannel` for ink (section 6.4) would only
  add a second path to keep consistent.
- **Strokes:** perfect-freehand 1.2.3 (vendored, MIT) computes the outlines - in thousandths of
  the slide's height, because its constants are tuned for pixels (a radius of at least 0.01 units
  swamped strokes measured in fractions of the slide). A pen's pressure shapes the stroke; mouse
  and finger strokes keep an even width. The highlighter is drawn under the pen strokes at 35 %.
  The ink lies over the live quiz views and under the laser pointer and the quiz buttons.
- **Input:** Pointer Events with their coalesced samples. Without a tool chosen ("navigate") a pen
  draws all the same and its eraser end erases, while the mouse keeps the quiz buttons; a chosen
  tool takes the mouse too. Touch is ignored for 1.5 s after a pen was seen (the palm).
- **Laser pointer:** `pointer {x, y}` / `{off}`, sent without an id (no answer), at most once per
  animation frame, not stored; a red dot, drawn the moment a position comes (no trail since
  2026-10-10, section 24).
- **Zoom:** a box dragged with the zoom tool becomes a square in fractions of the slide (the
  slide's shape; at most 12.5×), `zoom {rect}`, kept in the stage state and ended by the next slide
  or `zoom {rect: null}` (Z, the Zoom button, or a tap on the "zoomed" label over the slide - not
  Esc, see section 24). The presenter window zooms with the projector; the PDF is
  rendered anew for the part shown (sharp), the live views are scaled with CSS.
- **Whiteboard pages:** `board {after: frame, kind: blank|grid}` → its id; `go {board}` shows it,
  the next `slide` ends it. They come after their frame in navigation and overview, have ink of
  their own, can be frozen (`frozen_board`), and - like the ink - go on in a new game of the same
  build (a restart, the next group), not after a rebuild.
- **Keys:** P pen, H highlighter, E eraser, L laser, Z zoom, N whiteboard page (Shift+N with a
  grid), Ctrl+Z / Ctrl+Y, Esc back step by step (number, overview, tool).
- **Not yet:** ink on the overview's tiles and on the next step; zooming with the wheel or a pinch;
  touch drawing beyond the palm rule (with the iPad, M3).
- **Tested:** engine tests (strokes, batches, erase, clear, undo/redo per device, restart, a new
  game, a rebuild; zoom and whiteboard pages) and a server test (relay to the projector, pointer,
  `ink.load`, the projector's refusals); in Edge with the DBIS deck: a mouse stroke, a pen stroke
  with pressure (DevTools protocol), the highlighter, undo and redo, the laser, a zoom, a grid page
  with ink, both windows, and a projector reload that loads the ink from the server.

## 18. M3 as built (2026-10-07)

- **Pairing with a second step** (`server/devices.py`): the presenter window on the laptop (the
  presenter key) shows a QR code of `<public address>/stage#pair=<one-time code>` - in the
  fragment, so it never reaches a server log -, valid for two minutes and for one device. The
  device that opens it gets a four-character code and waits; the presenter window asks "iPad ·
  Safari wants to present. Allow it only if it shows this code" - Allow or Deny. Beyond the
  design's one-time token: a laptop screen mirrored to the projector would show the QR code to the
  room, and whoever scanned first would be in; now nobody is in whom the lecturer did not allow
  with the matching code. Unknown codes count against the client's address (20 in 10 minutes).
- **The device:** a token of its own (`X-Texquiz-Device`, `hello {device}`), kept in the device's
  local storage; the server keeps its hash in `<data>/devices.json`, owner and name. It presents
  as its lecturer - decks, deck.json, the stage PDF, results, the game, ink - but neither
  publishes, pairs devices, lists them, nor gets the presenter key. *Devices* in the presenter
  window lists them (paired, last seen) and removes one: its connections end at once (`bye
  removed`), and it is back at the start. No separate `devices` table: a file like
  `lecturers.json`.
- **On the iPad:** the same presenter window, without *Projector* and *Devices*; buttons of at
  least 44 px on a touch screen (`pointer: coarse`), a smaller page cache (20 instead of 48
  megapixels). The Pencil draws (with pressure; with the laser chosen, the dot follows the Pencil -
  also hovering, on iPads that sense it), a finger's swipe over the slide steps on or back, touch
  is ignored 1.5 s after the pen. The design's
  drawer for notes and next step was not needed: the wide layout fits a landscape iPad, the narrow
  one a portrait iPad.
- **The network:** the iPad reaches the server at its public address - in the room the laptop's
  address (the default without a tunnel), with `--tunnel` the tunnel's. The presenter window shows
  the round trip to the server next to the connection's dot (a ping every 5 s), so the lecturer
  sees what the room's network or the tunnel costs. Measured here only on this machine (2 ms);
  the room's Wi-Fi and the tunnel need the iPad in a lecture hall (M3's "done when").
- **Tested:** a server test of the whole pairing (the key only, one device per code, the code
  compared, allowed and denied, the token handed over once, what a device may and may not, removal
  ending its connection) and the expiry and storage of codes and tokens; in Edge, an iPad context
  (touch, iPad's user agent, storage of its own) paired from the laptop's window, stepping with a
  swipe, writing with a pen - both seen in the projector window -, and removed.

## 19. M4 as built (2026-10-07)

- **The annotated PDF** (`web/stage/export.js`, pdf-lib 1.17.1 vendored, MIT): *After the
  lecture*, *Make the PDF* in the presenter window. It takes the stage PDF (from the browser's
  cache) and all the game's ink in one message (`ink.all` → `{frames}`), and writes per frame the
  slide page of its last step - copied in one go, so the fonts are copied once - and per
  whiteboard page a blank or grid page, in the order presented; the note pages are not copied,
  so no note text is in the file. Each frame's strokes are drawn as filled vector paths, the
  same perfect-freehand outlines as on the screen (`ink.js` `strokeSvg`), the highlighter under
  the pen at 35 % opacity. Synthetic leaderboard slides have their anchor's page and fall away
  with the frame. The live quiz views are not in it (they are not part of the slide); the quiz
  results go into the archive as CSV.
- **The lecture archive:** the presenter window downloads the PDF
  (`<deck>-<date>-annotated.pdf`) and puts it on the server (`PUT
  /api/archive/<game>/annotated.pdf`, at most 300 MB, a PDF only), which keeps it in
  `<data>/archive/<deck>/<date>-<pin>/` with the game's results (the CSV of the results export,
  written anew); `GET /api/archive/<game>.zip` gives the folder as one file. Both for the
  lecturer's key and for paired devices. The Q&A and sketches (M6) will join the folder; the
  recordings (M5, section 20) did.
- **Tested:** a server test (`ink.all`, the archive's refusals, folder, files and ZIP); in Edge
  with the DBIS deck: ink on two frames (pen, highlighter) and on a grid page, the PDF made,
  downloaded and archived, the ZIP downloaded; the PDF checked: 34 pages (33 frames and the
  whiteboard page) of the slide's size, the strokes as filled vector paths in their colours (the
  highlighter's fill opacity 0.35), the grid, and no note text.

## 20. M5 as built (2026-10-07)

- **Recording** (`web/stage/record.js`): *Record* in the presenter window's top bar, on the laptop
  (the presenter key), not on a paired device. A dialog first opens the microphone and shows its
  level (another microphone or *no sound* can be chosen; the choice is kept); *Start recording*
  then opens the browser's dialog for the screen. The projector's screen is preselected where the
  browser can (`displaySurface: "monitor"`; `"window"` when the laptop has one screen), the
  presenter window itself is left out (`selfBrowserSurface`), and the capture is at most 1080p at
  30 frames a second - a 4K projector would cost the laptop's CPU. MediaRecorder records screen
  and microphone (WebM with VP9 and Opus, else VP8, else MP4; 2.5 Mbit/s video, 128 kbit/s audio -
  slides change rarely, so the encoder spends much less most of the time). While it runs, the top
  bar shows a red dot, the recorded time, the microphone's level, pause and stop; the projector
  shows nothing of it. Stop asks first (recording again makes a new file); *Stop sharing* in the
  browser's bar stops it too.
- **Parts:** MediaRecorder hands out a part every 10 s, and the presenter window sends it at once -
  one at a time, in order, again after a failure (after 1 s, doubling up to 15 s; meanwhile the top
  bar says *saving delayed*, and the parts wait in the window's memory). `POST
  /api/archive/<game>/recording {ext}` starts a *take* in the game's folder of the archive
  (`server/archive.py`), `PUT /api/recording/<take>/<n>` adds part n, `POST
  /api/recording/<take>/done` finishes it. Unlike section 9's sketch
  (`/api/stage/{session}/recording`), a take is not bound to its game: it stays in the folder of
  the game it started in while the lecture goes on with a new game or another deck. The server
  keeps `recording-<take>.<ext>.part` and `recording-<take>.json` (whose it is, parts and bytes):
  a part sent twice is taken once, one that comes too early is refused, one the server was
  writing when it stopped is written again (the file is cut back to the bytes counted), and a
  restarted server goes on where it was. Only the take's lecturer reaches it (anyone else: 404).
- **The end:** `done` renames the file to `recording-<take>.webm` (or `.mp4`) and, if ffmpeg is
  on the PATH, copies it through `ffmpeg -c copy` in a background thread: the browser's WebM has
  no duration and no seek index (cues), afterwards it has both. Closing or reloading the presenter
  window while recording asks first (`beforeunload`); if it closes anyway, a last request
  (`keepalive`) finishes the take with what reached the server - the last seconds at most are
  lost. A take nobody finished is listed as unfinished and can be finished under *After the
  lecture*.
- **After the lecture** lists the recordings of the game's folder and those this window made
  (kept in the tab's `sessionStorage`), with size and folder. *Download* asks for an address that
  downloads the file for ten minutes (`POST /api/recording/<take>/download` →
  `/download/<ticket>/<deck>-<date>-<time>.webm`, not kept by proxies): a link cannot send the
  key, and a recording is too large for the page's memory. The ZIP leaves recordings out.
- **The projector window follows the deck** (an M1 gap): when the presenter window opens another
  deck, it tells the projector window (BroadcastChannel `texstage`), which loads the deck in
  place - it stays full screen, and a screen share (R1) or a recording of it goes on; before, it
  kept the old deck. `PdfDeck.close()` frees a deck's pages and its PDF.js worker.
- **The top bar** stays one row while recording, down to 1280 px: the players and the join
  address take the room that is left and are cut short at the end.
- **R1** needs nothing more: the projector window has no controls, so a hall's capture system or
  Zoom/Teams shares it as it is.
- **Not done:** a recording cannot go on after a reload (the browser ends the capture; a new
  recording is a new file); the ZIP does not include recordings; only Edge was tested (Safari's
  MP4 path, Firefox's VP8 are not).
- **Tested:** server tests (parts in order and once, the refusals, another lecturer, a restarted
  server with a half-written part, finishing, a take without parts, the download address, the ZIP
  without the recording; a live WebM - no duration, no cues - remuxed by ffmpeg into the same
  streams with both); in Edge with the keynote deck, a canvas standing in for the screen (headless
  Edge has no picker) and Edge's fake microphone: the level in the dialog, a part held back by a
  failing network and sent later, pause, a new game while recording, stop, the file downloaded -
  VP9 1280×720 and Opus, 14.2 s as recorded without the 3 s pause, with cues -; another deck while
  recording, the projector window following in place; the window closed while recording (asked
  first, then finished on the server with its first part); the top bar at 1920 to 1280 px.

## 21. M6 as built (2026-10-07)

- **Text with formulas** (`web/shared/text.js`, KaTeX 0.19.0 vendored, MIT): texts typed during
  the lecture - polls and the audience's questions - are shown with `$...$` typeset, on the
  phones, the projector and in the presenter window. A page loads KaTeX (273 KB, the fonts as
  WOFF2) only when a text holds a formula, and draws the text again once it is there. The
  audience types formulas too: no trusted commands (no links), bounded sizes and macro expansion.
- **Ad-hoc polls (Q1, `server/polls.py`):** *Poll* in the presenter window's toolbar - yes/no,
  A-F (2 to 6 answers, their texts optional - the letters alone when the slide shows the
  answers -, one or several), a scale 1-5, a word cloud (24 characters), text (140 characters, a
  list) or a sketch; the question typed (optional for the choices), a formula previewed as it is
  typed; a time of 10 s to 5 min. `poll.create` adds a quiz definition to the game
  (`sessions.polls`: the public part with texts where a deck's quizzes have pictures, and the
  keys) and asks it at once: the round starts, the phones show it, and the projector shows a
  generated poll slide instead of the slide (`stage.poll`): the question, the answers' boxes (side
  by side for yes/no and the scale), the timer and the count, the join line - and as soon as the
  round closes the results, in the boxes or as a word cloud or list. Its reveal is `auto`: no
  reveal slide - the phones show their *Thanks* after the grace period for late answers (when the
  lecturer stops it or everyone answered: at once). ↻ (ask again) on the poll slide asks it once
  more. The first → (or Esc) takes the projector back to the slide where the lecturer was; any
  navigation does so too. The lecturer can write on a poll slide (its ink: `poll:<id>`);
  *Show* in the dialog's list of the game's polls brings one back. The polls are columns of the
  results table and CSV, and `polls.csv` in the archive (question, answers, counts or words).
- **Questions from the audience (Q2, `server/qa.py`):** closed until the lecturer opens them in
  the *Q&A* panel (the setting goes on in the deck's next game, the questions do not). Then the
  phones get a second tab: ask (anonymous, up to 280 characters, one every 20 s, at most 5 open
  per player, 500 per game) and upvote the others' (not one's own; taken back with a second
  tap); they get the list only while the tab is open (`qa.watch`), at most every 500 ms, and a
  question that opens brings the quiz tab back. The panel (a drawer over the next slide and the
  notes) lists the open questions by votes: *Show* puts one on the projector as a card over the
  slide (`stage.question`, until *Hide* or *Done*), *Done* moves it to the answered ones, *Delete*
  removes it, *Block* removes it with its asker's other open questions and stops that player
  asking (`players.muted`). No view names anybody: the player id stays on the server, for
  blocking. The store keeps the questions (a `questions` row each, with its votes); the archive
  lists them in `questions.csv`.
- **Sketch questions (Q3):** `\begin{quiz}[type=sketch]` in a deck (texquiz.sty: like an open
  question - a live area, never scored, the hint `sketch-hint`, German in the DBIS theme) or a
  sketch poll. The phone shows a drawing pad: finger, pen or mouse, four colours, undo and clear;
  the strokes are integers on a 1000 × 750 canvas (4:3), simplified (Ramer-Douglas-Peucker,
  more until the answer's JSON fits in 14 KB - the server takes at most 300 strokes and 6000
  numbers: `scoring.py`). The host view carries only the count: *Sketches* in the toolbar (while
  a sketch question is the current one) opens a gallery that fetches the drawings as they come
  (`sketch.list {quiz, after}`, numbered in the order they came); the lecturer picks up to 12,
  and *Show on the projector* puts them there on a board of their own (`stage.sketches`: the
  question - a poll's text or a deck's question as the phones' picture -, the tiles numbered,
  no names); the projector fetches their strokes (`sketch.get`, also for the display role). The
  archive keeps every sketch as `sketch-<question>-<n>.svg`; the results CSV says "(sketch)".
- **Overlays:** a poll and picked sketches take the slide's place on the projector until the
  lecturer goes on (`show_slide` and `go` end them; zoom does not apply to them, and sketches take
  no ink); the question card goes over whatever is shown. The presenter window's current view
  shows the same; while the projector is frozen, it keeps what it showed.
- **Store fix:** since M2 the store wrote every column named `points` as JSON - meant for the
  ink, it also hit the answers' points, which came back as text after a restart (the results CSV
  then failed). The JSON columns are per table now; older files are read as before.
- **Not done:** the annotated PDF has no poll slides or sketches (they are in the archive's CSV
  and SVG files); ad-hoc polls have no right answer and no points; the host console and the
  PowerPoint add-in do not ask polls or show the audience's questions panel.
- **Tested:** engine tests (polls of every kind and their refusals, the grace before the reveal,
  stop, the results table, a restarted server; sketches - their refusals, numbering, picking,
  the projector's fetch, navigation ending the board, kicked players; questions - closed,
  limits, votes, ranking, what phones and the presenter see, show, done, block, a restart, a new
  game); a server test over WebSockets (the three, and the archive's `polls.csv`,
  `questions.csv` and sketch SVGs after a restart); a LaTeX test for `type=sketch` (the pages,
  the hint, the handout, its refusals); in Edge with a deck built with a sketch question, the
  presenter and projector windows and two phones (mobile contexts): an A-F poll with formulas in
  the question and an answer (typeset on the phones and the projector, the results in the
  boxes), a word cloud, a question with a formula asked, upvoted, shown on the projector and
  done, the deck's sketch question drawn on both phones, picked in the gallery and shown, and the
  archive's files; no errors in any window.

## 22. M7 as built (2026-10-07)

- **PyMuPDF replaced by pypdfium2** (5.14.0, Apache-2.0/BSD-3-Clause; PDFium, Chrome's PDF
  engine; download approved). `texstage/build/pdf.py` is the one place that touches it: `Pdf`
  (pages, their size), `Page.render(scale, clip, alpha)`, `Page.words(clip)` and
  `Page.text(clip)`. A page is drawn through a matrix at exactly the scale, into an image of the
  rounded size (pypdfium2's own helper rounds up - 1081 pixels for 1080 - and draws the whole
  page into whole pixels, which scales a page and the half of a page twice as wide a little
  differently: the stage pages and the present deck's slide halves then differed by up to half a
  pixel). PDFium knows characters, not words: a word is a run of characters up to a
  space or line break PDFium generates, its box the characters' loose boxes (the font's ascent
  and descent, as PDF readers mark text - one height per line, which the notes' line grouping
  needs), typeset ligatures as letters. Ported: the build (`raster.py`, `notes.py`, `builder.py`,
  `stage.py`), `scripts/beamer2pptx.py`, `build-chapter.py`, `render-pages.py` (its contact
  sheet now with Pillow), `tools/contact_sheet.py`, `tools/deck_baseline.py` (its fingerprints
  are PDFium's now: baselines made before must be made again), the tests.
- **Compared on the keynote's present PDF** (43 slides): the notes text of 42 slides is
  identical; the one difference is a formula, where PDFium separates "∃ p" and "≤ p" that MuPDF
  ran together. Slide pictures have the same size (1920 × 1080); their pixels differ by 1.5/255
  on average - antialiasing at edges, 0.8 % of the pixels by more than a quarter. Phone images
  crop to the same box within a pixel. A rebuilt deck therefore gets new picture hashes and a
  new bundle ID - an ordinary new build; the stage PDF's pages and the handout's still match the
  present deck pixel for pixel.
- **Lazy import:** `texstage serve` - and the Docker image - loads nothing of the build (LaTeX,
  PDFium, Pillow, python-pptx, lxml); only the bundle format. `DEFAULT_SERVER` moved to
  `texstage/__init__.py`.
- **Packaging** (`pyproject.toml`, version 0.2.0): `license = "Apache-2.0"` with `LICENSE`,
  `NOTICE` and the vendored libraries' licence files; the commands `texquiz` and `texstage`.
  `texstage deck.tex` builds the deck with its stage PDF (`texstage build --stage`, the server
  `http://localhost:<port>`) and presents it (`texstage serve --present`); with folders, it
  presents the decks in them; a failed layout check only warns (since 2026-10-10 it is `texstage
  present`, section 24). The LaTeX package goes into the
  wheel as `texstage/latex/` (the repository keeps it in `latex/`, where the DBIS slide style
  finds it, and `pyproject.toml` maps that folder) and the build looks there first
  (`latex.latex_dir()`); `dbis-slides.sty` stays out. The package list is explicit, the web
  pages' folders included (setuptools would otherwise warn that it will stop packing them); a
  test keeps the list complete. `MANIFEST.in`: the source distribution has the docs (not
  `docs/pilot/`), the demo, `deploy/`, the texquiz scripts and the tests - not the DBIS tooling.
  The package page is `README-texstage.md`.
- **Licence scope:** the Apache-2.0 licence covers the texstage package of the repository, which
  `NOTICE` lists by path; the DBIS lecture tooling (`dbis-slides.sty`, the other scripts,
  `tools/`, `skills/`, `docs/pilot/`, `README.md`) is not covered. 80 source files say so in
  REUSE-style SPDX lines (`SPDX-FileCopyrightText: 2026 Stefan Decker`,
  `SPDX-License-Identifier: Apache-2.0`).
- **Licence audit** (the installed packages' own metadata): pypdfium2 (Apache-2.0,
  BSD-3-Clause and its dependencies' licences), Pillow (MIT-CMU), python-pptx (MIT) with
  XlsxWriter (BSD-2-Clause), lxml, Starlette, uvicorn, segno, click, idna, websockets,
  python-dotenv (BSD-3-Clause), anyio, h11, httptools, PyYAML, watchfiles (MIT), colorama (BSD),
  typing_extensions (PSF-2.0), uvloop where it is used (MIT/Apache-2.0); vendored PDF.js
  (Apache-2.0), perfect-freehand, pdf-lib, KaTeX (MIT). Nothing copyleft.
- **Not done:** publishing - no upload to PyPI, no public repository (the repository is the
  DBIS group's on gitlab.git.nrw); the package's name `texquiz` and `texstage` are free on PyPI
  today.
- **Also:** the server tries a folder rename again that Windows refuses for a moment (a virus
  scanner or the search indexer still holding a file just written): for up to 1.5 s when a
  build arrives, for 0.15 s when a game copies its deck (on the event loop; if that fails, the
  game goes on from the build folder). It made the publish tests fail now and then.
- **Tested:** the whole suite with every import of PyMuPDF blocked; `tests/test_packaging.py`
  (the package list, the licence files and headers, no PyMuPDF anywhere, the `texstage` command,
  a server that loads nothing of the build); the wheel and source distribution built offline (setuptools 78 of the
  machine's Python 3.13) and inspected; the wheel installed into a folder of its own: it finds
  its `texquiz.sty`, compiles the demo, and builds it for texstage - PowerPoint, bundle, stage PDF
  and notes - with PyMuPDF blocked; `texstage --help`.

## 23. Beside texquiz 0.1, until the merge (2026-10-08)

On 2026-10-08, until it was merged into `main` the same day, this version (0.2, branch
`texstage`) ran beside texquiz 0.1, which the lectures and the keynote used. The two shared
nothing at run time: two working trees of the repository (`lecture-tools` on `main`,
`lecture-tools-texstage` on `texstage`), each with a `.venv` of its own; fixes to 0.1 went to
`main` and were merged into `texstage`. This version's port and data folder were 8471 and
`~/.texstage`.

- **Why a data folder of its own:** this version adds columns to the tables it finds
  (`sessions.stage`, `sessions.polls`, `players.muted`) and tables of its own (`strokes`,
  `questions`), and 0.1 builds its objects from every column - after this version has opened a
  database, 0.1 fails on a game still open (`TypeError: Session.__init__() got an unexpected
  keyword argument 'stage'`, tried on a scratch copy). The folder also kept 0.1's remembered
  tunnel, presenter key and add-in apart.
- **The merge:** `DEFAULT_PORT` and `DATA_NAME` (`texstage/__init__.py`, the one place the
  commands, the presenter keys and the build take them from) are 8470 and `.texquiz` again: 0.2
  takes over the laptop server's folder, key and tunnel. Its first start on `~/.texquiz`
  upgrades the database, one way - 0.1 cannot load a game still open from it afterwards. Each
  lecture changes over on its own: its submodule to the new `main`, `pip install -e tools` again
  (pypdfium2), a rebuild (new picture hashes, so new bundle IDs).

## 24. After the merge (2026-10-08)

- **Dividers in the presenter window**, as in PowerPoint's presenter view (`web/stage/split.js`):
  one between the current step and the column with the next step and the notes, one between the
  next step and the notes. The grid has a column of its own for the first (`--grip`, 10 px, 18 px
  for fingers); in a narrow window, with the column below the step, it is a row. The shares are
  CSS variables (`--side-w`, `--next-h`, `--side-h`; defaults 35 %, 30 %, 38vh - the layout of
  before) and are kept with the presenter's preferences, per browser. Drag (mouse, pen, finger), or
  Tab to a divider and use the arrow keys (Shift: further); other keys stay the presenter's. A double
  click or tap puts a divider back; a click never leaves the focus on it, so the arrow keys keep
  stepping the slides. The next step can be dragged away entirely (all notes). While a divider is
  dragged, the PDF pictures only stretch (`PdfSurface.hold`): they are drawn sharp once it is let
  go, not at every intermediate size.
- **No browser dialogs in the presenter window:** `confirm()`, `alert()` and `prompt()` take a
  full-screen window out of full screen (reported for *Clear*). `web/stage/ask.js` asks in the page
  instead - `ask`, `tell`, `askText`; Enter yes, Esc no, and no key reaches the presenter
  meanwhile (it leaves the keys to any open `.dialog`, which also stops Enter or Space on a dialog's
  button from stepping the slides). *Clear* asks nothing: the server keeps it in the device's undo
  history of the frame, so ↶ or Ctrl+Z brings the ink back, and a notice says so.
- **A pen on the projector window** (`web/stage/pen.js`), for lecture halls with a pen display at
  the lectern that shows the projected picture: a pen (`pointerType` pen, nothing else) draws on
  the slide the window shows - frozen or zoomed as shown, not on a poll or the sketches - in the
  presenter window's pen colour and width (its preferences: same origin), the eraser end erases,
  and with the side button held - hovering or touching - it is the laser pointer (shown there at
  once, sent at most once per animation frame, off when the button is let go or the pen leaves;
  the button's tap opens no menu). The strokes carry the presenter window's name for undo: a
  window opened with `window.open` starts with a copy of the opener's sessionStorage, where the
  name is kept - so the presenter window's ↶, ↷ and Clear take them too. The server lets the
  display connection send `ink.begin`, `ink.points`, `ink.end`, `ink.erase` and `pointer` (`PEN`
  in app.py; it holds the presenter key anyway) and nothing else. The pen's colours, widths and
  the window name moved from presenter.js to pen.js, which both windows use.
- **Small presenter windows:** the current step keeps 120 px; in a window with the column below the
  step, the column gives way first (its row is `minmax(0, --side-h)`); in a short window (520 px
  or less) the tools and the bar stay one row each and scroll sideways.
- **The phones for screen readers:** the answers are pictures with a letter; the buttons are named
  ("Answer A", with a poll's text), the question's picture says what it is, the order's arrows
  name their answer, and the shapes are hidden from the reader.

The dry run with the keynote deck on 2026-10-09 found these, fixed the same day:

- **The tunnel over HTTP/2** (`server/tunnel.py`, see `design.md`, section 8): the wired network
  blocks QUIC, and cloudflared took 2.5 minutes to fall back.
- **A new presentation, or the lecture continued:** *Present* went on with the game of the
  morning's tests, its ink and whiteboard pages included. Now *Present* (not a reload in the
  lecture) asks when the deck has ink or whiteboard pages from before - of its open game or, while
  that has none, of its last ended game of the same build -, unless another presenter window is on
  the game: the welcome of a `stage` hello carries `earlier` ({game, open, at, frames, boards} or
  null) and `presenters` (its other windows). *New presentation* of an open game is `lecture.new`:
  a new game without the ink, the pages and the timer (the phones join with a new PIN); the old game
  ends and keeps them in the archive. *Continue that lecture* of an ended game is
  `lecture.continue {game}`: copies of its strokes (new ids) and its pages, so that lecture's
  archive stays as it was. The other windows get `{"t": "ink", "op": "reload"}` and load their ink
  anew. Ink of another build does not come along (its frames may differ); a quiz game can still be
  restarted with *New game*, which keeps ink and pages as before.
- **The laser, steadied and slower** (reported for mouse and touchpad: it trembled and moved too
  far). The presenter window smooths it with the One Euro filter (`web/stage/steady.js`: a still,
  trembling hand two to four times calmer, little lag when it moves quickly, the dot settles where
  the hand stops) and shows and sends it once per animation frame. With a mouse or touchpad, L (or
  the button) locks the mouse to the laser (pointer lock): the cursor hides, the laser moves 0.4 of
  the mouse's way and stays on the slide shown, and a click does not move it; L, Esc, another tool,
  the overview, the window losing the focus or pushing on past the slide's edge (below) give the
  cursor back. A pen or a finger points where it is, steadied too. (Taken back on 2026-10-10, the
  last item: it lagged.)

Reported after that, the same day:

- **A number question's answer slide:** the distribution of the answers covered the explanation
  (the live area of the frame). The answer slide shows it no more - the question slide did, when
  the time was up - in PowerPoint and texstage alike (`live.js`, `question(revealing)`).
- **The iPad's Pencil stopped drawing now and then:** a resting palm or finger elsewhere in the
  window - the notes, the toolbar, a button - began a scroll, a selection or a zoom, and iOS
  cancels the pen's stroke for that. While the pen draws and for 1.5 s after its last input
  (`PEN_QUIET`), the presenter window takes no other touch anywhere: no pointerdown reaches a
  button, divider or the swipe, touchstart and touchmove are cancelled (no scroll, zoom or
  click; the Pencil's own touches, `touchType` stylus, stay), and selectstart, contextmenu and
  Safari's gesture events too. On a tablet (`any-pointer: coarse`) nothing in the window selects
  text or opens a callout, and buttons ignore double taps (no zoom). On the iPad the strokes were
  lost all the same: the cause was Scribble (the last item). The guard stays, against a palm on
  the buttons.
- **Every deck reaches its quiz server through its build** (`docs/design.md`, sections 4 and
  5.2): PowerPoint keeps at most 2 MB for an add-in, so a chapter's file could not bring its deck
  to the server. The PowerPoint file carries none now; `texstage build` records its build folder in
  the data folder (`builds.json`), and the quiz server on that machine serves those decks too -
  in texstage's deck list as well, with their stage PDFs, whatever folder it was started with -;
  a server elsewhere gets the deck uploaded at the end of the build.
- **And by hand, to be sure** (`docs/design.md`, section 8): the build writes the deck as one
  file too, `<name>.bundle.zip` next to the PowerPoint file, and the deck lists of texstage and
  of the host page upload it - **Upload a deck**, or the file dropped onto the list - with the
  presenter key (`POST /api/bundles`); the list then says what arrived, or that the server had
  it already. A `.bundle` folder zipped by hand works too, for older builds.
- **The iPad's lost strokes, found** (on the lecturer's iPad, the same evening): a stroke whose
  Pencil came down quickly after the last one was lifted never arrived; with a short pause
  between strokes, all arrived. The cause was iPadOS's Scribble (handwriting into text fields,
  on by default): Safari keeps such a touch, and the page gets no pointer events for it (Apple's
  developer forums, thread 662874; WebKit bug 217430). Turning Scribble off (Settings → Apple
  Pencil) fixed it; `authoring.md` says so where it sets up the iPad. Not done: texstage
  cancelling the Pencil's own touch events on the slide, the workaround reported for Scribble
  left on.
- **A double tap of the pen's tip switches between drawing and the eraser** (the lecturer's
  wish, the same evening). Apps do this with the Pencil's own double tap, but Safari keeps that
  one to itself (`UIPencilInteraction` is for apps only). Here: twice on the same spot, quickly,
  without moving (`TAP_MS` 250 ms down, `TAP_MOVE` 4 px, `TAP_GAP` 300 ms between, `TAP_SPOT`
  6 px apart; CSS pixels, on an iPad about 5 to the millimetre); from the eraser it goes back to
  the drawing tool it came from. A tap goes to the server only when no second one can follow
  any more - a dot reaches the projector 0.3 s late, a stroke as soon as it moves 4 px - so a
  double tap leaves nothing behind: no dots, nothing erased (the eraser's taps give back what
  they took), nothing to undo. Dots side by side (ä, ö, ü, a colon) lie further apart and stay
  dots. Checked in the browser with simulated pen events (single and double taps both ways,
  also on a stroke; an umlaut's dots; a stroke sent while drawn; undo after a double tap; the
  highlighter; slow taps; the mouse unchanged); not yet on the iPad. (Taken back the next day: on
  the iPad it did not work reliably - the last item.)
- **Back from the zoom without Esc** (the lecturer, the same evening): in a full-screen window
  Esc also ends full screen - on Windows the projector window, whose keys come to the presenter
  window - and an iPad has no Esc key, so there the zoom could only be left by the next slide.
  Esc no longer ends the zoom. The red label over the zoomed slide in the presenter window
  ("Projector: zoomed ×2.0 - ⤢ tap: the whole slide") is a button now, for a finger, the Pencil
  or the mouse; the Zoom button, highlighted while zoomed, gives the whole slide back too, as Z
  does.
- **The laser kept the mouse in the slide** (the lecturer, on the laptop, the next morning): with
  the mouse locked to the laser, the toolbar could only be reached by L, Esc or another tool's
  key. Now pushing on past the slide's edge ends the laser and the cursor is back - outwards,
  80 px of the mouse's way (`LASER_OUT`, counted while the laser sits at the edge and the
  movement points mostly out of the slide; along the edge or back in starts the count anew), so
  a laser resting on something at the edge stays. Where the cursor shows up again is the
  browser's affair (expected: where the lock began - the Laser button, or where it was at L).
  Checked in the browser with the pointer lock stood in for (the hidden test pane is granted
  none); not yet on the laptop.
- **Back to the plain laser** (the lecturer, the same morning, after trying it: "too laggy" -
  better fast than late). The smoothing (`steady.js`, removed), the locked mouse at 0.4 of its
  way and with it pushing past the edge are gone: the laser is where the mouse, the pen or the
  finger is, at once in the presenter window and with the next animation frame on the
  projector, as before 2026-10-09. The cursor stays free.
- **And without its trail** (the lecturer, right after: "very laggy", in the presenter window
  too). The plain laser still drew a 300 ms fading trail behind the dot (requirement I4) - with
  the cursor hidden over the slide, a red streak that drags behind every movement. Now the laser
  is the dot alone (`PointerLayer`), drawn the moment a position comes - in the presenter window
  in the pointer's event, on the projector when the message arrives - instead of on the next
  animation frame. The projector's pen draws the same dot with its side button.
- **And the cursor as the dot** (the lecturer, after that: "still a little bit laggy, in both
  windows"). A dot the page draws comes a frame or two after the hand; the system's cursor does
  not. So with a mouse (or touchpad) the presenter window's laser is the cursor itself, a red dot
  made at start (`--laser-cursor`, a 32 px PNG), and the page draws none; a pen's or a finger's
  (an iPad has no cursor) is still drawn. The positions go to the projector at once, not with the
  next animation frame (pointermove comes once per frame anyway; while the laser is pressed and
  dragged, only the newest of the coalesced events) - also the projector pen's side-button
  laser. Measured in the browser: 1 ms from the mouse's event to the projector's connection.
- **And a little ahead** (the lecturer, after that: no lag in the presenter window, too much in
  the projector window - both on the laptop's own screen, 3-7 ms round trip). Measured: the
  positions reach the projector's connection 1 ms after the mouse's event (300 of them: median
  1.1 ms, at most 3.3 ms - no Nagle batching on the local connection), the server sends nothing
  else meanwhile, and the projector window does no heavy work per frame. What is left is the
  browser's own way to the screen: a dot that a window draws is two or three frames behind the
  system's cursor, which the lecturer sees right beside it. So the presenter window takes the
  mouse's raw input (`pointerrawupdate`, Chromium: not held back to the next frame; at most
  every 8 ms) and sends the dot where the mouse will be 25 ms later at its speed (`LASER_LEAD`,
  at most 3 % of the slide ahead); 30 ms without a movement, where it is. Checked with a steady
  movement: about 0.01 of the slide ahead at half a slide per second, and exactly in place after
  the stop.
- **The double tap goes again** (the lecturer: "it does not work reliably - better something
  that works all the time"). Strokes and the eraser go to the server at once again, as before;
  the Eraser button and E switch.
- **The iPad's laser seconds behind on the projector** (the lecturer, right after). The iPad
  reaches the server at its public address - with a tunnel, through Cloudflare, also at home
  on the same Wi-Fi (the pairing code names `public_url`) - and sent a position for every
  movement of the Pencil, without waiting; through the tunnel they piled up. Now the laser's
  positions go one at a time: each with an id, the next only when the server has answered the
  last - then the newest, the ones in between are dropped (and after a second without an
  answer, it goes on all the same). However slow the way, the dot is at most a round trip
  late; on the laptop the answer comes within a millisecond. The server answers such a
  position and keeps the answer out of its reply cache. Checked: 400 positions as fast as they
  come gave 13 messages, the last one the last position, 5 ms after the burst.
- **One command to present: `texstage present`** (the lecturer: what is the difference between
  texquiz and texstage - PowerPoint uses the same server). It is one server for both; texstage
  is the browser presenter's pages, and the command `texstage` is now `texstage present` by
  another name. `texstage present <deck.tex | build folder>` - in a lecture
  `tools/scripts/texstage-present.py <chapter>` - builds the deck when its build is missing, has
  no stage PDF or is older than its sources, uses the quiz server already running on this
  machine or starts one, and opens the presenter window on the deck, or with `--powerpoint`
  the live PPTX (`docs/design.md`, section 8). The presenter takes `?bundle=<id>` as a click on
  the deck's *Present* and drops it from the address, so a reload goes back into the lecture as
  before. Every build has the stage PDF now (`--no-stage` leaves it out, `--stage` is still
  taken): every deck of the server can be presented either way. `texstage serve` stays for the
  server alone.

## 25. The deck page: folders, names, off the list (2026-10-13)

- **Why:** a laptop's server lists every deck built on it - 19 on 2026-10-13, the keynote the 12th,
  below the window, and the page did not scroll (since the same day `main` scrolls while it shows
  a page; the presenter fits as before). The lecturer asked for deleting decks, folders, moving.
- **Folders** (`server/library.py`, `<data>/library.json`): per lecturer, nested; a deck is kept
  by its deck ID, so its folder and its shown name stay when it is built again. The page opens
  folders like a file browser, with the path above (*All decks* › ...); *New folder* makes one in
  the folder shown. Deleting a folder moves what it holds up to its parent - no deck is deleted;
  a folder cannot go into itself or into one of its own (400).
- **Moving:** a card's ⋯ › *Move to …* (a list of the folders - for a finger as for a mouse), or
  the card dragged onto a folder or onto a step of the path. A `.bundle.zip` dragged onto the page
  is still an upload: a move drags text, an upload a file.
- **Rename:** ⋯ › *Rename …* gives a deck a name of its own on the page (`label`); its own name and
  its deck ID stay below it; an empty name, or its own, brings that back.
- **Search and order:** the search field goes through all folders (folders by name, decks by shown
  name, name and deck ID; each hit says where it is); *By name* or *Newest first* is kept with the
  presenter's preferences (`deckSort`), the open folder per tab (`texstage:folder`).
- **Off the list, or deleted:** ⋯ › *Remove from the list …* for a deck built on this computer (a
  lecture's `build/texquiz`, a folder the server was started with, or a served copy of one): the
  library notes when (`hidden`); its builds up to then are no longer listed, a newer build is. The
  build folder is never deleted (the lecturer's choice), and a whole deck leaves the list, not one
  build - else an older served copy would take its place. ⋯ › *Delete …* for a deck this lecturer
  uploaded: `DELETE /api/decks/<deck>` deletes its builds in `bundles/<lecturer>/<deck>/` (and takes
  the laptop's builds of the same deck, if any, off the list). A game that plays one of those
  builds refuses the delete while it is under way (409: active within `stale_ms`); one left over
  from an earlier lecture ends first (`Engine.end`, what a new game of the deck would do - its
  results, ink and pages stay in the archive). An upload lists the deck again: its build time comes
  from the zip and may be older than when it was taken off.
- **API** (for hosts: the presenter key or a paired device; each lecturer sees and changes only
  their own library): `GET /api/decks` gives each deck `folder`, `label` and `uploaded` (what
  *Delete* does); `GET|POST /api/folders`, `PATCH|DELETE /api/folders/<id>`, `PATCH|DELETE
  /api/decks/<deck>`. A server older than this answers `/api/folders` with 404: the page then lists
  the decks without folders, so a reload during a lecture works with either.
- **Tested:** `tests/test_library.py` - the library, the API, a laptop's deck off the list and back
  with its next build, an uploaded deck deleted (refused while its game runs, its stale game ended)
  and uploaded again, two lecturers apart; in the browser pane on a test server with 19 decks: a
  folder made, decks moved by the menu and by dragging (onto a folder, onto the path), renamed,
  searched, sorted, one taken off the list, the folder deleted, *Present* as before - no console
  or server errors.
