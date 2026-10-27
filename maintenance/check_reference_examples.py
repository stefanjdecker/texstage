# SPDX-License-Identifier: Apache-2.0
"""Compile the synthetic authoring contract using this checkout; no server/publication."""
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTHONPATH=str(ROOT/"src"))
out=ROOT/".reference-build"
out.mkdir(exist_ok=True)
source=ROOT/"examples/reference/reference.tex"
def run(*args):
    subprocess.run([sys.executable,"-m","texstage.cli",*map(str,args)],cwd=ROOT,env=env,check=True)
run("build",source,"--server","http://127.0.0.1:8470","--key","synthetic-reference-only",
    "--data",out/"data","--height","720","--output-dir",out/"live")
run("pdf",source,"--handout","--output-dir",out/"handout")
deck=json.loads((out/"live/reference.bundle/deck.json").read_text(encoding="utf-8"))
keys=json.loads((out/"live/reference.bundle/keys.json").read_text(encoding="utf-8"))
quizzes=deck["items"]["quiz"]
assert {q["type"] for q in quizzes.values()}=={
    "single","multiple","truefalse","poll","numeric","text","open","order","sketch"}
assert not quizzes["estimate"]["scored"]
assert quizzes["text"]["reveal"]=="none"
assert len(deck["items"]["activity"])==4
assert {a.get("engine") for a in deck["items"]["activity"].values()}=={
    None,"sql","sparql","turtle"}
assert set(keys["items"]["activity"])=={"sql","sparql","turtle"}
assert all("reference" not in a for a in deck["items"]["activity"].values())
assert len(deck["items"]["video"])==1
print("PASS: checked live bundle, stage/solutions/handout and four activities")
