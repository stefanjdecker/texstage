# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Questions from the audience (texstage M6, docs/texstage-design.md, sections 10 and 21).

While the lecturer has them open, the phones ask questions - anonymous, up to 280 characters,
formulas between $...$ - and upvote those of the others. The presenter window sees them by
votes, puts one on the projector (a card over the slide), marks it done, deletes it, or blocks
whoever asked it (their open questions go too). The server keeps the asker's player id for that
only: no view names them. A game keeps its questions; the lecture archive lists them.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

TEXT_MAX = 280
GAP_MS = 20_000                          # a player asks at most every 20 s
OPEN_MAX = 5                             # a player's questions not yet answered
PER_GAME = 500
STATES = ("open", "done", "deleted")


@dataclass
class Asked:
    """A question from the audience."""
    id: str
    session: str
    player: str                          # for moderation only
    text: str
    created: int
    votes: list[str] = field(default_factory=list)      # the players who upvoted it
    state: str = "open"                  # open done deleted


def clean_question(text) -> str:
    if not isinstance(text, str):
        raise ValueError("a question is text")
    text = " ".join("".join(c for c in unicodedata.normalize("NFC", text)
                            if not unicodedata.category(c).startswith("C")).split())
    if not 1 <= len(text) <= TEXT_MAX:
        raise ValueError(f"a question has 1 to {TEXT_MAX} characters")
    return text


def ranked(questions) -> list[Asked]:
    """Open questions by votes (the oldest first among equals), then the answered ones."""
    return sorted((q for q in questions if q.state != "deleted"),
                  key=lambda q: (q.state != "open", -len(q.votes), q.created))
