// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The SQL engine of live activities (docs/live-activities-design.md, sections 8.3 and 8.8): SQLite
// (sql.js, web/vendor/sqljs) over the activity's seed - a script of CREATE TABLE and INSERT
// statements -, in the evaluator's worker (stage/evaluator-worker.js; the engines: index.js).
//
//   start(wasm)             sql.js, from the window's compiled WebAssembly module
//   load(SQL, seed)         the seed run into a database of its own, which is read-only from then on
//   evaluate(state, text, language)
//                           -> {status: ok | syntax | error | refused, error?, canonical?, rows?, summary?}
//                              (error: why, in the deck's language - i18n's "engines" -, SQLite's words after it)
//
// A query is one statement - SELECT, VALUES or WITH ... SELECT -; anything else is refused, and the
// database is read-only besides (PRAGMA query_only): no query changes what the next one sees. The
// same result, the same canonical form: the rows as a bag - their order does not count, repeated
// rows do -, the columns in the order the query gives them, their names not; a number by its value
// (7 and 7.0 alike; a fraction to 15 significant digits, so that two ways of computing an average
// agree), a text as written, NULL, a blob by its bytes. A number and a text with the same digits
// differ, as they do in SQL.

import { texts } from "../i18n/i18n.js";
import { bounded, cut, ROWS } from "./common.js";

export const NAME = "sql";
const MAX_ROWS = 100_000;          // more is an error, not a result: a join condition forgotten on large tables
const QUERY = /^(?:select|values|with)\b/i;
const LEADING = /^(?:\s+|--[^\n]*(?:\n|$)|\/\*[\s\S]*?(?:\*\/|$))*/;       // spaces and comments in front

let initSqlJs = null;

export async function start(wasm) {
  // sql.js's browser build is a UMD script, kept as published (web/vendor/README.md): a browser
  // imports it as a module that exports nothing, so it runs with CommonJS's `module` and
  // `exports` in place - which it also sets while it starts. Node loads it as CommonJS (the
  // tests) and gives it as the default export.
  const shim = !Object.hasOwn(globalThis, "module");
  if (shim) {
    globalThis.module = { exports: {} };
    globalThis.exports = globalThis.module.exports;
  }
  try {
    if (!initSqlJs) {
      const ns = await import("../vendor/sqljs/sql-wasm-browser.js");
      initSqlJs = typeof ns.default === "function" ? ns.default : globalThis.module.exports;
      if (typeof initSqlJs !== "function") throw new Error("sql.js did not load");
    }
    let failed;
    const failure = new Promise((_, reject) => { failed = reject; });
    return await Promise.race([failure, initSqlJs({
      instantiateWasm(imports, done) {
        WebAssembly.instantiate(wasm, imports).then((instance) => done(instance, wasm), failed);
        return {};
      },
    })]);
  } finally {
    if (shim) {
      delete globalThis.module;
      delete globalThis.exports;
    }
  }
}

export function load(SQL, seed) {
  const db = new SQL.Database();
  try {
    db.exec(seed);
  } catch (e) {
    db.close();
    throw new Error(`the seed: ${String(e?.message ?? e)}`);
  }
  db.exec("PRAGMA query_only = ON");
  return { db };
}

// ------------------------------------------------------------------ values
const hex = (bytes) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
const number = (v, digits) => (Number.isInteger(v) || !Number.isFinite(v) ? String(v) : String(Number(v.toPrecision(digits))));

function term(v) {
  if (v === null || v === undefined) return "NULL";
  if (typeof v === "number") return `n:${number(v, 15)}`;
  if (typeof v === "bigint") return `n:${v}`;
  if (v instanceof Uint8Array) return `x:${hex(v)}`;
  return `t:${JSON.stringify(String(v))}`;
}

function show(v) {
  if (v === null || v === undefined) return "NULL";
  if (typeof v === "number") return number(v, 12);
  if (v instanceof Uint8Array) return cut(`x'${hex(v)}'`);
  return cut(String(v));
}

