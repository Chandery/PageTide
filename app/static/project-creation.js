/* Project creation: quick (one AI call), guided (conversation) and manual (seed papers).
   Every wait shows what is happening and for how long; every result says where it came from.
   Candidate papers arrive one query at a time. Nothing here calls a model directly: the local
   server does, through the budgeted gateway. */
(() => {
'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const PDF = window.PDHCreationPdf;
const AI_WAIT = 90;           // the gateway gives up after this many seconds
const MAX_PATH = 8;
const SESSION_KEY = 'pdh-guidance-session';

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {...options, headers: {'Content-Type': 'application/json', ...(options.headers || {})}});
  } catch (error) {
    throw new Error('无法连接本地服务，请确认应用仍在运行');
  }
  let body = {};
  try { body = await response.json(); } catch (error) { /* an empty body is fine */ }
  if (!response.ok) throw new Error(body.error || '请求失败');
  return body;
}
const post = (path, body) => api(path, {method: 'POST', body: JSON.stringify(body)});

/* ------------------------------------------------------------------ activity line */
function makeActivity(el) {
  const text = $('.act-text', el), time = $('.act-time', el);
  let timer = null, started = 0, limit = 0;
  const tick = () => {
    const seconds = Math.floor((Date.now() - started) / 1000);
    time.textContent = limit ? `已等 ${seconds} 秒（最长约 ${limit} 秒）` : `已等 ${seconds} 秒`;
  };
  const clear = () => { clearInterval(timer); timer = null; };
  return {
    start(message, max = 0) {
      clear(); limit = max; started = Date.now();
      el.classList.remove('error'); text.textContent = message; el.hidden = false; tick();
      timer = setInterval(tick, 500);
    },
    set(message) { text.textContent = message; },
    stop() { clear(); el.hidden = true; },
    fail(message) { clear(); el.classList.add('error'); text.textContent = message; time.textContent = ''; el.hidden = false; },
  };
}

/* ------------------------------------------------------------------ chip input */
function makeChips(root, onChange = () => {}) {
  const chips = $('.chips', root), input = $('input', root);
  let values = [];
  const render = (flash = []) => {
    chips.innerHTML = '';
    values.forEach((value, index) => {
      const chip = document.createElement('span');
      chip.className = 'chip' + (flash.includes(value) ? ' changed' : '');
      chip.innerHTML = `<span data-no-i18n>${esc(value)}</span><button type="button" aria-label="删除" title="删除">×</button>`;
      $('button', chip).onclick = () => { values.splice(index, 1); render(); onChange(); };
      chips.appendChild(chip);
    });
  };
  const add = (raw) => {
    let changed = false;
    for (const part of String(raw).split(/[,，;；\n]/)) {
      const value = part.trim().slice(0, 120);
      if (value && !values.some((v) => v.toLowerCase() === value.toLowerCase()) && values.length < 40) { values.push(value); changed = true; }
    }
    input.value = '';
    if (changed) { render(); onChange(); }
  };
  input.addEventListener('keydown', (event) => {
    if (event.isComposing) return;
    if (event.key === 'Enter' || event.key === ',' || event.key === '，') { event.preventDefault(); add(input.value); }
    else if (event.key === 'Backspace' && !input.value && values.length) { values.pop(); render(); onChange(); }
  });
  input.addEventListener('blur', () => add(input.value));
  input.addEventListener('paste', () => setTimeout(() => { if (/[,，;；\n]/.test(input.value)) add(input.value); }));
  root.addEventListener('click', (event) => { if (event.target === root) input.focus(); });
  return {
    get: () => [...values],
    commit: () => add(input.value),
    set(list, {flashNew = false} = {}) {
      const before = new Set(values.map((v) => v.toLowerCase()));
      values = [];
      for (const value of list || []) if (value && !values.includes(value)) values.push(String(value).slice(0, 120));
      render(flashNew ? values.filter((v) => !before.has(v.toLowerCase())) : []);
      onChange();
    },
  };
}

/* ------------------------------------------------------------------ candidate cards */
const meta = (p) => {
  const authors = p.authors || [];
  const names = authors.slice(0, 3).join(', ') + (authors.length > 3 ? ' et al.' : '');
  return [names, p.published, p.source].filter(Boolean).join(' · ');
};

const PDF_BADGES = {
  direct: ['直链 PDF', '已知合法的 PDF 下载链接（arXiv 或开放获取）'],
  page: ['仅原文页', '这篇论文是开放获取的，但只给了原文网页，没有 PDF 直链'],
  none: ['无 PDF 来源', '没有找到合法的 PDF 来源；可以自己下载后附加'],
};
const pdfBadge = (status) => {
  const [text, tip] = PDF_BADGES[status] || PDF_BADGES.none;
  return `<span class="badge pdf-${PDF_BADGES[status] ? status : 'none'}" title="${tip}">${text}</span>`;
};

function candidateCard(paper, selected, onToggle) {
  const el = document.createElement('div');
  el.className = 'cand' + (selected ? ' selected' : '');
  el.dataset.key = paper.key;
  const hasAbstract = !!(paper.abstract || '').trim();
  el.innerHTML = `<input type="checkbox" aria-label="选择这篇论文"${selected ? ' checked' : ''}>
    <div>
      <div class="title" data-no-i18n>${esc(paper.title)}</div>
      <div class="meta" data-no-i18n>${esc(meta(paper))}</div>
      <div class="abstract" data-no-i18n>${hasAbstract ? esc(paper.abstract) : ''}</div>
      <div class="more">
        ${hasAbstract ? '<button type="button" class="toggle">展开摘要</button>' : '<span>没有摘要</span>'}
        ${paper.url ? `<a href="${esc(paper.url)}" target="_blank" rel="noreferrer">打开原文</a>` : ''}
        ${pdfBadge(paper.pdf_status)}
        <span class="tags"></span>
      </div>
    </div>`;
  const box = $('input', el);
  const toggle = (value) => { box.checked = value; el.classList.toggle('selected', value); onToggle(paper.key, value); };
  el.addEventListener('click', (event) => {
    if (event.target.closest('a, .toggle')) return;
    toggle(event.target === box ? box.checked : !box.checked);
  });
  const more = $('.toggle', el);
  if (more) more.onclick = () => {
    const open = el.classList.toggle('open');
    more.textContent = open ? '收起摘要' : '展开摘要';
  };
  el.setTags = (queries) => {
    $('.tags', el).innerHTML = (queries || []).map((q) => `<span class="tag"><span>命中</span> <span data-no-i18n>${esc(q)}</span></span>`).join(' ');
  };
  el.setSelected = (value) => { box.checked = value; el.classList.toggle('selected', value); };
  el.setTags(paper.matched_queries);
  return el;
}

