'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');
const handler = html.slice(html.indexOf("$('#btnRefresh').onclick ="), html.indexOf("function selectView("));
async function click(job) {
  const button = {}, notices = [], calls = [];
  const context = vm.createContext({$: () => button, state: {currentProject: 'p'},
    api: async (url, body) => {calls.push([url, body]); return url === '/api/refresh' ? {id: 'job-1'} : job;},
    toast: (message, kind) => notices.push([message, kind]), load: async () => {},
    setTimeout: callback => callback()});
  vm.runInContext(handler, context);
  await button.onclick();
  assert.equal(button.disabled, false);
  assert.equal(calls[0][1].project_id, 'p');
  return notices.at(-1);
}
test('refresh messages preserve changed, busy, failure and incomplete job states', async () => {
  for (const [job, match] of [
    [{state:'done', result:{reason_code:'route_recall_changed', errors:[{kind:'changed'}]}}, /学习图已变化/],
    [{state:'done', result:{reason_code:'refresh_running', errors:[{kind:'busy'}]}}, /已有抓取在运行/],
    [{state:'done', result:{added:2, errors:[{kind:'network_error'}]}}, /部分查询未完成/],
    [{state:'failed', error:'fixture failure'}, /抓取失败/],
    [{state:'running'}, /仍在进行/]]) {
    const [message, kind] = await click(job);
    assert.match(message, match); assert.notEqual(kind, 'ok');
    assert.doesNotMatch(message, /限流/);
  }
  assert.deepEqual(await click({state:'done',result:{added:2,errors:[]}}), ['新增 2 条','ok']);
});
