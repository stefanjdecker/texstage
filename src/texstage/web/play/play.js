// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The phone (docs/design.md, section 7): PIN -> nickname -> lobby -> answer per question
// type -> answer locked -> result -> final rank. Talks to the server over the shared client;
// the server decides everything, this page only shows its state and sends answers.
//
// The token from joining is kept in localStorage, so a reload or a lost connection resumes
// the same player. A screen is rebuilt only when it changes (not on every push), so an
// answer being typed or arranged survives the live updates.
//
// texstage M6: a poll typed during the lecture comes as text (formulas by KaTeX, text.js)
// where a deck's quiz has pictures; a sketch question gets a drawing pad (sketch.js); while
// the lecturer takes questions, a second tab asks and upvotes them - its list comes with the
// states only while the tab is open (qa.watch).

import { ActivityScreen } from "/static/play/activity.js";
import { PluginScreen } from "/static/shared/plugins.js";
import { Client } from "/static/shared/client.js";
import { color, shapeSVG } from "/static/shared/shapes.js";
import { PENS, SketchPad, sketchSVG } from "/static/shared/sketch.js";
import { textHTML } from "/static/shared/text.js";

const GERMAN = (navigator.language || "en").toLowerCase().startsWith("de");
document.documentElement.lang = GERMAN ? "de" : "en";
const T = GERMAN ? {
  pin: "Spiel-PIN", nick: "Dein Spitzname", join: "Mitspielen", in: "Du bist dabei!", watch: "Schau nach vorne – gleich geht es los.",
  ready: "Gleich geht's los!", send: "Abschicken", sent: "Antwort abgeschickt", waitOthers: "Warte auf die anderen …",
  timesUp: "Die Zeit ist um", noAnswer: "Keine Antwort", correct: "Richtig!", wrong: "Leider falsch", partly: "Teilweise richtig",
  thanks: "Danke!", points: "Punkte", streak: "Serie", rank: (r, n) => `Platz ${r} von ${n}`, paused: "Pausiert",
  finished: "Spielende", yourRank: "Dein Platz", again: "Neu beitreten", gameOver: "Dieses Spiel ist vorbei.",
  kicked: "Du wurdest aus dem Spiel entfernt.", offline: "Verbindung wird wiederhergestellt …", typeHere: "Deine Antwort",
  several: "Mehrere Antworten können richtig sein", tickAll: "Alles Zutreffende ankreuzen",
  orderHint: "In die richtige Reihenfolge bringen", practice: "Übungsrunde – ohne Punkte",
  answerWas: "Richtige Antwort", up: "nach oben", down: "nach unten", bonus: "Serienbonus",
  answer: "Antwort", questionPicture: "Die Frage, wie vorne gezeigt",
  waitReveal: "Gleich kommt die Auflösung …", reading: "Lies die Frage – gleich kommen die Antworten.",
  draw: "Zeichne mit dem Finger.", undo: "Rückgängig", clear: "Löschen", pens: ["Schwarz", "Rot", "Blau", "Grün"],
  tooMuch: "Zu viel gezeichnet – nimm ein paar Striche zurück.", quizTab: "Quiz", qaTab: "Fragen",
  ask: "Stell eine Frage – anonym.", yourQuestion: "Deine Frage", askSend: "Fragen", noQuestions: "Noch keine Fragen.",
  yours: "deine", answered: "beantwortet", upvote: "Diese Frage unterstützen", asked: "Deine Frage ist da.",
} : {
  pin: "Game PIN", nick: "Your nickname", join: "Join", in: "You're in!", watch: "Watch the screen – it starts soon.",
  ready: "Get ready!", send: "Submit", sent: "Answer sent", waitOthers: "Waiting for the others …",
  timesUp: "Time's up", noAnswer: "No answer", correct: "Correct!", wrong: "Not quite", partly: "Partly right",
  thanks: "Thanks!", points: "points", streak: "streak", rank: (r, n) => `Rank ${r} of ${n}`, paused: "Paused",
  finished: "Game over", yourRank: "Your rank", again: "Join again", gameOver: "This game is over.",
  kicked: "You have been removed from the game.", offline: "Reconnecting …", typeHere: "Your answer",
  several: "Several answers can be correct", tickAll: "Tick all that apply",
  orderHint: "Put them in the right order", practice: "Practice round – no points",
  answerWas: "Right answer", up: "up", down: "down", bonus: "streak bonus",
  answer: "Answer", questionPicture: "The question, as shown at the front",
  waitReveal: "The answer comes next …", reading: "Read the question – the answers come next.",
  draw: "Draw with your finger.", undo: "Undo", clear: "Clear", pens: ["black", "red", "blue", "green"],
  tooMuch: "Too much drawn – undo a few strokes.", quizTab: "Quiz", qaTab: "Questions",
  ask: "Ask a question – anonymously.", yourQuestion: "Your question", askSend: "Ask", noQuestions: "No questions yet.",
  yours: "yours", answered: "answered", upvote: "Upvote this question", asked: "Your question is in.",
};

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const app = $("#app");
const STORE = "texquiz:player";

