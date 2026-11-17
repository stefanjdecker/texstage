# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""maintenance/check_kinds_served.py, which CI runs in the server's image and with the installed wheels (the
plan of F2, package 11). What it sends and what it lets pass are held against made-up phones and pictures - a
check whose status is not ok, an entry not checked, a reference judged wrong, a kind without its texts, a slide
that reveals, a crowd graph's picture without the terms sent (the review: such faults passed, as a correct
server never shows them) -; its run is held to those rules in this process, with a server whose answers are
spoiled on their way to the check - an entry its kind does not take, a kind's file without its policy, a kind
without its texts, a picture that drops the terms -, the server's key starting with "-" as one in 64 does; and
it is run: its own deck, an activity of each of texstage's kinds made by texstage's build, passes; a deck the
server refuses - a kind newer than its own - fails with the server's reason; a deck without activities is
passed over, and with --every fails."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "maintenance" / "check_kinds_served.py"

pytest.importorskip("websockets")
pytest.importorskip("pyoxigraph")
from texstage.activities import registry  # noqa: E402

KINDS = {"triples", "sparql-query", "turtle-graph", "sql-query", "choice", "number", "text"}
if KINDS - {f.name for f in registry.found() if not f.fault}:
    pytest.skip("the kinds are not installed: pip install --no-deps -e kinds/...", allow_module_level=True)

spec = importlib.util.spec_from_file_location("check_kinds_served", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, errors="replace",
                          timeout=600)


def rewrite(bundle: Path, change) -> None:
    """A built deck changed - change(deck, keys) - with the bundle ID its files then have: a deck whose files and
    ID disagree is skipped for that, not for what the test means."""
    from texstage.build.bundle import bundle_id
    files = {name: bundle / name for name in ("deck.json", "keys.json")}
    deck, keys = (json.loads(files[n].read_text(encoding="utf-8")) for n in ("deck.json", "keys.json"))
    change(deck, keys)
    del deck["bundle"], keys["bundle"]
    bid = bundle_id(deck, keys)
    for name, data in (("deck.json", deck), ("keys.json", keys)):
        files[name].write_text(json.dumps(data | {"bundle": bid}), encoding="utf-8")


def test_its_own_deck_is_texstages_build_of_an_activity_of_each_kind(tmp_path):
    folder = check.probe_bundle(tmp_path / "bundles")
    deck, keys = (json.loads((folder / "probe.bundle" / n).read_text(encoding="utf-8")) for n in ("deck.json", "keys.json"))
    items, secret = deck["items"]["activity"], keys["items"]["activity"]
    assert [items[a]["kind"] for a in items] == [kind for _, kind, *_ in check.PROBE] and set(deck["kinds"]) == KINDS
    assert {k: v["package"] for k, v in deck["kinds"].items()} == {
        "triples": "texstage-kinds-rdf", "sparql-query": "texstage-kinds-rdf", "turtle-graph": "texstage-kinds-rdf",
        "sql-query": "texstage-kinds-sql", "choice": "texstage", "number": "texstage", "text": "texstage"}
    assert set(secret) == set(items) - {"crowd"} and all(secret[a]["referenceKeys"] for a in secret)  # the build ran them
    assert check.shown_on(deck) == {a: 257 + i for i, a in enumerate(items)}
    # a phone sends each reference as its kind takes a reference as an entry - a crowd graph a term per field
    assert {a: check.entry_for(items[a], secret.get(a, {})) for a in items} == {
        "crowd": ({"fields": [":probe0", ":probe1", ":probe2"]}, "3 terms"),
        "packing": ({"text": "SELECT item FROM packing WHERE quantity = 6;"}, "its first reference"),
        "rivers": ({"text": "SELECT ?name WHERE { ?r a :River ; :name ?name }"}, "its first reference"),
        "knows": ({"text": "ex:alice ex:knows ex:bob ."}, "its first reference"),
        "colour": ({"choice": [1]}, "its first reference"),
        "answer": ({"number": 42}, "its first reference"),
        "language": ({"text": "SPARQL"}, "its first reference")}


