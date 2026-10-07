'use strict';
const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const Context=require('../app/static/paper-context.js');
test('category, multi-unit and purpose labels stay separate and escape all source text',()=>{
  const html=Context.html({project_id:'p"x',categories:[{name:'<b>category</b>'}],units:[{id:'a"x',name:'<img src=x>'},{id:'b',name:'Second'}],map_available:true,route_enabled:false,saved_in_project:true,recommendation:{kind:'watch',name:'Old name'}},'k"x');
  for(const label of ['收藏类别','对应学习单元','本次推荐用途','关注新进展','Route 已关闭','在论文关系图中定位','在学习图中定位']) assert.ok(html.includes(label));
  assert.ok(!html.includes('<img'));assert.ok(!html.includes('<b>category'));
  assert.equal((html.match(/定位学习单元/g)||[]).length,2);
  assert.match(html,/data-key="k&quot;x"/);assert.match(html,/data-unit="a&quot;x"/);
});
test('unsaved papers have context but no graph navigation, unmatched saved papers retain both jumps',()=>{
  const c={project_id:'p',categories:[],units:[],map_available:true,route_enabled:true,saved_in_project:false,recommendation:null};
  assert.ok(!Context.html(c,'k').includes('data-action="graph-navigate"'));
  assert.match(Context.html({...c,saved_in_project:true},'k'),/没有对应的学习单元/);
  assert.equal((Context.html({...c,saved_in_project:true},'k').match(/data-action="graph-navigate"/g)||[]).length,2);
});
function drawerFixture(){
  const source=fs.readFileSync('app/static/index.html','utf8');
  const section=source.slice(source.indexOf('let detailToken = 0;'),source.indexOf("$('#detail').addEventListener('click'"));
  const nodes=new Map(), replies=[], notices=[];
  const node=selector=>{if(!nodes.has(selector)) nodes.set(selector,{innerHTML:'',classList:{add(){},remove(){}},addEventListener(){}});return nodes.get(selector);};
  const ctx=vm.createContext({state:{currentProject:'p1',projects:[]},window:{PDHPaperContext:Context,PDH:{setPetContext(){}}},PaperPolicy:{label:()=>''},$:node,hidePreview(){},esc:v=>v,md:v=>v,toast:(...v)=>notices.push(v),api:(url,body)=>new Promise(resolve=>replies.push({body,resolve}))});
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
