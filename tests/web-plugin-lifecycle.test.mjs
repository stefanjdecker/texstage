// SPDX-License-Identifier: Apache-2.0
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
class Node {
  constructor() { this.style = {}; this.children = []; }
  append(node) { this.children.push(node); node.parentElement = this; }
  setAttribute() {}
  getBoundingClientRect() { return {width:1000,height:500}; }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(n => n !== this); }
}
const url = "/plugins/" + "a".repeat(64) + "/example/view.mjs";
function descriptor() {
  return {type:"example.plane", item:"one", public:{a:1,b:2}, assets:{},
    modules:{"presenter-overlay":url, "presenter-controls":url, "participant-input":url},
    views:Object.fromEntries(["presenter-overlay","presenter-controls","participant-input"].map(k => [k,{epoch:1,revision:1,data:{}}]))};
}
async function harness(waitImport = async () => {}) {
  const mounts = [], contexts = [];
  const context = vm.createContext({document:{createElement:() => new Node()}, AbortController,
    ResizeObserver:class { observe() {} disconnect() {} }, crypto:globalThis.crypto});
  const source = fs.readFileSync(new URL("../src/texstage/web/shared/plugins.js", import.meta.url), "utf8");
  const module = new vm.SourceTextModule(source, {context, importModuleDynamically:async () => {
    await waitImport();
    const imported = new vm.SyntheticModule(["mount"], function () {
      this.setExport("mount", ctx => {
        contexts.push(ctx);
        const mount = {updates:0, destroyed:0, update(){this.updates++;}, place(){}, destroy(){this.destroyed++;}};
        mounts.push(mount); return mount;
      });
    }, {context});
    await imported.link(() => {}); await imported.evaluate(); return imported;
  }});
  await module.link(() => {}); await module.evaluate();
  return {api:module.namespace,mounts,contexts};
}
const settle = async map => Promise.all([...map.values()].map(v => v.ready));
test("ordinary updates preserve mounts; replacement and removal dispose them", async () => {
  const h = await harness(), layer = new Node(), controls = new Node();
  const box = new h.api.PluginBox({id:"one",type:"example.plane",layer,controls,host:{role:"presenter",send:async()=>{}}});
  const d = descriptor(); delete d.modules["participant-input"];
  box.place({box:{x:0,y:0,w:1,h:1}}); box.update({plugins:{items:[d]}}); await settle(box.surfaces);
  assert.equal(h.mounts.length,2);
  d.public = {b:2,a:1}; d.views["presenter-controls"].revision++;
  box.update({plugins:{items:[d]}}); await settle(box.surfaces);
  assert.equal(h.mounts.length,2); assert.equal(h.mounts[0].destroyed,0);
  d.public.a = 3;
  box.update({plugins:{items:[d]}}); await settle(box.surfaces);
  assert.equal(h.mounts.length,4); assert.equal(h.mounts[0].destroyed,1);
  delete d.modules["presenter-controls"];
  box.update({plugins:{items:[d]}});
  assert.equal(box.surfaces.size,1);
  box.update({plugins:{items:[]}});
  assert.equal(box.surfaces.size,0); assert.equal(layer.children.length,0); assert.equal(controls.children.length,0);
  assert.ok(h.contexts.every(ctx => ctx.signal.aborted));
});
test("participant mount identity includes language and assets", async () => {
  const h = await harness(), root = new Node();
  const screen = new h.api.PluginScreen({root,client:{send:async()=>{}}}), d = descriptor();
  screen.update({language:"en",plugins:{items:[d]}}); await settle(screen.views);
  d.views["participant-input"].revision++;
  screen.update({language:"en",plugins:{items:[d]}}); await settle(screen.views);
  assert.equal(h.mounts.length,1);
  screen.update({language:"de",plugins:{items:[d]}}); await settle(screen.views);
  assert.equal(h.mounts.length,2);
  d.assets.diagram = "/plugins/new.png";
  screen.update({language:"de",plugins:{items:[d]}}); await settle(screen.views);
  assert.equal(h.mounts.length,3);
  screen.update({plugins:{items:[]}}); assert.equal(root.children.length,0);
});
test("late module import cannot resurrect a removed activity", async () => {
  let release; const gate = new Promise(resolve => {release=resolve;});
  const h = await harness(() => gate), root = new Node();
  const screen = new h.api.PluginScreen({root,client:{send:async()=>{}}});
  screen.update({plugins:{items:[descriptor()]}});
  const waiting = settle(screen.views);
  screen.update({plugins:{items:[]}});
  release(); await waiting;
  assert.equal(h.mounts.length,0); assert.equal(root.children.length,0);
});
test("dispatch preserves domain receipts and operational error codes", async () => {
  const h = await harness(), root = new Node(), receipt = {accepted:false,error:"stale-answer",epoch:1,revision:8};
  let operational = false;
  const screen = new h.api.PluginScreen({root,client:{send:async message => {
    assert.equal(message.command.epoch,1);
    if (operational) throw {code:"queue-full",message:"queue full"};
    return {receipt};
  }}});
  screen.update({plugins:{items:[descriptor()]}}); await settle(screen.views);
  const ctx = h.contexts[0];
  await assert.rejects(ctx.dispatch("submit",{}), e => e.code === "stale-answer" && e.receipt === receipt);
  operational = true;
  await assert.rejects(ctx.dispatch("submit",{}), e => e.code === "queue-full");
  screen.destroy();
  await assert.rejects(ctx.dispatch("submit",{}), e => e.code === "read-only");
});

