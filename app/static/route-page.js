/* The learning-map page: the map drawn as a graph, progress per concept, marks that can be undone, and edits to the
   map itself. Reads and writes /api/route only. The one model-backed action is the explicit "draft with AI" click
   (action 'plan'); it returns a draft that changes nothing until the person saves. */
'use strict';
const R = window.PDHRoute;
const $ = (s, r = document) => r.querySelector(s);
const part = (role) => $(`[data-role="${role}"]`);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const projectId = new URLSearchParams(location.search).get('project_id') || localStorage.getItem('pdh-current-project') || '';
const state = {pendingIntro: null, route: null, draft: null, dirty: false, checking: false, busy: false, annotated: false, selected: null, editing: null, graph: null, project: null};

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
  // Preserve an edited draft, but a clean page must show the graph belonging to
  // the new revision before another watch/manual action can use that revision.
  try {
    state.route = await api();
    if (!state.dirty) {
      state.draft = state.route.graph ? JSON.parse(JSON.stringify(state.route.graph)) : null;
      state.annotated = false;
    }
  } catch (error) { /* shown by the caller */ }
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
    loadGrowth();   // the forming directions are on the page from the start; the map itself does not wait for them
  } catch (error) { notice(error.message); }
}

function render() {
  const route = state.route, graph = state.draft;
  part('back').href = projectId ? `/?project_id=${encodeURIComponent(projectId)}` : '/';
  part('empty').hidden = !!graph;
  part('main').hidden = !graph;
  if (!graph) return;
  part('summary').textContent = state.dirty ? '学习图有未保存的修改，目标状态在保存后重新计算。' : R.summaryText(route);
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
  const picked = growth.selected && growth.result && (growth.result.candidates || []).find((c) => c.id === growth.selected);
  if (growth.selected && !picked) growth.selected = null;
  const shown = picked ? R.ghostGraph(graph, [picked]) : graph;   // for drawing only, and only the direction you clicked: ghosts are never part of the draft
  if (state.selected && !shown.concepts.some((c) => c.id === state.selected)) state.selected = state.editing = null;
  const known = !state.dirty;   // progress belongs to the saved map; structural edits have none until saved
  // a re-draw keeps the zoom, the scroll position and the focused concept
  const keep = state.graph ? state.graph.view() : undefined;
  const focused = document.activeElement && document.activeElement.closest ? document.activeElement.closest('.rg-node') : null;
  if (state.graph) state.graph.destroy();
  state.graph = window.PDHGraph.mount(part('graph'), shown, {
    selected: state.selected,
    view: keep,
    maxHeight: '68vh',
    onRescale: () => render(),
    canSelect: () => {
      if (state.editing) { notice('先点“确定”或“取消”，再选别的概念。'); return false; }
      return true;
    },
    statusOf: (concept) => (concept.ghost ? R.ghostStatus(concept.candidate) : R.nodeStatus(concept, route.progress, known)),
    extraClass: (concept) => (concept.ghost ? `ghost${concept.candidate.status === 'ready' ? ' ready' : ''}`
      : known && route.progress && route.progress[concept.id] && route.progress[concept.id].manual === 'mastered' ? 'mastered' : ''),
    decorate: (el, concept, node) => { if (concept.ghost) el.insertAdjacentHTML('beforeend', R.ringSVG(concept.candidate.progress, concept.candidate.status === 'ready', node.w, node.h)); },
    edgeState: (from, to) => ((String(from).startsWith('ghost:') || String(to).startsWith('ghost:')) ? 'ghost' : known && route.progress && route.progress[from] && route.progress[from].status === 'satisfied' ? 'met'
      : known && route.progress && route.progress[to] && route.progress[to].status === 'locked' ? 'wait' : 'plain'),
    onSelect: (id) => {
      state.selected = id; state.editing = null; state.pendingIntro = null;
      if (!String(id).startsWith('ghost:') && growth.selected) { growth.selected = null; render(); return; }   // another node: the preview goes away
      renderDetail(); renderGrowth();
    },
  });
  if (state.selected && String(state.selected).startsWith('ghost:')) state.graph.focusNode(state.selected);
  else if (focused && focused.dataset.id) state.graph.focusNode(focused.dataset.id);
  renderDetail();
  renderGrowth();   // its buttons are off while there are unsaved edits
}

