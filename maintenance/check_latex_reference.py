# SPDX-License-Identifier: Apache-2.0
"""Source-review guard, not a full TeX parser. Update --write after reviewing API changes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
IS_TEXSTAGE=(ROOT/"docs/manual-content.json").exists()
NAME="latex-reference" if IS_TEXSTAGE else "style-reference"

def inventory():
    files=[]
    # Restrict to shipped styles and fixtures; never inspect generated build trees.
    paths=sorted(p for folder in ("latex","docs","examples","tests")
                 for p in (ROOT/folder).rglob("*.sty")
                 if not any(part in {"out","texquiz-out","__pycache__"} for part in p.parts))
    for path in paths:
        name=path.relative_to(ROOT).as_posix()
        source=re.sub(r"(?m)(?<!\\)%.*$", "", path.read_text(encoding="utf-8"))
        commands=set()
        for pattern in (
            r"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{?\s*\\([A-Za-z@]+)",
            r"\\(?:New|Renew|Provide)DocumentCommand\s*\{?\s*\\([A-Za-z@_:]+)",
            r"\\(?:gdef|edef|def)\s*\\([A-Za-z@]+)",
            r"\\cs_(?:new|set)(?:_protected|_eq)?:[A-Za-z]+\s*\\(texstage_[A-Za-z_:]+)",
        ):
            commands.update(re.findall(pattern,source))
        commands.update(re.findall(r"\\prg_new_conditional:Npnn\s*\\(texstage_[A-Za-z_:]+)",source))
        if name=="latex/texstage.sty":
            commands.update(("texstagemode","texquizmode","texquiznotes"))
        if name=="latex/texquiz.sty":
            commands.update(("choice","explain","accept","step"))
        if name=="latex/texactivity.sty":
            commands.update(("prompt","reference","seed"))
        environments=sorted(set(re.findall(
            r"\\(?:newenvironment|renewenvironment|newtcolorbox|renewtcolorbox|NewDocumentEnvironment)\s*\{\s*([A-Za-z]+)\s*\}",source)))
        styles=sorted(set(x.strip() for x in re.findall(
            r"(?m)^\s*([a-z][a-z0-9 -]*?)/\.(?:style|append style|code|is choice)\b",source)))
        keys=sorted(set(re.findall(r"(?m)^\s*([a-z][a-z-]*)\s*\.[a-z_]+:",source)))
        languages=sorted(set(re.findall(r"\\lstdefinelanguage\{([^}]+)\}",source)))
        private=sorted(x for x in commands if "@" in x or x.startswith("__") or x.endswith("dir") or x=="ojoin")
        scope=("upstream-texstage" if "/vendor/texstage/" in name else
               "documentation" if name.startswith("docs/") else
               "fixture-or-example" if name.startswith(("tests/","examples/")) else "runtime")
        files.append(dict(file=name,scope=scope,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            commands=sorted(commands-set(private)-{"csname"}),internal_commands=private,
            environments=environments,styles=styles,keys=keys,listings_languages=languages))
    return {"schema_version":1,"method":"Reviewed source hashes and declaration inventory; not a complete TeX parser.",
            "files":files}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write",action="store_true")
    args=parser.parse_args()
    path=ROOT/"docs"/(NAME+"-inventory.json")
    current=inventory()
    if args.write:
        path.write_text(json.dumps(current,indent=2)+"\n",encoding="utf-8",newline="\n")
    else:
        assert json.loads(path.read_text(encoding="utf-8"))==current, "Style source changed: review the reference and update its inventory"
        # Exact public-name presence, with upstream/fixture interfaces delegated.
        content=json.loads((ROOT/"docs"/("manual-content.json" if IS_TEXSTAGE else "style-reference-content.json")).read_text(encoding="utf-8"))
        text=json.dumps(content,ensure_ascii=False)
        missing=[]
        for file in current["files"]:
            if file["scope"]!="runtime": continue
            for group in ("commands","environments","styles","keys","listings_languages"):
                for name in file[group]:
                    if name in {"unknown","every node"}: continue
                    if name not in text: missing.append(file["file"]+": "+name)
        assert not missing, "Reference names missing:\n"+"\n".join(missing)
    print(f"PASS: {len(current['files'])} style files inventoried")
if __name__=="__main__": main()
