'use strict';
// The library as three panes (categories | paper list | selected paper), the PDF glyph and note mark in each row,
// and the graph that always draws every paper (folding is for the sidebar only).
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const STATIC = path.join(__dirname, '../app/static');
const cytoscape = require('../app/static/vendor/cytoscape/cytoscape.min.js');

function fixture(api = async () => { throw new Error('Unexpected API call'); }) {
  const storage = new Map();
  const context = vm.createContext({
    module: { exports: {} },
    window: { PDH: { api, toast() {}, md: text => `<div class="md">${String(text).replace(/</g, '&lt;')}</div>`, state: { currentProject: null, summaries: {} } },
      PDHPaperContext: require('../app/static/paper-context.js'), addEventListener() {} },
    document: { activeElement: null },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    crypto: { randomUUID: () => 'client-1' }, setTimeout, clearTimeout, URL,
    ResizeObserver: class { observe() {} disconnect() {} },
  });
  vm.runInContext(fs.readFileSync(path.join(STATIC, 'organization.js'), 'utf8'), context);
  const ui = context.module.exports;
  ui.setReader = reader => { context.window.PDH.openReader = reader; };
  ui.setSummaries = summaries => { context.window.PDH.state.summaries = summaries; };
  ui.setCytoscape = factory => { context.window.cytoscape = factory; };
  ui.setBeta = on => { context.window.PAGETIDE_ROUTE_BETA = on; };   // the learning-map setting (window.PAGETIDE_ROUTE_BETA)
  return ui;
}

// A page made of plain stand-ins: whatever is drawn into a named part is kept for the test to read.
function page(ui, names = []) {
  const parts = {};
  const part = name => parts[name] ||= { innerHTML: '', textContent: '', hidden: false, title: '', indeterminate: false,
    classes: new Map(), classList: { toggle(c, on) { parts[name].classes.set(c, on); }, add() {}, remove() {}, contains: () => false }, setAttribute() {} };
  const known = new Set(['.org-detail', '.org-list', '.org-bulk', '[data-select-all]', '[data-status]', '.org-sidebar', ...names]);
  ui.S.rows = [];
  ui.S.root = { querySelector: selector => known.has(selector) ? part(selector) : null,
    querySelectorAll: selector => selector === '.org-paper' ? ui.S.rows : [],
    classList: { contains: () => false, add() {}, toggle() {} } };
  return part;
}
const text = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ');
const row = (ui, key) => {   // a stand-in list row that remembers its marks and focus
  const r = { dataset: { key }, attrs: {}, classes: new Map(), focused: 0,
    classList: { toggle: (c, on) => r.classes.set(c, on) }, setAttribute: (k, v) => { r.attrs[k] = v; }, focus() { r.focused++; }, scrollIntoView() {},
    closest: selector => selector === '.org-paper' ? r : null };
  return r;
};
const base = (extra = {}) => ({
  directions: [{ id: 'd1', name: 'Models', rank: 0 }], projects: [], collapsed: [], positions: {}, revision: 3, drafts: [],
  items: [
    { key: 'local', title: 'Archived paper', published: '2024-05-01', directions: ['d1'], pdf: 'local', note: 'My own note', note_version: 2, abstract: 'An abstract about agents.', source: 'arXiv' },
    { key: 'direct', title: 'Downloadable paper', published: '2023-01-01', directions: [], pdf: 'direct', note: '', note_version: 0 },
    { key: 'page', title: 'Web page only', published: '2022-01-01', directions: [], pdf: 'page', note: '', note_version: 0 },
    { key: 'none', title: 'No source', published: '2021-01-01', directions: [], pdf: 'none', note: '', note_version: 0 }],
  ...extra });

