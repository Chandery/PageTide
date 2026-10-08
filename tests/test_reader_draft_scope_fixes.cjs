'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
const start=source.indexOf('const pet = {'),end=source.indexOf('/* A quote shows',start);
function runtime(){
 const nodes=new Map(),calls=[];
 const node=q=>{if(!nodes.has(q))nodes.set(q,{value:'',innerHTML:'',textContent:'',title:'',style:{},scrollHeight:42,classList:{contains:n=>n==='hidden',remove(){}},toggleAttribute(){}});return nodes.get(q);};
 const context={$:node,state:{currentProject:'cs',projects:[]},R:{key:null},window:{},lastFol:null,
 api:async url=>{calls.push(url);return {session:{id:'s'},history:[]};},setReference(){},setAttachPage(){},hideSel(){},closeReader(){},addIntro(){},addMsg(){},growInput(){}};
 vm.createContext(context);vm.runInContext(source.slice(start,end),context);
 const change=(key,project='cs')=>context.window.PDHSetContext(key,key,project);
 return {context,node,change,calls};
}
const draft='这篇论文的动作输入是什么？\nPD-1 / Li6PS5Cl，保持用户原文。';
test('switching papers starts with the destination draft and restores the original exactly',()=>{
 const r=runtime();r.change('a');r.node('#petInput').value=draft;r.change('b');assert.equal(r.node('#petInput').value,'');
 r.node('#petInput').value='第二篇独立问题';r.change('a');assert.equal(r.node('#petInput').value,draft);
 r.change('b');assert.equal(r.node('#petInput').value,'第二篇独立问题');
});
test('the same paper has independent drafts in different projects',()=>{
 const r=runtime();r.change('a','cs');r.node('#petInput').value=draft;r.change('a','materials');assert.equal(r.node('#petInput').value,'');
 r.node('#petInput').value='界面稳定性问题';r.change('a','cs');assert.equal(r.node('#petInput').value,draft);
 r.change('a','materials');assert.equal(r.node('#petInput').value,'界面稳定性问题');
});
test('reopening the same context and asynchronous history cannot replace the question',async()=>{
 const r=runtime();r.change('a');r.node('#petInput').value=draft;r.change('a');assert.equal(r.node('#petInput').value,draft);
 await vm.runInContext('pet.sessionPromise',r.context);assert.equal(r.node('#petInput').value,draft);
});
test('cleared drafts stay cleared and never resurrect when returning to the paper',()=>{
 const r=runtime();r.change('a');r.node('#petInput').value=draft;r.change('b');r.change('a');r.node('#petInput').value='';
 r.change('b');r.change('a');assert.equal(r.node('#petInput').value,'');
});
test('context identifiers cannot collide and no-selection drafts never migrate to a paper',()=>{
 const r=runtime();r.node('#petInput').value='尚未选择论文的问题';r.change('x/y','p');assert.equal(r.node('#petInput').value,'');
 r.node('#petInput').value='第一组';r.change('y','p/x');assert.equal(r.node('#petInput').value,'');
 r.node('#petInput').value='第二组';r.change('x/y','p');assert.equal(r.node('#petInput').value,'第一组');
 r.change(null);assert.equal(r.node('#petInput').value,'尚未选择论文的问题');
});
test('sending without a selected paper leaves the unsent question intact',()=>{
 const fn=source.slice(source.indexOf('function sendInput()'),source.indexOf('function growInput()',source.indexOf('function sendInput()')));
 const input={value:draft},calls=[];
 const context={$:()=>input,pet:{key:null,busy:false},R:{loading:false},growInput(){},toast:(...args)=>calls.push(args),ask:()=>{throw new Error('No-context submission should not be delegated');}};
 vm.createContext(context);vm.runInContext(fn,context);context.sendInput();assert.equal(input.value,draft);assert.equal(calls.length,1);
});

test('opening the assistant sizes a restored multiline draft after the panel becomes visible',()=>{
 const names=new Set(),input={value:draft,style:{}};
 Object.defineProperty(input,'scrollHeight',{get:()=>names.has('open')?84:0});
 const panel={classList:{contains:n=>names.has(n),toggle:(n,v)=>v?names.add(n):names.delete(n)}};
 const context={$:q=>q==='#petPanel'?panel:q==='#petInput'?input:{classList:{contains:n=>n==='hidden'}},
  document:{activeElement:null},R:{doc:null},requestAnimationFrame(){throw new Error('No PDF fit should be needed');}};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('let petFocus = null;'),source.indexOf('const SUGGESTIONS = [')),context);
 vm.runInContext(source.slice(source.indexOf('function growInput()'),source.indexOf("$('#petSend').onclick",source.indexOf('function growInput()'))),context);
 context.growInput();assert.equal(input.style.height,'0px');
 context.openPet();assert.equal(input.style.height,'84px');assert.equal(input.value,draft);
 context.setPetOpen(false);assert.equal(input.value,draft);
 context.openPet();assert.equal(input.style.height,'84px');
});

test('opening and closing the docked assistant refits a PDF whose width changes synchronously',()=>{
 const names=new Set(),frames=[],input={value:draft,style:{},scrollHeight:84};let fitted=0;
 const panel={contains:()=>false,classList:{contains:n=>names.has(n),toggle:(n,v)=>v?names.add(n):names.delete(n)}};
 const pages={};Object.defineProperty(pages,'clientWidth',{get:()=>names.has('open')?500:900});
 const reader={classList:{contains:()=>false},focus(){}};
 const context={$:q=>({'#petPanel':panel,'#petInput':input,'#readerPages':pages,'#reader':reader,'#readerAsk':reader}[q]),
  document:{activeElement:null},R:{doc:{}},requestAnimationFrame:fn=>frames.push(fn),layoutPages:()=>fitted++};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('let petFocus = null;'),source.indexOf('const SUGGESTIONS = [')),context);
 vm.runInContext(source.slice(source.indexOf('function growInput()'),source.indexOf("$('#petSend').onclick",source.indexOf('function growInput()'))),context);
 context.openPet();frames.shift()();assert.equal(fitted,1);assert.equal(input.value,draft);
 context.setPetOpen(false);frames.shift()();assert.equal(fitted,2);assert.equal(input.value,draft);
 context.setPetOpen(false);frames.shift()();assert.equal(fitted,2);
});
