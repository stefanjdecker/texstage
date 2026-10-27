// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// PDF.js for texstage (docs/texstage-design.md, section 4): the stage PDF of a --stage build,
// fetched once with the presenter key; its pages rendered at the size they are shown at, in
// device pixels, and kept in a cache, so stepping on shows a page that is ready.
//
//   const pdf = await PdfDeck.open(bundle, auth);         // the presenter key, or {device}
//   const surface = new PdfSurface(pdf);                   // a Stage's surface (live.js)
//   const notes = new PdfSurface(pdf, {pageOf: (slide) => slide?.note, className: "pdfpage"});
//   pdf.prefetch([[page, width, height], ...]);           // drawn when nothing else is
//   fit(box, aspect);                                      // the largest box of that ratio
//   linkable(box, {pdf, page, at, active});                // the page's web links, clickable

import * as pdfjs from "/static/vendor/pdfjs/pdf.min.mjs";
import { authHeaders } from "/static/shared/client.js";

pdfjs.GlobalWorkerOptions.workerSrc = "/static/vendor/pdfjs/pdf.worker.min.mjs";

const TABLET = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
const BUDGET = TABLET ? 20e6 : 48e6;   // rendered pixels kept (a 4K page is 8.3 million; a tablet has less memory)

export class PdfDeck {
  static async open(bundle, auth) {
    const r = await fetch(`/api/deck/${bundle}/pdf`, { headers: authHeaders(auth) });
    if (!r.ok) {
      throw new Error(r.status === 404 ? "This build has no stage PDF: build the deck again (texstage build, without --no-stage)."
        : `${r.status} ${await r.text()}`);
    }
    const data = new Uint8Array(await r.arrayBuffer());
    return new PdfDeck(await pdfjs.getDocument({ data, isEvalSupported: false }).promise);
  }

  constructor(doc) {
    this.doc = doc;
    this.pages = new Map();       // page number -> Promise of the PDFPageProxy
    this.done = new Map();        // "n@WxH" -> canvas, the most recently used last
    this.pixels = 0;
    this.running = new Map();     // "n@WxH" -> Promise of the canvas
    this.queue = [];              // prefetch jobs: [n, w, h]
    this.pumping = false;
    this.linkJobs = new Map();    // page number -> Promise of its links
    this.linkLists = new Map();   // page number -> its links, once read
  }

  page(n) {
    if (!this.pages.has(n)) this.pages.set(n, this.doc.getPage(n));
    return this.pages.get(n);
  }

  // the web links of page n (\href, \url): [{url, x, y, w, h}], fractions of the page from its
  // top left - read once from the page's annotations; links within the PDF are left out
  links(n) {
    if (!this.linkJobs.has(n)) {
      const job = (async () => {
        const page = await this.page(n);
        const [x0, y0, x1, y1] = page.view;
        const pw = x1 - x0;
        const ph = y1 - y0;
        const out = [];
        for (const a of await page.getAnnotations({ intent: "display" })) {
          if (a.subtype !== "Link" || !/^https?:\/\//i.test(a.url || "") || !a.rect) continue;
          const [ax0, ax1] = [Math.min(a.rect[0], a.rect[2]), Math.max(a.rect[0], a.rect[2])];
          const [ay0, ay1] = [Math.min(a.rect[1], a.rect[3]), Math.max(a.rect[1], a.rect[3])];
          out.push({ url: a.url, x: (ax0 - x0) / pw, y: (y1 - ay1) / ph, w: (ax1 - ax0) / pw, h: (ay1 - ay0) / ph });
        }
        this.linkLists.set(n, out);
        return out;
      })().catch((err) => {
        console.warn("texstage: links of page", n, err);
        return [];
      });
      this.linkJobs.set(n, job);
    }
    return this.linkJobs.get(n);
  }

  // the links of page n if read already, else none (and they are read now)
  linksNow(n) {
    if (!this.linkLists.has(n)) this.links(n);
    return this.linkLists.get(n) || [];
  }

  // page n fitted into w x h device pixels - or its part `view` ({x, y, w, h}, fractions of the
  // page: a zoom, rendered sharp) -: a canvas (shared - draw it, do not change it)
  render(n, w, h, view = null) {
    const id = `${n}@${w}x${h}${view ? `:${view.x},${view.y},${view.w},${view.h}` : ""}`;
    const done = this.done.get(id);
    if (done) {
      this.done.delete(id);
      this.done.set(id, done);
      return Promise.resolve(done);
    }
    if (!this.running.has(id)) {
      const job = (async () => {
        const page = await this.page(n);
        const base = page.getViewport({ scale: 1 });
        const v = view || { x: 0, y: 0, w: 1, h: 1 };
        const scale = Math.min(w / (base.width * v.w), h / (base.height * v.h));
        const viewport = page.getViewport({ scale, offsetX: -v.x * base.width * scale, offsetY: -v.y * base.height * scale });
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(base.width * v.w * scale));
        canvas.height = Math.max(1, Math.round(base.height * v.h * scale));
        await page.render({ canvas, viewport }).promise;
        this.keep(id, canvas);
        return canvas;
      })();
      this.running.set(id, job);
      job.finally(() => this.running.delete(id)).catch(() => {});
    }
    return this.running.get(id);
  }

