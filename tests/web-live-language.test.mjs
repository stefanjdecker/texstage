// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The live views in the deck's language (web/shared/live.js, web/stage/activity.js), in Node: a
// German deck (deck.json's "language": "de") gets the quiz's views - join, question, banner, answer
// panel, leaderboard, poll, the audience's question, the lecturer's buttons - and the activity box
// in German, through the Stage the presenter and projector windows make; an English deck, and one
// built before deck.json named its language, get them as they were. A window's own labels go over
// the deck's; the add-in, which shows its slide before its deck has come, speaks the deck's once it
// is there. The presenter window's activity panel (codeWords, resultLabel, resultTable) speaks the
// language it is given - English without one.
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web");
const { LABELS, LANGUAGES, Stage, liveLabels } = await import(pathToFileURL(path.join(web, "shared/live.js")).href);
const { ActivityBox, boxWords, codeWords, resultLabel, resultTable } =
  await import(pathToFileURL(path.join(web, "stage/activity.js")).href);

// a small DOM double: what the stage and the box write into their elements
function element() {
  const kids = new Map();
  return {
    innerHTML: "", textContent: "", style: {}, isConnected: true, clientWidth: 0, clientHeight: 0,
    classList: { add() {}, remove() {}, toggle() {} },
    prepend() {}, append() {}, remove() {}, addEventListener() {}, setAttribute() {}, getAttribute: () => null,
    querySelector(selector) {
      if (!kids.has(selector)) kids.set(selector, element());
      return kids.get(selector);
    },
    querySelectorAll: () => [],
  };
}
globalThis.requestAnimationFrame = () => 0;
globalThis.document = { createElement: element, createElementNS: element, documentElement: element() };
globalThis.getComputedStyle = () => ({ getPropertyValue: () => "" });

const ANSWERS = [{ id: "A", shape: 1 }, { id: "B", shape: 2 }];
const QUIZZES = { q: { type: "single", title: "Frage", answers: ANSWERS },
  sk: { type: "sketch", title: "Skizze", prompt: { text: "Ein ER-Diagramm" }, answers: [] } };
const SESSION = { pin: "123456", join: "https://quiz.example.org/play?pin=123456", qr: "qr.png", base: "/bundle/b/" };
const PLAYERS = [{ nickname: "ada", rank: 1, score: 900 }, { nickname: "bob", rank: 2, score: 400 }, { nickname: "cy", rank: 0, score: 0 }];
const TIMER = { timer: { x: 0.8, y: 0.1, w: 0.1, h: 0.18 } };
const round = (phase, extra = {}) => ({ phase, answered: 2, awaiting: 1, opens: 0, deadline: 0, limit: 20000, paused: false,
  results: phase === "open" || phase === "get-ready" ? undefined : { answered: 2, counts: { A: 1, B: 1 }, correct: 1 },
  keys: phase === "revealed" ? { correct: ["A"] } : undefined, ...extra });

// what the projector shows: the live layer's HTML, the timer's line under its count, the buttons
function shown(language, slide, rounds = {}, { labels, stage: extra = {}, players = PLAYERS } = {}) {
  const deck = { ...(language === undefined ? {} : { language }), bundle: "b", quizzes: QUIZZES, slides: [slide] };
  const stage = new Stage(element(), { controls: true, labels, surface: { element: element(), show() {} } });
  stage.show(slide, deck, { session: SESSION, players, rounds, stage: extra }, () => 0);
  const timer = stage.live.querySelector('[data-role="timer"]');
  return { html: stage.live.innerHTML, sub: timer.querySelector(".tq-timer-sub").textContent, controls: stage.controls.innerHTML };
}

const VIEWS = {
  join: () => [{ phase: "join", rects: {} }, {}],
  open: () => [{ quiz: "q", phase: "question", rects: TIMER }, { q: round("open") }],
  ready: () => [{ quiz: "q", phase: "question", rects: TIMER }, { q: round("get-ready", { opens: 3000 }) }],
  timeUp: () => [{ quiz: "q", phase: "question", rects: {} }, { q: round("closed", { closed_by: "time" }) }],
  allIn: () => [{ quiz: "q", phase: "question", rects: {} }, { q: round("closed", { closed_by: "all" }) }],
  revealed: () => [{ quiz: "q", phase: "reveal", rects: TIMER }, { q: round("revealed") }],
  answer: () => [{ quiz: "q", phase: "answer", rects: {} }, { q: round("revealed") }],
  leaderboard: () => [{ quiz: "q", phase: "leaderboard", rects: {} }, { q: round("revealed") }],
  poll: () => [{ overlay: "poll", quiz: "sk" }, { sk: round("open") }],
};

