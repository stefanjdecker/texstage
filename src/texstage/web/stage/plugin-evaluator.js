// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
import { makeOutcome, validateResult } from "./plugin-contracts.js";

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
      const assets = {};
      for (const [name, url] of Object.entries(job.engine.assets)) {
        if (!url.startsWith(job.engine.url.slice(0, 74)) || url.includes("..")) throw new Error("error");
        const r = await fetch(url, { signal: AbortSignal.timeout(10000) });
        if (!r.ok) throw new Error("error");
        assets[name] = await r.arrayBuffer();
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
    try {
      const { jobs } = await this.client.send({ t: "plugin.work" });
      await Promise.all((jobs || []).map(async job => {
        const outcome = await this.evaluate(job);
        if (!this.stopped) await this.client.send({ t: "plugin.result", result: {
          id: job.id, generation: job.generation, epoch: job.epoch, outcome } });
      }));
    } catch { /* disconnections are retried; the durable lease can be replaced */ }
    if (!this.stopped) this.timer = setTimeout(() => this.poll(), 750);
  }
  destroy() { this.stopped = true; clearTimeout(this.timer); for (const w of this.workers) w.terminate(); this.workers.clear(); }
}
