# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The pool of worker processes (texstage/server/pool.py and worker.py; the plan's 4.4 and 4.8, and what
package 3's review found): a check as the checks make it, with the references and the diff; references
checked on one process first, a runaway one a timeout, a crashing one internal; preparing again, dropping;
budgets of CPU time, stopped from inside or by ending the worker; the clock's backstop and the seed's; a
worker that dies - the check once more on a fresh process, then internal, set aside -; memory; the spare;
the priority; the job object (Windows), the address space (Linux); the students' turns; a retry without a
spare; a large seed sent to a busy worker, the pool's lock free all the while; closing; a pool whose
processes die or do not start. And what the second review found (2026-11-10): a prepare after a drop,
checks made against an earlier prepare, a process that cannot prepare what another did, SQLite's own cap,
retries on fresh processes, the queue left alone while no worker is free, a student's texts that wait,
closing while a process starts, a lower address space. Then the same data on every process: a seed's run
on the first one, copied to the others. And what package 4's review found: a text set aside says so, one
whose processes were stopped from outside is not set aside, and the workers leave Ctrl+C and Ctrl+Break to
the server. Budgets of 200 ms keep it quick. The test engine,
tests/pool_engines.py, does what a text says."""
from __future__ import annotations

import concurrent.futures as cf
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

psutil = pytest.importorskip("psutil")

sys.path.insert(0, str(Path(__file__).parent))           # the workers import pool_engines (spawn: this path)

from texstage import checks  # noqa: E402
from texstage.checks import common, texts  # noqa: E402
from texstage.server import pool as pool_module  # noqa: E402
from texstage.server.pool import Pool  # noqa: E402

ENGINES = {"sql": "texstage.checks.sql", "sparql": "texstage.checks.sparql", "test": "pool_engines"}
SQL_SEED = ("CREATE TABLE packing (item TEXT, quantity INTEGER);"
            " INSERT INTO packing VALUES ('Apples', 6), ('Cups', 6), ('Blankets', 2);")
REFERENCE = "SELECT item FROM packing WHERE quantity = 6"
RUNAWAY = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT count(*) FROM r"
RDF = "@prefix : <http://e.org/> .\n" + "\n".join(f":s{i} :p :o{i} ." for i in range(300))
FAST = 0.2
QUERIES_ONLY = texts.ENGINES["en"]["queriesOnly"]


@pytest.fixture(scope="module")
def pool():
    p = Pool(workers=2, engines=ENGINES, reference_budget_s=0.3).start()
    p.prepare("sql", "sql", SQL_SEED, [REFERENCE], "en").result(60)
    p.prepare("test", "test", "a seed").result(60)
    yield p
    p.close()


@pytest.fixture(autouse=True)
def whole(request):
    """Each test with the module's pool starts with it whole again: its workers and its spare ready, every
    activity prepared everywhere."""
    if "pool" in request.fixturenames:
        assert request.getfixturevalue("pool").wait_ready(60)


@pytest.fixture
def thread_errors(monkeypatch):
    """What escapes a thread of the pool: nothing should."""
    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda a: errors.append(f"{a.thread.name}: {a.exc_value!r}"))
    return errors


def check(p: Pool, act: str, text: str, **kw) -> dict:
    return p.submit(act, text, **kw).result(60)


def pids(p: Pool) -> tuple[set, set]:
    with p.lock:
        return {w.pid for w in p.workers}, {w.pid for w in p.spares}


def ended(p: Pool, since: int = 0) -> list[str]:
    return [e["why"] for e in p.stats()["ended"][since:]]


def checks_made(p: Pool, pid: int) -> int:
    """How many checks a process has made: 1 after a retry, if the retry found it fresh."""
    with p.lock:
        return next(w.done for w in p.workers + p.spares if w.pid == pid)


# ------------------------------------------------------------------ checks and references
def test_a_check_in_the_pool_is_the_checks_own(pool):
    state = checks.load("sql", SQL_SEED)
    reference = checks.evaluate("sql", state, REFERENCE, "en")
    for text, language in [("select item from packing where quantity=6", "en"), ("SELECT item FROM packing", "en"),
                           ("SELEC x", "en"), ("DELETE FROM packing", "de"), ("SELECT 1; SELECT 2", "de")]:
        got = check(pool, "sql", text, language=language)
        want = checks.evaluate("sql", state, text, language)
        assert (got["status"], got.get("error")) == (want["status"], want.get("error")), text
        if want["status"] == "ok":
            assert got["key"] == want["key"]
            assert got["summary"] == want["summary"] | {"diff": common.compare(want["rows"], reference["rows"])}
        assert "rows" not in got and "canonical" not in got        # they stay in the worker


def test_the_references_are_checked_as_the_activity_is_prepared(pool):
    outcomes = pool.prepare("refs", "sql", SQL_SEED, ["SELECT 1", "SELEC", REFERENCE], "de").result(60)
    assert [o["status"] for o in outcomes] == ["ok", "syntax", "ok"]
    assert all("diff" not in o.get("summary", {}) for o in outcomes)
    assert pool.wait_ready(60)
    r = check(pool, "refs", "SELECT 1 UNION ALL SELECT 2")         # against the first that gave a result,
    assert r["summary"]["diff"] == {"common": 1, "missing": 0, "extra": 1}     # on every process
    pool.drop("refs")


def test_a_runaway_reference_is_a_timeout_and_holds_up_one_process(pool):
    workers, _ = pids(pool)
    started = time.perf_counter()
    prepared = pool.prepare("run", "test", "a seed", ["spin 30", "ok the reference"])
    r = check(pool, "test", "ok while it runs")                     # the others go on meanwhile
    assert r["status"] == "ok" and time.perf_counter() - started < 0.4
    outcomes = prepared.result(60)
    assert [o["status"] for o in outcomes] == ["timeout", "ok"]
    assert pool.wait_ready(60)
    r = check(pool, "run", "ok a text")
    assert r["status"] == "ok" and r["summary"]["diff"] == {"common": 0, "missing": 1, "extra": 1}
    pool.drop("run")


def test_a_reference_that_ends_its_process_is_internal_and_its_activity_works(pool):
    n = len(ended(pool))
    outcomes = pool.prepare("crashing", "test", "a seed", ["crash", "ok the reference"]).result(60)
    assert [o["status"] for o in outcomes] == ["internal", "ok"] and len(ended(pool)) == n + 1   # one process, not all
    assert check(pool, "crashing", "ok a text")["status"] == "ok"
    pool.drop("crashing")


def test_an_engines_failure_is_the_texts_error(pool):
    r = check(pool, "test", "raise")
    assert (r["status"], r["error"]) == ("error", "the engine broke")


def test_the_same_text_while_it_is_checked_is_one_job(pool):
    a = pool.submit("test", "spin 0.3", owner="p1")
    b = pool.submit("test", "spin 0.3", owner="p2")
    assert a is b and a.result(60)["status"] == "ok"


def test_a_seed_that_does_not_load_fails_its_activity(pool):
    with pytest.raises(ValueError, match="it says fail"):
        pool.prepare("bad", "test", "fail now").result(60)
    r = check(pool, "bad", "ok x")
    assert r["status"] == "internal" and "it says fail" in r["error"]
    pool.drop("bad")


def test_a_seed_that_ends_two_processes_fails_its_activity(pool):
    n = len(ended(pool))
    with pytest.raises(ValueError, match="ended 2 processes"):
        pool.prepare("killer", "test", "crash").result(60)
    assert len(ended(pool)) == n + 2                                # its loading ends two processes, not all
    pool.drop("killer")
    assert pool.wait_ready(60) and check(pool, "test", "ok after the killer")["status"] == "ok"


def test_preparing_again_replaces_what_was_prepared():
    """A prepare waits behind a check; the activity is prepared again meanwhile, with another seed."""
    p = Pool(workers=1, spare=False, engines=ENGINES).start()
    try:
        p.prepare("x", "test", "a seed").result(60)
        busy = p.submit("x", "sleep 1", budget_s=1.0)
        time.sleep(0.2)
        first = p.prepare("t", "test", "v1", ["ok reference"])
        second = p.prepare("t", "test", "v2", ["ok reference"])
        assert second.result(30)[0]["summary"]["seed"] == "v2"
        assert first.cancelled()
        assert check(p, "t", "ok a text")["summary"]["seed"] == "v2"
        failing = p.prepare("u", "test", "fail at first")              # a seed that fails, then a good one
        good = p.prepare("u", "test", "the good seed")
        assert failing.cancelled() and good.result(30) == []
        assert check(p, "u", "ok a text")["summary"]["seed"] == "the good seed"
        assert busy.result(30)["status"] == "ok"
    finally:
        p.close()


def test_preparing_again_after_a_drop_is_answered_by_the_new_prepare():
    """Generations are the pool's: what a prepare dropped while it loads answers does not count for the next
    one under its name (the second review: both were generation 1, and the old reference's outcome came)."""
    p = Pool(workers=1, spare=False, engines=ENGINES).start()
    try:
        assert p.wait_ready(60)
        p.prepare("t", "test", "slow 1", ["ok the old reference"])
        time.sleep(0.3)                                                     # it loads the old seed
        p.drop("t")
        assert p.prepare("t", "test", "the new seed", ["raise"]).result(30) == [
            {"status": "error", "error": "the engine broke"}]
        assert check(p, "t", "ok a text")["summary"]["seed"] == "the new seed"
    finally:
        p.close()


def test_after_a_drop_and_a_new_prepare_every_process_has_the_new_one():
    """The deck reloaded while the workers are busy, their prepares behind their checks: each process
    prepares what is prepared now (the second review: one counted as prepared from the dropped prepare's
    answer, had nothing, and answered every check `internal`)."""
    p = Pool(workers=2, engines=ENGINES).start()
    try:
        p.prepare("x", "test", "seed x").result(60)
        assert p.wait_ready(60)
        busy = [p.submit("x", f"sleep 1.{i}5", owner=f"busy{i}", budget_s=2.0) for i in range(2)]
        time.sleep(0.2)
        assert p.prepare("t", "test", "seed v1", ["ok r"]).result(30)[0]["summary"]["seed"] == "seed v1"
        p.drop("t")
        assert p.prepare("t", "test", "seed v2", ["ok r"]).result(30)[0]["summary"]["seed"] == "seed v2"
        assert all(f.result(30)["status"] == "ok" for f in busy) and p.wait_ready(30)
        rs = [f.result(30) for f in [p.submit("t", f"ok text {i}", owner=f"s{i}") for i in range(20)]]
        assert {(r["status"], r["summary"]["seed"]) for r in rs} == {("ok", "seed v2")}
    finally:
        p.close()


def test_a_check_made_against_an_earlier_prepare_runs_again_against_the_new_one():
    """Prepared again with another seed while a text is checked: that text - and the same text submitted
    after, which joins it - is checked against the new seed; a text of an activity dropped meanwhile is
    `internal` (the second review: the old seed's outcome came)."""
    p = Pool(workers=1, spare=False, engines=ENGINES).start()
    try:
        p.prepare("t", "test", "seed v1").result(60)
        assert p.wait_ready(60)
        running = p.submit("t", "sleep 0.5 the text", budget_s=1.0)
        time.sleep(0.2)
        p.prepare("t", "test", "seed v2")
        again = p.submit("t", "sleep 0.5 the text", budget_s=1.0)
        r = again.result(30)
        assert again is running and (r["status"], r["summary"]["seed"], r["tries"]) == ("ok", "seed v2", 1)
        gone = p.submit("t", "sleep 0.5 gone", budget_s=1.0)
        time.sleep(0.2)
        p.drop("t")
        assert (gone.result(30)["status"], gone.result()["error"]) == ("internal", "dropped")
    finally:
        p.close()


@pytest.mark.parametrize("what", ["seed", "reference"])
def test_a_process_that_cannot_prepare_what_another_did_is_replaced(tmp_path, what):
    """The seed does not load on one process, or the reference with the rows gives none there: that process
    is ended, a fresh one prepares the activity, and every check compares alike (the second review: the
    activity failed for every process, unannounced - or that process's checks carried no diff)."""
    flaky = f"flaky {tmp_path / 'n'} 2"                                     # the second time, once
    p = Pool(workers=2, engines=ENGINES).start()
    try:
        assert p.wait_ready(60)
        seed, refs = (flaky, ["ok ref"]) if what == "seed" else ("a seed", [flaky])
        assert p.prepare("f", "test", seed, refs).result(60)[0]["status"] == "ok"
        assert p.wait_ready(60)
        rs = [check(p, "f", f"ok text {i}", owner=f"s{i}") for i in range(10)]
        assert all(r["status"] == "ok" and "diff" in r["summary"] for r in rs)
        assert p.stats()["failed"] == {} and [why.startswith("could not prepare f") for why in ended(p)] == [True]
    finally:
        p.close()


def test_an_activity_no_other_process_can_prepare_fails_and_says_so(tmp_path, caplog):
    seed = f"flaky {tmp_path / 'n'} " + " ".join(str(n) for n in range(2, 40))   # the first process only
    p = Pool(workers=2, engines=ENGINES).start()
    try:
        assert p.wait_ready(60)
        with caplog.at_level(logging.WARNING, logger="texstage.pool"):
            assert p.prepare("f", "test", seed).result(60) == []
            end = time.monotonic() + 30
            while "f" not in p.stats()["failed"] and time.monotonic() < end:
                time.sleep(0.05)
            assert "preparing it ended 3 processes" in p.stats()["failed"]["f"]
            r = check(p, "f", "ok x")
            assert r["status"] == "internal" and r["error"].startswith("not prepared: preparing it ended 3")
        assert any("activity f failed after it was prepared" in m for m in caplog.messages)
    finally:
        p.close()


# ------------------------------------------------------------------ the same data on every process (2026-11-10)
RANDOM = ("PRAGMA case_sensitive_like = ON; CREATE TABLE t (r INTEGER, b BLOB, at REAL, name TEXT);"
          " WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n LIMIT 50) INSERT INTO t SELECT"
          " random(), randomblob(8), julianday('now'), CASE i % 2 WHEN 0 THEN 'apple' ELSE 'Apple' END FROM n;")


def end_each_worker(p: Pool) -> None:
    """Each worker ended in turn: the spare takes its place, and a fresh spare prepares what is prepared."""
    for pid in sorted(pids(p)[0]):
        psutil.Process(pid).kill()
        end = time.monotonic() + 30
        while pid in pids(p)[0] and time.monotonic() < end:
            time.sleep(0.05)
        assert p.wait_ready(60)


def across(p: Pool, act: str, text: str, n: int = 20) -> list[dict]:
    """The text, told apart by a number at its end, from n students at once: on every worker."""
    rs = [f.result(30) for f in [p.submit(act, f"{text} {i}", owner=f"s{i}") for i in range(n)]]
    assert len({r["worker"] for r in rs}) == len(pids(p)[0])
    return rs


def test_every_process_checks_on_the_data_of_the_first_ones_run():
    """A seed that draws at random as it loads - SQL's random() - runs on the first process alone; every
    other, the spare and those started later among them, loads what that run left (2026-11-10: each
    process ran the seed, and one query had as many results as there were processes)."""
    p = Pool(workers=2, engines=ENGINES).start()
    try:
        assert p.wait_ready(60)
        token = p.prepare("t", "test", "token seed", ["ok the reference"]).result(60)[0]["summary"]["token"]
        assert p.wait_ready(60)
        assert {r["summary"]["token"] for r in across(p, "t", "ok text")} == {token}
        end_each_worker(p)
        assert {r["summary"]["token"] for r in across(p, "t", "ok text")} == {token}
    finally:
        p.close()


def test_the_process_that_goes_on_with_the_references_has_the_first_ones_data():
    """The first process ends at a reference: the next goes on with the ones after it on the data the
    first one's run left - not on a run of its own."""
    p = Pool(workers=2, engines=ENGINES).start()
    try:
        assert p.wait_ready(60)
        outcomes = p.prepare("t", "test", "token seed", ["ok one", "crash", "ok three"]).result(60)
        assert [o["status"] for o in outcomes] == ["ok", "internal", "ok"]
        assert outcomes[0]["summary"]["token"] == outcomes[2]["summary"]["token"]
    finally:
        p.close()


def test_an_sql_seed_with_random_and_the_time_gives_every_process_the_same_data():
    """random(), randomblob() and julianday('now') in the seed: one query, one key - the reference's - on
    every process, those started later too; and the seed's PRAGMA, which holds for its connection, not its
    database: LIKE takes the case into account on every process (E8 of the second review)."""
    p = Pool(workers=2, engines=ENGINES).start()
    try:
        assert p.wait_ready(60)
        reference = p.prepare("r", "sql", RANDOM, ["SELECT * FROM t"]).result(60)[0]
        assert p.wait_ready(60)
        for i in range(2):
            if i:
                end_each_worker(p)
            rs = across(p, "r", f"SELECT * FROM t -- round {i}, student")
            assert {r["key"] for r in rs} == {reference["key"]}
            assert {tuple(r["summary"]["diff"].items()) for r in rs} == {(("common", 50), ("missing", 0), ("extra", 0))}
            like = across(p, "r", f"SELECT count(*) FROM t WHERE name LIKE 'a%' -- round {i}, student")
            assert {str(r["summary"]["rows"]) for r in like} == {"[['25']]"}
        with p.lock:
            assert len(p.acts["r"]["image"]) > 0
    finally:
        p.close()


@pytest.mark.parametrize("what", ["temp", "size"])
def test_a_seed_that_makes_more_than_its_database_or_a_larger_one_runs_on_every_process(what):
    """No copy where it would lack what the seed made - a TEMP table here -, or past the size a copy may
    have: every process runs the seed itself, as before."""
    seed, text, kw = {
        "temp": ("CREATE TEMP TABLE w (x); INSERT INTO w VALUES (1), (2);", "SELECT count(*) FROM w --", {}),
        "size": (SQL_SEED, REFERENCE + " --", {"image_max_mb": 0.001})}[what]
    p = Pool(workers=2, engines=ENGINES, **kw).start()
    try:
        p.prepare("s", "sql", seed).result(60)
        assert p.wait_ready(60)
        rs = across(p, "s", text)
        assert {r["status"] for r in rs} == {"ok"} and len({r["key"] for r in rs}) == 1
        with p.lock:
            assert p.acts["s"]["image"] is None
    finally:
        p.close()


def test_a_dropped_activity_is_not_checked(pool):
    pool.prepare("gone", "test", "a seed").result(60)
    pool.drop("gone")
    assert check(pool, "gone", "ok x") == {"status": "internal", "error": "not prepared", "tries": 0}


def test_dropping_an_activity_ends_its_checks_and_holds_up_no_student():
    p = Pool(workers=1, engines=ENGINES).start()
    try:
        p.prepare("d", "test", "a seed").result(60)
        p.prepare("e", "test", "another seed").result(60)
        assert p.wait_ready(60)
        running = p.submit("d", "sleep 30", owner="s1", budget_s=FAST)      # the clock ends its worker
        time.sleep(0.2)
        waiting = p.submit("d", "ok waits", owner="s2")
        later = p.submit("e", "ok later", owner="s1")
        p.drop("d")
        assert waiting.result(1)["error"] == "dropped"                       # at once
        assert running.result(10)["error"] == "dropped"                      # its worker ended: not again
        assert later.result(10)["status"] == "ok"                            # the student goes on
        assert p.stats()["queued"] == 0
    finally:
        p.close()


# ------------------------------------------------------------------ budgets and the clock
def test_a_budget_is_a_number_of_seconds(pool):
    for budget in (None, 0, -1, 11, True, "2"):
        with pytest.raises(ValueError):
            pool.submit("test", "ok x", budget_s=budget)


def test_sql_stops_itself_at_its_budget_and_its_worker_goes_on(pool):
    before, n = pids(pool), len(ended(pool))
    r = check(pool, "sql", RUNAWAY, budget_s=FAST)
    assert r["status"] == "timeout" and FAST <= r["cpu_s"] < FAST + 0.15
    for text in ["SELECT zeroblob(40000000)", "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r "
                 "LIMIT 99999) SELECT zeroblob(300) FROM r"]:               # Python's work after SQLite's counts
        r = check(pool, "sql", text, budget_s=FAST)
        assert r["status"] == "timeout" and r["cpu_s"] < FAST + 0.25, text
    assert pids(pool) == before and len(ended(pool)) == n


def test_what_its_engine_cannot_stop_ends_its_worker_a_timeout_and_the_spare_takes_its_place(pool):
    workers, spares = pids(pool)
    n = len(ended(pool))
    r = check(pool, "test", "spin 30", budget_s=FAST)
    assert (r["status"], r["tries"]) == ("timeout", 1) and r["check_s"] < 3
    assert ended(pool, n) == ["cpu"]
    now, _ = pids(pool)
    assert r["worker"] in workers and r["worker"] not in now and len(spares) == 1 and spares <= now


def test_the_watchdog_goes_on_when_a_process_does_not_read(pool):
    class Unreadable:
        def cpu_times(self):
            raise ValueError("no")

        def memory_info(self):
            raise ValueError("no")

    spare = pool.spares[0]
    ps, spare.ps = spare.ps, Unreadable()
    try:
        assert check(pool, "test", "spin 30 #unread", budget_s=FAST)["status"] == "timeout"
    finally:
        spare.ps = ps


def test_a_check_whose_worker_dies_runs_once_more_on_another_process_then_is_internal_and_set_aside(pool):
    n = len(ended(pool))
    r = check(pool, "test", "crash")
    assert (r["status"], r["tries"]) == ("internal", 2) and len(set(r["workers"])) == 2
    assert [why.startswith("died") for why in ended(pool, n)] == [True, True]
    again = check(pool, "test", "crash")
    assert (again["status"], again["tries"]) == ("internal", 0)              # no third worker dies for it
    assert len(ended(pool)) == n + 2
    assert r["set_aside"] is True and again["set_aside"] is True             # the server keeps it so


def stop_from_outside(pid: int) -> None:
    """A worker ended as Ctrl+Break ends it on Windows, or a stop of the whole process group elsewhere
    (systemd's SIGTERM): the exit code says so (pool.STOPPED)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = k32.OpenProcess(0x0001, False, pid)                         # PROCESS_TERMINATE
        assert handle, ctypes.get_last_error()
        k32.TerminateProcess(handle, 0xC000013A)                             # STATUS_CONTROL_C_EXIT
        k32.CloseHandle(handle)
    else:
        os.kill(pid, 15)                                                    # SIGTERM


def checking(p: Pool, text: str, other_than: int | None = None, timeout: float = 30) -> int:
    """The pid of the process that checks the text - another than other_than."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with p.lock:
            for w in p.workers + p.spares:
                if w.job is not None and w.job["text"] == text and w.pid != other_than:
                    return w.pid
        time.sleep(0.01)
    raise AssertionError(f"nobody checks {text!r}")


def test_a_check_whose_processes_are_stopped_from_outside_is_internal_and_not_set_aside(pool):
    """Ctrl+Break on Windows, a stop of the process group elsewhere, ends the workers without their text's
    doing (the package 4 review: the text came back internal and set aside, and stayed so): it runs once
    more, and stopped again it is internal - not set aside, so that sent again it is checked again."""
    text = "sleep 2 #stopped"
    fut = pool.submit("test", text)
    first = checking(pool, text)
    stop_from_outside(first)
    stop_from_outside(checking(pool, text, other_than=first))
    r = fut.result(60)
    assert (r["status"], r["tries"]) == ("internal", 2) and "set_aside" not in r
    assert pool.wait_ready(60)
    assert check(pool, "test", text)["status"] == "ok"                      # checked again, not set aside


def test_the_workers_leave_ctrl_c_and_ctrl_break_to_the_server(pool):
    """Ctrl+C - and on Windows Ctrl+Break - reach every process of the console: the server's to answer,
    which closes the pool (the package 4 review: Ctrl+Break ended the workers first). SIGTERM is not
    ignored: multiprocessing ends its daemons with it as the server's process exits."""
    ignored = check(pool, "test", "signals")["summary"]["ignored"]
    assert ignored == (["SIGINT", "SIGBREAK"] if sys.platform == "win32" else ["SIGINT"])


def test_a_check_whose_worker_dies_once_is_checked_on_a_fresh_process(pool, tmp_path):
    marker = tmp_path / "once"
    marker.write_text("")
    r = check(pool, "test", f"crashonce {marker}")
    assert (r["status"], r["tries"]) == ("ok", 2) and len(set(r["workers"])) == 2
    assert checks_made(pool, r["workers"][1]) == 1                          # the retry was its first


def test_a_retry_waits_for_the_fresh_process_that_replaces_its_worker(tmp_path):
    """Without a spare: the other worker has checked texts already, so the retry waits for the one that
    replaces the worker that died, though it still loads its seed (the second review: it took the other)."""
    marker = tmp_path / "once"
    marker.write_text("")
    p = Pool(workers=2, spare=False, engines=ENGINES).start()
    try:
        p.prepare("test", "test", "slow 0.5").result(60)
        assert p.wait_ready(60)
        warm = [p.submit("test", f"spin 0.3 #{i}", owner=f"w{i}") for i in range(4)]     # both workers
        assert all(f.result(30)["status"] == "ok" for f in warm)
        before, _ = pids(p)
        r = check(p, "test", f"crashonce {marker}")
        assert (r["status"], r["tries"]) == ("ok", 2)
        assert r["workers"][1] not in before and checks_made(p, r["workers"][1]) == 1
    finally:
        p.close()


def test_two_retries_at_once_each_get_a_fresh_process(tmp_path):
    """Two workers die at once: the spare takes one retry, the other waits for a fresh process too (the
    second review: it took the spare after its first retry)."""
    markers = [tmp_path / f"once{i}" for i in range(2)]
    p = Pool(workers=2, engines=ENGINES).start()
    try:
        p.prepare("test", "test", "slow 0.5").result(60)
        assert p.wait_ready(60)
        warm = [p.submit("test", f"spin 0.3 #{i}", owner=f"w{i}") for i in range(4)]
        assert all(f.result(30)["status"] == "ok" for f in warm)
        for m in markers:
            m.write_text("")
        futures = [p.submit("test", f"crashonce {m}", owner=f"c{i}") for i, m in enumerate(markers)]
        rs = [f.result(60) for f in futures]
        assert all((r["status"], r["tries"]) == ("ok", 2) for r in rs)
        retried = [r["workers"][1] for r in rs]
        assert len(set(retried)) == 2 and all(checks_made(p, pid) == 1 for pid in retried)
    finally:
        p.close()


def test_the_clock_stops_what_takes_no_cpu_time(pool):
    r = check(pool, "test", "sleep 30", budget_s=FAST)                     # the backstop: five times 0.2 s
    assert (r["status"], r["tries"], r["error"]) == ("internal", 2, "clock")


def test_loading_a_seed_past_its_backstop_ends_its_process():
    p = Pool(workers=1, spare=False, engines=ENGINES, prepare_backstop_s=0.5).start()
    try:
        with pytest.raises(ValueError, match="ended 2 processes"):
            p.prepare("slow", "test", "slow 30").result(30)
        assert ended(p) == ["prepare", "prepare"]
    finally:
        p.close()


def test_sparql_stops_between_solutions_and_else_its_worker_is_ended(pool):
    pytest.importorskip("pyoxigraph")
    pool.prepare("rdf", "sparql", RDF).result(60)
    assert pool.wait_ready(60)
    n = len(ended(pool))
    r = check(pool, "rdf", "SELECT * WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i }", budget_s=FAST)
    assert r["status"] == "timeout" and r["cpu_s"] is not None and len(ended(pool)) == n    # from inside
    r = check(pool, "rdf", "SELECT (COUNT(*) AS ?n) WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i . ?j ?k ?l }",
              budget_s=FAST)
    assert r["status"] == "timeout" and ended(pool, n) == ["cpu"]           # no solution streams: the watchdog
    pool.drop("rdf")


# ------------------------------------------------------------------ the processes, memory
def test_workers_run_at_a_low_priority(pool):
    workers, spares = pids(pool)
    for pid in workers | spares:
        nice = psutil.Process(pid).nice()
        if sys.platform == "win32":
            assert nice == psutil.BELOW_NORMAL_PRIORITY_CLASS
        else:
            assert nice >= min(19, os.nice(0) + 10)


def test_memory_over_the_allowance_twice_is_the_students_error():
    p = Pool(workers=1, engines=ENGINES, mem_allowance_mb=100).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        r = p.submit("test", "alloc 300", language="de").result(60)
        assert (r["status"], r["error"], r["tries"]) == ("error", texts.ENGINES["de"]["tooMuchMemory"], 2)
        assert ended(p) == ["memory", "memory"]
    finally:
        p.close()


def test_memory_over_the_allowance_once_is_fine_on_a_fresh_process(tmp_path):
    marker = tmp_path / "once"
    marker.write_text("")
    p = Pool(workers=1, engines=ENGINES, mem_allowance_mb=100).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        r = p.submit("test", f"alloconce {marker} 300").result(60)
        assert (r["status"], r["tries"]) == ("ok", 2) and ended(p) == ["memory"]
    finally:
        p.close()


CROSS = ("CREATE TABLE a (x INTEGER, y TEXT); WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r "
         "LIMIT 400) INSERT INTO a SELECT n, 'name ' || n FROM r;")


def test_sqlites_own_cap_is_the_students_error_at_once_and_its_worker_goes_on():
    """A join condition forgotten, the rows sorted: SQLite's cap stops the query from inside, alike on
    every process - so no worker is ended for it (the second review: two were, for each such text)."""
    p = Pool(workers=1, spare=False, engines=ENGINES, heap_allowance_mb=8).start()
    try:
        p.prepare("s", "sql", CROSS, [], "de").result(60)
        r = p.submit("s", "SELECT * FROM a AS p, a AS q, a AS r ORDER BY p.y, q.y, r.y", language="de").result(60)
        assert (r["status"], r["error"], r["tries"]) == ("error", texts.ENGINES["de"]["tooMuchMemory"], 1)
        again = p.submit("s", "SELECT count(*) FROM a", language="de").result(60)
        assert again["status"] == "ok" and again["worker"] == r["worker"] and ended(p) == []
    finally:
        p.close()


@pytest.mark.parametrize("order", [("big", "small"), ("small", "big")])
def test_sqlites_cap_holds_every_seed_of_a_process(order):
    """A 40 MB seed and a small one, in either order: the cap - SQLite's, for the whole process - counts
    both (the second review: each seed set it from its own pages, a smaller one below what a larger one
    held, and no text of either ran)."""
    seeds = {"big": ("CREATE TABLE t (x); INSERT INTO t VALUES (zeroblob(40000000));", "SELECT length(x) FROM t"),
             "small": ("CREATE TABLE u (y); INSERT INTO u VALUES (1);", "SELECT y FROM u")}
    p = Pool(workers=1, spare=False, engines=ENGINES, heap_allowance_mb=4).start()
    try:
        for act in order:
            assert p.prepare(act, "sql", seeds[act][0], [seeds[act][1]]).result(60)[0]["status"] == "ok", act
        assert check(p, "big", "SELECT length(x) FROM t")["summary"]["rows"] == [["40000000"]]
        assert check(p, "small", "SELECT y FROM u")["status"] == "ok" and ended(p) == []
    finally:
        p.close()


@pytest.mark.skipif(sys.platform != "win32", reason="the job object is Windows'")
def test_the_job_object_holds_a_worker_to_its_memory():
    """An allocation over the job object's limit fails in the worker: it ends, and the text runs once more
    on a fresh process - failing there too, it is the student's error."""
    p = Pool(workers=1, spare=False, engines=ENGINES, mem_allowance_mb=4096, hard_mb=400).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        r = p.submit("test", "alloc 600").result(60)
        assert (r["status"], r["error"], r["tries"]) == ("error", texts.ENGINES["en"]["tooMuchMemory"], 2)
        assert p.wait_ready(60) and ended(p) == ["memory", "memory"]          # the second ends after its answer
        assert p.submit("test", "ok x").result(60)["status"] == "ok"
    finally:
        p.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the address space is capped on Linux")
def test_a_workers_address_space_is_capped_on_linux():
    p = Pool(workers=1, spare=False, engines=ENGINES, hard_mb=3000).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        assert p.submit("test", "limits").result(60)["summary"]["address_space"] == 2 * 3000 * 2**20
    finally:
        p.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the address space is capped on Linux")
def test_a_lower_address_space_limit_is_kept_and_the_pool_starts():
    """The server under ulimit -v below twice the hard stop: a process may not raise its hard limit, so a
    worker keeps the lower one (the second review: each worker failed as it started, and the pool broke)."""
    import resource
    limit = 3 * 2**30
    script = f"""if True:
        import sys
        sys.path.insert(0, {str(Path(__file__).parent)!r})
        from texstage.server.pool import Pool
        p = Pool(workers=1, spare=False, engines={{"test": "pool_engines"}}).start()
        p.prepare("test", "test", "a seed").result(60)
        print(p.submit("test", "limits").result(60)["summary"]["address_space"])
        p.close()"""
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120,
                          preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_AS, (limit, limit)))
    assert done.stdout.strip() == str(limit), done.stdout + done.stderr


