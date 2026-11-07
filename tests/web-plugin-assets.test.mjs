// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const prefix = '/plugins/' + 'a'.repeat(64) + '/';
const job = (names=['bytes.bin'], base=prefix) => ({engine:{url:base+'engine.mjs',
  assets:Object.fromEntries(names.map(name=>[name,base+name]))},binding:{},text:'answer'});
async function harness(fetcher = async()=>new Uint8Array([7]).buffer) {
  const requests=[], workers=[];
  class Worker {
    constructor() { this.terminated=false; workers.push(this); }
    postMessage(message) {
      const copy=structuredClone(message);
      if(copy.t==='init') {
        this.assets=Object.fromEntries(Object.entries(copy.assets).map(([k,b])=>[k,{size:b.byteLength,first:new Uint8Array(b)[0]}]));
        // A provider mutates its own clone. Later jobs must still see byte 7.
        for(const b of Object.values(copy.assets)) if(b.byteLength) new Uint8Array(b)[0]=99;
      }
      queueMicrotask(()=>this.onmessage?.({data:copy.t==='init' ? {t:'ready'} : {t:'result',result:{status:'ok'}}}));
    }
    terminate() { this.terminated=true; }
  }
  const context=vm.createContext({Worker,setTimeout,clearTimeout,AbortSignal,
    fetch:async(url,options)=>{requests.push(url); assert(options.signal instanceof AbortSignal);
      const value=await fetcher(url); return value?.response || {ok:true,arrayBuffer:async()=>value};}});
  const contract=new vm.SyntheticModule(['makeOutcome','validateResult'],function(){
    this.setExport('makeOutcome',value=>value); this.setExport('validateResult',value=>value);
  },{context});
  const module=new vm.SourceTextModule(fs.readFileSync(new URL('../src/texstage/web/stage/plugin-evaluator.js',import.meta.url),'utf8'),{context});
  await module.link(()=>contract); await module.evaluate();
  const evaluator=Object.create(module.namespace.PluginEvaluator.prototype);
  evaluator.workers=new Set(); evaluator.stopped=true;
  return {evaluator,requests,workers};
}
test('concurrent and later jobs share downloads, not mutable worker state',async()=>{
  const h=await harness();
  const jobs=await Promise.all([h.evaluator.evaluate(job()),h.evaluator.evaluate(job())]);
  assert(jobs.every(r=>r.status==='ok')); assert.equal(h.requests.length,1);
  assert.equal((await h.evaluator.evaluate(job())).status,'ok');
  assert.equal(h.requests.length,1); assert.equal(h.workers.length,3);
  assert(h.workers.every(w=>w.terminated && w.assets['bytes.bin'].first===7));
  assert.equal(h.evaluator.workers.size,0);
  h.evaluator.destroy(); assert.equal(h.evaluator.assets.entries.size,0);
});
test('failed downloads are evicted and can recover',async()=>{
  let attempt=0; const h=await harness(async()=>{if(++attempt===1) throw new Error('offline'); return new ArrayBuffer(1);});
  assert.equal((await h.evaluator.evaluate(job())).status,'error');
  assert.equal(h.evaluator.assets.entries.size,0);
  assert.equal((await h.evaluator.evaluate(job())).status,'ok');
  assert.equal(h.requests.length,2); h.evaluator.destroy();
});
test('unsuccessful HTTP responses are not cached',async()=>{
  let attempt=0;
  const h=await harness(async()=>++attempt===1 ? {response:{ok:false}} : new ArrayBuffer(1));
  assert.equal((await h.evaluator.evaluate(job())).status,'error');
  assert.equal((await h.evaluator.evaluate(job())).status,'ok');
  assert.equal(h.requests.length,2); h.evaluator.destroy();
});
test('complete provider payload URL is part of the cache identity',async()=>{
  const h=await harness();
  await h.evaluator.evaluate(job());
  await h.evaluator.evaluate(job(['bytes.bin'],'/plugins/'+'b'.repeat(64)+'/'));
  assert.equal(h.requests.length,2); h.evaluator.destroy();
});
test('approval checks precede cache access or any fetch',async()=>{
  const h=await harness();
  await h.evaluator.evaluate(job());
  for(const url of ['https://example.invalid/engine.mjs','/plugins/'+'a'.repeat(64)+'/../engine.mjs']) {
    const j=job(); j.engine.url=url;
    assert.equal((await h.evaluator.evaluate(j)).status,'error');
  }
  for(const url of [prefix+'../bytes.bin','/plugins/'+'b'.repeat(64)+'/bytes.bin']) {
    const j=job(); j.engine.assets['bytes.bin']=url;
    assert.equal((await h.evaluator.evaluate(j)).status,'error');
  }
  assert.equal(h.requests.length,1); assert(h.workers.every(w=>w.terminated)); h.evaluator.destroy();
});
test('LRU entry bound retains recently used resources',async()=>{
  const h=await harness();
  for(let i=0;i<64;i++) await h.evaluator.evaluate(job([i+'.bin']));
  await h.evaluator.evaluate(job(['0.bin']));
  await h.evaluator.evaluate(job(['64.bin']));
  await h.evaluator.evaluate(job(['0.bin']));
  assert.equal(h.requests.length,65);
  await h.evaluator.evaluate(job(['1.bin'])); assert.equal(h.requests.length,66);
  assert.equal(h.evaluator.assets.entries.size,64); h.evaluator.destroy();
});
test('byte budget evicts entries and oversized resources are not retained',async()=>{
  const h=await harness(async()=>new ArrayBuffer(9*1024*1024));
  await h.evaluator.evaluate(job(['one.bin','two.bin']));
  assert.equal(h.evaluator.assets.bytes,9*1024*1024);
  await h.evaluator.evaluate(job(['one.bin'])); assert.equal(h.requests.length,3);
  h.evaluator.destroy(); assert.equal(h.evaluator.assets.bytes,0);
  const big=await harness(async()=>new ArrayBuffer(16*1024*1024+1));
  for(let i=0;i<2;i++) assert.equal((await big.evaluator.evaluate(job())).status,'ok');
  assert.equal(big.requests.length,2); assert.equal(big.evaluator.assets.bytes,0);
  assert.equal(big.evaluator.assets.entries.size,0); big.evaluator.destroy();
});
test('late downloads cannot repopulate a destroyed cache',async()=>{
  let finish;
  const h=await harness(async url=>url.endsWith('late.bin') ? new Promise(resolve=>finish=resolve) : new ArrayBuffer(1));
  await h.evaluator.evaluate(job());
  const pending=h.evaluator.assets.get(prefix+'late.bin');
  h.evaluator.destroy(); finish(new ArrayBuffer(3)); await pending;
  assert.equal(h.evaluator.assets.entries.size,0); assert.equal(h.evaluator.assets.bytes,0);
});
