# Changelog

## Unreleased — 0.2.1.dev8 candidate

- A build records what it warned of in its `built.json` (`"warnings"`, beside
  its time; a build without warnings writes the file as before), and
  `texstage present` says them again before it opens the build it presents -
  the deck's newest, a build folder itself, one it built just now. Before,
  only the build's own output said them: a lecturer who had not read it, or
  presented a build made days before, presented ?? unwarned. The record is
  no part of the bundle ID, its copies keep it, and servers read the time
  alone, so the servers of 0.2.1.dev7 take such builds as they are.
- The load runs count a run's worker ends, not their teardown's: the runner
  read the server's log after killing its processes, and a pool that still
  ran logged those kills as deaths (CI on 2d3d4ee, Ubuntu 3.13).
- `docs/integration.md` names no pair any more: lecture-tools records the
  texstage it was tested with (its `requirements/texstage.json` and
  `texstage-assets.lock.json`), so a pairing changes nothing in texstage.
- texstage is 0.2.1.dev8: the warnings said again at present (above), where
  0.2.1.dev7 - the one lecture-tools 0.1.0.dev8 pins - has them not. The
  kinds' packages still need 0.2.1.dev4 or later.

## Earlier 0.2.1.dev7 candidate

The fixes of a review of F2's packages 12 to 14 and of KG's four activities on
the core's type (2026-11-19), which found F2 not ready for a class.

- With the core's activity type, a phone shows an activity's step until the
  quiz shows something after it - a reading, a question, its result. Before, a
  closed or revealed activity stayed on every phone through every later quiz's
  reading, "Answer sent", result and leaderboard; only the open question got
  through (KG's chapters 02, 03 and 05 had it after each of their activities).
  A step that runs (open or paused) shows as before, and one closed or
  revealed after the quiz shows over it. Which came last is a count of the
  game's, not a time - kept with it, so a restart changes nothing a phone
  shows -, and the same slide sent again moves it not. A phone that joins a
  new game - New game, the join slide after the podium - keeps no step of the
  one before.
- A server of the core's type starts whatever its tables hold: a row of the
  core's tables that does not read is left out, logged, and its game loads all
  else - and so writes nothing over what it has. A worker pool that cannot
  start - psutil missing, no job object - is a broken one: the server and its
  quizzes run, the activities' entries are not checked, and the windows say
  why. Before, either stopped `texstage serve` and `texstage present` with a
  traceback.
- A deck prepared again whose preparing fails, or whose reference could not be
  run this time (a worker that died), leaves a game the references' results it
  has; before, the panel's marks, the phones' verdicts and the archive's lost
  them.
- A build warns when pdflatex left the slides or the stage PDF unsettled - its
  last pass still asking for another, or references undefined (?? on the
  pages). On Windows the stage compile could get its output folder in the
  extended-length form, from which pdflatex read nothing back, and shipped
  every reference as ?? without a word (KG's 01-Intro: 137 on 46 pages);
  pdflatex now gets plain paths.
- `texstage publish` and `texstage build --server` send a deck whatever kinds
  the publishing machine has: the server judges it, and a deck it refuses is
  said with its reason while the others still go.
- The load tools: the budget table counts what never came as over budget,
  takes "unchecked" as no verdict, and holds the counts, the simulator's exit
  and the pool's health - a run that lost entries or phones, or broke the
  pool, no longer says "held". The load test holds each text's status, the
  verdict's 3 s and at most one end by the watchdog (077ec93 had let any
  number pass); a worker's end says its CPU time. `tools/load/groups.py`
  compares the core's groups with F1's for the same entries.
- With the core's activity type, a triple whose check could not be made - a
  worker that died, say -, sent again as the phone and the manual tell the
  student, is that entry again and is checked again; before, it was refused as
  sent already. Spaces around a field no longer make another entry, the
  phone's "n of the limit" counts as entering does (one taken back gives its
  place back), a crowd graph's fields offer the edges' labels the projector
  draws too, not its nodes alone, and an entry that counts no more - replaced,
  or taken back - has no verdict on the phone. A text the pool set aside (it
  ended a checking process twice) says it cannot be checked here, rather than
  "send it again", which the server refuses for it.
- A game keeps its references' results with them through a restart, not their
  keys alone: a stale game's reveal and archive show the reference's result
  again.
- At the reveal with `solution=show` the reference's card and a group shown
  after it stand beside the bars, or below them in a tall box, rather than
  over them; and the card's rule no longer frames a playing video.
