// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// texstage's texts (web/i18n), in Node: every language has every text English has - tables,
// lists and functions alike, a function with the same arguments, which it names as English does -,
// says it in its own words, and every text is said somewhere; a tag gets its language or English, a
// refusal its words, a page its deck's language or the browser's, and every code of a refusal the
// server sends a person (server/*.py, shared/client.js, the activity framework's core) has words to
// say it - its code read from the Python as Python writes it.
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
const python = (file) => fs.readFileSync(path.join(root, "src/texstage", file), "utf8");

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

// What a function text makes of its arguments, called with each of PROBES: distinct numbers (the plural's
// branch), the same with 1 first (the singular's), and objects - a refusal's err with its message, a kind's
// message's arguments - with distinct fields: the arguments' marks in its text, in the order it names them;
// "throws" if it throws.
const MARK = /M?7\d\d\d/g;
const PROBES = [(n) => Array.from({ length: n }, (_, i) => 7001 + i), (n) => Array.from({ length: n }, (_, i) => (i ? 7001 + i : 1)),
  (n) => Array.from({ length: n }, (_, i) => ({ message: `M${7001 + i}`, text: `M${7101 + i}`, line: 7201 + i, column: 7301 + i,
    n: 7401 + i }))];
function named(f, args) {
  try {
    return [...new Set(String(f(...args)).match(MARK) || [])].join(" ");
  } catch {
    return "throws";
  }
}

// where a catalog's function names other arguments than English's - one dropped, one added, two swapped -,
// but for the texts whose order German changes on purpose (REORDERED: none so far)
const REORDERED = new Set([]);
function placeholders(en, other, where = "") {
  const out = [];
  for (const [key, a] of Object.entries(en)) {
    const at = where ? `${where}.${key}` : key, b = other?.[key];
    if (kind(a) === "object" && kind(b) === "object") out.push(...placeholders(a, b, at));
    else if (kind(a) === "function" && kind(b) === "function") {
      for (const probe of PROBES) {
        const args = probe(Math.max(a.length, b.length));
        let [x, y] = [named(a, args), named(b, args)];
        if (REORDERED.has(at)) [x, y] = [x, y].map((s) => s.split(" ").sort().join(" "));
        if (x !== y) out.push(`${at}: English names ${x || "nothing"}, this ${y || "nothing"}`);
      }
    }
  }
  return [...new Set(out)];
}

test("a function text names the arguments English's names, in the same order", () => {
  const { meta, ...rest } = CATALOGS.en;
  for (const [tag, catalog] of Object.entries(CATALOGS)) {
    if (tag !== "en") assert.deepEqual(placeholders(rest, catalog), [], `${tag}: a placeholder dropped, added or swapped?`);
  }
  // (the check itself: a number dropped, two swapped, the singular's branch, an error's message)
  assert.deepEqual(placeholders(
    { a: (n) => `${n} checked`, b: (i, n) => `Reference ${i}: the group of ${n}`, c: (n) => `${n} ${n === 1 ? "entry" : "entries"}`,
      d: (err) => `Not taken (${err?.message})`, e: (n, m) => `${n} of ${m}` },
    { a: () => "geprüft", b: (i, n) => `Referenz ${n}: die Gruppe von ${i}`, c: (n) => (n === 1 ? "ein Beitrag" : `${n} Beiträge`),
      d: () => "Nicht angenommen", e: (n, m) => `${n} von ${m}` }),
  ["a: English names 7001, this nothing", "b: English names 7001 7002, this 7002 7001", "d: English names M7001, this nothing"]);
});

// English words that German texts never have: its small words, and the activity framework's - lower case, or
// capitalized at a sentence's start. A command line's options (--yes, --no-stage) are no words of a text.
const ENGLISH = new Set(["the", "is", "are", "were", "be", "been", "has", "have", "had", "and", "or", "of", "to", "at", "on", "by",
  "for", "from", "with", "into", "not", "no", "yes", "your", "you", "this", "that", "these", "those", "it", "its", "they", "them",
  "their", "there", "here", "which", "who", "whoever", "what", "please", "could", "would", "should", "can", "cannot", "does", "did",
  "again", "already", "yet", "than", "only", "every", "any", "some", "many", "much", "each", "more", "one", "two", "nothing", "if",
  "as", "out", "first", "now", "after", "before", "activity", "activities", "entry", "entries", "student", "students", "query",
  "queries", "send", "sent", "lecturer", "reveal", "revealed", "closed", "open", "error", "checked", "waiting", "answer",
  "answers", "question", "questions", "slide", "slides", "game", "players", "nickname", "contributions", "taken", "back",
  "right", "wrong", "result", "results"]);
