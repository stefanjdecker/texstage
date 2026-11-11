// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The Turtle engine of live activities (docs/live-activities-design.md, sections 8.3 and 8.9): a
// student's text read as Turtle by Oxigraph's parser - the SPARQL engine's Oxigraph (sparql.js),
// without a store -, in the evaluator's worker (stage/evaluator-worker.js; the engines: index.js).
// Chapter 3's thesis, one graph in many spellings: texts that write the same graph get one key -
// full triples or ; and , , 3596999 or "3596999"^^xsd:integer, a prefixed name or the IRI it
// stands for.
//
//   start(wasm)             Oxigraph, as the SPARQL engine starts it
//   load(ox, seed)          the seed's @base and @prefix lines, which a text may use without
//                           declaring them; the seed's triples are no part of anybody's graph
//   evaluate(state, text, language)
//                           -> {status: ok | syntax | error, error?, canonical?, rows?, summary?}
//                              (error: where and why, in the deck's language - i18n's "engines" -,
//                              Oxigraph's words after it)
//
// Turtle only - the parser of text/turtle (RDF 1.2's Turtle, as Oxigraph reads it), no TriG, no
// JSON-LD. The same graph, the same canonical form: the SPARQL engine's for a CONSTRUCT's graph,
// so that a Turtle text and a CONSTRUCT that give one graph have one key - the triples as a set
// (a triple written twice is one), sorted, each term as sparql.js writes it (an IRI, a literal
// with its datatype or its language in lower case; blank nodes all alike). A literal counts as
// written, as RDF compares terms: "03"^^xsd:integer is not 3 (a CONSTRUCT's literals from the
// store are Oxigraph's values, section 8.7). A phone keyboard's typographic quotes - “Berlin”,
// „Berlin“ - count as Turtle's, as the crowd graph takes them (checks/cleaning.py, clean_term).

import { texts } from "../i18n/i18n.js";
import { bounded, cut, ROWS } from "./common.js";
import { namespaces, prologue, rdfjsTerm, shorten, start } from "./sparql.js";

export { start };
export const NAME = "turtle";
const MAX_TRIPLES = 10_000;         // more is an error, not a graph (a phone's 2,000 characters make 2,000 at most)
const TURTLE = { format: "text/turtle" };
const XSD = "http://www.w3.org/2001/XMLSchema#";
const RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const DOUBLE_QUOTES = /[“”„‟«»]/g;  // (checks/cleaning.py: DOUBLE_QUOTES, SINGLE_QUOTES)
const SINGLE_QUOTES = /[‘’‚‛]/g;

export function load(ox, seed) {
  ox.parse(seed, TURTLE);           // a seed that does not parse says so when the activity opens
  const decls = prologue(seed);
  return { ox, decls, prefixes: namespaces(decls) };
}

function completed(state, text) {
  // the seed's declarations, in Turtle's form, in front of a text that does not make them itself;
  // how many lines they are
  const lines = [];
  const declares = (re) => re.test(text);
  for (const d of state.decls) {
    if (d.base !== undefined) {
      if (!declares(/^\s*(?:@base|BASE)\b/im)) lines.push(`@base <${d.base}> .`);
    } else if (!declares(new RegExp(`^\\s*(?:@prefix|PREFIX)\\s+${d.prefix.replace(/[.-]/g, "\\$&")}:`, "im"))) {
      lines.push(`@prefix ${d.prefix}: <${d.iri}> .`);
    }
  }
  return { turtle: lines.length ? `${lines.join("\n")}\n${text}` : text, shift: lines.length };
}

// ------------------------------------------------------------------ terms
// a term as itself - a blank node by its own label -, to tell the triples of a graph apart
const own = (t) => (t.termType === "Quad" ? `<<( ${own(t.subject)} ${own(t.predicate)} ${own(t.object)} )>>` : String(t));

