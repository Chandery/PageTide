'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function fixture(api = async () => { throw new Error('Unexpected API call'); }, storage = new Map()) {
  let clientCounter = 0;
  const context = vm.createContext({
    module: { exports: {} },
    window: { PDH: { api, toast() {} }, addEventListener() {} },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    crypto: { randomUUID: () => `fresh-client-${++clientCounter}` }, setTimeout, clearTimeout, URL,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/organization.js'), 'utf8'), context);
  const ui = context.module.exports;
  ui.setReader = reader => { context.window.PDH.openReader = reader; };
  ui.reduceMotion = enabled => { context.window.matchMedia = () => ({matches: enabled}); };
  ui.createGraph = elements => {
    context.elements=elements;
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/vendor/cytoscape/cytoscape.min.js'),'utf8'),context);
    return vm.runInContext("cytoscape({headless:true,elements:JSON.parse(JSON.stringify(elements)),layout:{name:'preset'}})",context);
  };
  ui.S.root = { querySelector: () => null };
  return ui;
}
function snapshot(extra = {}) {
  return { directions: [{ id: 'd1', name: 'Models', rank: 0 }],
    items: [{ key: 'paper:one', title: 'Models', directions: ['d1'], note: 'Original', note_version: 4 }],
    positions: {}, revision: 7, drafts: [], ...extra };
}

test('graph focus highlights a neighborhood and replaces camera motion; zoom keeps its center', () => {
  const ui = fixture(), calls = [];
  const collection = { length: 1, removeClass(c) {calls.push(['remove',c]);return this;}, addClass(c) {calls.push(['add',c]);return this;}, boundingBox:()=>({x1:0,x2:200,y1:0,y2:100,w:200,h:100}) };
  const node = {...collection, position:()=>({x:100,y:50}), closedNeighborhood:()=>collection};
  ui.S.cy = { elements:()=>collection, getElementById:()=>node, resize(){}, stop(...a){calls.push(['stop',...a]);}, minZoom:()=>0.12, maxZoom:()=>3, width:()=>800,height:()=>600, zoom:()=>1,pan:()=>({x:20,y:40}),animate(t,o){calls.push(['animate',t,o]);}, viewport(t){calls.push(['viewport',t]);} };
  ui.focusGraph('direction:a'); ui.focusGraph('paper:b');
  assert.equal(ui.S.graphFocus,'paper:b');
  assert.equal(calls.filter(c=>c[0]==='stop' && c[1]===true && c[2]===false).length,2);
  assert.ok(calls.some(c=>c[0]==='add' && c[1]==='org-focused'));
  assert.equal(calls.filter(c=>c[0]==='animate').at(-1)[2].queue,false);
  ui.zoomGraph(1.2);
  const target = calls.filter(c=>c[0]==='animate').at(-1)[1];
  assert.equal(target.pan.x,-56); assert.equal(target.pan.y,-12);
  ui.reduceMotion(true); ui.focusGraph('paper:b');
  assert.equal(calls.at(-1)[0],'viewport');
});

test('paper-only network deduplicates memberships and keeps only valid similarity edges', () => {
  const ui = fixture();
  const data = snapshot({ directions: [{id:'a',name:'A'},{id:'b',name:'B'},{id:'empty',name:'Empty'}], items:[
    {key:'one',title:'Paper One',directions:['a','b']}, {key:'two',title:'Paper Two',directions:['a']} ] });
  const elements = ui.networkElements(data, {edges:[{source:'one',target:'two',weight:0.7},{source:'one',target:'missing',weight:1}]});
  const nodes = elements.filter(e=>!e.data.source), edges = elements.filter(e=>e.data.source);
  assert.equal(nodes.length,2);
  assert.equal(nodes.filter(e=>e.data.key==='one').length,1);
  assert.equal(nodes.some(e=>e.data.direction==='empty'),false);
  assert.equal(edges.filter(e=>e.data.kind==='membership').length,0);
  assert.equal(edges.filter(e=>e.data.kind==='similarity').length,1);
  assert.equal(ui.networkElements({items:[],directions:data.directions},null).length,0);
});

test('graph node color keeps category hue and darkens newer papers', () => {
  const ui = fixture();
  const data = { directions: [{ id: 'a', name: 'A', color: '#168579' }], items: [
    { key: 'old', title: 'Old', published: '2022', directions: ['a'] },
    { key: 'new', title: 'New', published: '2026', directions: ['a'] },
  ] };
  const nodes = ui.networkElements(data, null).filter(e => !e.data.source);
  const oldColor = nodes.find(e => e.data.key === 'old').data.color;
  const newColor = nodes.find(e => e.data.key === 'new').data.color;
  assert.equal(oldColor.split(',')[0], newColor.split(',')[0]);
  assert.ok(Number(newColor.match(/,(\d+)%\)$/)[1]) < Number(oldColor.match(/,(\d+)%\)$/)[1]));
});

