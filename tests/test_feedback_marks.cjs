'use strict';
const test = require('node:test'), assert = require('node:assert/strict'), vm = require('node:vm'), fs = require('node:fs'), path = require('node:path');
const Marks = require('../app/static/feedback-marks.js');
const index = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');
const esc = s => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const cardSrc = index.slice(index.indexOf('function cardHTML('), index.indexOf('function renderCards('));
const fbSrc = index.slice(index.indexOf('async function doFeedback('), index.indexOf("$('#cards').addEventListener"));

function cardContext() {
  const ctx = vm.createContext({ window: { PDHMarks: Marks }, esc, state: { triaging: false, triagingKeys: new Set() },
    workTypeLabel: v => v, pdfBadge: () => '', routeBadge: () => '', aiSlot: () => '', judgeAskHTML: () => '' });
  vm.runInContext(cardSrc, ctx);
  return ctx;
}
const pressed = (html, fb) => (html.match(new RegExp('data-fb="' + fb + '"[^>]*aria-pressed="(true|false)"')) || [])[1];

test('view: the latest interest label wins and difficulty is its own mark', () => {
  assert.deepEqual(Marks.view({ saved: true, feedback: 'useful', familiarity: null }), { saved: true, irrelevant: false, tooHard: false });
  assert.deepEqual(Marks.view({ saved: true, feedback: 'irrelevant', familiarity: 'too_hard' }), { saved: false, irrelevant: true, tooHard: true });
  assert.deepEqual(Marks.view({ saved: false, feedback: null, familiarity: 'understood' }), { saved: false, irrelevant: false, tooHard: false });
});

test('a card shows the marks pressed and dims only when marked not interested', () => {
  const ctx = cardContext();
  const plain = ctx.cardHTML({ key: 'a', title: 'T' }, 0);
  assert.equal(pressed(plain, 'irrelevant'), 'false'); assert.equal(pressed(plain, 'too_hard'), 'false'); assert.doesNotMatch(plain, /is-passed/);
  const no = ctx.cardHTML({ key: 'a', title: 'T', feedback: 'irrelevant', feedback_id: 12, saved: true, familiarity: 'too_hard' }, 0);
  assert.equal(pressed(no, 'irrelevant'), 'true'); assert.equal(pressed(no, 'too_hard'), 'true');
  assert.match(no, /class="card is-passed"/); assert.match(no, /data-fid="12"/);
  assert.match(no, /data-fb="useful"[^>]*aria-pressed="false"/);   // saved and not interested never both show
  const hard = ctx.cardHTML({ key: 'a', title: 'T', familiarity: 'too_hard', saved: true, feedback: 'useful' }, 0);
  assert.equal(pressed(hard, 'too_hard'), 'true'); assert.equal(pressed(hard, 'irrelevant'), 'false'); assert.doesNotMatch(hard, /is-passed/);
  assert.match(hard, /data-fb="unsave"[^>]*aria-pressed="true"/);
});

test('the detail reply is read as separate interest and difficulty marks', () => {
  assert.deepEqual(Marks.detailMarks({ key: 'k', saved: false, feedback: { action: 'irrelevant', id: 5, familiar: { action: 'too_hard', id: 6 } } }),
    { key: 'k', saved: false, feedback: 'irrelevant', feedback_id: 5, familiarity: 'too_hard' });
  // no interest label: the entry's top-level action is the difficulty one and is not an interest
  assert.deepEqual(Marks.detailMarks({ key: 'k', saved: true, feedback: { action: 'too_hard', id: 6, familiar: { action: 'too_hard', id: 6 } } }),
    { key: 'k', saved: true, feedback: null, feedback_id: null, familiarity: 'too_hard' });
  assert.deepEqual(Marks.detailMarks({ key: 'k', saved: false, feedback: null }), { key: 'k', saved: false, feedback: null, feedback_id: null, familiarity: null });
});

function feedbackContext(replies, card) {
  const calls = [], toasts = [];
  const ctx = vm.createContext({ state: { currentProject: 'p', cards: [card], view: 'today' },
    api: async (url, body) => { calls.push(JSON.parse(JSON.stringify([url, body]))); const r = replies[url]; return typeof r === 'function' ? r(body) : r || {}; },
    toast: (...a) => toasts.push(a), renderCards: () => {}, refreshStats: async () => {} });
  vm.runInContext(fbSrc, ctx);
  return { ctx, calls, toasts };
}
const btn = (fb, pressedValue, fid) => ({ dataset: { fb, key: 'x', fid }, getAttribute: () => String(pressedValue) });

