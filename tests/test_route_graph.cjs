// Layout of the learning map as a graph (app/static/route-graph.js): pure functions, no DOM.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const G = require('../app/static/route-graph.js');

const graph = (ids, pairs) => ({ concepts: ids.map((id) => ({ id, name: id, hint: 1 })), prereqs: pairs.map(([from, to]) => ({ from, to })) });
const rect = (n) => ({ l: n.x, r: n.x + n.w, t: n.y, b: n.y + n.h });
const overlap = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;

function checkInvariants(g, layout, label = '') {
  const ids = Object.keys(layout.nodes);
  for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
    assert.ok(!overlap(rect(layout.nodes[ids[i]]), rect(layout.nodes[ids[j]])), `${label} nodes ${ids[i]} and ${ids[j]} overlap`);
  }
  ids.forEach((id) => {
    const n = layout.nodes[id];
    assert.ok(n.x >= 0 && n.y >= 0 && n.x + n.w <= layout.width && n.y + n.h <= layout.height, `${label} ${id} inside the canvas`);
  });
  layout.edges.forEach((e) => {
    const from = layout.nodes[e.from], to = layout.nodes[e.to];
    assert.ok(to.y > from.y, `${label} arrow ${e.from}->${e.to} points down`);
    assert.equal(e.points[0].y, from.y + from.h);
    assert.equal(e.points[e.points.length - 1].y, to.y);
    for (let i = 1; i < e.points.length; i++) assert.ok(e.points[i].y > e.points[i - 1].y, `${label} arrow ${e.from}->${e.to} never turns back`);
    // the whole drawn curve, not only its lane points, must stay out of every other node
    sampleEdge(e).forEach((pt) => Object.entries(layout.nodes).forEach(([id, n]) => {
      if (id === e.from || id === e.to) return;
      assert.ok(!(pt.x > n.x + 1 && pt.x < n.x + n.w - 1 && pt.y > n.y + 1 && pt.y < n.y + n.h - 1), `${label} arrow ${e.from}->${e.to} runs through ${id}`);
    }));
  });
}

// points of the drawn path: one cubic per pair of neighbouring points, vertical tangents (see curve() in route-graph.js)
function sampleEdge(e) {
  const out = [];
  for (let i = 1; i < e.points.length; i++) {
    const p = e.points[i - 1], q = e.points[i], dy = (q.y - p.y) / 2;
    for (let k = 0; k <= 24; k++) {
      const t = k / 24, u = 1 - t;
      out.push({ x: u * u * u * p.x + 3 * u * u * t * p.x + 3 * u * t * t * q.x + t * t * t * q.x,
                 y: u * u * u * p.y + 3 * u * u * t * (p.y + dy) + 3 * u * t * t * (q.y - dy) + t * t * t * q.y });
    }
  }
  return out;
}

test('an empty or missing graph lays out to nothing', () => {
  assert.deepEqual(G.layout({ concepts: [], prereqs: [] }).nodes, {});
  assert.deepEqual(G.layout(null).order, []);
});

test('a chain is a column, each concept one row below the one it needs', () => {
  const g = graph(['a', 'b', 'c', 'd'], [['a', 'b'], ['b', 'c'], ['c', 'd']]);
  const l = G.layout(g);
  assert.deepEqual(l.order, [['a'], ['b'], ['c'], ['d']]);
  checkInvariants(g, l);
  assert.equal(new Set(Object.values(l.nodes).map((n) => n.x)).size, 1);
});

test('two independent branches sit side by side and meet only where something needs both', () => {
  const g = graph(['a', 'b', 'c', 'd', 'e'], [['a', 'c'], ['b', 'd'], ['c', 'e'], ['d', 'e']]);
  const l = G.layout(g);
  checkInvariants(g, l);
  assert.equal(l.nodes.a.y, l.nodes.b.y);                  // both entry points at the top
  assert.ok(l.nodes.a.x !== l.nodes.b.x);
  assert.equal(l.nodes.c.y, l.nodes.d.y);
  assert.equal(l.crossings, 0);
  const mid = (l.nodes.c.x + l.nodes.d.x) / 2;
  assert.ok(Math.abs(l.nodes.e.x - mid) < 1, 'the concept that needs both is centred under them');
  assert.ok(l.nodes.c.x < l.nodes.d.x === l.nodes.a.x < l.nodes.b.x, 'branches keep their order (no needless swap)');
});

