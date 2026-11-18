# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Serve live activities as texstage and its kinds are installed here, and have a phone's entries checked
(docs/architecture/activity-framework-plan-f2.md, package 11): a server of the core's activity type
(`texstage serve` - the core's is its default since package 14 -, on a free port of 127.0.0.1, with a key and
a data folder of its own) takes the decks, serves their kinds' files for the browser, and checks a phone's
entry of each activity in its pool's processes - each kind found by its entry point, there as where the
server runs.

    python maintenance/check_kinds_served.py                             # a deck of its own (below)
    python maintenance/check_kinds_served.py --bundles <folder> [--every]   # the built decks there (*.bundle)

Its own deck has an activity of each of texstage's kinds - a crowd graph, SQL, SPARQL, Turtle, a choice, a
number, a text -, made by texstage's build from the records LaTeX writes (build/activity.py: entries), without
LaTeX. Each activity is opened by the first slide that opens it; a phone sends the activity's first reference
as its kind takes a reference as an entry (Kind.reference) - without references a choice's first option, a
number, a text, a term per field of a crowd graph -, and the step is revealed. The activity passes when the
phone's own entry is checked with status ok and, where the deck has references, judged correct - and a crowd
graph's picture shows the terms it was sent (drawn); every kind the deck names must be served with its
texts, under the kinds' policy. A deck without live activities, an activity no slide opens and one whose
entry the check cannot make (a code activity without a reference, an input it does not know) are said and
passed over - unless --every, as for its own deck, which takes none of them; and something must be checked.
CI runs it in the server's image (deploy/Dockerfile) and with the installed wheels (check_installed.py). It
needs what texstage needs: websockets comes with uvicorn[standard]."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

SQL_SEED = ("CREATE TABLE packing (item TEXT, quantity INTEGER);\n"
            "INSERT INTO packing VALUES ('Apples',6),('Cups',6),('Blankets',2);")
TTL_SEED = '@prefix : <http://example.org/> .\n:rhine a :River ; :name "Rhine" .\n:elbe a :River ; :name "Elbe" .'
PROBE = (           # its own deck: id, kind, the kind's keys {key: items}, the seed, the references
    ("crowd", "triples", {"fields": ["Subject", "Predicate", "Object"]}, "", ()),
    ("packing", "sql-query", {}, SQL_SEED, ("SELECT item FROM packing WHERE quantity = 6;",)),
    ("rivers", "sparql-query", {}, TTL_SEED, ("SELECT ?name WHERE { ?r a :River ; :name ?name }",)),
    ("knows", "turtle-graph", {}, "@prefix ex: <http://example.org/> .", ("ex:alice ex:knows ex:bob .",)),
    ("colour", "choice", {"options": ["Red", "Green", "Blue"], "select": ["one"]}, "", ("Green",)),
    ("answer", "number", {}, "", ("42",)),
    ("language", "text", {}, "", ("SPARQL",)),
)
START_S = 90                    # the server's start, its first import of every kind included
CHECK_S = 180                   # an activity's references and its entry: a lecture's seed may be large
KEY_HEADER = "X-Texquiz-Key"
WAITING = ("received", "waiting")       # an entry's check as a phone sees it before there is one


def say(line: str) -> None:
    print(line, flush=True)


# ------------------------------------------------------------------ its own deck
def hexed(text: str) -> str:
    return text.encode("utf-8").hex()


def records(probe=PROBE) -> str:
    """The deck's activities as texactivity.sty records them in the .tqz (build/activity.py: read)."""
    lines = []
    for line, (aid, kind, options, seed, references) in enumerate(probe, 1):
        core = {"id": aid, "kind": hexed(kind), "input": "", "engine": "", "limit": hexed("3"), "open": "auto",
                "seed": "", "reference": "", "file": hexed("probe.tex"), "line": str(line), "gap": "", "time": "",
                "budget": "", "counts": "", "feedback": "", "projector": "", "solution": ""}
        lines.append("activity|" + "|".join(f"{k}={v}" for k, v in core.items()))
        for key, items in options.items():
            lines.append(f"activityoption|id={aid}|key={hexed(key)}|value={hexed(', '.join(items))}|"
                         f"items={''.join(hexed(i) + ',' for i in items)}")
        lines += [f"activityref|id={aid}|text={hexed(r)}" for r in references]
        if seed:
            lines.append(f"activityseed|id={aid}|text={hexed(seed)}")
    return "\n".join(lines) + "\n"


