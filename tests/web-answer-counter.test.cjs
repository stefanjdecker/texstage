// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/texstage/web/shared/live.js'), 'utf8')
  .replace(/^import .*$/gm, '').replace(/^export /gm, '');
// live.js's texts as it imports them (an ES module: require(esm), Node 22.12+)
const { CATALOGS, texts } = require('../src/texstage/web/i18n/i18n.js');
const context = vm.createContext({CATALOGS, texts, esc: String, pct: (n) => `${n * 100}%`, box: () => ''});
vm.runInContext(source + '\nglobalThis.Stage = Stage;', context);

function render({answered, awaiting, connected, players = 3, phase = 'open', results}, timer) {
  const display = Object.assign(Object.create(context.Stage.prototype), {
    slide: {quiz: 'q', rects: timer ? {timer: {x: .8, y: .1, w: .1, h: .1}} : {}},
    state: {session: {connected, players}, rounds: {q: {answered, awaiting, phase, results}}},
    deck: {quizzes: {q: {type: 'single'}}},
    labels: {answer: 'answer', answers: 'answers', correct: 'correct', timesUp: "Time's up"},
  });
  return display.question(phase === 'revealed');
}

for (const timer of [true, false]) {
  const layout = timer ? 'standalone timer' : 'embedded pill';
  test(`${layout}: accepted answers stay in the total across disconnects and reconnects`, () => {
    const states = [
      {answered: 1, awaiting: 2, connected: 3, expected: '1 / 3 answers'},
      {answered: 1, awaiting: 2, connected: 2, expected: '1 / 3 answers'}, // answered phone leaves
      {answered: 1, awaiting: 2, connected: 3, expected: '1 / 3 answers'}, // answered phone returns
      {answered: 1, awaiting: 1, connected: 2, expected: '1 / 2 answers'}, // pending phone leaves
      {answered: 1, awaiting: 2, connected: 3, expected: '1 / 3 answers'}, // pending phone returns
      {answered: 2, awaiting: 1, connected: 2, expected: '2 / 3 answers'}, // still waiting for one
      {answered: 3, awaiting: 0, connected: 2, expected: '3 / 3 answers'},
    ];
    for (const state of states) assert.ok(render(state, timer).includes(state.expected), JSON.stringify(state));
  });

  test(`${layout}: zero online players never falls back to the lobby total`, () => {
    assert.ok(render({answered: 0, awaiting: 0, connected: 0}, timer).includes('0 / 0 answers'));
    assert.ok(render({answered: 1, awaiting: 0, connected: 0}, timer).includes('1 / 1 answer<'));
    assert.ok(render({answered: 0, awaiting: 2, connected: 2, phase: 'get-ready'}, timer).includes('0 / 2 answers'));
  });

  test(`${layout}: closed and revealed results retain disconnected players' answers`, () => {
    const state = {answered: 3, awaiting: 0, connected: 1, results: {answered: 3, correct: 2}};
    const closed = render({...state, phase: 'closed'}, timer);
    assert.ok(closed.includes('3 answers'));
    assert.ok(!closed.includes(' / 1'));
    assert.ok(render({...state, phase: 'revealed'}, timer).includes('2 / 3 correct'));
  });
}
