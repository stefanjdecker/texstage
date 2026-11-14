# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The core of the activity framework, its first part (texstage/activities: phases.py, entries.py,
store.py; docs/architecture/activity-framework-plan-f2.md, package 3): a game's steps and their phases
- reopening, pausing for a quiz round, a sleep, a reset, every move repeated -; the entries - the
limits, an entry sent again, another epoch -; the storage - the tables, the writer's commits, a
restart -; and the move of F1's rows, so that a store of today's games loads."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from texstage.activities import entries as entries_module
from texstage.activities import phases as phases_module
from texstage.activities import store as core
from texstage.activities.entries import Entries, Rules, shaped
from texstage.activities.phases import ONE, Phases, Refused
from texstage.activities.store import CheckRow, DetailRow, EntryRow, StepRow, Writer
from texstage.server.game import Session
from texstage.server.store import Store          # (before the activity type: the server's types come first)

from texstage.server import activity as f1  # isort: skip

HALF = chr(0xD83D)                   # half of an emoji's surrogate pair, as a browser cuts a text


class Saved:
    """What a game's steps or entries handed to be written, in order."""

    def __init__(self):
        self.rows = []

    def __call__(self, *rows):
        self.rows.extend(rows)

    def take(self):
        rows, self.rows = self.rows, []
        return rows


def refused(code: str, call, *args, **kwargs) -> Refused:
    with pytest.raises(Refused) as caught:
        call(*args, **kwargs)
    assert caught.value.code == code, str(caught.value)
    return caught.value


def game(save=None) -> Phases:
    return Phases("g1", save)


# ------------------------------------------------------------------ phases
def test_a_step_goes_from_ready_to_revealed_and_every_move_can_be_repeated():
    saved = Saved()
    p = game(saved)
    assert p.get("a") is None and p.current() is None and p.running() is None
    st = p.step("a")
    assert (st.session, st.activity, st.step, st.epoch, st.phase, st.time_left) == ("g1", "a", ONE, 0, "ready", None)
    assert saved.rows == [] and p.current() is None            # asking for a step stores nothing
    assert p.open("a", now=1000) == [st] and st.phase == "open"
    assert p.open("a", now=1100) == []
    assert p.running() is st and p.current() is st
    assert p.close("a", now=2000) == [st] and st.phase == "closed"
    assert p.close("a", now=2100) == []
    assert p.running() is None and p.current() is st
    assert p.reveal("a", now=3000) == [st] and st.phase == "revealed"
    assert p.reveal("a", now=3100) == [] and p.close("a", now=3200) == []
    assert saved.rows == [st, st, st]                          # one save for each move that changed it
    assert p.close("nobody-opened-it", now=3300) == [] and p.get("nobody-opened-it") is None
    for bad in (None, 7, "", ["a"]):                           # what is no step's name is refused, not an error
        refused("invalid", p.open, bad, now=3400)
        refused("invalid", p.reveal, "a", bad, now=3400)
        assert p.close(bad, now=3400) == [] and p.get(bad) is None


def test_one_step_is_open_at_a_time():
    p = game()
    p.open("a", now=0)
    changed = p.open("b", now=10)
    assert [(st.activity, st.phase) for st in changed] == [("a", "closed"), ("b", "open")]
    p.pause("b", now=20)
    changed = p.open("c", "vote", now=30)                      # a paused one closes too
    assert [(st.activity, st.step, st.phase, st.paused_by) for st in changed] == \
        [("b", ONE, "closed", ""), ("c", "vote", "open", "")]
    assert [st.activity for st in p.steps.values() if st.phase in ("open", "paused")] == ["c"]


def test_the_lecturer_reopens_a_closed_step_and_a_revealed_one_stays_revealed():
    p = game()
    p.open("a", now=0, time_ms=60_000)
    p.close("a", now=4_000)
    st = p.get("a")
    assert (st.phase, st.time_left) == ("closed", 56_000)      # what was left stays to be read
    assert p.open("a", now=20_000, reopen=False) == [] and st.phase == "closed"       # the slides: never
    assert p.open("a", now=21_000, time_ms=30_000) == [st]
    assert (st.phase, st.time_left, st.epoch) == ("open", 30_000, 0)                  # with the time it is given
    p.close("a", now=22_000)
    p.open("a", now=23_000)
    assert (st.phase, st.time_left) == ("open", None)                                 # ... or none
    p.time("a", now=23_500, add_ms=10_000)
    p.reveal("a", now=24_000)
    assert st.time_left is None                                # a revealed step has no time
    assert refused("revealed", p.open, "a", now=25_000) and st.phase == "revealed"
    assert p.reveal("never-opened", now=26_000)[0].phase == "revealed"                # the solution alone


def test_pause_and_resume_are_the_lecturers_and_a_quiz_rounds():
    p = game()
    refused("closed", p.pause, "a", now=0)
    refused("closed", p.resume, "a", now=0)
    p.open("a", now=0)
    st = p.get("a")
    assert p.resume("a", now=5) == []                          # open already
    assert p.pause("a", now=10) == [st] and (st.phase, st.paused_by) == ("paused", "lecturer")
    assert p.pause("a", now=20) == []
    assert p.open("a", now=30) == [st] and (st.phase, st.paused_by) == ("open", "")   # Open goes on, too
    p.pause("a", now=40)
    assert p.resume("a", now=50) == [st] and st.phase == "open"
    # a quiz round pauses the open step, and its end resumes it
    assert p.round(True, now=60) == [st] and (st.phase, st.paused_by) == ("paused", "quiz")
    assert p.round(True, now=70) == []
    assert p.round(False, now=80) == [st] and (st.phase, st.paused_by) == ("open", "")
    assert p.round(False, now=90) == []
    # ... unless the lecturer paused it meanwhile, or before
    p.round(True, now=100)
    assert p.pause("a", now=110) == [st] and st.paused_by == "lecturer"
    assert p.round(False, now=120) == [] and st.phase == "paused"
    assert p.round(True, now=130) == [] and st.paused_by == "lecturer"
    assert p.round(False, now=140) == [] and st.phase == "paused"
    p.resume("a", now=150)
    # a paused step closes, and nobody is said to have paused it then
    p.pause("a", now=160)
    assert p.close("a", now=170) == [st] and (st.phase, st.paused_by) == ("closed", "")
    refused("closed", p.pause, "a", now=180)
    refused("closed", p.resume, "a", now=180)
    assert p.round(True, now=200) == [] and p.round(False, now=210) == []             # nothing runs
    p.open("a", now=220)
    p.pause("a", now=230)
    assert p.reveal("a", now=240) == [st] and st.paused_by == ""
    p.reset("a", now=250)
    p.open("a", now=260)
    p.pause("a", now=270)
    assert p.reset("a", now=280) == [st] and (st.phase, st.paused_by) == ("ready", "")


def test_no_step_runs_beside_a_quiz_round():
    p = game()
    p.round(True, now=0)
    assert [(st.phase, st.paused_by, st.time_left) for st in p.open("a", now=10, time_ms=60_000)] == \
        [("paused", "quiz", 60_000)]                           # opened during a round: it waits for its end
    st = p.get("a")
    assert p.current() is st and p.open("a", now=20) == [] and p.resume("a", now=30) == []
    assert p.tick(40_000) == [] and st.time_left == 60_000     # its time has not begun
    assert p.round(False, now=50_000) == [st] and st.phase == "open"
    # the lecturer resumes during a round what the lecturer paused: it goes on when the round ends
    p.pause("a", now=50_100)
    p.round(True, now=50_200)
    assert p.resume("a", now=50_300) == [st] and (st.phase, st.paused_by) == ("paused", "quiz")
    assert p.round(False, now=50_400) == [st] and st.phase == "open"
    # ... and Open on a paused step, with another time
    p.round(True, now=50_500)
    assert p.open("a", now=50_600, time_ms=30_000) == [st] and (st.phase, st.time_left) == ("paused", 30_000)
    # the slides during a round: the step whose page comes waits, the one that ran closes
    changed = p.slide([("a", ONE, "open")], [("b", ONE, "open")], now=50_700)
    assert [(s.activity, s.phase, s.paused_by) for s in changed] == [("a", "closed", ""), ("b", "paused", "quiz")]
    assert p.round(False, now=50_800) == [p.get("b")] and p.get("b").phase == "open"
    # a server that starts again while a round runs
    q = game()
    rows = [StepRow("g1", "x", ONE, 0, "open", None, "", 1)]
    assert q.load(rows, now=0, round_on=True) == rows and (rows[0].phase, rows[0].paused_by) == ("paused", "quiz")
    assert q.round(False, now=10) == rows and rows[0].phase == "open"


