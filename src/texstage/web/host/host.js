// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The host console (docs/design.md, section 7): the lecturer's page. It pairs with the server
// (presenter key), picks a deck, and then is a browser slide host - the deck's slide pictures
// with the same live views the PowerPoint add-in shows, navigated with the arrow keys or a
// clicker - next to the players and the quizzes. The game runs without PowerPoint; with
// PowerPoint it is a remote: the stage follows the slide the server says is shown. It speaks the
// open game's deck's language (i18n.js: "host", "lecturer"), the key form and the decks the browser's.

import { errorText, pageLanguage, usePageLanguage } from "/static/i18n/i18n.js";
import { Client, hostFetch } from "/static/shared/client.js";
import { Stage } from "/static/shared/live.js";
import { uploadButton } from "/static/shared/upload.js";
import { ActsLine } from "/static/host/acts.js";
import { ask } from "/static/stage/ask.js";

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const app = $("#app");
const KEY = "texquiz:presenter-key";
const LAST = "texquiz:deck";          // this tab's game, for reloads

let key = null;
let deck = null;        // deck.json of the game's bundle
let client = null;
let state = null;       // the server's host view
let stage = null;
let local = null;       // the slide this console shows (follows the server unless we just moved)
let pending = null;     // a slide we asked for and the server has not confirmed yet
let T = null;           // the page's texts (speak): the open deck's language, else the browser's
let following = null;   // the deck list's look for changes (showDecks)

function speak(tag) {
  // the page's language from now on - the open deck's (a deck built before 2026-10-24 names none:
  // English), or the browser's (null)
  T = usePageLanguage(tag);
  document.title = T.host.title;
  $("#status").title = T.lecturer.connection;
}

async function start() {
  speak(null);
  key = (() => { try { return localStorage.getItem(KEY); } catch { return null; } })();
  if (!key) {
    try {
      key = (await (await fetch("/api/presenter-key")).json()).key || null;   // only on the server's machine
    } catch { key = null; }
  }
  if (!key) return keyForm();
  try {
    await showDecks(true);
  } catch (err) {
    // only the server's refusal of the key forgets it; the server out of reach for a moment, or
    // anything else, leaves it stored for the next try
    if (err?.status !== 403) return keyForm(errorText(pageLanguage(), err));
    try { localStorage.removeItem(KEY); } catch { /* ignore */ }
    keyForm(T.errors["bad-key"]);
  }
}

function keyForm(error = "") {
  const L = T.lecturer;
  app.innerHTML = `<div class="page"><h1>${esc(L.key)}</h1>
    <p>${L.keyWhere("<code>presenter-key</code>")}</p>
    <form class="field" id="keyform"><input id="key" type="password" autocomplete="off" required>
    <button class="primary">${esc(L.go)}</button></form><div class="error">${esc(error)}</div></div>`;
  $("#keyform").addEventListener("submit", async (e) => {
    e.preventDefault();
    key = $("#key").value.trim();
    try {
      await showDecks();
      try { localStorage.setItem(KEY, key); } catch { /* private mode */ }
    } catch (err) {
      keyForm(err?.status === 403 ? T.errors["bad-key"] : errorText(pageLanguage(), err));
    }
  });
}

