// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The SQL engine of live activities (web/engines/sql.js) on the vendored sql.js, in Node, started
// as the evaluator's worker starts it: the browser build loaded as a browser loads it - an ES
// module (a loader hook says so; Node alone would take it as CommonJS) - from the compiled
// WebAssembly module. The same result, the same key; only queries, on data no query changes; what
// went wrong; the summary; the comparison with a reference (engines/common.js).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import * as nodeModule from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web");
const BROWSER_LIKE = typeof nodeModule.registerHooks === "function";
if (BROWSER_LIKE) {
  nodeModule.registerHooks({
    load(url, context, nextLoad) {
      if (url.endsWith("/vendor/sqljs/sql-wasm-browser.js")) {
        return { format: "module", source: fs.readFileSync(new URL(url)), shortCircuit: true };
      }
      return nextLoad(url, context);
    },
  });
}
const sql = await import(pathToFileURL(path.join(web, "engines/sql.js")).href);
const { compare, key } = await import(pathToFileURL(path.join(web, "engines/common.js")).href);
const SQL = await sql.start(await WebAssembly.compile(fs.readFileSync(path.join(web, "vendor/sqljs/sql-wasm-browser.wasm"))));

const SEED = `CREATE TABLE professor (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE lecture (id INTEGER PRIMARY KEY, title TEXT NOT NULL, taught_by INTEGER REFERENCES professor (id), hours REAL);
INSERT INTO professor VALUES (1, 'Kant'), (2, 'Socrates'), (3, 'Popper');
INSERT INTO lecture VALUES (1, 'Foundations', 1, 2), (2, 'The Three Critiques', 1, 4), (3, 'Ethics', 2, 3.5);
`;
const state = sql.load(SQL, SEED);
const run = (q) => sql.evaluate(state, q);
const keyOf = (q) => {
  const r = run(q);
  assert.equal(r.status, "ok", `${q}: ${r.error}`);
  return key(r.canonical);
};
const JOIN = "SELECT p.name, l.title FROM professor p JOIN lecture l ON l.taught_by = p.id";

test("loaded as a browser loads it: an ES module, CommonJS's module only while it starts", async () => {
  assert.equal(typeof SQL.Database, "function");
  if (BROWSER_LIKE) {
    const ns = await import(pathToFileURL(path.join(web, "vendor/sqljs/sql-wasm-browser.js")).href);
    assert.deepEqual(Object.keys(ns), [], "a module that exports nothing, as in a browser");
    assert.equal(Object.hasOwn(globalThis, "module"), false);
  }
});

test("the same result, the same key - whatever the columns are called or the rows' order", () => {
  const k = keyOf(JOIN);
  assert.match(k, /^[0-9a-f]{16}$/);
  assert.equal(keyOf("SELECT name AS n, title AS t FROM lecture, professor WHERE taught_by = professor.id"), k);
  assert.equal(keyOf(`${JOIN} ORDER BY l.title DESC`), k);
  assert.equal(keyOf(`WITH pl AS (${JOIN}) SELECT * FROM pl`), k);
  assert.notEqual(keyOf("SELECT l.title, p.name FROM professor p JOIN lecture l ON l.taught_by = p.id"), k,
    "the columns' order counts");
  assert.notEqual(keyOf("SELECT p.name FROM professor p JOIN lecture l ON l.taught_by = p.id"),
    keyOf("SELECT DISTINCT p.name FROM professor p JOIN lecture l ON l.taught_by = p.id"), "a bag: repeated rows count");
  assert.equal(keyOf("VALUES (1), (2)"), keyOf("SELECT 2 UNION ALL SELECT 1"));
});

test("a value: a number by its value, a text as written, NULL", () => {
  assert.equal(keyOf("SELECT 7"), keyOf("SELECT 7.0"));
  assert.equal(keyOf("SELECT AVG(hours) FROM lecture"), keyOf("SELECT SUM(hours) / COUNT(*) FROM lecture"));
  assert.notEqual(keyOf("SELECT 7"), keyOf("SELECT '7'"), "a number is no text");
  assert.notEqual(keyOf("SELECT 'Kant'"), keyOf("SELECT 'kant'"));
  assert.notEqual(keyOf("SELECT NULL"), keyOf("SELECT ''"));
  assert.notEqual(keyOf("SELECT 1 / 2"), keyOf("SELECT 1 / 2.0"), "SQLite's integer division gives 0");
});

test("only queries, one at a time, on data that no query changes", () => {
  for (const q of ["DELETE FROM lecture", "DROP TABLE lecture", "UPDATE professor SET name = 'Hegel'",
    "WITH x AS (SELECT 1) DELETE FROM lecture", "PRAGMA query_only = OFF", "ATTACH ':memory:' AS other",
    "CREATE TEMP TABLE t (x)", "SELECT 1; DELETE FROM lecture", "EXPLAIN SELECT * FROM lecture"]) {
    assert.equal(run(q).status, "refused", q);
  }
  assert.match(run("SELECT 1; SELECT 2").error, /one statement/);
  assert.equal(run("SELECT COUNT(*) FROM lecture").summary.rows[0][0], "3");
  assert.equal(run("SELECT name FROM professor WHERE id = 1").summary.rows[0][0], "Kant");
  assert.equal(run("-- the professors\nSELECT name FROM professor;").status, "ok", "a comment in front, a semicolon behind");
});

test("what went wrong: a syntax error, an unknown table or column, a runaway query", () => {
  const syntax = run("SELEC name FROM professor");
  assert.equal(syntax.status, "syntax");
  assert.match(syntax.error, /near "SELEC": syntax error/);
  assert.equal(run("SELECT name FROM professor WHERE").status, "syntax");
  assert.equal(run("SELECT 'Kant").status, "syntax");
  assert.equal(run("").status, "syntax");
  assert.deepEqual(run("SELECT nme FROM professor"), { status: "error", error: "no such column: nme" });
  assert.deepEqual(run("SELECT * FROM prof"), { status: "error", error: "no such table: prof" });
  const runaway = run("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT x FROM c");
  assert.equal(runaway.status, "error");
  assert.match(runaway.error, /more than 100000 rows/);
});

test("the summary: the columns as the query names them, the first rows in its order, the count", () => {
  const s = run(`${JOIN} ORDER BY p.name, l.title`).summary;
  assert.equal(s.kind, "select");
  assert.deepEqual(s.columns, ["name", "title"]);
  assert.equal(s.count, 3);
  assert.deepEqual(s.rows[0], ["Kant", "Foundations"]);
  assert.deepEqual(run("SELECT NULL, 1.5, x'00ff', 0.1 + 0.2").summary.rows[0], ["NULL", "1.5", "x'00ff'", "0.3"]);
  const many = run("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 500) SELECT x, printf('%.200c', '*') FROM c");
  assert.equal(many.summary.count, 500);
  assert.ok(JSON.stringify(many.summary).length <= 11000 && many.summary.rows.length <= 20);
});

test("a result against the reference's: the rows in both, missing, more", () => {
  const reference = run(JOIN);
  assert.deepEqual(compare(run(JOIN), reference), { common: 3, missing: 0, extra: 0 });
  const cross = run("SELECT p.name, l.title FROM professor p, lecture l");
  assert.deepEqual(compare(cross, reference), { common: 3, missing: 0, extra: 6 });
  const one = run(`${JOIN} WHERE p.name = 'Socrates'`);
  assert.deepEqual(compare(one, reference), { common: 1, missing: 2, extra: 0 });
});

test("a seed that does not run says so", () => {
  assert.throws(() => sql.load(SQL, "CREATE TABLE x ("), /^Error: the seed: /);
});
