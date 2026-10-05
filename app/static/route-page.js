/* The learning-map page: progress per concept, marks that can be undone, and edits to the map itself.
   Reads and writes /api/route only. It never calls the AI. */
'use strict';
const R = window.PDHRoute;
const $ = (s, r = document) => r.querySelector(s);
const part = (role) => $(`[data-role="${role}"]`);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const projectId = new URLSearchParams(location.search).get('project_id') || localStorage.getItem('pdh-current-project') || '';
const state = {route: null, draft: null, dirty: false, checking: false, busy: false, annotated: false};

async function api(body) {
  const options = body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({project_id: projectId, ...body})} : {};
  const res = await fetch(body ? '/api/route' : `/api/route?project_id=${encodeURIComponent(projectId)}`, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function notice(message, isError = true) {
  const el = part('notice');
  el.hidden = !message; el.textContent = message || ''; el.classList.toggle('error', isError);
}

const CONFLICT = '学习图刚刚在别处改动过，已刷新到最新版本；你没有保存的修改还在，请再试一次。';

async function refreshRoute() {
  // The server's version only (revision and progress); the draft being edited is left alone.
  try { state.route = {...(await api()), graph: state.route && state.route.graph ? state.route.graph : null}; } catch (error) { /* shown by the caller */ }
}

async function guarded(action) {
  if (state.busy) return;
  state.busy = true; document.body.classList.add('busy');
  try { await action(); }
  catch (error) {
    notice(/revision conflict/i.test(error.message) ? CONFLICT : error.message);
    await refreshRoute();
    render();
  } finally { state.busy = false; document.body.classList.remove('busy'); }
}

async function load() {
  try {
    state.route = await api();
    state.draft = state.route.graph ? JSON.parse(JSON.stringify(state.route.graph)) : null;
    state.dirty = false; state.annotated = false;
    render();
  } catch (error) { notice(error.message); }
}

function render() {
  const route = state.route, graph = state.draft;
  part('back').href = projectId ? `/?project_id=${encodeURIComponent(projectId)}` : '/';
  part('empty').hidden = !!graph;
  part('main').hidden = !graph;
  if (!graph) return;
  part('summary').textContent = R.summaryText(route);
  part('modeSwitch').checked = !!route.enabled;
  part('modeSwitch').disabled = !(state.route && state.route.graph);   // nothing to switch before the first save
  part('save').hidden = part('discard').hidden = !state.dirty;
  const holder = part('map');
  holder.replaceChildren();
  R.columns(graph).forEach((col, index) => {
    const column = document.createElement('div');
    column.className = 'map-col';
    column.innerHTML = `<h4>第 ${index + 1} 层</h4>`;
    col.forEach((concept) => column.appendChild(card(graph, concept)));
    holder.appendChild(column);
  });
}

function card(graph, concept) {
  const progress = (state.route.progress || {})[concept.id];
  const el = document.createElement('div');
  const known = !state.dirty && progress;   // progress belongs to the saved map; structural edits have none until saved
  const status = known ? progress.status : 'proposed';
  el.className = `map-card${concept.side ? ' side' : ''}${status === 'satisfied' ? ' mastered' : ''}`;
  const needs = R.needsOf(graph, concept.id);
  const word = known ? R.STATUS[status] || '' : '未保存';
  const title = status === 'locked' ? R.LOCKED_TITLE : (known && progress.low_interest ? R.LOW_INTEREST_TITLE : '');
  el.innerHTML = `<span class="name" data-no-i18n>${esc(concept.name)}</span>
    ${(concept.terms || []).length ? `<div class="terms" data-no-i18n>${esc(concept.terms.join(' · '))}</div>` : '<div class="terms">（没有检索词）</div>'}
    <div class="badges"><span class="badge st-${esc(status)}" title="${esc(title)}">${esc(word)}</span>${known && progress.low_interest ? `<span class="badge" title="${esc(R.LOW_INTEREST_TITLE)}">暂不优先</span>` : ''}${known && progress.manual === 'mastered' ? '<span class="badge">你标为已掌握</span>' : ''}</div>
    ${needs.length ? `<div class="needs">前置：${needs.map((n) => `<span class="need ${n.label}" title="${esc(R.LABELS[n.label])}" data-no-i18n>${esc(n.name)}</span>`).join('、')}</div>` : ''}
    ${known ? `<div class="counts">${esc(R.countsText(progress))}</div>` : ''}
    ${concept.papers !== undefined ? `<div class="counts ${concept.grounding === 'ok' ? '' : 'none'}">公开文献里约 ${concept.papers} 篇</div>` : ''}
    <div class="row"></div>`;
  const row = $('.row', el);
  if (known) {
    R.actionsFor(progress).forEach((action) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'ghost small'; button.textContent = action.label;
      button.onclick = () => mark(concept.id, action.clear ? null : action.value);
      row.appendChild(button);
    });
  }
  const edit = document.createElement('button');
  edit.type = 'button'; edit.className = 'ghost small'; edit.textContent = '编辑';
  edit.onclick = () => editConcept(el, graph, concept);
  const del = document.createElement('button');
  del.type = 'button'; del.className = 'ghost small'; del.textContent = '删除';
  del.onclick = () => change(R.removeConcept(graph, concept.id));
  row.append(edit, del);
  return el;
}

