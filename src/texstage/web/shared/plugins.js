// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Experimental API 1 host: isolated mounts and role-filtered full views.
const approved = (url) => /^\/plugins\/[a-f0-9]{64}\/[a-zA-Z0-9_./-]+\.mjs$/.test(url) && !url.includes("..");
const requestID = () => [...crypto.getRandomValues(new Uint8Array(16))].map(x => x.toString(16).padStart(2, "0")).join("");
// Live view revisions do not change a mount's identity. Resource/public changes do.
const stable = value => JSON.stringify(value, (_key, v) => v && typeof v === "object" && !Array.isArray(v)
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const identity = (d, surface, role, language) => stable([d.type, d.item, d.modules[surface],
  d.public, d.assets || {}, role, language || "en"]);
const commandError = (code, receipt) => Object.assign(new Error(code), { code, ...(receipt ? { receipt } : {}) });

class Surface {
  constructor({ parent, descriptor, surface, role, send, clock, language }) {
    Object.assign(this, { descriptor, surface, role, send });
    this.identity = identity(descriptor, surface, role, language);
    this.controller = new AbortController();
    this.root = document.createElement("div");
    this.root.className = `texstage-plugin ${surface}`;
    parent.append(this.root);
    const overlay = surface.endsWith("overlay");
    if (overlay) Object.assign(this.root.style, { position: "absolute", inset: "0", pointerEvents: "none" });
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe(parent);
    const url = descriptor.modules[surface];
    this.ready = (async () => {
      if (!approved(url)) throw new Error("Unapproved plugin module");
      const module = await import(url);
      if (this.controller.signal.aborted) return;
      const ctx = { container: this.root, item: { id: descriptor.item, ...descriptor.public }, role, surface,
        language: language || "en", clock: clock || Date.now, signal: this.controller.signal,
        resolveAsset: (name) => {
          if (Object.hasOwn(descriptor.assets || {}, name)) return descriptor.assets[name];
          throw new Error(`Undeclared renderer asset: ${name}`);
        },
        dispatch: (operation, payload) => this.dispatch(operation, payload) };
      this.mount = module.mount(ctx);
      if (!this.mount || typeof this.mount.update !== "function" || typeof this.mount.destroy !== "function" ||
          (overlay && typeof this.mount.place !== "function") || this.mount.then) throw new Error("Invalid renderer contract");
      this.draw();
    })().catch(() => this.fail());
  }
  dispatch(operation, payload) {
    if (this.role === "projector" || this.controller.signal.aborted || !this.state) return Promise.reject(commandError("read-only"));
    const command = { type: this.descriptor.type, item: this.descriptor.item, operation, payload,
      epoch: this.state.epoch, expected_revision: this.state.revision, request_id: requestID() };
    // Client.send retains this exact envelope across reconnects and lost ACKs.
    return this.send({ t: "plugin.command", command }).then(r => {
      if (!r.receipt?.accepted) throw commandError(r.receipt?.error || "plugin", r.receipt);
      return r.receipt;
    });
  }
  update(state) {
    if (!state || (this.state && (state.epoch < this.state.epoch ||
        (state.epoch === this.state.epoch && state.revision < this.state.revision)))) return;
    this.state = state; this.draw();
  }
  place(rects) { this.rects = rects; this.draw(); }
  draw() {
    if (!this.mount || !this.state || this.controller.signal.aborted) return;
    try {
      if (this.surface.endsWith("overlay")) {
        if (!this.rects) return;
        const { width, height } = this.root.parentElement.getBoundingClientRect();
        const rects = Object.fromEntries(Object.entries(this.rects).map(([k, r]) => [k,
          { x: r.x * width, y: r.y * height, w: r.w * width, h: r.h * height }]));
        this.mount.place(rects);
      }
      this.mount.update(this.state);
    } catch { this.fail(); }
  }
  fail() {
    if (this.controller.signal.aborted) return;
    this.destroy(false);
    if (this.role === "presenter") {
      this.root.textContent = "Plugin view unavailable. The static slide is still usable.";
      this.root.setAttribute("role", "status");
    }
  }
  destroy(remove = true) {
    if (!this.controller.signal.aborted) {
      this.controller.abort(); this.observer.disconnect();
      try { this.mount?.destroy(); } catch { /* preserve the host */ }
      this.mount = null;
    }
    if (remove) this.root.remove();
  }
}

export class PluginBox {
  constructor({ id, type, layer, controls, host, clock, language }) {
    Object.assign(this, { id, type, layer, controls, host, clock, language });
    this.surfaces = new Map();
  }
  update(state) {
    const d = state.plugins?.items.find(d => d.type === this.type && d.item === this.id);
    if (!d) { this.destroy(); return; }
    for (const [surface, view] of this.surfaces) {
      if (!d.modules[surface] || view.identity !== identity(d, surface, this.host.role, this.language)) {
        view.destroy(); this.surfaces.delete(surface);
      }
    }
    for (const surface of Object.keys(d.modules)) {
      let view = this.surfaces.get(surface);
      if (!view) {
        view = new Surface({ parent: surface.endsWith("controls") ? (this.host.pluginControls || this.controls) : this.layer,
          descriptor: d, surface, role: this.host.role, send: this.host.read || this.host.send,
          clock: this.clock, language: this.language });
        this.surfaces.set(surface, view);
      }
      view.place(this.rects || {}); view.update(d.views[surface]);
    }
  }
  place(rects) { this.rects = rects; for (const v of this.surfaces.values()) v.place(rects); }
  destroy() { for (const v of this.surfaces.values()) v.destroy(); this.surfaces.clear(); }
  tick() {}
  key() { return false; }
}

export class PluginScreen {
  constructor({ root, client }) { Object.assign(this, { root, client }); this.views = new Map(); }
  update(state) {
    const keep = new Set();
    for (const d of state.plugins?.items || []) {
      if (!d.modules["participant-input"]) continue;
      const key = `${d.type}:${d.item}`; keep.add(key);
      const existing = this.views.get(key);
      if (existing && existing.identity !== identity(d, "participant-input", "participant", state.language)) {
        existing.destroy(); this.views.delete(key);
      }
      if (!this.views.has(key)) this.views.set(key, new Surface({ parent: this.root, descriptor: d,
        surface: "participant-input", role: "participant", send: msg => this.client.send(msg), language: state.language }));
      this.views.get(key).update(d.views["participant-input"]);
    }
    for (const [key, v] of this.views) if (!keep.has(key)) { v.destroy(); this.views.delete(key); }
  }
  destroy() { for (const v of this.views.values()) v.destroy(); this.views.clear(); }
}
