# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Ink on texstage's slides (docs/texstage-design.md, sections 6-7).

A stroke belongs to a frame of a game - a deck frame ("12") or a whiteboard page
("board:<id>") - so it stays through the frame's overlay steps and when the lecturer comes
back. It is drawn in the presenter window and shown on the projector while it is drawn:
begin, points in batches, end; only an ended stroke is kept (and stored, store.py).
Coordinates are fractions of the slide from the top left, the width is a fraction of the
slide's height, the pressure 0..1 (`sim`: to be simulated from the speed - mouse, finger).
Undo and redo are per device and frame and live in memory: a restarted server keeps the
strokes, not their history.

The book only checks and keeps strokes; the engine (game.py) ties it to the games, the
server (app.py) relays what happens to the other windows. Errors are ValueErrors (the
engine turns them into GameErrors).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

FRAME = re.compile(r"^(?:[1-9][0-9]{0,4}|board:[0-9a-f]{8}|poll:[a-z0-9-]{1,40})$")   # (M6: a poll's slide)
NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")         # stroke and device ids (made by the window)
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
TOOLS = ("pen", "highlighter")
WIDTHS = (0.0005, 0.1)       # of the slide's height
BATCH_MAX = 600              # points per message (a message has at most 16 KiB)
STROKE_MAX = 20000           # points per stroke
LIVE_MS = 120_000            # a stroke not ended by then is dropped
UNDO_MAX = 100               # actions per device and frame


@dataclass
class Stroke:
    id: str
    session: str
    frame: str
    device: str
    tool: str                # pen highlighter
    color: str               # #rrggbb
    width: float             # fraction of the slide's height
    sim: bool                # pressure simulated from the speed (mouse, finger)
    points: list = field(default_factory=list)    # [[x, y, pressure], ...]
    created: int = 0
    erased: int | None = None

    def view(self) -> dict:
        return {"id": self.id, "frame": self.frame, "tool": self.tool, "color": self.color,
                "width": self.width, "sim": self.sim, "points": self.points}


def check_frame(frame) -> str:
    if not isinstance(frame, str) or not FRAME.match(frame):
        raise ValueError("a frame is its number (as text), board:<id> or poll:<id>")
    return frame


def check_device(device) -> str:
    if not isinstance(device, str) or not NAME.match(device):
        raise ValueError("a device is named by letters, digits, - and _")
    return device


def check_points(points, room: int) -> list:
    """[[x, y, pressure], ...], rounded: 1/10000 of the slide, 1/1000 of the pressure."""
    if not isinstance(points, list) or len(points) > min(BATCH_MAX, room):
        raise ValueError(f"points: a list of at most {min(BATCH_MAX, room)} [x, y, pressure]")
    out = []
    for p in points:
        if not (isinstance(p, list) and len(p) == 3 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                             and math.isfinite(v) for v in p)):
            raise ValueError("a point is [x, y, pressure]")
        x, y, pressure = p
        if not (-1 <= x <= 2 and -1 <= y <= 2 and 0 <= pressure <= 1):
            raise ValueError("a point lies on the slide (fractions) with a pressure of 0 to 1")
        out.append([round(x, 4), round(y, 4), round(pressure, 3)])
    return out


