# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The tools of the load runs (tools/load; docs/architecture/activity-framework-plan.md, 4.9, package 6):
the runs' bundle with its stand-ins is one the server takes, and its references are checked ok by the
server's engines; the runner reads the simulator's lines and holds them against the design's budgets - what
never came counts as over them - and against what a run must have: every entry and every phone through,
the simulator ended well, the pool whole (the review of 2026-11-19: a run that lost entries, phones and its
pool said "held"). On F2's core (activity-framework-plan-f2.md, package 13): the simulator's phones speak the
core's messages and load the kinds' files their welcome names, as a phone does - against a server of the
core's type that the runner starts, every entry of a burst acknowledged and checked, each with its text's
status and within the verdict's budget, the projector's picture counted, the pool well; and groups.py, which
compares the core's groups with F1's, tells a difference from a tie in another order."""
from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import json
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
    bid = tool("bundle").make(tmp_path / "groups" / "groups.bundle", crowd=True)      # groups.py's: a crowd graph too
    b = BundleStore([tmp_path / "groups"]).get(bid)
    assert b is not None and list(b.items["activity"])[-1] == "crowd" and b.items["activity"]["crowd"]["input"] == "tuple"


WELL = {"exit": 0, "pool_broken": False, "workers_ended_for": [], "normalizer_ended_for": []}   # a run that went well
MUST = ["every entry of the burst sent, acknowledged and given its verdict: ",
        "every phone joined, with its files, and none lost its connection: ", "the simulator ended well: ",
        "the pool not broken, no worker ended but by its watchdog, the normalizing process never: "]


def test_the_runner_reads_the_simulators_lines_and_holds_them_against_the_budgets():
    pytest.importorskip("psutil")
    run = tool("run")
    out = ("game 123456: 1100 phones joined in 30.42 s (the core's activity type)\n"
           "/static/vendor/katex/katex.min.js and the kinds' 2 files loaded by 1100 phones (0 failed, 0 unfinished): "
           "median 40 ms, 95 % 900 ms, max 2100 ms (1100 of 1100)\n"
           "open: 1100 of 1100 phones after 210 ms (median 120 ms)\n"
           "close: 1100 of 1100 phones after 640 ms (median 300 ms)\n"
           "projector: the picture changed at most 5 times in a second (31 versions during the burst); its pictures "
           "came in median 4 ms, 95 % 9 ms, max 12 ms (31)\n"
           "panel: the picture changed at most 4 times in a second (30 versions during the burst); its pictures "
           "came in median 5 ms, 95 % 11 ms, max 15 ms (30)\n"
           "entries: 1000 of 1000 sent within 10.0 s (most at the end); 304 distinct texts, 10 running into their budget\n"
           "acknowledged: median 12 ms, 95 % 348 ms, max 700 ms (1000 of 1000)\n"
           "checked - sent until the phone had its verdict: median 30 ms, 95 % 3400 ms, max 9000 ms (1000 of 1000)\n"
           "... of the texts that do not run into their budget: median 25 ms, 95 % 2900 ms, max 8000 ms (990 of 990)\n"
           "statuses: {'ok': 700, 'syntax': 290, 'timeout': 10}\n"
           "connections lost and taken up again: 0\n")
    got = run.parse(out)
    times = lambda *v: dict(zip(("median", "p95", "max", "n", "of"), v))     # noqa: E731
    assert got == {"joined": {"phones": 1100, "s": 30.42},
                   "fetch": {"loaded": 1100, "failed": 0, "unfinished": 0} | times(40, 900, 2100, 1100, 1100),
                   "open": {"phones": 1100, "of": 1100, "last": 210, "median": 120},
                   "close": {"phones": 1100, "of": 1100, "last": 640, "median": 300},
                   "entries": {"sent": 1000, "of": 1000, "distinct": 304, "runaway": 10},
                   "ack": times(12, 348, 700, 1000, 1000), "checked": times(30, 3400, 9000, 1000, 1000),
                   "others": times(25, 2900, 8000, 990, 990), "projector": {"most": 5, "versions": 31},
                   "panel": {"most": 4, "versions": 30}, "drops": {"n": 0},
                   "statuses": {"ok": 700, "syntax": 290, "timeout": 10}}
    r = {"run": "SQL, 1 % runaway", "repetition": 1, "players": 1100, "burst": 1000, **got, **WELL,
         "workers_ended_for": ["cpu", "cpu", "clock"]}       # (the watchdog's way with the runaway texts: no fault)
    said = run.table([r])
    assert "an entry acknowledged (95 %), at most 500 ms: held in every run" in said
    assert "its verdict (95 %), at most 3000 ms: NOT in SQL, 1 % runaway #1: 3400 ms" in said
    assert "... of the texts that do not run into their budget (95 %), at most 3000 ms: held in every run" in said
    assert "... and closed, at most 500 ms: NOT in SQL, 1 % runaway #1: 640 ms" in said
    assert "the files on a phone (95 %), at most 30000 ms: held in every run" in said
    assert "the projector's picture, at most 4 updates in a second: NOT in SQL, 1 % runaway #1: 5 updates" in said
    assert all(f"{line}held in every run" in said for line in MUST), said
    unmeasured = run.table([{k: v for k, v in r.items() if k != "projector"}])
    assert "the projector's picture, at most 4 updates in a second: NOT in SQL, 1 % runaway #1: not measured" in unmeasured
    phones = run.table([{k: v for k, v in r.items() if k not in ("pool_broken", "workers_ended_for")}])
    assert f"{MUST[3]}the server's side has it" in phones                   # a session's phones' side: not its to say
    pool = {k: v for k, v in WELL.items() if k != "exit"}                  # ... and its server's side: the pool's alone
    server = run.table([{"run": "SQL, 1 % runaway", "repetition": 1, **pool}])
    assert f"{MUST[3]}held in every run" in server and f"{MUST[0]}the phones' side has it" in server
    assert "its verdict (95 %), at most 3000 ms: the phones' side has it" in server
    assert [r[0] for r in run.runs("sparql")] == ["SPARQL, 1 % runaway"] * 3 + [
        "SPARQL, 3 % runaway", "SPARQL, 5 % runaway", "SPARQL, heavier seed, 1 %"]


def test_a_run_that_lost_entries_or_phones_or_broke_the_pool_holds_no_budget_it_cannot_say():
    """The review of 2026-11-19: a synthetic run - 640 of 1,000 entries sent, the files failed on 650 phones, a
    broken pool - and every line said "held", the percentiles being of what came. What never came counts as over
    every budget, an unchecked entry has no verdict, and the counts and the pool's health are held too: in the
    simulator's lines as they are, and as they were before (no "of": short of what was asked for is never)."""
    pytest.importorskip("psutil")
    run = tool("run")
    now = ("game 123456: 1100 phones joined in 30.42 s (the core's activity type)\n"
           "/static/vendor/katex/katex.min.js and the kinds' 2 files loaded by 450 phones (650 failed, 0 unfinished): "
           "median 40 ms, 95 % never, max never (450 of 1100)\n"
           "open: 1100 of 1100 phones after 210 ms (median 120 ms)\n"
           "close: 1100 of 1100 phones after 240 ms (median 100 ms)\n"
           "projector: the picture changed at most 4 times in a second (31 versions during the burst); its pictures "
           "came in median 4 ms, 95 % 9 ms, max 12 ms (31)\n"
           "entries: 640 of 1000 sent within 10.0 s (most at the end); 300 distinct texts, 0 running into their budget\n"
           "acknowledged: median 12 ms, 95 % never, max never (640 of 1000)\n"
           "checked - sent until the phone had its verdict: median 30 ms, 95 % never, max never (630 of 1000)\n"
           "statuses: {'ok': 400, 'invalid': 230, 'not sent': 360, 'unchecked': 10}\n"
           "connections lost and taken up again: 0\n")
    before = ("game 123456: 1100 phones joined in 30.42 s (the core's activity type)\n"
              "/static/vendor/katex/katex.min.js and the kinds' 2 files loaded by 450 phones (650 failed, 0 unfinished): "
              "median 40 ms, 95 % 900 ms, max 2100 ms (450)\n"
              "open: 1100 phones after 210 ms (median 120 ms)\n"
              "close: 1100 phones after 240 ms (median 100 ms)\n"
              "projector: the picture changed at most 4 times in a second (31 versions during the burst)\n"
              "entries: 640 sent within 10.0 s (most at the end); 300 distinct texts, 0 running into their budget\n"
              "acknowledged: median 12 ms, 95 % 348 ms, max 700 ms (640)\n"
              "checked - sent until the phone had its verdict: median 30 ms, 95 % 2900 ms, max 9000 ms (640)\n"
              "statuses: {'ok': 400, 'syntax': 230, 'unchecked': 10}\n")
    broken = {"pool_broken": True, "workers_ended_for": ["cpu", "died (exit code 1)", "died (exit code 1)"],
              "normalizer_ended_for": ["ended (exit code 1)"]}
    for name, out in (("now", now), ("before", before)):
        said = run.table([{"run": name, "repetition": 1, "players": 1100, "burst": 1000, **run.parse(out), **WELL, **broken}])
        held = [line for line in said.splitlines() if line.endswith("held in every run")]
        assert held == ["the activity open on every phone, at most 500 ms: held in every run",
                        "... and closed, at most 500 ms: held in every run",
                        "the projector's picture, at most 4 updates in a second: held in every run",
                        "the simulator ended well: held in every run"], said
        assert f"an entry acknowledged (95 %), at most 500 ms: NOT in {name} #1: never for 360 of 1000" in said
        assert f"its verdict (95 %), at most 3000 ms: NOT in {name} #1: never for {370 if out is now else 360} of 1000" \
            in said
        assert f"the files on a phone (95 %), at most 30000 ms: NOT in {name} #1: never for 650 of 1100" in said
        no = "{'not sent': 360, 'unchecked': 10}" if out is now else "{'unchecked': 10}"
        assert f"{MUST[0]}NOT in {name} #1: 640 of 1000 sent, 640 acknowledged, {630 if out is now else 640} with a " \
               f"verdict {no}" in said
        assert f"{MUST[1]}NOT in {name} #1: the files failed on 650, unfinished on 0" in said
        assert f"{MUST[3]}NOT in {name} #1: broken; workers ended: died (exit code 1) (2); the normalizing process: " \
               "ended (exit code 1)" in said
    # unchecked is no verdict: the 95 % may hold, but what must come did not; connections lost; a simulator that failed
    unchecked = ("game 123456: 1100 phones joined in 30.42 s (the core's activity type)\n"
                 "/static/vendor/katex/katex.min.js loaded by 1100 phones (0 failed, 0 unfinished): median 40 ms, "
                 "95 % 900 ms, max 2100 ms (1100 of 1100)\n"
                 "open: 1100 of 1100 phones after 210 ms (median 120 ms)\n"
                 "close: 1100 of 1100 phones after 240 ms (median 100 ms)\n"
                 "projector: the picture changed at most 4 times in a second (31 versions during the burst)\n"
                 "entries: 1000 of 1000 sent within 10.0 s (most at the end); 300 distinct texts, 0 running into their budget\n"
                 "acknowledged: median 12 ms, 95 % 348 ms, max 700 ms (1000 of 1000)\n"
                 "checked - sent until the phone had its verdict: median 30 ms, 95 % 2900 ms, max never (990 of 1000)\n"
                 "statuses: {'ok': 760, 'invalid': 230, 'unchecked': 10}\n"
                 "connections lost and taken up again: 2\n")
    said = run.table([{"run": "Turtle", "repetition": 1, "players": 1100, "burst": 1000, **run.parse(unchecked), **WELL,
                       "exit": 1}])
    held = [line for line in said.splitlines() if line.endswith("held in every run")]
    assert len(held) == len(run.BUDGETS) + 1 and f"{MUST[3]}held in every run" in held, said    # the budgets, the pool
    assert f"{MUST[0]}NOT in Turtle #1: 1000 of 1000 sent, 1000 acknowledged, 990 with a verdict {{'unchecked': 10}}" \
        in said
    assert f"{MUST[1]}NOT in Turtle #1: 2 connections lost and taken up again" in said
    assert f"{MUST[2]}NOT in Turtle #1: exit 1" in said
    failed = run.table([{"run": "SQL", "repetition": 1, "players": 1100, "burst": 1000, **run.parse(""), **WELL,
                         "exit": "timeout (900 s)"}])
    assert [line for line in failed.splitlines() if line.endswith("held in every run")] == [f"{MUST[3]}held in every run"]
    assert "an entry acknowledged (95 %), at most 500 ms: NOT in SQL #1: not measured" in failed
    assert f"{MUST[2]}NOT in SQL #1: exit timeout (900 s)" in failed


