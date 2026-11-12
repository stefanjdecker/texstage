# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The core's checks (texstage/activities/checks.py; docs/architecture/activity-framework-plan-f2.md,
package 4): one check per step and distinct normalized input - identical texts merged, a text
normalized once, a form checked once -, what a worker's answers do, a check that leaves the queue, a
step that is full, and what a restarted server asks for again."""
from __future__ import annotations

import sqlite3

import pytest

from texstage.activities import checks as checks_module
from texstage.activities import store as core
from texstage.activities.checks import Checks, Leave, Normalize, Run
from texstage.activities.store import CheckRow, DetailRow, EntryRow, StepRow, Writer

A, S = "query", "main"
OK = {"status": "ok", "key": "k1", "detail": {"columns": ["n"], "rows": [[1]], "count": 1}, "verdict": "correct",
      "credit": 1, "message": {"code": "rows", "args": {"n": 1}}, "at": [1, 8]}
BROKE = {"status": "internal", "error": "the pool broke"}


class Saved:
    def __init__(self):
        self.rows = []

    def __call__(self, *rows):
        self.rows.extend(rows)

    def take(self):
        rows, self.rows = self.rows, []
        return rows


def entry(n: int, text: str, player: str | None = None, **more) -> EntryRow:
    return EntryRow(f"entry-{n:04d}", "g1", A, S, 0, player or f"p{n}", 1000 + n, {"text": text}, **more)


def clean(text: str) -> dict:
    """What a kind's normalize would make of a query here: its spaces as one, no case."""
    return {"text": " ".join(text.split()).upper()}


def asked(cs: Checks, e: EntryRow) -> Run:
    """An entry of a new text and a new form, through normalize: the check that is asked for."""
    (job,), _ = cs.entered(e)
    (run,), _ = cs.normalized(A, S, job.raw, clean(e.input["text"]))
    return run


def test_a_text_is_normalized_once_and_a_form_checked_once():
    saved = Saved()
    cs = Checks("g1", saved)
    e1, e2, e3 = entry(1, "select 1"), entry(2, "select 1"), entry(3, "SELECT   1")
    jobs, check = cs.entered(e1)
    raw = core.norm({"text": "select 1"})
    assert jobs == [Normalize(A, S, raw, {})] and jobs[0].input == {"text": "select 1"} and check is None
    assert cs.entered(e2) == ([], None)                        # the same text: it waits with the first
    jobs3, _ = cs.entered(e3)                                  # another text, which normalizes alike
    assert [type(j) for j in jobs3] == [Normalize] and jobs3[0].raw != raw
    assert saved.rows == [] and cs.state(e1) == "waiting" and cs.of(e1) is None
    form = core.norm(clean("select 1"))
    jobs, checked = cs.normalized(A, S, raw, clean("select 1"))
    assert jobs == [Run(A, S, form, {}, "p1")] and jobs[0].input == {"text": "SELECT 1"} and checked == []
    assert (e1.norm, e2.norm, e3.norm) == (form, form, "") and saved.take() == [e1, e2]
    assert cs.normalized(A, S, jobs3[0].raw, clean("SELECT   1")) == ([], [])     # the same form: no second check
    assert e3.norm == form and saved.take() == [e3]
    assert cs.counts(StepRow("g1", A)) == {"waiting": 3, "unchecked": 0, "forms": 1, "full": False}
    got = cs.checked(A, S, form, OK, now=5000)
    assert got == [e1, e2, e3]
    row, detail = saved.take()
    assert row == CheckRow("g1", A, S, form, "ok", key="k1", verdict="correct", credit=1,
                           message={"code": "rows", "args": {"n": 1}}, at=[1, 8], created=5000,
                           form={"text": "SELECT 1"})          # with its normalized text: what its group is shown by
    assert detail == DetailRow("g1", A, S, "k1", OK["detail"], 5000) and cs.detail(A, S, "k1") == OK["detail"]
    assert cs.of(e2) is row and cs.state(e3) == "checked"
    assert cs.counts(StepRow("g1", A)) == {"waiting": 0, "unchecked": 0, "forms": 1, "full": False}
    step = cs.steps[(A, S)]
    assert not step.forms and not step.pending and not step.asking and not step.unformed     # nothing is kept waiting
    # a known text, later: its check at once, and nothing to do
    e4 = entry(4, "select 1")
    assert cs.entered(e4) == ([], row) and e4.norm == form and saved.take() == [e4]
    e4b = entry(40, "select 1", norm=form)                     # one that has its norm already (a restart): not saved
    assert cs.entered(e4b) == ([], row) and saved.rows == []
    # a new text whose form has its check: the answer of normalize is its verdict
    e4c = entry(41, "  select  1")
    (job,), _ = cs.entered(e4c)
    assert cs.normalized(A, S, job.raw, clean("  select  1")) == ([], [e4c]) and cs.of(e4c) is row
    saved.take()
    # another form with the same result: its own check, the group's detail once
    e5 = entry(5, "select 2-1")
    run = asked(cs, e5)
    assert cs.checked(A, S, run.norm, OK | {"detail": {"another": "detail"}}, now=6000) == [e5]
    assert [type(r) for r in saved.take()] == [EntryRow, CheckRow] and cs.detail(A, S, "k1") == OK["detail"]
    assert cs.detail(A, S, "no-such-key") is None and cs.detail("no-such-activity", S, "k1") is None
    # a check without a key, or without a detail, has no detail to keep
    e6 = entry(6, "selec")
    run = asked(cs, e6)
    cs.checked(A, S, run.norm, {"status": "invalid", "message": {"code": "at", "args": {"line": 1}}, "detail": {"x": 1}})
    assert [type(r) for r in saved.take()] == [EntryRow, CheckRow] and cs.of(e6).message["code"] == "at"


