# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What a data folder holds per deck, and cleaning it by hand (server/datafolder.py; the deck management review's
item 9 - the lecturer chose "by hand only", 2026-11-17): texstage data shows it, the deck page's Storage a
lecturer's own (GET /api/storage); texstage data clean --before DATE lists what would go - ended lectures, their
recordings alone, copies kept for games - and deletes it with --yes, never an open game or what it uses, nor a
folder whose recording is still being made."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from starlette.testclient import TestClient

from fake_bundle import make_bundle
from test_server import KEY, config, join, say_hello
from texstage import cli
from texstage.server import datafolder
from texstage.server.app import create_app

HOST = {"X-Texquiz-Key": KEY}
TOMORROW = int(time.time() * 1000) + 86_400_000


def lecture(tmp_path):
    """A data folder with a deck's two lectures - the first ended, with a phone, its results and a recording in
    its archive folder; the second still open - and a copy kept for a game of another build."""
    fb = make_bundle(tmp_path / "bundles", deck="talk", title="Talk", stage=True)
    data = tmp_path / "data"
    with TestClient(create_app(config(tmp_path))) as client:
        with client.websocket_connect("/ws") as st, client.websocket_connect("/ws") as phone:
            first = say_hello(st, fb, role="stage")
            join(phone, first["pin"], "Ada")
            assert client.post(f"/api/decks/talk/lectures/{first['session']}/end", headers=HOST).status_code == 200
        with client.websocket_connect("/ws") as st:
            second = say_hello(st, fb, role="stage")                        # open, its archive folder empty
        storage = client.get("/api/storage", headers=HOST).json()
    (place,) = [p for p in (data / "archive" / "talk").iterdir() if p.name.endswith(first["pin"])]
    (place / "recording-0123456789ab.webm").write_bytes(b"x" * 5000)
    old = make_bundle(tmp_path / "old", deck="talk", title="Talk", time=30)
    shutil.copytree(old.path, data / "served" / "talk" / old.id)            # a copy no open game plays
    return fb, data, first, second, place, old, storage


def test_what_the_data_folder_holds_per_deck(tmp_path):
    fb, data, first, second, place, old, storage = lecture(tmp_path)
    (deck,) = datafolder.overview(data)
    assert (deck.deck, deck.lectures, deck.recordings, deck.recordings_bytes) == ("talk", 1, 1, 5000)
    assert deck.archive_bytes > 0 and deck.copies >= 1 and deck.total == deck.uploads_bytes + deck.copies_bytes + \
        deck.archive_bytes + deck.recordings_bytes
    assert [d["deck"] for d in storage] == ["talk"] and storage[0]["lectures"] == 1     # (the page's: the lecturer's)
    assert datafolder.overview(data, owner="bob") == []                              # (another lecturer's: none)
    assert cli.main(["data", "--data", str(data)]) == 0
    assert cli.main(["data", "clean", "--before", "2099-01-01", "--data", str(data)]) == 2   # (what goes: unsaid)


def test_cleaning_lists_first_deletes_with_yes_and_leaves_what_is_in_use(tmp_path, capsys):
    fb, data, first, second, place, old, storage = lecture(tmp_path)
    gone = datafolder.plan(data, TOMORROW, lectures=True, copies=True)
    assert [(g.kind, g.deck) for g in gone if g.kind == "lecture"] == [("lecture", "talk")]        # the ended one
    assert first["pin"] in gone[0].what and not any(second["pin"] in g.what for g in gone)          # not the open one
    copies = [g for g in gone if g.kind == "copy"]
    assert [g.what for g in copies] == [old.id], "not a copy the open game plays"
    assert datafolder.plan(data, int(time.time() * 1000) - 86_400_000, lectures=True, copies=True) == []   # (before)
    (place / "recording-ba9876543210.webm.part").write_bytes(b"y")             # a recording still being made
    for what in ({"lectures": True}, {"recordings": True}):                # left - and said so, with why
        assert [(g.kind, "still being made" in g.what) for g in datafolder.plan(data, TOMORROW, **what)] == [("held", True)]
    (place / "recording-ba9876543210.webm.part").unlink()
    (recording,) = datafolder.plan(data, TOMORROW, recordings=True)
    assert recording.kind == "recording" and recording.bytes == 5000
    capsys.readouterr()
    assert cli.main(["data", "clean", "--before", "2099-01-01", "--recordings", "--data", str(data)]) == 0
    said = capsys.readouterr().out
    assert "recording-0123456789ab.webm" in said and "nothing deleted yet" in said
    assert (place / "recording-0123456789ab.webm").exists(), "listed only"
    assert cli.main(["data", "clean", "--before", "2099-01-01", "--recordings", "--yes", "--data", str(data)]) == 0
    assert not (place / "recording-0123456789ab.webm").exists() and place.exists(), "the recording alone"
    assert cli.main(["data", "clean", "--before", "2099-01-01", "--lectures", "--copies", "--yes", "--data", str(data)]) == 0
    assert not place.exists() and not (data / "served" / "talk" / old.id).exists()
    with TestClient(create_app(config(tmp_path))) as client:
        listed = client.get("/api/decks/talk/lectures", headers=HOST).json()
        assert [x["pin"] for x in listed] == [second["pin"]], "the ended lecture's rows are gone, the open game stays"
    assert cli.main(["data", "clean", "--before", "yesterday", "--lectures", "--data", str(data)]) == 2
    assert json.loads(json.dumps(datafolder.overview(data)[0].view()))["lectures"] == 0


