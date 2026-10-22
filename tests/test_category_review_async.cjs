'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; }
const snap = revision => ({directions: [{id:'d',name:'Owner label'}],items:[],positions:{},projects:[{id:'p1',name:'One'},{id:'p2',name:'Two'}],revision});
const aiUnits = () => [{id:'c:d',kind:'category',section:'adjust',category:'d',action:'rename',name:'Research',reason:'Synthetic review',papers:0,requires:[]},
  {id:'p:fresh',kind:'paper',section:'classify',key:'fresh',from:[],to:['d'],fallback:false,reason:'Synthetic filing',requires:[]}];
const aiPreview = () => ({groups:[],ai_token:'old-token',fingerprint:'old-fingerprint',ai_units:aiUnits(),ai_plan:{categories:[{id:'d',action:'rename',name:'Research',reason:'Synthetic review'}],new_categories:[],papers:[{key:'fresh',categories:['d'],reason:'Synthetic filing'}]}});
const localPreview = () => ({groups:[],fingerprint:'old-fingerprint',merges:[{id:'m',target:'d',name:'Owner label',copies:[{id:'copy',name:'Alias'}],reason:'Synthetic review'}],moves:[]});

// Run the shipped function in a fresh VM. The fake DOM tracks view writes and lets
// the actual modal submit/close callbacks run; no network, store or model is used.
function fixture(api) {
  const writes = [], dialogs = [], toasts = [], nodes = new Map();
  function node(label) {
    let html = '', text = '';
    return {dataset:{},checked:true,disabled:false,hidden:false,listeners:{},
      get innerHTML() { return html; }, set innerHTML(value) { html = value; writes.push([label,'html',value]); },
      get textContent() { return text; }, set textContent(value) { text = value; writes.push([label,'text',value]); },
      classList:{add(){},remove(){},toggle(){},contains(){return false;}},setAttribute(){},
      querySelector(){return null;},querySelectorAll(){return [];},
      addEventListener(kind,fn){(this.listeners[kind] ||= []).push(fn);},focus(){},prepend(child){this.prepended = child;}};
  }
  function get(selector) { if (!nodes.has(selector)) nodes.set(selector,node(selector)); return nodes.get(selector); }
  const host = node('dialog-host');
  host.querySelector = () => dialogs.findLast(d => d.isConnected) || null;
  host.querySelectorAll = () => dialogs.filter(d => d.isConnected);
  Object.defineProperty(host,'innerHTML',{set(html){
    const children = new Map(), d = node('dialog'); d.html = html; d.isConnected = true;
    d.querySelector = selector => { if (!children.has(selector)) children.set(selector,node(`modal:${selector}`)); return children.get(selector); };
    const merge = node('merge'); merge.dataset.merge = 'm'; merge.querySelector = () => ({checked:true});
    const unitBoxes = aiUnits().map(u => { const box = node('unit'); box.dataset.unit = u.id; return box; });
    d.unitBoxes = unitBoxes;
    d.querySelectorAll = selector => selector === '[data-merge]' ? [merge] : selector === '[data-unit]' ? unitBoxes : [];
    d.showModal = () => {};
    d.remove = () => { d.isConnected = false; };
    d.close = () => { if (!d.isConnected) return; d.isConnected = false; for (const fn of d.listeners.close || []) fn(); };
    dialogs.push(d);
  }});
  const state = {currentProject:'p1'};
  const context = vm.createContext({module:{exports:{}},window:{PDH:{api,state,toast:(...args)=>toasts.push(args)},addEventListener(){}},document:{activeElement:null},
    localStorage:{getItem(){return null;},setItem(){}},crypto:{randomUUID:()=> 'synthetic-client'},setTimeout,clearTimeout,URL});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/organization.js'),'utf8'),context);
  const ui = context.module.exports;
  ui.S.root = {querySelector: selector => selector === '.org-dialog-host' ? host : get(selector),querySelectorAll:()=>[]};
  ui.S.scope = 'p1'; ui.S.snapshot = snap(1);
  return {ui,state,dialogs,writes,toasts};
}

