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

  function columns(g) {
    const level = layers(g), cols = [];
    g.concepts.forEach(c => { (cols[level[c.id] - 1] = cols[level[c.id] - 1] || []).push(c); });
    return cols.filter(Boolean);
  }

  function label(value) {
    if (value === null || value === undefined) return 'unknown';
    if (value >= 0.15) return 'supported';
    if (value <= -0.15) return 'contradicted';
    return 'neutral';
  }

  function needsOf(g, id) {
    const byId = Object.fromEntries(g.concepts.map(c => [c.id, c]));
    return g.prereqs.filter(e => e.to === id && byId[e.from]).map(e => ({ id: e.from, name: byId[e.from].name, support: e.support, label: label(e.support) }));
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

  function countsText(state) {
    const n = (v) => Number(v) || 0;
    return `收藏 ${n(state.useful)} · 不感兴趣 ${n(state.irrelevant)} · 太难 ${n(state.too_hard)} · 已展示 ${n(state.shown)}`;
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

  return { MAX_NODES, needsEditorHTML, readNeeds, STATUS, LOW_INTEREST_TITLE, LOCKED_TITLE, countsText, actionsFor, summaryText, LABELS, layers, columns, needsOf, check, addConcept, removeConcept, setNeeds, rename, toggleMastered, payload, label };
});
