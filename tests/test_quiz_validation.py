# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Authoring checks that preserve the answer students can actually submit."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from texstage.build.latex import LatexError, compile_deck
from texstage.build.quiz import quiz_entries
from texstage.build.tqz import Tqz
from texstage.server.bundles import QuizDef
from texstage.server.scoring import judge, validate

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs pdflatex")


def compile_quiz(tmp_path: Path, body: str, mode="present"):
    tex = tmp_path / "answer.tex"
    tex.write_text("\\documentclass[aspectratio=169]{beamer}\n\\usepackage{texquiz}\n"
                   "\\begin{document}\n" + body + "\n\\end{document}\n", encoding="utf-8")
    return compile_deck(tex, mode, tmp_path, passes=1)


def playable(question) -> QuizDef:
    public, keys = quiz_entries(question, {})
    return QuizDef(question.id, public["type"], public["time"], public["points"], public["scored"],
                   public["leaderboard"], public["reveal"], public.get("select", "single"),
                   [a["id"] for a in public.get("answers", [])], public.get("numeric", {}),
                   public.get("open", {}), public, keys)


def log_text(tmp_path: Path, mode="present") -> str:
    text = (tmp_path / f"answer-{mode}.log").read_text(encoding="utf-8", errors="replace")
    return " ".join(text.replace("(texquiz)", " ").split())


def test_accepted_text_is_the_displayed_unicode_not_latex(tmp_path):
    result = compile_quiz(tmp_path, r"""
        \begin{quiz}[id=words, type=text]{Type an accepted answer.}
          \accept{AT\&T}
          \accept{M\"unchen}
          \accept{New~York}
          \accept{\textbf{RDF}}
          \accept{Crème brûlée}
          \accept{C\#}
          \accept{\texorpdfstring{$x^2$}{x squared}}
        \end{quiz}
        \begin{quiz}[id=next, type=text]{Next question.}\accept{Next}\end{quiz}
    """)
    questions = Tqz.read(result.tqz).questions
    q = playable(questions["words"])
    assert q.keys["accept"] == ["AT&T", "München", "New York", "RDF", "Crème brûlée", "C#", "x squared"]
    for answer in q.keys["accept"]:
        assert judge(q, validate(q, {"text": answer})).correct, answer
    assert not judge(q, validate(q, {"text": r"AT\&T"})).correct
    assert "accept" not in q.public
    assert questions["next"].accept == ["Next"]  # converted answers reset between quizzes


def test_unsupported_accepted_text_requires_an_explicit_plain_answer(tmp_path):
    with pytest.raises(LatexError):
        compile_quiz(tmp_path, r"\begin{quiz}[id=math, type=text]{Name it.}\accept{$x^2$}\end{quiz}")
    assert "accepted text cannot be converted to plain text" in log_text(tmp_path)


@pytest.mark.parametrize("options, message", [
    ("answer=42,tolerance=-1", "tolerance must not be negative"),
    ("min=5,max=1", "min must not exceed max"),
    ("step=0", "step must be positive"),
    ("step=-0.5", "step must be positive"),
    ("answer=42,min=0,max=10", "no correct answer lies within the numeric bounds"),
    ("answer=-3,tolerance=2,min=0", "no correct answer lies within the numeric bounds"),
    ("answer=13,tolerance=2,max=10", "no correct answer lies within the numeric bounds"),
    ("answer=0.5,min=0,max=1", "no correct answer is selectable"),
    ("answer=0.5,min=0.25,max=1.25,step=0.5", "no correct answer is selectable"),
])
def test_unanswerable_numeric_settings_are_authoring_errors(tmp_path, options, message):
    with pytest.raises(LatexError):
        compile_quiz(tmp_path, rf"\begin{{quiz}}[id=n,type=numeric,{options}]{{How many?}}\end{{quiz}}")
    assert message in log_text(tmp_path)


@pytest.mark.parametrize("mode", ["handout", "solutions"])
def test_numeric_settings_are_also_checked_outside_present_mode(tmp_path, mode):
    with pytest.raises(LatexError):
        compile_quiz(tmp_path, r"\begin{quiz}[id=n,type=numeric,answer=42,tolerance=-1]{How many?}\end{quiz}", mode)
    assert "tolerance must not be negative" in log_text(tmp_path, mode)


def test_numeric_bounds_allow_tolerance_overlap_and_unscored_estimates(tmp_path):
    result = compile_quiz(tmp_path, r"""
        \begin{quiz}[id=overlap,type=numeric,answer=12,tolerance=2,min=0,max=10,step=0.5]{How many?}\end{quiz}
        \begin{quiz}[id=lower,type=numeric,answer=-2,tolerance=2,min=0]{How many?}\end{quiz}
        \begin{quiz}[id=estimate,type=numeric,min=-1.5,max=2.5,step=0.5]{Estimate it.}\end{quiz}
        \begin{quiz}[id=offset,type=numeric,answer=0.75,min=0.25,max=1.25,step=0.5]{How many?}\end{quiz}
        \begin{quiz}[id=integer,type=numeric,answer=2,min=1,max=3]{How many?}\end{quiz}
        \begin{quiz}[id=only,type=numeric,answer=0.25,min=0.25,max=0.25]{How many?}\end{quiz}
    """)
    questions = Tqz.read(result.tqz).questions
    for qid, value in (("overlap", 10), ("lower", 0), ("offset", 0.75), ("integer", 2), ("only", 0.25)):
        q = playable(questions[qid])
        assert judge(q, validate(q, {"value": value})).correct
    estimate = playable(questions["estimate"])
    assert not estimate.scored
    assert estimate.points == "none"
    assert judge(estimate, validate(estimate, {"value": -0.5})).correct is None
