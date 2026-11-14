# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A kind of activity - the contract, API 0 (docs/architecture/activity-framework-design.md, 6 and 7;
cut from today's four kinds: the plan of F2, 4.2). API 0 may change with any package until F4 calls it
API 1.

A kind is a class the core makes once, found by its package's entry point (registry.py). It has no
state, no messages and no lifecycle of its own: everything it does is a function the core calls with
data.

    class SqlQuery(Kind):
        NAME = "sql-query"                    # as a deck names it, and its entry point
        API = 0                               # the contract it implements
        INPUT = "code"                        # one of the core's inputs (INPUTS)
        REDUCTION = "groups"                  # groups | crowd | tally
        OPTIONS = fixed(tokens=Words(), seed=File(".sql"), reference=File())           # options.py
        MESSAGES = fixed(service=(), at=("line", "column", "message"))       # what a check may say, by code
        BUDGET_S = 1.0                        # a check's CPU time in seconds
        LIMIT = 5                             # a student's entries, unless the deck says

        def build(self, options, bodies) -> Built: ...           # the author's machine: its keys, its data
        def prepare(self, item, keys, files, limits=None, copy=None) -> Prepared: ...    # a worker, per seed
        def copy(self, prepared, most) -> bytes | None: ...      # optional: what prepare made, for every worker
        def normalize(self, step, entry) -> Entry: ...           # a worker: the entry cleaned - or Unfit
        def reference(self, step, text) -> Entry: ...            # a reference as an entry: by default its text
        def check(self, prepared, step, entry) -> Check: ...     # a worker: one distinct entry, in its budget

What the core promises a kind: prepare runs before any check of its seed, once per worker - and where
the kind has a copy of what the first worker's prepare made, every worker, the first too, prepares from
the copy (first); the references are checked first, compared with none, each with a budget of its own
(referenced); check gets one entry of the kind's input, as normalize gave it, and never who sent it.
What a kind promises: check leaves what was prepared as it found it; it raises for nothing a student
can send - an entry that is not of its input is the core's fault, TypeError -; and what it returns keeps
the rules of fault(), or the core makes the check internal.
"""
from __future__ import annotations

import dataclasses
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from texstage.activities.options import Options, Unbuildable
from texstage.checks.cleaning import Unfit

__all__ = ["API", "BUDGET_S", "COMPARED", "INPUTS", "REDUCTIONS", "SEVERAL", "STATUSES", "VERDICTS", "Built", "Check", "Entry", "Kind",
           "Message", "Prepared", "Step", "Unbuildable", "Unfit", "fault", "first", "fixed", "kept", "referenced", "validated"]

API = 0
INPUTS = ("code", "fields", "choice", "number", "text")       # the core's inputs (the design's 6.2)
REDUCTIONS = ("groups", "crowd", "tally")
# a check's status (the design's 6.3); internal is the core's alone - no kind returns it
STATUSES = ("ok", "invalid", "error", "refused", "timeout", "internal")
VERDICTS = ("correct", "partial", "incorrect")
FROM_F1 = {"syntax": "invalid"}             # what F1's checks, and the browser's before them, called it
NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")           # a kind's name: sql-query
CODE = re.compile(r"[a-z][a-zA-Z0-9]*")                       # an option's key; a message's code, as the catalogs name texts
BUDGET_S = 1.0                              # a check's CPU time in seconds, as the pool has it (server/pool.py)
BUDGET_MAX_S = 10.0                         # at most (the design's 11)
LIMIT_MAX = 50                              # a student's entries, at most
KEY_MAX = 4096                              # a key's characters: a hash - or a tuple's three terms, whose loose
#                                             keys may be many times their 60 characters (a ligature is three)
ARGUMENT_MAX = 300                          # a message's argument, if it is a text
DETAIL_MAX = 12 * 1024                      # a detail's JSON in characters, as it is sent (the design's 6.3)
COMPARED = "diff"                           # in a detail: what it says of the reference - the comparison with it.
#                                             The core keeps it from the projector until the reveal (reduce.py)
SEVERAL = "\n"                              # a tally's key of several choices: their texts, a line each - which
#                                             no option has (choice.build), and the core counts each (reduce.py)
SAFE = 2**53                                # the largest whole number a phone's JSON keeps


@dataclass(frozen=True)
class Entry:
    """What a step's input sends - one of: a text (the inputs code and text), the fields (input fields), a
    choice - the options' places in the item's `options`, from 0 (input choice) - or a number (input
    number). As the core stores it and hands it to a worker: stored(), of()."""
    text: str | None = None
    fields: tuple[str, ...] | None = None
    choice: tuple[int, ...] | None = None
    number: float | int | None = None

    def stored(self) -> dict:
        """The entry as the core keeps it - {"text": ...}, {"fields": [...]}, {"choice": [...]} or {"number":
        ...} -; ValueError for one that is none of them, or more than one."""
        given = {name: getattr(self, name) for name in ("text", "fields", "choice", "number") if getattr(self, name) is not None}
        if len(given) != 1:
            raise ValueError(f"an entry is a text, the fields, a choice or a number - not {sorted(given) or 'nothing'}")
        name, value = next(iter(given.items()))
        return {name: list(value) if name in ("fields", "choice") else value}

    @classmethod
    def of(cls, stored: dict) -> Entry:
        """An entry as the core keeps it (stored), made an entry again - the lists as tuples."""
        fields, choice = stored.get("fields"), stored.get("choice")
        return cls(text=stored.get("text"), fields=tuple(fields) if isinstance(fields, list) else fields,
                   choice=tuple(choice) if isinstance(choice, list) else choice, number=stored.get("number"))


@dataclass(frozen=True)
class Message:
    """What a check says to the student: a code into the kind's texts and what the text is made with - the
    phone says it in its language, the server sends no words (the design's 7.4). A kind lists its codes
    and their arguments (MESSAGES); an argument is a number or a text of at most 300 characters. A
    message's code is fixed; its arguments are the table the kind made."""
    code: str
    args: dict = field(default_factory=dict, hash=False)


@dataclass
class Built:
    """What a kind's build gives: its part of the public item (deck.json), of the keys (keys.json - the
    references, which no phone gets), and the files for the bundle, by name."""
    item: dict
    keys: dict = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)


