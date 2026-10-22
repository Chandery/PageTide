'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../app/static/settings.html'),'utf8');
const source=html.match(/<script>\s*const \$[\s\S]*?<\/script>/)[0].replace(/^<script>|<\/script>$/g,'').replace(/\n\s*loadSettings\(\);\s*$/,'');
function page(){
  const nodes=new Map(),calls=[],timers=new Map();let now=0,nextTimer=0;
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,textContent:'',disabled:false,dataset:{},setAttribute(){}});return nodes.get(id);};
  class Clock extends Date{static now(){return now;}}
  const context={document:{querySelector:node,documentElement:{dataset:{}}},Date:Clock,
    localStorage:{getItem(){return null;},setItem(){},removeItem(){}},matchMedia:()=>({matches:false}),
    setInterval:fn=>{const id=++nextTimer;timers.set(id,fn);return id;},clearInterval:id=>timers.delete(id),
    window:{location:{},PDHTheme:{apply(){}},PDHDialogs:{notice(message,{target,kind}={}){target.textContent=message;target.dataset.kind=kind;}}},
    fetch:async(url,init)=>{calls.push({url,init});const data=url==='/api/user_settings'?{settings:{}}:url==='/api/data-location'?{data_dir:'/test'}:{ai_enabled:false,usage:{tokens:23,month_tokens:45,usd:'0.003',month_usd:'0.006'}};return {ok:true,json:async()=>data};}};
  vm.createContext(context);vm.runInContext(source,context);
  return {context,node,calls,timers,tick(ms){now+=ms;for(const fn of timers.values())fn();}};
}
const turn=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(p){let resolve;const calls=[];p.context.fetch=async(url,init)=>{calls.push({url,init});if(url==='/api/ai-test')return new Promise(done=>resolve=done);return {ok:true,json:async()=>({usage:{tokens:23,month_tokens:45,usd:'0.003',month_usd:'0.006'},ai_enabled:false})};};return {calls,complete:data=>resolve({ok:true,json:async()=>data})};}

