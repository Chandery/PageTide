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

test('shape tells a branched map from a single line and counts entry points', () => {
  const R = load();
  const g = graph();
  assert.deepEqual(JSON.parse(JSON.stringify(R.shape(g))), { concepts: 4, roots: 1, levels: 3, width: 2, chain: false });
  const chain = { concepts: ['a', 'b', 'c', 'd'].map((id, i) => ({ id, name: id, hint: i + 1, state: 'active' })),
                  prereqs: [['a', 'b'], ['b', 'c'], ['c', 'd']].map(([from, to]) => ({ from, to, state: 'active' })) };
  assert.equal(R.shape(chain).chain, true);
  assert.match(R.shapeText(R.shape(chain)), /一条单线/);
  assert.match(R.shapeText(R.shape(g)), /1 个入口.*最多 2 个概念并行/);
  assert.equal(R.shapeText(R.shape({ concepts: [], prereqs: [] })), '');
  const two = { concepts: chain.concepts.slice(0, 2), prereqs: chain.prereqs.slice(0, 1) };
  assert.equal(R.shape(two).chain, false);   // two concepts in a row is not "a line", it is a small map
  const archived = { concepts: chain.concepts.map((c, i) => (i === 3 ? { ...c, state: 'archived' } : c)), prereqs: chain.prereqs };
  assert.equal(R.shape(archived).concepts, 3);
});

test('a locked concept waits only for its own unmet prerequisites', () => {
  const R = load();
  const g = { concepts: ['a', 'b', 'c'].map((id) => ({ id, name: id.toUpperCase(), hint: 1, state: 'active' })),
              prereqs: [{ from: 'a', to: 'c', state: 'active' }, { from: 'b', to: 'c', state: 'active' }] };
  const progress = { a: { status: 'satisfied' }, b: { status: 'unlocked' }, c: { status: 'locked' } };
  assert.deepEqual(JSON.parse(JSON.stringify(R.waitingOn(g, progress, 'c').map((n) => n.id))), ['b']);
  assert.deepEqual(JSON.parse(JSON.stringify(R.dependents(g, 'a').map((n) => n.id))), ['c']);
  assert.deepEqual(R.waitingOn(g, progress, 'a'), []);
});

test('a node says unsaved for a draft with structural edits, and its saved status otherwise', () => {
  const R = load();
  const c = { id: 'x', name: 'X' };
  assert.deepEqual(JSON.parse(JSON.stringify(R.nodeStatus(c, {}, false))), { key: 'proposed', label: '未保存', title: 'X' });
  assert.equal(R.nodeStatus(c, { x: { status: 'locked' } }, true).label, '未解锁');
  assert.equal(R.nodeStatus(c, { x: { status: 'locked' } }, true).title, R.LOCKED_TITLE);
  assert.equal(R.nodeStatus(c, { x: { status: 'unlocked', low_interest: true } }, true).title, R.LOW_INTEREST_TITLE);
  assert.equal(R.nodeStatus(c, {}, true).key, 'proposed');   // no progress row yet
});

