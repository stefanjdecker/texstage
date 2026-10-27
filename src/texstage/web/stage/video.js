// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A video on the slide (texvideo.sty; docs/content-types-design.md, section 7): the renderer of
// its box for live.js's Stage, in the presenter and in the projector window - a file of the
// deck (by its ticket), or an online one: YouTube's or Vimeo's player, or a <video> for an
// address of a file (build/video.py `player`).
//
// The server keeps each video's state, {playing, time, at} - its media time (s) at the server's
// time at (ms), as the timer keeps its time -, set by a presenter window (video.play, video.pause,
// video.seek) and sent to every window, which plays from time + (now - at) and corrects a drift of
// more than 0.3 s; a slide without the video stops it (server/video.py). Until it was played, the
// box shows the slide's poster (the stage PDF has it there); a frozen projector holds the
// video's picture.
//
// The presenter's copy is muted - the sound is the projector's - and has a bar at its foot: play
// or pause, the position (drag it), the time. A click into the video plays or pauses it, K too;
// J goes back 10 s (L stays the laser). The projector's copy plays the sound. Where the browser
// wants a click or a key in the window first, a file plays without sound and an online video
// waits, with a note on it, until one comes - host.click tells the presenter window.
//
//   new Stage(el, {types: {video: VideoBox}, host: {role, send, media, click}})
//     role                 "presenter" or "projector"
//     send(msg)            to the server (a presenter window; the projector only follows)
//     media(file, fresh)   a promise of the file's address (mediaAddresses below)
//     click(what)          the browser wants a click in this window: "sound" or "start"

import { authHeaders } from "/static/shared/client.js";

const DRIFT = 0.3;          // s: the windows follow closer than this
const BACK = 10;            // s: J
const pct = (v) => `${(v * 100).toFixed(3)}%`;
const minutes = (s) => {
  const n = Math.max(0, Math.floor(s + 1e-6));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
};

// the addresses of a deck's video files - tickets, as a <video> cannot send the key -, asked for
// once per window (POST /api/deck/<bundle>/media); fresh: anew (an address expired, or the server
// started anew and forgot it)
export function mediaAddresses(bundle, auth) {
  let asked = null;
  return (file, fresh = false) => {
    if (!asked || fresh) {
      const mine = asked = fetch(`/api/deck/${encodeURIComponent(bundle)}/media`, { method: "POST", headers: authHeaders(auth) })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`the video's address: ${r.status}`))));
      mine.catch(() => { if (asked === mine) asked = null; });     // the next one asks again
    }
    return asked.then((addresses) => addresses[file] || Promise.reject(new Error(`no address for ${file}`)));
  };
}

// ------------------------------------------------------------------ the players
// One small interface over a <video> and YouTube's and Vimeo's players: ready, started (has
// played: until then an online one shows the platform's own picture - the box keeps the poster),
// busy (seeking or buffering), time, paused, duration (Infinity while not known), muted (also to
// set), play() -> Promise (rejected with NotAllowedError where the browser refuses), pause(),
// seek(t), scrub(t) (while the bar is dragged), destroy(); settle - ms between two jumps -, near -
// s a pause may be off -, online - starts only after a click in the window (the trial, section 7:
// a key is not enough for YouTube, and its seek on a video not started tries to play it) -,
// clickable - while it waits for that click, the click goes into its own frame, which starts it.

class FilePlayer {
  constructor(box, { muted, preload, changed, failed }) {
    const v = this.v = document.createElement("video");
    v.playsInline = true;                          // an iPad: in the box, not full screen
    v.preload = preload;
    v.muted = muted;
    v.disablePictureInPicture = true;
    // the stage's animation frames stop in a hidden window - a video plays on: it starts when
    // its file is there, stops at its end and loops by its own events
    for (const event of ["loadedmetadata", "timeupdate"]) v.addEventListener(event, changed);
    if (failed) v.addEventListener("error", failed);
    box.append(v);
    Object.assign(this, { settle: 1000, near: 0.04, online: false });
  }

  set src(url) { this.v.src = url; }
  get early() { return Boolean(this.v.src); }      // play() before its head is there: an iPad loads it only then
  get started() { return true; }                   // (a paused one shows its frame)
  get ready() { return this.v.readyState >= 1; }   // HAVE_METADATA: before it, no position
  get busy() { return this.v.seeking; }
  get time() { return this.v.currentTime; }
  get paused() { return this.v.paused; }
  get duration() { return this.v.duration || Infinity; }
  get muted() { return this.v.muted; }
  set muted(m) { this.v.muted = m; }
  play() { return this.v.play(); }
  pause() { this.v.pause(); }
  seek(t) { this.v.currentTime = t; }
  scrub(t) {
    if (this.v.fastSeek) this.v.fastSeek(t);
    else this.v.currentTime = t;
  }

