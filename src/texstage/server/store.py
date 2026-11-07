# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Persistence: an SQLite file, written through by the engine (game.py).

Everything lives in memory; every change is also saved here, one transaction per engine
call, so a restarted server continues where it stopped: sessions that have not ended, their
players (with their tokens' hashes - the phones reconnect), rounds with their deadlines
and all answers. An answer is inserted (never replaced): one per round and player. A rewind
(Engine.again) deletes the rounds it withdraws, with their answers. texstage's ink: every
ended stroke, kept when erased (erased: when). texstage M6: a game's ad-hoc polls (sessions.
polls), the questions from the audience (questions, a row each, with its votes) and who may
not ask any more (players.muted).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from texstage.server import types as stage_types
from texstage.server.game import Answer, Player, Round, Session
from texstage.server.activity_points import ActivityPoints
from texstage.server.ink import Stroke
from texstage.server.qa import Asked

TABLES = {
    ActivityPoints: ("activity_points", ["session", "kind", "item", "epoch", "revision", "published", "maximum", "awards"]),
    Session: ("sessions", ["id", "pin", "deck", "bundle", "created", "last_active", "owner", "ended",
                           "finished", "slide", "current", "stage", "polls"]),
    Player: ("players", ["id", "session", "nickname", "token_hash", "joined", "kicked", "score", "streak",
                         "total_ms", "rank", "prev_rank", "muted"]),
    Round: ("rounds", ["id", "session", "quiz", "attempt", "practice", "phase", "started", "opens", "deadline",
                       "limit_ms", "paused_left", "paused_at", "closed", "closed_by", "revealed"]),
    Answer: ("answers", ["round", "player", "payload", "received", "answer_ms", "correct", "credit", "points",
                         "bonus", "sequence"]),
    Stroke: ("strokes", ["id", "session", "frame", "device", "tool", "color", "width", "sim", "points", "created",
                         "erased"]),
    Asked: ("questions", ["id", "session", "player", "text", "created", "votes", "state"]),
}
KEYS = {"activity_points": "session, kind, item", "sessions": "id", "players": "id", "rounds": "id", "answers": "round, player", "strokes": "id",
        "questions": "id"}
JSON = {ActivityPoints: ("awards",), Session: ("stage", "polls"), Answer: ("payload",), Stroke: ("points",), Asked: ("votes",)}   # per table:
# an answer's points are a number (files of M2 to M5 stored them as JSON text too; load() reads both)
for _cls, (_table, _cols, _key, _json) in stage_types.ROWS.items():     # the content types' tables (types.py)
    TABLES[_cls], KEYS[_table], JSON[_cls] = (_table, _cols), _key, _json


