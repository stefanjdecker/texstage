# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The contract a kind of activity implements, API 0 (texstage/activities: kind.py, options.py,
registry.py; docs/architecture/activity-framework-plan-f2.md, package 2): the rules a check must keep
and what the core makes of one that breaks them; what leaves the worker; the options' types; and the
registry - the kinds the installed packages bring, and why one is not used."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import texstage.activities.options as option_types
from texstage.activities import kind as contract
from texstage.activities import registry
from texstage.activities.kind import Check, Kind, Message, Step, fixed
from texstage.activities.options import Choice, File, Flag, Int, Named, Options, Unbuildable, Words


class Groups(Kind):
    NAME = "some-groups"
    INPUT = "code"
    REDUCTION = "groups"
    MESSAGES = fixed(plain=(), at=("line", "message"))


class Crowd(Kind):
    NAME = "some-crowd"
    INPUT = "fields"
    REDUCTION = "crowd"


PART = {"key": "k", "text": "K", "literal": False}
GOOD = [
    (Groups(), Check("ok", key="4cc49ff7c0a1e3b2")),
    (Groups(), Check("ok", key="k", detail={"rows": [["a", 1]], "count": 1}, verdict="partial", credit=0.5)),
    (Groups(), Check("ok", key="k", verdict="correct", credit=1)),
    (Groups(), Check("ok", key="x" * 4096)),
    (Groups(), Check("ok", key="k", detail={"cell": "\ud83d"})),                    # half an emoji, as the browser cut it
    (Groups(), Check("invalid", message=Message("at", {"line": 2, "message": "x" * 300}), at=(2, 7))),
    (Groups(), Check("error", message=Message("plain"))),
    (Groups(), Check("refused")), (Groups(), Check("timeout")),
    (Groups(), Check("ok", key="k", canonical="c" * 100_000, rows=["r"] * 10_000, memory=True)),      # the worker's own
    (Crowd(), Check("ok", key="k\x1fk", parts=[PART, PART])),
    (Crowd(), Check("invalid")),
    (Groups(), Check("ok", key="k", verdict="incorrect", credit=0)),
    (Groups(), Check("invalid", message=Message("at", {"line": 2.5, "message": ""}))),               # a float is a number
    (Groups(), Check("invalid", message=Message("at", {"line": 2**53, "message": "x"}))),
    (Groups(), Check("ok", key="k", detail={"rows": "x" * (12 * 1024 - 11)})),                      # the bound itself
    (Groups(), Check("ok", key="k", detail={"rows": ["\u0416" * 2000] * 5})),          # 10,000 letters: 60,000 escaped
    (Groups(), Check("ok", key="k", detail={"rows": ["\U0001f600" * 1000] * 10})),
]
BAD = [
    (Groups(), {"status": "ok"}, "not a Check"),
    (Groups(), None, "not a Check"),
    (Groups(), Check("syntax"), "the status 'syntax'"),
    (Groups(), Check("internal"), "the status 'internal'"),                          # the core's alone
    (Groups(), Check("ok"), "has a key"),
    (Groups(), Check("ok", key=""), "has a key"),
    (Groups(), Check("ok", key=7), "has a key"),
    (Groups(), Check("ok", key="x" * 4097), "has a key"),
    (Groups(), Check("invalid", key="k"), "has no key"),
    (Groups(), Check("error", detail={"a": 1}), "has no key, parts or detail"),
    (Groups(), Check("ok", key="k", verdict="right"), "the verdict 'right'"),
    (Groups(), Check("ok", key="k", credit=0.5), "a credit without a verdict"),
    (Groups(), Check("ok", key="k", verdict="partial", credit=1.5), "the credit 1.5"),
    (Groups(), Check("ok", key="k", verdict="partial", credit=True), "the credit True"),
    (Groups(), Check("ok", key="k", verdict="partial", credit="half"), "the credit 'half'"),
    (Groups(), Check("invalid", message="words"), "the message 'words'"),
    (Groups(), Check("invalid", message=Message("unknown")), "the message 'unknown': none of the kind's MESSAGES"),
    (Groups(), Check("invalid", message=Message("at", {"line": 1})), "the message at: its arguments are line, message"),
    (Groups(), Check("invalid", message=Message("plain", {"n": 1})), "the message plain: its arguments are none"),
    (Groups(), Check("invalid", message=Message("at", {"line": 1, "message": "x" * 301})), "at most 300 characters"),
    (Groups(), Check("invalid", message=Message("at", {"line": [1], "message": "x"})), "a number a phone can read or a text"),
    (Groups(), Check("invalid", message=Message("at", {"line": True, "message": "x"})), "a number a phone can read or a text"),
    (Groups(), Check("invalid", message=Message("at", {"line": float("nan"), "message": "x"})), "a number a phone can read"),
    (Groups(), Check("invalid", message=Message("at", {"line": float("inf"), "message": "x"})), "a number a phone can read"),
    (Groups(), Check("invalid", message=Message("at", {"line": 10**5000, "message": "x"})), "a number a phone can read"),
    (Groups(), Check("invalid", message=Message("at", {"line": 2**53 + 1, "message": "x"})), "a number a phone can read"),
    (Groups(), Check("invalid", message=Message("at", {"line": 1, "message": "half \ud83d"})), "a number a phone can read or a text"),
    (Groups(), Check("invalid", message=Message("at", ["line", "message"])), "the message at: its arguments are line, message"),
    (Groups(), Check("invalid", message=Message(["at"])), "the message ['at']: none of the kind's MESSAGES"),
    (Groups(), Check("ok", key="half \ud83d"), "has a key"),
    (Groups(), Check("ok", key="k", verdict="partial", credit=-0.1), "the credit -0.1"),
    (Groups(), Check("ok", key="k", verdict="partial", credit=float("nan")), "the credit nan"),
    (Groups(), Check("ok", key="k", verdict=["correct"]), "the verdict ['correct']"),
    (Groups(), Check(["ok"]), "the status ['ok']"),
    (Groups(), Check("invalid", at=(1, 2, 3)), "at (1, 2, 3)"),
    (Groups(), Check("invalid", at=(True, 1)), "at (True, 1)"),
    (Groups(), Check("invalid", detail={}), "has no key, parts or detail"),
    (Groups(), Check("ok", key="k", detail={"n": float("nan")}), "the detail is not JSON a phone can read"),
    (Groups(), Check("ok", key="k", detail={"n": float("inf")}), "the detail is not JSON a phone can read"),
    (Groups(), Check("ok", key="k", detail={"rows": "x" * (12 * 1024 - 10)}), "the detail: a table of at most 12 KiB"),
    (Crowd(), Check("invalid", parts=[PART, PART]), "has no key, parts or detail"),
    (Crowd(), Check("ok", key="k", parts=[PART, {**PART, "key": ""}]), "a part has a key and a text"),
    (Crowd(), Check("ok", key="k", parts=[PART, {**PART, "key": 7}]), "a part has a key and a text"),
    (Crowd(), Check("ok", key="k", parts=[PART, {**PART, "text": 7}]), "a part has a key and a text"),
    (Crowd(), Check("ok", key="k", parts=[PART, {**PART, "text": "half \ud83d"}]), "a part has a key and a text"),
    (Groups(), Check("invalid", at=(0, 1)), "at (0, 1)"),
    (Groups(), Check("invalid", at=(1,)), "at (1,)"),
    (Groups(), Check("invalid", at=[1, 2]), "at [1, 2]"),
    (Groups(), Check("invalid", at=(1.0, 2)), "at (1.0, 2)"),
    (Groups(), Check("ok", key="k", detail=["a"]), "the detail: a table"),
    (Groups(), Check("ok", key="k", detail={"rows": "x" * (12 * 1024)}), "the detail: a table of at most 12 KiB"),
    (Groups(), Check("ok", key="k", detail={"set": {1, 2}}), "the detail is not JSON"),
    (Groups(), Check("ok", key="k", parts=[PART]), "parts are for crowd, not for groups"),
    (Crowd(), Check("ok", key="k"), "has parts, one for each field"),
    (Crowd(), Check("ok", key="k", parts=[]), "has parts"),
    (Crowd(), Check("ok", key="k", parts=[PART]), "one for each field"),                 # (the step has two fields)
    (Crowd(), Check("ok", key="k", parts=[PART, {"key": "k", "text": "K"}]), "a part has a key and a text"),
    (Crowd(), Check("ok", key="k", parts=[PART, {**PART, "literal": 1}]), "a part has a key and a text"),
    (Crowd(), Check("ok", key="k", parts=[PART, {**PART, "text": ""}]), "a part has a key and a text"),
    (Crowd(), Check("ok", key="k", parts=[PART, {**PART, "more": 1}]), "a part has a key and a text"),
]
STEP = Step({"fields": ["From", "To"]})