  destroy() {
    this.v.pause();
    this.v.removeAttribute("src");
    this.v.load();                                 // lets go of the file
  }
}

// a platform's script, loaded once - when a slide first brings one of its videos; ready: how it
// says it is ready (YouTube's calls onYouTubeIframeAPIReady), else when it has loaded
const scripts = new Map();
function script(src, ready = null) {
  if (!scripts.has(src)) {
    scripts.set(src, new Promise((resolve, reject) => {
      ready?.(resolve);
      document.head.append(Object.assign(document.createElement("script"), { src, async: true,
        onload: ready ? null : () => resolve(),
        onerror: () => { scripts.delete(src); reject(new Error(`${src} did not load - is this computer online?`)); } }));
    }));
  }
  return scripts.get(src);
}

// YouTube's IFrame Player API, privacy-enhanced (youtube-nocookie.com); its time by asking it
class YouTubePlayer {
  constructor(box, { id, muted, changed }) {
    // (YouTube decides for itself whether a click in the page lets it play - not always: a click in
    // its own frame does)
    Object.assign(this, { settle: 2000, near: 0.15, online: true, clickable: true, early: false, state: -1, wanted: muted });
    const el = document.createElement("div");
    box.append(el);
    script("https://www.youtube.com/iframe_api", (resolve) => {
      const before = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        before?.();
        resolve();
      };
    }).then(() => {
      if (this.gone) return;
      this.p = new window.YT.Player(el, {
        videoId: id, host: "https://www.youtube-nocookie.com", width: "100%", height: "100%",
        playerVars: { controls: 0, disablekb: 1, fs: 0, iv_load_policy: 3, playsinline: 1, rel: 0, origin: location.origin,
          ...(muted ? { mute: 1 } : {}) },
        events: {
          onReady: () => {
            if (this.wanted) this.p.mute();
            this.ok = true;
            changed();
          },
          onStateChange: (e) => {                  // -1 unstarted, 0 ended, 1 playing, 2 paused, 3 buffering, 5 cued
            this.state = e.data;
            changed();
          },
          onAutoplayBlocked: () => {
            this.refused = true;
            changed();
          },
          onError: (e) => console.warn(`texstage: YouTube ${id}: error ${e.data}`),
        },
      });
      this.timer = setInterval(changed, 500);      // no time events: a hidden window follows by this
    }, (err) => console.warn("texstage:", err.message));
  }

  get ready() { return Boolean(this.ok); }
  get started() { return this.state !== -1 && this.state !== 5; }
  get busy() { return this.state === 3; }
  get time() { return this.ok ? this.p.getCurrentTime() : 0; }
  get paused() { return this.state !== 1 && this.state !== 3; }
  get duration() { return (this.ok && this.p.getDuration()) || Infinity; }
  get muted() { return this.ok ? this.p.isMuted() : this.wanted; }
  set muted(m) {
    this.wanted = m;
    if (this.ok) m ? this.p.mute() : this.p.unMute();
  }

  play() {
    this.refused = false;
    this.p?.playVideo();
    return Promise.resolve();                      // refused: onAutoplayBlocked
  }

  pause() { this.p?.pauseVideo(); }
  seek(t) { this.p?.seekTo(t, true); }
  scrub(t) { this.p?.seekTo(t, false); }

  destroy() {
    this.gone = true;
    clearInterval(this.timer);
    this.p?.destroy();
  }
}

// Vimeo's Player SDK; its time by its events, four a second, and in between by the clock
class VimeoPlayer {
  constructor(box, { id, hash, muted, changed }) {
    Object.assign(this, { settle: 2000, near: 0.15, online: true, early: false, t: 0, at: performance.now(), stopped: true,
      wanted: muted, length: Infinity });
    const el = document.createElement("div");
    box.append(el);
    script("https://player.vimeo.com/api/player.js").then(() => this.make(el, { id, hash, muted, changed }),
      (err) => console.warn("texstage:", err.message));
  }

