# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""One game's activities: the core's parts as one (docs/architecture/activity-framework-plan-f2.md, 4.3,
package 6) - the steps and their phases, the entries, their checks, what they are reduced to, the
pictures, the lecturer's acts. The parts know nothing of each other's callers; here whoever changes an
entry tells the reductions (touch), whoever moves a step the pictures (moved), and every job a part asks
for goes to whoever runs it - the type hands them to the pool (server/activities.py).

    play = Play(session, save=writer.put, ask=jobs.extend)
    play.load(steps, entries, checks, details, acts, now=now)       # a restart, in this order
    play.again()                                                    # ... and what was unchecked is asked for
    part = Part.of("kant", item, keys)                              # an activity of the deck: its kind, its setup
    play.move("open", "kant", now=now)
    got = play.enter(part, player, "entry-0001", {"text": "SELECT 1"}, now=now)
    play.normalized("kant", "main", raw, {"input": {...}}, now=now)     # the pool's answers, as they come
    play.checked("kant", "main", norm, outcome, now=now)
    play.picture(part, "stage"); play.step_part(part); play.mine(part, player)

Nothing here runs a kind's code, reads a clock or writes a file: the server's event loop calls it.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from texstage.activities import registry
from texstage.activities.checks import Checks
from texstage.activities.entries import Entered, Entries
from texstage.activities.kind import COMPARED, Kind
from texstage.activities.moderation import Done, Moderation
from texstage.activities.phases import Phases, Refused
from texstage.activities.reduce import Reduced, Setup
from texstage.activities.store import ONE, CheckRow, DetailRow, EntryRow, ModerationRow, StepRow
from texstage.activities.views import Pictures

FEEDBACK = ("none", "status", "verdict", "full")         # what a phone learns before the reveal (the design's 5.3)
MOVES = ("open", "close", "pause", "resume", "reveal", "reset", "time")
SUGGEST_MAX = 50                    # the words a phone offers for a field: the deck's, then what is drawn
F1_INPUTS = {"tuple": "triples"}    # an item of a deck built before kinds were named: its input, its engine
PUBLIC = ("prompt", "fields", "suggest", "tokens", "engine")      # of an item: what a phone's screen is made with


def kind_of(item: dict) -> Kind:
    """An item's kind: the one it names - or, for a deck built before kinds were named (the plan of F2,
    4.4: package 7 names them), the one of its input and engine. LookupError: none is installed."""
    name = item.get("kind") or F1_INPUTS.get(item.get("input"))
    if name is None and item.get("input") == "code":
        for found in registry.kinds().values():
            if getattr(found, "ENGINE", None) == item.get("engine"):
                return found
    if not isinstance(name, str):
        raise registry.Missing(f"no kind for an item of input={item.get('input')!r}, engine={item.get('engine')!r}")
    return registry.kind(name)


@dataclass(frozen=True)
class Part:
    """What a game reads of one activity of its deck: the item (deck.json), the keys (keys.json), its
    kind, and what the core makes of them."""
    activity: str
    item: dict
    keys: dict
    kind: Kind
    setup: Setup
    feedback: str = "status"

    @classmethod
    def of(cls, activity: str, item: dict, keys: dict | None = None, kind: Kind | None = None) -> Part:
        kind = kind or kind_of(item)
        feedback = item.get("feedback", "status")
        if feedback not in FEEDBACK:
            raise ValueError(f"feedback: one of {', '.join(FEEDBACK)}, not {feedback!r}")
        return cls(activity, item, keys or {}, kind, Setup.of(item, kind, keys), feedback)


