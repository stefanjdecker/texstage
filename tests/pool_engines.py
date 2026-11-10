# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""An engine for the pool's tests (tests/test_pool.py), which a worker loads as it loads texstage.checks'
- load(seed, **options), evaluate(state, text, language, budget_s) -: a text does what it says.

    ok x              a result (its summary names the seed)
    spin s            s seconds of CPU time, which the engine does not stop: the watchdog's
    sleep s           s seconds of the clock, without CPU time: the backstop's
    crash             the worker ends
    crashonce path    the worker ends if the file is there - and takes it away: the next try is a result
    alloc mb          mb of memory, held a second while the watchdog looks - or a MemoryError, in a job object
    alloconce path mb the same if the file is there, which it takes away
    raise             the engine fails: the text's error
    limits            the worker's address space (Linux)
    signals           the signals the worker ignores (SIGINT, SIGBREAK, SIGTERM)
    flaky dir n...    the engine fails the n-th time the text is checked, counted over every process

A seed "fail ..." does not load, "crash" ends the worker that loads it, "slow s" takes s seconds, and
"flaky dir n..." does not load the n-th time, counted alike. A seed "token ..." draws a random token as
it loads - a seed with random() in SQL -, which its image() copies to the pool's other processes, and
which a result's key and summary carry.
"""
from __future__ import annotations

import os
import time

HELD: list = []


def _count(folder: str) -> int:
    """How many times so far, in any process: each takes the next number's file in folder, which only
    one can create."""
    os.makedirs(folder, exist_ok=True)
    n = 1
    while True:
        try:
            os.close(os.open(os.path.join(folder, str(n)), os.O_CREAT | os.O_EXCL))
            return n
        except FileExistsError:
            n += 1


def _flaky(rest: list[str]) -> bool:
    return _count(rest[0]) in {int(n) for n in rest[1:]}


def load(seed: str, image: bytes | None = None, **options) -> dict:
    if seed.startswith("fail"):
        raise ValueError("the seed: it says fail")
    if seed.startswith("crash"):
        os._exit(3)
    if seed.startswith("slow "):
        time.sleep(float(seed.split()[1]))
    if seed.startswith("flaky ") and _flaky(seed.split()[1:]):
        raise ValueError("the seed: not on this process")
    if seed.startswith("token"):
        return {"seed": seed, "token": image.decode() if image is not None else os.urandom(8).hex()}
    return {"seed": seed}


def image(state: dict, most: int) -> bytes | None:
    """The token, for the pool's other processes - what a copy of its database is to an SQL seed."""
    return state["token"].encode() if "token" in state else None


def _once(path: str) -> bool:
    """Whether the file is there - taken away, so that the next try finds it gone."""
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


def _alloc(mb: int) -> None:
    HELD.append([b"x" * 2**20 for _ in range(mb)])
    time.sleep(1.0)
    HELD.clear()


def evaluate(state: dict, text: str, language: str | None = None, budget_s: float | None = None) -> dict:
    what, *rest = text.split()                           # "spin 0.1 #3": what follows the number tells texts apart
    arg = rest[0] if rest else ""
    if what == "spin":
        end = time.thread_time() + float(arg)
        while time.thread_time() < end:
            pass
    elif what == "sleep":
        time.sleep(float(arg))
    elif what == "crash":
        os._exit(3)
    elif what == "crashonce" and _once(arg):
        os._exit(3)
    elif what == "alloc":
        _alloc(int(arg))
    elif what == "alloconce" and _once(arg):
        _alloc(int(rest[1]))
    elif what == "raise":
        raise RuntimeError("the engine broke")
    elif what == "flaky" and _flaky(rest):
        raise RuntimeError("not on this process")
    elif what == "limits":                               # the worker's address space, on Linux
        import resource
        return {"status": "ok", "canonical": "limits", "rows": [], "summary": {
            "kind": "test", "address_space": resource.getrlimit(resource.RLIMIT_AS)[0]}}
    elif what == "signals":                              # those the worker leaves to the server
        import signal
        names = [n for n in ("SIGINT", "SIGBREAK", "SIGTERM") if hasattr(signal, n)]
        return {"status": "ok", "canonical": "signals", "rows": [], "summary": {
            "kind": "test", "ignored": [n for n in names if signal.getsignal(getattr(signal, n)) == signal.SIG_IGN]}}
    token = {"token": state["token"]} if "token" in state else {}
    return {"status": "ok", "canonical": "\n".join(["test", state["seed"], text, *token.values()]), "rows": [text],
            "summary": {"kind": "test", "seed": state["seed"], "text": text} | token}
