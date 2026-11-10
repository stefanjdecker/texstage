// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A live activity on the slide (texactivity.sty; docs/live-activities-design.md, sections 8 and 9):
// the renderer of its box for live.js's Stage - in the presenter and in the projector window -
// and the presenter window's ActivityAgent.
//
// The box draws the activity's picture, which it fetches (activity.view, a read) whenever the
// activity's version or layout in the state changes, at most twice a second: the crowd graph -
// nodes as labels (a literal as a box, as the slides draw one), edges as arrows with theirs,
// thicker with more students - or the clusters of
// the queries (or Turtle texts), a bar each, the reference's ticked (in the presenter window at
// once, everywhere after the reveal), a shown cluster as a card with its query and its result
// (codeWords: what a query is called, engine by engine). Both windows draw
// what the class sees, in the deck's language (boxWords); the box lies under the ink, so the lecturer
// writes on it. What the phones sent is set as text, never as HTML.
//
// The graph's positions are fractions of the box. The presenter window with the lease (the
// agent's: activity.work, renewed every 5 s) lays the graph out - a force layout that keeps the
// nodes where they were - and sends the positions (activity.layout, at most twice a second); the
// other windows move their nodes there, and lay out by themselves only while none come. With
// the same positions everywhere, a circle drawn around a node on the iPad lies around it on the
// projector.
//
//   new Stage(el, {types: {activity: ActivityBox}, host: {role, read, agent}})
//     read(msg)   a promise of the server's reply (the projector may read: activity.view)
//     agent       the presenter window's ActivityAgent; none in the projector

import { texts } from "../i18n/i18n.js";

const FETCH_MS = 500;       // a picture at most this often
const LAYOUT_MS = 500;      // positions sent at most this often
const FRAMELESS_MS = 300;   // no frame for this long: the window is not drawn (ActivityBox.drawGraph)
const RENEW_MS = 5000;      // the lease asked for again (it lasts 15 s)
const ELABEL = 17;          // an edge's label's font size, viewBox units (stage.css: .tq-elabel)
const GLIDE = 0.25;         // a label that changes its spot goes this part of the way a frame
const SVG = "http://www.w3.org/2000/svg";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const pct = (v) => `${(v * 100).toFixed(3)}%`;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const slideAspect = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--tq-aspect")) || 16 / 9;

function hash01(text) {
  // FNV-1a over the UTF-16 units: a node's place before it has one, the same in every window
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h / 4294967296;
}

// A label's font size (viewBox units, the box 1000 wide): smaller when the graph is crowded,
// larger for a node more students named.
export function labelSize(node, count) {
  const base = 20 - 6 * clamp((count - 20) / 40, 0, 1);
  return Math.min(base + 10, base + 2 * Math.log2(1 + (node.n || 1)));
}

