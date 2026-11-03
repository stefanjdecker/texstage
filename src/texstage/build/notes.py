# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Speaker notes from Beamer's "show notes on second screen" pages.

Shared by the live builder and the plain Beamer converter. A page is a pdf.Page (its
words with their boxes, points from the top left); a clip is (x0, y0, x1, y1).
"""
from __future__ import annotations

# The note page as typeset for extraction (it is never shown): small, ragged right and without
# hyphenation. Small, because text that runs below the page edge is lost to the extraction;
# no hyphenation, because then a line break inside a paragraph is always a space; and the
# \parskip gap tells the paragraphs apart (see note_paragraphs). texquiz.sty sets the same
# template when \texquiznotes is defined.
NOTE_TEMPLATE = (r"\setbeamertemplate{note page}{\tiny\raggedright\hyphenpenalty=10000"
                 r"\exhyphenpenalty=10000\setlength{\parskip}{1.2em}\insertnote\par}")


def note_paragraphs(page, clip=None) -> str:
    """The note text on (a clip of) a page, one paragraph per line of the result.

    Words are grouped into visual lines by their vertical centre (a subscript stays on its
    line), a line is read left to right, and a gap clearly larger than the line pitch - the
    \\parskip of NOTE_TEMPLATE - starts a new paragraph.
    """
    items = sorted(((w[1] + w[3]) / 2, w[0], w[4]) for w in page.words(clip))
    rows = []  # [centre of the line's first word, [(x0, word), ...]]
    for centre, x0, word in items:
        if rows and centre - rows[-1][0] < 2.5:
            rows[-1][1].append((x0, word))
        else:
            rows.append([centre, [(x0, word)]])
    if not rows:
        return ""
    texts = [" ".join(word for _, word in sorted(words)) for _, words in rows]
    gaps = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    pitch = min((g for g in gaps if g > 3), default=0.0)
    paragraphs, current = [], [texts[0]]
    for gap, text in zip(gaps, texts[1:]):
        if pitch and gap > 1.5 * pitch:
            paragraphs.append(" ".join(current))
            current = []
        current.append(text)
    paragraphs.append(" ".join(current))
    return "\n".join(paragraphs)


def note_reaches_bottom(page, clip, spare: float = 4.0) -> bool:
    """True if the note in `clip` runs down to the bottom edge: its end is cut off, or
    about to be. Measured in the PDF, because a note page that runs over does not always
    leave an Overfull warning in the log."""
    low = max((w[3] for w in page.words(clip)), default=0.0)
    return clip[3] - low < spare
