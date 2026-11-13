# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The game engine (server/game.py) driven with a fake clock: sessions, players, the round
cycle, scoring, the views' answer leaks, restart recovery."""
from __future__ import annotations

import os
import time

import pytest

from fake_bundle import make_bundle
from texstage.server.bundles import BundleStore
from texstage.server.game import Engine, GameError, Settings
from texstage.server.store import Store

T0 = 1_800_000_000_000          # ms


class World:
    def __init__(self, tmp_path, store_path=None, **bundle_kw):
        self.bundle = make_bundle(tmp_path / "bundles", **bundle_kw)
        self.bundles = BundleStore([tmp_path / "bundles"])
        self.store_path = store_path
        self.engine = Engine(self.bundles, Store(store_path) if store_path else None, Settings())
        self.now = T0
        self.session = self.engine.open_session(self.bundle.deck, self.bundle.id, self.now)

    def at(self, ms_from_start: int) -> int:
        self.now = T0 + ms_from_start
        return self.now

    def join(self, *names, connected=True):
        out = []
        for name in names:
            p, token = self.engine.join(self.session.pin, name, self.now)
            if connected:
                self.engine.connect(p.id, +1)
            out.append((p, token))
        return out

    def show(self, phase, quiz=None):
        self.engine.show_slide(self.session.id, self.bundle.slide(phase, quiz), self.now)
        return self.session.latest(quiz) if quiz else None


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


# ------------------------------------------------------------------ sessions and players

def test_a_session_per_deck(tmp_path):
    w = World(tmp_path)
    e, s = w.engine, w.session
    assert len(s.pin) == 6 and s.pin.isdigit()
    assert e.open_session(w.bundle.deck, w.bundle.id, T0 + 60_000) is s                 # the same game
    later = e.open_session(w.bundle.deck, w.bundle.id, T0 + 60_000 + Settings().stale_ms)
    assert later is not s and s.ended is not None                                       # the next lecture
    rebuilt = make_bundle(tmp_path / "bundles", title="Test deck v2")                   # a new build
    w.bundles.scanned = 0
    newest = e.open_session(rebuilt.deck, rebuilt.id, T0 + 60_000 + Settings().stale_ms)
    assert newest is not later and later.ended is not None
    with pytest.raises(GameError, match="not on this server"):
        e.open_session("other-deck", w.bundle.id, T0)


def test_the_join_slide_after_the_podium_starts_a_new_game(w):
    """The deck presented to a second group the same day: a new game, not the old one."""
    e = w.engine
    (a, token), = w.join("A")
    w.show("join")
    assert e.sessions[w.session.id] is w.session                          # before the podium: the same
    w.show("podium")
    new = e.show_slide(w.session.id, w.bundle.slide("join"), w.at(60_000))
    assert new is not w.session and new.pin != w.session.pin and w.session.ended == T0 + 60_000
    assert new.players == {} and e.open_session(w.bundle.deck, w.bundle.id, w.now) is new
    with pytest.raises(GameError):
        e.player_by_token(token)


def test_joining(w):
    e = w.engine
    (ada, token), = w.join("  Ada\u0007   Lovelace ")
    assert ada.nickname == "Ada Lovelace"
    assert e.player_by_token(token) is ada
    for bad, code in (("ada lovelace", "nickname-taken"), ("", "nickname"), ("x" * 21, "nickname"), (42, "nickname")):
        with pytest.raises(GameError) as err:
            e.join(w.session.pin, bad, w.now)
        assert err.value.code == code
    with pytest.raises(GameError, match="no game with this PIN"):
        e.join("000000", "Bob", w.now)
    e.kick(w.session.id, ada.id, w.now)
    with pytest.raises(GameError, match="removed"):
        e.player_by_token(token)
    (ada2, _), = w.join("Ada Lovelace")                  # the name is free again
    e.rename(w.session.id, ada2.id, "Countess", w.now)
    assert ada2.nickname == "Countess"


# ------------------------------------------------------------------ the round cycle

def test_answer_counter_keeps_disconnected_submissions_and_waits_for_each_player(w):
    e, sid = w.engine, w.session.id
    (a, token), (b, _), (c, _) = w.join("A", "B", "C")
    r = w.show("question", "pick")

    def counts(quiz="pick"):
        view = e.host_view(sid, w.now)["rounds"][quiz]
        return view["answered"], view["awaiting"]

    assert counts() == (0, 3)
    e.answer(a.id, r.id, {"choice": "B"}, w.at(4000))
    e.connect(a.id, -1)
    assert counts() == (1, 2)                 # the accepted answer still belongs in the total
    assert e.player_by_token(token) is a
    e.connect(a.id, +1)
    assert counts() == (1, 2)                 # resuming an answered player adds nothing
    e.connect(a.id, -1)
    e.answer(b.id, r.id, {"choice": "B"}, w.at(5000))
    assert counts() == (2, 1) and r.phase == "open"  # 2/3, even with only two phones online
    e.answer(c.id, r.id, {"choice": "B"}, w.at(6000))
    assert counts() == (3, 0) and r.phase == "closed" and r.closed_by == "all"
    w.show("reveal", "pick")
    results = e.host_view(sid, w.now)["rounds"]["pick"]["results"]
    assert results["answered"] == results["correct"] == 3 and a.score > 0
    w.at(10000)
    w.show("question", "tf")
    assert counts("tf") == (0, 2)             # the next question starts with the online players


def test_answer_counter_tracks_pending_reconnects_tabs_joins_and_removals(w):
    e, sid = w.engine, w.session.id
    (a, _), (b, token) = w.join("A", "B")
    r = w.show("question", "pick")

    def counts():
        view = e.host_view(sid, w.now)["rounds"]["pick"]
        return view["answered"], view["awaiting"]

    e.answer(a.id, r.id, {"choice": "B"}, w.at(4000))
    e.connect(b.id, -1)
    assert counts() == (1, 0) and r.phase == "open"  # disconnecting alone does not close it
    e.connect(a.id, -1)
    assert counts() == (1, 0)                 # zero online: no fallback to everyone who joined
    assert e.player_by_token(token) is b
    e.connect(b.id, +1)
    assert counts() == (1, 1)
    e.connect(b.id, +1)
    assert counts() == (1, 1)                 # two tabs are still one player
    e.connect(b.id, -1)
    assert counts() == (1, 1)
    (c, _), = w.join("C")
    assert counts() == (1, 2)
    e.kick(sid, b.id, w.now)
    assert counts() == (1, 1)
    e.answer(c.id, r.id, {"choice": "B"}, w.at(5000))
    assert counts() == (2, 0) and r.closed_by == "all"
    e.kick(sid, a.id, w.now)
    assert counts() == (1, 0)                 # removed players' submissions do not count


def test_answer_counter_with_no_answers_and_no_connected_players(w):
    e, sid = w.engine, w.session.id
    (a, _), = w.join("A")
    r = w.show("question", "pick")
    e.tick(w.at(3000))
    e.connect(a.id, -1)
    view = e.host_view(sid, w.now)["rounds"]["pick"]
    assert (view["answered"], view["awaiting"]) == (0, 0) and r.phase == "open"
    e.tick(r.deadline)
    assert r.phase == "closed" and r.closed_by == "time"


