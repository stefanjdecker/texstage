# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The core's storage (docs/architecture/activity-framework-design.md, 10.2; the plan of F2, 4.3 and
4.10): its tables, the writer that gathers what changed and commits it every 50 ms in one
transaction, what a restarted server reads back, and the move of F1's rows into them.

    steps      a step of an activity in a game: its epoch, its phase, the time left (phases.py)
    entries    what a student sent in a step (entries.py); its id is the phone's, unique per step
    checks     the verdict on one distinct normalized input of a step (the checks: package 4)
    details    what one group shows, one per key (LA's results)
    moderation the lecturer's acts on a step's picture, every act a row, so that it can be undone
               (moderation.py)

Every table has its `session`. ROWS has them as a content type gives the server its tables
(server/types.py), so that the type, once it is the core's (package 6), hands them to the server's
store, which then makes them (server/store.py); until then create() does, the same way. The table
`ledger` comes with what writes it (F3).

The core's rows are written by the Writer and read by load(), never by the server's store: that one
replaces a row it saves again, which moves it to the table's end, and reads a flag as a number. Here a
row is written as it is when the writer commits, not as it was when it was handed over - a row changed
twice in 50 ms is written once -, and a row that is there already is updated in place: the entries keep
the order they came in, which is the order they are read back in.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from texstage.activities.kind import FROM_F1
from texstage.checks import cleaning

__all__ = ["ROWS", "CheckRow", "DetailRow", "EntryRow", "Loaded", "ModerationRow", "StepRow", "Writer", "create",
           "gid", "load", "move", "norm"]

ONE = "main"                         # the step of an activity that writes none out (the design's 5.1)
EVERY_S = 0.05                       # the writer's commits (the design's 10.2)
RETRY_MAX_S = 2.0                    # ... and at most this far apart while the database refuses them
ASIDE_KEPT = 100                     # the rows set aside that the writer remembers, for whoever asks why
F1_SET_ASIDE = "set aside: "         # F1's mark of a text its pool set aside (server/activity.py: SET_ASIDE)
F1_FINAL = ("ok", "syntax", "error", "timeout", "refused")     # F1's statuses that are a verdict
MIN_MAX = 1000                       # a crowd graph's minimum, at most (the kind's option: min)


@dataclass
class StepRow:
    """A step in a game (phases.py)."""
    session: str
    activity: str
    step: str = ONE
    epoch: int = 0                   # a reset gives a new one: the entries of the earlier ones no longer count
    phase: str = "ready"
    time_left: int | None = None     # of its time, in ms; None: it has none
    paused_by: str = ""              # who paused it: lecturer, quiz (a round), sleep (the server did not run)
    seq: int = 0                     # its turn among the game's steps, counted up as one opens or is revealed:
    #                                  the step with the highest is the current one; 0: it never was


@dataclass
class EntryRow:
    """What a student sent in a step (entries.py)."""
    id: str                          # the phone's, unique in its step
    session: str
    activity: str
    step: str
    epoch: int
    player: str                      # for the phone's own list and for blocking only: no view names anybody
    created: int
    input: dict                      # {"text": ...}, {"fields": [...]}, {"choice": [...]} or {"number": ...}, as sent
    norm: str = ""                   # the hash of its normalized input (norm); "": not normalized yet. An entry
    #                                  is unchecked while its step has no check for its norm
    state: str = "in"                # in replaced withdrawn hidden


@dataclass
class CheckRow:
    """The verdict on one distinct normalized input of a step (the design's 6.3). aside: an internal
    check that is final - its text ended two workers and is not checked again, after a restart neither.
    parts: for crowd, what a restart needs to draw the graph again. form: the normalized input itself -
    what a group is shown by: as clean as its kind's normalize makes a text (reduce.py)."""
    session: str
    activity: str
    step: str
    norm: str
    status: str
    key: str | None = None
    parts: list | None = None
    verdict: str | None = None
    credit: float | None = None
    message: dict | None = None      # {code, args}
    at: list | None = None           # [line, column]
    aside: bool = False
    created: int = 0
    form: dict | None = None         # the input as normalize gave it (kind.py: Entry.stored); None: it has none


@dataclass
class DetailRow:
    """What one group shows: a result's columns and first rows, a graph."""
    session: str
    activity: str
    step: str
    key: str
    detail: dict
    created: int = 0


@dataclass
class ModerationRow:
    """An act of the lecturer's on a step's picture (moderation.py): every act a row, so that it can be
    undone and a restarted server has it again. No row names a student: a block names an entry, and is
    for whoever sent it."""
    session: str
    n: int                           # the act's number in its game, from 1: the order they are read back in
    activity: str
    step: str
    act: str                         # hide approve merge unmerge show min block
    epoch: int = 0                   # the step's, when it was done: what is shown is that epoch's
    target: str | None = None        # a group's id (gid) - of a crowd graph: a term's key
    role: str = ""                   # merge, unmerge: the term's role, node or label
    entry: str | None = None         # hide: an entry; block: an entry of the student
    onto: str | None = None          # merge: the term it is merged into
    off: bool = False                # hide, approve, block: taken back
    value: int | dict | list | None = None       # min: the number; block: {"hid": the entries it hid, "had": those
    #                                              of the student it found hidden} - what its undo goes by
    created: int = 0
    undone: bool = False


# as server/types.py has a type's ROWS: {dataclass: (table, columns, key, JSON columns)}
ROWS = {
    StepRow: ("steps", ["session", "activity", "step", "epoch", "phase", "time_left", "paused_by", "seq"],
              "session, activity, step", ()),
    EntryRow: ("entries", ["id", "session", "activity", "step", "epoch", "player", "created", "input", "norm",
                           "state"], "session, activity, step, id", ("input",)),
    CheckRow: ("checks", ["session", "activity", "step", "norm", "status", "key", "parts", "verdict", "credit",
                          "message", "at", "aside", "created", "form"], "session, activity, step, norm",
               ("parts", "message", "at", "form")),
    DetailRow: ("details", ["session", "activity", "step", "key", "detail", "created"],
                "session, activity, step, key", ("detail",)),
    ModerationRow: ("moderation", ["session", "n", "activity", "step", "act", "epoch", "target", "role", "entry", "onto",
                                   "off", "value", "created", "undone"], "session, n", ("value",)),
}
FLAGS = {CheckRow: ("aside",), ModerationRow: ("off", "undone")}       # stored as 0 and 1
# what a column that a file of an earlier version lacks is read as: the row's own default
DEFAULTS = {cls: {f.name: f.default for f in dataclasses.fields(cls)
                  if f.default is not dataclasses.MISSING and f.default is not None} for cls in ROWS}


def norm(input: dict) -> str:
    """The hash of a normalized input - what entries that are checked once have in common: 32
    hexadecimal digits of the SHA-256 of its JSON, the keys in order, no character escaped. A half of a
    surrogate pair, which no store takes, is hashed as JSON escapes it. It is stored with every entry
    and every check: changing it orphans them."""
    text = json.dumps(input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8", "backslashreplace")).hexdigest()[:32]


def gid(status: str, key: str | None = None) -> str:
    """A group's id, as the pictures and the moderation name it. Entries whose checks are ok group by
    their key, the others by their status (the design's 6.3); the id is 16 hexadecimal digits of a hash
    of both, since a key may be any text of up to 4,096 characters - a status's name among them. It is
    stored with the acts on a group: changing it orphans them."""
    text = "ok" + chr(0x1F) + (key or "") if status == "ok" else status
    return hashlib.sha256(text.encode("utf-8", "backslashreplace")).hexdigest()[:16]


def create(db: sqlite3.Connection) -> None:
    """The core's tables, as the server's store makes a type's (server/store.py): each with its columns
    - a file of an earlier version gets the ones it lacks - and an index by session."""
    for table, cols, key, _ in ROWS.values():
        db.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)}, PRIMARY KEY ({key}))")
        have = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        for col in cols:
            if col not in have:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
        db.execute(f"CREATE INDEX IF NOT EXISTS {table}_session ON {table} (session)")
    db.commit()


