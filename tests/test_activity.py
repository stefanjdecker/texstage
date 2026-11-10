# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Live activities on the server (server/activity.py; docs/live-activities-design.md, section 7):
the crowd graph and the clusters through the engine with a fake clock - the presenter window's
evaluation scripted -, a restarted server, the archive; and the whole over WebSockets. Then the
server's checks (checking.py; docs/architecture/activity-framework-plan.md, F1, 4.5 and 4.6) with a
pool of one worker: the references as the game starts, the texts as they come, internal, a restart
with texts waiting, the mode both writing down the differences, and over WebSockets the phones'
verdicts without a presenter window that evaluates."""
from __future__ import annotations

import concurrent.futures as cf
import csv
import hashlib
import io
import json
import queue
import re
import sqlite3
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from texstage.build.bundle import bundle_id
from texstage.server.app import ServerConfig, create_app
from texstage.server.bundles import BundleStore
from texstage.server.checking import COMPARE_COLUMNS, Checks, act_name
from texstage.server.game import Engine, GameError, Settings
from texstage.server.store import Store

sys.path.insert(0, str(Path(__file__).parent))           # the pool's workers import pool_engines (spawn: this path)

T0 = 1_800_000_000_000
KEY = "presenter-secret"
BOX = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
SEED = b'@prefix : <http://example.org/> .\n:kant :name "Kant" .\n'
SEED_NAME = f"data/{hashlib.sha256(SEED).hexdigest()[:16]}.ttl"
REFERENCE = "SELECT ?n WHERE { ?p :name ?n }"
RIGHT, WRONG = "SELECT ?n WHERE { ?p :name ?n }", "SELECT ?n WHER { ?p :name ?n }"
K1 = "0123456789abcdef"


def make_activity_bundle(folder: Path, crowd: dict | None = None, query: dict | None = None,
                         reference: str = REFERENCE, seed: bytes = SEED) -> str:
    """A format-2 bundle as build/activity.py writes one: a crowd graph on slides 257 and 258 (its
    frame's two steps), a query on 259; 256 and 260 ordinary slides."""
    pngs = {f"slides/{hashlib.sha256(d).hexdigest()[:16]}.png": d for d in (b"one", b"two")}
    s1, s2 = list(pngs)
    seed_name = f"data/{hashlib.sha256(seed).hexdigest()[:16]}.ttl"
    items = {"crowd": {"input": "tuple", "limit": 3, "fields": ["Subject", "Predicate", "Object"],
                       "suggest": [":KG"], "min": 1} | (crowd or {}),
             "query": {"input": "code", "limit": 3, "engine": "sparql", "tokens": ["SELECT", "{", "}"],
                       "seed": seed_name} | (query or {})}

    def live(item):
        return [{"type": "activity", "item": item, "rects": {"box": BOX}}]
    deck = {"format": 2, "deck": "act", "name": "Act", "types": ["activity"], "image": {"width": 1920, "height": 1080},
            "slides": [{"id": 256, "image": s1}, {"id": 257, "image": s2, "live": live("crowd")},
                       {"id": 258, "image": s2, "live": live("crowd")}, {"id": 259, "image": s2, "live": live("query")},
                       {"id": 260, "image": s1}],
            "items": {"activity": items}}
    keys = {"format": 2, "deck": "act", "items": {"activity": {"query": {"reference": [reference]}}}}
    bid = bundle_id(deck, keys)
    for rel, data in {**pngs, seed_name: seed}.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    for rel, data in (("deck.json", deck), ("keys.json", keys)):
        (folder / rel).write_text(json.dumps(data | {"bundle": bid}), encoding="utf-8")
    return bid



def receive(ws, timeout: float = 30.0) -> dict:
    """A WebSocket's next message - or the test fails after timeout (the package 4 review: a lost push
    hung the run, as starlette's receive_json waits for ever)."""
    box: queue.Queue = queue.Queue()

    def take():
        try:
            box.put((True, ws.receive_json()))
        except BaseException as e:  # noqa: BLE001 - handed to the test
            box.put((False, e))
    threading.Thread(target=take, daemon=True).start()
    try:
        ok, value = box.get(timeout=timeout)
    except queue.Empty:
        raise AssertionError(f"no message within {timeout} s") from None
    if not ok:
        raise value
    return value


class World:
    def __init__(self, tmp_path: Path, checks=None, **kw):
        self.tmp = tmp_path
        self.checks = checks                     # the server's (checking.py), started; None: the browser's mode
        self.bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle", **kw)
        self.now = T0
        self.engine = self.start()
        self.s = self.engine.open_session("act", self.bid, self.now)

    def start(self) -> Engine:
        return Engine(BundleStore([self.tmp / "bundles"]), Store(self.tmp / "store.sqlite3"), Settings(),
                      checks=self.checks)

    def settle(self, timeout: float = 60.0):
        """The pool's answers applied (Engine.apply_checks), once all it was given is answered."""
        end = time.monotonic() + timeout
        while True:
            self.engine.apply_checks(self.now)
            if not self.checks.waiting and all(p["outcomes"] is not None for p in self.checks.prepares.values()):
                return
            assert time.monotonic() < end, "the pool did not answer"
            time.sleep(0.02)

    def tick(self, ms: int = 10_000) -> int:
        self.now += ms
        return self.now

    def join(self, *names) -> list[str]:
        return [self.engine.join(self.s.pin, n, self.now)[0].id for n in names]

    def show(self, slide: int):
        self.engine.show_slide(self.s.id, slide, self.now)

    def stage(self, t: str, conn: str = "w1", window: str = "stage", **msg):
        """A message from a texstage window (window: its role; a message's own "role" is a term's)."""
        return self.engine.type_message(self.s.id, t, msg, self.now, role=window, conn=conn)

    def send(self, pid: str, activity: str, **msg):
        self.tick()
        return self.engine.type_player_message(pid, "activity.send", {"activity": activity, **msg}, self.now)

    def picture(self, activity: str, window: str = "display") -> dict:
        return self.stage("activity.view", window=window, activity=activity)["picture"]

    def phone(self, pid: str) -> dict | None:
        return self.engine.player_view(pid, self.now).get("activity")

    def item(self, activity: str) -> dict:
        return self.engine.host_view(self.s.id, self.now)["stage"]["activity"]["items"][activity]


def edges(pic: dict) -> set[tuple]:
    return {(e["s"], e["label"], e["o"], e["n"]) for e in pic["edges"]}


def test_the_crowd_graph_takes_terms_as_written(tmp_path):
    """terms=exact, the default - also for a deck built before the key: a term as written, as RDF
    compares IRIs - :kg and :KG two nodes, :inRoom and :inroom two labels -, which the lecturer may
    merge by hand."""
    w = World(tmp_path)                                               # (the item has no terms key)
    ada, bea = w.join("Ada", "Bea")
    w.show(257)
    w.send(ada, "crowd", fields=[":kg", ":inRoom", ":R1"])
    w.send(bea, "crowd", fields=[":KG", ":inroom", ":R1"])
    assert edges(w.picture("crowd")) == {(":kg", ":inRoom", ":R1", 1), (":KG", ":inroom", ":R1", 1)}
    assert {n["id"] for n in w.picture("crowd")["nodes"]} == {":kg", ":KG", ":R1"}
    w.send(ada, "crowd", fields=[":KG", ":inroom", ":R1"])             # another triple: no "sent already"
    w.stage("activity.merge", activity="crowd", role="node", term=":kg", into=":KG")
    w.stage("activity.merge", activity="crowd", role="label", term=":inroom", into=":inRoom")
    assert edges(w.picture("crowd")) == {(":KG", ":inRoom", ":R1", 2)}


def test_the_crowd_graph_draws_literals_as_boxes(tmp_path):
    """A term written as a literal - a quoted string with its language or datatype, a number, a
    boolean - says so in the picture: the windows and the archive draw it as a box, as the slides
    draw a literal. A phone's typographic quotes are Turtle's: “Kant” and "Kant" are one literal."""
    from texstage.server import activity
    for term in ['"Kant"', '"Kant"@de', '"42"^^xsd:integer', "'Kant'", "42", "-3.5", ".5", "1e3", "2.5E-3", "true",
                 "false", "“Kant”"]:
        assert activity.is_literal(term), term
    for term in [":Kant", "ex:Kant", "<http://example.org/Kant>", "_:b1", "Kant", ":42", "True", "a"]:
        assert not activity.is_literal(term), term
    assert activity.clean_term("“Kant”@de") == '"Kant"@de'                    # iOS's quotes
    assert activity.clean_term("„Kant“") == '"Kant"'                          # ... in German
    assert activity.clean_term("‘Kant’") == "'Kant'"
    assert activity.clean_term("“Stefan’s lecture”") == '"Stefan’s lecture"'
    assert activity.clean_term(":Stefan’s") == ":Stefan’s"                    # no string: as typed
    w = World(tmp_path)
    ada, bea, cy = w.join("Ada", "Bea", "Cy")
    w.show(257)
    w.send(ada, "crowd", fields=[":Kant", ":name", '"Kant"'])
    w.send(bea, "crowd", fields=[":Kant", ":name", "“Kant”"])                # an iPhone's
    w.send(cy, "crowd", fields=[":Kant", ":born", "1724"])
    pic = w.picture("crowd")
    assert {n["label"]: n.get("literal", False) for n in pic["nodes"]} == {":Kant": False, '"Kant"': True, "1724": True}
    assert edges(pic) == {(":Kant", ":name", '"Kant"', 2), (":Kant", ":born", "1724", 1)}
    svg = activity.graph_svg(pic)
    assert svg.count('fill="#ffffcc"') == 2 and svg.count("<circle") == 1                # two squares, a circle


def test_the_crowd_graph(tmp_path):
    """Triples from the phones: normalised as the word cloud groups answers (terms=loose), counted
    by students, a minimum, merged and unmerged, hidden, withdrawn, a student blocked; the phones'
    view; the frame's next step keeps it open, another frame closes it; the archive; a restarted
    server."""
    w = World(tmp_path, crowd={"terms": "loose"})
    ada, bea, cy = w.join("Ada", "Bea", "Cy")
    w.show(256)
    assert w.phone(ada) is None
    w.show(257)                                                       # its frame: open (open=auto)
    assert w.item("crowd")["phase"] == "open" and w.phone(ada)["fields"] == ["Subject", "Predicate", "Object"]
    assert w.send(ada, "crowd", fields=[":Alice", ":knows", ":Bob"])["contribution"]
    w.send(bea, "crowd", fields=[" :ALICE ", ":Knows", ":bob"])        # the same triple, spelled otherwise
    w.send(cy, "crowd", fields=[":Bob", ":knows", ":Carol"])
    assert edges(w.picture("crowd")) == {(":alice", ":knows", ":bob", 2), (":bob", ":knows", ":carol", 1)}
    assert {n["id"]: (n["label"], n["n"]) for n in w.picture("crowd")["nodes"]} == {
        ":alice": (":Alice", 2), ":bob": (":Bob", 3), ":carol": (":Carol", 1)}
    assert w.item("crowd") | {"version": 0} == {"phase": "open", "version": 0, "layout": 0, "students": 3,
                                                "count": 3, "waiting": 0, "unchecked": 0, "revealed": False,
                                                "min": 1}
    with pytest.raises(GameError, match="sent this one already"):
        w.send(ada, "crowd", fields=[":alice", ":KNOWS", ":bob"])
    for fields, message in (([":a", ":b"], "3 texts"), ([":a", "", ":c"], "1 to 60"), ([":a", 7, ":c"], "is text")):
        with pytest.raises(GameError, match=message):
            w.send(ada, "crowd", fields=fields)
    w.send(ada, "crowd", fields=[":Alice", ":teaches", ":KG"])
    with pytest.raises(GameError, match="one every 2 seconds"):
        w.engine.type_player_message(ada, "activity.send", {"activity": "crowd", "fields": ["a", "b", "c"]}, w.now + 1500)
    w.send(ada, "crowd", fields=[":Alice", ":likes", ":Tea"])
    with pytest.raises(GameError, match="at most 3"):
        w.send(ada, "crowd", fields=[":Alice", ":likes", ":Coffee"])
    phone = w.phone(ada)
    assert phone["used"] == 3 and len(phone["mine"]) == 3 and phone["suggest"][0] == ":KG" and ":Alice" in phone["suggest"]
    w.stage("activity.min", activity="crowd", min=2)
    assert edges(w.picture("crowd")) == {(":alice", ":knows", ":bob", 2)}
    w.stage("activity.min", activity="crowd", min=1)
    w.stage("activity.merge", activity="crowd", role="node", term=":carol", into=":alice")
    assert (":bob", ":knows", ":alice", 1) in edges(w.picture("crowd"))
    with pytest.raises(GameError, match=":carol is merged into :alice already"):
        w.stage("activity.merge", activity="crowd", role="node", term=":alice", into=":carol")
    with pytest.raises(GameError, match="no such term"):
        w.stage("activity.merge", activity="crowd", role="label", term=":alice", into=":knows")
    terms = {t["key"]: t for t in w.picture("crowd", window="stage")["terms"]}
    assert terms[":carol"]["into"] == ":alice" and terms[":knows"]["role"] == "label"
    w.stage("activity.unmerge", activity="crowd", role="node", term=":carol")
    w.stage("activity.hide", activity="crowd", term=":bob")
    assert {e[1] for e in edges(w.picture("crowd"))} == {":teaches", ":likes"}
    w.stage("activity.hide", activity="crowd", term=":bob", on=False)
    mine = w.phone(cy)["mine"][0]["id"]
    w.engine.type_player_message(cy, "activity.withdraw", {"activity": "crowd", "contribution": mine}, w.tick())
    assert (":bob", ":knows", ":carol", 1) not in edges(w.picture("crowd"))
    w.send(cy, "crowd", fields=[":Bob", ":hates", ":Mondays"])
    blocked = next(c for c in w.engine.books["activity"].shelf(w.s.id, "crowd").contributions.values()
                   if c.player == cy and c.state == "in")
    w.stage("activity.block", activity="crowd", contribution=blocked.id)
    assert ":hates" not in {e[1] for e in edges(w.picture("crowd"))} and w.phone(cy)["blocked"] is True
    with pytest.raises(GameError, match="closed contributions for you"):
        w.send(cy, "crowd", fields=[":a", ":b", ":c"])
    w.show(258)                                                       # its frame's next step: still open
    assert w.item("crowd")["phase"] == "open"
    w.show(259)                                                       # another frame: closed, the query opens
    assert w.item("crowd")["phase"] == "closed" and w.item("query")["phase"] == "open"
    assert w.phone(ada)["id"] == "query"
    with pytest.raises(GameError, match="this activity is closed"):
        w.send(ada, "crowd", fields=[":a", ":b", ":c"])
    files = w.engine.type_archive(w.s.id, w.now)
    assert {"activity-crowd.csv", "activity-crowd.json", "activity-crowd.svg"} <= set(files)
    assert files["activity-crowd.csv"].count("\n") == 1 + 6 and "Ada" not in files["activity-crowd.csv"]
    assert "<svg" in files["activity-crowd.svg"] and ":Alice" in files["activity-crowd.svg"]
    before = w.picture("crowd")
    w.engine.store.close()                                            # the server stops - and starts again
    again = World.__new__(World)
    again.__dict__ |= w.__dict__
    again.engine = w.start()
    again.s = again.engine.sessions[w.s.id]
    assert edges(again.picture("crowd")) == edges(before) and again.item("crowd")["phase"] == "closed"


def test_review_and_layout(tmp_path):
    """review: nothing on the projector before the lecturer lets each term; the graph's positions
    from the presenter window with the lease, for every window, not stored."""
    w = World(tmp_path, crowd={"review": True})
    ada, = w.join("Ada")
    w.show(257)
    w.send(ada, "crowd", fields=[":A", ":p", ":B"])
    assert w.picture("crowd")["edges"] == [] and w.phone(ada)["suggest"] == [":KG"]
    for term in (":A", ":p", ":B"):
        w.stage("activity.approve", activity="crowd", term=term, role="label" if term == ":p" else "node")
    assert edges(w.picture("crowd")) == {(":A", ":p", ":B", 1)}
    with pytest.raises(GameError, match="lays the graph out"):
        w.stage("activity.layout", activity="crowd", at={":A": [0.2, 0.3]})
    assert w.stage("activity.work")["lease"] is True                 # the lease: from activity.work
    w.stage("activity.layout", activity="crowd", at={":A": [0.2, 0.3], ":B": [0.8, 7], "x": "no"})
    assert w.picture("crowd")["at"] == {":A": [0.2, 0.3]} and w.item("crowd")["layout"] == 1


def test_the_clusters(tmp_path):
    """Queries: they wait for the presenter window with the lease, which gets every distinct text
    and the references once and sends keys back; a student's latest query counts; the same text
    takes a known result at once; the reference's cluster marked in the presenter window, for
    everyone after the reveal; a phone learns whether its query runs, and after the reveal whether
    its result is the reference's."""
    w = World(tmp_path)
    ada, bea, cy = w.join("Ada", "Bea", "Cy")
    w.show(259)
    assert w.phone(ada)["engine"] == "sparql"                         # (the phone's words: a query runs)
    for pid, text in ((ada, RIGHT), (bea, WRONG), (cy, RIGHT + "\n\n")):
        w.send(pid, "query", text=text)
    assert w.item("query")["waiting"] == 3 and w.phone(ada)["mine"]["status"] == "waiting"
    with pytest.raises(GameError, match="only a presenter window evaluates"):
        w.stage("activity.work", window="display")
    work = w.stage("activity.work")
    assert work["lease"] is True and sorted(j["text"] for j in work["jobs"]) == sorted([RIGHT, WRONG])
    assert work["references"] == {"query": [REFERENCE]} and work["engines"]["query"]["seed"] == SEED_NAME
    assert w.stage("activity.work", conn="w2") == {"lease": False}
    job = {j["text"]: j["input"] for j in work["jobs"]}
    w.engine.take_due()                                               # (the slide's: app.py pushes them)
    summary = {"columns": ["n"], "rows": [["Kant"]], "count": 1}
    with pytest.raises(GameError, match="another presenter window evaluates"):
        w.stage("activity.result", conn="w2", activity="query", input=job[RIGHT], status="ok", key=K1, summary=summary)
    w.stage("activity.result", activity="query", input=job[RIGHT], status="ok", key=K1, summary=summary)
    w.stage("activity.result", activity="query", input=job[WRONG], status="syntax", error="1:10: expected WHERE")
    assert w.stage("activity.result", activity="query", input=job[RIGHT], status="ok", key=K1) == {"stale": True}
    assert w.engine.take_due()[w.s.id] == {ada, bea, cy}              # their phones learn it
    assert w.phone(ada)["mine"]["status"] == "ok" and "match" not in w.phone(ada)["mine"]
    assert w.phone(bea)["mine"] | {"id": 0} == {"id": 0, "text": WRONG, "status": "syntax", "error": "1:10: expected WHERE"}
    pic = w.picture("query")
    assert [(c["key"], c["n"], c["reference"]) for c in pic["clusters"]] == [(K1, 2, False), ("syntax", 1, False)]
    assert pic["clusters"][0]["summary"] == summary and "contribution" not in pic["clusters"][0]
    with pytest.raises(GameError, match="no reference result yet"):
        w.stage("activity.reveal", activity="query")
    w.stage("activity.result", activity="query", reference=0, status="ok", key=K1)
    assert w.stage("activity.work")["references"] == {}
    staged = w.picture("query", window="stage")
    assert staged["clusters"][0]["reference"] is True and staged["refs"] == [K1]
    assert staged["clusters"][1]["errors"] == ["1:10: expected WHERE"]
    assert w.picture("query")["clusters"][0]["reference"] is False    # the projector: not before the reveal
    w.stage("activity.show", activity="query", cluster="syntax")
    assert w.picture("query")["shown"]["example"] == WRONG
    w.stage("activity.reveal", activity="query")
    assert w.picture("query")["clusters"][0]["reference"] is True
    assert w.phone(ada)["mine"]["match"] is True and "match" not in w.phone(bea)["mine"]
    w.send(bea, "query", text=RIGHT)                                  # a text with a known result: at once
    assert w.phone(bea)["mine"]["status"] == "ok" and w.phone(bea)["mine"]["match"] is True
    assert [(c["key"], c["n"]) for c in w.picture("query")["clusters"]] == [(K1, 3)]
    assert w.item("query")["waiting"] == 0 and w.stage("activity.work")["jobs"] == []
    w.tick(20_000)                                                    # w1 asked nothing for 15 s: w2 may
    assert w.stage("activity.work", conn="w2")["lease"] is True
    w.engine.left("w2")
    assert w.stage("activity.work")["lease"] is True
    for msg, message in (({"status": "ok", "key": "xyz"}, "16 hexadecimal"), ({"status": "odd"}, "status: one of"),
                         ({"status": "ok", "key": K1, "reference": 3}, "no such reference")):
        with pytest.raises(GameError, match=message):
            w.stage("activity.result", activity="query", input=job[RIGHT], **msg)
    files = w.engine.type_archive(w.s.id, w.now)
    assert set(files) == {"activity-query.csv", "activity-query.json"}
    assert json.loads(files["activity-query.json"])["clusters"][0]["reference"] is True


def test_a_turtle_activity(tmp_path):
    """engine=turtle on the server, clustered as queries are: the phone is told the engine - its
    words: a valid Turtle text, the reference's graph - and the tokens; an empty text is refused as
    a Turtle text; the presenter window gets the engine, the seed (the prefixes) and the reference,
    Turtle, to evaluate; after the reveal each phone learns whether its graph is the reference's."""
    right, wrong = 'dbr:Berlin rdfs:label "Berlin"@de .', 'dbr:Berlin rdfs:label "Berlin" .'
    w = World(tmp_path, query={"engine": "turtle", "tokens": ["dbr:Berlin", ":", "."]}, reference=right)
    ada, bea = w.join("Ada", "Bea")
    w.show(259)
    phone = w.phone(ada)
    assert phone["engine"] == "turtle" and phone["tokens"] == ["dbr:Berlin", ":", "."]
    with pytest.raises(GameError, match="a Turtle text has 1 to 2000 characters"):
        w.send(ada, "query", text=" \n ")
    w.send(ada, "query", text=right)
    w.send(bea, "query", text=wrong)
    work = w.stage("activity.work")
    assert work["engines"] == {"query": {"engine": "turtle", "seed": SEED_NAME}}
    assert work["references"] == {"query": [right]}
    job = {j["text"]: j["input"] for j in work["jobs"]}
    k2 = "fedcba9876543210"
    graph = {"kind": "graph", "count": 1, "rows": [["dbr:Berlin", "rdfs:label", '"Berlin"@de']]}
    w.stage("activity.result", activity="query", reference=0, status="ok", key=K1, summary=graph)
    w.stage("activity.result", activity="query", input=job[right], status="ok", key=K1)
    w.stage("activity.result", activity="query", input=job[wrong], status="ok", key=k2,
            summary=graph | {"rows": [["dbr:Berlin", "rdfs:label", '"Berlin"']]})
    assert w.phone(ada)["mine"]["status"] == "ok" and "match" not in w.phone(ada)["mine"]
    w.stage("activity.reveal", activity="query")
    assert w.phone(ada)["mine"]["match"] is True and w.phone(bea)["mine"]["match"] is False
    assert [(c["key"], c["n"], c["reference"], c["summary"]["kind"]) for c in w.picture("query")["clusters"]] == [
        (K1, 1, True, "graph"), (k2, 1, False, "graph")]


def test_the_archived_graph_draws_loops_and_edges_between_the_same_nodes():
    """The archive's picture (graph_svg) as the windows draw the graph (web/stage/activity.js):
    a triple whose subject is its object a loop at its node, two edges between the same nodes
    curved apart - their labels apart -, a single edge straight; every edge an arrow."""
    from texstage.server import activity                  # (after the registry, types.py: they import each other)
    pic = {"nodes": [{"id": ":t", "label": ":test", "n": 1}, {"id": ":a", "label": ":A", "n": 2},
                     {"id": ":b", "label": ":B", "n": 1}, {"id": ":c", "label": ":C", "n": 1}],
           "edges": [{"s": ":t", "o": ":t", "label": ":test", "n": 1}, {"s": ":a", "o": ":b", "label": ":p", "n": 1},
                     {"s": ":b", "o": ":a", "label": ":q", "n": 1}, {"s": ":b", "o": ":c", "label": ":r", "n": 1}],
           "at": {":t": [0.2, 0.3], ":a": [0.4, 0.6], ":b": [0.7, 0.6], ":c": [0.9, 0.2]}}
    svg = activity.graph_svg(pic)
    paths = re.findall(r'<path d="([^"]+)" fill="none"[^>]*marker-end="url\(#arrow\)"', svg)
    assert len(paths) == 4 and " C" in paths[0] and all(" Q" in p for p in paths[1:])
    labels = {t: (float(x), float(y)) for x, y, t in re.findall(r'<text x="([\d.]+)" y="([\d.]+)" font-size="13"[^>]*>([^<]+)<', svg)}
    assert labels[":test"][1] > 0.3 * 750 + 26                         # below the node (its name is above)
    assert abs(labels[":p"][1] - labels[":q"][1]) >= 30                 # :p and :q on either side
    assert [round(v, 1) for v in activity.edge_shapes(pic["edges"])[3].values()] == [0.0]
    star = [{"s": f":s{i}", "o": ":kg", "label": ":attends", "n": n} for i, n in enumerate([1, 4, 2, 3, 1])]
    assert activity.repeated_labels(star) == {0, 4}                     # the label on the three most named


def test_the_archived_graphs_labels_apart():
    """The archive's picture places the edges' labels as the windows do (place_labels): over every
    edge, on no node and none on another - the edge most students sent first -, inside the picture;
    one without a free spot left out."""
    from texstage.server import activity
    # a fan: six edges from one node to six close by, their middles close together
    fan = [f":n{i}" for i in range(6)]
    pic = {"nodes": [{"id": ":hub", "label": ":hub", "n": 6}] + [{"id": f, "label": f, "n": 1} for f in fan],
           "edges": [{"s": ":hub", "o": f, "label": f":relatesTo{i}", "n": 1 + (i == 4)} for i, f in enumerate(fan)],
           "at": {":hub": [0.5, 0.5]} | {f: [0.4 + 0.04 * i, 0.68] for i, f in enumerate(fan)}}
    svg = activity.graph_svg(pic)
    texts = [(float(x), float(y), t) for x, y, t in re.findall(r'<text x="([\d.]+)" y="([\d.]+)" font-size="13"[^>]*>([^<]+)<', svg)]
    assert svg.rindex("<path d=") < svg.index('font-size="13"')        # the labels over every edge
    boxes = [activity.label_box(x, y, 0.58 * 13 * len(t), 13) for x, y, t in texts]
    nodes = [(1000 * p[0], 750 * p[1]) for p in pic["at"].values()]
    for i, b in enumerate(boxes):
        assert 0 <= b[0] and b[2] <= 1000 and 0 <= b[1] and b[3] <= 750
        assert not any(b[0] < c[2] and c[0] < b[2] and b[1] < c[3] and c[1] < b[3] for c in boxes[i + 1:])
        assert not any(b[0] < x + 10 and x - 10 < b[2] and b[1] < y + 10 and y - 10 < b[3] for x, y in nodes)
    assert ":relatesTo4" in [t for _, _, t in texts]                    # sent by the most: placed first
    assert 3 <= len(texts) < 6, texts                                   # not all six have room
    # left out rather than on another; a loop's label has its one spot
    assert activity.place_labels([{"w": 40, "h": 13, "x": 100, "y": 100}], [(0, 0, 1000, 750)], (1000, 750)) == [None]
    assert activity.place_labels([{"w": 40, "h": 13, "x": 100, "y": 100}], [], (1000, 750)) == [(100, 100)]


def test_activities_over_websockets(tmp_path):
    """The presenter window, the projector window and two phones: the frame opens the activity on
    the phones, contributions count in every window's state, the projector reads the picture but
    neither evaluates nor moderates, the seed is served as the pictures are, the archive keeps the
    activity's files."""
    bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle")
    sql = b"CREATE TABLE t (x);\n"                                       # an SQL activity's seed (engines.py) ...
    sql_name = f"data/{hashlib.sha256(sql).hexdigest()[:16]}.sql"
    (tmp_path / "bundles" / "act.bundle" / sql_name).write_bytes(sql)
    (tmp_path / "bundles" / "act.bundle" / sql_name).with_suffix(".py").write_bytes(sql)    # ... and no engine's file
    config = ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                          presenter_key=KEY, settings=Settings(get_ready_ms=0))

    def recv(ws, t=None, until=None):
        for _ in range(60):
            m = receive(ws)
            if (t is None or m["t"] == t) and (until is None or until(m)):
                return m
        raise AssertionError(f"no {t} message")
    with TestClient(create_app(config)) as client, client.websocket_connect("/ws") as st, \
            client.websocket_connect("/ws") as dp, client.websocket_connect("/ws") as p1, \
            client.websocket_connect("/ws") as p2:
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": "act", "bundle": bid, "id": 1})
        pin = recv(st, "welcome")["pin"]
        dp.send_json({"t": "hello", "role": "display", "key": KEY, "deck": "act", "bundle": bid, "id": 1})
        recv(dp, "welcome")
        for p, name in ((p1, "Ada"), (p2, "Bea")):
            p.send_json({"t": "join", "pin": pin, "nickname": name, "id": "j"})
            recv(p, "welcome")
        st.send_json({"t": "slide", "slide": 257, "id": 2})
        phone = recv(p1, "state", until=lambda m: m.get("activity"))["activity"]
        assert phone["id"] == "crowd" and phone["phase"] == "open"
        p1.send_json({"t": "activity.send", "activity": "crowd", "fields": [":A", ":p", ":B"], "id": 3})
        assert recv(p1, "ok")["contribution"]
        counts = recv(dp, "state", until=lambda m: (m["stage"].get("activity") or {}).get("items", {})
                      .get("crowd", {}).get("count") == 1)["stage"]["activity"]["items"]["crowd"]
        assert counts["students"] == 1 and "merges" not in counts
        dp.send_json({"t": "activity.view", "activity": "crowd", "id": 4})
        pic = recv(dp, "ok", until=lambda m: m.get("re") == 4)["picture"]
        assert [(e["s"], e["o"]) for e in pic["edges"]] == [(":A", ":B")] and "terms" not in pic
        dp.send_json({"t": "activity.hide", "activity": "crowd", "term": ":a", "id": 5})
        assert recv(dp, "error", until=lambda m: m.get("re") == 5)["error"] == "read-only"
        dp.send_json({"t": "activity.work", "id": 6})
        assert recv(dp, "error", until=lambda m: m.get("re") == 6)["error"] == "read-only"
        st.send_json({"t": "activity.view", "activity": "crowd", "id": 7})
        assert "terms" in recv(st, "ok", until=lambda m: m.get("re") == 7)["picture"]
        st.send_json({"t": "slide", "slide": 260, "id": 8})               # the frame goes: closed
        assert recv(p2, "state", until=lambda m: not m.get("activity")).get("activity") is None
        p2.send_json({"t": "activity.send", "activity": "crowd", "fields": [":A", ":p", ":B"], "id": 9})
        assert recv(p2, "error", until=lambda m: m.get("re") == 9)["error"] == "closed"
        seed = client.get(f"/bundle/{bid}/{SEED_NAME}")
        assert seed.content == SEED and seed.headers["content-type"].startswith("text/turtle")
        seed = client.get(f"/bundle/{bid}/{sql_name}")
        assert seed.content == sql and seed.headers["content-type"].startswith("application/sql")
        assert client.get(f"/bundle/{bid}/{sql_name[:-4]}.py").status_code == 404
        game = recv(st, "state")["session"]["id"]
        z = client.get(f"/api/archive/{game}.zip", headers={"X-Texquiz-Key": KEY})
        names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
        assert {"activity-crowd.csv", "activity-crowd.json", "activity-crowd.svg"} <= set(names)


