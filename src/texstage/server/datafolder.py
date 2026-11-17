# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What a data folder holds per deck, and cleaning it by hand (the deck management review of 2026-11-14,
item 9; the lecturer's choice of 2026-11-17: by hand only). Nothing here is deleted by itself - as before, only
a deck's builds beyond the newest ten (uploads, copies kept for games: app.py, prune) go without being asked.

Per deck: its uploads (bundles/<lecturer>/<deck>/<id>/), the copies kept for its games (served/<deck>/<id>/),
its lectures - the games in the store that left something (store.py: LEFT, the deck page's Lectures' rule) or a
folder in the archive - and their archive folders (archive/<deck>/<day>-<pin>/), the recordings among their
files. `texstage data` shows it, the deck page's Storage too (GET /api/storage: a lecturer's own);
`texstage data clean --before DATE` removes, as asked: ended lectures (their rows in the store and their
archive folders, as the deck page's Lectures › Delete does), recordings alone, or copies - never an open game,
a copy an open game plays, nor a folder whose recording is still being made (a part came within a day). It
lists what would go and what it leaves and why, and deletes only when told (--yes): each folder or file moved
aside first, whole - a file held open keeps it where it is, and its rows in the store with it.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from texstage.server import archive
from texstage.server.bundles import built_time
from texstage.server.store import LEFT

STORE = "texquiz.sqlite3"
DAY_PIN = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d+)$")
MEDIA = re.compile(r"^recording-([0-9a-f]{12})\.(?:webm|mp4)(\.part)?$")   # a recording (.part: not finished)
TAKE = re.compile(r"^recording-([0-9a-f]{12})\.json$")                     # what the server knows of it
QUIET_S = 86_400                    # a recording no part of which came for a day is abandoned, not being made


def size_of(path: Path) -> tuple[int, int]:
    """(files, bytes) of a folder and everything in it - 0, 0 where it is not."""
    files = total = 0
    for top, _, names in os.walk(path):
        for name in names:
            try:
                total += (Path(top) / name).stat().st_size
                files += 1
            except OSError:
                continue
    return files, total


@dataclass
class Deck:
    deck: str
    uploads: int = 0
    uploads_bytes: int = 0
    copies: int = 0
    copies_bytes: int = 0
    lectures: int = 0
    archive_bytes: int = 0                 # the archive's files but its recordings
    recordings: int = 0
    recordings_bytes: int = 0

    @property
    def total(self) -> int:
        return self.uploads_bytes + self.copies_bytes + self.archive_bytes + self.recordings_bytes

    def view(self) -> dict:
        return {"deck": self.deck, "uploads": self.uploads, "uploadsBytes": self.uploads_bytes, "copies": self.copies,
                "copiesBytes": self.copies_bytes, "lectures": self.lectures, "archiveBytes": self.archive_bytes,
                "recordings": self.recordings, "recordingsBytes": self.recordings_bytes, "total": self.total}


