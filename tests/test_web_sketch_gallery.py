# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The presenter's production gallery synchronizes sketches through actual async JS."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_gallery_synchronization():
    test_file = Path(__file__).with_name("web-sketch-gallery.test.cjs")
    result = subprocess.run(["node", "--test", str(test_file)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
