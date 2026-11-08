// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The PowerPoint add-in "texstage" (docs/design.md, section 5): one instance per live
// slide, created by PowerPoint from the object the builder put over the slide. It reads its
// properties ({server, deck, bundle, quiz, phase, slideId, key}), draws its slide with the shared
// live views, and drives the game by the slides the lecturer shows - clicker only. It talks
// to the server it was loaded from: every server has its own add-in, and the PPTX names
// the add-in (texstage build --server, texstage retarget).
//
// PowerPoint preloads the next slide's add-in and keeps every instance alive (spike S1), so
// creation means nothing: every instance asks every 250 ms which slide the slideshow shows
// (getSelectedDataAsync(SlideRange)) and acts when it is its own. Only then it connects to the
// server (and stays connected a little while after); the instance whose slide was shown last
// also reports ordinary slides, so the host console and the server always know the slide.
// In PowerPoint's editing view it shows a small status bar instead. The presenter key comes
// with the deck (property key, texstage build); only if the server rejects it, the add-in tries
// a stored one or the laptop's own, and as a last resort asks for it in the status bar.
//
// The deck reaches the server through its build (texstage build: the server on the laptop that
// built it finds it by itself, any other gets it uploaded); the PowerPoint file carries none.
// Files built before 2026-10-09 carry it on the join slide (property texquizBundle): a server
// that does not know the deck still gets it from there (PUT /api/bundles/<id>) - as far as
// PowerPoint lets the add-in read it (at most 2 MB).
//
// Preparing the live slides (2026-10-04): the first time PowerPoint shows a live slide after
// the file was opened, it starts that slide's add-in - one to four seconds of white, black and
// a small grey box on the screen, also when presenting forward. Once started, an add-in stays
// until the file is closed, and the slide shows cleanly. So the add-in shows every later live
// slide not yet shown once (Office.js moves the slideshow), each until its add-in has drawn
// itself, and comes back. Meanwhile the server starts nothing (prepare) and every live slide
// shows "Preparing the quiz slides" instead of its content - no answers on the projector. A
// key pressed meanwhile (the slideshow is not where the preparation put it) ends it.
// Since 2026-10-10 the file's first slide does it (phase "prepare", not one of the deck's
// slides): the slideshow starts there before the lecture, and it says when all is ready - the
// game's PIN, the players. A join slide still prepares what is left: a slideshow started
// later, or a file built before.
//
// It speaks the deck's language once its deck.json is there (i18n.js: "addin"; the slide's views
// are live.js's), before that PowerPoint's (Office.context.displayLanguage) or the browser's; what
// it reports to the server's log stays English.

import { errorText, pageLanguage, pageTexts, supported, texts, usePageLanguage } from "/static/i18n/i18n.js";
import { Client, hostFetch } from "/static/shared/client.js";
import { Stage } from "/static/shared/live.js";

const KEY = "texquiz:presenter-key";       // shared by all instances (same origin)
const REPORTER = "texquiz:reporter";       // the instance that reports ordinary slides
const PREPARING = "texquiz:preparing";     // {bundle, done, total, until} while the live slides are prepared
const POLL_MS = 250;
const LINGER_MS = 15000;
const SHOWN_WAIT_MS = 10000;               // preparing: a slide's add-in has drawn itself within this
const me = Math.random().toString(36).slice(2);
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const words = () => pageTexts().addin;      // in the page's language: the deck's, before it PowerPoint's
const textOf = (table, key) => (Object.prototype.hasOwnProperty.call(table, key) ? table[key] : key);   // a phase's name, else itself

function failure(key, ...args) {
  // a failure the status bar shows in the page's language, and the server's log in English
  const say = (A) => (typeof A[key] === "function" ? A[key](...args) : A[key]);
  return Object.assign(new Error(say(texts("en").addin)), { shown: say(words()) });
}

// why the preparing stopped: at a slide PowerPoint did not go to, or the lecturer moved on
const stopReason = (A, stopped) => (stopped.moved ? A.movedOn : A.stoppedAt(stopped.slide, stopped.error));

let props = {};
let key = null;
let deck = null;
let slide = null;
let stage = null;
let client = null;
let state = null;
let view = null;               // PowerPoint's view once known: read = slideshow (and reading view), edit
let active = false;
let inactiveSince = 0;
let lastReported = null;
let status = "";
let slow = null;               // the status bar says "connecting" only when it takes a while
let fineUntil = 0;             // ... and "all fine" only for a few seconds after the editing view appears
let fineTimer = null;
const rejected = new Set();    // presenter keys the server did not accept
let channel = null;            // BroadcastChannel of the deck's instances: which slides have been shown
let shown = false;             // this slide has been on the screen since the file was opened
let preparedHere = false;      // this join slide (or the first slide) has prepared the live slides after it
let preparing = false;         // ... and is doing so now
let prepared = null;           // the first slide: {done, total, stopped} once its preparing has ended
const first = () => props.phase === "prepare";       // the file's first slide