function renderDetail() {
  const graph = state.draft, holder = part('detail');
  if (String(state.selected || '').startsWith('ghost:')) {   // a direction that is forming: its evidence, not a concept
    const found = growth.result && (growth.result.candidates || []).find((c) => `ghost:${c.id}` === state.selected);
    if (found) { holder.innerHTML = R.ghostDetailHTML(found, {locked: state.dirty}); return; }
  }
  const concept = graph && graph.concepts.find((c) => c.id === state.selected);
  if (!concept) {
    holder.innerHTML = '<div class="map-note">点一个概念：这里会显示它需要先读懂什么、读懂后可以读什么，也可以在这里标记或编辑它。</div>';
    return;
  }
  const known = !state.dirty && state.route.progress;
  if (state.editing === concept.id) { editConcept(holder, graph, concept); return; }
  holder.innerHTML = `${R.detailHTML(graph, concept, {progress: known ? state.route.progress : null, canEdit: true})}<div class="row"></div>`;
  const row = $('.row', holder);
  const progress = known ? state.route.progress[concept.id] : null;
  if (progress && (concept.state || 'active') === 'active') {
    row.insertAdjacentHTML('beforebegin', R.watchHTML((state.route.watch || []).includes(concept.id), progress.status === 'satisfied'));
    $('[data-route-watch]', holder).onchange = (event) => watch(concept.id, event.target.checked);
  }
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
  const stored = !state.dirty && !!(state.route && state.route.graph && state.route.graph.concepts.some((c) => c.id === concept.id));   // the server only knows saved concepts
  if (stored) {
    const ask = document.createElement('button');
    ask.type = 'button'; ask.className = 'ghost small'; ask.textContent = concept.intro ? '让 AI 重写简介' : '让 AI 写简介';
    ask.title = '点一次调用一次 AI：只发送概念名、检索词、项目名称和前 3 个关键词（合计前 40 个字），以及这个项目里匹配到该概念的最多 3 篇论文的标题和摘要节选；结果先放进编辑框，你点“确定”和“保存”才会生效';
    ask.onclick = () => askIntro(concept.id);
    row.appendChild(ask);
    const examples = document.createElement('button');
    examples.type = 'button'; examples.className = 'ghost small'; examples.textContent = '看公开文献里的代表论文';
    examples.title = '只发送这个概念的第一个检索词去公开文献库搜一次，结果不保存';
    examples.onclick = () => showExamples(concept.id);
    row.appendChild(examples);
    showMatched(concept.id);
  }
  const del = document.createElement('button');
  del.type = 'button'; del.className = 'ghost small'; del.textContent = '删除';
  del.onclick = () => { state.selected = state.editing = null; change(R.removeConcept(graph, concept.id)); };
  row.append(edit, del);
}

/* What a concept is: the project's own papers that use it (read when it is selected), a few public ones (on click),
   and one sentence from the model (on click). None of it is saved until the person saves the map. */
async function showMatched(id) {
  const box = $('[data-concept-papers]', part('detail'));
  if (!box) return;
  try {
    const out = await api({action: 'concept-papers', concept: id});
    if (state.selected === id && box.isConnected) box.innerHTML = R.matchedPapersHTML(out);
  } catch (error) { /* a concept the server does not know yet (an unsaved one) just has no list */ }
}
async function showExamples(id) {
  const box = $('[data-concept-examples]', part('detail'));
  if (!box) return;
  box.innerHTML = '<p class="map-note">正在公开文献里找…</p>';
  try {
    const out = await api({action: 'concept-examples', concept: id});
    if (state.selected === id && box.isConnected) box.innerHTML = `<h4>公开文献里的代表论文</h4>${R.examplesHTML(out)}`;
  } catch (error) { if (box.isConnected) box.innerHTML = `<p class="map-note">${esc(error.message)}</p>`; }
}
function askIntro(id) {
  return guarded(async () => {
    notice(''); part('aiActivity').textContent = '';
    const out = await api({action: 'concept-intro', concept: id});
    if (!out.ok) {
      notice(`没有使用 AI：${out.reason || 'AI 没有给出简介'}。可以自己写。`);
      return;
    }
    state.pendingIntro = {id, text: out.intro}; state.selected = state.editing = id;
    notice(`AI 写了一段话，已放进编辑框，点“确定”再保存才会生效；今天这个项目还能让 AI 写 ${out.attempts_left} 次。`, false);
    renderDetail();
  });
}

async function mark(concept, value) {
  await guarded(async () => {
    state.route = await api({action: 'manual', concept, value, revision: state.route.revision});
    state.draft = JSON.parse(JSON.stringify(state.route.graph)); state.dirty = false; state.annotated = false;
    notice(''); render();
  });
}

