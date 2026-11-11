# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Today's four kinds as classes of the contract (texstage/activities/kind.py; the packages in kinds/;
docs/architecture/activity-framework-plan-f2.md, packages 1 and 2): what they give is
what F1 gives - F1's golden fixtures through their checks, byte for byte; their build what the
build's activity module makes of the same record; a tuple's key and literals the activity type's; a
check's outcome, and the first worker's preparing, a worker's of F1's pool. What the cleaning itself
does is tests/test_cleaning.py's: here the kinds and the activity type are only shown to clean alike.
The contract's own rules - what a check must keep, the options' types, the registry, the kit - are
tests/test_contract.py's and tests/test_kit.py's. Where the kinds' packages are not installed, this test
puts their sources on the path."""
from __future__ import annotations

import dataclasses
import functools
import sqlite3
import sys
import time
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KINDS = ROOT / "kinds"
if not any(KINDS.glob("*/src")):                       # texstage's source archive has its tests, not the kinds
    pytest.skip("the kinds' packages are not here", allow_module_level=True)
for src in sorted(KINDS.glob("*/src")):
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

import test_checks as f1  # noqa: E402 - the fixtures, and how a record is held against them
from texstage_kinds_rdf import SparqlQuery, Triples, TurtleGraph  # noqa: E402
from texstage_kinds_sql import SqlQuery  # noqa: E402

import texstage.activities  # noqa: E402
from texstage import checks  # noqa: E402
from texstage.activities import kind as contract  # noqa: E402
import texstage.activities.options as option_types  # noqa: E402
from texstage.activities.code import CodeKind, words  # noqa: E402
from texstage.activities.kind import Entry, Message, Prepared, Step, Unbuildable, Unfit  # noqa: E402
from texstage.activities.options import Int, Options  # noqa: E402
from texstage.build import activity as build  # noqa: E402
from texstage.build.tqz import Tqz  # noqa: E402
from texstage.checks import common  # noqa: E402
from texstage.checks import sql as f1_sql  # noqa: E402
from texstage.engines import ENGINES  # noqa: E402
from texstage.server.types import Refused  # noqa: E402, I001 - before the activity type: types imports it
from texstage.server import activity as today  # noqa: E402
from texstage.server import pool, worker  # noqa: E402

CODE = {"sql": SqlQuery(), "sparql": SparqlQuery(), "turtle": TurtleGraph()}
ALL = [*CODE.values(), Triples()]
TO_F1 = {v: k for k, v in contract.FROM_F1.items()}


def needs(engine: str):
    if engine != "sql":
        pytest.importorskip("pyoxigraph")


def sqlites_cap() -> int:
    con = sqlite3.connect(":memory:")
    try:
        return con.execute("PRAGMA hard_heap_limit").fetchone()[0]
    finally:
        con.close()


@pytest.fixture(autouse=True, scope="module")
def sqlites_cap_stays():
    """SQLite's cap on its memory is the whole process's: a seed loaded here with an allowance would set it
    for every test after (the review of package 1: 96 MB) - such loads belong in a process of their own."""
    before = sqlites_cap()
    yield
    assert sqlites_cap() == before, "a test of this file set SQLite's memory cap for the whole test run"


@functools.cache
def prepared(engine: str, seed: str) -> Prepared:
    """A fixture's seed prepared once, as a worker does - through the bundle's file, as its item names it."""
    text = f1.fixture(engine)["seeds"][seed]
    return CODE[engine].prepare({"seed": "data/seed"}, {}, {"data/seed": text.encode("utf-8")})


def record(check, language: str | None = "en") -> dict:
    """What a fixture keeps of a result (test_checks.record), from a kind's check - its message in the
    words F1's check had for it."""
    out = {"status": TO_F1.get(check.status, check.status)}
    if check.message is not None:
        out["error"] = words(check.message, language)
    if check.canonical is not None:
        out["key"] = check.key
        if common.utf16_len(check.canonical) <= f1.CANONICAL_MAX:
            out["canonical"] = check.canonical
        else:
            out["canonical_length"] = common.utf16_len(check.canonical)
    if check.rows is not None and common.utf16_len(common.js_stringify(check.rows)) <= f1.CANONICAL_MAX:
        out["rows"] = check.rows
    if check.detail is not None:
        out["summary"] = check.detail
    return out


def through(engine: str, case: dict):
    return CODE[engine].check(prepared(engine, case["seed"]), Step({}, language=case["language"]),
                              Entry(text=f1.expand(case["text"])))


def outcome(check) -> dict:
    """A check as the outcome a worker of F1's pool sends (server/worker.py: _outcome)."""
    out = {"status": TO_F1.get(check.status, check.status)}
    if check.message:
        out["error"] = words(check.message, "en")
    if check.status == "ok":
        out["key"], out["summary"] = check.key, check.detail
    return out


# ------------------------------------------------------------------ the golden fixtures
@pytest.mark.parametrize("engine, i", list(f1.cases()))
def test_f1s_golden_fixtures_pass_through_the_kinds(engine, i):
    needs(engine)
    case = f1.fixture(engine)["cases"][i]
    check = through(engine, case)
    assert check.status in contract.STATUSES and check.status != "internal"
    assert (check.key is not None) == (check.status == "ok")
    assert check.verdict is None and check.credit is None and check.parts is None    # none of the three judges
    assert contract.fault(CODE[engine], check) is None
    f1.agrees(engine, case, record(check, case["language"]))


@pytest.mark.parametrize("engine", list(CODE))
def test_a_check_leaves_what_was_prepared_as_it_found_it(engine):
    """The fixtures again in the other order, on the same prepared seeds: every record as before (the kit
    will run a kind's fixtures twice, in both orders - the design's 7.1)."""
    needs(engine)
    cases = f1.fixture(engine)["cases"]
    once = [record(through(engine, c), c["language"]) for c in cases]
    again = [record(through(engine, c), c["language"]) for c in reversed(cases)]
    assert again == once[::-1]