- The presenter window's texts say what the core does: Block holds for the
  rest of the game, in every activity, and is undone under the Last acts of
  the activity where it was made, which list a block that holds however many
  acts came after it; Reset makes an activity ready again - it opens with O,
  or when a page of its frame before its reveal comes to the projector, unless
  it opens by hand -, and hidden groups, merges and blocks stay. The panel's
  refusals of a group, term or act that is not there have codes of their own
  (no-group, no-term, no-act) and come in the window's language; two German
  texts are idiomatic now.
- The manual says how to switch between the core's type and F1's (end the
  lecture first, and open the windows again), what +30 s and the host
  console's counts do, what `\reveal<n>` does for an activity never opened,
  and that Oxigraph's SPARQL errors give the right line but sometimes
  misleading words. `--workers` says how the default is counted (the physical
  cores less two, at least one, two spares and one that normalizes), and the
  Docker files pass it. A worker's memory is about 25 MB at rest and about 67
  MB at its peak while it checks; a check may take up to 1 GB before it is
  ended.
- `texstage pdf` says the references it left undefined, as a build does; a
  build whose deck publish cannot read says why it was not sent.
- texstage is 0.2.1.dev7: the review's fixes (above), where 0.2.1.dev6 - the
  one lecture-tools 0.1.0.dev7 pins - has them not. The kinds' packages still
  need 0.2.1.dev4 or later.

## Earlier 0.2.1.dev6 candidate

- The activity framework's core is the default activity type: `texstage serve`
  and `texstage present` run it unless they are started with `--activities f1`,
  which keeps F1's type until a class has used the core. A server checks every
  entry in worker processes it starts with itself, for a deck of quizzes alone
  too - by default the physical cores less two, two spares and one that
  normalizes; `--workers` sets how many. It needs the kinds' packages a deck
  names where it runs, as the build does, and skips a deck of a kind it lacks,
  naming the package - a deck built before kinds were named too, by its items'
  inputs. It plays decks of choice, number and text activities, and `texstage
  build --server` and `texstage publish` send them to another server: with F1's
  type the default they were left out, by the build without a word. At the
  reveal the projector shows the reference and its result unless the activity
  says `solution=mark` (F1's type marked the reference's group only). An
  earlier lecture's game of F1's type goes on in the core's. `--checks` is for
  F1's type alone: `texstage serve` says so when `--checks browser` or `both`
  is given without `--activities f1`. `texstage present` says when the server
  that runs already - one started before - runs F1's type. The load runs
  default to the core's type.
- With the core's activity type, an earlier lecture's game keeps its
  references' results through a restart of the server: the reference's group
  stays marked, the phones keep their verdicts, and the lecture archive -
  written when the next lecture opens the deck - has them. Before, a game idle
  for six hours or more lost them when the server started again, since a
  starting server does not prepare such a game's deck; a game moved from F1's
  tables takes the results F1 kept.
