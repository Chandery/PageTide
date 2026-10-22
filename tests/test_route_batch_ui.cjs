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
test('the generate button names the batch; the home page does not narrate batch composition',()=>{
 const {c}=context();
 assert.equal(c.dailyButtonText(),'生成今日发现');
 c.state.route.progress_verification_deferred=true;assert.equal(c.dailyButtonText(),'核验后生成推荐');
 c.state.route={enabled:false};assert.equal(c.dailyButtonText(),'生成今日 5 篇');
 assert.equal(typeof c.exploreLine,'undefined');
 for(const gone of ['每批最多','这次推荐：探索','以你现在能读的概念为主','每天只推一篇']) assert.ok(!html.includes(gone),gone);
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
test('watch cards show the short new-development label with the concept name and no standing explanation',()=>{
 const code=html.slice(html.indexOf('const ROUTE_KINDS'),html.indexOf('const PDF_BADGES'));
 const c=vm.createContext({esc:String});vm.runInContext(code,c);
 assert.match(c.routeBadge({route:{kind:'watch',name:'Lattice'}}),/新进展[\s\S]*Lattice/);
 assert.doesNotMatch(c.routeBadge({route:{kind:'watch',name:'Lattice'}}),/持续关注|不增加学习任务/);
 assert.match(c.routeBadge({route:{kind:'watch'}}),/新进展/);
 assert.doesNotMatch(c.routeBadge({route:{kind:'watch'}}),/不增加学习任务/);
 assert.equal(c.routeBadge({route:{kind:'unknown'}}),'');
});
