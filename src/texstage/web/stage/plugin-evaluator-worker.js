// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Dedicated to one leased job. Network is blocked by the host's worker CSP.
import { validateResult } from "./plugin-contracts.js";
let engine, library, job;
self.onmessage = async ({ data }) => {
  try {
    if (data.t === "init") {
      job = data.job;
      if (!/^\/plugins\/[a-f0-9]{64}\/[a-zA-Z0-9_./-]+\.mjs$/.test(job.engine.url) || job.engine.url.includes("..")) throw new Error("Unapproved engine");
      engine = await import(job.engine.url);
      for (const method of ["start", "load", "evaluate", "dispose"]) if (typeof engine[method] !== "function") throw new Error("Invalid engine contract");
      library = await engine.start({ assets: data.assets });
      postMessage({ t: "ready" }); return;
    }
    if (data.t !== "eval") return;
    let state, result;
    try {
      state = await engine.load(library, job.binding.seed || "", job.binding.options || {});
      result = validateResult(await engine.evaluate(state, data.text, { language: "en" }), job);
    } finally {
      if (state !== undefined) await engine.dispose(state);
    }
    postMessage({ t: "result", result });
  } catch {
    postMessage({ t: "result", result: { status: "error" } });
  }
};
