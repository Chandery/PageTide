/* Library import: bring an existing PDF library into a project.
   The page reads each PDF's first pages (pdf.js, in this window) for an identifier or title and uploads the file to the
   local server, one at a time into a staging batch. The server matches the hints to public metadata at a polite pace,
   the person reviews the result, and only then is anything written to the library. Nothing here calls a model. */
(() => {
'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const F = window.PDHImportFiles;
const H = window.PDHPdfHints;
const params = new URLSearchParams(location.search);
const projectId = params.get('project_id') || '';
const fromCreation = params.get('from') === 'creation';
const PAGE = 50;
const POLL_MS = 1000;
const HINT_TIMEOUT_MS = 25000;
const SEED_LIMIT = 20;

const S = {batch: null, picked: null, queue: [], stop: false, stage: '', tab: null, shown: 0, poll: null, ticking: false, rowsToken: 0,
  committed: null, seedsChosen: new Set(), uploadFailed: [], uploadBatchId: null, uploading: false, reviewToken: 0,
  sidecarError: null, open: [], pendingActions: 0};

async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, options); }
  catch (error) { throw new Error('无法连接本地服务，请确认应用仍在运行'); }
  let body = {};
  try { body = await response.json(); } catch (error) { /* an empty body is fine */ }
  if (!response.ok) throw new Error(body.error || '请求失败');
  return body;
}
const post = (path, body = {}) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
const batchUrl = (suffix = '') => `/api/import/batches/${S.batch.id}${suffix}`;
const systemError = message => window.PDHi18n?.system(String(message || '请求失败')) || String(message || '请求失败');

function fail(error) {
  const box = $('#error');
  box.textContent = error && error.message ? error.message : String(error);
  box.hidden = false;
  box.scrollIntoView({block: 'nearest'});
}
const clearError = () => { $('#error').hidden = true; };
async function guarded(work) {
  clearError();
  try { return await work(); } catch (error) { fail(error); return undefined; }
}

/* ------------------------------------------------------------------ steps */
const STEPS = ['source', 'working', 'review', 'done'];
function show(step) {
  const panels = {source: '#stepSource', working: '#stepWorking', review: '#stepReview', done: '#stepDone'};
  for (const name of STEPS) $(panels[name]).classList.toggle('active', name === step);
  STEPS.forEach((name, i) => {
    const li = $(`#steps [data-step="${name}"]`);
    li.classList.toggle('on', name === step);
    li.classList.toggle('past', i < STEPS.indexOf(step));
    if (name === step) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
  });
}

/* ------------------------------------------------------------------ labels */
const STATE_LABEL = {needs_choice: '需选择', matched: '已匹配', unmatched: '未识别', duplicate: '已在库', failed: '失败', excluded: '已排除'};
const SOURCE_LABEL = {pdf_id: '按 DOI / arXiv 编号', title: '按标题', sidecar: '来自导出文件', existing: '已在库',
  user_pick: '你选的', user_lookup: '你查找的', unresolved: '未识别'};
const SKIP_REASON = {too_large: '超过 60 MB，无法导入，已跳过', empty: '文件是空的，已跳过'};
const PAUSE_TEXT = {
  content_changed: '文件或题录已更新，旧匹配结果已忽略；点击继续，用新内容重新匹配。',
  openalex_quota: 'OpenAlex 今天的检索额度用完了。可以先看已有结果，之后再继续（没提交的导入会保留 30 天），或者不再联网、把剩下的按 PDF 原样导入。论文很多、又主要靠题目检索时，可以到设置里填一个免费的 OpenAlex key，额度约是不填的 10 倍。',
  network: '连不上网络，已暂停。恢复网络后点「继续」即可，已经匹配好的不会重来。',
  cancelled: '已暂停。点「继续」接着匹配。',
  error: '匹配时出错了，已暂停。已经完成的部分都保留着，可以点「继续」再试一次。',
  busy: '另一个导入正在匹配论文信息。等它结束后点「继续」。',
};

/* ------------------------------------------------------------------ project line, resume list */
async function loadProject() {
  if (!projectId) { fail(new Error('缺少项目：请从论文库或新建项目页进入导入')); $('#pickFiles').disabled = $('#pickFolder').disabled = true; return false; }
  const back = $('#back');
  back.href = `/?project_id=${encodeURIComponent(projectId)}`;
  $('#toLibrary').href = `/?project_id=${encodeURIComponent(projectId)}&view=library`;
  const {projects} = await api('/api/projects');
  const project = projects.find((p) => p.id === projectId);
  if (!project) { fail(new Error('项目不存在')); return false; }
  $('#target').innerHTML = `<span>导入到项目：</span><strong data-no-i18n>${esc(project.name)}</strong>${fromCreation ? '<span>（刚创建好）</span>' : ''}`;
  return true;
}

const RESUME_LABEL = {collecting: '补传并继续', committing: '重试提交'};

