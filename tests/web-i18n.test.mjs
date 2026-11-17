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

// the words German and English share, which German's texts have as entries of their own all the same
const SHARED = new Set(["Builds", "in", "Laser", "Marker", "MB", "OK", "Pause", "PIN", "Quiz", "Text", "Whiteboard", "Zoom"]);

// where a catalog says what English says, at any depth - a table's text, a list's, what a function makes of
// numbers -, but for a text of words both languages share (SHARED) or of none (+30 s, ✕); "undefined" is no
// word of a text: a function that looks an argument up in a table (a kind's name, say) makes it of a number
// in every language
function sameAsEnglish(en, other, where = "") {
  const out = [];
  const worded = (s) => typeof s === "string"
    && (s.match(/\p{L}{2,}/gu) || []).some((w) => !SHARED.has(w) && w !== "undefined");
  const made = (f) => {
    try {
      return f(...Array.from({ length: f.length }, (_, i) => i + 2));
    } catch {
      return undefined;                                   // (a function of something else: its shape is checked above)
    }
  };
  for (const [key, a] of Object.entries(en)) {
    const at = where ? `${where}.${key}` : key, b = other[key];
    if (kind(a) === "object" && kind(b) === "object") out.push(...sameAsEnglish(a, b, at));
    else if (kind(a) === "list" && kind(b) === "list") a.forEach((x, i) => { if (worded(x) && x === b[i]) out.push(`${at}[${i}]`); });
    else if (kind(a) === "function" && kind(b) === "function") {
      const [x, y] = [made(a), made(b)];
      if (worded(x) && x === y) out.push(`${at}()`);
    } else if (worded(a) && a === b) out.push(at);
  }
  return out;
}

