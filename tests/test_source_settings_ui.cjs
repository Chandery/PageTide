'use strict';
// Settings page: one row per data source (switch, key, status word, test, clear, get). Whitespace first: short words only.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../app/static/settings.html'),'utf8');
const source=html.match(/<script>\s*const \$[\s\S]*?<\/script>/)[0].replace(/^<script>|<\/script>$/g,'').replace(/\n\s*loadSettings\(\);\s*$/,'');
const KEY='bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000';
const SOURCES={
  openalex:{needs_key:false,key:'optional',configured:false,status_kind:null,used_today:null,daily_cap:null,key_url:'https://help.openalex.org/api-reference/authentication'},
  baidu_scholar:{needs_key:true,key:'required',configured:false,status_kind:null,used_today:0,daily_cap:40,key_url:'https://console.bce.baidu.com/qianfan/ais/console/apiKey'},
  baidu_web:{needs_key:true,key:'required',configured:false,status_kind:null,used_today:0,daily_cap:40,key_url:'https://console.bce.baidu.com/qianfan/ais/console/apiKey'},
};
function page({sources=SOURCES,settings={},confirm}={}){
  const nodes=new Map(),calls=[],confirms=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,textContent:'',disabled:false,hidden:false,href:'',dataset:{},setAttribute(){}});return nodes.get(id);};
  const context={document:{querySelector:node,documentElement:{dataset:{}}},
    localStorage:{getItem(){return null;},setItem(){},removeItem(){}},matchMedia:()=>({matches:false}),
    setInterval:()=>1,clearInterval(){},
    window:{location:{},PDHTheme:{apply(){}},PDHDialogs:{notice(message,{target,kind}={}){target.textContent=message;target.dataset.kind=kind;},
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
  for(const id of ['sourceArxiv','sourceOpenAlex','sourceBaiduScholar','openalexKey','baiduScholarKey','testOpenalexBtn','testBaiduScholarBtn',
    'clearOpenalexKeyBtn','clearBaiduScholarKeyBtn','openalexKeyStatus','baiduScholarKeyStatus','openalexKeyLink','baiduScholarKeyLink'])
    assert.match(section,new RegExp('id="'+id+'"'),id);
  for(const id of ['openalexKey','baiduScholarKey'])assert.match(section,new RegExp('<input type="password" id="'+id+'"[^>]*autocomplete="off"'));
  assert.match(section,/百度学术/);assert.match(section,/期刊与会议论文/);
  assert.doesNotMatch(section,/<small|<p[ >]|readonly-note/);              // no paragraphs under the rows
  assert.doesNotMatch(html,/value="bce-v3|ALTAK/);
});
test('the Baidu switch is off by default and follows the stored setting',async()=>{
  let p=page();await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceBaiduScholar').checked,false);
  p=page({settings:{sourceBaiduScholar:true}});await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceBaiduScholar').checked,true);
  p=page({settings:{sourceBaiduScholar:'yes'}});await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceBaiduScholar').checked,false);
});
test('status words: needs key, configured, invalid key, quota used up',()=>{
  const p=page(),word=()=>p.node('#baiduScholarKeyStatus').textContent;
  p.render();assert.equal(word(),'需要密钥');
  p.render(withSource('baidu_web',{configured:true}));assert.equal(word(),'已配置');
  p.render(withSource('baidu_web',{configured:true,status_kind:'ok'}));assert.equal(word(),'已配置');
  p.render(withSource('baidu_web',{configured:true,status_kind:'auth_required'}));assert.equal(word(),'密钥无效');
  p.render(withSource('baidu_web',{configured:true,status_kind:'quota_exhausted'}));assert.equal(word(),'今日额度已用完');
  p.render(withSource('baidu_web',{configured:true,used_today:40}));assert.equal(word(),'今日额度已用完');
  p.render(withSource('baidu_web',{configured:true,used_today:39}));assert.equal(word(),'已配置');
  p.render({...withSource('baidu_web',{configured:true}),baidu_scholar:{...SOURCES.baidu_scholar,configured:true,status_kind:'auth_required',used_today:40}});
  assert.equal(word(),'已配置');                                  // the key line shows the web search's state, not the Baidu Scholar tool's
  const oa=()=>p.node('#openalexKeyStatus').textContent;
  p.render();assert.equal(oa(),'未配置');
  p.render(withSource('openalex',{configured:true}));assert.equal(oa(),'已配置');
  p.render(withSource('openalex',{configured:true,status_kind:'auth_required'}));assert.equal(oa(),'密钥无效');
});
test('the get-key link comes from the source and the clear button only shows while a key is configured',()=>{
  const p=page();p.render();
  assert.equal(p.node('#baiduScholarKeyLink').href,SOURCES.baidu_scholar.key_url);
  assert.equal(p.node('#openalexKeyLink').href,SOURCES.openalex.key_url);
  assert.equal(p.node('#clearBaiduScholarKeyBtn').hidden,true);
  p.render(withSource('baidu_web',{configured:true}));assert.equal(p.node('#clearBaiduScholarKeyBtn').hidden,false);
});
test('the test button sends the typed key once, saves nothing and shows one word',async()=>{
  const p=page(),d=deferred(p);p.node('#baiduScholarKey').value='  '+KEY+' ';
  const pending=p.node('#testBaiduScholarBtn').onclick();await turn();
  assert.equal(p.node('#testBaiduScholarBtn').disabled,true);await p.node('#testBaiduScholarBtn').onclick();     // a second click does nothing
  assert.equal(d.sent.filter(c=>c.url==='/api/source-test').length,1);
  assert.deepEqual(JSON.parse(d.sent[0].init.body),{id:'baidu_web',api_key:KEY});       // the key line tests the key with the web search
  assert.equal(p.node('#baiduScholarKeyStatus').textContent,'测试中…');
  d.complete({ok:true,kind:'ok',reason:'anything the server says is not shown'});await pending;
  assert.equal(p.node('#baiduScholarKeyStatus').textContent,'可用');assert.equal(p.node('#baiduScholarKeyStatus').dataset.kind,'success');
  assert.equal(p.node('#testBaiduScholarBtn').disabled,false);
  assert.equal(d.sent.some(c=>c.init?.method==='POST'&&c.url!=='/api/source-test'),false);        // nothing saved
  assert.equal(p.node('#baiduScholarKey').value,'  '+KEY+' ');                                    // the field is left as typed
});
test('an empty field tests the saved key: the request carries only the id',async()=>{
  const p=page(),d=deferred(p);const pending=p.node('#testBaiduScholarBtn').onclick();await turn();
  assert.deepEqual(JSON.parse(d.sent[0].init.body),{id:'baidu_web'});
  d.complete({ok:false,kind:'auth_required'});await pending;
  assert.equal(p.node('#baiduScholarKeyStatus').textContent,'密钥无效');assert.equal(p.node('#baiduScholarKeyStatus').dataset.kind,'error');
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
  const p=page(),d=deferred(p);p.node('#baiduScholarKey').value='old-key/0000000000';const pending=p.node('#testBaiduScholarBtn').onclick();await turn();
  p.node('#baiduScholarKey').value='new-key/1111111111';p.node('#baiduScholarKey').oninput();
  d.complete({ok:true,kind:'ok'});await pending;
  assert.notEqual(p.node('#baiduScholarKeyStatus').textContent,'可用');assert.equal(p.node('#baiduScholarKey').value,'new-key/1111111111');
  assert.equal(p.node('#testBaiduScholarBtn').disabled,false);
});
test('reloading the settings invalidates a pending result and clears the typed key',async()=>{
  const p=page(),d=deferred(p);p.node('#baiduScholarKey').value=KEY;const pending=p.node('#testBaiduScholarBtn').onclick();await turn();
  p.context.fetch=async(url)=>({ok:true,json:async()=>url==='/api/user_settings'?{settings:{}}:url==='/api/data-location'?{data_dir:'/t'}:{ai_enabled:true,usage:{},sources:SOURCES}});
  await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#baiduScholarKey').value,'');
  d.complete({ok:true,kind:'ok'});await pending;assert.notEqual(p.node('#baiduScholarKeyStatus').textContent,'可用');
});
test('a transport failure never shows the key and frees the button',async()=>{
  const p=page();p.node('#baiduScholarKey').value=KEY;
  p.context.fetch=async()=>{throw new Error('network down while sending '+KEY);};
  await p.node('#testBaiduScholarBtn').onclick();
  const shown=p.node('#baiduScholarKeyStatus').textContent;assert.equal(shown,'无法连接');assert.ok(!shown.includes(KEY));
  assert.equal(p.node('#testBaiduScholarBtn').disabled,false);
});
test('the two rows test independently',async()=>{
  const p=page(),d=deferred(p);const a=p.node('#testOpenalexBtn').onclick();await turn();
  assert.equal(p.node('#testBaiduScholarBtn').disabled,false);
  d.complete({ok:true,kind:'ok'});await a;assert.equal(p.node('#openalexKeyStatus').textContent,'可用');assert.equal(p.node('#baiduScholarKeyStatus').textContent,'');
});
test('clearing sends the source id and refreshes the row',async()=>{
  const p=page();p.node('#baiduScholarKey').value='typed';
  p.context.fetch=async(url,init)=>{p.calls.push({url,init});return {ok:true,json:async()=>({ai_enabled:true,usage:{},sources:SOURCES})};};
  await p.node('#clearBaiduScholarKeyBtn').onclick();
  assert.deepEqual(JSON.parse(p.calls.at(-1).init.body),{clear_source_key:'baidu_scholar'});
  assert.equal(p.node('#baiduScholarKey').value,'');assert.equal(p.node('#baiduScholarKeyStatus').textContent,'需要密钥');
});
test('switching Baidu on asks once, declining leaves it off, the answer is kept for later',async()=>{
  const p=page({confirm:()=>false});await vm.runInContext('loadSettings()',p.context);
  p.node('#sourceBaiduScholar').checked=true;await p.node('#sourceBaiduScholar').onchange();
  assert.equal(p.confirms.length,1);assert.match(p.confirms[0],/百度学术/);assert.match(p.confirms[0],/中文/);
  assert.equal(p.node('#sourceBaiduScholar').checked,false);
  const q=page({confirm:()=>true});await vm.runInContext('loadSettings()',q.context);
  q.node('#sourceBaiduScholar').checked=true;await q.node('#sourceBaiduScholar').onchange();
  assert.equal(q.node('#sourceBaiduScholar').checked,true);
  q.node('#sourceBaiduScholar').checked=false;await q.node('#sourceBaiduScholar').onchange();
  q.node('#sourceBaiduScholar').checked=true;await q.node('#sourceBaiduScholar').onchange();
  assert.equal(q.confirms.length,1);                                                        // switching off and on again does not ask again
  await vm.runInContext('saveSettings()',q.context);
  const saved=JSON.parse(q.posts().filter(c=>c.url==='/api/user_settings').pop().init.body).settings;
  assert.equal(saved.sourceBaiduScholar,true);assert.equal(saved.baiduScholarConfirmed,true);
});
test('a stored confirmation is not asked for again and switching off never asks',async()=>{
  const p=page({settings:{baiduScholarConfirmed:true}});await vm.runInContext('loadSettings()',p.context);
  p.node('#sourceBaiduScholar').checked=true;await p.node('#sourceBaiduScholar').onchange();
  p.node('#sourceBaiduScholar').checked=false;await p.node('#sourceBaiduScholar').onchange();
  assert.equal(p.confirms.length,0);
  await vm.runInContext('saveSettings()',p.context);
  const saved=JSON.parse(p.posts().filter(c=>c.url==='/api/user_settings').pop().init.body).settings;
  assert.equal(saved.sourceBaiduScholar,false);assert.equal(saved.baiduScholarConfirmed,true);
});
test('an unconfirmed switch stays off in the saved settings',async()=>{
  const p=page();await vm.runInContext('loadSettings()',p.context);
  await vm.runInContext('saveSettings()',p.context);
  const saved=JSON.parse(p.posts().filter(c=>c.url==='/api/user_settings').pop().init.body).settings;
  assert.equal(saved.sourceBaiduScholar,false);assert.notEqual(saved.baiduScholarConfirmed,true);
});
test('saving sends a typed source key as source_key and never a blank one',async()=>{
  const p=page();await vm.runInContext('loadSettings()',p.context);
  p.node('#baiduScholarKey').value=' '+KEY+' ';p.node('#openalexKey').value='';
  await vm.runInContext('saveSettings()',p.context);
  const keyPosts=p.posts().filter(c=>c.url==='/api/settings'&&/source_key|openalex_key/.test(c.init.body)).map(c=>JSON.parse(c.init.body));
  assert.deepEqual(keyPosts,[{source_key:{id:'baidu_scholar',value:KEY}}]);
  const settingsFile=p.posts().filter(c=>c.url==='/api/user_settings').pop().init.body;assert.ok(!settingsFile.includes(KEY));
});

// ---- the second Baidu row: Baidu AI Search restricted to xueshu.baidu.com. It shares the Qianfan key of the Baidu Scholar row.
test('the web row is only a switch: no status word, no test button, no key field of its own',()=>{
  const section=html.slice(html.indexOf('<h2>数据源</h2>'),html.indexOf('<h2>存储与导出</h2>'));
  assert.match(section,/id="sourceBaiduWeb"/);
  assert.match(section,/百度搜索/);
  assert.doesNotMatch(section,/id="baiduWebStatus"|id="testBaiduWebBtn"|baiduWebKey|clearBaiduWeb|baiduWebKeyLink/);
  assert.equal((section.match(/>\s*测试\s*</g)||[]).length,2);                                  // OpenAlex and the Baidu key line: one test each
  assert.equal((section.match(/type="password"/g)||[]).length,2);                              // OpenAlex and Baidu: still two key fields
  assert.doesNotMatch(section,/<small|<p[ >]|readonly-note/);
  assert.ok(section.indexOf('id="sourceBaiduWeb"')>section.indexOf('id="sourceBaiduScholar"'));
});
test('the web switch is off by default and follows the stored setting',async()=>{
  let p=page();await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceBaiduWeb').checked,false);
  p=page({settings:{sourceBaiduWeb:true}});await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceBaiduWeb').checked,true);
  p=page({settings:{sourceBaiduWeb:'yes'}});await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceBaiduWeb').checked,false);
  p=page({settings:{sourceBaiduScholar:true}});await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#sourceBaiduWeb').checked,false);   // the other switch is not this one
});
test('the clear button and the get link sit on the key line',()=>{
  const p=page();p.render({...SOURCES,baidu_web:{...SOURCES.baidu_web,configured:true}});
  assert.equal(p.node('#clearBaiduScholarKeyBtn').hidden,false);assert.equal(p.node('#baiduScholarKeyLink').href,SOURCES.baidu_web.key_url);
});
test('the key line test sends only the id when the field is empty, shows one word and records nothing else',async()=>{
  const p=page(),d=deferred(p);const pending=p.node('#testBaiduScholarBtn').onclick();await turn();
  assert.deepEqual(JSON.parse(d.sent[0].init.body),{id:'baidu_web'});
  assert.equal(p.node('#baiduScholarKeyStatus').textContent,'测试中…');
  d.complete({ok:false,kind:'unavailable'});await pending;
  assert.equal(p.node('#baiduScholarKeyStatus').textContent,'服务暂不可用');assert.equal(p.node('#baiduScholarKeyStatus').dataset.kind,'error');
  assert.equal(p.node('#testBaiduScholarBtn').disabled,false);
});
test('every word the key line test can show, from the web search kinds',async()=>{
  const words={ok:'可用',auth_required:'密钥无效',quota_exhausted:'今日额度已用完',network_error:'无法连接',unavailable:'服务暂不可用'};
  for(const [kind,word] of Object.entries(words)){
    const p=page(),d=deferred(p);const pending=p.node('#testBaiduScholarBtn').onclick();await turn();
    d.complete({ok:kind==='ok',kind});await pending;assert.equal(p.node('#baiduScholarKeyStatus').textContent,word,kind);
  }
});
test('switching the web search on asks once, declining leaves it off, and the answer is the same one Baidu Scholar uses',async()=>{
  const p=page({confirm:()=>false});await vm.runInContext('loadSettings()',p.context);
  p.node('#sourceBaiduWeb').checked=true;await p.node('#sourceBaiduWeb').onchange();
  assert.equal(p.confirms.length,1);assert.match(p.confirms[0],/百度学术/);assert.match(p.confirms[0],/中文/);
  assert.equal(p.node('#sourceBaiduWeb').checked,false);
  const q=page({confirm:()=>true});await vm.runInContext('loadSettings()',q.context);
  q.node('#sourceBaiduWeb').checked=true;await q.node('#sourceBaiduWeb').onchange();
  assert.equal(q.node('#sourceBaiduWeb').checked,true);
  q.node('#sourceBaiduScholar').checked=true;await q.node('#sourceBaiduScholar').onchange();         // already confirmed through the web row
  assert.equal(q.confirms.length,1);
  await vm.runInContext('saveSettings()',q.context);
  const saved=JSON.parse(q.posts().filter(c=>c.url==='/api/user_settings').pop().init.body).settings;
  assert.equal(saved.sourceBaiduWeb,true);assert.equal(saved.sourceBaiduScholar,true);assert.equal(saved.baiduScholarConfirmed,true);
});
test('a stored confirmation is not asked for again by the web switch and switching off never asks',async()=>{
  const p=page({settings:{baiduScholarConfirmed:true}});await vm.runInContext('loadSettings()',p.context);
  p.node('#sourceBaiduWeb').checked=true;await p.node('#sourceBaiduWeb').onchange();
  p.node('#sourceBaiduWeb').checked=false;await p.node('#sourceBaiduWeb').onchange();
  assert.equal(p.confirms.length,0);
});
test('an unconfirmed web switch stays off in the saved settings',async()=>{
  const p=page({confirm:()=>false});await vm.runInContext('loadSettings()',p.context);
  p.node('#sourceBaiduWeb').checked=true;                                                                   // ticked without the change handler
  await vm.runInContext('saveSettings()',p.context);
  const saved=JSON.parse(p.posts().filter(c=>c.url==='/api/user_settings').pop().init.body).settings;
  assert.equal(saved.sourceBaiduWeb,false);
});
test('saving sends the shared key once, as the scholar key, and never a second time for the web row',async()=>{
  const p=page({settings:{baiduScholarConfirmed:true}});await vm.runInContext('loadSettings()',p.context);
  p.node('#baiduScholarKey').value=' '+KEY+' ';p.node('#sourceBaiduWeb').checked=true;
  await vm.runInContext('saveSettings()',p.context);
  const keyPosts=p.posts().filter(c=>c.url==='/api/settings'&&/source_key|openalex_key/.test(c.init.body)).map(c=>JSON.parse(c.init.body));
  assert.deepEqual(keyPosts,[{source_key:{id:'baidu_scholar',value:KEY}}]);
  const saved=JSON.parse(p.posts().filter(c=>c.url==='/api/user_settings').pop().init.body).settings;
  assert.equal(saved.sourceBaiduWeb,true);assert.ok(!JSON.stringify(saved).includes(KEY));
});
// ---- one Baidu block: a heading with the single key line, and the two switches under it.
test('the Baidu block is one heading, one key line, and the two switches under it',()=>{
  const section=html.slice(html.indexOf('<h2>数据源</h2>'),html.indexOf('<h2>存储与导出</h2>'));
  const at=id=>section.indexOf('id="'+id+'"');
  const heading=section.indexOf('class="source-name"');
  assert.ok(heading>0,'a heading element for the block');
  assert.match(section.slice(heading,heading+80),/>百度学术</);
  const order=['baiduScholarKey','baiduScholarKeyStatus','testBaiduScholarBtn','clearBaiduScholarKeyBtn','baiduScholarKeyLink','sourceBaiduScholar','sourceBaiduWeb'].map(at);
  assert.ok(order.every(i=>i>0),'every id is still there');
  assert.equal(at('baiduWebStatus'),-1);assert.equal(at('testBaiduWebBtn'),-1);          // the switches are only checkboxes
  assert.ok(heading<order[0]);
  assert.deepEqual([...order].sort((a,b)=>a-b),order,'key line first, then the scholar switch, then the web switch');
  assert.match(section,/百度学术接口/);                                    // the switch of the Baidu Scholar tool
  assert.match(section,/<\/label>/);
  assert.match(section.slice(at('sourceBaiduScholar'),at('sourceBaiduScholar')+120),/百度学术接口/);
  assert.match(section.slice(at('sourceBaiduWeb'),at('sourceBaiduWeb')+120),/百度搜索/);
  assert.doesNotMatch(section,/百度学术（百度搜索）/);
  assert.equal((section.match(/id="baiduScholarKey"/g)||[]).length,1);   // one key field for the block
  assert.doesNotMatch(section,/<small|<p[ >]|readonly-note/);
});
test('the block keeps the ids and the behaviour the rest of the page relies on',async()=>{
  const p=page({confirm:()=>true,settings:{sourceBaiduWeb:true,baiduScholarConfirmed:true}});await vm.runInContext('loadSettings()',p.context);
  assert.equal(p.node('#sourceBaiduWeb').checked,true);assert.equal(p.node('#sourceBaiduScholar').checked,false);
  p.render(withSource('baidu_web',{configured:true}));assert.equal(p.node('#baiduScholarKeyStatus').textContent,'已配置');      // the key line shows the key's state; the switches show nothing
});
