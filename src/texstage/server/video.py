# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The video on the server (docs/content-types-design.md, section 7; the registry: types.py).

Its state in the session, per video of the deck, {playing, time, at}: the media time (seconds)
at the server's time at (ms) - as the timer keeps its time - set by a presenter window
(video.play, video.pause, video.seek) and sent to every window with the stage's state, so a
reloaded projector goes on at the right second. A slide that does not show a playing video stops
it where it is - the next step of its frame, showing it too, does not -, and a video that plays by
itself (autoplay) starts from its start when a slide brings it. Its files: the posters are served
as the slide pictures are, a video only by a ticket (app.py: a <video> cannot send the key).
"""
from __future__ import annotations

import re

NAME = "video"
MESSAGES = ("video.play", "video.pause", "video.seek")      # from a presenter window
MEDIA = re.compile(r"^media/[0-9a-f]{16}\.(mp4|m4v|webm|mov)$")
POSTER = re.compile(r"^media/[0-9a-f]{16}\.(jpg|png)$")
TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
         ".jpg": "image/jpeg", ".png": "image/png"}


def handle(call, t: str, msg: dict) -> None:
    """A video message: the video's state in the stage (ValueError: refused)."""
    video, pos = msg.get("video"), msg.get("time")
    if not isinstance(video, str) or video not in call.items:
        raise ValueError("no such video in this deck")
    if isinstance(pos, bool) or not isinstance(pos, (int, float)) or not 0 <= pos < 86400:
        raise ValueError("time: the video's time, in seconds")
    stage = call.session.stage
    state = dict(stage.get(NAME) or {})
    playing = {"video.play": True, "video.pause": False}.get(t, (state.get(video) or {}).get("playing", False))
    state[video] = {"playing": playing, "time": round(float(pos), 3), "at": call.now}
    call.session.stage = {**stage, NAME: state}


def view(stage: dict) -> dict | None:
    return stage.get(NAME) or None


def slide(stage: dict, items: dict, before: tuple, after: tuple, now: int) -> dict:
    """The stage's state when the projector shows another slide: `before` the videos it showed,
    `after` those it shows now (none: a whiteboard page, a poll or sketches)."""
    old = stage.get(NAME) or {}
    state = {k: {"playing": False, "time": round(v["time"] + (now - v["at"]) / 1000, 3), "at": now}
             if v["playing"] and k not in after else v for k, v in old.items()}
    for k in after:
        if k not in before and items.get(k, {}).get("autoplay"):
            state[k] = {"playing": True, "time": float(items[k].get("start") or 0), "at": now}
    return stage if state == old else {**stage, NAME: state}


def media(items: dict) -> list[str]:
    """The bundle's video files (served by ticket)."""
    return sorted({v["media"] for v in items.values() if MEDIA.match(v.get("media", ""))})