async function mark(concept, value) {
  await guarded(async () => {
    state.route = await api({action: 'manual', concept, value, revision: state.route.revision});
    state.draft = JSON.parse(JSON.stringify(state.route.graph)); state.dirty = false; state.annotated = false;
    notice(''); render();
  });
}

function change(next) {
  if (state.checking) { notice('正在核对，请稍候再修改。'); return; }
  state.draft = next; state.dirty = true; state.annotated = false; notice(''); render();
}

function editConcept(el, graph, concept) {
  el.innerHTML = `<input class="edit" data-role="n" maxlength="60" placeholder="概念名称" aria-label="概念名称">
    <input class="edit" data-role="t" maxlength="130" placeholder="两个英文检索词，用 / 分隔" aria-label="英文检索词">
    ${R.needsEditorHTML(graph, concept.id)}
    <div class="row"><button type="button" class="small" data-act="ok">确定</button><button type="button" class="ghost small" data-act="no">取消</button></div>`;
  $('[data-role=n]', el).value = concept.name;
  $('[data-role=t]', el).value = (concept.terms || []).join(' / ');
  $('[data-act=no]', el).onclick = render;
  $('[data-act=ok]', el).onclick = () => {
    try {
      let next = R.rename(graph, concept.id, $('[data-role=n]', el).value, $('[data-role=t]', el).value.split('/'));
      next = R.setNeeds(next, concept.id, R.readNeeds(el));
      change(next);
    } catch (error) { notice(error.message); }
  };
}

part('add').onclick = () => {
  try { change(R.addConcept(state.draft, {name: '新概念', terms: [], hint: 2}, [])); }
  catch (error) { notice(error.message); }
};
part('startEmpty').onclick = () => {
  state.draft = {concepts: [{id: 'c1', name: '第一个概念', terms: [], hint: 1, origin: 'user', state: 'active', side: false}], prereqs: [], targets: ['c1']};
  state.route = {...(state.route || {}), progress: {}, total: 1, done: 0, exploration_share: 0.1, enabled: true};
  state.dirty = true; render();
};
part('discard').onclick = () => { if (!state.checking) load(); };
part('save').onclick = () => guarded(async () => {
  const verdict = R.check(state.draft);
  if (!verdict.ok) { notice(`学习图还不能保存：${verdict.reason}`); return; }
  state.route = await api({action: 'save', graph: state.draft, revision: state.route.revision ?? 0});
  state.draft = JSON.parse(JSON.stringify(state.route.graph)); state.dirty = false; state.annotated = false;
  notice('已保存。', false); render();
});
part('modeSwitch').onchange = () => guarded(async () => {
  if (!state.route || !state.route.graph) return;
  state.route = await api({action: 'mode', mode: part('modeSwitch').checked ? 'route' : 'off', revision: state.route.revision});
  notice(''); render();
});
part('check').onclick = async () => {
  if (state.checking || state.busy) return;
  const verdict = R.check(state.draft);
  if (!verdict.ok) { notice(`学习图还不能核对：${verdict.reason}`); return; }
  const sent = state.draft;
  state.checking = true; part('check').disabled = true; notice('正在用公开文献核对每个概念（OpenAlex，只发送检索词；这期间不能修改）…', false);
  try {
    const out = await api({action: 'ground', graph: sent});
    if (state.draft !== sent) return;   // the draft was replaced while the request ran (discard, save): drop the answer
    state.draft = out.graph; state.annotated = true; render();
    const missing = out.graph.concepts.filter((c) => c.grounding === 'none').length;
    notice(missing ? `有 ${missing} 个概念在公开文献里没找到，可以改检索词或删除。` : '核对完成。', !!missing);
  } catch (error) { notice(error.message); }
  finally { state.checking = false; part('check').disabled = false; }
};

(async () => {
  if (!projectId) { notice('没有指定项目。请从今日推荐页进入。'); return; }
  try {
    const projects = (await (await fetch('/api/projects')).json()).projects || [];
    const current = projects.find((p) => p.id === projectId);
    if (current) part('project').textContent = current.name;
  } catch (error) { /* the name is decoration */ }
  await load();
})();