# ------------------------------------------------------------------ the server's checks (F1, package 4)
@pytest.fixture
def pool():
    """The server's checks, started, with a pool of one worker and no spare - quick to start -, closed
    after the test: pool(mode, **the pool's options)."""
    pytest.importorskip("psutil")
    pytest.importorskip("pyoxigraph")
    made = []

    def make(mode: str = "server", **options) -> Checks:
        made.append(Checks(mode, workers=1, spare=False, **options).start())
        return made[-1]
    yield make
    for c in made:
        c.close()


def test_the_server_checks_the_references_as_the_game_starts_and_each_text_as_it_comes(tmp_path, pool):
    """--checks server: the references are checked as the game starts, before any text; every distinct
    text as it comes, on the pool - nothing waits for a presenter window, which gets the lease for the
    layout and no jobs, and whose results are refused; the same text takes the known result at once;
    the phones learn their verdicts, after the reveal whether their result is the reference's; the
    deck's last game ended, the pool lets go of it."""
    w = World(tmp_path, checks=pool())
    w.settle()
    ref = w.picture("query", window="stage")["refs"][0]
    assert re.fullmatch(r"[0-9a-f]{16}", ref)
    ada, bea, cy = w.join("Ada", "Bea", "Cy")
    w.show(259)
    for pid, text in ((ada, RIGHT), (bea, WRONG), (cy, RIGHT + "\n\n")):
        w.send(pid, "query", text=text)
    assert w.item("query")["waiting"] == 3 and w.phone(ada)["mine"]["status"] == "waiting"
    assert len(w.checks.waiting) == 2                                   # two distinct texts, one job each
    w.engine.take_due()
    w.settle()
    assert w.engine.take_due()[w.s.id] == {ada, bea, cy}              # their phones learn it
    assert w.item("query")["waiting"] == 0
    assert w.phone(ada)["mine"]["status"] == "ok" and "match" not in w.phone(ada)["mine"]
    assert w.phone(bea)["mine"]["status"] == "syntax" and w.phone(bea)["mine"]["error"]
    pic = w.picture("query")
    assert [(c["key"], c["n"]) for c in pic["clusters"]] == [(ref, 2), ("syntax", 1)]
    assert pic["clusters"][0]["summary"]["rows"] == [["Kant"]] and pic["clusters"][0]["reference"] is False
    assert w.stage("activity.work") == {"lease": True, "checks": "server", "jobs": [], "references": {},
                                        "known": {}, "engines": {}}
    assert w.stage("activity.work", conn="w2") == {"lease": False, "checks": "server"}
    with pytest.raises(GameError, match="the server checks"):
        w.stage("activity.result", activity="query", reference=0, status="ok", key=K1)
    w.stage("activity.reveal", activity="query")
    assert w.picture("query")["clusters"][0]["reference"] is True
    assert w.phone(ada)["mine"]["match"] is True and "match" not in w.phone(bea)["mine"]
    w.send(bea, "query", text=RIGHT)                                  # a text with a known result: at once
    assert w.phone(bea)["mine"]["status"] == "ok" and not w.checks.waiting
    from texstage.server import activity
    assert activity.failed_references(w.s.stage) == []
    assert [(c["key"], c["n"]) for c in w.picture("query")["clusters"]] == [(ref, 3)]
    files = w.engine.type_archive(w.s.id, w.now)
    assert json.loads(files["activity-query.json"])["clusters"][0]["reference"] is True
    w.engine.end(w.s.id, w.now)                                       # the deck's last game
    assert w.checks.prepares == {}


