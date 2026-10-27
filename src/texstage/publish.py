# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage publish: live decks onto a hosted quiz server (docs/design.md, section 8).

    texstage publish <bundles, or folders with bundles> --url https://quiz.example.org [--key K]

finds the bundles as `texstage serve` does (a chapter's build/texquiz/, three levels deep)
and sends each one the server does not have yet as a zip to PUT /api/bundles/<id>. The
server checks it and replaces the deck's previous build. The presenter key: --key, else the
environment variable TEXSTAGE_KEY, else the key remembered for this server in servers.json
in the data folder (--remember stores the given key there).
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from texstage import keys
from texstage.keys import remember_key  # noqa: F401  (texstage publish --remember)
from texstage.server.bundles import Bundle, BundleStore, bundle_files


class PublishError(RuntimeError):
    pass


def find_key(url: str, key: str | None, path: Path = keys.SERVERS) -> str:
    found = keys.find_key(url, key, path)
    if not found:
        raise PublishError(f"no presenter key for {url}: --key (with --remember to keep it), "
                           f"or TEXSTAGE_KEY")
    return found


def find_bundles(paths: list[Path]) -> tuple[list[Bundle], list[str]]:
    """The bundles in these folders (each checked), and what could not be read."""
    store = BundleStore(paths)
    return sorted(store.current(), key=lambda b: (b.deck, str(b.path))), store.problems


def pack(b: Bundle) -> bytes:
    """The bundle as a zip, including the declared local videos and all their posters."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("deck.json", "keys.json"):
            z.write(b.path / name, name, compress_type=zipfile.ZIP_DEFLATED)
        for kind in ("slides", "phone"):
            for p in sorted((b.path / kind).glob("*.png")):
                z.write(p, f"{kind}/{p.name}", compress_type=zipfile.ZIP_STORED)   # PNGs are packed
        stage = b.stage_pdf()
        if stage is not None:
            z.write(stage, f"stage/{stage.name}", compress_type=zipfile.ZIP_DEFLATED)
        for name in sorted(bundle_files(b.deck_json, b.keys)):
            if name.startswith("media/"):
                z.write(b.path / name, name, compress_type=zipfile.ZIP_STORED)   # movies/posters are compressed
    return buf.getvalue()


def call(url: str, key: str, method: str = "GET", data: bytes | None = None):
    headers = {"X-Texquiz-Key": key}
    if data is not None:
        headers["Content-Type"] = "application/zip"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as err:
        try:
            message = json.loads(err.read()).get("error", err.reason)
        except ValueError:
            message = err.reason
        if err.code == 403:
            message = "the server does not accept this presenter key"
        raise PublishError(f"{method} {url}: {err.code} {message}") from None
    except (urllib.error.URLError, OSError) as err:
        raise PublishError(f"{url}: {getattr(err, 'reason', err)}") from None


def publish(bundles: list[Bundle], url: str, key: str, say=print) -> int:
    """Sends the bundles the server does not have; returns how many were sent."""
    url = url.rstrip("/")
    _, decks = call(f"{url}/api/decks", key)
    there = {d["bundle"] for d in decks if d.get("complete", True)}    # a PPTX's upload lacks pictures
    sent = 0
    for b in bundles:
        if b.id in there:
            say(f"{b.deck}: bundle {b.id} is there already")
            continue
        data = pack(b)
        _, info = call(f"{url}/api/bundles/{b.id}", key, "PUT", data)
        say(f"{b.deck}: bundle {b.id} published ({len(data) / 1e6:.1f} MB, {info['quizzes']} quizzes, "
            f"{info['slides']} slides)")
        sent += 1
    return sent
