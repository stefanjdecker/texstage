# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shutil,subprocess
import pytest

@pytest.mark.skipif(shutil.which("node") is None,reason="needs Node.js")
def test_evaluator_batch_polling_and_teardown():
    result=subprocess.run([shutil.which("node"),"--experimental-vm-modules","--test",
        str(Path(__file__).with_name("web-plugin-evaluator-poll.test.mjs"))],
        capture_output=True,text=True,encoding="utf-8",timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
