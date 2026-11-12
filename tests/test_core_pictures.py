# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The core's reductions, pictures and moderation (texstage/activities/reduce.py, views.py, moderation.py;
docs/architecture/activity-framework-plan-f2.md, package 5): the groups - counted by students, the largest
first, shown by their most frequent normalized text -, today's crowd graph, the tally; what the projector
and the panel get, and when; the lecturer's acts, each a row that can be undone and that a restarted
server has again; and the move of what F1 kept of them."""
from __future__ import annotations

import random
import sqlite3

import pytest
from texstage_kinds_rdf import Triples

from texstage.activities import moderation as moderation_module
from texstage.activities import reduce as reduce_module
from texstage.activities import store as core
from texstage.activities import views as views_module
from texstage.activities.checks import Checks, Leave, Normalize, Run
from texstage.activities.entries import Entries, Rules
from texstage.activities.kind import Entry, Step, Unfit
from texstage.activities.moderation import Moderation
from texstage.activities.phases import Phases, Refused
from texstage.activities.reduce import Mods, Reduced, Setup, role
from texstage.activities.store import CheckRow, EntryRow, ModerationRow, StepRow, Writer, gid
from texstage.activities.views import Pictures
from texstage.server.store import Store  # noqa: F401 - before the activity type: the server's types come first

from texstage.server import activity as f1  # isort: skip

A, S = "a", "main"
D1 = {"columns": ["n"], "rows": [[1]], "count": 1}
CODE = Setup("groups", Rules("code", 5, 0), references=("SELECT 1",))
TRIPLES = Triples()


def refused(code: str, call, *args, **kwargs) -> Refused:
    with pytest.raises(Refused) as e:
        call(*args, **kwargs)
    assert e.value.code == code, f"{e.value.code}: {e.value}"
    return e.value


def query(form: dict) -> dict:
    """What a kind of queries would say of a normalized text here."""
    text = form["text"]
    if text in ("SELECT 1", "SELECT 1+0"):
        return {"status": "ok", "key": "k1", "detail": D1}
    if text.startswith("SELEC "):
        return {"status": "invalid", "message": {"code": "at", "args": {"line": 1, "column": 1, "message": text}},
                "at": [1, 1]}
    if text == "BOOM":
        return {"status": "internal", "set_aside": True}
    if text == "LOOP":
        return {"status": "timeout"}
    if text.startswith("JUDGED "):
        return {"status": "ok", "key": text, "verdict": "partial", "credit": 0.5}
    return {"status": "ok", "key": "k:" + text}


def clean(sent: dict) -> dict:
    """... and its normalize: spaces as one, no case, no comment - and nothing at all is refused."""
    text = " ".join(sent["text"].split("--")[0].split()).upper()
    if not text:
        raise Unfit("nothing but a comment", "text")
    return {"text": text}


def triple(item: dict):
    step = Step(item)

    def normalize(sent: dict) -> dict:
        return {"fields": list(TRIPLES.normalize(step, Entry(fields=tuple(sent["fields"]))).fields)}

    def check(form: dict) -> dict:
        return TRIPLES.check(None, step, Entry(fields=tuple(form["fields"]))).sent()
    return normalize, check


class Game:
    """One game's core, as package 6 will wire it: an entry comes, is normalized and checked, and
    everything that changed is told to the reductions."""

    def __init__(self, setup: Setup = CODE, normalize=clean, check=query, save=None, session: str = "g1"):
        self.setup, self.normalize, self.check = setup, normalize, check
        save = save or (lambda *rows: None)
        self.phases, self.entries, self.checks = Phases(session, save), Entries(session, save), Checks(session, save)
        self.reduced = Reduced(session, self.entries, self.checks)
        self.moderation = Moderation(session, self.entries, self.checks, self.reduced, save)
        self.pictures = Pictures(session, self.entries, self.checks, self.reduced, self.moderation)
        self.now, self.n, self.hold, self.held, self.jobs = 1000, 0, False, [], []
        self.pictures.moved(*self.phases.open(A, now=self.now))
        self.st = self.phases.get(A)

    def send(self, player: str, sent, eid: str | None = None) -> EntryRow:
        self.now += 10
        self.n += 1
        sent = {"text": sent} if isinstance(sent, str) else {"fields": list(sent)} if isinstance(sent, (list, tuple)) \
            else sent
        got = self.entries.enter(self.st, self.setup.rules, player, eid or f"entry-{self.n:04d}", sent, now=self.now)
        changed = [got.entry, *got.replaced]
        for old in got.replaced:
            self.jobs += self.checks.left(old)
        jobs, _ = self.checks.entered(got.entry)
        self.work(jobs, changed)
        self.reduced.touch(self.st, *changed)
        return got.entry

    def work(self, jobs, changed: list) -> None:
        for job in jobs:
            self.jobs.append(job)
            if isinstance(job, Normalize):
                try:
                    more, es = self.checks.normalized(A, S, job.raw, self.normalize(job.input), now=self.now)
                except Unfit as e:
                    more, es = self.checks.normalized(A, S, job.raw, refused=e.code, now=self.now)
                changed += es
                self.work(more, changed)
            elif isinstance(job, Run) and self.hold:
                self.held.append(job)
            elif isinstance(job, Run):
                changed += self.checks.checked(A, S, job.norm, self.check(job.input), now=self.now)

    def release(self, outcome: dict | None = None) -> None:
        held, self.held = self.held, []
        for job in held:
            self.reduced.touch(self.st, *self.checks.checked(A, S, job.norm, outcome or self.check(job.input),
                                                             now=self.now))

    def withdraw(self, e: EntryRow) -> None:
        self.entries.withdraw(self.st, e.player, e.id)
        self.jobs += self.checks.left(e)
        self.reduced.touch(self.st, e)

    def move(self, name: str, **more) -> None:
        self.now += 10
        self.pictures.moved(*getattr(self.phases, name)(A, now=self.now, **more))

    def act(self, act: str, **more):
        self.now += 10
        return self.moderation.act(self.st, self.setup, act, now=self.now, **more)

    def undo(self, n: int | None = None):
        return self.moderation.undo(self.st, self.setup, n, now=self.now)

    def picture(self, window: str = "display") -> dict:
        return self.pictures.picture(self.st, self.setup, window)

    def groups(self, window: str = "display") -> list[tuple]:
        return [(g["example"]["text"] if g["example"] else None, g["n"]) for g in self.picture(window)["groups"]]


def crowd(fields=("s", "p", "o"), terms: str = "exact", review: bool = False, least: int = 1, **more) -> Game:
    item = {"fields": list(fields), "min": least, "terms": terms} | ({"review": True} if review else {})
    setup = Setup("crowd", Rules("fields", 50, 0, "all", len(fields)), min=least, review=review)
    game = Game(setup, *triple(item), **more)
    game.item = {"input": "tuple"} | item
    return game


# ------------------------------------------------------------------ groups
def test_groups_are_counted_by_students_the_largest_first():
    g = Game()
    for player, text in [("p1", "select 1"), ("p2", "SELECT   1"), ("p3", "select 1+0"), ("p4", "select 2"),
                         ("p5", "select 2"), ("p6", "selec t"), ("p1", "select 3")]:
        g.send(player, text)
    pic = g.picture()
    assert (pic["students"], pic["entries"], pic["waiting"], pic["kind"], pic["reduction"]) == (6, 6, 0, "groups", "groups")
    # p1's latest counts: the first of theirs left its group
    # ... and among as many students, what is a result comes before what is none
    assert g.groups() == [("SELECT 1", 2), ("SELECT 2", 2), ("SELECT 3", 1), ("SELEC T", 1)]
    first = pic["groups"][0]
    assert first == {"id": gid("ok", "k1"), "status": "ok", "n": 2, "example": {"text": "SELECT 1"},
                     "reference": False, "detail": D1}
    assert pic["groups"][3]["status"] == "invalid" and pic["groups"][3]["id"] == gid("invalid")
    assert "detail" not in pic["groups"][1] and pic["others"] == 0 and pic["shown"] is None
    # with counts=all a student with two entries in one group counts once
    both = Game(Setup("groups", Rules("code", 5, 0, "all")))
    for player, text in [("p1", "select 1"), ("p1", "select 1+0"), ("p2", "select 1")]:
        both.send(player, text)
    assert both.groups() == [("SELECT 1", 2)] and both.picture()["entries"] == 3


def test_a_group_is_shown_by_its_most_frequent_text_in_normalized_form():
    g = Game()
    g.send("p1", "select 1+0  -- Ada was here")
    g.send("p2", "select 1")
    g.send("p3", "select  1")
    assert g.groups() == [("SELECT 1", 3)]                      # most have it so; never a text as it was typed
    assert "Ada" not in str(g.picture("stage")) and "Ada" not in str(g.picture())
    g.withdraw(g.entries.get(A, S, "entry-0003"))
    assert g.groups() == [("SELECT 1+0", 2)]                    # as many of each: the one that came first
    g.send("p4", "select 1")
    assert g.groups() == [("SELECT 1", 3)]
    # the panel has an entry of the group, for its buttons: the first with that text
    assert g.picture("stage")["groups"][0]["entry"] == "entry-0002"
    assert "entry" not in g.picture()["groups"][0]


def test_what_normalize_refused_has_no_text_to_show():
    g = Game()
    g.send("p1", "-- only a comment, with a name")
    g.send("p2", "  -- another")
    assert g.groups() == [(None, 2)] and g.picture()["groups"][0]["status"] == "invalid"
    stage = g.picture("stage")["groups"][0]
    assert stage["example"] is None and stage["entry"] == "entry-0001" and stage["messages"] == [{"code": "text", "args": {}}]
    g.send("p3", "selec t")                                    # the kind's own invalid: its form is what shows
    assert g.groups() == [("SELEC T", 3)]
    assert len(g.picture("stage")["groups"][0]["messages"]) == 2


def test_an_entry_counts_while_it_is_in_and_has_a_check():
    g = Game()
    g.hold = True
    e1 = g.send("p1", "select 1")
    pic = g.picture("stage")
    assert pic["groups"] == [] and (pic["entries"], pic["waiting"], pic["unchecked"]) == (1, 1, 0)
    g.release()
    assert g.groups() == [("SELECT 1", 1)] and g.picture("stage")["waiting"] == 0
    g.hold = False
    e2 = g.send("p2", "select 1")
    assert g.groups() == [("SELECT 1", 2)]
    assert g.reduced.touch(g.st, e1, e2) is False               # told again: nothing is counted twice
    assert g.groups() == [("SELECT 1", 2)]
    g.withdraw(e2)
    assert g.groups() == [("SELECT 1", 1)]
    g.entries.hide(e1)
    assert g.reduced.touch(g.st, e1) and g.groups() == [] and g.picture("stage")["hidden"] == 1
    g.entries.show(e1, CODE.rules)
    g.reduced.touch(g.st, e1)
    assert g.groups() == [("SELECT 1", 1)] and g.picture("stage")["hidden"] == 0
    with pytest.raises(ValueError):
        g.reduced.touch(g.st, EntryRow("entry-9999", "g1", "another", S, 0, "p1", 1, {"text": "x"}))
    # what could not be checked is in no group, and the panel counts it
    g.hold = True
    g.send("p3", "select 5")
    g.release({"status": "internal"})
    pic = g.picture("stage")
    assert (pic["waiting"], pic["unchecked"]) == (0, 1) and g.groups("stage") == [("SELECT 1", 1)]


def test_a_text_that_was_set_aside_is_the_panels_alone():
    g = Game()
    g.send("p1", "boom")
    g.send("p2", "select 1")
    assert g.groups() == [("SELECT 1", 1)]
    stage = g.picture("stage")
    assert [(x["status"], x["n"]) for x in stage["groups"]] == [("ok", 1), ("internal", 1)]
    assert "verdict" not in stage["groups"][1]                  # never graded


def test_a_reset_starts_the_groups_anew():
    g = Game()
    g.send("p1", "select 1")
    g.send("p2", "select 2")
    before = g.picture()["version"]
    g.move("reset")
    g.move("open")
    pic = g.picture()
    assert pic["groups"] == [] and pic["epoch"] == 1 and pic["version"] > before and pic["entries"] == 0
    g.send("p1", "select 2")
    assert g.groups() == [("SELECT 2", 1)]
    old = g.entries.get(A, S, "entry-0001")
    assert g.reduced.touch(g.st, old) is False                  # an entry of the earlier epoch counts no more


def test_the_projector_shows_eight_groups_the_panel_fifty(monkeypatch):
    monkeypatch.setattr(reduce_module, "GROUPS_LISTED", 12)
    g = Game()
    for i in range(15):
        g.send(f"p{i}", f"select {i + 10}")
    g.send("q1", "select 10")
    display, stage = g.picture(), g.picture("stage")
    assert len(display["groups"]) == reduce_module.GROUPS_SHOWN == 8 and display["others"] == 7
    assert len(stage["groups"]) == 12 and stage["others"] == 3
    assert display["groups"][0]["n"] == 2 and [x["n"] for x in display["groups"][1:]] == [1] * 7
    assert [x["example"]["text"] for x in display["groups"][1:3]] == ["SELECT 11", "SELECT 12"]     # then by key


def test_a_tally_is_in_the_decks_order_with_what_nobody_chose():
    setup = Setup("tally", Rules("code", 5, 0), options=("k:C", "k:A", "k:B"))
    g = Game(setup)
    for player, text in [("p1", "a"), ("p2", "a"), ("p3", "b"), ("p4", "other"), ("p5", "loop")]:
        g.send(player, text)
    pic = g.picture()
    assert pic["kind"] == "tally" and pic["reduction"] == "tally" and pic["others"] == 0
    assert [(x["id"], x["n"]) for x in pic["groups"]] == [
        (gid("ok", "k:C"), 0), (gid("ok", "k:A"), 2), (gid("ok", "k:B"), 1), (gid("ok", "k:OTHER"), 1),
        (gid("timeout"), 1)]
    assert pic["groups"][0]["example"] is None


# ------------------------------------------------------------------ the references, the reveal
def test_the_reference_shows_at_the_reveal_and_to_the_panel_at_once():
    g = Game()
    g.send("p1", "select 1")
    g.send("p2", "select 2")
    g.send("p3", "selec t")
    assert g.picture("stage")["references"] == [None]            # not run yet
    assert all("verdict" not in x for x in g.picture("stage")["groups"])
    assert g.reduced.verdict(A, S, g.checks.of(g.entries.get(A, S, "entry-0001"))) is None
    g.reduced.refer(A, S, [{"status": "ok", "key": "k1", "detail": D1}])
    display, stage = g.picture(), g.picture("stage")
    assert [x["reference"] for x in display["groups"]] == [False, False, False]
    assert all("verdict" not in x for x in display["groups"]) and "solution" not in display and "solution" not in stage
    assert "references" not in display and "SELECT 1" not in str({k: v for k, v in display.items() if k != "groups"})
    assert [(x["reference"], x["verdict"]) for x in stage["groups"]] == [
        (True, "correct"), (False, "incorrect"), (False, "incorrect")]
    assert stage["references"] == [{"group": gid("ok", "k1")}]
    g.move("reveal")
    display = g.picture()
    assert display["revealed"] and [(x["reference"], x["verdict"]) for x in display["groups"]] == [
        (True, "correct"), (False, "incorrect"), (False, "incorrect")]
    assert display["solution"] == [{"text": "SELECT 1", "group": gid("ok", "k1"), "detail": D1}]
    assert g.picture("stage")["solution"] == display["solution"]
    # a check's verdict, for the phones and the points
    of = {e.input["text"]: g.reduced.verdict(A, S, g.checks.of(e)) for e in g.entries.held[(A, S)].entries.values()}
    assert of == {"select 1": "correct", "select 2": "incorrect", "selec t": "incorrect"}
    assert g.reduced.verdict(A, S, None) is None
    assert g.reduced.verdict(A, S, CheckRow("g1", A, S, "n", "internal", aside=True)) is None


def test_solution_mark_shows_no_reference_and_a_failed_one_says_so():
    marked = Setup("groups", Rules("code", 5, 0), solution="mark", references=("SELECT 1", "SELECT nonsense"))
    g = Game(marked)
    g.send("p1", "select 1")
    g.reduced.refer(A, S, [{"status": "ok", "key": "k1"}, {"status": "error"}])
    g.move("reveal")
    assert "solution" not in g.picture() and g.picture()["groups"][0]["reference"] is True
    assert g.picture("stage")["references"] == [{"group": gid("ok", "k1")}, {"failed": "error"}]
    # a reference nobody matched: its own detail shows
    shown = Game(Setup("groups", Rules("code", 5, 0), references=("SELECT 1", "SELECT 9")))
    shown.send("p1", "select 2")
    shown.reduced.refer(A, S, [{"status": "ok", "key": "k1", "detail": D1}])
    shown.move("reveal")
    assert shown.picture()["solution"] == [{"text": "SELECT 1", "group": gid("ok", "k1"), "detail": D1},
                                           {"text": "SELECT 9"}]
    assert shown.picture("stage")["references"] == [{"group": gid("ok", "k1")}, None]
    # no reference with a result: nothing is judged
    none = Game(Setup("groups", Rules("code", 5, 0)))
    none.send("p1", "select 1")
    none.reduced.refer(A, S, [{"status": "timeout"}])
    none.move("reveal")
    assert "verdict" not in none.picture()["groups"][0] and "solution" not in none.picture()


def test_a_kind_that_judges_for_itself_is_not_overruled():
    g = Game()
    g.send("p1", "judged x")
    g.reduced.refer(A, S, [{"status": "ok", "key": "k1"}])
    assert g.picture("stage")["groups"][0]["verdict"] == "partial"
    assert g.reduced.verdict(A, S, g.checks.of(g.entries.get(A, S, "entry-0001"))) == "partial"


def test_what_the_class_sees_while_the_step_is_open_is_the_decks():
    count = Game(Setup("groups", Rules("code", 5, 0), projector="count"))
    count.send("p1", "select 1")
    pic = count.picture()
    assert pic["held"] == "count" and (pic["students"], pic["entries"]) == (1, 1) and "groups" not in pic
    assert count.picture("stage")["groups"] and "held" not in count.picture("stage")
    count.move("pause")
    assert "groups" not in count.picture()
    count.move("close")
    assert count.picture()["groups"] and "held" not in count.picture()
    hidden = Game(Setup("groups", Rules("code", 5, 0), projector="hidden"))
    hidden.send("p1", "select 1")
    hidden.move("close")
    pic = hidden.picture()
    assert pic["held"] == "hidden" and "groups" not in pic and "entries" not in pic and "students" not in pic
    hidden.move("reveal")
    assert hidden.picture()["groups"] and "held" not in hidden.picture()


def test_a_steps_setup_comes_from_its_item_its_kind_and_its_keys():
    class Kind:
        INPUT, LIMIT, REDUCTION = "code", 5, "groups"
    setup = Setup.of({"projector": "count", "solution": "mark", "limit": 2}, Kind(), {"reference": ["SELECT 1"]})
    assert setup == Setup("groups", Rules("code", 2, 5000, "latest"), projector="count", solution="mark",
                          references=("SELECT 1",))
    assert Setup.of({}, Kind()) == Setup("groups", Rules("code", 5, 5000, "latest"))
    item = {"fields": ["s", "p", "o"], "min": 2, "review": True, "terms": "loose"}
    assert Setup.of(item, TRIPLES) == Setup("crowd", Rules("fields", 10, 2000, "all", 3), min=2, review=True)
    assert Setup.of({"fields": ["s", "o"]}, TRIPLES).review is False
    assert Setup.of({"fields": ["s", "o"], "review": "yes"}, TRIPLES).review is False
    for wrong in ({"projector": "dark"}, {"solution": "tell"}):
        with pytest.raises(ValueError):
            Setup.of(wrong, Kind())
    for wrong in ({"min": 0}, {"min": True}, {"min": 1001}, {"min": "2"}):
        with pytest.raises(ValueError):
            Setup.of(item | wrong, TRIPLES)
    # min, review and options are a crowd graph's and a tally's: with another reduction they are the kind's own
    own = {"min": 0, "review": True, "options": [1, 2]}
    assert Setup.of(own, Kind()) == Setup("groups", Rules("code", 5, 5000, "latest"))
    assert Setup.of(item | {"options": [1]}, TRIPLES).options == ()

    class Choice:
        INPUT, LIMIT, REDUCTION = "code", 1, "tally"
    assert Setup.of({"options": ["a", "b"], "min": 0, "review": True}, Choice()) == Setup(
        "tally", Rules("code", 1, 5000, "latest"), options=("a", "b"))
    for wrong in ({"options": [1]}, {"options": "abc"}):
        with pytest.raises(ValueError):
            Setup.of(wrong, Choice())
    with pytest.raises(ValueError):
        Setup.of({}, Kind(), {"reference": [1]})
    Kind.REDUCTION = "cloud"
    with pytest.raises(ValueError):
        Setup.of({}, Kind())


# ------------------------------------------------------------------ the pictures' versions
def test_a_picture_is_made_once_per_version():
    g = Game()
    g.send("p1", "select 1")
    v = g.pictures.version(g.st)
    pic = g.picture()
    assert g.picture() is pic and pic["version"] == v[0] and g.picture("stage") is not pic
    assert g.picture("anybody") is pic                         # who is not the panel gets the projector's
    g.send("p2", "select 1")
    again = g.picture()
    assert again is not pic and again["version"] > pic["version"] and again["groups"][0]["n"] == 2
    for name, more in (("pause", {}), ("resume", {}), ("close", {}), ("reveal", {})):
        before = g.pictures.version(g.st)
        g.move(name, **more)
        assert g.pictures.version(g.st)[0] > before[0] and g.picture()["phase"] == g.st.phase
    before = g.pictures.version(g.st)
    g.pictures.moved(g.st)                                     # nothing a picture shows changed
    g.phases.tick(g.now + 100)
    assert g.pictures.version(g.st) == before
    # a move the pictures were not told is seen when the picture is asked for
    g.phases.reset(A, now=g.now)
    assert g.picture()["phase"] == "ready" and g.picture()["version"] > before[0]
    for _ in range(3 * views_module.KEPT):                     # the pictures kept are few
        g.reduced.bump(A, S)
        g.picture()
        g.picture("stage")
    assert len(g.pictures.cache[(A, S)]) <= views_module.KEPT


def test_the_windows_are_told_at_most_four_times_a_second():
    g = Game()
    assert g.pictures.told(g.st, 10_000) == {"version": g.pictures.version(g.st)[0], "layout": 0}
    assert g.pictures.told(g.st, 10_300) is None               # they know it
    told = []
    for ms in range(0, 1000, 20):                              # a burst: an entry every 20 ms
        g.send(f"p{ms}", "select 1")
        now = g.pictures.told(g.st, 11_000 + ms)
        if now:
            told.append((ms, now["version"]))
    assert [ms for ms, _ in told] == [0, 260, 520, 780] and len({v for _, v in told}) == 4
    assert g.pictures.told(g.st, 12_100)["version"] == g.pictures.version(g.st)[0]     # the last one, too
    assert g.pictures.told(g.st, 12_400) is None
    g.send("q", "select 1")
    assert g.pictures.told(g.st, 5_000) is not None            # a clock set back keeps nobody waiting


def test_a_crowd_graphs_positions_are_part_of_its_picture():
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    assert g.picture()["at"] == {} and g.picture()["layout"] == 0
    assert g.pictures.layout(g.st, g.setup, {":a": [0.25, 0.123456], ":b": [1, 0], ":c": [0.5, 0.5], ":bad": [2, 0],
                                    ":worse": "x", 7: [0, 0], ":bool": [True, 0]})
    pic = g.picture()
    assert pic["at"] == {":a": [0.25, 0.1235], ":b": [1, 0]} and pic["layout"] == 1      # the nodes it shows
    assert g.pictures.layout(g.st, g.setup, {":a": [0.25, 0.123456], ":b": [1, 0], ":c": [0.5, 0.5]}) is False
    assert g.picture() is pic and g.pictures.version(g.st)[1] == 1
    told = g.pictures.told(g.st, 50_000)
    assert g.pictures.layout(g.st, g.setup, {":a": [0.5, 0.5]}) and g.pictures.told(g.st, 51_000)["layout"] == told["layout"] + 1
    refused("invalid", g.pictures.layout, g.st, g.setup, [[0, 0]])
    refused("invalid", g.pictures.layout, g.st, g.setup, {f":n{i}": [0, 0] for i in range(4 * reduce_module.NODES_SHOWN + 1)})


# ------------------------------------------------------------------ the crowd graph
def test_a_crowd_graph_from_the_checks_parts():
    g = crowd()
    g.send("p1", [":Aachen", ":liegtIn", ":NRW"])
    g.send("p2", [":Aachen", ":liegtIn", ":NRW"])
    g.send("p2", [":Aachen", ":einwohner", "260000"])
    g.send("p3", [":NRW", ":liegtIn", ":Deutschland"])
    pic = g.picture()
    assert pic["kind"] == "graph" and pic["reduction"] == "crowd" and (pic["min"], pic["review"], pic["more"]) == (1, False, 0)
    assert pic["nodes"] == [{"id": ":NRW", "label": ":NRW", "n": 3}, {"id": ":Aachen", "label": ":Aachen", "n": 2},
                            {"id": "260000", "label": "260000", "n": 1, "literal": True},
                            {"id": ":Deutschland", "label": ":Deutschland", "n": 1}]      # the most students first
    assert pic["edges"][0] == {"s": ":Aachen", "o": ":NRW", "p": ":liegtIn", "label": ":liegtIn", "n": 2}
    assert len(pic["edges"]) == 3 and "terms" not in pic and "hiddenTuples" not in pic
    stage = g.picture("stage")
    assert stage["terms"][0] == {"role": "label", "key": ":liegtIn", "label": ":liegtIn", "n": 3, "hidden": False,
                                 "approved": False, "into": None}
    assert stage["hiddenTuples"] == 0 and stage["hidden"] == 0
    assert f1.graph_svg(pic).startswith("<svg") and ":Deutschland" in f1.graph_svg(pic)      # the archive's picture
    two = crowd(fields=("thing", "kind"))
    two.send("p1", ["Aachen", "Stadt"])
    assert two.picture()["edges"] == [{"s": "Aachen", "o": "Stadt", "p": None, "label": "", "n": 1}]


def test_a_term_is_written_as_most_of_the_entries_that_count_write_it():
    g = crowd(terms="loose")
    e1 = g.send("p1", ["AACHEN", "liegt in", "NRW"])
    g.send("p2", ["Aachen", "liegt in", "Nrw"])
    e3 = g.send("p3", ["Aachen", "Liegt In", "nrw"])
    pic = g.picture()
    assert [(n["id"], n["label"]) for n in sorted(pic["nodes"], key=lambda n: n["id"])] == [
        ("aachen", "Aachen"), ("nrw", "NRW")]                   # most; among as many, the one that came first
    assert pic["edges"] == [{"s": "aachen", "o": "nrw", "p": "liegt in", "label": "liegt in", "n": 3}]
    g.withdraw(e3)
    g.withdraw(e1)
    assert {n["label"] for n in g.picture()["nodes"]} == {"Aachen", "Nrw"}
    g.act("merge", target="aachen", onto="nrw")                # a node nobody writes any more: as it was written
    g.withdraw(g.entries.get(A, S, "entry-0002"))
    g.send("p4", ["aachen", "ist", "stadt"])
    assert {(n["id"], n["label"]) for n in g.picture()["nodes"]} == {("nrw", "NRW"), ("stadt", "stadt")}


def f1_picture(g: Game, window: str, layout: dict) -> dict:
    """F1's crowd graph (server/activity.py) of the same entries and the same moderation."""
    shelf = f1.Shelf()
    for e in g.entries.held[(A, S)].entries.values():
        check = g.checks.of(e)
        if e.epoch == g.st.epoch and check is not None and check.status == "ok":
            shelf.add(f1.Contribution(e.id, "g1", A, e.player, e.created, {"fields": [p["text"] for p in check.parts]},
                                      e.state, check.key))
    mods = g.moderation.of(A, S)
    st = {"min": mods.min if mods.min is not None else g.setup.min, "hidden": sorted(mods.hidden),
          "approved": sorted(mods.approved), "merges": [[r, a, b] for (r, a), b in mods.merges.items()]}
    return f1._crowd(g.item, st, shelf, window, layout)


