# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The load runs of F1's package 6 (docs/architecture/activity-framework-plan.md, 3.4 and 4.9; the budgets:
activity-framework-design.md, 15.1): for each run a fresh server that checks the texts itself (--checks
server) with a fresh data folder, then tools/simulate.py - 1,100 phones joining, each loading a file of
273 KB, then a burst of 1,000 entries within 10 s, most in the last seconds, 30 % of them distinct, some
running into their budget, while a presenter window's panel and the projector's box fetch the activity's
picture at every new version - and what matters from both: the phones' timings and the projector's updates
against the budgets, the server's and its workers' CPU time and memory, the workers the pool ended.

The servers run the activity framework's core, as texstage serve does by default (F2's packages 13 and 14,
activity-framework-plan-f2.md, 4.12): the phones speak its messages, and load the kinds' files their welcome
names besides the file of 273 KB. With --activities f1 they run F1's type, and the phones speak its messages.

On one machine, the dry run:

    python tools/load/run.py local <scratch> [part of a run's name] [--activities f1]
    python tools/load/run.py local <scratch> --tunnel NAME --port <the tunnel's port> --key <a key of your own>

(the second: the phones go out through the Cloudflare tunnel and come back - its way, though still this
machine's phones; the servers are on the internet meanwhile, hence a key that is not this file's).

For the session - the server on the presentation laptop, with the presenter window and PowerPoint or the
projector window open, the phones from a second machine, once over the room's Wi-Fi, once through the
tunnel - the same runs in the same order on both, with the same part of a name, if any, and the same
--activities:

    python tools/load/run.py server <scratch> [part] [-- more of texstage serve's options, e.g. --tunnel NAME]
    python tools/load/run.py phones <scratch> --url ws://<laptop>:8471/ws [part]      (or wss://<tunnel>/ws)

The laptop's side starts a server per run and waits for Enter, pressed when the phones' side says the run
is done; the phones' side waits for each new server by itself. Each side writes results-<side>.json to
its scratch folder and prints its table: the phones' side the budgets - what never came, an entry not
sent, acknowledged or checked, a file not loaded, counted as over them - and that every entry and every
phone came through and the simulator ended well; the laptop's side that the pool held: not broken, no
worker ended but by its watchdog's way with a long text, its normalizing process never ended (run local
has both in one). One budget is the laptop's own to measure: a slide change in the presenter window,
under 100 ms throughout - open it as /stage?timing, and its console says each change's time. The
projector's updates are counted on the phones' side, by a projector's connection of its own.

The scratch folder gets the bundle (bundle.py), a data folder per run, the logs and each run's entries
(entries-<n>.json: each text, its status, its times). From F0's tools/spike/run_q7.py (branch f0-spike),
which ran the spike's pool. Whether the core gives F1's groups for the same entries: groups.py.
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
from collections import Counter
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
TIMES = (r"median (?P<median>\d+|never)(?: ms)?, 95 % (?P<p95>\d+|never)(?: ms)?, max (?P<max>\d+|never)(?: ms)? "
         r"\((?P<n>\d+)(?: of (?P<of>\d+))?\)")         # (of: how many there were to be; one missing is "never")
PHASE = r" (?P<phones>\d+)(?: of (?P<of>\d+))? phones after (?P<last>\d+) ms \(median (?P<median>\d+) ms\)"
LINES = {                                               # the simulator's lines: each a dict of its numbers
    "joined": r"(?P<phones>\d+) phones joined in (?P<s>[\d.]+) s",
    "refused": r"^joins refused and tried again: (?P<n>\d+)",
    "fetch": r"loaded by (?P<loaded>\d+) phones \((?P<failed>\d+) failed, (?P<unfinished>\d+) unfinished\): " + TIMES,
    "open": r"^open:" + PHASE,
    "close": r"^close:" + PHASE,
    "entries": r"^entries: (?P<sent>\d+)(?: of (?P<of>\d+))? sent within .*?; (?P<distinct>\d+) distinct texts, "
               r"(?P<runaway>\d+) running into their budget",
    "ack": r"^acknowledged: " + TIMES,
    "checked": r"^checked - sent until the phone had its verdict: " + TIMES,
    "others": r"^\.\.\. of the texts that do not run into their budget: " + TIMES,
    "projector": r"^projector: the picture changed at most (?P<most>\d+) times in a second \((?P<versions>\d+) versions",
    "panel": r"^panel: the picture changed at most (?P<most>\d+) times in a second \((?P<versions>\d+) versions",
    "drops": r"^connections lost and taken up again: (?P<n>\d+)",
}
VERDICTS = ("ok", "invalid", "syntax", "error", "refused", "timeout")     # a check's statuses (F1: syntax); the
WATCHDOG = ("cpu", "clock")         # rest - unchecked, internal, no verdict, not sent, refused (code) - are none
#                                     ... and the ends of a worker that are the watchdog's way with a long text


def parse(out: str) -> dict:
    """The simulator's lines (LINES), each a dict of its numbers - None for one that never came -, and the
    entries' statuses."""
    res = {}
    for name, pattern in LINES.items():
        m = re.search(pattern, out, re.M)
        if m:
            res[name] = {k: None if v in (None, "never") else float(v) if "." in v else int(v)
                         for k, v in m.groupdict().items()}
    m = re.search(r"^statuses: (.*)$", out, re.M)
    res["statuses"] = ast.literal_eval(m.group(1)) if m else None
    return res


# ------------------------------------------------------------------ what a run is held against
def asked(r: dict, what: str) -> int | None:
    """What the run asked the simulator for: phones, entries (one a phone at most), or others - the entries
    whose texts do not run into their budget, as the simulator says."""
    phones, burst = r.get("players"), r.get("burst")
    entries = min(burst, phones) if burst and phones else None
    runaway = (r.get("entries") or {}).get("runaway")
    return {"phones": phones, "entries": entries,
            "others": None if entries is None or runaway is None else entries - runaway}[what]


def p95(r: dict, name: str, of: int | None) -> int | str:
    """A line's 95 % over all there were to be: what never came counts as over any budget, as the simulator
    counts it ("k of n" - else the percentiles of what came alone said a budget held while entries were lost);
    a line that does not, with fewer than asked for, is over too. Else why there is none."""
    line = r.get(name)
    if not line:
        return "not measured"
    total = max(of or 0, line["n"])
    if line["p95"] is None or (line["n"] < total and (line.get("of") or 0) < total):
        return f"never for {total - line['n']} of {total}"
    return line["p95"]


def every(r: dict, name: str) -> int | str:
    """When the last phone had the phase: a phone that never had it is over any budget."""
    line = r.get(name)
    if not line:
        return "not measured"
    total = max(asked(r, "phones") or 0, line.get("of") or 0, line["phones"])
    return line["last"] if line["phones"] >= total else f"never on {total - line['phones']} of {total} phones"


def lost_entries(r: dict) -> str | None:
    """What of the burst never came: entries not sent, not acknowledged, without a verdict."""
    e = r.get("entries")
    if not e:
        return "not measured"
    total = max(asked(r, "entries") or 0, e.get("of") or 0, e["sent"])
    acked, checked = ((r.get(name) or {}).get("n", 0) for name in ("ack", "checked"))
    if e["sent"] == acked == checked == total:
        return None
    no = {k: v for k, v in (r.get("statuses") or {}).items() if k not in VERDICTS}
    return f"{e['sent']} of {total} sent, {acked} acknowledged, {checked} with a verdict" + (f" {no}" if no else "")


def lost_phones(r: dict) -> str | None:
    """A phone that did not join, did not load its files, or lost its connection (and took it up again)."""
    joined, fetch = r.get("joined"), r.get("fetch")
    if not joined:
        return "not measured"
    why = [f"{joined['phones']} of {r['players']} joined"] if joined["phones"] < (r.get("players") or 0) else []
    if fetch and (fetch["failed"] or fetch["unfinished"]):
        why.append(f"the files failed on {fetch['failed']}, unfinished on {fetch['unfinished']}")
    if (r.get("drops") or {}).get("n"):
        why.append(f"{r['drops']['n']} connections lost and taken up again")
    return "; ".join(why) or None


def pool_faults(r: dict) -> str | None:
    """A pool that broke, a worker it ended other than by its watchdog's way with a long text, its normalizing
    process ended (by the server's log: ended, normalizer_ended)."""
    why = ["broken"] if r.get("pool_broken") else []
    faults = Counter(w for w in r.get("workers_ended_for") or () if w not in WATCHDOG)
    if faults:
        why.append("workers ended: " + ", ".join(f"{w} ({k})" for w, k in faults.items()))
    if r.get("normalizer_ended_for"):
        why.append("the normalizing process: " + ", ".join(r["normalizer_ended_for"]))
    return "; ".join(why) or None


# the design's budgets (AF 15.1): what of a run is held against which, at most how much of what - a reason
# instead of a number, such as "never for 360 of 1000", is over it
BUDGETS = {"an entry acknowledged (95 %)": (lambda r: p95(r, "ack", asked(r, "entries")), 500, "ms"),
           "its verdict (95 %)": (lambda r: p95(r, "checked", asked(r, "entries")), 3000, "ms"),
           "... of the texts that do not run into their budget (95 %)":
               (lambda r: p95(r, "others", asked(r, "others")) if r.get("others") else
                p95(r, "checked", asked(r, "entries")), 3000, "ms"),
           "the activity open on every phone": (lambda r: every(r, "open"), 500, "ms"),
           "... and closed": (lambda r: every(r, "close"), 500, "ms"),
           "the files on a phone (95 %)": (lambda r: p95(r, "fetch", asked(r, "phones")), 30_000, "ms"),
           "the projector's picture": (lambda r: (r.get("projector") or {}).get("most", "not measured"), 4,
                                       "updates in a second")}
# ... and what a run must have besides - each: why not, or None - on the phones' side, or the server's (the pool)
MUST = {"every entry of the burst sent, acknowledged and given its verdict": ("phones", lost_entries),
        "every phone joined, with its files, and none lost its connection": ("phones", lost_phones),
        "the simulator ended well": ("phones", lambda r: None if r["exit"] == 0 else f"exit {r['exit']}"),
        "the pool not broken, no worker ended but by its watchdog, the normalizing process never":
            ("server", pool_faults)}
SIDE = {"phones": ("exit", "the phones' side"), "server": ("pool_broken", "the server's side")}   # what its runs have


def runs(part: str) -> list[tuple[str, str, float, int]]:
    """The runs, one entry per repetition: (name, activity, runaway, repetition)."""
    return [(name, activity, runaway, i + 1) for name, activity, runaway, repeat in RUNS if part.lower() in name.lower()
            for i in range(repeat)]


def status(base: str, timeout: float = 1.0) -> dict | None:
    try:                                                    # (named: Cloudflare refuses urllib's own name)
        request = urllib.request.Request(f"{base}/api/status", headers={"User-Agent": "texstage-load-runs"})
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return None


ENDED = re.compile(r"checks: worker \S+ ended: (.*?)(?: \(after ([\d.]+) s of CPU\))?\s*$", re.M)   # pool.py's
NORMALIZING = re.compile(r"checks: the normalizing process ((?:ended|did not start).*?)\s*$", re.M)  # line, and
#                                                                     normalizer.py's, as each ends a process


def pool_broke(log: str) -> bool:
    """Whether the server's log says its pool broke - it, or its normalizing process, started no more - or never
    started (checking.py: NoPool; the second review of 2026-11-19: such a run's pool line said held)."""
    return "no more are started" in log or "the pool did not start" in log


def ended(log: str) -> list[str]:
    """Why the pool ended each worker it ended, from the server's log. "cpu" and "clock" are its watchdog's: a
    check over its first slice of CPU time runs again with its whole budget, one over the clock's backstop once
    more, one over its whole budget is the text's timeout. Anything else is a fault: a process that died, did
    not start or was not ready in time, took too much memory, or could not prepare."""
    return [why for why, _ in ENDED.findall(log)]


def ended_cpu(log: str) -> float:
    """The CPU time of the workers the pool ended, as its watchdog last read it - gone by the run's end."""
    return sum(float(cpu) for _, cpu in ENDED.findall(log) if cpu)


def normalizer_ended(log: str) -> list[str]:
    """Why the pool's normalizing process ended, each time (normalizer.py: _lost) - never, in a run that is
    well: its input is tried again on the next process, and the verdicts alone do not show it."""
    return NORMALIZING.findall(log)


# ------------------------------------------------------------------ the server's side
class Server:
    """texstage serve --checks ..., with a fresh data folder; its tree's memory is sampled while it runs."""

    def __init__(self, bundles: Path, data: Path, log: Path, args, local: bool):
        cmd = [PY, "-c", "import sys; from texstage.cli import main; sys.exit(main(sys.argv[1:]))",
               "serve", str(bundles), "--port", str(args.port), "--data", str(data), "--key", args.key,
               "--max-players", "1200", "--checks", args.checks, "--activities", args.activities, *args.more]
        if args.tunnel:
            cmd += ["--tunnel", args.tunnel]
        elif local:
            cmd += ["--host", "127.0.0.1", "--no-tunnel"]
        if args.workers:
            cmd += ["--workers", str(args.workers)]
        self.log = log
        self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log.open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
        self.base = f"http://127.0.0.1:{args.port}"
        for _ in range(120):
            if self.proc.poll() is not None:
                raise RuntimeError(f"the server ended at once - see {log}")
            if (s := status(self.base)) is not None:
                self.served = s.get("activities", "f1")      # the activity type it runs (F1's says none)
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
        """The server's and its workers' CPU time - those alive at the end, and those the pool ended -, their
        largest memory, the workers the pool ended and why (ended), its normalizing process's ends, the activity
        type it ran - then the end of them all."""
        self.watching = False
        server, workers = self.tree()
        usage, alive = dict(self.peak) | {"served": self.served}, None
        try:
            usage["server_cpu_s"] = round(sum(server.cpu_times()[:2]), 1) if server else None
            alive = sum(sum(w.cpu_times()[:2]) for w in workers)
        except psutil.Error:
            pass
        # the log as the run left it, read before the end: the processes are killed below, the workers first, and
        # a pool that still runs logs their deaths - "died (exit code -9)", the teardown's, not the run's (CI,
        # 2026-11-19: a worker and the normalizing process, after 0.2 s of CPU - likely 077ec93's "1 == 0" too)
        text = self.log.read_text(encoding="utf-8", errors="replace")
        try:
            for q in reversed([psutil.Process(self.proc.pid), *psutil.Process(self.proc.pid).children(recursive=True)]):
                try:
                    q.kill()
                except psutil.Error:
                    pass
        except psutil.Error:
            pass
        self.proc.wait(10)
        if alive is not None:
            usage["workers_cpu_s"] = round(alive + ended_cpu(text), 1)
        usage["workers_ended_for"] = ended(text)
        usage["workers_ended"] = len(usage["workers_ended_for"])
        usage["normalizer_ended_for"] = normalizer_ended(text)
        usage["pool_broken"] = pool_broke(text)
        return usage


# ------------------------------------------------------------------ the phones' side
def phones(bundle: Path, args, activity: str, runaway: float, n: int, log: Path, more: list[str]) -> dict:
    """A run's phones (tools/simulate.py): its lines (parse), what it was asked for - the phones and the burst
    its counts are held against -, how it ended; each entry's text and status in entries-<n>.json."""
    cmd = [PY, "-I", str(ROOT / "tools" / "simulate.py"), str(bundle), "--url", args.url, "--key", args.key,
           "--players", str(args.players), "--join-within", str(args.join_within),
           *([] if args.no_fetch else ["--fetch", FETCH]), "--activity", activity, "--burst", str(args.burst), "--within", "10", "--deadline", "--distinct", "0.3",
           "--runaway", str(runaway), "--wait", "30", "--seed", str(n), "--entries", str(log.with_name(f"entries-{n}.json")),
           *more]
    t = time.perf_counter()
    try:
        sim = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
        stdout, stderr, code = sim.stdout, sim.stderr, sim.returncode
    except subprocess.TimeoutExpired as e:                  # one that hangs - a phone that never joins - failed too
        stdout, stderr = (x.decode(errors="replace") if isinstance(x, bytes) else x or "" for x in (e.stdout, e.stderr))
        code = "timeout (900 s)"
    log.write_text(stdout + stderr, encoding="utf-8")
    return {"seconds": round(time.perf_counter() - t), "players": args.players, "burst": args.burst, **parse(stdout),
            "exit": code}


def table(results: list[dict]) -> str:
    """The runs' numbers - "never" for what never came, "-" for what was not measured here -, then each budget
    and what a run must have: held in every run, or NOT, where and why. A line of the other side - the pool's
    on the phones' side of a session - says so: that side's table has it."""
    def at(r, name, key):
        v = (r.get(name) or {}).get(key, "-")
        return "never" if v is None else v
    out = [f"{'run':30} {'ack 95 %':>9} {'verdict 95 %':>13} {'max':>7} {'others 95 %':>12} {'max':>7} {'open':>6} "
           f"{'close':>6} {'files 95 %':>10} {'proj/s':>6} {'entries: sent/ack/verdict of':>29} {'ended':>6}  statuses"]
    for r in results:
        counts = f"{at(r, 'entries', 'sent')}/{at(r, 'ack', 'n')}/{at(r, 'checked', 'n')} of {asked(r, 'entries') or '-'}"
        ended = f"{len(r['workers_ended_for'])}{' broken' if r.get('pool_broken') else ''}" if "pool_broken" in r else "-"
        out.append(f"{r['run'] + ' #' + str(r['repetition']):30} {at(r, 'ack', 'p95'):>9} {at(r, 'checked', 'p95'):>13} "
                   f"{at(r, 'checked', 'max'):>7} {at(r, 'others', 'p95'):>12} {at(r, 'others', 'max'):>7} "
                   f"{at(r, 'open', 'last'):>6} {at(r, 'close', 'last'):>6} {at(r, 'fetch', 'p95'):>10} "
                   f"{at(r, 'projector', 'most'):>6} {counts:>29} {ended:>6}  {r.get('statuses', '')}")
    out.append("")
    lines = [(f"{what}, at most {budget} {unit}", "phones", lambda r, v=value, b=budget, u=unit: over(v(r), b, u))
             for what, (value, budget, unit) in BUDGETS.items()] + [(what, *must) for what, must in MUST.items()]
    for what, side, why in lines:
        key, name = SIDE[side]
        here = [r for r in results if key in r]
        if not here:
            out.append(f"{what}: {name} has it")
            continue
        missed = [f"{r['run']} #{r['repetition']}: {w}" for r in here if (w := why(r)) is not None]
        out.append(f"{what}: " + ("held in every run" if not missed else "NOT in " + "; ".join(missed)))
    return "\n".join(out)


def over(value: int | str, budget: int, unit: str) -> str | None:
    """None if the budget held; else what it was - a number over it, or why there is none."""
    if isinstance(value, str):
        return value
    return None if value <= budget else f"{value} {unit}"


# ------------------------------------------------------------------ the three ways to run
def write(scratch: Path, side: str, results: list[dict], activities: str = "core") -> Path:
    """results-<side>.json: activities, the type asked for (--activities); served, the one the servers ran - each
    run's too."""
    out = scratch / f"results-{side}.json"
    served = sorted({str(r.get("served")) for r in results})
    out.write_text(json.dumps({"cores": psutil.cpu_count(logical=False), "threads": psutil.cpu_count(),
                               "activities": activities, "served": served[0] if len(served) == 1 else served,
                               "runs": results}, indent=1) + "\n", encoding="utf-8")
    return out


def bundle(scratch: Path, stand_ins: bool, lecture: Path | None = None) -> Path:
    cmd = [PY, "-I", str(HERE / "bundle.py"), str(scratch / "bundles")] + (["--stand-ins"] if stand_ins else []) \
        + (["--lecture", str(lecture)] if lecture and not stand_ins else [])
    subprocess.run(cmd, check=True)
    return scratch / "bundles" / "load.bundle"


def through_tunnel(server: Server, timeout: float = 90.0) -> str:
    """The phones' address through the server's tunnel, once the tunnel leads to this very server."""
    here = status(server.base)
    public = here["join"].removesuffix("/play")
    end, good = time.monotonic() + timeout, 0
    while good < 12:                                        # steadily: an answer now and then is not enough
        good = good + 1 if (status(public, 5.0) or {}).get("instance") == here["instance"] else 0
        if time.monotonic() > end:
            raise RuntimeError(f"the tunnel does not lead to this server steadily - see {server.log}")
        time.sleep(0.25)
    u = urllib.parse.urlsplit(public)
    return f"{'wss' if u.scheme == 'https' else 'ws'}://{u.netloc}/ws"


def local(args) -> int:
    path, results = bundle(args.scratch, args.stand_ins, args.lecture), []
    args.url = f"ws://127.0.0.1:{args.port}/ws"
    for n, (name, activity, runaway, i) in enumerate(runs(args.part), 1):
        server = Server(args.scratch / "bundles", args.scratch / f"data-{n}", args.scratch / f"server-{n}.log", args, True)
        try:                                                # (what follows -- is texstage serve's here)
            more = ["--phone-url", through_tunnel(server)] if args.tunnel else []
            run = phones(path, args, activity, runaway, n, args.scratch / f"simulate-{n}.log", more)
        finally:
            usage = server.stop()
        results.append({"run": name, "repetition": i, "activity": activity, "runaway": runaway, **run, **usage})
        print(json.dumps(results[-1]), flush=True)
    print("\n" + table(results) + f"\n\n{write(args.scratch, 'local', results, args.activities)}")
    return 0


def serve(args) -> int:
    bundle(args.scratch, args.stand_ins, args.lecture)
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
    print("\n" + table(results) + f"\n\n{write(args.scratch, 'server', results, args.activities)}")
    return 0


def call(args) -> int:
    path, results, seen = bundle(args.scratch, args.stand_ins, args.lecture), [], set()
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
        if s.get("activities", "f1") != args.activities:
            print(f"  (that server runs the activity type {s.get('activities', 'f1')}, not --activities {args.activities})")
        run = phones(path, args, activity, runaway, n, args.scratch / f"simulate-{n}.log", args.more)
        results.append({"run": name, "repetition": i, "activity": activity, "runaway": runaway,
                        "served": s.get("activities", "f1"), **run})
        print(json.dumps(results[-1]) + "\n  this run is done: Enter on the laptop", flush=True)
    print("\n" + table(results) + f"\n\n{write(args.scratch, 'phones', results, args.activities)}")
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
    ap.add_argument("--activities", default="core", choices=["core", "f1"],
                    help="the servers' activity type: the core's (default, as texstage serve's), or F1's")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--url", help="phones: the laptop's server, ws://<laptop>:<port>/ws")
    ap.add_argument("--players", type=int, default=1100)
    ap.add_argument("--burst", type=int, default=1000)
    ap.add_argument("--join-within", type=float, default=30.0, help="seconds in which the phones join (the plan: 120)")
    ap.add_argument("--no-fetch", action="store_true", help="the phones load no file as they join")
    ap.add_argument("--stand-ins", action="store_true", help="the bundle's stand-ins, not the lecture's activities")
    ap.add_argument("--lecture", type=Path, help="the KG lecture's folder, for its SPARQL and Turtle activities "
                                                 "(default: KnowlegeGraph-VL beside this repository, where it is)")
    ap.add_argument("--tunnel", metavar="NAME", help="local, server: the servers run this Cloudflare tunnel (on the "
                                                     "port its rules name); local: the phones come through it")
    args = ap.parse_args(argv)
    args.more = more
    args.scratch = args.scratch.resolve()
    args.scratch.mkdir(parents=True, exist_ok=True)
    if args.side == "phones" and not args.url:
        ap.error("phones: --url ws://<laptop>:<port>/ws")
    return {"local": local, "server": serve, "phones": call}[args.side](args)


if __name__ == "__main__":
    sys.exit(main())
