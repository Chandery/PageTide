'use strict';
// The interface language layer: Chinese source text -> the English pack, by exact key or pattern.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const SOURCE = fs.readFileSync(path.join(__dirname, '../app/static/i18n.js'), 'utf8');
const PACK = JSON.parse(fs.readFileSync(path.join(__dirname, '../app/static/i18n/en-US.json'), 'utf8')).messages;

test('graph navigation and distinct paper-purpose labels have English UI translations', () => {
  const {i18n}=load('en-US',PACK);
  for(const line of ['分类与学习用途','收藏类别','对应学习单元','定位学习单元','对应关系来自标题与摘要检索词，不会改动收藏类别或掌握状态。','Route 已关闭；学习图仍保留。','本次推荐用途','不在本项目当前推荐批次','在论文关系图中定位','在学习图中定位','收藏到这个项目后，可在图中定位论文。','没有对应的学习单元','部分论文未画出，可在列表搜索后定位。']) assert.doesNotMatch(i18n.translate(line),/[㐀-鿿]/,line);
});

test('current body matching and pending verification labels translate in full',()=>{
  const {i18n}=load('en-US',PACK);
  for(const line of ['正文待核验，学习匹配未确定','对应关系使用标题与可用摘要；缺摘要时使用当前版本的正文。不改动类别或掌握。','3 篇正文待核验','标题或当前版本正文用到了检索词：epitaxy','重新核验学习匹配','论文正文或 PDF 版本已变化，请重新核验学习匹配']) assert.doesNotMatch(i18n.translate(line),/[㐀-鿿]/,line);
});

test('goal status and following labels translate complete rendered sentences', () => {
  const {i18n} = load('en-US', PACK);
  for (const line of ['当前目标已完成 · 目标范围已满足 3 / 3 个概念',
    '目标或前置关系需要检查 · 目标范围已满足 0 / 2 个概念', '持续关注',
    '持续关注不改变掌握状态；满足这个概念后才推荐新进展。',
    '学习图有未保存的修改，目标状态在保存后重新计算。']) {
    assert.doesNotMatch(i18n.translate(line), /[㐀-鿿]/, line);
  }
});

// A minimal page: the DOM walk finds no element nodes here; translate() is what is tested.
function load(lang, messages) {
  const shown = [];
  const context = vm.createContext({
    PDH_I18N: { lang, messages },
    document: { documentElement: {}, addEventListener() {} },
    MutationObserver: class { observe() {} },
    alert: (message) => shown.push(message),
  });
  context.window = context;
  vm.runInContext(SOURCE, context);
  return { i18n: context.PDHi18n, context, shown };
}

const messages = {
  '论文库': 'Library',
  '今日推荐': "Today's picks",
  '{0} 篇推荐': ['{0} recommendation', '{0} recommendations'],
  '「{0}」下': 'under “{0}”',
  '有用 {0}': 'Useful {0}',
  '收藏 {0}': 'Saved {0}',
  '已删除 {0}': 'Deleted {0}',
  '默认项目': 'Default project',
  '今日 {0} / {1} token': 'Today {0} / {1} tokens',
};

test('Chinese mode passes every string through and carries no pack', () => {
  const { i18n, shown, context } = load('zh-CN', messages);
  assert.equal(i18n.lang, 'zh-CN');
  assert.equal(i18n.translate('论文库'), '论文库');
  assert.equal(i18n.t('{n} 篇', { n: 3 }), '3 篇');
  context.alert('论文库');
  assert.deepEqual(shown, ['论文库']);
  assert.deepEqual([...i18n.misses()], []);
});

test('exact keys keep the surrounding whitespace', () => {
  const { i18n } = load('en-US', messages);
  assert.equal(i18n.translate('论文库'), 'Library');
  assert.equal(i18n.translate('  今日推荐\n'), "  Today's picks\n");
  assert.equal(i18n.translate('Library'), 'Library');   // no Chinese: untouched
});

