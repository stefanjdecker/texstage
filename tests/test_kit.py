# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The kit - the test every kind passes (texstage/activities/kit.py; `texstage kinds check`;
docs/architecture/activity-framework-plan-f2.md, package 2): the four kinds pass it; a kind that breaks
a rule fails it with the reason; the kinds' fixtures are what tests/fixtures/checks/to_kinds.py makes of
the golden fixtures."""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import pytest

from texstage import cli
from texstage.activities import kit, registry
from texstage.activities.kind import Built, Check, Entry, Kind, Message, Unbuildable, Unfit, fixed
from texstage.activities.options import File, Words

ROOT = Path(__file__).resolve().parents[1]
FOUR = ("sql-query", "sparql-query", "turtle-graph", "triples")


def installed() -> dict:
    found = {f.name: f for f in registry.found()}
    if not (ROOT / "kinds").is_dir():
        pytest.skip("the kinds' packages are not here")
    missing = set(FOUR) - set(found)
    assert not missing, f"not installed: {missing} - pip install --no-deps -e kinds/texstage-kinds-sql -e kinds/texstage-kinds-rdf"
    return found


# ------------------------------------------------------------------ the four kinds
@pytest.mark.parametrize("name", FOUR)
def test_a_kind_of_today_passes_the_kit(name):
    if name != "sql-query":
        pytest.importorskip("pyoxigraph")
    report = kit.check(installed()[name].kind, name, known=set(installed()))
    assert report.faults == [] and report.ok
    assert report.fixtures == {"sql-query": 197, "sparql-query": 84, "turtle-graph": 65, "triples": 18}[name]
    assert report.builds == (6 if name == "triples" else 7)
    assert report.budget_s == 2.0 and report.slowest_s < 2.0
    assert not [w for w in report.warnings if "is for a kind" in w]         # every file of its folder is some kind's


def test_the_kinds_fixtures_are_what_the_golden_fixtures_make():
    """to_kinds.py makes them of tests/fixtures/checks/*.json and holds each case against its golden result;
    a golden fixture changed without it, or a kind that gives something else now, shows here."""
    pytest.importorskip("pyoxigraph")
    installed()
    spec = importlib.util.spec_from_file_location("to_kinds", ROOT / "tests" / "fixtures" / "checks" / "to_kinds.py")
    to_kinds = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(to_kinds)
    made = to_kinds.made()
    assert len(made) == 10
    stale = [path.name for path, text in made.items() if not path.is_file() or path.read_text(encoding="utf-8") != text]
    assert stale == [], "python tests/fixtures/checks/to_kinds.py writes them anew"
    on_disk = {p for p in (ROOT / "kinds").glob("*/src/*/tests/*.json")}
    assert on_disk == set(made)                                    # and no file of another making
    cases = sum(len(json.loads(text)["cases"]) for text in made.values())
    assert cases == 300 + 20 + 3 + 8 + 3 * 5 + 18                  # golden; safety; with references; triples
    assert sum(len(json.loads(text).get("builds", [])) for text in made.values()) == 3 * 7 + 6
    people = json.loads(made[ROOT / "kinds/texstage-kinds-sql/src/texstage_kinds_sql/tests/sql-reference.json"])
    everyone = people["cases"][2]["check"]["detail"]                # rows that are not ASCII: six times as long, escaped
    assert len(json.dumps(everyone)) > 12 * 1024 > len(json.dumps(everyone, ensure_ascii=False)) and "diff" in everyone


# ------------------------------------------------------------------ a kind for the tests, and how it breaks
class Echo(Kind):
    """A kind for the kit's tests: a text, grouped by its words in lower case."""
    NAME = "echo"
    INPUT = "code"
    REDUCTION = "groups"
    OPTIONS = fixed(tokens=Words())
    MESSAGES = fixed(empty=(), long=("n",))

    def normalize(self, step, entry):
        text = " ".join(entry.text.split())
        if not text:
            raise Unfit("no text", "text")
        return Entry(text=text)

    def check(self, prepared, step, entry):
        if len(entry.text) > 100:
            return Check("invalid", message=Message("long", {"n": len(entry.text)}))
        return Check("ok", key=entry.text.lower(), detail={"length": len(entry.text)})


CASES = [
    {"setting": "any", "entry": {"text": "Hello   World"}, "check": {"status": "ok", "key": "hello world", "detail": {"length": 11}}},
    {"setting": "any", "entry": {"text": "  "}, "unfit": "text"},
    {"setting": "any", "entry": {"text": {"repeat": 30, "line": "line {i}"}}, "check": {"status": "invalid", "message": {"code": "long"}}},
    {"setting": "any", "entry": {"text": " raw "}, "direct": True, "check": {"status": "ok", "key": " raw "}},
]


def fixtures(tmp_path, cases=CASES, kind="echo", settings=None) -> Path:
    data = {"kind": kind, "settings": {"any": {}} if settings is None else settings, "cases": cases}
    (tmp_path / "echo.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def faults(kind, tmp_path, cases=CASES, **more) -> list[str]:
    return kit.check(kind, folder=fixtures(tmp_path, cases, **more)).faults


def test_a_kind_that_keeps_the_rules_passes(tmp_path):
    report = kit.check(Echo(), "echo", fixtures(tmp_path))
    assert report.faults == [] and report.warnings == [] and report.fixtures == 4 and report.ok
    assert kit.said(report).startswith("echo: 4 fixtures, twice and in both orders")


def broken(**changes):
    return type("Broken", (Echo,), changes)()


@pytest.mark.parametrize("changes, why", [
    ({"NAME": "Echo"}, "NAME 'Echo': lower case letters and digits, with hyphens between"),
    ({"NAME": "echo_text"}, "NAME 'echo_text'"),
    ({"NAME": ""}, "NAME ''"),
    ({"API": 1}, "API 1: this texstage has API 0"),
    ({"INPUT": "tuple"}, "INPUT 'tuple': one of code, fields, choice, number, text"),
    ({"REDUCTION": "clusters"}, "REDUCTION 'clusters': one of groups, crowd, tally"),
    ({"BUDGET_S": 2000}, "BUDGET_S 2000: seconds, more than 0 and at most 10"),
    ({"BUDGET_S": 0}, "BUDGET_S 0"),
    ({"BUDGET_S": "2"}, "BUDGET_S '2'"),
    ({"LIMIT": 0}, "LIMIT 0: a student's entries, 1 to 50"),
    ({"LIMIT": 51}, "LIMIT 51"),
    ({"LIMIT": 2.5}, "LIMIT 2.5"),
    ({"OPTIONS": ["tokens"]}, "OPTIONS: a table of the deck's keys"),
    ({"OPTIONS": {"tokens": Words()}}, "OPTIONS: a table of the deck's keys"),           # a table anybody can change
    ({"OPTIONS": [("tokens", Words())]}, "OPTIONS: a table of the deck's keys"),
    ({"OPTIONS": ""}, "OPTIONS: a table of the deck's keys"),
    ({"OPTIONS": fixed(tokens="words")}, "OPTIONS: tokens is 'words', not a type of texstage.activities.options"),
    ({"OPTIONS": fixed(Tokens=Words())}, "OPTIONS: the key 'Tokens'"),
    ({"OPTIONS": fixed(seed_file=Words())}, "OPTIONS: the key 'seed_file'"),
    ({"OPTIONS": fixed(limit=Words())}, "OPTIONS: the key limit is the core's own"),
    ({"MESSAGES": ["empty"]}, "MESSAGES: a table of what its checks may say"),
    ({"MESSAGES": {"empty": ()}}, "MESSAGES: a table of what its checks may say"),
    ({"MESSAGES": fixed(empty=[])}, "MESSAGES: empty takes []"),
    ({"MESSAGES": fixed(long=("n", "n"))}, "MESSAGES: long takes ('n', 'n')"),
    ({"MESSAGES": fixed(long=("the-n",))}, "MESSAGES: long takes ('the-n',)"),
    ({"MESSAGES": fixed(**{"Too-Long": ()})}, "MESSAGES: the code 'Too-Long'"),
    ({"MESSAGES": fixed(too_long=())}, "MESSAGES: the code 'too_long'"),
    ({"NAME": "echo-"}, "NAME 'echo-'"),
    ({"NAME": 7}, "NAME 7"),
    ({"API": False}, "API False: this texstage has API 0"),
    ({"API": 0.0}, "API 0.0"),
    ({"BUDGET_S": True}, "BUDGET_S True"),
    ({"BUDGET_S": 10.5}, "BUDGET_S 10.5: seconds, more than 0 and at most 10"),
    ({"LIMIT": True}, "LIMIT True"),
])
def test_a_class_that_breaks_a_rule_fails_with_the_rule(tmp_path, changes, why):
    found = faults(broken(**changes), tmp_path)
    assert len(found) == 1 and why in found[0], found


def test_a_kind_whose_name_is_not_its_entry_points_and_what_is_no_kind(tmp_path):
    assert kit.check(Echo(), "echoes", fixtures(tmp_path)).faults == ["NAME 'echo' is not its entry point's, 'echoes'"]
    assert kit.check(object(), "echo").faults == ["object is no kind (a class of texstage.activities.Kind)"]


def check_with(result):
    def check(self, prepared, step, entry):
        return result(entry) if callable(result) else result
    return check


@pytest.mark.parametrize("changes, why", [
    ({"check": check_with(Check("ok"))}, "a check that is ok has a key"),
    ({"check": check_with(Check("syntax"))}, "the status 'syntax'"),
    ({"check": check_with({"status": "ok"})}, "check gave dict, not a Check"),
    ({"check": check_with(Check("invalid", message=Message("unknown")))}, "the message 'unknown': none of the kind's MESSAGES"),
    ({"check": check_with(lambda e: 1 / 0)}, "check raised ZeroDivisionError: division by zero"),
    ({"check": check_with(lambda e: Check("ok", key=e.text))}, 'key: "Hello World", not "hello world"'),
    ({"check": check_with(lambda e: Check("ok", key=e.text.lower(), detail={"length": 0}))}, 'detail: {"length": 0}, not {"length": 11}'),
    ({"check": check_with(lambda e: Check("invalid", message=Message("empty")))}, 'status: "invalid", not "ok"'),
    ({"normalize": lambda self, step, entry: entry}, 'key: "hello   world", not "hello world"'),
    ({"normalize": lambda self, step, entry: entry.text}, "normalize gave str, not an Entry"),
    ({"normalize": lambda self, step, entry: Entry(text=entry.text + "!")}, "normalize changes what it gave: a normal form is its own"),
])
def test_a_check_that_breaks_a_rule_fails_with_the_case_and_the_rule(tmp_path, changes, why):
    found = faults(broken(**changes), tmp_path)
    assert found and why in found[0] and found[0].startswith("echo.json, case 0 (\"Hello   World\"): "), found


def test_what_a_case_expects_and_does_not_get(tmp_path):
    cases = [{"setting": "any", "entry": {"text": "fine"}, "unfit": "text"},
             {"setting": "any", "entry": {"text": "   "}, "check": {"status": "ok"}},
             {"setting": "any", "entry": {"text": "  "}, "unfit": "field"},
             {"setting": "any", "entry": {"text": "x" * 101}, "check": {"status": "invalid", "message": {"code": "long", "args": {"n": 100}}}},
             {"setting": "any", "entry": {"text": "x" * 101}, "check": {"status": "invalid", "message": {"code": "empty"}}},
             {"setting": "any", "entry": {"text": "ok"}, "check": {"status": "ok", "at": [1, 1]}}]
    found = faults(Echo(), tmp_path, cases)
    assert [f.split("): ", 1)[1] for f in found] == [
        '{"status": "ok", "key": "fine", "detail": {"length": 4}}, not refused as text',
        "refused as text, where a check was to come",
        '{"unfit": "text"}, not refused as field',
        'message: {"code": "long", "args": {"n": 101}}, not {"code": "long", "args": {"n": 100}}',
        'message: {"code": "long", "args": {"n": 101}}, not {"code": "empty"}',
        "at: null, not [1, 1]"]


def test_a_check_that_changes_what_was_prepared_shows_the_second_time(tmp_path):
    class Counting(Echo):
        def prepare(self, item, keys, files, limits=None, copy=None):
            prepared = super().prepare(item, keys, files, limits, copy)
            prepared.state = []
            return prepared

        def check(self, prepared, step, entry):
            prepared.state.append(entry.text)                      # what a check must not do
            return Check("ok", key=f"{entry.text}-{len(prepared.state)}")

    cases = [{"setting": "any", "entry": {"text": t}, "check": {"status": "ok"}} for t in ("a", "b")]
    found = faults(Counting(), tmp_path, cases)
    assert len(found) == 2 and all("another check the second time" in f and "a check changed what was prepared" in f
                                   for f in found)
    assert found[0].startswith('echo.json, case 1 ("b"): another check the second time - {"status": "ok", "key": "b-3"} -')


def test_a_check_that_depends_on_the_one_before_shows_in_the_other_order(tmp_path):
    """Run twice in one order, it would give the same both times: each entry has the same one before it."""
    class Remembering(Echo):
        def prepare(self, item, keys, files, limits=None, copy=None):
            prepared = super().prepare(item, keys, files, limits, copy)
            prepared.state = {"last": None}
            return prepared

        def check(self, prepared, step, entry):
            after_a = prepared.state["last"] == "a"
            prepared.state["last"] = entry.text
            return Check("ok", key=f"{entry.text}, after a: {after_a}")

    cases = [{"setting": "any", "entry": {"text": t}, "check": {"status": "ok"}} for t in ("a", "b")]
    found = faults(type("Plain", (Remembering,), {"INPUT": "text"})(), tmp_path, cases)      # (no nested texts)
    assert found == ['echo.json, case 1 ("b"): another check the second time - {"status": "ok", "key": "b, after a: '
                     'False"} -: a check changed what was prepared']


def test_a_slow_fixture_is_a_warning_and_the_slowest_is_named(tmp_path):
    def slow(self, prepared, step, entry):
        end = time.thread_time() + 0.2
        while time.thread_time() < end:
            pass
        return Check("ok", key=entry.text)

    cases = [{"setting": "any", "entry": {"text": "burn"}, "check": {"status": "ok"}}]
    report = kit.check(broken(check=slow, BUDGET_S=0.1, INPUT="text"), folder=fixtures(tmp_path, cases))
    assert report.ok and report.slowest_s >= 0.15 and report.slowest == 'echo.json, case 0 ("burn")'
    assert len(report.warnings) == 1 and report.warnings[0].startswith('echo.json, case 0 ("burn"): 0.')
    assert "over the kind's budget of 0.1 s" in report.warnings[0]
    assert "the slowest 0." in kit.said(report) and "of 0.1 s" in kit.said(report) and "  warning: " in kit.said(report)
    code = kit.check(broken(check=slow, BUDGET_S=0.1), folder=fixtures(tmp_path, cases))      # of code: the nested texts too
    assert code.ok and len(code.warnings) == 4 and all("a text nested 1000 deep" in w for w in code.warnings[1:])
    assert code.slowest_s >= 0.15 and ("case 0" in code.slowest or "nested 1000 deep" in code.slowest)


def test_a_text_nested_as_deep_as_it_is_long_must_come_back(tmp_path):
    seen = []

    def deep(self, prepared, step, entry):
        seen.append(entry.text)
        if entry.text.startswith("[" * 1000):
            raise RecursionError("maximum recursion depth exceeded")
        return Check("ok", key="k")

    cases = [{"setting": "any", "entry": {"text": "x"}, "check": {"status": "ok"}}]
    found = faults(broken(check=deep), tmp_path, cases)
    assert found == ["echo.json, a text nested 1000 deep in []: check raised RecursionError: maximum recursion depth exceeded"]
    assert {t[:1] for t in seen if len(t) == 2000} == {"(", "[", "{"} and "(" * 1000 + ")" * 1000 in seen
    assert faults(broken(check=deep, INPUT="text"), tmp_path, cases) == []                 # no text of code: none tried


def test_the_fixtures_files(tmp_path):
    assert kit.check(Echo(), folder=tmp_path / "none").faults == ["no fixtures: echo has none in tests/*.json beside its module"]
    other = tmp_path / "other"
    other.mkdir()
    another = kit.check(Echo(), folder=fixtures(other, kind="another-kind"))             # a file of another kind's
    assert another.faults == ["no fixtures: echo has none in tests/*.json beside its module"]
    (other / "broken.json").write_text("{not json", encoding="utf-8")
    assert faults(Echo(), other)[0].startswith("broken.json: not JSON - ")
    (other / "broken.json").unlink()
    for cases, settings in (([], None), (CASES, []), ([{"setting": "none", "entry": {"text": "a"}, "unfit": "text"}], None),
                            ([{"setting": "any", "entry": "a", "unfit": "text"}], None),
                            ([{"setting": "any", "entry": {"text": "a"}}], None),
                            ([{"setting": "any", "entry": {"text": "a"}, "unfit": "text", "check": {"status": "ok"}}], None),
                            ([{"setting": "any", "entry": {"text": "a"}, "check": {"key": "a"}}], None)):
        found = faults(Echo(), other, cases, settings=settings)
        assert len(found) == 1 and found[0].startswith("echo.json: "), (cases, found)


def test_a_setting_the_kind_cannot_be_prepared_with_and_a_reference_that_breaks_a_rule(tmp_path):
    class Picky(Echo):
        def prepare(self, item, keys, files, limits=None, copy=None):
            if "seed" not in item:
                raise ValueError("no seed")
            return super().prepare(item, keys, files, limits, copy)

    cases = [{"setting": "bad", "entry": {"text": "a"}, "check": {"status": "ok"}},
             {"setting": "good", "entry": {"text": "b"}, "check": {"status": "ok"}}]
    settings = {"bad": {"item": {}}, "good": {"item": {"seed": "s"}, "files": {"s": "x"}}}
    report = kit.check(Picky(), folder=fixtures(tmp_path, cases, settings=settings))
    assert report.faults == ["echo.json, setting bad: preparing raised ValueError: no seed"] and report.fixtures == 1
    settings = {"any": {"keys": {"reference": ["fine", "x" * 101]}}}
    found = faults(broken(MESSAGES=fixed()), tmp_path, CASES[:1], settings=settings)
    assert found[0] == "echo.json, setting any, reference 2: the message 'long': none of the kind's MESSAGES"
    assert len(found) == 4 and all("a text nested 1000 deep" in f for f in found[1:])     # (2,000 characters are long too)


def test_a_fixtures_texts_and_what_a_case_pins():
    assert kit.text_of("plain") == "plain"
    assert kit.text_of({"repeat": 3, "line": "l{i};"}) == "l0;\nl1;\nl2;"
    assert kit.text_of({"deep": 2, "open": "(", "inside": "1", "close": ")", "before": "SELECT ", "after": ";"}) == "SELECT ((1));"
    assert kit.text_of({"deep": 1, "open": "[", "close": "]"}) == "[]"
    assert kit.entry_of({"fields": ["a", "b"]}) == Entry(fields=("a", "b")) and kit.entry_of({"fields": "ab"}) == Entry(fields="ab")
    got = {"status": "ok", "key": "k", "detail": {"n": 1}, "message": {"code": "c", "args": {"n": 1}}}
    assert kit.differs({"status": "ok"}, got) is None and kit.differs({"status": "ok", "key": "k", "detail": {"n": 1}}, got) is None
    assert kit.differs({"message": {"code": "c"}}, got) is None and kit.differs({"message": {"code": "c", "args": {"n": 1}}}, got) is None
    assert kit.differs({"message": {"code": "c", "args": {}}}, got) and kit.differs({"key": "K"}, got) == 'key: "k", not "K"'
    assert kit.differs({"verdict": "correct"}, got) == 'verdict: null, not "correct"'
    assert kit.differs({"status": ["error", "ok"]}, got) is None                   # a status an engine's build decides
    assert kit.differs({"status": ["error", "invalid"]}, got) == 'status: "ok", none of ["error", "invalid"]'


# ------------------------------------------------------------------ texstage kinds
def test_texstage_kinds_lists_the_installed_kinds(capsys):
    installed()
    assert cli.main(["kinds"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == sorted(FOUR)
    assert "sql-query     texstage-kinds-sql 0.1.0, API 0" in lines and "triples       texstage-kinds-rdf 0.1.0, API 0" in lines


def test_texstage_kinds_check_runs_the_kit(capsys):
    installed()
    assert cli.main(["kinds", "check", "triples"]) == 0
    assert capsys.readouterr().out.startswith("triples (texstage-kinds-rdf 0.1.0, API 0): 18 fixtures, twice and in both orders")
    assert cli.main(["kinds", "check", "triples", "relational-algebra"]) == 1
    out = capsys.readouterr()
    assert "relational-algebra: no kind of this name is installed" in out.err and out.out.startswith("triples (")


def test_texstage_kinds_says_what_cannot_be_used_and_fails(capsys, monkeypatch, tmp_path):
    class Dist:
        name, version = "some-kinds", "2.0.0"

    class Point:
        def __init__(self, name, target):
            self.name, self.value, self.dist, self._target = name, "some_kinds:It", Dist(), target

        def load(self):
            return self._target

    points = [Point("echo", Echo), Point("future", type("Future", (Echo,), {"NAME": "future", "API": 1}))]
    monkeypatch.setattr(registry, "found", lambda: tuple(registry.read(points)))
    assert cli.main(["kinds"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "echo    some-kinds 2.0.0, API 0", "future  some-kinds 2.0.0, API 1 - cannot be used: it implements API 1, this texstage API 0"]
    assert cli.main(["kinds", "check"]) == 1                       # echo has no fixtures beside this file; future is not used
    out = capsys.readouterr().out
    assert "echo (some-kinds 2.0.0, API 0)\n  FAILS: no fixtures: echo has none" in out
    assert "future (some-kinds 2.0.0): cannot be used - it implements API 1" in out
    monkeypatch.setattr(registry, "found", lambda: tuple(registry.read(points[:1])))
    assert cli.main(["kinds"]) == 0 and cli.main(["kinds", "check"]) == 1      # usable, and fails the kit: no fixtures
    assert "FAILS: no fixtures" in capsys.readouterr().out
    monkeypatch.setattr(registry, "found", lambda: ())
    assert cli.main(["kinds"]) == 0 and "no kinds are installed" in capsys.readouterr().out


# ------------------------------------------------------------------ what the review of package 2 found
def one(text: str = "a") -> list[dict]:
    return [{"setting": "any", "entry": {"text": text}, "check": {"status": "ok"}}]


def test_the_bounds_of_a_class_that_keeps_the_rules(tmp_path):
    assert faults(broken(BUDGET_S=10, LIMIT=50, NAME="e2-e", MESSAGES=fixed(aB1=("lineNumber",))), tmp_path) == [
        "no fixtures: e2-e has none in tests/*.json beside its module"]              # (the file is echo's)


def test_a_check_that_fails_only_the_second_time_fails_the_kit(tmp_path):
    """The second run is held against the first whatever it gave: a check that raises, or breaks a rule."""
    def twice(broken_how):
        class Second(Echo):
            INPUT = "text"

            def prepare(self, item, keys, files, limits=None, copy=None):
                prepared = super().prepare(item, keys, files, limits, copy)
                prepared.state = set()
                return prepared

            def check(self, prepared, step, entry):
                if entry.text in prepared.state:
                    return broken_how()
                prepared.state.add(entry.text)
                return Check("ok", key=entry.text)
        return faults(Second(), tmp_path, one())

    assert twice(lambda: Check("ok")) == ['echo.json, case 0 ("a"): another check the second time - a check that is ok has a '
                                          'key, a text of 1 to 4096 characters -: a check changed what was prepared']
    assert twice(lambda: 1 / 0) == ['echo.json, case 0 ("a"): another check the second time - check raised ZeroDivisionError: '
                                    'division by zero -: a check changed what was prepared']


def test_a_normalize_that_raises_fails_its_case_and_the_others_run(tmp_path):
    def raising(self, step, entry):
        if entry.text == "boom":
            raise KeyError("fields")
        return entry

    cases = [{"setting": "any", "entry": {"text": t}, "check": {"status": "ok"}} for t in ("boom", "fine")]
    report = kit.check(broken(normalize=raising, INPUT="text"), folder=fixtures(tmp_path, cases))
    assert report.faults == ["echo.json, case 0 (\"boom\"): normalize raised KeyError: 'fields'"] and report.fixtures == 2

    def coded(self, step, entry):
        raise Unfit("no", 7)
    assert faults(broken(normalize=coded, INPUT="text"), tmp_path, one()) == [
        'echo.json, case 0 ("a"): normalize refused with the code 7']


def test_the_kits_own_failure_is_said(tmp_path, monkeypatch):
    def failing(kind, files, report, now):
        now["what"] = "echo.json, case 3"
        raise MemoryError("no memory left")

    monkeypatch.setattr(kit, "_fixtures", failing)
    assert faults(Echo(), tmp_path) == ["the kit failed at echo.json, case 3 - MemoryError: no memory left"]


def test_what_a_kind_is_handed_as_the_core_hands_it(tmp_path):
    """The step's language and the kit's budget; the first worker's preparing; a thread with a worker's stack."""
    import threading
    seen = {"copies": 0, "prepared": []}

    class Watching(Echo):
        INPUT = "text"

        def prepare(self, item, keys, files, limits=None, copy=None):
            seen["prepared"].append(copy)
            return super().prepare(item, keys, files, limits, copy)

        def copy(self, prepared, most):
            seen["copies"] += 1
            seen["most"] = most
            return b"a copy"

        def check(self, prepared, step, entry):
            seen.setdefault("steps", []).append((step.language, step.budget_s, step.item))
            seen["thread"] = threading.current_thread().name
            return Check("ok", key=entry.text)

    before = threading.stack_size()
    cases = [{"setting": "any", "entry": {"text": "a"}, "check": {"status": "ok"}},
             {"setting": "any", "entry": {"text": "b"}, "language": "de", "check": {"status": "ok"}}]
    settings = {"any": {"item": {"tokens": ["?"]}}}
    assert faults(Watching(), tmp_path, cases, settings=settings) == []
    assert seen["steps"][:2] == [(None, kit.BUDGET_S, {"tokens": ["?"]}), ("de", kit.BUDGET_S, {"tokens": ["?"]})]
    assert seen["prepared"] == [None, b"a copy"] and seen["copies"] == 1 and seen["most"] == kit.COPY_MOST     # (kind.first)
    assert seen["thread"] == "texstage-kit" and threading.stack_size() == before and kit.STACK == 64 * 2**20
    assert kit.BUDGET_S == 10.0 and kit.HANG_S == 30.0


def test_a_check_that_does_not_come_back_is_given_up(tmp_path, monkeypatch):
    import threading
    stop = threading.Event()

    def spinning(self, prepared, step, entry):
        if entry.text == "spin":
            while not stop.is_set():
                pass
        return Check("ok", key=entry.text)

    monkeypatch.setattr(kit, "HANG_S", 0.5)
    cases = [{"setting": "any", "entry": {"text": t}, "check": {"status": "ok"}} for t in ("fine", "spin", "never reached")]
    try:
        report = kit.check(broken(check=spinning, INPUT="text"), folder=fixtures(tmp_path, cases))
        assert report.faults == ['echo.json, case 1 ("spin"): not back after 0.5 s - it hangs, or takes no heed of its '
                                 'budget; the kit gave the kind up there']
        assert report.fixtures == 1
    finally:
        stop.set()


def test_a_check_that_waits_is_slow_too(tmp_path):
    def sleeping(self, prepared, step, entry):
        time.sleep(0.3)
        return Check("ok", key=entry.text)

    report = kit.check(broken(check=sleeping, BUDGET_S=0.1, INPUT="text"), folder=fixtures(tmp_path, one()))
    assert report.ok and len(report.warnings) == 1 and report.slowest_s < 0.1
    assert "s of them computing - over the kind's budget of 0.1 s" in report.warnings[0]


def test_a_detail_is_compared_as_json_has_it(tmp_path):
    """A tuple is a list on a phone, a number that is a key a text: a case pins what is sent."""
    def tuples(self, prepared, step, entry):
        return Check("ok", key="k", detail={"rows": [("a", 1)], "by": {1: "one"}})

    cases = [{"setting": "any", "entry": {"text": "a"}, "check": {"status": "ok", "detail": {"rows": [["a", 1]], "by": {"1": "one"}}}}]
    assert faults(broken(check=tuples, INPUT="text"), tmp_path, cases) == []


MALFORMED = [
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": ["any"], "entry": {"text": "a"}, "unfit": "text"}]},
     "case 0 - a setting of the file"),
    ({"kind": "echo", "settings": {"any": "a seed"}, "cases": CASES}, "setting any - an item, keys, and files as texts"),
    ({"kind": "echo", "settings": {"any": {"files": {"s": 7}}}, "cases": CASES}, "setting any - an item, keys, and files as texts"),
    ({"kind": "echo", "settings": {"any": {"seed": "x"}}, "cases": CASES}, "setting any - an item, keys, and files as texts"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {"text": {"repeat": "x", "line": "l"}}, "unfit": "t"}]},
     "case 0 - an entry: a text"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {"text": {"deep": 3}}, "unfit": "t"}]},
     "case 0 - an entry: a text"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {}, "unfit": "t"}]}, "case 0 - an entry: a text"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {"text": "a", "fields": ["a"]}, "unfit": "t"}]},
     "case 0 - an entry: a text"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {"text": "a"}, "direkt": True, "unfit": "t"}]},
     "case 0 has direkt - a case has setting, entry, check or unfit, direct, language"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {"text": "a"}, "direct": "yes", "unfit": "t"}]},
     "case 0 - language is a tag, direct true or false"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {"text": "a"}, "unfit": 7}]},
     "case 0 - unfit: the code it is refused with"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {"text": "a"}, "check": {"status": []}}]},
     "case 0 - a check with its status, or the statuses it may be"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": [{"setting": "any", "entry": {"text": "a"}, "check": {"status": "ok", "kee": "a"}}]},
     "case 0 - a check has no kee"),
    ({"kind": "echo", "settings": {"any": {}}, "cases": CASES, "notes": "mine"}, "it has notes - a file has kind, settings, cases and builds"),
    ({"kind": "echo", "builds": [{"options": {}, "built": {"item": {}}, "refused": "no"}]}, "build 0 - options, bodies, files, and either built or refused"),
    ({"kind": "echo", "builds": [{"options": {}}]}, "build 0 - options, bodies, files, and either built or refused"),
    ({"kind": "echo", "builds": [{"options": [], "refused": "no"}]}, "build 0 - options and bodies are tables"),
    ({"kind": "echo", "builds": [{"refused": 7}]}, "build 0 - refused: the refusal's words"),
    ({"kind": "echo", "builds": [{"built": {"keys": {}}}]}, "build 0 - built: the item, the keys, the bundle's files as texts"),
    ({"kind": "echo", "builds": [{"built": {"item": {}, "files": {"a": 1}}}]}, "build 0 - built: the item"),
    ({"kind": 7, "settings": {"any": {}}, "cases": CASES}, 'a file says which kind it is for - {"kind": "echo", ...}'),
    ({"settings": {"any": {}}, "cases": CASES}, "a file says which kind it is for"),
    ([{"kind": "echo"}], "a file says which kind it is for"),
]


@pytest.mark.parametrize("data, why", MALFORMED)
def test_a_malformed_file_is_said_and_no_fixture_of_it_runs(tmp_path, data, why):
    (tmp_path / "echo.json").write_text(json.dumps(data), encoding="utf-8")
    report = kit.check(Echo(), folder=tmp_path)
    assert len(report.faults) == 1 and report.faults[0].startswith(f"echo.json: {why}"), report.faults
    assert report.fixtures == 0 and report.builds == 0


def test_a_key_twice_in_one_table_and_a_file_for_a_kind_that_is_not_installed(tmp_path):
    (tmp_path / "echo.json").write_text('{"kind": "echo", "settings": {"any": {}}, "cases": [], "cases": []}', encoding="utf-8")
    assert kit.check(Echo(), folder=tmp_path).faults == ["echo.json: not JSON - cases twice in one table"]
    fixtures(tmp_path)
    (tmp_path / "typo.json").write_text(json.dumps({"kind": "ehco", "settings": {"any": {}}, "cases": [
        {"setting": "any", "entry": {"text": "a"}, "check": {"status": "invalid"}}]}), encoding="utf-8")
    (tmp_path / "other.json").write_text(json.dumps({"kind": "other", "settings": {}, "cases": CASES}), encoding="utf-8")
    report = kit.check(Echo(), folder=tmp_path, known={"echo", "other"})
    assert report.ok and report.fixtures == 4
    assert report.warnings == ["typo.json is for a kind 'ehco', which is not installed - is the name misspelt?"]
    assert kit.check(Echo(), folder=tmp_path).warnings == []                    # (nobody said which are installed)
    assert "  warning: typo.json is for a kind" in kit.said(report)


class Building(Echo):
    """Echo with a build: its tokens, and a seed it wants."""
    OPTIONS = fixed(tokens=Words(), seed=File(".txt"))

    def build(self, options, bodies):
        item = {"tokens": options["tokens"]}
        if options["seed"] is None:
            raise Unbuildable("it needs a seed")
        if options["seed"].name == "crash.txt":
            raise KeyError("crash")
        text = options["seed"].text() + (bodies.get("more") or "")
        return Built(item, {"reference": bodies.get("references", [])}, {"data/seed.txt": text.encode("utf-8")})


BUILDS = [
    {"options": {"tokens": ["?"], "seed": "s.txt"}, "bodies": {"more": "!", "references": ["r"]}, "files": {"s.txt": "seed"},
     "built": {"item": {"tokens": ["?"]}, "keys": {"reference": ["r"]}, "files": {"data/seed.txt": "seed!"}}},
    {"options": {"tokens": ["?"]}, "refused": "it needs a seed"},
    {"options": {"seed": "missing.txt"}, "refused": "the seed missing.txt is not there (paths are the deck's)"},
    {"options": {"tokens": ["t" * 61], "seed": "s.txt"}, "refused": "tokens= takes at most 40 items of 1 to 60 characters"},
]


def builds(tmp_path, given) -> kit.Report:
    (tmp_path / "echo.json").write_text(json.dumps({"kind": "echo", "builds": given}), encoding="utf-8")
    return kit.check(Building(), folder=tmp_path)


def test_a_kinds_builds_are_held_against_what_they_must_make_or_refuse(tmp_path):
    report = builds(tmp_path, BUILDS)
    assert report.faults == [] and (report.builds, report.fixtures) == (4, 0)
    assert kit.said(report) == "echo: 0 fixtures, twice and in both orders, 4 builds"
    good = BUILDS[0]
    wrong = [
        ({**good, "built": {**good["built"], "item": {"tokens": []}}}, 'item: {"tokens": ["?"]}, not {"tokens": []}'),
        ({**good, "built": {**good["built"], "keys": {}}}, 'keys: {"reference": ["r"]}, not {}'),
        ({**good, "built": {**good["built"], "files": {"data/seed.txt": "seed"}}}, 'files: {"data/seed.txt": "seed!"}, not {"data/seed.txt": "seed"}'),
        ({"options": good["options"], "files": good["files"], "refused": "no"}, "it built, where it was to refuse with 'no'"),
        ({"options": {}, "built": {"item": {}}}, "refused - it needs a seed -, where it was to build"),
        ({"options": {}, "refused": "it wants a seed"}, "refused with 'it needs a seed', not 'it wants a seed'"),
        ({"options": {"seed": "crash.txt"}, "refused": "no"}, "build raised KeyError: 'crash'"),
    ]
    for given, why in wrong:
        assert builds(tmp_path, [BUILDS[1], given]).faults == [f"echo.json, build 1: {why}"]


def test_texstage_kinds_check_fails_when_there_is_nothing_to_check(capsys, monkeypatch):
    monkeypatch.setattr(registry, "found", lambda: ())
    assert cli.main(["kinds", "check"]) == 1
    assert capsys.readouterr().err.startswith("nothing to check: no kinds are installed")
    assert cli.main(["kinds"]) == 0                                             # listing none is no failure


def test_texstage_kinds_check_fails_for_a_kind_that_cannot_be_used(capsys, monkeypatch):
    """Alone - no other kind fails beside it."""
    class Dist:
        name, version = "some-kinds", "2.0.0"

    class Point:
        name, value, dist = "future", "some_kinds:Future", Dist()

        def load(self):
            return type("Future", (Echo,), {"NAME": "future", "API": 1})

    monkeypatch.setattr(registry, "found", lambda: tuple(registry.read([Point()])))
    assert cli.main(["kinds", "check"]) == 1 and cli.main(["kinds", "check", "future"]) == 1
    assert "future (some-kinds 2.0.0): cannot be used - it implements API 1, this texstage API 0" in capsys.readouterr().out


def test_a_name_that_only_reads_like_one_and_the_stack_the_kit_asks_for(tmp_path, monkeypatch):
    import threading

    class Reads:
        def __str__(self):
            return "echo"

    found = faults(broken(NAME=Reads()), tmp_path)
    assert len(found) == 1 and found[0].startswith("NAME <") and "lower case letters" in found[0]
    asked, real = [], threading.stack_size

    def stack_size(*size):
        asked.append(size)
        return real(*size)

    monkeypatch.setattr(threading, "stack_size", stack_size)
    before = real()
    assert faults(Echo(), tmp_path) == []
    assert asked == [(kit.STACK,), (before,)] and real() == before         # a worker's for its thread, then as it was


def test_texstage_kinds_check_tells_the_kit_which_kinds_are_installed(capsys, monkeypatch):
    installed()
    seen = []
    real = kit.check

    def check(kind, name=None, folder=None, known=None):
        seen.append((name, known))
        return real(kind, name, folder, known)

    monkeypatch.setattr(kit, "check", check)
    assert cli.main(["kinds", "check", "triples"]) == 0
    assert seen == [("triples", set(FOUR))] and "warning" not in capsys.readouterr().out
