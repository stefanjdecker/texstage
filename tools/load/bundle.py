# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A bundle for the load runs of F1's package 6 (docs/architecture/activity-framework-plan.md, 3.4 and
4.9), as build/activity.py writes one - no LaTeX needed - with four code activities, each on a slide of
its own:

    sparql       a SPARQL activity on a small seed
    sparql-big   the same on a heavier seed: 10,000 triples more
    turtle       a Turtle activity
    sql          the showcase's SQL activity

    python tools/load/bundle.py <folder> [--lecture <the KG lecture's folder>]    # writes <folder>/load.bundle

With --lecture - by default the folder KnowlegeGraph-VL beside this repository, where it is there - the
SPARQL and the Turtle activity are a lecture's own: its seed, its prefixes and its references, read from
there and written into the bundle only (the plan's run 3). Without it they are stand-ins of the same
size, made here. From F0's tools/spike/make_bundle.py (branch f0-spike).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
try:
    from texstage.build.bundle import bundle_id
except ImportError:                                      # a checkout without texstage installed: its own source
    sys.path.insert(0, str(ROOT / "src"))
    from texstage.build.bundle import bundle_id

LECTURE = ROOT.parent / "KnowlegeGraph-VL"
SQL_SEED = ("CREATE TABLE packing (item TEXT, quantity INTEGER);\n"
            "INSERT INTO packing VALUES ('Apples',6),('Cups',6),('Blankets',2);\n").encode()
SQL_REFERENCE = "SELECT item FROM packing WHERE quantity = 6;"
REFERENCE = re.compile(r"\\reference\{(.*?)\}\n\\end\{activity\}", re.S)
# the stand-ins: rivers and the cities on their banks, about as many triples as a lecture's seed
PREFIX = "@prefix : <http://example.org/> .\n"
SPARQL_REFERENCE = "SELECT ?name WHERE { ?r a :River ; :name ?name }"
TURTLE_PREFIXES = ("@prefix ex: <http://example.org/> .\n"
                   "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n").encode()
TURTLE_REFERENCE = 'ex:Berlin rdfs:label "Berlin"@de ;\n  ex:population 3596999 .'


def name(data: bytes, suffix: str, folder: str = "data") -> str:
    return f"{folder}/{hashlib.sha256(data).hexdigest()[:16]}{suffix}"


def rivers(n: int = 30) -> bytes:
    """n rivers with a name, a length and a city on their bank: four triples each."""
    lines = [f':r{i} a :River ; :name "River {i}" ; :length {100 + 37 * i} ; :locatedOnBank :c{i % 7} .'
             for i in range(n)]
    return (PREFIX + "\n".join(lines) + "\n").encode()


def bigger(ttl: bytes, subjects: int = 2500) -> bytes:
    """A seed and four triples per subject more - a class, a name, a size, a neighbour: 10,000."""
    lines = [f':s{i} a :Thing{i % 20} ; :name "thing {i}" ; :size {i * 7} ; :near :s{(i * 31) % subjects} .'
             for i in range(subjects)]
    return ttl + b"\n" + "\n".join(lines).encode() + b"\n"


def lecture(folder: Path) -> tuple[bytes, str, bytes, str]:
    """The lecture's SPARQL seed and reference, its Turtle prefixes and reference."""
    ttl = (folder / "05-SPARQL" / "data.ttl").read_bytes()
    prefixes = (folder / "03-Serialization" / "turtle-prefixes.ttl").read_bytes()
    sparql = REFERENCE.search((folder / "05-SPARQL" / "014.tex").read_text(encoding="utf-8")).group(1)
    turtle = REFERENCE.search((folder / "03-Serialization" / "015.tex").read_text(encoding="utf-8")).group(1)
    return ttl, sparql, prefixes, turtle


def make(out: Path, lecture_folder: Path | None = None) -> str:
    """Writes the bundle to out; its id."""
    if lecture_folder is not None:
        ttl, sparql_ref, prefixes, turtle_ref = lecture(lecture_folder)
    else:
        ttl, sparql_ref, prefixes, turtle_ref = rivers(), SPARQL_REFERENCE, TURTLE_PREFIXES, TURTLE_REFERENCE
    big = bigger(ttl)
    pngs = {name(d, ".png", "slides"): d for d in (b"load-one", b"load-two")}
    s1, s2 = list(pngs)
    box = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
    words = ["SELECT", "WHERE", "{", "}", "a", ":River", ":name"]
    items = {
        "sparql": {"input": "code", "limit": 5, "engine": "sparql", "seed": name(ttl, ".ttl"), "tokens": words},
        "sparql-big": {"input": "code", "limit": 5, "engine": "sparql", "seed": name(big, ".ttl"), "tokens": words},
        "turtle": {"input": "code", "limit": 5, "engine": "turtle", "seed": name(prefixes, ".ttl"),
                   "tokens": ["rdfs:label", "."]},
        "sql": {"input": "code", "limit": 5, "engine": "sql", "seed": name(SQL_SEED, ".sql"),
                "tokens": ["SELECT", "FROM", "WHERE", "quantity"]},
    }

    def live(item):
        return [{"type": "activity", "item": item, "rects": {"box": box}}]
    slides = [{"id": 256, "image": s1}] + [{"id": 257 + i, "image": s2, "live": live(a)} for i, a in enumerate(items)]
    deck = {"format": 2, "deck": "load", "name": "Load runs", "types": ["activity"],
            "image": {"width": 1920, "height": 1080}, "slides": slides + [{"id": 300, "image": s1}],
            "items": {"activity": items}}
    keys = {"format": 2, "deck": "load", "items": {"activity": {
        "sparql": {"reference": [sparql_ref]}, "sparql-big": {"reference": [sparql_ref]},
        "turtle": {"reference": [turtle_ref]}, "sql": {"reference": [SQL_REFERENCE]}}}}
    bid = bundle_id(deck, keys)
    files = {**pngs, items["sparql"]["seed"]: ttl, items["sparql-big"]["seed"]: big,
             items["turtle"]["seed"]: prefixes, items["sql"]["seed"]: SQL_SEED}
    for rel, data in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
    for rel, data in (("deck.json", deck), ("keys.json", keys)):
        (out / rel).write_text(json.dumps(data | {"bundle": bid}, ensure_ascii=False), encoding="utf-8")
    return bid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder", type=Path, nargs="?", default=Path("."))
    ap.add_argument("--lecture", type=Path, default=LECTURE if LECTURE.is_dir() else None,
                    help="the KG lecture's folder: its SPARQL and Turtle activities, not the stand-ins")
    ap.add_argument("--stand-ins", action="store_true", help="the stand-ins, though the lecture's folder is there")
    args = ap.parse_args()
    folder = None if args.stand_ins else args.lecture
    out = args.folder / "load.bundle"
    bid = make(out, folder)
    print(f"{out} (bundle {bid}; the SPARQL and Turtle activities: "
          f"{'the lecture in ' + str(folder) if folder else 'stand-ins'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