@pytest.mark.parametrize("seed", range(12))
def test_todays_crowd_graph(seed):
    """The same entries and the same acts give the graph F1 gives - node for node, edge for edge, in both
    windows. With terms=exact a term is written one way, so the entries that are hidden or taken back,
    whose writing F1 counts and the core does not, make no difference; with terms=loose all stay in."""
    rng = random.Random(seed)
    loose = seed % 3 == 0
    fields = ("s", "o") if seed % 4 == 1 else ("s", "p", "o")
    many = seed == 7                                           # more nodes than a box shows
    g = crowd(fields=fields, terms="loose" if loose else "exact", review=seed % 5 == 2,
              least=1 if many else 1 + seed % 2)
    words = [":Aachen", ":NRW", ":Köln", '"42"', "true", ":liegtIn"] + \
        ([":aachen", ":AACHEN", ":nrw", ":KÖLN", ":liegtin"] if loose else []) + \
        [f":n{i}" for i in range(60 if many else 0)]
    entries = []
    for i in range(400 if seed == 7 else 160):
        try:
            entries.append(g.send(f"p{rng.randrange(25)}", [rng.choice(words) for _ in fields]))
        except Refused as e:
            assert e.code in ("duplicate", "too-many")
    known = sorted({p["key"] for e in entries for p in g.checks.of(e).parts})
    for _ in range(40):
        act = rng.choice(["merge", "merge", "unmerge", "hide", "hide", "approve", "approve", "approve", "undo",
                          "merge" if many else "min"])
        try:
            if act == "undo":
                g.undo()
            elif act == "min":
                g.act("min", value=rng.randrange(1, 3))
            elif act in ("merge", "unmerge"):
                g.act(act, target=rng.choice(known), onto=rng.choice(known), role=rng.choice(["node", "label"]))
            else:
                g.act(act, target=rng.choice(known), off=rng.random() < 0.4)
        except Refused as e:
            assert e.code in ("invalid", "cycle")
        if not loose and rng.random() < 0.3:
            e = rng.choice(entries)
            if e.state == "in" and rng.random() < 0.5:
                g.withdraw(e)
            elif e.state in ("in", "hidden"):
                g.act("hide", entry=e.id, off=e.state == "hidden")
    if g.setup.review:
        for term in known[:-2]:
            g.act("approve", target=term)
    for term in sorted(g.moderation.of(A, S).hidden)[1:]:      # (one hidden term: something is left to draw)
        g.act("hide", target=term, off=True)
    layout = {k: [round(rng.random(), 4), round(rng.random(), 4)] for k in known[::2]}
    g.pictures.layout(g.st, g.setup, layout)
    for window in ("display", "stage"):
        ours, theirs = g.picture(window), f1_picture(g, window, layout)
        assert {k: ours[k] for k in theirs} == theirs
        assert ours["nodes"] and ours["edges"] and (ours["more"] > 0) == many      # (a graph with something in it)
    assert any(e.state != "in" for e in entries) or loose


