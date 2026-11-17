# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The bundle store's look at the folders (server/bundles.py): a folder is read again only where its files
changed since the last look, the deck list looks in a worker thread - off the event loop, where the phones'
answers are -, and a build's time is the one it was built at (built.json), which its copies keep, not its
deck.json's file time (the deck management review's item 5 and the deck page's suggestions 5 and 11)."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import zipfile
from io import BytesIO

from starlette.testclient import TestClient

from fake_bundle import make_bundle
from test_server import KEY, config
from texstage.build import bundle as build_bundle
from texstage.publish import find_bundles, pack
from texstage.server import bundles
from texstage.server.app import create_app
from texstage.server.bundles import BUILT, BundleStore, load_bundle

HOST = {"X-Texquiz-Key": KEY}


def test_a_look_reads_only_the_folders_that_changed(tmp_path, monkeypatch):
    a = make_bundle(tmp_path / "decks" / "a", deck="a")
    b = make_bundle(tmp_path / "decks" / "b", deck="b")
    read = []
    real = bundles.load_bundle
    monkeypatch.setattr(bundles, "load_bundle", lambda path: read.append(path.parent.name) or real(path))
    store = BundleStore([tmp_path / "decks"])
    assert sorted(read) == ["a", "b"] and len(store.current()) == 2
    read.clear()
    store.scan()
    assert read == [], "nothing changed: nothing read again"
    with monkeypatch.context() as m:                                       # what it offers: as the look found it
        m.setattr(bundles, "holds", lambda b: (_ for _ in ()).throw(AssertionError("read again")))
        assert {x.id for x in store.current()} == {a.id, b.id} and all(store.complete(x) for x in store.current())
    t = os.stat(a.path / "deck.json").st_mtime + 5                         # a's deck.json written again
    os.utime(a.path / "deck.json", (t, t))
    store.scan()
    assert read == ["a"]
    read.clear()
    c = make_bundle(tmp_path / "decks" / "b", deck="b", time=30)            # b rebuilt in its folder
    store.scan()
    assert read == ["b"]
    assert {x.id for x in store.current()} == {a.id, c.id}, "the old build: known, no longer offered"
    assert store.get(b.id) is not None
    shutil.rmtree(a.path)                                                   # a folder gone: forgotten
    store.scan()
    assert {x.id for x in store.current()} == {c.id}


def test_a_broken_folder_is_said_once_and_read_again_when_it_changes(tmp_path):
    good = make_bundle(tmp_path / "decks" / "good", deck="good")
    bad = tmp_path / "decks" / "bad.bundle"
    shutil.copytree(good.path, bad)
    (bad / "keys.json").write_text("{", encoding="utf-8")
    store = BundleStore([tmp_path / "decks"])
    assert len(store.skipped) == 1 and store.skipped[0].deck == "good" and len(store.problems) == 1
    store.scan()
    assert len(store.skipped) == 1, "as the last look found it"
    shutil.copyfile(good.path / "keys.json", bad / "keys.json")             # mended: the same build twice
    store.scan()
    assert store.skipped == [] and [x.id for x in store.current()] == [good.id]


def test_the_deck_list_looks_at_the_folders_off_the_event_loop(tmp_path, monkeypatch):
    make_bundle(tmp_path / "bundles")
    with TestClient(create_app(config(tmp_path))) as client:
        store = client.app.state.server.bundles
        where = []
        real = store.collect

        def collect():
            try:
                asyncio.get_running_loop()
                where.append("event loop")
            except RuntimeError:
                where.append("worker thread")
            return real()
        monkeypatch.setattr(store, "collect", collect)
        decks = client.get("/api/decks", headers=HOST).json()
        assert where == ["worker thread"] and len(decks) == 1


def test_a_builds_time_is_its_own_and_its_copies_keep_it(tmp_path):
    """built.json is the build's time: a copy of an old build - copied, checked out, unpacked - is not the newest
    because its files are new; texstage publish and a server's download carry it; a build before it has none
    and is dated by its deck.json, as before."""
    old = make_bundle(tmp_path / "bundles" / "old", deck="week", title="Old build")
    new = make_bundle(tmp_path / "bundles" / "new", deck="week", title="New build")
    (old.path / BUILT).write_text(json.dumps({"built": 1_700_000_000_000}), encoding="utf-8")
    (new.path / BUILT).write_text(json.dumps({"built": 1_700_000_600_000}), encoding="utf-8")
    t = 1_700_000_300                                                       # new's files: older than old's
    os.utime(new.path / "deck.json", (t, t))
    assert load_bundle(old.path).built == 1_700_000_000_000 and load_bundle(new.path).built == 1_700_000_600_000
    with TestClient(create_app(config(tmp_path))) as client:
        (deck,) = client.get("/api/decks", headers=HOST).json()
        assert (deck["bundle"], deck["built"]) == (new.id, 1_700_000_600_000), "the newer build, not the newer files"
        packed = client.get(f"/api/bundles/{new.id}.zip", headers=HOST).content
    assert json.loads(zipfile.ZipFile(BytesIO(packed)).read(BUILT)) == {"built": 1_700_000_600_000}
    (b,), _ = find_bundles([new.path])
    assert BUILT in zipfile.ZipFile(BytesIO(pack(b))).namelist()            # texstage publish sends it
    other = tmp_path / "other"                                              # an upload keeps it
    with TestClient(create_app(config(other))) as client:
        assert client.put(f"/api/bundles/{new.id}", content=pack(b), headers=HOST).status_code == 201
        (deck,) = client.get("/api/decks", headers=HOST).json()
        assert deck["built"] == 1_700_000_600_000
    (old.path / BUILT).unlink()                                             # a build made before built.json
    assert load_bundle(old.path).built == int(os.stat(old.path / "deck.json").st_mtime * 1000)
    (old.path / BUILT).write_text("{\"built\": \"soon\"}", encoding="utf-8")   # one that cannot be read: the same
    assert load_bundle(old.path).built == int(os.stat(old.path / "deck.json").st_mtime * 1000)


