// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The live views over a slide (docs/design.md, sections 5.2 and 7): what the projector shows
// on join, question, reveal, answer, leaderboard and podium slides (nothing on a quiz's
// reading slide, the question alone before the lecturer's click). The same code runs in
// the host console's slide host and, later, in the PowerPoint add-in: a stage shows one
// slide - its picture, and the live parts positioned by the slide's rectangles (fractions of
// the slide, deck.json) - from the host's view of the game (server/game.py, host_view).
//
//   const stage = new Stage(element, {send, controls: true});
//   stage.show(slide, deck, hostState, () => client.now());
//
// texstage draws the slide itself (a page of the stage PDF): {surface} is an object with an
// `element` that takes the picture's place and show(slide), called with the slide to draw -
// after the swap below. The stage's ratio is the CSS variable --tq-aspect (default 16 / 9).
//
// texstage M6 adds slides of its own, drawn here on a blank page (pdfview.js shownSlide): a
// poll of the game ({overlay: "poll", quiz}: its question and answers as typed, formulas by
// KaTeX - text.js -, then its results) and sketches the lecturer picked ({overlay:
// "sketches", quiz, players}; their strokes come through `sketches`, a function the page
// gives: (quiz, players) => Promise of [{n, player, strokes}]); and over any slide the
// audience's question the lecturer shows (stage.question).
//
// texstage's content types other than the quiz (docs/content-types-design.md, section 6.3) come
// with a renderer each, given as `types` - {video: VideoBox} (stage/video.js) - with `host`, what
// the window gives them (its role, send, the media files' addresses): see showTypes below.
//
// The live views speak the deck's language (deck.json's "language", the build's from babel's; their
// texts are i18n's "live" - German for a German deck, else English -, and so do the types' boxes,
// which get it; `labels`, a window's own texts, go over them.
//
// Nothing here knows the right answer before the server reveals it: the host view has no
// keys until then.

import { CATALOGS, texts } from "../i18n/i18n.js";
import { color, shapeSVG } from "./shapes.js";
import { sketchSVG } from "./sketch.js";
import { textHTML } from "./text.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const pct = (v) => `${(v * 100).toFixed(3)}%`;
const box = (r) => `left:${pct(r.x)};top:${pct(r.y)};width:${pct(r.w)};height:${pct(r.h)}`;
const PANEL = { x: 0.6, y: 0.5, w: 0.38, h: 0.44 };               // results of quizzes without a live area
const SIDE_PANEL = { x: 0.715, y: 0.56, w: 0.27, h: 0.36 };       // results over the author's answer frame
const AREA = { x: 0.0625, y: 0.16, w: 0.875, h: 0.76 };          // join and podium without a live area

