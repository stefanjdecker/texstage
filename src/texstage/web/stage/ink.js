// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Ink for texstage (docs/texstage-design.md, section 7; the server's side: server/ink.py): the
// strokes of a frame - a deck frame "12" or a whiteboard page "board:<id>" -, loaded from the
// server and kept up to date by its events, drawn as perfect-freehand outlines on a canvas over
// the slide, also while they are being drawn; and the laser pointer. Coordinates are fractions
// of the slide; a zoom (`view`, {x, y, w, h}, w = h) shows a part of it.
//
//   const book = new InkBook(client);            // all windows: strokes per frame
//   const layer = new InkLayer(book, aspect);    // a canvas (layer.element) over the slide
//   layer.show(key, view);                        // the frame shown, the zoom (or null)
//   book.event(msg);                              // the server's {op: begin|points|end|erase|restore}
//   const pointer = new PointerLayer(aspect);     // the laser pointer (a dot): move(x, y), off(), show(view)

import { getStroke } from "/static/vendor/perfect-freehand/index.mjs";

const SHAPES = {                                   // perfect-freehand's options per tool
  pen: { thinning: 0.55, smoothing: 0.5, streamline: 0.35, start: { taper: 0 }, end: { taper: 0 } },
  highlighter: { thinning: 0, smoothing: 0.6, streamline: 0.5, start: { cap: true }, end: { cap: true } },
};
export const HIGHLIGHT = 0.35;                     // the highlighter's opacity
const UNIT = 1000;                                // perfect-freehand works in thousandths of the slide's
                                                   // height: it is tuned for pixels, and in fractions its
                                                   // constants (a radius of at least 0.01) swamp the stroke

export class InkBook {
  constructor(client) {
    this.client = client;
    this.frames = new Map();        // frame key -> Map(stroke id -> stroke)
    this.where = new Map();         // stroke id -> frame key
    this.loaded = new Set();
    this.listeners = new Set();     // called after every change: (frame key) => ...
  }

  strokes(key) {
    return [...(this.frames.get(key)?.values() || [])];
  }

  frame(key) {
    if (!this.frames.has(key)) this.frames.set(key, new Map());
    return this.frames.get(key);
  }

  // the frame's strokes from the server, once (events keep them up to date afterwards)
  load(key) {
    if (!key || this.loaded.has(key)) return;
    this.loaded.add(key);
    this.client.send({ t: "ink.load", frame: key }).then((r) => {
      const strokes = this.frame(key);
      for (const s of r.strokes) if (!strokes.has(s.id)) this.put({ ...s, live: false });
      for (const s of r.drawing) if (!strokes.has(s.id)) this.put({ ...s, live: true });
      this.changed(key);
    }).catch((err) => {
      this.loaded.delete(key);
      console.warn("texstage: ink of", key, err);
    });
  }

  put(stroke) {
    this.frame(stroke.frame).set(stroke.id, stroke);
    this.where.set(stroke.id, stroke.frame);
  }

  // forgets everything (after a broken connection, events may be missing): loaded anew
  reset() {
    this.frames.clear();
    this.where.clear();
    this.loaded.clear();
  }

  changed(key) {
    for (const f of this.listeners) f(key);
  }

  // an event of the server (ink.py): another window drew, erased, or took something back
  event(e) {
    const key = e.op === "points" || e.op === "end" ? this.where.get(e.stroke) : e.frame;
    if (!key) return;
    const strokes = this.frame(key);
    if (e.op === "begin") this.put({ ...e.stroke, live: true });
    else if (e.op === "points") strokes.get(e.stroke)?.points.push(...e.points);
    else if (e.op === "end") {
      const s = strokes.get(e.stroke);
      if (s) s.live = false;
    } else if (e.op === "erase") {
      for (const id of e.strokes) strokes.delete(id);
    } else if (e.op === "restore") {
      for (const s of e.strokes) this.put({ ...s, live: false });
    }
    this.changed(key);
  }
}

// the outline of a stroke as SVG path data in slide heights (x * aspect, y): the canvas and the
// annotated PDF (export.js) draw the same
export function strokeSvg(stroke, aspect) {
  // without a pen (mouse, finger) the width stays even: a pressure made up from the speed
  // thins quick strokes to a hairline
  const shape = stroke.sim ? { ...SHAPES[stroke.tool], thinning: 0 } : SHAPES[stroke.tool];
  const outline = getStroke(stroke.points.map(([x, y, p]) => [x * aspect * UNIT, y * UNIT, p]),
    { size: stroke.width * UNIT, simulatePressure: false, last: !stroke.live, ...shape });
  return svgPath(outline.map(([x, y]) => [x / UNIT, y / UNIT]));
}

// the same as a Path2D, cached on the stroke
export function strokePath(stroke, aspect) {
  const n = stroke.points.length;
  if (stroke.path && stroke.pathN === n && stroke.pathLive === stroke.live && stroke.pathAspect === aspect) return stroke.path;
  stroke.path = new Path2D(strokeSvg(stroke, aspect));
  stroke.pathN = n;
  stroke.pathLive = stroke.live;
  stroke.pathAspect = aspect;
  return stroke.path;
}

