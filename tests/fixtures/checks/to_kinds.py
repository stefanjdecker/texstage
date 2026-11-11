# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The kinds' fixtures, which `texstage kinds check` runs (texstage/activities/kit.py), made from the golden
fixtures of today's engines beside this file - until F1 is in main and the golden fixtures move into the
kinds' packages themselves (docs/architecture/activity-framework-plan-f2.md, 4.2 and 4.7):

    python tests/fixtures/checks/to_kinds.py            writes kinds/*/src/*/tests/*.json
    python tests/fixtures/checks/to_kinds.py --check    says whether they are what it would write

Every golden case becomes a case of its kind - the entry, and the check the kind gives for it, which is
the golden result: tests/test_kinds.py holds the two against each other, and this file refuses to write a
case whose words differ. A case the server answers otherwise than the browser did (test_checks.py: KNOWN)
or in SQLite's own words, which depend on its build (BUILT), pins its status and its message's code only.
With them: the safety cases - SERVICE in every spelling, the names that are not it, nesting beyond the
parsers' cap and up to it -; a setting with references over rows that are not ASCII, and the kinds'
builds; and the cases of triples, which have no golden fixtures.
tests/test_kit.py: the files are what this makes."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "tests"), *(str(p) for p in sorted((ROOT / "kinds").glob("*/src")))]

import test_checks as f1  # noqa: E402 - the golden fixtures, KNOWN and BUILT, the safety tests' texts
from texstage_kinds_rdf import SparqlQuery, Triples, TurtleGraph  # noqa: E402
from texstage_kinds_sql import SqlQuery  # noqa: E402

from texstage.activities.code import words  # noqa: E402
from texstage.activities import kind as contract  # noqa: E402
from texstage.activities.kind import Entry, Step, Unbuildable, Unfit  # noqa: E402
from texstage.activities.kit import STACK, text_of  # noqa: E402
from texstage.activities.options import Options  # noqa: E402
from texstage.checks import common  # noqa: E402

KINDS = {"sql": SqlQuery(), "sparql": SparqlQuery(), "turtle": TurtleGraph()}
FOLDER = {"sql": "texstage-kinds-sql/src/texstage_kinds_sql", "sparql": "texstage-kinds-rdf/src/texstage_kinds_rdf",
          "turtle": "texstage-kinds-rdf/src/texstage_kinds_rdf", "triples": "texstage-kinds-rdf/src/texstage_kinds_rdf"}
SUFFIX = {"sql": ".sql", "sparql": ".ttl", "turtle": ".ttl"}
LOOSE = ("status", "message")                   # what a case pins whose words are SQLite's or the server's own
BUILDS = ("ok", "error", "invalid")             # ... and what a text may be that only some builds of SQLite run


def settings(engine: str) -> dict:
    return {name: {"item": {"seed": f"data/{name}{SUFFIX[engine]}"}, "files": {f"data/{name}{SUFFIX[engine]}": text}}
            for name, text in f1.fixture(engine)["seeds"].items()}


def pinned(kind, prepared, written: dict, language: str = "en", loose: bool = False) -> dict:
    """A case for an entry: what the kind gives for it now - through normalize, or direct where normalize
    refuses it or changes it."""
    step = Step({}, language=language)
    entry = Entry(text=text_of(written["text"]))
    case = {"entry": written}
    try:
        direct = kind.normalize(step, entry) != entry
    except Unfit:
        direct = True
    if direct:
        case["direct"] = True
    sent = kind.check(prepared, step, entry).sent()
    if loose:
        sent = {k: ({"code": v["code"]} if k == "message" else v) for k, v in sent.items() if k in LOOSE}
    case["check"] = sent
    return case


