'use strict';
// The reader's 外部打开 (was 浏览器打开, which did nothing in the desktop app: window.open of the app's own PDF address is
// refused there, and a browser could not open it without the app's session). The desktop app hands the PDF file to the
// system's default PDF app; a source run in a browser still opens a tab.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
const handler=source.slice(source.indexOf("$('#readerNative').onclick"),source.indexOf('};',source.indexOf("$('#readerNative').onclick"))+2);
function run({tauri,R}){
  const calls=[],opened=[],toasts=[],button={};
  const ctx={$:()=>button,R,window:{...(tauri?{__TAURI_INTERNALS__:{invoke:async(cmd,args)=>{calls.push([cmd,args]);if(tauri==='fail')throw 'denied';}}}:{}),open:(u,t)=>opened.push([u,t])},
    toast:(m)=>toasts.push(m)};
  ctx.window.open=(u,t)=>opened.push([u,t]);
  vm.createContext(ctx);vm.runInContext(handler.replace(/window\.open\(/g,'window.open('),ctx);
  return {button,calls,opened,toasts};
}
test('the desktop app opens the PDF file itself in the default PDF app',async()=>{
  const r=run({tauri:true,R:{path:'/data/pdfs/a.pdf',url:'/api/pdf/view?key=a'}});
  await r.button.onclick();
  assert.equal(JSON.stringify(r.calls),JSON.stringify([['open_pdf_file',{path:'/data/pdfs/a.pdf'}]]));
  assert.equal(r.opened.length,0);
});
test('a failure says so; a browser run opens a tab as before',async()=>{
  const f=run({tauri:'fail',R:{path:'/data/pdfs/a.pdf',url:'/u'}});await f.button.onclick();
  assert.match(f.toasts[0],/没能打开/);
  const b=run({tauri:false,R:{path:null,url:'/api/pdf/view?key=a'}});await b.button.onclick();
  assert.equal(JSON.stringify(b.opened),JSON.stringify([['/api/pdf/view?key=a','_blank']]));
});
test('the label says what it does and the path is reset for each paper',()=>{
  assert.match(source,/id="readerNative">外部打开</);
  assert.match(source,/R\.sha256 = null; R\.path = null;/);
});