test('initial radial layout assigns distinct positions around the selected origin', () => {
  const ui = fixture();
  const nodes = [
    { data: () => ({ id: 'paper:origin', degree: 3 }) },
    { data: () => ({ id: 'paper:a', degree: 2 }) },
    { data: () => ({ id: 'paper:b', degree: 1 }) },
  ];
  const positions = ui.radialPositions(nodes, 'paper:origin');
  assert.equal(positions['paper:origin'].x, 0);
  assert.equal(positions['paper:origin'].y, 0);
  assert.ok(positions['paper:a'].x !== positions['paper:b'].x || positions['paper:a'].y !== positions['paper:b'].y);
});

test('library paper action opens PDF directly without changing note selection', async () => {
  const ui = fixture(); ui.accept(snapshot());
  let opened;
  ui.setReader((...args)=>{opened=args;});
  await ui.handle('read',{dataset:{key:'paper:one'}});
  assert.deepEqual(opened,['paper:one','Models']);
  assert.equal(ui.S.key,null);
});

test('Cytoscape constructor positions never alias saved snapshot coordinates',()=>{
  const ui=fixture(), snap=snapshot(), positions={'direction:d1':{x:803,y:460},'paper:paper:one':{x:100,y:100}};
  const cy=ui.createGraph(ui.networkElements(snap,null,positions));
  assert.equal(cy.nodes().length,1);
  cy.nodes().forEach(n=>n.position({x:50,y:60}));cy.destroy();
  assert.deepEqual(positions,{'direction:d1':{x:803,y:460},'paper:paper:one':{x:100,y:100}});
});

test('multi-selection drag has one pointer owner and one complete save event',()=>{
  const ui=fixture(), cytoscape=require('../app/static/vendor/cytoscape/cytoscape.min.js');
  const cy=cytoscape({headless:true,elements:[{data:{id:'a'}},{data:{id:'b'}}]});
  const events=[];ui.bindGraphDrag(cy,e=>events.push('begin:'+e.target.id()),()=>{},e=>events.push('save:'+e.target.id()));
  cy.nodes().select();cy.nodes().emit('grab');cy.$id('a').emit('grabon');
  cy.nodes().emit('dragfree');cy.$id('a').emit('dragfreeon');
  assert.deepEqual(events,['begin:a','save:a']);cy.destroy();
});

test('ordinary click releases graph gesture while actual drag saves after freeon',()=>{
  const ui=fixture(), cytoscape=require('../app/static/vendor/cytoscape/cytoscape.min.js');
  const cy=cytoscape({headless:true,elements:[{data:{id:'a'}}]});
  const events=[];ui.bindGraphDrag(cy,()=>events.push('begin'),()=>events.push('drag'),()=>events.push('save'),e=>events.push(e.type));
  const n=cy.$id('a');n.emit('grabon');n.emit('tap');n.emit('freeon');
  assert.deepEqual(events,['begin','freeon']);events.length=0;
  n.emit('grabon');n.emit('drag');n.emit('freeon');n.emit('dragfreeon');
  assert.deepEqual(events,['begin','drag','save']);cy.destroy();assert.equal(events.at(-1),'destroy');
});

test('queued completed drags advance acknowledged revision even after graph is replaced', async () => {
  const writes=[];
  const ui=fixture(async (url,body)=>{writes.push(body);return snapshot({revision:body.revision+1});});
  ui.accept(snapshot());
  const save=ui.positionWriter(7);
  const first=save({'paper:one':{x:1,y:2}});
  const second=save({'paper:one':{x:3,y:4}});
  ui.S.cy=null;
  await first; await second;
  assert.deepEqual(writes.map(w=>w.revision),[7,8]);
  assert.equal(writes[1].positions['paper:one'].x,3);
});

