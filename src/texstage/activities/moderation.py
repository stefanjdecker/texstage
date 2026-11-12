# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The lecturer's acts on one game's pictures (docs/architecture/activity-framework-design.md, 10.2, 10.4
and 13; the plan of F2, 4.3): every act a row, so that it can be undone and a restarted server has it
again.

    hide      a group - of a crowd graph: a term, wherever it stands - is not on the projector; an entry
              is hidden (entries.py: it no longer counts, and gives its student no place back)
    approve   a crowd graph that reviews (review) shows a term
    merge     a crowd graph's term counts as another of its role; unmerge: no longer
    show      a group's detail is on the projector; no group: none is
    min       the students a crowd graph's triple needs
    block     the student of an entry sends no more, and what they have in the step is hidden

hide, approve and block are taken back with `off`. An act that changes nothing makes no row.

What holds is what the acts that are not undone say, in their order: undo marks an act, and everything
is read again without it - a term it merged is merged as the act before it said, an entry it hid is in
again unless another act that holds hides it, and one it showed is hidden again. An entry is as its
acts say, from what the first of them found: a row that shows an entry found it hidden, a block's row
has the entries it hid and those it found hidden. While a student is blocked, what they have in the
step stays hidden - no undo brings it back, and showing it is refused: unblock the student first. An
unblock is undone by blocking the student again, which is an act of its own (and hides what they sent
meanwhile); undone in its turn, things are as they were. An undo that would leave two terms merged into
each other is refused.

The acts on groups and terms stay through a reset, as the checks do - that two terms are one, or that a
word is not to be shown, is as true of the next epoch. The acts on entries are those entries': after a
reset they are neither listed nor undone, and no undo changes an entry of an earlier epoch. The group
whose detail is on the projector is its epoch's: after a reset none is. Who is blocked is the game's
(blocked): the server asks before it takes an entry (entries.py: enter) - and asks the player's own flag
too, which F1 set (`muted`): the move leaves that where it is.

The acts are loaded after the game's entries (load): a block is for its entry's student. No row names a
student: a block names an entry, and is for whoever sent it.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import NamedTuple

from texstage.activities.checks import Checks
from texstage.activities.entries import Entries
from texstage.activities.phases import Refused
from texstage.activities.reduce import ROLES, Mods, Reduced, Setup
from texstage.activities.store import MIN_MAX, EntryRow, ModerationRow, StepRow

__all__ = ["ACTS", "Done", "Moderation"]

ACTS = ("hide", "approve", "merge", "unmerge", "show", "min", "block")
ACTS_MAX = 5_000                     # a game's acts that hold
ROWS_MAX = 20_000                    # ... and its rows, the undone ones among them
ACTS_LISTED = 10                     # the panel's: the last ones, which it offers to undo


class Done(NamedTuple):
    """What an act did: its row - None: nothing changed -, the entries whose state changed, the jobs for
    the pool (an entry that is replaced as another is shown wants no check any more), and for a block
    the student whose phone learns it."""
    row: ModerationRow | None = None
    entries: Sequence[EntryRow] = ()
    jobs: Sequence = ()
    player: str | None = None


class _Cycle(Exception):
    """Two terms merged into each other."""


def _block(value) -> tuple[list, list]:
    """A block's row: the entries it hid, and those of the student it found hidden."""
    if isinstance(value, dict):
        return list(value.get("hid") or ()), list(value.get("had") or ())
    return list(value or ()) if isinstance(value, (list, tuple)) else [], []


