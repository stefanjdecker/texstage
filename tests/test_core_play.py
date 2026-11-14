# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""One game's core as one (texstage/activities/play.py; docs/architecture/activity-framework-plan-f2.md,
package 6): an entry's way from the phone to its group - through the kinds' own normalize and check, as a
worker of the pool runs them, without a process -, the lecturer's moves and acts, what the phones and the
windows get, and a restart."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KINDS = ROOT / "kinds"
if not any(KINDS.glob("*/src")):                       # texstage's source archive has its tests, not the kinds
    pytest.skip("the kinds' packages are not here", allow_module_level=True)
for src in sorted(KINDS.glob("*/src")):
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

from texstage.activities import registry  # noqa: E402
from texstage.activities.checks import Leave, Normalize, Run  # noqa: E402
from texstage.activities.phases import Refused  # noqa: E402
from texstage.activities.play import Part, Play, kind_of  # noqa: E402
from texstage.activities.store import CheckRow, DetailRow, EntryRow, ModerationRow, StepRow, gid  # noqa: E402
from texstage.server import worker  # noqa: E402

try:
    registry.kind("sql-query"), registry.kind("triples")
except LookupError:
    pytest.skip("the kinds are not installed: pip install --no-deps -e kinds/...", allow_module_level=True)

SEED = "CREATE TABLE t (x);\nINSERT INTO t VALUES (1), (2), (3);\n"
SQL = {"input": "code", "engine": "sql", "seed": "data/t.sql", "limit": 3, "gap": 0, "prompt": "All of t",
       "tokens": ["*"]}
SQL_KEYS = {"reference": ["SELECT x FROM t"]}
GRAPH = {"input": "tuple", "fields": ["Subject", "Predicate", "Object"], "suggest": [":Kant"], "terms": "exact",
         "min": 1, "gap": 0, "limit": 10}
FILES = {"data/t.sql": SEED.encode()}


class Desk:
    """What the server's type and the pool do around a Play, here in one process: the rows it saves kept as
    the tables keep them, its jobs run by the kinds as a worker runs them - at once, or when let go."""

    def __init__(self, session: str = "g1", **items):
        items = items or {"q": SQL, "g": GRAPH}
        self.parts = {name: Part.of(name, item, SQL_KEYS if item.get("input") == "code" else {})
                      for name, item in items.items()}
        self.rows: dict[int, object] = {}
        self.jobs: list = []
        self.left: list[Leave] = []
        self.hold = False
        self.now = 1000
        self.session = session
        self.play = Play(session, save=self.save, ask=self.take)
        self.engines = {}
        for name, part in self.parts.items():
            of = worker._OfKind(part.kind.NAME)
            state = of.load({"item": part.item, "keys": part.keys, "files": FILES})
            rows, outcomes = None, []
            for text in part.keys.get("reference", ()):
                outcome, found = of.check(state, None, text, "en", 1.0, reference=True)
                rows = found if rows is None and outcome["status"] == "ok" else rows
                outcomes.append(outcome)
            self.engines[name] = (of, state, rows)
            self.play.refer(name, outcomes)

    def save(self, *rows) -> None:
        for row in rows:
            self.rows[id(row)] = row

    def take(self, jobs: list) -> None:
        self.jobs += jobs
        if not self.hold:
            self.run()

    def run(self, only=None) -> None:
        """The jobs that wait, in their order - and those their answers ask for."""
        while True:
            i = next((i for i, job in enumerate(self.jobs) if only is None or isinstance(job, only)), None)
            if i is None:
                return
            job = self.jobs.pop(i)
            part = self.parts[job.activity]
            if isinstance(job, Normalize):
                answer = worker._normalize(part.kind.NAME, part.item, part.keys, "en", job.input)
                self.play.normalized(job.activity, job.step, job.raw, answer, now=self.now)
            elif isinstance(job, Run):
                of, state, rows = self.engines[job.activity]
                outcome, _ = of.check(state, rows, json.dumps(job.input), "en", 1.0)
                self.play.checked(job.activity, job.step, job.norm, outcome, now=self.now)
            else:
                self.left.append(job)

    def send(self, player: str, sent, activity: str = "q", eid: str | None = None, **more):
        self.now += 10
        sent = {"text": sent} if isinstance(sent, str) else {"fields": list(sent)}
        eid = eid or f"entry-{len(self.rows):05d}-{self.now}"
        return self.play.enter(self.parts[activity], player, eid, sent, now=self.now, **more).entry

    def move(self, name: str, activity: str = "q", **more):
        self.now += 10
        return self.play.move(name, activity, now=self.now, **more)

    def mine(self, player: str, activity: str = "q") -> list[dict]:
        return self.play.mine(self.parts[activity], player)["entries"]

    def groups(self, window: str = "display", activity: str = "q") -> list[tuple]:
        return [(g["example"]["text"] if g["example"] else None, g["n"])
                for g in self.play.picture(self.parts[activity], window)["groups"]]

    def stored(self, cls) -> list:
        return [r for r in self.rows.values() if isinstance(r, cls)]

    def again(self) -> Desk:
        """The server starts again: another Play of the same game, from the rows as they were saved."""
        new = Desk(self.session, **{name: part.item for name, part in self.parts.items()})
        new.now, new.hold = self.now + 1000, True
        new.play.load(self.stored(StepRow), self.stored(EntryRow), self.stored(CheckRow), self.stored(DetailRow),
                      sorted(self.stored(ModerationRow), key=lambda r: r.n), now=new.now)
        new.rows = dict(self.rows)
        return new