# ------------------------------------------------------------------ moderation
def rows(g: Game) -> list[tuple]:
    return [(r.n, r.act, r.target or r.entry, r.off, r.undone) for r in g.moderation.rows]


def test_a_group_is_hidden_from_the_projector_and_shown_in_detail():
    saved = []
    g = Game(save=lambda *r: saved.extend(r))
    g.send("p1", "select 1")
    g.send("p2", "select 2")
    g.send("p3", "select 2")
    one, two = gid("ok", "k1"), gid("ok", "k:SELECT 2")
    saved.clear()
    before = g.picture()["version"]
    done = g.act("hide", target=two)
    assert done.row == ModerationRow("g1", 1, A, S, "hide", target=two, created=g.now) and saved == [done.row]
    assert done.row.epoch == 0
    assert g.groups() == [("SELECT 1", 1)] and g.picture()["version"] > before and g.picture()["students"] == 3
    assert [(x["id"], x["hidden"]) for x in g.picture("stage")["groups"]] == [(two, True), (one, False)]
    assert g.act("hide", target=two) == moderation_module.Done() and len(saved) == 1      # again: nothing, and no row
    assert g.act("hide", target=one, off=True).row is None
    g.act("show", target=two)                                  # what is hidden is not shown in detail either
    assert g.picture()["shown"] is None and g.picture("stage")["shown"]["id"] == two
    g.act("hide", target=two, off=True)
    assert g.picture()["shown"]["id"] == two and g.picture()["shown"]["n"] == 2 and len(g.groups()) == 2
    assert g.act("show", target=two).row is None
    g.act("show")
    assert g.picture()["shown"] is None
    assert rows(g) == [(1, "hide", two, False, False), (2, "show", two, False, False), (3, "hide", two, True, False),
                       (4, "show", None, False, False)]
    assert [a["n"] for a in g.picture("stage")["acts"]] == [4, 3, 2, 1] and "acts" not in g.picture()
    assert g.picture("stage")["acts"][1] == {"n": 3, "act": "hide", "created": g.moderation.rows[2].created,
                                             "target": two, "off": True}
    refused("invalid", g.act, "hide", target="0123456789abcdef")
    refused("invalid", g.act, "hide", target=None)
    refused("invalid", g.act, "hide", target=two, entry="entry-0001")
    refused("invalid", g.act, "show", target=gid("ok", "nobody's"))
    refused("invalid", g.act, "praise", target=two)
    refused("invalid", g.act, "hide", target=two, off="yes")
    for act, more in (("merge", {"target": one, "onto": two}), ("unmerge", {"target": one}),
                      ("approve", {"target": one}), ("min", {"value": 2})):
        refused("reduction", g.act, act, **more)
    assert len(g.moderation.rows) == 4
    # a group whose entries are all gone cannot be shown, but stays hidden or not as it was
    g.withdraw(g.entries.get(A, S, "entry-0001"))
    refused("invalid", g.act, "show", target=one)
    assert g.act("hide", target=one).row is not None