test('branches of different depth are not forced into shared stages: a concept sits right under what it needs', () => {
  // long branch a->b->c->d, short branch x->y; y needs only x so it is on row 2, not row 4
  const g = graph(['a', 'b', 'c', 'd', 'x', 'y'], [['a', 'b'], ['b', 'c'], ['c', 'd'], ['x', 'y']]);
  const l = G.layout(g);
  checkInvariants(g, l);
  assert.equal(l.nodes.y.layer, 2);
  assert.equal(l.nodes.d.layer, 4);
});

test('a long arrow gets a lane that avoids the nodes in between', () => {
  // a -> d directly, while a -> b -> c -> d is the long way round
  const g = graph(['a', 'b', 'c', 'd'], [['a', 'b'], ['b', 'c'], ['c', 'd'], ['a', 'd']]);
  const l = G.layout(g);
  checkInvariants(g, l);
  const long = l.edges.find((e) => e.from === 'a' && e.to === 'd');
  assert.equal(long.points.length, 6);                       // start, then top and bottom of each of the two rows it passes, end
  assert.equal(long.points[1].x, long.points[2].x);          // straight down its lane inside a row
  assert.equal(long.points[3].x, long.points[4].x);
});

test('an arrow never cuts across the corner of a neighbouring node (review repro)', () => {
  const g = graph(['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7'],
    [['c1', 'c2'], ['c1', 'c3'], ['c2', 'c4'], ['c3', 'c5'], ['c4', 'c5'], ['c3', 'c6'], ['c3', 'c7']]);
  checkInvariants(g, G.layout(g));
});

test('ids are just text: names of object members, a leading tilde, arrows and repeats are all fine', () => {
  const g = graph(['constructor', '__proto__', '~x', 'a>b', 'toString', 'd'],
    [['constructor', 'a>b'], ['__proto__', '~x'], ['a>b', 'd'], ['~x', 'd'], ['constructor', 'd'], ['toString', 'd']]);
  const l = G.layout(g);
  checkInvariants(g, l);
  assert.equal(Object.keys(l.nodes).length, 6);
  assert.deepEqual(l.order.map((layer) => layer.length), [3, 2, 1]);   // dummies never show up in the order
  assert.equal(l.edges.length, 6);
  // the two different arrows constructor->a>b and constructor>a->b stay different arrows
  const h = graph(['a', 'b', 'c', 'a>b', 'c'.repeat(2)], [['a', 'b>c'], ['a>b', 'c'], ['a', 'a>b']]);
  assert.equal(G.layout(h).edges.length, 2);
});

test('repeated ids draw once, and arrows that are not active are not drawn', () => {
  const g = { concepts: [{ id: 'a', name: 'A' }, { id: 'a', name: 'A again' }, { id: 'b', name: 'B' }, { id: 'c', name: 'C' }],
              prereqs: [{ from: 'a', to: 'b' }, { from: 'b', to: 'c', state: 'proposed' }, { from: 'a', to: 'c', state: 'archived' }] };
  const l = G.layout(g);
  assert.equal(Object.keys(l.nodes).length, 3);
  assert.equal(l.edges.length, 1);
  assert.deepEqual(l.order.map((layer) => layer.length), [2, 1]);
});

test('ordering removes avoidable crossings', () => {
  // listed in an order that crosses if left alone: the second entry point feeds the first dependent and vice versa
  const g = graph(['a', 'b', 'x', 'y'], [['a', 'y'], ['b', 'x']]);
  assert.equal(G.layout(g).crossings, 0);
  const wide = graph(['a', 'b', 'c', 'p', 'q', 'r'], [['a', 'r'], ['b', 'q'], ['c', 'p']]);
  const l = G.layout(wide);
  assert.equal(l.crossings, 0);
  checkInvariants(wide, l);
});

test('the crossing counter counts what it should', () => {
  assert.equal(G.crossings([['a', 'b'], ['x', 'y']], [['a', 'y'], ['b', 'x']]), 1);
  assert.equal(G.crossings([['a', 'b'], ['x', 'y']], [['a', 'x'], ['b', 'y']]), 0);
  assert.equal(G.crossings([['a', 'b'], ['x', 'y'], ['m', 'n']], [['a', 'y'], ['b', 'x'], ['x', 'n'], ['y', 'm']]), 2);
});

