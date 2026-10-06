'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto,createHash}=require('node:crypto');
const policy=require('../app/static/paper-policy.js');
const reader=require('../app/static/reader-source.js');
class Element {
  constructor(doc,tag) {this.ownerDocument=doc;this.tag=tag;this.children=[];this.value='';this.classList={add(){},toggle(){}};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(){}
}
const document={createElement(tag){return new Element(this,tag);},createTextNode(text){return {textContent:text};}};
const walk=(el,tag)=>[...(el.tag===tag?[el]:[]),...(el.children||[]).flatMap(c=>walk(c,tag))];
test('new editor requires an explicit discipline; humanities languages survive switching to STEM and back',()=>{
  const root=new Element(document,'div'); const editor=policy.mount(root);
  assert.throws(()=>editor.read(),/请选择/);
  const select=walk(root,'select')[0], boxes=walk(root,'input');
  select.value='humanities';select.onchange();assert.throws(()=>editor.read(),/至少/);
  boxes.find(b=>b.value==='zh').checked=true;boxes.find(b=>b.value==='la').checked=true;
  assert.deepEqual(editor.read(),{discipline:'humanities',allowed_languages:['zh','la']});
  select.value='stem';select.onchange();assert.deepEqual(editor.read(),{discipline:'stem',allowed_languages:['en']});
  select.value='humanities';select.onchange();assert.deepEqual(editor.read().allowed_languages,['zh','la']);
  editor.disabled(true);assert.equal(walk(root,'fieldset')[0].disabled,true);
});
test('loading an old pending project does not assign English; saved multi-language selection restores',()=>{
  const root=new Element(document,'div'), editor=policy.mount(root,{status:'pending',discipline:null,allowed_languages:[]});
  assert.throws(()=>editor.read());
  editor.set({discipline:'humanities',allowed_languages:['en','zh']});
  assert.deepEqual(editor.read().allowed_languages,['en','zh']);
  assert.match(policy.label({metadata_language:'en'}),/未核验/);
  assert.match(policy.label({fulltext_status:'verified',fulltext_language:'zh'}),/中文.*已核验/);
});
test('project settings submit the selected humanities policy once and retain it after failure',async()=>{
  const nodes=new Map();for(const name of ['paperPolicy','languageForm','languageSave','main','back','routeLink','name','nameEcho','facts','delete','confirm','notice','renameForm','rename']) nodes.set(name,new Element(document,name));
  const doc={...document,querySelector(selector){return nodes.get(selector.match(/"(.+)"/)[1]);}};
  nodes.get('paperPolicy').ownerDocument=doc;
  const project={id:'p',name:'Learning',creation_mode:'manual',keywords:[],language_policy:{status:'pending'}};
  const posts=[];let release;
  const context={document:doc,PaperPolicy:policy,location:{search:'?project_id=p'},URLSearchParams,
    localStorage:{getItem(){return null;}},fetch:async(url,opts)=>{
      if(!opts) return {ok:true,json:async()=>({projects:[project]})};
      posts.push(JSON.parse(opts.body));return await new Promise(resolve=>{release=()=>resolve({ok:false,json:async()=>({error:'temporary failure'})});});
    }};
  vm.runInNewContext(fs.readFileSync('app/static/project-page.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  const root=nodes.get('paperPolicy');walk(root,'select')[0].value='humanities';walk(root,'input').find(b=>b.value==='zh').checked=true;
  const first=nodes.get('languageForm').onsubmit({preventDefault(){}});
  await nodes.get('languageForm').onsubmit({preventDefault(){}});
  assert.deepEqual(posts,[{action:'language',discipline:'humanities',allowed_languages:['zh']}]);
  assert.equal(walk(root,'fieldset')[0].disabled,true);release();await first;
  assert.equal(walk(root,'input').find(b=>b.value==='zh').checked,true);
  assert.equal(walk(root,'fieldset')[0].disabled,false);assert.match(nodes.get('notice').textContent,/temporary failure/);
});
test('reader hashes the loaded bytes, independent of a later document or metadata ID',async()=>{
  let release;const bytes=Buffer.from('%PDF-1.4\nloaded version');
  const oldDoc={getData:()=>new Promise(resolve=>{release=()=>resolve(bytes);})};
  const pending=reader.hash(oldDoc,webcrypto);const newDoc={getData:async()=>Buffer.from('new')};
  release();assert.equal(await pending,createHash('sha256').update(bytes).digest('hex'));
  assert.notEqual(await reader.hash(newDoc,webcrypto),await pending);
  await assert.rejects(reader.hash({getData:async()=>({byteLength:128*1024*1024+1})},webcrypto),/太大/);
  await assert.rejects(reader.hash(newDoc,{}),/来源版本/);
});
function extractor(api){
  const source=fs.readFileSync('app/static/index.html','utf8');
  const body=source.slice(source.indexOf('async function extractFulltext('),source.indexOf('\nfunction setFulltextBadge('));
  const doc={}, R={key:'p',doc,fulltext:false}, timers=[], badges=[];
  const context={R,api,PDHReaderSource:{hash:async()=> 'a'.repeat(64)},setTimeout:fn=>timers.push(fn),toast(){},setFulltextBadge:(...args)=>badges.push(args)};
  vm.runInNewContext(body,context);return {context,R,doc,timers,badges};
}
test('late cached text is ignored after switching to another paper',async()=>{
  let release;const f=extractor(()=>new Promise(resolve=>{release=resolve;}));
  const run=f.context.extractFulltext('p',f.doc,[]);await new Promise(resolve=>setImmediate(resolve));
  f.R.key='next';f.R.doc={};release({pages:1,chars:10,texts:[{text:'old'}]});await run;
  assert.equal(f.R.fulltext,false);assert.deepEqual(f.badges,[]);assert.equal(f.timers.length,0);
});
test('body extraction posts the captured source hash and ignores late save responses',async()=>{
  const calls=[];let save;
  const f=extractor(async(path,payload)=>{calls.push([path,payload]);if(!payload)return {pages:0};return await new Promise(resolve=>{save=resolve;});});
  await f.context.extractFulltext('p',f.doc,[{getTextContent:async()=>({items:[{str:'current body',hasEOL:true}]})}]);
  const timer=f.timers[0]();await new Promise(resolve=>setImmediate(resolve));
  assert.match(calls[0][0],/source_pdf_sha256=aaa/);assert.equal(calls[1][1].source_pdf_sha256,'a'.repeat(64));
  assert.equal(calls[1][1].pages[0].text,'current body\n');
  f.R.key='next';f.R.doc={};save({pages:1,chars:10});await timer;
  assert.equal(f.R.fulltext,false);assert.deepEqual(f.badges,[]);
});
