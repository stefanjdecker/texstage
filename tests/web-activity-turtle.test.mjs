// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The Turtle engine of live activities (web/engines/turtle.js) on the vendored Oxigraph, in Node,
// started as the evaluator's worker starts it: one graph in many spellings, one key - the key the
// SPARQL engine gives the same graph from a CONSTRUCT -; a graph is a set; blank nodes and a
// collection; what went wrong, at the student's line; the limits; the summary; the comparison
// with a reference (engines/common.js).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web");
const turtle = await import(pathToFileURL(path.join(web, "engines/turtle.js")).href);
const sparql = await import(pathToFileURL(path.join(web, "engines/sparql.js")).href);
const { compare, key } = await import(pathToFileURL(path.join(web, "engines/common.js")).href);
const ox = await turtle.start(await WebAssembly.compile(fs.readFileSync(path.join(web, "vendor/oxigraph/web_bg.wasm"))));

// the seed: chapter 3's prefixes - and a triple, which is no part of anybody's graph
const PREFIXES = `@prefix dbr: <http://dbpedia.org/resource/> .
@prefix dbo: <http://dbpedia.org/ontology/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
`;
const SEED = `${PREFIXES}dbr:Potsdam rdfs:label "Potsdam"@de .\n`;
const state = turtle.load(ox, SEED);
const run = (text) => turtle.evaluate(state, text);
const keyOf = (text) => {
  const r = run(text);
  assert.equal(r.status, "ok", `${text}: ${r.error}`);
  return key(r.canonical);
};

// three triples about Berlin (03-Serialization's running example), in four spellings
const FULL = `dbr:Berlin rdfs:label "Berlin"@de .
dbr:Berlin rdfs:label "Berlino"@it .
dbr:Berlin dbo:populationTotal 3596999 .`;
const SHORT = `dbr:Berlin rdfs:label "Berlin"@de , "Berlino"@it ;
  dbo:populationTotal 3596999 .`;
const TYPED = `dbr:Berlin rdfs:label "Berlin"@de , "Berlino"@it ;
  dbo:populationTotal "3596999"^^xsd:integer .`;
const IRIS = `<http://dbpedia.org/resource/Berlin> <http://www.w3.org/2000/01/rdf-schema#label> "Berlino"@IT, "Berlin"@de;
  <http://dbpedia.org/ontology/populationTotal> "3596999"^^<http://www.w3.org/2001/XMLSchema#integer>.`;
const LIST = "dbr:Berlin dbo:neighboringMunicipality ( dbr:Potsdam dbr:Teltow dbr:Falkensee ) .";

test("one graph, many spellings, one key - another graph, another key", () => {
  const k = keyOf(FULL);
  assert.match(k, /^[0-9a-f]{16}$/);
  for (const text of [SHORT, TYPED, IRIS]) assert.equal(keyOf(text), k, text);
  assert.equal(keyOf(`@prefix d: <http://dbpedia.org/resource/> .\nPREFIX l: <http://www.w3.org/2000/01/rdf-schema#>\n${
    FULL.replaceAll("dbr:", "d:").replaceAll("rdfs:", "l:")}`), k, "prefixes of the text's own");
  assert.equal(keyOf(SHORT.replace('"Berlin"@de', "“Berlin”@de").replace('"Berlino"@it', "„Berlino“@it")), k,
    "a phone keyboard's typographic quotes");
  assert.notEqual(keyOf(SHORT.replace("3596999", '"3596999"')), k, "a number as a string");
  assert.equal(keyOf(SHORT.replace("3596999", '"3596999"')), keyOf(SHORT.replace("3596999", '"3596999"^^xsd:string')),
    "a string is an xsd:string");
  assert.notEqual(keyOf(SHORT.replace("3596999", '"3596999"^^xsd:int')), k, "xsd:int is not xsd:integer");
  assert.notEqual(keyOf(SHORT.replace('"Berlin"@de', '"Berlin"')), k, "a language tag missing");
  assert.notEqual(keyOf(SHORT.replace("3596999", "03596999")), k, "a literal counts as written, as RDF compares terms");
});

test("a graph is a set: a triple written twice is one; the seed's triples are no part of it", () => {
  const twice = run(`${FULL}\n${SHORT}`);
  assert.equal(twice.status, "ok");
  assert.equal(twice.summary.count, 3);
  assert.deepEqual(twice.rows, run(FULL).rows);
  assert.equal(keyOf('dbr:Berlin rdfs:label "Berlin"@de , "Berlin"@de .'), keyOf('dbr:Berlin rdfs:label "Berlin"@de .'));
  assert.ok(!run(FULL).rows.some((r) => r.includes("Potsdam")));
});