# ------------------------------------------------------------------ the queue
def test_students_take_turns():
    """One student's many slow texts hold another's up by one round, not by all of them."""
    p = Pool(workers=1, spare=False, engines=ENGINES).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        assert p.wait_ready(60)
        order = []
        greedy = [p.submit("test", f"spin 0.15 #{i}", owner="greedy") for i in range(6)]
        other = p.submit("test", "ok other", owner="other")
        for i, f in enumerate(greedy):
            f.add_done_callback(lambda _, i=i: order.append(f"greedy {i}"))
        other.add_done_callback(lambda _: order.append("other"))
        for f in [*greedy, other]:
            f.result(60)
        assert order.index("other") == 2, order                             # behind the one running and one more
    finally:
        p.close()


def test_a_text_no_process_can_take_yet_holds_up_none_of_its_owners_others():
    """A student's text for an activity whose reference is still being checked waits; their next text, for
    another activity, goes at once to the worker that is free (a fix of the first review that no test held,
    the second found)."""
    p = Pool(workers=2, spare=False, engines=ENGINES).start()
    try:
        p.prepare("b", "test", "seed b").result(60)
        assert p.wait_ready(60)
        slow = p.prepare("a", "test", "seed a", ["sleep 3 the reference"])      # one worker, for 3 s
        time.sleep(0.2)
        t = time.perf_counter()
        first = p.submit("a", "ok for a", owner="s1")
        second = p.submit("b", "ok for b", owner="s1")
        assert second.result(30)["status"] == "ok" and time.perf_counter() - t < 1.5
        assert slow.result(30)[0]["status"] == "ok" and first.result(30)["status"] == "ok"
    finally:
        p.close()


