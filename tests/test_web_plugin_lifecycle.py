# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shutil
import subprocess
import pytest

@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_plugin_mount_lifecycle_and_structured_errors():
    result = subprocess.run([shutil.which("node"), "--experimental-vm-modules", "--test",
        str(Path(__file__).with_name("web-plugin-lifecycle.test.mjs"))],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_plugin_evaluator_queue_backoff_and_teardown():
    result = subprocess.run([shutil.which("node"), "--experimental-vm-modules", "--test",
        str(Path(__file__).with_name("web-plugin-evaluator.test.mjs"))],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_plugin_asset_cache_bounds_and_isolation():
    result = subprocess.run([shutil.which("node"), "--experimental-vm-modules", "--test",
        str(Path(__file__).with_name("web-plugin-assets.test.mjs"))],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

