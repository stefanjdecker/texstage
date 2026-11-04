# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The live views in the deck's language (web/shared/live.js, web/stage/activity.js), in Node: a
German deck's quiz views and activity box in German, through the Stage of the presenter and
projector windows; an English deck's - and one built before deck.json named its language - as
they were; the presenter window's activity panel in English."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_live_views_speak_the_decks_language():
    script = Path(__file__).with_name("web-live-language.test.mjs")
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
