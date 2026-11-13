// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// texstage's presenter window (docs/texstage-design.md, sections 5-8): the current step with
// the live quiz views (live.js) and the lecturer's quiz buttons, ink, laser pointer and zoom on
// it, whiteboard pages, the next step, the notes - the deck's own note page or its text -,
// timer and clock, the overview of the frames, and the projector window it opens. It drives the
// game as the PowerPoint add-in does (`slide` with the deck's slide IDs) and sets what the
// projector shows (`screen`, `zoom`, `go`). Keys pressed in the projector window come here
// (BroadcastChannel): a clicker works whichever has focus.
//
// On the laptop it runs with the presenter key, pairs presenter devices (Devices): an iPad
// opens the QR code it shows (/stage#pair=<code>), waits until the lecturer allows it here, and
// from then on runs this window with a token of its own (server/devices.py) - and records the
// lecture (Record, record.js): what the projector shows, with the microphone.
//
// M6: Poll asks a question typed now (the projector shows it instead of the slide until the
// lecturer goes on); Q&A opens the audience's questions and moderates them; Sketches shows
// the drawings of a sketch question and puts the picked ones on the projector.
//
// N3: a video on the slide (video.js) - a file of the deck, YouTube's, Vimeo's or an address of a
// file - plays here without sound, with a bar to play, pause and move it; the projector window
// plays it with the sound.
//
// Live activities (activity.js; docs/live-activities-design.md): the box draws the activity's
// picture here as on the projector; Activities opens the panel - open, close, reveal, the crowd
// graph's terms (merge, hide, approve, the minimum), the clusters (show one on the projector, hide,
// block) -; the agent holds the lease to lay the graph out and to evaluate the queries.
//
// The window speaks the open deck's language (i18n.js; speak): its texts are i18n's "presenter",
// "record" and "lecturer", its dates and numbers the language's (meta.locale), the server's
// refusals its "errors". Before a deck - the presenter key, pairing a device, the deck page - and
// back on the deck page it speaks the browser's.

import { errorText, pageLanguage, usePageLanguage } from "/static/i18n/i18n.js";
import { Client, authHeaders, hostFetch } from "/static/shared/client.js";
import { Stage } from "/static/shared/live.js";
import { sketchSVG } from "/static/shared/sketch.js";
import { textHTML } from "/static/shared/text.js";
import { uploadButton } from "/static/shared/upload.js";
import { annotatedPdf } from "/static/stage/export.js";
import { InkBook, InkLayer, PointerLayer, touched } from "/static/stage/ink.js";
import { PdfDeck, PdfSurface, fit, framesOf, inkKey, linkable, overlaySlide, sequence, shownSlide, zoomOverlay } from "/static/stage/pdfview.js";
import { Microphone, Recording, canRecord, microphones, pickScreen } from "/static/stage/record.js";
import { Dividers, SHARES } from "/static/stage/split.js";
import { ask, askText, notice, tell } from "/static/stage/ask.js";
import { BATCH, ERASER, MARKER, MARKERS, PENS, SIZES, deviceId } from "/static/stage/pen.js";   // (the projector's pen too)
import { VideoBox, mediaAddresses } from "/static/stage/video.js";
import { ActivityAgent, ActivityBox, codeWords, resultLabel, resultTable } from "/static/stage/activity.js";
import { Evaluator } from "/static/stage/evaluator.js";

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const app = $("#app");
const KEY = "texquiz:presenter-key";
const DEVICE = "texstage:device-token";    // a paired presenter device's token (an iPad: no key)
const LAST = "texstage:deck";          // this tab's deck, for reloads
const FOLDER = "texstage:folder";      // this tab's open folder on the deck page
const TAKES = "texstage:takes";        // this tab's recordings, for After the lecture
const PREFS = "texstage:prefs";        // notes as page or text, the text's size, pen and highlighter, microphone, dividers

let auth = null;        // the presenter key (text), or a paired device's token ({device})
let deck = null;        // deck.json of the game's bundle
let pdf = null;         // its stage PDF (pdfview.js)
let aspect = 16 / 9;
let frames = [];        // framesOf(deck)
let items = [];         // the slides and whiteboard pages in order (pdfview.js sequence)
let client = null;
let state = null;       // the server's host view
let stage = null;       // the current step (live.js Stage on a PdfSurface)
let box = null;         // its element: ink, pointer and the pen's input over the slide
let next = null;        // the next step
let note = null;        // the current step's note page
let book = null;        // the ink (ink.js)
let ink = null;         // the current frame's ink layer
let laser = null;       // the laser pointer
let view = null;        // the zoom shown here
let local = null;       // the slide (id) or whiteboard page ("board:<id>") shown here
let pending = null;     // one we asked for and the server has not confirmed yet
let typed = "";         // a frame number being typed (then Enter)
let overview = null;    // the overview while it is open: {el, tiles}
let projector = null;   // the projector window we opened
let channel = null;     // BroadcastChannel with the projector window
let ticker = null;
let tool = "auto";      // auto (a pen draws, the mouse navigates), pen, highlighter, eraser, pointer, zoom
let drawing = null;     // the gesture under way
let lastPen = 0;        // when a pen was last seen: touch is ignored meanwhile (the palm)
let counter = 0;
let flushing = false;
let swipe = null;       // a finger's swipe over the slide: the next or the previous step
let pinger = null;
let rec = null;         // the recording (record.js) - it goes on when the deck or the game changes
let recTicker = null;   // its time and the microphone's level, while it runs
let qaPanel = null;     // the audience's questions while their panel is open (M6)
let gallery = null;     // a sketch question's drawings while their gallery is open (M6)
let agent = null;       // the deck's live activities: the lease, the layout, the evaluation (activity.js)
let actPanel = null;    // their panel while it is open
let lang = "en";        // the window's language (speak): the open deck's, else the browser's
let T = null;           // ... and all its texts (i18n.js texts): T.presenter, T.record, T.lecturer, T.errors
const device = deviceId();
const prefs = loadPrefs();
const follow = new BroadcastChannel("texstage");   // the projector window follows when the deck changes

function loadPrefs() {
  const base = { notes: "text", size: 22, pen: PENS[0], marker: MARKERS[0], width: "M", mic: "", poll: "choice", pollTime: 0,
    split: SHARES, deckSort: "name" };
  try {
    const kept = { ...base, ...JSON.parse(localStorage.getItem(PREFS) || "{}") };
    return { ...kept, split: { ...SHARES, ...kept.split } };
  } catch {
    return base;
  }
}

function savePrefs() {
  try { localStorage.setItem(PREFS, JSON.stringify(prefs)); } catch { /* private mode */ }
}

async function start() {
  speak(null);
  const pairing = new URLSearchParams(location.hash.slice(1)).get("pair");
  if (pairing) {
    history.replaceState(null, "", location.pathname + location.search);   // the code is used up
    return pairThisDevice(pairing);
  }
  const token = stored(DEVICE);
  auth = stored(KEY) || await localKey() || (token ? { device: token } : null);
  if (!auth) return keyForm();
  try {
    await showDecks(true);
  } catch (err) {
    // only the server's refusal of the key (or of this device) forgets it; the server out of
    // reach for a moment, or anything else, leaves it stored for the next try
    if (err?.status !== 403) return keyForm(why(err));
    const removed = typeof auth === "object";
    forget();
    keyForm(removed ? T.presenter.removed : T.errors["bad-key"]);
  }
}

function speak(tag) {
  // the window's language from now on - the open deck's (a tag; a deck built before 2026-10-24
  // names none: English), or the browser's (null) -, and what the page's frame says in it
  T = usePageLanguage(tag);
  lang = pageLanguage();
  $("#status").title = T.lecturer.connection;
  $("#rtt").title = T.presenter.roundTrip;
}

function deckLanguage(d) {
  return d?.language || "";                          // (usePageLanguage: undefined would be no deck)
}

function refusal(r, info) {
  // a refusal of the HTTP API as errorText takes it: its code and its words (or the status)
  return Object.assign(new Error(info?.error || `HTTP ${r.status}`), { code: info?.code });
}

function why(err) {
  return errorText(lang, err);                       // what went wrong, in the window's language
}

function textOf(table, key) {
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : key;   // a phase's name, else itself
}

function decimal(v) {
  return new Intl.NumberFormat(T.meta.locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(v);
}

function hhmm(ms) {
  return new Date(ms).toLocaleTimeString(T.meta.locale, { hour: "2-digit", minute: "2-digit" });
}

function stored(name) {
  try { return localStorage.getItem(name); } catch { return null; }
}

async function localKey() {
  try {
    return (await (await fetch("/api/presenter-key")).json()).key || null;   // only on the server's machine
  } catch {
    return null;
  }
}

function forget() {
  try { localStorage.removeItem(auth && typeof auth === "object" ? DEVICE : KEY); } catch { /* ignore */ }
  auth = null;
}

function keyForm(error = "") {
  speak(null);
  const L = T.lecturer, D = T.presenter.devices;
  app.innerHTML = `<div class="page"><h1>${esc(L.key)}</h1>
    <p>${L.keyWhere("<code>presenter-key</code>")}</p>
    <form class="field" id="keyform"><input id="key" type="password" autocomplete="off" required>
    <button class="primary">${esc(L.go)}</button></form><div class="error">${esc(error)}</div>
    <p>${T.presenter.pairInstead(`<b>${esc(D.button)}</b>`, `<b>${esc(D.pair)}</b>`)}</p></div>`;
  $("#keyform").addEventListener("submit", async (e) => {
    e.preventDefault();
    auth = $("#key").value.trim();
    try {
      await showDecks();
      try { localStorage.setItem(KEY, auth); } catch { /* private mode */ }
    } catch (err) {
      keyForm(err?.status === 403 ? T.errors["bad-key"] : why(err));
    }
  });
}

// ------------------------------------------------------------------ pairing this device (an iPad)
async function pairThisDevice(token) {
  const P = T.presenter.pair, D = T.presenter.devices;
  const show = (html) => { app.innerHTML = `<div class="page"><h1>${esc(P.title)}</h1>${html}</div>`; };
  const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  const again = `<p>${esc(P.again(D.button, D.pair))}</p>`;
  show(`<p>${esc(P.asking)}</p>`);
  let r;
  try {
    r = await post("/api/pair/claim", { token, name: deviceName() });
  } catch {
    return show(`<p class="error">${esc(P.unreachable)}</p>${again}`);
  }
  if (!r.ok) {
    const info = await r.json().catch(() => ({}));
    return show(`<p class="error">${esc(info.code || info.error ? errorText(lang, refusal(r, info)) : P.refused)}</p>${again}`);
  }
  const { claim, code } = await r.json();
  show(`<p>${esc(P.compare)}</p>
    <div class="paircode">${esc(code)}</div><p>${esc(P.waiting)}</p>`);
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    let w;
    try {
      w = await (await post("/api/pair/wait", { claim })).json();
    } catch {
      continue;                                    // the network hiccuped: ask again
    }
    if (w.state === "approved") {
      try { localStorage.setItem(DEVICE, w.device); } catch { /* private mode: paired for this tab */ }
      auth = { device: w.device };
      return showDecks();
    }
    if (w.state !== "claimed") {
      return show(`<p class="error">${esc(w.state === "denied" ? P.denied : P.expired)}</p>${again}`);
    }
  }
}

function deviceName() {
  // what the lecturer sees in the list of devices, e.g. "iPad · Safari"
  const ua = navigator.userAgent;
  const P = T.presenter.pair;
  const what = /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) ? "iPad"
    : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows" : /Mac/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : P.device;
  const browser = /EdgiOS|Edg\//.test(ua) ? "Edge" : /FxiOS|Firefox\//.test(ua) ? "Firefox" : /CriOS|Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : P.browser;
  return `${what} · ${browser}`;
}

// ------------------------------------------------------------------ devices (the laptop)
async function devicesDialog() {
  const el = document.createElement("div");
  el.className = "dialog";
  document.body.append(el);
  let poll = null;
  const close = () => { clearInterval(poll); el.remove(); };
  const D = T.presenter.devices;
  const list = async () => {
    clearInterval(poll);
    const devices = await (await hostFetch("/api/devices", auth)).json();
    el.innerHTML = `<div class="box"><h2>${esc(D.title)}</h2>
      <p>${esc(D.intro)}</p>
      <div class="devices">${devices.map((d) => `<div class="device"><span class="name">${esc(d.name)}</span>
        <span class="meta">${esc(D.paired(new Date(d.paired).toLocaleDateString(T.meta.locale)))}${d.seen ? ` · ${esc(D.seen(hhmm(d.seen)))}` : ""}</span>
        <button data-remove="${esc(d.id)}">${esc(D.remove)}</button></div>`).join("") || `<p class="empty">${esc(D.none)}</p>`}</div>
      <div class="buttons"><button class="primary" id="pairnew">${esc(D.pair)}</button>
        <button class="secondary" id="closedlg">${esc(T.presenter.close)}</button></div></div>`;
    el.querySelector("#closedlg").onclick = close;
    el.querySelector("#pairnew").onclick = pairNew;
    el.querySelectorAll("[data-remove]").forEach((b) => b.onclick = async () => {
      if (!(await ask(D.removeAsk, D.remove))) return;
      await fetch(`/api/devices/${encodeURIComponent(b.dataset.remove)}`, { method: "DELETE", headers: authHeaders(auth) });
      list();
    });
  };
  const pairNew = async () => {
    const offer = await (await fetch("/api/pair", { method: "POST", headers: authHeaders(auth) })).json();
    el.innerHTML = `<div class="box"><h2>${esc(D.pair)}</h2>
      <p>${esc(D.scan)}</p>
      <div class="qr">${offer.qr}</div><p class="url">${esc(offer.url)}</p><div id="claimed"></div>
      <div class="buttons"><button class="secondary" id="back">${esc(D.back)}</button></div></div>`;
    el.querySelector("#back").onclick = list;
    poll = setInterval(async () => {
      const box = el.querySelector("#claimed");
      if (!box) return clearInterval(poll);
      let s;
      try {
        s = await (await fetch(`/api/pair/${encodeURIComponent(offer.token)}`, { headers: authHeaders(auth) })).json();
      } catch {
        return;
      }
      if (s.state === "claimed" && !box.dataset.asked) {
        box.dataset.asked = "1";
        box.innerHTML = `<p>${D.wants(`<b>${esc(s.name)}</b>`)}</p>
          <div class="paircode">${esc(s.code)}</div>
          <div class="buttons"><button class="primary" id="allow">${esc(D.allow)}</button>
            <button class="secondary" id="deny">${esc(D.deny)}</button></div>`;
        const decide = async (allow) => {
          clearInterval(poll);
          await fetch(`/api/pair/${encodeURIComponent(offer.token)}`, { method: "POST",
            headers: { ...authHeaders(auth), "Content-Type": "application/json" }, body: JSON.stringify({ allow }) });
          list();
        };
        box.querySelector("#allow").onclick = () => decide(true);
        box.querySelector("#deny").onclick = () => decide(false);
      } else if (s.state === "expired") {
        clearInterval(poll);
        box.innerHTML = `<p class="error">${esc(D.expired)}</p>`;
      }
    }, 1000);
  };
  await list();
}

