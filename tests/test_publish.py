# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Hosting (docs/design.md, section 8): texstage publish and the server's upload, the
presenter key behind a proxy, wrong PINs."""
from __future__ import annotations

import contextlib
import io
import os
import socket
import threading
import time
import zipfile
from pathlib import Path

import pytest
import uvicorn
from starlette.testclient import TestClient

from fake_bundle import make_bundle
from test_server import KEY, config, hello, recv
from texstage.cli import main
from texstage.publish import PublishError, find_bundles, find_key, pack, publish, remember_key
from texstage.server import app as app_module
from texstage.server.app import create_app

HOST = {"X-Texquiz-Key": KEY}


@pytest.fixture
def hosted(tmp_path):
    """A server without bundles of its own, and a deck built elsewhere."""
    (tmp_path / "bundles").mkdir()
    fb = make_bundle(tmp_path / "laptop")
    with TestClient(create_app(config(tmp_path))) as client:
        yield client, fb, tmp_path


def zipped(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_upload(hosted):
    client, fb, tmp = hosted
    (b,), _ = find_bundles([fb.path])
    data = pack(b)
    assert client.put(f"/api/bundles/{fb.id}", content=data).status_code == 403
    r = client.put(f"/api/bundles/{fb.id}", content=data, headers=HOST)
    assert r.status_code == 201 and r.json() == {"bundle": fb.id, "deck": "test", "name": "Test deck",
                                                 "quizzes": 8, "slides": len(fb.slides), "new": True}
    assert client.get("/api/decks", headers=HOST).json()[0]["complete"] is True
    # every build apart: the lecturer's folder, the deck, the build
    assert (tmp / "data" / "bundles" / "local" / "test" / fb.id / "deck.json").is_file()
    assert [d["bundle"] for d in client.get("/api/decks", headers=HOST).json()] == [fb.id]
    picture = next((fb.path / "slides").iterdir()).name
    assert client.get(f"/bundle/{fb.id}/slides/{picture}").status_code == 200
    assert client.put(f"/api/bundles/{fb.id}", content=data, headers=HOST).json()["new"] is False
    # a newer build of the deck: listed instead of the older one, which stays playable
    fb2 = make_bundle(tmp / "laptop2", title="Test deck v2")
    later = (fb.path / "deck.json").stat().st_mtime + 60
    os.utime(fb2.path / "deck.json", (later, later))                     # built a minute later
    (b2,), _ = find_bundles([fb2.path])
    assert client.put(f"/api/bundles/{fb2.id}", content=pack(b2), headers=HOST).status_code == 201
    assert [d["bundle"] for d in client.get("/api/decks", headers=HOST).json()] == [fb2.id]
    assert sorted(p.name for p in (tmp / "data" / "bundles" / "local" / "test").iterdir()) == sorted([fb.id, fb2.id])
    assert client.get(f"/bundle/{fb.id}/slides/{picture}").status_code == 200
    with client.websocket_connect("/ws") as h:                   # an older PPTX plays its own version
        assert hello(h, fb)["pin"]
        listed = {d["bundle"]: d for d in client.get("/api/decks", headers=HOST).json()}
        assert set(listed) == {fb.id, fb2.id} and listed[fb.id]["game"]   # the one being played, too


def test_a_deck_uploaded_by_hand(hosted):
    """The deck lists of texstage and the host page upload a deck's .bundle.zip (POST
    /api/bundles): its deck.json names the bundle. A .bundle folder zipped by hand is taken
    the same way - the files in their folder, backslashes, Finder's and Explorer's extras."""
    client, fb, tmp = hosted
    (b,), _ = find_bundles([fb.path])
    data = pack(b)
    assert client.post("/api/bundles", content=data).status_code == 403
    r = client.post("/api/bundles", content=data, headers=HOST)
    assert r.status_code == 201 and r.json() == {"bundle": fb.id, "deck": "test", "name": "Test deck",
                                                 "quizzes": 8, "slides": len(fb.slides), "new": True}
    assert client.get("/api/decks", headers=HOST).json()[0]["complete"] is True
    r = client.post("/api/bundles", content=data, headers=HOST)
    assert r.status_code == 200 and r.json()["new"] is False                 # the server has it already
    fb2 = make_bundle(tmp / "laptop2", title="Test deck v2")
    later = (fb.path / "deck.json").stat().st_mtime + 60
    os.utime(fb2.path / "deck.json", (later, later))
    files = {p.relative_to(fb2.path).as_posix(): p.read_bytes() for p in fb2.path.rglob("*") if p.is_file()}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            info = zipfile.ZipInfo("x", date_time=time.localtime(later)[:6])
            info.filename = "test.bundle\\" + name.replace("/", "\\")      # as PowerShell 5's Compress-Archive
            z.writestr(info, content)
        z.writestr("__MACOSX/test.bundle/._deck.json", b"x")
        z.writestr("test.bundle/.DS_Store", b"x")
        z.writestr("test.bundle/Thumbs.db", b"x")
    r = client.post("/api/bundles", content=buf.getvalue(), headers=HOST)
    assert r.status_code == 201 and r.json()["bundle"] == fb2.id
    assert [d["bundle"] for d in client.get("/api/decks", headers=HOST).json()] == [fb2.id]
    assert sorted(p.relative_to(tmp / "data" / "bundles" / "local" / "test" / fb2.id).as_posix()
                  for p in (tmp / "data" / "bundles" / "local" / "test" / fb2.id).rglob("*") if p.is_file()) == sorted(files)
    nested = zipped({f"lecture/build/test.bundle/{n}": c for n, c in files.items()})   # deeper: the same
    assert client.post("/api/bundles", content=nested, headers=HOST).json()["new"] is False


def test_bad_uploads_by_hand(hosted, monkeypatch):
    import json
    client, fb, tmp = hosted
    (b,), _ = find_bundles([fb.path])
    good = pack(b)
    files = {name: zipfile.ZipFile(io.BytesIO(good)).read(name) for name in zipfile.ZipFile(io.BytesIO(good)).namelist()}

    def post(data):
        r = client.post("/api/bundles", content=data, headers=HOST)
        return r.status_code, r.json().get("error", "")

    assert post(b"not a zip")[0] == 400
    status, error = post(zipped({"keys.json": files["keys.json"]}))
    assert status == 400 and "no deck.json" in error
    status, error = post(zipped({"talk.pptx": b"x", **{f"talk.bundle/{n}": c for n, c in files.items()}}))
    assert status == 400 and "no deck.json" in error                          # the whole build folder
    deck = json.loads(files["deck.json"])
    status, error = post(zipped({**files, "deck.json": json.dumps(deck | {"bundle": "../x"}).encode()}))
    assert status == 400 and "bundle ID" in error
    status, error = post(zipped({**files, "deck.json": json.dumps(deck | {"name": "Changed"}).encode()}))
    assert status == 400 and "do not match" in error and str(tmp) not in error   # no server folders in it
    status, error = post(zipped({**files, "../../evil.txt": b"x"}))
    assert status == 400 and "evil" in error
    monkeypatch.setattr(app_module, "BUNDLE_MAX", 1000)
    assert post(good)[0] == 413
    assert list((tmp / "data" / "bundles").iterdir()) == []         # nothing arrived
    assert list((tmp / "data" / "incoming").iterdir()) == []        # nothing left over


def test_a_played_deck_survives_a_rebuild(tmp_path):
    """A laptop's build folder: the deck a game plays is copied into the data folder, so a
    rebuild (which replaces the folder) leaves the game - or an older PPTX - its pictures."""
    import shutil
    fb = make_bundle(tmp_path / "bundles")
    picture = next((fb.path / "slides").iterdir()).name
    with TestClient(create_app(config(tmp_path))) as client:
        with client.websocket_connect("/ws") as h:
            assert hello(h, fb)["pin"]
        assert (tmp_path / "data" / "served" / "test" / fb.id / "deck.json").is_file()
        shutil.rmtree(fb.path)
        new = make_bundle(tmp_path / "bundles", time=30)                 # rebuilt in the same folder
        assert new.path == fb.path and new.id != fb.id
        assert client.get(f"/bundle/{fb.id}/slides/{picture}").status_code == 200
        assert client.get(f"/api/deck/{fb.id}", headers=HOST).status_code == 200
        assert new.id in {d["bundle"] for d in client.get("/api/decks", headers=HOST).json()}


def test_a_refused_rename_is_tried_again(tmp_path, monkeypatch):
    """Windows may refuse to rename a folder for a moment after files were written into it (a
    virus scanner, the search indexer): the server tries again before an upload fails."""
    src, dest = tmp_path / "new", tmp_path / "build"
    src.mkdir()
    real, calls = Path.rename, []

    def flaky(self, target):
        calls.append(target)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", flaky)
    monkeypatch.setattr(app_module.time, "sleep", lambda s: None)
    app_module.rename(src, dest)
    assert dest.is_dir() and len(calls) == 3

    def refused(self, target):
        raise PermissionError(5, "Access is denied")
    monkeypatch.setattr(Path, "rename", refused)
    with pytest.raises(PermissionError):
        app_module.rename(dest, src, tries=3)


def test_the_newest_builds_are_kept(hosted, monkeypatch):
    client, _, tmp = hosted
    monkeypatch.setattr(app_module, "KEEP_BUILDS", 3)
    ids = []
    for i in range(5):
        fb = make_bundle(tmp / f"build{i}", time=10 + i)
        t = 1_700_000_000 + 60 * i                                        # built a minute apart
        os.utime(fb.path / "deck.json", (t, t))
        (b,), _ = find_bundles([fb.path])
        assert client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=HOST).status_code == 201
        ids.append(fb.id)
    kept = {p.name for p in (tmp / "data" / "bundles" / "local" / "test").iterdir()}
    assert kept == set(ids[-3:])
    assert [d["bundle"] for d in client.get("/api/decks", headers=HOST).json()] == [ids[-1]]
    assert client.get(f"/api/deck/{ids[0]}", headers=HOST).status_code == 404   # cleaned up: a PPTX
                                                                                 # of it uploads it again


def test_a_pptx_brings_its_bundle(hosted):
    """The join slide's add-in uploads what the PPTX carries (bundle.carried): enough for
    presenting, marked incomplete; the full build replaces it (texstage publish)."""
    import json

    from texstage.build.bundle import carried
    client, fb, tmp = hosted
    deck = json.loads((fb.path / "deck.json").read_text(encoding="utf-8"))
    keys = json.loads((fb.path / "keys.json").read_text(encoding="utf-8"))
    files = {p.relative_to(fb.path).as_posix(): p.read_bytes() for p in fb.path.glob("*/*.png")}
    r = client.put(f"/api/bundles/{fb.id}", content=carried(deck, keys, files), headers=HOST)
    assert r.status_code == 201
    (d,) = client.get("/api/decks", headers=HOST).json()
    assert d["bundle"] == fb.id and d["complete"] is False
    assert client.get(f"/api/deck/{fb.id}", headers=HOST).status_code == 200      # the add-in can play
    with client.websocket_connect("/ws") as h:
        assert hello(h, fb)["pin"]
    (b,), _ = find_bundles([fb.path])
    r = client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=HOST)     # the full build
    assert r.status_code == 201 and r.json()["new"] is True
    assert client.get("/api/decks", headers=HOST).json()[0]["complete"] is True
    assert client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=HOST).json()["new"] is False


def test_the_stage_pdf_travels_with_the_bundle(hosted):
    """texstage publish sends a --stage build's PDF along. The bundle a PPTX carries has
    none, so the server counts it incomplete until the full build arrives."""
    import json

    from texstage.build.bundle import carried
    client, _, tmp = hosted
    fb = make_bundle(tmp / "staged", stage=True)
    deck = json.loads((fb.path / "deck.json").read_text(encoding="utf-8"))
    keys = json.loads((fb.path / "keys.json").read_text(encoding="utf-8"))
    files = {p.relative_to(fb.path).as_posix(): p.read_bytes() for p in fb.path.glob("*/*.*")}
    assert deck["pdf"]["file"] in files
    assert client.put(f"/api/bundles/{fb.id}", content=carried(deck, keys, files), headers=HOST).status_code == 201
    assert client.get("/api/decks", headers=HOST).json()[0]["complete"] is False
    assert client.get(f"/api/deck/{fb.id}/pdf", headers=HOST).status_code == 404
    (b,), _ = find_bundles([fb.path])
    with zipfile.ZipFile(io.BytesIO(pack(b))) as z:
        assert deck["pdf"]["file"] in z.namelist()
    assert client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=HOST).status_code == 201
    assert client.get("/api/decks", headers=HOST).json()[0]["complete"] is True
    assert client.get(f"/api/deck/{fb.id}/pdf", headers=HOST).content == fb.pdf


def test_published_videos_include_declared_movies_and_posters(hosted):
    """Publishing a video deck carries every supported local movie and online poster."""
    import json

    from texstage.build.bundle import bundle_id, content_name
    from texstage.server.bundles import load_bundle

    client, _, tmp = hosted
    folder = tmp / "video.bundle"
    image = b"slide image"
    slide = content_name("slides", image, ".png")
    assets = {slide: image}
    posters = [content_name("media", b"poster " + ext.encode(), ext) for ext in (".png", ".jpg")]
    assets.update({name: b"poster " + Path(name).suffix.encode() for name in posters})
    items = {}
    for n, ext in enumerate((".mp4", ".m4v", ".webm", ".mov")):
        data = b"movie " + ext.encode()
        movie = content_name("media", data, ext)
        assets[movie] = data
        items[f"clip{n}"] = {"media": movie, "poster": posters[n % 2]}
    online_poster = content_name("media", b"online poster", ".png")
    assets[online_poster] = b"online poster"
    items["online"] = {"src": "https://example.org/lecture.mp4", "player": {"file": "https://example.org/lecture.mp4"},
                       "poster": online_poster}
    deck = {"format": 2, "deck": "videos", "name": "Videos", "types": ["video"],
            "image": {"width": 1920, "height": 1080}, "slides": [{"id": 256, "image": slide}],
            "items": {"video": items}}
    keys = {"format": 2, "deck": "videos", "items": {}}
    bid = bundle_id(deck, keys)
    for name, data in assets.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    unused = content_name("media", b"unreferenced private recording", ".mp4")
    (folder / unused).write_bytes(b"unreferenced private recording")
    for name, obj in (("deck.json", deck), ("keys.json", keys)):
        (folder / name).write_text(json.dumps(obj | {"bundle": bid}), encoding="utf-8")
    packed = pack(load_bundle(folder))
    with zipfile.ZipFile(io.BytesIO(packed)) as z:
        assert set(z.namelist()) == {"deck.json", "keys.json", *assets}
        assert len(z.namelist()) == len(set(z.namelist()))   # shared posters are packed once
        for name, data in assets.items():
            assert z.read(name) == data
    assert client.put(f"/api/bundles/{bid}", content=packed, headers=HOST).status_code == 201
    assert client.get("/api/decks", headers=HOST).json()[0]["complete"] is True
    media = client.post(f"/api/deck/{bid}/media", headers=HOST).json()
    assert set(media) == {item["media"] for item in items.values() if "media" in item}
    for name, url in media.items():
        assert client.get(url).content == assets[name]
    for name in [*posters, online_poster]:
        response = client.get(f"/bundle/{bid}/{name}")
        assert response.status_code == 200 and response.content == assets[name]


def test_bad_uploads(hosted, monkeypatch):
    client, fb, tmp = hosted
    (b,), _ = find_bundles([fb.path])
    good = pack(b)
    files = {name: zipfile.ZipFile(io.BytesIO(good)).read(name) for name in zipfile.ZipFile(io.BytesIO(good)).namelist()}

    def put(data, bid=fb.id):
        r = client.put(f"/api/bundles/{bid}", content=data, headers=HOST)
        return r.status_code, r.json().get("error", "") if r.headers["content-type"] == "application/json" else r.text

    assert put(good, "0123456789abcdef")[0] == 400                  # another bundle's ID
    assert put(good, "../../x")[0] == 404
    assert put(b"not a zip")[0] == 400
    status, error = put(zipped({**files, "../../evil.txt": b"x"}))
    assert status == 400 and "evil" in error
    assert not (tmp / "evil.txt").exists() and not (tmp / "data" / "evil.txt").exists()
    assert put(zipped({k: v for k, v in files.items() if k != "keys.json"}))[0] == 400
    bad_deck = make_bundle(tmp / "other", deck="Bad Deck")
    (bb,), _ = find_bundles([bad_deck.path])
    status, error = put(pack(bb), bad_deck.id)
    assert status == 400 and "deck" in error
    monkeypatch.setattr(app_module, "BUNDLE_MAX", 1000)
    assert put(good)[0] == 413
    assert list((tmp / "data" / "bundles").iterdir()) == []         # nothing arrived
    assert list((tmp / "data" / "incoming").iterdir()) == []        # nothing left over


def test_the_presenter_key_stays_on_the_machine(hosted):
    client = TestClient(hosted[0].app, client=("127.0.0.1", 50000))
    assert client.get("http://localhost:8470/api/presenter-key").json() == {"key": KEY}
    assert client.get("http://[::1]:8470/api/presenter-key").status_code == 200
    # behind a proxy on the same machine, or a web page whose name resolves to 127.0.0.1
    assert client.get("http://localhost:8470/api/presenter-key",
                      headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 403
    assert client.get("http://localhost:8470/api/presenter-key",                 # Cloudflare's tunnel
                      headers={"CF-Connecting-IP": "203.0.113.9"}).status_code == 403
    assert client.get("http://quiz.example.org/api/presenter-key").status_code == 403
    assert client.get("http://evil.test:8470/api/presenter-key").status_code == 403


def test_wrong_pins_are_limited(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "WRONG_PINS", (3, 600))
    fb = make_bundle(tmp_path / "bundles")
    with TestClient(create_app(config(tmp_path))) as client:
        with client.websocket_connect("/ws") as h, client.websocket_connect("/ws") as p:
            pin = hello(h, fb)["pin"]
            wrong = "000000" if pin != "000000" else "111111"
            for i in range(3):
                p.send_json({"t": "join", "pin": wrong, "nickname": "Eve", "id": i})
                assert recv(p, "error")["error"] == "unknown-pin"
            p.send_json({"t": "join", "pin": pin, "nickname": "Eve", "id": "right"})
            assert recv(p, "error")["error"] == "too-many-attempts"


def test_keys(tmp_path, monkeypatch):
    from texstage import keys
    servers = tmp_path / "servers.json"
    monkeypatch.delenv("TEXQUIZ_KEY", raising=False)
    with pytest.raises(PublishError, match="no presenter key"):
        find_key("https://q.test", None, servers)
    remember_key("https://q.test", "kept", servers)
    assert find_key("https://q.test", None, servers) == "kept"
    # a server on this machine: the key in its data folder (made on first use, as the server does)
    local = keys.find_key("http://localhost:8470", None, servers, data_dir=tmp_path / "data")
    assert local and (tmp_path / "data" / "presenter-key").read_text().strip() == local
    assert keys.find_key("http://[::1]:8470", None, servers, data_dir=tmp_path / "data") == local
    monkeypatch.setenv("TEXQUIZ_KEY", "env")
    assert find_key("https://q.test", None, servers) == "env"
    assert find_key("https://q.test", "given", servers) == "given"


@contextlib.contextmanager
def running(app):
    """A real server for `app` on a free port, in a thread: its address."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(10)


