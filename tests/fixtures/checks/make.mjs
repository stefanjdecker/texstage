// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The golden fixtures of the checks in Python (docs/architecture/activity-framework-plan.md, 4.3):
// today's engines (web/engines: sql.js, sparql.js, turtle.js) run over a corpus of seeds and
// texts, and what each gives - status, error, canonical form, key, rows, summary - written to
// sql.json, sparql.json and turtle.json beside this script. The server's checks (texstage/checks)
// must give the same, byte for byte, so that a game that goes on across F1 keeps its keys and the
// class its groups. The corpus is public: the engines' tests' seeds, the showcase's, and texts that
// probe the rules - the forms of numbers and strings, the order of the rows, the summaries' limits,
// the errors and refusals. A text whose result has an error is run in German too.
//
//     node tests/fixtures/checks/make.mjs
//
// The fixtures outlive the JavaScript engines: once F1 has removed them, they stay the checks' record.
import fs from "node:fs";
import * as nodeModule from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.join(here, "../../../src/texstage/web");
if (typeof nodeModule.registerHooks === "function") {      // sql.js's browser build as a browser loads it
  nodeModule.registerHooks({
    load(url, context, nextLoad) {
      if (url.endsWith("/vendor/sqljs/sql-wasm-browser.js")) {
        return { format: "module", source: fs.readFileSync(new URL(url)), shortCircuit: true };
      }
      return nextLoad(url, context);
    },
  });
}
const engine = async (name) => import(pathToFileURL(path.join(web, `engines/${name}.js`)).href);
const { key } = await import(pathToFileURL(path.join(web, "engines/common.js")).href);
const wasm = (file) => WebAssembly.compile(fs.readFileSync(path.join(web, "vendor", file)));
const CANONICAL_MAX = 20_000;          // a longer canonical form is kept as its key and its length only

// ------------------------------------------------------------------ the corpus
const repeat = (n, f) => Array.from({ length: n }, (_, i) => f(i));
const LONG = "x".repeat(130);
const EMOJI = "😀".repeat(70);         // 140 UTF-16 units: a value cut in the middle of a pair

