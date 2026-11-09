# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A worker process of the pool (pool.py; docs/architecture/activity-framework-plan.md, F1, 4.4): it
prepares activities and checks their texts with texstage.checks, one at a time, on a thread with a
64 MB stack - pyoxigraph's parsers recurse, and 800 nested groups end a process with the default one
(F0, Q3). It starts at a low priority, Ctrl+C is the server's, not its own; on Linux its address space
is capped, the system's hard stop (on Windows the pool's job object is), and on Linux and macOS it ends
once the server's process is gone (on Windows the job object ends it).

What the pool sends and what the worker answers, through its pipe - in order, one at a time:

    ("prepare", act, gen, module, seed, references, rows, language, budget, options)
        -> ("loading", act, gen)                      it loads the seed
           ("reference", act, gen, i, reported)       it checks reference i
           ("referenced", act, gen, i, outcome, rows) - its outcome, and whether its rows are kept
           ("prepared", act, gen, error, seconds)     error: None, or why the seed did not load
    ("check", job, act, text, budget, language)  -> ("done", job, outcome, cpu_s)
    ("drop", act)
    ("exit",)

references: [i, text] to check and report; rows: [i, text], the reference whose rows the diffs count
against when another process found it - checked first, not reported. An outcome is what the presenter
window's evaluator sent the server (web/stage/evaluator-worker.js): the status, the error, and for a
result its key and summary - after the reference with the rows, the summary says how its rows compare
(diff). The rows stay in the worker. A text's budget is its CPU time, the key's computing included; an
outcome marked memory ran out of memory here, which the pool tries once more on a fresh process.
"""
from __future__ import annotations

import importlib
import os
import signal
import sys
import threading
import time

STACK = 64 * 2**20


def main(conn, options: dict) -> None:
    """The worker process's entry (multiprocessing, spawn): its limits, then the thread that checks."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.SetErrorMode(0x0001 | 0x0002)               # no dialog when it fails: it ends, and the pool sees it
        k32.SetPriorityClass(k32.GetCurrentProcess(), 0x4000)     # BELOW_NORMAL_PRIORITY_CLASS
    else:
        try:
            os.nice(10)
        except OSError:
            pass
        threading.Thread(target=_orphaned, args=(os.getppid(),), daemon=True, name="texstage-orphaned").start()
    if options.get("address_space") and sys.platform.startswith("linux"):
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (options["address_space"], options["address_space"]))
    for name in options.get("imports", ()):              # imported before "ready": ready means ready
        try:
            importlib.import_module(name)
        except ImportError:
            pass
    threading.stack_size(STACK)
    t = threading.Thread(target=_serve, args=(conn,), name="texstage-checks")
    t.start()
    t.join()


def _orphaned(parent: int) -> None:
    """Ends the worker once the server's process is gone - it is then another's child (Linux, macOS)."""
    while True:
        time.sleep(1.0)
        if os.getppid() != parent:
            os._exit(0)


def _evaluate(module, state, text: str, language: str | None, budget_s: float) -> tuple[dict, float]:
    """A text checked as the browser's evaluator checked it - an engine's failure is the text's error -,
    and when its budget ends."""
    from texstage.checks.common import well_formed
    end = time.thread_time() + budget_s
    try:
        return module.evaluate(state, well_formed(text), language, budget_s=budget_s), end
    except MemoryError:
        return {"status": "error", "error": "out of memory", "memory": True}, end
    except Exception as e:  # noqa: BLE001 - whatever the engine raises is this text's error, not the worker's
        return {"status": "error", "error": str(e).split("\n")[0] or type(e).__name__}, end


def _outcome(result: dict, reference_rows: list | None, end: float) -> dict:
    """What goes back of a check's result: status, error, and for a result its key and summary - a timeout
    when the key takes the text past its budget."""
    from texstage.checks.common import compare, key
    out = {"status": result["status"]}
    if result.get("error"):
        out["error"] = result["error"]
    if result.get("memory"):
        out["memory"] = True
    if result["status"] == "ok":
        k = key(result["canonical"], end)
        if k is None:
            return {"status": "timeout"}
        out["key"] = k
        out["summary"] = result["summary"]
        if reference_rows is not None:
            out["summary"]["diff"] = compare(result["rows"], reference_rows)
    return out


def _prepare(conn, states: dict, msg: tuple) -> None:
    _, act, gen, name, seed, references, rows_ref, language, budget_s, options = msg
    conn.send(("loading", act, gen))
    t = time.perf_counter()
    try:
        module = importlib.import_module(name)
        state = module.load(seed, **options)
    except Exception as e:  # noqa: BLE001 - a seed that does not load fails its activity
        states.pop(act, None)
        why = "the seed: out of memory" if isinstance(e, MemoryError) else str(e).split("\n")[0] or type(e).__name__
        conn.send(("prepared", act, gen, why, time.perf_counter() - t))
        return
    rows = None
    if rows_ref is not None:                             # the reference another process found the rows in
        conn.send(("reference", act, gen, rows_ref[0], False))
        result, _ = _evaluate(module, state, rows_ref[1], language, budget_s)
        if result["status"] == "ok":
            rows = result["rows"]
    for i, text in references:                           # in their order; the first that gives a result is
        conn.send(("reference", act, gen, i, True))      # the one to compare with, unless one before it was
        result, end = _evaluate(module, state, text, language, budget_s)
        outcome = _outcome(result, None, end)
        first = rows is None and outcome["status"] == "ok"
        conn.send(("referenced", act, gen, i, outcome, first))
        if first:
            rows = result["rows"]
    states[act] = (module, state, rows)
    conn.send(("prepared", act, gen, None, time.perf_counter() - t))


def _serve(conn) -> None:
    states: dict[str, tuple] = {}                        # act -> (module, state, the rows diffs count against)
    conn.send(("ready", os.getpid()))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return
        kind = msg[0]
        if kind == "exit":
            return
        if kind == "prepare":
            _prepare(conn, states, msg)
        elif kind == "check":
            _, job, act, text, budget_s, language = msg
            if act not in states:
                conn.send(("done", job, {"status": "internal", "error": "not prepared"}, 0.0))
                continue
            module, state, rows = states[act]
            cpu = time.thread_time()
            result, end = _evaluate(module, state, text, language, budget_s)
            conn.send(("done", job, _outcome(result, rows, end), time.thread_time() - cpu))
        elif kind == "drop":
            states.pop(msg[1], None)