async function watch(concept, value) {
  if (state.dirty || state.editing || state.busy) { renderDetail(); return; }
  await guarded(async () => {
    state.route = await api({action: 'watch', concept, value, revision: state.route.revision});
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
    <textarea class="edit" data-role="i" maxlength="140" rows="2" placeholder="简单说明这个概念是什么、门槛在哪（最多 140 字，可以不写）" aria-label="简介"></textarea>
    <p class="map-note" data-role="introNote"></p>
    ${R.needsEditorHTML(graph, concept.id)}
    <div class="row"><button type="button" class="small" data-act="ok">确定</button><button type="button" class="ghost small" data-act="no">取消</button></div>
    <section class="concept-papers" data-concept-papers></section>`;
  if (!state.dirty && state.route && state.route.graph && state.route.graph.concepts.some((c) => c.id === concept.id)) showMatched(concept.id);   // what the AI sentence is about stays in view while you edit it
  $('[data-role=n]', holder).value = concept.name;
  $('[data-role=t]', holder).value = (concept.terms || []).join(' / ');
  const proposed = state.pendingIntro && state.pendingIntro.id === concept.id ? state.pendingIntro.text : null;   // the model's sentence, not yet saved
  $('[data-role=i]', holder).value = proposed !== null ? proposed : (concept.intro || '');
  $('[data-role=introNote]', holder).textContent = proposed !== null ? 'AI 写的这句话还没有保存；可以改，点“确定”后标明“AI 写的”（改过就算你写的）。'
    : concept.intro ? (concept.intro_by === 'ai' ? '这句话是 AI 写的；改过之后就算你写的。' : '这句话是你写的。') : '';
  $('[data-act=no]', holder).onclick = () => { state.editing = null; state.pendingIntro = null; renderDetail(); };
  $('[data-act=ok]', holder).onclick = () => {
    try {
      let next = R.rename(graph, concept.id, $('[data-role=n]', holder).value, $('[data-role=t]', holder).value.split('/'));
      next = R.setNeeds(next, concept.id, R.readNeeds(holder));
      const text = $('[data-role=i]', holder).value;
      next = R.setIntro(next, concept.id, text, proposed !== null && text.trim() === proposed ? 'ai' : (concept.intro_by === 'ai' && text.trim() === concept.intro ? 'ai' : 'user'));
      state.editing = null; state.pendingIntro = null;
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
  state.route = {...(state.route || {}), progress: {}, total: 1, done: 0, exploration_share: 0.2, enabled: true};
  state.dirty = true; state.selected = 'c1'; state.editing = null; render();
};
part('discard').onclick = () => { if (!state.checking && !state.busy) load(); };
part('save').onclick = () => guarded(async () => {
  const verdict = R.check(state.draft);
  if (!verdict.ok) { notice(`学习图还不能保存：${verdict.reason}`); return; }
  state.route = await api({action: 'save', graph: state.draft, revision: state.route.revision ?? 0});
  state.draft = JSON.parse(JSON.stringify(state.route.graph)); state.dirty = false; state.annotated = false;
  notice('已保存。', false); render();
  loadGrowth();
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
  if (!part('aiBoundary').firstChild) part('aiBoundary').innerHTML = R.boundaryHTML('plan');   // built once, so a choice survives re-opening the box
  part('aiWarn').textContent = [state.dirty ? '你有没保存的修改，AI 草稿会替换掉它们。' : '',
    state.route && state.route.graph ? '保存草稿时，你在现在这张图上做的“已掌握 / 手动解锁”标记和你自己写的简介只会保留给名字相同的概念。' : ''].filter(Boolean).join(' ');
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
    const boundary = R.readBoundary(part('aiBoundary'));
    const out = await api({action: 'plan', goal, ...(boundary ? {boundary} : {})});
    if (!out.ok) {
      notice(out.reason_code === 'not_approved'
        ? '“为已有项目起草学习图”这项 AI 调用还在等你批准（harness/budget.json 里的 learning_path_plan_project）。批准之前，可以自己搭学习图。'
        : `没有使用 AI：${out.reason || 'AI 没有给出学习图'}。可以自己搭，或稍后再试。`);
      return;
    }
    state.route = {...(state.route || {}), progress: (state.route && state.route.progress) || {}, enabled: state.route ? state.route.enabled : true};
    if (!state.route.graph) Object.assign(state.route, {total: out.graph.concepts.length, done: 0, exploration_share: 0.2});
    state.draft = R.reuseIds(out.graph, state.route.graph); state.dirty = true; state.annotated = false; state.selected = state.editing = null;
    part('aiBox').hidden = true;
    const fixed = out.report ? ((out.report.dropped_edges || []).length + (out.report.merged || []).length) : 0;
    notice(`AI 已回复${out.tokens ? ` · 约 ${out.tokens} token` : ''}${fixed ? ` · 已自动修复 ${fixed} 处（重复概念、成环或多余的边）` : ''}。这是草稿，点“保存”才会生效；今天这个项目还能再生成 ${out.attempts_left} 次。`, false);
    render();
  } finally { part('aiGo').disabled = false; part('aiActivity').textContent = ''; }
});
/* ---- directions that are forming: from what the reader explicitly responded to; only a click adds one */
const growth = {result: null, undo: null, error: '', selected: null, judging: false};
function renderGrowth() {
  const box = part('growthList'), result = growth.result;
  if (!result) { box.innerHTML = growth.error ? `<p class="hint">${esc(growth.error)}</p>` : '<p class="hint">正在找潜在方向…</p>'; return; }
  const locked = state.dirty;   // a direction is saved straight to the stored map, so unsaved edits must be dealt with first
  box.innerHTML = R.pendingHTML(result, {busy: growth.judging})
    + R.judgementsHTML(result)
    + (result.candidates || []).map((c) => R.candidateRowHTML(c, growth.selected)).join('')
    + (R.growthNote(result) ? `<p class="hint">${esc(R.growthNote(result))}</p>` : '')
    + (growth.undo && growth.undo.revision === state.route.revision   // any other save or mark moves the revision on: then it is no longer the step to take back
      ? `<p class="hint">${esc(growth.undo.label)}。<button type="button" class="ghost small" data-growth="undo" data-event="${esc(growth.undo.id)}"${locked ? ' disabled title="先保存或放弃对学习图的修改"' : ''}>撤销</button></p>` : '');
}
async function loadGrowth() {
  try {
    growth.result = await api({action: 'candidates'}); growth.error = '';
  } catch (error) {
    growth.result = null; growth.error = `潜在方向没有读到：${error.message}`;
  }
  renderGrowth();
  if (state.draft) render();   // the ghost nodes join the drawing
}
part('findGrowth').onclick = () => guarded(async () => { notice(''); await loadGrowth(); });
function growthClick(event) {
  const button = event.target.closest('button[data-growth]');
  if (!button || button.disabled) return;
  const kind = button.dataset.growth, id = button.dataset.id;
  if (kind === 'select') {   // a row only previews: the map draws this one direction, nothing is added
    growth.selected = growth.selected === id ? null : id;
    state.selected = growth.selected ? `ghost:${id}` : null; state.editing = null; state.pendingIntro = null;
    render();
    return;
  }
  if (kind === 'judge') { judgeNow(); return; }
  guarded(async () => {
    notice('');
    const body = kind === 'undo' ? {action: 'undo', revision: state.route.revision, event: Number(button.dataset.event)}
      : {action: kind === 'accept' ? 'candidate-accept' : 'candidate-reject', candidate: id, revision: state.route.revision};
    const out = await api(body);
    const {undo, ...route} = out;
    growth.undo = kind === 'undo' || !undo ? null : {...undo, revision: route.revision};
    state.route = route; state.draft = route.graph ? JSON.parse(JSON.stringify(route.graph)) : null; state.dirty = false; state.annotated = false;
    state.selected = null; growth.selected = null;
    render();
    await loadGrowth();
  });
}
async function judgeNow() {
  if (growth.judging) return;
  growth.judging = true; renderGrowth(); notice('');
  try {
    const out = await api({action: 'direction-judge'});
    await loadGrowth();
    if (!out.ok) { notice(`未得到有效判断：${out.reason || 'AI 没有给出判断'} 今天还能判断 ${out.judges_left} 次。`); return; }
    notice(`AI 判断完了：${R.judgeSummary(out.results)}。今天还能判断 ${out.judges_left} 次。`, false);
    const made = (out.results || []).find((r) => r.direction && (r.verdict === 'new' || r.verdict === 'join'));
    if (made) { growth.selected = made.direction; state.selected = `ghost:${made.direction}`; render(); }
  } catch (error) { await refreshRoute(); await loadGrowth(); notice(error.message); }
  finally { growth.judging = false; renderGrowth(); }
}
part('growthList').onclick = growthClick;
part('detail').addEventListener('click', growthClick);   // the same buttons in a direction's own panel
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