test('not interested: set, shown, then pressed again it is undone by record id and the stored state is used', async () => {
  const card = { key: 'x', saved: false };
  const { ctx, calls, toasts } = feedbackContext({
    '/api/feedback': { feedback_id: 9, interest_changed: true, state: { feedback: 'irrelevant', feedback_id: 9, familiarity: null, saved: false } },
    '/api/undo': { undone: 9, state: { feedback: null, feedback_id: null, familiarity: null, saved: false } } }, card);
  await ctx.feedbackClick(btn('irrelevant', false, ''));
  assert.equal(card.feedback, 'irrelevant'); assert.equal(card.feedback_id, 9);
  assert.deepEqual(calls[0], ['/api/feedback', { key: 'x', action: 'irrelevant', project_id: 'p' }]);
  await ctx.feedbackClick(btn('irrelevant', true, '9'));
  assert.deepEqual(calls[1], ['/api/undo', { feedback_id: 9, project_id: 'p' }]);
  assert.equal(card.feedback, null); assert.equal(card.feedback_id, null);
  assert.equal(toasts.at(-1)[0], '已撤销：不感兴趣');
});

test('not interested on a saved paper: the server does the unsave in one commit; undo gives back what it reports', async () => {
  const card = { key: 'x', saved: true, feedback: 'useful', feedback_id: 3 };
  const { ctx, calls, toasts } = feedbackContext({
    '/api/feedback': { feedback_id: 9, interest_changed: true, unsaved: true, state: { feedback: 'irrelevant', feedback_id: 9, familiarity: null, saved: false } },
    '/api/undo': { undone: 9, restored_saved: true, state: { feedback: 'useful', feedback_id: 3, familiarity: null, saved: true } } }, card);
  await ctx.doFeedback('x', 'irrelevant');
  assert.deepEqual(calls.map(c => c[0]), ['/api/feedback']);   // no separate /api/unsave any more
  assert.equal(card.saved, false); assert.equal(card.feedback, 'irrelevant');
  assert.equal(toasts.at(-1)[0], '已记录：不感兴趣，已取消收藏');
  await ctx.doFeedback('x', 'irrelevant', { undo: true, feedbackId: '9' });
  assert.equal(card.feedback, 'useful'); assert.equal(card.saved, true);   // back to what it was before the press
});

test('a take-back that the server turned into a fresh confirmation is not reported as undone', async () => {
  const card = { key: 'x', saved: true, feedback: 'useful', familiarity: 'too_hard' };
  const { ctx, toasts } = feedbackContext({ '/api/feedback': { reconfirmed: true, retracted: [], feedback_id: 8,
    state: { feedback: 'useful', feedback_id: 3, familiarity: 'too_hard', saved: true } } }, card);
  await ctx.doFeedback('x', 'too_hard', { undo: true });
  assert.equal(toasts.at(-1)[0], '已记录：太难'); assert.equal(card.familiarity, 'too_hard');
});

test('too hard: its own mark, retracted by the feedback route, and it never touches the interest label', async () => {
  const card = { key: 'x', saved: true, feedback: 'useful', feedback_id: 3 };
  const { ctx, calls, toasts } = feedbackContext({
    '/api/feedback': body => body.retract
      ? { retracted: [4], state: { feedback: 'useful', feedback_id: 3, familiarity: null, saved: true } }
      : { feedback_id: 4, state: { feedback: 'useful', feedback_id: 3, familiarity: 'too_hard', saved: true } } }, card);
  await ctx.feedbackClick(btn('too_hard', false));
  assert.equal(card.familiarity, 'too_hard'); assert.equal(card.feedback, 'useful');
  await ctx.feedbackClick(btn('too_hard', true));
  assert.deepEqual(calls[1], ['/api/feedback', { key: 'x', action: 'too_hard', retract: true, project_id: 'p' }]);
  assert.equal(card.familiarity, null); assert.equal(card.feedback, 'useful');
  assert.equal(toasts.at(-1)[0], '已撤销：太难');
});

test('without a stored state in the reply the card still follows the press; save and unsave are not undone', async () => {
  const card = { key: 'x', saved: false };
  const { ctx, calls } = feedbackContext({}, card);
  await ctx.feedbackClick(btn('too_hard', false)); assert.equal(card.familiarity, 'too_hard');
  await ctx.feedbackClick(btn('too_hard', true)); assert.equal(card.familiarity, null);
  await ctx.feedbackClick({ dataset: { fb: 'unsave', key: 'x' }, getAttribute: () => 'true' });
  assert.equal(calls.at(-1)[0], '/api/unsave');   // a pressed save button unsaves; it is never an undo
});

test('the cards, the detail pane and the save toggle all use the same press handling and redraw from stored state', () => {
  assert.match(index, /feedbackClick\(fb\)\.catch/);                      // cards
  assert.match(index, /feedbackClick\(fb\)\.then\(/);                     // detail pane
  assert.match(index, /await openDetail\(d\.key\);\s*\/\/ redrawn from the stored state/);
  assert.match(index, /\.card\.is-passed h3[^}]*opacity:\.5/);
  assert.match(index, /button\[data-fb\]\[aria-pressed="true"\]/);
});