def test_round_cycle_and_scores(w):
    e, sid = w.engine, w.session.id
    (a, _), (b, _), (c, _) = w.join("A", "B", "C")
    r = w.show("question", "pick")
    assert r.phase == "get-ready"
    with pytest.raises(GameError, match="not open yet"):
        e.answer(a.id, r.id, {"choice": "B"}, w.at(1000))
    assert e.next_deadline() == T0 + 3000
    assert e.tick(w.at(3000)) == [sid] and r.phase == "open"
    e.answer(a.id, r.id, {"choice": "B"}, w.at(5000))         # 2 s: correct
    e.answer(b.id, r.id, {"choice": "A"}, w.at(8000))         # wrong
    with pytest.raises(GameError, match="already"):
        e.answer(b.id, r.id, {"choice": "B"}, w.at(9000))
    with pytest.raises(GameError) as err:
        e.answer(c.id, r.id, {"choice": "Z"}, w.at(9000))
    assert err.value.code == "invalid"
    e.answer(c.id, r.id, {"choice": "B"}, w.at(13000))        # 10 s: correct
    assert r.phase == "closed" and r.closed_by == "all"       # everybody connected has answered
    assert e.host_view(sid, w.at(13000))["rounds"]["pick"]["closed_by"] == "all"   # the banner's words
    w.show("question", "pick")                              # going back: nothing restarts
    assert w.session.latest("pick") is r and r.phase == "closed"
    w.show("reveal", "pick")
    assert r.phase == "revealed"
    assert (a.score, b.score, c.score) == (950, 0, 750)
    assert (a.rank, c.rank, b.rank) == (1, 2, 3) and (a.streak, b.streak, c.streak) == (1, 0, 1)
    # the next quiz: a second correct answer in a row earns the streak bonus
    w.at(20000)
    r2 = w.show("question", "tf")
    e.tick(w.at(23000))
    e.answer(a.id, r2.id, {"choice": "B"}, w.at(23000))       # at once: 1000 + 100
    e.answer(c.id, r2.id, {"choice": "A"}, w.at(23000))
    e.tick(w.at(43000))                                       # time is up (b never answered)
    assert r2.phase == "closed" and r2.closed_by == "time"
    w.show("leaderboard", "tf")                               # the leaderboard reveals as well
    assert r2.phase == "revealed"
    assert (a.score, a.streak, c.streak, b.streak) == (950 + 1100, 2, 0, 0)
    assert (a.prev_rank, a.rank) == (1, 1)


def test_the_reading_slide_starts_nothing(w):
    """A quiz opens on its reading slide (the question alone): the phones show the question,
    no round runs for as long as the lecturer likes; the click to the question slide starts
    it (get-ready, then open), and stepping back to the reading slide keeps the round."""
    e, sid = w.engine, w.session.id
    (a, _), = w.join("A")
    assert w.show("read", "pick") is None and w.session.current is None
    view = e.player_view(a.id, w.at(60_000))
    assert view["round"] is None and view["reading"]["quiz"] == "pick"
    assert view["reading"]["prompt"]["image"].startswith("phone/")       # the question, no answers
    assert e.next_deadline() is None and e.host_view(sid, w.now)["session"]["current"] is None
    r = w.show("question", "pick")
    assert r.phase == "get-ready" and r.opens == T0 + 63_000
    assert "reading" not in e.player_view(a.id, w.now)
    w.show("read", "pick")                                      # stepped back: the round goes on
    assert w.session.current == r.id and w.session.latest("pick") is r
    e.tick(w.at(63_000))
    assert r.phase == "open" and e.player_view(a.id, w.now)["round"]["phase"] == "open"
    w.show("reveal", "pick")
    w.show("read", "tf")                                        # the next quiz: its question, not the last result
    view = e.player_view(a.id, w.now)
    assert view["round"] is None and view["reading"]["quiz"] == "tf"


def test_preparing_the_slides_starts_nothing(w):
    """Before the lecture the add-in shows every live slide once, so that PowerPoint has
    started their add-ins: meanwhile the slides start, reveal and finish nothing and the
    phones see none of it; afterwards everything is as before. Preparing ends by itself."""
    e, sid = w.engine, w.session.id
    (a, _), = w.join("A")
    e.prepare(sid, True, w.now)
    assert e.host_view(sid, w.now)["session"]["preparing"] is True
    w.show("read", "pick")
    assert "reading" not in e.player_view(a.id, w.now)          # no question on the phones
    for phase, quiz in (("question", "pick"), ("reveal", "pick"), ("leaderboard", "pick"), ("podium", None)):
        w.show(phase, quiz)
    assert w.session.rounds == {} and w.session.finished is None and w.session.current is None
    e.prepare(sid, False, w.at(60_000))
    w.show("join")
    assert e.sessions[sid] is w.session                          # the same game: no podium was shown
    r = w.show("question", "pick")
    assert r is not None and r.phase == "get-ready"
    e.prepare(sid, True, w.at(70_000))
    assert e.host_view(sid, w.at(70_000 + Settings().prepare_ms))["session"]["preparing"] is False


def test_ties_go_to_the_faster_player(w):
    e = w.engine
    (a, _), = w.join("A")
    w.at(100)
    (b, _), = w.join("B")
    r = w.show("question", "pick")
    e.tick(w.at(3100))
    e.answer(b.id, r.id, {"choice": "B"}, w.at(4000))
    e.answer(a.id, r.id, {"choice": "B"}, w.at(4000))
    w.show("reveal", "pick")
    assert a.score == b.score and b.joined > a.joined
    r = w.show("question", "many")
    e.tick(w.at(10000))
    e.answer(a.id, r.id, {"choices": ["A", "C"]}, w.at(12000))
    e.answer(b.id, r.id, {"choices": ["A", "C"]}, w.at(12000))
    w.show("reveal", "many")
    assert a.score == b.score and (a.rank, b.rank) == (1, 2)         # same time: who joined first
    r = w.show("question", "steps")
    e.tick(w.at(20000))
    e.answer(b.id, r.id, {"order": ["A", "B", "C"]}, w.at(21000))    # wrong, both
    e.answer(a.id, r.id, {"order": ["A", "B", "C"]}, w.at(29000))
    w.show("reveal", "steps")
    assert a.score == b.score and (b.rank, a.rank) == (1, 2)         # b was faster in total


def test_lecturer_controls(w):
    e, sid = w.engine, w.session.id
    (a, _), (b, _) = w.join("A", "B")
    r = w.show("question", "pick")
    e.tick(w.at(3000))
    e.pause(sid, "pick", w.at(5000))
    with pytest.raises(GameError, match="paused"):
        e.answer(a.id, r.id, {"choice": "B"}, w.at(6000))
    assert e.next_deadline() is None
    assert e.host_view(sid, w.at(30000))["rounds"]["pick"]["remaining"] == 18000   # frozen
    e.resume(sid, "pick", w.at(30000))
    e.extend(sid, "pick", 10, w.at(30000))
    assert r.deadline == T0 + 30000 + 18000 + 10000 and r.limit_ms == 30000
    e.answer(a.id, r.id, {"choice": "B"}, w.at(32000))       # 2 s open before the pause + 2 s after
    assert r.answers[a.id].answer_ms == 4000
    e.skip(sid, None, w.at(33000))                           # the current round
    assert r.phase == "closed" and r.closed_by == "skip"
    with pytest.raises(GameError, match="time is up"):
        e.answer(b.id, r.id, {"choice": "B"}, w.at(33100))   # no grace after a skip
    with pytest.raises(GameError, match="not been revealed"):
        e.again(sid, "pick", w.at(34000))
    w.show("reveal", "pick")
    score = a.score
    practice = e.again(sid, "pick", w.at(40000))
    assert practice.attempt == 2 and practice.practice and w.session.latest("pick") is practice
    e.tick(w.at(43000))
    e.answer(a.id, practice.id, {"choice": "B"}, w.at(43000))
    e.skip(sid, "pick", w.at(44000))
    w.show("reveal", "pick")
    assert practice.phase == "revealed" and practice.answers[a.id].correct and a.score == score  # no points


