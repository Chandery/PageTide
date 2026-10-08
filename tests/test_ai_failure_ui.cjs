'use strict';
const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/static/index.html'),'utf8');
function page(result){
  const banner={hidden:true,innerHTML:''}, notices=[], calls=[];
  const state={currentProject:'p1',triaging:false,triagingKeys:new Set(),aiFailures:{}};
  const context=vm.createContext({state,$:()=>banner,esc:s=>String(s).replaceAll('<','&lt;'),toast:t=>notices.push(t),renderCards(){},load:async()=>{},
    api:async(path,body)=>{calls.push({path,body});return result;}});
  vm.runInContext(source.slice(source.indexOf('function aiUsageText(result)'), source.indexOf('async function generate()')),context);
  vm.runInContext(source.slice(source.indexOf('async function autoTriage()'),source.indexOf("$('#btnDaily').onclick")),context);
  vm.runInContext(source.slice(source.indexOf('function aiSlot(c)'),source.indexOf('// The learning map:')),context);
  return {context,state,banner,calls,notices};
}
test('whole-batch failure persists beside trigger after reload, with settings action',async()=>{
  const p=page({ok:false,reason:'API key invalid (HTTP 401)',reason_code:'http'});
  await vm.runInContext('autoTriage()',p.context);
  assert.equal(p.banner.hidden,false);assert.match(p.banner.innerHTML,/401/);assert.match(p.banner.innerHTML,/settings.html/);
  assert.equal(p.calls.length,1);assert.equal(p.state.triaging,false);
});
test('card failure keeps its prior summary and is isolated by project',async()=>{
  const p=page({ok:false,reason:'Insufficient balance (HTTP 402)'});
  await vm.runInContext("triageOne('paper')",p.context);
  let card=vm.runInContext("aiSlot({key:'paper',summary:{one_liner:'Earlier summary'}})",p.context);
  assert.match(card,/402/);assert.match(card,/Earlier summary/);
  p.state.currentProject='p2';card=vm.runInContext("aiSlot({key:'paper'})",p.context);assert.doesNotMatch(card,/402/);
  assert.equal(p.calls.length,1);
});
test('late failure from a different project does not appear in the current banner',async()=>{
  const p=page({ok:false,reason:'HTTP 503'});
  p.context.api=async()=>{p.state.currentProject='p2';return {ok:false,reason:'HTTP 503'};};
  await vm.runInContext("triageOne('paper')",p.context);
  assert.equal(p.banner.hidden,true);
  assert.deepEqual(p.notices,[]);
  assert.doesNotMatch(vm.runInContext("aiSlot({key:'paper'})",p.context),/503/);
});
