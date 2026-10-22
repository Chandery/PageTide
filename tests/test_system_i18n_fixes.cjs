'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=name=>fs.readFileSync(path.join(__dirname,'../app/static/',name),'utf8');
const messages=JSON.parse(read('i18n/en-US.json')).messages;
const decode=text=>text.replace(/&(?:amp|lt|gt|quot|#39);/g,value=>({'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&#39;':"'"}[value]));

// A DOM transport for real generated markup and the shipped MutationObserver
// callback. Filtering/translation is executed by i18n.js, not mirrored here.
function browser(lang) {
  let observer;
  const listeners=new Map();
  class Element {
    constructor(tag,attributes={}){this.nodeType=1;this.tagName=tag.toUpperCase();this.attrs=attributes;this.childNodes=[];this.parentElement=null;this.open=false;this.dataset={};}
    get children(){return this.childNodes.filter(node=>node.nodeType===1);}
    get textContent(){return this.childNodes.map(node=>node.nodeType===3?node.nodeValue:node.textContent).join('');}
    set textContent(value){this.childNodes=[];this.append({nodeType:3,nodeValue:String(value),parentElement:null});}
    replaceChildren(...nodes){this.childNodes=[];this.append(...nodes);}
    getAttribute(key){return this.attrs[key]??null;}
    setAttribute(key,value){this.attrs[key]=String(value);}
    hasAttribute(key){return key in this.attrs;}
    matches(selectors){return selectors.split(',').some(selector=>{
      selector=selector.trim();
      if(selector.includes(' ')){const parts=selector.split(/\s+/),last=parts.pop();return this.matches(last)&&!!this.parentElement?.closest(parts.join(' '));}
      if(selector.startsWith('.'))return (this.attrs.class||'').split(/\s+/).includes(selector.slice(1));
      if(selector.startsWith('#'))return this.attrs.id===selector.slice(1);
      const match=selector.match(/^(\w+)?\[([^=\]]+)(?:="([^"]*)")?\]$/);
      if(match)return (!match[1]||this.tagName===match[1].toUpperCase())&&this.hasAttribute(match[2])&&(match[3]===undefined||this.attrs[match[2]]===match[3]);
      return this.tagName===selector.toUpperCase();
    });}
    closest(selector){for(let node=this;node;node=node.parentElement)if(node.matches(selector))return node;return null;}
    append(...nodes){for(const node of nodes){node.parentElement=this;this.childNodes.push(node);}}
    appendChild(node){this.append(node);return node;}
    remove(){if(this.parentElement)this.parentElement.childNodes=this.parentElement.childNodes.filter(node=>node!==this);}
    addEventListener(name,fn){listeners.set(name,fn);}
    querySelectorAll(selector){return all(this).filter(node=>node.nodeType===1&&node!==this&&node.matches(selector));}
    querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
    showModal(){this.open=true;this.attrs.open='';}
    close(){this.open=false;delete this.attrs.open;}
    set innerHTML(html){
      this.childNodes=[];const stack=[this];
      for(const token of String(html).match(/<[^>]*>|[^<]+/g)||[]){
        if(token.startsWith('</')){const tag=token.match(/^<\/([\w-]+)/)[1].toUpperCase();const index=stack.findLastIndex(node=>node.tagName===tag);if(index>0)stack.length=index;continue;}
        if(token.startsWith('<')){const match=token.match(/^<([\w-]+)([\s\S]*?)\/?\s*>$/);if(!match)continue;const attrs={};for(const attr of match[2].matchAll(/([\w-]+)(?:="([^"]*)"|'([^']*)')?/g))attrs[attr[1]]=decode(attr[2]??attr[3]??'');const node=new Element(match[1],attrs);stack.at(-1).append(node);if(!/\/\s*>$/.test(token)&&!['INPUT','BR','IMG','META','LINK','HR'].includes(node.tagName))stack.push(node);}
        else stack.at(-1).append({nodeType:3,nodeValue:decode(token),parentElement:null});
      }
    }
  }
  const all=node=>[node,...(node.childNodes||[]).flatMap(all)];
  const root=new Element('main'),html=new Element('html');html.append(root);
  const document={documentElement:html,createElement:tag=>new Element(tag),addEventListener(){},createTreeWalker(node,_show,filter){const out=[];const visit=element=>{for(const child of element.childNodes||[]){const result=filter.acceptNode(child);if(result!==2){out.push(child);visit(child);}}};visit(node);let index=0;return {nextNode:()=>out[index++]||null};}};
  const context=vm.createContext({document,NodeFilter:{SHOW_ELEMENT:1,SHOW_TEXT:4,FILTER_ACCEPT:1,FILTER_REJECT:2},MutationObserver:class{constructor(callback){observer=callback;}observe(){}},PDH_I18N:{lang,messages},URLSearchParams});context.window=context;
  const language=next=>{observer=undefined;context.PDH_I18N={lang:next,messages};vm.runInContext(read('i18n.js'),context);};language(lang);
  vm.runInContext(read('profile-ui.js'),context);
  const flush=()=>observer?.([{type:'childList',addedNodes:[root]}]);
  const text=()=>all(root).filter(node=>node.nodeType===3).map(node=>node.nodeValue).join('');
  const systems=()=>all(root).flatMap(node=>node.nodeType===3&&!node.parentElement.closest('[data-no-i18n]')?[node.nodeValue]:node.nodeType===1&&!node.closest('[data-no-i18n]')?['title','placeholder','aria-label','alt'].map(key=>node.getAttribute(key)||''):[]).join('');
  return {context,root,flush,text,systems,language,listeners,all};
}
const entry={key:'paper',title:'收藏',kind:'positive',action:'useful',published:'2026',time:'2026-10-08',sources:['seed','useful_feedback'],reason:'有用',feedback_id:1};
const fixture=()=>({coverage:{start:'2026-09-01',end:'2026-10-08',last_activity:null},signals:{saved:2,positive:1,negative:1,too_hard:1},timeline:{weeks:[{start:'2026-10-01',end:'2026-10-08',saved:2,positive:1,negative:1,too_hard:1,exposed:2,activity:7}]},keyword_distribution:[{term:'有用',documents:2,sources:['seed','useful_feedback']}],keyword_evidence:{papers:2},inventory_distribution:[{term:'种子'}],inventory_evidence:{papers:1},weekly_change:{week_start:'2026-10-01',week_end:'2026-10-08',stats:{saved:2,positive:1},previous_stats:{saved:1},has_activity:true,comparable:true,keyword_changes:{rising:[{term:'收藏',delta:1}],falling:[]}},recent_feedback:[entry],versions:[{id:1,created_at:'2026-10-01',data:{pinned_terms:['有用']}}]});
function profile(b){const page=b.context.PDHProfile.create(b.root,{api:async()=>({items:[entry],total:1}),refresh(){},projectName:()=> '有用',openPaper(){},notify(){}});page.render(fixture(),{project_id:'p',pinned_terms:['收藏'],frozen:false},'有用');return page;}

test('actual recommendation cards preserve original titles and show no source-report language lines in either interface',()=>{
  for(const lang of ['zh-CN','en-US']){
    const b=browser(lang),src=read('index.html');vm.runInContext(read('paper-policy.js'),b.context);
    Object.assign(b.context,{esc:b.context.PDHProfile.esc,state:{triaging:false,triagingKeys:new Set(),currentProject:'p'},pdfBadge:()=>'',routeBadge:()=>'',explorationEvidence:()=>'',aiSlot:()=>'<b>AI 速览</b><span data-no-i18n>AI 中文解释</span>'});
    vm.runInContext(src.slice(src.indexOf('function cardHTML('),src.indexOf('function renderCards(')),b.context);
    b.root.innerHTML=b.context.cardHTML({key:'paper',title:'中文原始题名',language:{metadata_language:'en',metadata_source:'OpenAlex',fulltext_status:'unverified',title_metadata_conflict:true},why:''},0);b.flush();
    assert.equal(b.root.querySelector('.paper-title').textContent,'中文原始题名');assert.match(b.text(),/AI 中文解释/);assert.doesNotMatch(b.text(),/OpenAlex|来源报告语言|全文语言未核验|题名文字与英文来源报告不一致|Source-reported language|Full-text language|title.*source.*report/i);
    if(lang==='en-US')assert.doesNotMatch(b.systems(),/[㐀-鿿]/,b.systems());
  }
});

test('actual profile feedback rows, source labels and composite statistics render in English',()=>{
  const b=browser('en-US');profile(b);b.flush();
  assert.doesNotMatch(b.systems(),/[㐀-鿿]/,b.systems());
  assert.match(b.text(),/Useful/);assert.match(b.text(),/Useful · 2026-10-08/);assert.doesNotMatch(b.text(),/current feedback:/i);assert.match(b.text(),/Useful rate/);assert.match(b.text(),/Too hard/);
  assert.equal(b.root.querySelector('.profile-term').getAttribute('title'),'Source: Seed / Useful feedback');
});
test('profile protects CJK user titles, project names, keywords and feedback reasons even if they equal UI labels',()=>{
  const b=browser('en-US');profile(b);b.flush();
  const values=b.root.querySelectorAll('[data-no-i18n]').map(node=>b.all(node).filter(n=>n.nodeType===3).map(n=>n.nodeValue).join(''));
  assert.ok(values.filter(value=>value==='有用').length>=3,values.join(' | '));
  assert.ok(values.filter(value=>value==='收藏').length>=3,values.join(' | '));assert.ok(values.includes('种子'));
});
test('actual profile evidence drawer and rerender switch system language while preserving original user data',async()=>{
  const b=browser('en-US'),page=profile(b);
  const button={hasAttribute:name=>name==='data-history'};
  await b.listeners.get('click')({target:{closest:()=>button}});b.flush();
  assert.doesNotMatch(b.systems(),/[㐀-鿿]/,b.systems());assert.match(b.text(),/收藏/);
  b.language('zh-CN');page.render(fixture(),{project_id:'p',pinned_terms:['收藏'],frozen:false},'有用');b.flush();
  assert.match(b.text(),/有用 · 2026-10-08/);assert.doesNotMatch(b.text(),/当前反馈：/);assert.match(b.text(),/有用率/);assert.match(b.text(),/收藏/);
});

test('profile empty, frozen and all explicit feedback kinds keep their system labels in English',()=>{
  for(const kind of ['positive','saved','negative','too_hard','understood','seed','exposed','other']){
    const b=browser('en-US'),page=profile(b),data=fixture();data.recent_feedback=[{...entry,kind,action:({positive:'useful',negative:'irrelevant',too_hard:'too_hard',understood:'understood'})[kind],sources:['seed','saved']}];
    data.weekly_change.comparable=false;data.weekly_change.has_activity=false;data.timeline.weeks=[];
    page.render(data,{project_id:'p',pinned_terms:['收藏'],frozen:true,frozen_at:'2026-10-08'},'有用');b.flush();assert.doesNotMatch(b.systems(),/[㐀-鿿]/,kind+': '+b.systems());
  }
  const b=browser('en-US'),page=profile(b),data=fixture();data.signals={};data.keyword_distribution=[];data.inventory_distribution=[];data.recent_feedback=[];data.versions=[];data.weekly_change={comparable:false,has_activity:false};
  page.render(data,{project_id:'p',pinned_terms:[],frozen:false},'收藏');b.flush();assert.doesNotMatch(b.systems(),/[㐀-鿿]/,b.systems());
});

test('actual project facts translate fixed creation modes and the empty keyword placeholder only',()=>{
  for(const creation_mode of ['quick','manual','ai_guided']){
    const b=browser('en-US');b.root.innerHTML=read('project.html');b.context.part=role=>b.root.querySelector(`[data-role="${role}"]`);
    b.context.state={project:{id:'p',name:'有用',creation_mode,keywords:[]},busy:false};
    const src=read('project-page.js');vm.runInContext(src.slice(src.indexOf('function matches('),src.indexOf("part('confirm').oninput")),b.context);
    b.context.render();b.flush();const facts=b.context.part('facts');
    assert.doesNotMatch(facts.textContent,/[㐀-鿿]/,facts.textContent);assert.match(facts.textContent,/none yet/);
    b.context.state.project.keywords=['收藏'];b.context.render();b.flush();assert.match(facts.textContent,/收藏/);assert.equal(b.context.part('nameEcho').textContent,'有用');
  }
});
test('actual route detail translates system prerequisite tooltips without changing concept names',()=>{
  const b=browser('en-US');vm.runInContext(read('route-editor.js'),b.context);
  const graph={concepts:[{id:'a',name:'收藏',terms:['种子']},{id:'b',name:'有用',terms:[]}],targets:['b'],prereqs:[{from:'a',to:'b',support:0.6}]};
  b.root.innerHTML=b.context.PDHRoute.detailHTML(graph,graph.concepts[1],{});b.flush();
  const chip=b.root.querySelector('.need');assert.equal(chip.textContent,'收藏');assert.doesNotMatch(chip.getAttribute('title'),/[㐀-鿿]/);assert.match(chip.getAttribute('title'),/supports/);
});
test('actual import row errors translate defaults and saved identity warnings while preserving filenames and paper titles',()=>{
  const b=browser('en-US'),src=read('import.js');b.context.esc=b.context.PDHProfile.esc;
  vm.runInContext(src.slice(src.indexOf('const systemError ='),src.indexOf('\nfunction fail('))+'\n'+src.slice(src.indexOf('function paperLine('),src.indexOf("$('#tabs').addEventListener")),b.context);
  for(const item of [{id:1,state:'failed',relative_path:'收藏.pdf'},{id:2,state:'unmatched',relative_path:'有用.pdf',error:'标识对应的库内题名与 PDF 首页不一致，请核对后选择',paper:{title:'收藏'}}]){
    b.root.innerHTML=b.context.renderRow(item);b.flush();const errors=b.root.querySelectorAll('.err').map(node=>node.textContent).join('');
    assert.doesNotMatch(errors,/[㐀-鿿]/,errors);assert.match(b.text(),/收藏.pdf|有用.pdf/);if(item.paper)assert.equal(b.root.querySelector('.row-paper').textContent,'收藏');
  }
  b.root.innerHTML=b.context.renderRow({id:3,state:'failed',relative_path:'收藏.pdf',error:'条目 <img src=x onerror=1> 没有标题'});b.flush();
  assert.equal(b.root.querySelector('img'),null);assert.match(b.root.querySelector('.err').textContent,/Entry <img src=x onerror=1> has no title/);
});
test('actual intro-input excerpts translate their labels and stay exact; a partial-input receipt is not drawn',()=>{
  const b=browser('en-US');vm.runInContext(read('route-editor.js'),b.context);b.context.esc=b.context.PDHProfile.esc;
  b.root.innerHTML=b.context.PDHRoute.introInputHTML({scope_notice:'部分匹配论文因本次预算未发送；简介只依据下列节选起草。',context_excerpt:{concept:'收藏',terms:['有用'],goal:'种子',papers:[{title:'太难',abstract:'不相关'}]}});b.flush();
  assert.equal(b.root.querySelector('.map-note'),null);assert.doesNotMatch(b.text(),/部分匹配论文因本次预算未发送|Some matched papers/);
  assert.doesNotMatch(b.systems(),/[㐀-鿿]/,b.systems());assert.match(b.text(),/收藏/);assert.match(b.text(),/不相关/);
});
test('actual learning-map undo describes the fixed system event in the current language',()=>{
  const b=browser('en-US');vm.runInContext(read('route-editor.js'),b.context);b.context.R=b.context.PDHRoute;b.context.esc=b.context.PDHProfile.esc;
  b.context.growth={result:{candidates:[],pending:[]},undo:{id:1,label:'保存学习路径',revision:2},judging:false};b.context.state={route:{revision:2},dirty:false};b.context.part=()=>b.root;
  const src=read('route-page.js');vm.runInContext(src.slice(src.indexOf('function renderGrowth()'),src.indexOf('async function loadGrowth()')),b.context);
  b.context.renderGrowth();b.flush();assert.doesNotMatch(b.systems(),/[㐀-鿿]/,b.systems());assert.match(b.text(),/Save learning path/);assert.match(b.text(),/Undo/);
});

function organization(b){
  b.context.module={exports:{}};b.context.addEventListener=()=>{};
  const storage=new Map();b.context.localStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)};
  b.context.crypto={randomUUID:()=> 'local-test-client'};b.context.setTimeout=setTimeout;b.context.clearTimeout=clearTimeout;b.context.URL=URL;
  b.context.PDH={state:{currentProject:'p'},api:async()=>{throw Error('Unexpected request');}};
  vm.runInContext(read('organization.js'),b.context);return b.context.module.exports;
}
test('actual library project tags and paper selectors retain user names in text and accessible labels',()=>{
  const b=browser('en-US'),ui=organization(b),p={key:'one',title:'收藏',projects:['p','other'],directions:[],understood_in:[]};
  ui.S.snapshot={projects:[{id:'p',name:'有用'},{id:'other',name:'收藏'}],directions:[],items:[p]};
  ui.S.scope='p';ui.S.root=b.root;b.root.innerHTML='<div class="org-bulk"></div><div class="org-list"></div>';
  ui.renderList();b.flush();
  const selected=b.root.querySelector('[data-select-key]');assert.equal(selected.getAttribute('aria-label'),'Select 收藏');
  const tag=b.root.querySelector('.is-current');assert.equal(tag.getAttribute('title'),null);assert.equal(tag.textContent,'有用');
  const also=b.root.querySelector('.is-also');assert.equal(also.getAttribute('title'),'收藏');assert.match(also.textContent,/Also in:收藏/);
  const understood=b.root.querySelector('[data-action="understood"]');assert.equal(understood.getAttribute('data-project'),'p');assert.equal(understood.getAttribute('title'),null);assert.doesNotMatch(understood.textContent,/[㐀-鿿]/);
});
test('actual library undo handles fixed event labels in both languages',()=>{
  const b=browser('en-US'),ui=organization(b);b.root.innerHTML=ui.undoHTML({id:2,label:'保存学习路径'});b.flush();
  assert.match(b.text(),/Undo Save learning path/);assert.equal(b.root.querySelector('button').getAttribute('title'),'Undo: Save learning path');
  b.language('zh-CN');b.root.innerHTML=ui.undoHTML({id:2,label:'保存学习路径'});b.flush();assert.equal(b.text(),'撤销保存学习路径');
});
test('typed parser-system formatter translates error frames while preserving raw record identifiers and snippets',()=>{
  const b=browser('en-US');
  assert.equal(b.context.PDHi18n.system('条目 收藏 没有标题'),'Entry 收藏 has no title');
  assert.equal(b.context.PDHi18n.system('条目 有用：字段没有结束'),'Entry 有用: A field is not closed');
  assert.equal(b.context.PDHi18n.system('有一个条目没有结束：收藏 <title>'),'An entry is not closed: 收藏 <title>');
  assert.equal(b.context.PDHi18n.system('第 2 项没有读取：没有标题'),'Item 2 was not read: No title');
  for(const error of ['第 2 条记录没有标题','第 3 条记录缺少 ER 结束标记，已跳过','条目超过上限 20，多出的没有读取'])assert.doesNotMatch(b.context.PDHi18n.system(error),/[㐀-鿿]/);
  assert.equal(b.context.PDHi18n.system('Unknown diagnostic 收藏'),'Unknown diagnostic 收藏');
  b.language('zh-CN');assert.equal(b.context.PDHi18n.system('条目 收藏 没有标题'),'条目 收藏 没有标题');
});
test('actual sidecar upload and creation failure row use typed system errors and preserve filenames',async()=>{
  const b=browser('en-US'),src=read('import.js');b.context.esc=b.context.PDHProfile.esc;b.context.$=selector=>b.root.querySelector(selector);
  b.root.innerHTML='<div id="sidecarNote"></div><ul id="seedList"></ul>';
  b.context.S={batch:{id:'sidecar-test'},stage:'upload'};
  b.context.api=async()=>({entries:2,with_files:1,errors:['第 2 条记录没有标题','条目 收藏 没有标题']});b.context.batchUrl=()=>'/local-test';
  vm.runInContext(src.slice(src.indexOf('const systemError ='),src.indexOf('\nfunction fail('))+'\n'+src.slice(src.indexOf('async function uploadSidecar('),src.indexOf('async function uploadOne(')),b.context);
  await b.context.uploadSidecar({sidecars:[{format:'ris',file:{name:'收藏.ris'}},{format:'bibtex',file:{name:'有用.bib'}}]});b.flush();
  assert.match(b.text(),/Record 2 has no title/);assert.match(b.text(),/Entry 收藏 has no title/);assert.doesNotMatch(b.text(),/\.ris|\.bib/);
  const creation=read('project-creation.js');vm.runInContext(creation.slice(creation.indexOf('function seedRow('),creation.indexOf('function seedUpdate(')),b.context);
  b.context.seedRow({id:1,kind:'pdf',status:'failed',filename:'收藏.pdf',error:'第 3 条记录缺少 ER 结束标记，已跳过'});b.flush();
  assert.doesNotMatch(b.root.querySelector('.bad').textContent,/[㐀-鿿]/);assert.match(b.text(),/Record 3 has no ER ending marker/);assert.match(b.text(),/收藏.pdf/);
});

test('actual library category names stay original in directory, breadcrumb and detail actions',()=>{
  const b=browser('en-US'),ui=organization(b),p={key:'one',title:'有用',projects:['p'],directions:['d']};
  ui.S.snapshot={projects:[{id:'p',name:'收藏'}],directions:[{id:'d',name:'收藏',rank:0}],items:[p]};ui.S.scope='p';ui.S.filter='d';ui.S.root=b.root;
  b.root.innerHTML='<div class="org-bulk"></div><div class="org-list"></div><section id="sidebar"></section><section id="detail"></section>';
  ui.renderList();b.root.querySelector('#sidebar').innerHTML=ui.sidebarHTML();b.root.querySelector('#detail').innerHTML=ui.detailCategoriesHTML(p);b.flush();
  assert.equal(b.root.querySelector('.org-breadcrumb').textContent,'收藏');
  assert.equal(b.root.querySelector('.org-directory-name').getAttribute('title'),'收藏');
  assert.equal(b.root.querySelector('.org-detail-badge').textContent,'收藏');
  assert.equal(b.root.querySelector('.org-detail-badge').getAttribute('data-id'),'d');assert.equal(b.root.querySelector('.org-detail-badge').getAttribute('title'),null);
  assert.ok(b.root.querySelectorAll('.org-tags')[0].textContent.includes('收藏'));
});

test('actual persisted import rejection reports a file that failed to save, without claiming no transmission',()=>{
  const b=browser('en-US'),src=read('import.js');b.context.esc=b.context.PDHProfile.esc;b.context.$=selector=>b.root.querySelector(selector);
  b.root.innerHTML='<section id="failedBox"><p id="failedText"></p><ul id="failedList"></ul><button id="addMore"></button></section>';
  b.context.S={uploadFailed:[],batch:{id:'b',upload_failures:[{path:'收藏.pdf',message:'这不是 PDF 文件'}],counts:{failed:0}}};
  vm.runInContext(src.slice(src.indexOf('const systemError ='),src.indexOf('\nfunction fail('))+'\n'+src.slice(src.indexOf('function renderFailedUploads()'),src.indexOf('function renderCategories(')),b.context);
  b.context.renderFailedUploads();b.flush();assert.match(b.root.querySelector('#failedText').textContent,/failed to save/);assert.doesNotMatch(b.text(),/not uploaded|not transmitted/);assert.match(b.text(),/收藏.pdf/);assert.match(b.text(),/not a PDF file/);
  b.language('zh-CN');b.context.renderFailedUploads();b.flush();assert.match(b.root.querySelector('#failedText').textContent,/保存失败/);assert.doesNotMatch(b.text(),/未上传/);
});
