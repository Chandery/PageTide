'use strict';
// Settings page: one row per data source (switch, key, status word, test, clear, get). Whitespace first: short words only.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../app/static/settings.html'),'utf8');
const source=html.match(/<script>\s*const \$[\s\S]*?<\/script>/)[0].replace(/^<script>|<\/script>$/g,'').replace(/\n\s*loadSettings\(\);\s*$/,'');
const KEY='bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000';
const SOURCES={
  openalex:{needs_key:false,key:'optional',configured:false,status_kind:null,used_today:null,daily_cap:null,key_url:'https://help.openalex.org/api-reference/authentication'},
};
function page({sources=SOURCES,settings={},confirm}={}){
  const nodes=new Map(),calls=[],confirms=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,textContent:'',disabled:false,hidden:false,href:'',dataset:{},setAttribute(){}});return nodes.get(id);};
  const context={document:{querySelector:node,documentElement:{dataset:{}}},
    localStorage:{getItem(){return null;},setItem(){},removeItem(){}},matchMedia:()=>({matches:false}),
    setInterval:()=>1,clearInterval(){},
    window:{location:{},PTTheme:{apply(){}},PTDialogs:{notice(message,{target,kind}={}){target.textContent=message;target.dataset.kind=kind;},
      confirm:async message=>{confirms.push(message);return confirm?confirm(message):true;}}},
    fetch:async(url,init)=>{calls.push({url,init});
      const data=url==='/api/user_settings'?{settings}:url==='/api/data-location'?{data_dir:'/test'}:{ai_enabled:true,usage:{},sources};
      return {ok:true,json:async()=>data};}};
  vm.createContext(context);vm.runInContext(source,context);
  const posts=()=>calls.filter(c=>c.init?.method==='POST');
  return {context,node,calls,confirms,posts,render:(s=sources)=>vm.runInContext('renderGateway('+JSON.stringify({ai_enabled:true,usage:{},sources:s})+')',context)};
}
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const withSource=(id,patch)=>({...SOURCES,[id]:{...SOURCES[id],...patch}});
function deferred(p){let resolve;const sent=[];p.context.fetch=async(url,init)=>{
  sent.push({url,init});
  if(url==='/api/source-test')return new Promise(done=>resolve=done);
  return {ok:true,json:async()=>({ai_enabled:true,usage:{},sources:SOURCES,settings:{}})};};
  return {sent,complete:data=>resolve({ok:true,json:async()=>data})};}

