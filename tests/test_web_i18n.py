# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage's texts (web/i18n), in Node: every language has every text English has, a tag gets
its language or English, a refusal its words, and every refusal the server sends a person has
words in every language (web-i18n.test.mjs)."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_texts_in_every_language():
    script = Path(__file__).with_name("web-i18n.test.mjs")
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
