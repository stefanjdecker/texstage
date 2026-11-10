# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The server's checks of live activities (docs/architecture/activity-framework-plan.md, F1, 4.5 and
4.6): the pool of worker processes (pool.py) and what goes between it and the engine (game.py). The
engine runs on the server's event loop, the pool answers on threads of its own: an answer waits in the
inbox until the engine takes it (Engine.apply_checks), and wake() - the event loop's - says it is there.

    checks = Checks("server", bundles)           # or "both"; a server in the mode browser has none
    checks.start(wake)                           # the pool starts; wake() from its threads: answers wait
    checks.prepare(bundle)                       # a game of the deck: every process loads its code activities
    checks.submit(bundle_id, aid, text, sid, owner)   # a text that waits for its check
    checks.answers()                             # what the pool answered since, on the engine's thread
    checks.again(answer)                         # one the engine could not apply: with the next ones
    checks.problems(bundle_id)                   # {activity: why the pool cannot check it}, for the windows
    checks.release(bundle_id)                    # the deck's last game ended: the processes let go of it
    checks.close()

An activity is the pool's under "<bundle>/<activity>": a deck's build prepares once, for every game of it.
One text being checked is one job, whichever games wait for it; its answer goes to each. A build whose
preparing fails - its seed does not load, the pool is broken - is the server's failure, not the
references': they are `internal`, and so is every text of it, until the server starts again.

The modes (4.6): server - the pool checks, and its outcomes count; both - the presenter window checks
and its results count, as before F1, while the pool checks the same texts and references, and every
difference of status or key goes to checks-compare.csv in the game's archive folder (compare_file).
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import io
import logging
import queue
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger("texstage.checks")

MODES = ("server", "browser", "both")
COMPARE_COLUMNS = ["time", "activity", "what", "text", "browser status", "browser key", "browser error",
                   "server status", "server key", "server error"]
AGAIN = 3                           # times an answer the engine could not apply is applied again
AGAIN_S = 1.0                       # ... this long after (app.py)


def _failed(exc: BaseException) -> cf.Future:
    fut: cf.Future = cf.Future()
    fut.set_exception(exc)
    return fut


def _resolved(value) -> cf.Future:
    fut: cf.Future = cf.Future()
    fut.set_result(value)
    return fut


def act_name(bundle_id: str, aid: str) -> str:
    return f"{bundle_id}/{aid}"