test("blank nodes: their labels do not count; a collection is its seven triples", () => {
  const list = run(LIST);
  assert.equal(list.status, "ok");
  assert.equal(list.summary.count, 7);
  assert.equal(list.rows.length, 7);
  const spelled = `dbr:Berlin dbo:neighboringMunicipality _:a .
_:a rdf:first dbr:Potsdam ; rdf:rest _:b .
_:b rdf:first dbr:Teltow ; rdf:rest _:c .
_:c rdf:first dbr:Falkensee ; rdf:rest rdf:nil .`;
  assert.equal(keyOf(spelled), key(list.canonical), "the collection written out");
  assert.equal(keyOf(spelled.replaceAll("_:a", "_:x1").replaceAll("_:b", "_:x2")), key(list.canonical));
  assert.equal(keyOf(`dbr:Berlin dbo:neighboringMunicipality [ rdf:first dbr:Potsdam ; rdf:rest [ rdf:first dbr:Teltow ;
    rdf:rest [ rdf:first dbr:Falkensee ; rdf:rest rdf:nil ] ] ] .`), key(list.canonical), "... and nested");
  assert.equal(keyOf("dbr:Berlin dbo:neighboringMunicipality ( dbr:Teltow dbr:Potsdam dbr:Falkensee ) ."),
    key(list.canonical), "blank nodes all alike: a collection's order does not count (section 8.9)");
  assert.notEqual(keyOf("dbr:Berlin dbo:neighboringMunicipality ( dbr:Potsdam dbr:Teltow ) ."), key(list.canonical));
  assert.equal(keyOf("[] rdfs:label \"Berlin\"@de ."), keyOf("_:berlin rdfs:label \"Berlin\"@de ."));
  assert.deepEqual(list.summary.rows.slice(0, 2), [["_:b1", "rdf:first", "dbr:Potsdam"], ["dbr:Berlin", "dbo:neighboringMunicipality", "_:b1"]]);
});

test("the key of a Turtle text is the key of a SPARQL CONSTRUCT that gives the same graph", () => {
  for (const graph of [SHORT, LIST, `${TYPED}\ndbr:Berlin a dbo:City ; dbo:foundingDate "1237-10-28"^^xsd:date ;
  rdfs:comment "Hauptstadt"@DE , "the capital" .`]) {
    const store = sparql.load(ox, `${PREFIXES}${graph}\n`);
    const constructed = sparql.evaluate(store, "CONSTRUCT WHERE { ?s ?p ?o }");
    assert.equal(constructed.status, "ok");
    assert.equal(key(constructed.canonical), keyOf(graph), graph);
  }
});

test("what went wrong: Oxigraph's message at the student's line and column", () => {
  const syntax = (text) => {
    const r = run(text);
    assert.equal(r.status, "syntax", text);
    return r.error;
  };
  assert.equal(syntax('dbr:Berlin rdfs:label "Berlin"@de\ndbr:Berlin dbo:populationTotal 3596999 .'),
    "line 2, column 1: A dot is expected at the end of statements");
  assert.equal(syntax('dbr: Berlin rdfs:label "Berlin"@de .'), "line 1, column 6: Berlin is not a valid predicate");
  assert.equal(syntax('dbp:Berlin rdfs:label "Berlin"@de .'), "line 1, column 1: The prefix dbp: has not been declared");
  assert.equal(syntax('@prefix dbr: <http://dbpedia.org/resource/> .\ndbr:Berlin rdfs:label "Berlin"@de\ndbr:Berlin a dbo:City .'),
    "line 3, column 1: A dot is expected at the end of statements", "fewer lines in front: the text declares dbr: itself");
  assert.match(syntax('dbr:Berlin rdfs:label "Berlin@de .\ndbr:Berlin a dbo:City .'), /^line 1, column 23: /);
  assert.equal(syntax("dbr:Berlin dbo:populationTotal , 3596999 ."), "line 1, column 32: , is not a valid RDF object");
  assert.equal(keyOf("dbr:Berlin dbo:populationTotal 3596999 ; ."), keyOf("dbr:Berlin dbo:populationTotal 3596999 ."),
    "(a ; before the period is Turtle)");
  assert.match(syntax('dbr:Berlin rdfs:label "Berlin"^^ .'), /^line 1, column \d+: Expecting a datatype IRI/);
  assert.match(syntax('{ dbr:Berlin rdfs:label "Berlin"@de }'), /^line 1, /, "no TriG");
  assert.match(syntax('dbr:g { dbr:Berlin rdfs:label "Berlin"@de }'), /^line 1, /, "no TriG");
  assert.match(syntax('{"@id": "http://dbpedia.org/resource/Berlin", "http://www.w3.org/2000/01/rdf-schema#label": "Berlin"}'),
    /^line 1, column 1: /, "no JSON-LD");
  assert.equal(syntax("# nothing yet"), "no triples");
  assert.equal(syntax("@prefix ex: <http://example.org/> ."), "no triples");
});