def golden(engine: str) -> dict:
    kind, made = KINDS[engine], settings(engine)
    prepared = {name: kind.prepare(s["item"], {}, {n: t.encode("utf-8") for n, t in s["files"].items()})
                for name, s in made.items()}
    cases = []
    for case in f1.fixture(engine)["cases"]:
        written = case["text"] if isinstance(case["text"], str) else None
        loose = (engine, written, case["language"]) in f1.KNOWN or (engine, written) in f1.BUILT
        check = kind.check(prepared[case["seed"]], Step({}, language=case["language"]), Entry(text=f1.expand(case["text"])))
        record = {"status": {"invalid": "syntax"}.get(check.status, check.status)}
        if check.message is not None:
            record["error"] = words(check.message, case["language"])
        if check.canonical is not None:
            record["key"] = check.key
            if common.utf16_len(check.canonical) <= f1.CANONICAL_MAX:
                record["canonical"] = check.canonical
            else:
                record["canonical_length"] = common.utf16_len(check.canonical)
        if check.rows is not None and common.utf16_len(common.js_stringify(check.rows)) <= f1.CANONICAL_MAX:
            record["rows"] = check.rows
        if check.detail is not None:
            record["summary"] = check.detail
        f1.agrees(engine, case, record)                 # the kind gives the golden result, or this stops
        it = pinned(kind, prepared[case["seed"]], {"text": case["text"]}, case["language"], loose)
        cases.append({"setting": case["seed"], **({"language": "de"} if case["language"] == "de" else {}), **it})
    return {"kind": kind.NAME, "from": f"tests/fixtures/checks/{engine}.json", "settings": made, "cases": cases}


def texts_of(test) -> list[str]:
    """The texts a test of test_checks.py is run with (its parametrize)."""
    return list(test.pytestmark[0].args[1])


def safety(engine: str) -> dict:
    kind = KINDS[engine]
    seed = {"sparql": "@prefix : <http://e.org/> .\n:a :p :b .\n", "turtle": "@prefix : <http://e.org/> .\n",
            "sql": "CREATE TABLE t (x);\nINSERT INTO t VALUES (1);\n"}[engine]
    name = f"data/seed{SUFFIX[engine]}"
    made = {"seed": {"item": {"seed": name}, "files": {name: seed}}}
    prepared = kind.prepare(made["seed"]["item"], {}, {name: seed.encode("utf-8")})
    cap = common.NESTING_MAX
    if engine == "sparql":
        entries = [{"text": t} for t in texts_of(f1.test_service_is_refused_in_every_spelling)]
        entries += [{"text": t} for t in texts_of(f1.test_names_strings_and_comments_that_say_service_are_no_service)]
        deep = {"before": "SELECT * WHERE ", "open": "{ ", "inside": "?s ?p ?o ", "close": "} "}
        entries += [{"text": {"deep": 5000, **deep}}, {"text": {"deep": cap, **deep}}, {"text": {"deep": cap + 1, **deep}}]
    elif engine == "turtle":
        deep = {"before": ":a :p ", "open": "[ :q ", "inside": ":b", "close": " ]", "after": " ."}
        entries = [{"text": {"deep": 5000, **deep}}, {"text": {"deep": cap, **deep}}, {"text": {"deep": cap + 1, **deep}}]
    else:
        deep = {"before": "SELECT ", "open": "(", "inside": "1", "close": ")"}
        entries = [{"text": {"deep": 5000, **deep}}, {"text": {"deep": 50, **deep}},
                   {"text": "PRAGMA query_only = OFF"}, {"text": "SELECT 1; DELETE FROM t"},
                   {"text": "WITH d AS (SELECT 1) DELETE FROM t"}, {"text": "ATTACH DATABASE 'x.db' AS x"},
                   {"text": "SELECT load_extension('x')"}, {"text": "SELECT writefile('x', 1)"}]
    cases = []
    cases = [{"setting": "seed", **pinned(kind, prepared, written, loose=engine == "sql")} for written in entries]
    if engine == "sql":                                 # how deep an expression may be is SQLite's build's: Python's own on
        assert cases[0]["check"]["status"] in BUILDS   # Windows takes 5,000 levels, Ubuntu's refuses them
        cases[0]["check"] = {"status": list(BUILDS)}
    return {"kind": kind.NAME, "settings": made, "cases": cases}


