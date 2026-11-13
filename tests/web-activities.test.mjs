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
  return {
    innerHTML: "", textContent: "", value: "", hidden: false, disabled: false, inert: false, dataset: {}, style: {},
    options: [], listeners: {}, selectionStart: 0, selectionEnd: 0,
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    querySelector(sel) { if (!kids.has(sel)) kids.set(sel, element()); return kids.get(sel); },
    querySelectorAll(sel) { return [this.querySelector(sel)]; },
    append() {}, remove() {}, focus() {}, closest() { return null; },
  };
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

test("the panel: another activity picked while a picture comes is asked for, and nothing of the first is left", async () => {
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
  await later(10);
  assert.match(refs.el.querySelector("#actbody").innerHTML, /Reference 1 does not run here: syntax error/);
  refs.close();
});

test("the phone's screen: a text put back once after a reload, the kinds as they come, nothing after it is gone", async () => {
  const sent = [];
  const client = { send: (msg) => { sent.push(msg); return Promise.reject(Object.assign(new Error("closed"), { code: "closed" })); },
    now: () => 0 };
  let kinds = null;
  const root = element();
  const step = { activity: "q", step: "main", kind: "turtle-graph", input: "code", phase: "open", limit: 5, tokens: [] };
  const mine = { activity: "q", used: 1, blocked: false,
    entries: [{ id: "e1", input: { text: ":a :b :c ." }, state: "in", check: "checked", status: "ok" }] };
  const screen = new phone.StepScreen({ root, client, state: {}, step, language: "en", kinds: () => kinds });
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

