// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Questions and messages in the page instead of the browser's confirm(), alert() and prompt(),
// which take a full-screen window out of full screen. Enter answers yes (or OK), Esc no; while one
// is open, no key reaches the presenter (and presenter.js leaves the keys to any open .dialog).
//
//   if (await ask("Reset the timer to 0:00?", "Reset")) ...          // true: yes
//   await tell("A number of minutes, please.");
//   const text = await askText("Target duration in minutes", "45");  // null: cancelled
//   notice("All ink of this frame erased - ↶ or Ctrl+Z brings it back");  // fades by itself
//
// The texts are the caller's; the buttons a question does not name are OK and Cancel in the
// page's language (i18n.js pageTexts: the open deck's, else the browser's).

import { pageTexts } from "../i18n/i18n.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const words = () => pageTexts().dialog;

function open(text, { yes = words().ok, no = null, field = null } = {}) {
  return new Promise((resolve) => {
    const before = document.activeElement;
    const el = document.createElement("div");
    el.className = "dialog";
    el.setAttribute("role", "alertdialog");
    el.innerHTML = `<div class="box"><p class="ask">${esc(text)}</p>
      ${field === null ? "" : `<input type="text" class="askfield" value="${esc(field)}">`}
      <div class="buttons"><button class="primary" data-answer="yes">${esc(yes)}</button>
        ${no ? `<button class="secondary" data-answer="no">${esc(no)}</button>` : ""}</div></div>`;
    const input = el.querySelector(".askfield");
    const keys = (e) => {
      e.stopPropagation();                                   // none for the presenter meanwhile
      if (e.key === "Enter" || e.key === "Escape") {
        e.preventDefault();
        finish(e.key === "Enter");
      }
    };
    const finish = (yes) => {
      document.removeEventListener("keydown", keys, true);
      el.remove();
      before?.focus?.({ preventScroll: true });
      resolve(input ? (yes ? input.value : null) : yes);
    };
    el.querySelector('[data-answer="yes"]').onclick = () => finish(true);
    el.querySelector('[data-answer="no"]')?.addEventListener("click", () => finish(false));
    document.addEventListener("keydown", keys, true);
    document.body.append(el);
    (input || el.querySelector('[data-answer="yes"]')).focus();
    input?.select();
  });
}

export const ask = (text, yes = words().ok, no = words().cancel) => open(text, { yes, no });
export const tell = (text) => open(text);
export const askText = (text, value = "", yes = words().ok) => open(text, { yes, no: words().cancel, field: value });

export function notice(text) {
  let el = document.querySelector(".hint.note");
  if (!el) {
    el = Object.assign(document.createElement("div"), { className: "hint note", role: "status" });
    document.body.append(el);
  }
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(el.timer);
  el.timer = setTimeout(() => el.classList.remove("show"), 4000);
}
