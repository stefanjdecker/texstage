# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The checks of one game (docs/architecture/activity-framework-design.md, 6.3, 10.1 and 10.2; the plan
of F2, 4.3): one check per step and distinct normalized input, and the entries that wait for it. The
event loop's part - no kind code runs here: this module says what is to be done (its jobs), the pool's
workers do it (server/pool.py), and what they answer is handed back.

An entry's way from where entries.py leaves it (the design's 10.1, steps 4 and 5):

4. A text the step has not seen goes to the pool's process for normalizing (Normalize: the kind's
   normalize, quick); entries with the same text wait for that one. Only a normalized form the step has
   not seen is queued for a check, once (Run); entries with the same form wait for that one check. A
   check that no entry waits for any more - its entry replaced or taken back - leaves the queue (Leave).
5. The check comes back: it is stored, with its detail if its group has none yet, and the entries that
   waited have it.

What normalize refuses - too long once cleaned, nothing but spaces a phone cannot see - is a check of
its own: `invalid`, with the refusal's code as its message, under the hash of the input as it was sent.
It is kept in memory and not stored: asking the kind again costs nothing, and a restart does.

What could not be normalized at all - its kind is not installed, the process ended - is not the
student's (unnormalized): the entries count as unchecked, and the same text sent again, or the next
start of the server, asks again.

An `internal` check is never the text's doing unless the pool set the text aside (the design's 6.3):
set aside, it is stored and final; else nothing is stored, the entries that waited count as unchecked,
and the same text sent again - or the next start of the server - has it checked again.

A step takes FORMS_MAX distinct forms at a time - those whose check an entry of its epoch has (in or
hidden), that are being checked, or failed and are still waited for; what normalize refused is none.
Beyond, a new form waits unchecked, and counts() says the step is full (the plan of F2, 4.3); it is asked
for as soon as there is room - an entry replaced or taken back lets its form go, a check that comes back
makes room (due()). A reset keeps the checks - the same text has the same result -, and the new epoch's
entries count its forms anew: a number step whose students all change their estimate fills no more than
one whose students do not.

After a restart (load, again): the checks and details are the tables'; an entry that has none goes to
normalize again - a normalized form is stored with its check, not before - and is checked as a new one
is.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from texstage.activities.store import CheckRow, DetailRow, EntryRow, StepRow, norm

__all__ = ["Checks", "Leave", "Normalize", "Run"]

FORMS_MAX = 2_000                    # a step's distinct normalized forms (the plan of F2, 4.3)
WAITS = ("in", "hidden")             # the states of an entry that still wants its check: what is hidden may be shown


@dataclass(frozen=True)
class Normalize:
    """For the pool's normalizing process: the input as it was sent; raw is its hash, which the answer names."""
    activity: str
    step: str
    raw: str
    input: dict = field(hash=False, compare=False)


@dataclass(frozen=True)
class Run:
    """For the pool: one distinct normalized input to check. owner: a student who waits for it - the pool
    takes the students in turns."""
    activity: str
    step: str
    norm: str
    input: dict = field(hash=False, compare=False)
    owner: str = ""


@dataclass(frozen=True)
class Leave:
    """For the pool: this game waits for this check no longer; if nobody else does and it has not begun,
    it need not (pool.withdraw)."""
    activity: str
    step: str
    norm: str


