// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/texstage/web/play/play.js'), 'utf8');
const question = source.slice(source.indexOf('function question(r)'), source.indexOf('\nasync function submit('));

function render(numeric, sanitized, draftValue) {
  const listeners = {};
  const num = {value: sanitized, addEventListener: (event, fn) => { listeners[event] = fn; }};
  const label = {textContent: ''};
  const send = {addEventListener: (_event, fn) => { listeners.submit = fn; }};
  const app = {innerHTML: '', querySelectorAll: () => []};
  const submitted = [];
  const draft = draftValue === undefined ? {} : {q: {value: draftValue}};
  const context = vm.createContext({app, draft, ZOOM: 1, pageWidth: () => 400, answerScale: () => 1,
    promptCard: () => '', esc: String, T: {send: 'Submit'},
    $: (selector) => ({'#num': num, '#val': label, '#send': send}[selector] || null),
    submit: (_round, answer) => submitted.push(answer.value)});
  vm.runInContext(question, context);
  context.question({id: 'q', question: {type: 'numeric', numeric}});
  return {app, draft, num, label, listeners, submitted};
}

test('an untouched slider submits its browser-sanitized value on a grid anchored at min', () => {
  // Native range sanitization turns midpoint 2 into 3 for min=1, max=3, step=2.
  const t = render({min: 1, max: 3, step: 2}, '3');
  assert.match(t.app.innerHTML, /type="range"[^>]*value="2"/);
  assert.equal(t.label.textContent, '3');
  assert.equal(t.draft.q.value, 3);
  t.listeners.submit();
  assert.deepEqual(t.submitted, [3]);
  t.num.value = '1'; t.listeners.input(); t.listeners.submit();
  assert.equal(t.label.textContent, '1');
  assert.deepEqual(t.submitted, [3, 1]);
});

test('fractional minimum with default step starts at the valid midpoint', () => {
  const t = render({min: 0.5, max: 2.5}, '1.5');
  assert.match(t.app.innerHTML, /type="range"[^>]*step="1" value="1.5"/);
  assert.equal(t.label.textContent, '1.5');
  t.listeners.submit();
  assert.deepEqual(t.submitted, [1.5]);
});

test('a restored draft also follows native range sanitization before submission', () => {
  const t = render({min: 1, max: 3, step: 2}, '3', 2);
  assert.equal(t.label.textContent, '3');
  t.listeners.submit();
  assert.deepEqual(t.submitted, [3]);
});
