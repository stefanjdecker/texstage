# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The content types the server knows (docs/content-types-design.md, section 6.2;
docs/live-activities-design.md, section 7.5).

The quiz is the game itself (game.py, with the audience it shares with polls, Q&A and
sketches). Every other type lives on the stage and gives the server a module with

    NAME                                  its name, as deck.json's "types" says it
    MESSAGES                              the messages it takes, "<name>.<what>", from a presenter window
    handle(call, t, msg)                  one of them (call: Call below); returns the reply's fields or
                                          None; ValueError: refused
    view(stage)                           its part of the state every window gets (None: nothing)
    slide(stage, items, before, after, now)   the stage's state after a slide change

and, as it needs them,

    READS                                 those of its MESSAGES that only read: answered anew, never from
                                          the reply cache, and open to the projector window too
    QUIET                                 those that come in bulk (a window's results): the windows get
                                          the state within 200 ms, as with the phones' answers, not at once
    PLAYER_MESSAGES, player(call, t, msg) messages from phones (call.player: the phone's player)
    player_view(call)                     its part of a phone's state (None: nothing)
    Book                                  its larger data of all games, in memory: Book(), load(rows) at
                                          start, forget(session) when a game ends, left(conn) when a
                                          window goes
    ROWS                                  its tables: {dataclass: (table, columns, key, JSON columns)};
                                          every table has a column `session`
    archive(call)                         its files for the game's folder in the lecture archive:
                                          {name: text}, the names matching ARCHIVE
    FILES, FILE_TYPES                     bundle files it serves as the pictures are (a pattern of their
                                          names; deck.json lists them) and their media types by suffix
    MEDIA, POSTER, TYPES, media(items)    (the video) the bundle files it serves: by ticket, or as pictures
    shown(call, before, after, marks)     a slide change, for a type whose data are not the stage's; marks:
                                          what the new page is of each item it shows (a live box's phase)
    deck(call, bundle), resume(call)      a game comes to a deck; the server started again
    pulse(engine, now)                    a few times a second: the games whose windows need their state
    Book: begin(engine), apply(now),      once the engine has its games; the pool's answers, applied;
      release(bundle), casts, steps       a build's last game ended; a text for every phone of a game
    refuses(deck)                         why this server cannot play a deck of the type: refuses()
    failing(book, session)                the references of the game's deck that fail: failing()

A deck that names a type not here is refused (bundles.py), and so is one a type here refuses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


class Refused(ValueError):
    """A hook refuses a message; `code` is for the client (game.py's GameError codes), the message
    for people. A plain ValueError is refused as "invalid"."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


@dataclass
class Call:
    """What a type's hook gets: the game, the type's items in the deck (deck.json's and keys.json's),
    the time, its Book, and who calls - a window's role and connection, or a phone's player. The
    hook changes `session.stage[NAME]`, hands rows to `save`, and says which phones should get
    their state again: `phones` True (all) or a set of player ids."""
    session: Any
    items: dict
    keys: dict
    now: int
    book: Any = None
    role: str | None = None              # stage, display or host; "player" for a phone
    conn: str | None = None              # the calling connection's key (app.py Conn.key)
    player: Any = None                   # the calling phone's Player
    save: Callable = lambda *rows: None
    phones: Any = field(default_factory=set)
    changed: bool = True                 # False: nothing to store (the session is not saved)


WRITTEN = "__written__"                  # in a hook's reply: a function that takes what is to be called once the
#                                          hook's rows are written - the reply is sent then, not before (app.py)

# The types (after Refused and Call, which they use)
from texstage.server import activities, activity, video  # noqa: E402

# Live activities: F1's type, or the activity framework's core (activities.py; the plan of F2, package 6) -
# one of the two in a server, never both: they take the same messages and the same decks.
ACTIVITIES = {"f1": activity, "core": activities}
TYPES: dict = {}
KNOWN = {"quiz", video.NAME, activity.NAME}
MESSAGES: dict = {}
READS: set = set()
QUIET: set = set()
PLAYER_MESSAGES: dict = {}
ROWS = {cls: spec for t in (video, activity, activities) for cls, spec in getattr(t, "ROWS", {}).items()}
FILE_TYPES = {suffix: mime for t in (video, activity) for suffix, mime in getattr(t, "FILE_TYPES", {}).items()}
FILES = [t.FILES for t in (video, activity) if hasattr(t, "FILES")]             # patterns of names
ARCHIVE = [t.ARCHIVE for t in (video, activity) if hasattr(t, "ARCHIVE")]
using = ""


def use(which: str = "f1") -> None:
    """The activity type this server runs: "f1" or "core". What the engine and the app read of the types
    - by name, as they need it - is the chosen one's from here on; the tables, the files a type serves
    and the archive's names are both types' alike."""
    global using
    if which not in ACTIVITIES:
        raise ValueError(f"activities: one of {', '.join(ACTIVITIES)}, not {which!r}")
    types = {video.NAME: video, activity.NAME: ACTIVITIES[which]}
    TYPES.clear()
    TYPES.update(types)
    MESSAGES.clear()
    MESSAGES.update({m: t for t in types.values() for m in t.MESSAGES})
    READS.clear()
    READS.update(m for t in types.values() for m in getattr(t, "READS", ()))
    QUIET.clear()
    QUIET.update(m for t in types.values() for m in getattr(t, "QUIET", ()))
    PLAYER_MESSAGES.clear()
    PLAYER_MESSAGES.update({m: t for t in types.values() for m in getattr(t, "PLAYER_MESSAGES", ())})
    assert READS <= set(MESSAGES), "a read is one of the type's messages"
    using = which


use("f1")


def bundle_file(rel: str) -> bool:
    """Whether a bundle file is one a type serves as the pictures are served."""
    return any(re.fullmatch(p, rel) for p in FILES)


def refuses(deck: dict) -> str | None:
    """Why this server cannot play a deck whose types it knows - what a type it runs says of the deck's
    deck.json (its hook refuses: the core's type, of a kind it lacks; server/bundles.py refuses the deck)."""
    for kind in TYPES.values():
        check = getattr(kind, "refuses", None)
        why = check(deck) if check is not None else None
        if why:
            return why
    return None


def failing(engine, s) -> list[dict]:
    """The references of a game's deck that fail, for the deck list (app.py): [{activity, reference (from
    1), error}] - the activity type's own way to tell them (F1's: from the game's stage)."""
    kind = TYPES.get(activity.NAME)
    if kind is None or s is None:
        return []
    if hasattr(kind, "failing"):
        return kind.failing(engine.books.get(kind.NAME), s)
    return kind.failed_references(s.stage)
