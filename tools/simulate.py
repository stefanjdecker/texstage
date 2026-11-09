"""Simulated lecture: a host and N phones play a deck against a running texstage server.

    texstage serve <bundles> --port 8470            (in another terminal)
    python tools/simulate.py <bundle-folder> --players 300 [--url ws://localhost:8470/ws]
    python tools/simulate.py --pin 123456 --players 25     (phones only, in a running game)
    python tools/simulate.py <bundle-folder> --pin 123456  (... answering with the deck's references too)
    python tools/simulate.py <bundle-folder> --phone-url wss://quiz.example.org/ws   (phones through a tunnel)

The host (presenter key from the data folder's presenter-key, ~/.texstage or ~/.texquiz, or --key) walks through the deck's
live slides like a lecturer with a clicker; every phone answers each open question after
a random delay (some wrongly, some not at all). Prints, per slide, how long the server took
to tell all phones and the host, the final standings, and how long answers took to be
accepted. For checking the server under load (docs/design.md: 300 players per session; M6)
and for watching the views in M3. wss:// URLs work too (a hosted server).

A live activity (docs/live-activities-design.md) that opens while the phones are in the game gets
their contributions too, spread over a minute as a class sends them: triples about a lecture -
the same ones spelled otherwise, typos, each phone's own name - to a crowd graph; queries to a
query activity, SPARQL or SQL by the engine the phones are told (the KG lecture's exercise 2 and
the like: professors and their lectures), right ones in several spellings and the usual mistakes,
a mistake often corrected half a minute later; Turtle to a turtle activity (the KG lecture's
chapter 3, 03-Serialization/015.tex: three triples about Berlin) - the graph in several
spellings, wrong graphs, syntax errors -, and, when the bundle folder is given, the deck's
reference with variants of it, right and wrong (turtle_answers).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import ssl
import statistics
import time
import urllib.parse
from collections import Counter
from pathlib import Path

import websockets


def now_ms() -> int:
    return int(time.time() * 1000)


# what simulated students send to a live activity: triples about the lecture (a node the
# lecturer merges - :Decker, :StefanDecker -, the same triple in other case - other IRIs, other
# nodes unless the deck says terms=loose -, typos; literals - a string as a phone's keyboard
# quotes it, “...” is "...", one with a language, a number, a boolean) ...
TRIPLES = [(":Decker", ":teaches", ":KG"), (":Decker", ":teaches", ":KG"), (":StefanDecker", ":teaches", ":KG"),
           (":decker", ":teaches", ":kg"), (":Deker", ":teaches", ":KG"), (":KG", ":isAbout", ":RDF"),
           (":KG", ":isAbout", ":SPARQL"), (":KG", ":isAbout", ":Ontologies"), (":KG", ":isAbout", ":RFD"),
           (":KG", ":takesPlaceIn", ":Aachen"), (":KG", ":isTaughtAt", ":RWTH"), (":Decker", ":worksAt", ":RWTH"),
           (":SPARQL", ":queries", ":RDF"), (":RDF", ":isA", ":DataModel"), (":KG", ":hasLecturer", ":Decker"),
           (":KG", ":title", '"Knowledge Graphs"'), (":KG", ":title", "“Knowledge Graphs”"),
           (":KG", ":title", '"Knowledge Graphs"@en'), (":Decker", ":name", '"Stefan Decker"'),
           (":KG", ":credits", "6"), (":RWTH", ":founded", "1870"), (":KG", ":isMandatory", "false")]
# ... and queries for professors and their lectures, right in several spellings and wrong as
# students get them wrong: a cross product, the professors alone, the edge the wrong way round,
# OPTIONAL, a missing brace or keyword
QUERIES = {
    "sparql": {
        "right": ["SELECT ?name ?title WHERE { ?p a :Professor ; :name ?name . ?l :taughtBy ?p ; :title ?title }",
                  "SELECT ?n ?t WHERE { ?l :title ?t ; :taughtBy ?x . ?x :name ?n ; a :Professor }",
                  "SELECT ?name ?title WHERE {\n  ?professor a :Professor ; :name ?name .\n"
                  "  ?lecture :taughtBy ?professor ; :title ?title .\n} ORDER BY ?name"],
        "wrong": ["SELECT ?name ?title WHERE { ?p a :Professor ; :name ?name . ?l :title ?title }",
                  "SELECT ?name WHERE { ?p a :Professor ; :name ?name }",
                  "SELECT ?name ?title WHERE { ?p a :Professor ; :name ?name ; :taughtBy ?l . ?l :title ?title }",
                  "SELECT ?name ?title WHERE { ?p a :Professor ; :name ?name . OPTIONAL { ?l :taughtBy ?p ; :title ?title } }",
                  "SELECT ?name ?title WHERE { ?p a :Professor ; :name ?name . ?l :taughtBy ?p ; :title ?title",
                  "SELECT ?name ?title WHER { ?p a :Professor ; :name ?name . ?l :taughtBy ?p ; :title ?title }"],
    },
    "sql": {
        "right": ["SELECT p.name, l.title FROM professor p JOIN lecture l ON l.taught_by = p.id",
                  "SELECT name, title FROM lecture, professor WHERE taught_by = professor.id",
                  "SELECT professor.name, lecture.title FROM lecture JOIN professor ON lecture.taught_by = professor.id "
                  "ORDER BY professor.name"],
        "wrong": ["SELECT p.name, l.title FROM professor p, lecture l",
                  "SELECT name FROM professor",
                  "SELECT p.name, l.title FROM professor p LEFT JOIN lecture l ON l.taught_by = p.id",
                  "SELECT p.name, l.title FROM professor p JOIN lecture l ON l.id = p.id",
                  "SELECT p.name, l.title FORM professor p JOIN lecture l ON l.taught_by = p.id",
                  "SELECT p.nme, l.title FROM professor p JOIN lecture l ON l.taught_by = p.id"],
    },
}
# ... and Turtle: the KG lecture's chapter 3 (03-Serialization/015.tex), Berlin's two labels and
# its population in DBpedia's names (the seed declares dbr:, dbo:, rdfs: and xsd:) - the same three
# triples in several spellings (full triples, ; and , , the datatype written out, full IRIs,
# prefixes of its own, another order, an iPhone's quotes) - and wrong as students get it wrong:
# the number as a string or of another datatype, a language tag missing, a triple missing; a
# period missing, a space after a colon, ; where , belongs
BERLIN = 'dbr:Berlin rdfs:label "Berlin"@de , "Berlino"@it ;\n  dbo:populationTotal 3596999 .'
TURTLE = {
    "right": [BERLIN,
              'dbr:Berlin rdfs:label "Berlin"@de .\ndbr:Berlin rdfs:label "Berlino"@it .\n'
              'dbr:Berlin dbo:populationTotal 3596999 .',
              'dbr:Berlin rdfs:label "Berlin"@de ; rdfs:label "Berlino"@it ; dbo:populationTotal 3596999 .',
              '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\ndbr:Berlin rdfs:label "Berlin"@de , "Berlino"@it ;\n'
              '  dbo:populationTotal "3596999"^^xsd:integer .',
              '<http://dbpedia.org/resource/Berlin> <http://www.w3.org/2000/01/rdf-schema#label> "Berlin"@de, "Berlino"@it;\n'
              '  <http://dbpedia.org/ontology/populationTotal> 3596999.',
              '@prefix dbr: <http://dbpedia.org/resource/> .\n@prefix dbo: <http://dbpedia.org/ontology/> .\n'
              '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n' + BERLIN,
              'dbr:Berlin dbo:populationTotal 3596999 ;\n  rdfs:label "Berlino"@it , "Berlin"@de .',
              BERLIN.replace('"Berlin"@de', "“Berlin”@de").replace('"Berlino"@it', "“Berlino”@it")],
    "wrong": [BERLIN.replace("3596999", '"3596999"'),
              BERLIN.replace("3596999", '"3596999"^^xsd:int'),
              BERLIN.replace('"Berlin"@de', '"Berlin"'),
              BERLIN.replace(' , "Berlino"@it', ""),
              BERLIN[:-2],
              'dbr:Berlin rdfs:label "Berlin"@de .\ndbr:Berlin rdfs:label "Berlino"@it\n'
              'dbr:Berlin dbo:populationTotal 3596999 .',
              BERLIN.replace("dbr:Berlin", "dbr: Berlin"),
              BERLIN.replace(" , ", " ; ")],
}
XSD = "http://www.w3.org/2001/XMLSchema#"
NUMBER = re.compile(r"(?<=\s)[+-]?\d*\.?\d+(?=\s*[;,.](?:\s|$))")       # a number as an object, at the end of one
TAGGED = re.compile(r'("[^"\n]*")@[A-Za-z]+(?:-[A-Za-z0-9]+)*')          # a string with its language
PREFIXED = re.compile(r"(?<![<\w])([A-Za-z][\w-]*):(?=[A-Za-z])")       # a prefixed name: its prefix


def turtle_answers(reference: str) -> dict[str, list[str]]:
    """Answers made from a deck's reference (keys.json) to a turtle activity: the same graph - as
    written, its first number with the datatype written out - and others: that number as a
    string, a language tag left out; the last period left out, a space after a prefix's colon."""
    right, wrong = [reference], []
    if m := NUMBER.search(reference):
        number = m.group()
        datatype = "integer" if number.lstrip("+-").isdigit() else "decimal"
        right.append(f'{reference[:m.start()]}"{number}"^^<{XSD}{datatype}>{reference[m.end():]}')
        wrong.append(f'{reference[:m.start()]}"{number}"{reference[m.end():]}')
    wrong += [t for t in (TAGGED.sub(r"\1", reference, count=1), PREFIXED.sub(r"\1: ", reference, count=1),
                          reference.rstrip()[:-1] if reference.rstrip().endswith(".") else reference)
              if t != reference]
    return {"right": right, "wrong": wrong}