def test_ask_again_rewinds_the_later_questions(tmp_path):
    """↻ on a revealed question - after a test run, or a lecture restarted after an
    interruption: the question again (practice), and every later quiz of the deck runs anew;
    their points leave the scores, which are counted again from what is left (streak bonuses
    included). The rewind survives a server restart."""
    w = World(tmp_path, store_path=tmp_path / "games.sqlite3")
    e, sid = w.engine, w.session.id
    (a, _), (b, _) = w.join("A", "B")
    t = 0

    def play(quiz, answers):
        nonlocal t
        r = w.show("question", quiz)
        e.tick(w.at(t + 3000))
        for p, payload in answers:
            e.answer(p.id, r.id, payload, w.at(t + 5000))
        e.skip(sid, quiz, w.at(t + 6000))
        w.show("reveal", quiz)
        t += 10_000
        return r

    play("pick", [(a, {"choice": "B"}), (b, {"choice": "A"})])
    after_pick = (a.score, a.streak, b.score, a.rank, b.rank)
    play("many", [(a, {"choices": ["A", "C"]}), (b, {"choices": ["A", "C"]})])
    play("tf", [(a, {"choice": "B"}), (b, {"choice": "B"})])
    assert a.streak == 3 and a.score > after_pick[0] and b.score > 0
    w.show("question", "pick")                                     # back: nothing restarts
    assert w.session.latest("pick").attempt == 1
    practice = e.again(sid, "pick", w.at(t))
    assert practice.practice and w.session.latest("pick") is practice
    assert w.session.latest("many") is None and w.session.latest("tf") is None
    assert (a.score, a.streak, b.score, a.rank, b.rank) == after_pick    # as before "many"
    e.tick(w.at(t + 3000))
    e.skip(sid, "pick", w.at(t + 4000))
    w.show("reveal", "pick")
    t += 10_000
    anew = play("many", [(b, {"choices": ["A", "C"]})])             # asked anew, and it counts
    assert anew.attempt == 1 and not anew.practice and b.score > after_pick[2] and a.streak == 0
    restarted = Engine(w.bundles, Store(tmp_path / "games.sqlite3"), Settings())
    rounds = sorted((r.quiz, r.attempt) for r in restarted.sessions[sid].rounds.values())
    assert rounds == [("many", 1), ("pick", 1), ("pick", 2)]            # the old "many", "tf" are gone
    assert restarted.players[a.id].score == a.score and restarted.players[b.id].score == b.score


def test_reveal_command_and_results_table(w):
    """`reveal` does what a reveal slide does - for a practice round asked on the reveal
    slide; the results table (CSV export) leaves practice rounds out."""
    e, sid = w.engine, w.session.id
    (a, _), (b, _) = w.join("A", "B")
    r = w.show("question", "pick")
    e.tick(w.at(3000))
    e.answer(a.id, r.id, {"choice": "B"}, w.at(4000))
    w.show("reveal", "pick")
    practice = e.again(sid, "pick", w.at(10000))
    e.tick(w.at(13000))
    e.answer(b.id, practice.id, {"choice": "B"}, w.at(13000))
    e.skip(sid, "pick", w.at(14000))
    e.reveal(sid, "pick", w.at(15000))
    assert practice.phase == "revealed" and practice.answers[b.id].correct and b.score == 0
    rows = e.results_table(sid)
    header, first, second = rows[0], rows[1], rows[2]
    assert header[:8] == ["rank", "nickname", "score", "correct", "answered", "pick answer", "pick correct", "pick points"]
    assert first[:8] == [1, "A", 975, 1, 1, "B", 1, 975]
    assert second[:8] == [2, "B", 0, 0, 0, "", "", ""]                  # the practice answer does not count
    with pytest.raises(GameError, match="no question"):
        e.reveal(sid, "tf", w.now)


def test_a_rebuilt_deck_replaces_the_old_build(tmp_path):
    """The deck list offers the build on disk; a game playing the old build keeps it."""
    old = make_bundle(tmp_path / "b", title="Deck")
    store = BundleStore([tmp_path / "b"])
    new = make_bundle(tmp_path / "b", title="Deck", time=30)              # same folder, new content
    store.scanned = 0
    assert store.get(new.id) is not None
    assert [b.id for b in store.current()] == [new.id] and store.get(old.id) is not None


def built(fb, at: float):
    """deck.json's time (s), which is the build's (Bundle.built): the tests' builds come within a second."""
    os.utime(fb.path / "deck.json", (at, at))
    return fb


def test_a_window_of_an_older_build_leaves_the_game_alone(tmp_path):
    """A deck rebuilt in the lecture, its folder replaced: the new build's hello replaces the game (the
    PowerPoint file built anew, the presenter window). A window of the build before - opened before the
    rebuild, now connecting again or reloaded - is refused while that game runs, the game and its
    phones left alone (2026-11-13: it ended the game, and a new PIN came), unless the lecturer chose
    that build; a game gone stale (the next lecture) ends as ever."""
    hour_ago = int(time.time()) - 3600
    before = built(make_bundle(tmp_path / "b", title="Deck"), hour_ago)
    store = BundleStore([tmp_path / "b"])
    e = Engine(store, None, Settings())
    old = e.open_session("test", before.id, T0)
    after = built(make_bundle(tmp_path / "b", title="Deck", time=30), hour_ago + 3540)   # the same folder: replaced
    store.scanned = 0
    assert store.get(after.id).built - store.get(before.id).built == 3_540_000    # the old build: its own time
    new = e.open_session("test", after.id, T0 + 1000)
    assert old.ended == T0 + 1000 and new.bundle == after.id
    with pytest.raises(GameError, match="newer build") as refused:
        e.open_session("test", before.id, T0 + 2000)
    assert refused.value.code == "newer-build" and new.ended is None and list(e.sessions) == [new.id]
    assert e.open_session("test", after.id, T0 + 3000) is new                 # the new build's windows: its game
    theirs = e.open_session("test", before.id, T0 + 3000, owner="ann")        # (another lecturer's game: apart)
    assert theirs.bundle == before.id and new.ended is None
    chosen = e.open_session("test", before.id, T0 + 4000, chosen=True)        # the deck page: Present
    assert chosen.bundle == before.id and new.ended == T0 + 4000 and theirs.ended is None
    again = e.open_session("test", after.id, T0 + 5000)
    later = e.open_session("test", before.id, T0 + 5000 + Settings().stale_ms)    # the next lecture
    assert later.bundle == before.id and again.ended == T0 + 5000 + Settings().stale_ms
    built(make_bundle(tmp_path / "b", title="Deck"), hour_ago + 3600)         # the build before, made again
    store.scanned = 0
    store.get("0" * 16)                                                       # (an unknown ID: the store looks again)
    assert store.get(before.id).built > store.get(after.id).built            # now it is the newest


