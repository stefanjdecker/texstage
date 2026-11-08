// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A code activity on the phone (web/play/activity.js), in Node: what its screen says, engine by
// engine - a Turtle text is valid or not, a graph the reference's or not; a query's words as they
// were -, and the token bar's insertion at the cursor: a word with spaces around it, the start of
// one (?, _:, dbr:) with a space before it only, a sign (:, ., ", @, ^^) as it is.
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { activeContentType } from "../src/texstage/web/play/content-type.js";
import { languageTag, phoneLabels, phoneError } from "../src/texstage/web/play/locale.js";

test("a current plugin replaces retained built-in activity feedback on the phone", () => {
  const types = { activity: true, plugins: true };
  const state = { session: {}, activity: { id: "turtle-many", phase: "closed" },
    plugins: { items: [{ modules: { "participant-input": "/plugins/lesson.mjs" } }] } };
  assert.equal(activeContentType(state, types), "plugins");
  for (const phase of ["get-ready", "open"]) {
    assert.equal(activeContentType({ ...state, round: { phase } }, types), undefined);
  }
  assert.equal(activeContentType({ ...state, round: { phase: "revealed" } }, types), "plugins");
  assert.equal(activeContentType({ ...state, session: { finished: true } }, types), undefined);
  for (const items of [[], [{ modules: { "projector-overlay": "/plugins/slide.mjs" } }]]) {
    assert.equal(activeContentType({ ...state, plugins: { items } }, types), "activity");
  }
  assert.equal(activeContentType({ session: {}, plugins: { items: [] } }, types), undefined);
});

const url = pathToFileURL(path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web/play/activity.js")).href;
async function phone(language) {
  // The browser disagrees with the deck. Both mounted and standalone labels
  // must use the explicit session language, not a module-time browser global.
  Object.defineProperty(globalThis, "navigator", { value: { language: "fr-FR" }, configurable: true });
  const module = await import(url);
  return { ...module, language, words: engine => module.words(engine, language) };
}
const en = await phone("en-GB");
const de = await phone("de-DE");

test("phone labels and join errors follow an explicit deck language", () => {
  assert.equal(languageTag("de-AT"), "de");
  assert.equal(languageTag("EN-gb"), "en");
  assert.equal(languageTag("fr"), "en");
  const german = phoneLabels("de-DE"), english = phoneLabels("en");
  assert.equal(german.join, "Mitspielen");
  assert.equal(german.in, "Du bist dabei!");
  assert.equal(english.in, "You're in!");
  assert.deepEqual(Object.keys(german).sort(), Object.keys(english).sort());
  assert.equal(phoneError({ code: "nickname-taken", message: "this nickname is taken" }, "de"),
    "Dieser Spitzname ist bereits vergeben.");
  assert.match(phoneError({ code: "unknown-pin" }, "de"), /kein laufendes Spiel/);
  assert.match(phoneError({ code: "too-many-attempts" }, "de"), /falsche PINs/);
  assert.equal(phoneError({ message: "unknown error" }, "de"),
    "Die Aktion konnte nicht ausgeführt werden. Bitte versuche es erneut.");
});

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
  assert.equal(de.words("sparql").ok, "Deine Anfrage läuft ✓");
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
  const s = new module.ActivityScreen({ root, client: {}, state: { language: module.language,
    session: { base: "/" }, activity: { ...base, ...activity } } });
  return { root, el, update: (more) => s.update({ activity: { ...base, ...activity, ...more } }) };
}

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
