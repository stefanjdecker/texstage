// SPDX-License-Identifier: Apache-2.0
// Run against an isolated server serving the bilingual database example.
// Required: TEXSTAGE_TEST_BASE, TEXSTAGE_EXAMPLE_OUT, TEXSTAGE_TEST_KEY_FILE.
// Optional: TEXSTAGE_PLAYWRIGHT_MODULE, BROWSER, TEXSTAGE_TEST_OUTPUT.
const fs = require("node:fs"), path = require("node:path"), assert = require("node:assert/strict");
const pw = require(process.env.TEXSTAGE_PLAYWRIGHT_MODULE || "playwright");
const family = process.env.BROWSER || "chromium", base = process.env.TEXSTAGE_TEST_BASE;
const out = process.env.TEXSTAGE_EXAMPLE_OUT, keyFile = process.env.TEXSTAGE_TEST_KEY_FILE;
if (!base || !out || !keyFile) throw Error("Set the three required test environment variables.");
const key = fs.readFileSync(keyFile, "utf8").trim();
const output = path.resolve(process.env.TEXSTAGE_TEST_OUTPUT || "phone-language-results", family);
fs.mkdirSync(output, { recursive: true });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const decks = Object.fromEntries(["de", "en"].map(lang => [lang,
  JSON.parse(fs.readFileSync(path.join(out, (lang === "de" ? "database-de" : "database") + ".bundle", "deck.json"), "utf8"))]));