def test_an_entry_is_hidden_and_shown_again():
    g = Game()
    e1 = g.send("p1", "select 1")
    g.send("p2", "select 1")
    done = g.act("hide", entry=e1.id)
    assert done.entries == [e1] and e1.state == "hidden" and done.row.entry == e1.id and done.jobs == []
    assert g.groups() == [("SELECT 1", 1)] and g.picture("stage")["hidden"] == 1
    assert g.act("hide", entry=e1.id).row is None
    assert g.act("hide", entry=e1.id, off=True).entries == [e1] and e1.state == "in"
    assert g.groups() == [("SELECT 1", 2)]
    refused("invalid", g.act, "hide", entry="entry-9999")
    refused("invalid", g.act, "hide", entry=None)
    # hidden while it waits for its check, the student sends another: shown again it is replaced, and its
    # check need not be made
    g.hold = True
    e3 = g.send("p3", "select 3")
    g.act("hide", entry=e3.id)
    g.send("p3", "select 4")
    done = g.act("hide", entry=e3.id, off=True)
    assert e3.state == "replaced" and done.jobs == [Leave(A, S, e3.norm)]
    g.release()
    assert g.groups() == [("SELECT 1", 2), ("SELECT 4", 1)]


def test_a_student_is_blocked_and_what_they_sent_is_hidden():
    g = crowd()
    e1 = g.send("p1", [":a", ":p", ":b"])
    e2 = g.send("p1", [":a", ":p", ":c"])
    g.send("p2", [":a", ":p", ":b"])
    g.act("hide", entry=e2.id)
    done = g.act("block", entry=e1.id)
    assert done.player == "p1" and done.entries == [e1] and done.row.entry == e1.id
    assert done.row.value == {"hid": [e1.id], "had": [e2.id]}   # what it hid, and what it found hidden
    assert g.moderation.blocked == {"p1"} and e1.state == "hidden" and g.picture("stage")["hiddenTuples"] == 2
    assert [e["n"] for e in g.picture()["edges"]] == [1]
    refused("blocked", g.entries.enter, g.st, g.setup.rules, "p1", "entry-0099", {"fields": [":x", ":y", ":z"]},
            now=g.now, blocked="p1" in g.moderation.blocked)
    assert g.act("block", entry=e2.id).row is None             # blocked already, whichever of their entries
    assert "p1" not in str(g.moderation.rows) and "p1" not in str(g.picture("stage"))     # no row, no picture names them
    done = g.act("block", entry=e1.id, off=True)               # unblocked: what was hidden stays so
    assert done.player == "p1" and done.entries == [] and g.moderation.blocked == set() and e1.state == "hidden"
    assert g.act("block", entry=e1.id, off=True).row is None
    refused("invalid", g.act, "block", entry="entry-9999")
    refused("invalid", g.act, "block")


def test_terms_are_merged_hidden_and_approved():
    g = crowd(review=True)
    g.send("p1", [":Aachen", ":liegtIn", ":NRW"])
    g.send("p2", [":aachen", ":liegt_in", ":NRW"])
    g.send("p3", [":Köln", ":liegtIn", ":NRW"])
    assert g.picture()["nodes"] == []                           # a graph that reviews shows what was approved
    for term in (":Aachen", ":liegtIn", ":NRW", ":Köln"):
        g.act("approve", target=term)
    assert [(e["s"], e["n"]) for e in g.picture()["edges"]] == [(":Aachen", 1), (":Köln", 1)]
    g.act("merge", target=":aachen", onto=":Aachen")
    g.act("merge", target=":liegt_in", onto=":liegtIn", role="label")
    assert [(e["s"], e["n"]) for e in g.picture()["edges"]] == [(":Aachen", 2), (":Köln", 1)]
    terms = {(t["role"], t["key"]): t for t in g.picture("stage")["terms"]}
    assert terms[("node", ":aachen")]["into"] == ":Aachen" and terms[("label", ":liegt_in")]["into"] == ":liegtIn"
    assert terms[("node", ":Aachen")]["approved"] and not terms[("node", ":aachen")]["approved"]
    refused("cycle", g.act, "merge", target=":Aachen", onto=":aachen")
    refused("invalid", g.act, "merge", target=":Aachen", onto=":Aachen")
    refused("invalid", g.act, "merge", target=":Aachen", onto=":liegtIn")          # a label is no node
    refused("invalid", g.act, "merge", target=":nobody", onto=":Aachen")
    refused("invalid", g.act, "merge", target=":Aachen", onto=":NRW", role="edge")
    refused("invalid", g.act, "unmerge", target=":nobody")
    refused("invalid", g.act, "approve", target=":nobody")
    refused("reduction", g.act, "show", target=":Aachen")
    assert g.act("merge", target=":aachen", onto=":Aachen").row is None and g.act("unmerge", target=":Köln").row is None
    g.act("merge", target=":aachen", onto=":Köln")              # merged into another: the earlier merge is replaced
    assert [(e["s"], e["n"]) for e in g.picture()["edges"]] == [(":Köln", 2), (":Aachen", 1)]
    g.act("hide", target=":Köln")
    assert [(e["s"], e["n"]) for e in g.picture()["edges"]] == [(":Aachen", 1)]
    g.act("hide", target=":Köln", off=True)
    g.act("unmerge", target=":aachen")
    g.act("approve", target=":Köln", off=True)
    assert [(e["s"], e["n"]) for e in g.picture()["edges"]] == [(":Aachen", 1)]
    # the minimum: the deck's until the lecturer says
    assert g.picture()["min"] == 1 and g.act("min", value=1).row is None
    g.act("min", value=2)
    assert g.picture()["min"] == 2 and g.picture()["edges"] == []
    for wrong in (0, 1001, True, "2", None, 1.5):
        refused("invalid", g.act, "min", value=wrong)
    assert g.picture("stage")["acts"][0] == {"n": g.moderation.rows[-1].n, "act": "min", "value": 2,
                                             "created": g.moderation.rows[-1].created}


def test_every_act_can_be_undone():
    g = crowd()
    e1 = g.send("p1", [":a", ":p", ":b"])
    e2 = g.send("p1", [":a", ":p", ":c"])
    g.send("p2", [":A", ":p", ":b"])
    g.act("merge", target=":A", onto=":a")                     # 1
    g.act("merge", target=":A", onto=":b")                     # 2
    g.act("hide", target=":c")                                 # 3
    g.act("min", value=2)                                      # 4
    g.act("hide", entry=e2.id)                                 # 5
    g.act("block", entry=e1.id)                                # 6: hides e1
    mods = g.moderation.of(A, S)
    assert (mods.merges, mods.hidden, mods.min) == ({("node", ":A"): ":b"}, {":c"}, 2)
    before = g.picture()["version"]
    done = g.undo()                                            # the block: the student sends again, e1 is in - e2 not
    assert done.row.n == 6 and done.row.undone and done.player == "p1" and done.entries == [e1]
    assert g.moderation.blocked == set() and (e1.state, e2.state) == ("in", "hidden")
    assert g.picture()["version"] > before
    assert g.undo(4).row.n == 4 and g.picture()["min"] == 1      # any act, by its number
    assert g.undo(4) == moderation_module.Done()               # undone already
    assert g.undo().row.n == 5 and e2.state == "in"
    assert g.undo().row.n == 3 and g.moderation.of(A, S).hidden == set()
    assert g.undo().row.n == 2 and g.moderation.of(A, S).merges == {("node", ":A"): ":a"}    # as the act before said
    assert g.undo().row.n == 1 and g.moderation.of(A, S).merges == {}
    assert g.undo() == moderation_module.Done()                # none left
    assert [r.undone for r in g.moderation.rows] == [True] * 6 and g.picture("stage")["acts"] == []
    refused("invalid", g.undo, 99)
    refused("invalid", g.undo, True)
    # taking a hide back, undone: hidden again
    g.act("hide", entry=e2.id)
    g.act("hide", entry=e2.id, off=True)
    assert g.undo().entries == [e2] and e2.state == "hidden"
    # an entry the student took back meanwhile stays taken back
    g.act("hide", entry=e2.id, off=True)
    g.act("hide", entry=e1.id)
    last = g.moderation.rows[-1].n
    g.act("hide", entry=e1.id, off=True)
    g.withdraw(e1)
    assert g.undo(last).entries == [] and e1.state == "withdrawn"