def _games(data_dir: Path, owner: str | None = None) -> list[dict]:
    """The store's games (read only): id, deck, owner, pin, bundle, created, ended, and whether it left something
    (store.py: LEFT) - a lecturer's alone with owner; none without a store."""
    path = data_dir / STORE
    if not path.is_file():
        return []
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    where, params = (" WHERE COALESCE(owner, '') = ?", (owner,)) if owner is not None else ("", ())
    try:
        try:
            rows = db.execute(f"SELECT id, deck, owner, pin, bundle, created, ended, ({LEFT}) AS left_something "
                              f"FROM sessions s{where}", params).fetchall()
        except sqlite3.OperationalError:                # (a store without some of those tables: every game counts)
            rows = db.execute(f"SELECT id, deck, owner, pin, bundle, created, ended, 1 AS left_something "
                              f"FROM sessions s{where}", params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        db.close()


def _place(data_dir: Path, g: dict) -> Path | None:
    """A game's folder in the archive (archive.folder), whether it is there or not."""
    if g["created"] is None:
        return None
    return archive.folder(data_dir, SimpleNamespace(deck=g["deck"], created=g["created"], pin=g["pin"]), make=False)


def _archived(deck_dir: Path, pins: set[str] | None, d: Deck):
    """A deck's archive folders counted into d - only those of these PINs, where given (a lecturer's)."""
    for game in sorted(deck_dir.iterdir()) if deck_dir.is_dir() else []:
        m = DAY_PIN.match(game.name)
        if not m or not game.is_dir() or (pins is not None and m.group(2) not in pins):
            continue
        for p in game.iterdir():
            try:
                size = p.stat().st_size if p.is_file() else 0
            except OSError:
                continue
            if MEDIA.match(p.name):
                d.recordings += 1
                d.recordings_bytes += size
            elif TAKE.match(p.name):
                d.recordings_bytes += size
            else:
                d.archive_bytes += size


def overview(data_dir: Path, owner: str | None = None) -> list[Deck]:
    """Every deck's share of the data folder, the largest first - a lecturer's alone with owner (their uploads,
    the copies of decks they have games of, their games' archive folders)."""
    data_dir = Path(data_dir)
    games = _games(data_dir, owner)
    decks: dict[str, Deck] = {}

    def of(deck: str) -> Deck:
        return decks.setdefault(deck, Deck(deck))
    archived: dict[str, set[str]] = {}
    for g in games:
        if g["deck"] and g["ended"] is not None:
            pins = archived.setdefault(g["deck"], archive.pins(data_dir, g["deck"]))
            if g["left_something"] or str(g["pin"]) in pins:                 # (a recording alone: a lecture too)
                of(g["deck"]).lectures += 1
    lecturers = [data_dir / "bundles" / owner] if owner is not None else \
        [p for p in (data_dir / "bundles").iterdir() if p.is_dir()] if (data_dir / "bundles").is_dir() else []
    for lect in lecturers:
        for deck in lect.iterdir() if lect.is_dir() else []:
            for build in deck.iterdir() if deck.is_dir() else []:
                if (build / "deck.json").is_file():
                    d = of(deck.name)
                    d.uploads += 1
                    d.uploads_bytes += size_of(build)[1]
    mine = {g["deck"] for g in games} if owner is not None else None
    served = data_dir / "served"
    for deck in served.iterdir() if served.is_dir() else []:
        if mine is not None and deck.name not in mine:
            continue
        for build in deck.iterdir() if deck.is_dir() else []:
            if (build / "deck.json").is_file():
                d = of(deck.name)
                d.copies += 1
                d.copies_bytes += size_of(build)[1]
    pins: dict[str, set[str]] = {}
    for g in games:
        pins.setdefault(g["deck"], set()).add(str(g["pin"]))
    for name in {*decks, *(g["deck"] for g in games if g["deck"])}:
        _archived(archive.deck_folder(data_dir, name), pins.get(name, set()) if owner is not None else None, of(name))
    if owner is None:                                    # archive folders of decks with no game in the store
        root = data_dir / "archive"
        for deck_dir in root.iterdir() if root.is_dir() else []:
            if deck_dir.is_dir() and not any(archive.deck_folder(data_dir, n) == deck_dir for n in decks):
                _archived(deck_dir, None, of(deck_dir.name))
    return sorted((d for d in decks.values() if d.total or d.lectures), key=lambda d: (-d.total, d.deck))


@dataclass
class Gone:
    """Something cleaning removes (or would remove) - or leaves, and why (kind held): what, of which deck, how
    large."""
    kind: str                       # lecture, empty (games that left nothing), recording, copy - held: left
    deck: str
    what: str                       # the lecture's day, PIN and lecturer, the recording's file, the copy's build
    bytes: int = 0
    path: Path | None = field(default=None, repr=False)
    games: list[str] = field(default_factory=list, repr=False)       # its games in the store (rows to delete)
    also: list[Path] = field(default_factory=list, repr=False)       # files that go with it (a recording's .json)


def _being_made(place: Path, now: float) -> float | None:
    """When a recording in this folder last got a part, if one is still being made: a .part file, written to
    within QUIET_S. A .part quiet longer than that was abandoned (a browser that crashed): None."""
    latest = None
    for p in place.iterdir() if place.is_dir() else []:
        m = MEDIA.match(p.name)
        if m and m.group(2):
            try:
                t = max(p.stat().st_mtime, (place / f"recording-{m.group(1)}.json").stat().st_mtime
                        if (place / f"recording-{m.group(1)}.json").exists() else 0)
            except OSError:
                continue
            if now - t < QUIET_S:
                latest = max(latest or 0, t)
    return latest


def plan(data_dir: Path, before_ms: int, *, lectures: bool = False, recordings: bool = False, copies: bool = False,
         deck: str | None = None) -> list[Gone]:
    """What cleaning would remove: lectures that ended before the time (with their archive folders), the
    recordings of lectures that ended before it, copies kept for games (served/) built before it that no open
    game plays - of one deck, where given. A lecture whose recording is still being made is left, and said so
    (kind held); so is everything of an open game, without a word."""
    data_dir = Path(data_dir)
    games = _games(data_dir)
    open_bundles = {g["bundle"] for g in games if g["ended"] is None}
    out: list[Gone] = []
    empty: dict[str, list[str]] = {}                  # per deck the ended games that left nothing, not even a file
    now = time.time()
    for g in games:
        if g["ended"] is None or g["ended"] >= before_ms or (deck is not None and g["deck"] != deck) or not g["deck"]:
            continue
        if not (lectures or recordings):
            continue
        place = _place(data_dir, g)
        held = archive.files(place) if place is not None and place.is_dir() else []
        day = time.strftime("%Y-%m-%d", time.localtime(g["ended"] / 1000))      # (the day it ended: --before's)
        who = g["owner"] or "-"
        what = f"ended {day}, PIN {g['pin']}, lecturer {who}"
        busy = _being_made(place, now) if place is not None else None
        if busy is not None:
            out.append(Gone("held", g["deck"], f"{what}: a recording of it is still being made (a part at "
                                               f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(busy))})"))
            continue
        if lectures:
            if not g["left_something"] and not held:
                empty.setdefault(g["deck"], []).append(g["id"])
            else:
                out.append(Gone("lecture", g["deck"], what, size_of(place)[1] if place else 0,
                                place if place is not None and place.is_dir() else None, [g["id"]]))
        elif recordings and place is not None and place.is_dir():
            for p in sorted(place.iterdir()):
                m = MEDIA.match(p.name)
                if m and p.is_file():
                    take = place / f"recording-{m.group(1)}.json"
                    out.append(Gone("recording", g["deck"], f"{what}: {p.name}", p.stat().st_size, p,
                                    also=[take] if take.exists() else []))
    for name, ids in sorted(empty.items()):
        out.append(Gone("empty", name, f"{len(ids)} {'game' if len(ids) == 1 else 'games'} that left nothing", 0,
                        None, ids))
    if copies:
        served = data_dir / "served"
        for deck_dir in sorted(served.iterdir()) if served.is_dir() else []:
            if deck is not None and deck_dir.name != deck:
                continue
            for build in sorted(deck_dir.iterdir()) if deck_dir.is_dir() else []:
                if not (build / "deck.json").is_file() or build.name in open_bundles:
                    continue
                made = built_time(build) or int((build / "deck.json").stat().st_mtime * 1000)
                if made < before_ms:
                    out.append(Gone("copy", deck_dir.name, build.name, size_of(build)[1], build))
    return out


