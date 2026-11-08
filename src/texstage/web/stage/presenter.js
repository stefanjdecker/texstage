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
const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;                  // 1 quiz, 2 quizzes
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
const device = deviceId();
const prefs = loadPrefs();
const follow = new BroadcastChannel("texstage");   // the projector window follows when the deck changes

start();

function loadPrefs() {
  const base = { notes: "page", size: 22, pen: PENS[0], marker: MARKERS[0], width: "M", mic: "", poll: "choice", pollTime: 0,
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
  } catch {
    const removed = typeof auth === "object";
    forget();
    keyForm(removed ? "This device was removed in the presenter window - pair it again." : "This presenter key is not accepted.");
  }
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
  app.innerHTML = `<div class="page"><h1>Presenter key</h1>
    <p>The key is in the server's data folder (<code>presenter-key</code>) and is printed when it starts.</p>
    <form class="field" id="keyform"><input id="key" type="password" autocomplete="off" required>
    <button class="primary">Continue</button></form><div class="error">${esc(error)}</div>
    <p>An iPad or a second computer is paired instead: in texstage on the laptop, choose <b>Devices</b>, then
    <b>Pair a device</b>, and scan the code it shows.</p></div>`;
  $("#keyform").addEventListener("submit", async (e) => {
    e.preventDefault();
    auth = $("#key").value.trim();
    try {
      await showDecks();
      try { localStorage.setItem(KEY, auth); } catch { /* private mode */ }
    } catch {
      keyForm("This presenter key is not accepted.");
    }
  });
}

// ------------------------------------------------------------------ pairing this device (an iPad)
async function pairThisDevice(token) {
  const show = (html) => { app.innerHTML = `<div class="page"><h1>Pair this device</h1>${html}</div>`; };
  const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  const again = "<p>Make a new code in the presenter window on the laptop: Devices, Pair a device.</p>";
  show("<p>Asking the server ...</p>");
  let r;
  try {
    r = await post("/api/pair/claim", { token, name: deviceName() });
  } catch {
    return show(`<p class="error">The server cannot be reached.</p>${again}`);
  }
  if (!r.ok) return show(`<p class="error">${esc((await r.json().catch(() => ({}))).error || "This code does not work.")}</p>${again}`);
  const { claim, code } = await r.json();
  show(`<p>In the presenter window on the laptop, allow this device if it shows the same code:</p>
    <div class="paircode">${esc(code)}</div><p>Waiting for the laptop ...</p>`);
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
      return show(`<p class="error">${w.state === "denied" ? "The laptop did not allow this device." : "The code expired."}</p>${again}`);
    }
  }
}

function deviceName() {
  // what the lecturer sees in the list of devices, e.g. "iPad · Safari"
  const ua = navigator.userAgent;
  const what = /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) ? "iPad"
    : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows" : /Mac/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "a device";
  const browser = /EdgiOS|Edg\//.test(ua) ? "Edge" : /FxiOS|Firefox\//.test(ua) ? "Firefox" : /CriOS|Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : "a browser";
  return `${what} · ${browser}`;
}

