# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A file or folder moved into place, tried again for a moment where Windows refuses it: a virus
scanner or the search indexer may still hold a file that was just written (WinError 5 or 32).

The server's state files - the deck page's library.json, lecturers.json, devices.json - are
written whole, to a temporary file that then replaces the old one (replace); an uploaded deck's
folder is renamed into place (rename, app.py)."""
from __future__ import annotations

import time
from pathlib import Path

TRIES = 6                                             # 0.05 s to 0.8 s apart: 1.55 s in all


def _tried(move, tries: int):
    for attempt in range(tries):
        try:
            return move()
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.05 * 2 ** attempt)


def rename(src: Path, dest: Path, tries: int = TRIES):
    """src.rename(dest), tried again while Windows refuses it."""
    _tried(lambda: src.rename(dest), tries)


def replace(src: Path, dest: Path, tries: int = TRIES):
    """src.replace(dest) - an existing dest overwritten -, tried again while Windows refuses it."""
    _tried(lambda: src.replace(dest), tries)