def test_an_undo_that_would_merge_two_terms_into_each_other_is_refused():
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    g.act("merge", target=":a", onto=":b")                     # 1
    g.act("unmerge", target=":a")                              # 2
    g.act("merge", target=":b", onto=":a")                     # 3
    why = refused("cycle", g.undo, 2)
    assert ":a" in str(why) and ":b" in str(why)
    assert g.moderation.of(A, S).merges == {("node", ":b"): ":a"} and not g.moderation.rows[1].undone
    assert g.undo(3).row.n == 3 and g.undo(2).row.n == 2
    assert g.moderation.of(A, S).merges == {("node", ":a"): ":b"}


def test_a_restarted_server_has_the_acts_again(tmp_path):
    db = sqlite3.connect(tmp_path / "texstage.sqlite")
    core.create(db)
    w = Writer(db)
    g = crowd(save=w.put)
    e1 = g.send("p1", [":a", ":p", ":b"])
    e2 = g.send("p2", [":A", ":p", ":b"])
    g.send("p3", [":a", ":q", ":c"])
    g.act("merge", target=":A", onto=":a")
    g.act("hide", target=":c")
    g.act("hide", target=":c", off=True)
    g.act("min", value=2)
    g.act("block", entry=e2.id)
    g.act("hide", entry=e1.id)
    g.undo()
    g.pictures.layout(g.st, g.setup, {":a": [0.1, 0.2]})
    before = {w: {k: v for k, v in g.picture(w).items() if k not in ("version", "layout", "at")} for w in views_module.WINDOWS}
    w.flush()
    db.close()

    db = sqlite3.connect(tmp_path / "texstage.sqlite")
    got = core.load(db, ["g1"])
    assert [r.n for r in got.moderation] == [1, 2, 3, 4, 5, 6] and got.moderation[5].undone is True
    assert got.moderation[2].off is True and got.moderation[4].value == {"hid": [e2.id], "had": []} and got.moderation[3].value == 2
    again = crowd()
    again.phases.load(got.steps, now=g.now)
    again.st = again.phases.get(A)
    again.entries.load(got.entries)
    again.checks.load(got.checks, got.details, got.entries)
    again.moderation.load(got.moderation)
    again.reduced.load(got.steps, got.entries)
    assert again.moderation.blocked == {"p2"} and again.moderation.of(A, S) == g.moderation.of(A, S)
    after = {w: {k: v for k, v in again.picture(w).items() if k not in ("version", "layout", "at")} for w in views_module.WINDOWS}
    assert after == before and after["stage"]["acts"][0]["act"] == "block"
    assert again.picture()["at"] == {}                          # the positions are not stored: the window sends them
    assert again.act("hide", target=":c").row.n == 7           # the next act is the next number
    assert again.undo(5).player == "p2" and again.entries.get(A, S, e2.id).state == "in"
    db.close()


def test_the_groups_are_the_same_after_a_restart(tmp_path):
    db = sqlite3.connect(tmp_path / "texstage.sqlite")
    core.create(db)
    w = Writer(db)
    g = Game(save=w.put)
    for player, text in [("p1", "select 1  -- Ada"), ("p2", "select 1"), ("p3", "selec t"), ("p4", "loop"),
                         ("p5", "boom"), ("p6", "-- nothing"), ("p2", "select 2")]:
        g.send(player, text)
    g.act("hide", target=gid("timeout"))
    g.act("show", target=gid("ok", "k1"))
    before = {w: {k: v for k, v in g.picture(w).items() if k != "version"} for w in views_module.WINDOWS}
    w.flush()
    db.close()
    db = sqlite3.connect(tmp_path / "texstage.sqlite")
    got = core.load(db, ["g1"])
    assert {c.form["text"] for c in got.checks if c.form} == {"SELECT 1", "SELEC T", "LOOP", "BOOM", "SELECT 2"}
    again = Game()
    again.phases.load(got.steps, now=g.now)
    again.st = again.phases.get(A)
    again.entries.load(got.entries)
    again.checks.load(got.checks, got.details, got.entries)
    again.moderation.load(got.moderation)
    changed: list = []
    again.work(again.checks.again(got.entries), changed)       # what normalize refused is asked again
    again.reduced.load(got.steps, got.entries)
    after = {w: {k: v for k, v in again.picture(w).items() if k != "version"} for w in views_module.WINDOWS}
    assert after == before and "Ada" not in str(after)
    db.close()


def test_the_acts_on_groups_stay_through_a_reset_the_acts_on_entries_are_their_entries():
    g = crowd()
    e1 = g.send("p1", [":a", ":p", ":b"])
    g.send("p2", [":A", ":p", ":b"])
    g.act("merge", target=":A", onto=":a")
    g.act("hide", target=":b")
    g.act("hide", entry=e1.id)
    g.move("reset")
    g.move("open")
    assert g.picture("stage")["hiddenTuples"] == 0 and g.picture("stage")["terms"] == []
    g.send("p1", [":A", ":p", ":c"])
    g.send("p2", [":a", ":p", ":b"])
    assert [(e["s"], e["o"]) for e in g.picture()["edges"]] == [(":a", ":c")]      # merged, and :b hidden, as before
    assert g.act("hide", target=":b", off=True).row is not None and len(g.picture()["edges"]) == 2
    refused("invalid", g.act, "hide", entry=e1.id, off=True)    # an entry of the earlier epoch
    assert g.act("unmerge", target=":A").row is not None        # a merge of the earlier epoch can be taken back
    assert g.act("block", entry=e1.id).player == "p1"           # and a student blocked by an earlier entry
    assert g.moderation.rows[-1].epoch == 1
    # the group whose detail is on the projector is its epoch's: after a reset none is, the same result again neither
    q = Game()
    q.send("p1", "select 1")
    q.act("hide", target=gid("ok", "k1"))
    q.act("hide", target=gid("ok", "k1"), off=True)
    q.act("show", target=gid("ok", "k1"))
    q.move("reset")
    q.move("open")
    q.send("p1", "select 1")
    assert q.picture()["shown"] is None and q.picture("stage")["shown"] is None and len(q.groups()) == 1
    assert q.act("show").row is None                           # none is shown: nothing to take back
    assert q.act("show", target=gid("ok", "k1")).row.epoch == 1 and q.picture()["shown"]["n"] == 1


def test_a_game_takes_so_many_acts(monkeypatch):
    monkeypatch.setattr(moderation_module, "ACTS_MAX", 3)
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    for value in (2, 3, 4):
        g.act("min", value=value)
    refused("too-many", g.act, "min", value=5)
    assert g.undo().row.n == 3                                 # undoing is still possible


def test_the_acts_of_another_game_are_not_this_games():
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    g.moderation.load([ModerationRow("g2", 1, A, S, "hide", target=":a"), ModerationRow("g1", 2, A, S, "min", value=3),
                       ModerationRow("g1", 1, A, S, "hide", target=":b"),
                       ModerationRow("g1", 3, A, S, "block", entry="entry-gone", undone=True)])
    assert [r.n for r in g.moderation.rows] == [1, 2, 3] and g.moderation.of(A, S) == Mods(hidden={":b"}, min=3)


def test_the_acts_are_loaded_after_the_entries():
    g = crowd()
    e = g.send("p1", [":a", ":p", ":b"])
    g.act("hide", target=":b")
    g.act("block", entry=e.id)
    again = crowd()
    with pytest.raises(ValueError, match="load a game's entries before its acts"):      # else nobody were blocked,
        again.moderation.load(g.moderation.rows)                                        # and nothing said so
    assert again.moderation.rows == [] and again.moderation.blocked == set()
    again.entries.load([e])
    again.moderation.load(g.moderation.rows)
    assert again.moderation.blocked == {"p1"} and again.moderation.of(A, S).hidden == {":b"}
    g.undo()                                                   # a block that is undone needs no entry
    fresh = crowd()
    fresh.moderation.load(g.moderation.rows)
    assert fresh.moderation.blocked == set() and len(fresh.moderation.rows) == 2


# ------------------------------------------------------------------ storage
def test_a_groups_id():
    assert gid("ok", "k1") != gid("ok", "k2") != gid("invalid") and gid("invalid") == gid("invalid", "anything")
    assert gid("ok", "invalid") != gid("invalid") and gid("ok", "") != gid("ok")[:0] and len(gid("ok", "k1")) == 16
    assert set(gid("ok", "half " + chr(0xD83D))) <= set("0123456789abcdef")
    # stored with the acts on a group: another value orphans them
    assert (gid("ok", "k1"), gid("invalid")) == ("d15cef379fae947e", "f1234d75178d892a")


def test_acts_and_forms_are_stored_as_they_are():
    db = sqlite3.connect(":memory:")
    core.create(db)
    w = Writer(db)
    acts = [ModerationRow("g1", 2, A, S, "merge", 4, target=":Köln", role="label", onto=":Koeln", created=5),
            ModerationRow("g1", 1, A, S, "block", entry="entry-0001", value=["entry-0001", "entry-0002"]),
            ModerationRow("g1", 3, A, S, "hide", target=":x", off=True, undone=True),
            ModerationRow("g2", 1, A, S, "min", value=3)]
    check = CheckRow("g1", A, S, "n1", "ok", key="k", form={"text": "SELECT 'Köln'"})
    w.put(*acts, check, CheckRow("g1", A, S, "n2", "invalid"))
    assert w.flush() == 6
    got = core.load(db, ["g1"])
    assert got.moderation == [acts[1], acts[0], acts[2]]       # in the order of the acts
    assert got.moderation[2].off is True and got.moderation[2].undone is True and got.moderation[0].off is False
    assert got.checks[0].form == {"text": "SELECT 'Köln'"} and got.checks[1].form is None
    acts[1].undone = True                                      # an act undone is the same row
    w.put(acts[1])
    w.flush()
    assert [r.undone for r in core.load(db, ["g1"]).moderation] == [True, False, True]
    assert core.load(db, ["g2"]).moderation == [acts[3]]


