# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The checks of live activities, on the server (docs/architecture/activity-framework-plan.md, F1): the
browser's three engines (web/engines: sql.js, sparql.js, turtle.js) in Python - SQL with Python's
sqlite3, SPARQL and Turtle with pyoxigraph -, giving what they gave: the same status, error, canonical
form, key, rows and summary (tests/test_checks.py against tests/fixtures/checks/).

    state = load(engine, seed)                      # once per worker and activity
    result = evaluate(engine, state, text, language)  # {status, error?, canonical?, key?, rows?, summary?}
    comments(engine, text)                          # where its comments are: [(start, end), ...]
"""
from __future__ import annotations

from texstage.checks import common

ENGINES = ("sql", "sparql", "turtle")


def _module(engine: str):
    if engine == "sql":
        from texstage.checks import sql as mod
    elif engine == "sparql":
        from texstage.checks import sparql as mod
    elif engine == "turtle":
        from texstage.checks import turtle as mod
    else:
        raise ValueError(f"no engine {engine!r}")
    return mod


def load(engine: str, seed: str, **options) -> dict:
    """The seed read once: the state the engine's texts are checked against."""
    return _module(engine).load(seed, **options)


def comments(engine: str, text: str) -> list[tuple[int, int]]:
    """Where a text's comments are, (start, end) in their order, as the engine reads it - what a kind's
    normalize takes out (cleaning.uncommented)."""
    return _module(engine).comments(text)


def evaluate(engine: str, state: dict, text: str, language: str | None = None, **options) -> dict:
    """A text checked: its status (ok, syntax, error, refused - and timeout, over its budget), error, and for
    a result its canonical form, the form's key, its rows and its summary. A lone surrogate in the text -
    which only a broken phone sends - counts as U+FFFD, as it did in the browser's Oxigraph."""
    result = _module(engine).evaluate(state, common.well_formed(text), language, **options)
    if "canonical" in result:
        result["key"] = common.key(result["canonical"])
    return result
