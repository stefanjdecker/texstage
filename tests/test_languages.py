# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage in the deck's language (web/i18n/i18n.js), on the server's side: the deck's language
in the host's and the phones' views, the join slide's address and QR code naming it (a phone's
join form speaks it before it has joined), the polls a lecturer types in it, the codes of the
refusals the windows say in it, and the babel names the LaTeX packages share with the build."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
import segno
from starlette.testclient import TestClient

from fake_bundle import make_bundle
from test_server import KEY, config, hello, join, recv
from texstage.build.bundle import LANGUAGES
from texstage.server.app import create_app
from texstage.server.polls import WORDS, PollError, make_poll

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("language, spoken", [(None, "en"), ("en", "en"), ("de", "de"), ("fr", "en")])
def test_the_views_name_the_decks_language(tmp_path, language, spoken):
    """The host's and the phones' views name the language the deck's windows and phones speak:
    deck.json's if texstage speaks it, else (another language, a deck built before 2026-10-24)
    English; the join slide's address and QR code name it too."""
    fb = make_bundle(tmp_path / "bundles", language=language)
    with TestClient(create_app(config(tmp_path))) as client, client.websocket_connect("/ws") as host:
        pin = hello(host, fb)["pin"]
        session = recv(host, "state")["session"]
        assert session["language"] == spoken
        assert session["join"] == f"http://quiz.test/play?pin={pin}&lang={spoken}"
        assert session["qr"] == f"/join/{pin}.svg?lang={spoken}"
        with client.websocket_connect("/ws") as phone:
            join(phone, pin, "Ada")
            assert recv(phone, "state")["session"]["language"] == spoken


def qr(url: str) -> str:
    buf = io.BytesIO()
    segno.make_qr(url, error="m").save(buf, kind="svg", scale=8, border=2)
    return buf.getvalue().decode()


def test_the_join_code_names_the_language_it_is_given(tmp_path):
    """/join/<pin>.svg?lang=de encodes the phone's address with the language - one texstage speaks,
    never another text -, and looks up nothing: no game has to have the PIN."""
    make_bundle(tmp_path / "bundles")
    with TestClient(create_app(config(tmp_path))) as client:
        assert client.get("/join/123456.svg?lang=de").text == qr("http://quiz.test/play?pin=123456&lang=de")
        for other in ("", "fr", "de-AT", "DE", "de&x=1", "<b>"):
            assert client.get("/join/123456.svg", params={"lang": other}).text == qr("http://quiz.test/play?pin=123456"), other


def test_a_poll_is_in_the_decks_language(tmp_path):
    """A poll the lecturer types: its title and a yes/no poll's answers in the deck's language -
    English for any other -, answers the lecturer typed as they are."""
    yes_no = make_poll({"kind": "yesno"}, "de")[0]
    assert yes_no["title"] == "Umfrage" and [a["text"] for a in yes_no["answers"]] == ["Ja", "Nein"]
    assert make_poll({"kind": "sketch", "prompt": "Ein ER-Diagramm"}, "de")[0]["title"] == "Skizze"
    english = make_poll({"kind": "yesno"})[0]
    assert english["title"] == "Poll" and [a["text"] for a in english["answers"]] == ["Yes", "No"]
    assert make_poll({"kind": "yesno"}, "fr")[0] == english
    assert [a["text"] for a in make_poll({"kind": "yesno", "answers": ["Klar", "Nie"]}, "de")[0]["answers"]] == ["Klar", "Nie"]
    assert set(WORDS) == set(LANGUAGES)
    with pytest.raises(PollError) as err:
        make_poll({"kind": "words"}, "de")
    assert err.value.code == "poll-question"           # a lecturer can send it: the window says it
    fb = make_bundle(tmp_path / "bundles", language="de")
    with TestClient(create_app(config(tmp_path))) as client, client.websocket_connect("/ws") as st, \
            client.websocket_connect("/ws") as phone:
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": fb.deck, "bundle": fb.id, "id": 1})
        pin = recv(st, "welcome")["pin"]
        join(phone, pin, "Ada")
        st.send_json({"t": "poll.create", "kind": "yesno", "time": 10, "id": 2})
        quiz = recv(st, "ok", until=lambda m: m["re"] == 2)["quiz"]
        r = recv(phone, "state", until=lambda m: m["round"] and m["round"]["phase"] == "open", limit=200)["round"]
        assert r["question"]["title"] == "Umfrage" and [a["text"] for a in r["question"]["answers"]] == ["Ja", "Nein"]
        st.send_json({"t": "poll.create", "kind": "text", "time": 10, "id": 3})
        assert recv(st, "error", until=lambda m: m.get("re") == 3)["error"] == "poll-question"
        assert quiz


def test_the_http_refusals_have_codes(tmp_path):
    """The HTTP API's refusals name their code beside their English words: the windows say them
    in the deck's language (web/i18n: errors)."""
    fb = make_bundle(tmp_path / "bundles")
    key = {"X-Texquiz-Key": KEY}
    with TestClient(create_app(config(tmp_path))) as client:
        r = client.get(f"/api/deck/{fb.id}")
        assert r.status_code == 403 and r.json() == {"error": "presenter key required", "code": "key-required"}
        r = client.get("/api/deck/0123456789abcdef", headers=key)
        assert r.status_code == 404 and r.json()["code"] == "unknown-bundle"
        r = client.get(f"/api/deck/{fb.id}/pdf", headers=key)           # a build without the stage PDF
        assert r.status_code == 404 and r.json()["code"] == "no-stage-pdf"
        r = client.post("/api/folders", headers=key, json={"name": "  "})
        assert r.status_code == 400 and r.json()["code"] == "name-empty"
        r = client.patch("/api/folders/nope", headers=key, json={"name": "x"})
        assert r.status_code == 404 and r.json()["code"] == "no-folder"


def test_the_latex_packages_know_the_builds_language_names():
    """texstage.sty takes the same babel names for German as the build's language_tag
    (build/bundle.py, LANGUAGES): the slides' texts and the windows speak one language."""
    sty = (ROOT / "latex" / "texstage.sty").read_text(encoding="utf-8")
    names = re.search(r"\\clist_const:Nn \\c__texstage_de_names_clist\s*\{([^}]*)\}", sty).group(1)
    assert {n.strip() for n in names.split(",")} == {"de", *LANGUAGES["de"]}
    assert set(LANGUAGES) == {"en", "de"}, "another language: its babel names in texstage.sty and its texts"
