# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The deck page of texstage: each lecturer's folders, the folder and the shown name of each deck,
and the decks taken off the list - in the data folder, one entry per lecturer:

    <data>/library.json   {"<lecturer>": {"folders": {"<id>": {"name": "Knowledge Graphs", "parent": null}},
                                           "decks": {"<deck id>": {"folder": "<id>", "label": "...",
                                                                   "hidden": <ms>}}}}

A deck is kept by its deck ID, so its folder and its name stay when it is built again. "hidden" is
when it was taken off the list: its builds up to then are no longer listed, a newer build is (the
deck page never deletes a laptop's build folder - the next build brings the deck back; an uploaded
deck is deleted by the server, app.py). Folders nest; deleting one moves what it holds up to its
parent. Read on every call, written whole (a temporary file, then a rename), as lecturers.json."""
from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path

NAME_MAX = 80          # a folder's name, characters
LABEL_MAX = 120        # a deck's shown name
FOLDERS_MAX = 500      # per lecturer


class LibraryError(ValueError):
    """A request the library refuses; `missing` for an unknown folder (404 rather than 400)."""

    def __init__(self, message: str, missing: bool = False):
        super().__init__(message)
        self.missing = missing


def _name(value, limit: int, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LibraryError(f"a {what} needs a name")
    text = " ".join(value.split())
    if len(text) > limit:
        raise LibraryError(f"a {what}'s name has at most {limit} characters")
    return text


class Library:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _own(data: dict, lecturer: str) -> dict:
        own = data.setdefault(lecturer, {})
        if not isinstance(own.get("folders"), dict):
            own["folders"] = {}
        if not isinstance(own.get("decks"), dict):
            own["decks"] = {}
        return own

    def view(self, lecturer: str) -> dict:
        """{"folders": {id: {"name", "parent"}}, "decks": {deck: {"folder", "label", "hidden"}}}"""
        own = self._read().get(lecturer)
        if not isinstance(own, dict):
            return {"folders": {}, "decks": {}}
        folders = own.get("folders") if isinstance(own.get("folders"), dict) else {}
        decks = own.get("decks") if isinstance(own.get("decks"), dict) else {}
        return {"folders": folders, "decks": decks}

    def folders(self, lecturer: str) -> list[dict]:
        return [{"id": fid, "name": f.get("name", ""), "parent": f.get("parent")}
                for fid, f in sorted(self.view(lecturer)["folders"].items(), key=lambda kv: kv[1].get("name", "").casefold())]

    # ------------------------------------------------------------ folders
    @staticmethod
    def _check_parent(folders: dict, parent, moving: str | None = None):
        if parent is None:
            return
        if parent not in folders:
            raise LibraryError("no such folder", missing=True)
        node = parent
        while node is not None:                          # not into itself, nor into one of its own
            if node == moving:
                raise LibraryError("a folder cannot go into itself")
            node = folders.get(node, {}).get("parent")

    def add_folder(self, lecturer: str, name, parent=None) -> str:
        with self.lock:
            data = self._read()
            own = self._own(data, lecturer)
            if len(own["folders"]) >= FOLDERS_MAX:
                raise LibraryError(f"at most {FOLDERS_MAX} folders")
            self._check_parent(own["folders"], parent)
            fid = secrets.token_hex(6)
            own["folders"][fid] = {"name": _name(name, NAME_MAX, "folder"), "parent": parent}
            self._write(data)
            return fid

    def change_folder(self, lecturer: str, fid: str, changes: dict):
        """changes: "name" (renames), "parent" (moves; None: to the top)."""
        with self.lock:
            data = self._read()
            own = self._own(data, lecturer)
            folder = own["folders"].get(fid)
            if folder is None:
                raise LibraryError("no such folder", missing=True)
            if "name" in changes:
                folder["name"] = _name(changes["name"], NAME_MAX, "folder")
            if "parent" in changes:
                self._check_parent(own["folders"], changes["parent"], moving=fid)
                folder["parent"] = changes["parent"]
            self._write(data)

    def remove_folder(self, lecturer: str, fid: str):
        """Deletes a folder; its folders and its decks move up to its parent."""
        with self.lock:
            data = self._read()
            own = self._own(data, lecturer)
            folder = own["folders"].pop(fid, None)
            if folder is None:
                raise LibraryError("no such folder", missing=True)
            up = folder.get("parent")
            for f in own["folders"].values():
                if f.get("parent") == fid:
                    f["parent"] = up
            for deck, entry in list(own["decks"].items()):
                if entry.get("folder") == fid:
                    entry["folder"] = up
                    self._tidy(own, deck)
            self._write(data)

    # ------------------------------------------------------------ decks
    def change_deck(self, lecturer: str, deck: str, changes: dict):
        """changes: "folder" (moves it; None: to the top), "label" (its shown name; "" or None: its own)."""
        with self.lock:
            data = self._read()
            own = self._own(data, lecturer)
            entry = own["decks"].setdefault(deck, {})
            if "folder" in changes:
                self._check_parent(own["folders"], changes["folder"])
                entry["folder"] = changes["folder"]
            if "label" in changes:
                label = changes["label"]
                if label is None or (isinstance(label, str) and not label.strip()):
                    entry.pop("label", None)
                else:
                    entry["label"] = _name(label, LABEL_MAX, "deck")
            self._tidy(own, deck)
            self._write(data)

    def hide(self, lecturer: str, deck: str, now: int):
        """Takes the deck off the list: its builds up to now."""
        with self.lock:
            data = self._read()
            own = self._own(data, lecturer)
            own["decks"].setdefault(deck, {})["hidden"] = now
            self._write(data)

    def show(self, lecturer: str, deck: str):
        """Lists the deck again (an upload of it: its build may be older than when it was hidden)."""
        with self.lock:
            data = self._read()
            own = data.get(lecturer)
            entry = own.get("decks", {}).get(deck) if isinstance(own, dict) else None
            if not isinstance(entry, dict) or "hidden" not in entry:
                return
            entry.pop("hidden")
            self._tidy(own, deck)
            self._write(data)

    @staticmethod
    def _tidy(own: dict, deck: str):
        entry = own["decks"].get(deck, {})
        for key in ("folder", "label", "hidden"):
            if entry.get(key) is None:
                entry.pop(key, None)
        if not entry:
            own["decks"].pop(deck, None)