let state = null;        // the server's player view
let screenKey = "";
let draft = {};          // per round: selection, order, value, text, strokes
let joinError = "";
let tab = "quiz";        // or "qa": the audience's questions (M6)
let switched = null;     // the round that brought the quiz tab back
let listed = "";         // the questions as last drawn
const redraw = () => { screenKey = ""; listed = ""; if (state) render(); };   // a formula's KaTeX arrived

// texstage's content types on the phone (docs/live-activities-design.md, section 10): a type whose
// part of the state is there (state[name], with its item's id) gets the screen while no quiz round
// is open - the round comes first. Its screen owns its elements, so what is being typed survives
// the pushes:  new PHONE_TYPES[name]({root, client, T, state})  .update(state)  .destroy()
const PHONE_TYPES = { activity: ActivityScreen, plugins: PluginScreen };
let typeScreen = null;

const saved = (() => { try { return JSON.parse(localStorage.getItem(STORE) || "null"); } catch { return null; } })();
const urlPin = new URLSearchParams(location.search).get("pin") || "";

const client = new Client({
  onStatus: (s) => {
    $("#offline").hidden = s === "open" || !state;
    $("#offline").textContent = T.offline;
    if (s === "open" && tab === "qa") client.send({ t: "qa.watch", on: true }).catch(() => {});   // a new connection
  },
  onState: (m) => { state = m; render(); },
  onBye: (m) => {
    forget();
    state = null;
    showMessage(m.reason === "kicked" ? T.kicked : T.gameOver);
  },
});

function remember(pin, token, nickname) {
  try { localStorage.setItem(STORE, JSON.stringify({ pin, token, nickname })); } catch { /* private mode */ }
}
function forget() {
  try { localStorage.removeItem(STORE); } catch { /* ignore */ }
}

// ------------------------------------------------------------------ joining
if (saved && saved.token && (!urlPin || urlPin === saved.pin)) {
  client.login({ t: "resume", token: saved.token }).catch(() => { forget(); joinForm(); });
  app.innerHTML = '<div class="center"><div class="spinner"></div></div>';
} else {
  joinForm();
}

function joinForm() {
  screenKey = "join";
  app.innerHTML = `<form class="center" id="join" autocomplete="off">
    <h1>texstage</h1>
    <label for="pin">${esc(T.pin)}</label>
    <input id="pin" class="pin-input" inputmode="numeric" pattern="[0-9 ]*" maxlength="7" value="${esc(urlPin)}" required>
    <label for="nick">${esc(T.nick)}</label>
    <input id="nick" type="text" maxlength="20" value="${esc(saved?.nickname || "")}" required autocapitalize="words">
    <button class="main" type="submit">${esc(T.join)}</button>
    <div class="error" id="err">${esc(joinError)}</div></form>`;
  const form = $("#join");
  (urlPin ? $("#nick") : $("#pin")).focus();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const pin = $("#pin").value.replace(/\D/g, "");
    const nickname = $("#nick").value.trim();
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const w = await client.login({ t: "join", pin, nickname });
      remember(pin, w.token, w.nickname);
      client.relogin({ t: "resume", token: w.token });
      joinError = "";
    } catch (err) {
      joinError = err.message || String(err);
      $("#err").textContent = joinError;
      button.disabled = false;
    }
  });
}

