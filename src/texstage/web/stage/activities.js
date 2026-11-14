// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A live activity in the windows, as the activity framework has it (docs/architecture/activity-framework-
// design.md, 13; the plan of F2, 4.5) - for a server run with --activities core (the deck's view says so:
// activities "core"). Three parts:
//
//   StepBox     the box on the slide, the same in the presenter and the projector window: the projector's
//               picture of the step (activity.view, window "display") - the core's views: bars for groups
//               and a tally, the crowd graph with today's layout (activity.js) -, a group's detail drawn by
//               the kind's box.js where it has one, else as a table; nothing of the reference before the
//               reveal, nothing the projector holds back. In the presenter window it takes the controls'
//               keys for its activity (KEYS)
//   StepAgent   the lead window: the first presenter window that sends a crowd graph's positions
//               (activity.layout) lays it out for every window, 15 s and again with each it sends; another
//               is told so (lead: false, with a layout or a picture), follows the positions in the picture -
//               its own are dropped - and lays out again once a picture says nobody leads (lead: null)
//   panel       openStepPanel(env): the panel, the same for every kind - the phase and the time, the
//               counts, the controls (open, close, pause, resume, the time, reveal, reset), the groups or
//               the graph's terms with their buttons (activity.moderate), the last acts with Undo; the
//               lecturer's picture, whatever the projector holds back
//
// What a student typed is shown as text, never as HTML. A kind's box.js gives HTML, put in as it comes: the
// windows trust a kind's code as the server trusts its Python - and the kind escapes what it puts in, for
// a group's detail carries what students' queries gave (the design's 7.3).

import { ActivityBox, resultTable } from "./activity.js";
import { texts } from "../i18n/i18n.js";
import { clock, numberShown, timeLeft } from "../play/activities.js";
import { textHTML } from "../shared/text.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const FETCH_MS = 500;
const LAYOUT_MS = 500;
const SEVERAL = String.fromCharCode(10);      // a tally's choice of several: the options' texts, a line each (kind.py)
const DENSE = 8;                              // more rows than this: the box draws them smaller (26 options fit)
const SHORT = 80;                             // a reference without a result of its own this long, one line: a line

export function tallyText(text) {
  // a tally's label or reference as a line: a choice of several with " + " between its options
  return String(text ?? "").split(SEVERAL).join(" + ");
}

export function shownText(input, item, language) {
  // an entry's input as a line of text: its text - without the empty lines in front, where comments were
  // that the kind took out (the plan of F2, 4.7) -, its fields, its choice by the options' texts (the item's),
  // its number in the deck's language
  if (!input) return "";
  if (input.choice) return input.choice.map((n) => item?.options?.[n] ?? String(n)).join(" + ");
  if (input.number !== undefined && input.number !== null) return numberShown(input.number, language);
  return input.fields ? input.fields.join(" · ") : String(input.text ?? "").replace(/^(?:[ \t]*\r?\n)+/, "");
}

export function groupLabel(g, words, item, language, status = () => null) {
  // a group's short name: a tally's choice (its label), its result ("11 rows", "yes"), else what went wrong -
  // in the kind's own word where it has one (status: kinds.js, "<kind>:invalid" - an answer is not taken)
  if (g.status !== "ok") return status(g.status) || words.status2[g.status] || g.status;
  if (g.label) return tallyText(g.label);
  const d = g.detail || {};
  if (d.kind === "ask") return d.boolean ? words.yes : words.no;
  if (typeof d.count === "number") return d.kind === "graph" ? words.triples(d.count) : words.rows(d.count);
  return shownText(g.example, item, language) || words.result;
}

export const BINS = 12;              // a histogram's bars, at most: one per number while there are no more

function quantile(numbers, total, q) {
  // the number below which a share q of the students' numbers lies (numbers in order: [x, students, ...])
  let seen = 0;
  for (const [x, n] of numbers) {
    seen += n;
    if (seen >= q * total) return x;
  }
  return numbers[numbers.length - 1][0];
}

