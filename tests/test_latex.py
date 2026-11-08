# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texquiz.sty: output modes, metadata, geometry, phone assets, answer-leak checks.

Compiles with the installed pdflatex; the demo deck compile is shared per module.
"""
from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path

import pytest

from texstage.build.check import page_logs
from texstage.build.latex import LatexError, compile_deck
from texstage.build.pdf import Pdf
from texstage.build.tqz import Tqz

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs pdflatex")

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo" / "demo.tex"
DEMO_FRAMES = 12          # authored frames: 2 ordinary, join, 8 quizzes, podium
PLAIN = re.compile(r"[A-Za-z0-9 ,.?:;()/-]+")   # no macros, math, ties or ligatures
PREAMBLE = r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texquiz}
\begin{document}
"""


def deck(tmp: Path, name: str, body: str) -> Path:
    tex = tmp / f"{name}.tex"
    tex.write_text(PREAMBLE + textwrap.dedent(body) + "\n\\end{document}\n", encoding="utf-8")
    return tex


def render(pdf: Path, page: int) -> bytes:
    with Pdf(pdf) as doc:
        return doc[page - 1].render(1).tobytes()


def contains(box, inner) -> bool:
    """Whether the box (x0, y0, x1, y1) holds `inner`, a box or a point (x, y)."""
    x0, y0, x1, y1 = inner if len(inner) == 4 else (*inner, *inner)
    return box[0] <= x0 and box[1] <= y0 and x1 <= box[2] and y1 <= box[3]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    return {
        "handout": compile_deck(DEMO, "handout", out),
        "solutions": compile_deck(DEMO, "solutions", out),
        "present": compile_deck(DEMO, "present", out, notes=True),
    }


@pytest.fixture(scope="module")
def tqz(built):
    return Tqz.read(built["present"].tqz)


def pdf_text(pdf: Path) -> str:
    with Pdf(pdf) as doc:
        return "\n".join(p.text() for p in doc)


# ------------------------------------------------------------------ modes

def test_handout_has_one_page_per_frame_and_no_question_text(built, tqz):
    with Pdf(built["handout"].pdf) as doc:
        assert len(doc) == DEMO_FRAMES
    text = pdf_text(built["handout"].pdf)
    assert text.count("Live quiz") == 8
    for q in tqz.questions.values():
        words = q.prompt.split()[:4]
        assert " ".join(words) not in text, q.id
        for c in q.choices:
            if c.source not in ("True", "False"):
                assert c.source not in text, (q.id, c.source)
        if q.explanation:
            assert q.explanation[:20] not in text
    assert built["handout"].overfull == 0


def test_solutions_show_questions_and_explanations(built):
    with Pdf(built["solutions"].pdf) as doc:
        assert len(doc) == DEMO_FRAMES
    text = pdf_text(built["solutions"].pdf)
    assert "Which components form an RDF triple?" in text
    assert "An RDF triple consists of a subject" in text
    assert "Resource Description Framework" in text      # accepted answers
    assert "Answer: 6" in text                            # numeric answer
    assert built["solutions"].overfull == 0


def test_present_page_sequence(built, tqz):
    with Pdf(built["present"].pdf) as doc:
        slides = len(doc) - len(tqz.assets)
    seq = [(p.kind, p.quiz, p.phase) for _, p in sorted(tqz.pages.items())]
    assert seq[0] == ("join", "", "join")
    i = seq.index(("quiz", "rdf-triple", "read"))               # the question alone first
    assert seq[i + 1:i + 3] == [("quiz", "rdf-triple", "question"), ("quiz", "rdf-triple", "reveal")]
    assert seq[-1] == ("podium", "", "podium")
    # 2 ordinary + join + podium + 8 quizzes x (read, question, reveal); leaderboards are
    # added by the builder, not typeset
    assert slides == 2 + 1 + 1 + 24 == 28
    assert max(tqz.pages) <= slides
    assert tqz.questions["rdf-triple"].leaderboard
    assert not tqz.questions["favourite-format"].leaderboard      # polls: no leaderboard


def test_frame_numbers_match_between_handout_and_present(built):
    """A quiz is one frame with three slides, so the projector shows the same frame
    numbers as the handout ("n / 12" in the demo's footline)."""
    with Pdf(built["handout"].pdf) as h, Pdf(built["present"].pdf) as p:
        handout_last = h[-1].text().split()[-3:]
        slides = [page for page in p if "/ 12" in page.text()]
        assert handout_last == ["12", "/", "12"]
        assert slides[-1].text().split()[-3:] == ["12", "/", "12"]


def test_the_decks_language_is_babels(tqz, tmp_path):
    """The D record names the deck's language, which texstage's windows speak: babel's main one -
    the last of its options, also when babel comes after texstage.sty -, and English without
    babel (the demo; the format's \\languagename)."""
    assert tqz.language == "english"
    tex = tmp_path / "german.tex"
    tex.write_text("\\documentclass[aspectratio=169]{beamer}\n\\usepackage{texquiz}\n"
                   "\\usepackage[english,ngerman]{babel}\n\\begin{document}\n"
                   "\\begin{frame}{Eine Folie}Text.\\end{frame}\n\\end{document}\n", encoding="utf-8")
    assert Tqz.read(compile_deck(tex, "present", tmp_path / "out", passes=1).tqz).language == "ngerman"


