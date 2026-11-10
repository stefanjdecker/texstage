// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A live activity on the phone (docs/live-activities-design.md, section 10): play.js mounts this
// screen while the activity is open - or revealed - and no quiz round is. A tuple: its fields,
// each offering the deck's suggestions and the terms the projector shows, and below the
// student's own triples, each to be withdrawn. A query: a text field without autocorrection,
// the token bar (a tap inserts at the cursor), and the state of the latest query - being checked
// (where the server checks: checks "server"; else waiting for the lecturer's computer), runs, a
// syntax error with the engine's message, could not be checked (internal: never the student's
// fault, and no message), after the reveal whether its result is the reference's.
// Never the result itself. The screen owns its elements: what is being typed
// survives the pushes. The words follow the engine: a Turtle text (engine=turtle) is valid or
// not, its graph the reference's or not (words) - in the deck's language, as all of the phone's.

import { errorText, texts } from "../i18n/i18n.js";

const ENGINES = ["turtle"];          // the engines whose words differ from a query's (i18n's "activity")
// the server's refusals of a contribution (server/activity.py) in the screen's own words
export const REFUSALS = { closed: "closed", blocked: "blocked", "too-fast": "tooFast", "too-many": "tooMany",
  duplicate: "duplicate", field: "fillIn", text: "typeFirst" };

// a code activity's words in a language: a query's, with its engine's where they differ
export function words(engine, language) {
  const all = texts(language).activity;
  const base = Object.fromEntries(Object.entries(all).filter(([key]) => !ENGINES.includes(key)));
  return { ...base, ...(ENGINES.includes(engine) ? all[engine] : {}) };
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// The token bar: a token goes in at the cursor - a word (SELECT, a, :Professor, ?name, dbr:Berlin)
// with a space after it, and one before it where it would run into a word; the start of a word
// - ?, _:, dbo: or COUNT( - with that space before it only; a sign - :, ., {, ", @, ^^ or < - as
// it is (a colon may end a prefix being typed: dbr and : make dbr:). -> {value, cursor}
function spacing(token) {
  if (token === ":" || !/^[\p{L}\p{N}_?:$]/u.test(token)) return "sign";
  return /[\p{L}\p{N}_]$/u.test(token) ? "word" : "start";
}
export function insertToken(value, start, end, token) {
  const before = value.slice(0, start);
  const kind = spacing(token);
  const pad = kind !== "sign" && before && !/\s$/.test(before) && /[\p{L}\p{N}_?:)]$/u.test(before) ? " " : "";
  const add = pad + token + (kind === "word" ? " " : "");
  return { value: before + add + value.slice(end), cursor: start + add.length };
}

export class ActivityScreen {
  constructor({ root, client, state, language }) {
    this.root = root;
    this.client = client;
    const a = state.activity;
    this.id = a.id;
    this.kind = a.input;
    this.language = language;                        // the deck's (play.js)
    const L = this.L = words(a.engine, language);
    const prompt = a.prompt ? `<div class="card prompt"><img src="${esc(state.session.base + a.prompt.image)}"
      style="width:${(a.prompt.width * 1.4).toFixed(1)}px" alt=""></div>` : "";
    root.innerHTML = this.kind === "tuple"
      ? `${prompt}<form class="act" autocomplete="off">
          ${a.fields.map((f, i) => `<label>${esc(f)}<input type="text" data-field="${i}" list="act-words" maxlength="60"
            autocapitalize="off" autocorrect="off" spellcheck="false"></label>`).join("")}
          <datalist id="act-words"></datalist>
          <button class="main" type="submit">${esc(L.add)}</button>
          <div class="error" data-role="error"></div></form>
        <div class="actmine"><h3>${esc(L.mine)} <span data-role="used"></span></h3><ul data-role="mine"></ul></div>`
      : `${prompt}<form class="act" autocomplete="off">
          <label for="act-text">${esc(L.query)}</label>
          <div class="tokens" data-role="tokens"></div>
          <textarea id="act-text" rows="6" maxlength="2000" autocapitalize="off" autocorrect="off" spellcheck="false"
            autocomplete="off" class="code"></textarea>
          <button class="main" type="submit">${esc(L.send)} <span data-role="used"></span></button>
          <div class="error" data-role="error"></div></form>
        <div class="card actstate" data-role="state" hidden></div>`;
    this.form = root.querySelector("form");
    this.form.addEventListener("submit", (e) => { e.preventDefault(); this.submit(); });
    if (this.kind === "code") {
      this.text = root.querySelector("textarea");
      root.querySelector("[data-role=tokens]").innerHTML = (a.tokens || []).map((t) =>
        `<button type="button" data-token="${esc(t)}">${esc(t)}</button>`).join("");
      root.querySelector("[data-role=tokens]").addEventListener("click", (e) => {
        const b = e.target.closest("button[data-token]");
        if (b) this.insert(b.dataset.token);
      });
    } else {
      root.querySelector("[data-role=mine]").addEventListener("click", (e) => {
        const b = e.target.closest("button[data-withdraw]");
        if (b) this.client.send({ t: "activity.withdraw", activity: this.id, contribution: b.dataset.withdraw })
          .catch((err) => this.error(this.refusal(err)));
      });
    }
    this.listed = "";
  }

