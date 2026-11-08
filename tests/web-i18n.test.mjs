// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// texstage's texts (web/i18n), in Node: every language has every text English has - tables,
// lists and functions alike, a function with the same arguments -, a tag gets its language or
// English, a refusal its words, a page its deck's language or the browser's, and every code of a
// refusal the server sends a person (server/*.py, shared/client.js) has words to say it.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const web = path.join(root, "src/texstage/web");
const i18n = await import(pathToFileURL(path.join(web, "i18n/i18n.js")).href);
const { CATALOGS, browserLanguage, errorText, languageOf, pageLanguage, pageTexts, supported, texts, usePageLanguage } = i18n;
const { REFUSALS } = await import(pathToFileURL(path.join(web, "play/activity.js")).href);

const kind = (v) => (Array.isArray(v) ? "list" : v === null ? "null" : typeof v);

// where a catalog's texts differ from English's in shape: missing or extra, another kind, a
// list of another length, a function of other arguments
function differences(en, other, where = "") {
  const out = [];
  for (const key of new Set([...Object.keys(en), ...Object.keys(other)])) {
    const at = where ? `${where}.${key}` : key;
    if (!(key in other)) { out.push(`${at}: missing`); continue; }
    if (!(key in en)) { out.push(`${at}: not in English`); continue; }
    const [a, b] = [en[key], other[key]];
    if (kind(a) !== kind(b)) out.push(`${at}: ${kind(b)}, English has a ${kind(a)}`);
    else if (kind(a) === "object") out.push(...differences(a, b, at));
    else if (kind(a) === "list" && a.length !== b.length) out.push(`${at}: ${b.length} items, English ${a.length}`);
    else if (kind(a) === "function" && a.length !== b.length) out.push(`${at}: ${b.length} arguments, English ${a.length}`);
    else if (kind(a) === "string" && !b.trim()) out.push(`${at}: empty`);
  }
  return out;
}

test("every language has every text English has, of the same kind", () => {
  assert.ok(Object.keys(CATALOGS).includes("en") && Object.keys(CATALOGS).includes("de"));
  for (const [tag, catalog] of Object.entries(CATALOGS)) {
    if (tag !== "en") assert.deepEqual(differences(CATALOGS.en, catalog), [], tag);
  }
  for (const area of ["meta", "live", "box", "phone", "activity", "errors"]) assert.ok(area in CATALOGS.en, area);
  assert.equal(texts("de").meta.locale, "de-DE");
  assert.equal(texts("en").meta.locale, "en-GB");
});

test("German says it in German: a function's text too", () => {
  const de = texts("de");
  assert.equal(de.phone.join, "Mitspielen");
  assert.equal(de.phone.rank(2, 17), "Platz 2 von 17");
  assert.equal(de.box.rows(1), "1 Zeile");
  assert.equal(de.box.rows(3), "3 Zeilen");
  assert.equal(de.live.joinAt, "Mitmachen unter");
  // where German and English agree on a word (Quiz, PIN), it is still German's own entry
  for (const [area, table] of Object.entries(de)) {
    if (area === "meta") continue;
    const same = Object.entries(table).filter(([key, v]) => typeof v === "string" && v === CATALOGS.en[area][key]
      && v.length > 12);
    assert.deepEqual(same, [], `${area}: long texts the same as English - not translated?`);
  }
});

test("a tag gets its language, any other English; nothing comes from a prototype", () => {
  for (const tag of ["de", "DE", "de-AT", "de_CH", " de-DE "]) assert.equal(languageOf(tag), "de", tag);
  for (const tag of [undefined, null, "", "en", "en-US", "fr", "__proto__", "constructor", "toString", "-de"]) {
    assert.equal(languageOf(tag), "en", String(tag));
  }
  assert.equal(supported("fr"), null);
  assert.equal(supported("de-AT"), "de");
  assert.equal(texts("fr"), texts("en"));
  assert.equal(texts("de-AT"), texts("de"));
  assert.ok(Object.isFrozen(texts("de")));
});