# a deck with a slide text of each kind: the join slide, a true/false, a numeric and a multiple
# choice question's hints, a live activity's box
LANGUAGE_BODY = r"""
\quizjoinframe
\begin{quiz}[id=tf, type=truefalse, answer=false]{Statement one.}\end{quiz}
\begin{quiz}[id=num, type=numeric, answer=6, min=0, max=12]{How many?}\end{quiz}
\begin{quiz}[id=multi]{Which?}
  \choice*{One}
  \choice*{Two}
  \choice{Three}
\end{quiz}
\begin{frame}[t]{Triples}
  \begin{activity}[id=tuples,input=tuple,fields={S,P,O}]
    \prompt{A triple.}
  \end{activity}
\end{frame}
"""
ENGLISH_TEXTS = ["Join the quiz", "Enter a number on your phone.", "Several answers can be correct.", "True", "False",
                 "Live activity"]
GERMAN_TEXTS = ["Mitmachen", "Geben Sie auf Ihrem Handy eine Zahl ein.", "Mehrere Antworten k", "Wahr", "Falsch",
                "Live-Aktivit"]          # (an umlaut's accent comes apart in the OT1 font's text)


def language_text(tmp: Path, name: str, preamble: str = "") -> str:
    tex = tmp / f"{name}.tex"
    tex.write_text("\\documentclass[aspectratio=169]{beamer}\n" + preamble
                   + "\\usepackage{texquiz}\n\\usepackage{texactivity}\n\\begin{document}\n"
                   + textwrap.dedent(LANGUAGE_BODY) + "\\end{document}\n", encoding="utf-8")
    return " ".join(pdf_text(compile_deck(tex, "present", tmp / f"{name}-out", passes=1).pdf).split())


def test_the_slides_texts_are_in_the_decks_language(tmp_path):
    """texquiz's and texactivity's slide texts follow the deck's language, babel's main one
    (texstage.sty, section "language"): a German deck's join slide, hints, true/false labels and
    activity box are German; a deck without babel keeps English."""
    english = language_text(tmp_path, "english")
    german = language_text(tmp_path, "german", "\\usepackage[english,ngerman]{babel}\n")
    for en, de in zip(ENGLISH_TEXTS, GERMAN_TEXTS):
        assert en in english and de not in english, (en, de)
        assert de in german and en not in german, (en, de)


def test_a_text_quizsetup_gives_stays_in_any_language(tmp_path):
    """A text \\quizsetup gives - in the preamble, as a course theme does, before babel or after it -
    goes over the deck's language's; the other texts stay the language's."""
    setup = "\\usepackage{texquiz}\n\\quizsetup{join-title={Machen Sie mit}, number-hint={Bitte eine Zahl.}}\n"
    german = language_text(tmp_path, "german", setup + "\\usepackage[ngerman]{babel}\n")
    assert "Machen Sie mit" in german and "Bitte eine Zahl." in german
    assert "Mitmachen" not in german and "Geben Sie" not in german and "Mehrere Antworten k" in german
    english = language_text(tmp_path, "english", "\\usepackage{texquiz}\n\\quizsetup{join-title={Phones out}}\n")
    assert "Phones out" in english and "Join the quiz" not in english and "Enter a number on your phone." in english


def test_metadata(tqz):
    q = tqz.questions["rdf-triple"]
    assert (q.type, q.time, q.points, q.leaderboard) == ("single", 20, "standard", True)
    assert [c.correct for c in q.choices] == [False, True, False, False]
    assert q.prompt == "Which components form an RDF triple?"
    assert tqz.questions["iri-terms"].type == "multiple"
    assert tqz.questions["iri-terms"].points == "double"
    assert tqz.questions["owl-dl"].type == "truefalse"
    assert [c.correct for c in tqz.questions["owl-dl"].choices] == [False, True]
    assert tqz.questions["favourite-format"].points == "none"
    assert tqz.questions["triples-count"].numeric["answer"] == "6"
    assert tqz.questions["rdf-acronym"].accept == ["Resource Description Framework",
                                                   "Resource Description Format"]
    assert tqz.questions["kg-associations"].open["display"] == "wordcloud"


def test_shuffle_is_deterministic_and_ordering_never_solved(tqz):
    assert tqz.questions["rdf-triple"].order == [1, 2, 3, 4]          # no shuffle requested
    assert sorted(tqz.questions["iri-terms"].order) == [1, 2, 3, 4]
    assert tqz.questions["iri-terms"].order != [1, 2, 3, 4]
    assert tqz.questions["sparql-order"].order != [1, 2, 3, 4]


# ------------------------------------------------------------------ geometry

def test_rectangles_contain_their_text(built, tqz):
    """Recorded rectangles (second-screen notes mode, pgfpages) must cover the
    typeset prompt and choices exactly."""
    with Pdf(built["present"].pdf) as doc:
        for pno, pg in tqz.pages.items():
            if pg.kind != "quiz":
                continue
            q = tqz.questions[pg.quiz]
            page = doc[pno - 1]
            assert page.width == pytest.approx(2 * tqz.paper[0], abs=0.5)   # slide | notes
            words = page.words()
            for key, rect in pg.rects.items():
                if key not in ("prompt",) and not key.startswith("choice-"):
                    continue
                # word boxes use the font's full ascender/descender: allow 2pt
                x0, y0, x1, y1 = rect.top_down(page.height)
                box = (x0 - 2, y0 - 2, x1 + 2, y1 + 2)
                inside = " ".join(w[4] for w in words if contains(box, w[:4]))
                if key == "prompt":
                    expected = q.prompt
                else:
                    expected = next(c.source for c in q.choices if f"choice-{c.id}" == key)
                if PLAIN.fullmatch(expected):   # sources TeX prints verbatim
                    assert inside == expected, (pno, key)