def test_late_answers_within_the_grace_period(w):
    e = w.engine
    (a, _), (b, _), (c, _) = w.join("A", "B", "C")
    r = w.show("question", "pick")
    e.tick(w.at(23000))                                      # get-ready 3 s + 20 s: closed by time
    assert r.phase == "closed"
    e.answer(a.id, r.id, {"choice": "B"}, w.at(23300))      # sent in time, arrived a little late
    with pytest.raises(GameError, match="time is up"):
        e.answer(b.id, r.id, {"choice": "B"}, w.at(23600))
    w.show("reveal", "pick")
    assert r.answers[a.id].points == 500


def test_predict_then_see(tmp_path):
    """reveal=none: the question stays one slide; the answer slide, after other slides,
    reveals and scores."""
    w = World(tmp_path, reveal={"count": "none"})
    e = w.engine
    (a, _), = w.join("A")
    r = w.show("question", "count")
    e.tick(w.at(3000))
    e.answer(a.id, r.id, {"value": 6}, w.at(3000))
    w.engine.show_slide(w.session.id, w.bundle.slide(None), w.at(10000))   # an ordinary slide
    assert r.phase == "closed" and a.score == 0
    w.show("answer", "count")
    assert r.phase == "revealed" and a.score == 1000


def test_unscored_quizzes_leave_scores_and_streaks_alone(w):
    e = w.engine
    (a, _), = w.join("A")
    for quiz, answer in (("pick", {"choice": "B"}), ("vote", {"choice": "A"}), ("cloud", {"text": "graph"})):
        r = w.show("question", quiz)
        e.tick(w.at(w.now - T0 + 3000))
        e.answer(a.id, r.id, answer, w.now)
        w.show("reveal", quiz)
    assert a.streak == 1 and a.score == 1000
    r = w.session.latest("cloud")
    assert r.answers[a.id].correct is None and r.answers[a.id].points == 0


# ------------------------------------------------------------------ views

def test_views_reveal_nothing_early(w):
    e, sid = w.engine, w.session.id
    (a, _), (b, _) = w.join("A", "B")
    r = w.show("question", "pick")
    e.tick(w.at(3000))
    e.answer(a.id, r.id, {"choice": "B"}, w.at(4000))
    host = e.host_view(sid, w.now)["rounds"]["pick"]
    player = e.player_view(a.id, w.now)
    assert host["answered"] == 1 and "results" not in host and "keys" not in host
    assert player["round"]["answer"] == {"choice": "B"}
    assert "result" not in player["round"] and "keys" not in player["round"]
    assert player["round"]["question"]["type"] == "single"
    assert "correct" not in str(player)
    e.skip(sid, "pick", w.at(5000))
    host = e.host_view(sid, w.now)["rounds"]["pick"]
    assert host["results"] == {"answered": 1, "counts": {"A": 0, "B": 1, "C": 0, "D": 0}}
    assert "keys" not in host and "result" not in e.player_view(a.id, w.now)["round"]
    w.show("reveal", "pick")
    host = e.host_view(sid, w.now)["rounds"]["pick"]
    assert host["keys"]["correct"] == ["B"] and host["results"]["correct"] == 1
    mine = e.player_view(a.id, w.now)["round"]
    assert mine["result"] == {"correct": True, "credit": 1.0, "points": 975, "bonus": 0}   # after 1 s
    assert mine["keys"] == {"correct": ["B"]}
    assert e.player_view(b.id, w.now)["round"]["result"]["correct"] is False     # did not answer
    w.show("podium")
    assert e.player_view(b.id, w.now)["standings"][0]["nickname"] == "A"


def test_results_per_question_type(w):
    e, sid = w.engine, w.session.id
    players = [p for p, _ in w.join("A", "B", "C", connected=False)]
    answers = {
        "count": [{"value": 6}, {"value": 4}, {"value": 6}],
        "name": [{"text": "resource description framework"}, {"text": "Resource  Description Framework"},
                 {"text": "RDF"}],
        "steps": [{"order": ["C", "A", "B"]}, {"order": ["A", "C", "B"]}, {"order": ["C", "A", "B"]}],
    }
    results = {}
    for quiz, given in answers.items():
        r = w.show("question", quiz)
        e.tick(w.at(w.now - T0 + 3000))
        for p, ans in zip(players, given):
            e.answer(p.id, r.id, ans, w.now)
        w.show("reveal", quiz)
        results[quiz] = e.host_view(sid, w.now)["rounds"][quiz]["results"]
    assert results["count"] == {"answered": 3, "values": [4, 6, 6], "correct": 2}
    assert results["name"]["groups"] == [{"text": "resource description framework", "count": 2, "correct": True},
                                         {"text": "RDF", "count": 1, "correct": False}]
    assert results["steps"]["positions"]["C"] == [2, 1, 0] and results["steps"]["correct"] == 2


def test_a_bundle_from_texquiz_build(demo_build):
    """The server plays what the builder makes: the demo deck, one round."""
    result, deck, _ = demo_build
    bundles = BundleStore([result.bundle.parent])
    e = Engine(bundles)
    s = e.open_session("demo", result.bundle_id, T0)
    p, _ = e.join(s.pin, "Ada", T0)
    slide = {(b.get("phase"), b.get("item")): x["id"] for x in deck["slides"] for b in x.get("live", [])}
    e.show_slide(s.id, slide[("question", "rdf-triple")], T0)
    r = s.latest("rdf-triple")
    e.tick(T0 + 3000)
    view = e.player_view(p.id, T0 + 3000)["round"]["question"]
    assert [a["id"] for a in view["answers"]] == ["A", "B", "C", "D"] and view["prompt"]["image"].startswith("phone/")
    e.answer(p.id, r.id, {"choice": "B"}, T0 + 3000)
    e.show_slide(s.id, slide[("leaderboard", "rdf-triple")], T0 + 5000)
    assert r.answers[p.id].correct and p.score == 1000
    sparql = bundles.get(result.bundle_id).quizzes["sparql-order"]
    assert sparql.type == "order" and sparql.ids == ["A", "B", "C", "D"] and sparql.keys["order"] != sparql.ids


# ------------------------------------------------------------------ the stage (texstage)

