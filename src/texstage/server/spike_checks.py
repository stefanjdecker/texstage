# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""F0's spike (docs/architecture/activity-framework-plan.md, 3.3) - on the branch f0-spike only.

The server checks a waiting text in the pool of tools/spike/pool.py instead of handing it to the
presenter window's evaluator: activity.work then hands out no jobs, and each result is applied as the
evaluator's would be (activity.checked, game.py Engine.activity_checked), then pushed. On when the
environment has TEXSTAGE_SPIKE_POOL - its value the number of workers, empty for the default.
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("texstage.spike")
ROOT = Path(__file__).resolve().parents[3]
KEY = re.compile(r"[0-9a-f]{16}")
STATUSES = ("ok", "syntax", "error", "timeout", "refused")   # today's (activity.py); F1 adds internal


class Checker:
    def __init__(self, server, workers: int | None):
        sys.path.insert(0, str(ROOT / "tools" / "spike"))
        import pool as spike_pool

        self.server, self.loop = server, asyncio.get_running_loop()
        self.pool = spike_pool.Pool(workers or None)
        self.pool.start()
        self.state: dict[str, str] = {}           # act -> "preparing" | "ready"
        self.later: dict[str, list] = {}          # act -> (sid, aid, text) waiting for the prepare
        self.inflight: set[tuple] = set()
        self.stats = {"submitted": 0, "applied": 0, "failed": 0}
        log.info("spike: %d workers and a spare check the activities", self.pool.n)

    def prepare(self, session, aid: str, item: dict, refs: list[str]) -> str:
        b = self.server.engine.bundle(session)
        act = f"{b.id}/{aid}"
        if act in self.state:
            return act
        self.state[act] = "preparing"
        path = b.file(item["seed"]) if item.get("seed") else None
        seed = path.read_text(encoding="utf-8") if path else ""
        sid = session.id

        def run():
            try:
                self.pool.prepare(act, item["engine"], seed, refs)
                keys = self.pool.refs.get(act) or []
            except Exception:  # noqa: BLE001
                log.exception("spike: preparing %s failed", act)
                keys = []
            self.loop.call_soon_threadsafe(self._prepared, sid, aid, act, keys)

        threading.Thread(target=run, daemon=True).start()
        return act

    def _prepared(self, sid: str, aid: str, act: str, keys: list):
        self.state[act] = "ready"
        for i, k in enumerate(keys):
            ok = isinstance(k, str) and KEY.fullmatch(k)
            status = "ok" if ok else (k if k in STATUSES else "error")
            self.apply(sid, aid, {"reference": i, "status": status, "key": k if ok else None, "error": ""})
        for sid2, aid2, text, owner in self.later.pop(act, []):
            self._submit(sid2, aid2, act, text, owner)

    def submit(self, session, aid: str, item: dict, refs: list[str], text: str, owner: str | None = None):
        """A waiting text to the pool; owner, the student who sent it first, takes turns with the others."""
        act = self.prepare(session, aid, item, refs)
        if self.state.get(act) != "ready":
            self.later.setdefault(act, []).append((session.id, aid, text, owner))
        else:
            self._submit(session.id, aid, act, text, owner)

    def _submit(self, sid: str, aid: str, act: str, text: str, owner: str | None = None):
        if (sid, aid, text) in self.inflight:
            return
        self.inflight.add((sid, aid, text))
        self.stats["submitted"] += 1
        fut = self.pool.submit(act, None, text, owner=f"{sid}/{owner}" if owner else None)
        fut.add_done_callback(lambda f: self.loop.call_soon_threadsafe(self._done, sid, aid, text, f))

    def _done(self, sid: str, aid: str, text: str, fut):
        self.inflight.discard((sid, aid, text))
        try:
            r = fut.result()
        except Exception as e:  # noqa: BLE001
            r = {"status": "internal", "error": str(e)}
        status = r.get("status")
        if status not in STATUSES:                   # internal: never the student's fault - it stays
            self.stats["unchecked"] = self.stats.get("unchecked", 0) + 1     # waiting (F1 gives it a
            log.warning("spike: a text could not be checked (%s)", r.get("error"))   # status of its own)
            return
        self.apply(sid, aid, {"text": text, "status": status, "key": r.get("key") if status == "ok" else None,
                              "error": r.get("error") or ""})

    def apply(self, sid: str, aid: str, msg: dict):
        try:
            self.server.engine.activity_checked(sid, aid, msg, int(time.time() * 1000))
        except Exception:  # noqa: BLE001
            self.stats["failed"] += 1
            log.exception("spike: applying a check failed")
            return
        self.stats["applied"] += 1
        self.server.dirty.add(sid)
        self.server.push_due()

    def close(self):
        log.info("spike: %s", self.stats)
        self.pool.close()


CHECKER: Checker | None = None


def start(server, workers: int | None):
    global CHECKER
    from texstage.server import activity
    CHECKER = Checker(server, workers)
    activity.CHECKER = CHECKER


def stop():
    if CHECKER is not None:
        CHECKER.close()
