// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The annotated PDF for the students (docs/texstage-design.md, section 11): for every frame the
// slide page of its last step - everything it shows -, copied from the stage PDF (its note pages
// stay behind), with the frame's ink drawn over it as vector paths, and the whiteboard pages
// where they came. Made in the presenter window with pdf-lib, so it works the same on the laptop
// and on a hosted server; the presenter window downloads it and keeps it in the lecture archive.
//
//   const bytes = await annotatedPdf(stagePdf, deck, boards, frames);   // frames: {key: [strokes]}

import { PDFDocument, rgb } from "/static/vendor/pdf-lib/pdf-lib.esm.min.js";
import { HIGHLIGHT, strokeSvg } from "/static/stage/ink.js";
import { inkKey, sequence } from "/static/stage/pdfview.js";

const GRID = rgb(0.85, 0.88, 0.93);

export async function annotatedPdf(stagePdf, deck, boards, frames) {
  const src = await PDFDocument.load(stagePdf);
  const out = await PDFDocument.create();
  const { width, height } = deck.pdf;
  const aspect = width / height;
  // per frame its last step, per whiteboard page the page itself, in the order presented
  const items = sequence(deck, boards);
  const pages = items.filter((it, i) => it.board || !items[i + 1] || items[i + 1].board || items[i + 1].frame !== it.frame);
  const copied = await out.copyPages(src, pages.filter((it) => !it.board).map((it) => it.page - 1));   // one go: fonts once
  let next = 0;
  for (const it of pages) {
    let page;
    if (it.board) {
      page = out.addPage([width, height]);
      if (it.kind === "grid") grid(page, width, height);
    } else {
      page = out.addPage(copied[next]);
      next += 1;
    }
    const strokes = frames[inkKey(it)] || [];
    for (const tool of ["highlighter", "pen"]) {          // highlighting under the writing
      for (const s of strokes) {
        if (s.tool !== tool) continue;
        const path = strokeSvg({ ...s, live: false }, aspect);
        if (!path) continue;
        // the path is in slide heights, y down: from the top left corner, one slide height a unit
        page.drawSvgPath(path, { x: 0, y: height, scale: height, color: colour(s.color),
          opacity: tool === "highlighter" ? HIGHLIGHT : 1, borderWidth: 0 });
      }
    }
  }
  out.setTitle(`${deck.name} - with the lecture's ink`);
  out.setCreator("texstage");
  out.setProducer("texstage (pdf-lib)");
  return out.save();
}

function colour(hex) {
  const n = (i) => parseInt(hex.slice(i, i + 2), 16) / 255;
  return rgb(n(1), n(3), n(5));
}

function grid(page, w, h) {
  // the whiteboard's squares: 1/20 of the page's height, as on the screen
  const step = h / 20;
  for (let y = 0; y <= h + 0.01; y += step) page.drawLine({ start: { x: 0, y }, end: { x: w, y }, thickness: 0.4, color: GRID });
  for (let x = 0; x <= w + 0.01; x += step) page.drawLine({ start: { x, y: 0 }, end: { x, y: h }, thickness: 0.4, color: GRID });
}
