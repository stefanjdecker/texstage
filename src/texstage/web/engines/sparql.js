// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The SPARQL engine of live activities (docs/live-activities-design.md, sections 8.3 and 8.4):
// Oxigraph (web/vendor/oxigraph) over the activity's seed, in the evaluator's worker
// (stage/evaluator-worker.js; the engines: index.js).
//
//   start(wasm)             Oxigraph, from the window's compiled WebAssembly module
//   load(ox, seed)          the seed (Turtle) in a store, and the prologue its @base and @prefix
//                           lines give every query that does not declare them itself
//   evaluate(state, text, language)
//                           -> {status: ok | syntax | error | refused, error?, canonical?, rows?, summary?}
//                              (error: where and why, in the deck's language - i18n's "engines" -,
//                              Oxigraph's words after it)
//
// The same result, the same canonical form: a SELECT's rows as a bag - their order does not count,
// repeated rows do -, the columns in the order the query projects them, their names not; a value
// as its term (an IRI, a literal with its datatype or language; blank nodes all alike, an unbound
// one "-"); an ASK's yes or no; a CONSTRUCT's or DESCRIBE's triples, sorted. Oxigraph keeps typed
// literals of the XSD datatypes as values ("03"^^xsd:integer is "3"): their canonical form is
// Oxigraph's (section 8.7).
//
// The Turtle engine (turtle.js) takes Oxigraph, the seed's prologue and a graph's terms from here
// (start, prologue, namespaces, rdfjsTerm, shorten): a Turtle text and a CONSTRUCT that give the
// same graph have the same key.

import { texts } from "../i18n/i18n.js";
import { bounded, cut, ROWS } from "./common.js";

export const NAME = "sparql";
const XSD_STRING = "http://www.w3.org/2001/XMLSchema#string";
const JSON_RESULTS = "application/sparql-results+json";

export async function start(wasm) {
  const ox = await import("../vendor/oxigraph/web.js");
  ox.initSync({ module: wasm });
  return ox;
}

// ------------------------------------------------------------------ the seed and the prologue
export function prologue(seed) {
  // the seed's @base and @prefix lines (or BASE and PREFIX), in their order
  const decls = [];
  for (const m of seed.matchAll(/^\s*(?:@base\s+<([^>]*)>\s*\.|BASE\s+<([^>]*)>|@prefix\s+([\w.-]*):\s*<([^>]*)>\s*\.|PREFIX\s+([\w.-]*):\s*<([^>]*)>)/gim)) {
    if (m[1] !== undefined || m[2] !== undefined) decls.push({ base: m[1] ?? m[2] });
    else decls.push({ prefix: m[3] ?? m[5], iri: m[4] ?? m[6] });
  }
  return decls;
}

function resolve(iri, base) {
  try { return base ? new URL(iri, base).href : iri; } catch { return iri; }
}

export function namespaces(decls) {
  // the prologue's prefixes as [prefix, namespace] - for showing IRIs short -, the longest namespace first
  let base = null;
  const prefixes = [];
  for (const d of decls) {
    if (d.base !== undefined) base = resolve(d.base, base);
    else prefixes.push([d.prefix, resolve(d.iri, base)]);
  }
  return prefixes.sort((a, b) => b[1].length - a[1].length);
}

export function load(ox, seed) {
  const store = new ox.Store();
  store.load(seed, { format: "text/turtle" });
  const decls = prologue(seed);
  return { store, decls, prefixes: namespaces(decls) };
}

function completed(state, text) {
  // the seed's declarations in front of a query that does not make them itself; how many lines
  const lines = [];
  const declares = (re) => re.test(text);
  for (const d of state.decls) {
    if (d.base !== undefined) {
      if (!declares(/^\s*BASE\s/im)) lines.push(`BASE <${d.base}>`);
    } else if (!declares(new RegExp(`^\\s*PREFIX\\s+${d.prefix.replace(/[.-]/g, "\\$&")}:`, "im"))) {
      lines.push(`PREFIX ${d.prefix}: <${d.iri}>`);
    }
  }
  return { query: lines.length ? `${lines.join("\n")}\n${text}` : text, shift: lines.length };
}