class Checks:
    def __init__(self, mode: str, bundles=None, workers: int | None = None, **pool_options):
        if mode not in ("server", "both"):
            raise ValueError(f"checks: server or both, not {mode!r} - in the mode browser the server has none")
        self.mode = mode
        self.bundles = bundles                   # .get(bundle id) -> Bundle | None (bundles.py)
        self.workers = workers
        self.pool_options = pool_options         # (the tests': engines, budgets)
        self.pool = None
        self.closed = False
        self.inbox: queue.SimpleQueue = queue.SimpleQueue()
        self.wake: Callable[[], None] = lambda: None
        self.later: list[tuple[tuple, int]] = []         # (an answer the engine could not apply, how often)
        self.tried: dict[int, int] = {}                  # this round's answers from later: id -> how often
        self.prepares: dict[str, dict] = {}      # act -> {bundle, aid, texts, future, outcomes: None until known,
                                                 #         failed: why preparing it failed, or None}
        self.waiting: dict[tuple[str, str], dict] = {}     # (act, text) -> {future, games: the sessions it is for}
        self.compare_file: Callable | None = None          # (session) -> its checks-compare.csv (app.py), mode both
        self.outcomes: dict[tuple[str, str, str], dict] = {}   # both: (act, what, text) -> the pool's outcome
        self.browser: dict[tuple[str, str, str, str], dict] = {}   # both: (sid, aid, what, text) -> the window's

    # ------------------------------------------------------------------ the pool
    def start(self, wake: Callable[[], None] | None = None) -> Checks:
        from texstage.server.pool import Pool
        self.wake = wake or (lambda: None)
        self.pool = Pool(self.workers, **self.pool_options).start()
        return self

    def close(self) -> None:
        """The pool ends. What it answers as it closes - internal: closed - is not the texts': they still
        wait, and are checked after the next start (Engine.resume_checks)."""
        self.closed = True
        self.wake = lambda: None
        if self.pool is not None:
            self.pool.close()

    def _put(self, item: tuple) -> None:
        """From any thread - a future's callback runs on the pool's, or at once when it is done already."""
        self.inbox.put(item)
        try:
            self.wake()
        except RuntimeError:                     # the event loop is closed: the server stops
            pass

    # ------------------------------------------------------------------ what the engine sends
    def prepare(self, b) -> None:
        """Every code activity of the deck's build, once: its seed loaded and its references checked on
        every process of the pool (pool.py), before any of its texts."""
        if b is None or self.pool is None:
            return
        keys = (b.keys.get("items") or {}).get("activity") or {}
        for aid, item in (b.items.get("activity") or {}).items():
            act = act_name(b.id, aid)
            if item.get("input") != "code" or act in self.prepares:
                continue
            texts = list((keys.get(aid) or {}).get("reference") or [])
            path = b.file(item["seed"]) if item.get("seed") else None
            try:
                seed = path.read_text(encoding="utf-8") if path is not None else None
            except (OSError, UnicodeDecodeError):
                seed = None
            if seed is None:
                fut = _failed(ValueError(f"the seed {item.get('seed')}: not in the bundle"))
            else:
                try:
                    fut = self.pool.prepare(act, item.get("engine"), seed, texts, b.language)
                except (ValueError, RuntimeError) as e:          # an engine the pool lacks; the pool closed
                    fut = _failed(e)
            self.prepares[act] = {"bundle": b.id, "aid": aid, "texts": texts, "future": fut, "outcomes": None,
                                  "failed": None}
            fut.add_done_callback(lambda f, act=act: self._put(("prepared", act, f)))

    def submit(self, bundle_id: str, aid: str, text: str, sid: str, owner: str | None = None) -> None:
        """A text that waits in a game: to the pool, unless it is being checked already - then its answer
        comes for this game too. owner: the student, who takes turns with the others (pool.py)."""
        if self.pool is None:
            return
        act = act_name(bundle_id, aid)
        entry = self.waiting.get((act, text))
        if entry is not None:
            entry["games"].add(sid)
            return
        b = self.bundles.get(bundle_id) if self.bundles is not None else None
        if act not in self.prepares:
            self.prepare(b)
        try:
            fut = self.pool.submit(act, text, owner=owner, language=b.language if b is not None else None)
        except (RuntimeError, ValueError) as e:                  # the pool closed
            fut = _resolved({"status": "internal", "error": str(e)})
        entry = self.waiting[(act, text)] = {"future": fut, "games": {sid}}
        fut.add_done_callback(lambda f: self._put(("checked", act, text, f)))

    def release(self, bundle_id: str) -> None:
        """The deck's build has no game any more: the pool's processes let go of its activities."""
        for act in [a for a, p in self.prepares.items() if p["bundle"] == bundle_id]:
            del self.prepares[act]
            if self.pool is not None:
                self.pool.drop(act)
        prefix = bundle_id + "/"
        for k in [k for k in self.waiting if k[0].startswith(prefix)]:
            del self.waiting[k]
        for k in [k for k in self.outcomes if k[0].startswith(prefix)]:
            del self.outcomes[k]
        self.later = [(a, n) for a, n in self.later if a[1] != bundle_id]

    # ------------------------------------------------------------------ what the pool answers
    def answers(self) -> list[tuple]:
        """What the pool answered since, on the engine's thread - first those the engine could not apply
        last time (again):
            ("references", bundle, aid, outcomes, failed)   outcomes: one per reference, in their order;
                                                            failed: why preparing failed, or None
            ("text", bundle, aid, text, outcome, games)     games: the sessions whose texts wait for it
        What answers a prepare or a check that was let go of meanwhile is left out."""
        retried, self.later = self.later, []
        self.tried = {id(a): n for a, n in retried}
        out = [a for a, _ in retried]
        while True:
            try:
                item = self.inbox.get_nowait()
            except queue.Empty:
                return [] if self.closed else out
            if item[0] == "prepared":
                _, act, fut = item
                p = self.prepares.get(act)
                if p is None or p["future"] is not fut or fut.cancelled():
                    continue
                try:
                    outcomes = fut.result()
                except Exception as e:  # noqa: BLE001 - the seed does not load, the pool is closed or broken
                    why = str(e).split("\n")[0] or type(e).__name__
                    p["failed"] = why                    # the server's failure, not the references' (the
                    outcomes = [{"status": "internal", "error": why} for _ in p["texts"]]   # package 4 review)
                    log.warning("checks: %s not prepared: %s", act, why)
                p["outcomes"] = outcomes
                out.append(("references", p["bundle"], p["aid"], outcomes, p["failed"]))
            else:
                _, act, text, fut = item
                entry = self.waiting.get((act, text))
                if entry is None or entry["future"] is not fut:
                    continue
                del self.waiting[(act, text)]
                try:
                    outcome = fut.result()
                except Exception as e:  # noqa: BLE001 - never the student's fault
                    outcome = {"status": "internal", "error": str(e).split("\n")[0] or type(e).__name__}
                bundle, aid = act.split("/", 1)
                out.append(("text", bundle, aid, text, outcome, entry["games"]))

    def again(self, answer: tuple) -> bool:
        """An answer of this round the engine could not apply - its own error, the store's, not the
        answer's: it comes again with the next round, at most AGAIN times (the package 4 review: else
        one such answer lost its whole round, whose texts waited until a restart). Whether it will."""
        n = self.tried.get(id(answer), 0) + 1
        if n > AGAIN or self.closed:
            log.error("checks: an answer given up after %d tries: %s", AGAIN, answer[:3])
            return False
        self.later.append((answer, n))
        return True

    def references(self, bundle_id: str, aid: str) -> list[dict] | None:
        """The references' outcomes of an activity, once the pool has prepared it."""
        p = self.prepares.get(act_name(bundle_id, aid))
        return p["outcomes"] if p is not None else None

    def problems(self, bundle_id: str) -> dict[str, str]:
        """Why the pool cannot check a code activity of the build: {activity: why} - it is broken, or the
        activity's preparing failed. The presenter window says so (the package 4 review: else nothing
        told the lecturer, and every text counted as waiting)."""
        broken = getattr(self.pool, "broken", None)
        return {p["aid"]: broken or p["failed"] for p in self.prepares.values()
                if p["bundle"] == bundle_id and (broken or p["failed"])}

    # ------------------------------------------------------------------ the mode both
    def compare(self, s, aid: str, what: str, text: str, browser: dict | None = None,
                server: dict | None = None) -> None:
        """One side's outcome of a text or a reference (what: "text", "reference 1", ...) in a game: when
        both sides have answered, a difference of status or key goes to the game's checks-compare.csv."""
        act = act_name(s.bundle, aid)
        if server is not None:
            self.outcomes[(act, what, text)] = server
        if browser is not None:
            self.browser[(s.id, aid, what, text)] = browser
        server = self.outcomes.get((act, what, text))
        browser = self.browser.get((s.id, aid, what, text))
        if server is None or browser is None:
            return
        del self.browser[(s.id, aid, what, text)]
        b_key = browser.get("key") if browser.get("status") == "ok" else ""
        s_key = server.get("key") if server.get("status") == "ok" else ""
        if (browser.get("status"), b_key) == (server.get("status"), s_key) or self.compare_file is None:
            return
        row = [time.strftime("%H:%M:%S"), aid, what, text, browser.get("status"), b_key, browser.get("error") or "",
               server.get("status"), s_key, server.get("error") or ""]
        try:
            path = Path(self.compare_file(s))
            new = not path.exists()
            buf = io.StringIO()
            csv.writer(buf).writerows(([COMPARE_COLUMNS] if new else []) + [row])
            with path.open("a", encoding="utf-8", newline="") as f:
                f.write(("\ufeff" if new else "") + buf.getvalue())
        except OSError:
            log.exception("checks: writing a difference to checks-compare.csv")