def refused(code: str, call, *args, **kwargs) -> Refused:
    with pytest.raises(Refused) as e:
        call(*args, **kwargs)
    assert e.value.code == code, f"{e.value.code}: {e.value}"
    return e.value


# ------------------------------------------------------------------ an entry's way
def test_an_entry_is_normalized_checked_and_counted():
    d = Desk()
    d.move("open")
    d.hold = True
    e = d.send("p1", "SELECT x FROM t -- by Max")
    assert [type(j) for j in d.jobs] == [Normalize] and d.mine("p1")[0] == {
        "id": e.id, "input": {"text": "SELECT x FROM t -- by Max"}, "state": "in", "check": "waiting"}
    d.run(only=Normalize)                                   # ... its form is known now, its check asked for
    assert [(type(j), j.input, j.owner) for j in d.jobs] == [(Run, {"text": "SELECT x FROM t"}, "p1")]
    assert d.play.picture(d.parts["q"], "stage")["waiting"] == 1 and d.groups() == []
    d.run()
    mine = d.mine("p1")[0]
    assert (mine["check"], mine["status"]) == ("checked", "ok") and "verdict" not in mine      # feedback=status
    assert d.groups() == [("SELECT x FROM t", 1)]            # shown without its comment
    d.hold = False
    d.send("p2", "select x from t")                         # another text, the same result: one group
    d.send("p3", "SELECT x FROM t")                         # a text the step knows: no job at all
    d.send("p4", "SELEC x")
    assert d.groups("stage") == [("SELECT x FROM t", 3), ("SELEC x", 1)]
    assert len(d.stored(CheckRow)) == 3 and len(d.stored(EntryRow)) == 4
    wrong = d.mine("p4")[0]
    assert (wrong["status"], wrong["message"]["code"]) == ("invalid", "engine") and "at" not in wrong


def test_the_latest_entry_replaces_the_earlier_and_its_check_leaves_the_queue():
    d = Desk()
    d.move("open")
    d.hold = True
    first = d.send("p1", "SELECT 1")
    d.run(only=Normalize)
    d.send("p1", "SELECT 2")
    assert [type(j) for j in d.jobs] == [Run, Leave, Normalize] and d.jobs[1].norm == first.norm
    d.run()
    assert [(m["input"]["text"], m["state"]) for m in d.mine("p1")] == [("SELECT 2", "in"), ("SELECT 1", "replaced")]
    assert d.groups() == [("SELECT 2", 1)] and d.play.mine(d.parts["q"], "p1")["used"] == 2
    e = d.send("p1", "SELECT 3")
    d.run()
    d.play.withdraw(d.parts["q"], "p1", e.id, now=d.now)
    assert d.groups() == [] and [m["input"]["text"] for m in d.mine("p1")] == ["SELECT 2", "SELECT 1"]
    refused("too-many", d.send, "p1", "SELECT 4")            # three were sent: the limit is of what was sent