async function loadResume() {
  const {batches} = await api(`/api/import/batches?project_id=${encodeURIComponent(projectId)}`);
  const open = batches.filter((b) => ['collecting', 'resolving', 'paused', 'review', 'committing'].includes(b.status));
  const box = $('#resumeBox');
  box.hidden = !open.length;
  box.innerHTML = open.length ? '<strong>上次没有完成的导入</strong>' + open.map((b) => {
    const total = Object.values(b.counts || {}).reduce((a, n) => a + n, 0);
    const name = b.root_name ? `<span data-no-i18n>${esc(b.root_name)}</span>` : '<span>单独选择的文件</span>';
    return `<div class="line" data-batch="${esc(b.id)}">${name}<span>${total} 个文件</span>`
      + `<button type="button" class="small" data-act="resume">${RESUME_LABEL[b.status] === undefined ? '继续' : RESUME_LABEL[b.status]}</button>`
      + (b.status === 'committing' ? '' : '<button type="button" class="small ghost" data-act="drop">放弃</button>') + '</div>';
  }).join('') : '';
  S.open = open;
}
$('#resumeBox').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-act]');
  if (!button || button.disabled) return;
  const batch = S.open.find((b) => b.id === button.closest('[data-batch]').dataset.batch);
  if (!batch) return;
  return guarded(async () => {
    if (button.dataset.act === 'drop') {
      button.disabled=true;
      try {
        if (!await window.PDHDialogs.confirm('放弃这次导入？已暂存的文件会被删除，论文库不会有任何变化。', {valid:()=>S.open.some(b=>b.id===batch.id && b.status!=='committing')})) return;
        await post(`/api/import/batches/${batch.id}/discard`); await loadResume(); return;
      } finally {button.disabled=false;}
    }
    S.batch = batch;
    if (batch.status === 'committing') return retryCommit();       // a commit that was cut off: the same call finishes it
    if (batch.status === 'review') return enterReview();
    if (batch.status === 'collecting') return continueUpload(batch);   // files may be missing: offer to send them
    return startResolve();
  });
});

/* A batch whose files were not all sent: back to the first step with its options fixed; picking the same folder again
   sends only what is missing (the server already holds the rest), or the person can match what is there. */
const hasItems = detail => Object.values(detail.counts || {}).some(count => Number(count) > 0);
function continueUpload(batch, reselect = false) {
  if (S.uploading || S.pendingActions) return;
  S.batch = batch;
  if (!reselect && !hasItems(batch) && batch.upload_failures?.length) return enterReview();
  S.stage = 'source';
  S.rowsToken += 1;   // rows from the previous review must not paint after the return to file selection
  const total = Object.values(batch.counts || {}).reduce((a, n) => a + n, 0) - (batch.copies || 0);
  const o = batch.options || {};
  [['#optOnline', 'online'], ['#optFolders', 'folder_categories'], ['#optRoot', 'root_category'], ['#optReplace', 'replace_pdf'], ['#optFileless', 'include_fileless']]
    .forEach(([id, key]) => { $(id).checked = !!o[key]; $(id).disabled = true; });
  $('#continueText').textContent = !hasItems(batch) ? systemError('失败记录和本次导入选项已保留。请修复文件后重新选择，再开始导入。')
    : `正在继续这次导入（已有 ${total} 个文件）。重新选择同一个文件夹，只会补传缺少的文件。`;
  $('#continueBox').hidden = false;
  $('#continueSkip').hidden = !hasItems(batch);
  $('#continueSkip').onclick = () => guarded(startResolve);
  $('#continueBack').hidden = !reselect;
  $('#continueBack').textContent = systemError('返回查看失败记录');
  $('#continueBack').onclick = () => guarded(enterReview);
  if (reselect) {
    S.picked = null; S.queue = [];
    $('#picked').hidden = true; $('#start').disabled = true;
  }
  show('source');
}

async function retryCommit() {
  S.committed = (await post(batchUrl('/commit'))).result;
  return enterDone();
}

/* ------------------------------------------------------------------ choosing files */
function setPicked(result) {
  S.picked = result;
  const box = $('#picked');
  box.hidden = false;
  const pdfs = result.pdfs.length;
  $('#pickedSummary').innerHTML = `<div>找到 ${pdfs} 个 PDF</div>`
    + (result.ignored ? `<div>忽略了 ${result.ignored} 个其他文件</div>` : '')
    + (result.sidecars.length ? `<div><span>找到导出文件：</span><span data-no-i18n>${esc(result.sidecars.map((s) => s.file.name).join('、'))}</span></div>` : '');
  const skipped = $('#pickedSkipped');
  skipped.hidden = !result.skipped.length;
  skipped.innerHTML = result.skipped.map((s) => `<li><span data-no-i18n>${esc(s.path)}</span> <span>${SKIP_REASON[s.reason]}</span></li>`).join('');
  const warn = [];
  if (pdfs > F.MAX_FILES) warn.push(`一次最多导入 ${F.MAX_FILES} 个文件，现在有 ${pdfs} 个。请分批选择，或先选其中一部分子文件夹。`);
  if (F.looksLikeZoteroStorage(result.pdfs.map((p) => p.path))) {
    warn.push('这看起来是 Zotero 的 storage 文件夹：里面每篇论文一个随机命名的子文件夹，没有你整理的结构。建议在 Zotero 里用「导出分类…」导出带文件的文件夹再导入。');
  }
  if (result.sidecars.length && !S.batch) $('#optRoot').checked = true;   // resumed batches keep their original options
  $('#filelessRow').hidden = $('#filelessHint').hidden = !result.sidecars.length;
  const note = $('#pickedWarn');
  note.hidden = !warn.length;
  note.innerHTML = warn.map((w) => `<div>${esc(w)}</div>`).join('');
  $('#start').disabled = !(pdfs || result.sidecars.length) || pdfs > F.MAX_FILES;
}
const pick = (files) => setPicked(F.classify([...files]));
$('#pickFiles').onclick = () => $('#filesInput').click();
$('#pickFolder').onclick = () => $('#folderInput').click();
$('#filesInput').onchange = (event) => { pick(event.target.files); event.target.value = ''; };
$('#folderInput').onchange = (event) => { pick(event.target.files); event.target.value = ''; };

