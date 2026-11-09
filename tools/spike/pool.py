# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""F0's pool of worker processes (activity-framework-plan.md, 3.3; AF 10.3 and 11) - a prototype.

Workers are started with spawn at a low priority, one more waits as a spare. A job is one text; a
worker checks it in a thread with a 64 MB stack (deep nesting, probe_engines.py Q3) under a CPU-time
budget. A watchdog reads every worker's CPU time and memory (psutil) every 50 ms and ends a worker
over its budget or its limit; the clock is a backstop at five times the budget. A job whose worker
died runs once more on a fresh worker, then is `internal` (AF 11). On Windows each worker is in a job
object with a memory limit, the system's hard stop. Jobs wait in a queue per owner - a student - and
the owners take turns, so that one student's many texts do not hold up the others (AF 10.3).

The pool never blocks while it holds its lock (F0's review): messages to a worker go through its
outbox, which a thread of its own sends; a dead worker is joined, and psutil is read, outside it.

    pool = Pool(workers=4); pool.start()
    pool.prepare("act", "sparql", seed_text, [reference])           # on every worker, the spare too
    future = pool.submit("act", None, text, budget_s=2.0, owner="p1")  # -> {status, key, ...}
    pool.close()

Run by itself it measures Q4 to Q6 on this machine: python tools/spike/pool.py [--workers N]
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import multiprocessing as mp
import os
import platform
import queue
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STACK = 64 * 2**20                  # the checking thread's stack (Q3)
WATCH_S = 0.05                      # the watchdog's period
BACKSTOP = 5                        # the clock's backstop, times the budget
MEM_MB = 1024                       # a worker's memory limit (the watchdog's; the job object's is higher)
JOB_MEM_MB = 1536                   # the job object's hard stop per process (Windows)


# ------------------------------------------------------------------ in the worker
def _worker(conn):
    """A worker process: prepare and check what the pool sends, one at a time, in a thread whose stack
    takes deep nesting. Messages: ("prepare", act, engine, seed, refs), ("check", id, act, text,
    budget), ("test", id, what, arg), ("exit",)."""
    sys.path.insert(0, str(HERE))
    import checks
    try:
        import pyoxigraph  # noqa: F401 - imported before "ready", so that ready means ready for SPARQL
    except ImportError:
        pass

    threading.stack_size(STACK)
    states: dict[str, tuple[str, dict]] = {}

    def loop():
        conn.send(("ready", os.getpid(), time.time()))
        while True:
            try:
                msg = conn.recv()
            except EOFError:
                return
            kind = msg[0]
            if kind == "exit":
                return
            if kind == "prepare":
                _, act, engine, seed, refs = msg
                t = time.perf_counter()
                states[act] = (engine, checks.prepare(engine, seed, refs))
                conn.send(("prepared", act, states[act][1].get("refs"), time.perf_counter() - t))
            elif kind == "check":
                _, jid, act, text, budget = msg
                engine, state = states[act]
                try:
                    result = checks.check(engine, state, text, budget)
                except MemoryError:
                    result = {"status": "error", "key": "error", "error": "out of memory", "memory": True}
                conn.send(("done", jid, result))
            elif kind == "test":                       # what the measurements need: loops, crashes, memory
                _, jid, what, arg = msg
                if what == "noop":
                    conn.send(("done", jid, {"status": "ok"}))
                elif what == "spin":                   # CPU for arg seconds, not stoppable from inside
                    end = time.thread_time() + arg
                    while time.thread_time() < end:
                        pass
                    conn.send(("done", jid, {"status": "ok"}))
                elif what == "crash":
                    os._exit(3)
                elif what == "alloc":                  # arg MB, held, in 64 MB steps
                    try:
                        hold = [bytearray(64 * 2**20) for _ in range(int(arg // 64))]
                        conn.send(("done", jid, {"status": "ok", "held_mb": 64 * len(hold)}))
                    except MemoryError:
                        conn.send(("done", jid, {"status": "error", "error": "MemoryError", "memory": True}))

    t = threading.Thread(target=loop)
    t.start()
    t.join()


# ------------------------------------------------------------------ the job object (Windows)
def _job_object(mem_mb: int):
    """A Windows job object that limits each process in it to mem_mb of committed memory."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    job = k32.CreateJobObjectW(None, None)
    info = EXTENDED()
    info.Basic.LimitFlags = 0x100 | 0x2000          # PROCESS_MEMORY | KILL_ON_JOB_CLOSE
    info.ProcessMemoryLimit = mem_mb * 2**20
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):   # Extended
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject")

    def assign(pid: int) -> bool:
        h = k32.OpenProcess(0x0100 | 0x0001, False, pid)   # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        ok = bool(h) and bool(k32.AssignProcessToJobObject(job, h))
        if h:
            k32.CloseHandle(h)
        return ok

    return assign


# ------------------------------------------------------------------ the pool
class Worker:
    def __init__(self, ctx, pool: "Pool"):
        self.parent, child = ctx.Pipe()
        self.proc = ctx.Process(target=_worker, args=(child,), daemon=True)
        self.started = time.perf_counter()
        self.proc.start()
        child.close()
        self.pool, self.ready_s, self.job, self.ps = pool, None, None, None
        self.cpu0: float | None = None           # the process's CPU time when its job started (the watchdog's)
        self.ended_for: str | None = None
        self.prepared: set[str] = set()
        self.prepare_times: dict[str, float] = {}
        self.outbox: queue.Queue = queue.Queue()  # sent by its own thread: nobody blocks on a full pipe
        threading.Thread(target=self.send_loop, daemon=True).start()
        threading.Thread(target=self.read, daemon=True).start()

    def send_loop(self):
        while (msg := self.outbox.get()) is not None:
            try:
                self.parent.send(msg)
            except (OSError, EOFError, ValueError):
                return

    def read(self):
        while True:
            try:
                msg = self.parent.recv()
            except (EOFError, OSError):
                self.pool.died(self)
                return
            self.pool.received(self, msg)


class Pool:
    def __init__(self, workers: int | None = None, spare: bool = True, mem_mb: int = MEM_MB):
        import psutil
        self.psutil = psutil
        self.n = workers or max(1, (psutil.cpu_count(logical=False) or 2) - 2)
        self.spare_wanted, self.mem_mb = spare, mem_mb
        self.ctx = mp.get_context("spawn")
        self.lock = threading.RLock()
        self.ready = threading.Condition(self.lock)
        self.workers: list[Worker] = []          # checking
        self.spares: list[Worker] = []
        self.queues: collections.OrderedDict[str, collections.deque] = collections.OrderedDict()   # owner -> jobs
        self.jobs: dict[int, dict] = {}
        self.next_id = 0
        self.acts: dict[str, tuple] = {}         # act -> (engine, seed, refs): the spare and new workers too
        self.refs: dict[str, list] = {}          # act -> the references' keys, as a worker found them
        self.assign = _job_object(JOB_MEM_MB)
        self.events: list[dict] = []             # what the watchdog did, for the measurements
        self.closed = False

    # -- workers
    def start(self, wait: bool = True):
        with self.lock:
            self.workers = [Worker(self.ctx, self) for _ in range(self.n)]
            if self.spare_wanted:
                self.spares = [Worker(self.ctx, self)]
        threading.Thread(target=self.watch, daemon=True).start()
        if wait:
            self.wait_ready()

    def wait_ready(self, timeout: float = 60):
        end = time.monotonic() + timeout
        with self.lock:
            while any(w.ready_s is None or not set(self.acts) <= w.prepared for w in self.workers + self.spares):
                self.ready.wait(0.05)
                if time.monotonic() > end:
                    raise TimeoutError("workers not ready")

    def received(self, w: Worker, msg):
        kind = msg[0]
        if kind == "ready":                     # psutil and the job object outside the lock
            ps = self.psutil.Process(msg[1])
            try:
                ps.nice(self.psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == "win32" else 10)
            except Exception:  # noqa: BLE001
                pass
            in_job = self.assign(msg[1]) if self.assign else None
        with self.lock:
            if kind == "ready":
                w.ps, w.in_job_object = ps, in_job
                w.ready_s = time.perf_counter() - w.started
                for act, (engine, seed, refs) in self.acts.items():
                    w.outbox.put(("prepare", act, engine, seed, refs))
            elif kind == "prepared":
                w.prepared.add(msg[1])
                w.prepare_times[msg[1]] = msg[3]
                self.refs[msg[1]] = msg[2]
            elif kind == "done":
                job = self.jobs.pop(msg[1], None)
                w.job, w.cpu0 = None, None
                if job is not None:
                    job["future"].set_result(msg[2] | {"worker": w.proc.pid, "tries": job["tries"],
                                                       "queued_s": job["started"] - job["queued"],
                                                       "check_s": time.perf_counter() - job["started"]})
            self.ready.notify_all()
            self.dispatch()

    def died(self, w: Worker):
        w.proc.join(1)                           # outside the lock (F0's review)
        w.outbox.put(None)
        with self.lock:
            if self.closed:
                return
            why = w.ended_for or f"died (exit code {w.proc.exitcode})"
            self.events.append({"pid": w.proc.pid, "why": why, "at": time.perf_counter(),
                                "cpu_s": getattr(w, "ended_cpu", None), "mem_mb": getattr(w, "ended_mem_mb", None)})
            job = w.job
            if w in self.workers:
                self.workers.remove(w)
                self.workers.append(self.spares.pop() if self.spares else Worker(self.ctx, self))
                if self.spare_wanted:
                    self.spares.append(Worker(self.ctx, self))
            elif w in self.spares:
                self.spares.remove(w)
                self.spares.append(Worker(self.ctx, self))
            if job is not None:
                self.jobs.pop(job["id"], None)
                outcome = None
                if why == "cpu":
                    outcome = {"status": "timeout", "key": "timeout"}
                elif why == "memory" and job["tries"] >= 2:
                    outcome = {"status": "error", "key": "error", "error": "out of memory", "memory": True}
                elif job["tries"] >= 2:            # once more on a fresh worker, then never again (AF 11)
                    outcome = {"status": "internal", "key": "internal", "error": why}
                if outcome is None:
                    job["tries"] += 1
                    self.jobs[job["id"]] = job
                    self._enqueue(job, front=True)
                else:
                    job["future"].set_result(outcome | {"tries": job["tries"], "ended": why,
                                                        "check_s": time.perf_counter() - job["started"]})
            self.ready.notify_all()
            self.dispatch()

    # -- work
    def prepare(self, act: str, engine: str, seed: str, refs: list[str] | None = None, timeout: float = 60):
        """Every worker, the spare too, prepares the activity; its references' keys: self.refs[act]."""
        with self.lock:
            self.acts[act] = (engine, seed, refs or [])
            for w in self.workers + self.spares:
                if w.ready_s is not None:
                    w.outbox.put(("prepare", act, engine, seed, refs or []))
            end = time.monotonic() + timeout
            while any(act not in w.prepared for w in self.workers + self.spares):
                self.ready.wait(0.05)
                if time.monotonic() > end:
                    raise TimeoutError("prepare")

    def submit(self, act: str | None, engine: str | None, text, budget_s: float = 2.0, test: str | None = None,
               owner: str | None = None) -> cf.Future:
        fut: cf.Future = cf.Future()
        with self.lock:
            self.next_id += 1
            jid = self.next_id
            job = {"id": jid, "act": act, "text": text, "budget": budget_s, "test": test, "future": fut,
                   "tries": 1, "queued": time.perf_counter(), "started": None, "owner": owner or f"job {jid}"}
            self.jobs[jid] = job
            self._enqueue(job)
            self.dispatch()
        return fut

    def _enqueue(self, job: dict, front: bool = False):
        q = self.queues.setdefault(job["owner"], collections.deque())
        (q.appendleft if front else q.append)(job["id"])

    def _next(self, free: list[Worker]):
        """The next job and a free worker that can take it, the owners in turns."""
        for owner in list(self.queues):
            q = self.queues[owner]
            while q and q[0] not in self.jobs:
                q.popleft()
            if not q:
                del self.queues[owner]
                continue
            job = self.jobs[q[0]]
            w = next((w for w in free if job["act"] is None or job["act"] in w.prepared), None)
            if w is not None:
                q.popleft()
                if q:
                    self.queues.move_to_end(owner)
                else:
                    del self.queues[owner]
                return job, w
        return None, None

    def dispatch(self):
        with self.lock:
            free = [w for w in self.workers if w.ready_s is not None and w.job is None and not w.ended_for]
            while free:
                job, w = self._next(free)
                if job is None:
                    return
                free.remove(w)
                w.job, w.cpu0, job["started"] = job, None, time.perf_counter()
                w.outbox.put(("test", job["id"], job["test"], job["text"]) if job["test"] else
                             ("check", job["id"], job["act"], job["text"], job["budget"]))

    def queued(self) -> int:
        with self.lock:
            return sum(len(q) for q in self.queues.values())

    def watch(self):
        """Every 50 ms: a busy worker over its CPU budget or the clock's backstop, or any worker over its
        memory limit, is ended (AF 11). psutil is read, and workers are ended, outside the lock."""
        while not self.closed:
            time.sleep(WATCH_S)
            with self.lock:
                seen = [(w, w.job) for w in self.workers + self.spares if w.ps is not None and not w.ended_for]
            ends = []
            for w, job in seen:
                try:
                    mi = w.ps.memory_info()
                    cpu = sum(w.ps.cpu_times()[:2])
                except self.psutil.Error:
                    continue
                mem = getattr(mi, "private", mi.rss)          # committed memory, as the job object counts it
                why = None
                if mem > self.mem_mb * 2**20:
                    why = "memory"
                elif job is not None:
                    if w.cpu0 is None:
                        w.cpu0 = cpu                          # (the job's first 50 ms or less go uncounted)
                    elif cpu - w.cpu0 > job["budget"] * 1.25 + 0.1:   # the engines stop themselves at the budget
                        why = "cpu"
                    if why is None and time.perf_counter() - job["started"] > job["budget"] * BACKSTOP:
                        why = "clock"
                if why:
                    ends.append((w, job, why, cpu, mem))
            for w, job, why, cpu, mem in ends:
                with self.lock:
                    if w.job is not job or w.ended_for:       # its job ended meanwhile
                        continue
                    w.ended_for, w.ended_cpu = why, cpu - (w.cpu0 or cpu)
                    w.ended_mem_mb = mem / 2**20
                try:
                    w.proc.kill()
                except Exception:  # noqa: BLE001
                    pass

    def close(self):
        with self.lock:
            self.closed = True
            everyone = self.workers + self.spares
        for w in everyone:
            w.outbox.put(("exit",))
            w.outbox.put(None)
        for w in everyone:
            w.proc.join(2)
            if w.proc.is_alive():
                w.proc.kill()


# ------------------------------------------------------------------ the measurements (Q4 to Q6)
def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


def ms(x):
    return None if x is None else round(1000 * x, 1)


def measure(workers: int) -> dict:
    kg = HERE.parents[2] / "KnowlegeGraph-VL" / "05-SPARQL"
    seed = (kg / "data.ttl").read_text(encoding="utf-8")
    ref = ("SELECT ?name ?settlementName WHERE { ?river a :River ; :name ?name . "
           "?settlement :locatedOnBank ?river ; :name ?settlementName . } ORDER BY ?name")
    sql_seed = ("CREATE TABLE packing (item TEXT, quantity INTEGER);"
                " INSERT INTO packing VALUES ('Apples',6),('Cups',6),('Blankets',2);")
    out: dict = {}

    t = time.perf_counter()
    pool = Pool(workers)
    pool.start()
    out["q4_start"] = {"workers": pool.n, "spare": 1, "all_ready_s": round(time.perf_counter() - t, 2),
                       "each_ready_s": sorted(round(w.ready_s, 2) for w in pool.workers + pool.spares),
                       "pyoxigraph_imported_before_ready": True,
                       "in_job_object": all(getattr(w, "in_job_object", False) for w in pool.workers)
                       if pool.assign else "not Windows"}
    t = time.perf_counter()
    pool.prepare("kg", "sparql", seed, [ref])
    sparql_s = time.perf_counter() - t
    t = time.perf_counter()
    pool.prepare("sql", "sql", sql_seed, ["SELECT item FROM packing WHERE quantity = 6"])
    out["q4_prepare"] = {"sparql_on_all_ms": ms(sparql_s), "sql_on_all_ms": ms(time.perf_counter() - t),
                         "sparql_on_one_max_ms": ms(max(w.prepare_times["kg"] for w in pool.workers)),
                         "sql_on_one_max_ms": ms(max(w.prepare_times["sql"] for w in pool.workers))}

    # round trips: a check that takes no time, idle and with all other workers busy; how long submit holds
    [pool.submit("kg", None, ref).result(timeout=10) for _ in range(5)]          # warm
    idle, submits = [], []
    for _ in range(300):
        t = time.perf_counter()
        f = pool.submit(None, None, 0, test="noop")
        submits.append(time.perf_counter() - t)
        f.result(timeout=10)
        idle.append(time.perf_counter() - t)
    checks_idle = []
    for _ in range(100):
        t = time.perf_counter()
        pool.submit("kg", None, ref).result(timeout=10)
        checks_idle.append(time.perf_counter() - t)
    busy = [pool.submit(None, None, 3.0, test="spin", budget_s=10) for _ in range(pool.n - 1)]
    time.sleep(0.2)
    loaded = []
    for _ in range(100):
        t = time.perf_counter()
        pool.submit(None, None, 0, test="noop").result(timeout=10)
        loaded.append(time.perf_counter() - t)
    [b.result(timeout=30) for b in busy]
    out["q4_round_trip_ms"] = {
        "noop_idle_p50": ms(pct(idle, 50)), "noop_idle_p95": ms(pct(idle, 95)),
        "kg_reference_check_p50": ms(pct(checks_idle, 50)), "kg_reference_check_p95": ms(pct(checks_idle, 95)),
        "noop_others_busy_p50": ms(pct(loaded, 50)), "noop_others_busy_p95": ms(pct(loaded, 95)),
        "submit_call_max": ms(max(submits))}

    # a burst: 300 distinct SPARQL texts at once, the pool's throughput
    texts = [f"SELECT ?s WHERE {{ ?s ?p ?o }} LIMIT {i + 1}" for i in range(300)]
    t = time.perf_counter()
    futs = [pool.submit("kg", None, x, owner=f"p{i}") for i, x in enumerate(texts)]
    lat = [f.result(timeout=60) for f in futs]
    out["q4_burst_300_distinct"] = {"all_done_s": round(time.perf_counter() - t, 3),
                                    "queued_p95_ms": ms(pct([r["queued_s"] for r in lat], 95))}

    # turns: one owner's 18 slow jobs, then another owner's quick one - it waits for one job, not for 18
    slow = [pool.submit(None, None, 0.5, test="spin", budget_s=5, owner="greedy") for _ in range(18)]
    time.sleep(0.05)
    t = time.perf_counter()
    pool.submit(None, None, 0, test="noop", owner="other").result(timeout=30)
    other = time.perf_counter() - t
    [s.result(timeout=60) for s in slow]
    out["q4_turns"] = {"other_owner_waited_ms": ms(other), "greedy_jobs": 18, "each_s": 0.5, "workers": pool.n}

    # ending and replacing a worker: a crash, then the next job; the new spare ready, pyoxigraph imported
    # and both activities prepared
    t = time.perf_counter()
    r = pool.submit(None, None, 0, test="crash").result(timeout=30)
    crash_s = time.perf_counter() - t
    t = time.perf_counter()
    pool.submit("kg", None, ref).result(timeout=30)
    after = time.perf_counter() - t
    t = time.perf_counter()
    pool.wait_ready()
    out["q4_crash"] = {"result": r["status"], "tries": r["tries"], "both_tries_s": round(crash_s, 3),
                       "next_check_ms": ms(after), "spare_back_and_prepared_s": round(time.perf_counter() - t, 2)}

    # Q5: budgets - SQL stops itself; a loop the engine cannot stop is ended by the watchdog
    runaway_sql = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT count(*) FROM r"
    sql_stops = [pool.submit("sql", None, runaway_sql).result(timeout=30) for _ in range(5)]
    spins = []
    for _ in range(5):
        spins.append(pool.submit(None, None, 30.0, test="spin", budget_s=2.0).result(timeout=60))
        pool.wait_ready()
    sparql_runaway = "SELECT (COUNT(*) AS ?n) WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i . ?j ?k ?l }"
    sparql_stops = []
    for _ in range(3):
        sparql_stops.append(pool.submit("kg", None, sparql_runaway).result(timeout=60))
        pool.wait_ready()
    ended = [e for e in pool.events if e["why"] == "cpu"]
    out["q5_budget_2s"] = {
        "sql_from_inside_cpu_s": [round(r.get("cpu_s", -1), 3) for r in sql_stops],
        "sql_status": sorted({r["status"] for r in sql_stops}),
        "spin_ended_by_watchdog": [r["status"] for r in spins],
        "spin_wall_s": [round(r["check_s"], 2) for r in spins],
        "sparql_count_4way": [r["status"] for r in sparql_stops],
        "sparql_wall_s": [round(r["check_s"], 2) for r in sparql_stops],
        "watchdog_cpu_at_end_s": [round(e["cpu_s"], 2) for e in ended if e["cpu_s"] is not None]}

    # Q6: memory - SQLite's own cap (and no temporary files), the watchdog, the job object
    out["q6_sqlite_cap_400mb_string"] = pool.submit("sql", None, "SELECT length(hex(zeroblob(400000000)))").result(60)
    out["q6_sqlite_cap_600mb_sort"] = pool.submit(
        "sql", None, "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r LIMIT 6000000) "
                     "SELECT n, randomblob(100) AS b FROM r ORDER BY b", budget_s=10).result(60)
    r = pool.submit(None, None, 1300, test="alloc", budget_s=20).result(timeout=60)    # over the watchdog's 1 GB
    pool.wait_ready()
    out["q6_watchdog_1300mb"] = {k: r.get(k) for k in ("status", "error", "tries", "ended", "held_mb")}
    pool.mem_mb = 4096                                                                 # watchdog out of the way
    r = pool.submit(None, None, 2000, test="alloc", budget_s=20).result(timeout=60)    # over the job object's 1.5 GB
    pool.wait_ready()
    out["q6_job_object_2000mb"] = {k: r.get(k) for k in ("status", "error", "tries", "ended", "held_mb")}
    out["events"] = [e["why"] for e in pool.events]
    pool.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    import psutil
    res = {"machine": {"cpu": platform.processor(), "cores": psutil.cpu_count(logical=False),
                       "threads": psutil.cpu_count(), "system": platform.platform()}} | measure(args.workers)
    text = json.dumps(res, indent=1)
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