for (const kind of ['scope','project','reset']) {
  test(`late initial AI preview is discarded after ${kind} change`, async () => {
    const response = deferred(), f = fixture(() => response.promise);
    const run = f.ui.suggest(); await tick();
    if (kind === 'reset') f.ui.reset();
    else if (kind === 'scope') f.ui.S.scope = 'p2';
    else f.state.currentProject = 'p2';
    const currentSnapshot = f.ui.S.snapshot;
    response.resolve({suggestions:aiPreview(),...snap(2)}); await run;
    assert.equal(f.dialogs.length,1,'a late response must not open a preview in the next view');
    assert.equal(f.ui.S.snapshot,currentSnapshot,'a late response must not replace the current snapshot');
    assert.equal(f.writes.some(([selector]) => selector === '.org-sidebar'),false);
    assert.equal(f.toasts.length,0);
  });
}

test('closing before the initial job ID arrives cancels that job and never opens its result', async () => {
  const response = deferred(), calls = [];
  const f = fixture((url,body) => {calls.push([url,body]); return body?.action === 'cancel-category-review' ? Promise.resolve({cancelled:true}) : response.promise;});
  const run = f.ui.suggest(); await tick();
  f.dialogs[0].close();
  response.resolve({job:{id:'late-job',state:'running'}}); await run;
  assert.equal(f.dialogs.length,1);
  assert.equal(calls.filter(([,body])=>body?.action === 'cancel-category-review').length,1);
  assert.equal(calls.find(([,body])=>body?.action === 'cancel-category-review')[1].job_id,'late-job');
  assert.equal(calls.some(([url])=>url.startsWith('/api/jobs/')),false);
});

test('AI failure modal keeps the real cause and offers explicit settings, retry and local actions', async () => {
  const calls = [];
  const f = fixture((url,body) => {
    calls.push([url,body]);
    return Promise.resolve({suggestions:{groups:[],source:'local',stored:false},
      ai_review:{status:'failed',error_code:'no_key',error:'还没有配置 DeepSeek key，请到设置页填写',
        total_papers:2,remaining_papers:2}});
  });
  await f.ui.suggest();
  const html = f.dialogs.at(-1).html;
  assert.match(html,/还没有配置 DeepSeek key/);
  assert.match(html,/href="\/settings.html"/);
  assert.match(html,/data-retry-review/);
  assert.match(html,/data-local-review/);
  assert.equal(calls.length,1,'recovery actions must never retry automatically');
});

test('failed asynchronous job shows recoverable inline cause rather than disappearing into a toast', async () => {
  const f = fixture(() => Promise.resolve({job:{id:'failed-job',state:'failed',error:'分类目录正被修改，请稍后重试'}}));
  await f.ui.suggest();
  const html = f.dialogs.at(-1).html;
  assert.match(html,/分类目录正被修改/);
  assert.match(html,/data-retry-review/);
  assert.equal(f.toasts.length,0);
});

test('local unclassified preview offers AI classification and manual category creation without a standing explanation', async () => {
  const f = fixture(() => Promise.resolve({suggestions:{groups:[],pending_keys:['new-paper'],
    pending_details:[{key:'new-paper',code:'insufficient_group'}],scope:'p1',source:'local'}}));
  await f.ui.suggest('local');
  const html = f.dialogs.at(-1).html;
  assert.match(html,/data-review-ai/);
  assert.match(html,/data-review-create/);
  assert.doesNotMatch(html,/本地检查至少需要两篇/);
});

test('clicking AI from an unclassified local preview dispatches one explicit AI review for the same scope', async () => {
  const calls = [];
  const f = fixture((url,body) => {
    calls.push([url,body]);
    return Promise.resolve(body.action === 'suggest' ? {suggestions:{groups:[],pending_keys:['a'],scope:'p1'}}
      : {suggestions:{groups:[],source:'local'},ai_review:{error:'AI 总开关已关闭',error_code:'ai_off'}});
  });
  await f.ui.suggest('local');
  assert.deepEqual(calls.map(([,body])=>body.action), ['suggest']);
  f.dialogs.at(-1).querySelector('[data-review-ai]').listeners.click[0](); await tick();
  assert.deepEqual(calls.map(([,body])=>body.action), ['suggest','review-categories']);
  assert.equal(calls[1][1].project_id,'p1');
  assert.equal(calls[1][1].scope,undefined);
});