class Moderation:
    """One game's acts."""

    def __init__(self, session: str, entries: Entries, checks: Checks, reduced: Reduced,
                 save: Callable[..., None] | None = None):
        self.session = session
        self.entries = entries
        self.checks = checks
        self.reduced = reduced
        self.save = save or (lambda *rows: None)
        self.rows: list[ModerationRow] = []               # in their order
        self.mods: dict[tuple[str, str], Mods] = {}
        self.blocked: set[str] = set()                    # the students who send no more
        self.skipped: set[int] = set()                    # merges that hold but lead back to their own term

    # -------------------------------------------------------------- what holds
    def load(self, rows: Iterable[ModerationRow]) -> None:
        """The acts as the table has them. The game's entries are loaded before: a block is for its
        entry's student, and one whose entry is not there is a ValueError - nobody would be blocked, and
        nothing would say so. The entries' states are the table's own."""
        self.rows = sorted((r for r in rows if r.session == self.session), key=lambda r: r.n)
        for r in self.rows:
            if r.act == "block" and not r.undone and self.entries.get(r.activity, r.step, r.entry) is None:
                self.rows = []
                raise ValueError(f"the act {r.n} blocks the student of the entry {r.entry}, which is not loaded: "
                                 "load a game's entries before its acts")
        self._read()

    def of(self, activity: str, step: str) -> Mods:
        """What the acts make of a step's picture."""
        return self.mods.setdefault((activity, step), Mods())

    def acts(self, activity: str, step: str, epoch: int | None = None, last: int = ACTS_LISTED) -> list[dict]:
        """A step's last acts that hold, the latest first - for the panel, which offers to undo them.
        epoch: the step's - the acts on entries of another are not listed."""
        out = []
        for r in reversed(self.rows):
            if len(out) >= last:
                break
            if (r.activity, r.step) != (activity, step) or r.undone or self._past(r, epoch):
                continue
            one = {"n": r.n, "act": r.act, "created": r.created}
            for name in ("target", "entry", "onto"):
                if getattr(r, name) is not None:
                    one[name] = getattr(r, name)
            if r.role:
                one["role"] = r.role
            if r.off:
                one["off"] = True
            if r.act == "min":
                one["value"] = r.value
            out.append(one)
        return out

    @staticmethod
    def _past(r: ModerationRow, epoch: int | None) -> bool:
        """Whether an act is on an entry of another epoch than this one: no longer the panel's."""
        return epoch is not None and r.act == "hide" and r.entry is not None and r.epoch != epoch

    def _read(self, strict: bool = False, skipped: frozenset = frozenset()) -> None:
        """Everything read again from the acts that hold. strict: a merge that leads back to its own term
        is a _Cycle - unless it was skipped before (skipped: a game moved from a file that had one)."""
        self.mods, self.blocked, self.skipped = {}, set(), set()
        for r in self.rows:
            if not r.undone:
                self._apply(r, strict, skipped)

    def _apply(self, r: ModerationRow, strict: bool = False, skipped: frozenset = frozenset()) -> None:
        mods = self.of(r.activity, r.step)
        if r.act == "hide" and r.entry is None:
            (mods.hidden.discard if r.off else mods.hidden.add)(r.target)
        elif r.act == "approve":
            (mods.approved.discard if r.off else mods.approved.add)(r.target)
        elif r.act == "merge":
            if self._cyclic(mods, r.role, r.target, r.onto):
                if strict and r.n not in skipped:
                    raise _Cycle(f"{r.onto} is merged into {r.target}")
                self.skipped.add(r.n)
                return
            mods.merges[(r.role, r.target)] = r.onto
        elif r.act == "unmerge":
            mods.merges.pop((r.role, r.target), None)
        elif r.act == "show":
            mods.shown, mods.shown_epoch = r.target, r.epoch
        elif r.act == "min":
            mods.min = r.value
        elif r.act == "block":
            e = self.entries.get(r.activity, r.step, r.entry)
            if e is not None:
                (self.blocked.discard if r.off else self.blocked.add)(e.player)

    @staticmethod
    def _cyclic(mods: Mods, role: str, term: str, onto: str) -> bool:
        """Whether merging term into onto would merge it into itself: onto is, in the end, term."""
        seen = set()
        while onto != term and (role, onto) in mods.merges and onto not in seen:
            seen.add(onto)
            onto = mods.merges[(role, onto)]
        return onto == term

    def _wanted(self, st: StepRow) -> dict[str, bool]:
        """Which entries of the step its acts say are hidden - of those an act is about. Each from what
        the first act about it found (a row is made only of what changed something: one that shows an
        entry found it hidden; a block's row has what it hid and what it found hidden), then as the acts
        that hold say, in their order; and what a blocked student has in the step's epoch is hidden."""
        key = (st.activity, st.step)
        state: dict[str, bool] = {}
        for r in self.rows:
            if (r.activity, r.step) != key:
                continue
            if r.act == "hide" and r.entry is not None:
                state.setdefault(r.entry, r.off)
                if not r.undone:
                    state[r.entry] = not r.off
            elif r.act == "block":
                hid, had = _block(r.value)
                for eid in had:
                    state.setdefault(eid, True)
                for eid in hid:
                    state.setdefault(eid, False)
                if not r.off and not r.undone:
                    for eid in (*hid, *had):
                        state[eid] = True
        for player in self.blocked:
            for e in self.entries.mine(st, player):
                state[e.id] = True
        return state

    # -------------------------------------------------------------- an act
    def act(self, st: StepRow, setup: Setup, act: str, *, target: str | None = None, role: str = "node",
            onto: str | None = None, entry: str | None = None, off: bool = False, value=None, now: int = 0) -> Done:
        """An act of the lecturer's on a step. Refused, with a code: an act, a group, a term or an entry
        that is none (invalid), a merge that would merge a term into itself (cycle), an act that is not
        for the step's reduction (reduction), showing an entry of a student who is blocked (blocked), more
        acts than a game takes (too-many)."""
        if not isinstance(act, str) or act not in ACTS:
            raise Refused(f"act: one of {', '.join(ACTS)}")
        if not isinstance(off, bool):
            raise Refused("off: true or false")
        if len(self.rows) >= ROWS_MAX or sum(1 for r in self.rows if not r.undone) >= ACTS_MAX:
            raise Refused(f"this game has had {ACTS_MAX} acts", "too-many")
        crowd = setup.reduction == "crowd"
        mods = self.of(st.activity, st.step)
        row = ModerationRow(self.session, self.rows[-1].n + 1 if self.rows else 1, st.activity, st.step, act,
                            st.epoch, created=now)
        changed: list[EntryRow] = []
        player = None
        if act == "hide" and entry is not None:
            if target is not None:
                raise Refused("hide: a group or an entry, not both")
            e = self._entry(st, entry)
            if off and e.state == "hidden" and e.player in self.blocked:
                raise Refused("its student is blocked: unblock the student first", "blocked")
            changed = self.entries.show(e, setup.rules) if off else [e] if self.entries.hide(e) else []
            if not changed:
                return Done()
            row.entry, row.off = e.id, off
        elif act in ("hide", "approve"):
            if act == "approve" and not crowd:
                raise Refused("approve is for a crowd graph that reviews", "reduction")
            known = self.reduced.term(st, target) or self._merged(mods, target) if crowd \
                else self.reduced.group(st, target, setup)
            kept = mods.hidden if act == "hide" else mods.approved
            if not isinstance(target, str) or not (known or target in kept):
                raise Refused("no such term" if crowd else "no such group")
            if (target in kept) != off:
                return Done()
            row.target, row.off = target, off
        elif act in ("merge", "unmerge"):
            if not crowd:
                raise Refused(f"{act} is for a crowd graph", "reduction")
            if not isinstance(role, str) or role not in ROLES:
                raise Refused(f"role: one of {', '.join(ROLES)}")
            if not self._term(st, mods, role, target):
                raise Refused("no such term")
            row.target, row.role = target, role
            if act == "unmerge":
                if (role, target) not in mods.merges:
                    return Done()
            else:
                if onto == target or not self._term(st, mods, role, onto):
                    raise Refused("merge into another term")
                if self._cyclic(mods, role, target, onto):
                    raise Refused(f"{onto} is merged into {target} already", "cycle")
                if mods.merges.get((role, target)) == onto:
                    return Done()
                row.onto = onto
        elif act == "show":
            if crowd:
                raise Refused("a crowd graph shows itself", "reduction")
            if target is not None and not self.reduced.group(st, target, counted=True):
                raise Refused("no such group")
            if (mods.shown if mods.shown_epoch == st.epoch else None) == target:
                return Done()
            row.target = target
        elif act == "min":
            if not crowd:
                raise Refused("min is for a crowd graph", "reduction")
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MIN_MAX:
                raise Refused(f"min: the students a triple needs, 1 to {MIN_MAX}")
            if value == (mods.min if mods.min is not None else setup.min):
                return Done()
            row.value = value
        else:                                             # block
            e = self._entry(st, entry, any_epoch=True)
            if (e.player in self.blocked) != off:
                return Done()
            row.entry, row.off, player = e.id, off, e.player
            if not off:                                   # what the student has in the step: hidden, and remembered
                theirs = self.entries.mine(st, e.player)
                had = [o.id for o in theirs if o.state == "hidden"]
                changed = [o for o in theirs if self.entries.hide(o)]
                row.value = {"hid": [o.id for o in changed], "had": had}
        self.rows.append(row)
        self._apply(row)
        self.save(row)
        self._told(st, changed)
        return Done(row, changed, self._gone(changed), player)

    def _entry(self, st: StepRow, entry, any_epoch: bool = False) -> EntryRow:
        e = self.entries.get(st.activity, st.step, entry)
        if e is None or (e.epoch != st.epoch and not any_epoch):
            raise Refused("no such entry")
        return e

    @staticmethod
    def _merged(mods: Mods, term) -> bool:
        return any(term in (source, onto) for (_, source), onto in mods.merges.items())

    def _term(self, st: StepRow, mods: Mods, role: str, term) -> bool:
        """Whether a term is one of the step's in this role: an entry has it, or it was merged."""
        return isinstance(term, str) and (self.reduced.term(st, term, role) or (role, term) in mods.merges)

    def _gone(self, entries: Sequence[EntryRow]) -> list:
        """The jobs for the entries that want no check any more: replaced, as another was shown."""
        return [job for e in entries if e.state == "replaced" for job in self.checks.left(e)]

    def _told(self, st: StepRow, entries: Sequence[EntryRow]) -> None:
        self.reduced.touch(st, *entries)
        self.reduced.bump(st.activity, st.step)

    # -------------------------------------------------------------- undo
    def undo(self, st: StepRow, setup: Setup, n: int | None = None, *, now: int = 0) -> Done:
        """An act of the step undone - n: its number; None: the last that holds. What holds is read again
        without it, and the entries of the step's epoch are as the acts that are left say. An act that is
        undone already, or none to undo: nothing changes. Refused: no such act - an act on an entry of an
        earlier epoch is none any more - (invalid); without it two terms would be merged into each other
        (cycle)."""
        mine = [r for r in self.rows if (r.activity, r.step) == (st.activity, st.step)]
        if n is None:
            row = next((r for r in reversed(mine) if not r.undone and not self._past(r, st.epoch)), None)
        else:
            row = next((r for r in mine if r.n == n), None) if isinstance(n, int) and not isinstance(n, bool) else None
            if row is None or self._past(row, st.epoch):
                raise Refused("no such act")
        if row is None or row.undone:
            return Done()
        if row.act == "block" and row.off:                # an unblock is undone by blocking again: a new act,
            return self.act(st, setup, "block", entry=row.entry, now=now)      # which hides what came meanwhile
        skipped = frozenset(self.skipped)
        row.undone = True
        try:
            self._read(strict=True, skipped=skipped)
        except _Cycle as e:
            row.undone = False
            self._read()
            raise Refused(f"this cannot be undone: without it {e}", "cycle") from None
        player = None
        if row.act == "block":
            e = self.entries.get(row.activity, row.step, row.entry)
            player = e.player if e is not None else None
        changed: list[EntryRow] = []
        for eid, hidden in self._wanted(st).items():
            e = self.entries.get(st.activity, st.step, eid)
            if e is None or e.epoch != st.epoch:
                continue
            if hidden and e.state == "in":
                if self.entries.hide(e):
                    changed.append(e)
            elif not hidden and e.state == "hidden":
                changed += [o for o in self.entries.show(e, setup.rules) if o not in changed]
        self.save(row)
        self._told(st, changed)
        return Done(row, changed, self._gone(changed), player)