export function histogram(numbers, most = BINS) {
  // a number step's histogram (the picture's numbers: [[number, students, verdict?], ...], in order) - bars
  // {from, to, n, right, out?}: from === to, one number; right, a number in it was judged right (the server's
  // verdicts: after the reveal). A bar per number while there are at most `most`; else bars of equal width
  // over the class's range - and where numbers lie far out, beyond three times the spread of the middle half
  // of the students from it (the middle 80 %'s where half of them gave one number), a bar at each end takes
  // them (out: "below", "above"): a joke or two do not squeeze the rest into one bar, in a small class too
  if (!numbers?.length) return [];
  const bar = (part) => ({ from: part[0][0], to: part[part.length - 1][0], n: part.reduce((s, x) => s + x[1], 0),
    right: part.some((x) => x[2] === "correct") });
  if (numbers.length <= most) return numbers.map((x) => bar([x]));
  const total = numbers.reduce((s, x) => s + x[1], 0);
  const q1 = quantile(numbers, total, 0.25), q3 = quantile(numbers, total, 0.75);
  const spread = q3 - q1 || quantile(numbers, total, 0.9) - quantile(numbers, total, 0.1) || Math.abs(q1) / 10 || 1;
  const low = q1 - 3 * spread, high = q3 + 3 * spread;
  const below = numbers.filter(([x]) => x < low), above = numbers.filter(([x]) => x > high);
  const middle = numbers.filter(([x]) => x >= low && x <= high);
  const room = most - (below.length ? 1 : 0) - (above.length ? 1 : 0);
  let bars;
  if (middle.length <= room) bars = middle.map((x) => bar([x]));
  else {
    const lo = middle[0][0], hi = middle[middle.length - 1][0], width = (hi - lo) / room;
    bars = Array.from({ length: room }, (_, i) => ({ from: lo + i * width, to: i === room - 1 ? hi : lo + (i + 1) * width,
      n: 0, right: false }));
    for (const [x, n, verdict] of middle) {
      const b = bars[Math.min(room - 1, Math.floor((x - lo) / width))];
      b.n += n;
      b.right ||= verdict === "correct";
    }
  }
  return [...(below.length ? [{ ...bar(below), out: "below" }] : []), ...bars,
    ...(above.length ? [{ ...bar(above), out: "above" }] : [])];
}

export function histogramLabels(bars, language) {
  // the bars' labels in the deck's language: a number as it is, every digit; a stretch rounded to the digits
  // its width needs; the bars of the numbers far out by their nearest one, ≤ 3 and ≥ 900
  const stretches = bars.filter((b) => b.from !== b.to && !b.out);
  const width = stretches.length ? Math.min(...stretches.map((b) => b.to - b.from)) : 0;
  const digits = width > 0 ? Math.min(12, Math.max(0, Math.ceil(-Math.log10(width)) + 1)) : 0;
  const round = (x) => numberShown(Number(x.toFixed(digits)), language);
  return bars.map((b) => b.out && b.from !== b.to ? `${b.out === "below" ? "≤" : "≥"} ${numberShown(b.out === "below" ? b.to : b.from, language)}`
    : b.from === b.to ? numberShown(b.from, language) : `${round(b.from)} – ${round(b.to)}`);
}

// The controls as keys of the presenter window (the design's 13), for the activity on the slide shown -
// the same in every language, as the window's other keys: O open (a paused step: resume), C close,
// S pause or resume, R reveal, X reset (these two ask first, as their buttons do), + 30 s more, - no time.
export const KEYS = { open: "O", resume: "O", close: "C", pause: "S", reveal: "R", reset: "X", more: "+", notime: "-" };

export function keyAct(key, phase) {
  // the control a key is for in this phase of the step, or null
  const running = phase === "open" || phase === "paused";
  const k = String(key).toLowerCase();
  if (k === "o") return phase === "paused" ? "resume" : phase === "ready" || phase === "closed" ? "open" : null;
  if (k === "c") return running ? "close" : null;
  if (k === "s") return phase === "open" ? "pause" : phase === "paused" ? "resume" : null;
  if (k === "r") return phase && phase !== "revealed" ? "reveal" : null;
  if (k === "x") return phase && phase !== "ready" ? "reset" : null;
  if (k === "+") return running ? "more" : null;
  if (k === "-") return running ? "notime" : null;
  return null;
}

export async function stepAct({ send, ask, words }, activity, act) {
  // a control, from the panel or a key: the move it sends - a reveal and a reset once asked
  if (["open", "close", "pause", "resume"].includes(act)) return send({ t: `activity.${act}`, activity });
  if (act === "more") return send({ t: "activity.time", activity, add: 30 });
  if (act === "notime") return send({ t: "activity.time", activity, stop: true });
  if (act === "reveal" && await ask(words.revealAsk, words.reveal)) return send({ t: "activity.reveal", activity });
  if (act === "reset" && await ask(words.resetAsk, words.reset)) return send({ t: "activity.reset", activity });
  return null;
}

