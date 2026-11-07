# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Verified resources, served from an immutable byte snapshot, never deck code."""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import PluginError
from .manifest import resource_path

MIME = {".mjs": "text/javascript", ".js": "text/javascript", ".css": "text/css",
        ".wasm": "application/wasm", ".json": "application/json", ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".woff2": "font/woff2",
        ".txt": "text/plain"}
MAX_RESOURCE = 32 * 1024 * 1024
MAX_PACKAGE = 64 * 1024 * 1024


def verified_file(root: Path, name: str, sha256: str, size: int) -> bytes:
    name = resource_path(name)
    path = root / name
    if not 0 <= size <= MAX_RESOURCE:
        raise PluginError(f"resource exceeds package policy: {name}")
    cursor = root
    for part in name.split("/"):
        cursor = cursor / part
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise PluginError(f"linked plugin resource: {name}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise PluginError(f"resource escapes its distribution: {name}")
    try:
        if path.stat().st_size != size:
            raise PluginError(f"resource size changed: {name}")
        raw = path.read_bytes()
    except OSError as exc:
        raise PluginError(f"cannot read declared resource: {name}") from exc
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise PluginError(f"resource digest changed: {name}")
    return raw


def public_asset(name: str) -> str:
    suffix = Path(resource_path(name)).suffix.lower()
    if suffix not in MIME:
        raise PluginError(f"resource is not browser-servable: {name}")
    return MIME[suffix]
