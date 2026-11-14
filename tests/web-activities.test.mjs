// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The activity framework in the browser (the plan of F2, package 8), in Node: what the phone's step screen
// says of an entry - sending, received, being checked, what its check said in the kind's words, after the
// reveal its verdict -, its time and its ids; what the box calls a group; the kinds' texts as a phone says
// them (kinds.js); the controls as keys of the presenter window; and the lead window's agent - the
// projector never lays out, a presenter window that is told another leads follows it until the lead could
// have ended.
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = (rel) => pathToFileURL(path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web", rel)).href;
Object.defineProperty(globalThis, "navigator", { value: { language: "en-GB", languages: ["en-GB"] }, configurable: true });
const phone = await import(web("play/activities.js"));
const stage = await import(web("stage/activities.js"));
const { Kinds, Hints, HINT_MS, textsPath } = await import(web("kinds.js"));
const { ActsLine } = await import(web("host/acts.js"));
const { texts } = await import(web("i18n/i18n.js"));
const sqlTexts = (await import(pathToFileURL(path.join(path.dirname(fileURLToPath(import.meta.url)),
  "../kinds/texstage-kinds-sql/src/texstage_kinds_sql/texts/en.js")).href)).default;
const rdfDe = (await import(pathToFileURL(path.join(path.dirname(fileURLToPath(import.meta.url)),
  "../kinds/texstage-kinds-rdf/src/texstage_kinds_rdf/texts/de.js")).href)).default;

test("an entry's id is one the server takes, and new each time", () => {
  const ids = new Set(Array.from({ length: 200 }, () => phone.entryId()));
  assert.equal(ids.size, 200);
  for (const id of ids) assert.match(id, /^[A-Za-z0-9_-]{8,40}$/);
});

test("a step's time: what is left of it as the server read it, and a clock", () => {
  assert.equal(phone.timeLeft({ phase: "open", time: null }, 5000), null);
  assert.equal(phone.timeLeft({ phase: "open", time: 60_000, since: 1000 }, 11_000), 50_000);
  assert.equal(phone.timeLeft({ phase: "open", time: 5000, since: 1000 }, 99_000), 0);
  assert.equal(phone.timeLeft({ phase: "paused", time: 42_000, since: 1000 }, 99_000), 42_000);    // the time waits
  assert.deepEqual([phone.clock(0), phone.clock(59_001), phone.clock(60_000), phone.clock(125_000)], ["0:00", "1:00", "1:00", "2:05"]);
});

test("what an entry's state says - in the deck's language, the check's message in the kind's words", () => {
  const L = texts("en").steps;
  const kinds = new Kinds({}, "en");
  kinds.texts["sql-query"] = sqlTexts;
  const say = (m) => kinds.say("sql-query", m);
  const code = { input: "code" }, fields = { input: "fields" };
  const said = (entry, step = code) => phone.said(entry, step, L, say);
  assert.deepEqual(said({ check: "sending", state: "in" }), { words: "Sending …", cls: "" });
  assert.deepEqual(said({ state: "in" }), { words: "Received", cls: "" });                    // (feedback=none)
  assert.deepEqual(said({ check: "waiting", state: "in" }), { words: "Being checked …", cls: "" });
  assert.deepEqual(said({ check: "unchecked", state: "in" }), { words: "Could not be checked - not your fault.", cls: "" });
  assert.deepEqual(said({ check: "checked", status: "ok", state: "in" }), { words: "It runs ✓", cls: "good" });
  assert.deepEqual(said({ check: "checked", status: "ok", state: "in" }, fields), { words: "In ✓", cls: "good" });
  assert.deepEqual(said({ check: "checked", status: "error", state: "in", message: { code: "engine", args: { text: "no such table: t" } } }),
    { words: "Error: no such table: t", cls: "bad" });
  assert.deepEqual(said({ check: "checked", status: "invalid", state: "in", message: { code: "queriesOnly", args: {} } }),
    { words: "Syntax error: only queries are run: SELECT, VALUES or WITH ... SELECT", cls: "bad" });
  assert.deepEqual(said({ check: "checked", status: "ok", state: "replaced", verdict: "correct" }),
    { words: "replaced by a later one · It runs ✓ · Right ✓", cls: "good" });
  assert.deepEqual(said({ check: "checked", status: "ok", state: "in", verdict: "incorrect" }),
    { words: "It runs ✓ · Not right", cls: "bad" });
  assert.equal(kinds.say("sql-query", { code: "nowhere", args: {} }), "nowhere");          // a code without words: as it is
  assert.equal(kinds.say("no-kind", { code: "at", args: {} }), "at");
});

test("the kinds' texts: German where the deck is, made with the message's arguments", () => {
  const kinds = new Kinds({}, "de");
  kinds.texts["sparql-query"] = rdfDe;
  assert.equal(kinds.say("sparql-query", { code: "at", args: { line: 2, column: 7, message: "erwartet WHERE" } }),
    "Zeile 2, Spalte 7: erwartet WHERE");
  assert.equal(kinds.say("sparql-query", { code: "tooDeep", args: { n: 200 } }), "mehr als 200 Ebenen tief verschachtelt");
});

test("what the box calls a group: its result, else what went wrong; an entry's input as a line", () => {
  const w = texts("en").box;
  assert.equal(stage.groupLabel({ status: "ok", detail: { kind: "select", count: 3 } }, w), "3 rows");
  assert.equal(stage.groupLabel({ status: "ok", detail: { kind: "graph", count: 1 } }, w), "1 triple");
  assert.equal(stage.groupLabel({ status: "ok", detail: { kind: "ask", boolean: true } }, w), "yes");
  assert.equal(stage.groupLabel({ status: "ok", example: { text: "B" } }, w), "B");           // (a tally's choice)
  assert.equal(stage.groupLabel({ status: "invalid" }, w), "syntax error");
  assert.equal(stage.groupLabel({ status: "internal" }, w), "could not be checked");
  assert.equal(stage.shownText({ fields: ["Ada", "<b>"] }), "Ada · <b>");                       // (text: escaped where drawn)
  assert.equal(stage.shownText({ text: "SELECT 1" }), "SELECT 1");
  assert.equal(stage.shownText({ text: "\n  \n\tSELECT 1\n\nFROM t" }), "\tSELECT 1\n\nFROM t");      // (a comment was there)
  assert.equal(stage.shownText(null), "");
});

test("the controls as keys of the presenter window: what each is for in each phase, and what it sends", async () => {
  const at = (phase) => ["o", "c", "s", "r", "x", "+", "-", "q"].map((k) => stage.keyAct(k, phase));
  assert.deepEqual(at("ready"), ["open", null, null, "reveal", null, null, null, null]);
  assert.deepEqual(at("open"), [null, "close", "pause", "reveal", "reset", "more", "notime", null]);
  assert.deepEqual(at("paused"), ["resume", "close", "resume", "reveal", "reset", "more", "notime", null]);
  assert.deepEqual(at("closed"), ["open", null, null, "reveal", "reset", null, null, null]);
  assert.deepEqual(at("revealed"), [null, null, null, null, "reset", null, null, null]);
  assert.deepEqual(at(undefined), [null, null, null, null, null, null, null, null]);         // (no picture yet)
  assert.equal(stage.keyAct("O", "ready"), "open");                                          // either case
  const sent = [];
  let yes = false;
  const env = { send: (m) => sent.push(m), ask: async () => yes, words: texts("en").presenter.steps };
  await stage.stepAct(env, "q1", "more");
  await stage.stepAct(env, "q1", "notime");
  await stage.stepAct(env, "q1", "reveal");                                                  // asked, and not wanted
  yes = true;
  await stage.stepAct(env, "q1", "reset");
  await stage.stepAct(env, "q1", "pause");
  assert.deepEqual(sent, [{ t: "activity.time", activity: "q1", add: 30 }, { t: "activity.time", activity: "q1", stop: true },
    { t: "activity.reset", activity: "q1" }, { t: "activity.pause", activity: "q1" }]);
});

// ------------------------------------------------------------------ a stand-in for the browser's DOM
// What the screens, the box and the panel ask of it: an element per selector, kept; innerHTML as written;
// listeners kept, to be called by the tests. Not HTML - what the code does with the elements.
function element() {
  const kids = new Map();
  const e = {
    innerHTML: "", textContent: "", value: "", hidden: false, disabled: false, inert: false, dataset: {}, style: {},
    options: [], listeners: {}, selectionStart: 0, selectionEnd: 0, attrs: {}, classes: new Set(),
    setAttribute(name, value) { this.attrs[name] = String(value); },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    querySelector(sel) { if (!kids.has(sel)) kids.set(sel, element()); return kids.get(sel); },
    querySelectorAll(sel) { return [this.querySelector(sel)]; },
    append() {}, remove() {}, focus() {}, closest() { return null; },
  };
  e.classList = { toggle: (name, on) => { if (on ?? !e.classes.has(name)) e.classes.add(name); else e.classes.delete(name); } };
  return e;
}
globalThis.document = { createElement: () => element() };
const later = (ms = 0) => new Promise((ok) => setTimeout(ok, ms));

test("the lead window: the server's word - this window, another, nobody - and the positions it follows", async () => {
  const sent = [];
  let lead = false;
  const agent = new stage.StepAgent({ send: (msg) => { sent.push(msg); return Promise.resolve({ lead }); }, role: "presenter" });
  const view = agent.forBox("graph");
  const box = { id: "graph", own: new Map([["a", [0.1, 0.2]]]), sim: {}, drawn: 0, draw() { this.drawn += 1; } };
  view.attach(box);
  assert.equal(view.leads(), true);                                                     // (nobody said otherwise)
  view.layout("graph", new Map([["a", [0.1, 0.2]]]));
  await later(20);
  assert.deepEqual(sent, [{ t: "activity.layout", activity: "graph", at: { a: [0.1, 0.2] } }]);
  assert.equal(view.leads(), false);                                                    // told: another leads
  assert.equal(box.own.size, 0, "its own positions are dropped: it follows the picture's");
  assert.equal(box.sim, null);
  assert.equal(box.drawn, 1);
  view.layout("graph", new Map([["a", [0.3, 0.2]]]));                                   // ... so it sends nothing
  await later(600);
  assert.equal(sent.length, 1);
  view.seen(false);                                                                     // a picture: another still leads
  assert.equal(view.leads(), false, "no clock gives it the lead back - only the server's word");
  view.seen(null);                                                                      // nobody leads: it may
  assert.equal(view.leads(), true);
  lead = true;
  view.layout("graph", new Map([["a", [0.5, 0.5]]]));
  await later(20);
  assert.equal(sent.length, 2);
  view.seen(true);
  assert.equal(view.leads(), true);
  agent.destroy();
  const projector = new stage.StepAgent({ send: () => Promise.reject(new Error("read-only")), role: "projector" });
  assert.equal(projector.forBox("graph").leads(), false);
});

test("the box: the projector's picture in both windows; the controls' keys in the presenter window alone", async () => {
  const reads = [], sent = [];
  const host = (role) => ({
    role, read: (msg) => { reads.push(msg); return Promise.resolve({ picture: { phase: "open", groups: [], students: 0, entries: 0 }, lead: null }); },
    send: (msg) => sent.push(msg), ask: async () => true });
  const box = new stage.StepBox({ id: "q", item: { kind: "sql-query" }, layer: element(), host: host("presenter"), language: "en" });
  box.update({ stage: { activity: { items: { q: { version: 1, layout: 0 } } } } });
  await later(10);
  assert.deepEqual(reads, [{ t: "activity.view", activity: "q", window: "display" }]);
  assert.match(box.el.innerHTML, /0 students/);
  assert.equal(box.key("c"), true);                                                     // close, in the presenter window
  assert.equal(box.key("q"), false);
  await later(10);
  assert.deepEqual(sent, [{ t: "activity.close", activity: "q" }]);
  const projected = new stage.StepBox({ id: "q", item: { kind: "sql-query" }, layer: element(), host: host("projector"), language: "en" });
  projected.update({ stage: { activity: { items: { q: { version: 1, layout: 0 } } } } });
  await later(10);
  assert.equal(projected.key("c"), false, "the projector's box takes no key");
  assert.equal(sent.length, 1);
});

test("the panel: another activity picked while a picture comes is asked for, and nothing of the first is left", async (t) => {
  const reads = [];
  const answers = [];
  const env = {
    dock() {}, undock() {}, ask: async () => true, language: "en", kinds: null, now: () => 0, onSlide: () => null,
    items: () => ({ query: { kind: "sql-query" }, crowd: { kind: "triples" } }),
    state: () => ({ stage: { activity: { current: "query", items: { query: { phase: "open", version: 2, epoch: 0 },
      crowd: { phase: "open", version: 5, epoch: 0 } } } } }),
    send() { return Promise.resolve({}); },
    read(msg) { reads.push(msg.activity); return new Promise((ok) => answers.push(ok)); },
  };
  const panel = stage.openStepPanel(env);
  t.after(() => panel.close());
  assert.deepEqual(reads, ["query"]);
  const pick = panel.el.querySelector("#actpick"), body = panel.el.querySelector("#actbody");
  body.innerHTML = "the query's groups";
  pick.onchange({ target: { value: "crowd" } });                                        // picked while the query's comes
  assert.equal(body.innerHTML, "", "no button of the query's stays for the graph");
  answers[0]({ picture: { phase: "open", groups: [], references: [{ failed: "invalid" }] } });
  await later(10);
  assert.deepEqual(reads, ["query", "crowd"], "the graph's picture is asked for");
  answers[1]({ picture: { kind: "graph", phase: "open", terms: [{ role: "node", key: ":A", label: ":A", n: 2 }], nodes: [], edges: [],
    acts: [{ n: 3, act: "hide", target: ":A", role: "node" }] } });
  await later(10);
  assert.match(body.innerHTML, /hidden · :A/, "an act names its term");
  panel.close();
  const refs = stage.openStepPanel({ ...env, read: () => Promise.resolve({ picture: { phase: "open", groups: [],
    references: [{ failed: "invalid" }, null] } }) });
  t.after(() => refs.close());
  await later(10);
  assert.match(refs.el.querySelector("#actbody").innerHTML, /Reference 1 does not run here: syntax error/);
  refs.close();
});

test("the phone's screen: a text put back once after a reload, the kinds as they come, nothing after it is gone", async (t) => {
  const sent = [];
  const client = { send: (msg) => { sent.push(msg); return Promise.reject(Object.assign(new Error("closed"), { code: "closed" })); },
    now: () => 0 };
  let kinds = null;
  const root = element();
  const step = { activity: "q", step: "main", kind: "turtle-graph", input: "code", phase: "open", limit: 5, tokens: [] };
  const mine = { activity: "q", used: 1, blocked: false,
    entries: [{ id: "e1", input: { text: ":a :b :c ." }, state: "in", check: "checked", status: "ok" }] };
  const screen = new phone.StepScreen({ root, client, state: {}, step, language: "en", kinds: () => kinds });
  t.after(() => screen.destroy());
  screen.update({ activity: { mine } }, step);
  const text = root.querySelector("textarea"), list = root.querySelector("[data-role=mine]");
  assert.equal(text.value, ":a :b :c .", "a reload: the text as sent");
  text.value = "";                                                                       // the student clears it
  screen.update({ activity: { mine } }, step);                                           // a push (+30 s)
  assert.equal(text.value, "", "... and it stays cleared");
  assert.match(list.innerHTML, /It runs ✓/);
  kinds = new Kinds({}, "en");
  kinds.texts["turtle-graph"] = { "turtle-graph:ok": "Valid Turtle ✓" };
  assert.equal(screen.kindsReady(), false);                                              // (no input of its own)
  assert.match(list.innerHTML, /Valid Turtle ✓/, "the kind's own word, once its texts are there");
  kinds.modules["turtle-graph"] = { input: () => {} };
  assert.equal(screen.kindsReady(), true, "its kind's own input came: the screen is made anew");
  const sending = screen.send({ text: "x" });
  screen.destroy();
  list.innerHTML = "the next screen's list";
  root.querySelector("[data-role=error]").textContent = "";
  await sending;
  assert.equal(list.innerHTML, "the next screen's list", "a screen that is gone writes nothing");
  assert.equal(root.querySelector("[data-role=error]").textContent, "");
  assert.equal(phone.said({ check: "checked", status: "ok", state: "in" }, step, texts("en").steps, (m) => m.code,
    (s) => (s === "ok" ? "Valid Turtle ✓" : null)).words, "Valid Turtle ✓");
});

test("the kinds' files: texts in the deck's language, the windows' box, the rest of a phone's into the cache", async () => {
  const entry = { hash: "abc123", phone: ["web/hint.js", "web/cut.js", "texts/de.js", "texts/en.js"], window: ["web/box.js"] };
  assert.equal(textsPath(entry.phone, "de-AT"), "texts/de.js");
  assert.equal(textsPath(["texts/en.js"], "de"), "texts/en.js");                        // English where there is no German
  assert.equal(textsPath([], "en"), null);
  const imported = [], fetched = [];
  const load = async (u) => { imported.push(u); return u.endsWith("de.js") ? { default: { at: () => "bei" } } : { group: () => "g" }; };
  const get = async (u) => { fetched.push(u); };
  const onPhone = new Kinds({ one: entry, two: entry }, "de", "phone", { load, get });
  await onPhone.ready;
  await Promise.all(onPhone.fetching);
  assert.equal(onPhone.say("one", { code: "at", args: {} }), "bei");
  assert.deepEqual([...new Set(imported)], ["/kinds/abc123/texts/de.js"]);
  assert.deepEqual(fetched.sort(), ["/kinds/abc123/web/cut.js", "/kinds/abc123/web/hint.js"], "once, though two kinds share them");
  imported.length = 0;
  const inWindow = new Kinds({ one: entry }, "en", "window", { load, get });
  await inWindow.ready;
  assert.deepEqual(imported, ["/kinds/abc123/texts/en.js", "/kinds/abc123/web/box.js"]);
  assert.equal(typeof inWindow.module("one", "box").group, "function");
  assert.equal(inWindow.status("one", "ok"), null);
});

test("a hint for a text that is no longer there is dropped; the worker gets data alone", async () => {
  const posted = [];
  const worker = { postMessage(m) { structuredClone(m); posted.push(m); }, terminate() {} };
  const shown = [];
  const hints = new Hints("/kinds/abc/web/hint.js", (h) => shown.push(h), () => worker);
  hints.ask({ kind: "x" }, "SELEC", { language: "en" });
  await later(HINT_MS + 50);
  hints.ask({ kind: "x" }, "SELECT", { language: "en" });                                // a key, before the reply comes
  worker.onmessage({ data: { n: posted[0].n, hint: { code: "old" } } });                 // the reply to the first text
  await later(HINT_MS + 50);
  worker.onmessage({ data: { n: posted[1].n, hint: { code: "new" } } });
  assert.deepEqual(shown, [{ code: "new" }]);
  hints.destroy();
});

test("the host console's line: the time counts down between pushes, a change asked for sooner is asked later", async () => {
  const timers = [];
  const time = { t: 0, now() { return this.t; },
    after(f, ms) { const x = { f, at: this.t + ms }; timers.push(x); return x; },
    every(f, ms) { const x = { f, at: this.t + ms, every: ms }; timers.push(x); return x; },
    cancel(x) { const i = timers.indexOf(x); if (i >= 0) timers.splice(i, 1); } };
  const run = async (to) => {
    for (;;) {
      const next = timers.filter((x) => x.at <= to).sort((a, b) => a.at - b.at)[0];
      if (!next) break;
      time.t = next.at;
      if (next.every) next.at += next.every; else timers.splice(timers.indexOf(next), 1);
      next.f();
      await later(0);
    }
    time.t = to;
  };
  const reads = [];
  let drawn = 0;
  const line = new ActsLine({ read: (msg) => { reads.push(msg); return Promise.resolve({ picture: { students: 1, entries: 2, waiting: 0 } }); },
    now: () => time.t, render: () => { drawn += 1; }, time });
  const acts = (version, phase = "open") => ({ current: "q", items: { q: { phase, version, time: 120_000, since: 0 } } });
  const H = texts("en").host;
  line.update(acts(1));
  await later(0);
  assert.equal(reads.length, 1);
  assert.match(line.said("q", H), /^2:00 · /);
  line.update(acts(2));                                                                  // a new version, at once
  assert.equal(reads.length, 1);
  await run(6_000);
  assert.equal(reads.length, 2, "asked for when the two seconds are up");
  assert.match(line.said("q", H), /^1:54/, "the time ran");
  assert.ok(drawn >= 6, "drawn every second while the time runs");
  line.update(acts(2, "paused"));
  const before = drawn;
  await run(10_000);
  assert.equal(drawn, before, "a time that waits is not drawn again");
  line.destroy();
});


// ------------------------------------------------------------------ texstage's own kinds (package 9)
test("a number as a student types it, read as the deck's language writes numbers", () => {
  for (const [typed, n] of [["42", 42], ["-3.5", -3.5], ["3,5", 3.5], ["3.5", 3.5], [" 1 000 ", 1000], [".5", 0.5],
    ["+7", 7], ["1'000", 1000], ["1,000,000", 1e6], ["1,234.5", 1234.5], ["1.234,5", 1234.5], ["1234,567", 1234.567],
    [String.fromCharCode(0x2212) + "5", -5], ["3.", 3]]) {
    assert.equal(phone.parseNumber(typed, "en"), n, typed);
  }
  // one separator before three digits alone: a thousand where the deck's language groups with it, else a decimal
  assert.deepEqual(["1,000", "1.000", "2,500"].map((t) => phone.parseNumber(t, "en")), [1000, 1, 2500]);
  assert.deepEqual(["1,000", "1.000", "2,500"].map((t) => phone.parseNumber(t, "de")), [1, 1000, 2.5]);
  assert.deepEqual(["0.125", "-0.500", "0,125", "00.250"].map((t) => phone.parseNumber(t, "de")), [0.125, -0.5, 0.125, 0.25],
    "after a whole part of 0 a separator is a decimal one, in any language");
  assert.deepEqual(["3.141", "1 000,5", "12 345 678", "1 2", "1 0000"].map((t) => phone.parseNumber(t, "en")),
    [3.141, 1000.5, 12345678, null, null], "a space or an apostrophe between groups of three, else no number");
  for (const typed of ["", "abc", "1e3", "3,5,1", "--2", "0x10", "1.2.3", "12,34,5", "1,5.3", "1,000.000,5", "-", null]) {
    assert.equal(phone.parseNumber(typed, "en"), null, typed);
  }
  assert.equal(phone.numberShown(3.5, "de"), "3,5");
  assert.equal(phone.numberShown(1000.25, "en"), "1000.25");
  assert.equal(phone.numberShown(2 ** 40, "de"), "1099511627776", "every digit, no grouping");
  assert.equal(phone.numberShown(1e-13, "en"), "0.0000000000001");
  for (const n of [1000.5, 1.234, 0.001, 1e15, -7.25]) {
    for (const language of ["en", "de"]) {             // (a reload puts the number back as the language writes it)
      assert.equal(phone.parseNumber(phone.numberShown(n, language), language), n, `${n} in ${language}`);
    }
  }
});

test("an entry as the student's list shows it: a choice by its options, a number, a text", () => {
  const step = { options: ["Paris", "<b>Nice</b>", "$\\sigma$"] };
  assert.equal(phone.entryShown({ choice: [0, 1] }, step, "en"), "Paris + &#60;b&#62;Nice&#60;/b&#62;");
  assert.equal(phone.entryShown({ choice: [2] }, step, "en"), "$\\sigma$", "(typeset once KaTeX is there)");
  assert.equal(phone.entryShown({ number: 12.5 }, step, "de"), "12,5");
  assert.equal(phone.entryShown({ number: 0 }, step, "en"), "0");
  assert.equal(phone.entryShown({ text: "<i>" }, step, "en"), "<pre>&#60;i&#62;</pre>");
  assert.equal(phone.entryShown({ fields: ["a", "b"] }, step, "en"), "a · b");
  const L = texts("en").steps;
  assert.equal(phone.said({ check: "checked", status: "ok", state: "in" }, { input: "choice" }, L, (m) => m.code,
    (s) => (s === "ok" ? "Chosen ✓" : null)).words, "Chosen ✓");
  assert.ok(L.refused["too-large"] && texts("de").steps.refused["too-large"] && L.sign);
  for (const input of ["choice", "number", "text"]) {                  // till the kind's word is there: none that runs
    assert.equal(phone.said({ check: "checked", status: "ok", state: "in" }, { input }, L, (m) => m.code).words, L.fieldsOk);
  }
});

function choiceScreen(select, client) {
  // a phone's screen of a choice, and the state that tells it the choice that counts
  const step = { activity: "capital", step: "main", kind: "choice", input: "choice", options: ["Paris", "Lyon", "Nice"],
    select, phase: "open", limit: 10 };
  const root = element();
  const screen = new phone.StepScreen({ root, client, state: {}, step, language: "en", kinds: () => null });
  const mine = (choice) => ({ activity: { mine: { activity: "capital", used: choice ? 1 : 0,
    entries: choice ? [{ id: "e1", input: { choice }, state: "in", check: "checked", status: "ok" }] : [] } } });
  screen.update(mine(null), step);
  return { screen, root, step, mine };
}

test("a choice of one on the phone: a tap sends it, the choice that counts is not sent again, the latest tap wins", async (t) => {
  const sent = [];
  let refuse = null, hold = null;
  const client = { now: () => 0, send(msg) {
    sent.push(msg.choice);
    if (refuse) {
      const code = refuse;
      refuse = null;
      return Promise.reject(Object.assign(new Error(code), { code }));
    }
    return hold ? new Promise((ok) => { hold = ok; }) : Promise.resolve({});
  } };
  const { screen, root, step, mine } = choiceScreen("one", client);
  t.after(() => screen.destroy());                                        // (a failure: its timer goes too)
  screen.choose(0);
  await later(5);
  assert.deepEqual(sent, [[0]]);
  screen.update(mine([0]), step);
  screen.choose(0);                                                       // a tap of the choice that counts
  await later(5);
  assert.deepEqual(sent, [[0]], "nothing is sent for it");
  refuse = "too-fast";                                                    // a change of mind within the step's gap
  screen.choose(2);
  await later(1100);
  assert.deepEqual(sent, [[0], [2], [2]], "sent again once the gap is over");
  assert.equal(root.querySelector("[data-role=error]").textContent, "", "... and no error for it");
  screen.update(mine([2]), step);
  const lyon = root.querySelector("button[data-choice]");
  lyon.dataset.choice = "1";                                              // (the stand-in's one button: Lyon's)
  hold = true;                                                            // two taps, the first on its way
  screen.choose(0);
  screen.choose(1);
  await later(5);
  assert.deepEqual(sent.slice(3), [[0]]);
  screen.update(mine([2]), step);                                         // a push meanwhile: the tap stays marked
  assert.equal(lyon.attrs["aria-pressed"], "true", "the latest tap is marked, not the choice that counted");
  hold({});
  await later(5);
  assert.deepEqual(sent.slice(3), [[0], [1]], "the latest tap: sent once the first is answered");
  hold({});
  screen.destroy();
});

test("a choice of several on the phone: marked until Send, nothing marked is refused, the same choice is not sent again", async (t) => {
  const sent = [];
  const client = { now: () => 0, send(msg) { sent.push(msg.choice); return Promise.resolve({}); } };
  const { screen, root, step, mine } = choiceScreen("many", client);
  t.after(() => screen.destroy());
  await screen.submit();
  assert.equal(root.querySelector("[data-role=error]").textContent, texts("en").steps.refused.choice);
  const nice = root.querySelector("button[data-choice]");
  nice.dataset.choice = "2";                                              // (the stand-in's one button: Nice's)
  screen.choose(2);
  assert.ok(nice.classes.has("selected") && nice.attrs["aria-pressed"] === "true");
  screen.choose(2);
  assert.ok(!nice.classes.has("selected") && nice.attrs["aria-pressed"] === "false", "tapped again: not chosen");
  screen.choose(2);
  screen.choose(0);
  await screen.submit();
  assert.deepEqual(sent, [[0, 2]]);
  screen.update(mine([0, 2]), step);
  await screen.submit();
  assert.deepEqual(sent, [[0, 2]], "the choice that counts: nothing sent");
  screen.choose(1);
  await screen.submit();
  assert.deepEqual(sent, [[0, 2], [0, 1, 2]]);
  screen.destroy();
});

test("a number on the phone: read in the deck's language, refused there when it is none, ± for its sign", async (t) => {
  const sent = [];
  const client = { now: () => 0, send(msg) { sent.push(msg.number); return Promise.resolve({}); } };
  const step = { activity: "rows", step: "main", kind: "number", input: "number", phase: "open", limit: 5 };
  const root = element();
  const screen = new phone.StepScreen({ root, client, state: {}, step, language: "de", kinds: () => null, phone: "de-DE" });
  t.after(() => screen.destroy());
  screen.update({ activity: { mine: { activity: "rows", used: 1, entries: [{ id: "e1", input: { number: 1.5 }, state: "in" }] } } }, step);
  assert.equal(screen.text.value, "1,5", "a reload: the number as sent, as the deck's language writes it");
  screen.text.value = "1.000";
  await screen.submit();
  assert.deepEqual(sent, [1000]);
  screen.text.value = "zwölf";
  await screen.submit();
  assert.equal(root.querySelector("[data-role=error]").textContent, texts("de").steps.refused.number);
  assert.deepEqual(sent, [1000], "nothing sent");
  screen.text.value = "5";
  const sign = root.querySelector("[data-role=sign]").listeners.click[0];     // (the key as a tap reaches it)
  sign();
  assert.equal(screen.text.value, "-5");
  sign();
  assert.equal(screen.text.value, "5");
  // a German deck on a phone set to English: its keypad offers the point - 3.141 is pi, not 3141
  const english = new phone.StepScreen({ root: element(), client, state: {}, step, language: "de", kinds: () => null, phone: "en-US" });
  t.after(() => english.destroy());
  english.update({ activity: { mine: { activity: "rows", used: 1, entries: [{ id: "e1", input: { number: 1.5 }, state: "in" }] } } }, step);
  assert.equal(english.text.value, "1.5", "put back as the phone writes it");
  english.text.value = "3.141";
  await english.submit();
  assert.deepEqual(sent, [1000, 3.141]);
  screen.destroy();
});

test("what the windows call a group of a choice or a number - in the deck's language", () => {
  const w = texts("en").box;
  const item = { options: ["Paris", "Nice"] };
  const NL = String.fromCharCode(10);
  assert.equal(stage.groupLabel({ status: "ok", label: "Nice" + NL + "Paris", example: { choice: [0, 1] } }, w, item), "Nice + Paris");
  assert.equal(stage.groupLabel({ status: "ok", example: { choice: [1] } }, w, item), "Nice");
  assert.equal(stage.groupLabel({ status: "ok", example: { number: 12.5 } }, w, null, "de"), "12,5");
  assert.equal(stage.shownText({ choice: [1, 0] }, item), "Nice + Paris");
  assert.equal(stage.shownText({ number: 0 }), "0");
  assert.equal(stage.tallyText("a" + NL + "b"), "a + b");
});

test("a number step's histogram: a bar per number up to twelve, else stretches - and the numbers far out apart", () => {
  const bar = (from, n, right = false) => ({ from, to: from, n, right });
  assert.deepEqual(stage.histogram([[1, 2], [2, 1, "correct"], [5, 3, "incorrect"]]), [bar(1, 2), bar(2, 1, true), bar(5, 3)]);
  assert.ok(stage.histogram(Array.from({ length: 12 }, (_, i) => [i, 1])).every((b) => b.from === b.to), "twelve: a bar each");
  const bars = stage.histogram(Array.from({ length: 30 }, (_, i) => [i, 1]));
  assert.equal(bars.length, stage.BINS);
  assert.equal(bars.reduce((s, b) => s + b.n, 0), 30, "every student in a bar");
  assert.deepEqual([bars[0].from, bars.at(-1).to], [0, 29]);
  assert.deepEqual(stage.histogramLabels(bars, "en").slice(0, 2), ["0 – 2.4", "2.4 – 4.8"]);
  // one joke does not squeeze the class into one bar: it has a bar of its own at the end
  const joke = stage.histogram([...Array.from({ length: 30 }, (_, i) => [40 + i * 0.4, 2]), [1e15, 1, "incorrect"]]);
  assert.deepEqual([joke.at(-1).out, joke.at(-1).n], ["above", 1]);
  assert.ok(joke.slice(0, -1).filter((b) => b.n).length > 5, "the class's numbers spread over the bars");
  assert.equal(stage.histogramLabels(joke, "en").at(-1), "1000000000000000");
  assert.deepEqual(stage.histogramLabels(stage.histogram([[12345, 3], [12346, 1]]), "en"), ["12345", "12346"], "every digit");
  assert.deepEqual(stage.histogramLabels(stage.histogram([[3.5, 1]]), "de"), ["3,5"]);
  assert.deepEqual(stage.histogram([]), []);
});

test("the box draws a number step: the bars as the server judged them, the reference, a group the lecturer shows", async () => {
  const numbers = [[11, 1], [12.4, 2], [20, 1]];
  const host = { role: "projector", read: () => Promise.resolve({ picture: { phase: "open", groups: [], numbers, students: 4,
    entries: 4 }, lead: null }) };
  const box = new stage.StepBox({ id: "rows", item: { kind: "number", tolerance: 0.5 }, layer: element(), host, language: "en" });
  box.update({ stage: { activity: { items: { rows: { version: 1, layout: 0 } } } } });
  await later(10);
  assert.equal((box.el.innerHTML.match(/class="tq-hbar[ "]/g) || []).length, 3);
  assert.doesNotMatch(box.el.innerHTML, /tq-ref|tq-solline/, "nothing of the reference before the reveal");
  box.picture = { phase: "revealed", revealed: true, groups: [], students: 4, entries: 4, right: 2, solution: [{ text: "12" }],
    numbers: [[11, 1, "incorrect"], [12.4, 2, "correct"], [20, 1, "incorrect"]] };
  box.draw();
  assert.equal((box.el.innerHTML.match(/tq-hbar tq-ref/g) || []).length, 1, "12.4: judged right, within 0.5 of 12");
  assert.match(box.el.innerHTML, /The reference: 12 ± 0.5/);
  assert.match(box.el.innerHTML, /2 right/);
  box.picture = { ...box.picture, solution: undefined };                  // solution=mark: the bars alone
  box.draw();
  assert.equal((box.el.innerHTML.match(/tq-hbar tq-ref/g) || []).length, 1);
  assert.doesNotMatch(box.el.innerHTML, /tq-solline/);
  box.picture = { ...box.picture, shown: { id: "g", example: { number: 20 }, n: 1 } };      // a group the lecturer shows
  box.draw();
  assert.equal((box.el.innerHTML.match(/tq-showing/g) || []).length, 1);
  assert.match(box.el.innerHTML, /20 · 1 student/);
  box.picture = { phase: "open", students: 1, numbers: [], groups: [{ id: "x", status: "ok", n: 1, example: { number: 7 } }] };
  box.draw();                                                             // (keys that are no numbers: the groups)
  assert.match(box.el.innerHTML, /tq-clusters/);
});