test('the detail text names what a concept needs and what it opens, escapes names, and never says late or behind', () => {
  const R = load();
  const g = graph();
  g.concepts[1].name = '<img src=x onerror=alert(1)>';
  const html = R.detailHTML(g, g.concepts[1], { progress: { c1: { status: 'satisfied' }, c2: { status: 'unlocked', useful: 1, irrelevant: 0, too_hard: 0, shown: 3 } } });
  assert.ok(!html.includes('<img'), html);
  assert.match(html, /需要先读懂/);
  assert.match(html, /读懂它之后可以读/);
  assert.match(html, /need[^"]* done/);
  const entry = R.detailHTML(g, g.concepts[0], {});
  assert.match(entry, /这是一个入口/);
  assert.doesNotMatch(html + entry, /落后|拖延|逾期|未读|欠/);
  const locked = R.detailHTML(g, g.concepts[3], { progress: { c1: { status: 'satisfied' }, c2: { status: 'unlocked' }, c3: { status: 'unlocked' }, c4: { status: 'locked' } } });
  assert.match(locked, /只在等/);
  assert.match(locked, /其他分支的进度不影响它/);
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
  const text = R.countsText({ useful: 2, understood: 1, irrelevant: 1, too_hard: 1, shown: 5, rated: 3 });
  assert.match(text, /收藏 2/);
  assert.match(text, /已读懂 1/);
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

test('a draft that replaces the saved map reuses the saved id of every concept with the same name', () => {
  const R = load();
  const saved = { concepts: [concept('c1', 'Crystal basics', 1), concept('c2', 'Epitaxy', 2)], prereqs: [{ from: 'c1', to: 'c2' }], targets: ['c2'] };
  const draft = { concepts: [concept('c1', 'epitaxy', 1), concept('c2', 'CRYSTAL  basics', 1), concept('c3', 'Doping', 2), concept('c4', 'MBE', 3)],
                  prereqs: [{ from: 'c2', to: 'c1' }, { from: 'c1', to: 'c4' }, { from: 'c2', to: 'c3' }], targets: ['c4'] };
  const out = R.reuseIds(draft, saved);
  const byName = Object.fromEntries(out.concepts.map((c) => [c.name, c.id]));
  assert.equal(byName['CRYSTAL  basics'], 'c1');
  assert.equal(byName.epitaxy, 'c2');
  assert.equal(new Set(out.concepts.map((c) => c.id)).size, 4);
  assert.ok(out.concepts.filter((c) => !['CRYSTAL  basics', 'epitaxy'].includes(c.name)).every((c) => !['c1', 'c2'].includes(c.id)), 'new concepts never take a reused id');
  assert.deepEqual(JSON.parse(JSON.stringify(out.prereqs.map((e) => [e.from, e.to]))), [['c1', 'c2'], ['c2', byName.MBE], ['c1', byName.Doping]]);
  assert.deepEqual(JSON.parse(JSON.stringify(out.targets)), [byName.MBE]);
  assert.equal(R.check(out).ok, true);
  assert.equal(draft.concepts[0].id, 'c1');   // the input is not touched
  assert.equal(draft.concepts[0].name, 'epitaxy');
});

test('reuseIds with nothing saved, or with no name in common, only keeps the draft valid', () => {
  const R = load();
  const draft = { concepts: [concept('c1', 'A', 1), concept('c2', 'B', 2)], prereqs: [{ from: 'c1', to: 'c2' }], targets: ['c2'] };
  assert.deepEqual(JSON.parse(JSON.stringify(R.reuseIds(draft, null))), draft);
  const saved = { concepts: [concept('c1', 'X', 1), concept('c7', 'Y', 2)], prereqs: [], targets: [] };
  const out = R.reuseIds(draft, saved);
  assert.ok(out.concepts.every((c) => !['c1', 'c7'].includes(c.id)), 'no draft concept may take the id of a saved concept it does not match by name');
  assert.equal(R.check(out).ok, true);
});

test('only active arrows count as what a concept needs or opens', () => {
  const R = load();
  const g = graph();
  g.prereqs.push({ from: 'c3', to: 'c4', state: 'proposed' }, { from: 'c1', to: 'c4', state: 'archived' });
  assert.deepEqual(JSON.parse(JSON.stringify(R.needsOf(g, 'c4').map((n) => n.id))), ['c2']);
  assert.deepEqual(JSON.parse(JSON.stringify(R.dependents(g, 'c3').map((n) => n.id))), []);
  assert.deepEqual(JSON.parse(JSON.stringify(R.waitingOn(g, { c2: { status: 'unlocked' } }, 'c4').map((n) => n.id))), ['c2']);
});


test('the boundary choices are optional enums that match the server', () => {
  const R = load();
  const values = (list) => JSON.parse(JSON.stringify(list.map(([value]) => value)));
  assert.deepEqual(values(R.BACKGROUNDS), ['', 'unknown', 'engineering', 'ai_researcher', 'other']);
  assert.deepEqual(values(R.DEPTHS), ['', 'overview', 'read_papers', 'implement']);
  const html = R.boundaryHTML('x');
  assert.match(html, /id="x-background"/);
  assert.match(html, /id="x-depth"/);
  assert.equal((html.match(/<option value=""/g) || []).length, 2);   // each can be skipped
});

test('reading the boundary gives only the chosen values, or nothing when both are skipped', () => {
  const R = load();
  const root = (bg, depth) => ({ querySelector: (sel) => ({ value: sel.includes('background') ? bg : depth }) });
  assert.equal(R.readBoundary(root('', '')), undefined);
  assert.deepEqual(JSON.parse(JSON.stringify(R.readBoundary(root('unknown', '')))), { background: 'unknown' });
  assert.deepEqual(JSON.parse(JSON.stringify(R.readBoundary(root('engineering', 'implement')))), { background: 'engineering', depth: 'implement' });
  assert.equal(R.readBoundary(root('wizard', 'forever')), undefined);   // anything the server would refuse is never sent
});

test('a concept panel says what kind of unit it is and why a basic one is there', () => {
  const R = load();
  const graph = { concepts: [{ id: 'c1', name: 'Linear algebra', terms: ['linear algebra'], hint: 1, type: 'foundation', why: 'matrices underlie every model', state: 'active' }], prereqs: [], targets: ['c1'] };
  const text = R.typeText(graph.concepts[0]);
  assert.match(text, /基础/);
  assert.match(text, /matrices underlie every model/);
  assert.equal(R.typeText({ id: 'c2', name: 'x' }), '');
});


const growth = () => ({ id: 'g-0123456789', name: 'strain relaxation', terms: ['strain relaxation'], status: 'ready', positive: 2, paper_count: 4, sources: 2, overlap: 0.15,
  papers: [{ key: 's1', title: 'Strain <b>relaxation</b>' }, { key: 's2', title: 'Second' }], parent: { id: 'c2', name: 'Epitaxy' }, prereqs: [{ id: 'c1', name: 'Crystal basics', support: 0.4 }] });

test('a proposed direction shows its evidence as counts and titles, all escaped', () => {
  const R = load();
  const html = R.candidateHTML(growth());
  assert.match(html, /strain relaxation/);
  assert.match(html, /4 篇论文/);
  assert.match(html, /你明确点过 2 篇/);
  assert.match(html, /2 个来源/);
  assert.match(html, /重叠 15%/);
  assert.match(html, /建议放在：.*Epitaxy/);
  assert.match(html, /建议的前置：.*Crystal basics/);
  assert.ok(!html.includes('<b>relaxation</b>') && html.includes('&lt;b&gt;relaxation&lt;/b&gt;'));
});

test('a proposal has exactly two buttons, each carrying the id, and they are off while edits are unsaved', () => {
  const R = load();
  const html = R.candidateHTML(growth());
  assert.equal((html.match(/data-growth="accept"/g) || []).length, 1);
  assert.equal((html.match(/data-growth="reject"/g) || []).length, 1);
  assert.equal((html.match(/data-id="g-0123456789"/g) || []).length, 2);
  assert.ok(!/disabled/.test(html));
  assert.equal((R.candidateHTML(growth(), { locked: true }).match(/disabled/g) || []).length, 2);
});

test('a proposal without a parent or prerequisites says nothing about them', () => {
  const R = load();
  const bare = { ...growth(), parent: null, prereqs: [] };
  const html = R.candidateHTML(bare);
  assert.ok(!/建议放在|建议的前置/.test(html));
});

test('the list says how many are only being watched and never calls silence a reason', () => {
  const R = load();
  assert.match(R.growthNote({ candidates: [], watching: 2 }), /还有 2 个方向证据不够/);
  assert.match(R.growthNote({ candidates: [], watching: 0 }), /没有新的建议/);
  assert.equal(R.growthNote({ candidates: [growth()], watching: 0 }), '');
  assert.doesNotMatch(R.growthNote({ candidates: [], watching: 0 }), /落后|没读|不喜欢/);
});