def test_a_steps_time_counts_while_the_server_runs():
    saved = Saved()
    p = game(saved)
    p.open("a", now=0, time_ms=10_000)
    st = p.get("a")
    saved.take()
    for now in range(250, 4_751, 250):
        assert p.tick(now) == []
    assert st.time_left == 5_250 and saved.rows == []
    assert p.tick(5_000) == [] and saved.take() == [st]        # a running time is saved every 5 s
    p.pause("a", now=5_100)
    assert st.time_left == 4_900                               # a move counts up to its moment
    assert p.tick(60_000) == [] and st.time_left == 4_900      # paused: nothing counts
    p.resume("a", now=60_000)
    for now in range(60_250, 64_751, 250):
        assert p.tick(now) == [] and st.phase == "open"
    assert st.time_left == 150
    assert p.tick(65_000) == [st] and (st.phase, st.time_left) == ("closed", 0)       # used up: closed
    assert p.tick(66_000) == []
    assert refused("closed", p.pause, "a", now=67_000).changed == []


def test_a_refused_move_still_says_what_it_changed():
    saved = Saved()
    for move, more in (("pause", {}), ("resume", {}), ("time", {"add_ms": 30_000}), ("time", {"stop": True})):
        p = game(saved)
        p.open("a", now=0, time_ms=10_000)
        for now in range(250, 9_751, 250):
            p.tick(now)
        st = p.get("a")
        saved.take()
        why = refused("closed", getattr(p, move), "a", now=10_050, **more)            # as its time runs out
        assert why.changed == [st] and st.phase == "closed" and saved.take() == [st], move
        assert p.tick(10_300) == []                            # no later tick says it
    p = game()
    p.open("old", now=0)
    p.reveal("old", now=10)
    p.open("a", now=20, time_ms=10_000)
    why = refused("revealed", p.open, "old", now=3_600_000)    # ... and a sleep that a refused move found
    assert why.changed == [p.get("a")] and (p.get("a").phase, p.get("a").paused_by) == ("paused", "sleep")
    # what is not a move at all is refused before anything changes
    p = game()
    p.open("a", now=0, time_ms=10_000)
    assert refused("time", p.open, "a", now=3_600_000, time_ms=5).changed == [] and p.get("a").phase == "open"
    assert refused("time", p.time, "a", now=3_600_000).changed == [] and p.get("a").phase == "open"


def test_after_a_sleep_an_open_step_is_paused_not_closed():
    p = game()
    p.open("a", now=0, time_ms=10_000)
    st = p.get("a")
    p.tick(1_000)
    assert p.tick(3_600_000) == [st]                           # the laptop slept an hour
    assert (st.phase, st.paused_by, st.time_left) == ("paused", "sleep", 9_000)
    assert p.round(False, now=3_600_100) == []                 # a round's end does not resume it
    assert p.resume("a", now=3_600_200) == [st] and p.tick(3_600_700) == [] and st.time_left == 8_500
    assert p.tick(3_600_700 + phases_module.SLEEP_MS) == [] and st.time_left == 3_500    # 5 s: no sleep yet
    # a step without a time stays open through a sleep
    q = game()
    q.open("b", now=0)
    assert q.tick(3_600_000) == [] and q.get("b").phase == "open"
    # a move after a gap finds the step paused first, and each changed row comes once
    r = game()
    r.open("c", now=0, time_ms=10_000)
    assert r.reveal("c", now=50_000) == [r.get("c")] and r.get("c").phase == "revealed"
    s = game()
    s.open("d", now=0, time_ms=1_000)
    assert s.close("d", now=1_000) == [s.get("d")] and s.get("d").time_left == 0      # ran out, then the close
    # a round that opens after such a gap finds the step paused by the sleep: its end does not resume it
    t = game()
    t.open("e", now=0, time_ms=10_000)
    assert [x.paused_by for x in t.round(True, now=50_000)] == ["sleep"]
    assert t.round(False, now=50_100) == [] and t.get("e").phase == "paused"


def test_a_clock_that_is_set_back_takes_nothing_off():
    saved = Saved()
    p = game(saved)
    p.open("a", now=3_600_000, time_ms=60_000)
    st = p.get("a")
    p.tick(3_600_500)
    saved.take()
    assert p.tick(600_000) == [] and (st.phase, st.time_left) == ("open", 59_500)     # set back 50 minutes
    for now in range(600_250, 605_001, 250):
        p.tick(now)
    assert st.time_left == 54_500 and saved.take() == [st]     # counted, and saved, from the new time on


def test_more_time_and_no_time():
    saved = Saved()
    p = game(saved)
    refused("closed", p.time, "a", now=0, add_ms=10_000)
    p.open("a", now=0)
    st = p.get("a")
    saved.take()
    assert p.time("a", now=100, add_ms=10_000) == [st] and st.time_left == 10_000     # a step without a time gets one
    assert saved.take() == [st]
    p.tick(600)
    assert st.time_left == 9_500
    assert p.time("a", now=700, add_ms=30_000) == [st] and st.time_left == 39_400
    assert p.time("a", now=700, add_ms=30_000) == [st] and st.time_left == 69_400     # asked twice, it adds twice
    p.pause("a", now=800)
    p.time("a", now=900, add_ms=1_000)                         # a paused step, too
    assert st.time_left == 70_300
    assert p.open("a", now=60_000, time_ms=5_000) == [st] and (st.phase, st.time_left) == ("open", 5_000)
    p.pause("a", now=60_010)                                   # Open on a paused step: with the time given,
    assert p.open("a", now=60_020) == [st] and st.time_left == 4_990                  # or the one it had
    assert p.time("a", now=60_100, stop=True) == [st] and st.time_left is None
    assert p.time("a", now=60_200, stop=True) == []
    assert p.tick(3_600_000) == [] and st.phase == "open"
    p.time("a", now=3_600_000, add_ms=phases_module.TIME_MAX_MS)
    p.time("a", now=3_600_000, add_ms=phases_module.TIME_MAX_MS)
    assert st.time_left == phases_module.TIME_MAX_MS           # at most
    for bad in ({}, {"add_ms": 10_000, "stop": True}, {"add_ms": 999}, {"add_ms": True}, {"add_ms": 1.5e4},
                {"add_ms": -5_000}, {"add_ms": phases_module.TIME_MAX_MS + 1}):
        refused("time", p.time, "a", now=3_600_000, **bad)
    refused("time", p.open, "b", now=3_600_000, time_ms=0)
    p.close("a", now=3_600_100)
    refused("closed", p.time, "a", now=3_600_200, stop=True)


def test_a_reset_gives_a_new_epoch():
    p = game()
    assert p.reset("a", now=0) == [] and p.get("a") is None
    p.open("a", now=0, time_ms=60_000)
    st = p.get("a")
    assert p.reset("a", now=1_000) == [st]
    assert (st.phase, st.epoch, st.time_left, st.paused_by) == ("ready", 1, None, "")
    assert p.reset("a", now=1_100) == [] and st.epoch == 1     # a ready step has nothing to reset
    p.open("a", now=2_000)
    p.reveal("a", now=3_000)
    assert p.reset("a", now=4_000) == [st] and (st.phase, st.epoch) == ("ready", 2)   # after the reveal, too
    assert p.open("a", now=5_000) == [st] and st.phase == "open"


def test_the_current_step_is_the_one_opened_or_revealed_last():
    p = game()
    p.open("monday", now=1_000)
    p.reveal("monday", now=2_000)
    p.open("today", now=900_000)
    today = p.get("today")
    assert p.current() is today
    p.reset("today", now=901_000)
    assert p.current() is today and today.phase == "ready"     # a reset step stays the current one
    p.open("today", now=902_000)
    p.close("today", now=903_000)
    assert p.current() is today
    p.reveal("monday", now=904_000)                            # revealed already: nothing changes
    assert p.current() is today
    p.reveal("older", now=905_000)                             # a step revealed from the panel is shown
    assert p.current().activity == "older"
    p.open("today", now=906_000)
    assert p.current() is today                                # ... until one runs
    # two steps that changed in the same moment: the same current one after a restart
    q = game()
    q.open("a", now=0)
    q.slide([("a", ONE, "open")], [("b", ONE, "open")], now=20)
    q.slide([("b", ONE, "open")], [("b", ONE, "revealed")], now=20)
    assert q.current().activity == "b" and [st.seq for st in q.steps.values()] == [1, 2]
    for rows in (list(q.steps.values()), list(reversed(q.steps.values()))):
        r = game()
        r.load([StepRow(**vars(row)) for row in rows], now=30)
        assert r.current().activity == "b" and r.seq == 2
    r.open("c", now=40)
    assert r.get("c").seq == 3


def test_the_slides_open_close_and_reveal():
    p = game()
    page = [("a", ONE, "open")]
    changed = p.slide([], page, now=0, times={("a", ONE): 60_000})
    st = p.get("a")
    assert changed == [st] and (st.phase, st.time_left) == ("open", 60_000)
    assert p.slide(page, page, now=100) == []
    assert p.slide(page, [], now=200) == [st] and st.phase == "closed"                # its page goes
    assert p.slide([], page, now=300) == [] and st.phase == "closed"                  # going back never reopens
    assert p.open("a", now=400) == [st]                                               # the lecturer does
    # overlays: the second page reveals; going back changes nothing
    reveal = [("a", ONE, "revealed")]
    assert p.slide(page, reveal, now=500) == [st] and st.phase == "revealed"
    assert p.slide(reveal, page, now=600) == [] and st.phase == "revealed"
    assert p.slide(page, [], now=700) == []
    # a deck that opens a step by hand; the page still closes it, paused or not, though nothing opens
    assert p.slide([], [("m", ONE, "open")], now=800, manual=[("m", ONE)]) == [] and p.get("m").phase == "ready"
    p.open("m", now=900)
    p.pause("m", now=1_000)
    assert [(s.phase, s.paused_by) for s in p.slide([("m", ONE, "open")], [], now=1_100)] == [("closed", "")]
    # two steps on one page: the last one opens, as in F1
    both = [("x", ONE, "open"), ("y", ONE, "open")]
    p.slide([], both, now=1_200)
    assert (p.get("x").phase, p.get("y").phase) == ("closed", "open")


