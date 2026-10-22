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
    window: { PDH: { api, toast() {} }, PDHPaperContext: require('../app/static/paper-context.js'), addEventListener() {} },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    crypto: { randomUUID: () => `fresh-client-${++clientCounter}` }, setTimeout, clearTimeout, URL,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/organization.js'), 'utf8'), context);
  const ui = context.module.exports;
  ui.setReader = reader => { context.window.PDH.openReader = reader; };
  ui.setDetail = open => { context.window.PDH.openDetail = open; };
  ui.setDocument = doc => { context.document = doc; };
  ui.setProject = project => { context.window.PDH.state = {currentProject: project}; };
  ui.setAPI = api => { context.window.PDH.api = api; };
  ui.publicUI = context.window.PDHOrganization;
  ui.setCytoscape = factory => { context.window.cytoscape = factory; };
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
  assert.deepEqual(opened,['paper:one','Models',null]);
  assert.equal(ui.S.key,null);
});

test('library PDF carries its chosen scope while the top project stays unrelated', async () => {
  const ui = fixture(); ui.accept(snapshot({items:[{key:'a',title:'A',projects:['cs']},{key:'shared',title:'Shared',projects:['cs','materials']}] }));
  ui.setProject('medicine'); ui.S.scope = 'cs';
  const opened=[]; ui.setReader((...args)=>opened.push(args));
  await ui.handle('read',{dataset:{key:'a'}});
  await ui.handle('read',{dataset:{key:'shared'}});
  assert.deepEqual(opened,[['a','A','cs'],['shared','Shared','cs']]);
  assert.equal(ui.S.scope,'cs');
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

const reviewPreview = () => ({ fingerprint: 'f', scope: 'p1', pending_keys: ['p9'], profile: { project: 'P', pinned: [], unmatched: [] },
  groups: [
    { id: 'top', name: '世界模型', keys: ['p1', 'p2'], parent: null, reason: '来自画像固定关键词「world models」', kind: 'create', target: null, color: '#64748b' },
    { id: 'kid', name: 'JEPA', keys: ['p1'], parent: 'top', reason: '放在其下', kind: 'create', target: null, color: '#64748b' },
    { id: 'grand', name: '<b>Video</b>', keys: ['p2'], parent: 'kid', reason: 'x', kind: 'create', target: null, color: '#64748b' },
    { id: 'add-1', name: 'Robotics', keys: ['p3'], parent: null, reason: '标题或摘要提到「Robotics」', kind: 'add', target: 'd9', color: '#123456' }],
  merges: [{ id: 'merge-1', keep: 'd1', drop: ['d2'], keys: ['p4'], name: '机器人', reason: '同一层级有 2 个同名类别「机器人」' }],
  moves: [{ id: 'move-1', key: 'p5', from: ['d1'], to: 'd3', name: 'World <model>', reason: '它所在的类别「机器人」没有出现在标题或摘要里' }] });

test('the review lists only changes, in sections, nests child categories and escapes what it shows', () => {
  const ui = fixture();
  const html = ui.suggestionsHTML(reviewPreview(), key => ({ title: key === 'p1' ? 'Paper <one>' : key }), id => ({ d1: '机器人', d3: 'World <model>' }[id] || id));
  for (const title of ['新增分类', '归入已有分类', '合并重复分类', '建议调整归属']) assert.match(html, new RegExp(`<h4>${title}</h4>`));
  assert.equal((html.match(/class="org-suggestion is-child"/g) || []).length, 2);
  assert.match(html, /data-suggestion="1" style="--depth:1"><div class="org-suggestion-head"><input type="checkbox" data-enabled checked aria-label="采用此类别"><span class="org-suggestion-parent">世界模型 ›<\/span>/);
  assert.match(html, /Paper &lt;one&gt;/);
  assert.doesNotMatch(html, /<b>Video|<one>|<model>/);
  assert.doesNotMatch(html, /范围：/);
});

test('additions to an existing category cannot be renamed or recoloured; merges are ticked and moves are not', () => {
  const ui = fixture();
  const html = ui.suggestionsHTML(reviewPreview());
  const add = html.slice(html.indexOf('data-suggestion="3"'), html.indexOf('</fieldset>', html.indexOf('data-suggestion="3"')));
  assert.match(add, /data-name[^>]*readonly/);
  assert.doesNotMatch(add, /type="color"/);
  assert.match(add, /aria-label="加入这个类别"/);
  assert.match(html, /data-merge-enabled checked/);
  assert.match(html, /data-move-enabled aria-label/);
  assert.doesNotMatch(html, /data-move-enabled checked/);
  assert.doesNotMatch(html, /子类别和论文都会并入保留的那个/);
});

test('category review carries no standing explanation of its standards, with or without changes', () => {
  const ui = fixture();
  for (const preview of [reviewPreview(), { groups: [], merges: [], moves: [], pending_keys: [], scope: 'p1' }]) {
    const html = ui.suggestionsHTML(preview);
    for (const gone of ['明确的研究术语', '中英文同义名称归为同一类', '优先沿用已有分类', '证据不足的论文保留待分类', '方法细分类不会自动变成一级方向', '父级与子类不按同义分类合并']) assert.doesNotMatch(html, new RegExp(gone), gone);
    assert.match(html, preview.groups.length ? /新增分类/ : /没有需要调整的内容/);
  }
});

test('merge preview shows each real alias name safely and keeps legacy copy names readable', () => {
  const ui = fixture(), preview = reviewPreview();
  preview.merges[0].copies = [
    { id: 'd1', name: 'World Models', papers: 4, children: 1 },
    { id: 'd2', name: '世界模型', papers: 2, children: 0 },
    { id: 'd3', name: '<img src=x onerror=alert(1)>', papers: 1, children: 0 },
    { id: 'legacy', papers: 3, children: 0 },
  ];
  const html = ui.suggestionsHTML(preview, key => ({ title: key }), id => id === 'legacy' ? '手工<类别>' : id);
  for (const label of ['World Models', '世界模型', '&lt;img src=x onerror=alert(1)&gt;', '手工&lt;类别&gt;']) {
    assert.ok(html.includes(`<span data-no-i18n>${label}</span>`), label);
  }
  assert.doesNotMatch(html, /<img src=x|手工<类别>/);
  assert.ok(html.indexOf('World Models') < html.indexOf('4 篇、1 个子类'));
  assert.match(html, /data-merge-enabled checked/);
  assert.doesNotMatch(html, /合并后可以撤销/);
});

test('the category standards explanation has complete English UI translations', () => {
  const pack = JSON.parse(fs.readFileSync(path.join(__dirname, '../app/static/i18n/en-US.json'), 'utf8')).messages;
  for (const source of [
    '分类采用明确的研究术语；中英文同义名称归为同一类，优先沿用已有分类，证据不足的论文保留待分类。',
    '父级表示研究方向，子类表示更细的方向或方法；方法细分类不会自动变成一级方向，父级与子类不按同义分类合并。',
  ]) {
    assert.equal(typeof pack[source], 'string', source);
    assert.doesNotMatch(pack[source], /[㐀-鿿]/);
  }
});

test('with nothing to change the review says so and lists nothing, not even what was checked', () => {
  const ui = fixture();
  const html = ui.suggestionsHTML({ fingerprint: 'f', groups: [], merges: [], moves: [], pending_keys: [], scope: null, profile: {} });
  assert.match(html, /没有需要调整的内容/);
  assert.doesNotMatch(html, /<fieldset|org-review-section|type="checkbox"|没有共同短语|暂不归类/);
});

test('papers nothing could be proposed for are listed, and the review does not claim that nothing needs doing', () => {
  const ui = fixture();
  const html = ui.suggestionsHTML({ fingerprint: 'f', groups: [], merges: [], moves: [], pending_keys: ['p1', 'p2'], scope: 'x', profile: {} }, key => ({ title: key === 'p1' ? 'Survey <of> Embodied AI' : key }));
  assert.doesNotMatch(html, /没有需要调整的内容/);
  assert.match(html, /没有可调整的内容/);
  assert.match(html, /还没有归类的论文/);
  assert.match(html, /Survey &lt;of&gt; Embodied AI/);
  assert.doesNotMatch(html, /<fieldset|type="checkbox"/);          // nothing to tick: it is a to-do for the person, not a proposal
});

test('a possible match is marked and not ticked, merges show each copy, moves can be dismissed on purpose', () => {
  const ui = fixture();
  const preview = reviewPreview();
  preview.groups.push({ id: 'maybe-1', name: 'Embodied Intelligence', keys: ['p7'], parent: null, reason: '标题或摘要里有「embodied」，是类别「Embodied Intelligence」的一部分（可能相关，请核对）', kind: 'add', target: 'd2', weak: true, color: '#123456' });
  preview.merges[0].copies = [{ id: 'd1', papers: 4, children: 1 }, { id: 'd2', papers: 2, children: 0 }];
  const html = ui.suggestionsHTML(preview);
  const weak = html.slice(html.indexOf('is-weak'), html.indexOf('</fieldset>', html.indexOf('is-weak')));
  assert.match(weak, /可能相关/);
  assert.doesNotMatch(weak.slice(0, weak.indexOf('aria-label')), /checked/);          // its box is not ticked
  assert.match(weak, /data-member="p7" checked/);                                   // its papers are ticked, so ticking the category is enough to apply it
  assert.match(html, /4 篇、1 个子类/);
  assert.match(html, /data-move-dismiss/);
  assert.doesNotMatch(html, /没勾选“调整”也没勾选“保持现状”的建议，下次还会出现|原类别如果因此没有任何论文，会一并删除|没勾选的新增分类、归入和合并，下次检查时还会再出现/);   // the standing notes are gone
});

test('an old preview without merges or moves still renders', () => {
  const ui = fixture();
  const html = ui.suggestionsHTML({ fingerprint: 'f', groups: [{ id: 'g', name: 'A', keys: ['p1'], parent: null, reason: 'r' }], profile: {} });
  assert.match(html, /新增分类/);
  assert.doesNotMatch(html, /合并重复分类|建议调整归属/);
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
  assert.match(source, /<span class="org-undo-slot" data-undo-slot><\/span><button data-action="suggest"[^>]*>/);
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

test('the camera never starts from a paper that is not drawn (collapsed category, removed paper)', () => {
  const ui = fixture();
  const data = { directions: [{ id: 'd1', name: 'Models', rank: 0 }, { id: 'd2', name: 'Other', rank: 1 }],
    items: [{ key: 'hidden', title: 'Hidden', directions: ['d1'] }, { key: 'shown', title: 'Shown', directions: ['d2'] }],
    collapsed: ['d1'], positions: {}, revision: 1, drafts: [] };
  const nodes = ui.networkElements(data, null).filter(e => !e.data.source);
  assert.deepEqual([...nodes.map(n => n.data.key)], ['shown']);                // the paper being read is under a collapsed category
  assert.equal(ui.graphOrigin(nodes, 'hidden'), 'paper:shown');             // fall back to a node that exists
  assert.equal(ui.graphOrigin(nodes, 'shown'), 'paper:shown');
  assert.equal(ui.graphOrigin(nodes, 'removed-from-library'), 'paper:shown');
  assert.equal(ui.graphOrigin(nodes, null), 'paper:shown');
  assert.equal(ui.graphOrigin([], 'hidden'), undefined);                    // an empty graph has no origin, and the caller guards it
});

test('every library row has a labelled detail button that opens the shared detail pane, again after it was closed', async () => {
  const ui = fixture(); ui.accept(snapshot());
  let listHtml = '';
  ui.S.root = { querySelector: (selector) => ({ set innerHTML(v) { if (selector === '.org-list') listHtml = v; }, get innerHTML() { return ''; }, indeterminate: false, hidden: false, classList: { toggle() {} } }) };
  ui.renderList();
  assert.match(listHtml, /data-action="detail" data-key="paper:one"[^>]*>详情<\/button>/);
  assert.match(listHtml, /data-action="read" data-key="paper:one"/);       // the title still opens the PDF
  assert.ok(!/open-detail/.test(listHtml));                                  // there is one detail, not a second bigger one
  assert.ok(!/org-icon[^>]*pencil/.test(listHtml));                          // and no icon-only duplicate of the same button
  // the click handlers (no DOM here): the row button selects the paper for the shared pane, and the pane's × only clears the selection
  const source = fs.readFileSync(path.join(__dirname, '../app/static/organization.js'), 'utf8');
  assert.match(source, /case 'detail': S\.key = b\.dataset\.key; S\.navigationToken\+\+; renderDetail\(\);/);
  assert.match(source, /case 'detail-close': S\.navigationToken\+\+; S\.key = null;/);
  assert.ok(!/openDetail/.test(source));                                      // the library never calls the Today drawer
});

// ---- view scope (project tabs) and graph isolation (the shared tree stays one; only what is shown changes)
const scopedSnapshot = () => ({
  directions: [{ id: 'd1', name: 'Models', rank: 0 }, { id: 'd2', name: 'Robots', rank: 1 }, { id: 'd3', name: 'Empty', rank: 2 }, { id: 'd4', name: 'Child', rank: 3, parent_id: 'd1' }],
  projects: [{ id: 'p1', name: 'World' }, { id: 'p2', name: 'Embodied' }],
  items: [
    { key: 'a', title: 'A', directions: ['d1'], projects: ['p1'] },
    { key: 'b', title: 'B', directions: ['d1', 'd2'], projects: ['p1', 'p2'] },
    { key: 'c', title: 'C', directions: ['d2'], projects: ['p2'] },
    { key: 'd', title: 'D', directions: [], projects: ['p2'] },
    { key: 'e', title: 'E', directions: [], projects: [] }],
  positions: {}, revision: 1, drafts: [] });

test('a project tab shows that project\'s papers, the all tab shows everything, and a paper nobody saved shows in all only', () => {
  const ui = fixture(), snap = scopedSnapshot();
  assert.deepEqual([...ui.scopeItems(snap, 'p1').map(p => p.key)], ['a', 'b']);
  assert.deepEqual([...ui.scopeItems(snap, 'p2').map(p => p.key)], ['b', 'c', 'd']);
  assert.deepEqual([...ui.scopeItems(snap, 'all').map(p => p.key)], ['a', 'b', 'c', 'd', 'e']);
});

test('the tabs are all-projects plus one per project, the current project first, each with its paper count', () => {
  const ui = fixture(), snap = scopedSnapshot();
  const tabs = JSON.parse(JSON.stringify(ui.projectTabs(snap, 'p2', 'p2').map(t => [t.id, t.count, t.active, !!t.current])));
  assert.deepEqual(tabs, [['all', 5, false, false], ['p2', 3, true, true], ['p1', 2, false, false]]);
});

test('category stats count papers in scope and anywhere, include sub-categories, and mark a category shared by projects', () => {
  const ui = fixture(), snap = scopedSnapshot();
  const models = ui.categoryStats('d1', snap, 'p1');
  assert.deepEqual([models.all, models.inScope, models.cross], [2, 2, true]);
  assert.deepEqual({ ...models.perProject }, { p1: 2, p2: 1 });
  const robots = ui.categoryStats('d2', snap, 'p1');
  assert.deepEqual([robots.all, robots.inScope], [2, 1]);
  const empty = ui.categoryStats('d3', snap, 'p1');
  assert.deepEqual([empty.all, empty.inScope, empty.cross], [0, 0, false]);
});

test('categories holding only other projects\' papers are hidden in a project tab, with their sub-categories; empty and selected ones stay', () => {
  const ui = fixture(), snap = scopedSnapshot();
  snap.items = snap.items.filter(p => p.key !== 'b');                       // now Robots holds only p2's paper
  assert.deepEqual([...ui.otherProjectCategories(snap, 'p1', '*')], ['d2']);
  assert.deepEqual([...ui.otherProjectCategories(snap, 'p1', 'd2')], []);   // the selected category stays
  assert.deepEqual([...ui.otherProjectCategories(snap, 'all', '*')], []);
  assert.ok(![...ui.otherProjectCategories(snap, 'p1', '*')].includes('d3'));   // a category nobody uses yet is not "other"
  // a child of a hidden category is hidden with it, an empty child included, so no child floats without its parent
  snap.directions.push({ id: 'd5', name: 'Grandchild', rank: 4, parent_id: 'd2' });
  assert.deepEqual([...ui.otherProjectCategories(snap, 'p1', '*')].sort(), ['d2', 'd5']);
});

test('project tags: the tab\'s project solid and the others as "also in"; in all, every project; an unowned paper says so', () => {
  const ui = fixture(), snap = scopedSnapshot();
  const b = snap.items[1];
  const inProject = ui.projectTags(b, snap, 'p1', 'p1');
  assert.match(inProject, /is-current[^>]*><span data-no-i18n>World</);
  assert.match(inProject, /也在：<span data-no-i18n>Embodied</);
  const all = ui.projectTags(b, snap, 'all', 'p1');
  assert.match(all, /is-current[^>]*><span data-no-i18n>World</); assert.match(all, /is-other[^>]*><span data-no-i18n>Embodied</);
  assert.match(ui.projectTags(snap.items[4], snap, 'all', 'p1'), /未归项目/);
});

test('project names and categories are escaped everywhere the new view writes them', () => {
  const ui = fixture(), snap = scopedSnapshot();
  snap.projects[0].name = '"><img src=x onerror=alert(1)>';
  const tags = ui.projectTags(snap.items[1], snap, 'all', 'p1');
  assert.ok(!tags.includes('<img src=x'), tags);
  ui.accept(snap); ui.S.scope = 'p1';
  const sidebar = ui.sidebarHTML();
  assert.ok(!sidebar.includes('<img src=x'), 'sidebar');
  assert.match(sidebar, /role="tab"[^>]*data-scope="p1"/);
  assert.match(sidebar, /data-scope="all"/);
});

test('the sidebar has the project panel above the directory, counts follow the tab, and a note counts the hidden categories', () => {
  const ui = fixture(), snap = scopedSnapshot();
  snap.items = snap.items.filter(p => p.key !== 'b');
  ui.accept(snap); ui.S.scope = 'p1';
  const html = ui.sidebarHTML();
  assert.ok(html.indexOf('org-projects-panel') < html.indexOf('org-directory-title'));
  assert.match(html, /aria-selected="true"[^>]*data-scope="p1"/);
  assert.doesNotMatch(html, /另有 1 个类别只在其他项目/);
  assert.doesNotMatch(html, /data-id="d2"/);                                // Robots only holds p2's paper
  ui.S.scope = 'all';
  const all = ui.sidebarHTML();
  assert.match(all, /data-id="d2"/);
  assert.doesNotMatch(all, /只在其他项目/);
});

test('picking a project tab changes the view only: no request, no saved layout, no change to the shared state', async () => {
  const calls = [];
  const ui = fixture(async (...args) => { calls.push(args); return {}; });
  ui.accept(scopedSnapshot());
  const before = JSON.stringify(ui.S.snapshot);
  ui.S.scope = 'all'; ui.S.filter = 'd2'; ui.S.focus = 'category'; ui.S.key = 'c';
  ui.S.root = { querySelector: () => ({ set innerHTML(v) {}, get innerHTML() { return ''; }, indeterminate: false, classList: { toggle() {} }, setAttribute() {} }) };
  await ui.handle('project-tab', { dataset: { scope: 'p1' } });
  assert.deepEqual(calls, []);                                               // nothing was sent to the server
  assert.equal(JSON.stringify(ui.S.snapshot), before);
  assert.deepEqual([ui.S.scope, ui.S.filter, ui.S.focus, ui.S.key], ['p1', '*', 'all', null]);   // c is not p1's paper
  assert.equal(ui.S.selected.size, 0);
});

test('graph isolation removes papers outside the choice (it does not dim them)', () => {
  const ui = fixture(), snap = scopedSnapshot();
  const rel = { edges: [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }] };
  const keys = o => [...ui.graphItems(snap, rel, { scope: 'all', ...o }).map(p => p.key)];
  assert.deepEqual(keys({ mode: 'all', filter: '*' }), ['a', 'b', 'c', 'd', 'e']);
  assert.deepEqual(keys({ mode: 'category', filter: 'd1' }), ['a', 'b']);
  assert.deepEqual(keys({ mode: 'category', filter: 'd2' }), ['b', 'c']);
  assert.deepEqual(keys({ mode: 'category', filter: '' }), ['d', 'e']);
  assert.deepEqual(keys({ mode: 'paper', key: 'a', hops: 1 }), ['a', 'b']);
  assert.deepEqual(keys({ mode: 'paper', key: 'a', hops: 2 }), ['a', 'b', 'c']);
  assert.deepEqual(keys({ mode: 'paper', key: 'd', hops: 2 }), ['d']);
  assert.deepEqual([...ui.graphItems(snap, rel, { scope: 'p1', mode: 'paper', key: 'c', hops: 2 }).map(p => p.key)], ['a', 'b']);   // c is not p1's: the tab wins
});

test('a shared category links papers that have no similarity edge, and a category selection includes its sub-categories', () => {
  const ui = fixture(), snap = scopedSnapshot();
  snap.items.push({ key: 'f', title: 'F', directions: ['d4'], projects: ['p1'] }, { key: 'g', title: 'G', directions: ['d2'], projects: ['p1'] });
  const keys = o => [...ui.graphItems(snap, { edges: [] }, { scope: 'all', ...o }).map(p => p.key)];
  assert.deepEqual(keys({ mode: 'category', filter: 'd1' }), ['a', 'b', 'f']);
  assert.deepEqual(keys({ mode: 'paper', key: 'c', hops: 1 }), ['b', 'c', 'g']);
  assert.deepEqual(keys({ mode: 'paper', key: 'a', hops: 1 }), ['a', 'b']);
});

test('switching project forgets selection, filter, focus and relations, and starts on the new current project\'s tab', () => {
  const ui = fixture();
  ui.S.snapshot = scopedSnapshot(); ui.S.filter = 'd1'; ui.S.key = 'a'; ui.S.focus = 'paper2'; ui.S.relations = { edges: [] }; ui.S.selected.add('a'); ui.S.scope = 'all'; ui.S.query = 'x';
  ui.reset();
  assert.deepEqual([ui.S.filter, ui.S.key, ui.S.focus, ui.S.relations, ui.S.selected.size, ui.S.query, ui.S.snapshot.items.length], ['*', null, 'all', null, 0, '', 0]);
  assert.equal(ui.S.scope, 'all');   // no current project in this fixture: all
});

test('a project that was deleted falls back to the all tab when the data arrives', () => {
  const ui = fixture(); ui.S.scope = 'gone';
  ui.accept(scopedSnapshot());
  assert.equal(ui.S.scope, 'all');
});

test('positions placed only to draw a partial view are not saved or captured; positions the person set are kept', () => {
  const ui = fixture();
  ui.accept(scopedSnapshot());
  ui.S.transient = new Set(['paper:a']);
  const node = (id, x) => ({ id: () => id, isParent: () => false, position: () => ({ x, y: 0 }) });
  ui.S.cy = { nodes: () => ({ forEach: fn => [node('paper:a', 1), node('paper:b', 2)].forEach(fn) }) };
  ui.S.validNodes = new Set(['paper:a', 'paper:b']); ui.S.renderedSignature = ui.graphSignature(ui.S.snapshot); ui.S.positions = {};
  ui.capturePositions();
  assert.deepEqual(Object.keys(ui.S.positions), ['paper:b']);
});

test('switching between library and graph only restyles the two view tabs, never the project tabs', () => {
  const ui = fixture();
  const seen = [];
  const make = (cls) => ({ dataset: { action: cls }, setAttribute: (k, v) => seen.push([cls, k, v]), classList: { toggle() {} } });
  ui.S.mode = 'graph';
  ui.S.cy = null;
  ui.S.root = { querySelector: () => ({ hidden: false }), querySelectorAll: (selector) => selector === '.org-tabs [role=tab]' ? [make('library'), make('graph')] : [make('project-tab')] };
  ui.setMode();
  assert.deepEqual(seen.map(x => x[0]), ['library', 'graph']);
});

test('the detail pane shows the AI summary with its labels, escaped, and nothing when the paper has none', () => {
  const ui = fixture();
  const html = ui.aiSummaryHTML({ one_liner: 'Evaluates <b>agents</b>', why_relevant: 'Matches "world models"', caution: 'Preprint' });
  assert.match(html, /AI 速览/);
  assert.match(html, /相关：.*Matches &quot;world models&quot;/);
  assert.match(html, /注意：.*Preprint/);
  assert.ok(!html.includes('<b>agents</b>') && html.includes('&lt;b&gt;agents&lt;/b&gt;'));
  assert.equal(ui.aiSummaryHTML(null), '');
  assert.equal(ui.aiSummaryHTML({}), '');
  assert.ok(!/注意：/.test(ui.aiSummaryHTML({ one_liner: 'x', why_relevant: 'y' })));
  assert.ok(!/ · /.test(ui.aiSummaryHTML({ one_liner: 'x', caution: 'only caution' })));   // no dangling separator
});

test('the reading button icon is visible in both modes', () => {
  const css = fs.readFileSync(path.join(__dirname, '../app/static/organization.css'), 'utf8');
  assert.match(css, /\.org-detail \.org-reading-tools button \.org-icon \{ filter:invert\(1\); \}/);
  assert.match(css, /html\[data-mode="dark"\] \.org-detail \.org-reading-tools button \.org-icon \{ filter:none; \}/);
});


function routeBox() {
  const box = { hidden: true, innerHTML: '', classList: { toggle() {} } };
  const container = { innerHTML: '', title: '', setAttribute() {}, isConnected: true };
  const hint = { textContent: '' };
  const pick = (selector) => selector === '[data-view-seg]' ? box : selector === '.org-graph-wrap' ? { classList: box.classList } : selector === '.org-graph' ? container : selector === '.org-graph-hint' ? hint : selector === '[data-focus-seg]' ? { hidden: false, innerHTML: '' } : selector === '.org-graph-legend' ? { hidden: true, innerHTML: '' } : null;
  return { box, container, hint, root: { querySelector: pick, querySelectorAll: () => [] } };
}

test('the second graph view is offered only on a project tab whose project has a learning map', () => {
  const ui = fixture(), dom = routeBox();
  ui.S.root = dom.root;
  ui.S.snapshot = snapshot({ route_projects: ['p1'], projects: [{ id: 'p1', name: 'A' }, { id: 'p2', name: 'B' }] });
  ui.S.scope = 'all'; ui.renderViewSeg();
  assert.equal(dom.box.hidden, true);
  assert.equal(ui.routeAvailable(), false);
  ui.S.scope = 'p2'; ui.renderViewSeg();
  assert.equal(dom.box.hidden, true);   // a project without a map
  ui.S.scope = 'p1'; ui.renderViewSeg();
  assert.equal(dom.box.hidden, false);
  assert.match(dom.box.innerHTML, /data-view="papers"/);
  assert.match(dom.box.innerHTML, /data-view="route"/);
  assert.match(dom.box.innerHTML, /aria-checked="true"[^>]*data-action="graph-view" data-view="papers"/);
});

test('leaving the project tab, or a project losing its map, puts the paper graph back', () => {
  const ui = fixture(), dom = routeBox();
  ui.S.root = dom.root;
  ui.S.snapshot = snapshot({ route_projects: ['p1'], projects: [{ id: 'p1', name: 'A' }] });
  ui.S.scope = 'p1'; ui.S.graphView = 'route';
  ui.renderViewSeg();
  assert.equal(ui.S.graphView, 'route');
  ui.S.scope = 'all'; ui.renderViewSeg();
  assert.equal(ui.S.graphView, 'papers');
  ui.S.scope = 'p1'; ui.S.graphView = 'route'; ui.S.snapshot = snapshot({ route_projects: [] });
  ui.renderViewSeg();
  assert.equal(ui.S.graphView, 'papers');
});

test('the view switch changes only the view: no request that saves, no layout touched', async () => {
  const calls = [];
  const ui = fixture(async (url, body) => { calls.push([url, body]); return { available: false, reason: 'no_route', project_id: 'p1' }; });
  const dom = routeBox();
  ui.S.root = dom.root; ui.S.mode = 'graph';
  ui.S.snapshot = snapshot({ route_projects: ['p1'], projects: [{ id: 'p1', name: 'A' }] });
  ui.S.scope = 'p1'; ui.S.positions = { 'paper:one': { x: 1, y: 2 } };
  ui.setCytoscape(() => ({}));
  await ui.handle('graph-view', { dataset: { view: 'route' } });
  await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(ui.S.graphView, 'route');
  assert.deepEqual(calls.map(c => [c[0], c[1].action, c[1].project_id]), [['/api/organization', 'route-detail', 'p1']]);
  assert.deepEqual(JSON.parse(JSON.stringify(ui.S.positions)), { 'paper:one': { x: 1, y: 2 } });
  assert.match(dom.container.innerHTML, /还没有学习图|图谱组件未加载/);
});

test('a failed read of the learning map is shown as text, never as markup', async () => {
  const ui = fixture(async () => { throw new Error('<img src=x onerror=alert(1)>'); });
  const dom = routeBox();
  ui.S.root = dom.root; ui.S.mode = 'graph';
  ui.S.snapshot = snapshot({ route_projects: ['p1'] });
  ui.S.scope = 'p1'; ui.S.graphView = 'route';
  ui.setCytoscape(() => ({}));
  await ui.renderRouteGraph();
  assert.ok(!dom.container.innerHTML.includes('<img'));
  assert.match(dom.container.innerHTML, /&lt;img/);
});

test('a new snapshot makes the second view read the map again', () => {
  const ui = fixture();
  ui.S.routeDetail = { scope: 'p1', data: { available: true } };
  ui.accept(snapshot());
  assert.equal(ui.S.routeDetail, null);
});

test('the second view\'s style is accepted by cytoscape and styles units by status and edges by kind', () => {
  const ui = fixture();
  const D = require('../app/static/route-detail.js');
  const built = JSON.parse(JSON.stringify(D.layout({ available: true, units: [
      { id: 'a', name: 'Basics', level: 1, status: 'satisfied', state: 'active' }, { id: 'b', name: 'Next', level: 2, status: 'locked', state: 'proposed', side: true }],
    prereqs: [{ from: 'a', to: 'b', state: 'proposed' }], papers: [{ key: 'p', title: 'Paper' }, { key: 'q', title: 'Other' }],
    matches: [{ paper: 'p', unit: 'a', rank: 0, terms: ['x'] }, { paper: 'p', unit: 'b', rank: 1, terms: ['y'] }], unmatched: ['q'] }, { edges: [{ source: 'p', target: 'q', weight: 0.5 }] })));
  const elements = [...built.nodes.map(n => ({ data: { id: n.id, kind: n.kind, label: n.label, status: n.status, side: n.side }, position: { x: n.x, y: n.y } })),
    ...built.edges.map(e => ({ data: { id: e.id, source: e.source, target: e.target, kind: e.kind, rank: e.rank, proposed: e.proposed, weight: e.weight } }))];
  const cy = ui.createGraph(elements);
  assert.equal(cy.nodes().length, built.nodes.length);
  ui.S.cy = null;
  const styled = ui.createGraph(elements);   // headless, no style: only checks the elements are valid
  assert.ok(styled);
  const vm2 = require('node:vm');
  assert.doesNotThrow(() => cy.style(ui.routeStyle()));
  assert.equal(cy.nodes('[kind = "unit"][status = "satisfied"]').length, 1);
  assert.equal(cy.edges('[kind = "matched_to"]').length, 2);
  assert.equal(cy.edges('[kind = "prerequisite"][?proposed]').length, 1);
});

test('a slow read of the learning map never draws over the paper graph the person switched back to', async () => {
  let release;
  const ui = fixture(() => new Promise(resolve => { release = resolve; }));
  const dom = routeBox();
  ui.S.root = dom.root; ui.S.mode = 'graph';
  ui.S.snapshot = snapshot({ route_projects: ['p1'], projects: [{ id: 'p1', name: 'A' }] });
  ui.S.scope = 'p1'; ui.S.graphView = 'route';
  let created = 0;
  ui.setCytoscape(() => { created += 1; return { on() {}, nodes: () => ({}), zoom: () => 1, destroy() {}, resize() {}, animate() {} }; });
  const pending = ui.renderRouteGraph();
  ui.S.graphView = 'papers';          // the person clicks "论文关系" while the request is out
  ui.S.routeToken++;                  // what renderGraph does first on every render
  dom.container.innerHTML = '<paper-graph>';
  release({ available: true, units: [{ id: 'a', name: 'A', level: 1, status: 'unlocked', state: 'active' }], prereqs: [], papers: [], matches: [], unmatched: [], omitted: 0 });
  await pending;
  assert.equal(created, 0);
  assert.equal(dom.container.innerHTML, '<paper-graph>');
  assert.equal(ui.S.rcy, null);
});

test('a slow read for one project is dropped when another project tab was chosen', async () => {
  let release;
  const ui = fixture(() => new Promise(resolve => { release = resolve; }));
  const dom = routeBox();
  ui.S.root = dom.root; ui.S.mode = 'graph';
  ui.S.snapshot = snapshot({ route_projects: ['p1', 'p2'], projects: [{ id: 'p1', name: 'A' }, { id: 'p2', name: 'B' }] });
  ui.S.scope = 'p1'; ui.S.graphView = 'route';
  ui.setCytoscape(() => { throw new Error('must not draw'); });
  const pending = ui.renderRouteGraph();
  ui.S.scope = 'p2';
  release({ available: true, units: [], prereqs: [], papers: [], matches: [], unmatched: [], omitted: 0 });
  await pending;
  assert.equal(ui.S.routeDetail, null);
});


function routeGraphFixture() {
  const ui = fixture();
  ui.S.snapshot = snapshot({ route_projects: ['p1'], projects: [{ id: 'p1', name: 'A' }],
    directions: [{ id: 'd1', name: 'Models', rank: 0 }, { id: 'd2', name: 'Other', rank: 1 }],
    items: [{ key: 'one', title: 'One', directions: ['d1'], projects: ['p1'] }, { key: 'two', title: 'Two', directions: ['d2'], projects: ['p1'] }, { key: 'free', title: 'Free', directions: ['d2'], projects: ['p1'] }] });
  ui.S.scope = 'p1'; ui.S.graphView = 'route'; ui.S.mode = 'graph';
  ui.S.rcy = ui.createGraph([
    { data: { id: 'ru:a', kind: 'unit', label: 'A' }, position: { x: 0, y: 0 } }, { data: { id: 'ru:b', kind: 'unit', label: 'B' }, position: { x: 0, y: 200 } },
    { data: { id: 'rp:one', kind: 'paper', key: 'one', label: 'One' }, position: { x: 0, y: 100 } },
    { data: { id: 'rp:two', kind: 'paper', key: 'two', label: 'Two' }, position: { x: 100, y: 300 } },
    { data: { id: 'rp:free', kind: 'paper', key: 'free', label: 'Free' }, position: { x: 300, y: 500 } },
    { data: { id: 'e1', source: 'rp:one', target: 'ru:a', kind: 'matched_to' } }, { data: { id: 'e2', source: 'rp:two', target: 'ru:b', kind: 'matched_to' } },
    { data: { id: 'e3', source: 'ru:a', target: 'ru:b', kind: 'prerequisite' } }]);
  const base = routeBox().root;
  // every other part of the page (sidebar, list, detail pane) is a stand-in that accepts whatever is drawn into it
  const stub = () => new Proxy(function () {}, { get: (t, k) => (k === Symbol.toPrimitive ? () => '' : k === 'length' ? 0 : k === 'then' ? undefined : k in t ? t[k] : stub()), set: () => true, apply: () => stub() });
  ui.setDocument(stub());
  ui.S.root = { querySelector: (selector) => base.querySelector(selector) || stub(), querySelectorAll: () => [], classList: { contains: () => false, toggle() {}, add() {} } };
  return ui;
}
const dimmed = (ui) => JSON.parse(JSON.stringify(ui.S.rcy.elements('.org-dim').map(e => e.id()).sort()));

test('picking a paper in the left list focuses it in the learning-map view: it and its neighbours stay, the rest dims', () => {
  const ui = routeGraphFixture();
  ui.focusRoute('rp:one');
  assert.equal(ui.S.routeFocus, 'rp:one');
  assert.deepEqual(dimmed(ui), ['e2', 'e3', 'rp:free', 'rp:two', 'ru:b']);
  assert.ok(ui.S.rcy.getElementById('rp:one').hasClass('org-current'));
});

test('focusing nothing clears the dimming again', () => {
  const ui = routeGraphFixture();
  ui.focusRoute('rp:one'); ui.focusRoute(null);
  assert.deepEqual(dimmed(ui), []);
  assert.equal(ui.S.routeFocus, null);
});

test('picking a category in the left list keeps that category\'s papers and the units they fit, and dims the rest', () => {
  const ui = routeGraphFixture();
  ui.S.filter = 'd2';
  ui.focusRouteCategory();
  assert.deepEqual(dimmed(ui), ['e1', 'e3', 'rp:one', 'ru:a']);
  ui.S.filter = '*';
  ui.focusRouteCategory();
  assert.deepEqual(dimmed(ui), []);
});

test('a category with nothing drawn says so instead of dimming everything silently', () => {
  const ui = routeGraphFixture();
  ui.S.snapshot.directions.push({ id: 'd3', name: 'Empty', rank: 2 });
  ui.S.filter = 'd3';
  ui.focusRouteCategory();
  assert.deepEqual(dimmed(ui), []);
  assert.match(ui.S.notice, /没有/);
});

test('in the learning-map view the left list focuses the node instead of redrawing the paper graph', async () => {
  const ui = routeGraphFixture();
  await ui.handle('graph-paper-focus', { dataset: { key: 'one' } });
  assert.equal(ui.S.key, 'one');
  assert.equal(ui.S.routeFocus, 'rp:one');
  assert.equal(ui.S.focus, 'all');   // the paper graph's own focus mode is not touched
  await ui.handle('filter', { dataset: { id: 'd2' } });
  assert.deepEqual(dimmed(ui), ['e1', 'e3', 'rp:one', 'ru:a']);
});

test('actual navigation handler keeps the paper identity in both views and refuses another project', async () => {
  const ui = routeGraphFixture();
  await ui.handle('graph-navigate', {dataset:{key:'one', project:'p1', view:'papers'}});
  assert.equal(ui.S.key, 'one'); assert.equal(ui.S.graphFocus, 'paper:one');
  assert.equal(ui.S.graphView, 'papers'); assert.equal(ui.S.focus, 'paper1');
  await ui.handle('graph-navigate', {dataset:{key:'one', project:'p1', view:'route', unit:'a'}});
  assert.equal(ui.S.key, 'one'); assert.equal(ui.S.routeFocus, 'ru:a');
  assert.equal(ui.S.graphView, 'route'); assert.equal(ui.S.focus, 'all');
  await assert.rejects(ui.handle('graph-navigate', {dataset:{key:'one', project:'p2', view:'route'}}), /尚未收藏/);
  assert.equal(ui.S.scope, 'p1');
});

test('reset drops a pending route read even when the same project is reopened', async () => {
  let release;
  const ui = fixture(() => new Promise(r => {release=r;})), dom=routeBox();
  ui.S.root=dom.root; ui.S.mode='graph'; ui.S.graphView='route'; ui.S.scope='p1';
  ui.setProject('p1'); ui.S.snapshot=snapshot({route_projects:['p1']});
  ui.setCytoscape(() => {throw new Error('stale graph');});
  const pending=ui.renderRouteGraph(); ui.reset();
  ui.S.mode='graph'; ui.S.graphView='route'; ui.S.scope='p1'; dom.container.innerHTML='fresh';
  release({available:true,units:[],papers:[],matches:[]}); await pending;
  assert.equal(dom.container.innerHTML,'fresh'); assert.equal(ui.S.routeDetail,null);
});

test('reset ignores a pending snapshot without replacing the new project data', async () => {
  let release;
  const ui=fixture(() => new Promise(r=>{release=r;}));
  const pending=ui.refresh(); await new Promise(r=>setImmediate(r));
  ui.reset(); ui.accept(snapshot({items:[{key:'new',title:'New',directions:[]}]}));
  release(snapshot()); await pending;
  assert.equal(ui.S.snapshot.items[0].key,'new');
});

test('relations from an earlier project reset are ignored even for an identical corpus', async () => {
  let release;
  const ui=fixture(() => new Promise(r=>{release=r;})); ui.accept(snapshot());
  const pending=ui.loadRelations(); ui.reset(); ui.accept(snapshot());
  release({job:{state:'done',result:{relations:{edges:[{source:'a',target:'b'}]}}}});
  await pending; assert.equal(ui.S.relations,null); assert.equal(ui.S.relationsLoading,false);
});

test('paper context cache is scoped to the project and drops pre-reset replies', async () => {
  const replies=[];
  const ui=fixture((url,body)=>new Promise(resolve=>replies.push({body,resolve})));
  ui.S.scope='p1'; ui.contextFor('one');
  ui.reset(); ui.S.scope='p2'; ui.contextFor('one');
  replies[0].resolve({context:{project_id:'p1',categories:[],units:[],map_available:false,saved_in_project:false}});
  await new Promise(r=>setImmediate(r));
  assert.equal(ui.S.contexts.has(JSON.stringify(['p1','one'])),false);
  replies[1].resolve({context:{project_id:'p2',categories:[],units:[],map_available:false,saved_in_project:false}});
  await new Promise(r=>setImmediate(r));
  assert.equal(typeof ui.S.contexts.get(JSON.stringify(['p2','one'])), 'string');   // the p2 reply is cached under its own project
});

test('explicit unmatched entry names papers and carries no note about omitted matches', () => {
  const ui=fixture(), box={hidden:true,innerHTML:''};
  ui.S.root={querySelector:()=>box};ui.S.graphView='route';ui.S.snapshot=snapshot();
  ui.renderUnmatched({available:true,unmatched:['paper:one'],unmatched_total:150});
  assert.equal(box.hidden,false); assert.match(box.innerHTML,/150 篇/);
  assert.match(box.innerHTML,/data-key="paper:one"/);assert.doesNotMatch(box.innerHTML,/列表搜索后定位/);
  ui.S.graphView='papers';ui.renderUnmatched(); assert.equal(box.hidden,true);
});

test('a new Map request clears unmatched papers before a failed or unavailable project reply',async()=>{
  for(const result of [new Error('P2 error'),{available:false}]) {
    let release;
    const ui=fixture(()=>new Promise((resolve,reject)=>{release=()=>result instanceof Error?reject(result):resolve(result);}));
    const dom=routeBox(), box={hidden:false,innerHTML:'old P1 paper'};
    ui.S.root={querySelector:s=>s==='[data-route-unmatched]'?box:dom.root.querySelector(s)};
    ui.S.mode='graph';ui.S.graphView='route';ui.S.scope='p2';ui.setCytoscape(()=>({}));
    const pending=ui.renderRouteGraph();assert.equal(box.hidden,true);assert.equal(box.innerHTML,'');
    release();await pending;assert.equal(box.hidden,true);assert.equal(box.innerHTML,'');
  }
});

test('public pending navigation yields to a newer paper selection, closing or leaving the view',async()=>{
  for(const action of ['detail','detail-close','leave']) {
    const ui=routeGraphFixture();let release;
    ui.publicUI.open=()=>new Promise(r=>{release=r;});
    const pending=ui.publicUI.navigate({key:'one',project:'p1',view:'papers'});
    if(action==='leave')ui.publicUI.cancelNavigation();
    else await ui.handle(action,{dataset:{key:'two'}});
    const key=ui.S.key,view=ui.S.graphView;
    release(true);await pending;
    assert.equal(ui.S.key,key,action);assert.equal(ui.S.graphView,view,action);
  }
});

test('pending learning-match details are retained without an automatic loop and explicit retry refreshes them',async()=>{
  const ui=routeGraphFixture();ui.S.key='one';ui.S.mode='library';let calls=0;
  ui.setAPI(async()=>({context:{project_id:'p1',categories:[],map_available:true,saved_in_project:true,route_enabled:true,
    matching_status:++calls===1?'pending':'ready',units:calls===1?[]:[{id:'a',name:'New match'}]}}));
  ui.contextFor('one');await new Promise(r=>setImmediate(r));
  assert.equal(calls,1);assert.match(ui.S.contexts.get(JSON.stringify(['p1','one'])),/learning-match-retry/);
  await ui.handle('learning-match-retry',{dataset:{project:'p1',key:'one'}});await new Promise(r=>setImmediate(r));
  assert.equal(calls,2);assert.match(ui.S.contexts.get(JSON.stringify(['p1','one'])),/New match/);
});

test('a pending graph cache is reread on reopening instead of freezing uncertain matches',async()=>{
  let calls=0;
  const ui=fixture(async()=>{calls++;return {available:false};}),dom=routeBox();
  ui.S.root=dom.root;ui.S.mode='graph';ui.S.graphView='route';ui.S.scope='p1';ui.setCytoscape(()=>({}));
  ui.S.routeDetail={scope:'p1',focusKey:null,data:{available:true,pending_total:1}};
  await ui.renderRouteGraph();assert.equal(calls,1);
});

test('ready learning matches can be explicitly reread after adding body text',async()=>{
  const ui=routeGraphFixture();ui.S.key='one';ui.S.mode='library';let calls=0;
  ui.setAPI(async()=>({context:{project_id:'p1',categories:[],map_available:true,saved_in_project:true,route_enabled:true,
    matching_status:'ready',units:++calls===1?[]:[{id:'a',name:'Body-derived match'}]}}));
  ui.contextFor('one');await new Promise(r=>setImmediate(r));
  assert.doesNotMatch(ui.S.contexts.get(JSON.stringify(['p1','one'])),/没有对应的学习单元/);   // nothing to show is not narrated
  assert.match(ui.S.contexts.get(JSON.stringify(['p1','one'])),/learning-match-retry/);
  await ui.handle('learning-match-retry',{dataset:{project:'p1',key:'one'}});await new Promise(r=>setImmediate(r));
  assert.equal(calls,2);assert.match(ui.S.contexts.get(JSON.stringify(['p1','one'])),/Body-derived match/);
});

test('fulltext invalidation clears ready graph and context caches and rejects older replies',async()=>{
  const ui=routeGraphFixture();ui.S.key='one';ui.S.mode='library';let release;
  ui.S.root.hidden=true;
  ui.setAPI(()=>new Promise(r=>{release=r;}));
  ui.contextFor('one');
  ui.S.routeDetail={scope:'p1',focusKey:'one',data:{available:true,pending_total:0}};
  const token=ui.S.routeToken;
  await ui.publicUI.invalidateLearning('one');
  assert.equal(ui.S.routeDetail,null);assert.equal(ui.S.contexts.size,0);assert.ok(ui.S.routeToken>token);
  release({context:{project_id:'p1',categories:[],map_available:true,units:[]}});await new Promise(r=>setImmediate(r));
  assert.equal(ui.S.contexts.size,0);
});

test('late fulltext saving restarts the visible current-project graph instead of abandoning its read',async()=>{
  const replies=[];
  const ui=fixture(()=>new Promise(resolve=>replies.push(resolve))),dom=routeBox();
  ui.S.snapshot=snapshot({route_projects:['new-project'],projects:[{id:'new-project',name:'New'}]});
  ui.S.root=dom.root;ui.S.mode='graph';ui.S.graphView='route';ui.S.scope='new-project';ui.setCytoscape(()=>({}));
  const earlier=ui.renderRouteGraph();assert.equal(replies.length,1);
  const replacement=ui.publicUI.invalidateLearning('old-project-paper');assert.equal(replies.length,2);
  replies[0]({available:true});await earlier;
  replies[1]({available:false});await replacement;
  assert.doesNotMatch(dom.container.innerHTML,/正在读取学习图/);
  assert.match(dom.container.innerHTML,/没有学习图/);assert.equal(ui.S.scope,'new-project');
});

test('graph retry remains available for deferred progress with no pending saved papers',()=>{
  const ui=fixture(),box={hidden:true,innerHTML:''};ui.S.root={querySelector:()=>box};ui.S.graphView='route';
  ui.renderUnmatched({available:true,unmatched:[],pending:[],pending_total:0,progress_verification_deferred:true});
  assert.match(box.innerHTML,/route-verification-retry/);assert.match(box.innerHTML,/重新匹配/);
});

function aiPlanFixture() {
  // Unclassified paper fresh-1 is filed under a new category; the junk label is deleted with its holder re-homed;
  // a duplicate label is merged; one classified paper is moved.
  const plan = {category_scope:['d1','junk','dup'], scoped:true,
    categories:[{id:'d1',action:'keep',reason:'ok'},{id:'junk',action:'delete',reason:'<script>bad</script>'},{id:'dup',action:'merge',target:'d1',reason:'同义'}],
    new_categories:[{id:'new',name:'世界模型',parent_id:null,reason:'标题依据'}],
    papers:[{key:'fresh-1',categories:['new'],reason:'明确方向'},{key:'held',categories:['d1'],reason:'重新归类'},{key:'moved',categories:['new'],reason:'更准'}]};
  const units = [
    {id:'p:fresh-1',kind:'paper',section:'classify',key:'fresh-1',from:[],to:['new'],fallback:false,reason:'<img src=x>',requires:[]},
    {id:'c:dup',kind:'category',section:'adjust',category:'dup',action:'merge',target:'d1',reason:'同义',papers:2,requires:[]},
    {id:'c:junk',kind:'category',section:'adjust',category:'junk',action:'delete',reason:'<script>bad</script>',papers:1,rehome:[{key:'held',to:['d1']}],requires:[]},
    {id:'p:moved',kind:'paper',section:'rehome',key:'moved',from:['d1'],to:['new'],fallback:false,reason:'更准',requires:[]}];
  return {scope:'project-a', ai_plan:plan, ai_units:units};
}
function planUI() {
  const ui = fixture();
  ui.accept(snapshot({directions:[{id:'d1',name:'Models',rank:0},{id:'junk',name:'Junk',rank:1},{id:'dup',name:'Dup',rank:2}],
    projects:[{id:'project-a',name:'项目甲'}],
    items:[{key:'fresh-1',title:'Fresh paper',directions:[]},{key:'held',title:'Held paper',directions:['junk']},{key:'moved',title:'Moved paper',directions:['d1']}]}));
  return ui;
}

test('AI review lists unclassified papers first, then label changes, then moves, each unit with its own checkbox', () => {
  const html = planUI().suggestionsHTML(aiPlanFixture());
  const at = text => html.indexOf(text);
  assert.ok(at('归类未分类论文') > 0 && at('归类未分类论文') < at('调整现有分类') && at('调整现有分类') < at('重新归类'));
  for (const id of ['p:fresh-1','c:dup','c:junk','p:moved']) assert.match(html, new RegExp(`data-unit="${id}" checked`));
  assert.equal((html.match(/data-unit=/g) || []).length, 4, 'one checkbox per unit and nothing else');
  assert.match(html, /data-group/);                                  // the unclassified papers are grouped by where they go
  assert.match(html, /<em class="org-maybe">新建<\/em>/);              // the category that does not exist yet says so
  assert.doesNotMatch(html, /data-ai-plan/);                         // the old all-or-nothing switch is gone
  assert.match(html, /data-select-all-units/); assert.match(html, /data-select-no-units/); assert.match(html, /data-ai-summary/);
});

test('AI review carries no scope note and escapes model text', () => {
  const html = planUI().suggestionsHTML(aiPlanFixture());
  assert.doesNotMatch(html, /范围：|与其他项目共用的类别只接收论文|左边目录里显示/);
  assert.match(html, /&lt;script&gt;/); assert.match(html, /&lt;img src=x&gt;/);
  assert.doesNotMatch(html, /<script>/); assert.doesNotMatch(html, /<img src=x>/);
  const all = planUI().suggestionsHTML({...aiPlanFixture(), scope:null});
  assert.doesNotMatch(all, /范围：|与其他项目共用/);
});

test('deleting a label shows the papers it moves, and a merge carries no explanatory count line', () => {
  const html = planUI().suggestionsHTML(aiPlanFixture());
  assert.match(html, /1 篇论文改归别的类别/); assert.match(html, /Held paper/);
  assert.doesNotMatch(html, /2 篇论文随之并入/);
});

test('papers the model could not judge are marked as placed in 其他 for now', () => {
  const preview = aiPlanFixture();
  preview.ai_units = [{...preview.ai_units[0], fallback:true, to:['new']}];
  const html = planUI().suggestionsHTML(preview);
  assert.match(html, /依据不足，暂放/);
});

test('a plan with nothing to change says so briefly and shows no checkbox', () => {
  const html = planUI().suggestionsHTML({...aiPlanFixture(), ai_units:[]});
  assert.match(html, /没有需要调整的内容/); assert.doesNotMatch(html, /所有论文都已有类别/); assert.doesNotMatch(html, /data-unit=/);
});

test('a plan without selectable units is refused instead of being applied as a whole', () => {
  const html = planUI().suggestionsHTML({ai_plan:{categories:[],new_categories:[],papers:[]}});
  assert.match(html, /整理方案不完整/); assert.doesNotMatch(html, /data-unit=/);
});

test('ticking a deletion pulls in the deletion of its sub-categories, and unticking one unticks what needs it', () => {
  const ui = planUI();
  const units = [{id:'c:parent',section:'adjust',requires:['c:child']},{id:'c:child',section:'adjust',requires:[]},
    {id:'p:a',section:'classify',requires:[]},{id:'p:b',section:'classify',requires:[]},{id:'p:m',section:'rehome',requires:[]}];
  const sel = ui.planSelection(units);
  assert.deepEqual([...sel.all()].sort(), ['c:child','c:parent','p:a','p:b','p:m']);
  let chosen = sel.toggle(new Set(), 'c:parent', true);
  assert.deepEqual([...chosen].sort(), ['c:child','c:parent']);
  chosen = sel.toggle(chosen, 'c:child', false);
  assert.deepEqual([...chosen], [], 'the parent cannot stay without its child');
  assert.equal(sel.unclassifiedLeft(new Set(['p:a'])), 1);
  assert.equal(sel.unclassifiedLeft(sel.all()), 0);
});

test('the dialog keeps the count and the apply button in step with the ticks, with no unclassified warning', () => {
  const ui = planUI(), preview = aiPlanFixture();
  const listeners = {}, summary = {textContent:''}, submit = {textContent:'', disabled:false};
  const boxes = preview.ai_units.map(u => ({dataset:{unit:u.id}, checked:true, matches: s => s === '[data-unit]', closest: () => ({querySelectorAll: () => groupBoxes})}));
  const groupBoxes = [boxes[0]];
  const group = {checked:true, indeterminate:false, matches: s => s === '[data-group]', closest: () => ({querySelectorAll: () => groupBoxes})};
  const buttons = {'[data-select-all-units]':{}, '[data-select-no-units]':{}};
  const root = {querySelectorAll: s => s === '[data-unit]' ? boxes : s === '[data-group]' ? [group] : [],
    querySelector: s => s === '[data-ai-summary]' ? summary : s === '[type=submit]' ? submit : buttons[s] ? Object.assign(buttons[s], {addEventListener:(k,fn)=>{buttons[s].fn=fn;}}) : null,
    addEventListener: (kind, fn) => { listeners[kind] = fn; }};
  ui.wireAIPlan(root, preview.ai_units);
  assert.equal(summary.textContent, '已选 4 / 4 项');
  assert.equal(submit.textContent, '应用所选（4 项）');
  boxes[0].checked = false; listeners.change({target: boxes[0]});   // untick the only unclassified paper
  assert.equal(summary.textContent, '已选 3 / 4 项');
  assert.equal(group.checked, false);
  buttons['[data-select-no-units]'].fn();
  assert.equal(summary.textContent, '已选 0 / 4 项');
  assert.equal(submit.disabled, true);
  buttons['[data-select-all-units]'].fn();
  assert.equal(submit.disabled, false); assert.ok(boxes.every(b => b.checked));
  group.checked = false; listeners.change({target: group});          // untick the whole group at once
  assert.equal(boxes[0].checked, false); assert.ok(boxes.slice(1).every(b => b.checked));
});

test('the project name is never echoed unescaped into the review', () => {
  const ui = planUI();
  ui.S.snapshot.projects[0].name = '<img src=x onerror=alert(1)>';
  const html = ui.suggestionsHTML(aiPlanFixture());
  assert.doesNotMatch(html, /<img src=x/);
});

test('a new category shows where it will sit and why the model wants it', () => {
  const preview = aiPlanFixture();
  preview.ai_plan.new_categories[0].parent_id = 'd1';
  const html = planUI().suggestionsHTML(preview);
  assert.match(html, /Models › 世界模型/);                      // the path, not just the bare name
  assert.match(html, /标题依据/);                                // the model's reason for creating it
  const moved = html.slice(html.indexOf('<h4>重新归类</h4>'));
  assert.ok(html.includes('<h4>重新归类</h4>'));
  assert.match(moved, /Models › 世界模型/);                      // and in the move list too
});

test('every unit checkbox has an accessible name', () => {
  const html = planUI().suggestionsHTML(aiPlanFixture());
  for (const id of ['c:dup', 'c:junk']) assert.match(html, new RegExp(`data-unit="${id}" checked [^>]*aria-label="[^"]+"`));
  assert.match(html, /data-group checked aria-label="选择归入「[^"]*世界模型[^"]*」的论文"/);
  assert.equal((html.match(/aria-label="选择这一组"/g) || []).length, 0, 'groups are named after where they go');
});

test('the left directory hides exactly the categories the review leaves out (shared cases with the server rule)', () => {
  const ui = fixture(), cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/scope_directory_cases.json'), 'utf8'));
  for (const c of cases) {
    const items = Object.entries(c.papers).filter(([, p]) => p.saved).map(([key, p]) => ({key, title: key, projects: p.projects, directions: p.directions}));
    const snap = {directions: c.directions.map(d => ({...d, name: d.id})), items, projects: [], positions: {}, revision: 1, drafts: []};
    const hidden = ui.otherProjectCategories(snap, c.scope, '*');
    const shown = c.directions.map(d => d.id).filter(id => !hidden.has(id));
    assert.deepEqual(shown, c.shown, c.name);
  }
});