const SEARCH_PROBLEMS = {
  unavailable: 'OpenAlex 暂时不可用（对方限流或维护中）。草稿已保存，稍后再点「按检索式查找论文」。',
  network_error: '网络不通，没能连到 OpenAlex。检查网络后再试。',
};

/* ------------------------------------------------------------------ review area */
function makeReview(root, {sessionId, onCreate, createLabel}) {
  const view = $('#reviewTpl').content.firstElementChild.cloneNode(true);
  root.replaceChildren(view);
  const part = (role) => $(`[data-role="${role}"]`, view);
  const candidates = new Map(), selected = new Set();
  let searching = false, busy = false;
  const searchAct = makeActivity(part('searchActivity')), createAct = makeActivity(part('createActivity'));
  const keywords = makeChips(part('keywords'), () => refresh());
  if (createLabel) part('create').textContent = createLabel;

  function refresh() {
    const count = keywords.get().length;
    part('summary').textContent = `已选 ${selected.size} 篇候选，${count} 个关键词`;
    part('create').disabled = busy || !count;
    part('create').title = count ? '' : '至少需要 1 个关键词';
    part('search').disabled = searching || busy;
  }

  /* ---- learning map: AI proposes concepts and their order, the page lets you edit, check and confirm */
  const R = window.PDHRoute;
  const map = {graph: null, mastered: [], regenerated: 0, checking: false};
  const mapAct = makeActivity(part('mapActivity'));
  const mapNotice = (message, isError = true) => {
    const el = part('mapNotice');
    el.hidden = !message; el.textContent = message || ''; el.classList.toggle('error', isError);
  };
  const GROUNDING = {ok: '', none: '（公开文献里没找到）', no_terms: '（没有英文检索词）', unavailable: '（这次没能核对）', skipped: '（被限流，未核对）'};

  function renderMap() {
    const holder = part('map');
    holder.replaceChildren();
    const g = map.graph;
    part('mapActions').hidden = !g;
    part('mapRegen').hidden = !g || !sessionId();
    part('mapGenerate').hidden = !!g;
    if (!g) { part('mapNote').hidden = true; refresh(); return; }
    const verdict = R.check(g);
    part('mapNote').hidden = false;
    part('mapNote').textContent = verdict.ok
      ? `${g.concepts.length} 个概念，${R.columns(g).length} 层。越靠左越基础；勾选“已掌握”的概念作为起点，它后面的概念会先解锁。虚线框是与目标无关的旁支。`
      : `现在的学习图有问题：${verdict.reason}`;
    R.columns(g).forEach((col, index) => {
      const column = document.createElement('div');
      column.className = 'map-col';
      column.innerHTML = `<h4>第 ${index + 1} 层</h4>`;
      col.forEach((concept) => column.appendChild(conceptCard(g, concept)));
      holder.appendChild(column);
    });
    refresh();
  }

  function conceptCard(g, concept) {
    const card = document.createElement('div');
    const mastered = map.mastered.includes(concept.id);
    card.className = 'map-card' + (concept.side ? ' side' : '') + (mastered ? ' mastered' : '');
    const needs = R.needsOf(g, concept.id);
    const grounding = GROUNDING[concept.grounding] || '';
    card.innerHTML = `<span class="name" data-no-i18n>${esc(concept.name)}</span>
      <div class="terms" data-no-i18n>${esc((concept.terms || []).join(' · ') || '（没有检索词）')}</div>
      ${needs.length ? `<div class="needs">前置：${needs.map((n) => `<span class="need ${n.label}" title="${esc(R.LABELS[n.label])}" data-no-i18n>${esc(n.name)}</span>`).join('、')}</div>` : ''}
      ${concept.papers !== undefined ? `<div class="counts ${concept.grounding === 'ok' ? '' : 'none'}">公开文献里约 ${concept.papers} 篇${grounding}</div>` : ''}
      <div class="row"><label><input type="checkbox"${mastered ? ' checked' : ''}> 已掌握</label>
        <button type="button" class="ghost small" data-act="edit">编辑</button><button type="button" class="ghost small" data-act="del">删除</button></div>`;
    $('input[type=checkbox]', card).onchange = () => { map.mastered = R.toggleMastered(map.mastered, concept.id, g); renderMap(); };
    $('[data-act=del]', card).onclick = () => { map.graph = R.removeConcept(g, concept.id); map.mastered = map.mastered.filter((i) => i !== concept.id); renderMap(); };
    $('[data-act=edit]', card).onclick = () => editConcept(card, g, concept);
    return card;
  }

  function editConcept(card, g, concept) {
    card.innerHTML = `<input class="edit" data-role="n" maxlength="60" placeholder="概念名称" aria-label="概念名称">
      <input class="edit" data-role="t" maxlength="130" placeholder="两个英文检索词，用 / 分隔" aria-label="英文检索词">
      ${R.needsEditorHTML(g, concept.id)}
      <div class="row"><button type="button" class="small" data-act="ok">确定</button><button type="button" class="ghost small" data-act="no">取消</button></div>`;
    $('[data-role=n]', card).value = concept.name;
    $('[data-role=t]', card).value = (concept.terms || []).join(' / ');
    $('[data-act=no]', card).onclick = renderMap;
    $('[data-act=ok]', card).onclick = () => {
      try {
        let next = R.rename(g, concept.id, $('[data-role=n]', card).value, $('[data-role=t]', card).value.split('/'));
        next = R.setNeeds(next, concept.id, R.readNeeds(card));
        map.graph = next; mapNotice(''); renderMap();
      } catch (error) { mapNotice(error.message); }
    };
  }

  part('mapAdd').onclick = () => {
    try { map.graph = R.addConcept(map.graph, {name: '新概念', terms: [], hint: 2}, []); mapNotice(''); renderMap(); }
    catch (error) { mapNotice(error.message); }
  };
  part('mapDrop').onclick = () => { map.graph = null; map.mastered = []; mapNotice(''); renderMap(); };

  async function generateMap(regenerate) {
    if (!sessionId()) { mapNotice('请先开始创建会话。'); return; }
    mapNotice(''); mapAct.start('正在请 AI 规划学习路径（约 10–30 秒）…');
    part('mapGenerate').disabled = true; part('mapRegen').disabled = true;
    try {
      const out = await post(`/api/project-guidance/sessions/${sessionId()}/route`, {regenerate});
      if (!out.ok) { mapNotice(`没有使用 AI：${out.reason || 'AI 没有给出学习图'}。可以点“添加概念”自己搭学习图，或不使用学习图。`); return; }
      map.graph = out.graph; map.mastered = [];
      const fixed = out.report ? out.report.dropped_edges.length + out.report.merged.length + out.report.dropped_concepts.length : 0;
      mapNotice(`AI 已回复${out.tokens ? ` · 约 ${out.tokens} token` : ''}${fixed ? ` · 已自动修复 ${fixed} 处（重复概念、成环或多余的边）` : ''}。请检查后再创建。`, false);
      renderMap();
    } catch (error) { mapNotice(error.message); }
    finally { mapAct.stop(); part('mapGenerate').disabled = false; part('mapRegen').disabled = false; }
  }
  part('mapGenerate').onclick = () => generateMap(false);
  part('mapRegen').onclick = () => {
    if (confirm('重新生成会覆盖你对学习图的修改，并用掉 1 次重新生成机会。继续？')) generateMap(true);
  };

  part('mapCheck').onclick = async () => {
    if (!map.graph || map.checking) return;
    map.checking = true; mapNotice(''); mapAct.start('正在用公开文献核对每个概念（OpenAlex，只发送检索词）…');
    part('mapCheck').disabled = true;
    try {
      const out = await post('/api/route', {action: 'ground', graph: map.graph});
      map.graph = out.graph; renderMap();
      const missing = map.graph.concepts.filter((c) => c.grounding === 'none').length;
      mapNotice(missing ? `有 ${missing} 个概念在公开文献里没找到，可以改检索词或删除。` : '核对完成。', !!missing);
    } catch (error) { mapNotice(error.message); }
    finally { mapAct.stop(); map.checking = false; part('mapCheck').disabled = false; }
  };
  const mapPayload = () => (map.graph && R.check(map.graph).ok ? R.payload(map.graph, map.mastered) : null);

  function addPathItem(item = {}) {
    const holder = part('path');
    if ($$('.path-item', holder).length >= MAX_PATH) return;
    const row = document.createElement('div');
    row.className = 'path-item';
    row.innerHTML = `<div class="path-head"><input placeholder="阶段标题" maxlength="160"><button type="button" class="ghost small">删除</button></div><textarea placeholder="目的" maxlength="300"></textarea>`;
    $('input', row).value = item.title || '';
    $('textarea', row).value = item.purpose || '';
    $('button', row).onclick = () => { row.remove(); syncPath(); };
    holder.appendChild(row);
    syncPath();
    if (!item.title) $('input', row).focus();
  }
  const syncPath = () => { part('addPath').disabled = $$('.path-item', part('path')).length >= MAX_PATH; };
  part('addPath').onclick = () => addPathItem({});
  renderMap();

  function draft() {
    keywords.commit();
    return {
      keywords: keywords.get(),
      search_queries: part('queries').value.split('\n').map((x) => x.trim()).filter(Boolean).slice(0, 6),
      learning_path: $$('.path-item', part('path')).map((row) => ({title: $('input', row).value, purpose: $('textarea', row).value}))
        .filter((x) => x.title.trim()),
    };
  }

  function setDraft(d, options = {}) {
    keywords.set(d.keywords || [], options);
    part('queries').value = (d.search_queries || []).join('\n');
    part('path').innerHTML = '';
    (d.learning_path || []).forEach(addPathItem);
    syncPath();
    if (d.route_plan && d.route_plan.graph && !map.graph) { map.graph = d.route_plan.graph; renderMap(); }
    if (d.candidates && d.candidates.length && !candidates.size) addCandidates(d.candidates.map((p) => ({...p, url: p.url || (p.arxiv_id ? `https://arxiv.org/abs/${p.arxiv_id}` : null)})));
    refresh();
  }

  function addCandidates(items) {
    const list = part('cands');
    $$('.skeleton', list).forEach((el) => el.remove());
    for (const paper of items) {
      if (!paper.key) continue;
      let card = $(`.cand[data-key="${CSS.escape(paper.key)}"]`, list);
      if (card) { card.setTags(paper.matched_queries); continue; }
      card = candidateCard(paper, selected.has(paper.key), (key, value) => {
        value ? selected.add(key) : selected.delete(key);
        refresh();
      });
      candidates.set(paper.key, paper);
      list.appendChild(card);
    }
  }

  const skeletons = (n) => { part('cands').insertAdjacentHTML('beforeend', '<div class="skeleton" aria-hidden="true"></div>'.repeat(n)); };
  const notice = (message, isError = true) => {
    const el = part('searchNotice');
    el.hidden = !message; el.textContent = message || ''; el.classList.toggle('error', isError);
  };

  async function search() {
    if (searching || !sessionId()) return;
    const d = draft();
    let queries = d.search_queries.slice(0, 3);
    if (!queries.length && d.keywords.length) queries = [d.keywords.slice(0, 4).join(' ')];
    if (!queries.length) { notice('请先填写检索式或关键词。'); return; }
    searching = true; notice(''); refresh();
    const before = candidates.size;
    if (!candidates.size) skeletons(3);
    let problem = null;
    for (let i = 0; i < queries.length; i += 1) {
      searchAct.start(`正在查找第 ${i + 1}/${queries.length} 条检索式：${queries[i]}`);
      part('searchStatus').textContent = candidates.size ? `已找到 ${candidates.size} 篇候选，继续查找…` : '查找中…';
      let result;
      try {
        result = await post(`/api/project-guidance/sessions/${sessionId()}/search`, {query: queries[i], all_years: part('allYears').checked});
      } catch (error) { problem = {kind: 'request', message: error.message}; break; }
      addCandidates(result.items);
      if (result.error) {
        problem = result.error;
        if (result.error.kind === 'unavailable') break;   // more queries only add waiting
      }
    }
    searchAct.stop();
    $$('.skeleton', part('cands')).forEach((el) => el.remove());
    searching = false;
    part('searchStatus').textContent = candidates.size ? `已找到 ${candidates.size} 篇候选` : '';
    if (problem) {
      notice(SEARCH_PROBLEMS[problem.kind] || `部分检索失败：${problem.message}`);
    } else if (!candidates.size) {
      notice('没有找到候选论文。论文标题大多是英文，试试把检索式换成更宽的英文词。', false);
    } else if (candidates.size === before) {
      notice('这次没有新的候选论文。', false);
    }
    refresh();
  }
  part('search').onclick = search;
  part('selectAll').onclick = () => {
    for (const key of candidates.keys()) selected.add(key);
    $$('.cand', part('cands')).forEach((el) => el.setSelected(true));
    refresh();
  };
  part('selectNone').onclick = () => {
    selected.clear();
    $$('.cand', part('cands')).forEach((el) => el.setSelected(false));
    refresh();
  };
  part('create').onclick = async () => {
    busy = true; refresh();
    createAct.start('正在创建项目…');
    try {
      if (map.graph && !R.check(map.graph).ok) { mapNotice(`学习图还不能保存：${R.check(map.graph).reason}`); createAct.stop(); busy = false; refresh(); return; }
      await onCreate({draft: draft(), selectedKeys: [...selected], route: mapPayload()});
    } catch (error) {
      createAct.fail(error.message);
      busy = false; refresh();
    }
  };
  refresh();
  return {setDraft, draft, search, refresh, root: view,
    setBusy(value) { busy = value; refresh(); }};
}