def test_the_slides_reveal_only_what_was_opened():
    p = game()
    page, reveal = [("a", ONE, "open")], [("a", ONE, "revealed")]
    assert p.slide([], reveal, now=0) == [] and p.get("a").phase == "ready"           # paging back onto a reveal
    st = p.get("a")
    assert p.slide(reveal, page, now=10) == [st] and st.phase == "open"               # ... and on to the question
    assert p.slide(page, reveal, now=20) == [st] and st.phase == "revealed"
    # asked again: reset on the reveal's page, back to the question - it opens -, forward - it is revealed
    p.reset("a", now=30)
    assert p.slide(reveal, reveal, now=40) == [] and st.phase == "ready"
    assert p.slide(reveal, page, now=50) == [st] and (st.phase, st.epoch) == ("open", 1)
    assert p.slide(page, reveal, now=60) == [st] and st.phase == "revealed"
    # a closed step is revealed by its page, a ready one by the lecturer alone
    p.open("b", now=70)
    p.close("b", now=80)
    assert [s.phase for s in p.slide([], [("b", ONE, "revealed")], now=90)] == ["revealed"]


def test_a_page_that_asks_what_cannot_be_changes_nothing():
    p = game()
    p.open("x", now=0)
    with pytest.raises(ValueError, match="mark"):
        p.slide([("x", ONE, "open")], [("y", ONE, "open"), ("z", ONE, "closed")], now=100)
    assert p.get("x").phase == "open" and p.get("y").phase == "ready"
    why = refused("time", p.slide, [("x", ONE, "open")], [("y", ONE, "open")], now=200, times={("y", ONE): 5})
    assert why.changed == [] and p.get("x").phase == "open" and p.get("y").phase == "ready"
    refused("invalid", p.slide, [("x", ONE, "open")], [("y", ONE, "open"), (None, ONE, "open")], now=300)
    assert p.get("x").phase == "open" and p.get("y").phase == "ready"


def test_a_restarted_server_pauses_what_ran_on_a_time():
    saved = Saved()
    rows = [StepRow("g1", "timed", ONE, 2, "open", 30_000, "", 7), StepRow("g1", "done", ONE, 0, "revealed", seq=3),
            StepRow("g2", "other-game", ONE, 0, "open", 30_000, seq=99)]
    p = game(saved)
    changed = p.load(rows, now=10_000)
    assert changed == [rows[0]] == saved.rows
    assert (rows[0].phase, rows[0].paused_by, rows[0].time_left, rows[0].epoch) == ("paused", "sleep", 30_000, 2)
    assert p.current() is rows[0] and set(p.steps) == {("timed", ONE), ("done", ONE)} and p.seq == 7
    assert rows[2].phase == "open"                             # another game's: not this one's to touch
    untimed = [StepRow("g1", "u", ONE, 0, "open", None, "", 2), StepRow("g1", "done", ONE, 0, "revealed", seq=3),
               StepRow("g1", "ready-again", ONE, 4, "ready", seq=1)]
    q = game()
    assert q.load(untimed, now=10_000) == [] and q.current() is untimed[0]            # stays open
    q.close("u", now=10_100)
    assert q.current().activity == "done"                      # the one opened or revealed last


# ------------------------------------------------------------------ entries
CODE = Rules("code", limit=3, gap_ms=5_000, counts="latest")
TRIPLE = Rules("fields", limit=3, gap_ms=2_000, counts="all", fields=3)


def opened(activity: str = "a", **step) -> StepRow:
    return StepRow("g1", activity, ONE, **{"phase": "open", **step})


def test_an_entry_is_kept_and_the_latest_one_counts():
    saved = Saved()
    es, st = Entries("g1", saved), opened()
    e1, new, replaced = es.enter(st, CODE, "p1", "entry-0001", {"text": "SELECT 1"}, now=10_000)
    assert new and replaced == [] and saved.take() == [e1]
    assert e1 == EntryRow("entry-0001", "g1", "a", ONE, 0, "p1", 10_000, {"text": "SELECT 1"}, "", "in")
    e2 = es.enter(st, CODE, "p2", "entry-0002", {"text": "SELECT 2", "more": "is not kept"}, now=10_001).entry
    assert e2.input == {"text": "SELECT 2"}
    assert es.counts(st) == {"entries": 2, "students": 2}
    e3, new, replaced = es.enter(st, CODE, "p1", "entry-0003", {"text": "SELECT 3"}, now=15_000)
    assert replaced == [e1] and (e1.state, e3.state) == ("replaced", "in") and saved.take() == [e2, e1, e3]
    assert es.counts(st) == {"entries": 2, "students": 2}
    assert es.mine(st, "p1") == [e1, e3] and es.mine(st, "nobody") == []
    assert es.get("a", ONE, "entry-0003") is e3 and es.get("a", ONE, "entry-9999") is None
    assert es.get("b", ONE, "entry-0003") is None and es.get("a", ONE, None) is None and es.get(["a"], ONE, "x") is None
    # the latest replaces what is in: not what was taken back, not what the lecturer hid
    es.withdraw(st, "p1", "entry-0003")
    es.hide(e2)
    e4, _, replaced = es.enter(st, Rules("code", 9, 0), "p1", "entry-0004", {"text": "SELECT 4"}, now=20_000)
    assert replaced == [] and e3.state == "withdrawn"
    e5, _, replaced = es.enter(st, Rules("code", 9, 0), "p2", "entry-0005", {"text": "SELECT 5"}, now=20_000)
    assert replaced == [] and e2.state == "hidden"


def test_an_entry_sent_again_is_the_one_that_is_there():
    saved = Saved()
    es, st = Entries("g1", saved), opened()
    e = es.enter(st, CODE, "p1", "entry-0001", {"text": "SELECT 1"}, now=10_000).entry
    saved.take()
    again = es.enter(st, CODE, "p1", "entry-0001", {"text": "SELECT 1"}, now=10_050)         # no gap asked of it
    assert again == (e, False, []) and again.entry is e and saved.rows == []
    assert es.counts(st) == {"entries": 1, "students": 1}
    st.phase = "closed"                                        # ... whatever the step's phase is now
    assert es.enter(st, CODE, "p1", "entry-0001", {"text": "another text"}, now=99_000, blocked=True).new is False
    assert e.input == {"text": "SELECT 1"}
    assert "taken" in str(refused("invalid", es.enter, st, CODE, "p2", "entry-0001", {"text": "x"}, now=99_000))
    for bad in (None, 7, "", "short", "x" * 41, "has space 1", "semi;colon1", "entry-0001\n"):
        refused("invalid", es.enter, st, CODE, "p1", bad, {"text": "x"}, now=99_000)
    for nobody in (None, "", 7):
        refused("invalid", es.enter, st, CODE, nobody, "entry-0002", {"text": "x"}, now=99_000)
    b = opened("b")                                            # an id is its step's: another step has its own
    assert es.enter(b, CODE, "p1", "entry-0001", {"text": "y"}, now=99_000).new is True


def test_what_the_core_refuses_and_in_which_order():
    es = Entries("g1")
    st = opened(phase="ready")
    send = dict(now=10_000)
    refused("closed", es.enter, st, CODE, "p1", "entry-0001", {"text": ""}, blocked=True, **send)
    st.phase = "paused"
    refused("paused", es.enter, st, CODE, "p1", "entry-0001", {"text": ""}, blocked=True, **send)
    for phase in ("closed", "revealed"):
        st.phase = phase
        refused("closed", es.enter, st, CODE, "p1", "entry-0001", {"text": "x"}, **send)
    st.phase = "open"
    refused("blocked", es.enter, st, CODE, "p1", "entry-0001", {"text": ""}, blocked=True, **send)
    refused("text", es.enter, st, CODE, "p1", "entry-0001", {"text": "  \n "}, **send)
    refused("too-long", es.enter, st, CODE, "p1", "entry-0001", {"text": "x" * 2001}, **send)
    for bad in ({}, {"text": 5}, {"text": None}, {"text": ["x"]}, {"fields": ["a"]}, {"text": "half " + HALF}, None, "x"):
        refused("invalid", es.enter, st, CODE, "p1", "entry-0001", bad, **send)
    assert es.counts(st) == {"entries": 0, "students": 0}      # a refusal counts for nothing: not for the gap
    es.enter(st, CODE, "p1", "entry-0001", {"text": "x" * 2000}, **send)
    # blocked before too fast, too fast before anything about the text
    refused("blocked", es.enter, st, CODE, "p1", "entry-0002", {"text": ""}, now=14_999, blocked=True)
    refused("too-fast", es.enter, st, CODE, "p1", "entry-0002", {"text": ""}, now=14_999)
    es.enter(st, CODE, "p1", "entry-0002", {"text": "2"}, now=15_000)
    es.enter(st, CODE, "p1", "entry-0003", {"text": "3"}, now=20_000)
    # counts=latest: every entry sent counts against the limit, the replaced ones too
    refused("too-many", es.enter, st, CODE, "p1", "entry-0004", {"text": ""}, now=25_000)
    refused("too-fast", es.enter, st, CODE, "p1", "entry-0004", {"text": "4"}, now=24_000)
    es.enter(st, CODE, "p2", "entry-0005", {"text": "5"}, now=20_000)                 # each student their own