- The load runs (`tools/load/run.py`) and `tools/simulate.py` play a server of
  the activity framework's type too - the load runs by default, as `texstage
  serve` runs it (`--activities f1`: F1's), the simulator whichever type the
  server's welcome names: the phones send its
  entries and load the kinds' files their welcome names, and a projector's and
  a presenter's window count the picture's updates a second against the
  design's budget of four.
- texstage is 0.2.1.dev6: its default activity type is the core's (above), where
  0.2.1.dev5's - the one lecture-tools 0.1.0.dev6 pins - is F1's. The kinds'
  packages still need 0.2.1.dev4 or later.

## Earlier 0.2.1.dev5 candidate

- With the core's activity type, the presenter window says in words of its own
  what the activity framework refused a control or an act for, in the deck's
  language - an activity that is revealed and has to be reset first, a merge
  that would merge two terms into each other, more acts than a game takes and
  the like. A German window said these in the server's English after *Das hat
  nicht geklappt*, and a few in a quiz's words (*This question is closed.*).
- The manual has a page on running a live activity with the core's type -
  the panel, its keys, what the phones show -, the activity keys on the
  shortcut card, live activities in the participant quick reference and in
  troubleshooting, and on the SQL page where a submission runs: on the server
  with the core's type, in the presenter's browser with F1's unless `--checks
  server`. The design documents of the live activities and of the
  activity framework say what its stage F2 built, and what it left to F3.
- The deck list no longer stops the server: it looks at the build folders in a
  worker thread and reads only those whose files changed (a lecture's phones
  waited 0.5 to 2 s at every deck list). The deck page and the host console
  show a deck built meanwhile by themselves. A build's time is its own
  (`built.json`, which its copies keep): an old build copied again is not the
  newest.
- Rollback from the command line: `texstage present <build folder>` presents
  that build - a `<name>.bundle`, a server's kept copy, an upload. *Builds …*
  says what changed since the build before. The host console asks, as the
  presenter window does, before a new build ends a game with players.
- *Lectures …*: *End lecture …* ends the open game at once (its archive written,
  its PIN free, an upload deletable right away); *Continue* takes up an earlier
  lecture's ink and whiteboard pages, any one of the build, not only the last.
- The deck page: *Select* moves or removes several decks at once (*Move to …*
  makes a new folder on the spot), several files go up in one upload, the intro
  folds away, a card's menu goes by the arrow keys, build times lose their
  seconds; the host console's list shows the lecturer's names and folders.
- *Storage* on the deck page and `texstage data` show what the decks hold on the
  server; `texstage data clean --before DATE` removes ended lectures, their
  recordings or copies kept for games - listed first, deleted with `--yes`,
  never an open game's. Nothing is deleted by itself but, as before, a
  deck's builds beyond its newest ten.
- A choice's options are in its box on the slide - handout, solutions,
  PowerPoint -, each with its shape in its colour and as the phones show it
  (a formula typeset, `first_name`, `x^2`, `R&D` or `x < 5` as written), so
  that the prompt need not repeat them; the projector's bars of a choice show
  the shapes too. A box too small for what it shows draws it smaller, inside
  it, and the build's log says so. Past six options the shapes and colours
  repeated (options 4, 10, 16 and 22 were green squares): from seven options
  on every option carries its letter, A to Z, inside its shape - on the
  phones (where a screen reader says it), the projector's bars and the
  slide. A choice of up to six looks as before.
- `tolerance=` without a reference: a number activity judges nothing, and the
  build now warns of it. A kind's build may give warnings of its own
  (`Built.warnings`, each a line), which the build prints with the activity's
  id; the kit holds them against a fixture's.
- A server compares a kind's version as PEP 440 orders them: development and
  pre-release numbers count (0.1.0.dev4 < 0.1.0.dev5 < 0.1.0a1 < 0.1.0rc1 <
  0.1.0 < 0.1.0.post1), and so do an epoch (another line, as another major
  version) and every number of a release, so a deck built with a kind's later development
  release is refused by a server with an earlier one, as with a later
  release.
- texstage is 0.2.1.dev5: a kind's package whose build gives warnings needs
  it (`texstage>=0.2.1.dev5`), as 0.2.1.dev4's `Built` has none. The kinds'
  packages beside texstage give none and still need 0.2.1.dev4 or later. A
  deck with activities of texstage's own kinds gets a new bundle ID when it is
  built again, as deck.json names the texstage of its kinds; a server of
  0.2.1.dev4 still plays it, as it compares a kind's version by its numbers.

## Earlier 0.2.1.dev4 candidate

- A new presenter key - a server's own (`presenter-key` in its data folder)
  and a lecturer's (`texstage lecturer add | renew`) - never starts with `-`:
  one in 64 did, and on a command line `--key -Abc` reads as an option, so
  `texstage build`, `serve`, `publish` and `retarget` stopped (*argument
  --key: expected one argument*). A key made before stays as it is: the
  authoring guide and texstage's hints write `--key=<key>`, which takes it,
  and that error now says so.
- texstage is 0.2.1.dev4, the first candidate whose version says that it has
  the activity framework's contract: the kinds' packages
  (`kinds/texstage-kinds-rdf`, `kinds/texstage-kinds-sql`) need it
  (`texstage>=0.2.1.dev4`), which `pip check` holds - wheels named 0.2.1.dev3
  were built with the contract and without it. A deck with activities of
  texstage's own kinds (choice, number, text) gets a new bundle ID when it is
  built again, as deck.json names the texstage of its kinds; a server compares
  a kind's version by its numbers, so none refuses such a deck.
- The kinds' dependencies are locked with texstage's
  (`maintenance/lock_dependencies.py` reads `kinds/*/pyproject.toml`). CI builds
  and checks the kinds' wheels beside texstage's, builds a deck with an
  activity of each of texstage's kinds from the installed wheels, and has a
  server of the core's activity type - from the wheels, and in the server's
  image - check a phone's entry of each (`maintenance/check_kinds_served.py`).
  The installation guides, the README's and the showcase's install the kinds;
  a build that misses one says how to install it from texstage's source.

## Earlier 0.2.1.dev3 candidate

- Every page sends a Content-Security-Policy (`server/policy.py`): scripts come
  from the server alone and a page connects to it alone - the phone's page
  loads the least; the presenter's and the projector's windows also take
  YouTube's and Vimeo's players and a deck's video files from their addresses,
  the add-in Office.js. Every script carries a policy for when it runs as a
  worker, so a kind's file reaches nothing that way. Another site may no
  longer frame the presenter's window, the projector's or the host console.
  What a policy refuses is reported to the server, whose log says it once
  (`policy: the page ... refused ...`).
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
