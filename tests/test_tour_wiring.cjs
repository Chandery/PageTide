'use strict';
// How the pages are wired to the first-run tour, checked on the page source (no browser here; the real check is a browser run).
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const read = f => fs.readFileSync(path.join(__dirname, '../app/static', f), 'utf8');
const index = read('index.html');

function slice(from, to) { return index.slice(index.indexOf(from), index.indexOf(to, index.indexOf(from))); }

function page(currentProject, respond) {
  const store = {}, fetches = [], toasts = [];
  const context = vm.createContext({
    state: { currentProject, projects: [], realProjects: [], demo: null },
    localStorage: { setItem: (k, v) => { store[k] = v; }, getItem: k => store[k] },
    fetch: async (url, opts) => { fetches.push({ url, opts }); return respond(url, opts); },
    document: { getElementById: () => null },
    Date,
  });
  vm.runInContext("const DEMO_ID = 'pt-demo'; const inDemo = () => state.currentProject === DEMO_ID;", context);
  vm.runInContext(slice('let demoBlocked = null;', 'function toast('), context);
  vm.runInContext("function toast(m, kind) { if (suppressDemoDuplicate(m, kind)) return; TOASTS.push([m, kind]); }", Object.assign(context, { TOASTS: toasts }));
  vm.runInContext(slice('// While the guided tour shows the demo project', 'function mdInline'), context);
  vm.runInContext(slice('function rememberProject', 'async function loadProjects'), context);
  return { context, store, fetches, toasts };
}
const ok = data => ({ ok: true, status: 200, json: async () => data });

test('api() asks for the demo (header) only while the current project is the demo', async () => {
  const p = page('pt-demo', () => ok({}));
  await vm.runInContext("api('/api/home')", p.context);
  await vm.runInContext("api('/api/daily', {project_id: 'pt-demo'})", p.context);
  assert.equal(p.fetches[0].opts.headers['X-PT-Demo'], '1');
  assert.equal(p.fetches[1].opts.headers['X-PT-Demo'], '1');
  assert.equal(p.fetches[1].opts.headers['Content-Type'], 'application/json');
  const real = page('real-1', () => ok({}));
  await vm.runInContext("api('/api/home')", real.context);
  await vm.runInContext("api('/api/daily', {})", real.context);
  for (const f of real.fetches) assert.equal(JSON.stringify(f.opts.headers || {}).includes('X-PT-Demo'), false);
});

test('a demo_readonly 403 shows the server message once and still rejects', async () => {
  const message = '演示项目里不能这样做。创建自己的项目后可用。';
  const p = page('pt-demo', () => ({ ok: false, status: 403, json: async () => ({ error: message, reason_code: 'demo_readonly' }) }));
  await assert.rejects(vm.runInContext("api('/api/refresh', {})", p.context), { message });
  vm.runInContext("toast('抓取失败：' + " + JSON.stringify(message) + ", 'err')", p.context);   // the caller's own copy of that error is dropped
  assert.equal(JSON.stringify(p.toasts), JSON.stringify([[message, 'warn']]));
  // ...but only that one: a later unrelated error, or a second copy, is shown
  vm.runInContext("toast('别的错误', 'err'); toast('抓取失败：' + " + JSON.stringify(message) + ", 'err')", p.context);
  assert.equal(p.toasts.length, 3);
});