def test_with_no_worker_free_the_queue_is_not_walked(monkeypatch):
    """The spare waits while the worker checks: a submit - and a message - looks for a retry only (the
    second review: each walked the whole queue, and 1,000 texts took 1.0 s to their last verdict, not
    0.12 s)."""
    p = Pool(workers=1, engines=ENGINES).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        assert p.wait_ready(60)
        walks = []
        walk = Pool._next
        monkeypatch.setattr(Pool, "_next", lambda self, *a: walks.append(1) or walk(self, *a))
        busy = p.submit("test", "sleep 1", owner="busy", budget_s=1.0)
        time.sleep(0.2)
        n = len(walks)
        futures = [p.submit("test", f"ok {i}", owner=f"s{i}") for i in range(200)]
        assert len(walks) == n
        assert busy.result(30)["status"] == "ok" and all(f.result(30)["status"] == "ok" for f in futures)
    finally:
        p.close()


def test_a_retry_without_a_spare_does_not_wait_for_ever(tmp_path):
    marker = tmp_path / "once"
    marker.write_text("")
    p = Pool(workers=2, spare=False, engines=ENGINES).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        assert p.wait_ready(60)
        others = [p.submit("test", f"spin 0.01 #{i}", owner=f"s{i}") for i in range(40)]
        once = p.submit("test", f"crashonce {marker}", owner="me")
        assert all(f.result(30)["status"] == "ok" for f in others)
        assert (once.result(30)["status"], once.result()["tries"]) == ("ok", 2)
    finally:
        p.close()


