# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage's presenter devices (server/devices.py): pairing an iPad from the presenter window,
and what a paired device may do."""
from __future__ import annotations

import json

from test_server import KEY, recv, world  # noqa: F401  (the fixture)
from texstage.server.devices import PAIR_MS, Devices


def test_pairing_a_presenter_device(world):  # noqa: F811
    """The presenter window (the key) offers a one-time code; the device that opens it waits
    with a code to compare; the lecturer allows it; the device then presents with a token of
    its own - it neither publishes nor pairs - until it is removed, which ends its connection."""
    client, fb = world
    key = {"X-Texquiz-Key": KEY}
    assert client.post("/api/pair").status_code == 403                    # the presenter key only
    offer = client.post("/api/pair", headers=key).json()
    assert offer["url"] == f"http://quiz.test/stage#pair={offer['token']}" and offer["qr"].startswith("<svg")
    assert client.get(f"/api/pair/{offer['token']}", headers=key).json()["state"] == "waiting"
    claim = client.post("/api/pair/claim", json={"token": offer["token"], "name": "iPad · Safari\u0007"}).json()
    assert len(claim["code"]) == 4
    second = client.post("/api/pair/claim", json={"token": offer["token"], "name": "a student"})
    assert second.status_code == 404                                       # one device per code
    assert client.post("/api/pair/wait", json={"claim": claim["claim"]}).json() == {"state": "claimed"}
    status = client.get(f"/api/pair/{offer['token']}", headers=key).json()
    assert status == {"state": "claimed", "name": "iPad · Safari", "code": claim["code"]}
    assert client.post(f"/api/pair/{offer['token']}", json={"allow": True}).status_code == 403
    assert client.post(f"/api/pair/{offer['token']}", json={"allow": True}, headers=key).json() == {"state": "approved"}
    done = client.post("/api/pair/wait", json={"claim": claim["claim"]}).json()
    assert done["state"] == "approved" and done["device"]
    assert client.post("/api/pair/wait", json={"claim": claim["claim"]}).status_code == 404     # told once
    device = {"X-Texquiz-Device": done["device"]}
    assert [d["bundle"] for d in client.get("/api/decks", headers=device).json()] == [fb.id]
    assert client.get(f"/api/deck/{fb.id}", headers=device).status_code == 200
    assert client.post("/api/pair", headers=device).status_code == 403    # a device pairs no devices
    assert client.get("/api/devices", headers=device).status_code == 403
    assert client.put(f"/api/bundles/{fb.id}", content=b"x", headers=device).status_code == 403   # nor publishes
    (listed,) = client.get("/api/devices", headers=key).json()
    assert listed["name"] == "iPad · Safari" and listed["seen"] and listed["paired"]
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"t": "hello", "role": "stage", "device": done["device"], "deck": fb.deck, "bundle": fb.id, "id": 1})
        assert recv(ws, "welcome")["role"] == "stage"
        assert client.delete(f"/api/devices/{listed['id']}", headers=key).json() == {"removed": True}
        assert recv(ws, "bye")["reason"] == "removed"                      # out at once
    assert client.get("/api/decks", headers=device).status_code == 403
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"t": "hello", "role": "stage", "device": done["device"], "deck": fb.deck, "bundle": fb.id, "id": 1})
        assert recv(ws, "error")["error"] == "bad-key"
    other = client.post("/api/pair", headers=key).json()
    waiting = client.post("/api/pair/claim", json={"token": other["token"], "name": "a student"}).json()
    client.post(f"/api/pair/{other['token']}", json={"allow": False}, headers=key)
    assert client.post("/api/pair/wait", json={"claim": waiting["claim"]}).json() == {"state": "denied"}
    assert client.post("/api/pair/claim", json={"token": "made-up", "name": "x"}).status_code == 404


def test_pairing_codes_expire_and_only_hashes_are_kept(tmp_path):
    devices = Devices(tmp_path / "devices.json")
    late = devices.offer("ada", 0)
    assert devices.claim(late.token, "late", PAIR_MS + 1) is None         # two minutes are over
    p = devices.offer("ada", 0)
    waiting = devices.claim(p.token, "iPad", 1000)
    assert devices.decide("bob", p.token, True, 2000) is None              # another lecturer's code
    assert devices.decide("ada", p.token, True, 2000).state == "approved"
    token = devices.wait(waiting.claim, 3000).device
    stored = (tmp_path / "devices.json").read_text(encoding="utf-8")
    (entry,) = json.loads(stored).values()
    assert entry["owner"] == "ada" and entry["name"] == "iPad" and token not in stored    # only its hash
    assert devices.who(token, 4000)[0] == "ada" and devices.who("guess", 4000) is None
