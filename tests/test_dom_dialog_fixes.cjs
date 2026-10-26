'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const staticDir=path.join(__dirname,'../app/static');
function runtime(){
 const doc={activeElement:null};
 class Element{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.attrs={};this.dataset={};this.isConnected=true;this.disabled=false;this.hidden=false;this.open=false;this.textContent='';this.style={};this.classList={add(){},remove(){}};}
  append(...els){this.children.push(...els);for(const el of els)if(typeof el==='object')el.parent=this;}
  appendChild(el){this.append(el);return el;}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(k,f){(this.listeners[k]??=[]).push(f);}
  dispatch(k,event={}){event.preventDefault??=()=>{event.prevented=true;};event.stopImmediatePropagation??=()=>{};for(const f of this.listeners[k]||[])f(event);}
  showModal(){this.open=true;}
  close(){this.open=false;this.dispatch('close');}
  remove(){this.isConnected=false;}
  focus(){doc.activeElement=this;}
  contains(el){return el===this||this.children.some(c=>typeof c==='object'&&c.contains(el));}
  querySelectorAll(){return this.children.flatMap(c=>typeof c==='object'?[c,...c.querySelectorAll()]:[]).filter(c=>c.tagName==='BUTTON');}
 }
 doc.body=new Element('body');doc.createElement=tag=>new Element(tag);doc.querySelector=()=>null;
 const before=new Element('button');before.focus();
 const context={window:{PTi18n:{translate:s=>s}},document:doc,queueMicrotask};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(staticDir,'dialogs.js'),'utf8'),context);
 const buttons=()=>doc.body.children.filter(x=>x.open).at(-1)?.querySelectorAll();
 const dialog=()=>doc.body.children.filter(x=>x.open).at(-1);
 return {api:context.window.PTDialogs,doc,before,buttons,dialog};
}
test('confirm really renders and cancellation/Escape stay false with focus restored',async()=>{
 const r=runtime(),p=r.api.confirm('Delete draft?');assert.equal(r.api.active(),true);assert.equal(r.doc.activeElement.textContent,'取消');
 r.dialog().dispatch('cancel');assert.equal(await p,false);assert.equal(r.api.active(),false);assert.equal(r.doc.activeElement,r.before);
 const p2=r.api.confirm('Delete draft?');r.buttons()[0].onclick();assert.equal(await p2,false);
});
test('confirm queue is serialized, approval explicit, stale context never approved',async()=>{
 const r=runtime();let current=true;const p=r.api.confirm('first'),q=r.api.confirm('second',{valid:()=>current});
 assert.equal(r.doc.body.children.filter(x=>x.open).length,1);current=false;r.buttons()[1].onclick();assert.equal(await p,true);assert.equal(await q,false);assert.equal(r.api.active(),false);
 const z=r.api.confirm('third',{valid:()=>current});assert.equal(await z,false);
});
test('choose answers with the clicked button value, Escape gives the dismissed value, and the last button is the suggested one',async()=>{
 const r=runtime(),p=r.api.choose('No seeds yet',[{label:'取消',value:null},{label:'直接创建',value:'create'},{label:'查找论文',value:'search'}]);
 const b=r.buttons();assert.equal(b.length,3);assert.equal(b[2].className,'primary');assert.equal(r.doc.activeElement,b[0]);
 b[1].onclick();assert.equal(await p,'create');
 const q=r.api.choose('again',[{label:'a',value:'a'},{label:'b',value:'b'}]);r.dialog().dispatch('cancel');assert.equal(await q,null);
 let current=true;const z=r.api.choose('stale',[{label:'a',value:'a'}],{valid:()=>current});current=false;r.buttons()[0].onclick();assert.equal(await z,null);
});
test('confirmation keeps keyboard focus inside top dialog and notices persist accessibly',async()=>{
 const r=runtime(),p=r.api.confirm('<unsafe>');const [cancel,approve]=r.buttons();approve.focus();r.dialog().dispatch('keydown',{key:'Tab',shiftKey:false});assert.equal(r.doc.activeElement,cancel);
 cancel.focus();r.dialog().dispatch('keydown',{key:'Tab',shiftKey:true});assert.equal(r.doc.activeElement,approve);cancel.onclick();await p;
 const n=r.api.notice('Saved',{kind:'success'});assert.equal(n.textContent,'Saved');assert.equal(n.attrs.role,'status');assert.equal(n.hidden,false);
 r.api.notice('failed',{target:n,kind:'error'});assert.equal(n.attrs.role,'alert');assert.equal(n.textContent,'failed');assert.equal(n.hidden,false);
});
test('actual destructive call sites do not depend on unavailable native dialogs',()=>{
 for(const file of ['settings.html','project-creation.js','import.js','profile-ui.js','organization.js'])assert.doesNotMatch(fs.readFileSync(path.join(staticDir,file),'utf8'),/(?<![.\w])(?:alert|confirm)\s*\(|window\.(?:alert|confirm)\s*\(/g,file);
});