def probe_bundle(folder: Path, probe=PROBE) -> Path:
    """Its own deck in folder (probe.bundle), each activity on a slide of its own: the items, keys and files
    texstage's build makes of the records - each kind's build, its references run with the kind in a pool's
    process, deck.json's kinds as installed here; a slide's picture is a stand-in nobody looks at. (probe: a
    part of PROBE, for a test.)"""
    from texstage.build import activity, bundle
    from texstage.build.tqz import Tqz
    folder.mkdir(parents=True, exist_ok=True)
    source = folder.parent / "probe.tqz"
    source.write_text(records(probe), encoding="utf-8")
    try:
        acts = activity.entries(Tqz.read(source), folder.parent, {}, [])
    except activity.ActivityError as e:
        raise SystemExit(f"FAIL: its own deck does not build here - {e}") from None
    image = b"\x89PNG\r\n\x1a\nprobe"
    picture = f"slides/{hashlib.sha256(image).hexdigest()[:16]}.png"
    box = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
    slides = [{"id": 256, "image": picture},
              *({"id": 257 + i, "image": picture, "live": [{"type": "activity", "item": aid, "rects": {"box": box}}]}
                for i, aid in enumerate(acts.items)),
              {"id": 257 + len(acts.items), "image": picture}]
    deck = {"format": bundle.FORMAT, "deck": "probe", "name": "Probe", "language": "en", "types": ["activity"],
            "kinds": acts.kinds, "image": {"width": 1920, "height": 1080}, "slides": slides,
            "items": {"activity": acts.items}}
    keys = {"format": bundle.FORMAT, "deck": "probe", "items": {"activity": acts.keys}}
    deck["bundle"] = keys["bundle"] = bundle.bundle_id(deck, keys)
    bundle.write_bundle(folder / "probe.bundle", deck, keys, {picture: image, **acts.files})
    return folder


# ------------------------------------------------------------------ what is sent, what passes
def shown_on(deck: dict) -> dict[str, int]:
    """Each activity and the first slide that opens it - not one that reveals it (\\reveal<n>)."""
    out: dict[str, int] = {}
    for s in deck.get("slides", ()):
        for live in s.get("live", ()) or ():
            if live.get("type") == "activity" and live.get("phase") != "revealed":
                out.setdefault(live.get("item"), s["id"])
    return out


def entry_for(item: dict, keys: dict) -> tuple[dict | None, str]:
    """What a phone sends for the activity, and how to say it: its first reference as its kind takes a
    reference as an entry (Kind.reference) - or, without references, a choice's first option, a number, a
    text, a term per field of a crowd graph. None where the check cannot make one: a code activity without a
    reference, an input it does not know."""
    from texstage.activities.kind import Step
    from texstage.activities.play import kind_of
    kind = kind_of(item)
    references = keys.get("reference") or []
    if references:
        e = kind.reference(Step(item=item, keys=keys), references[0])
        sent = {name: list(value) if isinstance(value, tuple) else value
                for name, value in (("text", e.text), ("fields", e.fields), ("choice", e.choice), ("number", e.number))
                if value is not None}
        return (sent or None), "its first reference"
    fields = len(item.get("fields") or ()) or 3
    made = {"fields": ({"fields": [f":probe{i}" for i in range(fields)]}, f"{fields} terms"),
            "choice": ({"choice": [0]}, "its first option"), "number": ({"number": 1}, "a number"),
            "text": ({"text": "probe"}, "a text")}.get(kind.INPUT)
    return made if made is not None else (None, f"nothing: no reference, and its input is {kind.INPUT}")


def judged(entry: dict | None, referenced: bool) -> str | None:
    """Why the phone's own entry, as the phone has it after the reveal, does not pass - or None: checked with
    status ok, and judged correct where the deck has references."""
    if entry is None:
        return "the phone does not have its entry"
    if entry.get("check") != "checked":
        return f"its entry is {entry.get('check')!r}, not checked"
    if entry.get("status") != "ok":
        said = entry.get("message")
        return f"its entry's check says {entry.get('status')!r}" + (f" ({json.dumps(said)[:200]})" if said else "")
    if referenced and entry.get("verdict") != "correct":
        return f"its entry is judged {entry.get('verdict')!r}, not correct"
    return None


