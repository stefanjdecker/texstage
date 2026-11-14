# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A worker process of the pool (pool.py; docs/architecture/activity-framework-plan.md, F1, 4.4): it
prepares activities and checks their texts with texstage.checks, one at a time, on a thread with a
64 MB stack - pyoxigraph's parsers recurse, and 800 nested groups end a process with the default one
(F0, Q3). It starts at a low priority, Ctrl+C - and on Windows Ctrl+Break - is the server's, not its own
(the package 4 review: Ctrl+Break ended every worker before the server closed the pool, and the texts
being checked came back internal); on Linux its address space
is capped, the system's hard stop (on Windows the pool's job object is), and on Linux and macOS it ends
once the server's process is gone (on Windows the job object ends it).

What the pool sends and what the worker answers, through its pipe - in order, one at a time:

    ("prepare", act, gen, module, seed, references, rows, language, budget, options, image)
      [+ the bytes of a database, when image is "follows"]
        -> ("loading", act, gen)                      it loads the seed
           ("image", act, gen) + the bytes            the database the seed left, for the others
           ("reference", act, gen, i, reported)       it checks reference i
           ("referenced", act, gen, i, outcome, rows) - its outcome, and whether its rows are kept
           ("prepared", act, gen, error, seconds, here)   error: None, or why it is not prepared - the
                                                      seed does not load, or (here) the rows are not
                                                      found on this process
    ("check", job, act, text, budget, language)  -> ("done", job, outcome, cpu_s)
    ("normalize", job, kind, item, keys, language, input)  -> ("normalized", job, answer)   (normalizer.py)
    ("drop", act)
    ("exit",)

module: an engine's (texstage.checks.sql) - or "kind:<name>", a kind of the contract (_OfKind): then the
seed is {item, keys, files}, a text to check the normalized input as JSON, and an outcome what the kind's
check says (activities/kind.py: Check.sent), held against the contract's rules.
image: None, the seed is run; a number, to the first process: the seed is run, and the database it left -
at most that many bytes, where the engine makes one (checks/sql.py: image) - goes back, and this process
checks on a copy of it too, as every other will; "follows": such a database, in the seed's place. A
database goes as bytes of its own (send_bytes), not pickled: a copy less on either side.
references: [i, text] to check and report; rows: [i, text], the reference whose rows the diffs count
against when another process found it - checked first, not reported; when it gives no rows here, the
activity is not prepared here, since this process could not compare alike. An outcome is what the presenter
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
KIND = "kind:"                          # a module's name that is none: a kind of the contract (_OfKind)


def main(conn, options: dict) -> None:
    """The worker process's entry (multiprocessing, spawn): its limits, then the thread that checks."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if hasattr(signal, "SIGBREAK"):                     # Windows: the pool ends a worker with TerminateProcess
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)  # (kill), which no handler stops. Not SIGTERM elsewhere:
    if sys.platform == "win32":                         # multiprocessing ends its daemons with it at exit
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
        import resource                                  # the soft limit only, never above what it was: a
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)      # process may not raise its hard limit
        cap = min(x for x in (options["address_space"], soft, hard) if x != resource.RLIM_INFINITY)
        resource.setrlimit(resource.RLIMIT_AS, (cap, hard))
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


class _OfKind:
    """A kind of the contract where an engine's module is (F2's plan, 4.3; texstage/activities/kind.py): an
    activity whose module is named "kind:<name>". Its seed is {item, keys, files} - the public item, the
    keys, the bundle's files by the names the item gives them -, a text to check the normalized input as
    JSON, a reference its text. What goes back of a check is what the kind's check says (Check.sent), held
    against the contract's rules first: one that breaks them is internal, never the student's - as is
    whatever a kind's check raises."""

    def __init__(self, name: str):
        from texstage.activities import registry
        self.kind = registry.kind(name)
        self.item: dict = {}
        self.keys: dict = {}

    def load(self, seed: dict, image: bytes | None = None, **limits):
        self.item, self.keys = seed["item"], seed["keys"]
        return self.kind.prepare(self.item, self.keys, seed["files"], limits or None, copy=image)

    def image(self, prepared, most: int) -> bytes | None:
        return self.kind.copy(prepared, most)

    def check(self, prepared, rows: list | None, text: str, language: str | None, budget_s: float,
              reference: bool = False) -> tuple[dict, list | None]:
        """The outcome, and a result's rows - which stay in the worker. rows: the reference's, which a
        result is compared with; a reference itself is compared with none."""
        import json

        from texstage.activities.kind import Check, Entry, Prepared, Step, validated
        step = Step(self.item, self.keys, language, budget_s)
        try:
            entry = self.kind.reference(step, text) if reference else Entry.of(json.loads(text))
            check = validated(self.kind, self.kind.check(Prepared(prepared.state, rows), step, entry), step)
        except MemoryError:
            return {"status": "error", "memory": True}, None
        except Exception:  # noqa: BLE001 - a kind's check raises for nothing a student can send: the core's
            check = Check("internal")
        out = check.sent()
        if check.memory:
            out["memory"] = True
        return out, check.rows if check.status == "ok" else None


