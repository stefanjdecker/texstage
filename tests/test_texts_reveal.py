# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What a live activity's box shows at the reveal and when the lecturer shows a group, in Node
(web-texts-reveal.test.mjs): the reference's card and a shown group's card beside the bars - below them in a
box taller than wide -, both at once, none over the bars or over the other."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_reveal_and_a_shown_group_leave_the_bars_to_be_seen():
    script = Path(__file__).with_name("web-texts-reveal.test.mjs")
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