export function detailHTML(detail, kinds, kind, words, rows = 8) {
  // a group's detail: the kind's own (box.js: group(detail, words) -> HTML), else the core's table
  if (!detail) return "";
  const own = kinds?.module(kind, "box");
  if (own?.group) {
    try {
      return String(own.group(detail, words) ?? "");
    } catch (err) {
      console.warn("texstage: the kind's box failed", err);
    }
  }
  return resultTable(detail, rows, words.__language);
}

// ------------------------------------------------------------------ the box
export class StepBox extends ActivityBox {
  constructor(opts) {
    const agent = opts.host?.agent?.forBox ? opts.host.agent.forBox(opts.id) : null;
    super({ ...opts, host: { ...opts.host, agent } });
    this.kinds = opts.host?.kinds || null;
    this.boxWords = texts(this.language).box;
  }

  fetch() {
    if (this.busy || this.gone || !this.host.read) return;
    const wait = FETCH_MS - (performance.now() - this.fetched);
    if (wait > 0) {
      this.timer ??= setTimeout(() => { this.timer = null; this.fetch(); }, wait);
      return;
    }
    this.busy = true;
    this.fetched = performance.now();
    const want = this.want;
    this.host.read({ t: "activity.view", activity: this.id, window: "display" }).then((r) => {
      this.busy = false;
      if (this.gone) return;
      this.seen = want;
      this.picture = r.picture;
      this.host.agent?.seen(r.lead);                 // (true, false, null: this window, another, nobody)
      this.draw();
      if (this.want !== this.seen) this.fetch();
    }, () => { this.busy = false; });
  }

  draw() {
    const p = this.picture;
    if (!p || this.gone) return;
    if (p.held) this.drawHeld(p);
    else if (p.kind === "graph") this.drawGraph(p);
    else if (p.numbers && (p.numbers.length || !p.groups?.length)) this.drawHistogram(p);   // (keys that are numbers)
    else this.drawGroups(p);
  }

  headLine(p) {
    // the box's first line: how many students, how many wait for their checks, how many are right (the reveal)
    const w = this.boxWords;
    return [w.students(p.students || 0), p.waiting ? w.waiting(p.waiting) : "",
      p.revealed && p.right !== undefined ? w.right(p.right) : ""].filter(Boolean).join(" · ");
  }

  drawHistogram(p) {
    // a number step: a bar per number, or per stretch of numbers (histogram) - after the reveal the bars of the
    // numbers judged right in the reference's colour (the server's verdicts: the tolerance is the kind's),
    // and with solution=show the references themselves; a group the lecturer shows, its bar marked and named
    const w = this.boxWords;
    const bars = histogram(p.numbers);
    const labels = histogramLabels(bars, this.language);
    const most = Math.max(1, ...bars.map((b) => b.n));
    const shownNumber = p.shown?.example?.number;
    const showing = (b) => typeof shownNumber === "number" && b.from <= shownNumber && shownNumber <= b.to;
    const tolerance = Number(this.item?.tolerance) || 0;
    const solution = (p.solution || []).map((r) => Number(r.text)).filter(Number.isFinite).map((r) =>
      numberShown(r, this.language) + (tolerance ? ` ± ${numberShown(tolerance, this.language)}` : "")).join(" · ");
    const lines = (solution ? `<div class="tq-solline">${esc(w.solution)}: ${esc(solution)}</div>` : "") + (p.shown
      ? `<div class="tq-solline tq-shownline">${esc(shownText(p.shown.example, this.item, this.language))} · ${esc(w.students(p.shown.n))}</div>` : "");
    this.el.innerHTML = `<div class="tq-hist"><div class="tq-chead">${esc(this.headLine(p))}</div>${lines}${bars.length
      ? `<div class="tq-hbars">${bars.map((b) => `<div class="tq-hbar${b.right ? " tq-ref" : ""}${showing(b) ? " tq-showing" : ""}"><b>${b.n || ""}</b><i
          style="height:${((100 * b.n) / most).toFixed(1)}%"></i></div>`).join("")}</div>
        <div class="tq-hlabels">${labels.map((l) => `<span>${esc(l)}</span>`).join("")}</div>`
      : `<div class="tq-empty">${esc(p.phase === "open" || p.phase === "paused" ? w.held.waiting : w.held.none)}</div>`}</div>`;
    this.nodes = new Map();
    this.shape = null;
  }