def _values(row) -> list:
    _, cols, _, encoded = ROWS[type(row)]
    out = []
    for c in cols:
        v = getattr(row, c)
        if c in encoded:
            out.append(None if v is None else json.dumps(v, separators=(",", ":")))    # (escaped: half a pair too)
        else:
            out.append(int(v) if isinstance(v, bool) else v)
    return out


def _upsert(cls) -> str:
    table, cols, key, _ = ROWS[cls]
    keys = [k.strip() for k in key.split(",")]
    rest = [c for c in cols if c not in keys]
    return (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
            f"ON CONFLICT ({key}) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in rest)}")


UPSERT = {cls: _upsert(cls) for cls in ROWS}


def _the_databases(e: Exception) -> bool:
    """Whether a failure is the database's - a full disk, a lock, a file that is broken or closed -,
    which the next commit may not meet; else it is the row's, which no commit will ever take."""
    return isinstance(e, (sqlite3.OperationalError, sqlite3.InternalError)) or \
        type(e) in (sqlite3.DatabaseError, sqlite3.Error)


class Writer:
    """What changed, gathered and committed every 50 ms in one transaction (the design's 10.2) - not one
    transaction per call, as the game's engine has it. put() hands rows over, and what is to happen once
    they are written: an entry is acknowledged then, not before (the design's 10.1).

    It uses the store's connection, on the one event loop that the engine uses it on, and keeps its
    statements in a savepoint of its own: a commit of its that fails takes back what it wrote, not what
    the engine left there (a hook that saved and then refused leaves its row uncommitted).

    A commit the database refuses - a full disk - leaves the rows and what waits for them where they
    are, for the next one: nothing is acknowledged that is not written. failures counts them, error has
    the last one's words, for the panel. A row that no commit can take - a value no store has a type
    for: a fault of the core's - is set aside, so that it does not hold up every row after it: aside has
    it with the reason, `lost` is told, and what waited for it is not called.
    """

    def __init__(self, db: sqlite3.Connection, every_s: float = EVERY_S,
                 lost: Callable[[object, str], None] | None = None):
        self.db = db
        self.every_s = every_s
        self.lost = lost
        self.rows: dict[int, object] = {}                 # by identity, in the order they first came
        self.then: list[tuple[tuple[int, ...], Callable[[], None]]] = []   # what waits, with its rows
        self.aside: list[tuple[object, str]] = []         # the rows no commit took, the last ASIDE_KEPT
        self.failures = 0                                 # commits the database refused
        self.dropped = 0                                  # rows set aside
        self.untold = 0                                   # of what waited: those that failed when called
        self.error = ""
        self.commits = 0

    def put(self, *rows, then: Callable[[], None] | None = None) -> None:
        """Rows to write with the next commit, and what to call once these rows are written - with no
        rows: once everything handed over before is."""
        for row in rows:
            if type(row) not in ROWS:
                raise TypeError(f"{type(row).__name__} is none of the core's rows")
            self.rows.setdefault(id(row), row)
        if then is not None:
            self.then.append((tuple(id(row) for row in rows), then))

    def pending(self) -> int:
        return len(self.rows)

    def flush(self) -> int:
        """Everything handed over, in one transaction; then what waits for it. How many rows were
        written. An exception: the database refused the commit - nothing was written, and everything
        waits for the next flush."""
        if not self.rows and not self.then:
            return 0
        rows, then = list(self.rows.values()), self.then
        bad: dict[int, str] = {}
        try:
            self.db.execute("SAVEPOINT core_writer")
            try:
                for row in rows:
                    try:
                        self.db.execute(UPSERT[type(row)], _values(row))
                    except Exception as e:
                        if _the_databases(e):
                            raise
                        bad[id(row)] = f"{type(e).__name__}: {e}"[:300]
                self.db.execute("RELEASE core_writer")
            except BaseException:
                self.db.execute("ROLLBACK TO core_writer")
                self.db.execute("RELEASE core_writer")
                raise
            self.db.commit()
        except Exception as e:
            self.failures += 1
            self.error = f"{type(e).__name__}: {e}"[:300]
            raise
        self.rows, self.then = {}, []
        self.commits += 1
        self.error = ""
        for row in rows:
            if id(row) in bad:
                self.dropped += 1
                self.aside = [*self.aside, (row, bad[id(row)])][-ASIDE_KEPT:]
                self._call(self.lost, row, bad[id(row)])
        for ids, call in then:                            # every one, though one of them fails
            if not any(i in bad for i in ids):
                self._call(call)
        return len(rows) - len(bad)

    def _call(self, call, *args) -> None:
        if call is None:
            return
        try:
            call(*args)
        except Exception as e:  # noqa: BLE001 - the others still learn that their rows are written
            self.untold += 1
            self.error = f"{type(e).__name__}: {e}"[:300]

    def close(self) -> int:
        """When the server ends: what was handed over is written, if the database takes it. How many
        rows it did not take."""
        try:
            self.flush()
        except Exception:  # noqa: BLE001 - counted (failures, error); the server ends all the same
            pass
        return len(self.rows)

    async def run(self) -> None:
        """Until cancelled: a commit every 50 ms while there is something to write. One the database
        refuses is tried again, each time after twice as long, up to RETRY_MAX_S (failures, error).
        Cancelled, it writes what is left (close)."""
        wait = self.every_s
        try:
            while True:
                await asyncio.sleep(wait)
                if self.rows or self.then:
                    try:
                        self.flush()
                        wait = self.every_s
                    except Exception:  # noqa: BLE001 - counted; the loop that writes must not end
                        wait = min(RETRY_MAX_S, wait * 2)
        finally:
            self.close()


