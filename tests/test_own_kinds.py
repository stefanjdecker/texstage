# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage's own kinds - choice, number, text (texstage/activities/kinds; the plan of F2, 4.8, package 9) -
and what the core gained with them: the entries of choice and number (kind.py: Entry), their shape
(entries.py), a reference as an entry of the kind's input (Kind.reference), the option types Number and
InBody (options.py), a tally labelled by its choices and a number step's numbers for its histogram
(reduce.py). Over WebSockets, on a server of the core's type: phones choosing, counting and answering, and
the reveal judging them. F1's type refuses a deck of theirs."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from test_activity import KEY, receive
from texstage.activities import registry
from texstage.activities.entries import Rules, shaped
from texstage.activities.kind import Entry, Kind, Step, kept, referenced
from texstage.activities.kinds import Choice, Number, Text
from texstage.activities.options import InBody, Number as NumberOption, Options, Unbuildable
from texstage.activities.phases import Refused
from texstage.build.bundle import bundle_id
from texstage.server import activity as f1_activity
from texstage.server import types as stage_types
from texstage.server.app import ServerConfig, create_app
from texstage.server.game import Settings

BOX = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
NL = chr(10)


@pytest.fixture(autouse=True)
def f1_again():
    yield
    stage_types.use("f1")                               # (the type a server runs is the process's: F1's after)


def own_kinds() -> dict:
    """The registry's kinds, texstage's own among them - found through texstage's entry points, so only where
    texstage is installed: run from its source alone (PYTHONPATH=src), there are none, and the test is skipped.
    Installed without them, it fails: an old texstage.egg-info ahead of the installed one on sys.path."""
    try:
        importlib.metadata.distribution("texstage")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("texstage is not installed (pip install -e .): its entry points are not there")
    found = {f.name: f for f in registry.found()}
    missing = sorted({"choice", "number", "text"} - set(found))
    assert not missing, (f"texstage's entry points name no {missing} - is an old texstage.egg-info ahead of the "
                         "installed texstage on sys.path? pip install --no-deps --no-build-isolation -e .")
    return found


# ------------------------------------------------------------------ the contract and the core
def test_an_entry_as_the_core_keeps_it_and_hands_it_to_a_worker():
    for entry, stored in ((Entry(text="a"), {"text": "a"}), (Entry(fields=("a", "b")), {"fields": ["a", "b"]}),
                          (Entry(choice=(0, 2)), {"choice": [0, 2]}), (Entry(number=3.5), {"number": 3.5}),
                          (Entry(number=0), {"number": 0})):
        assert entry.stored() == stored and Entry.of(json.loads(json.dumps(stored))) == entry
    for wrong in (Entry(), Entry(text="a", choice=(1,))):
        with pytest.raises(ValueError):
            wrong.stored()
    assert Kind().reference(Step({}), "SELECT 1") == Entry(text="SELECT 1")      # (by default a reference's text)


def test_what_a_kinds_normalize_gives_is_held_against_what_the_core_keeps():
    """kind.kept, for the worker and the kit: one field, the kind's input's, JSON without NaN - else the
    input is unchecked (never the student's), and no window is sent what a browser cannot read."""
    class Code(Kind):
        INPUT = "code"
    assert kept(Number(), Entry(number=12.5)) == {"number": 12.5} and kept(Code(), Entry(text="q")) == {"text": "q"}
    for kind, entry, why in ((Number(), Entry(number=float("nan")), "cannot keep"), (Number(), Entry(text="12"), "not the kind's input"),
                             (Choice(), Entry(choice=(0,), text="x"), "cannot keep"), (Text(), "Berlin", "not an Entry")):
        with pytest.raises(ValueError, match=why):
            kept(kind, entry)


