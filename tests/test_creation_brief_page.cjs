'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const Brief=require('../app/static/route-brief.js'),R=require('../app/static/route-editor.js');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/static/project-creation.js'),'utf8');
const i18nSource=fs.readFileSync(require('node:path').join(__dirname,'../app/static/i18n.js'),'utf8');
const english=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../app/static/i18n/en-US.json'),'utf8')).messages;
const generation=source.slice(source.indexOf('  async function generateMap('),source.indexOf("  part('mapCheck').onclick"));
const manual=source.slice(source.indexOf("  part('mapStart').onclick"),source.indexOf('  async function generateMap('));
const readBrief=source.slice(source.indexOf('function readCreationBrief('),source.indexOf('// Where to go once a project exists:'));
const fieldError=source.slice(source.indexOf('function creationFieldError('),source.indexOf('function readCreationPolicy('));
const changedMap=source.slice(source.indexOf('  const changedMap = '),source.indexOf('  const mapNotice = '));
const brief={goal:'study',known:'',include:'',exclude:'',structure:'# teacher\nprobability first'};
function page(response,lang='zh-CN') {
  const controls=new Map(),parts=new Map(),calls=[],messages=[];let sid='first';
  function part(role){if(!parts.has(role))parts.set(role,{hidden:false,disabled:false,querySelectorAll(){return [...controls.values()];},querySelector(s){if(!controls.has(s))controls.set(s,{value:'',disabled:false});return controls.get(s);}});return parts.get(role);}
  Brief.mount(part('mapBrief'),brief);
  const map={graph:{concepts:[{id:'saved',name:'Old',terms:['old'],state:'active'}],prereqs:[],targets:['saved']},mastered:['saved'],checking:false,generating:false};
  const context=vm.createContext({Brief,PTBrief:Brief,R,map,part,MAX_PATH:8,busy:false,sessionId:()=>sid,mapNotice:m=>messages.push(m),mapAct:{start(){},stop(){}},renderMap(){},refresh(){},confirm:()=>true,
    // Stage DOM rendering is outside this fixed-brief test; generation and validation are shipped functions.
    addPathItem(){},syncPath(){},bindPathConcepts(){},
    PAGETIDE_I18N:{lang,messages:english},document:{documentElement:{},addEventListener(){}},MutationObserver:class{observe(){}},
    post:async(path,body)=>{calls.push({path,body});return response(()=>{sid='second';});}});
  context.window=context;
  vm.runInContext(i18nSource,context);
  vm.runInContext(fieldError+readBrief+changedMap+manual+generation,context);
  return {context,calls,map,part,messages};
}
test('creation sends fixed complete teacher requirements and preserves original draft on refusals',async()=>{
  for(const code of ['not_approved','bad_reply','network']){
    const p=page(()=>({ok:false,reason_code:code,reason:'refusal'}));const before=p.map.graph;
    await vm.runInContext('generateMap(true)',p.context);
    assert.equal(p.map.graph,before);assert.deepEqual(p.map.mastered,['saved']);
    assert.deepEqual(JSON.parse(JSON.stringify(p.calls)),[{path:'/api/project-guidance/sessions/first/route',body:{regenerate:true,brief}}]);
    assert.deepEqual(Brief.read(p.part('mapBrief')),brief);assert.equal(p.map.generating,false);
  }
});
test('response belonging to an earlier creation session never replaces current draft',async()=>{
  const p=page(changeSession=>{changeSession();return {ok:true,graph:{concepts:[]},report:{warnings:[]}};});const before=p.map.graph;
  await vm.runInContext('generateMap(false)',p.context);assert.equal(p.map.graph,before);
});
test('AI off still allows a manual graph with explicit target and preserves requirements',async()=>{
  for(const lang of ['zh-CN','en-US']) {
    const p=page(()=>{throw new Error('must not call');},lang);
    await vm.runInContext("part('mapStart').onclick()",p.context);
    assert.equal(R.check(p.map.graph).ok,true);assert.deepEqual(JSON.parse(JSON.stringify(p.map.graph.targets)),['c1']);
    assert.equal(p.map.graph.concepts[0].name,lang==='en-US'?english['第一个概念']:'第一个概念');
    if(lang==='en-US')assert.doesNotMatch(p.map.graph.concepts[0].name,/[㐀-鿿]/);
    assert.equal(p.context.PTi18n.lang,lang);
    assert.deepEqual(Brief.read(p.part('mapBrief')),brief);assert.equal(p.calls.length,0);
  }
});

test('discarding a cached map retains an explicit regeneration entry for changed requirements',async()=>{
  const created={concepts:[{id:'c1',name:'Task',terms:['task'],state:'active',hint:1}],prereqs:[],targets:['c1']};
  const p=page(()=>({ok:true,graph:created,report:{warnings:[]}}));
  await vm.runInContext('generateMap(false)',p.context);
  p.map.graph=null;p.context.document={activeElement:null};p.context.refresh=()=>{};
  p.part('map').replaceChildren=()=>{};
  const draw=source.slice(source.indexOf('  function renderMap()'),source.indexOf('  function renderDetail()'));
  vm.runInContext(draw,p.context);await vm.runInContext('renderMap()',p.context);
  assert.equal(p.part('mapGenerate').hidden,false);assert.equal(p.part('mapRegen').hidden,false);
  assert.equal(p.part('mapActions').hidden,true);
});