test('snapshot prunes deleted direction aliases but retains current membership coordinates', () => {
  const ui = fixture(), live = ui.cardId('paper:one', 'd1'), stale = ui.cardId('paper:one', 'deleted');
  ui.accept(snapshot());
  ui.S.positions = { [live]: { x: 10, y: 20 }, [stale]: { x: 30, y: 40 }, 'direction:deleted:anchor': { x: 1, y: 1 } };
  ui.accept(snapshot());
  assert.deepEqual(Object.keys(ui.S.positions), [live]);
  assert.equal(ui.S.positions[live].x, 10);
  ui.accept(snapshot({ directions: [], items: [] }));
  assert.equal(Object.keys(ui.S.positions).length, 0);
});

test('deselect removes shared identity only when all visible aliases are deselected', () => {
  const ui = fixture();
  ui.S.selected = new Set(['p1', 'offscreen']);
  const node = (key, selected) => ({ data: () => key, selected: () => selected });
  ui.syncGraphSelection([node('p1', false), node('p1', true)]);
  assert.equal(ui.S.selected.has('p1'), true);
  ui.syncGraphSelection([node('p1', false), node('p1', false)]);
  assert.equal(ui.S.selected.has('p1'), false);
  assert.equal(ui.S.selected.has('offscreen'), true);
});

test('conflicted save preserves draft text and original note version after refresh', async () => {
  const calls = [];
  const ui = fixture(async (_, body) => {
    calls.push(body);
    if (body.action === 'draft-save') return { draft: { version: 1 }, revision: 7 };
    throw new Error('Note version conflict');
  });
  ui.accept(snapshot());
  const draft = ui.draftFor(ui.S.snapshot.items[0]);
  draft.text = 'My unsaved work'; draft.dirty = true;
  await ui.saveNote('paper:one');
  ui.accept(snapshot({ items: [{ ...snapshot().items[0], note: 'Remote changes', note_version: 5 }] }));
  const restored = ui.draftFor(ui.S.snapshot.items[0]);
  assert.equal(restored.text, 'My unsaved work');
  assert.equal(restored.version, 4);
  assert.equal(restored.dirty, true);
  assert.match(restored.error, /Note version conflict/);
  assert.deepEqual(calls.map(c => c.action), ['draft-save', 'note']);
  assert.equal(calls[0].revision, 7);
  assert.equal(calls[1].version, 4);
});

test('database draft restores without browser storage and adopts client/version for next write', async () => {
  let request;
  const ui = fixture(async (_, body) => { request = body; return { draft: { version: 9 }, revision: 7 }; });
  ui.accept(snapshot({ drafts: [{ key: 'paper:one', client: 'previous-port-client', text: 'Recovered', version: 8, updated_at: '2026-09-14' }] }));
  const draft = ui.draftFor(ui.S.snapshot.items[0]);
  assert.equal(draft.text, 'Recovered');
  assert.equal(draft.client, 'previous-port-client');
  assert.equal(draft.serverVersion, 8);
  await ui.persistDraft('paper:one');
  assert.equal(request.action, 'draft-save');
  assert.equal(request.client, 'previous-port-client');
  assert.equal(request.version, 8);
  assert.equal(draft.serverVersion, 9);
});

test('closing replaced dialog does not remove replacement or steal focus', () => {
  const ui = fixture();
  let focused = 0;
  const replacement = { name: 'preview' };
  const children = new Set([replacement]);
  const old = { remove: () => children.delete(old) };
  const host = { querySelector: () => [...children][0] || null };
  ui.closeDialog(old, host, { focus: () => focused++ });
  assert.equal(children.has(replacement), true);
  assert.equal(focused, 0);
  children.clear();
  ui.closeDialog(old, host, { focus: () => focused++ });
  assert.equal(focused, 1);
});

