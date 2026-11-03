# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Lecturers with keys of their own (server/lecturers.py): each sees only their own decks,
games and results; uploaded decks belong to the uploader, decks in served folders are open."""
from __future__ import annotations

import json
import os
import sqlite3

import pytest
from starlette.testclient import TestClient

from fake_bundle import make_bundle
from test_server import KEY, config, hello, recv
from texstage.cli import main
from texstage.publish import find_bundles, pack
from texstage.server.app import create_app
from texstage.server.lecturers import LecturerError, Lecturers
from texstage.server.store import Store


def test_the_list_of_lecturers(tmp_path):
    path = tmp_path / "lecturers.json"
    lecturers = Lecturers(path, own={"Owner": "own-key"})
    ada = lecturers.add("Ada")
    assert lecturers.names() == ["ada", "owner"]
    assert lecturers.who(ada) == "ada" and lecturers.who("own-key") == "owner"
    assert lecturers.who("nope") is None and lecturers.who(None) is None and lecturers.who("") is None
    assert ada not in path.read_text(encoding="utf-8")                   # only the hash is kept
    with pytest.raises(LecturerError):
        lecturers.add("ada")
    with pytest.raises(LecturerError):
        lecturers.add("../evil")
    other = Lecturers(path)                                               # e.g. texstage lecturer, meanwhile
    new = other.renew("ada")
    assert lecturers.who(ada) is None and lecturers.who(new) == "ada"    # the running server sees it
    assert other.remove("ada") and not other.remove("ada")
    assert lecturers.who(new) is None


@pytest.mark.parametrize("change", ["renew", "remove"])
def test_lecturer_changes_with_the_same_timestamp(tmp_path, change):
    """A replacement file invalidates cached keys even within one clock tick."""
    path = tmp_path / "lecturers.json"
    lecturers = Lecturers(path)
    old = lecturers.add("ada")
    assert lecturers.who(old) == "ada"
    stamp = path.stat()
    other = Lecturers(path)
    if change == "renew":
        new = other.renew("ada")
        assert path.stat().st_size == stamp.st_size
    else:
        assert other.remove("ada")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert path.stat().st_mtime_ns == stamp.st_mtime_ns
    assert lecturers.who(old) is None
    if change == "renew":
        assert lecturers.who(new) == "ada"
    else:
        assert lecturers.names() == []


@pytest.fixture
def two(tmp_path):
    """A server with its own lecturer (KEY, 'local') and two more, ada and bob."""
    lecturers = Lecturers(tmp_path / "data" / "lecturers.json")
    keys = {"ada": lecturers.add("ada"), "bob": lecturers.add("bob")}
    (tmp_path / "bundles").mkdir()
    with TestClient(create_app(config(tmp_path))) as client:
        yield client, keys, tmp_path


def upload(client, fb, key):
    (b,), _ = find_bundles([fb.path])
    return client.put(f"/api/bundles/{fb.id}", content=pack(b), headers={"X-Texquiz-Key": key})


def decks(client, key):
    return {d["bundle"]: d for d in client.get("/api/decks", headers={"X-Texquiz-Key": key}).json()}


def test_lecturers_are_kept_apart(two):
    client, keys, tmp = two
    ada_deck = make_bundle(tmp / "ada", title="Ada's deck")              # both decks are called "test"
    bob_deck = make_bundle(tmp / "bob", title="Bob's deck")
    assert upload(client, ada_deck, keys["ada"]).status_code == 201
    assert upload(client, bob_deck, keys["bob"]).status_code == 201
    assert (tmp / "data" / "bundles" / "ada" / "test" / ada_deck.id).is_dir()
    assert set(decks(client, keys["ada"])) == {ada_deck.id} and set(decks(client, keys["bob"])) == {bob_deck.id}
    assert decks(client, KEY) == {}                                       # the server's own lecturer
    h = {"X-Texquiz-Key": keys["bob"]}
    assert client.get(f"/api/deck/{ada_deck.id}", headers=h).status_code == 404
    with client.websocket_connect("/ws") as ws:                         # bob cannot play ada's deck
        ws.send_json({"t": "hello", "role": "host", "key": keys["bob"], "deck": "test", "bundle": ada_deck.id, "id": 1})
        assert recv(ws, "error")["error"] == "unknown-bundle"
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.send_json({"t": "hello", "role": "host", "key": keys["ada"], "deck": "test", "bundle": ada_deck.id, "id": 1})
        b.send_json({"t": "hello", "role": "host", "key": keys["bob"], "deck": "test", "bundle": bob_deck.id, "id": 1})
        wa, wb = recv(a, "welcome"), recv(b, "welcome")
        assert wa["session"] != wb["session"] and wa["pin"] != wb["pin"]  # the same deck name, two games
    assert decks(client, keys["ada"])[ada_deck.id]["game"]["pin"] == wa["pin"]
    assert client.get(f"/api/results/{wa['session']}.csv", headers=h).status_code == 404
    assert client.get(f"/api/results/{wa['session']}.csv", headers={"X-Texquiz-Key": keys["ada"]}).status_code == 200
    # the same build, uploaded by bob too: both may play it, each their own game
    assert upload(client, ada_deck, keys["bob"]).status_code == 201
    assert ada_deck.id in decks(client, keys["bob"])


def test_served_folders_are_open_to_every_lecturer(tmp_path):
    lecturers = Lecturers(tmp_path / "data" / "lecturers.json")
    ada = lecturers.add("ada")
    fb = make_bundle(tmp_path / "bundles")
    with TestClient(create_app(config(tmp_path))) as client:
        assert fb.id in decks(client, ada) and fb.id in decks(client, KEY)
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as o:
            pa = hello(a, fb)["pin"]
            o.send_json({"t": "hello", "role": "host", "key": ada, "deck": fb.deck, "bundle": fb.id, "id": 1})
            assert recv(o, "welcome")["pin"] != pa
        assert upload(client, fb, ada).json()["new"] is False            # there already, for her too


def test_an_older_database_gets_the_owner_column(tmp_path):
    db = sqlite3.connect(tmp_path / "old.sqlite3")
    db.execute("CREATE TABLE sessions (id, pin, deck, bundle, created, last_active, ended, finished, slide, "
               "current, PRIMARY KEY (id))")
    db.execute("INSERT INTO sessions VALUES ('s1', '123456', 'demo', 'b', 1, 1, NULL, NULL, NULL, NULL)")
    db.commit()
    db.close()
    (s,) = Store(tmp_path / "old.sqlite3").load()
    assert s.id == "s1" and s.owner == ""


def test_lecturer_command(tmp_path, capsys):
    data = str(tmp_path / "data")
    assert main(["lecturer", "add", "Ada", "--data", data]) == 0
    key = capsys.readouterr().out.split("\n\n")[1].strip()
    assert Lecturers(tmp_path / "data" / "lecturers.json").who(key) == "ada"
    assert main(["lecturer", "add", "ada", "--data", data]) == 1          # there already
    assert main(["lecturer", "list", "--data", data]) == 0 and "ada" in capsys.readouterr().out
    assert main(["lecturer", "renew", "ada", "--data", data]) == 0
    assert Lecturers(tmp_path / "data" / "lecturers.json").who(key) is None
    assert main(["lecturer", "remove", "ada", "--data", data]) == 0
    assert json.loads((tmp_path / "data" / "lecturers.json").read_text()) == {}