// the lecturer's folders - none from a server older than the deck page (2026-10-13), which then lists
// the decks as before: a reload in the lecture must not fail on them
const folderList = () => hostFetch("/api/folders", auth).then((r) => r.json()).catch(() => []);

async function showDecks(resume = false, uploaded = "") {
  const [decks, folders] = await Promise.all([hostFetch("/api/decks", auth).then((r) => r.json()), folderList()]);
  const wanted = new URLSearchParams(location.search).get("bundle");    // texstage present: this deck
  if (wanted) {
    history.replaceState(null, "", location.pathname + location.hash);  // a reload goes back into it as below
    const d = decks.find((x) => x.bundle === wanted && x.stage);
    if (d) return openDeck(d, true);
  }
  if (resume) {                        // a reload in the middle of a lecture: back into it
    let last = null;
    try { last = sessionStorage.getItem(LAST); } catch { /* ignore */ }
    const d = decks.find((x) => x.bundle === last && x.stage);
    if (d) return openDeck(d);
  }
  speak(null);                         // the deck page: the browser's language
  for (const id of ["deckname", "pin", "join", "actions"]) $(`#${id}`).textContent = "";
  $("#status").className = "status";
  offline(false);
  state = null;
  renderRec();
  library(decks, folders, uploaded);
}

