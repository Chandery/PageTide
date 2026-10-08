'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const R=require('../app/static/route-editor.js'),Brief=require('../app/static/route-brief.js');
function setup() {
  const events=[],nodes=new Map(),listeners=new Map();
  const node=role=>{
    if(!nodes.has(role)) nodes.set(role,{hidden:false,open:false,textContent:'',innerHTML:'',classList:{add(){},remove(){},toggle(){}},
      querySelector:()=>null,querySelectorAll:()=>[],addEventListener(type,fn){this[type]=fn;},focus(){events.push(['focus',role]);},
      showModal(){this.open=true;events.push(['dialog',role]);},close(){this.open=false;}});
    return nodes.get(role);
  };
  const graph={concepts:[{id:'c1',name:'Crystal basics',terms:['crystal growth'],hint:1,state:'active'}],prereqs:[],targets:['c1']};
  const route={graph,revision:1,progress:{c1:{status:'readable'}},enabled:true,goal_status:'learning',total:1,done:0};
  const window={PDHRoute:R,PDHBrief:{...Brief},PDHGraph:{mount:()=>({destroy(){},view(){return {};}})},addEventListener:(type,fn)=>listeners.set(type,fn),
    __TAURI_INTERNALS__:{invoke:async cmd=>events.push(['quit',cmd])}};
  const context=vm.createContext({window,document:{querySelector:s=>node(s.match(/data-role="([^"]+)"/)?.[1]||s),body:{classList:{add(){},remove(){}}}},
    location:{search:''},localStorage:{getItem:()=>''},URLSearchParams,fetch:async(url,options)=>{
      const body=options?.body?JSON.parse(options.body):null;events.push(['request',body]);window.onRequest?.(body);
      return {ok:true,json:async()=>body?.action==='save'?{...route,revision:2}:body?.action==='candidates'?{candidates:[],pending:[]}:route};
    }});
  vm.runInContext(fs.readFileSync('app/static/route-page.js','utf8'),context);
  vm.runInContext(`state.route=${JSON.stringify(route)};state.draft=${JSON.stringify(graph)};`,context);
  events.length=0;
  const set=code=>vm.runInContext(code,context);
  const quit=()=>vm.runInContext("window.PDHPrepareQuit ? window.PDHPrepareQuit() : window.__TAURI_INTERNALS__.invoke('complete_quit')",context);
  return {window,events,node,set,quit,listeners};
}
test('native quit with dirty graph stays open and never saves or confirms AI',async()=>{
  const h=setup();h.set('state.dirty=true');await h.quit();
  assert.equal(h.events.some(e=>e[0]==='quit'),false);assert.equal(h.events.some(e=>e[0]==='request'),false);
  assert.equal(h.node('quitDialog').open,true);
});
test('brief, in-editor text, pending intro and unconfirmed preview each require explicit choice',async()=>{
  for(const code of ['state.briefDirty=true','state.editing="c1"','state.pendingIntro={id:"c1",text:"AI text"}','state.preview={confirmed:false}']){
    const h=setup();h.set(code);await h.quit();assert.equal(h.events.some(e=>e[0]==='quit'),false,code);
    assert.equal(h.node('quitDialog').open,true,code);assert.equal(h.events.some(e=>e[0]==='request'),false,code);
  }
});
test('save, grounding and AI judgement in flight cannot be abandoned by quit',async()=>{
  for(const code of ['state.busy=true','state.checking=true','growth.judging=true']){
    const h=setup();h.set(code);await h.quit();assert.equal(h.events.some(e=>e[0]==='quit'),false,code);
    assert.match(h.node('notice').textContent,/当前操作/);
  }
});
test('cancel or return to review leaves edits intact; only actual Save writes the graph',async()=>{
  const h=setup();h.set('state.dirty=true');await h.quit();h.node('quitCancel').onclick();
  assert.equal(h.node('quitDialog').open,false);assert.equal(h.set('state.dirty'),true);assert.equal(h.events.some(e=>e[0]==='quit'),false);
  await h.quit();h.node('quitReview').onclick();assert.equal(h.set('state.dirty'),true);
  assert.ok(h.events.some(e=>e[0]==='focus'&&e[1]==='save'));assert.equal(h.events.some(e=>e[0]==='request'),false);
  await h.node('save').onclick();assert.equal(h.set('state.dirty'),false);
  assert.equal(h.events.filter(e=>e[0]==='request'&&e[1]?.action==='save').length,1);
  await h.quit();assert.equal(h.events.filter(e=>e[0]==='quit').length,1);
});
test('explicit discard exits without committing the graph, brief or AI proposal',async()=>{
  const h=setup();h.set('state.dirty=true;state.briefDirty=true;state.preview={confirmed:false}');await h.quit();
  await h.node('quitDiscard').onclick();assert.equal(h.events.filter(e=>e[0]==='quit').length,1);
  assert.equal(h.events.some(e=>e[0]==='request'),false);assert.equal(h.set('state.preview.confirmed'),false);
});
test('Save cannot throw away a still-open concept edit or silently apply an AI introduction',async()=>{
  const h=setup();h.set('state.dirty=true;state.editing="c1";state.pendingIntro={id:"c1",text:"Unconfirmed AI"}');
  await h.node('save').onclick();assert.equal(h.events.some(e=>e[0]==='request'),false);
  assert.equal(h.set('state.dirty'),true);assert.equal(h.set('state.pendingIntro.text'),'Unconfirmed AI');
});
test('explicit creation Save resolves only its submitted brief, preserving edits typed during the request',async()=>{
  for(const late of [false,true]){
    const h=setup();let brief={goal:'Fixed learning goal'};h.window.PDHBrief.read=()=>({...brief});
    h.set('state.dirty=true;state.briefDirty=true;state.creationBrief=true');
    h.window.onRequest=body=>{if(body?.action==='save'&&late) brief={goal:'A later edit'};};
    await h.node('save').onclick();assert.equal(h.set('state.creationBrief'),null);
    assert.equal(h.set('state.briefDirty'),late);assert.equal(h.set('state.dirty'),false);
    await h.quit();assert.equal(h.events.some(e=>e[0]==='quit'),!late);
  }
});
test('a new operation after opening quit choice blocks discard; native errors preserve all edits',async()=>{
  const h=setup();h.set('state.dirty=true');await h.quit();h.set('state.busy=true');await h.node('quitDiscard').onclick();
  assert.equal(h.events.some(e=>e[0]==='quit'),false);h.set('state.busy=false');
  h.window.__TAURI_INTERNALS__.invoke=async()=>{throw new Error('native refusal');};await h.node('quitDiscard').onclick();
  assert.equal(h.set('state.dirty'),true);assert.match(h.node('notice').textContent,/应用保持打开/);
});
test('clean page exits once and duplicate requests do not double-complete',async()=>{
  const h=setup();let finish;h.window.__TAURI_INTERNALS__.invoke=cmd=>{h.events.push(['quit',cmd]);return new Promise(resolve=>{finish=resolve;});};
  const pending=h.quit();await h.quit();assert.equal(h.events.filter(e=>e[0]==='quit').length,1);finish();await pending;
});
test('browser unload uses the same unconfirmed-content and operation guards',()=>{
  const h=setup();h.set('state.pendingIntro={text:"AI text"}');let prevented=false;
  h.listeners.get('beforeunload')({preventDefault(){prevented=true;}});assert.equal(prevented,true);
});
