# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The pool's process that normalizes and does nothing else (docs/architecture/activity-framework-
design.md, 10.3; the plan of F2, 4.3): a kind's normalize is quick, and what is quick never waits
behind a check. One process (worker.py, the message "normalize"), one input at a time, in the order
they came.

    normalizer = Normalizer(ctx, options).start()
    normalizer.submit("sql-query", item, keys, {"text": "select 1"}, "en").result()
        -> {"input": {...}}        the input normalized: entries that normalize alike are checked once
           {"refused": code}       the kind's normalize refuses it (Unfit), with the phone's code
           {"error": why}          it could not be normalized - never the student's: the kind is not
                                   installed, its normalize raised or took too long, the process ended twice

An input whose process ends is tried again on the next one, TRIES times in all - a process that had
ended while it waited, unseen, costs none where the pipe says so -; one that takes longer than its time
on the clock (NORMALIZE_S) ends its process and is not tried again. Three processes in a row that end
before they are ready break it: what is submitted then is an error at once. On Windows a process that
ends before it takes its end of the pipe leaves that end open here, and its reader waits for ever: the
watch asks the process itself, as the pool's does (pool.py: _watch_once). A future's callbacks run on
the normalizer's threads: a caller on an event loop hands the result over itself.
"""
from __future__ import annotations

import collections
import concurrent.futures as cf
import logging
import threading
import time

from texstage.server import worker

log = logging.getLogger("texstage.checks")
NORMALIZE_S = 5.0                    # an input's time on the clock: normalize is quick, or it is broken
START_S = 60.0                       # a process not ready by then is ended
TRIES = 3                            # processes an input is given to, at most
EARLY_DEATHS = 3
WATCH_S = 0.1


class Normalizer:
    def __init__(self, ctx, options: dict | None = None, budget_s: float = NORMALIZE_S, on_ready=None,
                 target=worker.main, start_s: float = START_S):
        """target: what the process runs (the tests give their own); start_s: its time to become ready."""
        self.ctx = ctx
        self.target = target
        self.start_s = start_s
        self.options = dict(options or {}) | {"imports": ["texstage.activities.registry"]}
        self.budget = budget_s
        self.on_ready = on_ready             # called with the process's id (the pool: its job object)
        self.lock = threading.RLock()
        self.queue: collections.deque = collections.deque()
        self.current: dict | None = None
        self.conn = self.proc = None
        self.ready = False
        self.began = 0.0
        self.early_deaths = 0
        self.ended = 0                       # processes it lost
        self.broken: str | None = None
        self.closed = False
        self.next_id = 0

    # ------------------------------------------------------------------ starting and closing
    def start(self) -> Normalizer:
        self._spawn()
        threading.Thread(target=self._watch, daemon=True, name="texstage-normalize-watch").start()
        return self

    def _spawn(self) -> None:
        conn, child = self.ctx.Pipe()
        proc = self.ctx.Process(target=self.target, args=(child, self.options), daemon=True,
                                name="texstage-normalize")
        try:
            proc.start()
        except Exception as e:  # noqa: BLE001 - it cannot be started: an early death
            child.close()
            conn.close()
            self._lost(None, f"did not start ({type(e).__name__}: {e})")
            return
        child.close()
        with self.lock:
            closed = self.closed
            if not closed:
                self.conn, self.proc, self.ready, self.began = conn, proc, False, time.perf_counter()
        if closed:                                       # closed while it was being started: it is not needed
            proc.kill()
            proc.join(2)
            conn.close()
            return
        threading.Thread(target=self._read, args=(conn, proc), daemon=True, name=f"texstage-normalize-{proc.pid}").start()

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            waiting, self.queue, self.current = [*([self.current] if self.current else []), *self.queue], collections.deque(), None
            proc, conn = self.proc, self.conn
        for job in waiting:
            job["future"].cancel()
        if conn is not None:
            try:
                conn.send(("exit",))
            except (OSError, EOFError, ValueError):
                pass
        if proc is not None:
            proc.join(2)
            if proc.is_alive():
                proc.kill()
                proc.join(2)

    # ------------------------------------------------------------------ an input
    def submit(self, kind: str, item: dict, keys: dict, input: dict, language: str | None = None) -> cf.Future:
        fut: cf.Future = cf.Future()
        with self.lock:
            if self.closed:
                raise RuntimeError("the normalizer is closed")
            if self.broken:
                fut.set_result({"error": self.broken})
                return fut
            self.next_id += 1
            self.queue.append({"id": self.next_id, "msg": (kind, item, keys, language, input), "future": fut, "tries": 1})
            self._next()
        return fut

    def stats(self) -> dict:
        with self.lock:
            return {"waiting": len(self.queue) + (self.current is not None), "ended": self.ended, "broken": self.broken}

    def _next(self) -> None:
        """Under the lock: the next input to the process, if it waits for one."""
        if self.current is not None or not self.ready or not self.queue or self.closed:
            return
        job = self.current = self.queue.popleft()
        job["sent"] = time.perf_counter()
        try:
            self.conn.send(("normalize", job["id"], *job["msg"]))
        except (OSError, EOFError, ValueError):
            job["unsent"] = True                         # the process had ended: its reader sees it, and the
            #                                              input goes to the next one - no try of its own

    def _read(self, conn, proc) -> None:
        while True:
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                break
            except Exception:  # noqa: BLE001 - a message that does not read: the pipe is no good any more
                log.exception("checks: the normalizing process sent what does not read")
                proc.kill()
                break
            done = None
            if msg[0] == "ready":
                if self.on_ready is not None:
                    try:
                        self.on_ready(msg[1])
                    except Exception:  # noqa: BLE001
                        log.exception("checks: the normalizing process, as it became ready")
                with self.lock:
                    if proc is self.proc:
                        self.ready, self.early_deaths = True, 0
                        self._next()
            elif msg[0] == "normalized":
                with self.lock:
                    job = self.current
                    if proc is self.proc and job is not None and job["id"] == msg[1]:
                        self.current, done = None, (job["future"], msg[2])
                        self._next()
            if done is not None:
                self._settle(*done)
        self._lost(proc, None)

    def _lost(self, proc, why: str | None) -> None:
        """A process ended - or could not be started: its input once more on the next one, unless it took
        too long or this was its second; the next process, unless three in a row never were ready."""
        if proc is not None:
            proc.join(1)
        settle = []
        with self.lock:
            if self.closed or (proc is not None and proc is not self.proc):
                return
            was_ready, self.ready, self.proc, self.conn = self.ready, False, None, None
            self.ended += 1
            why = why or f"ended (exit code {proc.exitcode})"
            log.warning("checks: the normalizing process %s", why)
            self.early_deaths = 0 if was_ready else self.early_deaths + 1
            job, self.current = self.current, None
            if job is not None:
                if job.get("late"):
                    settle.append((job["future"], {"error": f"normalizing took more than {self.budget:g} s"}))
                elif job.pop("unsent", False):
                    self.queue.appendleft(job)
                elif job["tries"] >= TRIES:
                    settle.append((job["future"], {"error": f"the normalizing process ended {TRIES} times"}))
                else:
                    job["tries"] += 1
                    self.queue.appendleft(job)
            if self.early_deaths >= EARLY_DEATHS:
                self.broken = f"{EARLY_DEATHS} normalizing processes in a row ended before they were ready"
                log.warning("checks: %s; no more are started", self.broken)
                settle += [(j["future"], {"error": self.broken}) for j in self.queue]
                self.queue.clear()
        for fut, value in settle:
            self._settle(fut, value)
        if not self.broken:
            self._spawn()

    @staticmethod
    def _settle(fut: cf.Future, value: dict) -> None:
        try:
            fut.set_result(value)
        except cf.InvalidStateError:
            pass

    def _watch(self) -> None:
        """An input over its time on the clock, a process not ready in time: the process is ended."""
        while True:
            time.sleep(WATCH_S)
            with self.lock:
                if self.closed or self.broken:
                    return
                now, proc, conn, job = time.perf_counter(), self.proc, self.conn, self.current
                late = job is not None and now - job["sent"] > self.budget
                slow = proc is not None and not self.ready and now - self.began > self.start_s
                unseen = proc is not None and not self.ready and proc.exitcode is not None
                if late:
                    job["late"] = True
            if proc is not None and (late or slow) and not unseen:
                proc.kill()
            if unseen:                                   # it ended before it took its pipe (the module's text)
                try:
                    conn.close()
                except OSError:
                    pass
                self._lost(proc, f"ended before it was ready (exit code {proc.exitcode})")
