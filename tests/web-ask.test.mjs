// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The presenter's dialogs (stage/ask.js) with dialogs on top of each other: only the top one takes the keys.
// One Enter answered them all - a message's OK said yes to the question under it (the 2026-11 review: A6).
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

// a page as ask.js uses it: dialogs appended to the body, keydown listeners on the document, the focus
const listeners = [];
const dialogs = [];
const button = (answer) => ({ answer, onclick: null, focus() { globalThis.document.activeElement = this; },
  addEventListener(type, fn) { if (type === "click") this.onclick = fn; } });
globalThis.document = {
  activeElement: null,
  addEventListener: (type, fn) => listeners.push({ type, fn }),
  removeEventListener: (type, fn) => { const i = listeners.findIndex((l) => l.type === type && l.fn === fn); if (i >= 0) listeners.splice(i, 1); },
  createElement: () => {
    const el = { className: "", setAttribute() {}, parts: {},
      set innerHTML(html) {
        this.parts.yes = button("yes");
        this.parts.no = html.includes('data-answer="no"') ? button("no") : null;
      },
      querySelector(sel) {
        return sel === '[data-answer="yes"]' ? this.parts.yes : sel === '[data-answer="no"]' ? this.parts.no : null;
      },
      remove() { dialogs.splice(dialogs.indexOf(this), 1); } };
    return el;
  },
  body: { append: (el) => dialogs.push(el) },
  querySelectorAll: (sel) => (sel === ".dialog" ? [...dialogs] : []),
};

function press(key) {               // as a browser dispatches it: every listener of the node, in order
  const e = { key, stopPropagation() {}, preventDefault() {} };
  for (const l of [...listeners]) if (l.type === "keydown" && listeners.includes(l)) l.fn(e);
}

const { ask, tell } = await import(pathToFileURL(path.join(here, "../src/texstage/web/stage/ask.js")).href);

test("one Enter answers the top dialog only - a message over a question leaves the question open", async () => {
  const answers = [];
  ask("Delete the recording?", "Delete").then((a) => answers.push(["ask", a]));
  tell("The connection was lost.").then((a) => answers.push(["tell", a]));
  press("Enter");
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(answers, [["tell", true]]);
  assert.equal(dialogs.length, 1);                       // the question is still there
  press("Escape");
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(answers, [["tell", true], ["ask", false]]);
  assert.equal(dialogs.length, 0);
});

test("Enter with the focus on No answers no", async () => {
  const answer = ask("Reset the timer?", "Reset");
  dialogs[0].parts.no.focus();
  press("Enter");
  assert.equal(await answer, false);
  const again = ask("Reset the timer?", "Reset");
  press("Enter");                                        // the focus on Yes, as it opens
  assert.equal(await again, true);
});