def test_a_decks_options_and_references_are_read_alike():
    """kinds.option_text and text_reference, options.unescaped (the build's rule too): an option as the build
    passes it on and a reference as written read alike - also a formula a line broke -; a formula keeps its
    escapes; accents are their letters; a tie that joins text is a space, a tilde that joins nothing stays;
    what plain() keeps of an answer."""
    from texstage.activities.kinds import option_text, plain, text_reference
    from texstage.activities.options import unescaped
    B = chr(92)
    n_tilde = chr(0xF1)
    assert unescaped("R" + B + "&D, 50" + B + "% and $" + B + "{A" + B + "}$, " + B + "$5") == "R&D, 50% and $" + B + "{A" + B + "}$, $5"
    assert unescaped("Espa" + B + "~na " + B + "^" + B + "^xsd:int " + B + "^foaf:knows") == (
        "Espa" + B + "~na ^^xsd:int ^foaf:knows")                     # (\~ an accent, the kinds'; \^ a key's ^)
    for option, reference in (("$" + B + "sigma $", "$" + B + "sigma" + NL + "$"), ("R&D", "R" + B + "&D"),
                              ("Espa" + B + "~na", "Espa" + B + "~{n}a"), ("New~York", "New~York"),
                              ("$" + B + "{A, B" + B + "}$", "$" + B + "{A," + NL + "B" + B + "}$"),     # (a line broke it)
                              (B + "textasciitilde /bin", B + "textasciitilde{}/bin"), (B + "c {c}a", B + "c{c}a")):
        assert option_text(option) == option_text(reference, verbatim=True), (option, reference)
    assert [option_text(o) for o in ("$" + B + "{A, B" + B + "}$", "~/bin", "New~York", "Dr.~Smith", "Espa" + B + "~na",
                                     B + "'e", B + '"o', B + "~{}/bin", B + "textasciitilde user", B + "cite{x}",
                                     "example.org/" + B + "~{}user", B + "textasciitildebin", B + "c ca")] == [
        "$" + B + "{A, B" + B + "}$", "~/bin", "New York", "Dr. Smith", "Espa" + n_tilde + "a", chr(0xE9), chr(0xF6), "~/bin",
        "~user", B + "cite{x}", "example.org/~user", B + "textasciitildebin", chr(0xE7) + "a"]   # (\~{}: a tilde, no tie;
    #                                                                     \c ca: as \tl_to_str passes \c{c}a on)
    assert [text_reference(r) for r in ("~/bin", "~", "R" + B + "&D", "C:" + B + B + "Users", "Dr.~Smith", "z.~B.",
                                        "Espa" + B + "~na", "example.org/" + B + "~{}user", "~alice", "host:~/bin",
                                        "$" + B + "{A," + NL + "B" + B + "}$", B + B + "^o")] == [
        "~/bin", "~", "R&D", "C:" + B + "Users", "Dr. Smith", "z. B.", "Espa" + n_tilde + "a", "example.org/~user", "~alice",
        "host:~/bin", "$" + B + "{A, B" + B + "}$", B + "^o"]   # (a tilde that joins nothing: as written; a formula a line
    #                                                             broke keeps its escapes; \^ is never an accent)
    zwj, new = chr(0x200D), chr(0x3FFFD)                                 # (a joiner; a code point no table names yet)
    assert [plain(t) for t in ("a" + zwj + "b", "x" + chr(0x200B) + "y", new, "R" + chr(0xAD) + "x")] == ["a" + zwj + "b", "xy", new, "Rx"]
    assert [plain(t) for t in (zwj, "Berlin" + zwj, zwj + "x", "x " + zwj + " y", chr(0xFDD0) + "x", chr(0x1FFFE) + "y")] == [
        "", "Berlin", "x", "x y", "x", "y"]                              # (a joiner at an end; noncharacters)


def test_the_archive_writes_a_choice_by_its_options_and_a_number_with_every_digit():
    from texstage.server.activities import written
    item = {"options": ["Paris", "Nice", "$" + chr(92) + "sigma$"]}
    assert [written({"choice": c}, item) for c in ([0], [1, 2], [7])] == ["Paris", "Nice + $" + chr(92) + "sigma$", "7"]
    assert [written({"number": n}, item) for n in (1234567.5, 3.14159265, 0.00001, 42)] == ["1234567.5", "3.14159265", "1e-05", "42"]
    assert written({"text": "=1+2"}, item) == "=1+2" and written({"fields": ["a", "b"]}, item) == "a | b"   # (sheets.py: the cell)


def test_a_reference_is_an_entry_of_the_kinds_input():
    step = Step({"options": ["Paris", "Nice", "Lyon"], "select": "many"}, {"reference": ["Paris" + NL + "Lyon"]})
    assert Choice().reference(step, "Paris" + NL + "Lyon") == Entry(choice=(0, 2))
    assert [c.key for c in referenced(Choice(), Choice().prepare({}, {}, {}), step)] == ["Paris" + NL + "Lyon"]
    assert Number().reference(Step({}), "42") == Entry(number=42)
    assert Number().reference(Step({}), "1099511627776") == Entry(number=2**40)          # (whole: exactly)