// The deck page (server: library.py): folders, opened like a file browser with the path above, the
// decks in them, a search over all of them, by name or newest build first. A card's ⋯ renames,
// moves or deletes it; cards can also be dragged onto a folder or onto a step of the path. Delete
// deletes an uploaded deck; a build on this computer only leaves the list (its next build is back).
function library(decks, folders, uploaded = "") {
  const B = T.presenter.library, L = T.lecturer;
  let byId = new Map(folders.map((f) => [f.id, f]));
  const pathOf = (fid) => {                       // the folder and the folders it is in, from the top
    const out = [];
    for (let f = byId.get(fid); f && out.length < 64; f = byId.get(f.parent)) out.unshift(f);
    return out;
  };
  const within = (fid, root) => pathOf(fid).some((f) => f.id === root);    // root itself, or inside it
  const where = (fid) => pathOf(fid).map((f) => f.name).join(" › ") || B.all;
  const byName = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
  const shown = (d) => d.label || d.name;
  let here = null;
  try { here = sessionStorage.getItem(FOLDER) || null; } catch { /* ignore */ }
  if (!byId.has(here)) here = null;
  let query = "";
  let dragged = null;
  const laptop = typeof auth === "string";        // the presenter key (a paired device uploads nothing)
  app.innerHTML = `<div class="page"><h1>${esc(L.decks)}</h1>
    <p>${B.intro("<code>texstage present &lt;deck&gt;</code>")}${laptop ? ` ${L.upload("<code>.bundle.zip</code>")}` : ""}</p>
    ${laptop ? '<div class="uploadbar"><span id="upload"></span><span class="uploaded">' + esc(uploaded) + "</span></div>" : ""}
    <div class="libbar"><nav class="crumbs" aria-label="${esc(B.path)}"></nav>
      <input type="search" class="libsearch" placeholder="${esc(B.search)}" aria-label="${esc(B.searchLabel)}">
      <select class="libsort" aria-label="${esc(B.order)}"><option value="name">${esc(B.byName)}</option>
        <option value="newest">${esc(B.newest)}</option></select>
      <button class="secondary" id="newfolder">${esc(B.newFolder)}</button></div>
    <div class="decks"></div></div>`;
  const list = app.querySelector(".decks");
  const crumbs = app.querySelector(".crumbs");
  const search = app.querySelector(".libsearch");
  const sort = app.querySelector(".libsort");
  sort.value = prefs.deckSort === "newest" ? "newest" : "name";
  const built = (ms) => new Date(ms).toLocaleString(T.meta.locale);

  const folderCard = (f) => {
    const subs = folders.filter((g) => g.parent === f.id).length;
    const parts = [subs ? B.folders(subs) : "", B.decks(decks.filter((d) => d.folder === f.id).length),
      query ? B.within(where(f.parent)) : ""];
    return `<div class="deckcard folder" draggable="true" data-folder="${esc(f.id)}" tabindex="0">
      <span class="ficon" aria-hidden="true"></span>
      <div class="info"><div class="name">${esc(f.name)}</div><div class="meta">${esc(parts.filter(Boolean).join(" · "))}</div></div>
      <button class="more" data-more-folder="${esc(f.id)}" title="${esc(B.folderMenu)}" aria-label="${esc(B.folderActions)}">⋯</button></div>`;
  };
  const deckCard = (d) => `<div class="deckcard" draggable="true" data-deck="${esc(d.deck)}">
      <div class="info"><div class="name">${esc(shown(d))}</div>
      <div class="meta">${esc([query && byId.has(d.folder) ? B.within(where(d.folder)) : "", d.label ? d.name : "", d.deck,
    L.quizzes(d.quizzes), L.slides(d.slides), L.built(built(d.built))].filter(Boolean).join(" · "))}</div></div>
      ${d.game ? `<span class="tag open">${esc(L.game(d.game.pin, d.game.players))}</span>` : ""}
      ${d.failing?.length ? `<span class="tag bad" title="${esc(d.failing.map((f) => B.refFailed(f.activity, f.reference, f.error))
    .join("\n"))}">${esc(B.refsFail(d.failing.length))}</span>` : ""}
      ${d.stage ? `<button class="primary" data-present="${esc(d.bundle)}">${esc(B.present)}</button>`
    : `<span class="tag" title="${esc(B.noStageWhy)}">${esc(B.noStage)}</span>`}
      <button class="more" data-more-deck="${esc(d.bundle)}" title="${esc(B.deckMenu)}" aria-label="${esc(B.deckActions)}">⋯</button></div>`;

  const render = () => {
    try { sessionStorage.setItem(FOLDER, here || ""); } catch { /* ignore */ }
    const q = query.trim().toLocaleLowerCase();
    crumbs.innerHTML = [`<button class="crumb${here ? "" : " here"}" data-to="">${esc(B.all)}</button>`,
      ...pathOf(here).map((f) => `<button class="crumb${f.id === here ? " here" : ""}" data-to="${esc(f.id)}">${esc(f.name)}</button>`)]
      .join('<span class="sep">›</span>');
    const hit = (...texts) => texts.some((t) => String(t || "").toLocaleLowerCase().includes(q));
    const fs = folders.filter((f) => (q ? hit(f.name) : (f.parent || null) === here)).sort((a, b) => byName(a.name, b.name));
    const ds = decks.filter((d) => (q ? hit(d.label, d.name, d.deck) : (byId.has(d.folder) ? d.folder : null) === here))
      .sort((a, b) => (sort.value === "newest" ? b.built - a.built : byName(shown(a), shown(b))));
    list.innerHTML = fs.map(folderCard).join("") + ds.map(deckCard).join("")
      || `<p class="empty">${esc(q ? B.noMatch : here ? B.empty : L.noDecks)}</p>`;
  };
  const refresh = async () => {
    [decks, folders] = await Promise.all([hostFetch("/api/decks", auth).then((r) => r.json()), folderList()]);
    byId = new Map(folders.map((f) => [f.id, f]));
    if (!byId.has(here)) here = null;
    render();
  };
  const send = async (method, path, body) => {
    const r = await fetch(path, { method, body: body === undefined ? undefined : JSON.stringify(body),
      headers: { ...authHeaders(auth), "Content-Type": "application/json" } });
    const info = await r.json().catch(() => ({}));
    if (!r.ok) throw refusal(r, info);
    return info;
  };
  const act = async (job, done = "") => {         // a change, then the page as the server has it now
    try {
      await job();
      if (done) notice(done);
    } catch (err) {
      await tell(B.notDone(why(err)));
    }
    await refresh();
  };
  const moveTo = (item, to) => act(() => (item.deck
    ? send("PATCH", `/api/decks/${encodeURIComponent(item.deck)}`, { folder: to })
    : send("PATCH", `/api/folders/${encodeURIComponent(item.folder)}`, { parent: to })), B.moved(to ? byId.get(to)?.name : B.all));
  const menu = (button, entries) => {             // a small menu under a card's ⋯: [label, action]
    document.querySelector(".libmenu")?.remove();
    const el = document.createElement("div");
    el.className = "libmenu";
    el.setAttribute("role", "menu");
    el.innerHTML = entries.map(([label], i) => `<button role="menuitem" data-i="${i}">${esc(label)}</button>`).join("");
    document.body.append(el);
    const r = button.getBoundingClientRect();
    el.style.top = `${Math.max(8, Math.min(r.bottom + 4, innerHeight - el.offsetHeight - 8))}px`;
    el.style.left = `${Math.max(8, r.right - el.offsetWidth)}px`;
    const outside = (e) => { if (!el.contains(e.target)) close(); };
    const keys = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    const close = () => {
      el.remove();
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", keys, true);
    };
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-i]");
      if (b) { close(); entries[+b.dataset.i][1](); }
    });
    setTimeout(() => {
      document.addEventListener("pointerdown", outside, true);
      document.addEventListener("keydown", keys, true);
    });
    el.querySelector("button")?.focus();
  };
  const chooseFolder = (title, item) => new Promise((resolve) => {    // undefined: cancelled, null: the top
    const rows = [];
    const walk = (parent, depth) => folders.filter((f) => (f.parent || null) === parent).sort((a, b) => byName(a.name, b.name))
      .forEach((f) => {
        if (item.folder && within(f.id, item.folder)) return;             // a folder not into itself
        rows.push([f, depth]);
        walk(f.id, depth + 1);
      });
    walk(null, 1);
    const now = item.deck ? (decks.find((d) => d.deck === item.deck)?.folder ?? null) : (byId.get(item.folder)?.parent ?? null);
    const el = document.createElement("div");
    el.className = "dialog";
    el.innerHTML = `<div class="box"><h2>${esc(title)}</h2><div class="folderpick">
      <button data-to="" ${now === null ? "disabled" : ""}>${esc(B.all)}</button>
      ${rows.map(([f, depth]) => `<button data-to="${esc(f.id)}" style="padding-left:${12 + depth * 18}px" ${now === f.id ? "disabled" : ""}>${esc(f.name)}</button>`).join("")}
      </div><div class="buttons"><button class="secondary" data-cancel>${esc(T.dialog.cancel)}</button></div></div>`;
    const keys = (e) => { if (e.key === "Escape") { e.stopPropagation(); finish(undefined); } };
    const finish = (to) => {
      document.removeEventListener("keydown", keys, true);
      el.remove();
      resolve(to);
    };
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-to]");
      if (b) finish(b.dataset.to || null);
      else if (e.target.closest("[data-cancel]") || e.target === el) finish(undefined);
    });
    document.addEventListener("keydown", keys, true);
    document.body.append(el);
  });
  const deckMenu = (button, d) => menu(button, [
    [B.rename, async () => {
      const name = await askText(B.renameAsk(shown(d), d.name), shown(d), B.renameYes);
      if (name !== null) act(() => send("PATCH", `/api/decks/${encodeURIComponent(d.deck)}`, { label: name.trim() === d.name ? "" : name }));
    }],
    [B.move, async () => {
      const to = await chooseFolder(B.moveAsk(shown(d)), { deck: d.deck });
      if (to !== undefined) moveTo({ deck: d.deck }, to);
    }],
    [d.uploaded ? B.delete : B.unlist, async () => {
      const question = d.uploaded ? B.deleteAsk(shown(d)) : B.unlistAsk(shown(d));
      if (await ask(question, d.uploaded ? B.deleteYes : B.unlistYes))
        act(() => send("DELETE", `/api/decks/${encodeURIComponent(d.deck)}`), d.uploaded ? B.deleted(shown(d)) : B.unlisted(shown(d)));
    }]]);
  const folderMenu = (button, f) => menu(button, [
    [B.rename, async () => {
      const name = await askText(B.folderName, f.name, B.renameYes);
      if (name !== null) act(() => send("PATCH", `/api/folders/${encodeURIComponent(f.id)}`, { name }));
    }],
    [B.move, async () => {
      const to = await chooseFolder(B.moveFolderAsk(f.name), { folder: f.id });
      if (to !== undefined) moveTo({ folder: f.id }, to);
    }],
    [B.delete, async () => {
      if (await ask(B.deleteFolderAsk(f.name), B.deleteYes))
        act(() => send("DELETE", `/api/folders/${encodeURIComponent(f.id)}`));
    }]]);
  const openFolder = (fid) => {
    here = fid;
    query = search.value = "";
    render();
  };

  list.addEventListener("click", (e) => {
    const present = e.target.closest("[data-present]");
    const moreDeck = e.target.closest("[data-more-deck]");
    const moreFolder = e.target.closest("[data-more-folder]");
    const folderCard = e.target.closest(".deckcard.folder");
    if (present) openDeck(decks.find((d) => d.bundle === present.dataset.present), true);
    else if (moreDeck) deckMenu(moreDeck, decks.find((d) => d.bundle === moreDeck.dataset.moreDeck));
    else if (moreFolder) folderMenu(moreFolder, byId.get(moreFolder.dataset.moreFolder));
    else if (folderCard) openFolder(folderCard.dataset.folder);
  });
  list.addEventListener("keydown", (e) => {
    const card = e.target.closest?.(".deckcard.folder");
    if (card && e.key === "Enter" && e.target === card) openFolder(card.dataset.folder);
  });
  crumbs.addEventListener("click", (e) => {
    const step = e.target.closest("[data-to]");
    if (step) openFolder(step.dataset.to || null);
  });
  search.addEventListener("input", () => { query = search.value.trim(); render(); });
  sort.addEventListener("change", () => { prefs.deckSort = sort.value; savePrefs(); render(); });
  app.querySelector("#newfolder").onclick = async () => {
    const name = await askText(here ? B.newFolderIn(byId.get(here)?.name) : B.newFolderAsk, "", B.create);
    if (name !== null && name.trim()) act(() => send("POST", "/api/folders", { name, parent: here }));
  };
  // dragging a card onto a folder, or onto a step of the path (a .bundle.zip dropped is an upload)
  list.addEventListener("dragstart", (e) => {
    const card = e.target.closest?.("[data-deck], [data-folder]");
    if (!card) return;
    dragged = card.dataset.deck ? { deck: card.dataset.deck } : { folder: card.dataset.folder };
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", card.dataset.deck || card.dataset.folder);
    card.classList.add("dragging");
  });
  list.addEventListener("dragend", () => {
    dragged = null;
    app.querySelectorAll(".dragging, .droptarget").forEach((x) => x.classList.remove("dragging", "droptarget"));
  });
  const dropOn = (e) => {                         // the folder a card is dragged over: {el, to}
    const el = e.target.closest?.(".deckcard.folder, .crumb[data-to]");
    if (!el || !dragged) return null;
    const to = el.dataset.folder ?? (el.dataset.to || null);
    if (dragged.folder && to !== null && within(to, dragged.folder)) return null;
    return { el, to };
  };
  for (const zone of [list, crumbs]) {
    zone.addEventListener("dragover", (e) => {
      const t = dropOn(e);
      if (!t) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      t.el.classList.add("droptarget");
    });
    zone.addEventListener("dragleave", (e) => e.target.closest?.(".droptarget")?.classList.remove("droptarget"));
    zone.addEventListener("drop", (e) => {
      const t = dropOn(e);
      if (!t) return;
      e.preventDefault();
      const item = dragged;
      dragged = null;
      moveTo(item, t.to);
    });
  }
  render();
  if (laptop) uploadButton($("#upload"), auth, (message) => showDecks(false, message));
}

async function openDeck(d, chosen = false) {     // chosen: Present clicked (not a reload in the lecture)
  app.innerHTML = `<div class="page"><p>${esc(T.presenter.library.loading(d.name))}</p></div>`;
  try {
    deck = await (await hostFetch(`/api/deck/${d.bundle}`, auth)).json();
    pdf?.close();
    pdf = await PdfDeck.open(deck.bundle, auth);
  } catch (err) {
    app.innerHTML = `<div class="page"><h1>${esc(d.name)}</h1><p class="error">${esc(why(err))}</p>
      <p><button class="secondary" id="back">${esc(T.lecturer.decks)}</button></p></div>`;
    $("#back").onclick = () => showDecks();
    return;
  }
  speak(deckLanguage(deck));                      // from here on the deck's language
  const P = T.presenter, O = P.tools, L = T.lecturer;
  try { sessionStorage.setItem(LAST, d.bundle); } catch { /* ignore */ }
  frames = framesOf(deck);
  items = sequence(deck, []);
  aspect = deck.pdf.width / deck.pdf.height;
  document.documentElement.style.setProperty("--tq-aspect", String(aspect));
  $("#deckname").textContent = deck.name;
  const laptop = typeof auth === "string";        // the presenter key: the projector and the devices are here
  $("#actions").innerHTML = `${laptop ? `<button id="projector" title="${esc(P.projectorTitle)}">${esc(P.projector)}</button>
    <button id="devices" title="${esc(P.devices.buttonTitle)}">${esc(P.devices.button)}</button>` : ""}
    <button id="morebtn" class="morebtn" title="${esc(P.moreTitle)}" aria-expanded="false">⋯</button>
    <span class="more" id="more"><button id="archive" title="${esc(P.archiveTitle)}">${esc(P.archive)}</button>
    <button id="csv" title="${esc(L.csvTitle)}">${esc(L.csv)}</button><button id="newgame" title="${esc(L.newGameTitle)}">${esc(L.newGame)}</button>
    <button id="decks" title="${esc(L.decksTitle)}">${esc(L.decks)}</button></span>`;
  $("#morebtn").onclick = () => {
    const open = $("#more").classList.toggle("open");
    $("#morebtn").setAttribute("aria-expanded", String(open));
  };
  closeActivities();                    // a panel of the deck before stood in the column that is made anew
  closeQa();
  app.innerHTML = `<div class="pgrid">
    <section class="current"><div class="fitbox" id="currentbox"><div id="stage"></div><button class="onscreen" id="onscreen" hidden></button></div></section>
    <div class="split main" role="separator" tabindex="0" aria-label="${esc(P.splitMain)}"
      title="${esc(P.splitMainTitle)}"></div>
    <section class="side">
      <div class="label">${esc(P.next)} <span id="nextinfo"></span></div>
      <div class="nextwrap"><div class="pagebox" id="nextbox"></div></div>
      <div class="split next" role="separator" tabindex="0" aria-orientation="horizontal"
        aria-label="${esc(P.splitNext)}"
        title="${esc(P.splitNextTitle)}"></div>
      <div class="label">${esc(P.notes)} <span class="tools"><button id="notesmode"></button>
        <button id="smaller" title="${esc(P.smaller)}">A−</button><button id="larger" title="${esc(P.larger)}">A+</button></span></div>
      <div class="notes" id="notes"><div class="notewrap" id="notewrap"><div class="pagebox" id="notebox"></div></div>
        <div class="notetext" id="notetext"></div></div>
    </section>
    <footer class="toolbar" id="toolbar">
      <span class="group"><button data-tool="auto" title="${esc(O.auto)}">↖</button>
        <button data-tool="pen" title="${esc(O.penTitle)}">✎ ${esc(O.pen)}</button><button data-tool="highlighter" title="${esc(O.markerTitle)}">▮ ${esc(O.marker)}</button>
        <button data-tool="eraser" title="${esc(O.eraserTitle)}">⌫ ${esc(O.eraser)}</button>
        <button data-tool="pointer" title="${esc(O.laserTitle)}">● ${esc(O.laser)}</button>
        <button data-tool="zoom" title="${esc(O.zoomTitle)}">⌕ ${esc(O.zoom)}</button></span>
      <span class="group" id="swatches"></span><span class="group" id="sizes"></span>
      <span class="group"><button id="undo" title="${esc(O.undo)}">↶</button><button id="redo" title="${esc(O.redo)}">↷</button>
        <button id="clear" title="${esc(O.clearTitle)}">${esc(O.clear)}</button></span>
      <span class="group"><button id="blank" title="${esc(O.boardTitle)}">＋ ${esc(O.board)}</button>
        <button id="gridpage" title="${esc(O.gridTitle)}">＋ ${esc(O.grid)}</button></span>
      <span class="group"><button id="pollbtn" title="${esc(O.pollTitle)}">▤ ${esc(O.poll)}</button>
        <button id="qabtn" title="${esc(O.qaTitle)}">？ ${esc(O.qa)} <span class="badge" id="qacount" hidden></span></button>
        <button id="sketchbtn" title="${esc(O.sketchesTitle)}" hidden>✎ ${esc(O.sketches)} <span class="badge" id="sketchcount"></span></button>
        <button id="actbtn" title="${esc(O.activitiesTitle)}" hidden>◎ ${esc(O.activities)} <span class="badge count" id="actcount" hidden></span></button></span>
    </footer>
    <footer class="bar">
      <div class="clock"><button id="timer" title="${esc(P.timer)}"></button><span class="elapsed" id="elapsed">0:00</span>
        <span class="target" id="target"></span><button id="reset" title="${esc(P.reset)}">↺</button>
        <button id="settarget" title="${esc(P.target)}">⏱</button><span class="wall" id="wall"></span></div>
      <div class="nav"><button id="prev" title="${esc(P.prev)}">◀</button><span class="where" id="where"></span>
        <button id="next" title="${esc(P.nextStep)}">▶</button></div>
      <div class="screens"><button data-screen="black" title="${esc(P.blackTitle)}">${esc(P.black)}</button>
        <button data-screen="white" title="${esc(P.whiteTitle)}">${esc(P.white)}</button>
        <button data-screen="freeze" title="${esc(P.freezeTitle)}">${esc(P.freeze)}</button>
        <button id="overview" title="${esc(P.overviewTitle)}">${esc(P.overview)}</button></div>
    </footer></div>`;
  client?.close();
  client = new Client({
    onStatus: (s) => {
      $("#status").className = `status ${s}`;
      if (s === "closed") offline(true);                        // in words: a dot alone is overlooked
      else if (s === "open") offline(false);                    // (not while it tries again: no flicker)
      if (s === "open" && book?.loaded.size) {                  // back after a break: the ink anew
        book.reset();
        ink?.reload();
      }
    },
    onState: (m) => { state = m; update(); },
    onEvent: (m) => {
      if (m.t === "ink") {
        if (m.op === "reload") inkAnew();               // another window started anew or continued a lecture
        else book.event(m);
      } else if (m.t === "pointer") {
        if (m.off) laser.off();
        else laser.move(m.x, m.y);
      }
    },
    onBye: (m) => refused({ code: m.reason, message: m.message }),
  });
  book = new InkBook(client);
  agent?.destroy();
  agent = deck.items?.activity ? new ActivityAgent({ send: (msg) => client.send(msg) }) : null;
  if (agent && Object.values(deck.items.activity).some((a) => a.input === "code")) {
    // the queries are evaluated here while this window has the lease (evaluator.js) - unless the
    // server checks them (activity.work: checks "server"), and then this window makes no evaluator
    const own = agent;
    own.jobs = (work) => {
      if (work.checks === "server") return;
      own.evaluator ??= new Evaluator({ send: (msg) => client.send(msg), base: `/bundle/${deck.bundle}/` });
      own.evaluator.take(work).then((any) => { if (any) setTimeout(() => agent?.renew(), 50); });
    };
  }
  stage = new Stage($("#stage"), { send: (cmd) => client.send(cmd).catch(alertError), controls: true, surface: new PdfSurface(pdf),
    sketches: (quiz, players) => client.send({ t: "sketch.get", quiz, players }).then((r) => r.sketches),
    types: { video: VideoBox, activity: ActivityBox },
    host: { role: "presenter", send: (msg) => client.send(msg).catch(alertError), media: mediaAddresses(deck.bundle, auth),
      read: (msg) => client.send(msg), agent } });
  box = $("#stage");
  ink = new InkLayer(book, aspect);
  laser = new PointerLayer(aspect);
  box.append(ink.element, laser.element, Object.assign(document.createElement("div"), { className: "input", id: "input" }),
    Object.assign(document.createElement("div"), { className: "zoombox", id: "zoombox", hidden: true }));
  next = new PdfSurface(pdf, { className: "pdfpage" });
  note = new PdfSurface(pdf, { className: "pdfpage", pageOf: (s) => s?.note });
  $("#nextbox").append(next.element);
  $("#notebox").append(note.element);
  fit($("#currentbox"), aspect);
  fit($("#nextbox"), aspect);
  fit($("#notebox"), aspect);
  new Dividers($(".pgrid"), prefs.split, (shares) => { prefs.split = shares; savePrefs(); });
  box.addEventListener("pointerdown", onDown, true);
  box.addEventListener("pointermove", onMove, true);
  if (RAW) box.addEventListener("pointerrawupdate", onRaw, true);
  box.addEventListener("pointerup", onUp, true);
  box.addEventListener("pointercancel", onUp, true);
  box.addEventListener("pointerleave", () => { if (tool === "pointer" && !drawing) pointerOff(); });
  // the slide's web links: a click while navigating (↖) opens one; a pen draws, the tools keep theirs
  linkable(box, { pdf: () => pdf, page: pageHere, at: toSlide,
    active: (e) => tool === "auto" && !drawing && e.pointerType !== "pen" });
  channel?.close();
  channel = new BroadcastChannel(`texstage:${deck.bundle}`);
  channel.onmessage = (e) => {
    if (e.data?.type === "key") onKey(e.data);
    else if (e.data?.type === "video") {                // the projector's browser wants a click (video.js)
      notice(e.data.click === "sound" ? T.presenter.videoSound : T.presenter.videoStart);
    }
  };
  $("#prev").onclick = () => move(-1);
  $("#next").onclick = () => move(1);
  $("#timer").onclick = toggleTimer;
  $("#reset").onclick = async () => { if (await ask(T.presenter.resetAsk, T.presenter.resetYes)) send({ t: "timer", action: "reset" }); };
  $("#settarget").onclick = setTarget;
  app.querySelectorAll("[data-screen]").forEach((b) => b.onclick = () => screen(b.dataset.screen));
  app.querySelectorAll("[data-tool]").forEach((b) => b.onclick = () => (b.dataset.tool === "zoom" ? zoomKey()
    : setTool(b.dataset.tool === tool ? "auto" : b.dataset.tool)));
  $("#onscreen").onclick = () => { if (state?.stage?.zoom) send({ t: "zoom", rect: null }); };   // zoomed: the whole slide
  $("#undo").onclick = () => inkAction("ink.undo");
  $("#redo").onclick = () => inkAction("ink.redo");
  $("#clear").onclick = () => inkAction("ink.clear");
  $("#blank").onclick = () => addBoard("blank");
  $("#gridpage").onclick = () => addBoard("grid");
  $("#pollbtn").onclick = pollDialog;
  $("#qabtn").onclick = () => (qaPanel ? closeQa() : openQa());
  $("#sketchbtn").onclick = () => (gallery ? closeGallery() : openGallery(sketchQuiz()));
  $("#actbtn").onclick = () => (actPanel ? closeActivities() : openActivities());
  $("#overview").onclick = toggleOverview;
  $("#notesmode").onclick = () => { prefs.notes = prefs.notes === "page" ? "text" : "page"; savePrefs(); render(); };
  $("#smaller").onclick = () => textSize(-2);
  $("#larger").onclick = () => textSize(2);
  if (laptop) {
    $("#projector").onclick = openProjector;
    $("#devices").onclick = devicesDialog;
  }
  $("#csv").onclick = downloadResults;
  $("#archive").onclick = archiveDialog;
  $("#newgame").onclick = async () => {
    if (!(await ask(T.lecturer.newGameAsk, T.lecturer.newGame))) return;
    await client.send({ t: "restart" }).catch(alertError);
  };
  $("#decks").onclick = () => {
    client.close();
    client = null;
    closeOverview();
    closeQa();
    closeGallery();
    closeActivities();
    agent?.destroy();
    agent = null;
    try { sessionStorage.removeItem(LAST); } catch { /* ignore */ }
    showDecks();
  };
  renderTools();
  clearInterval(ticker);
  ticker = setInterval(tickClock, 250);
  const credentials = typeof auth === "string" ? { key: auth } : { device: auth.device };
  const hello = { t: "hello", role: "stage", ...credentials, deck: deck.deck, bundle: deck.bundle };
  const mine = client;
  let welcome;
  try {
    // chosen (Present clicked, texstage present): this build's game even where a newer build's runs - not so
    // a reload in the lecture, nor this hello again after a break (a window of an older build: newer-build)
    welcome = await client.login(chosen ? { ...hello, chosen: true } : hello);
  } catch (err) {
    if (client === mine) refused(err);            // (not when this window has opened another deck meanwhile)
    return;
  }
  if (chosen) mine.relogin(hello);                 // after a break: the same hello, no choice any more
  follow.postMessage({ type: "deck", bundle: deck.bundle });     // an open projector window: this deck now - its
  //                                                               hello after this one's, which may have chosen it
  clearInterval(pinger);
  pinger = setInterval(ping, 5000);
  ping();
  if (chosen && welcome?.earlier && !welcome.presenters) await newOrContinued(welcome.earlier);
}

// The server would not give this window its game, or took it away: a newer build of the deck is played (a
// window of a build before it, connected again), the device was removed, ... - the deck page, and why.
function refused(err) {
  client.close();
  if (err?.code === "removed") {                   // a device removed in the presenter window
    forget();
    speak(null);
    keyForm(T.presenter.removed);
  } else {
    showDecks().then(() => tell(why(err)), () => keyForm());
  }
}

async function newOrContinued(e) {
  // the deck's ink and whiteboard pages from before: a new presentation leaves them to the lecture
  // they belong to (in the archive), a continuation goes on with them (docs/texstage-design.md, 24)
  const E = T.presenter.earlier;
  const left = [e.frames ? E.ink(e.frames) : "", e.boards ? E.boards(e.boards) : ""].filter(Boolean);
  const what = left.length > 1 ? E.both(...left) : left[0] || "";
  const fresh = await ask([E.ask(lectureTime(e.at), what), e.open ? E.newGame : ""].filter(Boolean).join(" "), E.fresh, E.goOn);
  let r = null;
  if (fresh && e.open) r = await client.send({ t: "lecture.new" }).catch(alertError);
  else if (!fresh && !e.open) r = await client.send({ t: "lecture.continue", game: e.game }).catch(alertError);
  if (r) inkAnew();
}

function lectureTime(ms) {
  // when it was, as the question above says it: "of today, 10:15", "of 3 November, 10:15"
  const d = new Date(ms);
  const E = T.presenter.earlier;
  if (d.toDateString() === new Date().toDateString()) return E.today(hhmm(ms));
  return E.on(d.toLocaleDateString(T.meta.locale, { day: "numeric", month: "long" }), hhmm(ms));
}

function inkAnew() {
  book.reset();
  ink?.reload();
}

// The connection is gone: said across the window, since the slides here go on while nothing that is
// done reaches the server - the projector and the phones stay where they are. The round trip's last
// time goes with it; the next ping that comes back brings a new one.
function offline(on) {
  let el = document.querySelector("#offline");
  if (on && !el) {
    el = document.createElement("div");
    el.id = "offline";
    el.className = "offline";
    el.setAttribute("role", "alert");
    el.textContent = T.presenter.offline;
    document.body.append(el);
    $("#rtt").textContent = "";
  } else if (!on) {
    el?.remove();
  }
}

async function ping() {
  // the round trip to the server, next to the connection's dot: the room's network or the tunnel
  if (!client) return;
  const t0 = performance.now();
  try {
    await client.send({ t: "ping" });
    $("#rtt").textContent = `${Math.round(performance.now() - t0)} ms`;
  } catch { /* the next one */ }
}

function send(cmd) {
  return client.send(cmd).catch(alertError);
}

function alertError(err) {
  if (err?.code !== "no-round") tell(why(err));
}

function inkError(err) {
  console.warn("texstage: ink", err);              // a stroke the server did not take: not worth a dialog
}

const idOf = (item) => (item.board ? `board:${item.board}` : item.id);

function itemFor(id) {
  return items.find((it) => idOf(it) === id) || items[0];
}

function update() {
  const s = state.session;
  agent?.update(state);
  $("#pin").textContent = `${T.lecturer.pin} ${s.pin.slice(0, 3)} ${s.pin.slice(3)}`;
  $("#join").textContent = `${T.lecturer.players(s.players)} · ${s.join.replace(/\?pin=.*/, "")}`;   // cut short from the end
  items = sequence(deck, state.stage?.boards);
  renderRec();
  const there = state.stage?.board ? `board:${state.stage.board}` : s.slide;   // what the server shows
  if (pending !== null && there === pending) pending = null;
  if (pending === null) {
    if (there === null || there === undefined) {
      local = pending = deck.slides[0].id;                            // a fresh game: the first slide
      client.send({ t: "slide", slide: local }).catch(() => {});
    } else {
      local = there;
    }
  }
  render();
}

function render() {
  if (!state) return;
  const i = Math.max(0, items.findIndex((it) => idOf(it) === local));
  const current = items[i];
  const after = items[i + 1] || null;
  const st = state.stage || {};
  const overlay = overlaySlide(state);                    // a poll or sketches instead of the slide (M6)
  const there = st.board ? `board:${st.board}` : state.session.slide;
  view = !overlay && there === local ? st.zoom || null : null;   // the projector's zoom, on the slide it zooms
  stage.surface.zoom = view;
  stage.show(overlay || current, deck, state, () => client.now());
  if (!overlay && current?.page) pdf.links(current.page);  // its links ready for the first click
  zoomOverlay(box, view);
  ink.show(inkKey(overlay || current), view);
  laser.show(view);
  next.show(after);
  const P = T.presenter;
  const phase = (p) => textOf(T.lecturer.phase, p);
  $("#nextinfo").textContent = `· ${!after ? P.end
    : after.board ? P.aBoard : `${P.frame(after.frame)}${after.phase ? ` · ${phase(after.phase)}` : ""}`}`;
  if (typed) {
    $("#where").textContent = P.typing(typed);
  } else if (overlay) {
    $("#where").textContent = overlay.overlay === "poll" ? P.pollShown : P.sketchesShown;
  } else if (current.board) {
    $("#where").textContent = P.boardAfter(current.after);
  } else {
    const steps = new Set(deck.slides.filter((s) => s.frame === current.frame).map((s) => s.step)).size;
    const live = current.phase ? ` · ${phase(current.phase)}${current.quiz ? ` ${current.quiz}` : ""}` : "";
    $("#where").textContent = `${P.frameOf(current.frame, frames.length)}${steps > 1 ? ` · ${P.stepOf(current.step, steps)}` : ""}${live}`;
  }
  // the notes: the deck's note page, or its text
  const asText = prefs.notes === "text";
  // ... as text - unless this slide's notes have none (a picture, a formula): then its note page
  const text = asText && (Boolean(current.board) || !current.note || Boolean((current.notes || "").trim()));
  $("#notesmode").textContent = asText ? P.notesPage : P.notesText;
  $("#notesmode").title = asText ? P.notesPageTitle : P.notesTextTitle;
  $("#notewrap").hidden = text;
  $("#notetext").hidden = !text;
  note.show(text || current.board ? null : current);
  if (text) {
    const paragraphs = (current.notes || "").split("\n").filter(Boolean);
    $("#notetext").style.fontSize = `${prefs.size}px`;
    $("#notetext").innerHTML = paragraphs.map((p) => `<p>${esc(p)}</p>`).join("")
      || `<p class="empty">${esc(current.board ? P.boardNote : P.noNotes)}</p>`;
  } else if (current.board || !current.note) {
    $("#notewrap").dataset.empty = current.board ? P.boardNote : P.noNotePage;
  } else {
    delete $("#notewrap").dataset.empty;
  }
  // what the projector shows, if not just this
  const shown = shownSlide(deck, state);
  const frozen = shown?.overlay ? (shown.overlay === "poll" ? P.frozen.poll : P.frozen.sketches)
    : shown?.board ? P.frozen.board : P.frozen.frame(shown ? shown.frame : "?");
  // (zoomed: a tap on it, Z or the Zoom button give the whole slide back - not Esc: in a
  // full-screen window Esc ends full screen, and an iPad has none)
  const zoomed = Boolean(view) && !["black", "white", "freeze"].includes(st.screen);
  const away = st.screen === "black" ? P.blackScreen : st.screen === "white" ? P.whiteScreen
    : st.screen === "freeze" ? frozen : zoomed ? P.zoomed(decimal(1 / view.h)) : "";
  $("#onscreen").textContent = away ? P.onscreen(away) : "";
  $("#onscreen").hidden = !away;
  $("#onscreen").disabled = !zoomed;
  $('[data-tool="zoom"]').classList.toggle("zoomed", Boolean(view));
  app.querySelectorAll("[data-screen]").forEach((b) => press(b, b.dataset.screen === st.screen));
  if (overview) markOverview();
  renderInteraction();
  prefetch(i);
}

function prefetch(i) {
  const [w, h] = stage.surface.size();
  const [nw, nh] = next.size();
  const [mw, mh] = note.size();
  const jobs = [];
  for (const it of items.slice(i + 1, i + 3)) if (it.page) jobs.push([it.page, w, h]);
  const second = items[i + 2];
  if (second?.page) jobs.push([second.page, nw, nh]);
  const following = items[i + 1];
  if (following?.note && prefs.notes !== "text") jobs.push([following.note, mw, mh]);
  pdf.prefetch(jobs);
}

// /stage?timing logs every slide change to the console: how long this window took to render it, and
// until it was painted - the design's budget is 100 ms, also with 1,000 phones in the game (AF 15.1; from
// F0's spike, for the load runs: tools/load/run.py)
const TIMING = new URLSearchParams(location.search).has("timing");

function go(item) {
  const id = idOf(item);
  const t0 = TIMING ? performance.now() : 0;
  local = pending = id;
  render();
  if (TIMING) {
    const t1 = performance.now();
    requestAnimationFrame(() => setTimeout(() => console.log(
      `[timing] slide ${id}: render ${(t1 - t0).toFixed(1)} ms, painted ${(performance.now() - t0).toFixed(1)} ms`)));
  }
  if (item.board) send({ t: "go", board: item.board });
  else send({ t: "slide", slide: item.id });
  startTimerOnce();
}

function move(step) {
  if (endOverlay()) return;                          // a poll or sketches: first back to the slide
  const i = Math.max(0, items.findIndex((it) => idOf(it) === local));
  const j = Math.min(items.length - 1, Math.max(0, i + step));
  if (idOf(items[j]) !== local) go(items[j]);
}

function endOverlay() {
  // the projector shows the slide again, instead of a poll or sketches; whether it did not
  const st = state?.stage || {};
  if (st.poll) send({ t: "poll.show", quiz: null });
  else if (st.sketches) send({ t: "sketch.show", quiz: st.sketches.quiz, players: [] });
  else return false;
  return true;
}

function shownHere() {
  // what the current view shows - and what the pen writes on
  return overlaySlide(state) || itemFor(local);
}

function pageHere() {
  // the stage PDF's page the current view shows (its links), or null: a whiteboard page, a poll
  const s = state && shownHere();
  return s && !s.board && !s.overlay ? s.page || null : null;
}

function jumpToFrame(n) {
  const f = frames.find((x) => x.frame === n);
  if (f) go(f.first);
}

function screen(mode) {
  const now = state?.stage?.screen || "live";
  send({ t: "screen", screen: now === mode ? "live" : mode });
}

async function addBoard(kind) {
  const current = itemFor(local);
  const after = current.board ? current.after : current.frame;
  const r = await client.send({ t: "board", after, kind }).catch(alertError);
  if (r?.board) {
    items = sequence(deck, [...(state.stage?.boards || []), { id: r.board, after, kind }]);
    go({ board: r.board, kind, after });
  }
}

// ------------------------------------------------------------------ ink, pointer, zoom
function setTool(t) {
  if (tool === "pointer" && t !== "pointer") pointerOff();
  tool = t;
  $("#input").className = `input${t === "auto" ? "" : ` on ${t}`}`;
  renderTools();
}

function renderTools() {
  app.querySelectorAll("[data-tool]").forEach((b) => press(b, b.dataset.tool === tool));
  const marker = tool === "highlighter";
  const colors = marker ? MARKERS : PENS;
  const chosen = marker ? prefs.marker : prefs.pen;
  const O = T.presenter.tools;
  $("#swatches").innerHTML = colors.map((c) => `<button class="swatch${c === chosen ? " on" : ""}" data-color="${c}"
    style="--c:${c}" aria-pressed="${c === chosen}"
    title="${esc(`${marker ? O.markerColour : O.penColour}: ${O.colours[c] || c}`)}"></button>`).join("");
  $("#swatches").querySelectorAll("[data-color]").forEach((b) => b.onclick = () => {
    prefs[marker ? "marker" : "pen"] = b.dataset.color;
    savePrefs();
    if (tool === "auto" || tool === "eraser" || tool === "pointer" || tool === "zoom") setTool(marker ? "highlighter" : "pen");
    else renderTools();
  });
  $("#sizes").innerHTML = Object.keys(SIZES).map((s) => `<button class="size${s === prefs.width ? " on" : ""}"
    data-size="${s}" aria-pressed="${s === prefs.width}" title="${esc(`${O.width}: ${O.widths[s] || s}`)}">${s}</button>`).join("");
  $("#sizes").hidden = marker;
  $("#sizes").querySelectorAll("[data-size]").forEach((b) => b.onclick = () => {
    prefs.width = b.dataset.size;
    savePrefs();
    renderTools();
  });
}

// The pen comes first (an iPad's Pencil): while it draws and for PEN_QUIET ms after its last
// input, the palm and the fingers select, scroll, zoom, tap and swipe nothing, anywhere in the
// window - iOS would start a gesture of its own on such a touch and cancel the pen's stroke.
const PEN_QUIET = 1500;
const penBusy = () => Boolean(drawing?.pen) || performance.now() - lastPen < PEN_QUIET;
for (const type of ["pointerdown", "pointermove", "pointerup"]) {
  document.addEventListener(type, (e) => { if (e.pointerType === "pen") lastPen = performance.now(); }, true);
}
document.addEventListener("pointerdown", (e) => {
  if (e.pointerType === "touch" && penBusy()) {
    e.preventDefault();
    e.stopPropagation();                         // no button, divider or swipe gets it
  }
}, true);
for (const type of ["touchstart", "touchmove"]) {   // no scrolling, zooming or click of the palm
  document.addEventListener(type, (e) => {
    if (penBusy() && [...e.changedTouches].some((t) => t.touchType !== "stylus")) e.preventDefault();
  }, { capture: true, passive: false });
}
for (const type of ["selectstart", "contextmenu", "gesturestart", "gesturechange"]) {
  document.addEventListener(type, (e) => {
    if (penBusy() && !e.target.closest?.("input, textarea")) e.preventDefault();
  }, { capture: true, passive: false });
}

function toolFor(e) {
  if (e.pointerType === "pen") {
    lastPen = performance.now();
    if (e.button === 5 || (e.buttons & 32)) return "eraser";            // the pen's eraser end
    return tool === "auto" ? "pen" : tool;
  }
  if (e.pointerType === "touch" && performance.now() - lastPen < PEN_QUIET) return null;   // the palm
  if (e.button !== 0) return null;
  return tool === "auto" ? null : tool;
}

function toSlide(e) {
  const r = box.getBoundingClientRect();
  const v = view || { x: 0, y: 0, w: 1, h: 1 };
  return [v.x + ((e.clientX - r.left) / r.width) * v.w, v.y + ((e.clientY - r.top) / r.height) * v.h];
}

const round = (v, d) => Math.round(v * d) / d;

function point(e) {
  const [x, y] = toSlide(e);
  const pressure = e.pointerType === "pen" && e.pressure > 0 ? e.pressure : 0.5;
  return [round(x, 1e4), round(y, 1e4), round(pressure, 1e3)];
}

function onDown(e) {
  if (e.target.closest?.(".tq-typectl")) return;            // a video's bar (video.js): its own
  const t = toolFor(e);
  if (!t && e.pointerType === "touch" && tool === "auto" && performance.now() - lastPen > PEN_QUIET) {
    swipe = { id: e.pointerId, x: e.clientX, y: e.clientY };      // a finger: a swipe steps on or back
    return;
  }
  if (!t || !deck || !state) return;
  const frame = inkKey(shownHere());
  if ((!frame && t !== "pointer") || (t === "zoom" && overlaySlide(state))) return;   // sketches: no ink; polls: no zoom
  e.preventDefault();
  e.stopPropagation();
  try { box.setPointerCapture(e.pointerId); } catch { /* ignore */ }
  const p = point(e);
  if (t === "pen" || t === "highlighter") {
    const stroke = { id: `${device}-${Date.now().toString(36)}-${++counter}`, frame, tool: t,
      color: t === "pen" ? prefs.pen : prefs.marker, width: t === "pen" ? SIZES[prefs.width] : MARKER,
      sim: e.pointerType !== "pen", points: [p], live: true };
    book.put(stroke);
    book.changed(frame);
    drawing = { id: e.pointerId, stroke, frame, sent: 0 };
    begin(drawing);
  } else if (t === "eraser") {
    drawing = { id: e.pointerId, frame, erased: new Set() };
    eraseAt(p);
  } else if (t === "pointer") {
    drawing = { id: e.pointerId, pointer: true };
    pointerAt(p, e.pointerType);
  } else if (t === "zoom") {
    drawing = { id: e.pointerId, zoom: [p[0], p[1], p[0], p[1]] };
    showZoomBox();
  }
  if (drawing) drawing.pen = e.pointerType === "pen";   // the palm waits until it is done (penBusy)
}

function onRaw(e) {
  // the mouse's raw input (Chromium): the laser's positions, hovering or pressed
  if (tool === "pointer" && e.pointerType === "mouse" && (!drawing || drawing.pointer)) pointerAt(point(e), "mouse", e.timeStamp);
}

function onMove(e) {
  const raw = RAW && e.pointerType === "mouse";      // (the mouse's laser comes with onRaw)
  if (!drawing) {
    if (tool === "pointer" && e.pointerType !== "touch" && !raw) pointerAt(point(e), e.pointerType, e.timeStamp);   // the mouse or a hovering pen
    return;
  }
  if (e.pointerId !== drawing.id) return;
  e.preventDefault();
  const all = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
  let pointed = null;
  for (const ev of all.length ? all : [e]) {
    const p = point(ev);
    if (drawing.stroke) drawing.stroke.points.push(p);
    else if (drawing.erased) eraseAt(p);
    else if (drawing.pointer) pointed = p;         // (the laser: only where it is now)
    else if (drawing.zoom) drawing.zoom.splice(2, 2, p[0], p[1]);
  }
  if (pointed && !raw) pointerAt(pointed, e.pointerType, e.timeStamp);
  if (drawing.stroke) {
    book.changed(drawing.frame);
    flushSoon();
  }
  if (drawing?.zoom) showZoomBox();
}

function onUp(e) {
  if (swipe && e.pointerId === swipe.id) {
    const dx = e.clientX - swipe.x;
    const dy = e.clientY - swipe.y;
    swipe = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) move(dx < 0 ? 1 : -1);
    return;
  }
  if (!drawing || e.pointerId !== drawing.id) return;
  const d = drawing;
  drawing = null;
  if (d.stroke) {
    flush(d);
    d.stroke.live = false;
    book.changed(d.frame);
    client.send({ t: "ink.end", stroke: d.stroke.id }).catch(inkError);
  } else if (d.erased?.size) {
    client.send({ t: "ink.erase", device, frame: d.frame, strokes: [...d.erased] }).catch(inkError);
  } else if (d.zoom) {
    zoomTo(d.zoom);
  }
}

function begin(d) {
  // the stroke to the server, which shows it on the projector: its points so far
  const s = d.stroke;
  const pts = s.points.slice(0, BATCH);
  d.sent = pts.length;
  client.send({ t: "ink.begin", device, frame: d.frame, points: pts,
    stroke: { id: s.id, tool: s.tool, color: s.color, width: s.width, sim: s.sim } }).catch(inkError);
  flush(d);
}

function flushSoon() {
  if (flushing) return;
  flushing = true;
  requestAnimationFrame(() => {
    flushing = false;
    if (drawing?.stroke) flush(drawing);
  });
}

function flush(d) {
  // the points drawn since the last message: to the server, which shows them on the projector
  const pts = d.stroke.points;
  while (d.sent < pts.length) {
    const batch = pts.slice(d.sent, d.sent + BATCH);
    d.sent += batch.length;
    client.send({ t: "ink.points", stroke: d.stroke.id, points: batch }).catch(inkError);
  }
}

function eraseAt([x, y]) {
  const strokes = book.strokes(drawing.frame).filter((s) => !s.live);
  const hit = touched(strokes, x, y, ERASER * (view ? view.h : 1), aspect);
  if (!hit.length) return;
  for (const id of hit) {
    drawing.erased.add(id);
    book.frame(drawing.frame).delete(id);
  }
  book.changed(drawing.frame);
}

async function inkAction(t) {
  if (!deck || !state) return;
  const frame = inkKey(shownHere());
  if (!frame) return;
  const r = await client.send({ t, device, frame }).catch(inkError);
  if (r?.event) book.event(r.event);
  if (t === "ink.clear" && r?.event) notice(T.presenter.tools.cleared);   // no question
}

function pointerAt([x, y], type, t = performance.now()) {
  // the laser where the mouse, pen or finger is, to the projector at once. Here a mouse's is the
  // cursor itself, a red dot (--laser-cursor): the system draws it with the hand, while a dot the
  // page draws comes a frame or two late. A pen's or a finger's (an iPad: no cursor) is drawn.
  if (type === "mouse") return laserAhead(x, y, t);
  laser.move(x, y);
  laserSend({ t: "pointer", x, y });
}

// The projector's window shows the mouse's laser two or three frames after the mouse moved (the
// browser draws it there; here the system draws the cursor at once). So the mouse's raw input
// is taken (pointerrawupdate, not held back to the next frame), and the dot is sent where the
// mouse will be LASER_LEAD ms later at its speed; when it stops, where it is.
const LASER_LEAD = 25;          // ms ahead
const LASER_EVERY = 8;          // ms between two positions at most (the mouse may say 1000 a second)
const LASER_SETTLE = 30;        // ms without a movement: stopped
const LASER_REACH = 0.03;       // the lead at most this far (of the slide's width)
const RAW = "onpointerrawupdate" in window;
let track = [];                 // the mouse's last places: [x, y, ms]
let laserSent = 0;
let settle = 0;

function laserAhead(x, y, t) {
  track.push([x, y, t]);
  while (track.length > 2 && t - track[1][2] > 40) track.shift();
  clearTimeout(settle);
  settle = setTimeout(() => laserSend({ t: "pointer", x, y }), LASER_SETTLE);   // stopped: where it is
  if (t - laserSent < LASER_EVERY) return;
  laserSent = t;
  const old = [...track].reverse().find((p) => t - p[2] >= 12) || track[0];
  const dt = t - old[2];
  const clamp = (d) => Math.max(-LASER_REACH, Math.min(LASER_REACH, d));
  const ax = dt > 0 ? clamp(((x - old[0]) / dt) * LASER_LEAD) : 0;
  const ay = dt > 0 ? clamp(((y - old[1]) / dt) * LASER_LEAD) : 0;
  laserSend({ t: "pointer", x: round(x + ax, 1e4), y: round(y + ay, 1e4) });
}

function pointerOff() {
  clearTimeout(settle);
  track = [];
  laser.off();
  laserSend({ t: "pointer", off: true });
}

// The laser's positions go one at a time: the next only when the server has answered the last
// one - then the newest, the ones in between are dropped. A pen on the iPad sends a position
// for every movement, and through the tunnel those piled up: seconds behind on the projector.
// Now the dot is at most a round trip late, whatever the way; on the laptop the answer comes
// within a millisecond.
let laserNext = null;           // the newest position not sent yet
let laserFlying = null;         // the client whose answer is awaited

function laserSend(msg) {
  laserNext = msg;
  if (laserFlying === client || !client) return;
  const c = laserFlying = client;
  const go = () => {
    const m = laserNext;
    laserNext = null;
    if (!m || client !== c) {
      if (laserFlying === c) laserFlying = null;
      return;
    }
    Promise.race([c.send(m).catch(() => {}), new Promise((r) => setTimeout(r, 1000))]).then(go);   // (a lost answer)
  };
  go();
}

// the mouse's laser in this window: the cursor as the projector's red dot
document.documentElement.style.setProperty("--laser-cursor", (() => {
  const c = Object.assign(document.createElement("canvas"), { width: 32, height: 32 });
  const ctx = c.getContext("2d");
  const glow = ctx.createRadialGradient(16, 16, 0, 16, 16, 14);
  glow.addColorStop(0, "rgba(255, 40, 60, 0.95)");
  glow.addColorStop(0.35, "rgba(255, 40, 60, 0.85)");
  glow.addColorStop(1, "rgba(255, 40, 60, 0)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(16, 16, 14, 0, Math.PI * 2);
  ctx.fill();
  return `url(${c.toDataURL()}) 16 16, crosshair`;
})());

function showZoomBox() {
  const el = $("#zoombox");
  if (!drawing?.zoom) {
    el.hidden = true;
    return;
  }
  const [x0, y0, x1, y1] = drawing.zoom;
  const v = view || { x: 0, y: 0, w: 1, h: 1 };
  const pct = (a, o, s) => `${(((a - o) / s) * 100).toFixed(3)}%`;
  Object.assign(el.style, { left: pct(Math.min(x0, x1), v.x, v.w), top: pct(Math.min(y0, y1), v.y, v.h),
    width: pct(v.x + Math.abs(x1 - x0), v.x, v.w), height: pct(v.y + Math.abs(y1 - y0), v.y, v.h) });
  el.hidden = false;
}

function zoomTo([x0, y0, x1, y1]) {
  // a box of the slide's shape around what was dragged (a click: twice as large there)
  let s = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0));
  if (s < 0.02) s = (view ? view.w : 1) / 2;
  s = Math.min(1, Math.max(0.08, s));
  const x = Math.min(1 - s, Math.max(0, (x0 + x1) / 2 - s / 2));
  const y = Math.min(1 - s, Math.max(0, (y0 + y1) / 2 - s / 2));
  $("#zoombox").hidden = true;
  setTool("auto");
  send({ t: "zoom", rect: s >= 1 ? null : { x, y, w: s, h: s } });
}

function zoomKey() {
  if (state?.stage?.zoom) send({ t: "zoom", rect: null });
  else setTool(tool === "zoom" ? "auto" : "zoom");
}

// ------------------------------------------------------------------ timer and clock
function timerMs() {
  const t = state?.stage?.timer || {};
  return (t.elapsed || 0) + (t.since !== null && t.since !== undefined ? client.now() - t.since : 0);
}

function startTimerOnce() {
  // the timer starts with the first step the lecturer takes, as PowerPoint's with the show
  const t = state?.stage?.timer;
  if (t && (t.since === null || t.since === undefined) && !t.elapsed) send({ t: "timer", action: "start" });
}

function toggleTimer() {
  const running = state?.stage?.timer?.since !== null && state?.stage?.timer?.since !== undefined;
  send({ t: "timer", action: running ? "pause" : "start" });
}

async function setTarget() {
  const t = state?.stage?.timer || {};
  const now = t.target ? String(Math.round(t.target / 60000)) : "";
  const answer = await askText(T.presenter.targetAsk, now);
  if (answer === null) return;
  const minutes = Number(answer.replace(",", "."));
  if (answer.trim() && !(minutes > 0)) return tell(T.presenter.targetNumber);
  send({ t: "timer", action: "target", seconds: answer.trim() ? Math.round(minutes * 60) : 0 });
}

function clock(ms) {
  const s = Math.floor(Math.max(0, ms) / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

function tickClock() {
  if (!state || !$("#elapsed")) return;
  const t = state.stage?.timer || {};
  const ms = timerMs();
  const running = t.since !== null && t.since !== undefined;
  $("#elapsed").textContent = clock(ms);
  $("#elapsed").classList.toggle("stopped", !running);
  $("#timer").textContent = running ? "⏸" : "▶";
  const target = $("#target");
  if (t.target) {
    const left = t.target - ms;
    target.textContent = left >= 0 ? T.presenter.left(clock(left)) : T.presenter.over(clock(-left));
    target.className = `target ${left < 0 ? "over" : left < 5 * 60000 ? "soon" : ""}`;
  } else {
    target.textContent = "";
  }
  $("#wall").textContent = hhmm(Date.now());
}

function textSize(step) {
  prefs.size = Math.min(48, Math.max(12, prefs.size + step));
  if (prefs.notes !== "text") prefs.notes = "text";
  savePrefs();
  render();
}

// ------------------------------------------------------------------ overview
function toggleOverview() {
  if (overview) closeOverview();
  else openOverview();
}

function openOverview() {
  // a tile per frame (its last step: everything shown) and per whiteboard page
  const tiles = [];
  items.forEach((it, i) => {
    const after = items[i + 1];
    if (it.board) tiles.push({ item: it, go: it, label: T.presenter.overviewPage, key: idOf(it) });
    else if (!after || after.board || after.frame !== it.frame) {
      tiles.push({ item: it, go: frames.find((f) => f.frame === it.frame).first, label: String(it.frame), key: String(it.frame) });
    }
  });
  const el = document.createElement("div");
  el.className = "overview";
  el.innerHTML = `<div class="ovhead">${esc(T.presenter.overviewHead)}</div>
    <div class="ovgrid">${tiles.map((t) => `<button class="tile"><span class="num">${esc(t.label)}</span></button>`).join("")}</div>`;
  document.body.append(el);
  [...el.querySelectorAll(".tile")].forEach((b, i) => {
    const surface = new PdfSurface(pdf, { className: "pdfpage" });
    b.prepend(surface.element);
    b.onclick = () => { go(tiles[i].go); closeOverview(); };
    Object.assign(tiles[i], { b, surface });
  });
  overview = { el, tiles };
  requestAnimationFrame(() => tiles.forEach((t) => t.surface.show(t.item)));
  markOverview();
}

function markOverview() {
  const current = itemFor(local);
  const keyNow = current.board ? idOf(current) : String(current.frame);
  for (const t of overview.tiles) {
    const on = t.key === keyNow;
    t.b.classList.toggle("on", on);
    if (on && !overview.scrolled) {
      t.b.scrollIntoView({ block: "center" });
      overview.scrolled = true;
    }
  }
}

// The overview's own keys: the arrows move a mark from tile to tile - not the slide behind it, which
// the projector would follow -, Enter or Space goes to the marked tile, Home and End mark the first
// and the last. (A number and Enter, G and Esc are onKey's.)
function overviewKey(k) {
  const tiles = overview.tiles;
  const at = overview.at ?? Math.max(0, tiles.findIndex((t) => t.b.classList.contains("on")));
  const top = tiles[0].b.offsetTop;
  const columns = tiles.filter((t) => t.b.offsetTop === top).length || 1;
  const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: columns, ArrowUp: -columns, PageDown: 1, PageUp: -1,
    Backspace: -1 }[k];
  if (step !== undefined) markTile(Math.min(tiles.length - 1, Math.max(0, at + step)));
  else if (k === "Home") markTile(0);
  else if (k === "End") markTile(tiles.length - 1);
  else if (k === "Enter" || k === " ") {
    go(tiles[at].go);
    closeOverview();
  } else return false;
  return true;
}

function markTile(i) {
  overview.at = i;
  overview.tiles.forEach((t, j) => t.b.classList.toggle("sel", j === i));
  overview.tiles[i].b.scrollIntoView({ block: "nearest" });
}

function closeOverview() {
  overview?.el.remove();
  overview = null;
}

// A button that is on or off: its look, and what a screen reader says of it
function press(b, on) {
  b.classList.toggle("on", on);
  b.setAttribute("aria-pressed", String(on));
}

// ------------------------------------------------------------------ projector window
function openProjector() {
  if (projector && !projector.closed) {
    projector.focus();
    return;
  }
  // opened at once (a pop-up needs the click), then moved to the other screen
  projector = window.open(`/stage/projector?bundle=${encodeURIComponent(deck.bundle)}`, "texstage-projector",
    "popup,width=1280,height=720");
  if (!projector) {
    tell(T.presenter.popup);
    return;
  }
  placeOnOtherScreen(projector);
}

async function placeOnOtherScreen(win) {
  // Chromium's Window Management API (it asks once for the permission); elsewhere the
  // lecturer drags the window to the projector
  try {
    if (!("getScreenDetails" in window)) return;
    const screens = await window.getScreenDetails();
    const other = screens.screens.find((s) => s !== screens.currentScreen);
    if (!other) return;
    win.moveTo(other.availLeft, other.availTop);
    win.resizeTo(other.availWidth, other.availHeight);
  } catch { /* not allowed */ }
}

async function downloadResults() {
  const r = await hostFetch(`/api/results/${state.session.id}.csv`, auth);
  save(await r.blob(), (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "results.csv");
}

function save(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ------------------------------------------------------------------ polls, questions, sketches (M6)
const KINDS = ["yesno", "choice", "scale", "words", "text", "sketch"];   // their names and notes: presenter.poll
const TIMES = [10, 20, 30, 45, 60, 90, 120, 180, 300];
const POLL_TIMES = { yesno: 30, choice: 30, scale: 30, words: 45, text: 90, sketch: 120 };

function sketchQuiz() {
  // the sketch question the phones answer now - the deck's or a poll -, if there is one
  const quiz = state?.session?.current;
  const q = quiz && (deck.quizzes[quiz] || state.polls?.[quiz]);
  return q?.type === "sketch" ? quiz : null;
}

function renderInteraction() {
  // the Q&A button with the number of open questions; Sketches while a sketch question runs
  const open = (state.qa?.questions || []).filter((q) => q.state === "open").length;
  $("#qacount").textContent = open;
  $("#qacount").hidden = !open;
  $("#qabtn").classList.toggle("live", Boolean(state.qa?.open));
  const quiz = sketchQuiz();
  $("#sketchbtn").hidden = !quiz;
  if (quiz) $("#sketchcount").textContent = state.rounds?.[quiz]?.answered ?? 0;
  if (qaPanel) renderQa();
  if (gallery) syncGallery();
  const acts = state.stage?.activity;
  $("#actbtn").hidden = !deck.items?.activity;
  const current = acts?.items?.[acts.current];
  $("#actcount").textContent = current?.count ?? 0;
  $("#actcount").hidden = !current?.count;
  $("#actbtn").classList.toggle("live", current?.phase === "open");
  if (actPanel) renderActivities();
}

function pollDialog() {
  if (!state) return;
  const el = document.createElement("div");
  el.className = "dialog";
  let kind = POLL_TIMES[prefs.poll] ? prefs.poll : "choice";
  let choices = 4;                                    // answer fields, 2 to 6
  const texts = ["", "", "", "", "", ""];
  const asked = Object.entries(state.polls || {}).reverse();
  const Q = T.presenter.poll;
  el.innerHTML = `<div class="box wide"><h2>${esc(Q.title)}</h2>
    <div class="kinds">${KINDS.map((k) => `<button data-kind="${k}">${esc(Q.kinds[k])}</button>`).join("")}</div>
    <label class="col">${esc(Q.question)} <textarea id="pollprompt" rows="3" maxlength="300"
      placeholder="${esc(Q.placeholder)}"></textarea></label>
    <div class="preview" id="pollpreview" hidden></div>
    <div id="pollanswers"></div>
    <div class="buttons"><label>${esc(Q.time)} <select id="polltime">${TIMES.map((t) => `<option value="${t}">${esc(Q.seconds(t))}</option>`).join("")}</select></label>
      <span class="spacer"></span><button class="primary" id="pollstart">${esc(Q.start)}</button>
      <button class="secondary" id="closedlg">${esc(T.dialog.cancel)}</button></div>
    <p class="error" id="pollerr"></p>
    ${asked.length ? `<h3>${esc(Q.asked)}</h3><div class="pollhist">${asked.map(([quiz, q]) => `<div class="device">
      <span class="name">${esc(textOf(Q.kinds, q.adhoc))}</span>
      <span class="meta">${esc((q.prompt?.text || "").slice(0, 60) || Q.slides)} · ${esc(Q.answers(state.rounds?.[quiz]?.answered ?? 0))}</span>
      <button data-show="${esc(quiz)}">${esc(Q.show)}</button></div>`).join("")}</div>` : ""}</div>`;
  document.body.append(el);
  const prompt = el.querySelector("#pollprompt");
  const time = el.querySelector("#polltime");
  const preview = () => {
    const p = el.querySelector("#pollpreview");
    p.hidden = !prompt.value.includes("$");
    if (!p.hidden) p.innerHTML = textHTML(prompt.value, preview);
  };
  const answers = () => {
    // A-F: how many, their texts (optional), one or several; the others: what the phones do
    const box = el.querySelector("#pollanswers");
    el.querySelectorAll("[data-kind]").forEach((b) => b.classList.toggle("on", b.dataset.kind === kind));
    if (kind !== "choice") {
      box.innerHTML = `<p>${esc(Q.notes[kind])}</p>`;
      return;
    }
    box.innerHTML = `<div class="buttons left">${esc(Q.count)} ${[2, 3, 4, 5, 6].map((n) => `<button class="count${n === choices ? " on" : ""}"
        data-count="${n}">${n}</button>`).join("")}<label class="check"><input type="checkbox" id="pollmulti"> ${esc(Q.several)}</label></div>
      <div class="answerlist">${texts.slice(0, choices).map((t, i) => `<label><b>${String.fromCharCode(65 + i)}</b>
        <input data-answer="${i}" maxlength="120" value="${esc(t)}" placeholder="${esc(Q.optional)}"></label>`).join("")}</div>`;
    box.querySelectorAll("[data-count]").forEach((b) => b.onclick = () => { choices = +b.dataset.count; answers(); });
    box.querySelectorAll("[data-answer]").forEach((input) => input.oninput = () => { texts[+input.dataset.answer] = input.value; });
  };
  const pick = (k) => {
    kind = k;
    time.value = String(POLL_TIMES[k]);
    answers();
  };
  el.querySelectorAll("[data-kind]").forEach((b) => b.onclick = () => pick(b.dataset.kind));
  prompt.oninput = preview;
  el.querySelector("#closedlg").onclick = () => el.remove();
  const keys = (e) => {                               // Esc closes it, as it closes the other dialogs
    if (el.isConnected && e.key === "Escape") {
      e.stopPropagation();
      el.remove();
    }
    if (!el.isConnected) document.removeEventListener("keydown", keys, true);
  };
  document.addEventListener("keydown", keys, true);
  el.querySelectorAll("[data-show]").forEach((b) => b.onclick = () => {
    send({ t: "poll.show", quiz: b.dataset.show });
    el.remove();
  });
  el.querySelector("#pollstart").onclick = async () => {
    const spec = { t: "poll.create", kind, prompt: prompt.value, time: Number(time.value) };
    if (kind === "choice") {
      spec.answers = texts.slice(0, choices);
      spec.select = el.querySelector("#pollmulti").checked ? "multiple" : "single";
    }
    try {
      await client.send(spec);
      prefs.poll = kind;
      savePrefs();
      el.remove();
    } catch (err) {
      el.querySelector("#pollerr").textContent = why(err);
    }
  };
  pick(kind);
  prompt.focus();
}

function openQa() {
  qaPanel = document.createElement("aside");
  qaPanel.className = "qapanel";
  const Q = T.presenter.qa;
  qaPanel.innerHTML = `<div class="qahead"><h2>${esc(Q.title)}</h2>
      <label class="check" title="${esc(Q.openTitle)}"><input type="checkbox" id="qaopen"> ${esc(Q.open)}</label>
      <button class="secondary" id="qaclose" title="${esc(Q.closeTitle)}">✕</button></div>
    <div class="qabody" id="qabody"></div>`;
  if (actPanel) closeActivities();      // one panel at a time: they stand in the same place
  dock(qaPanel);
  qaPanel.querySelector("#qaopen").onchange = (e) => send({ t: "qa.open", on: e.target.checked });
  qaPanel.querySelector("#qaclose").onclick = closeQa;
  qaPanel.querySelector("#qabody").addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const question = b.closest("[data-q]").dataset.q;
    const act = b.dataset.act;
    if (act === "show") send({ t: "qa.show", question });
    else if (act === "hide") send({ t: "qa.show", question: null });
    else if (act === "done" || act === "open") send({ t: "qa.mark", question, state: act });
    else if (act === "delete") {
      if (await ask(T.presenter.qa.deleteAsk, T.presenter.qa.delete)) send({ t: "qa.mark", question, state: "deleted" });
    } else if (act === "block") {
      if (await ask(T.presenter.qa.blockAsk, T.presenter.qa.block)) send({ t: "qa.block", question });
    }
  });
  qaPanel.listed = "";
  renderQa();
}

function closeQa() {
  qaPanel?.remove();
  qaPanel = null;
  undock();
}

function renderQa() {
  // open questions by votes, with what the lecturer can do; the answered ones below
  const qa = state?.qa || { open: false, questions: [] };
  qaPanel.querySelector("#qaopen").checked = qa.open;
  const shown = state.stage?.question?.id || null;
  const key = JSON.stringify([qa, shown]);
  if (key === qaPanel.listed) return;
  qaPanel.listed = key;
  const Q = T.presenter.qa;
  const item = (q) => `<div class="qaitem${q.id === shown ? " shown" : ""}${q.state === "done" ? " done" : ""}" data-q="${esc(q.id)}">
      <div class="qavotes">▲ ${q.votes}</div><div class="qatext">${textHTML(q.text, () => {
        if (qaPanel) {
          qaPanel.listed = "";                     // KaTeX came: the formulas typeset
          renderQa();
        }
      })}</div>
      <div class="qaacts">${q.state === "done" ? `<button data-act="open">${esc(Q.reopen)}</button>`
        : `${q.id === shown ? `<button data-act="hide" class="on">${esc(Q.hide)}</button>`
          : `<button data-act="show" title="${esc(Q.showTitle)}">${esc(Q.show)}</button>`}
        <button data-act="done">${esc(Q.done)}</button>`}<button data-act="delete">${esc(Q.delete)}</button>
        <button data-act="block" title="${esc(Q.blockTitle)}">${esc(Q.block)}</button></div></div>`;
  const open = qa.questions.filter((q) => q.state === "open");
  const done = qa.questions.filter((q) => q.state === "done");
  qaPanel.querySelector("#qabody").innerHTML = `${open.map(item).join("")
    || `<p class="empty">${esc(qa.open ? Q.none : Q.closed)}</p>`}
    ${done.length ? `<h3>${esc(Q.answered)}</h3>${done.map(item).join("")}` : ""}`;
}

// ------------------------------------------------------------------ live activities (activity.js)
function openActivities() {
  actPanel = document.createElement("aside");
  actPanel.className = "qapanel actpanel";
  actPanel.innerHTML = `<div class="qahead"><h2>${esc(T.presenter.activity.title)}</h2><select id="actpick"></select>
      <button class="secondary" id="actclose" title="${esc(T.presenter.activity.closeTitle)}">✕</button></div>
    <div class="qabody" id="actbody"></div>`;
  if (qaPanel) closeQa();               // one panel at a time: they stand in the same place
  dock(actPanel);
  actPanel.chosen = null;               // the activity shown here (the current one by default)
  actPanel.merging = null;              // a term on its way into another: {role, term}
  actPanel.seen = "";
  actPanel.querySelector("#actclose").onclick = closeActivities;
  actPanel.querySelector("#actpick").onchange = (e) => {
    actPanel.chosen = e.target.value;
    actPanel.picked = true;             // the lecturer's choice stays while the panel is open
    actPanel.seen = "";
    renderActivities();
  };
  actPanel.querySelector("#actbody").addEventListener("click", onActivityClick);
  actPanel.querySelector("#actbody").addEventListener("change", (e) => {
    if (e.target.id === "actmin") send({ t: "activity.min", activity: actPanel.chosen, min: Number(e.target.value) || 1 });
  });
  renderActivities();
}

function closeActivities() {
  actPanel?.remove();
  actPanel = null;
  undock();
}

// A panel - Activities, Q&A - stands in the column, where the next slide was: the notes stay to be read
// below it, and nothing of the slide is covered. (In a narrow window, where the column is below the
// slide, it lies over the window as before: stage.css.)
function dock(panel) {
  const side = $(".side");
  side.prepend(panel);
  side.classList.add("docked");
}

function undock() {
  const side = document.querySelector(".side");
  if (side && !side.querySelector(":scope > .qapanel")) side.classList.remove("docked");
}

async function onActivityClick(e) {
  const b = e.target.closest("button[data-act]");
  if (!b || !actPanel) return;
  const activity = actPanel.chosen;
  const act = b.dataset.act;
  const term = b.closest("[data-term]")?.dataset;
  if (act === "open" || act === "close") send({ t: `activity.${act}`, activity });
  else if (act === "reveal") {
    if (await ask(T.presenter.activity.revealAsk, T.presenter.activity.reveal)) {
      send({ t: "activity.reveal", activity });
    }
  } else if (act === "hide" || act === "unhide") {
    send({ t: "activity.hide", activity, role: term.role, term: term.term, on: act === "hide" });
  } else if (act === "approve" || act === "unapprove") {
    send({ t: "activity.approve", activity, role: term.role, term: term.term, on: act === "approve" });
  } else if (act === "merge") {
    actPanel.merging = { role: term.role, term: term.term };
    actPanel.seen = "";
    renderActivities();
  } else if (act === "into") {
    const m = actPanel.merging;
    actPanel.merging = null;
    actPanel.seen = "";
    if (m) send({ t: "activity.merge", activity, role: m.role, term: m.term, into: term.term });
  } else if (act === "unmerge") send({ t: "activity.unmerge", activity, role: term.role, term: term.term });
  else if (act === "cancel") {
    actPanel.merging = null;
    actPanel.seen = "";
    renderActivities();
  } else if (act === "show") send({ t: "activity.show", activity, cluster: b.dataset.key });
  else if (act === "unshow") send({ t: "activity.show", activity, cluster: null });
  else if (act === "hidec") send({ t: "activity.hide", activity, contribution: b.dataset.contribution, on: true });
  else if (act === "block") {
    if (await ask(T.presenter.activity.blockAsk, T.presenter.activity.block)) {
      send({ t: "activity.block", activity, contribution: b.dataset.contribution });
    }
  }
}

function renderActivities() {
  // the chosen activity: its phase and buttons, and what the presenter window's picture holds
  const items = deck.items?.activity || {};
  const acts = state?.stage?.activity || { current: null, items: {} };
  const pick = actPanel.querySelector("#actpick");
  const ids = Object.keys(items);
  // the activity shown: the one the lecturer picked here - else the open one, else the one on this
  // slide (one that waits for its "Open" is not the server's current one yet: the panel showed the
  // deck's first, and "Open" would have opened that), else the one shown so far, else the deck's first
  const onSlide = itemFor(local)?.live?.find((b) => b.type === "activity")?.item;
  const auto = [acts.current, onSlide, actPanel.chosen, ids[0]].find((id) => id && items[id]);
  if (!actPanel.picked || !items[actPanel.chosen]) {
    if (auto !== actPanel.chosen) actPanel.seen = "";
    actPanel.chosen = auto;
  }
  if (pick.options.length !== ids.length) pick.innerHTML = ids.map((id) => `<option value="${esc(id)}">${esc(id)}</option>`).join("");
  pick.value = actPanel.chosen;
  const id = actPanel.chosen;
  const st = acts.items?.[id] || { phase: "ready", version: 0, count: 0, students: 0 };
  const checks = state?.checks || {};                     // who checks, and why the server cannot (host view)
  const want = `${id}:${st.version}:${JSON.stringify(actPanel.merging)}:${checks.mode}:${checks.failing?.[id] || ""}`;
  if (want === actPanel.seen || actPanel.loading) return;
  actPanel.loading = true;
  client.send({ t: "activity.view", activity: id }).then((r) => {
    if (!actPanel) return;
    actPanel.loading = false;
    if (actPanel.chosen !== id) return;
    actPanel.seen = want;
    drawActivityPanel(id, items[id], st, r.picture);
    renderActivities();                                   // (a newer version meanwhile)
  }, (err) => {
    if (actPanel) actPanel.loading = false;
    console.warn("texstage: activity", err);
  });
}

function drawActivityPanel(id, item, st, pic) {
  const crowd = item.input === "tuple";
  const A = T.presenter.activity, W = T.box;
  const words = codeWords(item, lang);                   // queries - or Turtle texts
  // who checks them, from the host view (the package 4 review: from activity.work, before its first
  // reply the panel said another window evaluates; and a pool that broke said nothing)
  const checks = state?.checks || { mode: "browser" };
  const failing = checks.failing?.[id];
  const note = crowd ? "" : checks.mode === "server" ? (failing ? A.serverFailed(words.many, failing) : A.server(words.many))
    : agent?.evaluator?.failed ? A.failed(words.many, agent.evaluator.failed)
      : agent?.leads() ? A.evaluates(words.many, agent.evaluator?.done ?? 0) : A.elsewhere(words.many);
  const counts = [W.students(st.students || 0), A.contributions(st.count || 0), st.waiting ? W.waiting(st.waiting) : "",
    st.unchecked ? W.unchecked(st.unchecked) : ""].filter(Boolean).map(esc).join(" · ");
  const head = `<div class="acthead"><b>${esc(textOf(A.phase, st.phase))}</b> · ${counts}
    <div class="buttons left">${st.phase === "open" ? `<button data-act="close">${esc(A.close)}</button>`
      : `<button data-act="open" class="primary">${esc(A.open)}</button>`}
      ${crowd ? "" : `<button data-act="reveal"${st.revealed ? " disabled" : ""}>${esc(st.revealed ? A.revealed : A.reveal)}</button>`}</div>
    ${note ? `<p class="note${failing && checks.mode === "server" ? " bad" : ""}">${esc(note)}</p>` : ""}</div>`;
  const body = crowd ? crowdPanel(item, st, pic) : clusterPanel(words, pic);
  actPanel.querySelector("#actbody").innerHTML = head + body;
}

function crowdPanel(item, st, pic) {
  const m = actPanel.merging;
  const terms = pic.terms || [];
  const A = T.presenter.activity;
  const row = (t) => {
    const into = t.into ? ` <span class="meta">→ ${esc(terms.find((o) => o.key === t.into && o.role === t.role)?.label || t.into)}</span>` : "";
    const acts = m ? (m.role === t.role && m.term !== t.key ? `<button data-act="into">${esc(A.into)}</button>` : "")
      : `${t.into ? `<button data-act="unmerge">${esc(A.unmerge)}</button>`
        : `<button data-act="merge" title="${esc(A.mergeTitle)}">${esc(A.merge)}</button>`}
        ${t.hidden ? `<button data-act="unhide">${esc(A.show)}</button>` : `<button data-act="hide">${esc(A.hide)}</button>`}
        ${item.review ? (t.approved ? `<button data-act="unapprove">${esc(A.unapprove)}</button>`
          : `<button data-act="approve" class="primary">${esc(A.approve)}</button>`) : ""}`;
    return `<div class="actterm${t.hidden ? " hidden" : ""}" data-role="${esc(t.role)}" data-term="${esc(t.key)}">
      <span class="n">${t.n}</span><span class="term">${esc(t.label)}${into}</span><span class="kind">${esc(t.role === "label" ? A.label : A.node)}</span>
      <span class="acts">${acts}</span></div>`;
  };
  return `<div class="buttons left"><label>${esc(A.from)} <input id="actmin" type="number" min="1" max="1000" value="${st.min ?? 1}">
      ${esc(A.on(st.min ?? 1))}</label></div>
    ${m ? `<p class="note">${A.mergeInto(`<b>${esc(m.term)}</b>`)}  <button data-act="cancel">${esc(T.dialog.cancel)}</button></p>` : ""}
    ${pic.more ? `<p class="note">${esc(A.moreNodes(pic.more))}</p>` : ""}
    ${terms.map(row).join("") || `<p class="empty">${esc(A.noTriples)}</p>`}`;
}

// A reference that ran, in the panel's words: the group of students that has its result - not its key
function refGroup(A, i, cluster) {
  return cluster ? A.refIn(i, cluster.n) : A.refAlone(i);
}

function clusterPanel(words, pic) {
  const A = T.presenter.activity;
  const refs = (pic.refs || []).map((r, i) => r === null ? A.refPending(i + 1)
    : typeof r === "object" ? A.refFailed(i + 1, r.failed) : refGroup(A, i + 1, pic.clusters.find((c) => c.key === r)));
  const shown = pic.shown?.key;
  return `${refs.length ? `<p class="note">${refs.map(esc).join("<br>")}</p>` : `<p class="note">${esc(A.noRef)}</p>`}
    ${pic.clusters.map((c) => `<div class="actcluster${c.reference ? " ref" : ""}${c.key === shown ? " shown" : ""}">
      <div class="top"><b>${esc(resultLabel(c, lang))}</b>${c.reference ? ` ✓ ${esc(A.theReference)}` : ""} · ${esc(T.box.students(c.n))}</div>
      <pre>${esc(c.example)}</pre>${c.errors?.length ? `<div class="meta">${c.errors.map(esc).join("<br>")}</div>` : ""}
      ${c.status === "ok" ? resultTable(c.summary, 4, lang) : ""}
      <div class="buttons left">${c.key === shown ? `<button data-act="unshow" class="on">${esc(A.unshow)}</button>`
        : `<button data-act="show" data-key="${esc(c.key)}" title="${esc(A.showTitle(words.one))}">${esc(A.show)}</button>`}
        <button data-act="hidec" data-contribution="${esc(c.contribution)}" title="${esc(A.hideOneTitle(words.one))}">${esc(A.hideOne(words.one))}</button>
        <button data-act="block" data-contribution="${esc(c.contribution)}">${esc(A.block)}</button></div></div>`).join("")
    || `<p class="empty">${esc(A.none(words.many))}</p>`}`;
}

function openGallery(quiz) {
  if (!quiz) return;
  const el = document.createElement("div");
  el.className = "overview gallery";
  el.innerHTML = `<div class="ovhead galhead"><span class="galtitle" id="galtitle"></span>
      <button class="primary" id="galshow"></button><button class="secondary" id="galhide">${esc(T.presenter.gallery.back)}</button>
      <button class="secondary" id="galclose">${esc(T.presenter.close)}</button></div>
    <div class="ovgrid galgrid" id="galgrid"></div>`;
  document.body.append(el);
  const shown = state.stage?.sketches;
  gallery = { quiz, el, sketches: [], round: null, cursor: 0, synced: null, loading: false,
    selected: shown?.quiz === quiz ? [...shown.players] : [] };
  el.querySelector("#galclose").onclick = closeGallery;
  el.querySelector("#galhide").onclick = () => send({ t: "sketch.show", quiz, players: [] });
  el.querySelector("#galshow").onclick = () => {
    if (gallery.selected.length) send({ t: "sketch.show", quiz, players: gallery.selected });
    closeGallery();
  };
  el.querySelector("#galgrid").addEventListener("click", (e) => {
    const b = e.target.closest("[data-player]");
    if (!b) return;
    const p = b.dataset.player;
    const at = gallery.selected.indexOf(p);
    if (at >= 0) gallery.selected.splice(at, 1);
    else if (gallery.selected.length < 12) gallery.selected.push(p);
    markGallery();
  });
  const q = deck.quizzes[quiz] || state.polls?.[quiz];
  const ask = q?.prompt?.text ? textHTML(q.prompt.text)
    : q?.prompt?.image ? `<img class="galimg" src="${esc(`${state.session.base}${q.prompt.image}`)}" alt="">` : esc(q?.title || quiz);
  el.querySelector("#galtitle").innerHTML = `${ask}<span class="meta" id="galcount"></span>`;
  markGallery();
  loadSketches();
}

function closeGallery() {
  gallery?.el.remove();
  gallery = null;
}

async function loadSketches() {
  // Stable submission cursors preserve gaps left by removed players. Each response
  // also names the remaining drawings so moderation removes already-loaded tiles.
  if (!gallery || gallery.loading) return;
  gallery.loading = true;
  const g = gallery;
  const requested = galleryState(g);
  let received = false;
  try {
    const r = await client.send({ t: "sketch.list", quiz: g.quiz, after: g.cursor, round: g.round });
    if (gallery !== g) return;
    if (r.round !== g.round) {
      g.sketches = [];
      if (g.round !== null) g.selected = [];
      g.el.querySelector("#galgrid").innerHTML = "";
    }
    g.round = r.round;
    g.cursor = r.cursor;
    const active = new Set(r.active);
    g.sketches = g.sketches.filter((x) => active.has(x.player));
    g.selected = g.selected.filter((p) => active.has(p));
    const grid = g.el.querySelector("#galgrid");
    grid.querySelectorAll("[data-player]").forEach((el) => { if (!active.has(el.dataset.player)) el.remove(); });
    const loaded = new Set(g.sketches.map((x) => x.player));
    for (const x of r.sketches) {
      if (loaded.has(x.player)) continue;
      g.sketches.push(x);
      grid.insertAdjacentHTML("beforeend", `<button class="tile sk" data-player="${esc(x.player)}">${sketchSVG(x.strokes, `#${x.n}`)}
        <span class="num">#${x.n}</span><span class="pick"></span></button>`);
    }
    g.synced = requested;
    received = true;
    markGallery();
  } catch (err) {
    console.warn("texstage: sketches", err);
  } finally {
    g.loading = false;
  }
  if (received && gallery === g) syncGallery();       // state may have advanced during the request
}