/* ------------------------------------------------------------------ state shared by the modes */
let mode = null, session = null, review = null;

function setMode(next) {
  mode = next;
  $$('.mode-card').forEach((card) => card.setAttribute('aria-checked', String(card.dataset.mode === next)));
  $$('.panel').forEach((panel) => panel.classList.remove('active'));
  const id = {quick: 'quickForm', ai_guided: 'guidedForm', manual: 'manualForm'}[next];
  if (id) $('#' + id).classList.add('active');
}

async function discardSession() {
  const id = session && session.id;
  session = null; review = null;
  localStorage.removeItem(SESSION_KEY);
  if (id) { try { await fetch(`/api/project-guidance/sessions/${id}`, {method: 'DELETE'}); } catch (error) { /* it stays a draft; harmless */ } }
}

async function resetAll() {
  await discardSession();
  stopQuick(); stopGuided();
  setMode(null);
}

$$('.mode-card').forEach((card) => {
  card.onclick = async () => {
    if (card.dataset.mode === mode) return;
    if (session) {
      if (!confirm('切换创建方式会放弃当前草稿，继续吗？')) return;
      await discardSession();
    }
    stopQuick(); stopGuided();
    setMode(card.dataset.mode);
    const first = $('.panel.active input, .panel.active textarea');
    if (first) first.focus();
  };
});
document.addEventListener('click', (event) => {
  if (event.target.closest('[data-act="cancel"]')) resetAll();
});

