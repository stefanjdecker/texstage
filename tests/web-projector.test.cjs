// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = (file) => fs.readFileSync(path.join(__dirname, '../src/texstage/web', file), 'utf8')
  .replace(/^import .*$/gm, '').replace(/^export /gm, '');
// the texts live.js and projector.js import (an ES module: require(esm), Node 22.12+)
const { CATALOGS, errorText, pageLanguage, pageTexts, texts, usePageLanguage } = require('../src/texstage/web/i18n/i18n.js');

function projector() {
  const live = vm.createContext({CATALOGS, texts});
  vm.runInContext(source('shared/live.js') + '\nglobalThis.Stage = Stage;', live);
  const nodes = Object.fromEntries(['.tq-timer-text', '.tq-timer-sub', '.tq-ring']
    .map((key) => [key, {style: {}}]));
  const classList = {add() {}, remove() {}, toggle() {}};
  const timer = {classList, querySelector: (selector) => nodes[selector]};
  // Exercise Stage.show and Stage.tick; only DOM painting and PDF rendering are stubbed.
  const display = Object.assign(Object.create(live.Stage.prototype), {
    surface: {show() {}, size: () => [1920, 1080]},
    live: {querySelector: () => timer}, labels: {getReady: 'Get ready'},
    render: () => '', questionCard: () => '', animate() {}, showTypes() {},
  });
  let now = 5000;
  const context = vm.createContext({
    URLSearchParams, location: {search: '?bundle=test', pathname: '/stage/projector'},
    document: {querySelector: () => ({classList}), addEventListener() {}},
    history: {replaceState() {}}, setTimeout() {}, clearTimeout() {},
    hostFetch: async () => { throw new Error('offline'); },
    shownSlide: (deck, state) => deck.slides[state.slide || 0],
    inkKey: (slide) => slide.id, zoomOverlay() {},
    errorText, pageLanguage, pageTexts, usePageLanguage,
  });
  vm.runInContext(source('stage/projector.js').replace(/^start\(\);$/m, '') + `
    globalThis.install = (display, clock) => {
      stage = display;
      client = { now: clock, close() {} };
      deck = { slides: [{ id: 1, quiz: 'q', phase: 'question' }, { id: 2 }] };
      pdf = { prefetch() {} };
      ink = { show() {} };
      laser = { show() {} };
    };
    globalThis.update = (s) => { state = s; render(); };
    globalThis.loadDeck = load;
  `, context);
  const install = () => context.install(display, () => now);
  install();
  return {context, display, nodes, install, setTime: (time) => { now = time; },
    text: () => nodes['.tq-timer-text'].textContent};
}

const state = (screen, phase = 'open', slide = 0) => ({
  stage: {screen}, slide,
  rounds: {q: {phase, opens: 10000, deadline: 10000, limit: 10000, paused: false}},
});

for (const phase of ['open', 'get-ready']) {
  test(`freeze holds the ${phase} countdown and resumes at the current server time`, () => {
    const p = projector();
    p.context.update(state('normal', phase));
    assert.equal(p.text(), 5);
    p.context.update(state('freeze', phase));
    const ring = p.nodes['.tq-ring'].style.strokeDashoffset;
    p.setTime(9000);
    p.display.tick();
    assert.equal(p.text(), 5);
    assert.equal(p.nodes['.tq-ring'].style.strokeDashoffset, ring);
    // The server can move to another slide while the audience keeps seeing this one.
    p.context.update(state('freeze', 'revealed', 1));
    assert.equal(p.display.slide.id, 1);
    assert.equal(p.text(), 5);
    p.context.update(state('normal', phase));
    assert.equal(p.text(), 1);
    // A second freeze records a new instant, not the previous freeze's clock.
    p.context.update(state('freeze', phase));
    p.setTime(9500);
    p.display.tick();
    assert.equal(p.display.clock(), 9000);
    p.context.update(state('normal', phase));
    assert.equal(p.display.clock(), 9500);
  });
}

test('a freeze at clock zero remains frozen', () => {
  const p = projector();
  p.setTime(0);
  p.context.update(state('freeze'));
  p.setTime(9000);
  p.display.tick();
  assert.equal(p.text(), 10);
  assert.equal(p.display.clock(), 0);
});

test('changing decks discards the previous freeze instant', async () => {
  const p = projector();
  p.context.update(state('freeze'));
  // Even if the new deck cannot load yet, the old held state must be discarded.
  await p.context.loadDeck('other');
  p.setTime(9000);
  p.install();
  p.context.update(state('freeze'));
  assert.equal(p.text(), 1);
});
