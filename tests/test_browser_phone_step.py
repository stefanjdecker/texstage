# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A phone in a real browser through an activity and a quiz after it (the review of 2026-11-19, A1): the
activity's step while it runs and once it is closed - and the quiz's reading, round and result as soon as
the quiz shows them, not the closed activity over them; a phone that joins a new game keeps no step of the
one before (the second review). play.js chooses the screen; the engine's tests hold the two moments it
compares (test_activities_phones.py), this one that the page heeds them."""
from __future__ import annotations

import hashlib
import io
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from PIL import Image

from test_browser_smoke import PHONE, browser, host, join, new_page  # noqa: F401 - (the fixtures)
from test_server import KEY

from texstage.build.bundle import bundle_id
from texstage.server import types as stage_types
from texstage.server.app import ServerConfig, create_app
from texstage.server.game import Settings

BOX = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
LIVE = {"x": 0.06, "y": 0.13, "w": 0.88, "h": 0.8}


def png(colour: str, size=(16, 9)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, "PNG")
    return buf.getvalue()


def write_bundle(folder: Path) -> tuple[str, dict]:
    """A format-2 bundle as a build writes one: the join slide, a text activity's slide, an ordinary one, then
    a quiz's reading, question and reveal slides. The slides' ids by what they are."""
    files = {f"slides/{hashlib.sha256(png(c)).hexdigest()[:16]}.png": png(c) for c in ("white", "grey")}
    plain, shown = list(files)
    pictures = {}
    for name in ("prompt", "A", "B"):
        data = png({"prompt": "black", "A": "red", "B": "blue"}[name], (40, 9))
        rel = f"phone/{hashlib.sha256(data).hexdigest()[:16]}.png"
        files[rel] = data
        pictures[name] = {"image": rel, "width": 200.0, "height": 45.0}
    ids = {"join": 256, "activity": 257, "after": 258, "read": 259, "question": 260, "reveal": 261}

    def live(what: str) -> list:
        if what == "activity":
            return [{"type": "activity", "item": "word", "phase": "open", "rects": {"box": BOX}}]
        if what == "after":
            return []
        return [{"type": "quiz", **({"item": "q"} if what != "join" else {}), "phase": what, "rects": {"live": LIVE}}]
    deck = {"format": 2, "deck": "step", "name": "Step", "types": ["activity", "quiz"], "language": "en",
            "image": {"width": 1920, "height": 1080},
            "slides": [{"id": sid, "image": shown if what != "after" else plain}
                       | ({"live": live(what)} if live(what) else {}) for what, sid in ids.items()],
            "items": {"activity": {"word": {"kind": "text", "input": "text", "limit": 3}},
                      "quiz": {"q": {"type": "single", "title": "Question", "time": 30, "points": "standard",
                                     "scored": True, "leaderboard": False, "reveal": "slide",
                                     "prompt": pictures["prompt"],
                                     "answers": [{"id": a, "shape": i + 1, **pictures[a]} for i, a in enumerate("AB")]}}}}
    keys = {"format": 2, "deck": "step", "items": {"activity": {"word": {"reference": ["Berlin"]}},
                                                   "quiz": {"q": {"prompt": "Which?", "correct": ["A"]}}}}
    bid = bundle_id(deck, keys)
    for rel, data in files.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    for rel, data in (("deck.json", deck), ("keys.json", keys)):
        (folder / rel).write_text(json.dumps(data | {"bundle": bid}), encoding="utf-8")
    return bid, ids


class Live:
    """A server of the core's type - one worker, no spare - in a thread, on a free port."""

    def __init__(self, tmp_path: Path):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        stage_types.use("core")
        self.app = create_app(ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data",
                                           public_url="http://quiz.test", presenter_key=KEY,
                                           settings=Settings(get_ready_ms=0), activities="core", workers=1,
                                           pool={"spare": False}))
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning",
                                                    timeout_graceful_shutdown=1))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        end = time.monotonic() + 30
        while not self.server.started:
            assert time.monotonic() < end and self.thread.is_alive(), "the server did not start"
            time.sleep(0.02)
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(15)


def screen(phone, text: str, timeout: float = 15000):
    phone.get_by_text(text).first.wait_for(timeout=timeout)


def test_a_phone_shows_the_quiz_after_a_closed_activity_and_a_new_game_no_step_of_the_old(new_page, tmp_path):
    bid, slides = write_bundle(tmp_path / "bundles" / "step.bundle")
    fb = type("Deck", (), {"deck": "step", "id": bid})
    with Live(tmp_path) as live:
        h, pin = host(live, fb)
        phone = join(new_page, live, pin, "Ada")
        n = iter(range(10, 100))

        def show(what: str):
            assert h.ask({"t": "slide", "slide": slides[what], "id": next(n)})["t"] == "ok"
        show("join")
        show("activity")                                                # it opens with its slide
        phone.locator("input, textarea").first.wait_for()
        show("after")                                                   # left: closed - still its screen
        screen(phone, "Closed.")
        show("read")                                                    # the quiz's reading: the quiz's screen
        screen(phone, "Read the question")
        assert "Closed." not in phone.inner_text("#app")
        show("question")
        phone.locator("button.answer").first.click()
        if phone.locator("#send").count():
            phone.locator("#send").click()
        screen(phone, "Answer sent")                                    # (before the fix: the closed activity)
        show("reveal")
        screen(phone, "Correct!")
        new = h.ask({"t": "restart", "id": next(n)})["pin"]             # New game
        screen(phone, "a new one has begun")
        phone.click("text=Join the new game")
        phone.click("#join button")
        screen(phone, "You're in!")                                     # (before: the old game's closed step)
        assert "Closed." not in phone.inner_text("#app") and new != pin
        h.close()