const drop = $('#drop');
drop.onclick = () => $('#pickFolder').click();
drop.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); $('#pickFolder').click(); } });
['dragenter', 'dragover'].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach((name) => drop.addEventListener(name, () => drop.classList.remove('over')));
drop.addEventListener('drop', (event) => {
  event.preventDefault(); event.stopPropagation();
  // The entries must be taken during the event itself; the walk afterwards is asynchronous.
  const entries = [...(event.dataTransfer.items || [])].map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null)).filter(Boolean);
  const plain = [...event.dataTransfer.files];
  guarded(async () => {
    const files = entries.length ? await F.walkEntries(entries) : plain;
    pick(files);
  });
});
// A file dropped beside the zone must not make the window navigate to it.
window.addEventListener('dragover', (event) => event.preventDefault());
window.addEventListener('drop', (event) => event.preventDefault());

const options = () => ({online: $('#optOnline').checked, folder_categories: $('#optFolders').checked,
  root_category: $('#optRoot').checked, replace_pdf: $('#optReplace').checked,
  include_fileless: $('#optFileless').checked});

/* ------------------------------------------------------------------ reading and uploading */
// The export of a reference manager comes first: it names the PDFs and carries their metadata. If it cannot be read the
// PDFs are still imported (they are identified from their own first pages); the reason is shown, not hidden.
async function uploadSidecar(picked, id = S.batch?.id) {
  const order = ['bibtex', 'ris', 'csljson'];
  const side = [...picked.sidecars].sort((a, b) => order.indexOf(a.format) - order.indexOf(b.format))[0];
  const note = $('#sidecarNote');
  note.innerHTML = '';
  if (!side) return null;
  try {
    const summary = await api(`/api/import/batches/${id}/sidecar`, {method: 'POST',
      headers: {'Content-Type': 'application/octet-stream', 'X-Filename': encodeURIComponent(side.file.name)}, body: side.file});
    if (S.batch?.id !== id || S.stage !== 'upload') return null;
    note.innerHTML = `<div>已读取导出文件：${summary.entries} 条题录，其中 ${summary.with_files} 条带 PDF</div>`
      + ((summary.errors || []).length ? `<div class="err">部分题录未读取，请核对：</div><ul>${summary.errors.map((v) => `<li data-no-i18n>${esc(systemError(v))}</li>`).join('')}</ul>` : '')
      + (picked.sidecars.length > 1 ? `<div><span>找到多个导出文件，只读取：</span><span data-no-i18n>${esc(side.file.name)}</span></div>` : '');
    return summary;
  } catch (error) {
    if (S.batch?.id !== id || S.stage !== 'upload') return null;
    S.sidecarError = error.message;
    note.innerHTML = `<div class="err"><span>导出文件没有读成功，PDF 仍会照常导入：</span><span data-no-i18n>${esc(systemError(error.message))}</span></div>`;
    return null;
  }
}

async function uploadOne(item, id = S.batch?.id) {
  let hints = null;
  try { hints = await H.withTimeout(H.extractHints(item.file), HINT_TIMEOUT_MS); }
  catch (error) { hints = null; }   // an unreadable first page is not fatal: the file is kept as a plain PDF
  if (S.batch?.id !== id || S.stage !== 'upload') return;  // extraction may finish after the active batch changed
  const headers = {'Content-Type': 'application/pdf', 'X-Relative-Path': encodeURIComponent(item.path),
    'X-Last-Modified': String(item.file.lastModified || 0)};
  const encoded = F.encodeHints(hints);
  if (encoded) headers['X-Import-Hints'] = encoded;
  await api(`/api/import/batches/${id}/pdf`, {method: 'POST', headers, body: item.file});
}

async function runUploads(id = S.batch?.id) {
  const state = {total: S.queue.length, done: 0, failed: []};
  S.stop = false;
  const current = () => S.batch?.id === id && S.stage === 'upload';
  const render = () => {
    if (!current()) return;
    $('#uploadCount').textContent = `${state.done} / ${state.total}`;
    $('#uploadBar').style.width = state.total ? `${Math.round(100 * state.done / state.total)}%` : '100%';
    const failed = $('#uploadFailed');
    failed.hidden = !state.failed.length;
    failed.innerHTML = state.failed.map((f) => `<li><span data-no-i18n>${esc(f.path)}</span>：<span data-no-i18n>${esc(systemError(f.message))}</span></li>`).join('');
  };
  const worker = async () => {
    while (!S.stop && current()) {
      const item = S.queue.shift();
      if (!item) return;
      $('#uploadNow').textContent = item.path;
      try { await uploadOne(item, id); }
      catch (error) { state.failed.push({path: item.path, message: error.message}); }
      state.done += 1;
      render();
    }
  };
  render();
  await Promise.all(Array.from({length: F.CONCURRENCY}, worker));
  if (current()) $('#uploadNow').textContent = '';
  return state;
}

// One pause button for both stages: while files are being read it stops taking new ones, while matching it asks the server.
function stopWork() {
  S.stop = true;
  if (S.stage === 'resolve') post(batchUrl('/cancel')).catch(fail);
}
$('#stop').onclick = stopWork;

