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
  vm.runInContext("const DEMO_ID = 'pdh-demo'; const inDemo = () => state.currentProject === DEMO_ID;", context);
  vm.runInContext("let demoBlockedAt = 0; function toast(m, kind) { if (kind !== 'ok' && kind !== 'ai' && Date.now() - demoBlockedAt < 2500) return; TOASTS.push([m, kind]); }", Object.assign(context, { TOASTS: toasts }));
  vm.runInContext(slice('// While the guided tour shows the demo project', 'function mdInline'), context);
  vm.runInContext(slice('function rememberProject', 'async function loadProjects'), context);
  return { context, store, fetches, toasts };
}
const ok = data => ({ ok: true, status: 200, json: async () => data });

test('api() asks for the demo (header) only while the current project is the demo', async () => {
  const p = page('pdh-demo', () => ok({}));
  await vm.runInContext("api('/api/home')", p.context);
  await vm.runInContext("api('/api/daily', {project_id: 'pdh-demo'})", p.context);
  assert.equal(p.fetches[0].opts.headers['X-PDH-Demo'], '1');
  assert.equal(p.fetches[1].opts.headers['X-PDH-Demo'], '1');
  assert.equal(p.fetches[1].opts.headers['Content-Type'], 'application/json');
  const real = page('real-1', () => ok({}));
  await vm.runInContext("api('/api/home')", real.context);
  await vm.runInContext("api('/api/daily', {})", real.context);
  for (const f of real.fetches) assert.equal(JSON.stringify(f.opts.headers || {}).includes('X-PDH-Demo'), false);
});

test('a demo_readonly 403 shows the server message once and still rejects', async () => {
  const message = '演示项目里不能这样做。创建自己的项目后可用。';
  const p = page('pdh-demo', () => ({ ok: false, status: 403, json: async () => ({ error: message, reason_code: 'demo_readonly' }) }));
  await assert.rejects(vm.runInContext("api('/api/refresh', {})", p.context), { message });
  vm.runInContext("toast('抓取失败：x', 'err')", p.context);   // the caller's own error toast is suppressed
  assert.equal(JSON.stringify(p.toasts), JSON.stringify([[message, 'warn']]));
});

test('the demo id is never written to localStorage', () => {
  const p = page('pdh-demo', () => ok({}));
  vm.runInContext("rememberProject('pdh-demo'); rememberProject('p7')", p.context);
  assert.equal(JSON.stringify(p.store), JSON.stringify({ 'pdh-current-project': 'p7' }));
  // Every write goes through rememberProject, which refuses the demo id.
  const writes = index.match(/localStorage\.setItem\('pdh-current-project'/g) || [];
  assert.equal(writes.length, 1);
});

test('an AI preview written by the demo is labelled 演示, a real one is not', () => {
  const ctx = vm.createContext({ state: { aiFailures: {}, triaging: false, triagingKeys: new Set(), currentProject: 'pdh-demo' }, esc: s => String(s) });
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
  assert.ok(start.indexOf('await load()') < start.indexOf("PDHTour.boot('index'"), 'the tour is drawn after the page has its data');
  assert.match(start, /requested !== DEMO_ID/);
});

test('demo mode skips automatic upkeep and forces the AI preview on', () => {
  assert.match(slice('async function autoMaintain()', "const key = state.currentProject || 'default'"), /if \(inDemo\(\)\) return;/);
  assert.match(slice('async function load()', 'const banner'), /if \(autoAi && inDemo\(\)\) autoAi\.checked = true;/);
  assert.match(index, /html\.pdh-demo #btnRefresh[^{]*#refreshRecord[^{]*#pet/);
  assert.match(index, /html\.pdh-demo[^{]*\.ai-action[^{]*\.read-action/);
});

test('the edit link only explains itself in the demo', () => {
  assert.match(index, /演示项目不能修改，创建自己的项目后在这里自定义/);
  assert.match(slice("$('#projectEdit').addEventListener", 'let tourLeaveTo'), /if \(!inDemo\(\)\) return;\s*e\.preventDefault\(\)/);
});

test('every page of the tour loads tour.js and boots its own step', () => {
  assert.match(index, /<script src="\/tour\.js"><\/script>/);
  assert.match(index, /PDHTour\.boot\('index'/);
  assert.match(read('settings.html'), /PDHTour\.boot\('settings'/);
  assert.match(read('weekly_report.html'), /PDHTour\.boot\('weekly'/);
  assert.match(read('project_creation.html'), /PDHTour\.boot\('creation'/);
  for (const f of ['index.html', 'settings.html', 'weekly_report.html', 'project_creation.html']) assert.match(read(f), /<link rel="stylesheet" href="\/tour\.css">/, f);
});

test('settings replays the tour from a fresh sandbox; the creation page offers the demo when there is no project', () => {
  const settings = read('settings.html');
  assert.match(settings, /id="replayTourBtn"[^>]*>重新查看</);
  assert.match(settings, /action:'start'[\s\S]*PDHTour\.begin\(\{[\s\S]*?returnProject[\s\S]*window\.location\.href='\/'/);
  const creation = read('project_creation.html');
  assert.match(creation, /link\.textContent='看看演示'/);
  assert.match(creation, /action:'start'[\s\S]*PDHTour\.begin\(\{version:[\s\S]*?returnProject:null\}\)/);
});

test('the weekly link of the profile carries the project id, so the demo report is routed by id', () => {
  assert.match(read('profile-ui.js'), /weekly_report\.html\?project_id=\$\{encodeURIComponent\(project\)\}/);
});
