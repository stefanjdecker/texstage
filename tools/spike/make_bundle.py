# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A bundle for F0's runs (activity-framework-plan.md, 3.4), as build/activity.py writes one - no LaTeX
needed - with four activities, each on a slide of its own:

    kg-rivers      the KG lecture's SPARQL activity on its seed (05-SPARQL/014.tex, data.ttl: 123 triples)
    kg-big         the same on a heavier seed: data.ttl and 10,000 triples more
    berlin-turtle  the KG lecture's Turtle activity (03-Serialization/015.tex, turtle-prefixes.ttl)
    packing-sql    the showcase's SQL activity

    python tools/spike/make_bundle.py <folder>      # writes <folder>/spike.bundle
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from texstage.build.bundle import bundle_id  # noqa: E402

KG = ROOT.parent / "KnowlegeGraph-VL"
SQL_SEED = ("CREATE TABLE packing (item TEXT, quantity INTEGER);\n"
            "INSERT INTO packing VALUES ('Apples',6),('Cups',6),('Blankets',2);\n").encode()
SQL_REFERENCE = "SELECT item FROM packing WHERE quantity = 6;"
REFERENCE = re.compile(r"\\reference\{(.*?)\}\n\\end\{activity\}", re.S)


def name(data: bytes, suffix: str, folder: str = "data") -> str:
    return f"{folder}/{hashlib.sha256(data).hexdigest()[:16]}{suffix}"


def bigger(ttl: bytes, subjects: int = 2500) -> bytes:
    """The KG seed and four triples per subject more - a class, a name, a size, a neighbour: 10,000."""
    lines = [f':s{i} a :Thing{i % 20} ; :name "thing {i}" ; :size {i * 7} ; :near :s{(i * 31) % subjects} .'
             for i in range(subjects)]
    return ttl + b"\n" + "\n".join(lines).encode() + b"\n"


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".") / "spike.bundle"
    ttl = (KG / "05-SPARQL" / "data.ttl").read_bytes()
    big = bigger(ttl)
    prefixes = (KG / "03-Serialization" / "turtle-prefixes.ttl").read_bytes()
    sparql_ref = REFERENCE.search((KG / "05-SPARQL" / "014.tex").read_text(encoding="utf-8")).group(1)
    turtle_ref = REFERENCE.search((KG / "03-Serialization" / "015.tex").read_text(encoding="utf-8")).group(1)
    pngs = {name(d, ".png", "slides"): d for d in (b"spike-one", b"spike-two")}
    s1, s2 = list(pngs)
    box = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
    rivers = ["SELECT", "WHERE", "{", "}", "a", ":River", ":name", ":locatedOnBank"]
    items = {
        "kg-rivers": {"input": "code", "limit": 5, "engine": "sparql", "seed": name(ttl, ".ttl"), "tokens": rivers},
        "kg-big": {"input": "code", "limit": 5, "engine": "sparql", "seed": name(big, ".ttl"), "tokens": rivers},
        "berlin-turtle": {"input": "code", "limit": 5, "engine": "turtle", "seed": name(prefixes, ".ttl"),
                          "tokens": ["dbr:Berlin", "rdfs:label", "dbo:populationTotal", "3596999"]},
        "packing-sql": {"input": "code", "limit": 5, "engine": "sql", "seed": name(SQL_SEED, ".sql"),
                        "tokens": ["SELECT", "FROM", "WHERE", "quantity"]},
    }

    def live(item):
        return [{"type": "activity", "item": item, "rects": {"box": box}}]
    slides = [{"id": 256, "image": s1}] + [{"id": 257 + i, "image": s2, "live": live(a)} for i, a in enumerate(items)]
    deck = {"format": 2, "deck": "spike", "name": "F0 spike", "types": ["activity"],
            "image": {"width": 1920, "height": 1080}, "slides": slides + [{"id": 300, "image": s1}],
            "items": {"activity": items}}
    keys = {"format": 2, "deck": "spike", "items": {"activity": {
        "kg-rivers": {"reference": [sparql_ref]}, "kg-big": {"reference": [sparql_ref]},
        "berlin-turtle": {"reference": [turtle_ref]}, "packing-sql": {"reference": [SQL_REFERENCE]}}}}
    bid = bundle_id(deck, keys)
    files = {**pngs, items["kg-rivers"]["seed"]: ttl, items["kg-big"]["seed"]: big,
             items["berlin-turtle"]["seed"]: prefixes, items["packing-sql"]["seed"]: SQL_SEED}
    for rel, data in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
    for rel, data in (("deck.json", deck), ("keys.json", keys)):
        (out / rel).write_text(json.dumps(data | {"bundle": bid}, ensure_ascii=False), encoding="utf-8")
    print(f"{out} (bundle {bid}; kg-big's seed {big.count(b'.') // 1} statements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
