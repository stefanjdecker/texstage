# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A code activity on the phone (web/play/activity.js), in Node: its words engine by engine - a
Turtle text is valid, its graph the reference's; a query's words unchanged - and the token bar's
insertion at the cursor."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_phones_words_and_token_bar():
    script = Path(__file__).with_name("web-activity-phone.test.mjs")
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
