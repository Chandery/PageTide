'use strict';
// The project-creation page after the owner's report: the assistant's question goes to the question box (not to the
// search-phrase box), the goal is not shown twice, the language choice is sent with every AI turn, a restored quick
// draft can retry, and with the beta learning map off nothing on the page names the map. Production source is
// executed in a vm with the DOM, network and model replaced; no real model or library is touched.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const SOURCE = process.env.PAGETIDE_CREATION_JS || path.join(__dirname, '../app/static/project-creation.js');
const source = () => fs.readFileSync(SOURCE, 'utf8');
function slice(from, to) {
  const s = source(), start = s.indexOf(from);
  assert.ok(start >= 0, `production source has ${from}`);
  const end = s.indexOf(to, start + from.length);
  assert.ok(end > start, `production source has ${to} after ${from}`);
  return s.slice(start, end);
}
const plain = value => JSON.parse(JSON.stringify(value));
const node = () => ({hidden: false, disabled: false, innerHTML: '', textContent: '', value: '', children: [], scrollTop: 0, scrollHeight: 0,
  replaceChildren(...items) { this.children = items; }, appendChild(item) { this.children.push(item); }, remove() {}});

test('the assistant question shows in the question box and the search phrases stay in the search box', () => {
  const nodes = new Map(), at = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  const context = vm.createContext({$: at, $$: () => [], esc: v => String(v), bubble: () => node(), guidedBusy: false,
    document: {createElement: () => ({setAttribute() {}})}, guidedTurn() {},
    session: {transcript: [{role: 'user', content: '目标'}], draft: {next_question: '你想先读论文还是复现？', summary: '机器人规划',
      choices: ['读论文', '复现'], search_queries: ['world model planning'], keywords: ['world model']}}});
  vm.runInContext(slice('function renderChat(live) {', '\nfunction showPending(') + ';globalThis.render = renderChat;', context);
  context.render(null);
  const question = at('#guideQuestion');
  assert.match(question.innerHTML, /你想先读论文还是复现/);
  assert.match(question.innerHTML, /机器人规划/);
  assert.equal(question.hidden, false);
  // The draft panel: queries come from search_queries only, never from next_question.
  const slots = new Map(), part = name => { if (!slots.has(name)) slots.set(name, {value: '', innerHTML: '', querySelectorAll: () => []}); return slots.get(name); };
  const review = vm.createContext({part, keywords: {set() {}}, syncPath() {}, addPathItem() {}, Brief: {set() {}}, bindPathConcepts() {},
    map: {graph: null, briefDirty: false, discarded: true, userEdited: false}, candidates: {size: 0}, addCandidates() {}, refresh() {},
    renderMap() {}, MAX_PATH: 8});
  vm.runInContext(slice('  function setDraft(d, options = {}) {', '\n  function addCandidates(') + ';globalThis.set = setDraft;', review);
  review.set(plain(context.session.draft));
  assert.equal(part('queries').value, 'world model planning');
  assert.ok(!part('queries').value.includes('你想先读论文'));
  context.session.draft.next_question = '';
  context.session.draft.summary = '';
  context.render(null);
  assert.equal(question.hidden, true);   // nothing to ask or confirm: the box is gone
});

function guidedFixture(transcript) {
  const calls = {bubbles: [], posts: [], appended: []};
  const chat = {...node(), appendChild(item) { calls.appended.push(item); }};
  const message = node();
  const context = vm.createContext({
    guidedBusy: false, setComposer() {}, AI_WAIT: 90, showPending() {}, renderChat() {}, retryable: () => false,
    $: id => id === '#guideChat' ? chat : id === '#guideMessage' ? message : node(),
    $$: () => [], guidedAct: {start() {}, stop() {}, fail() {}},
    bubble: entry => { calls.bubbles.push(plain(entry)); return {entry}; },
    session: {id: 's1', transcript, draft: {revision: 3}},
    review: {draft: () => ({keywords: ['a'], search_queries: [], learning_path: []}), setDraft() {}},
    policyEditor: {selected: () => ['zh', 'en']},
    post: async (url, body) => { calls.posts.push({url, body: plain(body)}); return {session: {transcript, draft: {}}}; }});
  vm.runInContext(slice('async function guidedTurn(', '\nfunction openGuidedWorkspace') + ';globalThis.turn = guidedTurn;', context);
  return {context, calls};
}