def test_the_core_shapes_a_choice_and_a_number():
    one = Rules.of({"options": ["A", "B", "C"]}, Choice())
    many = Rules.of({"options": ["A", "B", "C"], "select": "many"}, Choice())
    assert (one.options, one.many, one.gap_ms, one.limit, one.counts) == (3, False, 1000, 10, "latest")
    assert many.many
    assert shaped(many, {"choice": [2, 0, 2]}) == {"choice": [0, 2]}                # (in order, each once)
    assert shaped(one, {"choice": [1]}) == {"choice": [1]} and shaped(one, {"choice": [1, 1]}) == {"choice": [1]}
    for sent, code in (({"choice": []}, "choice"), ({"choice": [0, 1]}, "choice"), ({"choice": [3]}, "invalid"),
                       ({"choice": [True]}, "invalid"), ({"choice": "0"}, "invalid"), ({"text": "A"}, "invalid")):
        with pytest.raises(Refused) as refused:
            shaped(one, sent)
        assert refused.value.code == code, sent
    with pytest.raises(ValueError):
        Rules.of({"options": ["A"]}, Choice())                                       # (a choice of one is none)
    with pytest.raises(ValueError):
        Rules.of({"options": ["A", "B"], "select": "some"}, Choice())
    numbers = Rules.of({}, Number())
    assert numbers.gap_ms == 2000 and shaped(numbers, {"number": -3.5}) == {"number": -3.5}
    for sent, code in (({"number": "12"}, "number"), ({"number": True}, "number"), ({"number": float("nan")}, "number"),
                       ({"number": 1e16}, "too-large"), ({"number": -10**400}, "too-large"), ({}, "number")):
        with pytest.raises(Refused) as refused:                                       # (10^400: larger than a
            shaped(numbers, sent)                                                     # float, compared - no error)
        assert refused.value.code == code, sent
    assert shaped(numbers, {"number": 10**15}) == {"number": 10**15}
    assert shaped(Rules.of({}, Text()), {"text": " Berlin "}) == {"text": " Berlin "}   # (cleaning it: the kind's)


def test_the_option_types_number_and_in_body():
    declared = {"tolerance": NumberOption(0, 100), "reference": InBody()}
    assert Options(declared, {"tolerance": "0.5"})["tolerance"] == 0.5
    assert Options(declared, {"tolerance": ".5"})["tolerance"] == 0.5
    assert Options(declared, {})["tolerance"] == 0 and Options(declared, {})["reference"] is None
    for given in ("1e3", "-1", "101", "0x10", "1,5", " "):
        with pytest.raises(Unbuildable):
            Options(declared, {"tolerance": given})["tolerance"]
    with pytest.raises(Unbuildable, match="write .reference"):
        Options(declared, {"reference": "answer.txt"})["reference"]
    assert Options(declared, {}).unused({"references": ["42"]}) == []              # (a body the kind takes)


def test_texstages_own_kinds_are_found_as_every_kind_is():
    found = own_kinds()
    assert {found[n].package for n in ("choice", "number", "text")} == {"texstage"}
    assert [type(registry.kind(n)) for n in ("choice", "number", "text")] == [Choice, Number, Text]


def test_f1s_type_refuses_a_deck_of_a_kind_it_never_had():
    deck = {"items": {"activity": {"crowd": {"input": "tuple"}, "q": {"input": "code", "engine": "sql"}}}}
    assert f1_activity.refuses(deck) is None
    deck["items"]["activity"]["capital"] = {"kind": "choice", "options": ["A", "B"]}
    assert f1_activity.refuses(deck) == ("the activity capital is of the kind choice, which this server's activity type "
                                         "does not run - start it with texstage serve --activities core")
    assert f1_activity.refuses({}) is None


# ------------------------------------------------------------------ over WebSockets
ITEMS = {
    "capital": {"kind": "choice", "limit": 10, "options": ["Paris", "Lyon", "Nice", "Marseille"], "select": "one"},
    "coast": {"kind": "choice", "limit": 10, "options": ["Paris", "Nice", "Lyon", "Marseille"], "select": "many"},
    "rows": {"kind": "number", "limit": 5, "tolerance": 0.5},
    "word": {"kind": "text", "limit": 5},
    "again": {"kind": "choice", "limit": 10, "options": ["Paris", "Nice", "Lyon", "Marseille"], "select": "many",
              "counts": "all"},
    "both": {"kind": "text", "limit": 5, "counts": "all"},
}
REFERENCES = {"capital": ["Paris"], "coast": ["Nice" + NL + "Marseille"], "rows": ["12"], "word": ["Berlin"],
              "again": ["Nice" + NL + "Marseille"], "both": ["Berlin", "Bonn"]}