// The edges' shapes, one per edge: two or more edges between the same nodes, either way round,
// curve apart (bend: how far the curve's middle lies off the straight line, to the left of the
// edge's own direction; the middle one of an odd number straight); a node's own edge - a triple
// whose subject is its object - is a loop above its label, the next one larger (loop: 0, 1, ...).
const BEND = 34;                                                // viewBox units between two curves
export const loopHeight = (i) => 1.7 + 0.9 * i;                 // loop i's height, in label heights
export function edgeShapes(edges) {
  const groups = new Map();
  edges.forEach((e, i) => {
    const k = e.s === e.o ? `loop\u0000${e.s}` : e.s < e.o ? `${e.s}\u0000${e.o}` : `${e.o}\u0000${e.s}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(i);
  });
  const shapes = edges.map(() => ({ bend: 0 }));
  for (const list of groups.values()) {
    list.forEach((i, j) => {
      const e = edges[i];
      shapes[i] = e.s === e.o ? { loop: j } : { bend: (j - (list.length - 1) / 2) * BEND * (e.s < e.o ? 1 : -1) };
    });
  }
  return shapes;
}

// The edges whose labels are left out: one label on many edges at one node - thirty students who
// :attends :KG - shows on the LABELS_AT edges most students named, not on every one, where they
// would lie on one another around the node. The same in every window: no positions involved.
const LABELS_AT = 3;
export function repeatedLabels(edges) {
  const groups = new Map();
  edges.forEach((e, i) => {
    if (!e.label) return;
    for (const k of [`s\u0000${e.s}\u0000${e.label}`, `o\u0000${e.o}\u0000${e.label}`]) {
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(i);
    }
  });
  const left = new Set();
  for (const list of groups.values()) {
    if (list.length <= LABELS_AT) continue;
    for (const i of [...list].sort((a, b) => (edges[b].n || 1) - (edges[a].n || 1) || a - b).slice(LABELS_AT)) left.add(i);
  }
  return left;
}

// An edge's path from node a to node b (centres in viewBox units; label boxes {w, h}), leaving
// and entering the labels at their rims, where its label goes first and - but for a loop - its
// point t of the way (placeLabels): {d, lx, ly, at}.
const fx = (v) => v.toFixed(1);
export function edgePath(a, b, na, nb, shape) {
  if (shape.loop !== undefined) {
    const half = Math.min(na.w / 4, 22), top = a[1] - na.h / 2, L = na.h * loopHeight(shape.loop);
    const x0 = a[0] - half, x1 = a[0] + half, c = top - L;
    return { d: `M${fx(x0)},${fx(top)} C${fx(x0 - 0.6 * L)},${fx(c)} ${fx(x1 + 0.6 * L)},${fx(c)} ${fx(x1)},${fx(top)}`,
      lx: a[0], ly: top - 0.75 * L - 6 };
  }
  const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1, bend = shape.bend || 0;
  const c = [(a[0] + b[0]) / 2 - (dy / len) * 2 * bend, (a[1] + b[1]) / 2 + (dx / len) * 2 * bend];
  const rim = (p, n) => {                                       // where the way to the curve's handle leaves a label
    const ux = c[0] - p[0], uy = c[1] - p[1];
    const t = Math.min(Math.abs(n.w / 2 / (ux || 1e-9)), Math.abs(n.h / 2 / (uy || 1e-9)));
    return t < 1 ? [p[0] + ux * t, p[1] + uy * t] : p;          // (labels on one another: from the middles)
  };
  const p = rim(a, na), q = rim(b, nb);
  if (!bend) {
    return { d: `M${fx(p[0])},${fx(p[1])} L${fx(q[0])},${fx(q[1])}`, lx: (p[0] + q[0]) / 2, ly: (p[1] + q[1]) / 2 - 6,
      at: (t) => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t] };
  }
  return { d: `M${fx(p[0])},${fx(p[1])} Q${fx(c[0])},${fx(c[1])} ${fx(q[0])},${fx(q[1])}`,
    lx: (p[0] + 2 * c[0] + q[0]) / 4, ly: (p[1] + 2 * c[1] + q[1]) / 4 - 6,
    at: (t) => [(1 - t) ** 2 * p[0] + 2 * (1 - t) * t * c[0] + t * t * q[0], (1 - t) ** 2 * p[1] + 2 * (1 - t) * t * c[1] + t * t * q[1]] };
}

// The edges' labels apart. A label tries the spots along its edge (at(t): the edge's point t of
// the way) - its middle, above the line and below, then a little to either side, beside it, and
// further along - and takes the first that lies inside the box, on no node's label and on no
// label placed before; the labels of the edges most students sent are placed first. A loop's label
// (no at) has its one spot (x, y). A label with no free spot is left out (null) - rather than on
// another. The spots follow from where the nodes are, not from where the labels were: the windows
// put a label where the others do. Boxes [x0, y0, x1, y1] in viewBox units; a label {w, h: its font
// size, n, at | x, y} stands on its baseline, centred. -> per label {x, y, spot} | null
export const SPOTS = [[0.5, "above"], [0.5, "below"], [0.4, "above"], [0.6, "above"], [0.4, "below"], [0.6, "below"],
  [0.5, "right"], [0.5, "left"], [0.3, "above"], [0.7, "above"], [0.3, "below"], [0.7, "below"]];
export function spotOffset(side, w, h) {                         // the baseline's middle from the edge's point
  return side === "above" ? [0, -6] : side === "below" ? [0, 0.8 * h + 6]
    : [(side === "right" ? 1 : -1) * (w / 2 + 8), 0.3 * h];
}
export const labelBox = (x, y, w, h) => [x - w / 2 - 3, y - 0.8 * h - 2, x + w / 2 + 3, y + 0.25 * h + 2];
export function placeLabels(labels, obstacles, [W, H]) {
  const taken = [...obstacles];
  const free = (b) => b[0] >= 0 && b[1] >= 0 && b[2] <= W && b[3] <= H &&
    !taken.some((o) => b[0] < o[2] && o[0] < b[2] && b[1] < o[3] && o[1] < b[3]);
  const order = labels.map((l, i) => i).sort((i, j) => (labels[j].n || 1) - (labels[i].n || 1) || i - j);
  const out = labels.map(() => null);
  for (const i of order) {
    const l = labels[i];
    for (let k = 0; k < (l.at ? SPOTS.length : 1); k++) {
      let x = l.x, y = l.y;
      if (l.at) {
        const [t, side] = SPOTS[k], p = l.at(t), o = spotOffset(side, l.w, l.h);
        x = p[0] + o[0];
        y = p[1] + o[1];
      }
      const b = labelBox(x, y, l.w, l.h);
      if (!free(b)) continue;
      taken.push(b);
      out[i] = { x, y, spot: k };
      break;
    }
  }
  return out;
}

// The labels' boxes as fractions of the box (build() draws them this size): [width, the label's
// height, the loops' height above it] - a label with loops (a node's own edges, edgePath) with
// the room they and their labels take.
export function labelBoxes(nodes, edges, aspect) {
  const loops = new Map();
  for (const e of edges) if (e.s === e.o) loops.set(e.s, (loops.get(e.s) || 0) + 1);
  return nodes.map((nd) => {
    const s = labelSize(nd, nodes.length);
    const w = (0.58 * s * String(nd.label ?? nd.id).length + s) / 1000, h = (1.5 * s * aspect) / 1000;
    const k = loops.get(nd.id) || 0;
    if (!k) return [w, h, 0];
    const L = 1.5 * s * loopHeight(k - 1);                      // the largest loop (viewBox units)
    return [Math.max(w, (2 * Math.min(250 * w, 22) + 0.9 * L) / 1000), h, ((0.75 * L + 24) * aspect) / 1000];
  });
}

// The crowd graph's layout, a force simulation that runs - as d3-force's, cut to a graph of at most
// 40 labels: labels repel each other, edges pull their ends together like springs, a pull towards
// the middle - the stronger the more labels - keeps parts from drifting to the rim, and labels that
// overlap are pushed apart, the shorter way. Positions in a box `aspect` wide and 1 high. A step
// moves every label by its velocity; the heat (alpha) scales the forces and cools from step to
// step, so that the graph comes to rest - from cold in STEPS steps, five seconds at sixty frames a
// second. What changes heats it again: a new label (HEAT.node) more than a new edge (HEAT.edge); a
// count alone does not - grown labels are only pushed apart. An edge's label (the ones repeatedLabels
// leaves) takes room too: the other labels keep off its edge, and the edge stays long enough to hold
// it between its ends - room for placeLabels; labels apart come first, though (collide). Arithmetic
// and square roots only: the same steps give the same places in every browser. The presenter window
// with the lease steps it once a frame and sends the places; the other windows move their labels
// there (ActivityBox).
const STEPS = 300;
const ALPHA_MIN = 0.002, ALPHA_DECAY = 1 - ALPHA_MIN ** (1 / STEPS);
const HEAT = { cold: 1, node: 0.3, edge: 0.2 };
// (tuned 2026-10-18 on graphs of 12 to 40 labels and a class's star - 28 students :attends :KG:
// none on another at rest, at most two labels against the rim, about 60 % of the box used)
const REPEL = 0.02, SPRING = 0.05, LENGTH = 0.75, GRAVITY = 0.012, DECAY = 0.5, COLLIDE = 0.5;
const TAG_H = 22;           // an edge's label with its gap to the line, viewBox units (placeLabels' "above")

export class ForceLayout {
  constructor(aspect = 1.6) {
    this.aspect = aspect;
    this.ids = [];
    this.at = new Map();          // id -> {x, y, vx, vy}
    this.links = [];              // [i, j]: an edge between two labels
    this.tags = [];               // {i, j, w, bend}: an edge's label - its width, its curve's bend
    this.box = [];                // labelBoxes
    this.shape = null;            // the labels and edges (JSON), and their counts: what changed
    this.counts = null;
    this.alpha = 0;
  }

  // The picture's graph. A label that is there keeps its place and speed; one the simulation does
  // not know takes its place from prev (id -> [x, y], fractions: the places the window got) or
  // starts next to a neighbour that has one. Whether anything changed.
  update(nodes, edges, prev = new Map()) {
    const { aspect } = this;
    const ids = nodes.map((nd) => nd.id);
    const index = new Map(ids.map((id, i) => [id, i]));
    const near = new Map(ids.map((id) => [id, []]));
    for (const e of edges) {
      near.get(e.s)?.push(e.o);
      near.get(e.o)?.push(e.s);
    }
    const at = new Map();
    for (const id of ids) {
      if (this.at.has(id)) at.set(id, this.at.get(id));
      else if (prev.has(id)) at.set(id, { x: prev.get(id)[0] * aspect, y: prev.get(id)[1], vx: 0, vy: 0 });
    }
    const cold = at.size === 0;
    let fresh = 0;
    for (const id of ids) {
      if (at.has(id)) continue;
      fresh += 1;
      const by = near.get(id).find((o) => at.has(o));
      const hx = hash01(`x:${id}`), hy = hash01(`y:${id}`);
      const p = by ? { x: at.get(by).x + (hx - 0.5) * 0.1, y: at.get(by).y + (hy - 0.5) * 0.1 }
        : { x: (0.2 + 0.6 * hx) * aspect, y: 0.2 + 0.6 * hy };
      at.set(id, { ...p, vx: 0, vy: 0 });
    }
    const links = [], tags = [], shapes = edgeShapes(edges), unlabelled = repeatedLabels(edges);
    edges.forEach((e, k) => {
      const i = index.get(e.s), j = index.get(e.o);
      if (i === undefined || j === undefined || i === j) return;
      links.push([i, j]);
      if (e.label && !unlabelled.has(k)) {
        const w = 0.58 * ELABEL * String(e.label).length + 6;   // (as the box measures one it cannot)
        tags.push({ i, j, w: (w * aspect) / 1000, bend: ((shapes[k].bend || 0) * aspect) / 1000 });
      }
    });
    const shape = JSON.stringify([ids, links]), counts = JSON.stringify(nodes.map((nd) => nd.n));
    let heat = cold ? HEAT.cold : fresh ? HEAT.node : this.shape !== null && shape !== this.shape ? HEAT.edge : 0;
    const grown = this.counts !== null && counts !== this.counts;
    const first = this.shape === null;
    Object.assign(this, { ids, at, links, tags, shape, counts, box: labelBoxes(nodes, edges, aspect) });
    if (first && !heat && this.collide(ids.map((id) => at.get(id)), 0, 0.01, false)) heat = HEAT.node;   // labels on one another
    this.alpha = Math.max(this.alpha, heat);
    if (!heat && grown && this.alpha === 0) {                   // a count alone: grown labels apart, at once
      const P = ids.map((id) => at.get(id));
      for (let r = 0; r < 30 && this.collide(P, 1); r++);
      for (let r = 0; r < 30 && this.collide(P, 1, 0, false); r++);
    }
    return heat > 0 || grown;
  }

  get resting() {
    return this.alpha === 0;
  }

  step() {
    const { ids, at, links, aspect } = this, n = ids.length;
    if (!n || this.alpha === 0) {
      this.alpha = 0;
      return;
    }
    const a = this.alpha, P = ids.map((id) => at.get(id));
    const repel = (REPEL * aspect * a) / n;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = P[i].x - P[j].x, dy = P[i].y - P[j].y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1e-8) {
          dx = (i - j) * 1e-3;
          dy = 1e-3;
          d2 = dx * dx + dy * dy;
        }
        const f = repel / Math.max(d2, 4e-4);
        P[i].vx += dx * f; P[i].vy += dy * f;
        P[j].vx -= dx * f; P[j].vy -= dy * f;
      }
    }
    const length = LENGTH * Math.sqrt(aspect / n);
    for (const [i, j] of links) {
      const dx = P[j].x - P[i].x, dy = P[j].y - P[i].y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1e-6;
      const f = ((d - length) / d) * SPRING * a;
      P[i].vx += dx * f; P[i].vy += dy * f;
      P[j].vx -= dx * f; P[j].vy -= dy * f;
    }
    const g = GRAVITY * (4 + n / 10) * a;
    P.forEach((p, i) => {
      p.vx = (p.vx + (aspect / 2 - p.x) * g) * (1 - DECAY);
      p.vy = (p.vy + (0.5 - p.y) * g) * (1 - DECAY);
      p.x += p.vx;
      p.y += p.vy;
      this.inside(p, i);
    });
    this.collide(P, COLLIDE);
    this.alpha -= this.alpha * ALPHA_DECAY;
    if (this.alpha < ALPHA_MIN) {
      this.alpha = 0;
      for (let r = 0; r < 60 && this.collide(P, 1); r++);       // at rest: no label on another, and
      for (let r = 0; r < 60 && this.collide(P, 1, 0, false); r++);   // ... none for an edge's label's room
    }
  }

  inside(p, i) {
    const [w, h, up] = this.box[i], { aspect } = this;
    const x = clamp(p.x, (w / 2 + 0.01) * aspect, (1 - w / 2 - 0.01) * aspect);
    const y = clamp(p.y, h / 2 + up + 0.02, 1 - h / 2 - 0.02);
    if (x !== p.x) { p.x = x; p.vx = 0; }
    if (y !== p.y) { p.y = y; p.vy = 0; }
  }

  collide(P, strength, slack = 0, room = true) {
    // labels on one another (more than `slack` - a fraction of the box) pushed apart, the shorter
    // way - last, so that the room the edges' labels take (room) puts none on another; whether
    // there were any
    const { box: B, aspect } = this, n = P.length;
    const mid = (i) => P[i].y - B[i][2] / 2;                    // the middle of a label with its loops
    let any = false;
    // an edge's label: its edge long enough to hold it between the ends' labels, and its way - from
    // 15 % to 85 % of it, where placeLabels looks - free of the other labels to a label's height on
    // either side; they move off it, square to it
    const th = (TAG_H * aspect) / 1000, pad = (6 * aspect) / 1000;
    for (const { i, j, w, bend } of room ? this.tags : []) {
      const dx = P[j].x - P[i].x, dy = P[j].y - P[i].y, d = Math.sqrt(dx * dx + dy * dy) || 1e-6;
      const ux = Math.abs(dx / d) || 1e-9, uy = Math.abs(dy / d) || 1e-9;
      const rim = (k) => Math.min((B[k][0] * aspect) / 2 / ux, B[k][1] / 2 / uy);
      const short = rim(i) + rim(j) + 2 * Math.min(w / 2 / ux, th / uy) + pad - d;
      if (short > slack) {
        any = true;
        const s = (strength * short) / 2 / d;
        P[i].x -= dx * s; P[i].y -= dy * s;
        P[j].x += dx * s; P[j].y += dy * s;
      }
      const nx = -dy / d, ny = dx / d;                           // square to the edge, the side its curve bends to
      for (let k = 0; k < n; k++) {
        if (k === i || k === j) continue;
        const qx = P[k].x - P[i].x, qy = mid(k) - P[i].y, t = (qx * dx + qy * dy) / (d * d);
        if (t < 0.15 || t > 0.85) continue;
        const off = qx * nx + qy * ny - 4 * t * (1 - t) * bend;  // from the curve (edgePath's: bend off at its middle)
        const lack = (Math.abs(nx) * B[k][0] * aspect + Math.abs(ny) * (B[k][1] + B[k][2])) / 2 + th - Math.abs(off);
        if (lack <= slack) continue;
        any = true;
        const s = (off < 0 ? -1 : 1) * strength * lack;
        P[k].x += nx * s; P[k].y += ny * s;
      }
    }
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const ox = ((B[i][0] + B[j][0]) / 2 + 0.006) * aspect - Math.abs(P[i].x - P[j].x);
        const oy = (B[i][1] + B[i][2] + B[j][1] + B[j][2]) / 2 + 0.01 - Math.abs(mid(i) - mid(j));
        if (ox <= slack * aspect || oy <= slack) continue;
        any = true;
        if (ox < oy) {
          const s = ((P[i].x < P[j].x || (P[i].x === P[j].x && i < j) ? -1 : 1) * strength * ox) / 2;
          P[i].x += s; P[j].x -= s;
        } else {
          const s = ((mid(i) < mid(j) || (mid(i) === mid(j) && i < j) ? -1 : 1) * strength * oy) / 2;
          P[i].y += s; P[j].y -= s;
        }
      }
    }
    P.forEach((p, i) => this.inside(p, i));
    return any;
  }

  // the places as fractions of the box (what the windows share)
  places() {
    return new Map(this.ids.map((id) => {
      const p = this.at.get(id);
      return [id, [Math.round((p.x / this.aspect) * 1e4) / 1e4, Math.round(p.y * 1e4) / 1e4]];
    }));
  }
}

// The layout at rest at once: a window without places from the presenter's (and the tests).
export function layoutGraph(nodes, edges, prev = new Map(), aspect = 1.6) {
  const sim = new ForceLayout(aspect);
  sim.update(nodes, edges, prev);
  for (let k = 0; k < 4 * STEPS && !sim.resting; k++) sim.step();
  return sim.places();
}

// The box's words in the deck's language (deck.json's "language", which Stage gives the box, and the
// presenter window its panel; i18n's "box"): German for a German deck, English for any other. A code
// activity's contributions are queries - Turtle texts and their graphs for engine=turtle (code).
export function boxWords(language) {
  return texts(language).box;
}

// what the windows call a code activity's contributions and results, in the deck's language
export function codeWords(item, language) {
  return boxWords(language).code[item?.engine === "turtle" ? "turtle" : "query"];
}

// a result's short name: "11 rows", "yes", "7 triples" - or what went wrong
export function resultLabel(c, language) {
  const w = boxWords(language);
  if (c.status !== "ok") return w.status[c.status] || c.status;
  const s = c.summary || {};
  if (s.kind === "ask") return s.boolean ? w.yes : w.no;
  if (typeof s.count === "number") return s.kind === "graph" ? w.triples(s.count) : w.rows(s.count);
  return w.result;
}

export function resultTable(s, rows = 8, language) {
  // a result's first rows as a table (text only)
  if (!s) return "";
  const w = boxWords(language);
  if (s.kind === "ask") return `<div class="tq-answer">${s.boolean ? w.yes : w.no}</div>`;
  const cols = s.columns || (s.kind === "graph" ? w.graph : []);
  const body = (s.rows || []).slice(0, rows).map((r) => `<tr>${r.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("");
  const more = (s.count ?? 0) - Math.min(rows, (s.rows || []).length);
  return `<table class="tq-result"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${body}</tbody></table>${more > 0 ? `<div class="tq-more">${w.more(more)}</div>` : ""}`;
}

export class ActivityBox {
  constructor({ id, item, layer, host = {}, language = "" }) {
    this.id = id;
    this.item = item;
    this.host = host;
    this.language = language;      // the deck's: the box's words (boxWords)
    this.words = boxWords(language);
    this.el = Object.assign(document.createElement("div"), { className: "tq-activity" });
    layer.append(this.el);
    this.want = "";                // the version and layout the state names
    this.seen = "";                // ... and those of the picture drawn
    this.busy = false;
    this.fetched = -Infinity;
    this.timer = null;
    this.picture = null;
    this.aspect = 16 / 9;
    this.at = new Map();           // the nodes where they are drawn (fractions of the box)
    this.target = new Map();       // ... and where they go
    this.own = new Map();          // the positions this window laid out (it has the lease)
    this.sim = null;               // ... and its simulation (ForceLayout)
    this.ticked = -Infinity;       // the last frame (tick)
    this.nodes = new Map();        // id -> {g, w, h}
    this.edges = [];               // {e, line, text, w, lab, shape}
    this.labels = new Map();       // an edge's label (s, o, label) -> where it is drawn: {t, dx, dy, off}
    this.gliding = false;          // a label on its way to another spot
    host.agent?.attach(this);
  }

  place(rects) {
    const r = rects.box;
    if (!r) return;
    const css = `left:${pct(r.x)};top:${pct(r.y)};width:${pct(r.w)};height:${pct(r.h)}`;
    if (css === this.css) return;
    this.css = css;
    this.el.style.cssText = css;
    this.aspect = (r.w / r.h) * slideAspect();
    this.draw();
  }

  update(state) {
    const st = state?.stage?.activity?.items?.[this.id];
    this.want = st ? `${st.version}.${st.layout}` : "";
    if (this.want && this.want !== this.seen) this.fetch();
  }

  fetch() {
    if (this.busy || this.gone || !this.host.read) return;
    const wait = FETCH_MS - (performance.now() - this.fetched);
    if (wait > 0) {
      this.timer ??= setTimeout(() => { this.timer = null; this.fetch(); }, wait);
      return;
    }
    this.busy = true;
    this.fetched = performance.now();
    const want = this.want;
    this.host.read({ t: "activity.view", activity: this.id }).then((r) => {
      this.busy = false;
      if (this.gone) return;
      this.seen = want;
      this.picture = r.picture;
      this.draw();
      if (this.want !== this.seen) this.fetch();
    }, () => { this.busy = false; });
  }

  draw() {
    const p = this.picture;
    if (!p || this.gone) return;
    if (p.kind === "clusters") this.drawClusters(p);
    else this.drawGraph(p);
  }

  // ------------------------------------------------------------------ the crowd graph
  drawGraph(p) {
    // the graph is laid out and built anew only when it changed - new positions alone (the layout
    // coming back, or from the window with the lease) move the nodes that are there
    const shape = JSON.stringify([p.nodes.map((n) => [n.id, n.label, n.n]), p.edges.map((e) => [e.s, e.o, e.label, e.n]),
      this.aspect.toFixed(3)]);
    const changed = shape !== this.shape;
    const agent = this.host.agent;
    // without frames - a window minimised, hidden behind others or in the background gets none -
    // nothing steps the simulation or glides the nodes: laid out at rest and drawn there at once
    const frameless = performance.now() - this.ticked > FRAMELESS_MS;
    if (agent?.leads()) {                                // this window lays out, for every window
      if (!this.sim || this.sim.aspect !== this.aspect) this.sim = new ForceLayout(this.aspect);
      if (changed || !this.own.size) {
        this.sim.update(p.nodes, p.edges, this.own.size ? this.own : new Map(Object.entries(p.at || {})));
        if (frameless) for (let k = 0; k < 4 * STEPS && !this.sim.resting; k++) this.sim.step();
        this.own = this.sim.places();
        agent.layout(this.id, this.own);
      }
      this.target = new Map(this.own);                   // (tick steps it while it is not at rest)
    } else {
      this.sim = null;                                   // (with the lease again: from the places sent)
      const given = new Map(Object.entries(p.at || {}));
      if (p.nodes.every((n) => given.has(n.id))) this.target = given;
      else if (changed) this.target = layoutGraph(p.nodes, p.edges, new Map([...this.target, ...given]), this.aspect);
    }
    for (const [id, xy] of this.target) if (frameless || !this.at.has(id)) this.at.set(id, [...xy]);
    if (changed) {
      this.shape = shape;
      this.build(p);
    }
    this.gliding = this.placeAll(frameless);
  }

  build(p) {
    const H = 1000 / this.aspect;
    const before = new Set(this.nodes.keys());
    const fresh = (id) => (before.size && !before.has(id) ? " tq-new" : "");
    const size = (n) => labelSize(n, p.nodes.length);
    this.el.innerHTML = `<svg class="tq-graph" xmlns="${SVG}" viewBox="0 0 1000 ${H.toFixed(1)}" preserveAspectRatio="none">
      <defs><marker id="tq-arrow-${esc(this.id)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="16" markerHeight="16"
        markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="tq-arrowhead"/></marker></defs>
      <g class="tq-edges"></g><g class="tq-elabels"></g><g class="tq-nodes"></g></svg>
      ${p.nodes.length ? "" : `<div class="tq-empty">${p.phase === "open" ? this.words.noTriplesYet : this.words.noTriples}</div>`}
      ${p.more ? `<div class="tq-more">${this.words.more(p.more)}</div>` : ""}`;
    const edgesG = this.el.querySelector(".tq-edges");
    const labelsG = this.el.querySelector(".tq-elabels");         // (over every edge, so that none crosses one)
    const nodesG = this.el.querySelector(".tq-nodes");
    const shapes = edgeShapes(p.edges), unlabelled = repeatedLabels(p.edges);
    const labels = new Map();
    this.edges = p.edges.map((e, i) => {
      const line = document.createElementNS(SVG, "path");
      line.setAttribute("class", `tq-edge${fresh(e.s) || fresh(e.o)}`);
      line.setAttribute("stroke-width", (2 + 2 * Math.log2(e.n)).toFixed(1));
      line.setAttribute("marker-end", `url(#tq-arrow-${this.id})`);
      edgesG.append(line);
      let text = null, w = 0, lab = null;
      if (e.label && !unlabelled.has(i)) {
        text = document.createElementNS(SVG, "text");
        text.setAttribute("class", `tq-elabel${fresh(e.s) || fresh(e.o)}`);
        text.textContent = e.label;
        labelsG.append(text);
        try { w = text.getBBox().width; } catch { w = 0; }
        if (!w) w = 0.58 * ELABEL * e.label.length;
        const key = `${e.s}\u0000${e.o}\u0000${e.label}`;
        lab = this.labels.get(key) || {};                // (a label that was there stays where it was drawn)
        if (lab.off) text.classList.add("tq-off");
        labels.set(key, lab);
      }
      return { e, line, text, w, lab, shape: shapes[i] };
    });
    this.labels = labels;
    this.nodes = new Map();
    for (const n of p.nodes) {
      const g = document.createElementNS(SVG, "g");
      g.setAttribute("class", `tq-node${n.literal ? " tq-literal" : ""}${fresh(n.id)}`);   // (a literal: a box, as on the slides)
      const rect = document.createElementNS(SVG, "rect");
      const text = document.createElementNS(SVG, "text");
      const px = size(n);
      text.setAttribute("font-size", px.toFixed(1));
      text.textContent = n.label;
      g.append(rect, text);
      nodesG.append(g);
      let w;
      try { w = text.getBBox().width; } catch { w = 0; }
      if (!w) w = 0.58 * px * n.label.length;            // (a hidden window measures nothing)
      const h = px * 1.5;
      w += px;
      rect.setAttribute("x", (-w / 2).toFixed(1));
      rect.setAttribute("y", (-h / 2).toFixed(1));
      rect.setAttribute("width", w.toFixed(1));
      rect.setAttribute("height", h.toFixed(1));
      rect.setAttribute("rx", n.literal ? "0" : (h / 2).toFixed(1));
      this.nodes.set(n.id, { g, w, h });
    }
  }

  placeAll(snap = false) {
    // the nodes where they are, the edges between them and their labels apart (placeLabels): a
    // label whose spot changes glides there along its edge (snap: a window without frames puts it
    // there at once), one without a free spot fades out; whether a label is still on its way
    const H = 1000 / this.aspect;
    const xy = (id) => {
      const p = this.at.get(id) || [0.5, 0.5];
      return [p[0] * 1000, p[1] * H];
    };
    const obstacles = [];
    for (const [id, n] of this.nodes) {
      const [x, y] = xy(id);
      n.g.setAttribute("transform", `translate(${x.toFixed(1)},${y.toFixed(1)})`);
      obstacles.push([x - n.w / 2, y - n.h / 2, x + n.w / 2, y + n.h / 2]);
    }
    const shown = [];
    for (const edge of this.edges) {
      const { e, line, text, shape } = edge;
      const a = this.nodes.get(e.s), b = this.nodes.get(e.o);
      if (!a || !b) continue;
      const g = edgePath(xy(e.s), xy(e.o), a, b, shape);
      line.setAttribute("d", g.d);
      if (text) shown.push({ edge, g, w: edge.w, h: ELABEL, n: e.n, at: g.at, x: g.lx, y: g.ly });
    }
    const spots = placeLabels(shown, obstacles, [1000, H]);
    let gliding = false;
    shown.forEach(({ edge, g }, i) => {
      const { text, lab } = edge;
      if (spots[i]) {
        const [t, side] = g.at ? SPOTS[spots[i].spot] : [0.5, "above"];
        const [dx, dy] = g.at ? spotOffset(side, edge.w, ELABEL) : [0, 0];
        if (snap || lab.off !== false || (Math.abs(t - lab.t) < 0.002 && Math.abs(dx - lab.dx) + Math.abs(dy - lab.dy) < 0.5)) {
          Object.assign(lab, { t, dx, dy });             // new, back or there: at its spot
        } else {
          lab.t += (t - lab.t) * GLIDE;
          lab.dx += (dx - lab.dx) * GLIDE;
          lab.dy += (dy - lab.dy) * GLIDE;
          gliding = true;
        }
        lab.off = false;
      } else if (lab.t !== undefined) lab.off = true;     // (fades out where it is)
      else Object.assign(lab, { t: 0.5, dx: 0, dy: -6, off: true });
      text.classList.toggle("tq-off", lab.off);
      const [x, y] = g.at ? g.at(lab.t) : [g.lx, g.ly];
      text.setAttribute("x", (x + lab.dx).toFixed(1));
      text.setAttribute("y", (y + lab.dy).toFixed(1));
    });
    return gliding;
  }

  tick() {
    this.ticked = performance.now();
    if (!this.nodes.size) return;
    const agent = this.host.agent;
    if (this.sim && !this.sim.resting && agent?.leads()) {
      // the window with the lease: a step of the simulation, drawn at once, sent at most twice a second
      this.sim.step();
      this.own = this.target = this.sim.places();
      for (const [id, xy] of this.own) this.at.set(id, [...xy]);
      agent.layout(this.id, this.own);
      this.gliding = this.placeAll();
      return;
    }
    // the other windows: the nodes glide to the places sent - slowly enough to fill the half
    // second until the next ones come, so that the graph moves on as the simulation does
    let moved = false;
    for (const [id, t] of this.target) {
      const a = this.at.get(id);
      if (!a) continue;
      const dx = t[0] - a[0], dy = t[1] - a[1];
      if (Math.abs(dx) + Math.abs(dy) < 2e-4) continue;
      a[0] += dx * 0.1;
      a[1] += dy * 0.1;
      moved = true;
    }
    if (moved || this.gliding) this.gliding = this.placeAll();
  }

  // ------------------------------------------------------------------ the clusters
  drawClusters(p) {
    const w = this.words, words = codeWords(this.item, this.language);
    const most = Math.max(1, ...p.clusters.map((c) => c.n));
    const rows = p.clusters.map((c) => `<div class="tq-cluster${c.reference ? " tq-ref" : ""}${c.status !== "ok" ? " tq-bad" : ""}">
        <span class="tq-clabel">${esc(resultLabel(c, this.language))}${c.reference ? " ✓" : ""}</span>
        <span class="tq-cbar"><i style="width:${((100 * c.n) / most).toFixed(1)}%"></i></span>
        <span class="tq-cn">${c.n}</span></div>`).join("");
    const shown = p.shown ? `<div class="tq-shown"><div class="tq-shownhead">${esc(resultLabel(p.shown, this.language))}
        · ${w.students(p.shown.n)}${p.shown.reference ? ` · ${words.reference} ✓` : ""}</div>
        <pre>${esc(p.shown.example)}</pre>${p.shown.status === "ok" ? resultTable(p.shown.summary, 8, this.language) : ""}</div>` : "";
    const head = `${w.students(p.students)}${p.waiting ? ` · ${w.waiting(p.waiting)}` : ""}`;
    this.el.innerHTML = `<div class="tq-clusters"><div class="tq-chead">${head}</div>
      ${rows || `<div class="tq-empty">${p.phase === "open" ? words.waiting : words.none}</div>`}
      ${p.others ? `<div class="tq-more">${w.others} · ${p.others}</div>` : ""}</div>${shown}`;
    this.nodes = new Map();
    this.shape = null;
  }

  key() {
    return false;
  }

  destroy() {
    this.gone = true;
    clearTimeout(this.timer);
    this.el.remove();
    this.host.agent?.detach(this);
  }
}

// The presenter window's agent for the deck's activities: it asks for the lease to evaluate and
// lay out (activity.work, every 5 s while one of the deck's activities is on a slide of this
// window or queries wait), tells the boxes whether this window lays out, and sends their
// positions. The evaluation of the queries (L4) hooks in at `jobs`.
export class ActivityAgent {
  constructor({ send }) {
    this.send = send;              // (msg) => a promise of the server's reply
    this.boxes = new Set();
    this.lease = false;
    this.asking = false;
    this.waiting = 0;
    this.sent = new Map();         // activity -> the positions last sent (JSON)
    this.due = new Map();          // activity -> {at, timer}
    this.jobs = null;              // (reply) => the evaluator takes the work (L4) - none where the server checks
    this.timer = setInterval(() => this.renew(), RENEW_MS);
  }

  attach(box) {
    this.boxes.add(box);
    this.renew();
  }

  detach(box) {
    this.boxes.delete(box);
  }

  leads() {
    return this.lease;
  }

  update(state) {
    const items = state?.stage?.activity?.items || {};
    const waiting = Object.values(items).reduce((n, st) => n + (st.waiting || 0), 0);
    const more = waiting > this.waiting;
    this.waiting = waiting;
    if (more) this.renew();
  }

  async renew() {
    if (this.gone || this.asking || (!this.boxes.size && !this.waiting)) return;
    this.asking = true;
    try {
      const r = await this.send({ t: "activity.work" });
      const had = this.lease;
      this.lease = Boolean(r.lease);
      if (this.lease !== had) for (const b of this.boxes) b.draw();   // now this window lays out, or not
      if (this.lease && this.jobs) this.jobs(r);
    } catch {
      this.lease = false;
    } finally {
      this.asking = false;
    }
  }

  layout(activity, positions) {
    const at = Object.fromEntries(positions);
    const text = JSON.stringify(at);
    if (text === this.sent.get(activity)) return;
    const due = this.due.get(activity) || { last: -Infinity, timer: null };
    due.at = at;
    due.text = text;
    this.due.set(activity, due);
    const go = () => {
      due.timer = null;
      due.last = performance.now();
      this.sent.set(activity, due.text);
      this.send({ t: "activity.layout", activity, at: due.at }).catch(() => this.sent.delete(activity));
    };
    const wait = LAYOUT_MS - (performance.now() - due.last);
    if (wait <= 0) go();
    else due.timer ??= setTimeout(go, wait);
  }

  destroy() {
    this.gone = true;
    clearInterval(this.timer);
    for (const d of this.due.values()) clearTimeout(d.timer);
    this.evaluator?.destroy();
  }
}