async function startImport() {
  const picked = S.picked;
  if (!picked || S.uploading) return;
  S.uploading = true;
  $('#start').disabled = true;
  S.stage = 'upload';
  show('working');
  $('#stageResolve').hidden = true;
  $('#stageUpload').hidden = false;
  $('#resume').hidden = $('#toReview').hidden = true;
  $('#stop').hidden = false;
  let id = S.batch?.id;
  const current = () => S.batch?.id === id && S.stage === 'upload';
  try {
  if (!id) {
    const paths = picked.pdfs.map((p) => p.path);
    const source = picked.sidecars.length ? 'zotero' : paths.some((p) => p.includes('/')) ? 'folder' : 'files';
    const created = await post('/api/import/batches', {project_id: projectId, source, root_name: F.rootOf(paths), options: options()});
    if (S.batch || S.stage !== 'upload') return;
    S.batch = created; id = created.id;
  }
  S.uploadBatchId = id;
  S.uploadFailed = [];
  await uploadSidecar(picked, id);
  if (!current()) return;
  // Explicit reselection verifies content; name/size/mtime cannot prove that a
  // file is unchanged. The server reuses a result only after reading its SHA.
  S.queue = [...picked.pdfs];
  const already = 0;
  const result = await runUploads(id);
  if (!current()) return;
  result.done += already;
  S.uploadFailed = result.failed;
  if (S.stop) { pausedUpload(); return; }
  const detail = await api(`/api/import/batches/${id}?limit=0`);
  if (!current()) return;
  S.batch = detail;
  if (!hasItems(detail)) return await enterReview();  // failure receipts are actionable even without a registered item
  return await startResolve();
  } finally {
    S.uploading = false;
    $('#start').disabled = !S.picked || !(S.picked.pdfs.length || S.picked.sidecars.length) || S.picked.pdfs.length > F.MAX_FILES;
    $('#emptyReselect').disabled = S.pendingActions > 0;
    if (S.batch?.id === id && S.stage === 'review' && !hasItems(S.batch)) $('#emptyReselect').focus();
  }
}

function pausedUpload() {
  const id = S.batch?.id;
  $('#paused').hidden = false;
  $('#stageResolve').hidden = false;
  $('#paused').textContent = S.queue.length ? `已暂停：还有 ${S.queue.length} 个文件没有读取。点「继续」接着读取。` : '已暂停：文件都已读取完。点「继续」开始匹配。';
  $('#resume').hidden = false;
  $('#stop').hidden = true;
  $('#resume').onclick = () => guarded(async () => {
    if (S.batch?.id !== id || S.stage !== 'upload' || S.uploading) return;
    S.uploading = true;
    try {
    $('#paused').hidden = true; $('#resume').hidden = true; $('#stop').hidden = false;
    S.stage = 'upload';
    const again = await runUploads(id);
    if (S.batch?.id !== id || S.stage !== 'upload') return;
    S.uploadFailed = S.uploadFailed.concat(again.failed);
    if (S.stop) { pausedUpload(); return; }
    return await startResolve();
    } finally { S.uploading = false; $('#emptyReselect').disabled = S.pendingActions > 0; }
  });
}

/* ------------------------------------------------------------------ matching */
const sum = (counts, ...keys) => keys.reduce((a, k) => a + (counts[k] || 0), 0);
function renderCounts(detail) {
  const c = detail.counts, copies = detail.copies || 0;
  const total = Object.values(c).reduce((a, n) => a + n, 0) - copies;
  const waiting = sum(c, 'pending', 'resolving');
  const done = total - waiting;
  $('#resolveCount').textContent = `${done} / ${total}`;
  $('#resolveBar').style.width = total ? `${Math.round(100 * done / total)}%` : '100%';
  $('#resolveCounts').innerHTML = [['matched', '已匹配'], ['needs_choice', '需选择'], ['unmatched', '未识别'], ['duplicate', '已在库'], ['failed', '失败'], ['pending', '等待']]
    .map(([key, label]) => `<span>${label} <b>${(c[key] || 0) - (key === 'duplicate' ? copies : 0)}</b></span>`).join('');
  const rate = detail.openalex && detail.openalex.rate_limit;
  const keyed = detail.openalex && detail.openalex.configured;
  $('#quota').innerHTML = !detail.options.online ? '<div>联网补全已关闭：导入不会自动向 OpenAlex 发送任何内容；只有你在确认页里主动「查找」时，输入的文字才会发送。</div>'
    : (rate && rate.remaining != null ? `<div>OpenAlex 剩余额度约 ${rate.remaining}（每次检索消耗 10）</div>` : '')
      + (keyed === false ? '<div>还没有填 OpenAlex key，每天额度较少</div>' : '');
}

async function startResolve() {
  const id = S.batch?.id;
  if (!id) return;
  show('working');
  $('#stageUpload').hidden = !S.picked;
  $('#stageResolve').hidden = false;
  $('#paused').hidden = true;
  $('#resume').hidden = true;
  $('#toReview').hidden = true;
  $('#settle').hidden = true;
  $('#stop').hidden = false;
  S.stage = 'resolve';
  const detail = await api(`/api/import/batches/${id}?limit=0`);
  if (S.batch?.id !== id || S.stage !== 'resolve') return;
  S.batch = detail;
  if (!hasItems(detail)) return enterReview();
  await post(`/api/import/batches/${id}/resolve`);
  if (S.batch?.id !== id || S.stage !== 'resolve') return;
  clearInterval(S.poll);
  S.poll = setInterval(() => guarded(tick), POLL_MS);
  await tick();
}

