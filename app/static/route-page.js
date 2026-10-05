/* The learning-map page: the map drawn as a graph, progress per concept, marks that can be undone, and edits to the
   map itself. Reads and writes /api/route only. The one model-backed action is the explicit "draft with AI" click
   (action 'plan'); it returns a draft that changes nothing until the person saves. */
'use strict';
const R = window.PDHRoute;
const $ = (s, r = document) => r.querySelector(s);
const part = (role) => $(`[data-role="${role}"]`);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const projectId = new URLSearchParams(location.search).get('project_id') || localStorage.getItem('pdh-current-project') || '';
const state = {route: null, draft: null, dirty: false, checking: false, busy: false, annotated: false, selected: null, editing: null, graph: null, project: null};

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
  const saved = !!(state.route && state.route.graph);   // nothing to switch before the first save
  part('modeSeg').querySelectorAll('button').forEach((b) => {
    b.setAttribute('aria-checked', String((b.dataset.mode === 'route') === !!route.enabled));
    b.disabled = !saved;
  });
  part('modeNote').textContent = !saved ? '先保存一次学习图，才能切换推荐方式。' : route.enabled ? '推荐先从你现在能读的概念里选论文。' : '现在推荐按普通排序。'
  part('save').hidden = part('discard').hidden = !state.dirty;
  const shape = R.shape(graph);
  part('shape').textContent = R.shapeText(shape);
  part('shape').classList.toggle('single', shape.chain);
  if (state.selected && !graph.concepts.some((c) => c.id === state.selected)) state.selected = state.editing = null;
  const known = !state.dirty;   // progress belongs to the saved map; structural edits have none until saved
  // a re-draw keeps the zoom, the scroll position and the focused concept
  const keep = state.graph ? state.graph.view() : undefined;
  const focused = document.activeElement && document.activeElement.closest ? document.activeElement.closest('.rg-node') : null;
  if (state.graph) state.graph.destroy();
  state.graph = window.PDHGraph.mount(part('graph'), graph, {
    selected: state.selected,
    view: keep,
    maxHeight: '68vh',
    onRescale: () => render(),
    canSelect: () => {
      if (state.editing) { notice('先点“确定”或“取消”，再选别的概念。'); return false; }
      return true;
    },
    statusOf: (concept) => R.nodeStatus(concept, route.progress, known),
    extraClass: (concept) => (known && route.progress && route.progress[concept.id] && route.progress[concept.id].manual === 'mastered' ? 'mastered' : ''),
    edgeState: (from, to) => (known && route.progress && route.progress[from] && route.progress[from].status === 'satisfied' ? 'met'
      : known && route.progress && route.progress[to] && route.progress[to].status === 'locked' ? 'wait' : 'plain'),
    onSelect: (id) => { state.selected = id; state.editing = null; renderDetail(); },
  });
  if (focused && focused.dataset.id) state.graph.focusNode(focused.dataset.id);
  renderDetail();
}

function renderDetail() {
  const graph = state.draft, holder = part('detail');
  const concept = graph && graph.concepts.find((c) => c.id === state.selected);
  if (!concept) {
    holder.innerHTML = '<div class="map-note">点一个概念：这里会显示它需要先读懂什么、读懂后可以读什么，也可以在这里标记或编辑它。</div>';
    return;
  }
  const known = !state.dirty && state.route.progress;
  if (state.editing === concept.id) { editConcept(holder, graph, concept); return; }
  holder.innerHTML = `${R.detailHTML(graph, concept, {progress: known ? state.route.progress : null})}<div class="row"></div>`;
  const row = $('.row', holder);
  const progress = known ? state.route.progress[concept.id] : null;
  if (progress) {
    R.actionsFor(progress).forEach((action) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'ghost small'; button.textContent = action.label;
      button.onclick = () => mark(concept.id, action.clear ? null : action.value);
      row.appendChild(button);
    });
  }
  const edit = document.createElement('button');
  edit.type = 'button'; edit.className = 'ghost small'; edit.textContent = '编辑';
  edit.onclick = () => { state.editing = concept.id; renderDetail(); };
  const del = document.createElement('button');
  del.type = 'button'; del.className = 'ghost small'; del.textContent = '删除';
  del.onclick = () => { state.selected = state.editing = null; change(R.removeConcept(graph, concept.id)); };
  row.append(edit, del);
}

async function mark(concept, value) {
  await guarded(async () => {
    state.route = await api({action: 'manual', concept, value, revision: state.route.revision});
    state.draft = JSON.parse(JSON.stringify(state.route.graph)); state.dirty = false; state.annotated = false;
    notice(''); render();
  });
}

function change(next) {
  if (state.checking || state.busy) { notice(state.busy ? '正在处理上一步，请稍候再修改。' : '正在核对，请稍候再修改。'); return; }
  state.draft = next; state.dirty = true; state.annotated = false; notice(''); render();
}

