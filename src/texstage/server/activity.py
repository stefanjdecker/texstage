# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The live activity on the server (docs/live-activities-design.md, section 7; the registry:
types.py).

While an activity is open the phones send contributions; the server keeps them and reduces them
to the activity's picture, which the texstage windows draw - and runs nothing:

    crowd     (input=tuple) a contribution is a tuple of terms - a triple. A term counts as written
              (terms=exact, the default: as RDF compares IRIs, :kg and :KG are two) or as the word
              cloud groups answers (terms=loose: case, accents and spaces do not count); the
              lecturer merges a term into another, per role (node: the first and the last field;
              label: the ones between). The picture: the triples with at least `min` students, without hidden
              terms (with `review` only approved ones), the 40 nodes with the most students.
    clusters  (input=code) a contribution is a query - or, engine=turtle, a graph in Turtle. Every
              distinct text is checked, which gives its key - the hash of the result's canonical
              form - or its status (syntax, error, timeout, refused; internal: the server could not
              check it, never the student's fault): by the server's pool as the text comes
              (checking.py, the mode server), or by the presenter window with the lease (one at a
              time: activity.work; the mode browser, and both, where the pool checks too and the
              differences are written down); a student's latest query counts; the picture: the
              queries grouped by key, the largest first, the reference's marked (in the presenter
              window at once, everywhere after the reveal).

An `internal` check is never the text's doing - its error, which no phone sees, says why -, and the
next start of the server checks it again (restarted), unless the pool set the text aside, since it
ended two of its processes (its error begins SET_ASIDE): then the same text again is internal at once.

State in the session (stage["activity"]): {"current": the activity the phones show, "items": {id:
{phase: ready|open|closed, version (of the picture), layout, students, count, waiting, unchecked
(internal), revealed, min, merges [[role, term, into]], hidden [term], approved [term] | shown (a
cluster's key), refs [the references' keys]}}}; every window's view leaves out the lists and refs. An activity opens
when its frame comes to the projector (open=auto) or by the lecturer, closes when the projector
leaves the frame or by the lecturer; one is open at a time. Tables: contributions, results (one
row per distinct result). The phones' view: the current activity while it is open or revealed -
its input, prompt, the deck's suggestions and the terms the projector shows, a query's engine and
tokens, the phone's own contributions; before the reveal a query's state only (runs - for Turtle:
valid -, syntax error), never its result.
No view names anybody: a contribution's player is kept for the phone's own list and for blocking.
"""
from __future__ import annotations

import copy
import html
import json
import math
import re
import secrets
import time
from collections import Counter
from dataclasses import dataclass, field

from texstage.checks import cleaning
from texstage.checks.cleaning import TERM_MAX, TEXT_MAX, is_literal, norm_term, term_key  # noqa: F401 - the type's names
from texstage.engines import ENGINES
from texstage.server import sheets
from texstage.server.types import Refused

NAME = "activity"
MESSAGES = ("activity.open", "activity.close", "activity.reveal", "activity.merge", "activity.unmerge",
            "activity.hide", "activity.approve", "activity.min", "activity.block", "activity.show",
            "activity.view", "activity.work", "activity.result", "activity.layout")
READS = ("activity.view", "activity.work")
QUIET = ("activity.result", "activity.layout")             # one per query, two a second: the windows soon
PLAYER_MESSAGES = ("activity.send", "activity.withdraw")
FILE_TYPES = {suffix: mime for e in ENGINES.values() for suffix, mime in e["seed"].items()}
FILES = r"data/[0-9a-f]{16}(?:" + "|".join(map(re.escape, FILE_TYPES)) + ")"     # a query's seed (build/activity.py)
ARCHIVE = r"activity-[a-z0-9-]+\.(?:json|svg)"           # (its CSV: the archive takes any [a-z0-9-]+.csv)

GAP_MS = {"tuple": 2000, "code": 5000}
PER_ACTIVITY = 5000
RESULTS_MAX = 500                   # distinct results of an activity
NODES_SHOWN = 40                    # more labels than this do not fit apart in a slide's box
CLUSTERS_SHOWN = 8
SUGGEST_MAX = 50
JOBS = 20                           # inputs per activity.work
LEASE_MS = 15_000
SUMMARY_MAX = 12 * 1024
ERROR_MAX = 300
STATUSES = ("ok", "syntax", "error", "timeout", "refused")    # what the presenter window's evaluator sends
CHECKED = (*STATUSES, "internal")   # and the server's pool (checking.py): internal, never the student's fault
UNCHECKED = ("waiting", "internal")  # in no cluster: not checked yet, or could not be (counted apart)
SET_ASIDE = "set aside: "           # an internal check's error when the pool set its text aside: final
VIEW_KEYS = ("phase", "version", "layout", "students", "count", "waiting", "unchecked", "revealed", "min")
KEY = re.compile(r"[0-9a-f]{16}")


@dataclass
class Contribution:
    """A phone's contribution to an activity: a tuple of terms, or a query."""
    id: str
    session: str
    activity: str
    player: str                     # for the phone's own list and for blocking only
    created: int
    input: dict                     # {"fields": [...]} or {"text": ...}
    state: str = "in"               # in replaced withdrawn hidden
    key: str = ""                   # tuple: its terms' keys; query: its result's key ("" while it waits)
    status: str = "ok"              # ok waiting syntax error timeout refused internal
    error: str = ""

    def again(self) -> bool:
        """Whether a later check may give it a result: internal, and not set aside (SET_ASIDE)."""
        return self.status == "internal" and not self.error.startswith(SET_ASIDE)


@dataclass
class Result:
    """A distinct result of an activity's queries: what the windows show of it."""
    session: str
    activity: str
    key: str
    summary: dict
    created: int


ROWS = {Contribution: ("contributions", ["id", "session", "activity", "player", "created", "input", "state", "key",
                                         "status", "error"], "id", ("input",)),
        Result: ("results", ["session", "activity", "key", "summary", "created"], "session, activity, key",
                 ("summary",))}