test('the demo id is never written to localStorage', () => {
  const p = page('pt-demo', () => ok({}));
  vm.runInContext("rememberProject('pt-demo'); rememberProject('p7')", p.context);
  assert.equal(JSON.stringify(p.store), JSON.stringify({ 'pt-current-project': 'p7' }));
  // Every write goes through rememberProject, which refuses the demo id.
  const writes = index.match(/localStorage\.setItem\('pt-current-project'/g) || [];
  assert.equal(writes.length, 1);
});

test('an AI preview written by the demo is labelled 演示, a real one is not', () => {
  const ctx = vm.createContext({ state: { aiFailures: {}, triaging: false, triagingKeys: new Set(), currentProject: 'pt-demo' }, esc: s => String(s) });
  vm.runInContext(slice('function aiSlot(c)', '// The learning map:'), ctx);
  const demo = vm.runInContext("aiSlot({key:'k', summary:{one_liner:'x', model:'demo'}})", ctx);
  assert.match(demo, /<b>AI 速览 · 演示<\/b>/);
  const real = vm.runInContext("aiSlot({key:'k', summary:{one_liner:'x', model:'deepseek-chat'}})", ctx);
  assert.match(real, /<b>AI 速览<\/b>/);
});

test('start-up: no real project and no tour sends the person to the creation page; the tour is offered first', () => {
  const start = slice('// Load projects first, then decide on the tour', '// Cross-script bridge');
  const offer = start.indexOf('shouldOffer');
  const redirect = start.indexOf("window.location.replace('/project_creation.html')");
  assert.ok(offer > 0 && redirect > offer, 'offer is decided before the redirect');
  assert.match(start, /!state\.realProjects\.length\) \{ window\.location\.replace\('\/project_creation\.html'\)/);
  assert.match(start, /returnProject: state\.realProjects\.length \? state\.currentProject : null/);
  assert.ok(start.indexOf('state.currentProject = DEMO_ID') < start.indexOf('await load()'), 'the demo is current before the first load');
  assert.ok(start.indexOf('await load()') < start.indexOf("PTTour.boot('index'"), 'the tour is drawn after the page has its data');
  assert.match(start, /requested !== DEMO_ID/);
});

test('demo mode skips automatic upkeep and forces the AI preview on', () => {
  assert.match(slice('async function autoMaintain()', "const key = state.currentProject || 'default'"), /if \(inDemo\(\)\) return;/);
  assert.match(slice('async function load()', 'const banner'), /if \(autoAi && inDemo\(\)\) autoAi\.checked = true;/);
  assert.match(index, /html\.pt-demo #btnRefresh[^{]*#refreshRecord/);
  assert.match(index, /html\.pt-demo[^{]*\.ai-action/);
});

test('in the demo reading is on for the one paper with reading material, and nothing else about it shows', () => {
  const rule = index.slice(index.indexOf('Reading is on for the one paper'));
  assert.match(rule, /html\.pt-demo \.read-action:not\(\[data-read="https:\/\/doi\.org\/10\.48550\/arxiv\.1706\.03762"\]\)/);
  assert.match(rule, /html\.pt-demo #dRead:not\(\[data-key="https:\/\/doi\.org\/10\.48550\/arxiv\.1706\.03762"\]\)/);
  assert.match(rule, /html\.pt-demo #petImg[^{]*#petPanel \.switch[^{]*#petLog \.msg\.sys \.fol[^{]*\{ display:none/);
  assert.match(index, /id="dRead" data-key="\$\{esc\(d\.key\)\}"/);
  // pdf.js fetches the PDF without the demo header: the address names the demo project instead
  assert.match(index, /\/api\/pdf\/view\?key=\$\{encodeURIComponent\(key\)\}` \+ \(project === 'pt-demo' \? '&project_id=pt-demo' : ''\)/);
  // the attach-a-PDF control of the failure panel would write to the real library: not drawn for the demo
  assert.match(index, /\$\{project === 'pt-demo' \? '' : '<label class="btn tiny">选择或拖入 PDF/);
  // the demo question is filled in when 追问 is pressed, answers and translations are marked
  assert.match(index, /currentProject === 'pt-demo' && !\$\('#petInput'\)\.value\.trim\(\)\) \{ \$\('#petInput'\)\.value = window\.PTi18n\?\.exact\?\.\('这句话是什么意思？'\)/);
  assert.match(index, /const meta = r\.demo \? \['演示 · 预先写好的回答'\]/);
  assert.match(index, /r\.demo \? '划词翻译 · 演示' : '划词翻译'/);
});

test('the import page: the demo header on every request, the sample file, no pickers, and the tour boots there', () => {
  const imp = read('import.js'), html = read('import.html'), css = read('import.css');
  assert.match(imp, /const inDemo = projectId === DEMO_ID;/);
  assert.match(imp, /if \(inDemo\) options = \{\.\.\.options, headers: \{\.\.\.\(options\.headers \|\| \{\}\), 'X-PT-Demo': '1'\}\};/);
  assert.match(imp, /\(inDemo && demo && demo\.id === DEMO_ID \? demo : null\)/);
  assert.match(imp, /fetch\('\/demo\/sample-library\.bib'\)/);
  assert.match(imp, /\$\('#optOnline'\)\.checked = false;/);
  assert.match(html, /id="demoSample" hidden/); assert.match(html, /<link rel="stylesheet" href="\/tour\.css">/);
  assert.match(html, /<script src="\/tour\.js"><\/script>\s*<script>PTTour\.boot\('import',\{\}\);<\/script>/);
  assert.match(css, /html\.pt-demo \.picker,html\.pt-demo #drop,html\.pt-demo \.zotero,html\.pt-demo #options,html\.pt-demo #seedsCard,html\.pt-demo #aiCard,html\.pt-demo #catsDone,html\.pt-demo \.row-actions input,html\.pt-demo \.row-actions \[data-act="lookup"\]\{display:none/);
});

test('the edit link only explains itself in the demo', () => {
  assert.match(index, /演示项目不能修改，创建自己的项目后在这里自定义/);
  assert.match(slice("$('#projectEdit').addEventListener", 'let tourLeaveTo'), /if \(!inDemo\(\)\) return;\s*e\.preventDefault\(\)/);
});

test('every page of the tour loads tour.js and boots its own step', () => {
  assert.match(index, /<script src="\/tour\.js"><\/script>/);
  assert.match(index, /PTTour\.boot\('index'/);
  assert.match(read('settings.html'), /PTTour\.boot\('settings'/);
  assert.match(read('weekly_report.html'), /PTTour\.boot\('weekly'/);
  assert.match(read('project_creation.html'), /PTTour\.boot\('creation'/);
  for (const f of ['index.html', 'settings.html', 'weekly_report.html', 'project_creation.html']) assert.match(read(f), /<link rel="stylesheet" href="\/tour\.css">/, f);
});

test('settings replays the tour from the welcome card (the sandbox is built there); the creation page offers the demo when there is no project', () => {
  const settings = read('settings.html');
  assert.match(settings, /id="replayTourBtn"[^>]*>重新查看</);
  assert.match(settings, /PTTour\.begin\(\{step:'w0'[\s\S]*?returnProject[\s\S]*window\.location\.href='\/'/);
  assert.doesNotMatch(settings, /action:'start'/);
  const creation = read('project_creation.html');
  assert.match(creation, /link\.textContent='看看演示'/);
  assert.match(creation, /PTTour\.begin\(\{step:'w0',version:[\s\S]*?returnProject:null\}\)/);
});

test('the weekly link of the profile carries the project id, so the demo report is routed by id', () => {
  assert.match(read('profile-ui.js'), /weekly_report\.html\?project_id=\$\{encodeURIComponent\(project\)\}/);
});

test('the demo hides category editing, labels paraphrased abstracts in the library detail, and promises nothing it blocks', () => {
  const fs2 = require('node:fs'), path2 = require('node:path');
  const org = fs2.readFileSync(path2.join(__dirname, '..', 'app', 'static', 'organization.js'), 'utf8');
  const tour = fs2.readFileSync(path2.join(__dirname, '..', 'app', 'static', 'tour.js'), 'utf8');
  assert.match(index, /html\.pt-demo #organizationRoot \[data-action="membership"\], html\.pt-demo #organizationRoot \[data-action="paper-membership"\] \{ display:none/);
  assert.match(org, /inDemoPage\(\) && p\.arxiv_id[\s\S]{0,40}演示用的改写摘要，原文见 <a href="https:\/\/arxiv\.org\/abs\//);
  assert.doesNotMatch(tour, /钉住|撤销/);   // pinning is blocked in the demo, so the tour does not offer it
});