def test_the_server_checks_a_turtle_activity(tmp_path, pool):
    """engine=turtle on the server: the seed's prefixes in front of every text; the reference's graph
    and a student's alike, another's not."""
    right, wrong = 'dbr:Berlin rdfs:label "Berlin"@de .', 'dbr:Berlin rdfs:label "Berlin" .'
    seed = (b"@prefix dbr: <http://dbpedia.org/resource/> .\n"
            b"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n")
    w = World(tmp_path, checks=pool(), query={"engine": "turtle", "tokens": ["dbr:Berlin", ":", "."]},
              reference=right, seed=seed)
    ada, bea = w.join("Ada", "Bea")
    w.show(259)
    w.send(ada, "query", text=right)
    w.send(bea, "query", text=wrong)
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "ok" and w.phone(bea)["mine"]["status"] == "ok"
    w.stage("activity.reveal", activity="query")
    assert w.phone(ada)["mine"]["match"] is True and w.phone(bea)["mine"]["match"] is False
    assert sorted((c["n"], c["reference"], c["summary"]["kind"]) for c in w.picture("query")["clusters"]) == [
        (1, False, "graph"), (1, True, "graph")]


def test_a_text_the_server_cannot_check_is_internal_never_the_students_fault(tmp_path, pool):
    """A text whose check ends its worker, on a fresh one too: internal - counted apart from the waiting
    ones (unchecked), in no cluster, on the phone without the server's reasons -, set aside, so the same
    text again is internal at once; another student's text is checked as ever (pool_engines: a text says
    what it does)."""
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference")
    ada, bea, cy = w.join("Ada", "Bea", "Cy")
    w.show(259)
    w.send(ada, "query", text="crash")
    w.send(bea, "query", text="ok fine")
    w.settle()
    mine = w.phone(ada)["mine"]
    assert mine["status"] == "internal" and "error" not in mine
    assert w.phone(bea)["mine"]["status"] == "ok"
    assert (w.item("query")["waiting"], w.item("query")["unchecked"], w.item("query")["count"]) == (0, 1, 2)
    assert [(c["status"], c["n"]) for c in w.picture("query")["clusters"]] == [("ok", 1)]
    kept = w.engine.books["activity"].shelf(w.s.id, "query").mine[ada][-1]
    assert kept.error.startswith("set aside: ") and not kept.again()   # it ended two processes: final
    w.send(cy, "query", text="crash")
    assert w.phone(cy)["mine"]["status"] == "internal" and not w.checks.waiting
    assert (w.item("query")["waiting"], w.item("query")["unchecked"]) == (0, 2)