@dataclass
class Shelf:
    """One activity's contributions and results in one game - and what is kept as contributions come and
    change (add, change), so that a phone's view and a count do not go through all of them (F0's Q7:
    closing an activity of 1,000 entries reached the last of 1,100 phones after 597 ms)."""
    contributions: dict[str, Contribution] = field(default_factory=dict)    # in the order they came
    results: dict[str, Result] = field(default_factory=dict)                # by key
    last: dict[str, int] = field(default_factory=dict)                      # player -> their last one's time
    cache: dict = field(default_factory=dict)                               # the pictures, by what they show
    mine: dict[str, list[Contribution]] = field(default_factory=dict)       # player -> theirs, in that order
    ins: Counter = field(default_factory=Counter)                           # player -> how many of theirs are in
    count: int = 0                                                          # contributions in
    waits: int = 0                                                          # ... of them waiting for their check
    unchecked: int = 0                                                      # ... that could not be checked
    waiting: dict[str, dict[str, Contribution]] = field(default_factory=dict)   # text -> those waiting with it
    unsure: dict[str, dict[str, Contribution]] = field(default_factory=dict)    # text -> internal, not final
    known: dict[str, Contribution] = field(default_factory=dict)            # text -> the first with a final check

    def add(self, c: Contribution):
        self.contributions[c.id] = c
        self.mine.setdefault(c.player, []).append(c)
        self._tally(c, 1)

    def change(self, c: Contribution, **fields):
        """A contribution's state, status, key or error changed: every count and index with it."""
        self._tally(c, -1)
        for name, value in fields.items():
            setattr(c, name, value)
        self._tally(c, 1)

    def _tally(self, c: Contribution, n: int):
        if c.state == "in":
            self.count += n
            self.ins[c.player] += n
            if self.ins[c.player] <= 0:
                del self.ins[c.player]
            if c.status == "waiting":
                self.waits += n
            elif c.status == "internal":
                self.unchecked += n
        text = c.input.get("text")
        if text is None:
            return
        index = self.waiting if c.status == "waiting" else self.unsure if c.again() else None
        if index is None:                      # a final check: the text's known result (an internal check
            if n > 0:                          # that is not final is none)
                self.known.setdefault(text, c)
            return
        same = index.setdefault(text, {})
        if n > 0:
            same[c.id] = c
        else:
            same.pop(c.id, None)
            if not same:
                del index[text]


class Book:
    """The activities' contributions and results of all games, the evaluating windows' leases, the
    graphs' layouts (types.py: Book) - and the server's checks, if it checks (checking.py; the engine
    sets them)."""

    def __init__(self):
        self.shelves: dict[tuple[str, str], Shelf] = {}
        self.leases: dict[str, tuple[str, int]] = {}                       # session -> (connection, until)
        self.layouts: dict[tuple[str, str], dict] = {}                     # (session, activity) -> positions
        self.checks = None                                                 # checking.Checks; None: the browser's

    def shelf(self, sid: str, aid: str) -> Shelf:
        return self.shelves.setdefault((sid, aid), Shelf())

    def load(self, rows: list):
        for r in sorted(rows, key=lambda r: (r.created, getattr(r, "id", r.key))):
            if isinstance(r, Contribution):
                self.shelf(r.session, r.activity).add(r)
            else:
                self.shelf(r.session, r.activity).results[r.key] = r

    def forget(self, sid: str):
        for key in [k for k in self.shelves if k[0] == sid]:
            del self.shelves[key]
        for key in [k for k in self.layouts if k[0] == sid]:
            del self.layouts[key]
        self.leases.pop(sid, None)

    def left(self, conn: str):
        for sid in [s for s, (c, _) in self.leases.items() if c == conn]:
            del self.leases[sid]

    def lease(self, sid: str, conn: str | None, now: int) -> bool:
        """The lease to evaluate this game's queries: the window that has it, or the first to ask
        when nobody has it (or its window has not asked for 15 s); renewed with every request."""
        holder = self.leases.get(sid)
        if conn is None or (holder is not None and holder[0] != conn and holder[1] >= now):
            return False
        self.leases[sid] = (conn, now + LEASE_MS)
        return True

    def holds(self, sid: str, conn: str | None, now: int) -> bool:
        holder = self.leases.get(sid)
        return holder is not None and holder[0] == conn and holder[1] >= now


# ------------------------------------------------------------------ texts
# (the cleaning itself: checks/cleaning.py, which the kinds share - F2's plan, 4.2)
def clean_term(text) -> str:
    """A term as the phone sent it, cleaned (cleaning.clean_term) - or refused."""
    try:
        return cleaning.clean_term(text)
    except cleaning.Unfit as e:
        raise Refused(str(e), e.code) from None


def clean_code(text, what: str = "a query") -> str:
    """A query as typed, cleaned (cleaning.clean_code) - or refused."""
    try:
        return cleaning.clean_code(text, what)
    except cleaning.Unfit as e:
        raise Refused(str(e), e.code) from None


# ------------------------------------------------------------------ state
def _fresh(item: dict) -> dict:
    st = {"phase": "ready", "version": 0, "layout": 0, "students": 0, "count": 0, "waiting": 0, "unchecked": 0,
          "revealed": False}
    if item["input"] == "tuple":
        st |= {"min": item.get("min", 1), "merges": [], "hidden": [], "approved": []}
    else:
        st |= {"shown": None, "refs": []}
    return st


def _state(stage: dict) -> dict:
    return stage.get(NAME) or {"current": None, "items": {}}


def _open(state: dict, aid: str):
    for other, st in state["items"].items():
        if other != aid and st["phase"] == "open":
            st["phase"] = "closed"
            st["version"] += 1
    st = state["items"][aid]
    st["phase"] = "open"
    st["version"] += 1
    state["current"] = aid


def _recount(st: dict, shelf: Shelf):
    """The counts as the shelf keeps them (Shelf.change): of those in, the ones that wait for their check,
    and apart from them the ones that could not be checked (internal) - as the design's panel has them
    (AF 13); the package 4 review: counted together, a pool that broke looked like a slow one."""
    st["count"], st["students"] = shelf.count, len(shelf.ins)
    st["waiting"], st["unchecked"] = shelf.waits, shelf.unchecked
    st["version"] += 1


def _refs(st: dict, n: int) -> list[str | None]:
    """The activity's n references as its state has them: a key, "!status: error", or None - not run yet."""
    return ((st.get("refs") or []) + [None] * n)[:n]


def _item(call, aid) -> dict:
    if not isinstance(aid, str) or aid not in call.items:
        raise Refused("no such activity in this deck")
    return call.items[aid]