// Stop waiting for lookups: what is still pending is kept as plain PDFs (or by the export's own record) and nothing is sent.
async function settleRest() {
  const button=$('#settle'), id=S.batch?.id;
  if(button.disabled || !id)return;
  button.disabled=true;
  try {
    if (!await window.PDHDialogs.confirm('不再联网查找，把还没匹配的论文按 PDF 原样导入？之后仍可以在确认页里逐篇「查找」。', {valid:()=>S.batch?.id===id})) return;
    clearInterval(S.poll);
    await post(`/api/import/batches/${id}/settle`);
    if(S.batch?.id===id)return enterReview();
  } finally {button.disabled=false;}
}
$('#settle').onclick = () => guarded(settleRest);

async function tick() {
  const id = S.batch?.id;
  if (!id || S.stage !== 'resolve') return;
  if (S.ticking) return;   // a slow answer must not be overtaken by the next poll
  S.ticking = true;
  try {
    const detail = await api(`/api/import/batches/${id}?limit=0`);
    if (S.batch?.id !== id || S.stage !== 'resolve') return;
    S.batch = detail;
    renderCounts(detail);
    if (detail.status === 'review') { clearInterval(S.poll); return await enterReview(); }
    if (detail.worker_alive) return;
    if (detail.status === 'resolving' && !sum(detail.counts, 'pending', 'resolving')) {
      clearInterval(S.poll);
      return await enterReview();
    }
    clearInterval(S.poll);
    if (detail.status === 'review') return await enterReview();
    // 'resolving' with nobody working on it means the matching stopped without saying why: treat it as paused.
    const stalled = detail.status === 'resolving' && !detail.worker_alive;
    if (detail.status === 'paused' || stalled || detail.status === 'collecting') {
      $('#paused').hidden = false;
      $('#paused').textContent = PAUSE_TEXT[stalled || detail.status === 'collecting' ? 'error' : detail.pause_reason] || PAUSE_TEXT.error;
      $('#stop').hidden = true;
      $('#resume').hidden = false;
      $('#toReview').hidden = false;
      $('#settle').hidden = false;
      $('#resume').onclick = () => guarded(startResolve);
      $('#toReview').onclick = () => guarded(enterReview);
    }
  } finally { S.ticking = false; }
}

/* ------------------------------------------------------------------ review */
const TAB_ORDER = ['needs_choice', 'matched', 'unmatched', 'duplicate', 'failed', 'excluded'];
const tabCount = (detail, key) => (detail.counts[key] || 0) - (key === 'duplicate' ? detail.copies || 0 : 0);

async function enterReview() {
  const id = S.batch?.id, token = ++S.reviewToken;
  if (!id) return;
  clearInterval(S.poll);
  S.stage = 'review';
  const detail = await api(`/api/import/batches/${id}?limit=0&categories=1`);
  if (S.batch?.id !== id || S.stage !== 'review' || token !== S.reviewToken) return;
  S.batch = detail;
  if (S.batch.status === 'committed') return enterDone();
  $('#stop').hidden = true;
  show('review');
  if (!S.tab || !tabCount(S.batch, S.tab)) S.tab = TAB_ORDER.find((k) => tabCount(S.batch, k)) || 'matched';
  renderReviewChrome();
  await loadRows(true);
  if (S.batch?.id === id && S.stage === 'review' && token === S.reviewToken && !hasItems(S.batch) && !S.uploading) $('#emptyReselect').focus();
}

function importable(detail) { return sum(detail.counts, 'matched', 'unmatched') + tabCount(detail, 'duplicate'); }

