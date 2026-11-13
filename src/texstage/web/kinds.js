// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The deck's kinds in the browser (docs/architecture/activity-framework-design.md, 7.3 and 7.4; the
// plan of F2, 4.5): their texts and their modules, from the server's /kinds/<hash>/... (its
// kindfiles.py) - cached for ever, since the hash is that of their contents; the kinds of one package
// share it, so a file they share comes once. A page learns the deck's kinds from its welcome, or a window
// from the deck's view (kindFiles: {name: {hash, phone, window}}); a phone loads all of a kind's files in
// the background when it joins - its hints too, which a worker takes from the browser's cache when a
// step opens -, not in the second a step opens on 1,000 phones.
//
//   const kinds = new Kinds(welcome.kindFiles, language, "phone");   // or "window"
//   await kinds.ready;                                              // their texts, their modules
//   kinds.say(name, {code, args})                                   // a check's message in words
//   kinds.status(name, "ok")                                        // the kind's own word for a status, or null
//   kinds.module(name, "input" | "box")                             // a kind's module, or null
//   kinds.hints(name)                                               // a Hints for a step's text, or null
//
// A kind's text is a function of the message's arguments; a code it has no text for is said as it is. Its
// own words for a status are the texts' keys "<kind>:<status>" (no code has a colon), e.g. "turtle-graph:ok".

export const HINT_MS = 300;          // a hint is asked for this long after the last key

export const kindURL = (entry, path) => `/kinds/${encodeURIComponent(entry.hash)}/${path}`;

export function textsPath(files, language) {
  // the texts a page takes: the deck's language, else English, else none
  const lang = String(language || "en").toLowerCase().startsWith("de") ? "de" : "en";
  return [`texts/${lang}.js`, "texts/en.js"].find((p) => files.includes(p)) || null;
}

export class Kinds {
  // load, get: how a module is imported and a file fetched (the tests give their own)
  constructor(entries = {}, language = "en", side = "phone",
    { load = (u) => import(u), get = (u) => fetch(u).then((r) => r.arrayBuffer()) } = {}) {
    this.entries = entries || {};
    this.side = side;
    this.texts = {};                 // name -> {code: (args) => words}
    this.modules = {};               // name -> {input, box}
    this.importer = load;
    this.getter = get;
    this.fetching = [];              // the rest of a phone's files, on their way into the cache
    this.ready = this.load(language);
  }

  files(name) {
    const e = this.entries[name] || {};
    return this.side === "window" ? [...(e.phone || []), ...(e.window || [])] : [...(e.phone || [])];
  }

  async load(language) {
    const fetched = new Set();       // (kinds of one package: their files once)
    await Promise.all(Object.entries(this.entries).map(async ([name, entry]) => {
      const files = this.files(name);
      const texts = textsPath(files, language);
      try {
        if (texts) this.texts[name] = (await this.importer(kindURL(entry, texts))).default || {};
      } catch (err) {
        console.warn(`texstage: the texts of the kind ${name} did not load`, err);
      }
      this.modules[name] = {};
      for (const [which, path] of [["input", "web/input.js"], ["box", "web/box.js"]]) {
        if (!files.includes(path)) continue;
        try {
          this.modules[name][which] = await this.importer(kindURL(entry, path));
        } catch (err) {
          console.warn(`texstage: the ${which} of the kind ${name} did not load`, err);
        }
      }
      if (this.side !== "phone") return;
      for (const path of files) {    // the rest - hint.js and what it imports - into the browser's cache
        const url = kindURL(entry, path);
        if (path.startsWith("texts/") || path === "web/input.js" || fetched.has(url)) continue;
        fetched.add(url);
        this.fetching.push(Promise.resolve().then(() => this.getter(url)).catch(() => {}));   // (no hint: none)
      }
    }));
    return this;
  }

  say(name, message) {
    // a check's message in words: the kind's text for its code, made with its arguments
    if (!message || typeof message !== "object") return "";
    const text = this.texts[name]?.[message.code];
    try {
      if (typeof text === "function") return String(text(message.args || {}));
      if (typeof text === "string") return text;
    } catch { /* a text that cannot be made: its code */ }
    return String(message.code ?? "");
  }

  status(name, status) {
    // the kind's own word for a check's status - a Turtle text is valid, it does not run -, or null
    const text = this.texts[name]?.[`${name}:${status}`];
    try {
      if (typeof text === "function") return String(text({}));
      if (typeof text === "string") return text;
    } catch { /* the core's word */ }
    return null;
  }

  module(name, which) {
    return this.modules[name]?.[which] || null;
  }

  hints(name) {
    // a kind's hint.js runs in a Web Worker: a slow hint never holds up typing
    const entry = this.entries[name];
    if (!entry || !this.files(name).includes("web/hint.js") || typeof Worker === "undefined") return null;
    return new Hints(kindURL(entry, "web/hint.js"));
  }
}

// A kind's hints for a step's text: asked HINT_MS after the last key, in a module worker
// (play/hint-worker.js imports the kind's hint.js; its policy lets it import from the server alone); a key
// counts, so that a hint that comes for a text that is no longer there is dropped. -> onHint(null | {code,
// args, at}). What goes to the worker is data alone: the step's public part, the text, the deck's language.
export class Hints {
  constructor(module, onHint = () => {}, make = (url) => new Worker(url, { type: "module" })) {
    this.onHint = onHint;
    this.asked = 0;
    this.timer = null;
    this.worker = make(`/static/play/hint-worker.js?module=${encodeURIComponent(module)}`);
    this.worker.onmessage = (e) => { if (e.data?.n === this.asked) this.onHint(e.data.hint ?? null); };
    this.worker.onerror = () => { this.onHint(null); };
  }

  ask(step, text, words) {
    const n = ++this.asked;          // (a reply to an earlier key is no longer this text's)
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      try {
        this.worker.postMessage({ n, step, text, words });
      } catch {
        this.onHint(null);           // (what cannot be sent: no hint)
      }
    }, HINT_MS);
  }

  destroy() {
    clearTimeout(this.timer);
    this.worker.terminate();
  }
}