@dataclass
class Step:
    """What a check knows of its step - never who sent the entry: the public item, the keys, and the
    budget, a check's CPU time in seconds (None: none - the build; the kit gives its own). language: the
    deck's, for a detail that has words of its own; a message has none (Message)."""
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
    """A check (the design's 6.3). What the core stores and sends is sent(); canonical, rows and memory
    stay in the worker: the form the key is made of, the result's rows as the comparison counts them, and
    that the check ran out of memory - which the pool tries once more on a fresh process.

    parts, for crowd: per field its key, its cleaned text, and whether this text is written as a literal -
    the text's, not the key's: with terms=loose, true and TRUE are one node and only the first is written
    as a literal; a node is a literal when its label is, which the core chooses.
    at: the line and the column in the student's text, both from 1, the column in characters; a phone,
    whose strings count UTF-16 units, counts characters to find it.
    detail: whatever of it tells how the entry compares with the reference goes under COMPARED ("diff") and
    nowhere else: the core takes that out of what the projector gets until the reveal, and knows no other
    part of a detail."""
    status: str
    key: str | None = None
    parts: list[dict] | None = None
    verdict: str | None = None
    credit: float | None = None
    message: Message | None = None
    at: tuple[int, int] | None = None
    detail: dict | None = None                  # for the windows: columns, the first rows, the comparison
    canonical: str | None = None
    rows: list | None = None
    memory: bool = False

    def sent(self) -> dict:
        """What leaves the worker: the fields that are set, a message as {code, args}, at as a list."""
        out: dict = {"status": self.status}
        for name in ("key", "parts", "verdict", "credit", "detail"):
            if getattr(self, name) is not None:
                out[name] = getattr(self, name)
        if self.message is not None:
            out["message"] = {"code": self.message.code, "args": dict(self.message.args)}
        if self.at is not None:
            out["at"] = list(self.at)
        return out


def fixed(**declared) -> MappingProxyType:
    """A kind's OPTIONS - the deck's keys it takes, each with its type (options.py) - or its MESSAGES - what
    its checks may say, each code with the names of its arguments: a table nobody changes, since a class's
    is its subclasses' too."""
    return MappingProxyType(dict(declared))


class Kind:
    """A kind's base (the module's text has the contract)."""
    NAME = ""
    API = API
    INPUT = ""
    REDUCTION = ""
    OPTIONS: MappingProxyType = fixed()
    MESSAGES: MappingProxyType = fixed()
    BUDGET_S = BUDGET_S
    LIMIT = 5

    def build(self, options: Options, bodies: dict) -> Built:
        """options: the deck's keys, each read and checked as it is asked for (options.py: Options) - a
        refusal is Unbuildable, in the order the kind asks; bodies: what the environment's body gave -
        {"seed": text, "references": [texts]}."""
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
        """The entry cleaned: entries that normalize alike are checked once. Unfit (with the phone's code)
        for one that is not checked at all - too long, empty."""
        return entry

    def reference(self, step: Step, text: str) -> Entry:
        """A reference of the deck (keys.json: its text, as the build wrote it) as an entry of the kind's
        input, which check is given like a student's: by default the text."""
        return Entry(text=text)

    def check(self, prepared: Prepared, step: Step, entry: Entry) -> Check:
        """One entry of the kind's input, as normalize gave it; of another type: TypeError."""
        raise NotImplementedError


