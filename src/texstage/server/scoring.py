# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Checking and scoring answers (docs/design.md, section 6.3). Pure functions.

A correct answer earns speed points, base x (1 - 1/2 x answer time / time limit): from the
full base (1000, or 2000 with points=double) for an instant answer down to half of it at
the end. Consecutive correct answers add a streak bonus of 100 from the second one on, at
most 500. With partial=true a multiple-choice or ordering answer earns the share of the
points it got right; it counts as correct (for the streak) only when it is exact. Polls,
open questions and sketches have no right answer; numeric ones only with an answer.

A sketch (texstage M6) is the strokes drawn on the phone: {"strokes": [{"c": colour 0-3,
"p": [x, y, x, y, ...]}]}, integers on a 1000 x 750 canvas (4:3), simplified on the phone so
that the answer stays under the server's message limit.
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass

from texstage.server.bundles import QuizDef

STREAK_STEP = 100
STREAK_MAX = 500
TEXT_MAX = 100
SKETCH_W, SKETCH_H = 1000, 750
SKETCH_STROKES = 300
SKETCH_NUMBERS = 6000                    # the x and y of all points together
SKETCH_COLOURS = 4


class InvalidAnswer(ValueError):
    """The answer does not fit the question (wrong type, unknown choice, out of range)."""


def normalize_text(text: str) -> str:
    """For comparing short-text and grouping open answers: case, accents and spacing do
    not matter ("Résumé  " == "resume")."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text).casefold())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def _text(answer: dict, limit: int) -> dict:
    text = answer.get("text")
    if not isinstance(text, str):
        raise InvalidAnswer("expected {'text': ...}")
    text = " ".join(text.split())
    if not text or len(text) > limit:
        raise InvalidAnswer(f"the text must have 1 to {limit} characters")
    return {"text": text}


def _int(v, top: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= top


def _sketch(answer: dict) -> dict:
    strokes = answer.get("strokes")
    if not isinstance(strokes, list) or not 1 <= len(strokes) <= SKETCH_STROKES:
        raise InvalidAnswer(f"a sketch has 1 to {SKETCH_STROKES} strokes")
    out, numbers = [], 0
    for s in strokes:
        p = s.get("p") if isinstance(s, dict) else None
        c = s.get("c", 0) if isinstance(s, dict) else None
        if not isinstance(p, list) or len(p) < 2 or len(p) % 2 or not _int(c, SKETCH_COLOURS - 1):
            raise InvalidAnswer("a stroke is {c: 0-3, p: [x, y, ...]}")
        if not all(_int(v, SKETCH_H if i % 2 else SKETCH_W) for i, v in enumerate(p)):
            raise InvalidAnswer(f"a sketch's points are integers within {SKETCH_W} x {SKETCH_H}")
        numbers += len(p)
        out.append({"c": c, "p": p})
    if numbers > SKETCH_NUMBERS:
        raise InvalidAnswer("the sketch has too many points")
    return {"strokes": out}


def validate(q: QuizDef, answer) -> dict:
    """The answer in its canonical form, or InvalidAnswer."""
    if not isinstance(answer, dict):
        raise InvalidAnswer("an answer is an object")
    kind = q.type
    if kind == "poll":
        kind = "multiple" if q.select == "multiple" else "single"
    if kind in ("single", "truefalse"):
        choice = answer.get("choice")
        if choice not in q.ids:
            raise InvalidAnswer(f"choice must be one of {', '.join(q.ids)}")
        return {"choice": choice}
    if kind == "multiple":
        choices = answer.get("choices")
        if not isinstance(choices, list) or not choices or any(c not in q.ids for c in choices):
            raise InvalidAnswer(f"choices must be a non-empty list of {', '.join(q.ids)}")
        return {"choices": sorted(set(choices), key=q.ids.index)}
    if kind == "order":
        order = answer.get("order")
        if not isinstance(order, list) or sorted(order) != sorted(q.ids) or len(set(order)) != len(q.ids):
            raise InvalidAnswer(f"order must list {', '.join(q.ids)}, each once")
        return {"order": list(order)}
    if kind == "numeric":
        value = answer.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise InvalidAnswer("expected {'value': <number>}")
        lo, hi = q.numeric.get("min"), q.numeric.get("max")
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            raise InvalidAnswer(f"the value must be between {lo} and {hi}")
        return {"value": value}
    if kind == "text":
        return _text(answer, TEXT_MAX)
    if kind == "open":
        return _text(answer, int(q.open.get("max_chars") or 80))
    if kind == "sketch":
        return _sketch(answer)
    raise InvalidAnswer(f"unknown question type {q.type}")


@dataclass
class Verdict:
    correct: bool | None      # None: the question has no right answer
    credit: float             # share of the points earned, 0..1


def judge(q: QuizDef, answer: dict) -> Verdict:
    k = q.keys
    if q.type in ("single", "truefalse"):
        ok = answer["choice"] in k.get("correct", [])
        return Verdict(ok, float(ok))
    if q.type == "multiple":
        chosen, right = set(answer["choices"]), set(k.get("correct", []))
        exact = chosen == right
        if k.get("partial") and right:
            return Verdict(exact, max(0.0, (len(chosen & right) - len(chosen - right)) / len(right)))
        return Verdict(exact, float(exact))
    if q.type == "order":
        solution = k.get("order", [])
        hits = sum(a == b for a, b in zip(answer["order"], solution))
        exact = hits == len(solution)
        return Verdict(exact, hits / len(solution) if k.get("partial") and solution else float(exact))
    if q.type == "numeric":
        if k.get("answer") is None:
            return Verdict(None, 0.0)
        ok = abs(answer["value"] - k["answer"]) <= (k.get("tolerance") or 0) + 1e-9
        return Verdict(ok, float(ok))
    if q.type == "text":
        ok = normalize_text(answer["text"]) in {normalize_text(a) for a in k.get("accept", [])}
        return Verdict(ok, float(ok))
    return Verdict(None, 0.0)            # poll, open, sketch


def speed_points(base: int, answer_ms: int, limit_ms: int) -> int:
    share = min(max(answer_ms, 0), limit_ms) / limit_ms if limit_ms > 0 else 1.0
    return int(base * (1 - share / 2) + 0.5)


def streak_bonus(streak: int) -> int:
    """Bonus for the streak-th correct answer in a row."""
    return min(STREAK_STEP * (streak - 1), STREAK_MAX) if streak >= 2 else 0
