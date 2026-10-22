'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto,createHash}=require('node:crypto');
const policy=require('../app/static/paper-policy.js');
const reader=require('../app/static/reader-source.js');
class Element {
  constructor(doc,tag) {this.ownerDocument=doc;this.tag=tag;this.children=[];this.value='';this.attrs={};this.hidden=false;this.textContent='';this.events=[];this.classList={add(){},toggle(){}};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(key,value){this.attrs[key]=String(value);}
  removeAttribute(key){delete this.attrs[key];}
  scrollIntoView(){this.events.push('scroll');}
  focus(){this.events.push('focus');}
}
const document={createElement(tag){return new Element(this,tag);},createTextNode(text){return {textContent:text};}};
const walk=(el,tag)=>[...(el.tag===tag?[el]:[]),...(el.children||[]).flatMap(c=>walk(c,tag))];
const rows=root=>walk(root,'label').map(label=>{const box=label.children.find(c=>c.tag==='input'),text=label.children.find(c=>!c.tag);return {text:text.textContent,value:box.value,checked:!!box.checked,box};});
test('the editor offers exactly two check boxes, 中文 and 英文, none ticked for a new project, and no discipline drop-down',()=>{
  const root=new Element(document,'div'); const editor=policy.mount(root);
  assert.deepEqual(rows(root).map(r=>[r.text,r.value,r.checked]),[['中文','zh',false],['英文','en',false]]);
  assert.equal(walk(root,'select').length,0);
  assert.equal(JSON.stringify(root.children).includes('理工科'),false);assert.equal(JSON.stringify(root.children).includes('文科'),false);
  assert.equal(JSON.stringify(root.children).includes('学科'),false);
  assert.throws(()=>editor.read(),/至少选择一种/);
  rows(root)[1].box.checked=true;assert.deepEqual(editor.read(),{allowed_languages:['en']});
  rows(root)[0].box.checked=true;assert.deepEqual(editor.read(),{allowed_languages:['zh','en']});
  rows(root)[1].box.checked=false;assert.deepEqual(editor.read(),{allowed_languages:['zh']});
  assert.deepEqual(editor.selected(),['zh']);
  editor.disabled(true);assert.equal(walk(root,'fieldset')[0].disabled,true);
});
test('the editor shows its own surface only: a heading inside the card (not a legend on its border) and two boxes, no explanation text',()=>{
  const root=new Element(document,'div'); policy.mount(root);
  assert.equal(walk(root,'legend').length,0,'a legend would sit on the fieldset border');
  const heading=walk(root,'h3');assert.equal(heading.length,1);assert.equal(heading[0].textContent,'论文语言');
  const fieldset=walk(root,'fieldset')[0];assert.equal(fieldset.attrs['aria-labelledby'],heading[0].id);assert.ok(heading[0].id);
  assert.equal(fieldset.children[0],heading[0]);
  const text=[];(function collect(n){if(n.textContent&&!n.tag)text.push(n.textContent);if(n.tag==='h3')text.push(n.textContent);(n.children||[]).forEach(collect);})(root);
  assert.deepEqual(text.filter(Boolean),['论文语言','中文','英文']);
});
test('with nothing ticked the error appears inside the editor at the boxes, marks them, and clears when a box changes',()=>{
  const root=new Element(document,'div'); const editor=policy.mount(root);
  const error=walk(root,'p')[0];assert.equal(error.hidden,true);
  assert.throws(()=>editor.read());editor.error('请至少选择一种论文语言');
  assert.equal(error.hidden,false);assert.equal(error.textContent,'请至少选择一种论文语言');assert.equal(error.attrs.role,'alert');
  assert.ok(rows(root).every(r=>r.box.attrs['aria-invalid']==='true'));
  assert.deepEqual(rows(root)[0].box.events,['scroll','focus']);
  rows(root)[0].box.checked=true;rows(root)[0].box.onchange();
  assert.equal(error.hidden,true);assert.ok(rows(root).every(r=>!('aria-invalid' in r.box.attrs)));
  editor.error('again',false);assert.equal(error.hidden,false);assert.deepEqual(rows(root)[1].box.events,[]);
  editor.error('');assert.equal(error.hidden,true);
});
test('a saved project shows its languages ticked; extra legacy languages appear as ticked boxes so none is dropped silently',()=>{
  const root=new Element(document,'div'), editor=policy.mount(root,{status:'pending',discipline:null,allowed_languages:[]});
  assert.throws(()=>editor.read());
  editor.set({status:'ready',discipline:'humanities',allowed_languages:['en','zh']});
  assert.deepEqual(editor.read().allowed_languages,['zh','en']);assert.equal(rows(root).length,2);
  editor.set({status:'ready',discipline:'humanities',allowed_languages:['zh','la','ja']});
  assert.deepEqual(rows(root).map(r=>[r.text,r.value,r.checked]),[['中文','zh',true],['英文','en',false],['拉丁文','la',true],['日文','ja',true]]);
  assert.deepEqual(editor.read().allowed_languages,['zh','la','ja']);
  rows(root)[2].box.checked=false;assert.deepEqual(editor.read().allowed_languages,['zh','ja']);
  rows(root)[3].box.checked=false;rows(root)[1].box.checked=true;assert.deepEqual(editor.read().allowed_languages,['zh','en']);
  editor.set({status:'ready',discipline:'stem',allowed_languages:['en']});
  assert.deepEqual(rows(root).map(r=>[r.value,r.checked]),[['zh',false],['en',true]]);
  editor.set({allowed_languages:['xx']});assert.equal(rows(root).length,2);   // an unknown code is not shown as a box
  assert.match(policy.label({metadata_language:'en'}),/未核验/);
  assert.match(policy.label({fulltext_status:'verified',fulltext_language:'zh'}),/中文.*已核验/);
});
test('validation needs only languages and rejects empty, unknown or non-text codes',()=>{
  assert.deepEqual(policy.validate({allowed_languages:['zh','zh','en']}),{allowed_languages:['zh','en']});
  for(const bad of [null,{},{allowed_languages:[]},{allowed_languages:['xx']},{allowed_languages:[1]},{allowed_languages:'zh'}])assert.throws(()=>policy.validate(bad),/至少选择一种/);
});
test('language report distinguishes the source claim and current-PDF evidence without changing a conflicting title',()=>{
  const report=policy.report({metadata_language:'en',metadata_source:'OpenAlex',fulltext_status:'unverified',title_metadata_conflict:true});
  assert.match(report,/来源报告语言：英文（OpenAlex）/);assert.match(report,/全文语言未核验/);assert.match(report,/题名文字与英文来源报告不一致/);
  const verified=policy.report({metadata_language:'en',metadata_source:'OpenAlex',fulltext_status:'verified',fulltext_language:'en',title_metadata_conflict:true});
  assert.match(verified,/全文语言：英文（已核验）/);assert.doesNotMatch(verified,/全文语言未核验|全文语言：中文/);
  assert.match(policy.report({fulltext_status:'unverified'}),/来源报告语言：未知/);
});
test('project settings submit the ticked languages once, without a discipline, and retain them after failure',async()=>{
  const nodes=new Map();for(const name of ['paperPolicy','languageForm','languageSave','main','back','routeLink','name','nameEcho','facts','delete','confirm','notice','renameForm','rename']) nodes.set(name,new Element(document,name));
  const doc={...document,querySelector(selector){return nodes.get(selector.match(/"(.+)"/)[1]);}};
  nodes.get('paperPolicy').ownerDocument=doc;
  const project={id:'p',name:'Learning',creation_mode:'manual',keywords:[],language_policy:{status:'pending'},goal_confirmation:'机器人规划里的世界模型'};
  const posts=[];let release;
  const context={document:doc,PaperPolicy:policy,location:{search:'?project_id=p'},URLSearchParams,
    localStorage:{getItem(){return null;}},fetch:async(url,opts)=>{
      if(!opts) return {ok:true,json:async()=>({projects:[project]})};
      posts.push(JSON.parse(opts.body));return await new Promise(resolve=>{release=()=>resolve({ok:false,json:async()=>({error:'temporary failure'})});});
    }};
  vm.runInNewContext(fs.readFileSync('app/static/project-page.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  const factLabels=walk(nodes.get('facts'),'dt').map(dt=>dt.textContent);
  assert.ok(factLabels.includes('创建时与 AI 确认的目标'),'the saved goal says it came from the creation conversation: '+factLabels);
  assert.ok(!factLabels.includes('目标确认'));
  const root=nodes.get('paperPolicy');walk(root,'input').find(b=>b.value==='zh').checked=true;
  const first=nodes.get('languageForm').onsubmit({preventDefault(){}});
  await nodes.get('languageForm').onsubmit({preventDefault(){}});
  assert.deepEqual(posts,[{action:'language',allowed_languages:['zh']}]);
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
  await assert.rejects(reader.hash(newDoc,{}),/哪个 PDF 版本/);
});
function extractor(api){
  const source=fs.readFileSync('app/static/index.html','utf8');
  const body=source.slice(source.indexOf('async function extractFulltext('),source.indexOf('\nfunction setFulltextBadge('));
  const doc={}, R={key:'p',doc,fulltext:false}, timers=[], badges=[], invalidations=[];
  const context={R,api,window:{PDHOrganization:{invalidateLearning:key=>invalidations.push(key)}},PDHReaderSource:{hash:async()=> 'a'.repeat(64)},setTimeout:fn=>timers.push(fn),toast(){},setFulltextBadge:(...args)=>badges.push(args)};
  vm.runInNewContext(body,context);return {context,R,doc,timers,badges,invalidations};
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
  assert.deepEqual(f.invalidations,['p']);
  assert.equal(f.R.fulltext,false);assert.deepEqual(f.badges,[]);
});

test('closing the actual reader refreshes learning views after a version or text change',()=>{
  const source=fs.readFileSync('app/static/index.html','utf8');
  const close=source.slice(source.indexOf('function closeReader() {'),source.indexOf('function readerControls() {'));
  const assistant=source.slice(source.indexOf('function dockPanel(dock) {'),source.indexOf('function openPet()'));
  const line=assistant+close + source.split('\n').find(s=>s.startsWith("$('#readerBack').onclick ="));
  const nodes=new Map(),calls=[],frames=[];
  const classes=()=>{const values=new Set();return {add:name=>values.add(name),remove:name=>values.delete(name),contains:name=>values.has(name),toggle:(name,on)=>on?values.add(name):values.delete(name)};};
  const node=id=>{if(!nodes.has(id))nodes.set(id,{classList:classes(),clientWidth:640,value:''});return nodes.get(id);};
  const body={classList:classes(),appendChild(element){element.parentElement=this;}},state={key:'p',epoch:0,doc:{}};
  node('#petPanel').classList.add('open');node('#petPanel').classList.add('docked');node('#transPop').classList.add('show');
  node('#petInput').value='中文问题\n第二行';body.classList.add('reader-open');
  vm.runInNewContext(line,{$:node,R:state,pet:{busy:false},readerBackground:new Map(),readerFocus:null,setReference(){},setAttachPage(){},hideSel(){},document:{body},requestAnimationFrame:fn=>frames.push(fn),layoutPages:()=>calls.push(['layout']),toast(){},window:{PDHOrganization:{invalidateLearning:(...args)=>{calls.push(args);return Promise.resolve();}}}});
  node('#readerBack').onclick();assert.deepEqual(calls,[['p',true]]);
  assert.equal(node('#petPanel').classList.contains('open'),false);
  assert.equal(node('#petPanel').classList.contains('docked'),false);assert.equal(node('#petPanel').parentElement,body);
  assert.equal(node('#reader').classList.contains('hidden'),true);assert.equal(node('#transPop').classList.contains('show'),false);
  assert.equal(node('#petInput').value,'中文问题\n第二行');assert.equal(state.epoch,1);
  assert.equal(frames.length,1);for(const frame of frames)frame();assert.deepEqual(calls,[['p',true]]);
});
