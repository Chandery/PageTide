'use strict';
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/static/update-banner.js'), 'utf8');

function page(routes) {
  const el = () => ({hidden: true, textContent: '', title: '', disabled: false, onclick: null});
  const nodes = {updateBar: el(), updateLabel: el(), updateAct: el(), updateClose: el()};
  const calls = [], quits = [];
  const context = {window: {}, document: {getElementById: id => nodes[id]}};
  vm.createContext(context); vm.runInContext(source, context);
  const fetchFn = async (url, init) => {
    calls.push({url, method: init?.method || 'GET', body: init?.body && JSON.parse(init.body)});
    const route = routes[`${init?.method || 'GET'} ${url}`];
    const value = typeof route === 'function' ? route() : route;
    return {ok: value?.status ? value.status < 400 : true, json: async () => value?.body ?? value};
  };
  const mounted = context.window.PDHUpdate.mount({document: context.document, fetch: fetchFn, wait: async () => {}, quit: async () => { quits.push(1); }});
  return {nodes, calls, quits, mounted};
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('no strip when nothing is available, dismissed, or the check failed', async () => {
  for (const reply of [{available: false}, {available: true, latest: '0.2.0', dismissed: true}, {status: 'unknown', available: false}]) {
    const p = page({'GET /api/update': reply}); await flush();
    assert.equal(p.nodes.updateBar.hidden, true);
  }
  const broken = page({'GET /api/update': () => { throw new Error('offline'); }}); await flush();
  assert.equal(broken.nodes.updateBar.hidden, true);
});

test('a newer version shows its name and an update button; close remembers the version', async () => {
  const p = page({'GET /api/update': {available: true, latest: '0.2.0', dismissed: false, notes: 'n'}, 'POST /api/update/dismiss': {ok: true}});
  await flush();
  assert.equal(p.nodes.updateBar.hidden, false);
  assert.equal(p.nodes.updateLabel.textContent, '有新版本 v0.2.0');
  assert.equal(p.nodes.updateAct.textContent, '更新');
  await p.nodes.updateClose.onclick();
  assert.equal(p.nodes.updateBar.hidden, true);
  assert.deepEqual(p.calls.pop().body, {version: '0.2.0'});
});

test('update downloads, applies, then asks the page to quit (its draft guard)', async () => {
  let polls = 0;
  const p = page({
    'GET /api/update': {available: true, latest: '0.2.0'},
    'POST /api/update/download': {state: 'downloading', received: 1, total: 4},
    'GET /api/update/download': () => (++polls < 2 ? {state: 'downloading', received: 2, total: 4} : {state: 'ready'}),
    'POST /api/update/apply': {mode: 'installer'},
  });
  await flush(); await p.nodes.updateAct.onclick();
  assert.equal(p.nodes.updateLabel.textContent, '应用将关闭以完成安装');
  assert.equal(p.quits.length, 1);
  assert.deepEqual(p.calls.map(c => c.url).slice(1, 3), ['/api/update/download', '/api/update/download']);
});

test('macOS manual fallback does not quit; a failure shows retry and keeps the app open', async () => {
  const manual = page({'GET /api/update': {available: true, latest: '0.2.0'}, 'POST /api/update/download': {state: 'ready'}, 'POST /api/update/apply': {mode: 'manual'}});
  await flush(); await manual.nodes.updateAct.onclick();
  assert.equal(manual.quits.length, 0);
  assert.match(manual.nodes.updateLabel.textContent, /访达/);
  const failing = page({'GET /api/update': {available: true, latest: '0.2.0'}, 'POST /api/update/download': {state: 'error', message: '校验失败，已删除下载的文件'}});
  await flush(); await failing.nodes.updateAct.onclick();
  assert.equal(failing.quits.length, 0);
  assert.equal(failing.nodes.updateLabel.textContent, '更新失败：校验失败，已删除下载的文件');
  assert.equal(failing.nodes.updateAct.textContent, '重试');
  assert.equal(failing.nodes.updateAct.hidden, false);
});