TUPLES = [
    (["Subject", "Predicate", "Object"], "exact", [":Kant", ":knows", ":Hume"]),
    (["Subject", "Predicate", "Object"], "exact", ["  \u201cKant\u201d@de ", "is  a", "\u2018Philosopher\u2019"]),
    (["Subject", "Predicate", "Object"], "exact", ["KANT", "Knows", "hume"]),
    (["Subject", "Predicate", "Object"], "loose", ["KANT", "Knows", "hume"]),
    (["Subject", "Predicate", "Object"], "loose", ["K\u00f6ln", "liegt  am", "\"Rhein\"@de"]),
    (["Subject", "Predicate", "Object"], "loose", ["x", "is", "TRUE"]),
    (["Subject", "Predicate", "Object"], "exact", ["x", "is", "true"]),
    (["Subject", "Predicate", "Object"], "exact", ["a\u0007b", "x\u200b", "42"]),
    (["From", "To"], "exact", [":Aachen", ":K\u00f6ln"]),
    (["From", "To"], "loose", ["  Aachen ", "K\u00d6LN"]),
    (["Subject", "Predicate", "Object"], "exact", ["a", "", "c"]),
    (["Subject", "Predicate", "Object"], "exact", ["a", "b", "x" * 61]),
    (["Subject", "Predicate", "Object"], "exact", ["\u0301", "b", "c"]),
    (["Subject", "Predicate", "Object"], "exact", ["a", "b"]),
    (["Subject", "Predicate", "Object"], "exact", ["a", "b", "c", "d"]),
    (["From", "To"], "exact", ["a", "b", "c"]),
    (["Subject", "Predicate", "Object"], "exact", "abc"),
    (["Subject", "Predicate", "Object"], "exact", ["a", 5, "c"]),
]


def triples() -> dict:
    kind, made, cases = Triples(), {}, []
    for fields, terms, sent in TUPLES:
        name = f"{len(fields)} fields, {terms}"
        made.setdefault(name, {"item": {"fields": fields, "terms": terms}})
        step = Step(made[name]["item"])
        case = {"setting": name, "entry": {"fields": sent}}
        try:
            entry = kind.normalize(step, Entry(fields=tuple(sent) if isinstance(sent, list) else sent))
        except Unfit as e:
            case["unfit"] = e.code
        else:
            case["check"] = kind.check(kind.prepare(step.item, {}, {}), step, entry).sent()
        cases.append(case)
    given = [{"options": {"fields": ["Who", "does", "What"], "suggest": [":Kant", ":Hume"], "min": "2", "review": True,
                          "terms": "loose"}},
             {"options": {"fields": ["From", "To"]}},
             {"options": {"fields": ["One"]}},
             {"options": {"fields": ["a", "b", "c"], "terms": "fuzzy"}},
             {"options": {"fields": ["a", "b", "c"], "min": "many"}},
             {"options": {"fields": ["a", "b", "c"], "suggest": ["x", ""]}}]
    return {"kind": kind.NAME, "settings": made, "cases": cases, "builds": [built(kind, b) for b in given]}


def built(kind, build: dict) -> dict:
    """A build with what the kind makes of it now, or the words it refuses it with."""
    given = build.get("files", {})

    def files(name: str, what: str) -> str:
        if name not in given:
            raise Unbuildable(f"the {what} {name} is not there (paths are the deck's)")
        return given[name]

    try:
        made = kind.build(Options(kind.OPTIONS, build.get("options", {}), files), build.get("bodies", {}))
    except Unbuildable as e:
        return {**build, "refused": str(e)}
    return {**build, "built": {"item": made.item, "keys": made.keys,
                               "files": {name: data.decode("utf-8") for name, data in made.files.items()}}}


def names() -> list[str]:
    """Twenty names that are not ASCII - Cyrillic, some with German's umlauts, some with emoji -, long enough
    that a table of them is over 12 KiB once every letter is escaped, and a sixth of that as it is."""
    cyrillic = "".join(chr(0x410 + i % 32) for i in range(100))
    german = " M" + chr(0xFC) + "ller " + chr(0xC4) + chr(0xD6) + chr(0xDC) + chr(0xDF)
    return [cyrillic + ("", german, " " + chr(0x1F600) * 5)[i % 3] + f" {i}" for i in range(20)]