def test_what_normalize_refuses_is_a_check_of_its_own_and_no_form():
    saved = Saved()
    cs = Checks("g1", saved)
    e1, e2 = entry(1, chr(0x200B)), entry(2, chr(0x200B))      # a space no phone shows
    (job,), _ = cs.entered(e1)
    cs.entered(e2)
    jobs, checked = cs.normalized(A, S, job.raw, refused="text", now=700)
    assert jobs == [] and checked == [e1, e2]
    row = cs.of(e1)
    assert row == CheckRow("g1", A, S, job.raw, "invalid", message={"code": "text", "args": {}}, created=700)
    assert e1.norm == e2.norm == job.raw and cs.state(e2) == "checked"
    assert saved.take() == [e1, e2]                            # the entries' norms; the refusal itself is not stored
    e3 = entry(3, chr(0x200B))
    assert cs.entered(e3) == ([], row) and e3.norm == job.raw  # the same text again: refused at once
    assert cs.normalized(A, S, job.raw, refused="text", now=900) == ([], []) and cs.of(e1) is row     # twice: no more
    assert cs.counts(StepRow("g1", A)) == {"waiting": 0, "unchecked": 0, "forms": 0, "full": False}
    for neither in ({}, {"input": {"text": "x"}, "refused": "text"}):
        with pytest.raises(ValueError, match="normalized"):
            cs.normalized(A, S, job.raw, **neither)


def test_what_could_not_be_normalized_is_not_the_students():
    saved = Saved()
    cs = Checks("g1", saved)
    e1, e2 = entry(1, "select 1"), entry(2, "select 1")
    (job,), _ = cs.entered(e1)
    cs.entered(e2)
    assert cs.unnormalized(A, S, job.raw) == [e1, e2]          # the kind is not installed, the process ended
    assert cs.of(e1) is None and cs.state(e1) == cs.state(e2) == "unchecked" and saved.rows == []
    assert cs.counts(StepRow("g1", A)) == {"waiting": 0, "unchecked": 2, "forms": 0, "full": False}
    assert cs.unnormalized(A, S, job.raw) == [e1, e2]          # an answer twice: nothing more
    e3 = entry(3, "select 1")                                  # the same text again asks again
    jobs, _ = cs.entered(e3)
    assert jobs == [Normalize(A, S, job.raw, {})] and cs.state(e1) == "waiting"
    (run,), _ = cs.normalized(A, S, job.raw, clean("select 1"))
    assert cs.checked(A, S, run.norm, OK) == [e1, e2, e3] and cs.state(e1) == "checked"
    # one that left meanwhile is not kept
    e4 = entry(4, "select 4")
    (job4,), _ = cs.entered(e4)
    cs.unnormalized(A, S, job4.raw)
    e4.state = "withdrawn"
    assert cs.left(e4) == [] and cs.unnormalized(A, S, job4.raw) == []
    assert cs.unnormalized(A, S, "never-asked") == [] and cs.counts(StepRow("g1", A))["unchecked"] == 0