  make(el, { id, hash, muted, changed }) {
    if (this.gone) return;
    const p = this.p = new window.Vimeo.Player(el, { ...(hash ? { url: `https://vimeo.com/${id}/${hash}` } : { id: Number(id) }),
      controls: false, muted, dnt: true, playsinline: true, keyboard: false, pip: false });
    const stamp = (d) => {
      this.t = d.seconds;
      this.at = performance.now();
      changed();
    };
    p.on("timeupdate", stamp);
    p.on("seeked", stamp);
    for (const [event, stopped] of [["play", false], ["pause", true], ["ended", true]]) {
      p.on(event, () => {
        this.stopped = stopped;
        this.started ||= !stopped;
        changed();
      });
    }
    p.on("bufferstart", () => { this.buffering = true; });
    p.on("bufferend", () => {
      this.buffering = false;
      changed();
    });
    p.on("error", (e) => console.warn(`texstage: Vimeo ${id}: ${e.name}`));
    p.ready().then(() => p.getDuration()).then((d) => {
      this.length = d || Infinity;
      this.ok = true;
      changed();
    }).catch((err) => console.warn(`texstage: Vimeo ${id}:`, err?.name || err));
  }

  get ready() { return Boolean(this.ok); }
  get busy() { return Boolean(this.buffering); }
  get time() { return this.t + (this.stopped || this.buffering ? 0 : (performance.now() - this.at) / 1000); }
  get paused() { return this.stopped; }
  get duration() { return this.length; }
  get muted() { return this.wanted; }
  set muted(m) {
    this.wanted = m;
    this.p?.setMuted(m).catch(() => {});
  }

  play() { return this.p ? this.p.play() : Promise.resolve(); }      // refused: NotAllowedError
  pause() { this.p?.pause().catch(() => {}); }
  seek(t) {
    this.t = t;
    this.at = performance.now();
    this.p?.setCurrentTime(t).catch(() => {});
  }

  scrub(t) { this.seek(t); }

  destroy() {
    this.gone = true;
    this.p?.destroy().catch(() => {});
  }
}

// ------------------------------------------------------------------ the renderer
export class VideoBox {
  constructor({ id, item, layer, controls, host = {}, clock = () => Date.now() }) {
    this.id = id;
    this.item = item;
    this.host = host;
    this.clock = clock;
    this.start = item.start ?? 0;
    this.presenter = host.role === "presenter";
    this.state = null;             // the server's {playing, time, at} for this video - or ours, on its way
    this.sent = null;              // ours: {playing, time, at, when}
    this.frozen = false;
    this.jumped = -Infinity;       // when this window last set the position (performance.now)
    this.lead = 0;                 // s: how far ahead a jump aims - what the last one took to land
    this.drag = null;              // the bar's position while it is dragged (s)
    this.painted = {};
    this.controls = controls;
    const how = item.player || {};
    this.off = !item.media && !how.youtube && !how.vimeo && !how.file;   // its poster stays
    if (this.off) return;
    this.el = Object.assign(document.createElement("div"), { className: "tq-video" });
    layer.append(this.el);
    const muted = this.presenter || Boolean(item.muted);
    const changed = () => this.tick();
    this.player = how.youtube ? new YouTubePlayer(this.el, { id: how.youtube, muted, changed })
      : how.vimeo ? new VimeoPlayer(this.el, { id: how.vimeo, hash: how.hash, muted, changed })
        : new FilePlayer(this.el, { muted, preload: this.presenter ? "metadata" : "auto", changed,
          failed: item.media ? () => this.load(true) : null });
    if (how.file) this.player.src = how.file;
    if (this.presenter && host.send) this.makeBar();
    // a click in the window: the sound, or an online video's start, if the browser wanted one; a
    // key: the sound
    this.clicks = () => this.clicked(true);
    this.keys = () => this.clicked(false);
    document.addEventListener("pointerdown", this.clicks, true);
    document.addEventListener("keydown", this.keys, true);
    if (item.media) this.load(false);
  }

  async load(fresh) {
    if (this.gone || !this.host.media) return;
    if (fresh) {                                                // (once a while: a broken file stays broken)
      if (performance.now() - (this.retried ?? -Infinity) < 30000) return;
      this.retried = performance.now();
    }
    try {
      const url = await this.host.media(this.item.media, fresh);
      if (!this.gone) this.player.src = url;
    } catch (err) {
      console.warn(`texstage: video ${this.id}`, err);
    }
  }

  place(rects) {
    const r = rects.box;
    if (!r || this.off) return;
    const at = `left:${pct(r.x)};top:${pct(r.y)};width:${pct(r.w)};height:${pct(r.h)}`;
    if (at === this.at) return;
    this.at = at;
    this.rect = r;
    this.el.style.cssText = at;
    if (this.bar) this.bar.style.cssText = `left:${pct(r.x)};top:${pct(r.y + r.h)};width:${pct(r.w)}`;
    this.placeNote();
  }

