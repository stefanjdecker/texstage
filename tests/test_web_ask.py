# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The presenter's dialogs on top of each other: only the top one takes the keys (stage/ask.js)."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_browser_dialogs():
    script = Path(__file__).with_name("web-ask.test.mjs")
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
