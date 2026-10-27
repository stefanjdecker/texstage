# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Images from the present-mode PDF: slide pictures with their notes, phone images.

The PDF comes from a compile with second-screen notes: every slide page holds the slide on
the left half and its note page on the right half; the phone images follow the last slide,
one page each, exactly the size of the image. Rendered by PDFium (pdf.py).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from texstage.build.notes import note_paragraphs, note_reaches_bottom
from texstage.build.pdf import Pdf

PHONE_SCALE = 3          # phone images: 3 device pixels per CSS pixel
CSS_PX_PER_PT = 96 / 72


@dataclass
class SlideImage:
    page: int            # 1-based PDF page
    png: bytes
    notes: str
    notes_cut_off: bool  # the note reaches the bottom of its page


def render_slides(pdf: Path, count: int, slide_size: tuple[float, float], height: int) -> list[SlideImage]:
    """The first `count` pages: the slide half as PNG of `height` pixels, the notes as text."""
    width_pt, height_pt = slide_size
    zoom = height / height_pt
    slides = []
    with Pdf(pdf) as doc:
        for i in range(count):
            page = doc[i]
            if abs(page.width - 2 * width_pt) > 1:
                raise ValueError(f"page {i + 1} is {page.width:.0f}pt wide, expected slide and "
                                 f"notes side by side ({2 * width_pt:.0f}pt)")
            slide = (0, 0, width_pt, height_pt)
            note = (width_pt, 0, 2 * width_pt, height_pt)
            buf = io.BytesIO()
            page.render(zoom, clip=slide).save(buf, "PNG")
            slides.append(SlideImage(i + 1, buf.getvalue(), note_paragraphs(page, note),
                                     note_reaches_bottom(page, note)))
    return slides


def render_pages(pdf: Path, pages: range) -> list[tuple[bytes, float, float]]:
    """Phone images: the pages with a transparent background, cropped to what is drawn (a
    short answer is typeset in a box as wide as a long one), as (png, width, height), the
    size in CSS pixels."""
    zoom = PHONE_SCALE * CSS_PX_PER_PT
    pad = 2 * PHONE_SCALE
    out = []
    with Pdf(pdf) as doc:
        for i in pages:
            im = doc[i - 1].render(zoom, alpha=True)
            box = im.getchannel("A").getbbox()
            if box:
                im = im.crop((max(0, box[0] - pad), max(0, box[1] - pad),
                              min(im.width, box[2] + pad), min(im.height, box[3] + pad)))
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
            out.append((buf.getvalue(), round(im.width / PHONE_SCALE, 1), round(im.height / PHONE_SCALE, 1)))
    return out