test('clicking manual category creation opens the real editor without an AI or apply request', async () => {
  const calls=[];
  const f = fixture((url,body) => {calls.push([url,body]);return Promise.resolve({suggestions:{groups:[],pending_keys:['a'],scope:'p1'}});});
  await f.ui.suggest('local');
  f.dialogs.at(-1).querySelector('[data-review-create]').listeners.click[0](); await tick();
  assert.match(f.dialogs.at(-1).html,/新建类别/);
  assert.match(f.dialogs.at(-1).html,/name="name"/);
  assert.deepEqual(calls.map(([,body])=>body.action), ['suggest']);
});

test('failure retry only dispatches after clicking and stale recovery controls cannot change another scope', async () => {
  const calls=[];
  const f = fixture((url,body) => {calls.push([url,body]);return Promise.resolve({suggestions:{groups:[],source:'local'},ai_review:{error:'AI 总开关已关闭',error_code:'ai_off'}});});
  await f.ui.suggest();
  assert.equal(calls.length,1);
  f.dialogs.at(-1).querySelector('[data-retry-review]').listeners.click[0](); await tick();
  assert.equal(calls.length,2);
  const oldDialog=f.dialogs.at(-1); f.ui.S.scope='p2';
  oldDialog.querySelector('[data-local-review]').listeners.click[0](); await tick();
  assert.equal(calls.length,2);
});

for (const mode of ['ai','local']) for (const kind of ['scope','project','reset']) {
  test(`late ${mode} application preserves the next ${kind} view and its notice`, async () => {
    const application = deferred(), calls = [];
    const preview = mode === 'ai' ? aiPreview() : localPreview();
    const f = fixture((url,body) => {
      calls.push([url,body]);
      if (body?.action === 'apply-ai-review' || body?.action === 'apply-suggestions') return application.promise;
      return Promise.resolve({suggestions:preview});
    });
    await f.ui.suggest(mode);
    assert.equal(f.dialogs.length,2);
    const applying = f.dialogs[1].querySelector('form').onsubmit({preventDefault(){}}); await tick();
    assert.equal(calls.filter(([,body])=>body?.action === (mode === 'ai' ? 'apply-ai-review' : 'apply-suggestions')).length,1);
    if (kind === 'reset') f.ui.reset();
    else if (kind === 'scope') f.ui.S.scope = 'p2';
    else f.state.currentProject = 'p2';
    f.ui.S.snapshot = snap(9); f.ui.S.filter = 'd'; f.ui.S.notice = 'Current view notice';
    const currentSnapshot = f.ui.S.snapshot, writesBefore = f.writes.length;
    application.resolve({...snap(2),apply_result:{changed_papers:3,renamed_categories:1,merged_categories:1}}); await applying;
    assert.equal(f.ui.S.snapshot,currentSnapshot,'the old application response cannot replace a new view snapshot');
    assert.equal(f.ui.S.filter,'d'); assert.equal(f.ui.S.notice,'Current view notice');
    assert.equal(f.toasts.length,0,'the old application cannot announce success in a new view');
    const lateViewWrites = f.writes.slice(writesBefore).filter(([selector])=>!selector.startsWith('modal:') && selector !== '[data-status]');
    assert.deepEqual(lateViewWrites,[],'the old application cannot redraw the next view');
    assert.equal(f.ui.S.pending,0);
  });
}

test('applying an AI plan sends exactly the ticked units, not a whole-plan switch', async () => {
  const calls = [];
  const f = fixture((url, body) => { calls.push([url, body]);
    return Promise.resolve(body?.action === 'apply-ai-review' ? {...snap(2), apply_result:{classified_papers:1, changed_papers:1, still_unclassified:0}} : {suggestions:aiPreview()}); });
  await f.ui.suggest();
  const review = f.dialogs[1];
  review.unitBoxes[0].checked = false;   // the rename stays unticked
  await review.querySelector('form').onsubmit({preventDefault(){}}); await tick();
  const apply = calls.find(([,body]) => body?.action === 'apply-ai-review')[1];
  assert.deepEqual(JSON.parse(JSON.stringify(apply.selection)), {units:['p:fresh']});
  assert.equal(apply.ai_token, 'old-token');
  assert.equal(apply.fingerprint, 'old-fingerprint');
  assert.match(f.toasts.at(-1)[0], /已归类 1 篇未分类论文/);
  assert.doesNotMatch(f.toasts.at(-1)[0], /仍有/);
});