// ------------------------------------------------------------------ the keyword PRAGMA
// SQLite carries out many pragmas as it compiles them - PRAGMA query_only = OFF among them -, and
// evaluate compiles every statement to count them: a text with the keyword PRAGMA is refused before
// that, or it would make the database writable for every text after it (a WITH ... DELETE emptied it).
// A word as SQLite reads the text: not in a string, a quoted name, a comment or a parameter
// ($a(x;y) is one), a byte order mark where a token starts a space, and only up to a NUL, where
// SQLite's text ends. The server's check reads it alike (texstage/checks/sql.py: names_pragma).
const ID = /[A-Za-z0-9_$\u0080-\uffff]/;

export function namesPragma(text) {
  const nul = text.indexOf("\0");
  const t = nul === -1 ? text : text.slice(0, nul);
  const n = t.length;
  let i = 0;
  while (i < n) {
    const c = t[i];
    if ("$@:#".includes(c)) {                           // a parameter, with SQLite's (TCL's) a(...) and a::b
      let j = i + 1;
      let letters = 0;
      while (j < n) {
        if (ID.test(t[j])) {
          j += 1;
          letters += 1;
        } else if (t[j] === "(" && letters) {
          j += 1;
          while (j < n && !" \t\n\v\f\r)".includes(t[j])) j += 1;
          if (j < n && t[j] === ")") j += 1;
          break;
        } else if (t.startsWith("::", j)) {
          j += 2;
        } else {
          break;
        }
      }
      i = j;
    } else if (c === "\ufeff") {
      i += 1;
    } else if (ID.test(c)) {                            // a name, a keyword, a number: one word
      let j = i + 1;
      while (j < n && ID.test(t[j])) j += 1;
      if (/^pragma$/i.test(t.slice(i, j))) return true;
      i = j;
    } else if (c === "'" || c === '"' || c === "`") {
      let j = i + 1;
      for (;;) {
        j = t.indexOf(c, j);
        if (j === -1 || t[j + 1] !== c) break;
        j += 2;                                          // a doubled quote inside
      }
      i = j === -1 ? n : j + 1;
    } else if (c === "[") {
      const j = t.indexOf("]", i + 1);
      i = j === -1 ? n : j + 1;
    } else if (t.startsWith("--", i)) {
      const j = t.indexOf("\n", i);
      i = j === -1 ? n : j + 1;
    } else if (t.startsWith("/*", i)) {
      const j = t.indexOf("*/", i + 2);
      i = j === -1 ? n : j + 2;
    } else {
      i += 1;
    }
  }
  return false;
}

// ------------------------------------------------------------------ evaluation
function failure(e, W) {
  const text = String(e?.message ?? e).split("\n")[0];
  if (/readonly database/.test(text)) return { status: "refused", error: W.changesData };
  if (/syntax error|incomplete input|unrecognized token/.test(text)) return { status: "syntax", error: text };
  return { status: "error", error: text };
}

export function evaluate(state, text, language) {
  const { db } = state;
  const W = texts(language).engines;
  if (namesPragma(text)) return { status: "refused", error: W.queriesOnly };
  let statements = 0;
  try {
    for (const s of db.iterateStatements(text)) {
      s.free();
      statements += 1;
    }
  } catch (e) {
    return failure(e, W);
  }
  if (statements === 0) return { status: "syntax", error: W.noStatement };
  if (statements > 1) return { status: "refused", error: W.oneStatement };
  if (!QUERY.test(text.replace(LEADING, ""))) {
    return { status: "refused", error: W.queriesOnly };
  }
  let stmt;
  try {
    stmt = db.prepare(text);
  } catch (e) {
    return failure(e, W);
  }
  try {
    const columns = stmt.getColumnNames();
    const rows = [];
    const shown = [];
    while (stmt.step()) {
      if (rows.length === MAX_ROWS) return { status: "error", error: `more than ${MAX_ROWS} rows` };
      const values = stmt.get();
      rows.push(values.map(term).join("\t"));
      if (shown.length < ROWS) shown.push(values.map(show));
    }
    rows.sort();
    return { status: "ok", canonical: `select\n${columns.length}\n${rows.join("\n")}`, rows,
      summary: bounded({ kind: "select", columns: columns.map(cut), count: rows.length, rows: shown }) };
  } catch (e) {
    return failure(e, W);
  } finally {
    stmt.free();
  }
}
