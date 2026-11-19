# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Whether the core's activity type gives F1's groups for the same entries (F2's package 13; the plan of F2,
4.11): two servers of the load runs' bundle (bundle.py, with a crowd graph besides) - one of F1's type, one of
the core's -, and to each, as phones send them, the same made-up entries: to each code activity students who
send one to three texts - the reference in other spellings and with comments, the usual mistakes, syntax
errors, one that runs into its budget, a mistake often corrected -, to the crowd graph triples in other
spellings, and the lecturer merging and hiding some. Then both servers' pictures - the panel's and the
projector's, open, closed and revealed, and the one archived - compared: the groups, their statuses, counts,
reference marks and order; a crowd graph's nodes, edges and terms.

    python tools/load/groups.py <scratch> [part of an activity's name] [--lecture <the KG lecture's folder>]

Not compared, as they differ by design (package 13, 2026-11-18): a group's example - the core shows the form
most of its entries normalize to, without comments; F1 its earliest text as typed -; a crowd graph's count of
entries - a triple sent again in another spelling is an entry again in the core, F1 refuses it as sent
already; its students are counted alike -; the phones' own lists. Nor the order of groups of the same count,
which is said apart: F1 orders them by their raw key, the core puts those that are ok first - and so the
projector's few may end at another one of them.

The servers are this python's texstage, on 127.0.0.1 at --port and the next, each with a data folder in the
scratch folder and a key made here. Exit 0: the same groups; 1: what differs, printed and in groups.json.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import io
import json
import random
import re
import secrets
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import websockets

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GAP_S = {"tuple": 2.4, "code": 5.4}             # between a phone's entries: more than either type asks for
TYPES = ("f1", "core")