test('the opening goal is not drawn a second time on the first guided turn, and later messages still are', async () => {
  const goal = '我想了解世界模型';
  const first = guidedFixture([{role: 'user', content: goal}]);
  await first.context.turn({message: goal});
  assert.deepEqual(first.calls.bubbles.filter(b => b.role === 'user'), [], 'the goal bubble is already on screen');
  assert.equal(first.calls.posts.length, 1);
  assert.equal(first.calls.posts[0].body.message, goal);
  const later = guidedFixture([{role: 'user', content: goal}, {role: 'assistant', content: '好', mode: 'ai'}]);
  await later.context.turn({message: '只做仿真'});
  assert.deepEqual(later.calls.bubbles.filter(b => b.role === 'user').map(b => b.content), ['只做仿真']);
  const again = guidedFixture([{role: 'user', content: goal}, {role: 'assistant', content: '好', mode: 'ai'}]);
  await again.context.turn({message: goal});   // the same words typed again later are a new message
  assert.deepEqual(again.calls.bubbles.filter(b => b.role === 'user').map(b => b.content), [goal]);
});

test('every guided turn tells the server which paper languages are ticked', async () => {
  const f = guidedFixture([{role: 'user', content: '目标'}]);
  await f.context.turn({message: '目标'});
  assert.deepEqual(f.calls.posts[0].body.languages, ['zh', 'en']);
  assert.equal(f.calls.posts[0].body.base, 3, 'the draft revision the page lists are based on travels with the turn');
  assert.deepEqual(f.calls.posts[0].body.draft.keywords, ['a']);
});

test('quick creation sends the language choice with its one AI call', async () => {
  const posts = [];
  const context = vm.createContext({
    quickAct: {start() {}, stop() {}, fail() {}}, AI_WAIT: 90, $: () => node(),
    review: {setBusy() {}, setDraft() {}, root: node(), draft: () => ({keywords: ['mine'], search_queries: ['my query'], learning_path: []})},
    session: {id: 's1', draft: {goal: '目标', revision: 2}, transcript: []}, renderQuickNote() {}, discardSession() {}, stopQuick() {},
    policyEditor: {selected: () => ['en']},
    post: async (url, body) => { posts.push(plain(body)); return {session: {id: 's1', draft: {goal: '目标'}, transcript: [{role: 'assistant', content: 'x'}]}}; }});
  vm.runInContext(slice('async function quickTurn(', "\n$('#quickGo').onclick") + ';globalThis.turn = quickTurn;', context);
  assert.equal(await context.turn(), true);
  assert.deepEqual(posts[0].languages, ['en']);
  assert.equal(posts[0].base, 2);
  assert.equal(posts[0].message, '目标');
  assert.deepEqual(posts[0].draft, {keywords: ['mine'], search_queries: ['my query'], learning_path: []},
    'the person\'s edits travel with the quick call and with its retry');
});

test('quick creation shows the session draft in the review before its first AI call, so that call sends no stale empty lists', async () => {
  const order = [], nodes = new Map(), at = id => { if (!nodes.has(id)) nodes.set(id, {...node(), value: 'x'}); return nodes.get(id); };
  const context = vm.createContext({
    $: at, validateCreationStart: () => true, window: {PTDialogs: {notice() {}}}, session: null, finalize() {},
    makeReview: () => ({root: node(), setDraft: () => order.push('setDraft'), search: async () => order.push('search')}),
    quickAct: {start() {}, stop() {}}, stopQuick() {},
    createSession: async () => { order.push('createSession'); context.session = {draft: {}}; },
    quickTurn: async () => { order.push('quickTurn'); return true; }});
  vm.runInContext(slice("$('#quickGo').onclick = async () => {", '\n/* ------------------------------------------------------------------ guided creation'), context);
  await at('#quickGo').onclick();
  assert.deepEqual(order, ['createSession', 'setDraft', 'quickTurn', 'search']);
});