// Inside PowerPoint nobody sees the console: errors go to the server's log.
function report(what, data) {
  if (!key) return;
  const body = JSON.stringify({ addin: props.slideId, phase: props.phase, what, data });
  fetch("/api/client-log", { method: "POST", headers: { "X-Texquiz-Key": key }, body }).catch(() => {});
}
addEventListener("error", (e) => report("error", `${e.message} ${e.filename}:${e.lineno}`));
addEventListener("unhandledrejection", (e) => report("rejection", String(e.reason)));

Office.onReady(() => start().catch((err) => {
  report("start", String(err.message || err));
  setup(`<span class="bad">${esc(err.shown || err.message || err)}</span>`);
}));

async function start() {
  usePageLanguage(supported(Office.context?.displayLanguage));     // (none it speaks: the browser's)
  const settings = Office.context.document.settings;
  for (const k of ["server", "deck", "bundle", "quiz", "phase", "slideId", "key"]) props[k] = settings.get(k);
  if (!props.bundle || !props.slideId) throw failure("noProps");
  // the deck's instances tell each other which slides have been shown (preparing, below)
  channel = new BroadcastChannel(`texquiz:${props.bundle}`);
  channel.addEventListener("message", (e) => {
    if (e.data?.t === "who" && shown) channel.postMessage({ t: "shown", slide: props.slideId });
  });
  addEventListener("storage", (e) => { if (e.key === PREPARING) cover(); });
  cover();
  stage = new Stage($("#stage"), { send: (cmd) => client?.send(cmd).catch(() => {}), controls: true });
  if (first()) render();                           // (what it is for, while the deck loads)
  key = props.key || await presenterKey();         // the deck carries its server's key
  await loadDeck();
  const doc = Office.context.document;
  doc.getActiveViewAsync((r) => { if (r.status === "succeeded") setView(r.value); });
  doc.addHandlerAsync(Office.EventType.ActiveViewChanged, (e) => setView(e.activeView));
  setInterval(poll, POLL_MS);
}

async function presenterKey() {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored) return stored;
  } catch { /* storage blocked */ }
  try {
    const k = (await (await fetch("/api/presenter-key")).json()).key;   // the server on this PC
    if (k) {
      try { localStorage.setItem(KEY, k); } catch { /* ignore */ }
      return k;
    }
  } catch { /* not on this machine */ }
  return null;
}

async function loadDeck() {
  if (!key) {
    status = words().unpaired;
    return setup(pairForm());
  }
  try {
    deck = await (await hostFetch(`/api/deck/${props.bundle}`, key)).json();
    usePageLanguage(deck.language || "");        // (a deck built before 2026-10-24 names none: English)
  } catch (err) {
    const code = String(err.message).slice(0, 3);
    if (code === "403") {                          // try the next key: the file's, stored, the laptop's
      rejected.add(key);
      try { if (localStorage.getItem(KEY) === key) localStorage.removeItem(KEY); } catch { /* ignore */ }
      const next = [props.key, await presenterKey()].find((k) => k && !rejected.has(k));
      if (next) {
        key = next;
        return loadDeck();
      }
      status = props.key ? words().keyOld : words().keyRejected;
      key = null;
      return setup(pairForm());
    }
    if (code === "404" && await uploadBundle()) return loadDeck();
    status = carriesBundle() ? words().refused : words().missing;
    setTimeout(loadDeck, 3000);
    return setup("");
  }
  slide = first() ? null : deck.slides.find((s) => s.id === props.slideId);
  if (!slide && !first()) throw failure("notInDeck", props.slideId, props.deck, props.bundle);
  status = "";
  render();
  setup("");
}

const carriesBundle = () => Boolean(Office.context.document.settings.get("texquizBundle"));
let uploaded = false;

// The bundle this object carries, to the server - once per page (a failure is in the log).
async function uploadBundle() {
  if (uploaded || !carriesBundle()) return false;
  uploaded = true;
  const packed = Office.context.document.settings.get("texquizBundle");
  const body = Uint8Array.from(atob(packed), (c) => c.charCodeAt(0));
  try {
    const r = await fetch(`/api/bundles/${props.bundle}`, {
      method: "PUT", headers: { "X-Texquiz-Key": key, "Content-Type": "application/zip" }, body });
    if (r.ok) return true;
    report("upload", `${r.status} ${await r.text()}`);
  } catch (err) {
    report("upload", String(err.message || err));
  }
  return false;
}

