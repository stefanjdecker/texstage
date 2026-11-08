// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A code activity on the phone (web/play/activity.js), in Node: what its screen says, engine by
// engine - a Turtle text is valid or not, a graph the reference's or not; a query's words as they
// were -, in the deck's language (play.js gives it; never the phone's own), the server's refusals
// in its words, and the token bar's insertion at the cursor: a word with spaces around it, the
// start of one (?, _:, dbr:) with a space before it only, a sign (:, ., ", @, ^^) as it is.
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const url = pathToFileURL(path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web/play/activity.js")).href;
// an English phone: what it shows follows the deck, not navigator.language
Object.defineProperty(globalThis, "navigator", { value: { language: "en-GB", languages: ["en-GB"] }, configurable: true });
const module = await import(url);
// the screen as a phone shows it for a deck of this language
const phone = (language) => ({ ...module, language, words: (engine) => module.words(engine, language) });
const en = phone("en");
const de = phone("de");

test("a turtle activity's words: valid Turtle, the same graph - a query's as they were", () => {
  const turtle = en.words("turtle");
  assert.equal(turtle.ok, "Valid Turtle ✓");
  assert.equal(turtle.query, "Your Turtle");
  assert.equal(turtle.syntax, "Syntax error");
  assert.equal(turtle.match, "The same graph as the reference ✓");
  assert.equal(turtle.differ, "A different graph than the reference");
  for (const engine of ["sparql", "sql", undefined]) {
    const words = en.words(engine);
    assert.equal(words.ok, "Your query runs ✓", engine);
    assert.equal(words.query, "Your query");
    assert.equal(words.match, "The same result as the reference ✓");
    assert.equal(words.timeout, "The query ran too long.");
    assert.deepEqual(de.words(engine), de.words("sparql"));
  }
  assert.equal(de.words("turtle").ok, "Gültiges Turtle ✓");
  assert.equal(de.words("sparql").ok, "Ihre Anfrage läuft ✓");
  assert.deepEqual(module.words("sparql", "fr"), en.words("sparql"), "a language without texts: English");
  assert.deepEqual(module.words("sparql"), en.words("sparql"), "a deck that names none: English");
  assert.deepEqual(Object.keys(en.words("turtle")).sort(), Object.keys(en.words("sparql")).sort());
  assert.deepEqual(Object.keys(de.words("turtle")).sort(), Object.keys(en.words("turtle")).sort());
});

function screen(module, activity) {
  // the screen on a small DOM double: what it writes into its elements
  const els = new Map();
  const el = (selector) => {
    if (!els.has(selector)) {
      els.set(selector, { innerHTML: "", textContent: "", value: "", hidden: false, className: "",
        addEventListener() {}, querySelectorAll: () => [], focus() {} });
    }
    return els.get(selector);
  };
  const root = { innerHTML: "", querySelector: el, querySelectorAll: (s) => (s === "[data-role=used]" ? [el(s)] : []) };
  const base = { id: "berlin", phase: "open", input: "code", limit: 5, used: 0, blocked: false, tokens: [":", "_:"] };
  const s = new module.ActivityScreen({ root, client: {}, language: module.language,
    state: { session: { base: "/" }, activity: { ...base, ...activity } } });
  return { root, el, screen: s, update: (more) => s.update({ activity: { ...base, ...activity, ...more } }) };
}

test("the screen speaks the deck's language, and says the server's refusals in it", () => {
  const g = screen(de, { engine: "sparql" });
  assert.match(g.root.innerHTML, /Ihre Anfrage/);
  assert.match(g.root.innerHTML, /Abschicken/);
  g.update({ phase: "closed" });
  assert.equal(g.el("[data-role=error]").textContent, "Die Aktivität ist geschlossen.");
  assert.equal(g.screen.refusal({ code: "too-fast", message: "one every 5 seconds" }),
    "Bitte warten Sie ein paar Sekunden, bevor Sie wieder etwas schicken.");
  assert.equal(g.screen.refusal({ code: "text", message: "a query has 1 to 2000 characters" }), "Bitte tippen Sie zuerst Ihre Anfrage.");
  assert.equal(screen(de, { engine: "turtle" }).screen.refusal({ code: "text" }), "Bitte tippen Sie zuerst Ihr Turtle.");
  assert.equal(screen(de, { input: "tuple", fields: ["s", "p", "o"] }).screen.refusal({ code: "field" }), "Bitte füllen Sie jedes Feld aus.");
  assert.equal(g.screen.refusal({ code: "kicked" }), "Sie wurden aus dem Spiel entfernt.", "a refusal of the game's: the phone's words");
  assert.equal(g.screen.refusal({ code: "invalid", message: "fields: 3 texts" }), "Das hat nicht geklappt: fields: 3 texts");
  assert.equal(screen(en, { engine: "sparql" }).screen.refusal({ code: "duplicate" }), "You have sent this one already.");
});

test("the screen says it: valid Turtle, a syntax error at its line, the same graph - a query runs", () => {
  const t = screen(en, { engine: "turtle" });
  assert.match(t.root.innerHTML, /Your Turtle/);
  assert.match(t.el("[data-role=tokens]").innerHTML, /data-token="_:"/);
  t.update({ mine: { id: "c1", text: "dbr:Berlin rdfs:label \"Berlin\"@de .", status: "ok" } });
  assert.equal(t.el("[data-role=state]").innerHTML, "<p>Valid Turtle ✓</p>");
  t.update({ mine: { id: "c2", text: "x", status: "syntax", error: "line 2, column 1: A dot is expected at the end of statements" } });
  assert.equal(t.el("[data-role=state]").innerHTML, "<p>Syntax error: line 2, column 1: A dot is expected at the end of statements</p>");
  t.update({ phase: "closed", mine: { id: "c1", text: "x", status: "ok", match: true } });
  assert.match(t.el("[data-role=state]").innerHTML, /The same graph as the reference ✓/);
  assert.equal(t.el("[data-role=used]").textContent, "(0 of 5)");
  const q = screen(en, { engine: "sparql" });
  assert.match(q.root.innerHTML, /Your query/);
  q.update({ mine: { id: "c1", text: "SELECT * {}", status: "ok" } });
  assert.equal(q.el("[data-role=state]").innerHTML, "<p>Your query runs ✓</p>");
  const g = screen(de, { engine: "turtle" });
  g.update({ mine: { id: "c1", text: "x", status: "ok", match: false } });
  assert.match(g.el("[data-role=state]").innerHTML, /Gültiges Turtle ✓.*Ein anderer Graph als die Referenz/s);
});

test("the token bar inserts at the cursor: words with spaces, a sign as it is", () => {
  const at = (text, token, start = text.length, end = start) => en.insertToken(text, start, end, token);
  assert.deepEqual(at("", ":"), { value: ":", cursor: 1 });
  assert.deepEqual(at("dbr", ":"), { value: "dbr:", cursor: 4 }, "a prefix being typed");
  assert.deepEqual(at("dbr:Berlin rdfs:label \"Berlin\"", "@"), { value: "dbr:Berlin rdfs:label \"Berlin\"@", cursor: 31 });
  assert.equal(at("dbo:populationTotal \"3596999\"", "^^").value, "dbo:populationTotal \"3596999\"^^");
  assert.equal(at("\"3596999\"^^", "xsd:integer").value, "\"3596999\"^^xsd:integer ");
  assert.equal(at("dbr:Berlin", "rdfs:label").value, "dbr:Berlin rdfs:label ", "a word: a space before and after");
  assert.equal(at("dbr:Berlin rdfs:label ", "_:").value, "dbr:Berlin rdfs:label _:");
  assert.equal(at("dbr:Berlin rdfs:label", "_:").value, "dbr:Berlin rdfs:label _:", "the start of a word: a space before");
  assert.equal(at("?p a", "dbo:").value, "?p a dbo:");
  assert.equal(at("SELECT", "?").value, "SELECT ?", "SPARQL: ? then the name");
  assert.equal(at("SELECT", "?name").value, "SELECT ?name ");
  assert.equal(at("?p a", ":").value, "?p a:", "a colon goes where the cursor is");
  assert.equal(at("WHERE", "{").value, "WHERE{");
  assert.equal(at("<http://dbpedia.org/resource/Berlin", ">").value, "<http://dbpedia.org/resource/Berlin>");
  assert.deepEqual(at("abc", ".", 1, 2), { value: "a.c", cursor: 2 }, "a selection: replaced");
  assert.deepEqual(at("ab", "SELECT", 0, 0), { value: "SELECT ab", cursor: 7 });
});