const SQL = {
  seeds: {
    uni: `CREATE TABLE professor (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE lecture (id INTEGER PRIMARY KEY, title TEXT NOT NULL, taught_by INTEGER REFERENCES professor (id), hours REAL);
INSERT INTO professor VALUES (1, 'Kant'), (2, 'Socrates'), (3, 'Popper');
INSERT INTO lecture VALUES (1, 'Foundations', 1, 2), (2, 'The Three Critiques', 1, 4), (3, 'Ethics', 2, 3.5);
`,
    packing: `CREATE TABLE packing (item TEXT, quantity INTEGER);
INSERT INTO packing VALUES ('Apples',6),('Cups',6),('Blankets',2);
`,
    types: `CREATE TABLE v (id INTEGER PRIMARY KEY, i INTEGER, r REAL, t TEXT, b BLOB);
INSERT INTO v VALUES (1, 7, 7.0, '7', x'00ff'), (2, 9007199254740993, 0.1, 'Ä"\\' || char(10) || char(9) || char(1), NULL),
  (3, -0, 1e-7, '𝔸', x''), (4, 9223372036854775807, 1e21, 'ﬀ', NULL), (5, NULL, 2.5e-300, '', NULL),
  (6, -9223372036854775808, 123456789.123456789, 'Zebra', x'0a'), (7, 0, -1.5e-7, 'zebra', NULL), (8, 42, 1e300 * 1e10, 'é', NULL);
`,
  },
  texts: {
    uni: [
      "SELECT name FROM professor", "select name from professor;", "SELECT name FROM professor ORDER BY name DESC",
      "SELECT p.name, l.title FROM professor p JOIN lecture l ON l.taught_by = p.id",
      "SELECT p.name, l.title FROM professor p, lecture l", "SELECT name, name FROM professor", "SELECT * FROM lecture",
      "SELECT title, hours FROM lecture", "SELECT avg(hours) FROM lecture", "SELECT sum(hours) / count(*) FROM lecture",
      "SELECT count(*) FROM professor", "SELECT name FROM professor WHERE id > 5",
      "-- a comment\nSELECT name FROM professor", "/* a comment */ SELECT name FROM professor",
      "SELECT", "SELEC name FROM professor", "SELECT name FROM nope", "SELECT nme FROM professor",
      "SELECT name FROM professor WHERE", "SELECT 'unterminated", "SELECT name FROM professor; SELECT 1",
      "SELECT name FROM professor;;", "SELECT 1; -- after", "SELECT 1 /* c */ ;", "", "   ", "-- only a comment", ";",
      "INSERT INTO professor VALUES (9, 'X')", "DELETE FROM professor", "UPDATE professor SET name = 'Y'",
      "CREATE TABLE z (a)", "DROP TABLE professor", "ATTACH DATABASE 'x.db' AS x", "PRAGMA table_info(professor)",
      "SELECT * FROM pragma_table_info('professor')", "SELECT load_extension('x')",
      "WITH x AS (SELECT name FROM professor) SELECT name FROM x", "VALUES (1, 'a'), (2, 'b')",
      "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r LIMIT 100000) SELECT n FROM r",
      "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r LIMIT 100001) SELECT n FROM r",
      "EXPLAIN SELECT name FROM professor", "EXPLAIN QUERY PLAN SELECT name FROM professor",
      "WITH x AS (SELECT 9 AS id) DELETE FROM professor WHERE id IN (SELECT id FROM x)",
      "SELECT 1; /*", "SELECT 1; /* x", "SELECT 1 /* a */ */", "/* a */ SELECT 1 /* b */", "SELECT 1;\v",
      "SELECT 1; \v", "SELECT 1; /* c */\v", "SELECT 1; \ufeff\v", "\v",
      "SELECT 1; \u0085", "SELECT 1; \ufeff", "\ufeffSELECT 1", "\u00a0SELECT 1", "SELECT\u00a01",
      "; SELECT 1", "SELECT 1;; SELECT 2", "-- c\n;\nSELECT 1", "EXPLAIN", "explain_x SELECT 1",
      // pragmas, which SQLite carries out as it compiles them: refused before anything is compiled, so that
      // none changes the database of the cases after them (the count, the LIKE); the keyword as SQLite reads it
      "PRAGMA foreign_key_check(nope)", "PRAGMA nope.table_info(professor)", "SELECT * FROM pragma_query_only",
      "PRAGMA query_only = OFF", "pragma QUERY_ONLY=0; SELECT 1", "SELECT 1; PRAGMA query_only = OFF",
      "\ufeffPRAGMA query_only = OFF", "/* c */PRAGMA query_only = OFF", "EXPLAIN PRAGMA query_only = OFF",
      "PRAGMA case_sensitive_like = ON", "WITH x AS (SELECT 1) DELETE FROM professor", "SELECT count(*) FROM professor",
      "SELECT 'a' LIKE 'A'", 'SELECT \'PRAGMA\' AS "PRAGMA", 1 AS [pragma], 2 AS `pragma`', "SELECT 1 -- PRAGMA",
      "SELECT 1 /* PRAGMA */", "SELECT :pragma, $pragma, @pragma", "SELECT $a(PRAGMA)", "SELECT pragma FROM professor",
      "SELECT x\ufeffPRAGMA FROM professor", "SELECT 1\u0000PRAGMA query_only = OFF",
      // parameters, which sql.js left unbound: NULL
      "SELECT ?", "SELECT name FROM professor WHERE id = ?", "SELECT name FROM professor WHERE id = :id OR name = @n",
      "SELECT ?2, ?", "SELECT $x, $x", "SELECT ?, :x", "EXPLAIN SELECT ?", "SELECT ?; SELECT :y", "SELECT $a(x;y)",
      "SELECT ?0", "SELECT ?99999999",
    ],
    packing: ["SELECT item FROM packing WHERE quantity = 6;", "select item from packing where quantity=6",
      "SELECT item FROM packing WHERE quantity = 6 -- me", "SELECT item, quantity FROM packing",
      "SELECT * FROM packing ORDER BY quantity", "SELECT item FROM packing WHERE quantity = 2"],
    types: [
      "SELECT i, r, t, b FROM v", "SELECT t FROM v", "SELECT i FROM v", "SELECT r FROM v", "SELECT b FROM v",
      "SELECT 1 / 3.0, 2 / 3.0, 0.1 + 0.2, 1e-7, 1e21, 1e22, -0.0, 2.0, 1 / 0, 3.14159265358979, 1e-6, 123e-20",
      "SELECT 9007199254740993, 9007199254740992, -9007199254740993, 1.0e15 + 0.3, 2.675, 1.005, 0.000001234567890123456",
      "SELECT 'a' UNION ALL SELECT 'a'", "SELECT NULL", "SELECT x'0102'", "SELECT char(0)",
      `SELECT '${LONG}'`, `SELECT '${EMOJI}'`, "SELECT printf('%.300c', 'y')",
      "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r LIMIT 50) SELECT n, printf('%.300c', 'y') FROM r",
      "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r LIMIT 25) SELECT n, n * 0.1 FROM r",
      "SELECT t, length(t) FROM v ORDER BY t", "SELECT typeof(i), typeof(r), typeof(t), typeof(b) FROM v",
      "SELECT r * 3 FROM v", "SELECT round(r, 2) FROM v", "SELECT i + 0.5 FROM v",
      // texts as sql.js read them: up to a NUL, an ill-formed byte as U+FFFD, a leading BOM dropped
      "SELECT 'a' || char(0) || 'b'", "SELECT char(65, 0, 66), length(char(65, 0, 66))",
      "SELECT CAST(x'41ff42' AS TEXT)", "SELECT CAST(x'efbbbf41' AS TEXT), length(CAST(x'efbbbf41' AS TEXT))",
      "SELECT CAST(x'eda080' AS TEXT)", 'SELECT 1 AS "\ufeffx"', "SELECT 1\u0000; SELECT 2",
      "SELECT '\ud800'", "SELECT length('\ud800')",
    ],
  },
};

