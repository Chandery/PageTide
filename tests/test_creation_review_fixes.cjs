'use strict';
// Executes production review adapters and field validation. No model, network or private library.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=()=>fs.readFileSync(path.join(__dirname,'../app/static/project-creation.js'),'utf8');
const R=require('../app/static/route-editor.js');
function functionSource(name,next){const s=source(),start=s.indexOf(`function ${name}(`);assert.ok(start>=0,`production ${name} exists`);return s.slice(start,s.indexOf(next,start));}
const graph=()=>({concepts:[{id:'c1',name:'基础',terms:['world models'],hint:2,origin:'plan',state:'active'}],prereqs:[],targets:['c1']});
test('stage editing updates the real route concept and purpose, preserving independent branches and mastery',()=>{
 const context={window:{PDHRoute:R}};vm.createContext(context);vm.runInContext(functionSource('updateStageGraph','\nfunction creationFieldError(')+';globalThis.update=updateStageGraph;',context);
 const original=graph(),out=context.update(original,{title:'潜变量',purpose:'读懂隐状态'},'c1',['latent dynamics']);
 assert.equal(out.graph.concepts[0].name,'潜变量');assert.equal(out.graph.concepts[0].intro,'读懂隐状态');assert.equal(out.graph.concepts[0].intro_by,'user');assert.equal(out.graph.prereqs.length,0);assert.equal(JSON.stringify(out.graph.targets),'["c1"]');assert.equal(original.concepts[0].name,'基础');
 const added=context.update(out.graph,{title:'Planning',purpose:'学会规划'},null,['latent dynamics']);assert.equal(added.graph.concepts.length,2);assert.equal(added.graph.targets.length,2);assert.equal(added.graph.prereqs.length,0);assert.equal(added.graph.concepts[1].terms[0],'Planning');
 const ai=graph();ai.concepts[0].intro='AI stage purpose';ai.concepts[0].intro_by='ai';
 const renamed=context.update(ai,{title:'人工改名',purpose:'AI stage purpose'},'c1',[]);assert.equal(renamed.graph.concepts[0].intro_by,'ai','renaming must not relabel unchanged AI prose as user-authored');
});
test('review receives local route draft, redraws it and does not replace a manually edited map',()=>{
 let renders=0;const slots=new Map(),part=name=>{if(!slots.has(name))slots.set(name,{value:'',innerHTML:'',querySelectorAll:()=>[]});return slots.get(name);};
 const context={part,keywords:{set(){}},syncPath(){},addPathItem(){},Brief:{set(){}},map:{graph:null,briefDirty:false,discarded:false,userEdited:false},candidates:{size:0},addCandidates(){},refresh(){},mapNotice(){},renderMap(){renders++;},bindPathConcepts(){}};
 vm.createContext(context);vm.runInContext(functionSource('setDraft','\n  function addCandidates(')+';globalThis.set=setDraft;',context);
 context.set({goal:'Learn',route_draft:{graph:graph(),brief:{goal:'Learn'},source:'local_goal'}});assert.equal(context.map.graph.concepts[0].name,'基础');assert.equal(renders,1);
 context.map.userEdited=true;context.map.graph.concepts[0].name='我的编辑';context.set({route_draft:{graph:graph(),source:'local_stages'}});assert.equal(context.map.graph.concepts[0].name,'我的编辑');
 context.map.graph=null;context.map.discarded=true;context.set({route_draft:{graph:graph(),source:'local_stages'}});assert.equal(context.map.graph,null);
});
test('the confirmed brainstorm graph replaces only the automatic map and stage rows follow its actual concepts and edges',()=>{
 const slots=new Map(),rows=[],part=name=>{if(!slots.has(name))slots.set(name,{value:'',innerHTML:'',querySelectorAll:()=>[]});return slots.get(name);};let bound,notice='';
 const context={part,MAX_PATH:8,keywords:{set(){}},syncPath(){},addPathItem(item){rows.push(item);},Brief:{set(){}},map:{graph:graph(),briefDirty:false,discarded:false,userEdited:false},candidates:{size:0},addCandidates(){},refresh(){},mapNotice(message){notice=message;},renderMap(){},bindPathConcepts(ids){bound=ids;}};
 const ai={concepts:[{id:'a',name:'概率基础',terms:['probability'],intro:'AI foundation',intro_by:'ai',origin:'plan'},{id:'b',name:'Latent dynamics',terms:['latent dynamics'],intro:'AI target',intro_by:'ai',origin:'plan'}],prereqs:[{from:'a',to:'b',origin:'plan',support:null}],targets:['b']};
 vm.createContext(context);vm.runInContext(functionSource('setDraft','\n  function addCandidates(')+';globalThis.set=setDraft;',context);
 context.set({learning_path:[{title:'Old stage',purpose:'Old'}],route_draft:{graph:ai,brief:{goal:'Study latent dynamics'},source:'ai_guidance'}});
 assert.equal(context.map.graph,ai);assert.equal(context.map.graph.prereqs.length,1);assert.equal(rows[0].title,'概率基础');assert.equal(rows.some(row=>row.title==='Old stage'),false);assert.equal(JSON.stringify(bound),'["a","b"]');assert.match(notice,/AI/);
 context.map.userEdited=true;context.map.graph.concepts[0].name='我的基础';context.set({route_draft:{graph:graph(),source:'ai_guidance'}});assert.equal(context.map.graph.concepts[0].name,'我的基础');
});
test('missing discipline and language errors appear at their input and focus/scroll there',()=>{
 const events=[],nodes=new Map();const doc={createElement(){return {setAttribute(){},classList:{toggle(){}},textContent:''};}};
 const field=id=>{if(!nodes.has(id))nodes.set(id,{id,ownerDocument:doc,attrs:{},value:'',checked:false,parentElement:{appendChild(el){this.error=el;}},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},addEventListener(){},scrollIntoView(){events.push(['scroll',id]);},focus(){events.push(['focus',id]);}});return nodes.get(id);};
 const choices=field('choices'),select=field('select'),check=field('checkbox'),container={querySelector(s){return s==='select'?select:s==='input[type=checkbox]'?check:choices;}};
 let reason='请选择理工科或文科';const context={document:doc,$:()=>container,policyEditor:{read(){throw new Error(reason);}}};vm.createContext(context);vm.runInContext(functionSource('creationFieldError','\n// Where to go once a project exists:')+';globalThis.read=readCreationPolicy;',context);
 assert.equal(context.read(),null);assert.equal(select.attrs['aria-invalid'],'true');assert.equal(select.parentElement.error.textContent,reason);assert.deepEqual(events.at(-1),['focus','select']);
 reason='请至少选择一种允许的论文语言';select.value='humanities';assert.equal(context.read(),null);assert.deepEqual(events.at(-1),['focus','checkbox']);
});
test('confirm creation requires a reviewed graph and validates policy before creating',async()=>{
 const s=source(),start=s.indexOf("part('create').onclick = async () => {");assert.ok(start>=0);const end=s.indexOf('\n  refresh();\n  return',start),body=s.slice(start,end);
 let created=0,notice='',policyCalls=0;const slots=new Map(),part=name=>{if(!slots.has(name))slots.set(name,{checked:false,disabled:false,hidden:false,focus(){},scrollIntoView(){},querySelectorAll:()=>[]});return slots.get(name);};
 const context={part,$$:()=>[],map:{graph:graph(),generating:false,checking:false,editing:null,discarded:false},R,mapNotice(m){notice=m;},readCreationPolicy(){policyCalls++;return {discipline:'stem'};},readCreationBrief:()=>({goal:'Learn'}),busy:false,refresh(){},createAct:{start(){},stop(){},fail(){}},mapPayload:()=>({graph:graph()}),draft:()=>({keywords:['world model']}),selected:new Set(),onCreate:async payload=>{created++;assert.ok(payload.route.graph);}};
 vm.createContext(context);vm.runInContext(body,context);await part('create').onclick();assert.equal(created,0);assert.match(notice,/确认/);assert.equal(policyCalls,1);
 part('mapConfirm').checked=true;await part('create').onclick();assert.equal(created,1);
});
test('explicitly dropping a map is the only route-null finalize request and does not restore stage rows',async()=>{
 const slots=new Map(),part=name=>{if(!slots.has(name))slots.set(name,{querySelectorAll:()=>[]});return slots.get(name);};let committed=0,received;
 const s=source(),start=s.indexOf("part('create').onclick = async () => {"),end=s.indexOf('\n  refresh();\n  return',start);
 const context={part,$$:()=>[{commit(){committed++;}}],map:{graph:null,discarded:true},R,busy:false,readCreationPolicy:()=>({discipline:'stem'}),refresh(){},createAct:{start(){},stop(){},fail(){}},mapPayload:()=>null,draft:()=>({keywords:['planning']}),selected:new Set(),onCreate:async payload=>{received=payload;}};
 vm.createContext(context);vm.runInContext(s.slice(start,end),context);await part('create').onclick();assert.equal(committed,0);assert.equal(received.route,null);
 const finalContext={SESSION_KEY:'fixture',policyEditor:{disabled(){}},readCreationPolicy:()=>({discipline:'stem'}),session:{id:'s'},post:async(_,payload)=>{received=payload;return {project_id:'p'};},localStorage:{removeItem(){}},location:{},afterCreate:()=>'/project',creationLeaving:false};
 vm.createContext(finalContext);vm.runInContext(s.slice(s.indexOf('async function finalize('),s.indexOf('\nasync function createSession('))+';globalThis.finish=finalize;',finalContext);await finalContext.finish({draft:{},selectedKeys:[],route:null});assert.equal(received.skip_route,true);
});
test('guided question shows actionable choices, sends the chosen answer once and disables choices at round six',()=>{
 const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{children:[],innerHTML:'',textContent:'',replaceChildren(){},appendChild(el){this.children.push(el);}});return nodes.get(id);};let sent;
 const context={$:node,$$:()=>[],session:{transcript:[],turn_count:1,draft:{summary:'已确认入门',next_question:'更想理解还是复现？',choices:['先理解','先复现'],ready:false}},guidedBusy:false,bubble(){},esc:v=>String(v),document:{createElement:()=>({setAttribute(){}})},guidedTurn:message=>{sent=message;}};
 vm.createContext(context);vm.runInContext(functionSource('renderChat','\nfunction showPending(')+';globalThis.render=renderChat;',context);context.render(null);const question=node('#guideQuestion');assert.match(question.innerHTML,/更想理解/);assert.equal(question.children.length,2);question.children[0].onclick();assert.equal(sent.message,'先理解');
 question.children=[];context.session.turn_count=6;context.render(null);assert.equal(question.children.every(button=>button.disabled),true);assert.equal(node('#guideSend').disabled,true);
});
test('explicit AI graph planning rebuilds bound stage rows rather than re-adding the old stages on creation',async()=>{
 const rows=[{title:'Old local stage'}],slots=new Map(),part=name=>{if(!slots.has(name))slots.set(name,{querySelectorAll:()=>[],set innerHTML(value){if(name==='path')rows.length=0;}});return slots.get(name);};
 const next={concepts:Array.from({length:12},(_,i)=>({id:`new${i}`,name:`New concept ${i}`,intro:'AI purpose',intro_by:'ai'})),prereqs:[],targets:['new11']};
 const context={part,map:{graph:graph()},busy:false,sessionId:()=> 'session',readCreationBrief:()=>({goal:'Goal'}),refresh(){},mapNotice(){},mapAct:{start(){},stop(){}},post:async()=>({ok:true,graph:next}),changedMap(){},MAX_PATH:8,addPathItem:item=>rows.push(item),syncPath(){},bindPathConcepts(){},renderMap(){}};
 vm.createContext(context);vm.runInContext('async '+functionSource('generateMap',"\n  part('mapGenerate').onclick")+';globalThis.generate=generateMap;',context);await context.generate(false);
 assert.equal(rows.length,8);assert.equal(rows[0].title,'New concept 0');assert.equal(rows.some(item=>item.title==='Old local stage'),false);assert.equal(context.map.graph.concepts.length,12);
});
test('starting a manual map clears old bound stages so submitting cannot resurrect their concepts',()=>{
 const slots=new Map(),part=name=>{if(!slots.has(name))slots.set(name,{innerHTML:name==='path'?'<div class="path-item" data-concept-id="old">Old stage</div>':'',disabled:true});return slots.get(name);};
 const context={part,map:{graph:graph(),mastered:['c1']},busy:false,window:{},changedMap(){},renderMap(){}};vm.createContext(context);
 const s=source();vm.runInContext(s.slice(s.indexOf("  part('mapStart').onclick = "),s.indexOf("  part('mapDrop').onclick = ")),context);part('mapStart').onclick();
 assert.equal(part('path').innerHTML,'');assert.equal(part('addPath').disabled,false);assert.equal(context.map.graph.concepts.length,1);assert.equal(context.map.graph.concepts[0].id,'c1');assert.equal(context.map.mastered.length,0);
});
test('a pending guided turn disables keyword deletion along with input, then restores both',()=>{
 const input={tag:'input',disabled:false},remove={tag:'button',disabled:false},slots=new Map(),part=name=>{if(!slots.has(name))slots.set(name,{controls:name==='keywords'?[input,remove]:[]});return slots.get(name);};
 const context={part,$:(_,root)=>root.controls[0],$$:(selector,root)=>(root.controls||[]).filter(el=>selector.split(',').map(s=>s.trim()).includes(el.tag)),keywords:{get:()=>['planning']},selected:new Set(),MAX_PATH:8,searching:false,busy:true,map:{generating:false,checking:false}};
 vm.createContext(context);vm.runInContext(functionSource('refresh','\n  /* ---- learning map:')+';globalThis.refreshReview=refresh;',context);context.refreshReview();assert.equal(input.disabled,true);assert.equal(remove.disabled,true);
 context.busy=false;context.refreshReview();assert.equal(input.disabled,false);assert.equal(remove.disabled,false);
});
test('clearing a bound stage revokes map confirmation and blocks commit at its title; only new empty rows may be ignored',()=>{
 const rows=[],errors=[],input=()=>({value:'',listeners:{},addEventListener(kind,fn){this.listeners[kind]=fn;},focus(){}});
 const doc={createElement(){return {dataset:{},fields:{input:input(),textarea:input(),button:input()},remove(){rows.splice(rows.indexOf(this),1);}};}},slots=new Map();
 const part=name=>{if(!slots.has(name))slots.set(name,{checked:true,appendChild(row){rows.push(row);}});return slots.get(name);};
 const context={part,$:(selector,row)=>row.fields[selector],$$:()=>rows,document:doc,MAX_PATH:8,map:{graph:graph(),mastered:[],userEdited:false},busy:false,R,keywords:{get:()=>['planning']},changedMap(){context.map.userEdited=true;part('mapConfirm').checked=false;},creationFieldError(field,message){errors.push(message);},mapNotice(){},renderMap(){},syncPath(){},updateStageGraph(){throw new Error('must not update an empty stage');}};
 vm.createContext(context);vm.runInContext(functionSource('addPathItem','\n  const syncPath = ')+ ';globalThis.addStage=addPathItem;',context);context.addStage({title:'基础',purpose:'AI stage'});const bound=rows[0];bound.dataset.conceptId='c1';bound.fields.input.value='';bound.fields.textarea.value='';
 assert.equal(typeof bound.fields.input.listeners.input,'function');bound.fields.input.listeners.input();assert.equal(part('mapConfirm').checked,false);assert.equal(context.map.userEdited,true);assert.equal(bound.commit(),false);assert.equal(errors.at(-1),'请填写阶段标题');assert.equal(context.map.graph.concepts.length,1);
 context.addStage({});const fresh=rows[1];assert.equal(fresh.commit(),true);
});
