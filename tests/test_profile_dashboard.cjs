'use strict';
// Profile dashboard: numbers come straight from local counts, and the honesty rules hold in the markup.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function load() {
  const context = vm.createContext({ module: { exports: {} } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/profile-ui.js'), 'utf8'), context);
  return context.module.exports;
}

const week = (start, end, counts = {}) => {
  const w = { start, end, positive: 0, negative: 0, too_hard: 0, saved: 0, exposed: 0, ...counts };
  w.activity = w.positive + w.negative + w.too_hard + w.saved + w.exposed;
  return w;
};
const stats = (counts = {}) => {
  const s = { positive: 0, negative: 0, too_hard: 0, saved: 0, exposed: 0, ...counts };
  s.activity = s.positive + s.negative + s.too_hard + s.saved + s.exposed;
  return s;
};
function insights(over = {}) {
  return {
    signals: { pinned: 0, saved: 11, positive: 9, negative: 3, too_hard: 4, seed: 0 },
    timeline: { weeks: [week('2026-09-10', '2026-09-17', { positive: 10, saved: 10, exposed: 35 }), week('2026-09-17', '2026-09-24', { positive: 1, saved: 1, exposed: 15 }), week('2026-09-24', '2026-10-01')] },
    keyword_distribution: [{ term: 'world', documents: 10, sources: ['saved'] }, { term: 'robot', documents: 5, sources: ['saved'] }],
    weekly_change: { week_start: '2026-09-24T00:00:00+00:00', week_end: '2026-10-01T00:00:00+00:00', stats: stats(), previous_stats: stats({ positive: 1, saved: 1, exposed: 15 }), has_activity: false, comparable: false,
      keyword_changes: { rising: [], stable: [], falling: [{ term: 'action', current: 0, previous: 1, delta: -1 }] } },
    ...over,
  };
}

test('KPIs are totals with this-week and last-week counts and a 12-week trend', () => {
  const P = load();
  const m = P.dashboard(insights());
  const byKey = Object.fromEntries(m.kpis.map(k => [k.key, k]));
  assert.deepEqual(Object.keys(byKey), ['saved', 'positive', 'negative', 'too_hard']);
  assert.equal(byKey.saved.value, 11);
  assert.equal(byKey.saved.prev, 1);
  assert.equal(byKey.saved.week, 0);
  assert.deepEqual([...byKey.positive.trend], [10, 1, 0]);
  assert.equal(m.activity.value, 0);
  assert.equal(m.activity.prev, 17);
  assert.equal(m.weeks.peak, 55);
  assert.equal(m.weeks.active, 2);
});

test('useful rate counts only explicit useful vs irrelevant; too hard is left out', () => {
  const P = load();
  const f = P.dashboard(insights()).feedback;
  assert.equal(f.judged, 12);
  assert.equal(f.rate, 75);
  assert.equal(f.too_hard, 4);
  const html = P.feedbackHTML(f);
  assert.match(html, /75%/);
  assert.match(html, /共 12 篇/);
  assert.match(html, /“太难”不计入/);
});

test('with no explicit feedback there is no rate, and small samples are flagged', () => {
  const P = load();
  const none = P.dashboard(insights({ signals: { saved: 3, positive: 0, negative: 0, too_hard: 2 } })).feedback;
  assert.equal(none.rate, null);
  assert.doesNotMatch(P.feedbackHTML(none), /\d+%/);
  const few = P.dashboard(insights({ signals: { saved: 3, positive: 2, negative: 1, too_hard: 0 } })).feedback;
  assert.equal(few.few, true);
  assert.match(P.feedbackHTML(few), /样本还少/);
});

test('activity chart: one evidence button per week, bars scaled to the busiest week, current week labelled', () => {
  const P = load();
  const html = P.activityHTML(P.dashboard(insights()).weeks);
  assert.equal((html.match(/class="pd-col( is-current)?"/g) || []).length, 3);
  assert.equal((html.match(/data-evidence="week"/g) || []).length, 3);
  assert.match(html, /data-start="2026-09-10" data-end="2026-09-17"/);
  assert.match(html, /height:63\.6%/);  // 35 exposures of a 55-record peak
  assert.match(html, /本周/);
  const quiet = P.activityHTML(P.dashboard(insights({ timeline: { weeks: [week('2026-09-24', '2026-10-01')] } })).weeks);
  assert.match(quiet, /不推断兴趣变化/);
});

test('falling terms are not shown when the two weeks are not comparable', () => {
  const P = load();
  const report = insights().weekly_change;
  const html = P.trendHTML(report);
  assert.doesNotMatch(html, /↓/);
  assert.match(html, /这不表示兴趣下降/);
  const comparable = P.trendHTML({ ...report, comparable: true, has_activity: true });
  assert.match(comparable, /↓ action/);
});

test('KPI markup escapes nothing unsafe and keeps the evidence action', () => {
  const P = load();
  const m = P.dashboard(insights());
  const html = P.kpiHTML(m.kpis[3]);
  assert.match(html, /data-evidence="too_hard"/);
  assert.match(html, /不算负面/);
  assert.match(P.kpiHTML(m.activity), /data-evidence="week" data-start="2026-09-24T00:00:00\+00:00"/);
  const hostile = P.trendHTML({ ...insights().weekly_change, comparable: true, keyword_changes: { rising: [{ term: '<img src=x>', delta: 2 }], falling: [] } });
  assert.doesNotMatch(hostile, /<img/);
});
