// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The SPARQL engine of live activities (web/engines/sparql.js) on the vendored Oxigraph - the
// browser build, in Node, started as the evaluator's worker starts it (from the compiled
// WebAssembly module): the same result, the same key; the seed's prefixes; what went wrong, with
// the student's line numbers; the summary; the comparison with a reference (engines/common.js).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web");
const sparql = await import(pathToFileURL(path.join(web, "engines/sparql.js")).href);
const { compare, key } = await import(pathToFileURL(path.join(web, "engines/common.js")).href);
const ox = await sparql.start(await WebAssembly.compile(fs.readFileSync(path.join(web, "vendor/oxigraph/web_bg.wasm"))));

const SEED = `@base <http://data.rwth-aachen.de/resources/> .
@prefix : <> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
:kant a :Professor ; :name "Kant" .
:socrates a :Professor ; :name "Socrates" .
:popper a :Professor ; :name "Popper" .
:l1 :taughtBy :kant ; :title "Foundations" .
:l2 :taughtBy :kant ; :title "The Three Critiques" .
:l3 :taughtBy :socrates ; :title "Ethics" .
`;
const state = sparql.load(ox, SEED);
const run = (q) => sparql.evaluate(state, q);
const keyOf = (q) => {
  const r = run(q);
  assert.equal(r.status, "ok", `${q}: ${r.error}`);
  return key(r.canonical);
};
const JOIN = "SELECT ?name ?title WHERE { ?p a :Professor ; :name ?name . ?l :taughtBy ?p ; :title ?title }";

test("the same result, the same key - whatever the variables are called or the rows' order", () => {
  const k = keyOf(JOIN);
  assert.match(k, /^[0-9a-f]{16}$/);
  assert.equal(keyOf("SELECT ?n ?t WHERE { ?l :title ?t ; :taughtBy ?x . ?x :name ?n ; a :Professor }"), k);
  assert.equal(keyOf(`${JOIN} ORDER BY DESC(?title)`), k);
  assert.notEqual(keyOf("SELECT ?title ?name WHERE { ?p a :Professor ; :name ?name . ?l :taughtBy ?p ; :title ?title }"), k,
    "the columns' order counts");
  assert.notEqual(keyOf("SELECT ?name WHERE { ?p a :Professor ; :name ?name . ?l :taughtBy ?p }"),
    keyOf("SELECT DISTINCT ?name WHERE { ?p a :Professor ; :name ?name . ?l :taughtBy ?p }"), "a bag: repeated rows count");
  assert.equal(keyOf("ASK { :kant :name \"Kant\" }"), keyOf("ASK { :socrates a :Professor }"));
  assert.notEqual(keyOf("ASK { :kant :name \"Kant\" }"), keyOf("ASK { :kant :name \"Plato\" }"));
});

test("a query gets the seed's BASE and PREFIX lines unless it declares them itself", () => {
  assert.equal(run("SELECT ?n WHERE { ?p :name ?n }").rows.length, 3);
  assert.equal(run("PREFIX : <http://example.org/>\nSELECT ?n WHERE { ?p :name ?n }").rows.length, 0);
});

test("what went wrong: the student's line and column, SERVICE not run, an update is no query", () => {
  const syntax = run("SELECT ?n\nWHER { ?p :name ?n }");
  assert.equal(syntax.status, "syntax");
  assert.match(syntax.error, /^line 2, column \d+: /);
  assert.equal(run("SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }").status, "refused");
  assert.equal(run("INSERT DATA { :a :b :c }").status, "syntax");
  assert.equal(run("SELECT ?n WHERE { ?p :name ?n } GROUP BY ?p HAVING (?x").status, "syntax");
});

test("the summary: the columns, the first rows with the seed's prefixes, the count; a graph's triples", () => {
  const s = run(JOIN).summary;
  assert.deepEqual(s.columns, ["?name", "?title"]);
  assert.equal(s.count, 3);
  assert.deepEqual(new Set(s.rows.map((r) => r[0])), new Set(["Kant", "Socrates"]));
  const iri = run("SELECT ?p WHERE { ?p :name \"Kant\" }").summary.rows[0][0];
  assert.equal(iri, ":kant");
  const g = run("CONSTRUCT { ?p :teaches ?l } WHERE { ?l :taughtBy ?p }");
  assert.equal(g.status, "ok");
  assert.equal(g.summary.kind, "graph");
  assert.equal(g.summary.count, 3);
  assert.deepEqual(g.summary.rows[0].length, 3);
  assert.equal(run("ASK { :kant a :Professor }").summary.boolean, true);
  const many = run("SELECT ?a ?b ?c WHERE { ?a ?p1 ?b . ?b ?p2 ?c . ?c ?p3 ?d }");
  assert.ok(JSON.stringify(many.summary).length <= 11000 && many.summary.rows.length <= 20);
});

test("a result against the reference's: the rows in both, missing, more", () => {
  const reference = run(JOIN);
  assert.deepEqual(compare(run(JOIN), reference), { common: 3, missing: 0, extra: 0 });
  const cross = run("SELECT ?name ?title WHERE { ?p a :Professor ; :name ?name . ?l :title ?title }");
  assert.deepEqual(compare(cross, reference), { common: 3, missing: 0, extra: 6 });
  const one = run("SELECT ?name ?title WHERE { ?p :name ?name . ?l :taughtBy ?p ; :title ?title FILTER(?name = \"Kant\") }");
  assert.deepEqual(compare(one, reference), { common: 2, missing: 1, extra: 0 });
});

test("the key is FNV-1a over the UTF-8 bytes", () => {
  assert.equal(key(""), "cbf29ce484222325");
  assert.equal(key("a"), "af63dc4c8601ec8c");
});