@pytest.mark.parametrize("engine", list(CODE))
def test_a_check_is_what_a_worker_of_f1s_pool_sends(engine):
    """The references first, compared with none; then every text against the first reference's rows -
    status, error, key and summary with its diff, as server/worker.py makes an outcome."""
    needs(engine)
    kind, fixture = CODE[engine], f1.fixture(engine)
    for seed, text in fixture["seeds"].items():
        cases = [c for c in fixture["cases"] if c["seed"] == seed and c["language"] == "en"]
        good = [f1.expand(c["text"]) for c in cases if c["result"]["status"] == "ok"][:2]
        bad = [f1.expand(c["text"]) for c in cases if c["result"]["status"] != "ok"][:1]
        if not good:
            continue
        references = bad + good                      # a reference that fails, then two that give a result
        state, module = checks.load(engine, text), kind.engine
        mine = kind.prepare({"seed": "s"}, {}, {"s": text.encode("utf-8")})
        step = Step({"seed": "s"}, {"reference": references}, "en", 5.0)
        rows, wanted = None, []
        for r in references:
            result, end = worker._evaluate(module, state, r, "en", 5.0)
            wanted.append(worker._outcome(result, None, end))
            if rows is None and result["status"] == "ok":
                rows = result["rows"]
        assert [outcome(c) for c in contract.referenced(kind, mine, step)] == wanted
        assert mine.rows == rows == checks.evaluate(engine, state, good[0])["rows"]
        for c in cases:
            result, end = worker._evaluate(module, state, f1.expand(c["text"]), "en", 5.0)
            want = worker._outcome(result, rows, end)
            got = outcome(kind.check(mine, step, Entry(text=f1.expand(c["text"]))))
            assert got == want, c["text"]
            if want["status"] == "ok":
                assert set(want["summary"]["diff"]) == {"common", "missing", "extra"}


def test_a_text_over_its_budget_is_a_timeout_without_a_key():
    """A text that counts to thirty million: it ends by itself, so that a check that gives the engine no
    budget fails here instead of never coming back."""
    kind = SqlQuery()
    mine = kind.prepare({"seed": "s"}, {}, {"s": b"CREATE TABLE t(x); INSERT INTO t VALUES (1);"})
    runaway = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c LIMIT 30000000) "
               "SELECT count(*) FROM c")
    started = time.perf_counter()
    check = kind.check(mine, Step({}, budget_s=0.05), Entry(text=runaway))
    assert (check.status, check.key, check.detail, check.message) == ("timeout", None, None, None)
    assert time.perf_counter() - started < 2.0
    assert kind.check(mine, Step({}, budget_s=5.0), Entry(text="SELECT x FROM t")).status == "ok"   # and the seed is whole


# ------------------------------------------------------------------ where an error is
@pytest.mark.parametrize("engine, text, line", [
    ("sparql", "SELECT ?s WHERE {\n  ?s ?p ?o\n", 3),            # the brace not closed: where the text ends
    ("sparql", "SELECT ?s\nWHERE { ?s ?p }", 2),
    ("turtle", "ex:a ex:b ex:c .\nex:a ex:b .", 2),
])
def test_a_syntax_error_says_where_in_the_students_text(engine, text, line):
    """Line and column, apart from the words - the seed's two prefixes, which the check puts in front of the
    text, not counted."""
    needs(engine)
    seed = "@prefix ex: <http://example.org/> .\n@prefix foaf: <http://xmlns.com/foaf/0.1/> .\nex:a ex:b ex:c .\n"
    kind = CODE[engine]
    mine = kind.prepare({"seed": "s"}, {}, {"s": seed.encode()})
    check = kind.check(mine, Step({}, language="en"), Entry(text=text))
    assert check.status == "invalid" and check.at is not None, check
    assert check.at[0] == line and check.at[1] >= 1
    assert check.message.code == "at" and set(check.message.args) == {"line", "column", "message"}
    assert (check.message.args["line"], check.message.args["column"]) == check.at       # numbers both
    assert words(check.message, "en").startswith(f"line {check.at[0]}, column {check.at[1]}: ")
    german = kind.check(mine, Step({}, language="de"), Entry(text=text))
    assert german.at == check.at and german.message == check.message          # a message has no language
    assert words(german.message, "de").startswith(f"Zeile {line}, Spalte {check.at[1]}: ")


def test_a_place_counts_from_one_in_characters():
    """Behind two emoji - two characters, four of a phone's UTF-16 units - the column is the character's."""
    needs("sparql")
    seed = b"@prefix ex: <http://example.org/> .\nex:a ex:b ex:c .\n"
    turtle, text = TurtleGraph(), 'ex:a ex:b "\U0001f600\U0001f600" x .'
    check = turtle.check(turtle.prepare({"seed": "s"}, {}, {"s": seed}), Step({}), Entry(text=text))
    assert check.at == (1, text.index(" x .") + 2) == (1, 16)
    sparql, text = SparqlQuery(), 'SELECT * WHERE { ?s ?p "\U0001f600\U0001f600" x }'
    check = sparql.check(sparql.prepare({"seed": "s"}, {}, {"s": seed}), Step({}), Entry(text=text))
    assert check.at == (1, len(text) + 1) == (1, 32)                # where the text ends


def test_an_error_without_a_place_has_none():
    """SQLite gives no position; a text refused before any parser has none either."""
    needs("sparql")
    sql = SqlQuery()
    check = sql.check(sql.prepare({"seed": "s"}, {}, {"s": b"CREATE TABLE t(x);"}), Step({}), Entry(text="SELEC x FROM t"))
    assert (check.status, check.at) == ("invalid", None) and check.message.code == "engine"     # SQLite's own words
    sparql = SparqlQuery()
    refused = sparql.check(sparql.prepare({"seed": "s"}, {}, {"s": b""}), Step({}),
                           Entry(text="SELECT * WHERE { SERVICE <http://example.org/> { ?s ?p ?o } }"))
    assert (refused.status, refused.at, refused.key) == ("refused", None, None)
    assert refused.message == Message("service") and words(refused.message, "de").startswith("SERVICE (eine Anfrage")