function renderReviewChrome() {
  const d = S.batch, c = d.counts;
  const empty = !hasItems(d);
  $('#emptyImport').hidden = !empty;
  $('#reviewSummary').hidden = $('#tabs').hidden = $('#cats').hidden = $('#commit').hidden = empty;
  $('#commitNote').hidden = empty;
  $('#addMore').hidden = empty;
  if (empty) {
    $('#emptyImportTitle').textContent = systemError('没有文件保存为导入条目');
    $('#emptyImportText').textContent = systemError('失败原因保留在下方。本次没有导入论文库，原文件未改动。请检查或修复文件后重新选择，也可以明确放弃这次导入。');
    $('#emptyImportOptions').textContent = systemError(d.options?.online === false ? '联网补全仍关闭，重试将沿用这次导入的选项。' : '重试将沿用这次导入的选项。');
    $('#emptyReselect').textContent = systemError('重新选择文件后重试');
    $('#emptyReselect').disabled = S.uploading || S.pendingActions > 0;
    const id = d.id;
    $('#emptyReselect').onclick = () => { if (S.batch?.id === id && S.stage === 'review') return continueUpload(S.batch, true); };
  }
  const waiting = sum(c, 'pending', 'resolving');
  $('#reviewSummary').innerHTML = `<div>将导入 ${importable(d)} 篇</div>`
    + (c.needs_choice ? `<div>${c.needs_choice} 篇需要你选择，不处理就不会导入</div>` : '')
    + (c.failed ? `<div>${c.failed} 篇匹配失败</div>` : '')
    + (waiting ? `<div>${waiting} 篇还没有匹配</div>` : '')
    + (d.options && d.options.online === false ? '<div>联网补全已关闭。「查找」会把你输入的文字发给 OpenAlex。</div>' : '');
  renderFailedUploads();
  $('#tabs').innerHTML = TAB_ORDER.filter((k) => tabCount(d, k) || k === S.tab).map((k) =>
    `<button type="button" role="tab" data-tab="${k}" aria-selected="${k === S.tab}">${STATE_LABEL[k]} <span class="n">${tabCount(d, k)}</span></button>`).join('');
  const blocked = waiting > 0 || c.failed > 0;
  $('#commit').disabled = blocked || S.pendingActions > 0 || !importable(d);
  $('#discard').disabled = S.pendingActions > 0;
  $('#commit').textContent = `导入 ${importable(d)} 篇到论文库`;
  $('#commitNote').innerHTML = S.pendingActions ? '<span>正在完成审阅操作，请稍候</span>' : waiting ? '<span>还有论文没有匹配</span> <button type="button" class="small" id="matchMore">继续匹配</button> <button type="button" class="small ghost" id="settleMore">不再联网，按原样导入剩下的</button>' : c.failed ? '<span>请补传、查找或明确排除失败项后再提交</span>' : '';
  if (waiting && !S.pendingActions) {
    $('#matchMore').onclick = () => guarded(startResolve);
    $('#settleMore').onclick = () => guarded(settleRest);
  }
  renderCategories(d.categories);
  const warnings = d.sidecar && d.sidecar.errors || [];
  $('#reviewWarnings').hidden = !warnings.length;
  $('#reviewWarnings').innerHTML = warnings.length ? '<div>导出文件有部分题录未读取，请核对：</div><ul>'
    + warnings.map((v) => `<li data-no-i18n>${esc(systemError(v))}</li>`).join('') + '</ul>' : '';
}

// Transport or PDF validation failures leave no registered item; bytes may already have reached the local server.
function renderFailedUploads() {
  // The desktop server uses a new port after restart. Browser storage is
  // therefore not a durable import receipt; use the local batch snapshot.
  const local = S.uploadBatchId && S.uploadBatchId !== S.batch?.id ? [] : (S.uploadFailed || []);
  const failed = [...new Map([...local, ...(S.batch?.upload_failures || [])]
    .map(row => [row.path, row])).values()];
  const recorded = S.batch && S.batch.counts && S.batch.counts.failed || 0;
  $('#failedBox').hidden = !failed.length && !recorded;
  if (!failed.length && !recorded) return;
  $('#failedText').textContent = `${failed.length} 个文件未保存为导入条目（传输或校验失败），${recorded} 条匹配或归档失败。可补传原文件，或在失败列表中查找、排除：`;
  $('#failedList').innerHTML = failed.slice(0, 20).map((f) => `<li><span data-no-i18n>${esc(f.path)}</span> <span data-no-i18n>${esc(systemError(f.message))}</span></li>`).join('');
  $('#addMore').onclick = () => continueUpload(S.batch);
}

function renderCategories(preview) {
  if (!preview || !preview.paths.length) {
    $('#catsSummary').textContent = '分类预览';
    $('#catsBody').innerHTML = '<p class="hint">没有子文件夹需要整理成分类，论文会放在「未分类」。</p>';
    return;
  }
  $('#catsSummary').textContent = `分类预览：新建 ${preview.new_categories} 个，导入后共 ${preview.total_after} 个`;
  $('#catsBody').innerHTML = preview.paths.map((p) =>
    `<div class="cat-line" style="padding-left:${(p.path.length - 1) * 16}px"><span data-no-i18n>${esc(p.path.join(' / '))}</span><span class="n">${p.count} 篇</span></div>`).join('')
    + (preview.over_ai_limit ? '<div class="notice warn">分类超过 60 个：之后用 AI 整理分类会被拒绝（它不会截断过大的分类树）。可以只导入部分子文件夹，或之后手动合并。</div>' : '');
}

async function loadRows(reset) {
  const token = ++S.rowsToken;
  const id = S.batch?.id;
  if (reset) { S.shown = 0; $('#rows').innerHTML = ''; }
  const detail = await api(`/api/import/batches/${id}?state=${S.tab}&offset=${S.shown}&limit=${PAGE}`);
  if (token !== S.rowsToken || S.batch?.id !== id || S.stage !== 'review') return;   // an older batch/stage must not paint
  const html = detail.items.map(renderRow).join('');
  $('#rows').insertAdjacentHTML('beforeend', html);
  S.shown += detail.items.length;
  $('#more').hidden = detail.items.length < PAGE;
  if (!detail.items.length && reset) $('#rows').innerHTML = '';
}

function paperLine(item) {
  const paper = item.paper;
  if (!paper) return '';
  const meta = [paper.published ? String(paper.published).slice(0, 4) : '', (paper.authors || []).slice(0, 3).join(', ')].filter(Boolean).join(' · ');
  return `<div class="row-paper" data-no-i18n>${esc(paper.title)}</div><div class="row-meta">`
    + `${paper.unresolved ? '<span class="tag unresolved">未识别的 PDF</span>' : ''}`
    + `${item.match_source && !paper.unresolved ? `<span class="tag">${SOURCE_LABEL[item.match_source] || ''}</span>` : ''}`
    + `${meta ? `<span data-no-i18n>${esc(meta)}</span>` : ''}</div>`;
}