def test_rectangles_in_a_shrunk_frame(tmp_path):
    """Beamer shrinks by scaling the finished frame with a PDF transformation that
    \\pdfsavepos does not see; the reader maps the rectangles back. Once shrunk as
    requested, once more than requested (too much content)."""
    filler = "\n\n".join(f"Material line {i}." for i in range(12))
    for shrink, extra in ((20, ""), (5, filler)):
        tex = deck(tmp_path, f"shrunk{shrink}", rf"""
            \begin{{frame}}[t,shrink={shrink},quiz]{{Shrunk}}
            Some material. {extra}
            \begin{{quiz}}[id=shrunk]{{Which one?}}
              \choice{{Alpha}}\choice*{{Beta}}\choice{{Gamma}}\choice{{Delta}}
            \end{{quiz}}
            \end{{frame}}""")
        r = compile_deck(tex, "present", tmp_path / str(shrink), passes=1)
        t = Tqz.read(r.tqz)
        qn = next(n for n, g in t.pages.items() if g.phase == "question")
        # the reading page, shrunk by the same factor: its prompt exactly where the question's is
        assert t.pages[qn - 1].phase == "read" and t.pages[qn - 1].rects["prompt"] == t.pages[qn].rects["prompt"]
        with Pdf(r.pdf) as doc:
            page = doc[qn - 1]
            words = {w[4]: w[:4] for w in page.words()}
            rects = t.pages[qn].rects
            for key, word in (("choice-A", "Alpha"), ("choice-D", "Delta"), ("prompt", "Which")):
                # word boxes use the font's full ascender/descender: test their centres
                box = rects[key].top_down(page.height)
                x0, y0, x1, y1 = words[word]
                assert contains(box, ((x0 + x1) / 2, (y0 + y1) / 2)), (shrink, key)
                if key != "prompt":                        # unscaled, a box would be too wide
                    assert contains(box, words[word]) and box[2] - box[0] < 0.5 * page.width, (shrink, key)


def test_shrunk_ordinary_frames_look_the_same_in_the_live_deck(tmp_path):
    """The present mode marks every shrunk frame (for the mapping above); an ordinary
    frame's picture in the PowerPoint must still be the handout page, pixel for pixel."""
    lines = "\n\n".join(f"Line {i} of an ordinary frame that needs shrinking." for i in range(16))
    tex = deck(tmp_path, "ordinary", rf"""
        \begin{{frame}}[t,shrink=10]{{Ordinary, shrunk}}
        {lines}
        \end{{frame}}
        \begin{{frame}}[shrink=5]{{Ordinary, centred, shrunk}}
        Short.
        \end{{frame}}""")
    h = compile_deck(tex, "handout", tmp_path / "h", passes=1)
    p = compile_deck(tex, "present", tmp_path / "p", notes=True, passes=1)
    with Pdf(h.pdf) as hd, Pdf(p.pdf) as pd:
        for i in range(2):
            slide = (0, 0, hd[i].width, hd[i].height)
            assert hd[i].render(2).tobytes() == pd[i].render(2, clip=slide).tobytes(), i


def test_the_reading_page_is_the_question_without_its_answers(built, tqz):
    """The reading page comes directly before the question page: the prompt where the
    question page has it, the answers' room empty - the lecturer's click only makes the
    answers appear (and starts the round)."""
    with Pdf(built["present"].pdf) as doc:
        for qid, q in tqz.questions.items():
            pages = {p.phase: (n, p) for n, p in tqz.pages.items() if p.quiz == qid and p.kind == "quiz"}
            (rn, read), (qn, question) = pages["read"], pages["question"]
            assert rn + 1 == qn, qid
            assert read.rects["prompt"] == question.rects["prompt"], qid
            assert not [k for k in read.rects if k.startswith(("choice-", "step-"))], qid
            page = doc[rn - 1]
            slide = page.text((0, 0, page.width / 2, page.height))
            for source in [c.source for c in q.choices] + q.steps:
                if PLAIN.fullmatch(source) and len(source) > 3 and source not in q.prompt:
                    assert source not in slide, (qid, source)


def test_choice_boxes_stay_put_between_question_and_reveal(tqz):
    for qid, q in tqz.questions.items():
        if not q.choices:
            continue
        pages = {p.phase: p for p in tqz.pages.values() if p.quiz == qid and p.kind == "quiz"}
        for key, r in pages["question"].rects.items():
            if key.startswith("choice-"):
                assert pages["reveal"].rects[key] == r, (qid, key)


def test_live_areas(tqz):
    kinds = {p.kind for p in tqz.pages.values() if "live" in p.rects}
    assert kinds == {"join", "podium", "quiz"}
    for p in tqz.pages.values():
        if "live" in p.rects:
            assert p.rects["live"].h > 50 and p.rects["live"].w > 300


def test_notes_are_on_the_right_half(built, tqz):
    page_no = next(n for n, p in tqz.pages.items() if p.quiz == "rdf-triple" and p.phase == "question")
    with Pdf(built["present"].pdf) as doc:
        page = doc[page_no - 1]
        w, h = page.width, page.height
        assert "Ask for an example" in page.text((w / 2, 0, w, h))
        assert "Ask for an example" not in page.text((0, 0, w / 2, h))


