# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The server over HTTP and WebSocket (server/app.py): the protocol, pushes, the pictures,
restart recovery. Synthetic bundles (fake_bundle.py), get-ready off, real time."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fake_bundle import make_bundle
from texstage.server.app import ServerConfig, create_app
from texstage.server.game import Settings

KEY = "presenter-secret"


def config(tmp_path: Path) -> ServerConfig:
    return ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                        presenter_key=KEY, settings=Settings(get_ready_ms=0))


@pytest.fixture
def world(tmp_path):
    fb = make_bundle(tmp_path / "bundles")
    with TestClient(create_app(config(tmp_path))) as client:
        yield client, fb


def test_plugin_worker_keeps_connection_and_nested_worker_restrictions(world):
    client, _ = world
    response = client.get("/static/stage/plugin-evaluator-worker.js")
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; "
        "connect-src 'none'; worker-src 'none'"
    )
    assert response.headers["cache-control"] == "no-cache"


def recv(ws, t: str | None = None, until=None, limit: int = 60) -> dict:
    """The next message of type t (and matching `until`); states may be coalesced, so wait
    for the one that shows what the test expects."""
    for _ in range(limit):
        m = ws.receive_json()
        if (t is None or m["t"] == t) and (until is None or until(m)):
            return m
    raise AssertionError(f"no {t} message")


def hello(ws, fb, mid=1) -> dict:
    ws.send_json({"t": "hello", "role": "host", "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": mid})
    return recv(ws, "welcome")


def join(ws, pin, nickname) -> dict:
    ws.send_json({"t": "join", "pin": pin, "nickname": nickname, "id": "join"})
    return recv(ws, "welcome")


def round_phase(phase, quiz=None):
    if quiz:
        return lambda m: m.get("rounds", {}).get(quiz, {}).get("phase") == phase
    return lambda m: m.get("round") and m["round"]["phase"] == phase


def test_a_round_over_websockets(world):
    client, fb = world
    with client.websocket_connect("/ws") as h:
        h.send_json({"t": "hello", "role": "host", "key": "wrong", "deck": fb.deck, "bundle": fb.id, "id": 1})
        assert recv(h, "error")["error"] == "bad-key"
        pin = hello(h, fb, 2)["pin"]
        state = recv(h, "state")
        assert state["session"]["join"] == f"http://quiz.test/play?pin={pin}"
        assert state["session"]["qr"] == f"/join/{pin}.svg"
        with client.websocket_connect("/ws") as p1, client.websocket_connect("/ws") as p2:
            w1 = join(p1, pin, "Ada")
            assert w1["nickname"] == "Ada" and w1["token"]
            join(p2, pin, "Bob")
            recv(h, "state", until=lambda m: m["session"]["connected"] == 2)
            h.send_json({"t": "slide", "slide": fb.slide("question", "pick"), "id": 3})
            assert recv(h, "ok")["re"] == 3
            s1 = recv(p1, "state", until=round_phase("open"))
            assert s1["round"]["question"]["type"] == "single" and s1["session"]["base"] == f"/bundle/{fb.id}/"
            assert "correct" not in json.dumps(s1) and "keys" not in s1["round"]
            rid = s1["round"]["id"]
            p1.send_json({"t": "answer", "round": rid, "answer": {"choice": "B"}, "id": "a1"})
            assert recv(p1, "ok")["answer"] == {"choice": "B"}
            p1.send_json({"t": "answer", "round": rid, "answer": {"choice": "B"}, "id": "a1"})   # a retry
            assert recv(p1, until=lambda m: m["t"] in ("ok", "error"))["t"] == "ok"
            p2.send_json({"t": "answer", "round": rid, "answer": {"choice": "A"}, "id": "a2"})
            recv(p2, "ok")
            closed = recv(h, "state", until=round_phase("closed", "pick"))["rounds"]["pick"]   # all answered
            assert closed["results"]["counts"] == {"A": 1, "B": 1, "C": 0, "D": 0} and "keys" not in closed
            h.send_json({"t": "slide", "slide": fb.slide("reveal", "pick"), "id": 4})
            mine = recv(p1, "state", until=round_phase("revealed"))
            assert mine["round"]["result"]["correct"] is True and mine["round"]["result"]["points"] > 900
            assert mine["round"]["keys"] == {"correct": ["B"]} and mine["me"]["rank"] == 1
            assert recv(p2, "state", until=round_phase("revealed"))["round"]["result"]["correct"] is False
            board = recv(h, "state", until=round_phase("revealed", "pick"))
            assert [p["nickname"] for p in board["players"]] == ["Ada", "Bob"]
            assert board["rounds"]["pick"]["keys"]["correct"] == ["B"]


def test_answer_counter_pushes_on_phone_disconnect_and_resume(world):
    client, fb = world
    with client.websocket_connect("/ws") as h, client.websocket_connect("/ws") as bob:
        pin = hello(h, fb)["pin"]
        join(bob, pin, "Bob")

        def counter(connected, answered, awaiting, phase="open"):
            state = recv(h, "state", until=lambda m: m["session"]["connected"] == connected
                         and m.get("rounds", {}).get("pick", {}).get("answered") == answered)
            r = state["rounds"]["pick"]
            assert (r["awaiting"], r["phase"]) == (awaiting, phase)
            return r

        with client.websocket_connect("/ws") as cara:
            c = join(cara, pin, "Cara")
            with client.websocket_connect("/ws") as ada:
                a = join(ada, pin, "Ada")
                h.send_json({"t": "slide", "slide": fb.slide("question", "pick")})
                rid = counter(3, 0, 3)["id"]
                ada.send_json({"t": "answer", "round": rid, "answer": {"choice": "B"}})
                recv(ada, "ok")
                counter(3, 1, 2)
            counter(2, 1, 2)                 # an answered phone leaves; the total stays at three
            with client.websocket_connect("/ws") as resumed:
                resumed.send_json({"t": "resume", "token": a["token"]})
                assert recv(resumed, "welcome")["player"] == a["player"]
                assert recv(resumed, "state")["round"]["answer"] == {"choice": "B"}
                counter(3, 1, 2)             # resuming does not double-count the answer
            counter(2, 1, 2)
        counter(1, 1, 1)                     # an unanswered phone leaves; the total drops to two
        with client.websocket_connect("/ws") as resumed:
            resumed.send_json({"t": "resume", "token": c["token"]})
            assert recv(resumed, "welcome")["player"] == c["player"]
            counter(2, 1, 2)                 # resuming an unanswered player restores the total
            bob.send_json({"t": "answer", "round": rid, "answer": {"choice": "B"}})
            recv(bob, "ok")
            counter(2, 2, 1)                 # two answers and two online still means one pending
            resumed.send_json({"t": "answer", "round": rid, "answer": {"choice": "B"}})
            recv(resumed, "ok")
            closed = counter(2, 3, 0, "closed")
            assert closed["closed_by"] == "all" and closed["results"]["answered"] == 3


def test_the_timer_closes_the_question(tmp_path):
    fb = make_bundle(tmp_path / "bundles", time=1)
    with TestClient(create_app(config(tmp_path))) as client, \
            client.websocket_connect("/ws") as h, client.websocket_connect("/ws") as p:
        pin = hello(h, fb)["pin"]
        join(p, pin, "Ada")
        h.send_json({"t": "slide", "slide": fb.slide("question", "pick")})
        opened = recv(p, "state", until=round_phase("open"))
        assert 0 < opened["round"]["deadline"] - opened["now"] <= 1000
        closed = recv(p, "state", until=round_phase("closed"))     # pushed by the server's timer
        assert closed["now"] >= opened["round"]["deadline"]