def test_a_large_seed_goes_to_a_busy_worker_and_the_lock_stays_free():
    """8 MB to every process - one of them busy, whose pipe takes it only once its check is done -, while
    four processes die: neither a submit nor anyone else waits for the pool's lock."""
    p = Pool(workers=2, engines=ENGINES).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        assert p.wait_ready(60)
        waits, stop = [], threading.Event()

        def probe():
            while not stop.is_set():
                t = time.perf_counter()
                with p.lock:
                    pass
                waits.append(time.perf_counter() - t)
                time.sleep(0.001)

        busy = p.submit("test", "sleep 1.5", owner="busy", budget_s=1.0)
        time.sleep(0.2)
        threading.Thread(target=probe, daemon=True).start()
        crashes = [p.submit("test", f"crash {i}", owner=f"c{i}") for i in range(2)]
        big = p.prepare("big", "test", "x" * (8 * 2**20))
        calls = []
        for i in range(50):
            t = time.perf_counter()
            p.submit("test", f"ok {i}", owner=f"s{i}")
            calls.append(time.perf_counter() - t)
            time.sleep(0.01)
        big.result(60)
        assert busy.result(30)["status"] == "ok"
        assert [c.result(60)["status"] for c in crashes] == ["internal", "internal"]
        assert p.wait_ready(60)
        stop.set()
        assert check(p, "big", "ok big")["status"] == "ok"
        assert max(calls) < 0.1 and max(waits) < 0.1, (max(calls), max(waits))
    finally:
        p.close()


