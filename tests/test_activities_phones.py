# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What a phone shows of an activity's step against the quiz, and a server that starts whatever its core finds
(the review of 2026-11-19: A1, B1, B2).

A1: the step that runs - else the one closed or revealed last, until the quiz shows something after it: a
reading, a round, its result. The server says when each became what the phones show - the core's step its
"at" (activities.py), the quiz "quiz_at" (game.py) -, both kept with the game; the phone compares them
(play/activities.js: stepShown, web-activities.test.mjs). Before, a closed activity hid every later quiz's
reading, result and leaderboard.
B1: a game whose core rows do not read starts without them, and a pool that does not start is a broken one -
the server runs, its quizzes too, and the windows say why. B2: a prepare that fails leaves a game the
references it has."""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from fake_bundle import make_bundle
from test_activity import World

from texstage.server import activities
from texstage.server import types as stage_types
from texstage.server.bundles import BundleStore
from texstage.server.app import create_app
from texstage.server.checking import Checks, NoPool
from texstage.server.game import Engine, Settings
from texstage.server.store import Store

T0 = 1_800_000_000_000


@pytest.fixture(autouse=True)
def core():
    stage_types.use("core")              # (conftest.py puts the default back after each test)


def enter(w, pid: str, aid: str, entry: str, **sent) -> dict | None:
    w.tick()
    return w.engine.type_player_message(pid, "activity.enter", {"activity": aid, "entry": entry, **sent}, w.now)


def restart(w) -> None:
    """The core's rows written (its writer is the app's task), the store closed, and the engine anew."""
    w.engine.books[activities.NAME].writer.flush()
    w.engine.store.close()
    w.engine = w.start()


def step_cast(engine, sid: str) -> dict | None:
    """The step's part the phones of the game were sent last (activities.py: _cast) - None: none since."""
    text = engine.take_casts().get(sid)
    return json.loads(text)["step"] if text is not None else None


# ------------------------------------------------------------------ A1: the quiz's moment
def test_the_phones_view_says_the_moment_the_quiz_became_what_they_show_and_a_restart_keeps_it(tmp_path):
    """A moment of the game's count (hook.py: moment), not a time: no tie, no clock set back (the second
    review). A reading, a round, its result each move it; the same slide sent again, or an ordinary slide,
    none; the reveal as a command, a question asked again, a poll and a poll's own reveal do."""
    fb = make_bundle(tmp_path / "bundles")
    store = tmp_path / "store.sqlite3"
    engine = Engine(BundleStore([tmp_path / "bundles"]), Store(store), Settings(get_ready_ms=0))
    s = engine.open_session(fb.deck, fb.id, T0)
    pid = engine.join(s.pin, "Ada", T0)[0].id
    now = T0 + 1000

    def quiz_at() -> int | None:
        return engine.player_view(pid, now)["quiz_at"]
    engine.show_slide(s.id, fb.slides[0]["id"], now)
    assert quiz_at() is None                                            # no quiz yet: a step that ended shows
    seen = []
    for phase in ("read", "question", "reveal", "leaderboard"):
        now += 1000
        engine.show_slide(s.id, fb.slide(phase, "pick"), now)
        seen.append(quiz_at())
    assert seen == sorted(set(seen)) and len(seen) == 4                 # a reading, a round, its result
    engine.show_slide(s.id, fb.slide("leaderboard", "pick"), now + 10)  # the same slide again: no moment
    now += 1000
    engine.show_slide(s.id, fb.slides[-1]["id"], now)                   # an ordinary slide: the result stays
    assert quiz_at() == seen[-1]
    now += 1000
    engine.again(s.id, "pick", now)                                     # asked again, as practice
    asked = quiz_at()
    now += 1000
    engine.reveal(s.id, "pick", now)                                    # revealed by the command
    revealed = quiz_at()
    assert seen[-1] < asked < revealed
    now += 1000
    quiz = engine.poll_create(s.id, {"kind": "yesno", "prompt": "Ready?"}, now)    # a poll typed in the lecture
    polled = quiz_at()
    assert polled > revealed
    engine.skip(s.id, quiz, now + 10)                                   # closed: its results show by themselves
    now += 1000
    assert quiz_at() > polled
    last = quiz_at()
    engine.store.close()
    again = Engine(BundleStore([tmp_path / "bundles"]), Store(store), Settings(get_ready_ms=0))
    assert again.player_view(pid, now + 1000)["quiz_at"] == last        # kept with the game
    again.store.close()


