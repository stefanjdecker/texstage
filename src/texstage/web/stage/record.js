// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// texstage's recording (docs/texstage-design.md, sections 9 and 20): what the projector shows -
// the screen or window the lecturer picks in the browser's dialog, so slides, ink, pointer and
// quiz views as the hall sees them - and the microphone, as one video file. MediaRecorder hands
// out a part every 10 s, which goes to the server at once (PUT /api/recording/<take>/<part>, one
// at a time, again until it is taken): a crash loses the last seconds at most. The server keeps
// the take in the lecture's archive and finishes the file when the recording stops.
//
//   const mic = new Microphone();             // in a click: its level meter may run
//   await mic.open(deviceId);                 // getUserMedia; mic.level() 0..1
//   const screen = await pickScreen({sound}); // the browser's dialog (needs the click, too); shown in
//                                             // the dialog as a miniature before the recording starts
//   const rec = new Recording({auth, session, screen, mic, onChange});
//   await rec.start();  rec.pause(); rec.resume(); rec.stop();
//
// What went wrong - start()'s rejection, rec.error once it failed - is {code, message}: the
// server's refusal by its code, or the browser's recorder ("recorder"), for the presenter window
// to say in its language (i18n.js errorText). A recording that stopped by itself - the recorded
// screen went away: Stop sharing, the projector window closed, the display gone - says so in
// rec.cause ("screen"), the presenter window loudly; rec.silence() is how long the microphone has
// been silent while recording, rec.micLost whether it went away (the presenter window warns).

import { authHeaders } from "/static/shared/client.js";

const TYPES = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];
const PART_MS = 10000;
const VIDEO_BPS = 2_500_000;          // slides change rarely: the encoder spends less most of the time
const AUDIO_BPS = 128_000;
export const QUIET_MS = 30000;        // the microphone silent this long while recording: the presenter warns
const LOUD = 0.15;                    // a level above this is heard (mic.level(): -51 dB; a voice is far above)

// the server's refusal of a request (its JSON: {error, code}) as an error with its code
const refusal = (r, info) => Object.assign(new Error(info?.error || `HTTP ${r.status}`), { code: info?.code });

export function canRecord() {
  return Boolean(navigator.mediaDevices?.getDisplayMedia) && typeof MediaRecorder !== "undefined";
}

export function pickScreen({ sound = false } = {}) {
  // the projector's screen - preselected where the browser can (a single screen: a window, the
  // projector window) -, at most 1080p (a 4K projector would cost the laptop's CPU); with `sound`
  // the computer's sound too, the deck's videos - the browser offers it for an entire screen (Chromium
  // on Windows and ChromeOS: "Also share system audio") and a tab, not for a window
  const single = window.screen.isExtended === false;
  return navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: single ? "window" : "monitor", frameRate: { ideal: 30, max: 30 },
      width: { max: 1920 }, height: { max: 1080 } },
    audio: sound ? { echoCancellation: false, noiseSuppression: false, autoGainControl: false } : false,
    selfBrowserSurface: "exclude", surfaceSwitching: "exclude", systemAudio: sound ? "include" : "exclude",
    monitorTypeSurfaces: "include",
  });
}

export function surfaceOf(screen) {
  // what a capture shows, as the browser says: "monitor" (an entire screen), "window", "browser" (a tab), or ""
  return screen?.getVideoTracks()[0]?.getSettings?.().displaySurface || "";
}

export async function microphones() {
  // the inputs by name - once the browser allowed a microphone (before, it names none)
  try {
    return (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput" && d.label);
  } catch {
    return [];
  }
}

export class Microphone {
  // the microphone and its level: opened before the recording starts, so the lecturer sees that
  // it hears them
  constructor() {
    this.ctx = typeof AudioContext === "function" ? new AudioContext() : null;
    this.stream = null;
    this.analyser = null;
    this.generation = 0;
    this.closed = false;
  }

  async open(deviceId = "") {
    if (this.closed) return null;
    this.release();
    const generation = this.generation;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: {
      deviceId: deviceId ? { exact: deviceId } : undefined,
      echoCancellation: false, noiseSuppression: true, autoGainControl: true } });   // nothing plays back
    if (this.closed || generation !== this.generation) {
      stream.getTracks().forEach((t) => t.stop());    // cancelled, or a newer input was selected
      return null;
    }
    this.stream = stream;
    if (this.ctx) {
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 2048;
      this.ctx.createMediaStreamSource(this.stream).connect(this.analyser);
      this.samples = new Float32Array(this.analyser.fftSize);
      if (this.ctx.state === "suspended") this.ctx.resume().catch(() => {});
    }
    return this.stream;
  }

  get label() {
    return this.stream?.getAudioTracks()[0]?.label || "";
  }

  get deviceId() {
    return this.stream?.getAudioTracks()[0]?.getSettings().deviceId || "";
  }

  level() {
    // the loudness of the last ~40 ms, 0 (-60 dB and less) to 1 (0 dB)
    if (!this.analyser) return 0;
    this.analyser.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (const v of this.samples) sum += v * v;
    const db = 10 * Math.log10(sum / this.samples.length || 1e-12);
    return Math.min(1, Math.max(0, (db + 60) / 60));
  }

  release() {
    this.generation++;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.analyser = null;
  }

  close() {
    this.closed = true;
    this.release();
    this.ctx?.close().catch(() => {});
    this.ctx = null;
  }
}