async function finalize({draft, selectedKeys, route}) {
  const result = await post(`/api/project-guidance/sessions/${session.id}/finalize`, {draft, selected_keys: selectedKeys, route});
  localStorage.removeItem(SESSION_KEY);
  location.href = `/?project_id=${encodeURIComponent(result.project_id)}`;
}

async function createSession(name, goal, creationMode) {
  const result = await post('/api/project-guidance/sessions', {name, goal, creation_mode: creationMode});
  session = result.session;
  localStorage.setItem(SESSION_KEY, session.id);
  return session;
}

// One line saying whether the model answered, what it cost, and why not when it did not.
function turnMeta(entry, live) {
  if (entry.mode === 'ai') {
    const bits = ['<span class="ok">AI 已回复</span>'];
    if (entry.tokens) bits.push(`约 ${Number(entry.tokens).toLocaleString()} token`);
    if (live && live.elapsed_ms != null) bits.push(`${Math.max(1, Math.round(live.elapsed_ms / 1000))} 秒`);
    return bits.join('<span class="sep" aria-hidden="true">·</span>');
  }
  const why = esc(entry.reason_text || '');
  return `<span class="warn">这一轮没有使用 AI</span>${why ? `<span data-no-i18n>${why}</span>` : ''}`;
}
const retryable = (entry) => entry.mode === 'local' && entry.reason !== 'dry_run';
const settingsLink = (entry) => (['no_key', 'ai_off'].includes(entry.reason) ? '<a href="/settings.html">打开设置</a>' : '');

/* ------------------------------------------------------------------ quick creation */
const quickAct = makeActivity($('#quickActivity'));
function stopQuick() {
  quickAct.stop();
  $('#quickStart').hidden = false; $('#quickWork').hidden = true; $('#quickNote').hidden = true;
  $('#quickReview').replaceChildren(); $('#quickGo').disabled = false;
}

function renderQuickNote(entry, live) {
  const note = $('#quickNote');
  note.hidden = false;
  note.innerHTML = `<div><span class="who">助手：</span><span data-no-i18n>${esc(entry.content || '')}</span></div>
    <div class="meta">${turnMeta(entry, live)} ${retryable(entry) ? '<button type="button" id="quickRetry">重试 AI</button>' : ''} ${settingsLink(entry)}</div>`;
  const retry = $('#quickRetry');
  if (retry) retry.onclick = async () => { if (await quickTurn({retry: true})) review.search(); };
}

