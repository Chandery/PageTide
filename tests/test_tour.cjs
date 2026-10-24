'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const T = require('../app/static/tour.js');

function memory() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k) };
}

test('shouldOffer: no project, new version, seen version, already offered this session', () => {
  assert.equal(T.shouldOffer({ version: '0.1.0', seen_version: '0.1.0', project_count: 0 }, null), true);   // no project
  assert.equal(T.shouldOffer({ version: '0.2.0', seen_version: '0.1.0', project_count: 2 }, null), true);   // version differs
  assert.equal(T.shouldOffer({ version: '0.1.0', seen_version: null, project_count: 2 }, null), true);      // never seen
  assert.equal(T.shouldOffer({ version: '0.1.0', seen_version: '0.1.0', project_count: 2 }, null), false);  // seen, has project
  assert.equal(T.shouldOffer({ version: '0.1.0', seen_version: '0.1.0', has_project: false }, null), true);
  assert.equal(T.shouldOffer({ show: true, version: '0.1.0' }, '0.1.0'), false);                            // offered this session
  assert.equal(T.shouldOffer({ show: true, version: '0.2.0' }, '0.1.0'), true);                             // offered an older one
  assert.equal(T.shouldOffer({ show: false, version: '0.2.0' }, null), false);
  assert.equal(T.shouldOffer({ version: '0.1.0', seen_version: '0.1.0', project_count: 0 }, '0.1.0'), false);
  assert.equal(T.shouldOffer(null, null), false);
});