def refuses(deck: dict) -> str | None:
    """Why this type cannot play a deck's activities: one of a kind it never had - texstage's own choice,
    number, text, and any kind after the four -, whose item has no input of this type's (types.py: refuses).
    The core's type runs them: texstage serve --activities core."""
    for aid, item in sorted(((deck.get("items") or {}).get(NAME) or {}).items()):
        if not isinstance(item, dict) or item.get("input") not in ("tuple", "code"):
            kind = item.get("kind") if isinstance(item, dict) else None
            return (f"the activity {aid} is of the kind {kind or '(none)'}, which this server's activity type does not "
                    f"run - start it with texstage serve --activities core")
    return None


def failed_references(stage: dict) -> list[dict]:
    """The references that failed in a game - the deck list says so (app.py), before the lecture too,
    once a game of the deck has checked them: [{activity, reference (from 1), error}]."""
    state = stage.get(NAME) or {}
    return [{"activity": aid, "reference": i + 1, "error": r[1:]}
            for aid, st in (state.get("items") or {}).items() for i, r in enumerate(st.get("refs") or [])
            if isinstance(r, str) and r.startswith("!")]


def view(stage: dict) -> dict | None:
    """Every window's part: the activities' phases and counts - not the lists, not the references."""
    state = stage.get(NAME)
    if not state:
        return None
    return {"current": state.get("current"),
            "items": {aid: {k: st[k] for k in VIEW_KEYS if k in st} for aid, st in state["items"].items()}}


def slide(stage: dict, items: dict, before: tuple, after: tuple, now: int) -> dict:
    """The projector shows another slide: an activity whose frame it leaves closes; one whose frame
    comes for the first time opens (open=auto)."""
    old = stage.get(NAME)
    state = copy.deepcopy(old) if old else {"current": None, "items": {}}
    changed = False
    for aid in before:
        st = state["items"].get(aid)
        if aid not in after and st is not None and st["phase"] == "open":
            st["phase"] = "closed"
            st["version"] += 1
            changed = True
    for aid in after:
        if aid in before or aid not in items:
            continue
        if aid not in state["items"]:
            state["items"][aid] = _fresh(items[aid])
            changed = True
        if state["items"][aid]["phase"] == "ready" and items[aid].get("open", "auto") == "auto":
            _open(state, aid)
            changed = True
    return {**stage, NAME: state} if changed else stage


# ------------------------------------------------------------------ the presenter window's messages
def handle(call, t: str, msg: dict) -> dict | None:
    if t == "activity.work":
        return _work(call)
    aid = msg.get("activity")
    item = _item(call, aid)
    state = copy.deepcopy(_state(call.session.stage))
    st = state["items"].setdefault(aid, _fresh(item))
    shelf = call.book.shelf(call.session.id, aid)
    crowd = item["input"] == "tuple"
    reply = None
    if t == "activity.view":
        return {"picture": picture(call, aid)}
    if t == "activity.open":
        _open(state, aid)
        call.phones = True
    elif t == "activity.close":
        if st["phase"] == "open":
            st["phase"] = "closed"
            st["version"] += 1
            call.phones = True
    elif t == "activity.reveal":
        if crowd:
            raise Refused("a crowd graph has nothing to reveal")
        if not any(r and not r.startswith("!") for r in st["refs"]):
            who = "the server has not checked it" if _mode(call) == "server" else "the presenter window has not run it"
            raise Refused(f"no reference result yet - the deck gives none, or {who}")
        st["revealed"] = True
        st["version"] += 1
        call.phones = True
    elif t == "activity.result":
        reply = _result(call, aid, item, st, shelf, msg)
    elif t == "activity.layout":
        _layout(call, aid, st, msg)
    elif t == "activity.block":
        c = shelf.contributions.get(msg.get("contribution"))
        p = call.session.players.get(c.player) if c is not None else None
        if p is None:
            raise Refused("no such contribution")
        p.muted = True
        call.save(p)
        for o in list(shelf.mine.get(p.id, ())):
            if o.state == "in":
                shelf.change(o, state="hidden")
                call.save(o)
        _recount(st, shelf)
        call.phones = {p.id}
    elif t == "activity.hide" and "contribution" in msg:
        c = shelf.contributions.get(msg.get("contribution"))
        if c is None or c.state not in ("in", "hidden"):
            raise Refused("no such contribution")
        shelf.change(c, state="hidden" if msg.get("on", True) else "in")
        call.save(c)
        _recount(st, shelf)
    elif t == "activity.show":
        if crowd:
            raise Refused("a crowd graph shows itself")
        key = msg.get("cluster")
        if key is not None and (not isinstance(key, str) or key not in _clusters(shelf)):
            raise Refused("no such cluster")
        st["shown"] = key
        st["version"] += 1
    elif not crowd:
        raise Refused(f"{t} is for a crowd graph (input=tuple)")
    else:
        _moderate(t, st, shelf, msg, len(item["fields"]))
    call.session.stage = {**call.session.stage, NAME: state}
    return reply


def _terms(shelf: Shelf, nfields: int) -> set[tuple[str, str]]:
    roles = [_role(i, nfields) for i in range(nfields)]
    return {(roles[i], k) for c in shelf.contributions.values() for i, k in enumerate(c.key.split("\x1f"))}


def _role(i: int, n: int) -> str:
    return "node" if i in (0, n - 1) else "label"


def _moderate(t: str, st: dict, shelf: Shelf, msg: dict, nfields: int):
    """The crowd graph: merge, unmerge, hide, approve, the minimum."""
    if t == "activity.min":
        n = msg.get("min")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 1000:
            raise Refused("min: the students a triple needs, 1 to 1000")
        st["min"] = n
    else:
        role, term = msg.get("role", "node"), msg.get("term")
        known = {k for r, k in _terms(shelf, nfields) if r == role} | {m[1] for m in st["merges"] if m[0] == role}
        if role not in ("node", "label") or not isinstance(term, str) or term not in known:
            raise Refused("no such term")
        if t == "activity.merge":
            into = msg.get("into")
            if not isinstance(into, str) or into not in known or into == term:
                raise Refused("merge into another term")
            parents = {(r, a): b for r, a, b in st["merges"]}
            root = into
            while (role, root) in parents:                       # no cycles: into's root must not be term
                root = parents[(role, root)]
                if root == term:
                    raise Refused(f"{into} is merged into {term} already")
            st["merges"] = [m for m in st["merges"] if (m[0], m[1]) != (role, term)] + [[role, term, into]]
        elif t == "activity.unmerge":
            st["merges"] = [m for m in st["merges"] if (m[0], m[1]) != (role, term)]
        else:
            name = "hidden" if t == "activity.hide" else "approved"
            on = msg.get("on", True)
            st[name] = [x for x in st[name] if x != term] + ([term] if on else [])
    st["version"] += 1


