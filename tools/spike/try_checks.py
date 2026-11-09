# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A smoke test of the spike's checks (checks.py) on the KG lecture's and the showcase's seeds, in this
process - no pool. python tools/spike/try_checks.py"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import checks  # noqa: E402

KG = HERE.parents[2] / "KnowlegeGraph-VL"


def show(engine: str, state: dict, text: str):
    r = checks.check(engine, state, text)
    shown = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}
    print(f"  {text[:60]!r:66} -> {shown}")


def main() -> int:
    tex = (KG / "05-SPARQL" / "014.tex").read_text(encoding="utf-8")
    ref = re.search(r"\\reference\{(.*?)\}\n\\end\{activity\}", tex, re.S).group(1)
    sparql = checks.prepare("sparql", (KG / "05-SPARQL" / "data.ttl").read_text(encoding="utf-8"), [ref])
    print("sparql, the KG lecture's river-settlements; reference keys:", sparql["refs"])
    for t in [ref,
              "SELECT * WHERE { SERVICE <http://127.0.0.1:9/> { ?s ?p ?o } }",
              "SELECT * WHERE { \\u0053ERVICE <http://127.0.0.1:9/> { ?s ?p ?o } }",
              "SELECT * WHERE { ?s ?p 'SERVICE' }",
              "SELEC ?x WHERE { }",
              "SELECT ?o WHERE { ?s ?p ?o . ?a ?b ?c . ?d ?e ?f }",
              "SELECT * WHERE " + "{ " * 600 + "}" * 600]:
        show("sparql", sparql, t)

    sql = checks.prepare("sql", "CREATE TABLE packing (item TEXT, quantity INTEGER);"
                                " INSERT INTO packing VALUES ('Apples',6),('Cups',6),('Blankets',2);",
                         ["SELECT item FROM packing WHERE quantity = 6;"])
    print("sql, the showcase's packing-sql; reference keys:", sql["refs"], "heap limit:", sql["heap_limit"])
    for t in ["SELECT item FROM packing WHERE quantity = 6",
              "select item from packing where quantity=6 -- me",
              "DELETE FROM packing",
              "SELECT 1; SELECT 2",
              "ATTACH DATABASE 'x.db' AS x",
              "SELECT * FROM nope",
              "SELEC 1",
              "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT count(*) FROM r",
              "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r LIMIT 200000) SELECT n FROM r",
              "WITH RECURSIVE r(n, s) AS (SELECT 1, randomblob(1000) UNION ALL SELECT n+1, randomblob(1000) "
              "FROM r LIMIT 2000000) SELECT n, s FROM r ORDER BY s LIMIT 1"]:
        show("sql", sql, t)

    turtle = checks.prepare("turtle", (KG / "03-Serialization" / "turtle-prefixes.ttl").read_text(encoding="utf-8"))
    print("turtle, the KG lecture's berlin-turtle seed")
    for t in [":Berlin a :City ; :name “Berlin” .", ":a :b", ""]:
        show("turtle", turtle, t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
