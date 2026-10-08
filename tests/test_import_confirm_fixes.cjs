'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app/static/import.js'),'utf8');
const discard=source.slice(source.indexOf("$('#discard').onclick = "),source.indexOf("$('#commit').onclick = "));
function page(){
 const button={disabled:false},calls=[],S={batch:{id:'a'},pendingActions:0};let decide;
 const context={$:()=>button,S,post:async url=>calls.push(url),guarded:async fn=>fn(),location:{reload:()=>calls.push('reload')},window:{PDHDialogs:{confirm:(_,options)=>new Promise(resolve=>decide=choice=>resolve(choice&&options.valid()))}}};vm.createContext(context);vm.runInContext(discard,context);
 return {button,calls,S,choose:choice=>decide(choice)};
}
test('actual discard waits for explicit confirmation, ignores double click and preserves cancelled batch',async()=>{
 const p=page(),run=p.button.onclick();assert.equal(p.button.disabled,true);assert.deepEqual(p.calls,[]);await p.button.onclick();p.choose(false);await run;assert.deepEqual(p.calls,[]);assert.equal(p.S.batch.id,'a');assert.equal(p.button.disabled,false);
});
test('actual discard targets approved original batch and rejects scope changed during confirmation',async()=>{
 const p=page(),run=p.button.onclick();p.choose(true);await run;assert.deepEqual(p.calls,['/api/import/batches/a/discard','reload']);
 const q=page(),pending=q.button.onclick();q.S.batch={id:'b'};q.choose(true);await pending;assert.deepEqual(q.calls,[]);assert.equal(q.button.disabled,false);
});