def _layout(call, aid: str, st: dict, msg: dict):
    """The crowd graph's positions from the presenter window with the lease - fractions of the
    activity's box - for every window: not stored."""
    if call.role != "stage" or not call.book.holds(call.session.id, call.conn, call.now):
        raise Refused("another presenter window lays the graph out", "not-evaluator")
    at = msg.get("at")
    if not isinstance(at, dict) or len(at) > 4 * NODES_SHOWN:
        raise Refused("at: {term: [x, y]}")
    found = {}
    for term, p in at.items():
        if (isinstance(term, str) and isinstance(p, list) and len(p) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in p)):
            found[term] = [round(p[0], 4), round(p[1], 4)]
    call.book.layouts[(call.session.id, aid)] = found
    st["layout"] += 1
    call.changed = False


# ------------------------------------------------------------------ evaluation: in the presenter's browser, or on the server
def _mode(call) -> str:
    """Who checks this server's texts (checking.py, MODES): browser - the presenter window, as before F1."""
    return call.book.checks.mode if call.book is not None and call.book.checks is not None else "browser"


def _work(call) -> dict:
    """What the presenter window with the lease evaluates next: up to JOBS distinct waiting texts,
    the references not run yet - or that the server could not run (internal: its pool failed; the
    package 4 review: else after a fallback to the browser's checks the activity was never revealed) -,
    the keys whose results the server has. Where the server checks (the mode server), none: the lease
    is the crowd graph's layout's only."""
    if call.role != "stage":
        raise Refused("only a presenter window evaluates", "read-only")
    sid, book = call.session.id, call.book
    server = _mode(call) == "server"
    if not book.lease(sid, call.conn, call.now):
        return {"lease": False, "checks": "server"} if server else {"lease": False}
    if server:
        return {"lease": True, "checks": "server", "jobs": [], "references": {}, "known": {}, "engines": {}}
    state = _state(call.session.stage)
    jobs, refs, known, engines = [], {}, {}, {}
    for aid, item in call.items.items():
        if item["input"] != "code":
            continue
        st = state["items"].get(aid) or {}
        shelf = book.shelf(sid, aid)
        references = (call.keys.get(aid) or {}).get("reference") or []
        if any(r is None or r.startswith("!internal") for r in _refs(st, len(references))):
            refs[aid] = references
        texts = {}
        for text, waiting in shelf.waiting.items():
            c = next((c for c in waiting.values() if c.state in ("in", "hidden")), None)
            if c is not None:
                texts[text] = c
        for c in list(texts.values())[:max(0, JOBS - len(jobs))]:
            jobs.append({"activity": aid, "input": c.id, "text": c.input["text"]})
        if aid in refs or texts:
            known[aid] = list(shelf.results)
            engines[aid] = {"engine": item["engine"], "seed": item["seed"]}
    return {"lease": True, "jobs": jobs, "references": refs, "known": known, "engines": engines}


def _result(call, aid: str, item: dict, st: dict, shelf: Shelf, msg: dict) -> dict | None:
    """A result from the presenter window with the lease: for an input (every waiting contribution
    with its text), or for a reference - none where the server checks; in the mode both written down
    for the pool's to be compared with (checking.py: compare)."""
    sid = call.session.id
    if item["input"] != "code":
        raise Refused("a crowd graph has nothing to evaluate")
    mode = _mode(call)
    if mode == "server":
        raise Refused("the server checks the texts of this game", "not-evaluator")
    if call.role != "stage" or not call.book.holds(sid, call.conn, call.now):
        raise Refused("another presenter window evaluates", "not-evaluator")
    if msg.get("status") not in STATUSES:
        raise Refused(f"status: one of {', '.join(STATUSES)}")
    if msg["status"] == "ok" and (not isinstance(msg.get("key"), str) or not KEY.fullmatch(msg["key"])):
        raise Refused("key: 16 hexadecimal digits")
    if "reference" in msg:
        reply = _apply(call, aid, st, shelf, msg)
        if mode == "both":
            texts = (call.keys.get(aid) or {}).get("reference") or []
            call.book.checks.compare(call.session, aid, f"reference {msg['reference'] + 1}", texts[msg["reference"]],
                                     browser=msg)
        return reply
    first = shelf.contributions.get(msg.get("input"))
    if first is None or first.status != "waiting":
        return {"stale": True}                       # (withdrawn meanwhile, or evaluated already)
    text = first.input["text"]
    reply = _apply(call, aid, st, shelf, msg | {"text": text})
    if mode == "both" and reply is None:
        call.book.checks.compare(call.session, aid, "text", text, browser=msg)
    return reply


def checked(call, aid: str, msg: dict, again: bool = False) -> dict | None:
    """The server's check of a text - every contribution waiting with it - or of a reference ("reference":
    its index), from the pool (checking.py, Engine.apply_checks), applied as the presenter window's
    result is; a summary the shelf has no room for is left out, not the check. again: it was applied
    before and that failed - maybe after the shelf had changed (_apply)."""
    item = _item(call, aid)
    if item["input"] != "code":
        raise Refused("a crowd graph has nothing to check")
    if msg.get("status") not in CHECKED:
        raise Refused(f"status: one of {', '.join(CHECKED)}")
    state = copy.deepcopy(_state(call.session.stage))
    st = state["items"].setdefault(aid, _fresh(item))
    shelf = call.book.shelf(call.session.id, aid)
    reply = _apply(call, aid, st, shelf, msg, lenient=True, again=again)
    call.session.stage = {**call.session.stage, NAME: state}
    return reply


def restarted(call) -> bool:
    """The server started again (game.py: Engine): what could not be checked for the server's reasons -
    internal, not set aside (Contribution.again) - waits again for the next checks: the pool's
    (Engine.resume_checks), else the presenter window's. As the design has it (AF 10.2): a restarted
    server queues the entries still unchecked again. Whether the game changed."""
    state = copy.deepcopy(_state(call.session.stage))
    changed = False
    for aid, item in call.items.items():
        shelf = call.book.shelves.get((call.session.id, aid))
        if item["input"] != "code" or shelf is None:
            continue
        again = [c for same in shelf.unsure.values() for c in same.values()]
        for c in again:
            shelf.change(c, status="waiting", key="", error="")
            call.save(c)
        if again:
            _recount(state["items"].setdefault(aid, _fresh(item)), shelf)
            changed = True
    if changed:
        call.session.stage = {**call.session.stage, NAME: state}
    return changed