def test_a_clock_set_back_keeps_nobody_waiting():
    es, st = Entries("g1"), opened()
    es.enter(st, CODE, "p1", "entry-0001", {"text": "x"}, now=3_600_000)
    es.enter(st, CODE, "p1", "entry-0002", {"text": "y"}, now=600_000)                # set back 50 minutes
    refused("too-fast", es.enter, st, CODE, "p1", "entry-0003", {"text": "z"}, now=604_999)   # the gap, from then on
    assert es.enter(st, CODE, "p1", "entry-0003", {"text": "z"}, now=605_000).new


def test_fields_all_count_and_one_is_sent_once():
    es, st = Entries("g1"), opened()
    a = es.enter(st, TRIPLE, "p1", "entry-0001", {"fields": [":a", ":knows", ":b"]}, now=10_000).entry
    assert a.input == {"fields": [":a", ":knows", ":b"]}
    refused("duplicate", es.enter, st, TRIPLE, "p1", "entry-0002", {"fields": [":a", ":knows", ":b"]}, now=12_000)
    b, _, replaced = es.enter(st, TRIPLE, "p1", "entry-0002", {"fields": [":a", ":knows", ":c"]}, now=12_000)
    c = es.enter(st, TRIPLE, "p1", "entry-0003", {"fields": [":c", ":knows", ":d"]}, now=14_000).entry
    assert replaced == [] and [e.state for e in (a, b, c)] == ["in", "in", "in"]
    assert es.counts(st) == {"entries": 3, "students": 1}
    refused("too-many", es.enter, st, TRIPLE, "p1", "entry-0004", {"fields": [":d", ":knows", ":e"]}, now=16_000)
    es.withdraw(st, "p1", "entry-0001")                        # one taken back gives its place back
    d = es.enter(st, TRIPLE, "p1", "entry-0004", {"fields": [":a", ":knows", ":b"]}, now=16_000).entry   # and may come again
    assert d.state == "in" and es.counts(st) == {"entries": 3, "students": 1}
    for bad in ({"fields": [":a", ":b"]}, {"fields": ":a :b :c"}, {"fields": [":a", 1, ":c"]}, {"text": ":a :b :c"},
                {"fields": [":a", HALF, ":c"]}):
        refused("invalid", es.enter, st, TRIPLE, "p2", "entry-0009", bad, now=10_000)
    refused("field", es.enter, st, TRIPLE, "p2", "entry-0009", {"fields": [":a", " ", ":c"]}, now=10_000)
    refused("too-long", es.enter, st, TRIPLE, "p2", "entry-0009", {"fields": ["a" * 1000, "b" * 1000, "c"]}, now=10_000)
    assert es.enter(st, TRIPLE, "p2", "entry-0009", {"fields": ["a" * 1000, "b" * 999, "c"]}, now=10_000).new
    with pytest.raises(Refused, match="choice: places of the 3 options"):           # (package 9: a choice's shape)
        shaped(Rules("choice", options=3), {"choice": 1})
    with pytest.raises(Refused, match="no input"):
        shaped(Rules("nothing"), {"text": "a"})


def test_what_the_lecturer_hid_gives_no_place_back_and_is_not_sent_again():
    es, st = Entries("g1"), opened()
    rules = Rules("fields", 2, 0, "all", 1)
    a = es.enter(st, rules, "p1", "entry-0001", {"fields": ["something rude"]}, now=1).entry
    assert es.hide(a) and not es.hide(a) and es.counts(st) == {"entries": 0, "students": 0}
    refused("duplicate", es.enter, st, rules, "p1", "entry-0002", {"fields": ["something rude"]}, now=2)
    es.enter(st, rules, "p1", "entry-0002", {"fields": ["two"]}, now=3)
    refused("too-many", es.enter, st, rules, "p1", "entry-0003", {"fields": ["three"]}, now=4)    # hidden: no place back
    assert es.show(a, rules) and not es.show(a, rules)
    assert es.counts(st) == {"entries": 2, "students": 1}      # shown again: never more in than the limit


def test_nobody_fills_a_step_by_sending_and_taking_back():
    es, st = Entries("g1"), opened()
    rules = Rules("fields", 3, 0, "all", 1)
    for i in range(9):                                         # three times the limit in all
        es.enter(st, rules, "p1", f"entry-000{i}", {"fields": [str(i)]}, now=i)
        es.withdraw(st, "p1", f"entry-000{i}")
    refused("too-many", es.enter, st, rules, "p1", "entry-0009", {"fields": ["9"]}, now=9)
    assert es.enter(st, rules, "p2", "entry-0010", {"fields": ["mine"]}, now=10).new  # the others still send


def test_a_step_is_full_at_some_point(monkeypatch):
    monkeypatch.setattr(entries_module, "PER_STEP", 3)
    es, st = Entries("g1"), opened()
    for i in range(3):
        es.enter(st, CODE, f"p{i}", f"entry-000{i}", {"text": "x"}, now=10_000)
    es.withdraw(st, "p0", "entry-0000")                        # every entry counts, whatever became of it
    refused("full", es.enter, st, CODE, "p9", "entry-0009", {"text": "x"}, now=10_000)
    refused("too-many", es.enter, st, Rules("code", 1, 0), "p1", "entry-0011", {"text": "x"}, now=30_000)   # too many
    refused("full", es.enter, st, Rules("code", 2, 0), "p1", "entry-0011", {"text": ""}, now=30_000)    # before full,
    #                                                                                                    full before the text
    assert es.enter(st, CODE, "p0", "entry-0000", {"text": "x"}, now=10_000).new is False    # one sent again still answers
    st.epoch = 1                                               # another epoch has room again
    assert es.enter(st, CODE, "p9", "entry-0009", {"text": "x"}, now=40_000).new


def test_a_student_takes_an_entry_back():
    saved = Saved()
    es, st = Entries("g1", saved), opened()
    e = es.enter(st, CODE, "p1", "entry-0001", {"text": "x"}, now=10_000).entry
    saved.take()
    refused("invalid", es.withdraw, st, "p2", "entry-0001")    # not theirs
    refused("invalid", es.withdraw, st, "p1", "entry-0002")
    refused("invalid", es.withdraw, st, "p1", None)
    st.phase = "paused"
    refused("paused", es.withdraw, st, "p1", "entry-0001")
    st.phase = "closed"
    refused("closed", es.withdraw, st, "p1", "entry-0001")
    st.phase = "open"
    assert es.withdraw(st, "p1", "entry-0001") is e and e.state == "withdrawn" and saved.take() == [e]
    assert es.counts(st) == {"entries": 0, "students": 0} and es.mine(st, "p1") == [e]       # still on the phone's list
    st.phase = "closed"
    assert es.withdraw(st, "p1", "entry-0001") is e and saved.rows == []              # again: nothing changes
    st.phase = "open"
    es.enter(st, CODE, "p1", "entry-0002", {"text": "y"}, now=20_000)
    es.enter(st, CODE, "p1", "entry-0003", {"text": "z"}, now=30_000)
    refused("invalid", es.withdraw, st, "p1", "entry-0002")    # replaced: not in any more


def test_another_epoch_counts_anew_and_knows_the_earlier_ids():
    es, st = Entries("g1"), opened()
    for i in range(3):
        es.enter(st, CODE, "p1", f"entry-000{i}", {"text": str(i)}, now=10_000 + 5_000 * i)
    old = es.get("a", ONE, "entry-0002")
    st.epoch, st.phase = 1, "open"                             # a reset, and opened again
    assert es.counts(st) == {"entries": 0, "students": 0} and es.mine(st, "p1") == []
    e, new, _ = es.enter(st, CODE, "p1", "entry-0010", {"text": "anew"}, now=20_001)  # no gap, no limit left over
    assert new and e.epoch == 1 and es.counts(st) == {"entries": 1, "students": 1}
    assert es.enter(st, CODE, "p1", "entry-0002", {"text": "2"}, now=20_002)[:2] == (old, False)   # sent again, late
    assert old.epoch == 0 and old.state == "in"
    refused("invalid", es.withdraw, st, "p1", "entry-0002")    # the earlier epoch's are not to take back
    assert es.hide(old) and es.counts(st) == {"entries": 1, "students": 1}            # ... and count for nothing
    assert es.show(old, CODE) and old.state == "in" and es.counts(st) == {"entries": 1, "students": 1}


