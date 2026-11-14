// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A step of a live activity on the phone, as the activity framework has it (docs/architecture/
// activity-framework-design.md, 12; the plan of F2, 4.5) - for a server run with --activities core.
// play.js mounts it while the deck's current step is there and is not ready (activity.step: one text,
// the same for every phone) and no quiz round is open. One screen for every kind: the prompt, the
// input - the core's, code or fields, or the kind's own (web/input.js) -, Send, the student's entries
// and their states. The step's part comes with activity.step, the student's own with the state
// (state.activity.mine). What a student typed shows as text, never as HTML.
//
// An entry has an id the phone makes: sent again after a lost connection - the client sends a message
// again with its id -, the server answers with the entry that is there. Its states: sending; received;
// being checked; then what feedback= allows - it runs (or the kind's own word: a Turtle text is valid),
// a syntax error, the kind's message in the deck's language (kinds.js), right or wrong -, and after the
// reveal its verdict. The screen owns its elements: what is being typed survives the pushes. The deck's
// kinds come when they come (play.js gives them as a function: the ones there are now) - kindsReady().
//
// A kind's own input: input(element, step, words, send) draws into the element it is given and calls
// send({text} | {fields}), which gives a promise of whether the entry was taken.

import { errorText, texts } from "../i18n/i18n.js";
import { color, shapeSVG } from "../shared/shapes.js";
import { textHTML } from "../shared/text.js";
import { insertToken } from "./activity.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const OPEN = "open";
const AGAIN_MS = 1000;                  // a choice of one refused as too fast: sent again after this - the gap's
const AGAIN_TRIES = 5;                  // ... so often at most

