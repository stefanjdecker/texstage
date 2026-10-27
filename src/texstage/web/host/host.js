// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The host console (docs/design.md, section 7): the lecturer's page. It pairs with the server
// (presenter key), picks a deck, and then is a browser slide host - the deck's slide pictures
// with the same live views the PowerPoint add-in shows, navigated with the arrow keys or a
// clicker - next to the players and the quizzes. The game runs without PowerPoint; with
// PowerPoint it is a remote: the stage follows the slide the server says is shown.

import { Client, hostFetch } from "/static/shared/client.js";
import { Stage } from "/static/shared/live.js";
import { uploadButton } from "/static/shared/upload.js";

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;                  // 1 quiz, 2 quizzes
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

start();

async function start() {
  key = (() => { try { return localStorage.getItem(KEY); } catch { return null; } })();
  if (!key) {
    try {
      key = (await (await fetch("/api/presenter-key")).json()).key || null;   // only on the server's machine
    } catch { key = null; }
  }
  if (!key) return keyForm();
  try {
    await showDecks(true);
  } catch {
    try { localStorage.removeItem(KEY); } catch { /* ignore */ }
    keyForm("This presenter key is not accepted.");
  }
}

function keyForm(error = "") {
  app.innerHTML = `<div class="page"><h1>Presenter key</h1>
    <p>The key is in the server's data folder (<code>presenter-key</code>) and is printed when it starts.</p>
    <form class="field" id="keyform"><input id="key" type="password" autocomplete="off" required>
    <button class="primary">Continue</button></form><div class="error">${esc(error)}</div></div>`;
  $("#keyform").addEventListener("submit", async (e) => {
    e.preventDefault();
    key = $("#key").value.trim();
    try {
      await showDecks();
      try { localStorage.setItem(KEY, key); } catch { /* private mode */ }
    } catch {
      keyForm("This presenter key is not accepted.");
    }
  });
}

async function showDecks(resume = false, uploaded = "") {
  const decks = await (await hostFetch("/api/decks", key)).json();
  if (resume) {                        // a reload in the middle of a game: back into it
    let last = null;
    try { last = sessionStorage.getItem(LAST); } catch { /* ignore */ }
    const d = decks.find((x) => x.bundle === last && x.game);
    if (d) return openGame(d);
  }
  $("#deckname").textContent = "";
  $("#pin").textContent = "";
  $("#join").textContent = "";
  $("#actions").innerHTML = "";
  $("#status").className = "status";
  const cards = decks.map((d, i) => `<div class="deckcard"><div class="info"><div class="name">${esc(d.name)}</div>
      <div class="meta">${esc(d.deck)} · ${count(d.quizzes, "quiz", "quizzes")} · ${count(d.slides, "slide", "slides")} · built ${new Date(d.built).toLocaleString()}</div></div>
      ${d.game ? `<span class="tag open">game ${esc(d.game.pin)} · ${count(d.game.players, "player", "players")}</span>` : ""}
      <button class="primary" data-i="${i}">${d.game ? "Continue" : "Start"}</button></div>`).join("");
  app.innerHTML = `<div class="page"><h1>Decks</h1>
    <p>Built with <code>texstage build</code> / <code>tools/scripts/texstage-build.py</code>; a deck built now appears after a reload.
    A deck this server does not have: upload its <code>.bundle.zip</code> from the build folder, or drop it here.</p>
    <div class="uploadbar"><span id="upload"></span><span class="uploaded">${esc(uploaded)}</span></div>
    <div class="decks">${cards || '<p class="empty">No decks on this server yet.</p>'}</div></div>`;
  app.querySelectorAll("button[data-i]").forEach((b) => b.addEventListener("click", () => openGame(decks[+b.dataset.i])));
  uploadButton($("#upload"), key, (message) => showDecks(false, message));
}

