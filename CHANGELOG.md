# Changelog

## Unreleased — 0.2.1.dev3 candidate

- *Record*: once the screen is chosen, the recording waits in the top bar, not
  started and without a file - the screen as a live miniature (larger under the
  pointer), the microphone's level, *● Start* and ✕ -, so that whatever needs it
  is put right first; the dialog's miniature and its *Start recording* are gone.
  The screen can now be chosen before the lecture and *● Start* clicked when it
  begins. *● Start* records into the game open then; a refused start leaves it
  waiting; ✕, or the screen going away, lets the screen and the microphone go.
- A full-screen presenter window is full screen again after the choice: in a
  lecture, sharing an entire screen took it out of full screen (Chromium on
  Windows: as the capture starts, its "is sharing your screen" bar takes the
  focus, on the primary display), and only a click may bring a page back - at
  once while the click that opened the browser's dialog still counts (93f7ac7),
  else with *● Start*, ✕ or *Cancel*; a window that was not full screen stays so
  (`tests/test_browser_recording.py`, `tests/web-client-record.test.cjs`).
- The deck page helps find today's deck:
  - A card shows the deck's first slide and when you presented it last
    (*presented today, 10:14*, *presented 12 Nov*); the build time lost its
    seconds. *Recently presented* is a third order besides *By name* and
    *Newest first*.
  - Where a deck's lecture runs, its button says *Continue* (its tag the PIN);
    a lecture left for hours shows neither - the next opening is a new one. The
    host console's *Resume* follows the same rule.
  - *Remove from the list* asks first when the deck's lecture runs (it goes
    on), and the deck comes back: *Undo* in the notice, or *Put back* in the
    list of removed decks below the cards (`GET /api/removed`,
    `PATCH /api/decks/<deck> {"listed": true}`). Before, only the deck's next
    build brought it back.
  - On a phone (a paired device), a card with a tag squeezed its name to a word
    per line; its tags and buttons now go below the text.
  - The illustrated manual's *Choose a deck* describes the page as it is now -
    with the deck menu's *Lectures* and *Builds* and the decks a server does not
    play.
- The illustrated manual's 19 screenshots are new, from one session of today's
  texstage (they were from 27 October). The text follows the windows: the
  presenter's top bar keeps *After the lecture*, *Results (CSV)*, *New game* and
  *Decks* in its three-dot menu, and a question's *Pause*, *+10 s* and *Stop the
  question* sit at the foot of the slide.
- Browser smoke tests (`tests/test_browser_smoke.py`), the review's next step
  after the lecture room: Playwright drives a real browser - the installed
  Chrome, nothing downloaded - against a real server on a free port. A phone
  joins, types 6,5 with the ± key and sees the reveal; a phone rejoins after
  *New game* in one tap, and the old PIN gets the new one; the presenter
  pauses a question with a slow click while 40 answers stream in; the
  projector window's → waits behind *Reset the timer?*; *Decks* in an outage
  says so and comes back with the server. Each of them failed on the code
  before the lecture-room fixes. Playwright is a new dev dependency
  (`requirements/dev.txt`); CI runs the tests in the runners' Chrome and fails
  instead of skipping them. The fake test deck can have a real stage PDF
  (`make_bundle(stage="pdf")`).
- The lecture room, after a critical review of texstage (its first package):
  - One game left open whose build is not on the server any more (its folder
    gone, a kind missing) - with a question closed and not revealed - stopped
    the clock of every game: questions stayed on *Get ready* and never closed
    at their time, and nothing was logged. The clock now goes game by game,
    a game that fails is logged once, and the server says at start which games
    wait for their build.
  - The presenter's ⏸, +10 s and ⏭ on the slide - and the host console's
    rename, remove and quiz buttons - lost clicks while answers came in: the
    pushes drew them anew under the pointer, five times a second. They are
    drawn only when they change, and the host console's lists wait while a
    pointer is down in them.
  - After *New game*, the phones say *Join the new game*: one tap, the new
    PIN and the same nickname. A phone with the old PIN (the QR code, *Join
    again*) is told the game is over and given the new PIN, for two hours,
    instead of *No game with this PIN* - which counted towards the limit of
    300 wrong PINs per address and ten minutes: through the tunnel, a lecture
    hall shares one address and could lock itself out.
  - After a restart in the middle of a question, the first phone back to
    answer closed it for everyone ("everyone answered" counted only the phones
    connected). Phones that drop - every phone, when the server starts again -
    are now waited for 30 seconds.
  - A numeric question without min and max: an empty *Submit* sent 0, an
    iPhone's keypad has no minus, and a typed 3,5 could be lost. The field now
    takes 3,5 and 3.5, has a ± key, and *Submit* waits for a number.
  - Keys reached the game behind dialogs: the projector window's → moved the
    game while *Reset the timer?* was open, and one Enter answered a message
    and the question under it. Only the top dialog takes keys now, and Enter
    on *No* means no.
  - *Decks* clicked while the server could not be reached left a dead
    presenter (a dialog per queued command, errors every frame, a reload
    needed). It now says the server cannot be reached and tries again by
    itself; one dialog per error.
  - An error in one phone's view stopped the push for the phones after it,
    and the lecturer's command answered "internal". The others now get theirs,
    and it is logged.
  - The deck's *Lectures …* listed the newest 200 ended games, empty ones
    too: with thousands of empty games (two builds' windows ended each other's
    games until 2026-10), not one lecture was listed. Only games that left
    something - or files in the archive - are listed now.
