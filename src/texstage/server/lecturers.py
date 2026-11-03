# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The lecturers of a quiz server and their presenter keys (docs/design.md, section 5.3).

Every lecturer has a key of their own; a host connection or request is the lecturer whose
key it brings, and sees only that lecturer's decks, games and results. The server keeps
only the keys' hashes:

    <data>/lecturers.json     {"<name>": {"key": "<sha256 of the key>"}, ...}

changed with `texstage lecturer add | renew | remove | list` (on the server's machine; a
running server picks the changes up). The server's own key (<data>/presenter-key, the
laptop's - texstage serve) is one more lecturer, named when the server starts.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path

NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")


class LecturerError(ValueError):
    pass


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def valid_name(name: str) -> str:
    name = name.strip().lower()
    if not NAME.match(name):
        raise LecturerError(f"{name!r}: a lecturer's name has lowercase letters, digits, '.', '_' or '-' "
                            f"(at most 40)")
    return name


class Lecturers:
    def __init__(self, path: Path, own: dict[str, str] | None = None):
        """own: lecturers by name and plain key that are not in the file (the server's own)."""
        self.path = path
        self.own = {valid_name(n): key_hash(k) for n, k in (own or {}).items()}
        self._file: dict[str, str] = {}
        self._stamp = None

    def _read(self) -> dict[str, str]:
        try:
            state = self.path.stat()
            # Atomic replacements can share a timestamp, especially on Windows.
            stamp = (state.st_mtime_ns, state.st_size, state.st_ino)
        except FileNotFoundError:
            self._file, self._stamp = {}, None
            return self._file
        if stamp != self._stamp:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._file = {n: v["key"] for n, v in data.items() if isinstance(v, dict) and "key" in v}
            except (OSError, ValueError):
                pass                                  # keep the last good list
            self._stamp = stamp
        return self._file

    def _write(self, entries: dict[str, str]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({n: {"key": h} for n, h in sorted(entries.items())}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(self.path)
        self._stamp = None

    def who(self, key) -> str | None:
        """The lecturer whose key this is (None: nobody's)."""
        if not isinstance(key, str) or not key:
            return None
        h = key_hash(key)
        found = None
        for name, kh in (*self.own.items(), *self._read().items()):
            if secrets.compare_digest(h, kh):
                found = name                          # no early exit: the same time for every key
        return found

    def names(self) -> list[str]:
        return sorted(set(self.own) | set(self._read()))

    def add(self, name: str) -> str:
        """A new lecturer; returns their key (shown once - only its hash is kept)."""
        name = valid_name(name)
        entries = dict(self._read())
        if name in entries or name in self.own:
            raise LecturerError(f"there is a lecturer {name} already (texstage lecturer renew {name}: a new key)")
        key = secrets.token_urlsafe(18)
        entries[name] = key_hash(key)
        self._write(entries)
        return key

    def renew(self, name: str) -> str:
        """A new key for a lecturer (the old one stops working)."""
        name = valid_name(name)
        entries = dict(self._read())
        if name not in entries:
            raise LecturerError(f"no lecturer {name}")
        key = secrets.token_urlsafe(18)
        entries[name] = key_hash(key)
        self._write(entries)
        return key

    def remove(self, name: str) -> bool:
        name = valid_name(name)
        entries = dict(self._read())
        if entries.pop(name, None) is None:
            return False
        self._write(entries)
        return True
