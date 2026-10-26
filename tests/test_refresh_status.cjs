'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');
const handler = html.slice(html.indexOf("$('#btnRefresh').onclick ="), html.indexOf("function selectView("));
const record = html.slice(html.indexOf('function fetchedText'), html.indexOf('function renderEligibility'));
const cnkiAfter = [];       // projects the 知网 part (ADR 0045) was started for after a manual refresh
async function click(job, {batchToday, label = '生成今日推荐'} = {}) {
  const button = {}, daily = {textContent: label}, notices = [], calls = [];
  cnkiAfter.length = 0;
  const context = vm.createContext({$: (s) => s === '#btnDaily' ? daily : button, state: {currentProject: 'p', maintenance: {batch_today: !!batchToday}},
    api: async (url, body) => {calls.push([url, body]); return url === '/api/refresh' ? {id: 'job-1'} : job;},
    toast: (message, kind) => notices.push([message, kind]), load: async () => {},
    cnkiRefresh: (projectId) => { cnkiAfter.push(projectId); },
    setTimeout: callback => callback()});
  vm.runInContext(record, context);
  vm.runInContext(handler, context);
  await button.onclick();
  assert.equal(button.disabled, false);
  assert.equal(calls[0][1].project_id, 'p');
  return notices.at(-1);
}
test('the 知网 part starts after a finished refresh, never while one runs or is already running', async () => {
  await click({state:'done', result:{fetched:3, new_to_project:1, errors:[]}});
  assert.deepEqual(cnkiAfter, ['p']);
  await click({state:'failed', error:'fixture failure'});
  assert.deepEqual(cnkiAfter, ['p']);               // the server's sources failing does not stop 知网
  await click({state:'running'});
  assert.deepEqual(cnkiAfter, []);
  await click({state:'done', result:{reason_code:'refresh_running', errors:[]}});
  assert.deepEqual(cnkiAfter, []);
});
test('refresh messages preserve changed, busy, failure and incomplete job states', async () => {
  for (const [job, match] of [
    [{state:'done', result:{reason_code:'route_recall_changed', errors:[{kind:'changed'}]}}, /学习图已变化/],
    [{state:'done', result:{reason_code:'refresh_running', errors:[{kind:'busy'}]}}, /已有抓取在运行/],
    [{state:'done', result:{fetched:2, new_to_project:1, errors:[{kind:'network_error'}]}}, /部分查询未完成/],
    [{state:'failed', error:'fixture failure'}, /抓取失败/],
    [{state:'running'}, /仍在进行/]]) {
    const [message, kind] = await click(job);
    assert.match(message, match); assert.notEqual(kind, 'ok');
    assert.doesNotMatch(message, /限流/);
  }
  assert.deepEqual(await click({state:'done',result:{fetched:33,added:2,new_to_project:10,errors:[]}}), ['抓到 33 篇，新 10 篇','ok']);
});
test('a refresh that found nothing new still says how many it fetched', async () => {
  assert.deepEqual(await click({state:'done',result:{fetched:33,added:0,new_to_project:0,errors:[]}}), ['抓到 33 篇，没有新论文','ok']);
  const [message, kind] = await click({state:'done',result:{fetched:3,new_to_project:0,errors:[{kind:'network_error'}]}});
  assert.equal(message, '抓到 3 篇，没有新论文，部分查询未完成'); assert.equal(kind, 'warn');
});
function render(m) {
  const els = {'#maintainNote': {textContent: ''}, '#refreshRecord': {hidden: true, textContent: ''}};
  const context = vm.createContext({$: (s) => els[s]});
  vm.runInContext(record, context);
  context.renderMaintenance(m);
  return els;
}
test('the line under the fetch button shows the last successful fetch, local time, and hides without a record', () => {
  const at = new Date(2026, 9, 23, 18, 44).toISOString();
  let els = render({last_refresh_result: {at, fetched: 33, new_to_project: 10}});
  assert.equal(els['#refreshRecord'].hidden, false);
  assert.equal(els['#refreshRecord'].textContent, '最近抓取 10-23 18:44 · 抓到 33 篇，新 10 篇');
  els = render({last_refresh_result: {at: new Date(2026, 0, 5, 7, 5).toISOString(), fetched: 33, new_to_project: 0}});
  assert.equal(els['#refreshRecord'].textContent, '最近抓取 01-05 07:05 · 抓到 33 篇，没有新论文');
  for (const m of [{last_refresh_result: null}, {}, {last_refresh_result: {at: 'garbled', fetched: 1, new_to_project: 1}}]) {
    els = render(m);
    assert.equal(els['#refreshRecord'].hidden, true); assert.equal(els['#refreshRecord'].textContent, '');
  }
});
test('a failure note is one plain sentence per reason, never the request or the provider text', () => {
  assert.equal(render({last_error: 'unavailable'})['#maintainNote'].textContent, '论文来源暂时限流，稍后会自动再试');
  assert.equal(render({last_error: 'network_error'})['#maintainNote'].textContent, '连不上论文来源，请检查网络');
  const raw = render({last_error: 'OpenAlex fetch failed: https://api.openalex.org/works?mailto=owner%40example.invalid: HTTP Error 429'});
  assert.equal(raw['#maintainNote'].textContent, '上次抓取没有完成，稍后会自动再试');
});
test('a failure note and the success record are independent', () => {
  const els = render({last_error: 'busy', last_refresh_result: {at: new Date(2026, 9, 23, 9, 0).toISOString(), fetched: 4, new_to_project: 1}});
  assert.equal(els['#maintainNote'].textContent, '上次抓取没有完成，稍后会自动再试');   // an old raw record gets the general sentence
  assert.match(els['#refreshRecord'].textContent, /^最近抓取 10-23 09:00/);
});