def test_preparing_over_websockets(world):
    """The add-in's prepare command: the question slide it shows starts no round, the host
    view says so; after prepare off the same slide starts it."""
    client, fb = world
    with client.websocket_connect("/ws") as h:
        hello(h, fb)
        h.send_json({"t": "prepare", "on": True, "id": "p1"})
        assert recv(h, "ok")["re"] == "p1"
        assert recv(h, "state", until=lambda m: m["session"]["preparing"])
        h.send_json({"t": "slide", "slide": fb.slide("question", "pick"), "id": "s1"})
        recv(h, "ok")
        h.send_json({"t": "prepare", "on": False, "id": "p2"})
        assert recv(h, "state", until=lambda m: not m["session"]["preparing"])["rounds"] == {}
        h.send_json({"t": "slide", "slide": fb.slide("question", "pick"), "id": "s2"})
        recv(h, "state", until=lambda m: "pick" in m["rounds"])


def test_host_commands_and_retries(world):
    client, fb = world
    with client.websocket_connect("/ws") as h, client.websocket_connect("/ws") as p:
        pin = hello(h, fb)["pin"]
        welcome = join(p, pin, "Ada")
        h.send_json({"t": "slide", "slide": fb.slide("question", "pick")})
        for _ in range(2):                                   # the same command id twice: once
            h.send_json({"t": "extend", "quiz": "pick", "seconds": 10, "id": "e1"})
            recv(h, "ok")
        assert recv(h, "state", until=lambda m: "pick" in m["rounds"])["rounds"]["pick"]["limit"] == 30000
        h.send_json({"t": "pause", "id": "p"})
        assert recv(h, "state", until=lambda m: m["rounds"]["pick"]["paused"])["rounds"]["pick"]["paused"]
        h.send_json({"t": "continue", "id": "c"})
        h.send_json({"t": "skip", "quiz": "pick", "id": "s"})
        recv(h, "state", until=round_phase("closed", "pick"))
        h.send_json({"t": "again", "quiz": "pick", "id": "g"})
        assert recv(h, "error")["error"] == "busy"            # not revealed yet
        h.send_json({"t": "rename", "player": welcome["player"], "nickname": "Countess", "id": "r"})
        assert recv(p, "state", until=lambda m: m["me"]["nickname"] == "Countess")
        h.send_json({"t": "kick", "player": welcome["player"], "id": "k"})
        assert recv(p, "bye")["reason"] == "kicked"
        h.send_json({"t": "restart", "id": "n"})
        new = recv(h, "ok", until=lambda m: m["re"] == "n")
        assert new["pin"] != pin
        assert recv(h, "state", until=lambda m: m["session"]["pin"] == new["pin"])["session"]["players"] == 0


def test_join_retry_recovers_a_lost_welcome_without_claiming_another_player(world):
    """A reconnect retries its secret nonce, not its guessable request id or nickname."""
    client, fb = world
    with client.websocket_connect("/ws") as h:
        pin = hello(h, fb)["pin"]
        request = {"t": "join", "pin": pin, "nickname": "Ada", "id": "join", "join_nonce": "a1" * 16}
        with client.websocket_connect("/ws") as first:
            first.send_json(request)
            original = recv(first, "welcome")       # imagine the phone lost this welcome before storing it
        with client.websocket_connect("/ws") as retry:
            retry.send_json(request)
            recovered = recv(retry, "welcome")
            assert recovered["player"] == original["player"] and recovered["token"] == original["token"]
            assert recv(retry, "state")["me"]["players"] == 1
            with client.websocket_connect("/ws") as stranger:
                for forged in ({**request, "join_nonce": "b2" * 16},
                               {k: v for k, v in request.items() if k != "join_nonce"}):
                    stranger.send_json(forged)
                    assert recv(stranger, "error")["error"] == "nickname-taken"
                for changed in ({**request, "nickname": "Bob"}, {**request, "pin": "000000"}):
                    stranger.send_json(changed)
                    assert recv(stranger, "error")["error"] == "invalid"
                for nonce in ([], 42, "guess", "A" * 32):
                    stranger.send_json({**request, "join_nonce": nonce})
                    assert recv(stranger, "error")["error"] == "invalid"
            h.send_json({"t": "kick", "player": original["player"]})
            assert recv(retry, "bye")["reason"] == "kicked"
        with client.websocket_connect("/ws") as kicked:
            kicked.send_json(request)
            assert recv(kicked, "error")["error"] == "kicked"


def test_join_replay_cache_is_bounded_and_expires(tmp_path, monkeypatch):
    from texstage.server import app

    fb = make_bundle(tmp_path / "bundles")
    server = app.Server(config(tmp_path))
    try:
        session = server.engine.open_session(fb.deck, fb.id, 0)
        monkeypatch.setattr(app, "JOIN_REPLAY_MAX", 2)
        requests = [{"pin": session.pin, "nickname": str(n), "join_nonce": f"{n:032x}"} for n in range(3)]
        joined = [server._join(request, n) for n, request in enumerate(requests)]
        assert len(server.join_replies) == 2
        assert server._join(requests[-1], 3) == joined[-1]
        with pytest.raises(app.GameError, match="nickname is taken"):
            server._join(requests[0], 4)                 # the oldest entry was evicted
        with pytest.raises(app.GameError, match="nickname is taken"):
            server._join(requests[-1], app.JOIN_REPLAY_MS + 2)
        assert not server.join_replies
        assert server.engine.player_by_token(joined[-1][1]) is joined[-1][0]  # normal resume still works
        newer = {"pin": session.pin, "nickname": "new", "join_nonce": "f" * 32}
        server._join(newer, app.JOIN_REPLAY_MS + 3)
        server.engine.end(session.id, app.JOIN_REPLAY_MS + 4)
        with pytest.raises(app.GameError, match="join the game again"):
            server._join(newer, app.JOIN_REPLAY_MS + 5)
    finally:
        server.store.close()


def test_bad_messages_get_errors_not_crashes(world):
    client, fb = world
    with client.websocket_connect("/ws") as ws:
        ws.send_text("not json")
        assert recv(ws, "error")["error"] == "bad-json"
        ws.send_json({"t": "answer", "round": "x", "answer": {}})
        assert recv(ws, "error")["error"] == "hello-first"
        ws.send_json({"t": "hello", "role": "host", "key": ["x"]})
        assert recv(ws, "error")["error"] == "bad-key"
        ws.send_text("x" * 20000)
        assert recv(ws, "error")["error"] == "too-large"
        ws.send_json({"t": "ping", "id": 7})
        assert recv(ws, "pong")["re"] == 7
        pin = hello(ws, fb)["pin"]
        ws.send_json({"t": "slide", "slide": "first", "id": 8})
        assert recv(ws, "error")["error"] == "invalid"
        ws.send_json({"t": "kick", "player": ["x"], "id": 9})
        assert recv(ws, "error")["error"] == "unknown-player"
    with client.websocket_connect("/ws") as p:
        join(p, pin, "Ada")
        p.send_json({"t": "answer", "round": [1], "answer": {"choice": "A"}, "id": 1})
        assert recv(p, "error")["error"] == "unknown-round"
        p.send_json({"t": "slide", "slide": 256, "id": 2})
        assert recv(p, "error")["error"] == "unknown-command"     # players cannot drive the game