export function entryId() {
  // an entry's id, as the server takes it ([A-Za-z0-9_-]{8,40}): 128 random bits
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return "e" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function clock(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function timeLeft(step, now) {
  // what is left of a step's time (ms), as the server read it at `since`; null: it has none
  if (!step || step.time === null || step.time === undefined) return null;
  return step.phase === OPEN && typeof step.since === "number" ? Math.max(0, step.time - (now - step.since)) : step.time;
}

export function decimalComma(language) {
  // whether the deck's language writes 3,5 for three and a half
  return (1.5).toLocaleString(language || "en").includes(",");
}

export function parseNumber(text, language) {
  // a number as a student types it, or null: 42, -3.5; 3,5 and 3.5 in any deck; 1 000 and 1'000 (spaces,
  // apostrophes between the digits); 1,000.5 and 1.000,5 (the last separator is the decimal one, the other
  // groups by three); a minus sign as some keyboards type it. One separator before three digits alone is
  // what the deck's language makes of it - 1,000 is a thousand in English, 1.000 in German -, and no
  // exponent: the deck's own numbers have none
  const t = String(text ?? "").replace(/[\s'\u2019]/g, "").replace(String.fromCharCode(0x2212), "-");
  const m = /^([+-]?)([\d.,]+)$/.exec(t);
  if (!m || !/\d/.test(m[2])) return null;
  const body = m[2], seps = body.replace(/\d/g, "");
  let decimal = null;
  if (seps.includes(",") && seps.includes(".")) decimal = seps[seps.length - 1];
  else if (seps.length === 1) {
    const [whole, part] = body.split(seps);
    const grouped = /^\d{1,3}$/.test(whole) && /^\d{3}$/.test(part);       // 1,000 - or one and three thousandths
    decimal = !grouped || (seps === "," ? decimalComma(language) : !decimalComma(language)) ? seps : null;
  }
  const at = decimal ? body.lastIndexOf(decimal) : body.length;
  const whole = body.slice(0, at), part = decimal ? body.slice(at + 1) : "";
  const groups = whole.split(/[.,]/);
  if (groups.length > 1 && !(/^\d{1,3}$/.test(groups[0]) && groups.slice(1).every((g) => /^\d{3}$/.test(g)))) return null;
  if (groups.length > 1 && new Set(whole.replace(/\d/g, "")).size > 1) return null;   // (one kind groups)
  if (!/^\d*$/.test(part) || !(groups.join("") || part)) return null;
  const n = Number(`${m[1]}${groups.join("") || "0"}.${part || "0"}`);
  return Number.isFinite(n) ? n : null;
}

export function numberShown(n, language) {
  // a number in the deck's language, every digit the kind keeps (15) and no grouping: 3.5, 3,5, 1099511627776
  return Number(n).toLocaleString(language || "en", { maximumFractionDigits: 15, useGrouping: false });
}

export function choiceHTML(places, options, redraw) {
  // a choice by its options' texts, as HTML - their $math$ typeset (shared/text.js), " + " between them
  return places.map((n) => textHTML(options?.[n] ?? String(n), redraw)).join(" + ");
}

export function entryShown(input, step, language, redraw = null) {
  // an entry as the student's list shows it, as HTML: its text, its fields, its choice by the options' texts,
  // its number in the deck's language
  if (!input) return "";
  if (input.fields) return input.fields.map(esc).join(" · ");
  if (input.choice) return choiceHTML(input.choice, step?.options, redraw);
  if (input.number !== undefined && input.number !== null) return esc(numberShown(input.number, language));
  return `<pre>${esc(input.text ?? "")}</pre>`;
}

export function said(entry, step, L, say, status = () => null) {
  // an entry's state in words, and a class for its colour: the server says codes, the phone words -
  // a status in the kind's own word where it has one (status), its message in the kind's words (say)
  const states = [];
  let cls = "";
  if (entry.state && entry.state !== "in") states.push(L.state[entry.state] || entry.state);
  if (entry.check === "sending") states.push(L.sending);
  else if (entry.check === "waiting") states.push(L.waiting);
  else if (entry.check === "unchecked") states.push(L.unchecked);
  else if (entry.check === "checked" && entry.status) {
    const ok = entry.status === "ok";
    cls = ok ? "good" : entry.status === "internal" ? "" : "bad";
    const taken = ["fields", "choice", "number", "text"].includes(step?.input);     // (nothing of them runs: "In ✓",
    const word = status(entry.status) || (ok && taken ? L.fieldsOk : L.status[entry.status] || entry.status);   // till the kind's word)
    const message = entry.message ? say(entry.message) : "";
    states.push(message ? `${word}: ${message}` : word);
  } else states.push(L.received);
  if (entry.verdict) {
    states.push(L.verdict[entry.verdict] || entry.verdict);
    cls = entry.verdict === "correct" ? "good" : entry.verdict === "partial" ? "" : "bad";
  }
  return { words: states.join(" · "), cls };
}

export class StepScreen {
  constructor({ root, client, state, step, language, kinds }) {
    this.root = root;
    this.client = client;
    this.language = language;
    this.kindsNow = typeof kinds === "function" ? kinds : () => kinds;
    this.L = texts(language).steps;
    this.step = step;
    this.pending = [];                                 // entries on their way: {id, input, check: "sending"}
    this.listed = "";
    this.refilled = false;                             // (a reload puts the text as sent back - once)
    this.timer = setInterval(() => this.tick(), 1000);
    this.build(state, step);
  }

  get kinds() {
    return this.kindsNow() || null;
  }

  get kind() {
    return this.step.kind;
  }

  build(state, step) {
    const L = this.L;
    const p = step.prompt;
    const prompt = p?.image ? `<div class="card prompt"><img src="${esc((state.session?.base || "") + p.image)}"
      style="width:${((p.width || 200) * 1.4).toFixed(1)}px" alt=""></div>` : "";
    const own = this.kinds?.module(step.kind, "input");
    this.own = Boolean(own?.input);                    // (its kind's own input: play.js makes it anew if it comes later)
    let body;
    if (this.own) body = `<div class="act kindinput" data-role="input"></div>`;
    else if (step.input === "choice") {                // the deck's options, as a quiz's answers look - $math$ typeset
      const many = step.select === "many", options = step.options || [];
      body = `<form class="act" autocomplete="off">${many ? `<p class="note">${esc(L.several)}</p>` : ""}
        <div class="answers${options.some((o) => o.length > 14) ? " one" : ""}" data-role="choices">${options.map((o, i) =>
          `<button type="button" class="answer" data-choice="${i}" style="--c:${color(i + 1)}" aria-pressed="false"><span
            class="shape" aria-hidden="true">${shapeSVG(i + 1)}</span><span class="face text">${textHTML(o, () => this.typeset())}</span></button>`).join("")}</div>
        ${many ? `<button class="main" type="submit">${esc(L.send)} <span data-role="used"></span></button>`
          : `<p class="note" data-role="used"></p>`}</form>`;
    } else if (step.input === "number" || step.input === "text") {      // one line: a number, a short answer
      const number = step.input === "number";
      body = `<form class="act" autocomplete="off"><label for="step-line">${esc(number ? L.yourNumber : L.yourAnswer)}</label>
        <div class="line"><input id="step-line" type="text" data-role="line" maxlength="${number ? 40 : 100}" autocomplete="off"
          ${number ? 'inputmode="decimal" autocapitalize="off" autocorrect="off" spellcheck="false"' : ""}>${number
          ? `<button type="button" class="sign" data-role="sign" aria-label="${esc(L.sign)}">±</button>` : ""}</div>
        <div class="hint" data-role="hint" hidden></div>
        <button class="main" type="submit">${esc(L.send)} <span data-role="used"></span></button></form>`;
    } else if (step.input === "fields") {
      body = `<form class="act" autocomplete="off">${(step.fields || []).map((f, i) => `<label>${esc(f)}<input type="text"
          data-field="${i}" list="step-words" maxlength="60" autocapitalize="off" autocorrect="off" spellcheck="false"></label>`).join("")}
        <datalist id="step-words"></datalist>
        <button class="main" type="submit">${esc(L.add)} <span data-role="used"></span></button></form>`;
    } else {
      body = `<form class="act" autocomplete="off"><label for="step-text">${esc(L.yourText)}</label>
        <div class="tokens" data-role="tokens">${(step.tokens || []).map((t) =>
          `<button type="button" data-token="${esc(t)}">${esc(t)}</button>`).join("")}</div>
        <textarea id="step-text" rows="6" maxlength="2000" autocapitalize="off" autocorrect="off" spellcheck="false"
          autocomplete="off" class="code"></textarea>
        <div class="hint" data-role="hint" hidden></div>
        <button class="main" type="submit">${esc(L.send)} <span data-role="used"></span></button></form>`;
    }
    this.root.innerHTML = `${prompt}<div class="steptime" data-role="time" hidden></div>${body}
      <div class="error" data-role="error"></div><div class="note" data-role="phase"></div>
      <div class="actmine"><h3>${esc(L.mine)}</h3><ul data-role="mine"></ul></div>`;
    this.form = this.root.querySelector("form");
    this.form?.addEventListener("submit", (e) => { e.preventDefault(); this.submit(); });
    this.text = this.root.querySelector("textarea") || this.root.querySelector("input[data-role=line]");
    this.picked = new Set();                           // a choice of several, before it is sent
    this.wanted = undefined;                           // a choice of one, the latest tap, until it is sent
    this.root.querySelector("[data-role=choices]")?.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-choice]");
      if (b && !b.disabled) this.choose(Number(b.dataset.choice));
    });
    this.root.querySelector("[data-role=sign]")?.addEventListener("click", () => this.sign());
    this.root.querySelector("[data-role=tokens]")?.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-token]");
      if (b) this.insert(b.dataset.token);
    });
    this.root.querySelector("[data-role=mine]").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-withdraw]");
      if (b) this.withdraw(b.dataset.withdraw);
    });
    if (this.own) {
      try {
        own.input(this.root.querySelector("[data-role=input]"), this.public(step), this.L, (entry) => this.send(entry));
      } catch (err) {
        console.warn("texstage: the kind's input failed", err);
      }
    }
    this.text?.addEventListener("input", () => this.hints?.ask(this.public(this.step), this.text.value, { language: this.language }));
    this.wireHints();
  }

  wireHints() {
    // a kind's hints for the text - once the deck's kinds are there
    if (this.hints || !this.text || this.gone) return;
    this.hints = this.kinds?.hints(this.kind) || null;
    if (this.hints) this.hints.onHint = (hint) => this.hint(hint);
  }

  kindsReady() {
    // the deck's kinds came (play.js): whether the screen is to be made anew - its kind's own input came -,
    // else its hints, and its entries said in the kind's words
    if (this.gone) return false;
    if (!this.own && this.kinds?.module(this.kind, "input")) return true;
    this.wireHints();
    this.listed = "";
    this.list();
    return false;
  }

  choose(n) {
    // an option tapped: a choice of one goes at once - the latest tap wins (flush) -, of several it is marked
    // until Send
    if (this.step.select !== "many") {
      this.wanted = n;
      this.mark(new Set([n]));
      this.flush();
      return;
    }
    if (this.picked.has(n)) this.picked.delete(n);
    else this.picked.add(n);
    this.mark(this.picked);
  }

  counted() {
    // the student's choice that counts now - the latest entry's that is in -, or null
    return (this.entries || []).find((e) => e.state === "in")?.input?.choice || null;
  }

  async flush() {
    // a choice of one: the latest tap sent - after the one before is answered, again when it was too soon
    // after it (the step's gap: a student changes their mind quickly), not at all when it counts already
    if (this.flushing) return;
    this.flushing = true;
    let tries = 0;
    try {
      while (this.wanted !== undefined && !this.gone) {
        const n = this.wanted;
        const now = this.counted();
        if (now?.length === 1 && now[0] === n) {
          this.wanted = undefined;
          break;
        }
        const sent = await this.send({ choice: [n] }, true);
        if (sent === "later" && tries++ < AGAIN_TRIES) {
          await new Promise((resolve) => setTimeout(resolve, AGAIN_MS));
          continue;
        }
        if (sent === "later") this.error(this.refusal({ code: "too-fast" }));
        if (this.wanted === n || !sent || sent === "later") this.wanted = undefined;
      }
    } finally {
      this.flushing = false;
    }
  }

  sign() {
    // ±: the number's sign - for a phone whose keyboard for numbers has no minus (an iPhone's)
    const t = this.text;
    if (!t || t.disabled) return;
    const v = t.value.trim().replace(String.fromCharCode(0x2212), "-");
    t.value = v.startsWith("-") ? v.slice(1) : `-${v.replace(/^\+/, "")}`;
    t.focus();
  }

  typeset() {
    // KaTeX came (shared/text.js): the options and the list drawn again, their formulas typeset
    if (this.gone) return;
    const options = this.step.options || [];
    this.root.querySelectorAll("button[data-choice] .face").forEach((el) => {
      el.innerHTML = textHTML(options[Number(el.closest("button").dataset.choice)] ?? "");
    });
    this.listed = "";
    this.list();
  }

  mark(chosen) {
    this.root.querySelectorAll("button[data-choice]").forEach((b) => {
      const on = chosen.has(Number(b.dataset.choice));
      b.classList.toggle("selected", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }

  public(step) {
    // what a kind's module gets of the step: its public part, no time
    const { time, since, ...rest } = step || {};
    return rest;
  }

  insert(token) {
    const t = this.text;
    const s = t.selectionStart ?? t.value.length, e = t.selectionEnd ?? s;
    const { value, cursor } = insertToken(t.value, s, e, token);
    t.value = value;
    t.selectionStart = t.selectionEnd = cursor;
    t.focus();
    this.hints?.ask(this.public(this.step), t.value, { language: this.language });   // (as a key would)
  }

  error(text) {
    if (this.gone) return;
    this.root.querySelector("[data-role=error]").textContent = text || "";
  }

  hint(h) {
    const box = this.gone ? null : this.root.querySelector("[data-role=hint]");
    if (!box) return;
    box.hidden = !h;
    box.textContent = h ? `${this.L.hint}: ${this.kinds?.say(this.kind, h) ?? h.code}` : "";
  }

  refusal(err) {
    return this.L.refused[err?.code] || errorText(this.language, err);
  }

  async submit() {
    if (this.step.input === "choice") {
      if (!this.picked.size) return this.error(this.L.refused.choice);
      const choice = [...this.picked].sort((a, b) => a - b), now = this.counted();
      if (now && now.length === choice.length && now.every((n, i) => n === choice[i])) return;   // (it counts already)
      await this.send({ choice });
    } else if (this.step.input === "number") {
      const n = parseNumber(this.text.value, this.language);
      if (n === null) return this.error(this.L.refused.number);
      await this.send({ number: n });
    } else if (this.step.input === "fields") {
      const inputs = [...this.form.querySelectorAll("input[data-field]")];
      if (inputs.some((i) => !i.value.trim())) return this.error(this.L.refused.field);
      if (await this.send({ fields: inputs.map((i) => i.value) }) && !this.gone) {
        inputs.forEach((i) => { i.value = ""; });
        inputs[0].focus();
      }
    } else if (this.text) {
      if (!this.text.value.trim()) return this.error(this.L.refused.text);
      await this.send({ text: this.text.value });
    }
  }

  async send(input, later = false) {
    // an entry: its id made here, sent again with it after a lost connection; answered once written. later:
    // a refusal as too fast is said by no error but by "later" (flush sends it again)
    if (this.gone) return false;
    const id = entryId();
    const button = this.form?.querySelector("button.main");
    if (button) button.disabled = true;
    this.error("");
    this.pending.push({ id, input, check: "sending", state: "in" });
    this.list();
    try {
      await this.client.send({ t: "activity.enter", activity: this.step.activity, step: this.step.step, entry: id, ...input });
      return true;
    } catch (err) {
      if (later && err?.code === "too-fast") return "later";
      this.error(this.refusal(err));                   // (a screen that is gone says nothing: error)
      return false;
    } finally {
      this.pending = this.pending.filter((e) => e.id !== id);
      if (button && !this.gone) button.disabled = !this.open;
      this.list();
    }
  }

  withdraw(id) {
    this.client.send({ t: "activity.withdraw", activity: this.step.activity, step: this.step.step, entry: id })
      .catch((err) => this.error(this.refusal(err)));
  }

  update(state, step) {
    if (this.gone) return;
    this.state = state;
    this.step = step;
    const L = this.L;
    const mine = state?.activity?.mine?.activity === step.activity ? state.activity.mine : null;
    const blocked = Boolean(mine?.blocked);
    this.open = step.phase === OPEN && !blocked;
    this.form?.querySelectorAll("input, textarea, button").forEach((el) => { el.disabled = !this.open; });
    const own = this.root.querySelector("[data-role=input]");
    if (own) own.inert = !this.open;                   // (a kind's own input: nothing in it to touch)
    this.root.querySelector("[data-role=phase]").textContent = blocked ? L.blocked : step.phase === OPEN ? "" : L.phase[step.phase] || "";
    this.root.querySelectorAll("[data-role=used]").forEach((el) => {
      el.textContent = mine ? `(${L.of(mine.used, step.limit)})` : "";
    });
    if (step.input === "fields") {
      const words = (step.suggest || []).map((w) => `<option value="${esc(w)}">`).join("");
      const list = this.root.querySelector("#step-words");
      if (list && list.dataset.words !== words) {
        list.innerHTML = words;
        list.dataset.words = words;
      }
    } else if (step.input === "choice") {              // what is chosen: the latest entry's, or what is marked
      const latest = mine?.entries?.find((e) => e.state === "in")?.input?.choice || [];
      if (step.select === "many" && !this.refilled && mine) {
        this.refilled = true;
        latest.forEach((n) => this.picked.add(n));
      }
      this.mark(step.select === "many" ? this.picked : new Set(this.wanted !== undefined ? [this.wanted] : latest));
    } else if (this.text && !this.refilled && mine) {
      this.refilled = true;                            // (a reload: the text as sent - once, not a text cleared)
      const last = mine.entries?.[0]?.input;
      if (!this.text.value && last) this.text.value = last.number !== undefined ? numberShown(last.number, this.language) : last.text || "";
    }
    this.entries = mine?.entries || [];
    this.tick();
    this.list();
  }

  list() {
    if (this.gone) return;                             // (a screen that is gone writes into none that came after it)
    const L = this.L;
    const kinds = this.kinds;
    const say = (m) => kinds?.say(this.kind, m) ?? m.code;
    const status = (s) => kinds?.status(this.kind, s) ?? null;
    const known = new Set((this.entries || []).map((e) => e.id));
    const all = [...this.pending.filter((e) => !known.has(e.id)), ...(this.entries || [])];
    const open = this.step.phase === OPEN;
    const html = all.map((e) => {
      const { words, cls } = said(e, this.step, L, say, status);
      const shown = entryShown(e.input, this.step, this.language, () => this.typeset());
      const back = open && e.state === "in" && e.check !== "sending"
        ? `<button type="button" data-withdraw="${esc(e.id)}" aria-label="${esc(L.withdraw)}">×</button>` : "";
      return `<li class="${esc(cls)}"><span class="entry">${shown}</span><span class="said">${esc(words)}</span>${back}</li>`;
    }).join("") || `<li class="empty">${esc(L.empty)}</li>`;
    if (html === this.listed) return;
    this.listed = html;
    this.root.querySelector("[data-role=mine]").innerHTML = html;
  }

  tick() {
    if (this.gone) return;
    const box = this.root.querySelector("[data-role=time]");
    const left = timeLeft(this.step, this.client.now ? this.client.now() : Date.now());
    box.hidden = left === null;
    if (left !== null) box.textContent = this.L.left(clock(left));
  }

  destroy() {
    this.gone = true;
    clearInterval(this.timer);
    this.hints?.destroy();
  }
}