def test_the_stage_screen_and_timer(tmp_path):
    """texstage's presenter window sets what the projector shows - a frozen projector keeps
    the slide shown at the time, while the game follows the lecturer - and runs the timer,
    which a restarted server keeps and the deck's next game takes over (a new game, a
    rebuild), but not the next lecture."""
    db = tmp_path / "texquiz.sqlite3"
    w = World(tmp_path, store_path=db)
    e, sid = w.engine, w.session.id
    assert e.host_view(sid, w.now)["stage"] == {"video": None, "activity": None, "screen": "live", "frozen": None, "frozen_board": None,
                                                "timer": {"since": None, "elapsed": 0, "target": None},
                                                "zoom": None, "board": None, "boards": [],
                                                "poll": None, "sketches": None, "question": None}
    w.show("join")
    e.screen(sid, "freeze", w.at(1000))
    r = w.show("question", "pick")
    stage = e.host_view(sid, w.now)["stage"]
    assert stage["screen"] == "freeze" and stage["frozen"] == w.bundle.slide("join") and r is not None
    e.screen(sid, "black", w.now)
    assert e.host_view(sid, w.now)["stage"]["frozen"] is None
    e.screen(sid, "live", w.now)
    assert "screen" not in w.session.stage
    with pytest.raises(GameError, match="the screen is"):
        e.screen(sid, "purple", w.now)
    e.timer(sid, "start", None, w.at(10_000))
    e.timer(sid, "start", None, w.at(20_000))                          # running already
    e.timer(sid, "pause", None, w.at(70_000))
    e.timer(sid, "target", 5400, w.now)
    assert w.session.stage["timer"] == {"since": None, "elapsed": 60_000, "target": 5_400_000}
    e.timer(sid, "start", None, w.at(80_000))
    for bad in (("rewind", None), ("target", -1), ("target", 10**6)):
        with pytest.raises(GameError):
            e.timer(sid, *bad, w.now)
    timer = {"since": T0 + 80_000, "elapsed": 60_000, "target": 5_400_000}
    e.store.close()
    e2 = Engine(w.bundles, Store(db), Settings())                       # the server restarts
    assert e2.sessions[sid].stage["timer"] == timer
    new = e2.restart(sid, w.at(90_000))
    assert new.stage == {"timer": timer}                                # a new game: the timer goes on
    rebuilt = make_bundle(tmp_path / "bundles", title="Test deck v2")   # rebuilt during the lecture
    w.bundles.scanned = 0
    again = e2.open_session(rebuilt.deck, rebuilt.id, w.at(95_000))
    assert again is not new and again.stage == {"timer": timer}
    later = e2.open_session(rebuilt.deck, rebuilt.id, w.now + Settings().stale_ms)
    assert later is not again and later.stage == {}                     # the next lecture: from 0


def test_ink_on_the_frames(tmp_path):
    """Ink belongs to a frame of the game: begin, points in batches, end; erase, clear, and
    undo and redo per device; a restarted server keeps the strokes, a new game of the same
    build takes them over, a rebuild starts without."""
    db = tmp_path / "texquiz.sqlite3"
    w = World(tmp_path, store_path=db)
    e, sid = w.engine, w.session.id
    pen = {"id": "a1", "tool": "pen", "color": "#E21B3C", "width": 0.004, "sim": False}
    begun = e.ink_begin(sid, "laptop", "3", pen, [[0.1, 0.2, 0.5]], w.at(1000))
    assert begun["op"] == "begin" and begun["stroke"]["color"] == "#e21b3c"
    loaded = e.ink_load(sid, "3")
    assert loaded["strokes"] == [] and [s["id"] for s in loaded["drawing"]] == ["a1"]
    assert e.ink_points(sid, "a1", [[0.123456, 0.2, 0.61], [0.13, 0.21, 0.7]])["points"] == [
        [0.1235, 0.2, 0.61], [0.13, 0.21, 0.7]]
    assert e.ink_end(sid, "a1", w.now) == {"op": "end", "frame": "3", "stroke": "a1"}
    e.ink_begin(sid, "laptop", "3", {**pen, "id": "a2", "tool": "highlighter"}, [[0.5, 0.5, 0.5]], w.now)
    e.ink_end(sid, "a2", w.now)
    e.ink_begin(sid, "ipad", "board:0123abcd", {**pen, "id": "b1"}, [[0.5, 0.5, 0.5]], w.now)
    e.ink_end(sid, "b1", w.now)
    strokes = e.ink_load(sid, "3")["strokes"]
    assert [s["id"] for s in strokes] == ["a1", "a2"] and strokes[0]["points"] == [
        [0.1, 0.2, 0.5], [0.1235, 0.2, 0.61], [0.13, 0.21, 0.7]]
    assert e.ink_undo(sid, "laptop", "3", w.now) == {"op": "erase", "frame": "3", "strokes": ["a2"]}
    assert e.ink_undo(sid, "ipad", "3", w.now) is None                      # undo is per device
    redone = e.ink_redo(sid, "laptop", "3", w.now)
    assert redone["op"] == "restore" and [s["id"] for s in redone["strokes"]] == ["a2"]
    assert e.ink_erase(sid, "laptop", "3", ["a1", "zz"], w.now) == {"op": "erase", "frame": "3", "strokes": ["a1"]}
    assert e.ink_clear(sid, "laptop", "3", w.now)["strokes"] == ["a2"]
    assert [s["id"] for s in e.ink_undo(sid, "laptop", "3", w.now)["strokes"]] == ["a2"]   # the clear undone
    for frame, meta, points in (("3", pen, []),                              # the id is in use
                                ("frame 3", {**pen, "id": "x"}, []),
                                ("3", {**pen, "id": "x", "color": "red"}, []),
                                ("3", {**pen, "id": "x", "tool": "spray"}, []),
                                ("3", {**pen, "id": "x"}, [[0.1, 0.2]]),
                                ("3", {**pen, "id": "x"}, [[0.1, 0.2, 7]])):
        with pytest.raises(GameError):
            e.ink_begin(sid, "laptop", frame, meta, points, w.now)
    with pytest.raises(GameError):
        e.ink_points(sid, "a1", [[0.1, 0.1, 0.5]])                          # ended already
    e.store.close()
    e2 = Engine(w.bundles, Store(db), Settings())                           # the server restarts
    assert [s["id"] for s in e2.ink_load(sid, "3")["strokes"]] == ["a2"]
    assert [s["id"] for s in e2.ink_load(sid, "board:0123abcd")["strokes"]] == ["b1"]
    new = e2.restart(sid, w.at(5000))
    assert [s["id"] for s in e2.ink_load(new.id, "3")["strokes"]] == ["a2"]   # the same build: taken over
    rebuilt = make_bundle(tmp_path / "bundles", title="Test deck v2")
    w.bundles.scanned = 0
    again = e2.open_session(rebuilt.deck, rebuilt.id, w.at(6000))
    assert again.id != new.id and e2.ink_load(again.id, "3")["strokes"] == []   # a rebuild: none