def test_replies_at_once_resolve_every_future_once(thread_errors):
    """Many activities prepared at once, the threads switching all the time: every future resolves, no
    thread of the pool fails."""
    interval = sys.getswitchinterval()
    p = Pool(workers=3, engines=ENGINES).start()
    try:
        assert p.wait_ready(60)
        sys.setswitchinterval(1e-5)
        futures = [p.prepare(f"a{i}", "test", f"seed {i}", ["ok one", "ok two"]) for i in range(20)]
        assert all(len(f.result(60)) == 2 for f in futures)
        assert p.wait_ready(60) and thread_errors == []
    finally:
        sys.setswitchinterval(interval)
        p.close()


# ------------------------------------------------------------------ closing, breaking
def test_close_resolves_what_waits_at_once_and_ends_busy_workers():
    p = Pool(workers=1, spare=False, engines=ENGINES).start()
    p.prepare("test", "test", "a seed").result(60)
    assert p.wait_ready(60)
    running = p.submit("test", "sleep 5", budget_s=2.0)
    waiting = p.submit("test", "ok waits")
    time.sleep(0.2)
    t = time.perf_counter()
    p.close()
    assert time.perf_counter() - t < 1.5
    assert running.result(0)["error"] == waiting.result(0)["error"] == "closed"