def test_an_entry_hidden_and_shown_again():
    saved = Saved()
    es, st = Entries("g1", saved), opened()
    e = es.enter(st, TRIPLE, "p1", "entry-0001", {"fields": ["a", "b", "c"]}, now=10_000).entry
    saved.take()
    assert es.hide(e) and es.counts(st) == {"entries": 0, "students": 0} and saved.take() == [e]
    assert not es.hide(e) and saved.rows == []
    assert es.show(e, TRIPLE) and es.counts(st) == {"entries": 1, "students": 1} and saved.take() == [e]
    assert not es.show(e, TRIPLE) and saved.rows == []
    es.withdraw(st, "p1", "entry-0001")
    assert not es.hide(e) and not es.show(e, TRIPLE) and e.state == "withdrawn"       # only what is in, or hidden
    # where the latest counts: shown again after the student sent another, it is replaced by that one
    q = opened("q")
    e1 = es.enter(q, CODE, "p1", "entry-0001", {"text": "one"}, now=1).entry
    es.hide(e1)
    e2 = es.enter(q, CODE, "p1", "entry-0002", {"text": "two"}, now=6_000).entry
    assert es.show(e1, CODE) and (e1.state, e2.state) == ("replaced", "in")
    assert es.counts(q) == {"entries": 1, "students": 1}
    assert not es.hide(e1) and not es.show(e1, CODE) and e1.state == "replaced"       # a replaced one is neither
    es.hide(e2)
    assert es.show(e2, CODE) == [e2] and e2.state == "in"      # the latest itself is in again
    # both hidden, the earlier one shown first: the later one, shown, replaces it - one entry of a student is in
    e3 = es.enter(q, CODE, "p2", "entry-0003", {"text": "three"}, now=7_000).entry
    es.hide(e3)
    e4 = es.enter(q, CODE, "p2", "entry-0004", {"text": "four"}, now=13_000).entry
    es.hide(e4)
    saved.take()
    assert es.show(e3, CODE) == [e3] and es.show(e4, CODE) == [e4, e3] and saved.take() == [e3, e4, e3]
    assert (e3.state, e4.state) == ("replaced", "in") and es.counts(q) == {"entries": 2, "students": 2}
    assert es.show(e4, CODE) == []
    # where all count, both are in
    t = opened("t")
    f1_, f2_ = (es.enter(t, TRIPLE, "p1", f"entry-000{i}", {"fields": ["a", "b", str(i)]}, now=i * 10_000).entry
                for i in (5, 6))
    es.hide(f1_), es.hide(f2_)
    assert es.show(f1_, TRIPLE) == [f1_] and es.show(f2_, TRIPLE) == [f2_] and es.counts(t)["entries"] == 2


class _Kind:
    def __init__(self, input: str, limit: int = 5):
        self.INPUT, self.LIMIT = input, limit


def test_a_steps_rules_come_from_its_item_and_its_kind():
    assert Rules.of({}, _Kind("code")) == Rules("code", 5, 5_000, "latest", 0)
    assert Rules.of({"fields": ["s", "p", "o"]}, _Kind("fields", 10)) == Rules("fields", 10, 2_000, "all", 3)
    assert Rules.of({"limit": 2, "gap": 0.5, "counts": "all", "fields": ["not", "the", "code's"]}, _Kind("code")) \
        == Rules("code", 2, 500, "all", 0)
    assert Rules.of({"gap": 0}, _Kind("text")).gap_ms == 0
    for bad in ({"limit": 0}, {"limit": 51}, {"limit": True}, {"limit": "5"}, {"gap": -1}, {"gap": 3601}, {"gap": "2"},
                {"counts": "best"}):
        with pytest.raises(ValueError):
            Rules.of(bad, _Kind("code"))
    for bad in ({}, {"fields": []}, {"fields": "spo"}, {"fields": list("123456789")}):
        with pytest.raises(ValueError, match="fields"):
            Rules.of(bad, _Kind("fields"))


def test_who_takes_an_entry_ticks_first():
    p, es = game(), Entries("g1")
    p.open("a", now=0, time_ms=1_000)
    st = p.get("a")
    assert p.tick(1_200) == [st]                               # the time was up 200 ms ago
    refused("closed", es.enter, st, CODE, "p1", "entry-0001", {"text": "late"}, now=1_200)


# ------------------------------------------------------------------ storage
def memory() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    core.create(db)
    return db


def count(db, table: str) -> int:
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_the_tables_are_made_once_and_an_older_file_gets_its_columns():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE steps (session, activity, step, PRIMARY KEY (session, activity, step))")
    db.execute("INSERT INTO steps VALUES ('g1', 'a', 'main'), ('g1', 'b', 'main')")
    db.execute("CREATE TABLE entries (id, session, activity, step, epoch, player, created, input, "
               "PRIMARY KEY (session, activity, step, id))")
    db.execute("INSERT INTO entries VALUES ('entry-0001', 'g1', 'a', 'main', 0, 'p1', 5, '{\"text\": \"x\"}')")
    core.create(db)
    core.create(db)
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
    assert {"steps", "entries", "checks", "details"} <= names
    assert {"steps_session", "entries_session", "checks_session", "details_session"} <= names     # an index by session
    for table, cols, _, _ in core.ROWS.values():
        assert {r[1] for r in db.execute(f"PRAGMA table_info({table})")} == set(cols)
        assert "session" in cols                               # every table has its session
    # a column that came later is read as the row's default
    got = core.load(db, ["g1"])
    assert got.steps == [StepRow("g1", "a", "main", 0, "ready", None, "", 0), StepRow("g1", "b")]
    assert got.entries == [EntryRow("entry-0001", "g1", "a", "main", 0, "p1", 5, {"text": "x"}, "", "in")]
    p, es = game(), Entries("g1")
    assert p.load(got.steps, now=5) == [] and p.current() is None
    es.load(got.entries)
    assert es.counts(got.steps[0]) == {"entries": 1, "students": 1}
    assert core.load(db, []) == core.Loaded()


def test_the_writer_commits_what_was_handed_over_in_one_transaction():
    db = memory()
    w = Writer(db)
    acks = []
    assert w.flush() == 0 and w.commits == 0
    e = EntryRow("entry-0001", "g1", "a", ONE, 0, "p1", 10, {"text": "SELECT 1"})
    st = StepRow("g1", "a", phase="open", seq=5)
    w.put(e, st, then=lambda: acks.append("first"))
    w.put(e, then=lambda: acks.append("again"))                # the same row: written once
    assert w.pending() == 2 and count(db, "entries") == 0 and acks == []              # nothing before the commit
    e.state = "replaced"                                       # ... and as it is then
    assert w.flush() == 2 and w.commits == 1 and acks == ["first", "again"] and w.pending() == 0
    assert not db.in_transaction and w.then == []
    assert core.load(db, ["g1"]).entries == [e] and core.load(db, ["g1"]).steps == [st]
    assert w.flush() == 0 and w.commits == 1 and acks == ["first", "again"]
    w.put(then=lambda: acks.append("nothing to write"))        # what waits is still told
    assert w.flush() == 0 and acks[-1] == "nothing to write" and w.commits == 2
    with pytest.raises(TypeError, match="none of the core's rows"):
        w.put(Session("g1", "123456", "deck", "bundle", 0, 0))


def test_a_row_written_again_keeps_its_place():
    db = memory()
    w = Writer(db)
    rows = [EntryRow(f"entry-000{i}", "g1", "a", ONE, 0, f"p{i}", 10 - i, {"text": str(i)}) for i in range(3)]
    w.put(*rows)
    w.flush()
    rows[0].state, rows[0].norm = "hidden", "abc"
    w.put(rows[0])
    w.flush()
    back = core.load(db, ["g1"]).entries
    assert back == rows and [e.id for e in back] == ["entry-0000", "entry-0001", "entry-0002"]     # the order they came


def test_a_commit_the_database_refuses_writes_nothing_and_acknowledges_nothing():
    db = memory()
    w = Writer(db)
    acks = []
    step, entry = StepRow("g1", "a", phase="open"), EntryRow("entry-0001", "g1", "a", ONE, 0, "p1", 10, {"text": "x"})
    db.execute("ALTER TABLE entries RENAME TO elsewhere")      # the database cannot take the entry now
    db.commit()
    w.put(step, entry, then=lambda: acks.append("written"))
    for n in (1, 2):
        with pytest.raises(sqlite3.OperationalError):
            w.flush()
        assert count(db, "steps") == 0 and acks == [] and not db.in_transaction      # the step is not written alone
        assert w.failures == n and "entries" in w.error and w.pending() == 2 and w.commits == 0 and w.dropped == 0
    db.execute("ALTER TABLE elsewhere RENAME TO entries")
    db.commit()
    assert w.flush() == 2 and acks == ["written"] and count(db, "entries") == 1 and w.error == ""