def test_a_file_from_before_has_no_forms_and_no_acts():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE checks (session, activity, step, norm, status, key, parts, verdict, credit, message, at, "
               "aside, created, PRIMARY KEY (session, activity, step, norm))")
    db.execute("INSERT INTO checks (session, activity, step, norm, status, key, aside, created) VALUES "
               "('g1', 'a', 'main', 'n1', 'ok', 'k', 0, 7)")
    core.create(db)
    got = core.load(db, ["g1"])
    assert got.checks == [CheckRow("g1", A, S, "n1", "ok", key="k", created=7)] and got.moderation == []
    g = Game()
    e = EntryRow("entry-0001", "g1", A, S, 0, "p1", 5, {"text": "select 1"}, "n1")
    g.entries.load([e])
    g.checks.load(got.checks, [], [e])
    g.reduced.load([g.st], [e])
    assert g.groups() == [(None, 1)]                            # a group all the same: it has no text to show


def test_a_moved_games_graph_is_the_one_f1_showed(tmp_path):
    from texstage.checks import cleaning
    from texstage.server.game import Session
    item = {"input": "tuple", "fields": ["s", "p", "o"], "min": 1, "terms": "loose"}
    st = {"phase": "open", "version": 4, "min": 2, "merges": [["node", "aix", "aachen"], ["label", "in", "liegt in"]],
          "hidden": ["bonn"], "approved": ["aachen"]}
    stage = {"activity": {"current": A, "items": {A: st}}}
    store = Store(tmp_path / "texstage.sqlite")
    store.save(Session("g1", "111111", "deck", "bundle", 0, 0, stage=stage))
    shelf = f1.Shelf()
    sent = [("p1", ["Aachen", "liegt in", "NRW"], "in"), ("p2", ["AACHEN", "in", "NRW"], "in"),
            ("p3", ["Aix", "liegt in", "nrw"], "in"), ("p3", ["Bonn", "liegt in", "NRW"], "in"),
            ("p4", ["Bonn", "liegt in", "NRW"], "in"), ("p4", ["Aachen", "hat", "Dom"], "in"),
            ("p5", ["Aachen", "hat", "Dom"], "hidden"), ("p1", ["Aix", "hat", "Dom"], "in"),
            ("p2", ["Aachen", "liegt in", "NRW"], "withdrawn")]
    for i, (player, fields, state) in enumerate(sent):
        c = f1.Contribution(f"c{i:011d}", "g1", A, player, 100 + i, {"fields": fields}, state,
                            chr(0x1F).join(cleaning.term_key(f, item) for f in fields))
        shelf.add(c)
        store.save(c)
    store.commit()
    made = core.move(store.db, {"g1": stage})
    assert (made["entries"], made["checks"], made["moderation"]) == (9, 6, 5)
    got = core.load(store.db, ["g1"])
    g = crowd(terms="loose")
    g.phases.load(got.steps, now=5_000)
    g.st = g.phases.get(A)
    g.entries.load(got.entries)
    g.checks.load(got.checks, got.details, got.entries)
    g.moderation.load(got.moderation)
    g.reduced.load(got.steps, got.entries)
    assert g.checks.again(got.entries) == []                   # every triple has its check
    for window in views_module.WINDOWS:
        ours, theirs = g.picture(window), f1._crowd(item, st, shelf, window, {})
        assert {k: ours[k] for k in theirs} == theirs and len(ours["edges"]) == 2
    assert g.undo().row.act == "approve" and g.undo().row.act == "hide"      # what F1 kept can be undone now
    assert len(g.picture()["edges"]) == 3
    store.close()


# ------------------------------------------------------------------ what the review of package 5 found
def sql_game(**more) -> Game:
    """A game of the real kind of SQL queries: its normalize, its checks, its details."""
    from texstage_kinds_sql import SqlQuery

    from texstage.activities import kind as contract
    sql = SqlQuery()
    item, keys = {"seed": "s"}, {"reference": ["SELECT x FROM t ORDER BY x"]}
    prepared = sql.prepare(item, keys, {"s": b"CREATE TABLE t(x); INSERT INTO t VALUES (1), (2), (3);"})
    step = Step(item, keys, "en", 1.0)
    refs = [c.sent() for c in contract.referenced(sql, prepared, step)]

    def normalize(sent: dict) -> dict:
        return {"text": sql.normalize(step, Entry(text=sent["text"])).text}

    def check(form: dict) -> dict:
        return contract.validated(sql, sql.check(prepared, step, Entry(text=form["text"])), step).sent()
    g = Game(Setup("groups", Rules("code", 5, 0), references=tuple(keys["reference"]), **more), normalize, check)
    g.reduced.refer(A, S, refs)
    return g


def test_nothing_of_the_reference_reaches_the_projector_before_the_reveal_with_a_real_kind():
    g = sql_game()
    g.send("p1", "SELECT x FROM t")
    g.send("p2", "SELECT x FROM t WHERE x > 1")
    g.act("show", target=g.picture("stage")["groups"][0]["id"])
    display, stage = g.picture(), g.picture("stage")
    # the kind's detail says how a result compares with the reference: the panel has that, the projector not
    assert all(x["detail"]["columns"] == ["x"] and "diff" not in x["detail"] for x in display["groups"])
    assert "diff" not in display["shown"]["detail"] and "diff" not in str(display)
    assert sorted(x["detail"]["diff"]["missing"] for x in stage["groups"]) == [0, 1]
    assert "diff" in stage["shown"]["detail"]
    assert g.checks.detail(A, S, g.checks.of(g.entries.get(A, S, "entry-0001")).key)["diff"]      # (kept whole)
    for name in ("pause", "resume", "close"):
        g.move(name)
        assert "diff" not in str(g.picture()) and not any(x["reference"] for x in g.picture()["groups"])
    g.move("reveal")
    assert sorted(x["detail"]["diff"]["missing"] for x in g.picture()["groups"]) == [0, 1]
    assert g.picture()["solution"][0]["detail"]["diff"] == {"common": 3, "missing": 0, "extra": 0}


def test_a_group_shows_what_its_kinds_normalize_made_of_the_text():
    # the kinds take a text's comments out, and the spaces at its lines' ends (the design's 5.1): no name in
    # a comment is shown to the class. What is left is as it was typed - its case, its spacing within a line.
    g = sql_game()
    g.send("p1", "SELECT x FROM t   -- Max was here   \n\n")
    g.send("p2", "select x  from t /* and Moritz */")
    assert g.groups() == [("SELECT x FROM t", 2)]
    assert "Max" not in str(g.picture()) + str(g.picture("stage")) and "Moritz" not in str(g.picture("stage"))


def test_where_the_latest_counts_a_student_never_has_two_entries_in():
    g = Game()
    e1 = g.send("p1", "select 1")
    g.act("hide", entry=e1.id)
    e2 = g.send("p1", "select 2")
    g.act("hide", entry=e2.id)
    done = g.act("hide", entry=e1.id, off=True)               # the earlier one first: in
    assert done.entries == [e1] and (e1.state, e2.state) == ("in", "hidden")
    done = g.act("hide", entry=e2.id, off=True)               # then the later one: it replaces the earlier
    assert done.entries == [e2, e1] and (e1.state, e2.state) == ("replaced", "in")
    assert g.entries.counts(g.st) == {"entries": 1, "students": 1} and g.groups() == [("SELECT 2", 1)]
    # the same by undo, in the order of the acts - and the check the replaced one waited for need not be made
    g = Game()
    g.hold = True
    e1 = g.send("p1", "select 1")
    g.act("hide", entry=e1.id)
    e2 = g.send("p1", "select 2")
    g.act("hide", entry=e2.id)
    assert g.undo(1).entries == [e1] and e1.state == "in"
    done = g.undo(2)
    assert done.entries == [e2, e1] and (e1.state, e2.state) == ("replaced", "in") and done.jobs == [Leave(A, S, e1.norm)]
    g.release()
    assert g.groups() == [("SELECT 2", 1)] and g.entries.counts(g.st) == {"entries": 1, "students": 1}


def test_after_a_reset_no_undo_reaches_into_the_earlier_epoch():
    g = crowd()
    e1 = g.send("p1", [":a", ":p", ":b"])
    g.act("hide", target=":b")                                 # 1
    g.act("hide", entry=e1.id)                                 # 2
    g.move("reset")
    g.move("open")
    assert [a["n"] for a in g.picture("stage")["acts"]] == [1]  # the act on the entry is no longer the panel's
    assert g.moderation.acts(A, S) == g.moderation.acts(A, S, 0) and len(g.moderation.acts(A, S)) == 2
    refused("invalid", g.undo, 2)
    assert g.undo().row.n == 1 and g.undo() == moderation_module.Done()      # the last act that is this epoch's
    assert e1.state == "hidden" and not g.moderation.rows[1].undone
    # a block of the earlier epoch can be undone: the student sends again, the earlier entries stay as they are
    e2 = g.send("p2", [":a", ":p", ":c"])
    g.act("block", entry=e2.id)
    g.move("reset")
    g.move("open")
    done = g.undo()
    assert done.row.act == "block" and done.player == "p2" and done.entries == [] and e2.state == "hidden"
    assert g.moderation.blocked == set()


def test_while_a_student_is_blocked_no_undo_brings_their_entries_back():
    g = crowd()
    e1 = g.send("p1", [":a", ":p", ":b"])
    g.act("block", entry=e1.id)                                # 1: hides e1
    g.act("block", entry=e1.id, off=True)                      # 2
    e2 = g.send("p1", [":a", ":p", ":c"])
    done = g.act("block", entry=e1.id)                         # 3: hides e2, and finds e1 hidden
    assert done.row.value == {"hid": [e2.id], "had": [e1.id]}
    assert g.undo(1).entries == [] and (e1.state, e2.state) == ("hidden", "hidden")       # blocked all the same
    assert g.moderation.blocked == {"p1"} and g.picture()["edges"] == []
    refused("blocked", g.act, "hide", entry=e1.id, off=True)   # nor is one shown: unblock the student first
    g.undo(3)                                                  # no block holds any more: as before the blocks
    assert g.moderation.blocked == set() and (e1.state, e2.state) == ("in", "in")
    # an entry hidden before its student was blocked: the undo of that hide waits for the block's
    g = crowd()
    e1 = g.send("p1", [":a", ":p", ":b"])
    g.act("hide", entry=e1.id)                                 # 1
    g.act("block", entry=e1.id)                                # 2
    assert g.undo(1).entries == [] and e1.state == "hidden"
    assert g.undo(2).entries == [e1] and e1.state == "in"      # ... neither act holds: it is in


