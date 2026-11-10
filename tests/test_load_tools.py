# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The tools of the load runs (tools/load; docs/architecture/activity-framework-plan.md, 4.9, package 6):
the runs' bundle with its stand-ins is one the server takes, and its references are checked ok by the
server's engines; the runner reads the simulator's lines and holds them against the design's budgets."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def tool(name: str):
    spec = importlib.util.spec_from_file_location(f"load_{name}", ROOT / "tools" / "load" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    out = ("game 123456: 1100 phones joined in 30.42 s\n"
           "/static/vendor/katex/katex.min.js loaded by 1100 phones (0 failed, 0 unfinished): median 40 ms, "
           "95 % 900 ms, max 2100 ms\n"
           "open: 1100 phones after 210 ms (median 120 ms)\n"
           "close: 1100 phones after 640 ms (median 300 ms)\n"
           "acknowledged: median 12 ms, 95 % 348 ms, max 700 ms (1000)\n"
           "checked - sent until the phone had its verdict: median 30 ms, 95 % 3400 ms, max 9000 ms (1000)\n"
           "statuses: {'ok': 700, 'syntax': 290, 'timeout': 10}\n")
    got = run.parse(out)
    assert got == {"joined_s": 30.42, "fetch": [1100, 0, 0, 40, 900, 2100], "open": [1100, 210, 120],
                   "close": [1100, 640, 300], "ack": [12, 348, 700, 1000], "checked": [30, 3400, 9000, 1000],
                   "statuses": {"ok": 700, "syntax": 290, "timeout": 10}}
    said = run.table([{"run": "SQL, 1 % runaway", "repetition": 1, **got}])
    assert "an entry acknowledged (95 %), at most 500 ms: held in every run" in said
    assert "its verdict (95 %), at most 3000 ms: NOT in SQL, 1 % runaway #1: 3400 ms" in said
    assert "... and closed, at most 500 ms: NOT in SQL, 1 % runaway #1: 640 ms" in said
    assert "the file on a phone (95 %), at most 30000 ms: held in every run" in said
    assert [r[0] for r in run.runs("sparql")] == ["SPARQL, 1 % runaway"] * 3 + [
        "SPARQL, 3 % runaway", "SPARQL, 5 % runaway", "SPARQL, heavier seed, 1 %"]
