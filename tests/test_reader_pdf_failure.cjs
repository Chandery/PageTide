'use strict';
// Reader: what is shown when no PDF could be fetched. One short reason, up to three page buttons (the first is primary),
// one control to pick a PDF, and the whole area accepts a dropped PDF. No explanatory text.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
const failure=source.slice(source.indexOf('function showPdfFailure('),source.indexOf('async function openReader('));
const esc=source.split('\n').find(line=>line.startsWith('const esc ='));
const reasons=source.slice(source.indexOf('const PDF_REASONS = {'),source.indexOf('// No PDF could be fetched'));
const PAGES=[
  {kind:'source_page',label:'百度学术',url:'https://xueshu.baidu.com/usercenter/paper/show?paperid=p1',needs_login:true},
  {kind:'landing',label:'原文页面',url:'https://repo.example.org/kg',needs_login:false},
  {kind:'publisher_page',label:'出版方',url:'https://doi.org/10.1234/kg',needs_login:true},
];
function setup({late=false,uploadStatus=200}={}){
  const input={files:[]},note={textContent:''},calls=[],opened=[];let current=true;
  const box={innerHTML:'',classList:{add(){},remove(){},toggle(){}},querySelector:q=>q.includes('input')?input:note};
  const ctx={encodeURIComponent,
    api:async(url,body)=>{calls.push(['api',url,body]);return {ok:true};},
    fetch:async(url,init)=>{calls.push(['fetch',url,init.headers['X-Filename']]);if(late)current=false;
      return {ok:uploadStatus===200,status:uploadStatus,json:async()=>uploadStatus===200?{pdf_id:'public-id'}:{error:'bad file'}};},
    openReader:(...a)=>opened.push(a),console};
  vm.createContext(ctx);vm.runInContext(esc+'\n'+reasons+'\n'+failure,ctx);
  const show=result=>ctx.showPdfFailure(box,'k1','Title',result,'proj',()=>current);
  return {box,input,note,calls,opened,show,ctx};
}
const drop=files=>({preventDefault(){this.prevented=true;},dataTransfer:{files}});
const file=(name,type='application/pdf')=>({name,type});

