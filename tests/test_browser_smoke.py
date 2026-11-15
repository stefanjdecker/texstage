# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests in a real browser: a phone, the presenter window and the projector's keys, driven by
Playwright against a real server on a free port. They see what the Node tests cannot: a button drawn
anew under a pressed mouse, a key from the projector window behind a dialog, a phone's form as typed,
the presenter while its server is away. Each lecture-room bug of the 2026-11 review that lives in the
browser (A2, A3, A5, A6, A7) failed one of them before it was fixed.

Playwright drives the installed Chrome - no browser download; TEXSTAGE_BROWSER names another channel
(msedge), or "chromium" for Playwright's own. Without Playwright or the browser the tests are skipped,
unless TEXSTAGE_BROWSER_TESTS=required (CI): then they fail."""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from contextlib import ExitStack, contextmanager

import pytest
import uvicorn

from fake_bundle import QUIZZES, make_bundle
from test_server import KEY, config
from texstage.server.app import create_app

REQUIRED = os.environ.get("TEXSTAGE_BROWSER_TESTS") == "required"
CHANNEL = os.environ.get("TEXSTAGE_BROWSER", "chrome")
NUMBER = ("numeric", {"numeric": {"min": None, "max": None, "step": 1, "unit": "m"}}, {"answer": 6, "tolerance": 0})
DECK = {"pick": QUIZZES["pick"], "size": NUMBER}            # a choice, and a number typed in (no min, no max)
PHONE = {"viewport": {"width": 375, "height": 812}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}
WINDOW = {"viewport": {"width": 1280, "height": 800}}


def unavailable(reason: str):
    if REQUIRED:
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="module")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        unavailable("the browser smoke tests need Playwright (requirements/dev.txt)")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(**({} if CHANNEL == "chromium" else {"channel": CHANNEL}))
        except Exception as err:            # (Playwright's error names what it looked for)
            unavailable(f"no browser for the smoke tests ({CHANNEL}): {str(err).splitlines()[0]}")
        yield b
        b.close()


@pytest.fixture
def new_page(browser):
    """A page in a browser context of its own (a phone, a presenter's laptop), closed after the test."""
    contexts = []

    def make(**options):
        contexts.append(browser.new_context(**options))
        return contexts[-1].new_page()
    yield make
    for c in contexts:
        c.close()


class Live:
    """A real server - uvicorn in a thread - on a free port; stop() and start() again keep the port and
    the data folder (an outage)."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def start(self):
        self.app = create_app(config(self.tmp))
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning",
                                                    timeout_graceful_shutdown=1))   # (pages stay connected)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        end = time.monotonic() + 10
        while not self.server.started:
            assert time.monotonic() < end and self.thread.is_alive(), "the server did not start"
            time.sleep(0.02)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(10)


@contextmanager
def running(tmp_path):
    live = Live(tmp_path)
    live.start()
    try:
        yield live
    finally:
        live.stop()


class Socket:
    """A connection of the protocol (websockets' sync client), read by a thread of its own: the
    replies by id, the latest state."""

    def __init__(self, live: Live):
        from websockets.sync.client import connect
        self.stack = ExitStack()                     # (connect() as a context manager: websockets 17)
        self.ws = self.stack.enter_context(connect(live.url.replace("http://", "ws://") + "/ws"))
        self.replies: dict = {}
        self.state: dict | None = None
        self.seen = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for raw in self.ws:
                m = json.loads(raw)
                with self.seen:
                    if m.get("t") == "state":
                        self.state = m
                    if m.get("re") is not None:
                        self.replies[m["re"]] = m
                    self.seen.notify_all()
        except Exception:                   # (closed)
            pass

    def ask(self, msg: dict, timeout: float = 10) -> dict:
        self.ws.send(json.dumps(msg))
        with self.seen:
            assert self.seen.wait_for(lambda: msg["id"] in self.replies, timeout), f"no reply to {msg['t']}"
            return self.replies[msg["id"]]

    def until(self, test, timeout: float = 10) -> dict:
        with self.seen:
            assert self.seen.wait_for(lambda: self.state is not None and test(self.state), timeout), "no such state"
            return self.state

    def close(self):
        self.stack.close()


def host(live: Live, fb) -> tuple[Socket, str]:
    """The lecturer's connection (the host console's), and the game's PIN."""
    h = Socket(live)
    welcome = h.ask({"t": "hello", "role": "host", "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": "hello"})
    assert welcome["t"] == "welcome", welcome
    return h, welcome["pin"]


def present(new_page, live: Live, fb):
    """The presenter window (texstage present: /stage?bundle=)."""
    page = new_page(**WINDOW)
    page.goto(f"{live.url}/stage?bundle={fb.id}")
    page.wait_for_function("/PIN \\d/.test(document.querySelector('#pin')?.textContent || '')")
    return page


def join(new_page, live: Live, pin: str, nickname: str):
    """A phone that joins with the QR code's address."""
    phone = new_page(**PHONE)
    phone.goto(f"{live.url}/play?pin={pin}&lang=en")
    phone.fill("#nick", nickname)
    phone.click("#join button")
    phone.get_by_text("You're in!").wait_for()
    return phone


def test_a_phone_joins_types_a_number_and_sees_the_reveal(new_page, tmp_path):
    """A numeric question without min and max was a type=number field: an empty Submit sent 0, an iPhone's
    keypad has no minus, a typed 3,5 could be lost (A5). Text with a ± key now, Submit once it is a number."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        h, pin = host(live, fb)
        phone = join(new_page, live, pin, "Ada")
        h.ask({"t": "slide", "slide": fb.slide("question", "size"), "id": 2})
        field = phone.locator("#num")
        field.wait_for()
        assert (field.get_attribute("type"), field.get_attribute("inputmode")) == ("text", "decimal")
        assert phone.locator("#send").is_disabled()                   # nothing typed: nothing to send
        field.click()
        phone.keyboard.type("6,5")                                     # as a German keyboard types it
        phone.click("#sign")                                           # ±: an iPhone's keypad has no minus
        assert field.input_value() == "-6,5"
        phone.click("#send")
        phone.get_by_text("Answer sent").wait_for()
        assert "-6.5" in phone.inner_text("#app")
        h.ask({"t": "slide", "slide": fb.slide("reveal", "size"), "id": 3})
        phone.get_by_text("Not quite").wait_for()                      # 6 was right
        h.close()


def test_after_new_game_a_phone_joins_the_new_one_in_one_tap(new_page, tmp_path):
    """New game: the phones said "This game is over", and Join again filled in the old PIN - each try a wrong
    PIN, 300 of them lock out an address, and through the tunnel a hall has one (A3)."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        h, old = host(live, fb)
        phone = join(new_page, live, old, "Ada")
        new = h.ask({"t": "restart", "id": 2})["pin"]
        phone.get_by_text("a new one has begun").wait_for()
        phone.click("text=Join the new game")
        assert (phone.input_value("#pin"), phone.input_value("#nick")) == (new, "Ada")
        phone.click("#join button")
        phone.get_by_text("You're in!").wait_for()
        late = new_page(**PHONE)                                       # the old QR code, scanned late
        late.goto(f"{live.url}/play?pin={old}&lang=en")
        late.fill("#nick", "Bob")
        late.click("#join button")
        late.get_by_text("this is the new game's PIN").wait_for()
        assert late.input_value("#pin") == new
        assert not live.app.state.server.attempts.wrong                # no wrong PIN counted
        h.close()


def test_pause_takes_a_slow_click_while_answers_come_in(new_page, tmp_path):
    """The slide's ⏸, +10 s and ⏭ were drawn anew with each push - five a second while answers come in - and
    a button replaced between mouse-down and mouse-up gets no click: the lecturer could not pause (A2)."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        page = present(new_page, live, fb)
        h, pin = host(live, fb)
        crowd = []
        for i in range(40):
            s = Socket(live)
            s.ask({"t": "join", "pin": pin, "nickname": f"p{i}", "id": "join"})
            crowd.append(s)
        h.ask({"t": "slide", "slide": fb.slide("question", "pick"), "id": 2})
        rid = crowd[0].until(lambda m: (m.get("round") or {}).get("phase") == "open")["round"]["id"]

        done = threading.Event()

        def answer():                                                  # an answer every 60 ms, for 2.4 s
            for i, s in enumerate(crowd):
                if done.is_set():
                    return
                s.ws.send(json.dumps({"t": "answer", "round": rid, "answer": {"choice": "B"}, "id": f"a{i}"}))
                time.sleep(0.06)
        answering = threading.Thread(target=answer, daemon=True)
        answering.start()
        pause = page.locator('.tq-controls button[data-cmd="pause"]')
        pause.wait_for()
        page.wait_for_timeout(300)                                     # answers are coming in
        box = pause.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.wait_for_timeout(700)                                     # a slow click: several pushes long
        page.mouse.up()
        page.locator('.tq-controls button[data-cmd="continue"]').wait_for(timeout=3000)     # paused
        assert h.until(lambda m: (m.get("rounds", {}).get("pick") or {}).get("paused"))
        done.set()
        answering.join(5)
        for s in [h, *crowd]:
            s.close()


def test_the_projector_windows_keys_wait_behind_a_dialog(new_page, tmp_path):
    """The projector window's keys came in by its channel straight to the game, past the presenter's guard:
    its → moved the game while "Reset the timer?" was open (A6)."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        page = present(new_page, live, fb)
        where = lambda: re.search(r"frame (\d+)", page.inner_text("#where")).group(1)   # noqa: E731
        assert where() == "1"
        projector = page.context.new_page()                            # the projector window's channel
        projector.goto(f"{live.url}/api/status")
        key = f"""() => {{ const c = new BroadcastChannel('texstage:{fb.id}');
                           c.postMessage({{type: 'key', key: 'ArrowRight'}}); c.close(); }}"""
        page.click("#reset")
        page.get_by_text("Reset the timer to 0:00?").wait_for()
        projector.evaluate(key)
        page.wait_for_timeout(600)
        assert where() == "1"                                          # behind the dialog: no move
        page.keyboard.press("Escape")
        page.locator(".dialog").wait_for(state="detached")
        projector.evaluate(key)
        page.wait_for_function("/frame 2\\b/.test(document.querySelector('#where').textContent)")


def test_decks_in_an_outage_say_so_and_come_back_with_the_server(new_page, tmp_path):
    """Decks pressed while the server could not be reached left a dead presenter: a dialog per queued
    command, the client gone and its clock throwing every frame, nothing back without a reload (A7)."""
    fb = make_bundle(tmp_path / "bundles", quizzes=DECK, stage="pdf")
    with running(tmp_path) as live:
        page = present(new_page, live, fb)
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        live.stop()
        page.locator("#offline").wait_for()
        page.keyboard.press("ArrowRight")                              # commands queued in the outage
        page.keyboard.press("ArrowRight")
        page.click("#morebtn")
        page.click("#decks")
        page.get_by_text("The server cannot be reached").wait_for(timeout=10000)
        assert page.locator(".dialog").count() <= 1                    # one for the queued commands
        live.start()                                                   # the same port and data
        page.get_by_role("heading", name="Decks").wait_for(timeout=15000)      # back by itself
        assert errors == []
