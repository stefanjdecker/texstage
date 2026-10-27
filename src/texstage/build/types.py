# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The content types the build knows (docs/content-types-design.md, section 5.2).

The core (builder.py) compiles the deck, reads the records it writes (tqz.py), makes the
slide pictures and the stage PDF, and asks the types for the rest: a type is a module with

    NAME        its name, in deck.json ("types", "items", a live box's "type")
    KINDS       the kinds of its page records (G|kind|id|phase|page)
    USES_ADDIN  whether its live slides carry PowerPoint's add-in (then the live PPTX gets the
                first slide that prepares them)
    box(tqz, item) -> dict          a slide's live box for an item: {type, phase?, item?, rects?}

and, as it needs them, the steps quiz.py has: plan (slides of its own), entries (deck.json's
and keys.json's items), files (into the bundle), stored (the live PPTX's picture), addin (the
add-in's properties), solutions (a compile for the check). All types live in this package;
a deck names the ones it uses, and a server that lacks one refuses it (server/bundles.py).
"""
from __future__ import annotations

from types import ModuleType

from texstage.build import activity, quiz, video

TYPES: dict[str, ModuleType] = {quiz.NAME: quiz, video.NAME: video, activity.NAME: activity}


def of_kind(kind: str) -> ModuleType | None:
    """The type whose page records have this kind."""
    return next((t for t in TYPES.values() if kind in t.KINDS), None)