test('four phases in order: project, settings, recommend, library and profile', () => {
  const tour = T.STEPS.filter(s => !s.standalone);
  const phases = [];
  for (const s of tour) if (phases[phases.length - 1] !== s.phase) phases.push(s.phase);
  assert.deepEqual(phases, ['项目', '设置', '推荐', '论文库与画像']);
  const ids = tour.map(s => s.id);
  assert.deepEqual(ids, ['p1', 'p2', 's1', 's2', 's3', 's4', 'r1', 'r2', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7']);
  // library and profile part covers list, graph, profile and the weekly report
  const last = tour.filter(s => s.phase === '论文库与画像').map(s => s.target + ' ' + s.page).join('|');
  assert.match(last, /org-list/); assert.match(last, /graph/); assert.match(last, /data-view="profile"/); assert.match(last, /weekly/);
  assert.equal(new Set(ids).size, ids.length);
});

test('next follows the sequence, skip jumps past settings, the last step finishes', () => {
  assert.equal(T.next(null, 'p1'), 'p2');
  assert.equal(T.next(null, 's1', 'primary'), 's2');
  assert.equal(T.next(null, 's1', 'skip'), 'r1');
  assert.equal(T.next(null, 's4'), 'r1');
  assert.equal(T.next(null, 'r1'), 'r2');
  assert.equal(T.next(null, 'f6'), 'f7');
  assert.equal(T.next(null, 'f7'), 'finish');
  assert.equal(T.next(null, 'c1'), 'finish');
  assert.equal(T.next(null, 'nope'), 'finish');
  let id = 'p1', n = 0;
  while (id !== 'finish' && n++ < 50) id = T.next(null, id);
  assert.equal(id, 'finish'); assert.equal(n, 15);
});

test('stepsFor groups steps by page', () => {
  assert.deepEqual(T.stepsFor('settings').map(s => s.id), ['s2', 's3', 's4']);
  assert.deepEqual(T.stepsFor('weekly').map(s => s.id), ['f7']);
  assert.deepEqual(T.stepsFor('creation').map(s => s.id), ['c1']);
  assert.equal(T.stepsFor('index').length, 11);
  assert.deepEqual(T.stepsFor('nowhere'), []);
});

test('cross-page resume through sessionStorage, and no state means no tour', () => {
  T.setStorage(memory());
  assert.equal(T.current(), null);
  T.begin({ version: '0.1.0', returnProject: 'p-7' });
  assert.deepEqual(T.current(), { v: 1, step: 'p1', version: '0.1.0', returnProject: 'p-7' });
  const raw = JSON.parse(T.serialize(T.current()));
  assert.deepEqual(Object.keys(raw).sort(), ['returnProject', 'step', 'v', 'version']);
  // the settings page restores from what the index page left
  const s = T.pending();
  assert.equal(T.STEPS.find(x => x.id === s.step).page, 'index');
  T.setStorage(memory());
  T.begin({ version: '0.1.0', step: 's2' });
  assert.equal(T.stepsFor('settings').some(x => x.id === T.current().step), true);
  // corrupt, foreign version, unknown step
  const m = memory(); T.setStorage(m);
  m.setItem(T.KEY, '{bad'); assert.equal(T.current(), null);
  m.setItem(T.KEY, JSON.stringify({ v: 2, step: 'p1' })); assert.equal(T.current(), null);
  m.setItem(T.KEY, JSON.stringify({ v: 1, step: 'zz' })); assert.equal(T.current(), null);
  T.setStorage(null);
});

test('begin marks the version as offered for this session', () => {
  const m = memory(); T.setStorage(m);
  T.begin({ version: '0.3.0' });
  assert.equal(m.getItem(T.OFFERED_KEY), '0.3.0');
  assert.equal(T.shouldOffer({ show: true, version: '0.3.0' }, m.getItem(T.OFFERED_KEY)), false);
  T.setStorage(null);
});

test('the creation hint is pending but not demo mode', () => {
  const m = memory(); T.setStorage(m);
  m.setItem(T.KEY, T.serialize({ step: 'c1', version: '0.1.0', returnProject: null }));
  assert.equal(T.current(), null);
  assert.equal(T.pending().step, 'c1');
  T.setStorage(null);
});

test('finishTarget: first project vs back to the previous project', () => {
  assert.deepEqual(T.finishTarget(false), { url: '/project_creation.html', step: 'c1' });
  assert.deepEqual(T.finishTarget(true), { url: '/', step: null });
});

test('every step has text, phase, a page, and a target or the centred mark', () => {
  const pages = new Set(Object.keys(T.PAGE_URL));
  for (const s of T.STEPS) {
    assert.ok(s.text && s.text.trim(), s.id + ' text');
    assert.ok(s.phase && s.phase.trim(), s.id + ' phase');
    assert.ok(pages.has(s.page), s.id + ' page');
    assert.ok(typeof s.target === 'string' ? s.target.length > 0 : s.target === null, s.id + ' target');
    assert.ok(s.advance === 'next' || s.advance === 'click', s.id + ' advance');
    if (s.advance === 'next') assert.ok(s.primary && s.primary.label, s.id + ' primary');
    if (s.primary) assert.ok(s.primary.label.trim());
    assert.ok(!/\d\s*\/\s*\d/.test(s.phase + s.text), s.id + ' shows no counter');
  }
});

test('real selectors: the ones this tour depends on exist in the pages', () => {
  const fs = require('node:fs'), path = require('node:path');
  const read = f => fs.readFileSync(path.join(__dirname, '..', 'app', 'static', f), 'utf8');
  const index = read('index.html'), settings = read('settings.html'), creation = read('project_creation.html'),
    weekly = read('weekly_report.html'), org = read('organization.js'), profile = read('profile-ui.js');
  for (const id of ['projectBtn', 'projectEdit', 'settingsBtn', 'btnDaily', 'cards', 'organizationRoot', 'view-profile']) assert.match(index, new RegExp('id="' + id + '"'));
  assert.match(index, /data-view="library"/); assert.match(index, /data-view="profile"/); assert.match(index, /data-fb="\$\{saved/);
  for (const id of ['apiKey', 'openalexKey', 'baiduScholarKey']) assert.match(settings, new RegExp('id="' + id + '"'));
  assert.match(settings, /class="[^"]*\bsection\b/); assert.match(settings, /class="[^"]*\bsource-row\b/);
  assert.match(creation, /class="modes"/); assert.match(weekly, /id="weeklyContent"/);
  assert.match(org, /class="org-tabs"/); assert.match(org, /data-action="graph"/); assert.match(org, /class="org-list"/);
  assert.match(profile, /class="pd-link" href="\/weekly_report\.html/);
});
