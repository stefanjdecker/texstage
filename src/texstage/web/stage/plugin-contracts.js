// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Interpreter for the explicitly restricted, server-approved JSON Schema profile.
// No code generation, eval, remote references, or network access.
import { key, compare } from "../engines/common.js";

const own = (value, name) => Object.hasOwn(value, name);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const fail = message => { throw new Error(message); };
const stable = value => object(value)
  ? "{" + Object.keys(value).sort().map(k => JSON.stringify(k) + ":" + stable(value[k])).join(",") + "}"
  : Array.isArray(value) ? "[" + value.map(stable).join(",") + "]" : JSON.stringify(value);
const equal = (a, b) => stable(a) === stable(b);

export function jsonData(value, depth = 0) {
  if (depth > 64) fail("JSON nesting exceeds contract budget");
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Math.abs(value) > Number.MAX_SAFE_INTEGER) fail("Non-portable number");
    return;
  }
  if (typeof value !== "object") fail("Expected plain JSON data");
  if (Array.isArray(value)) {
    if (Object.getOwnPropertyNames(value).length !== value.length + 1 ||
        Object.getOwnPropertySymbols(value).length) fail("Invalid JSON array");
    for (let i = 0; i < value.length; i++) {
      const d = Object.getOwnPropertyDescriptor(value, String(i));
      if (!d || !own(d, "value")) fail("Invalid JSON array element");
      jsonData(d.value, depth + 1);
    }
    return;
  }
  if (![Object.prototype, null].includes(Object.getPrototypeOf(value)) ||
      Object.getOwnPropertySymbols(value).length) fail("Expected a plain JSON object");
  for (const d of Object.values(Object.getOwnPropertyDescriptors(value))) {
    if (!d.enumerable || !own(d, "value")) fail("Invalid JSON object property");
    jsonData(d.value, depth + 1);
  }
}