  key(k) {
    // the controls' keys, in the presenter window (Stage.typeKey: the slide shown has this box)
    const act = this.host.role === "presenter" && this.host.ask ? keyAct(k, this.picture?.phase) : null;
    if (!act) return false;
    stepAct({ send: this.host.send, ask: this.host.ask, words: texts(this.language).presenter.steps }, this.id, act);
    return true;
  }

  drawHeld(p) {
    // projector=hidden: nothing until the reveal; projector=count: the counts while the step runs
    const w = this.boxWords;
    this.el.innerHTML = `<div class="tq-clusters"><div class="tq-empty">${esc(p.held === "count"
      ? w.held.count(p.students || 0, p.entries || 0) : w.held.hidden)}</div></div>`;
    this.nodes = new Map();
    this.shape = null;
  }

  drawGroups(p) {
    // groups and a tally: a bar each - a choice of several by its options (the picture's options: how many
    // chose each); the deck's options with their $math$ typeset. After the reveal, references without a
    // result of their own in a line that leaves the bars to be seen, those with one in one box
    const w = { ...this.boxWords, __language: this.language };
    const kind = this.item?.kind;
    const tally = p.kind === "tally";
    const redraw = () => this.draw();
    const status = (s) => this.kinds?.status(kind, s) ?? null;
    const label = (g) => tally && g.status === "ok" ? textHTML(groupLabel(g, w, this.item, this.language), redraw)
      : esc(groupLabel(g, w, this.item, this.language, status));
    const mark = (g) => (g.reference ? " ✓" : "") + (g.verdict && p.revealed ? ` · ${w.verdict[g.verdict] || g.verdict}` : "");
    const listed = p.options ? p.options.map((o) => ({ ...o, status: "ok" })) : p.groups;
    const most = Math.max(1, ...listed.map((g) => g.n));
    const rows = listed.map((g) => `<div class="tq-cluster${g.reference ? " tq-ref" : ""}${g.status !== "ok" ? " tq-bad" : ""}">
        <span class="tq-clabel">${label(g)}${esc(mark(g))}</span>
        <span class="tq-cbar"><i style="width:${((100 * g.n) / most).toFixed(1)}%"></i></span>
        <span class="tq-cn">${g.n}</span></div>`).join("");
    const s = p.shown;
    const shown = s ? `<div class="tq-shown"><div class="tq-shownhead">${label(s)} · ${esc(w.students(s.n))}${esc(mark(s))}</div>
        <pre>${esc(shownText(s.example, this.item, this.language))}</pre>${s.status === "ok" ? detailHTML(s.detail, this.kinds, kind, w) : ""}</div>` : "";
    const refs = p.solution || [];
    const short = (r) => !r.detail && (tally || (!String(r.text).includes(SEVERAL) && String(r.text).length <= SHORT));
    const plain = refs.filter(short).map((r) => (tally ? textHTML(tallyText(r.text), redraw) : esc(r.text)));
    const line = plain.length ? `<div class="tq-solline">${esc(w.solution)}: ${plain.join(" · ")}</div>` : "";
    const results = refs.filter((r) => !short(r));                        // (a query: its text and its result in a box)
    const solution = results.length ? `<div class="tq-shown">${results.map((r) => `<div class="tq-shownhead">${esc(w.solution)}</div>
        <pre>${esc(r.text)}</pre>${r.detail ? detailHTML(r.detail, this.kinds, kind, w) : ""}`).join("")}</div>` : "";
    this.el.innerHTML = `<div class="tq-clusters${listed.length > DENSE ? " tq-dense" : ""}"><div class="tq-chead">${esc(this.headLine(p))}</div>
      ${line}${rows || `<div class="tq-empty">${esc(p.phase === "open" || p.phase === "paused" ? w.held.waiting : w.held.none)}</div>`}
      ${p.others && !p.options ? `<div class="tq-more">${esc(w.others)} · ${p.others}</div>` : ""}</div>${shown}${solution}`;
    this.nodes = new Map();
    this.shape = null;
    this.fit();
  }

