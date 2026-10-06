/* The learning map as a drawn graph: concepts are nodes, "A is needed before B" is an arrow from A to B.
   layout() is a pure function (no DOM) so it can be tested; mount() draws it with HTML nodes over an SVG of
   the arrows. The vertical position of a node is only how many prerequisites deep it is: it does not mean a
   stage has to be finished, every concept waits for its own prerequisites and nothing else. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PDHGraph = api;
})(typeof window !== 'undefined' ? window : this, function () {
  const DEFAULTS = { nodeW: 176, nodeH: 72, gapX: 28, gapY: 54, dummyW: 10, pad: 16 };
  const SWEEPS = 12;

  /* The page's text scale (--s in theme.css): the drawing is laid out in real pixels, so on a large screen the nodes,
     gaps and text all grow together instead of the whole picture being capped at 100%. */
  function cssScale() {
    if (typeof document === 'undefined' || typeof getComputedStyle !== 'function') return 1;
    const value = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--s'));
    return value > 0 ? value : 1;
  }
  function scaled(unit) {
    const out = {};
    Object.keys(DEFAULTS).forEach((key) => { out[key] = Math.round(DEFAULTS[key] * unit * 10) / 10; });
    return out;
  }

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* Longest-path layer of every concept; an edge that would close a cycle is ignored (the server rejects cycles,
     this only keeps the drawing from looping on bad input). */
  const edgeKey = (from, to) => JSON.stringify([from, to]);

  function levels(ids, edges) {
    const needs = new Map(ids.map((id) => [id, []]));
    edges.forEach((e) => needs.get(e.to).push(e.from));
    const memo = new Map(), visiting = new Set(), back = new Set();
    const depth = (id) => {
      if (memo.has(id)) return memo.get(id);
      visiting.add(id);
      let best = 0;
      needs.get(id).forEach((p) => {
        if (visiting.has(p)) { back.add(edgeKey(p, id)); return; }
        best = Math.max(best, depth(p));
      });
      visiting.delete(id);
      memo.set(id, best + 1);
      return best + 1;
    };
    ids.forEach(depth);
    return { level: Object.fromEntries(memo), back };
  }

  /* The concepts and arrows that can be drawn: text ids only, the first of a repeated id, active arrows between
     two known concepts, no self-arrows or repeats. Ids such as "constructor" or "a>b" are ordinary ids. */
  function usable(graph) {
    const seen = new Set(), concepts = [];
    ((graph && graph.concepts) || []).forEach((c) => {
      if (c && typeof c.id === 'string' && !seen.has(c.id)) { seen.add(c.id); concepts.push(c); }
    });
    const pairs = new Set(), prereqs = [];
    ((graph && graph.prereqs) || []).forEach((e) => {
      if (!e || !seen.has(e.from) || !seen.has(e.to) || e.from === e.to || (e.state || 'active') !== 'active') return;
      const key = edgeKey(e.from, e.to);
      if (!pairs.has(key)) { pairs.add(key); prereqs.push({ from: e.from, to: e.to }); }
    });
    return { concepts, prereqs };
  }

  /* Number of arrow pairs that cross, for layers (arrays of ids, top to bottom) and links [upperId, lowerId]
     that only join neighbouring layers. */
  function crossings(order, links) {
    const pos = new Map(), layerOf = new Map();
    order.forEach((layer, l) => layer.forEach((id, i) => { pos.set(id, i); layerOf.set(id, l); }));
    const perGap = new Map();
    links.forEach(([u, d]) => {
      if (!perGap.has(layerOf.get(u))) perGap.set(layerOf.get(u), []);
      perGap.get(layerOf.get(u)).push([pos.get(u), pos.get(d)]);
    });
    let total = 0;
    perGap.forEach((list) => {
      for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
        if ((list[i][0] - list[j][0]) * (list[i][1] - list[j][1]) < 0) total++;
      }
    });
    return total;
  }

  /* Least-squares placement of one layer: each node wants some x, but must keep its order and a minimum gap to
     its left neighbour. Pool-adjacent-violators on the gap-adjusted targets gives the closest feasible x. */
  function place(desired, widths, gap) {
    const n = desired.length;
    const offset = [];
    let run = 0;
    for (let i = 0; i < n; i++) { offset.push(run); run += widths[i] + gap; }
    // Work on centres: c_i - offset_i must be non-decreasing, where offset is the cumulative distance between centres.
    const centre = [];
    run = 0;
    for (let i = 0; i < n; i++) {
      if (i > 0) run += widths[i - 1] / 2 + gap + widths[i] / 2;
      centre.push(run);
    }
    const target = desired.map((d, i) => d - centre[i]);
    const blocks = [];
    target.forEach((value, i) => {
      blocks.push({ sum: value, count: 1, from: i });
      while (blocks.length > 1 && blocks[blocks.length - 2].sum / blocks[blocks.length - 2].count > blocks[blocks.length - 1].sum / blocks[blocks.length - 1].count) {
        const b = blocks.pop(), a = blocks.pop();
        blocks.push({ sum: a.sum + b.sum, count: a.count + b.count, from: a.from });
      }
    });
    const out = new Array(n);
    blocks.forEach((b) => { for (let k = 0; k < b.count; k++) out[b.from + k] = b.sum / b.count + centre[b.from + k]; });
    return out;
  }

  function layout(graph, options) {
    const o = { ...DEFAULTS, ...(options || {}) };
    const { concepts, prereqs } = usable(graph);
    const ids = concepts.map((c) => c.id);
    if (!ids.length) return { nodes: {}, edges: [], order: [], width: 0, height: 0, options: o, crossings: 0 };

    const { level, back } = levels(ids, prereqs);
    const used = prereqs.filter((e) => !back.has(edgeKey(e.from, e.to)) && level[e.from] < level[e.to]);
    const depth = Math.max(...ids.map((id) => level[id]));

    // Layers, with a dummy node on every layer a long arrow passes through, so arrows get their own lane. Dummies are
    // objects tracked in a set, never recognised by the look of an id.
    const dummies = new Set();
    const layers = Array.from({ length: depth }, () => []);
    ids.forEach((id) => layers[level[id] - 1].push(id));
    const chains = used.map((e) => {
      const path = [e.from];
      for (let l = level[e.from] + 1; l < level[e.to]; l++) {
        const dummy = { dummy: `${e.from}\u0000${e.to}\u0000${l}` };
        dummies.add(dummy);
        layers[l - 1].push(dummy);
        path.push(dummy);
      }
      path.push(e.to);
      return { from: e.from, to: e.to, path };
    });
    const links = [];
    chains.forEach((c) => { for (let i = 0; i < c.path.length - 1; i++) links.push([c.path[i], c.path[i + 1]]); });
    const up = new Map(), down = new Map();
    const push = (map, key, value) => { if (!map.has(key)) map.set(key, []); map.get(key).push(value); };
    links.forEach(([u, l]) => { push(down, u, l); push(up, l, u); });

    // Order inside layers: barycentre sweeps down and up, keep the ordering with the fewest crossings.
    const index = () => { const pos = new Map(); layers.forEach((layer) => layer.forEach((id, i) => pos.set(id, i))); return pos; };
    const count = () => crossings(layers, links);
    let best = layers.map((l) => l.slice()), bestScore = count();
    const sweep = (from, to, step, neighbours) => {
      for (let l = from; l !== to; l += step) {
        const pos = index();
        const key = (id) => {
          const around = neighbours.get(id);
          return around && around.length ? around.reduce((sum, n) => sum + pos.get(n), 0) / around.length : pos.get(id);
        };
        const keyed = layers[l].map((id, i) => ({ id, k: key(id), i }));
        keyed.sort((a, b) => (a.k - b.k) || (a.i - b.i));
        layers[l] = keyed.map((x) => x.id);
      }
    };
    for (let round = 0; round < SWEEPS && bestScore > 0; round++) {
      sweep(1, layers.length, 1, up);
      sweep(layers.length - 2, -1, -1, down);
      const score = count();
      if (score < bestScore) { bestScore = score; best = layers.map((l) => l.slice()); }
    }
    for (let l = 0; l < layers.length; l++) layers[l] = best[l];

    // Horizontal positions: start packed and centred, then pull every node toward its neighbours' mean.
    const widthOf = (id) => (dummies.has(id) ? o.dummyW : o.nodeW);
    const xc = new Map();
    const widest = Math.max(...layers.map((layer) => layer.reduce((sum, id) => sum + widthOf(id), 0) + Math.max(0, layer.length - 1) * o.gapX));
    layers.forEach((layer) => {
      const total = layer.reduce((sum, id) => sum + widthOf(id), 0) + Math.max(0, layer.length - 1) * o.gapX;
      let x = (widest - total) / 2;
      layer.forEach((id) => { xc.set(id, x + widthOf(id) / 2); x += widthOf(id) + o.gapX; });
    });
    const relax = (l, neighbours) => {
      const layer = layers[l];
      const desired = layer.map((id) => {
        const around = neighbours.get(id);
        return around && around.length ? around.reduce((sum, n) => sum + xc.get(n), 0) / around.length : xc.get(id);
      });
      place(desired, layer.map(widthOf), o.gapX).forEach((x, i) => xc.set(layer[i], x));
    };
    for (let round = 0; round < 6; round++) {
      for (let l = 1; l < layers.length; l++) relax(l, up);
      for (let l = layers.length - 2; l >= 0; l--) relax(l, down);
    }
    for (let l = 1; l < layers.length; l++) relax(l, up);

    const left = Math.min(...[...xc].map(([id, x]) => x - widthOf(id) / 2));
    const rowH = o.nodeH + o.gapY;
    const nodes = Object.create(null);
    ids.forEach((id) => {
      nodes[id] = { id, layer: level[id], x: xc.get(id) - left - o.nodeW / 2 + o.pad, y: (level[id] - 1) * rowH + o.pad, w: o.nodeW, h: o.nodeH };
    });
    const rowOf = new Map();
    layers.forEach((layer, l) => layer.forEach((id) => rowOf.set(id, l)));
    // An arrow leaves the bottom of its source, crosses the gap between rows in a smooth S, and in every row it
    // passes it runs straight down its own lane (top to bottom of that row), so it never cuts across a neighbour.
    const outEdges = chains.map((c) => {
      const points = [];
      c.path.forEach((id, i) => {
        if (i === 0) points.push({ x: nodes[id].x + nodes[id].w / 2, y: nodes[id].y + nodes[id].h });
        else if (i === c.path.length - 1) points.push({ x: nodes[id].x + nodes[id].w / 2, y: nodes[id].y });
        else {
          const x = xc.get(id) - left + o.pad, top = rowOf.get(id) * rowH + o.pad;
          points.push({ x, y: top }, { x, y: top + o.nodeH });
        }
      });
      return { from: c.from, to: c.to, points, d: curve(points) };
    });
    const maxX = Math.max(...Object.values(nodes).map((n) => n.x + n.w), ...outEdges.flatMap((e) => e.points.map((pt) => pt.x)));
    const order = layers.map((layer) => layer.filter((id) => !dummies.has(id)));
    return { nodes, edges: outEdges, order, width: Math.ceil(maxX + o.pad), height: depth * rowH - o.gapY + o.pad * 2, options: o, crossings: bestScore };
  }

  function curve(points) {
    const r = (v) => Math.round(v * 10) / 10;
    let d = `M${r(points[0].x)},${r(points[0].y)}`;
    for (let i = 1; i < points.length; i++) {
      const p = points[i - 1], q = points[i], dy = (q.y - p.y) / 2;
      d += ` C${r(p.x)},${r(p.y + dy)} ${r(q.x)},${r(q.y - dy)} ${r(q.x)},${r(q.y)}`;
    }
    return d;
  }

  /* ---- drawing -------------------------------------------------------------------------------------------- */
  function related(graph, id) {
    const up = new Set(), down = new Set();
    const edges = usable(graph).prereqs;
    const walk = (start, field, other, into) => {
      const stack = [start];
      while (stack.length) {
        const here = stack.pop();
        edges.forEach((e) => { if (e[field] === here && !into.has(e[other])) { into.add(e[other]); stack.push(e[other]); } });
      }
    };
    walk(id, 'to', 'from', up);
    walk(id, 'from', 'to', down);
    return { up, down };
  }

  /* options: statusOf(concept) -> {key, label, title}, extraClass(concept), decorate(element, concept, node) (a hook
     to add to a node after it is built, e.g. an outline), edgeState(from, to) -> 'met' | 'wait' | 'plain' | 'ghost',
     selected, onSelect(id|null), scale ('fit-width' | number), maxHeight. Returns a controller. */
  function mount(host, graph, options) {
    const opts = options || {};
    const doc = host.ownerDocument;
    const unit = cssScale();
    const geo = layout(graph, { ...scaled(unit), ...(opts.layout || {}) });
    const data = usable(graph);
    host.replaceChildren();
    host.classList.add('rg');
    const view = opts.view || null;   // what a re-draw keeps: zoom, whether it was chosen, scroll position
    const state = { scale: 1, manual: false, selected: opts.selected || null };
    const byId = new Map(data.concepts.map((c) => [c.id, c]));

    const tools = doc.createElement('div');
    tools.className = 'rg-tools';
    tools.innerHTML = '<button type="button" class="ghost small" data-z="out" aria-label="缩小">−</button>'
      + '<button type="button" class="ghost small" data-z="in" aria-label="放大">+</button>'
      + '<button type="button" class="ghost small" data-z="width">适应宽度</button>'
      + '<button type="button" class="ghost small" data-z="all">看全图</button><span class="rg-zoom"></span>';
    const viewport = doc.createElement('div');
    viewport.className = 'rg-viewport';
    viewport.tabIndex = 0;
    viewport.setAttribute('role', 'group');
    viewport.setAttribute('aria-label', '学习图');
    const sizer = doc.createElement('div');
    sizer.className = 'rg-sizer';
    const canvas = doc.createElement('div');
    canvas.className = 'rg-canvas';
    canvas.style.width = `${geo.width}px`;
    canvas.style.height = `${geo.height}px`;
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = doc.createElementNS(svgNS, 'svg');
    svg.setAttribute('class', 'rg-edges');
    svg.setAttribute('width', geo.width);
    svg.setAttribute('height', geo.height);
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = ['', 'met', 'hi'].map((kind) => `<defs><marker id="rg-arrow${kind ? '-' + kind : ''}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="rg-arrowhead ${kind}"/></marker></defs>`).join('');
    const edgeEls = geo.edges.map((e) => {
      const path = doc.createElementNS(svgNS, 'path');
      path.setAttribute('d', e.d);
      svg.appendChild(path);
      return { path, edge: e };
    });
    canvas.appendChild(svg);
    const nodeEls = new Map();
    data.concepts.forEach((concept) => {
      const n = geo.nodes[concept.id];
      const status = opts.statusOf ? opts.statusOf(concept) : { key: 'plain', label: '', title: '' };
      const el = doc.createElement('button');
      el.type = 'button';
      el.className = `rg-node st-${status.key}${concept.side ? ' side' : ''}${opts.extraClass ? ' ' + opts.extraClass(concept) : ''}`;
      Object.assign(el.style, { left: `${n.x}px`, top: `${n.y}px`, width: `${n.w}px`, height: `${n.h}px` });
      el.dataset.id = concept.id;
      el.title = status.title || concept.name;
      el.innerHTML = `<span class="rg-name" data-no-i18n>${esc(concept.name)}</span>${status.label ? `<span class="rg-state">${esc(status.label)}</span>` : ''}`;
      if (opts.decorate) opts.decorate(el, concept, n);
      el.onclick = () => { if (opts.canSelect && !opts.canSelect(concept.id)) return; select(state.selected === concept.id ? null : concept.id, true); };
      canvas.appendChild(el);
      nodeEls.set(concept.id, el);
    });
    sizer.appendChild(canvas);
    viewport.appendChild(sizer);
    host.append(tools, viewport);
    if (opts.maxHeight) viewport.style.maxHeight = opts.maxHeight;

    function apply() {
      canvas.style.transform = `scale(${state.scale})`;
      sizer.style.width = `${Math.ceil(geo.width * state.scale)}px`;
      sizer.style.height = `${Math.ceil(geo.height * state.scale)}px`;
      tools.querySelector('.rg-zoom').textContent = `${Math.round(state.scale * 100)}%`;
    }
    function fitWidth() {
      const room = viewport.clientWidth;
      return room > 0 ? Math.max(0.55, Math.min(1, (room - 2) / geo.width)) : 1;
    }
    function fitAll() {
      const w = viewport.clientWidth, h = viewport.clientHeight || (opts.viewHeight || 520);
      return w > 0 ? Math.max(0.35, Math.min(1, (w - 2) / geo.width, (h - 2) / geo.height)) : 1;
    }
    function zoom(next, manual) { state.scale = Math.max(0.35, Math.min(1.6, next)); state.manual = manual; apply(); }
    tools.onclick = (event) => {
      const kind = event.target && event.target.dataset && event.target.dataset.z;
      if (kind === 'in') zoom(state.scale + 0.15, true);
      else if (kind === 'out') zoom(state.scale - 0.15, true);
      else if (kind === 'width') zoom(fitWidth(), false);
      else if (kind === 'all') zoom(fitAll(), true);
    };

    function select(id, notify) {
      state.selected = id && byId.has(id) ? id : null;
      const rel = state.selected ? related(graph, state.selected) : null;
      nodeEls.forEach((el, key) => {
        const inside = !rel || key === state.selected || rel.up.has(key) || rel.down.has(key);
        el.classList.toggle('selected', key === state.selected);
        el.classList.toggle('dim', !inside);
        el.classList.toggle('prereq', !!rel && rel.up.has(key));
        el.classList.toggle('unlocks', !!rel && rel.down.has(key));
        el.setAttribute('aria-pressed', String(key === state.selected));
      });
      edgeEls.forEach(({ path, edge }) => {
        const on = !rel || ((edge.to === state.selected || rel.up.has(edge.to)) && (edge.from === state.selected || rel.up.has(edge.from)))
          || ((edge.from === state.selected || rel.down.has(edge.from)) && (edge.to === state.selected || rel.down.has(edge.to)));
        const met = opts.edgeState ? opts.edgeState(edge.from, edge.to) : 'plain';
        const hi = !!rel && on;
        path.setAttribute('class', `rg-edge ${met}${on ? '' : ' dim'}${hi ? ' hi' : ''}`);
        path.setAttribute('marker-end', `url(#rg-arrow${hi ? '-hi' : met === 'met' ? '-met' : ''})`);
      });
      if (notify && opts.onSelect) opts.onSelect(state.selected);
    }

    if (view && typeof view.scale === 'number') zoom(view.scale, !!view.manual);
    else zoom(opts.scale === 'all' ? fitAll() : typeof opts.scale === 'number' ? opts.scale : fitWidth(), typeof opts.scale === 'number');
    if (view) { viewport.scrollLeft = view.left || 0; viewport.scrollTop = view.top || 0; }
    select(state.selected, false);
    let resizing = null;
    const onResize = () => { cancelAnimationFrame(resizing); resizing = requestAnimationFrame(() => {
      if (cssScale() !== unit && opts.onRescale) { opts.onRescale(); return; }   // crossed a screen-size step: draw again at the new size
      if (!state.manual) { state.scale = fitWidth(); apply(); }
    }); };
    if (typeof window !== 'undefined') window.addEventListener('resize', onResize);
    return {
      geo, select: (id) => select(id, false), selected: () => state.selected, scale: () => state.scale,
      view: () => ({ scale: state.scale, manual: state.manual, left: viewport.scrollLeft, top: viewport.scrollTop }),
      focusNode: (id) => { const el = nodeEls.get(id); if (el) el.focus({ preventScroll: true }); },
      destroy: () => { if (typeof window !== 'undefined') window.removeEventListener('resize', onResize); },
      scrollTo: (id) => { const n = geo.nodes[id]; if (n) { viewport.scrollTo({ left: Math.max(0, n.x * state.scale - 40), top: Math.max(0, n.y * state.scale - 40) }); } },
    };
  }

  return { layout, mount, levels, crossings, related, scaled, DEFAULTS };
});
