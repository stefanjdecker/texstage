# SPDX-License-Identifier: Apache-2.0
"""Check an installed texstage wheel outside the source checkout (needs pdflatex)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import texstage
from texstage.api import LATEX_FILES, latex_resources

assert "site-packages" in Path(texstage.__file__).parts, texstage.__file__
with latex_resources() as resources:
    assert "site-packages" in resources.parts
    assert {p.name for p in resources.glob("*.sty")} == set(LATEX_FILES)
with tempfile.TemporaryDirectory(prefix="texstage-wheel-") as tmp:
    scratch = Path(tmp)
    source = scratch / "demo.tex"
    source.write_text(r"\documentclass{beamer}\usepackage{texquiz}\begin{document}\quizjoinframe\begin{quiz}[id=two]{Two plus two?}\choice*{Four}\choice{Five}\end{quiz}\end{document}")
    console = Path(sys.executable).with_name("texstage.exe" if os.name == "nt" else "texstage")
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "TEXINPUTS")}
    result = subprocess.run([str(console), "build", str(source), "--data", str(scratch / "data"),
                             "--key", "synthetic-test-key", "--no-check"], cwd=scratch, env=env,
                            capture_output=True, text=True, errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    bundle, = (scratch / "texquiz-out").glob("*.bundle")
    assert json.loads((bundle / "deck.json").read_text())["deck"] == "demo"
    assert list((scratch / "texquiz-out").glob("*.pptx"))
print("PASS: installed console, resources and synthetic live deck build")
