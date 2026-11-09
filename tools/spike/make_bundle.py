# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A bundle for F0's runs (activity-framework-plan.md, 3.4): the KG lecture's SPARQL activity on its
seed (05-SPARQL/014.tex, data.ttl) and the showcase's SQL activity, each on a slide of its own, as
build/activity.py writes them - no LaTeX needed.

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

KG = ROOT.parent / "KnowlegeGraph-VL" / "05-SPARQL"
SQL_SEED = ("CREATE TABLE packing (item TEXT, quantity INTEGER);\n"
            "INSERT INTO packing VALUES ('Apples',6),('Cups',6),('Blankets',2);\n").encode()
SQL_REFERENCE = "SELECT item FROM packing WHERE quantity = 6;"


def name(data: bytes, suffix: str, folder: str = "data") -> str:
    return f"{folder}/{hashlib.sha256(data).hexdigest()[:16]}{suffix}"


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".") / "spike.bundle"
    ttl = (KG / "data.ttl").read_bytes()
    tex = (KG / "014.tex").read_text(encoding="utf-8")
    reference = re.search(r"\\reference\{(.*?)\}\n\\end\{activity\}", tex, re.S).group(1)
    pngs = {name(d, ".png", "slides"): d for d in (b"spike-one", b"spike-two")}
    s1, s2 = list(pngs)
    box = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
    items = {
        "kg-rivers": {"input": "code", "limit": 5, "engine": "sparql", "seed": name(ttl, ".ttl"),
                      "tokens": ["SELECT", "WHERE", "{", "}", "a", ":River", ":name", ":locatedOnBank"]},
        "packing-sql": {"input": "code", "limit": 5, "engine": "sql", "seed": name(SQL_SEED, ".sql"),
                        "tokens": ["SELECT", "FROM", "WHERE", "quantity"]},
    }

    def live(item):
        return [{"type": "activity", "item": item, "rects": {"box": box}}]
    deck = {"format": 2, "deck": "spike", "name": "F0 spike", "types": ["activity"],
            "image": {"width": 1920, "height": 1080},
            "slides": [{"id": 256, "image": s1}, {"id": 257, "image": s2, "live": live("kg-rivers")},
                       {"id": 258, "image": s2, "live": live("packing-sql")}, {"id": 259, "image": s1}],
            "items": {"activity": items}}
    keys = {"format": 2, "deck": "spike", "items": {"activity": {"kg-rivers": {"reference": [reference]},
                                                                 "packing-sql": {"reference": [SQL_REFERENCE]}}}}
    bid = bundle_id(deck, keys)
    files = {**pngs, items["kg-rivers"]["seed"]: ttl, items["packing-sql"]["seed"]: SQL_SEED}
    for rel, data in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
    for rel, data in (("deck.json", deck), ("keys.json", keys)):
        (out / rel).write_text(json.dumps(data | {"bundle": bid}, ensure_ascii=False), encoding="utf-8")
    print(f"{out} (bundle {bid})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