function candidates(item) {
  return (item.candidates || []).map((c, i) => {
    const p = c.paper, meta = [p.published ? String(p.published).slice(0, 4) : '', (p.authors || []).slice(0, 2).join(', ')].filter(Boolean).join(' · ');
    return `<div class="cand"><div><div class="cand-title" data-no-i18n>${esc(p.title)}</div><div class="cand-meta">`
      + `${c.existing ? '<span class="tag">已在库</span> ' : ''}${meta ? `<span data-no-i18n>${esc(meta)}</span> ` : ''}<span>相似度 ${Math.round(c.score * 100)}%</span></div></div>`
      + `<button type="button" class="small" data-act="pick" data-index="${i}">${c.existing ? '就是它（已在库）' : '选这个'}</button></div>`;
  }).join('');
}

function renderRow(item) {
  const lookup = '<input type="text" placeholder="输入 DOI、arXiv 编号或论文名称" aria-label="查找这篇论文" maxlength="300">'
    + '<button type="button" class="small" data-act="lookup">查找</button>';
  const state = item.state;
  let body = '', actions = '';
  if (state === 'needs_choice') {
    body = candidates(item);
    actions = `${lookup}<button type="button" class="small ghost" data-act="keep">都不是，保留为未识别 PDF</button><button type="button" class="small ghost" data-act="exclude">排除</button>`;
  } else if (state === 'matched') {
    body = paperLine(item);
    actions = `${lookup}<button type="button" class="small ghost" data-act="exclude">排除</button>`;
  } else if (state === 'unmatched') {
    body = paperLine(item);
    actions = `${lookup}<button type="button" class="small ghost" data-act="exclude">排除</button>`;
  } else if (state === 'duplicate') {
    body = paperLine(item);
    actions = `${lookup}<button type="button" class="small ghost" data-act="keep">保留为未识别 PDF</button><button type="button" class="small ghost" data-act="exclude">排除</button>`;
  } else if (state === 'failed') {
    body = `<div class="err" data-no-i18n>${esc(systemError(item.error || '匹配失败'))}</div>`;
    actions = `${lookup}<button type="button" class="small ghost" data-act="keep">保留为未识别 PDF</button><button type="button" class="small ghost" data-act="exclude">排除</button>`;
  } else if (state === 'excluded') {
    body = paperLine(item);
    actions = '<button type="button" class="small" data-act="include">恢复</button>';
  }
  const where = item.kind === 'entry' ? '<span class="tag">没有 PDF 的题录</span>' : `<span data-no-i18n>${esc(item.relative_path || '')}</span>`;
  const warning = item.error && state !== 'failed' ? `<div class="err" data-no-i18n>${esc(systemError(item.error))}</div>` : '';
  return `<li class="row" data-item="${item.id}"><div class="row-file">${where}</div>${warning}${body}`
    + `<div class="row-actions">${actions}</div><div class="err" data-error hidden></div></li>`;
}

$('#tabs').addEventListener('click', (event) => {
  const button = event.target.closest('[data-tab]');
  if (!button) return;
  S.tab = button.dataset.tab;
  guarded(async () => { renderReviewChrome(); await loadRows(true); });
});
$('#more').onclick = () => guarded(() => loadRows(false));

$('#rows').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-act]');
  if (!button) return;
  const row = button.closest('.row');
  const body = {action: button.dataset.act};
  if (body.action === 'keep') body.action = 'unresolved';
  if (body.action === 'pick') body.index = Number(button.dataset.index);
  if (body.action === 'lookup') {
    body.text = $('input', row).value;
    if (!body.text.trim()) { $('input', row).focus(); return; }
  }
  button.disabled = true;
  S.pendingActions += 1;
  renderReviewChrome();
  const errorBox = $('[data-error]', row);
  errorBox.hidden = true;
  api(batchUrl(`/items/${row.dataset.item}`), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
    .then(async () => {
      S.batch = await api(batchUrl('?limit=0&categories=1'));
      if (!tabCount(S.batch, S.tab) && S.tab !== 'matched') S.tab = TAB_ORDER.find((k) => tabCount(S.batch, k)) || 'matched';
      renderReviewChrome();
      await loadRows(true);
    })
    .catch((error) => { button.disabled = false; errorBox.textContent = error.message; errorBox.hidden = false; })
    .finally(() => { S.pendingActions -= 1; renderReviewChrome(); });
});

$('#discard').onclick = async () => {
  const button=$('#discard'), id=S.batch?.id;
  if (S.pendingActions || button.disabled || !id) return;
  button.disabled=true;
  try {
    if(!await window.PDHDialogs.confirm('放弃这次导入？已暂存的文件会被删除，论文库不会有任何变化。', {valid:()=>S.batch?.id===id && !S.pendingActions}))return;
    return await guarded(async () => { await post(`/api/import/batches/${id}/discard`); location.reload(); });
  } finally {button.disabled=false;}
};

$('#commit').onclick = () => guarded(async () => {
  if (S.pendingActions) throw new Error('正在完成审阅操作，请等待后再提交');
  const button = $('#commit');
  button.disabled = true;
  button.textContent = '正在导入…';
  try {
    S.committed = (await post(batchUrl('/commit'))).result;
  } catch (error) { S.batch = await api(batchUrl('?limit=0&categories=1')); await enterReview(); throw error; }
  return enterDone();
});