# ------------------------------------------------------------------ A1: the step's moment
def test_the_steps_part_says_the_moment_it_became_the_phones_step_and_a_restart_keeps_it(tmp_path):
    w = World(tmp_path)
    (ada,) = w.join("Ada")
    w.engine.take_casts()
    w.tick()
    w.show(257)                                                         # the crowd graph's slide: it opens
    part = step_cast(w.engine, w.s.id)
    assert (part["activity"], part["phase"]) == ("crowd", "open") and part["at"] >= 1
    opened = part["at"]
    w.tick()
    w.engine.pulse(w.now)                                               # its time goes on: still the same step
    assert step_cast(w.engine, w.s.id) in (None, part)
    w.tick()
    w.show(256)                                                         # leaving its slide closes it
    part = step_cast(w.engine, w.s.id)
    assert part["phase"] == "closed" and part["at"] > opened
    left = part["at"]
    w.tick()
    w.engine.pulse(w.now)
    assert step_cast(w.engine, w.s.id) is None                          # nothing moved: no new part, the same at
    restart(w)                                                          # a restart: the at is the game's
    w.tick()
    w.engine.pulse(w.now)
    part = step_cast(w.engine, w.s.id)
    assert (part["phase"], part["at"]) == ("closed", left)


def test_a_step_that_ended_gives_way_to_a_quiz_shown_after_it_and_one_revealed_after_the_quiz_does_not(tmp_path):
    """The two moments as the phone compares them (play/activities.js: stepShown) - in a game with both; the
    same move that closes the step and shows a reading gives the reading the later one."""
    w = World(tmp_path)
    (ada,) = w.join("Ada")
    w.tick()
    w.show(257)
    w.tick()
    w.show(256)                                                         # closed
    closed = step_cast(w.engine, w.s.id)
    w.engine._quiz_shown(w.s, w.now)                                    # (as a reading slide does: game.py)
    quiz_at = w.engine.player_view(ada, w.now)["quiz_at"]
    assert closed["phase"] == "closed" and quiz_at > closed["at"]        # the quiz is shown: the step gives way
    w.tick()
    w.stage("activity.reveal", activity="crowd")                         # revealed after the quiz
    revealed = step_cast(w.engine, w.s.id)
    assert revealed["phase"] == "revealed" and revealed["at"] > quiz_at  # its verdicts show


# ------------------------------------------------------------------ B1: the core's start, the pool's
def test_a_row_of_the_core_that_does_not_read_is_left_out_and_the_games_and_the_server_start(tmp_path, caplog):
    """One row that does not read (its JSON broken): it is left out, said - its game loads all else, and
    writes nothing over what it has (the second review: the game had started empty, its new acts numbered
    from 1 over the stored ones) -, the other games load, and the server starts."""
    w = World(tmp_path)
    (ada,) = w.join("Ada")
    w.show(257)
    enter(w, ada, "crowd", "e-ada-001", fields=[":KG", ":is", ":Graph"])
    other = w.engine.open_session("act", w.bid, w.now, owner="another")  # another lecturer's game of the deck
    bea = w.engine.join(other.pin, "Bea", w.now)[0].id
    w.engine.show_slide(other.id, 257, w.now)
    enter(w, bea, "crowd", "e-bea-001", fields=[":Bea", ":is", ":Here"])
    w.engine.books[activities.NAME].writer.flush()
    w.engine.store.close()
    db = sqlite3.connect(tmp_path / "store.sqlite3")
    db.execute("INSERT INTO entries (id, session, activity, step, epoch, player, created, input, norm, state) "
               "VALUES ('bad', ?, 'crowd', 'main', 0, ?, 1, '{not json', '', 'in')", (w.s.id, ada))
    db.commit()
    db.close()
    engine = w.start()                                                  # (before: JSONDecodeError - the server
    book = engine.books[activities.NAME]                                #  did not start)
    assert book.plays[w.s.id].entries.get("crowd", "main", "e-ada-001") is not None
    assert book.plays[w.s.id].entries.get("crowd", "main", "bad") is None
    assert book.plays[other.id].entries.get("crowd", "main", "e-bea-001") is not None
    assert "a row of entries does not read" in caplog.text
    engine.store.close()


def test_a_pool_that_does_not_start_is_a_broken_one_and_says_why(monkeypatch):
    import texstage.server.pool as pool

    def fails(*args, **kwargs):
        raise OSError("no job object")
    monkeypatch.setattr(pool, "Pool", fails)
    checks = Checks("server").start()
    assert isinstance(checks.pool, NoPool) and "no job object" in checks.pool.broken
    assert checks.pool.submit("act", "text").result()["status"] == "internal"
    with pytest.raises(RuntimeError, match="no job object"):
        checks.pool.prepare("act", "sql", "", []).result()
    assert checks.pool.normalize("kind", {}, {}, {}).result() == {"error": checks.pool.broken}
    checks.close()