async function control(deck) {
  const ws = new WebSocket(base.replace(/^http/, "ws") + "/ws"), pending = new Map();
  controls.push({ close: () => ws.close() });
  const prefix = require("node:crypto").randomUUID();
  let seq = 0;
  ws.addEventListener("message", event => {
    const m = JSON.parse(event.data), item = pending.get(m.re);
    if (!item) {
      if (m.t === "error") console.error("Uncorrelated protocol error:", m.error, m.message);
      return;
    }
    pending.delete(m.re); clearTimeout(item.timer);
    if (m.t === "error") item.reject(Error(m.error + ": " + m.message)); else item.resolve(m);
  });
  ws.addEventListener("close", event => {
    for (const item of pending.values()) {
      clearTimeout(item.timer); item.reject(Error("Control socket closed: " + event.code));
    }
    pending.clear();
  });
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  const send = data => new Promise((resolve, reject) => {
    const id = prefix + "-" + (++seq);
    const timer = setTimeout(() => { pending.delete(id); reject(Error("Timeout: " + data.t)); }, 60000);
    pending.set(id, { resolve, reject, timer });
    ws.send(JSON.stringify({ ...data, id }));
  });
  await send({ t: "hello", role: "stage", key, deck: deck.deck, bundle: deck.bundle });
  // Every run uses fresh sessions on this disposable test server.
  const fresh = await send({ t: "lecture.new" });
  await send({ t: "slide", slide: deck.slides[0].id });
  return { pin: fresh.pin, send, close: () => ws.close() };
}
let browser, lastPage;
const controls = [], errors = [], checked = [];
(async () => {
  browser = await pw[family].launch({ headless: true });
  const byLanguage = {};
  for (const lang of ["de", "en"]) {
    const de = lang === "de", deck = decks[lang], ctl = await control(deck);
    byLanguage[lang] = ctl;
    const context = await browser.newContext({ locale: de ? "en-GB" : "de-DE",
      viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: family !== "firefox" });
    const phone = lastPage = await context.newPage();
    phone.on("pageerror", e => { errors.push(e.message); console.error("Phone error:", e.message); });
    assert.deepEqual(await (await fetch(base + "/api/join-language?pin=" + ctl.pin)).json(), { language: lang });
    await phone.goto(base + "/play?pin=" + ctl.pin);
    await phone.waitForFunction(lang => document.documentElement.lang === lang, lang);
    assert.equal(await phone.locator('label[for="nick"]').innerText(), de ? "Dein Spitzname" : "Your nickname");
    assert.equal(await phone.locator("#join button").innerText(), de ? "Mitspielen" : "Join");
    await phone.screenshot({ path: path.join(output, lang + "-join.png"), fullPage: true });
    const nickname = "Locale " + lang + " " + family + " " + Date.now();
    await phone.locator("#nick").fill(nickname);
    await phone.locator("#join button").click();
    await phone.getByRole("heading", { name: de ? "Du bist dabei!" : "You're in!", exact: true }).waitFor();
    assert.match(await phone.locator("#score").innerText(), de ? /Punkte$/ : /points$/);
    await phone.screenshot({ path: path.join(output, lang + "-lobby.png"), fullPage: true });
    await phone.reload();
    await phone.getByRole("heading", { name: de ? "Du bist dabei!" : "You're in!", exact: true }).waitFor();
    assert.equal(await phone.locator("html").getAttribute("lang"), lang);

    // A failed join is localized too. This page has no player's stored token.
    const otherContext = await browser.newContext({ locale: de ? "en-US" : "de-DE" });
    const other = await otherContext.newPage();
    await other.goto(base + "/play?pin=" + ctl.pin);
    await other.waitForFunction(lang => document.documentElement.lang === lang, lang);
    await other.locator("#nick").fill(nickname);
    await other.locator("#join button").click();
    await other.getByText(de ? "Dieser Spitzname ist bereits vergeben." : "This nickname is already taken.", { exact: true }).waitFor();

    await ctl.send({ t: "qa.open", on: true });
    await phone.locator('#tabs [data-tab="qa"]').click();
    await phone.getByLabel(de ? "Stell eine Frage – anonym." : "Ask a question – anonymously.", { exact: true }).waitFor();
    await phone.locator("#asktext").fill("Draft question");
    await ctl.send({ t: "timer", action: "reset", seconds: 0 });
    assert.equal(await phone.locator("#asktext").inputValue(), "Draft question");
    await phone.locator('#tabs [data-tab="quiz"]').click();
    await ctl.send({ t: "qa.open", on: false });

    const question = deck.slides.find(s => s.live?.some(b => b.type === "quiz" && b.phase === "question"));
    await ctl.send({ t: "slide", slide: question.id });
    await phone.locator(".answer").first().waitFor();
    assert.match(await phone.locator(".answer").first().getAttribute("aria-label"), de ? /^Antwort / : /^Answer /);
    await phone.locator(".answer").first().click();
    await phone.getByRole("heading", { name: de ? "Antwort abgeschickt" : "Answer sent", exact: true }).waitFor();

    // Move away from the quiz before opening a built-in activity.
    const answer = question.live.find(b => b.type === "quiz").item;
    const reveal = deck.slides.find(s => s.live?.some(b => b.type === "quiz" && b.phase === "reveal" && b.item === answer));
    await ctl.send({ t: "slide", slide: reveal.id });
    const sqlId = Object.keys(deck.items.activity).find(id => deck.items.activity[id].engine === "sql");
    const sqlSlide = deck.slides.find(s => s.live?.some(b => b.type === "activity" && b.item === sqlId));
    await ctl.send({ t: "slide", slide: sqlSlide.id });
    await ctl.send({ t: "activity.open", activity: sqlId });
    await phone.getByLabel(de ? "Deine Anfrage" : "Your query", { exact: true }).waitFor();
    assert.match(await phone.locator("form.act button.main").innerText(), de ? /^Abschicken/ : /^Send/);
    await phone.locator("#act-text").fill("SELECT draft FROM catalogue;");
    await ctl.send({ t: "timer", action: "reset", seconds: 0 });
    assert.equal(await phone.locator("#act-text").inputValue(), "SELECT draft FROM catalogue;");
    assert.equal(await phone.locator("#act-text").evaluate(el => el === document.activeElement), true);
    await phone.screenshot({ path: path.join(output, lang + "-sql.png"), fullPage: true });
    checked.push({ language: lang, browserLocale: de ? "en-GB" : "de-DE",
      join: true, lobby: true, resume: true, duplicateNickname: true, qa: true, quiz: true, sql: true, drafts: true });
    await otherContext.close();
    await context.close();
  }

  // A delayed lookup for the previous PIN must not overwrite the current one,
  // replace the student's input, or move focus.
  const context = await browser.newContext({ locale: "en-GB" }), manual = await context.newPage();
  await manual.route("**/api/join-language?pin=*", async route => {
    const response = await route.fetch();
    if (new URL(route.request().url()).searchParams.get("pin") === byLanguage.de.pin) await delay(700);
    await route.fulfill({ response });
  });
  await manual.goto(base + "/play");
  await manual.locator("#nick").fill("Kept nickname");
  await manual.locator("#pin").fill(byLanguage.de.pin);
  await manual.locator("#nick").focus();
  await manual.waitForFunction(() => document.documentElement.lang === "de");
  assert.equal(await manual.locator("#nick").inputValue(), "Kept nickname");
  assert.equal(await manual.locator("#nick").evaluate(el => el === document.activeElement), true);
  await manual.locator("#pin").fill("");
  await manual.locator("#pin").fill(byLanguage.de.pin);
  await delay(100);
  await manual.locator("#pin").fill(byLanguage.en.pin);
  await manual.locator("#nick").focus();
  await manual.waitForFunction(() => document.documentElement.lang === "en");
  await delay(800);
  assert.equal(await manual.locator("html").getAttribute("lang"), "en");
  assert.equal(await manual.locator("#nick").inputValue(), "Kept nickname");
  assert.equal(await manual.locator("#nick").evaluate(el => el === document.activeElement), true);
  assert.equal(await manual.locator("#join button").innerText(), "Join");
  await context.close();
  assert.deepEqual(errors, []);
  const result = { family, version: browser.version(), checked, manualPin: true, staleLookup: true, pageErrors: errors };
  fs.writeFileSync(path.join(output, "report.json"), JSON.stringify(result, null, 2) + "\n");
  console.log(JSON.stringify(result));
})().catch(async error => {
  console.error(error);
  if (lastPage && !lastPage.isClosed()) {
    await lastPage.screenshot({ path: path.join(output, "failure.png"), fullPage: true }).catch(() => {});
    console.error("Phone at failure:", await lastPage.locator("body").innerText().catch(() => "unavailable"));
  }
  process.exitCode = 1;
}).finally(async () => {
  for (const ctl of controls) ctl.close();
  if (browser) await browser.close();
});
