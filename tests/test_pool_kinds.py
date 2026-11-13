# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The pool's processes prepare and check through the kinds (texstage/server/worker.py: _OfKind;
docs/architecture/activity-framework-plan-f2.md, package 6): an activity named "kind:<name>" has the
kind's prepare, its copy for every process, its references and its checks - what a check says there is
what the kind's check says here, held against the contract's rules."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KINDS = ROOT / "kinds"
if not any(KINDS.glob("*/src")):                       # texstage's source archive has its tests, not the kinds
    pytest.skip("the kinds' packages are not here", allow_module_level=True)
for src in sorted(KINDS.glob("*/src")):
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

from texstage.activities import kind as contract  # noqa: E402
from texstage.activities import registry  # noqa: E402
from texstage.activities.kind import Check, Entry, Kind, Message, Prepared, Step, fixed  # noqa: E402
from texstage.server import worker  # noqa: E402
from texstage.server.pool import Pool  # noqa: E402

SQL_SEED = ("CREATE TABLE packing (item TEXT, quantity INTEGER);"
            " INSERT INTO packing VALUES ('Apples', 6), ('Cups', 6), ('Blankets', 2);")
REFERENCE = "SELECT item FROM packing WHERE quantity = 6"
RUNAWAY = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT count(*) FROM r"
SQL = {"item": {"seed": "data/packing.sql"}, "keys": {"reference": ["SELEC x", REFERENCE]},
       "files": {"data/packing.sql": SQL_SEED.encode()}}
TRIPLES = {"item": {"fields": ["Subject", "Predicate", "Object"], "terms": "loose"}, "keys": {}, "files": {}}


def installed(name: str) -> Kind:
    try:
        return registry.kind(name)
    except LookupError:
        pytest.skip(f"the kind {name} is not installed: pip install --no-deps -e kinds/...")


@pytest.fixture(scope="module")
def pool():
    installed("sql-query")
    p = Pool(workers=2, spare=1, reference_budget_s=0.5).start()
    yield p
    p.close()


def sent(text: str) -> str:
    return json.dumps({"text": text})


def test_a_kinds_activity_is_prepared_and_checked_as_the_kind_does(pool):
    kind = installed("sql-query")
    outcomes = pool.prepare("packing", "kind:sql-query", SQL, SQL["keys"]["reference"], "en").result(60)
    mine, _ = contract.first(kind, SQL["item"], SQL["keys"], SQL["files"], most=2**20)
    step = Step(SQL["item"], SQL["keys"], "en", 1.0)
    assert outcomes == [c.sent() for c in contract.referenced(kind, mine, step)]
    assert [o["status"] for o in outcomes] == ["invalid", "ok"] and "diff" not in outcomes[1]["detail"]
    for text in ["select item from packing where quantity=6", "SELECT item FROM packing", "SELEC x",
                 "DELETE FROM packing", "SELECT 1; SELECT 2", "SELECT count(*) FROM packing"]:
        got = pool.submit("packing", sent(text), language="en").result(60)
        want = kind.check(mine, step, Entry(text=text)).sent()
        assert {k: got.get(k) for k in want} == want, text
        assert "rows" not in got and "canonical" not in got and "error" not in got       # the kind's words are codes
    right = pool.submit("packing", sent(REFERENCE)).result(60)
    assert right["detail"]["diff"] == {"common": 2, "missing": 0, "extra": 0}           # against the second reference


def test_every_process_has_the_kinds_copy_of_the_first_ones_run(pool):
    """random() in the seed: one run, copied - every process answers alike (the kind's copy)."""
    seed = dict(SQL, files={"data/packing.sql": b"CREATE TABLE r (x); INSERT INTO r VALUES (random());"}, keys={})
    pool.prepare("random", "kind:sql-query", seed, [], "en").result(60)
    assert pool.wait_ready(60)
    keys = {pool.submit("random", sent(f"SELECT x FROM r -- {i}")).result(60)["key"] for i in range(12)}
    assert len(keys) == 1


