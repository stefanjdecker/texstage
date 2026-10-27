// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// What the engines of live activities share (docs/live-activities-design.md, section 8.3), in the
// evaluator's worker (stage/evaluator-worker.js): the key of a result's canonical form, a result's
// rows against a reference's, and a summary that fits into a message.
//
//   key(canonical)          the result's key: 64-bit FNV-1a of its canonical form, 16 hex digits
//   compare(result, ref)    -> {common, missing, extra}: the rows (a bag) of a result against a reference's
//   bounded(summary)        the summary with fewer rows until it fits into a message
//   cut(text)               a value as a summary shows it: at most CELL characters

export const ROWS = 20;              // rows in a summary
export const CELL = 120;             // characters of a value in it
const SUMMARY_MAX = 11000;           // bytes of JSON - a message to the server has 16 KiB (server/activity.py: 12 KiB)

export const cut = (s) => (s.length > CELL ? `${s.slice(0, CELL - 1)}…` : s);

export function bounded(summary) {
  while (JSON.stringify(summary).length > SUMMARY_MAX && summary.rows?.length) summary.rows = summary.rows.slice(0, -1);
  return summary;
}

export function compare(result, reference) {
  // in both, the reference's not here, more
  const counts = new Map();
  for (const r of reference.rows) counts.set(r, (counts.get(r) || 0) + 1);
  let common = 0;
  for (const r of result.rows) {
    const n = counts.get(r) || 0;
    if (n) {
      common += 1;
      counts.set(r, n - 1);
    }
  }
  return { common, missing: reference.rows.length - common, extra: result.rows.length - common };
}

const ENCODER = new TextEncoder();
export function key(canonical) {
  let h = 0xcbf29ce484222325n;
  for (const byte of ENCODER.encode(canonical)) {
    h ^= BigInt(byte);
    h = (h * 0x100000001b3n) & 0xffffffffffffffffn;
  }
  return h.toString(16).padStart(16, "0");
}
