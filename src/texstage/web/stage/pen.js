// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The pen's colours and widths, and a pen on a slide without the presenter's tools: the projector
// window on a pen display in the lecture hall (docs/texstage-design.md, section 24). The pen draws
// in the presenter window's pen colour and width, its eraser end erases, and with its side button
// held - hovering or touching - it is the laser pointer; mouse and finger do what they did. The
// strokes go out under the presenter window's name for undo (ink.py) - a window it opens starts
// with a copy of its sessionStorage -, so its ↶, ↷ and Clear take them too.
//
//   new Pen(box, { book, send, raw, laser, aspect, where: () => ({ frame, zoom }) });

import { touched } from "/static/stage/ink.js";

export const PENS = ["#1d1d1f", "#e21b3c", "#1368ce", "#26890c"];
export const MARKERS = ["#ffd400", "#7ee36b", "#ff8ad8", "#6cc8ff"];
export const SIZES = { S: 0.003, M: 0.005, L: 0.009 };   // pen widths: of the slide's height
export const MARKER = 0.022;                  // the highlighter's width
export const ERASER = 0.014;                  // the eraser's radius, at the size the slide is shown
export const BATCH = 400;                     // points per message
const PREFS = "texstage:prefs";               // the presenter window's (presenter.js)

export function deviceId() {
  // the window's name for undo and redo (ink.py): kept over reloads of the tab
  try {
    let id = sessionStorage.getItem("texstage:device");
    if (!id) {
      id = Math.random().toString(36).slice(2, 10);
      sessionStorage.setItem("texstage:device", id);
    }
    return id;
  } catch {
    return Math.random().toString(36).slice(2, 10);
  }
}

const round = (v, d) => Math.round(v * d) / d;

function penStyle() {
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem(PREFS) || "{}"); } catch { /* private mode */ }
  return { color: prefs.pen || PENS[0], width: SIZES[prefs.width] || SIZES.M };
}

export class Pen {
  constructor(box, { book, send, raw, laser, aspect, where }) {
    Object.assign(this, { box, book, send, raw, laser, aspect, where, device: deviceId(), drawing: null, counter: 0,
      flushing: false, pointing: false });
    box.addEventListener("pointerdown", (e) => this.down(e));
    box.addEventListener("pointermove", (e) => this.move(e));
    box.addEventListener("pointerup", (e) => this.up(e));
    box.addEventListener("pointercancel", (e) => this.up(e));
    box.addEventListener("pointerleave", (e) => { if (e.pointerType === "pen") this.pointerOff(); });
    box.addEventListener("contextmenu", (e) => e.preventDefault());    // the side button's tap: no menu
  }

  point(e, zoom) {
    const r = this.box.getBoundingClientRect();
    const v = zoom || { x: 0, y: 0, w: 1, h: 1 };
    const x = v.x + ((e.clientX - r.left) / r.width) * v.w;
    const y = v.y + ((e.clientY - r.top) / r.height) * v.h;
    return [round(x, 1e4), round(y, 1e4), round(e.pressure > 0 ? e.pressure : 0.5, 1e3)];
  }

  down(e) {
    if (e.pointerType !== "pen" || this.drawing) return;      // mouse and finger: as before
    const { frame, zoom } = this.where();
    const side = e.button === 2 || (e.buttons & 2) !== 0;    // the side button: the laser pointer
    if (!frame && !side) return;                               // a poll or sketches on the screen: no ink
    e.preventDefault();
    try { this.box.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    const p = this.point(e, zoom);
    if (side) {
      this.drawing = { id: e.pointerId, zoom, laser: true };
      this.pointer(p);
      return;
    }
    if (e.button === 5 || (e.buttons & 32)) {                 // the pen's eraser end
      this.drawing = { id: e.pointerId, frame, zoom, erased: new Set() };
      this.erase(p);
      return;
    }
    const { color, width } = penStyle();
    const stroke = { id: `${this.device}-${Date.now().toString(36)}-${++this.counter}`, frame, tool: "pen",
      color, width, sim: false, points: [p], live: true };
    this.book.put(stroke);
    this.book.changed(frame);
    this.drawing = { id: e.pointerId, frame, zoom, stroke, sent: 1 };
    this.send({ t: "ink.begin", device: this.device, frame, points: [p],
      stroke: { id: stroke.id, tool: stroke.tool, color, width, sim: false } });
  }

  move(e) {
    if (e.pointerType !== "pen") return;
    const d = this.drawing;
    if (!d) {                                                  // hovering: the laser while the side button is held
      if (e.buttons & 2) this.pointer(this.point(e, this.where().zoom));
      else this.pointerOff();
      return;
    }
    if (e.pointerId !== d.id) return;
    e.preventDefault();
    if (d.laser) {
      this.pointer(this.point(e, d.zoom));
      return;
    }
    const all = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
    for (const ev of all.length ? all : [e]) {
      const p = this.point(ev, d.zoom);
      if (d.stroke) d.stroke.points.push(p);
      else this.erase(p);
    }
    if (!d.stroke) return;
    this.book.changed(d.frame);
    if (this.flushing) return;
    this.flushing = true;
    requestAnimationFrame(() => {
      this.flushing = false;
      if (this.drawing?.stroke) this.flush(this.drawing);
    });
  }

  up(e) {
    const d = this.drawing;
    if (!d || e.pointerId !== d.id) return;
    this.drawing = null;
    if (d.laser) {
      this.pointerOff();
    } else if (d.stroke) {
      this.flush(d);
      d.stroke.live = false;
      this.book.changed(d.frame);
      this.send({ t: "ink.end", stroke: d.stroke.id });
    } else if (d.erased.size) {
      this.send({ t: "ink.erase", device: this.device, frame: d.frame, strokes: [...d.erased] });
    }
  }

  flush(d) {
    const pts = d.stroke.points;
    while (d.sent < pts.length) {
      const batch = pts.slice(d.sent, d.sent + BATCH);
      d.sent += batch.length;
      this.send({ t: "ink.points", stroke: d.stroke.id, points: batch });
    }
  }

  pointer([x, y]) {
    // shown here and sent on at once (as the presenter's)
    this.laser.move(x, y);
    this.pointing = true;
    this.raw({ t: "pointer", x, y });
  }

  pointerOff() {
    if (!this.pointing) return;
    this.pointing = false;
    this.laser.off();
    this.raw({ t: "pointer", off: true });
  }

  erase([x, y]) {
    const d = this.drawing;
    const strokes = this.book.strokes(d.frame).filter((s) => !s.live);
    const hit = touched(strokes, x, y, ERASER * (d.zoom ? d.zoom.h : 1), this.aspect);
    for (const id of hit) {
      d.erased.add(id);
      this.book.frame(d.frame).delete(id);
    }
    if (hit.length) this.book.changed(d.frame);
  }
}