function showMessage(text) {
  screenKey = "message";
  $("#who").textContent = "";
  $("#score").textContent = "";
  setTab("quiz");
  $("#tabs").hidden = true;
  app.innerHTML = `<div class="center"><h2>${esc(text)}</h2><button class="main" id="again">${esc(T.again)}</button></div>`;
  $("#again").onclick = () => { joinError = ""; joinForm(); };
}

// ------------------------------------------------------------------ the audience's questions (M6)
function setTab(t) {
  if (t === tab) return;
  tab = t;
  app.hidden = tab !== "quiz";
  $("#qa").hidden = tab !== "qa";
  $("#tabs").querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  if (state) client.send({ t: "qa.watch", on: tab === "qa" }).catch(() => {});
  if (tab === "qa") askForm();
}

function tabs() {
  // the tabs while the lecturer takes questions; a question that opens brings the quiz back
  const open = Boolean(state.qa?.open);
  const bar = $("#tabs");
  if (!bar.firstChild) {
    bar.innerHTML = `<button data-tab="quiz" aria-selected="true">${esc(T.quizTab)}</button>
      <button data-tab="qa" aria-selected="false">${esc(T.qaTab)}</button>`;
    bar.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
  }
  bar.hidden = !open;
  const r = state.round;
  const asking = r && (r.phase === "get-ready" || (r.phase === "open" && !r.answer));
  if (tab === "qa" && (!open || (asking && switched !== r.id))) {
    if (asking) switched = r.id;
    setTab("quiz");
  }
}

function askForm() {
  const box = $("#qa");
  if (box.firstChild) return;
  box.innerHTML = `<form class="ask" id="askform"><label for="asktext">${esc(T.ask)}</label>
      <textarea id="asktext" rows="3" maxlength="280" placeholder="${esc(T.yourQuestion)}"></textarea>
      <div class="askrow"><span class="count"><span id="askchars">0</span> / 280</span>
        <button class="main" id="asksend" disabled>${esc(T.askSend)}</button></div>
      <div class="error" id="askerr"></div></form>
    <div class="qalist" id="qalist"></div>`;
  const text = $("#asktext");
  text.addEventListener("input", () => {
    $("#askchars").textContent = text.value.length;
    $("#asksend").disabled = !text.value.trim();
  });
  $("#askform").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#asksend").disabled = true;
    try {
      await client.send({ t: "qa.ask", text: text.value });
      text.value = "";
      $("#askchars").textContent = "0";
      $("#askerr").className = "note";
      $("#askerr").textContent = T.asked;
    } catch (err) {
      $("#askerr").className = "error";
      $("#askerr").textContent = err.message;
      $("#asksend").disabled = false;
    }
  });
  $("#qalist").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-q]");
    if (b) client.send({ t: "qa.vote", question: b.dataset.q, on: b.getAttribute("aria-pressed") !== "true" }).catch(() => {});
  });
  listed = "";
}

function questions() {
  const list = $("#qalist");
  const items = state.qa?.questions;
  if (!list || !items) return;
  const key = JSON.stringify(items);
  if (key === listed) return;
  listed = key;
  list.innerHTML = items.map((q) => {
    const done = q.state === "done";
    return `<div class="qitem${done ? " done" : ""}"><div class="qtext">${textHTML(q.text, redraw)}
        ${q.mine || done ? `<div class="tags">${q.mine ? `<span>${esc(T.yours)}</span>` : ""}${done ? `<span>${esc(T.answered)}</span>` : ""}</div>` : ""}</div>
      <button class="vote" data-q="${esc(q.id)}" aria-pressed="${q.voted}" aria-label="${esc(T.upvote)}" ${q.mine || done ? "disabled" : ""}>▲<b>${q.votes}</b></button></div>`;
  }).join("") || `<p class="empty">${esc(T.noQuestions)}</p>`;
}

