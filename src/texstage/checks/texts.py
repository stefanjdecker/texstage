# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The checks' words, in English and German - the catalogs' `engines` (web/i18n/en.js, de.js), which the
browser's engines said them with; the server says them now (tests/test_checks.py compares the two)."""
from __future__ import annotations

import contextlib
import contextvars

ENGINES = {
    "en": {
        "at": "line {line}, column {column}: {message}",
        "changesData": "only queries are run - this one changes the data",
        "noStatement": "no statement",
        "oneStatement": "one statement at a time",
        "queriesOnly": "only queries are run: SELECT, VALUES or WITH ... SELECT",
        "service": "SERVICE (a query to another endpoint) is not run",
        "noTriples": "no triples",
        "tooManyTriples": "more than {n} triples",
        "tooDeep": "nested more than {n} levels deep",
        "tooMuchMemory": "needs more memory than a check may use",
    },
    "de": {
        "at": "Zeile {line}, Spalte {column}: {message}",
        "changesData": "nur Anfragen werden ausgeführt – diese ändert die Daten",
        "noStatement": "keine Anweisung",
        "oneStatement": "nur eine Anweisung auf einmal",
        "queriesOnly": "nur Anfragen werden ausgeführt: SELECT, VALUES oder WITH … SELECT",
        "service": "SERVICE (eine Anfrage an einen anderen Endpunkt) wird nicht ausgeführt",
        "noTriples": "keine Tripel",
        "tooManyTriples": "mehr als {n} Tripel",
        "tooDeep": "mehr als {n} Ebenen tief verschachtelt",
        "tooMuchMemory": "braucht mehr Speicher, als eine Prüfung verwenden darf",
    },
}


def language(tag: str | None) -> str:
    """The catalog a tag gets: German for de and de-*, English for any other (web/i18n/i18n.js, languageOf)."""
    t = (tag or "").strip().lower().replace("_", "-")
    return "de" if t == "de" or t.startswith("de-") else "en"


class Said(str):
    """A text of the catalogs that knows what it says: its code there and the arguments it was made with -
    so that a kind can send the code and leave the words to the phone (the framework's design, 7.4)."""

    def __new__(cls, words: str, code: str, args: dict):
        said = super().__new__(cls, words)
        said.code, said.args = code, args
        return said

    def __getnewargs__(self):                       # pickled and copied whole, should one ever travel
        return str(self), self.code, self.args


_CODED = contextvars.ContextVar("texstage-checks-coded", default=False)


@contextlib.contextmanager
def coded():
    """While it is entered, the checks' words carry their codes (Said): a kind of the activity framework
    checks so (activities/code.py). F1's worker does not - its outcomes are plain text, as before."""
    token = _CODED.set(True)
    try:
        yield
    finally:
        _CODED.reset(token)


class Words:
    """The engines' words in one language: W.service, W.at(line, column, message), W.tooManyTriples(n)."""

    def __init__(self, tag: str | None):
        self._t = ENGINES[language(tag)]

    def _say(self, code: str, **args) -> str:
        words = self._t[code].format(**args)
        return Said(words, code, args) if _CODED.get() else words

    def __getattr__(self, name: str):
        return self._say(name)

    def at(self, line, column, message) -> str:
        return self._say("at", line=line, column=column, message=message)

    def tooManyTriples(self, n: int) -> str:  # noqa: N802 - the catalog's name
        return self._say("tooManyTriples", n=n)

    def tooDeep(self, n: int) -> str:  # noqa: N802 - the catalog's name
        return self._say("tooDeep", n=n)


def arguments(code: str) -> tuple[str, ...]:
    """What a text of the catalogs is made with, by its code: at -> (line, column, message)."""
    import string
    return tuple(name for _, name, _, _ in string.Formatter().parse(ENGINES["en"][code]) if name)