async function showDecks(resume = false, uploaded = "") {
  const [decks, folders] = await Promise.all([hostFetch("/api/decks", key).then((r) => r.json()),
    hostFetch("/api/folders", key).then((r) => r.json()).catch(() => [])]);
  if (resume) {                        // a reload in the middle of a game: back into it
    let last = null;
    try { last = sessionStorage.getItem(LAST); } catch { /* ignore */ }
    const d = decks.find((x) => x.bundle === last && x.game);
    if (d) return openGame(d);
  }
  speak(null);                         // the decks: the browser's language
  const L = T.lecturer;
  $("#deckname").textContent = "";
  $("#pin").textContent = "";
  $("#join").textContent = "";
  $("#actions").innerHTML = "";
  $("#status").className = "status";
  // as the deck page names and files them (library.py): the lecturer's own name for a deck, its folder - by
  // folder, then by name
  const byId = new Map((Array.isArray(folders) ? folders : []).map((f) => [f.id, f]));
  const path = (fid) => {
    const out = [];
    for (let f = byId.get(fid); f && out.length < 64; f = byId.get(f.parent)) out.unshift(f.name);
    return out.join(" › ");
  };
  const byName = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
  decks.sort((a, b) => byName(path(a.folder), path(b.folder)) || byName(a.label || a.name, b.label || b.name) || b.built - a.built);
  const built = (ms) => new Date(ms).toLocaleString(T.meta.locale, { dateStyle: "medium", timeStyle: "short" });
  const cards = decks.map((d, i) => `<div class="deckcard"><div class="info"><div class="name">${esc(d.label || d.name)}</div>
      <div class="meta">${esc([path(d.folder), d.label ? d.name : "", d.deck, L.quizzes(d.quizzes), L.slides(d.slides),
    L.built(built(d.built))].filter(Boolean).join(" · "))}</div></div>
      ${d.game?.running ? `<span class="tag open">${esc(L.game(d.game.pin, d.game.players))}</span>` : ""}
      <button class="primary" data-i="${i}">${esc(d.game?.running ? T.host.resume : T.host.start)}</button></div>`).join("");
  app.innerHTML = `<div class="page"><h1>${esc(L.decks)}</h1>
    <p>${T.host.intro("<code>texstage build</code>", "<code>tools/scripts/texstage-build.py</code>")}
    ${L.upload("<code>.bundle.zip</code>")}</p>
    <div class="uploadbar"><span id="upload"></span><span class="uploaded">${esc(uploaded)}</span></div>
    <div class="decks">${cards || `<p class="empty">${esc(L.noDecks)}</p>`}</div></div>`;
  app.querySelectorAll("button[data-i]").forEach((b) => b.addEventListener("click", () => openGame(decks[+b.dataset.i])));
  uploadButton($("#upload"), key, (message) => showDecks(false, message));
  // a deck built meanwhile, a game started or ended elsewhere: the list follows by itself while it is shown
  const list = app.querySelector(".decks"), was = JSON.stringify(decks.map((d) => [d.bundle, d.game, d.label, d.folder]));
  clearTimeout(following);
  const look = async () => {                      // (the next once this one has answered: none overlap)
    if (!list.isConnected || client) return;
    if (!document.hidden && !document.querySelector(".dialog")) {
      try {
        const now = await (await hostFetch("/api/decks", key)).json();
        if (list.isConnected && !client && JSON.stringify(now.map((d) => [d.bundle, d.game, d.label, d.folder])) !== was) {
          return showDecks(false, uploaded);
        }
      } catch {
        /* the server away: the next turn */
      }
    }
    if (list.isConnected && !client) following = setTimeout(look, 8000);
  };
  following = setTimeout(look, 8000);
}

async function openGame(d) {
  deck = await (await hostFetch(`/api/deck/${d.bundle}`, key)).json();
  speak(deck.language || "");          // from here on the deck's language
  const H = T.host, L = T.lecturer;
  try { sessionStorage.setItem(LAST, d.bundle); } catch { /* ignore */ }
  $("#deckname").textContent = deck.name;
  $("#actions").innerHTML = `<button id="csv">${esc(L.csv)}</button><button id="newgame">${esc(L.newGame)}</button>
    <button id="decks">${esc(L.decks)}</button>`;
  app.innerHTML = `<div class="game">
    <section class="stagecol"><div class="stagewrap" id="wrap"><div id="stage"></div></div>
      <div class="nav"><button id="prev" title="${esc(H.prev)}">◀</button><span class="where" id="where"></span>
      <button id="next" title="${esc(H.next)}">▶</button><button id="full" title="${esc(H.full)}">⛶</button></div></section>
    <aside class="side"><div class="panel"><h2 id="ptitle">${esc(H.players)}</h2><div class="players" id="players"></div></div>
      <div class="panel"><h2>${esc(H.quizzes)}</h2><div class="quizzes" id="quizzes"></div></div>
      <div class="panel" id="actspanel" hidden><h2>${esc(H.activities)}</h2><div class="quizzes" id="acts"></div></div></aside></div>`;
  // the lists' buttons, by delegation: a push draws the lists anew (fill), their buttons with them
  $("#players").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-rename], button[data-kick]");
    const p = b && state?.players.find((x) => x.id === (b.dataset.rename || b.dataset.kick));
    if (!p) return;
    if (b.dataset.rename) {
      const name = prompt(T.host.renameAsk, p.nickname);
      if (name) client.send({ t: "rename", player: p.id, nickname: name }).catch(alertError);
    } else if (confirm(T.host.removeAsk(p.nickname))) client.send({ t: "kick", player: p.id }).catch(alertError);
  });
  $("#quizzes").addEventListener("click", (e) => {
    const b = e.target.closest("[data-quiz]");
    if (!b) return;
    // a quiz starts on its reading slide (the question alone); the next key starts the round
    const target = deck.slides.find((s) => s.quiz === b.dataset.quiz && s.phase === "read")
      || deck.slides.find((s) => s.quiz === b.dataset.quiz && s.phase === "question");
    if (target) go(target.id);
  });
  client?.close();
  client = new Client({
    onStatus: (s) => { $("#status").className = `status ${s}`; },
    onState: (m) => { state = m; update(); },
    onBye: (m) => refused({ code: m.reason, message: m.message }),
  });
  stage = new Stage($("#stage"), { send: (cmd) => client.send(cmd).catch(alertError), controls: true });
  const mine = client;
  // a game of the deck on another build with players, answers or ink (replaces-game): asked first, as the
  // presenter window asks - this build ends that game, or the running build is opened instead
  const hello = { t: "hello", role: "host", key, deck: deck.deck, bundle: deck.bundle, ask: true };
  try {
    await client.login(hello);
  } catch (err) {
    if (client !== mine) return;                  // (not when this console has left the game meanwhile)
    if (err?.code !== "replaces-game" || !err.detail) return refused(err);
    const replace = await replaceOrKeep(err.detail);
    if (client !== mine) return;
    if (!replace) return openGame({ bundle: err.detail.bundle });           // the running build
    try {
      await client.login({ ...hello, ask: false });
    } catch (again) {
      if (client === mine) refused(again);
      return;
    }
  }
  mine.relogin(hello);                            // after a break: asking again, as the presenter window does
  $("#prev").onclick = () => move(-1);
  $("#next").onclick = () => move(1);
  $("#full").onclick = fullscreen;
  $("#decks").onclick = () => {
    client.close();
    client = null;
    try { sessionStorage.removeItem(LAST); } catch { /* ignore */ }
    showDecks();
  };
  $("#newgame").onclick = async () => {
    if (!confirm(T.lecturer.newGameAsk)) return;
    await client.send({ t: "restart" }).catch(alertError);
  };
  $("#csv").onclick = downloadResults;
}