def test_a_reference_that_fails_shows_as_the_game_starts_and_in_the_deck_list(tmp_path, pool):
    """A reference with a syntax error: failed in the presenter window's panel as the game starts - before
    the lecture -, and the deck list says so (/api/decks: failing)."""
    w = World(tmp_path, checks=pool(), reference="SELECT ?n WHER { ?p :name ?n }")
    w.settle()
    assert w.picture("query", window="stage")["refs"][0]["failed"].startswith("syntax: ")
    from texstage.server import activity
    [failed] = activity.failed_references(w.s.stage)
    assert (failed["activity"], failed["reference"]) == ("query", 1) and failed["error"].startswith("syntax: ")
    with pytest.raises(GameError, match="no reference result yet"):
        w.stage("activity.reveal", activity="query")
    config = ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                          presenter_key=KEY, checks="server", workers=1, pool={"spare": False})
    with TestClient(create_app(config)) as client, client.websocket_connect("/ws") as st:
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": "act", "bundle": w.bid, "id": 1})
        assert receive(st)["t"] == "welcome"
        end = time.monotonic() + 60
        while not (failing := client.get("/api/decks", headers={"X-Texquiz-Key": KEY}).json()[0]["failing"]):
            assert time.monotonic() < end, "the deck list never said so"
            time.sleep(0.05)
        assert [(f["activity"], f["reference"]) for f in failing] == [("query", 1)]