@dataclass
class _Step:
    """One step's checks in one game."""
    checks: dict[str, CheckRow] = field(default_factory=dict)             # by norm: the final ones
    refused: dict[str, CheckRow] = field(default_factory=dict)            # by an input's hash: what normalize refused
    details: dict[str, DetailRow] = field(default_factory=dict)           # by key
    raws: dict[str, str | None] = field(default_factory=dict)             # an input's hash -> its norm; None: asked
    stuck: set[str] = field(default_factory=set)                          # inputs that could not be normalized
    forms: dict[str, dict] = field(default_factory=dict)                  # norm -> the normalized input, until checked
    pending: set[str] = field(default_factory=set)                        # norms whose check is asked for
    failed: set[str] = field(default_factory=set)                         # ... came back internal, not set aside
    held: dict[str, None] = field(default_factory=dict)                   # ... wait for room, in the order they came
    unformed: dict[str, dict[str, EntryRow]] = field(default_factory=dict)    # raw -> the entries that wait for it
    asking: dict[str, dict[str, EntryRow]] = field(default_factory=dict)      # norm -> the entries that wait for it
    having: dict[str, dict[str, int]] = field(default_factory=dict)           # norm -> the entries that have its
    holders: Counter = field(default_factory=Counter)                         # check: id -> epoch; per (norm, epoch)
    held_in: Counter = field(default_factory=Counter)                         # epoch -> the forms its entries have

    def count(self, epoch: int) -> int:
        """The step's forms in an epoch: those its entries have the check of, those being checked, those
        that failed and are waited for."""
        return self.held_in[epoch] + len(self.pending) + len(self.failed)

    def have(self, form: str, e: EntryRow) -> None:
        """An entry that is in or hidden has the form's check: the form counts in the entry's epoch."""
        if e.state not in WAITS or e.id in self.having.setdefault(form, {}):
            return
        self.having[form][e.id] = e.epoch
        self.holders[form, e.epoch] += 1
        if self.holders[form, e.epoch] == 1:
            self.held_in[e.epoch] += 1

    def let_go(self, e: EntryRow) -> bool:
        """An entry that left lets its form's check go - whether the form counts no more in its epoch."""
        epoch = self.having.get(e.norm, {}).pop(e.id, None) if e.norm else None
        if epoch is None:
            return False
        self.holders[e.norm, epoch] -= 1
        if self.holders[e.norm, epoch]:
            return False
        del self.holders[e.norm, epoch]
        self.held_in[epoch] -= 1
        return True


