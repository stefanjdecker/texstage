# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The stage PDF for texstage, the browser presenter (docs/texstage-design.md, section 3).

texstage build (unless --no-stage) compiles the present deck a second time, alongside the
first, with the deck's own note pages (\\def\\texquiznotes{stage}): every slide is a page of
its own, followed by its note page if its frame has a note - not on a second screen, so the slide
pages carry no note text and go into the students' annotated PDF as they are. The note
pages are numbered on like any page; texquiz.sty marks each one in the log
("texquiz-check: note" before its page mark). This module pairs the slides with their
note pages, checks the pairing against the present compile, and numbers every slide's
frame and overlay step (from the present compile's .nav).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from texstage.build import bundle as bnd
from texstage.build.check import frame_ranges, page_logs
from texstage.build.notes import note_reaches_bottom
from texstage.build.pdf import Pdf
from texstage.build.tqz import Tqz


class StageError(RuntimeError):
    """The stage compile does not match the present compile (the message says how)."""


@dataclass
class StagePage:
    page: int                    # the slide's page in the stage PDF
    note: int | None = None      # its note page there; None: its frame has no note


@dataclass
class Stage:
    pdf: Path                    # the stage PDF in the build folder
    file: str                    # its name in the bundle: stage/<content hash>.pdf
    pages: list[StagePage]       # per page of the present compile (index page - 1)
    steps: dict[int, tuple[int, int]]   # page of the present compile -> (frame, step)
    paper: tuple[float, float]   # page size in PDF points
    cut_off: list[int] = field(default_factory=list)   # present pages whose note page is full

    def entry(self, page: int, notes: str) -> dict:
        """The stage fields of a deck.json slide shown from page `page` of the present
        compile (a leaderboard slide: its anchor's page)."""
        p = self.pages[page - 1]
        frame, step = self.steps.get(page, (page, 1))
        out: dict = {"frame": frame, "step": step, "page": p.page}
        if p.note is not None:
            out["note"] = p.note
        if notes:
            out["notes"] = notes
        return out

    def deck_entry(self) -> dict:
        return {"file": self.file, "width": round(self.paper[0], 3), "height": round(self.paper[1], 3)}


def pair_pages(log: Path) -> list[StagePage]:
    """The slides of a stage compile in order, each with its note page."""
    slides: list[StagePage] = []
    for p in page_logs(log.read_text(encoding="latin-1", errors="replace")):
        if ("note", "") in p.marks:
            if not slides or slides[-1].note is not None:
                raise StageError(f"page {p.page} of the stage PDF is a note page without its slide")
            slides[-1].note = p.page
        else:
            slides.append(StagePage(p.page))
    return slides


def frames_and_steps(nav: Path) -> dict[int, tuple[int, int]]:
    """Page -> (frame, overlay step), both 1-based, from Beamer's frame page ranges. A frame
    broken by allowframebreaks shows up as overlapping ranges ({6}{6}, then {6}{7}): every
    break page counts as a frame of its own, as Beamer numbers them."""
    out: dict[int, tuple[int, int]] = {}
    done = 0
    for frame, (first, last) in enumerate(frame_ranges(nav), 1):
        first = max(first, done + 1)
        for page in range(first, last + 1):
            out[page] = (frame, page - first + 1)
        done = max(done, last)
    return out


def plan_stage(staged, present_nav: Path, tqz: Tqz, count: int) -> tuple[Stage, bytes]:
    """The stage PDF of a stage compile (latex.CompileResult) and its bytes for the bundle.
    `count`: the slide pages of the present compile, whose live pages (`tqz`) the stage
    compile must show on the same slides."""
    pages = pair_pages(staged.log)
    if len(pages) != count:
        raise StageError(f"the stage compile has {len(pages)} slide pages, the present compile {count} - "
                         f"does the deck's note page template show \\insertnote?")
    def items(page):
        return [(i.kind, i.id, i.phase) for i in page.items]
    live = {n: items(page) for n, page in tqz.pages.items()}
    staged_live = {n: items(page) for n, page in Tqz.read(staged.tqz).pages.items()}
    if {pages[n - 1].page: v for n, v in live.items()} != staged_live:
        raise StageError("the live slides of the stage compile are not those of the present compile")
    with Pdf(staged.pdf) as doc:
        if len(doc) != count + sum(p.note is not None for p in pages):
            raise StageError(f"{staged.pdf.name}: {len(doc)} pages, but the log marks "
                             f"{count} slides and their note pages")
        cut_off = [n for n, p in enumerate(pages, 1)
                   if p.note is not None and note_reaches_bottom(doc[p.note - 1], doc[p.note - 1].rect)]
    data = staged.pdf.read_bytes()
    stage = Stage(staged.pdf, bnd.content_name("stage", data, ".pdf"), pages, frames_and_steps(present_nav),
                  tqz.paper, cut_off)
    return stage, data