def test_the_runner_reads_why_the_pool_ended_its_workers():
    """The server's log as pool.py writes it: why each worker ended - the watchdog's "cpu" and "clock" told apart
    from a fault - and the CPU time it had taken, no other line that names a worker; and the ends of the pool's
    normalizing process, as normalizer.py writes them."""
    pytest.importorskip("psutil")
    run = tool("run")
    log = ("12:00:01 checks: worker 4242 ended: cpu (after 1.5 s of CPU)\n"
           "12:00:02 checks: worker 4243 is not in the job object\n"
           "12:00:03 checks: worker 4244 ended: died (exit code 3)\n"
           "12:00:03 checks: the normalizing process ended (exit code 1)\n"
           "12:00:03 checks: the normalizing process, as it became ready\n"
           "12:00:04 checks: worker 4245 ended: could not prepare sql: no (such) table (after 0.7 s of CPU)\n"
           "12:00:04 checks: the normalizing process did not start (OSError: no)\n"
           "12:00:05 checks: 3 processes in a row died before they were ready; no more are started\n")
    assert run.ended(log) == ["cpu", "died (exit code 3)", "could not prepare sql: no (such) table"]
    assert run.ended_cpu(log) == pytest.approx(2.2) and run.ended("") == [] and run.ended_cpu("") == 0
    assert run.normalizer_ended(log) == ["ended (exit code 1)", "did not start (OSError: no)"]
    assert run.pool_broke(log) and not run.pool_broke(log.split("12:00:05")[0])
    assert run.pool_broke("12:00:01 checks: the pool did not start: no job object\n")         # (checking.py: NoPool)
    checking = (ROOT / "src" / "texstage" / "server" / "checking.py").read_text(encoding="utf-8")
    assert 'NoPool(f"the pool did not start: ' in checking
    pool = (ROOT / "src" / "texstage" / "server" / "pool.py").read_text(encoding="utf-8")
    assert 'logs.append(f"checks: worker {w.pid} ended: {why}"' in pool and '(after {w.cpu:.1f} s of CPU)' in pool
    normalizer = (ROOT / "src" / "texstage" / "server" / "normalizer.py").read_text(encoding="utf-8")
    assert 'log.warning("checks: the normalizing process %s", why)' in normalizer       # the lines the runner reads
    assert all(why in normalizer for why in ('f"ended (exit code', 'f"did not start (', 'f"ended before it was ready'))