test('the data source section has one row per source with short controls and no explanatory text',()=>{
  const section=html.slice(html.indexOf('<h2>数据源</h2>'),html.indexOf('<h2>存储与导出</h2>'));
  for(const id of ['sourceArxiv','sourceOpenAlex','sourceCnki','openalexKey','testOpenalexBtn','clearOpenalexKeyBtn','openalexKeyStatus','openalexKeyLink'])
    assert.match(section,new RegExp('id="'+id+'"'),id);
  assert.match(section,new RegExp('<input type="password" id="openalexKey"[^>]*autocomplete="off"'));
  assert.match(section,/期刊与会议论文/);assert.match(section,/<label for="sourceCnki">知网<\/label>/);
  assert.doesNotMatch(section,/sourceBaidu|百度|baiduScholarKey/);         // neither Baidu interface is offered (owner, 2026-10-26: 知网 replaces the Baidu search)
  assert.equal((section.match(/type="password"/g)||[]).length,1);          // OpenAlex is the only source key field left
  assert.equal((section.match(/>\s*测试\s*</g)||[]).length,1);
  assert.doesNotMatch(section,/<small|<p[ >]|readonly-note/);              // no paragraphs under the rows
  assert.doesNotMatch(html,/value="bce-v3|ALTAK/);
});
test('the page has no leftover Baidu element, and a stored Baidu value is neither shown nor sent back',async()=>{
  assert.doesNotMatch(html,/sourceBaiduScholar|sourceBaiduWeb|baiduScholarKey|baiduConfirmed|baiduScholarConfirmed/);
  const p=page({settings:{sourceBaiduScholar:true,sourceBaiduWeb:true,baiduScholarConfirmed:true,recommendCount:7}});
  await vm.runInContext('loadSettings()',p.context);
  await vm.runInContext('saveSettings()',p.context);
  const saved=JSON.parse(p.posts().filter(c=>c.url==='/api/user_settings').pop().init.body).settings;
  for(const k of ['sourceBaiduScholar','sourceBaiduWeb','baiduScholarConfirmed'])assert.equal(k in saved,false,k);   // the next save drops the old values; the server ignored them anyway
  assert.equal(saved.recommendCount,7);
});
test('status words: needs key, configured, invalid key, quota used up',()=>{
  const p=page(),oa=()=>p.node('#openalexKeyStatus').textContent;
  p.render();assert.equal(oa(),'未配置');
  p.render(withSource('openalex',{configured:true}));assert.equal(oa(),'已配置');
  p.render(withSource('openalex',{configured:true,status_kind:'ok'}));assert.equal(oa(),'已配置');
  p.render(withSource('openalex',{configured:true,status_kind:'auth_required'}));assert.equal(oa(),'密钥无效');
  p.render(withSource('openalex',{configured:true,status_kind:'quota_exhausted'}));assert.equal(oa(),'今日额度已用完');
  p.render(withSource('openalex',{configured:true,used_today:40,daily_cap:40}));assert.equal(oa(),'今日额度已用完');
  p.render(withSource('openalex',{configured:true,used_today:39,daily_cap:40}));assert.equal(oa(),'已配置');
});
test('the get-key link comes from the source and the clear button only shows while a key is configured',()=>{
  const p=page();p.render();
  assert.equal(p.node('#openalexKeyLink').href,SOURCES.openalex.key_url);
  assert.equal(p.node('#clearOpenalexKeyBtn').hidden,true);
  p.render(withSource('openalex',{configured:true}));assert.equal(p.node('#clearOpenalexKeyBtn').hidden,false);
});
test('the test button sends the typed key once, saves nothing and shows one word',async()=>{
  const p=page(),d=deferred(p);p.node('#openalexKey').value='  '+KEY+' ';
  const pending=p.node('#testOpenalexBtn').onclick();await turn();
  assert.equal(p.node('#testOpenalexBtn').disabled,true);await p.node('#testOpenalexBtn').onclick();     // a second click does nothing
  assert.equal(d.sent.filter(c=>c.url==='/api/source-test').length,1);
  assert.deepEqual(JSON.parse(d.sent[0].init.body),{id:'openalex',api_key:KEY});
  assert.equal(p.node('#openalexKeyStatus').textContent,'测试中…');
  d.complete({ok:true,kind:'ok',reason:'anything the server says is not shown'});await pending;
  assert.equal(p.node('#openalexKeyStatus').textContent,'可用');assert.equal(p.node('#openalexKeyStatus').dataset.kind,'success');
  assert.equal(p.node('#testOpenalexBtn').disabled,false);
  assert.equal(d.sent.some(c=>c.init?.method==='POST'&&c.url!=='/api/source-test'),false);        // nothing saved
  assert.equal(p.node('#openalexKey').value,'  '+KEY+' ');                                       // the field is left as typed
});
test('an empty field tests the saved key: the request carries only the id',async()=>{
  const p=page(),d=deferred(p);const pending=p.node('#testOpenalexBtn').onclick();await turn();
  assert.deepEqual(JSON.parse(d.sent[0].init.body),{id:'openalex'});
  d.complete({ok:false,kind:'auth_required'});await pending;
  assert.equal(p.node('#openalexKeyStatus').textContent,'密钥无效');assert.equal(p.node('#openalexKeyStatus').dataset.kind,'error');
});
test('every failure kind shows one short word',async()=>{
  const words={auth_required:'密钥无效',quota_exhausted:'今日额度已用完',network_error:'无法连接',unavailable:'服务暂不可用',bad_response:'返回无法识别',invalid_input:'请求无效'};
  for(const [kind,word] of Object.entries(words)){
    const p=page(),d=deferred(p);const pending=p.node('#testOpenalexBtn').onclick();await turn();
    assert.deepEqual(JSON.parse(d.sent[0].init.body),{id:'openalex'});
    d.complete({ok:false,kind,reason:'ignored'});await pending;assert.equal(p.node('#openalexKeyStatus').textContent,word,kind);
  }
  const p=page(),d=deferred(p);const pending=p.node('#testOpenalexBtn').onclick();await turn();
  d.complete({ok:false,kind:KEY});await pending;assert.equal(p.node('#openalexKeyStatus').textContent,'请求失败');   // an unknown kind is never echoed
});
test('a changed key invalidates a late result',async()=>{
  const p=page(),d=deferred(p);p.node('#openalexKey').value='old-key/0000000000';const pending=p.node('#testOpenalexBtn').onclick();await turn();
  p.node('#openalexKey').value='new-key/1111111111';p.node('#openalexKey').oninput();
  d.complete({ok:true,kind:'ok'});await pending;
  assert.notEqual(p.node('#openalexKeyStatus').textContent,'可用');assert.equal(p.node('#openalexKey').value,'new-key/1111111111');
  assert.equal(p.node('#testOpenalexBtn').disabled,false);
});
test('reloading the settings invalidates a pending result and clears the typed key',async()=>{
  const p=page(),d=deferred(p);p.node('#openalexKey').value=KEY;const pending=p.node('#testOpenalexBtn').onclick();await turn();
  p.context.fetch=async(url)=>({ok:true,json:async()=>url==='/api/user_settings'?{settings:{}}:url==='/api/data-location'?{data_dir:'/t'}:{ai_enabled:true,usage:{},sources:SOURCES}});
  await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#openalexKey').value,'');
  d.complete({ok:true,kind:'ok'});await pending;assert.notEqual(p.node('#openalexKeyStatus').textContent,'可用');
});
test('a transport failure never shows the key and frees the button',async()=>{
  const p=page();p.node('#openalexKey').value=KEY;
  p.context.fetch=async()=>{throw new Error('network down while sending '+KEY);};
  await p.node('#testOpenalexBtn').onclick();
  const shown=p.node('#openalexKeyStatus').textContent;assert.equal(shown,'无法连接');assert.ok(!shown.includes(KEY));
  assert.equal(p.node('#testOpenalexBtn').disabled,false);
});
test('clearing sends the source id and refreshes the row',async()=>{
  const p=page();p.node('#openalexKey').value='typed';
  p.context.fetch=async(url,init)=>{p.calls.push({url,init});return {ok:true,json:async()=>({ai_enabled:true,usage:{},sources:SOURCES})};};
  await p.node('#clearOpenalexKeyBtn').onclick();
  assert.deepEqual(JSON.parse(p.calls.at(-1).init.body),{clear_source_key:'openalex'});
  assert.equal(p.node('#openalexKey').value,'');assert.equal(p.node('#openalexKeyStatus').textContent,'未配置');
});
test('saving sends a typed source key as source_key and never a blank one',async()=>{
  const p=page();await vm.runInContext('loadSettings()',p.context);
  p.node('#openalexKey').value=' '+KEY+' ';
  await vm.runInContext('saveSettings()',p.context);
  const keyPosts=p.posts().filter(c=>c.url==='/api/settings'&&/source_key|openalex_key/.test(c.init.body)).map(c=>JSON.parse(c.init.body));
  assert.deepEqual(keyPosts,[{source_key:{id:'openalex',value:KEY}}]);
  const settingsFile=p.posts().filter(c=>c.url==='/api/user_settings').pop().init.body;assert.ok(!settingsFile.includes(KEY));
  const q=page();await vm.runInContext('loadSettings()',q.context);q.node('#openalexKey').value='';
  await vm.runInContext('saveSettings()',q.context);
  assert.equal(q.posts().filter(c=>c.url==='/api/settings'&&/source_key|openalex_key/.test(c.init.body)).length,0);   // a blank field posts no key
});

// ---- the 知网 row replaced the Baidu search row (owner, 2026-10-26): a switch only, off by default, one question on first use.
test('the 知网 switch is off by default, follows the stored setting and is saved only once confirmed',async()=>{
  let p=page();await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceCnki').checked,false);
  p=page({settings:{sourceCnki:true,cnkiConfirmed:true}});await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceCnki').checked,true);
  p=page({settings:{sourceCnki:'yes'}});await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceCnki').checked,false);
  p=page({confirm:()=>false});await vm.runInContext('loadSettings()',p.context);
  p.node('#sourceCnki').checked=true;await p.node('#sourceCnki').onchange();
  assert.equal(p.confirms.length,1);assert.match(p.confirms[0],/知网/);assert.equal(p.node('#sourceCnki').checked,false);
  const q=page({confirm:()=>true});await vm.runInContext('loadSettings()',q.context);
  q.node('#sourceCnki').checked=true;await q.node('#sourceCnki').onchange();
  q.node('#sourceCnki').checked=false;await q.node('#sourceCnki').onchange();
  q.node('#sourceCnki').checked=true;await q.node('#sourceCnki').onchange();                    // off and on again: already confirmed
  assert.equal(q.confirms.length,1);
  await vm.runInContext('saveSettings()',q.context);
  const saved=JSON.parse(q.posts().filter(c=>c.url==='/api/user_settings').pop().init.body).settings;
  assert.equal(saved.sourceCnki,true);assert.equal(saved.cnkiConfirmed,true);
});
// ---- the DeepSeek key line has a get link too (a fixed address: the provider list has one provider).
test('the AI key has a get-key link to the DeepSeek key page, always shown',()=>{
  const link=html.match(/<a id="apiKeyLink"[^>]*>([^<]*)<\/a>/);
  assert.ok(link,'the link exists');
  assert.match(link[0],/href="https:\/\/platform\.deepseek\.com\/api_keys"/);
  assert.match(link[0],/target="_blank"/);assert.match(link[0],/rel="noopener noreferrer"/);
  assert.doesNotMatch(link[0],/hidden/);
  assert.equal(link[1],'获取');                                              // the same word as the source rows
  const ai=html.slice(html.indexOf('<h2>API 配置</h2>'),html.indexOf('<h2>推荐设置</h2>'));
  for(const id of ['apiKey','apiKeyLink','apiKeyStatus','testAiBtn'])assert.ok(ai.includes('id="'+id+'"'),id);   // the link sits in the key row's heading, beside its status
});