class Play:
    """One game's core. save: rows to write (the writer's put); ask: jobs for the pool (checks.py:
    Normalize, Run, Leave), as a list - both are called as things happen, never later."""

    def __init__(self, session: str, save: Callable[..., None] | None = None,
                 ask: Callable[[list], None] | None = None):
        self.session = session
        self.ask = ask or (lambda jobs: None)
        self.phases = Phases(session, save)
        self.entries = Entries(session, save)
        self.checks = Checks(session, save)
        self.reduced = Reduced(session, self.entries, self.checks)
        self.moderation = Moderation(session, self.entries, self.checks, self.reduced, save)
        self.pictures = Pictures(session, self.entries, self.checks, self.reduced, self.moderation)
        self._unchecked: list[EntryRow] = []              # after a load: the entries to ask for again

    def _ask(self, jobs: Iterable) -> None:
        jobs = list(jobs)
        if jobs:
            self.ask(jobs)

    # -------------------------------------------------------------- a restart
    def load(self, steps: Iterable[StepRow], entries: Iterable[EntryRow], checks: Iterable[CheckRow],
             details: Iterable[DetailRow], acts: Iterable[ModerationRow], *, now: int,
             round_on: bool = False) -> list[StepRow]:
        """The game as the tables have it, in the order the parts need: the steps, the entries, the
        checks, the acts - a block is for its entry's student -, then the reductions. The steps that
        changed as the server was away (phases.py: load). The references are not here: a restarted
        server checks them again (refer), and what is unchecked is asked for with again()."""
        entries = [e for e in entries if e.session == self.session]
        rows = self.phases.load(steps, now, round_on)
        self.entries.load(entries)
        self.checks.load(checks, details, entries)
        self.moderation.load(acts)
        self.reduced.load(self.phases.steps.values(), entries)
        self.pictures.moved(*self.phases.steps.values())
        self._unchecked = entries
        return rows

    def again(self) -> None:
        """After a load, once the pool takes jobs: the entries that still want a check are asked for."""
        entries, self._unchecked = self._unchecked, []
        self._ask(self.checks.again(entries))

    # -------------------------------------------------------------- the steps
    def step(self, activity: str, step: str = ONE) -> StepRow:
        """The step - as it is; one that never moved is ready."""
        return self.phases.step(activity, step)

    def tick(self, now: int) -> list[StepRow]:
        """The server's tick, a few times a second and before an entry is taken: the steps it changed."""
        rows = self.phases.tick(now)
        self.pictures.moved(*rows)
        return rows

    def move(self, name: str, *args, now: int, **more) -> list[StepRow]:
        """A move of the phases - open, close, pause, resume, reveal, reset, time; round, slide - and the
        steps it changed. A refusal has changed some all the same (the time ran out as the lecturer
        pressed Pause): the pictures are told those too, and the refusal has them (changed)."""
        try:
            rows = getattr(self.phases, name)(*args, now=now, **more)
        except Refused as e:
            self.pictures.moved(*e.changed)
            raise
        self.pictures.moved(*rows)
        return rows

    # -------------------------------------------------------------- entries
    def blocked(self, player: str) -> bool:
        return player in self.moderation.blocked

    def enter(self, part: Part, player: str, entry, sent: dict, *, now: int, step: str = ONE,
              blocked: bool = False) -> Entered:
        """A phone's entry, after a tick. blocked: the engine's word of the player (muted); the acts'
        is asked here. An entry sent again changes nothing and asks for nothing."""
        self.tick(now)
        st = self.step(part.activity, step)
        got = self.entries.enter(st, part.setup.rules, player, entry, sent, now=now,
                                 blocked=blocked or self.blocked(player))
        if got.new:
            jobs = [job for old in got.replaced for job in self.checks.left(old)]
            jobs += self.checks.entered(got.entry)[0]
            self.reduced.touch(st, got.entry, *got.replaced)
            self._ask(jobs)
        return got

    def withdraw(self, part: Part, player: str, entry, *, now: int, step: str = ONE) -> EntryRow:
        self.tick(now)
        st = self.step(part.activity, step)
        e = self.entries.withdraw(st, player, entry)
        jobs = self.checks.left(e)
        self.reduced.touch(st, e)
        self._ask(jobs)
        return e

    # -------------------------------------------------------------- what the pool answers
    def _touch(self, activity: str, step: str, entries: list[EntryRow]) -> list[EntryRow]:
        st = self.phases.get(activity, step)
        if st is not None and entries:
            self.reduced.touch(st, *entries)
        return entries

    def normalized(self, activity: str, step: str, raw: str, answer: dict, *, now: int) -> list[EntryRow]:
        """The normalizing process's answer for an input (pool.normalize): {"input": ...}, {"refused":
        the phone's code} - or anything else: it could not be normalized, which is never the student's.
        The entries it concerns, whose phones learn it."""
        if isinstance(answer, dict) and isinstance(answer.get("input"), dict):
            jobs, entries = self.checks.normalized(activity, step, raw, answer["input"], now=now)
        elif isinstance(answer, dict) and isinstance(answer.get("refused"), str):
            jobs, entries = self.checks.normalized(activity, step, raw, refused=answer["refused"], now=now)
        else:
            jobs, entries = [], self.checks.unnormalized(activity, step, raw)
        self._touch(activity, step, entries)
        self._ask(jobs)
        return entries

    def checked(self, activity: str, step: str, norm: str, outcome: dict, *, now: int) -> list[EntryRow]:
        """A check's outcome from the pool. The entries that waited for it, whose phones learn it."""
        return self._touch(activity, step, self.checks.checked(activity, step, norm, outcome, now=now))

    def refer(self, activity: str, outcomes: Iterable[dict | None], step: str = ONE) -> None:
        """The pool's outcomes of the step's references: without them no check has a verdict."""
        self.reduced.refer(activity, step, outcomes)

    # -------------------------------------------------------------- the lecturer's acts
    def _done(self, st: StepRow, done: Done) -> Done:
        if done.entries:
            self.reduced.touch(st, *done.entries)
        self._ask(done.jobs)
        return done

    def act(self, part: Part, act: str, *, now: int, step: str = ONE, **what) -> Done:
        st = self.step(part.activity, step)
        return self._done(st, self.moderation.act(st, part.setup, act, now=now, **what))

    def undo(self, part: Part, n: int | None = None, *, now: int, step: str = ONE) -> Done:
        st = self.step(part.activity, step)
        return self._done(st, self.moderation.undo(st, part.setup, n, now=now))

    # -------------------------------------------------------------- what the windows get
    def picture(self, part: Part, window: str = "display", step: str = ONE) -> dict:
        return self.pictures.picture(self.step(part.activity, step), part.setup, window)

    def told(self, activity: str, now: int, step: str = ONE) -> dict | None:
        """A step's new version for the windows, at most four times a second (views.py: told)."""
        st = self.phases.get(activity, step)
        return self.pictures.told(st, now) if st is not None else None

    def layout(self, part: Part, at, step: str = ONE) -> bool:
        return self.pictures.layout(self.step(part.activity, step), part.setup, at)

    # -------------------------------------------------------------- what the phones get
    def step_part(self, part: Part, step: str = ONE) -> dict:
        """The step's own part of a phone's state: the same for every phone of the game, so that it is
        serialized once (the design's 10.4). What a field offers is the deck's words and then what the
        projector draws - a student takes up a term another wrote."""
        st = self.step(part.activity, step)
        rules = part.setup.rules
        out = {"activity": st.activity, "step": st.step, "epoch": st.epoch, "phase": st.phase,
               "kind": part.kind.NAME, "input": rules.input, "limit": rules.limit, "counts": rules.counts,
               "feedback": part.feedback, "time": st.time_left}
        for name in PUBLIC:
            if part.item.get(name) is not None:
                out[name] = part.item[name]
        if part.setup.reduction == "crowd":
            drawn = [n["label"] for n in self.picture(part, "display", step).get("nodes", ())]
            out["suggest"] = list(dict.fromkeys([*part.item.get("suggest", ()), *drawn]))[:SUGGEST_MAX]
        return out

    def mine(self, part: Part, player: str, step: str = ONE) -> dict:
        """A phone's own part: its student's entries of the step's epoch, the latest first, each with
        what feedback= allows of its check - and after the reveal its verdict. An entry the lecturer
        hid is the student's as before: no phone is told."""
        st = self.step(part.activity, step)
        theirs = [e for e in self.entries.mine(st, player) if e.state != "withdrawn"]
        counted = theirs if part.setup.rules.counts == "latest" else [e for e in theirs if e.state in ("in", "hidden")]
        return {"activity": st.activity, "step": st.step, "epoch": st.epoch, "used": len(counted),
                "blocked": self.blocked(player), "entries": [self._shown(part, st, e) for e in reversed(theirs)]}

    def _shown(self, part: Part, st: StepRow, e: EntryRow) -> dict:
        out = {"id": e.id, "input": e.input, "state": "in" if e.state == "hidden" else e.state}
        revealed = st.phase == "revealed"
        level = FEEDBACK.index(part.feedback)
        if level == 0 and not revealed:
            return out | {"check": "received"}
        check = self.checks.of(e)
        if check is None or check.status == "internal":   # (why the server could not: not the phone's)
            return out | {"check": "unchecked" if check is not None else self.checks.state(e)}
        out |= {"check": "checked", "status": check.status}
        if check.message is not None:
            out["message"] = check.message
        if check.at is not None:
            out["at"] = check.at
        if level >= 2 or revealed:
            verdict = self.reduced.verdict(st.activity, st.step, check)
            if verdict is not None:
                out["verdict"] = verdict
        if level >= 3 and check.key is not None:
            compared = (self.checks.detail(st.activity, st.step, check.key) or {}).get(COMPARED)
            if compared is not None:
                out["compared"] = compared
        return out
