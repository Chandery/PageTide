'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const page=fs.readFileSync(path.join(__dirname,'../app/static/route-page.js'),'utf8');
const index=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
const judge=page.slice(page.indexOf('async function judgeNow()'),page.indexOf("part('growthList').onclick"));
const load=page.slice(page.indexOf('async function loadGrowth()'),page.indexOf("part('findGrowth').onclick"));
const today=index.slice(index.indexOf('async function doJudge(key)'),index.indexOf('function cardHTML'));
const prompt=index.slice(index.indexOf('function judgeAskHTML(c)'),index.indexOf('function judgeSummary(results)'));
const feedback=index.slice(index.indexOf('async function doFeedback('),index.indexOf("$('#cards').addEventListener"));
const R=require('../app/static/route-editor.js');
const queueResult=(overrides={})=>({ok:true,results:[],judges_left:9,requested:20,processed:20,complete:true,pending:0,model_calls:7,...overrides});
function mapContext(result) {
 const notices=[],calls=[];
 const c=vm.createContext({growth:{judging:false,result:{judges_left:10,pending:Array.from({length:result.requested||0},(_,i)=>({key:String(i)}))}},state:{draft:null},
  api:async body=>{calls.push(body.action);return body.action==='candidates'?{judges_left:result.judges_left,candidates:[],pending:[]}:result;},
  notice:(...args)=>notices.push(args),renderGrowth:()=>{},render:()=>{},R:{...R,judgeSummary:()=> 'proposal'}});
 vm.runInContext(load+judge,c);return {c,notices,calls};
}
test('a paid invalid judgment refreshes remaining attempts and never claims AI was unused',async()=>{
 const {c,notices,calls}=mapContext({ok:false,reason_code:'bad_reply',reason:'未保存学习判断',judges_left:9});
 await c.judgeNow();assert.deepEqual(calls,['direction-judge','candidates']);
 assert.equal(c.growth.result.judges_left,9);assert.equal(c.growth.judging,false);
 assert.equal(notices.at(-1)[0],'未得到有效判断：未保存学习判断');
 assert.doesNotMatch(notices.at(-1)[0],/没有使用 AI|本地整理|9 次/);
});
test('an unpaid approval refusal retains its reason and refreshed attempts',async()=>{
 const {c,notices}=mapContext({ok:false,reason_code:'not_approved',reason:'尚未批准',judges_left:10});
 await c.judgeNow();assert.equal(c.growth.result.judges_left,10);
 assert.match(notices.at(-1)[0],/尚未批准/);
});
test('Today says invalid judgment and actual attempts without hiding the retry button',async()=>{
 const notices=[];const card={key:'x',judgeAsk:true};
 const c=vm.createContext({state:{currentProject:'p',cards:[card]},api:async()=>({ok:false,reason:'未保存',judges_left:9}),
  renderCards:()=>{},toast:(...args)=>notices.push(args),PTRoute:R});vm.runInContext(today,c);
 await c.doJudge('x');assert.equal(card.judgeBusy,false);assert.equal(card.judgeAsk,true);
 assert.equal(notices.at(-1)[0],'未得到判断：未保存');assert.doesNotMatch(notices.at(-1)[0],/没有使用 AI|9 次/);
});

