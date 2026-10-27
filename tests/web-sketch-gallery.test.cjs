// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

// Run the production gallery's async synchronization with a small DOM double.
const source = fs.readFileSync(path.join(__dirname, '../src/texstage/web/stage/presenter.js'), 'utf8');
const syncSource = source.slice(source.indexOf('async function loadSketches()'), source.indexOf('function markGallery()'));
const tick = () => new Promise((resolve) => setImmediate(resolve));
const sketch = (n, player) => ({ n, player, strokes: [] });
const plain = (value) => JSON.parse(JSON.stringify(value));

function setup() {
  const grid = {
    tiles: [],
    set innerHTML(value) { assert.equal(value, ''); this.tiles = []; },
    querySelectorAll(selector) { assert.equal(selector, '[data-player]'); return [...this.tiles]; },
    insertAdjacentHTML(position, html) {
      assert.equal(position, 'beforeend');
      const player = html.match(/data-player="([^"]+)"/)[1];
      const tile = { dataset: { player }, remove: () => { this.tiles = this.tiles.filter((x) => x !== tile); } };
      this.tiles.push(tile);
    },
  };
  const g = { quiz: 'draw', round: null, cursor: 0, synced: null, loading: false, sketches: [], selected: [],
    el: { querySelector: (selector) => { assert.equal(selector, '#galgrid'); return grid; } } };
  const calls = [], replies = [], errors = [];
  const context = vm.createContext({
    gallery: g, state: { rounds: { draw: { id: 'r1', answered: 3 } }, players: ['a', 'b', 'c', 'd'].map((id) => ({ id })) },
    client: { send: async (message) => { calls.push(message); assert.ok(replies.length, 'unexpected gallery request'); return replies.shift(); } },
    esc: String, sketchSVG: () => '<svg/>', markGallery() {}, console: { warn: (...args) => errors.push(args) },
  });
  vm.runInContext(syncSource, context);
  return { context, g, grid, calls, replies, errors };
}

test('a kick and a new sketch with the same answer count refresh the gallery', async () => {
  const { context, g, grid, calls, replies, errors } = setup();
  replies.push({ round: 'r1', cursor: 3, active: ['a', 'b', 'c'], sketches: [sketch(1, 'a'), sketch(2, 'b'), sketch(3, 'c')] });
  await vm.runInContext('loadSketches()', context);
  g.selected = ['a'];
  context.state.players = ['b', 'c', 'd'].map((id) => ({ id })); // A kicked, D answered; count stays 3.
  replies.push({ round: 'r1', cursor: 4, active: ['b', 'c', 'd'], sketches: [sketch(4, 'd')] });
  vm.runInContext('syncGallery()', context);
  await tick();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].after, 3);
  assert.deepEqual(plain(g.sketches.map((x) => [x.n, x.player])), [[2, 'b'], [3, 'c'], [4, 'd']]);
  assert.deepEqual(plain(g.selected), []);
  assert.deepEqual(grid.tiles.map((x) => x.dataset.player), ['b', 'c', 'd']);
  assert.equal(g.cursor, 4);
  assert.deepEqual(errors, []);
});

test('a new practice round clears old drawings and selections before any new answer', async () => {
  const { context, g, grid, calls, replies, errors } = setup();
  replies.push({ round: 'r1', cursor: 3, active: ['a', 'b', 'c'], sketches: [sketch(1, 'a'), sketch(2, 'b'), sketch(3, 'c')] });
  await vm.runInContext('loadSketches()', context);
  g.selected = ['b'];
  context.state.rounds.draw = { id: 'r2', answered: 0 };
  replies.push({ round: 'r2', cursor: 0, active: [], sketches: [] });
  vm.runInContext('syncGallery()', context);
  await tick();
  assert.equal(calls[1].round, 'r1');
  assert.deepEqual(plain(g.sketches), []);
  assert.deepEqual(plain(g.selected), []);
  assert.deepEqual(grid.tiles, []);
  assert.equal(g.cursor, 0);
  context.state.rounds.draw.answered = 1;
  replies.push({ round: 'r2', cursor: 1, active: ['b'], sketches: [sketch(1, 'b')] });
  vm.runInContext('syncGallery()', context);
  await tick();
  assert.deepEqual(plain(g.sketches.map((x) => x.n)), [1]);
  assert.deepEqual(errors, []);
});

test('a state update during a request is fetched after its response', async () => {
  const { context, g, calls, replies, errors } = setup();
  context.state.rounds.draw.answered = 0;
  let resolveFirst;
  replies.push(new Promise((resolve) => { resolveFirst = resolve; }));
  const loading = vm.runInContext('loadSketches()', context);
  context.state.rounds.draw.answered = 2;
  vm.runInContext('syncGallery()', context);
  assert.equal(calls.length, 1);
  replies.push({ round: 'r1', cursor: 2, active: ['a', 'b'], sketches: [sketch(2, 'b')] });
  resolveFirst({ round: 'r1', cursor: 1, active: ['a'], sketches: [sketch(1, 'a')] });
  await loading;
  await tick();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].after, 1);
  assert.deepEqual(plain(g.sketches.map((x) => x.player)), ['a', 'b']);
  assert.deepEqual(errors, []);
});

test('a failed request does not start an unbounded retry loop', async () => {
  const { context, calls, replies, errors } = setup();
  replies.push(Promise.reject(new Error('offline')));
  await vm.runInContext('loadSketches()', context);
  await tick();
  assert.equal(calls.length, 1);
  assert.equal(errors.length, 1);
});