test("a refusal's words: its code's, else the server's after a sentence that it did not work", () => {
  assert.equal(errorText("de", { code: "unknown-pin", message: "no game with this PIN" }), "Es gibt kein Spiel mit dieser PIN.");
  assert.equal(errorText("en", { code: "unknown-pin" }), "No game with this PIN.");
  assert.equal(errorText("de", { code: "bad-bundle", message: "deck.json is too large" }),
    "Das ist keine .bundle.zip eines Foliensatzes (deck.json is too large).");
  assert.equal(errorText("de", { code: "invalid", message: "zoom: {x, y, w, h}" }), "Das hat nicht geklappt: zoom: {x, y, w, h}");
  assert.equal(errorText("en", { code: "__proto__", message: "x" }), "That did not work: x");
  assert.equal(errorText("de", new Error("offline")), "Das hat nicht geklappt: offline");
  assert.equal(errorText("de", {}), "Das hat nicht geklappt.");
  assert.equal(errorText("fr", { code: "full" }), "The game is full.");
});

test("a page speaks its deck's language, without one the browser's first that texstage speaks", () => {
  const nav = (languages, language = languages[0]) =>
    Object.defineProperty(globalThis, "navigator", { value: { languages, language }, configurable: true });
  nav(["fr-FR", "de-DE", "en"]);
  assert.equal(browserLanguage(), "de");
  nav(["fr-FR", "nl"]);
  assert.equal(browserLanguage(), "en");
  nav([], "de-AT");
  assert.equal(browserLanguage(), "de");
  assert.equal(pageLanguage(), "de");                         // no deck: the browser's
  assert.equal(usePageLanguage("en").phone.join, "Join");     // an English deck
  assert.equal(pageLanguage(), "en");
  assert.equal(pageTexts(), texts("en"));
  assert.equal(usePageLanguage(null), texts("de"));           // back to the decks: the browser's
  assert.equal(usePageLanguage("fr"), texts("en"));           // a deck in another language: English
});

// the codes of the refusals the server and the client make (their source)
function codes() {
  const found = new Map();
  const add = (code, where) => found.set(code, [...(found.get(code) || []), where]);
  const server = path.join(root, "src/texstage/server");
  for (const file of fs.readdirSync(server).filter((f) => f.endsWith(".py"))) {
    const src = fs.readFileSync(path.join(server, file), "utf8");
    for (const m of src.matchAll(/GameError\(\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const m of src.matchAll(/refuse\(\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const m of src.matchAll(/code\s*=\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const line of src.split("\n").filter((l) => /(Refused|PollError)\(/.test(l))) {
      const m = line.match(/,\s*"([a-z][a-z0-9-]*)"\)\s*(?:#.*)?$/);
      if (m) add(m[1], file);
    }
    for (const m of src.matchAll(/self\.code = "([a-z][a-z0-9-]*)" if .* else "([a-z][a-z0-9-]*)"/g)) {
      add(m[1], file);
      add(m[2], file);
    }
  }
  const client = fs.readFileSync(path.join(web, "shared/client.js"), "utf8");
  for (const m of client.matchAll(/code: (?:m\.reason \|\| )?"([a-z][a-z0-9-]*)"/g)) add(m[1], "client.js");
  return found;
}

// codes no person meets in normal use - a window or a page that sends what it should not; their
// words are the server's after "That did not work" (errorText)
const PROTOCOL = new Set(["invalid", "unknown-command", "hello-first", "bad-json", "internal", "not-evaluator"]);

test("every refusal a person can meet has words in every language", () => {
  const all = codes();
  for (const code of ["unknown-pin", "nickname-taken", "kicked", "qa-own", "poll-question", "key-required", "deck-running",
    "name-empty", "recording-too-large", "recording-part", "disconnected", "field", "too-many-polls"]) {
    assert.ok(all.has(code), `the scan finds ${code}`);
  }
  const missing = [...all].filter(([code]) => !PROTOCOL.has(code) && !(code in CATALOGS.en.errors) && !(code in REFUSALS))
    .map(([code, where]) => `${code} (${[...new Set(where)].join(", ")})`);
  assert.deepEqual(missing, []);
  for (const [code, key] of Object.entries(REFUSALS)) assert.ok(key in CATALOGS.en.activity, `${code}: activity.${key}`);
});