# ------------------------------------------------------------------ what a check must keep
def _text(v, most: int) -> bool:
    """A text of at most `most` characters that a store and a phone take: no half of a surrogate pair."""
    if not isinstance(v, str) or len(v) > most:
        return False
    try:
        v.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _number(v) -> bool:
    """A number a phone's JSON keeps: whole up to 2^53, or finite."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return -SAFE <= v <= SAFE
    return isinstance(v, float) and math.isfinite(v)


def fault(kind: Kind, check, step: Step | None = None) -> str | None:
    """The rule a kind's check breaks, in words - or None. The core holds every check against it before
    it stores one (validated); the kit, every fixture's. It never raises: a check - or a kind - that
    cannot even be held against the rules breaks them."""
    try:
        return _fault(kind, check, step)
    except Exception as e:  # noqa: BLE001 - a RecursionError among them
        return f"the check cannot be held against the rules - {type(e).__name__}: {str(e)[:200]}"


def _fault(kind: Kind, check, step: Step | None) -> str | None:
    if not isinstance(check, Check):
        return f"check gave {type(check).__name__}, not a Check"
    if not isinstance(check.status, str) or check.status not in STATUSES or check.status == "internal":
        return f"the status {check.status!r}: one of {', '.join(s for s in STATUSES if s != 'internal')}"
    if check.status == "ok":
        if not check.key or not _text(check.key, KEY_MAX):
            return f"a check that is ok has a key, a text of 1 to {KEY_MAX} characters"
    elif check.key is not None or check.parts is not None or check.detail is not None:
        return f"a check that is {check.status} has no key, parts or detail"
    if check.verdict is not None and (not isinstance(check.verdict, str) or check.verdict not in VERDICTS):
        return f"the verdict {check.verdict!r}: {', '.join(VERDICTS)} or none"
    if check.credit is not None:
        if check.verdict is None:
            return "a credit without a verdict"
        if not _number(check.credit) or not 0 <= check.credit <= 1:
            return f"the credit {check.credit!r}: a number from 0 to 1"
    if check.message is not None:
        m = check.message
        codes = kind.MESSAGES if isinstance(kind.MESSAGES, Mapping) else {}
        if not isinstance(m, Message) or not isinstance(m.code, str) or m.code not in codes:
            return f"the message {getattr(m, 'code', m)!r}: none of the kind's MESSAGES"
        if not isinstance(m.args, dict) or set(m.args) != set(codes[m.code]):
            return f"the message {m.code}: its arguments are {', '.join(codes[m.code]) or 'none'}"
        if not all(_number(v) or _text(v, ARGUMENT_MAX) for v in m.args.values()):
            return (f"the message {m.code}: an argument is a number a phone can read or a text of at most "
                    f"{ARGUMENT_MAX} characters")
    if check.at is not None:
        at = check.at
        if not (isinstance(at, tuple) and len(at) == 2 and all(type(n) is int and n >= 1 for n in at)):
            return f"at {at!r}: a line and a column, both whole numbers from 1"
    if check.detail is not None:
        if not isinstance(check.detail, dict):
            return f"the detail: a table of at most {DETAIL_MAX // 1024} KiB as JSON"
        try:                                            # as it is sent: no character escaped, no space between
            size = len(json.dumps(check.detail, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        except (TypeError, ValueError, RecursionError):
            return "the detail is not JSON a phone can read"
        if size > DETAIL_MAX:
            return f"the detail: a table of at most {DETAIL_MAX // 1024} KiB as JSON"
    if kind.REDUCTION == "crowd" and check.status == "ok":
        item = step.item if step is not None and isinstance(step.item, dict) else {}
        fields = item.get("fields") if isinstance(item.get("fields"), (list, tuple)) else None
        if not isinstance(check.parts, list) or not check.parts or (fields is not None and len(check.parts) != len(fields)):
            return "a check for crowd that is ok has parts, one for each field"
        for p in check.parts:
            if not (isinstance(p, dict) and set(p) == {"key", "text", "literal"} and isinstance(p["literal"], bool)
                    and p["key"] and p["text"] and _text(p["key"], KEY_MAX) and _text(p["text"], KEY_MAX)):
                return "a part has a key and a text - texts - and literal, true or false"
    elif check.parts is not None:
        return f"parts are for crowd, not for {kind.REDUCTION}"
    return None


def validated(kind: Kind, check, step: Step | None = None) -> Check:
    """The check as the core takes it: itself, or - where it breaks a rule - an internal one, which is
    never the student's (the design's 6.3)."""
    return check if fault(kind, check, step) is None else Check("internal")


STORED = {"code": "text"}                   # an input's entry as the core keeps it: this field, else the input's name


def kept(kind: Kind, entry) -> dict:
    """What a kind's normalize gave, as the core keeps it (Entry.stored) and sends it to the windows: one
    field, the kind's input's, and JSON without NaN or infinity - else ValueError, which is never the
    student's (server/worker.py: the input is unchecked; the kit: a fault)."""
    if not isinstance(entry, Entry):
        raise ValueError(f"{type(entry).__name__}, not an Entry")
    try:
        stored = entry.stored()
        json.dumps(stored, allow_nan=False)
    except (ValueError, TypeError) as e:
        raise ValueError(f"an entry the core cannot keep - {e}") from None
    if set(stored) != {STORED.get(kind.INPUT, kind.INPUT)}:
        raise ValueError(f"{', '.join(stored)}, not the kind's input ({kind.INPUT})")
    return stored


# ------------------------------------------------------------------ what the core does around a kind
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
        check = kind.check(bare, step, kind.reference(step, text))
        if prepared.rows is None and check.status == "ok":
            prepared.rows = check.rows
        checks.append(check)
    return checks