def test_join_and_podium_frames_take_a_note(tmp_path):
    """note={...} is the speaker note of a join, leaderboard or podium frame, which have no
    body to write \\note into: paragraphs and [stage directions] allowed, shown beside the
    slide wherever Beamer shows notes, never in the handout."""
    tex = deck(tmp_path, "notes", r"""
        \quizjoinframe[note={JOINNOTE, first paragraph. [Wait for the phones.]

        JOINSECOND paragraph.}]
        \begin{quiz}[id=q]{Which?}\choice*{A}\choice{B}\end{quiz}
        \quizpodiumframe[title=Final, note=PODIUMNOTE]""")
    p = compile_deck(tex, "present", tmp_path / "p", notes=True)
    t = Tqz.read(p.tqz)
    with Pdf(p.pdf) as d:
        for phase, words in (("join", ("JOINNOTE", "JOINSECOND", "[Wait for the phones.]")),
                             ("podium", ("PODIUMNOTE",))):
            page = d[next(n for n, g in t.pages.items() if g.phase == phase) - 1]
            w, h = page.width, page.height
            right = page.text((w / 2, 0, w, h))
            assert all(word in right for word in words), (phase, right)
            assert words[0] not in page.text((0, 0, w / 2, h))
    shown = tex.read_text(encoding="utf-8").replace(
        "\\usepackage{texquiz}", "\\usepackage{texquiz}\n\\setbeameroption{show notes on second screen}")
    notes = tmp_path / "shown.tex"
    notes.write_text(shown, encoding="utf-8")
    text = pdf_text(compile_deck(notes, "handout", tmp_path / "n", passes=1, explicit_mode=False).pdf)
    assert "JOINNOTE" in text and "PODIUMNOTE" in text                # the lecturer's notes PDF
    text = pdf_text(compile_deck(tex, "handout", tmp_path / "h", passes=1).pdf)
    assert "JOINNOTE" not in text and "PODIUMNOTE" not in text


STAGED = r"""
    \begin{frame}{One}
    First.\note{NOTEONE.}
    \end{frame}
    \begin{frame}{Steps}
    \begin{itemize}\item A \pause \item B\end{itemize}
    \note{NOTESTEPS.}
    \end{frame}
    \begin{frame}{Silent}
    No note.
    \end{frame}
    \quizjoinframe
    \begin{frame}[t,quiz]{Question}
    \begin{quiz}[id=q]{Which?}\choice*{A}\choice{B}\end{quiz}
    \note{NOTEQUIZ.}
    \end{frame}"""


def test_stage_notes_are_pages_of_their_own(tmp_path):
    """notes="stage" (texstage build --stage): the deck's own note page follows every slide
    whose frame has a note, as a page of its own and marked in the log; the slide pages hold
    no note text, there are no phone pages, and the PDF is the same file when nothing changed."""
    tex = deck(tmp_path, "staged", STAGED)
    s = compile_deck(tex, "present", tmp_path / "s", notes="stage")
    marked = [(p.page, ("note", "") in p.marks) for p in page_logs(s.log.read_text(encoding="latin-1"))]
    notes = [2, 4, 6, 10, 12, 14]               # after One, both steps, and read, question, reveal
    assert marked == [(n, n in notes) for n in range(1, 15)]
    with Pdf(s.pdf) as doc:
        assert len(doc) == 14
        texts = [page.text() for page in doc]
    for n, words in ((2, "NOTEONE"), (4, "NOTESTEPS"), (6, "NOTESTEPS"), (10, "NOTEQUIZ"), (14, "NOTEQUIZ")):
        assert words in texts[n - 1], n
    for n in range(1, 15):
        if n not in notes:
            assert "NOTE" not in texts[n - 1], n
    assert {p.phase: p.page for p in Tqz.read(s.tqz).pages.values()} == {"join": 8, "read": 9, "question": 11,
                                                                         "reveal": 13}
    again = compile_deck(tex, "present", tmp_path / "again", notes="stage")
    assert again.pdf.read_bytes() == s.pdf.read_bytes()


def test_phone_assets(built, tqz):
    keys = [(a.item, a.key) for a in tqz.assets]
    assert ("rdf-triple", "prompt") in keys and ("rdf-triple", "choice-B") in keys
    assert ("sparql-order", "step-4") in keys and ("owl-dl", "choice-true") in keys
    with Pdf(built["present"].pdf) as doc:
        first = len(doc) - len(tqz.assets)
        for i, a in enumerate(tqz.assets):
            page = doc[first + i]
            assert (page.width, page.height) == (pytest.approx(a.w, abs=0.5), pytest.approx(a.h, abs=0.5))
        prompt = doc[first + keys.index(("rdf-triple", "prompt"))]
        assert prompt.text().strip() == "Which components form an RDF triple?"
        assert prompt.render(1, alpha=True).getpixel((0, 0))[3] == 0      # transparent background


def test_long_answers_switch_to_one_column_and_widen_phone_images(tmp_path):
    tex = deck(tmp_path, "long", r"""
        \begin{quiz}[id=short]{Short?}\choice*{yes}\choice{no}\end{quiz}
        \begin{quiz}[id=long]{Which is valid N-Triples?}
          \choice*{\texttt{<http://ex.org/alice> <http://xmlns.com/foaf/0.1/knows> <http://ex.org/bob> .}}
          \choice{\texttt{ex:alice foaf:knows ex:bob .}}
        \end{quiz}""")
    r = compile_deck(tex, "present", tmp_path, passes=1)
    assert r.overfull == 0
    t = Tqz.read(r.tqz)
    widths = {p.quiz: p.rects["choice-A"].w for p in t.pages.values() if p.phase == "question"}
    assert widths["long"] > 1.9 * widths["short"]          # one column vs. two
    asset = next(a for a in t.assets if (a.item, a.key) == ("long", "choice-A"))
    assert asset.w > 5.4 / 2.54 * 72 + 10                   # wider than the 5.4 cm column


# ------------------------------------------------------------------ leaks