function editConcept(holder, graph, concept) {
  holder.innerHTML = `<input class="edit" data-role="n" maxlength="60" placeholder="概念名称" aria-label="概念名称">
    <input class="edit" data-role="t" maxlength="130" placeholder="两个英文检索词，用 / 分隔" aria-label="英文检索词">
    ${R.needsEditorHTML(graph, concept.id)}
    <div class="row"><button type="button" class="small" data-act="ok">确定</button><button type="button" class="ghost small" data-act="no">取消</button></div>`;
  $('[data-role=n]', holder).value = concept.name;
  $('[data-role=t]', holder).value = (concept.terms || []).join(' / ');
  $('[data-act=no]', holder).onclick = () => { state.editing = null; renderDetail(); };
  $('[data-act=ok]', holder).onclick = () => {
    try {
      let next = R.rename(graph, concept.id, $('[data-role=n]', holder).value, $('[data-role=t]', holder).value.split('/'));
      next = R.setNeeds(next, concept.id, R.readNeeds(holder));
      state.editing = null;
      change(next);
    } catch (error) { notice(error.message); }
  };
}

part('add').onclick = () => {
  try {
    let name = '新概念', n = 1;
    while (state.draft.concepts.some((c) => c.name === name)) name = `新概念 ${++n}`;
    const next = R.addConcept(state.draft, {name, terms: [], hint: 2}, []);
    state.selected = state.editing = next.concepts[next.concepts.length - 1].id;
    change(next);
  } catch (error) { notice(error.message); }
};
part('startEmpty').onclick = () => {
  state.draft = {concepts: [{id: 'c1', name: '第一个概念', terms: [], hint: 1, origin: 'user', state: 'active', side: false}], prereqs: [], targets: ['c1']};
  state.route = {...(state.route || {}), progress: {}, total: 1, done: 0, exploration_share: 0.1, enabled: true};
  state.dirty = true; state.selected = 'c1'; state.editing = null; render();
};
part('discard').onclick = () => { if (!state.checking && !state.busy) load(); };
part('save').onclick = () => guarded(async () => {
  const verdict = R.check(state.draft);
  if (!verdict.ok) { notice(`学习图还不能保存：${verdict.reason}`); return; }
  state.route = await api({action: 'save', graph: state.draft, revision: state.route.revision ?? 0});
  state.draft = JSON.parse(JSON.stringify(state.route.graph)); state.dirty = false; state.annotated = false;
  notice('已保存。', false); render();
});
part('modeSeg').onclick = (event) => {
  const choice = event.target.closest('button[data-mode]');
  if (!choice || choice.disabled || choice.getAttribute('aria-checked') === 'true') return;
  guarded(async () => {
    if (!state.route || !state.route.graph) return;
    state.route = await api({action: 'mode', mode: choice.dataset.mode, revision: state.route.revision});
    notice(''); render();
  });
};
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

function defaultGoal() {
  const project = state.project || {};
  return [project.name, ...((project.keywords || []).slice(0, 5))].filter(Boolean).join('，').slice(0, 250);
}
function openAi() {
  part('aiBox').hidden = false;
  part('aiWarn').textContent = [state.dirty ? '你有没保存的修改，AI 草稿会替换掉它们。' : '',
    state.route && state.route.graph ? '保存草稿时，你在现在这张图上做的“已掌握 / 手动解锁”标记只会保留给名字相同的概念。' : ''].filter(Boolean).join(' ');
  if (!part('goal').value) part('goal').value = defaultGoal();
  part('goal').focus();
}
part('aiOpen').onclick = part('aiOpen2').onclick = openAi;
part('aiCancel').onclick = () => { if (!state.busy) part('aiBox').hidden = true; };
part('aiGo').onclick = () => guarded(async () => {
  const goal = part('goal').value.trim();
  if (!goal) { notice('请先写下你想学什么。'); return; }
  part('aiGo').disabled = true; part('aiActivity').textContent = 'AI 正在起草（约 10–30 秒）…'; notice('');
  try {
    const out = await api({action: 'plan', goal});
    if (!out.ok) {
      notice(out.reason_code === 'not_approved'
        ? '“为已有项目起草学习图”这项 AI 调用还在等你批准（harness/budget.json 里的 learning_path_plan_project）。批准之前，可以自己搭学习图。'
        : `没有使用 AI：${out.reason || 'AI 没有给出学习图'}。可以自己搭，或稍后再试。`);
      return;
    }
    state.route = {...(state.route || {}), progress: (state.route && state.route.progress) || {}, enabled: state.route ? state.route.enabled : true};
    if (!state.route.graph) Object.assign(state.route, {total: out.graph.concepts.length, done: 0, exploration_share: 0.1});
    state.draft = R.reuseIds(out.graph, state.route.graph); state.dirty = true; state.annotated = false; state.selected = state.editing = null;
    part('aiBox').hidden = true;
    const fixed = out.report ? ((out.report.dropped_edges || []).length + (out.report.merged || []).length) : 0;
    notice(`AI 已回复${out.tokens ? ` · 约 ${out.tokens} token` : ''}${fixed ? ` · 已自动修复 ${fixed} 处（重复概念、成环或多余的边）` : ''}。这是草稿，点“保存”才会生效；今天这个项目还能再生成 ${out.attempts_left} 次。`, false);
    render();
  } finally { part('aiGo').disabled = false; part('aiActivity').textContent = ''; }
});
window.addEventListener('beforeunload', (event) => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });

(async () => {
  if (!projectId) { notice('没有指定项目。请从今日推荐页进入。'); return; }
  try {
    const projects = (await (await fetch('/api/projects')).json()).projects || [];
    const current = projects.find((p) => p.id === projectId);
    if (current) { part('project').textContent = current.name; state.project = current; }
  } catch (error) { /* the name is decoration */ }
  await load();
})();