// ------------------------------------------------------------------ devices (the laptop)
async function devicesDialog() {
  const el = document.createElement("div");
  el.className = "dialog";
  document.body.append(el);
  let poll = null;
  const close = () => { clearInterval(poll); el.remove(); };
  const list = async () => {
    clearInterval(poll);
    const devices = await (await hostFetch("/api/devices", auth)).json();
    const time = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    el.innerHTML = `<div class="box"><h2>Presenter devices</h2>
      <p>An iPad or a second computer runs this presenter window too: it steps through the slides, writes and points.</p>
      <div class="devices">${devices.map((d) => `<div class="device"><span class="name">${esc(d.name)}</span>
        <span class="meta">paired ${new Date(d.paired).toLocaleDateString()}${d.seen ? ` · seen ${time(d.seen)}` : ""}</span>
        <button data-remove="${esc(d.id)}">Remove</button></div>`).join("") || '<p class="empty">No device is paired.</p>'}</div>
      <div class="buttons"><button class="primary" id="pairnew">Pair a device</button><button class="secondary" id="closedlg">Close</button></div></div>`;
    el.querySelector("#closedlg").onclick = close;
    el.querySelector("#pairnew").onclick = pairNew;
    el.querySelectorAll("[data-remove]").forEach((b) => b.onclick = async () => {
      if (!(await ask("Remove this device? It stops presenting at once.", "Remove"))) return;
      await fetch(`/api/devices/${encodeURIComponent(b.dataset.remove)}`, { method: "DELETE", headers: authHeaders(auth) });
      list();
    });
  };
  const pairNew = async () => {
    const offer = await (await fetch("/api/pair", { method: "POST", headers: authHeaders(auth) })).json();
    el.innerHTML = `<div class="box"><h2>Pair a device</h2>
      <p>Scan this code with the iPad's camera, or open the address in its browser - valid for two minutes, and once.</p>
      <div class="qr">${offer.qr}</div><p class="url">${esc(offer.url)}</p><div id="claimed"></div>
      <div class="buttons"><button class="secondary" id="back">Back</button></div></div>`;
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
        box.innerHTML = `<p><b>${esc(s.name)}</b> wants to present. Allow it only if it shows this code:</p>
          <div class="paircode">${esc(s.code)}</div>
          <div class="buttons"><button class="primary" id="allow">Allow</button><button class="secondary" id="deny">Deny</button></div>`;
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
        box.innerHTML = '<p class="error">The code expired - pair again.</p>';
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
  for (const id of ["deckname", "pin", "join", "actions"]) $(`#${id}`).textContent = "";
  $("#status").className = "status";
  state = null;
  renderRec();
  library(decks, folders, uploaded);
}

// The deck page (server: library.py): folders, opened like a file browser with the path above, the
// decks in them, a search over all of them, by name or newest build first. A card's ⋯ renames,
// moves or deletes it; cards can also be dragged onto a folder or onto a step of the path. Delete
// deletes an uploaded deck; a build on this computer only leaves the list (its next build is back).
function library(decks, folders, uploaded = "") {
  let byId = new Map(folders.map((f) => [f.id, f]));
  const pathOf = (fid) => {                       // the folder and the folders it is in, from the top
    const out = [];
    for (let f = byId.get(fid); f && out.length < 64; f = byId.get(f.parent)) out.unshift(f);
    return out;
  };
  const within = (fid, root) => pathOf(fid).some((f) => f.id === root);    // root itself, or inside it
  const where = (fid) => pathOf(fid).map((f) => f.name).join(" › ") || "All decks";
  const byName = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
  const shown = (d) => d.label || d.name;
  let here = null;
  try { here = sessionStorage.getItem(FOLDER) || null; } catch { /* ignore */ }
  if (!byId.has(here)) here = null;
  let query = "";
  let dragged = null;
  const laptop = typeof auth === "string";        // the presenter key (a paired device uploads nothing)
  app.innerHTML = `<div class="page"><h1>Decks</h1>
    <p>The decks of this quiz server (<code>texstage present &lt;deck&gt;</code> builds one if needed and opens it
    here); a deck built now appears after a reload. Folders keep them in order: drag a deck onto a folder, or
    use its ⋯.${laptop ? " A deck this server does not have: upload its"
    + " <code>.bundle.zip</code> from the build folder, or drop it here." : ""}</p>
    ${laptop ? '<div class="uploadbar"><span id="upload"></span><span class="uploaded">' + esc(uploaded) + "</span></div>" : ""}
    <div class="libbar"><nav class="crumbs" aria-label="folder"></nav>
      <input type="search" class="libsearch" placeholder="Search all decks" aria-label="search all decks">
      <select class="libsort" aria-label="order"><option value="name">By name</option>
        <option value="newest">Newest first</option></select>
      <button class="secondary" id="newfolder">New folder</button></div>
    <div class="decks"></div></div>`;
  const list = app.querySelector(".decks");
  const crumbs = app.querySelector(".crumbs");
  const search = app.querySelector(".libsearch");
  const sort = app.querySelector(".libsort");
  sort.value = prefs.deckSort === "newest" ? "newest" : "name";

  const folderCard = (f) => {
    const subs = folders.filter((g) => g.parent === f.id).length;
    const parts = [subs ? count(subs, "folder", "folders") : "",
      count(decks.filter((d) => d.folder === f.id).length, "deck", "decks"), query ? `in ${esc(where(f.parent))}` : ""];
    return `<div class="deckcard folder" draggable="true" data-folder="${esc(f.id)}" tabindex="0">
      <span class="ficon" aria-hidden="true"></span>
      <div class="info"><div class="name">${esc(f.name)}</div><div class="meta">${parts.filter(Boolean).join(" · ")}</div></div>
      <button class="more" data-more-folder="${esc(f.id)}" title="rename, move or delete the folder" aria-label="folder actions">⋯</button></div>`;
  };
  const deckCard = (d) => `<div class="deckcard" draggable="true" data-deck="${esc(d.deck)}">
      <div class="info"><div class="name">${esc(shown(d))}</div>
      <div class="meta">${query && byId.has(d.folder) ? `in ${esc(where(d.folder))} · ` : ""}${d.label ? `${esc(d.name)} · ` : ""}${esc(d.deck)} · ${count(d.quizzes, "quiz", "quizzes")} · ${count(d.slides, "slide", "slides")} · built ${new Date(d.built).toLocaleString()}</div></div>
      ${d.game ? `<span class="tag open">game ${esc(d.game.pin)} · ${count(d.game.players, "player", "players")}</span>` : ""}
      ${d.stage ? `<button class="primary" data-present="${esc(d.bundle)}">Present</button>`
    : '<span class="tag" title="built without it (--no-stage, or before 2026-10-10 without --stage): build it again">no stage PDF</span>'}
      <button class="more" data-more-deck="${esc(d.bundle)}" title="rename, move or remove the deck" aria-label="deck actions">⋯</button></div>`;

  const render = () => {
    try { sessionStorage.setItem(FOLDER, here || ""); } catch { /* ignore */ }
    const q = query.trim().toLocaleLowerCase();
    crumbs.innerHTML = [`<button class="crumb${here ? "" : " here"}" data-to="">All decks</button>`,
      ...pathOf(here).map((f) => `<button class="crumb${f.id === here ? " here" : ""}" data-to="${esc(f.id)}">${esc(f.name)}</button>`)]
      .join('<span class="sep">›</span>');
    const hit = (...texts) => texts.some((t) => String(t || "").toLocaleLowerCase().includes(q));
    const fs = folders.filter((f) => (q ? hit(f.name) : (f.parent || null) === here)).sort((a, b) => byName(a.name, b.name));
    const ds = decks.filter((d) => (q ? hit(d.label, d.name, d.deck) : (byId.has(d.folder) ? d.folder : null) === here))
      .sort((a, b) => (sort.value === "newest" ? b.built - a.built : byName(shown(a), shown(b))));
    list.innerHTML = fs.map(folderCard).join("") + ds.map(deckCard).join("") || `<p class="empty">${q ? "No deck or folder matches."
      : here ? "This folder is empty - drag a deck onto it, or use a deck's ⋯ and Move to." : "No decks on this server yet."}</p>`;
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
    if (!r.ok) throw new Error(info.error || `the server answered ${r.status}`);
    return info;
  };
  const act = async (job, done = "") => {         // a change, then the page as the server has it now
    try {
      await job();
      if (done) notice(done);
    } catch (err) {
      await tell(`Not done: ${err.message || err}`);
    }
    await refresh();
  };
  const moveTo = (item, to) => act(() => (item.deck
    ? send("PATCH", `/api/decks/${encodeURIComponent(item.deck)}`, { folder: to })
    : send("PATCH", `/api/folders/${encodeURIComponent(item.folder)}`, { parent: to })), `Moved to ${to ? byId.get(to)?.name : "All decks"}`);
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
      <button data-to="" ${now === null ? "disabled" : ""}>All decks</button>
      ${rows.map(([f, depth]) => `<button data-to="${esc(f.id)}" style="padding-left:${12 + depth * 18}px" ${now === f.id ? "disabled" : ""}>${esc(f.name)}</button>`).join("")}
      </div><div class="buttons"><button class="secondary" data-cancel>Cancel</button></div></div>`;
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
    ["Rename …", async () => {
      const name = await askText(`The name of "${shown(d)}" on this page (empty: its own, "${d.name}")`, shown(d), "Rename");
      if (name !== null) act(() => send("PATCH", `/api/decks/${encodeURIComponent(d.deck)}`, { label: name.trim() === d.name ? "" : name }));
    }],
    ["Move to …", async () => {
      const to = await chooseFolder(`Move "${shown(d)}" to`, { deck: d.deck });
      if (to !== undefined) moveTo({ deck: d.deck }, to);
    }],
    [d.uploaded ? "Delete …" : "Remove from the list …", async () => {
      const question = d.uploaded
        ? `Delete "${shown(d)}" from this server? Its uploaded builds are deleted; the results of its games stay in the archive.`
        : `Remove "${shown(d)}" from the list? Its build folder stays on this computer - its next build brings it back.`;
      if (await ask(question, d.uploaded ? "Delete" : "Remove"))
        act(() => send("DELETE", `/api/decks/${encodeURIComponent(d.deck)}`), `${shown(d)}: ${d.uploaded ? "deleted" : "off the list"}`);
    }]]);
  const folderMenu = (button, f) => menu(button, [
    ["Rename …", async () => {
      const name = await askText("The folder's name", f.name, "Rename");
      if (name !== null) act(() => send("PATCH", `/api/folders/${encodeURIComponent(f.id)}`, { name }));
    }],
    ["Move to …", async () => {
      const to = await chooseFolder(`Move the folder "${f.name}" to`, { folder: f.id });
      if (to !== undefined) moveTo({ folder: f.id }, to);
    }],
    ["Delete …", async () => {
      if (await ask(`Delete the folder "${f.name}"? What it holds moves up one level - no deck is deleted.`, "Delete"))
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
    const name = await askText(here ? `A new folder in "${byId.get(here)?.name}"` : "A new folder", "", "Create");
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
  app.innerHTML = `<div class="page"><p>Loading ${esc(d.name)} ...</p></div>`;
  try {
    deck = await (await hostFetch(`/api/deck/${d.bundle}`, auth)).json();
    pdf?.close();
    pdf = await PdfDeck.open(deck.bundle, auth);
  } catch (err) {
    app.innerHTML = `<div class="page"><h1>${esc(d.name)}</h1><p class="error">${esc(err.message || err)}</p>
      <p><button class="secondary" id="back">Decks</button></p></div>`;
    $("#back").onclick = () => showDecks();
    return;
  }
  try { sessionStorage.setItem(LAST, d.bundle); } catch { /* ignore */ }
  frames = framesOf(deck);
  items = sequence(deck, []);
  aspect = deck.pdf.width / deck.pdf.height;
  document.documentElement.style.setProperty("--tq-aspect", String(aspect));
  $("#deckname").textContent = deck.name;
  const laptop = typeof auth === "string";        // the presenter key: the projector and the devices are here
  $("#actions").innerHTML = `${laptop ? `<button id="projector" title="open the projector window (on the second screen)">Projector</button>
    <button id="devices" title="an iPad or a second computer as presenter">Devices</button>` : ""}
    <button id="archive" title="the annotated PDF for the students, the lecture's archive">After the lecture</button>
    <button id="csv">Results (CSV)</button><button id="newgame">New game</button><button id="decks">Decks</button>`;
  app.innerHTML = `<div class="pgrid">
    <section class="current"><div class="fitbox" id="currentbox"><div id="stage"></div><button class="onscreen" id="onscreen" hidden></button></div></section>
    <div class="split main" role="separator" tabindex="0" aria-label="room for the slide and for the notes"
      title="drag: more room for the slide or for the notes (double click: as it was)"></div>
    <section class="side">
      <div class="label">Next <span id="nextinfo"></span></div>
      <div class="nextwrap"><div class="pagebox" id="nextbox"></div></div>
      <div class="split next" role="separator" tabindex="0" aria-orientation="horizontal"
        aria-label="room for the next slide and for the notes"
        title="drag: more room for the next slide or for the notes (double click: as it was)"></div>
      <div class="label">Notes <span class="tools"><button id="notesmode"></button>
        <button id="smaller" title="smaller text">A−</button><button id="larger" title="larger text">A+</button></span></div>
      <div class="notes" id="notes"><div class="notewrap" id="notewrap"><div class="pagebox" id="notebox"></div></div>
        <div class="notetext" id="notetext"></div></div>
    </section>
    <footer class="toolbar" id="toolbar">
      <span class="group"><button data-tool="auto" title="navigate - a pen draws all the same (Esc)">↖</button>
        <button data-tool="pen" title="pen (P)">✎ Pen</button><button data-tool="highlighter" title="highlighter (H)">▮ Marker</button>
        <button data-tool="eraser" title="eraser (E) - also the pen's eraser end">⌫ Eraser</button>
        <button data-tool="pointer" title="laser pointer (L)">● Laser</button>
        <button data-tool="zoom" title="zoom: drag a box over the slide (Z) - zoomed: the whole slide again">⌕ Zoom</button></span>
      <span class="group" id="swatches"></span><span class="group" id="sizes"></span>
      <span class="group"><button id="undo" title="undo (Ctrl+Z)">↶</button><button id="redo" title="redo (Ctrl+Y)">↷</button>
        <button id="clear" title="erase all ink of this frame">Clear</button></span>
      <span class="group"><button id="blank" title="a whiteboard page after this frame (N)">＋ Whiteboard</button>
        <button id="gridpage" title="a whiteboard page with a grid (Shift+N)">＋ Grid</button></span>
      <span class="group"><button id="pollbtn" title="ask a question now: yes/no, A-D, a scale, a word cloud, text or a sketch">▤ Poll</button>
        <button id="qabtn" title="questions from the audience">？ Q&amp;A <span class="badge" id="qacount" hidden></span></button>
        <button id="sketchbtn" title="the drawings of this sketch question" hidden>✎ Sketches <span class="badge" id="sketchcount"></span></button>
        <button id="actbtn" title="the deck's live activities: open, close, reveal, moderate" hidden>◎ Activities <span class="badge" id="actcount" hidden></span></button></span>
    </footer>
    <footer class="bar">
      <div class="clock"><button id="timer" title="start / pause the timer (T)"></button><span class="elapsed" id="elapsed">0:00</span>
        <span class="target" id="target"></span><button id="reset" title="reset the timer">↺</button>
        <button id="settarget" title="a target duration">⏱</button><span class="wall" id="wall"></span></div>
      <div class="nav"><button id="prev" title="previous step (←, PageUp)">◀</button><span class="where" id="where"></span>
        <button id="next" title="next step (→, PageDown, Space)">▶</button></div>
      <div class="screens"><button data-screen="black" title="black projector (B)">Black</button>
        <button data-screen="white" title="white projector (W)">White</button>
        <button data-screen="freeze" title="the projector keeps this slide while you go on (F)">Freeze</button>
        <button id="overview" title="all frames (G)">Overview</button></div>
    </footer></div>`;
  client?.close();
  client = new Client({
    onStatus: (s) => {
      $("#status").className = `status ${s}`;
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
    onBye: (m) => {
      client.close();
      if (m.reason === "removed") {                // a device removed in the presenter window
        forget();
        keyForm(m.message || "This device was removed.");
      } else {
        showDecks().catch(() => keyForm());
      }
    },
  });
  book = new InkBook(client);
  agent?.destroy();
  agent = deck.items?.activity ? new ActivityAgent({ send: (msg) => client.send(msg) }) : null;
  if (agent && Object.values(deck.items.activity).some((a) => a.input === "code")) {
    // the queries are evaluated here while this window has the lease (evaluator.js)
    const evaluator = new Evaluator({ send: (msg) => client.send(msg), base: `/bundle/${deck.bundle}/` });
    agent.evaluator = evaluator;
    agent.jobs = (work) => evaluator.take(work).then((any) => { if (any) setTimeout(() => agent?.renew(), 50); });
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
      notice(e.data.click === "sound" ? "The projector plays the video without sound - click into the projector window once."
        : "The projector waits for a click to play the video - click into the projector window once.");
    }
  };
  follow.postMessage({ type: "deck", bundle: deck.bundle });     // an open projector window: this deck now
  $("#prev").onclick = () => move(-1);
  $("#next").onclick = () => move(1);
  $("#timer").onclick = toggleTimer;
  $("#reset").onclick = async () => { if (await ask("Reset the timer to 0:00?", "Reset")) send({ t: "timer", action: "reset" }); };
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
    if (!(await ask("Start a new game? The players join again with a new PIN.", "New game"))) return;
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
  const welcome = await client.login({ t: "hello", role: "stage", ...credentials, deck: deck.deck, bundle: deck.bundle });
  clearInterval(pinger);
  pinger = setInterval(ping, 5000);
  ping();
  if (chosen && welcome?.earlier && !welcome.presenters) await newOrContinued(welcome.earlier);
}

async function newOrContinued(e) {
  // the deck's ink and whiteboard pages from before: a new presentation leaves them to the lecture
  // they belong to (in the archive), a continuation goes on with them (docs/texstage-design.md, 24)
  const what = [e.frames ? `ink on ${count(e.frames, "frame", "frames")}` : "",
    e.boards ? count(e.boards, "whiteboard page", "whiteboard pages") : ""].filter(Boolean).join(" and ");
  const fresh = await ask(`The lecture of ${lectureTime(e.at)} left ${what}. Is this a new presentation, or does it `
    + `continue that lecture?${e.open ? " A new presentation also starts a new game: the phones join with a new PIN." : ""}`,
  "New presentation", "Continue that lecture");
  let r = null;
  if (fresh && e.open) r = await client.send({ t: "lecture.new" }).catch(alertError);
  else if (!fresh && !e.open) r = await client.send({ t: "lecture.continue", game: e.game }).catch(alertError);
  if (r) inkAnew();
}

function lectureTime(ms) {
  const d = new Date(ms);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === new Date().toDateString()) return `today, ${time}`;
  return `${d.toLocaleDateString("en-GB", { day: "numeric", month: "long" })}, ${time}`;
}

function inkAnew() {
  book.reset();
  ink?.reload();
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
  if (err?.code !== "no-round") tell(err?.message || String(err));
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
  $("#pin").textContent = `PIN ${s.pin.slice(0, 3)} ${s.pin.slice(3)}`;
  $("#join").textContent = `${count(s.players, "player", "players")} · ${s.join.replace(/\?pin=.*/, "")}`;   // cut short from the end
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
  $("#nextinfo").textContent = !after ? "· the end"
    : after.board ? "· a whiteboard page" : `· frame ${after.frame}${after.phase ? ` · ${after.phase}` : ""}`;
  if (typed) {
    $("#where").textContent = `frame ${typed}_ (Enter)`;
  } else if (overlay) {
    $("#where").textContent = `${overlay.overlay === "poll" ? "a poll" : "sketches"} on the projector - Esc or → : back to the slide`;
  } else if (current.board) {
    $("#where").textContent = `whiteboard page after frame ${current.after}`;
  } else {
    const steps = new Set(deck.slides.filter((s) => s.frame === current.frame).map((s) => s.step)).size;
    const live = current.phase ? ` · ${current.phase}${current.quiz ? ` ${current.quiz}` : ""}` : "";
    $("#where").textContent = `frame ${current.frame} / ${frames.length}${steps > 1 ? ` · step ${current.step} / ${steps}` : ""}${live}`;
  }
  // the notes: the deck's note page, or its text
  const text = prefs.notes === "text";
  $("#notesmode").textContent = text ? "Page" : "Text";
  $("#notesmode").title = text ? "the note page as typeset" : "the notes as text you can enlarge";
  $("#notewrap").hidden = text;
  $("#notetext").hidden = !text;
  note.show(text || current.board ? null : current);
  if (text) {
    const paragraphs = (current.notes || "").split("\n").filter(Boolean);
    $("#notetext").style.fontSize = `${prefs.size}px`;
    $("#notetext").innerHTML = paragraphs.map((p) => `<p>${esc(p)}</p>`).join("")
      || `<p class="empty">${current.board ? "A whiteboard page." : "No notes."}</p>`;
  } else if (current.board || !current.note) {
    $("#notewrap").dataset.empty = current.board ? "A whiteboard page." : "No note page for this slide.";
  } else {
    delete $("#notewrap").dataset.empty;
  }
  // what the projector shows, if not just this
  const shown = shownSlide(deck, state);
  const frozen = shown?.overlay ? `a ${shown.overlay === "poll" ? "poll" : "sketch board"}`
    : shown?.board ? "a whiteboard page" : `frame ${shown ? shown.frame : "?"}`;
  // (zoomed: a tap on it, Z or the Zoom button give the whole slide back - not Esc: in a
  // full-screen window Esc ends full screen, and an iPad has none)
  const zoomed = Boolean(view) && !["black", "white", "freeze"].includes(st.screen);
  const away = st.screen === "black" ? "black" : st.screen === "white" ? "white"
    : st.screen === "freeze" ? `frozen on ${frozen}` : zoomed ? `zoomed ×${(1 / view.h).toFixed(1)} - ⤢ tap: the whole slide` : "";
  $("#onscreen").textContent = away ? `Projector: ${away}` : "";
  $("#onscreen").hidden = !away;
  $("#onscreen").disabled = !zoomed;
  $('[data-tool="zoom"]').classList.toggle("zoomed", Boolean(view));
  app.querySelectorAll("[data-screen]").forEach((b) => b.classList.toggle("on", b.dataset.screen === st.screen));
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

function go(item) {
  const id = idOf(item);
  local = pending = id;
  render();
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
  app.querySelectorAll("[data-tool]").forEach((b) => b.classList.toggle("on", b.dataset.tool === tool));
  const marker = tool === "highlighter";
  const colors = marker ? MARKERS : PENS;
  const chosen = marker ? prefs.marker : prefs.pen;
  $("#swatches").innerHTML = colors.map((c) => `<button class="swatch${c === chosen ? " on" : ""}" data-color="${c}"
    style="--c:${c}" title="${marker ? "highlighter" : "pen"} colour"></button>`).join("");
  $("#swatches").querySelectorAll("[data-color]").forEach((b) => b.onclick = () => {
    prefs[marker ? "marker" : "pen"] = b.dataset.color;
    savePrefs();
    if (tool === "auto" || tool === "eraser" || tool === "pointer" || tool === "zoom") setTool(marker ? "highlighter" : "pen");
    else renderTools();
  });
  $("#sizes").innerHTML = Object.keys(SIZES).map((s) => `<button class="size${s === prefs.width ? " on" : ""}"
    data-size="${s}" title="pen width">${s}</button>`).join("");
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
  if (t === "ink.clear" && r?.event) notice("All ink of this frame erased - ↶ or Ctrl+Z brings it back");   // no question
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
  const answer = await askText("Target duration in minutes (empty: none)", now);
  if (answer === null) return;
  const minutes = Number(answer.replace(",", "."));
  if (answer.trim() && !(minutes > 0)) return tell("A number of minutes, please.");
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
    target.textContent = left >= 0 ? `${clock(left)} left` : `${clock(-left)} over`;
    target.className = `target ${left < 0 ? "over" : left < 5 * 60000 ? "soon" : ""}`;
  } else {
    target.textContent = "";
  }
  $("#wall").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
    if (it.board) tiles.push({ item: it, go: it, label: "page", key: idOf(it) });
    else if (!after || after.board || after.frame !== it.frame) {
      tiles.push({ item: it, go: frames.find((f) => f.frame === it.frame).first, label: String(it.frame), key: String(it.frame) });
    }
  });
  const el = document.createElement("div");
  el.className = "overview";
  el.innerHTML = `<div class="ovhead">Frames and whiteboard pages - click one, or type a frame's number and Enter; G or Esc closes</div>
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

function closeOverview() {
  overview?.el.remove();
  overview = null;
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
    tell("The browser blocked the projector window - allow pop-ups for this page.");
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
const KINDS = [["yesno", "Yes / No"], ["choice", "A – F"], ["scale", "Scale 1–5"], ["words", "Word cloud"],
  ["text", "Text"], ["sketch", "Sketch"]];
const KIND_NOTES = {
  yesno: "The phones answer Yes or No.",
  scale: "The phones pick 1 to 5 - say in the question what 1 and 5 mean.",
  words: "The phones type a word or two (24 characters); the projector shows a word cloud.",
  text: "The phones type an answer (140 characters); the projector lists them.",
  sketch: "The phones draw; Sketches shows the drawings, and you pick some for the projector.",
};
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
  el.innerHTML = `<div class="box wide"><h2>Ask a poll</h2>
    <div class="kinds">${KINDS.map(([k, label]) => `<button data-kind="${k}">${label}</button>`).join("")}</div>
    <label class="col">Question <textarea id="pollprompt" rows="3" maxlength="300"
      placeholder="Type the question - formulas between $...$ (yes/no, A-F and the scale can do without: the slide asks)"></textarea></label>
    <div class="preview" id="pollpreview" hidden></div>
    <div id="pollanswers"></div>
    <div class="buttons"><label>Time <select id="polltime">${TIMES.map((t) => `<option value="${t}">${t} s</option>`).join("")}</select></label>
      <span class="spacer"></span><button class="primary" id="pollstart">Ask now</button>
      <button class="secondary" id="closedlg">Cancel</button></div>
    <p class="error" id="pollerr"></p>
    ${asked.length ? `<h3>Asked in this game</h3><div class="pollhist">${asked.map(([quiz, q]) => `<div class="device">
      <span class="name">${esc(KINDS.find(([k]) => k === q.adhoc)?.[1] || q.adhoc)}</span>
      <span class="meta">${esc((q.prompt?.text || "").slice(0, 60)) || "(the slide's question)"} · ${count(state.rounds?.[quiz]?.answered ?? 0, "answer", "answers")}</span>
      <button data-show="${esc(quiz)}">Show</button></div>`).join("")}</div>` : ""}</div>`;
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
      box.innerHTML = `<p>${esc(KIND_NOTES[kind])}</p>`;
      return;
    }
    box.innerHTML = `<div class="buttons left">Answers ${[2, 3, 4, 5, 6].map((n) => `<button class="count${n === choices ? " on" : ""}"
        data-count="${n}">${n}</button>`).join("")}<label class="check"><input type="checkbox" id="pollmulti"> several answers</label></div>
      <div class="answerlist">${texts.slice(0, choices).map((t, i) => `<label><b>${String.fromCharCode(65 + i)}</b>
        <input data-answer="${i}" maxlength="120" value="${esc(t)}" placeholder="optional - the letter alone, if the slide has the answers"></label>`).join("")}</div>`;
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
      el.querySelector("#pollerr").textContent = err.message || err;
    }
  };
  pick(kind);
  prompt.focus();
}