async function quickTurn({retry = false} = {}) {
  quickAct.start('正在请求 AI 整理关键词和检索式…', AI_WAIT);
  $('#quickNote').hidden = true;
  if (review) review.setBusy(true);
  let result;
  try {
    result = await post(`/api/project-guidance/sessions/${session.id}/turn`, {message: session.draft.goal, retry});
  } catch (error) {
    quickAct.fail(`没能完成这一步：${error.message}`);
    const note = $('#quickNote');
    note.hidden = false;
    note.innerHTML = '<div class="meta"><button type="button" id="quickAgain">重试</button><button type="button" class="ghost" id="quickBack">返回修改</button></div>';
    $('#quickAgain').onclick = async () => { if (await quickTurn({retry: false})) review.search(); };
    $('#quickBack').onclick = async () => { await discardSession(); stopQuick(); };
    return false;
  }
  quickAct.stop();
  session = result.session;
  const entry = session.transcript[session.transcript.length - 1];
  renderQuickNote(entry, result);
  review.setDraft(session.draft, {flashNew: true});
  review.root.hidden = false;
  review.setBusy(false);
  return true;
}

$('#quickGo').onclick = async () => {
  const name = $('#quickName').value.trim(), goal = $('#quickGoal').value.trim();
  if (!name || !goal) { alert('请填写项目名称和研究目标'); return; }
  $('#quickGo').disabled = true;
  $('#quickStart').hidden = true; $('#quickWork').hidden = false;
  review = makeReview($('#quickReview'), {sessionId: () => session && session.id, onCreate: finalize});
  review.root.hidden = true;
  quickAct.start('正在创建草稿…');
  try {
    await createSession(name, goal, 'quick');
  } catch (error) {
    quickAct.stop(); stopQuick(); alert(error.message); return;
  }
  if (await quickTurn()) await review.search();
};

/* ------------------------------------------------------------------ guided creation */
const guidedAct = makeActivity($('#guidedActivity'));
let guidedBusy = false;

function stopGuided() {
  guidedAct.stop();
  $('#guidedStart').hidden = false; $('#guidedWork').hidden = true;
  $('#guideChat').replaceChildren(); $('#guidedReview').replaceChildren(); $('#guidedGo').disabled = false;
  guidedBusy = false;
}

function setComposer(enabled) {
  guidedBusy = !enabled;
  $('#guideSend').disabled = !enabled;
  $('#guideMessage').disabled = !enabled;
  if (review) review.setBusy(!enabled);
}

function bubble(entry, live) {
  const el = document.createElement('div');
  const user = entry.role === 'user';
  el.className = 'msg ' + (user ? 'user' : 'assistant');
  el.innerHTML = `<span class="who">${user ? '你：' : '助手：'}</span><span data-no-i18n>${esc(entry.content || '')}</span>`;
  if (!user) {
    el.insertAdjacentHTML('beforeend', `<div class="meta">${turnMeta(entry, live)} ${retryable(entry) ? '<button type="button" data-retry>重试 AI</button>' : ''} ${settingsLink(entry)}</div>`);
    const retry = $('[data-retry]', el);
    if (retry) retry.onclick = () => guidedTurn({retry: true});
  }
  return el;
}

function renderChat(live) {
  const chat = $('#guideChat');
  chat.replaceChildren(...session.transcript.map((entry, index) =>
    bubble(entry, index === session.transcript.length - 1 ? live : null)));
  // Only the newest answer may be retried: older ones were followed by more conversation.
  $$('[data-retry]', chat).slice(0, -1).forEach((button) => button.remove());
  chat.scrollTop = chat.scrollHeight;
  const used = session.turn_count || 0;
  $('#turnCounter').textContent = `AI 对话已用 ${used}/6 轮`;
  $('#guideSend').disabled = guidedBusy || used >= 6;
  if (used >= 6) $('#guideMessage').placeholder = '6 轮 AI 对话已用完，请直接编辑右侧草稿后创建';
}

function showPending(text) {
  const chat = $('#guideChat');
  const el = document.createElement('div');
  el.className = 'msg assistant pending';
  el.id = 'pendingBubble';
  el.innerHTML = `<span class="dots" aria-hidden="true"><i></i><i></i><i></i></span><span>${esc(text)}</span>`;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

async function guidedTurn({message = '', retry = false} = {}) {
  if (guidedBusy) return false;
  setComposer(false);
  const chat = $('#guideChat');
  if (!retry && message) {
    chat.appendChild(bubble({role: 'user', content: message}));
    $('#guideMessage').value = '';
  } else if (retry) {
    $$('.msg.assistant', chat).at(-1)?.remove();
  }
  showPending('正在请求 AI，整理你的方向…');
  guidedAct.start('正在请求 AI…', AI_WAIT);
  let result;
  try {
    result = await post(`/api/project-guidance/sessions/${session.id}/turn`, {
      message: retry ? undefined : message, retry, draft: review.draft()});
  } catch (error) {
    guidedAct.fail(`这一轮没有发出去：${error.message}`);
    if (!retry && message) $('#guideMessage').value = message;   // nothing was recorded; keep what was typed
    setComposer(true);
    renderChat(null);   // back to what the server holds
    return false;
  }
  guidedAct.stop();
  session = result.session;
  review.setDraft(session.draft, {flashNew: true});
  setComposer(true);
  renderChat(result);
  return true;
}

function openGuidedWorkspace() {
  $('#guidedStart').hidden = true; $('#guidedWork').hidden = false;
  review = makeReview($('#guidedReview'), {sessionId: () => session && session.id, onCreate: finalize});
}

$('#guidedGo').onclick = async () => {
  const name = $('#guidedName').value.trim(), goal = $('#guidedGoal').value.trim();
  if (!name || !goal) { alert('请填写项目名称和研究目标'); return; }
  $('#guidedGo').disabled = true;
  try {
    await createSession(name, goal, 'ai_guided');
  } catch (error) { alert(error.message); $('#guidedGo').disabled = false; return; }
  openGuidedWorkspace();
  review.setDraft(session.draft);
  renderChat(null);
  await guidedTurn({message: goal});   // the assistant answers the goal right away
};

const sendGuided = () => {
  const message = $('#guideMessage').value.trim();
  if (!message) { $('#guideMessage').focus(); return; }
  guidedTurn({message});
};
$('#guideSend').onclick = sendGuided;
$('#guideMessage').addEventListener('keydown', (event) => {
  if (event.isComposing) return;
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); sendGuided(); }
});