const RDF_TYPES = `@prefix ex: <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:a ex:n 7 ; ex:d 7.0 ; ex:f 7e0 ; ex:s "7" ; ex:b true ; ex:i "03"^^xsd:integer ; ex:l "Kant"@DE , "Kant"@en-GB .
ex:a ex:x [ ex:y "blank" ] .
ex:b ex:n -0.0 ; ex:s "Ä\\"\\\\\\n\\t" ; ex:u "𝔸" , "ﬀ" , "Zebra" , "zebra" , "é" .
ex:c ex:long "${LONG}" ; ex:emoji "${EMOJI}" ; ex:date "2026-11-09"^^xsd:date ; ex:neg -5 ; ex:big 12345678901234567890 .
`;
const SPARQL = {
  seeds: {
    uni: `@base <http://data.rwth-aachen.de/resources/> .
@prefix : <> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
:kant a :Professor ; :name "Kant" .
:socrates a :Professor ; :name "Socrates" .
:popper a :Professor ; :name "Popper" .
:l1 :taughtBy :kant ; :title "Foundations" .
:l2 :taughtBy :kant ; :title "The Three Critiques" .
:l3 :taughtBy :socrates ; :title "Ethics" .
`,
    picnic: fs.readFileSync(path.join(here, "../../../examples/showcase/picnic.ttl"), "utf8"),
    types: RDF_TYPES,
  },
  texts: {
    uni: [
      "SELECT ?name ?title WHERE { ?p a :Professor ; :name ?name . ?l :taughtBy ?p ; :title ?title . }",
      "SELECT ?title ?name WHERE { ?l :title ?title ; :taughtBy ?p . ?p :name ?name }",
      "select ?name ?title where { ?p a :Professor ; :name ?name . ?l :taughtBy ?p ; :title ?title . } order by ?name",
      "SELECT ?name WHERE { ?p a :Professor ; :name ?name }", "SELECT DISTINCT ?p WHERE { ?l :taughtBy ?p }",
      "SELECT * WHERE { ?s ?p ?o }", "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }",
      "SELECT ?name ?title WHERE { ?p :name ?name . OPTIONAL { ?l :taughtBy ?p ; :title ?title } }",
      "PREFIX : <http://other.org/> SELECT ?s WHERE { ?s a :Professor }",
      "BASE <http://other.org/> PREFIX : <> SELECT ?s WHERE { ?s ?p ?o } LIMIT 1",
      "ASK { :kant a :Professor }", "ASK { :kant a :Lecture }",
      "CONSTRUCT { ?p :teaches ?l } WHERE { ?l :taughtBy ?p }", "CONSTRUCT WHERE { ?s :name ?o }", "DESCRIBE :kant",
      "SELEC ?name WHERE { ?p :name ?name }", "SELECT ?name WHERE {\n  ?p a :Professor ;\n     :name ?name\n  ?x }",
      "SELECT ?x WHERE { ?x }", "SELECT * WHERE { SERVICE <http://127.0.0.1:9/sparql> { ?s ?p ?o } }",
      "SELECT * WHERE { SERVICE SILENT <http://127.0.0.1:9/sparql> { ?s ?p ?o } }",
      "INSERT DATA { :a :b :c }", "", "# just a comment",
      "SELECT ?service WHERE { ?service :name ?n }", "SELECT * WHERE { ?s :name 'SERVICE' }",
    ],
    picnic: ["SELECT ?person WHERE { ?person :brings :water . }", "SELECT ?who WHERE { ?who :brings :water }",
      "SELECT ?person ?thing WHERE { ?person :brings ?thing }", "SELECT ?person WHERE { ?person :brings :bread }"],
    types: [
      "SELECT ?o WHERE { ex:a ?p ?o }", "SELECT ?p ?o WHERE { ex:a ?p ?o }", "SELECT ?o WHERE { ex:b ?p ?o }",
      "SELECT ?s ?p ?o WHERE { ?s ?p ?o }", "SELECT ?l WHERE { ex:a ex:l ?l }", "SELECT (LANG(?l) AS ?lang) WHERE { ex:a ex:l ?l }",
      "SELECT (STR(?o) AS ?s) WHERE { ex:a ?p ?o }", "SELECT (DATATYPE(?o) AS ?d) WHERE { ex:a ?p ?o FILTER isLiteral(?o) }",
      "SELECT (1/3 AS ?x) (0.1 + 0.2 AS ?y) (1e-7 AS ?z) (2.0 AS ?w) {}", "SELECT ?x WHERE { VALUES ?x { 1 2 3 1 } }",
      "SELECT ?x ?y WHERE { OPTIONAL { ?x ex:nothing ?y } }", "SELECT ?b WHERE { ex:a ex:x ?b }",
      "SELECT ?y WHERE { ex:a ex:x [ ex:y ?y ] }", "SELECT (SUM(?n) AS ?t) WHERE { ?s ex:n ?n }",
      "SELECT (AVG(?n) AS ?t) WHERE { ?s ex:n ?n }", "SELECT ?o WHERE { ex:b ex:u ?o } ORDER BY ?o",
      "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "CONSTRUCT { ex:c ex:copy ?o } WHERE { ex:c ?p ?o }",
      "SELECT ?o WHERE { ex:c ?p ?o }",
      'SELECT ?x WHERE { BIND("\ud800" AS ?x) }', 'SELECT ?x WHERE { BIND("a\u0000b" AS ?x) }',
      'SELECT ?x WHERE { BIND("\ufeffA" AS ?x) }',
    ],
  },
};