@pytest.fixture
def live(tmp_path):
    """A real server on a free port (texstage publish speaks HTTP through urllib)."""
    (tmp_path / "srv").mkdir()
    with running(create_app(config(tmp_path / "srv"))) as url:
        yield url


def test_behind_a_proxy(live):
    """Caddy on the same machine: uvicorn trusts its X-Forwarded-* headers (from 127.0.0.1)."""
    import urllib.error
    import urllib.request
    import xml.etree.ElementTree as ET

    proxied = {"Host": "quiz.example.org", "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.5"}

    def get(path, headers):
        with urllib.request.urlopen(urllib.request.Request(live + path, headers=headers), timeout=10) as r:
            return r.read()

    root = ET.fromstring(get("/addin/manifest.xml", proxied))       # the add-in's page over HTTPS
    ns = {"o": "http://schemas.microsoft.com/office/appforoffice/1.1"}
    assert root.find("o:DefaultSettings/o:SourceLocation", ns).get("DefaultValue") == "https://quiz.example.org/addin/"
    with pytest.raises(urllib.error.HTTPError) as err:
        get("/api/presenter-key", proxied)
    assert err.value.code == 403
    assert b'"key"' in get("/api/presenter-key", {})                 # on the machine itself: yes


def test_publish_command(live, tmp_path, capsys):
    fb = make_bundle(tmp_path / "chapter" / "build" / "texquiz")
    (b,), _ = find_bundles([tmp_path / "chapter"])
    assert publish([b], live, KEY, say=lambda s: None) == 1
    assert publish([b], live, KEY, say=lambda s: None) == 0          # there already
    with pytest.raises(PublishError, match="does not accept"):
        publish([b], live, "wrong")
    fb2 = make_bundle(tmp_path / "chapter2", title="Second deck", deck="second")
    assert main(["publish", str(fb2.path), "--url", live + "/", "--key", KEY]) == 0
    assert f"second: bundle {fb2.id} published" in capsys.readouterr().out
    assert main(["publish", str(tmp_path / "nothing"), "--url", live, "--key", KEY]) == 1
    assert main(["publish", str(fb.path), "--url", "http://127.0.0.1:9", "--key", KEY]) == 1