def _normalize(name: str, item: dict, keys: dict, language: str | None, input: dict) -> dict:
    """A kind's normalize for an input as it was sent (F2's plan, 4.3): {"input": the normalized input} -
    entries that normalize alike are checked once -, {"refused": the phone's code} where the kind does
    not take it (Unfit), {"error": why} where it could not be asked: never the student's."""
    from texstage.activities import registry
    from texstage.activities.kind import Entry, Step, Unfit, kept
    try:
        kind = registry.kind(name)
        out = kind.normalize(Step(item, keys, language), Entry.of(input))
        try:
            return {"input": kept(kind, out)}                # (one field, the kind's input's - no NaN for a window)
        except ValueError as e:
            return {"error": f"{name}: normalize gave {e}"[:300]}
    except Unfit as e:
        return {"refused": e.code}
    except Exception as e:  # noqa: BLE001 - whatever a kind's normalize raises: not the student's
        return {"error": f"{type(e).__name__}: {e}"[:300]}


def _prepare(conn, states: dict, msg: tuple) -> None:
    _, act, gen, name, seed, references, rows_ref, language, budget_s, options, image = msg
    data = conn.recv_bytes() if image == "follows" else None
    conn.send(("loading", act, gen))
    t = time.perf_counter()
    try:
        module = _OfKind(name[len(KIND):]) if name.startswith(KIND) else importlib.import_module(name)
        state = module.load(seed, **options) if data is None else module.load(seed, image=data, **options)
        data = None                                      # let go of before "prepared": the watchdog counts from it
        if isinstance(image, int) and hasattr(module, "image") and (data := module.image(state, image)):
            state = None                                 # the seed's own run goes first: one database at a time
            try:
                state = module.load(seed, image=data, **options)
            except Exception:  # noqa: BLE001 - the copy does not load: every process runs the seed
                data, state = None, module.load(seed, **options)
            if data is not None:
                conn.send(("image", act, gen))
                conn.send_bytes(data)
                data = None
    except Exception as e:  # noqa: BLE001 - a seed that does not load fails its activity
        states.pop(act, None)
        why = "the seed: out of memory" if isinstance(e, MemoryError) else str(e).split("\n")[0] or type(e).__name__
        conn.send(("prepared", act, gen, why, time.perf_counter() - t, False))
        return
    rows, of_kind = None, isinstance(module, _OfKind)
    if rows_ref is not None:                             # the reference another process found the rows in
        conn.send(("reference", act, gen, rows_ref[0], False))
        if of_kind:
            outcome, rows = module.check(state, None, rows_ref[1], language, budget_s, reference=True)
            status = outcome["status"]
        else:
            result, _ = _evaluate(module, state, rows_ref[1], language, budget_s)
            status, rows = result["status"], result.get("rows")
        if status != "ok":                               # not here: its diffs would differ from the others'
            states.pop(act, None)
            why = f"its reference {rows_ref[0] + 1} gives no rows here ({status})"
            conn.send(("prepared", act, gen, why, time.perf_counter() - t, True))
            return
    for i, text in references:                           # in their order; the first that gives a result is
        conn.send(("reference", act, gen, i, True))      # the one to compare with, unless one before it was
        if of_kind:
            outcome, found = module.check(state, None, text, language, budget_s, reference=True)
        else:
            result, end = _evaluate(module, state, text, language, budget_s)
            outcome, found = _outcome(result, None, end), result.get("rows")
        first = rows is None and outcome["status"] == "ok"
        conn.send(("referenced", act, gen, i, outcome, first))
        if first:
            rows = found
    states[act] = (module, state, rows)
    conn.send(("prepared", act, gen, None, time.perf_counter() - t, False))


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
            if isinstance(module, _OfKind):
                outcome, _ = module.check(state, rows, text, language, budget_s)
            else:
                result, end = _evaluate(module, state, text, language, budget_s)
                outcome = _outcome(result, rows, end)
            conn.send(("done", job, outcome, time.thread_time() - cpu))
        elif kind == "normalize":
            conn.send(("normalized", msg[1], _normalize(*msg[2:])))
        elif kind == "drop":
            states.pop(msg[1], None)