def drawn(picture: dict, sent: dict) -> str | None:
    """Why the activity's picture after the reveal - the lecturer's - does not show the terms the phone sent,
    or None. A crowd graph's is looked at (the other reductions count entries, which the entry's check stands
    for): its panel lists each term in its role - the first and the last a node, one between them a label -
    as sent, cleaned as texstage cleans a term; and where it draws a triple of one student (min 1, no review)
    it draws the phone's, an edge from its first term to its last labelled with the one between."""
    from texstage.checks.cleaning import Unfit, clean_term
    if picture.get("reduction") != "crowd" or "fields" not in sent:
        return None

    def cleaned(term) -> str:
        try:
            return clean_term(term)
        except Unfit:                                   # (the kind took it: as it was sent)
            return str(term)
    terms = [cleaned(t) for t in sent["fields"]]
    listed = {(t.get("role"), t.get("label")) for t in picture.get("terms") or ()}
    missing = [t for i, t in enumerate(terms) if ("node" if i in (0, len(terms) - 1) else "label", t) not in listed]
    if missing:
        return f"its picture lists no term {', '.join(missing)} of those the phone sent"
    if (picture.get("min") or 1) > 1 or picture.get("review"):
        return None                                     # (one student's triple is not drawn, as it should not be)
    label = {n.get("id"): n.get("label") for n in picture.get("nodes") or ()}
    between = terms[1] if len(terms) == 3 else ""
    if not any((label.get(e.get("s")), e.get("label") or "", label.get(e.get("o"))) == (terms[0], between, terms[-1])
               for e in picture.get("edges") or ()):
        return f"its picture draws no edge from {terms[0]} to {terms[-1]}" + (f" labelled {between}" if between else "")
    return None


def files_fault(named, kind_files: dict) -> str | None:
    """Why the kinds' files a page is told of (the welcome's kindFiles) do not do - or None: every kind the deck
    names has its files for the browser, its texts among them."""
    for name in sorted(named):
        files = kind_files.get(name)
        if not files or not files.get("phone"):
            return f"the kind {name} has no files for the browser"
        if not any(path.startswith("texts/") for path in files["phone"]):
            return f"the kind {name}'s files for the browser have no texts"
    return None


# ------------------------------------------------------------------ the server
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def command() -> list[str]:
    """The installed console, as a lecturer runs it - or texstage's main where there is none."""
    console = Path(sys.executable).with_name("texstage.exe" if os.name == "nt" else "texstage")
    if console.is_file():
        return [str(console)]
    return [sys.executable, "-c", "import sys; from texstage.cli import main; sys.exit(main())"]