  update(state) {
    if (this.off) return;
    const st = state?.stage?.video?.[this.id] || null;
    this.frozen = !this.presenter && state?.stage?.screen === "freeze";
    const sent = this.sent;
    if (sent) {
      // ours back from the server - not an older state that happens to say the same (at: the
      // server's time, ours estimated: client.js)
      const back = st && st.playing === sent.playing && Math.abs(st.time - sent.time) < 0.002 && st.at > sent.at - 1000;
      if (!back && performance.now() - sent.when < 3000) return;          // ours is on its way
      this.sent = null;
    }
    this.state = st;
    this.tick();                                               // (a hidden window too)
  }

  end() {
    return Math.min(this.item.end ?? Infinity, this.player.duration);
  }

  where(now = this.clock()) {
    // where the video is by the state: [its position (s), playing]
    const st = this.state;
    if (!st) return [this.start, false];
    const end = this.end();
    const pos = st.time + (st.playing ? (now - st.at) / 1000 : 0);
    if (pos < end) return [pos, st.playing];
    if (this.item.loop && end < Infinity && end > this.start) {
      return [this.start + ((pos - this.start) % (end - this.start)), st.playing];
    }
    return [end, false];                                       // at its end
  }

  tick() {
    if (this.gone || this.off) return;
    const pl = this.player;
    const [pos, playing] = this.where();
    if (this.bar) this.paint(this.drag ?? pos, playing);
    const shown = Boolean(this.state) && pl.started;           // until then the slide's poster
    if (shown !== this.shown) this.el.classList.toggle("tq-shown", this.shown = shown);
    if (this.waiting === "start" && !pl.paused) this.unwait();  // it plays after all: no click needed
    if (this.frozen) {
      if (!pl.paused) pl.pause();                              // a frozen projector holds the picture
      return;
    }
    if (this.drag !== null || pl.busy) return;
    if (!pl.ready) {
      if (playing && pl.paused && !this.starting && pl.early) this.play();
      return;
    }
    const t = performance.now();
    const behind = pos - pl.time;
    if (playing) {
      if (Math.abs(behind) > DRIFT && (t - this.jumped > pl.settle || pl.paused)) {
        // off again soon after a jump: the jump itself took that long - aim that much further ahead
        if (!pl.paused && t - this.jumped < 3 * pl.settle) this.lead = Math.min(1.5, Math.max(0, this.lead + behind));
        this.jump(pos + this.lead, t);
      }
      if (pl.paused && !this.starting && !this.waiting) this.go();
    } else {
      if (!pl.paused) pl.pause();
      if (pl.started && Math.abs(behind) > pl.near && t - this.jumped > pl.settle / 4) this.jump(pos, t);
    }
  }

  jump(pos, t) {
    this.player.seek(pos);
    this.jumped = t;
  }

  go() {
    // an online player starts only in a window that had a click or a key (the trial, section 7)
    const pl = this.player;
    const active = navigator.userActivation?.hasBeenActive ?? true;
    if (pl.refused || (pl.online && !active)) this.needClick("start");
    else this.play();
  }

  async play() {
    const pl = this.player;
    this.starting = true;
    try {
      await pl.play();
    } catch (err) {
      if (err?.name !== "NotAllowedError") return;
      if (pl.online || pl.muted) {
        this.needClick("start");
      } else {                                                 // a file plays on without its sound
        pl.muted = true;
        this.needClick("sound");
        await pl.play().catch(() => this.needClick("start"));
      }
    } finally {
      this.starting = false;
    }
  }

  needClick(what) {
    // the browser wants a click or a key in this window: for the sound, or to start at all
    if (this.waiting === what) return;
    this.waiting = what;
    this.note ||= Object.assign(document.createElement("div"), { className: "tq-vnote" });
    this.note.textContent = what === "sound" ? "🔇 Click for sound" : "▶ Click for the video";
    this.controls?.append(this.note);
    this.el.classList.toggle("tq-wait", what === "start" && Boolean(this.player.clickable));
    this.placeNote();
    this.host.click?.(what);
  }

  clicked(pointer) {
    if (!this.waiting || (this.waiting === "start" && !pointer)) return;
    if (this.waiting === "sound") this.player.muted = false;
    else this.unblocked = performance.now();                  // that click starts it: it toggles nothing
    this.unwait();
    this.tick();                                               // within the click: the browser lets it play
  }

  unwait() {
    this.waiting = null;
    this.el.classList.remove("tq-wait");
    this.player.refused = false;
    this.note?.remove();
    this.note = null;
  }

  placeNote() {
    const r = this.rect;
    if (this.note && r) this.note.style.cssText = `left:${pct(r.x + r.w / 2)};top:${pct(r.y + r.h / 2)}`;
  }