test('patterns fill values; plurals follow the first number', () => {
  const { i18n } = load('en-US', messages);
  assert.equal(i18n.translate('1 篇推荐'), '1 recommendation');
  assert.equal(i18n.translate('5 篇推荐'), '5 recommendations');
  assert.equal(i18n.translate('今日 120 / 55000 token'), 'Today 120 / 55000 tokens');
});

test('Chinese captured by a pattern is translated again', () => {
  const { i18n } = load('en-US', messages);
  assert.equal(i18n.translate('已删除 默认项目'), 'Deleted Default project');
  assert.equal(i18n.translate('「World models」下'), 'under “World models”');
});

test('a " · " list is translated part by part, all or nothing', () => {
  const { i18n } = load('en-US', messages);
  assert.equal(i18n.translate('07-10 · 有用 0 · 收藏 2'), '07-10 · Useful 0 · Saved 2');
  // One unknown part keeps the whole list Chinese and reports it once.
  assert.equal(i18n.translate('有用 0 · 未知词'), '有用 0 · 未知词');
  assert.deepEqual([...i18n.misses()], ['有用 0 · 未知词']);
});

test('unknown text stays Chinese and is listed for the audit', () => {
  const { i18n } = load('en-US', messages);
  assert.equal(i18n.translate('测试·手动'), '测试·手动');
  assert.ok([...i18n.misses()].includes('测试·手动'));
});

test('t() fills named slots after choosing the plural form', () => {
  const { i18n } = load('en-US', { '共 {n} 篇': ['{n} paper in total', '{n} papers in total'] });
  assert.equal(i18n.t('共 {n} 篇', { n: 4 }), '4 papers in total');
  assert.equal(i18n.t('共 {n} 篇', { n: 1 }), '1 paper in total');
});

// Review finding: a "{0}" part matched any text and Chinese parts were translated again,
// so words, names, notes and AI text came back half-translated ("收藏夹" -> "Saved 夹").
test('words, names and AI text are never half-translated', () => {
  const { i18n } = load('en-US', PACK);
  for (const text of ['收藏夹', '首页', '见第 3 页', '上篇', '撤销重做', '只看了第 3 页',
    '这篇论文提出了一种新的世界模型']) {
    assert.equal(i18n.translate(text), text, text);
  }
  // The label is UI; what follows it is the model's text, kept as written.
  assert.equal(i18n.translate('相关：x · 注意：只看了第 3 页'), 'Related: x · Note: 只看了第 3 页');
  assert.equal(i18n.translate('相关：这篇论文很好'), 'Related: 这篇论文很好');
  // A count slot takes numbers only, and a whole pack entry inside a key is still translated.
  assert.equal(i18n.translate('1 篇推荐'), '1 pick');
  assert.equal(i18n.translate('视觉 · 第 4 页（引用所在页）'), 'Vision · p. 4 (quoted page)');
  assert.equal(i18n.translate('世界模型（已加入）'), '世界模型 (added)');   // a project name, then UI
  // Review round 2: a part that is itself a pattern sentence is translated whole, not left Chinese.
  const toast = i18n.translate('新增 3 条（2 个查询被限流跳过）');
  assert.doesNotMatch(toast, /[㐀-鿿]/, toast);
  const removal = i18n.translate('3 个直接子类别会移到「世界模型」下。可以使用「撤销上一步」恢复。');
  assert.match(removal, /^3 direct subcategor.*世界模型.*Undo/, removal);
  assert.doesNotMatch(removal.replace('世界模型', ''), /[㐀-鿿]/, removal);
  assert.equal(toast, '3 new papers (2 queries skipped by rate limiting)');
  assert.equal(i18n.translate('新增 1 条'), '1 new paper');
  assert.equal(i18n.translate('1 个直接子类别会移到顶层目录。可以使用「撤销上一步」恢复。'),
    '1 direct subcategory will move to the top level. You can restore it with "Undo".');
  assert.equal(i18n.translate('12 条 · 2026-09-01 至 2026-10-01（UTC，不含右端）'),
    '12 records · 2026-09-01 to 2026-10-01 (UTC, end excluded)');
  // Review round 3: a nested pattern sentence still may not glue onto the key's own Chinese.
  assert.equal(i18n.translate('撤销失败：网络'), '撤销失败：网络');
  assert.equal(i18n.translate('依据当前项目画像的固定关键词：JEPA。一级类别来自这些关键词；类别内部再按标题里反复出现的短语细分。'),
    "Based on the current project's pinned keywords: JEPA. Top-level categories come from these keywords; inside each, papers are split by phrases that recur in titles.");
  assert.match(i18n.translate('依据「世界模型」画像的固定关键词：JEPA。一级类别来自这些关键词；类别内部再按标题里反复出现的短语细分。'),
    /^Based on the pinned keywords of the “世界模型” profile: JEPA\. /);
  assert.match(i18n.translate('当前项目还没有固定关键词，先按标题里反复出现的短语分组。在“画像”页固定关键词后再生成，会以它们为一级类别。'),
    /^Current project has no pinned keywords yet/);
});

