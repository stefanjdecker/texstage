// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const settle = () => new Promise(resolve => setImmediate(resolve));
async function harness(replies) {
  const timers = [], messages = [], running = [];
  const context = vm.createContext({setTimeout:(fn,ms) => { const t={fn,ms}; timers.push(t); return t; },
    clearTimeout:t => { const i=timers.indexOf(t); if(i>=0) timers.splice(i,1); }});
  const contracts = new vm.SyntheticModule(['makeOutcome','validateResult'], function() {
    this.setExport('makeOutcome', x=>x); this.setExport('validateResult', ()=>{});
  },{context});
  const module = new vm.SourceTextModule(fs.readFileSync(new URL('../src/texstage/web/stage/plugin-evaluator.js',import.meta.url),'utf8'),{context});
  await module.link(()=>contracts); await module.evaluate();
  const Evaluator = module.namespace.PluginEvaluator;
  class Measured extends Evaluator {
    evaluate(job) { return new Promise(resolve=>running.push({job,resolve})); }
  }
  const evaluator = new Measured({send:async message=>{
    messages.push(message);
    if(message.t==='plugin.work') { const next=replies.shift(); if(next instanceof Error) throw next; return {jobs:next}; }
    return {accepted:true};
  }});
  await settle(); return {evaluator,timers,messages,running};
}
test('busy polling waits for the bounded batch and idle/error polling backs off',async()=>{
  const h=await harness([[{id:'one'},{id:'two'}],[],new Error('disconnected')]);
  assert.equal(h.running.length,2); assert.equal(h.timers.length,0);
  h.running[0].resolve({status:'error'}); await settle();
  assert.equal(h.timers.length,0); assert.equal(h.messages.filter(m=>m.t==='plugin.result').length,1);
  h.running[1].resolve({status:'error'}); await settle();
  assert.equal(h.timers[0].ms,0);
  await h.timers.shift().fn(); await settle(); assert.equal(h.timers[0].ms,750);
  await h.timers.shift().fn(); await settle(); assert.equal(h.timers[0].ms,750);
  h.evaluator.destroy(); assert.equal(h.timers.length,0);
});
test('destroy during evaluation prevents late result submission and polling',async()=>{
  const h=await harness([[{id:'one'}]]);
  h.evaluator.destroy(); h.running[0].resolve({status:'error'}); await settle();
  assert.equal(h.messages.filter(m=>m.t==='plugin.result').length,0);
  assert.equal(h.timers.length,0);
});
