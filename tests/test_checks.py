# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The checks in Python (texstage/checks) against the golden fixtures of today's engines in the browser
(tests/fixtures/checks, made by make.mjs from web/engines): every case's status, error, key, canonical
form, rows and summary as the browser's engine gave them - byte for byte, so that a game that goes on
across F1 keeps its keys and the class its groups (docs/architecture/activity-framework-plan.md, 4.3).
A case that differs on purpose, or by the engines' versions, is in KNOWN with its reason. And the checks'
words are the catalogs' (web/i18n); their safety; and what keeps the pool's processes alike - a copy of
an SQL database, a SPARQL seed's blank nodes numbered."""
from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from texstage import checks
from texstage.checks import common, texts

FIXTURES = Path(__file__).parent / "fixtures" / "checks"
WEB = Path(__file__).parent.parent / "src" / "texstage" / "web"
CANONICAL_MAX = 20_000                          # as make.mjs keeps them

# (engine, text, language) -> why the server's check gives another result than the browser's engine
KNOWN = {
    ("sparql", "SELECT * WHERE { SERVICE SILENT <http://127.0.0.1:9/sparql> { ?s ?p ?o } }", "en"):
        "refused now: the server never connects, SILENT or not (F0, Q1); the browser's build, which had no "
        "network, answered SILENT with an empty solution",
    ("sql", "SELECT load_extension('x')", "en"):
        "an error either way, in other words: sql.js has no load_extension, Python's SQLite refuses it",
    ("sql", "SELECT load_extension('x')", "de"): "as in English",
    ("sql", "SELECT '\ud800'", "en"):
        "a lone surrogate, which only a broken phone sends, is U+FFFD on the server (checks.evaluate), as it was "
        "in the browser's Oxigraph; sql.js gave SQLite its three bytes (WTF-8), read back as three U+FFFD",
    ("sql", "SELECT length('\ud800')", "en"): "the same: the length is 1 either way, the column's name differs",
    ("sql", "SELECT ?, :x", "en"):
        "an error: Python's sqlite3 binds parameters with names or without, not both in one statement (sql.py: "
        "_execute); sql.js left them all unbound, NULL",
}
# (engine, text) -> the error's words as a pattern, where they are SQLite's and depend on how it was built:
# the largest parameter number is 32766 in sql.js's and Python's own SQLite, 250000 in Debian's and Ubuntu's
BUILT = {
    ("sql", "SELECT ?0"): r"variable number must be between \?1 and \?\d+",
    ("sql", "SELECT ?99999999"): r"variable number must be between \?1 and \?\d+",
}


def expand(text) -> str:
    """A fixture's text, or {repeat: n, line}: n lines, {i} in each its number (make.mjs: expand)."""
    if isinstance(text, str):
        return text
    return "\n".join(text["line"].replace("{i}", str(i)) for i in range(text["repeat"]))


def record(result: dict) -> dict:
    """What a fixture keeps of a result (make.mjs: record)."""
    out = {"status": result["status"]}
    if "error" in result:
        out["error"] = result["error"]
    if "canonical" in result:
        out["key"] = result["key"]
        if common.utf16_len(result["canonical"]) <= CANONICAL_MAX:
            out["canonical"] = result["canonical"]
        else:
            out["canonical_length"] = common.utf16_len(result["canonical"])
    if "rows" in result and common.utf16_len(common.js_stringify(result["rows"])) <= CANONICAL_MAX:
        out["rows"] = result["rows"]
    if "summary" in result:
        out["summary"] = result["summary"]
    return out


def fixture(engine: str) -> dict:
    return json.loads((FIXTURES / f"{engine}.json").read_text(encoding="utf-8"))


def cases():
    for engine in checks.ENGINES:
        for i, case in enumerate(fixture(engine)["cases"]):
            text = case["text"] if isinstance(case["text"], str) else f"{case['text']['repeat']} lines"
            yield pytest.param(engine, i, id=f"{engine}-{i}-{case['language']}-{text[:40]}")


@functools.cache
def state(engine: str, seed: str):
    return checks.load(engine, fixture(engine)["seeds"][seed])


