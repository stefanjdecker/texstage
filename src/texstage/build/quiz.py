# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The quiz (texquiz) in the build: what the content type gives at the build's steps
(docs/content-types-design.md, section 5.2; the registry: types.py).

    records    the quiz's own (Q P C S L A E N O; tqz.py reads them into Tqz.questions)
    plan       a leaderboard slide after the reveal of every scored quiz that has one
    box        a slide's live box: the quiz's phase, its id, its rectangles
    entries    deck.json's items.quiz (what the phones see) and keys.json's (host only)
    files      the phone pictures (the extra pages: Tqz.assets)
    stored     the picture the live PPTX keeps for a slide (an answer slide: its question's)
    addin      the add-in object's properties of a live slide - the quiz's slides need the
               add-in, and so the live PPTX's first slide that prepares them
    solutions  whether the check needs the solutions compile

Answers are identified by their position on the question slide: A, B, C, ... - the labels
the slide shows. The authored ids (and the step numbers of an ordering question, which are
its solution) stay in keys.json.
"""
from __future__ import annotations

from texstage.build.bundle import content_name, public_rects
from texstage.build.tqz import Item, Question, Tqz

NAME = "quiz"
KINDS = {"quiz", "answer", "join", "leaderboard", "podium"}     # its page records' kinds
USES_ADDIN = True
UNSCORED_TYPES = {"poll", "open", "sketch"}
GIVES_AWAY = ("reveal", "leaderboard", "answer")                 # phases that show the answer


class QuizError(ValueError):
    """A deck's quizzes cannot be built (the message says why)."""


def number(text: str):
    """'' -> None, '6' -> 6, '0.5' -> 0.5"""
    if text == "":
        return None
    value = float(text)
    return int(value) if value.is_integer() else value


def scored(q: Question) -> bool:
    if q.points == "none" or q.type in UNSCORED_TYPES:
        return False
    return not (q.type == "numeric" and q.numeric.get("answer", "") == "")


def letter(position: int) -> str:
    return chr(ord("A") + position - 1)


def public_ids(q: Question) -> dict[str, str]:
    """Rectangle/asset key of every answer item ('choice-<id>', 'step-<n>') -> its public id,
    the letter of its position on the question slide."""
    if q.type == "order":
        keys = [f"step-{n}" for n in range(1, len(q.steps) + 1)]
    else:
        keys = [f"choice-{c.id}" for c in q.choices]
    return {keys[authored - 1]: letter(pos) for pos, authored in enumerate(q.order, 1)}


def plan(tqz: Tqz, pages: list[int], warnings: list[str]) -> list[tuple[int, Item | None, bool]]:
    """The deck's slides as (picture page, its quiz item, added): one per slide page, plus a
    leaderboard slide (added: no notes of its own) after the reveal of every scored quiz that
    has leaderboard=true - after its reveal slide, or (reveal=none) after the last page of its
    answer frame - unless the deck has its own leaderboard frame there."""
    items = {p: next((i for i in tqz.pages[p].items if i.kind in KINDS), None) if p in tqz.pages else None
             for p in pages}
    if tqz.questions and not any(i is not None and i.kind == "join" for i in items.values()):
        warnings.append("no \\quizjoinframe: the deck has no slide that shows how to join")
    answers: dict[str, list[int]] = {}
    for page, item in items.items():
        if item is not None and item.kind == "answer":
            if item.id not in tqz.questions:
                raise QuizError(f"page {page}: the frame option answer={item.id} names no quiz of this deck")
            answers.setdefault(item.id, []).append(page)
    anchors: dict[int, str] = {}             # page -> quiz whose leaderboard follows it
    for q in tqz.questions.values():
        question = next(p for p, i in items.items() if i is not None and i.kind == "quiz" and i.id == q.id
                        and i.phase == "question")
        if q.reveal == "none" and q.id not in answers:
            warnings.append(f"quiz {q.id} has reveal=none, but no frame has answer={q.id}: "
                            f"the class never sees whether it was right")
        if not (scored(q) and q.leaderboard):
            continue
        if q.reveal == "slide":
            anchor = next(p for p, i in items.items() if i is not None and i.id == q.id and i.phase == "reveal")
        else:
            anchor = max(answers.get(q.id, [question]))
        anchors[anchor] = q.id
    slides: list[tuple[int, Item | None, bool]] = []
    for page in pages:
        slides.append((page, items[page], False))
        quiz = anchors.get(page)
        nxt = items.get(page + 1)
        if quiz and not (nxt is not None and nxt.kind == "leaderboard"):
            slides.append((page, Item("leaderboard", quiz, "leaderboard"), True))
    return slides


def box(tqz: Tqz, item: Item) -> dict:
    """The live box of a slide with this quiz item: {type, phase, item?, rects?}."""
    entry: dict = {"type": NAME, "phase": item.phase}
    if item.id:
        entry["item"] = item.id
    q = tqz.questions.get(item.id)
    rects = public_rects(item.rects, public_ids(q) if q else {}, tqz.paper)
    if rects:
        entry["rects"] = rects
    return entry


def entries(tqz: Tqz, phone: dict[str, dict]) -> tuple[dict, dict]:
    """deck.json's and keys.json's items.quiz: {quiz id: public}, {quiz id: private}."""
    public, private = {}, {}
    for q in tqz.questions.values():
        public[q.id], private[q.id] = quiz_entries(q, phone.get(q.id, {}))
    return public, private


def quiz_entries(q: Question, assets: dict[str, dict]) -> tuple[dict, dict]:
    """(public, private) description of a quiz. `assets` maps asset keys to image entries."""
    ids = public_ids(q)
    public = {"type": q.type, "title": q.title, "time": q.time, "points": q.points,
              "scored": scored(q), "leaderboard": q.leaderboard, "reveal": q.reveal,
              "prompt": assets.get("prompt")}
    private: dict = {"prompt": q.prompt}
    if q.type == "poll":
        public["select"] = q.select or "single"
    if q.type == "order" or q.choices:
        by_id = {v: k for k, v in ids.items()}            # public id -> asset key
        items = []
        for pos, shape in enumerate(q.shapes, 1):
            pid = letter(pos)
            items.append({"id": pid, "shape": shape, **(assets.get(by_id[pid]) or {})})
        public["answers"] = items
    if q.choices:
        private["answers"] = dict(sorted((ids[f"choice-{c.id}"], {"id": c.id, "source": c.source})
                                         for c in q.choices))
        if q.type != "poll":
            private["correct"] = sorted(ids[f"choice-{c.id}"] for c in q.choices if c.correct)
    if q.type == "order":
        private["answers"] = dict(sorted((ids[f"step-{n}"], {"source": s}) for n, s in enumerate(q.steps, 1)))
        private["order"] = [ids[f"step-{n}"] for n in range(1, len(q.steps) + 1)]
    if q.type in ("multiple", "order"):
        private["partial"] = q.partial
    if q.type == "numeric":
        n = q.numeric
        public["numeric"] = {k: number(n.get(k, "")) for k in ("min", "max", "step")}
        public["numeric"]["unit"] = n.get("unit", "")
        private["answer"] = number(n.get("answer", ""))
        private["tolerance"] = number(n.get("tolerance", "")) or 0
    if q.type == "text":
        private["accept"] = q.accept
    if q.type == "open":
        public["open"] = {"display": q.open.get("display", "wordcloud"),
                          "max_chars": int(q.open.get("max_chars") or 80)}
    if q.explanation is not None:
        private["explanation"] = q.explanation
    return public, private


def files(tqz: Tqz, images: list[tuple[bytes, float, float]]) -> tuple[dict, dict[str, bytes]]:
    """{quiz: {asset key: {"image", "width", "height"}}} and the files, from the phone
    images in shipping order (the X records of the .tqz)."""
    found: dict[str, dict] = {}
    out: dict[str, bytes] = {}
    for asset, (png, width, height) in zip(tqz.assets, images, strict=True):
        name = content_name("phone", png)
        out[name] = png
        found.setdefault(asset.item, {})[asset.key] = {"image": name, "width": width, "height": height}
    return found, out


def question_pages(tqz: Tqz) -> dict[str, int]:
    """Every quiz's question page."""
    return {i.id: p for p, page in tqz.pages.items() for i in page.items if i.kind == "quiz" and i.phase == "question"}


def stored(box: dict, page: int, question: dict[str, int]) -> int:
    """The page whose picture the live PPTX keeps for a slide with this box. The first time
    PowerPoint shows a live slide, it shows that picture for a moment before the slide's
    add-in has started (also while the add-in prepares the slides before the lecture). So a
    slide that gives an answer away - reveal, leaderboard, answer frame - keeps its quiz's
    question picture; the add-in draws the real one (the bundle's). Without a quiz server
    these slides show the question: present the static deck."""
    if box["phase"] in GIVES_AWAY and box.get("item") in question:
        return question[box["item"]]
    return page


def addin(box: dict) -> tuple[dict, str]:
    """The quiz's part of a live slide's add-in properties, and the object's name."""
    quiz = box.get("item")
    return {"quiz": quiz, "phase": box["phase"]}, f"texstage {box['phase']}" + (f" {quiz}" if quiz else "")


def solutions(log: str) -> bool:
    """Whether the check needs the solutions compile: the deck has quiz or answer frames."""
    return "texquiz-check: quiz" in log or "texquiz-check: answer" in log
