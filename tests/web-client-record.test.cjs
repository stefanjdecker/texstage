// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Run the browser's actual modules with controlled sockets and media permissions.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

const web = path.join(__dirname, '../src/texstage/web');
const source = (file) => fs.readFileSync(path.join(web, file), 'utf8');
// the presenter window's texts, as presenter.js has them (an ES module: require(esm), Node 22.12+)
const { texts } = require('../src/texstage/web/i18n/i18n.js');
function moduleIn(context, file, names) {
  const code = source(file).replace(/^import .*$/gm, '').replace(/^export /gm, '');
  vm.runInContext(code + `\nObject.assign(globalThis, {${names.join(',')}});`, context);
}
const settle = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return {promise, resolve, reject}; };

function transport(onStatus = () => {}, onBye = () => {}) {
  const sockets = [], timers = [];
  class Socket {
    static OPEN = 1;
    constructor() { this.readyState = 0; this.sent = []; sockets.push(this); }
    send(data) { this.sent.push(JSON.parse(data)); }
    open() { this.readyState = 1; this.onopen(); }
    message(msg) { this.onmessage({data: JSON.stringify(msg)}); }
    close() { this.readyState = 3; this.onclose(); }
  }
  const context = vm.createContext({console, WebSocket: Socket, crypto: webcrypto,
    location: {protocol: 'http:', host: 'lecture.local'}, setTimeout: (fn) => timers.push(fn)});
  moduleIn(context, 'shared/client.js', ['Client']);
  moduleIn(context, 'stage/ink.js', ['InkBook', 'InkLayer']);
  const client = new context.Client({onStatus, onBye});
  const reconnect = () => { sockets.at(-1).close(); timers.shift()(); sockets.at(-1).open(); return sockets.at(-1); };
  const welcome = (socket) => socket.message({t: 'welcome', re: socket.sent.findLast((m) => ['hello', 'join', 'resume'].includes(m.t)).id});
  return {context, client, sockets, reconnect, welcome};
}

test('reconnect authenticates before reloading the same ink frame', async () => {
  let book;
  const t = transport((status) => {
    if (status === 'open' && book?.loaded.size) { book.reset(); book.load('1'); }
  });
  book = new t.context.InkBook(t.client);
  const login = t.client.login({t: 'hello', role: 'stage', key: 'test'});
  t.sockets[0].open(); t.welcome(t.sockets[0]); await login;
  book.loaded.add('1');
  book.put({id: 'stroke', frame: '1', points: [[0.1, 0.1, 0.5]]});
  const socket = t.reconnect();
  assert.deepEqual(socket.sent.map((m) => m.t), ['hello']);
  t.welcome(socket);
  assert.deepEqual(socket.sent.map((m) => m.t), ['hello', 'ink.load']);
  socket.message({t: 'ok', re: socket.sent[1].id,
    strokes: [{id: 'stroke', frame: '1', points: [[0.1, 0.1, 0.5]]}], drawing: []});
  await settle();
  assert.equal(book.strokes('1').length, 1);
  assert.equal(book.loaded.has('1'), true);
});

test('pending commands retain their IDs and replay once after welcome', async () => {
  const t = transport();
  const login = t.client.login({t: 'hello', role: 'stage'});
  const queued = t.client.send({t: 'slide', slide: 257});
  t.sockets[0].open();
  t.client.raw({t: 'pointer', x: 0.5, y: 0.5});
  assert.deepEqual(t.sockets[0].sent.map((m) => m.t), ['hello']);
  t.welcome(t.sockets[0]); await login;
  const command = t.sockets[0].sent[1];
  const socket = t.reconnect();
  assert.equal(socket.sent.length, 1);
  t.welcome(socket);
  assert.deepEqual(socket.sent[1], command);
  assert.equal(socket.sent.length, 2);
  socket.message({t: 'ok', re: command.id});
  await queued;
  const next = t.reconnect(); t.welcome(next);
  assert.deepEqual(next.sent.map((m) => m.t), ['hello']);
});

test('join retries keep an unguessable nonce, but a new attempt gets a new nonce', async () => {
  const t = transport();
  const first = t.client.login({t: 'join', pin: '123456', nickname: 'Ada'});
  const firstError = assert.rejects(first, (error) => error.code === 'unknown-pin');
  t.sockets[0].open();
  const initial = t.sockets[0].sent[0];
  assert.match(initial.join_nonce, /^[a-f0-9]{32}$/);
  const socket = t.reconnect();
  assert.deepEqual(socket.sent[0], initial);
  socket.message({t: 'error', re: initial.id, error: 'unknown-pin', message: 'Try another PIN'});
  await firstError;
  const next = t.client.login({t: 'join', pin: '123456', nickname: 'Ada'});
  assert.notEqual(socket.sent[1].join_nonce, initial.join_nonce);
  t.welcome(socket); await next;
});

