# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The activity framework in the browser (web/play/activities.js, web/stage/activities.js, web/kinds.js), in
Node: an entry's states as the phone says them, the step's time, the kinds' texts, what the box calls a
group, the lead window's agent (web-activities.test.mjs)."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_phone_the_box_and_the_lead_window_of_the_activity_framework():
    script = Path(__file__).with_name("web-activities.test.mjs")
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
