'use strict';
const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const Context=require('../app/static/paper-context.js');
const Policy=require('../app/static/paper-policy.js');
test('category and unit names are shown with their jumps, escaped, and nothing is explained',()=>{
  const html=Context.html({project_id:'p"x',categories:[{name:'<b>category</b>'}],units:[{id:'a"x',name:'<img src=x>'},{id:'b',name:'Second'}],map_available:true,route_enabled:false,saved_in_project:true,recommendation:{kind:'watch',name:'Old name'}},'k"x');
  for(const label of ['收藏类别','学习单元','在论文关系图中定位','在学习图中定位']) assert.ok(html.includes(label));
  for(const gone of ['本次推荐用途','关注新进展','学习图已关闭','对应关系','<p class="hint">']) assert.ok(!html.includes(gone),gone);
  assert.ok(!html.includes('<img'));assert.ok(!html.includes('<b>category'));
  assert.equal((html.match(/定位学习单元/g)||[]).length,2);
  assert.match(html,/data-key="k&quot;x"/);assert.match(html,/data-unit="a&quot;x"/);
});
test('unsaved papers have no graph navigation; an unmatched saved paper keeps both jumps and says nothing more',()=>{
  const c={project_id:'p',categories:[],units:[],map_available:true,route_enabled:true,saved_in_project:false,recommendation:null};
  assert.ok(!Context.html(c,'k').includes('data-action="graph-navigate"'));
  assert.doesNotMatch(Context.html({...c,saved_in_project:true},'k'),/学习单元<\/b>|没有对应/);
  assert.equal((Context.html({...c,saved_in_project:true},'k').match(/data-action="graph-navigate"/g)||[]).length,2);
});

test('pending matching offers a retry, never claims there is no unit, and keeps paper navigation',()=>{
  const html=Context.html({project_id:'p',categories:[],units:[],map_available:true,route_enabled:true,saved_in_project:true,matching_status:'pending'},'pending');
  assert.match(html,/data-action="learning-match-retry"/);assert.ok(!html.includes('没有对应的学习单元'));
  assert.match(html,/在学习图中定位/);
});
function drawerFixture(){
  const source=fs.readFileSync('app/static/index.html','utf8');
  const section=source.slice(source.indexOf('let detailToken = 0;'),source.indexOf("$('#detail').addEventListener('click'"));
  const nodes=new Map(), replies=[], notices=[];
  const node=selector=>{if(!nodes.has(selector)){const classes=new Set();nodes.set(selector,{innerHTML:'',classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c)},addEventListener(){}});}return nodes.get(selector);};
  const ctx=vm.createContext({state:{currentProject:'p1',projects:[]},window:{PDHPaperContext:Context,PDH:{setPetContext(){}}},PaperPolicy:Policy,$:node,hidePreview(){},esc:v=>v,md:v=>v,toast:(...v)=>notices.push(v),api:(url,body)=>new Promise(resolve=>replies.push({body,resolve}))});
  vm.runInContext(section+'\nthis.open=openDetail;this.close=closeDetail;',ctx);
  return {ctx,replies,node,notices};
}
test('actual Today detail drops late paper/project replies and closing cancels pending rendering',async()=>{
  const {ctx,replies,node}=drawerFixture();
  const old=ctx.open('a');ctx.state.currentProject='p2';const latest=ctx.open('b');
  replies[0].resolve({key:'a',title:'OLD',projects:[]});await old;
  assert.equal(node('#detail').innerHTML,'');
  replies[1].resolve({key:'b',title:'NEW',projects:[],context:null});await latest;
  assert.match(node('#detail').innerHTML,/NEW/);assert.ok(!node('#detail').innerHTML.includes('OLD'));
  const third=ctx.open('c');ctx.close();const before=node('#detail').innerHTML;
  replies[2].resolve({key:'c',title:'CLOSED',projects:[]});await third;
  assert.equal(node('#detail').innerHTML,before);
});

test('reading from Today closes its stale detail and reopening rereads current learning evidence',async()=>{
  const {ctx,replies,node}=drawerFixture(), reads=[];
  ctx.window.PDH.openReader=(...args)=>{assert.equal(node('#detail').classList.contains('hidden'),true);reads.push(args);};
  const first=ctx.open('body');replies[0].resolve({key:'body',title:'Body paper',projects:[],context:{project_id:'p1',categories:[],units:[],map_available:true,route_enabled:true,saved_in_project:true}});await first;
  assert.doesNotMatch(node('#detail').innerHTML,/New body match/);
  node('#dRead').onclick();assert.equal(node('#detail').classList.contains('hidden'),true);
  assert.deepEqual(reads,[['body','Body paper']]);
  const reopened=ctx.open('body');assert.equal(replies.length,2);
  replies[1].resolve({key:'body',title:'Body paper',projects:[],context:{project_id:'p1',categories:[],units:[{id:'a',name:'New body match'}],map_available:true,route_enabled:true,saved_in_project:true}});await reopened;
  assert.match(node('#detail').innerHTML,/New body match/);assert.equal(node('#detail').classList.contains('hidden'),false);
});
