# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""F0's Q7 runs on one machine (activity-framework-plan.md, 3.4; activity-framework-f0.md, 2): for each
run a fresh server with the spike's pool (TEXSTAGE_SPIKE_POOL) and a fresh data folder, then
simulate.py - 1,100 phones joining within 30 s, each loading a file of 273 KB, then a burst of 1,000
entries within 10 s, most in the last seconds, 30 % distinct - and what matters from both: the phones'
timings, the server's pushes that took longer than 20 ms, its CPU time and memory and its workers'.

    python tools/spike/run_q7.py <scratch folder> [part of a run's name]   # writes tools/spike/results/q7.json

The scratch folder gets the bundle (make_bundle.py), a data folder per run and the servers' logs.
"""
from __future__ import annotations

import ast
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = sys.executable
KEY, PORT = "f0-spike-test-key", 8471
RUNS = [  # (name, activity, share of runaway texts, repetitions)
    ("SPARQL, 1 % runaway", "kg-rivers", 0.01, 3),
    ("SPARQL, 3 % runaway", "kg-rivers", 0.03, 1),
    ("SPARQL, 5 % runaway", "kg-rivers", 0.05, 1),
    ("SPARQL, heavier seed, 1 %", "kg-big", 0.01, 1),
    ("Turtle", "berlin-turtle", 0.0, 1),
    ("SQL, 1 % runaway", "packing-sql", 0.01, 1),
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


def serve(bundles: Path, data: Path, log: Path) -> subprocess.Popen:
    env = {**os.environ, "TEXSTAGE_SPIKE_POOL": ""}
    proc = subprocess.Popen([PY, "-c", "import sys; from texstage.cli import main; sys.exit(main(sys.argv[1:]))",
                             "serve", str(bundles), "--host", "127.0.0.1", "--port", str(PORT), "--data", str(data),
                             "--key", KEY, "--max-players", "1200", "--no-tunnel"],
                            cwd=ROOT, env=env, stdout=log.open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=1).read()
            return proc
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("the server did not start")


def stop(proc: subprocess.Popen) -> dict:
    """The server's and its workers' CPU time and memory, then the end of them all. (A venv's python.exe on
    Windows is a launcher that starts the interpreter as its child: the server is the process in the tree
    that is not a worker - a worker's command line says --multiprocessing-fork - and uses the most memory.)"""
    p = psutil.Process(proc.pid)
    tree = [p] + p.children(recursive=True)

    def is_worker(q):
        try:
            return any("multiprocessing" in a for a in q.cmdline())
        except psutil.Error:
            return False
    workers = [q for q in tree if is_worker(q)]
    server = max((q for q in tree if q not in workers), key=lambda q: q.memory_info().rss)
    usage = {"server_mb": round(server.memory_info().rss / 2**20), "server_cpu_s": round(sum(server.cpu_times()[:2]), 1),
             "workers": len(workers), "workers_cpu_s": round(sum(sum(w.cpu_times()[:2]) for w in workers), 1),
             "worker_mb_max": round(max((w.memory_info().rss for w in workers), default=0) / 2**20)}
    for q in reversed(tree):
        try:
            q.kill()
        except psutil.Error:
            pass
    proc.wait(10)
    return usage


def main() -> int:
    scratch = Path(sys.argv[1]).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[2] if len(sys.argv) > 2 else ""
    runs = [r for r in RUNS if wanted in r[0]]
    subprocess.run([PY, "-I", str(HERE / "make_bundle.py"), str(scratch / "bundles")], check=True)
    bundle = scratch / "bundles" / "spike.bundle"
    results = []
    n = 0
    for name, activity, runaway, repeat in runs:
        for i in range(repeat):
            n += 1
            log = scratch / f"server-{n}.log"
            proc = serve(scratch / "bundles", scratch / f"data-{n}", log)
            t = time.perf_counter()
            sim = subprocess.run([PY, "-I", str(ROOT / "tools" / "simulate.py"), str(bundle),
                                  "--url", f"ws://127.0.0.1:{PORT}/ws", "--key", KEY, "--players", "1100",
                                  "--join-within", "30", "--fetch", "/static/vendor/katex/katex.min.js",
                                  "--activity", activity, "--burst", "1000", "--within", "10", "--deadline",
                                  "--distinct", "0.3", "--runaway", str(runaway), "--wait", "30", "--seed", str(n)],
                                 cwd=ROOT, capture_output=True, text=True, timeout=600)
            usage = stop(proc)
            text = log.read_text(encoding="utf-8", errors="replace")
            pushes = [(int(a), int(b)) for a, b in re.findall(r"spike: a push to (\d+) phones took (\d+) ms", text)]
            run = {"run": name, "repetition": i + 1, "activity": activity, "runaway": runaway,
                   "seconds": round(time.perf_counter() - t), **parse(sim.stdout), **usage,
                   "slow_pushes": len(pushes), "slowest_push_ms": max((b for _, b in pushes), default=0),
                   "unchecked": text.count("could not be checked")}
            results.append(run)
            (scratch / f"simulate-{n}.log").write_text(sim.stdout + sim.stderr, encoding="utf-8")
            print(json.dumps(run), flush=True)
    out = HERE / "results" / (f"q7-{re.sub(r'[^a-z0-9]+', '-', wanted.lower()).strip('-')}.json" if wanted
                              else "q7.json")
    out.write_text(json.dumps({"machine": {"cores": psutil.cpu_count(logical=False), "threads": psutil.cpu_count()},
                               "runs": results}, indent=1) + "\n", encoding="utf-8")
    print(f"\n{'run':28} {'ack p95':>8} {'verdict p95':>12} {'max':>7} {'open':>6} {'close':>6} {'push max':>9} "
          f"{'server MB':>10}")
    for r in results:
        print(f"{r['run'] + ' #' + str(r['repetition']):28} {r.get('ack', [0, 0])[1]:>8} "
              f"{r.get('checked', [0, 0])[1]:>12} {r.get('checked', [0, 0, 0])[2]:>7} {r.get('open', [0, 0])[1]:>6} "
              f"{r.get('close', [0, 0])[1]:>6} {r['slowest_push_ms']:>9} {r['server_mb']:>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