function svgPath(points) {
  // quadratic curves through the midpoints of the outline (perfect-freehand's README)
  if (points.length < 2) return "";
  const d = ["M", points[0][0].toFixed(5), points[0][1].toFixed(5), "Q"];
  for (let i = 0; i < points.length; i += 1) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % points.length];
    d.push(x0.toFixed(5), y0.toFixed(5), ((x0 + x1) / 2).toFixed(5), ((y0 + y1) / 2).toFixed(5));
  }
  d.push("Z");
  return d.join(" ");
}

// the canvas transform for slide heights -> device pixels of a canvas `height` high, zoomed to `view`
function transform(ctx, height, aspect, view) {
  const k = height / (view ? view.h : 1);
  ctx.setTransform(k, 0, 0, k, -(view ? view.x * aspect : 0) * k, -(view ? view.y : 0) * k);
}

function fit(canvas) {
  const r = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(r.width * dpr);
  const h = Math.round(r.height * dpr);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  return [w, h];
}

// a canvas that draws the strokes of one frame (whenever they change), zoomed like the slide
export class InkLayer {
  constructor(book, aspect, className = "ink") {
    this.book = book;
    this.aspect = aspect;
    this.element = document.createElement("canvas");
    this.element.className = className;
    this.key = null;
    this.view = null;
    this.dirty = true;
    book.listeners.add((key) => { if (key === this.key) this.redraw(); });
    new ResizeObserver(() => this.redraw()).observe(this.element);
  }

  show(key, view = null) {
    if (key === this.key && JSON.stringify(view) === JSON.stringify(this.view)) return;
    this.key = key;
    this.view = view;
    this.book.load(key);
    this.redraw();
  }

  reload() {
    this.book.load(this.key);
    this.redraw();
  }

  redraw() {
    if (this.dirty && this.frameRequested) return;
    this.dirty = true;
    this.frameRequested = true;
    requestAnimationFrame(() => {
      this.frameRequested = false;
      if (this.dirty) this.draw();
    });
  }

  draw() {
    this.dirty = false;
    const [w, h] = fit(this.element);
    const ctx = this.element.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!this.key || w < 2) return;
    transform(ctx, h, this.aspect, this.view);
    const strokes = this.book.strokes(this.key);
    for (const tool of ["highlighter", "pen"]) {            // highlighting under the writing
      ctx.globalAlpha = tool === "highlighter" ? HIGHLIGHT : 1;
      for (const s of strokes) {
        if (s.tool !== tool) continue;
        ctx.fillStyle = s.color;
        ctx.fill(strokePath(s, this.aspect));
      }
    }
    ctx.globalAlpha = 1;
  }
}

// the strokes of `strokes` that a round eraser at (x, y) - fractions of the slide - touches
export function touched(strokes, x, y, radius, aspect) {
  const px = x * aspect;
  const hit = [];
  for (const s of strokes) {
    const reach = radius + s.width / 2;
    const pts = s.points;
    for (let i = 0; i < pts.length; i += 1) {
      const ax = pts[i][0] * aspect;
      const ay = pts[i][1];
      const [bx, by] = i + 1 < pts.length ? [pts[i + 1][0] * aspect, pts[i + 1][1]] : [ax, ay];
      if (segmentDistance(px, y, ax, ay, bx, by) <= reach) {
        hit.push(s.id);
        break;
      }
    }
  }
  return hit;
}

function segmentDistance(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

// the laser pointer: a red dot over everything on the slide, drawn the moment it moves - no
// trail (until 2026-10-10 a 300 ms fading trail followed it, and every movement looked late)
export class PointerLayer {
  constructor(aspect) {
    this.aspect = aspect;
    this.element = document.createElement("canvas");
    this.element.className = "pointer";
    this.at = null;                 // [x, y] in fractions of the slide, or null: off
    this.view = null;
  }

  show(view) {
    this.view = view;
    this.draw();
  }

  move(x, y) {
    this.at = [x, y];
    this.draw();
  }

  off() {
    this.at = null;
    this.draw();
  }

  draw() {
    const [w, h] = fit(this.element);
    const ctx = this.element.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!this.at || w < 2) return;
    const v = this.view || { x: 0, y: 0, w: 1, h: 1 };
    const x = ((this.at[0] - v.x) / v.w) * w;
    const y = ((this.at[1] - v.y) / v.h) * h;
    const r = Math.max(4, h * 0.011);
    const glow = ctx.createRadialGradient(x, y, 0, x, y, r * 2.4);
    glow.addColorStop(0, "rgba(255, 40, 60, 0.95)");
    glow.addColorStop(0.35, "rgba(255, 40, 60, 0.85)");
    glow.addColorStop(1, "rgba(255, 40, 60, 0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(x, y, r * 2.4, 0, Math.PI * 2);
    ctx.fill();
  }
}
