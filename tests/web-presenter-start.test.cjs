// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The presenter window's start with a stored presenter key (web/stage/presenter.js), in Node. A
// key typed into the key form is kept in localStorage, and a reload starts with it: start() then
// reaches showDecks() before its first pause, so it must run after every constant of the module
// has its value - before, folderList's did not, start() took the error for a refused key, and the
// key was gone (the host console's start, host.js, likewise). And only the server's refusal of the
// key forgets it: the server out of reach for a moment, or any other failure, leaves it stored.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const web = path.join(__dirname, '../src/texstage/web');
const source = (file) => fs.readFileSync(path.join(web, file), 'utf8');
// the window's texts and its language, as presenter.js imports them (an ES module: require(esm));
// an English browser, whatever the machine's locale (Node's navigator says it)
const { errorText, pageLanguage, usePageLanguage } = require('../src/texstage/web/i18n/i18n.js');
Object.defineProperty(globalThis, 'navigator', { value: { language: 'en-GB', languages: ['en-GB'] }, configurable: true });

test('start() runs after every top-level declaration of its module', () => {
  for (const file of ['stage/presenter.js', 'host/host.js']) {
    const lines = source(file).split('\n');
    const call = lines.indexOf('start();');
    assert.ok(call > 0, `${file} calls start() at the top level`);
    assert.equal(lines.filter((line) => line === 'start();').length, 1, file);
    const later = lines.slice(call + 1).filter((line) => /^(const|let|var|class) /.test(line));
    assert.deepEqual(later, [], `${file}: declarations after start() - not there yet when it runs`);
  }
});

// start() and the functions it calls before the key form, from presenter.js, over a stored key
function presenter(stored) {
  const presenter = source('stage/presenter.js');
  const code = presenter.slice(presenter.indexOf('async function start()'), presenter.indexOf('\nfunction keyForm('));
  const store = new Map(Object.entries(stored));
  const shown = [];
  const context = vm.createContext({
    KEY: 'texquiz:presenter-key', DEVICE: 'texstage:device-token',
    localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k) },
    location: { hash: '', pathname: '/stage', search: '' }, history: { replaceState() {} },
    fetch: async () => { throw new TypeError('not on the server machine'); },
    $: () => ({}), errorText, pageLanguage, usePageLanguage, URLSearchParams,
    keyForm: (error = '') => shown.push(error), pairThisDevice: async () => {},
    decks: async () => {},
  });
  vm.runInContext(`var auth = null, T = null, lang = "en";\nasync function showDecks() { return decks(); }\n${code}`, context);
  return { context, store, shown, start: (failure) => {
    context.decks = failure ? async () => { throw failure; } : async () => {};
    return context.start();
  } };
}

const KEY = 'texquiz:presenter-key';
const refused = Object.assign(new Error('presenter key required'), { status: 403, code: 'key-required' });

test('a stored key that the server takes opens the decks, and stays stored', async () => {
  const p = presenter({ [KEY]: 'right-key' });
  await p.start(null);
  assert.deepEqual(p.shown, []);
  assert.equal(p.store.get(KEY), 'right-key');
  assert.equal(p.context.auth, 'right-key');
});

test('only the server refusing the key forgets it', async () => {
  const p = presenter({ [KEY]: 'wrong-key' });
  await p.start(refused);
  assert.equal(p.store.has(KEY), false);
  assert.deepEqual(p.shown, ['This presenter key is not accepted.']);
  const device = presenter({ 'texstage:device-token': 'removed-device' });
  await device.start(refused);
  assert.equal(device.store.has('texstage:device-token'), false, 'a removed device forgets its token');
  assert.match(device.shown[0], /removed/);
});

test('the server out of reach, or another failure, keeps the stored key for the next try', async () => {
  for (const failure of [new TypeError('Failed to fetch'), Object.assign(new Error('the server failed'), { status: 500 }),
    new ReferenceError("Cannot access 'folderList' before initialization")]) {
    const p = presenter({ [KEY]: 'right-key' });
    await p.start(failure);
    assert.equal(p.store.get(KEY), 'right-key', failure.message);
    assert.deepEqual(p.shown, [`That did not work: ${failure.message}`], failure.message);
  }
});
