// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The engines of live activities (docs/live-activities-design.md, section 8.3), by the name a deck
// gives (engine=): the module the evaluator's worker imports (stage/evaluator-worker.js), and the
// WebAssembly that the window compiles once and hands to the worker (stage/evaluator.js) - the
// worker reaches no network. The build's and the server's half of the table - the seed's file
// types, the tokens every bar offers - is texstage/engines.py.
//
// An engine module exports
//   NAME
//   start(wasm)             its library, from the compiled WebAssembly module (async)
//   load(lib, seed)         the seed's text -> the state its queries run on
//   evaluate(state, text)   -> {status: ok | syntax | error | refused, error?, canonical?, rows?, summary?}
// and the worker does the rest with common.js: the key of `canonical`, the comparison of `rows`.
// Engines may share a library: turtle parses with the SPARQL engine's Oxigraph.

export const ENGINES = {
  sparql: { module: "./sparql.js", wasm: "../vendor/oxigraph/web_bg.wasm" },
  sql: { module: "./sql.js", wasm: "../vendor/sqljs/sql-wasm-browser.wasm" },
  turtle: { module: "./turtle.js", wasm: "../vendor/oxigraph/web_bg.wasm" },
};

// an engine's file as an address (`module` or `wasm`)
export const engineUrl = (name, what) => new URL(ENGINES[name][what], import.meta.url).href;
