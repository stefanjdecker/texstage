// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// What the presenter window says when the server refuses one of its messages (web/stage/presenter.js:
// sendTyped, alertError, alertText), in Node: a control or an act of a live activity that the activity
// framework's core refuses in the core's words for the lecturer (presenter.steps.refused, by the refusal's
// code), in the deck's language - not a quiz question's words, which a code may share -; anything else as
// ever (errorText), and one dialog for one refusal. The functions are presenter.js's own, run as they are
// written there (the module itself runs only in a browser).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web");
const { CATALOGS, errorText } = await import(pathToFileURL(path.join(web, "i18n/i18n.js")).href);
const { refusedText } = await import(pathToFileURL(path.join(web, "stage/activities.js")).href);
const source = fs.readFileSync(path.join(web, "stage/presenter.js"), "utf8");

function cut(from, to) {
  // presenter.js from a line that starts with `from` up to the next that starts with `to`
  const start = source.indexOf(`\n${from}`), end = source.indexOf(`\n${to}`, start + 1);
  assert.ok(start > 0 && end > start, `presenter.js: ${from} ... ${to}`);
  return source.slice(start, end);
}

// the window over a deck: its language, its deck's activity type, the server's answer to every message, and the
// dialogs it shows (tell)
function windowOf({ lang = "en", activities = "core", answer }) {
  const told = [];
  let release;
  const context = vm.createContext({
    lang, deck: { activities }, errorText, refusedText,
    client: { send: () => answer() },
    tell: (text) => { told.push(text); return new Promise((done) => { release = done; }); },
  });
  vm.runInContext([
    source.match(/^const core = .*$/m)[0],
    cut("function why(err)", "}") + "\n}",
    cut("function sendTyped(msg)", "// the server's time while connected"),
  ].join("\n"), context);
  return { told, send: (msg) => context.sendTyped(msg), close: () => release?.() };
}

const refusal = (code, message = "the server's words, for a log") => Object.assign(new Error(message), { code });
const later = () => new Promise((done) => setTimeout(done, 0));

test("a control or an act the core refuses: the core's words for the lecturer, in the deck's language", async () => {
  for (const lang of ["en", "de"]) {
    const table = CATALOGS[lang].presenter.steps.refused;
    assert.ok(Object.keys(table).length >= 10, lang);
    for (const [code, words] of Object.entries(table)) {
      const w = windowOf({ lang, answer: () => Promise.reject(refusal(code)) });
      await w.send({ t: "activity.moderate", activity: "q", act: "hide", group: "g" });
      assert.deepEqual(w.told, [words], `${lang}: ${code}`);
    }
  }
  // the words of a quiz question's refusal are not the activity's, though the code is the same
  const w = windowOf({ lang: "de", answer: () => Promise.reject(refusal("closed")) });
  await w.send({ t: "activity.open", activity: "q" });
  assert.deepEqual(w.told, ["Die Aktivität ist nicht offen."]);
  assert.notEqual(w.told[0], errorText("de", { code: "closed" }));
});

test("anything else as ever: a code the core's table lacks, a quiz's message, F1's type", async () => {
  const cases = [
    [{ lang: "de", answer: () => Promise.reject(refusal("invalid", "act: one of hide, approve")) }, { t: "activity.moderate" },
      "Das hat nicht geklappt: act: one of hide, approve"],
    [{ lang: "en", answer: () => Promise.reject(refusal("closed")) }, { t: "round.skip" }, errorText("en", { code: "closed" })],
    [{ lang: "en", activities: "f1", answer: () => Promise.reject(refusal("closed")) }, { t: "activity.open" },
      errorText("en", { code: "closed" })],
    [{ lang: "de", answer: () => Promise.reject(new Error("offline")) }, { t: "activity.close" }, "Das hat nicht geklappt: offline"],
  ];
  for (const [how, msg, words] of cases) {
    const w = windowOf(how);
    await w.send(msg);
    assert.deepEqual(w.told, [words], JSON.stringify(msg));
  }
});

test("no dialog for what needs none; one dialog for one refusal", async () => {
  const quiet = windowOf({ answer: () => Promise.reject(refusal("no-round")) });
  await quiet.send({ t: "round.reveal" });
  assert.deepEqual(quiet.told, [], "no question asked yet: nothing to say");
  const fine = windowOf({ answer: () => Promise.resolve({ ok: true }) });
  assert.deepEqual(await fine.send({ t: "activity.open", activity: "q" }), { ok: true });
  assert.deepEqual(fine.told, []);
  const twice = windowOf({ lang: "de", answer: () => Promise.reject(refusal("no-group")) });
  await Promise.all([twice.send({ t: "activity.moderate" }), twice.send({ t: "activity.moderate" })]);
  assert.deepEqual(twice.told, [CATALOGS.de.presenter.steps.refused["no-group"]], "the same refusal twice: one dialog");
  twice.close();
  await later();
  await twice.send({ t: "activity.moderate" });
  assert.equal(twice.told.length, 2, "closed, it may come again");
});