def reference(engine: str) -> dict:
    """A setting with references - the first fails, the second gives the rows the checks after it are
    compared with - over rows that are not ASCII, whose details an escaped JSON would make six times as
    long (the review of package 2); and the kind's builds."""
    kind, suffix = KINDS[engine], SUFFIX[engine]
    people = names()
    if engine == "sql":
        seed = "CREATE TABLE person (name TEXT, n INTEGER);\n" + "".join(
            f"INSERT INTO person VALUES ('{name}', {i});\n" for i, name in enumerate(people))
        references = ["SELEC name FROM person", "SELECT name FROM person", "SELECT name, n FROM person"]
        texts = ["SELECT name FROM person ORDER BY n DESC", "SELECT name FROM person WHERE n < 5", "SELECT * FROM person",
                 "SELECT n FROM person", "SELECT name FROM persons"]
    elif engine == "sparql":
        seed = "@prefix : <http://e.org/> .\n" + "".join(f':p{i} :name "{name}" ; :n {i} .\n' for i, name in enumerate(people))
        references = ["SELECT ?name WHERE { ?p :name ?name", "SELECT ?name WHERE { ?p :name ?name }", "ASK { ?p :name ?name }"]
        texts = ["SELECT ?x WHERE { ?p :name ?x }", "SELECT ?name WHERE { ?p :name ?name ; :n ?n FILTER(?n < 5) }",
                 "SELECT * WHERE { ?p ?q ?o }", "SELECT ?n WHERE { ?p :n ?n }", "SELECT ?name WHERE { ?p :nam ?name }"]
    else:
        seed = "@prefix : <http://e.org/> .\n"
        lines = [f':p{i} :name "{name}" .' for i, name in enumerate(people[:12])]       # (a text has 2,000 characters)
        references = [":a :b", "\n".join(lines), ":a :b :c ."]
        texts = ["\n".join(reversed(lines)), "\n".join(lines[:5]), "\n".join(lines) + "\n:p0 :n 0 .", ":x :y :z .", ":x :y"]
    name = f"data/people{suffix}"
    item, keys, files = {"seed": name}, {"reference": references}, {name: seed.encode("utf-8")}
    prepared, _ = contract.first(kind, item, keys, files, most=2**20)
    step = Step(item, keys)
    assert [c.status for c in contract.referenced(kind, prepared, step)] == ["invalid", "ok", "ok"]
    cases = []
    for text in texts:
        sent = kind.check(prepared, step, kind.normalize(step, Entry(text=text))).sent()
        assert sent["status"] != "ok" or "diff" in sent["detail"]
        cases.append({"setting": "people", "entry": {"text": text}, "check": sent})
    other, small = (".ttl" if engine == "sql" else ".sql"), {"sql": "CREATE TABLE t (x);\n"}.get(engine, "@prefix : <http://e.org/> .\n")
    given = [
        {"options": {"tokens": ["a", "?"], "seed": f"Seed{suffix.upper()}", "reference": "ref.txt"},
         "bodies": {"references": ["from the body"]}, "files": {f"Seed{suffix.upper()}": small, "ref.txt": "  from the file \n"}},
        {"bodies": {"seed": small.strip()}},
        {"options": {"seed": f"seed{other}"}, "files": {f"seed{other}": small}},
        {"options": {"tokens": ["?"]}},
        {"options": {"seed": f"missing{suffix}"}},
        {"options": {"tokens": ["t" * 61], "seed": f"missing{suffix}"}},
        {"options": {"seed": f"seed{suffix}", "reference": "empty.txt"}, "files": {f"seed{suffix}": small, "empty.txt": " \n"}},
    ]
    return {"kind": kind.NAME, "settings": {"people": {"item": item, "keys": keys, "files": {name: seed}}}, "cases": cases,
            "builds": [built(kind, b) for b in given]}


def made() -> dict[Path, str]:
    """Every fixture file of the kinds, by its path, as its text - made on a thread with a worker's stack,
    as the nested texts are checked in a lecture."""
    result: list = []
    old = threading.stack_size(STACK)
    try:
        thread = threading.Thread(target=lambda: result.append(_made()))
        thread.start()
        thread.join()
    finally:
        threading.stack_size(old)
    return result[0]


def _made() -> dict[Path, str]:
    files = {}
    for engine in KINDS:
        folder = ROOT / "kinds" / FOLDER[engine] / "tests"
        files[folder / f"{engine}-golden.json"] = golden(engine)
        files[folder / f"{engine}-safety.json"] = safety(engine)
        files[folder / f"{engine}-reference.json"] = reference(engine)
    files[ROOT / "kinds" / FOLDER["triples"] / "tests" / "triples.json"] = triples()
    return {path: json.dumps(data, ensure_ascii=True, indent=1) + "\n" for path, data in files.items()}


if __name__ == "__main__":
    stale = []
    for path, text in made().items():
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            stale.append(path)
            if "--check" not in sys.argv[1:]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
    print(("stale" if "--check" in sys.argv[1:] else "written") + ": " + (", ".join(p.name for p in stale) or "nothing"))
    sys.exit(1 if stale and "--check" in sys.argv[1:] else 0)