def test_a_failed_commit_takes_back_its_own_rows_not_the_engines():
    db = memory()
    db.execute("CREATE TABLE sessions (id PRIMARY KEY, slide)")
    db.commit()
    w = Writer(db)
    db.execute("INSERT INTO sessions VALUES ('g1', 3)")        # the engine saved, and has not committed yet
    db.execute("ALTER TABLE entries RENAME TO elsewhere")
    w.put(StepRow("g1", "a", phase="open"), EntryRow("entry-0001", "g1", "a", ONE, 0, "p1", 10, {"text": "x"}))
    with pytest.raises(sqlite3.OperationalError):
        w.flush()
    assert db.in_transaction and count(db, "steps") == 0       # the writer's step is taken back,
    assert count(db, "sessions") == 1                          # the engine's row is still there to commit
    db.execute("ALTER TABLE elsewhere RENAME TO entries")
    assert w.flush() == 2 and not db.in_transaction
    assert count(db, "sessions") == 1 and count(db, "steps") == 1


def test_a_row_that_no_commit_can_take_is_set_aside():
    db = memory()
    lost, acks = [], []
    w = Writer(db, lost=lambda row, why: lost.append((row, why)))
    good = EntryRow("entry-0001", "g1", "a", ONE, 0, "p1", 10, {"text": "x"})
    bad = EntryRow("entry-0002", "g1", "a", ONE, 0, "p2", object(), {"text": "y"})    # no store has a type for this
    worse = CheckRow("g1", "a", ONE, "n", "ok", key="k", message={"code": "x", "args": {1, 2}})   # nor JSON for a set
    huge = CheckRow("g1", "a", ONE, "m", "ok", key="k", created=10**30)
    w.put(good, then=lambda: acks.append("good"))
    w.put(bad, then=lambda: acks.append("bad"))
    w.put(worse, huge)
    w.put(then=lambda: acks.append("everything before"))
    later = EntryRow("entry-0003", "g1", "a", ONE, 0, "p3", 11, {"text": "z"})
    w.put(later, then=lambda: acks.append("later"))
    assert w.flush() == 2 and count(db, "entries") == 2 and count(db, "checks") == 0  # the others are not held up
    assert acks == ["good", "everything before", "later"]      # what waited for the row is not told it is written
    assert [row for row, _ in lost] == [bad, worse, huge] and all(why for _, why in lost)
    assert w.dropped == 3 and [row for row, _ in w.aside] == [bad, worse, huge] and w.failures == 0 and w.pending() == 0
    bad.created = 12                                           # handed over again, as it can be written
    w.put(bad)
    assert w.flush() == 1 and count(db, "entries") == 3


def test_one_that_cannot_be_told_does_not_keep_the_others_waiting():
    db = memory()
    acks = []

    def gone(*_):
        raise ConnectionError("this phone left")
    w = Writer(db, lost=gone)
    w.put(EntryRow("entry-0001", "g1", "a", ONE, 0, "p1", 10, {"text": "x"}), then=gone)
    w.put(EntryRow("entry-0002", "g1", "a", ONE, 0, "p2", object(), {"text": "y"}))
    w.put(then=lambda: acks.append("told"))
    assert w.flush() == 1 and acks == ["told"] and count(db, "entries") == 1 and w.pending() == 0
    assert w.untold == 2 and "this phone left" in w.error and w.failures == 0


def test_the_writer_commits_every_50_ms_and_writes_what_is_left_when_it_ends():
    async def lecture():
        db = memory()
        w = Writer(db)
        acks = []
        task = asyncio.create_task(w.run())
        w.put(EntryRow("entry-0001", "g1", "a", ONE, 0, "p1", 10, {"text": "x"}), then=lambda: acks.append(1))
        assert count(db, "entries") == 0
        for _ in range(100):
            await asyncio.sleep(0.01)
            if acks:
                break
        assert acks == [1] and count(db, "entries") == 1 and w.commits == 1
        db.execute("ALTER TABLE entries RENAME TO elsewhere")  # a commit the database refuses does not end the loop
        db.commit()
        w.put(EntryRow("entry-0002", "g1", "a", ONE, 0, "p2", 11, {"text": "y"}))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if w.failures >= 3:
                break
        assert w.failures >= 3 and not task.done() and w.pending() == 1
        db.execute("ALTER TABLE elsewhere RENAME TO entries")
        db.commit()
        for _ in range(300):
            await asyncio.sleep(0.01)
            if not w.pending():
                break
        assert count(db, "entries") == 2 and w.commits == 2    # one commit for each time there was something
        w.put(EntryRow("entry-0003", "g1", "a", ONE, 0, "p3", 12, {"text": "the last 50 ms"}))
        task.cancel()                                          # the server ends
        with pytest.raises(asyncio.CancelledError):
            await task
        return count(db, "entries"), w.pending()
    assert asyncio.run(lecture()) == (3, 0)


def test_the_writer_waits_longer_and_longer_for_a_database_that_refuses():
    async def lecture():
        db = memory()
        w = Writer(db, every_s=0.01)
        db.execute("ALTER TABLE entries RENAME TO elsewhere")
        db.commit()
        w.put(EntryRow("entry-0001", "g1", "a", ONE, 0, "p1", 10, {"text": "x"}))
        task = asyncio.create_task(w.run())
        await asyncio.sleep(0.5)                               # 50 tries without waiting longer; with, about six
        failures = w.failures
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return failures, w.close()
    failures, left = asyncio.run(lecture())
    assert 2 <= failures <= 12 and left == 1                   # close says how many rows were not written


def test_what_is_stored_comes_back_as_it_was():
    db = memory()
    w = Writer(db)
    rows = [
        StepRow("g1", "a", ONE, 3, "paused", 12_345, "quiz", 99),
        EntryRow("entry-0001", "g1", "a", ONE, 3, "p1", 10, {"fields": ["Zürich", "liegt in", "Schweiz"]}, "n1", "hidden"),
        CheckRow("g1", "a", ONE, "n1", "ok", key="k", parts=[{"key": "zurich", "text": "Zürich", "literal": False}],
                 verdict="partial", credit=0.5, message={"code": "rows", "args": {"missing": 3}}, at=[2, 7],
                 created=11),
        CheckRow("g1", "a", ONE, "n2", "internal", aside=True, created=12),
        CheckRow("g1", "a", ONE, "n3", "invalid"),
        DetailRow("g1", "a", ONE, "k", {"columns": ["x"], "rows": [["half " + HALF]], "count": 1}, 13),
        EntryRow("entry-0001", "g2", "a", ONE, 0, "p1", 10, {"text": "another game's, with the same id"}),
    ]
    w.put(*rows)
    assert w.flush() == 7
    got = core.load(db, ["g1"])
    assert got.steps == rows[:1] and got.entries == rows[1:2] and got.checks == rows[2:5] and got.details == rows[5:6]
    assert got.checks[1].aside is True and got.checks[0].aside is False and got.checks[2].key is None
    assert core.load(db, ["g2"]).entries == rows[6:] and core.load(db, ["g1", "g2", "g3"]).entries == [rows[1], rows[6]]
    es = Entries("g1")                                         # a game takes its own entries, and none twice
    es.load(reversed(core.load(db, ["g1", "g2"]).entries))
    es.load(core.load(db, ["g1", "g2"]).entries)
    assert list(es.held) == [("a", ONE)] and len(es.held[("a", ONE)].entries) == 1 and len(es.mine(rows[0], "p1")) == 1
    assert es.held[("a", ONE)].entries["entry-0001"].input == {"fields": ["Zürich", "liegt in", "Schweiz"]}
    one = EntryRow("entry-0009", "g1", "b", ONE, 0, "p1", 10, {"text": "x"})
    es.load([one])
    es.load([one])
    assert es.counts(StepRow("g1", "b")) == {"entries": 1, "students": 1} and es.mine(StepRow("g1", "b"), "p1") == [one]


def test_the_hash_of_a_normalized_input():
    n = core.norm({"text": "SELECT 1"})
    assert len(n) == 32 and set(n) <= set("0123456789abcdef")
    assert n == core.norm({"text": "SELECT 1"}) != core.norm({"text": "SELECT 2"})
    assert core.norm({"a": 1, "b": 2}) == core.norm({"b": 2, "a": 1})                 # the keys in order
    assert core.norm({"fields": ["a", "b"]}) != core.norm({"fields": ["b", "a"]}) != core.norm({"text": "a b"})
    assert core.norm({"text": "Zürich"}) != core.norm({"text": "Zurich"})
    assert core.norm({"text": "Z" + chr(0xFC) + "rich"}) != core.norm({"text": "Z\\u00fcrich"})   # not as JSON escapes it
    assert len(core.norm({"text": "half " + HALF})) == 32      # what no store takes still has one
    assert core.norm({"text": "half " + HALF}) != core.norm({"text": "half \\ud83d"})


def test_the_hash_is_stored_and_must_not_change():
    # stored with every entry and every check: another value orphans them
    assert core.norm({"text": "SELECT 1"}) == PINNED["text"]
    assert core.norm({"fields": [":Aachen", ":liegtIn", ":NRW"]}) == PINNED["fields"]
    assert core.norm({"text": "Z" + chr(0xFC) + "rich"}) == PINNED["umlaut"]


