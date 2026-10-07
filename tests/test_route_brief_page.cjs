'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const Brief=require('../app/static/route-brief.js');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/static/route-page.js'),'utf8');
const handlers=source.slice(source.indexOf('function defaultGoal()'),source.indexOf('/* ---- directions'));
const loader=source.slice(source.indexOf('async function load()'),source.indexOf('\nfunction render()'));
const brief={goal:'goal',known:'',include:'',exclude:'',structure:'teacher text'};
const graph={concepts:[{id:'c1',name:'saved'}],prereqs:[],targets:['c1']};
const preview=()=>({draft_id:'a'.repeat(32),revision:3,brief:{...brief},before:{graph,goal_status:'completed'},after:{graph:{...graph,concepts:[{id:'c1',name:'changed'}]},progress:{}},changes:{reset:['c1']},stale:false,confirmed:false});
function page(responder) {
  const parts=new Map(),controls=new Map();
  function part(role) { if (!parts.has(role)) parts.set(role,{hidden:false,disabled:false,innerHTML:'',textContent:'',focus(){},addEventListener(){},querySelector(selector){ if(!controls.has(selector)) controls.set(selector,{value:'',focus(){},disabled:false});return controls.get(selector);},querySelectorAll(){return [...controls.values()];}});return parts.get(role); }
  Brief.mount(part('briefFields'),brief);
  const calls=[],messages=[];
  const context=vm.createContext({Brief,R:{nodeStatus(){return {};}},state:{route:{graph,revision:3},draft:graph,dirty:false,briefReady:true,briefDirty:false,preview:null,loadSequence:0},growth:{},part,$:(selector,holder)=>holder.querySelector(selector),
    api:async body=>{calls.push(body);return responder(body);},notice:message=>messages.push(message),render(){},loadGrowth:async()=>{},guarded:async action=>action(),
    window:{PDHGraph:{mount(){return {destroy(){}};}}},JSON});
  vm.runInContext(handlers+loader,context);
  return {context,calls,messages,part,read:()=>Brief.read(part('briefFields'))};
}
test('revision generation sends only brief plus current version and preserves saved Map',async()=>{
  const p=page(()=>({ok:true,preview:preview(),attempts_left:1}));
  await vm.runInContext('generateBrief()',p.context);
  assert.deepEqual(JSON.parse(JSON.stringify(p.calls)),[{action:'revision-generate',brief,revision:3}]);
  assert.equal(p.context.state.draft,graph);assert.equal(p.context.state.dirty,false);
  assert.equal(p.context.state.preview.draft_id,'a'.repeat(32));assert.deepEqual(p.read(),brief);
});
test('refusal and invalid reply retain previous preview and teacher input',async()=>{
  for(const reason_code of ['not_approved','bad_reply','network','budget']){
    const p=page(()=>({ok:false,reason_code,reason:'refused'}));const prior=preview();p.context.state.preview=prior;
    await vm.runInContext('generateBrief()',p.context);
    assert.equal(p.context.state.preview,prior);assert.equal(p.context.state.draft,graph);assert.deepEqual(p.read(),brief);
    assert.equal(p.part('aiGo').disabled,false);
  }
});
test('confirm uses bound draft ID once, with no client graph or refresh revision',async()=>{
  const p=page(()=>({graph,revision:4,undo:{id:10,label:'saved'}}));p.context.state.preview=preview();
  await vm.runInContext('confirmRevision()',p.context);await vm.runInContext('confirmRevision()',p.context);
  assert.deepEqual(JSON.parse(JSON.stringify(p.calls)),[{action:'revision-confirm',draft_id:'a'.repeat(32)}]);
  assert.equal(p.context.state.preview.confirmed,true);assert.equal(p.context.growth.undo.revision,4);
});
test('409 retains preview and input and disables confirmation until explicit regeneration',async()=>{
  const p=page(()=>{const e=new Error('changed');e.status=409;throw e;});const prior=preview();p.context.state.preview=prior;
  await assert.rejects(vm.runInContext('confirmRevision()',p.context));
  assert.equal(p.context.state.preview,prior);assert.equal(prior.stale,true);assert.deepEqual(p.read(),brief);
  assert.equal(p.part('revisionConfirm').disabled,true);
  await vm.runInContext('confirmRevision()',p.context);assert.equal(p.calls.length,1);
});
test('editing requirements or unsaved structure blocks confirming earlier preview',async()=>{
  const p=page(()=>{throw new Error('must not send');});p.context.state.preview=preview();
  Brief.set(p.part('briefFields'),{...brief,structure:'new teacher text'});
  await vm.runInContext('confirmRevision()',p.context);assert.equal(p.calls.length,0);assert.equal(p.part('revisionConfirm').disabled,true);
  p.context.state.dirty=true;await vm.runInContext('generateBrief()',p.context);assert.equal(p.calls.length,0);
});
test('restart reads the real draft wrapper and restores pending preview without a model call',async()=>{
  const prior=preview();const p=page(body=>body?{draft:prior}:{graph,revision:3});
  await vm.runInContext('load()',p.context);
  assert.equal(p.context.state.preview,prior);assert.deepEqual(p.read(),brief);
  assert.deepEqual(JSON.parse(JSON.stringify(p.calls)),[null,{action:'revision-draft'}]);
});

test('confirmation keeps any newer teacher text dirty and restores controls',async()=>{
  let p;
  p=page(()=>{
    assert.equal(p.part('briefFields').querySelectorAll().every(el=>el.disabled),true);
    Brief.set(p.part('briefFields'),{...brief,structure:'newer teacher text'});
    p.context.state.briefDirty=true;
    return {graph,revision:4};
  });
  p.context.state.preview=preview();
  await vm.runInContext('confirmRevision()',p.context);
  assert.equal(p.context.state.briefDirty,true);
  assert.equal(p.read().structure,'newer teacher text');
  assert.equal(p.part('briefFields').querySelectorAll().every(el=>!el.disabled),true);
});

test('restart restores the persisted current undo identity and clears an absent one',async()=>{
  const p=page(body=>body?{draft:null}:{graph,revision:7,undo:{id:42,label:'修改学习图'}});
  await vm.runInContext('load()',p.context);
  assert.deepEqual(JSON.parse(JSON.stringify(p.context.growth.undo)),{id:42,label:'修改学习图',revision:7});
  const q=page(body=>body?{draft:null}:{graph,revision:8,undo:null});q.context.growth.undo={id:42,revision:7};
  await vm.runInContext('load()',q.context);assert.equal(q.context.growth.undo,null);
});