def test_after_a_restart_the_texts_that_wait_are_checked(tmp_path, pool):
    """Texts wait - sent while the presenter window was to check them, none was there -, and the server
    restarts with its own checks: the open game's deck is prepared again, the texts are checked."""
    w = World(tmp_path)
    ada, bea = w.join("Ada", "Bea")
    w.show(259)
    w.send(ada, "query", text=RIGHT)
    w.send(bea, "query", text=WRONG)
    assert w.item("query")["waiting"] == 2
    w.engine.store.close()                                            # the server stops - and starts again
    w.checks = pool()
    w.engine = w.start()
    w.s = w.engine.sessions[w.s.id]
    w.engine.resume_checks(w.now)
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "ok" and w.phone(bea)["mine"]["status"] == "syntax"
    assert w.item("query")["waiting"] == 0
    assert w.picture("query")["clusters"][0]["key"] == w.picture("query", window="stage")["refs"][0]


def test_in_the_mode_both_the_windows_results_count_and_the_differences_are_written_down(tmp_path, pool):
    """--checks both: the presenter window evaluates and its results count, as before F1; the pool checks
    the same texts and the references, and each difference of status or key - here the window's keys,
    made up - is a row of the game's checks-compare.csv; a text both find alike is none."""
    w = World(tmp_path, checks=pool("both"))
    compare = tmp_path / "checks-compare.csv"
    w.checks.compare_file = lambda s: compare
    ada, bea = w.join("Ada", "Bea")
    w.show(259)
    w.send(ada, "query", text=RIGHT)
    w.send(bea, "query", text=WRONG)
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "waiting"               # the pool's outcomes do not count
    assert "checks" not in w.phone(ada)                              # (the phone's words: the lecturer's computer)
    work = w.stage("activity.work")
    assert "checks" not in work and sorted(j["text"] for j in work["jobs"]) == sorted([RIGHT, WRONG])
    job = {j["text"]: j["input"] for j in work["jobs"]}
    w.stage("activity.result", activity="query", input=job[RIGHT], status="ok", key=K1,
            summary={"columns": ["n"], "rows": [["Kant"]], "count": 1})
    w.stage("activity.result", activity="query", input=job[WRONG], status="syntax", error="1:10: expected WHERE")
    w.stage("activity.result", activity="query", reference=0, status="ok", key=K1)
    assert w.phone(ada)["mine"]["status"] == "ok"
    assert [(c["key"], c["n"]) for c in w.picture("query")["clusters"]] == [(K1, 1), ("syntax", 1)]
    rows = list(csv.reader(compare.read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0] == COMPARE_COLUMNS
    assert [(r[1], r[2], r[3], r[4], r[5], r[7]) for r in rows[1:]] == [
        ("query", "text", RIGHT, "ok", K1, "ok"), ("query", "reference 1", REFERENCE, "ok", K1, "ok")]
    assert re.fullmatch(r"[0-9a-f]{16}", rows[1][8]) and rows[1][8] != K1 and rows[1][8] == rows[2][8]


def test_over_websockets_the_phones_get_their_verdicts_without_an_evaluating_window(tmp_path):
    """A server with its own checks: the presenter window shows the slide and evaluates nothing - its
    activity.work gives the lease, no jobs -; a phone's query is checked, and its verdict pushed."""
    pytest.importorskip("psutil")
    pytest.importorskip("pyoxigraph")
    bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle")
    config = ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                          presenter_key=KEY, settings=Settings(get_ready_ms=0), checks="server", workers=1,
                          pool={"spare": False})

    def recv(ws, t=None, until=None):
        for _ in range(200):
            m = receive(ws)
            if (t is None or m["t"] == t) and (until is None or until(m)):
                return m
        raise AssertionError(f"no {t} message")
    with TestClient(create_app(config)) as client, client.websocket_connect("/ws") as st, \
            client.websocket_connect("/ws") as p1:
        assert client.get("/api/status").json()["checks"] == "server"
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": "act", "bundle": bid, "id": 1})
        pin = recv(st, "welcome")["pin"]
        p1.send_json({"t": "join", "pin": pin, "nickname": "Ada", "id": "j"})
        recv(p1, "welcome")
        st.send_json({"t": "slide", "slide": 259, "id": 2})
        recv(p1, "state", until=lambda m: (m.get("activity") or {}).get("id") == "query")
        p1.send_json({"t": "activity.send", "activity": "query", "text": RIGHT, "id": 3})
        assert recv(p1, "ok", until=lambda m: m.get("re") == 3)["contribution"]
        mine = recv(p1, "state", until=lambda m: ((m.get("activity") or {}).get("mine") or {}).get("status") == "ok")
        assert mine["activity"]["mine"]["text"] == RIGHT
        st.send_json({"t": "activity.work", "id": 4})
        work = recv(st, "ok", until=lambda m: m.get("re") == 4)
        assert work["lease"] is True and work["checks"] == "server" and work["jobs"] == []


# ------------------------------------------------------------------ what package 4's review found (2026-11-10)
class FakePool:
    """The pool's interface, its texts' futures resolved by the test; it prepares at once."""

    def __init__(self):
        self.futures: dict[tuple[str, str], cf.Future] = {}
        self.broken = None

    def prepare(self, act, engine, seed, references, language=None):
        fut = cf.Future()
        fut.set_result([{"status": "ok", "key": K1} for _ in references])
        return fut

    def submit(self, act, text, owner=None, language=None):
        return self.futures.setdefault((act, text), cf.Future())

    def drop(self, act):
        pass

    def close(self):
        pass


def restart(w: World, checks) -> None:
    """The server stops and starts again - with checks (started), or with the browser's (None)."""
    w.engine.store.close()
    if w.checks is not None:
        w.checks.close()
    w.checks = checks
    w.engine = w.start()
    w.s = w.engine.sessions[w.s.id]
    w.engine.resume_checks(w.now)                                  # (app.py: as the server starts, in every mode)