# ------------------------------------------------------------------ an engine in a check module's place
class Engine:
    """An engine for the tests: it does what `does` makes of a text, and keeps what its load and its
    checks were given."""

    def __init__(self, does):
        self.does, self.loads, self.budgets = does, [], []

    def load(self, seed, **options):
        self.loads.append((seed, options))
        return {"seed": seed}

    def evaluate(self, state, text, language=None, budget_s=None):
        self.budgets.append(budget_s)
        return self.does(text)


def kind_with(monkeypatch, does) -> CodeKind:
    monkeypatch.setitem(sys.modules, "an_engine_of_the_tests", Engine(does))

    class Some(CodeKind):
        NAME = "some"
        MODULE = "an_engine_of_the_tests"

    return Some()


def a_result(text):
    return {"status": "ok", "canonical": "select\n1\n" + text, "rows": [text], "summary": {"kind": "select", "count": 1}}


def test_whatever_an_engine_raises_is_the_texts_error_not_the_workers(monkeypatch):
    def does(text):
        if text == "memory":
            raise MemoryError
        if text == "words":
            raise RuntimeError("the first line\nand more")
        if text == "none":
            raise ValueError
        return {"status": "error", "error": "out of memory", "memory": True}

    kind = kind_with(monkeypatch, does)
    mine = kind.prepare({"seed": "s"}, {}, {"s": b"x"})
    got = {t: kind.check(mine, Step({}), Entry(text=t)) for t in ("memory", "words", "none", "said")}
    assert [(c.status, c.message, c.memory) for c in got.values()] == [
        ("error", Message("engine", {"text": t}), m) for t, m in (
            ("out of memory", True), ("the first line", False), ("ValueError", False),
            ("out of memory", True))]                            # (the last: the engine says so itself)
    assert all(c.key is None and c.detail is None and contract.fault(kind, c) is None for c in got.values())


def test_an_engines_long_words_are_cut_to_what_a_message_takes(monkeypatch):
    """SQLite names the token it stumbles on, and a token may have 2,000 characters."""
    kind = kind_with(monkeypatch, lambda text: {"status": "error", "error": "near " + "x" * 2000})
    check = kind.check(kind.prepare({"seed": "s"}, {}, {"s": b"x"}), Step({}), Entry(text="a"))
    assert check.message == Message("engine", {"text": ("near " + "x" * 2000)[:300]}) and contract.fault(kind, check) is None


def test_making_the_key_counts_against_the_budget(monkeypatch):
    kind = kind_with(monkeypatch, a_result)
    mine, ends, key = kind.prepare({"seed": "s"}, {}, {"s": b"x"}), [], common.key

    def late(canonical, end=None):
        ends.append(end)
        return None if end is not None else key(canonical)

    monkeypatch.setattr(common, "key", late)
    now = time.thread_time()
    check = kind.check(mine, Step({}, budget_s=2.0), Entry(text="a"))
    assert (check.status, check.key, check.rows, check.detail) == ("timeout", None, None, None)
    assert now + 1.5 < ends[0] <= time.thread_time() + 2.0      # the budget's end, not a new one for the key
    free = kind.check(mine, Step({}), Entry(text="a"))            # no budget: the build, the tests
    assert ends[1] is None and (free.status, free.key) == ("ok", key("select\n1\na"))


def test_the_references_have_a_budget_of_their_own(monkeypatch):
    """They are the lecturer's: F1's pool gives them ten seconds where a student's text has two."""
    kind = kind_with(monkeypatch, a_result)
    mine = kind.prepare({"seed": "s"}, {}, {"s": b"x"})
    step = Step({}, {"reference": ["a", "b"]}, budget_s=2.0)
    found = contract.referenced(kind, mine, step, budget_s=pool.REFERENCE_BUDGET_S)
    assert [c.status for c in found] == ["ok", "ok"] and mine.rows == ["a"]
    assert kind.engine.budgets == [10.0, 10.0] and step.budget_s == 2.0      # the step is as it was
    kind.check(mine, step, Entry(text="c"))
    contract.referenced(kind, Prepared(mine.state), step)
    assert kind.engine.budgets[2:] == [2.0, 2.0, 2.0]                       # without one: the step's


def test_an_entry_of_another_input_is_the_cores_fault_not_the_students(monkeypatch):
    """A check of an entry without what its kind checks raises - the core makes that an internal check -,
    where the engine's own failures are the text's error."""
    code, triples = kind_with(monkeypatch, a_result), Triples()
    mine = code.prepare({"seed": "s"}, {}, {"s": b"x"})
    for entry in (Entry(), Entry(fields=("a", "b", "c")), Entry(text=7)):
        with pytest.raises(TypeError, match="some checks a text"):
            code.check(mine, Step({}), entry)
    assert code.engine.budgets == []                               # no engine saw them
    step = Step({"fields": ["s", "p", "o"]})
    for entry in (Entry(), Entry(text="a b c"), Entry(fields="abc"), Entry(fields=["a", "b", "c"])):
        with pytest.raises(TypeError, match="triples checks fields"):
            triples.check(Prepared(), step, entry)


def test_an_entry_cannot_be_changed():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Entry(text="a").text = "b"
    assert Entry(text="a") == Entry(text="a") and hash(Entry(fields=("a", "b"))) == hash(Entry(fields=("a", "b")))


