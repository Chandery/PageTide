'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
const handler=source.slice(source.indexOf("document.addEventListener('keydown', event => {",source.indexOf('function readerControls()')),source.indexOf("document.addEventListener('focusin', event => {",source.indexOf('function readerControls()')));
function runtime(){
 const nodes=new Map(),listeners=[];let closed=0,hiddenSelection=0,modal=false;
 const node=q=>{if(!nodes.has(q)){const names=new Set();nodes.set(q,{value:q==='#petInput'?'中文问题\n第二行':'',classList:{contains:n=>names.has(n),add:n=>names.add(n),remove:n=>names.delete(n),toggle:(n,v)=>v?names.add(n):names.delete(n)},focus(){context.document.activeElement=this;}});}return nodes.get(q);};
 const context={$:node,document:{activeElement:null,addEventListener:(event,fn)=>listeners.push(fn),querySelector:()=>modal?{}:null},window:{PDHDialogs:{active:()=>modal},getSelection:()=>({removeAllRanges(){}})},setPetOpen:open=>node('#petPanel').classList.toggle('open',open),hideSel:()=>{node('#selbar').classList.remove('show');hiddenSelection++;},closeReader:()=>closed++,readerControls:()=>[node('#readerAsk')]};
 vm.createContext(context);vm.runInContext(handler,context);
 const escape=(isComposing=false)=>{let prevented=false;listeners[0]({key:'Escape',isComposing,preventDefault(){prevented=true;},stopPropagation(){},stopImmediatePropagation(){}});return prevented;};
 return {node,escape,closed:()=>closed,hidden:()=>hiddenSelection,setModal:v=>modal=v};
}
test('actual reader handler closes assistant before reader and preserves Chinese draft',()=>{
 const r=runtime();r.node('#petPanel').classList.add('open');assert.equal(r.escape(),true);assert.equal(r.closed(),0);assert.equal(r.node('#petPanel').classList.contains('open'),false);assert.equal(r.node('#petInput').value,'中文问题\n第二行');r.escape();assert.equal(r.closed(),1);
});
test('topmost translation, selection and confirmation take Escape ahead of reader',()=>{
 const r=runtime();r.node('#petPanel').classList.add('open');r.node('#transPop').classList.add('show');r.escape();assert.equal(r.node('#transPop').classList.contains('show'),false);assert.equal(r.node('#petPanel').classList.contains('open'),true);
 r.node('#selbar').classList.add('show');r.escape();assert.equal(r.hidden(),1);assert.equal(r.closed(),0);
 r.setModal(true);assert.equal(r.escape(),false);assert.equal(r.closed(),0);assert.equal(r.node('#petPanel').classList.contains('open'),true);
});
test('actual paint wait completes if native animation frames stop and cancels scheduled work',async()=>{
 const fn=source.slice(source.indexOf('function afterPaints('),source.indexOf('function currentAnchor('));let cancelled=0;
 const context={setTimeout,clearTimeout,requestAnimationFrame:()=>7,cancelAnimationFrame:id=>{assert.equal(id,7);cancelled++;}};vm.createContext(context);vm.runInContext(fn,context);
 await Promise.race([context.afterPaints(2),new Promise((_,reject)=>setTimeout(()=>reject(new Error('paint wait never completed')),450))]);assert.equal(cancelled,1);
});

test('actual renderPage success waits for canvas and text, failures cannot claim ready',async()=>{
 const fn=source.slice(source.indexOf('function renderPage('),source.indexOf('function markCurrent('));
 let finish,fail=false;const notes=[],canvas={style:{},getContext:()=>({})},text={innerHTML:'',style:{setProperty(){}}};
 const page={getViewport:()=>({width:80,height:100,scale:1}),render:()=>({promise:fail?Promise.reject(new Error('bad canvas')):new Promise(resolve=>finish=resolve)}),getTextContent:async()=>({items:[],styles:{}})};
 const root={querySelector:()=>({querySelector:()=>({querySelector:q=>q==='canvas'?canvas:text})})};
 const context={R:{pages:[page],renderedScale:1,jobs:new Map()},document:root,window:{devicePixelRatio:1},lib:async()=>({TextLayer:class{async render(){}}}),toast:msg=>notes.push(msg)};
 vm.createContext(context);vm.runInContext(fn,context);const pending=context.renderPage(1,root);let ready=false;pending.then(()=>ready=true);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(ready,false);finish();assert.equal(await pending,true);
 fail=true;assert.equal(await context.renderPage(1,root,new Map()),false);assert.match(notes.at(-1),/bad canvas/);
});

test('reader Escape during Chinese composition leaves every layer and draft intact',()=>{
 const r=runtime();r.node('#petPanel').classList.add('open');assert.equal(r.escape(true),false);assert.equal(r.closed(),0);assert.equal(r.node('#petPanel').classList.contains('open'),true);assert.equal(r.node('#petInput').value,'中文问题\n第二行');
});