test("a German deck's quiz views are German", () => {
  const de = Object.fromEntries(Object.entries(VIEWS).map(([name, view]) => [name, shown("de", ...view())]));
  for (const text of ["Mitmachen unter", "quiz.example.org/play", "Spiel-PIN", "3 Personen"]) assert.ok(de.join.html.includes(text), text);
  assert.ok(shown("de", ...VIEWS.join(), { players: PLAYERS.slice(0, 1) }).html.includes("1 Person<"));
  assert.ok(de.open.html.includes("2 / 3 Antworten"));
  assert.ok(de.open.controls.includes('title="Pause"') && de.open.controls.includes('title="10 Sekunden mehr"')
    && de.open.controls.includes('title="Die Frage beenden"'));
  assert.equal(de.ready.sub, "Bereit?");
  assert.ok(de.timeUp.html.includes("Die Zeit ist um!") && de.timeUp.html.includes("2 Antworten"));
  assert.ok(de.timeUp.controls.includes('title="Die Antwort zeigen"'));
  assert.ok(de.allIn.html.includes("Alle Antworten sind da!"));
  assert.ok(de.revealed.html.includes("1 / 2 richtig"));
  assert.ok(de.revealed.controls.includes("Noch einmal fragen (Übung)"));
  assert.ok(de.answer.html.includes(">Ergebnisse<") && de.answer.html.includes("1 / 2 richtig"));
  assert.ok(de.leaderboard.html.includes(">Bestenliste<") && de.leaderboard.html.includes("ada"));
  assert.ok(de.poll.html.includes("Zeichnen Sie Ihre Antwort auf dem Handy.")
    && de.poll.html.includes("Mitmachen unter quiz.example.org/play · Spiel-PIN 123456"));
  for (const [name, view] of Object.entries(de)) {
    for (const english of ["Join at", "Game PIN", "players", "answers", "Time&#39;s up", "All answers are in", "Results",
      "Leaderboard", "Draw your answer", "correct", "Get ready", "Stop the question", "Show the answer", "Ask again"]) {
      assert.ok(!view.html.includes(english) && !view.controls.includes(english) && view.sub !== english, `${name}: ${english}`);
    }
  }
  const nobody = shown("de", ...VIEWS.leaderboard(), { players: [{ nickname: "cy", rank: 0, score: 0 }] }).html;
  assert.ok(nobody.includes(">Bestenliste<") && nobody.includes("Noch keine Punkte"));
  const audience = shown("de", ...VIEWS.join(), { stage: { question: { text: "Warum 3NF?", votes: 4 } } }).html;
  assert.ok(audience.includes("Frage aus dem Publikum") && audience.includes("Warum 3NF?"));
});

test("an English deck's quiz views are as they were - also a deck that names no language", () => {
  for (const [name, view] of Object.entries(VIEWS)) {
    const before = shown(undefined, ...view());                  // built before 2026-10-24
    assert.deepEqual(shown("en", ...view()), before, name);
    assert.deepEqual(shown("en-GB", ...view()), before, name);
    assert.deepEqual(shown("fr", ...view()), before, name);       // a language the views do not speak
    assert.notDeepEqual(shown("de", ...view()), before, name);
  }
  const join = shown("en", ...VIEWS.join()).html;
  for (const text of ["Join at", "Game PIN", "3 players"]) assert.ok(join.includes(text), text);
  assert.ok(shown("en", ...VIEWS.timeUp()).html.includes("Time&#39;s up!"));
  assert.ok(shown("en", ...VIEWS.allIn()).html.includes("All answers are in!"));
  assert.ok(shown("en", ...VIEWS.revealed()).html.includes("1 / 2 correct"));
  assert.ok(shown("en", ...VIEWS.leaderboard()).html.includes(">Leaderboard<"));
  assert.equal(shown("en", ...VIEWS.ready()).sub, "Get ready");
  assert.ok(shown(undefined, ...VIEWS.open()).controls.includes('title="Stop the question"'));
});