function openQa() {
  qaPanel = document.createElement("aside");
  qaPanel.className = "qapanel";
  qaPanel.innerHTML = `<div class="qahead"><h2>Questions</h2>
      <label class="check" title="the phones get a tab to ask and upvote"><input type="checkbox" id="qaopen"> open for the phones</label>
      <button class="secondary" id="qaclose" title="close the panel">✕</button></div>
    <div class="qabody" id="qabody"></div>`;
  document.body.append(qaPanel);
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
      if (await ask("Delete this question?", "Delete")) send({ t: "qa.mark", question, state: "deleted" });
    } else if (act === "block") {
      if (await ask("Block whoever asked this? Their question and their other open questions go, and they cannot "
        + "ask any more in this game.", "Block")) send({ t: "qa.block", question });
    }
  });
  qaPanel.listed = "";
  renderQa();
}

function closeQa() {
  qaPanel?.remove();
  qaPanel = null;
}

function renderQa() {
  // open questions by votes, with what the lecturer can do; the answered ones below
  const qa = state?.qa || { open: false, questions: [] };
  qaPanel.querySelector("#qaopen").checked = qa.open;
  const shown = state.stage?.question?.id || null;
  const key = JSON.stringify([qa, shown]);
  if (key === qaPanel.listed) return;
  qaPanel.listed = key;
  const item = (q) => `<div class="qaitem${q.id === shown ? " shown" : ""}${q.state === "done" ? " done" : ""}" data-q="${esc(q.id)}">
      <div class="qavotes">▲ ${q.votes}</div><div class="qatext">${textHTML(q.text, () => {
        if (qaPanel) {
          qaPanel.listed = "";                     // KaTeX came: the formulas typeset
          renderQa();
        }
      })}</div>
      <div class="qaacts">${q.state === "done" ? '<button data-act="open">Reopen</button>'
        : `${q.id === shown ? '<button data-act="hide" class="on">Hide</button>' : '<button data-act="show" title="on the projector, over the slide">Show</button>'}
        <button data-act="done">Done</button>`}<button data-act="delete">Delete</button>
        <button data-act="block" title="whoever asked it cannot ask any more">Block</button></div></div>`;
  const open = qa.questions.filter((q) => q.state === "open");
  const done = qa.questions.filter((q) => q.state === "done");
  qaPanel.querySelector("#qabody").innerHTML = `${open.map(item).join("")
    || `<p class="empty">${qa.open ? "No questions yet." : "Questions are closed - open them, and the phones get a tab for them."}</p>`}
    ${done.length ? `<h3>Answered</h3>${done.map(item).join("")}` : ""}`;
}