/* ------------------------------------------------------------------ done */
async function enterDone() {
  show('done');
  S.batch = await api(batchUrl('?limit=0'));
  const result = S.committed || S.batch.result || {};   // a batch reopened after its commit still shows what it did
  $('#doneSummary').innerHTML = `<div>新增 ${result.new_papers || 0} 篇论文，关联已有 ${result.linked_existing || 0} 篇（其中 ${result.unresolved || 0} 篇是未识别的 PDF），归档 ${result.pdfs_archived || 0} 个 PDF</div>`
    + (result.already_in_library ? `<div>${result.already_in_library} 篇本来就在这个项目的论文库里</div>` : '')
    + (result.skipped_needs_choice ? `<div>${result.skipped_needs_choice} 篇没有选择，未导入</div>` : '')
    + (result.skipped_failed ? `<div>${result.skipped_failed} 篇失败，未导入</div>` : '')
    + (result.excluded ? `<div>${result.excluded} 篇已排除</div>` : '')
    + (result.extra_pdfs ? `<div><span>${result.extra_pdfs} 个文件对应的论文已经有另一个 PDF，没有归档（原文件没有改动）：</span><span data-no-i18n>${esc((result.extra_pdf_names || []).join('、'))}</span></div>` : '');
  await applyCategories();
  await renderSeeds();
  renderAi(result);
  $('#again').onclick = (event) => { event.preventDefault(); location.href = location.pathname + location.search.replace(/&?from=creation/, ''); };
}

async function applyCategories(again = false) {
  const box = $('#catsDone');
  const wanted = S.batch.options && S.batch.options.folder_categories;
  if (!wanted && !again) { box.hidden = true; return; }
  box.hidden = false;
  try {
    const {result} = await post(batchUrl('/categories'));
    box.innerHTML = `<div><strong>分类</strong> <span>新建 ${result.created_categories || 0} 个，复用已有 ${result.reused_categories || 0} 个，放入 ${result.changed_papers || 0} 篇。</span></div>`
      + (result.undo ? '<button type="button" class="small" id="undoCats">撤销分类</button>' : '');
    const undo = $('#undoCats');
    if (undo) undo.onclick = () => guarded(async () => {
      await post('/api/organization', {action: 'undo', event: result.undo.id});
      box.innerHTML = '<div>已撤销这次导入的分类。论文仍在论文库里，只是回到未分类。</div>';
    });
  } catch (error) {
    box.innerHTML = `<div class="err" data-no-i18n>${esc(systemError(error.message))}</div><div>论文已经导入，只是分类没有应用成功。</div><button type="button" class="small" id="retryCats">重新应用文件夹分类</button>`;
    $('#retryCats').onclick = () => guarded(() => applyCategories(true));
  }
}

async function renderSeeds() {
  const card = $('#seedsCard');
  const [matched, existing] = await Promise.all([api(batchUrl('?state=matched&limit=200')), api(batchUrl('?state=duplicate&limit=200'))]);
  const papers = [...matched.items, ...existing.items].filter((i) => i.committed && i.paper && !i.paper.unresolved && (i.paper_key || i.paper.key));
  card.hidden = !papers.length;
  if (!papers.length) return;
  S.seedsChosen = new Set(fromCreation && papers.length <= SEED_LIMIT ? papers.map((i) => i.paper_key || i.paper.key) : []);
  const list = $('#seedList');
  list.innerHTML = papers.map((i) => {
    const key = i.paper_key || i.paper.key;
    return `<li><input type="checkbox" value="${esc(key)}" id="seed-${i.id}"${S.seedsChosen.has(key) ? ' checked' : ''}>`
      + `<label for="seed-${i.id}" data-no-i18n>${esc(i.paper.title)}</label></li>`;
  }).join('');
  const sync = () => {
    S.seedsChosen = new Set([...list.querySelectorAll('input:checked')].map((box) => box.value));
    const full = S.seedsChosen.size >= SEED_LIMIT;
    list.querySelectorAll('input:not(:checked)').forEach((box) => { box.disabled = full; });
    $('#seedCount').textContent = `已选 ${S.seedsChosen.size} / ${SEED_LIMIT}`;
    $('#seedGo').disabled = !S.seedsChosen.size;
  };
  list.onchange = sync;
  sync();
  $('#seedGo').onclick = () => guarded(async () => {
    const {result} = await post(batchUrl('/seeds'), {action: 'add', keys: [...S.seedsChosen]});
    $('#seedCount').textContent = `已设为种子 ${result.added} 篇，项目现在共有 ${result.seeds} 篇种子`;
    $('#seedGo').disabled = true;
    list.querySelectorAll('input').forEach((box) => { box.disabled = true; });
  });
}

function renderAi(result) {
  const total = (result.new_papers || 0) + (result.linked_existing || 0);
  const card = $('#aiCard');
  card.hidden = total < 2;
  const batches = Math.ceil(total / 12);
  card.innerHTML = `<h3>让 AI 复审分类（可选）</h3><p class="hint">在论文库点「整理分类」触发：先给出预览，你确认后才会应用，也可以撤销。</p>`
    + `<p class="hint">它按每批 12 篇调用 AI，你的论文库约需 ${batches} 批；论文很多时可能超出每日额度而中止，那时可以改天再试。导入本身没有用任何 AI。</p>`;
}

/* ------------------------------------------------------------------ start */
$('#start').onclick = () => guarded(startImport);
(async () => {
  guarded(async () => {
    if (await loadProject()) await loadResume();
  });
})();
})();