test('a pattern does not glue onto neighbouring Chinese', () => {
  const { i18n } = load('en-US', { '收藏 {0}': 'Saved {0}', '撤销{0}': 'Undo{0}', '「{0}」下': 'under “{0}”' });
  assert.equal(i18n.translate('收藏夹'), '收藏夹');
  assert.equal(i18n.translate('撤销重做'), '撤销重做');
  assert.equal(i18n.translate('撤销：移动论文'), 'Undo：移动论文');
  assert.equal(i18n.translate('收藏 世界模型'), 'Saved 世界模型');   // a name after a space is kept as is
  assert.equal(i18n.translate('「强化学习」下'), 'under “强化学习”');
});

test('exact() swaps only a whole pack entry', () => {
  const { i18n } = load('en-US', PACK);
  assert.equal(i18n.exact('论文库'), PACK['论文库']);
  assert.equal(i18n.exact('收藏 3'), '收藏 3');
  assert.equal(i18n.exact('第 3 页的实验怎么设计的？'), '第 3 页的实验怎么设计的？');
});

test('dialogs are translated', () => {
  const { context, shown } = load('en-US', messages);
  context.alert('论文库');
  assert.deepEqual(shown, ['Library']);
});

test('the shipped pack translates its own keys', () => {
  const { i18n } = load('en-US', PACK);
  assert.equal(i18n.translate('论文库'), PACK['论文库']);
  assert.equal(i18n.translate('今日 0 / 55000 token'), 'Today 0 / 55000 tokens');
  assert.equal(i18n.translate('每日 $0.15'), '$0.15 per day');
  assert.deepEqual([...i18n.misses()], []);
});

const COUNTED = ['已选择 3 篇', '今日 5 篇', '没有符合的 2 篇', '共 4 篇论文已读'];
const noUnitEaten = (pack) => {
  const { i18n } = load('en-US', pack);
  return COUNTED.filter((text) => { const out = i18n.translate(text); return /[㐀-鿿]/.test(out) && !out.includes('篇'); });   // Chinese left, its unit gone
};

test('no pack entry may rewrite a sentence it does not own: text with a count and no entry keeps its unit', () => {
  assert.deepEqual(noUnitEaten(PACK), []);
});

test('the guard above does catch a pack entry that eats the unit', () => {
  assert.ok(noUnitEaten({ ...PACK, '{0} {1} 篇': '{0} {1}' }).length > 0);
});