def deck_references(bundle: Path | None) -> dict[str, list[str]]:
    """The references of the deck's activities (keys.json in the bundle folder), by activity."""
    try:
        keys = json.loads((bundle / "keys.json").read_text(encoding="utf-8"))
    except (TypeError, OSError, ValueError):
        return {}
    return {aid: list(k.get("reference") or []) for aid, k in (keys.get("items", {}).get("activity") or {}).items()}


class Phone:
    window = 4.0                                # answers come within this many seconds
    rtts: list[int] = []                        # all phones: answer sent -> "ok" (ms)
    drops: list[str] = []                       # all phones: connections lost (and taken up again)
    references: dict[str, list[str]] = {}       # the deck's activities' references, if the bundle is given
    fetch: str | None = None                    # --fetch: a file every phone loads when it joins ...
    fetches: list[float] = []                   # ... and the seconds it took, all phones
    fetch_failed: list[str] = []
    bursting = False                            # --activity: the phones send their burst entries only
    entries: list[dict] = []                    # all phones' burst entries: sent, acknowledged, checked (ms)

    def __init__(self, url: str, pin: str, name: str, rng: random.Random):
        self.url, self.pin, self.name, self.rng = url, pin, name, rng
        self.state: dict = {}
        self.seen: dict[str, int] = {}          # "round id:phase" and "round id" -> local time first seen
        self.answered: set[str] = set()
        self.sent: dict[str, int] = {}
        self.acted: set[str] = set()            # the activities this phone has taken part in (or chosen not to)
        self.busy: set[str] = set()             # ... and those it is reading, thinking about, typing for
        self.n = 0
        self.token = None                       # from the welcome: a lost connection resumes with it
        self.gone = False                       # the server said bye
        self.ws = None
        self.burst_at: float | None = None      # --activity: when this phone sends (time.monotonic) ...
        self.burst_text: str | None = None      # ... and what
        self.entry: dict | None = None          # ... and how it went
        self.fetched = False

    async def run(self, stop: asyncio.Event):
        # as a phone's browser does (web/shared/client.js): a lost or closed connection is taken
        # up again with the token - until the server says bye (the game is over, the phone removed)
        while True:
            try:
                async with websockets.connect(self.url, max_size=2**22) as ws:
                    self.ws = ws
                    first = {"t": "resume", "token": self.token} if self.token else \
                        {"t": "join", "pin": self.pin, "nickname": self.name}
                    await ws.send(json.dumps(first | {"id": "join"}))
                    if Phone.fetch and not self.fetched:         # as a phone loads the kinds' files (AF 7.3)
                        self.fetched = True
                        asyncio.create_task(self.get_file())
                    reader = asyncio.create_task(self.read(ws))
                    stopper = asyncio.create_task(stop.wait())
                    done, _ = await asyncio.wait({reader, stopper}, return_when=asyncio.FIRST_COMPLETED)
                    reader.cancel()
                    stopper.cancel()
                    if reader in done and reader.exception():
                        raise reader.exception()             # e.g. the join failed
                    if stopper in done or self.gone:
                        return
                    why = f"closed by the server, code {ws.close_code}"
            except (websockets.ConnectionClosedError, OSError) as err:
                if stop.is_set() or self.token is None:
                    raise
                why = str(err)
            line = f"{time.strftime('%H:%M:%S')} {self.name}: connection lost ({why}) - taken up again"
            Phone.drops.append(line)
            print(line, flush=True)
            await asyncio.sleep(1 + self.rng.random())

    async def read(self, ws):
        async for text in ws:
            m = json.loads(text)
            if m["t"] == "error" and m.get("re") == "join":
                raise RuntimeError(f"{self.name}: {m['message']}")
            if m["t"] == "welcome" and m.get("token"):
                self.token = m["token"]
            if m["t"] == "bye":
                self.gone = True
            if m["t"] == "ok" and m.get("re") in self.sent:
                Phone.rtts.append(now_ms() - self.sent.pop(m["re"]))
            e = self.entry
            if e and m.get("re") == e["mid"]:
                if m["t"] == "ok":
                    e["ack"], e["cid"] = now_ms(), m.get("contribution")
                elif m["t"] == "error":
                    e["refused"] = m.get("code") or m.get("message")
            if m["t"] != "state":
                continue
            self.state = m
            mine = (m.get("activity") or {}).get("mine")
            if e and e.get("cid") and "checked" not in e and isinstance(mine, dict) and mine.get("id") == e["cid"] \
                    and mine.get("status") not in (None, "waiting"):
                e["checked"], e["status"] = now_ms(), mine["status"]
            r = m.get("round")
            if r:
                self.seen.setdefault(r["id"], now_ms())
                self.seen.setdefault(f"{r['id']}:{r['phase']}", now_ms())
                if r["phase"] == "open" and r["id"] not in self.answered and not r["answer"]:
                    self.answered.add(r["id"])
                    asyncio.create_task(self.answer(r))
            act = m.get("activity")
            if act and act.get("phase") == "open" and act["id"] not in self.acted | self.busy and not act.get("blocked"):
                self.busy.add(act["id"])
                asyncio.create_task(self.contribute(act))

    def open(self, aid: str) -> bool:
        act = self.state.get("activity")
        return bool(act) and act.get("id") == aid and act.get("phase") == "open"

    async def contribute(self, act: dict):
        # as a student: an activity that closes before the phone sent anything - the lecturer only
        # passed its frame - is still to do when it opens again
        try:
            await self.take_part(act)
        finally:
            self.busy.discard(act["id"])

    async def get_file(self):
        try:
            _, seconds = await http_get(self.url, Phone.fetch)
            Phone.fetches.append(seconds)
        except Exception as err:  # noqa: BLE001 - counted, not fatal
            Phone.fetch_failed.append(f"{type(err).__name__}: {err}"[:120])

    async def take_part(self, act: dict):
        rng, aid = self.rng, act["id"]
        if Phone.bursting:                                     # --activity: one entry, at its time
            self.acted.add(aid)
            if self.burst_text is None or act["input"] != "code":
                return
            await asyncio.sleep(max(0.0, self.burst_at - time.monotonic()))
            if self.open(aid):
                self.n += 1
                self.entry = {"mid": f"b{self.n}", "text": self.burst_text, "sent": now_ms()}
                Phone.entries.append(self.entry)
                await self.send({"t": "activity.send", "activity": aid, "id": self.entry["mid"],
                                 "text": self.burst_text})
            return
        if rng.random() < 0.1:                                 # some take no part
            self.acted.add(aid)
            return
        if act["input"] == "tuple":
            own = (f":{self.name}", ":attends", ":KG")
            picks = ([own] if rng.random() < 0.7 else []) + rng.sample(TRIPLES, rng.randint(1, 4))
            await asyncio.sleep(rng.uniform(2, 15))
            for t in picks[:act["limit"]]:
                if not self.open(aid):
                    return
                await self.contribution(aid, fields=list(t) if len(act["fields"]) == 3 else [t[0], t[-1]])
                await asyncio.sleep(rng.uniform(2.5, 9))           # (one every 2 s at most)
            return
        tokens = act.get("tokens", [])                           # (a server that does not tell the engine)
        engine = act.get("engine") or ("sparql" if "?" in tokens else "turtle" if "_:" in tokens else "sql")
        if engine == "turtle":
            queries = {"right": list(TURTLE["right"]), "wrong": list(TURTLE["wrong"])}
            for reference in Phone.references.get(aid, []):
                for kind, texts in turtle_answers(reference).items():
                    queries[kind] += texts * 3                   # the deck's own graph: as often as the rest
        else:
            queries = QUERIES.get(engine, QUERIES["sql"])
        await asyncio.sleep(rng.uniform(5, 40))                   # typing on a phone takes a while
        wrong = rng.random() < 0.55
        if not self.open(aid):
            return
        await self.contribution(aid, text=rng.choice(queries["wrong" if wrong else "right"]))
        if wrong and act["limit"] > 1 and rng.random() < 0.6:     # ... and is corrected
            await asyncio.sleep(rng.uniform(15, 40))
            if self.open(aid):
                await self.contribution(aid, text=rng.choice(queries["right"]))

    async def contribution(self, aid: str, **body):
        self.n += 1
        self.acted.add(aid)
        await self.send({"t": "activity.send", "activity": aid, "id": f"a{self.n}", **body})

    async def send(self, msg: dict):
        try:
            await self.ws.send(json.dumps(msg))
        except websockets.ConnectionClosed:                    # lost meanwhile (run takes it up again)
            pass

    async def answer(self, r: dict):
        if self.rng.random() < 0.05:                           # some never answer
            return
        await asyncio.sleep(self.rng.uniform(0.3, min(self.window, r["limit"] / 1000 * 0.8)))
        q = r["question"]
        ids = [a["id"] for a in q.get("answers", [])]
        kind = q["type"]
        if kind in ("single", "truefalse") or (kind == "poll" and q.get("select") != "multiple"):
            answer = {"choice": self.rng.choice(ids)}
        elif kind in ("multiple", "poll"):
            answer = {"choices": self.rng.sample(ids, self.rng.randint(1, len(ids)))}
        elif kind == "order":
            answer = {"order": self.rng.sample(ids, len(ids))}
        elif kind == "numeric":
            lo, hi = q["numeric"].get("min") or 0, q["numeric"].get("max") or 100
            answer = {"value": self.rng.randint(int(lo), int(hi))}
        else:
            answer = {"text": self.rng.choice(["graph", "RDF", "triples", "knowledge", "SPARQL"])}
        self.sent[r["id"]] = now_ms()
        await self.send({"t": "answer", "round": r["id"], "answer": answer, "id": r["id"]})


