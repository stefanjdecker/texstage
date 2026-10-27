# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Ad-hoc polls (texstage M6, docs/texstage-design.md, sections 10 and 21): questions the
lecturer types during the lecture, with formulas between $...$:

    yesno    Yes / No                         poll, one answer
    choice   A-D (2 to 6), texts optional     poll, one or several answers
    scale    1 to 5                           poll, one answer
    words    a word cloud                     open, up to 24 characters
    text     free text, as a list             open, up to 140 characters
    sketch   a drawing on the phone           sketch

A poll belongs to the game, not to the deck: the session keeps its quiz definition - the
public part the phones get (texts where a deck's quizzes have pictures) and the keys (here
only the texts again, as the build keeps a quiz's LaTeX source) - and the game treats it like
a quiz of the deck: the round cycle, the views, the results table. Its reveal is "auto": the
results show as soon as the round closes, there is no reveal slide.
"""
from __future__ import annotations

import unicodedata

from texstage.server.bundles import QuizDef

KINDS = ("yesno", "choice", "scale", "words", "text", "sketch")
TIMES = {"yesno": 30, "choice": 30, "scale": 30, "words": 45, "text": 90, "sketch": 120}
TIME_MIN, TIME_MAX = 10, 600
PROMPT_MAX = 300
ANSWER_MAX = 120
POLLS_MAX = 100                          # per game
SCALE = 5
TITLES = {"sketch": "Sketch"}


class PollError(ValueError):
    """A poll the presenter window should not have sent (the message says why)."""


def clean(text, limit: int, lines: bool = False) -> str:
    """Typed text: no control characters (line breaks only if `lines`), single spaces."""
    if text is None:
        return ""
    if not isinstance(text, str):
        raise PollError("a text is a string")
    text = unicodedata.normalize("NFC", text)
    if lines:
        text = "\n".join(line for line in (clean(part, limit) for part in text.splitlines()) if line)
    else:
        text = " ".join("".join(c for c in text if not unicodedata.category(c).startswith("C")).split())
    if len(text) > limit:
        raise PollError(f"at most {limit} characters")
    return text


def make_poll(spec) -> tuple[dict, dict]:
    """(public, keys) of a poll from what the presenter window sends:
    {kind, prompt?, answers? (choice: 2-6 texts, may be empty; yesno: 2), select?, time?}."""
    if not isinstance(spec, dict) or spec.get("kind") not in KINDS:
        raise PollError(f"a poll is {', '.join(KINDS)}")
    kind = spec["kind"]
    prompt = clean(spec.get("prompt"), PROMPT_MAX, lines=True)
    time = spec.get("time", TIMES[kind])
    if isinstance(time, bool) or not isinstance(time, int) or not TIME_MIN <= time <= TIME_MAX:
        raise PollError(f"a poll runs {TIME_MIN} to {TIME_MAX} seconds")
    qtype = {"words": "open", "text": "open", "sketch": "sketch"}.get(kind, "poll")
    public = {"type": qtype, "title": TITLES.get(kind, "Poll"), "time": time, "points": "none", "scored": False,
              "leaderboard": False, "reveal": "auto", "adhoc": kind, "prompt": {"text": prompt} if prompt else None}
    keys: dict = {"prompt": prompt}
    if qtype == "poll":
        given = spec.get("answers")
        if kind == "scale":
            texts = [str(i) for i in range(1, SCALE + 1)]
        elif given is None:
            texts = ["Yes", "No"] if kind == "yesno" else ["", "", "", ""]
        elif not isinstance(given, list) or not (len(given) == 2 if kind == "yesno" else 2 <= len(given) <= 6):
            raise PollError("yes/no has 2 answers, A-D 2 to 6")
        else:
            texts = [clean(t, ANSWER_MAX) for t in given]
        select = spec.get("select", "single") if kind == "choice" else "single"
        if select not in ("single", "multiple"):
            raise PollError("select is single or multiple")
        public["select"] = select
        public["answers"] = [{"id": chr(65 + i), "shape": i + 1, "text": t} for i, t in enumerate(texts)]
        keys["answers"] = {chr(65 + i): {"source": t} for i, t in enumerate(texts)}
    elif qtype == "open":
        public["open"] = {"display": "wordcloud", "max_chars": 24} if kind == "words" \
            else {"display": "list", "max_chars": 140}
    if not prompt and qtype != "poll":
        raise PollError("this poll needs its question")
    return public, keys


def poll_quiz(qid: str, entry: dict) -> QuizDef:
    """The game's quiz definition of a poll (entry: {public, keys}, as the session keeps it)."""
    public = entry["public"]
    return QuizDef(id=qid, type=public["type"], time=public["time"], points="none", scored=False, leaderboard=False,
                   reveal="auto", select=public.get("select", "single"),
                   ids=[a["id"] for a in public.get("answers", [])], numeric={}, open=public.get("open", {}),
                   public=public, keys=entry["keys"])