QUIZ = r"""
\begin{{quiz}}[id=leak]{{Which one?}}
  \choice{a}{{Alpha}}
  \choice{b}{{Beta}}
  \choice{c}{{Gamma}}
  \explain{{Because.}}
\end{{quiz}}
"""


def test_correct_answer_does_not_change_the_question_page(tmp_path):
    """Two decks differing only in the correct choice: reading and question pages must be
    pixel-identical, reveal pages must differ."""
    a = deck(tmp_path, "a", QUIZ.format(a="*", b="", c=""))
    b = deck(tmp_path, "b", QUIZ.format(a="", b="", c="*"))
    ra = compile_deck(a, "present", tmp_path / "a", passes=1)
    rb = compile_deck(b, "present", tmp_path / "b", passes=1)
    assert render(ra.pdf, 1) == render(rb.pdf, 1)      # reading
    assert render(ra.pdf, 2) == render(rb.pdf, 2)      # question
    assert render(ra.pdf, 3) != render(rb.pdf, 3)      # reveal
    ha = compile_deck(a, "handout", tmp_path / "a", passes=1)
    hb = compile_deck(b, "handout", tmp_path / "b", passes=1)
    assert render(ha.pdf, 1) == render(hb.pdf, 1)


def test_handout_page_does_not_depend_on_the_question(tmp_path):
    a = deck(tmp_path, "a", QUIZ.format(a="*", b="", c=""))
    other = deck(tmp_path, "other", r"""
        \begin{quiz}[id=other, type=numeric, answer=42]{How many? $\int_0^1 x\,dx$}
        \end{quiz}""")
    ha = compile_deck(a, "handout", tmp_path / "a", passes=1)
    ho = compile_deck(other, "handout", tmp_path / "o", passes=1)
    assert render(ha.pdf, 1) == render(ho.pdf, 1)


# ------------------------------------------------------------------ course-style frames

COURSE = r"""
\begin{frame}[t,fragile,quiz]{Question: How Many Solutions?}
\label{sl:test:question}
\begin{lstlisting}
SELECT ?c WHERE { ?c :locatedOnBank ?r . }  # listing material
\end{lstlisting}
Material: the graph has SECRETMATERIAL.
\begin{quiz}[id=cities, title={Question: How Many Solutions?}]{How many solution mappings?}
  \choice{2}\choice{3}\choice{4}\choice*{5}
\end{quiz}
\note{Script. Ask first.}
\end{frame}

\begin{frame}[t,fragile,answer]{Answer: Five -- the Self-Join Keeps the Diagonal}
\label{sl:test:answer}
\begin{lstlisting}
THEANSWERLISTING
\end{lstlisting}
The real answer to slide~\ref{sl:test:question}.
\end{frame}

\begin{frame}{After}
Question on slide~\ref{sl:test:question}, answer on slide~\ref{sl:test:answer}.
\end{frame}
"""


def course_deck(tmp: Path) -> Path:
    tex = tmp / "course.tex"
    preamble = PREAMBLE.replace(r"\begin{document}", "\\usepackage{listings}\n\\begin{document}")
    tex.write_text(preamble + COURSE + "\n\\end{document}\n", encoding="utf-8")
    return tex


def test_quiz_inside_an_authors_frame(tmp_path):
    tex = course_deck(tmp_path)
    h = compile_deck(tex, "handout", tmp_path / "h")
    s = compile_deck(tex, "solutions", tmp_path / "s")
    p = compile_deck(tex, "present", tmp_path / "p", notes=True)
    with Pdf(h.pdf) as d:
        assert len(d) == 3                                         # one page per frame
        text = "\n".join(page.text() for page in d)
    for secret in ("SECRETMATERIAL", "solution mappings", "THEANSWERLISTING", "Diagonal"):
        assert secret not in text, secret                          # question, answer, titles
    assert "Live quiz" in text and "The answer is shown in the lecture." in text
    assert "Question on slide 1, answer on slide 2." in text       # labels still resolve
    with Pdf(s.pdf) as d:
        assert len(d) == 3
        text = "\n".join(page.text() for page in d)
    assert "SECRETMATERIAL" in text and "THEANSWERLISTING" in text and "Diagonal" in text
    t = Tqz.read(p.tqz)
    with Pdf(p.pdf) as d:
        assert len(d) - len(t.assets) == 5                        # reading, question, reveal, answer, after
        assert all("SECRETMATERIAL" in d[i].text() for i in range(3))   # the material on all three
    assert [(n, g.phase) for n, g in sorted(t.pages.items())] == [(1, "read"), (2, "question"), (3, "reveal")]
    assert {"prompt", "choice-A", "choice-D"} <= set(t.pages[2].rects)
    assert t.pages[2].rects["choice-D"] == t.pages[3].rects["choice-D"]
    assert t.pages[1].rects["prompt"] == t.pages[2].rects["prompt"] and "choice-A" not in t.pages[1].rects
    assert "timer" not in t.pages[2].rects                         # inline: timer in the corner
    assert t.questions["cities"].title == "Question: How Many Solutions?"