test('ticking nothing applies nothing and says so', async () => {
  const calls = [];
  const f = fixture((url, body) => { calls.push([url, body]); return Promise.resolve({suggestions:aiPreview()}); });
  await f.ui.suggest();
  const review = f.dialogs[1];
  review.unitBoxes.forEach(box => { box.checked = false; });
  await review.querySelector('form').onsubmit({preventDefault(){}}); await tick();
  assert.equal(calls.filter(([,body]) => body?.action === 'apply-ai-review').length, 0);
  assert.equal(review.querySelector('.org-dialog-error').textContent, '请先选择');
});

test('a plan with no selectable change offers no apply button', async () => {
  const f = fixture(() => Promise.resolve({suggestions:{...aiPreview(), ai_units:[]}}));
  await f.ui.suggest();
  assert.match(f.dialogs[1].html, /没有需要调整的内容/);
  assert.doesNotMatch(f.dialogs[1].html, /所有论文都已有类别/);
  assert.doesNotMatch(f.dialogs[1].html, /type="submit"/);
});

test('while an application is in flight the ticks and the apply button are locked, and come back after a failure', async () => {
  let reject; const failing = new Promise((_, fail) => { reject = fail; }); failing.catch(() => {});
  const f = fixture((url, body) => body?.action === 'apply-ai-review' ? failing : Promise.resolve({suggestions:aiPreview()}));
  await f.ui.suggest();
  const review = f.dialogs[1];
  const applying = review.querySelector('form').onsubmit({preventDefault(){}}); await tick();
  assert.ok(review.unitBoxes.every(box => box.disabled), 'ticks are locked while applying');
  reject(new Error('服务端拒绝'));
  await applying; await tick();
  assert.ok(review.unitBoxes.every(box => !box.disabled), 'the choice is editable again after a failure');
  assert.equal(review.querySelector('.org-dialog-error').textContent, '服务端拒绝');
});

test('a revision conflict while applying says in words that the library changed after the preview', async () => {
  const f = fixture((url, body) => body?.action === 'apply-ai-review' ? Promise.reject(new Error('Organization revision conflict')) : Promise.resolve({suggestions:aiPreview()}));
  await f.ui.suggest();
  const review = f.dialogs[1];
  await review.querySelector('form').onsubmit({preventDefault(){}}); await tick();
  assert.equal(review.querySelector('.org-dialog-error').textContent, '类别或论文已变化，请重新整理');
});

test('a completed choice says how many more items were applied with it, for the choice to stay applicable', async () => {
  const f = fixture((url, body) => Promise.resolve(body?.action === 'apply-ai-review'
    ? {...snap(2), apply_result:{classified_papers:0, changed_papers:2, merged_categories:2, also_applied:['c:child']}} : {suggestions:aiPreview()}));
  await f.ui.suggest();
  await f.dialogs[1].querySelector('form').onsubmit({preventDefault(){}}); await tick();
  assert.match(f.toasts.at(-1)[0], /另带上了 1 项/);
});

test('the apply error sits in the footer that stays in view, next to the button', async () => {
  const f = fixture(() => Promise.resolve({suggestions:aiPreview()}));
  await f.ui.suggest();
  const review = f.dialogs[1];
  assert.equal(review.querySelector('footer').prepended, review.querySelector('.org-dialog-error'));
});

test('papers still unclassified after a partial application are reported in the notice', async () => {
  const f = fixture((url, body) => Promise.resolve(body?.action === 'apply-ai-review'
    ? {...snap(2), apply_result:{classified_papers:0, changed_papers:0, renamed_categories:1, still_unclassified:3}} : {suggestions:aiPreview()}));
  await f.ui.suggest();
  await f.dialogs[1].querySelector('form').onsubmit({preventDefault(){}}); await tick();
  assert.match(f.toasts.at(-1)[0], /改名 1、合并 0、删除 0 个标签/);
  assert.doesNotMatch(f.toasts.at(-1)[0], /仍有 3 篇未分类/);
});