@dataclass
class Loaded:
    """What the tables have of the running games, as a restarted server reads it: the entries in the
    order they came."""
    steps: list[StepRow] = field(default_factory=list)
    entries: list[EntryRow] = field(default_factory=list)
    checks: list[CheckRow] = field(default_factory=list)
    details: list[DetailRow] = field(default_factory=list)
    moderation: list[ModerationRow] = field(default_factory=list)       # in the order of the acts


def _rows(db: sqlite3.Connection, cls, sessions: list[str]) -> list:
    table, cols, _, encoded = ROWS[cls]
    flags, defaults = FLAGS.get(cls, ()), DEFAULTS[cls]
    marks = ", ".join("?" * len(sessions))
    out = []
    order = "session, n" if cls is ModerationRow else "rowid"
    for r in db.execute(f"SELECT {', '.join(cols)} FROM {table} WHERE session IN ({marks}) ORDER BY {order}", sessions):
        values = {}
        for c, v in zip(cols, r):
            if v is None and c in defaults:               # a column that came later: the row's default
                v = defaults[c]
            values[c] = json.loads(v) if c in encoded and v is not None else bool(v) if c in flags else v
        out.append(cls(**values))
    return out


def load(db: sqlite3.Connection, sessions: Iterable[str]) -> Loaded:
    """The core's rows of these games."""
    sessions = list(sessions)
    if not sessions:
        return Loaded()
    return Loaded(_rows(db, StepRow, sessions), _rows(db, EntryRow, sessions), _rows(db, CheckRow, sessions),
                  _rows(db, DetailRow, sessions), _rows(db, ModerationRow, sessions))