def clean(data_dir: Path, gone: list[Gone]) -> tuple[int, list[str]]:
    """Removes what plan() found (not what it holds back): each folder or file moved aside first, whole - one
    held open (a player, a backup, Windows) is refused as a whole and stays, with its rows in the store -, then
    the rows of what went (every table, as the deck page's Lectures › Delete), then what was moved aside. The
    bytes freed, and what could not go and why."""
    from texstage.server.store import Store
    data_dir = Path(data_dir)
    aside = data_dir / "incoming" / f"trash-{secrets.token_hex(6)}"
    aside.mkdir(parents=True, exist_ok=True)
    freed, failed, rows = 0, [], []
    for i, g in enumerate(gone):
        if g.kind == "held":
            continue
        paths = [p for p in ([g.path] if g.path is not None else []) + g.also if p.exists()]
        try:
            for j, p in enumerate(paths):
                os.replace(p, aside / f"{i}-{j}-{p.name}")
        except OSError as err:
            failed.append(f"{g.deck}, {g.what}: {err.strerror or err}")
            continue
        rows += g.games
        freed += g.bytes
        if g.kind == "lecture" and g.path is not None:
            try:
                g.path.parent.rmdir()                    # (the deck's folder of the archive, now empty)
            except OSError:
                pass
    if rows and (data_dir / STORE).is_file():
        store = Store(data_dir / STORE)
        try:
            for game in rows:
                store.delete_session(game)
        finally:
            store.db.close()
    for old in (data_dir / "incoming").glob("trash-*"):  # (and what an earlier cleaning could not remove)
        shutil.rmtree(old, ignore_errors=True)
    if aside.exists():
        failed.append(f"{aside}: some of it is still held open - removed by the next cleaning")
    return freed, failed
