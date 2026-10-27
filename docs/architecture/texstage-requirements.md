# texstage - requirements

Status: 2026-10-06, from the requirements interview with the lecturer; input for the design
(`texstage-design.md`). **texstage** is the presenter and the system around it; *texquiz* stays
the name of the quiz part (the LaTeX package and the game).

## 1. Goal

A browser-based presenter for Beamer PDFs that replaces PowerPoint as texquiz's presentation
surface: slides, speaker notes, ink, laser pointer and the live quizzes in one system that runs
on every platform and can be released as open source. PowerPoint stays an export
(`texstage build` keeps producing the PPTX).

Why: PowerPoint is the only part of today's chain that is neither open nor cross-platform, it
needs an add-in per PC, and it shows the slides as pictures. The browser can render the Beamer
PDF itself (PDF.js), take pen input with pressure (Pointer Events), and already runs texquiz's
live views (the host page).

## 2. Decisions from the interview

| Topic | Decision |
|---|---|
| Users | DBIS lecturers first; designed so that it can be released as open source later |
| Input | Beamer PDFs built by lecture-tools (texstage present build), with quizzes and `\note` scripts |
| Setups | laptop + projector; Wacom pen on the laptop; iPad as presenter and ink surface; hybrid and recorded lectures |
| Timeline | no fixed date - built properly; PowerPoint remains the fallback meanwhile |
| Build first | replace PowerPoint: the presenter core with today's quizzes |
| Hosting | both: on the laptop (offline-capable, phones and iPad via room network or tunnel) and on a hosted server |
| Platforms | Windows (Edge/Chrome), macOS, Linux, iPad Safari |
| Integration | part of texquiz in lecture-tools: one server, one build |
| Students | quizzes only - no live slide following on their devices |
| Recording | lecture-hall capture and screen sharing of the projector output; in-app recording to a video file (projector + microphone, no camera) |
| After the lecture | annotated PDF for students; quiz results bundled with it per lecture |
| New quiz features | ad-hoc polls, student Q&A, sketch answers |
| Q&A | questions and votes only in the presenter view; the lecturer puts a selected one on the projector |
| Notes | both: the notes page as Beamer typesets it by default; a reflowing text view as an option for small screens |
| Annotated PDF | one page per frame (its last overlay step) with all of the frame's ink |
| Phone content | text with inline math (`$...$`, rendered with KaTeX) for everything that does not come from LaTeX |
| Rebuilt deck | ink starts fresh: it belongs to one lecture and one build; that lecture's annotated PDF keeps it |
| Name | texstage (texquiz stays the quiz part) |
| Licence | Apache-2.0 at release |

Not chosen (out of scope for now): students following the slides live or taking private notes;
keeping ink for the next lecture or year; ink replay synchronised with a recording; camera
picture in the recording; automatic upload to Opencast or RWTHmoodle.

## 3. Functional requirements

### 3.1 Presenting (milestone 1)

- **P1** Load a deck from a texstage build: the Beamer PDF and the build's metadata; render the
  pages as vectors with PDF.js.
- **P2** Overlays are steps of one slide: navigation steps through a frame's overlay pages; the
  slide number is the frame number, as in the footline; the overview shows one tile per frame.
- **P3** Two windows: a **projector window** (full screen, no UI at all, 16:9) and a **presenter
  window** (current step, next step, notes, timer, controls).
- **P4** Notes: the Beamer `\note` script of the current frame (Script and Background), shown as
  Beamer typesets it; a reflowing text view as an option for small screens.
- **P5** Timer: elapsed time, wall clock, optional target duration with a warning.
- **P6** Overview and jump: a grid of all frames; jump by click or by typing a number; never
  visible on the projector.
- **P7** Black or freeze the projector.
- **P8** Keyboard and clicker: arrows, PageUp/PageDown, Space; keys for black, freeze, overview,
  pen, pointer - PowerPoint's keys where they exist.
- **P9** Quizzes as today, driven by navigation: join lobby, reading slide, countdown, reveal,
  leaderboard, podium; all question types (polls, word clouds, numeric, ordering ...); results as
  CSV.

### 3.2 Ink and pointer (milestone 2)