def test_the_runs_ends_are_the_ones_before_its_teardown(tmp_path, monkeypatch):
    """Server.stop kills the server's processes, its workers first; a pool that still runs logs their deaths -
    "died (exit code -9)", the teardown's. They are not the run's: CI on 2026-11-19 failed on a worker and the
    normalizing process killed so, after 0.2 s of CPU (likely the "1 == 0" before 077ec93, too)."""
    pytest.importorskip("psutil")
    run = tool("run")
    log = tmp_path / "server.log"
    log.write_text("12:00:01 checks: worker 41 ended: cpu (after 1.5 s of CPU)\n", encoding="utf-8")

    class Gone:                                         # a process of the tree: killed, the pool logs it
        def __init__(self, pid):
            self.pid = pid

        def children(self, recursive=False):
            return [Gone(42)]

        def kill(self):
            with log.open("a", encoding="utf-8") as f:
                f.write(f"12:00:09 checks: worker {self.pid} ended: died (exit code -9) (after 0.2 s of CPU)\n"
                        "12:00:09 checks: the normalizing process ended (exit code -9)\n")
    monkeypatch.setattr(run.psutil, "Process", Gone)
    server = object.__new__(run.Server)
    server.log, server.watching, server.peak, server.served = log, True, {"server_mb": 1, "worker_mb": 1, "workers": 1}, "core"
    server.proc = type("Proc", (), {"pid": 40, "wait": lambda self, timeout=None: 0})()
    server.tree = lambda: (None, [])
    usage = server.stop()
    assert usage["workers_ended_for"] == ["cpu"] and usage["normalizer_ended_for"] == [], usage
    assert "died (exit code -9)" in log.read_text(encoding="utf-8")       # (written - by the teardown)


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
    e = {"eid": eid}                                    # unchecked - the server could not - is no verdict: it may come yet
    p.note(e)
    assert e == {"eid": eid, "status": "unchecked"}
    p.state["activity"]["mine"]["entries"][0] |= {"check": "checked", "status": "internal"}   # set aside: final, none
    p.note(e)
    assert e == {"eid": eid, "status": "internal"}
    p.state["activity"]["mine"]["entries"][0]["status"] = "ok"
    p.note(e)
    assert e["status"] == "ok" and isinstance(e["checked"], int)
    p.state["activity"]["mine"]["blocked"] = True
    p.step = p.step | {"input": "fields", "fields": ["S", "P", "O"], "phase": "closed"}
    assert p.current()["input"] == "tuple" and p.current()["blocked"] and not p.open("turtle")
    w = sim.Window("ws://x", "k", {"deck": "d", "bundle": "b"}, "display", "turtle")
    w.told = [10.0, 10.1, 10.2, 10.3, 10.9, 11.5, 13.0]
    assert w.most_in_a_second(10.0, 20.0) == 5 and w.most_in_a_second(11.0, 20.0) == 1 and w.most_in_a_second(30, 40) == 0


