// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The crowd graph's layout (web/stage/activity.js: ForceLayout, the simulation the presenter window
// runs, and layoutGraph, the same at rest at once): the same graph, the same places in every
// window; 40 labels - what the projector shows at most (server/activity.py) - inside the box and
// apart; the simulation comes to rest, a new label heats it and a count alone does not; a graph
// that changed nothing keeps its places, one that grows triple by triple moves but keeps its
// labels apart. And its edges (edgeShapes, edgePath): a triple whose subject is its object a loop
// above its node, with room kept for it; edges between the same two nodes curved apart. And the
// edges' labels (placeLabels): apart, on no node, inside the box, those most students sent first,
// left out rather than on another; the layout makes room for them.
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "../src/texstage/web");
const { edgePath, edgeShapes, ForceLayout, labelBox, labelBoxes, labelSize, layoutGraph, loopHeight, placeLabels, repeatedLabels } =
  await import(pathToFileURL(path.join(web, "stage/activity.js")).href);
const ASPECT = 1.55;

function graph(n) {
  // n nodes with names like the phones send, a sparse graph of a few parts
  const nodes = Array.from({ length: n }, (_, i) => ({ id: `:student${i}`, label: `:Student${i}`, n: 1 + (i % 4) }));
  const edges = Array.from({ length: Math.round(n * 0.9) }, (_, i) => ({ s: `:student${i}`, o: `:student${(i * 7 + 3) % n}` }))
    .filter((e) => e.s !== e.o);
  return { nodes, edges };
}

function boxes(nodes) {
  return nodes.map((nd) => {
    const s = labelSize(nd, nodes.length);
    return [(0.58 * s * nd.label.length + s) / 1000, (1.5 * s * ASPECT) / 1000];
  });
}

function overlaps(nodes, at) {
  const B = boxes(nodes);
  const P = nodes.map((nd) => at.get(nd.id));
  let k = 0;
  for (let i = 0; i < P.length; i++) {
    for (let j = i + 1; j < P.length; j++) {
      if (Math.abs(P[i][0] - P[j][0]) < (B[i][0] + B[j][0]) / 2 && Math.abs(P[i][1] - P[j][1]) < (B[i][1] + B[j][1]) / 2) k++;
    }
  }
  return k;
}

// how far a node went, the box's height the unit
const moved = ([x, y], [x2, y2]) => Math.hypot((x2 - x) * ASPECT, y2 - y);

test("the same graph, the same places", () => {
  const { nodes, edges } = graph(25);
  assert.deepEqual([...layoutGraph(nodes, edges, new Map(), ASPECT)], [...layoutGraph(nodes, edges, new Map(), ASPECT)]);
});

test("40 labels inside the box, none on another", () => {
  const { nodes, edges } = graph(40);
  const at = layoutGraph(nodes, edges, new Map(), ASPECT);
  const B = boxes(nodes);
  nodes.forEach((nd, i) => {
    const [x, y] = at.get(nd.id);
    assert.ok(x - B[i][0] / 2 >= 0 && x + B[i][0] / 2 <= 1 && y - B[i][1] / 2 >= 0 && y + B[i][1] / 2 <= 1, `${nd.id} in the box`);
  });
  const k = overlaps(nodes, at);
  assert.ok(k <= 6, `${k} labels on one another`);
});

test("a graph that changed nothing keeps its places; a new node comes next to its neighbour", () => {
  const { nodes, edges } = graph(12);
  const first = layoutGraph(nodes, edges, new Map(), ASPECT);
  const again = layoutGraph(nodes, edges, first, ASPECT);
  for (const [id, xy] of first) {
    const d = moved(xy, again.get(id));
    assert.ok(d < 0.05, `${id} stays (moved ${d.toFixed(3)})`);
  }
  const grown = layoutGraph([...nodes, { id: ":new", label: ":New", n: 1 }], [...edges, { s: ":new", o: ":student3" }], first, ASPECT);
  assert.ok(moved(grown.get(":new"), grown.get(":student3")) < 0.6, "next to its neighbour");
});