@pytest.mark.parametrize("kind, check", GOOD)
def test_a_check_that_keeps_the_rules(kind, check):
    assert contract.fault(kind, check, STEP) is None
    assert contract.validated(kind, check, STEP) is check


@pytest.mark.parametrize("kind, check, why", BAD)
def test_a_check_that_breaks_a_rule_is_internal_and_the_rule_is_said(kind, check, why):
    assert why in contract.fault(kind, check, STEP)
    assert contract.validated(kind, check, STEP) == Check("internal")           # never the student's


def test_what_leaves_the_worker():
    check = Check("ok", key="k", detail={"count": 1}, verdict="correct", credit=1.0, canonical="select\n1", rows=["r"],
                  memory=True)
    assert check.sent() == {"status": "ok", "key": "k", "detail": {"count": 1}, "verdict": "correct", "credit": 1.0}
    said = Check("invalid", message=Message("at", {"line": 2, "message": "x"}), at=(2, 7)).sent()
    assert said == {"status": "invalid", "message": {"code": "at", "args": {"line": 2, "message": "x"}}, "at": [2, 7]}
    assert Check("timeout").sent() == {"status": "timeout"}
    crowd = Check("ok", key="k", parts=[PART]).sent()
    assert crowd == {"status": "ok", "key": "k", "parts": [PART]}
    assert Check("ok", key="k", verdict="incorrect", credit=0).sent() == {"status": "ok", "key": "k", "verdict": "incorrect", "credit": 0}
    message = Message("at", {"line": 2, "message": "x"})
    sent = Check("invalid", message=message).sent()
    sent["message"]["args"]["line"] = 3                             # what is sent is its own table
    assert message.args == {"line": 2, "message": "x"}


