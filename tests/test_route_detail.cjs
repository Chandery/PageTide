const test = require('node:test');
const assert = require('node:assert/strict');
const D = require('../app/static/route-detail.js');

const plain = (value) => JSON.parse(JSON.stringify(value));
const detail = () => ({
  available: true, project_id: 'p',
  units: [
    { id: 'a', name: 'Crystal basics', level: 1, status: 'unlocked', state: 'active', type: 'topic' },
    { id: 'b', name: 'Epitaxy', level: 2, status: 'locked', state: 'active' },
    { id: 'g', name: 'Strain', level: 2, status: 'locked', state: 'proposed' }],
  prereqs: [{ from: 'a', to: 'b', state: 'active' }, { from: 'a', to: 'ghost', state: 'active' }],
  papers: [{ key: 'p1', title: 'Crystal growth' }, { key: 'p2', title: 'Epitaxial layers' }, { key: 'p3', title: 'Both' }, { key: 'free', title: 'Poetry' }],
  matches: [{ paper: 'p1', unit: 'a', rank: 0, terms: ['crystal growth'] }, { paper: 'p2', unit: 'b', rank: 0, terms: ['epitaxy'] },
    { paper: 'p3', unit: 'b', rank: 0, terms: ['epitaxy'] }, { paper: 'p3', unit: 'a', rank: 1, terms: ['lattice'] }],
  unmatched: ['free'], omitted: 3 });

test('units sit in rows by level, papers hang under the unit they fit, unmatched papers get a row of their own', () => {
  const out = plain(D.layout(detail(), null));
  const at = (id) => out.nodes.find((n) => n.id === id);
  assert.ok(at('ru:a').y < at('ru:b').y);
  assert.equal(at('ru:b').y, at('ru:g').y);
  assert.ok(at('rp:p1').y > at('ru:a').y);
  assert.ok(Math.abs(at('rp:p2').x - at('ru:b').x) <= 120 && at('rp:p2').y > at('ru:b').y);
  assert.ok(at('rp:free').y > at('rp:p2').y);
  assert.equal(at('rg:unmatched').kind, 'group');
});

test('no two nodes share a place', () => {
  const out = plain(D.layout(detail(), null));
  const seen = new Set(out.nodes.map((n) => `${Math.round(n.x)},${Math.round(n.y)}`));
  assert.equal(seen.size, out.nodes.length);
});

test('the edges are prerequisite, matched_to (with the terms that matched) and similarity between drawn papers only', () => {
  const rel = { edges: [{ source: 'p1', target: 'p2', weight: 0.4 }, { source: 'p1', target: 'not-drawn', weight: 0.9 }, { source: 'p1', target: 'p1', weight: 1 }] };
  const out = plain(D.layout(detail(), rel));
  const kinds = (k) => out.edges.filter((e) => e.kind === k);
  assert.equal(kinds('prerequisite').length, 1);   // the edge to an unknown unit is not drawn
  assert.deepEqual(kinds('matched_to').map((e) => e.rank).sort(), [0, 0, 0, 1]);
  assert.match(kinds('matched_to').find((e) => e.source === 'rp:p1').title, /crystal growth/);
  assert.equal(kinds('similarity').length, 1);
  assert.equal(kinds('similarity')[0].title, '内容相近');
  assert.ok(out.edges.every((e) => ['prerequisite', 'matched_to', 'similarity'].includes(e.kind)));   // no cites, no stance
});

test('a proposed unit is drawn as proposed and the progress status colours the rest', () => {
  const out = plain(D.layout(detail(), null));
  const status = Object.fromEntries(out.nodes.filter((n) => n.kind === 'unit').map((n) => [n.name, n.status]));
  assert.deepEqual(status, { 'Crystal basics': 'unlocked', Epitaxy: 'locked', Strain: 'proposed' });
});

test('titles stay plain data: long ones are cut, markup is not interpreted or removed', () => {
  const d = detail();
  d.papers[0].title = '<img src=x onerror=alert(1)>' + 'x'.repeat(200);
  const node = plain(D.layout(d, null)).nodes.find((n) => n.id === 'rp:p1');
  assert.ok(node.label.length <= 30);
  assert.ok(node.label.startsWith('<img'));
});

test('a missing or unavailable answer draws nothing', () => {
  assert.deepEqual(plain(D.layout(null, null)).nodes, []);
  assert.deepEqual(plain(D.layout({ available: false }, null)).edges, []);
});

test('a crowded unit spreads its papers over a grid instead of one line', () => {
  const d = detail();
  d.papers = Array.from({ length: 9 }, (_, i) => ({ key: `k${i}`, title: `Paper ${i}` }));
  d.matches = d.papers.map((p) => ({ paper: p.key, unit: 'a', rank: 0, terms: ['x'] }));
  d.unmatched = [];
  const nodes = plain(D.layout(d, null)).nodes.filter((n) => n.kind === 'paper');
  assert.equal(new Set(nodes.map((n) => n.y)).size, 3);   // nine papers, three to a row
  assert.equal(new Set(nodes.map((n) => `${n.x},${n.y}`)).size, 9);
});

test('the summary is just units and papers; left-out counts stay in the data, not the sentence', () => {
  const out = plain(D.layout(detail(), null));
  assert.equal(D.summary(out.counts), '3 个学习单元 · 4 篇论文');
  assert.equal(out.counts.unmatched, 1);assert.equal(out.counts.omitted, 3);
});

test('pending body verification is a separate row and matching tooltips identify current body terms',()=>{
  const d=detail();d.papers.push({key:'pending',title:'Pending paper'});d.pending=['pending'];
  d.matches[0].source='local_body';
  const out=plain(D.layout(d,null));
  assert.equal(out.counts.matched,3);assert.equal(out.counts.unmatched,1);assert.equal(out.counts.pending,1);
  const at=id=>out.nodes.find(n=>n.id===id);
  assert.ok(at('rg:pending').y>at('rp:free').y);assert.ok(at('rp:pending').y>at('rg:pending').y);
  assert.match(out.edges.find(e=>e.source==='rp:p1'&&e.kind==='matched_to').title,/检索词：crystal growth/);
  assert.doesNotMatch(D.summary(out.counts),/正文待核验/);
});