def test_without_a_reference_a_phone_sends_what_the_input_takes():
    assert check.entry_for({"kind": "choice", "options": ["A", "B"], "select": "one"}, {}) == ({"choice": [0]}, "its first option")
    assert check.entry_for({"kind": "number"}, {}) == ({"number": 1}, "a number")
    assert check.entry_for({"kind": "text"}, {}) == ({"text": "probe"}, "a text")
    assert check.entry_for({"kind": "triples", "fields": ["Who", "Whom"]}, {}) == ({"fields": [":probe0", ":probe1"]}, "2 terms")
    assert check.entry_for({"input": "tuple"}, {})[0] == {"fields": [":probe0", ":probe1", ":probe2"]}  # a deck from before kinds
    sent, how = check.entry_for({"kind": "sql-query"}, {})                 # a code activity without a reference
    assert sent is None and how == "nothing: no reference, and its input is code"


def test_an_entry_passes_when_its_check_is_ok_and_its_reference_judged_correct():
    ok = {"id": "e", "check": "checked", "status": "ok"}
    assert check.judged(ok, referenced=False) is None
    assert check.judged(ok | {"verdict": "correct"}, referenced=True) is None
    assert check.judged(ok | {"verdict": "incorrect"}, referenced=True) == "its entry is judged 'incorrect', not correct"
    assert check.judged(ok, referenced=True) == "its entry is judged None, not correct"           # no verdict where due
    assert check.judged(ok | {"status": "refused"}, referenced=False) == "its entry's check says 'refused'"
    assert check.judged(ok | {"status": "invalid", "message": {"code": "at"}}, referenced=False) == \
        "its entry's check says 'invalid' ({\"code\": \"at\"})"
    assert check.judged({"id": "e", "check": "unchecked"}, referenced=False) == "its entry is 'unchecked', not checked"
    assert check.judged({"id": "e", "check": "received"}, referenced=False) == "its entry is 'received', not checked"
    assert check.judged(None, referenced=False) == "the phone does not have its entry"


def test_every_kind_the_deck_names_is_served_with_its_texts():
    good = {"hash": "h", "phone": ["texts/en.js", "texts/de.js"], "window": []}
    assert check.files_fault({"sql-query"}, {"sql-query": good}) is None
    assert check.files_fault({"sql-query", "choice"}, {"sql-query": good}) == "the kind choice has no files for the browser"
    assert check.files_fault({"sql-query"}, {"sql-query": good | {"phone": []}}) == \
        "the kind sql-query has no files for the browser"
    assert check.files_fault({"sql-query"}, {"sql-query": good | {"phone": ["web/hint.js"]}}) == \
        "the kind sql-query's files for the browser have no texts"