class Server:
    """texstage serve with its default type, the core's, its output in a file (UTF-8); stopped as a lecturer stops it
    (Ctrl+Break, SIGTERM - or, where there is no console to send Ctrl+Break in, ended), and whatever of its
    processes is left after that ended."""

    def __init__(self, bundles: Path, scratch: Path):
        self.port, self.key = free_port(), secrets.token_urlsafe(24)
        self.url = f"http://127.0.0.1:{self.port}"
        self.log = scratch / "server.log"
        env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "TEXINPUTS")}
        env["PYTHONUTF8"] = "1"
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with open(self.log, "wb") as out:                # (--key=: one key in 64 starts with "-", an option's look)
            self.proc = subprocess.Popen(
                [*command(), "serve", str(bundles), "--data", str(scratch / "data"), "--host", "127.0.0.1",
                 "--port", str(self.port), f"--key={self.key}", "--no-tunnel"],
                stdout=out, stderr=subprocess.STDOUT, env=env, creationflags=flags)

    def get(self, path: str, key: bool = False):
        """status, headers (their names in any case), body."""
        request = urllib.request.Request(self.url + path, headers={KEY_HEADER: self.key} if key else {})
        with urllib.request.urlopen(request, timeout=10) as r:
            return r.status, r.headers, r.read()

    def started(self) -> dict:
        deadline = time.monotonic() + START_S
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                self.fail(f"the server ended at its start ({self.proc.returncode})")
            try:
                return json.loads(self.get("/api/status")[2])
            except (OSError, ValueError):
                time.sleep(0.5)
        self.fail(f"the server did not answer within {START_S} s")

    def tail(self, lines: int = 80) -> str:
        try:
            return "\n".join(self.log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
        except OSError:
            return "(no output)"

    def fail(self, why: str):
        tail = self.tail()                              # (as it was: stopping adds its own lines)
        self.stop()
        raise SystemExit(f"FAIL: {why}\n--- the server's output, its end:\n{tail}")

    def stop(self) -> None:
        if self.proc.poll() is not None:
            return
        try:
            import psutil
            family = psutil.Process(self.proc.pid).children(recursive=True)
        except Exception:                                # (no psutil, or it ended meanwhile)
            family = []
        try:
            self.proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        except OSError:                                  # (no console to send Ctrl+Break in)
            self.proc.terminate()
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(10)
        for p in family:
            try:
                p.kill()
            except Exception:
                pass


# ------------------------------------------------------------------ a window, a phone
class Socket:
    """A WebSocket of the server's protocol, open while the stack is: what comes while an answer is waited
    for is put aside for the next one that asks - a check's push may come before an entry's answer."""

    def __init__(self, server: Server, stack: contextlib.ExitStack):
        self.ws = stack.enter_context(connect(server.url.replace("http", "ws", 1) + "/ws", open_timeout=15,
                                              max_size=None))
        self.aside: list[dict] = []
        self.n = 0

    def send(self, **message) -> None:
        self.ws.send(json.dumps(message))

    def recv(self, t: str | tuple, until=lambda m: True, timeout: float = 30) -> dict:
        types = (t,) if isinstance(t, str) else t
        for i, m in enumerate(self.aside):
            if m.get("t") in types and until(m):
                return self.aside.pop(i)
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no {'/'.join(types)} as waited for within {timeout:g} s")
            m = json.loads(self.ws.recv(timeout=left))
            if m.get("t") in types and until(m):
                return m
            self.aside = (self.aside + [m])[-300:]

    def ask(self, t: str, **message) -> dict:
        self.n += 1
        n = self.n
        self.send(t=t, id=n, **message)
        return self.recv(("ok", "error"), lambda m: m.get("re") == n)


def own(m: dict, activity: str, entry: str) -> dict | None:
    """The phone's own entry in a state it was sent - of the activity's step - or None."""
    mine = (m.get("activity") or {}).get("mine") or {}
    if mine.get("activity") != activity:
        return None
    return next((e for e in mine.get("entries") or () if e.get("id") == entry), None)


# ------------------------------------------------------------------ a deck
def served(server: Server, folder: Path, every: bool) -> tuple[list[str], int, int, list[str]]:
    """One deck: the presenter's window, a phone, each activity opened, an entry of it sent, checked and
    revealed - what was done, the deck's activities, how many were checked, what was passed over."""
    from texstage.activities import registry
    from texstage.activities.play import kind_of
    deck = json.loads((folder / "deck.json").read_text(encoding="utf-8"))
    keys = json.loads((folder / "keys.json").read_text(encoding="utf-8"))
    bid, name = deck["bundle"], deck["deck"]
    items = (deck.get("items") or {}).get("activity") or {}
    secret = (keys.get("items") or {}).get("activity") or {}
    if not items:
        if every:
            server.fail(f"{name}: the deck has no live activity - nothing to check")
        return ["  no live activity: passed over"], 0, 0, [f"{name} (no activity)"]
    listed = json.loads(server.get("/api/decks", key=True)[2])
    if bid not in {d["bundle"] for d in listed}:
        server.fail(f"the server did not take the deck {name} ({folder.name})")
    kinds = {a: kind_of(item) for a, item in items.items()}
    found = {f.name: f.package for f in registry.found()}
    lines, checked, skipped = [], 0, []
    with contextlib.ExitStack() as stack:
        stage = Socket(server, stack)
        stage.send(t="hello", role="stage", key=server.key, deck=name, bundle=bid, id=0)
        welcome = stage.recv(("welcome", "error"))
        if welcome["t"] != "welcome":
            server.fail(f"{name}: the presenter's window was refused: {welcome}")
        files = welcome.get("kindFiles") or {}
        fault = files_fault({k.NAME for k in kinds.values()}, files)
        if fault:
            server.fail(f"{name}: {fault}")
        for kind in sorted({k.NAME for k in kinds.values()}):
            paths = [*files[kind]["phone"], *files[kind]["window"]]
            for path in paths:
                status, headers, _ = server.get(f"/kinds/{files[kind]['hash']}/{path}")
                if status != 200 or "default-src 'none'" not in headers.get("Content-Security-Policy", ""):
                    server.fail(f"{name}: the kind {kind}'s file {path}: {status}, policy "
                                f"{headers.get('Content-Security-Policy')!r}")
            lines.append(f"  the kind {kind}: {len(paths)} files for the browser, its texts among them")
        phone = Socket(server, stack)
        phone.send(t="join", pin=welcome["pin"], nickname="Probe", id="j")
        phone.recv("welcome")
        shown = shown_on(deck)
        for n, (activity, item) in enumerate(items.items(), 1):
            kind = kinds[activity]
            package = (deck.get("kinds") or {}).get(kind.NAME, {}).get("package") or found.get(kind.NAME, "?")
            head = f"  {activity} ({kind.NAME}, {package}): "
            sent, how = entry_for(item, secret.get(activity) or {})
            if activity not in shown or sent is None:
                why = "no slide opens it" if activity not in shown else f"the check sends it {how}"
                lines.append(head + f"passed over - {why}")
                skipped.append(f"{name}: {activity}")
                continue
            referenced = bool((secret.get(activity) or {}).get("reference"))
            if stage.ask("slide", slide=shown[activity])["t"] != "ok":
                server.fail(f"{name}: slide {shown[activity]} was refused")
            stage.ask("activity.open", activity=activity)           # (open=manual; refused if it is open)
            phone.recv("activity.step", lambda m: (m.get("step") or {}).get("activity") == activity
                       and m["step"].get("phase") == "open")
            entry = f"probe-{n:04d}-{secrets.token_hex(4)}"
            got = phone.ask("activity.enter", activity=activity, entry=entry, **sent)
            if got["t"] != "ok":
                server.fail(f"{name}: {activity}'s entry was refused: {got}")
            deadline = time.monotonic() + CHECK_S
            while True:                                 # the pool's answer, as the lecturer's panel counts it
                pic = stage.ask("activity.view", activity=activity)["picture"]
                if pic.get("checked", 0) >= 1 or pic.get("unchecked", 0) or time.monotonic() > deadline:
                    break
                time.sleep(0.2)
            if stage.ask("activity.reveal", activity=activity)["t"] != "ok":
                server.fail(f"{name}: {activity} could not be revealed")
            try:                                        # the phone's own entry, as the reveal tells it
                state = phone.recv("state", lambda m: (lambda e: e is not None and e.get("check") not in WAITING
                                                       and (not referenced or "verdict" in e))(own(m, activity, entry)))
                mine = own(state, activity, entry)
            except TimeoutError:
                mine = next((own(m, activity, entry) for m in reversed(phone.aside)
                             if own(m, activity, entry) is not None), None)
            fault = judged(mine, referenced)
            if fault:
                server.fail(f"{name}: {activity}: {fault}")
            pic = stage.ask("activity.view", activity=activity)["picture"]       # the lecturer's, revealed
            fault = drawn(pic, sent)
            if fault:
                server.fail(f"{name}: {activity}: {fault}")
            lines.append(head + f"{how} - checked, ok" + (", judged correct" if referenced else "")
                         + (", in its picture" if pic.get("reduction") == "crowd" else ""))
            checked += 1
    if every and skipped:
        server.fail(f"{name}: not every activity was checked - passed over: {', '.join(skipped)}")
    return lines, len(items), checked, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bundles", type=Path, help="a folder of built decks (*.bundle) - by default a deck of its own")
    ap.add_argument("--every", action="store_true",
                    help="every deck must have activities and every activity be checked (so for its own deck)")
    args = ap.parse_args()
    every = args.every or args.bundles is None
    with tempfile.TemporaryDirectory(prefix="texstage-served-", ignore_cleanup_errors=True) as tmp:
        scratch = Path(tmp)
        bundles = args.bundles.resolve() if args.bundles else probe_bundle(scratch / "bundles")
        decks = sorted(p for p in bundles.glob("*.bundle") if (p / "deck.json").is_file())
        if not decks:
            raise SystemExit(f"FAIL: no built deck (*.bundle) in {bundles}")
        server = Server(bundles, scratch)
        activities = checked = 0
        skipped: list[str] = []
        try:
            status = server.started()
            if status.get("activities") != "core":
                server.fail(f"the server runs the activity type {status.get('activities')!r}, not the core's - "
                            "a server's default")
            for folder in decks:
                say(f"{folder.name}:")
                lines, total, done, passed = served(server, folder, every)
                for line in lines:
                    say(line)
                activities, checked, skipped = activities + total, checked + done, skipped + passed
            if not checked:
                server.fail("no activity was checked")
        except SystemExit:
            raise
        except Exception as e:                           # (a dropped socket, a message not as expected, ...)
            server.fail(f"{type(e).__name__}: {e}")
        finally:
            server.stop()
    say(f"PASS: a server of the core's type took {len(decks)} deck(s), served their kinds' files and checked a "
        f"phone's entry of {checked} of their {activities} activities in its pool"
        + (f"; passed over: {', '.join(skipped)}" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