# (the first: 32 digits of the SHA-256 of {"text":"SELECT 1"}, as any tool gives it)
PINNED = {"text": "6d164938867f94a8b35de21e468777e7", "fields": "e0d62aec2a1b8795481f91cc45f2331d",
          "umlaut": "119f9202ea3c2fc8bec75da5c0528a76"}


def test_a_restarted_server_goes_on_where_it_stopped(tmp_path):
    path = tmp_path / "texstage.sqlite"
    db = sqlite3.connect(path)
    core.create(db)
    w = Writer(db)
    p, es = Phases("g1", w.put), Entries("g1", w.put)
    p.open("q", now=0, time_ms=60_000)
    st = p.get("q")
    es.enter(st, CODE, "p1", "entry-0001", {"text": "SELECT 1"}, now=1_000)
    es.enter(st, CODE, "p2", "entry-0002", {"text": "SELECT 2"}, now=1_500)
    es.enter(st, CODE, "p1", "entry-0003", {"text": "SELECT 3"}, now=6_000)
    p.reset("q", now=7_000)
    p.open("q", now=8_000, time_ms=60_000)
    es.enter(st, CODE, "p1", "entry-0004", {"text": "SELECT 4"}, now=9_000)
    es.enter(st, CODE, "p2", "entry-0005", {"text": "SELECT 5"}, now=9_500)
    es.withdraw(st, "p2", "entry-0005")
    p.tick(9_750)
    w.flush()
    es.enter(st, CODE, "p3", "entry-0006", {"text": "never written, never acknowledged"}, now=9_900)
    db.close()                                                 # the server fails before the next commit

    db = sqlite3.connect(path)
    core.create(db)
    got = core.load(db, ["g1"])
    w = Writer(db)
    p2, es2 = Phases("g1", w.put), Entries("g1", w.put)
    changed = p2.load(got.steps, now=500_000)
    es2.load(got.entries)
    st2 = p2.get("q")
    assert changed == [st2] and (st2.phase, st2.paused_by, st2.epoch, st2.seq) == ("paused", "sleep", 1, 1)
    assert st2.time_left == 58_250                             # as it was at the last commit, 1.75 s after it opened
    assert es2.counts(st2) == {"entries": 1, "students": 1}
    assert [(e.id, e.state) for e in es2.mine(st2, "p1")] == [("entry-0004", "in")]
    assert [(e.id, e.state) for e in es2.mine(st2, "p2")] == [("entry-0005", "withdrawn")]
    assert es2.get("q", ONE, "entry-0006") is None
    refused("paused", es2.enter, st2, CODE, "p3", "entry-0006", {"text": "sent again"}, now=500_100)
    p2.resume("q", now=500_200)
    # an entry sent again after the restart is the stored one, of the earlier epoch too
    assert es2.enter(st2, CODE, "p1", "entry-0004", {"text": "SELECT 4"}, now=500_300).new is False
    assert es2.enter(st2, CODE, "p1", "entry-0001", {"text": "SELECT 1"}, now=500_300).entry.epoch == 0
    # the gap and the limit go on from what was sent before
    refused("too-fast", es2.enter, st2, Rules("code", 3, 600_000), "p1", "entry-0007", {"text": "x"}, now=500_400)
    refused("too-many", es2.enter, st2, Rules("code", 1, 0), "p1", "entry-0007", {"text": "x"}, now=500_400)
    assert es2.enter(st2, CODE, "p3", "entry-0006", {"text": "sent again"}, now=500_500).new
    assert w.flush() == 2 and count(db, "entries") == 6        # the step, paused and resumed, and the entry
    db.close()


# ------------------------------------------------------------------ the move of F1's rows
def f1_store(path) -> Store:
    """A store as F1 leaves it: a game with a query activity - revealed - and a crowd graph, open."""
    store = Store(path)
    stage = {"screen": "slide", "activity": {"current": "triples", "items": {
        "query": {"phase": "closed", "version": 9, "revealed": True, "shown": "k1", "refs": ["k1"]},
        "triples": {"phase": "open", "version": 4, "min": 2, "merges": [["node", ":aachen", ":Aachen"],
                                                                      ["label", ":liegt_in", ":liegtIn"]],
                    "hidden": [":x"], "approved": [":Aachen", ":NRW"]},
        "untouched": {"phase": "ready", "version": 0}}}}
    store.save(Session("g1", "111111", "deck", "bundle", 0, 0, stage=stage))
    store.save(Session("g2", "222222", "deck", "bundle", 0, 0, stage={}))
    c = f1.Contribution
    rows = [
        c("c00000000001", "g1", "query", "p1", 100, {"text": "SELECT 1"}, "in", "k1", "ok"),
        c("c00000000002", "g1", "query", "p2", 110, {"text": "SELECT 1"}, "in", "k1", "ok"),
        c("c00000000003", "g1", "query", "p1", 120, {"text": "SELEC"}, "replaced", "syntax", "syntax", 'near "SELEC"'),
        c("c00000000004", "g1", "query", "p3", 130, {"text": "SELECT 2"}, "in", "", "waiting"),
        c("c00000000005", "g1", "query", "p4", 140, {"text": "SELECT 3"}, "in", "internal", "internal", "the pool broke"),
        c("c00000000006", "g1", "query", "p5", 150, {"text": "SELECT 4"}, "in", "internal", "internal",
          f1.SET_ASIDE + "it ended two processes"),
        c("c00000000007", "g1", "query", "p1", 160, {"text": "SELECT x"}, "in", "error", "error", "no such column: x"),
        c("c00000000008", "g1", "query", "p6", 170, {"text": "SELECT 9"}, "withdrawn", "timeout", "timeout"),
        c("c00000000009", "g1", "triples", "p1", 200, {"fields": [":Aachen", ":liegtIn", ":NRW"]}, "in",
          ":Aachen\x1f:liegtIn\x1f:NRW"),
        c("c0000000000a", "g1", "triples", "p2", 210, {"fields": [":Aachen", ":einwohner", '"260000"']}, "hidden",
          ':Aachen\x1f:einwohner\x1f"260000"'),
        c("c0000000000b", "g2", "query", "p1", 300, {"text": "SELECT 1"}, "in", "k1", "ok"),
        c("c0000000000c", "g1", "triples", "p3", 220, {"fields": [":x", ":y", ":z"]}, "in",
          "two\x1fkeys"),                                      # not what F1 writes: keys that do not fit the fields
        c("c0000000000d", "g1", "query", "p7", 180, {"text": "SELECT 7"}, "in", "", "ok"),      # ... ok without a key
    ]
    for row in rows:
        store.save(row)
    rows[0].state = "replaced"                                 # F1 saves a changed row again: it moves to the table's end
    store.save(rows[0])
    store.save(f1.Result("g1", "query", "k1", {"columns": ["1"], "rows": [[1]], "count": 1}, 105))
    store.save(f1.Result("g2", "query", "k1", {"columns": ["1"], "rows": [[1]], "count": 1}, 305))
    store.commit()
    return store


