# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A kind's own files for the browser (docs/architecture/activity-framework-design.md, 7.3 and 7.4; the
plan of F2, 4.5): what a phone loads of a kind - its modules for the phones (web/hint.js, web/input.js),
what they import from beside them, its texts (texts/<language>.js) - and what the windows load besides,
web/box.js and its imports (activities/kit.py: phone_files, window_files). They are served under

    /kinds/<hash>/<path>

the hash that of the files and their contents: cached long, never stale - a kind installed from source
changes without a new version, and its hash with it. The kinds of one package share their folder, so
their files and their hash: a phone fetches a file they share once. Each file is gzip-compressed once,
when the server starts. A page learns the deck's kinds from its welcome or the deck's view (app.py:
kindFiles) and loads their files in the background (web/kinds.js) - not in the second a step opens on
1,000 phones."""
from __future__ import annotations

import gzip
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from texstage.activities import kit, registry

log = logging.getLogger("texstage.server")

MEDIA = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json"}
assert set(MEDIA) == set(kit.SERVED), "the server serves what the kit counts"


@dataclass
class KindFiles:
    """The files of a kind's folder - shared by the kinds of its package: by their path in it, each as it is
    and compressed."""
    hash: str = ""
    phone: list[str] = field(default_factory=list)       # what a phone loads, in this order
    window: list[str] = field(default_factory=list)      # what the windows load besides
    files: dict[str, tuple[bytes, bytes, str]] = field(default_factory=dict)    # path -> (as it is, gzip, media type)

    def entry(self) -> dict:
        """What a page is told of a kind (its welcome, the deck's view)."""
        return {"hash": self.hash, "phone": self.phone, "window": self.window}


def of(kind) -> KindFiles:
    """A kind's files, read and compressed, and their hash: of their paths and contents alone."""
    home = kit._lexical(kit.home_of(kind))
    out = KindFiles()
    digest = hashlib.sha256()
    for side, paths in (("phone", kit.phone_files(kind)), ("window", kit.window_files(kind))):
        for path in paths:
            rel = path.relative_to(home).as_posix()
            if rel in out.files:
                continue
            data = path.read_bytes()
            out.files[rel] = (data, gzip.compress(data, 9), MEDIA[path.suffix.lower()])
            getattr(out, side).append(rel)
            digest.update(side.encode() + b"\0" + rel.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    out.hash = digest.hexdigest()[:20]
    return out


class Kinds:
    """Every installed kind's files, read once (the server starts; reload() reads them anew)."""

    def __init__(self):
        self.by_name: dict[str, KindFiles] = {}
        self.by_hash: dict[str, KindFiles] = {}
        self.reload()

    def reload(self) -> None:
        by_name, by_home = {}, {}
        for name, kind in registry.kinds().items():
            try:
                home = kit.home_of(kind)
                if home not in by_home:                  # (the kinds of a package: their folder's files, once)
                    by_home[home] = of(kind)
                by_name[name] = by_home[home]
            except (OSError, TypeError, ValueError) as e:     # a file that went, a class of no file: none to give
                log.warning("the kind %s has no files for the browser: %s", name, e)
                by_name[name] = KindFiles()
        self.by_name = by_name
        self.by_hash = {k.hash: k for k in by_home.values()}

    def deck(self, items: dict) -> dict:
        """What a page is told of a deck's kinds: {name: {hash, phone, window}} - the kinds its activities name,
        or name through the keys of before kinds were named."""
        from texstage.activities.play import kind_of
        out = {}
        for item in (items or {}).values():
            try:
                name = kind_of(item).NAME
            except LookupError:                          # (the server refuses or fails the activity: its problems)
                continue
            if name in self.by_name:
                out[name] = self.by_name[name].entry()
        return out

    def file(self, digest: str, path: str) -> tuple[bytes, bytes, str] | None:
        k = self.by_hash.get(digest)
        return k.files.get(path) if k is not None else None