def test_fault_never_raises():
    """What cannot even be held against the rules breaks them: the core gets a reason, and an internal check."""
    deep = {}
    for _ in range(100_000):
        deep = {"d": deep}
    listed = type("Listed", (Groups,), {"MESSAGES": ["plain"]})()
    none = type("None_", (Groups,), {"MESSAGES": None})()
    cases = [(Groups(), Check("ok", key="k", detail=deep), None, "the detail is not JSON a phone can read"),
             (listed, Check("invalid", message=Message("plain")), None, "the message 'plain': none of the kind's MESSAGES"),
             (none, Check("invalid", message=Message("plain")), None, "none of the kind's MESSAGES"),
             (Crowd(), Check("ok", key="k", parts=[PART]), Step(None), None),
             (Crowd(), Check("ok", key="k", parts=[PART]), Step({"fields": 7}), None),
             (Crowd(), Check("ok", key="k", parts=PART), Step({"fields": ["a"]}), "has parts")]
    for kind, check, step, why in cases:
        found = contract.fault(kind, check, step)
        assert (found is None) if why is None else (why in found), found
        assert contract.validated(kind, check, step).status == ("ok" if why is None else "internal")

    class Odd(Groups):
        @property
        def REDUCTION(self):                                        # noqa: N802 - a kind that cannot even say what it is
            raise RuntimeError("no reduction")

    found = contract.fault(Odd(), Check("ok", key="k"))
    assert found == "the check cannot be held against the rules - RuntimeError: no reduction"
    assert contract.validated(Odd(), Check("ok", key="k")) == Check("internal")


def test_a_messages_code_is_fixed_and_a_table_cannot_be_changed():
    with pytest.raises(AttributeError):
        Message("plain").code = "other"
    assert hash(Message("at", {"line": 1})) == hash(Message("at", {"line": 2})) and Message("at", {"line": 1}) != Message("at", {"line": 2})
    table = fixed(a=Words(), b=())
    assert dict(table) == {"a": table["a"], "b": ()} and list(table) == ["a", "b"]
    with pytest.raises(TypeError):
        table["c"] = ()
    assert contract.Kind.OPTIONS == {} and contract.Kind.MESSAGES == {}


