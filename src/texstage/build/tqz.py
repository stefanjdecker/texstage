# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Reader for the .tqz file the present compile writes (texstage.sty, and the content
types' packages on it: texquiz.sty).

One record per line, fields separated by "|", free text hex-encoded (UTF-8).
Positions come from \\pdfsavepos in scaled points, measured from the lower-left
corner of the (physical) PDF page; they are converted to PDF points here.

The core's (texstage.sty):
  D|version|paperwidth|paperheight|language
                                          (the deck's language: babel's main one, \\languagename
                                           - ngerman, english; none before 2026-10-24)
  G|kind|id|phase|page                    (an item on a page; several per page. The kind names
                                           the content type - the quiz's: quiz/answer/join/
                                           podium/leaderboard; build/types.py)
  R|id|phase|key|x|y|w|h|page             (a rectangle of item id, lower-left corner)
  V|id|phase|key|x|y|w|page               (horizontal mark; live-top/live-bottom pairs)
  X|id|key|w|h                            (an extra page of item id, in shipping order)
  K|page|factor|height   Z|x|y|page       (a shrunk frame: Beamer's scale factor, the height
                                           of the frame body and the top left corner of it)
The quiz's (texquiz.sty), by letter:
  Q|id|type|time|points|leaderboard|shuffle|select|partial|cols|title|file|line|reveal
  P|id|prompt            C|id|index|choice-id|correct|source
  S|id|index|source      L|id|display order|shapes      A|id|accepted text
  E|id|explanation       N|id|answer|tolerance|min|max|step|unit
  O|id|display|max-chars
Every other type's start with its name (video|...): the reader keeps them for it, by name.

Beamer shrinks a frame by scaling the finished body with a PDF transformation, which
\\pdfsavepos does not see. The point the scaling keeps in place is the body's reference
point, its bottom left corner as recorded: c = (Z.x, Z.y - height). The rectangles of
such a page are mapped here: p' = c + factor * (p - c).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SP_PER_BP = 65536 * 72.27 / 72  # TeX scaled points per PDF point


def _bp(sp: str) -> float:
    return int(sp) / SP_PER_BP


def _hex(s: str) -> str:
    return bytes.fromhex(s).decode("utf-8") if s else ""


@dataclass
class Rect:
    """Rectangle in PDF points; (x, y) is the lower-left corner, y measured up."""
    x: float
    y: float
    w: float
    h: float

    def top_down(self, page_height: float) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1) with y measured from the top, as the build's PDF pages use it (pdf.py)."""
        return (self.x, page_height - self.y - self.h, self.x + self.w, page_height - self.y)


@dataclass
class Choice:
    index: int          # authored position, 1-based
    id: str
    correct: bool
    source: str         # detokenized LaTeX


@dataclass
class Question:
    id: str
    type: str
    time: int
    points: str
    leaderboard: bool
    shuffle: bool
    select: str
    partial: bool
    cols: int
    title: str
    file: str
    line: int
    reveal: str = "slide"   # slide | none (revealed on a frame with answer=<id>)
    prompt: str = ""
    choices: list[Choice] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    order: list[int] = field(default_factory=list)    # display position -> authored index
    shapes: list[int] = field(default_factory=list)   # display position -> shape 1..6
    accept: list[str] = field(default_factory=list)
    explanation: str | None = None
    numeric: dict[str, str] = field(default_factory=dict)
    open: dict[str, str] = field(default_factory=dict)


@dataclass
class Item:
    """An item of a content type on a page (a G record) - a quiz in one of its phases, a
    join frame, a video - with its rectangles."""
    kind: str           # the quiz's: quiz | answer | leaderboard | join | podium; else a type's name
    id: str             # the item's id ('' for join/leaderboard/podium)
    phase: str          # the quiz's: read | question | reveal | answer | leaderboard | join | podium
    rects: dict[str, Rect] = field(default_factory=dict)


@dataclass
class Page:
    page: int           # 1-based physical PDF page
    items: list[Item] = field(default_factory=list)

    # The page's first item - all a quiz page has (texquiz puts one on a page)
    @property
    def kind(self) -> str:
        return self.items[0].kind

    @property
    def quiz(self) -> str:
        return self.items[0].id

    @property
    def phase(self) -> str:
        return self.items[0].phase

    @property
    def rects(self) -> dict[str, Rect]:
        return self.items[0].rects

    def item(self, id: str) -> Item | None:
        """The item of this id - else the page's first (a rectangle of a page's only item)."""
        return next((i for i in self.items if i.id == id), self.items[0] if self.items else None)