- Recording, after a review of it:
  - The Record dialog shows the chosen screen live as a miniature before
    anything is recorded (*Choose the screen …*, then *Start recording* or
    *Choose another …*), so the presenter's own screen, with its notes and
    the next step's answers, is not recorded by mistake. Where the browser
    allows, it says first on which screen the projector window is.
  - *Also record the computer's sound (the deck's videos)*: unticked each
    time the dialog opens. The browser gives it for an entire screen
    (Chromium on Windows and ChromeOS), and it is mixed with the microphone
    into one track.
  - A recording that stops by itself - the projector window closed, the
    display changed, *Stop sharing* - says so in the top bar until
    dismissed, with *Record again*. Before, it looked like a normal save,
    and the note went after 30 s.
  - The top bar warns when the microphone has heard nothing for 30 s while
    recording, or when it is gone (unplugged).
- A deck's lectures and builds on the deck page (the review's second
  package), under a deck card's ⋯:
  - *Lectures …* lists the deck's games, open and ended, with what each
    left: players, questions asked, ink, polls, questions, and what its
    archive holds. For each: *Results (CSV)*, *Archive (ZIP)*, *Make the
    PDF* (from the stored ink, kept in the archive), its recordings, and
    *Delete …* for an ended one (its rows and its archive folder). Before,
    an ended game's results were out of every window's reach.
  - *Builds …* lists every build of the deck on the server, with when it
    was built, where it is from and its games. *Present* goes back to an
    older one (asking first where a game would end), *Download* gives its
    `.bundle.zip` for another server, and *Delete …* removes an upload.
  - Routes: `GET /api/decks/<deck>/lectures`, `GET /api/decks/<deck>/builds`,
    `GET /api/bundles/<id>.zip`, `DELETE /api/bundles/<id>`,
    `GET /api/archive/<game>/ink`, `DELETE /api/archive/<game>`; results,
    archive ZIP, files and the annotated PDF also for ended games.
  - Fixed on the way: `texstage publish` (and a build's upload to another
    server) left out the activities' seed files (`data/<hash>.sql|.ttl`), so
    a hosted server's copy was incomplete; and in windows up to 1350 px wide
    the presenter's top-bar rule hid the deck cards' ⋯ buttons.
- Decks without silent surprises (a review of deck management):
  - Before a build ends the deck's running game on another build - a rebuild
    in the break, opened with `texstage present` - the presenter window asks:
    the game's PIN, players, questions asked and ink, and that the phones
    would join again with a new PIN. *Keep the running build* leaves it.
  - Every game that ends writes its results, polls, questions and sketches to
    the lecture archive. Before, only *Make the PDF* and *Download the
    archive* did, and an ended game's results were out of every window's
    reach.
  - The deck page lists the decks the server does not play, with why (a kind
    it lacks, a broken `deck.json`; `GET /api/skipped`), and the server's log
    says when it finds a new one. The presenter opens a build that
    `texstage present` names but the list does not show (an older build, a
    deck taken off the list), and says why when it cannot.
  - `texstage present` on a port where a server runs says which of its
    options that server does not take (`--activities`, `--tunnel`,
    `--public-url`, `--host`, further folders), whether that server has the
    deck's build or why not, and when the build would end a game with
    players.
  - `texstage present deck.tex` looks at the deck's own build: the decks of
    one folder share its `texquiz-out`, and another deck's build there made
    it present that deck instead.