test('language evidence and exclusion counts translate as complete UI messages',()=>{
  const {i18n}=load('en-US',PACK);
  assert.equal(i18n.translate('全文语言：中文（已核验）'),'Full-text language: Chinese (verified)');
  assert.equal(i18n.translate('全文语言未核验 · 元数据语言：en'),'Full-text language unverified · Metadata language: en');
  assert.equal(i18n.translate('语言未知 2 篇'),'Language unknown: 2 papers');
});
test('connection test and unlimited accounting translate complete status sentences',()=>{
  const {i18n}=load('en-US',PACK);
  for(const text of ['测试 AI','AI 用量记录','正在测试 AI…已等待 4 秒','AI 测试成功 · DeepSeek · mock-model · 用时 4.2 秒 · 本次 9 token','AI 测试失败：HTTP 401 · 用时 1.2 秒','本次用量未确认；预留记录保留，待核对。','今日 900 token · 含待确认预留','今日消耗 $0.003 · 本月消耗 $0.006','来源报告语言：英文（OpenAlex） · 全文语言未核验 · 题名文字与英文来源报告不一致','不设用量上限，仍记录消耗。未确认用量的预留记录仍保留，待核对。']){
    assert.doesNotMatch(i18n.translate(text),/[㐀-鿿]/,text);
  }
});

test('actual Route batch sentences and badges translate in empty, watch-only and mixed batches',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
 const helpers=html.slice(html.indexOf('function dailyButtonText'),html.indexOf('function renderRoute'));
 const {i18n,context}=load('en-US',PACK);context.state={cards:[]};
 vm.runInContext(helpers,context);
 for(const goal_status of ['learning','completed']) {
  for(const cards of [[],[{route:{kind:'watch'}}],[{route:{kind:'route'}},{route:{kind:'explore_new'}},{route:{kind:'watch'}}]]) {
   context.state.cards=cards;
   const line=context.exploreLine({goal_status});
   assert.doesNotMatch(i18n.translate(line),/[㐀-鿿]/,line);
  }
 }
 assert.doesNotMatch(i18n.translate('生成今日发现'),/[㐀-鿿]/);
 const badges=html.slice(html.indexOf('const ROUTE_KINDS'),html.indexOf('const PDF_BADGES'));
 vm.runInContext(badges+';globalThis.batchTitles=ROUTE_TITLES;',context);
 for(const kind of ['explore','explore_new','watch'])assert.doesNotMatch(i18n.translate(context.batchTitles[kind]),/[㐀-鿿]/);
});


test('growth contract disclosure and complete summaries translate into English', () => {
  const {i18n} = load('en-US', PACK);
  for (const line of ['新任务','前置缺口','已过期','可确认提议','证据较少',
    '「Example」是一个新任务提议，预览后确认才会入图',
    '「Example」是一个前置缺口提议，预览后确认才会入图',
    '「Example」是一个新分支提议，预览后确认才会入图',
    '「Example」已覆盖这项学习任务',
    '「Example」已成为学习提议，请到学习图页预览并确认',
    '提议已过期：图或有效证据发生变化，不会自动调用 AI。',
    '你明确认为有用或选作种子、还待判断的论文：',
    '点一次调用一次 AI：发送最多 3 篇有用或选定种子的标题和摘要节选、完整有界学习图的概念说明和前置目标、已有提议，不发送笔记、画像或其他项目']) {
    assert.doesNotMatch(i18n.translate(line), /[㐀-鿿]/, line);
  }
});

test('fixed brief fields, preview and attempt status translate as rendered', () => {
  const {i18n}=load('en-US',PACK);
  for (const line of ['学习目标（必填） · 最多 250 字','已知基础 · 最多 150 字','希望包含 · 最多 150 字',
    '希望排除 · 最多 150 字','结构意见 · 最多 500 字','修改预览','作为学习目标',
    '预览已生成；今天还能修改 1 次。请检查后确认。','创建草稿已生成；今天还能创建 2 次。检查并保存才生效。',
    '学习图或有效反馈已变化，草稿保留；请重新生成预览后确认。']) {
    assert.doesNotMatch(i18n.translate(line), /[㐀-鿿]/,line);
  }
});