function galleryState(g) {
  const r = state.rounds?.[g.quiz];
  return JSON.stringify([r?.id, r?.answered, (state.players || []).map((p) => p.id).sort()]);
}

function syncGallery() {
  // Counts alone miss a removed player plus a new answer, or a new practice round.
  if (galleryState(gallery) !== gallery.synced) loadSketches();
}

function markGallery() {
  const g = gallery;
  g.el.querySelectorAll("[data-player]").forEach((b) => {
    const at = g.selected.indexOf(b.dataset.player);
    b.classList.toggle("on", at >= 0);
    b.querySelector(".pick").textContent = at >= 0 ? String(at + 1) : "";
  });
  g.el.querySelector("#galshow").textContent = T.presenter.gallery.show(g.selected.length);
  g.el.querySelector("#galshow").disabled = !g.selected.length;
  g.el.querySelector("#galcount").textContent = ` · ${T.presenter.gallery.count(g.sketches.length)}`;
}

// ------------------------------------------------------------------ recording (M5)
function renderRec() {
  // in the top bar - never on the projector -: Record, or while it runs a red dot, the time, the
  // microphone's level, pause and stop; when it ends, whether it was saved
  const el = $("#rec");
  const R = T.record;
  const open = Boolean(client && state?.session) && typeof auth === "string" && canRecord();
  const shape = rec ? `${rec.state}${rec.late ? " late" : ""}` : open ? "idle" : "";
  if (el.dataset.shape !== `${shape}:${lang}`) {            // (the deck page, another deck: another language)
    el.dataset.shape = `${shape}:${lang}`;
    el.className = `rec ${shape}`;
    const late = rec?.late ? `<span class="reclate" title="${esc(R.lateTitle)}">${esc(R.late)}</span>` : "";
    if (!rec) {
      el.innerHTML = open ? `<button id="recbtn" title="${esc(R.buttonTitle)}">● ${esc(R.button)}</button>` : "";
      if (open) $("#recbtn").onclick = recordDialog;
    } else if (rec.state === "recording" || rec.state === "paused") {
      const paused = rec.state === "paused";
      el.innerHTML = `<span class="recdot"></span><span class="rectime" id="rectime"></span>
        ${rec.mic ? `<span class="meter" title="${esc(R.meter)}"><i id="reclevel"></i></span>` : `<span class="nosound">${esc(R.noSound)}</span>`}${late}
        <button id="recpause" title="${esc(paused ? R.resumeTitle : R.pauseTitle)}">${paused ? `● ${esc(R.resume)}` : "❚❚"}</button>
        <button id="recstop" title="${esc(R.stopTitle)}">■</button>`;
      $("#recpause").onclick = () => (paused ? rec.resume() : rec.pause());
      $("#recstop").onclick = async () => { if (await ask(T.record.stopAsk, T.record.stop)) rec.stop(); };
    } else if (rec.state === "starting" || rec.state === "stopping") {
      el.innerHTML = `<span class="recdot"></span><span class="rectime" id="rectime"></span><span>${esc(R.saving)}</span>${late}`;
    } else {
      const saved = rec.state === "saved";
      el.innerHTML = `<span class="${saved ? "recsaved" : "recfail"}">${esc(saved ? R.saved : R.stopped(why(rec.error)))}</span>
        <button id="recok" title="${saved ? esc(R.savedTitle) : ""}">${esc(R.ok)}</button>`;
      const done = rec;
      $("#recok").onclick = () => { rec = null; renderRec(); };
      if (saved) setTimeout(() => { if (rec === done) { rec = null; renderRec(); } }, 30000);
    }
  }
  const running = Boolean(rec?.active);
  if (running && !recTicker) recTicker = setInterval(tickRec, 150);
  if (!running && recTicker) {
    clearInterval(recTicker);
    recTicker = null;
  }
  tickRec();
}

