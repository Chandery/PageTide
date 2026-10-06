/* The library graph's second view (learning map + papers): a project's learning units (top, by how many prerequisites come first) with the
   papers it saved hung under the unit they fit, and the papers that fit no unit in their own row at the bottom.
   Pure: it turns the server's route-detail answer (and the similarity relations the page already has) into nodes
   and edges with positions. Nothing here is stored; the layout lives in memory only, so this view can never move a
   node of the paper graph. Titles and unit names are data for the graph's canvas, never markup. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PDHRouteDetail = api;
})(typeof window !== 'undefined' ? window : this, function () {
  const UNIT_W = 210, PAPER_GAP = 118, PAPER_ROW = 78, PAPER_DROP = 120, ROW_PAD = 110, MAX_COLS = 3, FREE_COLS = 8;

  const unitId = (id) => `ru:${id}`;
  const paperId = (key) => `rp:${key}`;
  const clip = (text, n) => { const s = String(text == null ? '' : text); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

  function layout(detail, relations) {
    if (!detail || !detail.available) return { nodes: [], edges: [], counts: { units: 0, papers: 0, matched: 0, unmatched: 0, omitted: 0 } };
    const units = detail.units || [], papers = detail.papers || [], matches = detail.matches || [];
    const drawn = new Set(papers.map((p) => p.key));
    const title = new Map(papers.map((p) => [p.key, p.title]));

    // each paper hangs under the unit it fits best (rank 0); the second unit gets a line only
    const anchor = new Map();
    for (const m of matches) if (m.rank === 0 && drawn.has(m.paper) && !anchor.has(m.paper)) anchor.set(m.paper, m.unit);
    const under = new Map(units.map((u) => [u.id, []]));
    for (const p of papers) if (anchor.has(p.key) && under.has(anchor.get(p.key))) under.get(anchor.get(p.key)).push(p.key);

    // rows by level; a unit's slot is as wide as the grid of papers under it
    const levels = [...new Set(units.map((u) => u.level))].sort((a, b) => a - b);
    const nodes = [], edges = [];
    let y = 0;
    for (const level of levels) {
      const row = units.filter((u) => u.level === level);
      const slots = row.map((u) => {
        const n = under.get(u.id).length, cols = Math.max(1, Math.min(n, MAX_COLS));
        return { unit: u, n, cols, rows: Math.ceil(n / cols), width: Math.max(UNIT_W, cols * PAPER_GAP + 30) };
      });
      const total = slots.reduce((sum, s) => sum + s.width, 0);
      let x = -total / 2;
      for (const s of slots) {
        const cx = x + s.width / 2;
        nodes.push({ id: unitId(s.unit.id), kind: 'unit', label: clip(s.unit.name, 34), name: s.unit.name, status: s.unit.state === 'proposed' ? 'proposed' : (s.unit.status || 'locked'),
          type: s.unit.type || null, why: s.unit.why || null, side: !!s.unit.side, x: cx, y });
        under.get(s.unit.id).forEach((key, i) => {
          const col = i % s.cols, rowIndex = Math.floor(i / s.cols);
          nodes.push({ id: paperId(key), kind: 'paper', key, label: clip(title.get(key), 30), x: cx + (col - (s.cols - 1) / 2) * PAPER_GAP, y: y + PAPER_DROP + rowIndex * PAPER_ROW });
        });
        x += s.width;
      }
      y += ROW_PAD + PAPER_DROP + Math.max(0, ...slots.map((s) => s.rows)) * PAPER_ROW;
    }

    // papers that fit no unit are listed, in a row of their own
    const free = (detail.unmatched || []).filter((key) => drawn.has(key));
    if (free.length) {
      nodes.push({ id: 'rg:unmatched', kind: 'group', label: '没有对应的学习单元', x: 0, y: y });
      free.forEach((key, i) => {
        const col = i % FREE_COLS, rowIndex = Math.floor(i / FREE_COLS), inRow = Math.min(FREE_COLS, free.length - rowIndex * FREE_COLS);
        nodes.push({ id: paperId(key), kind: 'paper', key, label: clip(title.get(key), 30), x: (col - (inRow - 1) / 2) * PAPER_GAP, y: y + 70 + rowIndex * PAPER_ROW });
      });
    }

    const unitIds = new Set(units.map((u) => u.id));
    (detail.prereqs || []).forEach((e, i) => {
      if (unitIds.has(e.from) && unitIds.has(e.to)) edges.push({ id: `rr:${i}`, source: unitId(e.from), target: unitId(e.to), kind: 'prerequisite', proposed: e.state === 'proposed', title: '要先读懂：上面的概念是下面概念的前置' });
    });
    matches.forEach((m, i) => {
      if (drawn.has(m.paper) && unitIds.has(m.unit)) edges.push({ id: `rm:${i}`, source: paperId(m.paper), target: unitId(m.unit), kind: 'matched_to', rank: m.rank,
        title: m.terms && m.terms.length ? `标题或摘要用到了检索词：${m.terms.join('、')}` : '标题或摘要用到了这个概念的检索词' });
    });
    ((relations && relations.edges) || []).forEach((e, i) => {
      if (e.source !== e.target && drawn.has(e.source) && drawn.has(e.target)) {
        edges.push({ id: `rs:${i}`, source: paperId(e.source), target: paperId(e.target), kind: 'similarity', weight: e.weight, title: `内容相似度 ${Math.round((e.weight || 0) * 100)}%（非引用关系）` });
      }
    });
    const matchedCount = papers.length - (detail.unmatched || []).length;
    return { nodes, edges, counts: { units: units.length, papers: papers.length, matched: matchedCount, unmatched: (detail.unmatched || []).length, omitted: detail.omitted || 0 } };
  }

  /* One sentence under the graph: what is drawn, and what was left out. */
  function summary(counts) {
    const parts = [`${counts.units} 个学习单元`, `${counts.papers} 篇论文`];
    if (counts.unmatched) parts.push(`${counts.unmatched} 篇没有对应的单元`);
    if (counts.omitted) parts.push(`另有 ${counts.omitted} 篇没有画出来`);
    return parts.join(' · ');
  }

  return { layout, summary, unitId, paperId };
});