def percentiles(values: list[int]) -> str:
    if not values:
        return "none"
    v = sorted(values)
    pick = lambda q: v[min(len(v) - 1, int(q * len(v)))]   # noqa: E731
    return f"median {pick(0.5)} ms, 95 % {pick(0.95)} ms, max {v[-1]} ms ({len(v)})"


# ------------------------------------------------------------------ --activity: F0's runs
# (docs/architecture/activity-framework-plan.md, 3.4): a burst of entries to one activity, timed
RUNAWAY = {"sparql": "SELECT (COUNT(*) AS ?n{k}) WHERE {{ ?a ?b ?c . ?d ?e ?f . ?g ?h ?i . ?j ?x ?l }}",
           "sql": "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT count(*) FROM r WHERE n > {k}",
           "turtle": None}


def is_runaway(text: str) -> bool:
    return text.startswith(("SELECT (COUNT(*) AS ?n", "WITH RECURSIVE r(n)"))


def burst_texts(engine: str, reference: str, n: int, distinct: float, runaway: float, rng: random.Random) -> list[str]:
    """n texts for a burst: a share distinct (the reference with a LIMIT of its own), a share running
    into its budget (each its own), the rest a few common ones, right and wrong, again and again."""
    ref = reference.strip().rstrip(";")
    common = [ref, " ".join(ref.split()), ref.replace("SELECT", "select", 1),
              ref.replace("SELECT", "SELEC", 1),                          # a syntax error
              re.sub(r"\?(\w+)", r"?\1x", ref, count=1)]                   # a variable misspelt: another result
    texts = [RUNAWAY[engine].format(k=i) for i in range(round(n * runaway))] if RUNAWAY.get(engine) else []
    texts += [f"{ref} LIMIT {i + 1}" for i in range(round(n * distinct))]
    texts += [rng.choice(common) for _ in range(max(0, n - len(texts)))]
    rng.shuffle(texts)
    return texts[:n]


