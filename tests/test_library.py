# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage's deck page (library.py): folders, moving and renaming decks, taking a deck off the
list - a laptop's build comes back with its next build, an uploaded deck is deleted."""
from __future__ import annotations

import os
import time

import pytest
from starlette.testclient import TestClient

from fake_bundle import make_bundle
from test_server import KEY, config
from texstage.publish import find_bundles, pack
from texstage.server.app import create_app
from texstage.server.bundles import BundleStore
from texstage.server.lecturers import Lecturers
from texstage.server.library import Library, LibraryError

HOST = {"X-Texquiz-Key": KEY}


# ------------------------------------------------------------------ the library itself
def test_folders_nest_and_move_up(tmp_path):
    lib = Library(tmp_path / "library.json")
    kg = lib.add_folder("ada", "  Knowledge   Graphs ")
    old = lib.add_folder("ada", "Old", parent=kg)
    deep = lib.add_folder("ada", "Deeper", parent=old)
    assert {f["name"]: f["parent"] for f in lib.folders("ada")} == {"Knowledge Graphs": None, "Old": kg,
                                                                     "Deeper": old}
    assert lib.folders("bob") == []                                       # each lecturer's own
    with pytest.raises(LibraryError):
        lib.change_folder("ada", kg, {"parent": deep})                    # not into one of its own
    with pytest.raises(LibraryError):
        lib.change_folder("ada", kg, {"parent": kg})
    with pytest.raises(LibraryError) as err:
        lib.add_folder("ada", "x", parent="nope")
    assert err.value.missing
    with pytest.raises(LibraryError):
        lib.add_folder("ada", "   ")
    lib.change_deck("ada", "kg-01-intro", {"folder": old, "label": "Intro"})
    lib.remove_folder("ada", old)                                         # its folder and deck move up
    assert {f["name"]: f["parent"] for f in lib.folders("ada")} == {"Knowledge Graphs": None, "Deeper": kg}
    assert lib.view("ada")["decks"]["kg-01-intro"] == {"folder": kg, "label": "Intro"}
    lib.change_deck("ada", "kg-01-intro", {"folder": None, "label": ""})  # back to the top, its own name
    assert "kg-01-intro" not in lib.view("ada")["decks"]
    lib.change_deck("ada", "talk", {"folder": kg, "label": "The talk"})
    lib.remove_folder("ada", kg)                                          # to the top: no folder kept
    assert lib.view("ada")["decks"]["talk"] == {"label": "The talk"}


def test_hide_and_show(tmp_path):
    lib = Library(tmp_path / "library.json")
    lib.hide("ada", "talk", 1000)
    assert lib.view("ada")["decks"]["talk"] == {"hidden": 1000}
    lib.show("ada", "talk")
    assert lib.view("ada")["decks"] == {}
    lib.show("ada", "unknown")                                            # nothing to do


# ------------------------------------------------------------------ the server
@pytest.fixture
def laptop(tmp_path):
    """A laptop's server with two built decks."""
    alpha = make_bundle(tmp_path / "bundles" / "alpha", deck="alpha", title="Alpha")
    beta = make_bundle(tmp_path / "bundles" / "beta", deck="beta", title="Beta")
    with TestClient(create_app(config(tmp_path))) as client:
        yield client, alpha, beta, tmp_path


def listed(client, headers=HOST) -> dict:
    return {d["deck"]: d for d in client.get("/api/decks", headers=headers).json()}


def test_folders_api(laptop):
    client, alpha, beta, _ = laptop
    assert client.get("/api/folders").status_code == 403
    assert client.get("/api/folders", headers=HOST).json() == []
    r = client.post("/api/folders", json={"name": "Talks"}, headers=HOST)
    assert r.status_code == 201
    talks = r.json()["id"]
    sub = client.post("/api/folders", json={"name": "2026", "parent": talks}, headers=HOST).json()["id"]
    assert client.patch(f"/api/folders/{talks}", json={"parent": sub}, headers=HOST).status_code == 400
    assert client.patch(f"/api/folders/{sub}", json={"name": "Keynotes"}, headers=HOST).status_code == 200
    assert client.patch("/api/folders/nope", json={"name": "x"}, headers=HOST).status_code == 404
    assert client.post("/api/folders", content=b"[", headers=HOST).status_code == 400
    # a deck into a folder, with a name of its own
    assert client.patch("/api/decks/alpha", json={"folder": sub, "label": "Alpha, the talk"},
                        headers=HOST).status_code == 200
    assert client.patch("/api/decks/alpha", json={"folder": "nope"}, headers=HOST).status_code == 404
    assert client.patch("/api/decks/gamma", json={"label": "x"}, headers=HOST).status_code == 404
    decks = listed(client)
    assert (decks["alpha"]["folder"], decks["alpha"]["label"]) == (sub, "Alpha, the talk")
    assert (decks["beta"]["folder"], decks["beta"]["label"]) == (None, None)
    assert decks["alpha"]["uploaded"] is False                            # a laptop's build
    # deleting the outer folder: the inner one moves to the top, the deck stays in it
    assert client.delete(f"/api/folders/{talks}", headers=HOST).status_code == 200
    assert client.get("/api/folders", headers=HOST).json() == [{"id": sub, "name": "Keynotes", "parent": None}]
    assert listed(client)["alpha"]["folder"] == sub


def test_a_laptop_build_leaves_the_list_until_the_next_build(laptop):
    client, alpha, beta, tmp = laptop
    r = client.delete("/api/decks/alpha", headers=HOST)
    assert r.status_code == 200 and r.json() == {"deleted": 0, "hidden": True}
    assert set(listed(client)) == {"beta"}
    assert (alpha.path / "deck.json").is_file()                           # the build folder stays
    later = time.time() + 60                                              # built again, a minute later
    os.utime(alpha.path / "deck.json", (later, later))
    assert set(listed(client)) == {"alpha", "beta"}