test("every text has its German; a window's own labels go over the deck's", () => {
  assert.deepEqual(Object.keys(LANGUAGES.de).sort(), Object.keys(LABELS).sort());
  assert.deepEqual(liveLabels("de"), { ...LABELS, ...LANGUAGES.de });
  assert.deepEqual(liveLabels("DE-at"), liveLabels("de"));
  for (const other of [undefined, null, "", "en", "en-US", "fr", "__proto__", "constructor"]) assert.deepEqual(liveLabels(other), LABELS);
  const own = shown("de", ...VIEWS.join(), { labels: { joinAt: "Beitreten unter" } }).html;
  assert.ok(own.includes("Beitreten unter") && own.includes("Spiel-PIN") && !own.includes("Mitmachen unter"));
});

test("the add-in's stage speaks its deck's language once the deck has come", () => {
  const stage = new Stage(element(), { controls: true, surface: { element: element(), show() {} } });
  const state = { session: SESSION, players: PLAYERS, rounds: {}, stage: {} };
  const slide = { phase: "join", rects: {} };
  stage.show(slide, null, state);                                 // its slide before its deck (addin.js)
  assert.ok(stage.live.innerHTML.includes("Join at"));
  stage.show(slide, { language: "de", quizzes: QUIZZES, slides: [slide] }, state);
  assert.ok(stage.live.innerHTML.includes("Mitmachen unter"));
  stage.refresh();
  assert.ok(stage.live.innerHTML.includes("Mitmachen unter"));
});

// ------------------------------------------------------------------ the activity box

const CLUSTERS = {
  kind: "clusters", phase: "open", students: 5, waiting: 2, others: 4,
  clusters: [
    { key: "a", n: 3, status: "ok", reference: true, summary: { kind: "select", count: 11, columns: ["name"], rows: [["Kant"]] } },
    { key: "b", n: 1, status: "ok", summary: { kind: "select", count: 1, columns: ["name"], rows: [["Carnap"]] } },
    { key: "c", n: 1, status: "syntax" }, { key: "d", n: 1, status: "timeout" }, { key: "e", n: 1, status: "refused" },
    { key: "f", n: 1, status: "ok", summary: { kind: "ask", boolean: true } },
  ],
  shown: { n: 3, status: "ok", reference: true, example: "SELECT name FROM Professoren",
    summary: { kind: "select", count: 11, columns: ["name"], rows: [["Kant"], ["Carnap"]] } },
};
const GRAPH = { kind: "graph", phase: "open", nodes: [], edges: [], more: 5 };

function box(language, engine, picture) {
  // the box as Stage makes it, and its picture drawn
  const b = new ActivityBox({ id: "q1", item: { input: engine ? "code" : "tuple", engine }, layer: element(), language });
  b.picture = picture;
  b.draw();
  return b.el.innerHTML;
}

test("a German deck's activity box is German", () => {
  const sql = box("de", "sql", CLUSTERS);
  for (const text of ["5 Personen · 2 warten", "11 Zeilen ✓", "1 Zeile<", "Syntaxfehler", "lief zu lange", "nicht ausgeführt",
    ">ja<", "andere · 4", "· 3 Personen · das Ergebnis der Referenz ✓", "und 9 weitere"]) {
    assert.ok(sql.includes(text), text);
  }
  assert.ok(box("de", "sql", { ...CLUSTERS, waiting: 1 }).includes("5 Personen · 1 wartet"));
  assert.ok(box("de", "sparql", { ...CLUSTERS, clusters: [], shown: null }).includes("Warten auf die ersten Anfragen …"));
  assert.ok(box("de", "sparql", { ...CLUSTERS, phase: "closed", clusters: [], shown: null }).includes("Keine Anfragen."));
  const turtle = box("de", "turtle", { ...CLUSTERS, shown: { n: 1, status: "ok", reference: true, example: ":a :b :c .",
    summary: { kind: "graph", count: 7, rows: [[":a", ":b", ":c"]] } } });
  assert.ok(turtle.includes("7 Tripel") && turtle.includes("· 1 Person · der Graph der Referenz ✓")
    && turtle.includes("<th>Subjekt</th><th>Prädikat</th><th>Objekt</th>") && turtle.includes("und 6 weitere"));
  assert.ok(box("de", "turtle", { ...CLUSTERS, clusters: [], shown: null }).includes("Warten auf die ersten Graphen …"));
  assert.ok(box("de", null, GRAPH).includes("Warten auf die ersten Tripel …") && box("de", null, GRAPH).includes("und 5 weitere"));
  assert.ok(box("de", null, { ...GRAPH, phase: "closed" }).includes("Keine Tripel."));
  for (const english of ["student", "waiting", "rows", "syntax error", "ran too long", "not run", "others", "reference's", "and 9 more"]) {
    assert.ok(!sql.includes(english), english);
  }
});