def test_http(world, tmp_path):
    client, fb = world
    status = client.get("/api/status").json()
    assert status["bundles"] == 1 and status["join"] == "http://quiz.test/play"
    assert status["instance"] == client.app.state.server.instance      # which server an address leads to
    assert client.get("/api/presenter-key").status_code == 403         # not from this machine
    phone = next((fb.path / "phone").iterdir()).name
    r = client.get(f"/bundle/{fb.id}/phone/{phone}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    for path in (f"/bundle/{fb.id}/phone/keys.json", f"/bundle/{fb.id}/x/{phone}", f"/bundle/0000/phone/{phone}",
                 f"/bundle/{fb.id}/deck.json", "/join/12ab56.svg"):
        assert client.get(path).status_code == 404, path
    svg = client.get("/join/123456.svg")
    assert svg.status_code == 200 and svg.text.lstrip().startswith("<?xml")
    local = TestClient(client.app, client=("127.0.0.1", 50000))      # the app runs already
    assert local.get("http://localhost:8470/api/presenter-key").json() == {"key": KEY}


def test_pages_and_the_host_api(world):
    client, fb = world
    assert client.get("/", follow_redirects=False).headers["location"] == "/play"
    for path in ("/play", "/host"):
        r = client.get(path)
        assert r.status_code == 200 and 'type="module"' in r.text and r.headers["cache-control"] == "no-cache"
    for path in ("shared/client.js", "shared/live.js", "shared/shapes.js", "shared/live.css",
                 "play/play.js", "play/play.css", "host/host.js", "host/host.css"):
        r = client.get(f"/static/{path}")
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", path
    key = {"X-Texquiz-Key": KEY}
    for path in ("/api/decks", f"/api/deck/{fb.id}", "/api/results/x.csv"):
        assert client.get(path).status_code == 403, path                       # hosts only
        assert client.get(path, headers={"X-Texquiz-Key": "wrong"}).status_code == 403, path
    decks = client.get("/api/decks", headers=key).json()
    assert [(d["bundle"], d["game"]) for d in decks] == [(fb.id, None)]
    deck = client.get(f"/api/deck/{fb.id}", headers=key).json()
    assert deck["bundle"] == fb.id and "correct" not in json.dumps(deck["quizzes"])
    with client.websocket_connect("/ws") as h, client.websocket_connect("/ws") as p:
        pin = hello(h, fb)["pin"]
        sid = recv(h, "state")["session"]["id"]
        join(p, pin, "Ada")
        h.send_json({"t": "slide", "slide": fb.slide("question", "pick")})
        rid = recv(p, "state", until=round_phase("open"))["round"]["id"]
        p.send_json({"t": "answer", "round": rid, "answer": {"choice": "B"}, "id": "a"})
        recv(p, "ok")
        h.send_json({"t": "slide", "slide": fb.slide("reveal", "pick")})
        recv(p, "state", until=round_phase("revealed"))
    assert client.get("/api/decks", headers=key).json()[0]["game"] == {"pin": pin, "players": 1, "session": sid}
    r = client.get(f"/api/results/{sid}.csv", headers=key)
    assert f"-{pin}.csv" in r.headers["content-disposition"] and r.headers["content-type"].startswith("text/csv")
    rows = [line.split(",") for line in r.text.lstrip("﻿").splitlines()]
    assert rows[0][:5] == ["rank", "nickname", "score", "correct", "answered"]
    assert rows[1][:5] == ["1", "Ada", rows[1][2], "1", "1"] and int(rows[1][2]) > 900
    assert rows[1][5:8] == ["B", "1", rows[1][2]]                       # pick: answer, correct, points