test("the box draws a choice: a bar per option - a choice of several counted per option -, the references in a line", () => {
  const NL = String.fromCharCode(10);
  const host = { role: "projector", read: () => new Promise(() => {}) };
  const box = new stage.StepBox({ id: "coast", item: { kind: "choice", options: ["Paris", "Nice", "Marseille"] }, layer: element(),
    host, language: "en" });
  box.picture = { kind: "tally", phase: "revealed", revealed: true, students: 2, right: 1,
    groups: [{ id: "a", status: "ok", label: "Nice", n: 1 }, { id: "b", status: "ok", label: "Nice" + NL + "Marseille", n: 1, reference: true }],
    options: [{ label: "Paris", n: 0, reference: false }, { label: "Nice", n: 2, reference: true }, { label: "Marseille", n: 1, reference: true }],
    solution: [{ text: "Nice" + NL + "Marseille" }] };
  box.draw();
  const html = box.el.innerHTML;
  assert.deepEqual([...html.matchAll(/<span class="tq-cn">(\d+)</g)].map((m) => m[1]), ["0", "2", "1"], "per option");
  assert.equal((html.match(/tq-cluster tq-ref/g) || []).length, 2);
  assert.match(html, /The reference: Nice \+ Marseille/);
  assert.doesNotMatch(html, /tq-shown/, "no box over the bars");
  assert.match(html, /1 right/);
  box.picture = { kind: "tally", phase: "open", students: 0,                             // a deck's 26 options fit
    groups: Array.from({ length: 26 }, (_, i) => ({ id: `g${i}`, status: "ok", label: String.fromCharCode(65 + i), n: 0 })) };
  box.draw();
  assert.match(box.el.innerHTML, /tq-clusters tq-dense/);
  box.item = { kind: "sql-query" };                                       // a code kind's references with their results
  box.picture = { kind: "groups", phase: "revealed", revealed: true, students: 0, groups: [],
    solution: [{ text: "SELECT 1", detail: { columns: ["n"], rows: [[1]], count: 1 } },
      { text: "SELECT 2", detail: { columns: ["n"], rows: [[2]], count: 1 } }] };
  box.draw();
  assert.equal((box.el.innerHTML.match(/class="tq-shown"/g) || []).length, 1, "one box, not one over the other");
  assert.equal((box.el.innerHTML.match(/tq-shownhead/g) || []).length, 2);
  box.item = { kind: "text" };                                            // a short answer's reference: in the line
  box.picture = { kind: "groups", phase: "revealed", revealed: true, students: 0, groups: [], solution: [{ text: "Berlin" }] };
  box.draw();
  assert.match(box.el.innerHTML, /tq-solline">The reference: Berlin/);
  box.item = { kind: "sql-query" };                                       // a query without a result: its text in a box
  box.picture = { ...box.picture, solution: [{ text: "SELECT name" + String.fromCharCode(10) + "FROM people" }] };
  box.draw();
  assert.match(box.el.innerHTML, /class="tq-shown"/);
  assert.match(box.el.innerHTML, /<pre>SELECT name/);
});

test("the panel: how many are right where the groups are judged; a reference without a group of its own", async (t) => {
  const picture = { phase: "open", students: 3, entries: 3, right: 3, references: [{ group: "none" }, { group: "g0" }],
    groups: [{ id: "g1", status: "ok", n: 2, verdict: "correct", example: { number: 12.4 } },
      { id: "g2", status: "ok", n: 1, verdict: "correct", example: { number: 11.9 } },
      { id: "g0", status: "ok", n: 0, example: null }] };                // (a tally's right option that nobody chose)
  const panel = stage.openStepPanel({ dock() {}, undock() {}, ask: async () => true, language: "de", kinds: null, now: () => 0,
    onSlide: () => null, items: () => ({ rows: { kind: "number" } }), send: () => Promise.resolve({}),
    state: () => ({ stage: { activity: { current: "rows", items: { rows: { phase: "open", version: 1, epoch: 0 } } } } }),
    read: () => Promise.resolve({ picture }) });
  t.after(() => panel.close());
  await later(10);
  const html = panel.el.querySelector("#actbody").innerHTML;
  assert.match(html, /Referenz 1/);
  assert.doesNotMatch(html, /Gruppe von 0/, "an empty group is no group of the reference's");
  assert.match(html, /3 Personen liegen richtig/);
  assert.match(html, /12,4/, "a number as the deck's language writes it");
  panel.close();
});

test("an answer a kind's normalize refused: the kind's word for it, the reason in the core's words", (t) => {
  const kinds = new Kinds({}, "en");
  kinds.texts.text = { "text:invalid": "Not taken" };
  const step = { activity: "word", step: "main", kind: "text", input: "text", phase: "open", limit: 5 };
  const root = element();
  const screen = new phone.StepScreen({ root, client: { now: () => 0, send: () => Promise.resolve({}) }, state: {}, step,
    language: "en", kinds: () => kinds });
  t.after(() => screen.destroy());
  screen.update({ activity: { mine: { activity: "word", used: 1, entries: [{ id: "e1", input: { text: String.fromCharCode(0x200B) },
    state: "in", check: "checked", status: "invalid", message: { code: "text", args: {} } }] } } }, step);
  assert.match(root.querySelector("[data-role=mine]").innerHTML, /Not taken: Please type your text first\./);
});