// What a build would end, as the presenter window says it (presenter.js: replaceOrKeep), and the choice
async function replaceOrKeep(e) {
  const R = T.presenter.replace, E = T.presenter.earlier;
  const what = [e.players ? T.lecturer.players(e.players) : "", e.asked ? R.asked(e.asked) : "",
    e.frames ? E.ink(e.frames) : "", e.boards ? E.boards(e.boards) : ""].filter(Boolean).join(", ");
  let when = "";
  if (e.built) {
    const d = new Date(e.built), hm = d.toLocaleTimeString(T.meta.locale, { hour: "2-digit", minute: "2-digit" });
    when = d.toDateString() === new Date().toDateString() ? E.today(hm)
      : E.on(d.toLocaleDateString(T.meta.locale, { day: "numeric", month: "long" }), hm);
  }
  return ask(R.ask(when, e.pin, what, e.newer), R.open, R.keep);
}

const textOf = (table, key) => (Object.prototype.hasOwnProperty.call(table, key) ? table[key] : key);   // a phase's name, else itself

// The server would not give this console its game, or took it away: a newer build of the deck is played (a
// console of a build before it, connected again or reloaded), the game is over, ... - the decks, and why.
function refused(err) {
  client.close();
  client = null;
  state = null;                                    // (the keys move no slide of the game left)
  try { sessionStorage.removeItem(LAST); } catch { /* ignore */ }
  showDecks().then(() => alertError(err),
    (e) => keyForm(e?.status === 403 ? T.errors["bad-key"] : errorText(pageLanguage(), e)));
}

function alertError(err) {
  if (err?.code !== "no-round") alert(errorText(pageLanguage(), err));
}

function slideIndex(id) {
  const i = deck.slides.findIndex((s) => s.id === id);
  return i < 0 ? 0 : i;
}

function update() {
  const s = state.session;
  $("#pin").textContent = `${T.lecturer.pin} ${s.pin.slice(0, 3)} ${s.pin.slice(3)}`;
  $("#join").textContent = s.join.replace(/\?pin=.*/, "");
  if (pending !== null && s.slide === pending) pending = null;
  if (pending === null) {
    if (s.slide === null || s.slide === undefined) {
      local = pending = deck.slides[0].id;                            // a fresh game: the first slide
      client.send({ t: "slide", slide: local }).catch(() => {});
    } else {
      local = s.slide;
    }
  }
  render();
}