# ------------------------------------------------------------------ SQL: a copy of what prepare made
def test_sqlites_allowance_and_a_copy_reach_the_seeds_load(monkeypatch):
    seen = []
    monkeypatch.setattr(f1_sql, "load", lambda seed, **options: seen.append((seed, options)))
    kind, item, files = SqlQuery(), {"seed": "s"}, {"s": b"CREATE TABLE t(x);"}
    kind.prepare(item, {}, files)
    kind.prepare(item, {}, files, limits={})
    kind.prepare(item, {}, files, limits={"heap_allowance": 0})
    kind.prepare(item, {}, files, limits={"heap_allowance": 48 * 2**20})
    kind.prepare(item, {}, files, limits={"heap_allowance": 48 * 2**20}, copy=b"a database")
    assert seen == [("CREATE TABLE t(x);", o) for o in (
        {}, {}, {}, {"heap_allowance": 48 * 2**20}, {"heap_allowance": 48 * 2**20, "image": b"a database"})]


def test_a_copy_of_what_prepare_made_gives_every_worker_the_same_data():
    kind = SqlQuery()
    item, files = {"seed": "s"}, {"s": b"CREATE TABLE t(x); INSERT INTO t VALUES (random()), (random());"}
    run = kind.prepare(item, {}, files)                                # (no allowance here: sqlites_cap_stays)
    image = kind.copy(run, 2**20)
    assert isinstance(image, bytes) and image
    others = [kind.prepare(item, {}, files, copy=image) for _ in range(2)]
    keys = {kind.check(p, Step(item), Entry(text="SELECT x FROM t")).key for p in (run, *others)}
    assert len(keys) == 1 and None not in keys
    alone = kind.prepare(item, {}, files)                              # without the copy: other numbers
    assert kind.check(alone, Step(item), Entry(text="SELECT x FROM t")).key not in keys
    assert kind.copy(run, 16) is None                                  # larger than a copy may be
    assert all(k.copy(Prepared(), 2**20) is None for k in ALL if not isinstance(k, SqlQuery))


class Pipe:
    """A worker's end of its pipe, for server/worker.py's _prepare: what it sent."""

    def __init__(self):
        self.sent, self.data = [], []

    def send(self, message):
        self.sent.append(message)

    def send_bytes(self, data):
        self.data.append(data)


COUNTERS = ("SELECT total_changes()", "SELECT last_insert_rowid()", "SELECT changes()")


def test_the_first_worker_checks_on_the_copy_too_as_f1s_does():
    """A database that ran its seed counts the seed's changes, one loaded from a copy does not: the first
    worker lets go of its run and prepares from the copy, or one text has two keys (the review of package
    1; server/worker.py: _prepare does so since 2026-11-10)."""
    kind, item, seed = SqlQuery(), {"seed": "s"}, "CREATE TABLE t(x); INSERT INTO t VALUES (1), (2), (3);"
    files = {"s": seed.encode()}
    mine, image = contract.first(kind, item, {}, files, most=2**20)
    others = [kind.prepare(item, {}, files, copy=image) for _ in range(2)]
    pipe, states = Pipe(), {}
    worker._prepare(pipe, states, ("prepare", "act", 1, kind.MODULE, seed, [], None, "en", 5.0, {}, 2**20))
    module, state, _ = states["act"]
    assert len(pipe.data) == 1 and pipe.sent[-1][:4] == ("prepared", "act", 1, None)
    run = kind.prepare(item, {}, files)                                # the seed's own run, for the difference
    for text in (*COUNTERS, "SELECT x FROM t"):
        result, end = worker._evaluate(module, state, text, "en", 5.0)
        want = worker._outcome(result, None, end)
        got = [outcome(kind.check(p, Step(item, budget_s=5.0), Entry(text=text))) for p in (mine, *others)]
        assert got == [want] * 3, text
        differs = outcome(kind.check(run, Step(item, budget_s=5.0), Entry(text=text))) != want
        assert differs is (text in COUNTERS), text


def test_the_first_worker_without_a_copy_keeps_its_run(monkeypatch):
    needs("sparql")
    files = {"s": b"CREATE TABLE t(x); INSERT INTO t VALUES (1);"}
    sql = SqlQuery()
    for most in (None, 16):                                            # none asked for; larger than it may be
        mine, image = contract.first(sql, {"seed": "s"}, {}, files, most=most)
        assert image is None and sql.check(mine, Step({}), Entry(text="SELECT total_changes()")).rows == ["n:1"]
    mine, image = contract.first(SparqlQuery(), {"seed": "s"}, {}, {"s": b""}, most=2**20)     # a kind that has none
    assert image is None and mine.state is not None

    class Broken(SqlQuery):                                            # its copy does not load: every worker runs the seed
        def prepare(self, item, keys, files, limits=None, copy=None):
            if copy is not None:
                raise ValueError("the copy of its database: not a database")
            return super().prepare(item, keys, files, limits)

    mine, image = contract.first(Broken(), {"seed": "s"}, {}, files, most=2**20)
    assert image is None and sql.check(mine, Step({}), Entry(text="SELECT total_changes()")).rows == ["n:1"]


def test_a_seed_is_read_as_f1s_server_reads_it(tmp_path):
    """UTF-8, its line ends \\n, a byte order mark kept (server/checking.py: read_text)."""
    data = "\ufeffCREATE TABLE t(x);\r\nINSERT INTO t VALUES ('a\rb');\r\n".encode()
    assert data.startswith(b"\xef\xbb\xbf")
    (tmp_path / "seed.sql").write_bytes(data)
    read = SqlQuery().seed({"seed": "s"}, {"s": data})
    assert read == (tmp_path / "seed.sql").read_text(encoding="utf-8") and read.startswith("\ufeffCREATE") and "\r" not in read
    with pytest.raises(ValueError, match="the seed s: not in the bundle"):
        SqlQuery().seed({"seed": "s"}, {})
    with pytest.raises(ValueError, match="the seed s: not UTF-8") as e:
        SqlQuery().seed({"seed": "s"}, {"s": b"CREATE TABLE t(x); -- \xff\xfe"})
    assert not isinstance(e.value, UnicodeDecodeError)


