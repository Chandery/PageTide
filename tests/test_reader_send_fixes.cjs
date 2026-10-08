'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const html=fs.readFileSync('app/static/index.html','utf8');
const source=html.slice(html.indexOf('async function ask(question)'),html.indexOf('async function translate(text, rect)'));
function fixture(reply = {ok:false,reason:"AI disabled"}) {
  const sent=[], notices=[], messages=[];
  const pet={key:'a',project:'cs',epoch:1,title:'A',selection:'A quote',selPage:1,busy:false,attachPage:false,session:'session',sessionPromise:Promise.resolve(),referenceIdentity:{key:'a',project_id:'cs',pdf_sha256:'a'.repeat(64),kind:'pdf'}};
  const R={key:'a',project:'cs',sha256:'a'.repeat(64),doc:{},current:1,loading:false};
  const node={classList:{contains:()=>false},disabled:false,checked:false};
  const context=vm.createContext({pet,R,state:{currentProject:'medicine'},
    $:()=>node,openPet(){},toast:(...args)=>notices.push(args),
    addMsg:(...args)=>{messages.push(args);return {prepend(){},remove(){}};},refCard(){},
    setReference(){pet.selection=null;pet.selPage=null;pet.referenceIdentity=null;},
    setAttachPage:value=>{pet.attachPage=value;},
    PDHFigure:{figureRequest:()=>null},PDHReaderIdentity:require('../app/static/reader-identity.js'),
    api:async(path,body)=>{sent.push({path,body});return reply;},aiFailure:r=>r});
  vm.runInContext(html.slice(html.indexOf('function aiUsageText(result)'),html.indexOf('function aiFailure(reason)')),context);
  vm.runInContext(source,context);
  return {pet,R,sent,notices,messages,ask:context.ask};
}
test('actual send rejects mixed paper, project or quote version before API transport',async()=>{
  for (const mismatch of [f=>{f.pet.key='b';},f=>{f.pet.project='medicine';},f=>{f.pet.referenceIdentity.pdf_sha256='b'.repeat(64);}]) {
    const f=fixture();mismatch(f);await f.ask('What does this quote mean?');
    assert.equal(f.sent.length,0);assert.ok(f.notices.some(n=>n[0].includes('不一致')));
  }
});
test('actual answer reports unknown billing as a reservation, not measured token use', async()=>{
  const f=fixture({ok:true,answer:'Bounded evidence',mode:'text',usage:{total_tokens:5500},usd:'0.00258',usage_unknown:true,usage_reserved:true});
  await f.ask('Explain');
  assert.ok(f.notices.some(n=>n[0].includes('计费未确认，暂按上限占用')));
  assert.ok(f.notices.every(n=>!n[0].includes('5500 token')));
});
test('actual send binds selected quote to reading project and PDF, despite unrelated top project',async()=>{
  const f=fixture();await f.ask('What does this quote mean?');
  const body=f.sent[0].body;
  assert.equal(body.key,'a');assert.equal(body.project_id,'cs');assert.equal(body.selection,'A quote');
  assert.equal(body.reader_context.pdf_sha256,'a'.repeat(64));assert.equal(body.session_id,'session');
});

test('actual reply visibly discloses omitted retrieval passages and abstract excerpts',async()=>{
  const f=fixture({ok:true,answer:'Bounded public evidence',mode:'text',pages:[1],usage:{total_tokens:1},usd:'0',context_limits:{abstract_truncated:true,omitted_passages:2}});
  await f.ask('Explain this evidence');
  const message=f.messages.find(m=>m[0]==='ai');assert.ok(message);
  assert.ok(message[3].includes('摘要仅为节选'));
  assert.ok(message[3].includes('输入上限省略了 2 段检索内容'));
});