- **I1** Pressure-sensitive pen (Wacom via Windows Ink, Apple Pencil; mouse as fallback),
  highlighter, eraser (also the pen's eraser end), colours and widths, undo/redo, clear.
- **I2** Ink belongs to the frame: it stays when the next overlay step appears and when the
  lecturer comes back to the slide.
- **I3** Ink appears on the projector while it is drawn.
- **I4** Laser pointer: follows the mouse or the hovering pen, with a short fading trail; shown on
  the projector.
- **I5** Zoom into a region on the projector, and draw on the magnified slide.
- **I6** Whiteboard pages: insert a blank or grid page on the fly; it gets a place in the overview
  and in the annotated PDF.

### 3.3 iPad as presenter (milestone 3)

- **T1** The laptop drives the projector; the iPad runs the presenter window over the network.
- **T2** Pairing: the iPad becomes a presenter device by scanning a code on the laptop (one-time
  token); students can never pair.
- **T3** Ink, pointer and navigation from the iPad appear on the projector, over the room network
  or the tunnel.

### 3.4 After the lecture (milestone 4)

- **A1** Annotated PDF: one page per frame (its last overlay step) with the frame's ink as
  vectors, plus the whiteboard pages - ready to upload for students.
- **A2** Per lecture, the annotated PDF and the quiz results (CSV) are saved together.

### 3.5 Recording and hybrid (milestone 5)

- **R1** The projector window is clean and shareable as one window - for the hall's capture
  system and for Zoom/Teams screen sharing.
- **R2** In-app recording: a video file of the projector output (slides, ink, pointer, quizzes)
  with microphone audio; start, pause, stop; no camera.

### 3.6 New interaction (milestone 6)

- **Q1** Ad-hoc polls without LaTeX: yes/no, A-D, scale, word cloud, or a typed question;
  phones and projector show text with inline math (KaTeX).
- **Q2** Student Q&A: anonymous questions with upvotes, visible in the presenter view only; the
  lecturer puts a selected question on the projector.
- **Q3** Sketch answers: students draw on the phone; the presenter view shows a gallery; the
  lecturer puts selected sketches on the projector; sketches are part of the lecture's results.

## 4. Non-functional requirements

- **Offline:** presenting on the laptop alone (projector and presenter window) works without any
  network; phones and the iPad need the room network, a hotspot or the tunnel.
- **Latency:** a slide change in under 100 ms; local ink within one frame; ink from the iPad on
  the projector in under 50 ms on the room network, best effort through the tunnel.
- **Robustness:** a reload or reconnect loses nothing; a restarted server resumes the deck, the
  position, the ink and the game (as texquiz's games already do).
- **Security:** only paired presenter devices control the deck; students only answer quizzes and
  post questions; lecturers on a hosted server see only their own decks (as today).
- **Browsers:** current Chrome, Edge, Firefox and Safari; Safari on iPadOS. Chromium-only
  accelerations (low-latency canvas, delegated ink trail) are enhancements, not requirements.
- **Fidelity:** the projector shows the PDF as the PDF viewer would - vector text, the deck's
  fonts, 16:9.
- **Licence hygiene for Apache-2.0:** every dependency must be compatible. PDF.js (Apache-2.0),
  perfect-freehand (MIT), pdf-lib (MIT), Starlette, uvicorn, segno, lxml (BSD), Pillow (HPND) and
  python-pptx (MIT) are. **PyMuPDF is AGPL-3.0 or commercial**, and the texstage build depends on
  it today: before the release, replace it (e.g. pypdfium2, Apache-2.0/BSD) or make it optional.

## 5. Milestones

| | Milestone | Done when |
|---|---|---|
| M1 | Replace PowerPoint: P1-P9 | one chapter of a lecture is presented without PowerPoint, quizzes included |
| M2 | Ink and pointer: I1-I6 | a lecture with Wacom ink, pointer, zoom and a whiteboard page |
| M3 | iPad as presenter: T1-T3 | the same lecture driven and inked from the iPad |
| M4 | After the lecture: A1-A2 | the annotated PDF and the results of a real lecture, uploaded |
| M5 | Recording and hybrid: R1-R2 | a recorded lecture as a video file; a screen-shared session |
| M6 | New interaction: Q1-Q3 | one lecture with an ad-hoc poll, Q&A and a sketch question |
| M7 | Open-source release | licence audit done (PyMuPDF), documentation, packaging, Apache-2.0 |

## 6. Left to the design

The user-facing questions were decided in a last interview round (section 2: notes, annotated
PDF, phone content, rebuilt decks, name). Three technical questions are left to the design:

1. **Frames and steps:** where the frame-to-page map comes from - texquiz's build metadata or
   Beamer's `.nav` file.
2. **Recording technique:** compose slides, ink and quiz views in one canvas and record it, or
   capture the projector tab (a permission prompt; browser support differs, notably Safari).
3. **Ink transport:** iPad to projector directly over the room network or through the server;
   behaviour through the tunnel. Related: merging the ink into the annotated PDF in the browser
   (pdf-lib) or on the server.

Answered in [texstage-design.md](texstage-design.md): 1 in section 3, 2 in section 9, 3 in
sections 6.4 and 11.
