# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Presenter keys (docs/design.md, section 5.3): a server's own key lives in its data folder
(presenter-key, made on the first start); a live deck carries the key of its server, so its
slides pair by themselves; keys of servers elsewhere are given (--key, TEXSTAGE_KEY - or
TEXQUIZ_KEY, its name until 2026-10-10) or remembered in servers.json in the data folder."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from texstage import DEFAULT_DATA

DATA = DEFAULT_DATA
SERVERS = DATA / "servers.json"
LOCAL = {"localhost", "127.0.0.1", "::1"}


def env_key() -> str | None:
    """The presenter key given in the environment: TEXSTAGE_KEY, or TEXQUIZ_KEY (until 2026-10-10)."""
    return os.environ.get("TEXSTAGE_KEY") or os.environ.get("TEXQUIZ_KEY") or None


def load_presenter_key(data_dir: Path) -> str:
    """The key of the server with this data folder, made on first use."""
    path = data_dir / "presenter-key"
    if not path.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(18) + "\n", encoding="ascii")
    return path.read_text(encoding="ascii").strip()


def remembered_keys(path: Path = SERVERS) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def remember_key(url: str, key: str, path: Path = SERVERS):
    keys = remembered_keys(path)
    keys[url] = key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")


def find_key(url: str, key: str | None = None, path: Path = SERVERS, data_dir: Path = DATA) -> str | None:
    """The presenter key for this server: given, else TEXSTAGE_KEY (or TEXQUIZ_KEY), else
    remembered, else - for a server on this machine - the one in the data folder. None: unknown."""
    key = key or env_key() or remembered_keys(path).get(url.rstrip("/"))
    if key:
        return key
    if (urlsplit(url).hostname or "") in LOCAL:
        return load_presenter_key(data_dir)
    return None