def test_an_entry_taken_back_wants_no_check_any_more():
    d = Desk()
    d.move("open")
    d.hold = True
    e = d.send("p1", "SELECT 1")
    d.run(only=Normalize)                                   # its check is asked for ...
    assert [type(j) for j in d.jobs] == [Run]
    d.play.withdraw(d.parts["q"], "p1", e.id, now=d.now)    # ... and leaves the queue with it
    assert [(type(j), j.norm) for j in d.jobs] == [(Run, e.norm), (Leave, e.norm)]
    assert d.mine("p1") == [] and d.play.picture(d.parts["q"], "stage")["waiting"] == 0


def test_an_entry_sent_again_while_it_waits_asks_for_nothing_more():
    d = Desk()
    d.move("open")
    d.hold = True
    e = d.send("p1", "SELECT 1", eid="entry-of-p1-0001")
    jobs = list(d.jobs)
    assert d.send("p1", "SELECT 1", eid="entry-of-p1-0001") is e and d.jobs == jobs
    d.run()
    assert d.send("p1", "SELECT 1", eid="entry-of-p1-0001") is e and d.jobs == []
    assert d.groups() == [("SELECT 1", 1)] and d.play.mine(d.parts["q"], "p1")["used"] == 1


def test_an_entry_sent_again_is_the_one_that_is_there():
    d = Desk()
    d.move("open")
    e = d.send("p1", "SELECT 1", eid="entry-of-p1-0001")
    d.move("close")
    again = d.send("p1", "SELECT 1", eid="entry-of-p1-0001")     # the phone lost its connection, the step closed
    assert again is e and len(d.stored(EntryRow)) == 1 and d.jobs == []
    refused("closed", d.send, "p1", "SELECT 2")


def test_what_cannot_be_normalized_is_not_the_students():
    d = Desk()
    d.move("open")
    d.hold = True
    e = d.send("p1", "SELECT 1")
    job = d.jobs.pop()
    assert d.play.normalized("q", "main", job.raw, {"error": "the process ended"}, now=d.now) == [e]
    assert d.mine("p1")[0]["check"] == "unchecked" and d.play.picture(d.parts["q"], "stage")["unchecked"] == 1
    d.hold = False
    d.send("p2", "SELECT 1")                                # the same text again: asked again, and both have it
    assert [m["check"] for m in d.mine("p1")] == ["checked"] and d.groups() == [("SELECT 1", 2)]


def test_a_check_that_is_internal_tells_the_phone_nothing_of_it():
    d = Desk()
    d.move("open")
    d.hold = True
    e = d.send("p1", "SELECT 1")
    d.run(only=Normalize)
    d.play.checked("q", "main", e.norm, {"status": "internal", "error": "set aside: it failed twice", "set_aside": True},
                   now=d.now)
    assert d.mine("p1") == [{"id": e.id, "input": {"text": "SELECT 1"}, "state": "in", "check": "unchecked"}]


# ------------------------------------------------------------------ feedback, and the reveal
@pytest.mark.parametrize("feedback, before, after", [
    ("none", {"check": "received"}, {"check": "checked", "status": "ok", "verdict": "correct"}),
    ("status", {"check": "checked", "status": "ok"}, {"check": "checked", "status": "ok", "verdict": "correct"}),
    ("verdict", {"check": "checked", "status": "ok", "verdict": "correct"}, None),
    ("full", {"check": "checked", "status": "ok", "verdict": "correct",
              "compared": {"common": 3, "missing": 0, "extra": 0}}, None),
])
def test_a_phone_learns_what_feedback_allows_and_its_verdict_at_the_reveal(feedback, before, after):
    d = Desk(q=SQL | {"feedback": feedback})
    d.move("open")
    d.send("p1", "select x from t")
    d.send("p2", "SELECT 1")

    def told(player: str) -> dict:
        return {k: v for k, v in d.mine(player)[0].items() if k not in ("id", "input", "state")}
    assert told("p1") == before
    if feedback in ("verdict", "full"):
        assert told("p2")["verdict"] == "incorrect"
    d.move("reveal")
    assert told("p1") == (after or before) and told("p2")["verdict"] == "incorrect"


