// SPDX-License-Identifier: Apache-2.0
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { conforms, jsonData, jsonSize, validateResult, validateOutcome, makeOutcome } from "../src/texstage/web/stage/plugin-contracts.js";

const fixture = JSON.parse(fs.readFileSync(process.env.TEXSTAGE_CONTRACT_FIXTURE, "utf8"));
const job = {
  namespace: "a".repeat(64), binding: { references: [] },
  engine: { summary_kinds: ["text", "select", "graph", "ask"], result_data_schema: "result.json",
    result_contract: { version: 2, summary_schema: fixture.summary, data_schema: fixture.schema,
      data_schema_digest: "b".repeat(64), data_max: 8192, outcome_max: 12288 } },
};
const raw = () => ({ status: "ok", canonical: "schedule-a",
  summary: { kind: "text", text: "Analyzed" }, data: { valid: true, order: ["a", "b"] } });

for (const c of fixture.cases) test("schema parity: " + c.name, () => {
  assert.equal(conforms(c.schema, c.value), c.valid);
});

test("typed facts survive worker validation and transport; equality is optional", () => {
  const result = raw(), outcome = makeOutcome(validateResult(result, job), [], job);
  assert.deepEqual(outcome.data, result.data);
  assert.ok(!Object.hasOwn(outcome, "matches"));
  assert.deepEqual(validateOutcome(outcome, job), outcome);
  const other = raw(); other.canonical = "schedule-b"; other.data.order.reverse();
  const second = makeOutcome(other, [], job);
  assert.notEqual(outcome.key, second.key);
  assert.ok(second.data.valid);
});

test("matches means canonical equality, not validity", () => {
  const referenced = structuredClone(job); referenced.binding.references = ["reference"];
  const reference = raw(), result = raw(); result.canonical = "different";
  const outcome = makeOutcome(result, [reference], referenced);
  assert.equal(outcome.matches, false);
  assert.equal(outcome.data.valid, true);
  assert.throws(() => validateOutcome({ ...outcome, matches: true }, job));
});

test("undeclared and invalid data fail at worker and transport boundaries", () => {
  for (const data of [{ valid: "yes", order: ["a"] }, { valid: true, order: ["a", "a"] },
                      { valid: true, order: ["a"], secret: "not part of contract" }]) {
    assert.throws(() => validateResult({ ...raw(), data }, job));
    const valid = makeOutcome(raw(), [], job);
    assert.throws(() => validateOutcome({ ...valid, data }, job));
  }
  const old = structuredClone(job); delete old.engine.result_data_schema; old.engine.result_contract.data_schema = null;
  assert.throws(() => validateResult(raw(), old));
  const summaryOnly = raw(); delete summaryOnly.data;
  assert.equal(makeOutcome(summaryOnly, [], old).status, "ok");
});

test("complete summary schema and row dimensions are enforced", () => {
  for (const summary of [{kind:"text"}, {kind:"text",text:"x",html:"secret"},
      {kind:"ask",boolean:"yes"}, {kind:"graph",count:1,rows:[["s","p"]]},
      {kind:"select",count:0,columns:["x"],rows:[["1"]]}]) {
    assert.throws(() => validateResult({ ...raw(), summary }, job));
  }
});

test("combined, canonical and ASCII JSON budgets reject oversized values", () => {
  assert.equal(jsonSize("😀"), 14);
  assert.throws(() => validateResult({ ...raw(), data: { valid:true, order:["ü".repeat(1400)] } }, job));
  assert.throws(() => validateResult({ ...raw(), canonical: "x".repeat(1024 * 1024) }, job));
  assert.throws(() => validateResult({ ...raw(), summary: {kind:"text",text:"x".repeat(8000)},
    data: {valid:true,order:["y".repeat(5000)]} }, job));
});

test("non-JSON values cannot be normalized into a plausible result", () => {
  const accessor = { get x() { throw Error("getter must not execute"); } };
  for (const value of [NaN, Infinity, 9007199254740992, 1n, undefined, new Date(), [,], accessor,
                       {x:undefined}, Object.assign([1], {extra:2})]) assert.throws(() => jsonData(value));
  const cycle = {}; cycle.self = cycle; assert.throws(() => jsonData(cycle));
});

test("failure statuses carry no data, error strings or stale summaries", () => {
  assert.deepEqual(makeOutcome({status:"syntax"}, [], job), {status:"syntax"});
  assert.throws(() => validateResult({status:"error",data:{}}, job));
  assert.throws(() => validateResult({status:"ok",canonical:"x",summary:{kind:"text",text:"x"},unknown:1}, job));
  assert.throws(() => validateOutcome({status:"timeout",summary:{kind:"text",text:"x"}}, job));
});