def _apply(call, aid: str, st: dict, shelf: Shelf, msg: dict, lenient: bool = False,
           again: bool = False) -> dict | None:
    """A check's outcome - status, key, error, summary - for a text (msg's "text": every contribution
    waiting with it) or a reference (its "reference"). lenient, the server's: a summary over the size or
    the activity's number of results is left out; the window's is refused. A final outcome - any but an
    internal one that is not set aside - is also that of the text's entries that could not be checked
    before (Shelf.unsure; the review of package 4's fixes: they stayed so until a restart, beside the
    same text's verdict). again: the outcome was applied before, and that failed - if the store failed
    after the shelf had changed, the entries that have the outcome already are saved, counted and
    pushed again (the same review: the retry found nothing waiting, and did nothing)."""
    status = msg["status"]
    key = msg.get("key") if status == "ok" else status
    if status == "ok" and (not isinstance(key, str) or not KEY.fullmatch(key)):
        raise Refused("key: 16 hexadecimal digits")
    error = msg.get("error") if isinstance(msg.get("error"), str) else ""
    if status == "internal" and msg.get("set_aside") is True and not error.startswith(SET_ASIDE):
        error = SET_ASIDE + error                    # (the pool's: final - Contribution.again)
    summary = msg.get("summary")
    if status == "ok" and key not in shelf.results and isinstance(summary, dict):
        why = None
        if len(json.dumps(summary)) > SUMMARY_MAX:
            why = Refused(f"the summary has more than {SUMMARY_MAX // 1024} KB")
        elif len(shelf.results) >= RESULTS_MAX:
            why = Refused(f"this activity has {RESULTS_MAX} different results already", "too-many")
        if why is not None and not lenient:
            raise why
        if why is None:
            r = Result(call.session.id, aid, key, summary, call.now)
            call.save(r)                             # (first: a save that fails leaves it to be saved again)
            shelf.results[key] = r
    if "reference" in msg:
        references = (call.keys.get(aid) or {}).get("reference") or []
        i = msg.get("reference")
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(references):
            raise Refused("no such reference")
        refs = (st["refs"] + [None] * len(references))[:len(references)]
        refs[i] = key if status == "ok" else f"!{status}: {error[:ERROR_MAX]}"
        st["refs"] = refs
        st["version"] += 1
        return None
    text, error = msg.get("text"), error[:ERROR_MAX] if status != "ok" else ""
    waiting = list(shelf.waiting.get(text, {}).values())
    if status != "internal" or error.startswith(SET_ASIDE):
        waiting += list(shelf.unsure.get(text, {}).values())
    saved = [c for c in shelf.contributions.values()
             if c.input.get("text") == text and (c.status, c.key, c.error) == (status, key, error)] if again else []
    if not waiting and not saved:
        return {"stale": True}                       # (checked already: a known result, an earlier check)
    phones = set()
    for c in waiting:
        shelf.change(c, status=status, key=key, error=error)
        call.save(c)
        phones.add(c.player)
    for c in saved:
        call.save(c)
        phones.add(c.player)
    _recount(st, shelf)
    call.phones = phones
    return None


# ------------------------------------------------------------------ the phones
def player(call, t: str, msg: dict) -> dict | None:
    aid = msg.get("activity")
    item = _item(call, aid)
    state = copy.deepcopy(_state(call.session.stage))
    st = state["items"].get(aid)
    p = call.player
    if st is None or st["phase"] != "open":
        raise Refused("this activity is closed", "closed")
    if p.muted:
        raise Refused("the lecturer has closed contributions for you", "blocked")
    shelf = call.book.shelf(call.session.id, aid)
    mine = shelf.mine.get(p.id, [])
    if t == "activity.withdraw":
        c = shelf.contributions.get(msg.get("contribution"))
        if c is None or c.player != p.id or c.state != "in":
            raise Refused("no such contribution of yours")
        shelf.change(c, state="withdrawn")
        call.save(c)
        _recount(st, shelf)
        call.session.stage = {**call.session.stage, NAME: state}
        return None
    if call.now - shelf.last.get(p.id, 0) < GAP_MS[item["input"]]:
        raise Refused(f"one every {GAP_MS[item['input']] // 1000} seconds", "too-fast")
    used = len(mine) if item["input"] == "code" else sum(1 for c in mine if c.state == "in")
    if used >= item["limit"]:
        raise Refused(f"at most {item['limit']} from each of you", "too-many")
    if len(shelf.contributions) >= PER_ACTIVITY:
        raise Refused("this activity has had enough contributions", "too-many")
    cid = secrets.token_hex(6)
    if item["input"] == "tuple":
        fields = msg.get("fields")
        if not isinstance(fields, list) or len(fields) != len(item["fields"]):
            raise Refused(f"fields: {len(item['fields'])} texts")
        fields = [clean_term(f) for f in fields]
        key = "\x1f".join(term_key(f, item) for f in fields)
        if any(c.key == key and c.state == "in" for c in mine):
            raise Refused("you have sent this one already", "duplicate")
        c = Contribution(cid, call.session.id, aid, p.id, call.now, {"fields": fields}, key=key)
    else:
        text = clean_code(msg.get("text"), ENGINES.get(item.get("engine"), {}).get("text", "a query"))
        for old in list(mine):
            if old.state == "in":
                shelf.change(old, state="replaced")
                call.save(old)
        done = shelf.known.get(text)                 # the same text: its result is known
        c = Contribution(cid, call.session.id, aid, p.id, call.now, {"text": text},
                         key=done.key if done else "", status=done.status if done else "waiting",
                         error=done.error if done else "")
    shelf.add(c)
    shelf.last[p.id] = call.now
    call.save(c)
    _recount(st, shelf)
    call.session.stage = {**call.session.stage, NAME: state}
    if c.status == "waiting" and call.book.checks is not None:        # the server checks it (checking.py)
        call.book.checks.submit(call.session.bundle, aid, c.input["text"], call.session.id, owner=p.id)
    return {"contribution": cid}