def test_inline_quiz_explains_on_its_reveal(tmp_path):
    """A quiz in an author's frame that reveals on its own slide shows its \\explain there
    and in the solutions - below the answers, never on the question page or in the
    handout. With reveal=none the answer frame explains, so the quiz does not."""
    tex = course_deck(tmp_path)
    src = tex.read_text(encoding="utf-8").replace(r"\choice*{5}", r"\choice*{5}\explain{EXPLAINTEXT}")
    tex.write_text(src, encoding="utf-8")
    p = compile_deck(tex, "present", tmp_path / "p", notes=True)
    t = Tqz.read(p.tqz)
    with Pdf(p.pdf) as d:
        assert "EXPLAINTEXT" not in d[0].text() + d[1].text() and "EXPLAINTEXT" in d[2].text()
    assert "explain" in t.pages[3].rects and "explain" not in {**t.pages[1].rects, **t.pages[2].rects}
    explain, last = t.pages[3].rects["explain"], t.pages[3].rects["choice-D"]
    assert explain.y + explain.h <= last.y + 0.01                    # below the answers (y is up)
    assert "EXPLAINTEXT" in pdf_text(compile_deck(tex, "solutions", tmp_path / "s").pdf)
    assert "EXPLAINTEXT" not in pdf_text(compile_deck(tex, "handout", tmp_path / "h").pdf)
    tex.write_text(src.replace("[id=cities,", "[id=cities, reveal=none,"), encoding="utf-8")
    assert "EXPLAINTEXT" not in pdf_text(compile_deck(tex, "solutions", tmp_path / "s2").pdf)


def test_reveal_on_a_later_answer_frame(tmp_path):
    """Predict-then-see: reveal=none keeps the quiz to its reading and question slides;
    the answer frame names the quiz and is recorded for the live deck."""
    tex = course_deck(tmp_path)
    src = tex.read_text(encoding="utf-8")
    src = src.replace("[id=cities,", "[id=cities, reveal=none,")
    src = src.replace("[t,fragile,answer]", "[t,fragile,answer=cities]")
    tex.write_text(src, encoding="utf-8")
    p = compile_deck(tex, "present", tmp_path / "p", notes=True)
    t = Tqz.read(p.tqz)
    assert t.questions["cities"].reveal == "none"
    assert [(n, g.kind, g.quiz, g.phase) for n, g in sorted(t.pages.items())] == [
        (1, "quiz", "cities", "read"), (2, "quiz", "cities", "question"), (3, "answer", "cities", "answer")]
    with Pdf(p.pdf) as d:
        assert "THEANSWERLISTING" in d[2].text()                # the author's answer frame
    h = compile_deck(tex, "handout", tmp_path / "h")
    assert "THEANSWERLISTING" not in pdf_text(h.pdf)


def test_a_sketch_question(tmp_path):
    """type=sketch (texstage M6): the phones draw. Like an open question: the question with
    its hint, a live area, never scored; the handout keeps it a placeholder."""
    tex = deck(tmp_path, "sketch", r"""
        \begin{quiz}[id=draw-tree, type=sketch, time=90]{Draw the B$^+$ tree after inserting 7.}
        \end{quiz}
        \begin{frame}{After}x\end{frame}""")
    p = compile_deck(tex, "present", tmp_path / "p", notes=True)
    t = Tqz.read(p.tqz)
    q = t.questions["draw-tree"]
    assert (q.type, q.points, q.time, q.choices) == ("sketch", "none", 90, [])
    assert [(n, g.phase) for n, g in sorted(t.pages.items())] == [(1, "read"), (2, "question"), (3, "reveal")]
    assert {"prompt", "timer", "live"} <= set(t.pages[2].rects)
    with Pdf(p.pdf) as d:
        assert "Draw your answer on your phone." in d[1].text()
    assert "Draw the B" not in pdf_text(compile_deck(tex, "handout", tmp_path / "h").pdf)
    for body, message in ((r"\begin{quiz}[id=x, type=sketch]{Q?}\choice{a}\choice{b}\end{quiz}", "not allowed"),
                          (r"\begin{quiz}[id=x, type=sketch, points=double]{Q?}\end{quiz}", "is not scored")):
        with pytest.raises(LatexError, match=message):
            compile_deck(deck(tmp_path, "bad", body), "handout", tmp_path / "e", passes=1)


def test_texquiz_loaded_after_pgfpages(tmp_path):
    """dbis-style.sty with \\dbisnotes turns on second-screen notes (pgfpages) before it
    loads texquiz; the phone images must still be pages of their own size."""
    tex = tmp_path / "late.tex"
    tex.write_text(r"""\documentclass[aspectratio=169]{beamer}
\setbeameroption{show notes on second screen}
\usepackage{texquiz}
\begin{document}
\begin{quiz}[id=late]{Which one?}\choice*{Alpha}\choice{Beta}\end{quiz}
\begin{frame}{After}x\end{frame}
\end{document}
""", encoding="utf-8")
    for mode in ("handout", "present"):
        r = compile_deck(tex, mode, tmp_path / mode, passes=1)
        if mode == "present":
            t = Tqz.read(r.tqz)
            with Pdf(r.pdf) as d:
                assert len(d) == 4 + len(t.assets)              # reading, question, reveal, after + images
                assert d[-1].width == pytest.approx(t.assets[-1].w, abs=0.5)


def test_notes_build_defaults_to_solutions(tmp_path):
    """A lecturer's notes PDF (Beamer shows notes, e.g. build-chapter.py --notes)
    keeps quizzes and answer frames readable."""
    tex = course_deck(tmp_path)
    src = tex.read_text(encoding="utf-8").replace(
        "\\usepackage{texquiz}", "\\usepackage{texquiz}\n\\setbeameroption{show notes on second screen}")
    tex.write_text(src, encoding="utf-8")
    r = compile_deck(tex, "handout", tmp_path / "n", passes=1, explicit_mode=False)
    text = pdf_text(r.pdf)
    assert "THEANSWERLISTING" in text and "solution mappings" in text


# ------------------------------------------------------------------ errors

