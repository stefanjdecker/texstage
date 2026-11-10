# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The load runs of F1's package 6 (docs/architecture/activity-framework-plan.md, 3.4 and 4.9; the budgets:
activity-framework-design.md, 15.1): for each run a fresh server that checks the texts itself (--checks
server) with a fresh data folder, then tools/simulate.py - 1,100 phones joining, each loading a file of
273 KB, then a burst of 1,000 entries within 10 s, most in the last seconds, 30 % of them distinct, some
running into their budget - and what matters from both: the phones' timings against the budgets, the
server's and its workers' CPU time and memory, the workers the pool ended.

On one machine, the dry run:

    python tools/load/run.py local <scratch> [part of a run's name]

For the session - the server on the presentation laptop, with the presenter window and PowerPoint or the
projector window open, the phones from a second machine, once over the room's Wi-Fi, once through the
tunnel - the same runs in the same order on both, with the same part of a name, if any:

    python tools/load/run.py server <scratch> [part] [-- more of texstage serve's options, e.g. --tunnel NAME]
    python tools/load/run.py phones <scratch> --url ws://<laptop>:8471/ws [part] [-- --phone-url wss://<tunnel>/ws]

The laptop's side starts a server per run and waits for Enter, pressed when the phones' side says the run
is done; the phones' side waits for each new server by itself. Each side writes results-<side>.json to
its scratch folder, and the phones' side prints the table with the budgets.

The scratch folder gets the bundle (bundle.py), a data folder per run and the logs. From F0's
tools/spike/run_q7.py (branch f0-spike), which ran the spike's pool.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = sys.executable
KEY, PORT = "load-runs-test-key", 8471
FETCH = "/static/vendor/katex/katex.min.js"
RUNS = [  # (name, activity, share of texts running into their budget, repetitions) - the plan's runs 2 and 3, and F0's
    ("SQL, 1 % runaway", "sql", 0.01, 3),
    ("SPARQL, 1 % runaway", "sparql", 0.01, 3),
    ("SPARQL, 3 % runaway", "sparql", 0.03, 1),
    ("SPARQL, 5 % runaway", "sparql", 0.05, 1),
    ("SPARQL, heavier seed, 1 %", "sparql-big", 0.01, 1),
    ("Turtle", "turtle", 0.0, 1),
]
LINES = {
    "joined_s": (r"phones joined in ([\d.]+) s", float),
    "fetch": (r"loaded by (\d+) phones \((\d+) failed, (\d+) unfinished\): median (\d+) ms, 95 % (\d+) ms, "
              r"max (\d+) ms", int),
    "open": (r"^open: (\d+) phones after (\d+) ms \(median (\d+) ms\)", int),
    "close": (r"^close: (\d+) phones after (\d+) ms \(median (\d+) ms\)", int),
    "ack": (r"^acknowledged: median (\d+) ms, 95 % (\d+) ms, max (\d+) ms \((\d+)\)", int),
    "checked": (r"^checked - sent until the phone had its verdict: median (\d+) ms, 95 % (\d+) ms, max (\d+) ms "
                r"\((\d+)\)", int),
}
# the design's budgets (AF 15.1), in ms: what of a run is held against which
BUDGETS = {"an entry acknowledged (95 %)": (lambda r: r.get("ack", [0, None])[1], 500),
           "its verdict (95 %)": (lambda r: r.get("checked", [0, None])[1], 3000),
           "the activity open on every phone": (lambda r: r.get("open", [0, None])[1], 500),
           "... and closed": (lambda r: r.get("close", [0, None])[1], 500),
           "the file on a phone (95 %)": (lambda r: r.get("fetch", [0] * 5)[4] if r.get("fetch") else None, 30_000)}


def parse(out: str) -> dict:
    res = {}
    for name, (pattern, kind) in LINES.items():
        m = re.search(pattern, out, re.M)
        if m:
            vals = [kind(g) for g in m.groups()]
            res[name] = vals[0] if len(vals) == 1 else vals
    m = re.search(r"^statuses: (.*)$", out, re.M)
    res["statuses"] = ast.literal_eval(m.group(1)) if m else None
    return res


def runs(part: str) -> list[tuple[str, str, float, int]]:
    """The runs, one entry per repetition: (name, activity, runaway, repetition)."""
    return [(name, activity, runaway, i + 1) for name, activity, runaway, repeat in RUNS if part.lower() in name.lower()
            for i in range(repeat)]


def status(base: str, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base}/api/status", timeout=timeout) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ the server's side
class Server:
    """texstage serve --checks ..., with a fresh data folder; its tree's memory is sampled while it runs."""

    def __init__(self, bundles: Path, data: Path, log: Path, args, local: bool):
        cmd = [PY, "-c", "import sys; from texstage.cli import main; sys.exit(main(sys.argv[1:]))",
               "serve", str(bundles), "--port", str(args.port), "--data", str(data), "--key", args.key,
               "--max-players", "1200", "--checks", args.checks, *args.more]
        if local:
            cmd += ["--host", "127.0.0.1", "--no-tunnel"]
        if args.workers:
            cmd += ["--workers", str(args.workers)]
        self.log = log
        self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log.open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
        self.base = f"http://127.0.0.1:{args.port}"
        for _ in range(120):
            if self.proc.poll() is not None:
                raise RuntimeError(f"the server ended at once - see {log}")
            if status(self.base) is not None:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"the server did not start - see {log}")
        self.peak = {"server_mb": 0, "worker_mb": 0, "workers": 0}
        self.watching = True
        threading.Thread(target=self.watch, daemon=True).start()

    def tree(self) -> tuple[psutil.Process | None, list[psutil.Process]]:
        """The server's process and its workers. (A venv's python.exe on Windows is a launcher that starts the
        interpreter as its child: the server is the process of the tree that is not a worker - a worker's
        command line says multiprocessing - and uses the most memory.)"""
        try:
            p = psutil.Process(self.proc.pid)
            tree = [p] + p.children(recursive=True)
        except psutil.Error:
            return None, []

        def is_worker(q):
            try:
                return any("multiprocessing" in a for a in q.cmdline())
            except psutil.Error:
                return False
        workers = [q for q in tree if is_worker(q)]
        others = [q for q in tree if q not in workers]
        try:
            server = max(others, key=lambda q: q.memory_info().rss) if others else None
        except psutil.Error:
            server = None
        return server, workers

    def watch(self):
        while self.watching:
            server, workers = self.tree()
            try:
                self.peak["server_mb"] = max(self.peak["server_mb"], round(server.memory_info().rss / 2**20)) if server else 0
                self.peak["worker_mb"] = max([self.peak["worker_mb"], *(round(w.memory_info().rss / 2**20) for w in workers)])
                self.peak["workers"] = max(self.peak["workers"], len(workers))
            except psutil.Error:
                pass
            time.sleep(1.0)

    def stop(self) -> dict:
        """The server's and its workers' CPU time, their largest memory, the workers the pool ended - then
        the end of them all."""
        self.watching = False
        server, workers = self.tree()
        usage = dict(self.peak)
        try:
            usage["server_cpu_s"] = round(sum(server.cpu_times()[:2]), 1) if server else None
            usage["workers_cpu_s"] = round(sum(sum(w.cpu_times()[:2]) for w in workers), 1)
        except psutil.Error:
            pass
        try:
            for q in reversed([psutil.Process(self.proc.pid), *psutil.Process(self.proc.pid).children(recursive=True)]):
                try:
                    q.kill()
                except psutil.Error:
                    pass
        except psutil.Error:
            pass
        self.proc.wait(10)
        text = self.log.read_text(encoding="utf-8", errors="replace")
        usage["workers_ended"] = len(re.findall(r"checks: worker \S+ ended", text))
        usage["pool_broken"] = "no more are started" in text
        return usage


# ------------------------------------------------------------------ the phones' side
def phones(bundle: Path, args, activity: str, runaway: float, n: int, log: Path, more: list[str]) -> dict:
    cmd = [PY, "-I", str(ROOT / "tools" / "simulate.py"), str(bundle), "--url", args.url, "--key", args.key,
           "--players", str(args.players), "--join-within", str(args.join_within), "--fetch", FETCH,
           "--activity", activity, "--burst", str(args.burst), "--within", "10", "--deadline", "--distinct", "0.3",
           "--runaway", str(runaway), "--wait", "30", "--seed", str(n), *more]
    t = time.perf_counter()
    sim = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    log.write_text(sim.stdout + sim.stderr, encoding="utf-8")
    return {"seconds": round(time.perf_counter() - t), **parse(sim.stdout), "exit": sim.returncode}


def table(results: list[dict]) -> str:
    out = [f"{'run':30} {'ack 95 %':>9} {'verdict 95 %':>13} {'max':>7} {'open':>6} {'close':>6} {'file 95 %':>10}  statuses"]
    for r in results:
        f = r.get("fetch") or [0] * 6
        out.append(f"{r['run'] + ' #' + str(r['repetition']):30} {r.get('ack', [0, 0])[1]:>9} "
                   f"{r.get('checked', [0, 0])[1]:>13} {r.get('checked', [0, 0, 0])[2]:>7} {r.get('open', [0, 0])[1]:>6} "
                   f"{r.get('close', [0, 0])[1]:>6} {f[4]:>10}  {r.get('statuses')}")
    out.append("")
    for what, (value, budget) in BUDGETS.items():
        over = [f"{r['run']} #{r['repetition']}: {value(r)} ms" for r in results
                if value(r) is None or value(r) > budget]
        out.append(f"{what}, at most {budget} ms: " + ("held in every run" if not over else "NOT in " + "; ".join(over)))
    return "\n".join(out)


# ------------------------------------------------------------------ the three ways to run
def write(scratch: Path, side: str, results: list[dict]) -> Path:
    out = scratch / f"results-{side}.json"
    out.write_text(json.dumps({"cores": psutil.cpu_count(logical=False), "threads": psutil.cpu_count(),
                               "runs": results}, indent=1) + "\n", encoding="utf-8")
    return out


def bundle(scratch: Path, stand_ins: bool) -> Path:
    cmd = [PY, "-I", str(HERE / "bundle.py"), str(scratch / "bundles")] + (["--stand-ins"] if stand_ins else [])
    subprocess.run(cmd, check=True)
    return scratch / "bundles" / "load.bundle"


def local(args) -> int:
    path, results = bundle(args.scratch, args.stand_ins), []
    args.url = f"ws://127.0.0.1:{args.port}/ws"
    for n, (name, activity, runaway, i) in enumerate(runs(args.part), 1):
        server = Server(args.scratch / "bundles", args.scratch / f"data-{n}", args.scratch / f"server-{n}.log", args, True)
        try:                                                # (what follows -- is texstage serve's here)
            run = phones(path, args, activity, runaway, n, args.scratch / f"simulate-{n}.log", [])
        finally:
            usage = server.stop()
        results.append({"run": name, "repetition": i, "activity": activity, "runaway": runaway, **run, **usage})
        print(json.dumps(results[-1]), flush=True)
    print("\n" + table(results) + f"\n\n{write(args.scratch, 'local', results)}")
    return 0


def serve(args) -> int:
    bundle(args.scratch, args.stand_ins)
    todo, results = runs(args.part), []
    for n, (name, activity, runaway, i) in enumerate(todo, 1):
        server = Server(args.scratch / "bundles", args.scratch / f"data-{n}", args.scratch / f"server-{n}.log", args, False)
        try:
            input(f"run {n} of {len(todo)}: {name} #{i} - the server is up (port {args.port}, key {args.key}); "
                  "the phones' side goes on by itself. Enter when it says this run is done: ")
        finally:
            usage = server.stop()
        results.append({"run": name, "repetition": i, "activity": activity, "runaway": runaway, **usage})
        print(json.dumps(results[-1]), flush=True)
    print(f"\n{write(args.scratch, 'server', results)}")
    return 0


def call(args) -> int:
    path, results, seen = bundle(args.scratch, args.stand_ins), [], set()
    u = urllib.parse.urlsplit(args.url)
    base = f"{'https' if u.scheme == 'wss' else 'http'}://{u.netloc}"
    todo = runs(args.part)
    for n, (name, activity, runaway, i) in enumerate(todo, 1):
        print(f"run {n} of {len(todo)}: {name} #{i} - waiting for the laptop's server of this run ...", flush=True)
        while True:                                         # a server not seen yet: each run has its own
            s = status(base, 3.0)
            if s is not None and s.get("instance") not in seen:
                seen.add(s.get("instance"))
                break
            time.sleep(1.0)
        if s.get("checks") != "server":
            print(f"  (that server checks with --checks {s.get('checks')})")
        run = phones(path, args, activity, runaway, n, args.scratch / f"simulate-{n}.log", args.more)
        results.append({"run": name, "repetition": i, "activity": activity, "runaway": runaway, **run})
        print(json.dumps(results[-1]) + "\n  this run is done: Enter on the laptop", flush=True)
    print("\n" + table(results) + f"\n\n{write(args.scratch, 'phones', results)}")
    return 0


def main() -> int:
    argv, more = sys.argv[1:], []
    if "--" in argv:
        argv, more = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("side", choices=["local", "server", "phones"])
    ap.add_argument("scratch", type=Path)
    ap.add_argument("part", nargs="?", default="", help="only the runs whose name has this")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--key", default=KEY, help="the presenter key of the runs' servers")
    ap.add_argument("--checks", default="server", choices=["server", "browser", "both"])
    ap.add_argument("--workers", type=int)
    ap.add_argument("--url", help="phones: the laptop's server, ws://<laptop>:<port>/ws")
    ap.add_argument("--players", type=int, default=1100)
    ap.add_argument("--burst", type=int, default=1000)
    ap.add_argument("--join-within", type=float, default=30.0, help="seconds in which the phones join (the plan: 120)")
    ap.add_argument("--stand-ins", action="store_true", help="the bundle's stand-ins, not the lecture's activities")
    args = ap.parse_args(argv)
    args.more = more
    args.scratch = args.scratch.resolve()
    args.scratch.mkdir(parents=True, exist_ok=True)
    if args.side == "phones" and not args.url:
        ap.error("phones: --url ws://<laptop>:<port>/ws")
    return {"local": local, "server": serve, "phones": call}[args.side](args)


if __name__ == "__main__":
    sys.exit(main())