@pytest.mark.parametrize("engine, i", list(cases()))
def test_a_check_gives_what_the_browsers_engine_gave(engine, i):
    if engine != "sql":
        pytest.importorskip("pyoxigraph")
    case = fixture(engine)["cases"][i]
    text = expand(case["text"])
    got = record(checks.evaluate(engine, state(engine, case["seed"]), text, case["language"]))
    want = case["result"]
    written = case["text"] if isinstance(case["text"], str) else None
    if (engine, written, case["language"]) in KNOWN:
        assert got != want, "a known difference that is none any more: take it out of KNOWN"
        return
    if (engine, written) in BUILT:
        pattern = BUILT[(engine, written)]
        assert re.fullmatch(pattern, got.pop("error", "")) and re.fullmatch(pattern, (want := dict(want)).pop("error"))
    differences = {k: (got.get(k), want.get(k)) for k in set(got) | set(want) if got.get(k) != want.get(k)}
    assert not differences, json.dumps(differences, ensure_ascii=False, indent=1)[:3000]


def test_the_fixtures_cover_what_they_should():
    for engine in checks.ENGINES:
        statuses = {c["result"]["status"] for c in fixture(engine)["cases"]}
        assert {"ok", "syntax"} <= statuses, engine
        assert {c["language"] for c in fixture(engine)["cases"]} == {"en", "de"}, engine
    assert "refused" in {c["result"]["status"] for c in fixture("sql")["cases"]}
    assert "refused" in {c["result"]["status"] for c in fixture("sparql")["cases"]}


def test_the_checks_words_are_the_catalogs():
    node = shutil.which("node")
    if node is None:
        pytest.skip("no node")
    script = f"""
      const i18n = await import({json.dumps((WEB / "i18n" / "i18n.js").as_uri())});
      const out = {{}};
      for (const tag of ["en", "de"]) {{
        const W = i18n.texts(tag).engines;
        out[tag] = Object.fromEntries(Object.entries(W).filter(([, v]) => typeof v === "string"));
        out[tag].at = W.at("{{line}}", "{{column}}", "{{message}}");
        out[tag].tooManyTriples = W.tooManyTriples("{{n}}");
        out[tag].tooDeep = W.tooDeep("{{n}}");
      }}
      console.log(JSON.stringify(out));"""
    done = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True,
                          encoding="utf-8", check=True)
    catalogs = json.loads(done.stdout)
    for tag in ("en", "de"):
        for name, words in texts.ENGINES[tag].items():
            assert catalogs[tag][name] == words, (tag, name)


@pytest.mark.parametrize("x, js", [
    (0.0, "0"), (-0.0, "0"), (7.0, "7"), (100.0, "100"), (1e21, "1e+21"), (1e-7, "1e-7"), (1e-6, "0.000001"),
    (123.456, "123.456"), (2.5e-300, "2.5e-300"), (-1.5e-7, "-1.5e-7"), (9007199254740993.0, "9007199254740992"),
    (9.223372036854776e18, "9223372036854776000"), (1.7976931348623157e308, "1.7976931348623157e+308"),
    (5e-324, "5e-324"), (0.1 + 0.2, "0.30000000000000004"), (float("inf"), "Infinity"), (float("nan"), "NaN"),
])
def test_numbers_as_javascript_writes_them(x, js):
    assert common.js_number(x) == js


def test_strings_lengths_and_order_as_javascript_has_them():
    assert common.js_quote('Ä"\\\n\t\x01\u2028😀') == '"Ä\\"\\\\\\n\\t\\u0001\u2028😀"'
    assert common.utf16_len("😀a") == 3
    assert common.js_sorted(["ﬀ", "𝔸", "Z", "a"]) == ["Z", "a", "𝔸", "ﬀ"]        # UTF-16: a surrogate < U+FB00
    assert common.cut("😀" * 70).endswith("…") and common.utf16_len(common.cut("😀" * 70)) == 120
    assert common.key("") == "cbf29ce484222325" and common.key("a") == "af63dc4c8601ec8c"


