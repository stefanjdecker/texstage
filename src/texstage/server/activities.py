# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Live activities as the activity framework has them - the content type, thin: its hooks (types.py)
hand over to the core (texstage/activities: play.py) and to the pool
(docs/architecture/activity-framework-design.md, 10 and 13; the plan of F2, 4.3, package 6).

It stands beside F1's type (activity.py) until the windows speak it too (package 8): a server runs one of
the two (types.py: use). The build speaks it since package 7: an item names its kind, a page says what it
is of its activity (open, revealed), the deck names its kinds - which a server of this type must have
(refuses) - and keys.json the references' keys, which the deck list holds against this server's (failing).
The messages, one namespace for every kind (the design's 10.4):

    phone      activity.enter {activity, step?, entry, text | fields} -> {entry, state}, once it is written
               activity.withdraw {activity, step?, entry}
    presenter  activity.open {activity, time?: seconds}, .close, .pause, .resume, .reveal, .reset {activity}
               activity.time {activity, add: seconds | stop: true}
               activity.moderate {activity, act, group?, into?, entry?, role?, value?, on?} -> {act: its number}
               activity.undo {activity, act?: its number} -> {act}
               activity.layout {activity, at} -> {lead}     the lead window's positions of a crowd graph
    presenter, activity.view {activity} -> {picture, lead}  (a read)
    projector

What the windows get with their state (view): {current, items: {activity: {step, phase, epoch, time,
version, layout}}} - a version they were told at most four times a second; a window that has another
fetches the picture. What a phone gets: its own entries of the current step with its state (player_view:
{mine}), and the step's own part - the same for every phone - as a message of its own, serialized once:
{"t": "activity.step", "step": {...} | null} (Book.casts; app.py sends it).

One activity has one step in F2 (`main`); steps are F3's.
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import io
import json
import logging
import queue
import re
import sys
import time

from texstage.activities import registry
from texstage.activities import store as core
from texstage.activities.checks import Leave, Normalize, Run
from texstage.activities.code import words
from texstage.activities.kind import Message
from texstage.activities.phases import MARKS
from texstage.activities.phases import Refused as CoreRefused
from texstage.activities.play import MOVES, Part, Play
from texstage.activities.store import ONE, EntryRow, Writer
from texstage.checks.texts import ENGINES as TEXTS
from texstage.server.types import WRITTEN, Refused  # (first: types imports this module, and F1's, which needs it)
from texstage.server import activity as f1  # noqa: I001

log = logging.getLogger("texstage.activities")

NAME = "activity"
STATE = "activities"                # the type's part of a game's stage - not F1's "activity", which stays as F1 left it
MESSAGES = ("activity.open", "activity.close", "activity.pause", "activity.resume", "activity.reveal",
            "activity.reset", "activity.time", "activity.moderate", "activity.undo", "activity.view", "activity.layout")
READS = ("activity.view",)
QUIET = ("activity.layout",)                               # in bulk: the windows soon
PLAYER_MESSAGES = ("activity.enter", "activity.withdraw")
FILE_TYPES = f1.FILE_TYPES
FILES = f1.FILES                                           # a kind's seed, as the pictures are served
ARCHIVE = f1.ARCHIVE
LEASE_MS = 15_000                   # the lead window's: as long after each layout it sends
STEP_EVERY_MS = 1_000               # the phones get the step's part anew at most this often - at once when it moves
TIME_MAX_S = 4 * 60 * 60


def act_name(bundle_id: str, aid: str) -> str:
    return f"{bundle_id}/{aid}"


class Book:
    """The core of every game on this server: each game's Play, the writer that commits their rows, the
    pool's answers as they come, the lead windows' leases, and what the phones are to be sent."""

    def __init__(self):
        self.checks = None                               # the engine's: checking.py's Checks, whose pool it is
        self.engine = None
        self.writer: Writer | None = None
        self.plays: dict[str, Play] = {}
        self.parts: dict[tuple[str, str], Part] = {}     # (a build, an activity)
        self.inbox: queue.SimpleQueue = queue.SimpleQueue()
        self.prepared: dict[str, dict] = {}              # act -> {bundle, aid, outcomes: None until known, failed}
        self.asked: dict[tuple[str, str, str, str], tuple[str, str]] = {}    # (game, activity, step, norm) -> (act, text)
        self.leads: dict[tuple[str, str], tuple[str, int]] = {}             # (game, activity) -> (connection, until)
        self.steps: dict[str, tuple[str, int]] = {}      # game -> the step's part as it was sent last, and when
        self.casts: dict[str, str] = {}                  # game -> what every phone of it is to be sent now
        self.rounds: dict[str, bool] = {}                # game -> whether a quiz round runs, as its steps know it
        self.late: set[str] = set()                      # games whose windows a refused message left untold
        self.faulty: set[str] = set()                    # games whose tick failed, and was said so

    # -------------------------------------------------------------- the engine's
    def load(self, rows: list) -> None:
        """(The type has no rows of the server's store: its tables are the core's own - begin.)"""

    def begin(self, engine) -> None:
        """Once the engine has its games: the core's tables, the writer, and every game as the tables have
        it - a game of F1's moved first (activities/store.py: move), before any act is in memory."""
        self.engine = engine
        db = engine.store.db if engine.store is not None else None
        if db is None:
            return
        core.create(db)
        self.writer = Writer(db, lost=lambda row, why: log.error("a row no commit takes is set aside - %s: %r", why, row))
        sessions = list(engine.sessions)
        if not sessions:
            return
        now = int(time.time() * 1000)
        have = {st.session for st in core.load(db, sessions).steps}
        stages = {s.id: s.stage for s in engine.sessions.values() if s.id not in have and s.stage.get(f1.NAME)}
        for sid, stage in stages.items():                # a game at a time: one that does not move takes none
            b = engine.bundles.get(engine.sessions[sid].bundle)      # of the others' rows back with it
            try:
                moved = core.move(db, {sid: stage}, {sid: (b.items.get(NAME) or {}) if b is not None else {}})
                if any(moved.values()):
                    log.info("activities: the game %s moved from F1's tables: %s", sid, moved)
            except Exception:  # noqa: BLE001 - it starts empty; the server starts
                log.exception("activities: F1's rows of the game %s did not move", sid)
        loaded = core.load(db, sessions)
        for sid in {r.session for rows in (loaded.steps, loaded.entries) for r in rows}:
            mine = [[r for r in rows if r.session == sid] for rows in
                    (loaded.steps, loaded.entries, loaded.checks, loaded.details, loaded.moderation)]
            self.rounds[sid] = engine.round_on(sid)
            try:
                self.play(sid).load(*mine, now=now, round_on=self.rounds[sid])
            except Exception:  # noqa: BLE001 - one game's rows: the others load
                log.exception("activities: the game %s did not load", sid)
                self.plays.pop(sid, None)

    def forget(self, sid: str) -> None:
        self.plays.pop(sid, None)
        self.steps.pop(sid, None)
        self.casts.pop(sid, None)
        self.rounds.pop(sid, None)
        for key in [k for k in self.leads if k[0] == sid]:
            del self.leads[key]
        for key in [k for k in self.asked if k[0] == sid]:
            asked = self.asked.pop(key)
            if self.pool is not None:                    # what waited for the game alone leaves the queue
                self.pool.withdraw(*asked)
        self.late.discard(sid)
        self.faulty.discard(sid)

    def left(self, conn: str) -> None:
        """A window has gone: what it led, another may."""
        for key in [k for k, (holder, _) in self.leads.items() if holder == conn]:
            del self.leads[key]

    def release(self, bundle_id: str) -> None:
        """The build's last game ended: the pool lets go of its activities."""
        for act in [a for a, p in self.prepared.items() if p["bundle"] == bundle_id]:
            del self.prepared[act]
            if self.pool is not None:
                self.pool.drop(act)
        for key in [k for k in self.parts if k[0] == bundle_id]:
            del self.parts[key]

    # -------------------------------------------------------------- a game's core, a deck's parts
    @property
    def pool(self):
        return getattr(self.checks, "pool", None)

    def play(self, sid: str) -> Play:
        if sid not in self.plays:
            save = self.writer.put if self.writer is not None else None
            self.plays[sid] = Play(sid, save=save, ask=lambda jobs, sid=sid: self._ask(sid, jobs))
            self._known(sid)
        return self.plays[sid]

    def _known(self, sid: str) -> None:
        """A game's core is made: the references of its deck that are known are its own at once - the pool
        prepared the deck when the game came, long before anybody touched an activity (the review: they
        were given only to a game that had its core by then, and a deck's first game had no verdicts)."""
        s = self.engine.sessions.get(sid) if self.engine is not None else None
        for p in self.prepared.values():
            if s is not None and p["bundle"] == s.bundle and p["outcomes"] is not None:
                self.plays[sid].refer(p["aid"], p["outcomes"])

    def problems(self, bundle_id: str) -> dict[str, str]:
        """Why the pool cannot check an activity of the build: {activity: why} - it is broken, or the
        activity's preparing failed: its seed does not load, its kind is not installed. The windows say
        so (the engine's host view, and the panel's picture), as F1's do."""
        broken = getattr(self.pool, "broken", None)
        return {p["aid"]: broken or p["failed"] for p in self.prepared.values()
                if p["bundle"] == bundle_id and (broken or p["failed"])}

    def failing(self, bundle_id: str) -> list[dict]:
        """The build's references that do not run here, or give another result than when the deck was built -
        another SQLite, say (the design's 9): [{activity, reference (from 1), error}], which the deck list
        says, before the lecture too, once a game of the deck has had it prepared."""
        out = []
        for p in self.prepared.values():
            if p["bundle"] != bundle_id or not p["outcomes"]:
                continue
            part = self.parts.get((bundle_id, p["aid"]))
            built = (part.keys.get("referenceKeys") if part is not None else None) or []
            b = self.engine.bundles.get(bundle_id) if self.engine is not None else None
            for i, o in enumerate(p["outcomes"]):
                if not isinstance(o, dict) or o.get("status") != "ok":
                    out.append({"activity": p["aid"], "reference": i + 1,
                                "error": _said(o, b.language if b is not None else None)})
                elif i < len(built) and isinstance(built[i], str) and o.get("key") != built[i]:
                    out.append({"activity": p["aid"], "reference": i + 1,       # (None: it gave two at build)
                                "error": "it gives another result here than when the deck was built - another "
                                         "engine (another SQLite, say), or data that change from day to day; "
                                         "the verdicts are this server's"})
        return out

    def part(self, bundle_id: str, aid: str, item: dict, keys: dict | None) -> Part:
        key = (bundle_id, aid)
        if key not in self.parts:
            self.parts[key] = Part.of(aid, item, keys or {})
        return self.parts[key]

    def lead(self, sid: str, aid: str, conn: str | None, now: int, take: bool = False, free: bool = False) -> bool:
        """Whether this window leads the activity's layout - the first presenter window that sends one,
        for LEASE_MS after each it sends. free: or could, since nobody does; take: it sends one now."""
        holder = self.leads.get((sid, aid))
        if holder is not None and holder[1] <= now:
            holder = None
        if conn is None or (holder is not None and holder[0] != conn):
            return False
        if take:
            self.leads[(sid, aid)] = (conn, now + LEASE_MS)
        return take or free or holder is not None

    # -------------------------------------------------------------- to the pool
    def _wake(self, item: tuple) -> None:
        """From any thread - a future's callback runs on the pool's, or at once when it is done already."""
        self.inbox.put(item)
        try:
            getattr(self.checks, "wake", lambda: None)()
        except RuntimeError:                             # the event loop is closed: the server stops
            pass

    def prepare(self, b) -> None:
        """Every activity of the deck's build, once: prepared by its kind on every process of the pool, its
        references checked before any of its texts."""
        if b is None or self.pool is None:
            return
        keys = (b.keys.get("items") or {}).get(NAME) or {}
        for aid, item in (b.items.get(NAME) or {}).items():
            act = act_name(b.id, aid)
            if act in self.prepared:
                continue
            self.prepared[act] = {"bundle": b.id, "aid": aid, "outcomes": None, "failed": None}
            try:
                part = self.part(b.id, aid, item, keys.get(aid))
                files = {}
                if item.get("seed"):
                    files[item["seed"]] = b.file(item["seed"]).read_bytes()
                fut = self.pool.prepare(act, "kind:" + part.kind.NAME, {"item": part.item, "keys": part.keys, "files": files},
                                        list(part.setup.references), b.language)
            except Exception as e:  # noqa: BLE001 - no kind, no seed, the pool closed: the activity fails (problems)
                fut = cf.Future()
                fut.set_exception(e)
            fut.add_done_callback(lambda f, act=act: self._wake(("prepared", act, f)))

    def _ask(self, sid: str, jobs: list) -> None:
        """A game's jobs (activities/checks.py) to the pool; their answers come to the inbox."""
        s = self.engine.sessions.get(sid) if self.engine is not None else None
        b = self.engine.bundles.get(s.bundle) if s is not None else None
        if b is None or self.pool is None:
            for job in jobs:                             # nobody checks: unchecked, and said so - not waiting
                self._lost(sid, job, "the server has no pool that checks")
            return
        keys = (b.keys.get("items") or {}).get(NAME) or {}
        for job in jobs:
            item = (b.items.get(NAME) or {}).get(job.activity)
            if item is None:
                self._lost(sid, job, "no such activity in the deck")
                continue
            act = act_name(b.id, job.activity)
            try:
                part = self.part(b.id, job.activity, item, keys.get(job.activity))
                if isinstance(job, Normalize):
                    fut = self.pool.normalize(part.kind.NAME, part.item, part.keys, job.input, b.language)
                    fut.add_done_callback(lambda f, j=job: self._wake(("normalized", sid, j.activity, j.step, j.raw, f)))
                elif isinstance(job, Run):
                    if act not in self.prepared:
                        self.prepare(b)
                    text = json.dumps(job.input, sort_keys=True)
                    self.asked[(sid, job.activity, job.step, job.norm)] = (act, text)
                    fut = self.pool.submit(act, text, owner=job.owner or None, budget_s=part.budget_s or part.kind.BUDGET_S,
                                           language=b.language)                        # (budget=: the deck's)
                    fut.add_done_callback(lambda f, j=job: self._wake(("checked", sid, j.activity, j.step, j.norm, f)))
                elif isinstance(job, Leave):
                    asked = self.asked.pop((sid, job.activity, job.step, job.norm), None)
                    if asked is not None:
                        self.pool.withdraw(*asked)
            except Exception as e:  # noqa: BLE001 - the pool closed, a kind that is gone
                log.warning("activities: a job of %s in game %s was not taken - %s: %s", job.activity, sid,
                            type(e).__name__, e)
                self._lost(sid, job, f"{type(e).__name__}: {e}")

    def _lost(self, sid: str, job, why: str) -> None:
        """A job nobody took: answered as the pool answers one it could not do, so that the entries which
        wait for it are unchecked - never waiting for ever - and the same text sent again is asked for
        again (the review: it waited, and so did every later entry of the text)."""
        if isinstance(job, Leave):
            return
        fut: cf.Future = cf.Future()
        fut.set_exception(RuntimeError(why[:300]))
        if isinstance(job, Normalize):
            self._wake(("normalized", sid, job.activity, job.step, job.raw, fut))
        else:
            self.asked.pop((sid, job.activity, job.step, job.norm), None)
            self._wake(("checked", sid, job.activity, job.step, job.norm, fut))

    def apply(self, now: int) -> set[str]:
        """On the event loop: what the pool answered since, told to the games it is for. The games whose
        windows need their state; the phones it concerns are due (the engine's)."""
        changed: set[str] = set()
        while True:
            try:
                item = self.inbox.get_nowait()
            except queue.Empty:
                return changed
            try:
                self._apply(item, now, changed)
            except Exception:  # noqa: BLE001 - one answer: the others are applied
                log.exception("activities: an answer of the pool was not applied: %r", item[:5])

    def _apply(self, item: tuple, now: int, changed: set[str]) -> None:
        what, fut = item[0], item[-1]
        if what == "prepared":
            p = self.prepared.get(item[1])
            if p is None:
                return
            try:
                p["outcomes"] = fut.result()
            except cf.CancelledError:                    # prepared again, or dropped
                return
            except Exception as e:  # noqa: BLE001 - the seed does not load, no such kind: the windows say so
                p["failed"] = str(e).split("\n")[0][:300] or type(e).__name__                    # (problems)
                log.warning("activities: %s is not prepared: %s", item[1], p["failed"])
            for s in self.engine.sessions.values():
                if s.bundle != p["bundle"]:
                    continue
                changed.add(s.id)                        # (its host view says what failed)
                if s.id in self.plays:                   # a game without a core yet gets them with it (_known)
                    self.plays[s.id].refer(p["aid"], p["outcomes"] or [])
                    self.engine._due(s.id, True)         # a verdict a phone may have now: after a reveal, or
            return                                       # with feedback=verdict (the review: no phone was told)
        _, sid, aid, step, name = item[:5]
        play = self.plays.get(sid)
        if play is None:
            return
        try:
            answer = fut.result()
        except cf.CancelledError:                        # nobody waits for it any more (Leave)
            return
        except Exception as e:  # noqa: BLE001 - the pool's own failure: never the student's
            answer = {"status": "internal", "error": str(e)[:300]}
        if what == "normalized":
            entries = play.normalized(aid, step, name, answer if "status" not in answer else {}, now=now)
        else:
            self.asked.pop((sid, aid, step, name), None)
            entries = play.checked(aid, step, name, _fit(self._kind(sid, aid), answer), now=now)
        self.engine._due(sid, {e.player for e in entries})
        changed.add(sid)

    def _kind(self, sid: str, aid: str):
        s = self.engine.sessions.get(sid)
        part = self.parts.get((s.bundle, aid)) if s is not None else None
        return part.kind if part is not None else None


MEMORY = {catalog["tooMuchMemory"] for catalog in TEXTS.values()}      # the pool's words for it, in every language


def _said(outcome, language: str | None) -> str:
    """What a reference's check said, in words (the engines' texts; a kind's own code as it is)."""
    if not isinstance(outcome, dict):
        return repr(outcome)[:300]
    m = outcome.get("message")
    if isinstance(m, dict) and isinstance(m.get("code"), str):
        try:
            return words(Message(m["code"], dict(m.get("args") or {})), language)
        except (KeyError, IndexError, ValueError):
            return f"{outcome.get('status')}: {m['code']}"
    return str(outcome.get("error") or outcome.get("status"))[:300]


PRE = re.compile(r"[-_.]?(a|b|c|rc|alpha|beta|pre|preview|dev)", re.IGNORECASE)


def _version(text) -> tuple[int, ...]:
    """A package's version, to compare: its numbers, four of them - 1.2 is 1.2.0 -, then 0 for a release before
    it (1.2.0rc1, 1.2.0.dev3) and 1 for the release; () where it begins with no number."""
    m = re.match(r"(\d+(?:\.\d+)*)(.*)", str(text or "").strip())
    if not m:
        return ()
    numbers = tuple(int(n) for n in m.group(1).split("."))[:4]
    return numbers + (0,) * (4 - len(numbers)) + (0 if PRE.match(m.group(2)) else 1,)


def refuses(deck: dict) -> str | None:
    """Why this server cannot play the deck's activities: a kind the deck names (deck.json's kinds, as the
    build had them) that it lacks, cannot use, or has with another API, another major version or an older
    version than the build's - whose keys it may not know (the design's 7.2) -, and which package to
    install. A deck built before kinds were named has none, and is played as before."""
    wanted = deck.get("kinds")
    if not wanted:
        return None
    if not isinstance(wanted, dict):
        return "deck.json's kinds are no table of kinds"
    found = {f.name: f for f in registry.found()}
    for name, need in sorted(wanted.items()):
        need = need if isinstance(need, dict) else {}
        package, version, api = need.get("package") or "its package", str(need.get("version") or ""), need.get("api")
        install = f"install {package}{f' {version} or later' if version else ''} where the server runs"
        f = found.get(name)
        if f is None:
            return f"the deck's activities are of the kind {name}, which this server does not have - {install}"
        if f.kind is None:
            return f"the deck's activities are of the kind {name}, which this server's {f.package} {f.version} " \
                   f"cannot be used for: {f.fault}"
        if api is not None and f.api != api:
            return f"the deck's activities are of the kind {name} with API {api}, this server's {f.package} " \
                   f"{f.version} has API {f.api} - {install}"
        have, built = _version(f.version), _version(version)
        if have and built and (have[0] != built[0] or have < built):
            return f"the deck's activities are of the kind {name} of {package} {version}, this server has " \
                   f"{f.version} - {install}"
    return None


def failing(book, s) -> list[dict]:
    """The references of a game's deck that fail, for the deck list (types.py: failing)."""
    return book.failing(s.bundle) if book is not None and s is not None else []


def _fit(kind, outcome: dict) -> dict:
    """An outcome as the core takes it (activities/checks.py: checked). The pool's own - a text that needs
    too much memory, a check it could not make - have its words (`error`), where a kind's have a
    message: the kind's own code for it if it has one, else none - a student is told a status."""
    if "error" not in outcome or "message" in outcome:
        return outcome
    out = {k: v for k, v in outcome.items() if k != "error"}
    codes = getattr(kind, "MESSAGES", {}) or {}
    if outcome.get("status") == "error" and "tooMuchMemory" in codes and outcome["error"] in MEMORY:
        out["message"] = {"code": "tooMuchMemory", "args": {}}
    elif outcome.get("status") == "error" and "engine" in codes:
        out["message"] = {"code": "engine", "args": {"text": str(outcome["error"])[:300]}}
    return out


# ------------------------------------------------------------------ what a hook reads of its call
def _aid(call, msg: dict) -> str:
    aid = msg.get("activity")
    if not isinstance(aid, str) or aid not in call.items:
        raise Refused("no such activity in this deck")
    if msg.get("step", ONE) != ONE:
        raise Refused("an activity has one step")
    return aid


def _part(call, aid: str) -> Part:
    try:
        return call.book.part(call.session.bundle, aid, call.items[aid], call.keys.get(aid))
    except (LookupError, ValueError) as e:               # its kind is not installed; its item is not the core's
        raise Refused(str(e)) from None


def _play(call) -> Play:
    return call.book.play(call.session.id)


def _seconds(v, what: str) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 1 <= v <= TIME_MAX_S:
        raise Refused(f"{what}: 1 second to {TIME_MAX_S // 3600} hours", "time")
    return round(v * 1000)


def _told(call, play: Play, moved: bool = False) -> bool:
    """The type's part of the game's stage, as the windows have it: each step the game's core knows - one
    that moved, or was looked at -, with the version the windows are told now. Whether it changed. moved: a step moved - every phone gets its
    state, and the step's part at once."""
    old = call.session.stage.get(STATE) or {}
    items = {}
    for (aid, step), st in play.phases.steps.items():
        if aid not in call.items:
            continue
        was = (old.get("items") or {}).get(aid) or {}
        told = play.told(aid, call.now, step)
        # a time that runs is told once, with when it was read: a window counts on from there. Told anew
        # with every tick, every window and every phone would get its state ten times a second
        same = (was.get("phase"), was.get("epoch"), was.get("time") is None) == (st.phase, st.epoch, st.time_left is None)
        if moved or not same:
            left, since = st.time_left, call.now
        else:
            left, since = was.get("time"), was.get("since")
        items[aid] = {"step": step, "phase": st.phase, "epoch": st.epoch, "time": left, "since": since,
                      "version": told["version"] if told else was.get("version", 0),
                      "layout": told["layout"] if told else was.get("layout", 0)}
    current = play.phases.current()
    new = {"current": current.activity if current is not None and current.activity in call.items else None,
           "items": items}
    _cast(call, play, items, moved)
    if moved:
        call.phones = True
    if new == old:
        return False
    call.session.stage = {**call.session.stage, STATE: new}
    return True


def _cast(call, play: Play, items: dict, now: bool) -> None:
    """The step's own part for the phones, when it is another than they have - at once (now) when a step
    moved, else at most every STEP_EVERY_MS: what a field offers grows with the graph. Its time is the
    one the windows are told, with when it was read (_told)."""
    current = play.phases.current()
    part = None
    if current is not None and current.activity in call.items:
        try:
            part = play.step_part(_part(call, current.activity), current.step)
            part |= {"time": items[current.activity]["time"], "since": items[current.activity]["since"]}
        except Refused:
            part = None
    text = json.dumps({"t": "activity.step", "step": part}, ensure_ascii=False, separators=(",", ":"))
    last = call.book.steps.get(call.session.id)
    if last is not None and (last[0] == text or (not now and call.now - last[1] < STEP_EVERY_MS)):
        return
    if last is None and part is None:
        return
    call.book.steps[call.session.id] = (text, call.now)
    call.book.casts[call.session.id] = text


def _refused(e: CoreRefused) -> Refused:
    return Refused(str(e), e.code)


def _late(call) -> None:
    """A step changed, and the message that found it so may be refused - its time ran out as a phone sent
    or as the lecturer pressed Pause: the engine and the app tell nobody after a refusal, so the phones
    are due here, and the windows with the next tick (the review: the panel showed "open" at 0:00)."""
    call.book.late.add(call.session.id)
    if call.book.engine is not None:
        call.book.engine._due(call.session.id, True)


# ------------------------------------------------------------------ the windows
def view(stage: dict) -> dict | None:
    return stage.get(STATE) or None


def slide(stage: dict, items: dict, before: tuple, after: tuple, now: int) -> dict:
    """(The engine asks shown, which has the game.)"""
    return stage


def shown(call, before: tuple, after: tuple, marks: dict | None = None) -> None:
    """The projector shows another slide (the design's 8.2): an activity whose frame it leaves closes; one
    whose page comes for the first time opens - with the deck's time= -, unless the deck opens it by hand
    (open=manual); a page the build marks revealed (\\reveal<n>) reveals it, if it was opened. marks: what
    the new page is of each activity it shows - a deck built before package 7 has none: every page of an
    activity opens it."""
    here = [aid for aid in (*before, *after) if aid in call.items]
    if not here or (call.session.id not in call.book.plays and not any(aid in call.items for aid in after)):
        return
    play = _play(call)
    marks = marks or {}
    manual = [(aid, ONE) for aid in here if call.items[aid].get("open", "auto") != "auto"]
    times = {}
    for aid in after:
        if aid in call.items:
            try:
                time_ms = _part(call, aid).time_ms
            except Refused:                              # its kind is not here: it opens without (and fails)
                time_ms = None
            if time_ms is not None:
                times[(aid, ONE)] = time_ms
    rows = play.move("slide", [(aid, ONE, "open") for aid in before if aid in call.items],
                     [(aid, ONE, marks[aid] if marks.get(aid) in MARKS else "open") for aid in after if aid in call.items],
                     now=call.now, manual=manual, times=times)
    _told(call, play, moved=bool(rows))


def handle(call, t: str, msg: dict) -> dict | None:
    aid = _aid(call, msg)
    part, play, sid = _part(call, aid), _play(call), call.session.id
    if t == "activity.view":
        window = "stage" if call.role == "stage" else "display"
        reply = {"picture": play.picture(part, window), "lead": call.book.lead(sid, aid, call.conn, call.now)}
        writer = call.book.writer
        if window == "stage" and writer is not None and (writer.error or writer.dropped):
            reply["store"] = {"failures": writer.failures, "error": writer.error, "set_aside": writer.dropped}
        failed = call.book.problems(call.session.bundle).get(aid)
        if window == "stage" and failed:                 # why nothing of it is checked
            reply["failed"] = failed
        return reply
    if t == "activity.layout":
        call.changed = False
        if not call.book.lead(sid, aid, call.conn, call.now, free=True):
            return {"lead": False}
        try:
            play.layout(part, msg.get("at"))             # (a layout that is none takes no lease)
        except CoreRefused as e:
            raise _refused(e) from None
        _told(call, play)
        return {"lead": call.book.lead(sid, aid, call.conn, call.now, take=True)}
    name = t.split(".", 1)[1]
    try:
        if name in MOVES:
            more = {}
            if name == "open" and msg.get("time") is not None:
                more["time_ms"] = _seconds(msg["time"], "a step's time")
            elif name == "open" and part.time_ms is not None:      # the deck's time=, for the step's first opening
                st = play.phases.get(aid, ONE)
                if st is None or st.phase == "ready":
                    more["time_ms"] = part.time_ms
            elif name == "time":
                more = {"stop": True} if msg.get("stop") is True else {"add_ms": _seconds(msg.get("add"), "more time")}
            rows = play.move(name, aid, now=call.now, **more)
            _told(call, play, moved=bool(rows) or name == "time")
            return None
        if name == "undo":
            n = msg.get("act")
            if n is not None and (isinstance(n, bool) or not isinstance(n, int)):
                raise Refused("act: an act's number")
            done = play.undo(part, n, now=call.now)
        else:
            on = msg.get("on", True)
            if not isinstance(on, bool):
                raise Refused("on: true or false")
            done = play.act(part, msg.get("act"), target=msg.get("group"), role=msg.get("role", "node"),
                            onto=msg.get("into"), entry=msg.get("entry"), off=not on, value=msg.get("value"), now=call.now)
    except CoreRefused as e:
        if e.changed:                                    # the time ran out as the lecturer pressed Pause
            _told(call, play, moved=True)
            _late(call)
        raise _refused(e) from None
    _told(call, play)
    if done.player:
        call.phones = {done.player}                      # the student who is blocked, or is no more
    return {"act": done.row.n if done.row is not None else None}


def pulse(engine, now: int) -> set[str]:
    """The server's tick, a few times a second: every game's steps - a time that ran out closes its
    step -, and what the windows and the phones are to be told now. The games whose windows need their
    state."""
    book = engine.books[NAME]
    changed = book.apply(now)                            # (answers nobody woke the engine for: a job not taken)
    for sid, play in list(book.plays.items()):
        s = engine.sessions.get(sid)
        if s is None:
            continue
        try:
            call = engine._call(s, sys.modules[__name__], now)
        except Exception:  # noqa: BLE001 - its deck is not on this server any more
            continue
        try:
            rows = play.tick(now)
            on = engine.round_on(sid)                    # a quiz round pauses the step that runs; its end resumes it
            if book.rounds.get(sid, False) != on:
                book.rounds[sid] = on
                rows += play.move("round", on, now=now)
            if _told(call, play, moved=bool(rows)):
                changed.add(sid)
            engine._due(sid, call.phones)
        except Exception:  # noqa: BLE001 - one game's fault: the others' time goes on (said once a game)
            if sid not in book.faulty:
                book.faulty.add(sid)
                log.exception("activities: the tick of the game %s failed", sid)
    changed |= {sid for sid in book.late if sid in engine.sessions}
    book.late.clear()
    return changed


def deck(call, b) -> None:
    """A game of a deck: the pool prepares the deck's activities. Their references are the game's once it
    has a core (Book: _known), or as they come."""
    call.book.prepare(b)


def resume(call) -> None:
    """The server started again: what was unchecked in the game is asked for."""
    if call.session.id in call.book.plays:
        _play(call).again()


# ------------------------------------------------------------------ the phones
def player(call, t: str, msg: dict) -> dict | None:
    aid = _aid(call, msg)
    part, play, p = _part(call, aid), _play(call), call.player
    call.changed = False                                 # (the entry is the writer's, not the session's)
    rows = play.tick(call.now)
    if rows:
        _told(call, play, moved=True)
        _late(call)
    try:
        if t == "activity.withdraw":
            entry = play.withdraw(part, p.id, msg.get("entry"), now=call.now)
        else:
            sent = {k: msg[k] for k in ("text", "fields") if k in msg}
            entry = play.enter(part, p.id, msg.get("entry"), sent, now=call.now, blocked=bool(p.muted)).entry
    except CoreRefused as e:
        raise _refused(e) from None
    reply = {"entry": entry.id, "state": play._shown(part, play.step(aid), entry)}
    writer = call.book.writer
    if writer is not None:                               # acknowledged once it is written (the design's 10.1)
        reply[WRITTEN] = lambda done, row=entry: writer.put(row, then=done)
    return reply


def player_view(call) -> dict | None:
    """A phone's own part of the current step: its entries, with what feedback= allows of their checks."""
    play = call.book.plays.get(call.session.id)
    current = play.phases.current() if play is not None else None
    if current is None or current.activity not in call.items:
        return None
    try:
        mine = play.mine(_part(call, current.activity), call.player.id, current.step)
    except Refused:
        return None
    mine["blocked"] = mine["blocked"] or bool(call.player.muted)
    return {"mine": mine}


# ------------------------------------------------------------------ the archive
def archive(call) -> dict[str, str]:
    """Per activity with entries: activity-<id>.csv - a row per entry with its step and epoch, without
    names -, activity-<id>.json - the step's final picture, as the panel has it - and, for a crowd graph,
    its picture as SVG (F1's graph_svg draws the core's)."""
    files: dict[str, str] = {}
    play = call.book.plays.get(call.session.id)
    if play is None:
        return files
    for aid in call.items:
        held = play.entries.held.get((aid, ONE))
        entries: list[EntryRow] = list(held.entries.values()) if held is not None else []
        if not entries:
            continue
        try:
            part = _part(call, aid)
        except Refused:
            continue
        rows = [["time", "step", "epoch", "input", "state", "status", "verdict"]]
        for e in entries:
            text = " | ".join(e.input["fields"]) if "fields" in e.input else e.input.get("text", "")
            check = play.checks.of(e)
            rows.append([time.strftime("%H:%M:%S", time.localtime(e.created / 1000)), e.step, e.epoch, text, e.state,
                         check.status if check is not None else play.checks.state(e),
                         play.reduced.verdict(aid, e.step, check) or "" if check is not None else ""])
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        files[f"activity-{aid}.csv"] = chr(0xFEFF) + buf.getvalue()
        pic = play.picture(part, "stage")
        files[f"activity-{aid}.json"] = json.dumps(pic, ensure_ascii=False, indent=1) + "\n"
        if pic.get("kind") == "graph":
            files[f"activity-{aid}.svg"] = f1.graph_svg(pic)
    return files