def test_an_unblock_is_undone_by_blocking_again():
    g = crowd()
    e1 = g.send("p1", [":a", ":p", ":b"])
    g.act("block", entry=e1.id)                                # 1
    g.act("block", entry=e1.id, off=True)                      # 2
    e2 = g.send("p1", [":a", ":p", ":c"])
    done = g.undo()                                            # the unblock: blocked again, by a new act
    assert done.row.n == 3 and done.row.act == "block" and not done.row.off and done.player == "p1"
    assert done.entries == [e2] and g.moderation.blocked == {"p1"} and not g.moderation.rows[1].undone
    assert (e1.state, e2.state) == ("hidden", "hidden")
    assert g.undo().row.n == 3 and g.moderation.blocked == set()             # undone in its turn: as it was
    assert (e1.state, e2.state) == ("hidden", "in")
    g.act("block", entry=e1.id)
    assert g.undo(2) == moderation_module.Done()               # blocked already: nothing to do


def test_showing_an_entry_that_no_act_hid_can_be_undone():
    g = crowd()
    e1 = g.send("p1", [":a", ":p", ":b"])
    g.entries.hide(e1)                                         # as a game moved from F1 has them: hidden, no act
    g.reduced.touch(g.st, e1)
    assert g.act("hide", entry=e1.id, off=True).entries == [e1] and e1.state == "in"
    assert g.undo().entries == [e1] and e1.state == "hidden"   # the act found it hidden
    # ... and a block leaves it as it found it, when it is undone
    e2 = g.send("p1", [":a", ":p", ":c"])
    done = g.act("block", entry=e2.id)
    assert done.row.value == {"hid": [e2.id], "had": [e1.id]}
    assert g.undo().entries == [e2] and (e1.state, e2.state) == ("hidden", "in")
    # what a block hid and the lecturer showed again after the unblock: the undo of that hides it again
    g.act("block", entry=e2.id)
    g.act("block", entry=e2.id, off=True)
    g.act("hide", entry=e2.id, off=True)
    assert e2.state == "in" and g.undo().entries == [e2] and e2.state == "hidden"


def test_merges_that_go_round_in_a_stored_game_do_not_keep_anything_from_being_undone():
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    g.moderation.load([ModerationRow("g1", 1, A, S, "merge", target=":a", role="node", onto=":b"),
                       ModerationRow("g1", 2, A, S, "merge", target=":b", role="node", onto=":a"),
                       ModerationRow("g1", 4, A, S, "merge", target=":c", role="node", onto=":c")])
    assert g.moderation.of(A, S).merges == {("node", ":a"): ":b"} and g.moderation.skipped == {2, 4}
    assert g.act("min", value=2).row.n == 5                    # the next number is after the last, not the count
    assert g.undo().row.act == "min"                           # what does not hold keeps no other act from it
    assert g.undo(2).row.undone and g.moderation.of(A, S).merges == {("node", ":a"): ":b"}
    # ... while an undo that itself makes two terms go round is refused as before
    g.act("unmerge", target=":a")
    g.act("merge", target=":b", onto=":a")
    refused("cycle", g.undo, g.moderation.rows[-2].n)


def test_a_crowd_graphs_writing_does_not_depend_on_the_order_of_the_checks(tmp_path):
    g = crowd(terms="loose")
    g.hold = True
    g.send("p1", ["AACHEN", "liegt in", "NRW"])                # the first to write it - checked last
    g.hold = False
    for player, word, where in (("p2", "aachen", "NRW"), ("p3", "AACHEN", "Deutschland"), ("p4", "aachen", "NRW")):
        g.send(player, [word, "liegt in", where])              # (checked at once: other triples than the first)
    assert g.reduced._of(g.st).first[("node", "aachen", "AACHEN")][1] == "entry-0003"
    g.release()
    assert [n["label"] for n in g.picture()["nodes"] if n["id"] == "aachen"] == ["AACHEN"]     # as many: the first
    # one entry that writes a term two ways: by the text, the same every time
    for order in (("aa", "AA"), ("AA", "aa")):
        both = crowd(terms="loose")
        both.send("p1", [order[0], "is", order[1]])
        both.send("p2", [order[1], "is", order[0]])
        assert [n["label"] for n in both.picture()["nodes"]] == ["AA"]


def test_a_groups_messages_are_the_first_five_in_the_order_their_entries_came():
    g = Game()
    g.hold = True
    for i, name in enumerate("ABCDEFG"):
        g.send(f"p{i}", f"selec {name}")
    g.send("p9", "SELEC   a")                                  # the same message as the first's: once
    g.held.reverse()                                           # the checks come back the other way round
    g.release()
    said = [m["args"]["message"] for m in g.picture("stage")["groups"][0]["messages"]]
    assert said == ["SELEC A", "SELEC B", "SELEC C", "SELEC D", "SELEC E"]
    assert g.picture("stage")["groups"][0]["n"] == 8 and "messages" not in g.picture()["groups"][0]
    m = Game()                                                 # one message of several texts: where the first came
    for i, text in enumerate(["-- one", "selec B", "-- two", "selec C", "-- three"]):
        m.send(f"p{i}", text)
    assert [x["code"] for x in m.picture("stage")["groups"][0]["messages"]] == ["text", "at", "at"]
    g.withdraw(g.entries.get(A, S, "entry-0001"))              # its text is the eighth entry's too: that one is
    said = [m["args"]["message"] for m in g.picture("stage")["groups"][0]["messages"]]     # its first now
    assert said == ["SELEC B", "SELEC C", "SELEC D", "SELEC E", "SELEC F"]
    for i in (2, 3, 4):
        g.withdraw(g.entries.get(A, S, f"entry-000{i}"))
    said = [m["args"]["message"] for m in g.picture("stage")["groups"][0]["messages"]]
    assert said == ["SELEC E", "SELEC F", "SELEC G", "SELEC A"]


def test_a_group_that_is_no_result_is_not_judged_by_one_check_of_it():
    def check(form: dict) -> dict:
        out = {"status": "invalid"}
        return out | {"verdict": "partial", "credit": 0.5} if form["text"] == "A" else out
    g = Game(check=check)
    for i, text in enumerate("ABC"):
        g.send(f"p{i}", text)
    assert "verdict" not in g.picture("stage")["groups"][0]
    assert [g.reduced.verdict(A, S, g.checks.of(e)) for e in g.entries.held[(A, S)].entries.values()] == [
        "partial", None, None]                                 # each check's own verdict is its own
    g.reduced.refer(A, S, [{"status": "ok", "key": "k1"}])
    assert g.picture("stage")["groups"][0]["verdict"] == "incorrect"
    # what was set aside is never judged, with a reference neither
    g.send("p7", "boom") if False else None
    aside = Game()
    aside.send("p1", "boom")
    aside.reduced.refer(A, S, [{"status": "ok", "key": "k1"}])
    assert [(x["status"], "verdict" in x) for x in aside.picture("stage")["groups"]] == [("internal", False)]


def test_the_panels_counts_follow_the_checks_though_no_entry_changes():
    g = Game()
    g.hold = True
    e1 = g.send("p1", "select 1")
    g.send("p2", "select 2")
    pic = g.picture("stage")
    assert (pic["entries"], pic["checked"], pic["waiting"], pic["unchecked"], pic["forms"]) == (2, 0, 2, 0, 2)
    g.withdraw(e1)                                             # nobody waits for its check any more ...
    before = g.pictures.version(g.st)
    g.held = [j for j in g.held if j.input == {"text": "SELECT 1"}]
    g.release()                                                # ... and the pool answers all the same
    assert g.pictures.version(g.st)[0] > before[0] and g.picture("stage")["forms"] == g.checks.counts(g.st)["forms"]
    told = g.pictures.told(g.st, 90_000)
    assert told is not None and g.pictures.told(g.st, 91_000) is None
    g.hold = False
    g.send("p3", "select 3")
    g.checks.checked(A, S, core.norm({"text": "SELECT 2"}), {"status": "internal"})     # failed: nothing touched
    assert g.pictures.told(g.st, 92_000) is not None
    pic = g.picture("stage")
    assert (pic["entries"], pic["checked"], pic["waiting"], pic["unchecked"]) == (2, 1, 0, 1)
    assert g.picture()["checked"] == 1 and "unchecked" not in g.picture()
    before = g.pictures.version(g.st)
    g.reduced.refer(A, S, [{"status": "ok", "key": "k1"}])
    once = g.pictures.version(g.st)
    g.reduced.refer(A, S, [{"status": "ok", "key": "k1"}])     # the same again: no new version
    assert once[0] > before[0] and g.pictures.version(g.st) == once


def test_a_tallys_choice_that_nobody_made_can_be_hidden_and_the_rest_is_capped(monkeypatch):
    setup = Setup("tally", Rules("code", 5, 0), options=("k:C", "k:A"))
    g = Game(setup)
    g.send("p1", "a")
    nobody = gid("ok", "k:C")
    assert g.act("hide", target=nobody).row.target == nobody
    assert [x["id"] for x in g.picture()["groups"]] == [gid("ok", "k:A")]
    assert [(x["id"], x["hidden"]) for x in g.picture("stage")["groups"]] == [(nobody, True), (gid("ok", "k:A"), False)]
    refused("invalid", g.act, "show", target=nobody)           # nothing of it to show
    refused("invalid", g.act, "hide", target=gid("ok", "k:Z"))
    assert g.act("hide", target=nobody, off=True).row is not None and len(g.picture()["groups"]) == 2
    monkeypatch.setattr(reduce_module, "GROUPS_SHOWN", 2)
    for i, text in enumerate(["x1", "x2", "x2", "x3", "x3", "x3", "loop"]):
        g.send(f"q{i}", text)
    pic = g.picture()                                          # the deck's choices, then the largest of the others
    assert [(x["id"], x["n"]) for x in pic["groups"]] == [(nobody, 0), (gid("ok", "k:A"), 1), (gid("ok", "k:X3"), 3),
                                                          (gid("ok", "k:X2"), 2)]
    assert pic["others"] == 2                                  # the students of the rest