test('a hub that many need is centred over them', () => {
  const g = graph(['a', 'b', 'c', 'hub'], [['a', 'hub'], ['b', 'hub'], ['c', 'hub']]);
  const l = G.layout(g);
  checkInvariants(g, l);
  assert.ok(Math.abs(l.nodes.hub.x - l.nodes.b.x) < 1);
});

test('a concept sits under what it needs, not in the middle of its row', () => {
  const g = graph(['a', 'b', 'c', 'd', 'y'], [['d', 'y']]);
  const l = G.layout(g);
  checkInvariants(g, l);
  assert.ok(Math.abs(l.nodes.y.x - l.nodes.d.x) < 1, 'y is right under d');
  const g2 = graph(['a', 'b', 'c', 'd', 'e', 'f', 'g'], [['a', 'e'], ['a', 'f'], ['d', 'g']]);
  const l2 = G.layout(g2);
  checkInvariants(g2, l2);
  assert.ok(Math.abs(l2.nodes.g.x - l2.nodes.d.x) < 1);
  assert.ok(Math.abs((l2.nodes.e.x + l2.nodes.f.x) / 2 - l2.nodes.a.x) < G.DEFAULTS.nodeW, 'two dependents stay near their one prerequisite');
});

test('a map with no arrows is one row', () => {
  const g = graph(['a', 'b', 'c'], []);
  const l = G.layout(g);
  assert.equal(new Set(Object.values(l.nodes).map((n) => n.y)).size, 1);
  checkInvariants(g, l);
});

test('bad input is survived: dangling, self, duplicate and cyclic arrows are ignored or broken', () => {
  const g = graph(['a', 'b', 'c'], [['a', 'a'], ['a', 'zzz'], ['q', 'a'], ['a', 'b'], ['a', 'b'], ['b', 'c'], ['c', 'a']]);
  const l = G.layout(g);
  checkInvariants(g, l);
  assert.ok(l.edges.length <= 2);
});

test('the layout is deterministic and does not touch its input', () => {
  const g = graph(['a', 'b', 'c', 'd', 'e'], [['a', 'c'], ['b', 'd'], ['c', 'e'], ['d', 'e']]);
  const before = JSON.stringify(g);
  assert.deepEqual(G.layout(g), G.layout(JSON.parse(before)));
  assert.equal(JSON.stringify(g), before);
});

test('a width bound: twelve concepts in a chain stay one node wide, a fan stays inside the canvas', () => {
  const ids = Array.from({ length: 12 }, (_, i) => `n${i}`);
  const chain = G.layout(graph(ids, ids.slice(1).map((id, i) => [ids[i], id])));
  assert.equal(chain.width, G.DEFAULTS.nodeW + G.DEFAULTS.pad * 2);
  const fan = graph(['root', ...ids], ids.map((id) => ['root', id]));
  const l = G.layout(fan);
  checkInvariants(fan, l);
  assert.equal(l.order[1].length, 12);
});

test('seeded random acyclic graphs of up to 40 concepts keep every invariant and finish quickly', () => {
  let seed = 12345;
  const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
  const started = Date.now();
  for (let round = 0; round < 60; round++) {
    const n = 2 + Math.floor(rnd() * 39);
    const ids = Array.from({ length: n }, (_, i) => `n${i}`);
    const pairs = [];
    for (let i = 1; i < n; i++) for (let k = 0; k < 3; k++) if (rnd() < 0.35) pairs.push([ids[Math.floor(rnd() * i)], ids[i]]);
    const g = graph(ids, pairs);
    checkInvariants(g, G.layout(g), `round ${round}`);   // includes the drawn curves, not only the lane points
  }
  assert.ok(Date.now() - started < 8000, 'sixty graphs of up to forty concepts in a few seconds');
});

test('related() returns every prerequisite and every dependent, nothing else', () => {
  const g = graph(['a', 'b', 'c', 'd', 'x'], [['a', 'b'], ['b', 'c'], ['c', 'd']]);
  const r = G.related(g, 'b');
  assert.deepEqual([...r.up].sort(), ['a']);
  assert.deepEqual([...r.down].sort(), ['c', 'd']);
  assert.equal(r.up.has('x') || r.down.has('x'), false);
});