async function openGame(d) {
  deck = await (await hostFetch(`/api/deck/${d.bundle}`, key)).json();
  try { sessionStorage.setItem(LAST, d.bundle); } catch { /* ignore */ }
  $("#deckname").textContent = deck.name;
  $("#actions").innerHTML = `<button id="csv">Results (CSV)</button><button id="newgame">New game</button><button id="decks">Decks</button>`;
  app.innerHTML = `<div class="game">
    <section class="stagecol"><div class="stagewrap" id="wrap"><div id="stage"></div></div>
      <div class="nav"><button id="prev" title="previous slide (←)">◀</button><span class="where" id="where"></span>
      <button id="next" title="next slide (→)">▶</button><button id="full" title="full screen (F)">⛶</button></div></section>
    <aside class="side"><div class="panel"><h2 id="ptitle">Players</h2><div class="players" id="players"></div></div>
      <div class="panel"><h2>Quizzes</h2><div class="quizzes" id="quizzes"></div></div></aside></div>`;
  client?.close();
  client = new Client({
    onStatus: (s) => { $("#status").className = `status ${s}`; },
    onState: (m) => { state = m; update(); },
  });
  stage = new Stage($("#stage"), { send: (cmd) => client.send(cmd).catch(alertError), controls: true });
  await client.login({ t: "hello", role: "host", key, deck: deck.deck, bundle: deck.bundle });
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
    if (!confirm("Start a new game? The players join again with a new PIN.")) return;
    await client.send({ t: "restart" }).catch(alertError);
  };
  $("#csv").onclick = downloadResults;
}

function alertError(err) {
  if (err?.code !== "no-round") alert(err?.message || err);
}

function slideIndex(id) {
  const i = deck.slides.findIndex((s) => s.id === id);
  return i < 0 ? 0 : i;
}

function update() {
  const s = state.session;
  $("#pin").textContent = `PIN ${s.pin.slice(0, 3)} ${s.pin.slice(3)}`;
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
  stage.show(slide, deck, state, () => client.now());
  const i = slideIndex(local);
  const live = slide.phase ? ` · ${slide.phase}${slide.quiz ? ` · ${slide.quiz}` : ""}` : "";
  $("#where").textContent = `slide ${i + 1} / ${deck.slides.length}${live}`;
  const players = state.players;
  $("#ptitle").textContent = `Players (${players.length}, ${state.session.connected} online)`;
  $("#players").innerHTML = players.map((p) => `<div class="player"><span class="rank">${p.rank || ""}</span>
      <span class="dot ${p.connected ? "on" : ""}"></span><span class="name">${esc(p.nickname)}</span>
      <span class="pts">${p.score}</span><button data-rename="${p.id}" title="rename">✎</button><button data-kick="${p.id}" title="remove">✕</button></div>`).join("")
    || '<div class="empty">Nobody has joined yet.</div>';
  $("#players").querySelectorAll("[data-rename]").forEach((b) => b.onclick = () => {
    const p = players.find((x) => x.id === b.dataset.rename);
    const name = prompt("New nickname", p.nickname);
    if (name) client.send({ t: "rename", player: p.id, nickname: name }).catch(alertError);
  });
  $("#players").querySelectorAll("[data-kick]").forEach((b) => b.onclick = () => {
    const p = players.find((x) => x.id === b.dataset.kick);
    if (confirm(`Remove ${p.nickname} from the game?`)) client.send({ t: "kick", player: p.id }).catch(alertError);
  });
  $("#quizzes").innerHTML = Object.entries(deck.quizzes).map(([id, q]) => {
    const r = state.rounds[id];
    const tag = r ? `<span class="tag ${r.phase}">${r.phase}${r.phase === "open" || r.phase === "get-ready" ? ` · ${r.answered}` : ""}</span>` : "";
    return `<button class="quiz" data-quiz="${esc(id)}"><span class="title" title="${esc(q.title)}">${esc(id)}</span><span class="tag">${esc(q.type)}</span>${tag}</button>`;
  }).join("");
  $("#quizzes").querySelectorAll("[data-quiz]").forEach((b) => b.onclick = () => {
    // a quiz starts on its reading slide (the question alone); the next key starts the round
    const target = deck.slides.find((s) => s.quiz === b.dataset.quiz && s.phase === "read")
      || deck.slides.find((s) => s.quiz === b.dataset.quiz && s.phase === "question");
    if (target) go(target.id);
  });
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