class Store:
    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(str(path), check_same_thread=False)  # used by one event loop
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        for cls, (table, cols) in TABLES.items():
            self.db.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)}, PRIMARY KEY ({KEYS[table]}))")
            have = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for col in cols:
                if col not in have:                       # a file of an earlier version
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
        self.db.execute("CREATE INDEX IF NOT EXISTS players_session ON players (session)")
        self.db.execute("CREATE INDEX IF NOT EXISTS rounds_session ON rounds (session)")
        self.db.execute("CREATE INDEX IF NOT EXISTS strokes_session ON strokes (session)")
        self.db.execute("CREATE INDEX IF NOT EXISTS questions_session ON questions (session)")
        for table, _ in (TABLES[cls] for cls in stage_types.ROWS):
            self.db.execute(f"CREATE INDEX IF NOT EXISTS {table}_session ON {table} (session)")
        self.db.commit()

    @staticmethod
    def _values(item, cols):
        out, encoded = [], JSON.get(type(item), ())
        for c in cols:
            v = getattr(item, c)
            out.append(json.dumps(v) if c in encoded else int(v) if isinstance(v, bool) else v)
        return out

    def save(self, item):
        table, cols = TABLES[type(item)]
        self.db.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        self._values(item, cols))

    def insert_answer(self, a: Answer):
        table, cols = TABLES[Answer]
        self.db.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        self._values(a, cols))

    def delete_round(self, round_id: str):
        """A round withdrawn by a rewind (Engine.again), with its answers."""
        self.db.execute("DELETE FROM answers WHERE round = ?", (round_id,))
        self.db.execute("DELETE FROM rounds WHERE id = ?", (round_id,))

    def commit(self):
        self.db.commit()

    def close(self):
        if self.db is not None:
            self.db.commit()
            self.db.close()
            self.db = None

    @staticmethod
    def _session(r) -> Session:
        return Session(**{**dict(r), "owner": r["owner"] or "", "stage": json.loads(r["stage"]) if r["stage"] else {},
                          "polls": json.loads(r["polls"]) if r["polls"] else {}})

    def load(self) -> list[Session]:
        """The sessions that have not ended, with their players, rounds and answers."""
        sessions = {r["id"]: self._session(r) for r in self.db.execute("SELECT * FROM sessions WHERE ended IS NULL")}
        if not sessions:
            return []
        marks = ", ".join("?" * len(sessions))
        for r in self.db.execute(f"SELECT * FROM players WHERE session IN ({marks})", list(sessions)):
            p = Player(**{**dict(r), "kicked": bool(r["kicked"]), "muted": bool(r["muted"])})
            sessions[p.session].players[p.id] = p
        rounds = {}
        for r in self.db.execute(f"SELECT * FROM rounds WHERE session IN ({marks})", list(sessions)):
            rd = Round(**{**dict(r), "practice": bool(r["practice"])})
            sessions[rd.session].rounds[rd.id] = rounds[rd.id] = rd
        if rounds:
            rmarks = ", ".join("?" * len(rounds))
            for r in self.db.execute(f"SELECT * FROM answers WHERE round IN ({rmarks})", list(rounds)):
                correct = None if r["correct"] is None else bool(r["correct"])
                a = Answer(**{**dict(r), "payload": json.loads(r["payload"]), "correct": correct,
                              "points": int(r["points"] or 0), "sequence": int(r["sequence"] or 0)})
                rounds[a.round].answers[a.player] = a
            for rd in rounds.values():
                # Older files did not persist submission numbers; migrate once using
                # their existing display order, then keep those numbers across reveals.
                next_number = max((a.sequence for a in rd.answers.values()), default=0)
                for a in sorted(rd.answers.values(), key=lambda a: (a.received, a.player)):
                    if not a.sequence:
                        next_number += 1
                        a.sequence = next_number
                        self.save(a)
            self.db.commit()
        for r in self.db.execute(f"SELECT * FROM activity_points WHERE session IN ({marks})", list(sessions)):
            item = ActivityPoints(**{**dict(r), "published": bool(r["published"]), "awards": json.loads(r["awards"])})
            sessions[item.session].activity_points[(item.kind, item.item)] = item
        return list(sessions.values())

    def load_strokes(self, sessions: list[str]) -> list[Stroke]:
        """The ink of these games (texstage): the strokes not erased, in the order drawn."""
        if not sessions:
            return []
        marks = ", ".join("?" * len(sessions))
        rows = self.db.execute(f"SELECT * FROM strokes WHERE session IN ({marks}) AND erased IS NULL "
                               f"ORDER BY created, rowid", sessions)
        return [Stroke(**{**dict(r), "sim": bool(r["sim"]), "points": json.loads(r["points"])}) for r in rows]

    def ended_session(self, sid: str) -> Session | None:
        """A game that ended, without its players and rounds (texstage: the lecture before)."""
        r = self.db.execute("SELECT * FROM sessions WHERE id = ? AND ended IS NOT NULL", (sid,)).fetchone()
        return self._session(r) if r else None

    def last_marked(self, deck: str, bundle: str, owner: str) -> dict | None:
        """The last ended game of a deck's build and lecturer with ink or whiteboard pages:
        {id, last_active, frames, boards} (texstage: the lecture before)."""
        rows = self.db.execute("SELECT id, last_active, stage FROM sessions WHERE deck = ? AND bundle = ? "
                               "AND COALESCE(owner, '') = ? AND ended IS NOT NULL ORDER BY ended DESC LIMIT 20",
                               (deck, bundle, owner)).fetchall()
        for r in rows:
            boards = len((json.loads(r["stage"]) if r["stage"] else {}).get("boards") or [])
            frames = self.db.execute("SELECT COUNT(DISTINCT frame) FROM strokes WHERE session = ? AND erased IS NULL",
                                     (r["id"],)).fetchone()[0]
            if frames or boards:
                return {"id": r["id"], "last_active": r["last_active"], "frames": frames, "boards": boards}
        return None

    def load_questions(self, sessions: list[str]) -> list[Asked]:
        """The questions from the audience of these games (texstage M6), deleted ones too."""
        if not sessions:
            return []
        marks = ", ".join("?" * len(sessions))
        rows = self.db.execute(f"SELECT * FROM questions WHERE session IN ({marks}) ORDER BY created", sessions)
        return [Asked(**{**dict(r), "votes": json.loads(r["votes"])}) for r in rows]

    def load_rows(self, cls, sessions: list[str]) -> list:
        """A content type's rows of these games (types.py: ROWS) - a row saved again comes later (INSERT
        OR REPLACE): its Book puts them in its own order."""
        if not sessions:
            return []
        table, cols = TABLES[cls]
        encoded = JSON.get(cls, ())
        marks = ", ".join("?" * len(sessions))
        rows = self.db.execute(f"SELECT * FROM {table} WHERE session IN ({marks}) ORDER BY rowid", sessions)
        return [cls(**{c: json.loads(r[c]) if c in encoded and r[c] is not None else r[c] for c in cols})
                for r in rows]
