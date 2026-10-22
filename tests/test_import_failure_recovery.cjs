'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/static/import.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../app/static/import.html'), 'utf8');
const pack = JSON.parse(fs.readFileSync(path.join(__dirname, '../app/static/i18n/en-US.json'), 'utf8')).messages;
const plain = value => JSON.parse(JSON.stringify(value));
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };
const settle = () => new Promise(resolve => setImmediate(resolve));

function page({lang = 'zh-CN', batch = null, failPdf = true, holdHints = null, holdDetail = null} = {}) {
  class Element {
    constructor(id, attrs = '') {
      this.id = id; this.disabled = /\bdisabled\b/.test(attrs); this.hidden = /\bhidden\b/.test(attrs);
      this.checked = /\bchecked\b/.test(attrs); this.value = ''; this.textContent = ''; this.innerHTML = '';
      this.style = {}; this.listeners = new Map(); this.attrs = {}; this.clicks = 0;
      const classes = new Set((attrs.match(/class="([^"]*)"/)?.[1] || '').split(' ').filter(Boolean));
      this.classList = {toggle(name, on) { const wanted = on ?? !classes.has(name); if (wanted) classes.add(name); else classes.delete(name); },
        add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name)};
    }
    addEventListener(name, fn) { this.listeners.set(name, fn); }
    setAttribute(name, value) { this.attrs[name] = value; }
    removeAttribute(name) { delete this.attrs[name]; }
    getAttribute(name) { return this.attrs[name] ?? null; }
    closest() { return null; }
    matches() { return false; }
    insertAdjacentHTML(_where, value) { this.innerHTML += value; }
    scrollIntoView() {}
    focus() { this.focused = true; }
    click() { this.clicks += 1; }
  }
  const nodes = new Map([...html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)].map(m => [m[1], new Element(m[1], m[0])]));
  const marks = new Map(['source', 'working', 'review', 'done'].map(key => [key, new Element(key)]));
  const get = id => { const node = nodes.get(id); assert.ok(node, 'Real page element is missing: ' + id); return node; };
  const document = {documentElement: {nodeType: 9, lang: lang}, querySelector(selector) {
    const step = selector.match(/^#steps \[data-step="(\w+)"\]$/);
    if (step) return marks.get(step[1]);
    if (selector.startsWith('#')) return get(selector.slice(1));
    return null;
  }, createTreeWalker() {return {nextNode: () => null};}, addEventListener() {}};
  const calls = [], dialogs = [], intervals = new Set();
  const defaultBatch = () => ({id: 'a', status: 'collecting', counts: {}, copies: 0, options: {online: false, folder_categories: true, root_category: false, replace_pdf: false, include_fileless: false},
    upload_failures: [{path: '收藏.pdf', message: '不是 PDF 文件'}], items: [], categories: {paths: [], new_categories: 0, total_after: 0}});
  let held = batch ? plain(batch) : defaultBatch();
  let nextFailure = failPdf;
  let confirm = async (_message, options) => { dialogs.push(options); return false; };
  const context = vm.createContext({document, URLSearchParams, Map, Set, Promise, console,
    location: {search: '?project_id=p', pathname: '/import.html', reload: () => calls.push({path: 'reload'})},
    PDH_I18N: {lang, messages: pack}, NodeFilter: {}, MutationObserver: class {observe() {}},
    setInterval(fn) {intervals.add(fn); return fn;}, clearInterval(fn) {intervals.delete(fn);},
    addEventListener() {},
    PDHImportFiles: {CONCURRENCY: 1, MAX_FILES: 2000, rootOf: () => '', encodeHints: () => '', looksLikeZoteroStorage: () => false},
    PDHPdfHints: {withTimeout: value => value, extractHints: async () => { if (holdHints) await holdHints.promise; return null; }},
    PDHDialogs: {confirm: (...args) => confirm(...args)},
    fetch: async (url, options = {}) => {
      calls.push({path: url, method: options.method || 'GET', body: options.body});
      if (url === '/api/projects') return response({projects: [{id: 'p', name: '收藏'}]});
      if (url.startsWith('/api/import/batches?')) return response({batches: batch ? [plain(held)] : []});
      if (url === '/api/import/batches' && options.method === 'POST') return response(plain(held));
      if (url.endsWith('/pdf')) {
        if (nextFailure) return response({error: '不是 PDF 文件'}, false);
        held.counts = {unmatched: 1}; held.upload_failures = []; held.status = 'collecting'; return response({item: {id: 1}});
      }
      if (url.endsWith('/resolve')) {held.status = 'review'; return response({status: 'review'});}
      if (url.endsWith('/discard')) {held.status = 'discarded'; return response({status: 'discarded'});}
      if (url.startsWith('/api/import/batches/')) {
        if (holdDetail && url.includes('categories=1')) await holdDetail.promise;
        return response(plain(held));
      }
      throw new Error('Unexpected actual page request: ' + url);
    }});
  context.window = context;
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/i18n.js'), 'utf8'), context);
  // Expose lexical functions inside the production closure; execute its real bindings, upload worker and review render.
  vm.runInContext(source.replace(/\}\)\(\);\s*$/, 'window.importTest = {S, startImport, continueUpload, startResolve, enterReview};\n})();'), context);
  const item = {path: '收藏.pdf', file: {name: '收藏.pdf', lastModified: 2, size: 5, bytes: 'original'}};
  context.importTest.S.picked = {pdfs: [item], sidecars: [], skipped: [], ignored: 0};
  get('optOnline').checked = false;
  return {context, api: context.importTest, get, held: () => held, calls, dialogs, item, intervals,
    failPdf: value => {nextFailure = value;}, confirm: value => {confirm = async (_message, options) => {dialogs.push(options); return value && options.valid();};},
    async ready() {await settle();}};
}
function response(body, ok = true) { return {ok, json: async () => body}; }
const failureBatch = () => ({id: 'a', status: 'collecting', counts: {}, copies: 0, options: {online: false, folder_categories: true, root_category: false, replace_pdf: false, include_fileless: false},
  upload_failures: [{path: '收藏.pdf', message: '不是 PDF 文件'}], items: [], categories: {paths: []}});