def flaky(tmp_path: Path) -> bytes:
    """A seed for pool_engines whose first load anywhere fails, and every later one loads."""
    return f"flaky {tmp_path / 'loads'} 1".encode()


def test_what_the_server_could_not_check_is_checked_after_a_restart(tmp_path, pool):
    """A text that came back internal for the server's reasons - here its activity was not prepared: the
    seed's first load fails - is no known result: the same text from another student goes to the pool
    again; the panel counts both apart from the waiting ones, the windows learn why the server cannot
    check, and the references are internal, not the deck's failure. After a restart whose pool can, the
    texts wait again and are checked, the references too, and the store has their outcomes (the package 4
    review: they stayed internal, and the same text took it at once)."""
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference",
              seed=flaky(tmp_path))
    w.settle()
    assert w.picture("query", window="stage")["refs"][0]["failed"].startswith("internal: ")
    checks = w.engine.host_view(w.s.id, w.now)["checks"]
    assert checks["mode"] == "server" and list(checks["failing"]) == ["query"]
    ada, bea = w.join("Ada", "Bea")
    w.show(259)
    w.send(ada, "query", text="ok fine")
    w.settle()
    w.send(bea, "query", text="ok fine")
    assert w.phone(bea)["mine"]["status"] == "waiting"             # not Ada's internal: to the pool
    w.settle()
    assert [w.phone(p)["mine"]["status"] for p in (ada, bea)] == ["internal", "internal"]
    assert (w.item("query")["waiting"], w.item("query")["unchecked"]) == (0, 2)
    restart(w, pool(engines={"sparql": "pool_engines"}))
    assert [w.phone(p)["mine"]["status"] for p in (ada, bea)] == ["waiting", "waiting"]
    assert (w.item("query")["waiting"], w.item("query")["unchecked"]) == (2, 0)     # counted again
    w.settle()
    db = sqlite3.connect(tmp_path / "store.sqlite3")             # committed as they were applied - before
    try:                                                          # any window's message commits
        assert sorted(r[0] for r in db.execute("SELECT status FROM contributions")) == ["ok", "ok"]
    finally:
        db.close()
    assert [w.phone(p)["mine"]["status"] for p in (ada, bea)] == ["ok", "ok"]
    assert re.fullmatch(r"[0-9a-f]{16}", w.picture("query", window="stage")["refs"][0])
    assert w.engine.host_view(w.s.id, w.now)["checks"] == {"mode": "server", "failing": {}}


def test_after_a_fallback_to_the_browsers_checks_the_window_checks_what_the_server_could_not(tmp_path, pool):
    """The same, and the lecturer starts the server again with --checks browser: the presenter window gets
    the text and the reference as its work, and the activity can be revealed (the package 4 review: it got
    neither, and the reveal was refused for ever); the phone's words are the browser's again."""
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference",
              seed=flaky(tmp_path))
    w.settle()
    ada, = w.join("Ada")
    w.show(259)
    w.send(ada, "query", text="ok fine")
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "internal" and w.phone(ada)["checks"] == "server"
    restart(w, None)
    assert w.engine.host_view(w.s.id, w.now)["checks"] == {"mode": "browser"}
    work = w.stage("activity.work")
    assert work["references"] == {"query": ["ok the reference"]} and [j["text"] for j in work["jobs"]] == ["ok fine"]
    w.stage("activity.result", activity="query", reference=0, status="ok", key=K1)
    w.stage("activity.result", activity="query", input=work["jobs"][0]["input"], status="ok", key=K1,
            summary={"kind": "test"})
    w.stage("activity.reveal", activity="query")
    assert w.phone(ada)["mine"]["status"] == "ok" and w.phone(ada)["mine"]["match"] is True
    assert "checks" not in w.phone(ada)


def test_the_panel_has_each_reference_not_run_yet(tmp_path):
    """Before a reference is run - by the presenter window, or by the server as it prepares the deck - the
    panel has it as not run yet, not as a deck that gives none (the package 4 review)."""
    w = World(tmp_path)
    assert w.picture("query", window="stage")["refs"] == [None]
    assert w.stage("activity.work")["references"] == {"query": [REFERENCE]}


def test_two_games_of_one_build_share_its_checks_and_the_last_to_end_lets_go(tmp_path, pool):
    """Two lecturers' games of the same build: one job for the same text in both, its student the owner of
    the job, and the verdict in both; the first game ends while the other's text is checked - the build
    stays prepared, the verdict comes, the references stay -; the last game ends, and the pool lets go of
    the build (the package 4 review: the tests passed without the one job, with the build let go of early,
    and with it never let go of)."""
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference")
    e, c = w.engine, w.checks
    other = e.open_session("act", w.bid, w.now, owner="other")
    w.settle()
    ada = e.join(w.s.pin, "Ada", w.now)[0].id
    bob = e.join(other.pin, "Bob", w.now)[0].id
    for s in (w.s, other):
        e.show_slide(s.id, 259, w.now)
    w.tick()
    for pid in (ada, bob):
        e.type_player_message(pid, "activity.send", {"activity": "query", "text": "sleep 0.5"}, w.now)
    assert [(k[1], v["games"]) for k, v in c.waiting.items()] == [("sleep 0.5", {w.s.id, other.id})]
    with c.pool.lock:
        assert c.pool.inflight[(act_name(w.bid, "query"), "sleep 0.5")]["owner"] == ada
    w.settle()
    assert [e.player_view(p, w.now)["activity"]["mine"]["status"] for p in (ada, bob)] == ["ok", "ok"]
    w.tick()
    e.type_player_message(bob, "activity.send", {"activity": "query", "text": "sleep 1 #bob"}, w.now)
    e.end(w.s.id, w.now)                                           # the first game ends meanwhile
    assert len(c.prepares) == 1 and c.pool.stats()["activities"] == 1
    w.settle()
    assert e.player_view(bob, w.now)["activity"]["mine"]["status"] == "ok"
    view = e.type_message(other.id, "activity.view", {"activity": "query"}, w.now, role="stage", conn="x")
    assert re.fullmatch(r"[0-9a-f]{16}", view["picture"]["refs"][0])
    e.end(other.id, w.now)                                         # the build's last game
    assert c.prepares == {} and c.pool.stats()["activities"] == 0


def test_a_summary_over_the_limits_is_left_out_not_the_check(tmp_path, pool):
    """The server's outcome with a summary over 12 KB (pool_engines puts the seed into every summary): the
    verdict arrives without it - the presenter window's would be refused (the package 4 review: no test
    looked)."""
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference",
              seed=b"x" * 13_000)
    w.settle()
    ada, = w.join("Ada")
    w.show(259)
    w.send(ada, "query", text="ok fine")
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "ok" and w.item("query")["waiting"] == 0
    assert [("summary" in c, c["n"]) for c in w.picture("query")["clusters"]] == [(False, 1)]


def test_a_text_being_checked_as_the_server_stops_waits_and_is_checked_after_the_start(tmp_path, pool):
    """The server stops while a text is checked: what the pool answers as it closes is not the text's - it
    waits, and the next start checks it (the package 4 review: no test looked)."""
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference")
    w.settle()
    ada, = w.join("Ada")
    w.show(259)
    w.send(ada, "query", text="sleep 2")
    time.sleep(0.3)                                                # (being checked)
    w.checks.close()
    w.engine.apply_checks(w.now)
    assert w.phone(ada)["mine"]["status"] == "waiting"
    restart(w, pool(engines={"sparql": "pool_engines"}))
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "ok"


def test_a_restart_prepares_no_stale_game_and_opening_its_deck_again_prepares_it_once(tmp_path, pool):
    """Games end only when their deck is opened again: a restart prepares the open games' decks - not a
    stale one's, an earlier lecture's (the package 4 review: every deck of a semester, on every process,
    and held) -; a text sent to that game prepares it; opening its deck again ends the game, and the new
    game has the build as it was prepared (it was dropped, then prepared again)."""
    w = World(tmp_path)
    ada, = w.join("Ada")
    w.show(259)
    w.now += Settings().stale_ms + 1                               # last week's lecture
    restart(w, pool())
    assert w.checks.prepares == {}
    w.send(ada, "query", text=RIGHT)
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "ok" and w.checks.pool.gens == 1
    w.now += Settings().stale_ms + 1
    new = w.engine.open_session("act", w.bid, w.now)
    assert new.id != w.s.id and w.checks.pool.gens == 1 and len(w.checks.prepares) == 1
    view = w.engine.type_message(new.id, "activity.view", {"activity": "query"}, w.now, role="stage", conn="x")
    assert re.fullmatch(r"[0-9a-f]{16}", view["picture"]["refs"][0])


