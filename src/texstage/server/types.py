# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The content types the server knows (docs/content-types-design.md, section 6.2;
docs/live-activities-design.md, section 7.5).

The quiz is the game itself (game.py, with the audience it shares with polls, Q&A and
sketches). Every other type lives on the stage and gives the server a module with

    NAME                                  its name, as deck.json's "types" says it
    MESSAGES                              the messages it takes, "<name>.<what>", from a presenter window
    handle(call, t, msg)                  one of them (call: hook.py's Call); returns the reply's fields or
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

from texstage.server.hook import WRITTEN, Call, Refused  # noqa: F401 - the engine's and the types' names (hook.py)

# The types
from texstage.server import activities, activity, video

# Live activities: the activity framework's core (activities.py; the plan of F2, package 6), the default since
# package 14, or F1's type (activity.py; texstage serve --activities f1), kept until a class has used the core
# (4.12) - one of the two in a server, never both: they take the same messages and the same decks.
ACTIVITIES = {"core": activities, "f1": activity}
DEFAULT = "core"
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


def use(which: str = DEFAULT) -> None:
    """The activity type this server runs: "core" (the default) or "f1". What the engine and the app read of
    the types - by name, as they need it - is the chosen one's from here on; the tables, the files a type
    serves and the archive's names are both types' alike."""
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


use()


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