function tickRec() {
  const el = $("#rec");
  if (!rec) {
    el.title = "";
    return;
  }
  const time = $("#rectime");
  if (time) time.textContent = rec.state === "paused" ? T.record.paused(clock(rec.elapsed())) : clock(rec.elapsed());
  const level = $("#reclevel");
  if (level) level.style.width = `${Math.round((rec.state === "recording" ? rec.mic?.level() || 0 : 0) * 100)}%`;
  el.title = rec.take ? T.record.onServer(rec.file, decimal(rec.saved / 1e6)) : "";
}

async function recordDialog() {
  if (rec?.active || !state?.session) return;
  const mic = new Microphone();                   // made in the click: its level meter may run
  const R = T.record;
  const el = document.createElement("div");
  el.className = "dialog";
  el.innerHTML = `<div class="box"><h2>${esc(R.title)}</h2>
    <p>${esc(R.intro)}</p>
    <label class="microw">${esc(R.microphone)} <select id="micselect"></select></label>
    <div class="meter large"><i id="miclevel"></i></div><p id="micstate">${esc(R.asking)}</p>
    <p>${esc(R.screen)}</p>
    <div class="buttons"><button class="primary" id="recstart" disabled>${esc(R.start)}</button>
      <button class="secondary" id="closedlg">${esc(T.dialog.cancel)}</button></div></div>`;
  document.body.append(el);
  const select = el.querySelector("#micselect");
  const startButton = el.querySelector("#recstart");
  const say = (text, error = false) => { const p = el.querySelector("#micstate"); p.textContent = text; p.className = error ? "error" : ""; };
  const meter = setInterval(() => { el.querySelector("#miclevel").style.width = `${Math.round(mic.level() * 100)}%`; }, 100);
  let sound = false;
  let closed = false;
  let micRequest = 0;
  const starting = new AbortController();
  const close = (keep = false) => {
    if (closed) return;
    closed = true;
    micRequest++;
    starting.abort();
    clearInterval(meter);
    if (!keep) mic.close();
    el.remove();
  };
  const openMic = async (id) => {
    const request = ++micRequest;
    sound = false;
    if (id === "none") {
      mic.release();
      say(R.silent);
      return true;
    }
    try {
      const stream = await mic.open(id);
      if (closed || request !== micRequest || !stream) return false;
      sound = true;
      say(R.speak);
    } catch (err) {
      if (closed || request !== micRequest) return false;
      mic.release();
      if (id && err.name === "OverconstrainedError") return openMic("");      // that one is gone: the default
      say(R.noMic(err.name === "NotAllowedError" ? R.notAllowed : err.message || err.name), true);
    }
    return true;
  };
  const fill = async () => {
    // the microphones by name, once the browser allowed one; before, only the default
    const named = (await microphones()).map((d) => [d.deviceId, d.label]);
    if (closed) return;
    const options = [...(named.length ? named : [["", R.defaultMic]]), ["none", R.none]];
    select.innerHTML = options.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join("");
    const want = sound ? (named.some(([v]) => v === prefs.mic) ? prefs.mic : mic.deviceId) : "none";
    select.value = options.some(([v]) => v === want) ? want : options[0][0];
  };
  select.onchange = async () => {
    prefs.mic = select.value;
    savePrefs();
    startButton.disabled = true;                 // not before the microphone is there (or not)
    if (await openMic(select.value)) startButton.disabled = false;
  };
  el.querySelector("#closedlg").onclick = () => close();
  startButton.onclick = async () => {
    if (closed) return;
    const button = startButton;
    button.disabled = true;
    let screen;
    try {
      screen = await pickScreen();                // in the click, as the browser wants it
    } catch (err) {
      if (closed) return;
      button.disabled = false;
      return say(err.name === "NotAllowedError" ? R.noScreen : R.cannot(err.message || err.name), true);
    }
    if (closed || !state?.session) {
      screen.getTracks().forEach((t) => t.stop());
      return close();
    }
    const r = new Recording({ auth, session: state.session.id, screen, mic: sound ? mic : null, onChange: () => renderRec() });
    try {
      await r.start({ signal: starting.signal });
    } catch (err) {
      screen.getTracks().forEach((t) => t.stop());
      if (closed) return;
      button.disabled = false;
      return say(R.notStarted(why(err)), true);
    }
    rec = r;
    remember(r);
    close(sound);                                 // the recording has the microphone now
    renderRec();
  };
  if (!(await openMic(prefs.mic || ""))) return;
  await fill();
  if (closed) return;
  startButton.disabled = false;
}

