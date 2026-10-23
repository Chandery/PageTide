'use strict';
// Creation page: the paper languages go with every candidate search, a Baidu Scholar problem is one short status (never an
// error that stops the page), and a Baidu hit can be added as a seed. Executes the production functions in a virtual page.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app/static/project-creation.js'),'utf8');
function slice(from,to){const start=source.indexOf(from);assert.ok(start>=0,from);const end=source.indexOf(to,start);assert.ok(end>start,to);return source.slice(start,end);}
const notes=slice('const BAIDU_PROBLEMS','\n\n');
const SEARCH_PROBLEMS=slice('const SEARCH_PROBLEMS','};')+'};';

test('one short status per Baidu problem, from a fixed table and never from server text',()=>{
  const ctx={};vm.createContext(ctx);vm.runInContext(notes+';globalThis.note=baiduNote;',ctx);
  assert.equal(ctx.note({}),'');assert.equal(ctx.note({baidu:null}),'');assert.equal(ctx.note(undefined),'');assert.equal(ctx.note(null),'');
  assert.equal(ctx.note({baidu:{kind:'quota_exhausted'}}),'百度学术：今日额度已用完');
  assert.equal(ctx.note({baidu:{kind:'auth_required'}}),'百度学术：密钥无效');
  assert.equal(ctx.note({baidu:{kind:'network_error'}}),'百度学术：无法连接');
  assert.equal(ctx.note({baidu:{kind:'unavailable'}}),'百度学术：暂时不可用');
  assert.equal(ctx.note({baidu:{kind:'bad_response',message:'secret text'}}),'百度学术：暂时不可用');
  assert.doesNotMatch(ctx.note({baidu:{kind:'<img onerror>',message:'bce-v3/ALTAK-key'}}),/img|ALTAK/);
});

function searchPage({answers,languages=['zh'],candidatesSize=0}){
  const body=slice('  async function search() {',"  part('search').onclick = search;");
  const requests=[],notices=[],slots=new Map();
  const part=name=>{if(!slots.has(name))slots.set(name,{checked:false,textContent:''});return slots.get(name);};
  const ctx={sessionId:()=>'s1',draft:()=>({search_queries:['知识图谱','信息抽取'],keywords:[]}),
    candidates:new Map(),part,searchAct:{start(){},stop(){}},skeletons(){},addCandidates(items){for(const p of items)ctx.candidates.set(p.key,p);},
    refresh(){},$$:()=>[],
    notice:(message,isError=true)=>notices.push([message,isError]),
    policyEditor:{selected:()=>languages},
    post:async(url,payload)=>{requests.push({url,payload});return answers.shift();},
    };
  vm.createContext(ctx);vm.runInContext(SEARCH_PROBLEMS+'\n'+notes+'\nlet searching=false;'+body+';globalThis.run=search;',ctx);
  return {ctx,requests,notices,run:()=>ctx.run()};
}
const item=key=>({key,title:key,matched_queries:['q']});

test('every candidate search carries the ticked paper languages',async()=>{
  const p=searchPage({answers:[{items:[item('a')],error:null},{items:[],error:null}],languages:['zh','en']});
  await p.run();
  assert.deepEqual(p.requests.map(r=>r.payload.languages),[['zh','en'],['zh','en']]);
  assert.deepEqual(p.requests.map(r=>r.payload.query),['知识图谱','信息抽取']);
  assert.ok(p.requests.every(r=>r.url==='/api/project-guidance/sessions/s1/search'));
});
test('a Baidu problem becomes one short status and the other results stay',async()=>{
  const p=searchPage({answers:[{items:[item('a')],error:null,baidu:{kind:'quota_exhausted'}},{items:[item('b')],error:null,baidu:{kind:'quota_exhausted'}}]});
  await p.run();
  assert.equal(p.requests.length,2);                                  // a Baidu problem does not stop the next query
  assert.equal(p.ctx.candidates.size,2);
  assert.deepEqual(p.notices.at(-1),['百度学术：今日额度已用完',false]);
});
test('an OpenAlex problem and a Baidu problem are shown together, OpenAlex first',async()=>{
  const p=searchPage({answers:[{items:[],error:{kind:'network_error',message:'x'},baidu:{kind:'auth_required'}},{items:[],error:null}]});
  await p.run();
  const [message,isError]=p.notices.at(-1);
  assert.equal(isError,true);assert.match(message,/^网络不通，没能连到 OpenAlex。 百度学术：密钥无效$/);
});
test('without any problem the old notices are unchanged',async()=>{
  const none=searchPage({answers:[{items:[],error:null},{items:[],error:null}]});await none.run();
  assert.deepEqual(none.notices.at(-1),['没有找到论文',false]);
});

