'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
const helpers=html.slice(html.indexOf('function dailyButtonText'),html.indexOf('function renderRoute'));
const generate=html.slice(html.indexOf('async function generate()'),html.indexOf('async function autoTriage()'));
function context(response={}) {
 const button={},notices=[];
 const c=vm.createContext({state:{currentProject:'p',route:{enabled:true,goal_status:'completed'},cards:[]},
  $:id=>id==='#autoAi'?{checked:true}:button,api:async()=>response,renderEligibility:()=>{},renderCards:()=>{},renderRoute:()=>{},
  toast:(...args)=>notices.push(args),autoTriage:async()=>{c.triages++;},triages:0});
 vm.runInContext(helpers+generate,c);return {c,button,notices};
}
test('fixed learning quota, completed daily cap and actual discovery counts are visible',()=>{
 const {c}=context();
 assert.match(c.exploreLine({goal_status:'learning'}),/三篇路径、一篇探索、一篇新进展/);
 assert.match(c.exploreLine({goal_status:'completed'}),/每日本地最多一篇/);
 assert.doesNotMatch(c.exploreLine({goal_status:'completed',progress_verification_deferred:true}),/目标已完成/);
 c.state.route.progress_verification_deferred=true;assert.equal(c.dailyButtonText(),'核验后生成推荐');
 c.state.cards=[{route:{kind:'explore_new'}},{route:{kind:'watch'}},{route:{kind:'route'}}];
 assert.match(c.exploreLine({goal_status:'learning'}),/探索 1 篇、新进展 1 篇/);
 c.state.cards=[{route:{kind:'route'}}];
 assert.match(c.exploreLine({goal_status:'learning'}),/前置缺口或新分支/);
 assert.doesNotMatch(c.exploreLine({goal_status:'learning'}),/探索约占/);
});
test('reopening completed daily batch preserves summary and does not trigger another AI triage',async()=>{
 const {c,button,notices}=context({cards:[{key:'x',summary:{text:'saved'}}],reused:true,reason:'每日最多一篇'});
 await c.generate();assert.equal(c.triages,0);assert.equal(c.state.cards[0].summary.text,'saved');
 assert.equal(notices.at(-1)[0],'每日最多一篇');assert.equal(button.textContent,'生成今日发现');assert.equal(button.disabled,false);
});
test('short batches show the shortage reason and empty batches preserve existing cards',async()=>{
 const {c,notices}=context({cards:[{key:'x'}],shortfall:{reason:'路径不足'}});
 await c.generate();assert.equal(notices.at(-1)[0],'路径不足');assert.equal(notices.at(-1)[1],'warn');
 const empty=context({cards:[],reason:'需要检查路线'});empty.c.state.cards=[{key:'previous'}];
 await empty.c.generate();assert.equal(empty.c.state.cards[0].key,'previous');assert.equal(empty.c.triages,0);
});
test('watch cards explain satisfied watched concepts without adding learning tasks',()=>{
 const code=html.slice(html.indexOf('const ROUTE_KINDS'),html.indexOf('const PDF_BADGES'));
 const c=vm.createContext({esc:String});vm.runInContext(code,c);
 assert.match(c.routeBadge({route:{kind:'watch',name:'Lattice'}}),/持续关注/);
 assert.match(c.routeBadge({route:{kind:'watch'}}),/不增加学习任务/);
 assert.equal(c.routeBadge({route:{kind:'unknown'}}),'');
});