def test_an_internal_check_is_not_the_texts_doing_unless_it_is_set_aside():
    saved = Saved()
    cs = Checks("g1", saved)
    e1 = entry(1, "select 1")
    run = asked(cs, e1)
    saved.take()
    assert cs.checked(A, S, run.norm, BROKE) == [e1]
    assert saved.rows == [] and cs.of(e1) is None and cs.state(e1) == "unchecked"     # nothing is stored
    assert cs.counts(StepRow("g1", A)) == {"waiting": 0, "unchecked": 1, "forms": 1, "full": False}
    e2 = entry(2, "select 1")                                  # the same text again: checked again
    jobs, check = cs.entered(e2)
    assert jobs == [Run(A, S, run.norm, {}, "p2")] and jobs[0].input == {"text": "SELECT 1"} and check is None
    assert cs.state(e1) == "waiting" and cs.counts(StepRow("g1", A))["forms"] == 1
    aside = {"status": "internal", "error": "it ended two processes", "set_aside": True}
    assert cs.checked(A, S, run.norm, aside, now=9) == [e1, e2]
    row = cs.of(e1)
    assert (row.status, row.aside, row.key, row.created) == ("internal", True, None, 9) and saved.take()[-1] is row
    assert not cs.steps[(A, S)].failed and not cs.steps[(A, S)].forms
    e3 = entry(3, "select 1")
    assert cs.entered(e3) == ([], row)                         # set aside: final, no third worker dies for it
    # a check that failed and then comes back all the same - it was asked for twice - is the form's check
    e4 = entry(4, "select 4")
    run4 = asked(cs, e4)
    assert cs.checked(A, S, run4.norm, BROKE) == [e4] and cs.state(e4) == "unchecked"
    assert cs.checked(A, S, run4.norm, OK) == [e4] and cs.state(e4) == "checked" and not cs.steps[(A, S)].failed
    # a form that failed and that nobody waits for any more is no form of the step's
    e5 = entry(5, "select 5")
    run5 = asked(cs, e5)
    cs.checked(A, S, run5.norm, BROKE)
    forms = cs.counts(StepRow("g1", A))["forms"]
    e5.state = "withdrawn"
    assert cs.left(e5) == [] and cs.counts(StepRow("g1", A))["forms"] == forms - 1


def test_a_check_that_nobody_waits_for_leaves_the_queue():
    cs = Checks("g1")
    e1, e2 = entry(1, "select 1"), entry(2, "select 1")
    (job,), _ = cs.entered(e1)
    cs.entered(e2)
    (run,), _ = cs.normalized(A, S, job.raw, clean("select 1"))
    e1.state = "replaced"
    assert cs.left(e1) == []                                   # another student still waits for it
    assert cs.left(e1) == []
    e2.state = "withdrawn"
    assert cs.left(e2) == [Leave(A, S, run.norm)]
    assert cs.left(e2) == [] and cs.counts(StepRow("g1", A))["forms"] == 0
    # asked for again when the text comes again - without normalizing it a second time
    e3 = entry(3, "select 1")
    jobs, _ = cs.entered(e3)
    assert jobs == [Run(A, S, run.norm, {}, "p3")]
    # an answer that comes all the same is kept, for whoever sends the text next
    e3.state = "withdrawn"
    assert cs.left(e3) == [Leave(A, S, run.norm)]
    assert cs.checked(A, S, run.norm, OK) == [] and cs.entered(entry(4, "select 1"))[1].status == "ok"
    # one that leaves while its text is normalized: the answer tells the step the form, and asks for no check
    e5 = entry(5, "select 5")
    (job5,), _ = cs.entered(e5)
    e5.state = "replaced"
    assert cs.left(e5) == [] and cs.normalized(A, S, job5.raw, clean("select 5")) == ([], []) and e5.norm == ""
    jobs, _ = cs.entered(entry(6, "select 5"))
    assert [type(j) for j in jobs] == [Run]
    assert cs.left(entry(7, "never entered", norm="x")) == [] and Checks("g1").left(e1) == []
    # one that is hidden still wants its check: the lecturer may show it again
    e8 = entry(8, "select 8", state="hidden")
    (job8,), _ = cs.entered(e8)
    assert [type(j) for j in cs.normalized(A, S, job8.raw, clean("select 8"))[0]] == [Run]