# ------------------------------------------------------------------ the options' types
def refusal(option, key, given) -> str:
    with pytest.raises(Unbuildable) as e:
        option.read(key, given, None)
    return str(e.value)


def test_words():
    assert Words().read("suggest", ["a", "b"], None) == ["a", "b"] and Words().read("suggest", None, None) == []
    assert Words().read("tokens", [f"t{i}" for i in range(40)], None)[39] == "t39"
    assert Words().read("tokens", ["t" * 60], None) == ["t" * 60]
    said = "tokens= takes at most 40 items of 1 to 60 characters"
    assert refusal(Words(), "tokens", [f"t{i}" for i in range(41)]) == said
    assert refusal(Words(), "tokens", ["t" * 61]) == said and refusal(Words(), "tokens", ["a", ""]) == said
    assert refusal(Words(), "tokens", ["a", 5]) == said
    assert refusal(Words(), "tokens", "abc") == said and refusal(Words(), "tokens", {"a": 1}) == said     # no list
    given = ["a", "b"]
    read = Words().read("tokens", given, None)
    read.append("c")                                                # the deck's own list is not the kind's to change
    assert given == ["a", "b"] and Words().read("tokens", ("a", "b"), None) == ["a", "b"]
    assert refusal(Words(3, 2), "fields", ["abc"]) == "fields= takes at most 3 items of 1 to 2 characters"
    assert Words(3, 2).read("fields", ["ab", "c", "d"], None) == ["ab", "c", "d"]
    assert refusal(Words(3, 2), "fields", ["a", "b", "c", "d"]).startswith("fields=")


def test_a_number():
    assert Int(1000).read("min", "", None) == 1 and Int(50, 5).read("limit", None, None) == 5
    assert Int(1000).read("min", "1000", None) == 1000 and Int(1000).read("min", "1", None) == 1
    assert Int(1000).read("min", "007", None) == 7
    for given in ("0", "1001", "many", "-1", "1.5", "\u00b2", "\u0663", " 3"):
        assert refusal(Int(1000), "min", given) == f"min={given} - a number from 1 to 1000"
    assert refusal(Int(50, 5), "limit", 7) == "limit=7 - a number from 1 to 50"      # the record has digits, not numbers


def test_a_flag_and_a_choice():
    assert Flag().read("review", True, None) is True and Flag().read("review", None, None) is False
    terms = Choice("exact", "loose")
    assert terms.read("terms", "", None) == "exact" and terms.read("terms", None, None) == "exact"
    assert terms.read("terms", "loose", None) == "loose" and terms.values == ("exact", "loose")
    assert refusal(terms, "terms", "fuzzy") == "terms=fuzzy - exact or loose"
    assert refusal(terms, "terms", "Loose") == "terms=Loose - exact or loose"


def test_a_file_is_read_when_its_text_is_asked_for():
    asked = []

    def files(name, what):
        asked.append((name, what))
        if name == "missing.sql":
            raise Unbuildable(f"the {what} {name} is not there (paths are the deck's)")
        return "CREATE TABLE t(x);"

    assert File(".sql").read("seed", "", files) is None and File(".sql").read("seed", None, files) is None
    seed = File(".sql", ".db").read("seed", "Data/Seed.SQL", files)
    assert isinstance(seed, Named) and (seed.name, seed.suffix) == ("Data/Seed.SQL", ".sql") and asked == []
    assert seed.text() == "CREATE TABLE t(x);" and asked == [("Data/Seed.SQL", "seed")]
    missing = File().read("reference", "missing.sql", files)
    with pytest.raises(Unbuildable, match="the reference missing.sql is not there"):
        missing.text()
    assert File(".sql", ".db").suffixes == (".sql", ".db") and File().suffixes == ()
    assert File().read("seed", " ", files).name == " "               # a name of spaces is a name: the kind refuses it