const englishWords = (s) => (String(s).replace(/--[a-z][a-z-]*/g, "").match(/\p{L}+/gu) || [])
  .filter((w) => ENGLISH.has(w) || (ENGLISH.has(w.toLowerCase()) && w === w[0] + w.slice(1).toLowerCase()));

// where a catalog's text has English words: a string, a list's, what a function makes of numbers - 2, 3, ...; 1
// (the singular's branch); 0 - and of an object of a kind's message's arguments
function englishIn(catalog, where = "") {
  const out = [];
  const say = (at, s) => { const w = englishWords(s); if (w.length) out.push(`${at}: ${[...new Set(w)].join(", ")} - "${s}"`); };
  for (const [key, v] of Object.entries(catalog)) {
    const at = where ? `${where}.${key}` : key;
    if (kind(v) === "object") out.push(...englishIn(v, at));
    else if (kind(v) === "list") v.forEach((x, i) => say(`${at}[${i}]`, x));
    else if (kind(v) === "string") say(at, v);
    else if (kind(v) === "function") {
      for (const args of [Array.from({ length: v.length }, (_, i) => i + 2), Array.from({ length: v.length }, () => 1),
        Array.from({ length: v.length }, () => 0), [{ line: 2, column: 3, message: "", n: 4, text: "" }]]) {
        let s = "";
        try {
          s = String(v(...args));
        } catch { /* (a function of something else) */ }
        say(`${at}()`, s.replace(/undefined|\[object Object\]/g, ""));
      }
    }
  }
  return [...new Set(out)];
}

// the kinds' own words (web/kinds.js): texstage's own kinds' and those of the kinds' packages in kinds/
const KIND_TEXTS = [path.join(root, "src/texstage/activities/kinds/texts"),
  ...fs.readdirSync(path.join(root, "kinds"), { withFileTypes: true }).filter((d) => d.isDirectory())
    .flatMap((d) => fs.readdirSync(path.join(root, "kinds", d.name, "src"), { withFileTypes: true })
      .filter((p) => p.isDirectory() && fs.existsSync(path.join(root, "kinds", d.name, "src", p.name, "texts", "en.js")))
      .map((p) => path.join(root, "kinds", d.name, "src", p.name, "texts")))];
const kindTexts = async (dir, tag) => (await import(pathToFileURL(path.join(dir, `${tag}.js`)).href)).default;

test("German says it in German: no English words, a function's text and the kinds' words too", async () => {
  const { meta, ...rest } = CATALOGS.de;
  assert.deepEqual(englishIn(rest), [], "English words in German texts - half translated?");
  assert.ok(KIND_TEXTS.length >= 3, KIND_TEXTS.join(", "));
  for (const dir of KIND_TEXTS) {
    const [en, de] = [await kindTexts(dir, "en"), await kindTexts(dir, "de")];
    const where = path.relative(root, dir);
    assert.deepEqual(differences(en, de), [], where);
    assert.deepEqual(englishIn(de), [], where);
    assert.deepEqual(sameAsEnglish(en, de), [], where);
    assert.deepEqual(placeholders(en, de), [], where);
  }
  // (the check itself: half English, English in a singular's branch alone, a sentence's capital; German's own words pass)
  assert.deepEqual(englishIn({ a: "The activity is not offen.", b: (n) => `${n} ${n === 1 ? "entry" : "Beiträge"}`,
    c: "Was bisher geschickt wurde, zählt nicht mehr.", d: "mit --yes löscht es; ohne --no-stage", e: ["Please wait"] })
    .map((x) => x.split(":")[0]), ["a", "b()", "e[0]"]);
});

// The pages' code (web/, but its texts and the vendors'), where a text is said: by its key's name - T.x.name,
// ["name"], or the name as a string a table is looked up with
function pagesCode() {
  const files = [];
  const walk = (dir) => {
    for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, f.name);
      if (f.isDirectory()) { if (!["i18n", "vendor"].includes(f.name)) walk(p); } else if (/\.(m?js|html)$/.test(f.name)) files.push(p);
    }
  };
  walk(web);
  return files.map((f) => fs.readFileSync(f, "utf8")).join("\n");
}