@dataclass
class Asset:
    item: str           # the item the extra page belongs to (a quiz's id)
    key: str            # the quiz's: prompt | choice-<id> | step-<n>
    w: float
    h: float


@dataclass
class Tqz:
    version: str
    paper: tuple[float, float]
    questions: dict[str, Question]
    pages: dict[int, Page]
    assets: list[Asset]
    records: dict[str, list[list[str]]] = field(default_factory=dict)   # a type's own, by its name
    language: str = ""          # the deck's, as babel names it (ngerman); '' from an older texstage.sty

    @classmethod
    def read(cls, path: Path) -> "Tqz":
        version, paper, language = "", (0.0, 0.0), ""
        questions: dict[str, Question] = {}
        pages: dict[int, Page] = {}
        marks: dict[tuple[int, str, str], dict[str, tuple[float, float, float]]] = {}
        assets: list[Asset] = []
        records: dict[str, list[list[str]]] = {}
        factors: dict[int, float] = {}
        corners: dict[int, tuple[float, float]] = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw:
                continue
            f = raw.split("|")
            kind = f[0]
            if len(kind) > 1 and kind.isidentifier():
                records.setdefault(kind, []).append(f[1:])          # video|..., cell|...
            elif kind == "D":
                version, paper = f[1], (_bp(f[2]), _bp(f[3]))
                language = f[4] if len(f) > 4 else ""
            elif kind == "Q":
                questions[f[1]] = Question(
                    id=f[1], type=f[2], time=int(f[3]), points=f[4], leaderboard=f[5] == "true",
                    shuffle=f[6] == "true", select=f[7], partial=f[8] == "true", cols=int(f[9]),
                    title=_hex(f[10]), file=_hex(f[11]), line=int(f[12]), reveal=f[13])
            elif kind == "P":
                questions[f[1]].prompt = _hex(f[2])
            elif kind == "C":
                questions[f[1]].choices.append(Choice(int(f[2]), f[3], f[4] == "1", _hex(f[5])))
            elif kind == "S":
                questions[f[1]].steps.append(_hex(f[3]))
            elif kind == "L":
                q = questions[f[1]]
                q.order = [int(x) for x in f[2].split(",") if x]
                q.shapes = [int(x) for x in f[3].split(",") if x]
            elif kind == "A":
                questions[f[1]].accept.append(_hex(f[2]))
            elif kind == "E":
                questions[f[1]].explanation = _hex(f[2])
            elif kind == "N":
                questions[f[1]].numeric = dict(zip(("answer", "tolerance", "min", "max", "step"), f[2:7]))
                questions[f[1]].numeric["unit"] = _hex(f[7])
            elif kind == "O":
                questions[f[1]].open = {"display": f[2], "max_chars": f[3]}
            elif kind == "G":
                page = int(f[4])
                pages.setdefault(page, Page(page)).items.append(Item(f[1], f[2], f[3]))
            elif kind == "R":
                item = _item(pages, int(f[8]), f[1], raw, path)
                item.rects[f[3]] = Rect(_bp(f[4]), _bp(f[5]), _bp(f[6]), _bp(f[7]))
            elif kind == "V":
                page = int(f[7])
                area, _, edge = f[3].rpartition("-")
                marks.setdefault((page, f[1], area), {})[edge] = (_bp(f[4]), _bp(f[5]), _bp(f[6]))
            elif kind == "X":
                assets.append(Asset(f[1], f[2], _bp(f[3]), _bp(f[4])))
            elif kind == "K":
                factors[int(f[1])] = (float(f[2]), _bp(f[3]))
            elif kind == "Z":
                corners[int(f[3])] = (_bp(f[1]), _bp(f[2]))
            else:
                raise ValueError(f"{path}: unknown record {raw[:40]!r}")
        for (page, id, area), m in marks.items():
            (x, top, w), (_, bottom, _) = m["top"], m["bottom"]
            _item(pages, page, id, f"V|{id}|{area}", path).rects[area] = Rect(x, bottom, w, top - bottom)
        for page, (s, height) in factors.items():
            if page in pages and page in corners:
                cx, cy = corners[page][0], corners[page][1] - height
                for item in pages[page].items:
                    item.rects = {k: Rect(cx + s * (r.x - cx), cy + s * (r.y - cy), s * r.w, s * r.h)
                                  for k, r in item.rects.items()}
        return cls(version, paper, questions, pages, assets, records, language)


def _item(pages: dict[int, Page], page: int, id: str, raw: str, path: Path) -> Item:
    """The item a rectangle or mark of `id` on `page` belongs to."""
    item = pages[page].item(id) if page in pages else None
    if item is None:
        raise ValueError(f"{path}: {raw[:40]!r} on page {page}, which has no item")
    return item