test('whole-queue status, disclosure and busy text translate as actually rendered', () => {
 const R=require('../app/static/route-editor.js'),{i18n}=load('en-US',PACK);
 for(const out of [
  {requested:20,processed:20,pending:0,complete:true,judges_left:9},
  {requested:20,processed:9,pending:11,complete:false,judges_left:9,reason:'本次未保存全部有效判断，未完成的论文仍保留在待判断中。'},
  {requested:11,processed:11,pending:2,complete:true,judges_left:8},
  {requested:3,processed:3,pending:0,complete:true,judges_left:8,reason_code:'network',reason:'Request or billing status is unknown'},
  {requested:3,processed:3,pending:0,complete:true,judges_left:8,reason_code:'network'}
 ])assert.doesNotMatch(i18n.translate(R.judgeProgress(out).message),/[㐀-鿿]/);
 for(const line of ['判断全部待判断论文','正在判断全部…','正在判断全部 20 篇…','正在判断全部待判断论文…','正在判断全部 20 篇待判断论文…',
  '这篇你认为有用。要让 AI 判断本项目全部待判断论文的学习价值吗？',
  '点一次判断本项目全部待判断论文，自动依次分批，每批最多 3 篇；整次只计 1 次判断机会，可能有多次 AI 调用。只发送有用或选定种子的标题和摘要节选、完整有界学习图的概念说明和前置目标、已有提议，不发送笔记、画像或其他项目']){
  assert.doesNotMatch(i18n.translate(line),/[㐀-鿿]/,line);
 }
});

test('actual eligibility renderer keeps system counts translatable in separate nodes',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
 const fn=html.slice(html.indexOf('function renderEligibility('),html.indexOf('\nfunction ',html.indexOf('function renderEligibility(')+1));
 const {i18n,context}=load('en-US',PACK),note={children:[],replaceChildren(){this.children=[];},append(...nodes){this.children.push(...nodes);}};
 context.$=()=>note;context.state={currentProject:'p',projects:[{id:'p',language_policy:{status:'ready',revision:1}}]};
 context.document.createElement=()=>({children:[],textContent:'',append(...nodes){this.children.push(...nodes);}});
 vm.runInContext(fn,context);context.renderEligibility({policy_revision:1,excluded:{fixed_scope_conflict:2,language_unknown:1},examples:[]});
 assert.equal(note.children.filter(n=>typeof n==='object').length,3);
 for(const n of note.children.filter(n=>typeof n==='object'))assert.doesNotMatch(i18n.translate(n.textContent),/[㐀-鿿]/);
});
test('import PDF validation errors and undone categories translate without changing a filename',()=>{
 const {i18n,context}=load('en-US',PACK);
 const src=fs.readFileSync(path.join(__dirname,'../app/static/import.js'),'utf8');
 vm.runInContext(src.match(/const systemError = [^\n]+/)[0]+';globalThis.errorText=systemError;',context);
 assert.doesNotMatch(context.errorText('PDF 不完整或缺少有效结尾，请重新下载或选择完整文件'),/[㐀-鿿]/);
 assert.equal(context.errorText('私人论文名.pdf'),'私人论文名.pdf');
 assert.doesNotMatch(i18n.translate('已撤销这次导入的分类。论文仍在论文库里，只是回到未分类。'),/[㐀-鿿]/);
 assert.equal(i18n.translate('删除'),'Remove');
});
test('actual manual map default localizes only newly created system name',()=>{
 const {context}=load('en-US',PACK);context.map={generating:false,checking:false,graph:{concepts:[{name:'我的原名'}]}};context.busy=false;
 const actions={};context.part=key=>actions[key]??={};context.renderMap=()=>{};
 const src=fs.readFileSync(path.join(__dirname,'../app/static/project-creation.js'),'utf8');
 vm.runInContext(src.slice(src.indexOf('  const changedMap = '),src.indexOf('  const mapNotice = '))+
   src.slice(src.indexOf("  part('mapStart').onclick = "),src.indexOf("  part('mapDrop').onclick = ")),context);
 context.part('mapStart').onclick();assert.equal(context.map.graph.concepts[0].name,'First concept');
 const userName='我的原名';assert.equal(context.PDHi18n.exact(userName),userName);
});