function resumeFixture(saved) {
  const calls = [];
  const nodes = new Map(), at = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  const context = vm.createContext({
    SESSION_KEY: 'k', finalize() {}, localStorage: {getItem: () => 'sid', removeItem() {}}, api: async () => ({session: saved}),
    setMode: m => calls.push(['mode', m]), $: at, makeReview: () => ({setDraft: d => calls.push(['draft', d.search_queries])}),
    renderQuickNote: () => calls.push(['note']), renderQuickIdle: () => calls.push(['idle']), renderChat: () => calls.push(['chat']),
    openGuidedWorkspace: () => { context.review = {setDraft: d => calls.push(['draft', d.search_queries])}; },
    session: null, review: null});
  vm.runInContext(slice('async function resume() {', '\nresume();') + ';globalThis.run = resume;', context);
  return {context, calls};
}

test('a restored quick draft the AI never answered offers the one call again instead of a bare form', async () => {
  const unanswered = resumeFixture({status: 'draft', draft: {creation_mode: 'quick', search_queries: []}, transcript: [{role: 'user', content: '目标'}]});
  await unanswered.context.run();
  assert.deepEqual(unanswered.calls.map(c => c[0]), ['mode', 'draft', 'idle']);
  assert.deepEqual(unanswered.calls.find(c => c[0] === 'draft')[1], [], 'no search phrase was invented');
  const answered = resumeFixture({status: 'draft', draft: {creation_mode: 'quick', search_queries: ['world model']},
    transcript: [{role: 'user', content: '目标'}, {role: 'assistant', content: '好', mode: 'ai'}]});
  await answered.context.run();
  assert.deepEqual(answered.calls.map(c => c[0]), ['mode', 'draft', 'note']);
  const idle = slice('function renderQuickIdle() {', '\nasync function quickTurn(');
  const note = node(), retry = node(), tries = [];
  const context = vm.createContext({$: id => id === '#quickNote' ? note : retry, review: {search() { tries.push('search'); }},
    quickTurn: async arg => { tries.push(plain(arg)); return true; }});
  vm.runInContext(idle + ';globalThis.show = renderQuickIdle;', context);
  context.show();
  assert.equal(note.hidden, false);
  assert.match(note.innerHTML, /AI 还没有整理这个目标/);
  await retry.onclick();
  assert.deepEqual(tries, [{retry: false}, 'search'], 'a fresh turn (not a retry of a local answer), then the search');
});

test('with no keyword the review shows one quiet line at the keywords, and not while the AI works', () => {
  const input = {tag: 'input', disabled: false}, slots = new Map();
  const part = name => { if (!slots.has(name)) slots.set(name, {controls: name === 'keywords' ? [input] : [], hidden: true}); return slots.get(name); };
  let count = 0;
  const context = vm.createContext({part, $$: (selector, root) => root.controls || [], keywords: {get: () => Array(count).fill('k')},
    selected: new Set(), MAX_PATH: 8, searching: false, busy: false, map: {generating: false, checking: false}});
  vm.runInContext(slice('  function refresh() {', '\n  /* ---- learning map:') + ';globalThis.refreshReview = refresh;', context);
  context.refreshReview();
  assert.equal(part('keywordHint').hidden, false);
  assert.equal(part('create').disabled, true);
  assert.equal(input.disabled, false, 'the person can type a keyword');
  count = 1; context.refreshReview();
  assert.equal(part('keywordHint').hidden, true);
  assert.equal(part('create').disabled, false);
  count = 0; context.busy = true; context.refreshReview();
  assert.equal(part('keywordHint').hidden, true);
  const html = fs.readFileSync(path.join(__dirname, '../app/static/project_creation.html'), 'utf8');
  assert.match(html, /data-role="keywordHint"[^>]*hidden>添加至少一个关键词后才能创建。/);
});