# ------------------------------------------------------------------ the kinds' facts
def test_the_kinds_say_what_the_engines_table_and_the_build_say():
    for engine, kind in CODE.items():
        assert kind.ENGINE == engine and kind.MODULE == f"texstage.checks.{engine}"
        assert kind.SEED == ENGINES[engine]["seed"] and kind.TOKENS == ENGINES[engine]["tokens"]
        assert kind.TEXT == ENGINES[engine]["text"]
        assert (kind.INPUT, kind.REDUCTION, kind.LIMIT) == ("code", "groups", build.LIMITS["code"])
        assert kind.OPTIONS["seed"].suffixes == tuple(kind.SEED) and list(kind.OPTIONS) == ["tokens", "seed", "reference"]
    triples = Triples()
    assert (triples.INPUT, triples.REDUCTION, triples.LIMIT) == ("fields", "crowd", build.LIMITS["tuple"])
    assert (triples.FIELDS, triples.TERMS) == (build.FIELDS, build.TERMS)
    assert (option_types.WORD_MAX, option_types.WORDS_MAX) == (build.WORD_MAX, build.WORDS_MAX)
    assert {k.NAME for k in ALL} == {"sql-query", "sparql-query", "turtle-graph", "triples"}
    keys = {"fields", "suggest", "tokens", "min", "review", "terms", "seed", "reference"}      # a record's, that are a kind's
    assert all(k.API == 0 for k in ALL) and keys == set().union(*(k.OPTIONS for k in ALL))
    assert not keys & set(option_types.CORE)


def test_the_contracts_own_facts():
    assert contract.STATUSES == ("ok", "invalid", "error", "refused", "timeout", "internal")      # the design's 6.3
    assert contract.FROM_F1 == {"syntax": "invalid"}
    assert all(k.BUDGET_S == contract.BUDGET_S == pool.BUDGET_S == 1.0 for k in ALL)      # seconds, as a step's
    assert "{ " + " , ".join(option_types.PRESETS["fields"]) + " }" in (ROOT / "latex" / "texactivity.sty").read_text(
        encoding="utf-8")
    for kind in ALL:                                                # a kind's options are its own, and fixed
        with pytest.raises(TypeError):
            kind.OPTIONS["more"] = "words"
    assert Triples.OPTIONS is not CodeKind.OPTIONS and contract.Kind.OPTIONS == {}
    for name in ("Kind", "Built", "Prepared", "Check", "Entry", "Step", "Message", "Unbuildable", "Unfit", "fixed"):
        assert getattr(texstage.activities, name) is getattr(contract, name)      # as the design's 7.1 imports them


def test_each_package_names_its_kinds_as_entry_points():
    found = {}
    for path in sorted(KINDS.glob("*/pyproject.toml")):
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        assert project["version"] == "0.1.0" and "texstage" in project["dependencies"]
        for name, target in project["entry-points"]["texstage.kinds"].items():
            module, cls = target.split(":")
            assert (path.parent / "src" / module / "__init__.py").is_file()
            found[name] = getattr(sys.modules[module], cls)
    assert found == {k.NAME: type(k) for k in ALL}