test('a rejected reconnect clears stale commands and tells the page the session ended', async () => {
  const byes = [];
  const t = transport(() => {}, (m) => byes.push(m));
  const login = t.client.login({t: 'resume', token: 'expired-later'});
  t.sockets[0].open(); t.welcome(t.sockets[0]); await login;
  const socket = t.reconnect();
  const answer = t.client.send({t: 'answer', quiz: 'q', answer: {choice: 'A'}});
  const rejected = assert.rejects(answer, (error) => error.code === 'unknown-player');
  socket.message({t: 'error', re: socket.sent[0].id, error: 'unknown-player', message: 'The game ended'});
  await rejected;
  assert.equal(byes.length, 1);
  assert.equal(byes[0].message, 'The game ended');
  assert.equal(t.client.pending.size, 0);
  assert.equal(t.client.loginMsg, null);
  const rejoin = t.client.login({t: 'join', pin: '654321', nickname: 'Ada'});
  t.welcome(socket); await rejoin;
  assert.equal(socket.sent.some((m) => m.t === 'answer'), false);
});

// The end of the presenter window's openDeck (presenter.js), run as it is: its hello - chosen when Present
// was clicked or texstage present opened the deck -, then the projector told of the deck, or the refusal.
function presenterHello(t) {
  const presenter = source('stage/presenter.js');
  const from = presenter.indexOf('  const credentials = typeof auth');
  const to = presenter.indexOf('\n}\n', from);       // (openDeck's end)
  assert.ok(from > 0 && to > from, 'presenter.js: the hello at the end of openDeck');
  const told = [], refusals = [];
  Object.assign(t.context, {auth: 'key', deck: {deck: 'demo', bundle: 'b1'}, client: t.client, pinger: 0,
    follow: {postMessage: (m) => told.push(m)}, refused: (err) => refusals.push(err), ping() {},
    setInterval: () => 0, clearInterval() {}, newOrContinued: async () => {}});
  vm.runInContext(`globalThis.helloOf = async function (chosen) {\n${presenter.slice(from, to)}\n};`, t.context);
  return {open: (chosen) => t.context.helloOf(chosen), told, refusals};
}

test('the presenter window chooses its build once: after a break its hello takes no newer game away', async () => {
  const t = transport();
  const p = presenterHello(t);
  const opened = p.open(true);
  t.sockets[0].open();
  assert.equal(t.sockets[0].sent[0].chosen, true);
  assert.equal(p.told.length, 0);                  // the projector's hello comes after this one's (it does not choose)
  t.welcome(t.sockets[0]); await opened;
  assert.deepEqual(p.told.map((m) => [m.type, m.bundle]), [['deck', 'b1']]);
  const socket = t.reconnect();
  assert.deepEqual(socket.sent.map((m) => [m.t, m.bundle, 'chosen' in m]), [['hello', 'b1', false]]);
  t.welcome(socket);
  assert.equal(t.client.ready, true);
});

test('a presenter window refused at its hello - a newer build is played - says so and moves no projector', async () => {
  const t = transport();
  const p = presenterHello(t);
  const opened = p.open(false);
  t.sockets[0].open();
  const hello = t.sockets[0].sent[0];
  assert.equal('chosen' in hello, false);          // a reload in the lecture: no choice
  t.sockets[0].message({t: 'error', re: hello.id, error: 'newer-build', message: 'a newer build is being played'});
  await opened;
  assert.deepEqual(p.refusals.map((err) => err.code), ['newer-build']);
  assert.equal(p.told.length, 0);
});

test('an initial login rejection remains a form error, not a game-over event', async () => {
  const byes = [];
  const t = transport(() => {}, (m) => byes.push(m));
  const login = t.client.login({t: 'join', pin: '000000', nickname: 'Ada'});
  const rejected = assert.rejects(login, (error) => error.code === 'unknown-pin');
  t.sockets[0].open();
  t.sockets[0].message({t: 'error', re: t.sockets[0].sent[0].id, error: 'unknown-pin', message: 'Unknown PIN'});
  await rejected;
  assert.equal(byes.length, 0);
});

