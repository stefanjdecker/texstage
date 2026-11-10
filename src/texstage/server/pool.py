# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The pool of worker processes that checks the texts of live activities on the server
(docs/architecture/activity-framework-plan.md, F1, 4.4; the design's 10.3 and 11) - from F0's
prototype (tools/spike/pool.py, on the branch f0-spike), reworked after package 3's review.

    pool = Pool().start()
    outcomes = pool.prepare(act, "sql", seed, references, language).result()   # the references'
    future = pool.submit(act, text, owner=player, language=language)  # -> {status, error?, key?, summary?}
    pool.drop(act); pool.close()

- **Workers** (worker.py) start with spawn, as many as the cores less two - at least one -, at a low
  priority; one more waits as a spare. When the pool ends a worker, the spare takes its place at once
  and a new spare starts.
- **Preparing** an activity: one process - the spare, else one that waits - loads its seed and checks its
  references first, each under its own budget of CPU time; a reference that runs away is a `timeout`,
  one that ends its process `internal`, and the next process goes on with the ones after it. Then every
  other process loads the seed, and checks the reference the diffs count against. An SQL seed runs on
  the first process alone: the database it leaves - up to IMAGE_MAX_MB - is what every other loads,
  the next to go on with the references among them, and what the first checks on too; else a seed with
  random() or the time gives each process data of its own (checks/sql.py: image). A seed that does not
  load fails its activity, as does one whose loading ends two processes. A process that cannot prepare
  what the first one did - the seed does not load there, or that reference gives no rows there - is
  ended, and a fresh one prepares it; when three could not, the activity fails, and the log and stats()
  say so. Preparing again replaces what was prepared: each prepare has a generation of the pool's, never
  given twice - after a drop neither -, what an older one answers is set aside, and a check made against
  it runs again.
- **A job** is one text of a prepared activity; the same text, while it is being checked, gets the same
  future. Each owner - a student - has a queue of their own, and the owners take turns; a text that no
  process can take yet does not hold up the owner's others. While no worker is free, only a retry can
  go - to the spare -, and the queue is not walked.
- **Budgets** of CPU time, 2 s by default, at most 10: SQLite stops a query from inside, SPARQL and
  Turtle stop between solutions, and the Python work after the engine counts too; where nothing stops a
  check, the watchdog ends the worker. Either way the text is a `timeout`, the student's. The clock is a
  backstop at five times the budget.
- **Once more, then never again:** a check whose worker died, or that the backstop stopped, runs once
  more on a fresh process - the spare, or a worker that has checked nothing yet: it waits for one that is
  being started, or replaced, or still prepares its activity, and takes the next free process only with
  none to come -; failing again it is `internal`, and its text is set aside: submitted again, it is
  `internal` at once. Both outcomes say `set_aside: True`; no other `internal` does - a check whose
  activity is gone meanwhile, one of a broken pool or of an activity not prepared, one whose process was
  stopped from outside (STOPPED: Ctrl+Break, a stop of the whole process group) -, since those are not
  the text's doing. A process not ready within a minute is ended.
- **Memory:** SQLite's own cap (checks/sql.py, heap_allowance) - a text that reaches it is the student's
  `error` at once, and its worker goes on: SQLite counts alike in every process -; the watchdog, every
  50 ms, ends a worker whose committed memory is more than an allowance above what it held after its
  prepares; a job object on Windows and an address space on Linux as the systems' hard stop. A text that
  runs out of memory otherwise - over the watchdog's limit, or Python's in the worker - runs once more on
  a fresh process; doing it again is the student's `error`, and its message says so. pyoxigraph ending
  its process at the hard stop is a death like any other: `internal`.
- **Broken:** three processes in a row that die before they are ready, or cannot be started at all,
  break the pool: it starts no more, and what is submitted or prepared then fails at once. On Windows the
  watchdog asks a process that is not ready yet whether it has ended: one that ends before it takes its
  pipe leaves no end of the pipe to be seen.
- **Nothing blocks while the pool holds its lock:** a worker's messages go out through its outbox, which
  a thread of its own sends (a prepare carries a whole seed), its replies come in on another; processes
  start, psutil is read, a dead worker is joined, futures are resolved and log lines written outside the
  lock. A future's callbacks run on the pool's threads: a caller on an event loop hands the result over
  itself (call_soon_threadsafe).
"""
from __future__ import annotations

import collections
import concurrent.futures as cf
import logging
import multiprocessing as mp
import os
import queue
import signal
import sys
import threading
import time

from texstage.checks.texts import Words
from texstage.server import worker

log = logging.getLogger("texstage.pool")

ENGINES = {"sql": "texstage.checks.sql", "sparql": "texstage.checks.sparql", "turtle": "texstage.checks.turtle"}
BUDGET_S = 2.0                      # a check's CPU time (plan 4.4)
BUDGET_MAX_S = 10.0                 # at most (AF 11)
REFERENCE_BUDGET_S = 10.0           # a reference's, as it is prepared: the lecturer's own
WATCH_S = 0.05                      # the watchdog's period
BACKSTOP = 5                        # the clock's backstop, times the budget
MEM_ALLOWANCE_MB = 1024             # what a check may take beyond what its worker holds prepared (F0, Q6)
HEAP_ALLOWANCE_MB = 256             # SQLite's own cap for a text, beyond the seeds (F0, Q6)
IMAGE_MAX_MB = 128                  # a seed's database copied to the other processes: at most, and at most a
                                    # quarter of MEM_ALLOWANCE_MB - making the copy takes three times as much
HARD_MB = 2048                      # the system's stop: the job object's per process; twice that, address space
PREPARE_BACKSTOP_S = 120.0          # loading a seed that takes longer ends its process
START_BACKSTOP_S = 60.0             # a process not ready by then is ended: it counts as an early death
EARLY_DEATHS = 3                    # processes in a row that die before they are ready: the pool is broken
SEED_DEATHS = 2                     # processes a seed's loading ends: its activity fails
# A worker stopped from outside - Windows' console closed or Ctrl+Break'd, a stop of the whole process group
# (systemd's SIGTERM, a terminal's SIGHUP) - is not its text's doing: such a death sets no text aside.
STOPPED = {0xC000013A, *(-getattr(signal, n) for n in ("SIGTERM", "SIGHUP", "SIGINT") if hasattr(signal, n))}


def _resolved(value: dict) -> cf.Future:
    fut: cf.Future = cf.Future()
    fut.set_result(value)
    return fut


def _failed(exc: BaseException) -> cf.Future:
    fut: cf.Future = cf.Future()
    fut.set_exception(exc)
    return fut


class _Worker:
    """A worker process, and the two threads that talk to it - made first, started once it is listed."""

    def __init__(self, pool: Pool):
        self.pool = pool
        self.conn = self.proc = self.pid = None
        self.started_at: float | None = None
        self.start_error = ""
        self.ready = False
        self.buried = False                 # the pool has seen its end (_died), once
        self.ps = None                      # psutil.Process, once it is ready
        self.base = 0                       # its committed memory after its prepares: the watchdog counts from it
        self.job: dict | None = None        # the check it is making
        self.unit: dict | None = None       # what it does: a check, a seed's loading, a reference - for the watchdog
        self.done = 0                       # checks it has made: none, it is fresh
        self.ended_for: str | None = None
        self.prepared: set[str] = set()     # acts prepared, at their generation
        self.preparing: dict[str, int] = {}  # act -> the generation last sent, until it is answered
        self.outbox: queue.SimpleQueue = queue.SimpleQueue()

    def start(self) -> None:
        self.conn, child = self.pool.ctx.Pipe()
        self.proc = self.pool.ctx.Process(target=worker.main, args=(child, self.pool.options), daemon=True,
                                          name="texstage-check")
        try:
            self.proc.start()
        finally:
            child.close()
        self.pid, self.started_at = self.proc.pid, time.perf_counter()
        threading.Thread(target=self._send, daemon=True, name=f"texstage-pool-send-{self.pid}").start()
        threading.Thread(target=self._read, daemon=True, name=f"texstage-pool-read-{self.pid}").start()

    def _send(self) -> None:
        while (msg := self.outbox.get()) is not None:
            try:
                if isinstance(msg, bytes):
                    self.conn.send_bytes(msg)            # a database, after the prepare it belongs to
                else:
                    self.conn.send(msg)
            except (OSError, EOFError, ValueError):
                return

    def _read(self) -> None:
        while True:
            try:
                msg = self.conn.recv()
                if msg[0] == "image":                    # the database follows, as bytes of its own
                    msg = (*msg, self.conn.recv_bytes())
            except (EOFError, OSError):
                break
            except Exception:  # noqa: BLE001 - a message that does not read: the pipe is no good any more
                log.exception("checks: worker %s sent what does not read", self.pid)
                self.kill()
                break
            try:
                self.pool._received(self, msg)
            except Exception:  # noqa: BLE001 - the reader goes on whatever handling a message raised
                log.exception("checks: handling a message of worker %s", self.pid)
        try:
            self.pool._died(self)
        except Exception:  # noqa: BLE001
            log.exception("checks: the end of worker %s", self.pid)

    def kill(self) -> None:
        try:
            self.proc.kill()
        except (OSError, AttributeError, ValueError):
            pass

    def free(self) -> bool:
        return self.ready and not self.ended_for and self.job is None and self.unit is None and not self.preparing


class Pool:
    def __init__(self, workers: int | None = None, spare: bool = True, engines: dict | None = None,
                 mem_allowance_mb: float = MEM_ALLOWANCE_MB, heap_allowance_mb: float = HEAP_ALLOWANCE_MB,
                 hard_mb: float = HARD_MB, reference_budget_s: float = REFERENCE_BUDGET_S,
                 prepare_backstop_s: float = PREPARE_BACKSTOP_S, image_max_mb: float = IMAGE_MAX_MB):
        import psutil
        self.psutil = psutil
        self.size = workers or max(1, (psutil.cpu_count(logical=False) or os.cpu_count() or 1) - 2)
        self.spare = spare
        self.engines = dict(ENGINES if engines is None else engines)
        self.mem_allowance = int(mem_allowance_mb * 2**20)
        self.heap_allowance = int(heap_allowance_mb * 2**20)
        self.image_max = int(min(image_max_mb * 2**20, self.mem_allowance / 4))
        self.reference_budget = reference_budget_s
        self.prepare_backstop = prepare_backstop_s
        self.options = {"imports": [ENGINES["sql"], ENGINES["sparql"], ENGINES["turtle"]],   # pyoxigraph too
                        "address_space": int(2 * hard_mb * 2**20) if sys.platform.startswith("linux") else None}
        self.job_object = _JobObject(int(hard_mb * 2**20)) if sys.platform == "win32" else None
        self.ctx = mp.get_context("spawn")
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.workers: list[_Worker] = []
        self.spares: list[_Worker] = []
        self.acts: dict[str, dict] = {}
        self.jobs: dict[int, dict] = {}
        self.inflight: dict[tuple[str, str], dict] = {}
        self.set_aside: set[tuple[str, str]] = set()
        self.queues: collections.OrderedDict[str, collections.deque] = collections.OrderedDict()   # owner -> ids
        self.events: collections.deque = collections.deque(maxlen=200)   # the processes the pool lost, and why
        self.next_id = 0
        self.gens = 0                       # the prepares' generations: the pool's, never given twice
        self.retry_ids: set[int] = set()    # queued jobs that run once more
        self.early_deaths = 0
        self.spawning = 0                   # replacements decided, not started yet
        self.starting = 0                   # processes being started
        self.broken: str | None = None
        self.started = self.closed = False

    # ------------------------------------------------------------------ starting, waiting, closing
    def start(self) -> Pool:
        """Starts the workers and the spare; they become ready on their own (wait_ready)."""
        with self.lock:
            if self.started or self.closed:
                raise RuntimeError("the pool has been started")
            self.started = True
        for _ in range(self.size):
            self._spawn(spare=False)
        if self.spare:
            self._spawn(spare=True)
        threading.Thread(target=self._watch, daemon=True, name="texstage-pool-watch").start()
        log.info("checks: %d workers%s", self.size, " and a spare" if self.spare else "")
        return self

    def wait_ready(self, timeout: float = 60.0) -> bool:
        """Whether every worker and the spare are ready, with every activity prepared, within timeout."""
        end = time.monotonic() + timeout
        with self.lock:
            while not self._all_ready():
                left = end - time.monotonic()
                if left <= 0 or self.broken or self.closed:
                    return False
                self.changed.wait(min(left, 0.05))
            return True

    def _all_ready(self) -> bool:
        if len(self.workers) != self.size or len(self.spares) != (1 if self.spare else 0):
            return False
        acts = {act for act, a in self.acts.items() if not a["failed"]}
        return all(w.ready and not w.ended_for and acts <= w.prepared for w in self.workers + self.spares)

    def close(self) -> None:
        """Ends the workers - a busy one at once -; what still waits is `internal`, resolved first."""
        resolve = []
        with self.lock:
            if self.closed:
                return
            self.closed = True
            everyone = self.workers + self.spares
            busy = {id(w) for w in everyone if not w.free()}
            self.workers, self.spares = [], []
            for job in self.jobs.values():
                resolve.append((job["future"], self._finished(job, {"status": "internal", "error": "closed"}), None))
            self.jobs.clear()
            self.inflight.clear()
            self.queues.clear()
            self.retry_ids.clear()
            for a in self.acts.values():
                self._claim(a, resolve, exc=RuntimeError("the pool closed"))
            self.changed.notify_all()
        self._settle(resolve)
        with self.lock:                                  # a process being started: it gets its pid, to be
            end = time.monotonic() + 5                   # ended below - else _spawn ends it as it starts
            while self.starting and time.monotonic() < end:
                self.changed.wait(0.05)
        for w in everyone:
            if w.pid is None:
                continue
            if id(w) in busy:
                w.kill()
            else:
                w.outbox.put(("exit",))
            w.outbox.put(None)
        end = time.monotonic() + 2
        for w in everyone:
            if w.pid is not None:
                w.proc.join(max(0.0, end - time.monotonic()))
                if w.proc.is_alive():
                    w.kill()
                    w.proc.join(1)
        if self.job_object is not None:
            self.job_object.close()

    # ------------------------------------------------------------------ activities and texts
    def prepare(self, act: str, engine: str, seed: str, references: list[str] = (),
                language: str | None = None) -> cf.Future:
        """Every worker, the spare too, prepares the activity - its seed loaded, its references checked
        in their order, first on one process. The future: their outcomes, a `timeout` for one that ran
        away - or the seed's error (ValueError). Preparing it again cancels the earlier future."""
        module = self.engines.get(engine)
        if module is None:
            raise ValueError(f"no engine {engine!r}")
        resolve = []
        with self.lock:
            if self.closed:
                raise RuntimeError("the pool is closed")
            if self.broken:
                return _failed(RuntimeError(self.broken))
            old = self.acts.get(act)
            if old is not None:
                self._claim(old, resolve, exc=cf.CancelledError())
            refs = list(references)
            self.gens += 1
            a = {"act": act, "gen": self.gens, "module": module, "seed": seed, "texts": refs,
                 "language": language, "options": {"heap_allowance": self.heap_allowance} if engine == "sql" else {},
                 "outcomes": [None] * len(refs), "rows_from": None, "phase": "lead", "lead": None, "deaths": 0,
                 "loaded": False, "image": None, "failed": None,                # loaded: on some process
                 "future": cf.Future()}
            fut = a["future"]
            self.acts[act] = a
            self.set_aside = {k for k in self.set_aside if k[0] != act}
            for w in self.workers + self.spares:
                w.prepared.discard(act)
            self._lead(a)
        self._settle(resolve)
        return fut

    def submit(self, act: str, text: str, owner: str | None = None, budget_s: float = BUDGET_S,
               language: str | None = None) -> cf.Future:
        """A text to check: the future, its outcome - the status (ok, syntax, error, refused, timeout,
        internal), the error, for a result its key and summary, set_aside for a text the pool sets aside;
        besides, how many tries, the CPU time, the waiting and checking times and the processes it ran on."""
        if isinstance(budget_s, bool) or not isinstance(budget_s, (int, float)) or not 0 < budget_s <= BUDGET_MAX_S:
            raise ValueError(f"budget_s: more than 0 and at most {BUDGET_MAX_S} seconds, not {budget_s!r}")
        with self.lock:
            if self.closed:
                raise RuntimeError("the pool is closed")
            if self.broken:
                return _resolved({"status": "internal", "error": self.broken, "tries": 0})
            a = self.acts.get(act)
            if a is None or a["failed"]:
                why = "not prepared" + (f": {a['failed']}" if a else "")
                return _resolved({"status": "internal", "error": why, "tries": 0})
            if (act, text) in self.set_aside:
                return _resolved({"status": "internal", "error": "set aside: it failed twice", "tries": 0,
                                  "set_aside": True})
            job = self.inflight.get((act, text))
            if job is not None:
                return job["future"]
            self.next_id += 1
            job = {"id": self.next_id, "act": act, "text": text, "owner": owner or f"#{self.next_id}",
                   "budget": float(budget_s), "language": language, "future": cf.Future(), "tries": 1,
                   "queued": time.perf_counter(), "started": None, "gen": None, "workers": []}
            self.jobs[job["id"]] = job
            self.inflight[(act, text)] = job
            self._enqueue(job)
            self._dispatch()
            return job["future"]

    def drop(self, act: str) -> None:
        """The activity goes - its deck is gone: the workers let go of it; what waits for it is `internal`
        at once, what is being checked `internal` when it ends. Prepared again under its name, it starts
        afresh: what was under way for it counts for nothing."""
        resolve = []
        with self.lock:
            a = self.acts.pop(act, None)
            if a is not None:
                self._claim(a, resolve, exc=cf.CancelledError())
            for w in self.workers + self.spares:
                w.prepared.discard(act)                  # a load under way stays in w.preparing until it is
                w.outbox.put(("drop", act))              # answered: the worker is busy until then
            self._unqueue(act, "dropped", resolve)
            self.set_aside = {k for k in self.set_aside if k[0] != act}
            self.changed.notify_all()
            self._dispatch()
        self._settle(resolve)

    def stats(self) -> dict:
        with self.lock:
            return {"workers": len(self.workers), "ready": sum(w.ready for w in self.workers),
                    "spares": len(self.spares), "busy": sum(not w.free() for w in self.workers + self.spares),
                    "queued": sum(len(q) for q in self.queues.values()), "activities": len(self.acts),
                    "set_aside": len(self.set_aside), "broken": self.broken, "ended": list(self.events),
                    "failed": {act: a["failed"] for act, a in self.acts.items() if a["failed"]}}

    # ------------------------------------------------------------------ preparing
    def _lead(self, a: dict) -> None:
        """One process checks an activity's references first - the spare, else one that waits, else the
        next to be free -, so that a reference that runs away or ends its process holds up one, not all."""
        if a["phase"] != "lead" or a["lead"] is not None or a["failed"]:
            return
        live = [w for w in self.spares + self.workers if w.ready and not w.ended_for]
        if live:
            w = next((w for w in live if w.free()), live[0])
            a["lead"] = w
            self._send_prepare(w, a, lead=True)

    def _send_prepare(self, w: _Worker, a: dict, lead: bool) -> None:
        """The prepare - with the database the first process's run of the seed left, once there is one, or
        to the first process the size of the one it may make."""
        refs = [[i, t] for i, t in enumerate(a["texts"]) if a["outcomes"][i] is None] if lead else []
        rows = None if a["rows_from"] is None else [a["rows_from"], a["texts"][a["rows_from"]]]
        image = "follows" if a["image"] is not None else self.image_max if lead else None
        w.prepared.discard(a["act"])
        w.preparing[a["act"]] = a["gen"]
        w.outbox.put(("prepare", a["act"], a["gen"], a["module"], a["seed"], refs, rows, a["language"],
                      self.reference_budget, a["options"], image))
        if a["image"] is not None:
            w.outbox.put(a["image"])

    def _spread(self, a: dict) -> None:
        """The references checked: every other process loads the seed - or the database it left."""
        for w in self.workers + self.spares:
            if w.ready and not w.ended_for and a["act"] not in w.prepared and w.preparing.get(a["act"]) != a["gen"]:
                self._send_prepare(w, a, lead=False)

    def _reference_lost(self, a: dict, why: str) -> dict:
        if why == "cpu":
            return {"status": "timeout"}
        if why == "memory":
            return {"status": "error", "error": Words(a["language"]).tooMuchMemory}
        return {"status": "internal", "error": why}

    def _prepare_lost(self, unit: dict, why: str, resolve: list, logs: list) -> None:
        """A process ended while it prepared: a reported reference gets its outcome, and the next process
        goes on after it; a seed's loading counts against the seed."""
        a = self.acts.get(unit["act"])
        if a is None or a["gen"] != unit["gen"] or a["failed"]:
            return
        if unit["kind"] == "reference" and unit["reported"] and a["phase"] == "lead":
            if a["outcomes"][unit["i"]] is None:
                a["outcomes"][unit["i"]] = self._reference_lost(a, why)
            return
        self._prepare_failed(a, why, resolve, logs)

    def _prepare_failed(self, a: dict, why: str, resolve: list, logs: list) -> None:
        """A process its preparing ended, or that could not prepare it: two fail the activity while its
        references are checked, three after."""
        a["deaths"] += 1
        if a["deaths"] >= (SEED_DEATHS if a["phase"] == "lead" else SEED_DEATHS + 1):
            self._fail(a, f"preparing it ended {a['deaths']} processes ({why})", resolve, logs)

    def _fail(self, a: dict, error: str, resolve: list, logs: list) -> None:
        """The activity cannot be prepared: its future fails - resolved already, the log says so, as does
        stats() -, and what waits for it is `internal`."""
        if a["future"] is None:
            logs.append(f"checks: activity {a['act']} failed after it was prepared: {error}")
        a["failed"], a["phase"], a["lead"] = error, "failed", None
        self._claim(a, resolve, exc=ValueError(error))
        self._unqueue(a["act"], f"not prepared: {error}", resolve)

    @staticmethod
    def _claim(a: dict, resolve: list, value=None, exc: BaseException | None = None) -> None:
        """The activity's future, claimed under the lock, so that only one reply resolves it."""
        fut, a["future"] = a["future"], None
        if fut is not None:
            resolve.append((fut, value, exc))

    # ------------------------------------------------------------------ the workers' messages
    def _spawn(self, spare: bool, planned: bool = False) -> None:
        """A new worker or spare: listed under the lock, then started outside it, which takes a while - and
        ended at once if the pool closed meanwhile (the second review: close() did not see it)."""
        w = _Worker(self)
        with self.lock:
            if planned:
                self.spawning -= 1
            if self.closed or self.broken:
                return
            (self.spares if spare else self.workers).append(w)
            self.starting += 1
        error = None
        try:
            w.start()
        except Exception as e:  # noqa: BLE001 - a process that cannot be started dies before it is ready
            error = w.start_error = f"{type(e).__name__}: {e}"
            if w.conn is not None:
                w.conn.close()
        with self.lock:
            self.starting -= 1
            closed = self.closed
            self.changed.notify_all()
        if error is not None:
            self._died(w)
        elif closed:
            w.kill()
            w.outbox.put(None)

    def _received(self, w: _Worker, msg: tuple) -> None:
        kind, resolve, kills, logs = msg[0], [], [], []
        if kind == "ready":                              # psutil and the job object, outside the lock
            try:
                ps = self.psutil.Process(msg[1])
            except self.psutil.Error:
                w.kill()                                 # gone, or not to be watched: it ends, its reader sees it
                return
            in_job = self.job_object.assign(msg[1]) if self.job_object is not None else True
            memory = self._memory(ps)
        elif kind == "prepared":
            memory = self._memory(w.ps) if w.ps is not None else None
        with self.lock:
            if self.closed:
                return
            if kind == "ready":
                if not in_job:
                    logs.append(f"checks: worker {msg[1]} is not in the job object")
                w.ps, w.ready, w.base = ps, True, memory or 0
                self.early_deaths = 0
                for a in self.acts.values():
                    if a["phase"] == "ready":
                        self._send_prepare(w, a, lead=False)
                    else:
                        self._lead(a)
            elif kind == "loading":
                w.unit = {"kind": "load", "act": msg[1], "gen": msg[2], "started": time.perf_counter()}
            elif kind == "image":
                _, act, gen, data = msg
                a = self.acts.get(act)
                if a is not None and a["gen"] == gen and a["phase"] == "lead" and a["lead"] is w:
                    a["image"], a["loaded"] = data, True     # what every other process loads in the seed's place
            elif kind == "reference":
                _, act, gen, i, reported = msg
                w.unit = {"kind": "reference", "act": act, "gen": gen, "i": i, "reported": reported,
                          "budget": self.reference_budget, "started": time.perf_counter(), "cpu0": None}
                a = self.acts.get(act)
                if a is not None and a["gen"] == gen:
                    a["loaded"] = True                   # its seed loads: a load that fails is the process's
            elif kind == "referenced":
                _, act, gen, i, outcome, rows = msg
                w.unit = None
                a = self.acts.get(act)
                if a is not None and a["gen"] == gen and a["phase"] == "lead" and a["lead"] is w:
                    if outcome.pop("memory", False):
                        outcome = {"status": "error", "error": Words(a["language"]).tooMuchMemory}
                    a["outcomes"][i] = outcome
                    if rows and a["rows_from"] is None:
                        a["rows_from"] = i
            elif kind == "prepared":
                _, act, gen, error, _seconds, here = msg
                w.unit = None
                if w.preparing.get(act) == gen:
                    del w.preparing[act]
                a = self.acts.get(act)
                if a is not None and a["gen"] == gen and not a["failed"]:
                    if error is not None and not here and not a["loaded"]:
                        self._fail(a, error, resolve, logs)          # its seed does not load
                    elif error is not None:                          # this process cannot prepare what
                        w.ended_for = w.ended_for or f"could not prepare {act}: {error}"   # another did:
                        kills.append(w)                              # a fresh one will
                        self._prepare_failed(a, w.ended_for, resolve, logs)
                    else:
                        w.prepared.add(act)
                        w.base = max(w.base, memory or 0)
                        a["loaded"] = True
                        if a["phase"] == "lead" and a["lead"] is w:
                            a["phase"], a["lead"] = "ready", None
                            self._claim(a, resolve, value=[o or {"status": "internal", "error": "not checked"}
                                                           for o in a["outcomes"]])
                            self._spread(a)
            elif kind == "done":
                _, jid, outcome, cpu_s = msg
                job = self.jobs.get(jid)
                if w.job is not None and w.job["id"] == jid:
                    w.job, w.unit, w.done = None, None, w.done + 1
                if job is not None:
                    out_of_memory = outcome.pop("memory", False)
                    if out_of_memory:                    # out of memory in the worker: it ends, and the text
                        w.ended_for = w.ended_for or "memory"    # runs once more, on a fresh process
                        kills.append(w)
                    a = self.acts.get(job["act"])
                    stale = a is not None and a["gen"] != job["gen"]
                    if stale and self._retryable(job):
                        self._requeue(job)               # prepared again meanwhile: once more, against that
                    else:
                        if a is None:
                            outcome = {"status": "internal", "error": "dropped"}
                        elif stale:
                            outcome = {"status": "internal", "error": self.broken or f"not prepared: {a['failed']}"}
                        elif out_of_memory and job["tries"] < 2 and self._retryable(job):
                            self._retry(job)
                            outcome = None
                        elif out_of_memory:
                            outcome = {"status": "error", "error": Words(job["language"]).tooMuchMemory}
                        if outcome is not None:
                            self._forget(job)
                            resolve.append((job["future"], self._finished(job, outcome, cpu_s, w), None))
            self.changed.notify_all()
            self._dispatch()
        self._after_lock(logs, resolve, kills)

    def _died(self, w: _Worker) -> None:
        with self.lock:                                  # once, whoever sees its end first: its reader at the
            if w.buried:                                 # pipe's end, the start that failed, or the watchdog
                return
            w.buried = True
        if w.pid is not None:
            w.proc.join(1)                               # outside the lock (F0's review)
        w.outbox.put(None)
        resolve, spawn, logs = [], [], []
        with self.lock:
            if self.closed:
                return
            role = "worker" if w in self.workers else "spare" if w in self.spares else None
            if role == "worker":
                self.workers.remove(w)
            elif role == "spare":
                self.spares.remove(w)
            if w.ended_for:
                why = w.ended_for
            elif w.pid is None:
                why = f"did not start ({w.start_error})"
            else:
                why = f"died (exit code {w.proc.exitcode})"
            stopped = not w.ended_for and w.pid is not None and w.proc.exitcode in STOPPED
            self.events.append({"worker": w.pid, "why": why, "at": time.time()})
            logs.append(f"checks: worker {w.pid} ended: {why}")
            if not w.ready:
                self.early_deaths += 1
            if role == "worker":
                if self.spares:
                    self.workers.append(self.spares.pop(0))     # the spare takes its place at once
                    spawn.append(True)
                else:
                    spawn.append(False)
            elif role == "spare":
                spawn.append(True)
            unit, job = w.unit, w.job
            w.unit = w.job = None
            for a in self.acts.values():
                if a["lead"] is w:
                    a["lead"] = None
            if unit is not None and unit["kind"] in ("load", "reference"):
                self._prepare_lost(unit, why, resolve, logs)
            if job is not None and self.jobs.get(job["id"]) is job:
                a = self.acts.get(job["act"])
                stale = a is not None and a["gen"] != job["gen"]
                if stale and self._retryable(job):
                    self._requeue(job)                   # it ran against what was prepared before: not a try
                else:
                    if a is None:
                        outcome = {"status": "internal", "error": "dropped"}
                    else:
                        outcome = None if stale else self._after(job, why, stopped)
                    if outcome is None and self._retryable(job):
                        self._retry(job)
                    else:
                        self._forget(job)
                        if outcome is None:
                            outcome = {"status": "internal", "error": self.broken or f"not prepared: {a['failed']}"}
                        resolve.append((job["future"], self._finished(job, outcome, None, w), None))
            if self.early_deaths >= EARLY_DEATHS and not self.broken:
                self._break(f"{EARLY_DEATHS} processes in a row died before they were ready", resolve, logs)
            if self.broken:
                spawn.clear()
            self.spawning += len(spawn)                  # replacements to come: a retry waits for a fresh one
            for a in self.acts.values():                 # a new lead for what lost one
                self._lead(a)
            self.changed.notify_all()
            self._dispatch()
        self._after_lock(logs, resolve, [])
        for spare in spawn:
            self._spawn(spare, planned=True)

    def _break(self, why: str, resolve: list, logs: list) -> None:
        """No more processes are started; what waits, and what is being prepared, fails."""
        self.broken = why
        logs.append(f"checks: {why}; no more are started")
        for job in list(self.jobs.values()):
            self._forget(job)
            resolve.append((job["future"], self._finished(job, {"status": "internal", "error": why}), None))
        for a in self.acts.values():
            self._claim(a, resolve, exc=RuntimeError(why))

    def _after(self, job: dict, why: str, stopped: bool = False) -> dict | None:
        """What a check comes to whose worker the pool lost: None, once more. Failing again, it is
        `internal` and set aside - its outcome says so (set_aside), and the server keeps it so (activity.py)
        -, unless its process was stopped from outside (STOPPED): then it is not the text's doing, and the
        next start of the server checks it again."""
        if why == "cpu":
            return {"status": "timeout"}
        if job["tries"] < 2:
            return None
        if why == "memory":
            return {"status": "error", "error": Words(job["language"]).tooMuchMemory}
        if stopped:
            return {"status": "internal", "error": why}
        self.set_aside.add((job["act"], job["text"]))
        return {"status": "internal", "error": why, "set_aside": True}

    def _retryable(self, job: dict) -> bool:
        a = self.acts.get(job["act"])
        return a is not None and not a["failed"] and not self.broken and not self.closed

    def _retry(self, job: dict) -> None:
        job["tries"] += 1
        self._requeue(job)

    def _requeue(self, job: dict) -> None:
        """To the front of its owner's queue: after a death once more, a try more; after its activity was
        prepared again, as it was, since what it ran against is gone."""
        job["started"] = None
        self._enqueue(job, front=True)
        if job["tries"] > 1:
            self.retry_ids.add(job["id"])

    def _unqueue(self, act: str, why: str, resolve: list) -> None:
        """What waits for the activity - not what is being checked - is `internal`."""
        running = {id(w.job) for w in self.workers + self.spares if w.job is not None}
        for job in [j for j in self.jobs.values() if j["act"] == act and id(j) not in running]:
            self._forget(job)
            resolve.append((job["future"], self._finished(job, {"status": "internal", "error": why}), None))

    @staticmethod
    def _finished(job: dict, outcome: dict, cpu_s: float | None = None, w: _Worker | None = None) -> dict:
        now = time.perf_counter()
        started = job["started"] or now
        return outcome | {"tries": job["tries"], "cpu_s": cpu_s, "queued_s": started - job["queued"],
                          "check_s": now - started, "worker": w.pid if w else None, "workers": list(job["workers"])}

    def _forget(self, job: dict) -> None:
        self.jobs.pop(job["id"], None)
        self.retry_ids.discard(job["id"])
        if self.inflight.get((job["act"], job["text"])) is job:
            del self.inflight[(job["act"], job["text"])]

    def _after_lock(self, logs: list, resolve: list, kills: list) -> None:
        for line in logs:
            log.warning(line)
        self._settle(resolve)
        for w in kills:
            w.kill()

    @staticmethod
    def _settle(resolve: list) -> None:
        """Futures resolved outside the lock - their callbacks may take it -, each once."""
        for fut, value, exc in resolve:
            try:
                if isinstance(exc, cf.CancelledError):
                    fut.cancel()
                elif exc is not None:
                    fut.set_exception(exc)
                else:
                    fut.set_result(value)
            except cf.InvalidStateError:
                pass

    # ------------------------------------------------------------------ the queue
    def _enqueue(self, job: dict, front: bool = False) -> None:
        q = self.queues.setdefault(job["owner"], collections.deque())
        (q.appendleft if front else q.append)(job["id"])

    def _next(self, free: list[_Worker], spares: list[_Worker]):
        """The next job and a process to take it, the owners in turns, each owner's first that a process
        can take."""
        for owner in list(self.queues):
            q = self.queues[owner]
            for k, jid in enumerate(q):
                job = self.jobs.get(jid)
                if job is None:
                    continue
                w = self._taker(job, free, spares)
                if w is not None:
                    del q[k]
                    self.queues.move_to_end(owner)
                    self._tidy(owner)
                    return job, w
            self._tidy(owner)
        return None, None

    def _next_retry(self, free: list[_Worker], spares: list[_Worker]):
        """The oldest retry a process can take - before the owners' turns, so that no first try takes the
        fresh process it waits for, and without walking the queue."""
        for jid in sorted(self.retry_ids):
            job = self.jobs.get(jid)
            w = self._taker(job, free, spares) if job is not None else None
            if w is not None:
                q = self.queues.get(job["owner"])
                if q is not None and jid in q:
                    q.remove(jid)
                    self._tidy(job["owner"])
                return job, w
        return None, None

    def _taker(self, job: dict, free: list[_Worker], spares: list[_Worker]) -> _Worker | None:
        """A first try goes to a free worker; a second to a fresh process - the spare, a worker that has
        checked nothing yet -, and to any free one only when no fresh one is to come."""
        act = job["act"]
        if job["tries"] == 1:
            return next((w for w in free if act in w.prepared), None)
        w = next((w for w in spares + free if act in w.prepared and w.done == 0), None)
        if w is None and not self._coming(act):
            w = next((w for w in spares + free if act in w.prepared), None)
        return w

    def _coming(self, act: str) -> bool:
        """Whether a fresh process is to come for the activity: one decided on or being started, one being
        ended - its replacement -, or one that has checked nothing and has not prepared it yet."""
        return self.spawning > 0 or any(w.ended_for or (w.done == 0 and act not in w.prepared)
                                        for w in self.workers + self.spares)

    def _tidy(self, owner: str) -> None:
        q = self.queues.get(owner)
        if q is not None:
            while q and q[0] not in self.jobs:
                q.popleft()
            if not q:
                del self.queues[owner]

    def _dispatch(self) -> None:
        """Jobs to the processes that wait - not one still loading a seed, which would count against the
        check's clock. Retries first; with no worker free only a retry can go, to a spare, and the queue is
        not walked - else every message and every submit walked it while the spare waited (the second
        review)."""
        free = [w for w in self.workers if w.free()]
        spares = [w for w in self.spares if w.free()]
        while free or (spares and self.retry_ids):
            job, w = self._next_retry(free, spares) if self.retry_ids else (None, None)
            if job is None and free:
                job, w = self._next(free, spares)
            if job is None:
                return
            (free if w in free else spares).remove(w)
            self.retry_ids.discard(job["id"])
            now = time.perf_counter()
            w.job, job["started"], job["gen"] = job, now, self.acts[job["act"]]["gen"]
            w.unit = {"kind": "check", "job": job, "budget": job["budget"], "started": now, "cpu0": None}
            job["workers"].append(w.pid)
            w.outbox.put(("check", job["id"], job["act"], job["text"], job["budget"], job["language"]))

    # ------------------------------------------------------------------ the watchdog
    def _memory(self, ps) -> int | None:
        """Committed memory - private bytes on Windows, as the job object counts it; elsewhere resident."""
        try:
            mi = ps.memory_info()
        except Exception:  # noqa: BLE001 - gone, or not to be read: unknown
            return None
        return getattr(mi, "private", mi.rss)

    def _watch(self) -> None:
        """Every 50 ms - whatever one round raises, the next one comes."""
        while True:
            time.sleep(WATCH_S)
            try:
                if not self._watch_once():
                    return
            except Exception:  # noqa: BLE001
                log.exception("checks: the watchdog")

    def _watch_once(self) -> bool:
        """A worker over its memory, a check or a reference over its CPU budget or the clock's backstop, a
        seed's loading over its own: the process is ended. psutil is read, and processes ended, outside the
        lock; the rules are applied under it, to what each process was doing when it was read."""
        with self.lock:
            if self.closed:
                return False
            seen = [(w, w.unit) for w in self.workers + self.spares if w.ps is not None and not w.ended_for]
            # Windows: a process that ended before it took its end of the pipe - it could not start: a broken
            # environment, a virus scanner - leaves that end open in this process, where it was duplicated
            # for it to take: its reader waits for ever, and the pool never learned that it died (the review
            # of package 4's fixes: no process ever started, yet the pool was not broken, and every text
            # waited). So the process itself is asked, while it is not ready.
            unseen = [w for w in self.workers + self.spares
                      if sys.platform == "win32" and not w.ready and not w.buried and w.pid is not None
                      and w.proc.exitcode is not None]
        for w in unseen:
            try:
                w.conn.close()                           # (its reader ends, if the system lets it)
            except OSError:
                pass
            self._died(w)
        readings = []
        for w, unit in seen:
            try:                                          # one process that does not read stops no round
                cpu = sum(w.ps.cpu_times()[:2])
            except Exception:  # noqa: BLE001
                continue
            readings.append((w, unit, cpu, self._memory(w.ps)))
        now, kills = time.perf_counter(), []
        with self.lock:
            for w in self.workers + self.spares:          # a process not ready in time: an early death
                if not w.ready and not w.ended_for and w.started_at and now - w.started_at > START_BACKSTOP_S:
                    w.ended_for = "not ready in time"
                    kills.append(w)
            for w, unit, cpu, memory in readings:
                if w.ended_for or w.unit is not unit:    # what it was doing changed meanwhile
                    continue
                why = None
                if memory is not None and memory > w.base + self.mem_allowance:
                    why = "memory"
                elif unit is not None and unit["kind"] in ("check", "reference"):
                    if unit["cpu0"] is None:
                        unit["cpu0"] = cpu               # its first 50 ms or less go uncounted
                    elif cpu - unit["cpu0"] > unit["budget"] * 1.25 + 0.1:   # the engines stop at the budget
                        why = "cpu"
                    if why is None and now - unit["started"] > unit["budget"] * BACKSTOP:
                        why = "clock"
                elif unit is not None and unit["kind"] == "load" and now - unit["started"] > self.prepare_backstop:
                    why = "prepare"
                if why:
                    w.ended_for = why
                    kills.append(w)
        for w in kills:
            w.kill()
        return True


class _JobObject:
    """A Windows job object: a worker in it may commit at most limit bytes - beyond, an allocation fails
    in the worker -, a crash ends it without a dialog, and the workers end with the job: when the pool
    closes, or when the server's process is gone."""

    def __init__(self, limit: int):
        import ctypes
        from ctypes import wintypes

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.k32 = k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.OpenProcess.restype = wintypes.HANDLE
        self.handle = k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
        info = Extended()
        # PROCESS_MEMORY | DIE_ON_UNHANDLED_EXCEPTION | KILL_ON_JOB_CLOSE
        info.Basic.LimitFlags = 0x100 | 0x400 | 0x2000
        info.ProcessMemoryLimit = limit
        if not k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        self.lock = threading.Lock()

    def assign(self, pid: int) -> bool:
        with self.lock:
            if not self.handle:
                return False
            h = self.k32.OpenProcess(0x0100 | 0x0001, False, pid)      # PROCESS_SET_QUOTA | PROCESS_TERMINATE
            if not h:
                return False
            try:
                return bool(self.k32.AssignProcessToJobObject(self.handle, h))
            finally:
                self.k32.CloseHandle(h)

    def close(self) -> None:
        with self.lock:
            if self.handle:
                self.k32.CloseHandle(self.handle)
                self.handle = None