SHOWS = {257: "capital", 258: "coast", 259: "rows", 260: "word", 261: "again", 262: "both"}


def own_bundle(folder: Path) -> str:
    """A bundle as build/activity.py writes one, with an activity of each of texstage's own kinds."""
    pngs = {f"slides/{hashlib.sha256(d).hexdigest()[:16]}.png": d for d in (b"one", b"two")}
    s1, s2 = list(pngs)
    deck = {"format": 2, "deck": "own", "name": "Own", "types": ["activity"], "image": {"width": 1920, "height": 1080},
            "slides": [{"id": sid, "image": s2 if sid in SHOWS else s1}
                       | ({"live": [{"type": "activity", "item": SHOWS[sid], "rects": {"box": BOX}}]} if sid in SHOWS else {})
                       for sid in (256, 257, 258, 259, 260, 261, 262)],
            "items": {"activity": ITEMS}}
    keys = {"format": 2, "deck": "own", "items": {"activity": {a: {"reference": r} for a, r in REFERENCES.items()}}}
    bid = bundle_id(deck, keys)
    for rel, data in pngs.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    for rel, data in (("deck.json", deck), ("keys.json", keys)):
        (folder / rel).write_text(json.dumps(data | {"bundle": bid}), encoding="utf-8")
    return bid


ASIDE: dict[int, list] = {}


def recv(ws, t=None, until=None, tries: int = 400):
    aside = ASIDE.setdefault(id(ws), [])
    for _ in range(tries):
        m = aside.pop(0) if aside else receive(ws)
        if (t is None or m["t"] == t) and (until is None or until(m)):
            return m
    raise AssertionError(f"no {t} message")


def ask(ws, n, t: str, **msg) -> dict:
    ws.send_json({"t": t, "id": n, **msg})
    aside = ASIDE.setdefault(id(ws), [])
    for _ in range(400):
        m = receive(ws)
        if m.get("re") == n and m["t"] in ("ok", "error"):
            return m
        aside.append(m)
    raise AssertionError(f"no answer to {t}")


def view(st, n: int, activity: str, until, window: str = "display") -> dict:
    """The activity's picture, asked for until it is as it is to be: the pool checks in its own time."""
    for i in range(400):
        pic = ask(st, f"{n}.{i}", "activity.view", activity=activity, window=window)["picture"]
        if until(pic):
            return pic
        time.sleep(0.05)
    panel = ask(st, f"{n}.why", "activity.view", activity=activity)                 # (the panel's: why not)
    raise AssertionError(f"the picture never came: {pic} - the panel: unchecked {panel['picture'].get('unchecked')}, "
                         f"failed {panel.get('failed')}, store {panel.get('store')}")


def verdicts(phone, activity: str, count: int) -> list:
    """A phone's own entries' verdicts, once the reveal has given them."""
    def ready(m):
        mine = (m.get("activity") or {}).get("mine") or {}
        return mine.get("activity") == activity and len([e for e in mine.get("entries", []) if e.get("verdict")]) >= count
    return [e.get("verdict") for e in recv(phone, "state", until=ready)["activity"]["mine"]["entries"]]


