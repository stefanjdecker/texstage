// SPDX-License-Identifier: Apache-2.0
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
async function setup(send){
 const timers=[],context=vm.createContext({setTimeout:(fn,delay)=>{timers.push({fn,delay});return timers.length;},clearTimeout:()=>{}});
 const module=new vm.SourceTextModule(fs.readFileSync(new URL("../src/texstage/web/stage/plugin-evaluator.js",import.meta.url),"utf8"),{context});
 await module.link(()=>new vm.SyntheticModule(["makeOutcome","validateResult"],function(){
  this.setExport("makeOutcome",()=>{});this.setExport("validateResult",()=>{});
 },{context}));
 await module.evaluate();
 const evaluator=new module.namespace.PluginEvaluator({send});
 return {evaluator,timers};
}
const tick=()=>new Promise(r=>setImmediate(r));
test("nonempty batches continue promptly after results, without increasing concurrency",async()=>{
 const sent=[],jobs=[{id:"a",epoch:1,generation:1},{id:"b",epoch:1,generation:1}];
 let work=0,active=0,peak=0;
 const {evaluator,timers}=await setup(async message=>{
  sent.push(message);return message.t==="plugin.work"?{jobs:work++===0?jobs:[]}:{accepted:true};
 });
 evaluator.evaluate=async()=>{active++;peak=Math.max(peak,active);await tick();active--;return {status:"error"};};
 await tick();await tick();await tick();
 assert.equal(peak,2);assert.equal(sent.filter(m=>m.t==="plugin.result").length,2);
 assert.equal(timers[0].delay,0);
 timers[0].fn();await tick();assert.equal(timers[1].delay,750);
 evaluator.destroy();
});
test("empty and failed polls retain backoff",async()=>{
 for(const fails of [false,true]){
  const {evaluator,timers}=await setup(async()=>{if(fails)throw Error("disconnected");return {jobs:[]};});
  await tick();assert.equal(timers[0].delay,750);evaluator.destroy();
 }
});
test("destroy during evaluation neither submits an old result nor schedules another poll",async()=>{
 let release;const sent=[];
 const {evaluator,timers}=await setup(async m=>{sent.push(m);return {jobs:[{id:"a"}]};});
 evaluator.evaluate=()=>new Promise(r=>{release=r;});
 await tick();evaluator.destroy();release({status:"error"});await tick();
 assert.equal(sent.length,1);assert.equal(timers.length,0);
});