def player_view(call) -> dict | None:
    """What a phone shows of the current activity, while it is open or revealed."""
    state = _state(call.session.stage)
    aid = state.get("current")
    st = state["items"].get(aid) if aid else None
    if st is None or aid not in call.items or (st["phase"] != "open" and not st.get("revealed")):
        return None
    item, p = call.items[aid], call.player
    shelf = call.book.shelf(call.session.id, aid)
    theirs = shelf.mine.get(p.id, [])
    mine = [c for c in theirs if c.state != "withdrawn"]
    out = {"id": aid, "phase": st["phase"], "input": item["input"], "limit": item["limit"], "blocked": p.muted}
    if item.get("prompt"):
        out["prompt"] = item["prompt"]
    if item["input"] == "tuple":
        shown = [n["label"] for n in picture(call, aid, role="display")["nodes"]]
        words = list(dict.fromkeys(item.get("suggest", []) + shown))[:SUGGEST_MAX]
        out |= {"fields": item["fields"], "suggest": words, "used": len(mine),
                "mine": [{"id": c.id, "fields": c.input["fields"]} for c in reversed(mine)]}
    else:                                   # (the engine: the phone's words - a query runs, a Turtle text is valid)
        out |= {"engine": item.get("engine"), "tokens": item.get("tokens", []), "used": len(theirs)}
        if _mode(call) == "server":                  # the phone's words: being checked, not waiting for the
            out["checks"] = "server"                 # lecturer's computer (the package 4 review)
        latest = next((c for c in reversed(mine) if c.state in ("in", "hidden")), None)
        if latest is not None:
            last = {"id": latest.id, "text": latest.input["text"], "status": latest.status}
            if latest.error and latest.status != "internal":      # (why the server could not: not the phone's)
                last["error"] = latest.error
            if st.get("revealed") and latest.status == "ok":
                last["match"] = latest.key in st["refs"]
            out["mine"] = last
    return out


# ------------------------------------------------------------------ the picture
def picture(call, aid: str, role: str | None = None) -> dict:
    """The activity's picture as a window draws it: the projector's (role display) moderated, the
    presenter window's (stage) with what is hidden, merged and waiting for review, and the
    reference's clusters before the reveal."""
    role = "stage" if (role or call.role) == "stage" else "display"
    item = call.items[aid]
    st = _state(call.session.stage)["items"].get(aid) or _fresh(item)
    shelf = call.book.shelf(call.session.id, aid)
    layout = call.book.layouts.get((call.session.id, aid), {})
    key = (role, st["version"], st["layout"])
    if key not in shelf.cache:
        if len(shelf.cache) > 8:
            shelf.cache.clear()
        base = {"activity": aid, "phase": st["phase"], "version": st["version"], "students": st["students"],
                "count": st["count"]}
        if item["input"] == "tuple":
            shelf.cache[key] = base | _crowd(item, st, shelf, role, layout)
        else:
            n_refs = len((call.keys.get(aid) or {}).get("reference") or [])
            shelf.cache[key] = base | _clustered(st, shelf, role, n_refs)
    return shelf.cache[key]


def _crowd(item: dict, st: dict, shelf: Shelf, role: str, layout: dict) -> dict:
    n = len(item["fields"])
    spellings: dict[tuple[str, str], Counter] = {}
    for c in shelf.contributions.values():
        for i, (word, k) in enumerate(zip(c.input["fields"], c.key.split("\x1f"))):
            spellings.setdefault((_role(i, n), k), Counter())[word] += 1
    parents = {(r, a): b for r, a, b in st["merges"]}

    def root(r: str, k: str) -> str:
        seen = set()
        while (r, k) in parents and k not in seen:
            seen.add(k)
            k = parents[(r, k)]
        return k

    def label(r: str, k: str) -> str:
        counts = spellings.get((r, k))
        return counts.most_common(1)[0][0] if counts else k
    hidden, approved = set(st["hidden"]), set(st["approved"])
    tuples: dict[tuple, set] = {}
    for c in shelf.contributions.values():
        if c.state == "in":
            terms = tuple(root(_role(i, n), k) for i, k in enumerate(c.key.split("\x1f")))
            tuples.setdefault(terms, set()).add(c.player)
    visible = {t: who for t, who in tuples.items()
               if len(who) >= st["min"] and not hidden & set(t)
               and (not item.get("review") or set(t) <= approved)}
    nodes: dict[str, set] = {}
    for t, who in visible.items():
        for k in (t[0], t[-1]):
            nodes.setdefault(k, set()).update(who)
    ranked = sorted(nodes, key=lambda k: (-len(nodes[k]), label("node", k)))
    top = set(ranked[:NODES_SHOWN])

    def node(k: str) -> dict:                            # a literal says so: the windows draw it as a box
        return {"id": k, "label": label("node", k), "n": len(nodes[k])} | \
            ({"literal": True} if is_literal(label("node", k)) else {})
    out = {"kind": "graph", "min": st["min"], "review": bool(item.get("review")),     # (2 or 3 fields: the build)
           "nodes": [node(k) for k in ranked[:NODES_SHOWN]],
           "edges": [{"s": t[0], "o": t[-1], "p": t[1] if n == 3 else None,
                      "label": label("label", t[1]) if n == 3 else "", "n": len(who)}
                     for t, who in sorted(visible.items(), key=lambda e: (-len(e[1]), e[0]))
                     if t[0] in top and t[-1] in top],
           "more": max(0, len(ranked) - NODES_SHOWN),
           "at": {k: layout[k] for k in ranked[:NODES_SHOWN] if k in layout}}
    if role == "stage":
        counted: dict[tuple[str, str], set] = {}
        for c in shelf.contributions.values():
            if c.state == "in":
                for i, k in enumerate(c.key.split("\x1f")):
                    counted.setdefault((_role(i, n), k), set()).add(c.player)
        merged = {(r, a): b for r, a, b in st["merges"]}
        terms = sorted(counted, key=lambda rk: (-len(counted[rk]), rk))[:300]
        out["terms"] = [{"role": r, "key": k, "label": label(r, k), "n": len(counted[(r, k)]),
                         "hidden": k in hidden, "approved": k in approved, "into": merged.get((r, k))}
                        for r, k in terms]
        out["hiddenTuples"] = sum(1 for c in shelf.contributions.values() if c.state == "hidden")
    return out


