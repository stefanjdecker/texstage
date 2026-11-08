// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The presenter window's evaluator of the live activities' queries (docs/live-activities-design.md,
// section 8): the work the agent gets with the lease (activity.work, activity.js) - the references
// first, then each distinct query text - run in a module worker per activity (evaluator-worker.js,
// never on this window's thread: a slide change must stay quick), each with a budget of 2 s: over
// it the worker is terminated and a new one starts from the compiled module. The results go to
// the server as data (activity.result): the key of the result's canonical form, its summary when
// the server does not know the key yet, or what went wrong - in the deck's language, the window's
// (i18n's pageLanguage), which the phones speak too. Nothing of it runs in the server or on the
// phones.

import { ENGINES, engineUrl } from "/static/engines/index.js";
import { pageLanguage, pageTexts } from "/static/i18n/i18n.js";

const BUDGET_MS = 2000;
const WORKER = "/static/stage/evaluator-worker.js";

async function compile(url) {
  // the engine's WebAssembly, compiled once per window (a server that does not say
  // application/wasm: from its bytes)
  try {
    return await WebAssembly.compileStreaming(fetch(url));
  } catch {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return WebAssembly.compile(await r.arrayBuffer());
  }
}

class Runner {
  // one activity's worker: its seed loaded, its references run (again after a restart)
  constructor(spec, module, seed) {
    Object.assign(this, { spec, module, seed, refs: [], n: 0 });
    this.start();
  }

  start() {
    this.worker?.terminate();
    this.worker = new Worker(WORKER, { type: "module" });
    this.ready = new Promise((resolve, reject) => {
      this.worker.onmessage = ({ data }) => (data.t === "ready" ? resolve() : reject(new Error(data.error || pageTexts().engines.notStarted)));
      this.worker.onerror = (e) => reject(new Error(e.message || pageTexts().engines.workerFailed));
    });
    this.worker.postMessage({ t: "init", engine: this.spec.engine, module: this.module, seed: this.seed });
  }

  async eval(text, reference = false, again = false) {
    await this.ready;
    const id = ++this.n;
    const result = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve({ status: "timeout" }), BUDGET_MS);
      this.worker.onmessage = ({ data }) => {
        if (data.t === "done" && data.id === id) {
          clearTimeout(timer);
          resolve(data);
        }
      };
      this.worker.postMessage({ t: "eval", id, text, reference, language: pageLanguage() });
    });
    if (result.status === "timeout") {
      this.start();                                    // a new worker from the compiled module ...
      for (const r of this.refs) await this.eval(r, true, true);   // ... with the references again (quick)
    } else if (reference && result.status === "ok" && !again) {
      this.refs.push(text);
    }
    return result;
  }

  destroy() {
    this.worker?.terminate();
  }
}

export class Evaluator {
  constructor({ send, base }) {
    this.send = send;              // (msg) => a promise of the server's reply
    this.base = base;              // the bundle's address: /bundle/<id>/
    this.modules = new Map();      // an engine's WebAssembly (its address) -> compiled (sparql and turtle share Oxigraph's)
    this.runners = new Map();      // activity -> Runner
    this.sent = new Set();         // "activity key": summaries sent from this window
    this.busy = false;
    this.done = 0;                 // queries evaluated here (for the panel)
    this.failed = null;            // why the engine cannot run here
  }

  async runner(activity, spec) {
    let r = this.runners.get(activity);
    if (r && r.spec.seed === spec.seed) return r;
    r?.destroy();
    if (!Object.hasOwn(ENGINES, spec.engine)) throw new Error(pageTexts().engines.noEngine(spec.engine));
    const wasm = engineUrl(spec.engine, "wasm");
    if (!this.modules.has(wasm)) this.modules.set(wasm, compile(wasm));
    const module = await this.modules.get(wasm);
    const res = await fetch(this.base + spec.seed);
    if (!res.ok) throw new Error(pageTexts().engines.seed(spec.seed, res.status));
    r = new Runner(spec, module, await res.text());
    this.runners.set(activity, r);
    return r;
  }

  // the work of activity.work: {jobs: [{activity, input, text}], references: {activity: [texts]},
  // known: {activity: [keys]}, engines: {activity: {engine, seed}}}; whether there was any
  async take(work) {
    if (this.busy) return false;
    this.busy = true;
    const jobs = [];
    for (const [activity, refs] of Object.entries(work.references || {})) {
      refs.forEach((text, i) => jobs.push({ activity, reference: i, text }));
    }
    jobs.push(...(work.jobs || []));
    try {
      for (const job of jobs) {
        const spec = work.engines?.[job.activity];
        if (!spec) continue;
        let r;
        try {
          r = await (await this.runner(job.activity, spec)).eval(job.text, job.reference !== undefined);
          this.failed = null;
        } catch (err) {
          this.failed = err.message || String(err);
          console.warn("texstage: evaluator", err);
          return false;
        }
        this.done += 1;
        const msg = { t: "activity.result", activity: job.activity, status: r.status };
        if (job.reference !== undefined) msg.reference = job.reference;
        else msg.input = job.input;
        if (r.error) msg.error = r.error.slice(0, 300);
        if (r.status === "ok") {
          msg.key = r.key;
          const sent = `${job.activity} ${r.key}`;
          if (!(work.known?.[job.activity] || []).includes(r.key) && !this.sent.has(sent)) {
            msg.summary = r.summary;
            this.sent.add(sent);
          }
        }
        await this.send(msg).catch((err) => console.warn("texstage: activity.result", err));
      }
    } finally {
      this.busy = false;
    }
    return jobs.length > 0;
  }

  destroy() {
    for (const r of this.runners.values()) r.destroy();
    this.runners.clear();
  }
}
