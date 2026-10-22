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

test('goal summary distinguishes completion, learning and structural review', () => {
  const R = load();
  for (const [status, text] of [['completed', '已完成'], ['learning', '学习中'], ['needs_review', '需检查']]) {
    const line = R.summaryText({goal_status: status, goal_done: 3, goal_total: 3, done: 3, total: 9});
    assert.equal(line, `${text} · 3/3`);
    assert.doesNotMatch(line, /3\/9/);
  }
});

test('watching does not claim mastery and new developments require satisfaction', () => {
  const R = load();
  assert.match(R.watchHTML(true, false), /data-route-watch checked/);
  assert.doesNotMatch(R.watchHTML(true, false), /不改变掌握状态/);   // the explanation is gone; only the checkbox remains
  assert.doesNotMatch(R.watchHTML(false, true), /开启后可推荐这个方向的新进展/);
  assert.match(R.watchHTML(false, true), /持续关注/);
  assert.doesNotMatch(R.watchHTML(false, true), /data-route-watch checked/);
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
  assert.equal(R.shapeText(R.shape(chain)), '');   // the shape sentence is no longer shown
  assert.equal(R.shapeText(R.shape(g)), '');
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
  assert.match(html, /先读懂：/);
  assert.match(html, /之后可读：/);
  assert.match(html, /need[^"]* done/);
  const entry = R.detailHTML(g, g.concepts[0], {});
  assert.doesNotMatch(entry, /先读懂/);   // an entry has no prerequisites, so it shows no line about them
  assert.doesNotMatch(html + entry, /落后|拖延|逾期|未读|欠/);
  const locked = R.detailHTML(g, g.concepts[3], { progress: { c1: { status: 'satisfied' }, c2: { status: 'unlocked' }, c3: { status: 'unlocked' }, c4: { status: 'locked' } } });
  assert.doesNotMatch(locked, /只在等|其他分支的进度不影响它/);
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

test('deleting and adding never reuses watched identity, including a reloaded draft', () => {
  const R = load(), original = graph();
  const removed = R.removeConcept(original, 'c4');
  const next = R.addConcept(removed, { name: 'Different task', terms: ['different task'], hint: 3 }, ['c2']);
  const id = next.concepts.at(-1).id;
  assert.notEqual(id, 'c4');
  assert.ok(!original.concepts.some(c => c.id === id));
  const reloaded = load().addConcept(JSON.parse(JSON.stringify(removed)), { name: 'Different task', terms: ['different task'], hint: 3 }, ['c2']);
  assert.notEqual(reloaded.concepts.at(-1).id, id);
});

test('adding a concept picks a fresh id and refuses a cycle or full map and warns on harder prerequisites', () => {
  const R = load();
  const g = R.addConcept(graph(), { name: 'Strain', terms: ['strain'], hint: 3 }, ['c2']);
  assert.equal(g.concepts.length, 5);
  assert.match(g.concepts[4].id, /^r-/);
  assert.ok(!graph().concepts.some(c => c.id === g.concepts[4].id));
  assert.equal(R.check(R.addConcept(graph(), { name: 'Loop', terms: ['loop'], hint: 1 }, ['c4'])).warnings.length, 1);
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
  assert.equal(R.check(bad).ok, true);
  assert.equal(R.check(bad).warnings.length, 1);
  assert.equal(R.check({...graph(), targets: []}).ok, false);
  assert.equal(R.check(R.setTarget({...graph(), targets: []}, 'c4', true)).ok, true);
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
  assert.equal(added.prereqs.filter(e => e.to === added.concepts.at(-1).id).length, 1);
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
  for (const text of [...Object.values(R.STATUS), R.LOW_INTEREST_TITLE, R.LOCKED_TITLE]) assert.doesNotMatch(text, /落后|欠|不喜欢|未完成|逾期|错过|没读|讨厌/);
  assert.equal(R.LOW_INTEREST_TITLE, '暂时排在后面');
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
  assert.equal(R.summaryText({ done: 2, total: 5, exploration_share: 0.26 }), '已读懂 2/5');
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

test('the low-interest tooltip is three words and carries no mechanism note', () => {
  const R = load();
  assert.equal(R.LOW_INTEREST_TITLE, '暂时排在后面');
  assert.doesNotMatch(R.LOW_INTEREST_TITLE, /不感兴趣|不等于不喜欢|恢复/);
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

test('a model draft never replaces an introduction the person wrote; a model-written one is replaced', () => {
  const R = load();
  const saved = { concepts: [{ ...concept('c1', 'Epitaxy', 1), intro: 'Mine.', intro_by: 'user' }, { ...concept('c2', 'Doping', 2), intro: 'Old AI line.', intro_by: 'ai' }],
                  prereqs: [], targets: [] };
  const draft = { concepts: [{ ...concept('c1', 'Doping', 1), intro: 'New AI line.', intro_by: 'ai' }, { ...concept('c2', 'epitaxy', 1), intro: 'AI says this.', intro_by: 'ai' }],
                  prereqs: [], targets: [] };
  const out = R.reuseIds(draft, saved);
  const byName = Object.fromEntries(out.concepts.map((c) => [c.name, c]));
  assert.equal(byName.epitaxy.intro, 'Mine.');
  assert.equal(byName.epitaxy.intro_by, 'user');
  assert.equal(byName.Doping.intro, 'New AI line.');
  assert.equal(byName.Doping.intro_by, 'ai');
  assert.equal(draft.concepts[1].intro, 'AI says this.');   // the input is not touched
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


const gates = (o = {}) => ({ papers: { have: 4, need: 3, ok: true }, positive: { have: 2, need: 2, ok: true }, sources: { have: 2, need: 2, ok: true }, strength: { have: 0.29, need: 0.25, ok: true }, ...o });
const growth = (o = {}) => ({ id: 'g-0123456789', name: 'strain relaxation', terms: ['strain relaxation'], status: 'ready', positive: 2, paper_count: 4, sources: 2, source_names: ['journal-a', 'journal-b'], overlap: 0.15,
  progress: 1, gates: gates(), missing: [], parts: [{ key: 'S', label: '证据量', hint: '你明确点过的论文越多越高', value: 0.49 }, { key: 'C', label: '集中度', hint: '这些论文的文字越接近越高', value: 0.6 }],
  papers: [{ key: 's1', title: 'Strain <b>relaxation</b>', source: 'journal-a', explicit: true }, { key: 's2', title: 'Second', source: 'journal-b', explicit: false }],
  parent: { id: 'c2', name: 'Epitaxy' }, prereqs: [{ id: 'c1', name: 'Crystal basics', support: 0.4 }],
  topology: { needs: [{ id: 'c1', name: 'Crystal basics', support: 0.4 }], parent: { id: 'c2', name: 'Epitaxy' }, note: '加入后：Crystal basics → 「strain relaxation」；它比「Epitaxy」更细' }, ...o });
const forming = () => growth({ status: 'watch', progress: 0.62, gates: gates({ papers: { have: 2, need: 3, ok: false }, sources: { have: 1, need: 2, ok: false }, strength: { have: 0.12, need: 0.25, ok: false } }),
  missing: ['还差 1 篇属于这个方向的论文', '还差 1 个不同来源'], prereqs: [], parent: null, topology: { needs: [], parent: null, note: '加入后「strain relaxation」会是一个新的入口（没有前置）' } });

test('a direction row shows how far it is and what it has, all escaped, and is only a row to click', () => {
  const R = load();
  const html = R.candidateRowHTML(forming(), null);
  assert.match(html, /strain relaxation/);
  assert.doesNotMatch(html.replace(/<[^>]*>/g, ''), /%/);           // a score is never shown as a number (bar widths are not text)
  assert.doesNotMatch(html.replace(/<[^>]*>/g, ''), /论文 2\/3|你点过 2\/2|来源 1\/2/);   // the gate counts are not on the row
  assert.match(html, /证据较少/);
  assert.match(html, /data-growth="select"/);
  assert.doesNotMatch(html, /data-growth="accept"|data-growth="reject"/);       // adding and turning down live in the panel you open
  const ready = R.candidateRowHTML(growth({ name: 'x <b>y</b>' }), null);
  assert.match(ready, /可加入/);
  assert.ok(!ready.includes('<b>y</b>') && ready.includes('&lt;b&gt;y&lt;/b&gt;'));
});

test('the row of the direction you opened is marked, the others are not', () => {
  const R = load();
  assert.match(R.candidateRowHTML(growth(), 'g-0123456789'), /is-selected[^>]*aria-pressed="true"/);
  assert.match(R.candidateRowHTML(growth(), 'other'), /aria-pressed="false"/);
});

test('only a ready direction can be added; every one can be turned down; edits that are unsaved lock both', () => {
  const R = load();
  const button = (html, kind) => (html.match(new RegExp(`<button[^>]*data-growth="${kind}"[^>]*>`)) || [''])[0];
  assert.ok(!/disabled/.test(button(R.ghostDetailHTML(growth()), 'accept')));
  assert.ok(/disabled/.test(button(R.ghostDetailHTML(forming()), 'accept')));
  assert.ok(!/disabled/.test(button(R.ghostDetailHTML(forming()), 'reject')));
  const locked = R.ghostDetailHTML(growth(), { locked: true });
  assert.ok(/disabled/.test(button(locked, 'accept')) && /disabled/.test(button(locked, 'reject')));
});

test('the panel no longer carries the placement note', () => {
  const R = load();
  assert.doesNotMatch(R.ghostDetailHTML(growth()), /加入后：Crystal basics/);   // the placement note is no longer shown
  assert.doesNotMatch(R.ghostDetailHTML(forming()), /新的入口/);
});

test('the panel shows the model\'s introduction and barrier, marked as its opinion, escaped', () => {
  const R = load();
  const html = R.ghostDetailHTML(growth({ intro: '位错滑移释放<i>应力</i>。', barrier: '要先懂外延。' }));
  assert.match(html, /位错滑移释放/);
  assert.match(html, /门槛：/);
  assert.match(html, /要先懂外延/);
  assert.match(html, /AI 判断/);
  assert.ok(!html.includes('<i>应力</i>'));
  assert.doesNotMatch(R.ghostDetailHTML(growth()), /AI 判断/);                 // no brief yet: nothing to attribute
});

test('the waiting exploration papers are listed with the one button that asks the model, and it can be off', () => {
  const R = load();
  assert.equal(R.pendingHTML({ pending: [], judges_left: 5 }, {}), '');
  const html = R.pendingHTML({ pending: [{ key: 'a', title: 'T <b>1</b>' }, { key: 'b', title: 'T2' }, { key: 'c', title: 'T3' }, { key: 'd', title: 'T4' }], judges_left: 7 }, {});
  assert.match(html, /<b>4<\/b>/);
  assert.match(html, /data-growth="judge"/);
  assert.ok(!html.includes('<b>1</b>') && html.includes('T &lt;b&gt;1&lt;/b&gt;'));
  assert.equal((html.match(/<li/g) || []).length, 3);                          // the first three are only a preview of the queue
  assert.doesNotMatch(html, /今天还能判断 7 次|每批最多 3 篇|整次只计 1 次判断机会/);
  assert.match(html, />判断全部</);
  assert.match(html, /title="调用 AI，只发送论文标题、摘要节选和学习图概念"/);
  assert.match(R.pendingHTML({ pending: [{ key: 'a', title: 'T' }], judges_left: 0 }, {}), /data-growth="judge" disabled/);
  assert.match(R.pendingHTML({ pending: [{ key: 'a', title: 'T' }], judges_left: 3 }, { busy: true }), /data-growth="judge" disabled/);
  assert.match(R.pendingHTML({ pending: [{ key: 'a', title: 'T' }], judges_left: 3 }, { busy: true }), />正在判断…</);
});

test('queue progress uses backend counts and distinguishes partial, complete and legacy responses', () => {
 const R=load(), out={ok:true,requested:20,processed:20,pending:0,complete:true,model_calls:7,judges_left:9};
 const complete=R.judgeProgress(out);assert.equal(complete.complete,true);
 assert.equal(complete.message,'判断完毕 · 20/20 篇');
 const partial=R.judgeProgress({...out,processed:9,pending:11,complete:false,reason:'预算不足'});
 assert.equal(partial.complete,false);assert.equal(partial.message,'判断已停止 · 9/20 篇 · 还有 11 篇待判断 · 预算不足');
 const newPending=R.judgeProgress({...out,pending:2});
 assert.equal(newPending.complete,true);assert.equal(newPending.message,'判断完毕 · 20/20 篇 · 还有 2 篇待判断');
 assert.equal(complete.warning,false);assert.equal(partial.warning,true);
 const uncertain=R.judgeProgress({...out,reason_code:'network',reason:'Request or billing status is unknown'});
 assert.equal(uncertain.complete,true);assert.equal(uncertain.warning,true);
 assert.match(uncertain.message,/Request or billing status is unknown/);
 const noReason=R.judgeProgress({...out,reason_code:'network'});
 assert.equal(noReason.warning,true);assert.match(noReason.message,/调用状态需确认/);
 assert.equal(R.judgeProgress({ok:true,results:[],judges_left:9}),null);
});

test('what the model said is put in plain words, one phrase per group, and never as a fact about the reader', () => {
  const R = load();
  const text = R.judgeSummary([{ verdict: 'new', name: '应变弛豫' }, { verdict: 'join', name: '应变弛豫' }, { verdict: 'covered', nearest: 'Epitaxy' }, { verdict: 'covered' }, { verdict: 'unclear' }]);
  assert.equal(text, '「应变弛豫」新分支；并入「应变弛豫」；「Epitaxy」已覆盖；已有概念已覆盖；AI 看不出来');
  assert.equal(R.judgeSummary([{ verdict: 'declined', name: '应变弛豫' }]), '「应变弛豫」已不再提示');
  assert.equal(R.judgeSummary([{ verdict: 'full' }]), '潜在方向已满');
  assert.match(R.judgeSummary([{ verdict: 'unusable' }]), /回复不完整.*可再试/);
  assert.equal(R.judgeSummary([]), '');
});

test('the detail of a direction lists what is missing and the papers with the ones you marked, without gate or evidence-part tables', () => {
  const R = load();
  const html = R.ghostDetailHTML(forming());
  assert.equal((html.match(/class="gate[ "]/g) || []).length, 0);   // the per-gate rows are not on the surface any more
  assert.match(html, /还差 1 个不同来源/);
  assert.match(html, /还差 1 篇属于这个方向的论文/);
  assert.doesNotMatch(html, /证据量|证据是怎么来的|growth-parts/);
  assert.doesNotMatch(html.replace(/<[^>]*>/g, ''), /0\.12|0\.25|\d%/);   // never a decimal or a percentage as text
  assert.match(html, /你点过/);                    // the paper marker
  assert.match(html, /journal-a/);
  assert.doesNotMatch(html, /加入后/);
  assert.ok(!html.includes('<b>relaxation</b>'));
});

test('the list says what to do when nothing is on file and never calls silence a reason', () => {
  const R = load();
  assert.equal(R.growthNote({ candidates: [] }), '还没有潜在方向');
  assert.equal(R.growthNote({ candidates: [growth(), forming()] }), '');
  assert.equal(R.growthNote({ candidates: [], pending: [{ key: 'a', title: 'T' }] }), '');   // there is something to judge: the pending block says so
  assert.doesNotMatch(R.growthNote({ candidates: [] }), /落后|没读|不喜欢/);
});

test('the display graph has a ghost node per direction, with dashed arrows from what it would need, and leaves the real graph alone', () => {
  const R = load();
  const graph = { concepts: [{ id: 'c1', name: 'Crystal basics', terms: ['x'], hint: 1, state: 'active' }, { id: 'c2', name: 'Epitaxy', terms: ['y'], hint: 2, state: 'active' }],
    prereqs: [{ from: 'c1', to: 'c2', state: 'active' }], targets: ['c2'] };
  const before = JSON.stringify(graph);
  const shown = R.ghostGraph(graph, [growth(), forming()]);
  assert.equal(JSON.stringify(graph), before);
  assert.equal(shown.concepts.length, 4);
  const ghosts = shown.concepts.filter((c) => c.ghost);
  assert.deepEqual(JSON.parse(JSON.stringify(ghosts.map((c) => c.id))), ['ghost:g-0123456789', 'ghost:g-0123456789']);   // the two samples share an id here; real ones differ
  assert.ok(shown.prereqs.some((e) => e.from === 'c1' && e.to === 'ghost:g-0123456789' && e.ghost));
  assert.equal(shown.prereqs.filter((e) => e.ghost).length, 1);   // the forming one has no prerequisite: it is an entry
  assert.deepEqual(JSON.parse(JSON.stringify(shown.targets)), ['c2']);
});

test('a prerequisite the map no longer has is not drawn, and a ghost never reuses a real id', () => {
  const R = load();
  const graph = { concepts: [{ id: 'c9', name: 'Other', terms: ['y'], hint: 2, state: 'active' }], prereqs: [], targets: ['c9'] };
  const shown = R.ghostGraph(graph, [growth()]);
  assert.equal(shown.prereqs.length, 0);
  assert.ok(shown.concepts.every((c) => c.id === 'c9' || c.id.startsWith('ghost:')));
});

test('the border is a track plus a filled part of the same outline, and a full solid line only when it can be added', () => {
  const R = load();
  const part = R.ringSVG(0.62, false, 176, 72);
  assert.match(part, /<svg/);
  assert.equal((part.match(/<rect/g) || []).length, 2);
  assert.match(part, /pathLength="100"/);
  assert.match(part, /stroke-dasharray="62 38"/);
  const full = R.ringSVG(1, true, 176, 72);
  assert.match(full, /class="rg-ring is-ready"/);
  assert.doesNotMatch(full, /stroke-dasharray="[0-9. ]+ [0-9. ]+" class="rg-ring-fill"/);
  const empty = R.ringSVG(NaN, false, 176, 72);                                  // no number: an empty ring, never NaN, and no dot
  assert.doesNotMatch(empty, /NaN|rg-ring-fill/);
  assert.equal((empty.match(/<rect/g) || []).length, 1);
  assert.match(R.ringSVG(5, false, 176, 72), /stroke-dasharray="97 3"/);          // not ready never shows as full
});

test('the status of a ghost node says it is a direction in the making and how far', () => {
  const R = load();
  assert.deepEqual(JSON.parse(JSON.stringify(R.ghostStatus(forming()))), { key: 'ghost', label: '潜在方向 · 证据中', title: R.ghostStatus(forming()).title });
  assert.match(R.ghostStatus(growth()).label, /可以加入/);
  assert.match(R.ghostStatus(forming()).title, /还差 1 篇属于这个方向的论文/);
});

// ---- what a concept is: intro, role, difficulty, the project's papers and a few public ones
const mapOf = () => ({ concepts: [
  { id: 'c1', name: 'Crystal basics', terms: ['crystal growth'], hint: 1, state: 'active', intro: '晶体怎样长出来。', intro_by: 'ai' },
  { id: 'c2', name: 'Epitaxy', terms: ['epitaxy'], hint: 2, state: 'active' },
  { id: 'c3', name: 'MBE', terms: ['mbe'], hint: 3, state: 'active', intro: 'My own words <b>here</b>.', intro_by: 'user' },
  { id: 'c4', name: 'Side branch', terms: ['side'], hint: 2, state: 'active', side: true }],
  prereqs: [{ from: 'c1', to: 'c2', state: 'active' }, { from: 'c2', to: 'c3', state: 'active' }], targets: ['c3'] });

test('every concept has a role and a difficulty in words', () => {
  const R = load(), g = mapOf();
  const role = (id) => R.roleOf(g, g.concepts.find((c) => c.id === id));
  assert.deepEqual(['c1', 'c2', 'c3', 'c4'].map(role), ['entry', 'middle', 'target', 'side']);
  assert.match(R.ROLE_TEXT.entry, /入口/);
  assert.deepEqual([1, 2, 3, 4].map((h) => R.HINT_TEXT[h]), ['入门', '基础', '进阶', '前沿']);
});

test('the detail says what the concept is and marks an AI-written intro, without role or difficulty lines', () => {
  const R = load(), g = mapOf();
  const ai = R.detailHTML(g, g.concepts[0], {});
  assert.match(ai, /晶体怎样长出来。/);
  assert.match(ai, /AI 写的/);
  assert.doesNotMatch(ai, /角色：|难度 \d/);   // role and difficulty are no longer written out in the detail
  const mine = R.detailHTML(g, g.concepts[2], {});
  assert.doesNotMatch(mine, /你写的|AI 写的/);   // only an AI-written intro is marked; the reader's own is not
  assert.ok(!mine.includes('<b>here</b>') && mine.includes('&lt;b&gt;here&lt;/b&gt;'));
});

test('a concept without an intro shows no intro text and no author badge', () => {
  const R = load(), g = mapOf();
  const html = R.detailHTML(g, g.concepts[1], {});
  assert.doesNotMatch(html, /还没有简介|concept-intro/);
  assert.doesNotMatch(html, /AI 写的|你写的/);
  assert.match(html, /data-concept-papers/);      // where the project's own papers go
  assert.match(html, /data-concept-examples/);    // where the public ones go
});

test('the papers of the project that fit a concept are listed with the matched words and only what the reader did', () => {
  const R = load();
  const html = R.matchedPapersHTML({ papers: [
    { key: 'a', title: 'Epitaxial <i>layers</i>', terms: ['epitaxy', 'epitaxial'], feedback: 'useful', familiarity: 'understood' },
    { key: 'b', title: 'Plain', terms: ['epitaxy'], feedback: null, familiarity: null }], total: 7 });
  assert.doesNotMatch(html, /你的项目里有 7 篇用到了它的检索词/);
  assert.match(html, /epitaxy · epitaxial/);
  assert.match(html, /你点过有用/);
  assert.match(html, /你点过已读懂/);
  assert.ok(!html.includes('<i>layers</i>') && html.includes('&lt;i&gt;layers&lt;/i&gt;'));
  assert.match(html, /另有 5 篇/);
  assert.equal((html.match(/你点过/g) || []).length, 2);   // the paper nobody marked says nothing about the reader
});

test('no matching paper is said plainly', () => {
  const R = load();
  assert.match(R.matchedPapersHTML({ papers: [], total: 0 }), /还没有相关论文/);
  assert.doesNotMatch(R.matchedPapersHTML({ papers: [], total: 0 }), /落后|没读|不喜欢/);
});

test('public examples show title, year and a snippet, and an outage is a sentence, not an error', () => {
  const R = load();
  const html = R.examplesHTML({ ok: true, examples: [{ title: 'Paper <b>x</b>', year: '2024', source: 'Nature', snippet: 'We show <script>' }] });
  assert.match(html, /2024/);
  assert.ok(!html.includes('<b>x</b>') && !html.includes('<script>'));
  assert.match(R.examplesHTML({ ok: true, examples: [], reason_code: 'none' }), /没有找到/);
  assert.match(R.examplesHTML({ ok: false, examples: [], reason_code: 'unavailable' }), /暂时连不上/);
  assert.match(R.examplesHTML({ ok: true, examples: [], reason_code: 'no_terms' }), /没有检索词/);
});

test('setting an intro marks who wrote it, keeps the author when nothing changed, and clearing removes both', () => {
  const R = load(), g = mapOf();
  const ai = R.setIntro(g, 'c2', '这是 AI 的句子', 'ai');
  assert.deepEqual(JSON.parse(JSON.stringify(ai.concepts[1])), { ...g.concepts[1], intro: '这是 AI 的句子', intro_by: 'ai' });
  const same = R.setIntro(ai, 'c2', '这是 AI 的句子', 'user');
  assert.equal(same.concepts[1].intro_by, 'ai');                         // the person saved without touching it: still the model's
  const edited = R.setIntro(ai, 'c2', '我改了一下', 'user');
  assert.equal(edited.concepts[1].intro_by, 'user');
  const cleared = R.setIntro(edited, 'c2', '   ', 'user');
  assert.ok(!('intro' in cleared.concepts[1]) && !('intro_by' in cleared.concepts[1]));
  assert.equal(R.setIntro(g, 'c2', 'x'.repeat(300), 'user').concepts[1].intro.length, 140);
  assert.equal(JSON.stringify(g), JSON.stringify(mapOf()));               // the original is left alone
});

test('a new concept can carry an intro and keeps it through a rename and a re-draft', () => {
  const R = load(), g = mapOf();
  const grown = R.addConcept(g, { name: 'Dreamer', terms: ['dreamer'], hint: 3, intro: 'A method.', intro_by: 'user' }, ['c2']);
  assert.equal(grown.concepts[grown.concepts.length - 1].intro, 'A method.');
  const renamed = R.rename(grown, 'c2', 'Epitaxy basics', ['epitaxy']);
  assert.equal(renamed.concepts[1].name, 'Epitaxy basics');
  const reused = R.reuseIds(grown, g);
  assert.equal(reused.concepts.find((c) => c.name === 'Dreamer').intro, 'A method.');
});


test('current one-paper proposal can be confirmed while stale strong proposal cannot', () => {
  const R = load();
  const weak = {...forming(), can_accept: true, stale: false, proposal_type: 'new_task'};
  const html = R.ghostDetailHTML(weak);
  assert.match(html, /新任务/);
  assert.doesNotMatch(html, /仅供参考/);
  assert.doesNotMatch(html.match(/<button[^>]+data-growth="accept"[^>]*>/)[0], /disabled/);
  const stale = R.ghostDetailHTML(growth({can_accept: false, stale: true}));
  assert.match(stale.match(/<button[^>]+data-growth="accept"[^>]*>/)[0], /disabled/);
  assert.doesNotMatch(stale, /不会自动调用 AI/);
  assert.match(R.ghostStatus(growth({stale:true})).label, /已过期/);
});

test('missing prerequisite ghost points to dependent and cannot change stored map', () => {
  const R = load(), graph = mapOf(), before = JSON.stringify(graph);
  const ghost = R.ghostGraph(graph, [growth({proposal_type:'missing_prerequisite',
    topology:{needs:[],required_by:[{id:'c2',name:'Epitaxy'}]}})]);
  assert.ok(ghost.prereqs.some(e => e.from === 'ghost:g-0123456789' && e.to === 'c2'));
  assert.equal(JSON.stringify(graph), before);
});

test('judgment history is not drawn on the page', () => {
  assert.equal(load().judgementsHTML({judgements:[{stale:true,verdict:'covered',titles:['<script>x</script>'],reason:'<b>source</b>'}]}), '');
});
