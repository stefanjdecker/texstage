# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Presenter devices (texstage, docs/texstage-design.md, section 5): an iPad or another
computer that runs the presenter window for a lecturer.

A device is paired once from the presenter window on the laptop (the presenter key): it
shows a QR code with a one-time token, valid for two minutes; the device that opens it gets a
short code, which the lecturer allows in the presenter window when it is the one the device
shows - so whoever else sees the QR code (a laptop screen mirrored to the projector) cannot
get in. The device then keeps a token of its own; the server keeps its hash:

    <data>/devices.json   {"<id>": {"owner": "<lecturer>", "name": "iPad · Safari",
                                    "token": "<sha256 of the token>", "paired": <ms>}}

A device is its lecturer's for presenting - decks, games, ink -; it cannot publish, pair
other devices or see the presenter key. The lecturer removes it in the presenter window (or
its entry in the file); its connections end at once.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import unicodedata
from dataclasses import dataclass
from pathlib import Path

PAIR_MS = 120_000            # a pairing code is valid this long
CODE = "ACDEFHJKLMNPQRTUVWXY3479"    # the device's code: no characters that look alike
NAME_MAX = 40


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clean_name(name) -> str:
    """A device's name as it says it (the user agent's gist), printable and short."""
    text = name if isinstance(name, str) else ""
    text = "".join(c for c in unicodedata.normalize("NFC", text) if not unicodedata.category(c).startswith("C"))
    return " ".join(text.split())[:NAME_MAX] or "a device"


@dataclass
class Pairing:
    token: str                   # in the QR code, once
    owner: str
    created: int
    state: str = "waiting"       # waiting claimed approved denied
    claim: str | None = None     # the device's secret while it waits for the lecturer
    code: str = ""               # shown on the device and in the presenter window
    name: str = ""
    device: str | None = None    # the new device's token, handed over once


class Devices:
    def __init__(self, path: Path):
        self.path = path
        self._file: dict[str, dict] = {}
        self._stamp = None
        self.pairings: dict[str, Pairing] = {}
        self.seen: dict[str, int] = {}             # device id -> last request (this run)

    # ------------------------------------------------------------ the paired devices (file)
    def _read(self) -> dict[str, dict]:
        try:
            stamp = self.path.stat().st_mtime_ns
        except FileNotFoundError:
            self._file, self._stamp = {}, None
            return self._file
        if stamp != self._stamp:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._file = {i: d for i, d in data.items()
                              if isinstance(d, dict) and isinstance(d.get("token"), str) and isinstance(d.get("owner"), str)}
            except (OSError, ValueError):
                pass                                  # keep the last good list
            self._stamp = stamp
        return self._file

    def _write(self, entries: dict[str, dict]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        self._stamp = None

    def who(self, token, now: int) -> tuple[str, str] | None:
        """(lecturer, device id) of the device with this token; None: no device's."""
        if not isinstance(token, str) or not token:
            return None
        h = token_hash(token)
        found = None
        for i, d in self._read().items():
            if secrets.compare_digest(h, d["token"]):
                found = (d["owner"], i)               # no early exit: the same time for every token
        if found:
            self.seen[found[1]] = now
        return found

    def list(self, owner: str) -> list[dict]:
        return [{"id": i, "name": d.get("name", ""), "paired": d.get("paired"), "seen": self.seen.get(i)}
                for i, d in sorted(self._read().items(), key=lambda x: x[1].get("paired") or 0) if d["owner"] == owner]

    def remove(self, owner: str, device: str) -> bool:
        entries = dict(self._read())
        if entries.get(device, {}).get("owner") != owner:
            return False
        del entries[device]
        self._write(entries)
        self.seen.pop(device, None)
        return True

    # ------------------------------------------------------------ pairing (memory)
    def offer(self, owner: str, now: int) -> Pairing:
        """A one-time pairing token for the QR code in the lecturer's presenter window."""
        self._expire(now)
        p = Pairing(secrets.token_urlsafe(18), owner, now)
        self.pairings[p.token] = p
        return p

    def status(self, owner: str, token, now: int) -> Pairing | None:
        self._expire(now)
        p = self.pairings.get(token) if isinstance(token, str) else None
        return p if p is not None and p.owner == owner else None

    def claim(self, token, name, now: int) -> Pairing | None:
        """The device opened the QR code: it waits for the lecturer, with a code to compare."""
        self._expire(now)
        p = self.pairings.get(token) if isinstance(token, str) else None
        if p is None or p.state != "waiting":
            return None                               # unknown, used or expired: one device per code
        p.state, p.claim, p.name = "claimed", secrets.token_urlsafe(18), clean_name(name)
        p.code = "".join(secrets.choice(CODE) for _ in range(4))
        return p

    def decide(self, owner: str, token, allow: bool, now: int) -> Pairing | None:
        """The lecturer allows the device (a new device and its token) or does not."""
        p = self.status(owner, token, now)
        if p is None or p.state != "claimed":
            return None
        if allow:
            device = secrets.token_urlsafe(24)
            entries = dict(self._read())
            entries[secrets.token_hex(6)] = {"owner": owner, "name": p.name, "token": token_hash(device), "paired": now}
            self._write(entries)
            p.device = device
        p.state = "approved" if allow else "denied"
        return p

    def wait(self, claim, now: int) -> Pairing | None:
        """The device asks whether it may: its pairing (the token once approved, then gone)."""
        self._expire(now)
        p = next((x for x in self.pairings.values() if isinstance(claim, str) and x.claim is not None
                  and secrets.compare_digest(x.claim, claim)), None)
        if p is not None and p.state in ("approved", "denied"):
            del self.pairings[p.token]                # told once
        return p

    def _expire(self, now: int):
        for token, p in list(self.pairings.items()):
            if now - p.created > PAIR_MS + (60_000 if p.state != "waiting" else 0):
                del self.pairings[token]