def test_the_presenter_and_projector_windows(world):
    """texstage: the presenter window (role stage) drives the game as a host does and sets
    what the projector shows and the timer; the projector window (display) gets the same host
    view and can send nothing."""
    client, fb = world
    with client.websocket_connect("/ws") as st, client.websocket_connect("/ws") as dp:
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1})
        w = recv(st, "welcome")
        dp.send_json({"t": "hello", "role": "display", "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1})
        assert w["role"] == "stage" and recv(dp, "welcome")["session"] == w["session"]      # the same game
        s = recv(dp, "state")
        assert s["role"] == "display" and s["stage"] == {
            "video": None, "activity": None, "screen": "live", "frozen": None, "frozen_board": None,
            "timer": {"since": None, "elapsed": 0, "target": None}, "zoom": None, "board": None, "boards": [],
            "poll": None, "sketches": None, "question": None}
        question = fb.slide("question", "pick")
        st.send_json({"t": "slide", "slide": question, "id": 2})
        recv(dp, "state", until=lambda m: "pick" in m["rounds"])             # the game follows
        st.send_json({"t": "screen", "screen": "freeze", "id": 3})
        s = recv(dp, "state", until=lambda m: m["stage"]["screen"] == "freeze")
        assert s["stage"]["frozen"] == question
        st.send_json({"t": "timer", "action": "start", "id": 4})
        st.send_json({"t": "timer", "action": "target", "seconds": 5400, "id": 5})
        s = recv(dp, "state", until=lambda m: m["stage"]["timer"]["target"])
        assert s["stage"]["timer"]["since"] and s["stage"]["timer"]["target"] == 5_400_000
        st.send_json({"t": "screen", "screen": "purple", "id": 6})
        assert recv(st, "error", until=lambda m: m["re"] == 6)["error"] == "invalid"
        dp.send_json({"t": "slide", "slide": question, "id": 2})
        assert recv(dp, "error")["error"] == "read-only"                   # the projector only shows
    key = {"X-Texquiz-Key": KEY}
    assert [d["stage"] for d in client.get("/api/decks", headers=key).json()] == [False]   # no --stage build
    for path in ("/stage", "/stage/projector"):
        r = client.get(path)
        assert r.status_code == 200 and 'type="module"' in r.text and r.headers["cache-control"] == "no-cache"
    for path in ("stage/presenter.js", "stage/projector.js", "stage/pdfview.js", "stage/ink.js", "stage/export.js",
                 "stage/record.js", "stage/split.js", "stage/ask.js", "stage/pen.js", "stage/stage.css", "vendor/pdfjs/pdf.min.mjs", "vendor/pdfjs/pdf.worker.min.mjs",
                 "vendor/perfect-freehand/index.mjs", "vendor/pdf-lib/pdf-lib.esm.min.js"):
        r = client.get(f"/static/{path}")
        assert r.status_code == 200, path
        assert ("javascript" if path.endswith("js") else "css") in r.headers["content-type"], path   # modules


def test_ink_pointer_and_whiteboard_pages_reach_the_projector(world):
    """What the presenter window draws reaches the projector window while it is drawn; the
    projector window loads a frame's ink; the pointer goes along, unanswered; whiteboard
    pages and the zoom are part of the state."""
    client, fb = world
    with client.websocket_connect("/ws") as st, client.websocket_connect("/ws") as dp:
        for ws, role in ((st, "stage"), (dp, "display")):
            ws.send_json({"t": "hello", "role": role, "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1})
            recv(ws, "welcome")
        pen = {"id": "s1", "tool": "pen", "color": "#000000", "width": 0.004, "sim": True}
        st.send_json({"t": "ink.begin", "device": "laptop", "frame": "2", "stroke": pen,
                      "points": [[0.1, 0.1, 0.5]], "id": 2})
        begun = recv(dp, "ink")
        assert begun["op"] == "begin" and begun["stroke"]["id"] == "s1" and begun["frame"] == "2"
        st.send_json({"t": "ink.points", "stroke": "s1", "points": [[0.2, 0.2, 0.5]], "id": 3})
        assert recv(dp, "ink")["points"] == [[0.2, 0.2, 0.5]]
        st.send_json({"t": "ink.end", "stroke": "s1", "id": 4})
        assert recv(dp, "ink")["op"] == "end"
        dp.send_json({"t": "ink.load", "frame": "2", "id": 5})
        loaded = recv(dp, "ok", until=lambda m: m["re"] == 5)
        assert [s["points"] for s in loaded["strokes"]] == [[[0.1, 0.1, 0.5], [0.2, 0.2, 0.5]]]
        st.send_json({"t": "pointer", "x": 0.5, "y": 0.25})
        assert recv(dp, "pointer") == {"t": "pointer", "x": 0.5, "y": 0.25}
        for _ in range(2):                         # with an id: answered (the next may go), never from the cache
            st.send_json({"t": "pointer", "x": 0.75, "y": 0.5, "id": 50})
            assert recv(st, "ok", until=lambda m: m["re"] == 50) == {"t": "ok", "re": 50}
            assert recv(dp, "pointer") == {"t": "pointer", "x": 0.75, "y": 0.5}
        st.send_json({"t": "ink.undo", "device": "laptop", "frame": "2", "id": 6})
        assert recv(st, "ok", until=lambda m: m["re"] == 6)["event"]["strokes"] == ["s1"]
        assert recv(dp, "ink")["op"] == "erase"
        st.send_json({"t": "board", "after": 2, "kind": "blank", "id": 7})
        board = recv(st, "ok", until=lambda m: m["re"] == 7)["board"]
        st.send_json({"t": "go", "board": board, "id": 8})
        recv(dp, "state", until=lambda m: m["stage"]["board"] == board)
        st.send_json({"t": "zoom", "rect": {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5}, "id": 9})
        recv(dp, "state", until=lambda m: m["stage"]["zoom"] == {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5})
        dp.send_json({"t": "screen", "screen": "black", "id": 10})
        assert recv(dp, "error")["error"] == "read-only"
        st.send_json({"t": "ink.points", "stroke": "nope", "points": [], "id": 11})
        assert recv(st, "error", until=lambda m: m["re"] == 11)["error"] == "invalid"


def test_the_projector_window_draws_with_a_pen(world):
    """A pen display in the hall shows the projector window (pen.js): its pen draws and erases
    there, under the presenter window's name, so the presenter window's undo and redo take it,
    and its side button moves the laser pointer; the projector window sends nothing else."""
    client, fb = world
    with client.websocket_connect("/ws") as st, client.websocket_connect("/ws") as dp:
        for ws, role in ((st, "stage"), (dp, "display")):
            ws.send_json({"t": "hello", "role": role, "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1})
            recv(ws, "welcome")
        pen = {"id": "p1", "tool": "pen", "color": "#e21b3c", "width": 0.005, "sim": False}
        dp.send_json({"t": "ink.begin", "device": "laptop", "frame": "2", "stroke": pen,
                      "points": [[0.1, 0.1, 0.5]], "id": 2})
        assert recv(st, "ink")["op"] == "begin"
        dp.send_json({"t": "ink.points", "stroke": "p1", "points": [[0.3, 0.3, 0.6]], "id": 3})
        assert recv(st, "ink")["points"] == [[0.3, 0.3, 0.6]]
        dp.send_json({"t": "ink.end", "stroke": "p1", "id": 4})
        assert recv(st, "ink")["op"] == "end"
        recv(dp, "ok", until=lambda m: m["re"] == 4)
        st.send_json({"t": "ink.undo", "device": "laptop", "frame": "2", "id": 5})         # the presenter's undo
        assert recv(st, "ok", until=lambda m: m["re"] == 5)["event"]["strokes"] == ["p1"]
        assert recv(dp, "ink")["op"] == "erase"
        st.send_json({"t": "ink.redo", "device": "laptop", "frame": "2", "id": 6})
        recv(st, "ok", until=lambda m: m["re"] == 6)
        assert recv(dp, "ink")["op"] == "restore"
        dp.send_json({"t": "ink.erase", "device": "laptop", "frame": "2", "strokes": ["p1"], "id": 7})   # its eraser end
        assert recv(st, "ink")["op"] == "erase"
        dp.send_json({"t": "pointer", "x": 0.25, "y": 0.5})                       # its side button: the laser
        assert recv(st, "pointer") == {"t": "pointer", "x": 0.25, "y": 0.5}
        dp.send_json({"t": "pointer", "off": True})
        assert recv(st, "pointer") == {"t": "pointer", "off": True}
        for n, t in enumerate(("screen", "ink.clear", "ink.undo", "slide", "zoom", "board"), 8):
            dp.send_json({"t": t, "id": n})
            assert recv(dp, "error", until=lambda m: m["re"] == n)["error"] == "read-only", t


def test_the_decks_built_on_this_machine(tmp_path):
    """texstage build records its folders in the data folder (builds.py), and the server with
    that data folder serves those decks too - also one built while it runs, the stage PDF
    included: no upload (a lecture's deck is too large for its PowerPoint file to bring)."""
    from texstage.builds import build_folders, remember_build
    cfg = config(tmp_path)                                   # serves tmp/bundles: nothing there
    first = make_bundle(tmp_path / "ch01" / "build" / "texquiz", deck="ch01", stage=True)
    remember_build(tmp_path / "ch01" / "build" / "texquiz", cfg.data_dir)
    with TestClient(create_app(cfg)) as client:
        auth = {"X-Texquiz-Key": KEY}
        assert client.get(f"/api/deck/{first.id}", headers=auth).status_code == 200
        later = make_bundle(tmp_path / "ch02" / "build" / "texquiz", deck="ch02", title="Chapter two")
        remember_build(tmp_path / "ch02" / "build" / "texquiz", cfg.data_dir)     # built while it runs
        decks = {d["bundle"]: d for d in client.get("/api/decks", headers=auth).json()}
        assert {first.id, later.id} <= set(decks) and decks[first.id]["stage"] and decks[first.id]["complete"]
    shutil.rmtree(tmp_path / "ch02")                                              # a folder that is gone
    remember_build(tmp_path / "ch01" / "build" / "texquiz", cfg.data_dir)         # recorded once, the newest last
    assert build_folders(cfg.data_dir) == [(tmp_path / "ch01" / "build" / "texquiz").resolve()]


def test_a_new_presentation_or_the_lecture_continued(world):
    """A presenter window that opens a deck learns of the ink and whiteboard pages from before
    and of the other presenter windows (its welcome); lecture.new starts a new game without
    them, lecture.continue copies those of an ended game; the other windows load their ink anew."""
    client, fb = world
    there = {"t": "hello", "role": "stage", "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1}
    with client.websocket_connect("/ws") as st, client.websocket_connect("/ws") as dp:
        st.send_json(there)
        first = recv(st, "welcome")
        assert first["earlier"] is None and first["presenters"] == 0
        dp.send_json({**there, "role": "display"})
        assert "earlier" not in recv(dp, "welcome")
        pen = {"id": "s1", "tool": "pen", "color": "#000000", "width": 0.004, "sim": True}
        st.send_json({"t": "ink.begin", "device": "laptop", "frame": "2", "stroke": pen, "points": [[0.1, 0.1, 0.5]], "id": 2})
        st.send_json({"t": "ink.end", "stroke": "s1", "id": 3})
        recv(st, "ok", until=lambda m: m["re"] == 3)
        dp.send_json({"t": "lecture.new", "id": 2})
        assert recv(dp, "error", until=lambda m: m["re"] == 2)["error"] == "read-only"
        with client.websocket_connect("/ws") as again:                     # Present in a second window
            again.send_json(there)
            w = recv(again, "welcome")
            assert w["earlier"]["open"] and w["earlier"]["frames"] == 1 and w["presenters"] == 1
            again.send_json({"t": "lecture.new", "id": "a2"})                # (the windows' ids differ)
            assert recv(again, "ok", until=lambda m: m["re"] == "a2")["pin"] != first["pin"]
            for ws in (st, dp):                                             # the others: ink anew
                recv(ws, "ink", until=lambda m: m["op"] == "reload")
            dp.send_json({"t": "ink.load", "frame": "2", "id": 3})
            assert recv(dp, "ok", until=lambda m: m["re"] == 3)["strokes"] == []    # the new game: none
            again.send_json({"t": "lecture.continue", "game": first["session"], "id": "a3"})
            assert recv(again, "ok", until=lambda m: m["re"] == "a3") == {"t": "ok", "re": "a3", "frames": 1, "boards": 0}
            recv(dp, "ink", until=lambda m: m["op"] == "reload")
            dp.send_json({"t": "ink.load", "frame": "2", "id": 4})
            assert recv(dp, "ok", until=lambda m: m["re"] == 4)["strokes"][0]["id"].startswith("s1-")
            again.send_json({"t": "lecture.continue", "game": first["session"], "id": "a4"})
            assert recv(again, "error", until=lambda m: m["re"] == "a4")["error"] == "invalid"


def test_the_lecture_archive(world, tmp_path):
    """texstage M4: the game's ink in one message (for the annotated PDF); the presenter window
    puts the PDF into the lecture archive - <data>/archive/<deck>/<date>-<pin>/, with the
    results - and gets the folder as one ZIP."""
    import io
    import zipfile
    client, fb = world
    key = {"X-Texquiz-Key": KEY}
    with client.websocket_connect("/ws") as st:
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1})
        welcome = recv(st, "welcome")
        sid, pin = welcome["session"], welcome["pin"]
        pen = {"id": "s1", "tool": "pen", "color": "#e21b3c", "width": 0.005, "sim": False}
        st.send_json({"t": "ink.begin", "device": "laptop", "frame": "2", "stroke": pen, "points": [[0.1, 0.1, 0.5]], "id": 2})
        st.send_json({"t": "ink.end", "stroke": "s1", "id": 3})
        st.send_json({"t": "ink.all", "id": 4})
        frames = recv(st, "ok", until=lambda m: m["re"] == 4)["frames"]
        assert list(frames) == ["2"] and frames["2"][0]["id"] == "s1"
    url = f"/api/archive/{sid}/annotated.pdf"
    assert client.put(url, content=b"%PDF-1.7 ink").status_code == 403
    assert client.put(url, content=b"no PDF", headers=key).status_code == 400
    kept = client.put(url, content=b"%PDF-1.7 ink", headers=key).json()
    assert kept["folder"].startswith("archive/test/") and kept["folder"].endswith(f"-{pin}")
    assert (tmp_path / "data" / kept["folder"] / "annotated.pdf").read_bytes() == b"%PDF-1.7 ink"
    csv = next(f for f in kept["files"] if f.endswith(".csv"))
    assert kept["files"] == sorted(["annotated.pdf", csv]) and csv.startswith("test-")
    z = client.get(f"/api/archive/{sid}.zip", headers=key)
    assert z.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(z.content)) as archive:
        assert sorted(archive.namelist()) == sorted(["annotated.pdf", csv])
        assert archive.read(csv).decode("utf-8-sig").startswith("rank,nickname")
    assert client.get("/api/archive/nope.zip", headers=key).status_code == 404


def test_a_recording_comes_in_parts(tmp_path):
    """texstage M5: a recording reaches the server in parts while it is made - each taken once
    and in order, also by a restarted server, and a part half-written when the server stopped
    is written again -; it is finished when it stops, stays in the folder of the game it
    started in, and is downloaded through an address that expires. Its lecturer's only."""
    import hashlib
    import io
    import zipfile
    fb = make_bundle(tmp_path / "bundles")
    key, ben = {"X-Texquiz-Key": KEY}, {"X-Texquiz-Key": "ben-key"}
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "lecturers.json").write_text(
        json.dumps({"ben": {"key": hashlib.sha256(b"ben-key").hexdigest()}}), encoding="utf-8")
    with TestClient(create_app(config(tmp_path))) as client:
        with client.websocket_connect("/ws") as st:
            sid = hello(st, fb)["session"]
        assert client.get(f"/api/archive/{sid}/files", headers=key).json() == []
        assert not (tmp_path / "data" / "archive").exists()                       # a look makes no folder
        start = f"/api/archive/{sid}/recording"
        assert client.post(start, json={"ext": "webm"}).status_code == 403
        assert client.post(start, json={"ext": "webm"}, headers=ben).status_code == 404      # not ben's game
        assert client.post(start, json={"ext": "avi"}, headers=key).status_code == 400
        r = client.post(start, json={"ext": "webm"}, headers=key)
        assert r.status_code == 201
        take, folder = r.json()["take"], tmp_path / "data" / r.json()["folder"]
        assert r.json()["file"] == f"recording-{take}.webm" and folder.parent.parent.name == "archive"

        def part(n, data, headers=key, c=client):
            return c.put(f"/api/recording/{take}/{n}", content=data, headers=headers)
        assert part(0, b"\x1aE\xdf\xa3head").json() == {"next": 1, "size": 8}
        assert part(0, b"\x1aE\xdf\xa3head").json() == {"next": 1, "size": 8}      # sent again: taken once
        late = part(2, b"late")
        assert late.status_code == 409 and late.json()["next"] == 1                  # part 1 is missing
        assert part(1, b"-body", headers=ben).status_code == 404                     # ben's key: no such recording
        assert part(1, b"-body", headers={}).status_code == 403
        assert part(1, b"-body").json() == {"next": 2, "size": 13}
        listed = client.get(f"/api/archive/{sid}/files", headers=key).json()
        assert listed == [{"name": f"recording-{take}.webm", "size": 13, "take": take, "unfinished": True}]
        assert client.post(f"/api/recording/{take}/download", headers=key).status_code == 409   # not finished
    with (folder / f"recording-{take}.webm.part").open("ab") as f:
        f.write(b"half a part")                                 # the server stopped while writing part 2
    with TestClient(create_app(config(tmp_path))) as client:
        server = client.app.state.server
        assert part(2, b"-tail", c=client).json() == {"next": 3, "size": 18}       # where it was
        done = client.post(f"/api/recording/{take}/done", headers=key).json()
        assert done["file"] == f"recording-{take}.webm" and done["finished"] and done["parts"] == 3
        job = server.recordings.remuxing.get(take)
        if job:
            job.join(30)                                        # ffmpeg does not take this as WebM
        assert (folder / f"recording-{take}.webm").read_bytes() == b"\x1aE\xdf\xa3head-body-tail"
        assert sorted(p.name for p in folder.iterdir()) == [f"recording-{take}.json", f"recording-{take}.webm"]
        assert client.post(f"/api/recording/{take}/done", headers=key).json()["finished"] == done["finished"]
        assert part(3, b"more", c=client).status_code == 409                        # finished
        url = client.post(f"/api/recording/{take}/download", headers=key).json()["url"]
        assert url.startswith("/download/") and url.endswith(".webm") and "test-" in url
        r = client.get(url)
        assert r.content == b"\x1aE\xdf\xa3head-body-tail" and r.headers["content-type"] == "video/webm"
        assert r.headers["content-disposition"].startswith("attachment") and "no-store" in r.headers["cache-control"]
        assert client.get(url.replace("/download/", "/download/x")).status_code == 404
        assert client.post(f"/api/recording/{take}/download", headers=ben).status_code == 404
        z = client.get(f"/api/archive/{sid}.zip", headers=key)
        with zipfile.ZipFile(io.BytesIO(z.content)) as zipped:
            assert not [n for n in zipped.namelist() if n.startswith("recording")]   # downloaded on its own
        empty = client.post(start, json={"ext": "mp4"}, headers=key).json()["take"]
        assert client.post(f"/api/recording/{empty}/done", headers=key).json() == {"take": empty, "file": None, "size": 0}
        assert client.get(f"/api/recording/{empty}", headers=key).status_code == 404   # nothing was kept


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_finished_recording_is_remuxed(world, tmp_path):
    """A recording as browsers write it - a live WebM, no duration, no seek index (cues) - is
    copied through ffmpeg once it is finished: the same streams, with both."""
    client, fb = world
    live = tmp_path / "live.webm"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=duration=3:size=320x180:rate=10", "-c:v", "libvpx", "-b:v", "200k",
                    "-f", "webm", "-live", "1", str(live)], check=True)
    data = live.read_bytes()
    assert b"\x1c\x53\xbb\x6b" not in data                     # no cues
    key = {"X-Texquiz-Key": KEY}
    with client.websocket_connect("/ws") as st:
        sid = hello(st, fb)["session"]
    r = client.post(f"/api/archive/{sid}/recording", json={"ext": "webm"}, headers=key).json()
    take, folder = r["take"], tmp_path / "data" / r["folder"]
    third = len(data) // 3 + 1
    for n in range(3):
        assert client.put(f"/api/recording/{take}/{n}", content=data[n * third:(n + 1) * third], headers=key).json()["next"] == n + 1
    assert client.post(f"/api/recording/{take}/done", headers=key).status_code == 200
    job = client.app.state.server.recordings.remuxing.get(take)
    if job:
        job.join(60)
    fixed = (folder / f"recording-{take}.webm").read_bytes()
    assert b"\x1c\x53\xbb\x6b" in fixed
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(folder / f"recording-{take}.webm")], capture_output=True, text=True)
    assert abs(float(probe.stdout) - 3.0) < 0.3
    assert not client.get(f"/api/recording/{take}", headers=key).json()["remuxing"]