# ------------------------------------------------------------------ the move of F1's data (the plan of F2, 4.10)
def _tables(db: sqlite3.Connection) -> set[str]:
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _f1_check(session: str, activity: str, row: dict, input: dict) -> CheckRow | None:
    """F1's verdict on a contribution as a check - or None: it waited, or could not be checked for the
    server's reasons, or is not what F1 writes (ok without a key), and is checked again."""
    status, error = row["status"] or "ok", row["error"] or ""
    base = (session, activity, ONE, norm(input))
    if status == "internal" and error.startswith(F1_SET_ASIDE):
        return CheckRow(*base, "internal", aside=True, created=row["created"])
    if status not in F1_FINAL:
        return None
    if status != "ok":
        return CheckRow(*base, FROM_F1.get(status, status), created=row["created"], form=input)
    if not row["key"] or not isinstance(row["key"], str):
        return None
    fields = input.get("fields")
    if fields is None:
        return CheckRow(*base, "ok", key=row["key"], created=row["created"], form=input)
    keys = row["key"].split("\x1f")
    if len(keys) != len(fields):
        return None
    parts = [{"key": k, "text": f, "literal": cleaning.is_literal(f)} for k, f in zip(keys, fields)]
    return CheckRow(*base, "ok", key=row["key"], parts=parts, created=row["created"], form=input)