test('recovered remote draft cannot save until explicit comparison confirmation', async () => {
  const calls = [];
  const ui = fixture(async (_, body) => {
    calls.push(body);
    if (body.action === 'draft-save') return { draft: { version: 9 }, revision: 7 };
    if (body.action === 'draft-clear') return { draft: { version: 10 }, revision: 7 };
    return snapshot({ items: [{ ...snapshot().items[0], note: body.text, note_version: 6 }] });
  });
  ui.accept(snapshot({ drafts: [{ key: 'paper:one', client: 'old-client', text: 'Older draft', version: 8, updated_at: '2026-09-14' }] }));
  const draft = ui.draftFor(ui.S.snapshot.items[0]);
  await ui.saveNote('paper:one');
  assert.equal(calls.length, 0);
  assert.equal(draft.recovered, true);
  assert.equal(draft.text, 'Older draft');
  assert.equal(draft.dirty, true);
  draft.text = 'Edited recovered draft'; draft.error = '';
  ui.accept(snapshot({ items: [{ ...snapshot().items[0], note: 'Peer note', note_version: 5 }] }));
  await ui.saveNote('paper:one');
  assert.equal(calls.length, 0);
  assert.equal(draft.recovered, true);
  ui.confirmDraftVersion('paper:one', 5);
  await ui.saveNote('paper:one');
  assert.deepEqual(calls.map(c => c.action), ['draft-save', 'note', 'draft-clear']);
  assert.equal(calls[1].version, 5);
  assert.equal(calls[1].text, 'Edited recovered draft');
  assert.equal(draft.recovered, false);
  assert.equal(draft.dirty, false);
});

test('paper links accept HTTP(S) only', () => {
  const ui = fixture();
  assert.equal(ui.safePaperURL('https://example.org/paper'), 'https://example.org/paper');
  assert.equal(ui.safePaperURL('http://example.org/paper'), 'http://example.org/paper');
  for (const value of ['javascript:alert(1)', 'file:///etc/passwd', 'data:text/html,test', '/relative', null]) assert.equal(ui.safePaperURL(value), null);
  assert.equal(ui.paperURL({arxiv_id: '2401.01234'}), 'https://arxiv.org/abs/2401.01234');
  assert.equal(ui.paperURL({doi: '10.1000/example'}), 'https://doi.org/10.1000/example');
});

test('newer local draft wins reload while remote alternatives and client versions survive', async () => {
  const storage = new Map();
  const first = fixture(undefined, storage);
  first.accept(snapshot());
  const local = first.draftFor(first.S.snapshot.items[0]);
  Object.assign(local, { text: 'Latest offline edit', dirty: true, client: 'same-client', serverVersion: 3 });
  first.cacheDraft('paper:one', local);
  const ui = fixture(undefined, storage);
  ui.accept(snapshot({ drafts: [{ key: 'paper:one', client: 'same-client', text: 'Older remote', version: 3 }, { key: 'paper:one', client: 'peer-client', text: 'Peer draft', version: 2 }] }));
  const draft = ui.draftFor(ui.S.snapshot.items[0]);
  assert.equal(draft.text, 'Latest offline edit');
  assert.equal(draft.client, 'same-client');
  assert.equal(draft.serverVersion, 3);
  assert.equal(draft.recovered, true);
  assert.deepEqual(Array.from(draft.variants, d => d.text), ['Older remote', 'Peer draft']);
  await ui.saveNote('paper:one');
  assert.equal(draft.text, 'Latest offline edit');
  ui.chooseDraftVariant('paper:one', draft.variants[1]);
  assert.equal(draft.text, 'Peer draft');
  assert.equal(draft.recovered, true);
  assert.equal(draft.variants.some(d => d.text === 'Latest offline edit'), true);
  const reopened = fixture(undefined, storage);
  reopened.accept(snapshot());
  assert.equal(reopened.draftFor(reopened.S.snapshot.items[0]).variants.some(d => d.text === 'Latest offline edit'), true);
});

test('queued stale direction intent keeps its explicit revision and is rejected', async () => {
  let request;
  const ui = fixture(async (_, body) => { request = body; throw new Error('Organization revision conflict'); });
  ui.accept(snapshot());
  const intent = { action: 'direction-save', id: 'd1', name: 'Old edit', color: '#168579', revision: 7 };
  const pending = ui.mutate(intent, false);
  ui.accept(snapshot({ revision: 8 }));
  await assert.rejects(pending, /revision conflict/);
  assert.equal(request.revision, 7);
  assert.equal(ui.S.snapshot.revision, 8);
});

