// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The presenter window's dividers, as in PowerPoint's presenter view: one between the current slide
// and the column with the next slide and the notes (in a narrow window, where the column stands below
// the slide, between the two), one between the next slide and the notes. Drag one - mouse, pen or
// finger -, or give it the focus (Tab) and move it with the arrow keys (Shift: further); a double
// click or tap puts it back. The shares are kept with the presenter's other preferences.
//
//   new Dividers(grid, prefs.split, (shares) => { prefs.split = shares; savePrefs(); });

import { PdfSurface } from "/static/stage/pdfview.js";

// the column's part of the width, the next slide's part of the column, and the column's part of the
// window's height when it stands below the slide (stage.css: 1.85 : 1, 30 %, 38vh before)
export const SHARES = { side: 0.35, next: 0.3, stacked: 0.38 };
const LIMITS = { side: [0.15, 0.7], next: [0, 0.8], stacked: [0.12, 0.75] };
const NARROW = window.matchMedia("(max-width: 900px)");     // stage.css: the column below the slide
const STEP = 0.02;
const AGAIN_MS = 400;                                         // a second press this soon: put it back

const orient = (el) => el.setAttribute("aria-orientation", NARROW.matches ? "horizontal" : "vertical");
NARROW.addEventListener("change", () => document.querySelectorAll(".split.main").forEach(orient));

export class Dividers {
  constructor(grid, shares, save) {
    this.grid = grid;
    this.shares = { ...SHARES, ...shares };
    this.save = save;
    this.last = { main: 0, next: 0 };
    for (const which of ["main", "next"]) {
      const el = grid.querySelector(`.split.${which}`);
      el.addEventListener("pointerdown", (e) => this.down(e, which));
      el.addEventListener("keydown", (e) => this.key(e, which));
    }
    orient(grid.querySelector(".split.main"));
    this.apply();
  }

  // the share the divider moves: the column's width, or its height below the slide, or the next slide's
  part(which) {
    return which === "next" ? "next" : NARROW.matches ? "stacked" : "side";
  }

  set(part, value) {
    const [lo, hi] = LIMITS[part];
    this.shares[part] = Math.round(Math.min(hi, Math.max(lo, value)) * 1000) / 1000;
    this.apply();
  }

  apply() {
    const s = this.shares;
    this.grid.style.setProperty("--side-w", `${s.side * 100}%`);
    this.grid.style.setProperty("--next-h", `${s.next * 100}%`);
    this.grid.style.setProperty("--side-h", `${s.stacked * 100}vh`);
    for (const which of ["main", "next"]) {
      const el = this.grid.querySelector(`.split.${which}`);
      const part = this.part(which);
      el.setAttribute("aria-valuenow", String(Math.round(s[part] * 100)));
      el.setAttribute("aria-valuemin", String(LIMITS[part][0] * 100));
      el.setAttribute("aria-valuemax", String(LIMITS[part][1] * 100));
    }
  }

  reset(which) {
    const part = this.part(which);
    this.set(part, SHARES[part]);
    this.save({ ...this.shares });
  }

  down(e, which) {
    if (e.button !== 0) return;
    e.preventDefault();                                       // no text selection
    const el = e.currentTarget;
    const again = e.timeStamp - this.last[which] < AGAIN_MS;  // the second press of a double click or tap
    try { el.setPointerCapture(e.pointerId); } catch { /* a pointer that is gone already */ }
    const [x0, y0] = [e.clientX, e.clientY];
    let moved = false;
    const move = (ev) => {
      if (!moved && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 3) return;   // a click so far
      if (!moved) {
        moved = true;
        el.classList.add("dragging");
        PdfSurface.hold(true);                                // the pictures stretch until it is let go
      }
      this.drag(ev, which);
    };
    const up = (ev) => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      if (moved) {
        el.classList.remove("dragging");
        PdfSurface.hold(false);
        this.save({ ...this.shares });
      } else if (again) {
        this.reset(which);
      }
      this.last[which] = moved || again ? 0 : ev.timeStamp;  // a click: another one soon puts it back
      // the arrow keys stay the slides': a divider keeps the focus only from Tab, never from a click
      const unfocus = () => { if (document.activeElement === el) el.blur(); };
      unfocus();
      setTimeout(unfocus, 0);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }

  drag(e, which) {
    const side = this.grid.querySelector(".side").getBoundingClientRect();
    if (which === "next") {
      const top = this.grid.querySelector(".nextwrap").getBoundingClientRect().top;
      const share = (e.clientY - top) / side.height;
      this.set("next", share < 0.05 ? 0 : share);             // up to the top: no next slide, all notes
    } else if (NARROW.matches) {
      this.set("stacked", (side.bottom - e.clientY) / window.innerHeight);
    } else {
      const g = this.grid.getBoundingClientRect();
      const pad = parseFloat(getComputedStyle(this.grid).paddingLeft) || 0;
      this.set("side", (side.right - e.clientX) / (g.width - 2 * pad));
    }
  }

  key(e, which) {
    if (e.key === "Escape") {                                 // and on to the presenter's Esc
      e.currentTarget.blur();
      return;
    }
    const part = this.part(which);
    const step = e.shiftKey ? 5 * STEP : STEP;
    const delta = {
      side: { ArrowLeft: step, ArrowRight: -step },          // the divider moves left: a wider column
      stacked: { ArrowUp: step, ArrowDown: -step },          // up: a taller column below the slide
      next: { ArrowUp: -step, ArrowDown: step },             // up: less of the next slide
    }[part][e.key];
    if (!delta) return;                                       // other keys: the presenter's
    e.preventDefault();
    e.stopPropagation();
    this.set(part, this.shares[part] + delta);
    this.save({ ...this.shares });
  }
}
