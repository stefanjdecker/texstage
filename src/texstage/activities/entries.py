# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The entries of one game (docs/architecture/activity-framework-design.md, 10.1 and 10.2; the plan of
F2, 4.3): what the students send in a step, and what the event loop decides about it without a kind -
no kind code runs here.

An entry's way, as far as this module takes it (the design's 10.1, steps 1 to 3):

1. The phone makes the entry's id. An id the step has already is the entry sent again - after a lost
   reply, after a restart of the server -: it gets the entry that is there, and nothing is counted
   twice. An id is unique in its step, through all its epochs.
2. What the core knows is checked, in this order: the step is open, the student is not blocked, not
   too fast (gap), not over the limit, the step not full, the input of the step's shape and not too
   long. The step is asked as it is after a tick (phases.py): who takes an entry ticks first, so that
   a step whose time is up is closed before the entry is looked at.
3. The entry is kept - with counts=latest in place of the student's earlier ones, which enter() gives
   too - and handed to the writer (store.py), which says when it is written: then it is acknowledged.

What follows - the kind's normalize in a worker, the check, the groups - is the checks' (package 4)
and the reductions' (package 5); an entry's norm is "" until then. What is kept is the input as it was
sent, of the right shape and size: what the kind's normalize makes of it, or that it refuses it, is
the check's to say.

The limit: with counts=latest every entry a student sent counts against it. With counts=all those
count that are in or that the lecturer hid - hiding gives no place back -, and one taken back gives
its place back; so that nobody fills a step by sending and taking back, a student sends at most
TAKEN_BACK times the limit in all. What a student has in, or had hidden, is not taken a second time.