function remembered() {
  try { return JSON.parse(sessionStorage.getItem(TAKES) || "[]"); } catch { return []; }
}

function remember(r) {
  try {
    sessionStorage.setItem(TAKES, JSON.stringify([...remembered(), { take: r.take, file: r.file }].slice(-20)));
  } catch { /* private mode */ }
}

async function listRecordings(box) {
  // those in this game's folder of the archive, and those this window made (each stays in the
  // folder of the game it started in)
  const found = new Map();
  try {
    for (const f of await (await hostFetch(`/api/archive/${state.session.id}/files`, auth)).json()) {
      if (f.take) found.set(f.take, { take: f.take, file: f.name, size: f.size, finished: !f.unfinished, remuxing: f.remuxing });
    }
  } catch { /* the game is over */ }
  for (const t of remembered()) {
    if (found.has(t.take)) continue;
    try {
      found.set(t.take, await (await hostFetch(`/api/recording/${t.take}`, auth)).json());
    } catch { /* not there any more */ }
  }
  if (!box.isConnected) return;
  const takes = [...found.values()];
  const R = T.record;
  box.innerHTML = takes.map((t) => {
    const here = rec?.take === t.take && rec.active;
    const what = here ? R.recording : !t.finished ? R.unfinished : t.remuxing ? R.finishing : "";
    const button = here || t.remuxing ? ""
      : !t.finished ? `<button data-finish="${esc(t.take)}" title="${esc(R.finishTitle)}">${esc(R.finish)}</button>`
        : `<button data-download="${esc(t.take)}">${esc(R.download)}</button>`;
    return `<div class="device"><span class="name">${esc(t.file)}</span><span class="meta">${esc(R.size(decimal(t.size / 1e6)))}${
      what ? ` · ${esc(what)}` : ""}${t.folder ? ` · ${esc(t.folder)}` : ""}</span>${button}</div>`;
  }).join("") || `<p class="empty">${esc(R.noTakes)}</p>`;
  box.querySelectorAll("[data-download]").forEach((b) => b.onclick = async () => {
    const r = await fetch(`/api/recording/${b.dataset.download}/download`, { method: "POST", headers: authHeaders(auth) });
    const info = await r.json().catch(() => ({}));
    if (!r.ok) return tell(why(refusal(r, info)));
    const a = document.createElement("a");        // the server sends it as a download: the page stays
    a.href = info.url;
    a.click();
  });
  box.querySelectorAll("[data-finish]").forEach((b) => b.onclick = async () => {
    await fetch(`/api/recording/${b.dataset.finish}/done`, { method: "POST", headers: authHeaders(auth) });
    listRecordings(box);
  });
  if (takes.some((t) => t.remuxing || (rec?.take === t.take && rec.active))) {
    setTimeout(() => { if (box.isConnected) listRecordings(box); }, 3000);
  }
}

