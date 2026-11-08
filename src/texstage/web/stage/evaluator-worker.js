// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The evaluator's worker (evaluator.js; docs/live-activities-design.md, section 8.2): an engine
// (web/engines/index.js) over an activity's seed, one query at a time. The server serves this
// script with Content-Security-Policy: connect-src 'none' - a student's query reaches no network -,
// and the window hands it the engine's compiled WebAssembly module and the seed.
//
//   {t: "init", engine, module, seed}            -> {t: "ready"} | {t: "failed", error}
//   {t: "eval", id, text, reference?, language?}  -> {t: "done", id, status, error?, key?, summary?}
//                                                    (error in the deck's language: the window's)
// A reference's rows are kept: every later result's summary says how it compares (summary.diff).

import { ENGINES, engineUrl } from "/static/engines/index.js";
import { compare, key } from "/static/engines/common.js";

let engine = null;
let state = null;
let reference = null;

self.onmessage = async ({ data }) => {
  if (data.t === "init") {
    try {
      if (!Object.hasOwn(ENGINES, data.engine)) throw new Error(`no engine ${data.engine}`);
      engine = await import(engineUrl(data.engine, "module"));
      state = engine.load(await engine.start(data.module), data.seed);
      reference = null;
      postMessage({ t: "ready" });
    } catch (e) {
      postMessage({ t: "failed", error: String(e?.message ?? e) });
    }
    return;
  }
  if (data.t !== "eval") return;
  let out;
  try {
    const r = engine.evaluate(state, data.text, data.language);
    out = { t: "done", id: data.id, status: r.status };
    if (r.error) out.error = r.error;
    if (r.status === "ok") {
      out.key = key(r.canonical);
      out.summary = r.summary;
      if (data.reference) reference ??= r;
      else if (reference) out.summary.diff = compare(r, reference);
    }
  } catch (e) {
    out = { t: "done", id: data.id, status: "error", error: String(e?.message ?? e) };
  }
  postMessage(out);
};