export class Recording {
  constructor({ auth, session, screen, mic = null, onChange = () => {} }) {
    Object.assign(this, { auth, session, screen, mic, onChange });
    // ready: the screen chosen, nothing recorded yet and no file - it waits for start() (the presenter window's
    // Start); then starting, recording, paused, stopping, saved, failed. Let go while it waits (drop): dropped,
    // or gone when the screen went away by itself.
    this.state = "ready";
    this.error = null;         // why it failed: {code, message}
    this.take = null;          // the server's name for it, and its file there
    this.file = null;
    this.folder = null;
    this.part = 0;             // the next part's number
    this.queue = [];           // parts the server has not taken yet: {part, blob}
    this.sending = false;
    this.late = false;         // a part waits for the network or the server
    this.saved = 0;            // bytes on the server
    this.ms = 0;               // the time recorded before the last start or resume
    this.since = null;         // and since then (performance.now())
    this.waiting = [];         // who waits for the queue to empty
    this.cause = null;         // why it stopped by itself: "screen" (the recorded screen went away); null: Stop
    this.micLost = false;      // the microphone went away while recording (unplugged): no voice any more
    this.loud = null;          // when the microphone was last heard (silence)
    this.mixer = null;         // the microphone and the computer's sound as one track (an AudioContext)
    this.unload = (e) => {     // closing or reloading the window would end the recording
      if (this.active) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    this.gone = () => {        // it ends anyway: what the server has becomes the file
      if (this.active && this.take) {
        fetch(`/api/recording/${this.take}/done`, { method: "POST", keepalive: true, headers: authHeaders(this.auth) });
      }
    };
    // the screen went away by itself - Stop sharing, the projector window closed, the display gone (a stopped track
    // fires no "ended": the recording's own stop is not this) - : while it waits, nothing is lost and it is let go;
    // while it records, what came is saved, and the presenter window says it loudly (cause), not as a Stop
    screen.getVideoTracks()[0]?.addEventListener("ended", () => {
      if (this.state === "ready") return this.drop("gone");
      if (this.state === "recording" || this.state === "paused") this.cause = "screen";
      this.stop();
    });
  }

  get active() {
    return this.state === "recording" || this.state === "paused" || this.state === "stopping";
  }

  elapsed() {
    return this.ms + (this.since === null ? 0 : performance.now() - this.since);
  }

  async start({ signal } = {}) {
    // the file on the server, in this.session's archive, then the recorder: from here on it records. Refused, or the
    // network gone: it waits again (ready), and the rejection says why
    signal?.throwIfAborted();
    if (this.state !== "ready") return;
    this.state = "starting";
    this.onChange(this);
    const type = TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "";
    const ext = type.startsWith("video/mp4") ? "mp4" : "webm";
    try {
      const r = await fetch(`/api/archive/${this.session}/recording`, { method: "POST", signal,
        headers: { ...authHeaders(this.auth), "Content-Type": "application/json" }, body: JSON.stringify({ ext }) });
      const info = await r.json().catch(() => ({}));
      signal?.throwIfAborted();
      if (!r.ok) throw refusal(r, info);
      if (this.state !== "starting") return;      // let go meanwhile (the screen went away)
      Object.assign(this, { take: info.take, file: info.file, folder: info.folder });
    } catch (err) {
      if (this.state === "starting") {
        this.state = "ready";
        this.onChange(this);
      }
      throw err;
    }
    const voice = this.mic?.stream?.getAudioTracks() || [];
    const tracks = [...this.screen.getVideoTracks(), ...this.audio(voice, this.screen.getAudioTracks())];
    this.recorder = new MediaRecorder(new MediaStream(tracks), { ...(type ? { mimeType: type } : {}),
      videoBitsPerSecond: VIDEO_BPS, audioBitsPerSecond: AUDIO_BPS });
    this.recorder.ondataavailable = (e) => {
      if (!e.data.size) return;
      this.queue.push({ part: this.part++, blob: e.data });
      this.send();
    };
    this.recorder.onstop = () => this.finish();
    this.recorder.onerror = (e) => this.fail({ code: "recorder", message: e.error?.message || "" });
    voice[0]?.addEventListener("ended", () => {   // the microphone unplugged: the video goes on, without the voice
      if (!this.active) return;
      this.micLost = true;
      this.onChange(this);
    });
    this.recorder.start(PART_MS);
    this.since = performance.now();
    this.loud = this.since;
    this.state = "recording";
    addEventListener("beforeunload", this.unload);
    addEventListener("pagehide", this.gone);
    this.onChange(this);
  }

  audio(voice, sound) {
    // the recording's audio track: the microphone, the computer's sound (pickScreen's sound), or both mixed
    // into one - MediaRecorder records one audio track
    if (!voice.length || !sound.length || typeof AudioContext !== "function") return [...voice, ...sound].slice(0, 1);
    this.mixer = new AudioContext();
    const into = this.mixer.createMediaStreamDestination();
    for (const track of [voice[0], sound[0]]) this.mixer.createMediaStreamSource(new MediaStream([track])).connect(into);
    if (this.mixer.state === "suspended") this.mixer.resume().catch(() => {});
    return into.stream.getAudioTracks();
  }

  silence(now = performance.now()) {
    // how long the microphone has been silent while recording (ms; 0 while paused, or recording without one):
    // the presenter window warns after QUIET_MS - a microphone switched off or unplugged, found in the lecture
    if (this.state !== "recording" || !this.mic) {
      this.loud = now;
      return 0;
    }
    if (this.micLost) return now - this.loud;
    if (this.loud === null || this.mic.level() > LOUD) this.loud = now;
    return now - this.loud;
  }

  drop(state = "dropped") {
    // let go before anything was recorded - ✕ in the presenter window (dropped), or the screen went away (gone):
    // the screen and the microphone stop, and there is no file
    if (this.state !== "ready") return;
    this.release();
    this.state = state;
    this.onChange(this);
  }

  pause() {
    if (this.state !== "recording") return;
    this.recorder.pause();
    this.ms = this.elapsed();
    this.since = null;
    this.state = "paused";
    this.onChange(this);
  }

  resume() {
    if (this.state !== "paused") return;
    this.recorder.resume();
    this.since = performance.now();
    this.state = "recording";
    this.onChange(this);
  }

  stop() {
    // the recorder hands out its last part, then stops (finish)
    if (this.state !== "recording" && this.state !== "paused") return;
    this.ms = this.elapsed();
    this.since = null;
    this.state = "stopping";
    this.onChange(this);
    if (this.recorder.state !== "inactive") this.recorder.stop();
    else this.finish();               // it stopped by itself (no track left): finished already
  }

  async finish() {
    if (this.finishing) return;
    this.finishing = true;
    this.release();
    this.ms = this.elapsed();
    this.since = null;
    if (this.state === "failed") return;
    this.state = "stopping";
    this.onChange(this);
    await this.drained();
    if (this.state === "failed") return;
    for (let wait = 1000; ; wait = Math.min(2 * wait, 15000)) {
      let r = null;
      try {
        r = await fetch(`/api/recording/${this.take}/done`, { method: "POST", headers: authHeaders(this.auth) });
      } catch { /* the network: again */ }
      if (r?.ok) {
        const info = await r.json();
        this.saved = info.size;
        this.state = "saved";
        break;
      }
      if (r && r.status < 500) {
        this.fail(refusal(r, await r.json().catch(() => ({}))));
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, wait));
    }
    this.detach();
    this.onChange(this);
  }