// ------------------------------------------------------------------ after the lecture (M4)
function archiveDialog() {
  const el = document.createElement("div");
  const A = T.presenter.after;
  el.className = "dialog";
  el.innerHTML = `<div class="box"><h2>${esc(A.title)}</h2>
    <p>${esc(A.intro)}</p>
    <div class="buttons"><button class="primary" id="makepdf">${esc(A.make)}</button></div><p id="pdfstate"></p>
    <p>${esc(A.zipIntro)}</p>
    <div class="buttons"><button class="secondary" id="zip">${esc(A.zip)}</button></div>
    <h3>${esc(A.recordings)}</h3><div class="recordings" id="recordings"><p class="empty">...</p></div>
    <div class="buttons"><button class="secondary" id="closedlg">${esc(T.presenter.close)}</button></div></div>`;
  document.body.append(el);
  listRecordings(el.querySelector("#recordings"));
  const say = (text, error = false) => { const p = el.querySelector("#pdfstate"); p.textContent = text; p.className = error ? "error" : ""; };
  el.querySelector("#closedlg").onclick = () => el.remove();
  el.querySelector("#makepdf").onclick = async () => {
    const button = el.querySelector("#makepdf");
    button.disabled = true;
    try {
      say(A.collecting);
      const [stagePdf, ink] = await Promise.all([
        (await hostFetch(`/api/deck/${deck.bundle}/pdf`, auth)).arrayBuffer(),      // the browser has it already
        client.send({ t: "ink.all" })]);
      say(A.making);
      const bytes = await annotatedPdf(stagePdf, deck, state.stage?.boards || [], ink.frames);
      const day = new Date().toISOString().slice(0, 10);
      save(new Blob([bytes], { type: "application/pdf" }), `${deck.deck}-${day}-annotated.pdf`);
      say(A.keeping);
      const r = await fetch(`/api/archive/${state.session.id}/annotated.pdf`, { method: "PUT",
        headers: { ...authHeaders(auth), "Content-Type": "application/pdf" }, body: bytes });
      const kept = await r.json().catch(() => ({}));
      // (a refusal without its own code: the archive's - "The archive did not take it (...)")
      say(r.ok ? A.kept(kept.folder) : A.notKept(why({ code: kept.code || "archive", message: kept.error || String(r.status) })), !r.ok);
    } catch (err) {
      say(A.failed(why(err)), true);
    } finally {
      button.disabled = false;
    }
  };
  el.querySelector("#zip").onclick = async () => {
    const r = await hostFetch(`/api/archive/${state.session.id}.zip`, auth);
    save(await r.blob(), (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "archive.zip");
  };
}

// ------------------------------------------------------------------ keys
// PowerPoint's where it has them: arrows, PageUp/PageDown (clickers), Space, Enter, Home/End,
// a number and Enter, B or . black, W or , white, Ctrl+Z undo, Ctrl+Y redo; and F freeze,
// G overview, T timer, P pen, H highlighter, E eraser, L laser, Z zoom, N whiteboard page
// (Shift+N with a grid), Esc back step by step (number, overview, tool - not the zoom: in a
// full-screen window Esc also ends full screen; Z, the Zoom button or the label give it back);
// on a slide with a video K plays or pauses it and J goes 10 s back (video.js - Keynote's and
// YouTube's keys; their L, forward, is the laser here: the video's bar goes there)
function onKey(e) {
  const k = e.key;
  if (/^[0-9]$/.test(k)) {
    typed = (typed + k).slice(-4);
    render();
    return true;
  }
  if (typed && (k === "Enter" || k === "Backspace" || k === "Escape")) {
    if (k === "Enter") {
      const n = Number(typed);
      typed = "";
      jumpToFrame(n);
      closeOverview();
    } else {
      typed = k === "Backspace" ? typed.slice(0, -1) : "";
    }
    render();
    return true;
  }
  if (overview && overviewKey(k)) return true;
  if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(k)) move(1);
  else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(k)) move(-1);
  else if (k === "Home") go(items[0]);
  else if (k === "End") go(items[items.length - 1]);
  else if (k === "b" || k === "B" || k === ".") screen("black");
  else if (k === "w" || k === "W" || k === ",") screen("white");
  else if (k === "f" || k === "F") screen("freeze");
  else if (k === "g" || k === "G") toggleOverview();
  else if (k === "t" || k === "T") toggleTimer();
  else if (k === "p" || k === "P") setTool(tool === "pen" ? "auto" : "pen");
  else if (k === "h" || k === "H") setTool(tool === "highlighter" ? "auto" : "highlighter");
  else if (k === "e" || k === "E") setTool(tool === "eraser" ? "auto" : "eraser");
  else if (k === "l" || k === "L") setTool(tool === "pointer" ? "auto" : "pointer");
  else if (k === "z" || k === "Z") zoomKey();
  else if (k === "n") addBoard("blank");
  else if (k === "N") addBoard("grid");
  else if (k === "Escape") return escape();
  else return stage.typeKey(k);
  return true;
}

function escape() {
  if (overview) closeOverview();
  else if (gallery) closeGallery();
  else if (endOverlay()) return true;
  else if (tool !== "auto") setTool("auto");
  else return false;
  return true;
}

document.addEventListener("click", (e) => {           // a click elsewhere closes the top bar's "more"
  if (e.target.closest?.("#morebtn")) return;
  document.querySelector("#more")?.classList.remove("open");
  document.querySelector("#morebtn")?.setAttribute("aria-expanded", "false");
});

document.addEventListener("keydown", (e) => {
  if (!deck || !state || e.target.closest("input, textarea") || e.altKey || $(".dialog")) return;   // a dialog's keys
  if (e.ctrlKey || e.metaKey) {
    const k = e.key.toLowerCase();
    if (k === "z" && !e.shiftKey) inkAction("ink.undo");
    else if (k === "y" || (k === "z" && e.shiftKey)) inkAction("ink.redo");
    else return;
    e.preventDefault();
    return;
  }
  if (onKey(e)) e.preventDefault();
});

// Last, when every constant above has its value: with a stored key start() reaches showDecks()
// before its first pause, and a constant whose line has not run yet (folderList) would throw -
// which start() took for a refused key, and forgot the key.
start();