def test_feedback_is_one_of_the_four():
    with pytest.raises(ValueError, match="feedback: one of none, status, verdict, full"):
        Part.of("q", SQL | {"feedback": "all"}, SQL_KEYS)


# ------------------------------------------------------------------ the steps
def test_a_move_tells_the_pictures_and_a_refusal_what_it_changed():
    d = Desk()
    part = d.parts["q"]
    assert d.play.told("q", d.now) is None and d.play.step("q").phase == "ready"      # (no step moved yet)
    rows = d.move("open", time_ms=1000)
    assert [(r.phase, r.time_left) for r in rows] == [("open", 1000)]
    first = d.play.told("q", d.now)
    assert first is not None and d.play.told("q", d.now + 10) is None                 # told: nothing new
    d.send("p1", "SELECT 1")
    assert d.play.told("q", d.now + 100) is None                                      # ... less than 250 ms ago
    assert d.play.told("q", d.now + 300)["version"] != first["version"]
    d.now += 5000                                           # the time ran out; the lecturer presses Pause
    e = refused("closed", d.play.move, "pause", "q", now=d.now)
    assert [(r.activity, r.phase) for r in e.changed] == [("q", "closed")]
    assert d.play.picture(part)["phase"] == "closed"        # the picture knows, though the move was refused
    refused("closed", d.send, "p2", "SELECT 2")


def test_an_entry_is_taken_in_the_step_as_it_is_after_a_tick():
    d = Desk()
    d.move("open", time_ms=1000)
    d.now += 2000
    refused("closed", d.send, "p1", "SELECT 1")             # nobody ticked since: the entry's own tick closes it
    assert d.play.step("q").phase == "closed"


def test_the_steps_own_part_is_the_same_for_every_phone():
    d = Desk()
    d.move("open", time_ms=60_000)
    part = d.play.step_part(d.parts["q"])
    assert part == {"activity": "q", "step": "main", "epoch": 0, "phase": "open", "kind": "sql-query", "input": "code",
                    "limit": 3, "counts": "latest", "feedback": "status", "time": 60_000, "prompt": "All of t",
                    "tokens": ["*"], "engine": "sql", "gap": 0}             # (the deck's gap: a phone sends a tap again after it)
    assert "seed" not in part and "reference" not in str(part)
    d.move("open", "g")
    for player, triple in [("p1", [":Kant", ":knows", ":Hume"]), ("p2", [":Hume", ":knows", ":Smith"])]:
        d.send(player, triple, "g")
    graph = d.play.step_part(d.parts["g"])
    assert graph["suggest"] == [":Kant", ":Hume", ":Smith"] and graph["fields"] == GRAPH["fields"]
    assert (graph["kind"], graph["input"], graph["counts"]) == ("triples", "fields", "all")


# ------------------------------------------------------------------ the lecturer's acts
def test_an_act_changes_the_groups_and_tells_no_phone():
    d = Desk()
    d.move("open")
    d.send("p1", "SELECT 1")
    d.send("p2", "SELECT 1")
    d.send("p3", "SELECT 2")
    check = d.play.checks.of(d.play.entries.mine(d.play.step("q"), "p1")[0])
    done = d.play.act(d.parts["q"], "hide", target=gid("ok", check.key), now=d.now)
    assert done.row.n == 1 and not done.entries             # the group is not shown; its entries are as they were
    assert d.groups() == [("SELECT 2", 1)] and d.groups("stage")[0] == ("SELECT 1", 2)
    d.play.undo(d.parts["q"], now=d.now)
    assert d.groups() == [("SELECT 1", 2), ("SELECT 2", 1)]
    theirs = d.play.entries.mine(d.play.step("q"), "p3")[0]
    done = d.play.act(d.parts["q"], "hide", entry=theirs.id, now=d.now)
    assert [e.state for e in done.entries] == ["hidden"] and d.groups("stage") == [("SELECT 1", 2)]
    assert d.mine("p3")[0]["state"] == "in"                 # what the lecturer hid is the student's as before
    d.play.undo(d.parts["q"], now=d.now)
    assert d.groups() == [("SELECT 1", 2), ("SELECT 2", 1)]


