// SPDX-License-Identifier: Apache-2.0
// Run from a Texstage source checkout with Node 24. Uses its actual browser engines.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { registerHooks } from "node:module";

const root=path.dirname(fileURLToPath(import.meta.url));
const web=process.env.TEXSTAGE_WEB || path.resolve(root,"../../src/texstage/web");
registerHooks({load(url,context,next){
  if(url.endsWith("/vendor/sqljs/sql-wasm-browser.js"))
    return {format:"module",source:fs.readFileSync(new URL(url)),shortCircuit:true};
  return next(url,context);
}});
const load=name=>import(pathToFileURL(path.join(web,"engines",name+".js")).href);
const [sql,sparql,turtle]=await Promise.all(["sql","sparql","turtle"].map(load));
const wasm=async name=>WebAssembly.compile(fs.readFileSync(path.join(web,name)));
const SQL=await sql.start(await wasm("vendor/sqljs/sql-wasm-browser.wasm"));
const ox=await sparql.start(await wasm("vendor/oxigraph/web_bg.wasm"));
const read=rel=>fs.readFileSync(path.join(root,rel),"utf8");
const sqlSeed=read("data/library.sql"), rdfSeed=read("data/library.ttl");
const sqlState=sql.load(SQL,sqlSeed), graphState=sparql.load(ox,rdfSeed), turtleState=turtle.load(ox,rdfSeed);
const runSql=q=>sql.evaluate(sqlState,q);
const runGraph=q=>sparql.evaluate(graphState,q);
const runTurtle=q=>turtle.evaluate(turtleState,q);
const rows=(result)=>{assert.equal(result.status,"ok",result.error);return result.summary.rows.map(r=>r.join("|")).sort();};
const expected={
  "sql-filter":["Database Basics","Practical SQL"],
  "sql-join":["Ada|Database Basics","Ben|Graph Stories","Cara|Network Notes"],
  "sql-count":["Ada|1","Ben|1","Cara|1","Dan|0"],
  "sql-available":["Practical SQL"],
  "sql-bags":["Ada","Ada","Ben","Ben","Cara"],
};
const results={};
for(const [id,wanted] of Object.entries(expected)){
  const r=runSql(read("answers/"+id+".sql")); results[id]=r;
  assert.deepEqual(rows(r),[...wanted].sort(),id);
}
const equivalents={
 "sql-filter":"SELECT title FROM books WHERE topic IN ('databases') ORDER BY title DESC;",
 "sql-join":"SELECT m.name,b.title FROM members m,books b,loans l WHERE l.member_id=m.member_id AND b.book_id=l.book_id AND l.returned_on IS NULL;",
 "sql-count":"SELECT m.name,(SELECT COUNT(*) FROM loans l WHERE l.member_id=m.member_id AND l.returned_on IS NULL) AS active_loans FROM members m;",
 "sql-available":"SELECT b.title FROM books b LEFT JOIN loans l ON b.book_id=l.book_id AND l.returned_on IS NULL WHERE l.loan_id IS NULL;",
 "sql-bags":"SELECT m.name FROM loans l JOIN members m ON m.member_id=l.member_id ORDER BY m.name DESC;",
};
for(const [id,q] of Object.entries(equivalents)) assert.equal(runSql(q).canonical,results[id].canonical,id);
const mistakes={
 "sql-filter":"SELECT title FROM books;",
 "sql-join":read("answers/sql-join.sql").replace("IS NULL","= NULL"),
 "sql-count":read("answers/sql-count.sql").replace("COUNT(l.loan_id)","COUNT(*)"),
 "sql-available":"SELECT b.title FROM books b JOIN loans l ON b.book_id=l.book_id WHERE l.returned_on IS NOT NULL;",
 "sql-bags":read("answers/sql-bags.sql").replace("SELECT m.name","SELECT DISTINCT m.name"),
};
for(const [id,q] of Object.entries(mistakes)){
  const r=runSql(q);assert.equal(r.status,"ok",id);assert.notEqual(r.canonical,results[id].canonical,id);
}
assert.equal(runSql("DROP TABLE books").status,"refused");
assert.deepEqual(rows(runSql(read("answers/sql-filter.sql"))),expected["sql-filter"]);

const select=runGraph(read("answers/sparql-select.rq"));
assert.deepEqual(rows(select),expected["sql-join"]);
assert.equal(runGraph("SELECT ?n ?t WHERE {?x :status :open. ?x :book ?b. ?b :title ?t. ?x :member ?m. ?m :name ?n.} ORDER BY DESC(?n)").canonical,select.canonical);
const ask=runGraph(read("answers/sparql-ask.rq"));
assert.equal(ask.status,"ok");assert.equal(ask.summary.boolean,false);
assert.equal(runGraph("ASK { ?loan :member :ada ; :status :open . }").summary.boolean,true);
const construct=runGraph(read("answers/sparql-construct.rq"));
assert.deepEqual(rows(construct),[":ada|:borrows|:b101",":ben|:borrows|:b102",":cara|:borrows|:b104"]);
assert.equal(construct.canonical,runTurtle(":cara :borrows :b104. :ada :borrows :b101. :ben :borrows :b102.").canonical);
const one=runTurtle(read("answers/turtle-one.ttl"));
assert.deepEqual(rows(one),[":ben|:borrows|:b102"]);
assert.equal(one.canonical,runTurtle("<https://example.org/library/ben> <https://example.org/library/borrows> <https://example.org/library/b102> .").canonical);
assert.notEqual(one.canonical,runTurtle(':ben :borrows "Graph Stories" .').canonical);
const many=runTurtle(read("answers/turtle-many.ttl"));
assert.deepEqual(rows(many),[":ada|:hasBorrowed|:b101",":ada|:hasBorrowed|:b103"]);
assert.equal(many.canonical,runTurtle(":ada :hasBorrowed :b103. :ada :hasBorrowed :b101. :ada :hasBorrowed :b101.").canonical);
assert.equal(runTurtle("").status,"syntax");

// Fresh data separates two tempting queries that happen to work on the first snapshot.
const extra=sql.load(SQL,sqlSeed+"\nINSERT INTO members VALUES(5,'Eve'),(6,'Ada');"+
  "INSERT INTO loans VALUES(206,5,103,'2026-10-03');");
try{
  const correct=sql.evaluate(extra,read("answers/sql-count.sql"));
  assert.deepEqual(rows(correct),["Ada|0","Ada|1","Ben|1","Cara|1","Dan|0","Eve|0"]);
  const wrongWhere="SELECT m.name,COUNT(l.loan_id) FROM members m LEFT JOIN loans l ON l.member_id=m.member_id WHERE l.returned_on IS NULL GROUP BY m.member_id,m.name;";
  assert.notEqual(sql.evaluate(extra,wrongWhere).canonical,correct.canonical,"only returned loans must still count zero");
  const wrongGroup=read("answers/sql-count.sql").replace("GROUP BY m.member_id, m.name","GROUP BY m.name");
  assert.notEqual(sql.evaluate(extra,wrongGroup).canonical,correct.canonical,"different members may share a name");
}finally{extra.db.close();}
sqlState.db.close();
graphState.store.free();
console.log(JSON.stringify({reference_exercises:10,sql_alternatives:5,sql_mistakes:5,
  rdf_alternatives_and_counterexamples:true,transfer_data_probes:2,sql_mutations_refused:true}));
