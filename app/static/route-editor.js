/* Learning-map editor helpers for the creation page. Pure functions on the same graph shape the server validates
   (app/pathgraph.py); the server is the authority, these only keep the page honest before it sends anything. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PDHRoute = api;
})(typeof window !== 'undefined' ? window : this, function () {
  const MAX_NODES = 40;
  const MAX_FAN_IN = 3;
  const LABELS = {
    supported: '语料支持这个先后顺序',
    contradicted: '语料提示顺序可能反了',
    neutral: '语料没有明显倾向',
    unknown: '语料不足，没有判断',
  };

  const STATUS = { satisfied: '已满足', unlocked: '可以读', locked: '未解锁', proposed: '建议中', archived: '已归档' };
  const LOW_INTEREST_TITLE = '这个概念暂时排在后面：来自你的“暂不优先”设置，或你对它的评价里不感兴趣明显多于收藏。这只表示优先顺序，不等于不喜欢；取消“暂不优先”或改变相关评价后会自动恢复。';
  const LOCKED_TITLE = '还在等前置概念被读懂；读懂后会自动解锁，也可以手动解锁。';

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

  function check(g) {
    if (!g || !Array.isArray(g.concepts) || !g.concepts.some(c => (c.state || 'active') === 'active')) return { ok: false, reason: '至少需要一个概念' };
    if (g.concepts.length > MAX_NODES) return { ok: false, reason: '图太大了' };
    const hint = Object.fromEntries(g.concepts.map(c => [c.id, c.hint]));
    if (g.prereqs.some(e => hint[e.from] > hint[e.to])) return { ok: false, reason: '前置概念必须比依赖它的概念更基础' };
    const fan = {};
    g.prereqs.forEach(e => { fan[e.to] = (fan[e.to] || 0) + 1; });
    if (Object.values(fan).some(n => n > MAX_FAN_IN)) return { ok: false, reason: `一个概念最多 ${MAX_FAN_IN} 个前置` };
    if (!acyclic(g)) return { ok: false, reason: '前置关系不能成环' };
    return { ok: true, reason: '' };
  }

  function nextId(g) {
    const numbers = g.concepts.map(c => /^c(\d+)$/.exec(c.id)).filter(Boolean).map(m => Number(m[1]));
    return `c${Math.max(0, ...numbers) + 1}`;
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
      if (known[n].hint > hint) throw new Error('前置概念必须比依赖它的概念更基础');
    });
    next.concepts.push({ id, name, terms: terms(item.terms), hint, origin: 'user', state: 'active', side: false });
    needs.forEach(n => next.prereqs.push({ from: n, to: id, support: null, origin: 'user', state: 'active' }));
    const verdict = check(next);
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
    const verdict = check(next);
    if (!verdict.ok) throw new Error(verdict.reason);
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
    const savedByName = new Map();
    saved.concepts.forEach(c => { if (!savedByName.has(nameKey(c.name))) savedByName.set(nameKey(c.name), c.id); });
    const number = (id) => { const m = /^c(\d+)$/.exec(id); return m ? Number(m[1]) : 0; };
    let top = Math.max(0, ...saved.concepts.map(c => number(c.id)), ...next.concepts.map(c => number(c.id)));
    const taken = new Set(), rename = new Map();
    next.concepts.forEach(c => {
      const wanted = savedByName.get(nameKey(c.name));
      if (wanted && !taken.has(wanted)) { rename.set(c.id, wanted); taken.add(wanted); }
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

  function shapeText(s) {
    if (!s || !s.concepts) return '';
    if (s.chain) return `这张图现在是一条单线：${s.concepts} 个概念，每个只依赖上一个，没有并行的分支。真实的领域通常有几个互相独立的基础方向；可以在概念里改前置，或重新让 AI 起草。`;
    if (s.concepts < 2) return `${s.concepts} 个概念`;
    return `${s.concepts} 个概念 · ${s.roots} 个入口，可以同时开始 · 最多 ${s.width} 个概念并行`;
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

  /* The information half of the detail panel (the pages add their own buttons). `ctx.progress` is the saved map's
     progress or null; `ctx.mastered` is the creation page's "I already know this" mark. */
  function detailHTML(g, concept, ctx) {
    const c = ctx || {}, p = c.progress ? c.progress[concept.id] : null;
    const needs = needsOf(g, concept.id), waiting = new Set(waitingOn(g, c.progress, concept.id).map(n => n.id));
    const unlocks = dependents(g, concept.id);
    const chip = (n) => `<span class="need ${n.label}${c.progress ? (waiting.has(n.id) ? ' wait' : ' done') : ''}" title="${esc(LABELS[n.label])}" data-no-i18n>${esc(n.name)}</span>`;
    const lines = [];
    lines.push(`<h3 data-no-i18n>${esc(concept.name)}</h3>`);
    lines.push((concept.terms || []).length ? `<div class="terms" data-no-i18n>${esc(concept.terms.join(' · '))}</div>` : '<div class="terms">（没有检索词）</div>');
    if (typeText(concept)) lines.push(`<div class="terms"><span>类型：</span><span>${esc(TYPES[concept.type])}</span>${concept.why ? ` · <span>为什么在这里：</span><span data-no-i18n>${esc(concept.why)}</span>` : ''}</div>`);
    if (p) {
      lines.push(`<div class="badges"><span class="badge st-${esc(p.status)}" title="${esc(p.status === 'locked' ? LOCKED_TITLE : '')}">${esc(STATUS[p.status] || '')}</span>`
        + `${p.low_interest ? `<span class="badge" title="${esc(LOW_INTEREST_TITLE)}">暂不优先</span>` : ''}`
        + `${p.manual === 'mastered' ? '<span class="badge">你标为已掌握</span>' : ''}</div>`);
    } else if (c.mastered) {
      lines.push('<div class="badges"><span class="badge st-satisfied">你标为已掌握（起点）</span></div>');
    }
    lines.push(needs.length
      ? `<div class="needs">需要先读懂：${needs.map(chip).join('、')}</div>`
      : '<div class="needs">没有前置，这是一个入口，可以直接开始。</div>');
    if (p && p.status === 'locked' && waiting.size) {
      lines.push(`<div class="map-note">它只在等 ${[...waiting].map(id => `<span data-no-i18n>${esc(needs.find(n => n.id === id).name)}</span>`).join('、')}；其他分支的进度不影响它。</div>`);
    }
    if (unlocks.length) lines.push(`<div class="needs">读懂它之后可以读：${unlocks.map(n => `<span class="need" data-no-i18n>${esc(n.name)}</span>`).join('、')}</div>`);
    if (p) lines.push(`<div class="counts">${esc(countsText(p))}</div>`);
    if (concept.papers !== undefined) lines.push(`<div class="counts ${concept.grounding === 'ok' ? '' : 'none'}">公开文献里约 ${esc(concept.papers)} 篇</div>`);
    return lines.join('');
  }

  /* What the reader may say about where they start and how deep they want to go. Both can be skipped; the server
     accepts exactly these values (app/routeplan.py) and the page sends nothing else about the reader. */
  const BACKGROUNDS = [['', '不说明（默认）'], ['unknown', '未知（会补充基础概念）'], ['engineering', '计算机 / 工程'], ['ai_researcher', 'AI 研究者'], ['other', '其他']];
  const DEPTHS = [['', '不说明（默认：能读论文）'], ['overview', '快速了解'], ['read_papers', '能读论文'], ['implement', '研究 / 实现']];
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

  /* One proposed new direction: what it is called, the evidence behind it (counts and titles), where it would sit.
     Everything is data from the server and goes through esc(); the two buttons carry the id and nothing else. */
  function candidateHTML(c, options) {
    const locked = options && options.locked ? ' disabled title="先保存或放弃对学习图的修改"' : '';
    const titles = (c.papers || []).slice(0, 5).map((p) => `<li data-no-i18n>${esc(p.title)}</li>`).join('');
    const where = [];
    if (c.parent) where.push(`<div class="needs">建议放在：<span class="need" data-no-i18n>${esc(c.parent.name)}</span></div>`);
    if ((c.prereqs || []).length) where.push(`<div class="needs">建议的前置：${c.prereqs.map((p) => `<span class="need" data-no-i18n>${esc(p.name)}</span>`).join('、')}</div>`);
    return `<article class="growth-card"><h4 data-no-i18n>${esc(c.name)}</h4>`
      + `<div class="counts">${esc(c.paper_count)} 篇论文（其中你明确点过 ${esc(c.positive)} 篇）· ${esc(c.sources)} 个来源 · 与现有概念重叠 ${Math.round((Number(c.overlap) || 0) * 100)}%</div>`
      + `<ul class="growth-papers">${titles}</ul>${where.join('')}`
      + `<div class="row"><button type="button" class="primary small" data-growth="accept" data-id="${esc(c.id)}"${locked}>加入学习图</button>`
      + `<button type="button" class="ghost small" data-growth="reject" data-id="${esc(c.id)}"${locked}>不再提示</button></div></article>`;
  }

  /* What to say when there is nothing to propose: the truth, never a reason to feel behind. */
  function growthNote(result) {
    if ((result.candidates || []).length) return '';
    const watching = Number(result.watching) || 0;
    return watching ? `暂时没有可以加入的方向；还有 ${watching} 个方向证据不够，继续点“有用”或“已读懂”后再来看。` : '现在没有新的建议。继续读、点“有用”或“已读懂”后再来看。';
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
    const total = Number(route.total) || 0, done = Number(route.done) || 0;
    const share = Math.round((Number(route.exploration_share) || 0) * 100);
    return `已读懂 ${done} / ${total} 个概念 · 探索约占 ${share}%`;
  }

  return { MAX_NODES, needsEditorHTML, readNeeds, STATUS, LOW_INTEREST_TITLE, LOCKED_TITLE, countsText, candidateHTML, growthNote, BACKGROUNDS, DEPTHS, TYPES, boundaryHTML, readBoundary, typeText, actionsFor, summaryText, LABELS, layers, shape, shapeText, waitingOn, dependents, nodeStatus, detailHTML, needsOf, check, addConcept, removeConcept, setNeeds, rename, reuseIds, toggleMastered, payload, label };
});