def test_zoom_and_whiteboard_pages(w):
    """The zoom stays on its slide and ends with it; a whiteboard page goes after a frame,
    the projector shows it until the next slide of the deck."""
    e, sid = w.engine, w.session.id
    w.show("join")
    e.zoom(sid, {"x": 0.9, "y": -1, "w": 0.25, "h": 0.25}, w.now)
    assert e.host_view(sid, w.now)["stage"]["zoom"] == {"x": 0.75, "y": 0.0, "w": 0.25, "h": 0.25}
    w.show("join")                                                          # the same slide again
    assert w.session.stage["zoom"]
    w.show("question", "pick")
    assert "zoom" not in w.session.stage
    board = e.board_add(sid, 3, "grid", w.now)
    e.zoom(sid, {"x": 0, "y": 0, "w": 0.5, "h": 0.5}, w.now)
    e.go_board(sid, board, w.now)
    stage = e.host_view(sid, w.now)["stage"]
    assert stage["board"] == board and stage["boards"] == [{"id": board, "after": 3, "kind": "grid"}]
    assert stage["zoom"] is None
    e.screen(sid, "freeze", w.now)                                          # frozen on the page
    assert e.host_view(sid, w.now)["stage"]["frozen_board"] == board
    e.screen(sid, "live", w.now)
    assert "frozen_board" not in w.session.stage
    w.show("reveal", "pick")
    assert e.host_view(sid, w.now)["stage"]["board"] is None
    for after, kind in ((3, "dots"), (-1, "blank"), ("3", "blank")):
        with pytest.raises(GameError):
            e.board_add(sid, after, kind, w.now)
    with pytest.raises(GameError):
        e.go_board(sid, "nope", w.now)
    with pytest.raises(GameError):
        e.zoom(sid, {"x": 0}, w.now)


def test_a_new_presentation_or_the_lecture_continued(tmp_path):
    """A presenter window that opens a deck with ink or whiteboard pages from before asks: a new
    presentation is a new game without them - they stay with the game that ends -, and the
    continuation of a lecture that ended gets copies of its ink and pages."""
    db = tmp_path / "texquiz.sqlite3"
    w = World(tmp_path, store_path=db)
    e, s = w.engine, w.session
    deck, bid = w.bundle.deck, w.bundle.id
    assert e.earlier(s.id) is None                                          # nothing to ask about

    def draw(sid, stroke, frame):
        e.ink_begin(sid, "laptop", frame, {"id": stroke, "tool": "pen", "color": "#123456", "width": 0.005,
                                           "sim": True}, [[0.1, 0.2, 0.5]], w.now)
        e.ink_end(sid, stroke, w.now)

    w.show("join")
    draw(s.id, "a1", "2")
    board = e.board_add(s.id, 3, "grid", w.at(60_000))
    draw(s.id, "a2", f"board:{board}")
    assert e.open_session(deck, bid, w.at(3_600_000)) is s                 # an hour later: the same game
    assert e.earlier(s.id) == {"game": s.id, "open": True, "at": T0 + 60_000, "frames": 2, "boards": 1}
    new = e.fresh(s.id, w.at(3_601_000))                                    # a new presentation
    assert s.ended and new.pin != s.pin and e.marks(new) == (0, 0) and "timer" not in new.stage
    assert e.earlier(new.id) == {"game": s.id, "open": False, "at": T0 + 3_600_000, "frames": 2, "boards": 1}
    later = e.open_session(deck, bid, w.at(3_601_000 + Settings().stale_ms))   # the next lecture
    assert later is not new and new.ended and e.earlier(later.id)["game"] == s.id   # (new had nothing)
    assert e.take_over(later.id, s.id, w.now) == {"frames": 2, "boards": 1}   # it continues that lecture
    assert later.stage["boards"] == [{"id": board, "after": 3, "kind": "grid"}]
    copies = e.ink_all(later.id)["frames"]
    assert sorted(copies) == ["2", f"board:{board}"] and copies["2"][0]["id"].startswith("a1-")
    with pytest.raises(GameError, match="of its own"):
        e.take_over(later.id, s.id, w.now)                                  # once
    e.store.close()
    e2 = Engine(w.bundles, Store(db), Settings())                           # a restarted server
    assert e2.ink_all(later.id)["frames"].keys() == copies.keys()
    assert sorted(st.id for st in e2.store.load_strokes([s.id])) == ["a1", "a2"]   # the old lecture keeps its own
    newest = e2.fresh(later.id, w.at(4_000_000 + Settings().stale_ms))
    for game in ("nope", newest.id, None):                                  # not an ended game of the deck
        with pytest.raises(GameError, match="no earlier lecture"):
            e2.take_over(newest.id, game, w.now)
    e2.store.close()


# ------------------------------------------------------------------ texstage M6: polls, sketches, questions

def test_ad_hoc_polls(tmp_path):
    """A poll the lecturer types is a quiz of the game: asked at once (the phones get its
    texts), shown on the projector instead of the slide, revealed when it closes - after the
    grace period for late answers -, in the results table; a restarted server keeps it."""
    db = tmp_path / "texquiz.sqlite3"
    w = World(tmp_path, store_path=db)
    e, sid = w.engine, w.session.id
    (a, token_a), (b, _), (c, _) = w.join("A", "B", "C")
    w.show("join")
    for bad in ({"kind": "essay"}, {"kind": "choice", "answers": ["only one"]}, {"kind": "words"},
                {"kind": "yesno", "time": 2}, {"kind": "choice", "prompt": "x" * 301}, {"kind": "choice", "select": "all"}):
        with pytest.raises(GameError):
            e.poll_create(sid, bad, w.now)
    quiz = e.poll_create(sid, {"kind": "choice", "prompt": "Which is  $O(n \\log n)$?\n\n Sorting",
                               "answers": ["Merge sort", "", "Bubble sort"], "time": 20}, w.at(1000))
    assert quiz == "poll-1" and w.session.stage["poll"] == quiz
    q = e.player_view(a.id, w.now)["round"]["question"]
    assert q["prompt"] == {"text": "Which is $O(n \\log n)$?\nSorting"} and q["adhoc"] == "choice"
    assert [(x["id"], x["shape"], x["text"]) for x in q["answers"]] == [("A", 1, "Merge sort"), ("B", 2, ""), ("C", 3, "Bubble sort")]
    host = e.host_view(sid, w.now)
    assert host["polls"][quiz]["answers"][0]["text"] == "Merge sort" and host["rounds"][quiz]["phase"] == "get-ready"
    rid = w.session.latest(quiz).id
    e.tick(w.at(4000))
    e.answer(a.id, rid, {"choice": "A"}, w.at(5000))
    e.answer(b.id, rid, {"choice": "A"}, w.at(6000))
    assert e.next_deadline() == T0 + 24000
    e.tick(w.at(24000))
    r = w.session.rounds[rid]
    assert r.phase == "closed" and e.next_deadline() == T0 + 24000 + Settings().grace_ms
    e.answer(c.id, rid, {"choice": "C"}, w.at(24300))                   # late, but within the grace
    e.tick(w.at(24600))
    assert r.phase == "revealed"                                         # no reveal slide: by itself
    assert e.host_view(sid, w.now)["rounds"][quiz]["results"]["counts"] == {"A": 2, "B": 0, "C": 1}
    assert e.player_view(a.id, w.now)["round"]["result"]["correct"] is None and a.score == 0
    words = e.poll_create(sid, {"kind": "words", "prompt": "One word?"}, w.at(30000))
    assert words == "poll-2" and w.session.stage["poll"] == words
    e.skip(sid, words, w.at(31000))                                      # stopped: revealed at once
    assert w.session.latest(words).phase == "revealed"
    e.poll_show(sid, quiz, w.now)                                        # the first one again
    assert e.host_view(sid, w.now)["stage"]["poll"] == quiz
    with pytest.raises(GameError):
        e.poll_show(sid, "pick", w.now)                                  # a quiz of the deck, not a poll
    w.show("question", "pick")                                           # going on ends it
    assert "poll" not in w.session.stage
    header, *rows = e.results_table(sid)
    assert header[-6:] == ["poll-1 answer", "poll-1 correct", "poll-1 points", "poll-2 answer", "poll-2 correct",
                           "poll-2 points"]
    assert {row[1]: row[-6] for row in rows} == {"A": "A", "B": "A", "C": "C"}
    e.store.close()
    e2 = Engine(w.bundles, Store(db), Settings())                        # the server restarts
    s2 = e2.sessions[sid]
    assert list(s2.polls) == [quiz, words] and e2.quiz(s2, quiz).type == "poll"
    assert e2.host_view(sid, w.now)["rounds"][quiz]["results"]["counts"]["A"] == 2
    scale = e2.poll_create(sid, {"kind": "scale"}, w.at(40000))
    assert [x["text"] for x in e2.sessions[sid].polls[scale]["public"]["answers"]] == ["1", "2", "3", "4", "5"]


