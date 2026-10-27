# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Layout check of quiz and answer frames in the builds that show them.

A normal compile (the course's build-chapter.py, check-labels.py) only ever sees the
handout, where quiz and answer frames are placeholder pages; how they really look - the
question with its answer boxes below the author's material, the answer frame as written -
appears only in the present and solutions builds. In those, texquiz.sty marks the log:

    texquiz-check: quiz <id>        while a quiz frame's page is typeset
    texquiz-check: answer <id>      the same for an answer frame (id may be empty)
    texquiz-check: page <n>         after every shipped page

so every Overfull box and every "Frame text is shrunk" warning can be attributed to its
page. With second-screen notes the note page of slide n is shipped after it as a page of
its own, also numbered n; its warnings (a long note) are not the slide's and are skipped.
Pages map to frames through the .nav file, and frames to NNN.tex through the markers
combine-slides.py writes into a course deck.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MARK = re.compile(r"texquiz-check: (\w+) ?(\S*)")
OVERFULL = re.compile(r"Overfull \\([hv])box \(([\d.]+)pt too (wide|high)\)")
# "Class beamer Warning: Frame text is shrunk by a factor of 28.52 percent instead of 9 percent"
SHRINK = re.compile(r"shrunk by a factor of\s*([\d.]+)\s*percent")
FRAMEPAGES = re.compile(r"\\beamer@framepages\s*\{(\d+)\}\{(\d+)\}")
FRAME_FILE = re.compile(r"^%%% --- Start of (\S+\.tex) --- %%%$", re.M)

VBOX_LIMIT = 1.0     # pt: content pushed down into the footline (the pilot's case)
HBOX_LIMIT = 5.0     # pt: as build-chapter.py, smaller ones are only listed


@dataclass
class PageLog:
    page: int
    marks: list[tuple[str, str]] = field(default_factory=list)   # (kind, quiz id)
    overfull: list[tuple[str, float]] = field(default_factory=list)  # ('h'|'v', pt)
    shrink: float | None = None


@dataclass
class Finding:
    where: str           # "032.tex" or "frame 7 (page 9)"
    what: str            # "quiz cities-two-rivers" / "answer frame"
    build: str           # present | solutions | notes
    message: str
    problem: bool        # fails the check (else only listed)

    def __str__(self) -> str:
        return f"{self.where} ({self.what}, {self.build} build): {self.message}"


def page_logs(log: str) -> list[PageLog]:
    """The log cut into slide pages at the 'texquiz-check: page <n>' marks; a note page
    (the same number again) is dropped."""
    pages, current = [], PageLog(0)
    for line in log.splitlines():
        m = MARK.search(line)
        if m:
            if m.group(1) == "page":
                number = int(m.group(2))
                if not pages or pages[-1].page != number:
                    current.page = number
                    pages.append(current)
                current = PageLog(0)
            else:
                current.marks.append((m.group(1), m.group(2)))
            continue
        m = OVERFULL.search(line)
        if m:
            current.overfull.append((m.group(1), float(m.group(2))))
        m = SHRINK.search(line)
        if m:
            current.shrink = max(current.shrink or 0.0, float(m.group(1)))
    return pages


def frame_ranges(nav: Path) -> list[tuple[int, int]]:
    if not nav.exists():
        return []
    return [(int(a), int(b)) for a, b in FRAMEPAGES.findall(nav.read_text(encoding="latin-1"))]


def frame_files(tex: Path) -> list[str]:
    """NNN.tex of every frame of a deck made by combine-slides.py, in order."""
    return FRAME_FILE.findall(tex.read_text(encoding="utf-8", errors="replace"))


def locator(tex: Path, nav: Path):
    """page -> "032.tex" when the deck is one frame per file, else "frame F (page P)"."""
    ranges = frame_ranges(nav)
    files = frame_files(tex)
    use_files = bool(files) and len(files) == len(ranges)

    def where(page: int) -> str:
        frame = next((i for i, (a, b) in enumerate(ranges, 1) if a <= page <= b), None)
        if frame is None:
            return f"page {page}"
        return files[frame - 1] if use_files else f"frame {frame} (page {page})"
    return where


def check_log(log: Path, build: str, where, max_shrink: float) -> list[Finding]:
    """Findings on the marked pages of one compile."""
    findings = []
    text = log.read_text(encoding="latin-1", errors="replace")
    seen = set()       # a quiz frame is three pages in present mode: report a message once
    for p in page_logs(text):
        if not p.marks:
            continue
        kind, quiz = p.marks[0]
        what = f"quiz {quiz}" if kind == "quiz" else ("answer frame" + (f" of {quiz}" if quiz else ""))
        messages = []
        for box, pt in p.overfull:
            if box == "v":
                messages.append((f"overfull {pt:.1f}pt too high - the content runs into the "
                                 f"footline; shrink the frame or shorten the material", pt >= VBOX_LIMIT))
            else:
                messages.append((f"overfull {pt:.1f}pt too wide", pt >= HBOX_LIMIT))
        if p.shrink is not None and p.shrink >= max_shrink:
            messages.append((f"shrunk by {p.shrink:.0f}% - too much content, text is tiny", True))
        for message, problem in messages:
            key = (where(p.page), what, message)
            if key not in seen:
                seen.add(key)
                findings.append(Finding(where(p.page), what, build, message, problem))
    return findings


def shipped_pages(log: Path) -> int:
    """How many slide pages the log marks (consistency check against the PDF)."""
    return len(page_logs(log.read_text(encoding="latin-1", errors="replace")))
