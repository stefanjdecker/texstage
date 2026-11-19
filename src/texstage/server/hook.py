# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What a content type's hook gets and gives (types.py, which says what a type is): the call, a refusal, and
a reply's WRITTEN. A module of its own, which the types' modules import - types.py imports them, so a type's
module imported first found it half made (the review of 2026-11-19)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


MOMENT = "moment"                        # (a game's stage) the count of what its phones were shown


def moment(session) -> int:
    """The game's next moment: what its phones show became another - the quiz's (game.py: quiz_at), an
    activity's step (activities.py: its at). A count kept with the game, so that which came last hangs on no
    clock (the second review of 2026-11-19: milliseconds tie, and a clock set back misorders them)."""
    had = session.stage.get(MOMENT)
    n = (had if isinstance(had, int) and not isinstance(had, bool) else 0) + 1
    session.stage = {**session.stage, MOMENT: n}
    return n


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