def test_sketch_questions(tmp_path):
    """A sketch question - of the deck or ad hoc -: the phones send their drawing; the
    presenter window gets them numbered in the order they came, and picks some for the
    projector, which gets their strokes."""
    w = World(tmp_path, quizzes={"draw": ("sketch", {"scored": False, "points": "none"}, {})})
    e, sid = w.engine, w.session.id
    (a, _), (b, _), (c, _) = w.join("A", "B", "C")
    r = w.show("question", "draw")
    e.tick(w.at(3000))
    line = {"strokes": [{"c": 0, "p": [10, 20, 500, 400]}, {"c": 2, "p": [999, 749]}]}
    for bad in ({"strokes": []}, {"strokes": [{"c": 0, "p": [1, 2, 3]}]}, {"strokes": [{"c": 4, "p": [1, 2]}]},
                {"strokes": [{"c": 0, "p": [1001, 2]}]}, {"strokes": [{"c": 0, "p": [1, 751]}]},
                {"strokes": [{"c": 0, "p": [1.5, 2]}]}, {"strokes": [{"p": [1, 2] * 3001}]}, {"text": "a cat"}):
        with pytest.raises(GameError, match="sketch|stroke|points"):
            e.answer(a.id, r.id, bad, w.now)
    e.answer(b.id, r.id, line, w.at(4000))
    e.answer(a.id, r.id, {"strokes": [{"p": [1, 1, 2, 2]}]}, w.at(5000))
    e.answer(c.id, r.id, line, w.at(6000))
    got = e.sketch_list(sid, "draw")
    assert [(x["n"], x["player"]) for x in got["sketches"]] == [(1, b.id), (2, a.id), (3, c.id)]
    assert got["sketches"][1]["strokes"] == [{"c": 0, "p": [1, 1, 2, 2]}]                     # colour 0 made explicit
    assert [x["n"] for x in e.sketch_list(sid, "draw", after=2)["sketches"]] == [3]
    assert "sketches" not in e.host_view(sid, w.now)["rounds"]["draw"].get("results", {})    # the counts only
    with pytest.raises(GameError):
        e.sketch_list(sid, "pick")                                       # not a sketch question
    for bad in ([a.id, a.id], ["nobody"], [a.id] * 13, [[a.id]], "x"):
        with pytest.raises(GameError):
            e.sketch_show(sid, "draw", bad, w.now)
    e.sketch_show(sid, "draw", [c.id, b.id], w.now)
    assert e.host_view(sid, w.now)["stage"]["sketches"] == {"quiz": "draw", "players": [c.id, b.id]}
    shown = e.sketch_get(sid, "draw", [c.id, b.id])["sketches"]
    assert [(x["n"], x["player"]) for x in shown] == [(1, b.id), (3, c.id)] and shown[0]["strokes"] == line["strokes"]
    quiz = e.poll_create(sid, {"kind": "sketch", "prompt": "Draw a B+ tree"}, w.at(10000))  # ad hoc
    assert e.quiz(w.session, quiz).type == "sketch" and "sketches" not in w.session.stage   # the poll instead
    e.sketch_show(sid, "draw", [a.id], w.now)
    assert "poll" not in w.session.stage
    e.go_board(sid, e.board_add(sid, 2, "blank", w.now), w.now)          # going on ends it
    assert "sketches" not in w.session.stage
    e.sketch_show(sid, "draw", [a.id], w.now)
    e.sketch_show(sid, "draw", [], w.now)
    assert "sketches" not in w.session.stage
    assert {row[1]: row[5] for row in e.results_table(sid)[1:]} == {"A": "(sketch)", "B": "(sketch)", "C": "(sketch)"}
    e.kick(sid, a.id, w.now)
    assert [x["n"] for x in e.sketch_list(sid, "draw")["sketches"]] == [1, 3]


def test_sketch_cursors_survive_removal_reveal_restart_and_a_new_round(tmp_path):
    db = tmp_path / "texquiz.sqlite3"
    w = World(tmp_path, store_path=db, quizzes={"draw": ("sketch", {"scored": False, "points": "none"}, {})})
    e, sid = w.engine, w.session.id
    people = [p for p, _ in w.join("A", "B", "C", "D")]
    # Arrival order remains stable even when several answers have the same millisecond.
    a, b, c, d = sorted(people, key=lambda p: p.id, reverse=True)
    r = w.show("question", "draw")
    line = {"strokes": [{"p": [10, 20, 30, 40]}]}
    for p in (a, b, c):
        e.answer(p.id, r.id, line, w.at(4000))
    first = e.sketch_list(sid, "draw")
    assert [(x["n"], x["player"]) for x in first["sketches"]] == [(1, a.id), (2, b.id), (3, c.id)]
    e.sketch_show(sid, "draw", [a.id], w.now)
    e.kick(sid, a.id, w.at(4500))
    assert "sketches" not in w.session.stage
    with pytest.raises(GameError):
        e.sketch_show(sid, "draw", [a.id], w.now)
    e.answer(d.id, r.id, line, w.at(5000))
    delta = e.sketch_list(sid, "draw", after=first["cursor"], round_id=r.id)
    assert [(x["n"], x["player"]) for x in delta["sketches"]] == [(4, d.id)]
    assert delta["active"] == [b.id, c.id, d.id] and delta["cursor"] == 4
    assert [x["n"] for x in e.sketch_get(sid, "draw", [b.id, d.id])["sketches"]] == [2, 4]
    e.reveal(sid, "draw", w.at(6000))
    e.store.close()
    e = Engine(w.bundles, Store(db), Settings())
    try:
        assert [x["n"] for x in e.sketch_list(sid, "draw")["sketches"]] == [2, 3, 4]
        assert [n for _, n, _ in e.sketch_answers(sid)] == [2, 3, 4]
        again = e.again(sid, "draw", w.at(7000))
        e.answer(b.id, again.id, line, w.at(11000))
        changed = e.sketch_list(sid, "draw", after=4, round_id=r.id)
        assert changed["round"] == again.id and changed["cursor"] == 1
        assert [(x["n"], x["player"]) for x in changed["sketches"]] == [(1, b.id)]
    finally:
        e.store.close()


