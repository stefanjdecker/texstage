# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The deck page's Lectures and Builds (the review of deck management, its second package): a deck's
games, open and ended, each with its archive - the results, the archive's ZIP, the annotated PDF made from
an ended game's ink -, an ended one deleted; every build of a deck on disk, an older one presented, one
downloaded as the .bundle.zip a server takes, an upload deleted."""
from __future__ import annotations

import io
import os
import sqlite3
import time
import zipfile

from starlette.testclient import TestClient

from fake_bundle import make_bundle
from test_server import KEY, config, join, recv, round_phase, say_hello
from texstage.publish import find_bundles, pack
from texstage.server.app import create_app
from texstage.server.lecturers import Lecturers

HOST = {"X-Texquiz-Key": KEY}


def lectures(client, deck: str = "test", headers=HOST) -> list[dict]:
    return client.get(f"/api/decks/{deck}/lectures", headers=headers).json()


def test_a_decks_lectures_keep_their_results_ink_and_archive(tmp_path):
    """A deck's lectures - the open game and the ended ones, the newest first - each with what it left.
    An ended one's results, archive ZIP and files are there as an open one's are; its annotated PDF is
    made from its ink (GET .../ink) and kept; another lecturer sees none of it. An ended lecture is
    deleted - its rows in the store and its folder -, an open one is not (the review of 2026-11-14: once a
    game had ended, no window reached any of it)."""
    bob = {"X-Texquiz-Key": Lecturers(tmp_path / "data" / "lecturers.json").add("bob")}
    fb = make_bundle(tmp_path / "bundles", stage=True)
    built = int(os.stat(fb.path / "deck.json").st_mtime * 1000)
    with TestClient(create_app(config(tmp_path))) as client, client.websocket_connect("/ws") as st:
        first = say_hello(st, fb, role="stage")
        with client.websocket_connect("/ws") as phone:
            join(phone, first["pin"], "Ada")
            st.send_json({"t": "slide", "slide": fb.slide("question", "pick"), "id": 2})
            state = recv(phone, "state", until=round_phase("open"))
            phone.send_json({"t": "answer", "round": state["round"]["id"], "answer": {"choice": "B"}, "id": "a"})
            recv(phone, "ok")
        pen = {"id": "s1", "tool": "pen", "color": "#e21b3c", "width": 0.005, "sim": False}
        st.send_json({"t": "ink.begin", "device": "laptop", "frame": "2", "stroke": pen, "points": [[0.1, 0.1, 0.5]],
                      "id": 3})
        st.send_json({"t": "ink.end", "stroke": "s1", "id": 4})
        recv(st, "ok", until=lambda m: m["re"] == 4)
        st.send_json({"t": "lecture.new", "id": 5})              # a new presentation: the first ends, its ink kept
        second = recv(st, "ok", until=lambda m: m["re"] == 5)
        game = first["session"]
        listed = lectures(client)
        assert [(x["pin"], x["ended"] is None) for x in listed] == [(second["pin"], True), (first["pin"], False)]
        now, ended = listed
        assert now["running"] is True and now["players"] == 0
        assert (ended["players"], ended["asked"], ended["frames"], ended["built"], ended["pdf"]) == (1, 1, 1, built, True)
        results = f"test-{time.strftime('%Y-%m-%d', time.localtime(ended['created'] / 1000))}-{first['pin']}.csv"
        assert [f["name"] for f in ended["files"]] == [results]                     # (written when it ended)
        assert lectures(client, headers=bob) == []
        csv = client.get(f"/api/results/{game}.csv", headers=HOST)
        assert csv.status_code == 200 and "Ada" in csv.text
        assert client.get(f"/api/results/{game}.csv", headers=bob).status_code == 404
        ink = client.get(f"/api/archive/{game}/ink", headers=HOST).json()
        assert ink["bundle"] == fb.id and [s["id"] for s in ink["frames"]["2"]] == ["s1"] and ink["boards"] == []
        kept = client.put(f"/api/archive/{game}/annotated.pdf", content=b"%PDF-1.7 ink", headers=HOST).json()
        assert kept["folder"].endswith(f"-{first['pin']}") and "annotated.pdf" in kept["files"]
        z = client.get(f"/api/archive/{game}.zip", headers=HOST)
        assert sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == sorted(["annotated.pdf", results])
        folder = tmp_path / "data" / kept["folder"]
        (folder / results).unlink()                       # a lecture that ended before games left their archive:
        assert "Ada" in client.get(f"/api/results/{game}.csv", headers=HOST).text   # counted from the store
        assert client.delete(f"/api/archive/{second['session']}", headers=HOST).status_code == 409   # still open
        assert client.delete(f"/api/archive/{game}", headers=bob).status_code == 404
        assert client.delete(f"/api/archive/{game}", headers=HOST).json() == {"deleted": game}
        assert [x["pin"] for x in lectures(client)] == [second["pin"]] and not folder.exists()
        assert client.get(f"/api/results/{game}.csv", headers=HOST).status_code == 404
    db = sqlite3.connect(tmp_path / "data" / "texquiz.sqlite3")
    left = [db.execute(f"SELECT COUNT(*) FROM {table} WHERE session = ?", (game,)).fetchone()[0]
            for table in ("players", "rounds", "strokes")]
    assert left == [0, 0, 0] and db.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (game,)).fetchone()[0] == 0
    db.close()


def test_a_decks_builds_are_presented_downloaded_and_an_upload_deleted(tmp_path):
    """Every build of a deck on disk, the newest first, each with where it is from and its game. The oldest
    is presented (a rollback: the hello the deck page's Present of a build says), downloaded as one file
    that another server takes (Upload a deck), and an upload of the lecturer's deleted - not while a game
    of it runs; a build folder on this computer never."""
    hour_ago = int(time.time()) - 3600
    older = make_bundle(tmp_path / "bundles" / "a", deck="talk", title="Talk", stage=True)
    newer = make_bundle(tmp_path / "bundles" / "b", deck="talk", title="Talk", stage=True, time=30)
    upload = make_bundle(tmp_path / "elsewhere", deck="talk", title="Talk", stage=True, time=45)
    for fb, at in ((older, hour_ago), (newer, hour_ago + 600), (upload, hour_ago + 1200)):
        os.utime(fb.path / "deck.json", (at, at))
    with TestClient(create_app(config(tmp_path))) as client:
        (b,), _ = find_bundles([upload.path])
        assert client.put(f"/api/bundles/{upload.id}", content=pack(b), headers=HOST).status_code == 201
        builds = client.get("/api/decks/talk/builds", headers=HOST).json()
        assert [(x["bundle"], x["source"], x["newest"], x["uploaded"]) for x in builds] == [
            (upload.id, "uploaded", True, True), (newer.id, "folder", False, False), (older.id, "folder", False, False)]
        assert builds[2]["folder"] == str(older.path) and builds[0]["folder"] is None
        assert client.get("/api/decks/talk/builds").status_code == 403
        with client.websocket_connect("/ws") as presenter, client.websocket_connect("/ws") as phone:
            game = say_hello(presenter, older, role="stage", chosen=True)          # the oldest build: a rollback
            join(phone, game["pin"], "Ada")
            played = client.get("/api/decks/talk/builds", headers=HOST).json()[2]["game"]
            assert (played["pin"], played["players"], played["running"]) == (game["pin"], 1, True)
        z = client.get(f"/api/bundles/{older.id}.zip", headers=HOST)
        assert z.status_code == 200 and z.headers["content-disposition"].endswith('.bundle.zip"')
        assert client.get(f"/api/bundles/{older.id}.zip").status_code == 403
        assert client.delete(f"/api/bundles/{newer.id}", headers=HOST).status_code == 400      # a build folder
        with client.websocket_connect("/ws") as presenter:
            say_hello(presenter, upload, role="stage", chosen=True)
            assert client.delete(f"/api/bundles/{upload.id}", headers=HOST).status_code == 409  # its game runs
        engine = client.app.state.server.engine
        for s in engine.sessions.values():
            s.last_active -= engine.settings.stale_ms                                         # an earlier lecture's
        assert client.delete(f"/api/bundles/{upload.id}", headers=HOST).json() == {"deleted": upload.id}
        assert [x["bundle"] for x in client.get("/api/decks/talk/builds", headers=HOST).json()] == [newer.id, older.id]
        assert not (tmp_path / "data" / "bundles" / "local" / "talk").exists()
    other = tmp_path / "other"                                                        # the download, uploaded
    with TestClient(create_app(config(other))) as elsewhere:                          # to another server
        r = elsewhere.post("/api/bundles", content=z.content, headers=HOST)
        assert r.status_code == 201 and r.json()["bundle"] == older.id and r.json()["new"] is True


def test_the_lectures_are_listed_however_many_empty_games_came_after(tmp_path):
    """A deck had thousands of ended games that left nothing (two builds' windows ended each other's games,
    until 2026-10): the list held the newest 200 of them, and not one lecture (the 2026-11 review: B1). A game
    that left only files in the archive - a recording - is a lecture all the same."""
    from types import SimpleNamespace

    from texstage.server import archive
    fb = make_bundle(tmp_path / "bundles", stage=True)
    with TestClient(create_app(config(tmp_path))) as client, client.websocket_connect("/ws") as st:
        first = say_hello(st, fb, role="stage")
        with client.websocket_connect("/ws") as phone:
            join(phone, first["pin"], "Ada")                                  # a lecture: its player
        st.send_json({"t": "lecture.new", "id": 2})
        second = recv(st, "ok", until=lambda m: m["re"] == 2)
        st.send_json({"t": "lecture.new", "id": 3})
        third = recv(st, "ok", until=lambda m: m["re"] == 3)
        db = sqlite3.connect(tmp_path / "data" / "texquiz.sqlite3")
        db.row_factory = sqlite3.Row
        row = dict(db.execute("SELECT * FROM sessions WHERE id = ?", (second["session"],)).fetchone())
        place = archive.folder(tmp_path / "data", SimpleNamespace(deck=fb.deck, created=row["created"], pin=row["pin"]))
        (place / "recording-0123456789ab.webm").write_bytes(b"a recording")                   # ... and one with a recording alone
        for i in range(250):                                                   # 250 empty ones after them
            empty = {**row, "id": f"empty{i:04d}", "pin": f"{100000 + i}", "created": row["created"] + 1000 * (i + 1),
                     "ended": row["ended"] + 1000 * (i + 1), "stage": "{}", "polls": "{}"}
            db.execute(f"INSERT INTO sessions ({', '.join(empty)}) VALUES ({', '.join('?' * len(empty))})",
                       list(empty.values()))
        db.commit()
        db.close()
        listed = lectures(client)
        assert [x["pin"] for x in listed] == [third["pin"], second["pin"], first["pin"]]
        assert listed[2]["players"] == 1 and [f["name"] for f in listed[1]["files"]] == ["recording-0123456789ab.webm"]


def test_a_builds_changes_since_the_build_before(tmp_path):
    """Builds told two builds apart by their time alone (the deck page's suggestion 7): each build now says what
    changed since the build before it - its slides by their pictures (content-addressed: the same picture is the
    same slide), added, removed or changed; its quizzes, activities, videos by ID, added, removed or changed (a
    definition or a key: a right answer)."""
    import copy

    from texstage.server.bundles import changes, load_bundle
    older = make_bundle(tmp_path / "bundles" / "a", deck="talk", title="Talk", stage=True)
    newer = make_bundle(tmp_path / "bundles" / "b", deck="talk", title="Talk", stage=True, time=30)   # quizzes' time
    now = int(time.time())
    for fb, at in ((older, now - 600), (newer, now)):
        os.utime(fb.path / "deck.json", (at, at))
    a, b = load_bundle(older.path), load_bundle(newer.path)
    quizzes = len(b.quizzes)
    assert changes(b, a) == {"slides": {"added": 0, "removed": 0, "changed": 0},
                             "items": {"quiz": {"added": 0, "removed": 0, "changed": quizzes}}}
    assert changes(a, a) == {"slides": {"added": 0, "removed": 0, "changed": 0}, "items": {}}
    c = copy.deepcopy(b)
    slides = c.deck_json["slides"]
    slides[0] = {**slides[0], "image": "slides/" + "0" * 16 + ".png"}            # a picture changed in place
    c.deck_json["slides"] = slides + [{"image": "slides/" + "1" * 16 + ".png"}]   # one added at the end
    first = sorted(c.items["quiz"])[0]
    c.items = {**c.items, "quiz": {k: v for k, v in c.items["quiz"].items() if k != first}}   # a quiz removed
    c.keys = copy.deepcopy(c.keys)
    assert changes(c, b) == {"slides": {"added": 1, "removed": 0, "changed": 1},
                             "items": {"quiz": {"added": 0, "removed": 1, "changed": 0}}}
    d = copy.deepcopy(b)
    d.deck_json["slides"] = d.deck_json["slides"][1:]                            # the first slide gone
    keys = (d.keys.get("items") or {}).get("quiz") or d.keys["quizzes"]          # (format 1's keys: quizzes)
    second = sorted(keys)[0]
    keys[second] = {**keys[second], "_": "another"}                            # only its right answer changed
    assert changes(d, b)["items"] == {"quiz": {"added": 0, "removed": 0, "changed": 1}}
    assert changes(d, b)["slides"] == {"added": 0, "removed": 1, "changed": 0}
    with TestClient(create_app(config(tmp_path))) as client:
        builds = client.get("/api/decks/talk/builds", headers=HOST).json()
        assert [x["bundle"] for x in builds] == [newer.id, older.id]
        assert builds[0]["changes"] == {"slides": {"added": 0, "removed": 0, "changed": 0},
                                        "items": {"quiz": {"added": 0, "removed": 0, "changed": quizzes}}}
        assert builds[1]["changes"] is None                                     # (the oldest: none before it)


def test_end_lecture_ends_the_game_writes_its_archive_and_frees_its_upload(tmp_path):
    """End lecture (the deck page's suggestion 8): a game left open ended only by itself - the next lecture, a new
    build, hours idle -, and an upload of its deck could not be deleted for six hours after it. Now the lecturer
    ends it: what it left goes to the archive, the phones are told it is over, its PIN is free, and the upload
    can be deleted at once. Not another lecturer's game, nor one whose recording is still being made."""
    from texstage.server.archive import Take
    bob = {"X-Texquiz-Key": Lecturers(tmp_path / "data" / "lecturers.json").add("bob")}
    fb = make_bundle(tmp_path / "elsewhere", deck="talk", title="Talk", stage=True)
    (b,), _ = find_bundles([fb.path])
    with TestClient(create_app(config(tmp_path))) as client:
        assert client.put(f"/api/bundles/{fb.id}", content=pack(b), headers=HOST).status_code == 201   # an upload
        with client.websocket_connect("/ws") as st, client.websocket_connect("/ws") as phone:
            game = say_hello(st, fb, role="stage")
            join(phone, game["pin"], "Ada")
            assert client.delete("/api/decks/talk", headers=HOST).status_code == 409          # (its game is open)
            end = f"/api/decks/talk/lectures/{game['session']}/end"
            assert client.post(end).status_code == 403
            assert client.post(end, headers=bob).status_code == 404                           # not bob's game
            assert client.post("/api/decks/talk/lectures/nosuchgame/end", headers=HOST).status_code == 404
            server = client.app.state.server
            folder = tmp_path / "data" / "archive"
            from texstage.server import archive
            place = archive.folder(tmp_path / "data", server.engine.sessions[game["session"]], make=True)
            server.recordings.takes["t1"] = Take("t1", "local", "webm", 0, folder=place)     # a recording runs
            assert client.post(end, headers=HOST).status_code == 409
            server.recordings.takes["t1"].finished = 1                                        # ... and is done
            assert client.post(end, headers=HOST).json() == {"ended": game["session"]}
            bye = recv(phone, "bye")
            assert bye["reason"] == "no-session"
            del server.recordings.takes["t1"]
        (lecture,) = lectures(client, "talk")
        assert lecture["ended"] is not None and lecture["players"] == 1
        assert any(f["name"].endswith(".csv") for f in lecture["files"]), "its results: in the archive"
        assert client.post(end, headers=HOST).status_code == 404                              # (ended already)
        assert game["pin"] in server.engine.ended                                             # its PIN: free again
        assert client.delete("/api/decks/talk", headers=HOST).status_code == 200              # the upload: at once
        assert folder.exists()


def test_continue_takes_up_an_older_lecture_not_only_the_last(tmp_path):
    """Lectures › Continue (the deck page's suggestion 8): the Present question offered only the last lecture's ink;
    any earlier lecture of the build goes on now - its ink copied into the game (lecture.continue), the lecture
    in between left as it is."""
    fb = make_bundle(tmp_path / "bundles", stage=True)
    pen = {"tool": "pen", "color": "#e21b3c", "width": 0.005, "sim": False}
    with TestClient(create_app(config(tmp_path))) as client, client.websocket_connect("/ws") as st:
        first = say_hello(st, fb, role="stage")

        def ink(stroke: str, frame: str, mid: int):
            st.send_json({"t": "ink.begin", "device": "laptop", "frame": frame, "stroke": {"id": stroke, **pen},
                          "points": [[0.1, 0.1, 0.5]], "id": mid})
            st.send_json({"t": "ink.end", "stroke": stroke, "id": mid + 1})
            recv(st, "ok", until=lambda m: m["re"] == mid + 1)
        ink("s1", "2", 10)                                                 # the first lecture: ink on frame 2
        st.send_json({"t": "lecture.new", "id": 20})
        recv(st, "ok", until=lambda m: m["re"] == 20)
        ink("s2", "3", 30)                                                 # the second: ink on frame 3
        st.send_json({"t": "lecture.new", "id": 40})
        recv(st, "ok", until=lambda m: m["re"] == 40)                      # the third: none yet
        st.send_json({"t": "lecture.continue", "game": first["session"], "id": 50})
        assert recv(st, "ok", until=lambda m: m["re"] == 50)["frames"] == 1     # the first's: its frame
        st.send_json({"t": "lecture.continue", "game": first["session"], "id": 51})
        assert recv(st, "error", until=lambda m: m["re"] == 51)["error"] == "has-ink"   # (once)