test('graph gesture sends only changed nodes with rendered revision and invalidates peer cache', async () => {
  let request;
  const ui = fixture(async (_, body) => { request = body; throw new Error('Organization revision conflict'); });
  const id = ui.cardId('paper:one', 'd1');
  ui.accept(snapshot({ positions: { [id]: { x: 1, y: 2 } } }));
  const renderedRevision = ui.S.snapshot.revision;
  ui.S.positions[id] = { x: 50, y: 50 };
  const before = { [id]: { x: 1, y: 2 }, untouched: { x: 4, y: 5 } };
  const delta = ui.changedPositions(before, { ...before, [id]: { x: 10, y: 20 } });
  assert.deepEqual(Object.keys(delta), [id]);
  ui.accept(snapshot({ revision: 8, positions: { [id]: { x: 90, y: 90 } } }));
  assert.equal(Object.keys(ui.S.positions).length, 0);
  await assert.rejects(ui.mutate({ action: 'positions', positions: delta, revision: renderedRevision }, false), /revision conflict/);
  assert.equal(request.revision, 7);
  assert.deepEqual(Object.keys(request.positions), [id]);
  assert.equal(ui.S.snapshot.positions[id].x, 90);
});

test('actual direction-up queued behind autosave cannot overwrite a newer direction name', async () => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const calls = [];
  const oldDirections = [{ id: 'd1', name: 'First', color: '#168579', rank: 0 }, { id: 'd2', name: 'Old name', color: '#168579', rank: 1 }];
  const latest = snapshot({ revision: 8, directions: [oldDirections[0], { ...oldDirections[1], name: 'Peer renamed' }] });
  const ui = fixture(async (_, body) => {
    calls.push(body);
    if (body.action === 'note') { await gate; return latest; }
    if (body.revision !== latest.revision) throw new Error('Organization revision conflict');
    throw new Error('Stale arrow was incorrectly authorized');
  });
  ui.accept(snapshot({ directions: oldDirections }));
  const autosave = ui.mutate({ action: 'note', key: 'paper:one', text: 'Saved note', version: 4 }, false);
  const arrow = ui.handle('direction-up', { dataset: { id: 'd2' } });
  const rejected = assert.rejects(arrow, /Organization revision conflict/);
  release();
  await autosave;
  await rejected;
  assert.deepEqual(calls.map(c => c.action), ['note', 'direction-save']);
  assert.equal(calls[1].name, 'Old name');
  assert.equal(calls[1].rank, 0);
  assert.equal(calls[1].revision, 7);
  assert.equal(ui.S.snapshot.directions[1].name, 'Peer renamed');
});

test('default positions revision is captured before queue dispatch', async () => {
  let request;
  const ui = fixture(async (_, body) => { request = body; throw new Error('Organization revision conflict'); });
  ui.accept(snapshot());
  const pending = ui.mutate({ action: 'positions', positions: { node: { x: 1, y: 2 } } }, false);
  ui.accept(snapshot({ revision: 8 }));
  await assert.rejects(pending, /revision conflict/);
  assert.equal(request.revision, 7);
});

test('draft CAS versions still advance at dispatch for sequential queued writes', async () => {
  const versions = [];
  const ui = fixture(async (_, body) => { versions.push(body.version); return { draft: { version: body.version + 1 }, revision: 7 }; });
  ui.accept(snapshot());
  const draft = ui.draftFor(ui.S.snapshot.items[0]);
  draft.serverVersion = 2;
  const first = ui.mutate({ action: 'draft-save', key: 'paper:one', client: draft.client, text: 'First' }, false);
  const second = ui.mutate({ action: 'draft-save', key: 'paper:one', client: draft.client, text: 'Second' }, false);
  await first; await second;
  assert.deepEqual(versions, [2, 3]);
  assert.equal(draft.serverVersion, 4);
});