test("an English deck's activity box is as it was - also a deck that names no language", () => {
  for (const [engine, picture] of [["sql", CLUSTERS], ["turtle", CLUSTERS], [null, GRAPH], [null, { ...GRAPH, phase: "closed" }]]) {
    assert.equal(box("en", engine, picture), box(undefined, engine, picture));
    assert.equal(box("fr", engine, picture), box(undefined, engine, picture));
  }
  const sql = box(undefined, "sql", CLUSTERS);
  for (const text of ["5 students · 2 waiting", "11 rows ✓", "1 row<", "syntax error", "ran too long", "not run", ">yes<",
    "others · 4", "· 3 students · the reference's result ✓", "and 9 more"]) {
    assert.ok(sql.includes(text), text);
  }
  assert.ok(box(undefined, "sparql", { ...CLUSTERS, clusters: [], shown: null }).includes("Waiting for the first queries …"));
  assert.ok(box(undefined, "turtle", { ...CLUSTERS, phase: "closed", clusters: [], shown: null }).includes("No graphs."));
  assert.ok(box(undefined, null, GRAPH).includes("Waiting for the first triples …") && box(undefined, null, GRAPH).includes("and 5 more"));
  assert.ok(box(undefined, null, { ...GRAPH, phase: "closed" }).includes("No triples."));
});

test("the box's words: German for every English one; without a language English", () => {
  const shape = (w) => JSON.stringify(Object.keys(w).sort().map((k) => [k, typeof w[k] === "object" && !Array.isArray(w[k])
    ? Object.keys(w[k]).sort().map((j) => [j, typeof w[k][j] === "object" ? Object.keys(w[k][j]).sort() : typeof w[k][j]]) : typeof w[k]]));
  assert.equal(shape(boxWords("de")), shape(boxWords("en")));
  for (const other of [undefined, "", "en", "fr", "constructor", "__proto__"]) assert.equal(boxWords(other), boxWords("en"));
  assert.equal(boxWords("de-DE"), boxWords("de"));
  // (the presenter window's panel calls these with the deck's language; without one: English)
  assert.equal(codeWords({ engine: "sql" }).many, "queries");
  assert.equal(codeWords({ engine: "turtle" }).one, "text");
  assert.equal(codeWords({ engine: "turtle" }, "de").one, "Text");
  assert.equal(resultLabel(CLUSTERS.clusters[0]), "11 rows");
  assert.equal(resultLabel({ status: "ok", summary: { kind: "graph", count: 1 } }), "1 triple");
  assert.equal(resultLabel({ status: "ok", summary: { kind: "graph", count: 1 } }, "de"), "1 Tripel");
  assert.equal(resultLabel({ status: "error" }, "de"), "Fehler");
  assert.equal(resultLabel({ status: "ok", summary: {} }, "de"), "ein Ergebnis");
  assert.ok(resultTable(CLUSTERS.shown.summary, 1).includes("and 10 more"));
  assert.ok(resultTable({ kind: "ask", boolean: false }, 4, "de").includes(">nein<"));
});

test("the stage gives the deck's language to the box it makes", async () => {
  const deck = { language: "de", bundle: "b", quizzes: {}, items: { activity: { q1: { input: "code", engine: "sql" } } } };
  const slide = { live: [{ type: "activity", item: "q1", rects: { box: { x: 0.1, y: 0.2, w: 0.8, h: 0.6 } } }] };
  deck.slides = [slide];
  const stage = new Stage(element(), { surface: { element: element(), show() {} }, types: { activity: ActivityBox },
    host: { role: "projector", read: async () => ({ picture: CLUSTERS }) } });
  stage.show(slide, deck, { session: SESSION, players: [], rounds: {}, stage: { activity: { items: { q1: { version: 1, layout: 0 } } } } });
  const [mounted] = stage.mounted.values();
  assert.equal(mounted.language, "de");
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.ok(mounted.el.innerHTML.includes("5 Personen · 2 warten") && mounted.el.innerHTML.includes("Syntaxfehler"));
});
