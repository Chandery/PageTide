/* Learning-map editor helpers for the creation page. Pure functions on the same graph shape the server validates
   (app/pathgraph.py); the server is the authority, these only keep the page honest before it sends anything. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTRoute = api;
})(typeof window !== 'undefined' ? window : this, function () {
  const MAX_NODES = 40;
  const INTRO_LIMIT = 140;   // the same bound as pathgraph.INTRO_LIMIT
  const MAX_FAN_IN = 3;
  const LABELS = {
    supported: '文献支持这个先后顺序',
    contradicted: '文献显示的先后顺序可能反了',
    neutral: '文献里看不出明显的先后',
    unknown: '文献不够，无法判断',
  };

  const STATUS = { satisfied: '已满足', unlocked: '可以读', locked: '未解锁', proposed: '建议中', archived: '已归档' };
  const LOW_INTEREST_TITLE = '暂时排在后面';
  const LOCKED_TITLE = '在等前置概念';

  const clean = (text, limit) => String(text || '').replace(/[,|:!"\\\r\n\t]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, limit);
  const copy = (g) => JSON.parse(JSON.stringify(g));
  const nameKey = (text) => String(text || '').toLowerCase().replace(/[\s\-_]+/g, ' ').trim();
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const hasLetter = (text) => /[\p{L}\p{N}]/u.test(text);
  const unique = (list) => [...new Set(list || [])];
  const needsMap = (g) => {
    const out = {};
    g.concepts.forEach(c => { out[c.id] = []; });
    g.prereqs.forEach(e => { if (out[e.to] && out[e.from]) out[e.to].push(e.from); });
    return out;
  };

  function layers(g) {
    const needs = needsMap(g), memo = {};
    const depth = (id, trail) => {
      if (memo[id]) return memo[id];
      if (trail.includes(id)) return 1;
      memo[id] = 1 + Math.max(0, ...needs[id].map(p => depth(p, trail.concat(id))));
      return memo[id];
    };
    g.concepts.forEach(c => depth(c.id, []));
    return memo;
  }

  function label(value) {
    if (value === null || value === undefined) return 'unknown';
    if (value >= 0.15) return 'supported';
    if (value <= -0.15) return 'contradicted';
    return 'neutral';
  }

  function needsOf(g, id) {
    const byId = Object.fromEntries(g.concepts.map(c => [c.id, c]));
    return g.prereqs.filter(e => e.to === id && byId[e.from] && (e.state || 'active') === 'active').map(e => ({ id: e.from, name: byId[e.from].name, support: e.support, label: label(e.support) }));
  }

  function acyclic(g) {
    const needs = needsMap(g), state = {};
    const visit = (id) => {
      state[id] = 1;
      for (const p of needs[id]) { if (state[p] === 1 || (state[p] === undefined && !visit(p))) return false; }
      state[id] = 2;
      return true;
    };
    return g.concepts.every(c => state[c.id] === 2 || visit(c.id));
  }

  function check(g, {targets = true} = {}) {
    if (!g || !Array.isArray(g.concepts) || !g.concepts.some(c => (c.state || 'active') === 'active')) return { ok: false, reason: '至少需要一个概念' };
    if (g.concepts.length > MAX_NODES) return { ok: false, reason: '图太大了' };
    const hint = Object.fromEntries(g.concepts.map(c => [c.id, c.hint]));
    const known = new Set(g.concepts.map(c => c.id));
    if (!Array.isArray(g.prereqs) || g.prereqs.some(e => !known.has(e.from) || !known.has(e.to))) return {ok: false, reason: '前置概念不存在'};
    if (targets && (!(g.targets || []).length || g.targets.some(id => !g.concepts.some(c => c.id === id && (c.state || 'active') === 'active')))) return {ok: false, reason: '请明确选择活动学习目标'};
    const fan = {};
    g.prereqs.forEach(e => { fan[e.to] = (fan[e.to] || 0) + 1; });
    if (Object.values(fan).some(n => n > MAX_FAN_IN)) return { ok: false, reason: `一个概念最多 ${MAX_FAN_IN} 个前置` };
    if (!acyclic(g)) return { ok: false, reason: '前置关系不能成环' };
    return { ok: true, reason: '', warnings: g.prereqs.some(e => hint[e.from] > hint[e.to]) ? ['前置难度提示高于后续概念'] : [] };
  }

  let identitySequence = 0;
  function nextId(g) {
    // Deleting and adding is a new identity, even after the draft is reloaded.
    const used = new Set(g.concepts.map(c => c.id));
    let id;
    do {
      const nonce = typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID().replace(/-/g, '')
        : `${Date.now().toString(16)}${(++identitySequence).toString(16)}${Math.random().toString(16).slice(2)}`;
      id = `r-${nonce}`;
    } while (used.has(id));
    return id;
  }

  function terms(list) {
    const out = [];
    (list || []).forEach(t => { const x = clean(t, 60); if (x && !out.some(o => o.toLowerCase() === x.toLowerCase())) out.push(x); });
    return out.slice(0, 2);
  }

  function addConcept(g, item, needs) {
    if (g.concepts.length >= MAX_NODES) throw new Error('图太大了');
    const name = clean(item.name, 60);
    if (!name || !hasLetter(name)) throw new Error('概念需要名称');
    if (g.concepts.some(c => nameKey(c.name) === nameKey(name))) throw new Error('已经有同名的概念');
    const next = copy(g), id = nextId(g), hint = Math.max(1, Math.min(4, Number(item.hint) || 2));
    const known = Object.fromEntries(g.concepts.map(c => [c.id, c]));
    needs = unique(needs);
    needs.forEach(n => {
      if (!known[n]) throw new Error('前置概念不存在');
    });
    const intro = String(item.intro || '').replace(/\s+/g, ' ').trim().slice(0, INTRO_LIMIT);
    next.concepts.push({ id, name, terms: terms(item.terms), hint, origin: 'user', state: 'active', side: false, ...(intro ? { intro, intro_by: item.intro_by === 'ai' ? 'ai' : 'user' } : {}) });
    needs.forEach(n => next.prereqs.push({ from: n, to: id, support: null, origin: 'user', state: 'active' }));
    const verdict = check(next, {targets: false});
    if (!verdict.ok) throw new Error(verdict.reason);
    return next;
  }

  function removeConcept(g, id) {
    const next = copy(g);
    next.concepts = next.concepts.filter(c => c.id !== id);
    next.prereqs = next.prereqs.filter(e => e.from !== id && e.to !== id);
    next.targets = (next.targets || []).filter(t => t !== id);
    return next;
  }

  function setNeeds(g, id, needs) {
    const next = copy(g);
    next.prereqs = next.prereqs.filter(e => e.to !== id);
    unique(needs).forEach(n => next.prereqs.push({ from: n, to: id, support: null, origin: 'user', state: 'active' }));
    const verdict = check(next, {targets: false});
    if (!verdict.ok) throw new Error(verdict.reason);
    return next;
  }

  function setTarget(g, id, value) {
    if (!g.concepts.some(c => c.id === id && (c.state || 'active') === 'active')) throw new Error('目标概念必须活动');
    const next = copy(g), existing = new Set(next.targets || []);
    value ? existing.add(id) : existing.delete(id);
    next.targets = [...existing];
    return next;
  }

  function rename(g, id, name, termList) {
    const cleaned = clean(name, 60);
    if (!cleaned || !hasLetter(cleaned)) throw new Error('概念需要名称');
    if (g.concepts.some(c => c.id !== id && nameKey(c.name) === nameKey(cleaned))) throw new Error('已经有同名的概念');
    const next = copy(g), target = next.concepts.find(c => c.id === id);
    if (!target) throw new Error('概念不存在');
    target.name = cleaned;
    target.terms = terms(termList);
    return next;
  }

  /* A map from the AI numbers its concepts c1..cN again. Marks on the saved map (already known, unlocked by hand,
     start) are kept only for the same id and the same name, so a draft that is going to replace the saved map
     reuses the saved id of every concept whose name is the same; the others get ids no saved concept has. */
  function reuseIds(draft, saved) {
    const next = copy(draft);
    if (!saved || !Array.isArray(saved.concepts) || !saved.concepts.length) return next;
    const savedByName = new Map(), savedConcept = new Map();
    saved.concepts.forEach(c => { if (!savedByName.has(nameKey(c.name))) { savedByName.set(nameKey(c.name), c.id); savedConcept.set(c.id, c); } });
    const number = (id) => { const m = /^c(\d+)$/.exec(id); return m ? Number(m[1]) : 0; };
    let top = Math.max(0, ...saved.concepts.map(c => number(c.id)), ...next.concepts.map(c => number(c.id)));
    const taken = new Set(), rename = new Map();
    next.concepts.forEach(c => {
      const wanted = savedByName.get(nameKey(c.name));
      if (wanted && !taken.has(wanted)) {
        rename.set(c.id, wanted); taken.add(wanted);
        // A sentence the person wrote about a concept is theirs: a model draft of the same-named concept never replaces it.
        const old = savedConcept.get(wanted);
        if (old && old.intro && old.intro_by !== 'ai') { c.intro = old.intro; c.intro_by = old.intro_by || 'user'; }
      }
    });
    next.concepts.forEach(c => { if (!rename.has(c.id)) rename.set(c.id, `c${++top}`); });
    next.concepts.forEach(c => { c.id = rename.get(c.id); });
    next.prereqs.forEach(e => { e.from = rename.get(e.from); e.to = rename.get(e.to); });
    next.targets = (next.targets || []).map(t => rename.get(t)).filter(Boolean);
    return next;
  }

  function toggleMastered(list, id, g) {
    const set = new Set(list || []);
    if (!g.concepts.some(c => c.id === id)) return [...set];
    if (set.has(id)) set.delete(id); else set.add(id);
    return [...set];
  }

  function payload(g, mastered) {
    if (!g || !Array.isArray(g.concepts) || !g.concepts.length) return null;
    const ids = new Set(g.concepts.map(c => c.id));
    return { graph: g, mastered: (mastered || []).filter(i => ids.has(i)) };
  }

  /* Prerequisites are chosen from a list keyed by id, so a name may contain any character (a slash, a comma). */
  function needsEditorHTML(g, id) {
    const chosen = new Set(g.prereqs.filter(e => e.to === id).map(e => e.from));
    const rows = g.concepts.filter(c => c.id !== id).map(c =>
      `<label class="need-option"><input type="checkbox" value="${esc(c.id)}"${chosen.has(c.id) ? ' checked' : ''}> <span data-no-i18n>${esc(c.name)}</span></label>`);
    return `<fieldset class="need-list"><legend>前置概念</legend>${rows.join('') || '<span class="hint">还没有别的概念</span>'}</fieldset>`;
  }

  function readNeeds(container) {
    return [...container.querySelectorAll('.need-list input[type=checkbox]:checked')].map(box => box.value);
  }

  /* How branched the map is: concepts, entry points (nothing needed first), levels, the widest level and whether it
     is a single line. Same meaning as pathgraph.shape on the server. */
  function shape(g) {
    const live = (g.concepts || []).filter(c => (c.state || 'active') === 'active');
    const ids = new Set(live.map(c => c.id));
    const edges = (g.prereqs || []).filter(e => ids.has(e.from) && ids.has(e.to));
    const level = layers({ concepts: live, prereqs: edges });
    const needed = new Set(edges.map(e => e.to)), per = {};
    Object.values(level).forEach(v => { per[v] = (per[v] || 0) + 1; });
    const width = Math.max(0, ...Object.values(per));
    return { concepts: live.length, roots: live.filter(c => !needed.has(c.id)).length, levels: Object.keys(per).length, width, chain: live.length >= 4 && width === 1 };
  }

  function shapeText() {
    return '';
  }

  /* The prerequisites of a concept that are not understood yet, and the concepts that need it. */
  function waitingOn(g, progress, id) {
    return needsOf(g, id).filter(n => !progress || !progress[n.id] || progress[n.id].status !== 'satisfied');
  }

  function dependents(g, id) {
    const byId = Object.fromEntries(g.concepts.map(c => [c.id, c]));
    return g.prereqs.filter(e => e.from === id && byId[e.to] && (e.state || 'active') === 'active').map(e => ({ id: e.to, name: byId[e.to].name }));
  }

  /* What a node says about itself on the graph: {key, label, title}. `known` is false for a draft with unsaved
     structural edits (progress belongs to the saved map). */
  function nodeStatus(concept, progress, known) {
    const p = known && progress ? progress[concept.id] : null;
    if (!p) return { key: 'proposed', label: known ? '' : '未保存', title: concept.name };
    const title = p.status === 'locked' ? LOCKED_TITLE : (p.low_interest ? LOW_INTEREST_TITLE : concept.name);
    return { key: p.status, label: STATUS[p.status] || '', title };
  }

  /* What a concept IS, in plain words: its role on the map, how hard it is, one sentence about it (and who wrote it),
     the project's own papers that use its search terms, a few public papers. Everything from data goes through esc(). */
  const ROLE_TEXT = { entry: '入口', middle: '中间概念', target: '目标', side: '旁支' };
  const ROLE_LABEL = { entry: '入口', middle: '中间概念', target: '目标', side: '旁支' };
  const HINT_TEXT = { 1: '入门', 2: '基础', 3: '进阶', 4: '前沿' };

  function roleOf(g, concept) {
    if ((g.targets || []).includes(concept.id)) return 'target';
    if (concept.side) return 'side';
    const needed = (g.prereqs || []).some((e) => e.to === concept.id && (e.state || 'active') === 'active');
    return needed ? 'middle' : 'entry';
  }

  function introHTML(concept, canEdit) {
    if (!concept.intro) return '';
    return `<p class="concept-intro" data-no-i18n>${esc(concept.intro)}</p>${concept.intro_by === 'ai' ? '<div class="badges"><span class="badge">AI 写的</span></div>' : ''}`;
  }

  function introInputHTML(out) {
    const body = out && out.context_excerpt;
    if (!body) return '';
    const papers = (Array.isArray(body.papers) ? body.papers : []).slice(0, 3).map((p) =>
      `<li data-no-i18n><b>${esc(p.title || '')}</b><p>${esc(p.abstract || '')}</p></li>`).join('');
    return `<details><summary>发送给 AI 的内容</summary><p><b>概念</b><span data-no-i18n>：${esc(body.concept || '')} · ${esc((body.terms || []).join(' · '))}</span></p>`
      + `<p><b>项目</b><span data-no-i18n>：${esc(body.goal || '')}</span></p><ul>${papers}</ul></details>`;
  }

  const FEEDBACK_TEXT = { useful: '你点过有用', irrelevant: '你点过不相关' };
  const FAMILIAR_TEXT = { understood: '你点过已读懂', too_hard: '你点过太难' };
  function matchedPapersHTML(result) {
    const papers = (result && result.papers) || [], total = Number(result && result.total) || 0;
    if (!papers.length) return '<h4>项目里的论文</h4><p class="map-note">还没有相关论文</p>';
    const rows = papers.map((p) => `<li><span data-no-i18n>${esc(p.title)}</span> <small data-no-i18n>${esc((p.terms || []).join(' · '))}</small>`
      + [FEEDBACK_TEXT[p.feedback], FAMILIAR_TEXT[p.familiarity]].filter(Boolean).map((t) => ` <em class="mark">${t}</em>`).join('') + '</li>').join('');
    return `<h4>项目里的论文</h4><ul class="concept-list">${rows}</ul>${total > papers.length ? `<p class="map-note">另有 ${total - papers.length} 篇</p>` : ''}`;
  }

  function examplesHTML(result) {
    const list = (result && result.examples) || [];
    if (result && result.ok === false) return `<p class="map-note">${result.reason_code === 'unavailable' || result.reason_code === 'network_error' ? '暂时连不上公开文献库' : '没能读到公开文献'}</p>`;
    if (!list.length) return `<p class="map-note">${result && result.reason_code === 'no_terms' ? '还没有检索词' : '公开文献里没有找到'}</p>`;
    return '<ul class="concept-list">' + list.map((e) => `<li><span data-no-i18n>${esc(e.title)}</span> <small data-no-i18n>${esc([e.year, e.source].filter(Boolean).join(' · '))}</small>`
      + (e.snippet ? `<div class="map-note" data-no-i18n>${esc(e.snippet)}</div>` : '') + '</li>').join('') + '</ul>';
  }

  /* A copy of the map with the concept's intro set. A sentence left as it was keeps its author; a changed one is the
     person's (or the model's when they put the model's sentence in); an empty one removes the intro and its author. */
  function setIntro(g, id, text, by) {
    const next = copy(g), target = next.concepts.find((c) => c.id === id);
    if (!target) throw new Error('概念不存在');
    const value = String(text || '').replace(/\s+/g, ' ').trim().slice(0, INTRO_LIMIT);
    if (!value) { delete target.intro; delete target.intro_by; return next; }
    if (target.intro !== value) target.intro_by = by === 'ai' ? 'ai' : 'user';
    target.intro = value;
    return next;
  }

  /* The information half of the detail panel (the pages add their own buttons). `ctx.progress` is the saved map's
     progress or null; `ctx.mastered` is the creation page's "I already know this" mark. */
  function detailHTML(g, concept, ctx) {
    const c = ctx || {}, p = c.progress ? c.progress[concept.id] : null;
    const needs = needsOf(g, concept.id), waiting = new Set(waitingOn(g, c.progress, concept.id).map(n => n.id));
    const unlocks = dependents(g, concept.id);
    const chip = (n) => `<span class="need ${n.label}${c.progress ? (waiting.has(n.id) ? ' wait' : ' done') : ''}" title="${esc((typeof window!=='undefined' && window.PTi18n?.t(LABELS[n.label])) || LABELS[n.label])}" data-no-i18n>${esc(n.name)}</span>`;
    const lines = [];
    lines.push(`<h3 data-no-i18n>${esc(concept.name)}</h3>`);
    lines.push((concept.terms || []).length ? `<div class="terms" data-no-i18n>${esc(concept.terms.join(' · '))}</div>` : '');
    lines.push(introHTML(concept, Boolean(ctx && ctx.canEdit)));
    if (concept.why) lines.push(`<div class="terms" data-no-i18n>${esc(concept.why)}</div>`);
    if (p) {
      lines.push(`<div class="badges"><span class="badge st-${esc(p.status)}" title="${esc(p.status === 'locked' ? LOCKED_TITLE : '')}">${esc(STATUS[p.status] || '')}</span>`
        + `${p.low_interest ? `<span class="badge" title="${esc(LOW_INTEREST_TITLE)}">暂不优先</span>` : ''}`
        + `${p.manual === 'mastered' ? '<span class="badge">你标为已掌握</span>' : ''}</div>`);
    } else if (c.mastered) {
      lines.push('<div class="badges"><span class="badge st-satisfied">你标为已掌握（起点）</span></div>');
    }
    lines.push(needs.length
      ? `<div class="needs">先读懂：${needs.map(chip).join('、')}</div>`
      : '');
    if (unlocks.length) lines.push(`<div class="needs">之后可读：${unlocks.map(n => `<span class="need" data-no-i18n>${esc(n.name)}</span>`).join('、')}</div>`);
    if (concept.papers !== undefined) lines.push(`<div class="counts ${concept.grounding === 'ok' ? '' : 'none'}">公开文献约 ${esc(concept.papers)} 篇</div>`);
    lines.push('<section class="concept-papers" data-concept-papers></section><section class="concept-examples" data-concept-examples></section>');
    return lines.join('');
  }

  /* What the reader may say about where they start and how deep they want to go. Both can be skipped; the server
     accepts exactly these values (app/routeplan.py) and the page sends nothing else about the reader. */
  const BACKGROUNDS = [['', '不说明'], ['unknown', '未知'], ['engineering', '计算机 / 工程'], ['ai_researcher', 'AI 研究者'], ['other', '其他']];
  const DEPTHS = [['', '不说明'], ['overview', '快速了解'], ['read_papers', '能读论文'], ['implement', '研究 / 实现']];
  const TYPES = { topic: '主题', method: '方法', problem: '问题', foundation: '基础' };

  function boundaryHTML(prefix) {
    const select = (name, label, list) => `<label class="boundary-field" for="${esc(prefix)}-${name}"><span>${label}</span><select id="${esc(prefix)}-${name}">`
      + list.map(([value, text]) => `<option value="${esc(value)}">${text}</option>`).join('') + '</select></label>';
    return `<div class="boundary">${select('background', '你的背景', BACKGROUNDS)}${select('depth', '想学到', DEPTHS)}</div>`;
  }

  /* The boundary to send: only the chosen values, nothing when both are skipped or a value is not on the list. */
  function readBoundary(container) {
    const pick = (name, list) => {
      const node = container.querySelector(`[id$="-${name}"]`);
      return node && list.some(([value]) => value === node.value) ? node.value : '';
    };
    const out = {}, background = pick('background', BACKGROUNDS), depth = pick('depth', DEPTHS);
    if (background) out.background = background;
    if (depth) out.depth = depth;
    return Object.keys(out).length ? out : undefined;
  }

  /* "foundation · why ..." for a concept that has a type (the page puts the labels around it), or ''. */
  function typeText(concept) {
    if (!concept || !TYPES[concept.type]) return '';
    return TYPES[concept.type] + (concept.why ? ' · ' + concept.why : '');
  }

  /* ---- potential directions: what the model judged from the exploration papers you collected, with the evidence the
     app counts under each. A row is only a row: the map shows a direction (ghost node, progress outline, arrows) when
     you click it. Everything is data from the server and goes through esc(); the buttons carry the id only. */
  const pct = (v) => Math.round(Math.max(0, Math.min(1, Number(v) || 0)) * 100);
  const level = (v) => (pct(v) >= 67 ? '高' : pct(v) >= 34 ? '中' : '低');   // a score is shown as a word, never as a number
  const GATE_LABEL = { papers: '属于这个方向的论文', positive: '你明确点过的论文', sources: '不同来源', strength: '证据强度' };
  const ready = (c) => c.status === 'ready';
  const accepts = (c) => !c.stale && (typeof c.can_accept === 'boolean' ? c.can_accept : ready(c));
  const kindText = {new_task: '新任务', missing_prerequisite: '前置缺口', new_branch: '新分支', legacy: '旧规则提议'};
  const gateText = (g) => `${Number(g.have) || 0}/${Number(g.need) || 0}`;

  function evidenceHTML(value) {
    const types = {basic: '基础实验', observational: '观察性临床研究', trial: '临床试验', review: '综述', unknown: '研究类型未确认'};
    const evidence = Array.isArray(value.source_evidence) ? value.source_evidence : [];
    const quotes = evidence.slice(0, 12);
    const details = quotes.length ? `<details><summary>判断依据</summary><ul>` + quotes.map((q) =>
      `<li><b>${types[q.type] || types.unknown}</b><span data-no-i18n> · ${esc(q.title || q.paper || '')} · “${esc(q.quote || '')}”</span></li>`).join('')
      + '</ul></details>' : '';
    return (value.optional_relation ? '<p>缺少前置依据，作为可选任务</p>' : '') + details;
  }

  function candidateRowHTML(c, selectedId) {
    const g = c.gates || {};
    const chosen = c.id === selectedId;
    return `<button type="button" class="growth-row${ready(c) ? ' is-ready' : ''}${chosen ? ' is-selected' : ''}" data-growth="select" data-id="${esc(c.id)}" aria-pressed="${chosen}">`
      + `<span class="growth-row-top"><b data-no-i18n>${esc(c.name)}</b><span class="growth-pill">${c.stale ? '已过期' : (accepts(c) ? '可加入' : '证据较少')}</span></span>`
      + `<span class="growth-meter" role="img" aria-label="证据进度"><i style="width:${pct(c.progress)}%"></i></span>`
      + `</button>`;
  }

  /* The side panel for one direction: the model's introduction and barrier (marked as the model's), each gate with how
     far it is, the papers behind it (the ones you marked first), where it would sit, and what the strength is made of. */
  function ghostDetailHTML(c, options) {
    const locked = options && options.locked ? ' disabled title="先保存或放弃修改"' : '';
    const g = c.gates || {};
    const missing = (c.missing || []).length ? `<ul class="growth-missing">${c.missing.map((m) => `<li>${esc(m)}</li>`).join('')}</ul>` : '';
    const papers = (c.papers || []).map((p) => `<li><span data-no-i18n>${esc(p.title)}</span>${p.explicit ? ' <em class="mark">你点过</em>' : ''}${p.source ? ` <small data-no-i18n>${esc(p.source)}</small>` : ''}</li>`).join('');
    const terms = (c.terms || []).length ? `<div class="terms" data-no-i18n>${esc(c.terms.join(' · '))}</div>` : '';
    const brief = (c.intro || c.barrier)
      ? `<p class="concept-intro" data-no-i18n>${esc(c.intro || '')}</p>${c.barrier ? `<p class="concept-intro"><b>门槛：</b><span data-no-i18n>${esc(c.barrier)}</span></p>` : ''}`
        + '<div class="badges"><span class="badge">AI 判断</span></div>' : '';
    const accept = accepts(c) ? '' : ' disabled title="暂不能加入"';
    return `<h3 data-no-i18n>${esc(c.name)}</h3><p>${kindText[c.proposal_type] || '新分支'}</p>${terms}<div class="badges"><span class="badge">${c.stale ? '已过期' : (accepts(c) ? '可以加入' : '证据较少')}</span></div>${brief}`
      + `<div class="growth-meter" role="img" aria-label="证据进度"><i style="width:${pct(c.progress)}%"></i></div>`
      + `${missing}${evidenceHTML(c)}`
      + `<h4>相关论文</h4><ul class="growth-papers">${papers}</ul>`
      + `<div class="row"><button type="button" class="primary small" data-growth="accept" data-id="${esc(c.id)}"${locked || accept}>加入学习图</button>`
      + `<button type="button" class="ghost small" data-growth="reject" data-id="${esc(c.id)}"${locked}>不再提示</button></div>`;
  }

  /* The exploration papers you collected that nobody has judged yet, with the one button that asks the model. */
  function pendingHTML(result, options) {
    const list = (result && result.pending) || [];
    if (!list.length) return '';
    const left = Number(result.judges_left) || 0;
    const off = left <= 0 ? ' disabled title="今天的次数用完了"' : (options && options.busy ? ' disabled' : '');
    return `<div class="growth-pending"><p>待判断的论文：<b>${list.length}</b></p>`
      + `<ul class="growth-papers">${list.slice(0, 3).map((p) => `<li data-no-i18n>${esc(p.title)}</li>`).join('')}</ul>`
      + `<div class="row"><button type="button" class="small" data-growth="judge"${off} title="调用 AI，只发送论文标题、摘要节选和学习图概念">${options && options.busy ? '正在判断…' : '判断全部'}</button></div></div>`;
  }

  /* A completed snapshot may have new pending papers. Saved partial results still need a continuation. */
  function judgeProgress(out) {
    if (!out || typeof out.complete !== 'boolean'
      || ![out.requested, out.processed, out.pending].every((n) => Number.isInteger(n) && n >= 0)
      || out.processed > out.requested) return null;   // older responses use the original result summary
    const lines = [out.complete ? '判断完毕' : '判断已停止', `${out.processed}/${out.requested} 篇`];
    if (out.pending > 0) lines.push(`还有 ${out.pending} 篇待判断`);
    const warning = !out.complete || Boolean(out.reason_code || out.reason || out.usage_unknown);
    if (out.reason) lines.push(out.reason);
    else if (warning && out.complete) lines.push('调用状态需确认');
    return {complete: out.complete, warning, message: lines.join(' · ')};
  }

  /* One line per judged group, in plain words, for the page to show after the model answered. */
  function judgeSummary(results) {
    const says = (results || []).map((r) => {
      const name = r.name ? `「${r.name}」` : '';
      if (r.verdict === 'new') return `${name}${kindText[r.proposal_type] || '新分支'}`;
      if (r.verdict === 'join') return `并入${name}`;
      if (r.verdict === 'covered') return `${r.nearest ? `「${r.nearest}」` : '已有概念'}已覆盖`;
      if (r.verdict === 'declined') return `${name || '这个方向'}已不再提示`;
      if (r.verdict === 'full') return '潜在方向已满';
      if (r.verdict === 'unusable') return 'AI 回复不完整，可再试';
      return 'AI 看不出来';
    });
    return says.join('；');
  }

  /* A copy of the map for drawing only: each direction is a ghost node, with dashed arrows from what it would need.
     The real graph is never touched and a ghost never reuses a real id, so nothing here can be saved by accident. */
  function ghostGraph(graph, candidates) {
    const known = new Set((graph.concepts || []).map((c) => c.id));
    const concepts = [...(graph.concepts || [])], prereqs = [...(graph.prereqs || [])];
    (candidates || []).forEach((c) => {
      const id = `ghost:${c.id}`;
      concepts.push({ id, name: c.name, terms: c.terms || [], hint: 2, state: 'active', side: false, ghost: true, candidate: c });
      ((c.topology && c.topology.required_by) || []).forEach((dependent) => {
        if (known.has(dependent.id)) prereqs.push({from: id, to: dependent.id, state: 'active', ghost: true});
      });
      ((c.topology && c.topology.needs) || []).forEach((need) => {
        if (known.has(need.id)) prereqs.push({ from: need.id, to: id, state: 'active', ghost: true });
      });
    });
    return { ...graph, concepts, prereqs };
  }

  /* The outline of a ghost node: a dashed track, and over it the share of evidence collected, drawn along the same
     outline (pathLength 100, so the share is the dash length). Not ready never shows as full; ready is one solid line. */
  function ringSVG(progress, isReady, w, h) {
    const share = isReady ? 100 : Math.min(97, Math.round(Math.max(0, Math.min(1, Number(progress) || 0)) * 100));
    const inset = 1.5, rx = 9, ww = Math.max(1, (Number(w) || 0) - 2 * inset), hh = Math.max(1, (Number(h) || 0) - 2 * inset);
    const rect = (cls, dash) => `<rect class="${cls}" x="${inset}" y="${inset}" width="${ww}" height="${hh}" rx="${rx}" pathLength="100"${dash ? ` stroke-dasharray="${dash}"` : ''}/>`;
    return `<svg class="rg-ring${isReady ? ' is-ready' : ''}" viewBox="0 0 ${Number(w) || 0} ${Number(h) || 0}" aria-hidden="true">${rect('rg-ring-track', '2 1.4')}${share > 0 ? rect('rg-ring-fill', isReady ? '' : `${share} ${100 - share}`) : ''}</svg>`;
  }

  function ghostStatus(c) {
    if (c.stale) return {key: 'ghost', label: '潜在方向 · 已过期', title: '已过期'};
    return { key: 'ghost', label: accepts(c) ? '潜在方向 · 可以加入' : `潜在方向 · 证据${level(c.progress)}`,
      title: accepts(c) ? '可以加入' : ((c.missing || []).join('；') || '证据还不够') };
  }

  /* What to say when no direction is on file yet: the truth, never a reason to feel behind. */
  function growthNote(result) {
    if ((result.candidates || []).length) return '';
    return (result.pending || []).length ? '' : '还没有潜在方向';
  }

  function judgementsHTML() {
    return '';
  }

  function countsText(state) {
    const n = (v) => Number(v) || 0;
    return `收藏 ${n(state.useful)} · 已读懂 ${n(state.understood)} · 不感兴趣 ${n(state.irrelevant)} · 太难 ${n(state.too_hard)} · 已展示 ${n(state.shown)}`;
  }

  /* Marks a person may set on a concept. Each has a way back (clear), none is inferred from silence. */
  function actionsFor(state) {
    if (state.status === 'proposed' || state.status === 'archived') return [];
    const out = [];
    if (state.status === 'locked') out.push({ value: 'unlocked', clear: state.manual === 'unlocked', label: '手动解锁' });
    out.push({ value: 'mastered', clear: state.manual === 'mastered', label: state.manual === 'mastered' ? '取消已掌握' : '标记已掌握' });
    out.push({ value: 'demoted', clear: state.manual === 'demoted', label: state.manual === 'demoted' ? '恢复优先' : '暂不优先' });
    return out;
  }

  function summaryText(route) {
    if (route.goal_status) {
      const label = route.goal_status === 'completed' ? '已完成' : route.goal_status === 'needs_review' ? '需检查' : '学习中';
      return `${label} · ${Number(route.goal_done) || 0}/${Number(route.goal_total) || 0}`;
    }
    const total = Number(route.total) || 0, done = Number(route.done) || 0;
    return `已读懂 ${done}/${total}`;
  }

  function watchHTML(watching, satisfied) {
    return `<label class="map-note"><input type="checkbox" data-route-watch ${watching ? 'checked' : ''}> 持续关注</label>`;
  }

  return { setTarget, watchHTML, MAX_NODES, needsEditorHTML, readNeeds, STATUS, LOW_INTEREST_TITLE, LOCKED_TITLE, countsText, ROLE_TEXT, ROLE_LABEL, HINT_TEXT, roleOf, introHTML, introInputHTML, matchedPapersHTML, examplesHTML, setIntro, candidateRowHTML, pendingHTML, judgementsHTML, judgeSummary, judgeProgress, ghostDetailHTML, ghostGraph, ringSVG, ghostStatus, growthNote, BACKGROUNDS, DEPTHS, TYPES, boundaryHTML, readBoundary, typeText, actionsFor, summaryText, LABELS, layers, shape, shapeText, waitingOn, dependents, nodeStatus, detailHTML, needsOf, check, addConcept, removeConcept, setNeeds, rename, reuseIds, toggleMastered, payload, label };
});