test('category tree traverses nested folders and parent view deduplicates shared papers', () => {
  const ui = fixture();
  ui.accept(snapshot({directions:[
    {id:'root',name:'AI',rank:0}, {id:'child',name:'World models',parent_id:'root',rank:1},
    {id:'leaf',name:'Robotics',parent_id:'child',rank:2}, {id:'other',name:'Medicine',rank:3}
  ],items:[{key:'shared',title:'Shared',directions:['leaf','child','other']},{key:'second',title:'Second',directions:['leaf']},{key:'outside',title:'Outside',directions:['other']}]}));
  assert.deepEqual(JSON.parse(JSON.stringify(ui.treeRows().map(d=>[d.id,d.depth,d.path]))),
    [['root',0,'AI'],['child',1,'AI / World models'],['leaf',2,'AI / World models / Robotics'],['other',0,'Medicine']]);
  ui.S.filter='root';
  assert.deepEqual(Array.from(ui.visible(),p=>p.key),['shared','second']);
  ui.S.snapshot.collapsed=['root'];
  assert.deepEqual(Array.from(ui.treeRows().filter(d=>!d.hidden),d=>d.id),['root','other']);
  // Folding the tree does not change library memberships or the selected parent view.
  assert.deepEqual(Array.from(ui.visible(),p=>p.key),['shared','second']);
});

test('paper-only graph respects nested collapse and preserves shared papers', () => {
  const ui=fixture();
  const snap=snapshot({directions:[{id:'a',name:'A'},{id:'b',name:'B',parent_id:'a'},{id:'c',name:'C'}],items:[
    {key:'shared',directions:['b','c']},{key:'inside',directions:['b']}],positions:{}});
  const expanded=ui.networkElements(snap,null);
  assert.equal(expanded.filter(e=>e.data.key==='shared').length,1);
  assert.equal(expanded.filter(e=>e.data.kind==='hierarchy').length,0);
  const collapsed=ui.networkElements({...snap,collapsed:['a']},null);
  assert.equal(collapsed.filter(e=>e.data.key==='shared').length,1);
  assert.equal(collapsed.filter(e=>e.data.key==='inside').length,0);
  assert.equal(collapsed.filter(e=>e.data.direction==='b').length,0);
  const nodeIds=new Set(collapsed.filter(e=>!e.data.source).map(e=>e.data.id));
  assert.ok(collapsed.filter(e=>e.data.source).every(e=>nodeIds.has(e.data.source)&&nodeIds.has(e.data.target)));
});

test('directory retains expansion for persisted collapsed leaf categories in graph mode', () => {
  const ui=fixture();
  ui.accept(snapshot({directions:[{id:'leaf',name:'Saved <leaf>',rank:0}],collapsed:['leaf'],items:[{key:'p',directions:['leaf']}]}));
  ui.S.mode='graph';
  const markup=ui.sidebarHTML();
  assert.match(markup,/data-action="collapse"/);
  assert.match(markup,/aria-expanded="false"/);
  assert.match(markup,/展开 Saved &lt;leaf&gt;/);
  assert.match(markup,/org-category-menu/);
  assert.doesNotMatch(markup,/Saved <leaf>/);
});

test('reading viewport stays readable and centers a real paper in a dispersed corpus', () => {
  const ui=fixture(), cy=ui.createGraph([
    {data:{id:'paper:a',key:'a'},position:{x:0,y:0}},
    {data:{id:'paper:b',key:'b'},position:{x:5000,y:3000}}
  ]);
  ui.S.cy=cy; cy.width=()=>800; cy.height=()=>550;
  const target=ui.graphViewport(cy.nodes());
  assert.ok(target.zoom>=0.9);
  assert.ok(cy.nodes().some(n=>{
    const p=n.position();
    return Math.abs(p.x*target.zoom+target.pan.x-400)<1 && Math.abs(p.y*target.zoom+target.pan.y-275)<1;
  }));
  const overview=ui.graphViewport(cy.nodes(),true);
  assert.ok(overview.zoom<target.zoom);
  cy.destroy();
});