// ------------------------------------------------------------------ terms
const lexical = (v) => JSON.stringify(v);
function jsonTerm(b) {
  if (b === undefined) return "-";
  if (b.type === "uri") return `<${b.value}>`;
  if (b.type === "bnode") return "_:";
  if (b.type === "literal" || b.type === "typed-literal") {
    if (b["xml:lang"]) return `${lexical(b.value)}@${b["xml:lang"].toLowerCase()}`;
    return `${lexical(b.value)}^^<${b.datatype || XSD_STRING}>`;
  }
  return `?${b.type}`;
}
export function rdfjsTerm(t) {
  // a graph's term (RDF/JS, as Oxigraph gives it) in the canonical form - with RDF 1.2's text
  // direction and triple terms, which Oxigraph's Turtle reads
  if (t.termType === "NamedNode") return `<${t.value}>`;
  if (t.termType === "BlankNode") return "_:";
  if (t.termType === "Literal") {
    if (t.language) return `${lexical(t.value)}@${t.language.toLowerCase()}${t.direction ? `--${t.direction}` : ""}`;
    return `${lexical(t.value)}^^<${t.datatype?.value || XSD_STRING}>`;
  }
  if (t.termType === "Quad") return `<<( ${rdfjsTerm(t.subject)} ${rdfjsTerm(t.predicate)} ${rdfjsTerm(t.object)} )>>`;
  return `?${t.termType}`;
}

export function shorten(state, iri) {
  for (const [p, ns] of state.prefixes) {
    if (ns && iri.startsWith(ns) && /^[\w.-]*$/u.test(iri.slice(ns.length))) return `${p}:${iri.slice(ns.length)}`;
  }
  return `<${iri}>`;
}
function showJson(state, b) {
  if (b === undefined) return "";
  if (b.type === "uri") return cut(shorten(state, b.value));
  if (b.type === "bnode") return "_:b";
  return cut(b["xml:lang"] ? `${b.value}@${b["xml:lang"]}` : b.value);
}
function showRdfjs(state, t) {
  if (t.termType === "NamedNode") return cut(shorten(state, t.value));
  if (t.termType === "BlankNode") return "_:b";
  return cut(t.language ? `${t.value}@${t.language}` : t.value);
}

// ------------------------------------------------------------------ evaluation
function failure(e, shift, W) {
  const text = String(e?.message ?? e).split("\n")[0];
  const at = /^error at (\d+):(\d+): (.*)$/.exec(text);
  if (at) return { status: "syntax", error: W.at(Math.max(1, Number(at[1]) - shift), at[2], at[3]) };
  if (/^The service .* is not supported/.test(text)) return { status: "refused", error: W.service };
  return { status: "error", error: text };
}

export function evaluate(state, text, language) {
  const W = texts(language).engines;
  const { query, shift } = completed(state, text);
  let json;
  try {
    json = JSON.parse(state.store.query(query, { results_format: JSON_RESULTS }));
  } catch (e) {
    if (!/Not supported RDF format/.test(String(e?.message ?? e))) return failure(e, shift, W);
    let quads;                                           // a CONSTRUCT or DESCRIBE: its triples
    try {
      quads = state.store.query(query);
    } catch (e2) {
      return failure(e2, shift, W);
    }
    const rows = quads.map((q) => `${rdfjsTerm(q.subject)} ${rdfjsTerm(q.predicate)} ${rdfjsTerm(q.object)}`).sort();
    return { status: "ok", canonical: `graph\n${rows.join("\n")}`, rows,
      summary: bounded({ kind: "graph", count: quads.length,
        rows: quads.slice(0, ROWS).map((q) => [q.subject, q.predicate, q.object].map((t) => showRdfjs(state, t))) }) };
  }
  if (typeof json.boolean === "boolean") {
    return { status: "ok", canonical: `ask\n${json.boolean}`, rows: [String(json.boolean)], summary: { kind: "ask", boolean: json.boolean } };
  }
  const vars = json.head?.vars || [];
  const bindings = json.results?.bindings || [];
  const rows = bindings.map((b) => vars.map((v) => jsonTerm(b[v])).join("\t")).sort();
  return { status: "ok", canonical: `select\n${vars.length}\n${rows.join("\n")}`, rows,
    summary: bounded({ kind: "select", columns: vars.map((v) => `?${v}`), count: bindings.length,
      rows: bindings.slice(0, ROWS).map((b) => vars.map((v) => showJson(state, b[v]))) }) };
}