const TURTLE_PREFIXES = `@prefix dbr: <http://dbpedia.org/resource/> .
@prefix dbo: <http://dbpedia.org/ontology/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
`;
const BERLIN = 'dbr:Berlin rdfs:label "Berlin"@de , "Berlino"@it ;\n           dbo:populationTotal 3596999 .';
const TURTLE = {
  seeds: {
    prefixes: `${TURTLE_PREFIXES}dbr:Potsdam rdfs:label "Potsdam"@de .\n`,
    base: "@base <http://example.org/base/> .\n@prefix : <ns#> .\n",
    picnic: fs.readFileSync(path.join(here, "../../../examples/showcase/picnic.ttl"), "utf8"),
    none: "",
  },
  texts: {
    prefixes: [
      BERLIN, BERLIN.replace(/\s+/g, " "),
      'dbr:Berlin rdfs:label "Berlin"@de .\ndbr:Berlin rdfs:label "Berlino"@it .\ndbr:Berlin dbo:populationTotal 3596999 .',
      'dbr:Berlin rdfs:label "Berlin"@DE , "Berlino"@IT ; dbo:populationTotal "3596999"^^xsd:integer .',
      '<http://dbpedia.org/resource/Berlin> rdfs:label "Berlin"@de , "Berlino"@it ; dbo:populationTotal 3596999 .',
      "dbr:Berlin rdfs:label “Berlin”@de , „Berlino“@it ; dbo:populationTotal 3596999 .",
      "dbr:Berlin rdfs:label ‘Berlin’@de .", 'dbr:Berlin dbo:populationTotal "3596999" .',
      'dbr:Berlin dbo:populationTotal 3596999.0 .', 'dbr:Berlin dbo:populationTotal 3.596999e6 .',
      'dbr:Berlin dbo:populationTotal "03596999"^^xsd:integer .', 'dbr:Berlin dbr:flag true , false .',
      'dbr:Berlin dbr:near [ rdfs:label "a" ] , [ rdfs:label "a" ] .', 'dbr:Berlin dbr:list ( 1 2 3 ) .',
      'dbr:Berlin rdfs:label "Berlin"@de . dbr:Berlin rdfs:label "Berlin"@de .',
      'dbr:Potsdam rdfs:label "Potsdam"@de .', '_:x rdfs:label "x" . _:x rdfs:label "y" .',
      'dbr:Berlin rdfs:label "Ä\\"\\\\\\n"@de , "𝔸" , "ﬀ" , "Zebra" , "zebra" .',
      `dbr:Berlin rdfs:comment "${LONG}" , "${EMOJI}" .`, 'dbr:Berlin rdfs:label "text"@ar--rtl .',
      "dbr:Berlin rdf:type dbo:City .", "dbr:Berlin a dbo:City .",
      repeat(25, (i) => `dbr:Berlin dbr:p${i} ${i} .`).join("\n"),
      "dbr:Berlin rdfs:label \"Berlin\"@de", 'dbr:Berlin rdfs:label "Berlin .', "ex:Berlin a dbo:City .",
      'dbr:Berlin rdfs:label """multi\nline""" .', "dbr:Berlin rdfs:label\n  \"Berlin\n", "# only a comment", "",
      "dbr:Berlin dbr:p dbr:Q .\nfoo bar baz", "@prefix dbr: <http://other.org/> .\ndbr:X a dbr:Y .",
      "PREFIX dbr: <http://other.org/>\ndbr:X a dbr:Y .",
      'dbr:Berlin rdfs:label "\ud800" .', 'dbr:Berlin rdfs:label "\ufeffBerlin" .', '\ufeffdbr:Berlin rdfs:label "B" .',
      { repeat: 10_001, line: "dbr:s{i} dbr:p dbr:o ." },         // too many triples: kept as its pattern
    ],
    base: [":a :b :c .", "<rel> <p> <o> .", "@base <http://elsewhere.org/> .\n<rel> <p> <o> ."],
    picnic: [":Sam :brings :bread .", ":Sam :brings :bread , :water .", ":Sam :brings :bread"],
    none: ["<http://e.org/a> <http://e.org/b> <http://e.org/c> .", "ex:a ex:b ex:c ."],
  },
};

