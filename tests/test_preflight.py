# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage check (preflight.py): is a live deck ready to present on this PC?"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from test_publish import KEY, running
from test_server import config
from texstage import addin, preflight
from texstage.build.powerpoint import PptxDeck, origin
from texstage.cli import main
from texstage.preflight import check, in_this_network, read_deck
from texstage.server.app import create_app

REG = r"Software\texquiz-tests\WEF\Developer"
TUNNEL = "https://quiz.example.org"


@pytest.fixture
def served(tmp_path):
    """A real server in a thread; its phones join at its own address, as on a hosted server."""
    (tmp_path / "srv").mkdir()
    cfg = config(tmp_path / "srv")
    app = create_app(cfg)
    with running(app) as url:
        cfg.public_url = url
        yield SimpleNamespace(url=url, cfg=cfg)


@pytest.fixture
def live(served):
    return served.url


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 9), "white").save(buf, "PNG")
    return buf.getvalue()


def make_pptx(path: Path, server: str, key: str | None, carries: bool = True, live_slide: bool = True,
              first: bool = False) -> Path:
    deck = PptxDeck((160, 90), server)
    deck.add_slide(png(), "")
    deck.add_slide(png(), "")
    if live_slide:
        props = {"server": origin(server), "deck": "test", "bundle": "0123456789abcdef", "quiz": None,
                 "phase": "join", "slideId": 257}
        if key:
            props["key"] = key
        if first:                                     # since 2026-10-10: slide 1 prepares the live slides
            deck.add_addin(0, props | {"phase": "prepare", "slideId": 256}, "texquiz prepare")
        if carries:
            props["texquizBundle"] = "UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA=="
        deck.add_addin(1, props, "texquiz join")
    deck.save(path)
    return path


@pytest.fixture
def registered(live, tmp_path):
    """The live server's add-in, registered under a test key (not Office's)."""
    if sys.platform != "win32":
        pytest.skip("registration is Windows only")
    import winreg
    addin.install(live, tmp_path / "addins", key=REG)
    yield live
    for sub in (REG, r"Software\texquiz-tests\WEF", r"Software\texquiz-tests"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub, 0, winreg.KEY_ALL_ACCESS) as k:
                while True:
                    try:
                        winreg.DeleteValue(k, winreg.EnumValue(k, 0)[0])
                    except OSError:
                        break
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)


def run(pptx: Path) -> tuple[bool, str]:
    lines: list[str] = []
    ok = check(pptx, say=lines.append, registry_key=REG, office_js=None)
    return ok, "\n".join(lines)


def test_ready(registered, tmp_path):
    pptx = make_pptx(tmp_path / "deck.pptx", registered, KEY)
    d = read_deck(pptx)
    assert (d.live, d.servers, d.keys, d.carries) == (1, {registered}, {KEY}, True)
    ok, out = run(pptx)
    assert ok and out.endswith("ready"), out
    assert "registered on this PC" in out and "accepts the deck's presenter key" in out
    assert "the join slide brings it" in out and "phones join at" in out


def test_what_is_missing(registered, tmp_path):
    (tmp_path / "deck-static.pptx").write_bytes(b"")
    ok, out = run(make_pptx(tmp_path / "deck.pptx", registered, "wrong-key"))
    assert not ok and "does not accept the deck's presenter key" in out and "present deck-static.pptx" in out
    ok, out = run(make_pptx(tmp_path / "nokey.pptx", registered, None))
    assert not ok and "carries no presenter key" in out
    ok, out = run(make_pptx(tmp_path / "nobundle.pptx", registered, KEY, carries=False))   # the files of today
    assert not ok and "its build hands it over" in out and "texstage publish" in out
    ok, out = run(make_pptx(tmp_path / "down.pptx", "http://127.0.0.1:9", KEY))
    assert not ok and "not registered on this PC" in out and "does not answer" in out
    assert "texstage-serve.py" in out                                   # a local server: start it


def test_the_first_slide_prepares(registered, tmp_path):
    """A first slide prepares the live slides (since 2026-10-10): not one of the deck's live
    slides; a file without one is an older build, whose join slide does it."""
    pptx = make_pptx(tmp_path / "deck.pptx", registered, KEY, first=True)
    d = read_deck(pptx)
    assert (d.live, d.first, d.bundles) == (1, True, {"0123456789abcdef"})
    ok, out = run(pptx)
    assert ok and "1 live slides" in out and "built before 2026-10-10" not in out, out
    ok, out = run(make_pptx(tmp_path / "older.pptx", registered, KEY))
    assert ok and "the join slide prepares the quiz slides" in out, out


def test_a_join_slide_that_carries_too_much(registered, tmp_path, monkeypatch):
    """A file built before 2026-10-09 whose join slide carries more than PowerPoint keeps for an
    add-in (2 MB) cannot bring the deck - build it again (the build hands it over)."""
    from texstage import preflight
    monkeypatch.setattr(preflight, "CARRY_MAX", 10)
    pptx = make_pptx(tmp_path / "large.pptx", registered, KEY)
    assert read_deck(pptx).carried == len("UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA==")
    ok, out = run(pptx)
    assert not ok and "more than PowerPoint keeps" in out and "build it again" in out


def test_the_phones_address(registered, served, tmp_path, monkeypatch):
    """Through a tunnel, the check tries the phones' address over the internet: does it lead
    to this very server? (Here the "internet" leads wherever `target` says.)"""
    pptx = make_pptx(tmp_path / "deck.pptx", registered, KEY)
    served.cfg.public_url = TUNNEL
    target = {"url": served.url}
    real = preflight.get
    monkeypatch.setattr(preflight, "get", lambda url, key=None, timeout=5:
                        real(url.replace(TUNNEL, target["url"]), key, timeout))
    ok, out = run(pptx)
    assert ok and f"phones reach the server at {TUNNEL}/play (checked over the internet)" in out, out
    (tmp_path / "other").mkdir()
    with running(create_app(config(tmp_path / "other"))) as other:
        target["url"] = other
        ok, out = run(pptx)
    assert not ok and "does not reach this server: it leads to another texstage server" in out, out
    target["url"] = "http://127.0.0.1:9"                               # the tunnel is down
    ok, out = run(pptx)
    assert not ok and f"phones would join at {TUNNEL}/play, but it does not reach this server" in out
    served.cfg.public_url = "http://192.168.1.20:8470"                 # the laptop in the room's network
    ok, out = run(pptx)
    assert ok and "phones join at http://192.168.1.20:8470/play - open it on a phone in the room" in out


def test_in_this_network():
    assert all(in_this_network(u) for u in ("http://localhost:8470", "http://10.1.2.3:8470",
                                            "http://192.168.1.20:8470", "http://[::1]:8470", "http://[fe80::1]"))
    assert not any(in_this_network(u) for u in ("https://quiz.example.org", "http://137.226.1.2:8470"))


def test_a_deck_without_live_slides(tmp_path):
    ok, out = run(make_pptx(tmp_path / "plain.pptx", "http://localhost:8470", None, live_slide=False))
    assert ok and "no live slides" in out


def test_check_command(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing.pptx")]) == 2
    make_pptx(tmp_path / "plain.pptx", "http://localhost:8470", None, live_slide=False)
    assert main(["check", str(tmp_path / "plain.pptx"), "--offline"]) == 0