def test_a_whiteboard_only_lecture_is_a_lecture_and_storage_is_the_lecturers_own(tmp_path):
    """A lecture that left whiteboard pages alone counted as "a game that left nothing" - and was deleted under
    that word (the review of 2026-11-17, F3): one rule, the deck page's Lectures'. Another lecturer's Storage
    shows nothing of it (D10)."""
    import sqlite3

    from texstage.server.lecturers import Lecturers
    fb, data, first, second, place, old, storage = lecture(tmp_path)
    db = sqlite3.connect(data / datafolder.STORE)
    db.execute("UPDATE sessions SET ended = ?, stage = ? WHERE id = ?",
               (int(time.time() * 1000), json.dumps({"boards": [{"id": "b1", "strokes": []}]}), second["session"]))
    db.commit()
    db.close()
    (deck,) = datafolder.overview(data)
    assert deck.lectures == 2
    kinds = [(g.kind, second["pin"] in g.what) for g in datafolder.plan(data, TOMORROW, lectures=True)]
    assert ("lecture", True) in kinds and not any(k == "empty" for k, _ in kinds)
    bob = {"X-Texquiz-Key": Lecturers(data / "lecturers.json").add("bob")}
    with TestClient(create_app(config(tmp_path))) as client:
        assert client.get("/api/storage", headers=bob).json() == []
        assert [d["deck"] for d in client.get("/api/storage", headers=HOST).json()] == ["talk"]


def test_what_cannot_be_moved_aside_keeps_its_rows_and_is_said(tmp_path, monkeypatch, capsys):
    """clean --yes deleted a lecture's rows, then its folder with errors ignored: a file held open stayed, an
    orphan no listing found, and was counted as freed (the review of 2026-11-17, F2). Now each folder is moved
    aside whole first; one that is refused keeps its rows, is not counted, and is said."""
    fb, data, first, second, place, old, storage = lecture(tmp_path)
    real = datafolder.os.replace

    def refuse_the_lecture(src, dst):
        if Path(src) == place:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real(src, dst)
    monkeypatch.setattr(datafolder.os, "replace", refuse_the_lecture)
    capsys.readouterr()
    assert cli.main(["data", "clean", "--before", "2099-01-01", "--lectures", "--yes", "--data", str(data)]) == 1
    out = capsys.readouterr()
    assert "not cleaned:" in out.err and "being used by another process" in out.err and "0 cleaned, 0 B freed" in out.out
    assert place.exists()
    with TestClient(create_app(config(tmp_path))) as client:                # its rows: still there
        assert first["pin"] in [x["pin"] for x in client.get("/api/decks/talk/lectures", headers=HOST).json()]


def test_a_recording_is_listed_once_and_one_quiet_for_a_day_is_abandoned(tmp_path, capsys):
    """--recordings listed a recording's .json as one more (N1); a .part blocked its lecture for ever, unsaid (D4):
    one written to within a day is being made - left, and said -, one quiet longer was abandoned."""
    fb, data, first, second, place, old, storage = lecture(tmp_path)
    (place / "recording-0123456789ab.json").write_text("{}", encoding="utf-8")
    gone = datafolder.plan(data, TOMORROW, recordings=True)
    assert [g.what.split(": ")[-1] for g in gone] == ["recording-0123456789ab.webm"]
    part = place / "recording-ba9876543210.webm.part"
    part.write_bytes(b"y" * 10)
    capsys.readouterr()
    assert cli.main(["data", "clean", "--before", "2099-01-01", "--lectures", "--data", str(data)]) == 0
    out = capsys.readouterr().out
    assert "left alone" in out and "still being made" in out
    day_ago = time.time() - 2 * 86_400
    os.utime(part, (day_ago, day_ago))                                      # quiet for two days: abandoned
    kinds = [g.kind for g in datafolder.plan(data, TOMORROW, lectures=True)]
    assert "held" not in kinds and "lecture" in kinds
    assert cli.main(["data", "clean", "--before", "2099-01-01", "--recordings", "--yes", "--data", str(data)]) == 0
    assert not (place / "recording-0123456789ab.json").exists() and not part.exists()   # (the .json went with it)

