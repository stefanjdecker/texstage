# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Live activities on the server (server/activity.py; docs/live-activities-design.md, section 7):
the crowd graph and the clusters through the engine with a fake clock - the presenter window's
evaluation scripted -, a restarted server, the archive; and the whole over WebSockets."""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from texstage.build.bundle import bundle_id
from texstage.server.app import ServerConfig, create_app
from texstage.server.bundles import BundleStore
from texstage.server.game import Engine, GameError, Settings
from texstage.server.store import Store

T0 = 1_800_000_000_000
KEY = "presenter-secret"
BOX = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
SEED = b'@prefix : <http://example.org/> .\n:kant :name "Kant" .\n'
SEED_NAME = f"data/{hashlib.sha256(SEED).hexdigest()[:16]}.ttl"
REFERENCE = "SELECT ?n WHERE { ?p :name ?n }"
RIGHT, WRONG = "SELECT ?n WHERE { ?p :name ?n }", "SELECT ?n WHER { ?p :name ?n }"
K1 = "0123456789abcdef"


def make_activity_bundle(folder: Path, crowd: dict | None = None, query: dict | None = None,
                         reference: str = REFERENCE) -> str:
    """A format-2 bundle as build/activity.py writes one: a crowd graph on slides 257 and 258 (its
    frame's two steps), a query on 259; 256 and 260 ordinary slides."""
    pngs = {f"slides/{hashlib.sha256(d).hexdigest()[:16]}.png": d for d in (b"one", b"two")}
    s1, s2 = list(pngs)
    items = {"crowd": {"input": "tuple", "limit": 3, "fields": ["Subject", "Predicate", "Object"],
                       "suggest": [":KG"], "min": 1} | (crowd or {}),
             "query": {"input": "code", "limit": 3, "engine": "sparql", "tokens": ["SELECT", "{", "}"],
                       "seed": SEED_NAME} | (query or {})}

    def live(item):
        return [{"type": "activity", "item": item, "rects": {"box": BOX}}]
    deck = {"format": 2, "deck": "act", "name": "Act", "types": ["activity"], "image": {"width": 1920, "height": 1080},
            "slides": [{"id": 256, "image": s1}, {"id": 257, "image": s2, "live": live("crowd")},
                       {"id": 258, "image": s2, "live": live("crowd")}, {"id": 259, "image": s2, "live": live("query")},
                       {"id": 260, "image": s1}],
            "items": {"activity": items}}
    keys = {"format": 2, "deck": "act", "items": {"activity": {"query": {"reference": [reference]}}}}
    bid = bundle_id(deck, keys)
    for rel, data in {**pngs, SEED_NAME: SEED}.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    for rel, data in (("deck.json", deck), ("keys.json", keys)):
        (folder / rel).write_text(json.dumps(data | {"bundle": bid}), encoding="utf-8")
    return bid


class World:
    def __init__(self, tmp_path: Path, **kw):
        self.tmp = tmp_path
        self.bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle", **kw)
        self.now = T0
        self.engine = self.start()
        self.s = self.engine.open_session("act", self.bid, self.now)

    def start(self) -> Engine:
        return Engine(BundleStore([self.tmp / "bundles"]), Store(self.tmp / "store.sqlite3"), Settings())

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
                                                "count": 3, "waiting": 0, "revealed": False, "min": 1}
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
            m = ws.receive_json()
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