  insert(token) {
    // the token at the cursor (insertToken)
    const t = this.text;
    const s = t.selectionStart ?? t.value.length, e = t.selectionEnd ?? s;
    const { value, cursor } = insertToken(t.value, s, e, token);
    t.value = value;
    t.selectionStart = t.selectionEnd = cursor;
    t.focus();
  }

  error(text) {
    this.root.querySelector("[data-role=error]").textContent = text || "";
  }

  refusal(err) {
    // what the server refused, in the screen's words or the phone's (i18n's errors)
    const own = REFUSALS[err?.code];
    return own ? this.L[own] : errorText(this.language, err);
  }

  async submit() {
    const button = this.form.querySelector("button.main");
    button.disabled = true;
    this.error("");
    try {
      if (this.kind === "tuple") {
        const inputs = [...this.form.querySelectorAll("input[data-field]")];
        await this.client.send({ t: "activity.send", activity: this.id, fields: inputs.map((i) => i.value) });
        inputs.forEach((i) => { i.value = ""; });
        inputs[0].focus();
      } else {
        await this.client.send({ t: "activity.send", activity: this.id, text: this.text.value });
      }
    } catch (err) {
      this.error(this.refusal(err));
    } finally {
      button.disabled = false;
    }
  }

  update(state) {
    const a = state.activity;
    if (!a) return;
    const L = this.L;
    const closed = a.phase !== "open" || a.blocked;
    this.form.querySelectorAll("input, textarea, button").forEach((el) => { el.disabled = closed; });
    if (closed) this.error(a.blocked ? L.blocked : L.closed);
    else if ([L.blocked, L.closed].includes(this.root.querySelector("[data-role=error]").textContent)) this.error("");
    this.root.querySelectorAll("[data-role=used]").forEach((el) => { el.textContent = `(${L.of(a.used, a.limit)})`; });
    const key = JSON.stringify([a.suggest, a.mine, a.phase, a.checks]);
    if (key === this.listed) return;
    this.listed = key;
    if (this.kind === "tuple") {
      this.root.querySelector("#act-words").innerHTML = (a.suggest || []).map((w) => `<option value="${esc(w)}">`).join("");
      this.root.querySelector("[data-role=mine]").innerHTML = (a.mine || []).map((c) => `<li><span>${c.fields.map(esc).join(" · ")}</span>
        ${a.phase === "open" ? `<button type="button" data-withdraw="${esc(c.id)}" aria-label="${esc(L.withdraw)}">×</button>` : ""}</li>`)
        .join("") || `<li class="empty">${esc(L.empty)}</li>`;
      return;
    }
    const box = this.root.querySelector("[data-role=state]");
    const m = a.mine;
    box.hidden = !m;
    if (!m) return;
    if (!this.text.value && m.text) this.text.value = m.text;          // (a reload: the query as sent)
    const waiting = a.checks === "server" ? L.checking : L.waiting;        // the server's checks, or the lecturer's computer
    const word = { waiting, ok: L.ok, timeout: L.timeout, internal: L.internal }[m.status];
    const said = word || `${L[m.status] || m.status}${m.error ? `: ${m.error}` : ""}`;
    const verdict = m.match === undefined ? "" : `<p class="${m.match ? "good" : "bad"}">${esc(m.match ? L.match : L.differ)}</p>`;
    box.className = `card actstate ${m.status}`;
    box.innerHTML = `<p>${esc(said)}</p>${verdict}`;
  }

  destroy() {
    this.gone = true;
  }
}