  keep(id, canvas) {
    this.done.set(id, canvas);
    this.pixels += canvas.width * canvas.height;
    for (const [old, c] of this.done) {
      if (this.pixels <= BUDGET || old === id) break;
      this.done.delete(old);
      this.pixels -= c.width * c.height;
    }
  }

  // a deck no longer shown: its pages' memory, and its worker
  close() {
    this.queue = [];
    this.done.clear();
    this.pixels = 0;
    this.doc.loadingTask.destroy().catch(() => {});
  }

  // render these pages when nothing else is drawn (replaces the jobs not started yet)
  prefetch(jobs) {
    this.queue = jobs.filter(([n, w, h]) => n >= 1 && n <= this.doc.numPages && w > 1 && h > 1);
    this.pump();
  }

  async pump() {
    if (this.pumping) return;
    this.pumping = true;
    while (this.queue.length) {
      await new Promise((resolve) => setTimeout(resolve, 40));    // the page on screen goes first
      const [n, w, h] = this.queue.shift() || [];
      if (n) await this.render(n, w, h).catch(() => {});
    }
    this.pumping = false;
  }
}

// a canvas that shows one page of the PDF - or a whiteboard page ({board, kind}) -, as large as
// its box allows, in device pixels, zoomed to `view` if given
let held = false;                  // a divider of the presenter window is dragged (split.js)
const missed = new Set();          // the surfaces that wanted a new picture meanwhile

export class PdfSurface {
  // while held, the canvases keep their pictures, stretched; let go, each draws once at its size
  static hold(on) {
    held = on;
    if (on) return;
    const surfaces = [...missed];
    missed.clear();
    surfaces.forEach((s) => s.draw());
  }

  constructor(pdf, { pageOf = (slide) => slide?.page, className = "tq-slide" } = {}) {
    this.pdf = pdf;
    this.pageOf = pageOf;
    this.element = document.createElement("canvas");
    this.element.className = className;
    this.slide = null;
    this.n = null;
    this.view = null;
    this.zoom = null;              // the view a Stage's show() uses (it passes only the slide)
    this.drawn = "";
    this.wanted = "";
    new ResizeObserver(() => this.draw()).observe(this.element);
  }

  show(slide, view = this.zoom) {
    this.slide = slide || null;
    this.n = (slide && !slide.board && this.pageOf(slide)) || null;
    this.view = view;
    this.draw();
  }

  size() {
    const r = this.element.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    return [Math.round(r.width * dpr), Math.round(r.height * dpr)];
  }

