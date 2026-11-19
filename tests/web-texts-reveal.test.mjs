// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// What the box of a live activity shows at the reveal and when the lecturer shows a group (web/stage/
// activities.js: StepBox.drawGroups), in Node: with solution=show, the core's default, the references with their
// results in a card, and the group the lecturer shows in a card of its own - beside the bars, both at once, none
// over the bars or over the other (the review of 2026-11-19: the reference's card lay over the bars until a
// reset, and a group shown after the reveal under it); below the bars in a box taller than wide; nothing of it
// where there is no card. (How it looks at the projector's size: stage.css, .tq-split.)
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = (rel) => pathToFileURL(path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web", rel)).href;
Object.defineProperty(globalThis, "navigator", { value: { language: "en-GB", languages: ["en-GB"] }, configurable: true });

// a stand-in for the box's element: its markup as written, its classes as toggled
function element() {
  const e = { innerHTML: "", style: {}, classes: new Set(), append() {}, remove() {}, querySelector: () => null };
  e.classList = { toggle: (name, on) => { if (on ?? !e.classes.has(name)) e.classes.add(name); else e.classes.delete(name); } };
  return e;
}
globalThis.document = { createElement: () => element() };
const { StepBox } = await import(web("stage/activities.js"));

const result = (columns, n) => ({ columns, rows: Array.from({ length: n }, (_, i) => columns.map((c) => `${c}${i}`)), count: n });
const REFERENCE = "SELECT ?river ?settlement WHERE {\n  ?river :flowsThrough ?s .\n  ?s :name ?settlement .\n}";
const groups = [
  { id: "g1", status: "ok", n: 14, example: { text: REFERENCE }, detail: result(["river", "settlement"], 8), reference: true,
    verdict: "correct" },
  { id: "g2", status: "ok", n: 6, example: { text: "SELECT * WHERE { ?s ?p ?o }" }, detail: result(["s", "p", "o"], 8),
    verdict: "incorrect" },
];
const revealed = { kind: "groups", phase: "revealed", revealed: true, students: 20, entries: 20, right: 14, groups,
  solution: [{ text: REFERENCE, detail: result(["river", "settlement"], 8) }] };

function box(language = "en") {
  return new StepBox({ id: "rivers", item: { kind: "sparql-query" }, layer: element(), language,
    host: { role: "projector", read: () => new Promise(() => {}) } });
}
const cards = (b) => b.el.innerHTML.match(/<div class="tq-cards">([\s\S]*)$/)?.[1] ?? "";
const bars = (b) => b.el.innerHTML.split('<div class="tq-cards">')[0];

test("the reveal: the reference and its result in a card beside the bars, which stay to be seen", () => {
  const b = box();
  b.picture = revealed;
  b.draw();
  assert.deepEqual([...b.el.classes].sort(), ["tq-split"]);
  assert.equal((bars(b).match(/class="tq-cluster[ "]/g) || []).length, 2, "the bars, outside the cards");
  assert.doesNotMatch(bars(b), /tq-shown/);
  assert.match(cards(b), /^<div class="tq-shown"><div class="tq-shownhead">The reference<\/div>/);
  assert.match(cards(b), /<pre>SELECT \?river/);
  assert.match(cards(b), /<table class="tq-result">/);
});

test("a group shown after the reveal: a card of its own beside the reference's, not under it", () => {
  const b = box("de");
  b.picture = { ...revealed, shown: { ...groups[1] } };
  b.draw();
  assert.deepEqual([...b.el.classes].sort(), ["tq-split", "tq-two"]);
  const [reference, shown] = cards(b).split('<div class="tq-shown">').slice(1);
  assert.match(reference, /Die Referenz/);
  assert.match(shown, /8 Zeilen · 6 Personen · nicht richtig/);
  assert.match(shown, /<pre>SELECT \* WHERE/);
  b.picture = { ...revealed, phase: "open", revealed: false, solution: undefined, shown: { ...groups[1], verdict: undefined } };
  b.draw();                                                             // shown while it is open: beside the bars too
  assert.deepEqual([...b.el.classes], ["tq-split"]);
  assert.equal((cards(b).match(/class="tq-shown"/g) || []).length, 1);
});

test("a box taller than wide: the cards below the bars; no card, no split - whatever was drawn before", () => {
  const b = box();
  b.aspect = 0.8;                                                       // (place: the box's width over its height)
  b.picture = { ...revealed, shown: { ...groups[1] } };
  b.draw();
  assert.deepEqual([...b.el.classes].sort(), ["tq-split", "tq-tall", "tq-two"]);
  b.picture = { ...revealed, solution: undefined };                     // solution=mark: the bars alone
  b.draw();
  assert.deepEqual([...b.el.classes], []);
  assert.doesNotMatch(b.el.innerHTML, /tq-cards|tq-shown/);
  b.picture = { ...revealed, shown: { ...groups[1] } };
  b.draw();
  b.picture = { phase: "open", students: 2, numbers: [[1, 1], [2, 1]], groups: [] };     // a number step: no cards
  b.draw();
  assert.deepEqual([...b.el.classes], []);
  b.picture = { phase: "open", held: "count", students: 2, entries: 2 };                  // projector=count
  b.draw();
  assert.deepEqual([...b.el.classes], []);
});