function setView(v) {
  view = v;
  if (view !== "read") {                 // editing: no game, a status bar
    active = false;
    disconnect();
  }
  if (view === "edit") fineUntil = Date.now() + 5000;
  setup("");
  if (first()) render();
}

function poll() {
  cover();                                 // the storage event may not reach every instance
  if (!deck || view !== "read") return;
  Office.context.document.getSelectedDataAsync(Office.CoercionType.SlideRange, (r) => {
    if (r.status !== "succeeded") return;
    const current = r.value?.slides?.[0]?.id;
    if (current === undefined) return;
    const mine = current === props.slideId;
    if (mine && !active) {
      active = true;
      try { localStorage.setItem(REPORTER, me); } catch { /* ignore */ }
      connect();
      if (!shown) {                        // on the screen, drawn: PowerPoint has started this add-in
        shown = true;
        requestAnimationFrame(() => channel.postMessage({ t: "shown", slide: props.slideId }));
      }
      if ((props.phase === "join" || first()) && !preparedHere) {
        preparedHere = true;               // a second join slide shown by a running preparation: nothing to do
        if (!cover()) prepare().catch((err) => report("prepare", String(err.message || err)));
      }
    } else if (!mine && active) {
      active = false;
      inactiveSince = Date.now();
    }
    // (the first slide is not the deck's: the server hears of the deck's slides only)
    if (client && current !== lastReported && (mine || reporter()) && deck.slides.some((s) => s.id === current)) {
      lastReported = current;
      client.send({ t: "slide", slide: current }).catch(() => {});
    }
    if (!active && client && !reporter() && !preparing && Date.now() - inactiveSince > LINGER_MS) disconnect();
  });
}

// ------------------------------------------------------------------ preparing the live slides
const sleep = (ms) => new Promise((res) => setTimeout(res, ms));
const goTo = (id) => new Promise((res) => Office.context.document.goToByIdAsync(id, Office.GoToType.Slide, res));
const currentSlide = () => new Promise((res) => Office.context.document.getSelectedDataAsync(
  Office.CoercionType.SlideRange, (r) => res(r.status === "succeeded" ? r.value?.slides?.[0]?.id : undefined)));

// Every live slide after this one (the first slide: every live slide) that has not been shown
// since the file was opened, once - see the comment at the top. The waiting is done on
// messages, not on timers: this page is in the background meanwhile, where timers are slowed
// down.
async function prepare() {
  const seen = new Set([props.slideId]);
  const collect = (e) => { if (e.data?.t === "shown") seen.add(e.data.slide); };
  channel.addEventListener("message", collect);
  channel.postMessage({ t: "who" });
  await sleep(600);
  const from = deck.slides.findIndex((s) => s.id === props.slideId);     // (the first slide: -1)
  const todo = deck.slides.slice(from + 1).filter((s) => s.phase && !seen.has(s.id));
  if (!todo.length) {
    channel.removeEventListener("message", collect);
    prepared = { done: 0, total: 0, stopped: null };
    render();
    return;
  }
  preparing = true;
  let done = 0;
  const mark = () => {
    try {
      localStorage.setItem(PREPARING, JSON.stringify({ bundle: props.bundle, done, total: todo.length,
                                                       until: Date.now() + 2 * SHOWN_WAIT_MS + 60000 }));
    } catch { /* storage blocked: the slides are prepared all the same, only not covered */ }
    cover();
  };
  const shownNow = (id) => new Promise((res) => {
    if (seen.has(id)) return res(true);
    const on = (e) => {
      if (e.data?.t === "shown" && e.data.slide === id) { clearTimeout(timer); channel.removeEventListener("message", on); res(true); }
    };
    const timer = setTimeout(() => { channel.removeEventListener("message", on); res(false); }, SHOWN_WAIT_MS);
    channel.addEventListener("message", on);
  });
  mark();
  client?.send({ t: "prepare", on: true }).catch(() => {});
  let stopped = null;                    // why it stopped (stopReason)
  try {
    for (const s of todo) {
      const r = await goTo(s.id);
      if (r.status !== "succeeded") { stopped = { slide: s.id, error: r.error ? r.error.message : r.status }; break; }
      if (!await shownNow(s.id)) report("prepare", `slide ${s.id} did not report within ${SHOWN_WAIT_MS} ms`);
      done++;
      mark();
      if (await currentSlide() !== s.id) { stopped = { moved: true }; break; }
    }
  } finally {
    channel.removeEventListener("message", collect);
    try { localStorage.removeItem(PREPARING); } catch { /* ignore */ }
    preparing = false;
    cover();
    client?.send({ t: "prepare", on: false }).catch(() => {});
  }
  if (!stopped) await goTo(props.slideId);
  prepared = { done, total: todo.length, stopped };
  render();
  report("prepared", `${done} of ${todo.length} live slides${stopped ? ` - stopped: ${stopReason(texts("en").addin, stopped)}` : ""}`);
}