class Checks:
    """One game's checks, by step."""

    def __init__(self, session: str, save: Callable[..., None] | None = None):
        self.session = session
        self.save = save or (lambda *rows: None)
        self.steps: dict[tuple[str, str], _Step] = {}
        self.later: list = []                     # the jobs an answer made room for (checked): due() gives them

    def due(self) -> list:
        """The jobs an answer made room for since they were last asked for - forms that waited for room, which
        a check that came back (checked) or one that nobody waits for any more let in."""
        jobs, self.later = self.later, []
        return jobs

    def _step(self, activity: str, step: str) -> _Step:
        return self.steps.setdefault((activity, step), _Step())

    # -------------------------------------------------------------- a restart
    def load(self, checks: Iterable[CheckRow], details: Iterable[DetailRow], entries: Iterable[EntryRow] = ()) -> None:
        """The checks and details as the tables have them, and of the entries what they tell: an input
        whose entry has a check is a text the step knows."""
        for c in checks:
            if c.session == self.session:
                self._step(c.activity, c.step).checks[c.norm] = c
        for d in details:
            if d.session == self.session:
                self._step(d.activity, d.step).details[d.key] = d
        for e in entries:
            if e.session == self.session and e.norm and e.norm in self._step(e.activity, e.step).checks:
                self._step(e.activity, e.step).raws[norm(e.input)] = e.norm
                self._step(e.activity, e.step).have(e.norm, e)

    def again(self, entries: Iterable[EntryRow]) -> list:
        """After a restart: the entries that still want a check and have none are asked for again - those
        that waited, those whose check failed for the server's reasons, those normalize refused. The
        jobs."""
        jobs = []
        for e in entries:
            if e.session == self.session and e.state in WAITS and self.of(e) is None:
                jobs += self.entered(e)[0]
        return jobs

    # -------------------------------------------------------------- reading
    def of(self, e: EntryRow) -> CheckRow | None:
        """An entry's check, if it has one."""
        s = self.steps.get((e.activity, e.step))
        if s is None or not e.norm:
            return None
        return s.checks.get(e.norm) or s.refused.get(e.norm)

    def state(self, e: EntryRow) -> str:
        """checked; unchecked - its check failed for the server's reasons, it could not be normalized, or
        its step is full -; else waiting."""
        if self.of(e) is not None:
            return "checked"
        s = self.steps.get((e.activity, e.step))
        if s is None:
            return "waiting"
        if e.norm and (e.norm in s.failed or e.norm in s.held):
            return "unchecked"
        return "unchecked" if s.stuck and norm(e.input) in s.stuck else "waiting"

    def detail(self, activity: str, step: str, key: str) -> dict | None:
        s = self.steps.get((activity, step))
        d = s.details.get(key) if s is not None else None
        return d.detail if d is not None else None

    def counts(self, st: StepRow) -> dict:
        """For the panel, of the step's epoch and the entries that are in: how many wait for their check,
        how many could not be checked; the step's distinct forms, and whether it takes no more."""
        s = self.steps.get((st.activity, st.step)) or _Step()
        waiting = unchecked = 0
        for group in (*s.unformed.values(), *s.asking.values()):
            for e in group.values():
                if e.state == "in" and e.epoch == st.epoch:
                    if self.state(e) == "unchecked":
                        unchecked += 1
                    else:
                        waiting += 1
        forms = s.count(st.epoch)
        return {"waiting": waiting, "unchecked": unchecked, "forms": forms, "full": forms >= FORMS_MAX}

    # -------------------------------------------------------------- an entry comes, an entry goes
    def entered(self, e: EntryRow) -> tuple[list, CheckRow | None]:
        """A new entry (entries.py: enter). What is to be done for it - nothing, if its text is known or
        asked for already -, and its check, if the step has it."""
        s = self._step(e.activity, e.step)
        raw = norm(e.input)
        form = s.raws.get(raw, "")
        if form is None:                                  # being normalized: it waits with the others
            s.unformed.setdefault(raw, {})[e.id] = e
            return [], None
        if raw in s.refused:                              # what normalize refused: refused at once
            self._norm(e, raw)
            return [], s.refused[raw]
        if not form or (form not in s.checks and form not in s.forms):
            s.raws[raw] = None                            # a new text - or one whose form is gone (a restart)
            s.stuck.discard(raw)
            s.unformed.setdefault(raw, {})[e.id] = e
            return [Normalize(e.activity, e.step, raw, e.input)], None
        return self._formed(s, e, form), s.checks.get(form)

    def _norm(self, e: EntryRow, form: str) -> None:
        if e.norm != form:
            e.norm = form
            self.save(e)

    def _formed(self, s: _Step, e: EntryRow, form: str) -> list:
        """An entry whose normalized form is known: it has its check, or waits for it - asked for now, if
        nobody has."""
        self._norm(e, form)
        if form in s.checks:
            s.have(form, e)
            return []
        s.asking.setdefault(form, {})[e.id] = e
        if form in s.pending:
            return []
        if form in s.held:                                # it waits for room - which this epoch may have
            if s.count(e.epoch) >= FORMS_MAX:
                return []
            del s.held[form]
        elif form not in s.failed and s.count(e.epoch) >= FORMS_MAX:
            s.held[form] = None                           # the step is full: it waits, unchecked
            return []
        s.pending.add(form)
        s.failed.discard(form)
        return [Run(e.activity, e.step, form, s.forms[form], e.player)]

    def _room(self, s: _Step) -> list:
        """The forms that waited for room, in the order they came, as far as the epoch of the entries that wait
        for each (the latest) has room now - a form nobody waits for any more is no form of the step's, and an
        earlier epoch's that waited takes no room of a later one's."""
        jobs = []
        for form in list(s.held):
            waiting = s.asking.get(form)
            if not waiting:
                del s.held[form]
                continue
            if s.count(max(e.epoch for e in waiting.values())) >= FORMS_MAX:
                continue
            del s.held[form]
            first = next(iter(waiting.values()))
            s.pending.add(form)
            jobs.append(Run(first.activity, first.step, form, s.forms[form], first.player))
        return jobs

    def left(self, e: EntryRow) -> list:
        """An entry that wants no check any more - replaced, taken back. The jobs: its check leaves the
        queue, if nobody else of this game waits for it - and a form that waited for the room it
        leaves is asked for."""
        s = self.steps.get((e.activity, e.step))
        if s is None:
            return []
        freed = s.let_go(e)                               # (its form, if it had the check: one less of the epoch's)
        for raw in [r for r, group in s.unformed.items() if e.id in group]:
            del s.unformed[raw][e.id]                     # (the answer still tells the step its form)
            if not s.unformed[raw] and raw in s.stuck:
                del s.unformed[raw]
        form, jobs = e.norm, []
        if form and e.id in s.asking.get(form, {}):
            del s.asking[form][e.id]
            if not s.asking[form]:
                del s.asking[form]
                s.held.pop(form, None)
                s.failed.discard(form)                    # nobody waits for it: it is no form of the step's
                if form in s.pending:
                    s.pending.discard(form)
                    jobs.append(Leave(e.activity, e.step, form))
                freed = True
        if freed:
            jobs += self._room(s)
        return jobs

    # -------------------------------------------------------------- what the workers answer
    def normalized(self, activity: str, step: str, raw: str, input: dict | None = None, refused: str | None = None, *,
                   now: int = 0) -> tuple[list, list[EntryRow]]:
        """The normalizing process's answer for an input (raw: its hash): the normalized input - or the
        code the kind's normalize refused it with. The jobs that follow, and the entries that have their
        check now. (An answer that is neither: unnormalized.)"""
        if (input is None) == (refused is None):
            raise ValueError("normalized: the normalized input, or the code it was refused with")
        s = self._step(activity, step)
        entries = list(s.unformed.pop(raw, {}).values())
        s.stuck.discard(raw)
        if refused is not None:
            if raw not in s.refused:
                s.refused[raw] = CheckRow(self.session, activity, step, raw, "invalid",
                                          message={"code": refused, "args": {}}, created=now)
            s.raws[raw] = raw
            for e in entries:
                self._norm(e, raw)
            return [], entries
        form = norm(input)
        s.raws[raw] = form
        if form not in s.checks:
            s.forms.setdefault(form, input)
        jobs, checked = [], []
        for e in entries:
            if e.state in WAITS:
                jobs += self._formed(s, e, form)
            else:                                         # gone meanwhile: its form is kept all the same
                self._norm(e, form)
            if form in s.checks:
                checked.append(e)
        return jobs, checked

    def unnormalized(self, activity: str, step: str, raw: str) -> list[EntryRow]:
        """An input that could not be normalized (the pool's {"error": ...}) - never the student's: the
        entries that waited for it stay, unchecked, and are given; the same text sent again asks again."""
        s = self._step(activity, step)
        if s.raws.get(raw, "") is None:
            del s.raws[raw]
            s.stuck.add(raw)
        return list(s.unformed.get(raw, {}).values())

    def checked(self, activity: str, step: str, form: str, outcome: dict, *, now: int = 0) -> list[EntryRow]:
        """A check's outcome, as it leaves the worker (kind.py: Check.sent) and the pool (set_aside): it is
        stored, its detail too if its group has none, and the entries that waited have it - which are
        given. An internal one that is not set aside is not stored: the entries stay, unchecked. An
        answer for a form that has its check - it was asked for twice - changes nothing. What came back may
        make room for a form that waited (due())."""
        s = self._step(activity, step)
        s.pending.discard(form)
        try:
            return self._outcome(s, activity, step, form, outcome, now)
        finally:
            self.later += self._room(s)

    def _outcome(self, s: _Step, activity: str, step: str, form: str, outcome: dict, now: int) -> list[EntryRow]:
        status = outcome.get("status")
        if form in s.checks:
            return self._have(s, form)
        if status == "internal" and not outcome.get("set_aside"):
            if form in s.asking:                          # (nobody waits for it: it is no form of the step's)
                s.failed.add(form)
            return list(s.asking.get(form, {}).values())
        row = CheckRow(self.session, activity, step, form, status, key=outcome.get("key"), parts=outcome.get("parts"),
                       verdict=outcome.get("verdict"), credit=outcome.get("credit"), message=outcome.get("message"),
                       at=outcome.get("at"), aside=status == "internal", created=now, form=s.forms.get(form))
        s.checks[form] = row
        rows = [row]
        if row.key and outcome.get("detail") is not None and row.key not in s.details:
            s.details[row.key] = DetailRow(self.session, activity, step, row.key, outcome["detail"], now)
            rows.append(s.details[row.key])
        self.save(*rows)
        s.forms.pop(form, None)
        s.failed.discard(form)
        return self._have(s, form)

    @staticmethod
    def _have(s: _Step, form: str) -> list[EntryRow]:
        """The entries that waited for a form's check, which they have now."""
        entries = list(s.asking.pop(form, {}).values())
        for e in entries:
            s.have(form, e)
        return entries