async def http_get(ws_url: str, path: str) -> tuple[int, float]:
    """GET path from the server ws_url names, as a phone's browser loads a file: (bytes, seconds)."""
    u = urllib.parse.urlsplit(ws_url)
    tls = u.scheme in ("wss", "https")
    t = time.perf_counter()
    reader, writer = await asyncio.open_connection(u.hostname, u.port or (443 if tls else 80),
                                                   ssl=ssl.create_default_context() if tls else None)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: {u.netloc}\r\nConnection: close\r\n\r\n".encode())
    await writer.drain()
    n = 0
    while chunk := await reader.read(1 << 16):
        n += len(chunk)
    writer.close()
    return n, time.perf_counter() - t


async def fanout(phones: list, done, sent: int, timeout: float = 30.0) -> tuple[int, int, int]:
    """Until every phone's state says done(phone): the last one's and the median's lag in ms, and how many."""
    seen: dict[int, int] = {}
    end = time.monotonic() + timeout
    while len(seen) < len(phones) and time.monotonic() < end:
        t = now_ms()
        for i, p in enumerate(phones):
            if i not in seen and done(p):
                seen[i] = t - sent
        await asyncio.sleep(0.01)
    lags = sorted(seen.values()) or [0]
    return lags[-1], lags[len(lags) // 2], len(seen)


async def drive_activity(args, deck: dict, key: str, phones: list, rng: random.Random):
    """--activity: open it as a presenter window does, the phones send their burst, close it, report."""
    aid = args.activity
    item = deck["items"]["activity"][aid]
    refs = Phone.references.get(aid) or []
    n = min(args.burst or len(phones), len(phones))
    texts = burst_texts(item["engine"], refs[0] if refs else "", n, args.distinct, args.runaway, rng)
    Phone.bursting = True
    async with websockets.connect(args.url, max_size=2**22) as stage:
        await stage.send(json.dumps({"t": "hello", "role": "stage", "key": key, "deck": deck["deck"],
                                     "bundle": deck["bundle"], "id": "hello"}))

        async def drain():
            async for text in stage:
                m = json.loads(text)
                if m["t"] == "error":
                    print("stage error:", m)
        reader = asyncio.create_task(drain())
        await asyncio.sleep(0.5)
        start = time.monotonic() + 1.0                      # every phone has seen the activity open by then
        for p, text in zip(rng.sample(phones, n), texts):
            u = rng.random()
            p.burst_text = text
            p.burst_at = start + args.within * (u ** (1 / 3) if args.deadline else u)
        sent = now_ms()
        await stage.send(json.dumps({"t": "activity.open", "activity": aid, "id": "open"}))
        last, median, count = await fanout(phones, lambda p: (p.state.get("activity") or {}).get("phase") == "open", sent)
        print(f"open: {count} phones after {last} ms (median {median} ms)", flush=True)
        end = start + args.within + args.wait
        while time.monotonic() < end:                      # the burst, then until every entry has its verdict
            if time.monotonic() > start + args.within and \
                    sum(1 for e in Phone.entries if "checked" in e or "refused" in e) >= n:
                break
            await asyncio.sleep(0.1)
        sent = now_ms()
        await stage.send(json.dumps({"t": "activity.close", "activity": aid, "id": "close"}))
        last, median, count = await fanout(phones, lambda p: (p.state.get("activity") or {}).get("phase") != "open", sent)
        print(f"close: {count} phones after {last} ms (median {median} ms)")
        reader.cancel()
    entries = Phone.entries
    statuses = Counter(e.get("status") or (f"refused ({e['refused']})" if "refused" in e else "no verdict")
                       for e in entries)
    print(f"entries: {len(entries)} sent within {args.within} s ({'most at the end' if args.deadline else 'evenly'}); "
          f"{len(set(texts))} distinct texts, {sum(1 for t in texts if is_runaway(t))} running into their budget")
    print(f"acknowledged: {percentiles([e['ack'] - e['sent'] for e in entries if 'ack' in e])}")
    print(f"checked - sent until the phone had its verdict: "
          f"{percentiles([e['checked'] - e['sent'] for e in entries if 'checked' in e])}")
    print("statuses:", dict(statuses.most_common()))


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path, nargs="?", help="the bundle folder (its deck.json gives the slides, its "
                                                          "keys.json the activities' references)")
    ap.add_argument("--pin", help="only phones: join this running game and answer whatever is asked "
                                  "(the lecturer drives it, e.g. from the host console)")
    ap.add_argument("--duration", type=float, default=600, help="with --pin: seconds to stay")
    ap.add_argument("--url", default="ws://localhost:8470/ws")
    ap.add_argument("--phone-url", help="the phones' address, if not --url (e.g. a tunnel's: the host stays local, "
                                        "like PowerPoint)")
    ap.add_argument("--key", help="presenter key (default: presenter-key in ~/.texstage, or ~/.texquiz)")
    ap.add_argument("--players", type=int, default=30)
    ap.add_argument("--prefix", default="Sim", help="with --pin: the phones' nicknames, <prefix>000 and on (another "
                                                     "simulation in the same game needs other names)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds on a reveal or leaderboard slide")
    ap.add_argument("--skip-after", type=float, default=6.0,
                    help="seconds after which the host skips a question not everybody has answered")
    ap.add_argument("--answer-window", type=float, default=4.0,
                    help="phones answer within this many seconds (smaller: a harder burst)")
    ap.add_argument("--activity", help="with the bundle: instead of the quiz, open this activity as a presenter "
                                       "window does, let the phones send a burst, close it and report (F0's runs)")
    ap.add_argument("--burst", type=int, help="with --activity: entries in the burst (default: one per phone)")
    ap.add_argument("--within", type=float, default=10.0, help="with --activity: seconds the burst takes")
    ap.add_argument("--deadline", action="store_true", help="with --activity: most entries in the last seconds")
    ap.add_argument("--distinct", type=float, default=0.3, help="with --activity: the share of distinct texts")
    ap.add_argument("--runaway", type=float, default=0.0,
                    help="with --activity: the share of texts that run into their budget")
    ap.add_argument("--wait", type=float, default=30.0,
                    help="with --activity: seconds after the burst to wait for the last verdicts")
    ap.add_argument("--fetch", help="a path every phone loads when it joins, e.g. /static/vendor/katex/katex.min.js")
    ap.add_argument("--join-within", type=float, default=0.0,
                    help="with the bundle: the phones join spread over this many seconds (default: all at once)")
    args = ap.parse_args()
    Phone.fetch = args.fetch
    rng = random.Random(args.seed)
    Phone.window = args.answer_window
    Phone.references = deck_references(args.bundle)
    phone_url = args.phone_url or args.url
    if args.pin:                                      # phones only: the lecturer drives the game
        stop = asyncio.Event()
        phones = [Phone(phone_url, args.pin, f"{args.prefix}{i:03d}", random.Random(rng.random())) for i in range(args.players)]
        tasks = [asyncio.create_task(p.run(stop)) for p in phones]
        await asyncio.sleep(2)
        failed = [t.exception() for t in tasks if t.done() and t.exception()]
        print(f"{args.players - len(failed)} phones in game {args.pin}" + (f"; {failed[0]}" if failed else ""), flush=True)
        await asyncio.sleep(args.duration)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"connections lost and taken up again: {len(Phone.drops)}")
        return
    deck = json.loads((args.bundle / "deck.json").read_text(encoding="utf-8"))
    data = Path.home() / ".texstage"
    if not data.exists() and (Path.home() / ".texquiz").is_dir():
        data = Path.home() / ".texquiz"                    # the data folder's name until 2026-10-10
    key = args.key or (data / "presenter-key").read_text().strip()
    async with websockets.connect(args.url, max_size=2**22) as host:
        await host.send(json.dumps({"t": "hello", "role": "host", "key": key, "deck": deck["deck"],
                                    "bundle": deck["bundle"], "id": "hello"}))
        host_state: dict = {}

        async def host_reader():
            async for text in host:
                m = json.loads(text)
                if m["t"] == "state":
                    host_state.update(m)
                elif m["t"] == "ok" and m.get("re") == "restart":
                    host_state["pin"] = m["pin"]
                elif m["t"] == "error":
                    print("host error:", m)
        reader = asyncio.create_task(host_reader())
        # a new game: the server keeps a deck's game running (the same lecture), so a second
        # simulation would otherwise meet the phones of the first
        await host.send(json.dumps({"t": "restart", "id": "restart"}))
        while "pin" not in host_state:
            await asyncio.sleep(0.05)
        pin = host_state["pin"]
        while host_state.get("session", {}).get("pin") != pin:
            await asyncio.sleep(0.05)
        stop = asyncio.Event()
        phones = [Phone(phone_url, pin, f"P{i:03d}", random.Random(rng.random())) for i in range(args.players)]
        t0 = time.perf_counter()

        async def later(p: Phone, delay: float):           # --join-within: as a class arrives
            await asyncio.sleep(delay)
            await p.run(stop)
        tasks = [asyncio.create_task(later(p, rng.uniform(0, args.join_within)) if args.join_within else p.run(stop))
                 for p in phones]
        report = time.monotonic() + 5
        while host_state.get("session", {}).get("connected", 0) < args.players:
            await asyncio.sleep(0.05)
            for t in tasks:
                if t.done() and t.exception():
                    raise t.exception()
            if time.monotonic() > report:                   # stalled: say how far it got
                report = time.monotonic() + 5
                print(f"  joining: {sum(1 for p in phones if p.state)} phones have a state, the host sees "
                      f"{host_state.get('session', {}).get('connected')} connected", flush=True)
        print(f"game {pin}: {args.players} phones joined in {time.perf_counter() - t0:.2f} s", flush=True)
        if args.fetch:
            until = time.monotonic() + 120
            while len(Phone.fetches) + len(Phone.fetch_failed) < args.players and time.monotonic() < until:
                await asyncio.sleep(0.1)
            print(f"{args.fetch} loaded by {len(Phone.fetches)} phones ({len(Phone.fetch_failed)} failed): "
                  f"{percentiles([round(1000 * s) for s in Phone.fetches])}", flush=True)
            if Phone.fetch_failed:
                print("  failures:", dict(Counter(Phone.fetch_failed).most_common(3)), flush=True)
        if args.activity:
            await drive_activity(args, deck, key, phones, rng)
            stop.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            reader.cancel()
            return
        fanout = []                                         # per slide: until the last phone had it
        for slide in deck["slides"]:
            phase, quiz = slide.get("phase"), slide.get("quiz")
            if phase not in ("question", "reveal", "answer", "leaderboard", "podium"):
                continue
            sent = now_ms()
            await host.send(json.dumps({"t": "slide", "slide": slide["id"], "id": f"s{slide['id']}"}))
            if phase == "question":
                target = None                               # the round itself (its get-ready screen)
            elif phase == "podium":
                await asyncio.sleep(args.pause)
                break
            else:
                target = "revealed"
            # wait until every phone has seen it, then until the question is closed
            while True:
                rid = host_state.get("rounds", {}).get(quiz, {}).get("id")
                seen = [p.seen.get(rid if target is None else f"{rid}:{target}") for p in phones] if rid else []
                if seen and all(seen):
                    break
                await asyncio.sleep(0.02)
            lag = [s - sent for s in seen]
            if max(lag) < 0:                                 # the reveal slide revealed it already
                line = f"{phase:11} {quiz:18} (revealed before)"
            else:
                fanout.append(max(lag))
                line = (f"{phase:11} {quiz:18} all {len(phones)} phones after {max(lag)} ms "
                        f"(median {statistics.median(lag):.0f})")
            if phase == "question":
                skip_at = time.monotonic() + args.skip_after
                while host_state["rounds"][quiz]["phase"] not in ("closed", "revealed"):
                    if time.monotonic() > skip_at:          # the lecturer stops waiting
                        await host.send(json.dumps({"t": "skip", "quiz": quiz, "id": f"skip-{quiz}"}))
                        skip_at = float("inf")
                    await asyncio.sleep(0.05)
                r = host_state["rounds"][quiz]
                line += f"; {r['results']['answered']} answers, then closed"
            else:
                await asyncio.sleep(args.pause)
            print(line)
        top = host_state["players"][:5]
        print("standings:", ", ".join(f"{p['rank']}. {p['nickname']} {p['score']}" for p in top))
        print(f"slides reached the last phone: {percentiles(fanout)}")
        print(f"answers, sent until accepted: {percentiles(Phone.rtts)}")
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        reader.cancel()


if __name__ == "__main__":
    asyncio.run(main())
