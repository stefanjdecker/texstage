# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The presenter window's start with a stored presenter key, in Node (web-presenter-start.test.cjs):
start() runs after every constant of its module (presenter.js, host.js) - before, a reload with a
stored key forgot it -, and only the server's refusal of the key forgets it."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_a_stored_presenter_key_survives_a_reload():
    script = Path(__file__).with_name("web-presenter-start.test.cjs")
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