  async send() {
    // the parts in order, one at a time; one the server did not answer goes again
    if (this.sending) return;
    this.sending = true;
    let wait = 1000;
    while (this.queue.length && this.state !== "failed") {
      const { part, blob } = this.queue[0];
      let r = null;
      try {
        r = await fetch(`/api/recording/${this.take}/${part}`, { method: "PUT",
          headers: { ...authHeaders(this.auth), "Content-Type": "application/octet-stream" }, body: blob });
      } catch { /* the network: again */ }
      if (r?.ok) {
        this.saved = (await r.json()).size;
        this.queue.shift();
        wait = 1000;
        this.late = false;
        this.onChange(this);
      } else if (r && r.status !== 507 && r.status < 500) {
        this.fail(refusal(r, await r.json().catch(() => ({}))));
      } else {
        this.late = true;           // the network, or the server's disk: again in a while
        this.onChange(this);
        await new Promise((resolve) => setTimeout(resolve, wait));
        wait = Math.min(2 * wait, 15000);
      }
    }
    this.sending = false;
    if (!this.queue.length || this.state === "failed") this.waiting.splice(0).forEach((resolve) => resolve());
  }

  drained() {
    if (!this.queue.length && !this.sending) return Promise.resolve();
    return new Promise((resolve) => this.waiting.push(resolve));
  }

  fail(error) {
    if (this.state === "failed") return;
    const recording = this.state === "recording" || this.state === "paused";
    this.state = "failed";
    this.error = error;
    this.ms = this.elapsed();
    this.since = null;
    if (recording) {
      try { this.recorder.stop(); } catch { /* stopped already */ }
    }
    this.release();
    this.detach();
    this.waiting.splice(0).forEach((resolve) => resolve());
    this.onChange(this);
  }

  release() {
    this.screen.getTracks().forEach((t) => t.stop());
    this.mic?.close();
    this.mixer?.close().catch(() => {});
    this.mixer = null;
  }

  detach() {
    removeEventListener("beforeunload", this.unload);
    removeEventListener("pagehide", this.gone);
  }
}
