'use strict';
// Route Mode slice 5b: the layered learning-map editor of the creation page (pure functions; the DOM glue is in project-creation.js).
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function load() {
  const context = vm.createContext({ module: { exports: {} }, window: {} });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/route-editor.js'), 'utf8'), context);
  return context.module.exports;
}

const concept = (id, name, hint, extra = {}) => ({ id, name, terms: [name.toLowerCase()], hint, origin: 'plan', state: 'active', side: false, ...extra });
const graph = () => ({
  concepts: [concept('c1', 'Crystal basics', 1), concept('c2', 'Epitaxy', 2), concept('c3', 'Doping', 2), concept('c4', 'MBE', 3)],
  prereqs: [{ from: 'c1', to: 'c2', support: 0.4 }, { from: 'c1', to: 'c3', support: -0.3 }, { from: 'c2', to: 'c4', support: null }],
  targets: ['c4'],
});

test('layers are the longest path from the entry points', () => {
  const R = load();
  assert.deepEqual({ ...R.layers(graph()) }, { c1: 1, c2: 2, c3: 2, c4: 3 });
});

test('columns group concepts by layer in a stable order', () => {
  const R = load();
  const cols = R.columns(graph());
  assert.deepEqual(JSON.parse(JSON.stringify(cols.map(col => col.map(c => c.id)))), [['c1'], ['c2', 'c3'], ['c4']]);
});

test('a concept knows its prerequisites by name and the corpus label of each edge', () => {
  const R = load();
  const info = R.needsOf(graph(), 'c4');
  assert.deepEqual(JSON.parse(JSON.stringify(info.map(i => [i.name, i.label]))), [['Epitaxy', 'unknown']]);
  assert.deepEqual(JSON.parse(JSON.stringify(R.needsOf(graph(), 'c3').map(i => [i.name, i.label]))), [['Crystal basics', 'contradicted']]);
  assert.deepEqual(JSON.parse(JSON.stringify(R.needsOf(graph(), 'c2').map(i => i.label))), ['supported']);
});

test('removing a concept removes its edges and keeps the graph valid', () => {
  const R = load();
  const next = R.removeConcept(graph(), 'c2');
  assert.deepEqual(JSON.parse(JSON.stringify(next.concepts.map(c => c.id))), ['c1', 'c3', 'c4']);
  assert.equal(next.prereqs.length, 1);
  assert.equal(R.check(next).ok, true);
});

test('adding a concept picks a fresh id and refuses a cycle, a harder prerequisite, a full map', () => {
  const R = load();
  const g = R.addConcept(graph(), { name: 'Strain', terms: ['strain'], hint: 3 }, ['c2']);
  assert.equal(g.concepts.length, 5);
  assert.equal(g.concepts[4].id, 'c5');
  assert.throws(() => R.addConcept(graph(), { name: 'Loop', terms: ['loop'], hint: 1 }, ['c4']), (e) => /更基础/.test(e.message));
  const cyclic = graph();
  assert.throws(() => R.setNeeds(cyclic, 'c1', ['c4']), (e) => /更基础|环/.test(e.message));
  let full = graph();
  for (let i = 0; i < R.MAX_NODES; i += 1) { try { full = R.addConcept(full, { name: `N${i}`, terms: [`n${i}`], hint: 2 }, []); } catch (e) { break; } }
  assert.ok(full.concepts.length <= R.MAX_NODES);
  assert.throws(() => R.addConcept(full, { name: 'one more', terms: ['x'], hint: 2 }, []), (e) => /太大/.test(e.message));
});

test('editing keeps ids stable and cleans the text', () => {
  const R = load();
  const g = R.rename(graph(), 'c2', '  Epitaxial  growth,  ', ['epitaxy', ' epitaxial growth ', 'extra', '']);
  assert.equal(g.concepts[1].name, 'Epitaxial growth');
  assert.deepEqual(JSON.parse(JSON.stringify(g.concepts[1].terms)), ['epitaxy', 'epitaxial growth']);
  assert.equal(g.concepts[1].id, 'c2');
  assert.throws(() => R.rename(graph(), 'c2', '   ', []), (e) => /名称/.test(e.message));
});

test('a start mark is a set of concept ids that must exist and may not be repeated', () => {
  const R = load();
  assert.deepEqual(JSON.parse(JSON.stringify(R.toggleMastered([], 'c1', graph()))), ['c1']);
  assert.deepEqual(JSON.parse(JSON.stringify(R.toggleMastered(['c1'], 'c1', graph()))), []);
  assert.deepEqual(JSON.parse(JSON.stringify(R.toggleMastered(['c1'], 'nope', graph()))), ['c1']);
});

test('check reports the reason a graph would be refused by the server', () => {
  const R = load();
  assert.equal(R.check(graph()).ok, true);
  const bad = graph();
  bad.concepts[0].hint = 3;   // c1 -> c2 now has a prerequisite harder than its dependent
  assert.match(R.check(bad).reason, /更基础/);
  const cyc = graph();
  cyc.concepts.forEach(c => { c.hint = 2; });
  cyc.prereqs.push({ from: 'c4', to: 'c1' });
  assert.match(R.check(cyc).reason, /环/);
  assert.match(R.check({ concepts: [], prereqs: [], targets: [] }).reason, /至少/);
});

test('the payload sent on create carries the graph and only existing mastered ids', () => {
  const R = load();
  const body = R.payload(graph(), ['c1', 'ghost']);
  assert.deepEqual(JSON.parse(JSON.stringify(body.mastered)), ['c1']);
  assert.equal(body.graph.concepts.length, 4);
  assert.equal(R.payload(null, []), null);
  assert.equal(R.payload({ concepts: [], prereqs: [], targets: [] }, []), null);
});