def test_an_uploaded_deck_is_deleted(tmp_path):
    (tmp_path / "bundles").mkdir()
    fb = make_bundle(tmp_path / "elsewhere", deck="talk", title="Talk")
    with TestClient(create_app(config(tmp_path))) as client:
        (b,), _ = find_bundles([fb.path])
        assert client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=HOST).status_code == 201
        assert listed(client)["talk"]["uploaded"] is True
        folder = tmp_path / "data" / "bundles" / "local" / "talk"
        # a game of it, playing right now: not while it runs
        engine = client.app.state.server.engine
        now = int(time.time() * 1000)
        s = engine.open_session("talk", fb.id, now, owner="local")
        assert client.delete("/api/decks/talk", headers=HOST).status_code == 409
        assert (folder / fb.id / "deck.json").is_file()
        # the game left over from a lecture hours ago: it ends, the deck goes
        s.last_active = now - engine.settings.stale_ms - 1000
        r = client.delete("/api/decks/talk", headers=HOST)
        assert r.status_code == 200 and r.json() == {"deleted": 1, "hidden": False}
        assert s.id not in engine.sessions and not folder.exists()
        assert listed(client) == {}
        assert client.delete("/api/decks/talk", headers=HOST).status_code == 404
        # uploaded again: listed again
        assert client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=HOST).status_code == 201
        assert set(listed(client)) == {"talk"}


def test_each_lecturer_has_a_deck_page_of_their_own(tmp_path):
    keys = {"ada": Lecturers(tmp_path / "data" / "lecturers.json").add("ada")}
    make_bundle(tmp_path / "bundles" / "alpha", deck="alpha", title="Alpha")
    ada = {"X-Texquiz-Key": keys["ada"]}
    with TestClient(create_app(config(tmp_path))) as client:
        fid = client.post("/api/folders", json={"name": "Mine"}, headers=ada).json()["id"]
        assert client.get("/api/folders", headers=HOST).json() == []
        assert client.patch(f"/api/folders/{fid}", json={"name": "x"}, headers=HOST).status_code == 404
        assert client.patch("/api/decks/alpha", json={"folder": fid}, headers=ada).status_code == 200
        assert listed(client, ada)["alpha"]["folder"] == fid and listed(client)["alpha"]["folder"] is None
        assert client.delete("/api/decks/alpha", headers=ada).json()["hidden"] is True
        assert set(listed(client, ada)) == set() and set(listed(client)) == {"alpha"}   # off Ada's list only


@pytest.mark.parametrize("upload_order", [("ada", "bob"), ("bob", "ada")])
@pytest.mark.parametrize("bob_stale", [False, True])
def test_deleting_a_shared_upload_preserves_the_other_lecturers_game(tmp_path, upload_order, bob_stale):
    lecturers = Lecturers(tmp_path / "data" / "lecturers.json")
    headers = {name: {"X-Texquiz-Key": lecturers.add(name)} for name in ("ada", "bob")}
    fb = make_bundle(tmp_path / "elsewhere", deck="talk", stage=True)
    (b,), _ = find_bundles([fb.path])
    with TestClient(create_app(config(tmp_path))) as client:
        for name in upload_order:
            assert client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=headers[name]).status_code == 201
        server = client.app.state.server
        now = int(time.time() * 1000)
        ada = server.engine.open_session("talk", fb.id, now, owner="ada")
        bob = server.engine.open_session("talk", fb.id, now, owner="bob")
        ada.last_active = now - server.engine.settings.stale_ms - 1000
        if bob_stale:
            bob.last_active = ada.last_active
        result = client.delete("/api/decks/talk", headers=headers["ada"])
        assert result.status_code == 200 and result.json() == {"deleted": 1, "hidden": False}
        assert ada.id not in server.engine.sessions
        assert server.engine.sessions[bob.id] is bob and bob.ended is None
        assert not (server.published / "ada" / "talk").exists()
        assert (server.published / "bob" / "talk" / fb.id / "deck.json").is_file()
        # The primary cached copy may have belonged to Ada. Bob's next request must
        # work immediately, and deleting Ada's non-primary copy must revoke her access too.
        assert server.bundles.get(fb.id).owners == {"bob"}
        assert client.get(f"/api/deck/{fb.id}", headers=headers["bob"]).status_code == 200
        assert client.get(f"/api/deck/{fb.id}/pdf", headers=headers["bob"]).content == fb.pdf
        assert client.get(f"/api/deck/{fb.id}", headers=headers["ada"]).status_code == 404
        assert listed(client, headers["ada"]) == {}
        assert listed(client, headers["bob"])["talk"]["game"]["session"] == bob.id
        assert client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=headers["ada"]).status_code == 201
        assert server.bundles.get(fb.id).owners == {"ada", "bob"}


def test_a_scan_during_cleanup_does_not_restore_a_dropped_copy(tmp_path):
    published = tmp_path / "bundles"
    ada = make_bundle(published / "ada" / "talk", deck="talk")
    bob = make_bundle(published / "bob" / "talk", deck="talk")
    store = BundleStore([published], published=published)
    assert ada.id == bob.id and store.get(ada.id).owners == {"ada", "bob"}
    store.drop(ada.path)          # asynchronous filesystem cleanup has not finished yet
    store.scan()
    assert store.get(ada.id).owners == {"bob"}
    assert store.get(ada.id).path == bob.path
    store.add(ada.path)           # an explicit new upload restores this owner's copy
    assert store.get(ada.id).owners == {"ada", "bob"}