/* ------------------------------------------------------------------ manual creation */
const seedHint = (message) => { const el = $('#seedNote'); el.textContent = message; el.hidden = !message; };
const seedKeywords = makeChips($('#manualKeywords'), () => manualRefresh());
const seeds = [];
let seedSeq = 0, queue = Promise.resolve();
const queued = (fn) => { const run = queue.then(fn, fn); queue = run.catch(() => {}); return run; };   // one OpenAlex lookup at a time
const seedFailure = (r) => ({
  not_found: 'OpenAlex 里没有这篇（刚发布的论文可能还没收录）',
  unavailable: 'OpenAlex 暂时不可用（对方限流或维护中），稍后重试',
  network_error: '网络不通，没能连到 OpenAlex',
  invalid_input: r.error, failed: r.error || '解析失败',
}[r.status] || r.error || '解析失败');

function seedRow(item) {
  let li = $(`#seedList [data-id="${item.id}"]`);
  if (!li) { li = document.createElement('li'); li.dataset.id = item.id; $('#seedList').appendChild(li); }
  li.className = 'seed' + (item.status === 'failed' ? ' failed' : '');
  const origin = {id: 'DOI / 链接', name: '名称检索', pdf: 'PDF'}[item.kind];
  let state = '<span class="spinner"></span>', title = '', sub = '', help = '';
  const label = item.kind === 'pdf' ? item.filename : item.input;
  if (item.status === 'resolved') {
    state = '<span class="good">✓</span>';
    title = item.paper.title;
    sub = `<span data-no-i18n>${esc(meta(item.paper))}</span> <span class="tag">${esc(origin)}</span>${item.pdfId ? ` <span data-no-i18n>${esc(item.filename || '')}</span> <span class="good">PDF 创建后保存到这篇论文</span>` : ''}`;
  } else if (item.status === 'failed') {
    state = '<span class="bad">!</span>'; title = label;
    sub = `<span class="bad" data-no-i18n>${esc(item.error)}</span>`;
    help = `<div class="help"><div class="row"><input data-help-input placeholder="改填标题、DOI 或 arXiv 编号" value="${esc(item.guess || '')}"><button type="button" data-do="again">重试</button></div></div>`;
  } else if (item.status === 'help') {
    state = '<span class="warn">?</span>'; title = label;
    sub = `${item.error ? `<span class="bad" data-no-i18n>${esc(item.error)}</span> ` : ''}<span>没能确定是哪篇论文，请选一篇，或改标题/DOI 再查</span>`;
    help = `<div class="help">${(item.hits || []).map((p, i) => `<button type="button" class="pick" data-do="pick" data-index="${i}"><span data-no-i18n>${esc(p.title)}</span><small data-no-i18n>${esc(meta(p))}</small></button>`).join('')}
      <div class="row"><input data-help-input placeholder="标题、DOI 或 arXiv 编号" value="${esc(item.guess || '')}"><button type="button" data-do="again">再查一次</button></div></div>`;
  } else {
    title = label; sub = item.stage || '正在处理…';
  }
  li.innerHTML = `<span class="state">${state}</span><div class="title" data-no-i18n>${esc(title)}</div>
    <button type="button" class="ghost small remove" data-do="remove" title="移除" aria-label="移除">×</button>
    <div class="sub">${sub}</div>${help}`;
}

function seedUpdate(item, patch) {
  Object.assign(item, patch);
  seedRow(item);
  manualRefresh();
}

function seedAccept(item, paper) {
  const other = seeds.find((s) => s !== item && s.status === 'resolved' && s.paper.key === paper.key);
  if (other) {
    if (item.pdfId && !other.pdfId) { seedUpdate(other, {pdfId: item.pdfId, filename: item.filename}); }
    seedRemove(item);
    seedHint('这篇论文已经在种子列表里了。');
    return;
  }
  seedUpdate(item, {status: 'resolved', paper, error: null});
}

function seedRemove(item) {
  seeds.splice(seeds.indexOf(item), 1);
  $(`#seedList [data-id="${item.id}"]`)?.remove();
  manualRefresh();
}

function seedNew(kind, fields) {
  const item = {id: ++seedSeq, kind, status: 'working', stage: '正在排队…', ...fields};
  seeds.push(item); seedRow(item); manualRefresh();
  return item;
}

async function seedResolve(item, text) {
  seedUpdate(item, {status: 'working', stage: '正在向 OpenAlex 核对…', guess: text});
  try {
    const result = await queued(() => post('/api/seeds/resolve', {input: text}));
    if (result.status === 'resolved') seedAccept(item, result.paper);
    else seedUpdate(item, {status: 'failed', error: seedFailure(result), guess: text});
  } catch (error) {
    seedUpdate(item, {status: 'failed', error: error.message, guess: text});
  }
}

async function seedFromInput(text) {
  const input = text.trim();
  if (!input) return;
  if (!PDF.looksLikeIdentifier(input)) { openSeedSearch(input); return; }
  if (seeds.some((s) => s.kind === 'id' && s.input.toLowerCase() === input.toLowerCase())) {
    seedHint('这个标识已经添加过了。');
    return;
  }
  $('#seedInput').value = '';
  const item = seedNew('id', {input});
  await seedResolve(item, input);
}
$('#seedAdd').onclick = () => seedFromInput($('#seedInput').value);
$('#seedInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); seedFromInput($('#seedInput').value); }
});