def test_a_store_of_todays_games_loads(tmp_path):
    assert core.F1_SET_ASIDE == f1.SET_ASIDE and set(core.F1_FINAL) == set(f1.STATUSES)
    store = f1_store(tmp_path / "texstage.sqlite")
    sessions = {s.id: s.stage for s in store.load()}
    before = (count(store.db, "contributions"), count(store.db, "results"))
    made = core.move(store.db, {"g1": sessions["g1"]})
    assert made == {"steps": 3, "entries": 12, "checks": 7, "details": 1, "moderation": 7}
    assert (count(store.db, "contributions"), count(store.db, "results")) == before   # the old tables stay
    assert not store.db.in_transaction
    got = core.load(store.db, ["g1", "g2"])
    assert {e.session for e in got.entries} == {"g1"}          # the game that was not asked for is not moved

    # the entries: one step, epoch 0, the ids and the states kept, in the order they came
    query = [e for e in got.entries if e.activity == "query"]
    assert [e.id[-1] for e in query] == list("12345678d")
    assert {(e.step, e.epoch) for e in got.entries} == {(ONE, 0)}
    assert [e.state for e in query] == ["replaced", "in", "replaced", "in", "in", "in", "in", "withdrawn", "in"]
    assert query[0].input == {"text": "SELECT 1"} and query[0].norm == core.norm({"text": "SELECT 1"}) == query[1].norm

    # the checks: a status and a key per distinct input; what waited or failed for the server's reasons has none
    checks = {(c.activity, c.norm): c for c in got.checks}

    def of(text: str) -> CheckRow | None:
        return checks.get(("query", core.norm({"text": text})))
    assert (of("SELECT 1").status, of("SELECT 1").key, of("SELECT 1").created) == ("ok", "k1", 100)
    assert of("SELECT 1").form == {"text": "SELECT 1"} and of("SELEC").form == {"text": "SELEC"}    # as F1 cleaned it
    assert (of("SELEC").status, of("SELEC").key, of("SELEC").message) == ("invalid", None, None)
    assert of("SELECT 2") is None and of("SELECT 3") is None and of("SELECT 7") is None
    assert (of("SELECT 4").status, of("SELECT 4").aside) == ("internal", True)
    assert of("SELECT x").status == "error" and of("SELECT 9").status == "timeout"
    triple = checks[("triples", core.norm({"fields": [":Aachen", ":einwohner", '"260000"']}))]
    assert triple.status == "ok" and triple.key == ':Aachen\x1f:einwohner\x1f"260000"'
    assert triple.parts == [{"key": ":Aachen", "text": ":Aachen", "literal": False},
                            {"key": ":einwohner", "text": ":einwohner", "literal": False},
                            {"key": '"260000"', "text": '"260000"', "literal": True}]
    assert len(checks[("triples", core.norm({"fields": [":Aachen", ":liegtIn", ":NRW"]}))].parts) == 3
    assert triple.form == {"fields": [":Aachen", ":einwohner", '"260000"']}
    assert ("triples", core.norm({"fields": [":x", ":y", ":z"]})) not in checks       # ... nor what F1 never wrote
    assert got.details == [DetailRow("g1", "query", ONE, "k1", {"columns": ["1"], "rows": [[1]], "count": 1}, 105)]

    # the steps: each activity's phase, the revealed one revealed; the one the phones showed is the current
    steps = {st.activity: st for st in got.steps}
    assert {a: st.phase for a, st in steps.items()} == {"query": "revealed", "triples": "open", "untouched": "ready"}
    assert {a: st.seq for a, st in steps.items()} == {"query": 0, "triples": 1, "untouched": 0}
    assert all((st.step, st.epoch, st.time_left) == (ONE, 0, None) for st in got.steps)

    # the lecturer's acts: the result that was shown; the graph's minimum, merges, hidden and approved terms
    acts = [(r.n, r.activity, r.act, r.target, r.role, r.onto, r.value) for r in got.moderation]
    assert acts == [(1, "query", "show", core.gid("ok", "k1"), "", None, None),
                    (2, "triples", "min", None, "", None, 2),
                    (3, "triples", "merge", ":aachen", "node", ":Aachen", None),
                    (4, "triples", "merge", ":liegt_in", "label", ":liegtIn", None),
                    (5, "triples", "hide", ":x", "", None, None),
                    (6, "triples", "approve", ":Aachen", "", None, None),
                    (7, "triples", "approve", ":NRW", "", None, None)]
    assert all((r.step, r.off, r.undone, r.entry) == (ONE, False, False, None) for r in got.moderation)

    # ... and the core goes on with them
    p, es = Phases("g1"), Entries("g1")
    assert p.load(got.steps, now=2_000) == [] and p.current() is steps["triples"]
    p.close("triples", now=2_100)
    assert p.current() is steps["triples"]                     # closed, it is still what the phones showed
    p.open("triples", now=2_200)
    es.load(got.entries)
    assert es.counts(steps["query"]) == {"entries": 6, "students": 6}
    assert es.counts(steps["triples"]) == {"entries": 2, "students": 2}
    again = es.enter(steps["triples"], TRIPLE, "p1", "c00000000009", {"fields": ["x", "y", "z"]}, now=3_000)
    assert not again.new and again.entry.input == {"fields": [":Aachen", ":liegtIn", ":NRW"]}
    refused("duplicate", es.enter, steps["triples"], TRIPLE, "p1", "entry-0001",
            {"fields": [":Aachen", ":liegtIn", ":NRW"]}, now=3_000)
    refused("duplicate", es.enter, steps["triples"], TRIPLE, "p2", "entry-0001",        # what was hidden in F1, too
            {"fields": [":Aachen", ":einwohner", '"260000"']}, now=3_000)

    # moved once: again, nothing is made, and what the core changed since stays
    w = Writer(store.db)
    es.save = w.put
    assert es.hide(got.entries[1])
    w.flush()
    assert core.move(store.db, sessions) == {"steps": 1, "entries": 1, "checks": 1, "details": 1,
                                             "moderation": 0}              # g2 only
    assert core.move(store.db, sessions) == {"steps": 0, "entries": 0, "checks": 0, "details": 0, "moderation": 0}
    assert len(core.load(store.db, ["g1"]).moderation) == 7
    assert [e.state for e in core.load(store.db, ["g1"]).entries][1] == "hidden"
    store.close()


def test_a_store_without_f1s_tables_and_a_game_without_activities():
    db = sqlite3.connect(":memory:")
    assert core.move(db, {}) == {"steps": 0, "entries": 0, "checks": 0, "details": 0, "moderation": 0}
    stage = {"activity": {"current": "b", "items": {
        "a": {"phase": "closed", "shown": "syntax", "min": 0, "merges": [["node", ":a"], ["edge", ":a", ":b"], 7],
              "hidden": [None, ""], "approved": "x"},     # (not what F1 writes: nothing is made of it)
        "b": {"phase": "ready"}}}}
    assert core.move(db, {"g1": stage, "g2": {}, "g3": None}) == {"steps": 2, "entries": 0, "checks": 0, "details": 0,
                                                                 "moderation": 1}
    (shown,) = core.load(db, ["g1"]).moderation                # F1's word for a text that does not parse
    assert (shown.act, shown.target, shown.n) == ("show", core.gid("invalid"), 1)
    steps = {st.activity: st for st in core.load(db, ["g1", "g2", "g3"]).steps}
    assert (steps["a"].phase, steps["a"].seq, steps["b"].phase, steps["b"].seq) == ("closed", 0, "ready", 1)


def test_what_f1_never_wrote_makes_no_act_and_ends_no_move():
    db = sqlite3.connect(":memory:")
    items = {
        "round": {"min": 3, "merges": [["node", "a", "b"], ["node", "b", "c"], ["node", "c", "a"], ["node", "d", "d"],
                                       ["label", "c", "a"]]},           # c into a would lead back to c; d into itself
        "big": {"min": 5000, "hidden": ["x", "x", "y"], "approved": ["x", "x"]},
        "huge": {"min": 10 ** 30},
        "decks": {"min": 2}, "ones": {"min": 1}, "true": {"min": True},
        "list": [1, 2], "text": "x", "number": 5, "none": None}
    stage = {"activity": {"current": "round", "items": items}}
    decks = {"g1": {"decks": {"min": 2}, "round": {"min": 2}, "big": "no item", "ones": {}, "true": {"min": 5}}}
    made = core.move(db, {"g1": stage, "g2": {"activity": "no state"}, "g3": {"activity": {"items": ["a", 1]}},
                          "g4": 7}, decks)
    assert made == {"steps": 10, "entries": 0, "checks": 0, "details": 0, "moderation": 7}
    acts = [(r.n, r.activity, r.act, r.target, r.role, r.onto, r.value) for r in core.load(db, ["g1"]).moderation]
    assert acts == [(1, "big", "hide", "x", "", None, None), (2, "big", "hide", "y", "", None, None),
                    (3, "big", "approve", "x", "", None, None),
                    (4, "round", "min", None, "", None, 3),            # not the deck's: the lecturer's
                    (5, "round", "merge", "a", "node", "b", None), (6, "round", "merge", "b", "node", "c", None),
                    (7, "round", "merge", "c", "label", "a", None)]
    steps = {st.activity: st.phase for st in core.load(db, ["g1"]).steps}
    assert steps == dict.fromkeys(items, "ready")              # each has its step, whatever its state was
    # without the deck's items a minimum is moved as it is: it may be the lecturer's
    other = sqlite3.connect(":memory:")
    assert core.move(other, {"g1": {"activity": {"items": {"a": {"min": 2}}}}})["moderation"] == 1


def test_an_activity_moved_later_numbers_its_acts_after_the_games():
    db = sqlite3.connect(":memory:")
    core.create(db)
    w = Writer(db)
    w.put(StepRow("g1", "a"), core.ModerationRow("g1", 1, "a", ONE, "hide", target="t"),
          core.ModerationRow("g1", 5, "a", ONE, "min", value=2))
    w.flush()
    stage = {"activity": {"items": {"a": {"hidden": ["never moved: a has its step"]}, "b": {"hidden": ["u", "v"]}}}}
    assert core.move(db, {"g1": stage})["moderation"] == 2
    assert [(r.n, r.activity, r.target) for r in core.load(db, ["g1"]).moderation] == [
        (1, "a", "t"), (5, "a", None), (6, "b", "u"), (7, "b", "v")]


def test_a_move_that_fails_leaves_nothing_half_moved(tmp_path):
    store = f1_store(tmp_path / "texstage.sqlite")
    core.create(store.db)
    store.db.execute("DROP TABLE details")                     # a table that takes no detail: the last rows fail
    store.db.execute("CREATE TABLE details (session, activity, step, key, detail NOT NULL CHECK (detail = 'never'), "
                     "created, PRIMARY KEY (session, activity, step, key))")
    store.commit()
    stage = store.load()[0].stage
    with pytest.raises(sqlite3.Error):
        core.move(store.db, {"g1": stage})
    assert count(store.db, "entries") == 0 and count(store.db, "steps") == 0 and not store.db.in_transaction
    store.close()
