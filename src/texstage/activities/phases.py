# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The steps of one game and their phases (docs/architecture/activity-framework-design.md, 5.2; the
plan of F2, 4.3).

                      +------open-------+
                      v                 |
    ready --open--> open --close--> closed --reveal--> revealed
                    |  ^
               pause|  |resume
                    v  |
                  paused

- One step is open at a time: opening one closes the one that runs. While a quiz round runs, none is:
  the round pauses the open step, and its end resumes it - unless the lecturer paused it meanwhile -,
  and a step that is opened or resumed during a round waits, paused, for the round's end.
- A move gives the rows it changed. Repeated, it changes nothing - but for more time, which adds each
  time it is asked for. What cannot be is refused (Refused, with a code for the phone or the window) -
  opening a revealed step, pausing one that is closed. A refused move may have changed rows all the
  same - the step's time ran out as the lecturer pressed Pause -: the refusal has them (changed), and
  the windows and the phones are told as after any move.
- The lecturer's Open on a closed step goes on with what is there, with the time the lecturer gives
  it; the slides never reopen one. A revealed step stays revealed.
- A step's time counts while the server runs: every move and every tick (the server's, a few times a
  second) takes off what passed since the last one - and where more than SLEEP_MS passed, the server
  did not run (the laptop slept, its event loop stood still): the step is paused, not closed, and the
  lecturer resumes it. That holds for a round that opens or ends after such a gap too: its end resumes
  what a round paused, not what a sleep did. A server that starts again was away as well: its open
  steps with a time are paused. A step without a time stays open through both. A clock that is set
  back takes nothing off, and one set forward by more than SLEEP_MS is a sleep.
- Reset gives a step a new epoch: its entries stay stored, but no longer count (entries.py).
- The current step - the one the phones show - is the one that runs, else the one that was opened or
  revealed last (StepRow.seq); a reset leaves it the current one.

