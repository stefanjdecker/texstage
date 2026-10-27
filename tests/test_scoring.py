# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Checking and scoring answers (server/scoring.py, docs/design.md section 6.3)."""
from __future__ import annotations

import pytest

from texstage.server.bundles import QuizDef
from texstage.server.scoring import InvalidAnswer, judge, normalize_text, speed_points, streak_bonus, validate


def quiz(kind, ids=("A", "B", "C", "D"), keys=None, **kw) -> QuizDef:
    return QuizDef(id="q", type=kind, time=20, points="standard", scored=True, leaderboard=True, reveal="slide",
                   select=kw.get("select", "single"), ids=list(ids), numeric=kw.get("numeric", {}),
                   open=kw.get("open", {}), public={}, keys=keys or {})


def test_speed_points():
    assert speed_points(1000, 0, 20000) == 1000          # at once: the full base
    assert speed_points(1000, 10000, 20000) == 750
    assert speed_points(1000, 20000, 20000) == 500       # at the last moment: half
    assert speed_points(1000, 25000, 20000) == 500       # (late answers in the grace period)
    assert speed_points(2000, 2000, 20000) == 1900       # points=double


def test_streak_bonus():
    assert [streak_bonus(n) for n in range(1, 9)] == [0, 100, 200, 300, 400, 500, 500, 500]


@pytest.mark.parametrize("kind,answer", [
    ("single", {"choice": "E"}), ("single", {"choices": ["A"]}), ("single", "A"),
    ("multiple", {"choices": []}), ("multiple", {"choices": ["A", "X"]}),
    ("order", {"order": ["A", "B", "C"]}), ("order", {"order": ["A", "A", "B", "C"]}),
    ("numeric", {"value": "6"}), ("numeric", {"value": True}), ("numeric", {"value": 13}),
    ("numeric", {"value": float("nan")}), ("text", {"text": "   "}), ("text", {"text": "x" * 101}),
])
def test_invalid_answers(kind, answer):
    q = quiz(kind, numeric={"min": 0, "max": 12})
    with pytest.raises(InvalidAnswer):
        validate(q, answer)


def test_canonical_answers():
    assert validate(quiz("multiple"), {"choices": ["C", "A", "C"]}) == {"choices": ["A", "C"]}
    assert validate(quiz("text"), {"text": "  Resource   Description  "}) == {"text": "Resource Description"}
    assert validate(quiz("poll", select="multiple"), {"choices": ["B"]}) == {"choices": ["B"]}
    assert validate(quiz("open", open={"max_chars": 5}), {"text": "graph"}) == {"text": "graph"}
    with pytest.raises(InvalidAnswer):
        validate(quiz("open", open={"max_chars": 5}), {"text": "graphs"})


def test_judging():
    assert judge(quiz("single", keys={"correct": ["B"]}), {"choice": "B"}).correct is True
    assert judge(quiz("single", keys={"correct": ["B"]}), {"choice": "A"}).credit == 0
    many = quiz("multiple", keys={"correct": ["A", "C"], "partial": False})
    assert judge(many, {"choices": ["A", "C"]}).correct
    assert not judge(many, {"choices": ["A"]}).correct and judge(many, {"choices": ["A"]}).credit == 0
    partial = quiz("multiple", keys={"correct": ["A", "C"], "partial": True})
    assert judge(partial, {"choices": ["A"]}).credit == 0.5
    assert judge(partial, {"choices": ["A", "B"]}).credit == 0.0        # a wrong one costs one right one
    assert judge(partial, {"choices": ["A"]}).correct is False          # only an exact answer is "correct"
    order = quiz("order", ids="ABC", keys={"order": ["C", "A", "B"], "partial": True})
    assert judge(order, {"order": ["C", "B", "A"]}).credit == pytest.approx(1 / 3)
    assert judge(order, {"order": ["C", "A", "B"]}).correct
    num = quiz("numeric", keys={"answer": 6, "tolerance": 1})
    assert judge(num, {"value": 7}).correct and not judge(num, {"value": 7.5}).correct
    assert judge(quiz("numeric", keys={}), {"value": 7}).correct is None  # an estimate: no right answer
    text = quiz("text", keys={"accept": ["Résumé of RDF"]})
    assert judge(text, {"text": "resume  OF rdf"}).correct
    assert judge(quiz("poll"), {"choice": "A"}).correct is None


def test_normalize_text():
    assert normalize_text("  Ärger\tim  Büro ") == "arger im buro"
    assert normalize_text("ＲＤＦ") == "rdf"                              # full-width letters