// ---- list rows
test('each row shows one PDF glyph for its state, a note mark only when a note exists, and no "有笔记" text', () => {
  const ui = fixture(); ui.accept(base());
  const part = page(ui); ui.renderList();
  const html = part('.org-list').innerHTML, rows = html.split('<article').slice(1);
  assert.equal(rows.length, 4);
  const byKey = key => rows.find(r => r.includes(`data-key="${key}"`));
  assert.match(byKey('local'), /class="org-pdf is-local"[^>]*aria-label="已下载 PDF"/);
  assert.match(byKey('direct'), /class="org-pdf is-direct"[^>]*aria-label="可下载 PDF"/);
  assert.match(byKey('page'), /class="org-pdf is-page"[^>]*aria-label="仅有网页"/);
  assert.match(byKey('none'), /class="org-pdf is-none"/);
  assert.doesNotMatch(byKey('none'), /aria-label="(已下载|可下载|仅有)/);
  assert.match(byKey('local'), /class="org-note-mark"[^>]*>✎</);
  for (const key of ['direct', 'page', 'none']) assert.doesNotMatch(byKey(key), /org-note-mark/);
  assert.doesNotMatch(text(html), /有笔记/);                          // the mark is a glyph; no words on the surface
  assert.match(byKey('local'), /2024/);                              // the year, nothing more of the date
  assert.doesNotMatch(text(byKey('local')), /2024-05-01/);
});

test('a row carries no category tags, project tags or detail button: those live in the right pane', () => {
  const ui = fixture(); ui.accept(base({ projects: [{ id: 'p', name: 'World' }] }));
  ui.S.snapshot.items[0].projects = ['p'];
  const part = page(ui); ui.renderList();
  const html = part('.org-list').innerHTML;
  assert.doesNotMatch(html, /org-tags|org-proj|data-action="detail"|>详情</);
  assert.match(html, /data-action="paper-membership"/);              // category editing and 已读懂 stay on the row
});

test('rows are a keyboard list: one tab stop on the selected row, the first row when nothing is selected', () => {
  const ui = fixture(); ui.accept(base());
  let part = page(ui); ui.renderList();
  const stops = html => html.split('<article').slice(1).map(r => /tabindex="0"/.test(r));
  assert.deepEqual(stops(part('.org-list').innerHTML), [true, false, false, false]);
  ui.S.key = 'page'; ui.renderList();
  const rows = part('.org-list').innerHTML.split('<article').slice(1);
  assert.deepEqual(rows.map(r => /tabindex="0"/.test(r)), rows.map(r => r.includes('data-key="page"')));   // the selected row, wherever the order puts it
  assert.match(part('.org-list').innerHTML, /role="listbox"|role="option"/);
});

// ---- selection fills the right pane
test('selecting a paper fills the pane: title, meta, the user\'s note first, then the folded abstract, the read button, and the AI summary marked as AI', async () => {
  const ui = fixture(); ui.accept(base());
  ui.setSummaries({ local: { one_liner: 'Agents learn a world model.', why_relevant: 'Matches your seeds', caution: '' } });
  ui.setReader(() => {});
  const part = page(ui);
  await ui.handle('select', { dataset: { key: 'local' } });
  assert.equal(ui.S.key, 'local');
  const pane = part('.org-detail'), html = pane.innerHTML;
  assert.equal(pane.classes.get('has-paper'), true);
  const at = s => { const i = html.indexOf(s); assert.ok(i >= 0, `missing ${s}`); return i; };
  const order = [at('Archived paper'), at('org-notes'), at('My own note'), at('org-abstract'), at('data-action="read"'), at('AI 速览')];
  assert.deepEqual([...order].sort((a, b) => a - b), order, 'title, note, abstract, read, AI in that order');
  assert.match(html, /<details class="org-abstract">/);              // folded until asked for
  assert.doesNotMatch(html, /<details class="org-abstract" open/);
  assert.match(html, /2024/); assert.match(html, /arXiv/);
  assert.match(html, /data-action="note-open"/);                     // an edit action, not an always-open textarea
  assert.doesNotMatch(html, /<textarea/);
  assert.match(html.slice(order[1], order[3]), /My own note/);
  assert.doesNotMatch(html.slice(order[1], order[3]), /Agents learn a world model|AI 速览/);   // AI text is never mixed into the note
  assert.match(html.slice(order[5] - 40), /class="org-ai"/);
  assert.doesNotMatch(html.slice(0, order[5]), /Agents learn a world model/);
});

test('the pane shows category chips and no counts, diagnostics or reason codes', async () => {
  const ui = fixture(); ui.accept(base());
  const part = page(ui);
  await ui.handle('select', { dataset: { key: 'local' } });
  const html = part('.org-detail').innerHTML;
  assert.match(html, /class="org-detail-badge" data-action="filter" data-id="d1"/);
  assert.doesNotMatch(text(html), /\d+ 篇|个类别|reason|DOI|arXiv:/);
});

test('with no note the pane offers a quiet place to write; nothing selected leaves the pane empty', async () => {
  const ui = fixture(); ui.accept(base());
  const part = page(ui);
  ui.renderDetail();
  assert.equal(part('.org-detail').innerHTML, '');                   // whitespace
  assert.equal(part('.org-detail').classes.get('has-paper'), false);
  await ui.handle('select', { dataset: { key: 'direct' } });
  assert.match(part('.org-detail').innerHTML, /data-action="note-open"/);
  assert.doesNotMatch(part('.org-detail').innerHTML, /<textarea/);
});

test('a single click on a row selects it and moves the highlight; the row checkbox does not', async () => {
  const ui = fixture(); ui.accept(base());
  const part = page(ui); ui.S.rows = [row(ui, 'local'), row(ui, 'direct')];
  const rowEl = ui.S.rows[1];
  const click = (target, action) => ({ target: Object.assign(target, { closest: s => s === '[data-action]' ? { dataset: { action, key: 'direct' }, disabled: false } : /input|select|textarea|a\b/.test(s) && target.isInput ? target : null }) });
  ui.S.root.querySelectorAll = selector => selector === '.org-paper' ? ui.S.rows : [];
  ui.S.root.onclick = null;
  await ui.onRootClick(click({ isInput: true }, 'select'));
  assert.equal(ui.S.key, null);                                      // a checkbox click is not a selection
  await ui.onRootClick(click({}, 'select'));
  assert.equal(ui.S.key, 'direct');
  assert.equal(rowEl.classes.get('is-active'), true);
  assert.equal(ui.S.rows[0].classes.get('is-active'), false);
  assert.equal(rowEl.attrs['aria-selected'], 'true');
  assert.match(part('.org-detail').innerHTML, /Downloadable paper/);
});

// ---- opening the reader
test('double-click, Enter on a row, and the read button open the reader; a click on a control inside the row does not', async () => {
  const ui = fixture(); ui.accept(base());
  const opened = []; ui.setReader((...args) => opened.push(args));
  const part = page(ui);
  const r = row(ui, 'local'); ui.S.rows = [r];
  await ui.onListDblClick({ target: r });
  assert.deepEqual(opened.splice(0), [['local', 'Archived paper', null]]);
  await ui.onListDblClick({ target: { closest: s => s === '.org-paper' ? r : /input|button/.test(s) ? {} : null } });
  assert.equal(opened.length, 0);
  let prevented = 0;
  await ui.onListKey({ key: 'Enter', target: r, preventDefault: () => prevented++ });
  assert.deepEqual(opened.splice(0), [['local', 'Archived paper', null]]);
  assert.equal(prevented, 1);
  assert.equal(ui.S.key, 'local');                                   // Enter also selects, so the pane follows
  const inner = { closest: s => s === '.org-paper' ? r : null };      // Enter on a button inside the row keeps its own meaning
  await ui.onListKey({ key: 'Enter', target: inner, preventDefault: () => prevented++ });
  assert.equal(opened.length, 0); assert.equal(prevented, 1);
  await ui.handle('select', { dataset: { key: 'local' } });
  assert.match(part('.org-detail').innerHTML, /data-action="read" data-key="local"/);
  await ui.handle('read', { dataset: { key: 'local' } });
  assert.deepEqual(opened.splice(0), [['local', 'Archived paper', null]]);
});

test('Up and Down move the selection through the rows on screen and keep focus on the new row', async () => {
  const ui = fixture(); ui.accept(base());
  const part = page(ui); ui.S.rows = ['local', 'direct', 'page', 'none'].map(k => row(ui, k));
  ui.S.query = ''; ui.S.filter = '*';
  const press = (key, target) => { const event = { key, target, prevented: false, preventDefault() { this.prevented = true; } }; return ui.onListKey(event).then(() => event); };
  let event = await press('ArrowDown', ui.S.rows[0]);
  assert.equal(ui.S.key, 'direct'); assert.equal(event.prevented, true); assert.equal(ui.S.rows[1].focused, 1);
  await press('ArrowDown', ui.S.rows[1]);
  assert.equal(ui.S.key, 'page');
  await press('ArrowUp', ui.S.rows[2]);
  assert.equal(ui.S.key, 'direct');
  await press('ArrowUp', ui.S.rows[1]); await press('ArrowUp', ui.S.rows[0]);
  assert.equal(ui.S.key, 'local');                                   // stays on the first row
  await press('ArrowDown', ui.S.rows[3]);
  assert.equal(ui.S.key, 'none');                                    // and on the last
  assert.match(part('.org-detail').innerHTML, /No source/);
});

test('the read button is disabled with a quiet reason when the paper has no PDF source, and enabled otherwise', async () => {
  const ui = fixture(); ui.accept(base()); ui.setReader(() => {});
  const part = page(ui);
  await ui.handle('select', { dataset: { key: 'none' } });
  assert.match(part('.org-detail').innerHTML, /<button[^>]*data-action="read"[^>]*disabled[^>]*title="无 PDF 来源"|<button[^>]*title="无 PDF 来源"[^>]*data-action="read"[^>]*disabled/);
  for (const key of ['local', 'direct', 'page']) {
    await ui.handle('select', { dataset: { key } });
    assert.doesNotMatch(part('.org-detail').innerHTML.match(/<button[^>]*data-action="read"[^>]*>/)[0], /disabled/, key);
  }
});

// ---- the note: shown first, edited in place, same save/version/draft behaviour
test('the note edit action opens the existing editor in place and "完成" saves and returns to the rendered note', async () => {
  const calls = [];
  const ui = fixture(async (_, body) => {
    calls.push(body);
    if (body.action === 'draft-save') return { draft: { version: 1 }, revision: 3 };
    if (body.action === 'draft-clear') return { draft: { version: 2 }, revision: 3 };
    return base({ revision: 4, items: base().items.map(p => p.key === 'local' ? { ...p, note: 'Edited', note_version: 3 } : p) });
  });
  ui.accept(base()); const part = page(ui);
  await ui.handle('select', { dataset: { key: 'local' } });
  await ui.handle('note-open', { dataset: {} });
  const open = part('.org-detail').innerHTML;
  assert.match(open, /<textarea data-note-editor[^>]*>My own note<\/textarea>/);
  assert.match(open, /data-action="note-done"/); assert.match(open, /data-action="history"/); assert.match(open, /data-action="note-save"/);
  const draft = ui.draftFor(ui.S.snapshot.items[0]); draft.text = 'Edited'; draft.dirty = true;
  await ui.handle('note-done', { dataset: {} });
  assert.deepEqual(calls.filter(c => c.action === 'note').map(c => [c.key, c.text, c.version]), [['local', 'Edited', 2]]);
  const closed = part('.org-detail').innerHTML;
  assert.doesNotMatch(closed, /<textarea/);
  assert.match(closed, /Edited/);
});

test('a first note shows its mark in the row as soon as "完成" saves it, without a reload', async () => {
  const ui = fixture(async (_, body) => {
    if (body.action === 'draft-save') return { draft: { version: 1 }, revision: 3 };
    if (body.action === 'draft-clear') return { draft: { version: 2 }, revision: 3 };
    return base({ revision: 4, items: base().items.map(p => p.key === 'direct' ? { ...p, note: 'First note', note_version: 1 } : p) });
  });
  ui.accept(base()); const part = page(ui);
  await ui.handle('select', { dataset: { key: 'direct' } });
  await ui.handle('note-open', { dataset: {} });
  const draft = ui.draftFor(ui.S.snapshot.items.find(p => p.key === 'direct')); draft.text = 'First note'; draft.dirty = true;
  await ui.handle('note-done', { dataset: {} });
  const rowHtml = part('.org-list').innerHTML.split('</article>').find(r => r.includes('data-key="direct"'));
  assert.match(rowHtml, /org-note-mark/);
});

test('the selected row keeps its title readable: its actions show on hover or keyboard focus inside it, not because it is selected', () => {
  const css = fs.readFileSync(path.join(STATIC, 'organization.css'), 'utf8');
  assert.doesNotMatch(css, /\.org-paper\.is-active \.org-paper-actions\s*[,{][^}]*display:flex/);
  assert.match(css, /\.org-paper:hover \.org-paper-actions/);
});

test('"完成" keeps the editor open while the draft is unsaved or in conflict', async () => {
  const ui = fixture(async (_, body) => { if (body.action === 'draft-save') return { draft: { version: 1 }, revision: 3 }; throw new Error('Note version conflict'); });
  ui.accept(base()); const part = page(ui);
  await ui.handle('select', { dataset: { key: 'local' } });
  await ui.handle('note-open', { dataset: {} });
  const draft = ui.draftFor(ui.S.snapshot.items[0]); draft.text = 'Mine'; draft.dirty = true;
  await ui.handle('note-done', { dataset: {} });
  assert.match(part('.org-detail').innerHTML, /<textarea/);
  assert.equal(draft.dirty, true); assert.match(draft.error, /conflict/);
});

test('a recovered or unsaved draft always reopens in the editor, never hidden behind the rendered note', async () => {
  const ui = fixture(); ui.accept(base()); const part = page(ui);
  const draft = ui.draftFor(ui.S.snapshot.items[0]); draft.text = 'Left over'; draft.dirty = true;
  await ui.handle('select', { dataset: { key: 'local' } });
  assert.match(part('.org-detail').innerHTML, /<textarea data-note-editor[^>]*>Left over<\/textarea>/);
});

// ---- graph: folding is for the sidebar only, and "全部论文" always draws everything
const many = (count, categories) => base({ directions: categories.map((id, i) => ({ id, name: id, rank: i })), collapsed: categories,
  items: Array.from({ length: count }, (_, i) => ({ key: `k${i}`, title: `Paper ${i}`, published: '2024', directions: [categories[i % categories.length]], pdf: 'none', note: '', note_version: 0 })) });
function graphPage(ui) {
  const container = { innerHTML: '', title: '', setAttribute() {} };
  const parts = { '.org-graph': container };
  const quiet = () => ({ innerHTML: '', textContent: '', hidden: false, classList: { toggle() {}, add() {}, remove() {} } });
  for (const s of ['.org-graph-hint', '[data-focus-seg]', '[data-view-seg]', '.org-graph-wrap', '[data-route-unmatched]', '.org-graph-legend', '.org-detail', '.org-list', '.org-bulk', '.org-sidebar', '[data-status]']) parts[s] = quiet();
  ui.S.root = { querySelector: s => parts[s] || null, querySelectorAll: () => [], classList: { contains: () => false } };
  let drawn;
  ui.setCytoscape(options => { drawn = options.elements; return cytoscape({ ...options, container: undefined, headless: true }); });
  return { container, hint: parts['.org-graph-hint'], drawn: () => drawn };
}

test('全部论文 draws every paper even when all their categories are folded', () => {
  const ui = fixture(); ui.accept(many(8, ['a', 'b']));
  const g = graphPage(ui); ui.S.mode = 'graph'; ui.S.filter = '*'; ui.S.focus = 'all';
  ui.setMode();
  assert.equal(g.drawn().filter(e => !e.data.source).length, 8);
  assert.doesNotMatch(g.container.innerHTML, /没有论文|还没有论文/);
  ui.S.cy?.destroy();
});

test('more than 60 papers are drawn at once: no overview gate, no "显示全部" step', () => {
  const ui = fixture(); ui.accept(many(150, ['a', 'b', 'c']));
  const g = graphPage(ui); ui.S.mode = 'graph'; ui.S.filter = '*'; ui.S.focus = 'all';
  ui.setMode();
  assert.equal(g.drawn().filter(e => !e.data.source).length, 150);
  assert.doesNotMatch(g.container.innerHTML, /org-overview|show-all-graph|先选一个类别/);
  const source = fs.readFileSync(path.join(STATIC, 'organization.js'), 'utf8');
  assert.doesNotMatch(source, /OVERVIEW_LIMIT|show-all-graph|showAll/);
  ui.S.cy?.destroy();
});

test('the empty message follows what will be drawn, not the list before filtering', () => {
  const ui = fixture(); ui.accept(base({ items: [] }));
  const g = graphPage(ui); ui.S.mode = 'graph';
  ui.setMode();
  assert.match(g.container.innerHTML, /还没有论文/);
  assert.equal(g.drawn(), undefined);
  const source = fs.readFileSync(path.join(STATIC, 'organization.js'), 'utf8');
  assert.match(source, /if \(!nodes\.length\)/);                      // checked after the elements are built
});

test('a folded category never removes papers from the graph elements', () => {
  const ui = fixture(); const snap = many(6, ['a', 'b']);
  snap.directions.push({ id: 'child', name: 'child', parent_id: 'a', rank: 9 });
  snap.items.push({ key: 'deep', title: 'Deep', directions: ['child'] });
  snap.collapsed = ['a', 'b', 'child'];
  const nodes = ui.networkElements(snap, null).filter(e => !e.data.source);
  assert.equal(nodes.length, 7);
});

test('folding changes the sidebar only: no chevron on a leaf category, a folded parent hides its children, a stale folded leaf still lists its papers', () => {
  const ui = fixture();
  ui.accept(base({ directions: [{ id: 'root', name: 'Root', rank: 0 }, { id: 'child', name: 'Child', parent_id: 'root', rank: 1 }, { id: 'leaf', name: 'Leaf', rank: 2 }],
    collapsed: ['leaf'], items: [{ key: 'p', title: 'Under leaf', directions: ['leaf'] }, { key: 'q', title: 'Under child', directions: ['child'] }] }));
  ui.S.mode = 'graph';
  const markup = ui.sidebarHTML();
  const chevrons = [...markup.matchAll(/data-action="collapse"[^>]*data-id="(\w+)"|data-id="(\w+)"[^>]*data-action="collapse"|data-action="collapse" title="[^"]*" aria-label="[^"]*" data-no-i18n data-id="(\w+)"/g)].map(m => m[1] || m[2] || m[3]);
  assert.deepEqual(chevrons, ['root']);                              // only a category that has children can fold
  assert.match(markup, /Under leaf/);                                // a leaf folded by an older version still shows its papers
  ui.S.mode = 'library';
  assert.doesNotMatch(ui.sidebarHTML(), /data-action="collapse"[^>]*data-id="leaf"/);
});

test('folding a category saves the fold and repaints the sidebar without redrawing or re-laying-out the graph', async () => {
  const tree = { directions: [{ id: 'd1', name: 'A', rank: 0 }, { id: 'd2', name: 'B', parent_id: 'd1', rank: 1 }] };
  const ui = fixture(async (_, body) => base({ ...tree, revision: 4, collapsed: body.collapsed ? [body.id] : [] }));
  ui.accept(base(tree));
  const part = page(ui);
  ui.S.positions = { 'paper:local': { x: 1, y: 2 } };
  ui.S.mode = 'library';
  const before = ui.graphSignature(ui.S.snapshot);
  await ui.handle('collapse', { dataset: { id: 'd1' } });
  assert.deepEqual([...ui.S.collapsed], ['d1']);
  assert.equal(ui.graphSignature(ui.S.snapshot), before);            // the saved layout is not invalidated by a fold
  assert.deepEqual(JSON.parse(JSON.stringify(ui.S.positions)), { 'paper:local': { x: 1, y: 2 } });
  assert.ok(part('.org-sidebar').innerHTML.includes('展开'));
});

test('a big category is linked by a bounded number of lines, a small one still by all pairs', () => {
  const ui = fixture();
  const snap = base({ directions: [{ id: 'big', name: 'Big', rank: 0 }, { id: 'small', name: 'Small', rank: 1 }],
    items: [...Array.from({ length: 400 }, (_, i) => ({ key: `b${i}`, title: `B${i}`, directions: ['big'] })), ...Array.from({ length: 5 }, (_, i) => ({ key: `s${i}`, title: `S${i}`, directions: ['small'] }))] });
  const edges = ui.networkElements(snap, null).filter(e => e.data.kind === 'category');
  const within = prefix => edges.filter(e => e.data.source.startsWith(`paper:${prefix}`));
  assert.equal(within('s').length, 10);                              // 5 papers: every pair
  assert.ok(within('b').length <= 400 * 4, `bounded, got ${within('b').length}`);
  assert.ok(within('b').length >= 399);                              // and still one connected group
});

test('the graph hint pill is hidden while it has no text, and the overview styles are gone', () => {
  const css = fs.readFileSync(path.join(STATIC, 'organization.css'), 'utf8');
  assert.match(css, /\.org-graph-hint:empty\s*\{\s*display:none/);
  assert.doesNotMatch(css, /\.org-overview/);
});

// ---- layout and theme
// A headless graph of a fixed size that accepts objects made inside the page's sandbox (cytoscape's plain-object check
// does not recognise another realm's objects, so the page's {zoom, pan} would be ignored in the test only).
function sizedGraph(options, size) {
  const plain = v => JSON.parse(JSON.stringify(v));
  const cy = cytoscape({ ...options, elements: plain(options.elements || []), style: [], container: undefined, headless: true });
  cy.width = () => size.w; cy.height = () => size.h; cy.resize = () => cy;
  const viewport = cy.viewport.bind(cy), animate = cy.animate.bind(cy);
  cy.viewport = v => viewport(plain(v));
  cy.animate = (v, o) => { viewport(plain(v)); return cy; };          // the end state of the camera move, at once
  return cy;
}

test('locating a paper in a laid-out graph centres it, instead of keeping the old view or fitting its neighbours', () => {
  const ui = fixture();
  const positions = Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`paper:k${i}`, { x: i * 300, y: (i % 2) * 400 }]));
  ui.accept({ ...many(8, ['a', 'b']), positions });                      // every paper already has a saved place
  graphPage(ui);
  // A real 600x500 graph: the elements are copied out of the page's sandbox so cytoscape accepts them.
  ui.setCytoscape(options => sizedGraph(options, { w: 600, h: 500 }));
  ui.S.mode = 'graph'; ui.S.filter = '*'; ui.S.focus = 'all';
  ui.setMode();
  assert.equal(ui.S.cy.nodes().length, 8);
  ui.S.cy.viewport({ zoom: 1, pan: { x: -1500, y: 0 } });               // the person had looked elsewhere
  ui.S.key = 'k7'; ui.S.focus = 'paper1'; ui.S.graphFocus = 'paper:k7';    // what 在论文关系图中定位 sets
  ui.setMode();
  const p = ui.S.cy.getElementById('paper:k7').renderedPosition();
  assert.deepEqual([Math.round(p.x), Math.round(p.y)], [300, 250]);
  ui.S.cy.destroy();
});