def test_a_check_asked_for_twice_is_one_check():
    saved = Saved()
    cs = Checks("g1", saved)
    e1 = entry(1, "select 1")
    run = asked(cs, e1)
    e1.state = "withdrawn"
    assert cs.left(e1) == [Leave(A, S, run.norm)]              # ... but it was being checked already
    e2 = entry(2, "select 1")
    assert cs.entered(e2)[0] == [Run(A, S, run.norm, {}, "p2")]      # the same text again: asked for again
    saved.take()
    assert cs.checked(A, S, run.norm, OK, now=1) == [e2] and len(saved.take()) == 2
    assert cs.checked(A, S, run.norm, BROKE, now=2) == [] and saved.rows == []       # the second answer: nothing
    assert cs.checked(A, S, run.norm, OK | {"key": "another"}, now=3) == [] and saved.rows == []
    assert cs.of(e2).key == "k1" and cs.state(e2) == "checked" and not cs.steps[(A, S)].failed
    assert cs.counts(StepRow("g1", A)) == {"waiting": 0, "unchecked": 0, "forms": 1, "full": False}
    # an internal answer for a check nobody waits for is no form of the step's
    e3 = entry(3, "select 3")
    run3 = asked(cs, e3)
    e3.state = "replaced"
    cs.left(e3)
    assert cs.checked(A, S, run3.norm, BROKE) == [] and cs.counts(StepRow("g1", A))["forms"] == 1


def test_a_step_takes_so_many_forms_and_the_panel_is_told(monkeypatch):
    monkeypatch.setattr(checks_module, "FORMS_MAX", 2)
    cs = Checks("g1")
    es = [entry(i, f"select {i}") for i in range(4)]
    runs = []
    for e in es:
        (job,), _ = cs.entered(e)
        runs += cs.normalized(A, S, job.raw, clean(e.input["text"]))[0]
    assert [r.owner for r in runs] == ["p0", "p1"]             # the third and the fourth form wait
    assert cs.counts(StepRow("g1", A)) == {"waiting": 2, "unchecked": 2, "forms": 2, "full": True}
    assert cs.state(es[2]) == "unchecked" and cs.state(es[0]) == "waiting"
    assert cs.entered(entry(8, "select 2")) == ([], None)      # a form that waits for room is not asked for twice
    cs.checked(A, S, runs[0].norm, OK)
    assert cs.counts(StepRow("g1", A)) == {"waiting": 1, "unchecked": 3, "forms": 2, "full": True}
    again = entry(9, "select 0")                               # what the step knows is still answered
    assert cs.entered(again)[1].status == "ok"
    # what normalize refuses is no form: it is refused, full or not
    junk = entry(10, "   ")
    (job,), _ = cs.entered(junk)
    assert cs.normalized(A, S, job.raw, refused="text") == ([], [junk]) and cs.counts(StepRow("g1", A))["forms"] == 2
    # the counts are of the step's epoch and of the entries that are in
    es[1].state = "hidden"
    es[3].epoch = 1
    assert cs.counts(StepRow("g1", A)) == {"waiting": 0, "unchecked": 2, "forms": 2, "full": True}
    assert cs.counts(StepRow("g1", A, epoch=1)) == {"waiting": 0, "unchecked": 1, "forms": 2, "full": True}
    assert cs.counts(StepRow("g1", "another")) == {"waiting": 0, "unchecked": 0, "forms": 0, "full": False}
    # room: the form whose only entry leaves makes room for the one that waited longest
    es[1].state = "withdrawn"
    assert cs.left(es[1]) == [Leave(A, S, runs[1].norm), Run(A, S, core.norm(clean("select 2")), {}, "p2")]
    assert cs.state(es[2]) == "waiting" and cs.state(es[3]) == "unchecked"
    # a form that failed for the server's reasons is checked again though the step is full
    cs.checked(A, S, core.norm(clean("select 2")), BROKE)
    retry = entry(11, "select 2")
    assert [type(j) for j in cs.entered(retry)[0]] == [Run] and cs.counts(StepRow("g1", A))["forms"] == 2
    # ... and once nobody waits for it, it is no form any more: the last one that waited is asked for
    for e in (es[2], cs.steps[(A, S)].asking[core.norm(clean("select 2"))]["entry-0008"], retry):
        e.state = "withdrawn"
        jobs = cs.left(e)
    assert jobs == [Leave(A, S, core.norm(clean("select 2"))), Run(A, S, core.norm(clean("select 3")), {}, "p3")]
    assert cs.counts(StepRow("g1", A))["forms"] == 2 and not cs.steps[(A, S)].held
    # a form that waits for room and that nobody waits for any more is not asked for when there is room
    waits, goes = entry(20, "select 20"), entry(21, "select 21")
    for e in (waits, goes):
        (job,), _ = cs.entered(e)
        assert cs.normalized(A, S, job.raw, clean(e.input["text"])) == ([], [])       # full: both wait
    waits.state = "withdrawn"
    assert cs.left(waits) == []
    es[3].state = "withdrawn"                                  # the one that was asked for leaves: room for one
    assert cs.left(es[3]) == [Leave(A, S, core.norm(clean("select 3"))), Run(A, S, core.norm(clean("select 21")), {}, "p21")]


