// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The WebSocket client of all texstage pages (protocol: src/texstage/server/app.py).
//
//   const c = new Client({onState, onStatus, onBye});
//   c.login({t: "join", pin, nickname});   // sent now and again after every reconnect
//   await c.send({t: "answer", ...});      // resolves with the reply, rejects with {code, message}
//   c.raw({t: "pointer", x, y});           // once, now or never (no id, no answer)
//   c.now()                                // the server's clock, for countdowns
//
// Reconnects by itself (1 s, 2 s, ... 10 s). A command sent while the connection is down
// waits and goes out with the same id afterwards; the server answers a repeated id from its
// cache, so nothing runs twice. Other messages of the server (texstage's ink and pointer) go
// to onEvent.

export class Client {
  constructor({ onState = () => {}, onStatus = () => {}, onBye = () => {}, onWelcome = () => {},
    onEvent = () => {} } = {}) {
    this.handlers = { onState, onStatus, onBye, onWelcome, onEvent };
    this.url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
    this.pending = new Map();     // id -> {msg, resolve, reject}
    this.loginMsg = null;
    this.offset = 0;              // server clock - local clock
    this.counter = 0;
    this.delay = 1000;
    this.ws = null;
    this.ready = false;           // the current socket has received its welcome
    this.stopped = false;
    this.connect();
  }

  now() {
    return Date.now() + this.offset;
  }

  connect() {
    if (this.stopped) return;
    const ws = new WebSocket(this.url);
    this.ws = ws;
    this.ready = false;
    this.handlers.onStatus("connecting");
    ws.onopen = () => {
      if (this.ws !== ws) return;
      this.delay = 1000;
      if (this.loginMsg) this.identify();
    };
    ws.onmessage = (event) => { if (this.ws === ws) this.receive(JSON.parse(event.data)); };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ready = false;
      this.handlers.onStatus("closed");
      if (!this.stopped) setTimeout(() => this.connect(), this.delay);
      this.delay = Math.min(this.delay * 2, 10000);
    };
  }

  receive(m) {
    if (m.now) {
      // the server's time when it sent the message; the delivery delay makes us a few ms late
      const offset = m.now - Date.now();
      this.offset = Math.abs(offset - this.offset) > 1000 ? offset : this.offset * 0.8 + offset * 0.2;
    }
    const loginReply = this.loginMsg && m.re === this.loginMsg.id;
    const initialLogin = loginReply && this.pending.has(m.re);
    if (loginReply && m.t === "error") {
      this.ready = false;
      this.loginMsg = null;
      this.rejectPending({ code: m.error, message: m.message });
      // The first login has a caller to show its error. After a reconnect that promise has
      // already resolved: notify the page so an expired player/device can leave the old game.
      if (!initialLogin) this.handlers.onBye({ t: "bye", reason: m.error, message: m.message });
      return;
    }
    if (m.t === "welcome" && !loginReply) return;    // a replaced login's late reply
    if (m.re !== undefined && m.re !== null && this.pending.has(m.re)) {
      const p = this.pending.get(m.re);
      this.pending.delete(m.re);
      if (m.t === "error") p.reject({ code: m.error, message: m.message });
      else p.resolve(m);
    }
    if (m.t === "welcome") {
      this.ready = true;
      // Flush once before callbacks: their ink reload/watch commands may send immediately,
      // and must never run before hello or be included in this replay a second time.
      for (const p of this.pending.values()) this.raw(p.msg);
      this.handlers.onStatus("open");
      this.handlers.onWelcome(m);
    }
    else if (m.t === "state") this.handlers.onState(m);
    else if (m.t === "bye") {
      this.loginMsg = null;
      this.ready = false;
      this.rejectPending({ code: m.reason || "ended", message: m.message || "the session ended" });
      this.handlers.onBye(m);
    } else if (m.t === "error" && (m.re === undefined || m.re === null)) console.warn("texquiz:", m.message);
    else if (m.t !== "ok" && m.t !== "error" && m.t !== "pong") this.handlers.onEvent(m);
  }

  raw(msg) {
    if (this.ready && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  identify() {
    if (this.loginMsg && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(this.loginMsg));
  }

  send(msg) {
    const id = `${Date.now().toString(36)}-${++this.counter}`;
    const full = { ...msg, id };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { msg: full, resolve, reject });
      this.raw(full);
    });
  }

  login(msg) {
    // the message that identifies us (hello, join, resume): sent again after a reconnect
    if (this.loginMsg && this.pending.has(this.loginMsg.id)) {
      const old = this.pending.get(this.loginMsg.id);
      this.pending.delete(this.loginMsg.id);
      old.reject({ code: "replaced", message: "a new login replaced this one" });
    }
    this.ready = false;
    const id = `${Date.now().toString(36)}-${++this.counter}`;
    // A lost join welcome must not create another player. This nonce identifies just this
    // attempt; getRandomValues also works on a lecture's plain HTTP LAN address.
    const nonce = msg.t === "join" ? { join_nonce: [...crypto.getRandomValues(new Uint8Array(16))]
      .map((x) => x.toString(16).padStart(2, "0")).join("") } : {};
    const full = this.loginMsg = { ...msg, ...nonce, id };
    const promise = new Promise((resolve, reject) => this.pending.set(id, { msg: full, resolve, reject }));
    this.identify();
    return promise;
  }

  relogin(msg) {
    // e.g. join -> resume once we have a token
    this.loginMsg = { ...msg, id: `re-${++this.counter}` };
  }

  close() {
    // a closed client reports nothing more (its "closed" would read as a broken connection)
    this.stopped = true;
    this.ready = false;
    const ws = this.ws;
    this.ws = null;
    ws?.close();
    this.rejectPending({ code: "disconnected", message: "the connection was closed" });
  }

  rejectPending(error) {
    for (const p of this.pending.values()) p.reject(error);
    this.pending.clear();
  }
}

// the lecturer's credentials for requests: the presenter key (text), or a paired presenter
// device's token ({device}, texstage)
export function authHeaders(auth) {
  return auth && typeof auth === "object" ? { "X-Texquiz-Device": auth.device } : { "X-Texquiz-Key": auth };
}

// GET with the presenter key (host pages) or a device's token. A refusal throws an Error as
// web/i18n's errorText takes it: the API's code and words (its JSON), and the HTTP status.
export async function hostFetch(path, auth) {
  const r = await fetch(path, { headers: authHeaders(auth) });
  if (!r.ok) {
    const body = await r.text();
    let info = null;
    try { info = JSON.parse(body); } catch { /* not JSON: a proxy's page */ }
    throw Object.assign(new Error(info?.error || `${r.status} ${body}`.trim()), { status: r.status, code: info?.code });
  }
  return r;
}