test('the map reports the entire 20-paper snapshot with one request and one attempt',async()=>{
 const {c,notices,calls}=mapContext(queueResult());
 await c.judgeNow();
 assert.deepEqual(calls,['direction-judge','candidates']);
 assert.equal(notices.at(-1)[0],'判断完毕 · 20/20 篇');
 assert.equal(notices.at(-1)[1],false);assert.equal(c.growth.judging,false);
 assert.ok(notices.some(([line])=>line==='正在判断…'));
});
test('a complete map queue still warns when request or billing status is unknown',async()=>{
 const {c,notices}=mapContext(queueResult({reason_code:'network',reason:'Request or billing status is unknown'}));
 await c.judgeNow();
 assert.equal(notices.at(-1)[0],'判断完毕 · 20/20 篇 · Request or billing status is unknown');
 assert.equal(notices.at(-1)[1],true);
});
test('a partial saved result reports counts and a stop reason without claiming completion',async()=>{
 const out=queueResult({processed:9,complete:false,pending:11,model_calls:4,reason:'本日 token 预算不足',results:[{verdict:'new',direction:'d1'}]});
 const {c,notices}=mapContext(out);
 await c.judgeNow();
 assert.equal(notices.at(-1)[0],'判断已停止 · 9/20 篇 · 还有 11 篇待判断 · 本日 token 预算不足');
 assert.doesNotMatch(notices.at(-1)[0],/判断完毕|AI 判断完了/);
 assert.equal(notices.at(-1)[1],true);assert.equal(c.growth.selected,'d1');
});
test('a stopped job can be continued with counts from the next snapshot',async()=>{
 const {c,notices,calls}=mapContext(queueResult({processed:9,complete:false,pending:11,model_calls:3,reason:'回复不完整'}));
 await c.judgeNow();
 c.api=async body=>{calls.push(body.action);return body.action==='candidates'?{judges_left:8,candidates:[],pending:[]}:queueResult({requested:11,processed:11,judges_left:8,model_calls:4});};
 await c.judgeNow();
 assert.deepEqual(calls,['direction-judge','candidates','direction-judge','candidates']);
 assert.equal(notices.at(-1)[0],'判断完毕 · 11/11 篇');
});
function todayContext(cards,result){
 const notices=[],calls=[],renders=[];
 const state={currentProject:'p',cards};
 const c=vm.createContext({state,PTRoute:R,judgeSummary:()=> 'proposal',
  api:async(path,body)=>{calls.push(body);return typeof result==='function'?result(body):result;},
  toast:(...args)=>notices.push(args),renderCards:()=>renders.push(cards.map(card=>Boolean(card.judgeBusy)))});
 vm.runInContext(today,c);return {c,state,notices,calls,renders};
}
test('Today complete clears every prompt that was present at the start',async()=>{
 const cards=[{key:'x',judgeAsk:true},{key:'y',judgeAsk:true}];
 const {c,notices,calls}=todayContext(cards,queueResult());
 await c.doJudge('x');
 assert.equal(calls.length,1);assert.equal(calls[0].project_id,'p');
 assert.deepEqual(cards.map(card=>card.judgeAsk),[false,false]);
 assert.deepEqual(cards.map(card=>card.judgeBusy),[false,false]);
 assert.match(notices.at(-1)[0],/20\/20 篇/);assert.equal(notices.at(-1)[1],'ok');
});
test('Today warns about unknown billing even when paper judgments are complete',async()=>{
 const card={key:'x',judgeAsk:true};
 const {c,notices}=todayContext([card],queueResult({reason_code:'network',reason:'Request or billing status is unknown'}));
 await c.doJudge('x');
 assert.equal(card.judgeAsk,false);assert.equal(notices.at(-1)[1],'warn');
 assert.match(notices.at(-1)[0],/20\/20 篇.*Request or billing status is unknown/);
});
test('Today partial keeps all prompts, then a complete continuation clears them',async()=>{
 const cards=[{key:'x',judgeAsk:true},{key:'y',judgeAsk:true}];
 const {c,notices,calls}=todayContext(cards,queueResult({processed:9,complete:false,pending:11,reason:'预算不足'}));
 await c.doJudge('x');
 assert.deepEqual(cards.map(card=>card.judgeAsk),[true,true]);assert.equal(notices.at(-1)[1],'warn');
 assert.match(notices.at(-1)[0],/9\/20 篇.*还有 11 篇待判断.*预算不足/);
 c.api=async(path,body)=>{calls.push(body);return queueResult({requested:11,processed:11,judges_left:8});};
 await c.doJudge('y');
 assert.equal(calls.length,2);assert.deepEqual(cards.map(card=>card.judgeAsk),[false,false]);
 assert.equal(notices.at(-1)[0],'判断完毕 · 11/11 篇');
});
test('Today complete snapshot can leave new papers pending without hiding their prompts',async()=>{
 let resolve;const cards=[{key:'x',judgeAsk:true}];
 const {c,notices}=todayContext(cards,()=>new Promise(done=>{resolve=done;}));
 const job=c.doJudge('x');
 const added={key:'new',judgeAsk:true};cards.push(added);
 resolve(queueResult({pending:2}));await job;
 assert.equal(cards[0].judgeAsk,false);assert.equal(added.judgeAsk,true);
 assert.equal(notices.at(-1)[0],'判断完毕 · 20/20 篇 · 还有 2 篇待判断');
});
test('Today locks the project across cards and releases the lock after a stopped job',async()=>{
 let resolve;const cards=[{key:'x',judgeAsk:true},{key:'y',judgeAsk:true}];
 const {c,calls,renders}=todayContext(cards,()=>new Promise(done=>{resolve=done;}));
 const job=c.doJudge('x');await c.doJudge('y');
 assert.equal(calls.length,1);assert.deepEqual(renders[0],[true,true]);
 resolve(queueResult({processed:0,complete:false,pending:20,reason:'尚未批准',ok:false}));await job;
 assert.equal(c.state.judgeJobs.has('p'),false);
 c.api=async(path,body)=>{calls.push(body);return queueResult();};await c.doJudge('y');
 assert.equal(calls.length,2);
});
test('a newly added Today prompt is disabled by the project lock and unlocked after failure',async()=>{
 let reject;const cards=[{key:'x',judgeAsk:true}];
 const {c,state,notices}=todayContext(cards,()=>new Promise((resolve,no)=>{reject=no;}));
 c.esc=String;vm.runInContext(prompt,c);
 const job=c.doJudge('x'),added={key:'new',judgeAsk:true};cards.push(added);
 assert.match(c.judgeAskHTML(added),/data-judge="ask"[^>]*disabled/);
 assert.match(c.judgeAskHTML(added),/判断中…/);
 reject(Error('Connection interrupted'));await job;
 assert.equal(state.judgeJobs.has('p'),false);assert.equal(added.judgeAsk,true);
 assert.doesNotMatch(c.judgeAskHTML(added),/data-judge="ask"[^>]*disabled/);
 assert.equal(notices.at(-1)[0],'Connection interrupted');assert.equal(notices.at(-1)[1],'err');
});
test('a stale Today response cannot clear or notify a different project',async()=>{
 let resolve;const oldCard={key:'x',judgeAsk:true};
 const {c,state,notices,calls}=todayContext([oldCard],()=>new Promise(done=>{resolve=done;}));
 const job=c.doJudge('x');const newCard={key:'x',judgeAsk:true};
 state.currentProject='other';state.cards=[newCard];
 resolve(queueResult());await job;
 assert.equal(calls[0].project_id,'p');assert.equal(newCard.judgeAsk,true);
 assert.equal(oldCard.judgeBusy,false);assert.equal(state.judgeJobs.has('p'),false);
 assert.equal(notices.length,0);
});
test('Today legacy successful fixture retains its original summary and one-card dismissal',async()=>{
 const cards=[{key:'x',judgeAsk:true},{key:'y',judgeAsk:true}];
 const {c,notices}=todayContext(cards,{ok:true,results:[],judges_left:9});
 await c.doJudge('x');assert.equal(notices.at(-1)[0],'proposal');
 assert.deepEqual(cards.map(card=>card.judgeAsk),[false,true]);
});
test('Useful shows the growth prompt, difficulty keeps interest, irrelevant clears the prompt',async()=>{
 const card={key:'x'};const c=vm.createContext({state:{currentProject:'p',cards:[card],route:{graph:{}},view:'today'},
  api:async()=>({saved:true}),toast:()=>{},renderCards:()=>{},refreshStats:async()=>{}});vm.runInContext(feedback,c);
 await c.doFeedback('x','useful');assert.equal(card.judgeAsk,true);
 await c.doFeedback('x','too_hard');assert.equal(card.judgeAsk,true);
 await c.doFeedback('x','irrelevant');assert.equal(card.judgeAsk,false);
});

