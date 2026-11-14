// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The recording (web/stage/record.js), in Node with the browser's media stood in for: the screen asked for
// without the computer's sound unless the lecturer ticks it, the microphone and that sound recorded as one
// track, a recording that stopped by itself saying why (a Stop does not), and the microphone's silence and
// its loss noticed while recording (the review of the recording, 2026-11-14).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/texstage/web/stage/record.js'), 'utf8')
  .replace(/^import .*$/gm, '').replace(/^export /gm, '');

class Track {
  constructor(kind, settings = {}) { Object.assign(this, { kind, settings, listeners: {}, stopped: false }); }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  stop() { this.stopped = true; }                     // (the page's own stop fires no "ended")
  end() { (this.listeners.ended || []).forEach((fn) => fn()); }    // the source went away by itself
  getSettings() { return this.settings; }
}

class Stream {
  constructor(tracks = []) { this.tracks = tracks; }
  getTracks() { return this.tracks; }
  getVideoTracks() { return this.tracks.filter((t) => t.kind === 'video'); }
  getAudioTracks() { return this.tracks.filter((t) => t.kind === 'audio'); }
}

function world({ isExtended = true } = {}) {
  const made = { recorders: [], asked: [], contexts: [] };
  class Recorder {
    static isTypeSupported(type) { return type === 'video/webm;codecs=vp9,opus'; }
    constructor(stream, options) { Object.assign(this, { stream, options, state: 'inactive' }); made.recorders.push(this); }
    start() { this.state = 'recording'; }
    pause() { this.state = 'paused'; }
    resume() { this.state = 'recording'; }
    stop() { this.state = 'inactive'; Promise.resolve().then(() => this.onstop?.()); }
  }
  class Context {
    constructor() { Object.assign(this, { state: 'running', sources: [], closed: false }); made.contexts.push(this); }
    createMediaStreamDestination() { this.out = new Track('audio'); return { stream: new Stream([this.out]) }; }
    createMediaStreamSource(stream) { const node = { stream, connect(to) { node.to = to; } }; this.sources.push(node); return node; }
    resume() { return Promise.resolve(); }
    close() { this.closed = true; return Promise.resolve(); }
  }
  let now = 1000;
  const context = vm.createContext({
    window: { screen: { isExtended } }, MediaRecorder: Recorder, MediaStream: Stream, AudioContext: Context,
    navigator: { mediaDevices: { getDisplayMedia: async (options) => {
      made.asked.push(options);
      return new Stream([new Track('video', { displaySurface: 'monitor' })]);
    } } },
    fetch: async () => ({ ok: true, status: 200, json: async () => ({ take: 't1', file: 'recording-t1.webm', folder: 'a', size: 10 }) }),
    authHeaders: () => ({}), performance: { now: () => now },
    addEventListener() {}, removeEventListener() {}, setTimeout: (fn) => fn(),
  });
  vm.runInContext(`${source}\nglobalThis.api = { pickScreen, surfaceOf, Recording, QUIET_MS };`, context);
  return { api: context.api, made, pass(ms) { now += ms; }, now: () => now };
}

const mic = (track, level = () => 0.5) => ({ stream: new Stream([track]), level, close() {} });

async function until(done) {
  for (let i = 0; i < 50 && !done(); i++) await new Promise((resolve) => setImmediate(resolve));
  assert.ok(done(), 'it came to that');
}

test("the screen is asked for without the computer's sound unless the lecturer ticks it", async () => {
  const { api, made } = world();
  await api.pickScreen();
  await api.pickScreen({ sound: true });
  const [plain, sound] = made.asked;
  assert.equal(plain.audio, false);
  assert.equal(plain.systemAudio, 'exclude');
  assert.equal(plain.video.displaySurface, 'monitor');
  assert.equal(plain.selfBrowserSurface, 'exclude');                    // never the presenter window itself
  assert.equal(sound.systemAudio, 'include');
  assert.equal(typeof sound.audio, 'object');
  const single = world({ isExtended: false });                         // one screen: the projector window
  await single.api.pickScreen();
  assert.equal(single.made.asked[0].video.displaySurface, 'window');
  assert.equal(api.surfaceOf(new Stream([new Track('video', { displaySurface: 'window' })])), 'window');
  assert.equal(api.surfaceOf(null), '');
});

test("the microphone and the computer's sound are recorded as one audio track", async () => {
  const { api, made } = world();
  const picture = new Track('video'), desk = new Track('audio'), voice = new Track('audio');
  const rec = new api.Recording({ auth: 'k', session: 's', screen: new Stream([picture, desk]), mic: mic(voice) });
  await rec.start();
  const [mixer] = made.contexts;
  assert.deepEqual([...made.recorders[0].stream.getTracks()], [picture, mixer.out]);   // (the sandbox's array: copied)
  assert.deepEqual(mixer.sources.map((s) => s.stream.getTracks()[0]), [voice, desk]);
  rec.stop();
  await until(() => rec.state === 'saved');
  assert.equal(mixer.closed, true);
  const alone = world();                                               // the microphone alone: its own track
  const own = new Track('audio');
  await new alone.api.Recording({ auth: 'k', session: 's', screen: new Stream([new Track('video')]), mic: mic(own) }).start();
  assert.deepEqual([...alone.made.recorders[0].stream.getAudioTracks()], [own]);
  assert.equal(alone.made.contexts.length, 0);
});

test('a recording that stops by itself says why; a Stop does not', async () => {
  const { api } = world();
  const picture = new Track('video');
  const rec = new api.Recording({ auth: 'k', session: 's', screen: new Stream([picture]) });
  await rec.start();
  picture.end();                                                       // the projector window closed
  await until(() => rec.state === 'saved');
  assert.equal(rec.cause, 'screen');
  const other = world();
  const stopped = new other.api.Recording({ auth: 'k', session: 's', screen: new Stream([new Track('video')]) });
  await stopped.start();
  stopped.stop();
  await until(() => stopped.state === 'saved');
  assert.equal(stopped.cause, null);
});

test('the microphone silent for 30 s while recording is noticed, and so is its loss', async () => {
  const w = world();
  let level = 0;
  const voice = new Track('audio');
  const rec = new w.api.Recording({ auth: 'k', session: 's', screen: new Stream([new Track('video')]),
    mic: mic(voice, () => level) });
  await rec.start();
  w.pass(29000);
  assert.ok(rec.silence(w.now()) < w.api.QUIET_MS);
  w.pass(2000);
  assert.ok(rec.silence(w.now()) >= w.api.QUIET_MS);
  level = 0.6;                                                          // a voice
  assert.equal(rec.silence(w.now()), 0);
  level = 0;
  rec.pause();                                                          // paused: no warning, and none at once after
  w.pass(60000);
  assert.equal(rec.silence(w.now()), 0);
  rec.resume();
  w.pass(10000);
  assert.ok(rec.silence(w.now()) < w.api.QUIET_MS);
  voice.end();                                                          // unplugged
  assert.equal(rec.micLost, true);
});