def test_polls_questions_and_sketches(tmp_path):
    """texstage M6 over WebSockets: the presenter window asks a poll (the phone gets it, the
    projector shows it instead of the slide, the results come by themselves); a phone asks and
    upvotes questions - it gets the list only while it shows it -, the presenter window puts
    one on the projector and blocks an asker; a sketch question: the gallery, two sketches on
    the projector, whose window fetches their strokes. The archive keeps it all."""
    import io
    import zipfile
    fb = make_bundle(tmp_path / "bundles", quizzes={"draw": ("sketch", {"scored": False, "points": "none"}, {})})
    key = {"X-Texquiz-Key": KEY}
    with TestClient(create_app(config(tmp_path))) as client, client.websocket_connect("/ws") as st, \
            client.websocket_connect("/ws") as dp, client.websocket_connect("/ws") as ph, \
            client.websocket_connect("/ws") as ph2:
        for ws, role in ((st, "stage"), (dp, "display")):
            ws.send_json({"t": "hello", "role": role, "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1})
            w = recv(ws, "welcome")
        sid, pin = w["session"], w["pin"]
        ada = join(ph, pin, "Ada")["player"]
        join(ph2, pin, "Bob")
        st.send_json({"t": "poll.create", "kind": "yesno", "prompt": "Ready for $\\sigma$?", "time": 10, "id": 2})
        quiz = recv(st, "ok", until=lambda m: m["re"] == 2)["quiz"]
        s = recv(dp, "state", until=lambda m: m["stage"]["poll"] == quiz)
        assert s["polls"][quiz]["prompt"] == {"text": "Ready for $\\sigma$?"}
        r = recv(ph, "state", until=lambda m: m["round"] and m["round"]["phase"] == "open", limit=200)["round"]
        assert [a["text"] for a in r["question"]["answers"]] == ["Yes", "No"]
        ph.send_json({"t": "answer", "round": r["id"], "answer": {"choice": "A"}, "id": 3})
        recv(ph, "ok")
        st.send_json({"t": "skip", "quiz": quiz, "id": 3})
        recv(ph, "state", until=lambda m: m["round"]["phase"] == "revealed")       # no reveal slide needed
        assert recv(dp, "state", until=lambda m: m["rounds"][quiz]["phase"] == "revealed")[
            "rounds"][quiz]["results"]["counts"] == {"A": 1, "B": 0}
        st.send_json({"t": "poll.show", "quiz": None, "id": 4})
        recv(dp, "state", until=lambda m: m["stage"]["poll"] is None)

        ph.send_json({"t": "qa.ask", "text": "Why?", "id": 5})
        assert recv(ph, "error")["error"] == "qa-closed"
        st.send_json({"t": "qa.open", "on": True, "id": 5})
        assert recv(ph, "state", until=lambda m: m["qa"]["open"])["qa"] == {"open": True}   # no list yet
        ph.send_json({"t": "qa.watch", "on": True, "id": 6})
        assert recv(ph, "state", until=lambda m: "questions" in m["qa"])["qa"]["questions"] == []
        ph2.send_json({"t": "qa.ask", "text": "Is $x^2$ convex?", "id": 6})
        qid = recv(ph2, "ok", until=lambda m: m["re"] == 6)["question"]
        assert recv(ph, "state", until=lambda m: m["qa"].get("questions"))["qa"]["questions"][0]["text"] == "Is $x^2$ convex?"
        ph.send_json({"t": "qa.vote", "question": qid, "on": True, "id": 7})
        recv(ph, "state", until=lambda m: m["qa"]["questions"][0]["voted"])
        host = recv(st, "state", until=lambda m: m["qa"]["questions"] and m["qa"]["questions"][0]["votes"] == 1)
        assert "player" not in host["qa"]["questions"][0]
        st.send_json({"t": "qa.show", "question": qid, "id": 8})
        assert recv(dp, "state", until=lambda m: m["stage"]["question"])["stage"]["question"]["text"] == "Is $x^2$ convex?"
        st.send_json({"t": "qa.mark", "question": qid, "state": "done", "id": 9})
        recv(dp, "state", until=lambda m: m["stage"]["question"] is None)
        ph.send_json({"t": "qa.ask", "text": "Spam", "id": 10})
        spam = recv(ph, "ok", until=lambda m: m["re"] == 10)["question"]
        st.send_json({"t": "qa.block", "question": spam, "id": 10})
        recv(ph, "state", until=lambda m: not m["qa"]["open"])                   # blocked: no more asking

        st.send_json({"t": "slide", "slide": fb.slide("question", "draw"), "id": 11})
        r = recv(ph2, "state", until=lambda m: m["round"] and m["round"]["phase"] == "open", limit=200)["round"]
        drawing = {"strokes": [{"c": 1, "p": [100, 100, 900, 650]}]}
        ph2.send_json({"t": "answer", "round": r["id"], "answer": drawing, "id": 12})
        recv(ph2, "ok", until=lambda m: m["re"] == 12)
        ph.send_json({"t": "answer", "round": r["id"], "answer": {"strokes": [{"p": [5, 5]}]}, "id": 13})
        recv(ph, "ok", until=lambda m: m["re"] == 13)
        st.send_json({"t": "sketch.list", "quiz": "draw", "id": 14})
        gallery = recv(st, "ok", until=lambda m: m["re"] == 14)["sketches"]
        assert [x["n"] for x in gallery] == [1, 2]     # as they came; the same millisecond: by player (test_game)
        bobs, adas = sorted(gallery, key=lambda x: x["player"] == ada)
        assert bobs["strokes"] == drawing["strokes"] and adas["strokes"] == [{"c": 0, "p": [5, 5]}]
        st.send_json({"t": "sketch.show", "quiz": "draw", "players": [gallery[1]["player"], gallery[0]["player"]],
                      "id": 15})
        shown = recv(dp, "state", until=lambda m: m["stage"]["sketches"])["stage"]["sketches"]
        dp.send_json({"t": "sketch.get", **shown, "id": 16})
        got = recv(dp, "ok", until=lambda m: m["re"] == 16)["sketches"]
        assert [x["n"] for x in got] == [1, 2] and ada in [x["player"] for x in got]
        dp.send_json({"t": "sketch.show", "quiz": "draw", "players": [], "id": 17})
        assert recv(dp, "error")["error"] == "read-only"
    with TestClient(create_app(config(tmp_path))) as client:                    # restarted: all kept
        z = client.get(f"/api/archive/{sid}.zip", headers=key)
        with zipfile.ZipFile(io.BytesIO(z.content)) as zipped:
            names = sorted(zipped.namelist())
            assert {"polls.csv", "questions.csv", "sketch-draw-1.svg", "sketch-draw-2.svg"} <= set(names)
            polls = zipped.read("polls.csv").decode("utf-8-sig")
            assert "Ready for $\\sigma$?" in polls and "A 1 · B 0" in polls
            questions = zipped.read("questions.csv").decode("utf-8-sig")
            assert "Is $x^2$ convex?,1,done," in questions and "Spam" not in questions
            svg = zipped.read(f"sketch-draw-{bobs['n']}.svg").decode("utf-8")      # numbered as in the gallery
            assert svg.startswith("<svg") and 'points="100,100 900,650" stroke="#e21b3c"' in svg


def test_serve_present_opens_the_presenter_once_the_server_answers(monkeypatch):
    import contextlib
    import webbrowser

    from texstage import cli
    asked, opened = [], []

    def urlopen(url, timeout):
        asked.append(url)
        if len(asked) < 3:
            raise OSError("not listening yet")
        return contextlib.nullcontext()
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(webbrowser, "open", opened.append)
    cli.open_when_up("http://localhost:8470/stage")
    assert asked == ["http://localhost:8470/api/status"] * 3 and opened == ["http://localhost:8470/stage"]


def test_the_stage_pdf_is_for_hosts_only(tmp_path):
    """texstage's PDF (texstage build --stage) holds every reveal page: with the presenter
    key only, never at a picture's address; a build without --stage has none."""
    fb = make_bundle(tmp_path / "bundles", stage=True)
    plain = make_bundle(tmp_path / "bundles", title="Plain deck")
    with TestClient(create_app(config(tmp_path))) as client:
        url = f"/api/deck/{fb.id}/pdf"
        assert client.get(url).status_code == 403
        assert client.get(url, headers={"X-Texquiz-Key": "wrong"}).status_code == 403
        r = client.get(url, headers={"X-Texquiz-Key": KEY})
        assert r.status_code == 200 and r.content == fb.pdf
        assert r.headers["content-type"] == "application/pdf" and r.headers["cache-control"].startswith("private")
        name = json.loads((fb.path / "deck.json").read_text(encoding="utf-8"))["pdf"]["file"]
        assert client.get(f"/bundle/{fb.id}/{name}").status_code == 404
        assert client.get(f"/api/deck/{plain.id}/pdf", headers={"X-Texquiz-Key": KEY}).status_code == 404


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_page_scripts_parse():
    for js in sorted((Path(__file__).resolve().parents[1] / "src" / "texstage" / "web").rglob("*.js")):
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        assert r.returncode == 0, f"{js.name}: {r.stderr}"


def test_a_restarted_server_continues(tmp_path):
    fb = make_bundle(tmp_path / "bundles")
    with TestClient(create_app(config(tmp_path))) as client, \
            client.websocket_connect("/ws") as h, client.websocket_connect("/ws") as p:
        pin = hello(h, fb)["pin"]
        token = join(p, pin, "Ada")["token"]
        h.send_json({"t": "slide", "slide": fb.slide("question", "pick")})
        rid = recv(p, "state", until=round_phase("open"))["round"]["id"]
    # the server stops (the phone loses its connection) and starts again
    with TestClient(create_app(config(tmp_path))) as client, \
            client.websocket_connect("/ws") as h, client.websocket_connect("/ws") as p:
        p.send_json({"t": "resume", "token": token, "id": "r"})
        assert recv(p, "welcome")["nickname"] == "Ada"
        state = recv(p, "state")
        assert state["round"]["id"] == rid and state["round"]["phase"] == "open"
        p.send_json({"t": "answer", "round": rid, "answer": {"choice": "B"}, "id": "a"})
        recv(p, "ok")
        assert hello(h, fb)["pin"] == pin                        # the same game
        p.send_json({"t": "resume", "token": "not-a-token", "id": "x"})
        assert recv(p, "error")["error"] == "unknown-player"


def test_bundles_of_format_2_and_1(tmp_path):
    """The server reads format 2 (since 2026-10-10: the content types, their items, the slides'
    live boxes) - and format 1, the builds of before (fake_bundle.py makes those). A deck that
    needs a content type this server does not know is refused when it is found, saying so."""
    from texstage.build.bundle import bundle_id
    from texstage.server.bundles import BundleError, load_bundle

    def write(folder: Path, deck: dict, keys: dict) -> str:
        folder.mkdir()
        bid = bundle_id(deck, keys)
        for name, data in (("deck.json", deck | {"bundle": bid}), ("keys.json", keys | {"bundle": bid})):
            (folder / name).write_text(json.dumps(data), encoding="utf-8")
        return bid
    quiz = {"type": "single", "title": "T", "time": 20, "points": "standard", "scored": True, "leaderboard": True,
            "reveal": "slide", "prompt": None, "answers": [{"id": "A", "shape": 1}, {"id": "B", "shape": 2}]}
    prompt = {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2}
    deck = {"format": 2, "deck": "d", "name": "D", "types": ["quiz"], "image": {"width": 1920, "height": 1080},
            "slides": [{"id": 256, "image": "slides/0000000000000000.png"},
                       {"id": 257, "image": "slides/1111111111111111.png",
                        "live": [{"type": "quiz", "phase": "question", "item": "q1", "rects": {"prompt": prompt}}]}],
            "items": {"quiz": {"q1": quiz}}}
    keys = {"format": 2, "deck": "d", "items": {"quiz": {"q1": {"correct": ["A"]}}}}
    bid = write(tmp_path / "two", deck, keys)
    b = load_bundle(tmp_path / "two")
    assert b.id == bid and list(b.quizzes) == ["q1"] and b.quizzes["q1"].keys == {"correct": ["A"]}
    assert [(s.phase, s.quiz) for s in b.slides.values()] == [(None, None), ("question", "q1")]
    assert b.deck_json["quizzes"] == {"q1": quiz} and b.deck_json["slides"][1]["rects"] == {"prompt": prompt}
    write(tmp_path / "cell", deck | {"types": ["quiz", "cell"]}, keys)
    with pytest.raises(BundleError, match="needs cell, which this server does not know"):
        load_bundle(tmp_path / "cell")
    write(tmp_path / "three", deck | {"format": 3}, keys | {"format": 3})
    with pytest.raises(BundleError, match="external bundles require an explicit plugin lock"):
        load_bundle(tmp_path / "three")
    lost = {"id": 258, "image": "slides/2222222222222222.png", "live": [{"type": "video", "item": "gone", "rects": {}}]}
    write(tmp_path / "lost", deck | {"types": ["quiz", "video"], "slides": [*deck["slides"], lost]}, keys)
    with pytest.raises(BundleError, match="slide 3 names an unknown video gone"):
        load_bundle(tmp_path / "lost")


def test_the_video_when_the_slide_changes():
    """server/video.py's slide(): a playing video that the new slide does not show stops where it
    is, one it shows plays on, one it brings that plays by itself starts from its start - again
    when it comes back -, a whiteboard page or a poll (nothing after) stops them all."""
    from texstage.server import video
    items = {"a": {"media": "m"}, "b": {"media": "m", "autoplay": True, "start": 2.0}}
    playing = {"video": {"a": {"playing": True, "time": 1.0, "at": 1000}}}
    assert video.slide(playing, items, ("a",), ("a",), 5000) is playing
    assert video.slide(playing, items, ("a",), (), 5000)["video"]["a"] == {"playing": False, "time": 5.0, "at": 5000}
    after = video.slide(playing, items, ("a",), ("b",), 5000)["video"]
    assert after["a"]["playing"] is False and after["b"] == {"playing": True, "time": 2.0, "at": 5000}
    assert video.slide({}, items, ("b",), ("b",), 5000) == {}                      # (a step: not again)
    paused = {"video": {"b": {"playing": False, "time": 9.0, "at": 1000}}}
    assert video.slide(paused, items, (), ("b",), 5000)["video"]["b"]["time"] == 2.0
    assert video.slide(paused, items, ("b",), ("b",), 5000) is paused


def test_a_video_on_the_stage(tmp_path):
    """A deck's video (docs/content-types-design.md, section 7): the presenter window plays,
    pauses and seeks it - {playing, time, at} in the stage's state, for every window -; the next
    step of its frame lets it play on, a slide without it stops it where it is, a slide with a
    video that plays by itself starts that; the projector window only follows. The file goes out
    by a ticket only, with byte ranges (seeking); the poster as the slide pictures do."""
    import hashlib

    from texstage.build.bundle import bundle_id
    folder = tmp_path / "bundles" / "v.bundle"
    files = {"slides": [b"one", b"two"], "movie": bytes(range(256)) * 8, "poster": b"poster"}
    name = lambda folder, data, ext: f"{folder}/{hashlib.sha256(data).hexdigest()[:16]}.{ext}"
    s1, s2 = (name("slides", d, "png") for d in files["slides"])
    movie, poster = name("media", files["movie"], "mp4"), name("media", files["poster"], "png")
    for rel, data in ((s1, files["slides"][0]), (s2, files["slides"][1]), (movie, files["movie"]), (poster, files["poster"])):
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    box = {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.5}
    deck = {"format": 2, "deck": "v", "name": "V", "types": ["video"], "image": {"width": 1920, "height": 1080},
            "slides": [{"id": 256, "image": s1}] + [
                {"id": n, "image": s2, "live": [{"type": "video", "item": v, "rects": {"box": box}}]}
                for n, v in ((257, "clip"), (258, "clip"), (259, "intro"))],
            "items": {"video": {"clip": {"media": movie, "poster": poster, "start": 1.0},
                                "intro": {"media": movie, "poster": poster, "start": 3.0, "autoplay": True}}}}
    keys = {"format": 2, "deck": "v", "items": {}}
    bid = bundle_id(deck, keys)
    for rel, data in (("deck.json", deck), ("keys.json", keys)):
        (folder / rel).write_text(json.dumps(data | {"bundle": bid}), encoding="utf-8")
    clip = lambda m, v="clip": (m["stage"].get("video") or {}).get(v) or {}
    with TestClient(create_app(config(tmp_path))) as client, \
            client.websocket_connect("/ws") as st, client.websocket_connect("/ws") as dp:
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": "v", "bundle": bid, "id": 1})
        recv(st, "welcome")
        dp.send_json({"t": "hello", "role": "display", "key": KEY, "deck": "v", "bundle": bid, "id": 1})
        recv(dp, "welcome")
        st.send_json({"t": "slide", "slide": 257, "id": 2})
        st.send_json({"t": "video.play", "video": "clip", "time": 1.0, "id": 3})
        playing = clip(recv(dp, "state", until=lambda m: clip(m).get("playing")))
        assert playing["time"] == 1.0 and playing["at"] > 0
        st.send_json({"t": "video.seek", "video": "clip", "time": 4.25, "id": 4})      # playing on
        assert clip(recv(dp, "state", until=lambda m: clip(m).get("time") == 4.25))["playing"] is True
        st.send_json({"t": "video.pause", "video": "clip", "time": 2.5, "id": 5})
        recv(dp, "state", until=lambda m: clip(m).get("playing") is False and clip(m)["time"] == 2.5)
        st.send_json({"t": "video.play", "video": "clip", "time": 2.5, "id": 6})
        recv(dp, "state", until=lambda m: clip(m).get("playing"))
        st.send_json({"t": "slide", "slide": 258, "id": 70})                           # its frame's next step
        assert clip(recv(dp, "state", until=lambda m: m["session"]["slide"] == 258))["playing"] is True
        st.send_json({"t": "slide", "slide": 259, "id": 7})                            # a slide without it
        m = recv(dp, "state", until=lambda m: m["session"]["slide"] == 259)
        assert clip(m)["playing"] is False and clip(m)["time"] >= 2.5
        assert clip(m, "intro")["playing"] is True and clip(m, "intro")["time"] == 3.0  # it plays by itself
        st.send_json({"t": "slide", "slide": 256, "id": 71})
        assert clip(recv(dp, "state", until=lambda m: m["session"]["slide"] == 256), "intro")["playing"] is False
        st.send_json({"t": "video.play", "video": "other", "time": 0, "id": 8})
        assert recv(st, "error", until=lambda m: m.get("re") == 8)["error"] == "invalid"
        st.send_json({"t": "video.play", "video": "clip", "time": True, "id": 9})
        assert recv(st, "error", until=lambda m: m.get("re") == 9)["error"] == "invalid"
        dp.send_json({"t": "video.play", "video": "clip", "time": 0, "id": 10})       # the projector follows
        assert recv(dp, "error")["error"] == "read-only"
        assert client.get(f"/bundle/{bid}/{movie}").status_code == 404                # not by its name
        assert client.post(f"/api/deck/{bid}/media").status_code == 403
        urls = client.post(f"/api/deck/{bid}/media", headers={"X-Texquiz-Key": KEY}).json()
        assert list(urls) == [movie] and urls[movie].startswith("/media/")     # (both videos' file)
        part = client.get(urls[movie], headers={"Range": "bytes=100-299"})
        assert part.status_code == 206 and part.content == files["movie"][100:300]
        assert part.headers["content-type"] == "video/mp4"
        assert client.get(urls[movie].replace("/media/", "/media/x")).status_code == 404
        pic = client.get(f"/bundle/{bid}/{poster}")
        assert pic.content == files["poster"] and pic.headers["content-type"] == "image/png"
