const test = require('node:test');
const assert = require('node:assert/strict');
const W = require('../app/static/weekly-ui.js');

const tally = (o = {}) => ({ saved: 0, positive: 0, understood: 0, negative: 0, too_hard: 0, exposed: 0, ...o });
const report = (extra = {}) => ({
  week_start: '2026-10-01T00:00:00+00:00', week_end: '2026-10-08T00:00:00+00:00', previous_start: '2026-09-24T00:00:00+00:00',
  stats: tally({ saved: 3, positive: 3, understood: 2, negative: 1 }), previous_stats: tally({ saved: 1, positive: 1 }),
  has_activity: true, comparable: true,
  keyword_changes: { rising: [{ term: 'dynamics', current: 3, previous: 0, delta: 3 }], stable: [], falling: [{ term: 'planning', current: 0, previous: 2, delta: -2 }] },
  daily: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-0${i + 1}`, weekday: (i + 3) % 7, ...tally(i === 6 ? { positive: 2, understood: 1 } : i === 2 ? { negative: 1 } : {}) })),
  directions: [
    { id: 'd1', name: 'World models / Latent', status: 'new', current: { ...tally({ positive: 2, understood: 1, saved: 2 }), papers: 3 }, previous: { ...tally(), papers: 0 }, papers: [{ key: 'a', title: 'Paper <b>A</b>', kinds: ['positive', 'saved', 'understood'] }], more: 2 },
    { id: 'd2', name: 'Vision', status: 'quiet', current: { ...tally(), papers: 0 }, previous: { ...tally({ positive: 2, saved: 2 }), papers: 2 }, papers: [], more: 0 }],
  units: { items: [{ id: 'c1', name: 'Crystal <i>basics</i>', status: 'satisfied', current: { understood: 2, positive: 1, negative: 0, too_hard: 0, papers: 2 } }, { id: 'c2', name: 'Epitaxy', status: 'locked', current: { understood: 0, positive: 0, negative: 0, too_hard: 0, papers: 0 } }],
    done: 1, total: 2, enabled: true, advanced: ['Crystal <i>basics</i>'] },
  highlights: { papers: 5, previous_papers: 2, directions: 2, positive: 3, negative: 1, judged: 4, seen: 6, seen_acted: 2, units_advanced: 1 },
  picks: [{ key: 'a', title: 'Paper <b>A</b>', published: '2026', kinds: ['saved', 'understood'], directions: ['World models'], unit: 'Crystal <i>basics</i>' }],
  ...extra });

test('every section of a full report is drawn', () => {
  const html = W.weeklyHTML(report());
  for (const marker of ['wk-hero', 'wk-kpis', 'wk-days', 'wk-dirs', 'wk-progress', 'wk-picks', 'wk-terms']) assert.match(html, new RegExp(marker), marker);
  assert.match(html, /本周涉及 2 个方向，5 篇论文/);
  assert.match(html, /论文数比上周 \+3/);
});

test('the five numbers each open their records, and show last week next to this week', () => {
  const html = W.kpis(report());
  assert.equal((html.match(/data-evidence="/g) || []).length, 5);
  assert.match(html, /data-evidence="understood" data-start="2026-10-01T00:00:00\+00:00" data-end="2026-10-08T00:00:00\+00:00"/);
  assert.match(html, /上周 1 · 变化 \+2/);
  assert.match(html, /上周 0 · 持平/);
});

test('the week is seven columns, labelled by weekday and date, and the last one is today', () => {
  const html = W.days(report());
  assert.equal((html.match(/class="wk-day[ "]/g) || []).length, 7);
  assert.equal((html.match(/is-today/g) || []).length, 1);
  assert.match(html, /周[一二三四五六日]<small>10-0\d/);
});

test('a direction shows last week and this week, its papers and a neutral status', () => {
  const html = W.directions(report());
  assert.match(html, /World models \/ Latent/);
  assert.match(html, /新出现/);
  assert.match(html, /本周没有记录/);
  assert.match(html, /上周论文 2/);
  assert.match(html, /其余 2/);
  assert.doesNotMatch(html, /下降|不感兴趣|冷淡|流失|放弃|落后/);
});

test('the directions section discloses canonical alias counting before cards or an empty result', () => {
  const message = '周报将 2 组同义类别按一个方向统计；论文库原类别与归属保留。';
  for (const extra of [{}, { directions: [] }]) {
    const html = W.directions(report({ ...extra, category_normalization: { message, merged_groups: 2 } }));
    assert.ok(html.includes(`<p class="wk-note wk-normalization">${message}</p>`));
    const result = html.indexOf(extra.directions ? '本周没有哪个方向' : '<div class="wk-dirs">');
    assert.ok(html.indexOf(message) < result);
  }
  assert.doesNotMatch(W.directions(report()), /wk-normalization/);
  assert.doesNotMatch(W.directions(report({ category_normalization: { message: '' } })), /wk-normalization/);
  assert.doesNotMatch(W.directions(report({ category_normalization: { message: { text: 'wrong type' } } })), /wk-normalization|object Object/);
});

test('category normalization disclosure treats the server message as text', () => {
  const html = W.weeklyHTML(report({ category_normalization: { message: '<img src=x onerror=1> & "details"' } }));
  assert.match(html, /&lt;img src=x onerror=1&gt; &amp; &quot;details&quot;/);
  assert.doesNotMatch(html, /<img src=x/);
});

test('titles, names and reasons are text, never markup', () => {
  const html = W.weeklyHTML(report());
  assert.ok(!html.includes('<b>A</b>') && html.includes('Paper &lt;b&gt;A&lt;/b&gt;'));
  assert.ok(!html.includes('<i>basics</i>') && html.includes('Crystal &lt;i&gt;basics&lt;/i&gt;'));
  const hostile = W.weeklyHTML(report({ directions: [{ id: 'x', name: '"><img src=x onerror=1>', status: '"><b>', current: { ...tally(), papers: 1 }, previous: { ...tally(), papers: 0 }, papers: [], more: 0 }] }));
  assert.ok(!hostile.includes('<img') && !hostile.includes('"><b>'));
});

test('the learning map section says what advanced, and that saving alone does not', () => {
  assert.match(W.units(report()), /本周有“已读懂”记录的概念/);
  assert.match(W.units(report()), /已读懂 1 \/ 2 个概念/);
  const none = report({ units: { items: [], done: 0, total: 3, enabled: true, advanced: [] } });
  assert.match(W.units(none), /收藏表示感兴趣，不推进学习进度/);
  assert.equal(W.units(report({ units: null })), '');
});

test('an empty week says so and does not read it as lost interest', () => {
  const html = W.weeklyHTML(report({ has_activity: false, comparable: false, directions: [], picks: [], daily: [], units: null, highlights: { papers: 0, previous_papers: 0, directions: 0, judged: 0, seen: 0, seen_acted: 0 } }));
  assert.match(html, /本周还没有记录/);
  assert.match(html, /没有记录不代表兴趣下降/);
  assert.match(html, /本周没有哪个方向上有/);
  assert.doesNotMatch(html, /wk-dirs/);
});

test('being shown a paper is counted as seen, not as turned down', () => {
  const html = W.exposure(report());
  assert.match(html, /露出的论文：6 篇，其中你有明确动作的：2 篇。没有动作的不代表不感兴趣/);
  assert.match(html, /有用率 75%/);
  assert.equal(W.exposure(report({ highlights: { seen: 0, judged: 0 } })), '');
  assert.match(W.exposure(report({ highlights: { seen: 0, judged: 3, positive: 2 } })), /样本还少/);
});

test('terms that rose or fell open their papers, and an unscaled week is not compared', () => {
  assert.match(W.terms(report()), /data-term="dynamics"/);
  assert.match(W.terms(report({ comparable: false })), /需要本周和上周都有记录/);
  assert.match(W.terms(report({ keyword_changes: { rising: [], stable: [], falling: [] } })), /词项与上周持平/);
});

test('saves that came without a rating still show in a direction that also has a not-relevant record', () => {
  const html = W.directions(report({ directions: [{ id: 'd', name: 'D', status: 'other', current: { ...tally({ saved: 3, negative: 1 }), papers: 4 }, previous: { ...tally(), papers: 0 }, papers: [], more: 0 }] }));
  assert.match(html, /<i class="k-saved" style="width:75\.0%">/);
  assert.match(html, /<i class="k-negative" style="width:25\.0%">/);
});

test('a useful paper is drawn once: its save is not a second colour', () => {
  const html = W.directions(report({ directions: [{ id: 'd', name: 'D', status: 'new', current: { ...tally({ saved: 2, positive: 2 }), papers: 2 }, previous: { ...tally(), papers: 0 }, papers: [], more: 0 }] }));
  assert.doesNotMatch(html, /class="k-saved" style/);
  assert.match(html, /<i class="k-positive" style="width:100\.0%">/);
});

test('directions beyond the list are announced, and a switched-off map says so', () => {
  assert.match(W.directions(report({ more_directions: 3 })), /另有方向没有列出：3/);
  assert.doesNotMatch(W.directions(report()), /另有方向没有列出/);
  const off = report(); off.units.enabled = false;
  assert.match(W.units(off), /学习图现在是关闭状态/);
  assert.doesNotMatch(W.units(report()), /关闭状态/);
});

test('the unsorted bucket can be translated while a person\'s own category names are left alone', () => {
  const html = W.directions(report({ directions: [{ id: '', name: '未分类', status: 'new', current: { ...tally({ positive: 1 }), papers: 1 }, previous: { ...tally(), papers: 0 }, papers: [], more: 0 },
    { id: 'x', name: '我的类别', status: 'new', current: { ...tally({ positive: 1 }), papers: 1 }, previous: { ...tally(), papers: 0 }, papers: [], more: 0 }] }));
  assert.match(html, /<h4>未分类<\/h4>/);
  assert.match(html, /<h4 data-no-i18n>我的类别<\/h4>/);
});

test('missing numbers never print NaN or undefined', () => {
  const html = W.weeklyHTML({ week_start: '2026-10-01', week_end: '2026-10-08', has_activity: true, stats: {}, previous_stats: {}, directions: [{ id: 'q', name: 'Q', status: 'new', current: {}, previous: {}, papers: [] }], daily: [{}], keyword_changes: {} });
  assert.doesNotMatch(html, /NaN|undefined|null/);
});