test('after a manual fetch with new papers and a batch already made today, the toast points at the button by its current label', async () => {
  const done = {state:'done',result:{fetched:33,new_to_project:10,new_recommendable:4,errors:[]}};
  assert.deepEqual(await click(done, {batchToday: true}), ['抓到 33 篇，新 10 篇，点「生成今日推荐」查看','ok']);
  assert.deepEqual(await click(done, {batchToday: true, label: '生成今日发现'}), ['抓到 33 篇，新 10 篇，点「生成今日发现」查看','ok']);
  assert.deepEqual(await click(done, {batchToday: false}), ['抓到 33 篇，新 10 篇','ok']);
  assert.deepEqual(await click({state:'done',result:{fetched:33,new_to_project:0,errors:[]}}, {batchToday: true}), ['抓到 33 篇，没有新论文','ok']);
  // new links that the next batch could not show (no PDF, other language, outside the time window) promise nothing
  assert.deepEqual(await click({state:'done',result:{fetched:33,new_to_project:10,new_recommendable:0,errors:[]}}, {batchToday: true}), ['抓到 33 篇，新 10 篇','ok']);
  const [message, kind] = await click({state:'done',result:{fetched:3,new_to_project:1,new_recommendable:1,errors:[{kind:'network_error'}]}}, {batchToday: true});
  assert.equal(message, '抓到 3 篇，新 1 篇，点「生成今日推荐」查看，部分查询未完成'); assert.equal(kind, 'warn');
});
test('a manual fetch with every source switched off says so instead of reporting 0 papers', async () => {
  const [message, kind] = await click({state:'done',result:{fetched:0,added:0,new_to_project:0,errors:[],reason_code:'sources_disabled'}});
  assert.equal(message, '数据源都已关闭'); assert.equal(kind, 'warn');
});
test('the line shows the year only when the record is not from this year', () => {
  const old = new Date(new Date().getFullYear() - 1, 11, 30, 18, 44).toISOString();
  const els = render({last_refresh_result: {at: old, fetched: 3, new_to_project: 1}});
  assert.equal(els['#refreshRecord'].textContent, `最近抓取 ${new Date(old).getFullYear()}-12-30 18:44 · 抓到 3 篇，新 1 篇`);
});