- Presenter view, after a review of it: a lost connection is said across the
  window, not by a dot alone; the Activities panel shows the activity of the
  slide and stands in the column, with the notes below it, instead of over
  the next slide and the notes; in the overview the arrow keys choose a frame
  and no longer move the projected slide; a running round's buttons stay to
  be seen, also on a tablet; the notes come as text; the slide takes the room
  the window has, the column what is left; in a narrower window the buttons
  of before and after a lecture fold into one, and the join address stays
  whole; Esc closes the poll dialog; a reference is named by its group, not
  its key; buttons say what they are and whether they are on.
- Speak the deck's language everywhere, English or German: shared message
  catalogs (`web/i18n/`) for the live views, the phones, the presenter,
  projector and host windows and the PowerPoint add-in. Phones follow the deck
  instead of their browser; the join slide's QR code names the language.
  Pages without a deck use the browser's language.
- German defaults for the slides' own texts (texquiz's `\quizsetup` texts,
  texactivity's labels), chosen by Babel's main language; `\quizsetup` values
  still win. Typed polls get their title and yes/no answers in the deck's
  language.
- Server refusals carry codes (WebSocket `error`, HTTP API `code`) that the
  windows and phones translate; new codes for votes on one's own or answered
  questions, poll and whiteboard limits, empty activity fields and the deck
  library. German phone texts now use "Sie", as the slides do.
- Keep a presenter key stored in the browser when the presenter window or the
  host console reloads. It was deleted as "not accepted": the start ran before
  the script's constants were set, and any failure at the start forgot the
  key. Now only the server's refusal forgets it.
- Update public-source installation, SQL activity restrictions, PowerPoint
  command guidance and release status; correct screenshot provenance.
- Regenerate the Markdown, LaTeX and PDF manuals from their shared source.

- Preserve the deck language from Babel/Polyglossia in the bundle. German
  decks use German live labels in the presenter and projector views.
- Retain compatibility with older language-free TQZ records and English
  fallback for unsupported languages. Ported from lecture-tools 97a3317.

## Earlier 0.2.1.dev2 candidate

- Added the lazy `compile_latex` API and `LatexResult`, supporting pdflatex
  and latexmk, source-relative includes, output/job names, bounded reruns
  and captured diagnostics without selecting a theme or content mode.
- Routed live-deck and plain PowerPoint compilation through the same runner.
- Added compiler, chapter compatibility and installed-package checks.

## Earlier 0.2.1.dev1 candidate

- Moved plain Beamer-to-PowerPoint conversion from lecture-tools into
  Texstage, with `texstage pptx` and the lazy `convert_beamer_to_pptx` API.
- Reused the live deck's slide writer while preserving fitted images, notes,
  overlay order, output paths, resolution options and legacy two-pass mode.
- Refuse to overwrite retained conversion artifacts; clean generated
  artifacts on failure unless explicitly kept.

## Earlier 0.2.1.dev0 candidate

- Normalize inline activity references and seeds to LF line endings across
  LaTeX versions, preserving indentation, comments and literal escape sequences.
- Reload lecturer keys after an atomic file replacement even when its timestamp
  matches the cached file, including same-size key renewals.

- Converted the manuals and references to portrait LaTeX articles with serif
  text, continuous sections, multipage tables and wrapped code.
- Unified the downloadable manual PDF and native LaTeX build, preserving all
  presenter and phone screenshots.

- Added a source-reviewed LaTeX package/command reference to the shared manual,
  a standalone reference page, compiled authoring examples and CI coverage checks.

- Extracted the standalone runtime, server, browser assets and four generic styles.
- Added the supported lazy `texstage.api` facade for companion integrations.
- Added hashed runtime/build/development locks, CI, source-archive rebuild checks
  and an installed-wheel smoke check.
- Added installation, development, contribution and release documentation.
- Added an illustrated user manual in Markdown and PDF, 19 screenshots of a
  synthetic session, a runnable manual demo, and locked PDF build dependencies.
- Added an editable LaTeX edition of the same manual, with shared screenshots,
  standalone latexmk build instructions and a CI compilation check.

This candidate has not been published. DBIS styles and course commands are owned
by the companion lecture-tools project. Publication rights for retained developer
utilities and hosted/platform validation remain release prerequisites.