// ------------------------------------------------------------------ screens
function render() {
  const me = state.me;
  $("#who").textContent = me.nickname;
  $("#score").textContent = `${me.score} ${T.points}`;
  $("#offline").hidden = true;
  tabs();
  if (tab === "qa") questions();
  const r = state.round;
  const asking = r && (r.phase === "get-ready" || r.phase === "open");
  const typed = state.session.finished || asking ? undefined : Object.keys(PHONE_TYPES).find((name) =>
    name === "plugins" ? state.plugins?.items.some(d => d.modules["participant-input"]) : state[name]);
  if (typed) {
    const k = `type:${typed}:${state[typed].id ?? ""}`;
    if (k !== screenKey || !typeScreen) {
      screenKey = k;
      typeScreen?.destroy();
      app.innerHTML = "";
      typeScreen = new PHONE_TYPES[typed]({ root: app, client, T, state, language: GERMAN ? "de" : "en" });
    }
    typeScreen.update(state);
    progress();
    return;
  }
  if (typeScreen) {
    typeScreen.destroy();
    typeScreen = null;
  }
  let key;
  if (state.session.finished) key = `finished:${me.rank}`;
  else if (!r) key = state.reading ? `reading:${state.reading.quiz}` : "lobby";
  else key = `${r.id}:${r.phase}:${r.answer ? 1 : 0}:${r.paused ? 1 : 0}`;
  if (key !== screenKey) {
    screenKey = key;
    if (state.session.finished) finished();
    else if (!r && state.reading) reading(state.reading);
    else if (!r) lobby();
    else if (r.phase === "get-ready") getReady(r);
    else if (r.phase === "open" && !r.answer) question(r);
    else if (r.phase === "revealed") result(r);
    else waiting(r);
  }
  progress();
}

function progress() {
  const bar = $("#progress span");
  const r = state?.round;
  if (!r || r.phase !== "open") { bar.style.width = "0"; return; }
  const left = r.paused ? r.remaining : Math.max(0, r.deadline - client.now());
  bar.style.width = `${(100 * left) / r.limit}%`;
}
setInterval(() => state && progress(), 200);

// The pictures are rendered at 3 device pixels per CSS pixel; shown 1.4 times their LaTeX
// size, normal-size text becomes about 18 px - readable on a phone, still sharp.
const ZOOM = 1.4;

function picture(p, alt = "", scale = ZOOM) {
  return `<img src="${state.session.base}${p.image}" style="width:${(p.width * scale).toFixed(1)}px" alt="${esc(alt)}">`;
}

// one scale for all answers of a question (the widest decides), so their text has one size
function answerScale(q, room) {
  const widest = Math.max(1, ...(q.answers || []).map((a) => a.width));
  return Math.min(ZOOM, room / widest);
}
const pageWidth = () => Math.min(innerWidth, 640) - 32;

// a question's prompt: the picture of a deck's quiz, the text of a poll typed in the lecture
function promptHTML(p) {
  if (!p) return "";
  return p.text !== undefined ? `<div class="card prompt text"><span>${textHTML(p.text, redraw)}</span></div>`
    : `<div class="card prompt">${picture(p, T.questionPicture)}</div>`;
}

function promptCard(r) {
  return promptHTML(r.question.prompt);
}

function lobby() {
  app.innerHTML = `<div class="center"><div class="big">✓</div><h1>${esc(T.in)}</h1><p>${esc(T.watch)}</p></div>`;
}

// the lecturer shows the question alone: read it here too; the answers come with the next click
function reading(rd) {
  app.innerHTML = `${promptHTML(rd.prompt)}<div class="center"><p>${esc(T.reading)}</p></div>`;
}

function getReady(r) {
  app.innerHTML = `${r.practice ? `<p>${esc(T.practice)}</p>` : ""}<div class="center"><h1>${esc(T.ready)}</h1><div class="big" id="count"></div></div>`;
  const tick = () => {
    const el = $("#count");
    if (!el) return;
    el.textContent = Math.max(0, Math.ceil((r.opens - client.now()) / 1000)) || "";
    requestAnimationFrame(tick);
  };
  tick();
}

