# SPDX-License-Identifier: Apache-2.0
"""Build the showcase, verify coverage and rehearse its real activity answers.
Uses the installed build dependencies, plus Node.js for the JavaScript engines;
texstage's own kinds (choice, number, text) are rehearsed with this checkout's code.
No server, publication, Office or physical-device automation.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".showcase-build"
SOURCE = ROOT / "examples/showcase/showcase.tex"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT/"src"))
# What phones send to the activities of texstage's own kinds, and what they get:
# the reveal's verdict, or the code the server refuses the entry with (a kind's
# own refusal would be "invalid <code>": a check the reveal calls incorrect).
OWN_KINDS = {
    "cool-bag": [({"choice":[0,2]},"correct"),({"choice":[2,0]},"correct"),
                 ({"choice":[0]},"incorrect"),({"choice":[0,2,3]},"incorrect"),
                 ({"choice":[]},"refused choice")],
    "walk": [({"number":7.5},"correct"),({"number":8},"correct"),({"number":7},"correct"),
             ({"number":9},"incorrect"),({"number":75},"incorrect"),({"number":"7.5"},"refused number")],
    "take-home": [({"text":"litter"},"correct"),({"text":"  Rubbish "},"correct"),({"text":"TRASH"},"correct"),
                  ({"text":"leftovers"},"incorrect"),({"text":"   "},"refused text")],
}

def run(*args):
    subprocess.run([sys.executable, "-m", "texstage.cli", *map(str,args)],
                   cwd=ROOT, env=ENV, check=True)

def rehearse_own_kinds(deck,keys):
    """Each answer as a server of the activity framework's core takes it: shaped as
    a phone's entry, normalized and checked by its kind after the references, and
    judged as the reveal judges. Imported from this checkout, as the builds run."""
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(ROOT/"src"))
    from texstage.activities import registry
    from texstage.activities.checks import Checks
    from texstage.activities.entries import Entries,Rules,shaped
    from texstage.activities.kind import Entry,Step,Unfit,first,referenced,validated
    from texstage.activities.phases import Refused
    from texstage.activities.reduce import Reduced
    from texstage.activities.store import ONE,CheckRow
    reveal=Reduced("showcase",Entries("showcase"),Checks("showcase"))
    for aid,answers in OWN_KINDS.items():
        item,key=deck["items"]["activity"][aid],keys["items"]["activity"][aid]
        kind=registry.kind(item["kind"])
        step=Step(item,key,deck.get("language"))
        prepared,_=first(kind,item,key,{})
        refs=[validated(kind,c,step) for c in referenced(kind,prepared,step)]
        assert [c.key for c in refs]==key["referenceKeys"],aid+": the build's reference keys"
        reveal.refer(aid,ONE,[c.sent() for c in refs])
        rules=Rules.of(item,kind)
        for sent,expected in answers:
            try:
                entry=kind.normalize(step,Entry.of(shaped(rules,sent)))
            except Refused as e:
                got="refused "+e.code
            except Unfit as e:
                got="invalid "+e.code
            else:
                c=validated(kind,kind.check(prepared,step,entry),step)
                got=reveal.verdict(aid,ONE,CheckRow("showcase",aid,ONE,"",c.status,key=c.key,verdict=c.verdict))
            assert got==expected,f"{aid}: {sent} is {got}, not {expected}"
        print("PASS "+aid+": correct, equivalent, incorrect and refused answers ("+item["kind"]+")")

def main():
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required to verify the three activity engines.")
    run("build",SOURCE,"--server","http://127.0.0.1:8766","--key","synthetic-showcase-only",
        "--data",OUT/"data","--height","900","--output-dir",OUT/"live")
    run("pdf",SOURCE,"--handout","--output-dir",OUT/"handout")
    bundle=OUT/"live/showcase.bundle"
    deck=json.loads((bundle/"deck.json").read_text(encoding="utf-8"))
    keys=json.loads((bundle/"keys.json").read_text(encoding="utf-8"))
    quizzes=deck["items"]["quiz"]
    assert len(quizzes)==13
    assert {q["type"] for q in quizzes.values()}=={
        "single","multiple","truefalse","numeric","text","order","poll","open","sketch"}
    assert not quizzes["duration"]["scored"]
    assert quizzes["blanket"]["reveal"]=="none"
    acts=deck["items"]["activity"]
    assert len(acts)==8
    assert {a.get("engine") for a in acts.values()}=={None,"sql","sparql","turtle"}
    assert {a["kind"] for a in acts.values()}=={"triples","choice","number","text",
        "sql-query","sparql-query","turtle-graph"}
    assert len(acts["carry"]["fields"])==2 and len(acts["bring"]["fields"])==3
    assert acts["carry"]["min"]==2 and acts["bring"]["review"]
    assert acts["cool-bag"]["options"]==["Yoghurt","Bread","Butter","Apples"]
    assert acts["cool-bag"]["select"]=="many" and acts["walk"]["tolerance"]==0.5
    assert set(keys["items"]["activity"])=={"packing-sql","water-sparql","bread-turtle",
        "cool-bag","walk","take-home"}
    assert all("reference" not in a for a in acts.values())
    assert all("correct" not in q and "accepted" not in q for q in quizzes.values())
    video=deck["items"]["video"]["packing"]
    assert video["start"]==1 and video["end"]==8 and video["loop"] and video["muted"]
    for field,original in (("media","packing.mp4"),("poster","packing-poster.jpg")):
        assert hashlib.sha256((bundle/video[field]).read_bytes()).digest()==hashlib.sha256(
            (SOURCE.parent/original).read_bytes()).digest()
    assert all(s.get("note") for s in deck["slides"])
    # The automatic leaderboard reuses its question's stage page/note page,
    # but deliberately has no separate extracted notes string.
    assert all(s.get("notes") or any(i.get("phase")=="leaderboard" for i in s.get("live",[]))
               for s in deck["slides"])
    subprocess.run([node,str(ROOT/"maintenance/check_showcase_engines.mjs"),str(bundle)],
                   cwd=ROOT,check=True)
    rehearse_own_kinds(deck,keys)
    output=OUT/"output"
    output.mkdir(exist_ok=True)
    # Use the stage PDF, excluding private note pages and extra phone assets.
    # This preview is a static review copy; use the browser for interaction.
    slide_pages=list(dict.fromkeys(s["page"]-1 for s in deck["slides"]))
    with pdfium.PdfDocument(bundle/deck["pdf"]["file"]) as stage:
        with pdfium.PdfDocument.new() as preview:
            preview.import_pages(stage,slide_pages)
            preview.save(output/"showcase-preview.pdf")
    shutil.copyfile(OUT/"live/build/showcase-solutions.pdf",output/"showcase-solutions.pdf")
    shutil.copyfile(OUT/"handout/showcase-handout.pdf",output/"showcase-handout.pdf")
    counts={}
    for name in ("preview","solutions","handout"):
        with pdfium.PdfDocument(output/f"showcase-{name}.pdf") as doc:
            counts[name]=len(doc)
    # Layout review remains visual; treat any overfull box as a failed rehearsal.
    for log in (OUT/"live/build").glob("*.log"):
        assert "Overfull " not in log.read_text(encoding="latin-1"),log
    assert "Overfull " not in (OUT/"handout/showcase-handout.log").read_text(encoding="latin-1")
    report={"quizzes":len(quizzes),"activities":len(acts),"videos":1,
            "authored_frames":max(s["frame"] for s in deck["slides"]),
            "live_steps":len(deck["slides"]),"pdf_pages":counts,
            "code_examples":"actual JS/WASM engines: references, equivalent/different results, syntax errors passed",
            "own_kinds":"choice, number, text: correct, equivalent, incorrect and refused answers, as the core's reveal judges them",
            "limits":"No physical device, Office, external network, autoplay or recording-permission test."}
    (output/"verification.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("PASS: showcase coverage, private references, media, notes, three engine and three kind rehearsals")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