def test_a_restarted_server_asks_again_for_what_has_no_check(tmp_path):
    db = sqlite3.connect(tmp_path / "texstage.sqlite")
    core.create(db)
    w = Writer(db)
    cs = Checks("g1", w.put)
    done, waits, failed, gone, refused = (entry(1, "select 1"), entry(2, "select 2"), entry(3, "select 3"),
                                          entry(4, "select 4", state="withdrawn"), entry(5, "  "))
    forms = {}
    for e in (done, waits, failed, gone, refused):
        (job,), _ = cs.entered(e)
        if e is refused:
            cs.normalized(A, S, job.raw, refused="text")
            continue
        for run in cs.normalized(A, S, job.raw, clean(e.input["text"]))[0]:
            forms[e.id] = run.norm
    assert set(forms) == {"entry-0001", "entry-0002", "entry-0003"} and gone.norm      # taken back: no check asked
    cs.checked(A, S, forms[done.id], OK, now=50)
    cs.checked(A, S, forms[failed.id], BROKE)
    other = EntryRow("entry-0001", "g2", A, S, 0, "p1", 1, {"text": "select 77"})
    w.put(done, waits, failed, gone, refused, other, CheckRow("g2", "theirs", S, "n", "ok", key="k9"),
          DetailRow("g2", "theirs", S, "k9", {"theirs": 1}))
    w.flush()
    db.close()

    db = sqlite3.connect(tmp_path / "texstage.sqlite")
    got = core.load(db, ["g1", "g2"])
    assert len(got.checks) == 2 and len(got.details) == 2     # of g1: the one check - a refusal is not stored
    cs2 = Checks("g1")
    cs2.load(got.checks, got.details, got.entries)
    assert cs2.detail(A, S, "k1") == OK["detail"] and list(cs2.steps) == [(A, S)]     # another game's are not taken
    by_id = {e.id: e for e in got.entries if e.session == "g1"}
    assert cs2.of(by_id["entry-0001"]).status == "ok" and cs2.of(by_id["entry-0005"]) is None
    jobs = cs2.again(got.entries)
    assert sorted(j.input["text"] for j in jobs) == ["  ", "select 2", "select 3"]     # what waited, failed, was refused
    assert all(type(j) is Normalize for j in jobs)
    (run,), _ = cs2.normalized(A, S, core.norm({"text": "select 2"}), clean("select 2"))
    assert run.norm == forms["entry-0002"] and cs2.checked(A, S, run.norm, OK) == [by_id["entry-0002"]]
    assert cs2.normalized(A, S, core.norm({"text": "  "}), refused="text") == ([], [by_id["entry-0005"]])
    assert cs2.of(by_id["entry-0005"]).status == "invalid"
    # a text the step knew is answered without a worker: its entry's check came back with it
    assert cs2.entered(entry(8, "select 1")) == ([], cs2.of(by_id["entry-0001"]))
    assert cs2.again(got.entries) == []                        # asked for once
    db.close()