  async draw() {
    const [w, h] = this.size();
    if (w < 2 || h < 2) return;                    // not laid out (yet)
    if (held) {
      missed.add(this);
      return;
    }
    const el = this.element;
    const v = this.view;
    const zoom = v ? `:${v.x},${v.y},${v.w},${v.h}` : "";
    const board = this.slide?.board ? this.slide.kind : null;
    const id = board ? `board-${board}@${w}x${h}${zoom}` : this.n ? `${this.n}@${w}x${h}${zoom}` : `none@${w}x${h}`;
    this.wanted = id;                              // (also when it is drawn: a slower page may still come)
    if (id === this.drawn) return;
    let page = null;
    if (this.n) {
      try {
        page = await this.pdf.render(this.n, w, h, v);
      } catch (err) {
        console.warn("texstage: page", this.n, err);
      }
    }
    if (this.wanted !== id) return;               // moved on meanwhile
    if (el.width !== w || el.height !== h) {
      el.width = w;
      el.height = h;
    }
    const ctx = el.getContext("2d");
    ctx.clearRect(0, 0, w, h);
    if (page || board) {
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, w, h);
    }
    if (page) ctx.drawImage(page, Math.round((w - page.width) / 2), Math.round((h - page.height) / 2));
    if (board === "grid") grid(ctx, w, h, v);
    this.drawn = id;
  }
}

// a whiteboard page's grid: squares of 1/20 of the page's height
function grid(ctx, w, h, view) {
  const v = view || { x: 0, y: 0, w: 1, h: 1 };
  const aspect = w / h;                            // the page's (a zoom keeps it)
  const step = 0.05;
  ctx.strokeStyle = "#d8e1ee";
  ctx.lineWidth = Math.max(1, h / 700);
  ctx.beginPath();
  for (let y = 0; y <= 1 + 1e-9; y += step) {
    const py = Math.round(((y - v.y) / v.h) * h) + 0.5;
    ctx.moveTo(0, py);
    ctx.lineTo(w, py);
  }
  for (let x = 0; x <= aspect + 1e-9; x += step) {
    const px = Math.round(((x / aspect - v.x) / v.w) * w) + 0.5;
    ctx.moveTo(px, 0);
    ctx.lineTo(px, h);
  }
  ctx.stroke();
}

// keeps `box` the largest box of the ratio `aspect` (width / height) inside its parent
export function fit(box, aspect) {
  const parent = box.parentElement;
  const resize = () => {
    const width = Math.max(0, Math.min(parent.clientWidth, parent.clientHeight * aspect));
    box.style.width = `${Math.floor(width)}px`;
    box.style.height = `${Math.floor(width / aspect)}px`;
  };
  new ResizeObserver(resize).observe(parent);
  resize();
}

// the link at (x, y) - fractions of the page - with `slack` around each (a finger is not a
// mouse); the smallest if links overlap; or null
export function linkAt(links, x, y, slack = 0) {
  let best = null;
  for (const l of links || []) {
    const inside = x >= l.x - slack && x <= l.x + l.w + slack && y >= l.y - slack && y <= l.y + l.h + slack;
    if (inside && (!best || l.w * l.h < best.w * best.h)) best = l;
  }
  return best;
}

// The web links of the page shown in `box` made clickable: over a link the cursor is a hand and
// the address its tooltip; a click - the mouse, or a finger's tap - opens it in a new tab.
//   pdf()    the PdfDeck shown (it may change: another deck)
//   page()   the page number shown, or null (a whiteboard page, a poll: no links)
//   at(e)    [x, y], the pointer's place in fractions of the page (with the zoom)
//   active(e) whether a click may open a link now (a pen draws, a tool has its own clicks)
// The click is taken in the capture phase, so nothing else gets a click that opened a link.
export function linkable(box, { pdf, page, at, active = () => true }) {
  let down = null;
  const hit = (e, slack) => {
    const d = pdf();
    const n = page();
    if (!d || !n || !active(e)) return null;
    if (e.target.closest?.("button, a, input, textarea, select, .tq-typectl, .tq-video")) return null;
    const [x, y] = at(e);
    return linkAt(d.linksNow(n), x, y, slack);
  };
  const hover = (link) => {
    box.classList.toggle("tq-onlink", Boolean(link));
    if (link) box.title = link.url;
    else box.removeAttribute("title");
  };
  box.addEventListener("pointerdown", (e) => { down = { id: e.pointerId, x: e.clientX, y: e.clientY }; }, true);
  box.addEventListener("pointermove", (e) => { if (e.pointerType !== "touch") hover(hit(e, 0)); });
  box.addEventListener("pointerleave", () => hover(null));
  box.addEventListener("click", (e) => {
    if (e.button !== 0 || e.pointerType === "pen") return;
    if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 10) return;   // a swipe or a drag
    const link = hit(e, e.pointerType === "touch" ? 0.012 : 0);
    if (!link) return;
    e.preventDefault();
    e.stopPropagation();
    window.open(link.url, "_blank", "noopener");
  }, true);
}