@pytest.mark.parametrize("body, message", [
    (r"\begin{quiz}[id=x]{Q?}\choice{a}\choice{b}\end{quiz}", "mark a correct choice"),
    (r"\begin{quiz}{Q?}\choice*{a}\choice{b}\end{quiz}", "id is required"),
    (r"\begin{quiz}[id=Bad_Id]{Q?}\choice*{a}\choice{b}\end{quiz}", "id is required"),
    (r"\begin{quiz}[id=x]{Q?}\choice*{a}\choice{b}\end{quiz}"
     r"\begin{quiz}[id=x]{Q?}\choice*{a}\choice{b}\end{quiz}", "duplicate quiz id"),
    (r"\begin{quiz}[id=x]{Q?}\choice*{a}\end{quiz}", "needs 2--6 choices"),
    (r"\begin{quiz}[id=x]{Q?}Some text \choice*{a}\choice{b}\end{quiz}", "text outside"),
    (r"\begin{quiz}[id=x, colour=red]{Q?}\choice*{a}\choice{b}\end{quiz}", "unknown key 'colour'"),
    (r"\quizjoinframe[notes={Hello}]", "unknown key 'notes'"),
    (r"\begin{quiz}[id=x, type=truefalse]{Q?}\end{quiz}", "answer=true or answer=false"),
    (r"\begin{quiz}[id=x, type=poll]{Q?}\choice*{a}\choice{b}\end{quiz}", "a poll has no correct"),
    (r"\begin{quiz}[id=x, type=poll, points=double]{Q?}\choice{a}\choice{b}\end{quiz}", "is not scored"),
    (r"\begin{quiz}[id=x, type=numeric, answer=4x]{Q?}\end{quiz}", "answer must be a decimal"),
    (r"\begin{quiz}[id=x, type=order]{Q?}\step{only}\end{quiz}", "needs 2--6 steps"),
    (r"\begin{quiz}[id=x, time=2]{Q?}\choice*{a}\choice{b}\end{quiz}", "time must be 5--240"),
    (r"\begin{frame}\begin{quiz}[id=x]{Q?}\choice*{a}\choice{b}\end{quiz}\end{frame}",
     "needs the frame option 'quiz', e.g. \\begin{frame}[t,quiz]"),
])
def test_authoring_errors(tmp_path, body, message):
    tex = deck(tmp_path, "err", body)
    with pytest.raises(LatexError) as err:
        compile_deck(tex, "handout", tmp_path, passes=1)
    flat = " ".join(str(err.value).replace("(texquiz)", " ").split())
    assert message in flat, flat


@pytest.mark.parametrize("body, message", [
    (r"\video{clip.mp4}", "poster is required"),
    (r"\video[poster=clip.png]{gone.mp4}", "the file 'gone.mp4' is not there"),
    (r"\video[poster=clip.png, colour=red]{clip.mp4}", "unknown key 'colour'"),
    (r"\video[poster=clip.png]{clip.mp4}\end{frame}\begin{frame}\video[poster=clip.png, start=3]{clip.mp4}",
     "the id names another video"),
    (r"\video[poster=clip.png, width=2cm]{clip.mp4}\video[poster=clip.png, width=2cm]{clip.mp4}",
     "the video is twice on this slide"),
])
def test_video_authoring_errors(tmp_path, body, message):
    """texvideo.sty: one id, one video - the same one may come again (test_build.py), another
    one under its id may not."""
    from PIL import Image
    Image.new("RGB", (32, 18)).save(tmp_path / "clip.png")
    (tmp_path / "clip.mp4").write_bytes(b"x")
    tex = tmp_path / "err.tex"
    tex.write_text(f"\\documentclass{{beamer}}\n\\usepackage{{texvideo}}\n\\begin{{document}}\n"
                   f"\\begin{{frame}}{body}\\end{{frame}}\n\\end{{document}}\n", encoding="utf-8")
    with pytest.raises(LatexError) as err:
        compile_deck(tex, "handout", tmp_path, passes=1)
    flat = " ".join(str(err.value).replace("(texvideo)", " ").split())
    assert message in flat, flat


ACTIVITY_DECK = r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texactivity}
\begin{document}
\begin{frame}[t,label=graph]{Graph}
\begin{activity}[id=crowd, suggest={:KG, :teaches}, min=2]
  \prompt{Add triples about this lecture.}