def test_a_kinds_options_are_read_once_when_it_asks():
    class Counted(Int):
        reads = 0

        def read(self, key, given, files):
            Counted.reads += 1
            return super().read(key, given, files)

    options = Options(fixed(min=Counted(1000), terms=Choice("exact", "loose"), suggest=Words()),
                      {"min": "many", "terms": "fuzzy", "suggest": ["x"], "tokens": ["?"]})
    assert Counted.reads == 0 and options.given("min") == "many" and options.given("seed") is None
    assert options["suggest"] == ["x"] and options["suggest"] is options["suggest"]
    with pytest.raises(Unbuildable, match="terms=fuzzy"):                # the one the kind asks for first is said
        options["terms"]
    with pytest.raises(Unbuildable, match="min=many"):
        options["min"]
    with pytest.raises(KeyError):
        options["tokens"]                                                 # no option of this kind
    fine = Options(fixed(min=Counted(1000)), {"min": "3"})
    Counted.reads = 0
    assert (fine["min"], fine["min"], Counted.reads) == (3, 3, 1)
    assert option_types.CORE == ("id", "input", "engine", "kind", "limit", "open")
    given = {"min": "3"}
    held = Options(fixed(min=Int(1000)), given)
    given["min"] = "many"                                           # what a deck gave is read as it was given
    assert held["min"] == 3 and held.given("min") == "3"
    declared = fixed(suggest=Words())
    assert Options(declared, {"fields": ["Subject", "Predicate", "Object"]}).unused() == []
    assert Options(declared, {"fields": ["Object", "Predicate", "Subject"]}).unused() == ["fields"]       # no preset
    assert Options(declared, {}).unused({"seed": "x", "references": ["y"]}) == ["seed", "reference"]
    assert Options(declared, {"reference": "r.sql"}).unused({"seed": "x"}) == ["reference", "seed"]


# ------------------------------------------------------------------ the registry
@dataclass
class Dist:
    name: str
    version: str = "1.0.0"


class Point:
    """An entry point, as importlib.metadata gives one."""

    def __init__(self, name, target, package="some-kinds", value="some_kinds:Some"):
        self.name, self.value, self.dist, self._target = name, value, Dist(package), target

    def load(self):
        if isinstance(self._target, BaseException):
            raise self._target
        return self._target


class Named2(Groups):
    NAME = "another"


class Future(Groups):
    API = 1


class Unmade(Groups):
    def __init__(self):
        raise RuntimeError("needs a licence key")


class Shouting(Groups):
    NAME = "Some_Groups"


def test_the_installed_kinds_are_found_by_their_entry_points():
    """The four of kinds/, installed as docs/development.md says (pip install -e kinds/...)."""
    if not (Path(__file__).resolve().parents[1] / "kinds").is_dir():
        pytest.skip("the kinds' packages are not here")              # (texstage's source archive, alone)
    found = {f.name: f for f in registry.found()}
    missing = {"sql-query", "sparql-query", "turtle-graph", "triples"} - set(found)
    assert not missing, f"not installed: {missing} - pip install --no-deps -e kinds/texstage-kinds-sql -e kinds/texstage-kinds-rdf"
    assert {n: (f.package, f.version, f.api, f.fault) for n, f in found.items() if n in ("sql-query", "triples")} == {
        "sql-query": ("texstage-kinds-sql", "0.1.0", 0, None), "triples": ("texstage-kinds-rdf", "0.1.0", 0, None)}
    kinds = registry.kinds()
    assert all(kinds[n].NAME == n and isinstance(kinds[n], Kind) for n in ("sql-query", "sparql-query", "turtle-graph", "triples"))
    assert registry.kind("triples") is kinds["triples"] is registry.kind("triples")          # made once
    with pytest.raises(registry.Missing, match="no kind relational-algebra is installed .*installed: .*sql-query"):
        registry.kind("relational-algebra")


def test_why_an_entry_point_gives_no_kind():
    points = [Point("some-groups", Groups), Point("broken", ImportError("No module named 'pyoxigraph'\nmore")),
              Point("a-function", len, value="builtins:len"), Point("an-object", Groups(), value="some_kinds:it"),
              Point("some-other", Named2), Point("future", type("F", (Future,), {"NAME": "future"})),
              Point("unmade", type("U", (Unmade,), {"NAME": "unmade"})), Point("Some_Groups", Shouting)]
    found = {f.name: f for f in registry.read(points)}
    assert found["some-groups"].fault is None and isinstance(found["some-groups"].kind, Groups)
    assert (found["some-groups"].package, found["some-groups"].version, found["some-groups"].api) == ("some-kinds", "1.0.0", 0)
    faults = {n: f.fault for n, f in found.items() if f.kind is None}
    assert faults == {
        "broken": "it does not load - ImportError: No module named 'pyoxigraph'",
        "a-function": "builtins:len is no kind (a class of texstage.activities.Kind)",
        "an-object": "some_kinds:it is no kind (a class of texstage.activities.Kind)",
        "some-other": "its class is named 'another', its entry point 'some-other'",
        "future": "it implements API 1, this texstage API 0",
        "unmade": "it cannot be made - RuntimeError: needs a licence key",
        "Some_Groups": "a kind's name is lower case letters and digits, with hyphens between: sql-query",
    }
    assert found["future"].api == 1 and found["broken"].api is None