// ------------------------------------------------------------------ live activities (activity.js)
function openActivities() {
  actPanel = document.createElement("aside");
  actPanel.className = "qapanel actpanel";
  actPanel.innerHTML = `<div class="qahead"><h2>Activities</h2><select id="actpick"></select>
      <button class="secondary" id="actclose" title="close the panel">✕</button></div>
    <div class="qabody" id="actbody"></div>`;
  document.body.append(actPanel);
  actPanel.chosen = null;               // the activity shown here (the current one by default)
  actPanel.merging = null;              // a term on its way into another: {role, term}
  actPanel.seen = "";
  actPanel.querySelector("#actclose").onclick = closeActivities;
  actPanel.querySelector("#actpick").onchange = (e) => { actPanel.chosen = e.target.value; actPanel.seen = ""; renderActivities(); };
  actPanel.querySelector("#actbody").addEventListener("click", onActivityClick);
  actPanel.querySelector("#actbody").addEventListener("change", (e) => {
    if (e.target.id === "actmin") send({ t: "activity.min", activity: actPanel.chosen, min: Number(e.target.value) || 1 });
  });
  renderActivities();
}

function closeActivities() {
  actPanel?.remove();
  actPanel = null;
}

async function onActivityClick(e) {
  const b = e.target.closest("button[data-act]");
  if (!b || !actPanel) return;
  const activity = actPanel.chosen;
  const act = b.dataset.act;
  const term = b.closest("[data-term]")?.dataset;
  if (act === "open" || act === "close") send({ t: `activity.${act}`, activity });
  else if (act === "reveal") {
    if (await ask("Reveal the reference's result - in every window, and on the phones whether theirs is the same?", "Reveal")) {
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
    if (await ask("Block whoever sent this? Their contributions go, and they cannot send any more in this game.", "Block")) {
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
  if (!actPanel.chosen || !items[actPanel.chosen]) actPanel.chosen = acts.current && items[acts.current] ? acts.current : ids[0];
  if (pick.options.length !== ids.length) pick.innerHTML = ids.map((id) => `<option value="${esc(id)}">${esc(id)}</option>`).join("");
  pick.value = actPanel.chosen;
  const id = actPanel.chosen;
  const st = acts.items?.[id] || { phase: "ready", version: 0, count: 0, students: 0 };
  const want = `${id}:${st.version}:${JSON.stringify(actPanel.merging)}`;      // (not the layout: no positions here)
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
  const words = codeWords(item);                         // queries - or Turtle texts
  const phase = { ready: "not opened yet", open: "open - the phones send", closed: "closed" }[st.phase] || st.phase;
  const head = `<div class="acthead"><b>${esc(phase)}</b> · ${count(st.students || 0, "student", "students")} ·
      ${count(st.count || 0, "contribution", "contributions")}${st.waiting ? ` · ${st.waiting} waiting` : ""}
    <div class="buttons left">${st.phase === "open" ? '<button data-act="close">Close</button>'
      : '<button data-act="open" class="primary">Open</button>'}
      ${crowd ? "" : `<button data-act="reveal"${st.revealed ? " disabled" : ""}>${st.revealed ? "Revealed" : "Reveal"}</button>`}</div>
    ${crowd ? "" : `<p class="note">${agent?.evaluator?.failed ? `The ${words.many} cannot be evaluated here: ${esc(agent.evaluator.failed)}`
      : agent?.leads() ? `This window evaluates the ${words.many} (${agent.evaluator?.done ?? 0} so far).`
        : `Another presenter window evaluates the ${words.many} - or none: they wait.`}</p>`}</div>`;
  const body = crowd ? crowdPanel(item, st, pic) : clusterPanel(words, pic);
  actPanel.querySelector("#actbody").innerHTML = head + body;
}

function crowdPanel(item, st, pic) {
  const m = actPanel.merging;
  const terms = pic.terms || [];
  const row = (t) => {
    const into = t.into ? ` <span class="meta">→ ${esc(terms.find((o) => o.key === t.into && o.role === t.role)?.label || t.into)}</span>` : "";
    const acts = m ? (m.role === t.role && m.term !== t.key ? '<button data-act="into">← into this</button>' : "")
      : `${t.into ? '<button data-act="unmerge">Unmerge</button>' : '<button data-act="merge" title="merge it into another term">Merge…</button>'}
        ${t.hidden ? '<button data-act="unhide">Show</button>' : '<button data-act="hide">Hide</button>'}
        ${item.review ? (t.approved ? '<button data-act="unapprove">Unapprove</button>' : '<button data-act="approve" class="primary">Approve</button>') : ""}`;
    return `<div class="actterm${t.hidden ? " hidden" : ""}" data-role="${esc(t.role)}" data-term="${esc(t.key)}">
      <span class="n">${t.n}</span><span class="term">${esc(t.label)}${into}</span><span class="kind">${t.role === "label" ? "label" : "node"}</span>
      <span class="acts">${acts}</span></div>`;
  };
  return `<div class="buttons left"><label>On the projector from <input id="actmin" type="number" min="1" max="1000" value="${st.min ?? 1}">
      ${(st.min ?? 1) === 1 ? "student" : "students"} on</label></div>
    ${m ? `<p class="note">Merge <b>${esc(m.term)}</b> into …  <button data-act="cancel">Cancel</button></p>` : ""}
    ${pic.more ? `<p class="note">${pic.more} more nodes than the projector shows.</p>` : ""}
    ${terms.map(row).join("") || '<p class="empty">No triples yet.</p>'}`;
}

function clusterPanel(words, pic) {
  const refs = (pic.refs || []).map((r, i) => r === null ? `reference ${i + 1}: not run yet`
    : typeof r === "object" ? `reference ${i + 1} failed: ${r.failed}` : `reference ${i + 1}: ${r}`);
  const shown = pic.shown?.key;
  return `${refs.length ? `<p class="note">${refs.map(esc).join("<br>")}</p>` : '<p class="note">The deck gives no reference.</p>'}
    ${pic.clusters.map((c) => `<div class="actcluster${c.reference ? " ref" : ""}${c.key === shown ? " shown" : ""}">
      <div class="top"><b>${esc(resultLabel(c))}</b>${c.reference ? " ✓ the reference's" : ""} · ${count(c.n, "student", "students")}</div>
      <pre>${esc(c.example)}</pre>${c.errors?.length ? `<div class="meta">${c.errors.map(esc).join("<br>")}</div>` : ""}
      ${c.status === "ok" ? resultTable(c.summary, 4) : ""}
      <div class="buttons left">${c.key === shown ? '<button data-act="unshow" class="on">Hide from the projector</button>'
        : `<button data-act="show" data-key="${esc(c.key)}" title="its ${words.one} and result on the projector">Show</button>`}
        <button data-act="hidec" data-contribution="${esc(c.contribution)}" title="this ${words.one} goes - the others of its cluster stay">Hide this ${words.one}</button>
        <button data-act="block" data-contribution="${esc(c.contribution)}">Block</button></div></div>`).join("")
    || `<p class="empty">No ${words.many} yet.</p>`}`;
}

function openGallery(quiz) {
  if (!quiz) return;
  const el = document.createElement("div");
  el.className = "overview gallery";
  el.innerHTML = `<div class="ovhead galhead"><span class="galtitle" id="galtitle"></span>
      <button class="primary" id="galshow"></button><button class="secondary" id="galhide">Back to the slide</button>
      <button class="secondary" id="galclose">Close</button></div>
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
  g.el.querySelector("#galshow").textContent = `Show on the projector (${g.selected.length})`;
  g.el.querySelector("#galshow").disabled = !g.selected.length;
  g.el.querySelector("#galcount").textContent = ` · ${count(g.sketches.length, "sketch", "sketches")} - pick up to 12`;
}

// ------------------------------------------------------------------ recording (M5)
function renderRec() {
  // in the top bar - never on the projector -: Record, or while it runs a red dot, the time, the
  // microphone's level, pause and stop; when it ends, whether it was saved
  const el = $("#rec");
  const open = Boolean(client && state?.session) && typeof auth === "string" && canRecord();
  const shape = rec ? `${rec.state}${rec.late ? " late" : ""}` : open ? "idle" : "";
  if (el.dataset.shape !== shape) {
    el.dataset.shape = shape;
    el.className = `rec ${shape}`;
    const late = rec?.late ? '<span class="reclate" title="the network or the server does not take the parts yet - they wait here">saving delayed</span>' : "";
    if (!rec) {
      el.innerHTML = open ? '<button id="recbtn" title="record what the projector shows, with your voice">● Record</button>' : "";
      if (open) $("#recbtn").onclick = recordDialog;
    } else if (rec.state === "recording" || rec.state === "paused") {
      const paused = rec.state === "paused";
      el.innerHTML = `<span class="recdot"></span><span class="rectime" id="rectime"></span>
        ${rec.mic ? '<span class="meter" title="the microphone"><i id="reclevel"></i></span>' : '<span class="nosound">no sound</span>'}${late}
        <button id="recpause" title="${paused ? "go on recording" : "pause the recording"}">${paused ? "● Resume" : "❚❚"}</button>
        <button id="recstop" title="stop the recording">■</button>`;
      $("#recpause").onclick = () => (paused ? rec.resume() : rec.pause());
      $("#recstop").onclick = async () => { if (await ask("Stop the recording? Recording again makes a new file.", "Stop")) rec.stop(); };
    } else if (rec.state === "starting" || rec.state === "stopping") {
      el.innerHTML = `<span class="recdot"></span><span class="rectime" id="rectime"></span><span>saving ...</span>${late}`;
    } else {
      const saved = rec.state === "saved";
      el.innerHTML = `<span class="${saved ? "recsaved" : "recfail"}">${saved ? "Recording saved" : `Recording stopped: ${esc(rec.error)}`}</span>
        <button id="recok" title="${saved ? "After the lecture lists it" : ""}">OK</button>`;
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
  if (time) time.textContent = `${rec.state === "paused" ? "paused " : ""}${clock(rec.elapsed())}`;
  const level = $("#reclevel");
  if (level) level.style.width = `${Math.round((rec.state === "recording" ? rec.mic?.level() || 0 : 0) * 100)}%`;
  el.title = rec.take ? `${rec.file} · ${(rec.saved / 1e6).toFixed(1)} MB on the server` : "";
}

async function recordDialog() {
  if (rec?.active || !state?.session) return;
  const mic = new Microphone();                   // made in the click: its level meter may run
  const el = document.createElement("div");
  el.className = "dialog";
  el.innerHTML = `<div class="box"><h2>Record the lecture</h2>
    <p>A video of what the projector shows - slides, ink, pointer, quizzes - with your voice. It goes to the
    server while it is recorded, into the lecture's archive (After the lecture).</p>
    <label class="microw">Microphone <select id="micselect"></select></label>
    <div class="meter large"><i id="miclevel"></i></div><p id="micstate">Asking for the microphone ...</p>
    <p>Start opens the browser's dialog: choose the projector's screen, or the projector window.</p>
    <div class="buttons"><button class="primary" id="recstart" disabled>Start recording</button>
      <button class="secondary" id="closedlg">Cancel</button></div></div>`;
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
      say("Recording without sound.");
      return true;
    }
    try {
      const stream = await mic.open(id);
      if (closed || request !== micRequest || !stream) return false;
      sound = true;
      say("Speak: the bar shows what the microphone hears.");
    } catch (err) {
      if (closed || request !== micRequest) return false;
      mic.release();
      if (id && err.name === "OverconstrainedError") return openMic("");      // that one is gone: the default
      say(`No microphone - ${err.name === "NotAllowedError" ? "the browser may not use it" : err.message || err.name}.
        The recording would have no sound.`, true);
    }
    return true;
  };
  const fill = async () => {
    // the microphones by name, once the browser allowed one; before, only the default
    const named = (await microphones()).map((d) => [d.deviceId, d.label]);
    if (closed) return;
    const options = [...(named.length ? named : [["", "the default microphone"]]), ["none", "no sound"]];
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
      return say(err.name === "NotAllowedError" ? "No screen was chosen - Start again." : `The browser cannot record the screen: ${err.message || err.name}`, true);
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
      return say(`The recording did not start: ${err.message || err}`, true);
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
  box.innerHTML = takes.map((t) => {
    const here = rec?.take === t.take && rec.active;
    const what = here ? "being recorded" : !t.finished ? "unfinished" : t.remuxing ? "being finished" : "";
    const button = here || t.remuxing ? ""
      : !t.finished ? `<button data-finish="${esc(t.take)}" title="it was not stopped in this window: keep what came">Finish</button>`
        : `<button data-download="${esc(t.take)}">Download</button>`;
    return `<div class="device"><span class="name">${esc(t.file)}</span><span class="meta">${(t.size / 1e6).toFixed(1)} MB${
      what ? ` · ${what}` : ""}${t.folder ? ` · ${esc(t.folder)}` : ""}</span>${button}</div>`;
  }).join("") || '<p class="empty">No recording.</p>';
  box.querySelectorAll("[data-download]").forEach((b) => b.onclick = async () => {
    const r = await fetch(`/api/recording/${b.dataset.download}/download`, { method: "POST", headers: authHeaders(auth) });
    const info = await r.json().catch(() => ({}));
    if (!r.ok) return tell(info.error || String(r.status));
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
  el.className = "dialog";
  el.innerHTML = `<div class="box"><h2>After the lecture</h2>
    <p>The annotated PDF: every frame as it was shown last, with your ink, and the whiteboard pages -
    for the students. It is also kept in the lecture's archive on the server, with the quiz results.</p>
    <div class="buttons"><button class="primary" id="makepdf">Make the PDF</button></div><p id="pdfstate"></p>
    <p>The archive - the annotated PDF and the results - as one file:</p>
    <div class="buttons"><button class="secondary" id="zip">Download the archive (ZIP)</button></div>
    <h3>Recordings</h3><div class="recordings" id="recordings"><p class="empty">...</p></div>
    <div class="buttons"><button class="secondary" id="closedlg">Close</button></div></div>`;
  document.body.append(el);
  listRecordings(el.querySelector("#recordings"));
  const say = (text, error = false) => { const p = el.querySelector("#pdfstate"); p.textContent = text; p.className = error ? "error" : ""; };
  el.querySelector("#closedlg").onclick = () => el.remove();
  el.querySelector("#makepdf").onclick = async () => {
    const button = el.querySelector("#makepdf");
    button.disabled = true;
    try {
      say("Collecting the ink ...");
      const [stagePdf, ink] = await Promise.all([
        (await hostFetch(`/api/deck/${deck.bundle}/pdf`, auth)).arrayBuffer(),      // the browser has it already
        client.send({ t: "ink.all" })]);
      say("Making the PDF ...");
      const bytes = await annotatedPdf(stagePdf, deck, state.stage?.boards || [], ink.frames);
      const day = new Date().toISOString().slice(0, 10);
      save(new Blob([bytes], { type: "application/pdf" }), `${deck.deck}-${day}-annotated.pdf`);
      say("Downloaded. Keeping it in the archive ...");
      const r = await fetch(`/api/archive/${state.session.id}/annotated.pdf`, { method: "PUT",
        headers: { ...authHeaders(auth), "Content-Type": "application/pdf" }, body: bytes });
      const kept = await r.json().catch(() => ({}));
      say(r.ok ? `Downloaded, and kept in the server's archive (${kept.folder}).` : `Downloaded; the archive did not take it: ${kept.error || r.status}`, !r.ok);
    } catch (err) {
      say(`The PDF failed: ${err.message || err}`, true);
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