  // ------------------------------------------------------------------ the presenter's
  say(t, time) {
    const end = this.end();
    time = Math.round(Math.max(this.start, end < Infinity ? Math.min(time, end) : time) * 1000) / 1000;
    const playing = t !== "video.pause";
    this.state = { playing, time, at: this.clock() };           // here at once; the server's comes back
    this.sent = { ...this.state, when: performance.now() };
    this.host.send({ t, video: this.id, time });
  }

  toggle() {
    const [pos, playing] = this.where();
    if (playing) this.say("video.pause", pos);
    else this.say("video.play", pos >= this.end() - 0.05 ? this.start : pos);     // at its end: from its start
  }

  seek(time) {
    // playing on from there, or paused there (also at its end)
    this.say(this.where()[1] ? "video.seek" : "video.pause", time);
  }

  key(k) {
    if (!this.bar) return false;
    if (k === "k" || k === "K") this.toggle();
    else if (k === "j" || k === "J") this.seek(this.where()[0] - BACK);
    else return false;
    return true;
  }

  makeBar() {
    const bar = this.bar = Object.assign(document.createElement("div"), { className: "tq-vbar" });
    bar.innerHTML = `<button class="tq-vplay" title="Play or pause - K, or a click into the video"></button>
      <div class="tq-vtrack" title="Drag: another position - J: 10 s back"><div class="tq-vdone"></div></div>
      <span class="tq-vtime"></span>`;
    this.controls.append(bar);
    this.button = bar.querySelector(".tq-vplay");
    this.done = bar.querySelector(".tq-vdone");
    this.time = bar.querySelector(".tq-vtime");
    const toggle = () => {
      if (performance.now() - (this.unblocked || 0) > 1500) this.toggle();
    };
    this.button.addEventListener("click", toggle);
    const track = bar.querySelector(".tq-vtrack");
    const at = (e) => {
      const r = track.getBoundingClientRect();
      const end = this.end();
      if (end === Infinity || !r.width) return null;                  // no length yet: the file's head not there
      return this.start + Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (end - this.start);
    };
    track.addEventListener("pointerdown", (e) => {
      const pos = at(e);
      if (pos === null) return;
      e.preventDefault();
      try { track.setPointerCapture(e.pointerId); } catch { /* ignore */ }
      this.drag = pos;
      this.scrub(pos);
    });
    track.addEventListener("pointermove", (e) => {
      if (this.drag === null || e.buttons === 0) return;                // (a hovering pen: no drag)
      const pos = at(e);
      if (pos === null) return;
      this.drag = pos;
      this.scrub(pos);
    });
    const up = (e) => {
      if (this.drag === null) return;
      const pos = this.drag;
      this.drag = null;
      if (e.type === "pointerup") this.seek(pos);
    };
    track.addEventListener("pointerup", up);
    track.addEventListener("pointercancel", up);
    // a click into the video plays or pauses it - the mouse's or a finger's: a pen writes there
    // (presenter.js takes its pointerdown before it gets here, its click comes all the same)
    this.el.classList.add("tq-click");
    this.el.addEventListener("pointerdown", () => { this.armed = performance.now(); });
    this.el.addEventListener("click", () => {
      if (performance.now() - (this.armed || 0) < 1500) toggle();
      this.armed = 0;
    });
  }

  scrub(pos) {
    // the presenter's copy shows the frame while the bar is dragged (an online one 4 times a second)
    const pl = this.player;
    if (!pl.ready || performance.now() - (this.scrubbed || 0) < (pl.online ? 250 : 0)) return;
    this.scrubbed = performance.now();
    pl.scrub(pos);
  }

  paint(pos, playing) {
    const end = this.end();
    const len = end < Infinity ? end - this.start : 0;
    const share = len > 0 ? Math.min(1, Math.max(0, (pos - this.start) / len)) : 0;
    const text = `${minutes(pos - this.start)} / ${len ? minutes(len) : "–:––"}`;
    const p = this.painted;
    if (p.share !== share) this.done.style.width = pct(share);
    if (p.text !== text) this.time.textContent = text;
    if (p.playing !== playing) {
      this.button.textContent = playing ? "⏸" : "▶";
      this.button.setAttribute("aria-label", playing ? "Pause" : "Play");
    }
    this.painted = { share, text, playing };
  }

  destroy() {
    this.gone = true;
    if (this.off) return;
    this.player.destroy();
    this.el.remove();
    this.bar?.remove();
    this.note?.remove();
    document.removeEventListener("pointerdown", this.clicks, true);
    document.removeEventListener("keydown", this.keys, true);
  }
}