def test_two_packages_with_a_kind_of_one_name_bring_none():
    found = registry.read([Point("some-groups", Groups, "b-kinds"), Point("some-groups", Groups, "a-kinds"),
                           Point("some-crowd", Crowd, "a-kinds")])
    assert [(f.name, f.package, f.kind is None, f.fault) for f in found] == [
        ("some-crowd", "a-kinds", False, None),
        ("some-groups", "a-kinds", True, "b-kinds brings a kind of this name too"),
        ("some-groups", "b-kinds", True, "a-kinds brings a kind of this name too")]


def test_a_kind_that_cannot_be_used_says_why_when_it_is_asked_for(monkeypatch):
    monkeypatch.setattr(registry, "found", lambda: tuple(registry.read([Point("future", type("F", (Future,), {"NAME": "future"}))])))
    assert registry.kinds() == {}
    with pytest.raises(registry.Missing, match="the kind future of some-kinds 1.0.0 cannot be used: it implements API 1"):
        registry.kind("future")
    with pytest.raises(registry.Missing, match=r"no kind sql-query is installed \(installed: none\)"):
        registry.kind("sql-query")


# ------------------------------------------------------------------ what the review of package 2 found
def test_what_a_package_does_when_it_is_imported_is_its_kinds_reason():
    class Leaving:
        name, value, dist = "leaving", "leaving_kinds:It", Dist("leaving-kinds")

        def load(self):
            raise SystemExit(0)

    class Meta(type):
        @property
        def NAME(cls):                                              # noqa: N802
            raise RuntimeError("no name\nand more")

    unreadable = Meta("Unreadable", (Groups,), {})
    made = type("Made", (Unmade,), {"NAME": "unmade", "__init__": lambda self: (_ for _ in ()).throw(ImportError("No module named 'pyoxigraph'\nmore"))})
    found = {f.name: f for f in registry.read([Leaving(), Point("unreadable", unreadable), Point("unmade", made),
                                               Point("some-groups", Groups)])}
    assert found["leaving"].fault == "it does not load - SystemExit: 0" and found["some-groups"].fault is None
    assert found["unreadable"].fault == "its class cannot be read - RuntimeError: no name"
    assert found["unmade"].fault == "it cannot be made - ImportError: No module named 'pyoxigraph'"      # one line
    with pytest.raises(KeyboardInterrupt):                          # the lecturer's own Ctrl+C is not a package's reason
        registry.read([Point("stopped", KeyboardInterrupt())])


@pytest.mark.parametrize("api", [False, 0.0, "0", None, 1])
def test_an_api_that_is_not_this_one(api):
    found = registry.read([Point("odd", type("Odd", (Groups,), {"NAME": "odd", "API": api}))])[0]
    assert found.kind is None and found.fault == f"it implements API {api!r}, this texstage API 0" and found.api == api


def test_a_name_twice_in_one_package_a_name_that_ends_in_a_hyphen_and_no_package():
    twice = registry.read([Point("some-groups", Groups), Point("some-groups", Groups), Point("some-crowd", Crowd)])
    assert [(f.name, f.kind is None, f.fault) for f in twice] == [
        ("some-crowd", False, None), ("some-groups", True, "its package names this kind twice"),
        ("some-groups", True, "its package names this kind twice")]
    hyphen = registry.read([Point("some-", type("H", (Groups,), {"NAME": "some-"}))])[0]
    assert hyphen.fault == "a kind's name is lower case letters and digits, with hyphens between: sql-query"
    lone = Point("some-groups", Groups)
    lone.dist = None                                                # an entry point of no distribution
    assert [(f.package, f.version, f.fault) for f in registry.read([lone])] == [("?", "?", None)]