def tool(path: Path):
    spec = importlib.util.spec_from_file_location(f"load_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sim, run, load_bundle = tool(ROOT / "tools" / "simulate.py"), tool(HERE / "run.py"), tool(HERE / "bundle.py")


# ------------------------------------------------------------------ the made-up entries
def texts(engine: str, ref: str) -> list[str]:
    """What students send for a reference: the same in other spellings and with comments, other results, errors."""
    ref = ref.strip()
    one = " ".join(ref.split())
    if engine == "turtle":
        made = sim.turtle_answers(ref)
        prefix = (re.search(r"([A-Za-z][\w-]*):", ref) or re.search("(x)", "x")).group(1)
        return [*made["right"], one, f"# Berlin, in Turtle\n{ref}", f"{ref}  # done", *made["wrong"],
                re.sub(r"\d+", lambda m: str(int(m.group(0)) + 1), ref, count=1), f"{ref}\n{prefix}:x {prefix}:p {prefix}:o ."]
    comment = "#" if engine == "sparql" else "--"
    bare = ref.rstrip(";")
    out = [ref, one, ref.replace("SELECT", "select", 1).replace("WHERE", "where", 1), f"{comment} my answer\n{ref}",
           f"{bare} LIMIT 1", ref.replace("SELECT", "SELEC", 1), f"{comment} I do not know",
           sim.RUNAWAY[engine].format(k=0)]
    if engine == "sparql":
        return out + [re.sub(r"\?(\w+)", r"?\1x", ref, count=1), "SELECT * WHERE { ?s ?p ?o }", f"{ref} }}",
                      "SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }"]
    return out + [bare, "SELECT item FROM packing", "SELECT * FROM packing WHERE quantity = 6",
                  "SELECT item FROM packing WHERE quantity = 2", "SELECT item FROM packin WHERE quantity = 6"]


def corpus(aid: str, item: dict, refs: list[str], rng: random.Random, students: int = 30) -> dict:
    """Students' entries for one activity, in rounds - each one's first, then their second, ... (package 13's): to a
    code activity one to three texts, every one of them at least once, a wrong one often corrected; to a crowd
    graph their own triple and one to three more, some in other spellings, now and then their own again with
    spaces (F1: sent already) - and the lecturer's acts on it."""
    players = [f"S{i + 1:02d}" for i in range(students)]
    rounds: list[list[dict]] = []

    def send(k: int, player: str, entry: dict):
        while len(rounds) <= k:
            rounds.append([])
        rounds[k].append({"player": player, "input": entry})
    if item["input"] == "tuple":
        spell = [lambda t: t, str.lower, lambda t: f" {t} ", lambda t: t.upper() if t.startswith(":K") else t]
        for p in players:
            mine = [(f":{p}", ":attends", ":KG")] + rng.sample(sim.TRIPLES, rng.randint(1, 3))
            for k, t in enumerate(mine):
                send(k, p, {"fields": [(rng.choice(spell) if rng.random() < 0.4 else spell[0])(x) for x in t]})
            if rng.random() < 0.15:
                send(len(mine), p, {"fields": [f"{x} " for x in mine[0]]})
        acts = [{"act": "merge", "term": ":decker", "into": ":Decker"},
                {"act": "merge", "term": ":StefanDecker", "into": ":Decker"}, {"act": "hide", "term": ":RFD"}]
        return {"activity": aid, "players": players, "rounds": rounds, "acts": acts, "reveal": False}
    pool = texts(item["engine"], refs[0])
    right = pool[:4]
    for i, p in enumerate(players):
        first = pool[i] if i < len(pool) else rng.choice(pool)
        send(0, p, {"text": first})
        if first not in right and rng.random() < 0.7:
            send(1, p, {"text": rng.choice(pool)})
            if rng.random() < 0.3:
                send(2, p, {"text": rng.choice(right)})
    return {"activity": aid, "players": players, "rounds": rounds, "acts": [], "reveal": True}


# ------------------------------------------------------------------ playing them
class Socket:
    """One connection: messages with ids and their answers; the latest state; the welcome."""

    def __init__(self, ws):
        self.ws, self.n, self.waiting, self.state, self.welcome = ws, 0, {}, None, None
        self.task = asyncio.create_task(self.read())

    async def read(self):
        async for text in self.ws:
            m = json.loads(text)
            if m["t"] in ("ok", "error") and m.get("re") in self.waiting:
                self.waiting.pop(m["re"]).set_result(m)
            elif m["t"] == "welcome":
                self.welcome = m
            elif m["t"] == "state":
                self.state = m

    async def ask(self, t: str, timeout: float = 30.0, **msg) -> dict:
        self.n += 1
        fut = asyncio.get_running_loop().create_future()
        self.waiting[f"m{self.n}"] = fut
        await self.ws.send(json.dumps({"t": t, "id": f"m{self.n}", **msg}))
        return await asyncio.wait_for(fut, timeout)

    async def until(self, ok, timeout: float = 30.0):
        end = time.monotonic() + timeout
        while not (self.welcome is not None and ok(self)):
            if time.monotonic() > end:
                raise TimeoutError("the server did not get there")
            await asyncio.sleep(0.02)


async def play(which: str, url: str, key: str, deck: dict, c: dict) -> dict:
    """One corpus on one server: a game of its own, the activity opened, the phones' entries, every check back, the
    lecturer's acts; the panel's and the projector's pictures open, closed and revealed; the archive's."""
    aid, core = c["activity"], which == "core"
    crowd = deck["items"]["activity"][aid]["input"] == "tuple"
    out: dict = {"refused": 0, "acts": [], "pictures": {}}
    hello = {"key": key, "deck": deck["deck"], "bundle": deck["bundle"], "id": "hello"}
    async with websockets.connect(url, max_size=2**23) as w1, websockets.connect(url, max_size=2**23) as w2:
        stage, display = Socket(w1), Socket(w2)
        await w1.send(json.dumps({"t": "hello", "role": "stage"} | hello))
        await stage.until(lambda s: s.state is not None)
        pin = (await stage.ask("restart"))["pin"]
        await stage.until(lambda s: (s.state or {}).get("session", {}).get("pin") == pin)
        game = stage.state["session"]["id"]
        await w2.send(json.dumps({"t": "hello", "role": "display"} | hello))
        await display.until(lambda s: s.state is not None)
        assert (await stage.ask("activity.open", activity=aid))["t"] == "ok"
        phones = {name: Socket(await websockets.connect(url, max_size=2**23)) for name in c["players"]}
        for name, p in phones.items():
            await p.ws.send(json.dumps({"t": "join", "pin": pin, "nickname": name, "id": "join"}))
        for p in phones.values():
            await p.until(lambda s: s.welcome is not None)
        n = 0
        for r, entries in enumerate(c["rounds"]):
            if r:
                await asyncio.sleep(GAP_S["tuple" if crowd else "code"])
            for e in entries:                                            # one after the other: the same order on both
                n += 1
                p = phones[e["player"]]
                got = await (p.ask("activity.enter", activity=aid, entry=f"{e['player']}-entry-{n:04d}", **e["input"])
                             if core else p.ask("activity.send", activity=aid, **e["input"]))
                out["refused"] += got["t"] == "error"
        end = time.monotonic() + 60
        while time.monotonic() < end:                                    # every check back
            pic = await picture(stage, aid, "stage")
            if not pic.get("waiting") and (crowd or not core or pic.get("checked", 0) + pic.get("unchecked", 0)
                                           >= pic.get("entries", 0)):
                break
            await asyncio.sleep(0.2)
        for act in c["acts"]:
            if core:
                msg = {"act": act["act"], "role": "node", "group": act["term"]} | {k: act[k] for k in ("into",) if k in act}
                got = await stage.ask("activity.moderate", activity=aid, **msg)
            else:
                msg = {"role": "node", "term": act["term"]} | {k: act[k] for k in ("into",) if k in act}
                got = await stage.ask(f"activity.{act['act']}", activity=aid, **msg)
            out["acts"].append(got["t"])
        await asyncio.sleep(0.6)

        async def shot(when: str):
            for window, ws in (("stage", stage), ("display", display)):
                out["pictures"][f"{when}, {'panel' if window == 'stage' else 'projector'}"] = await picture(ws, aid, window)
        await shot("open")
        await stage.ask("activity.close", activity=aid)
        await asyncio.sleep(0.6)
        await shot("closed")
        if c["reveal"]:
            out["reveal"] = (await stage.ask("activity.reveal", activity=aid))["t"]
            await asyncio.sleep(0.8)
            await shot("revealed")
        for p in phones.values():
            await p.ws.close()
    request = urllib.request.Request(f"{url.replace('ws://', 'http://').removesuffix('/ws')}/api/archive/{game}.zip",
                                     headers={"X-Texquiz-Key": key})
    with urllib.request.urlopen(request, timeout=30) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    name = f"activity-{aid}.json"
    out["pictures"]["archived"] = json.loads(z.read(name).decode("utf-8-sig")) if name in z.namelist() else {}
    return out


async def picture(ws: Socket, aid: str, window: str) -> dict:
    reply = await ws.ask("activity.view", activity=aid, **({"window": "display"} if window == "display" else {}))
    return reply.get("picture") or {"error": reply.get("message") or reply.get("code")}


# ------------------------------------------------------------------ comparing them
def view(pic: dict) -> dict:
    """What of a picture is compared: a crowd graph's nodes, edges and terms; else the groups - F1's clusters by
    the core's group ids (store.gid) - with status, count and reference mark, their order, the students beyond."""
    from texstage.activities.store import gid
    if pic.get("kind") == "graph":
        return {"nodes": {n["id"]: (n["label"], n["n"], bool(n.get("literal"))) for n in pic.get("nodes", [])},
                "edges": {(e["s"], e.get("p"), e["o"]): (e.get("label"), e["n"]) for e in pic.get("edges", [])},
                "terms": {(t["role"], t["key"]): (t["label"], t["n"], t["hidden"], t["approved"], t.get("into"))
                          for t in pic.get("terms", [])},
                "node order": [n["id"] for n in pic.get("nodes", [])], "more": pic.get("more"), "min": pic.get("min"),
                "students": pic.get("students")}
    if pic.get("kind") == "clusters":                                    # F1's
        listed = [(gid(s, c["key"] if s == "ok" else None), {"status": s, "n": c["n"], "reference": c["reference"]})
                  for c in pic.get("clusters", []) for s in [{"syntax": "invalid"}.get(c["status"], c["status"])]]
        entries = pic.get("count")
    else:
        listed = [(g["id"], {"status": g["status"], "n": g["n"], "reference": g["reference"]}) for g in pic.get("groups", [])]
        entries = pic.get("entries")
    return {"groups": dict(listed), "order": [g for g, _ in listed], "others": pic.get("others", 0),
            "students": pic.get("students"), "entries": entries}


def differ(a: dict, b: dict) -> tuple[list[str], bool]:
    """What differs between F1's view (a) and the core's (b), in words - and whether groups of the same count
    came in another order (by design: F1 by raw key, the core ok first), at the projector's end of its few too."""
    out, ties = [], False
    for part in a:
        x, y = a[part], b.get(part)
        if part == "groups":
            last = {w: min((v["n"] for v in g.values()), default=0) for w, g in (("F1", x), ("core", y))}
            for g in sorted(set(x) | set(y)):
                gx, gy = x.get(g), y.get(g)
                if gx is None or gy is None:                              # listed by one: a tie at the end of the few?
                    have, by = (gx, "F1") if gy is None else (gy, "core")
                    if a["others"] and b["others"] and have["n"] == last[by]:
                        ties = True
                    else:
                        out.append(f"group {g} ({have['status']}, {have['n']}) only in {by}'s")
                    continue
                out += [f"group {g} ({gx['status']}): {k} {gx[k]!r} in F1's, {gy[k]!r} in the core's"
                        for k in ("status", "n", "reference") if gx[k] != gy[k]]
        elif part == "order":
            nx, ny = [a["groups"][g]["n"] for g in x], [b["groups"][g]["n"] for g in y]
            if nx != ny:
                out.append(f"the groups' counts in order: {nx} in F1's, {ny} in the core's")
            elif x != y:
                ties = True
        elif isinstance(x, dict):
            out += [f"{part} {k!r}: {x.get(k)!r} in F1's, {(y or {}).get(k)!r} in the core's"
                    for k in sorted(set(x) | set(y or {}), key=repr) if x.get(k) != (y or {}).get(k)]
        elif x != y:
            out.append(f"{part}: {x!r:.300} in F1's, {y!r:.300} in the core's")
    return out, ties


def report(got: dict) -> tuple[list[str], list[str]]:
    """What differs between the two servers' plays of a corpus; and the pictures whose ties came in another order."""
    a, b = got["f1"], got["core"]
    out, ties = [], []
    if a["acts"] != b["acts"] or a.get("reveal") != b.get("reveal"):
        out.append(f"the lecturer's acts: {a['acts']} {a.get('reveal')} in F1's, {b['acts']} {b.get('reveal')} in the core's")
    for name, pa in a["pictures"].items():
        pb = b["pictures"].get(name, {})
        if "error" in pa or "error" in pb:
            out.append(f"{name}: {pa.get('error')} in F1's, {pb.get('error')} in the core's")
            continue
        found, tie = differ(view(pa), view(pb))
        out += [f"{name}: {x}" for x in found]
        if tie:
            ties.append(name)
    return out, ties


# ------------------------------------------------------------------ the two servers
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scratch", type=Path)
    ap.add_argument("part", nargs="?", default="", help="only the activities whose name has this")
    ap.add_argument("--port", type=int, default=8483, help="F1's server's port; the core's is the next")
    ap.add_argument("--lecture", type=Path, help="the KG lecture's folder: its SPARQL and Turtle activities")
    ap.add_argument("--students", type=int, default=30)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    bundles = scratch / "bundles"
    load_bundle.make(bundles / "groups.bundle", args.lecture, crowd=True)
    deck = json.loads((bundles / "groups.bundle" / "deck.json").read_text(encoding="utf-8"))
    refs = sim.deck_references(bundles / "groups.bundle")
    rng = random.Random(args.seed)
    corpora = [corpus(aid, item, refs.get(aid) or [""], rng, args.students)
               for aid, item in deck["items"]["activity"].items() if args.part in aid and aid != "sparql-big"]
    key = "groups-" + secrets.token_hex(12)
    servers, results, differences = {}, {}, 0
    try:
        for i, which in enumerate(TYPES):
            more = argparse.Namespace(port=args.port + i, key=key, checks="server", activities=which, more=[],
                                      tunnel=None, workers=2)
            servers[which] = run.Server(bundles, scratch / f"data-{which}", scratch / f"server-{which}.log", more, True)
            if servers[which].served != which:
                raise SystemExit(f"the server at {args.port + i} runs {servers[which].served}, not {which}")
        for c in corpora:
            got = {which: asyncio.run(play(which, f"ws://127.0.0.1:{args.port + i}/ws", key, deck, c))
                   for i, which in enumerate(TYPES)}
            found, ties = report(got)
            differences += len(found)
            entries = sum(map(len, c["rounds"]))
            results[c["activity"]] = {"differences": found, "ties in another order": ties, "got": got}
            print(f"== {c['activity']}: {len(c['players'])} students, {entries} entries (refused: F1 {got['f1']['refused']}, "
                  f"the core {got['core']['refused']}): {len(found)} differences"
                  + (f"; groups of the same count in another order in {len(ties)} pictures" if ties else "")
                  + "".join(f"\n   {x}" for x in found[:40]), flush=True)
    finally:
        usage = {which: s.stop() for which, s in servers.items()}
    out = scratch / "groups.json"
    out.write_text(json.dumps({"results": results, "pools": usage}, indent=1, ensure_ascii=False, default=str),
                   encoding="utf-8")
    sick = {which: why for which, u in usage.items() if (why := run.pool_faults(u))}
    print(f"\n{differences} differences in {len(results)} activities" + (f"; the pools: {sick}" if sick else "")
          + f" - {out}")
    return 1 if differences or sick else 0


if __name__ == "__main__":
    sys.exit(main())