test('paper focus centers the chosen paper even with a distant neighbor', () => {
  const ui=fixture(), cy=ui.createGraph([
    {data:{id:'paper:a',key:'a'},position:{x:50,y:70}},
    {data:{id:'paper:b',key:'b'},position:{x:7000,y:4000}},
    {data:{id:'ab',source:'paper:a',target:'paper:b'}}
  ]);
  ui.S.cy=cy; cy.width=()=>800; cy.height=()=>550;
  let target; cy.animate=t=>{target=t;};
  ui.focusGraph('paper:a');
  assert.ok(target.zoom>=1);
  assert.equal(50*target.zoom+target.pan.x,400);
  assert.equal(70*target.zoom+target.pan.y,275);
  cy.destroy();
});

test('category focus clears stale paper focus and locates uncategorized papers', () => {
  const ui=fixture();
  ui.S.snapshot=snapshot({items:[{key:'a',directions:['d1']},{key:'b',directions:[]}]});
  const cy=ui.createGraph([{data:{id:'paper:a',key:'a'},position:{x:0,y:0}},
    {data:{id:'paper:b',key:'b'},position:{x:2000,y:700}}]);
  ui.S.cy=cy; cy.width=()=>800; cy.height=()=>550;
  let target; cy.animate=t=>{target=t;};
  ui.S.graphFocus='paper:a'; ui.S.filter='';
  ui.focusCategory();
  assert.equal(ui.S.graphFocus,null);
  assert.equal(cy.getElementById('paper:b').hasClass('org-dim'),false);
  assert.equal(cy.getElementById('paper:a').hasClass('org-dim'),true);
  assert.equal(2000*target.zoom+target.pan.x,400);
  ui.S.filter='empty'; target=null; ui.focusCategory();
  assert.equal(target,null);
  assert.match(ui.S.notice,/没有/);
  cy.destroy();
});

test('selected category reveals folded papers without changing saved collapse or coordinates', () => {
  const ui=fixture(), snap=snapshot({collapsed:['d1'],positions:{'paper:paper:one':{x:123,y:456}}});
  const before=JSON.stringify(snap);
  const elements=ui.networkElements(snap,null,snap.positions,new Set(['paper:one']));
  assert.equal(elements.filter(e=>e.data.key==='paper:one').length,1);
  assert.equal(JSON.stringify(snap),before);
  assert.ok(elements[0].data.size>=28);
});

test('graph sidebar nests papers under their category for direct paper focus', () => {
  const ui=fixture();
  ui.S.mode='graph'; ui.S.snapshot=snapshot({items:[{key:'a',title:'Alpha Paper',published:'2025-01-01',directions:['d1']},{key:'b',title:'Beta Paper',published:'2024-01-01',directions:[]}]});
  const markup=ui.sidebarHTML();
  assert.doesNotMatch(markup,/图谱论文/); assert.match(markup,/Alpha Paper/); assert.match(markup,/Beta Paper/); assert.match(markup,/data-action="graph-paper-focus"/);
});