def test_the_simulators_times_count_what_never_came_and_its_burst_has_each_common_text():
    """The percentiles of a burst, its files, over all there were to be: one that never came is "never", over any
    budget. A burst has each of its few common texts once, then again and again: a small one a wrong one too."""
    sim = simulator()
    assert sim.percentiles([30, 10, 20]) == "median 20 ms, 95 % 30 ms, max 30 ms (3)" and sim.percentiles([]) == "none"
    assert sim.percentiles([30, 10, 20], 3) == "median 20 ms, 95 % 30 ms, max 30 ms (3 of 3)"
    assert sim.percentiles([30, 10, 20], 4) == "median 30 ms, 95 % never, max never (3 of 4)"
    assert sim.percentiles(list(range(1, 21)), 21) == "median 11 ms, 95 % 20 ms, max never (20 of 21)"
    assert sim.percentiles([], 2) == "median never, 95 % never, max never (0 of 2)"
    reference = "ex:Berlin rdfs:label \"Berlin\"@de ;\n  ex:population 3596999 ."
    texts = sim.burst_texts("turtle", reference, 6, 0.3, 0.0, random.Random(1))
    assert len(texts) == 6 and reference in texts and reference.rstrip(" .") in texts        # (a syntax error)
    assert len(set(texts)) == 6 and sum(t.startswith(reference + "\nex:extra") for t in texts) == 2
    texts = sim.burst_texts("sql", "SELECT 1", 100, 0.3, 0.01, random.Random(1))
    assert len(texts) == 100 and sum(map(sim.is_runaway, texts)) == 1 and "SELEC 1" in texts