def _clusters(shelf: Shelf) -> dict[str, list[Contribution]]:
    """The latest queries grouped by key (a status for what is not a result), not those that wait or
    that could not be checked (UNCHECKED)."""
    groups: dict[str, list[Contribution]] = {}
    for c in shelf.contributions.values():
        if c.state == "in" and c.status not in UNCHECKED:
            groups.setdefault(c.key if c.status == "ok" else c.status, []).append(c)
    return groups


def _clustered(st: dict, shelf: Shelf, role: str, n_refs: int = 0) -> dict:
    """n_refs: the deck's references - the presenter window has each, None while it is not run yet (the
    package 4 review: before, it said the deck gives none while the server prepared them)."""
    groups = _clusters(shelf)
    show_refs = role == "stage" or st.get("revealed")
    refs = set(st["refs"]) if show_refs else set()

    def entry(key: str, members: list[Contribution]) -> dict:
        texts = Counter(c.input["text"] for c in members)
        example = max(members, key=lambda c: (texts[c.input["text"]], -c.created))
        status = key if key in STATUSES else "ok"
        e = {"key": key, "n": len({c.player for c in members}), "status": status, "example": example.input["text"],
             "reference": key in refs}
        if status == "ok" and key in shelf.results:
            e["summary"] = shelf.results[key].summary
        if role == "stage":
            e["contribution"] = example.id
            if status != "ok":
                e["errors"] = list(dict.fromkeys(c.error for c in members if c.error))[:5]
        return e
    ranked = sorted(groups.items(), key=lambda kv: (-len({c.player for c in kv[1]}), kv[0]))
    shown_n = CLUSTERS_SHOWN if role == "display" else 50
    out = {"kind": "clusters", "revealed": bool(st.get("revealed")), "waiting": st.get("waiting", 0),
           "clusters": [entry(k, m) for k, m in ranked[:shown_n]],
           "others": sum(len({c.player for c in m}) for _, m in ranked[shown_n:]),
           "shown": None}
    if st.get("shown") in groups:
        out["shown"] = entry(st["shown"], groups[st["shown"]])
    if role == "stage":
        out["unchecked"] = st.get("unchecked", 0)
        out["refs"] = [r if r is None or not r.startswith("!") else {"failed": r[1:]}
                       for r in (_refs(st, n_refs) if n_refs else st["refs"])]
    return out


# ------------------------------------------------------------------ the lecture archive
def archive(call) -> dict[str, str]:
    """Per activity with contributions: activity-<id>.csv (a row each, no names), .json (the final
    picture, the reference's marked) and, for a graph, .svg."""
    files = {}
    for aid, item in call.items.items():
        shelf = call.book.shelves.get((call.session.id, aid))
        if shelf is None or not shelf.contributions:
            continue
        rows = [["time", "input", "state", "status", "error"]]
        for c in shelf.contributions.values():
            text = " | ".join(c.input["fields"]) if "fields" in c.input else c.input["text"]
            rows.append([time.strftime("%H:%M:%S", time.localtime(c.created / 1000)), text, c.state, c.status, c.error])
        files[f"activity-{aid}.csv"] = "﻿" + sheets.csv_text(rows)
        pic = picture(call, aid, role="stage")
        files[f"activity-{aid}.json"] = json.dumps(pic, ensure_ascii=False, indent=1) + "\n"
        if pic["kind"] == "graph":
            files[f"activity-{aid}.svg"] = graph_svg(pic)
    return files


BEND = 34                           # two edges between the same nodes: their curves this far apart


def edge_shapes(edges: list[dict]) -> list[dict]:
    """Per edge, as the windows draw it (web/stage/activity.js, edgeShapes): edges between the same
    two nodes, either way round, curve apart - bend: the curve's middle off the straight line, to
    the left of the edge's own direction -; a node's own edge (subject = object) is a loop."""
    groups: dict[tuple, list[int]] = {}
    for i, e in enumerate(edges):
        groups.setdefault(("loop", e["s"]) if e["s"] == e["o"] else tuple(sorted((e["s"], e["o"]))), []).append(i)
    shapes = [{"bend": 0.0} for _ in edges]
    for members in groups.values():
        for j, i in enumerate(members):
            e = edges[i]
            shapes[i] = {"loop": j} if e["s"] == e["o"] else \
                {"bend": (j - (len(members) - 1) / 2) * BEND * (1 if e["s"] < e["o"] else -1)}
    return shapes


LABELS_AT = 3                       # one label on many edges at one node: shown on this many


def repeated_labels(edges: list[dict]) -> set[int]:
    """The edges whose labels are left out, as the windows leave them out (web/stage/activity.js,
    repeatedLabels): a label on many edges at one node shows on the LABELS_AT most students named."""
    groups: dict[tuple, list[int]] = {}
    for i, e in enumerate(edges):
        if e.get("label"):
            for k in (("s", e["s"], e["label"]), ("o", e["o"], e["label"])):
                groups.setdefault(k, []).append(i)
    left = set()
    for members in groups.values():
        if len(members) > LABELS_AT:
            left.update(sorted(members, key=lambda i: (-(edges[i].get("n") or 1), i))[LABELS_AT:])
    return left


# the spots along an edge its label tries, in turn (web/stage/activity.js, SPOTS): t of the way, and
# above the line, below it or beside it
SPOTS = [(0.5, "above"), (0.5, "below"), (0.4, "above"), (0.6, "above"), (0.4, "below"), (0.6, "below"),
         (0.5, "right"), (0.5, "left"), (0.3, "above"), (0.7, "above"), (0.3, "below"), (0.7, "below")]


def spot_offset(side: str, w: float, h: float) -> tuple[float, float]:
    """A label's baseline's middle from its edge's point (activity.js, spotOffset); w its width, h its
    font size."""
    if side == "above":
        return 0.0, -6.0
    if side == "below":
        return 0.0, 0.8 * h + 6
    return (1 if side == "right" else -1) * (w / 2 + 8), 0.3 * h