test('detail pane names the paper category prominently, links it, and marks uncategorized papers', () => {
  const ui=fixture();
  ui.S.snapshot=snapshot({items:[{key:'a',title:'Alpha',directions:['d1']},{key:'b',title:'Beta',directions:[]}]});
  const filed=ui.detailCategoriesHTML(ui.S.snapshot.items[0]);
  assert.match(filed,/class="org-detail-categories" aria-label="所属类别"/);
  assert.match(filed,/class="org-detail-badge" data-action="filter" data-id="d1"[^>]*><i style="background:hsl\(/);
  assert.match(filed,/data-action="paper-membership" data-key="a">编辑类别/);
  assert.match(ui.detailCategoriesHTML(ui.S.snapshot.items[1]),/is-empty" data-action="filter" data-id=""[^>]*>未分类/);
});

test('categories left at the default slate still get distinct graph hues matching their chips', () => {
  const ui=fixture();
  ui.S.snapshot=snapshot({directions:[{id:'x',name:'X',color:'#64748b',rank:0},{id:'y',name:'Y',color:'#64748b',rank:1},{id:'z',name:'Z',color:'#168579',rank:2}],items:[{key:'p',title:'P',directions:['y']}]});
  const hue=c=>c.match(/^hsl\((\d+),/)[1];
  assert.notEqual(hue(ui.categoryColor('x')),hue(ui.categoryColor('y')));
  assert.equal(hue(ui.categoryColor('z')),'174');
  const node=ui.networkElements(ui.S.snapshot,null).find(e=>e.data.key==='p');
  assert.equal(hue(node.data.color),hue(ui.categoryColor('y')));
});

test('suggestion review nests child categories under their parent and states the profile basis', () => {
  const ui = fixture();
  const preview = { fingerprint: 'f', pending_keys: ['p3'],
    profile: { project: '世界模型<项目>', pinned: ['world models', 'JEPA'], unmatched: [{ term: 'diffusion', documents: 1 }, { term: 'WM', documents: 9, same_as: 'world models' }] },
    groups: [
      { id: 'top', name: '世界模型', keys: ['p1', 'p2'], parent: null, reason: '来自画像固定关键词「world models」' },
      { id: 'kid', name: 'JEPA', keys: ['p1'], parent: 'top', reason: '放在其下' },
      { id: 'grand', name: '<b>Video</b>', keys: ['p2'], parent: 'kid', reason: 'x' }] };
  const html = ui.suggestionsHTML(preview, key => ({ title: key === 'p1' ? 'Paper <one>' : key }));
  assert.match(html, /依据「世界模型&lt;项目&gt;」画像的固定关键词：world models、JEPA/);
  assert.match(html, /未单独成类：diffusion（只有 1 篇提到）；WM（与「world models」基本是同一批论文）/);
  assert.match(html, /3 个类别 · 1 篇没有共同短语/);
  assert.equal((html.match(/class="org-suggestion is-child"/g) || []).length, 2);
  assert.match(html, /data-suggestion="0" style="--depth:0"/);
  assert.match(html, /data-suggestion="1" style="--depth:1"><div class="org-suggestion-head"><input type="checkbox" data-enabled checked aria-label="采用此类别"><span class="org-suggestion-parent">世界模型 ›<\/span>/);
  assert.match(html, /style="--depth:2"/);
  assert.match(html, /Paper &lt;one&gt;/);
  assert.doesNotMatch(html, /<b>|<one>/);
});

test('suggestion review reports pinned terms dropped over the category limit', () => {
  const ui = fixture();
  const html = ui.suggestionsHTML({ groups: [], profile: { project: 'P', pinned: ['a'],
    unmatched: [{ term: '<late>', documents: 4, dropped: true }] } });
  assert.match(html, /未单独成类：&lt;late&gt;（4 篇提到，超出 12 个一级类别上限）/);
});

test('suggestion review without pinned terms says the groups are title phrases', () => {
  const ui = fixture();
  const html = ui.suggestionsHTML({ groups: [], profile: { project: 'Demo', pinned: [], unmatched: [] } });
  assert.match(html, /「Demo」还没有固定关键词，先按标题里反复出现的短语分组/);
  assert.match(html, /没有可应用的建议/);
});

test('undo button names the change it undoes and is absent when nothing visible can be undone', () => {
  const ui = fixture();
  assert.equal(ui.undoHTML(null), '');
  assert.equal(ui.undoHTML({ id: 3, label: null }), '');
  const html = ui.undoHTML({ id: 12, label: '应用<建议>' });
  assert.match(html, /data-action="undo" data-event="12" title="撤销：应用&lt;建议&gt;"/);
  assert.match(html, />撤销应用&lt;建议&gt;<\/button>$/);
});

test('toolbar has an undo slot and no refresh button', () => {
  const source = fs.readFileSync(path.join(__dirname, '../app/static/organization.js'), 'utf8');
  assert.match(source, /<span class="org-undo-slot" data-undo-slot><\/span><button data-action="suggest">/);
  assert.doesNotMatch(source, /button\('refresh'|data-action="refresh"|case 'refresh'/);
});

test('named undo sends the event id it showed', async () => {
  const calls = [];
  const ui = fixture(async (url, body) => { calls.push(body); return snapshot({ revision: 8, undo: null }); });
  ui.accept(snapshot({ undo: { id: 41, label: '新建类别' } }));
  ui.S.root = { querySelector: () => null, querySelectorAll: () => [] };
  try { await ui.handle('undo', { dataset: {} }); } catch (error) { /* rendering needs a DOM */ }
  assert.equal(calls[0]?.action, 'undo');
  assert.equal(calls[0]?.event, 41);
});
