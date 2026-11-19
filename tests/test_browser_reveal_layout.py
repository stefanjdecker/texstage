# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The projector's box of groups with one shown, drawn by the stage's own StepBox with its own stylesheets in a
real browser: no bar lies under the card - in a box as wide as KG's river-settlements' (1.35 wide for 1 high),
where the card stands beside the bars, and in one taller than wide, where it stands below them and the bars
are made to fit above it (the second review of 2026-11-19: in KG's boxes the last bars lay under the card,
which the texts' tests could not see)."""
from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest

from test_browser_smoke import browser, new_page  # noqa: F401 - (the fixtures)

WEB = Path(__file__).resolve().parents[1] / "src" / "texstage" / "web"
STAGE = {"width": 1280, "height": 720}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/shared/live.css"><link rel="stylesheet" href="/stage/stage.css">
<style>body { margin: 0 } .tq-stage { width: 1280px }</style></head><body>
<div class="tq-stage" style="--tq-aspect: 16 / 9"><div class="tq-live"></div></div></body></html>"""

DRAW = """async (rect) => {
  const { StepBox } = await import("/stage/activities.js");
  const result = (columns, n) => ({ columns, rows: Array.from({ length: Math.min(n, 8) }, (_, i) => columns.map((c) => c + i)), count: n });
  const groups = [
    { id: "g1", status: "ok", n: 31, example: { text: "SELECT ?name ?settlementName WHERE {\\n  ?river a :River ; :name ?name .\\n  ?s :locatedOnBank ?river ; :name ?settlementName .\\n}" }, detail: result(["name", "settlementName"], 8) },
    { id: "g2", status: "ok", n: 12, example: { text: "SELECT ?name WHERE { ?r a :River ; :name ?name }" }, detail: result(["name"], 5) },
    { id: "g3", status: "ok", n: 9, example: { text: "SELECT ?name ?settlementName WHERE { ?r :name ?name . ?x :locatedOnBank ?s . ?s :name ?settlementName }" }, detail: result(["name", "settlementName"], 40) },
    { id: "g4", status: "ok", n: 7, example: { text: "SELECT * WHERE { ?river a :River ; :name ?name . ?s :locatedOnBank ?river ; :name ?settlementName }" }, detail: result(["river", "name", "s", "settlementName"], 8) },
    { id: "g5", status: "ok", n: 5, example: { text: "SELECT ?name ?settlementName WHERE { ?r :name ?name . ?s :name ?settlementName }" }, detail: result(["name", "settlementName"], 85) },
    { id: "g6", status: "ok", n: 4, example: { text: "SELECT ?settlementName ?name WHERE { ?r :name ?name . ?s :locatedOnBank ?r ; :name ?settlementName }" }, detail: result(["settlementName", "name"], 8) },
    { id: "g7", status: "invalid", n: 3, example: { text: "SELEC ?name" } },
  ];
  const box = new StepBox({ id: "river-settlements", item: { kind: "sparql-query" }, layer: document.querySelector(".tq-live"),
    language: "en", host: { role: "projector", read: () => new Promise(() => {}) } });
  box.place({ box: rect });
  box.picture = { kind: "groups", phase: "closed", students: 71, entries: 71, groups, others: 0, shown: { ...groups[3] } };
  box.draw();
  await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
  box.fit();
  const of = (e) => e.getBoundingClientRect();
  const cards = [...document.querySelectorAll(".tq-cards .tq-shown")].map(of);
  const bars = [...document.querySelectorAll(".tq-cluster")].map(of);
  const area = of(box.el);
  const meet = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  return { classes: [...box.el.classList].sort(), cards: cards.length, bars: bars.length,
           under: bars.filter((b) => cards.some((c) => meet(b, c))).length,
           outside: bars.filter((b) => b.bottom > area.bottom + 1 || b.right > area.right + 1).length };
}"""


@pytest.fixture(scope="module")
def web():
    """The pages' folder over HTTP (its modules import each other by relative paths), on a free port."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.mark.parametrize("rect, tall", [
    ({"x": 0.43874, "y": 0.15473, "w": 0.49876, "h": 0.65555}, False),        # river-settlements' box: 1.35
    ({"x": 0.35, "y": 0.06, "w": 0.30, "h": 0.72}, True),                     # taller than wide: 0.74
])
def test_no_bar_lies_under_the_shown_card(new_page, web, rect, tall):
    page = new_page(viewport=STAGE)
    page.goto(f"{web}/shared/live.css")                                # (the folder's origin, for the module)
    page.set_content(PAGE)
    report = page.evaluate(DRAW, rect)
    assert ("tq-tall" in report["classes"]) == tall, report
    assert {k: report[k] for k in ("cards", "bars", "under", "outside")} == {"cards": 1, "bars": 7, "under": 0,
                                                                              "outside": 0}, report
