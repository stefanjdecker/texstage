# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The SPARQL check (web/engines/sparql.js in Python; docs/live-activities-design.md, sections 8.4 and
8.6): Oxigraph - pyoxigraph - over the activity's seed, a Turtle graph whose @base and @prefix lines
every query that does not declare them itself gets in front.

The same result, the same canonical form, as sparql.js wrote it: a SELECT's rows as a bag - their order
does not count, repeated rows do -, the columns in the order the query projects them, their names not; a
value as its term (an IRI, a literal with its datatype or language; blank nodes all alike, an unbound one
"-"); an ASK's yes or no; a CONSTRUCT's or DESCRIBE's triples, sorted. Oxigraph keeps typed literals of the
XSD datatypes as values ("03"^^xsd:integer is "3").

SERVICE is refused before the query runs, by tokens - variables and prefixed names read whole, the
escapes decoded -: pyoxigraph would query the other endpoint over HTTP (F0). SERVICE SILENT too, which the
browser's build, without a network, answered with an empty solution.

The Turtle check (turtle.py) takes the seed's prologue and a graph's terms from here.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

import pyoxigraph as ox

from texstage.checks.common import (IRI, NESTING_MAX, ROWS, bounded, collected, cut, deadline, hash_comments,
                                    js_quote, js_sorted, mapped, message, nesting, utf16_len)
from texstage.checks.texts import Words

XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"
PROLOGUE = re.compile(r"^\s*(?:@base\s+<([^>]*)>\s*\.|BASE\s+<([^>]*)>|@prefix\s+([\w.-]*):\s*<([^>]*)>\s*\.|"
                      r"PREFIX\s+([\w.-]*):\s*<([^>]*)>)", re.I | re.M | re.A)
LOCAL = re.compile(r"[\w.-]*", re.A)
AT = re.compile(r"error at (\d+):(\d+): (.*)", re.S)


# ------------------------------------------------------------------ the seed and the prologue
def prologue(seed: str) -> list[dict]:
    """The seed's @base and @prefix lines (or BASE and PREFIX), in their order."""
    decls = []
    for m in PROLOGUE.finditer(seed):
        if m.group(1) is not None or m.group(2) is not None:
            decls.append({"base": m.group(1) if m.group(1) is not None else m.group(2)})
        else:
            decls.append({"prefix": m.group(3) if m.group(3) is not None else m.group(5),
                          "iri": m.group(4) if m.group(4) is not None else m.group(6)})
    return decls


def _resolved(base: str | None, iri: str) -> str:
    """iri against base, as JavaScript's URL resolves it: an empty fragment kept - "ns#" -, which urljoin
    drops before Python 3.14."""
    if not base:
        return iri
    if iri.endswith("#"):
        return urljoin(base, iri[:-1]) + "#"
    return urljoin(base, iri)


def namespaces(decls: list[dict]) -> list[tuple[str, str]]:
    """The prologue's prefixes as (prefix, namespace), for showing IRIs short - the longest namespace first."""
    base, prefixes = None, []
    for d in decls:
        if "base" in d:
            base = _resolved(base, d["base"])
        else:
            prefixes.append((d["prefix"], _resolved(base, d["iri"])))
    return sorted(prefixes, key=lambda p: -utf16_len(p[1]))


def load(seed: str) -> dict:
    """The seed's graph in a store of its own, its blank nodes numbered in the order they come: pyoxigraph
    gives each a random id as it reads it, and the order of blank nodes - ORDER BY, and what a LIMIT
    takes after it - differed from one process of the pool to the next (2026-11-10)."""
    store = ox.Store()
    store.extend(_numbered(ox.parse(seed, format=ox.RdfFormat.TURTLE)))
    decls = prologue(seed)
    return {"store": store, "decls": decls, "prefixes": namespaces(decls)}


def _numbered(quads) -> list:
    ids: dict[str, ox.BlankNode] = {}

    def term(t):
        if isinstance(t, ox.BlankNode):
            b = ids.get(t.value)
            if b is None:
                b = ids[t.value] = ox.BlankNode(f"{len(ids) + 1:x}")
            return b
        if isinstance(t, ox.Triple):
            return ox.Triple(term(t.subject), t.predicate, term(t.object))
        return t

    return [ox.Quad(term(q.subject), q.predicate, term(q.object), q.graph_name) for q in quads]