test('a source page is named after its source: 知网 says where it opens, never "百度学术"',()=>{
  const p=setup();
  p.show({ok:false,reason:'landing_page_only',pages:[{kind:'source_page',label:'知网',url:'https://kns.cnki.net/kcms2/article/abstract?v=x',needs_login:true}]});
  assert.match(p.box.innerHTML,/>在知网打开<\/a>/);assert.doesNotMatch(p.box.innerHTML,/百度学术/);
  p.show({ok:false,reason:'landing_page_only',pages:[{kind:'source_page',label:'某来源',url:'https://x.example/p',needs_login:true}]});
  assert.match(p.box.innerHTML,/>来源页面<\/a>/);
});
test('one reason line, up to three page buttons with the first primary, one file control',()=>{
  const p=setup();p.show({ok:false,reason:'landing_page_only',pages:PAGES});
  const html=p.box.innerHTML;
  assert.match(html,/这篇的 PDF 在原文页面上：打开原文页下载，再拖到这里。/);
  const links=[...html.matchAll(/<a class="([^"]*)" href="([^"]*)"[^>]*>([^<]*)<\/a>/g)];
  assert.deepEqual(links.map(m=>m[3]),['百度学术','原文页面','出版方']);
  assert.deepEqual(links.map(m=>m[2]),PAGES.map(x=>x.url));
  assert.match(links[0][1],/\bprimary\b/);assert.doesNotMatch(links[1][1],/primary/);assert.doesNotMatch(links[2][1],/primary/);
  for(const m of html.matchAll(/<a [^>]*>/g)){assert.match(m[0],/target="_blank"/);assert.match(m[0],/rel="noreferrer"/);}
  assert.match(html,/选择或拖入 PDF/);assert.equal((html.match(/<input type="file"/g)||[]).length,1);
  assert.doesNotMatch(html,/附加本地 PDF/);
  assert.ok(html.length<1500,'no explanatory text');
});
test('labels follow the page kind, not the server text, and at most three buttons',()=>{
  const p=setup();p.show({reason:'landing_page_only',pages:[...PAGES,{kind:'landing',label:'x',url:'https://a.example/4'},{kind:'source_page',label:'<b>',url:'https://a.example/5'}]});
  assert.equal((p.box.innerHTML.match(/<a /g)||[]).length,3);
  const q=setup();q.show({reason:'landing_page_only',pages:[{kind:'landing',label:'<script>alert(1)</script>',url:'https://a.example/1'}]});
  assert.doesNotMatch(q.box.innerHTML,/<script>/);assert.match(q.box.innerHTML,/>原文页面</);
});
test('only https page links are offered and every value is escaped',()=>{
  const p=setup();p.show({reason:'landing_page_only',pages:[{kind:'landing',url:'javascript:alert(1)'},{kind:'landing',url:'http://a.example/x'},
    {kind:'landing',url:'https://a.example/x?"onmouseover="alert(1)'},{kind:'source_page'},'junk',null]});
  const html=p.box.innerHTML;
  assert.doesNotMatch(html,/javascript:|http:\/\/a\.example/);
  assert.equal((html.match(/<a /g)||[]).length,1);assert.doesNotMatch(html,/href="[^"]*"onmouseover/);assert.match(html,/&quot;/);
});
test('an older answer with only a landing page still gets one page button, and no pages means only the file control',()=>{
  const p=setup();p.show({reason:'landing_page_only',landing_page:'https://repo.example.org/p'});
  assert.deepEqual([...p.box.innerHTML.matchAll(/<a [^>]*href="([^"]*)"/g)].map(m=>m[1]),['https://repo.example.org/p']);
  const q=setup();q.show({reason:'no_oa_source'});assert.equal((q.box.innerHTML.match(/<a /g)||[]).length,0);assert.match(q.box.innerHTML,/没有找到可下载的 PDF 来源。/);
  assert.match(q.box.innerHTML,/选择或拖入 PDF/);
});
test('the file control uploads, attaches and reopens the paper',async()=>{
  const p=setup();p.show({reason:'no_oa_source'});p.input.files=[file('a.pdf')];await p.input.onchange();
  assert.deepEqual(p.calls.map(c=>c[0]+':'+c[1]),['fetch:/api/seeds/pdf','api:/api/pdf/attach']);
  assert.deepEqual(JSON.parse(JSON.stringify(p.calls[1][2])),{key:'k1',pdf_id:'public-id'});assert.deepEqual(p.opened,[['k1','Title','proj']]);
});
test('dropping a PDF anywhere on the area does the same: upload, attach, reopen',async()=>{
  const p=setup();p.show({reason:'no_oa_source'});
  assert.equal(typeof p.box.ondragover,'function');assert.equal(typeof p.box.ondrop,'function');
  const over=drop([file('a.pdf')]);p.box.ondragover(over);assert.equal(over.prevented,true);
  const event=drop([file('dropped paper.pdf')]);await p.box.ondrop(event);
  assert.equal(event.prevented,true);
  assert.deepEqual(p.calls.map(c=>c[0]+':'+c[1]),['fetch:/api/seeds/pdf','api:/api/pdf/attach']);
  assert.equal(p.calls[0][2],encodeURIComponent('dropped paper.pdf'));
  assert.deepEqual(p.opened,[['k1','Title','proj']]);
});
test('a dropped file that is not a PDF is refused without any request',async()=>{
  const p=setup();p.show({reason:'no_oa_source'});
  await p.box.ondrop(drop([file('notes.txt','text/plain')]));
  assert.deepEqual(p.calls,[]);assert.match(p.note.textContent,/PDF/);
  const empty=drop([]);await p.box.ondrop(empty);assert.equal(empty.prevented,true);assert.deepEqual(p.calls,[]);
  const noTransfer={preventDefault(){}};await p.box.ondrop(noTransfer);assert.deepEqual(p.calls,[]);
});
test('a PDF with an upper-case extension and no type is accepted',async()=>{
  const p=setup();p.show({reason:'no_oa_source'});await p.box.ondrop(drop([file('SCAN.PDF','')]));
  assert.equal(p.calls[0][0],'fetch');
});
test('a failed upload is reported beside the control and nothing is attached',async()=>{
  const p=setup({uploadStatus:400});p.show({reason:'no_oa_source'});await p.box.ondrop(drop([file('a.pdf')]));
  assert.deepEqual(p.calls.map(c=>c[0]),['fetch']);assert.match(p.note.textContent,/附加失败/);assert.deepEqual(p.opened,[]);
});
test('a late reply for another paper does not reopen anything, for a drop as for the control',async()=>{
  const p=setup({late:true});p.show({reason:'no_oa_source'});await p.box.ondrop(drop([file('a.pdf')]));
  assert.deepEqual(p.opened,[]);assert.deepEqual(p.calls.map(c=>c[0]),['fetch']);
});
test('opening the reader clears the drop handlers of an earlier failure',()=>{
  const open=source.slice(source.indexOf('async function openReader('),source.indexOf('async function openReader(')+1500);
  assert.match(open,/box\.ondragover\s*=\s*box\.ondrop\s*=\s*null/);
});