  fit() {
    // many rows (tq-dense): the font made smaller till they fit in the box, whose height is the deck's
    const rows = this.el.querySelector?.(".tq-clusters.tq-dense");
    if (!rows?.clientHeight || typeof getComputedStyle !== "function") return;
    for (let i = 0; i < 4 && rows.scrollHeight > rows.clientHeight + 1; i += 1) {
      const size = parseFloat(getComputedStyle(rows).fontSize);
      rows.style.fontSize = `${(size * Math.max(0.5, (rows.clientHeight - 1) / rows.scrollHeight)).toFixed(2)}px`;
    }
  }
}

// ------------------------------------------------------------------ the lead window
export class StepAgent {
  constructor({ send, role = "presenter" }) {
    this.send = send;                  // (msg) => a promise of the server's reply
    this.role = role;                  // presenter: may lead; projector: follows
    this.boxes = new Set();
    this.others = new Set();           // the activities another window leads, as the server last said
    this.sent = new Map();             // activity -> the positions last sent (JSON)
    this.due = new Map();              // activity -> {at, text, last, timer}
  }

  forBox(id) {
    return {
      attach: (box) => this.boxes.add(box),
      detach: (box) => this.boxes.delete(box),
      leads: () => this.leads(id),
      layout: (activity, positions) => this.layout(activity, positions),
      seen: (lead) => this.seen(id, lead),
    };
  }

  seen(id, lead) {
    // what the server said with a picture: this window leads (true), another does (false), nobody (null)
    if (lead === false) this.follow(id);
    else this.others.delete(id);
  }

  follow(id) {
    // another window leads: its positions, not this window's - which are dropped, so that this window lays
    // out from the positions it is given, should it lead again
    if (!this.others.has(id)) this.sent.delete(id);
    this.others.add(id);
    for (const b of this.boxes) {
      if (b.id !== id) continue;
      b.own = new Map();
      b.sim = null;
    }
  }

  leads(id) {
    return this.role === "presenter" && !this.others.has(id);
  }

  update() {
    // (the window's state: nothing to ask - the lead comes with the positions a window sends)
  }

  layout(activity, positions) {
    const at = Object.fromEntries(positions);
    const text = JSON.stringify(at);
    if (text === this.sent.get(activity) || !this.leads(activity)) return;
    const due = this.due.get(activity) || { last: -Infinity, timer: null };
    due.at = at;
    due.text = text;
    this.due.set(activity, due);
    const go = () => {
      due.timer = null;
      due.last = performance.now();
      this.sent.set(activity, due.text);
      this.send({ t: "activity.layout", activity, at: due.at }).then((r) => {
        if (r.lead === false) {                         // another window leads: follow it
          this.follow(activity);
          for (const b of this.boxes) if (b.id === activity) b.draw();
        }
      }, () => this.sent.delete(activity));
    };
    const wait = LAYOUT_MS - (performance.now() - due.last);
    if (wait <= 0) go();
    else due.timer ??= setTimeout(go, wait);
  }

  destroy() {
    this.gone = true;
    for (const d of this.due.values()) clearTimeout(d.timer);
  }
}