// Same ASCII JSON budget as Python's canonical(..., ensure_ascii=True).
export const jsonSize = value => JSON.stringify(value).replace(/[^\x00-\x7f]/g,
  c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0")).length;

export function conforms(schema, value) {
  let visits = 0;
  const types = {
    object, array: Array.isArray, string: v => typeof v === "string",
    boolean: v => typeof v === "boolean", null: v => v === null,
    number: v => typeof v === "number" && Number.isFinite(v),
    integer: v => typeof v === "number" && Number.isSafeInteger(v),
  };
  const check = (s, v, depth = 0) => {
    if (++visits > 100000 || depth > 64) fail("Schema validation budget exceeded");
    if (typeof s === "boolean") return s;
    if (!object(s)) fail("Invalid schema");
    if (own(s, "$ref")) {
      if (!s.$ref.startsWith("#/")) fail("Invalid schema reference");
      let target = schema;
      for (const part of s.$ref.slice(2).split("/")) {
        const k = part.replace(/~1/g, "/").replace(/~0/g, "~");
        if (Array.isArray(target) ? !/^(0|[1-9][0-9]*)$/.test(k) || !own(target, k)
            : !object(target) || !own(target, k)) fail("Unresolved schema reference");
        target = target[k];
      }
      if (!check(target, v, depth + 1)) return false;
    }
    if (own(s, "type") && !(Array.isArray(s.type) ? s.type : [s.type]).some(t => types[t]?.(v))) return false;
    if (own(s, "const") && !equal(s.const, v)) return false;
    if (own(s, "enum") && !s.enum.some(candidate => equal(candidate, v))) return false;
    if (s.allOf && !s.allOf.every(child => check(child, v, depth + 1))) return false;
    if (s.anyOf && !s.anyOf.some(child => check(child, v, depth + 1))) return false;
    if (s.oneOf && s.oneOf.filter(child => check(child, v, depth + 1)).length !== 1) return false;
    if (own(s, "not") && check(s.not, v, depth + 1)) return false;
    if (typeof v === "number") {
      if (own(s, "minimum") && v < s.minimum || own(s, "maximum") && v > s.maximum ||
          own(s, "exclusiveMinimum") && v <= s.exclusiveMinimum ||
          own(s, "exclusiveMaximum") && v >= s.exclusiveMaximum) return false;
    }
    if (typeof v === "string") {
      const length = [...v].length;
      if (own(s, "minLength") && length < s.minLength || own(s, "maxLength") && length > s.maxLength) return false;
    }
    if (Array.isArray(v)) {
      if (own(s, "minItems") && v.length < s.minItems || own(s, "maxItems") && v.length > s.maxItems) return false;
      if (s.uniqueItems && new Set(v.map(stable)).size !== v.length) return false;
      const prefix = s.prefixItems || [];
      if (!prefix.every((child, i) => i >= v.length || check(child, v[i], depth + 1))) return false;
      if (own(s, "items") && !v.slice(prefix.length).every(x => check(s.items, x, depth + 1))) return false;
    }
    if (object(v)) {
      const keys = Object.keys(v);
      if (own(s, "minProperties") && keys.length < s.minProperties ||
          own(s, "maxProperties") && keys.length > s.maxProperties ||
          s.required?.some(k => !own(v, k))) return false;
      for (const k of keys) {
        if (own(s.properties || {}, k)) {
          if (!check(s.properties[k], v[k], depth + 1)) return false;
        } else if (own(s, "additionalProperties") && !check(s.additionalProperties, v[k], depth + 1)) return false;
      }
    }
    return true;
  };
  return check(schema, value);
}

function contract(job) {
  const c = job.engine.result_contract;
  if (!c || c.version !== 2 || c.data_max !== 8192 || c.outcome_max !== 12288) fail("Unsupported engine result contract");
  return c;
}

function facts(result, job) {
  const c = contract(job), summary = result.summary;
  if (!conforms(c.summary_schema, summary) || !job.engine.summary_kinds.includes(summary.kind)) fail("Invalid engine summary");
  if (own(summary, "rows")) {
    const width = summary.kind === "graph" ? 3 : summary.columns.length;
    if (summary.rows.length > summary.count || summary.rows.some(row => row.length !== width)) fail("Invalid summary dimensions");
  }
  if (own(result, "data")) {
    if (c.data_schema === null || !own(job.engine, "result_data_schema")) fail("Undeclared engine data");
    if (jsonSize(result.data) > c.data_max) fail("Engine data exceeds budget");
    if (!conforms(c.data_schema, result.data)) fail("Invalid engine data");
  }
}

export function validateResult(result, job) {
  jsonData(result);
  if (!object(result) || !["ok", "syntax", "error", "refused"].includes(result.status)) fail("Invalid engine status");
  if (result.status !== "ok") {
    if (Object.keys(result).length !== 1) fail("Failed evaluations carry only status");
    return result;
  }
  if (Object.keys(result).some(k => !["status", "canonical", "summary", "rows", "data"].includes(k)) ||
      typeof result.canonical !== "string" || jsonSize(result.canonical) > 1024 * 1024) fail("Invalid engine result");
  if (own(result, "rows") && (!Array.isArray(result.rows) || result.rows.some(r => typeof r !== "string") ||
      jsonSize(result.rows) > 1024 * 1024)) fail("Invalid canonical rows");
  facts(result, job);
  // Check the actual transport form's combined budget, before leaving the worker.
  validateOutcome({ status: "ok", key: key(result.canonical), namespace: job.namespace,
    summary: result.summary, ...(own(result, "data") ? { data: result.data } : {}),
    ...(job.binding.references?.length ? { matches: false } : {}) }, job);
  return result;
}

export function validateOutcome(outcome, job) {
  jsonData(outcome);
  const c = contract(job);
  if (!object(outcome) || jsonSize(outcome) > c.outcome_max ||
      !["ok", "syntax", "error", "refused", "timeout"].includes(outcome.status)) fail("Invalid evaluation outcome");
  if (outcome.status !== "ok") {
    if (Object.keys(outcome).length !== 1) fail("Failed evaluations carry only status");
    return outcome;
  }
  if (Object.keys(outcome).some(k => !["status", "key", "namespace", "summary", "matches", "data"].includes(k)) ||
      typeof outcome.key !== "string" || !/^[a-f0-9]{16}$/.test(outcome.key) || outcome.namespace !== job.namespace ||
      own(outcome, "matches") !== !!job.binding.references?.length ||
      own(outcome, "matches") && typeof outcome.matches !== "boolean") fail("Invalid outcome identity");
  facts(outcome, job);
  return outcome;
}

export function makeOutcome(result, references, job) {
  validateResult(result, job);
  if (result.status !== "ok") return { status: result.status };
  references.forEach(reference => {
    validateResult(reference, job);
    if (reference.status !== "ok") fail("Invalid reference result");
  });
  const summary = { ...result.summary };
  if (references[0]?.rows && result.rows) summary.diff = compare(result, references[0]);
  return validateOutcome({ status: "ok", key: key(result.canonical), namespace: job.namespace, summary,
    ...(own(result, "data") ? { data: result.data } : {}),
    ...(references.length ? { matches: references.some(r => r.canonical === result.canonical) } : {}) }, job);
}