function capture() {
  const track = {stopped: false, stop() { this.stopped = true; }, getSettings: () => ({deviceId: 'mic'})};
  return {track, getTracks: () => [track], getAudioTracks: () => [track], getVideoTracks: () => [track]};
}
function mediaContext() {
  const requests = [];
  const context = vm.createContext({console, AbortController,
    navigator: {mediaDevices: {getUserMedia() { const d = deferred(); requests.push(d); return d.promise; },
      enumerateDevices: async () => []}}});
  moduleIn(context, 'stage/record.js', ['Microphone', 'Recording']);
  return {context, requests};
}

test('closing a microphone stops a stream acquired after cancellation', async () => {
  const {context, requests} = mediaContext();
  const mic = new context.Microphone();
  const open = mic.open(); mic.close();
  const stream = capture(); requests[0].resolve(stream);
  assert.equal(await open, null);
  assert.equal(stream.track.stopped, true);
  assert.equal(mic.stream, null);
});

test('rapid input changes keep only the newest microphone, even when the old request finishes last', async () => {
  const {context, requests} = mediaContext();
  const mic = new context.Microphone();
  const first = mic.open('old'), second = mic.open('new');
  const old = capture(), current = capture();
  requests[1].resolve(current); assert.equal(await second, current);
  requests[0].resolve(old); assert.equal(await first, null);
  assert.equal(old.track.stopped, true);
  assert.equal(current.track.stopped, false);
  assert.equal(mic.stream, current);
  mic.release(); assert.equal(current.track.stopped, true);
});

function dialogContext() {
  const {context, requests} = mediaContext();
  const nodes = new Map();
  const el = {remove() { this.removed = true; }, querySelector(key) {
    if (!nodes.has(key)) nodes.set(key, {style: {}, value: '', disabled: false});
    return nodes.get(key);
  }};
  const screen = deferred();
  let starts = 0;
  Object.assign(context, {
    document: {createElement: () => el, body: {append() {}}}, setInterval() { return 1; }, clearInterval() {},
    rec: null, state: {session: {id: 'game'}}, prefs: {mic: ''}, auth: 'key', T: texts('en'),
    esc: (s) => s, savePrefs() {}, renderRec() {}, remember() {}, pickScreen: () => screen.promise,
  });
  // Keep actual Recording.start: replacing only its side effects tells us whether it ran.
  context.Recording.prototype.start = async function() { starts++; };
  const presenter = source('stage/presenter.js');
  const dialog = presenter.slice(presenter.indexOf('async function recordDialog()'), presenter.indexOf('\nfunction remembered()'));
  vm.runInContext(dialog, context);
  return {context, requests, nodes, el, screen, starts: () => starts};
}

test('cancelling the recording dialog during microphone permission releases its late stream', async () => {
  const t = dialogContext();
  const opened = t.context.recordDialog();
  t.el.querySelector('#closedlg').onclick();
  const stream = capture(); t.requests[0].resolve(stream); await opened;
  assert.equal(t.el.removed, true);
  assert.equal(stream.track.stopped, true);
  assert.equal(t.starts(), 0);
});

test('cancelling while the screen picker is pending never starts a recording', async () => {
  const t = dialogContext();
  const opened = t.context.recordDialog();
  const mic = capture(); t.requests[0].resolve(mic); await opened;
  const start = t.el.querySelector('#recstart').onclick();
  t.el.querySelector('#closedlg').onclick();
  const screen = capture(); t.screen.resolve(screen); await start;
  assert.equal(screen.track.stopped, true);
  assert.equal(mic.track.stopped, true);
  assert.equal(t.starts(), 0);
});

test('cancelling during the recording request prevents MediaRecorder from starting', async () => {
  const {context} = mediaContext();
  const response = deferred();
  let created = 0;
  Object.assign(context, {authHeaders: () => ({}), fetch: () => response.promise,
    MediaRecorder: class { static isTypeSupported() { return true; } constructor() { created++; } },
  });
  const controller = new AbortController();
  const recording = new context.Recording({auth: 'key', session: 'game', screen: capture()});
  const start = recording.start({signal: controller.signal});
  const rejected = assert.rejects(start, (error) => error.name === 'AbortError');
  controller.abort();
  response.resolve({ok: true, json: async () => ({take: 'take', file: 'file', folder: 'folder'})});
  await rejected;
  assert.equal(created, 0);
});