function render() {
  const slide = deck.slides[slideIndex(local)];
  stage.show(slide, deck, state, () => (client ? client.now() : Date.now()));   // (its clock runs on when the game is left)
  const i = slideIndex(local);
  const H = T.host, L = T.lecturer;
  const live = slide.phase ? ` · ${textOf(L.phase, slide.phase)}${slide.quiz ? ` · ${slide.quiz}` : ""}` : "";
  $("#where").textContent = `${H.slideOf(i + 1, deck.slides.length)}${live}`;
  const players = state.players;
  $("#ptitle").textContent = H.playersOf(players.length, state.session.connected);
  fill($("#players"), players.map((p) => `<div class="player"><span class="rank">${p.rank || ""}</span>
      <span class="dot ${p.connected ? "on" : ""}"></span><span class="name">${esc(p.nickname)}</span>
      <span class="pts">${p.score}</span><button data-rename="${p.id}" title="${esc(H.rename)}">✎</button>
      <button data-kick="${p.id}" title="${esc(H.remove)}">✕</button></div>`).join("")
    || `<div class="empty">${esc(H.nobody)}</div>`);
  fill($("#quizzes"), Object.entries(deck.quizzes).map(([id, q]) => {
    const r = state.rounds[id];
    const tag = r ? `<span class="tag ${r.phase}">${esc(textOf(L.round, r.phase))}${r.phase === "open" || r.phase === "get-ready" ? ` · ${r.answered}` : ""}</span>` : "";
    return `<button class="quiz" data-quiz="${esc(id)}"><span class="title" title="${esc(q.title)}">${esc(id)}</span><span class="tag">${esc(q.type)}</span>${tag}</button>`;
  }).join(""));
  activities();
}

// The lists are drawn anew with the pushes - five a second while answers come in - and a button drawn anew
// under a pressed pointer loses its click (rename, remove, a quiz): a list a pointer is down in waits, and
// is drawn once it is up; a list whose HTML is the same is left alone.
let pressed = null;
document.addEventListener("pointerdown", (e) => { pressed = e.target.closest?.("#players, #quizzes") || null; }, true);
for (const up of ["pointerup", "pointercancel"]) {
  document.addEventListener(up, () => {
    if (!pressed) return;
    pressed = null;
    setTimeout(() => { if (deck && state) render(); });     // (after the click, which comes next)
  }, true);
}
function fill(el, html) {
  if (el === pressed || el.drawn === html) return;
  el.drawn = html;
  el.innerHTML = html;
}

// The deck's live activities, with --activities core (the deck's view says so): each one's phase - and of
// the current one its time left, counting down, and its counts, from its picture as the presenter window has
// it (acts.js: whatever the projector holds back; the design's 13).
let actsLine = null;
function activities() {
  const box = $("#acts");
  const items = deck?.items?.activity || {};
  if (box) $("#actspanel").hidden = deck?.activities !== "core" || !Object.keys(items).length;
  if (!box || !state || !client || $("#actspanel").hidden) {    // (no game shown, or left: nothing counts down)
    actsLine?.destroy();
    actsLine = null;
    return;
  }
  const A = T.presenter.steps, H = T.host;
  actsLine ??= new ActsLine({ read: (msg) => (client ? client.send(msg) : Promise.reject(new Error("no game"))),
    now: () => (client ? client.now() : Date.now()), render: () => activities() });
  const acts = state.stage?.activity || { current: null, items: {} };
  actsLine.update(acts);
  box.innerHTML = Object.keys(items).map((id) => {
    const phase = acts.items?.[id]?.phase || "ready";
    const more = actsLine.said(id, H);
    return `<div class="quiz"><span class="title">${esc(id)}</span><span class="tag ${esc(phase)}">${esc(A.phase[phase] || phase)}</span>
      ${more ? `<span class="tag">${esc(more)}</span>` : ""}</div>`;
  }).join("");
}

function go(id) {
  local = id;
  pending = id;
  render();
  client.send({ t: "slide", slide: id }).catch(alertError);
}

function move(step) {
  const i = Math.min(deck.slides.length - 1, Math.max(0, slideIndex(local) + step));
  if (deck.slides[i].id !== local) go(deck.slides[i].id);
}

function fullscreen() {
  const wrap = $("#wrap");
  if (document.fullscreenElement) document.exitFullscreen();
  else wrap.requestFullscreen?.();
}

async function downloadResults() {
  const r = await hostFetch(`/api/results/${state.session.id}.csv`, key);
  const name = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "results.csv";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await r.blob());
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

// keys: arrows and PageUp/PageDown (what clickers send), Space, Home/End, F for full screen
document.addEventListener("keydown", (e) => {
  if (!deck || !state || e.target.closest("input, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key;
  if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(k)) move(1);
  else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(k)) move(-1);
  else if (k === "Home") go(deck.slides[0].id);
  else if (k === "End") go(deck.slides[deck.slides.length - 1].id);
  else if (k === "f" || k === "F") fullscreen();
  else return;
  e.preventDefault();
});

// Last, when every constant above has its value (as in the presenter window, presenter.js).
start();
