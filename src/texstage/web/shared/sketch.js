// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Sketches (texstage M6): what the phones draw for a sketch question - strokes on a 1000 x 750
// canvas (4:3) in whole units, simplified (Ramer-Douglas-Peucker) until the answer fits in a
// message (the server checks the same: scoring.py) - and how the pages draw them.
//
//   const pad = new SketchPad(element, {onChange});     // the phone: draw, pen, undo, clear
//   client.send({t: "answer", round, answer: {strokes: pad.encode()}});
//   el.innerHTML = sketchSVG(strokes);                   // the gallery, the projector

import { texts } from "../i18n/i18n.js";

export const W = 1000;
export const H = 750;
export const PENS = ["#1d1d1f", "#e21b3c", "#1368ce", "#26890c"];
const WIDTH = 8;
const BUDGET = 14000;                  // characters of the strokes' JSON (a message has at most 16 KiB)
const NUMBERS = 6000;                  // the x and y of all points (scoring.py)

// Ramer-Douglas-Peucker: the points of a line that stay further than `eps` from it
export function simplify(points, eps) {
  if (points.length <= 2) return points.slice();
  const keep = new Uint8Array(points.length);
  keep[0] = keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop();
    const [ax, ay] = points[a];
    const [bx, by] = points[b];
    const dx = bx - ax;
    const dy = by - ay;
    const len = Math.hypot(dx, dy);
    let far = -1;
    let at = -1;
    for (let i = a + 1; i < b; i++) {
      const [x, y] = points[i];
      // from the line through a and b - or, if they are one point (a closed stroke), from it
      const d = len ? Math.abs(dy * x - dx * y + bx * ay - by * ax) / len : Math.hypot(x - ax, y - ay);
      if (d > far) [far, at] = [d, i];
    }
    if (far > eps) {
      keep[at] = 1;
      stack.push([a, at], [at, b]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

// strokes as the server takes them: [{c, p: [x, y, ...]}] - simplified more until they fit;
// null if even then they do not (far too much drawn)
export function encode(strokes) {
  for (const eps of [0.6, 1.2, 2, 3.5, 6, 10]) {
    const out = strokes.map((s) => ({ c: s.c, p: simplify(s.points, eps).flatMap(([x, y]) => [Math.round(x), Math.round(y)]) }));
    const numbers = out.reduce((n, s) => n + s.p.length, 0);
    if (numbers <= NUMBERS && JSON.stringify(out).length <= BUDGET) return out;
  }
  return null;
}

// a sketch as SVG markup; label: its number ("#3"), for what a screen reader says of it - "Sketch #3",
// in the page's language (<html lang>, which the page sets: i18n.js markLanguage)
export function sketchSVG(strokes, label = "") {
  const lines = (strokes || []).map((s) => {
    const p = s.p.length > 2 ? s.p : [...s.p, ...s.p];                   // a dot: a line of no length
    const pts = [];
    for (let i = 0; i < p.length; i += 2) pts.push(`${p[i]},${p[i + 1]}`);
    return `<polyline points="${pts.join(" ")}" stroke="${PENS[s.c || 0]}"/>`;
  }).join("");
  const name = texts(globalThis.document?.documentElement?.lang).sketch.label(label)
    .replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  return `<svg class="tq-sketch" viewBox="0 0 ${W} ${H}" role="img" aria-label="${name}">
    <g fill="none" stroke-width="${WIDTH}" stroke-linecap="round" stroke-linejoin="round">${lines}</g></svg>`;
}

// the phone's drawing area: a finger, a pen or the mouse draws; the strokes stay in canvas units
export class SketchPad {
  constructor(el, { onChange = () => {} } = {}) {
    this.el = el;
    this.onChange = onChange;
    this.strokes = [];               // {c, points: [[x, y], ...]}
    this.pen = 0;
    this.drawing = null;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "pad";
    el.append(this.canvas);
    this.canvas.addEventListener("pointerdown", (e) => this.down(e));
    this.canvas.addEventListener("pointermove", (e) => this.move(e));
    this.canvas.addEventListener("pointerup", (e) => this.up(e));
    this.canvas.addEventListener("pointercancel", (e) => this.up(e));
    new ResizeObserver(() => this.draw()).observe(this.canvas);
  }

  point(e) {
    const r = this.canvas.getBoundingClientRect();
    const x = Math.min(W, Math.max(0, ((e.clientX - r.left) / r.width) * W));
    const y = Math.min(H, Math.max(0, ((e.clientY - r.top) / r.height) * H));
    return [x, y];
  }

  down(e) {
    if (this.drawing || (e.pointerType === "mouse" && e.button !== 0)) return;
    e.preventDefault();
    try { this.canvas.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    this.drawing = { id: e.pointerId, stroke: { c: this.pen, points: [this.point(e)] } };
    this.strokes.push(this.drawing.stroke);
    this.draw();
  }

  move(e) {
    if (!this.drawing || e.pointerId !== this.drawing.id) return;
    e.preventDefault();
    const all = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
    for (const ev of all.length ? all : [e]) this.drawing.stroke.points.push(this.point(ev));
    this.draw();
  }

  up(e) {
    if (!this.drawing || e.pointerId !== this.drawing.id) return;
    this.drawing = null;
    this.onChange(this);
  }

  undo() {
    this.strokes.pop();
    this.draw();
    this.onChange(this);
  }

  clear() {
    this.strokes = [];
    this.draw();
    this.onChange(this);
  }

  encode() {
    return encode(this.strokes);
  }

  draw() {
    const r = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(r.width * dpr);
    const h = Math.round(r.height * dpr);
    if (w < 2 || h < 2) return;
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    const ctx = this.canvas.getContext("2d");
    ctx.clearRect(0, 0, w, h);
    ctx.lineCap = ctx.lineJoin = "round";
    ctx.lineWidth = (WIDTH * w) / W;
    for (const s of this.strokes) {
      ctx.strokeStyle = PENS[s.c];
      ctx.beginPath();
      s.points.forEach(([x, y], i) => (i ? ctx.lineTo((x * w) / W, (y * h) / H) : ctx.moveTo((x * w) / W, (y * h) / H)));
      if (s.points.length === 1) ctx.lineTo((s.points[0][0] * w) / W + 0.01, (s.points[0][1] * h) / H);
      ctx.stroke();
    }
  }
}
