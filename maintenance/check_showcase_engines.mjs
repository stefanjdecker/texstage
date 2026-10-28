// SPDX-License-Identifier: Apache-2.0
// Rehearse the actual compiled showcase against texstage's browser engines.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bundle = path.resolve(process.argv[2] || path.join(root, ".showcase-build/live/showcase.bundle"));
const read = p => fs.readFileSync(p, "utf8");
const deck = JSON.parse(read(path.join(bundle, "deck.json")));
const keys = JSON.parse(read(path.join(bundle, "keys.json")));
const web = path.join(root, "src/texstage/web");
const engine = async name => import(pathToFileURL(path.join(web, "engines", name + ".js")).href);
const { key } = await engine("common");
const sql = await engine("sql"), sparql = await engine("sparql"), turtle = await engine("turtle");
const SQL = await sql.start(await WebAssembly.compile(fs.readFileSync(path.join(web,"vendor/sqljs/sql-wasm-browser.wasm"))));
const ox = await sparql.start(await WebAssembly.compile(fs.readFileSync(path.join(web,"vendor/oxigraph/web_bg.wasm"))));
const seed = id => read(path.join(bundle, deck.items.activity[id].seed));
const ref = id => keys.items.activity[id].reference[0];
const checks = [
  ["packing-sql",sql,SQL,
   "SELECT item FROM packing WHERE quantity > 5;",
   "SELECT item FROM packing WHERE quantity = 2;",
   "SELEC item FROM packing;",2],
  ["water-sparql",sparql,ox,
   "SELECT ?who WHERE { ?who :brings :water . }",
   "SELECT ?person WHERE { ?person :brings :apples . }",
   "SELECT ?person WHERE { ?person :brings",1],
  ["bread-turtle",turtle,ox,
   "<https://example.org/picnic/Sam> :brings :bread .",
   ":Alex :brings :bread .",
   ":Sam :brings :bread",1],
];
for (const [id,e,runtime,same,wrong,bad,count] of checks) {
  const state = e.load(runtime,seed(id));
  const good = e.evaluate(state,ref(id));
  assert.equal(good.status,"ok",id+": reference must execute");
  assert.equal(good.summary.count,count,id+": expected result size");
  const equivalent=e.evaluate(state,same), other=e.evaluate(state,wrong), invalid=e.evaluate(state,bad);
  assert.equal(equivalent.status,"ok");
  assert.equal(other.status,"ok");
  assert.equal(key(equivalent.canonical),key(good.canonical),id+": equivalent result");
  assert.notEqual(key(other.canonical),key(good.canonical),id+": different result");
  assert.equal(invalid.status,"syntax",id+": intended syntax-error example");
  if(id==="packing-sql") assert.deepEqual(good.summary.rows.map(r=>r[0]).sort(),["Apples","Cups"]);
  if(id==="water-sparql") assert.match(JSON.stringify(good.rows),/picnic\/Sam/);
  if(id==="bread-turtle") assert.match(JSON.stringify(good.rows),/picnic\/bread/);
  console.log("PASS "+id+": correct, equivalent, different and syntax-error submissions");
}
