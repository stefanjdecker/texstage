# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A kind of activity - the provisional contract (F2's plan, 4.2: "first the four as classes"; the
design's 7.1 is its sketch). Today's four kinds stand behind it (kinds/texstage-kinds-sql,
kinds/texstage-kinds-rdf), so that package 2 can cut the contract, API 0, from what they share and
from where they differ - not from the sketch. Whatever is here may change with it.

A kind is a class the core makes once; it has no state, no messages, no lifecycle (the design's 6.1):

    build(options, bodies, files) -> Built        the author's machine: its keys checked, its data made
    prepare(item, keys, files, ...) -> Prepared   a worker, once per seed: what its checks run against
    copy(prepared, most) -> bytes | None          optional: what prepare made, for every worker (first)
    normalize(step, entry) -> Entry               a worker: the entry cleaned - or Unfit, said at once
    check(prepared, step, entry) -> Check         a worker: one distinct entry, within its budget

What the four taught, beyond the sketch (the plan's 4.2 lists it for package 2): normalize gives an
entry, not a string - a tuple's fields stay fields -, and may refuse; a check carries what stays in its
worker (the canonical form its key is made of, the rows the next checks are compared with); prepare is
not alike on every worker, and where a kind has a copy of what it made, every worker - the first too -
checks on the copy (first); a kind says how many entries a student has by default (LIMIT) and what it
calls a student's text (TEXT). A check of an entry that is not of the kind's input is the core's fault,
not the student's: it raises TypeError, which the core makes an internal check.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from types import MappingProxyType

from texstage.checks.cleaning import Unfit

__all__ = ["BUDGET_S", "FIELDS", "FROM_F1", "KEYS", "STATUSES", "Built", "Check", "Entry", "Kind", "Prepared", "Step",
           "Unbuildable", "Unfit", "first", "number", "referenced", "unused", "words"]

# a check's status (the design's 6.3); internal is the core's alone - no kind returns it
STATUSES = ("ok", "invalid", "error", "refused", "timeout", "internal")
FROM_F1 = {"syntax": "invalid"}             # what F1's checks, and the browser's before them, called it
KEYS = ("fields", "suggest", "tokens", "min", "review", "terms", "seed", "reference")   # a deck's keys that are a
#                                             kind's, in the record's order (build/activity.py); limit and open
#                                             are the core's
FIELDS = ("Subject", "Predicate", "Object")  # what fields= is when a deck does not give it (texactivity.sty)
WORD_MAX = 60                               # a field's label, a suggestion, a token
WORDS_MAX = 40                              # suggestions, tokens
BUDGET_S = 2.0                              # a check's CPU time in seconds, as F1's pool has it (server/pool.py)


class Unbuildable(ValueError):
    """A deck's activity cannot be built: why, without the activity's name - the core says which."""


@dataclass(frozen=True)
class Entry:
    """What a step's input sends: a text (input code) or the fields (input fields)."""
    text: str | None = None
    fields: tuple[str, ...] | None = None


@dataclass
class Built:
    """What a kind's build gives: its part of the public item (deck.json), of the keys (keys.json - the
    references, which no phone gets), and the files for the bundle, by name."""
    item: dict
    keys: dict = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)


@dataclass
class Step:
    """What a check knows of its step - never who sent the entry: the public item, the keys, the deck's
    language (the checks word their messages on the server, as F1's; codes are package 2's question)
    and the budget, a check's CPU time in seconds (None: none - the build, the tests)."""
    item: dict
    keys: dict = field(default_factory=dict)
    language: str | None = None
    budget_s: float | None = None


@dataclass
class Prepared:
    """What a worker keeps for a seed: the kind's own state - a database, a store - and the rows of the
    first reference that gave a result, which the checks after it are compared with (referenced)."""
    state: object = None
    rows: list | None = None


@dataclass
class Check:
    """A check (the design's 6.3). canonical, rows and memory stay in the worker: the form the key is
    made of, the result's rows as the comparison counts them, and that the check ran out of memory -
    which the pool tries once more on a fresh process.

    parts, for crowd: per field its key, its cleaned text, and whether this text is written as a literal -
    the text's, not the key's: with terms=loose, true and TRUE are one node and only the first is written
    as a literal; a node is a literal when its label is (today's _crowd), which the core chooses.
    at: the line and the column in the student's text, both from 1, the column in characters - as the
    message says them; a phone, whose strings count UTF-16 units, counts characters to find it."""
    status: str
    key: str | None = None
    parts: list[dict] | None = None
    verdict: str | None = None
    credit: float | None = None
    message: str | None = None                  # for the student, in the step's language
    at: tuple[int, int] | None = None
    detail: dict | None = None                  # for the windows: columns, the first rows, the comparison
    canonical: str | None = None
    rows: list | None = None
    memory: bool = False


class Kind:
    """A kind's base, provisional. NAME as a deck names it; INPUT one of the core's inputs (the design's
    6.2); REDUCTION groups, crowd or tally; OPTIONS the deck's keys it takes, each with a word for its
    type (the option types are package 2's); BUDGET_S a check's CPU time in seconds - a step's budget_s
    is in seconds too, as F1's pool counts -; LIMIT a student's entries by default."""
    NAME = ""
    API = 0
    INPUT = ""
    REDUCTION = ""
    OPTIONS: MappingProxyType = MappingProxyType({})
    BUDGET_S = BUDGET_S
    LIMIT = 5

    def build(self, options: dict, bodies: dict, files) -> Built:
        """options: the deck's keys as its record has them (words as lists, a file as its name); bodies:
        what the environment's body gave - {"seed": text, "references": [texts]}; files(name, what): a
        file of the deck's folder as text, Unbuildable when it is not there."""
        raise NotImplementedError

    def prepare(self, item: dict, keys: dict, files: dict[str, bytes], limits: dict | None = None,
                copy: bytes | None = None) -> Prepared:
        """files: the bundle's, by the names the item gives them; limits: what the pool allows this
        worker (heap_allowance); copy: what the first worker's prepare left (copy), in the seed's place."""
        return Prepared()

    def copy(self, prepared: Prepared, most: int) -> bytes | None:
        """What the first worker's prepare made, at most `most` bytes - where a seed need not give the
        same on every run (SQL's random()). Every worker then prepares from it, the first too (first):
        what ran the seed is not what was loaded from a copy. None: every worker prepares for itself."""
        return None

    def normalize(self, step: Step, entry: Entry) -> Entry:
        return entry

    def check(self, prepared: Prepared, step: Step, entry: Entry) -> Check:
        """One entry of the kind's input, as normalize gave it; of another type: TypeError."""
        raise NotImplementedError


def words(key: str, items: list[str]) -> list[str]:
    """A list of a deck's key - labels, suggestions, tokens - within its bounds."""
    if len(items) > WORDS_MAX or any(not w or len(w) > WORD_MAX for w in items):
        raise Unbuildable(f"{key}= takes at most {WORDS_MAX} items of 1 to {WORD_MAX} characters")
    return items


def number(key: str, value: str, default: int, top: int) -> int:
    """A number of a deck's key, 1 to top, in ASCII's digits (isdigit alone takes a superscript 2, which
    int does not, and an Arabic 3, which it does)."""
    if not value:
        return default
    if not (value.isascii() and value.isdigit()) or not 1 <= int(value) <= top:
        raise Unbuildable(f"{key}={value} - a number from 1 to {top}")
    return int(value)


def unused(kind: Kind, options: dict, bodies: dict | None = None) -> list[str]:
    """The keys a deck gave that this kind does not take - a warning of the build's. A seed or a reference
    is given as a key or in the body; fields left at their default were not given."""
    bodies = bodies or {}
    given = {**options, "seed": options.get("seed") or bodies.get("seed"),
             "reference": options.get("reference") or bodies.get("references")}
    if list(options.get("fields") or []) == list(FIELDS):
        given["fields"] = None
    return [k for k in KEYS if given.get(k) and k not in kind.OPTIONS]


def first(kind: Kind, item: dict, keys: dict, files: dict[str, bytes], limits: dict | None = None,
          most: int | None = None) -> tuple[Prepared, bytes | None]:
    """The first worker's preparing, as F1's (server/worker.py: _prepare): the seed's own run - and where
    the kind has a copy of what the run made, of at most `most` bytes, the worker lets go of the run and
    prepares from the copy, as every worker after it will: a database that ran its seed answers
    total_changes() otherwise than one loaded from a copy, and one text had two keys. Gives what was
    prepared and the copy for the others; a copy that does not load is none, and every worker runs the
    seed."""
    prepared = kind.prepare(item, keys, files, limits)
    data = kind.copy(prepared, most) if most is not None else None
    if not data:
        return prepared, None
    prepared = None                                     # the seed's own run goes first: one at a time
    try:
        return kind.prepare(item, keys, files, limits, copy=data), data
    except Exception:  # noqa: BLE001 - the copy does not load: every worker runs the seed
        return kind.prepare(item, keys, files, limits), None


def referenced(kind: Kind, prepared: Prepared, step: Step, budget_s: float | None = None) -> list[Check]:
    """The step's references checked, in their order, as a worker does before any student's text: the
    first that gives a result is the one the checks after it are compared with (its rows stay in
    prepared). budget_s: the references' own budget - they are the lecturer's, and F1's pool gives them
    ten seconds where a student's text has two; None: the step's."""
    if budget_s is not None:
        step = dataclasses.replace(step, budget_s=budget_s)
    checks, bare = [], Prepared(prepared.state)          # a reference is compared with none
    for text in step.keys.get("reference", []):
        check = kind.check(bare, step, Entry(text=text))
        if prepared.rows is None and check.status == "ok":
            prepared.rows = check.rows
        checks.append(check)
    return checks