export class Stage {
  constructor(el, { send = null, controls = false, labels = {}, surface = null, sketches = null, types = null,
    host = {} } = {}) {
    this.el = el;
    this.send = send;
    this.given = labels;
    this.labels = { ...LABELS, ...labels };
    this.language = "";                    // the deck's (show), which this.labels speak
    this.surface = surface;
    this.fetchSketches = sketches;
    this.sketchCache = new Map();          // "quiz/player" -> {n, strokes}
    this.asked = new Set();                // sketches asked for and not there yet
    this.redraw = () => this.refresh();
    this.types = types || {};
    this.host = host;
    this.mounted = new Map();              // "type:item" -> its renderer, while the slide shown has its box
    el.classList.add("tq-stage");
    el.innerHTML = `${surface ? "" : '<img class="tq-slide" alt="">'}<div class="tq-live"></div>`
      + `${types ? '<div class="tq-types"></div>' : ""}${controls ? '<div class="tq-controls"></div>' : ""}`
      + `${types ? '<div class="tq-typectl"></div>' : ""}`;
    if (surface) el.prepend(surface.element);
    this.img = el.querySelector("img.tq-slide");
    this.live = el.querySelector(".tq-live");
    this.controls = el.querySelector(".tq-controls");
    this.typeLayer = el.querySelector(".tq-types");
    this.typeControls = el.querySelector(".tq-typectl");
    this.html = "";
    this.key = "";
    this.clock = () => Date.now();
    this.controls?.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-cmd]");
      if (b && this.send) this.send({ t: b.dataset.cmd, quiz: this.slide?.quiz, ...(b.dataset.cmd === "extend" ? { seconds: 10 } : {}) });
    });
    const loop = () => {
      requestAnimationFrame(loop);                       // first: an error must not stop the clock
      try {
        this.tick();
      } finally {
        this.tickTypes();
      }
    };
    requestAnimationFrame(loop);
  }

  show(slide, deck, state, clock) {
    // A round that is not revealed (e.g. "ask again" pressed on the reveal slide) is shown
    // on its question slide: the reveal slide's picture would give the answer away, and
    // on the reading slide (the lecturer stepped back) its answers and timer would vanish.
    const round = slide?.quiz ? state?.rounds?.[slide.quiz] : null;
    if (round && round.phase !== "revealed" && ["read", "reveal", "answer", "leaderboard"].includes(slide.phase)) {
      slide = deck.slides.find((s) => s.quiz === slide.quiz && s.phase === "question") || slide;
    }
    this.slide = slide;
    this.deck = deck;
    this.state = state;
    if (clock) this.clock = clock;
    const language = deck?.language || "";
    if (language !== this.language) {      // (the add-in shows its slide before its deck has come)
      this.language = language;
      this.labels = { ...liveLabels(language), ...this.given };
    }
    if (this.surface) {
      this.surface.show(slide);
    } else {
      const src = slide ? `${state?.session?.base ?? `/bundle/${deck.bundle}/`}${slide.image}` : "";
      if (this.img.getAttribute("src") !== src) this.img.src = src;
    }
    const html = slide && state ? this.render() + this.questionCard() : "";
    if (html !== this.html) {
      this.html = html;
      this.live.innerHTML = html;
      this.animate();
    }
    if (this.controls) this.controls.innerHTML = slide && state ? this.renderControls() : "";
    this.showTypes();
    this.tick();
  }

  refresh() {
    // again with what it has (a formula's KaTeX or a sketch arrived)
    if (this.deck) this.show(this.slide, this.deck, this.state);
  }

  round() {
    // no state yet: the add-in shows its slide before it connects (found in M4)
    return this.slide?.quiz ? this.state?.rounds?.[this.slide.quiz] : null;
  }

  quizOf(id) {
    // a quiz of the deck, or a poll of the game (M6)
    return this.deck?.quizzes?.[id] || this.state?.polls?.[id];
  }

  // ------------------------------------------------------------------ views
  render() {
    const { slide } = this;
    if (slide.overlay === "poll") return this.pollSlide();
    if (slide.overlay === "sketches") return this.sketchBoard();
    switch (slide.phase) {
      case "join": return this.lobby();
      case "read": return "";                 // the question alone: nothing live until the click
      case "question": return this.question(false);
      case "reveal": return this.question(true);
      case "answer": return this.answerPanel();
      case "leaderboard": return this.leaderboard();
      case "podium": return this.podium();
      default: return "";
    }
  }

  lobby() {
    const s = this.state.session;
    const players = this.state.players || [];
    const area = this.slide.rects?.live || AREA;
    const url = (s.join || "").replace(/\?pin=.*/, "").replace(/^https?:\/\//, "");
    const names = players.slice(-40).map((p) => `<span class="tq-chip">${esc(p.nickname)}</span>`).join("");
    return `<div class="tq-lobby" style="${box(area)}">
      <div class="tq-lobby-top">
        <div class="tq-lobby-text"><div class="tq-small">${esc(this.labels.joinAt)}</div><div class="tq-url">${esc(url)}</div>
          <div class="tq-small">${esc(this.labels.pin)}</div><div class="tq-pin">${esc(s.pin.slice(0, 3))}&thinsp;${esc(s.pin.slice(3))}</div></div>
        <img class="tq-qr" src="${esc(s.qr)}" alt="${esc(this.labels.qr)}">
      </div>
      <div class="tq-count">${players.length} ${esc(players.length === 1 ? this.labels.player : this.labels.players)}</div>
      <div class="tq-names">${names}</div>
    </div>`;
  }

  timer(round) {
    const r = this.slide.rects.timer;
    return `<div class="tq-timer" style="${box(r)}" data-role="timer">
      <svg viewBox="0 0 100 100"><circle class="tq-ring-bg" cx="50" cy="50" r="44"/><circle class="tq-ring" cx="50" cy="50" r="44"/></svg>
      <div class="tq-timer-text"></div><div class="tq-timer-sub"></div></div>`;
  }

  question(revealing) {
    const round = this.round();
    if (!round) return "";
    const q = this.quizOf(this.slide.quiz);
    const parts = [];
    const open = round.phase === "get-ready" || round.phase === "open";
    const r = this.slide.rects || {};
    const total = round.answered + round.awaiting;
    const answered = round.results?.answered ?? round.answered;
    const status = open
      ? `${round.answered} / ${total} ${this.answerWord(total)}`
      : this.correctLine(round) || `${answered} ${this.answerWord(answered)}`;
    if (r.timer) {
      // a quiz frame of its own: the timer in its square, the count below it; once
      // closed, the count in the square (the explanation may sit below)
      if (open) parts.push(this.timer(round));
      const where = open ? `top:${pct(r.timer.y + r.timer.h + 0.01)}`
        : `top:${pct(r.timer.y + r.timer.h / 2)};transform:translate(-100%,-50%)`;
      parts.push(`<div class="tq-status" style="left:${pct(r.timer.x + r.timer.w)};${where}">${esc(status)}</div>`);
    } else {
      // a quiz inside the author's frame: no free corner, so a pill on the footline
      parts.push(`<div class="tq-pill" ${open ? 'data-role="timer"' : ""}>${open ? `<span class="tq-pill-ring">
        <svg viewBox="0 0 100 100"><circle class="tq-ring-bg" cx="50" cy="50" r="44"/><circle class="tq-ring" cx="50" cy="50" r="44"/></svg>
        <span class="tq-timer-text"></span></span><span class="tq-timer-sub"></span>` : ""}<span>${esc(status)}</span></div>`);
    }
    if (!open && round.results) {
      if (r.cells && ["single", "truefalse", "multiple", "poll"].includes(q.type)) parts.push(this.cellBars(round, q));
      else if (q.type === "order" && round.phase === "revealed" && r.cells) parts.push(this.orderShares(round, q));
      else if (["numeric", "text", "open"].includes(q.type) && !(revealing && q.type === "numeric")) {
        // (a number's answer slide: its explanation sits where the distribution would go; the
        // question slide showed the distribution when the time was up)
        const area = r.live || PANEL;
        parts.push(`<div class="tq-results ${r.live ? "" : "tq-panel"}" style="${box(area)}">${this.resultsChart(round, q)}</div>`);
      }
    }
    if (round.phase === "closed" && !revealing) {
      parts.push(`<div class="tq-banner">${esc(round.closed_by === "all" ? this.labels.allAnswered : this.labels.timesUp)}</div>`);
    }
    return parts.join("");
  }

  correctLine(round) {
    const res = round.results;
    if (round.phase !== "revealed" || !res || res.correct === undefined) return "";
    return `${res.correct} / ${res.answered} ${this.labels.correct}`;
  }

  answerWord(n) {
    return n === 1 ? this.labels.answer : this.labels.answers;        // 1 answer, 0 / 1 answer, 3 answers
  }

  cellBars(round, q) {
    const counts = round.results.counts || {};
    const max = Math.max(1, ...Object.values(counts));
    const total = Math.max(1, round.results.answered);
    const right = new Set(round.phase === "revealed" ? round.keys?.correct || [] : []);
    return (q.answers || []).map((a) => {
      const cell = this.slide.rects.cells?.[a.id];
      if (!cell) return "";
      const n = counts[a.id] || 0;
      return `<div class="tq-cell ${right.has(a.id) ? "tq-right" : ""}" style="${box(cell)}">
        <div class="tq-bar" style="width:${pct(n / max)};background:${color(a.shape)}"></div>
        <div class="tq-badge" style="border-color:${color(a.shape)}">${n}<span>${Math.round((100 * n) / total)}%</span></div></div>`;
    }).join("");
  }

  orderShares(round, q) {
    const order = round.keys?.order || [];
    const total = Math.max(1, round.results.answered);
    return order.map((id, i) => {
      const cell = this.slide.rects.cells?.[id];
      if (!cell) return "";
      const n = round.results.positions?.[id]?.[i] || 0;
      const a = (q.answers || []).find((x) => x.id === id);
      return `<div class="tq-cell" style="${box(cell)}"><div class="tq-bar" style="width:${pct(n / total)};background:${color(a?.shape || 1)}"></div>
        <div class="tq-badge">${Math.round((100 * n) / total)}%<span>${esc(this.labels.inPlace)}</span></div></div>`;
    }).join("");
  }

  resultsChart(round, q) {
    const res = round.results;
    if (q.type === "numeric") return histogram(res.values || [], q.numeric || {}, round.phase === "revealed" ? round.keys : null);
    const groups = res.groups || [];
    if (!groups.length) return `<div class="tq-empty">${esc(this.labels.noAnswers)}</div>`;
    if (q.type === "open" && q.open?.display === "list") {
      return `<ol class="tq-list">${groups.slice(0, 12).map((g) => `<li>${esc(g.text)}<b>${g.count}</b></li>`).join("")}</ol>`;
    }
    const max = Math.max(...groups.map((g) => g.count));
    const words = groups.slice(0, 40).map((g, i) => {
      const size = 2.4 + 6 * Math.sqrt(g.count / max);          // readable from the back row
      const cls = g.correct === true ? "tq-ok" : g.correct === false ? "tq-no" : "";
      return `<span class="${cls}" style="font-size:${size.toFixed(2)}cqh;color:${cls ? "" : color((i % 6) + 1)}">${esc(g.text)}</span>`;
    });
    return `<div class="tq-cloud">${words.join(" ")}</div>`;
  }

  answerPanel() {
    const round = this.round();
    if (!round || !round.results) return "";
    const q = this.quizOf(this.slide.quiz);
    let body;
    if (["single", "truefalse", "multiple", "poll"].includes(q.type)) {
      const counts = round.results.counts || {};
      const max = Math.max(1, ...Object.values(counts));
      const right = new Set(round.keys?.correct || []);
      body = (q.answers || []).map((a) => `<div class="tq-row ${right.has(a.id) ? "tq-right" : ""}">
          <span class="tq-shape" style="background:${color(a.shape)}">${shapeSVG(a.shape)}</span><b>${a.id}</b>
          <span class="tq-rowbar"><span style="width:${pct((counts[a.id] || 0) / max)};background:${color(a.shape)}"></span></span>
          <span class="tq-n">${counts[a.id] || 0}</span>${right.has(a.id) ? '<span class="tq-check">✓</span>' : ""}</div>`).join("");
    } else if (q.type === "order") {
      const res = round.results;
      body = `<div class="tq-big">${res.correct ?? 0} / ${res.answered}</div><div class="tq-small">${esc(this.labels.rightOrder)}</div>`;
    } else {
      body = `<div class="tq-chart">${this.resultsChart(round, q)}</div>`;
    }
    const line = this.correctLine(round) || `${round.results.answered} ${this.answerWord(round.results.answered)}`;
    // over the author's slide: small, and it fades after a while (the mouse brings it back)
    return `<div class="tq-panel tq-answer" style="${box(SIDE_PANEL)}"><div class="tq-panel-title">${esc(this.labels.results)}</div>${body}<div class="tq-panel-foot">${esc(line)}</div></div>`;
  }

  leaderboard() {
    const players = (this.state.players || []).filter((p) => p.rank > 0).slice(0, 5);
    const rows = players.map((p) => {
      const was = p.prev_rank || 6;
      const move = !p.prev_rank ? "" : p.rank < p.prev_rank ? "▲" : p.rank > p.prev_rank ? "▼" : "";
      return `<div class="tq-lb-row" data-from="${Math.min(was, 6)}" data-to="${p.rank}">
        <span class="tq-lb-rank">${p.rank}</span><span class="tq-lb-name">${esc(p.nickname)}</span>
        <span class="tq-lb-move ${move === "▲" ? "up" : "down"}">${move}</span><span class="tq-lb-score">${p.score}</span></div>`;
    }).join("");
    return `<div class="tq-dim"></div><div class="tq-lb"><div class="tq-lb-title">${esc(this.labels.leaderboard)}</div>
      <div class="tq-lb-rows" style="height:${players.length * 13}cqh">${rows || `<div class="tq-empty">${esc(this.labels.noScores)}</div>`}</div></div>`;
  }

  podium() {
    const area = this.slide.rects?.live || AREA;
    const top = (this.state.players || []).filter((p) => p.rank > 0).slice(0, 3);
    const order = [top[1], top[0], top[2]];
    const cols = order.map((p, i) => {
      if (!p) return `<div class="tq-pod-col"></div>`;
      const place = [2, 1, 3][i];
      return `<div class="tq-pod-col"><div class="tq-pod-name">${esc(p.nickname)}</div><div class="tq-pod-score">${p.score}</div>
        <div class="tq-pod-block tq-pod-${place}"><span>${place}</span></div></div>`;
    }).join("");
    return `<div class="tq-podium" style="${box(area)}">${cols}</div>`;
  }

  // ------------------------------------------------------------------ texstage M6
  aspect() {
    return this.el.clientWidth && this.el.clientHeight ? this.el.clientWidth / this.el.clientHeight : 16 / 9;
  }

  pollSlide() {
    // a poll of the game on a page of its own: its question and answers as typed, the timer
    // and the count; the results as soon as it closes (in the answers' boxes, or a word cloud
    // or list below the question)
    const q = this.quizOf(this.slide.quiz);
    if (!q) return "";
    const rects = pollRects(q, this.aspect());
    this.slide.rects = rects;                    // what question() and cellBars() draw into
    const answers = (q.answers || []).map((a) => `<div class="tq-poll-cell" style="${box(rects.cells[a.id])};--c:${color(a.shape)}">
        <span class="tq-poll-shape">${shapeSVG(a.shape)}</span><b>${esc(a.id)}</b>
        <span class="tq-poll-text">${textHTML(a.text, this.redraw)}</span></div>`).join("");
    const s = this.state.session;
    const url = (s.join || "").replace(/\?pin=.*/, "").replace(/^https?:\/\//, "");
    const sketch = q.type === "sketch" ? `<div class="tq-poll-note" style="${box(rects.live)}">${esc(this.labels.sketchHint)}</div>` : "";
    return `<div class="tq-poll-title" style="${box(rects.title)}">${esc(q.title)}</div>
      <div class="tq-poll-prompt" style="${box(rects.prompt)}">${textHTML(q.prompt?.text || "", this.redraw)}</div>
      ${answers}${sketch}${this.question(true)}
      <div class="tq-poll-join" style="${box(rects.join)}">${esc(this.labels.joinAt)} ${esc(url)} · ${esc(this.labels.pin)} ${esc(s.pin)}</div>`;
  }

  sketchBoard() {
    // the sketches the lecturer picked, in a grid, numbered as in the gallery
    const { quiz, players = [] } = this.slide;
    const q = this.quizOf(quiz);
    const missing = players.filter((p) => !this.sketchCache.has(`${quiz}/${p}`));
    if (missing.length && this.fetchSketches) {
      const key = `${quiz}/${missing.join(",")}`;
      if (!this.asked.has(key)) {
        this.asked.add(key);
        this.fetchSketches(quiz, missing).then((found) => {
          for (const x of found || []) this.sketchCache.set(`${quiz}/${x.player}`, x);
          this.refresh();
        }).catch(() => {}).finally(() => this.asked.delete(key));
      }
    }
    const n = players.length;
    const cols = n <= 1 ? 1 : n <= 4 ? 2 : n <= 9 ? 3 : 4;
    const rows = Math.max(1, Math.ceil(n / cols));
    const top = 0.14;
    const area = { x: 0.03, y: top, w: 0.94, h: 0.97 - top };
    const gap = 0.012;
    // tiles of 4:3, as large as the grid allows
    const aspect = this.aspect();
    let w = (area.w - (cols - 1) * gap) / cols;
    let h = (w * aspect) / (4 / 3);
    if (rows * h + (rows - 1) * gap * aspect > area.h) {
      h = (area.h - (rows - 1) * gap * aspect) / rows;
      w = (h * (4 / 3)) / aspect;
    }
    const x0 = area.x + (area.w - (cols * w + (cols - 1) * gap)) / 2;
    const y0 = area.y + (area.h - (rows * h + (rows - 1) * gap * aspect)) / 2;
    const tiles = players.map((p, i) => {
      const x = this.sketchCache.get(`${quiz}/${p}`);
      const r = { x: x0 + (i % cols) * (w + gap), y: y0 + Math.floor(i / cols) * (h + gap * aspect), w, h };
      return `<div class="tq-sketch-tile" style="${box(r)}">${x ? sketchSVG(x.strokes, `#${x.n}`) : ""}
        <span class="tq-sketch-n">${x ? `#${x.n}` : "…"}</span></div>`;
    }).join("");
    // the question: a poll's text, or the picture of a deck's quiz the phones show
    const ask = q?.prompt?.text !== undefined ? textHTML(q.prompt.text, this.redraw)
      : q?.prompt?.image ? `<img class="tq-sketch-img" src="${esc(`${this.state.session.base}${q.prompt.image}`)}" alt="">`
        : esc(q?.title || "");
    return `<div class="tq-poll-prompt tq-sketch-prompt" style="${box({ x: 0.04, y: 0.025, w: 0.92, h: top - 0.04 })}">${ask}</div>${tiles}`;
  }

  questionCard() {
    // a question from the audience, as a card over the slide
    const shown = this.state?.stage?.question;
    if (!shown) return "";
    return `<div class="tq-qa-card"><div class="tq-qa-label">${esc(this.labels.audience)}</div>
      <div class="tq-qa-text">${textHTML(shown.text, this.redraw)}</div>
      ${shown.votes ? `<div class="tq-qa-votes">▲ ${shown.votes}</div>` : ""}</div>`;
  }

  renderControls() {
    const round = this.round();
    if (!round || !["question", "reveal", "answer"].includes(this.slide.phase)) return "";
    const b = (cmd, label, title) => `<button data-cmd="${cmd}" title="${esc(title)}">${label}</button>`;
    if (round.phase === "get-ready" || round.phase === "open") {
      return (round.paused ? b("continue", "▶", this.labels.continue) : b("pause", "⏸", this.labels.pause))
        + b("extend", "+10 s", this.labels.extend) + b("skip", "⏭", this.labels.skip);
    }
    if (round.phase === "closed") return b("reveal", "✓", this.labels.reveal);
    if (round.phase === "revealed") return b("again", "↻", this.labels.again);
    return "";
  }

  // ------------------------------------------------------------------ texstage's content types
  // A type's renderer owns its elements: made when a slide brings its box, kept while the next
  // slides show the same item (the steps of a frame: a video plays on), moved if its box moves,
  // removed when it goes - the swap of the live layer's HTML above never touches them. Its
  // elements lie in .tq-types, under the ink; its buttons in .tq-typectl, over the pen's input.
  //   new types[type]({id, item, layer, controls, host, clock, language}): item is deck.json's,
  //   language the deck's (its texts')
  //   .place(rects)  .update(state)  .tick()  .key(key) -> taken?  .destroy()
  showTypes() {
    if (!this.typeLayer) return;
    const { slide, deck, state } = this;
    const boxes = slide && state && !slide.overlay ? slide.live || [] : [];
    const keep = new Set();
    for (const b of boxes) {
      const item = deck.items?.[b.type]?.[b.item];
      const key = `${b.type}:${b.item}`;
      if (!this.types[b.type] || !item || keep.has(key)) continue;
      keep.add(key);
      let r = this.mounted.get(key);
      if (!r) {
        r = new this.types[b.type]({ id: b.item, item, layer: this.typeLayer, controls: this.typeControls,
          host: this.host, clock: () => this.clock(), language: this.language });
        this.mounted.set(key, r);
      }
      r.place(b.rects || {});
      r.update(state);
    }
    for (const [key, r] of this.mounted) {
      if (!keep.has(key)) {
        this.mounted.delete(key);
        r.destroy();
      }
    }
  }

  tickTypes() {
    if (!this.mounted.size) return;
    if (!this.el.isConnected) {                 // the window made a new stage (another deck): these go
      for (const r of this.mounted.values()) r.destroy();
      this.mounted.clear();
      return;
    }
    for (const r of this.mounted.values()) r.tick();
  }

  typeKey(k) {
    // a key for the content on the slide (a video's K and J): whether one took it
    for (const r of this.mounted.values()) if (r.key(k)) return true;
    return false;
  }

  // ------------------------------------------------------------------ motion
  tick() {
    const el = this.live.querySelector('[data-role="timer"]');
    const round = this.round();
    if (!el || !round) return;
    const now = this.clock();
    let text, sub = "", share;
    if (round.phase === "get-ready") {
      const left = Math.max(0, round.opens - now);
      text = Math.ceil(left / 1000) || "";
      sub = this.labels.getReady;
      share = 1;
      el.classList.add("tq-ready");
    } else {
      el.classList.remove("tq-ready");
      const left = round.paused ? round.remaining : Math.max(0, round.deadline - now);
      text = round.paused ? "⏸" : Math.ceil(left / 1000);
      share = round.limit ? left / round.limit : 0;
      el.classList.toggle("tq-hurry", !round.paused && left < 5000);
    }
    el.querySelector(".tq-timer-text").textContent = text;
    el.querySelector(".tq-timer-sub").textContent = sub;
    el.querySelector(".tq-ring").style.strokeDashoffset = String(276.46 * (1 - share));
  }

  animate() {
    // leaderboard: rows start at their previous rank and move to the new one
    const rows = this.live.querySelectorAll(".tq-lb-row");
    rows.forEach((row) => { row.style.transform = `translateY(${(row.dataset.from - 1) * 13}cqh)`; });
    if (!rows.length) return;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      rows.forEach((row) => {
        row.classList.add("tq-moving");
        row.style.transform = `translateY(${(row.dataset.to - 1) * 13}cqh)`;
      });
    }));
  }
}

// the layout of a poll's page (fractions of the slide): title, question, the timer's square,
// the answers' boxes - side by side for yes/no and the scale, two or three columns for A-F -,
// below them the room for a word cloud or list, and the join line at the bottom
function pollRects(q, aspect) {
  const timer = { x: 0.86, y: 0.06, w: 0.1, h: 0.1 * aspect };
  const rects = { title: { x: 0.05, y: 0.05, w: 0.7, h: 0.06 }, prompt: { x: 0.05, y: 0.12, w: 0.76, h: 0.24 },
    timer, live: { x: 0.05, y: 0.4, w: 0.9, h: 0.5 }, join: { x: 0.05, y: 0.93, w: 0.9, h: 0.05 } };
  const answers = q.answers || [];
  if (answers.length) {
    const n = answers.length;
    const cols = q.adhoc === "scale" ? n : n <= 4 ? 2 : 3;
    const rows = Math.ceil(n / cols);
    const gap = 0.02;
    const area = { x: 0.05, y: 0.42, w: 0.9, h: 0.46 };
    const w = (area.w - (cols - 1) * gap) / cols;
    const h = Math.min(0.19, (area.h - (rows - 1) * gap * aspect) / rows);
    rects.cells = Object.fromEntries(answers.map((a, i) => [a.id, {
      x: area.x + (i % cols) * (w + gap), y: area.y + Math.floor(i / cols) * (h + gap * aspect), w, h }]));
  }
  return rects;
}

function histogram(values, range, keys) {
  if (!values.length) return `<div class="tq-empty">–</div>`;
  let lo = range.min ?? Math.min(...values);
  let hi = range.max ?? Math.max(...values);
  let step = range.step || 1;
  if (hi - lo > 30 * step) step = (hi - lo) / 20;
  const bins = [];
  for (let x = lo; x <= hi + 1e-9 && bins.length < 40; x += step) bins.push({ x, n: 0 });
  if (!bins.length) bins.push({ x: lo, n: 0 });
  for (const v of values) {
    const i = Math.min(bins.length - 1, Math.max(0, Math.round((v - lo) / step)));
    bins[i].n += 1;
  }
  const max = Math.max(...bins.map((b) => b.n));
  const ok = (x) => keys && keys.answer !== undefined && keys.answer !== null && Math.abs(x - keys.answer) <= (keys.tolerance || 0) + step / 2 - 1e-9;
  const label = (x) => (Number.isInteger(x) ? x : x.toFixed(1));
  const every = Math.ceil(bins.length / 12);
  return `<div class="tq-hist">${bins.map((b, i) => `<div class="tq-hcol ${ok(b.x) ? "tq-ok" : ""}">
    <span class="tq-hn">${b.n || ""}</span><span class="tq-hbar" style="height:${pct(b.n / max)}"></span>
    <span class="tq-hx">${i % every === 0 ? label(b.x) : ""}</span></div>`).join("")}</div>`;
}

// The live views' texts (i18n's "live"): English's, and the other languages' by BCP 47 tag
// (deck.json's "language")
export const LABELS = CATALOGS.en.live;
export const LANGUAGES = Object.fromEntries(Object.entries(CATALOGS).filter(([tag]) => tag !== "en")
  .map(([tag, catalog]) => [tag, catalog.live]));

// the texts for a deck's language: its own, English for any other - and for a deck built before
// 2026-10-24, which names none
export function liveLabels(language) {
  return { ...texts(language).live };
}