def test_a_text_that_runs_away_is_a_timeout(pool):
    pool.prepare("packing", "kind:sql-query", SQL, [], "en").result(60)
    assert pool.submit("packing", sent(RUNAWAY), budget_s=0.3).result(60)["status"] == "timeout"
    assert pool.wait_ready(60)
    assert pool.submit("packing", sent("SELECT 1")).result(60)["status"] == "ok"


def test_fields_are_checked_through_their_kind(pool):
    kind = installed("triples")
    assert pool.prepare("graph", "kind:triples", TRIPLES, [], "de").result(60) == []
    got = pool.submit("graph", json.dumps({"fields": ["Kant", "kennt", "HUME"]})).result(60)
    assert {k: got.get(k) for k in ("status", "key", "parts")} == kind.check(
        Prepared(), Step(TRIPLES["item"]), Entry(fields=("Kant", "kennt", "HUME"))).sent()
    assert got["parts"][2] == {"key": "hume", "text": "HUME", "literal": False}


def test_an_engine_that_is_none_is_refused_as_before(pool):
    """F1's way in: an item without an engine is no engine the pool has - a ValueError, which F1's checks
    take (checking.py: prepare), not an AttributeError that ends the game's opening (package 6's review)."""
    for engine in (None, "prolog", 7):
        with pytest.raises(ValueError, match="no engine"):
            pool.prepare("none", engine, "a seed")


def test_a_kind_that_is_not_installed_fails_its_activity(pool):
    with pytest.raises(ValueError, match="no kind"):
        pool.prepare("none", "kind:no-such-kind", TRIPLES, [], "en").result(60)
    assert pool.submit("none", sent("x")).result(60)["status"] == "internal"
    assert pool.wait_ready(60)


# ------------------------------------------------------------------ the worker's part, without a process
class Odd(Kind):
    NAME = "odd"
    INPUT = "code"
    REDUCTION = "groups"
    MESSAGES = fixed(said=("what",))

    def check(self, prepared, step, entry):
        if entry.text == "raises":
            raise RuntimeError("a kind's own fault")
        if entry.text == "memory":
            raise MemoryError
        if entry.text == "no key":
            return Check("ok")
        if entry.text == "unlisted":
            return Check("invalid", message=Message("nowhere"))
        if entry.text == "out of memory":
            return Check("error", message=Message("said", {"what": "memory"}), memory=True)
        return Check("ok", key=entry.text, detail={"compared": prepared.rows}, rows=[entry.text])


def test_what_a_kinds_check_raises_or_gets_wrong_is_internal(monkeypatch):
    monkeypatch.setattr(registry, "kind", lambda name: Odd())
    odd = worker._OfKind("odd")
    state = odd.load({"item": {"a": 1}, "keys": {}, "files": {}}, heap_allowance=1)
    assert odd.image(state, 100) is None
    for text in ("raises", "no key", "unlisted"):
        assert odd.check(state, None, sent(text), "en", 1.0) == ({"status": "internal"}, None), text
    assert odd.check(state, None, "no JSON", "en", 1.0) == ({"status": "internal"}, None)
    assert odd.check(state, None, sent("memory"), "en", 1.0) == ({"status": "error", "memory": True}, None)
    assert odd.check(state, None, sent("out of memory"), "en", 1.0) == (
        {"status": "error", "message": {"code": "said", "args": {"what": "memory"}}, "memory": True}, None)
    # a result is compared with the reference's rows; a reference - its text as it is - with none
    assert odd.check(state, ["r"], sent("x"), "en", 1.0) == ({"status": "ok", "key": "x", "detail": {"compared": ["r"]}}, ["x"])
    assert odd.check(state, ["r"], "x", "en", 1.0, reference=True) == (
        {"status": "ok", "key": "x", "detail": {"compared": ["r"]}}, ["x"])