def test_a_crowd_graphs_picture_shows_the_terms_its_phone_sent():
    sent = {"fields": [":a", ":p", ":b"]}
    terms = [{"role": "node", "label": ":a"}, {"role": "label", "label": ":p"}, {"role": "node", "label": ":b"}]
    good = {"reduction": "crowd", "kind": "graph", "min": 1, "review": False, "terms": terms,
            "nodes": [{"id": "ka", "label": ":a"}, {"id": "kb", "label": ":b"}],
            "edges": [{"s": "ka", "o": "kb", "p": "kp", "label": ":p"}]}
    assert check.drawn(good, sent) is None
    assert check.drawn(good, {"fields": [" :a  ", ":p", ":b"]}) is None          # cleaned, as texstage cleans a term
    assert check.drawn(good | {"terms": terms[:2]}, sent) == "its picture lists no term :b of those the phone sent"
    assert check.drawn(good | {"terms": [], "nodes": [], "edges": []}, sent) == \
        "its picture lists no term :a, :p, :b of those the phone sent"
    assert check.drawn(good | {"terms": [terms[0], terms[1] | {"role": "node"}, terms[2]]}, sent) == \
        "its picture lists no term :p of those the phone sent"                    # a label listed as a node
    assert check.drawn(good | {"edges": []}, sent) == "its picture draws no edge from :a to :b labelled :p"
    assert check.drawn(good | {"edges": [{"s": "kb", "o": "ka", "label": ":p"}]}, sent) == \
        "its picture draws no edge from :a to :b labelled :p"                     # the wrong way round
    assert check.drawn(good | {"edges": [{"s": "ka", "o": "kb", "label": ":q"}]}, sent) == \
        "its picture draws no edge from :a to :b labelled :p"
    # a triple of one student is not drawn where it needs two, or the lecturer's approval: the panel lists it
    assert check.drawn(good | {"edges": [], "min": 2}, sent) is None
    assert check.drawn(good | {"edges": [], "review": True}, sent) is None
    assert check.drawn(good | {"terms": [], "min": 2}, sent) == \
        "its picture lists no term :a, :p, :b of those the phone sent"
    pair = good | {"terms": [terms[0], terms[2]], "edges": [{"s": "ka", "o": "kb", "p": None, "label": ""}]}
    assert check.drawn(pair, {"fields": [":a", ":b"]}) is None                     # two fields: an edge without a label
    assert check.drawn(pair | {"edges": []}, {"fields": [":a", ":b"]}) == "its picture draws no edge from :a to :b"
    assert check.drawn({"reduction": "groups", "groups": []}, {"text": "SELECT 1"}) is None   # other pictures count


@pytest.fixture
def serving(tmp_path, monkeypatch):
    """start(*activities): a server of the check's (check.Server) with a deck of those of its own activities,
    for check.served in this process - its key starting with "-", as one key in 64 does, and taken as the key."""
    monkeypatch.setattr(check.secrets, "token_urlsafe", lambda n: "-" + "k" * (n + 7))
    servers = []

    def start(*activities):
        folder = check.probe_bundle(tmp_path / "bundles", [p for p in check.PROBE if p[0] in activities])
        server = check.Server(folder, tmp_path)
        servers.append(server)
        assert server.key.startswith("-") and server.started()["activities"] == "core", server.tail()
        assert server.get("/api/decks", key=True)[0] == 200
        return server, folder / "probe.bundle"
    yield start
    for server in servers:
        server.stop()


def test_a_run_fails_on_an_entry_whose_check_is_not_ok(serving, monkeypatch):
    server, deck = serving("packing")
    monkeypatch.setattr(check, "entry_for", lambda item, keys: ({"text": "SELEC item FROM packing;"}, "no SQL"))
    with pytest.raises(SystemExit, match="probe: packing: its entry's check says '"):   # (the kind's word for it)
        check.served(server, deck, True)


def test_a_run_fails_on_a_kinds_file_without_its_policy(serving, monkeypatch):
    server, deck = serving("crowd")
    get = check.Server.get

    def unguarded(self, path, key=False):
        status, headers, body = get(self, path, key)
        return (status, {}, body) if path.startswith("/kinds/") else (status, headers, body)
    monkeypatch.setattr(check.Server, "get", unguarded)
    with pytest.raises(SystemExit, match=r"probe: the kind triples's file \S+: 200, policy None"):
        check.served(server, deck, True)


def test_a_run_fails_on_a_kind_served_without_its_files_for_the_browser(serving, monkeypatch):
    server, deck = serving("crowd")                    # (the review: files taken as listed - none, a check of nothing)
    recv = check.Socket.recv

    def unlisted(self, t, until=lambda m: True, timeout=30):
        m = recv(self, t, until, timeout)
        if m.get("t") == "welcome" and m.get("kindFiles"):
            m["kindFiles"] = {name: files | {"phone": []} for name, files in m["kindFiles"].items()}
        return m
    monkeypatch.setattr(check.Socket, "recv", unlisted)
    with pytest.raises(SystemExit, match="probe: the kind triples has no files for the browser"):
        check.served(server, deck, True)