test('actual all-rejected upload exits Working and exposes reselection/discard without resolving or committing', async () => {
  const p = page(); await p.ready(); await p.api.startImport();
  assert.equal(p.get('stepReview').classList.contains('active'), true);
  assert.equal(p.get('stepWorking').classList.contains('active'), false);
  assert.equal(p.get('emptyImport').hidden, false);
  assert.equal(p.get('emptyReselect').disabled, false);
  assert.equal(p.get('discard').disabled, false);
  assert.equal(p.get('commit').hidden, true);
  assert.match(p.get('failedList').innerHTML, /收藏.pdf/);
  assert.match(p.get('failedList').innerHTML, /不是 PDF/);
  assert.equal(p.calls.some(call => /\/(?:resolve|commit|discard)$/.test(call.path)), false);
  assert.deepEqual(p.item.file, {name: '收藏.pdf', lastModified: 2, size: 5, bytes: 'original'});
});
test('actual cold collecting batch with only persistent failures opens actionable recovery rather than an empty match', async () => {
  const p = page({batch: failureBatch()}); await p.ready(); p.api.S.picked = null;
  await p.api.continueUpload(p.held());
  assert.equal(p.get('stepReview').classList.contains('active'), true);
  assert.equal(p.get('emptyImport').hidden, false);
  assert.match(p.get('failedList').innerHTML, /收藏.pdf/);
  assert.equal(p.api.S.batch.options.online, false);
  assert.equal(p.calls.some(call => call.path.endsWith('/resolve')), false);
});
test('reselect/back and cancelled explicit discard retain the same batch, failure receipts and disabled offline option', async () => {
  const p = page(); await p.ready(); await p.api.startImport();
  await p.get('emptyReselect').onclick();
  assert.equal(p.get('stepSource').classList.contains('active'), true);
  assert.equal(p.get('continueSkip').hidden, true);
  assert.equal(p.get('continueBack').hidden, false);
  assert.equal(p.get('optOnline').checked, false); assert.equal(p.get('optOnline').disabled, true);
  assert.equal(p.get('start').disabled, true);
  await p.get('continueBack').onclick(); await p.get('discard').onclick();
  assert.equal(p.api.S.batch.id, 'a'); assert.equal(p.held().upload_failures.length, 1);
  assert.equal(p.calls.some(call => call.path.endsWith('/discard')), false);
  p.confirm(true); await p.get('discard').onclick();
  assert.deepEqual(p.calls.filter(call => call.path.endsWith('/discard')).map(call => call.path), ['/api/import/batches/a/discard']);
  assert.equal(p.calls.at(-1).path, 'reload');
});
test('explicit repaired-file retry keeps the original batch and enters normal matching with no stale failed receipt', async () => {
  const p = page(); await p.ready(); await p.api.startImport(); await p.get('emptyReselect').onclick();
  p.api.S.picked = {pdfs: [p.item], sidecars: [], skipped: [], ignored: 0}; p.failPdf(false);
  await p.api.startImport();
  assert.equal(p.calls.filter(call => call.path === '/api/import/batches').length, 1);
  assert.equal(p.calls.filter(call => call.path.endsWith('/resolve')).length, 1);
  assert.equal(p.get('stepReview').classList.contains('active'), true);
  assert.equal(p.get('emptyImport').hidden, true); assert.equal(p.get('commit').hidden, false);
  assert.equal(p.get('failedBox').hidden, true); assert.equal(p.api.S.batch.options.online, false);
});
test('duplicate Start while first-page parsing is pending creates and uploads once', async () => {
  const hold = deferred(), p = page({holdHints: hold}); await p.ready();
  const first = p.api.startImport(); await settle(); const second = p.api.startImport();
  hold.resolve(); const results = await Promise.allSettled([first, second]);
  assert.equal(p.calls.filter(call => call.path === '/api/import/batches').length, 1);
  assert.equal(p.calls.filter(call => call.path.endsWith('/pdf')).length, 1);
  assert.equal(results.every(result => result.status === 'fulfilled'), true);
});
test('batch change during hint extraction cannot send a file to the new batch or paint old failure results', async () => {
  const hold = deferred(), p = page({holdHints: hold}); await p.ready();
  const work = p.api.startImport(); await settle();
  p.api.S.batch = {...failureBatch(), id: 'other'}; p.api.S.stage = 'source'; hold.resolve(); const result = await Promise.allSettled([work]);
  assert.equal(p.calls.some(call => call.path.endsWith('/pdf')), false);
  assert.equal(p.api.S.batch.id, 'other'); assert.deepEqual(plain(p.api.S.uploadFailed), []);
  assert.equal(result[0].status, 'fulfilled');
});
test('late recovery detail cannot overwrite a different batch or a newly selected source stage', async () => {
  const hold = deferred(), p = page({batch: failureBatch(), holdDetail: hold}); await p.ready(); p.api.S.batch = p.held();
  const work = p.api.enterReview(); await settle(); p.api.S.batch = {...failureBatch(), id: 'other'}; p.api.S.stage = 'source';
  hold.resolve(); await work;
  assert.equal(p.api.S.batch.id, 'other'); assert.equal(p.get('emptyImport').hidden, true);
});
test('actual recovery dynamic system strings translate while CJK filenames stay exact', async () => {
  const p = page({lang: 'en-US'}); await p.ready(); await p.api.startImport();
  assert.doesNotMatch(p.get('emptyImportTitle').textContent + p.get('emptyImportOptions').textContent + p.get('emptyReselect').textContent, /[㐀-鿿]/);
  assert.match(p.get('emptyImportTitle').textContent, /No files imported/);
  assert.match(p.get('failedList').innerHTML, /收藏.pdf/); assert.match(p.get('failedList').innerHTML, /not a PDF file/);
});