class InkBook:
    """The strokes of the games, the strokes being drawn, and undo/redo per device and frame."""

    def __init__(self):
        self.strokes: dict[str, dict[str, Stroke]] = defaultdict(dict)      # session -> id -> stroke
        self.live: dict[tuple[str, str], Stroke] = {}                        # (session, id) -> being drawn
        self.undos: dict[tuple[str, str, str], list] = defaultdict(list)    # (session, device, frame)
        self.redos: dict[tuple[str, str, str], list] = defaultdict(list)

    def add(self, s: Stroke):
        """A stored stroke (a restarted server)."""
        self.strokes[s.session][s.id] = s

    def begin(self, session: str, device, frame, meta, points, now: int) -> Stroke:
        check_device(device)
        if not isinstance(meta, dict):
            raise ValueError("stroke: {id, tool, color, width, sim}")
        sid, tool, color, width = meta.get("id"), meta.get("tool"), meta.get("color"), meta.get("width")
        if not isinstance(sid, str) or not NAME.match(sid):
            raise ValueError("a stroke id has letters, digits, - and _")
        if (session, sid) in self.live or sid in self.strokes[session]:
            raise ValueError(f"stroke {sid} exists already")
        if tool not in TOOLS:
            raise ValueError(f"the tool is {' or '.join(TOOLS)}")
        if not isinstance(color, str) or not COLOR.match(color):
            raise ValueError("a colour is #rrggbb")
        if isinstance(width, bool) or not isinstance(width, (int, float)) or not WIDTHS[0] <= width <= WIDTHS[1]:
            raise ValueError(f"the width is {WIDTHS[0]} to {WIDTHS[1]} of the slide's height")
        self._expire(now)
        stroke = Stroke(sid, session, check_frame(frame), device, tool, color.lower(), round(float(width), 5),
                        bool(meta.get("sim")), check_points(points, STROKE_MAX), now)
        self.live[(session, sid)] = stroke
        return stroke

    def extend(self, session: str, stroke_id, points) -> list:
        stroke = self.live.get((session, stroke_id))
        if stroke is None:
            raise ValueError(f"no stroke {stroke_id} is being drawn")
        new = check_points(points, STROKE_MAX - len(stroke.points))
        stroke.points.extend(new)
        return new

    def end(self, session: str, stroke_id) -> Stroke:
        stroke = self.live.pop((session, stroke_id), None)
        if stroke is None:
            raise ValueError(f"no stroke {stroke_id} is being drawn")
        self.strokes[session][stroke.id] = stroke
        self._did(session, stroke.device, stroke.frame, ("add", [stroke.id]))
        return stroke

    def erase(self, session: str, device, frame, ids, now: int) -> list[Stroke]:
        check_device(device)
        check_frame(frame)
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ValueError("strokes: a list of stroke ids")
        gone = [s for s in (self.strokes[session].get(i) for i in ids)
                if s is not None and s.frame == frame and s.erased is None]
        for s in gone:
            s.erased = now
        if gone:
            self._did(session, device, frame, ("erase", [s.id for s in gone]))
        return gone

    def clear(self, session: str, device, frame, now: int) -> list[Stroke]:
        return self.erase(session, device, frame, [s.id for s in self.frame(session, check_frame(frame))], now)

    def undo(self, session: str, device, frame, now: int) -> tuple[str, list[Stroke]]:
        """The device's last action on the frame taken back: ('erase'|'restore', strokes)."""
        key = (session, check_device(device), check_frame(frame))
        if not self.undos.get(key):
            return "erase", []
        kind, ids = self.undos[key].pop()
        self.redos[key].append((kind, ids))
        return self._apply(session, "erase" if kind == "add" else "restore", ids, now)

    def redo(self, session: str, device, frame, now: int) -> tuple[str, list[Stroke]]:
        key = (session, check_device(device), check_frame(frame))
        if not self.redos.get(key):
            return "erase", []
        kind, ids = self.redos[key].pop()
        self.undos[key].append((kind, ids))
        return self._apply(session, "restore" if kind == "add" else "erase", ids, now)

    def frame(self, session: str, frame: str) -> list[Stroke]:
        """The frame's strokes, in the order they were drawn."""
        return [s for s in self.strokes[session].values() if s.frame == frame and s.erased is None]

    def drawing(self, session: str, frame: str) -> list[Stroke]:
        return [s for (sess, _), s in self.live.items() if sess == session and s.frame == frame]

    def move(self, old: str, new: str) -> list[Stroke]:
        """A new game of the same build (a restart, the next group) takes the ink over."""
        moved = self.strokes.pop(old, {})
        for s in moved.values():
            s.session = new
        self.strokes[new].update(moved)
        self.forget(old)
        return list(moved.values())

    def forget(self, session: str):
        """A game that ended: its ink stays in the store, not in memory."""
        self.strokes.pop(session, None)
        for book in (self.live, self.undos, self.redos):
            for key in [k for k in book if k[0] == session]:
                del book[key]

    def _apply(self, session: str, op: str, ids: list, now: int) -> tuple[str, list[Stroke]]:
        changed = []
        for i in ids:
            s = self.strokes[session].get(i)
            if s is not None and (s.erased is None) == (op == "erase"):
                s.erased = now if op == "erase" else None
                changed.append(s)
        return op, changed

    def _did(self, session: str, device: str, frame: str, action: tuple):
        key = (session, device, frame)
        self.undos[key].append(action)
        del self.undos[key][:-UNDO_MAX]
        self.redos.pop(key, None)

    def _expire(self, now: int):
        for key, s in list(self.live.items()):
            if now - s.created > LIVE_MS:
                del self.live[key]
