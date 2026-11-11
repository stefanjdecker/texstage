# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The pool's process that normalizes (texstage/server/normalizer.py; docs/architecture/activity-
framework-plan-f2.md, package 4): its inputs in order, one that takes too long, a process that ends -
while it works, while it waits, before it is ready -, three in a row that never are ready, and its end.
The process is the tests' own (pool_engines.normalizer); the kinds' normalize through it: test_pool.py."""
from __future__ import annotations

import multiprocessing as mp
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))           # the processes import pool_engines (spawn: this path)

import pool_engines  # noqa: E402

from texstage.server import normalizer as normalizer_module  # noqa: E402
from texstage.server.normalizer import Normalizer  # noqa: E402


def made(options: dict | None = None, **more) -> Normalizer:
    return Normalizer(mp.get_context("spawn"), options, target=pool_engines.normalizer, **more).start()


def ask(n: Normalizer, text: str):
    return n.submit("some-kind", {}, {}, {"text": text})


def until(what, timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if what():
            return True
        time.sleep(0.02)
    return False


def running() -> list:
    return [p for p in mp.active_children() if p.name == "texstage-normalize" and p.is_alive()]


def test_inputs_are_answered_in_the_order_they_came():
    n = made()
    try:
        futures = [ask(n, f"select {i}") for i in range(20)]            # before the process is ready, too
        assert [f.result(60) for f in futures] == [{"input": {"text": f"SELECT {i}"}} for i in range(20)]
        assert n.stats() == {"waiting": 0, "ended": 0, "broken": None}
    finally:
        n.close()


def test_an_input_that_takes_too_long_is_an_error_and_holds_up_no_other():
    n = made(budget_s=0.5)
    try:
        slow, behind = ask(n, "sleep 30"), ask(n, "select 1")
        assert slow.result(30) == {"error": "normalizing took more than 0.5 s"}     # never the student's
        assert behind.result(30) == {"input": {"text": "SELECT 1"}}                 # by the next process
        assert n.stats()["ended"] == 1 and n.stats()["broken"] is None
    finally:
        n.close()


def test_an_input_whose_process_ends_is_tried_again_a_few_times(tmp_path):
    n = made()
    try:
        mark = tmp_path / "once"
        mark.write_text("")
        assert ask(n, f"dieonce {mark}").result(60) == {"input": {"text": f"DIEONCE {mark}".upper()}}
        assert n.stats()["ended"] == 1
        deadly, behind = ask(n, "die"), ask(n, "select 1")
        assert deadly.result(60) == {"error": f"the normalizing process ended {normalizer_module.TRIES} times"}
        assert behind.result(60) == {"input": {"text": "SELECT 1"}}
        assert n.stats() == {"waiting": 0, "ended": 1 + normalizer_module.TRIES, "broken": None}
    finally:
        n.close()


def test_a_process_that_ends_while_it_waits_or_before_it_is_ready_is_replaced():
    n = made()
    try:
        n.proc.kill()                                          # before it took its pipe, or just after
        assert ask(n, "select 1").result(60) == {"input": {"text": "SELECT 1"}}
        assert until(lambda: n.ready and n.stats()["waiting"] == 0)
        ended = n.stats()["ended"]
        n.proc.kill()                                          # while it waits: the next input is no try fewer
        for i in range(5):
            assert ask(n, f"select {i}").result(60) == {"input": {"text": f"SELECT {i}"}}
        assert n.stats()["ended"] == ended + 1 and n.stats()["broken"] is None
    finally:
        n.close()


@pytest.mark.parametrize("options, more", [({"dies": True}, {}), ({"never_ready": True}, {"start_s": 0.3})])
def test_three_processes_in_a_row_that_never_are_ready_break_it(options, more):
    n = made(options, **more)
    try:
        waiting = ask(n, "select 1")
        assert set(waiting.result(60)) == {"error"} and "in a row" in waiting.result()["error"]
        assert n.stats()["broken"] and n.stats()["ended"] == normalizer_module.EARLY_DEATHS
        assert ask(n, "select 2").result(1) == {"error": n.stats()["broken"]}       # at once, from then on
        assert until(lambda: not running(), 10)
    finally:
        n.close()


def test_closed_it_answers_nothing_more_and_leaves_no_process():
    n = made()
    slow, behind = ask(n, "sleep 30"), ask(n, "select 1")
    assert until(lambda: n.current is not None)
    n.close()
    n.close()
    assert slow.cancelled() and behind.cancelled()
    with pytest.raises(RuntimeError, match="closed"):
        ask(n, "select 2")
    assert until(lambda: not running(), 10)
    # closed while the next process is being started: that one is not left behind
    n = made()
    assert until(lambda: n.ready)
    n.proc.kill()
    n.close()
    assert until(lambda: not running(), 10)
    n._spawn()                                                 # (the start that was under way as it closed)
    assert until(lambda: not running(), 10)
    time.sleep(1.0)
    assert not running()