function answerFace(a, scale = ZOOM) {
  const face = a.text === undefined ? picture(a, a.id, scale)                 // a deck's quiz: its picture
    : a.text ? `<span>${textHTML(a.text, redraw)}</span>` : `<b class="letter">${esc(a.id)}</b>`;   // a poll: its text, or the letter
  return `<span class="shape" aria-hidden="true">${shapeSVG(a.shape)}</span><span class="face${a.text === undefined ? "" : " text"}">${face}</span>`;
}

// a name for screen readers: the pictures say only the letter
function answerLabel(a) {
  return a.text ? `${T.answer} ${a.id}: ${a.text}` : `${T.answer} ${a.id}`;
}

function question(r) {
  const q = r.question;
  const d = (draft[r.id] ||= {});
  const kind = q.type === "poll" ? (q.select === "multiple" ? "multiple" : "single") : q.type;
  if (r.paused) {
    app.innerHTML = `${promptCard(r)}<div class="center"><h2>${esc(T.paused)}</h2></div>`;
    return;
  }
  let body = "";
  // two columns only if every answer picture fits its column at full size (texts: if short)
  const column = (pageWidth() - 10) / 2 - 56;
  const two = !(q.answers || []).some((a) => (a.text === undefined ? a.width * ZOOM > column : a.text.length > 14));
  const cols = two ? "answers" : "answers one";
  const scale = answerScale(q, kind === "order" ? pageWidth() - 116 : two ? column : pageWidth() - 56);
  if (kind === "single" || kind === "truefalse") {
    body = `<div class="${cols}">${q.answers.map((a) =>
      `<button class="answer" style="--c:${color(a.shape)}" data-id="${a.id}" aria-label="${esc(answerLabel(a))}">${answerFace(a, scale)}</button>`).join("")}</div>`;
  } else if (kind === "multiple") {
    d.choices ||= [];
    const hint = q.type === "poll" ? T.tickAll : T.several;          // a poll has no right answers
    body = `<p>${esc(hint)}</p><div class="${cols}">${q.answers.map((a) =>
      `<button class="answer ${d.choices.includes(a.id) ? "selected" : ""}" style="--c:${color(a.shape)}" data-id="${a.id}" aria-label="${esc(answerLabel(a))}" aria-pressed="${d.choices.includes(a.id)}">${answerFace(a, scale)}</button>`).join("")}</div>
      <button class="main" id="send" ${d.choices.length ? "" : "disabled"}>${esc(T.send)}</button>`;
  } else if (kind === "order") {
    d.order ||= q.answers.map((a) => a.id);
    const byId = Object.fromEntries(q.answers.map((a) => [a.id, a]));
    body = `<p>${esc(T.orderHint)}</p><div class="order">${d.order.map((id, i) => `<div class="item">
        <div class="answer" style="--c:${color(byId[id].shape)}">${answerFace(byId[id], scale)}</div>
        <div class="moves"><button data-move="${i}" data-dir="-1" aria-label="${esc(`${answerLabel(byId[id])}, ${T.up}`)}" ${i === 0 ? "disabled" : ""}>▲</button>
        <button data-move="${i}" data-dir="1" aria-label="${esc(`${answerLabel(byId[id])}, ${T.down}`)}" ${i === d.order.length - 1 ? "disabled" : ""}>▼</button></div></div>`).join("")}</div>
      <button class="main" id="send">${esc(T.send)}</button>`;
  } else if (kind === "numeric") {
    const n = q.numeric || {};
    const slider = n.min !== null && n.min !== undefined && n.max !== null && n.max !== undefined;
    d.value ??= slider ? (n.min + n.max) / 2 : "";
    body = slider
      ? `<div class="value"><span id="val">${esc(d.value)}</span> ${esc(n.unit || "")}</div>
         <input class="slider" id="num" type="range" min="${n.min}" max="${n.max}" step="${n.step || 1}" value="${d.value}">`
      : `<input id="num" type="number" inputmode="decimal" step="any" value="${esc(d.value)}" placeholder="${esc(n.unit || "")}">`;
    body += `<button class="main" id="send">${esc(T.send)}</button>`;
  } else if (kind === "sketch") {
    d.pen ??= 0;
    body = `<p>${esc(T.draw)}</p><div class="padbox" id="padbox"></div>
      <div class="padtools">${PENS.map((c, i) => `<button class="pen${i === d.pen ? " on" : ""}" data-pen="${i}"
        style="--c:${c}" aria-label="${esc(T.pens[i])}" aria-pressed="${i === d.pen}"></button>`).join("")}
        <span class="gap"></span><button class="tool" id="undo">↶ ${esc(T.undo)}</button>
        <button class="tool" id="clear">✕ ${esc(T.clear)}</button></div>
      <button class="main" id="send" ${d.strokes?.length ? "" : "disabled"}>${esc(T.send)}</button>`;
  } else {
    const max = q.type === "open" ? q.open?.max_chars || 80 : 100;
    d.text ??= "";
    body = `<textarea id="text" rows="2" maxlength="${max}" placeholder="${esc(T.typeHere)}">${esc(d.text)}</textarea>
      <div class="count"><span id="chars">${d.text.length}</span> / ${max}</div><button class="main" id="send">${esc(T.send)}</button>`;
  }
  app.innerHTML = `${r.practice ? `<p>${esc(T.practice)}</p>` : ""}${promptCard(r)}${body}<div class="error" id="err"></div>`;

  app.querySelectorAll(".answers .answer").forEach((b) => b.addEventListener("click", () => {
    if (kind === "multiple") {
      d.choices = d.choices.includes(b.dataset.id) ? d.choices.filter((x) => x !== b.dataset.id) : [...d.choices, b.dataset.id];
      b.classList.toggle("selected");
      b.setAttribute("aria-pressed", d.choices.includes(b.dataset.id));
      $("#send").disabled = !d.choices.length;
    } else {
      app.querySelectorAll(".answer").forEach((x) => x.classList.toggle("dim", x !== b));
      submit(r, { choice: b.dataset.id });
    }
  }));
  app.querySelectorAll("[data-move]").forEach((b) => b.addEventListener("click", () => {
    const i = +b.dataset.move, j = i + +b.dataset.dir;
    [d.order[i], d.order[j]] = [d.order[j], d.order[i]];
    question(r);
  }));
  const num = $("#num");
  const readNumber = () => {
    d.value = num.value === "" ? "" : Number(num.value);
    if ($("#val")) $("#val").textContent = num.value;
  };
  if (num) {
    num.addEventListener("input", readNumber);
    // A range input sanitizes its value onto the step grid anchored at min. Keep the
    // label and submitted draft in sync even before the student first moves its thumb.
    readNumber();
  }
  const text = $("#text");
  text?.addEventListener("input", () => { d.text = text.value; $("#chars").textContent = text.value.length; });
  let pad = null;
  if (kind === "sketch") {
    pad = new SketchPad($("#padbox"), { onChange: () => { d.strokes = pad.strokes; $("#send").disabled = !pad.strokes.length; } });
    pad.strokes = d.strokes || [];
    pad.pen = d.pen;
    app.querySelectorAll("[data-pen]").forEach((b) => b.addEventListener("click", () => {
      d.pen = pad.pen = +b.dataset.pen;
      app.querySelectorAll("[data-pen]").forEach((x) => {
        x.classList.toggle("on", x === b);
        x.setAttribute("aria-pressed", String(x === b));
      });
    }));
    $("#undo").addEventListener("click", () => pad.undo());
    $("#clear").addEventListener("click", () => pad.clear());
  }
  $("#send")?.addEventListener("click", () => {
    if (kind === "multiple") submit(r, { choices: d.choices });
    else if (kind === "order") submit(r, { order: d.order });
    else if (kind === "numeric") submit(r, { value: Number(d.value) });
    else if (kind === "sketch") {
      const strokes = pad.encode();
      if (strokes) submit(r, { strokes });
      else $("#err").textContent = T.tooMuch;
    } else submit(r, { text: d.text });
  });
}

