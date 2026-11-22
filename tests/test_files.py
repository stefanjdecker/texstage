# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A file moved into place, tried again where Windows refuses it (server/files.py): a virus scanner or the
search indexer may still hold a file that was just written. The deck page's save gave up at once, until
the full suite of 2026-11-22 caught it on Windows (test_library, WinError 5 on library.json)."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from texstage.server import files
from texstage.server.library import Library


def test_a_refused_replace_is_tried_again(tmp_path, monkeypatch):
    src, dest = tmp_path / "new.json", tmp_path / "old.json"
    src.write_text("new", encoding="utf-8")
    dest.write_text("old", encoding="utf-8")
    real, calls = Path.replace, []

    def flaky(self, target):
        calls.append(target)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        return real(self, target)
    monkeypatch.setattr(Path, "replace", flaky)
    monkeypatch.setattr(files.time, "sleep", lambda s: None)
    files.replace(src, dest)
    assert dest.read_text(encoding="utf-8") == "new" and not src.exists() and len(calls) == 3

    def refused(self, target):
        raise PermissionError(5, "Access is denied")
    monkeypatch.setattr(Path, "replace", refused)
    with pytest.raises(PermissionError):
        files.replace(dest, src, tries=3)


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses to replace a file another handle holds")
def test_the_deck_page_saves_while_its_file_is_held_for_a_moment(tmp_path):
    """A handle without FILE_SHARE_DELETE - Python's own, as a scanner's - makes Windows refuse to
    replace library.json until it is closed; the save waits for it now."""
    library = Library(tmp_path / "library.json")
    library.add_folder("ada", "Knowledge Graphs")
    held = open(tmp_path / "library.json", encoding="utf-8")
    try:
        threading.Timer(0.2, held.close).start()
        library.add_folder("ada", "Databases")
    finally:
        held.close()
    assert [f["name"] for f in library.folders("ada")] == ["Databases", "Knowledge Graphs"]
