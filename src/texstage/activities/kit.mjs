// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The kit's browser half in Node (activities/kit.py: browser; docs/architecture/activity-framework-design.md,
// 7.5): a kind's texts in English and German, and its modules for the browser, loaded as a phone has them -
// a network that refuses, imports from the kind's folder alone (no Node module, no package), none of Node's
// own globals (process, Buffer, ...). kit.py runs it under Node's permission model, so that it reads the
// kind's folder and its own and writes nothing.
// The job comes on stdin - {token, home: the kind's folder, messages: {code: [argument names]}, texts: {en,
// de: a file}, modules: {path: [a file, the function it gives]}} -, what it found goes to stdout as one line,
// the token, a space and {faults, warnings}: what a module writes there itself is never taken for it.
// It finds a kind's mistakes; it is no sandbox for a module that means harm.
import * as modules from "node:module";
import { pathToFileURL } from "node:url";

const read = () => new Promise((ok) => {
  let s = "";
  process.stdin.on("data", (d) => { s += d; });
  process.stdin.on("end", () => ok(s));
});
const job = JSON.parse(await read());
const faults = [], warnings = [];
// what the kit itself needs, taken before a kind's module could change it
const write = process.stdout.write.bind(process.stdout);
const stringify = JSON.stringify;
const windows = process.platform === "win32";
const url = (file) => pathToFileURL(file).href;                // (as Node writes it: the same as it resolves to)
const home = job.home ? url(job.home).replace(/\/?$/, "/") : "";
const fold = (s) => (windows ? s.toLowerCase() : s);

const refuse = () => { throw new Error("a kind's module reaches no network"); };
for (const name of ["fetch", "WebSocket", "XMLHttpRequest", "EventSource"]) globalThis[name] = refuse;
for (const name of ["process", "Buffer", "global", "setImmediate", "clearImmediate"]) delete globalThis[name];   // (a phone has none)
const own = (specifier, parent) => {
  // whether an import leads into the kind's folder - looked at before Node looks for it, which may not read a
  // file elsewhere (the permission model) and would say so in its words: a path (./, ../, /) or a URL, never
  // a package's name
  if (!/^(\.{0,2}\/|[a-z][a-z0-9+.-]*:)/i.test(specifier)) return false;
  try {
    return fold(new URL(specifier, parent).href).startsWith(fold(home));
  } catch {
    return false;
  }
};
if (typeof modules.registerHooks === "function") {
  modules.registerHooks({
    resolve(specifier, context, next) {
      if (home && !own(specifier, context.parentURL)) throw new Error(`${specifier}: a kind's module imports only its own files`);
      const found = next(specifier, context);     // (and where it led: a link out of the folder)
      if (home && !fold(found.url).startsWith(fold(home))) throw new Error(`${specifier}: a kind's module imports only its own files`);
      return found;
    },
  });
} else {
  warnings.push("this Node cannot hook imports (22.15 and later can): what the modules import is not held to the kind's folder");
}

const loaded = {};
for (const [lang, file] of Object.entries(job.texts || {})) {
  try {
    loaded[lang] = (await import(url(file))).default;
  } catch (e) {
    faults.push(`texts/${lang}.js does not load: ${e?.message ?? e}`);
  }
}
for (const [lang, table] of Object.entries(loaded)) {
  if (!table || typeof table !== "object") {
    faults.push(`texts/${lang}.js: its default is no table of texts`);
    delete loaded[lang];
    continue;
  }
  for (const [code, names] of Object.entries(job.messages || {})) {
    const text = table[code];
    if (text === undefined) {
      faults.push(`texts/${lang}.js: no text for ${code}`);
      continue;
    }
    const args = Object.fromEntries(names.map((n, i) => [n, `<${n}:${i}>`]));
    let said;
    try {
      said = typeof text === "function" ? text(args) : text;
    } catch (e) {
      faults.push(`texts/${lang}.js: ${code} fails with its arguments - ${e?.message ?? e}`);
      continue;
    }
    if (typeof said !== "string" || !said) {
      faults.push(`texts/${lang}.js: ${code} gives no text`);
      continue;
    }
    for (const [n, v] of Object.entries(args)) if (!said.includes(v)) warnings.push(`texts/${lang}.js: ${code} does not say its ${n}`);
  }
}
if (loaded.en && loaded.de) {
  const en = Object.keys(loaded.en).sort().join(" "), de = Object.keys(loaded.de).sort().join(" ");
  if (en !== de) faults.push(`texts/en.js and texts/de.js have other keys: ${en || "none"} - ${de || "none"}`);
}
for (const [path, [file, name]] of Object.entries(job.modules || {})) {
  try {
    const m = await import(url(file));
    if (typeof m[name] !== "function") faults.push(`${path}: no function ${name}`);
  } catch (e) {
    faults.push(`${path} does not load in Node, as a phone has it: ${e?.message ?? e}`);
  }
}
write(`\n${job.token} ${stringify({ faults, warnings })}\n`);