def test_a_lecture_with_texstages_own_kinds(tmp_path):
    """A choice of one and of several, a number, a short answer: the phones send them, the pool checks them,
    the projector's picture counts them - a tally in the deck's order with its labels, a number step's
    numbers -, and the reveal judges them: a choice by the reference's, a number within the tolerance, a text
    as the quiz compares text answers."""
    own_kinds()
    bid = own_bundle(tmp_path / "bundles" / "own.bundle")
    config = ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                          presenter_key=KEY, settings=Settings(get_ready_ms=0), activities="core", workers=1,
                          pool={"spare": False})
    with TestClient(create_app(config)) as client, client.websocket_connect("/ws") as st, \
            client.websocket_connect("/ws") as ada, client.websocket_connect("/ws") as bea, \
            client.websocket_connect("/ws") as cy:
        ASIDE.clear()
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": "own", "bundle": bid, "id": 1})
        pin = recv(st, "welcome")["pin"]
        for phone, name in ((ada, "Ada"), (bea, "Bea"), (cy, "Cy")):
            phone.send_json({"t": "join", "pin": pin, "nickname": name, "id": "j"})
            assert set(recv(phone, "welcome")["kindFiles"]) == {"choice", "number", "text"}
        # a choice of one: a tap each, counted per option in the deck's order - none left out
        assert ask(st, 2, "slide", slide=257)["t"] == "ok"
        part = recv(ada, "activity.step", until=lambda m: (m["step"] or {}).get("activity") == "capital")["step"]
        assert (part["input"], part["options"], part["select"]) == ("choice", ITEMS["capital"]["options"], "one")
        assert ask(bea, 3, "activity.enter", activity="capital", entry="bea-capital-0", choice=[0, 1])["error"] == "choice"
        assert ask(ada, 4, "activity.enter", activity="capital", entry="ada-capital-1", choice=[0])["t"] == "ok"
        assert ask(bea, 4, "activity.enter", activity="capital", entry="bea-capital-1", choice=[2])["t"] == "ok"
        pic = view(st, 5, "capital", lambda p: sum(g["n"] for g in p["groups"]) == 2 and not p.get("waiting"))
        assert pic["kind"] == "tally" and [(g["label"], g["n"]) for g in pic["groups"]] == [
            ("Paris", 1), ("Lyon", 0), ("Nice", 1), ("Marseille", 0)]
        assert not any(g.get("reference") for g in pic["groups"])                # (nothing of it before the reveal)
        assert ask(st, 6, "activity.reveal", activity="capital")["t"] == "ok"
        assert verdicts(ada, "capital", 1) == ["correct"] and verdicts(bea, "capital", 1) == ["incorrect"]
        # a choice of several: the references together are the right one
        assert ask(st, 7, "slide", slide=258)["t"] == "ok"
        assert ask(ada, 8, "activity.enter", activity="coast", entry="ada-coast-1", choice=[3, 1])["t"] == "ok"
        assert ask(bea, 8, "activity.enter", activity="coast", entry="bea-coast-1", choice=[1])["t"] == "ok"
        pic = view(st, 9, "coast", lambda p: sum(g["n"] for g in p["groups"]) == 2 and not p.get("waiting"))
        assert [(g["label"], g["n"]) for g in pic["groups"]] == [                     # (the groups: what is checked
            ("Paris", 0), ("Nice", 1), ("Lyon", 0), ("Marseille", 0), ("Nice" + NL + "Marseille", 1)]   # and judged)
        assert [(o["label"], o["n"], o["reference"]) for o in pic["options"]] == [    # what the class sees: per option
            ("Paris", 0, False), ("Nice", 2, False), ("Lyon", 0, False), ("Marseille", 1, False)]
        assert ask(st, 10, "activity.reveal", activity="coast")["t"] == "ok"
        assert verdicts(ada, "coast", 1) == ["correct"] and verdicts(bea, "coast", 1) == ["incorrect"]
        pic = view(st, "10b", "coast", lambda p: p["revealed"])
        assert [o["label"] for o in pic["options"] if o["reference"]] == ["Nice", "Marseille"] and pic["right"] == 1
        # a number: within the tolerance; the picture has every number for a histogram
        assert ask(st, 11, "slide", slide=259)["t"] == "ok"
        assert ask(bea, 12, "activity.enter", activity="rows", entry="bea-rows-0", number="13")["error"] == "number"
        huge = ask(bea, "12b", "activity.enter", activity="rows", entry="bea-rows-00", number=10**400)    # (no float
        assert huge["error"] == "too-large"                                                            # holds it)
        assert ask(bea, 13, "activity.enter", activity="rows", entry="bea-rows-1", number=13)["t"] == "ok"
        assert ask(ada, 13, "activity.enter", activity="rows", entry="ada-rows-1", number=12.4)["t"] == "ok"
        assert ask(cy, 13, "activity.enter", activity="rows", entry="cy-rows-1", number=12.4)["t"] == "ok"
        pic = view(st, 14, "rows", lambda p: sum(x[1] for x in p.get("numbers") or []) == 3 and not p.get("waiting"))
        assert pic["numbers"] == [[12.4, 2], [13, 1]] and "right" not in pic          # (in order, by students; no
        #                                                                           verdict before the reveal)
        assert ask(st, 15, "activity.reveal", activity="rows")["t"] == "ok"
        assert verdicts(ada, "rows", 1) == ["correct"] and verdicts(bea, "rows", 1) == ["incorrect"]
        pic = view(st, "15b", "rows", lambda p: p["revealed"])
        assert pic["numbers"] == [[12.4, 2, "correct"], [13, 1, "incorrect"]] and pic["right"] == 2
        # a short answer: case, accents and spacing do not matter
        assert ask(st, 16, "slide", slide=260)["t"] == "ok"
        assert ask(ada, 17, "activity.enter", activity="word", entry="ada-word-1", text="  BERLIN ")["t"] == "ok"
        assert ask(bea, 17, "activity.enter", activity="word", entry="bea-word-1", text="Bonn")["t"] == "ok"
        assert ask(cy, 17, "activity.enter", activity="word", entry="cy-word-1", text="=1+2")["t"] == "ok"
        pic = view(st, 18, "word", lambda p: sum(g["n"] for g in p["groups"]) == 3 and not p.get("waiting"))
        assert sorted(g["example"]["text"] for g in pic["groups"]) == ["=1+2", "BERLIN", "Bonn"]   # (as normalize gave it)
        assert "numbers" not in pic                                                  # (a text step has no histogram)
        assert ask(st, 19, "activity.reveal", activity="word")["t"] == "ok"
        assert verdicts(ada, "word", 1) == ["correct"] and verdicts(bea, "word", 1) == ["incorrect"]
        # counts=all: a student's two choices count her once per option, and once among the right
        assert ask(st, "c1", "slide", slide=261)["t"] == "ok"
        assert ask(ada, "c2", "activity.enter", activity="again", entry="ada-again-1", choice=[1, 3])["t"] == "ok"
        time.sleep(1.1)                                                              # (a choice's gap: 1 s)
        assert ask(ada, "c3", "activity.enter", activity="again", entry="ada-again-2", choice=[1])["t"] == "ok"
        assert ask(st, "c4", "activity.reveal", activity="again")["t"] == "ok"
        pic = view(st, "c5", "again", lambda p: p["revealed"] and sum(g["n"] for g in p["groups"]) == 2 and not p.get("waiting"))
        assert [(o["label"], o["n"]) for o in pic["options"]] == [("Paris", 0), ("Nice", 1), ("Lyon", 0), ("Marseille", 1)]
        assert pic["right"] == 1
        # two references, and a student who gives both: right once
        assert ask(st, "d1", "slide", slide=262)["t"] == "ok"
        assert ask(bea, "d2", "activity.enter", activity="both", entry="bea-both-1", text="Berlin")["t"] == "ok"
        time.sleep(2.1)                                                              # (a text's gap: 2 s)
        assert ask(bea, "d3", "activity.enter", activity="both", entry="bea-both-2", text="Bonn")["t"] == "ok"
        assert ask(st, "d4", "activity.reveal", activity="both")["t"] == "ok"
        pic = view(st, "d5", "both", lambda p: p["revealed"] and sum(g["n"] for g in p["groups"]) == 2 and not p.get("waiting"))
        assert [g["verdict"] for g in pic["groups"]] == ["correct", "correct"] and pic["right"] == 1
        # a number the lecturer hides has no bar
        panel = view(st, 20, "rows", lambda p: len(p["groups"]) == 2, window="stage")
        thirteen = next(g["id"] for g in panel["groups"] if g["example"] == {"number": 13})
        assert ask(st, 21, "activity.moderate", activity="rows", act="hide", group=thirteen)["t"] == "ok"
        assert view(st, 22, "rows", lambda p: len(p["numbers"]) == 1)["numbers"] == [[12.4, 2, "correct"]]
        # the archive: a choice by its options' texts, a number with all its digits
        game = recv(st, "state")["session"]["id"]
        z = client.get(f"/api/archive/{game}.zip", headers={"X-Texquiz-Key": KEY})
        files = zipfile.ZipFile(io.BytesIO(z.content))

        def written(aid):
            text = files.read(f"activity-{aid}.csv").decode("utf-8-sig")
            assert chr(13) * 2 not in text                                         # (CSV's line ends, once)
            return [row[3] for row in csv.reader(text.splitlines())][1:]
        assert (written("capital"), written("coast")) == (["Paris", "Nice"], ["Nice + Marseille", "Nice"])
        assert (sorted(written("rows")), written("word")) == (["12.4", "12.4", "13"], ["  BERLIN ", "Bonn", "'=1+2"])   # (as sent;
        #                                                         a formula shown, not run: sheets.py)