def test_each_package_carries_its_licence():
    """The wheel of a package has what its pyproject.toml names: the repository's licence, and a notice."""
    paths = sorted(KINDS.glob("*/pyproject.toml"))
    assert len(paths) == 2
    for path in paths:
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        assert (project["license"], project["license-files"]) == ("Apache-2.0", ["LICENSE", "NOTICE"])
        assert (path.parent / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
        notice = (path.parent / "NOTICE").read_text(encoding="utf-8")
        assert notice.startswith(project["name"] + ",") and "Apache License 2.0" in notice and "texstage (Apache-2.0)" in notice


# ------------------------------------------------------------------ normalize: the activity type's cleaning
@pytest.mark.parametrize("text", ["SELECT 1", "  SELECT 1  \r\n\r\n", "\n\nSELECT\t1 \n FROM t \n\n", "a\x00b\x07c",
                                  "e\u0301", "", "   \n ", "x" * 2001, None, 7])
def test_a_text_is_cleaned_as_the_activity_type_cleans_it(text):
    """The kinds and the type clean alike - with one function; what it does: tests/test_cleaning.py."""
    for engine, kind in CODE.items():
        try:
            want = today.clean_code(text, ENGINES[engine]["text"])
        except Refused as e:
            with pytest.raises(Unfit) as mine:
                kind.normalize(Step({}), Entry(text=text))
            assert (str(mine.value), mine.value.code) == (str(e), e.code)
        else:
            assert kind.normalize(Step({}), Entry(text=text)) == Entry(text=want)


def test_the_bounds_of_an_entry():
    """A text of 2,000 characters, a field of 60 - one more is refused, with the code the phone has words for."""
    code, triples = SqlQuery(), Triples()
    step = Step({"fields": ["s", "p", "o"]})
    assert code.normalize(step, Entry(text="x" * 2000)).text == "x" * 2000
    with pytest.raises(Unfit, match="a query has 1 to 2000 characters") as e:
        code.normalize(step, Entry(text="x" * 2001))
    assert e.value.code == "text"
    with pytest.raises(Unfit, match="a Turtle text is text") as e:
        TurtleGraph().normalize(step, Entry(fields=("a", "b", "c")))
    assert e.value.code == "invalid"
    assert triples.normalize(step, Entry(fields=("a", "b", "c" * 60))).fields[2] == "c" * 60
    with pytest.raises(Unfit, match="every field has 1 to 60 characters") as e:
        triples.normalize(step, Entry(fields=("a", "b", "c" * 61)))
    assert e.value.code == "field"


def test_fields_are_a_list_of_the_right_length():
    """As the activity type takes them (player): a text, a dictionary, three characters of one string are none."""
    triples, step = Triples(), Step({"fields": ["s", "p", "o"]})
    for fields in (None, "abc", {"a": 1, "b": 2, "c": 3}, ("a", "b"), ["a", "b", "c", "d"], 3):
        with pytest.raises(Unfit, match="fields: 3 texts") as e:
            triples.normalize(step, Entry(fields=fields))
        assert e.value.code == "invalid"
    assert triples.normalize(step, Entry(fields=["a", " b ", "c"])) == Entry(fields=("a", "b", "c"))     # a list: a tuple
    with pytest.raises(Unfit, match="fields: 3 texts"):
        triples.normalize(step, Entry(text="a b c"))


TUPLES = [[":Kant", ":knows", ":Hume"], ["  \u201cKant\u201d@de ", "is  a", "\u2018Philosopher\u2019"], ["KANT", "Knows", "hume"],
          ["\u00dcn\u00efcode\x07", "x", "42"], ["a", "b", "true"], ["\u201eKant\u201c", "b", "3.14e2"], ["a", "", "c"],
          ["a", "b", "x" * 61], ["a", "b"], ["a", "b", "c", "d"], ["a", 5, "c"], ["\u200b", "b", "c"]]


@pytest.mark.parametrize("terms", ["exact", "loose", None])
@pytest.mark.parametrize("fields", TUPLES)
def test_a_tuple_is_cleaned_and_keyed_as_the_activity_type_does(fields, terms):
    """The key a contribution gets today (server/activity.py: player), and the nodes' literals (_crowd)."""
    kind = Triples()
    item = {"input": "tuple", "fields": ["Subject", "Predicate", "Object"], **({"terms": terms} if terms else {})}
    step = Step(item)
    try:
        if len(fields) != len(item["fields"]):
            raise Refused(f"fields: {len(item['fields'])} texts")
        cleaned = [today.clean_term(f) for f in fields]
    except Refused as e:
        with pytest.raises(Unfit) as mine:
            kind.normalize(step, Entry(fields=tuple(fields)))
        assert (str(mine.value), mine.value.code) == (str(e), e.code)
        return
    entry = kind.normalize(step, Entry(fields=tuple(fields)))
    assert entry == Entry(fields=tuple(cleaned)) and kind.normalize(step, entry) == entry
    check = kind.check(kind.prepare(item, {}, {}), step, entry)
    assert check.status == "ok" and check.key == "\x1f".join(today.term_key(f, item) for f in cleaned)
    assert check.parts == [{"key": today.term_key(f, item), "text": f, "literal": today.is_literal(f)} for f in cleaned]
    assert check.detail is None and check.rows is None and check.verdict is None


def test_tuples_that_differ_in_case_are_one_only_with_loose_terms():
    kind, a, b = Triples(), Entry(fields=("Kant", "knows", "Hume")), Entry(fields=("KANT ", "Knows", "hume"))
    for terms, same in (("exact", False), ("loose", True)):
        step = Step({"fields": ["s", "p", "o"], "terms": terms})
        keys = [kind.check(Prepared(), step, kind.normalize(step, e)).key for e in (a, b)]
        assert (keys[0] == keys[1]) is same
    assert kind.check(Prepared(), Step({"fields": ["s", "o"]}), Entry(fields=("Kant", "Hume"))).key == "Kant\x1fHume"


def test_a_literal_is_the_texts_not_the_keys():
    """With loose terms true and TRUE are one node, and only the first is written as a literal: a part says
    how its own text is written, and a node is a literal when its label is - the core's choice (_crowd)."""
    kind, step = Triples(), Step({"fields": ["s", "p", "o"], "terms": "loose"})
    parts = [kind.check(Prepared(), step, Entry(fields=("x", "is", text))).parts[2] for text in ("true", "TRUE")]
    assert [p["key"] for p in parts] == ["true", "true"] and [p["literal"] for p in parts] == [True, False]
    assert [p["text"] for p in parts] == ["true", "TRUE"]


# ------------------------------------------------------------------ the build
def hexed(text: str) -> str:
    return text.encode("utf-8").hex()


def listed(items) -> str:
    return "".join(hexed(x) + "," for x in items)


def tqz(tmp_path, a: dict) -> Tqz:
    """A build's record of one activity, as texactivity.sty writes it (build/activity.py: read)."""
    fields = ["act", a.get("input", "code"), a.get("engine", ""), listed(a.get("fields", [])),
              listed(a.get("suggest", [])), listed(a.get("tokens", [])), a.get("limit", ""), a.get("min", ""),
              "true" if a.get("review") else "false", a.get("open", ""), a.get("terms", ""),
              hexed(a.get("seed", "")), hexed(a.get("reference", "")), hexed("deck.tex"), "1"]
    records = ["activity|" + "|".join(fields)]
    records += [f"activityref|act|{hexed(r)}" for r in a.get("references", [])]
    if "body" in a:
        records.append(f"activityseed|act|{hexed(a['body'])}")
    path = tmp_path / "deck.tqz"
    path.write_text("\n".join(records) + "\n", encoding="utf-8")
    return Tqz.read(path)


def by_kind(tmp_path, a: build.Activity) -> tuple[dict, dict, dict, list[str]]:
    """What the core will do around a kind's build (package 7): the keys that are its own - input, limit,
    open -, the activity's name in front of a refusal, the keys the kind does not take as a warning."""
    kind = Triples() if a.input == "tuple" else CODE[a.engine]

    def files(name: str, what: str) -> str:
        path = tmp_path / name
        if not path.is_file():
            raise Unbuildable(f"the {what} {name} is not there (paths are the deck's)")
        return path.read_text(encoding="utf-8-sig")

    options = Options(kind.OPTIONS, {"fields": a.fields, "suggest": a.suggest, "tokens": a.tokens, "min": a.min,
                                     "review": a.review, "terms": a.terms, "seed": a.seed, "reference": a.reference_file},
                      files)
    bodies = {"seed": a.seed_text, "references": a.references}
    try:
        item = {"input": a.input, "limit": Int(build.LIMIT_MAX, kind.LIMIT).read("limit", a.limit, None)}
        built = kind.build(options, bodies)
    except Unbuildable as e:
        raise build.ActivityError(f"activity {a.id}: {e}") from None
    item.update(built.item)
    if a.open == "manual":
        item["open"] = "manual"
    extra = options.unused(bodies)
    return item, built.keys, built.files, [f"activity {a.id}: {', '.join(extra)} - not for input={a.input}"] if extra else []


SPO = ["Subject", "Predicate", "Object"]
SEED_TTL = "@prefix : <https://example.org/> .\n:ada :name \"Ada\" ."
MB2 = 2 * 2**20
BUILT, REFUSED = True, False
ACTIVITIES = {
    "sql, a seed file and a reference file": (BUILT, {"engine": "sql", "seed": "seed.sql", "reference": "ref.sql",
                                                      "tokens": ["SELECT", "*", "FROM"], "limit": "3", "open": "manual"}),
    "sparql, the seed and two references in the body": (BUILT, {
        "engine": "sparql", "body": SEED_TTL, "fields": SPO, "references": ["SELECT * WHERE { ?s ?p ?o }", "ASK { ?s ?p ?o }"]}),
    "turtle, no reference": (BUILT, {"engine": "turtle", "body": SEED_TTL}),
    "sql, a seed file in capitals": (BUILT, {"engine": "sql", "seed": "SEED.SQL"}),
    "a tuple with everything": (BUILT, {"input": "tuple", "fields": ["Who", "does", "What"], "suggest": [":Kant", ":Hume"],
                                        "min": "2", "review": True, "terms": "loose", "limit": "7"}),
    "a tuple of two fields, the defaults": (BUILT, {"input": "tuple", "fields": ["From", "To"]}),
    "a tuple with a query's keys": (BUILT, {"input": "tuple", "fields": SPO, "tokens": ["?"], "seed": "seed.sql",
                                            "references": ["SELECT 1"]}),
    "a tuple with a query's bodies": (BUILT, {"input": "tuple", "fields": SPO, "body": SEED_TTL, "reference": "ref.sql"}),
    "a query with a tuple's keys": (BUILT, {"engine": "sql", "seed": "seed.sql", "fields": ["a", "b"], "suggest": ["x"],
                                            "min": "3", "review": True, "terms": "loose"}),
    # the bounds themselves, and what comes first where a deck gives both
    "a tuple at its bounds": (BUILT, {"input": "tuple", "fields": ["a" * 60, "b", "c"], "min": "1000", "limit": "50",
                                      "suggest": [f"s{i}" for i in range(40)]}),
    "a query at its bounds": (BUILT, {"engine": "sql", "body": "-- " + "x" * (MB2 - 4), "references": ["x" * 2000],
                                      "tokens": [f"t{i}" for i in range(39)] + ["t" * 60]}),
    "a seed file and a seed in the body: the file": (BUILT, {"engine": "sql", "seed": "seed.sql", "body": "CREATE TABLE z(z);"}),
    "references in the body and a reference file: the file's last": (BUILT, {
        "engine": "sql", "seed": "seed.sql", "references": ["SELECT 1", "SELECT 2"], "reference": "ref.sql"}),
    # what cannot be built
    "a tuple of one field": (REFUSED, {"input": "tuple", "fields": ["One"]}),
    "a tuple of four fields": (REFUSED, {"input": "tuple", "fields": ["a", "b", "c", "d"]}),
    "a tuple, terms unknown": (REFUSED, {"input": "tuple", "fields": SPO, "terms": "fuzzy"}),
    "a tuple, min not a number": (REFUSED, {"input": "tuple", "fields": SPO, "min": "many"}),
    "a tuple, min too large": (REFUSED, {"input": "tuple", "fields": SPO, "min": "1001"}),
    "a tuple, min a superscript two": (REFUSED, {"input": "tuple", "fields": SPO, "min": "\u00b2"}),
    "a tuple, min an Arabic three": (REFUSED, {"input": "tuple", "fields": SPO, "min": "\u0663"}),
    "a tuple, a label too long": (REFUSED, {"input": "tuple", "fields": ["a", "b" * 61, "c"]}),
    "a tuple, too many suggestions": (REFUSED, {"input": "tuple", "fields": SPO, "suggest": [f"s{i}" for i in range(41)]}),
    "a tuple, an empty suggestion": (REFUSED, {"input": "tuple", "fields": SPO, "suggest": ["a", " "]}),
    "a limit of zero": (REFUSED, {"engine": "sql", "seed": "seed.sql", "limit": "0"}),
    "a limit too large": (REFUSED, {"input": "tuple", "fields": SPO, "limit": "51"}),
    "a limit a superscript two": (REFUSED, {"engine": "sql", "seed": "seed.sql", "limit": "\u00b2"}),
    "too many tokens": (REFUSED, {"engine": "sparql", "body": SEED_TTL, "tokens": [f"t{i}" for i in range(41)]}),
    "a token too long": (REFUSED, {"engine": "sparql", "body": SEED_TTL, "tokens": ["t" * 61]}),
    "a seed of another type": (REFUSED, {"engine": "sql", "seed": "seed.ttl"}),
    "a seed that is not there": (REFUSED, {"engine": "sparql", "seed": "missing.ttl"}),
    "no seed": (REFUSED, {"engine": "turtle"}),
    "a seed one byte too large": (REFUSED, {"engine": "sql", "body": "-- " + "x" * (MB2 - 3)}),
    "a reference too long": (REFUSED, {"engine": "sql", "seed": "seed.sql", "references": ["SELECT 1", "x" * 2001]}),
    "an empty reference file": (REFUSED, {"engine": "sql", "seed": "seed.sql", "reference": "empty.sql"}),
    "a reference file that is not there": (REFUSED, {"engine": "sql", "seed": "seed.sql", "reference": "missing.sql"}),
    # two faults at once: which one is said
    "a limit and the fields": (REFUSED, {"input": "tuple", "fields": ["One"], "limit": "0"}),
    "a label and a suggestion": (REFUSED, {"input": "tuple", "fields": ["a", "b" * 61, "c"], "suggest": ["s" * 61]}),
    "a suggestion and min": (REFUSED, {"input": "tuple", "fields": SPO, "suggest": ["s" * 61], "min": "many"}),
    "min and terms": (REFUSED, {"input": "tuple", "fields": SPO, "min": "many", "terms": "fuzzy"}),
    "the tokens and no seed": (REFUSED, {"engine": "turtle", "tokens": ["t" * 61]}),
    "the tokens and a seed of another type": (REFUSED, {"engine": "sql", "seed": "seed.ttl", "tokens": ["t" * 61]}),
    "a seed too large and a reference too long": (REFUSED, {"engine": "sql", "body": "-- " + "x" * MB2,
                                                            "references": ["x" * 2001]}),
    "a seed that is not there and a reference that is not": (REFUSED, {"engine": "sql", "seed": "missing.sql",
                                                                       "reference": "missing-too.sql"}),
}


@pytest.mark.parametrize("name", list(ACTIVITIES))
def test_a_kinds_build_is_what_the_build_makes_of_the_same_record(tmp_path, name):
    for file, text in (("seed.sql", "CREATE TABLE t(x);\nINSERT INTO t VALUES (1);\n"), ("SEED.SQL", "CREATE TABLE u(y);\n"),
                       ("seed.ttl", SEED_TTL), ("ref.sql", "\ufeffSELECT x FROM t\n\n"), ("empty.sql", " \n")):
        (tmp_path / file).write_text(text, encoding="utf-8")
    builds, activity = ACTIVITIES[name]
    records = tqz(tmp_path, activity)
    warnings: list[str] = []
    try:
        items, keys, files = build.entries(records, tmp_path, {}, warnings)
    except build.ActivityError as e:
        assert not builds, f"a record that should build: {e}"
        with pytest.raises(build.ActivityError) as mine:
            by_kind(tmp_path, build.read(records)["act"])
        assert str(mine.value) == str(e)
        return
    assert builds, "a record that should not build"
    item, mine_keys, mine_files, mine_warnings = by_kind(tmp_path, build.read(records)["act"])
    assert item == items["act"] and list(item) == list(items["act"])       # deck.json's entry, key for key
    assert mine_keys == keys.get("act", {}) and mine_files == files and mine_warnings == warnings


def test_what_the_build_makes_of_the_records_that_show_an_order(tmp_path):
    """The comparison above holds two sides against each other; these are written out."""
    (tmp_path / "seed.sql").write_text("CREATE TABLE t(x);\n", encoding="utf-8")
    (tmp_path / "ref.sql").write_text("SELECT x FROM t\n", encoding="utf-8")

    def built(name):
        return by_kind(tmp_path, build.read(tqz(tmp_path, ACTIVITIES[name][1]))["act"])

    item, keys, files, warnings = built("a seed file and a seed in the body: the file")
    assert list(files.values()) == [b"CREATE TABLE t(x);\n"] and warnings == []
    _, keys, _, _ = built("references in the body and a reference file: the file's last")
    assert keys == {"reference": ["SELECT 1", "SELECT 2", "SELECT x FROM t"]}
    item, _, files, _ = built("a query at its bounds")
    assert len(next(iter(files.values()))) == MB2 and len(item["tokens"]) == 40 + len(ENGINES["sql"]["tokens"])
    _, _, _, warnings = built("a tuple with a query's bodies")
    assert warnings == ["activity act: seed, reference - not for input=tuple"]
    for name, said in (("a limit and the fields", "limit=0 - a number from 1 to 50"),
                       ("a label and a suggestion", "fields= takes at most 40 items of 1 to 60 characters"),
                       ("a suggestion and min", "suggest= takes at most 40 items of 1 to 60 characters"),
                       ("min and terms", "min=many - a number from 1 to 1000"),
                       ("the tokens and no seed", "tokens= takes at most 40 items of 1 to 60 characters"),
                       ("a seed too large and a reference too long", "the seed has 2048 KB - at most 2 MB, which the "
                                                                    "presenter's browser loads"),
                       ("a tuple, min a superscript two", "min=\u00b2 - a number from 1 to 1000"),
                       ("a tuple, min an Arabic three", "min=\u0663 - a number from 1 to 1000")):
        with pytest.raises(build.ActivityError) as e:
            built(name)
        assert str(e.value) == f"activity act: {said}", name


def test_the_keys_a_kind_does_not_take():
    def unused(kind, given, bodies=None):
        return Options(kind.OPTIONS, given).unused(bodies)

    sql, triples = SqlQuery(), Triples()
    assert unused(sql, {"fields": list(option_types.PRESETS["fields"]), "tokens": ["?"], "seed": "s.sql"}) == []
    assert unused(sql, {"fields": ["a", "b"], "suggest": ["x"], "min": "2", "review": True, "terms": "loose"}) == [
        "fields", "suggest", "min", "review", "terms"]
    assert unused(sql, {"review": False, "min": "", "suggest": [], "terms": ""}, {"seed": "x", "references": ["y"]}) == []
    assert unused(triples, {"fields": ["a", "b"], "tokens": ["?"]}) == ["tokens"]
    assert unused(triples, {"seed": "", "reference": ""}, {"seed": "CREATE TABLE t(x);"}) == ["seed"]
    assert unused(triples, {"seed": "", "reference": ""}, {"references": ["SELECT 1"]}) == ["reference"]
    assert unused(triples, {"seed": "s.sql", "reference": "r.sql"}, {"seed": "", "references": []}) == ["seed", "reference"]
    assert unused(triples, {"limit": "3", "open": "manual", "id": "act"}) == []                 # the core's own keys
