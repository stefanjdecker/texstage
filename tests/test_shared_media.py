# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A video ticket keeps working when a shared upload's physical copy changes."""
from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile

import pytest
from starlette.testclient import TestClient

from test_server import config
from texstage.build.bundle import bundle_id
from texstage.server.app import MEDIA_MS, create_app
from texstage.server.lecturers import Lecturers


def movie_bundle():
    movie = bytes(range(256)) * 8
    media = f"media/{hashlib.sha256(movie).hexdigest()[:16]}.mp4"
    slide = "slides/0000000000000000.png"
    deck = {"format": 2, "deck": "video", "name": "Video", "types": ["video"],
            "image": {"width": 1920, "height": 1080},
            "slides": [{"id": 256, "image": slide,
                        "live": [{"type": "video", "item": "clip", "rects": {
                            "box": {"x": 0, "y": 0, "w": 1, "h": 1}}}]}],
            "items": {"video": {"clip": {"media": media}}}}
    keys = {"format": 2, "deck": "video", "items": {}}
    bid = bundle_id(deck, keys)
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w") as archive:
        for name, body in (("deck.json", deck), ("keys.json", keys)):
            archive.writestr(name, json.dumps(body | {"bundle": bid}))
        archive.writestr(slide, b"slide")
        archive.writestr(media, movie)
    return bid, packed.getvalue(), media, movie


@pytest.mark.parametrize("upload_order", [("ada", "bob"), ("bob", "ada")])
def test_existing_video_ticket_survives_deleting_another_lecturers_copy(tmp_path, upload_order):
    lecturers = Lecturers(tmp_path / "data" / "lecturers.json")
    headers = {who: {"X-Texquiz-Key": lecturers.add(who)} for who in ("ada", "bob")}
    bid, packed, media, movie = movie_bundle()
    with TestClient(create_app(config(tmp_path))) as client:
        for who in upload_order:
            assert client.put(f"/api/bundles/{bid}", content=packed, headers=headers[who]).status_code == 201
        server = client.app.state.server
        bob = server.engine.open_session("video", bid, int(time.time() * 1000), owner="bob")
        url = client.post(f"/api/deck/{bid}/media", headers=headers["bob"]).json()[media]
        first = client.get(url, headers={"Range": "bytes=0-99"})
        assert first.status_code == 206 and first.content == movie[:100]
        assert client.delete("/api/decks/video", headers=headers["ada"]).status_code == 200
        assert server.engine.sessions[bob.id] is bob
        next_part = client.get(url, headers={"Range": "bytes=100-299"})
        assert next_part.status_code == 206 and next_part.content == movie[100:300]
        assert next_part.headers["content-type"] == "video/mp4"
        assert client.get(url.rsplit("/", 1)[0] + "/wrong.mp4").status_code == 404
        ticket = url.split("/")[2]
        bundle, name, until = server.media[ticket]
        server.media[ticket] = (bundle, name, until - MEDIA_MS - 1000)
        assert client.get(url).status_code == 404


def test_video_ticket_does_not_outlive_the_last_copy(tmp_path):
    lecturers = Lecturers(tmp_path / "data" / "lecturers.json")
    headers = {"X-Texquiz-Key": lecturers.add("ada")}
    bid, packed, media, _ = movie_bundle()
    with TestClient(create_app(config(tmp_path))) as client:
        assert client.put(f"/api/bundles/{bid}", content=packed, headers=headers).status_code == 201
        url = client.post(f"/api/deck/{bid}/media", headers=headers).json()[media]
        assert client.delete("/api/decks/video", headers=headers).status_code == 200
        assert client.get(url).status_code == 404