// While the live slides are prepared, every one of them (of this deck) is covered. Returns
// whether a preparation is running.
function cover() {
  let p = null;
  try { p = JSON.parse(localStorage.getItem(PREPARING) || "null"); } catch { /* storage blocked */ }
  const on = Boolean(p && p.bundle === props.bundle && p.until > Date.now());
  const el = $("#prepare");
  if (on) {
    const text = `${esc(words().preparing)}<small>${Number(p.done)} / ${Number(p.total)}</small>`;
    if (el.innerHTML !== text) el.innerHTML = text;
  }
  if (el.hidden === on) el.hidden = !on;
  return on;
}

function reporter() {
  try { return localStorage.getItem(REPORTER) === me; } catch { return false; }
}

function connect() {
  if (client) return;
  lastReported = null;
  let mine = null;
  client = mine = new Client({
    onState: (m) => { state = m; render(); },
    // the status bar follows the connection: a stale "connecting" stayed on the slide (M6)
    onStatus: (s) => {
      if (mine && client !== mine) return;           // a client this page has closed
      clearTimeout(slow);
      if (s === "open") {
        status = "";
        setup("");
      } else {
        slow = setTimeout(() => { status = words().connecting; setup(""); }, 2000);
      }
    },
  });
  client.login({ t: "hello", role: "host", key, deck: deck.deck, bundle: deck.bundle }).catch((err) => {
    status = errorText(pageLanguage(), err);
    setup("");
  });
}

function disconnect() {
  client?.close();
  client = null;
  state = null;
  clearTimeout(slow);
  status = "";
  render();
  setup("");
}

function render() {
  if (first()) renderFirst();
  else if (slide) stage.show(slide, deck, state, () => (client ? client.now() : Date.now()));
}

// The first slide: what it is for; in the slideshow how far the preparing is (the cover shows
// it meanwhile), then ready - with the game's PIN, the players and where they join.
function renderFirst() {
  let el = $("#first");
  if (!el) {
    el = Object.assign(document.createElement("div"), { id: "first" });
    $("#stage").after(el);                         // under the cover and the status bar
  }
  const s = state?.session;
  const players = state?.players?.length ?? 0;
  const A = words();
  let what = "";
  const more = [];
  if (!deck) what = A.connectingFirst;
  else if (view !== "read") what = A.startHere;
  else if (!prepared) what = A.preparing;
  else if (prepared.stopped) {
    what = A.partly(prepared.done, prepared.total);
    more.push(A.stopped(stopReason(A, prepared.stopped)));
  } else {
    what = A.ready;
    more.push(prepared.total ? A.prepared(prepared.total) : A.already);
  }
  if (s && view === "read") {
    more.push(A.game(`${s.pin.slice(0, 3)} ${s.pin.slice(3)}`, players, s.join.replace(/^https?:\/\//, "").replace(/\?pin=.*/, "")));
  }
  if (prepared && !prepared.stopped && view === "read") more.push(A.goOn);
  el.innerHTML = `<small>texstage</small><div class="name">${esc(deck?.name || props.deck)}</div>
    <div class="what">${esc(what)}</div>${more.map((m) => `<div class="more">${esc(m)}</div>`).join("")}`;
}

// The status bar: what this object is and whether it can reach the server. Problems show
// until they are solved; "all fine" only for a few seconds when the editing view appears -
// a slideshow started from there must not inherit it (M6).
function setup(extra) {
  const el = $("#setup");
  const problem = extra || status;
  clearTimeout(fineTimer);
  if (!problem && !(view === "edit" && Date.now() < fineUntil)) {
    el.hidden = true;
    return;
  }
  if (!problem) fineTimer = setTimeout(() => setup(""), fineUntil - Date.now());
  const A = words();
  const what = props.phase ? `${textOf(pageTexts().lecturer.phase, props.phase)}${props.quiz ? ` · ${props.quiz}` : ""}` : "";
  const server = `<span class="${deck ? "ok" : "bad"}">● ${esc(A.server)}</span>`;
  el.innerHTML = `<b>texstage</b> · ${esc(what)} · ${server} · ${key ? `<span class="ok">${esc(A.paired)}</span>` : `<span class="bad">${esc(A.notPaired)}</span>`}
    ${status ? `<div>${esc(status)}</div>` : ""}${extra || ""}`;
  el.hidden = false;
  const form = el.querySelector("form");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    key = form.querySelector("input").value.trim();
    try { localStorage.setItem(KEY, key); } catch { /* ignore */ }
    await loadDeck();
  });
}

function pairForm() {
  const A = words();
  return `<form><input type="password" placeholder="${esc(A.keyField)}"><button>${esc(A.pair)}</button></form>`;
}