In memory, per step: every entry by its id, and of the step's epoch the entries by student, the
students who have one in, and the counts - what a phone's view and the panel read, so that none goes
through all entries (the design's 10.2). A reset gives the step a new epoch: the earlier entries stay,
stored and by their ids, and no longer count.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import NamedTuple

from texstage.activities.phases import ONE, Refused
from texstage.activities.store import EntryRow, StepRow
from texstage.checks.cleaning import TEXT_MAX

__all__ = ["Entered", "Entries", "Rules", "STATES"]

STATES = ("in", "replaced", "withdrawn", "hidden")
ID = re.compile(r"[A-Za-z0-9_-]{8,40}")      # an entry's id, as a phone makes it
PER_STEP = 10_000                    # a step's entries in one epoch (the plan of F2, 4.3)
TAKEN_BACK = 3                       # counts=all: a student sends at most this many times the limit in all
GAP_S = {"fields": 2}                # seconds between a student's entries, by input; else 5 (as F1 had them)
GAP_ELSE_S = 5
GAP_MAX_S = 3600
LIMIT_MAX = 50                       # a student's entries, at most (kind.py)
FIELDS_MAX = 8


@dataclass(frozen=True)
class Rules:
    """A step's rules for its entries (the design's 8.1): the input's shape, how many each student may
    send (limit), how far apart (gap_ms), and whether a student's latest entry replaces the earlier
    ones (counts=latest: queries) or all count (counts=all: triples)."""
    input: str = "code"              # one of the core's inputs (kind.py: INPUTS)
    limit: int = 5
    gap_ms: int = GAP_ELSE_S * 1000
    counts: str = "latest"
    fields: int = 0                  # the input fields: how many

    @classmethod
    def of(cls, item: dict, kind) -> Rules:
        """A step's rules from its item (deck.json) and its kind: the deck's limit=, gap= (seconds) and
        counts=, else the kind's limit, the input's gap, and all for fields, the latest for the rest."""
        input = kind.INPUT
        limit, gap = item.get("limit", kind.LIMIT), item.get("gap", GAP_S.get(input, GAP_ELSE_S))
        counts = item.get("counts", "all" if input == "fields" else "latest")
        fields = item.get("fields") if input == "fields" else ()
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= LIMIT_MAX:
            raise ValueError(f"limit: 1 to {LIMIT_MAX}, not {limit!r}")
        if isinstance(gap, bool) or not isinstance(gap, (int, float)) or not 0 <= gap <= GAP_MAX_S:
            raise ValueError(f"gap: 0 to {GAP_MAX_S} seconds, not {gap!r}")
        if counts not in ("latest", "all"):
            raise ValueError(f"counts: latest or all, not {counts!r}")
        if input == "fields" and (not isinstance(fields, (list, tuple)) or not 1 <= len(fields) <= FIELDS_MAX):
            raise ValueError(f"fields: 1 to {FIELDS_MAX} of them")
        return cls(input, limit, round(gap * 1000), counts, len(fields))


class Entered(NamedTuple):
    """What enter() gives: the entry, whether it is new - not one sent again -, and the student's
    earlier entries it replaced (counts=latest), which leave their groups and the checks' queue."""
    entry: EntryRow
    new: bool
    replaced: list[EntryRow]


@dataclass
class Held:
    """One step's entries in one game."""
    entries: dict[str, EntryRow] = field(default_factory=dict)          # of every epoch, in the order they came
    epoch: int = 0
    mine: dict[str, list[EntryRow]] = field(default_factory=dict)       # this epoch's: player -> theirs, in order
    ins: Counter = field(default_factory=Counter)                       # player -> how many of theirs are in
    last: dict[str, int] = field(default_factory=dict)                  # player -> when their last one came
    total: int = 0                                                      # this epoch's entries, in any state
    count: int = 0                                                      # ... of them in

    def turn(self, epoch: int) -> None:
        """Another epoch is the step's: what is counted and listed is that epoch's."""
        self.epoch = epoch
        self.mine, self.ins, self.last, self.total, self.count = {}, Counter(), {}, 0, 0
        for e in self.entries.values():
            if e.epoch == epoch:
                self._list(e)

    def add(self, e: EntryRow) -> None:
        self.entries[e.id] = e
        if e.epoch == self.epoch:
            self._list(e)

    def _list(self, e: EntryRow) -> None:
        self.mine.setdefault(e.player, []).append(e)
        self.last[e.player] = e.created                   # (in the order they came: the last one's)
        self.total += 1
        self._tally(e, 1)

    def change(self, e: EntryRow, state: str) -> None:
        if e.epoch == self.epoch:
            self._tally(e, -1)
        e.state = state
        if e.epoch == self.epoch:
            self._tally(e, 1)

    def _tally(self, e: EntryRow, n: int) -> None:
        if e.state == "in":
            self.count += n
            self.ins[e.player] += n
            if self.ins[e.player] <= 0:
                del self.ins[e.player]


def _text(v) -> bool:
    """A text a store, a worker and a phone take: no half of a surrogate pair."""
    if not isinstance(v, str):
        return False
    try:
        v.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def shaped(rules: Rules, sent: dict) -> dict:
    """What a phone sent, as the step's input stores it - {"text": ...} or {"fields": [...]} -, or
    Refused. Only the shape and the size, of what was sent as it was sent: cleaning it is the kind's
    normalize, in a worker."""
    if rules.input in ("code", "text"):
        text = sent.get("text") if isinstance(sent, dict) else None
        if not _text(text):
            raise Refused("text: a text")
        if not text.strip():
            raise Refused("type something first", "text")
        if len(text) > TEXT_MAX:
            raise Refused(f"at most {TEXT_MAX} characters", "too-long")
        return {"text": text}
    if rules.input == "fields":
        fields = sent.get("fields") if isinstance(sent, dict) else None
        if not isinstance(fields, list) or len(fields) != rules.fields or not all(_text(f) for f in fields):
            raise Refused(f"fields: {rules.fields} texts")
        if not all(f.strip() for f in fields):
            raise Refused("fill in every field", "field")
        if sum(len(f) for f in fields) > TEXT_MAX:
            raise Refused(f"at most {TEXT_MAX} characters", "too-long")
        return {"fields": list(fields)}
    raise Refused(f"the input {rules.input} comes with texstage's own kinds")       # (package 9)


def _closed(st: StepRow) -> Refused:
    return Refused("this step is paused", "paused") if st.phase == "paused" else Refused("this step is closed", "closed")


class Entries:
    """One game's entries, by step."""

    def __init__(self, session: str, save: Callable[..., None] | None = None):
        self.session = session
        self.save = save or (lambda *rows: None)
        self.held: dict[tuple[str, str], Held] = {}

    def load(self, rows: Iterable[EntryRow]) -> None:
        """The entries as the tables have them, in the order they came - when the server starts
        again. One that is there already is not taken twice."""
        for e in rows:
            if e.session == self.session and e.id not in self._held(e.activity, e.step).entries:
                self._held(e.activity, e.step).add(e)

    def _held(self, activity: str, step: str = ONE) -> Held:
        return self.held.setdefault((activity, step), Held())

    def _of(self, st: StepRow) -> Held:
        held = self._held(st.activity, st.step)
        if held.epoch != st.epoch:
            held.turn(st.epoch)
        return held

    # -------------------------------------------------------------- reading
    def get(self, activity: str, step: str, entry: str) -> EntryRow | None:
        held = self.held.get((activity, step)) if isinstance(activity, str) and isinstance(step, str) else None
        return held.entries.get(entry) if held is not None and isinstance(entry, str) else None

    def mine(self, st: StepRow, player: str) -> list[EntryRow]:
        """A student's entries of the step's epoch, in the order they came - the phone's own list."""
        return list(self._of(st).mine.get(player, ()))

    def counts(self, st: StepRow) -> dict[str, int]:
        """Of the step's epoch: the entries that are in, and the students who have one in."""
        held = self._of(st)
        return {"entries": held.count, "students": len(held.ins)}

    # -------------------------------------------------------------- from the phones
    def enter(self, st: StepRow, rules: Rules, player: str, entry, sent: dict, *, now: int,
              blocked: bool = False) -> Entered:
        """A phone's entry, in a step as it is after a tick. An id the step has is the entry sent
        again - the one that is there, whatever the step's phase is now. Refused, with the phone's
        code: closed, paused, blocked, too-fast, too-many, full, duplicate, text, field, too-long."""
        if not isinstance(player, str) or not player:
            raise Refused("no such student")
        if not isinstance(entry, str) or not ID.fullmatch(entry):
            raise Refused("entry: an id of 8 to 40 letters, digits, - and _")
        held = self._of(st)
        known = held.entries.get(entry)
        if known is not None:
            if known.player != player:                    # (a phone's id met another's: never whose)
                raise Refused("entry: this id is taken")
            return Entered(known, False, [])
        if st.phase != "open":
            raise _closed(st)
        if blocked:
            raise Refused("the lecturer has closed entries for you", "blocked")
        last = held.last.get(player)
        if last is not None and 0 <= now - last < rules.gap_ms:          # (a clock set back: no gap is asked)
            raise Refused(f"one every {rules.gap_ms / 1000:g} seconds", "too-fast")
        theirs = held.mine.get(player, ())
        if rules.counts == "latest":
            over = len(theirs) >= rules.limit
        else:
            standing = sum(1 for old in theirs if old.state in ("in", "hidden"))
            over = standing >= rules.limit or len(theirs) >= rules.limit * TAKEN_BACK
        if over:
            raise Refused(f"at most {rules.limit} from each of you", "too-many")
        if held.total >= PER_STEP:
            raise Refused("this step has had enough entries", "full")
        input = shaped(rules, sent)
        replaced = []
        if rules.counts == "latest":
            for old in theirs:
                if old.state == "in":
                    held.change(old, "replaced")
                    replaced.append(old)
        elif any(old.state in ("in", "hidden") and old.input == input for old in theirs):
            raise Refused("you have sent this one already", "duplicate")
        e = EntryRow(entry, self.session, st.activity, st.step, st.epoch, player, now, input)
        held.add(e)
        self.save(*replaced, e)
        return Entered(e, True, replaced)

    def withdraw(self, st: StepRow, player: str, entry) -> EntryRow:
        """A student takes an entry of theirs back, while the step is open. Again: nothing changes."""
        held = self._of(st)
        e = held.entries.get(entry) if isinstance(entry, str) else None
        if e is None or e.player != player or e.epoch != st.epoch:
            raise Refused("no such entry of yours")
        if e.state == "withdrawn":
            return e
        if st.phase != "open":
            raise _closed(st)
        if e.state != "in":
            raise Refused("no such entry of yours")
        held.change(e, "withdrawn")
        self.save(e)
        return e

    # -------------------------------------------------------------- from the lecturer (moderation: package 5)
    def hide(self, e: EntryRow) -> bool:
        """The lecturer hides an entry that is in. Whether it changed."""
        if e.state != "in":
            return False
        self._held(e.activity, e.step).change(e, "hidden")
        self.save(e)
        return True

    def show(self, e: EntryRow, rules: Rules) -> bool:
        """The lecturer shows a hidden entry again: it is in - or, where the latest counts and the
        student has sent another since that is in, replaced by it. Whether it changed."""
        if e.state != "hidden":
            return False
        held = self._held(e.activity, e.step)
        theirs = held.mine.get(e.player, []) if e.epoch == held.epoch else []
        later = theirs[next((i for i, o in enumerate(theirs) if o is e), len(theirs)) + 1:]
        latest = rules.counts == "latest" and any(o.state == "in" for o in later)
        held.change(e, "replaced" if latest else "in")
        self.save(e)
        return True