def test_a_server_whose_pool_does_not_start_runs_its_quizzes_and_says_why(tmp_path, monkeypatch, caplog):
    """The app's start with such a pool (app.py: start): the server runs - a deck of quizzes plays -, its log
    says why the activities' entries are not checked, and an activity's panel says it (problems)."""
    import texstage.server.pool as pool
    from starlette.testclient import TestClient

    from fake_bundle import make_bundle
    from test_server import KEY, config

    def fails(*args, **kwargs):
        raise OSError("no job object")
    monkeypatch.setattr(pool, "Pool", fails)
    fb = make_bundle(tmp_path / "bundles")
    with TestClient(create_app(config(tmp_path))) as client, client.websocket_connect("/ws") as ws:
        assert client.get("/api/status").status_code == 200
        ws.send_json({"t": "hello", "role": "host", "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1})
        while (m := ws.receive_json())["t"] != "welcome":
            assert m["t"] != "error", m
        ws.send_json({"t": "slide", "slide": fb.slide("question", "pick"), "id": 2})
        while (m := ws.receive_json()).get("re") != 2:
            pass
        assert m["t"] == "ok"                                           # a round of the quiz starts
    assert "the pool did not start: no job object" in caplog.text


# ------------------------------------------------------------------ B2: a prepare that fails
def test_a_prepare_that_fails_leaves_the_game_the_references_it_kept(tmp_path):
    w = World(tmp_path)
    (ada,) = w.join("Ada")
    w.show(259)                                                         # the query's slide: its core is made
    book = w.engine.books[activities.NAME]
    play = book.plays[w.s.id]
    play.refer("query", [{"status": "ok", "key": "k1"}])
    before = play.reduced.steps[("query", "main")].refs
    act = activities.act_name(w.bid, "query")
    book.prepared[act] = {"bundle": w.bid, "aid": "query", "outcomes": None, "failed": None}
    fut = cf.Future()
    fut.set_exception(ValueError("the seed does not load"))
    book._apply(("prepared", act, fut), w.now, set())                   # prepared again, and it failed
    assert book.prepared[act]["failed"] == "the seed does not load"
    assert play.reduced.steps[("query", "main")].refs == before == [{"status": "ok", "key": "k1"}]


def test_a_prepare_whose_reference_could_not_be_run_leaves_the_game_the_one_it_kept(tmp_path):
    """A worker that died while it ran the reference (internal, not set aside): the game keeps the reference
    it had ok - in its core and kept with it (the second review: it took the internal one, and a stale start
    later had nothing to fall back on)."""
    w = World(tmp_path)
    (ada,) = w.join("Ada")
    w.show(259)
    book = w.engine.books[activities.NAME]
    play = book.plays[w.s.id]
    book._keep(w.engine.sessions[w.s.id], "query", [{"status": "ok", "key": "k1"}])
    play.refer("query", [{"status": "ok", "key": "k1"}])
    act = activities.act_name(w.bid, "query")
    book.prepared[act] = {"bundle": w.bid, "aid": "query", "outcomes": None, "failed": None}
    fut = cf.Future()
    fut.set_result([{"status": "internal", "error": "the worker died"}])
    book._apply(("prepared", act, fut), w.now, set())
    assert play.reduced.steps[("query", "main")].refs == [{"status": "ok", "key": "k1"}]
    assert activities.kept(w.engine.sessions[w.s.id].stage)["query"] == [{"status": "ok", "key": "k1"}]
    fut = cf.Future()                                                   # one that ran, and gives another: it counts
    fut.set_result([{"status": "ok", "key": "k2"}])
    book.prepared[act] = {"bundle": w.bid, "aid": "query", "outcomes": None, "failed": None}
    book._apply(("prepared", act, fut), w.now, set())
    assert play.reduced.steps[("query", "main")].refs == [{"status": "ok", "key": "k2"}]


def test_a_block_whose_entry_does_not_read_blocks_nobody_and_no_new_act_writes_over_a_stored_one(tmp_path, caplog):
    """The third review of 2026-11-19: a block whose entry's row did not read dropped its whole game, and the
    fresh core numbered its acts from 1 over the stored ones; and where the last act's row did not read, the
    next act took its number. Now the game loads, the block blocks nobody (said), and new acts come after
    every number the table has."""
    w = World(tmp_path)
    ada, bea = w.join("Ada", "Bea")
    w.show(257)
    enter(w, ada, "crowd", "e-ada-001", fields=[":KG", ":is", ":Graph"])
    enter(w, bea, "crowd", "e-bea-001", fields=[":Bea", ":is", ":Here"])
    w.tick()
    w.stage("activity.moderate", activity="crowd", act="block", entry="e-ada-001")              # act 1
    w.tick()
    w.stage("activity.moderate", activity="crowd", act="min", value=2)                          # act 2
    w.engine.books[activities.NAME].writer.flush()
    w.engine.store.close()
    db = sqlite3.connect(tmp_path / "store.sqlite3")
    db.execute("UPDATE entries SET input = '{not json' WHERE id = 'e-ada-001'")
    db.execute("UPDATE moderation SET value = '{not json' WHERE session = ? AND n = 2", (w.s.id,))
    db.commit()
    db.close()
    w.engine = w.start()
    play = w.engine.books[activities.NAME].plays[w.s.id]                 # the game loads
    assert play.entries.get("crowd", "main", "e-bea-001") is not None and play.moderation.blocked == set()
    assert "blocks nobody" in caplog.text and "a row of moderation does not read" in caplog.text
    w.tick()
    w.stage("activity.moderate", activity="crowd", act="min", value=3)
    w.engine.books[activities.NAME].writer.flush()
    w.engine.store.close()
    db = sqlite3.connect(tmp_path / "store.sqlite3")
    rows = db.execute("SELECT n, act, value FROM moderation WHERE session = ? ORDER BY n", (w.s.id,)).fetchall()
    db.close()
    assert [(n, act) for n, act, _ in rows] == [(1, "block"), (2, "min"), (3, "min")] and rows[1][2] == "{not json"


def test_a_game_of_acts_alone_loads_them_and_a_game_whose_rows_do_not_load_writes_over_none(tmp_path):
    """The fourth review of 2026-11-19: a game with acts alone - a minimum set on a step never opened, so no
    step stored - did not load them; and where its rows did not load at all, the count of its acts came too
    late, and a fresh core wrote act 1 over the stored one."""
    w = World(tmp_path)
    w.join("Ada")
    w.stage("activity.moderate", activity="crowd", act="min", value=2)
    w.tick()
    w.stage("activity.moderate", activity="crowd", act="min", value=4)
    w.engine.books[activities.NAME].writer.flush()
    w.engine.store.close()
    w.engine = w.start()
    play = w.engine.books[activities.NAME].plays[w.s.id]                 # loaded: the acts alone
    assert play.moderation.of("crowd", "main").min == 4
    w.engine.store.close()
    db = sqlite3.connect(tmp_path / "store.sqlite3")
    db.execute("UPDATE moderation SET value = CAST(X'FF' AS TEXT) WHERE session = ? AND n = 1", (w.s.id,))
    db.commit()                                                         # (not UTF-8: no row of the game reads)
    db.close()
    w.engine = w.start()
    assert w.s.id not in w.engine.books[activities.NAME].plays
    w.tick()
    assert w.stage("activity.moderate", activity="crowd", act="min", value=3)["act"] == 3       # after the stored
    w.engine.books[activities.NAME].writer.flush()
    w.engine.store.close()
    db = sqlite3.connect(tmp_path / "store.sqlite3")
    assert [n for (n,) in db.execute("SELECT n FROM moderation WHERE session = ? ORDER BY n", (w.s.id,))] == [1, 2, 3]
    db.close()


def test_a_game_whose_core_is_made_after_a_prepare_that_could_not_run_keeps_the_reference_it_kept(tmp_path):
    """(_known, as for a game that had its core: the third review of 2026-11-19)"""
    w = World(tmp_path)
    w.join("Ada")
    s = w.engine.sessions[w.s.id]
    book = w.engine.books[activities.NAME]
    book._keep(s, "query", [{"status": "ok", "key": "k1"}])            # kept from before (a restart)
    book.prepared[activities.act_name(w.bid, "query")] = {"bundle": w.bid, "aid": "query", "failed": None,
                                                          "outcomes": [{"status": "internal", "error": "died"}]}
    assert w.s.id not in book.plays
    w.show(259)                                                         # its core is made now
    assert book.plays[w.s.id].reduced.steps[("query", "main")].refs == [{"status": "ok", "key": "k1"}]
    assert activities.kept(w.engine.sessions[w.s.id].stage)["query"] == [{"status": "ok", "key": "k1"}]


def test_a_poll_typed_over_an_open_activity_comes_after_the_close_it_makes(tmp_path):
    """The poll takes the projector: the activity it shows closes - and the poll's moment is the later one, so
    its results show on the phones, not the closed activity (the third review of 2026-11-19)."""
    w = World(tmp_path)
    (ada,) = w.join("Ada")
    w.show(257)
    w.engine.take_casts()
    w.tick()
    w.engine.poll_create(w.s.id, {"kind": "yesno", "prompt": "Ready?"}, w.now)
    part = step_cast(w.engine, w.s.id)
    assert part["phase"] == "closed" and w.engine.player_view(ada, w.now)["quiz_at"] > part["at"]


# ------------------------------------------------------------------ D5: a type's module imported first
@pytest.mark.parametrize("module", ["texstage.server.activities", "texstage.server.activity", "texstage.server.types"])
def test_a_types_module_can_be_imported_first(module):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    r = subprocess.run([sys.executable, "-c", f"import {module}; from texstage.server import types; "
                        "assert types.TYPES and types.MESSAGES"], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
