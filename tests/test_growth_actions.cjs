'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const page=fs.readFileSync(path.join(__dirname,'../app/static/route-page.js'),'utf8');
const index=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
const judge=page.slice(page.indexOf('async function judgeNow()'),page.indexOf("part('growthList').onclick"));
const load=page.slice(page.indexOf('async function loadGrowth()'),page.indexOf("part('findGrowth').onclick"));
const today=index.slice(index.indexOf('async function doJudge(key)'),index.indexOf('function cardHTML'));
const feedback=index.slice(index.indexOf('async function doFeedback(key, action)'),index.indexOf("$('#cards').addEventListener"));
function mapContext(result) {
 const notices=[],calls=[];
 const c=vm.createContext({growth:{judging:false,result:{judges_left:10}},state:{draft:null},
  api:async body=>{calls.push(body.action);return body.action==='candidates'?{judges_left:result.judges_left,candidates:[],pending:[]}:result;},
  notice:(...args)=>notices.push(args),renderGrowth:()=>{},render:()=>{},R:{judgeSummary:()=> 'proposal'}});
 vm.runInContext(load+judge,c);return {c,notices,calls};
}
test('a paid invalid judgment refreshes remaining attempts and never claims AI was unused',async()=>{
 const {c,notices,calls}=mapContext({ok:false,reason_code:'bad_reply',reason:'未保存学习判断',judges_left:9});
 await c.judgeNow();assert.deepEqual(calls,['direction-judge','candidates']);
 assert.equal(c.growth.result.judges_left,9);assert.equal(c.growth.judging,false);
 assert.match(notices.at(-1)[0],/未得到有效判断/);assert.match(notices.at(-1)[0],/9 次/);
 assert.doesNotMatch(notices.at(-1)[0],/没有使用 AI|本地整理/);
});
test('an unpaid approval refusal retains its reason and refreshed attempts',async()=>{
 const {c,notices}=mapContext({ok:false,reason_code:'not_approved',reason:'尚未批准',judges_left:10});
 await c.judgeNow();assert.equal(c.growth.result.judges_left,10);
 assert.match(notices.at(-1)[0],/尚未批准/);
});
test('Today says invalid judgment and actual attempts without hiding the retry button',async()=>{
 const notices=[];const card={key:'x',judgeAsk:true};
 const c=vm.createContext({state:{currentProject:'p',cards:[card]},api:async()=>({ok:false,reason:'未保存',judges_left:9}),
  renderCards:()=>{},toast:(...args)=>notices.push(args)});vm.runInContext(today,c);
 await c.doJudge('x');assert.equal(card.judgeBusy,false);assert.equal(card.judgeAsk,true);
 assert.match(notices.at(-1)[0],/未得到有效判断.*9 次/);assert.doesNotMatch(notices.at(-1)[0],/没有使用 AI/);
});
test('Useful shows the growth prompt, difficulty keeps interest, irrelevant clears the prompt',async()=>{
 const card={key:'x'};const c=vm.createContext({state:{currentProject:'p',cards:[card],route:{graph:{}},view:'today'},
  api:async()=>({saved:true}),toast:()=>{},renderCards:()=>{},refreshStats:async()=>{}});vm.runInContext(feedback,c);
 await c.doFeedback('x','useful');assert.equal(card.judgeAsk,true);
 await c.doFeedback('x','too_hard');assert.equal(card.judgeAsk,true);
 await c.doFeedback('x','irrelevant');assert.equal(card.judgeAsk,false);
});

test('the registered edge-state callback treats both proposed edge directions as ghosts',()=>{
 const source=page.slice(page.indexOf('edgeState:'),page.indexOf('onSelect:',page.indexOf('edgeState:')));
 const c=vm.createContext({known:true,route:{progress:{basis:{status:'satisfied'},goal:{status:'locked'}}}});
 const edge=vm.runInContext('({'+source+'}).edgeState',c);
 assert.equal(edge('basis','ghost:d1'),'ghost');assert.equal(edge('ghost:d1','goal'),'ghost');
 assert.equal(edge('basis','goal'),'met');
});
test('a judgment Conflict refreshes counts and stale opinions while preserving the edited draft',async()=>{
 const calls=[],notices=[],draft={concepts:[{name:'My unsaved edit'}]};
 const c=vm.createContext({growth:{judging:false,result:{judges_left:10}},state:{dirty:true,draft},
  api:async body=>{const action=body?body.action:'route';calls.push(action);
    if(action==='direction-judge')throw Error('Map changed during judgment');
    return action==='candidates'?{judges_left:9,candidates:[{stale:true}]}:{graph:{concepts:[{name:'Changed server map'}]}};},
  notice:(...args)=>notices.push(args),renderGrowth:()=>{},render:()=>{},R:{judgeSummary:()=>''}});
 const refresh=page.slice(page.indexOf('async function refreshRoute()'),page.indexOf('async function guarded('));
 vm.runInContext(refresh+load+judge,c);await c.judgeNow();
 assert.deepEqual(calls,['direction-judge','route','candidates']);assert.equal(c.state.draft,draft);
 assert.equal(c.growth.result.judges_left,9);assert.equal(c.growth.result.candidates[0].stale,true);
 assert.equal(c.growth.judging,false);assert.equal(notices.at(-1)[0],'Map changed during judgment');
});