test("German says it in German: a function's text too", () => {
  const de = texts("de");
  assert.equal(de.phone.join, "Mitspielen");
  assert.equal(de.phone.rank(2, 17), "Platz 2 von 17");
  assert.equal(de.box.rows(1), "1 Zeile");
  assert.equal(de.box.rows(3), "3 Zeilen");
  assert.equal(de.live.joinAt, "Mitmachen unter");
  // where German and English agree on a word (Quiz, PIN), it is still German's own entry - and nothing else
  // German says is English's, however deep it lies (presenter.steps.refused, steps.phase, ...)
  const { meta, ...rest } = CATALOGS.en;
  assert.deepEqual(sameAsEnglish(rest, CATALOGS.de), [], "German texts the same as English - not translated?");
  const looked = (words) => (n, how) => `${n} ${words}${({ added: "?" })[how]}`;   // (a table's key: a number names none)
  assert.deepEqual(sameAsEnglish({ a: { b: ["Bitte", "Same words"] }, f: (n) => `${n} more`, g: looked(""), h: looked("slides ") },
    { a: { b: ["Please", "Same words"] }, f: (n) => `${n} more`, g: looked(""), h: looked("slides ") }), ["a.b[1]", "f()", "h()"]);
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
  const sources = fs.readdirSync(server).filter((f) => f.endsWith(".py")).map((f) => path.join(server, f));
  sources.push(path.join(root, "src/texstage/checks/cleaning.py"));     // what an entry is refused for (Unfit)
  for (const source of sources) {
    const file = path.basename(source);
    const src = fs.readFileSync(source, "utf8");
    for (const m of src.matchAll(/GameError\(\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const m of src.matchAll(/refuse\(\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const m of src.matchAll(/code\s*=\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const line of src.split("\n").filter((l) => /(Refused|PollError|Unfit)\(/.test(l))) {
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
    "name-empty", "recording-too-large", "recording-part", "disconnected", "field", "text", "too-many-polls"]) {
    assert.ok(all.has(code), `the scan finds ${code}`);
  }
  const missing = [...all].filter(([code]) => !PROTOCOL.has(code) && !(code in CATALOGS.en.errors) && !(code in REFUSALS))
    .map(([code, where]) => `${code} (${[...new Set(where)].join(", ")})`);
  assert.deepEqual(missing, []);
  for (const [code, key] of Object.entries(REFUSALS)) assert.ok(key in CATALOGS.en.activity, `${code}: activity.${key}`);
});

// The activity framework's core refuses with codes of its own (activities/, server/activities.py), whose words
// are the page's that meets them: a phone's entry - entries.py, and what a kind's normalize refuses (texstage's
// own kinds, the cleaning the kinds of texstage-kinds-rdf and -sql use) - in the phone's steps.refused, a
// window's control or act - phases.py, moderation.py, views.py, the type - in the windows' presenter.steps.refused
// (stage/activities.js: refusedText). A quiz's code may be the same and say something else (errors).
const CORE = {
  phone: ["activities/entries.py", "activities/kinds/__init__.py", "checks/cleaning.py"],
  window: ["activities/phases.py", "activities/moderation.py", "activities/views.py", "server/activities.py"],
};

function coreCodes() {
  // file (from src/texstage) -> the codes it refuses with: Refused(words, "code"), Unfit(words, "code")
  const src = path.join(root, "src/texstage");
  const files = fs.readdirSync(path.join(src, "activities"), { recursive: true })
    .filter((f) => f.endsWith(".py")).map((f) => `activities/${f.replaceAll("\\", "/")}`);
  files.push("server/activities.py", "checks/cleaning.py");
  const found = new Map();
  for (const file of files) {
    const text = fs.readFileSync(path.join(src, file), "utf8");
    const codes = [...text.matchAll(/\b(?:Refused|Unfit)\(\s*f?"(?:[^"\\\n]|\\.)*"\s*,\s*"([a-z][a-z0-9-]*)"\s*\)/g)]
      .map((m) => m[1]);
    if (codes.length) found.set(file, new Set(codes));
  }
  return found;
}

test("every refusal of the activity framework's core has words on the page that meets it", () => {
  const found = coreCodes();
  for (const [file, code] of [["activities/entries.py", "too-fast"], ["activities/entries.py", "paused"],
    ["activities/entries.py", "closed"], ["activities/phases.py", "revealed"], ["activities/moderation.py", "cycle"],
    ["activities/views.py", "reduction"], ["activities/kinds/__init__.py", "too-large"], ["server/activities.py", "time"],
    ["checks/cleaning.py", "field"]]) {
    assert.ok(found.get(file)?.has(code), `the scan finds ${code} in ${file}`);
  }
  const tables = { phone: CATALOGS.en.steps.refused, window: CATALOGS.en.presenter.steps.refused };
  const missing = [];
  for (const [file, codes] of found) {
    const whose = Object.keys(CORE).find((w) => CORE[w].includes(file));
    assert.ok(whose, `${file} refuses with ${[...codes].join(", ")}: whose words are they - a phone's or a window's (CORE)?`);
    for (const code of codes) if (!PROTOCOL.has(code) && !(code in tables[whose])) missing.push(`${code} (${file}: ${whose})`);
  }
  assert.deepEqual(missing, []);
  // and no words for a code no refusal of theirs has - they would never be said
  for (const [whose, table] of Object.entries(tables)) {
    const said = new Set(CORE[whose].flatMap((file) => [...(found.get(file) || [])]));
    assert.deepEqual(Object.keys(table).filter((code) => !said.has(code)), [], `${whose}: words no refusal says`);
  }
});

test("a window says what the core refused in the core's words, in the deck's language", async () => {
  const { refusedText } = await import(pathToFileURL(path.join(web, "stage/activities.js")).href);
  assert.equal(refusedText("de", { code: "cycle", message: "b is merged into a already" }),
    CATALOGS.de.presenter.steps.refused.cycle);
  assert.equal(refusedText("en", { code: "closed" }), "The activity is not open.");          // not a quiz question's words
  assert.notEqual(refusedText("en", { code: "closed" }), errorText("en", { code: "closed" }));
  assert.equal(refusedText("fr", { code: "too-many" }), CATALOGS.en.presenter.steps.refused["too-many"]);
  for (const err of [{ code: "invalid", message: "no such group" }, { code: "__proto__" }, { code: "toString" }, {}, null,
    new Error("offline")]) {
    assert.equal(refusedText("de", err), null, JSON.stringify(err));                          // errorText says these
  }
});