// ------------------------------------------------------------------ the panel
// env: {dock(el), undock(), send(msg) -> promise, read(msg) -> promise, ask(question, yes) -> promise of a
// bool, language, kinds, items() -> deck.json's activities, state() -> the window's state, onSlide() -> the
// activity on the slide shown, now() -> the server's clock}
export function openStepPanel(env) {
  const A = texts(env.language).presenter.steps;
  const W = { ...texts(env.language).box, __language: env.language };
  const el = document.createElement("aside");
  el.className = "qapanel actpanel";
  el.innerHTML = `<div class="qahead"><h2>${esc(A.title)}</h2><select id="actpick"></select>
      <button class="secondary" id="actclose" title="${esc(A.closeTitle)}">✕</button></div>
    <div class="qabody" id="actbody"></div>`;
  env.dock(el);
  const panel = { el, chosen: null, picked: false, merging: null, seen: "", loading: false, picture: null, reply: null };

  const close = () => {
    clearInterval(panel.timer);
    el.remove();
    env.undock();
    panel.closed = true;
  };
  el.querySelector("#actclose").onclick = () => { close(); env.onClose?.(); };
  el.querySelector("#actpick").onchange = (e) => {
    panel.chosen = e.target.value;
    panel.picked = true;
    panel.seen = "";
    panel.reply = null;
    el.querySelector("#actbody").innerHTML = "";        // (no buttons of the activity before for this one)
    render();
  };

  const moderate = (msg) => env.send({ t: "activity.moderate", activity: panel.chosen, ...msg });

  el.querySelector("#actbody").addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const activity = panel.chosen;
    const act = b.dataset.act;
    const term = b.closest("[data-term]")?.dataset;
    const group = b.closest("[data-group]")?.dataset;
    if (KEYS[act]) await stepAct({ send: env.send, ask: env.ask, words: A }, activity, act);
    else if (act === "undo") env.send({ t: "activity.undo", activity, ...(b.dataset.n ? { act: Number(b.dataset.n) } : {}) });
    else if (act === "show") moderate({ act: "show", group: group.group });
    else if (act === "unshow") moderate({ act: "show" });
    else if (act === "hideg") moderate({ act: "hide", group: group.group, on: true });
    else if (act === "unhideg") moderate({ act: "hide", group: group.group, on: false });
    else if (act === "block") { if (await env.ask(A.blockAsk, A.block)) moderate({ act: "block", entry: group.entry }); }
    else if (act === "hide" || act === "unhide") moderate({ act: "hide", group: term.term, role: term.role, on: act === "hide" });
    else if (act === "approve" || act === "unapprove") moderate({ act: "approve", group: term.term, role: term.role, on: act === "approve" });
    else if (act === "unmerge") moderate({ act: "unmerge", group: term.term, role: term.role });
    else if (act === "merge") { panel.merging = { role: term.role, term: term.term }; panel.seen = ""; render(); }
    else if (act === "into") {
      const m = panel.merging;
      panel.merging = null;
      panel.seen = "";
      if (m) moderate({ act: "merge", group: m.term, role: m.role, into: term.term });
    } else if (act === "cancel") { panel.merging = null; panel.seen = ""; render(); }
  });
  el.querySelector("#actbody").addEventListener("change", (e) => {
    if (e.target.id === "actmin") moderate({ act: "min", value: Number(e.target.value) || 1 });
  });

  function render() {
    if (panel.closed) return;
    const items = env.items() || {};
    const acts = env.state()?.stage?.activity || { current: null, items: {} };
    const ids = Object.keys(items);
    const auto = [acts.current, env.onSlide(), panel.chosen, ids[0]].find((id) => id && items[id]);
    if (!panel.picked || !items[panel.chosen]) {
      if (auto !== panel.chosen) panel.seen = "";
      panel.chosen = auto;
    }
    const pick = el.querySelector("#actpick");
    if (pick.options.length !== ids.length) pick.innerHTML = ids.map((id) => `<option value="${esc(id)}">${esc(id)}</option>`).join("");
    pick.value = panel.chosen || "";
    const id = panel.chosen;
    if (!id) return;
    const st = acts.items?.[id] || { phase: "ready", version: 0 };
    const want = `${id}:${st.version}:${st.phase}:${st.epoch}:${JSON.stringify(panel.merging)}`;
    tick();
    if (want === panel.seen || panel.loading) return;
    panel.loading = true;
    env.read({ t: "activity.view", activity: id }).then((r) => {
      panel.loading = false;
      if (panel.closed) return;
      if (panel.chosen !== id) return render();          // (another was picked meanwhile: its picture)
      panel.seen = want;
      panel.reply = r;
      draw(id, items[id], st, r);
      render();                                          // (a newer version meanwhile)
    }, (err) => {
      panel.loading = false;
      console.warn("texstage: activity", err);
      if (!panel.closed && panel.chosen !== id) render();
    });
  }

  function tick() {
    // the time left, as the state told it with when it was read
    const id = panel.chosen;
    const st = env.state()?.stage?.activity?.items?.[id];
    const box = el.querySelector("[data-role=time]");
    if (!box || !st) return;
    const left = timeLeft({ phase: st.phase, time: st.time, since: st.since }, env.now());
    box.textContent = left === null ? "" : A.left(clock(left));
  }
  panel.timer = setInterval(tick, 1000);

  function draw(id, item, st, r) {
    const p = r.picture;
    const crowd = p.kind === "graph";
    const counts = [W.students(p.students || 0), A.entries(p.entries || 0), A.checked(p.checked || 0),
      p.waiting ? W.waiting(p.waiting) : "", p.unchecked ? W.unchecked(p.unchecked) : "",
      p.full ? A.full : "", p.hidden ? A.hidden(p.hidden) : ""].filter(Boolean).map(esc).join(" · ");
    const phase = p.phase;
    const running = phase === "open" || phase === "paused";
    const button = (act, label, primary = false) => `<button data-act="${act}"${primary ? ' class="primary"' : ""}${
      KEYS[act] ? ` title="${esc(label)} (${KEYS[act]})"` : ""}>${esc(label)}</button>`;     // (its key on the slide)
    const controls = [
      phase === "open" ? button("pause", A.pause) : phase === "paused" ? button("resume", A.resume, true) : "",
      running ? button("close", A.close) : phase !== "revealed" ? button("open", A.open, true) : "",
      running ? button("more", A.more) : "",
      running && st.time !== null && st.time !== undefined ? button("notime", A.noTime) : "",
      phase !== "revealed" ? button("reveal", A.reveal) : "",
      phase !== "ready" ? button("reset", A.reset) : "",
      p.acts?.length ? button("undo", A.undo) : "",                // (the last act that holds)
    ].join("");
    const notes = [r.failed ? `<p class="note bad">${esc(A.failed(r.failed))}</p>` : "",
      r.store ? `<p class="note bad">${esc(A.store(r.store.failures, r.store.error))}</p>` : "",
      crowd && r.lead ? `<p class="note">${esc(A.lead)}</p>` : ""].join("");
    const head = `<div class="acthead"><b>${esc(A.phase[phase] || phase)}</b> <span data-role="time"></span> · ${counts}
      <div class="buttons left">${controls}</div>${notes}</div>`;
    const body = crowd ? crowdPanel(p) : groupsPanel(p, item);
    el.querySelector("#actbody").innerHTML = head + body + actsList(p, item);
    tick();
  }

  function crowdPanel(p) {
    const m = panel.merging;
    const terms = p.terms || [];
    const row = (t) => {
      const into = t.into ? ` <span class="meta">→ ${esc(terms.find((o) => o.key === t.into && o.role === t.role)?.label || t.into)}</span>` : "";
      const acts = m ? (m.role === t.role && m.term !== t.key ? `<button data-act="into">${esc(A.into)}</button>` : "")
        : `${t.into ? `<button data-act="unmerge">${esc(A.unmerge)}</button>` : `<button data-act="merge">${esc(A.merge)}</button>`}
          ${t.hidden ? `<button data-act="unhide">${esc(A.unhide)}</button>` : `<button data-act="hide">${esc(A.hide)}</button>`}
          ${p.review ? (t.approved ? `<button data-act="unapprove">${esc(A.unapprove)}</button>`
            : `<button data-act="approve" class="primary">${esc(A.approve)}</button>`) : ""}`;
      return `<div class="actterm${t.hidden ? " hidden" : ""}" data-role="${esc(t.role)}" data-term="${esc(t.key)}">
        <span class="n">${t.n}</span><span class="term">${esc(t.label)}${into}</span>
        <span class="kind">${esc(t.role === "label" ? A.label : A.node)}</span><span class="acts">${acts}</span></div>`;
    };
    return `<div class="buttons left"><label>${esc(A.from)} <input id="actmin" type="number" min="1" max="1000" value="${p.min ?? 1}">
        ${esc(A.on(p.min ?? 1))}</label></div>
      ${m ? `<p class="note">${esc(A.mergeInto(m.term))} <button data-act="cancel">${esc(texts(env.language).dialog.cancel)}</button></p>` : ""}
      ${p.more ? `<p class="note">${esc(A.moreNodes(p.more))}</p>` : ""}
      ${terms.map(row).join("") || `<p class="empty">${esc(A.noTriples)}</p>`}`;
  }

  function groupsPanel(p, item) {
    // the groups, the references' - each its group, if one has its result - and, where the groups are judged,
    // how many are right: a number's group may be right within the tolerance (the server counts them all)
    const kind = item?.kind;
    const language = env.language;
    const refs = (p.references || []).map((x, i) => x === null ? A.refPending(i + 1)
      : x.failed ? A.refFailed(i + 1, W.status2[x.failed] || x.failed)
      : (() => {
        const g = p.groups.find((gr) => gr.id === x.group);
        return g?.n ? A.refIn(i + 1, g.n) : A.refAlone(i + 1);         // (a tally's option nobody chose: none)
      })());
    if (p.right !== undefined) refs.push(A.right(p.right));
    const shown = p.shown?.id;
    const say = (m) => {                               // the kind's words, else the core's (a code of the core's)
      const words = env.kinds?.say(kind, m);
      return words && words !== m.code ? words : texts(env.language).steps.refused[m.code] ?? m.code;
    };
    const status = (s) => env.kinds?.status(kind, s) ?? null;
    const redraw = () => { panel.seen = ""; render(); };          // (KaTeX came: the options' formulas)
    const label = (g) => p.kind === "tally" && g.status === "ok" ? textHTML(groupLabel(g, W, item, language), redraw)
      : esc(groupLabel(g, W, item, language, status));
    const group = (g) => `<div class="actcluster${g.reference ? " ref" : ""}${g.id === shown ? " shown" : ""}${g.hidden ? " hidden" : ""}"
        data-group="${esc(g.id)}" data-entry="${esc(g.entry || "")}">
      <div class="top"><b>${label(g)}</b>${g.reference ? " ✓" : ""}${g.verdict ? ` · ${esc(W.verdict[g.verdict] || g.verdict)}` : ""}
        · ${esc(W.students(g.n))}</div>
      <pre>${esc(shownText(g.example, item, language))}</pre>
      ${g.messages?.length ? `<div class="meta">${g.messages.map((mm) => esc(say(mm))).join("<br>")}</div>` : ""}
      ${g.status === "ok" ? detailHTML(g.detail, env.kinds, kind, W, 4) : ""}
      <div class="buttons left">${g.id === shown ? `<button data-act="unshow" class="on">${esc(A.unshow)}</button>`
        : `<button data-act="show" title="${esc(A.showTitle)}">${esc(A.show)}</button>`}
        ${g.hidden ? `<button data-act="unhideg">${esc(A.unhide)}</button>` : `<button data-act="hideg">${esc(A.hide)}</button>`}
        ${g.entry ? `<button data-act="block" title="${esc(A.blockTitle)}">${esc(A.block)}</button>` : ""}</div></div>`;
    return `${refs.length ? `<p class="note">${refs.map(esc).join("<br>")}</p>` : `<p class="note">${esc(A.noRef)}</p>`}
      ${p.groups.map(group).join("") || `<p class="empty">${esc(A.none)}</p>`}
      ${p.others ? `<p class="note">${esc(A.others(p.others))}</p>` : ""}`;
  }

  function actsList(p, item) {
    // the step's last acts that hold, the latest first (moderation.py: acts), each to be undone - a group by
    // its result and text, a term by its label, an entry by its group's text where the picture has it
    const acts = p.acts || [];
    if (!acts.length) return "";
    const cut = (text) => (text.length > 40 ? `${text.slice(0, 39)}…` : text);
    const named = (key, role) => {
      const g = (p.groups || []).find((gr) => gr.id === key);
      if (g) return `${groupLabel(g, W, item, env.language)}: ${cut(shownText(g.example, item, env.language))}`;
      const t = (p.terms || []).find((tm) => tm.key === key && (!role || tm.role === role));
      return t ? t.label : key;
    };
    const whose = (entry) => {
      const g = entry ? (p.groups || []).find((gr) => gr.entry === entry) : null;
      return g ? cut(shownText(g.example, item, env.language)) : "";
    };
    return `<h3>${esc(A.acts)}</h3>${acts.map((a) => {
      const what = a.target ? named(a.target, a.role) : whose(a.entry);
      return `<div class="actterm"><span class="n">${a.n}</span><span class="term">${esc(A.act[a.act] || a.act)}${what
        ? ` · ${esc(what)}` : ""}${a.onto ? ` → ${esc(named(a.onto, a.role))}` : ""}${a.value !== undefined ? ` · ${esc(a.value)}`
        : ""}${a.off ? " ✕" : ""}</span>
      <span class="acts"><button data-act="undo" data-n="${a.n}">${esc(A.undo)}</button></span></div>`;
    }).join("")}`;
  }

  panel.render = render;
  panel.close = close;
  render();
  return panel;
}
