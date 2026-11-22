// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A deck uploaded by hand (docs/architecture/design.md, section 8): texstage build writes the whole deck as
// one file, <name>.bundle.zip next to its PowerPoint file. The deck lists of the host page and
// of texstage take it - a button, or the file dropped onto the page; several at once, a semester's
// chapters, one after the other - and send it to POST /api/bundles with the presenter key, so a
// server without the deck gets it from any browser, nothing to install.
//
//   uploadButton(el, auth, (message) => showDecks(false, message));   // the list again, with the outcome
//
// It speaks the page's language (i18n.js pageTexts: a list of decks, the browser's), the server's
// refusal by its code (errorText).

import { errorText, pageLanguage, pageTexts } from "/static/i18n/i18n.js";
import { authHeaders } from "/static/shared/client.js";

export function uploadButton(el, auth, done) {
  const U = pageTexts().upload;
  el.innerHTML = `<input type="file" accept=".zip" multiple hidden><button class="secondary"></button>`;
  const input = el.querySelector("input");
  const button = el.querySelector("button");
  button.title = U.title;
  button.textContent = U.button;
  button.onclick = () => input.click();
  input.onchange = () => { if (input.files.length) sendAll([...input.files]); };
  const page = el.closest(".page");
  if (page) {                                    // or dropped anywhere on the deck list
    const files = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
    page.addEventListener("dragover", (e) => {
      if (!files(e)) return;
      e.preventDefault();
      page.classList.add("dropping");
    });
    page.addEventListener("dragleave", (e) => { if (!page.contains(e.relatedTarget)) page.classList.remove("dropping"); });
    page.addEventListener("drop", (e) => {
      if (!files(e)) return;
      e.preventDefault();
      page.classList.remove("dropping");
      if (e.dataTransfer.files.length) sendAll([...e.dataTransfer.files]);
    });
  }

  async function sendAll(files) {               // one after the other; what became of each, in a line
    button.disabled = true;
    const said = [];
    for (const file of files) said.push(await send(file));
    done(said.join(" · "));
  }

  async function send(file) {
    const size = new Intl.NumberFormat(pageTexts().meta.locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
      .format(file.size / 1e6);
    button.textContent = U.uploading(file.name, size);
    try {
      const r = await fetch("/api/bundles", { method: "POST", body: file,
        headers: { ...authHeaders(auth), "Content-Type": "application/zip" } });
      const info = await r.json().catch(() => ({}));
      if (!r.ok) throw Object.assign(new Error(info.error || `HTTP ${r.status}`), { code: info.code });
      return info.new ? U.uploaded(info.name, info.quizzes, info.slides) : U.known(info.name);
    } catch (err) {
      return U.failed(file.name, errorText(pageLanguage(), err));
    }
  }
}