// ------------------------------------------------------------------ running it
function record(result) {
  const out = { status: result.status };
  if (result.error !== undefined) out.error = result.error;
  if (result.canonical !== undefined) {
    out.key = key(result.canonical);
    if (result.canonical.length <= CANONICAL_MAX) out.canonical = result.canonical;
    else out.canonical_length = result.canonical.length;
  }
  if (result.rows !== undefined && JSON.stringify(result.rows).length <= CANONICAL_MAX) out.rows = result.rows;
  if (result.summary !== undefined) out.summary = result.summary;
  return out;
}

// a text, or {repeat: n, line}: n lines, {i} in each its number (the Python tests expand it alike)
const expand = (text) => (typeof text === "string" ? text
  : Array.from({ length: text.repeat }, (_, i) => text.line.replaceAll("{i}", String(i))).join("\n"));

function run(name, mod, lib, corpus) {
  const cases = [];
  for (const [seed, texts] of Object.entries(corpus.texts)) {
    const state = mod.load(lib, corpus.seeds[seed]);
    for (const text of texts) {
      const en = record(mod.evaluate(state, expand(text), "en"));
      cases.push({ seed, text, language: "en", result: en });
      if (en.error !== undefined) {
        cases.push({ seed, text, language: "de", result: record(mod.evaluate(state, expand(text), "de")) });
      }
    }
  }
  const file = path.join(here, `${name}.json`);
  fs.writeFileSync(file, `${JSON.stringify({ made_by: "tests/fixtures/checks/make.mjs", engine: name,
    seeds: corpus.seeds, cases }, null, 1)}\n`);
  console.log(`${name}: ${cases.length} cases -> ${path.relative(process.cwd(), file)}`);
}

const sql = await engine("sql");
run("sql", sql, await sql.start(await wasm("sqljs/sql-wasm-browser.wasm")), SQL);
const sparql = await engine("sparql");
const ox = await sparql.start(await wasm("oxigraph/web_bg.wasm"));
run("sparql", sparql, ox, SPARQL);
run("turtle", await engine("turtle"), ox, TURTLE);