test("the simulation comes to rest; a new label heats it, a count alone does not", () => {
  const { nodes, edges } = graph(25);
  const sim = new ForceLayout(ASPECT);
  assert.equal(sim.update(nodes, edges), true);
  let steps = 0;
  for (; !sim.resting && steps < 1000; steps++) sim.step();
  assert.ok(steps <= 300, `from cold at rest after ${steps} steps`);
  const rest = sim.places();
  assert.equal(sim.update(nodes, edges), false, "nothing changed");
  assert.ok(sim.resting);
  const counted = nodes.map((nd, i) => (i === 4 ? { ...nd, n: nd.n + 9 } : nd));
  assert.equal(sim.update(counted, edges), true);
  assert.ok(sim.resting, "a count alone: no heat");
  for (const [id, xy] of rest) assert.ok(moved(xy, sim.places().get(id)) < 0.05, `${id} after a count`);
  sim.update([...counted, { id: ":new", label: ":New", n: 1 }], [...edges, { s: ":new", o: ":student3" }]);
  assert.ok(!sim.resting, "a new label heats it");
  const handover = new ForceLayout(ASPECT);                  // a window that gets the lease: from the places sent
  handover.update(nodes, edges, rest);
  assert.ok(handover.resting && [...rest].every(([id, xy]) => moved(xy, handover.places().get(id)) === 0));
});

test("a graph growing triple by triple moves, comes to rest after every triple, and keeps its labels apart", () => {
  // one simulation, as the presenter window runs it, every new picture into it
  const { nodes, edges } = graph(40);
  const sim = new ForceLayout(ASPECT);
  const seen = new Set();
  const moves = [];
  let at = new Map();
  for (let k = 0; k < edges.length; k++) {
    seen.add(edges[k].s);
    seen.add(edges[k].o);
    const shown = nodes.filter((nd) => seen.has(nd.id));
    sim.update(shown, edges.slice(0, k + 1));
    let steps = 0;
    for (; !sim.resting && steps < 1000; steps++) sim.step();
    assert.ok(steps <= 300, `at rest ${steps} steps after edge ${k}`);
    const next = sim.places();
    for (const [id, xy] of at) moves.push(moved(xy, next.get(id)));
    const o = overlaps(shown, next);
    assert.ok(o <= 3, `${o} labels on one another after edge ${k}`);
    at = next;
  }
  moves.sort((a, b) => a - b);
  assert.ok(moves[Math.floor(moves.length / 2)] < 0.1 && moves.at(-1) < 0.45,
    `the labels that were there: median ${moves[Math.floor(moves.length / 2)].toFixed(3)}, at most ${moves.at(-1).toFixed(3)}`);
});

test("a class's star - 28 students :attends :KG - at rest: labels apart, few against the rim, few labels on the edges", () => {
  const nodes = [{ id: ":KG", label: ":KG", n: 30 }, { id: ":Decker", label: ":Decker", n: 2 }, { id: ":RDF", label: ":RDF", n: 2 },
    ...Array.from({ length: 28 }, (_, i) => ({ id: `:s${i}`, label: `:Student${i}`, n: 1 }))];
  const edges = [{ s: ":Decker", o: ":KG", label: ":teaches", n: 2 }, { s: ":KG", o: ":RDF", label: ":isAbout", n: 2 },
    ...Array.from({ length: 28 }, (_, i) => ({ s: `:s${i}`, o: ":KG", label: ":attends", n: 1 + (i % 3) }))];
  const at = layoutGraph(nodes, edges, new Map(), ASPECT);
  assert.equal(overlaps(nodes, at), 0);
  const B = labelBoxes(nodes, edges, ASPECT);
  const rim = nodes.filter((nd, i) => {
    const [x, y] = at.get(nd.id), [w, h, up] = B[i];
    return x - w / 2 < 0.012 || x + w / 2 > 0.988 || y - h / 2 - up < 0.022 || y + h / 2 > 0.978;
  });
  assert.ok(rim.length <= 3, `${rim.length} labels against the rim`);
  const left = repeatedLabels(edges);
  assert.equal(left.size, 25, "the :attends label on three of the 28 edges");
  assert.ok(!left.has(0) && !left.has(1), "the other labels all shown");
  const kept = edges.map((e, i) => i).filter((i) => edges[i].label === ":attends" && !left.has(i));
  assert.deepEqual(kept.map((i) => edges[i].n), [3, 3, 3], "on the edges most students named");
});

