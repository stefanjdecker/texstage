# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""F0's probes of the engines (docs/architecture/activity-framework-plan.md, 3.2, Q1 to Q3).

Q1  does pyoxigraph run SERVICE over HTTP? A listener on 127.0.0.1 records the connections.
Q2  can a running SPARQL query be stopped? Streaming results are checked between solutions;
    blocking ones (ORDER BY, COUNT over a cross product) are timed, each in a process of its own.
Q3  how deep can a text nest before a parser fails? Each depth runs in a process of its own,
    since a parser that overflows its stack ends the whole process.

    python tools/spike/probe_engines.py [--seed data.ttl] [--only 1 2 3] [--json out.json]

The seed defaults to the KG lecture's (../KnowlegeGraph-VL/05-SPARQL/data.ttl beside this repo).
"""
from __future__ import annotations

import argparse
import json
import platform
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT.parent / "KnowlegeGraph-VL" / "05-SPARQL" / "data.ttl"
BUDGET_S = 2.0                      # a check's CPU time, as today's 2 s of the clock (LA section 12)
CAP_S = 20.0                        # a blocking query is ended after this long


# ------------------------------------------------------------------ Q1: SERVICE
def q1() -> list[dict]:
    import pyoxigraph as ox

    hits: list[float] = []
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            hits.append(time.monotonic())
            try:
                conn.settimeout(2)
                conn.recv(4096)
                conn.sendall(b"HTTP/1.1 500 no\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    url = f"http://127.0.0.1:{port}/sparql"
    forms = {
        "SERVICE": f"SELECT * WHERE {{ SERVICE <{url}> {{ ?s ?p ?o }} }}",
        "service (lower case)": f"select * where {{ service <{url}> {{ ?s ?p ?o }} }}",
        "\\u0053ERVICE (escaped)": f"SELECT * WHERE {{ \\u0053ERVICE <{url}> {{ ?s ?p ?o }} }}",
        "SERVICE SILENT": f"SELECT * WHERE {{ SERVICE SILENT <{url}> {{ ?s ?p ?o }} }}",
    }
    store = ox.Store()
    out = []
    for name, query in forms.items():
        before, t = len(hits), time.perf_counter()
        try:
            result = f"{len(list(store.query(query)))} rows"
        except Exception as e:  # noqa: BLE001 - what the engine says is the finding
            result = f"{type(e).__name__}: {str(e)[:140]}"
        time.sleep(0.2)
        out.append({"form": name, "connections": len(hits) - before, "result": result,
                    "seconds": round(time.perf_counter() - t, 3)})
    srv.close()
    return out


# ------------------------------------------------------------------ Q2: stopping a query
Q2_CASES = {
    "stream: 3-way cross product": "SELECT * WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i }",
    "ORDER BY: 2-way cross product": "SELECT * WHERE { ?a ?b ?c . ?d ?e ?f } ORDER BY ?c ?f",
    "ORDER BY: 3-way cross product": "SELECT * WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i } ORDER BY ?c ?f ?i",
    "COUNT: 3-way cross product": "SELECT (COUNT(*) AS ?n) WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i }",
    "COUNT: 4-way cross product": "SELECT (COUNT(*) AS ?n) WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i . ?j ?k ?l }",
    "DISTINCT: 3-way cross product": "SELECT DISTINCT ?a ?d ?g WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i }",
}


def child_q2(seed: str, query: str) -> dict:
    import psutil
    import pyoxigraph as ox

    store = ox.Store()
    store.load(path=seed, format=ox.RdfFormat.TURTLE)
    me = psutil.Process()
    cpu0, wall0 = time.process_time(), time.perf_counter()
    first, rows, stopped = None, 0, False
    for _ in store.query(query):
        if first is None:
            first = time.process_time() - cpu0
        rows += 1
        if rows % 500 == 0 and time.process_time() - cpu0 > BUDGET_S:
            stopped = True
            break
    mem = me.memory_info()
    return {"first_cpu_s": first, "rows": rows, "stopped_between_solutions": stopped,
            "cpu_s": time.process_time() - cpu0, "wall_s": time.perf_counter() - wall0,
            "peak_mb": round(getattr(mem, "peak_wset", mem.rss) / 2**20)}


def q2(seed: Path) -> list[dict]:
    out = []
    for name, query in Q2_CASES.items():
        t = time.perf_counter()
        try:
            done = subprocess.run([sys.executable, "-I", __file__, "--child", "q2", str(seed), query],
                                  capture_output=True, text=True, timeout=CAP_S)
            line = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
            res = json.loads(line) if line.startswith("{") else {"failed": done.returncode,
                                                                 "stderr": done.stderr[-200:]}
        except subprocess.TimeoutExpired:
            res = {"ended_after_s": CAP_S}
        out.append({"case": name, **res, "process_s": round(time.perf_counter() - t, 2)})
    return out


# ------------------------------------------------------------------ Q3: nesting
FORMS = {
    "sparql: nested groups { { } }": lambda n: "SELECT * WHERE " + "{ " * n + "}" * n,
    "sparql: nested parentheses": lambda n: "SELECT * WHERE { FILTER(" + "(" * n + "1" + ")" * n + ") }",
    "turtle: nested collections": lambda n: "@prefix : <http://e.org/> . :s :p " + "(" * n + ")" * n + " .",
    "turtle: nested blank nodes": lambda n: "@prefix : <http://e.org/> . :s :p " + "[ :p " * n + ":o" + " ]" * n + " .",
    "sql: nested parentheses": lambda n: "SELECT " + "(" * n + "1" + ")" * n,
    "sql: nested subqueries": lambda n: "SELECT " + "(SELECT " * n + "1" + ")" * n,
}
DEPTHS = (50, 100, 128, 129, 200, 256, 400, 512, 800, 1000, 2000, 5000)


def child_q3(form: str, depth: int) -> dict:
    text = FORMS[form](depth)
    try:
        if form.startswith("sql"):
            sqlite3.connect(":memory:").execute(text).fetchall()
        else:
            import pyoxigraph as ox
            if form.startswith("sparql"):
                list(ox.Store().query(text))
            else:
                list(ox.parse(text, format=ox.RdfFormat.TURTLE))
        return {"status": "ok"}
    except Exception as e:  # noqa: BLE001
        return {"status": f"{type(e).__name__}: {str(e)[:100]}"}


def q3() -> list[dict]:
    out = []
    for form in FORMS:
        for depth in DEPTHS:
            try:
                done = subprocess.run([sys.executable, "-I", __file__, "--child", "q3", form, str(depth)],
                                      capture_output=True, text=True, timeout=CAP_S)
                line = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
                status = json.loads(line)["status"] if line.startswith("{") else \
                    f"CRASH (exit code {done.returncode:#x})"
            except subprocess.TimeoutExpired:
                status = f"ended after {CAP_S} s"
            out.append({"form": form, "depth": depth, "length": len(FORMS[form](depth)), "status": status})
    return out


# ------------------------------------------------------------------ main
def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        if sys.argv[2] == "q2":
            print(json.dumps(child_q2(sys.argv[3], sys.argv[4])))
        else:
            print(json.dumps(child_q3(sys.argv[3], int(sys.argv[4]))))
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=Path, default=SEED)
    ap.add_argument("--only", type=int, nargs="*", default=[1, 2, 3])
    ap.add_argument("--json", type=Path, help="also write the results here")
    args = ap.parse_args()
    import psutil
    import pyoxigraph
    results = {"machine": {"cpu": platform.processor(), "system": platform.platform(),
                           "cores": psutil.cpu_count(logical=False), "threads": psutil.cpu_count(),
                           "python": platform.python_version(), "pyoxigraph": pyoxigraph.__version__,
                           "sqlite": sqlite3.sqlite_version}}
    if 1 in args.only:
        results["q1"] = q1()
    if 2 in args.only:
        results["q2"] = q2(args.seed)
    if 3 in args.only:
        results["q3"] = q3()
    text = json.dumps(results, indent=1, ensure_ascii=False)
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
