# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The checks' words, in English and German - the catalogs' `engines` (web/i18n/en.js, de.js), which the
browser's engines said them with; the server says them now (tests/test_checks.py compares the two)."""
from __future__ import annotations

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


class Words:
    """The engines' words in one language: W.service, W.at(line, column, message), W.tooManyTriples(n)."""

    def __init__(self, tag: str | None):
        self._t = ENGINES[language(tag)]

    def __getattr__(self, name: str):
        return self._t[name]

    def at(self, line, column, message) -> str:
        return self._t["at"].format(line=line, column=column, message=message)

    def tooManyTriples(self, n: int) -> str:  # noqa: N802 - the catalog's name
        return self._t["tooManyTriples"].format(n=n)

    def tooDeep(self, n: int) -> str:  # noqa: N802 - the catalog's name
        return self._t["tooDeep"].format(n=n)