/* ---- paper-name search for the seed box */
const searchAct = makeActivity($('#seedSearchActivity'));
let searchToken = 0;
async function openSeedSearch(query) {
  const token = ++searchToken;
  $('#seedSearch').hidden = false;
  $('#seedSearchTitle').textContent = `“${query}” 的检索结果`;
  $('#seedSearchList').innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
  $('#seedSearchNotice').hidden = true;
  searchAct.start('正在 OpenAlex 里按名称检索…');
  let result;
  try { result = await queued(() => post('/api/seeds/search', {query})); }
  catch (error) { result = {status: 'failed', error: error.message, items: []}; }
  if (token !== searchToken) return;
  searchAct.stop();
  $('#seedSearchList').innerHTML = '';
  const notice = $('#seedSearchNotice');
  if (!result.items.length) {
    notice.hidden = false; notice.classList.toggle('error', result.status !== 'empty');
    notice.textContent = result.status === 'empty' ? '没有找到。试试更完整的英文标题，或直接粘贴 DOI / arXiv 编号。' : seedFailure(result);
  }
  for (const paper of result.items) {
    const hit = document.createElement('div');
    hit.className = 'seed-hit';
    const added = () => seeds.some((s) => s.status !== 'failed' && s.paper && s.paper.key === paper.key);
    hit.innerHTML = `<div class="title" data-no-i18n>${esc(paper.title)}</div><div class="meta" data-no-i18n>${esc(meta(paper))}</div>
      <div class="abstract" data-no-i18n>${esc(paper.abstract || '')}</div><button type="button">添加</button>`;
    const button = $('button', hit);
    button.onclick = () => {
      if (added()) { seedRemoveByKey(paper.key); button.textContent = '添加'; return; }
      const item = seedNew('name', {input: paper.title});
      seedUpdate(item, {status: 'resolved', paper});
      button.textContent = '已添加';
    };
    button.title = '再点一次撤销';
    if (added()) button.textContent = '已添加';
    $('#seedSearchList').appendChild(hit);
  }
}
const seedRemoveByKey = (key) => { const item = seeds.find((s) => s.paper && s.paper.key === key); if (item) seedRemove(item); };
$('#seedSearchClose').onclick = () => { searchToken += 1; searchAct.stop(); $('#seedSearch').hidden = true; };

/* ---- dropped PDFs */
let pdfjs = null;
async function loadPdfjs() {
  if (pdfjs) return pdfjs;
  pdfjs = await import('/vendor/pdfjs/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.min.mjs';
  return pdfjs;
}

async function extractHints(file) {
  const lib = await loadPdfjs();
  const doc = await lib.getDocument({data: new Uint8Array(await file.arrayBuffer()), standardFontDataUrl: '/vendor/pdfjs/standard_fonts/'}).promise;
  try {
    const texts = [];
    let items = [], pageHeight = 0;
    for (let n = 1; n <= Math.min(2, doc.numPages); n += 1) {
      const page = await doc.getPage(n);
      const viewport = page.getViewport({scale: 1});
      const content = await page.getTextContent();
      texts.push(content.items.map((i) => i.str).join(' '));
      if (n === 1) {
        pageHeight = viewport.height;
        items = content.items.filter((i) => i.str && i.str.trim())
          .map((i) => ({str: i.str, height: Math.abs(i.transform[3]) || i.height, y: viewport.height - i.transform[5]}));
      }
    }
    let info = null;
    try { info = (await doc.getMetadata()).info; } catch (error) { /* metadata is optional */ }
    return PDF.identify({pageTexts: texts, items, pageHeight, info, filename: file.name});
  } finally { doc.destroy(); }
}
const withTimeout = (promise, ms) => Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error('读取超时')), ms))]);

async function uploadPdf(file) {
  let response;
  try {
    response = await fetch('/api/seeds/pdf', {method: 'POST', body: file,
      headers: {'Content-Type': 'application/pdf', 'X-Filename': encodeURIComponent(file.name)}});
  } catch (error) { throw new Error('无法连接本地服务'); }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || 'PDF 导入失败');
  return body;
}

async function pdfProcess(item, file) {
  seedUpdate(item, {stage: '正在读取 PDF 首页…'});
  const [uploaded, hints] = await Promise.allSettled([uploadPdf(file), withTimeout(extractHints(file), 25000)]);
  if (uploaded.status === 'rejected') { seedUpdate(item, {status: 'failed', error: uploaded.reason.message}); return; }
  item.pdfId = uploaded.value.pdf_id;
  if (hints.status === 'rejected') {
    seedUpdate(item, {status: 'help', hits: [], guess: '', stage: '',
      error: '读不出这个 PDF 的文字（可能是扫描件）'});
    return;
  }
  const found = hints.value;
  const ids = [found.arxiv, found.doi].filter(Boolean);
  let lastFailure = null;
  for (const id of ids) {
    seedUpdate(item, {stage: `识别到 ${id}，正在核对…`});
    try {
      const result = await queued(() => post('/api/seeds/resolve', {input: id}));
      if (result.status === 'resolved') { seedAccept(item, result.paper); return; }
      lastFailure = result;
    } catch (error) { lastFailure = {status: 'failed', error: error.message}; }
  }
  const hits = [];
  for (const title of found.titles) {
    seedUpdate(item, {stage: `按标题检索：${title}`});
    let result;
    try { result = await queued(() => post('/api/seeds/search', {query: title})); }
    catch (error) { lastFailure = {status: 'failed', error: error.message}; continue; }
    if (result.status !== 'ok' && result.status !== 'empty') { lastFailure = result; continue; }
    const best = result.items.map((p) => ({p, score: PDF.similarity(title, p.title)})).sort((a, b) => b.score - a.score)[0];
    if (best && best.score >= 0.8) { seedAccept(item, best.p); return; }   // the same title: no need to ask
    for (const p of result.items) if (!hits.some((h) => h.key === p.key)) hits.push(p);
  }
  seedUpdate(item, {status: 'help', hits: hits.slice(0, 5), guess: found.titles[0] || found.arxiv || found.doi || '',
    error: lastFailure ? seedFailure(lastFailure) : null});
}

function addPdfFiles(files) {
  for (const file of files) {
    if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
      seedHint(`「${file.name}」不是 PDF，已忽略。`);
      continue;
    }
    pdfProcess(seedNew('pdf', {filename: file.name, input: file.name}), file);
  }
}