test('a seed is added by its OpenAlex id, else by the identifier Baidu gave it',()=>{
  const ctx={};vm.createContext(ctx);vm.runInContext(slice('const seedIdentifier','\n')+';globalThis.id=seedIdentifier;',ctx);
  assert.equal(ctx.id({openalex_id:'https://openalex.org/W1',seed_id:'x'}),'https://openalex.org/W1');
  assert.equal(ctx.id({openalex_id:null,seed_id:'baidu:abc'}),'baidu:abc');
  assert.equal(ctx.id({openalex_id:null,seed_id:'https://doi.org/10.1/x'}),'https://doi.org/10.1/x');
  assert.equal(ctx.id({}),undefined);
  assert.match(source,/s\.pdfId \? \{identifier: seedIdentifier\(s\.paper\), pdf_id: s\.pdfId\} : seedIdentifier\(s\.paper\)/);
});

function seedPage(result){
  const nodes=new Map(),list={innerHTML:'',children:[],appendChild(x){this.children.push(x);}};
  const node=sel=>{if(sel==='#seedSearchList')return list;if(!nodes.has(sel))nodes.set(sel,{hidden:true,textContent:'',innerHTML:'',classList:{toggle(){}},onclick:null});return nodes.get(sel);};
  const body=slice('async function openSeedSearch(query) {','const seedRemoveByKey');
  const ctx={$:(sel,root)=>root?{onclick:null,textContent:''}:node(sel),searchAct:{start(){},stop(){}},queued:fn=>fn(),
    post:async()=>result,seedFailure:r=>'失败：'+r.status,esc:x=>String(x??''),meta:()=>'meta',seeds:[],
    document:{createElement:()=>({className:'',innerHTML:''})},seedNew:()=>({}),seedUpdate(){},seedRemoveByKey(){}};
  vm.createContext(ctx);vm.runInContext(notes+'\nlet searchToken=0;'+body+';globalThis.open=openSeedSearch;',ctx);
  return {node,list,open:q=>ctx.open(q)};
}
test('the seed search shows a Baidu problem beside the hits, and only a failure of both as a failure',async()=>{
  const hits=seedPage({status:'ok',items:[{key:'k',title:'t',abstract:'a'}],baidu:{kind:'quota_exhausted'}});
  await hits.open('知识图谱构建');
  assert.equal(hits.node('#seedSearchNotice').hidden,false);assert.equal(hits.node('#seedSearchNotice').textContent,'百度学术：今日额度已用完');
  assert.equal(hits.list.children.length,1);
  const quiet=seedPage({status:'ok',items:[{key:'k',title:'t',abstract:'a'}]});await quiet.open('知识图谱构建');
  assert.equal(quiet.node('#seedSearchNotice').hidden,true);
  const failed=seedPage({status:'network_error',items:[],baidu:{kind:'auth_required'}});await failed.open('知识图谱构建');
  assert.match(failed.node('#seedSearchNotice').textContent,/失败：network_error/);assert.match(failed.node('#seedSearchNotice').textContent,/百度学术：密钥无效/);
  const empty=seedPage({status:'empty',items:[]});await empty.open('知识图谱构建');
  assert.equal(empty.node('#seedSearchNotice').textContent,'没有找到');
});