The times are the server's clock in ms, as everywhere in the server (`now`). A move saves the rows it
changed (save: the writer's put, store.py); a running time is saved every SAVE_MS, so that a server
that fails takes at most that much off a step's time when it starts again. An entry is asked of a
step as it is after a tick (entries.py): who takes entries ticks first.
"""
from __future__ import annotations

import functools
from collections.abc import Callable, Iterable

from texstage.activities.store import ONE, StepRow

__all__ = ["ONE", "PHASES", "Phases", "Refused"]

PHASES = ("ready", "open", "paused", "closed", "revealed")
RUNNING = ("open", "paused")
MARKS = ("open", "revealed")         # what a page of the slides says of a step it shows (the design's 8.2)
SLEEP_MS = 5_000                     # more than this between two ticks: the server did not run
SAVE_MS = 5_000                      # a running time is saved this often
TIME_MAX_MS = 4 * 60 * 60 * 1000     # a step's time, at most


class Refused(ValueError):
    """The core refuses a move or an entry: `code` is for the phone or the window, which says it in its
    language; the message is for people who read a log. changed: the steps the refused move changed
    all the same (the module's text)."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code
        self.changed: list[StepRow] = []


def _time(ms, what: str = "a step's time") -> int:
    if isinstance(ms, bool) or not isinstance(ms, int) or not 1000 <= ms <= TIME_MAX_MS:
        raise Refused(f"{what}: 1 second to {TIME_MAX_MS // 3_600_000} hours, in ms", "time")
    return ms


def _move(method):
    """A move: it gives the rows it changed, each once - its own and those of the moves it made on its
    way (the tick first) -, and a refusal has them too."""
    @functools.wraps(method)
    def moved(self, *args, **kwargs) -> list[StepRow]:
        if self._moving is not None:                      # inside another move: that one gives the rows
            method(self, *args, **kwargs)
            return []
        self._moving = {}
        try:
            method(self, *args, **kwargs)
        except Refused as e:
            e.changed = list(self._moving.values())
            raise
        finally:
            rows, self._moving = self._moving, None
        return list(rows.values())
    return moved


class Phases:
    """One game's steps."""

    def __init__(self, session: str, save: Callable[..., None] | None = None):
        self.session = session
        self.save = save or (lambda *rows: None)
        self.steps: dict[tuple[str, str], StepRow] = {}
        self.round_on = False                             # a quiz round runs
        self.seq = 0                                      # the highest turn given (StepRow.seq)
        self.counted: dict[tuple[str, str], int] = {}     # an open step with a time: when it was last counted
        self.saved: dict[tuple[str, str], int] = {}       # ... and when its time was last saved
        self._moving: dict[int, StepRow] | None = None    # the rows the move that runs has changed

    # -------------------------------------------------------------- reading
    @_move
    def load(self, rows: Iterable[StepRow], now: int, round_on: bool = False) -> list[StepRow]:
        """The steps as the tables have them, when the server starts again; round_on: a quiz round runs
        (the engine knows). The server was away: a step that was open with a time is paused (by
        sleep), as after a sleep - and one that is open though a round runs, by the round. The rows
        that changed."""
        self.round_on = bool(round_on)
        for row in rows:
            if row.session != self.session:
                continue
            self.steps[(row.activity, row.step)] = row
            self.seq = max(self.seq, row.seq)
            if row.phase == "open" and row.time_left is not None:
                self._set(row, now, phase="paused", paused_by="sleep")
            elif row.phase == "open" and self.round_on:
                self._set(row, now, phase="paused", paused_by="quiz")

    def get(self, activity: str, step: str = ONE) -> StepRow | None:
        return self.steps.get((activity, step)) if isinstance(activity, str) and isinstance(step, str) else None

    def step(self, activity: str, step: str = ONE) -> StepRow:
        """The step - ready, in epoch 0, if nothing moved it yet (and not stored until something does)."""
        if not isinstance(activity, str) or not isinstance(step, str) or not activity or not step:
            raise Refused("no such step")
        key = (activity, step)
        if key not in self.steps:
            self.steps[key] = StepRow(self.session, activity, step)
        return self.steps[key]

    def running(self) -> StepRow | None:
        """The step that is open or paused: at most one."""
        return next((st for st in self.steps.values() if st.phase in RUNNING), None)

    def current(self) -> StepRow | None:
        """The step the phones show: the one that runs, else the one opened or revealed last."""
        running = self.running()
        if running is not None or not self.seq:
            return running
        return next((st for st in self.steps.values() if st.seq == self.seq), None)

    # -------------------------------------------------------------- the time
    @_move
    def tick(self, now: int) -> list[StepRow]:
        """The open step's time, counted up to now: used up, the step closes; after a gap of more than
        SLEEP_MS it is paused instead (by sleep), and nothing is taken off. The rows that changed
        phase - a time that only ran on is saved every SAVE_MS and is not among them."""
        st = self.running()
        if st is None or st.phase != "open" or st.time_left is None:
            return
        key = (st.activity, st.step)
        passed = now - self.counted.get(key, now)
        self.counted[key] = now
        if passed > SLEEP_MS:
            self._set(st, now, phase="paused", paused_by="sleep")
        elif passed < 0:                                  # the clock set back: nothing counts, and the
            self.saved[key] = now                         # savings go on from the new time
        elif passed > 0:
            st.time_left = max(0, st.time_left - passed)
            if st.time_left == 0:
                self._set(st, now, phase="closed")
            elif now - self.saved.get(key, now) >= SAVE_MS:
                self.saved[key] = now
                self.save(st)

    def _set(self, st: StepRow, now: int, **fields) -> None:
        """A step's phase and what goes with it; saved, and among the rows the move gives. The clocks
        of its time start anew."""
        for name, value in fields.items():
            setattr(st, name, value)
        key = (st.activity, st.step)
        if st.phase == "open":
            self.counted[key] = self.saved[key] = now
        else:
            self.counted.pop(key, None)
            self.saved.pop(key, None)
        self._changed(st)

    def _changed(self, st: StepRow) -> None:
        self.save(st)
        if self._moving is not None:
            self._moving[id(st)] = st

    def _turn(self, st: StepRow) -> None:
        """The step is the current one from now on."""
        if st.seq != self.seq or not st.seq:
            self.seq += 1
            st.seq = self.seq

    def _go(self, st: StepRow, now: int, **fields) -> None:
        """A step starts or goes on: open - or, while a quiz round runs, paused until its end."""
        if self.round_on:
            self._set(st, now, phase="paused", paused_by="quiz", **fields)
        else:
            self._set(st, now, phase="open", paused_by="", **fields)

    # -------------------------------------------------------------- the moves
    @_move
    def open(self, activity: str, step: str = ONE, *, now: int, time_ms: int | None = None,
             reopen: bool = True) -> list[StepRow]:
        """Open a ready step, with its time (None: none) - or, reopen, a closed one again, with the time
        the lecturer gives it; the slides give reopen=False and leave a closed step closed. A paused
        step goes on, with the time it had or the one given. The step that ran until now closes."""
        if time_ms is not None:
            time_ms = _time(time_ms)
        st = self.step(activity, step)
        self.tick(now)
        if st.phase == "open" or (st.phase == "closed" and not reopen):
            return
        if st.phase == "revealed":
            raise Refused("a revealed step stays revealed - reset it to ask again", "revealed")
        if st.phase == "paused":
            if st.paused_by == "quiz" and self.round_on and time_ms in (None, st.time_left):
                return                                    # it waits for the round's end already
            self._go(st, now, **({} if time_ms is None else {"time_left": time_ms}))
            return
        for other in list(self.steps.values()):
            if other is not st and other.phase in RUNNING:
                self._set(other, now, phase="closed", paused_by="")
        self._turn(st)
        self._go(st, now, time_left=time_ms)

    @_move
    def close(self, activity: str, step: str = ONE, *, now: int) -> list[StepRow]:
        st = self.get(activity, step)
        self.tick(now)
        if st is not None and st.phase in RUNNING:
            self._set(st, now, phase="closed", paused_by="")

    @_move
    def pause(self, activity: str, step: str = ONE, *, now: int) -> list[StepRow]:
        """The lecturer pauses the open step: its time stops, the phones cannot send. A step a quiz round
        or a sleep paused is the lecturer's to resume from now on."""
        st = self.get(activity, step)
        self.tick(now)
        if st is None or st.phase not in RUNNING:
            raise Refused("this step is not open", "closed")
        if st.phase != "paused" or st.paused_by != "lecturer":
            self._set(st, now, phase="paused", paused_by="lecturer")

    @_move
    def resume(self, activity: str, step: str = ONE, *, now: int) -> list[StepRow]:
        """The lecturer resumes a paused step, whoever paused it - during a quiz round, for its end."""
        st = self.get(activity, step)
        self.tick(now)
        if st is None or st.phase not in RUNNING:
            raise Refused("this step is not paused", "closed")
        if st.phase == "paused" and not (st.paused_by == "quiz" and self.round_on):
            self._go(st, now)

    @_move
    def round(self, on: bool, *, now: int) -> list[StepRow]:
        """A quiz round opens (on) - the open step is paused - or ends: the step the round paused goes
        on; one the lecturer paused meanwhile stays paused."""
        self.tick(now)
        self.round_on = bool(on)
        st = self.running()
        if st is None:
            return
        if on and st.phase == "open":
            self._set(st, now, phase="paused", paused_by="quiz")
        elif not on and st.phase == "paused" and st.paused_by == "quiz":
            self._set(st, now, phase="open", paused_by="")

    @_move
    def reveal(self, activity: str, step: str = ONE, *, now: int) -> list[StepRow]:
        """Reveal a step, whatever its phase: it ends, and is the current one. (What the reveal shows
        and gives: the checks and the points, packages 4 and 5, F3.)"""
        st = self.step(activity, step)
        self.tick(now)
        if st.phase != "revealed":
            self._turn(st)
            self._set(st, now, phase="revealed", paused_by="", time_left=None)

    @_move
    def reset(self, activity: str, step: str = ONE, *, now: int) -> list[StepRow]:
        """A new epoch: the step is ready again, and what was sent no longer counts. A ready step has
        nothing to reset."""
        st = self.get(activity, step)
        self.tick(now)
        if st is not None and st.phase != "ready":
            self._set(st, now, phase="ready", epoch=st.epoch + 1, time_left=None, paused_by="")

    @_move
    def time(self, activity: str, step: str = ONE, *, now: int, add_ms: int | None = None,
             stop: bool = False) -> list[StepRow]:
        """More time for a step that runs - one without a time gets one; asked twice, it adds twice -,
        or, stop, no time any more: it stays open until it is closed."""
        if stop == (add_ms is not None):
            raise Refused("time: add (ms) or stop", "time")
        if add_ms is not None:
            add_ms = _time(add_ms, "more time")
        st = self.get(activity, step)
        self.tick(now)
        if st is None or st.phase not in RUNNING:
            raise Refused("this step is not open", "closed")
        if stop and st.time_left is None:
            return
        st.time_left = None if stop else min(TIME_MAX_MS, (st.time_left or 0) + add_ms)
        if st.phase == "open":
            self.counted[(st.activity, st.step)] = self.saved[(st.activity, st.step)] = now
        self._changed(st)

    # -------------------------------------------------------------- the slides
    @_move
    def slide(self, before: Iterable[tuple[str, str, str]], after: Iterable[tuple[str, str, str]], *, now: int,
              times: dict[tuple[str, str], int | None] | None = None,
              manual: Iterable[tuple[str, str]] = ()) -> list[StepRow]:
        """The projector shows another page (the design's 8.2). before, after: the steps the old and the
        new page show, each (activity, step, mark) - the mark says what the page is of its step: "open"
        or "revealed". A step whose pages the projector leaves closes. A step that is ready opens when
        a page of its comes that is marked open, with its time (times) - unless the deck opens it by
        hand (manual). A page marked revealed reveals its step if it was opened: paging back onto the
        reveal of a step nobody answered reveals nothing. Going back never reopens a closed step.
        What is asked is looked at first: a mark or a time that is none changes nothing."""
        before, after, manual, times = list(before), list(after), set(manual), dict(times or {})
        for a, s, mark in after:
            if mark not in MARKS:
                raise ValueError(f"a page's mark is one of {', '.join(MARKS)}, not {mark!r}")
            self.step(a, s)
            if times.get((a, s)) is not None:
                _time(times[(a, s)])
        self.tick(now)
        stay = {(a, s) for a, s, _ in after}
        for a, s, _ in before:
            st = self.get(a, s)
            if (a, s) not in stay and st is not None and st.phase in RUNNING:
                self._set(st, now, phase="closed", paused_by="")
        for a, s, mark in after:
            st = self.step(a, s)
            if mark == "revealed":
                if st.phase != "ready":
                    self.reveal(a, s, now=now)
            elif st.phase == "ready" and (a, s) not in manual:
                self.open(a, s, now=now, time_ms=times.get((a, s)), reopen=False)