test('a located paper stays in the middle when the graph box changes size, until the person moves the graph', () => {
  const ui = fixture();
  const size = { w: 1200, h: 800 };
  const cy = sizedGraph({ elements: [{ data: { id: 'paper:a' }, position: { x: 900, y: 300 } }, { data: { id: 'paper:b' }, position: { x: 100, y: 100 } }] }, size);
  ui.S.cy = cy;
  ui.focusGraph('paper:a');
  const centred = () => { const p = cy.getElementById('paper:a').renderedPosition(); return [Math.round(p.x), Math.round(p.y)]; };
  assert.deepEqual(centred(), [600, 400]);
  size.w = 560;                                                         // the pane appears or WebKit settles the size late
  ui.keepFocusCentered();
  assert.deepEqual(centred(), [280, 400]);
  ui.graphMovedByPerson();                                              // a drag or a wheel zoom
  size.w = 900;
  ui.keepFocusCentered();
  assert.deepEqual(centred(), [280, 400]);                              // no longer pulled back
});

test('the pane opens with a selected paper and closes like the graph pane: closed, the list takes the whole width', () => {
  const css = fs.readFileSync(path.join(STATIC, 'organization.css'), 'utf8');
  const block = css.slice(css.indexOf('/* Library as three panes'));
  assert.ok(block.length > 200, 'three-pane block exists');
  // Owner 2026-10-22: the list mode no longer keeps an empty column for the pane.
  assert.doesNotMatch(css, /\.org-list:not\(\[hidden\]\)\)[^{]*\.org-detail:not\(\.has-paper\)\s*\{[^}]*display:block/);
  assert.doesNotMatch(css, /\.org-workspace:has\(\.org-list:not\(\[hidden\]\)\)\s*\{[^}]*grid-template-columns/);
  assert.match(css, /\.org-workspace:not\(:has\(\.org-detail\.has-paper\)\)\s*\{\s*grid-template-columns:var\(--org-side\) minmax\(0,1fr\);/);
  assert.match(css, /\.org-workspace:has\(\.org-detail\.has-paper\)\s*\{\s*grid-template-columns:var\(--org-side\) minmax\(0,1fr\) minmax\(/);
  assert.match(block, /\.org-pdf\.is-local/); assert.match(block, /\.org-pdf\.is-direct/); assert.match(block, /\.org-pdf\.is-page/);
  assert.match(block, /@media \(max-width:900px\)/);
  assert.doesNotMatch(block, /#[0-9a-fA-F]{3,8}\b|rgba?\(/);          // light and dark both come from the theme variables
});

// ---- sorting the library list (owner 2026-10-23: by title, by publication date, by the date saved)
const sortable = () => base({ items: [
  { key: 'b', title: 'beta world models', published: '2021-05-01', saved_at: '2026-10-03T10:00:00+00:00', directions: [], pdf: 'none', note: '', note_version: 0 },
  { key: 'a', title: 'Alpha planning', published: '2024-01-01', saved_at: '2026-10-01T10:00:00+00:00', directions: [], pdf: 'none', note: '', note_version: 0 },
  { key: 'c', title: '中文标题', published: '', saved_at: null, directions: [], pdf: 'none', note: '', note_version: 0 },
  { key: 'd', title: 'Diffusion policy 10', published: '2023-07-01', saved_at: '2026-10-02T10:00:00+00:00', directions: [], pdf: 'none', note: '', note_version: 0 }] });
const listOrder = part => [...part('.org-list').innerHTML.matchAll(/data-action="select" data-key="([^"]+)"/g)].map(m => m[1]);

test('the list sorts by date saved (newest first by default), publication date, or title; papers missing the date go last', () => {
  const ui = fixture(); ui.accept(sortable()); const part = page(ui);
  ui.renderList();
  assert.deepEqual(listOrder(part), ['b', 'd', 'a', 'c']);                                   // 最近收藏
  for (const [mode, order] of [['saved-asc', ['a', 'd', 'b', 'c']], ['published-desc', ['a', 'd', 'b', 'c']],
                               ['published-asc', ['b', 'd', 'a', 'c']], ['title', ['a', 'b', 'd', 'c']]]) {
    ui.S.sort = mode; ui.renderList();
    assert.deepEqual(listOrder(part), order, mode);
  }
});

test('papers saved together (one import) keep a stable title order inside the same date', () => {
  const ui = fixture();
  const same = '2026-10-05T08:00:00+00:00';
  ui.accept(base({ items: ['Zeta', 'alpha', 'Beta'].map((t, i) => ({ key: `s${i}`, title: t, published: '2024', saved_at: same, directions: [], pdf: 'none', note: '', note_version: 0 })) }));
  const part = page(ui);
  for (const mode of ['saved-desc', 'saved-asc', 'published-desc']) {
    ui.S.sort = mode; ui.renderList();
    assert.deepEqual(listOrder(part), ['s1', 's2', 's0'], mode);
  }
});

test('the list header offers the five orders as one quiet menu, and the choice is remembered', () => {
  const ui = fixture(); ui.accept(sortable()); const part = page(ui);
  ui.renderList();
  const bulk = part('.org-bulk').innerHTML;
  const options = [...bulk.matchAll(/<option value="([^"]+)"[^>]*>([^<]+)<\/option>/g)].map(m => [m[1], m[2]]);
  assert.deepEqual(options, [['saved-desc', '最近收藏'], ['saved-asc', '最早收藏'], ['published-desc', '最新发表'], ['published-asc', '最早发表'], ['title', '标题']]);
  assert.match(bulk, /<select data-sort aria-label="排序"/);
  ui.setSort('title');
  assert.equal(ui.S.sort, 'title');
  assert.equal(ui.storedSort(), 'title');
  assert.deepEqual(listOrder(part), ['a', 'b', 'd', 'c']);
  ui.setSort('nonsense');
  assert.equal(ui.S.sort, 'title');                                                          // unknown values are ignored
});

// ---- "已读懂" (owner 2026-10-23): it belongs to the learning map, and a mistaken press can be taken back
const understoodLib = (on) => base({ items: [{ key: 'u', title: 'Understood paper', published: '2024', projects: ['p1'],
  understood_in: on ? ['p1'] : [], directions: [], pdf: 'none', note: '', note_version: 0 }] });

test('with the learning map switched off there is no "已读懂" anywhere in the library', () => {
  const ui = fixture(); ui.setBeta(false); ui.accept(understoodLib(false)); const part = page(ui);
  ui.S.scope = 'p1'; ui.renderList();
  assert.doesNotMatch(part('.org-list').innerHTML, /data-action="understood"|已读懂/);
  ui.setBeta(true); ui.renderList();
  assert.match(part('.org-list').innerHTML, /data-action="understood"/);
});

test('pressing "已读懂" again takes it back: the mark is retracted, not recorded a second time', async () => {
  const calls = [];
  const ui = fixture(async (url, body) => { calls.push(JSON.parse(JSON.stringify([url, body]))); return body.retract ? { retracted: [7] } : { feedback_id: 7 }; });
  ui.setBeta(true); ui.accept(understoodLib(true)); const part = page(ui);
  ui.S.scope = 'p1'; ui.renderList();
  assert.match(part('.org-list').innerHTML, /aria-pressed="true"/);
  await ui.handle('understood', { dataset: { key: 'u', project: 'p1' } });
  assert.deepEqual(calls, [['/api/feedback', { key: 'u', action: 'understood', project_id: 'p1', retract: true }]]);
  assert.deepEqual([...ui.S.snapshot.items[0].understood_in], []);
  assert.match(part('.org-list').innerHTML, /aria-pressed="false"/);
  await ui.handle('understood', { dataset: { key: 'u', project: 'p1' } });               // and pressing it once more marks it again
  assert.deepEqual(calls[1], ['/api/feedback', { key: 'u', action: 'understood', project_id: 'p1' }]);
  assert.deepEqual([...ui.S.snapshot.items[0].understood_in], ['p1']);
});

test('after a learning-map revision one press confirms the mark anew; a failed request changes nothing', async () => {
  let reply = { retracted: [], reconfirmed: true, feedback_id: 9 };
  const ui = fixture(async () => { if (reply instanceof Error) throw reply; return reply; });
  ui.setBeta(true); ui.accept(understoodLib(true)); const part = page(ui);
  ui.S.scope = 'p1'; ui.renderList();
  await ui.handle('understood', { dataset: { key: 'u', project: 'p1' } });
  assert.deepEqual([...ui.S.snapshot.items[0].understood_in], ['p1']);
  assert.match(part('.org-list').innerHTML, /aria-pressed="true"/);
  reply = new Error('网络错误');
  await ui.handle('understood', { dataset: { key: 'u', project: 'p1' } });
  assert.deepEqual([...ui.S.snapshot.items[0].understood_in], ['p1']);
});

test('with the learning map off the weekly report and the profile evidence say nothing about "已读懂"', () => {
  const vm2 = require('node:vm');
  const load = (file, beta) => {
    const ctx = vm2.createContext({ window: { PAGETIDE_ROUTE_BETA: beta }, module: { exports: {} }, document: {} });
    vm2.runInContext(fs.readFileSync(path.join(STATIC, file), 'utf8'), ctx);
    return ctx;
  };
  const report = { stats: { saved: 2, understood: 1 }, previous_stats: {}, daily: [{ date: '2026-10-20', weekday: 1, saved: 1, understood: 1 }],
    directions: [{ name: 'A', status: 'other', current: { saved: 0, understood: 0, papers: 1 }, previous: {} }],
    units: { done: 1, total: 3, items: [{ name: 'U', status: 'satisfied', current: { understood: 1 } }] } };
  for (const beta of [false, true]) {
    const ctx = load('weekly-ui.js', beta);
    const weekly = ctx.module.exports.weeklyHTML ? ctx.module.exports : ctx.window.PDHWeekly || ctx.PDHWeekly;
    const html = weekly.weeklyHTML(report);
    if (beta) assert.match(html, /已读懂/); else assert.doesNotMatch(html, /已读懂|学习图进度/);
  }
});
