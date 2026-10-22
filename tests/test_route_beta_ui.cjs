'use strict';
// Learning-map mode (beta) is a Settings switch, off by default. These tests run the real page code with the flag
// the server injects (window.PDH_ROUTE_BETA) and check that the learning-map parts disappear or stay.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,'../app/static',name),'utf8');

function loadContext(flag){
  const sandbox={window:flag===undefined?{}:{PDH_ROUTE_BETA:flag}};
  sandbox.module={exports:{}};
  vm.createContext(sandbox);
  vm.runInContext(read('paper-context.js'),sandbox);
  return sandbox.window.PDHPaperContext||sandbox.module.exports;
}
const context={project_id:'p',categories:[{name:'Cat'}],units:[{id:'a',name:'Unit A'}],map_available:true,route_enabled:true,
  saved_in_project:true,recommendation:{kind:'route',name:'Unit A'}};

test('with the beta off the paper detail shows categories and the paper graph but no learning-map rows',()=>{
  const html=loadContext(false).html(context,'k');
  assert.match(html,/收藏类别/);assert.match(html,/在论文关系图中定位/);
  for(const hidden of ['学习单元','本次推荐用途','在学习图中定位','定位学习单元','重新核验学习匹配','Unit A']) assert.ok(!html.includes(hidden),hidden);
});
test('with the beta on, or no flag at all, the paper detail keeps the learning-map rows',()=>{
  for(const flag of [true,undefined]){
    const html=loadContext(flag).html(context,'k');
    for(const shown of ['学习单元','Unit A','定位学习单元','在学习图中定位']) assert.ok(html.includes(shown),`${flag}:${shown}`);
    assert.ok(!html.includes('本次推荐用途'),`${flag}: the recommendation-use row is gone`);
  }
});

function settingsPage(stored){
  const source=read('settings.html').match(/<script>\s*const \$[\s\S]*?<\/script>/)[0].replace(/^<script>|<\/script>$/g,'');
  const nodes=new Map(),calls=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,textContent:'',disabled:false,dataset:{},setAttribute(){}});return nodes.get(id);};
  const context={document:{querySelector:node,documentElement:{dataset:{}}},localStorage:{getItem(){return null;},setItem(){},removeItem(){}},matchMedia(){return {matches:false};},
    window:{location:{},PDHTheme:{apply(){}},PDHSaveFile:async()=>({})},alert(){},confirm(){return true;},
    fetch:async(url,init)=>{calls.push({url,init});
      if(url==='/api/user_settings'&&!init)return {ok:true,json:async()=>({settings:stored})};
      return {ok:true,json:async()=>({status:'saved'})};}};
  vm.createContext(context);vm.runInContext(source,context);
  return {node,calls,context};
}
test('the settings page shows the beta switch off by default, and the hotspot defaults',async()=>{
  const p=settingsPage({});await vm.runInContext('loadSettings()',p.context);
  assert.equal(p.node('#routeBeta').checked,false);
  assert.equal(String(p.node('#newPaperBoost').value),'0.5');
  assert.equal(p.node('#timePreference').value,'all');
});
test('the beta switch is saved with the other settings, and turning it on round-trips',async()=>{
  const p=settingsPage({routeBeta:true});await vm.runInContext('loadSettings()',p.context);
  assert.equal(p.node('#routeBeta').checked,true);
  await vm.runInContext('saveSettings()',p.context);
  let sent=p.calls.filter(x=>x.url==='/api/user_settings'&&x.init?.method==='POST').pop();
  assert.equal(JSON.parse(sent.init.body).settings.routeBeta,true);
  p.node('#routeBeta').checked=false;p.node('#saveBtn').disabled=false;   // a successful save leaves the page, so the button stays disabled
  await vm.runInContext('saveSettings()',p.context);
  sent=p.calls.filter(x=>x.url==='/api/user_settings'&&x.init?.method==='POST').pop();
  assert.equal(JSON.parse(sent.init.body).settings.routeBeta,false);
});

test('every learning-map entry point is marked so the page hides it while the beta is off',()=>{
  const creation=read('project_creation.html');
  assert.match(creation,/data-role="mapBlock" data-route-beta/);
  assert.match(creation,/data-role="pathBlock" data-route-beta/);
  assert.match(read('project.html'),/<div class="map-actions" data-route-beta><a[^>]*data-role="routeLink"/);
  // the creation page sentences that name the map have a map-free twin shown instead
  assert.equal((creation.match(/data-route-beta-off/g)||[]).length,3);
});
test('with the beta off a new project is created without a map and leaving the page is not "unsaved"',()=>{
  const source=read('project-creation.js');
  const start=source.indexOf('const map = {'),literal=source.slice(start,source.indexOf('};',start)+2);
  const quit=source.slice(source.indexOf('quitState:'),source.indexOf('\n',source.indexOf('quitState:')));
  for(const [flag,discarded] of [[false,true],[true,false],[undefined,false]]){
    const context=vm.createContext({window:flag===undefined?{}:{PDH_ROUTE_BETA:flag}});
    vm.runInContext(literal+';globalThis.map=map;',context);
    assert.equal(context.map.discarded,discarded,`flag ${flag}`);
    // the page-leave check must not treat the automatic "no map" as an unsaved edit
    Object.assign(context,{searching:false,busy:false,mapConfirming:false,keywords:0,selected:{size:0}});
    const dirty=vm.runInContext(`(${quit.replace(/^quitState:/,'').replace(/,$/,'')})()`,context).dirty;
    assert.equal(dirty,false,`dirty with flag ${flag}`);
  }
});
test('the library graph and the learning-map page honour the switch',()=>{
  assert.match(read('organization.js'),/const routeAvailable = \(\) => window\.PDH_ROUTE_BETA !== false && /);
  assert.match(read('route-page.js'),/if \(window\.PDH_ROUTE_BETA === false\) \{[\s\S]*?return;\s*\}/);
});
test('the home page replaces the learning-map panel with the hotspot-mode line when the beta is off',()=>{
  const source=read('index.html');
  assert.match(source,/if \(window\.PDH_ROUTE_BETA === false\) \{[\s\S]*?热点模式[\s\S]*?return;/);
});