def test_old_answer_rows_receive_persistent_submission_numbers(tmp_path):
    db = tmp_path / "texquiz.sqlite3"
    w = World(tmp_path, store_path=db, quizzes={"draw": ("sketch", {"scored": False, "points": "none"}, {})})
    (a, _), (b, _) = w.join("A", "B")
    r = w.show("question", "draw")
    line = {"strokes": [{"p": [10, 20]}]}
    w.engine.answer(b.id, r.id, line, w.at(4000))
    w.engine.answer(a.id, r.id, line, w.at(5000))
    w.engine.store.db.execute("ALTER TABLE answers DROP COLUMN sequence")  # a file from before this field
    w.engine.store.close()
    e = Engine(w.bundles, Store(db), Settings())
    try:
        assert [(x["n"], x["player"]) for x in e.sketch_list(w.session.id, "draw")["sketches"]] == [(1, b.id), (2, a.id)]
        assert sorted(row[0] for row in e.store.db.execute("SELECT sequence FROM answers")) == [1, 2]
    finally:
        e.store.close()


def test_questions_from_the_audience(tmp_path):
    """Questions from the phones, while the lecturer has them open: anonymous, upvoted, by
    votes; one on the projector; done, deleted, or the asker blocked. A restarted server keeps
    them; a new game keeps the questions open, not the old game's questions."""
    db = tmp_path / "texquiz.sqlite3"
    w = World(tmp_path, store_path=db)
    e, sid = w.engine, w.session.id
    (a, token_a), (b, _), (c, _) = w.join("A", "B", "C")
    assert e.player_view(a.id, w.now, questions=True)["qa"] == {"open": False}
    with pytest.raises(GameError, match="closed"):
        e.qa_ask(a.id, "Why?", w.now)
    e.qa_open(sid, True, w.now)
    for bad in ("", "   ", "x" * 281, 42):
        with pytest.raises(GameError):
            e.qa_ask(a.id, bad, w.now)
    qa1 = e.qa_ask(a.id, "  Why is $\\bowtie$\u0007 associative? ", w.at(1000))
    assert qa1.text == "Why is $\\bowtie$ associative?"
    with pytest.raises(GameError, match="every 20 seconds"):
        e.qa_ask(a.id, "And?", w.at(2000))
    qa2 = e.qa_ask(b.id, "Is this in the exam?", w.at(3000))
    with pytest.raises(GameError, match="own"):
        e.qa_vote(a.id, qa1.id, True, w.now)
    assert e.qa_vote(b.id, qa1.id, True, w.now) and e.qa_vote(c.id, qa1.id, True, w.now)
    assert not e.qa_vote(c.id, qa1.id, True, w.now)                    # once
    e.qa_vote(c.id, qa2.id, True, w.now)
    e.qa_vote(c.id, qa2.id, False, w.now)                              # taken back
    seen = e.player_view(c.id, w.now, questions=True)["qa"]
    assert seen["open"] and [(x["text"], x["votes"], x["voted"], x["mine"]) for x in seen["questions"]] == [
        ("Why is $\\bowtie$ associative?", 2, True, False), ("Is this in the exam?", 0, False, False)]
    assert "questions" not in e.player_view(c.id, w.now)["qa"]          # only to a phone that shows them
    host = e.host_view(sid, w.now)["qa"]
    assert host["open"] and [x["id"] for x in host["questions"]] == [qa1.id, qa2.id]
    assert not any("player" in x or "mine" in x for x in host["questions"])   # nobody's name
    e.qa_show(sid, qa1.id, w.now)
    assert e.host_view(sid, w.now)["stage"]["question"] == {"id": qa1.id, "text": qa1.text, "votes": 2}
    e.qa_mark(sid, qa1.id, "done", w.now)
    assert e.host_view(sid, w.now)["stage"]["question"] is None
    with pytest.raises(GameError, match="answered"):
        e.qa_vote(b.id, qa1.id, False, w.now)
    assert [x["state"] for x in e.host_view(sid, w.now)["qa"]["questions"]] == ["open", "done"]   # done ones last
    e.qa_ask(b.id, "Can you go slower?", w.at(30_000))
    e.qa_show(sid, qa2.id, w.now)
    e.qa_block(sid, qa2.id, w.now)                                     # b asks no more, b's questions go
    assert b.muted and e.host_view(sid, w.now)["stage"]["question"] is None
    assert [x["text"] for x in e.host_view(sid, w.now)["qa"]["questions"]] == [qa1.text]
    assert e.player_view(b.id, w.now)["qa"] == {"open": False}
    with pytest.raises(GameError, match="closed questions for you"):
        e.qa_ask(b.id, "Hello?", w.at(60_000))
    with pytest.raises(GameError):
        e.qa_show(sid, qa2.id, w.now)                                  # deleted
    e.store.close()
    e2 = Engine(w.bundles, Store(db), Settings())                      # the server restarts
    s2 = e2.sessions[sid]
    assert [(q.text, q.state, len(q.votes)) for q in s2.questions.values()] == [
        (qa1.text, "done", 2), ("Is this in the exam?", "deleted", 0), ("Can you go slower?", "deleted", 0)]
    assert s2.players[b.id].muted and e2.player_view(a.id, w.now)["qa"]["open"]
    new = e2.restart(sid, w.at(70_000))
    assert new.stage.get("qa") is True and new.questions == {}


# ------------------------------------------------------------------ restart recovery

def test_a_restarted_server_continues(tmp_path):
    db = tmp_path / "texquiz.sqlite3"
    w = World(tmp_path, store_path=db)
    e = w.engine
    (a, token_a), (b, _) = w.join("A", "B")
    r = w.show("question", "pick")
    e.tick(w.at(3000))
    e.answer(a.id, r.id, {"choice": "B"}, w.at(5000))
    pin, sid, rid = w.session.pin, w.session.id, r.id
    e.store.close()
    # the server stops and starts again, after the time limit
    e2 = Engine(w.bundles, Store(db), Settings())
    s = e2.sessions[sid]
    assert s.pin == pin and s.current == rid
    a2 = e2.player_by_token(token_a)
    assert a2.nickname == "A" and a2.connections == 0
    r2 = s.rounds[rid]
    assert r2.phase == "open" and r2.answers[a2.id].payload == {"choice": "B"}
    assert e2.next_deadline() == T0 + 23000
    assert e2.tick(T0 + 60000) == [sid] and r2.phase == "closed" and r2.closed == T0 + 23000
    e2.show_slide(sid, w.bundle.slide("reveal", "pick"), T0 + 61000)
    assert a2.score == 950 and a2.rank == 1
    assert e2.open_session(w.bundle.deck, w.bundle.id, T0 + 62000).id == sid     # the same game
    e2.store.close()
    e3 = Engine(w.bundles, Store(db), Settings())
    assert e3.player_by_token(token_a).score == 950 and e3.sessions[sid].rounds[rid].phase == "revealed"
    assert e3.sessions[sid].rounds[rid].answers[a2.id].points == 950           # a number, as before
    assert e3.results_table(sid)[1][:8] == [1, "A", 950, 1, 1, "B", 1, 950]
    e3.restart(sid, T0 + 70000)
    e3.store.close()
    e4 = Engine(w.bundles, Store(db), Settings())
    assert sid not in e4.sessions and len(e4.sessions) == 1
    with pytest.raises(GameError):
        e4.player_by_token(token_a)                         # a new game: join again