const zone = $('#dropzone');
zone.onclick = () => $('#pdfPick').click();
zone.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); $('#pdfPick').click(); } });
$('#pdfPick').onchange = (event) => { addPdfFiles([...event.target.files]); event.target.value = ''; };
['dragenter', 'dragover'].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add('over'); }));
['dragleave', 'drop'].forEach((name) => zone.addEventListener(name, () => zone.classList.remove('over')));
zone.addEventListener('drop', (event) => { event.preventDefault(); event.stopPropagation(); addPdfFiles([...event.dataTransfer.files]); });
// A PDF dropped anywhere else must not navigate the window away; outside manual creation it opens that mode.
window.addEventListener('dragover', (event) => event.preventDefault());
window.addEventListener('drop', async (event) => {
  event.preventDefault();
  if (!event.dataTransfer || !event.dataTransfer.files.length) return;
  if (mode !== 'manual') {
    if (session) return;
    setMode('manual');
  }
  addPdfFiles([...event.dataTransfer.files]);
});

/* ---- help rows: pick a hit, retry with other text, remove */
$('#seedList').addEventListener('click', (event) => {
  const button = event.target.closest('[data-do]');
  if (!button) return;
  const item = seeds.find((s) => String(s.id) === button.closest('li').dataset.id);
  if (!item) return;
  const action = button.dataset.do;
  if (action === 'remove') seedRemove(item);
  else if (action === 'pick') seedAccept(item, item.hits[Number(button.dataset.index)]);
  else if (action === 'again') {
    const text = $('[data-help-input]', button.closest('li')).value.trim();
    if (!text) return;
    if (PDF.looksLikeIdentifier(text)) seedResolve(item, text);
    else searchForItem(item, text);
  }
});

async function searchForItem(item, title) {
  seedUpdate(item, {status: 'working', stage: `按标题检索：${title}`, guess: title});
  let result;
  try { result = await queued(() => post('/api/seeds/search', {query: title})); }
  catch (error) { result = {status: 'failed', error: error.message, items: []}; }
  if (result.status !== 'ok' && result.status !== 'empty') { seedUpdate(item, {status: 'failed', error: seedFailure(result), guess: title}); return; }
  const best = result.items.map((p) => ({p, score: PDF.similarity(title, p.title)})).sort((a, b) => b.score - a.score)[0];
  if (best && best.score >= 0.8) { seedAccept(item, best.p); return; }
  seedUpdate(item, {status: 'help', hits: result.items.slice(0, 5), guess: title,
    error: result.items.length ? null : '没有找到，试试更完整的英文标题'});
}

/* ---- create */
const manualAct = makeActivity($('#manualActivity'));
function manualRefresh() {
  const working = seeds.filter((s) => s.status === 'working').length;
  const ready = seeds.filter((s) => s.status === 'resolved').length;
  const keywords = seedKeywords.get().length;
  const parts = [];
  if (keywords) parts.push(`${keywords} 个关键词`);
  if (ready) parts.push(`${ready} 篇种子论文`);
  if (working) parts.push(`${working} 个种子仍在处理`);
  $('#manualSummary').textContent = parts.join('，');
  $('#manualCreate').disabled = !!working || !(keywords || ready);
  $('#manualCreate').title = working ? '请等种子处理完成' : (keywords || ready ? '' : '至少需要 1 个关键词或 1 篇种子论文');
}

$('#manualCreate').onclick = async () => {
  const name = $('#manualName').value.trim();
  seedKeywords.commit();
  if (!name) { alert('请填写项目名称'); $('#manualName').focus(); return; }
  const payload = seeds.filter((s) => s.status === 'resolved')
    .map((s) => (s.pdfId ? {identifier: s.paper.openalex_id, pdf_id: s.pdfId} : s.paper.openalex_id));
  $('#manualCreate').disabled = true;
  manualAct.start(payload.length ? `正在创建项目并导入 ${payload.length} 篇种子论文…` : '正在创建项目…');
  let result;
  try {
    result = await post('/api/projects', {name, creation_mode: 'manual', keywords: seedKeywords.get(), seeds: payload});
  } catch (error) {
    manualAct.fail(error.message); manualRefresh(); return;
  }
  manualAct.stop();
  const go = `/?project_id=${encodeURIComponent(result.project_id)}`;
  const problems = (result.seed_results || []).filter((r) => !['resolved', 'duplicate'].includes(r.status) || r.pdf_attached === false);
  if (!problems.length) { location.href = go; return; }
  const box = $('#manualResult');
  box.hidden = false;
  box.innerHTML = `<div><strong>项目已创建，但有 ${problems.length} 个种子没有完全导入：</strong></div>`
    + problems.map((r) => `<div class="bad" data-no-i18n>${esc(r.input)}：${esc(r.pdf_error || r.error || r.status)}</div>`).join('')
    + '<div class="actions"><button type="button" class="primary" id="enterProject">进入项目</button></div>';
  $('#enterProject').onclick = () => { location.href = go; };
};
$('#manualName').addEventListener('input', manualRefresh);
manualRefresh();

/* ------------------------------------------------------------------ resume an unfinished draft */
async function resume() {
  const id = localStorage.getItem(SESSION_KEY);
  if (!id) return;
  let saved;
  try { saved = (await api(`/api/project-guidance/sessions/${id}`)).session; } catch (error) { localStorage.removeItem(SESSION_KEY); return; }
  if (saved.status !== 'draft') { localStorage.removeItem(SESSION_KEY); return; }
  session = saved;
  if (saved.draft.creation_mode === 'quick') {
    setMode('quick');
    $('#quickStart').hidden = true; $('#quickWork').hidden = false;
    review = makeReview($('#quickReview'), {sessionId: () => session && session.id, onCreate: finalize});
    review.setDraft(saved.draft);
    const last = saved.transcript[saved.transcript.length - 1];
    if (last && last.role === 'assistant') renderQuickNote(last, null);
  } else {
    setMode('ai_guided');
    openGuidedWorkspace();
    review.setDraft(saved.draft);
    renderChat(null);
  }
}
resume();
})();