def _completed(state: dict, text: str) -> tuple[str, int]:
    """The seed's declarations in front of a query that does not make them itself; how many lines.

    The seed's base is in front of every query, one with a BASE of its own too: the seed's prefixes
    may be relative to it - `@prefix : <> .`, as the lectures' seeds have -, and the query's own BASE,
    behind them, is the base of what the query writes. Until 2026-11-12 a query with a BASE got the
    seed's prefixes without the seed's base - where a relative one has no base at all: a syntax error,
    in a line the student did not write."""
    lines = []
    for d in state["decls"]:
        if "base" in d:
            lines.append(f"BASE <{d['base']}>")
        elif not re.search(rf"^\s*PREFIX\s+{re.escape(d['prefix'])}:", text, re.I | re.M):
            lines.append(f"PREFIX {d['prefix']}: <{d['iri']}>")
    return ("\n".join(lines) + "\n" + text if lines else text), len(lines)


# ------------------------------------------------------------------ SERVICE
ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})")
# A query's words - a variable, a prefixed name with its escapes (ex:a\#b), a word - and the characters
# that begin or end what hides them: a comment, a string, an IRI, an escape.
STEPS = re.compile(r"""[?$][\w\u00b7\u0300-\u036f\u203f-\u2040]+"""
                   r"""|(?:[^\W\d_][\w.\-\u00b7]*)?:(?:[\w.\-:%\u00b7\u0300-\u036f\u203f-\u2040]|\\[^\n\r])*"""
                   r"""|[^\W\d_]\w*|[#\\'"<\n\r]""")


def comments(text: str) -> list[tuple[int, int]]:
    """Where the query's comments are - for the kind's normalize, which takes them out: what is one
    whether a < is an IRI's start or the comparison (common.hash_comments)."""
    return hash_comments(text, less_than=True)


def _decoded(text: str) -> str:
    return ESCAPE.sub(lambda m: chr(int(m.group(1) or m.group(2), 16)), text)


def _service(text: str) -> bool:
    """Whether SERVICE is a word of the query however it is read: Oxigraph takes a < as an IRI's start or as
    the comparison, as the grammar around it wants, so the text is read both ways at once, as its comments
    are (common.hash_comments) - and where a comment is found to be none, the cautious way round: a word
    counts if one reading has it. In `FILTER(?o<'>') SERVICE <e> { } FILTER(?o != 'c')` the first reading
    finds an IRI, <'>, and a string behind it, ') SERVICE ... '; the second, Oxigraph's, a comparison with
    the string '>' - and the word.

    What an IRI may be is no query's word in either reading - <http://e.org/SERVICE> -: no space and no
    brace is in it, and SERVICE wants an endpoint and a brace behind it. A string that goes over its
    line's end is no text Oxigraph takes; it is read on as if it had ended there."""
    if "ervice" not in text.lower():
        return False
    states = {("code", 0, 0)}               # the readings: (code, # - a comment -, a string's quotes; read from; words from)
    for step in STEPS.finditer(text):
        i, c = step.start(), step.group()
        mark = len(c) == 1 and c in "#\\'\"<\n\r"
        after = set()
        for mode, since, quiet in states:
            if i < since:                                   # inside what this reading took whole
                after.add((mode, since, quiet))
            elif not mark:
                if mode == "code" and i >= quiet and c.upper() == "SERVICE":
                    return True
                after.add((mode, since, quiet))
            elif mode == "#":
                after.add(("code" if c in "\n\r" else "#", 0, quiet))
            elif mode == "code":
                if c == "#":
                    after.add(("#", 0, quiet))
                elif c == "\\":
                    after.add(("code", i + 2, quiet))
                elif c in "'\"":
                    after.add((c * 3, i + 3, quiet) if text.startswith(c * 3, i) else (c, 0, quiet))
                elif c == "<" and (m := IRI.match(text, i)):
                    after.add(("code", m.end(), quiet))     # an IRI
                    after.add(("code", 0, m.end()))         # ... or the comparison, and no word up to its >
                else:
                    after.add(("code", 0, quiet))
            elif c == "\\":                                 # in a string, short or long
                after.add((mode, i + 2, quiet))
            elif text.startswith(mode, i):
                after.add(("code", i + len(mode), quiet))
            else:
                after.add(("code" if c in "\n\r" and len(mode) == 1 else mode, 0, quiet))
        states = {(mode, since if since > i + 1 else 0, quiet if quiet > i + 1 else 0) for mode, since, quiet in after}
    return False


def names_service(text: str) -> bool:
    """Whether the keyword SERVICE is in the query - a word of its own, not a part of a string, an IRI, a
    comment, a variable or a prefixed name -, as written or with its escapes decoded.

    Until 2026-11-12 a pattern read the text one way, and four texts got the word past it, which Oxigraph
    then ran (found with the review of the kinds' comments): a name's escape - in ex:a\\#b the # began a
    comment here, in ex:a\\'b the ' a string -; an IRI with a no-break space or a \\u escape in front of
    its #, which was none here; a long string with an escaped quote at its end, '''a\\'''' - its last quote
    began a string; and a comparison that looks like an IRI's start (_service)."""
    return _service(text) or _service(_decoded(text))


