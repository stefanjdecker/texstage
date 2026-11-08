# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Pre-join language and ordinary phone state, without optional plugins."""
import pytest
from starlette.testclient import TestClient

from fake_bundle import make_bundle
from texstage.server.app import ServerConfig, create_app
from test_server import hello, recv, join, KEY


@pytest.mark.parametrize("language,expected", [("de", "de"), ("en", "en"), (None, "en")])
def test_phone_language_before_join_and_after_resume(tmp_path, language, expected):
    fb = make_bundle(tmp_path / "bundles", language=language)
    config = ServerConfig(bundles=[fb.path], data_dir=tmp_path / "data",
                          public_url="http://quiz.test", presenter_key=KEY)
    with TestClient(create_app(config)) as client, client.websocket_connect("/ws") as host:
        pin = hello(host, fb)["pin"]
        response = client.get("/api/join-language", params={"pin": pin})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"language": expected}  # no title, keys, token or participants
        with client.websocket_connect("/ws") as phone:
            token = join(phone, pin, "Learner")["token"]
            state = recv(phone, "state")
            assert state["language"] == expected
            assert state["round"] is None
            assert "keys" not in state and "token" not in state
        with client.websocket_connect("/ws") as resumed:
            resumed.send_json({"t": "resume", "token": token, "id": "resume"})
            recv(resumed, "welcome")
            assert recv(resumed, "state")["language"] == expected


def test_language_probe_shares_wrong_pin_throttling_and_rejects_expired_sessions(tmp_path):
    fb = make_bundle(tmp_path / "bundles", language="de")
    config = ServerConfig(bundles=[fb.path], data_dir=tmp_path / "data",
                          public_url="http://quiz.test", presenter_key=KEY)
    app = create_app(config)
    with TestClient(app) as client, client.websocket_connect("/ws") as host:
        welcome = hello(host, fb)
        pin = welcome["pin"]
        for value in ("", "../keys.json", "<script>", "123", "1234567"):
            assert client.get("/api/join-language", params={"pin": value}).json() == {"language": None}
        session = app.state.server.engine.sessions[welcome["session"]]
        session.ended = 1
        assert client.get("/api/join-language", params={"pin": pin}).json() == {"language": None}
        session.ended = None
        wrong = "000000" if pin != "000000" else "111111"
        for _ in range(app.state.server.attempts.limit):
            client.get("/api/join-language", params={"pin": wrong})
        blocked = client.get("/api/join-language", params={"pin": pin})
        assert blocked.status_code == 429
        assert blocked.json() == {"language": None}
        with client.websocket_connect("/ws") as phone:
            phone.send_json({"t": "join", "pin": pin, "nickname": "Learner", "id": "join"})
            assert recv(phone, "error")["error"] == "too-many-attempts"