// a literal that Turtle writes without quotes: its datatype and the lexical forms it takes
const BARE = {
  [`${XSD}integer`]: /^[+-]?\d+$/,
  [`${XSD}decimal`]: /^[+-]?\d*\.\d+$/,
  [`${XSD}double`]: /^[+-]?(?:\d+\.\d*|\.\d+|\d+)[eE][+-]?\d+$/,
  [`${XSD}boolean`]: /^(?:true|false)$/,
};

function show(state, t, blanks, predicate = false) {
  // a term as Turtle writes it, for the summary: an IRI with the seed's prefixes (rdf:type as a), a
  // literal in quotes with its language or datatype - a number or a boolean as it stands, so that
  // 3596999 and "3596999" look different -, a blank node numbered as it first comes
  if (t.termType === "NamedNode") return predicate && t.value === RDF_TYPE ? "a" : shorten(state, t.value);
  if (t.termType === "BlankNode") {
    if (!blanks.has(t.value)) blanks.set(t.value, `_:b${blanks.size + 1}`);
    return blanks.get(t.value);
  }
  if (t.termType === "Literal") {
    const datatype = t.datatype?.value || `${XSD}string`;
    if (BARE[datatype]?.test(t.value)) return t.value;
    const quoted = JSON.stringify(t.value);
    if (t.language) return `${quoted}@${t.language}${t.direction ? `--${t.direction}` : ""}`;
    return datatype === `${XSD}string` ? quoted : `${quoted}^^${shorten(state, datatype)}`;
  }
  if (t.termType === "Quad") {
    return `<<( ${show(state, t.subject, blanks)} ${show(state, t.predicate, blanks, true)} ${show(state, t.object, blanks)} )>>`;
  }
  return `?${t.termType}`;
}

// ------------------------------------------------------------------ evaluation
// Oxigraph's messages: "Parser error at line 5 column 3: ...", "Parser error at line 5 between
// columns 1 and 11: ...", "Parser error between line 3 column 7 and line 4 column 11: ..."
const AT = /^Parser error (?:at line (\d+) (?:column (\d+)|between columns (\d+) and \d+)|between line (\d+) column (\d+) and line \d+ column \d+): (.*)$/;

function failure(e, shift, W) {
  const text = String(e?.message ?? e).split("\n")[0];
  const at = AT.exec(text);
  if (!at) return { status: /^Parser error/.test(text) ? "syntax" : "error", error: text };
  const line = Math.max(1, Number(at[1] ?? at[4]) - shift);     // the student's line: the seed's are in front
  return { status: "syntax", error: W.at(line, at[2] ?? at[3] ?? at[5], at[6]) };
}

export function evaluate(state, text, language) {
  const W = texts(language).engines;
  const { turtle, shift } = completed(state, text.replace(DOUBLE_QUOTES, '"').replace(SINGLE_QUOTES, "'"));
  let quads;
  try {
    quads = state.ox.parse(turtle, TURTLE);
  } catch (e) {
    return failure(e, shift, W);
  }
  const seen = new Set();
  const triples = [];                                  // the graph, a set: in the order written, each once
  for (const q of quads) {
    const it = `${own(q.subject)} ${own(q.predicate)} ${own(q.object)}`;
    if (!seen.has(it)) {
      seen.add(it);
      triples.push(q);
    }
  }
  if (!triples.length) return { status: "syntax", error: W.noTriples };
  if (triples.length > MAX_TRIPLES) return { status: "error", error: W.tooManyTriples(MAX_TRIPLES) };
  const rows = triples.map((q) => `${rdfjsTerm(q.subject)} ${rdfjsTerm(q.predicate)} ${rdfjsTerm(q.object)}`).sort();
  const blanks = new Map();
  return { status: "ok", canonical: `graph\n${rows.join("\n")}`, rows,
    summary: bounded({ kind: "graph", count: triples.length,
      rows: triples.slice(0, ROWS).map((q) => [show(state, q.subject, blanks), show(state, q.predicate, blanks, true),
        show(state, q.object, blanks)].map(cut)) }) };
}