def test_the_groups_comparison_tells_a_difference_from_groups_of_one_count_in_another_order():
    """tools/load/groups.py (package 13's comparison, in the repository since the review of 2026-11-19): F1's clusters
    by the core's group ids; a count, a status or a reference mark that differs is a difference, an example is not;
    groups of one count in another order - F1 orders them by raw key, the core ok first -, at the end of the
    projector's few too, are said apart."""
    pytest.importorskip("psutil")
    simulator()
    groups = tool("groups")
    from texstage.activities.store import gid
    f1 = {"kind": "clusters", "students": 7, "count": 7, "others": 0, "clusters": [
        {"key": "k1", "status": "ok", "n": 3, "reference": True, "example": "SELECT 1"},
        {"key": "error", "status": "error", "n": 1, "reference": False, "example": "SELECT x"},
        {"key": "k2", "status": "ok", "n": 1, "reference": False, "example": "SELECT 2"},
        {"key": "syntax", "status": "syntax", "n": 1, "reference": False, "example": "SELEC 1"}]}
    core = {"kind": "groups", "students": 7, "entries": 7, "others": 0, "groups": [
        {"id": gid("ok", "k1"), "status": "ok", "n": 3, "reference": True, "example": {"text": "select 1"}},
        {"id": gid("ok", "k2"), "status": "ok", "n": 1, "reference": False},
        {"id": gid("error"), "status": "error", "n": 1, "reference": False},
        {"id": gid("invalid"), "status": "invalid", "n": 1, "reference": False}]}
    assert groups.differ(groups.view(f1), groups.view(core)) == ([], True)
    assert groups.differ(groups.view(f1), groups.view(f1)) == ([], False)
    core["groups"][0] |= {"n": 2, "reference": False}
    found, _ = groups.differ(groups.view(f1), groups.view(core))
    assert found == [f"group {gid('ok', 'k1')} (ok): n 3 in F1's, 2 in the core's",
                     f"group {gid('ok', 'k1')} (ok): reference True in F1's, False in the core's",
                     "the groups' counts in order: [3, 1, 1, 1] in F1's, [2, 1, 1, 1] in the core's"]
    core["groups"][0] |= {"n": 3, "reference": True}                      # the projector's few end in a tie: F1's
    f1 |= {"others": 2, "clusters": f1["clusters"][:2]}                    # with the error, the core's with k2
    core |= {"others": 2, "groups": core["groups"][:2]}
    assert groups.differ(groups.view(f1), groups.view(core)) == ([], True)
    core["groups"][1] |= {"n": 2}
    assert groups.differ(groups.view(f1), groups.view(core))[0] == [
        "the groups' counts in order: [3, 1] in F1's, [3, 2] in the core's"]
    texts = groups.texts("sparql", "SELECT ?n WHERE { ?r :name ?n }")
    assert texts[:2] == ["SELECT ?n WHERE { ?r :name ?n }"] * 2 and "SELEC ?n WHERE { ?r :name ?n }" in texts
    c = groups.corpus("crowd", {"input": "tuple"}, [], random.Random(1), 5)
    assert c["players"] == ["S01", "S02", "S03", "S04", "S05"] and c["acts"] and not c["reveal"]
    assert all(e["input"]["fields"][1].strip().lower() == ":attends" for e in c["rounds"][0])


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
    checked - each with its text's status, its verdict within the budget -; the projector's and the panel's
    pictures come as they change; and the pool is well: not broken, no worker ended but once at most by its
    watchdog, its normalizing process never ended."""
    pytest.importorskip("psutil")
    pytest.importorskip("pyoxigraph")
    sim = simulator()                                   # noqa: F841 - (skips without websockets)
    from texstage.activities import registry
    try:
        registry.kind("turtle-graph")
    except LookupError:
        pytest.skip("the kinds are not installed: pip install --no-deps -e kinds/...")
    run = tool("run")
    bundle = tmp_path / "bundles" / "load.bundle"
    tool("bundle").make(bundle)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    args = argparse.Namespace(port=port, key="load-runs-test-key", checks="server", activities="core", more=[],
                              tunnel=None, workers=1)
    server = run.Server(tmp_path / "bundles", tmp_path / "data", tmp_path / "server.log", args, True)
    try:
        assert run.status(server.base)["activities"] == "core"
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "simulate.py"), str(bundle),
                              "--url", f"ws://127.0.0.1:{port}/ws", "--key", args.key, "--players", "6",
                              "--fetch", run.FETCH, "--activity", "turtle", "--burst", "6", "--within", "1", "--wait", "20",
                              "--entries", str(tmp_path / "entries.json")],
                             cwd=ROOT, capture_output=True, text=True, timeout=180)
    finally:
        usage = server.stop()
    log = (tmp_path / "server.log").read_text(encoding="utf-8", errors="replace")
    said = (f"{out.stdout}{out.stderr}\nthe pool: {usage}\nits log: "            # (a failure in CI says why: the
            + " | ".join(line for line in log.splitlines() if "checks:" in line))         # workers' ends among it)
    got = run.parse(out.stdout)
    assert out.returncode == 0, said
    assert usage["served"] == "core" and "the core's activity type" in out.stdout and " and the kinds' " in out.stdout, said
    assert (got["fetch"]["loaded"], got["fetch"]["failed"], got["fetch"]["unfinished"]) == (6, 0, 0), said
    assert got["open"]["phones"] == got["close"]["phones"] == 6 and got["entries"]["sent"] == 6, said
    assert got["ack"]["n"] == got["checked"]["n"] == 6, said
    # each text's status: the burst has each common text once (simulate.py: burst_texts) - the reference, written on
    # one line, another graph, all ok, and the reference without its last period, invalid - and two distinct, ok
    wrong = json.loads((bundle / "keys.json").read_text(encoding="utf-8"))["items"]["activity"]["turtle"]["reference"][0]
    wrong = wrong.strip().rstrip(" .\n")
    entries = json.loads((tmp_path / "entries.json").read_text(encoding="utf-8"))
    assert sorted((e["text"] == wrong, e["status"]) for e in entries) == [(False, "ok")] * 5 + [(True, "invalid")], said
    assert got["statuses"] == {"ok": 5, "invalid": 1}, said
    assert got["projector"]["versions"] >= 1 and got["panel"]["versions"] >= 1, said
    # The verdicts within their budget (AF 15.1: 3 s for 95 %) - a check slowed by 0.6 s of CPU made 4.7 s (the review
    # of 2026-11-19). And the watchdog ends a worker whose check runs over its first slice of CPU time, or over the
    # clock's backstop, and the check runs again (pool.py): one such end is let pass - CI's Linux job had one on
    # 2026-11-18, and why was not recorded, so the message now says it -, no more: the burst has no text that runs
    # away, and that check of 0.6 s ended five workers. Any other end is a fault, as is one of the normalizing process
    # (its input runs again: the verdicts do not show it).
    value, budget, unit = run.BUDGETS["its verdict (95 %)"]
    assert run.over(value(got | {"players": 6, "burst": 6}), budget, unit) is None, said
    ends = usage["workers_ended_for"]
    assert not usage["pool_broken"] and set(ends) <= set(run.WATCHDOG) and len(ends) <= 1, said
    assert not usage["normalizer_ended_for"], said