def test_closing_while_a_replacement_starts_ends_it(monkeypatch):
    """close() while the replacement of a worker that died is being started: it waits for the start and
    ends the process (the second review: it was left running, outside the job object)."""
    p = Pool(workers=1, spare=False, engines=ENGINES).start()
    try:
        assert p.wait_ready(60)
        starting, go, new = threading.Event(), threading.Event(), []
        start = pool_module._Worker.start

        def held(self):
            new.append(self)
            starting.set()
            go.wait(10)
            start(self)

        monkeypatch.setattr(pool_module._Worker, "start", held)
        psutil.Process(p.workers[0].pid).kill()                           # its replacement is started
        assert starting.wait(10)
        closing = threading.Thread(target=p.close)
        closing.start()
        while not p.closed:
            time.sleep(0.01)
        go.set()                                                            # it starts with the pool closed
        closing.join(15)
        assert not closing.is_alive() and new[0].pid is not None
        new[0].proc.join(5)
        assert not new[0].proc.is_alive()
    finally:
        p.close()


def test_a_pool_whose_processes_die_before_they_are_ready_starts_no_more():
    p = Pool(workers=2, engines=ENGINES)
    p.options["imports"] = [*p.options["imports"], "pool_dies_on_import"]
    p.start()
    try:
        t = time.monotonic()
        while not p.broken and time.monotonic() - t < 30:
            time.sleep(0.05)
        assert p.broken
        time.sleep(0.5)
        n = len(ended(p))
        time.sleep(1.0)
        assert len(ended(p)) == n                                           # none started any more
        with pytest.raises(RuntimeError):
            p.prepare("x", "test", "a seed").result(1)
        assert p.submit("x", "ok x").result(1)["status"] == "internal"
    finally:
        p.close()


def test_a_process_that_cannot_be_started_breaks_the_pool_and_no_thread_fails(monkeypatch, thread_errors):
    p = Pool(workers=1, spare=False, engines=ENGINES).start()
    try:
        p.prepare("test", "test", "a seed").result(60)
        assert p.wait_ready(60)

        def cannot(self):
            raise OSError(1455, "The paging file is too small for this operation to complete")

        monkeypatch.setattr(pool_module._Worker, "start", cannot)
        r = check(p, "test", "crash")                                      # its replacement cannot start
        assert r["status"] == "internal" and p.broken
        assert p.stats()["workers"] == 0 and check(p, "test", "ok x")["status"] == "internal"
        assert thread_errors == []
    finally:
        p.close()


def test_futures_of_what_is_replaced_dropped_or_closed_do_not_hang():
    p = Pool(workers=1, spare=False, engines=ENGINES).start()
    try:
        prepared = p.prepare("t", "test", "slow 0.5")
        p.drop("t")
        assert prepared.cancelled()
        prepared = p.prepare("t", "test", "slow 0.5")
    finally:
        p.close()
    with pytest.raises((RuntimeError, cf.CancelledError)):
        prepared.result(1)
