// SPDX-License-Identifier: Apache-2.0
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
function harness(name){
 const source=fs.readFileSync(path.join(__dirname,"../src/texstage/web/stage",name+".js"),"utf8");
 const start=source.lastIndexOf('document.addEventListener("keydown", (e) => {');
 const code=source.slice(start,source.indexOf("\n});",start)+4);
 let handler;const actions=[];
 vm.runInNewContext(code,{document:{addEventListener:(name,fn)=>handler=fn},deck:{},state:{},$:()=>null,
  onKey:e=>{actions.push(e.key);return true;},inkAction:a=>actions.push(a),
  channel:{postMessage:m=>actions.push(m.key)}});
 return {actions,send({control=false,handled=false,key="Enter"}={}){
  let prevented=false;
  handler({key,defaultPrevented:handled,target:{closest:selector=>{
   if(control){for(const expected of ["select","button","summary","contenteditable",".texstage-plugin"])assert(selector.includes(expected));return {};}
   return null;
  }},preventDefault(){prevented=true;}});
  return prevented;
 }};
}
for(const page of ["presenter","projector"]){
 test(page+": native/plugin keys are not slide commands; background navigation still works",()=>{
  const h=harness(page);
  for(const key of ["Enter"," ","ArrowDown","Home","b"]){assert.equal(h.send({control:true,key}),false);}
  assert.equal(h.send({handled:true}),false);
  if(page==="projector")assert.equal(h.send({key:"Tab"}),false);
  assert.deepEqual(h.actions,[]);
  assert.equal(h.send({key:"ArrowRight"}),true);assert.deepEqual(h.actions,["ArrowRight"]);
 });
}
