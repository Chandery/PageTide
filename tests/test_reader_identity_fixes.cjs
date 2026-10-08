'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const identity = require('../app/static/reader-identity.js');
test('selection and page evidence require the same paper, project and PDF version', () => {
  const a = {key:'a',project_id:'p',pdf_sha256:'v1'};
  assert.equal(identity.matches(a, {...a}),true);
  for (const [field,value] of [['key','b'],['project_id','q'],['pdf_sha256','v2']])
    assert.equal(identity.matches(a,{...a,[field]:value}),false);
});
test('bottom/right translation stays inside small viewport after content grows', () => {
  assert.deepEqual(identity.popupPosition({left:600,bottom:470},{width:400,height:330},{width:640,height:480}),{left:230,top:140});
  assert.deepEqual(identity.popupPosition({left:-10,bottom:40},{width:200,height:60},{width:640,height:480}),{left:10,top:50});
});
test('reading follows the selected library project without changing the top project', () => {
  assert.equal(identity.readingProject(['cs'],'cs','medicine'),'cs');
  assert.equal(identity.readingProject(['cs'],'all','medicine'),'cs');
  assert.equal(identity.readingProject(['cs','materials'],'all','medicine'),null);
});

const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../app/static/index.html'),'utf8');
const attachment = source.slice(source.indexOf('function showPdfFailure('),source.indexOf('async function openReader('));
for (const late of [false,true]) test(`actual attachment keeps reading project and suppresses stale reopen: late=${late}`,async()=>{
  const input={files:[{name:'a.pdf'}]},note={},calls=[];
  const box={querySelector:q=>q.includes('input')?input:note};let current=true;
  const ctx={esc:x=>x,pdfReason:x=>x,encodeURIComponent,api:async()=>{},fetch:async()=>{
    if(late)current=false;return {ok:true,json:async()=>({pdf_id:'public'})};
  },openReader:(...a)=>calls.push(a)};
  vm.createContext(ctx);vm.runInContext(attachment,ctx);
  ctx.showPdfFailure(box,'cs-paper','CS title',{reason:'missing'},'cs-project',()=>current);
  await input.onchange();
  assert.deepEqual(calls,late?[]:[['cs-paper','CS title','cs-project']]);
});
