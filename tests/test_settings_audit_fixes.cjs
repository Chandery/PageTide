'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/static/settings.html'),'utf8').match(/<script>\s*const \$[\s\S]*?<\/script>/)[0].replace(/^<script>|<\/script>$/g,'');
function page(){
 const nodes=new Map(), calls=[],alerts=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:true,textContent:'',disabled:false,dataset:{},setAttribute(){}});return nodes.get(id);};
 const context={document:{querySelector:node,documentElement:{dataset:{}}},localStorage:{getItem(){return null;},setItem(){},removeItem(){}},matchMedia(){return {matches:false};},window:{location:{},PDHTheme:{apply(){}},PDHSaveFile:async()=>({status:'saved',path:'/test/export.json'}),PDHDialogs:{confirm:async()=>true,notice(message,options={}){alerts.push(message);if(options.target){options.target.textContent=message;options.target.dataset.kind=options.kind;}}}},alert:x=>alerts.push(x),confirm:()=>true,fetch:async(url,init)=>{calls.push({url,init});const data=url==='/api/user_settings'?{settings:{}}:url==='/api/data-location'?{data_dir:'/test/data'}:url==='/api/export'?{version:1,tables:{}}:url==='/api/cache'?{removed:['metadata-cache'],preserved:['pdf','fulltext']}:{};return {ok:true,json:async()=>data};}};
 vm.createContext(context);vm.runInContext(source,context);
 return {nodes,node,calls,alerts,context};
}
test('explicit zero boost survives actual settings save handler',async()=>{
 const p=page();await vm.runInContext('loadSettings()',p.context);p.node('#newPaperBoost').value='0';
 await vm.runInContext('saveSettings()',p.context);
 const sent=p.calls.filter(x=>x.url==='/api/user_settings'&&x.init?.method==='POST').pop();
 assert.equal(JSON.parse(sent.init.body).settings.newPaperBoost,0);
});
test('cache failure does not announce success',async()=>{
 const p=page();await vm.runInContext('loadSettings()',p.context);p.context.fetch=async()=>({ok:false,json:async()=>({error:'test error'})});
 await p.node('#clearCacheBtn').onclick();assert.match(p.alerts.pop(),/清理失败/);assert.equal(p.alerts.some(x=>/已清除/.test(x)),false);
});
test('settings show actual data location and export whole snapshot with save receipt',async()=>{
 const p=page();await vm.runInContext('loadSettings()',p.context);assert.equal(p.node('#dataDir').value,'/test/data');
 await p.node('#exportBtn').onclick();assert.equal(p.calls.filter(x=>x.url.startsWith('/api/export')).pop().url,'/api/export');assert.match(p.alerts.pop(),/\/test\/export.json/);
});
test('cold origin theme uses saved backend choice and mode save merges preferences',async()=>{
 const events=[],calls=[],doc={documentElement:{dataset:{}}},storage={getItem(){return null;},setItem(){},removeItem(){}};
 const context={window:{dispatchEvent:e=>events.push(e.detail)},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},document:doc,localStorage:storage,matchMedia:()=>({matches:false,addEventListener(){}}),fetch:async(url,init)=>{calls.push({url,init});return {ok:true,json:async()=>({settings:{theme:'dark'}})};}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../app/static/theme.js'),'utf8'),context);
 await context.window.PDHTheme.ready;assert.equal(doc.documentElement.dataset.mode,'dark');assert.equal(events.at(-1),'dark');
 await context.window.PDHTheme.set('light');assert.equal(doc.documentElement.dataset.mode,'light');assert.equal(events.at(-1),'light');assert.equal(JSON.parse(calls.at(-1).init.body).merge,true);
});

for(const receipt of [{status:'cancelled'},{status:'saved',path:'/chosen/result.json'},{}])test('actual export handler honors receipt '+JSON.stringify(receipt),async()=>{
 const p=page();p.context.window.PDHSaveFile=async()=>receipt;await p.node('#exportBtn').onclick();
 const status=p.node('#exportStatus');assert.equal(p.node('#exportBtn').disabled,false);
 if(receipt.status==='cancelled'){assert.match(status.textContent,/已取消导出/);assert.doesNotMatch(status.textContent,/导出已保存/);}
 else if(receipt.status==='saved')assert.match(status.textContent,/\/chosen\/result.json/);
 else{assert.match(status.textContent,/导出失败/);assert.equal(status.dataset.kind,'error');}
});
test('actual export prevents overlapping save pickers and reports thrown save error',async()=>{
 const p=page();let complete,count=0;p.context.window.PDHSaveFile=()=>{count++;return new Promise(resolve=>complete=resolve);};
 const run=p.node('#exportBtn').onclick();await new Promise(resolve=>setImmediate(resolve));
 await p.node('#exportBtn').onclick();assert.equal(count,1);complete({status:'cancelled'});await run;
 p.context.window.PDHSaveFile=async()=>{throw new Error('write denied');};await p.node('#exportBtn').onclick();assert.match(p.node('#exportStatus').textContent,/write denied/);assert.equal(p.node('#exportBtn').disabled,false);
});
test('actual cache cancellation does not clear data and releases button',async()=>{
 const p=page();p.context.window.PDHDialogs.confirm=async()=>false;await p.node('#clearCacheBtn').onclick();assert.equal(p.calls.some(x=>x.url==='/api/cache'),false);assert.equal(p.node('#clearCacheBtn').disabled,false);
});