def test_the_quick_string_functions_are_the_plain_ones():
    """utf16_len, cut, js_quote, js_sorted and key go by regular expressions and Python's own order, for
    values of megabytes; on random strings - surrogates, astral characters, controls - they give what the
    plain loops over characters give."""
    import random

    def utf16_len(s):
        return len(s) + sum(1 for c in s if ord(c) > 0xFFFF)

    def cut(s):
        if utf16_len(s) <= common.CELL:
            return s
        return s.encode("utf-16-le", "surrogatepass")[: (common.CELL - 1) * 2].decode("utf-16-le", "surrogatepass") + "…"

    def js_quote(s):
        out = []
        for c in s:
            o = ord(c)
            out.append(common._ESCAPES.get(c) or (f"\\u{o:04x}" if o < 0x20 or 0xD800 <= o <= 0xDFFF else c))
        return '"' + "".join(out) + '"'

    def key(s):
        h = 0xCBF29CE484222325
        for byte in common.well_formed(s).encode("utf-8"):
            h = ((h ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        return f"{h:016x}"

    rng = random.Random(3)
    pool = ["a", "Z", " ", '"', "\\", "\n", "\t", "\x00", "\x1f", "\x7f", "é", "\u2028", chr(0xD800), chr(0xDFFF),
            chr(0xE000), chr(0xFFFF), chr(0x10000), chr(0x1F600), chr(0x10FFFF), "ﬀ"]
    strings = ["".join(rng.choice(pool) for _ in range(rng.choice([0, 1, 5, 59, 60, 61, 119, 120, 121, 300])))
               for _ in range(3000)]
    for s in strings:
        assert (common.utf16_len(s), common.cut(s), common.js_quote(s), common.key(s)) == \
            (utf16_len(s), cut(s), js_quote(s), key(s)), ascii(s)
    assert common.js_sorted(strings) == sorted(strings, key=lambda s: s.encode("utf-16-be", "surrogatepass"))
    ascii_only = [s.encode("ascii", "ignore").decode() for s in strings]
    assert common.js_sorted(ascii_only) == sorted(ascii_only, key=lambda s: s.encode("utf-16-be", "surrogatepass"))


def test_texts_as_the_browser_handed_them_to_its_engines():
    assert common.well_formed("a\ud800b") == "a\ufffdb"                    # TextEncoder: a lone surrogate
    assert common.well_formed("😀") == "😀"                       # a pair is its character
    assert common.well_formed("\udc00\ud800") == "\ufffd\ufffd"
    assert common.key("\ud800") == common.key("\ufffd")
    assert common.nesting("{ ( [ ] ) } ((") == 3 and common.nesting(")))(") == 1


# ------------------------------------------------------------------ the checks' safety (plan 4.4)
SQL_SEED = "CREATE TABLE t (a INTEGER, b TEXT); INSERT INTO t VALUES (1, 'x'), (2, 'y');"
RDF_SEED = "@prefix : <http://e.org/> .\n:a :service :b ; :Service :c ; :SERVICE :d ; :p 'SERVICE' .\n"


def sql(state, text):
    r = checks.evaluate("sql", state, text, "en")
    return r["status"], r.get("error"), r.get("canonical")


def test_no_sql_text_changes_the_database_or_the_connection_for_the_texts_after_it():
    """SQLite carries out many pragmas as it compiles them - query_only = OFF among them, behind EXPLAIN
    too -, and sql.js compiled every statement to count them: in the browser, until 2026-11-09, these
    texts made the database writable, and a WITH ... DELETE then emptied it for every text after it. Both
    checks now refuse a text with the keyword PRAGMA before anything is compiled; on the server, the
    authorizer makes a pragma compile to nothing besides - the second guard, tried here on its own."""
    state = checks.load("sql", SQL_SEED)
    state["con"].execute("PRAGMA query_only = OFF")                   # as a text's compiling would
    assert sql(state, "WITH x AS (SELECT 1) DELETE FROM t")[:2] == ("refused", texts.ENGINES["en"]["changesData"])
    for text in ["PRAGMA query_only = OFF", "EXPLAIN PRAGMA query_only = OFF", "SELECT 1; PRAGMA query_only = OFF",
                 "PRAGMA query_only = OFF; SELECT 1", "PRAGMA case_sensitive_like = ON", "PRAGMA writable_schema = ON",
                 "PRAGMA temp_store = FILE", "PRAGMA recursive_triggers = ON"]:
        assert sql(state, text)[0] == "refused", text
        assert sql(state, "WITH x AS (SELECT 1) DELETE FROM t")[:2] == ("refused", texts.ENGINES["en"]["changesData"])
        assert sql(state, "SELECT count(*) FROM t")[2] == "select\n1\nn:2", text
        assert sql(state, "SELECT 'a' LIKE 'A'")[2] == "select\n1\nn:1", text
        assert sql(state, "SELECT * FROM pragma_query_only")[2] == "select\n1\nn:1", text
        assert sql(state, "SELECT * FROM pragma_temp_store")[2] == "select\n1\nn:2", text   # MEMORY


def test_no_sql_text_reaches_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = checks.load("sql", SQL_SEED)
    for text in ["ATTACH DATABASE 'a.db' AS a", "VACUUM INTO 'b.db'", "SELECT 1; ATTACH 'c.db' AS c",
                 "SELECT load_extension('d')"]:
        assert sql(state, text)[0] in ("refused", "error"), text
    assert sql(state, "SELECT * FROM a.t")[:2] == ("error", "no such table: a.t")
    assert list(tmp_path.iterdir()) == []


def test_a_sort_beyond_sqlites_cap_fails_in_memory_without_a_temporary_file(tmp_path):
    """temp_store = MEMORY: past the heap's cap a sort is out of memory - with SQLite's default storage it
    went on in temporary files (F0's review). In a process of its own: the cap holds for all of a
    process's SQLite connections, and only goes down."""
    script = """if True:
        from texstage import checks
        state = checks.load("sql", "CREATE TABLE t (a);", heap_allowance=64 * 2**20)
        r = checks.evaluate("sql", state, "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r "
                            "LIMIT 3000000) SELECT printf('%.100c', 'x') || n AS s FROM r ORDER BY s", "en")
        print(r["status"], "|", r.get("error"))"""
    env = dict(os.environ, TMP=str(tmp_path), TEMP=str(tmp_path), TMPDIR=str(tmp_path), SQLITE_TMPDIR=str(tmp_path))
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=300)
    assert done.stdout.strip() == "error | " + texts.ENGINES["en"]["tooMuchMemory"], done.stdout + done.stderr
    assert list(tmp_path.iterdir()) == []


def test_without_sqlites_own_function_the_first_seed_sets_the_cap_and_keeps_it():
    """Where ctypes cannot reach the SQLite Python runs on, PRAGMA hard_heap_limit - which only lowers it -
    is set by the first seed alone: a smaller one after it no longer sets it below what the first holds
    (the second review). In a process of its own, as the cap is the process's."""
    script = """if True:
        from texstage import checks
        from texstage.checks import sql
        sql._HEAP[:] = [None]
        big = checks.load("sql", "CREATE TABLE t (x); INSERT INTO t VALUES (zeroblob(40000000));",
                          heap_allowance=4 * 2**20)
        checks.load("sql", "CREATE TABLE u (y);", heap_allowance=4 * 2**20)
        print(checks.evaluate("sql", big, "SELECT length(x) FROM t", "en")["status"])"""
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert done.stdout.strip() == "ok", done.stdout + done.stderr


# ------------------------------------------------------------------ alike on every process of the pool (2026-11-10)
RANDOM_SEED = ("PRAGMA case_sensitive_like = ON; CREATE TABLE t (r INTEGER, b BLOB, at REAL, name TEXT);"
               " WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n LIMIT 50) INSERT INTO t SELECT"
               " random(), randomblob(8), julianday('now'), CASE i % 2 WHEN 0 THEN 'apple' ELSE 'Apple' END FROM n;")


def test_a_copy_of_an_sql_database_checks_as_the_run_it_was_made_from():
    """The pool's other processes load a copy of what the first one's run of the seed left: random(),
    randomblob() and the time alike - and the seed's PRAGMA statements, which hold for their connection,
    not its database: LIKE takes the case into account on the copy too. Read-only, as the run is."""
    from texstage.checks import sql as engine
    run = checks.load("sql", RANDOM_SEED)
    copy = checks.load("sql", RANDOM_SEED, image=engine.image(run, 2**20))
    for text in ["SELECT * FROM t", "SELECT count(*) FROM t WHERE name LIKE 'a%'"]:
        assert sql(copy, text) == sql(run, text), text
    assert sql(checks.load("sql", RANDOM_SEED), "SELECT * FROM t") != sql(run, "SELECT * FROM t")   # a run's own
    assert sql(copy, "SELECT count(*) FROM t WHERE name LIKE 'a%'")[2] == "select\n1\nn:25"
    assert sql(copy, "DELETE FROM t")[0] == "refused" and sql(copy, "SELECT count(*) FROM t")[2] == "select\n1\nn:50"
    assert sql(copy, "PRAGMA query_only = OFF")[0] == "refused" and sql(copy, "DELETE FROM t")[0] == "refused"


def test_a_seeds_temp_tables_are_there_for_the_texts():
    """temp_store = MEMORY, set after the seed until 2026-11-10, dropped the seed's TEMP tables - SQLite drops
    them as the setting changes -, which the browser kept. A seed that sets another storage loses them still:
    the texts' storage is in memory."""
    state = checks.load("sql", "CREATE TEMP TABLE w (x); INSERT INTO w VALUES (1), (2); CREATE TEMP VIEW v AS SELECT 3;")
    assert sql(state, "SELECT count(*) FROM w")[2] == "select\n1\nn:2" and sql(state, "SELECT * FROM v")[2] == "select\n1\nn:3"
    assert sql(state, "SELECT * FROM pragma_temp_store")[2] == "select\n1\nn:2"
    state = checks.load("sql", "PRAGMA temp_store = FILE; CREATE TEMP TABLE w (x);")
    assert sql(state, "SELECT * FROM pragma_temp_store")[2] == "select\n1\nn:2"


@pytest.mark.parametrize("seed", [
    "CREATE TEMP TABLE w (x); CREATE TABLE m (y);",
    "CREATE TABLE m (y); CREATE TEMP VIEW v AS SELECT * FROM m;",
    "ATTACH ':memory:' AS aux; CREATE TABLE aux.n (z); CREATE TABLE m (y);",
])
def test_a_seed_that_made_more_than_its_database_has_no_copy(seed):
    """A copy of the main database would lack it: every process runs such a seed itself."""
    from texstage.checks import sql as engine
    assert engine.image(checks.load("sql", seed), 2**20) is None


def test_a_database_larger_than_a_copy_may_be_has_none():
    from texstage.checks import sql as engine
    state = checks.load("sql", SQL_SEED)
    assert engine.image(state, state["size"] - 1) is None and len(engine.image(state, state["size"])) == state["size"]


def test_a_copy_is_made_past_sqlites_cap_and_the_cap_is_back_after():
    """A database larger than what its cap leaves free: SQLite needs as much again for the copy, so the cap
    is lifted while it is made - and is what it was after. In a process of its own, as the cap is the
    process's."""
    script = """if True:
        from texstage import checks
        from texstage.checks import sql
        seed = "CREATE TABLE t (x); INSERT INTO t VALUES (zeroblob(40000000));"
        run = checks.load("sql", seed, heap_allowance=4 * 2**20)
        if sql._HEAP[0] is None:
            print("no ctypes")
            raise SystemExit
        cap = sql._HEAP[0][0](-1)
        data = sql.image(run, 2**30)
        print(data is not None and len(data) > 40000000, sql._HEAP[0][0](-1) == cap)
        del run
        copy = checks.load("sql", seed, heap_allowance=4 * 2**20, image=data)
        print(checks.evaluate("sql", copy, "SELECT length(x) FROM t", "en")["summary"]["rows"])"""
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    if done.stdout.strip() == "no ctypes":
        pytest.skip("ctypes does not reach the SQLite Python runs on")
    assert done.stdout.split("\n")[:2] == ["True True", "[['40000000']]"], done.stdout + done.stderr


def test_a_sparql_seeds_blank_nodes_are_alike_in_every_load():
    """pyoxigraph gives each blank node a random id as it reads it: ordered by them and cut by a LIMIT, a
    result came out differently on the pool's processes - four keys in five (2026-11-10). Numbered in the
    order the seed has them, they are alike in every load."""
    pytest.importorskip("pyoxigraph")
    seed = ("@prefix : <http://e.org/> .\n_:alice :name 'Alice' ; :knows _:bob . _:bob :name 'Bob' .\n"
            "[ :name 'Dave' ] . [ :name 'Eve' ] . :x :list ( 1 2 3 ) . :y :name 'Yves' .\n")
    queries = ["SELECT * WHERE { ?s ?p ?o } LIMIT 3", "SELECT ?n WHERE { ?p :name ?n } ORDER BY ?p LIMIT 2",
               "SELECT (GROUP_CONCAT(?n) AS ?all) WHERE { ?p :name ?n }"]
    keys = {tuple(checks.evaluate("sparql", checks.load("sparql", seed), q, "en")["key"] for q in queries)
            for _ in range(8)}
    assert len(keys) == 1


@functools.cache
def rdf_state(engine: str):
    pytest.importorskip("pyoxigraph")
    return checks.load(engine, RDF_SEED)


@pytest.mark.parametrize("text", [
    "SELECT * WHERE { SERVICE <http://127.0.0.1:9/sparql> { ?s ?p ?o } }",
    "select * where { service <http://127.0.0.1:9/sparql> { ?s ?p ?o } }",
    "SELECT * WHERE { SeRvIcE SILENT <http://127.0.0.1:9/sparql> { ?s ?p ?o } }",
    "SELECT * WHERE { ?s ?p ?o . SERVICE ?endpoint { ?s ?p ?o } }",
    "SELECT * WHERE { # a comment\nSERVICE <http://127.0.0.1:9/sparql> { ?s ?p ?o } }",
    "SELECT * WHERE { \\u0053ERVICE <http://127.0.0.1:9/sparql> { ?s ?p ?o } }",
    "SELECT * WHERE { \\U00000053ervice <http://127.0.0.1:9/sparql> { ?s ?p ?o } }",
    "SELECT * WHERE { { SELECT * WHERE { SERVICE <http://127.0.0.1:9/sparql> { ?s ?p ?o } } } }",
])
def test_service_is_refused_in_every_spelling(text):
    r = checks.evaluate("sparql", rdf_state("sparql"), text, "en")
    assert (r["status"], r.get("error")) == ("refused", texts.ENGINES["en"]["service"])


@pytest.mark.parametrize("text", [
    "SELECT ?service WHERE { ?service ?p ?o }", "SELECT $service WHERE { $service ?p ?o }",
    "SELECT * WHERE { ?s :service ?o }", "PREFIX ex: <http://e.org/> SELECT * WHERE { ?s ex:Service ?o }",
    "PREFIX service: <http://e.org/> SELECT * WHERE { ?s service:p ?o }",
    "SELECT * WHERE { ?s ?p 'SERVICE' }", 'SELECT * WHERE { ?s ?p """SERVICE""" }',
    "SELECT * WHERE { ?s ?p ?o } # SERVICE <http://127.0.0.1:9/sparql>",
    "SELECT * WHERE { ?s <http://e.org/SERVICE> ?o }",
])
def test_names_strings_and_comments_that_say_service_are_no_service(text):
    r = checks.evaluate("sparql", rdf_state("sparql"), text, "en")
    assert r["status"] == "ok" and r["summary"]["count"] >= 1, r


def deep(engine: str, n: int) -> str:
    """A text n levels deep: groups in SPARQL, blank nodes in Turtle."""
    if engine == "sparql":
        return "SELECT * WHERE " + "{ " * n + "?s ?p ?o " + "} " * n
    return ":a :p " + "[ :q " * n + ":b" + " ]" * n + " ."


@pytest.mark.parametrize("engine", ["sparql", "turtle"])
def test_nesting_beyond_the_cap_is_a_syntax_error_before_any_parser(engine):
    r = checks.evaluate(engine, rdf_state(engine), deep(engine, 5000), "en")    # the default stack ends at 800
    assert (r["status"], r.get("error")) == ("syntax", f"nested more than {common.NESTING_MAX} levels deep")


@pytest.mark.parametrize("engine", ["sparql", "turtle"])
def test_nesting_up_to_the_cap_is_checked_on_a_thread_with_a_workers_stack(engine):
    """A worker checks on a thread with a 64 MB stack (F0, Q3) - here on Linux and macOS too."""
    state, result = rdf_state(engine), {}
    old = threading.stack_size(64 * 2**20)
    try:
        t = threading.Thread(target=lambda: result.update(
            checks.evaluate(engine, state, deep(engine, common.NESTING_MAX), "en")))
        t.start()
        t.join()
    finally:
        threading.stack_size(old)
    assert result["status"] == "ok", result