// What a person sees with the beta learning map off: elements marked data-route-beta are hidden by the server's style.
function visibleWithMapOff(html) {
  const text = html.replace(/<!--[\s\S]*?-->/g, '').replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '');
  let out = '', hidden = 0;
  const stack = [];
  for (const token of text.match(/<\/?[a-zA-Z][^>]*>|[^<]+/g) || []) {
    if (token[0] !== '<') { if (!hidden) out += token; continue; }
    const name = token.match(/^<\/?([a-zA-Z0-9]+)/)[1].toLowerCase();
    if (['input', 'br', 'img', 'meta', 'link', 'hr'].includes(name) || token.endsWith('/>')) { if (!hidden) out += ' ' + token; continue; }
    if (token[1] === '/') { const top = stack.pop(); if (top) hidden -= 1; continue; }
    const skip = /data-route-beta(?![-\w])/.test(token);
    stack.push(skip); if (skip) hidden += 1;
    if (!hidden) out += ' ' + token;
  }
  return out;
}

test('with the beta learning map off, nothing the creation page shows names the map, the path or concepts', () => {
  const html = fs.readFileSync(path.join(__dirname, '../app/static/project_creation.html'), 'utf8');
  const seen = visibleWithMapOff(html);
  assert.match(seen, /关键词/);
  assert.match(seen, /检索式/);
  assert.doesNotMatch(seen, /学习图|学习路径|概念|学习阶段/);
  assert.match(html, /data-role="mapBlock"[^>]*data-route-beta/);   // and it is there once the beta switch is on
  assert.match(html, /data-role="pathBlock"[^>]*data-route-beta/);
  // Sanity check of the helper: hidden elements really are skipped, off-variants really are kept.
  assert.doesNotMatch(visibleWithMapOff('<p data-route-beta>学习图 <b>x</b></p><p data-route-beta-off>关键词</p>'), /学习图/);
  assert.match(visibleWithMapOff('<p data-route-beta>学习图 <b>x</b></p><p data-route-beta-off>关键词</p>'), /关键词/);
});

test('creating with no candidate asks first: nothing is searched unless chosen, and creating anyway stays possible', async () => {
  const s = source();
  const start = s.indexOf("part('create').onclick = async () => {"), end = s.indexOf('\n  refresh();\n  return', start);
  const slots = new Map(), part = name => { if (!slots.has(name)) slots.set(name, {querySelectorAll: () => [], checked: false, scrollIntoView() {}}); return slots.get(name); };
  let created = 0, searched = 0, asked = '', answer = null, offered = [];
  const candidates = {size: 0};
  const context = vm.createContext({part, candidates, searching: false, searchedOnce: false, search: async () => { searched++; },
    window: {PTDialogs: {choose: async (message, buttons) => { asked = message; offered = buttons.map(b => b.value); return answer; }}},
    $$: () => [], map: {graph: null, discarded: true, generating: false, checking: false, editing: null},
    R: {check: () => ({ok: true})}, busy: false, readCreationPolicy: () => ({allowed_languages: ['zh']}), refresh() {}, mapNotice() {},
    createAct: {start() {}, stop() {}, fail() {}}, mapPayload: () => null, draft: () => ({keywords: ['语法教学']}), selected: new Set(),
    onCreate: async () => { created++; }, readCreationBrief: () => ({goal: 'g'})});
  vm.runInContext(s.slice(start, end), context);
  await part('create').onclick();                              // dismissed: nothing happens, nothing is searched
  assert.match(asked, /还没有候选论文/);
  assert.equal(JSON.stringify(offered), JSON.stringify([null, 'create', 'search']));
  assert.equal(searched, 0); assert.equal(created, 0);
  answer = 'search'; context.busy = false;
  await part('create').onclick();                              // the person chose to search: search, do not create
  assert.equal(searched, 1); assert.equal(created, 0);
  context.searchedOnce = true; answer = 'back'; context.busy = false;
  await part('create').onclick();                              // searched and found nothing: say so plainly
  assert.match(asked, /没有找到任何论文/); assert.equal(created, 0);
  answer = 'create'; context.busy = false;
  await part('create').onclick();
  assert.equal(created, 1);                                    // they may still create, knowingly
  candidates.size = 3; asked = ''; context.busy = false;
  await part('create').onclick();
  assert.equal(asked, '');                                     // papers found: no question
});
test('with the beta map off the review starts without a map, create needs none, and the draft is not marked changed', async () => {
  const s = source();
  assert.match(s, /discarded: window\.PAGETIDE_ROUTE_BETA === false/);
  const start = s.indexOf("part('create').onclick = async () => {"), end = s.indexOf('\n  refresh();\n  return', start);
  assert.ok(start >= 0 && end > start);
  const slots = new Map(), part = name => { if (!slots.has(name)) slots.set(name, {querySelectorAll: () => [], checked: false}); return slots.get(name); };
  let received;
  const context = vm.createContext({part, candidates: {size: 1}, searching: false, $$: () => [], map: {graph: null, discarded: true, generating: false, checking: false, editing: null},
    R: {check: () => ({ok: true})}, busy: false, readCreationPolicy: () => ({allowed_languages: ['zh']}), refresh() {}, mapNotice() {},
    createAct: {start() {}, stop() {}, fail() {}}, mapPayload: () => null, draft: () => ({keywords: ['world model']}), selected: new Set(),
    onCreate: async payload => { received = plain(payload); }, readCreationBrief: () => ({goal: 'g'})});
  vm.runInContext(s.slice(start, end), context);
  await part('create').onclick();
  assert.equal(received.route, null);
  assert.deepEqual(received.draft.keywords, ['world model']);
});