test('a complete Today job preserves a new same-card prompt created by real feedback',async()=>{
 let resolve;const cards=[{key:'x'},{key:'y'}];
 const {c,state}=todayContext(cards,queueResult());state.route={graph:{}};state.view='today';
 c.refreshStats=async()=>{};vm.runInContext(feedback,c);
 c.api=async(path)=>path==='/api/route'?new Promise(done=>{resolve=done;}):{saved:true};
 await c.doFeedback('x','useful');await c.doFeedback('y','useful');
 const original=cards[0].judgeAskGeneration,job=c.doJudge('x');
 await c.doFeedback('x','irrelevant');assert.equal(cards[0].judgeAsk,false);
 await c.doFeedback('x','useful');assert.ok(cards[0].judgeAskGeneration>original);
 resolve(queueResult({requested:2,processed:2,pending:1}));await job;
 assert.equal(cards[0].judgeAsk,true);assert.equal(cards[1].judgeAsk,false);
 assert.equal(cards[0].judgeBusy,false);assert.equal(state.judgeJobs.has('p'),false);
});
test('continuing a partial job without processed keys cannot clear newly expressed interest',async()=>{
 let resolve,jobNumber=0;const cards=[{key:'x'},{key:'y'}];
 const {c,state}=todayContext(cards,queueResult());state.route={graph:{}};state.view='today';
 c.refreshStats=async()=>{};vm.runInContext(feedback,c);
 c.api=async(path)=>{
  if(path!=='/api/route')return {saved:true};
  if(++jobNumber===1)return queueResult({requested:2,processed:1,pending:1,complete:false,reason:'Interrupted'});
  return new Promise(done=>{resolve=done;});
 };
 await c.doFeedback('x','useful');await c.doFeedback('y','useful');
 await c.doJudge('x');assert.deepEqual(cards.map(card=>card.judgeAsk),[true,true]);
 const job=c.doJudge('y');
 await c.doFeedback('x','irrelevant');await c.doFeedback('x','useful');
 resolve(queueResult({requested:1,processed:1,pending:1}));await job;
 assert.equal(jobNumber,2);assert.deepEqual(cards.map(card=>card.judgeAsk),[true,false]);
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