// the tables a page looks up by a value - their keys are its values, not names in the code: the refusals' (by
// their codes: the tests below), the server's checks' words (checks/texts.py says them too, which test_checks.py
// compares), a build's source (the server's: app.py), and those whose values the Python names (VALUES)
const LOOKED_UP = ["errors", "steps.refused", "presenter.steps.refused", "presenter.builds.source"];
const tuple = (file, name) => {
  const m = python(file).match(new RegExp(`^${name} = \\(([^)]*)\\)`, "m"));
  assert.ok(m, `${file}: ${name}`);
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
};
const VALUES = {
  "box.verdict": tuple("activities/kind.py", "VERDICTS"), "steps.verdict": tuple("activities/kind.py", "VERDICTS"),
  "box.status2": tuple("activities/kind.py", "STATUSES"), "steps.status": tuple("activities/kind.py", "STATUSES"),
  "steps.state": tuple("activities/entries.py", "STATES").filter((s) => s !== "in"),        // (in: no word of its own)
  "presenter.steps.act": tuple("activities/moderation.py", "ACTS"),
  "presenter.steps.phase": tuple("activities/phases.py", "PHASES"),
  "steps.phase": tuple("activities/phases.py", "PHASES").filter((p) => p !== "open"),      // (open: the phone's input)
};
const SERVER_WORDS = [...python("checks/texts.py").split('"de": {')[0].matchAll(/^\s+"(\w+)": "/gm)].map((m) => m[1]);

// the texts whose key's name the pages' code never has - none of a table looked up by a value
function unsaid(catalog, code, where = "") {
  const out = [];
  for (const [key, v] of Object.entries(catalog)) {
    const at = where ? `${where}.${key}` : key;
    if (LOOKED_UP.includes(at) || at in VALUES) continue;
    if (kind(v) === "object") {
      out.push(...unsaid(v, code, at));
      continue;
    }
    if (where === "engines" && SERVER_WORDS.includes(key)) continue;
    const k = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (!new RegExp(`\\.${k}\\b|\\[\\s*["'\`]${k}["'\`]\\s*\\]|["'\`]${k}["'\`]`).test(code)) out.push(at);
  }
  return out;
}

test("every text is said: its name is in the pages' code, a table looked up by a value has its values' keys", () => {
  const { meta, ...rest } = CATALOGS.en;
  assert.ok(SERVER_WORDS.includes("tooDeep") && SERVER_WORDS.includes("at"), SERVER_WORDS.join(", "));
  assert.deepEqual(unsaid(rest, pagesCode()), [], "texts nobody says - left over, or said under another name?");
  for (const [at, values] of Object.entries(VALUES)) {
    const table = at.split(".").reduce((t, k) => t[k], CATALOGS.en);
    assert.deepEqual(Object.keys(table).sort(), [...values].sort(), `${at}: a word for each value it is looked up by`);
  }
  // (the check itself: a key nobody names is found, one in a looked-up table is not)
  assert.deepEqual(unsaid({ a: { lead: "x", neverUsed: "y" }, errors: { "no-such": "z" } }, "W.a.lead"), ["a.neverUsed"]);
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

// ------------------------------------------------------------------ the refusals in the Python
// A refusal's code, read as Python writes it: the calls of a refusal's class (REFUSING) - under any name a
// module imports it as (from ... import Refused as CoreRefused) -, their arguments split as Python splits them,
// strings in every form (either quote, tripled, a prefix, an f-string's fields, over several lines) and
// comments skipped. The code is the second argument or code=, a plain string - without one the class's
// default, invalid. A code that is anything else the scan cannot read, and says so - but where a refusal passes
// on another's code, which is read where that one is raised (PASSED).
const REFUSING = ["Refused", "Unfit", "PollError"];
const PASSED = ["server/activities.py: e.code",           // _refused: the core's refusal as the type's (hook.py)
  "server/activity.py: e.code"];                         // F1's: what cleaning.py refused (Unfit) as its own
const QUOTE = /^([rRbBuUfF]{0,2})('''|"""|'|")/;
const CLOSING = { "(": ")", "[": "]", "{": "}" };

function stringAt(src, i) {
  // whether a string starts at i: a quote, or a prefix and a quote that are no name's end
  const m = QUOTE.exec(src.slice(i, i + 5));
  return Boolean(m) && (m[1] === "" || !/\w/.test(src[i - 1] || ""));
}

function stringEnd(src, i) {
  // where the string at i ends, -1 if it does not: an f-string's fields are expressions, strings and all
  const m = QUOTE.exec(src.slice(i, i + 5));
  const quote = m[2], f = /f/i.test(m[1]);
  let j = i + m[0].length;
  while (j < src.length) {
    if (src[j] === "\\") j += 2;
    else if (src.startsWith(quote, j)) return j + quote.length;
    else if (quote.length === 1 && src[j] === "\n") return -1;
    else if (f && src[j] === "{" && src[j + 1] !== "{") {
      j = groupEnd(src, j + 1, "}");
      if (j < 0) return -1;
    } else j += f && src[j] === "{" ? 2 : 1;
  }
  return -1;
}

function groupEnd(src, i, close) {
  // where a group that opened before i ends, after its closing bracket - -1 if it does not
  const want = [close];
  while (i < src.length) {
    const c = src[i];
    if (c === "#") {
      const end = src.indexOf("\n", i);
      i = end < 0 ? src.length : end;
    } else if (stringAt(src, i)) {
      i = stringEnd(src, i);
      if (i < 0) return -1;
    } else if (CLOSING[c]) {
      want.push(CLOSING[c]);
      i += 1;
    } else {
      i += 1;
      if (c === want[want.length - 1]) want.pop();
      if (!want.length) return i;
    }
  }
  return -1;
}

function splitArgs(text) {
  // a call's arguments, as Python splits them: at the commas outside brackets and strings, without comments
  const out = [];
  let depth = 0, arg = "", i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === "#") {
      const end = text.indexOf("\n", i);
      i = end < 0 ? text.length : end;
      continue;
    }
    if (stringAt(text, i)) {
      const end = stringEnd(text, i);
      arg += text.slice(i, end);
      i = end;
      continue;
    }
    if ("([{".includes(c)) depth += 1;
    else if (")]}".includes(c)) depth -= 1;
    if (c === "," && depth === 0) {
      out.push(arg.trim());
      arg = "";
    } else arg += c;
    i += 1;
  }
  out.push(arg.trim());
  return out.filter(Boolean);
}

function pythonCalls(src, names) {
  // the calls of these names in a module's source - and of the names it imports them as -: [{name, line, args}]
  const known = new Set(names);
  for (const m of src.matchAll(/^\s*from\s+[\w.]+\s+import\s+(\([^)]*\)|[^\n]*)/gm)) {
    for (const a of m[1].matchAll(/\b(\w+)\s+as\s+(\w+)/g)) if (known.has(a[1])) known.add(a[2]);
  }
  for (const m of src.matchAll(/^(\w+)\s*=\s*(\w+)\s*$/gm)) if (known.has(m[2])) known.add(m[1]);
  const line = (i) => src.slice(0, i).split("\n").length;
  const calls = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === "#") {
      const end = src.indexOf("\n", i);
      i = end < 0 ? src.length : end;
    } else if (stringAt(src, i)) {
      const end = stringEnd(src, i);
      assert.ok(end > 0, `a string the scan cannot read, line ${line(i)}`);
      i = end;
    } else if (/[A-Za-z_]/.test(c)) {
      const name = /^\w+/.exec(src.slice(i, i + 200))[0];
      const open = /^\s*\(/.exec(src.slice(i + name.length, i + name.length + 40));
      if (known.has(name) && open && !/\b(?:class|def)\s+$/.test(src.slice(Math.max(0, i - 12), i))) {
        const from = i + name.length + open[0].length, to = groupEnd(src, from, ")");
        assert.ok(to > 0, `a call the scan cannot read, line ${line(i)}`);
        calls.push({ name, line: line(i), args: splitArgs(src.slice(from, to - 1)) });
      }
      i += name.length;                                   // (on into its arguments: a call in a call)
    } else i += 1;
  }
  return calls;
}

function givenCode(call) {
  // what a refusal's call gives for its code: its second argument, or code= - undefined if neither
  const keyword = call.args.find((a) => /^code\s*=(?!=)/.test(a));
  return keyword ? keyword.replace(/^code\s*=\s*/, "") : call.args.filter((a) => !/^\w+\s*=(?!=)/.test(a))[1];
}

function codeOf(call) {
  // a refusal's code: a plain string given for it - "invalid" without one, null if anything else (*args too)
  const given = givenCode(call);
  if (given === undefined) return call.args.some((a) => a.startsWith("*")) ? null : "invalid";
  return /^[uU]?(["'])([a-z][a-z0-9-]*)\1$/.exec(given)?.[2] ?? null;
}

function refusals(file) {
  // a module's refusals (file from src/texstage): [{line, code, given}] - code null where the scan cannot read it
  return pythonCalls(python(file), REFUSING).map((call) => ({ line: call.line, code: codeOf(call), given: givenCode(call) }));
}

// the modules whose refusals reach a person: the server's, what an entry is refused for (Unfit), the activity
// framework's core
const SCANNED = () => [...fs.readdirSync(path.join(root, "src/texstage/server")).filter((f) => f.endsWith(".py")).map((f) => `server/${f}`),
  "checks/cleaning.py", ...fs.readdirSync(path.join(root, "src/texstage/activities"), { recursive: true })
    .filter((f) => f.endsWith(".py")).map((f) => `activities/${f.replaceAll("\\", "/")}`)];

test("the scan reads every refusal's code, however the Python writes it", () => {
  const unread = SCANNED().flatMap((file) => refusals(file).filter((r) => r.code === null).map((r) => `${file}: ${r.given}`));
  assert.deepEqual(unread.filter((x) => !PASSED.includes(x)), [], "a code that is no plain string: whose words would say it?");
  assert.deepEqual(PASSED.filter((x) => !unread.includes(x)), [], "PASSED: a code passed on that is no longer there");
  // (the scan itself: each way to write a refusal - and what is none)
  const src = [
    "from texstage.activities.phases import Refused as CoreRefused  # Refused('in a comment', 'no')",
    "class Refused(ValueError):",
    '    """Refused("in a docstring", "no")"""',
    "raise Refused('off: true or false', 'single')",
    'raise Refused("off: \\"true\\" or false", "escaped")',
    'raise Refused("off: " + str(off), "joined")',
    'raise Refused("off: true "',
    '              "or false",    # the words, over two lines',
    '              "implicit")',
    'raise Refused("off", code="keyword")',
    'raise Refused(f"{a(\'x\')}: {\', \'.join(ACTS)} {{n}}", "fstring")',
    'raise CoreRefused("on: true or false", "aliased")',
    'raise phases.Refused("x", "dotted")',
    'raise Refused("off")',
    'raise Refused("off", "off" + "-bad")',
    'raise Refused("off", e.code)',
    "isinstance(x, Refused)",
  ].join("\n");
  assert.deepEqual(pythonCalls(src, REFUSING).map(codeOf),
    ["single", "escaped", "joined", "implicit", "keyword", "fstring", "aliased", "dotted", "invalid", null, null]);
});

// the codes of the refusals the server and the client make (their source)
function codes() {
  const found = new Map();
  const add = (code, where) => found.set(code, [...(found.get(code) || []), where]);
  const server = path.join(root, "src/texstage/server");
  const sources = fs.readdirSync(server).filter((f) => f.endsWith(".py")).map((f) => `server/${f}`);
  sources.push("checks/cleaning.py");                                // what an entry is refused for (Unfit)
  for (const source of sources) {
    const file = path.basename(source);
    const src = python(source);
    for (const m of src.matchAll(/GameError\(\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const m of src.matchAll(/refuse\(\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const m of src.matchAll(/code\s*=\s*"([a-z][a-z0-9-]*)"/g)) add(m[1], file);
    for (const r of refusals(source)) if (r.code) add(r.code, file);
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
  // file (from src/texstage) -> the codes it refuses with, but invalid: Refused(words, "code"), Unfit(words, code="code")
  const files = SCANNED().filter((f) => f.startsWith("activities/"));
  files.push("server/activities.py", "checks/cleaning.py");
  const found = new Map();
  for (const file of files) {
    const codes = refusals(file).map((r) => r.code).filter((code) => code && code !== "invalid");
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
  for (const err of [{ code: "invalid", message: "act: one of hide, approve" }, { code: "__proto__" }, { code: "toString" }, {},
    null, new Error("offline")]) {
    assert.equal(refusedText("de", err), null, JSON.stringify(err));                          // errorText says these
  }
  // a window speaks to the lecturer, a phone to the student: no window's refusal says what a phone's text says
  const strings = (o) => Object.values(o).flatMap((v) => (kind(v) === "object" ? strings(v) : kind(v) === "string" ? [v] : []));
  for (const [tag, catalog] of Object.entries(CATALOGS)) {
    const phone = new Set([...strings(catalog.steps), ...strings(catalog.activity), ...strings(catalog.phone)]);
    for (const [code, words] of Object.entries(catalog.presenter.steps.refused)) {
      assert.ok(!phone.has(words), `${tag}: presenter.steps.refused.${code} says what a phone says: "${words}"`);
    }
  }
});