def test_the_build_writes_its_time_beside_deck_json_and_into_its_zip(tmp_path):
    deck, keys = {"format": 2, "deck": "d"}, {"format": 2}
    build_bundle.write_bundle(tmp_path / "d.bundle", deck, keys, {}, built=1234)
    assert json.loads((tmp_path / "d.bundle" / BUILT).read_text(encoding="utf-8")) == {"built": 1234}
    build_bundle.write_zip(tmp_path / "d.bundle.zip", deck, keys, {}, built=1234)
    assert json.loads(zipfile.ZipFile(tmp_path / "d.bundle.zip").read(BUILT)) == {"built": 1234}
    build_bundle.write_bundle(tmp_path / "e.bundle", deck, keys, {})       # (without a time: none, as before)
    assert not (tmp_path / "e.bundle" / BUILT).exists()


def test_a_folder_that_could_not_be_read_is_read_again_at_the_next_look(tmp_path, monkeypatch):
    """A deck.json held open a moment (a sync tool, a virus scanner) made its folder skipped - and the record kept it
    so until its files changed (the review of 2026-11-17, F1): a failed read is read again at every look."""
    a = make_bundle(tmp_path / "decks" / "a", deck="a")
    real, fail = bundles.load_bundle, {"once": True}

    def flaky(path):
        if fail.pop("once", False):
            raise bundles.BundleError(f"{path}: [Errno 13] Permission denied")
        return real(path)
    monkeypatch.setattr(bundles, "load_bundle", flaky)
    store = BundleStore([tmp_path / "decks"])
    assert store.current() == [] and len(store.skipped) == 1
    store.scan()                                                            # the file free again, nothing changed
    assert [x.id for x in store.current()] == [a.id] and store.skipped == []


def test_a_folder_dropped_while_a_look_runs_stays_dropped(tmp_path):
    """A look in a worker thread that read a folder before it was dropped and removed merged its build back - a
    re-upload was then taken for one the server has (the review of 2026-11-17, F5)."""
    a = make_bundle(tmp_path / "decks" / "a", deck="a")
    b = make_bundle(tmp_path / "decks" / "b", deck="b")
    store = BundleStore([tmp_path / "decks"])
    found = store.collect()                                                 # a look, before ...
    store.drop(a.path)                                                      # ... the folder is dropped and gone
    shutil.rmtree(a.path)
    store.apply(found)
    assert [x.id for x in store.current()] == [b.id] and a.id not in store.bundles
    store.scan()
    assert a.id not in store.bundles


def test_a_change_of_built_json_alone_is_seen_and_the_record_is_the_stores_own(tmp_path):
    a = make_bundle(tmp_path / "decks" / "a", deck="a")
    (a.path / BUILT).write_text(json.dumps({"built": 1_700_000_000_000}), encoding="utf-8")
    store = BundleStore([tmp_path / "decks"])
    assert store.bundles[a.id].built == 1_700_000_000_000
    (a.path / BUILT).write_text(json.dumps({"built": 1_700_000_600_000}), encoding="utf-8")
    store.scan()
    assert store.bundles[a.id].built == 1_700_000_600_000                  # (built.json is in the stamp)
    known = store.bundles[a.id]
    known.owners, known.path = {"someone"}, tmp_path / "elsewhere"          # the store's own copy changed ...
    (seen,) = store.seen.values()
    assert seen.bundle.owners is None and seen.bundle.path == a.path        # ... not the record (merge copies)


def test_a_built_time_out_of_reason_is_not_taken(tmp_path):
    """A clock gone wrong, or microseconds for milliseconds, in built.json: such a build would stay the newest -
    its deck could not be taken off the list - and its download failed (the review of 2026-11-17, D3)."""
    a = make_bundle(tmp_path / "decks" / "a", deck="a")
    mtime = int(os.stat(a.path / "deck.json").st_mtime * 1000)
    for value in (int(time.time() * 1000) + 2 * 86_400_000, int(time.time() * 1_000_000), 12, -5):
        (a.path / BUILT).write_text(json.dumps({"built": value}), encoding="utf-8")
        assert load_bundle(a.path).built == mtime, value
    (a.path / BUILT).write_text(json.dumps({"built": int(time.time() * 1000) + 3_600_000}), encoding="utf-8")
    assert load_bundle(a.path).built > mtime                                # (an hour ahead: a clock a little off)


def test_an_unknown_id_does_not_wait_for_a_look_under_way(tmp_path):
    """get() of an unknown ID - a picture asked for without a key - looked at every folder on the event loop and
    waited for a look in a worker thread (the review of 2026-11-17, D1): while one runs, it answers at once."""
    a = make_bundle(tmp_path / "decks" / "a", deck="a")
    store = BundleStore([tmp_path / "decks"])
    store.scanned = 0.0
    with store.looking:                                                     # a look under way elsewhere
        started = time.monotonic()
        assert store.get("0" * 16) is None and time.monotonic() - started < 1
    assert store.get(a.id) is not None