def test_a_restart_with_the_servers_checks_keeps_the_keys_a_game_has(tmp_path, pool):
    """A game the browser's checks began - the reference's key and the students' from the window, here a
    made-up one, as where 4.3 does not hold - and a restart with --checks server: the game keeps its keys,
    and a revealed match stays a match (plan 4.11; the package 4 review: the pool's key replaced the
    reference's)."""
    w = World(tmp_path)
    ada, = w.join("Ada")
    w.show(259)
    w.send(ada, "query", text=RIGHT)
    work = w.stage("activity.work")
    w.stage("activity.result", activity="query", reference=0, status="ok", key=K1)
    w.stage("activity.result", activity="query", input=work["jobs"][0]["input"], status="ok", key=K1,
            summary={"columns": ["n"], "rows": [["Kant"]], "count": 1})
    w.stage("activity.reveal", activity="query")
    assert w.phone(ada)["mine"]["match"] is True
    restart(w, pool())
    w.settle()
    assert w.picture("query", window="stage")["refs"] == [K1] and w.phone(ada)["mine"]["match"] is True


def test_an_answer_the_engine_cannot_apply_comes_again_and_the_rest_of_its_round_is_applied(tmp_path,
                                                                                             monkeypatch):
    """Two texts answered in one round, and applying the first fails - an error of the engine's, not the
    answer's: the other is applied, and the first comes again with the next round (checking.py: again; the
    package 4 review: the whole round was lost, its texts waited until a restart)."""
    from texstage.server import activity
    c = Checks("server")
    c.pool = FakePool()
    c.again_s = 0                                                  # (due at once: the next round is its time)
    w = World(tmp_path, checks=c)
    w.engine.apply_checks(w.now)                                   # (the references)
    ada, bea = w.join("Ada", "Bea")
    w.show(259)
    w.send(ada, "query", text="SELECT ?a WHERE {}")
    w.send(bea, "query", text="SELECT ?b WHERE {}")
    for i, fut in enumerate(c.pool.futures.values()):
        fut.set_result({"status": "ok", "key": f"{i:016x}"})
    real, calls = activity.checked, []

    def once(call, aid, msg, again=False):
        calls.append(msg["text"])
        if len(calls) == 1:
            raise RuntimeError("a bug, once")
        return real(call, aid, msg, again=again)
    monkeypatch.setattr(activity, "checked", once)
    w.engine.apply_checks(w.now)
    assert sorted(w.phone(p)["mine"]["status"] for p in (ada, bea)) == ["ok", "waiting"] and len(c.later) == 1
    w.engine.apply_checks(w.now)                                   # the next round (app.py: a second on)
    assert [w.phone(p)["mine"]["status"] for p in (ada, bea)] == ["ok", "ok"] and c.later == []


# ------------------------------------------------------------------ what the review of those fixes found (2026-11-10)
class AgainPool(FakePool):
    """As the pool does: a text submitted after its check is done is checked again."""

    def submit(self, act, text, owner=None, language=None):
        fut = self.futures.get((act, text))
        if fut is None or fut.done():
            fut = self.futures[(act, text)] = cf.Future()
        return fut


def fake_checks(pool=None) -> Checks:
    c = Checks("server")
    c.pool = pool or AgainPool()
    return c


@pytest.mark.parametrize("failing", ["Contribution", "Session", "Result"])
def test_an_answer_whose_saving_failed_after_the_shelf_changed_is_repaired_when_it_comes_again(tmp_path, failing):
    """The store fails once while an answer is applied - after the entry changed in memory, or before the
    game or the result is saved: when the answer comes again, the entry, the game and the result are saved,
    the counts are right and the phone is pushed (the review of package 4's fixes: the retry found nothing
    waiting and did nothing - no push, "1 waiting" for ever, the row waiting in the store)."""
    c = fake_checks()
    c.again_s = 0
    w = World(tmp_path, checks=c)
    w.engine.apply_checks(w.now)
    ada, = w.join("Ada")
    w.show(259)
    w.send(ada, "query", text="SELECT ?a WHERE {}")
    for fut in c.pool.futures.values():
        fut.set_result({"status": "ok", "key": "00000000000000aa", "summary": {"columns": ["a"], "rows": [], "count": 0}})
    w.engine.take_due()
    store, real, failed = w.engine.store, w.engine.store.save, []

    def save(item):
        if type(item).__name__ == failing and not failed:
            failed.append(item)
            raise sqlite3.OperationalError("database is locked")
        return real(item)
    store.save = save
    w.engine.apply_checks(w.now)
    assert failed and len(c.later) == 1
    w.engine.apply_checks(w.now)                                   # it comes again
    due = w.engine.take_due()
    assert c.later == [] and due == {w.s.id: {ada}}
    assert w.phone(ada)["mine"]["status"] == "ok" and w.item("query")["waiting"] == 0
    assert [("summary" in k) for k in w.picture("query")["clusters"]] == [True]
    db = sqlite3.connect(tmp_path / "store.sqlite3")
    try:
        assert db.execute("SELECT status, key FROM contributions").fetchall() == [("ok", "00000000000000aa")]
        assert db.execute("SELECT key FROM results").fetchall() == [("00000000000000aa",)]
    finally:
        db.close()


def test_an_answer_comes_again_after_a_while_however_many_others_come_meanwhile_and_three_times_at_most(
        tmp_path, monkeypatch):
    """An answer that cannot be applied for a moment, while the pool's other answers come: each of those is
    a round, but the one to apply again waits for its time, and is applied then (the review of package 4's
    fixes: counted by rounds, its three tries were gone after 0.13 s, and its text waited with no job).
    One that never can is given up after three more tries."""
    from texstage.server import activity
    from texstage.server.checking import AGAIN
    c = fake_checks()
    c.again_s = 0.25
    w = World(tmp_path, checks=c, query={"limit": 50})
    w.engine.apply_checks(w.now)
    pids = w.join(*[f"P{i}" for i in range(4)])
    w.show(259)
    act = act_name(w.bid, "query")
    for i, pid in enumerate(pids):
        w.send(pid, "query", text=f"SELECT ?t{i} WHERE {{}}")
    real, state = activity.checked, {"fail": True, "calls": 0}

    def busy(call, aid, msg, again=False):
        if msg.get("text") == "SELECT ?t0 WHERE {}" and state["fail"]:
            state["calls"] += 1
            raise RuntimeError("the store is busy")
        return real(call, aid, msg, again=again)
    monkeypatch.setattr(activity, "checked", busy)
    for i in range(4):                                             # four answers, a round each
        c.pool.futures[(act, f"SELECT ?t{i} WHERE {{}}")].set_result({"status": "ok", "key": f"{i:016x}"})
        w.engine.apply_checks(w.now)
    assert state["calls"] == 1 and len(c.later) == 1               # tried once: its time has not come
    assert [w.phone(p)["mine"]["status"] for p in pids] == ["waiting", "ok", "ok", "ok"]
    state["fail"] = False
    time.sleep(0.3)
    w.engine.apply_checks(w.now)
    assert w.phone(pids[0])["mine"]["status"] == "ok" and c.later == []
    # one that can never be applied: AGAIN more tries, then it is given up - its text waits
    c.again_s = 0
    bea, = w.join("Bea")
    w.send(bea, "query", text="SELECT ?t0 WHERE {} #2")
    monkeypatch.setattr(activity, "checked", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("a bug")))
    c.pool.futures[(act, "SELECT ?t0 WHERE {} #2")].set_result({"status": "ok", "key": K1})
    rounds = 0
    while (c.later or not rounds) and rounds < 10:
        w.engine.apply_checks(w.now)
        rounds += 1
    assert rounds == AGAIN + 1 and c.later == [] and w.phone(bea)["mine"]["status"] == "waiting"


def test_the_server_wakes_itself_once_for_the_answers_to_apply_again(tmp_path):
    """An answer to apply again has nothing to wake the engine when the pool is silent: the server sets one
    wake-up for when it is due, however many rounds come before (app.py: _checked, _again)."""
    make_activity_bundle(tmp_path / "bundles" / "act.bundle")
    config = ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                          presenter_key=KEY, checks="server", workers=1, pool={"spare": False})
    server = create_app(config).state.server
    calls = []

    class Loop:
        def call_later(self, delay, fn):
            calls.append((delay, fn))

        def call_soon_threadsafe(self, fn):
            calls.append(("soon", fn))
    try:
        server.loop = Loop()
        server.checks.later.append((("text", "b", "a", "t", {"status": "ok"}, set()), 1, time.monotonic() + 60))
        server._checked()
        server._checked()
        assert calls == [(server.checks.again_s + 0.01, server._again)]
        server._again()
        assert calls[-1] == ("soon", server._checked) and not server.again_due
        pushed = []                                              # applying fails: the phones due are pushed all the same
        server.push_due = lambda: pushed.append(1)
        server.engine.apply_checks = lambda now: (_ for _ in ()).throw(RuntimeError("a bug"))
        server._checked()
        assert pushed == [1]
    finally:
        server.store.close()


def test_a_commit_that_fails_does_not_lose_the_round(tmp_path, monkeypatch):
    """The store does not commit as the pool's answers are applied: they are applied, the windows and
    phones learn them, and the next commit takes what was saved."""
    c = fake_checks()
    w = World(tmp_path, checks=c)
    w.engine.apply_checks(w.now)
    ada, = w.join("Ada")
    w.show(259)
    w.send(ada, "query", text=RIGHT)
    for fut in c.pool.futures.values():
        fut.set_result({"status": "ok", "key": K1})
    w.engine.take_due()

    def full():
        raise sqlite3.OperationalError("database or disk is full")
    monkeypatch.setattr(w.engine.store, "commit", full)
    assert w.engine.apply_checks(w.now) == {w.s.id}
    assert w.engine.take_due() == {w.s.id: {ada}} and w.phone(ada)["mine"]["status"] == "ok"