async function submit(r, answer) {
  app.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  try {
    await client.send({ t: "answer", round: r.id, answer });
    if (navigator.vibrate) navigator.vibrate(30);
  } catch (err) {
    const el = $("#err");
    if (el) el.textContent = err.message;
    app.querySelectorAll("button").forEach((b) => { b.disabled = false; });
    app.querySelectorAll(".answer").forEach((x) => x.classList.remove("dim"));
  }
}

// an answer as the player gave it: the pictures of the chosen answers, a number, a text, a sketch
function mine(q, a) {
  if (!a) return "";
  if (a.strokes) return `<div class="card mine-sketch">${sketchSVG(a.strokes)}</div>`;
  const ids = a.choice ? [a.choice] : a.choices || a.order;
  if (ids) {
    const byId = Object.fromEntries((q.answers || []).map((x) => [x.id, x]));
    const scale = answerScale(q, pageWidth() - 70);
    return `<div class="mine-list">${ids.map((id, i) => `<div class="mine-row">${a.order ? `<b>${i + 1}.</b>` : ""}
      <div class="answer small" style="--c:${color(byId[id].shape)}">${answerFace(byId[id], scale)}</div></div>`).join("")}</div>`;
  }
  const text = a.value !== undefined ? `${a.value}${q.numeric?.unit ? ` ${q.numeric.unit}` : ""}` : a.text;
  return `<div class="card mine-text">${esc(text)}</div>`;
}