def _f1_acts(session: str, activity: str, st: dict, n: int, item: dict | None = None) -> list[ModerationRow]:
    """What F1 kept of the lecturer's acts in an activity's state, as acts - numbered from n: the crowd
    graph's minimum, merges, hidden and approved terms, and the result shown on the projector. item: the
    activity's item of the deck, if the caller has it - a minimum that is the deck's own is no act of the
    lecturer's (F1 wrote the deck's into every graph's state). What F1 never wrote makes no act: a minimum
    beyond MIN_MAX, a term twice, a merge that leads back to its own term - which no undo could pass."""
    def text(v) -> bool:
        return isinstance(v, str) and bool(v)
    rows: list[ModerationRow] = []

    def act(name: str, **more) -> None:
        rows.append(ModerationRow(session, n + len(rows), activity, ONE, name, **more))

    def listed(name: str) -> list:
        return st[name] if isinstance(st.get(name), list) else []
    least = st.get("min")
    if isinstance(least, int) and not isinstance(least, bool) and 1 <= least <= MIN_MAX \
            and not (isinstance(item, dict) and item.get("min", 1) == least):
        act("min", value=least)                               # (first: the last act is the first to be undone)
    merged: dict[tuple[str, str], str] = {}
    for m in listed("merges"):
        if isinstance(m, (list, tuple)) and len(m) == 3 and m[0] in ("node", "label") and text(m[1]) and text(m[2]):
            role, term, onto = m
            end, seen = onto, set()
            while end != term and (role, end) in merged and end not in seen:
                seen.add(end)
                end = merged[(role, end)]
            if end != term:                                   # (else: it leads back to the term itself)
                merged[(role, term)] = onto
                act("merge", target=term, role=role, onto=onto)
    for name, kept in (("hide", "hidden"), ("approve", "approved")):
        for term in dict.fromkeys(t for t in listed(kept) if text(t)):
            act(name, target=term)
    shown = st.get("shown")
    if text(shown):                                           # a result's key - or F1's word for what is none
        final = shown in F1_FINAL and shown != "ok"
        act("show", target=gid(FROM_F1.get(shown, shown)) if final else gid("ok", shown))
    return rows