def test_the_panel_says_how_many_entries_of_a_crowd_graph_are_no_triple():
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    g.send("p2", [":a", ":p", "x" * 61])                       # a field longer than a term may be
    g.send("p3", [":c", ":p", "y" * 61])
    stage = g.picture("stage")
    assert (stage["entries"], stage["students"], stage["invalid"], len(stage["edges"])) == (3, 3, 2, 1)
    assert "invalid" not in g.picture()
    g.withdraw(g.entries.get(A, S, "entry-0002"))
    assert g.picture("stage")["invalid"] == 1


def test_only_a_crowd_graphs_nodes_are_laid_out():
    q = Game()
    q.send("p1", "select 1")
    before = q.pictures.version(q.st)
    refused("reduction", q.pictures.layout, q.st, q.setup, {"x": [0.5, 0.5]})
    assert q.pictures.version(q.st) == before
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    assert g.pictures.layout(g.st, g.setup, {":a": [0.1, 0.2], ":p": [0.3, 0.3], ":nobody's": [0.4, 0.4],
                                             "x" * 100_000: [0.5, 0.5]})
    assert g.pictures.at[(A, S)] == {":a": [0.1, 0.2]}         # a label and what no entry has are not kept
    for place in ([2, 0], [0, -0.1], [True, 0], [0.5], [0.5, 0.5, 0.5], "xy", [float("nan"), 0], ["0", "1"]):
        g.pictures.layout(g.st, g.setup, {":a": place, ":b": [1, 1]})
        assert g.pictures.at[(A, S)] == {":b": [1, 1]}, place  # a place is two numbers in the box


def test_what_the_reductions_keep_as_the_entries_change():
    g = Game(Setup("groups", Rules("code", 9, 0, "all")))
    e1 = g.send("p1", "select 1")
    g.send("p1", "select 1+0")
    g.send("p2", "select 1+0", eid="aa-entry-2")
    g.send("p3", "select 1", eid="zz-entry-3")
    assert g.groups() == [("SELECT 1", 3)]                      # as many of each: the one that came first, not by id
    g.withdraw(e1)
    assert g.groups() == [("SELECT 1+0", 3)]
    late = g.send("p4", "select 1+0")
    g.act("hide", entry="entry-0002")
    assert g.picture("stage")["groups"][0]["entry"] == "aa-entry-2"
    g.act("hide", entry="entry-0002", off=True)                # back in: it is the first of its text again
    assert g.picture("stage")["groups"][0]["entry"] == "entry-0002"
    g.withdraw(late)
    g.withdraw(g.entries.get(A, S, "zz-entry-3"))              # a text nobody has in any more
    assert g.groups() == [("SELECT 1+0", 2)] and g.picture("stage")["groups"][0]["entry"] == "entry-0002"
    with pytest.raises(ValueError):                            # an entry of another step: none of the call is counted
        g.reduced.touch(g.st, g.entries.get(A, S, "entry-0002"),
                        EntryRow("entry-9999", "g1", "another", S, 0, "p1", 1, {"text": "x"}))
    # the groups in the order of their keys among as many students, and the others counted by students
    o = Game(Setup("groups", Rules("code", 9, 0, "all")))
    for i, text in enumerate(["c", "b", "a", "a", "b", "c"]):
        o.send(f"p{i}", text)
    assert o.groups() == [("A", 2), ("B", 2), ("C", 2)]
    assert o.reduced.reduce(o.st, o.setup)["others"] == 0
    import texstage.activities.reduce as r
    shown, r.GROUPS_SHOWN = r.GROUPS_SHOWN, 1
    try:
        assert o.reduced.reduce(o.st, o.setup)["others"] == 4
    finally:
        r.GROUPS_SHOWN = shown
    other = Reduced("g2", o.entries, o.checks)                 # another game's steps and entries are not this one's
    other.load([StepRow("g1", A)], o.entries.held[(A, S)].entries.values())
    assert other.steps == {}
    mine = Reduced("g1", o.entries, o.checks)
    mine.load([StepRow("g2", A)], o.entries.held[(A, S)].entries.values())
    assert mine.steps == {}
    other.load([StepRow("g2", A)], o.entries.held[(A, S)].entries.values())      # its own step, another's entries
    assert other.steps == {}
    # a check that fails changes what the entry is: told so, the reduction says that something changed
    f = Game()
    f.hold = True
    e = f.send("p1", "select 1")
    assert f.reduced.touch(f.st, e) is False
    f.checks.checked(A, S, e.norm, {"status": "internal"})
    assert f.reduced.touch(f.st, e) is True and f.reduced.touch(f.st, e) is False
    before = f.reduced.version(f.st)                           # another epoch is another version, whoever asks first
    f.phases.reset(A, now=f.now)
    assert f.reduced.version(f.st) > before


def test_a_reference_without_a_detail_of_its_own_shows_its_groups():
    g = Game()
    g.send("p1", "select 1")
    g.reduced.refer(A, S, [{"status": "ok", "key": "k1"}])
    g.move("reveal")
    assert g.picture()["solution"] == [{"text": "SELECT 1", "group": gid("ok", "k1"), "detail": D1}]


def test_the_panels_lists_are_capped(monkeypatch):
    monkeypatch.setattr(reduce_module, "TERMS_LISTED", 2)
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    g.send("p2", [":a", ":p", ":c"])
    assert [t["key"] for t in g.picture("stage")["terms"]] == [":p", ":a"]
    g.act("merge", target=":b", onto=":c")
    e = g.entries.get(A, S, "entry-0001")
    g.act("block", entry=e.id)
    for value in (2, 3, 4):
        g.act("min", value=value)
    acts = g.moderation.acts(A, S, 0, last=4)
    assert [a["n"] for a in acts] == [5, 4, 3, 2] and "value" not in acts[3] and acts[3]["entry"] == e.id
    assert g.moderation.acts(A, S, 0)[4] == {"n": 1, "act": "merge", "created": g.moderation.rows[0].created,
                                             "target": ":b", "onto": ":c", "role": "node"}
    assert len(g.picture("stage")["acts"]) == 5


def test_the_acts_of_two_steps_are_apart():
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    other = StepRow("g1", "b")
    g.act("hide", target=":a")                                 # 1, of the step a
    assert g.moderation.act(other, g.setup, "min", value=3, now=5).row.n == 2
    assert [a["n"] for a in g.moderation.acts(A, S)] == [1] and [a["n"] for a in g.moderation.acts("b", S)] == [2]
    refused("invalid", g.undo, 2)                              # another step's act
    assert g.undo().row.n == 1 and g.undo() == moderation_module.Done()
    assert g.moderation.of("b", S).min == 3 and g.moderation.undo(other, g.setup).row.n == 2
    # an entry's id is its step's: the acts on one of another step with the same id are not about this one
    other.phase = "open"
    twin = g.entries.enter(other, g.setup.rules, "p9", "entry-0001", {"fields": [":x", ":y", ":z"]}, now=9).entry
    mine = g.entries.get(A, S, "entry-0001")
    assert g.moderation.act(other, g.setup, "hide", entry=twin.id, now=9).entries == [twin]
    g.act("hide", target=":b")
    assert g.undo().entries == [] and (mine.state, twin.state) == ("in", "hidden")


def test_an_undone_act_is_stored_as_undone(tmp_path):
    db = sqlite3.connect(tmp_path / "texstage.sqlite")
    core.create(db)
    w = Writer(db)
    g = crowd(save=w.put)
    e = g.send("p1", [":a", ":p", ":b"])
    g.act("hide", target=":a")
    g.act("block", entry=e.id)
    w.flush()                                                  # the acts are written - and undone after that
    g.undo(1)
    w.flush()
    assert [(r.n, r.undone) for r in core.load(db, ["g1"]).moderation] == [(1, True), (2, False)]
    g.act("block", entry=e.id, off=True)
    g.undo()                                                   # blocked again: a new row
    w.flush()
    assert [(r.n, r.act, r.off, r.undone) for r in core.load(db, ["g1"]).moderation][2:] == [
        (3, "block", True, False), (4, "block", False, False)]
    db.close()


def test_what_the_acts_take_from_a_window():
    g = crowd()
    e = g.send("p1", [":a", ":p", ":b"])
    refused("invalid", g.act, "praise", entry=e.id)            # no act: nobody is blocked by it
    refused("invalid", g.act, ["hide"], entry=e.id)
    assert g.moderation.blocked == set() and g.moderation.rows == []
    for more in ({"target": [":a"]}, {"target": {"a": 1}}, {"entry": [e.id]}, {"entry": 7}):
        refused("invalid", g.act, "hide", **more)
    refused("invalid", g.act, "merge", target=":a", onto=":b", role=["node"])
    # a term that only a merge knows - no entry of the epoch has it - can be hidden, approved and unmerged
    g.act("merge", target=":a", onto=":b")
    g.move("reset")
    g.move("open")
    assert g.act("hide", target=":b").row is not None and g.act("approve", target=":a").row is not None
    assert g.act("hide", target=":b", off=True).row is not None
    refused("invalid", g.act, "hide", target=":nobody")
    assert g.act("unmerge", target=":a").row is not None and g.moderation.of(A, S).merges == {}
    # a group that is hidden and gone with its epoch can be shown again
    q = Game()
    q.send("p1", "select 1")
    q.act("hide", target=gid("ok", "k1"))
    q.move("reset")
    q.move("open")
    assert q.act("hide", target=gid("ok", "k1"), off=True).row is not None
    refused("invalid", q.act, "hide", target=gid("ok", "k1"))  # ... and is none to hide, until it comes again


def test_a_game_takes_so_many_acts_that_hold_and_so_many_rows(monkeypatch):
    monkeypatch.setattr(moderation_module, "ACTS_MAX", 2)
    monkeypatch.setattr(moderation_module, "ROWS_MAX", 5)
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    g.act("min", value=2)
    g.act("min", value=3)
    refused("too-many", g.act, "min", value=4)
    g.undo()                                                   # an undone act makes room
    g.act("min", value=4)
    g.undo()
    g.act("min", value=5)
    g.undo()
    g.act("min", value=6)
    assert len(g.moderation.rows) == 5 and sum(1 for r in g.moderation.rows if not r.undone) == 2
    g.undo()
    refused("too-many", g.act, "min", value=7)                 # ... until the rows are as many as a game keeps


def test_a_reset_empties_a_crowd_graph():
    g = crowd()
    g.send("p1", [":a", ":p", ":b"])
    g.move("reset")
    g.move("open")
    pic = g.picture("stage")
    assert (pic["nodes"], pic["edges"], pic["terms"], pic["more"]) == ([], [], [], 0)
    refused("invalid", g.act, "merge", target=":a", onto=":b")   # the earlier epoch's terms are not this one's