test('the status words never describe disinterest, lateness or debt', () => {
  const R = load();
  for (const text of Object.values(R.LABELS)) assert.doesNotMatch(text, /落后|欠|不喜欢|未完成|逾期/);
});

test('a repeated prerequisite is collapsed so the page and the server agree', () => {
  const R = load();
  const g = R.setNeeds(graph(), 'c4', ['c2', 'c2']);
  assert.equal(g.prereqs.filter(e => e.to === 'c4').length, 1);
  const added = R.addConcept(graph(), { name: 'Strain', terms: ['strain'], hint: 3 }, ['c2', 'c2']);
  assert.equal(added.prereqs.filter(e => e.to === 'c5').length, 1);
});

test('a name made only of punctuation is refused like the server refuses it', () => {
  const R = load();
  assert.throws(() => R.rename(graph(), 'c1', '++', []), (e) => /名称/.test(e.message));
  assert.throws(() => R.addConcept(graph(), { name: '!!!', terms: [], hint: 2 }, []), (e) => /名称/.test(e.message));
  assert.equal(R.rename(graph(), 'c1', '量子阱', []).concepts[0].name, '量子阱');
});

test('status words describe where a concept stands, never disinterest, lateness or debt', () => {
  const R = load();
  assert.deepEqual(Object.keys(JSON.parse(JSON.stringify(R.STATUS))).sort(), ['archived', 'locked', 'proposed', 'satisfied', 'unlocked']);
  // the only allowed mention of disinterest is its explicit negation
  for (const text of [...Object.values(R.STATUS), R.LOW_INTEREST_TITLE, R.LOCKED_TITLE]) assert.doesNotMatch(text.replace('不等于不喜欢', ''), /落后|欠|不喜欢|未完成|逾期|错过|没读|讨厌/);
  assert.match(R.LOW_INTEREST_TITLE, /不等于不喜欢/);
});

test('a concept card summary reports only explicit counts', () => {
  const R = load();
  const text = R.countsText({ useful: 2, irrelevant: 1, too_hard: 1, shown: 5, rated: 3 });
  assert.match(text, /收藏 2/);
  assert.match(text, /太难 1/);
  assert.match(text, /已展示 5/);
  assert.doesNotMatch(R.countsText({ useful: 0, irrelevant: 0, too_hard: 0, shown: 0, rated: 0 }), /undefined|NaN/);
});

test('the actions offered for a concept depend on its state and are all reversible', () => {
  const R = load();
  const names = (state) => JSON.parse(JSON.stringify(R.actionsFor(state).map(a => a.value + ':' + (a.clear ? 'clear' : 'set'))));
  assert.deepEqual(names({ status: 'unlocked', manual: null, low_interest: false }), ['mastered:set', 'demoted:set']);
  assert.deepEqual(names({ status: 'locked', manual: null, low_interest: false }), ['unlocked:set', 'mastered:set', 'demoted:set']);
  assert.deepEqual(names({ status: 'satisfied', manual: 'mastered', low_interest: false }), ['mastered:clear', 'demoted:set']);
  assert.deepEqual(names({ status: 'unlocked', manual: 'demoted', low_interest: true }), ['mastered:set', 'demoted:clear']);
  assert.deepEqual(names({ status: 'proposed', manual: null, low_interest: false }), []);
});

test('the progress summary line is plain', () => {
  const R = load();
  assert.equal(R.summaryText({ done: 2, total: 5, exploration_share: 0.26 }), '已读懂 2 / 5 个概念 · 探索约占 26%');
  assert.doesNotMatch(R.summaryText({ done: 0, total: 0, exploration_share: 0.1 }), /NaN/);
});

test('a concept name must be unique ignoring case and spaces', () => {
  const R = load();
  assert.throws(() => R.addConcept(graph(), { name: '  epitaxy ', terms: ['x'], hint: 2 }, []), (e) => /同名/.test(e.message));
  assert.throws(() => R.rename(graph(), 'c3', 'EPITAXY', []), (e) => /同名/.test(e.message));
  assert.equal(R.rename(graph(), 'c2', 'Epitaxy', ['epitaxy']).concepts[1].name, 'Epitaxy');   // keeping its own name is fine
});

test('prerequisites are edited by id, so a name containing a slash is not a problem', () => {
  const R = load();
  const g = graph();
  g.concepts.push(concept('c5', 'Planning/Control', 2));
  g.concepts.push(concept('c6', 'Robot', 3));
  const html = R.needsEditorHTML(g, 'c6');
  assert.match(html, /value="c5"/);
  assert.doesNotMatch(html, /value="c6"/);                  // not a prerequisite of itself
  assert.match(html, /Planning\/Control/);
  const next = R.setNeeds(g, 'c6', ['c5']);
  assert.deepEqual(JSON.parse(JSON.stringify(R.needsOf(next, 'c6').map(n => n.name))), ['Planning/Control']);
});

test('the prerequisite editor escapes concept names', () => {
  const R = load();
  const g = graph();
  g.concepts.push(concept('c5', '<img src=x onerror=alert(1)>', 2));
  assert.doesNotMatch(R.needsEditorHTML(g, 'c4'), /<img/);
});

test('the low-interest tooltip names its real causes and the way back', () => {
  const R = load();
  assert.match(R.LOW_INTEREST_TITLE, /暂不优先/);
  assert.match(R.LOW_INTEREST_TITLE, /不感兴趣/);
  assert.match(R.LOW_INTEREST_TITLE, /不等于不喜欢/);
  assert.match(R.LOW_INTEREST_TITLE, /恢复/);
});
