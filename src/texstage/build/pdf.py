# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""PDF pages for the build, with pypdfium2 (Apache-2.0/BSD-3-Clause; PDFium, the PDF engine of
Chrome): a PDF's pages, their size, a page or a part of it rendered as an image, and the
words on a page with their boxes. PyMuPDF did this before texstage M7; its AGPL does not go
with texstage's Apache-2.0 (docs/texstage-design.md, sections 12 and 22).

    with Pdf(path) as pdf:
        page = pdf[0]                                  # also len(pdf), iteration
        page.width, page.height, page.rect             # points
        page.render(scale, clip=(x0, y0, x1, y1))      # a PIL image; alpha=True: transparent
        page.words(clip)                               # [(x0, y0, x1, y1, word), ...]
        page.text(), page.text(clip)

Coordinates are points measured from the top left corner (y downwards) - the convention the
build has always used; PDFium measures from the bottom left. An image is the size the scale
gives, rounded (pypdfium2's own helper rounds up, which turns 1080 pixels into 1081), and the
page is drawn at exactly that scale through a matrix: drawn into a whole number of pixels
instead, a page and the half of a page twice as wide come out scaled a little differently.
"""
from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image

# typeset ligatures as letters, as text extraction always gave them
LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
                           "ﬅ": "st", "ﬆ": "st"})


class Pdf:
    def __init__(self, path: Path | str | bytes):
        self.doc = pdfium.PdfDocument(path if isinstance(path, bytes) else str(path))

    def __len__(self) -> int:
        return len(self.doc)

    def __getitem__(self, index: int) -> Page:
        if not -len(self) <= index < len(self):
            raise IndexError(f"page {index} of {len(self)}")
        return Page(self.doc[index % len(self)])

    def __iter__(self):
        return (self[i] for i in range(len(self)))

    def close(self):
        self.doc.close()

    def __enter__(self) -> Pdf:
        return self

    def __exit__(self, *exc):
        self.close()


class Page:
    def __init__(self, page):
        self.page = page
        self.width, self.height = page.get_size()
        left, bottom, _, _ = page.get_mediabox()
        self.origin = (left, bottom)

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, self.width, self.height)

    def render(self, scale: float, clip: tuple[float, float, float, float] | None = None,
               alpha: bool = False) -> Image.Image:
        """The page - or the part `clip` of it - at `scale` pixels per point: RGB on white, or
        RGBA on a transparent background."""
        x0, y0, x1, y1 = clip or self.rect
        width, height = round((x1 - x0) * scale), round((y1 - y0) * scale)
        if width < 1 or height < 1:
            raise ValueError("nothing to render")
        bitmap = pdfium.PdfBitmap.new_native(width, height, pdfium_c.FPDFBitmap_BGRA if alpha else pdfium_c.FPDFBitmap_BGR)
        bitmap.fill_rect((255, 255, 255, 0 if alpha else 255), 0, 0, width, height)
        matrix = pdfium_c.FS_MATRIX(scale, 0, 0, scale, -x0 * scale, -y0 * scale)
        pdfium_c.FPDF_RenderPageBitmapWithMatrix(bitmap, self.page, matrix, pdfium_c.FS_RECTF(0, 0, width, height),
                                                 pdfium_c.FPDF_ANNOT)
        return bitmap.to_pil()

    def words(self, clip: tuple[float, float, float, float] | None = None) -> list[tuple[float, float, float, float, str]]:
        """The words (or the words in `clip`) in reading order: (x0, y0, x1, y1, text), the box
        the font's ascent and descent give - one height for a line, as PDF readers mark text.
        PDFium knows characters, not words: a word is a run of characters up to a space or a
        line break (PDFium adds both where the gaps are)."""
        textpage = self.page.get_textpage()
        out: list[tuple[float, float, float, float, str]] = []
        word: list = []                         # [x0, y0, x1, y1, text]

        def done():
            if word:
                out.append((word[0], word[1], word[2], word[3], word[4].translate(LIGATURES)))
                word.clear()
        try:
            left, bottom = self.origin
            for i in range(textpage.count_chars()):
                code = pdfium_c.FPDFText_GetUnicode(textpage, i)
                ch = chr(code) if code else ""
                if not ch or ch.isspace():
                    done()
                    continue
                l, b, r, t = textpage.get_charbox(i, loose=True)
                box = (l - left, self.height - (t - bottom), r - left, self.height - (b - bottom))
                if clip is not None:
                    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                    if not (clip[0] <= cx <= clip[2] and clip[1] <= cy <= clip[3]):
                        done()
                        continue
                if word and abs((box[1] + box[3]) / 2 - (word[1] + word[3]) / 2) > (box[3] - box[1]) / 2:
                    done()                      # another line without a line break between
                if word:
                    word[:] = [min(word[0], box[0]), min(word[1], box[1]), max(word[2], box[2]),
                               max(word[3], box[3]), word[4] + ch]
                else:
                    word.extend([*box, ch])
            done()
        finally:
            textpage.close()
        return out

    def text(self, clip: tuple[float, float, float, float] | None = None) -> str:
        """The page's text, its lines as PDFium reads them - or the words in `clip`, by spaces."""
        if clip is not None:
            return " ".join(w[4] for w in self.words(clip))
        textpage = self.page.get_textpage()
        try:
            return textpage.get_text_range().replace("\r\n", "\n").translate(LIGATURES)
        finally:
            textpage.close()