test("a node's own edge is a loop above it; edges between the same two nodes curve apart", () => {
  const edges = [{ s: ":a", o: ":a" }, { s: ":a", o: ":a" }, { s: ":a", o: ":b" }, { s: ":b", o: ":a" }, { s: ":b", o: ":c" }];
  const shapes = edgeShapes(edges);
  assert.deepEqual(shapes.map((x) => x.loop), [0, 1, undefined, undefined, undefined]);
  assert.equal(shapes[4].bend, 0, "one edge between two nodes is straight");
  const A = [300, 200], B = [600, 200], box = { w: 80, h: 30 };
  assert.match(edgePath(B, [800, 200], box, box, shapes[4]).d, /^M[\d.,]+ L[\d.,]+$/);
  const ab = edgePath(A, B, box, box, shapes[2]), ba = edgePath(B, A, box, box, shapes[3]);
  assert.match(ab.d, /^M[\d.,]+ Q[\d.,]+ [\d.,]+$/);
  assert.ok(Math.abs(ab.ly - ba.ly) >= 30, `the two labels apart (${ab.ly.toFixed(1)}, ${ba.ly.toFixed(1)})`);
  const l0 = edgePath(A, A, box, box, shapes[0]), l1 = edgePath(A, A, box, box, shapes[1]);
  assert.match(l0.d, /^M[\d.,]+ C[\d.,]+ [\d.,]+ [\d.,]+$/);
  assert.ok(l0.ly < A[1] - box.h / 2 && l1.ly < l0.ly, `the loops' labels above the node, the second higher (${l0.ly}, ${l1.ly})`);
  assert.equal(l0.lx, A[0]);
});

test("a node with a loop keeps room above it: no other label in the loop", () => {
  const nodes = [{ id: ":t", label: ":test", n: 1 }, ...Array.from({ length: 14 }, (_, i) => ({ id: `:n${i}`, label: `:Node${i}`, n: 1 }))];
  const edges = [{ s: ":t", o: ":t" }, ...nodes.slice(1).map((nd, i) => ({ s: i % 2 ? ":t" : nd.id, o: i % 2 ? nd.id : ":t" }))];
  const at = layoutGraph(nodes, edges, new Map(), ASPECT);
  const B = boxes(nodes);
  const s = labelSize(nodes[0], nodes.length), L = 1.5 * s * loopHeight(0);
  const [tx, ty] = at.get(":t");
  const w = Math.max(B[0][0], (2 * Math.min(250 * B[0][0], 22) + 0.9 * L) / 1000);
  const loop = [tx - w / 2, tx + w / 2, ty - B[0][1] / 2 - ((0.75 * L + 24) * ASPECT) / 1000, ty - B[0][1] / 2];
  nodes.slice(1).forEach((nd, i) => {
    const [x, y] = at.get(nd.id);
    const b = B[i + 1];
    const inside = x + b[0] / 2 > loop[0] && x - b[0] / 2 < loop[1] && y + b[1] / 2 > loop[2] && y - b[1] / 2 < loop[3];
    assert.ok(!inside, `${nd.id} is not in :test's loop`);
  });
});

// ------------------------------------------------------------------ the edges' labels
const hit = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
const straight = (a, b) => edgePath(a, b, { w: 60, h: 24 }, { w: 60, h: 24 }, { bend: 0 }).at;

test("an edge's label stands above its edge's middle; one that would lie on another moves along its edge", () => {
  // two edges crossing at their middles (500, 300)
  const labels = [{ w: 80, h: 17, n: 2, at: straight([300, 300], [700, 300]) }, { w: 80, h: 17, n: 1, at: straight([500, 120], [500, 480]) }];
  const [a, b] = placeLabels(labels, [], [1000, 650]);
  assert.equal(a.spot, 0);
  assert.equal(a.x, 500);
  assert.ok(a.y < 300 && a.y > 280, `above the line, close to it (${a.y})`);
  assert.notEqual(b.spot, 0);
  assert.ok(!hit(labelBox(a.x, a.y, 80, 17), labelBox(b.x, b.y, 80, 17)), "the two apart");
  assert.deepEqual(placeLabels(labels, [], [1000, 650]), [a, b], "the same places, the same spots");
});

test("the label of the edge most students sent takes the middle", () => {
  const labels = [{ w: 80, h: 17, n: 1, at: straight([300, 300], [700, 300]) }, { w: 80, h: 17, n: 5, at: straight([500, 120], [500, 480]) }];
  const [a, b] = placeLabels(labels, [], [1000, 650]);
  assert.equal(b.spot, 0);
  assert.notEqual(a.spot, 0);
});

test("a label with no free spot is left out; none on a node's label or outside the box", () => {
  const at = straight([300, 300], [700, 300]);
  assert.deepEqual(placeLabels([{ w: 80, h: 17, at }], [[0, 0, 1000, 650]], [1000, 650]), [null], "nodes everywhere");
  const [nodeOn] = placeLabels([{ w: 80, h: 17, at }], [[440, 260, 560, 299]], [1000, 650]);
  assert.ok(nodeOn.spot > 0 && !hit(labelBox(nodeOn.x, nodeOn.y, 80, 17), [440, 260, 560, 299]), "away from the node's label");
  const [top] = placeLabels([{ w: 80, h: 17, at: straight([300, 10], [700, 10]) }], [], [1000, 650]);
  assert.equal(top.spot, 1, "an edge along the top: its label below it");
  // a loop's label has its one spot
  assert.deepEqual(placeLabels([{ w: 60, h: 17, x: 500, y: 200 }], [], [1000, 650]), [{ x: 500, y: 200, spot: 0 }]);
  assert.deepEqual(placeLabels([{ w: 60, h: 17, x: 500, y: 200 }], [[480, 180, 520, 220]], [1000, 650]), [null]);
});