def test_a_blocked_student_sends_no_more():
    d = Desk()
    d.move("open")
    e = d.send("p1", "SELECT 1")
    done = d.play.act(d.parts["q"], "block", entry=e.id, now=d.now)
    assert done.player == "p1" and d.play.blocked("p1") and d.play.mine(d.parts["q"], "p1")["blocked"]
    refused("blocked", d.send, "p1", "SELECT 2")
    refused("blocked", d.send, "p2", "SELECT 2", blocked=True)       # ... nor one the engine has muted
    d.play.act(d.parts["q"], "block", entry=e.id, off=True, now=d.now)
    d.send("p1", "SELECT 2")


def test_merged_terms_are_one_node():
    d = Desk()
    d.move("open", "g")
    d.send("p1", [":Kant", ":knows", ":Hume"], "g")
    d.send("p2", [":kant", ":knows", ":Hume"], "g")
    part = d.parts["g"]
    assert len(d.play.picture(part)["nodes"]) == 3
    d.play.act(part, "merge", target=":kant", onto=":Kant", role="node", step="main", now=d.now)
    picture = d.play.picture(part)
    assert sorted(n["label"] for n in picture["nodes"]) == [":Hume", ":Kant"] and picture["edges"][0]["n"] == 2
    assert d.play.layout(part, {":Kant": [0.2, 0.3]}) and d.play.told("g", d.now + 300)["layout"] == 1


# ------------------------------------------------------------------ a restart
def test_a_restarted_game_is_as_it_was_and_asks_for_what_was_unchecked():
    d = Desk()
    d.move("open", time_ms=60_000)
    d.move("open", "g")                                     # (one activity at a time: q is closed by it)
    d.move("open", "q", time_ms=60_000)
    for player, text in [("p1", "SELECT x FROM t"), ("p2", "select x from t"), ("p3", "SELEC x")]:
        d.send(player, text)
    d.hold = True
    waiting = d.send("p4", "SELECT 4")                      # ... and one that the server never checked
    hidden = d.play.entries.mine(d.play.step("q"), "p3")[0]
    d.play.act(d.parts["q"], "hide", entry=hidden.id, now=d.now)
    before = {w: d.play.picture(d.parts["q"], w) for w in ("display", "stage")}
    new = d.again()
    step = new.play.step("q")
    assert (step.phase, step.paused_by) == ("paused", "sleep")      # the server was away: its time waits
    for window in ("display", "stage"):
        after = new.play.picture(new.parts["q"], window)
        assert {k: after[k] for k in ("groups", "entries", "students")} == {
            k: before[window][k] for k in ("groups", "entries", "students")}, window
    assert new.jobs == [] and new.mine("p4")[0]["check"] == "waiting"
    new.play.again()
    assert [(type(j), j.input) for j in new.jobs] == [(Normalize, {"text": "SELECT 4"})]
    new.hold = False
    new.run()
    assert new.mine("p4")[0]["status"] == "ok" and new.play.entries.get("q", "main", waiting.id).norm
    assert "verdict" not in new.mine("p1")[0]               # (feedback=status: not before the reveal)
    new.play.move("resume", "q", now=new.now)
    new.play.move("reveal", "q", now=new.now)
    assert new.mine("p1")[0]["verdict"] == "correct" and new.mine("p4")[0]["verdict"] == "incorrect"
    new.play.undo(new.parts["q"], now=new.now)              # the act of before the restart
    assert ("SELEC x", 1) in new.groups()


# ------------------------------------------------------------------ a deck's item and its kind
def test_an_item_of_a_deck_built_before_kinds_were_named_has_the_kind_of_its_input_and_engine():
    assert kind_of({"input": "tuple", "fields": ["a", "b"]}).NAME == "triples"
    assert kind_of({"input": "code", "engine": "sql"}).NAME == "sql-query"
    assert kind_of({"input": "code", "engine": "turtle"}).NAME == "turtle-graph"
    assert kind_of({"kind": "sparql-query", "input": "code", "engine": "sql"}).NAME == "sparql-query"    # named: that one
    for item in ({"input": "code", "engine": "prolog"}, {"input": "sketch"}, {}, {"kind": "no-such-kind"}):
        with pytest.raises(LookupError):
            kind_of(item)
