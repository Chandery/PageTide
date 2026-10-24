'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const dir=path.join(__dirname,'../app/static');
function setup(){
 const events=[],nodes=new Map(),listeners=new Map();let flags={dirty:false,busy:false};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{id,open:false,disabled:false,isConnected:true,inert:false,value:'',textContent:'',attrs:{},listeners:{},setAttribute(k,v){this.attrs[k]=v;},focus(){doc.activeElement=this;events.push(['focus',id]);},showModal(){this.open=true;events.push(['dialog',id]);},close(){this.open=false;},addEventListener(k,f){this.listeners[k]=f;},contains(el){return el===this||['creationQuitCancel','creationQuitReview','creationQuitDiscard'].includes(el?.id);},querySelectorAll(){return ['creationQuitCancel','creationQuitReview','creationQuitDiscard'].map(node);}});return nodes.get(id);};
 const doc={activeElement:node('editor'),querySelector:s=>node(s.slice(1))};
 const window={addEventListener:(k,f)=>listeners.set(k,f),__TAURI_INTERNALS__:{invoke:async command=>events.push(['quit',command])},PTDialogs:{notice:(message,{target})=>{target.textContent=message;events.push(['notice',message]);}}};
 const context=vm.createContext({window,document:doc});vm.runInContext(fs.readFileSync(path.join(dir,'creation-quit.js'),'utf8'),context);
 window.PTCreationQuit.mount({dirty:()=>flags.dirty,busy:()=>flags.busy,focus:()=>node('editor').focus()});
 return {window,node,events,listeners,flags,doc,quit:()=>window.PTPrepareQuit()};
}
test('creation inputs and unconfirmed edits require explicit choice, default Cancel preserves data',async()=>{
 const h=setup();h.flags.dirty=true;h.node('editor').value='中文学习目标';await h.quit();assert.equal(h.node('creationQuitDialog').open,true);assert.equal(h.doc.activeElement,h.node('creationQuitCancel'));assert.equal(h.events.some(e=>e[0]==='quit'),false);
 h.node('creationQuitCancel').onclick();assert.equal(h.node('creationQuitDialog').open,false);assert.equal(h.node('editor').value,'中文学习目标');assert.equal(h.doc.activeElement,h.node('editor'));
 await h.quit();h.node('creationQuitReview').onclick();assert.equal(h.node('editor').value,'中文学习目标');assert.equal(h.events.some(e=>e[0]==='quit'),false);
});
test('busy before Quit or after choice prevents exiting and never confirms AI or creates project',async()=>{
 const h=setup();h.flags.dirty=true;h.flags.busy=true;await h.quit();assert.equal(h.node('creationQuitDialog').open,false);assert.equal(h.events.some(e=>e[0]==='quit'),false);
 h.flags.busy=false;await h.quit();h.flags.busy=true;await h.node('creationQuitDiscard').onclick();assert.equal(h.events.some(e=>e[0]==='quit'),false);assert.equal(h.node('creationQuitDialog').open,true);
});
test('only explicit Discard exits; IPC failure retains edits and supports retry without duplicate Quit',async()=>{
 const h=setup();h.flags.dirty=true;h.node('editor').value='unsaved';await h.quit();h.window.__TAURI_INTERNALS__.invoke=async()=>{throw new Error('native refused');};await h.node('creationQuitDiscard').onclick();assert.equal(h.node('editor').value,'unsaved');assert.equal(h.node('creationQuitDialog').open,true);assert.equal(h.node('creationQuitDiscard').disabled,false);
 let resolve;h.window.__TAURI_INTERNALS__.invoke=command=>{h.events.push(['quit',command]);return new Promise(done=>resolve=done);};const pending=h.node('creationQuitDiscard').onclick();await h.node('creationQuitDiscard').onclick();await h.quit();assert.equal(h.events.filter(e=>e[0]==='quit').length,1);resolve();await pending;
});
test('Escape cancels, keyboard cycles, browser unload guards dirty/busy, clean page exits directly',async()=>{
 const h=setup();h.flags.dirty=true;await h.quit();const dialog=h.node('creationQuitDialog');let prevented=false;dialog.listeners.cancel({preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(dialog.open,false);
 await h.quit();h.node('creationQuitDiscard').focus();dialog.listeners.keydown({key:'Tab',shiftKey:false,preventDefault(){}});assert.equal(h.doc.activeElement,h.node('creationQuitCancel'));
 let blocked=false;h.listeners.get('beforeunload')({preventDefault(){blocked=true;}});assert.equal(blocked,true);h.node('creationQuitCancel').onclick();h.flags.dirty=false;await h.quit();assert.equal(h.events.filter(e=>e[0]==='quit').length,1);
});
test('actual creation adapter detects programmatic field edits, map/brief/edit/keyword and in-flight state',()=>{
 const source=fs.readFileSync(path.join(dir,'project-creation.js'),'utf8');
 const slice=source.slice(source.indexOf('function creationInputSignature('),source.indexOf('window.PTCreationQuit.mount('));
 const input={id:'manualName',value:'',type:'text',checked:false,closest:()=>null},ctx={document:{querySelectorAll:()=>[input]},creationPending:0,modeConfirming:false,guidedBusy:false,seeds:[],seedKeywords:{get:()=>[]},session:null,review:null,window:{PTDialogs:{active:()=>false}}};vm.createContext(ctx);vm.runInContext(slice+';globalThis.exitState=creationExitState;',ctx);
 assert.equal(ctx.exitState().dirty,false);input.value='中文材料方向';assert.equal(ctx.exitState().dirty,true);input.value='';assert.equal(ctx.exitState().dirty,false);
 for(const state of [{dirty:true,busy:false},{dirty:false,busy:true}]){ctx.review={quitState:()=>state};assert.equal(ctx.exitState().dirty,state.dirty);assert.equal(ctx.exitState().busy,state.busy);}
 ctx.review=null;ctx.seeds.push({status:'working'});assert.equal(ctx.exitState().busy,true);ctx.seeds.length=0;ctx.creationPending=1;assert.equal(ctx.exitState().busy,true);
});

test('actual creation request counter includes response parsing and releases on success or network failure',async()=>{
 const source=fs.readFileSync(path.join(dir,'project-creation.js'),'utf8');
 const slice=source.slice(source.indexOf('let creationPending = '),source.indexOf('const post = '));let response;
 const ctx={fetch:()=>new Promise(resolve=>response=resolve)};vm.createContext(ctx);vm.runInContext(slice+';globalThis.pendingCount=()=>creationPending;',ctx);
 const call=ctx.api('/api/local');assert.equal(ctx.pendingCount(),1);response({ok:true,json:async()=>({ok:true})});await call;assert.equal(ctx.pendingCount(),0);
 ctx.fetch=async()=>{throw new Error('offline');};await assert.rejects(ctx.api('/api/local'));assert.equal(ctx.pendingCount(),0);
});
test('production HTML loads quit helper before creation adapter and has accessible explicit choices',()=>{
 const html=fs.readFileSync(path.join(dir,'project_creation.html'),'utf8');assert.ok(html.indexOf('/creation-quit.js')<html.indexOf('/project-creation.js'));
 assert.match(html,/id="creationQuitDialog"[^>]*aria-labelledby="creationQuitTitle"[^>]*aria-describedby="creationQuitText"/);
 for(const id of ['creationQuitCancel','creationQuitReview','creationQuitDiscard'])assert.match(html,new RegExp('id="'+id+'"'));
});
