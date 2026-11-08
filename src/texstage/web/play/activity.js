// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A live activity on the phone (docs/live-activities-design.md, section 10): play.js mounts this
// screen while the activity is open - or revealed - and no quiz round is. A tuple: its fields,
// each offering the deck's suggestions and the terms the projector shows, and below the
// student's own triples, each to be withdrawn. A query: a text field without autocorrection,
// the token bar (a tap inserts at the cursor), and the state of the latest query - waiting, runs,
// a syntax error with the engine's message, after the reveal whether its result is the
// reference's. Never the result itself. The screen owns its elements: what is being typed
// survives the pushes. The words follow the engine: a Turtle text (engine=turtle) is valid or
// not, its graph the reference's or not (words).

import { languageTag, phoneError } from "./locale.js";

function vocabulary(language) {
const GERMAN = languageTag(language) === "de";
const L = GERMAN ? {
  add: "Hinzufügen", send: "Abschicken", mine: "Deine Beiträge", withdraw: "Zurückziehen",
  of: (n, m) => `${n} von ${m}`, closed: "Die Aktivität ist geschlossen.", blocked: "Die Lehrperson hat Beiträge für dich gesperrt.",
  waiting: "Abgeschickt - wartet auf den Rechner der Lehrperson …", ok: "Deine Anfrage läuft ✓",
  syntax: "Syntaxfehler", error: "Fehler", timeout: "Die Anfrage lief zu lange.", refused: "Das wird nicht ausgeführt",
  match: "Gleiches Ergebnis wie die Referenz ✓", differ: "Ein anderes Ergebnis als die Referenz", query: "Deine Anfrage",
  sent: "Abgeschickt.", empty: "Noch nichts.",
} : {
  add: "Add", send: "Send", mine: "Yours", withdraw: "Withdraw",
  of: (n, m) => `${n} of ${m}`, closed: "The activity is closed.", blocked: "The lecturer has closed contributions for you.",
  waiting: "Sent - waiting for the lecturer's computer …", ok: "Your query runs ✓",
  syntax: "Syntax error", error: "Error", timeout: "The query ran too long.", refused: "That is not run",
  match: "The same result as the reference ✓", differ: "A different result than the reference", query: "Your query",
  sent: "Sent.", empty: "Nothing yet.",
};
// a code activity's words where its engine's differ from a query's
const ENGINE_WORDS = {
  turtle: GERMAN ? {
    ok: "Gültiges Turtle ✓", timeout: "Das Parsen dauerte zu lange.", refused: "Das wird nicht angenommen",
    match: "Derselbe Graph wie die Referenz ✓", differ: "Ein anderer Graph als die Referenz", query: "Dein Turtle",
  } : {
    ok: "Valid Turtle ✓", timeout: "Parsing it took too long.", refused: "That is not taken",
    match: "The same graph as the reference ✓", differ: "A different graph than the reference", query: "Your Turtle",
  },
};
return engine => ({ ...L, ...(ENGINE_WORDS[engine] || {}) });
}
const VOCABULARY = { en: vocabulary("en"), de: vocabulary("de") };
export const words = (engine, language = "en") => VOCABULARY[languageTag(language)](engine);

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
  constructor({ root, client, state, language = state.language || "en" }) {
    this.root = root;
    this.client = client;
    this.language = language;
    const a = state.activity;
    this.id = a.id;
    this.kind = a.input;
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
          .catch((err) => this.error(phoneError(err, this.language)));
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
      this.error(phoneError(err, this.language));
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
    const key = JSON.stringify([a.suggest, a.mine, a.phase]);
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
    const word = { waiting: L.waiting, ok: L.ok, timeout: L.timeout }[m.status];
    const said = word || `${L[m.status] || m.status}${m.error ? `: ${m.error}` : ""}`;
    const verdict = m.match === undefined ? "" : `<p class="${m.match ? "good" : "bad"}">${esc(m.match ? L.match : L.differ)}</p>`;
    box.className = `card actstate ${m.status}`;
    box.innerHTML = `<p>${esc(said)}</p>${verdict}`;
  }

  destroy() {
    this.gone = true;
  }
}