# ------------------------------------------------------------------ terms
def json_term(t) -> str:
    """A SELECT's value as sparql.js wrote it from the JSON results - a literal's direction not shown."""
    if t is None:
        return "-"
    if isinstance(t, ox.NamedNode):
        return f"<{t.value}>"
    if isinstance(t, ox.BlankNode):
        return "_:"
    if isinstance(t, ox.Literal):
        if t.language:
            return f"{js_quote(t.value)}@{t.language.lower()}"
        return f"{js_quote(t.value)}^^<{t.datatype.value if t.datatype else XSD_STRING}>"
    return "?triple"


def rdf_term(t) -> str:
    """A graph's term in the canonical form - with RDF 1.2's text direction and triple terms."""
    if isinstance(t, ox.NamedNode):
        return f"<{t.value}>"
    if isinstance(t, ox.BlankNode):
        return "_:"
    if isinstance(t, ox.Literal):
        if t.language:
            direction = f"--{t.direction}" if getattr(t, "direction", None) else ""
            return f"{js_quote(t.value)}@{t.language.lower()}{direction}"
        return f"{js_quote(t.value)}^^<{t.datatype.value if t.datatype else XSD_STRING}>"
    if isinstance(t, ox.Triple):
        return f"<<( {rdf_term(t.subject)} {rdf_term(t.predicate)} {rdf_term(t.object)} )>>"
    return f"?{type(t).__name__}"


def shorten(state: dict, iri: str) -> str:
    for p, ns in state["prefixes"]:
        if ns and iri.startswith(ns) and LOCAL.fullmatch(iri[len(ns):]):
            return f"{p}:{iri[len(ns):]}"
    return f"<{iri}>"


def _show(state: dict, t) -> str:
    if t is None:
        return ""
    if isinstance(t, ox.NamedNode):
        return cut(shorten(state, t.value))
    if isinstance(t, ox.BlankNode):
        return "_:b"
    if isinstance(t, ox.Literal):
        return cut(f"{t.value}@{t.language}" if t.language else t.value)
    return cut(str(t))


# ------------------------------------------------------------------ evaluation
def _failure(e: BaseException, shift: int, W: Words) -> dict:
    text = message(e)
    m = AT.fullmatch(text)
    if m:
        line = max(1, int(m.group(1)) - shift)              # the student's line: the seed's prefixes are in front
        return {"status": "syntax", "error": W.at(line, int(m.group(2)), m.group(3)), "at": (line, int(m.group(2)))}
    return {"status": "error", "error": text}


def evaluate(state: dict, text: str, language: str | None = None, budget_s: float | None = None) -> dict:
    """A query checked; budget_s, in a worker of the pool, its CPU time - read between solutions, the
    rest the pool's watchdog's."""
    W = Words(language)
    end = deadline(budget_s)
    if nesting(text) > NESTING_MAX:
        return {"status": "syntax", "error": W.tooDeep(NESTING_MAX)}
    if names_service(text):
        return {"status": "refused", "error": W.service}
    query, shift = _completed(state, text)
    try:
        result = state["store"].query(query)
        if isinstance(result, ox.QueryBoolean):
            yes = bool(result)
            return {"status": "ok", "canonical": f"ask\n{'true' if yes else 'false'}",
                    "rows": ["true" if yes else "false"], "summary": {"kind": "ask", "boolean": yes}}
        if isinstance(result, ox.QueryTriples):
            triples = collected(result, end)
            rows = None if triples is None else mapped(
                triples, lambda t: f"{rdf_term(t.subject)} {rdf_term(t.predicate)} {rdf_term(t.object)}", end)
            if rows is None:
                return {"status": "timeout"}
            rows = js_sorted(rows)
            return {"status": "ok", "canonical": "graph\n" + "\n".join(rows), "rows": rows,
                    "summary": bounded({"kind": "graph", "count": len(triples), "rows": [
                        [_show(state, x) for x in (t.subject, t.predicate, t.object)] for t in triples[:ROWS]]})}
        variables = list(result.variables)
        solutions = collected(result, end)
        rows = None if solutions is None else mapped(
            solutions, lambda s: "\t".join(json_term(s[v]) for v in variables), end)
        if rows is None:
            return {"status": "timeout"}
    except (SyntaxError, ValueError, OSError, RuntimeError) as e:
        return _failure(e, shift, W)
    names = [v.value for v in variables]
    rows = js_sorted(rows)
    return {"status": "ok", "canonical": f"select\n{len(names)}\n" + "\n".join(rows), "rows": rows,
            "summary": bounded({"kind": "select", "columns": [f"?{n}" for n in names], "count": len(solutions),
                                "rows": [[_show(state, s[v]) for v in variables] for s in solutions[:ROWS]]})}
