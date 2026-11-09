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

A seed "fail ..." does not load, "crash" ends the worker that loads it, "slow s" takes s seconds.
"""
from __future__ import annotations

import os
import time

HELD: list = []


def load(seed: str, **options) -> dict:
    if seed.startswith("fail"):
        raise ValueError("the seed: it says fail")
    if seed.startswith("crash"):
        os._exit(3)
    if seed.startswith("slow "):
        time.sleep(float(seed.split()[1]))
    return {"seed": seed}


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
    elif what == "limits":                               # the worker's address space, on Linux
        import resource
        return {"status": "ok", "canonical": "limits", "rows": [], "summary": {
            "kind": "test", "address_space": resource.getrlimit(resource.RLIMIT_AS)[0]}}
    return {"status": "ok", "canonical": f"test\n{state['seed']}\n{text}", "rows": [text],
            "summary": {"kind": "test", "seed": state["seed"], "text": text}}