test('the finalize request carries the ticked languages and no discipline', async () => {
  const s = source();
  let sent;
  const context = vm.createContext({SESSION_KEY: 'k', policyEditor: {disabled() {}}, readCreationPolicy: () => ({allowed_languages: ['zh', 'en']}),
    session: {id: 's'}, post: async (url, body) => { sent = plain(body); return {project_id: 'p'}; }, localStorage: {removeItem() {}},
    location: {}, afterCreate: () => '/x', creationLeaving: false});
  vm.runInContext(s.slice(s.indexOf('async function finalize('), s.indexOf('\nasync function createSession(')) + ';globalThis.finish = finalize;', context);
  await context.finish({draft: {}, selectedKeys: [], route: null});
  assert.deepEqual(sent.language_policy, {allowed_languages: ['zh', 'en']});
  assert.equal('discipline' in sent.language_policy, false);
});

test('manual creation without seeds asks before searching, and a keyword still being typed counts', () => {
  const s = source();
  const body = s.slice(s.indexOf("$('#manualCreate').onclick"), s.indexOf("$('#manualName').addEventListener('input', manualRefresh);"));
  assert.match(body, /PTDialogs\.choose\(/);
  assert.doesNotMatch(body, /await searchQueries\(\);\n\s*const message/);            // never a search before the question
  assert.match(body, /choice === 'search'\) \{.*await searchQueries\(\); return; \}/); // searching never also creates
  assert.match(s, /seedKeywords\.get\(\)\.length \+ \(\$\('#manualKeywords input'\)\.value\.trim\(\) \? 1 : 0\)/);
  assert.match(s, /\$\('#manualKeywords input'\)\.addEventListener\('input', manualRefresh\)/);
});

test('candidate cards have no 展开摘要 button, only the link to the original', () => {
  const s = source();
  const card = s.slice(s.indexOf('function candidateCard('), s.indexOf('const SEARCH_PROBLEMS'));
  assert.doesNotMatch(card, /展开摘要|收起摘要/);
  assert.match(card, /打开原文/);
});

test('manual creation shows found papers as the same checkbox cards as AI creation, kept in step with the seed list', () => {
  const s = source();
  const hit = s.slice(s.indexOf('function seedHit('), s.indexOf('function syncSeedHits('));
  assert.match(hit, /candidateCard\(paper, seedTaken\(paper\.key\)/);
  assert.match(hit, /if \(!on\) \{ seedRemoveByKey\(key\); return; \}/);
  assert.doesNotMatch(hit, />添加<\/button>/);
  assert.match(s.slice(s.indexOf('function manualRefresh('), s.indexOf("$('#manualCreate').onclick")), /syncSeedHits\(\)/);
  assert.match(fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'project_creation.html'), 'utf8'), /class="cands" id="seedSearchList"/);
});