test("the limits: a graph of more than 10,000 triples is an error, not a result", () => {
  const r = run(`dbr:Berlin dbo:p (${" 1".repeat(5001)} ) .`);
  assert.deepEqual(r, { status: "error", error: "more than 10000 triples" });
  assert.equal(run(`dbr:Berlin dbo:p (${" 1".repeat(4999)} ) .`).summary.count, 9999);
});

test("the seed: its @base and prefixes serve every text; a seed that does not parse says so", () => {
  const based = turtle.load(ox, "@base <http://dbpedia.org/resource/> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n");
  const r = turtle.evaluate(based, '<Berlin> rdfs:label "Berlin"@de .');
  assert.equal(r.status, "ok");
  assert.equal(key(r.canonical), keyOf('dbr:Berlin rdfs:label "Berlin"@de .'));
  assert.equal(turtle.evaluate(based, "@base <http://example.org/> .\n<Berlin> rdfs:label \"Berlin\"@de .").rows[0],
    '<http://example.org/Berlin> <http://www.w3.org/2000/01/rdf-schema#label> "Berlin"@de', "a base of the text's own");
  assert.throws(() => turtle.load(ox, "@prefix dbr: <http://dbpedia.org/resource/"), /Parser error/);
});

test("the summary: the triples as written, short with the seed's prefixes, a number not as a string", () => {
  const s = run(`${SHORT}\ndbr:Berlin a dbo:City ; dbo:foundingDate "1237-10-28"^^xsd:date ; dbo:mayor dbr:Kai_Wegner .`).summary;
  assert.equal(s.kind, "graph");
  assert.equal(s.count, 6);
  assert.deepEqual(s.rows, [
    ["dbr:Berlin", "rdfs:label", '"Berlin"@de'], ["dbr:Berlin", "rdfs:label", '"Berlino"@it'],
    ["dbr:Berlin", "dbo:populationTotal", "3596999"], ["dbr:Berlin", "a", "dbo:City"],
    ["dbr:Berlin", "dbo:foundingDate", '"1237-10-28"^^xsd:date'], ["dbr:Berlin", "dbo:mayor", "dbr:Kai_Wegner"]]);
  assert.equal(run(SHORT.replace("3596999", '"3596999"')).summary.rows[2][2], '"3596999"');
  assert.equal(run("dbr:Berlin geo:lat 52.52 .").status, "syntax", "geo: is not the seed's");
  assert.deepEqual(run("<http://example.org/x> <http://example.org/p> 52.52, true, 1e3, \"a \\\"b\\\"\" .").summary.rows.map((r) => r[2]),
    ["52.52", "true", "1e3", '"a \\"b\\""']);
  const many = run(`dbr:Berlin rdfs:comment ${Array.from({ length: 60 }, (_, i) => `"${"x".repeat(200)} ${i}"`).join(", ")} .`);
  assert.equal(many.summary.count, 60);
  assert.ok(JSON.stringify(many.summary).length <= 11000 && many.summary.rows.length <= 20);
  assert.ok(many.summary.rows.every((r) => r.every((v) => v.length <= 120)));
});

test("a graph against the reference's: the triples in both, missing, more", () => {
  const reference = run(SHORT);
  assert.deepEqual(compare(run(FULL), reference), { common: 3, missing: 0, extra: 0 });
  assert.deepEqual(compare(run(SHORT.replace(', "Berlino"@it', "")), reference), { common: 2, missing: 1, extra: 0 });
  assert.deepEqual(compare(run(SHORT.replace("3596999", '"3596999"')), reference), { common: 2, missing: 1, extra: 1 });
});

test("where and why, in the deck's language (the presenter window's) - Oxigraph's words as they are", () => {
  const r = turtle.evaluate(state, 'dbr:Berlin rdfs:label "Berlin"@de\ndbr:Berlin dbo:populationTotal 3596999 .', "de");
  assert.deepEqual([r.status, r.error], ["syntax", "Zeile 2, Spalte 1: A dot is expected at the end of statements"]);
  assert.equal(turtle.evaluate(state, "# nothing yet", "de").error, "keine Tripel");
  assert.equal(turtle.evaluate(state, "# nothing yet", "en-GB").error, "no triples");
});
