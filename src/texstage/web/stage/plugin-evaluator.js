// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
import { makeOutcome, validateResult } from "./plugin-contracts.js";

// Only immutable, provider-pinned resource bytes are shared. postMessage clones
// each ArrayBuffer into a fresh job worker; no engine or answer state is reused.
class AssetCache {
  constructor() { this.entries = new Map(); this.bytes = 0; }
  remove(url) {
    const entry = this.entries.get(url);
    if (entry) { this.bytes -= entry.bytes; this.entries.delete(url); }
  }
  trim() {
    while (this.entries.size > 64 || this.bytes > 16 * 1024 * 1024) this.remove(this.entries.keys().next().value);
  }
  get(url) {
    let entry = this.entries.get(url);
    if (entry) {
      this.entries.delete(url); this.entries.set(url, entry);
      return entry.promise;
    }
    entry = {bytes:0}; this.entries.set(url, entry); this.trim();
    entry.promise = (async () => {
      try {
        const response = await fetch(url, {signal:AbortSignal.timeout(10000)});
        if (!response.ok) throw new Error("error");
        const bytes = await response.arrayBuffer();
        if (this.entries.get(url) === entry) {
          if (bytes.byteLength > 16 * 1024 * 1024) this.remove(url);
          else { entry.bytes = bytes.byteLength; this.bytes += entry.bytes; this.trim(); }
        }
        return bytes;
      } catch (error) {
        if (this.entries.get(url) === entry) this.remove(url);
        throw error;
      }
    })();
    return entry.promise;
  }
  clear() { this.entries.clear(); this.bytes = 0; }
}

export class PluginEvaluator {
  constructor(client) { this.client = client; this.workers = new Set(); this.stopped = false; this.poll(); }
  async evaluate(job) {
    const worker = new Worker("/static/stage/plugin-evaluator-worker.js", { type: "module" });
    this.workers.add(worker);
    const exchange = (message, timeout) => new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("timeout")), timeout);
      worker.onmessage = e => { clearTimeout(timer); resolve(e.data); };
      worker.onerror = () => { clearTimeout(timer); reject(new Error("error")); };
      worker.postMessage(message);
    });
    try {
      if (!/^\/plugins\/[a-f0-9]{64}\/[a-zA-Z0-9_./-]+\.mjs$/.test(job.engine.url) || job.engine.url.includes("..")) throw new Error("error");
      this.assets ||= new AssetCache();
      const assets = {};
      for (const [name, url] of Object.entries(job.engine.assets)) {
        if (!url.startsWith(job.engine.url.slice(0, 74)) || url.includes("..")) throw new Error("error");
        assets[name] = await this.assets.get(url);
      }
      if ((await exchange({ t: "init", job, assets }, 30000)).t !== "ready") throw new Error("error");
      const references = [];
      for (const text of job.binding.references || []) {
        const { result } = await exchange({ t: "eval", text }, 2000);
        validateResult(result, job);
        if (result.status !== "ok") throw new Error("error");
        references.push(result);
      }
      const { result } = await exchange({ t: "eval", text: job.text }, 2000);
      return makeOutcome(result, references, job);
    } catch (e) { return { status: e.message === "timeout" ? "timeout" : "error" }; }
    finally { worker.terminate(); this.workers.delete(worker); }
  }
  async poll() {
    if (this.stopped) return;
    let busy = false;
    try {
      const { jobs, more_work } = await this.client.send({ t: "plugin.work" });
      busy = Boolean(jobs?.length || more_work);
      await Promise.all((jobs || []).map(async job => {
        const outcome = await this.evaluate(job);
        if (!this.stopped) await this.client.send({ t: "plugin.result", result: {
          id: job.id, generation: job.generation, epoch: job.epoch, outcome } });
      }));
    } catch { busy = false; /* reconnect retries keep the idle backoff */ }
    // Keep draining a busy queue with the same two-job lease and worker limits.
    // Empty queues and transport errors retain the ordinary polling backoff.
    if (!this.stopped) this.timer = setTimeout(() => this.poll(), busy ? 0 : 750);
  }
  destroy() { this.stopped = true; clearTimeout(this.timer); for (const w of this.workers) w.terminate(); this.workers.clear(); this.assets?.clear(); }
}
