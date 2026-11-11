# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage's kinds for RDF (docs/architecture/activity-framework-design.md, section 17):

    triples        two or three fields, drawn as the crowd's graph - today's input=tuple
    sparql-query   a query over the seed's graph, run by pyoxigraph - today's input=code, engine=sparql
    turtle-graph   a graph written in Turtle, parsed by pyoxigraph; of the seed only its @base and
                   @prefix lines count - today's input=code, engine=turtle

Behind the provisional contract (texstage.activities.kind; F2's plan, package 1). The two checks are
still F1's (texstage.checks.sparql, .turtle) and move here once F1 is in main; a tuple's cleaning is
the activity type's until the core replaces it (texstage.checks.cleaning)."""
from __future__ import annotations

from types import MappingProxyType

try:
    from texstage.activities.code import CodeKind
except ImportError as e:                                  # an older texstage: say what is missing
    raise ImportError("texstage-kinds-rdf needs a texstage with the activity framework's contract "
                      "(texstage.activities); this one has none") from e
from texstage.activities.kind import Built, Check, Entry, Kind, Prepared, Step, Unbuildable, Unfit, number, words
from texstage.checks import cleaning

__all__ = ["SparqlQuery", "Triples", "TurtleGraph"]

TURTLE = {".ttl": "text/turtle; charset=utf-8"}


class SparqlQuery(CodeKind):
    NAME = "sparql-query"
    ENGINE = "sparql"
    MODULE = "texstage.checks.sparql"
    SEED = TURTLE
    TOKENS = ["{", "}", "?", ".", ";", ":"]
    TEXT = "a query"


class TurtleGraph(CodeKind):
    NAME = "turtle-graph"
    ENGINE = "turtle"
    MODULE = "texstage.checks.turtle"
    SEED = TURTLE
    TOKENS = [":", ".", ";", ",", '"', "@", "^^", "<", ">", "_:", "[", "]", "(", ")"]
    TEXT = "a Turtle text"


class Triples(Kind):
    """The crowd's graph: every entry two or three terms - the first and the last a node, a middle one
    the edge's label. Nothing to prepare, nothing to run: the check says each field's key (terms=exact:
    the term as written; loose: as the word cloud groups words) and whether this text is written as a
    literal - the text's, not the key's: a node is a literal when its label is, which the core chooses;
    equal keys are one entry, and the lecturer's merges stay the core's."""
    NAME = "triples"
    INPUT = "fields"
    REDUCTION = "crowd"
    OPTIONS = MappingProxyType({"fields": "words", "suggest": "words", "min": "number", "review": "flag",
                                "terms": "choice"})
    LIMIT = 10
    FIELDS = (2, 3)
    TERMS = ("exact", "loose")

    def build(self, options: dict, bodies: dict, files) -> Built:
        fields = list(options.get("fields") or [])
        if not self.FIELDS[0] <= len(fields) <= self.FIELDS[1]:
            raise Unbuildable(f"{len(fields)} fields - an activity of input=tuple has {self.FIELDS[0]} or "
                              f"{self.FIELDS[1]}: the first and the last a node, a middle one the edge's label")
        item: dict = {"fields": words("fields", fields)}
        suggest = words("suggest", list(options.get("suggest") or []))
        if suggest:
            item["suggest"] = suggest
        item["min"] = number("min", options.get("min") or "", 1, 1000)
        if options.get("review"):
            item["review"] = True
        terms = options.get("terms") or ""
        if terms and terms not in self.TERMS:
            raise Unbuildable(f"terms={terms} - {' or '.join(self.TERMS)}")
        item["terms"] = terms or self.TERMS[0]
        return Built(item)

    def normalize(self, step: Step, entry: Entry) -> Entry:
        """The fields cleaned: control characters out, spaces collapsed, a phone's typographic quotes
        the ones Turtle writes."""
        n = len(step.item["fields"])
        if not isinstance(entry.fields, (list, tuple)) or len(entry.fields) != n:    # (a string has a length too)
            raise Unfit(f"fields: {n} texts")
        return Entry(fields=tuple(cleaning.clean_term(f) for f in entry.fields))

    def check(self, prepared: Prepared, step: Step, entry: Entry) -> Check:
        if not isinstance(entry.fields, tuple):               # not the student's error: the core's
            raise TypeError(f"{self.NAME} checks fields, not {entry!r}")
        parts = [{"key": cleaning.term_key(f, step.item), "text": f, "literal": cleaning.is_literal(f)}
                 for f in entry.fields]
        return Check("ok", key="\x1f".join(p["key"] for p in parts), parts=parts)
