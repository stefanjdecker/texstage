// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// texstage's texts in English - every text there is, area by area (i18n.js): the other
// languages' catalogs give theirs over these. A function is a text that names something: a
// count, a name - the other catalogs' take the same arguments.

export default {
  // dates and numbers as the language writes them (Intl)
  meta: { locale: "en-GB" },

  // the views over a slide (shared/live.js): join, question, reveal, answer, leaderboard, podium,
  // a poll typed in the lecture, sketches, the audience's question - and the lecturer's buttons there
  live: {
    joinAt: "Join at", pin: "Game PIN", player: "player", players: "players", answer: "answer", answers: "answers",
    correct: "correct", timesUp: "Time's up!", allAnswered: "All answers are in!", getReady: "Get ready", results: "Results",
    leaderboard: "Leaderboard", noScores: "No scores yet", noAnswers: "No answers",
    rightOrder: "in the right order", inPlace: "in place", pause: "Pause", continue: "Continue",
    extend: "10 seconds more", skip: "Stop the question",
    again: "Ask again (practice) - and the questions after it start anew",
    reveal: "Show the answer",
    audience: "Question from the audience", sketchHint: "Draw your answer on your phone.", qr: "QR code",
  },

  // a live activity's box on the projector and the presenter's slide (stage/activity.js); a code
  // activity's contributions are queries - Turtle texts and their graphs for engine=turtle
  box: {
    code: {
      query: { one: "query", many: "queries", waiting: "Waiting for the first queries …", none: "No queries.", reference: "the reference's result" },
      turtle: { one: "text", many: "texts", waiting: "Waiting for the first graphs …", none: "No graphs.", reference: "the reference's graph" },
    },
    status: { syntax: "syntax error", error: "error", timeout: "ran too long", refused: "not run" },
    yes: "yes", no: "no", result: "a result", graph: ["subject", "predicate", "object"],
    rows: (n) => `${n} ${n === 1 ? "row" : "rows"}`, triples: (n) => `${n} ${n === 1 ? "triple" : "triples"}`,
    students: (n) => `${n} ${n === 1 ? "student" : "students"}`, waiting: (n) => `${n} waiting`,
    more: (n) => `and ${n} more`, others: "others", noTriplesYet: "Waiting for the first triples …", noTriples: "No triples.",
  },

  // the phone (play/play.js)
  phone: {
    pin: "Game PIN", nick: "Your nickname", join: "Join", in: "You're in!", watch: "Watch the screen – it starts soon.",
    ready: "Get ready!", send: "Submit", sent: "Answer sent", waitOthers: "Waiting for the others …",
    timesUp: "Time's up", noAnswer: "No answer", correct: "Correct!", wrong: "Not quite", partly: "Partly right",
    thanks: "Thanks!", points: "points", streak: "streak", rank: (r, n) => `Rank ${r} of ${n}`, paused: "Paused",
    finished: "Game over", yourRank: "Your rank", again: "Join again", gameOver: "This game is over.",
    kicked: "You have been removed from the game.", offline: "Reconnecting …", typeHere: "Your answer",
    several: "Several answers can be correct", tickAll: "Tick all that apply",
    orderHint: "Put them in the right order", practice: "Practice round – no points",
    answerWas: "Right answer", up: "up", down: "down", bonus: "streak bonus",
    answer: "Answer", questionPicture: "The question, as shown at the front",
    waitReveal: "The answer comes next …", reading: "Read the question – the answers come next.",
    draw: "Draw with your finger.", undo: "Undo", clear: "Clear", pens: ["black", "red", "blue", "green"],
    tooMuch: "Too much drawn – undo a few strokes.", quizTab: "Quiz", qaTab: "Questions",
    ask: "Ask a question – anonymously.", yourQuestion: "Your question", askSend: "Ask", noQuestions: "No questions yet.",
    yours: "yours", answered: "answered", upvote: "Upvote this question", asked: "Your question is in.",
    connecting: "Connecting …",
  },

  // a live activity on the phone (play/activity.js); turtle: an engine=turtle activity's words
  // where they differ from a query's
  activity: {
    add: "Add", send: "Send", mine: "Yours", withdraw: "Withdraw",
    of: (n, m) => `${n} of ${m}`, closed: "The activity is closed.", blocked: "The lecturer has closed contributions for you.",
    waiting: "Sent - waiting for the lecturer's computer …", ok: "Your query runs ✓",
    syntax: "Syntax error", error: "Error", timeout: "The query ran too long.", refused: "That is not run",
    match: "The same result as the reference ✓", differ: "A different result than the reference", query: "Your query",
    sent: "Sent.", empty: "Nothing yet.",
    // what the server refuses (server/activity.py's codes)
    tooFast: "Please wait a few seconds before you send again.", tooMany: "No more contributions are taken.",
    duplicate: "You have sent this one already.", fillIn: "Please fill in every field.",
    typeFirst: "Please type your query first.",
    turtle: {
      ok: "Valid Turtle ✓", timeout: "Parsing it took too long.", refused: "That is not taken",
      match: "The same graph as the reference ✓", differ: "A different graph than the reference", query: "Your Turtle",
      typeFirst: "Please type your Turtle first.",
    },
  },

  // what a live activity's evaluation says besides its engine's own words (engines/*.js, run by
  // the presenter window's evaluator in the deck's language): where a syntax error is, why a
  // query is not run - and why the evaluator cannot run (stage/evaluator.js)
  engines: {
    at: (line, column, message) => `line ${line}, column ${column}: ${message}`,
    changesData: "only queries are run - this one changes the data",
    noStatement: "no statement",
    oneStatement: "one statement at a time",
    queriesOnly: "only queries are run: SELECT, VALUES or WITH ... SELECT",
    service: "SERVICE (a query to another endpoint) is not run",
    noTriples: "no triples",
    tooManyTriples: (n) => `more than ${n} triples`,
    notStarted: "the engine did not start",
    workerFailed: "the worker failed",
    noEngine: (name) => `texstage runs no engine ${name}`,
    seed: (name, status) => `the seed ${name}: ${status}`,
  },

  // the server's refusals a person can meet, by their code (server/game.py, server/app.py - the
  // WebSocket's error and the HTTP API's "code") and the client's own (shared/client.js)
  errors: {
    unexpected: (detail) => `That did not work: ${detail}`,
    failed: "That did not work.",
    // joining and playing
    "unknown-pin": "No game with this PIN.",
    nickname: "A nickname has 1 to 20 characters.",
    "nickname-taken": "This nickname is taken.",
    full: "The game is full.",
    "too-many-attempts": "Too many wrong PINs from this network – try again in a few minutes.",
    kicked: "You have been removed from the game.",
    "unknown-player": "Please join the game again.",
    "no-session": "This game is over.",
    "unknown-round": "There is no such question.",
    "not-open": "The question is not open yet.",
    paused: "The question is paused.",
    "not-paused": "The question is not paused.",
    closed: "This question is closed.",
    "already-answered": "You have answered already.",
    // the audience's questions
    "qa-closed": "Questions are closed.",
    "qa-blocked": "The lecturer has closed questions for you.",
    "too-fast": "Please wait a few seconds before you ask again.",
    "too-many": "There are enough questions for now.",
    "qa-own": "Not for your own question.",
    "qa-answered": "This question is answered already.",
    "unknown-question": "There is no such question.",
    // the connection (shared/client.js)
    disconnected: "The connection was lost.",
    ended: "The session ended.",
    replaced: "A newer login in another tab replaced this one.",
    // presenting
    "bad-key": "This presenter key is not accepted.",
    "key-required": "This needs the presenter key.",
    "read-only": "The projector window only shows the slides.",
    busy: "The question has not been revealed yet.",
    "no-round": "No question has been asked yet.",
    "unknown-bundle": "This deck is not on this server.",
    "unknown-quiz": "This deck has no such quiz.",
    "too-many-polls": "This game has had enough polls.",
    "too-many-boards": "This lecture has enough whiteboard pages.",
    "poll-question": "This poll needs its question.",
    // decks, folders, devices, recordings and the archive (the HTTP API)
    "no-deck": "This deck is not on this server any more.",
    "deck-running": "A game of this deck is running – delete it after the lecture.",
    "bad-bundle": (err) => `This is not a deck's .bundle.zip${err?.message ? ` (${err.message})` : ""}.`,
    "too-large": "The file is too large.",
    "not-pdf": "This is not a PDF.",
    "no-stage-pdf": "This build has no stage PDF: build the deck again (texstage build, without --no-stage).",
    library: (err) => `The list of decks did not change${err?.message ? ` (${err.message})` : ""}.`,
    "name-empty": "A name cannot be empty.",
    "name-long": "This name is too long.",
    "folder-cycle": "A folder cannot go into itself.",
    "too-many-folders": "There are enough folders already.",
    "no-folder": "This folder is not there any more.",
    "pair-unknown": "No device is waiting for this code.",
    "pair-expired": "This pairing code is used or expired.",
    "pair-too-many": "Too many unknown codes from this network – try again later.",
    "no-recording": "This recording is not on the server.",
    "recording-unfinished": "The recording is not finished yet.",
    "recording-write": "The server cannot save the recording.",
    "recording-too-large": "The recording is too large.",
    "recording-part": (err) => `The recording's part was not taken${err?.message ? ` (${err.message})` : ""}.`,
    archive: (err) => `The archive did not take it${err?.message ? ` (${err.message})` : ""}.`,
    "local-only": "This works only on the computer the server runs on.",
    // the recording's own (stage/record.js): the browser's recorder stopped - after "Recording stopped:"
    recorder: (err) => `the browser stopped recording (${err?.message || "an error"})`,
  },

  // the lecturer's pages - the presenter window (stage/presenter.js) and the host console
  // (host/host.js) - where they say the same: the presenter key, the decks and their games; a
  // slide's phase (deck.json) and a question's (the server's rounds) as they show them. A text
  // whose arguments are markup - a file name in <code>, a button's name in <b> - goes into the page
  // as HTML, here and in the sections below: no < or & in it.
  lecturer: {
    key: "Presenter key",
    keyWhere: (file) => `The key is in the server's data folder (${file}) and is printed when it starts.`,
    go: "Continue", connection: "connection", decks: "Decks", noDecks: "No decks on this server yet.",
    upload: (file) => `A deck this server does not have: upload its ${file} from the build folder, or drop it here.`,
    quizzes: (n) => `${n} ${n === 1 ? "quiz" : "quizzes"}`, slides: (n) => `${n} ${n === 1 ? "slide" : "slides"}`,
    players: (n) => `${n} ${n === 1 ? "player" : "players"}`, built: (date) => `built ${date}`,
    game: (pin, n) => `game ${pin} · ${n} ${n === 1 ? "player" : "players"}`, pin: "PIN",
    csv: "Results (CSV)", newGame: "New game", newGameAsk: "Start a new game? The players join again with a new PIN.",
    phase: { join: "join", read: "read", question: "question", reveal: "reveal", answer: "answer",
      leaderboard: "leaderboard", podium: "podium", prepare: "prepare" },
    round: { "get-ready": "get-ready", open: "open", closed: "closed", revealed: "revealed" },
  },

  // the presenter window (stage/presenter.js, stage/index.html): pairing a device, the deck page, the
  // tools over the slide, the notes, what the projector shows, polls, the audience's questions, the
  // activities, the sketches and what comes after the lecture. The keys in brackets are the same
  // in every language.
  presenter: {
    roundTrip: "the round trip to the server", close: "Close",
    pairInstead: (devices, pair) => `An iPad or a second computer is paired instead: in texstage on the laptop, choose ${devices}, then ${pair}, and scan the code it shows.`,
    removed: "This device was removed in the presenter window - pair it again.",
    // this device (an iPad) opened the code the laptop shows - in the browser's language
    pair: {
      title: "Pair this device",
      again: (devices, pair) => `Make a new code in the presenter window on the laptop: ${devices}, ${pair}.`,
      asking: "Asking the server ...", unreachable: "The server cannot be reached.", refused: "This code does not work.",
      compare: "In the presenter window on the laptop, allow this device if it shows the same code:",
      waiting: "Waiting for the laptop ...", denied: "The laptop did not allow this device.", expired: "The code expired.",
      device: "a device", browser: "a browser",       // its name in the laptop's list, where its browser does not say
    },
    // the laptop's presenter devices (Devices)
    devices: {
      button: "Devices", buttonTitle: "an iPad or a second computer as presenter", title: "Presenter devices",
      intro: "An iPad or a second computer runs this presenter window too: it steps through the slides, writes and points.",
      paired: (date) => `paired ${date}`, seen: (time) => `seen ${time}`,
      remove: "Remove", removeAsk: "Remove this device? It stops presenting at once.", none: "No device is paired.",
      pair: "Pair a device",
      scan: "Scan this code with the iPad's camera, or open the address in its browser - valid for two minutes, and once.",
      back: "Back", wants: (name) => `${name} wants to present. Allow it only if it shows this code:`,
      allow: "Allow", deny: "Deny", expired: "The code expired - pair again.",
    },
    // the deck page (server/library.py): folders and decks - in the browser's language
    library: {
      intro: (command) => `The decks of this quiz server (${command} builds one if needed and opens it here); a deck built now appears after a reload. Folders keep them in order: drag a deck onto a folder, or use its ⋯.`,
      all: "All decks", path: "folder", search: "Search all decks", searchLabel: "search all decks",
      order: "order", byName: "By name", newest: "Newest first", newFolder: "New folder",
      folders: (n) => `${n} ${n === 1 ? "folder" : "folders"}`, decks: (n) => `${n} ${n === 1 ? "deck" : "decks"}`,
      within: (path) => `in ${path}`,
      folderMenu: "rename, move or delete the folder", folderActions: "folder actions",
      deckMenu: "rename, move or remove the deck", deckActions: "deck actions",
      present: "Present", noStage: "no stage PDF",
      noStageWhy: "built without it (--no-stage, or before 2026-10-10 without --stage): build it again",
      noMatch: "No deck or folder matches.",
      empty: "This folder is empty - drag a deck onto it, or use a deck's ⋯ and Move to.",
      notDone: (why) => `Not done: ${why}`, moved: (where) => `Moved to ${where}`,
      rename: "Rename …", move: "Move to …", delete: "Delete …", unlist: "Remove from the list …",
      renameAsk: (name, own) => `The name of "${name}" on this page (empty: its own, "${own}")`, renameYes: "Rename",
      moveAsk: (name) => `Move "${name}" to`,
      deleteAsk: (name) => `Delete "${name}" from this server? Its uploaded builds are deleted; the results of its games stay in the archive.`,
      unlistAsk: (name) => `Remove "${name}" from the list? Its build folder stays on this computer - its next build brings it back.`,
      deleteYes: "Delete", unlistYes: "Remove",
      deleted: (name) => `${name}: deleted`, unlisted: (name) => `${name}: off the list`,
      folderName: "The folder's name", moveFolderAsk: (name) => `Move the folder "${name}" to`,
      deleteFolderAsk: (name) => `Delete the folder "${name}"? What it holds moves up one level - no deck is deleted.`,
      newFolderIn: (name) => `A new folder in "${name}"`, newFolderAsk: "A new folder", create: "Create",
      loading: (name) => `Loading ${name} ...`,
    },
    // the open deck: the top bar's buttons, the slide, the next step, the notes
    projector: "Projector", projectorTitle: "open the projector window (on the second screen)",
    archive: "After the lecture", archiveTitle: "the annotated PDF for the students, the lecture's archive",
    splitMain: "room for the slide and for the notes",
    splitMainTitle: "drag: more room for the slide or for the notes (double click: as it was)",
    splitNext: "room for the next slide and for the notes",
    splitNextTitle: "drag: more room for the next slide or for the notes (double click: as it was)",
    next: "Next", notes: "Notes", smaller: "smaller text", larger: "larger text",
    notesPage: "Page", notesText: "Text",
    notesPageTitle: "the note page as typeset", notesTextTitle: "the notes as text you can enlarge",
    boardNote: "A whiteboard page.", noNotes: "No notes.", noNotePage: "No note page for this slide.",
    tools: {
      auto: "navigate - a pen draws all the same (Esc)",
      pen: "Pen", penTitle: "pen (P)", marker: "Marker", markerTitle: "highlighter (H)",
      eraser: "Eraser", eraserTitle: "eraser (E) - also the pen's eraser end",
      laser: "Laser", laserTitle: "laser pointer (L)",
      zoom: "Zoom", zoomTitle: "zoom: drag a box over the slide (Z) - zoomed: the whole slide again",
      undo: "undo (Ctrl+Z)", redo: "redo (Ctrl+Y)", clear: "Clear", clearTitle: "erase all ink of this frame",
      board: "Whiteboard", boardTitle: "a whiteboard page after this frame (N)",
      grid: "Grid", gridTitle: "a whiteboard page with a grid (Shift+N)",
      poll: "Poll", pollTitle: "ask a question now: yes/no, A-D, a scale, a word cloud, text or a sketch",
      qa: "Q&A", qaTitle: "questions from the audience",
      sketches: "Sketches", sketchesTitle: "the drawings of this sketch question",
      activities: "Activities", activitiesTitle: "the deck's live activities: open, close, reveal, moderate",
      penColour: "pen colour", markerColour: "highlighter colour", width: "pen width",
      cleared: "All ink of this frame erased - ↶ or Ctrl+Z brings it back",
    },
    // the bar below: timer and clock, the steps, the projector's screen
    timer: "start / pause the timer (T)", reset: "reset the timer", resetAsk: "Reset the timer to 0:00?", resetYes: "Reset",
    target: "a target duration", targetAsk: "Target duration in minutes (empty: none)", targetNumber: "A number of minutes, please.",
    left: (time) => `${time} left`, over: (time) => `${time} over`,
    prev: "previous step (←, PageUp)", nextStep: "next step (→, PageDown, Space)",
    black: "Black", blackTitle: "black projector (B)", white: "White", whiteTitle: "white projector (W)",
    freeze: "Freeze", freezeTitle: "the projector keeps this slide while you go on (F)",
    overview: "Overview", overviewTitle: "all frames (G)",
    // where the lecturer is: the bar, the next step's label
    end: "the end", aBoard: "a whiteboard page", frame: (n) => `frame ${n}`, typing: (n) => `frame ${n}_ (Enter)`,
    pollShown: "a poll on the projector - Esc or → : back to the slide",
    sketchesShown: "sketches on the projector - Esc or → : back to the slide",
    boardAfter: (n) => `whiteboard page after frame ${n}`,
    frameOf: (n, m) => `frame ${n} / ${m}`, stepOf: (n, m) => `step ${n} / ${m}`,
    // what the projector shows if not this slide (the label over it)
    onscreen: (what) => `Projector: ${what}`, blackScreen: "black", whiteScreen: "white",
    frozen: { poll: "frozen on a poll", sketches: "frozen on a sketch board", board: "frozen on a whiteboard page",
      frame: (n) => `frozen on frame ${n}` },
    zoomed: (factor) => `zoomed ×${factor} - ⤢ tap: the whole slide`,
    overviewHead: "Frames and whiteboard pages - click one, or type a frame's number and Enter; G or Esc closes",
    overviewPage: "page",
    popup: "The browser blocked the projector window - allow pop-ups for this page.",
    videoSound: "The projector plays the video without sound - click into the projector window once.",
    videoStart: "The projector waits for a click to play the video - click into the projector window once.",
    // a lecture of this deck left ink: a new presentation, or its continuation
    earlier: {
      ink: (n) => `ink on ${n} ${n === 1 ? "frame" : "frames"}`,
      boards: (n) => `${n} ${n === 1 ? "whiteboard page" : "whiteboard pages"}`,
      both: (a, b) => `${a} and ${b}`,
      today: (time) => `of today, ${time}`, on: (date, time) => `of ${date}, ${time}`,
      ask: (when, what) => `The lecture ${when} left ${what}. Is this a new presentation, or does it continue that lecture?`,
      newGame: "A new presentation also starts a new game: the phones join with a new PIN.",
      fresh: "New presentation", goOn: "Continue that lecture",
    },
    // a poll typed now (Poll)
    poll: {
      title: "Ask a poll",
      kinds: { yesno: "Yes / No", choice: "A – F", scale: "Scale 1–5", words: "Word cloud", text: "Text", sketch: "Sketch" },
      notes: {
        yesno: "The phones answer Yes or No.",
        scale: "The phones pick 1 to 5 - say in the question what 1 and 5 mean.",
        words: "The phones type a word or two (24 characters); the projector shows a word cloud.",
        text: "The phones type an answer (140 characters); the projector lists them.",
        sketch: "The phones draw; Sketches shows the drawings, and you pick some for the projector.",
      },
      question: "Question",
      placeholder: "Type the question - formulas between $...$ (yes/no, A-F and the scale can do without: the slide asks)",
      time: "Time", seconds: (n) => `${n} s`, start: "Ask now",
      asked: "Asked in this game", slides: "(the slide's question)",
      answers: (n) => `${n} ${n === 1 ? "answer" : "answers"}`, show: "Show",
      count: "Answers", several: "several answers", optional: "optional - the letter alone, if the slide has the answers",
    },
    // the audience's questions (Q&A)
    qa: {
      title: "Questions", open: "open for the phones", openTitle: "the phones get a tab to ask and upvote",
      closeTitle: "close the panel", deleteAsk: "Delete this question?", delete: "Delete",
      blockAsk: "Block whoever asked this? Their question and their other open questions go, and they cannot ask any more in this game.",
      block: "Block", blockTitle: "whoever asked it cannot ask any more",
      reopen: "Reopen", hide: "Hide", show: "Show", showTitle: "on the projector, over the slide", done: "Done",
      none: "No questions yet.", closed: "Questions are closed - open them, and the phones get a tab for them.",
      answered: "Answered",
    },
    // the deck's live activities (Activities; stage/activity.js): many and one are what the box
    // calls the contributions (box.code: queries, or Turtle texts)
    activity: {
      title: "Activities", closeTitle: "close the panel",
      revealAsk: "Reveal the reference's result - in every window, and on the phones whether theirs is the same?",
      reveal: "Reveal", revealed: "Revealed",
      blockAsk: "Block whoever sent this? Their contributions go, and they cannot send any more in this game.", block: "Block",
      phase: { ready: "not opened yet", open: "open - the phones send", closed: "closed" },
      contributions: (n) => `${n} ${n === 1 ? "contribution" : "contributions"}`, close: "Close", open: "Open",
      failed: (many, why) => `The ${many} cannot be evaluated here: ${why}`,
      evaluates: (many, n) => `This window evaluates the ${many} (${n} so far).`,
      elsewhere: (many) => `Another presenter window evaluates the ${many} - or none: they wait.`,
      into: "← into this", unmerge: "Unmerge", merge: "Merge…", mergeTitle: "merge it into another term",
      show: "Show", hide: "Hide", approve: "Approve", unapprove: "Unapprove", label: "label", node: "node",
      from: "On the projector from", on: (n) => `${n === 1 ? "student" : "students"} on`,
      mergeInto: (term) => `Merge ${term} into …`, moreNodes: (n) => `${n} more nodes than the projector shows.`,
      noTriples: "No triples yet.",
      refPending: (i) => `reference ${i}: not run yet`, refFailed: (i, why) => `reference ${i} failed: ${why}`,
      refKey: (i, key) => `reference ${i}: ${key}`, noRef: "The deck gives no reference.", theReference: "the reference's",
      unshow: "Hide from the projector", showTitle: (one) => `its ${one} and result on the projector`,
      hideOne: (one) => `Hide this ${one}`, hideOneTitle: (one) => `this ${one} goes - the others of its cluster stay`,
      none: (many) => `No ${many} yet.`,
    },
    // a sketch question's drawings (Sketches)
    gallery: {
      back: "Back to the slide", show: (n) => `Show on the projector (${n})`,
      count: (n) => `${n} ${n === 1 ? "sketch" : "sketches"} - pick up to 12`,
    },
    // After the lecture: the annotated PDF, the archive, the recordings (record)
    after: {
      title: "After the lecture",
      intro: "The annotated PDF: every frame as it was shown last, with your ink, and the whiteboard pages - for the students. It is also kept in the lecture's archive on the server, with the quiz results.",
      make: "Make the PDF", zipIntro: "The archive - the annotated PDF and the results - as one file:",
      zip: "Download the archive (ZIP)", recordings: "Recordings",
      collecting: "Collecting the ink ...", making: "Making the PDF ...", keeping: "Downloaded. Keeping it in the archive ...",
      kept: (folder) => `Downloaded, and kept in the server's archive (${folder}).`, notKept: (why) => `Downloaded. ${why}`,
      failed: (why) => `The PDF failed: ${why}`,
    },
  },

  // the recording (stage/presenter.js with stage/record.js): the top bar's button and state, its
  // dialog, the takes After the lecture
  record: {
    button: "Record", buttonTitle: "record what the projector shows, with your voice",
    late: "saving delayed", lateTitle: "the network or the server does not take the parts yet - they wait here",
    meter: "the microphone", noSound: "no sound",
    resume: "Resume", resumeTitle: "go on recording", pauseTitle: "pause the recording",
    stopTitle: "stop the recording", stopAsk: "Stop the recording? Recording again makes a new file.", stop: "Stop",
    saving: "saving ...", saved: "Recording saved", savedTitle: "After the lecture lists it",
    stopped: (why) => `Recording stopped: ${why}`, ok: "OK",
    paused: (time) => `paused ${time}`, size: (mb) => `${mb} MB`, onServer: (file, mb) => `${file} · ${mb} MB on the server`,
    title: "Record the lecture",
    intro: "A video of what the projector shows - slides, ink, pointer, quizzes - with your voice. It goes to the server while it is recorded, into the lecture's archive (After the lecture).",
    microphone: "Microphone", asking: "Asking for the microphone ...",
    screen: "Start opens the browser's dialog: choose the projector's screen, or the projector window.",
    start: "Start recording", silent: "Recording without sound.", speak: "Speak: the bar shows what the microphone hears.",
    noMic: (why) => `No microphone - ${why}. The recording would have no sound.`, notAllowed: "the browser may not use it",
    defaultMic: "the default microphone", none: "no sound", noScreen: "No screen was chosen - Start again.",
    cannot: (why) => `The browser cannot record the screen: ${why}`,
    notStarted: (why) => `The recording did not start: ${why}`,
    recording: "being recorded", unfinished: "unfinished", finishing: "being finished",
    finish: "Finish", finishTitle: "it was not stopped in this window: keep what came", download: "Download",
    noTakes: "No recording.",
  },

  // the dialogs of the presenter window (stage/ask.js): their buttons where a question names none
  dialog: { ok: "OK", cancel: "Cancel" },

  // a deck uploaded by hand on the lists of decks (shared/upload.js)
  upload: {
    button: "Upload a deck", title: "the deck's .bundle.zip - texstage build writes it next to the PowerPoint file",
    uploading: (name, size) => `Uploading ${name} (${size} MB) ...`,
    uploaded: (name, quizzes, slides) => `${name}: uploaded (${quizzes} ${quizzes === 1 ? "quiz" : "quizzes"}, ${slides} ${slides === 1 ? "slide" : "slides"})`,
    known: (name) => `${name}: the server has it already`, failed: (name, why) => `${name} was not uploaded: ${why}`,
  },

  // the projector window's own texts (stage/projector.js, stage/projector.html) - its slide's are live's
  projector: {
    title: "texstage projector", open: "Open the projector from texstage's presenter window.", full: "Click for full screen",
  },

  // a video on the slide (stage/video.js): the presenter's bar, the note where the browser wants a click
  video: {
    play: "Play", pause: "Pause", toggle: "Play or pause - K, or a click into the video",
    track: "Drag: another position - J: 10 s back", sound: "Click for sound", start: "Click for the video",
  },

  // the annotated PDF (stage/export.js): its title
  pdf: { title: (deck) => `${deck} - with the lecture's ink` },

  // a sketch's picture (shared/sketch.js): what a screen reader says of it, with its number if it has one
  sketch: { label: (number) => (number ? `Sketch ${number}` : "Sketch") },

  // the host console (host/host.js, host/index.html): the decks, then a game's slides, players and quizzes
  host: {
    title: "texstage host",
    intro: (build, script) => `Built with ${build} / ${script}; a deck built now appears after a reload.`,
    resume: "Continue", start: "Start", prev: "previous slide (←)", next: "next slide (→)", full: "full screen (F)",
    players: "Players", playersOf: (n, online) => `Players (${n}, ${online} online)`, quizzes: "Quizzes",
    nobody: "Nobody has joined yet.", rename: "rename", remove: "remove",
    renameAsk: "New nickname", removeAsk: (name) => `Remove ${name} from the game?`, slideOf: (n, m) => `slide ${n} / ${m}`,
  },

  // the PowerPoint add-in (addin/addin.js): its status bar in the editing view, the file's first
  // slide, the cover while the live slides are prepared - the deck's language once the deck is there
  addin: {
    noProps: "this object has no texstage properties",
    notInDeck: (slide, deck, bundle) => `slide ${slide} is not in deck ${deck} (${bundle})`,
    unpaired: "not paired with the quiz server",
    keyOld: "the presenter key in this file is not the server's - build the deck again, or pair here",
    keyRejected: "the presenter key is not accepted",
    refused: "the quiz server did not take this deck (its log says why)",
    missing: "the quiz server does not have this deck - its build hands it over: present on the laptop that built it, or build it for this server (or texstage publish it there)",
    connecting: "connecting to the quiz server …", preparing: "Preparing the quiz slides …",
    // the first slide
    connectingFirst: "Connecting to the quiz server …",
    startHere: "Start the slideshow here: this slide prepares the quiz slides.",
    partly: (done, total) => `${done} of ${total} quiz slides prepared`,
    stopped: (why) => `Stopped (${why}) - the join slide prepares the rest.`,
    stoppedAt: (slide, why) => `slide ${slide}: ${why}`, movedOn: "the lecturer moved on",
    ready: "Ready", prepared: (n) => `${n} ${n === 1 ? "quiz slide" : "quiz slides"} prepared.`,
    already: "The quiz slides were prepared already.",
    game: (pin, n, join) => `Game PIN ${pin} · ${n} ${n === 1 ? "player" : "players"} · ${join}`,
    goOn: "Go on to the first slide when the lecture starts.",
    // the status bar
    server: "server", paired: "paired", notPaired: "not paired",
    keyField: "presenter key (texstage serve prints it)", pair: "Pair",
  },
};