function lectureGraph(students) {
  // what a class sends: a core of the lecture's names - the triples many students sent - and a star
  // of students who :attends :KG
  const core = [[":Decker", ":teaches", ":KG", 8], [":KG", ":hasLecturer", ":Decker", 3], [":Decker", ":worksAt", ":RWTH", 6],
    [":KG", ":isAbout", ":RDF", 6], [":KG", ":isAbout", ":SPARQL", 5], [":KG", ":isAbout", ":Ontologies", 4],
    [":SPARQL", ":queries", ":RDF", 3], [":KG", ":takesPlaceIn", ":Aachen", 3], [":KG", ":isTaughtAt", ":RWTH", 2],
    [":RWTH", ":locatedIn", ":Aachen", 2], [":RDF", ":isA", ":DataModel", 2], [":Ada", ":knows", ":Bob", 1]];
  const edges = [...core.map(([s, label, o, n]) => ({ s, o, label, n })),
    ...Array.from({ length: students }, (_, i) => ({ s: `:Student${i}`, o: ":KG", label: ":attends", n: 1 }))];
  const count = new Map();
  for (const e of edges) for (const t of [e.s, e.o]) count.set(t, (count.get(t) || 0) + e.n);
  return { nodes: [...count].map(([id, n]) => ({ id, label: id, n })), edges };
}

function placed(nodes, edges, at) {
  // what ActivityBox.placeAll does - the labels' widths as the layout guesses them
  const H = 1000 / ASPECT, xy = (id) => [at.get(id)[0] * 1000, at.get(id)[1] * H];
  const box = new Map(nodes.map((nd) => {
    const s = labelSize(nd, nodes.length);
    return [nd.id, { w: 0.58 * s * nd.label.length + s, h: 1.5 * s }];
  }));
  const obstacles = nodes.map((nd) => {
    const [x, y] = xy(nd.id), b = box.get(nd.id);
    return [x - b.w / 2, y - b.h / 2, x + b.w / 2, y + b.h / 2];
  });
  const shapes = edgeShapes(edges), left = repeatedLabels(edges);
  const labels = [];
  edges.forEach((e, i) => {
    if (!e.label || left.has(i)) return;
    const g = edgePath(xy(e.s), xy(e.o), box.get(e.s), box.get(e.o), shapes[i]);
    labels.push({ e, w: 0.58 * 17 * e.label.length, h: 17, n: e.n, at: g.at, x: g.lx, y: g.ly });
  });
  const spots = placeLabels(labels, obstacles, [1000, H]);
  return { labels, spots, obstacles, boxes: spots.map((s, i) => s && labelBox(s.x, s.y, labels[i].w, labels[i].h)) };
}

test("a class's graph at rest: the edges' labels apart and on no node; the layout makes room, most are shown", () => {
  for (const students of [16, 24]) {
    const { nodes, edges } = lectureGraph(students);
    const { labels, spots, obstacles, boxes: B } = placed(nodes, edges, layoutGraph(nodes, edges, new Map(), ASPECT));
    const shown = B.filter(Boolean);
    shown.forEach((b, i) => {
      for (const o of obstacles) assert.ok(!hit(b, o), `${students}: a label on a node's label`);
      for (const c of shown.slice(i + 1)) assert.ok(!hit(b, c), `${students}: two labels on one another`);
    });
    const out = labels.filter((l, i) => !spots[i]);
    assert.ok(out.length <= 3, `${students}: ${out.length} of ${labels.length} left out`);
    assert.ok(out.every((l) => l.n <= 3), `${students}: left out ${out.map((l) => `${l.e.label} (${l.n})`).join(", ")}`);
    // the same graph laid out as if its edges had no labels: less room for them
    const bare = layoutGraph(nodes, edges.map(({ label, ...e }) => e), new Map(), ASPECT);
    const without = placed(nodes, edges, bare).spots.filter((s) => !s).length;
    assert.ok(without > out.length, `${students}: ${without} left out without room, ${out.length} with`);
  }
});
