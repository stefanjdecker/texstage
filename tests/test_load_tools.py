# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The tools of the load runs (tools/load; docs/architecture/activity-framework-plan.md, 4.9, package 6):
the runs' bundle with its stand-ins is one the server takes, and its references are checked ok by the
server's engines; the runner reads the simulator's lines and holds them against the design's budgets. On
F2's core (activity-framework-plan-f2.md, package 13): the simulator's phones speak the core's messages and
load the kinds' files their welcome names, as a phone does - against a server of the core's type that the
runner starts, every entry of a burst acknowledged and checked, the projector's picture counted."""
from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import random
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def tool(name: str, folder: str = "tools/load"):
    spec = importlib.util.spec_from_file_location(f"load_{name}", ROOT / folder / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def simulator():
    pytest.importorskip("websockets")
    return tool("simulate", "tools")


def test_the_runs_bundle_with_its_stand_ins_is_one_the_server_takes_and_its_references_check(tmp_path):
    pytest.importorskip("pyoxigraph")
    from texstage.server.bundles import BundleStore
    from texstage.server.pool import ENGINES
    bid = tool("bundle").make(tmp_path / "bundles" / "load.bundle")
    b = BundleStore([tmp_path / "bundles"]).get(bid)
    assert b is not None and list(b.items["activity"]) == ["sparql", "sparql-big", "turtle", "sql"]
    for aid, item in b.items["activity"].items():
        engine = importlib.import_module(ENGINES[item["engine"]])
        state = engine.load(b.file(item["seed"]).read_text(encoding="utf-8"))
        reference = b.keys["items"]["activity"][aid]["reference"][0]
        outcome = engine.evaluate(state, reference, "en", 2.0)
        assert outcome["status"] == "ok", (aid, outcome)
    big = b.file(b.items["activity"]["sparql-big"]["seed"]).read_text(encoding="utf-8")
    assert big.count(":near") == 2500                                 # the heavier seed: 10,000 triples more


def test_the_runner_reads_the_simulators_lines_and_holds_them_against_the_budgets():
    pytest.importorskip("psutil")
    run = tool("run")
    out = ("game 123456: 1100 phones joined in 30.42 s (the core's activity type)\n"
           "/static/vendor/katex/katex.min.js and the kinds' 2 files loaded by 1100 phones (0 failed, 0 unfinished): "
           "median 40 ms, 95 % 900 ms, max 2100 ms\n"
           "open: 1100 phones after 210 ms (median 120 ms)\n"
           "close: 1100 phones after 640 ms (median 300 ms)\n"
           "projector: the picture changed at most 5 times in a second (31 versions during the burst); its pictures "
           "came in median 4 ms, 95 % 9 ms, max 12 ms (31)\n"
           "panel: the picture changed at most 4 times in a second (30 versions during the burst); its pictures "
           "came in median 5 ms, 95 % 11 ms, max 15 ms (30)\n"
           "acknowledged: median 12 ms, 95 % 348 ms, max 700 ms (1000)\n"
           "checked - sent until the phone had its verdict: median 30 ms, 95 % 3400 ms, max 9000 ms (1000)\n"
           "statuses: {'ok': 700, 'syntax': 290, 'timeout': 10}\n")
    got = run.parse(out)
    assert got == {"joined_s": 30.42, "fetch": [1100, 0, 0, 40, 900, 2100], "open": [1100, 210, 120],
                   "close": [1100, 640, 300], "ack": [12, 348, 700, 1000], "checked": [30, 3400, 9000, 1000],
                   "projector": [5, 31], "panel": [4, 30], "statuses": {"ok": 700, "syntax": 290, "timeout": 10}}
    said = run.table([{"run": "SQL, 1 % runaway", "repetition": 1, **got}])
    assert "an entry acknowledged (95 %), at most 500 ms: held in every run" in said
    assert "its verdict (95 %), at most 3000 ms: NOT in SQL, 1 % runaway #1: 3400 ms" in said
    assert "... and closed, at most 500 ms: NOT in SQL, 1 % runaway #1: 640 ms" in said
    assert "the files on a phone (95 %), at most 30000 ms: held in every run" in said
    assert "the projector's picture, at most 4 updates in a second: NOT in SQL, 1 % runaway #1: 5 updates" in said
    unmeasured = run.table([{"run": "Turtle", "repetition": 1, **{k: v for k, v in got.items() if k != "projector"}}])
    assert "the projector's picture, at most 4 updates in a second: NOT in Turtle #1: None" in unmeasured
    assert [r[0] for r in run.runs("sparql")] == ["SPARQL, 1 % runaway"] * 3 + [
        "SPARQL, 3 % runaway", "SPARQL, 5 % runaway", "SPARQL, heavier seed, 1 %"]


def test_a_phone_of_the_simulator_loads_the_kinds_files_as_a_phone_does():
    """web/kinds.js: a kind's texts in the deck's language - else English - and its input module, then the rest of
    its phone's files but its texts; a file the kinds of one package share, once."""
    sim = simulator()
    shared = {"hash": "a1", "phone": ["texts/de.js", "texts/en.js", "web/hint.js"], "window": ["web/box.js"]}
    files = {"turtle-graph": shared, "sparql-query": dict(shared),
             "sql-query": {"hash": "b/2", "phone": ["texts/en.js", "web/input.js", "web/lib.js"], "window": []}}
    assert sim.kind_paths(files) == ["/kinds/a1/texts/en.js", "/kinds/a1/web/hint.js", "/kinds/b%2F2/texts/en.js",
                                     "/kinds/b%2F2/web/input.js", "/kinds/b%2F2/web/lib.js"]
    assert sim.kind_paths(files, "de-DE")[:2] == ["/kinds/a1/texts/de.js", "/kinds/a1/web/hint.js"]
    assert sim.kind_paths({"text": {"hash": "c", "phone": ["web/x.js"]}}) == ["/kinds/c/web/x.js"]
    assert sim.kind_paths(None) == [] and sim.kind_paths({}) == []


def test_a_phone_of_the_simulator_speaks_the_cores_messages(monkeypatch):
    """With a server of the core's type a phone sends activity.enter with an id of its own, learns the phase from
    activity.step - the same for every phone - and its verdict from its own entries; with F1's, as before."""
    sim = simulator()
    p = sim.Phone("ws://127.0.0.1:1/ws", "123456", "P001", random.Random(1))
    assert sim.Phone.sending("turtle", "b1", p.entry_id(), text="x .") == {"t": "activity.send", "activity": "turtle",
                                                                          "id": "b1", "text": "x ."}
    p.state = {"activity": {"id": "turtle", "phase": "open", "input": "code", "mine": {"id": "c1", "status": "waiting"}}}
    assert p.open("turtle") and p.verdict({"cid": "c1"}) is None
    p.state["activity"]["mine"]["status"] = "syntax"
    assert p.verdict({"cid": "c1"}) == "syntax"
    monkeypatch.setattr(sim.Phone, "core", True)
    eid = p.entry_id()
    assert eid == "P001-entry-0000" and sim.Phone.sending("turtle", "b1", eid, text="x .") == {
        "t": "activity.enter", "activity": "turtle", "entry": eid, "id": "b1", "text": "x ."}
    assert sim.Phone("ws://x", "1", "Ü ber!", random.Random(1)).entry_id() == "__ber_-entry-0000"
    assert p.current() is None and not p.open("turtle")
    p.step = {"activity": "turtle", "step": "main", "phase": "open", "kind": "turtle-graph", "input": "code",
              "limit": 5, "engine": "turtle", "tokens": ["."]}
    p.state = {"activity": {"mine": {"activity": "turtle", "blocked": False,
                                     "entries": [{"id": eid, "input": {"text": "x ."}, "state": "in", "check": "waiting"}]}}}
    assert p.current() == {"id": "turtle", "phase": "open", "input": "code", "limit": 5, "fields": [], "engine": "turtle",
                           "tokens": ["."], "blocked": False} and p.open("turtle")
    assert p.verdict({"eid": eid}) is None
    p.state["activity"]["mine"]["entries"][0] |= {"check": "checked", "status": "invalid"}
    assert p.verdict({"eid": eid}) == "invalid" and p.verdict({"eid": "other-entry-01"}) is None
    p.state["activity"]["mine"]["entries"][0]["check"] = "unchecked"
    assert p.verdict({"eid": eid}) == "unchecked"
    p.state["activity"]["mine"]["blocked"] = True
    p.step = p.step | {"input": "fields", "fields": ["S", "P", "O"], "phase": "closed"}
    assert p.current()["input"] == "tuple" and p.current()["blocked"] and not p.open("turtle")
    w = sim.Window("ws://x", "k", {"deck": "d", "bundle": "b"}, "display", "turtle")
    w.told = [10.0, 10.1, 10.2, 10.3, 10.9, 11.5, 13.0]
    assert w.most_in_a_second(10.0, 20.0) == 5 and w.most_in_a_second(11.0, 20.0) == 1 and w.most_in_a_second(30, 40) == 0


def test_a_file_a_phone_of_the_simulator_cannot_load_is_no_file_loaded():
    """A 404 - a kind's file the server does not have - counts as failed, not as a file of 22 bytes loaded."""
    sim = simulator()

    async def go():
        async def answer(reader, writer):
            await reader.readline()
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\n\r\nnot found")
            await writer.drain()
            writer.close()
        server = await asyncio.start_server(answer, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with pytest.raises(OSError, match="HTTP/1.1 404"):
                await sim.http_get(f"ws://127.0.0.1:{port}/ws", "/kinds/a1/texts/en.js")
        finally:
            server.close()
    asyncio.run(go())


def test_the_load_runs_play_on_a_server_of_the_cores_type(tmp_path):
    """The runner's server of the core's type (--activities core) and a burst of the simulator's: every phone has
    the kinds' files and the stand-in file, sees the step open and closed, and gets every entry acknowledged and
    checked; the projector's and the panel's pictures come as they change."""
    pytest.importorskip("psutil")
    pytest.importorskip("pyoxigraph")
    sim = simulator()                                   # noqa: F841 - (skips without websockets)
    from texstage.activities import registry
    try:
        registry.kind("turtle-graph")
    except LookupError:
        pytest.skip("the kinds are not installed: pip install --no-deps -e kinds/...")
    run = tool("run")
    tool("bundle").make(tmp_path / "bundles" / "load.bundle")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    args = argparse.Namespace(port=port, key="load-runs-test-key", checks="server", activities="core", more=[],
                              tunnel=None, workers=1)
    server = run.Server(tmp_path / "bundles", tmp_path / "data", tmp_path / "server.log", args, True)
    try:
        assert run.status(server.base)["activities"] == "core"
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "simulate.py"), str(tmp_path / "bundles" / "load.bundle"),
                              "--url", f"ws://127.0.0.1:{port}/ws", "--key", args.key, "--players", "6",
                              "--fetch", run.FETCH, "--activity", "turtle", "--burst", "6", "--within", "1", "--wait", "20"],
                             cwd=ROOT, capture_output=True, text=True, timeout=180)
    finally:
        usage = server.stop()
    got = run.parse(out.stdout)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "the core's activity type" in out.stdout and " and the kinds' " in out.stdout, out.stdout
    assert got["fetch"][:3] == [6, 0, 0] and got["open"][0] == 6 and got["close"][0] == 6, out.stdout
    assert got["ack"][3] == 6 and got["checked"][3] == 6, out.stdout
    assert set(got["statuses"]) <= {"ok", "invalid"} and sum(got["statuses"].values()) == 6, out.stdout
    assert got["projector"][1] >= 1 and got["panel"][1] >= 1, out.stdout
    assert not usage["pool_broken"] and usage["workers_ended"] == 0