def test_a_verdict_is_also_that_of_the_same_text_that_could_not_be_checked_before(tmp_path):
    """Ada's text could not be checked - not set aside: its processes were stopped from outside. Bea sends
    the same text and gets its verdict: Ada's entry has it too, and counts as checked (the review of
    package 4's fixes: hers stayed "could not be checked" until a restart, beside a cluster of two)."""
    c = fake_checks()
    w = World(tmp_path, checks=c)
    w.engine.apply_checks(w.now)
    ada, bea, cy = w.join("Ada", "Bea", "Cy")
    w.show(259)
    act = act_name(w.bid, "query")
    w.send(ada, "query", text=RIGHT)
    c.pool.futures[(act, RIGHT)].set_result({"status": "internal", "error": "died (exit code -15)"})
    w.engine.apply_checks(w.now)
    assert w.phone(ada)["mine"]["status"] == "internal" and w.item("query")["unchecked"] == 1
    w.send(bea, "query", text=RIGHT)
    w.engine.take_due()
    c.pool.futures[(act, RIGHT)].set_result({"status": "ok", "key": K1})
    w.engine.apply_checks(w.now)
    assert w.engine.take_due() == {w.s.id: {ada, bea}}
    w.send(cy, "query", text=RIGHT)
    assert [w.phone(p)["mine"]["status"] for p in (ada, bea, cy)] == ["ok", "ok", "ok"]
    assert (w.item("query")["waiting"], w.item("query")["unchecked"]) == (0, 0)
    assert [(k["key"], k["n"]) for k in w.picture("query")["clusters"]] == [(K1, 3)]
    # an outcome that is not final itself heals nothing: another text, twice internal
    w.tick()
    w.send(ada, "query", text=WRONG)
    c.pool.futures[(act, WRONG)].set_result({"status": "internal", "error": "not prepared: x"})
    w.engine.apply_checks(w.now)
    w.send(bea, "query", text=WRONG)
    c.pool.futures[(act, WRONG)].set_result({"status": "internal", "error": "not prepared: x"})
    w.engine.apply_checks(w.now)
    assert [w.phone(p)["mine"]["status"] for p in (ada, bea)] == ["internal", "internal"]
    assert w.item("query")["unchecked"] == 2


def test_a_stale_games_entries_stay_as_they_are_at_a_restart(tmp_path, pool):
    """A restart leaves a stale game alone - its deck is not prepared, so its entries that could not be
    checked do not wait again either (the review of package 4's fixes: they did, with nobody to check
    them, and the panel said "1 waiting" beside "The server checks the queries.")."""
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference",
              seed=flaky(tmp_path))
    w.settle()
    ada, = w.join("Ada")
    w.show(259)
    w.send(ada, "query", text="ok fine")
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "internal"
    w.now += Settings().stale_ms + 1
    restart(w, pool(engines={"sparql": "pool_engines"}))
    assert w.checks.prepares == {} and not w.checks.waiting
    assert w.phone(ada)["mine"]["status"] == "internal"
    assert (w.item("query")["waiting"], w.item("query")["unchecked"]) == (0, 1)


def test_a_pool_that_breaks_during_the_lecture_is_said_to_the_windows(tmp_path, pool, monkeypatch):
    """The pool breaks while the game runs - a worker dies, and no new process can be started -: the texts
    sent then could not be checked, counted apart from the waiting ones, and the host view says why for the
    activity, though its references are fine (the package 4 review's own case; the review of its fixes:
    only a failed preparing was tested)."""
    from texstage.server import pool as pool_module
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference")
    w.settle()
    assert w.engine.host_view(w.s.id, w.now)["checks"] == {"mode": "server", "failing": {}}
    pids = w.join("Ada", "Bea", "Cy")
    w.show(259)

    def cannot(self):
        raise OSError(1455, "The paging file is too small for this operation to complete")
    monkeypatch.setattr(pool_module._Worker, "start", cannot)
    w.send(pids[0], "query", text="crash")                         # its worker dies; none takes its place
    w.settle()
    for i, pid in enumerate(pids[1:]):
        w.send(pid, "query", text=f"ok fine {i}")
    w.settle()
    assert w.checks.pool.broken
    assert w.engine.host_view(w.s.id, w.now)["checks"]["failing"] == {"query": w.checks.pool.broken}
    assert [w.phone(p)["mine"]["status"] for p in pids] == ["internal"] * 3
    assert (w.item("query")["waiting"], w.item("query")["unchecked"]) == (0, 3)
    assert re.fullmatch(r"[0-9a-f]{16}", w.picture("query", window="stage")["refs"][0])


def test_a_text_set_aside_stays_so_when_the_server_starts_again(tmp_path, pool):
    """The design's rule (AF 6.3): no third worker dies for a text set aside, after a restart neither - its
    entry stays internal, does not wait again, and the same text again is internal at once, without the
    pool; the counts are as before the restart."""
    w = World(tmp_path, checks=pool(engines={"sparql": "pool_engines"}), reference="ok the reference")
    ada, bea = w.join("Ada", "Bea")
    w.show(259)
    w.send(ada, "query", text="crash")
    w.settle()
    restart(w, pool(engines={"sparql": "pool_engines"}))
    w.settle()
    assert w.phone(ada)["mine"]["status"] == "internal" and not w.checks.waiting
    assert (w.item("query")["waiting"], w.item("query")["unchecked"]) == (0, 1)
    w.send(bea, "query", text="crash")
    assert w.phone(bea)["mine"]["status"] == "internal" and not w.checks.waiting
    assert w.checks.pool.stats()["ended"] == []                    # no process of the new pool died


def test_a_deck_built_again_lets_go_of_the_old_build(tmp_path, pool):
    """The lecturer builds the deck again during the lecture and opens it: the old build's game ends, and
    the pool lets go of the old build - after the new game is there (the review of package 4's fixes: no
    test would have seen it held for ever)."""
    new = make_activity_bundle(tmp_path / "bundles" / "act2.bundle", seed=SEED + b":hume :name \"Hume\" .\n")
    w = World(tmp_path, checks=pool())
    w.settle()
    assert new != w.bid and list(w.checks.prepares) == [act_name(w.bid, "query")]
    s = w.engine.open_session("act", new, w.now)
    assert s.id != w.s.id and list(w.checks.prepares) == [act_name(new, "query")]
    w.s = s
    w.settle()
    assert w.checks.pool.stats()["activities"] == 1


def test_a_failed_preparing_reaches_the_windows_of_a_game_that_keeps_its_keys(tmp_path, pool):
    """A game the browser's checks began, with its reference's key, and a restart with --checks server
    whose pool cannot prepare the deck: the game keeps its key, and its windows are pushed all the same,
    to say why the server cannot check."""
    w = World(tmp_path, reference="ok the reference", seed=flaky(tmp_path))
    w.stage("activity.work")
    w.stage("activity.result", activity="query", reference=0, status="ok", key=K1)
    restart(w, pool(engines={"sparql": "pool_engines"}))
    changed, end = set(), time.monotonic() + 60
    while any(p["outcomes"] is None for p in w.checks.prepares.values()):
        changed |= w.engine.apply_checks(w.now)
        assert time.monotonic() < end, "the pool did not answer"
        time.sleep(0.02)
    changed |= w.engine.apply_checks(w.now)
    assert w.s.id in changed
    assert list(w.engine.host_view(w.s.id, w.now)["checks"]["failing"]) == ["query"]
    assert w.picture("query", window="stage")["refs"] == [K1]


def test_a_reference_that_failed_for_its_own_reasons_is_not_the_windows_again_but_the_pools_after_a_restart(
        tmp_path, pool):
    """The window's reference failed - a syntax error, here made up: activity.work does not hand it out
    again (only one not run yet, or one the server could not run); a restart with --checks server fills it
    with the pool's outcome, as it fills none that has a key."""
    w = World(tmp_path)
    w.stage("activity.work")
    w.stage("activity.result", activity="query", reference=0, status="syntax", error="1:1: made up")
    assert w.stage("activity.work")["references"] == {}
    restart(w, pool())
    w.settle()
    assert re.fullmatch(r"[0-9a-f]{16}", w.picture("query", window="stage")["refs"][0])


def test_the_server_resumes_the_checks_as_it_starts_whoever_checks(tmp_path, monkeypatch):
    """What could not be checked waits again when the server starts - for the presenter window too: the
    server runs Engine.resume_checks in the browser's mode as well (a fallback to --checks browser)."""
    make_activity_bundle(tmp_path / "bundles" / "act.bundle")
    seen = []
    real = Engine.resume_checks
    monkeypatch.setattr(Engine, "resume_checks", lambda self, now: (seen.append(self.checks), real(self, now))[1])
    config = ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                          presenter_key=KEY)
    with TestClient(create_app(config)) as client:
        assert client.get("/api/status").json()["checks"] == "browser"
    assert seen == [None]