// the right answer after the reveal, in the same form
function right(q, keys) {
  if (keys.correct) return mine(q, { choices: keys.correct });
  if (keys.order) return mine(q, { order: keys.order });
  if (keys.answer !== undefined && keys.answer !== null) {
    return mine(q, { value: `${keys.answer}${keys.tolerance ? ` ± ${keys.tolerance}` : ""}` });
  }
  if (keys.accept?.length) return mine(q, { text: keys.accept[0] });
  return "";
}

function waiting(r) {
  const answered = !!r.answer;
  app.innerHTML = `${promptCard(r)}<h2>${esc(answered ? T.sent : T.timesUp)}</h2>
    ${answered ? mine(r.question, r.answer) : `<p>${esc(T.noAnswer)}</p>`}
    <div class="center"><div class="spinner"></div><p>${esc(r.phase === "open" ? T.waitOthers : T.waitReveal)}</p></div>`;
}

function result(r) {
  const res = r.result || {};
  const q = r.question;
  let cls, title;
  if (res.correct === true) { cls = "ok"; title = T.correct; }
  else if (res.correct === false && res.credit > 0) { cls = "ok"; title = T.partly; }
  else if (res.correct === false) { cls = "no"; title = r.answer ? T.wrong : T.noAnswer; }
  else { cls = "none"; title = r.answer ? T.thanks : T.noAnswer; }
  const pts = res.points + res.bonus;
  const me = state.me;
  const solution = res.correct === true ? "" : right(q, r.keys || {});
  app.innerHTML = `<div class="result ${cls}"><h1>${esc(title)}</h1>
      ${pts ? `<div><span class="pill">+${pts} ${esc(T.points)}</span></div>` : ""}
      ${res.bonus ? `<p>${esc(T.bonus)} +${res.bonus} · ${esc(T.streak)} ${me.streak}</p>` : ""}
      ${me.rank ? `<p>${esc(T.rank(me.rank, me.players))}</p>` : ""}</div>
    ${r.answer ? mine(q, r.answer) : ""}
    ${solution ? `<h2>${esc(T.answerWas)}</h2>${solution}` : ""}`;
  if (navigator.vibrate && res.correct === true) navigator.vibrate([40, 60, 40]);
}

function finished() {
  const me = state.me;
  const top = (state.standings || []).map((p) => `<div><span>${p.rank}. ${esc(p.nickname)}</span><span>${p.score}</span></div>`).join("");
  app.innerHTML = `<div class="center"><h1>${esc(T.finished)}</h1>
    ${me.rank ? `<p>${esc(T.yourRank)}</p><div class="big">${me.rank}</div><p>${esc(T.rank(me.rank, me.players))} · ${me.score} ${esc(T.points)}</p>` : ""}
    <div class="standings">${top}</div></div>`;
}