def move(db: sqlite3.Connection, stages: dict[str, dict], decks: dict[str, dict] | None = None) -> dict[str, int]:
    """F1's rows of these games - `contributions`, `results`, and each activity's phase in the game's
    stage (stages: {session: its stage}) - as the core's: entries (one step, epoch 0, the ids kept),
    checks (a status and a key per distinct input, the text as F1 cleaned it as its form; F1's words
    for an error stay behind), details (the summaries), steps, the activity the phones showed being the
    current one, and the lecturer's acts (moderation: the crowd graph's minimum, merges, hidden and
    approved terms, the result that was shown; decks: {session: its deck's items}, so that a minimum
    which is the deck's own makes no act). An activity that has a step already is not moved again; the
    old tables stay as they are. Everything in one transaction. How many rows of each were made.

    A game is moved before its acts are loaded (moderation.py: load) and before any act is made: the
    moved acts are numbered after the table's, which knows nothing of acts that are only in memory. Who
    was blocked in F1 is the server's (a player's `muted`), and stays there: package 6 asks both."""
    made = {"steps": 0, "entries": 0, "checks": 0, "details": 0, "moderation": 0}
    if not stages:
        return made
    create(db)
    tables, sessions = _tables(db), list(stages)
    marks = ", ".join("?" * len(sessions))
    done = {(r[0], r[1]) for r in db.execute(f"SELECT session, activity FROM steps WHERE session IN ({marks})",
                                             sessions)}
    rows: list = []
    seen: set[tuple[str, str]] = set()
    checked: set[tuple[str, str, str]] = set()
    if "contributions" in tables:
        cursor = db.execute(           # (F1 replaces a row it saves again, which moves it to the table's end)
            f"SELECT id, session, activity, player, created, input, state, key, status, error FROM contributions "
            f"WHERE session IN ({marks}) ORDER BY created, id", sessions)
        names = [d[0] for d in cursor.description]
        for values in cursor.fetchall():
            c = dict(zip(names, values))
            if (c["session"], c["activity"]) in done:
                continue
            seen.add((c["session"], c["activity"]))
            input = json.loads(c["input"])
            entry = EntryRow(c["id"], c["session"], c["activity"], ONE, 0, c["player"], c["created"], input,
                             norm(input), c["state"] or "in")
            rows.append(entry)
            made["entries"] += 1
            check = _f1_check(c["session"], c["activity"], c, input)
            if check is not None and (check.session, check.activity, check.norm) not in checked:
                checked.add((check.session, check.activity, check.norm))      # the first with a verdict, as F1
                rows.append(check)
                made["checks"] += 1
    if "results" in tables:
        for session, activity, key, summary, created in db.execute(
                f"SELECT session, activity, key, summary, created FROM results WHERE session IN ({marks}) "
                f"ORDER BY created, key", sessions).fetchall():
            if (session, activity) in done:
                continue
            seen.add((session, activity))
            rows.append(DetailRow(session, activity, ONE, key, json.loads(summary), created))
            made["details"] += 1
    acts = dict(db.execute(f"SELECT session, MAX(n) FROM moderation WHERE session IN ({marks}) GROUP BY session",
                           sessions).fetchall())
    for session, stage in stages.items():
        state = stage.get("activity") if isinstance(stage, dict) else None
        state = state if isinstance(state, dict) else {}
        items = state["items"] if isinstance(state.get("items"), dict) else {}
        deck = (decks or {}).get(session)
        for activity in sorted({a for s, a in seen if s == session} | {a for a in items if isinstance(a, str)}):
            if (session, activity) in done:
                continue
            st = items[activity] if isinstance(items.get(activity), dict) else {}      # (else: not what F1 writes)
            item = deck.get(activity) if isinstance(deck, dict) else None
            moved = _f1_acts(session, activity, st, acts.get(session, 0) + 1, item)
            acts[session] = acts.get(session, 0) + len(moved)
            rows += moved
            made["moderation"] += len(moved)
            phase = "revealed" if st.get("revealed") else st.get("phase") if st.get("phase") in ("open", "closed") \
                else "ready"
            rows.append(StepRow(session, activity, ONE, 0, phase, seq=1 if activity == state.get("current") else 0))
            made["steps"] += 1
    try:
        for row in rows:
            db.execute(UPSERT[type(row)], _values(row))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return made
