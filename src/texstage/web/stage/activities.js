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
import { clock, timeLeft } from "../play/activities.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const FETCH_MS = 500;
const LAYOUT_MS = 500;

export function shownText(input) {
  // an entry's input as a line of text: its text - without the empty lines in front, where comments were
  // that the kind took out (the plan of F2, 4.7) -, or its fields
  if (!input) return "";
  return input.fields ? input.fields.join(" · ") : String(input.text ?? "").replace(/^(?:[ \t]*\r?\n)+/, "");
}

export function groupLabel(g, words) {
  // a group's short name: its result ("11 rows", "yes"), else what went wrong
  if (g.status !== "ok") return words.status2[g.status] || g.status;
  const d = g.detail || {};
  if (d.kind === "ask") return d.boolean ? words.yes : words.no;
  if (typeof d.count === "number") return d.kind === "graph" ? words.triples(d.count) : words.rows(d.count);
  return shownText(g.example) || words.result;
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
    else this.drawGroups(p);
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
    const w = { ...this.boxWords, __language: this.language };
    const most = Math.max(1, ...p.groups.map((g) => g.n));
    const kind = this.item?.kind;
    const mark = (g) => (g.reference ? " ✓" : "") + (g.verdict && p.revealed ? ` · ${w.verdict[g.verdict] || g.verdict}` : "");
    const rows = p.groups.map((g) => `<div class="tq-cluster${g.reference ? " tq-ref" : ""}${g.status !== "ok" ? " tq-bad" : ""}">
        <span class="tq-clabel">${esc(groupLabel(g, w))}${esc(mark(g))}</span>
        <span class="tq-cbar"><i style="width:${((100 * g.n) / most).toFixed(1)}%"></i></span>
        <span class="tq-cn">${g.n}</span></div>`).join("");
    const s = p.shown;
    const shown = s ? `<div class="tq-shown"><div class="tq-shownhead">${esc(groupLabel(s, w))} · ${esc(w.students(s.n))}${esc(mark(s))}</div>
        <pre>${esc(shownText(s.example))}</pre>${s.status === "ok" ? detailHTML(s.detail, this.kinds, kind, w) : ""}</div>` : "";
    const solution = (p.solution || []).map((r) => `<div class="tq-shown"><div class="tq-shownhead">${esc(w.solution)}</div>
        <pre>${esc(r.text)}</pre>${detailHTML(r.detail, this.kinds, kind, w)}</div>`).join("");
    const head = `${w.students(p.students || 0)}${p.waiting ? ` · ${w.waiting(p.waiting)}` : ""}`;
    this.el.innerHTML = `<div class="tq-clusters"><div class="tq-chead">${esc(head)}</div>
      ${rows || `<div class="tq-empty">${esc(p.phase === "open" || p.phase === "paused" ? w.held.waiting : w.held.none)}</div>`}
      ${p.others ? `<div class="tq-more">${esc(w.others)} · ${p.others}</div>` : ""}</div>${shown}${solution}`;
    this.nodes = new Map();
    this.shape = null;
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
    el.querySelector("#actbody").innerHTML = head + body + actsList(p);
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
    const kind = item?.kind;
    const refs = (p.references || []).map((x, i) => x === null ? A.refPending(i + 1)
      : x.failed ? A.refFailed(i + 1, W.status2[x.failed] || x.failed)
      : (() => { const g = p.groups.find((gr) => gr.id === x.group); return g ? A.refIn(i + 1, g.n) : A.refAlone(i + 1); })());
    const shown = p.shown?.id;
    const say = (m) => env.kinds?.say(kind, m) ?? m.code;
    const group = (g) => `<div class="actcluster${g.reference ? " ref" : ""}${g.id === shown ? " shown" : ""}${g.hidden ? " hidden" : ""}"
        data-group="${esc(g.id)}" data-entry="${esc(g.entry || "")}">
      <div class="top"><b>${esc(groupLabel(g, W))}</b>${g.reference ? " ✓" : ""}${g.verdict ? ` · ${esc(W.verdict[g.verdict] || g.verdict)}` : ""}
        · ${esc(W.students(g.n))}</div>
      <pre>${esc(shownText(g.example))}</pre>
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

  function actsList(p) {
    // the step's last acts that hold, the latest first (moderation.py: acts), each to be undone - a group by
    // its result and text, a term by its label, an entry by its group's text where the picture has it
    const acts = p.acts || [];
    if (!acts.length) return "";
    const cut = (text) => (text.length > 40 ? `${text.slice(0, 39)}…` : text);
    const named = (key, role) => {
      const g = (p.groups || []).find((gr) => gr.id === key);
      if (g) return `${groupLabel(g, W)}: ${cut(shownText(g.example))}`;
      const t = (p.terms || []).find((tm) => tm.key === key && (!role || tm.role === role));
      return t ? t.label : key;
    };
    const whose = (entry) => {
      const g = entry ? (p.groups || []).find((gr) => gr.entry === entry) : null;
      return g ? cut(shownText(g.example)) : "";
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