test('settings replace daily/monthly caps with recorded usage and explicit connection test',()=>{
  const p=page();vm.runInContext("renderGateway({ai_enabled:false,limits:{daily_total_tokens:9,monthly_total_tokens:99,daily_usd:7,monthly_usd:70},usage:{tokens:23,month_tokens:45,usd:'0.003',month_usd:'0.006'}})",p.context);
  assert.doesNotMatch(html,/不设用量上限，仍记录消耗/);assert.doesNotMatch(html,/预算上限（|上限变更需要 owner/);
  const usage=p.node('#budgetLimits').textContent;assert.match(usage,/23/);assert.match(usage,/45/);assert.match(usage,/\$0\.003/);assert.match(usage,/\$0\.006/);assert.doesNotMatch(usage,/\/|\$7|\$70/);
  assert.match(html,/id="testAiBtn"/);assert.match(html,/id="aiTestStatus"[^>]*role="status"/);
});
test('actual test handler sends temporary input once without saving it or changing AI toggle',async()=>{
  const p=page(),d=deferred(p);p.node('#apiKey').value=' temporary-test-secret ';p.node('#aiEnabled').checked=false;
  const pending=p.node('#testAiBtn').onclick();await turn();
  assert.equal(p.node('#testAiBtn').disabled,true);await p.node('#testAiBtn').onclick();
  assert.equal(d.calls.filter(x=>x.url==='/api/ai-test').length,1);
  assert.deepEqual(JSON.parse(d.calls[0].init.body),{api_key:'temporary-test-secret'});
  p.tick(4100);assert.equal(p.node('#aiTestStatus').textContent,'正在测试 AI…');
  d.complete({ok:true,provider:'DeepSeek',model:'mock-model',elapsed_ms:4200,usage:{total_tokens:9}});await pending;
  assert.equal(d.calls.some(x=>x.init?.method==='POST'&&x.url!=='/api/ai-test'),false);assert.equal(p.node('#aiEnabled').checked,false);assert.equal(p.node('#apiKey').value,' temporary-test-secret ');
  assert.match(p.node('#aiTestStatus').textContent,/成功.*本次 9 token/);assert.doesNotMatch(p.node('#aiTestStatus').textContent,/mock-model|4\.2/);assert.equal(p.node('#aiTestStatus').dataset.kind,'success');
  assert.equal(p.node('#testAiBtn').disabled,false);assert.equal(p.timers.size,0);
});
test('empty input omits a key so explicit disabled-AI test can use the stored credential',async()=>{
  const p=page(),d=deferred(p);const pending=p.node('#testAiBtn').onclick();await turn();assert.deepEqual(JSON.parse(d.calls[0].init.body),{});
  d.complete({ok:false,reason_code:'no_key',reason:'未配置 DeepSeek 密钥，请先填写密钥。',elapsed_ms:0});await pending;
  assert.match(p.node('#aiTestStatus').textContent,/未配置 DeepSeek 密钥/);assert.equal(p.node('#aiTestStatus').dataset.kind,'error');assert.equal(p.node('#aiEnabled').checked,false);
});
test('specific failures stay beside the key and cannot echo a submitted secret',async()=>{
  const p=page(),d=deferred(p);p.node('#apiKey').value='temporary-secret';const pending=p.node('#testAiBtn').onclick();await turn();
  d.complete({ok:false,reason_code:'authentication',reason:'密钥无效 temporary-secret；HTTP 401',elapsed_ms:120});await pending;
  assert.match(p.node('#aiTestStatus').textContent,/密钥无效.*HTTP 401/);assert.doesNotMatch(p.node('#aiTestStatus').textContent,/temporary-secret/);assert.equal(d.calls.filter(x=>x.url==='/api/ai-test').length,1);
});
test('a changed key invalidates late results while preventing another in-flight model request',async()=>{
  const p=page(),d=deferred(p);p.node('#apiKey').value='old-secret';const pending=p.node('#testAiBtn').onclick();await turn();
  p.node('#apiKey').value='new-secret';p.node('#apiKey').oninput();const status=p.node('#aiTestStatus').textContent;
  assert.equal(p.node('#testAiBtn').disabled,true);await p.node('#testAiBtn').onclick();p.tick(3000);assert.equal(p.node('#aiTestStatus').textContent,status);
  d.complete({ok:true,model:'OLD-KEY-RESULT',elapsed_ms:3000,usage:{total_tokens:1}});await pending;
  assert.equal(d.calls.filter(x=>x.url==='/api/ai-test').length,1);assert.doesNotMatch(p.node('#aiTestStatus').textContent,/OLD-KEY-RESULT|成功/);assert.equal(p.node('#apiKey').value,'new-secret');assert.equal(p.node('#testAiBtn').disabled,false);
});
test('reloading settings invalidates a pending test result',async()=>{
  const p=page(),d=deferred(p);p.node('#apiKey').value='old-secret';const pending=p.node('#testAiBtn').onclick();await turn();
  await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#apiKey').value,'');
  d.complete({ok:true,model:'BEFORE-RESET',usage:{total_tokens:1},elapsed_ms:1});await pending;
  assert.doesNotMatch(p.node('#aiTestStatus').textContent,/BEFORE-RESET|成功/);assert.equal(p.node('#testAiBtn').disabled,false);
});
test('successful connection with unknown usage preserves uncertainty rather than reporting zero tokens',async()=>{
  const p=page(),d=deferred(p);const pending=p.node('#testAiBtn').onclick();await turn();d.complete({ok:true,model:'mock',elapsed_ms:5,usage_unknown:true,usage_reserved:true});await pending;
  assert.match(p.node('#aiTestStatus').textContent,/成功.*用量未确认/);assert.doesNotMatch(p.node('#aiTestStatus').textContent,/本次 0 token/);
});
test('known prompt and completion usage without a total is confirmed and summed in the actual handler',async()=>{
  const p=page(),d=deferred(p);const pending=p.node('#testAiBtn').onclick();await turn();
  d.complete({ok:true,model:'mock',elapsed_ms:5,usage_unknown:false,usage_reserved:false,usage:{prompt_tokens:10,completion_tokens:2}});await pending;
  assert.match(p.node('#aiTestStatus').textContent,/本次 12 token/);assert.doesNotMatch(p.node('#aiTestStatus').textContent,/未确认|已保留/);
});
test('unknown usage without a retained reservation never claims that a reservation exists',async()=>{
  const p=page(),d=deferred(p);const pending=p.node('#testAiBtn').onclick();await turn();
  d.complete({ok:true,model:'mock',elapsed_ms:5,usage_unknown:true,usage_reserved:false,usage:{prompt_tokens:10,completion_tokens:2,total_tokens:12}});await pending;
  assert.match(p.node('#aiTestStatus').textContent,/用量未确认/);assert.doesNotMatch(p.node('#aiTestStatus').textContent,/记录已保留|本次 12 token/);
});
test('transport failure releases the test button without an automatic retry',async()=>{
  const p=page();let attempts=0;p.context.fetch=async()=>{attempts++;throw new Error('network unavailable');};await p.node('#testAiBtn').onclick();
  assert.equal(attempts,1);assert.match(p.node('#aiTestStatus').textContent,/network unavailable/);assert.equal(p.node('#aiTestStatus').dataset.kind,'error');assert.equal(p.node('#testAiBtn').disabled,false);assert.equal(p.timers.size,0);
});
test('a slow usage refresh cannot overwrite a completed AI test with the waiting timer',async()=>{
  const p=page();let finishUsage;p.context.fetch=async(url)=>url==='/api/ai-test'?{ok:true,json:async()=>({ok:true,model:'mock',elapsed_ms:100,usage:{total_tokens:1}})}:new Promise(resolve=>finishUsage=()=>resolve({ok:true,json:async()=>({usage:{tokens:1}})}));
  const pending=p.node('#testAiBtn').onclick();await turn();const completed=p.node('#aiTestStatus').textContent;assert.match(completed,/AI 测试成功/);
  p.tick(2000);assert.equal(p.node('#aiTestStatus').textContent,completed);finishUsage();await pending;
});
test('settings keep pending usage explicitly uncertain even without aggregate ceilings',()=>{
  const p=page();vm.runInContext("renderUsage({usage:{tokens:900,month_tokens:1900,usd:'0.01',month_usd:'0.02',tokens_known:false,pending_reservations:1}})",p.context);
  assert.match(p.node('#budgetLimits').textContent,/含未确认的用量/);assert.doesNotMatch(p.node('#budgetLimits').textContent,/\/|undefined|null/);
  vm.runInContext("renderUsage({usage:{tokens:0,month_tokens:1900,month_tokens_known:false,month_pending_reservations:1}})",p.context);assert.match(p.node('#budgetLimits').textContent,/含未确认的用量/);
});
test('actual home handler renders unlimited runtime and finite developer usage without null crashes',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
  const body=source.slice(source.indexOf('function usageLabel(')===-1?source.indexOf('async function load()'):source.indexOf('function usageLabel('),source.indexOf('// Opening-time upkeep:'));
  for(const usage of [{tokens:20,ceiling:null,dev:false},{tokens:900,ceiling:null,dev:false,tokens_known:false,pending_reservations:1},{tokens:20,ceiling:100,dev:true}]){
    const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{style:{},dataset:{},textContent:'',replaceChildren(...items){this.content=items;}});return nodes.get(id);};
    const context={state:{currentProject:'p'},$:node,document:{getElementById:()=>node('#devbanner'),createElement:()=>({dataset:{}})},api:async url=>url.startsWith('/api/home')?{usage,dev_mode:usage.dev,stats:{},profile:{},cards:[]}:url==='/api/data-location'?{data_dir:'/test'}:{},renderStats(){},renderCards(){},renderProfile(){},renderMaintenance(){},renderRoute(){},renderEligibility(){},console};
    vm.createContext(context);vm.runInContext(source.split('\n').find(line=>line.startsWith('const esc ='))+'\n'+body,context);await context.load();
    const footer=node('#foot').textContent;assert.match(footer,/20|900/);assert.doesNotMatch(footer,/null|undefined/);
    if(usage.ceiling==null)assert.doesNotMatch(footer,/\/ /);else assert.match(footer,/20 \/ 100/);
    if(usage.tokens_known===false)assert.match(footer,/含未确认的用量/);
  }
});
