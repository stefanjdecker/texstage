// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A deck uploaded by hand (docs/design.md, section 8): texstage build writes the whole deck as
// one file, <name>.bundle.zip next to its PowerPoint file. The deck lists of the host page and
// of texstage take it - a button, or the file dropped onto the page - and send it to
// POST /api/bundles with the presenter key, so a server without the deck gets it from any
// browser, nothing to install.
//
//   uploadButton(el, auth, (message) => showDecks(false, message));   // the list again, with the outcome

import { authHeaders } from "/static/shared/client.js";

export function uploadButton(el, auth, done) {
  el.innerHTML = `<input type="file" accept=".zip" hidden>
    <button class="secondary" title="the deck's .bundle.zip - texstage build writes it next to the PowerPoint file">Upload a deck</button>`;
  const input = el.querySelector("input");
  const button = el.querySelector("button");
  button.onclick = () => input.click();
  input.onchange = () => { if (input.files[0]) send(input.files[0]); };
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
      if (e.dataTransfer.files[0]) send(e.dataTransfer.files[0]);
    });
  }

  async function send(file) {
    button.disabled = true;
    button.textContent = `Uploading ${file.name} (${(file.size / 1e6).toFixed(1)} MB) ...`;
    let message;
    try {
      const r = await fetch("/api/bundles", { method: "POST", body: file,
        headers: { ...authHeaders(auth), "Content-Type": "application/zip" } });
      const info = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(info.error || `the server answered ${r.status}`);
      message = info.new ? `${info.name}: uploaded (${info.quizzes} quizzes, ${info.slides} slides)`
        : `${info.name}: the server has it already`;
    } catch (err) {
      message = `${file.name} was not uploaded: ${err.message || err}`;
    }
    done(message);
  }
}