def test_what_was_found_stays_as_it_was_found_until_it_is_forgotten(monkeypatch):
    import dataclasses
    from importlib import metadata
    with pytest.raises(dataclasses.FrozenInstanceError):
        registry.read([Point("some-groups", Groups)])[0].kind = None
    asked = []
    monkeypatch.setattr(metadata, "entry_points", lambda group: asked.append(group) or [Point("some-groups", Groups)])
    registry.forget()
    try:
        assert registry.found() is registry.found() and asked == ["texstage.kinds"]         # read once
        assert set(registry.kinds()) == {"some-groups"}
        registry.forget()
        assert registry.found()[0].name == "some-groups" and asked == ["texstage.kinds"] * 2
    finally:
        monkeypatch.undo()
        registry.forget()


def test_a_kind_of_an_engine_that_is_not_installed_cannot_be_made(monkeypatch):
    """Not listed as one that can be used: nothing is installed half."""
    from texstage.activities.code import CodeKind

    class Lost(CodeKind):
        NAME = "lost"
        MODULE = "an_engine_nobody_installed"

    found = registry.read([Point("lost", Lost)])[0]
    assert found.kind is None and found.fault == "it cannot be made - ModuleNotFoundError: No module named 'an_engine_nobody_installed'"
    assert isinstance(CodeKind(), CodeKind)                                   # (a base without an engine is made)


def test_a_text_that_carries_its_code_travels_whole_and_only_while_a_kind_asks():
    import copy
    import pickle

    from texstage.checks import texts
    W = texts.Words("en")
    with texts.coded():
        said = W.at(2, 7, "x")
        with texts.coded():                                         # one inside another: the outer stays
            assert type(W.service) is texts.Said
        assert type(W.service) is texts.Said
    assert type(W.service) is str and type(W.at(2, 7, "x")) is str             # it ends
    with pytest.raises(RuntimeError):
        with texts.coded():
            raise RuntimeError("a check failed")
    assert type(W.tooDeep(500)) is str                                         # ... also when a check raised
    for travelled in (pickle.loads(pickle.dumps(said)), copy.copy(said), copy.deepcopy(said)):
        assert type(travelled) is texts.Said and travelled == "line 2, column 7: x"
        assert (travelled.code, travelled.args) == ("at", {"line": 2, "column": 7, "message": "x"})
    assert texts.arguments("at") == ("line", "column", "message") and texts.arguments("tooDeep") == ("n",)


def test_a_catalogs_text_is_cut_as_an_engines_words_are_and_a_code_a_kind_does_not_list_is_the_engines(monkeypatch):
    import sys

    from texstage.activities.code import CodeKind, said, words
    from texstage.activities.kind import Entry
    from texstage.checks import texts

    class Engine:
        def load(self, seed, **options):
            return {}

        def evaluate(self, state, text, language=None, budget_s=None):
            W = texts.Words(language)
            error = W.at(1, 2, "m" * 734) if text == "long" else W.service
            return {"status": "syntax", "error": error}

    monkeypatch.setitem(sys.modules, "an_engine_of_these_tests", Engine())

    class Some(CodeKind):
        NAME = "some"
        MODULE = "an_engine_of_these_tests"
        MESSAGES = said("at")                                       # ... and no service

    kind = Some()
    mine = kind.prepare({"seed": "s"}, {}, {"s": b"x"})
    long = kind.check(mine, Step({}), Entry(text="long"))
    assert long.message == Message("at", {"line": 1, "column": 2, "message": "m" * 300}) and contract.fault(kind, long) is None
    unlisted = kind.check(mine, Step({}), Entry(text="service"))
    assert unlisted.message == Message("engine", {"text": "SERVICE (a query to another endpoint) is not run"})
    assert contract.fault(kind, unlisted) is None and words(unlisted.message, "de").startswith("SERVICE (a query")


def test_the_catalogs_texts_take_the_same_arguments_in_every_language():
    """A message's arguments are read off the English text: the German one is made with the same."""
    import string

    from texstage.checks import texts
    for code in texts.ENGINES["en"]:
        names = [{name for _, name, _, _ in string.Formatter().parse(texts.ENGINES[lang][code]) if name} for lang in ("en", "de")]
        assert names[0] == names[1] == set(texts.arguments(code)), code
    assert set(texts.ENGINES["en"]) == set(texts.ENGINES["de"])