def label_box(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    """A label standing centred on its baseline at (x, y), with a little room around it (activity.js,
    labelBox)."""
    return x - w / 2 - 3, y - 0.8 * h - 2, x + w / 2 + 3, y + 0.25 * h + 2


def place_labels(labels: list[dict], obstacles: list[tuple], size: tuple[float, float]) -> list[tuple | None]:
    """The edges' labels apart, as the windows place them (activity.js, placeLabels): each at the first
    spot along its edge (at(t): the edge's point t of the way) that lies inside the picture, on no
    obstacle (the nodes) and on no label placed before - those of the edges most students sent first;
    a loop's label (no at) has its one spot (x, y). One with no free spot is left out (None).
    labels: {w, h, n, at | x, y} -> per label (x, y) | None"""
    taken = list(obstacles)

    def free(b):
        return b[0] >= 0 and b[1] >= 0 and b[2] <= size[0] and b[3] <= size[1] and \
            not any(b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3] for o in taken)

    def spots(lab):
        if lab.get("at") is None:
            yield lab["x"], lab["y"]
            return
        for t, side in SPOTS:
            (px, py), (ox, oy) = lab["at"](t), spot_offset(side, lab["w"], lab["h"])
            yield px + ox, py + oy

    out: list[tuple | None] = [None] * len(labels)
    for i in sorted(range(len(labels)), key=lambda i: (-(labels[i].get("n") or 1), i)):
        for x, y in spots(labels[i]):
            b = label_box(x, y, labels[i]["w"], labels[i]["h"])
            if free(b):
                taken.append(b)
                out[i] = (x, y)
                break
    return out


def graph_svg(pic: dict) -> str:
    """The crowd graph as an SVG picture: at the presenter window's positions, else on a circle;
    a resource a circle, a literal a square as the slides draw one (rdf-literal: light yellow, a
    dark rim), the name above; edges as arrows - curved apart between the same two nodes, a node's
    own one a loop below it -, their labels over them, apart and on no node (place_labels)."""
    w, h = 1000, 750
    at = dict(pic.get("at") or {})
    nodes = pic["nodes"]
    for i, n in enumerate(nodes):
        if n["id"] not in at:
            a = 2 * math.pi * i / max(1, len(nodes))
            at[n["id"]] = [0.5 + 0.4 * math.cos(a), 0.5 + 0.4 * math.sin(a)]
    xy = {k: (round(p[0] * w, 1), round(p[1] * h, 1)) for k, p in at.items()}
    radius = {n["id"]: min(26, 8 + 2 * n["n"]) for n in nodes}
    boxes = {n["id"] for n in nodes if n.get("literal")}  # (a square: radius its half side)
    parts = ['<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="12" markerHeight="12" '
             'markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#8a8a96"/>'
             '</marker></defs>']
    obstacles = []                                       # the nodes: their circles and their names above them
    for n in nodes:
        (x, y), r, wn = xy[n["id"]], radius[n["id"]], 0.58 * 15 * len(n["label"])
        obstacles += [(x - r, y - r, x + r, y + r), (x - wn / 2, y - 30 - 12, x + wn / 2, y - 30 + 4)]
    unlabelled = repeated_labels(pic["edges"])
    labels = []
    for i, (e, shape) in enumerate(zip(pic["edges"], edge_shapes(pic["edges"]))):
        if e["s"] not in xy or e["o"] not in xy:
            continue
        (x1, y1), (x2, y2) = xy[e["s"]], xy[e["o"]]
        r1, r2 = radius.get(e["s"], 8), radius.get(e["o"], 8)
        on = None                                        # the edge's point t of the way (none for a loop)
        if "loop" in shape:
            size = 34 + r1 + 18 * shape["loop"]
            a, b, low = x1 - 0.6 * r1, x1 + 0.6 * r1, y1 + 0.8 * r1
            d = f"M{a:.1f},{low:.1f} C{a - 0.6 * size:.1f},{y1 + r1 + size:.1f} {b + 0.6 * size:.1f},{y1 + r1 + size:.1f} {b:.1f},{low:.1f}"
            lx, ly = x1, y1 + r1 + 0.75 * size + 16
        else:
            length = math.hypot(x2 - x1, y2 - y1) or 1
            bend = shape["bend"]
            cx, cy = (x1 + x2) / 2 - (y2 - y1) / length * 2 * bend, (y1 + y2) / 2 + (x2 - x1) / length * 2 * bend

            def rim(x, y, r, square, gap=0):             # leave the circle or the square towards the curve's handle
                k = math.hypot(cx - x, cy - y) or 1
                ux, uy = (cx - x) / k, (cy - y) / k
                r = (r / max(abs(ux), abs(uy), 1e-9) if square else r) + gap
                return x + ux * r, y + uy * r
            (px, py), (qx, qy) = rim(x1, y1, r1, e["s"] in boxes), rim(x2, y2, r2, e["o"] in boxes, gap=3)
            d = f"M{px:.1f},{py:.1f} Q{cx:.1f},{cy:.1f} {qx:.1f},{qy:.1f}"
            lx, ly = (px + 2 * cx + qx) / 4, (py + 2 * cy + qy) / 4

            def on(t, p=(px, py), c=(cx, cy), q=(qx, qy)):
                return tuple((1 - t) ** 2 * p[k] + 2 * (1 - t) * t * c[k] + t * t * q[k] for k in (0, 1))
        parts.append(f'<path d="{d}" fill="none" stroke="#8a8a96" stroke-width="{min(8, 1 + e["n"])}" '
                     f'marker-end="url(#arrow)"/>')
        if e.get("label") and i not in unlabelled:
            labels.append({"text": e["label"], "w": 0.58 * 13 * len(e["label"]), "h": 13, "n": e["n"], "at": on,
                           "x": lx, "y": ly})
    for lab, spot in zip(labels, place_labels(labels, obstacles, (w, h))):
        if spot:
            parts.append(f'<text x="{spot[0]:.1f}" y="{spot[1]:.1f}" font-size="13" fill="#555" text-anchor="middle" '
                         f'paint-order="stroke" stroke="#fff" stroke-width="4">{html.escape(lab["text"])}</text>')
    for n in nodes:
        (x, y), r = xy[n["id"]], radius[n["id"]]
        parts.append(f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r}" height="{2 * r}" fill="#ffffcc" stroke="#4d4d4d" '
                     f'stroke-width="2"/>' if n["id"] in boxes else
                     f'<circle cx="{x}" cy="{y}" r="{r}" fill="#46178f" opacity="0.85"/>')
        parts.append(f'<text x="{x}" y="{y - 30}" font-size="15" text-anchor="middle">{html.escape(n["label"])}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'font-family="sans-serif"><rect width="{w}" height="{h}" fill="#fff"/>{"".join(parts)}</svg>\n')
