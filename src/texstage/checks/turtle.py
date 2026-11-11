# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The Turtle check (web/engines/turtle.js in Python; docs/live-activities-design.md, section 8.9): a
student's text read as Turtle by pyoxigraph's parser, the seed's @base and @prefix lines in front where
the text does not declare them; the seed's triples are no part of anybody's graph.

Texts that write the same graph get one key - full triples or ; and , , 3596999 or "3596999"^^xsd:integer,
a prefixed name or the IRI it stands for -, the SPARQL check's for a CONSTRUCT's graph: the triples as a
set, sorted, each term as sparql.py writes it (blank nodes all alike). A literal counts as written:
"03"^^xsd:integer is not 3. A phone keyboard's typographic quotes count as Turtle's.
"""
from __future__ import annotations

import re

import pyoxigraph as ox

from texstage.checks.common import (NESTING_MAX, ROWS, bounded, collected, cut, deadline, js_quote, js_sorted,
                                    mapped, message, nesting)
from texstage.checks.sparql import namespaces, prologue, rdf_term, shorten
from texstage.checks.texts import Words

MAX_TRIPLES = 10_000
XSD = "http://www.w3.org/2001/XMLSchema#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
QUOTES = str.maketrans({c: '"' for c in "“”„‟«»"} | {c: "'" for c in "‘’‚‛"})
BARE = {                                # a literal that Turtle writes without quotes, and its lexical forms
    f"{XSD}integer": re.compile(r"[+-]?\d+", re.A),
    f"{XSD}decimal": re.compile(r"[+-]?\d*\.\d+", re.A),
    f"{XSD}double": re.compile(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)[eE][+-]?\d+", re.A),
    f"{XSD}boolean": re.compile(r"true|false"),
}
# pyoxigraph's messages: "Parser error at line 5 column 3: ...", "Parser error at line 5 between columns 1 and
# 11: ...", "Parser error between line 3 column 7 and line 4 column 11: ..."
AT = re.compile(r"Parser error (?:at line (\d+) (?:column (\d+)|between columns (\d+) and \d+)|"
                r"between line (\d+) column (\d+) and line \d+ column \d+): (.*)", re.S)


def load(seed: str) -> dict:
    list(ox.parse(seed, format=ox.RdfFormat.TURTLE))      # a seed that does not parse says so now
    decls = prologue(seed)
    return {"decls": decls, "prefixes": namespaces(decls)}


def _completed(state: dict, text: str) -> tuple[str, int]:
    lines = []
    for d in state["decls"]:
        if "base" in d:
            if not re.search(r"^\s*(?:@base|BASE)\b", text, re.I | re.M):
                lines.append(f"@base <{d['base']}> .")
        elif not re.search(rf"^\s*(?:@prefix|PREFIX)\s+{re.escape(d['prefix'])}:", text, re.I | re.M):
            lines.append(f"@prefix {d['prefix']}: <{d['iri']}> .")
    return ("\n".join(lines) + "\n" + text if lines else text), len(lines)


def _own(t):
    """A term as itself - a blank node by its own label -, to tell the triples of a graph apart."""
    if isinstance(t, ox.Triple):
        return ("triple", _own(t.subject), _own(t.predicate), _own(t.object))
    if isinstance(t, ox.Literal):
        return ("literal", t.value, t.language, str(getattr(t, "direction", None) or ""), t.datatype.value if
                t.datatype else "")
    return (type(t).__name__, t.value)


def _show(state: dict, t, blanks: dict, predicate: bool = False) -> str:
    """A term as Turtle writes it, for the summary: an IRI with the seed's prefixes (rdf:type as a), a
    literal in quotes with its language or datatype - a number or a boolean as it stands -, a blank node
    numbered as it first comes."""
    if isinstance(t, ox.NamedNode):
        return "a" if predicate and t.value == RDF_TYPE else shorten(state, t.value)
    if isinstance(t, ox.BlankNode):
        if t.value not in blanks:
            blanks[t.value] = f"_:b{len(blanks) + 1}"
        return blanks[t.value]
    if isinstance(t, ox.Literal):
        datatype = t.datatype.value if t.datatype else f"{XSD}string"
        bare = BARE.get(datatype)
        if bare and bare.fullmatch(t.value):
            return t.value
        quoted = js_quote(t.value)
        if t.language:
            direction = f"--{t.direction}" if getattr(t, "direction", None) else ""
            return f"{quoted}@{t.language}{direction}"
        return quoted if datatype == f"{XSD}string" else f"{quoted}^^{shorten(state, datatype)}"
    if isinstance(t, ox.Triple):
        return (f"<<( {_show(state, t.subject, blanks)} {_show(state, t.predicate, blanks, True)} "
                f"{_show(state, t.object, blanks)} )>>")
    return f"?{type(t).__name__}"


def _failure(e: BaseException, shift: int, W: Words) -> dict:
    text = message(e)
    m = AT.fullmatch(text)
    if not m:
        return {"status": "syntax" if text.startswith("Parser error") else "error", "error": text}
    line = max(1, int(m.group(1) or m.group(4)) - shift)      # the student's line: the seed's are in front
    column = m.group(2) or m.group(3) or m.group(5)
    return {"status": "syntax", "error": W.at(line, column, m.group(6)), "at": (line, int(column))}


def evaluate(state: dict, text: str, language: str | None = None, budget_s: float | None = None) -> dict:
    """A text checked; budget_s, in a worker of the pool, its CPU time - read between triples."""
    W = Words(language)
    end = deadline(budget_s)
    if nesting(text) > NESTING_MAX:
        return {"status": "syntax", "error": W.tooDeep(NESTING_MAX)}
    turtle, shift = _completed(state, text.translate(QUOTES))
    try:
        quads = collected(ox.parse(turtle, format=ox.RdfFormat.TURTLE), end)
    except (SyntaxError, ValueError, OSError) as e:
        return _failure(e, shift, W)
    if quads is None:
        return {"status": "timeout"}
    seen, triples = set(), []                  # the graph, a set: in the order written, each once
    for q in quads:
        it = (_own(q.subject), _own(q.predicate), _own(q.object))
        if it not in seen:
            seen.add(it)
            triples.append(q)
    if not triples:
        return {"status": "syntax", "error": W.noTriples}
    if len(triples) > MAX_TRIPLES:
        return {"status": "error", "error": W.tooManyTriples(MAX_TRIPLES)}
    rows = mapped(triples, lambda q: f"{rdf_term(q.subject)} {rdf_term(q.predicate)} {rdf_term(q.object)}", end)
    if rows is None:
        return {"status": "timeout"}
    rows = js_sorted(rows)
    blanks: dict = {}
    shown = [[cut(_show(state, q.subject, blanks)), cut(_show(state, q.predicate, blanks, True)),
              cut(_show(state, q.object, blanks))] for q in triples[:ROWS]]
    return {"status": "ok", "canonical": "graph\n" + "\n".join(rows), "rows": rows,
            "summary": bounded({"kind": "graph", "count": len(triples), "rows": shown})}