// the frames of a deck in order: {frame, first, last} (slides of deck.json)
export function framesOf(deck) {
  const frames = new Map();
  for (const s of deck.slides) {
    const f = frames.get(s.frame) || { frame: s.frame, first: s, last: s };
    f.last = s;
    frames.set(s.frame, f);
  }
  return [...frames.values()];
}

// a poll of the game or picked sketches, which the projector shows instead of the slide (M6):
// slides of their own on a blank page (live.js draws them), or null
export function overlaySlide(state) {
  const st = state?.stage || {};
  if (st.poll) return { board: `poll:${st.poll}`, kind: "blank", overlay: "poll", quiz: st.poll, phase: "question" };
  if (st.sketches) return { board: `sketches:${st.sketches.quiz}`, kind: "blank", overlay: "sketches", ...st.sketches };
  return null;
}

// what the projector shows: a poll or sketches (overlaySlide), the frozen slide or whiteboard
// page while frozen, else the one shown; a whiteboard page as {board, kind, after}
export function shownSlide(deck, state) {
  const overlay = overlaySlide(state);
  if (overlay) return overlay;
  const st = state?.stage || {};
  const frozen = st.screen === "freeze";
  const board = frozen ? st.frozen_board : st.board;
  if (board) {
    const b = (st.boards || []).find((x) => x.id === board);
    if (b) return { board: b.id, kind: b.kind, after: b.after };
  }
  const id = frozen && st.frozen !== null && st.frozen !== undefined ? st.frozen : state?.session?.slide;
  return deck.slides.find((s) => s.id === id) || null;
}

// the live views of a Stage (live.js) zoomed like the slide, a video and its bar too: the part
// `view` fills the stage
export function zoomOverlay(stageEl, view) {
  const zoom = view ? `scale(${1 / view.h}) translate(${-view.x * 100}%, ${-view.y * 100}%)` : "";
  for (const layer of stageEl.querySelectorAll(":scope > .tq-live, :scope > .tq-types, :scope > .tq-typectl")) {
    layer.style.transform = zoom;
  }
}

// the ink of a slide or a whiteboard page: its frame's ("12", "board:<id>"); a poll's page has
// its own ("poll:<id>"), picked sketches none
export function inkKey(slide) {
  if (!slide) return null;
  if (slide.overlay) return slide.overlay === "poll" ? `poll:${slide.quiz}` : null;
  return slide.board ? `board:${slide.board}` : String(slide.frame);
}

// the slides and whiteboard pages in the order presented: a page after its frame's last step
export function sequence(deck, boards) {
  const out = [];
  const after = new Map();
  for (const b of boards || []) {
    if (!after.has(b.after)) after.set(b.after, []);
    after.get(b.after).push({ board: b.id, kind: b.kind, after: b.after });
  }
  for (const b of after.get(0) || []) out.push(b);
  deck.slides.forEach((s, i) => {
    out.push(s);
    const nextFrame = deck.slides[i + 1]?.frame;
    if (nextFrame !== s.frame) for (const b of after.get(s.frame) || []) out.push(b);
  });
  return out;
}
