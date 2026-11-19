# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What the presenter window says when the server refuses one of its messages, in Node
(web-texts-presenter.test.mjs): a control or an act the activity framework's core refuses in the core's words
for the lecturer, in the deck's language; anything else as ever, and one dialog for one refusal."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_presenter_window_says_a_refusal_in_the_cores_words():
    script = Path(__file__).with_name("web-texts-presenter.test.mjs")
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