\end{activity}
\end{frame}
\begin{frame}[t,fragile]{Query}
\begin{activity}[id=join, input=code, engine=sparql, seed=uni.ttl, height=4cm, tokens={SELECT, \{}]
  \prompt{The professors with their lectures.}
  \reference{SELECT ?n WHERE {
  ?p :name ?n .   # REFERENCECOMMENT
}}
\end{activity}
\pause Next step.
\end{frame}
\againframe<1>{graph}
\end{document}
"""


def test_a_live_activity(tmp_path):
    """texactivity.sty (docs/live-activities-design.md, section 5): the box in every mode - the
    solutions add the reference, verbatim, its lines and its # kept -; in present mode the box on
    every slide that shows the activity (the steps of its frame, the frame again), the records
    and the prompt for the phones once."""
    from texstage.build.activity import read
    tex = tmp_path / "act.tex"
    tex.write_text(ACTIVITY_DECK, encoding="utf-8")
    p = compile_deck(tex, "present", tmp_path / "p")
    t = Tqz.read(p.tqz)
    assert [(n, [(i.kind, i.id) for i in page.items]) for n, page in sorted(t.pages.items())] == [
        (1, [("activity", "crowd")]), (2, [("activity", "join")]), (3, [("activity", "join")]),
        (4, [("activity", "crowd")])]
    assert set(t.pages[1].items[0].rects) == {"box"}
    assert t.pages[2].items[0].rects["box"].h == pytest.approx(4 / 2.54 * 72, abs=0.5)     # height=4cm
    assert [(a.item, a.key) for a in t.assets] == [("activity:crowd", "prompt"), ("activity:join", "prompt")]
    acts = read(t)
    assert (acts["crowd"].fields, acts["crowd"].suggest, acts["crowd"].min) == (
        ["Subject", "Predicate", "Object"], [":KG", ":teaches"], "2")
    assert (acts["join"].input, acts["join"].engine, acts["join"].tokens, acts["join"].seed) == (
        "code", "sparql", ["SELECT", "{"], "uni.ttl")
    assert acts["join"].references == ["SELECT ?n WHERE {\n  ?p :name ?n .   # REFERENCECOMMENT\n}"]
    with Pdf(p.pdf) as d:
        assert len(d) == 4 + 2                                  # four slides, two phone pictures
        assert "Live activity" in d[0].text() and "REFERENCECOMMENT" not in pdf_text(p.pdf)
    h = compile_deck(tex, "handout", tmp_path / "h")
    assert "Add triples" in pdf_text(h.pdf) and "REFERENCECOMMENT" not in pdf_text(h.pdf)
    s = compile_deck(tex, "solutions", tmp_path / "s")
    assert "?p :name ?n . # REFERENCECOMMENT" in " ".join(pdf_text(s.pdf).split()) and s.overfull == 0


@pytest.mark.parametrize("body, message", [
    (r"\begin{activity}\prompt{x}\end{activity}", "an activity needs an id"),
    (r"\begin{activity}[id=Bad]\end{activity}", "an id has lowercase letters"),
    (r"\begin{activity}[id=a, input=code]\end{activity}", "input=code needs an engine"),
    (r"\begin{activity}[id=a, engine=sparql]\end{activity}", "input=tuple takes no engine"),
    (r"\begin{activity}[id=a, colour=red]\end{activity}", "unknown key 'colour'"),
    (r"\begin{activity}[id=a]\end{activity}\begin{activity}[id=b]\end{activity}", "a frame has one activity"),
    (r"\begin{activity}[id=a]\end{activity}\end{frame}\begin{frame}\begin{activity}[id=a, min=3]\end{activity}",
     "the id names another activity"),
])
def test_activity_authoring_errors(tmp_path, body, message):
    """texactivity.sty refuses what it can tell: an id, an engine for code and none for a tuple,
    one activity per frame, one id for one activity."""
    tex = tmp_path / "err.tex"
    tex.write_text(f"\\documentclass{{beamer}}\n\\usepackage{{texactivity}}\n\\begin{{document}}\n"
                   f"\\begin{{frame}}{body}\\end{{frame}}\n\\end{{document}}\n", encoding="utf-8")
    with pytest.raises(LatexError) as err:
        compile_deck(tex, "handout", tmp_path, passes=1)
    flat = " ".join(str(err.value).replace("(texactivity)", " ").split())
    assert message in flat, flat


def test_a_poll_with_several_answers_has_its_own_hint(tmp_path):
    """A poll has no right answers: under several answers it says "Tick all that apply." (or the
    deck's poll-hint) - a scored question keeps "Several answers can be correct."."""
    tex = deck(tmp_path, "hints", r"""
        \begin{quiz}[id=poll, type=poll, select=multiple]{Which do you use?}
          \choice{Coffee}\choice{Tea}
        \end{quiz}
        \begin{quiz}[id=scored, type=multiple]{Which are prime?}
          \choice*{Two}\choice{Four}
        \end{quiz}
        \quizsetup{poll-hint={Pick any.}}
        \begin{quiz}[id=own, type=poll, select=multiple]{Which again?}
          \choice{Coffee}\choice{Tea}
        \end{quiz}""")
    result = compile_deck(tex, "present", tmp_path / "out")
    with Pdf(result.pdf) as doc:
        texts = [" ".join(doc[i].text().split()) for i in range(len(doc))]
    question = {q: next(t for t in texts if title in t and ("Coffee" in t or "Two" in t))
                for q, title in (("poll", "Which do you use?"), ("scored", "Which are prime?"), ("own", "Which again?"))}
    assert "Tick all that apply." in question["poll"] and "can be correct" not in question["poll"]
    assert "Several answers can be correct." in question["scored"]
    assert "Pick any." in question["own"]


def test_the_core_loads_without_the_quiz(tmp_path):
    """texstage.sty, the core under the content types' packages, works on its own - a deck of
    a type that is not the quiz (a video, a cell) loads only it: the present compile writes
    the .tqz with the paper, the log has the page marks, and a page record of another kind,
    with its rectangle, reaches the build's reader."""
    tex = tmp_path / "core.tex"
    tex.write_text(r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texstage}
\ExplSyntaxOn
\cs_new_protected:Npn \demobox
  {
    \texstage_page_record:nnn { video } { clip } { show }
    \leavevmode \texstage_rect:nnnnn { clip } { show } { box } { 4cm } { 2cm } \rule{4cm}{2cm}
  }
\ExplSyntaxOff
\begin{document}
\begin{frame}{A box}\demobox\end{frame}
\end{document}
""", encoding="utf-8")
    r = compile_deck(tex, "present", tmp_path / "out", passes=1)
    t = Tqz.read(r.tqz)
    assert t.paper[0] > t.paper[1] > 0 and not t.questions and not t.assets and t.language == "english"
    (page,) = t.pages.values()
    assert (page.kind, page.quiz, page.phase) == ("video", "clip", "show") and set(page.rects) == {"box"}
    assert abs(page.rects["box"].w - 4 / 2.54 * 72) < 0.5
    assert "texquiz-check: page 1" in r.log.read_text(encoding="latin-1")