def test_a_run_fails_on_a_crowd_graph_whose_picture_drops_the_terms(serving, monkeypatch):
    server, deck = serving("crowd")
    ask = check.Socket.ask

    def dropped(self, t, **message):
        got = ask(self, t, **message)
        if t == "activity.view":
            got["picture"] = got["picture"] | {"terms": [], "nodes": [], "edges": []}
        return got
    monkeypatch.setattr(check.Socket, "ask", dropped)
    with pytest.raises(SystemExit, match="probe: crowd: its picture lists no term :probe0, :probe1, :probe2"):
        check.served(server, deck, True)


def test_an_activity_is_opened_by_the_first_slide_that_opens_it():
    deck = {"slides": [{"id": 256},
                       {"id": 257, "live": [{"type": "activity", "item": "q", "phase": "revealed"}]},
                       {"id": 258, "live": [{"type": "quiz", "item": "x"}, {"type": "activity", "item": "q", "phase": "open"}]},
                       {"id": 259, "live": [{"type": "activity", "item": "q"}]},
                       {"id": 260, "live": [{"type": "activity", "item": "only-revealed", "phase": "revealed"}]}]}
    assert check.shown_on(deck) == {"q": 258}


def test_the_check_passes_where_the_server_checks_and_fails_where_it_cannot(tmp_path):
    from fake_bundle import make_bundle
    r = run()                                                              # its own deck
    assert r.returncode == 0, r.stdout + r.stderr
    for line in ("crowd (triples, texstage-kinds-rdf): 3 terms - checked, ok, in its picture",
                 "packing (sql-query, texstage-kinds-sql): its first reference - checked, ok, judged correct",
                 "colour (choice, texstage): its first reference - checked, ok, judged correct"):
        assert line in r.stdout, r.stdout
    assert r.stdout.rstrip().endswith("checked a phone's entry of 7 of their 7 activities in its pool")
    # beside a deck of quizzes alone, which is passed over - and with --every not
    mixed = check.probe_bundle(tmp_path / "mixed")
    make_bundle(mixed, deck="quizzes")
    r = run("--bundles", str(mixed))
    assert r.returncode == 0 and "7 of their 7 activities in its pool; passed over: quizzes (no activity)" in r.stdout, \
        r.stdout + r.stderr
    r = run("--bundles", str(mixed), "--every")
    assert r.returncode != 0 and "FAIL: quizzes: the deck has no live activity" in r.stderr, r.stdout + r.stderr
    quizzes = tmp_path / "quizzes"                                       # nothing checked is no pass
    make_bundle(quizzes, deck="quizzes")
    r = run("--bundles", str(quizzes))
    assert r.returncode != 0 and "FAIL: no activity was checked" in r.stderr, r.stdout + r.stderr
    # an activity that no slide opens - its one slide reveals it - is passed over, and with --every not
    hidden = check.probe_bundle(tmp_path / "hidden")
    rewrite(hidden / "probe.bundle", lambda deck, keys: deck["slides"][-2]["live"][0].update(phase="revealed"))
    r = run("--bundles", str(hidden))
    assert r.returncode == 0 and "6 of their 7 activities in its pool; passed over: probe: language" in r.stdout, \
        r.stdout + r.stderr
    assert "language (text, texstage): passed over - no slide opens it" in r.stdout
    r = run("--bundles", str(hidden), "--every")
    assert r.returncode != 0 and "FAIL: probe: not every activity was checked - passed over: probe: language" in r.stderr, \
        r.stdout + r.stderr
    # a deck built with a later kind than this server has: the server refuses it, and the check says why
    newer = check.probe_bundle(tmp_path / "newer")
    rewrite(newer / "probe.bundle", lambda deck, keys: deck["kinds"]["sql-query"].update(version="99.0.0"))
    r = run("--bundles", str(newer))
    assert r.returncode != 0 and "FAIL: the server did not take the deck probe" in r.stderr, r.stdout + r.stderr
    assert "install texstage-kinds-sql 99.0.0 or later" in r.stderr, r.stderr      # the server's reason, in its log
